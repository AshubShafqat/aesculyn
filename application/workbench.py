"""Local research inventory and bounded, owner-scoped training processes."""
import json,os,subprocess,sys,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
FILES=['ARCHITECTURE_AUDIT.md','APPLICATION.md','APPLICATION_VERIFICATION.md','RESEARCH_RESULTS.md','research/run.py','research/data.py','research/neural.py','research/client.py','research/classical.py','application/provision.py','application/model.py','application/jobs.py','application/http.py','application/incidents.py','application/captures.py','ids/rules.py','ids/risk.py','ids/pcap.py','test_ids.py','test_safety_unit.py','Dockerfile','compose.yaml']

class Workbench:
 def __init__(self,store):
  self.store=store;self.root=store.root/'training';self.root.mkdir(exist_ok=True);self.enabled=os.environ.get('AESCULYN_ENABLE_TRAINING')=='1';self.archive=Path(os.environ.get('AESCULYN_DATASET','data/dataset.zip')).resolve();self.lock=threading.Lock();self.process=None
  with store.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS training_jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,status TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL,configuration TEXT NOT NULL,error TEXT)')
   db.execute("UPDATE training_jobs SET status='interrupted',error='Server restarted; previous child process is not managed by this session.' WHERE status='running'")
 def inventory(self,user):
  with self.store.connect() as db:rows=db.execute('SELECT * FROM training_jobs WHERE user_id=? ORDER BY created DESC LIMIT 30',(user['id'],)).fetchall()
  audit=ROOT/'artifacts/research-v2-final/data_audit.json';r=json.loads(audit.read_text()) if audit.exists() else None
  return {'mode':'local research','training_enabled':self.enabled,'dataset_available':self.archive.is_file(),'files':[{'name':f,'bytes':(ROOT/f).stat().st_size} for f in FILES if (ROOT/f).is_file()],'dataset_audit':r,'jobs':[dict(j) for j in rows],'existing_experiment':{'name':'v2 eight-class diagnostic study','models':51,'aggregation_rounds':240,'report_available':(ROOT/'artifacts/research-v2-final/report.json').is_file()},'notice':'v2 is NumPy, not PyTorch/LightGBM/CNN. Training uses the configured local dataset; public hosting may disable it.'}
 def file(self,name):
  if name not in FILES:raise ValueError('This file is not available in the workbench.')
  return (ROOT/name).read_text(encoding='utf-8')
 def start(self,user,config):
  if not self.enabled:raise ValueError('Training is disabled on this server. Enable it only in the local research environment.')
  if not self.archive.is_file():raise ValueError('The administrator must configure AESCULYN_DATASET with the existing dataset ZIP.')
  seed=int(config.get('seed',17));protocol=config.get('protocol','unseen_site')
  if seed not in [17,29,43] or protocol not in ['unseen_site','temporal_federation']:raise ValueError('Unsupported training seed or protocol.')
  with self.lock:
   if self.process and self.process.poll() is None:raise ValueError('A training experiment is already running on this server.')
   job=uuid.uuid4().hex;folder=self.root/job;folder.mkdir();log=folder/'training.log';output=folder/'experiment';configuration={'pipeline':'v2_numpy_reference','seed':seed,'protocol':protocol,'rounds':20,'label_design':'8 classes; A6 remains in ML in this legacy reproduction'}
   with self.store.connect() as db:db.execute('INSERT INTO training_jobs VALUES(?,?,?,?,?,?,?)',(job,user['id'],'running',int(time.time()),int(time.time()),json.dumps(configuration),None))
   args=[sys.executable,'-u','-m','research.run','--archive',str(self.archive),'--output',str(output),'--seeds',str(seed),'--protocols',protocol]
   with log.open('w',encoding='utf-8') as stream:self.process=subprocess.Popen(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
   threading.Thread(target=self.finish,args=(job,self.process),daemon=True).start();self.store.audit_event(user['id'],'training_started',job)
  return self.job(user,job)
 def finish(self,job,process):
  code=process.wait()
  with self.store.connect() as db:db.execute("UPDATE training_jobs SET status=CASE WHEN status='cancelling' THEN 'cancelled' ELSE ? END,updated=?,error=? WHERE id=?",('completed' if code==0 else 'failed',int(time.time()),None if code==0 else 'Training process failed. Inspect its private log.',job))
 def job(self,user,job):
  with self.store.connect() as db:r=db.execute('SELECT * FROM training_jobs WHERE id=? AND user_id=?',(job,user['id'])).fetchone()
  if not r:return None
  d=dict(r);p=self.root/job/'training.log';d['log']=p.read_text(encoding='utf-8',errors='replace')[-24000:] if p.exists() else '';d['report_available']=(self.root/job/'experiment/report.json').exists();return d
 def cancel(self,user,job):
  r=self.job(user,job)
  if not r:raise ValueError('Training job not found.')
  with self.lock:
   if r['status']!='running' or not self.process or self.process.poll() is not None:raise ValueError('This training process is not running.')
   with self.store.connect() as db:db.execute("UPDATE training_jobs SET status='cancelling' WHERE id=?",(job,))
   self.process.terminate();self.store.audit_event(user['id'],'training_cancelled',job)
 def close(self):
  with self.lock:
   if self.process and self.process.poll() is None:self.process.terminate()
