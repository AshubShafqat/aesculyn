"""Configurable dry-run ladder with immediate escalation and clean-window release."""
from dataclasses import dataclass
import math

@dataclass
class Policy:
 watch:float=.30
 restrict:float=.60
 quarantine:float=.80
 release_margin:float=.05
 clean_windows:int=3
 def validate(self):
  if not 0<self.watch<self.restrict<self.quarantine<=1 or not 0<=self.release_margin<self.watch or not 1<=self.clean_windows<=100:raise ValueError('Invalid risk thresholds or hysteresis')
  return self

def decide(attack_probability,rule_hits,previous=None,policy=None,calibrated=False):
 p=(policy or Policy()).validate();score=float(attack_probability)
 if not math.isfinite(score) or not 0<=score<=1:raise ValueError('Invalid attack probability')
 if rule_hits:score=1.
 target=3 if score>=p.quarantine else 2 if score>=p.restrict else 1 if score>=p.watch else 0
 previous=previous or {'level':0,'clean_windows':0};level=int(previous['level']);clean=0
 if target>=level:level=target
 else:
  boundary=[0,p.watch,p.restrict,p.quarantine][level]
  clean=int(previous.get('clean_windows',0))+1 if score<boundary-p.release_margin else 0
  if clean>=p.clean_windows:level=target;clean=0
 return {'score':score,'attack_probability':float(attack_probability),'level':level,'target_level':target,'clean_windows':clean,'calibrated':bool(calibrated),'mode':'dry-run','executed':False,'action':['log_only','propose_watch','propose_rate_limit_and_ae_review','propose_quarantine_pending_review'][level],'reason':'Qualifying rule hit sets risk to one.' if rule_hits else ('Validation-calibrated experimental model score.' if calibrated else 'Uncalibrated experimental model score; thresholds are not operationally validated.')}
