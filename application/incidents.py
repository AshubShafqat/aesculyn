"""Workspace-owned incidents and a deliberately simulated response audit."""
import json,time,uuid
from dataclasses import asdict
from ids.rules import detect,RuleConfig
from ids.risk import decide,Policy
from engine import FEATURES,CLASSES

class Incidents:
 def __init__(self,store):
  self.store=store
  with store.connect() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,analysis_id TEXT NOT NULL,row_index INTEGER NOT NULL,created INTEGER NOT NULL,prediction TEXT NOT NULL,level INTEGER NOT NULL,source TEXT NOT NULL,status TEXT NOT NULL,evidence TEXT NOT NULL);CREATE INDEX IF NOT EXISTS incidents_owner ON incidents(workspace_id,created);CREATE TABLE IF NOT EXISTS policy_config(workspace_id TEXT PRIMARY KEY,configuration TEXT NOT NULL);''')
 def config(self,wid):
  with self.store.connect() as db:r=db.execute('SELECT configuration FROM policy_config WHERE workspace_id=?',(wid,)).fetchone()
  return json.loads(r[0]) if r else {'policy':asdict(Policy()),'rules':asdict(RuleConfig()),'mode':'dry-run'}
 def configure(self,user,value):
  if set(value)-{'policy','rules','mode'} or value.get('mode','dry-run')!='dry-run':raise ValueError('Only dry-run response is supported. Host enforcement is disabled.')
  try:
   policy=Policy(**value.get('policy',{})).validate();rules=RuleConfig(**value.get('rules',{}))
   if not isinstance(rules.enabled,dict) or set(rules.enabled)-{'preamble_exec','bad_first_pdu','big_pdu_len','unknown_ae'} or not all(isinstance(v,bool) for v in rules.enabled.values()):raise ValueError('Invalid enabled rules')
   if not isinstance(rules.allowed_ae,list) or len(rules.allowed_ae)>100 or not all(isinstance(x,str) and 1<=len(x)<=16 for x in rules.allowed_ae):raise ValueError('AE titles must be strings of 1–16 characters')
  except (TypeError,KeyError):raise ValueError('Invalid policy configuration')
  data={'policy':asdict(policy),'rules':asdict(rules),'mode':'dry-run'}
  with self.store.connect() as db:db.execute('INSERT OR REPLACE INTO policy_config VALUES(?,?)',(user['workspace_id'],json.dumps(data)))
  self.store.audit_event(user['id'],'dry_run_policy_updated');return data
 def record(self,record,x,p,registry):
  config=self.config(record['workspace_id']);policy=Policy(**config['policy']);rules=RuleConfig(**config['rules']);items=[]
  for i,prob in enumerate(p):
   f=dict(zip(FEATURES,map(float,x[i])));source='batch-row-'+str(i);timestamp=record['created'];hits=detect(f,timestamp,source,rules);risk=decide(1-float(prob[0]),hits,policy=policy);prediction=CLASSES[int(prob.argmax())]
   if risk['level']==0 and not hits:continue
   explanation=registry.explain(record['model_id'],x[i]);top=sorted(explanation['features'],key=lambda a:abs(a['contribution']),reverse=True)[:5]
   evidence={'model_id':record['model_id'],'probabilities':dict(zip(CLASSES,map(float,prob))),'attack_probability':1-float(prob[0]),'rules':hits,'risk':risk,'top_features':top,'explanation':{k:v for k,v in explanation.items() if k!='features'},'summary':'; '.join(h['explanation'] for h in hits) or ('The model predicts '+prediction+'; its largest local logit-margin attributions are '+', '.join(f['feature'] for f in top[:3])+'.'),'source_note':'No source identity is retained by the feature-only CSV flow. Risk is evaluated independently per row; no per-client temporal hysteresis is claimed.','response':{'mode':'dry-run','proposed_action':risk['action'],'executed':False,'review':'pending'}}
   items.append((uuid.uuid4().hex,record['workspace_id'],record['id'],i,timestamp,prediction,risk['level'],source,'open',json.dumps(evidence,allow_nan=False)))
  with self.store.connect() as db:
   db.execute('DELETE FROM incidents WHERE analysis_id=?',(record['id'],));db.executemany('INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?)',items)
  return len(items)
 def list(self,wid,query='',status='all',level='all',attack='all',page=0):
  if status not in ['all','open','acknowledged','resolved'] or level not in ['all','1','2','3'] or attack not in ['all',*CLASSES]:raise ValueError('Invalid incident filter')
  where='workspace_id=?';params=[wid]
  for key,value in [('status',status),('level',level),('prediction',attack)]:
   if value!='all':where+=' AND '+key+'=?';params.append(value)
  if query:where+=' AND (source LIKE ? OR prediction LIKE ?)';params.extend(['%'+query[:80]+'%']*2)
  with self.store.connect() as db:
   count=db.execute('SELECT count(*) FROM incidents WHERE '+where,params).fetchone()[0];rows=db.execute('SELECT id,analysis_id,row_index,created,prediction,level,source,status FROM incidents WHERE '+where+' ORDER BY created DESC,id DESC LIMIT 50 OFFSET ?',(*params,max(0,int(page))*50)).fetchall();levels=db.execute('SELECT level,count(*) AS n FROM incidents WHERE workspace_id=? GROUP BY level',(wid,)).fetchall()
  return {'incidents':[dict(r) for r in rows],'total':count,'page':page,'levels':{str(r['level']):r['n'] for r in levels},'mode':'dry-run'}
 def get(self,wid,iid):
  with self.store.connect() as db:r=db.execute('SELECT * FROM incidents WHERE id=? AND workspace_id=?',(iid,wid)).fetchone()
  if not r:return None
  d=dict(r);d['evidence']=json.loads(d['evidence']);return d
 def review(self,user,iid,status):
  if status not in ['acknowledged','resolved']:raise ValueError('Choose acknowledge or resolve.')
  if not self.get(user['workspace_id'],iid):raise ValueError('Incident not found.')
  with self.store.connect() as db:db.execute('UPDATE incidents SET status=? WHERE id=? AND workspace_id=?',(status,iid,user['workspace_id']))
  self.store.audit_event(user['id'],'incident_'+status,iid)
 def remove_analysis(self,aid):
  with self.store.connect() as db:db.execute('DELETE FROM incidents WHERE analysis_id=?',(aid,))
