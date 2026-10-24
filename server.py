import io,json,mimetypes,threading,time
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from pathlib import Path
import numpy as np
import pandas as pd
from engine import ROOT,FEATURES,CLASSES,validate_frame,predict,terms,load_model
EVENTS=[];LOCK=threading.Lock()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,data,status=200,kind='application/json'):
        raw=json.dumps(data,allow_nan=False).encode() if kind=='application/json' else data
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'");self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        u=urlparse(self.path);q=parse_qs(u.query)
        try:
            if u.path=='/api/summary':
                f=ROOT/'artifacts/summary.json'
                return self.send(json.loads(f.read_text()) if f.exists() else {'error':'Dataset not prepared. Run engine.py first.'},200 if f.exists() else 503)
            if u.path=='/api/health': return self.send({'model_artifact':(ROOT/'artifacts/model.npz').exists(),'dataset_artifact':(ROOT/'artifacts/flows.csv').exists(),'cpu_threads':__import__('os').cpu_count(),'federated':'Not configured','enforcement':'Not configured','mode':'Local offline research'})
            if u.path=='/api/events':
                with LOCK: data=list(EVENTS)
                return self.send(data)
            if u.path=='/api/rows':
                d=pd.read_csv(ROOT/'artifacts/flows.csv');search=q.get('search',[''])[0].lower()[:80]
                if search: d=d[d.label_class.str.contains(search,regex=False)]
                sort=q.get('sort',['label_class'])[0]
                if sort in d: d=d.sort_values(sort,kind='stable')
                page=max(0,int(q.get('page',['0'])[0]));return self.send({'total':len(d),'page':page,'rows':d.iloc[page*20:page*20+20].to_dict('records')})
            if u.path=='/api/explain':
                d=pd.read_csv(ROOT/'artifacts/test_predictions.csv');i=int(q.get('row',['0'])[0])
                if i<0 or i>=len(d): raise ValueError('Row is outside test dataset')
                r=d.iloc[[i]];model=load_model();t=terms(validate_frame(r),model)[0];scores=t.sum(1)+np.log(model['prior']);order=np.argsort(scores);winner=int(order[-1]);runner=int(order[-2]);contribution=t[winner]-t[runner]
                return self.send({'row':i,'prediction':CLASSES[winner],'reference':CLASSES[runner],'actual':str(r.label_class.iloc[0]),'margin':float(scores[winner]-scores[runner]),'prior_margin':float(np.log(model['prior'][winner]/model['prior'][runner])),'contributions':[{'feature':c,'value':float(r[c].iloc[0]),'contribution':float(contribution[j])} for j,c in enumerate(FEATURES)]})
            if u.path=='/api/export': return self.send((ROOT/'artifacts/summary.json').read_bytes(),kind='application/json; charset=utf-8')
            allowed={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}
            if u.path not in allowed: return self.send({'error':'Not found'},404)
            f=ROOT/'static'/allowed[u.path];return self.send(f.read_bytes(),kind=mimetypes.guess_type(f.name)[0] or 'text/plain')
        except (ValueError,KeyError) as e: self.send({'error':str(e)},400)
        except FileNotFoundError: self.send({'error':'Dataset or model is unavailable. Run engine.py.'},503)
        except Exception: self.send({'error':'Request failed; check local artifacts and input format.'},500)
    def do_POST(self):
        # Browser same-origin protection, no CORS, and bounded CSV input.
        if self.path!='/api/predict': return self.send({'error':'Not found'},404)
        if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')): return self.send({'error':'Origin not allowed'},403)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>5_000_000: raise ValueError('CSV upload must be 1 byte to 5 MB')
            d=pd.read_csv(io.BytesIO(self.rfile.read(n)))
            if len(d)>10000: raise ValueError('Batch limit is 10,000 rows')
            x=validate_frame(d);start=time.perf_counter();pred=predict(x,load_model());elapsed=time.perf_counter()-start
            counts={c:int((pred==c).sum()) for c in CLASSES};now=datetime.now(timezone.utc).isoformat()
            event={'timestamp':now,'rows':len(d),'predictions':counts,'malicious_predictions':int((pred!='benign').sum()),'severity':'Review required' if (pred!='benign').any() else 'Informational','explanation':'Exact model decomposition available for held-out examples'}
            with LOCK:
                EVENTS.insert(0,event);del EVENTS[100:]
            return self.send({'rows':len(d),'inference_ms':elapsed*1000,'counts':counts,'predictions':pred.tolist(),'note':'Uncalibrated baseline. Predictions are not confirmed incidents.'})
        except (ValueError,UnicodeDecodeError,pd.errors.ParserError) as e: self.send({'error':str(e)},400)
        except FileNotFoundError: self.send({'error':'Model unavailable; run engine.py.'},503)
        except Exception: self.send({'error':'Inference failed. Verify the CSV and model artifacts.'},400)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args()
    print(f'DICOM Sentinel: http://127.0.0.1:{a.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
