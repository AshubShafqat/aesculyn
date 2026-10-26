"""Private offline capture reports. Raw capture bytes are never retained."""
import hashlib,io,json,secrets,time,uuid
from dataclasses import asdict
from ids.pcap import extract
from ids.rules import detect,RuleConfig
from ids.risk import decide,Policy
class Captures:
 def __init__(self,store,incidents):
  self.store=store;self.incidents=incidents;self.root=store.root/'captures';self.root.mkdir(exist_ok=True)
  key=store.root/'source-salt'
  if not key.exists():key.write_text(secrets.token_hex(32))
  self.salt=key.read_text()
  with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS captures(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,name TEXT NOT NULL,created INTEGER NOT NULL,summary TEXT NOT NULL)')
 def submit(self,user,raw,name):
  if not raw or len(raw)>5000000:raise ValueError('PCAP limit is 5 MB.')
  with self.store.connect() as db:
   if db.execute('SELECT count(*) FROM captures WHERE workspace_id=?',(user['workspace_id'],)).fetchone()[0]>=20:raise ValueError('Workspace capture limit is 20. Delete old capture reports first.')
  report=extract(io.BytesIO(raw),self.salt+'|'+user['workspace_id']);config=self.incidents.config(user['workspace_id']);policy=Policy(**config['policy']);rules=RuleConfig(**config['rules']);states={};level_counts={str(i):0 for i in range(4)};rule_counts={};events=[];created=int(time.time());cid=uuid.uuid4().hex
  for i,w in enumerate(report['windows']):
   hits=detect(w['features'],w['timestamp'],w['source'],rules,w['visible_ae']);risk=decide(0,hits,states.get(w['source']),policy);states[w['source']]=risk;level_counts[str(risk['level'])]+=1
   # AE title contents are discarded after evaluating the local allowlist.
   w.pop('visible_ae',None);w['rules']=hits;w['risk']=risk
   for hit in hits:
    rule_counts[hit['rule']]=rule_counts.get(hit['rule'],0)+1
    if 'unknown_titles' in hit['evidence']:hit['evidence']={'unknown_title_count':len(hit['evidence']['unknown_titles'])}
   if risk['level']:
    evidence={'capture_id':cid,'mode':'rules-only','rules':hits,'risk':risk,'summary':'; '.join(h['explanation'] for h in hits) or 'The prior rule-driven level is held until clean-window hysteresis releases it.','response':{'mode':'dry-run','proposed_action':risk['action'],'executed':False},'source_note':'Workspace-specific pseudonym, not a model input. Missing windows are not treated as clean observations.','timestamp':w['timestamp'],'probabilities':None,'attack_probability':None,'top_features':[]}
    events.append((uuid.uuid4().hex,user['workspace_id'],cid,i,created,'preamble_polyglot' if any(h['rule']=='preamble_exec' for h in hits) else 'rule_indicator',risk['level'],'capture-'+cid,'open',json.dumps(evidence)))
  summary={k:v for k,v in report.items() if k!='windows'};summary.update(windows=len(report['windows']),rules=rule_counts,levels=level_counts,mode='offline PCAP / rules-only / dry-run',sha256=hashlib.sha256(raw).hexdigest(),incidents=len(events));report['summary']=summary
  (self.root/(cid+'.json')).write_text(json.dumps(report,allow_nan=False),encoding='utf-8');name=str(name).replace('\\','/').rsplit('/',1)[-1][:120]
  with self.store.connect() as db:
   db.execute('INSERT INTO captures VALUES(?,?,?,?,?)',(cid,user['workspace_id'],name,created,json.dumps(summary)));db.executemany('INSERT INTO incidents VALUES(?,?,?,?,?,?,?,?,?,?)',events)
  self.store.audit_event(user['id'],'offline_capture_analyzed',cid);return self.get(user,cid)
 def list(self,user):
  with self.store.connect() as db:rows=db.execute('SELECT * FROM captures WHERE workspace_id=? ORDER BY created DESC',(user['workspace_id'],)).fetchall()
  return [{**dict(r),'summary':json.loads(r['summary'])} for r in rows]
 def get(self,user,cid):
  with self.store.connect() as db:r=db.execute('SELECT * FROM captures WHERE id=? AND workspace_id=?',(cid,user['workspace_id'])).fetchone()
  if not r:return None
  d=dict(r);d['summary']=json.loads(d['summary']);return d
 def report(self,user,cid):
  if not self.get(user,cid):return None
  return json.loads((self.root/(cid+'.json')).read_text(encoding='utf-8'))
 def delete(self,user,cid):
  if not self.get(user,cid):raise ValueError('Capture report not found.')
  (self.root/(cid+'.json')).unlink();self.incidents.remove_analysis(cid)
  with self.store.connect() as db:db.execute('DELETE FROM captures WHERE id=? AND workspace_id=?',(cid,user['workspace_id']))
  self.store.audit_event(user['id'],'capture_report_deleted',cid)
