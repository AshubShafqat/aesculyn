"""One process per simulated site. Only model arrays, statistics and aggregates cross the pipe."""
import os,time,traceback
from pathlib import Path
import numpy as np
from .neural import seed_everything,network,restore,state_arrays,moments,scaled,train_epochs

def client_worker(conn,partition_path,seed):
 try:
  seed_everything(seed)
  with np.load(partition_path,allow_pickle=False) as p:x=p['x'];y=p['y'];site=str(p['site'])
  stats=moments(x);counts=np.bincount(y,minlength=8)
  conn.send({'kind':'ready','site':site,'pid':os.getpid(),'examples':len(y),'moments':stats,'class_counts':counts})
  model=network()
  while True:
   task=conn.recv()
   if task['kind']=='stop':break
   if task['kind']!='train':raise ValueError('Unknown client task')
   begin=time.perf_counter();restore(model,task['state']);a=scaled(x,task['mean'],task['scale'])
   info=train_epochs(model,a,y,task['weights'],task['epochs'],task['seed'],lr=task['lr'],mu=task['mu'],global_state=task['state'])
   state=state_arrays(model)
   conn.send({'kind':'update','site':site,'pid':os.getpid(),'examples':len(y),'state':state,'loss':info['loss'],'steps':info['steps'],'elapsed_seconds':time.perf_counter()-begin,'parameter_bytes':sum(v.nbytes for v in state.values())})
 except EOFError:pass
 except Exception as e:
  try:conn.send({'kind':'error','error':type(e).__name__+': '+str(e)})
  except (BrokenPipeError,EOFError):pass
 finally:conn.close()
