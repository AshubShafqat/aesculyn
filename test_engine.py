import unittest,tempfile,zipfile,json,urllib.request,urllib.error
from pathlib import Path
import numpy as np
import pandas as pd
from engine import *
class EngineTests(unittest.TestCase):
 def test_label_mapping(self):
  s=json.loads((ROOT/'artifacts/summary.json').read_text());self.assertEqual(s['distribution']['benign'],31652);self.assertEqual(sum(s['distribution'].values()),38401)
 def test_no_leakage_columns(self):
  self.assertEqual(len(FEATURES),25);self.assertFalse(set(FEATURES)&{'label_binary','label_class','window_start','scenario_id','client_ip','site','run_id','split_site'})
 def test_invalid_missing_empty_nonfinite_negative(self):
  for frame in [pd.DataFrame(),pd.DataFrame([{c:0 for c in FEATURES if c!='syn'}]),pd.DataFrame([{c:np.inf for c in FEATURES}]),pd.DataFrame([{c:-1 for c in FEATURES}]),pd.DataFrame([{c:'bad' for c in FEATURES}])]:
   with self.assertRaises(ValueError): validate_frame(frame)
 def test_feature_order(self):
  d=pd.DataFrame([{c:i for i,c in enumerate(FEATURES)}]);np.testing.assert_array_equal(validate_frame(d),validate_frame(d[list(reversed(FEATURES))]))
 def test_duplicate_isolation(self):
  d=pd.DataFrame([{**{c:v for c in FEATURES},'split':part} for part,v in [('train',1),('test',1),('test',2),('val',3)]]);m,r=split_data(d,'split');self.assertEqual(r['test'],1);self.assertEqual(m['test'].sum(),1)
 def test_metric_hand_calculation(self):
  m=metrics(np.array(['benign','benign','recon','recon']),np.array(['benign','recon','benign','recon']));self.assertEqual(m['accuracy'],.5);self.assertEqual(m['false_negatives'],1);self.assertEqual(m['false_positives'],1);self.assertEqual(m['false_negative_rate'],.5)
 def test_explanation_additivity(self):
  d=pd.read_csv(ROOT/'artifacts/test_predictions.csv').head(20);model=load_model();t=terms(validate_frame(d),model)
  for a in t:
   s=a.sum(1)+np.log(model['prior']);o=np.argsort(s);self.assertAlmostEqual(float((a[o[-1]]-a[o[-2]]).sum()+np.log(model['prior'][o[-1]]/model['prior'][o[-2]])),float(s[o[-1]]-s[o[-2]]),places=7)
 def test_saved_metrics_reproduce(self):
  d=pd.read_csv(ROOT/'artifacts/test_predictions.csv');m=metrics(d.label_class.values,predict(validate_frame(d),load_model()));s=json.loads((ROOT/'artifacts/summary.json').read_text());self.assertEqual(m,s['experiments']['split_site']['test'])
 def test_zip_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bad.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('../features.csv','x\n1')
   with self.assertRaises(ValueError):inspect_archive(p)
 def test_bad_zip_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'bad.zip';p.write_bytes(b'not zip')
   with self.assertRaises(zipfile.BadZipFile):inspect_archive(p)
 def test_train_only_parameters(self):
  x=np.array([[i+1]*len(FEATURES) for i in range(16)],float);y=np.array(CLASSES*2);m=fit(x,y);np.testing.assert_allclose(m['means'][0],np.log1p(x[[0,8]]).mean(0))
class ApiTests(unittest.TestCase):
 def get(self,path):
  return json.load(urllib.request.urlopen('http://127.0.0.1:8765'+path))
 def test_health_and_safe_rows(self):
  self.assertTrue(self.get('/api/health')['model_artifact']);r=self.get('/api/rows')['rows'];self.assertEqual(len(r),20);self.assertNotIn('client_ip',r[0])
 def test_inference_and_event(self):
  d=pd.read_csv(ROOT/'artifacts/flows.csv').head(3);req=urllib.request.Request('http://127.0.0.1:8765/api/predict',d.to_csv(index=False).encode(),headers={'Content-Type':'text/csv'});res=json.load(urllib.request.urlopen(req));self.assertEqual(res['rows'],3);self.assertEqual(sum(res['counts'].values()),3);self.assertTrue(self.get('/api/events'))
 def test_invalid_upload(self):
  req=urllib.request.Request('http://127.0.0.1:8765/api/predict',b'x\n1')
  with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
  self.assertEqual(e.exception.code,400)
 def test_invalid_explanation_index(self):
  with self.assertRaises(urllib.error.HTTPError) as e:self.get('/api/explain?row=-1')
  self.assertEqual(e.exception.code,400)
if __name__=='__main__':unittest.main(verbosity=2)
