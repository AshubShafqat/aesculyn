"""Bounded persisted background inference jobs; only sanitized feature arrays are stored."""
import hashlib,json,shutil,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from engine import CLASSES,FEATURES,metrics
from .model import parse_csv

class Jobs:
 def __init__(self,store,registry,incidents=None,workers=2):
  self.store=store;self.registry=registry;self.incidents=incidents;self.root=store.root/'analyses';self.root.mkdir(exist_ok=True);self.pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='analysis');self.lock=threading.Lock()
 def path(self,aid,kind):
  import re
  if not re.fullmatch('[0-9a-f]{32}',aid) or kind not in ['input','result']:raise ValueError('Invalid analysis reference')
  return self.root/(aid+'-'+kind+'.npz')
 def submit(self,user,raw,name,model_id):
  self.registry.get(model_id)
  if shutil.disk_usage(self.root).free<len(raw)*3+1_000_000:raise ValueError('Server storage is low. Free disk space before uploading this batch.')
  x,labels,validation=parse_csv(raw)
  name=str(name).replace('\\','/').rsplit('/',1)[-1].strip()
  if not name or len(name)>120 or any(ord(c)<32 for c in name):raise ValueError('Choose a filename up to 120 printable characters.')
  aid=self.store.create_analysis(user['workspace_id'],name,len(x),model_id,hashlib.sha256(raw).hexdigest(),labels is not None)
  try:
   np.savez_compressed(self.path(aid,'input'),x=x,labels=labels if labels is not None else np.array([],int),validation=np.array(json.dumps(validation)))
  except OSError:
   self.store.update(aid,status='failed',error='Insufficient storage to save this batch.');raise ValueError('Unable to store this batch; check available disk space.')
  self.store.audit_event(user['id'],'analysis_queued',aid);self.pool.submit(self.run,aid);return self.store.analysis(user['workspace_id'],aid)
 def run(self,aid):
  try:
   with self.store.connect() as db:r=db.execute('SELECT * FROM analyses WHERE id=?',(aid,)).fetchone()
   if not r:return
   if self.store.cancelled(aid):self.store.update(aid,status='cancelled',error=None);return
   self.store.update(aid,status='running',progress=1,error=None)
   with np.load(self.path(aid,'input'),allow_pickle=False) as a:x=a['x'];labels=a['labels'];validation=json.loads(str(a['validation']))
   begin=time.perf_counter();probs=[];outside=[]
   for start in range(0,len(x),256):
    if self.store.cancelled(aid):self.store.update(aid,status='cancelled',error=None);return
    p,o=self.registry.predict(r['model_id'],x[start:start+256]);probs.append(p);outside.append(o);self.store.update(aid,progress=min(95,int((start+len(p))/len(x)*95)))
   p=np.concatenate(probs);o=np.concatenate(outside);pred=p.argmax(1);elapsed=(time.perf_counter()-begin)*1000
   if self.store.cancelled(aid):self.store.update(aid,status='cancelled',error=None);return
   summary={'rows':len(x),'counts':{c:int((pred==i).sum()) for i,c in enumerate(CLASSES)},'malicious_predictions':int((pred!=0).sum()),'inference_ms':elapsed,'validation':validation,'out_of_training_range_rows':int(o.any(1).sum()),'out_of_range_features':{c:int(o[:,i].sum()) for i,c in enumerate(FEATURES) if o[:,i].any()},'scores':'Uncalibrated softmax outputs; not confidence guarantees.','severity_rule':'Review required if predicted class is not benign; informational otherwise.','ground_truth':'User-supplied labels, not independently verified.' if len(labels) else 'No ground-truth labels supplied.'}
   if len(labels):summary['evaluation']=metrics(np.array(CLASSES)[labels],np.array(CLASSES)[pred])
   if self.incidents:summary['incidents']=self.incidents.record(dict(r),x,p,self.registry)
   np.savez_compressed(self.path(aid,'result'),prediction=pred,probabilities=p,outside=o.any(1))
   # Serialize cancellation with completion so a late cancellation cannot be lost.
   with self.store.connect() as db:
    db.execute('BEGIN IMMEDIATE');c=db.execute('SELECT cancel FROM analyses WHERE id=?',(aid,)).fetchone()
    if not c:return
    if c['cancel']:db.execute("UPDATE analyses SET status='cancelled',updated=? WHERE id=?",(int(time.time()),aid))
    else:db.execute("UPDATE analyses SET status='completed',progress=100,summary=?,updated=? WHERE id=?",(json.dumps(summary,allow_nan=False),int(time.time()),aid))
  except Exception:
   self.store.update(aid,status='failed',error='Analysis could not finish. Verify the model package and available storage, then retry.')
 def arrays(self,aid):
  with np.load(self.path(aid,'input'),allow_pickle=False) as a:x=a['x'];labels=a['labels']
  with np.load(self.path(aid,'result'),allow_pickle=False) as a:pred=a['prediction'];p=a['probabilities'];outside=a['outside']
  return x,labels,pred,p,outside
 def retry(self,user,record):
  if record['status'] not in ['failed','cancelled']:raise ValueError('Only failed or cancelled analyses can be retried.')
  with np.load(self.path(record['id'],'input'),allow_pickle=False) as a:x=a['x'];labels=a['labels']
  import pandas as pd
  d=pd.DataFrame(x,columns=FEATURES)
  if len(labels):d['label_class']=np.array(CLASSES)[labels]
  return self.submit(user,d.to_csv(index=False).encode(),record['name'],record['model_id'])
 def cancel(self,user,record):
  if record['status'] not in ['queued','running']:raise ValueError('This analysis is no longer running.')
  self.store.update(record['id'],cancel=1);self.store.audit_event(user['id'],'analysis_cancel_requested',record['id'])
 def delete(self,user,record):
  if record['status'] in ['queued','running']:raise ValueError('Cancel the analysis and wait for it to stop before deleting it.')
  # Paths are generated from a validated UUID, never an uploaded filename.
  for kind in ['input','result']:
   p=self.path(record['id'],kind)
   if p.exists():p.unlink()
  if self.incidents:self.incidents.remove_analysis(record['id'])
  self.store.delete(user['workspace_id'],record['id']);
  if self.incidents:self.incidents.remove_analysis(record['id'])
  self.store.audit_event(user['id'],'analysis_deleted',record['id'])
 def close(self):self.pool.shutdown(wait=True,cancel_futures=False)
