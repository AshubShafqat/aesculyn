"""Correctness checks for gradients, isolation, aggregation, and protocol boundaries."""
import tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from engine import FEATURES,CLASSES
from research.data import numeric_digest,partition
from research.neural import *
from research.run import score,run_federated,CONFIG
from research.classical import binary_auc,average_precision,forest_fit,forest_prob,logistic_fit,softmax,weighted_gini,best_split

class ResearchTests(unittest.TestCase):
 def setUp(self):seed_everything(4)
 def test_fedavg_sample_weighted(self):
  result=aggregate([{'w':np.array([1.,3.])},{'w':np.array([5.,7.])}],[1,3]);np.testing.assert_allclose(result['w'],[4.,6.])
 def test_aggregation_rejects_bad_updates(self):
  for states,counts in [([],[]),([{'w':np.array([np.nan])}],[1]),([{'w':np.zeros(2)},{'w':np.zeros(3)}],[1,1]),([{'w':np.zeros(1)}],[0])]:
   with self.assertRaises(ValueError):aggregate(states,counts)
 def test_gradient_finite_difference_with_fedprox(self):
  m=network();anchor={k:v+.02 for k,v in m.items()};x=np.random.normal(size=(5,len(FEATURES)));y=np.arange(5);weights=np.linspace(.7,1.3,8);loss,g=loss_grad(m,x,y,weights,.1,anchor)
  for k in m:
   for index in [0,m[k].size//2,m[k].size-1]:
    a=m[k].flat[index];eps=1e-5;m[k].flat[index]=a+eps;plus=loss_grad(m,x,y,weights,.1,anchor)[0];m[k].flat[index]=a-eps;minus=loss_grad(m,x,y,weights,.1,anchor)[0];m[k].flat[index]=a
    self.assertAlmostEqual(g[k].flat[index],(plus-minus)/(2*eps),places=5)
 def test_proximal_gradient(self):
  m=network();anchor={k:v+.1 for k,v in m.items()};x=np.random.normal(size=(4,25));y=np.arange(4);a,ga=loss_grad(m,x,y,np.ones(8));b,gb=loss_grad(m,x,y,np.ones(8),.2,anchor)
  self.assertGreater(b,a)
  for k in m:np.testing.assert_allclose(gb[k]-ga[k],.2*(m[k]-anchor[k]),atol=1e-10)
 def test_mu_zero_matches_unregularized(self):
  m=network();x=np.random.normal(size=(4,25));y=np.arange(4);a,ga=loss_grad(m,x,y,np.ones(8));b,gb=loss_grad(m,x,y,np.ones(8),0,state_arrays(m));self.assertEqual(a,b)
  for k in ga:np.testing.assert_array_equal(ga[k],gb[k])
 def test_training_decreases_loss(self):
  m=network();x=np.random.normal(size=(80,25));y=np.arange(80)%8;a=loss_grad(m,x,y,np.ones(8))[0];train_epochs(m,x,y,np.ones(8),30,7,lr=.04);self.assertLess(loss_grad(m,x,y,np.ones(8))[0],a)
 def test_moments_equal_pooled_train(self):
  a=np.arange(250).reshape(10,25);b=np.arange(250,500).reshape(10,25);mean,scale=merge_moments([moments(a),moments(b)]);x=np.log1p(np.concatenate([a,b]));np.testing.assert_allclose(mean,x.mean(0));np.testing.assert_allclose(scale,x.std(0))
 def test_checkpoint_roundtrip(self):
  m=network();x=np.ones((2,25))
  with tempfile.TemporaryDirectory() as td:
   f=Path(td)/'m.npz';save_model(f,m);np.testing.assert_array_equal(probabilities(m,x),probabilities(load_model(f),x))
 def test_feature_label_alignment_metrics(self):
  y=np.array([0,1,2]);p=np.eye(8)[[0,0,2]];m=score(y,p);self.assertEqual(m['false_negatives'],1);self.assertEqual(m['false_positives'],0);self.assertAlmostEqual(m['accuracy'],2/3)
 def test_test_labels_cannot_change_training_membership(self):
  d=self.frame();h=numeric_digest(d);a,_=partition(d,h,set(),'unseen_site');changed=d.copy();changed.loc[changed.split_time.eq('test'),'label_class']='benign';b,_=partition(changed,h,set(h[-3:]),'unseen_site');np.testing.assert_array_equal(a['train'],b['train'])
 def test_rejects_invalid_probabilities(self):
  with self.assertRaises(ValueError):score(np.array([0]),np.full((1,8),.5))
 def test_auc_ties_and_order(self):
  self.assertEqual(binary_auc([0,1],[.5,.5]),.5);self.assertEqual(binary_auc([0,1],[0,1]),1.);self.assertEqual(binary_auc([0,1],[1,0]),0.)
 def test_average_precision_ties(self):
  self.assertEqual(average_precision([0,1],[.5,.5]),.5);self.assertEqual(average_precision([0,1],[0,1]),1.)
 def test_cart_split_matches_separation(self):
  x=np.array([[0],[0],[1],[1]],np.uint8);y=np.array([0,0,1,1]);split=best_split(x,y,np.ones(4),[0],1,2);self.assertEqual(split[1:],(0,0));self.assertEqual(split[0],2.)
 def test_forest_predicts_multiclass_clusters(self):
  y=np.repeat(np.arange(8),12);x=np.repeat(y[:,None],25,axis=1).astype(float);m=forest_fit(x,y,4,n_estimators=8,max_depth=8,min_leaf=1);p=forest_prob(m,x);self.assertGreater((p.argmax(1)==y).mean(),.95);np.testing.assert_allclose(p.sum(1),1)
 def test_logistic_probabilities_and_learning(self):
  y=np.repeat(np.arange(8),8);x=np.eye(8)[y];m=logistic_fit(x,y,4,epochs=35);p=softmax(x@np.array(m['w'])+m['b']);self.assertGreater((p.argmax(1)==y).mean(),.95);np.testing.assert_allclose(p.sum(1),1)
 def frame(self):
  rows=[]
  for i,s in enumerate(['A','B','C']):
   for j,part in enumerate(['train','val','test']):
    for k,c in enumerate(CLASSES):rows.append({**{f:1+i*100+j*10+k for f in FEATURES},'site':s,'split_time':part,'window_start':j*1000+k*2,'label_class':c})
  return pd.DataFrame(rows)
 def test_unseen_site_isolation(self):
  d=self.frame();h=numeric_digest(d);m,meta=partition(d,h,set(),'unseen_site');self.assertEqual(set(d.loc[m['train'],'site']),{'A','B'});self.assertEqual(set(d.loc[m['test'],'site']),{'C'});self.assertEqual(meta['feature_overlap']['train_test'],0)
 def test_duplicate_removal_and_temporal_order(self):
  d=self.frame();d.loc[d.index[-1],FEATURES]=d.loc[0,FEATURES].values;h=numeric_digest(d);m,meta=partition(d,h,set(),'temporal_federation');self.assertFalse(m['test'][-1]);self.assertLess(d.loc[m['train'],'window_start'].max()+60,d.loc[m['val'],'window_start'].min());self.assertFalse(set(h[m['train']])&set(h[m['test']]))
 def test_separate_process_clients_and_round_log(self):
  original=CONFIG['rounds'];CONFIG['rounds']=1
  try:
   with tempfile.TemporaryDirectory() as td:
    root=Path(td);paths=[];stats=[]
    for i,site in enumerate(['A','B']):
     x=np.abs(np.random.normal(size=(16,25)));y=np.arange(16)%8;f=root/(site+'.npz');np.savez(f,x=x,y=y,site=np.array(site));paths.append(f);stats.append(moments(x))
    mean,scale=merge_moments(stats);detail=run_federated(paths,mean,scale,np.ones(8),scaled(x,mean,scale),y,7,'fedprox',root/'fed');self.assertEqual(len(set(c['process_id'] for c in detail['clients'])),2);self.assertEqual(detail['history'][0]['aggregation_examples'],32);self.assertTrue((root/'fed/best.npz').exists());self.assertEqual(detail['mu'],.01)
  finally:CONFIG['rounds']=original
if __name__=='__main__':unittest.main(verbosity=2)
