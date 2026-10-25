"""Integration checks against the completed private research artifacts."""
import hashlib,json,os,unittest,urllib.request,urllib.error
from pathlib import Path
import numpy as np
import pandas as pd
from engine import ROOT,CLASSES
from research_predict import infer
from research.run import score
from research.neural import load_model,scaled,probabilities
BASE=os.environ.get('AESCULYN_TEST_URL','http://127.0.0.1:8767')
DIR=ROOT/'artifacts/research-v2-final'
@unittest.skipUnless((DIR/'report.json').exists(),'Completed private research artifacts required')
class ResearchIntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=json.loads((DIR/'report.json').read_text(encoding='utf-8'))
 def test_config_and_source_lock(self):
  lock=json.loads((DIR/'configuration.json').read_text(encoding='utf-8'))
  for name,digest in lock['source_file_sha256'].items():
   p=ROOT/'engine.py' if name=='engine.py' else ROOT/'research'/name;self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),digest,name)
  self.assertTrue((DIR/'selection_lock.json').exists())
 def test_model_artifact_hashes(self):
  self.assertEqual(len(self.r['runs']),51)
  for r in self.r['runs']:self.assertEqual(hashlib.sha256((DIR/r['artifact']).read_bytes()).hexdigest(),r['artifact_sha256'])
 def test_selection_uses_validation_only(self):
  for protocol,selection in self.r['selections'].items():
   means=selection['mean_validation_macro_f1'];self.assertEqual(selection['selected_method'],max(means,key=means.get))
 def test_actual_federated_rounds(self):
  runs=[v for v in self.r['federated_runs'].values() if v['strategy']!='local_only'];self.assertEqual(len(runs),12);self.assertEqual(sum(len(r['history']) for r in runs),240)
  for r in runs:
   self.assertEqual(len(r['history']),20);self.assertGreater(len(set(c['process_id'] for c in r['clients'])),1)
   for row in r['history']:self.assertEqual(row['aggregation_examples'],sum(c['examples'] for c in r['clients']));self.assertGreater(sum(c['optimizer_steps'] for c in row['clients']),0)
 def test_saved_predictions_reproduce_metrics(self):
  from engine import metrics
  for r in self.r['runs']:
   d=pd.read_csv((DIR/r['artifact']).with_suffix('.test_predictions.csv'));m=metrics(d.actual.to_numpy(),d.prediction.to_numpy());self.assertEqual(m['confusion_matrix'],r['test']['confusion_matrix']);self.assertEqual(m['macro_f1'],r['test']['macro_f1'])
 def test_research_inference_and_column_order(self):
  d=pd.read_csv(ROOT/'artifacts/flows.csv').head(3);a=infer(d,DIR);b=infer(d[d.columns[::-1]],DIR);self.assertEqual(a['predictions'],b['predictions']);self.assertEqual(a['method'],'central_mlp');self.assertEqual(a['rows'],3)
  with self.assertRaises(ValueError):infer(d,DIR,method='../escape')
 def test_public_export_has_no_private_artifacts(self):
  text=(ROOT/'public/research.json').read_text(encoding='utf-8');self.assertNotIn('client_ip',json.dumps(json.loads(text)['results']));self.assertNotIn('artifact_sha256',text);self.assertNotIn('process_id',text);self.assertNotIn('C:\\Users',text)
 def test_research_api(self):
  data=json.load(urllib.request.urlopen(BASE+'/api/research'));self.assertEqual(data['status'],'completed');d=pd.read_csv(ROOT/'artifacts/flows.csv').head(2);req=urllib.request.Request(BASE+'/api/research/predict?protocol=unseen_site&method=fedavg&seed=17',d.to_csv(index=False).encode(),headers={'Content-Type':'text/csv'});r=json.load(urllib.request.urlopen(req));self.assertEqual(r['rows'],2);self.assertEqual(r['method'],'fedavg')
if __name__=='__main__':unittest.main(verbosity=2)
