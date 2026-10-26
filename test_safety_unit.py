"""Dry-run incident privacy checks without socket binding."""
import struct,tempfile,unittest
import numpy as np
from application.store import Store
from application.incidents import Incidents
from application.captures import Captures
from engine import FEATURES

def one_packet_pcap(payload=b''):
 tcp=struct.pack('!HHIIBBHHH',50000,104,0,0,0x50,2,1024,0,0)+payload
 ip=b'\x45\x00'+struct.pack('!H',20+len(tcp))+bytes(4)+b'\x40\x06'+bytes(2)+bytes([10,1,1,2,10,1,1,3])+tcp
 frame=bytes(12)+b'\x08\x00'+ip
 return b'\xd4\xc3\xb2\xa1'+struct.pack('<HHiIII',2,4,0,0,65535,1)+struct.pack('<IIII',100,0,len(frame),len(frame))+frame

class SafetyUnit(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=r'C:\Users\Malik\Documents\Codex\2026-10-24\hi\work\pip-temp');self.store=Store(self.tmp.name);_,_,self.user=self.store.register('qa@example.test','Local QA','temporary-test-password');self.incidents=Incidents(self.store);self.captures=Captures(self.store,self.incidents)
 def tearDown(self):self.tmp.cleanup()
 def test_capture_report_discards_raw_and_masks_ip(self):
  result=self.captures.submit(self.user,one_packet_pcap(),'sample.pcap');self.assertEqual(result['summary']['packets'],1);self.assertEqual(result['summary']['windows'],1)
  report=self.captures.report(self.user,result['id']);self.assertNotIn('10.1.1.2',str(report));self.assertNotIn('visible_ae',str(report));self.assertFalse(any(p.suffix=='.pcap' for p in self.captures.root.iterdir()))
  _,_,other=Store(self.tmp.name).register('b@example.test','Other','temporary-test-password');self.assertIsNone(self.captures.get(other,result['id']))
 def test_rules_create_reviewable_dry_run_incident(self):
  class Fake:
   def explain(self,model,row):return {'method':'test attribution','features':[{'feature':f,'contribution':float(i)/100} for i,f in enumerate(FEATURES)]}
  aid='a'*32;self.store.create_analysis(self.user['workspace_id'],'sample.csv',1,'m','hash',False)
  with self.store.connect() as db:db.execute("UPDATE analyses SET id=? WHERE name='sample.csv'",(aid,))
  record={'id':aid,'workspace_id':self.user['workspace_id'],'model_id':'m','created':1700000000};x=np.zeros((1,len(FEATURES)));x[0,FEATURES.index('preamble_exec')]=1;p=np.array([[.2,.8,0,0,0,0,0,0]])
  self.assertEqual(self.incidents.record(record,x,p,Fake()),1);item=self.incidents.list(self.user['workspace_id'])['incidents'][0];i=self.incidents.get(self.user['workspace_id'],item['id']);self.assertEqual(i['level'],3);self.assertFalse(i['evidence']['response']['executed']);self.assertEqual(i['evidence']['rules'][0]['rule'],'preamble_exec');self.incidents.review(self.user,i['id'],'acknowledged');self.assertEqual(self.incidents.get(self.user['workspace_id'],i['id'])['status'],'acknowledged')
 def test_dry_run_policy_rejects_host_enforcement(self):
  with self.assertRaises(ValueError):self.incidents.configure(self.user,{'mode':'live','policy':{},'rules':{}})
  with self.assertRaises(ValueError):self.incidents.configure(self.user,{'mode':'dry-run','policy':{'watch':.9},'rules':{}})
if __name__=='__main__':unittest.main()
