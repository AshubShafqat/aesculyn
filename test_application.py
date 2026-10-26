"""Account isolation, real checkpoint inference, schema and explanation verification."""
import csv,hashlib,http.client,io,json,tempfile,threading,time,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
import numpy as np
from application.http import Application,handler_for
from application.model import parse_csv,Registry
from application.store import Store,password_matches
from engine import FEATURES,CLASSES
ROOT=Path(__file__).resolve().parent

def sample(n=3,labels=False):
 d=io.StringIO();w=csv.writer(d);w.writerow(FEATURES+(['label_class'] if labels else []))
 for i in range(n):w.writerow([i]*25+([CLASSES[i%8]] if labels else []))
 return d.getvalue().encode()

class SchemaTests(unittest.TestCase):
 def test_valid_optional_labels(self):
  x,y,a=parse_csv(sample(labels=True));self.assertEqual(x.shape,(3,25));self.assertEqual(y.tolist(),[0,1,2]);self.assertEqual(a['ignored_columns'],0)
 def test_invalid(self):
  for raw in [b'',b'a,b\n1,2',sample().replace(b'out_pkts',b'in_pkts'),sample().replace(b'0,0',b'-1,0',1),sample().replace(b'0,0',b'nan,0',1),sample().replace(b'0,0',b'0.5,0',1),sample(labels=True).replace(b'benign',b'unknown'),sample(10001)]:
   with self.subTest(raw=raw[:40]),self.assertRaises(ValueError):parse_csv(raw)
 def test_extra_columns_excluded(self):
  raw=sample().decode().splitlines();raw[0]+=',patient_name'
  for i in range(1,len(raw)):raw[i]+=',DO_NOT_STORE'
  x,y,a=parse_csv('\n'.join(raw).encode());self.assertEqual(x.shape[1],25);self.assertEqual(a['ignored_columns'],1)

class StoreTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_password_session_and_revocation(self):
  token,csrf,u=self.s.register('a@example.com','Researcher','a-strong-test-password');s=self.s.authenticate(token);self.assertTrue(self.s.csrf(s,csrf));self.assertFalse(self.s.csrf(s,'wrong'));self.assertEqual(csrf,self.s.rotate_csrf(token))
  with self.s.connect() as db:
   encoded=db.execute('SELECT password FROM users').fetchone()[0];stored=db.execute('SELECT token FROM sessions').fetchone()[0]
  self.assertNotEqual(token,stored);self.assertNotIn('a-strong-test-password',encoded);self.assertTrue(password_matches('a-strong-test-password',encoded))
  self.s.change_password(u['id'],'a-strong-test-password','a-second-good-password');self.assertIsNone(self.s.authenticate(token))
  with self.assertRaises(ValueError):self.s.login('a@example.com','a-strong-test-password')
  self.s.login('a@example.com','a-second-good-password')
 def test_ownership_and_recovery(self):
  _,_,a=self.s.register('a@example.com','A','test-password-long');_,_,b=self.s.register('b@example.com','B','test-password-long');aid=self.s.create_analysis(a['workspace_id'],'test',3,'m','h',False)
  self.assertIsNone(self.s.analysis(b['workspace_id'],aid));Store(self.tmp.name);self.assertEqual(self.s.analysis(a['workspace_id'],aid)['status'],'failed')
 def test_rate_limit(self):
  self.assertTrue(self.s.throttle('x',limit=1));self.assertFalse(self.s.throttle('x',limit=1))

@unittest.skipUnless((ROOT/'modelstore/registry.json').exists(),'Provision the private model package first')
class ApplicationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.app=Application(cls.tmp.name,ROOT/'modelstore','http://127.0.0.1:8780');cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(cls.app));cls.port=cls.server.server_port;cls.app.authority=f'127.0.0.1:{cls.port}';cls.app.origin='http://'+cls.app.authority;cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.a=cls.account('one@example.com');cls.b=cls.account('two@example.com')
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.app.close();cls.tmp.cleanup()
 @classmethod
 def request(cls,path,method='GET',body=None,account=None,headers=None):
  h={'Content-Type':'application/json'}
  if account:h.update({'Cookie':account['cookie'],'X-CSRF-Token':account['csrf']})
  h.update(headers or {});data=json.dumps(body).encode() if isinstance(body,dict) else body;c=http.client.HTTPConnection('127.0.0.1',cls.port,timeout=20);c.request(method,path,data,h);r=c.getresponse();raw=r.read();result=(r.status,dict(r.getheaders()),raw);c.close();return result
 @classmethod
 def account(cls,email):
  status,h,raw=cls.request('/api/auth/register','POST',{'email':email,'name':'Local tester','password':'a-test-only-password'});assert status==200,raw;d=json.loads(raw);return {'cookie':h['Set-Cookie'].split(';')[0],'csrf':d['csrf'],'user':d['user']}
 def upload(self,labels=True):
  s,h,b=self.request('/api/analyses?name=test.csv&model='+self.app.registry.default,'POST',sample(labels=labels),self.a,{'Content-Type':'text/csv'});self.assertEqual(s,202,b);aid=json.loads(b)['analysis']['id']
  for _ in range(100):
   s,h,b=self.request('/api/analyses/'+aid,account=self.a);r=json.loads(b)['analysis']
   if r['status'] not in ['running','queued']:break
   time.sleep(.03)
  self.assertEqual(r['status'],'completed',r);return aid,r
 def test_auth_csrf_origin_host(self):
  self.assertEqual(self.request('/api/analyses')[0],401)
  self.assertEqual(self.request('/api/workspace','PATCH',{'name':'x'},self.a,{'X-CSRF-Token':'invalid'})[0],403)
  self.assertEqual(self.request('/api/workspace','PATCH',{'name':'x'},self.a,{'Origin':'https://other.example'})[0],403)
  self.assertEqual(self.request('/api/health',headers={'Host':'evil.example'})[0],421)
  s,h,b=self.request('/api/session',account=self.a);self.assertEqual(json.loads(b)['csrf'],self.a['csrf']);self.assertIn('HttpOnly',self.request('/api/auth/login','POST',{'email':'one@example.com','password':'a-test-only-password'})[1]['Set-Cookie'])
 def test_real_inference_exports_and_ownership(self):
  aid,r=self.upload();self.assertEqual(sum(r['summary']['counts'].values()),3);self.assertIn('evaluation',r['summary']);self.assertEqual(r['summary']['evaluation']['records'],3)
  for op in ['', '/rows','/explanation','/predictions.csv','/report.json','/report.html']:
   self.assertEqual(self.request('/api/analyses/'+aid+op,account=self.b)[0],404)
   self.assertEqual(self.request('/api/analyses/'+aid+op,account=self.a)[0],200)
  self.assertEqual(self.request('/api/analyses/'+aid,'DELETE',{'confirm':aid},self.b)[0],404)
  s,h,b=self.request('/api/analyses/'+aid+'/rows',account=self.a);self.assertEqual(len(json.loads(b)['rows']),3)
  self.assertEqual(self.request('/api/analyses/'+aid+'/explanation?row=99',account=self.a)[0],400)
  self.assertEqual(self.request('/api/analyses/'+aid,'DELETE',{'confirm':'no'},self.a)[0],400)
  self.assertEqual(self.request('/api/analyses/'+aid,'DELETE',{'confirm':aid},self.a)[0],200);self.assertFalse(self.app.jobs.path(aid,'input').exists());self.assertFalse(self.app.jobs.path(aid,'result').exists())
 def test_explanation_completeness(self):
  x,_,_=parse_csv(sample());e=self.app.registry.explain(self.app.registry.default,x[2]);total=sum(f['contribution'] for f in e['features']);self.assertAlmostEqual(e['input_margin']-e['baseline_margin'],total+e['completeness_residual'],places=9);self.assertTrue(e['converged']);self.assertEqual(len(e['features']),25)
 def test_checkpoint_prediction_consistency(self):
  aid,r=self.upload(False);x,labels,pred,p,_=self.app.jobs.arrays(aid);direct,_=self.app.registry.predict(r['model_id'],x);np.testing.assert_array_equal(p.argmax(1),pred);np.testing.assert_allclose(p,direct,rtol=0,atol=0);self.assertNotIn('evaluation',r['summary'])
 def test_model_tampering_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);manifest=json.loads((ROOT/'modelstore/registry.json').read_text());manifest['models'][0]['sha256']='0'*64;(p/'registry.json').write_text(json.dumps(manifest));self.assertFalse(Registry(p).models)
 def test_cancel_and_retry(self):
  u=self.a['user'];aid=self.app.store.create_analysis(u['workspace_id'],'cancel.csv',3,self.app.registry.default,'x',False);x,_,validation=parse_csv(sample());np.savez_compressed(self.app.jobs.path(aid,'input'),x=x,labels=np.array([],int),validation=np.array(json.dumps(validation)));r=self.app.store.analysis(u['workspace_id'],aid);self.app.jobs.cancel(u,r);self.app.jobs.run(aid);r=self.app.store.analysis(u['workspace_id'],aid);self.assertEqual(r['status'],'cancelled');new=self.app.jobs.retry(u,r);self.assertNotEqual(new['id'],aid)

if __name__=='__main__':unittest.main()
