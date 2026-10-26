"""Read-only registry, input schema checks and approximate integrated gradients."""
import hashlib,io,json
from pathlib import Path
import numpy as np
import pandas as pd
from engine import FEATURES,CLASSES,validate_frame
from research.neural import load_model,scaled,probabilities,seed_everything

COUNTERS=[c for c in FEATURES if c not in ['mean_pkt','std_pkt','mean_iat','std_iat']]

def parse_csv(raw):
 if not raw or len(raw)>5_000_000:raise ValueError('Upload a nonempty CSV no larger than 5 MB.')
 try:
  # Check headers before pandas can silently mangle duplicate names.
  import csv
  text=raw.decode('utf-8-sig');head=next(csv.reader(io.StringIO(text)))
  if len(head)!=len(set(head)):raise ValueError('CSV contains duplicate column names.')
  d=pd.read_csv(io.StringIO(text),nrows=10001)
 except (UnicodeDecodeError,StopIteration,pd.errors.ParserError,pd.errors.EmptyDataError):raise ValueError('Upload a valid UTF-8 CSV with a header row.')
 if len(d)>10000:raise ValueError('Maximum batch size is 10,000 rows.')
 x=validate_frame(d)
 if any((d[c].astype(float)%1!=0).any() for c in COUNTERS):raise ValueError('Packet and event counters must be integers.')
 labels=None
 if 'label_class' in d:
  if d.label_class.isna().any() or not set(d.label_class).issubset(CLASSES):raise ValueError('Optional label_class must use the eight documented class labels.')
  labels=np.array([CLASSES.index(v) for v in d.label_class])
 return x,labels,{'rows':len(d),'input_columns':len(d.columns),'ignored_columns':len([c for c in d if c not in FEATURES+['label_class']]),'missing_values':0,'duplicate_feature_rows':int(pd.DataFrame(x).duplicated().sum())}

class Registry:
 def __init__(self,directory):
  self.root=Path(directory).resolve();self.models={};self.default=None;self.error=None
  try:
   manifest=json.loads((self.root/'registry.json').read_text(encoding='utf-8'));self.default=manifest['default']
   if manifest.get('schema')!=1:raise ValueError('Unsupported registry schema')
   seed_everything(17)
   for m in manifest['models']:
    if m['features']!=FEATURES or m['classes']!=CLASSES or m['id'] in self.models:raise ValueError('Registry schema mismatch')
    paths=[]
    for key,hashkey in [('file','sha256'),('preprocessing_file','preprocessing_sha256')]:
     path=(self.root/m[key]).resolve()
     if not path.is_relative_to(self.root) or hashlib.sha256(path.read_bytes()).hexdigest()!=m[hashkey]:raise ValueError('Model integrity validation failed')
     paths.append(path)
    with np.load(paths[1],allow_pickle=False) as z:
     if z['features'].tolist()!=FEATURES or z['classes'].tolist()!=CLASSES:raise ValueError('Normalization schema mismatch')
     mean=z['mean'].copy();scale=z['scale'].copy()
    if mean.shape!=(25,) or scale.shape!=(25,) or not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale<=0).any():raise ValueError('Invalid normalization artifact')
    model=load_model(paths[0])
    expected={'w0':(25,64),'b0':(64,),'w1':(64,32),'b1':(32,),'w2':(32,8),'b2':(8,)}
    if set(model)!=set(expected) or any(model[k].shape!=shape for k,shape in expected.items()):raise ValueError('Invalid model architecture')
    low=np.asarray(m['feature_min']);high=np.asarray(m['feature_max'])
    if low.shape!=(25,) or high.shape!=(25,) or not np.isfinite(low).all() or not np.isfinite(high).all() or (low<0).any() or (high<low).any():raise ValueError('Invalid training range metadata')
    for v in model.values():
     if not np.isfinite(v).all():raise ValueError('Nonfinite model parameters')
     v.flags.writeable=False
    self.models[m['id']]={'card':m,'model':model,'mean':mean,'scale':scale}
   if self.default not in self.models:raise ValueError('Default model unavailable')
  except Exception as e:self.models={};self.default=None;self.error='Model registry unavailable. Provision a valid model package before analysis.'
 def get(self,mid):
  if mid not in self.models:raise ValueError('Choose an available model version.')
  return self.models[mid]
 def cards(self):
  return [{k:v for k,v in m['card'].items() if k not in ['file','preprocessing_file','feature_min','feature_max']} for m in self.models.values()]
 def predict(self,mid,x):
  r=self.get(mid);a=scaled(x,r['mean'],r['scale']);p=probabilities(r['model'],a)
  if not np.isfinite(p).all():raise ValueError('Prediction produced invalid scores.')
  low=np.array(r['card']['feature_min']);high=np.array(r['card']['feature_max']);outside=(x<low)|(x>high)
  return p,outside
 def explain(self,mid,x):
  r=self.get(mid);a=scaled(np.asarray(x).reshape(1,-1),r['mean'],r['scale'])[0];model=r['model'];p=probabilities(model,a[None])[0];order=np.argsort(p);winner=int(order[-1]);reference=int(order[-2])
  def margin(z):
   h1=np.maximum(z@model['w0']+model['b0'],0);h2=np.maximum(h1@model['w1']+model['b1'],0);o=h2@model['w2']+model['b2'];return float(o[winner]-o[reference])
  delta=margin(a)-margin(np.zeros_like(a));attribution=None;residual=None
  for steps in [128,512,2048]:
   alpha=np.linspace(0,1,steps+1);points=alpha[:,None]*a;z1=points@model['w0']+model['b0'];h1=np.maximum(z1,0);z2=h1@model['w1']+model['b1'];v=model['w2'][:,winner]-model['w2'][:,reference];g2=(z2>0)*v;g1=(g2@model['w1'].T)*(z1>0);grad=g1@model['w0'].T;attribution=a*(grad[0]/2+grad[-1]/2+grad[1:-1].sum(0))/steps;residual=float(delta-attribution.sum())
   if abs(residual)<=max(.01,abs(delta)*.01):break
  return {'prediction':CLASSES[winner],'reference':CLASSES[reference],'method':'Approximate integrated gradients of winner-versus-runner-up logit margin','baseline':'Zero standardized log1p input (training log-feature means)','baseline_margin':margin(np.zeros_like(a)),'input_margin':margin(a),'completeness_residual':residual,'integration_steps':steps,'converged':abs(residual)<=max(.01,abs(delta)*.01),'features':[{'feature':c,'value':float(x[i]),'contribution':float(attribution[i])} for i,c in enumerate(FEATURES)],'note':'Local attribution, not a causal explanation, SHAP value, or calibrated confidence.'}
