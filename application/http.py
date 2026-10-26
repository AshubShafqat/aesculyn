"""HTTP interface for a real local/offline application; deployment sits behind HTTPS."""
import argparse,csv,html,io,json,os,re,secrets,shutil,threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import numpy as np
from engine import FEATURES,CLASSES
from .store import Store
from .model import Registry
from .jobs import Jobs
from .workbench import Workbench
from .incidents import Incidents
from .captures import Captures
ROOT=Path(__file__).resolve().parent.parent

class Application:
 def __init__(self,data,models,origin):
  parsed=urlparse(origin)
  if parsed.scheme not in ['http','https'] or not parsed.netloc or parsed.path not in ('','/'):raise ValueError('Public URL must be an HTTP(S) origin without a path.')
  if parsed.scheme!='https' and parsed.hostname not in ['localhost','127.0.0.1','::1']:raise ValueError('Public deployments require an HTTPS public URL.')
  self.origin=origin.rstrip('/');self.authority=parsed.netloc;self.secure=parsed.scheme=='https';self.store=Store(data);self.registry=Registry(models);self.incidents=Incidents(self.store);self.captures=Captures(self.store,self.incidents);self.jobs=Jobs(self.store,self.registry,self.incidents);self.workbench=Workbench(self.store)
 def close(self):self.workbench.close();self.jobs.close()

def handler_for(app):
 class Handler(BaseHTTPRequestHandler):
  server_version='Aesculyn';sys_version=''
  def setup(self):
   super().setup();self.connection.settimeout(20)
  def log_message(self,*args):pass
  def send(self,obj,status=200,kind='application/json',cookie=None,download=None):
   raw=json.dumps(obj,allow_nan=False).encode() if kind=='application/json' else obj
   self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
   if app.secure:self.send_header('Strict-Transport-Security','max-age=31536000')
   if cookie is not None:self.send_header('Set-Cookie',cookie)
   if download:self.send_header('Content-Disposition','attachment; filename="'+download+'"')
   self.end_headers();self.wfile.write(raw)
  def fail(self,message,status=400):return self.send({'error':message},status)
  def cookie(self,token,clear=False):return 'aesculyn_session='+('' if clear else token)+'; HttpOnly; SameSite=Strict; Path=/; Max-Age='+('0' if clear else '28800')+('; Secure' if app.secure else '')
  def token(self):
   try:
    c=SimpleCookie();c.load(self.headers.get('Cookie',''));return c['aesculyn_session'].value if 'aesculyn_session' in c else ''
   except Exception:return ''
  def allowed_host(self):
   host=self.headers.get('Host','');return host==app.authority or (not app.secure and host in [app.authority.replace('127.0.0.1','localhost'),app.authority.replace('localhost','127.0.0.1')])
  def identity(self,mutating=False):
   session=app.store.authenticate(self.token())
   if not session:self.fail('Sign in to continue.',401);return None
   if mutating and not app.store.csrf(session,self.headers.get('X-CSRF-Token','')):self.fail('Session verification failed. Refresh and try again.',403);return None
   return app.store.user(session['user_id'])
  def body(self,limit=16_384):
   if self.headers.get('Transfer-Encoding'):raise ValueError('Chunked request bodies are not supported.')
   try:n=int(self.headers.get('Content-Length','0'))
   except ValueError:raise ValueError('Invalid request length.')
   if n<=0 or n>limit:raise ValueError('Request size exceeds the supported limit.')
   self.connection.settimeout(20);raw=self.rfile.read(n)
   if len(raw)!=n:raise ValueError('Incomplete upload.')
   return raw
  def payload(self):
   try:r=json.loads(self.body())
   except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('Invalid JSON request.')
   if not isinstance(r,dict):raise ValueError('Expected a JSON object.')
   return r
  def route(self,method):
   if not self.allowed_host():return self.fail('Host is not allowed.',421)
   u=urlparse(self.path);q=parse_qs(u.query);path=u.path
   if method!='GET' and self.headers.get('Origin') not in (None,app.origin,app.origin.replace('127.0.0.1','localhost') if not app.secure else app.origin):return self.fail('Origin is not allowed.',403)
   if method=='GET' and path in ['/','/app.js','/style.css','/favicon.svg']:
    name={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}[path];file=ROOT/'application/ui'/name;kind={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}[file.suffix];return self.send(file.read_bytes(),kind=kind)
   if method=='GET' and path=='/api/health':return self.send({'status':'ok','analysis_ready':bool(app.registry.models),'mode':'offline batch analysis','storage_available':shutil.disk_usage(app.store.root).free>2_000_000})
   if method=='POST' and path in ['/api/auth/register','/api/auth/login']:
    if not app.store.throttle('auth:'+self.client_address[0],limit=20):return self.fail('Too many authentication attempts. Try again in ten minutes.',429)
    d=self.payload()
    result=app.store.register(d.get('email',''),d.get('name',''),d.get('password','')) if path.endswith('register') else app.store.login(d.get('email',''),d.get('password',''))
    token,csrf,user=result;return self.send({'user':user,'csrf':csrf},cookie=self.cookie(token))
   user=self.identity(method!='GET')
   if not user:return
   if method=='GET' and path=='/api/session':return self.send({'user':user,'csrf':app.store.rotate_csrf(self.token())})
   if method=='POST' and path=='/api/auth/logout':app.store.logout(self.token());return self.send({'ok':True},cookie=self.cookie('',True))
   if method=='POST' and path=='/api/auth/password':
    d=self.payload();app.store.change_password(user['id'],d.get('current_password',''),d.get('new_password',''));return self.send({'ok':True},cookie=self.cookie('',True))
   if method=='PATCH' and path=='/api/workspace':app.store.rename_workspace(user['id'],self.payload().get('name',''));return self.send({'user':app.store.user(user['id'])})
   if method=='GET' and path=='/api/models':return self.send({'default':app.registry.default,'models':app.registry.cards(),'error':app.registry.error})
   if method=='GET' and path=='/api/captures':return self.send({'captures':app.captures.list(user)})
   if method=='POST' and path=='/api/captures':
    if not app.store.throttle('capture:'+user['id'],limit=20,seconds=3600):return self.fail('Capture analysis limit reached.',429)
    return self.send({'capture':app.captures.submit(user,self.body(5_000_000),q.get('name',['capture.pcap'])[0])},202)
   capture=re.fullmatch(r'/api/captures/([0-9a-f]{32})(?:/(report|windows))?',path)
   if capture:
    cid,op=capture.groups();r=app.captures.get(user,cid)
    if not r:return self.fail('Capture report not found.',404)
    if method=='GET' and op=='report':return self.send(json.dumps(app.captures.report(user,cid)).encode(),kind='application/json; charset=utf-8',download='capture-'+cid[:8]+'.json')
    if method=='GET' and op=='windows':
     page=max(0,int(q.get('page',['0'])[0]));r=app.captures.report(user,cid);return self.send({'windows':r['windows'][page*20:page*20+20],'total':len(r['windows']),'page':page})
    if method=='GET':return self.send({'capture':r})
    if method=='DELETE':
     if self.payload().get('confirm')!=cid:raise ValueError('Deletion confirmation required.')
     app.captures.delete(user,cid);return self.send({'ok':True})
    return self.fail('Capture operation unavailable.',404)
   if method=='GET' and path=='/api/incidents':return self.send(app.incidents.list(user['workspace_id'],q.get('search',[''])[0],q.get('status',['all'])[0],q.get('level',['all'])[0],q.get('class',['all'])[0],int(q.get('page',['0'])[0])))
   if method=='GET' and path=='/api/policy':return self.send(app.incidents.config(user['workspace_id']))
   if method=='PATCH' and path=='/api/policy':return self.send(app.incidents.configure(user,self.payload()))
   incident=re.fullmatch(r'/api/incidents/([0-9a-f]{32})',path)
   if incident:
    iid=incident.group(1);item=app.incidents.get(user['workspace_id'],iid)
    if not item:return self.fail('Incident not found.',404)
    if method=='GET':return self.send({'incident':item})
    if method=='PATCH':app.incidents.review(user,iid,self.payload().get('status'));return self.send({'incident':app.incidents.get(user['workspace_id'],iid)})
    return self.fail('Operation unavailable.',404)
   if method=='GET' and path=='/api/workbench':return self.send(app.workbench.inventory(user))
   if method=='GET' and path=='/api/workbench/file':return self.send({'name':q.get('name',[''])[0],'content':app.workbench.file(q.get('name',[''])[0])})
   if method=='POST' and path=='/api/workbench/train':return self.send({'job':app.workbench.start(user,self.payload())},202)
   training=re.fullmatch(r'/api/workbench/jobs/([0-9a-f]{32})(?:/(cancel|report))?',path)
   if training:
    job,op=training.groups();r=app.workbench.job(user,job)
    if not r:return self.fail('Training job not found.',404)
    if method=='GET' and op is None:return self.send({'job':r})
    if method=='POST' and op=='cancel':app.workbench.cancel(user,job);return self.send({'ok':True})
    if method=='GET' and op=='report' and r['report_available']:return self.send((app.workbench.root/job/'experiment/report.json').read_bytes(),kind='application/json; charset=utf-8',download='aesculyn-experiment-'+job[:8]+'.json')
    return self.fail('Training operation unavailable.',409)
   if method=='GET' and path=='/api/events':return self.send({'events':app.store.events(user['id'])})
   if method=='GET' and path=='/api/research':
    file=ROOT/'public/research.json'
    if not file.exists():return self.fail('Research evidence package is not installed.',503)
    return self.send(json.loads(file.read_text(encoding='utf-8')))
   if method=='GET' and path=='/api/template':return self.send((','.join(FEATURES)+'\n').encode(),kind='text/csv; charset=utf-8',download='aesculyn-input-template.csv')
   if method=='GET' and path=='/api/analyses':return self.send({'analyses':app.store.list_analyses(user['workspace_id'])})
   if method=='POST' and path=='/api/analyses':
    if not app.store.throttle('upload:'+user['id'],limit=30,seconds=3600):return self.fail('Hourly analysis limit reached.',429)
    if not self.headers.get('Content-Type','').startswith('text/csv'):raise ValueError('Upload the CSV as text/csv.')
    raw=self.body(5_000_000);r=app.jobs.submit(user,raw,q.get('name',['analysis.csv'])[0],q.get('model',[app.registry.default])[0]);return self.send({'analysis':r},202)
   match=re.fullmatch(r'/api/analyses/([0-9a-f]{32})(?:/(rows|explanation|predictions.csv|report.json|report.html|cancel|retry))?',path)
   if not match:return self.fail('Not found.',404)
   aid,operation=match.groups();r=app.store.analysis(user['workspace_id'],aid)
   if not r:return self.fail('Analysis not found.',404)
   if method=='GET' and operation is None:return self.send({'analysis':r})
   if method=='DELETE' and operation is None:
    if self.payload().get('confirm')!=aid:raise ValueError('Deletion confirmation is required.')
    app.jobs.delete(user,r);return self.send({'ok':True})
   if method=='POST' and operation=='cancel':app.jobs.cancel(user,r);return self.send({'ok':True})
   if method=='POST' and operation=='retry':return self.send({'analysis':app.jobs.retry(user,r)},202)
   if method!='GET':return self.fail('Not found.',404)
   if r['status']!='completed':return self.fail('Results are available after analysis completes.',409)
   if operation in ['rows','explanation','predictions.csv']:
    x,labels,pred,p,outside=app.jobs.arrays(aid)
    if operation=='rows':
     page=max(0,int(q.get('page',['0'])[0]));query=q.get('class',['all'])[0]
     if query not in ['all',*CLASSES]:raise ValueError('Unknown class filter.')
     ix=np.arange(len(x)) if query=='all' else np.flatnonzero(pred==CLASSES.index(query));chunk=ix[page*20:page*20+20]
     return self.send({'total':len(ix),'page':page,'rows':[{'row':int(i),'prediction':CLASSES[pred[i]],'actual':CLASSES[labels[i]] if len(labels) else None,'review':bool(pred[i]!=0),'outside_training_range':bool(outside[i]),'features':{c:float(x[i,j]) for j,c in enumerate(FEATURES)}} for i in chunk]})
    if operation=='explanation':
     index=int(q.get('row',['0'])[0])
     if index<0 or index>=len(x):raise ValueError('Row index is outside this analysis.')
     e=app.registry.explain(r['model_id'],x[index]);e['row']=index;return self.send(e)
    output=io.StringIO();w=csv.writer(output);w.writerow(['row','prediction','review_required','outside_training_range']+(['user_supplied_label'] if len(labels) else []))
    for i in range(len(x)):w.writerow([i,CLASSES[pred[i]],bool(pred[i]!=0),bool(outside[i])]+([CLASSES[labels[i]]] if len(labels) else []))
    return self.send(output.getvalue().encode(),kind='text/csv; charset=utf-8',download='aesculyn-predictions-'+aid[:8]+'.csv')
   if operation in ['report.json','report.html']:
    model=next(c for c in app.registry.cards() if c['id']==r['model_id']);data={'analysis':r,'model':model,'notice':'Offline experimental predictions, not confirmed incidents. Uploaded labels, if present, are not independently verified.'}
    if operation=='report.json':return self.send(json.dumps(data,indent=2).encode(),kind='application/json; charset=utf-8',download='aesculyn-report-'+aid[:8]+'.json')
    safe=html.escape;body='<!doctype html><html lang="en"><meta charset="utf-8"><title>Aesculyn analysis report</title><style>body{font:15px/1.7 system-ui;max-width:850px;margin:50px auto;color:#173e49}h1{color:#087f86}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #d8e5e8;padding:8px;text-align:left}@media print{body{margin:15mm}}</style><h1>Aesculyn · Analysis report</h1><p>'+safe(r['name'])+'</p><p>'+safe(data['notice'])+'</p><p>Model: '+safe(model['name'])+' · '+safe(model['id'])+'</p><table><tr><th>Predicted class</th><th>Records</th></tr>'+''.join('<tr><td>'+safe(c)+'</td><td>'+str(n)+'</td></tr>' for c,n in r['summary']['counts'].items())+'</table><h2>Analysis metadata and limitations</h2><pre>'+safe(json.dumps(data,indent=2))+'</pre></html>'
    return self.send(body.encode(),kind='text/html; charset=utf-8',download='aesculyn-report-'+aid[:8]+'.html')
   return self.fail('Not found.',404)
  def dispatch(self,method):
   try:self.route(method)
   except ValueError as e:self.fail(str(e))
   except (FileNotFoundError,OSError):self.fail('Required storage or model files are unavailable. Contact the application administrator.',503)
   except Exception:self.fail('The request could not be completed. Try again or contact the application administrator.',500)
  def do_GET(self):self.dispatch('GET')
  def do_POST(self):self.dispatch('POST')
  def do_PATCH(self):self.dispatch('PATCH')
  def do_DELETE(self):self.dispatch('DELETE')
 return Handler

def main():
 p=argparse.ArgumentParser();p.add_argument('--host',default=os.environ.get('AESCULYN_HOST','127.0.0.1'));p.add_argument('--port',type=int,default=int(os.environ.get('PORT','8780')));p.add_argument('--data',type=Path,default=Path(os.environ.get('AESCULYN_DATA','appdata')));p.add_argument('--models',type=Path,default=Path(os.environ.get('AESCULYN_MODELS','modelstore')));p.add_argument('--public-url',default=os.environ.get('AESCULYN_PUBLIC_URL'));a=p.parse_args();origin=a.public_url or f'http://127.0.0.1:{a.port}';app=Application(a.data,a.models,origin);server=ThreadingHTTPServer((a.host,a.port),handler_for(app));server.daemon_threads=True;print('Aesculyn application:',origin,flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close();app.close()
if __name__=='__main__':main()
