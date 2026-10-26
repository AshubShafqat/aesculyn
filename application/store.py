"""SQLite ownership, sessions and persisted analysis state."""
import contextlib,hashlib,hmac,json,re,secrets,sqlite3,time,uuid
from pathlib import Path

ITERATIONS=600_000

def password_hash(password,salt=None):
 if not isinstance(password,str) or not 12<=len(password)<=128:raise ValueError('Use a password between 12 and 128 characters.')
 salt=salt or secrets.token_hex(16)
 digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
 return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'
def password_matches(password,encoded):
 try:
  method,n,salt,digest=encoded.split('$')
  if method!='pbkdf2_sha256' or not isinstance(password,str) or len(password)>128:return False
  actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(n)).hex()
  return hmac.compare_digest(actual,digest)
 except (ValueError,TypeError):return False

def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()
def now():return int(time.time())

class Store:
 def __init__(self,directory):
  self.root=Path(directory).resolve();self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'aesculyn.sqlite3'
  with self.connect() as db:
   db.executescript('''
   PRAGMA journal_mode=WAL;
   CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,created INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,start INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,name TEXT NOT NULL,created INTEGER NOT NULL,updated INTEGER NOT NULL,status TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,rows INTEGER NOT NULL,model_id TEXT NOT NULL,input_hash TEXT NOT NULL,labelled INTEGER NOT NULL,summary TEXT,error TEXT,cancel INTEGER NOT NULL DEFAULT 0);
   CREATE INDEX IF NOT EXISTS analyses_workspace ON analyses(workspace_id,created);
   CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,action TEXT NOT NULL,analysis_id TEXT,created INTEGER NOT NULL);
   ''')
   db.execute("UPDATE analyses SET status='failed',error='Server restarted before analysis completed. Retry this analysis.',updated=? WHERE status IN ('queued','running')",(now(),))
   db.execute('DELETE FROM sessions WHERE expires<?',(now(),))
 @contextlib.contextmanager
 def connect(self):
  db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
  try:
   with db:yield db
  finally:db.close()
 def throttle(self,key,limit=10,seconds=600):
  key=token_hash(key)
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
   if row and row['start']>now()-seconds:
    if row['count']>=limit:return False
    db.execute('UPDATE attempts SET count=count+1 WHERE key=?',(key,))
   else:db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,1,now()))
   db.execute('DELETE FROM attempts WHERE start<?',(now()-86400,))
  return True
 def register(self,email,name,password):
  email=str(email).strip().lower();name=str(name).strip()
  if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError('Enter a valid email address.')
  if not 1<=len(name)<=80 or any(ord(c)<32 for c in name):raise ValueError('Enter a name between 1 and 80 characters.')
  encoded=password_hash(password);uid=uuid.uuid4().hex;wid=uuid.uuid4().hex
  try:
   with self.connect() as db:
    db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(uid,email,name,encoded,now()));db.execute('INSERT INTO workspaces VALUES(?,?,?)',(wid,uid,'My research workspace'));db.execute('INSERT INTO audit(user_id,action,created) VALUES(?,?,?)',(uid,'account_created',now()))
  except sqlite3.IntegrityError:raise ValueError('An account with this email already exists. Sign in instead.')
  return self.create_session(uid)
 def login(self,email,password):
  with self.connect() as db:user=db.execute('SELECT * FROM users WHERE email=?',(str(email).strip().lower(),)).fetchone()
  # Perform the same expensive hashing for nonexistent accounts.
  encoded=user['password'] if user else 'pbkdf2_sha256$600000$'+'0'*32+'$'+'0'*64
  valid=password_matches(password,encoded)
  if not user or not valid:raise ValueError('Email or password is incorrect.')
  return self.create_session(user['id'])
 def create_session(self,uid):
  token=secrets.token_urlsafe(32);csrf=hmac.new(token.encode(),b'aesculyn-csrf',hashlib.sha256).hexdigest()
  with self.connect() as db:
   db.execute('DELETE FROM sessions WHERE expires<?',(now(),));db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token_hash(token),uid,token_hash(csrf),now()+8*3600))
  return token,csrf,self.user(uid)
 def user(self,uid):
  with self.connect() as db:
   row=db.execute('SELECT u.id,u.email,u.name,w.id AS workspace_id,w.name AS workspace FROM users u JOIN workspaces w ON w.user_id=u.id WHERE u.id=?',(uid,)).fetchone()
  return dict(row) if row else None
 def authenticate(self,token):
  if not token or len(token)>256:return None
  with self.connect() as db:row=db.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(token_hash(token),now())).fetchone()
  return dict(row) if row else None
 def csrf(self,session,token):return isinstance(token,str) and hmac.compare_digest(session['csrf'],token_hash(token))
 def logout(self,token):
  with self.connect() as db:db.execute('DELETE FROM sessions WHERE token=?',(token_hash(token),))
 def rotate_csrf(self,token):
  csrf=hmac.new(token.encode(),b'aesculyn-csrf',hashlib.sha256).hexdigest()
  with self.connect() as db:db.execute('UPDATE sessions SET csrf=? WHERE token=?',(token_hash(csrf),token_hash(token)))
  return csrf
 def change_password(self,uid,old,new):
  with self.connect() as db:row=db.execute('SELECT password FROM users WHERE id=?',(uid,)).fetchone()
  if not row or not password_matches(old,row['password']):raise ValueError('Current password is incorrect.')
  encoded=password_hash(new)
  with self.connect() as db:db.execute('UPDATE users SET password=? WHERE id=?',(encoded,uid));db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
 def rename_workspace(self,uid,name):
  name=str(name).strip()
  if not 1<=len(name)<=80 or any(ord(c)<32 for c in name):raise ValueError('Workspace name must be 1 to 80 characters.')
  with self.connect() as db:db.execute('UPDATE workspaces SET name=? WHERE user_id=?',(name,uid))
 def list_analyses(self,wid):
  with self.connect() as db:rows=db.execute('SELECT * FROM analyses WHERE workspace_id=? ORDER BY created DESC,id DESC LIMIT 100',(wid,)).fetchall()
  return [self.decode(r) for r in rows]
 @staticmethod
 def decode(row):
  if not row:return None
  r=dict(row);r['summary']=json.loads(r['summary']) if r.get('summary') else None;return r
 def analysis(self,wid,aid):
  with self.connect() as db:row=db.execute('SELECT * FROM analyses WHERE id=? AND workspace_id=?',(aid,wid)).fetchone()
  return self.decode(row)
 def create_analysis(self,wid,name,rows,model_id,input_hash,labelled):
  aid=uuid.uuid4().hex
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute("SELECT count(*) FROM analyses WHERE status IN ('queued','running')").fetchone()[0]>=16:raise ValueError('Server analysis queue is full. Try again after current jobs finish.')
   if db.execute('SELECT count(*) FROM analyses WHERE workspace_id=?',(wid,)).fetchone()[0]>=100:raise ValueError('Workspace limit is 100 analyses. Delete old analyses first.')
   if db.execute("SELECT count(*) FROM analyses WHERE workspace_id=? AND status IN ('queued','running')",(wid,)).fetchone()[0]>=3:raise ValueError('At most three analyses can be queued per workspace.')
   db.execute('INSERT INTO analyses(id,workspace_id,name,created,updated,status,progress,rows,model_id,input_hash,labelled) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(aid,wid,name,now(),now(),'queued',0,rows,model_id,input_hash,int(labelled)))
  return aid
 def update(self,aid,**changes):
  allowed={'status','progress','summary','error','cancel'}
  if not changes or set(changes)-allowed:raise ValueError('Invalid analysis update')
  if isinstance(changes.get('summary'),dict):changes['summary']=json.dumps(changes['summary'],allow_nan=False)
  changes['updated']=now()
  with self.connect() as db:db.execute('UPDATE analyses SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',(*changes.values(),aid))
 def cancelled(self,aid):
  with self.connect() as db:r=db.execute('SELECT cancel FROM analyses WHERE id=?',(aid,)).fetchone()
  return not r or bool(r['cancel'])
 def delete(self,wid,aid):
  with self.connect() as db:db.execute('DELETE FROM analyses WHERE id=? AND workspace_id=?',(aid,wid))
 def audit_event(self,uid,action,aid=None):
  with self.connect() as db:db.execute('INSERT INTO audit(user_id,action,analysis_id,created) VALUES(?,?,?,?)',(uid,action,aid,now()))
 def events(self,uid):
  with self.connect() as db:rows=db.execute('SELECT action,analysis_id,created FROM audit WHERE user_id=? ORDER BY id DESC LIMIT 50',(uid,)).fetchall()
  return [dict(r) for r in rows]
 def close(self):pass
