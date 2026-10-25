"""Small NumPy MLP with analytic backpropagation, SGD, and FedProx.

The same implementation, normalization, initialization and loss serve centralized,
local-only, FedAvg and FedProx experiments. Gradient and aggregation tests are provided.
"""
import random
import numpy as np
from threadpoolctl import threadpool_limits
from engine import FEATURES,CLASSES
_THREAD_LIMIT=None

def seed_everything(seed):
 global _THREAD_LIMIT
 random.seed(seed);np.random.seed(seed)
 if _THREAD_LIMIT is None:_THREAD_LIMIT=threadpool_limits(limits=1)

def network():
 dims=[len(FEATURES),64,32,len(CLASSES)]
 return {'w'+str(i):np.random.normal(0,np.sqrt(2/a),(a,b)).astype(np.float64) for i,(a,b) in enumerate(zip(dims,dims[1:]))}|{'b'+str(i):np.zeros(b,np.float64) for i,b in enumerate(dims[1:])}
def state_arrays(model):return {k:v.copy() for k,v in model.items()}
def restore(model,state):
 if set(model)!=set(state) or any(model[k].shape!=np.asarray(state[k]).shape for k in model):raise ValueError('Network state shape mismatch')
 for k in model:model[k]=np.asarray(state[k],dtype=np.float64).copy()
def aggregate(states,counts):
 if not states or len(states)!=len(counts) or any(n<=0 for n in counts):raise ValueError('Invalid client counts')
 keys=set(states[0]);total=sum(counts)
 if any(set(s)!=keys for s in states):raise ValueError('Client state keys disagree')
 out={}
 for k in states[0]:
  if any(s[k].shape!=states[0][k].shape or not np.isfinite(s[k]).all() for s in states):raise ValueError('Invalid client arrays')
  out[k]=sum(s[k].astype(np.float64)*(n/total) for s,n in zip(states,counts))
 return out

def moments(x):
 a=np.log1p(x).astype(np.float64);return {'n':len(a),'sum':a.sum(0),'sum_sq':(a*a).sum(0)}
def merge_moments(stats):
 n=sum(s['n'] for s in stats)
 if n<=0:raise ValueError('Empty normalization statistics')
 mean=sum(s['sum'] for s in stats)/n;var=np.maximum(sum(s['sum_sq'] for s in stats)/n-mean*mean,0);scale=np.sqrt(var);scale[scale<1e-8]=1
 return mean,scale
def scaled(x,mean,scale):return (np.log1p(x)-mean)/scale
def class_weights(counts):
 c=np.asarray(counts,float)
 if (c<=0).any():raise ValueError('Global training class missing')
 w=1/np.sqrt(c);return w/w.mean()
def forward(model,x):
 z1=x@model['w0']+model['b0'];a1=np.maximum(z1,0);z2=a1@model['w1']+model['b1'];a2=np.maximum(z2,0);z3=a2@model['w2']+model['b2'];logits=z3-z3.max(1,keepdims=True);exp=np.exp(logits);p=exp/exp.sum(1,keepdims=True)
 return p,(x,z1,a1,z2,a2,logits)
def loss_grad(model,x,y,weights,mu=0.,anchor=None):
 p,(x,z1,a1,z2,a2,logits)=forward(model,x);sample_weights=np.asarray(weights)[y];denom=sample_weights.sum();rows=np.arange(len(y))
 logp=logits-np.log(np.exp(logits).sum(1,keepdims=True));loss=float(-(sample_weights*logp[rows,y]).sum()/denom)
 dz=p.copy();dz[rows,y]-=1;dz*=sample_weights[:,None]/denom
 grad={'w2':a2.T@dz,'b2':dz.sum(0)};d2=(dz@model['w2'].T)*(z2>0);grad['w1']=a1.T@d2;grad['b1']=d2.sum(0);d1=(d2@model['w1'].T)*(z1>0);grad['w0']=x.T@d1;grad['b0']=d1.sum(0)
 if mu:
  if anchor is None:raise ValueError('FedProx needs a global anchor')
  for k in model:delta=model[k]-anchor[k];loss+=mu/2*float((delta*delta).sum());grad[k]+=mu*delta
 return loss,grad
def train_epochs(model,x,y,weights,epochs,seed,lr=.03,batch_size=256,mu=0.,global_state=None):
 if mu<0 or epochs<1 or len(x)!=len(y) or len(y)==0:raise ValueError('Invalid training settings')
 rng=np.random.default_rng(seed);velocity={k:np.zeros_like(v) for k,v in model.items()};anchor=state_arrays(model) if global_state is None else global_state;steps=0
 for _ in range(epochs):
  order=rng.permutation(len(y));total=0.
  for start in range(0,len(order),batch_size):
   idx=order[start:start+batch_size];loss,grad=loss_grad(model,x[idx],y[idx],weights,mu,anchor)
   if not np.isfinite(loss) or any(not np.isfinite(g).all() for g in grad.values()):raise ValueError('Nonfinite neural training')
   for k in model:velocity[k]=.9*velocity[k]+grad[k];model[k]-=lr*velocity[k]
   total+=loss*len(idx);steps+=1
 return {'loss':total/len(y),'steps':steps,'epochs':epochs}
def probabilities(model,x):return forward(model,x)[0]
def save_model(path,model):np.savez_compressed(path,**model)
def load_model(path):
 with np.load(path,allow_pickle=False) as z:state={k:z[k] for k in z.files}
 model=network();restore(model,state);return model
