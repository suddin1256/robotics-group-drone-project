import json,mimetypes,secrets,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from .store import Store
from .manager import Manager,ROOT,profile_settings

WEB=Path(__file__).with_name('web')

def create_server(port=8000,data_dir=None,dashboard_port=8082):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    server.token=secrets.token_urlsafe(32)
    server.store=Store(data_dir or ROOT/'.local/room_app');server.manager=Manager(server.store,dashboard_port)
    return server

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,value,status=200):
        body=json.dumps(value,allow_nan=False).encode();self.send_bytes(body,'application/json',status)
    def send_bytes(self,body,kind,status=200):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def host_ok(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def do_GET(self):
        if not self.host_ok():self.respond({'error':'Local host required'},403);return
        path=urlparse(self.path).path;store=self.server.store
        try:
            if path=='/api/state':
                profiles=store.rows('SELECT * FROM profiles ORDER BY created')
                for p in profiles:p['settings']=profile_settings(p['name'])
                rooms=store.rows('SELECT rooms.*, (SELECT count(*) FROM recordings WHERE room_id=rooms.id) AS flights,(SELECT count(*) FROM maps WHERE room_id=rooms.id) AS maps FROM rooms ORDER BY created DESC')
                self.respond({'profiles':profiles,'rooms':rooms,'active':self.server.manager.state(),'storage':str(store.root),'token':self.server.token});return
            if path=='/api/discover':
                found=[];folder=Path.home()/'Documents/tello-recordings'
                for p in sorted(folder.glob('*'),reverse=True):
                    if p.is_dir() and (p/'metadata.yaml').is_file():found.append({'name':p.name,'path':str(p.resolve())})
                self.respond(found);return
            parts=path.strip('/').split('/')
            if len(parts)==3 and parts[:2]==['api','rooms']:
                room=store.one('rooms',parts[2]);room['recordings']=store.rows('SELECT * FROM recordings WHERE room_id=? ORDER BY created DESC',(room['id'],));room['sessions']=store.rows('SELECT * FROM sessions WHERE room_id=? ORDER BY created DESC',(room['id'],));room['maps']=store.rows('SELECT * FROM maps WHERE room_id=? ORDER BY updated DESC',(room['id'],));self.respond(room);return
            if len(parts)==4 and parts[:2]==['api','room-map']:
                store.one('rooms',parts[2]);name=parts[3]
                if name not in {'room-map.json','reconstruction.log'}:raise ValueError('Unknown artifact')
                f=store.root/'rooms'/parts[2]/name
                if not f.exists():self.respond({'state':'waiting','points':[],'sessions':[]});return
                self.send_bytes(f.read_bytes(),'application/json' if name.endswith('.json') else 'text/plain');return
            if len(parts)==4 and parts[:2]==['api','map']:
                item=store.one('maps',parts[2]);name=parts[3]
                if name not in {'map.json','floorplan.json'}:raise ValueError('Unknown artifact')
                f=Path(item['path'])/name;self.send_bytes(f.read_bytes(),'application/json');return
            if len(parts)==3 and parts[:2]==['api','log']:
                row=store.one('sessions',parts[2]);self.respond({'log':Path(row['log']).read_text(errors='replace')[-14000:]});return
            if path in {'/','/app.js','/app.css'}:
                f=WEB/('index.html' if path=='/' else path[1:]);body=f.read_bytes()
                if path=='/':body=body.replace(b'__APP_TOKEN__',self.server.token.encode())
                self.send_bytes(body,mimetypes.guess_type(str(f))[0] or 'text/plain');return
            self.respond({'error':'Not found'},404)
        except (ValueError,OSError) as error:self.respond({'error':str(error)},400)
    def do_POST(self):
        if not self.host_ok() or self.headers.get('X-App-Token')!=self.server.token:
            self.respond({'error':'Reload the local app before making changes.'},403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=12000:raise ValueError('Invalid request size')
            d=json.loads(self.rfile.read(length));path=urlparse(self.path).path;store=self.server.store;manager=self.server.manager
            if path=='/api/profiles':result=store.profile(d.get('name',''))
            elif path=='/api/rooms':result=store.room(d.get('name',''))
            elif path=='/api/import':
                allowed={str(p.resolve()) for p in (Path.home()/'Documents/tello-recordings').glob('*') if (p/'metadata.yaml').is_file()}
                if d.get('path') not in allowed:raise ValueError('Choose a recording from the discovered list.')
                result=store.recording(d['room_id'],d['path'])
            elif path=='/api/start':result=manager.start(d['room_id'],d['profile_id'],d['kind'],d.get('recording_id'),d.get('ready'),d.get('quick') is True)
            elif path=='/api/stop':manager.stop(d.get('landed') is True);result={'ok':True}
            elif path=='/api/land':manager.request_land();result={'requested':True}
            elif path=='/api/rebuild':store.one('rooms',d['room_id']);manager.rebuild(d['room_id'],force=True);result={'requested':True}
            else:raise ValueError('Unknown action')
            self.respond(result)
        except (ValueError,KeyError,TypeError,OSError) as error:self.respond({'error':str(error)},400)
