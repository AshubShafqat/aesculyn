"""Inference from immutable experiment records; no pickle or arbitrary model paths."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from engine import FEATURES,CLASSES,validate_frame
from research.neural import load_model,scaled,probabilities
from research.classical import load_classical
from research.run import predict_classical

def infer(frame,experiment_dir,protocol='unseen_site',method=None,seed=None):
 root=Path(experiment_dir).resolve();report=json.loads((root/'report.json').read_text(encoding='utf-8'))
 if report.get('status')!='completed':raise ValueError('Experiment has not completed')
 if protocol not in report['protocols']:raise ValueError('Unknown experiment protocol')
 method=method or report['selections'][protocol]['selected_method'];seed=int(seed if seed is not None else report['configuration']['seeds'][0])
 matches=[r for r in report['runs'] if r['protocol']==protocol and r['method']==method and r['seed']==seed]
 if len(matches)!=1:raise ValueError('Unknown model, protocol, or seed combination')
 r=matches[0];path=(root/r['artifact']).resolve()
 if not path.is_relative_to(root):raise ValueError('Artifact is outside the experiment directory')
 import hashlib
 if hashlib.sha256(path.read_bytes()).hexdigest()!=r['artifact_sha256']:raise ValueError('Model artifact integrity check failed')
 x=validate_frame(frame)
 counters=[c for c in FEATURES if c not in ['mean_pkt','std_pkt','mean_iat','std_iat']]
 if any((frame[c].astype(float)%1!=0).any() for c in counters):raise ValueError('Packet and event counters must be integers')
 with np.load(root/protocol/'preprocessing.npz',allow_pickle=False) as z:
  if z['features'].tolist()!=FEATURES or z['classes'].tolist()!=CLASSES:raise ValueError('Preprocessing schema mismatch')
  a=scaled(x,z['mean'],z['scale'])
 if path.name.endswith('.json.gz'):p=predict_classical(method,load_classical(path),x if method=='gaussian_nb' else a)
 else:p=probabilities(load_model(path),a)
 predictions=np.array(CLASSES)[p.argmax(1)].tolist()
 return {'rows':len(frame),'protocol':protocol,'method':method,'seed':seed,'predictions':predictions,'counts':{c:predictions.count(c) for c in CLASSES},'uncalibrated_attack_scores':(1-p[:,0]).tolist(),'note':'Offline experimental model. Scores are uncalibrated; predictions are not confirmed incidents.'}
def main():
 a=argparse.ArgumentParser();a.add_argument('--input',required=True,type=Path);a.add_argument('--experiment',type=Path,default=Path('artifacts/research-v2-final'));a.add_argument('--protocol',default='unseen_site');a.add_argument('--method');a.add_argument('--seed',type=int);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
 if args.input.stat().st_size>5_000_000:raise ValueError('CSV limit is 5 MB')
 frame=pd.read_csv(args.input)
 if len(frame)>10000:raise ValueError('Batch limit is 10,000 rows')
 r=infer(frame,args.experiment,args.protocol,args.method,args.seed);pd.DataFrame({'row':range(r['rows']),'prediction':r['predictions'],'uncalibrated_attack_score':r['uncalibrated_attack_scores']}).to_csv(args.output,index=False);print(json.dumps({k:v for k,v in r.items() if k not in ['predictions','uncalibrated_attack_scores']}))
if __name__=='__main__':main()
