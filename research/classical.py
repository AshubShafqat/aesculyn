"""Portable reference classifiers using NumPy only.

Histogram random forest: bootstrap CART, random feature subsets, weighted Gini,
training-only quantile bins, weighted leaf class frequencies, mean probabilities.
These are reference implementations, not scikit-learn estimators.
"""
import gzip,json
import numpy as np
from .neural import seed_everything


def softmax(a):
 z=a-np.max(a,axis=1,keepdims=True);e=np.exp(z);return e/e.sum(1,keepdims=True)
def balanced_weights(y):
 counts=np.bincount(y,minlength=8)
 if (counts==0).any():raise ValueError('A training class is missing')
 return len(y)/(8*counts)
def logistic_fit(x,y,seed,epochs=70,lr=.025,l2=.001):
 seed_everything(seed);rng=np.random.default_rng(seed);w=np.zeros((x.shape[1],8));b=np.zeros(8);vw=np.zeros_like(w);vb=b.copy();cw=balanced_weights(y)
 for epoch in range(epochs):
  order=rng.permutation(len(y));rate=lr/(1+epoch/40)
  for start in range(0,len(y),256):
   ix=order[start:start+256];p=softmax(x[ix]@w+b);p[np.arange(len(ix)),y[ix]]-=1;p*=cw[y[ix],None]/cw[y[ix]].sum();gw=x[ix].T@p+l2*w;gb=p.sum(0);vw=.9*vw+gw;vb=.9*vb+gb;w-=rate*vw;b-=rate*vb
 return {'kind':'logistic_regression','w':w.tolist(),'b':b.tolist(),'epochs':epochs,'l2':l2}

def bins_fit(x,bins=24):
 cuts=[np.unique(np.quantile(x[:,i],np.linspace(0,1,bins+1)[1:-1])).tolist() for i in range(x.shape[1])]
 return cuts

def bins_transform(x,cuts):return np.column_stack([np.searchsorted(c,x[:,i],side='left') for i,c in enumerate(cuts)]).astype(np.uint8)
def weighted_gini(counts):
 a=np.asarray(counts,float);s=a.sum(axis=-1);return s-np.sum(a*a,axis=-1)/np.maximum(s,1e-15)

def best_split(x,y,weights,features,min_leaf,bins):
 best=None;parent=np.bincount(y,weights=weights,minlength=8);impurity=weighted_gini(parent)
 for f in features:
  codes=x[:,f].astype(int);hist=np.bincount(codes*8+y,weights=weights,minlength=bins*8).reshape(bins,8);raw=np.bincount(codes,minlength=bins);left=np.cumsum(hist,axis=0)[:-1];right=parent-left;ln=np.cumsum(raw)[:-1];rn=len(y)-ln;valid=(ln>=min_leaf)&(rn>=min_leaf);gain=impurity-weighted_gini(left)-weighted_gini(right);gain[~valid]=-np.inf;t=int(np.argmax(gain))
  if gain[t]>1e-10 and (best is None or gain[t]>best[0]):best=(float(gain[t]),int(f),t)
 return best

def forest_fit(x,y,seed,n_estimators=64,max_depth=11,min_leaf=4,max_bins=24):
 seed_everything(seed);rng=np.random.default_rng(seed);cuts=bins_fit(x,max_bins);binned=bins_transform(x,cuts);cw=balanced_weights(y);trees=[];features_per_node=max(1,int(np.sqrt(x.shape[1])))
 def grow(ix,depth):
  counts=np.bincount(y[ix],weights=cw[y[ix]],minlength=8);prob=(counts/counts.sum()).tolist()
  if depth>=max_depth or len(ix)<2*min_leaf or np.count_nonzero(counts)<2:return {'p':prob}
  fs=rng.choice(x.shape[1],size=features_per_node,replace=False);split=best_split(binned[ix],y[ix],cw[y[ix]],fs,min_leaf,max_bins)
  if split is None:return {'p':prob}
  _,f,t=split;left=binned[ix,f]<=t
  return {'f':f,'t':t,'l':grow(ix[left],depth+1),'r':grow(ix[~left],depth+1)}
 for _ in range(n_estimators):trees.append(grow(rng.integers(0,len(y),size=len(y)),0))
 return {'kind':'random_forest','cuts':cuts,'trees':trees,'n_estimators':n_estimators,'max_depth':max_depth,'min_leaf':min_leaf,'max_bins':max_bins}

def forest_prob(model,x):
 a=bins_transform(x,model['cuts']);out=np.zeros((len(x),8))
 def visit(node,ix):
  if len(ix)==0:return
  if 'p' in node:out[ix]+=np.array(node['p']);return
  mask=a[ix,node['f']]<=node['t'];visit(node['l'],ix[mask]);visit(node['r'],ix[~mask])
 for tree in model['trees']:visit(tree,np.arange(len(x)))
 return out/len(model['trees'])
def binary_auc(y,scores):
 y=np.asarray(y,bool);scores=np.asarray(scores);pos=int(y.sum());neg=len(y)-pos
 if not pos or not neg:return None
 order=np.argsort(scores,kind='stable');rank=np.empty(len(y),float);i=0
 while i<len(y):
  j=i+1
  while j<len(y) and scores[order[j]]==scores[order[i]]:j+=1
  rank[order[i:j]]=(i+1+j)/2;i=j
 return float((rank[y].sum()-pos*(pos+1)/2)/(pos*neg))
def average_precision(y,scores):
 y=np.asarray(y,bool)
 if not y.any():return None
 order=np.argsort(-np.asarray(scores),kind='stable');s=np.asarray(scores)[order];a=y[order];tp=np.cumsum(a);ends=np.r_[np.flatnonzero(s[:-1]!=s[1:]),len(s)-1];recall=tp[ends]/a.sum();precision=tp[ends]/(ends+1)
 return float(np.sum(np.diff(np.r_[0,recall])*precision))
def save_classical(path,model):
 with gzip.open(path,'wt',encoding='utf-8') as f:json.dump(model,f,separators=(',',':'),allow_nan=False)
def load_classical(path):
 with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)
