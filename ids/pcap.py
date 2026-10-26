"""Bounded classic-PCAP IPv4/TCP extractor. No capture, enforcement or TLS decryption."""
import hashlib,ipaddress,math,struct
import numpy as np
from engine import FEATURES
MAGIC={b'\xd4\xc3\xb2\xa1':('<',1e-6),b'\xa1\xb2\xc3\xd4':('>',1e-6),b'\x4d\x3c\xb2\xa1':('<',1e-9),b'\xa1\xb2\x3c\x4d':('>',1e-9)}
EVENTS=['PAD','SYN','RST','FIN','TCP','ASSOC_RQ','ASSOC_AC','ASSOC_RJ','P_DATA','RELEASE_RQ','RELEASE_RP','ABORT','BAD_PDU','BIG_PDU','HTTP_POST','PREAMBLE_EXEC','OTHER']
def packets(stream,max_packets=200000):
 h=stream.read(24)
 if len(h)!=24 or h[:4] not in MAGIC:raise ValueError('Expected classic PCAP; pcapng is unsupported.')
 endian,unit=MAGIC[h[:4]];major,minor,zone,sig,snap,link=struct.unpack(endian+'HHiIII',h[4:])
 if (major,minor)!=(2,4) or link!=1 or snap>16777216:raise ValueError('Only Ethernet PCAP v2.4 is supported.')
 count=0
 while True:
  head=stream.read(16)
  if not head:break
  if len(head)!=16:raise ValueError('Truncated PCAP header.')
  sec,frac,size,original=struct.unpack(endian+'IIII',head)
  if size>snap or size>16777216 or original<size:raise ValueError('Invalid packet size.')
  frame=stream.read(size);count+=1
  if len(frame)!=size:raise ValueError('Truncated packet.')
  if count>max_packets:raise ValueError('PCAP exceeds 200,000 packets.')
  yield sec+frac*unit,frame

def decode(frame):
 if len(frame)<14:return None
 offset=14;etype=int.from_bytes(frame[12:14],'big')
 if etype==0x8100:
  if len(frame)<18:return None
  etype=int.from_bytes(frame[16:18],'big');offset=18
 if etype!=0x0800 or len(frame)<offset+20:return None
 ip=frame[offset:];ihl=(ip[0]&15)*4;total=int.from_bytes(ip[2:4],'big')
 if ip[0]>>4!=4 or ihl<20 or total<ihl or len(ip)<total or ip[9]!=6 or int.from_bytes(ip[6:8],'big')&0x3fff:return None
 tcp=ip[ihl:total]
 if len(tcp)<20:return None
 th=(tcp[12]>>4)*4
 if th<20 or len(tcp)<th:return None
 return str(ipaddress.ip_address(ip[12:16])),str(ipaddress.ip_address(ip[16:20])),int.from_bytes(tcp[:2],'big'),int.from_bytes(tcp[2:4],'big'),tcp[13],tcp[th:]

def extract(stream,salt,ports=(104,11112),max_pdu=16777216):
 windows={};first_payload=set();seen=skipped=0;last=None
 for ts,frame in packets(stream):
  seen+=1
  if last is not None and ts<last:raise ValueError('PCAP timestamps must be nondecreasing.')
  last=ts;d=decode(frame)
  if d is None:skipped+=1;continue
  src,dst,sp,dp,flags,payload=d
  if dp in ports:client,flow,outgoing=src,(src,sp,dst,dp),True
  elif sp in ports:client,flow,outgoing=dst,(dst,dp,src,sp),False
  else:skipped+=1;continue
  source=hashlib.sha256((salt+'|'+client).encode()).hexdigest()[:20];start=math.floor(ts/2)*2;key=(source,start)
  if key not in windows:
   if len(windows)>=10000:raise ValueError('PCAP exceeds 10,000 windows.')
   windows[key]={'features':dict.fromkeys(FEATURES,0),'source':source,'timestamp':start,'times':[],'lengths':[],'ports':set(),'srcports':set(),'called':set(),'calling':set(),'events':[]}
  w=windows[key];f=w['features'];f['out_pkts' if outgoing else 'in_pkts']+=1;f['out_bytes' if outgoing else 'in_bytes']+=len(frame);w['lengths'].append(len(frame));w['times'].append(ts);w['ports'].add(dp if outgoing else sp);w['srcports'].add(sp if outgoing else dp);event='TCP'
  for mask,name in [(2,'syn'),(4,'rst'),(1,'fin')]:
   if flags&mask:f[name]+=1;event=name.upper()
  if payload and not payload.startswith((b'\x16\x03',b'\x17\x03')):
   if payload.startswith(b'POST '):f['http_post']+=1;event='HTTP_POST'
   if len(payload)>=6 and payload[0] in range(1,8) and payload[1]==0:
    kind=payload[0];size=int.from_bytes(payload[2:6],'big')
    if outgoing and flow not in first_payload and kind!=1:f['bad_first_pdu']+=1
    first_payload.add(flow)
    if size>max_pdu:f['big_pdu_len']+=1
    name,event={1:('assoc_rq','ASSOC_RQ'),2:('assoc_ac','ASSOC_AC'),3:('assoc_rj','ASSOC_RJ'),4:('pdata_pkts','P_DATA'),5:('release','RELEASE_RQ'),6:('release','RELEASE_RP'),7:('abort','ABORT')}[kind];f[name]+=1
    if kind in (1,2) and len(payload)>=42:
     w['called'].add(payload[10:26].decode('ascii',errors='replace').strip());w['calling'].add(payload[26:42].decode('ascii',errors='replace').strip())
   pos=payload.find(b'DICM')
   if pos>=128 and payload[pos-128:pos].startswith((b'MZ',b'\x7fELF',b'#!')):f['preamble_exec']+=1;event='PREAMBLE_EXEC'
  w['events'].append([EVENTS.index(event),int(outgoing),min(len(frame),32767)])
 result=[]
 for key,w in sorted(windows.items(),key=lambda kv:(kv[0][1],kv[0][0])):
  f=w['features'];lengths=np.asarray(w.pop('lengths'));iat=np.diff(w.pop('times'));f.update(mean_pkt=float(lengths.mean()),std_pkt=float(lengths.std()),mean_iat=float(iat.mean()) if len(iat) else 0.,std_iat=float(iat.std()) if len(iat) else 0.,n_dst_ports=len(w.pop('ports')),n_src_ports=len(w.pop('srcports')),n_called_ae=len(w['called']),n_calling_ae=len(w['calling']));w['visible_ae']=sorted(w.pop('called')|w.pop('calling'));events=w['events'][-32:];w['events']=[[0,0,0]]*(32-len(events))+events;result.append(w)
 return {'windows':result,'packets':seen,'skipped_packets':skipped,'schema':'experimental-pcap-v1','limitations':['Classic Ethernet IPv4 TCP PCAP only. No IPv6, pcapng, IP/TCP reassembly or TLS decryption.','Only fully visible per-packet headers are inspected; fragmented/segmented application fields can be missed.','Feature semantics and event encoding are not validated against the supplied training generator. ML inference is disabled for these extracted windows.']}
