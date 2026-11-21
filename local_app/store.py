import json,sqlite3,time,uuid
from pathlib import Path

def uid():return uuid.uuid4().hex

class Store:
    def __init__(self,root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,name TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY,name TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS recordings(id TEXT PRIMARY KEY,room_id TEXT,name TEXT,path TEXT UNIQUE,created REAL,linked INTEGER);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,room_id TEXT,profile_id TEXT,recording_id TEXT,kind TEXT,state TEXT,runtime TEXT,log TEXT,created REAL,ended REAL,error TEXT);
            CREATE TABLE IF NOT EXISTS maps(id TEXT PRIMARY KEY,room_id TEXT,session_id TEXT,origin TEXT,path TEXT,updated REAL,landmarks INTEGER,state TEXT,UNIQUE(session_id,origin));
            ''')
    def connect(self):
        db=sqlite3.connect(self.root/'library.sqlite3',timeout=10);db.row_factory=sqlite3.Row;return db
    def rows(self,sql,args=()):
        with self.connect() as db:return [dict(r) for r in db.execute(sql,args)]
    def one(self,table,key):
        if table not in {'profiles','rooms','recordings','sessions','maps'}:raise ValueError('Invalid collection')
        rows=self.rows(f'SELECT * FROM {table} WHERE id=?',(key,))
        if not rows:raise ValueError('Item not found')
        return rows[0]
    def profile(self,name):
        name=str(name).strip()
        if not 1<=len(name)<=60:raise ValueError('Enter a name (up to 60 characters).')
        rows=self.rows('SELECT * FROM profiles WHERE lower(name)=lower(?)',(name,))
        if rows:return rows[0]
        key=uid()
        with self.connect() as db:db.execute('INSERT INTO profiles VALUES(?,?,?)',(key,name,time.time()))
        return self.one('profiles',key)
    def room(self,name):
        name=str(name).strip()
        if not 1<=len(name)<=100:raise ValueError('Enter a room name (up to 100 characters).')
        key=uid();folder=self.root/'rooms'/key;folder.mkdir(parents=True)
        (folder/'room.json').write_text(json.dumps({'id':key,'name':name},indent=2))
        with self.connect() as db:db.execute('INSERT INTO rooms VALUES(?,?,?)',(key,name,time.time()))
        return self.one('rooms',key)
    def recording(self,room_id,path,linked=True):
        self.one('rooms',room_id);path=Path(path).resolve()
        existing=self.rows('SELECT * FROM recordings WHERE path=?',(str(path),))
        if existing:
            if existing[0]['room_id']!=room_id:raise ValueError('This recording already belongs to another room.')
            return existing[0]
        key=uid()
        with self.connect() as db:db.execute('INSERT INTO recordings VALUES(?,?,?,?,?,?)',(key,room_id,path.name,str(path),time.time(),int(linked)))
        refs=self.root/'rooms'/room_id/'recordings';refs.mkdir(exist_ok=True)
        (refs/(key+'.json')).write_text(json.dumps({'recording':str(path),'linked':linked},indent=2))
        return self.one('recordings',key)
    def update_session(self,key,**values):
        if not set(values)<={'state','ended','error'}:raise ValueError('Invalid session update')
        with self.connect() as db:db.execute('UPDATE sessions SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),key))
