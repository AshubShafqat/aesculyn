"""Evidence-based rules on observed counters or decoded, visible DICOM fields."""
from dataclasses import dataclass,field
import math

@dataclass
class RuleConfig:
 enabled:dict=field(default_factory=lambda:{'preamble_exec':True,'bad_first_pdu':True,'big_pdu_len':True,'unknown_ae':True})
 allowed_ae:list=field(default_factory=list)

def detect(features,timestamp,source,config=None,visible_ae=None):
 c=config or RuleConfig();hits=[]
 for name in ['preamble_exec','bad_first_pdu','big_pdu_len']:
  value=float(features.get(name,0))
  if not math.isfinite(value) or value<0:raise ValueError('Invalid rule counter')
  if c.enabled.get(name,False) and value>0:
   hits.append({'rule':name,'timestamp':timestamp,'source':source,'severity':'high','evidence':{'feature':name,'observed_count':value},'explanation':{'preamble_exec':'Executable-header evidence was observed in a visible DICOM preamble; this is an A6 rule indicator, not proof of execution.','bad_first_pdu':'The extractor reported an invalid first DICOM PDU.','big_pdu_len':'The extractor reported a DICOM PDU length above its configured bound.'}[name]})
 # A count of AE titles cannot establish which title was used. Require visible strings.
 if c.enabled.get('unknown_ae') and c.allowed_ae and visible_ae is not None:
  unknown=sorted(set(visible_ae)-set(c.allowed_ae))
  if unknown:hits.append({'rule':'unknown_ae','timestamp':timestamp,'source':source,'severity':'medium','evidence':{'unknown_titles':unknown},'explanation':'A visible AE title was not present in the configured allowlist.'})
 return hits
