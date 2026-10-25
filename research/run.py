"""Run locked-protocol model comparisons and real process-isolated FedAvg/FedProx training.

Usage: python -m research.run --archive DATA.zip --output artifacts/research
No private rows, client partition files or checkpoints are copied to public/.
"""
import argparse,hashlib,json,multiprocessing as mp,os,platform,time
from pathlib import Path
import numpy as np
import pandas as pd
from engine import FEATURES,CLASSES,fit as nb_fit,terms as nb_terms,metrics,validate_frame
from .data import audit_archive,partition,PROTOCOLS,write_json
from .neural import seed_everything,network,state_arrays,restore,aggregate,moments,merge_moments,scaled,class_weights,train_epochs,probabilities,save_model,load_model
from .client import client_worker
from .classical import softmax,logistic_fit,forest_fit,forest_prob,binary_auc,average_precision,save_classical,load_classical

CONFIG={'seeds':[17,29,43],'purge_gap_seconds':60,'rounds':20,'local_epochs':2,'lr':.03,'batch_size':256,'fedprox_mu':.01,'class_weighting':'inverse square root of aggregate training counts for MLP; balanced for tree/logistic candidates','mlp_hidden':[64,32],'selection':'highest mean validation macro-F1 across seeds, never test scores','checkpoint_selection':'highest validation macro-F1; earlier checkpoint wins ties','candidates':{'gaussian_nb':{'log1p':True,'uniform_priors':True,'variance_smoothing':.001},'logistic_regression':{'epochs':70,'lr':.025,'l2':.001,'class_weight':'balanced'},'random_forest':{'n_estimators':64,'max_depth':11,'min_leaf':4,'max_bins':24,'class_weight':'balanced','max_features':'sqrt'},'central_mlp':{'backend':'NumPy analytic backpropagation','normalization':'log1p, train-only aggregate mean/std','optimizer':'SGD, momentum .9, reset per 2-epoch block'}}}

def score(y,prob):
 prob=np.asarray(prob,float)
 if prob.shape!=(len(y),len(CLASSES)) or not np.isfinite(prob).all() or (prob<0).any() or not np.allclose(prob.sum(1),1):raise ValueError('Invalid prediction probability matrix')
 pred=prob.argmax(1);m=metrics(np.array(CLASSES)[y],np.array(CLASSES)[pred]);binary=y!=0;attack=1-prob[:,0]
 m['binary_roc_auc']=binary_auc(binary,attack) if len(np.unique(binary))==2 else None
 m['binary_average_precision']=average_precision(binary,attack) if binary.any() else None
 m['binary_attack_recall']=1-m['false_negative_rate'];m['uncalibrated_scores']=True
 return m

def receive(conn,timeout=180):
 if not conn.poll(timeout):raise TimeoutError('Federated client exceeded timeout')
 result=conn.recv()
 if result.get('kind')=='error':raise RuntimeError(result['error'])
 return result

def fit_classical(name,x,y,seed):
 if name=='gaussian_nb':
  m=nb_fit(x,np.array(CLASSES)[y]);return {'kind':name,**{k:v.tolist() for k,v in m.items()}}
 if name=='logistic_regression':return logistic_fit(x,y,seed)
 if name=='random_forest':return forest_fit(x,y,seed)
 raise ValueError('Unknown model')

def predict_classical(name,model,x):
 if name=='gaussian_nb':
  m={k:np.asarray(model[k]) for k in ['means','variances','prior']};return softmax(nb_terms(x,m).sum(2)+np.log(m['prior']))
 if name=='logistic_regression':return softmax(x@np.asarray(model['w'])+np.asarray(model['b']))
 if name=='random_forest':return forest_prob(model,x)
 raise ValueError('Unknown model')

def train_central(x,y,xv,yv,weights,seed,out):
 seed_everything(seed);model=network();best=-1.;history=[]
 for r in range(1,CONFIG['rounds']+1):
  info=train_epochs(model,x,y,weights,CONFIG['local_epochs'],seed+r,lr=CONFIG['lr']);m=score(yv,probabilities(model,xv));history.append({'round':r,'loss':info['loss'],'validation_macro_f1':m['macro_f1']})
  if m['macro_f1']>best:best=m['macro_f1'];save_model(out,model);best_round=r
 return load_model(out),history,best_round

def run_federated(partition_paths,mean,scale,weights,xv,yv,seed,strategy,folder):
 ctx=mp.get_context('spawn');processes=[];pipes=[];ready=[];mu=CONFIG['fedprox_mu'] if strategy=='fedprox' else 0.
 folder.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
 try:
  for i,path in enumerate(partition_paths):
   parent,child=ctx.Pipe();proc=ctx.Process(target=client_worker,args=(child,str(path),seed+i),daemon=True);proc.start();child.close();pipes.append(parent);processes.append(proc)
  ready=[receive(c) for c in pipes]
  if len(set(r['site'] for r in ready))!=len(ready) or len(set(r['pid'] for r in ready))!=len(ready):raise AssertionError('Clients not isolated')
  stats=[r['moments'] for r in ready];fm,fs=merge_moments(stats)
  if not np.allclose(fm,mean) or not np.allclose(fs,scale):raise AssertionError('Federated train-only normalization disagreement')
  counts=sum(r['class_counts'] for r in ready)
  if not np.allclose(class_weights(counts),weights):raise AssertionError('Training-only class weight disagreement')
  seed_everything(seed);model=network();initial=state_arrays(model);global_state=initial;best=-1.;history=[];local_states=[initial for _ in pipes]
  local_best=[-1.]*len(pipes);local_best_round=[0]*len(pipes)
  for r in range(1,CONFIG['rounds']+1):
   for i,c in enumerate(pipes):c.send({'kind':'train','state':local_states[i] if strategy=='local_only' else global_state,'mean':mean,'scale':scale,'weights':weights,'epochs':CONFIG['local_epochs'],'seed':seed+r*100+i,'lr':CONFIG['lr'],'mu':mu})
   updates=[receive(c) for c in pipes]
   if any(u['site']!=ready[i]['site'] or u['examples']!=ready[i]['examples'] for i,u in enumerate(updates)):raise AssertionError('Client identity/count mismatch')
   row={'round':r,'strategy':strategy,'mu':mu,'clients':[{'site':u['site'],'process_id':u['pid'],'examples':u['examples'],'local_loss':u['loss'],'optimizer_steps':u['steps'],'parameter_bytes':u['parameter_bytes'],'local_training_seconds':u['elapsed_seconds']} for u in updates]}
   if strategy=='local_only':
    local_states=[u['state'] for u in updates];scores=[]
    for i,u in enumerate(updates):
     restore(model,u['state']);metric=score(yv,probabilities(model,xv));scores.append(metric['macro_f1'])
     if metric['macro_f1']>local_best[i]:local_best[i]=metric['macro_f1'];local_best_round[i]=r;save_model(folder/('local_'+u['site']+'.npz'),model)
    row['validation_macro_f1_by_site']={u['site']:float(v) for u,v in zip(updates,scores)}
   else:
    global_state=aggregate([u['state'] for u in updates],[u['examples'] for u in updates]);restore(model,global_state);metric=score(yv,probabilities(model,xv));row['validation_macro_f1']=metric['macro_f1'];row['aggregation_examples']=sum(u['examples'] for u in updates)
    if metric['macro_f1']>best:best=metric['macro_f1'];best_round=r;save_model(folder/'best.npz',model)
   history.append(row)
   with (folder/'rounds.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
  info={'strategy':strategy,'clients':[{'site':r['site'],'examples':r['examples'],'process_id':r['pid']} for r in ready],'rounds':CONFIG['rounds'],'mu':mu,'elapsed_seconds':time.perf_counter()-start,'history':history,'transport':'multiprocessing.Pipe on one host; model arrays and aggregate statistics only during training','normalization':'training-only client n/sum/sum_sq aggregated without secure aggregation','privacy':'No differential privacy or cryptographic secure aggregation; simulation administrator can access all partition files.'}
  if strategy=='local_only':info['selected_rounds_by_site']={r['site']:n for r,n in zip(ready,local_best_round)}
  else:info['selected_round']=best_round
  write_json(folder/'training.json',info)
  return info
 finally:
  for c in pipes:
   try:c.send({'kind':'stop'})
   except (BrokenPipeError,EOFError,OSError):pass
  for p in processes:
   p.join(timeout=10)
   if p.is_alive():p.terminate();p.join(timeout=5)
  for c in pipes:c.close()

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path,default=Path('artifacts/research'));parser.add_argument('--seeds',type=int,nargs='+',default=CONFIG['seeds']);parser.add_argument('--rounds',type=int,default=CONFIG['rounds']);parser.add_argument('--protocols',nargs='+',choices=list(PROTOCOLS),default=list(PROTOCOLS));args=parser.parse_args()
 if args.rounds<1 or not args.seeds:raise ValueError('At least one round and seed required')
 CONFIG['seeds']=args.seeds;CONFIG['rounds']=args.rounds
 root=args.output.resolve()
 if root.exists() and any(root.iterdir()):raise ValueError('Output directory must be empty; existing experiments are never overwritten')
 root.mkdir(parents=True,exist_ok=True)
 versions={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'classical_backend':'NumPy reference implementations','neural_backend':'NumPy analytic backpropagation'}
 source_files=sorted(Path(__file__).parent.glob('*.py'))+[Path(__file__).parent.parent/'engine.py']
 source_hash=hashlib.sha256(b''.join(f.name.encode()+f.read_bytes() for f in source_files)).hexdigest()
 lock={'configuration':CONFIG,'protocols':args.protocols,'versions':versions,'source_sha256':source_hash,'source_file_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files},'stage':'configuration_locked_before_training','test_policy':'Previously inspected corpus, diagnostic holdouts. Test predictions evaluated only after all validation selection is frozen.'}
 write_json(root/'configuration.json',lock);print('Configuration locked',flush=True)
 df,hashes,conflicts,audit=audit_archive(args.archive);write_json(root/'data_audit.json',audit)
 x=validate_frame(df);y=np.array([CLASSES.index(c) for c in df.label_class]);records=[];protocol_info={};run_details={}
 for protocol in args.protocols:
  folder=root/protocol;folder.mkdir();masks,meta=partition(df,hashes,conflicts,protocol,CONFIG['purge_gap_seconds']);protocol_info[protocol]=meta;write_json(folder/'partitions.json',meta)
  xt,yt=x[masks['train']],y[masks['train']];xv,yv=x[masks['val']],y[masks['val']]
  stats=[];paths=[]
  for site in meta['training_sites']:
   mask=masks['train']&df.site.eq(site).to_numpy();path=folder/('client_'+site+'.npz');np.savez_compressed(path,x=x[mask],y=y[mask],site=np.array(site));paths.append(path);stats.append(moments(x[mask]))
  mean,scale=merge_moments(stats);weights=class_weights(np.bincount(yt,minlength=len(CLASSES)));np.savez(folder/'preprocessing.npz',mean=mean,scale=scale,weights=weights,features=np.array(FEATURES),classes=np.array(CLASSES))
  a=scaled(xt,mean,scale);av=scaled(xv,mean,scale)
  for seed in args.seeds:
   seedfolder=folder/str(seed);seedfolder.mkdir()
   for name in ['gaussian_nb','logistic_regression','random_forest']:
    print(protocol,seed,name,flush=True);begin=time.perf_counter();xx=xt if name=='gaussian_nb' else a;vx=xv if name=='gaussian_nb' else av
    model=fit_classical(name,xx,yt,seed);vp=predict_classical(name,model,vx);path=seedfolder/(name+'.json.gz');save_classical(path,model)
    records.append({'protocol':protocol,'seed':seed,'method':name,'validation':score(yv,vp),'training_seconds':time.perf_counter()-begin,'artifact':str(path.relative_to(root))})
   print(protocol,seed,'central_mlp',flush=True);begin=time.perf_counter();path=seedfolder/'central_mlp.npz';model,history,best_round=train_central(a,yt,av,yv,weights,seed,path)
   records.append({'protocol':protocol,'seed':seed,'method':'central_mlp','validation':score(yv,probabilities(model,av)),'training_seconds':time.perf_counter()-begin,'selected_round':best_round,'artifact':str(path.relative_to(root))});write_json(seedfolder/'central_history.json',history)
   for strategy in ['local_only','fedavg','fedprox']:
    print(protocol,seed,strategy,flush=True);f=seedfolder/strategy;detail=run_federated(paths,mean,scale,weights,av,yv,seed,strategy,f);run_details[f'{protocol}/{seed}/{strategy}']=detail
    names=[('local_'+site,f/('local_'+site+'.npz')) for site in meta['training_sites']] if strategy=='local_only' else [(strategy,f/'best.npz')]
    for name,path in names:
     model=load_model(path);records.append({'protocol':protocol,'seed':seed,'method':name,'validation':score(yv,probabilities(model,av)),'training_seconds':detail['elapsed_seconds'],'selected_round':detail.get('selected_round',detail.get('selected_rounds_by_site',{}).get(name.removeprefix('local_'))),'artifact':str(path.relative_to(root))})
   write_json(root/'validation_progress.json',records)
 # Seal selections before loading the test partitions for prediction.
 selections={}
 for protocol in args.protocols:
  methods=sorted(set(r['method'] for r in records if r['protocol']==protocol));means={name:float(np.mean([r['validation']['macro_f1'] for r in records if r['protocol']==protocol and r['method']==name])) for name in methods}
  selections[protocol]={'mean_validation_macro_f1':means,'selected_method':max(means,key=means.get)}
 write_json(root/'selection_lock.json',{'selections':selections,'stage':'all_validation_selections_frozen_before_test_prediction'})
 print('All validation selections frozen. Evaluating diagnostic test partitions.',flush=True)
 for r in records:
  protocol=r['protocol'];masks,_=partition(df,hashes,conflicts,protocol,CONFIG['purge_gap_seconds']);testx=x[masks['test']];testy=y[masks['test']]
  with np.load(root/protocol/'preprocessing.npz',allow_pickle=False) as z:ax=scaled(testx,z['mean'],z['scale'])
  begin=time.perf_counter();path=root/r['artifact']
  if path.name.endswith('.json.gz'):model=load_classical(path);prob=predict_classical(r['method'],model,testx if r['method']=='gaussian_nb' else ax)
  else:model=load_model(path);prob=probabilities(model,ax)
  r['test']=score(testy,prob);r['inference_ms_per_1000']=float((time.perf_counter()-begin)*1e6/len(testy));r['artifact_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
  pd.DataFrame({'actual':np.array(CLASSES)[testy],'prediction':np.array(CLASSES)[prob.argmax(1)]}).to_csv(path.with_suffix('.test_predictions.csv'),index=False)
  # Simulated-client performance on each site's test subset, not raw-record exports.
  sites=df.loc[masks['test'],'site'].to_numpy();r['test_by_site']={s:score(testy[sites==s],prob[sites==s]) for s in sorted(set(sites))}
 report={'schema_version':1,'status':'completed','study':'Aesculyn v2 diagnostic model comparison and process-isolated federation','dataset_sha256':audit['dataset_sha256'],'configuration':CONFIG,'versions':versions,'source_sha256':source_hash,'source_file_sha256':lock['source_file_sha256'],'audit':audit,'protocols':protocol_info,'selections':selections,'runs':records,'federated_runs':run_details,'limitations':audit['limitations']+['Clients are real separate local processes, not independent hospitals or authenticated network services.','Training normalization moments and class counts are shared without secure aggregation.','No differential privacy, Byzantine defense, live network capture, clinical validation, or enforcement.','All final test metrics are diagnostic reuse of this corpus; new independent capture data is required.','Softmax and tree probabilities are uncalibrated and are not confidence guarantees.','The baseline deployed inference endpoint remains unchanged; research checkpoints require the separate research inference interface.','Model checkpoint selection uses validation; test results do not choose the winner.','Conflicting feature-label groups are reported, not used to curate training. Duplicate representatives use target-independent partition/index precedence.','Histogram gradient boosting and third-party ML backends were not run because of disk and native-module application-control constraints.']}
 write_json(root/'report.json',report);print('Completed:',root/'report.json',flush=True)
if __name__=='__main__':main()
