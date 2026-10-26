"""Provision only immutable checkpoints chosen by the study's validation policy."""
import argparse,hashlib,json,shutil
from pathlib import Path
import numpy as np
from engine import CLASSES,FEATURES

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def provision(experiment,output):
 root=Path(experiment).resolve();out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
 report=json.loads((root/'report.json').read_text(encoding='utf-8'));protocol='unseen_site';seed=report['configuration']['seeds'][0];selected=report['selections'][protocol]['selected_method']
 if selected!='central_mlp':raise ValueError('This release supports only the validation-selected MLP family.')
 pre=root/protocol/'preprocessing.npz';pre_dest=out/'unseen-v2-normalization.npz';shutil.copyfile(pre,pre_dest)
 # Training-only empirical feature ranges provide descriptive out-of-range warnings.
 lo=np.full(len(FEATURES),np.inf);hi=np.full(len(FEATURES),-np.inf)
 for site in report['protocols'][protocol]['training_sites']:
  with np.load(root/protocol/('client_'+site+'.npz'),allow_pickle=False) as z:lo=np.minimum(lo,z['x'].min(0));hi=np.maximum(hi,z['x'].max(0))
 models=[]
 for method in ['central_mlp','fedavg','fedprox']:
  run=next(r for r in report['runs'] if r['protocol']==protocol and r['seed']==seed and r['method']==method)
  src=root/run['artifact']
  if digest(src)!=run['artifact_sha256']:raise ValueError('Experiment model checksum does not match')
  mid=f'{method}-unseen-v2-s{seed}';dest=out/(mid+'.npz');shutil.copyfile(src,dest)
  family=[r for r in report['runs'] if r['protocol']==protocol and r['method']==method]
  models.append({'id':mid,'name':{'central_mlp':'Centralized MLP','fedavg':'Federated MLP · FedAvg','fedprox':'Federated MLP · FedProx'}[method],'method':method,'default':method==selected,'protocol':protocol,'seed':seed,'file':dest.name,'sha256':digest(dest),'preprocessing_file':pre_dest.name,'preprocessing_sha256':digest(pre_dest),'features':FEATURES,'classes':CLASSES,'validation':run['validation'],'test':run['test'],'family_test_mean':{k:float(np.mean([r['test'][k] for r in family])) for k in ['accuracy','macro_f1','false_positive_rate','false_negative_rate']},'dataset_sha256':report['dataset_sha256'],'source_sha256':report['source_sha256'],'feature_min':lo.tolist(),'feature_max':hi.tolist(),'architecture':[25,64,32,8],'score_type':'uncalibrated_softmax','selection':('Family selected by mean validation macro F1.' if method==selected else 'Alternative federated checkpoint; not the validation-selected default family.')+' Seed is the first fixed study seed, not chosen using test scores.','limitations':['Diagnostic reuse of a previously inspected single-run corpus.','No fresh external validation or hospital deployment.','Uncalibrated predictions; no automatic network action.']})
 manifest={'schema':1,'default':next(m['id'] for m in models if m['default']),'models':models}
 (out/'registry.json').write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf-8');return manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,default=Path('artifacts/research-v2-final'));p.add_argument('--output',type=Path,default=Path('modelstore'));a=p.parse_args();r=provision(a.experiment,a.output);print('Provisioned',len(r['models']),'checksum-verified research checkpoints. Default:',r['default'])
