"""Local-only Gaussian naive Bayes research baseline. No extracted code is executed."""
import hashlib, io, json, zipfile
from pathlib import Path, PurePosixPath
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parent
DEFAULT_ARCHIVE = Path(__import__('os').environ.get('AESCULYN_DATASET', 'data/dataset.zip'))
FEATURES = ['out_pkts','out_bytes','in_pkts','in_bytes','mean_pkt','std_pkt','mean_iat','std_iat','syn','rst','fin','n_dst_ports','n_src_ports','assoc_rq','assoc_ac','assoc_rj','abort','release','pdata_pkts','n_called_ae','n_calling_ae','bad_first_pdu','big_pdu_len','http_post','preamble_exec']
CLASSES = ['benign','recon','ae_bruteforce','assoc_flood','malformed_pdu','ransomware_like','exfiltration','preamble_polyglot']

def inspect_archive(path):
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos)>10000: raise ValueError('Archive has too many entries')
        names=set()
        for i in infos:
            n=PurePosixPath(i.filename.replace('\\','/'))
            if n.is_absolute() or '..' in n.parts or ':' in i.filename or i.filename in names: raise ValueError('Unsafe or duplicate archive path')
            if i.file_size>2_000_000_000 or i.file_size/max(i.compress_size,1)>10000: raise ValueError('Oversized archive entry')
            names.add(i.filename)
        candidates=[i for i in infos if i.filename.endswith('/features.csv') or i.filename=='features.csv']
        if len(candidates)!=1 or candidates[0].file_size>100_000_000: raise ValueError('Expected one features.csv below 100 MB')
        raw=z.read(candidates[0])
        return pd.read_csv(io.BytesIO(raw)),hashlib.sha256(raw).hexdigest(),{'entries':len(infos),'compressed_bytes':Path(path).stat().st_size,'uncompressed_bytes':sum(i.file_size for i in infos),'feature_bytes':len(raw),'formats':sorted(set(PurePosixPath(i.filename).suffix for i in infos if not i.is_dir()))}

def validate_frame(df):
    missing=[c for c in FEATURES if c not in df]
    if missing: raise ValueError('Missing feature columns: '+', '.join(missing))
    if df.empty or len(df)>100000: raise ValueError('Expected 1 to 100,000 rows')
    try: x=df[FEATURES].apply(pd.to_numeric,errors='raise').to_numpy(dtype=float)
    except (ValueError,TypeError): raise ValueError('Features must contain numeric values')
    if not np.isfinite(x).all(): raise ValueError('Features contain missing or infinite values')
    if (x<0).any(): raise ValueError('Traffic counters and statistics must be nonnegative')
    return x

def transform(x): return np.log1p(x)

def fit(x,y):
    a=transform(x)
    if set(y)!=set(CLASSES): raise ValueError('Training set must contain all eight classes')
    means=np.array([a[y==c].mean(0) for c in CLASSES])
    variances=np.array([a[y==c].var(0) for c in CLASSES]) + max(float(a.var(0).max())*1e-3,1e-6)
    # Uniform priors intentionally counter majority-class dominance; no test tuning.
    return {'means':means,'variances':variances,'prior':np.full(len(CLASSES),1/len(CLASSES))}

def terms(x,model):
    a=transform(x)
    return -.5*(np.log(2*np.pi*model['variances'])[None,:,:]+(a[:,None,:]-model['means'][None,:,:])**2/model['variances'][None,:,:])

def predict(x,model): return np.array(CLASSES)[(terms(x,model).sum(2)+np.log(model['prior'])).argmax(1)]

def metrics(y,p):
    cm=np.array([[int(((y==a)&(p==b)).sum()) for b in CLASSES] for a in CLASSES])
    rows=[]
    for i,c in enumerate(CLASSES):
        tp=int(cm[i,i]); support=int(cm[i].sum()); precision=tp/max(int(cm[:,i].sum()),1);recall=tp/max(support,1)
        rows.append({'class':c,'precision':precision,'recall':recall,'f1':2*precision*recall/max(precision+recall,1e-15),'support':support})
    fn=int(((y!='benign')&(p=='benign')).sum());fp=int(((y=='benign')&(p!='benign')).sum())
    return {'accuracy':float((y==p).mean()),'macro_precision':float(np.mean([r['precision'] for r in rows])),'macro_recall':float(np.mean([r['recall'] for r in rows])),'macro_f1':float(np.mean([r['f1'] for r in rows])),'weighted_f1':float(sum(r['f1']*r['support'] for r in rows)/len(y)),'false_negatives':fn,'false_positives':fp,'false_negative_rate':fn/max(int((y!='benign').sum()),1),'false_positive_rate':fp/max(int((y=='benign').sum()),1),'confusion_matrix':cm.tolist(),'per_class':rows,'records':len(y)}

def split_data(df,column):
    if not set(df[column]).issubset({'train','val','test'}): raise ValueError('Invalid predefined split labels')
    # Keep all identical feature vectors in only the earliest partition.
    hashes=pd.util.hash_pandas_object(df[FEATURES],index=False)
    masks={}; seen=set();removed={}
    for part in ['train','val','test']:
        m=df[column].eq(part);drop=m & hashes.isin(seen);removed[part]=int(drop.sum());m=m & ~drop
        masks[part]=m.to_numpy();seen.update(hashes[m].tolist())
    return masks,removed

def prepare(path=DEFAULT_ARCHIVE):
    df,digest,archive=inspect_archive(path);x=validate_frame(df)
    if df.label_class.isna().any() or set(df.label_class)!=set(CLASSES): raise ValueError('Unknown or missing class labels')
    if not np.array_equal((df.label_class!='benign').astype(int).values,df.label_binary.values): raise ValueError('Binary and multiclass labels disagree')
    experiments={};models={}; masks_all={}
    for split in ['split_site','split_time','split_block']:
        masks,removed=split_data(df,split);model=fit(x[masks['train']],df.label_class.values[masks['train']]);models[split]=model;masks_all[split]=masks
        experiments[split]={'validation':metrics(df.label_class.values[masks['val']],predict(x[masks['val']],model)),'test':metrics(df.label_class.values[masks['test']],predict(x[masks['test']],model)),'partition_counts':{k:int(v.sum()) for k,v in masks.items()},'duplicate_overlap_removed':removed,'sites':{k:sorted(df.loc[v,'site'].unique().tolist()) for k,v in masks.items()},'time_ranges':{k:[int(df.loc[v,'window_start'].min()),int(df.loc[v,'window_start'].max())] for k,v in masks.items()}}
    primary=models['split_site'];m=masks_all['split_site']['test'];pred=predict(x[m],primary)
    schema=[{'name':c,'dtype':str(df[c].dtype),'missing':int(df[c].isna().sum()),'role':'feature' if c in FEATURES else 'excluded metadata / label'} for c in df]
    counts={c:int((df.label_class==c).sum()) for c in CLASSES}
    summary={'rows':len(df),'columns':len(df.columns),'features':FEATURES,'classes':CLASSES,'distribution':counts,'sites':df.site.value_counts().to_dict(),'sha256':digest,'archive':archive,'schema':schema,'missing_values':int(df.isna().sum().sum()),'duplicate_rows':int(df.duplicated().sum()),'duplicate_feature_vectors':int(df[FEATURES].duplicated().sum()),'label_mapping':{'benign':0,'all_other_listed_classes':1},'experiments':experiments,'primary':'split_site','model':'Gaussian naive Bayes · log1p features · uniform priors','limitations':['Offline baseline; no clinical or deployment validation.','All feature rows share one run_id; independent-run generalization cannot be measured.','Raw PCAP and sequence data are not parsed or exposed.','Labels are supplied annotations; capture provenance and attack realism are unverified.','Feature independence assumption and uniform priors limit score interpretation.','No SHAP/LIME, federated clients, differential privacy, or enforcement integration.','Three predefined split experiments reuse the corpus; they are not independent replications.']}
    # Only telemetry feature values and labels are exposed, never IP addresses or raw packets.
    preview=df[FEATURES+['label_class','split_site']].copy()
    tests=df.loc[m,FEATURES+['label_class']].copy();tests['prediction']=pred
    ROOT.joinpath('artifacts').mkdir(exist_ok=True)
    ROOT.joinpath('artifacts/summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    preview.to_csv(ROOT/'artifacts/flows.csv',index=False);tests.to_csv(ROOT/'artifacts/test_predictions.csv',index=False)
    np.savez(ROOT/'artifacts/model.npz',**primary,features=np.array(FEATURES),classes=np.array(CLASSES))
    print(json.dumps({'rows':len(df),'primary':experiments['split_site']['test'],'duplicates':summary['duplicate_feature_vectors']},indent=2))
    return summary

def load_model():
    with np.load(ROOT/'artifacts/model.npz',allow_pickle=False) as z:
        if z['features'].tolist()!=FEATURES or z['classes'].tolist()!=CLASSES: raise ValueError('Model schema mismatch')
        return {k:z[k] for k in ['means','variances','prior']}

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--archive',type=Path,default=DEFAULT_ARCHIVE);prepare(a.parse_args().archive)
