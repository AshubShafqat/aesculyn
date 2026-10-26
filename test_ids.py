import unittest,io,struct
from ids.rules import detect,RuleConfig
from ids.risk import decide,Policy
from ids.pcap import extract,packets
class PipelineTests(unittest.TestCase):
 def test_rules_observed_only(self):
  self.assertFalse(detect({'n_called_ae':99},1,'s',RuleConfig(allowed_ae=['PACS'])))
  self.assertEqual(detect({'preamble_exec':1},1,'s')[0]['rule'],'preamble_exec')
  self.assertEqual(detect({},1,'s',RuleConfig(allowed_ae=['PACS']),['UNKNOWN'])[0]['rule'],'unknown_ae')
  self.assertFalse(detect({'preamble_exec':1},1,'s',RuleConfig(enabled={})))
 def test_thresholds(self):
  for p,l in [(0,0),(.299,0),(.3,1),(.6,2),(.8,3),(1,3)]:self.assertEqual(decide(p,[])['level'],l)
  self.assertEqual(decide(0,[{'rule':'x'}])['level'],3);self.assertFalse(decide(1,[])['executed'])
 def test_hysteresis(self):
  r=decide(.9,[])
  for _ in range(2):r=decide(.1,[],r);self.assertEqual(r['level'],3)
  self.assertEqual(decide(.1,[],r)['level'],0)
  with self.assertRaises(ValueError):decide(float('nan'),[])
  with self.assertRaises(ValueError):Policy(watch=.9).validate()
 def test_malformed_pcap(self):
  for raw in [b'',bytes(24),b'\xd4\xc3\xb2\xa1'+bytes(20)]:
   with self.assertRaises(ValueError):list(packets(io.BytesIO(raw)))
 def test_synthetic_association(self):
  pdu=b'\x01\x00'+struct.pack('!I',68)+b'\x00\x01\x00\x00'+b'PACS            '+b'SCU             '+bytes(32)
  tcp=struct.pack('!HHIIBBHHH',50000,104,0,0,0x50,2,1024,0,0)+pdu
  ip=b'\x45\x00'+struct.pack('!H',20+len(tcp))+bytes(4)+b'\x40\x06'+bytes(2)+bytes([10,1,1,2,10,1,1,3])+tcp;frame=bytes(12)+b'\x08\x00'+ip
  raw=b'\xd4\xc3\xb2\xa1'+struct.pack('<HHiIII',2,4,0,0,65535,1)+struct.pack('<IIII',100,0,len(frame),len(frame))+frame
  d=extract(io.BytesIO(raw),'test');w=d['windows'][0];self.assertEqual(w['features']['assoc_rq'],1);self.assertEqual(w['features']['syn'],1);self.assertIn('PACS',w['visible_ae']);self.assertEqual(len(w['events']),32);self.assertNotIn('10.1.1.2',str(d))
if __name__=='__main__':unittest.main()
