import json, sqlite3, uuid, time
from pathlib import Path

class Store:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'files').mkdir(exist_ok=True)
        self.path=self.root/'state.sqlite3'
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,body TEXT NOT NULL,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,prompt_id TEXT,error TEXT,progress TEXT,outputs TEXT NOT NULL DEFAULT '[]');
            ''')
    def connect(self):
        c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row;return c
    def put(self,kind,body,id=None,replace=False):
        id=id or uuid.uuid4().hex
        with self.connect() as c:
            c.execute(('INSERT OR REPLACE' if replace else 'INSERT')+' INTO records VALUES(?,?,?)',(kind,id,json.dumps(body,ensure_ascii=False)))
        return dict(body,id=id)
    def get(self,kind,id):
        with self.connect() as c:r=c.execute('SELECT body FROM records WHERE kind=? AND id=?',(kind,id)).fetchone()
        return dict(json.loads(r['body']),id=id) if r else None
    def list(self,kind):
        with self.connect() as c:rs=c.execute('SELECT id,body FROM records WHERE kind=? ORDER BY rowid DESC',(kind,)).fetchall()
        return [dict(json.loads(r['body']),id=r['id']) for r in rs]
    def create_job(self,body):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM jobs WHERE idempotency_key=?',(body['idempotency_key'],)).fetchone()
            if old:
                if json.loads(old['body']) != body:raise ValueError('idempotency_key reused with different request')
                return self.decode(old)
            id=uuid.uuid4().hex;t=time.time()
            c.execute('INSERT INTO jobs(id,idempotency_key,body,state,created,updated) VALUES(?,?,?,?,?,?)',(id,body['idempotency_key'],json.dumps(body),'queued',t,t))
        return self.job(id)
    @staticmethod
    def decode(r):
        if not r:return None
        d=dict(r)
        for k in ('body','outputs','progress'):
            d[k]=json.loads(d[k]) if d[k] else None
        return d
    def job(self,id):
        with self.connect() as c:return self.decode(c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone())
    def jobs(self,states=None):
        with self.connect() as c:
            rs=c.execute('SELECT * FROM jobs '+('WHERE state IN ('+','.join('?' for _ in states)+') ' if states else '')+'ORDER BY created',states or []).fetchall()
        return [self.decode(r) for r in rs]
    def update_job(self,id,**changes):
        allowed={'state','prompt_id','error','progress','outputs'}
        if not set(changes)<=allowed:raise ValueError('Unknown job fields')
        for k in ('progress','outputs'):
            if k in changes:changes[k]=json.dumps(changes[k])
        changes['updated']=time.time()
        with self.connect() as c:c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',[*changes.values(),id])
    def append_outfit(self,character_id,outfit,name='',parent_id=None):
        """Append an immutable clothing version without replacing any old tags."""
        version=dict(outfit,name=name,parent_id=parent_id,character_id=character_id)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT body FROM records WHERE kind=? AND id=?',('character',character_id)).fetchone()
            if not row:raise LookupError('Unknown character')
            character=json.loads(row['body'])
            old=c.execute('SELECT body FROM records WHERE kind=? AND id=?',('outfit_version',character_id+':'+outfit['id'])).fetchone()
            if old:
                if json.loads(old['body'])!=version:raise ValueError('Outfit version ID already used; create a new version')
                return version
            if any(o['id']==outfit['id'] for o in character['outfits']):raise ValueError('Outfit ID already exists')
            if parent_id and not any(o['id']==parent_id for o in character['outfits']):raise LookupError('Unknown parent outfit')
            character['outfits'].append(outfit)
            c.execute('UPDATE records SET body=? WHERE kind=? AND id=?',(json.dumps(character,ensure_ascii=False),'character',character_id))
            c.execute('INSERT INTO records VALUES(?,?,?)',('outfit_version',character_id+':'+outfit['id'],json.dumps(version,ensure_ascii=False)))
        return version
