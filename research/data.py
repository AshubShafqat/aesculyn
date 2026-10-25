"""Dataset audit and purged, fixed experimental partitions. No packet extraction."""
import hashlib, io, json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from engine import CLASSES, FEATURES, inspect_archive, validate_frame
PROTOCOLS = {'unseen_site':(['A','B'],['C']), 'temporal_federation':(['A','B','C'],['A','B','C'])}
def write_json(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')
def numeric_digest(df):
 x=validate_frame(df).astype('<f8');x[x==0]=0
 return np.array([hashlib.sha256(r.tobytes()).hexdigest() for r in x])
def audit_archive(archive):
 df,sha,info=inspect_archive(archive)
 cols=['site','client_ip','window_start','label_binary','label_class','scenario_id','run_id','split_time','split_site','split_block']
 if any(c not in df for c in cols) or df[cols].isna().any().any():raise ValueError('Missing metadata or labels')
 validate_frame(df)
 if set(df.label_class)!=set(CLASSES) or set(df.site)!={'A','B','C'}:raise ValueError('Unexpected classes/sites')
 if not np.array_equal((df.label_class!='benign').astype(int),df.label_binary):raise ValueError('Binary/class label disagreement')
 for c in ['split_time','split_site','split_block']:
  if set(df[c])!={'train','val','test'}:raise ValueError('Invalid predefined split')
 if not np.isfinite(df.window_start.to_numpy(float)).all():raise ValueError('Invalid timestamps')
 keys=['site','client_ip','window_start'];conflict_keys=int((df.groupby(keys).label_class.nunique()>1).sum())
 if conflict_keys:raise ValueError('Conflicting collection-key labels')
 hashes=numeric_digest(df);g=pd.DataFrame({'hash':hashes,'label':df.label_class}).groupby('hash').label.nunique();conflicts=set(g[g>1].index)
 with zipfile.ZipFile(archive) as z:
  ns=[n for n in z.namelist() if n.endswith('/labels.csv') or n=='labels.csv']
  if len(ns)!=1 or z.getinfo(ns[0]).file_size>10_000_000:raise ValueError('Expected one bounded labels.csv')
  a=pd.read_csv(io.BytesIO(z.read(ns[0])))
 ac=['site','src_ip','start_ts','end_ts','label_class']
 if any(c not in a for c in ac) or a[ac].isna().any().any():raise ValueError('Invalid annotation schema')
 if not set(a.label_class).issubset(set(CLASSES)-{'benign'}):raise ValueError('Unknown annotation class')
 if not np.isfinite(a[['start_ts','end_ts']].to_numpy(float)).all() or (a.end_ts<a.start_ts).any():raise ValueError('Invalid annotation intervals')
 exact=np.zeros(len(df),bool);near=exact.copy();inside=exact.copy()
 for r in a.itertuples():
  source=df.site.eq(r.site)&df.client_ip.eq(r.src_ip);cl=df.label_class.eq(r.label_class);m=source&df.window_start.between(r.start_ts,r.end_ts)
  inside|=m.to_numpy(copy=True);exact|=(m&cl).to_numpy(copy=True);near|=(source&cl&df.window_start.between(r.start_ts-2,r.end_ts+2)).to_numpy(copy=True)
 pos=df.label_binary.eq(1).to_numpy(copy=True)
 counters=[c for c in FEATURES if c not in ['mean_pkt','std_pkt','mean_iat','std_iat']]
 fractional={c:int((df[c]%1!=0).sum()) for c in counters}
 if any(fractional.values()):raise ValueError('Fractional counters')
 corr=df[FEATURES].corr().abs();pairs=[{'a':c,'b':b,'absolute_pearson':float(corr.loc[c,b])} for i,c in enumerate(FEATURES) for b in FEATURES[i+1:] if np.isfinite(corr.loc[c,b]) and corr.loc[c,b]>.95]
 splits={c:{'class_counts':pd.crosstab(df[c],df.label_class).to_dict(orient='index'),'time_ranges':{k:[int(v.window_start.min()),int(v.window_start.max())] for k,v in df.groupby(c)},'sites':{k:sorted(v.site.unique().tolist()) for k,v in df.groupby(c)}} for c in ['split_time','split_site','split_block']}
 report={'dataset_sha256':sha,'rows':len(df),'columns':len(df.columns),'class_counts':df.label_class.value_counts().to_dict(),'site_class_counts':pd.crosstab(df.site,df.label_class).to_dict(orient='index'),'missing_cells':int(df.isna().sum().sum()),'full_duplicate_rows':int(df.duplicated().sum()),'repeated_feature_vectors':len(df)-len(set(hashes)),'conflicting_feature_vectors':len(conflicts),'rows_with_conflicting_features':int(np.isin(hashes,list(conflicts)).sum()),'duplicate_collection_keys':int(df.duplicated(keys).sum()),'conflicting_collection_keys':conflict_keys,'unique_run_ids':int(df.run_id.nunique()),'annotation_intervals':len(a),'malicious_windows':int(pos.sum()),'malicious_annotation_exact_matches':int((pos&exact).sum()),'malicious_annotation_matches_with_2s_tolerance':int((pos&near).sum()),'benign_windows_inside_attack_intervals':int((~pos&inside).sum()),'fractional_counter_values':fractional,'highly_correlated_feature_pairs':pairs,'archive':info,'supplied_splits':splits,'excluded_columns':[c for c in df if c not in FEATURES],'limitations':['Annotation agreement checks internal consistency, not independently verified truth.','Two-second annotation tolerance is a diagnostic assumption; capture-window semantics are undocumented.','One run_id prevents independent-run validation.','Previously inspected data reused diagnostically; no fresh external holdout exists.','Retrospective traffic windows: feature availability and live extraction unverified.','Capture provenance, attack realism, and PCAP feature extraction require independent verification.']}
 return df,hashes,conflicts,report

def partition(df,hashes,conflicts,protocol,gap_seconds=60):
 if protocol not in PROTOCOLS or gap_seconds<0:raise ValueError('Invalid protocol/purge gap')
 train_sites,test_sites=PROTOCOLS[protocol]
 masks={'train':(df.site.isin(train_sites)&df.split_time.eq('train')).to_numpy(copy=True),'val':(df.site.isin(train_sites)&df.split_time.eq('val')).to_numpy(copy=True),'test':(df.site.isin(test_sites)&df.split_time.eq('test')).to_numpy(copy=True)}
 before={k:int(v.sum()) for k,v in masks.items()};removed={k:{'boundary_purge':0,'conflicting_features':0,'repeated_features':0} for k in masks}
 for site in sorted(df.site.unique()):
  for earlier,later in [('train','val'),('val','test')]:
   a=masks[earlier]&df.site.eq(site).to_numpy(copy=True);b=masks[later]&df.site.eq(site).to_numpy(copy=True)
   if not a.any() or not b.any():continue
   end=int(df.loc[a,'window_start'].max());start=int(df.loc[b,'window_start'].min())
   if end>=start:raise ValueError('Nonchronological split within site')
   for name,drop in [(earlier,a&(df.window_start.to_numpy(copy=True)>=start-gap_seconds)),(later,b&(df.window_start.to_numpy(copy=True)<=end+gap_seconds))]:
    masks[name]&=~drop;removed[name]['boundary_purge']+=int(drop.sum())
 # Also enforce chronology across sites, not just within each site's predefined split.
 for earlier,later in [('train','val'),('val','test')]:
  a=masks[earlier].copy();b=masks[later].copy();end=int(df.loc[a,'window_start'].max());start=int(df.loc[b,'window_start'].min())
  for name,drop in [(earlier,a&(df.window_start.to_numpy(copy=True)>=start-gap_seconds)),(later,b&(df.window_start.to_numpy(copy=True)<=end+gap_seconds))]:
   masks[name]&=~drop;removed[name]['boundary_purge']+=int(drop.sum())
 seen=set()
 for name in ['train','val','test']:
  # Conflicts are audit findings only. Never let evaluation labels curate training rows.
  # Feature-only duplicate precedence is independent of every partition's target values.
  removed[name]['conflicting_features']=0
  for i in np.flatnonzero(masks[name]):
   if hashes[i] in seen:masks[name][i]=False;removed[name]['repeated_features']+=1
   else:seen.add(hashes[i])
  if not masks[name].any():raise ValueError('Empty partition: '+name)
 for a,b in [('train','val'),('train','test'),('val','test')]:
  if set(hashes[masks[a]])&set(hashes[masks[b]]):raise AssertionError('Feature overlap after isolation')
 if set(df.loc[masks['train'],'label_class'])!=set(CLASSES):raise ValueError('Training class absent')
 meta={'training_sites':train_sites,'test_sites':test_sites,'gap_seconds':gap_seconds,'before':before,'counts':{k:int(v.sum()) for k,v in masks.items()},'removed':removed,'class_counts':{k:df.loc[v,'label_class'].value_counts().to_dict() for k,v in masks.items()},'sites':{k:sorted(df.loc[v,'site'].unique().tolist()) for k,v in masks.items()},'time_ranges_by_site':{k:{s:[int(g.window_start.min()),int(g.window_start.max())] for s,g in df.loc[v].groupby('site')} for k,v in masks.items()},'partition_sha256':{k:hashlib.sha256(''.join(sorted(hashes[v])).encode()).hexdigest() for k,v in masks.items()},'feature_overlap':{'train_val':0,'train_test':0,'val_test':0}}
 return masks,meta
