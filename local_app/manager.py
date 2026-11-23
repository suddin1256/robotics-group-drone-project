import json,os,platform,signal,socket,subprocess,sys,threading,time
from pathlib import Path
from urllib.request import Request,urlopen
from .store import uid

ROOT=Path(__file__).resolve().parents[1]

def profile_settings(name):
    silicon=platform.system()=='Darwin' and platform.machine().lower() in {'arm64','aarch64'}
    first=name.casefold().split()[0] if name.strip() else ''
    legacy=first=='shadib' and platform.system()=='Darwin' and not silicon
    legacy=legacy and (Path.home()/'Documents/tello-ros2/pixi.toml').exists() and (Path.home()/'Documents/tello-slam/pixi.toml').exists()
    optimized=first in {'nahil','rian'} and silicon
    mapping_ready=(ROOT/'vision/models/mapping-ready.json').is_file()
    return {'reuse_existing':bool(legacy),'depth_model':'metric-indoor' if mapping_ready else 'depth-anything' if optimized else 'midas',
            'label':'Existing Intel Mac setup' if legacy else 'Apple Silicon / Depth Anything' if optimized else 'Portable setup / MiDaS',
            'note':'Profile preferences are checked against this computer. Profiles are local presets, not accounts.'}

class Manager:
    def __init__(self,store,dashboard_port=8082):
        self.store=store;self.port=dashboard_port;self.lock=threading.RLock();self.active=None;self.process=None
        self.closing=False;self.rebuild_process=None;self.last_rebuild=0
        self.pending_rooms=set();self.snapshot_versions={}
        self.preparation=None
        self.batch_process=None;self.batch_room=None
        with store.connect() as db:db.execute("UPDATE sessions SET state='interrupted',ended=?,error='App restarted; saved data retained.' WHERE state IN ('starting','running','stopping')",(time.time(),))
        self.thread=threading.Thread(target=self.monitor,daemon=True);self.thread.start()
    def state(self):
        with self.lock:
            if not self.active:return None
            row=self.store.one('sessions',self.active)
            row['recording']=self.store.one('recordings',row['recording_id']) if row.get('recording_id') else None
            row['dashboard_url']=f'http://127.0.0.1:{self.port}/';row['dashboard_ready']=False
            try:
                with urlopen(row['dashboard_url']+'control.json',timeout=1) as f:row['control']=json.load(f)
                row['dashboard_ready']=True
            except Exception:pass
            try:row['playback']=json.loads((Path(row['runtime'])/'live/playback.json').read_text())
            except (OSError,ValueError):pass
            try:row['log_tail']=Path(row['log']).read_text(errors='replace')[-4500:]
            except OSError:row['log_tail']=''
            return row
    def command(self,profile,kind,runtime,recording=None,destination=None,quick=False):
        settings=profile_settings(profile['name']);cmd=[sys.executable,str(ROOT/'start.py'),'--driver','community','--runtime-dir',str(runtime),'--port',str(self.port)]
        if settings['reuse_existing']:cmd+=['--reuse-existing']
        if kind in {'replay','demo'}:cmd+=['--domain-id','73']
        if quick:cmd+=['--no-slam']
        else:cmd+=['--vision','--depth-model',settings['depth_model']]
        if kind=='replay':
            cmd+=['--bag',str(recording)]
            if not quick:cmd+=['--slam-all-frames']
        elif kind=='demo':cmd+=['--demo','--no-slam'] if not quick else ['--demo']
        elif kind=='live':cmd+=['--enable-flight','--record','--record-dir',str(destination)]
        else:raise ValueError('Unknown session type')
        return cmd,settings
    def start(self,room_id,profile_id,kind,recording_id=None,ready=False,quick=False):
        with self.lock:
            if self.batch_process and self.batch_process.poll() is None:raise ValueError('Stop the background room build before starting playback or a live flight.')
            if self.preparation and self.preparation.poll() is None:raise ValueError('Wait for model preparation to finish before starting a session.')
            if self.active:raise ValueError('End the current session before starting another.')
            if room_id is not None:self.store.one('rooms',room_id)
            elif kind!='replay':raise ValueError('Choose a room for a new flight.')
            profile=self.store.one('profiles',profile_id)
            if kind=='live' and ready is not True:raise ValueError('Complete the Tello connection step first.')
            recording=None
            if kind=='replay':
                recording=self.store.one('recordings',recording_id)
                if recording['room_id']!=room_id:raise ValueError('Recording belongs to a different room.')
                if not (Path(recording['path'])/'metadata.yaml').is_file():raise ValueError('Recording is missing. Restore its linked folder.')
            # Refuse to replace another dashboard/source session.
            with socket.socket() as sock:
                try:sock.bind(('127.0.0.1',self.port))
                except OSError:raise ValueError('Another flight dashboard is running. Close that session first.')
            base=self.store.root/'rooms'/room_id if room_id else self.store.root/'previews'
            key=uid();folder=base/'sessions'/key;folder.mkdir(parents=True)
            runtime=folder/'runtime';log=folder/'launcher.log';destination=base/'flights'/('flight_'+time.strftime('%Y%m%d_%H%M%S')+'_'+key[:6])
            if kind=='live':destination.parent.mkdir(exist_ok=True)
            cmd,settings=self.command(profile,kind,runtime,recording['path'] if recording else None,destination,quick)
            with self.store.connect() as db:db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,room_id,profile_id,recording_id,kind,'starting',str(runtime),str(log),time.time(),None,None))
            handle=log.open('w');env=os.environ.copy();env['PATH']=os.pathsep.join([str(ROOT/'.tools'),str(Path.home()/'.pixi/bin'),env.get('PATH','')]);env['TMPDIR']=str(ROOT/'.tmp');env['PIXI_CACHE_DIR']=str(ROOT/'.cache/pixi')
            (ROOT/'.tmp').mkdir(exist_ok=True)
            env['TELLO_ARCHIVE_MAPPING']='1'
            try:self.process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
            except Exception as error:
                self.store.update_session(key,state='failed',ended=time.time(),error=str(error));raise
            finally:handle.close()
            self.active=key;self.destination=destination if kind=='live' else None
            (folder/'session.json').write_text(json.dumps({'command':cmd,'profile':settings,'kind':kind},indent=2))
            return self.state()
    def manage_recording(self,action,key,room_id=None,confirmation=None):
        from .recordings import permanently_delete
        with self.lock:
            row=self.store.one('recordings',key)
            if self.batch_process and self.batch_process.poll() is None:raise ValueError('Stop the room build before changing recordings.')
            if self.rebuild_process and self.rebuild_process.poll() is None:raise ValueError('The room map update is finishing. Try again shortly.')
            if self.active:
                session=self.store.one('sessions',self.active)
                if session['kind']=='live':raise ValueError('End the live flight before managing recordings.')
                if action=='delete' and session.get('recording_id')==key:raise ValueError('End playback before permanently deleting this recording.')
            old=row['room_id']
            if action=='assign':result=self.store.assign_recording(key,room_id)
            elif action=='delete':result=permanently_delete(self.store,key,confirmation)
            else:raise ValueError('Unknown recording action')
            for affected in {old,room_id if action=='assign' else None}:
                if affected:self.pending_rooms.add(affected)
            self.last_rebuild=time.monotonic() # Allow several library edits before rebuilding.
            return result
    def mapping_setup_state(self):
        ready=(ROOT/'vision/models/mapping-ready.json').exists()
        process=self.preparation
        result={'ready':ready,'state':'running' if process and process.poll() is None else 'failed' if process and process.returncode else 'ready' if ready else 'not prepared'}
        log=ROOT/'logs/mapping-setup.log'
        result['log']=log.read_text(errors='replace')[-3000:] if log.exists() else ''
        return result
    def prepare_mapping(self):
        with self.lock:
            if self.batch_process and self.batch_process.poll() is None:raise ValueError('Stop the room build before changing models.')
            if self.active:raise ValueError('End the current session before preparing models.')
            if self.preparation and self.preparation.poll() is None:return self.mapping_setup_state()
            python=ROOT/'vision/.venv/bin/python'
            if not python.exists():raise ValueError('Run the first-time laptop setup before preparing mapping models.')
            log=ROOT/'logs/mapping-setup.log';log.parent.mkdir(exist_ok=True)
            env=os.environ.copy();env['TMPDIR']=str(ROOT/'.tmp');env['PATH']=os.pathsep.join([str(ROOT/'.tools'),str(Path.home()/'.pixi/bin'),env.get('PATH','')]);env['PIXI_CACHE_DIR']=str(ROOT/'.cache/pixi')
            env.pop('HF_HUB_OFFLINE',None);env.pop('TRANSFORMERS_OFFLINE',None)
            with log.open('w') as stream:self.preparation=subprocess.Popen([str(python),str(ROOT/'scripts/setup_mapping.py')],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
            return self.mapping_setup_state()
    def room_build_state(self,room_id):
        path=self.store.root/'rooms'/room_id/'room-build.json'
        try:state=json.loads(path.read_text())
        except (OSError,ValueError):return None
        if state.get('state') in {'queued','running','stopping'} and not (self.batch_room==room_id and self.batch_process and self.batch_process.poll() is None):
            state.update(state='interrupted',stage='stopped; saved work retained')
        log=path.with_name('room-build.log')
        state['log']=log.read_text(errors='replace')[-4500:] if log.exists() else ''
        return state
    def start_room_build(self,room_id,profile_id,force=False):
        with self.lock:
            self.store.one('rooms',room_id);profile=self.store.one('profiles',profile_id)
            if self.active:raise ValueError('End the current flight/playback before building the room.')
            if self.batch_process and self.batch_process.poll() is None:raise ValueError('A room build is already running.')
            if self.preparation and self.preparation.poll() is None:raise ValueError('Wait for model preparation to finish.')
            if self.rebuild_process and self.rebuild_process.poll() is None:raise ValueError('The current map update is finishing; try again shortly.')
            if not self.mapping_setup_state()['ready']:raise ValueError('Prepare mapping models in the room library first.')
            if not self.store.rows('SELECT id FROM recordings WHERE room_id=?',(room_id,)):raise ValueError('Add recordings to this room first.')
            python=ROOT/'vision/.venv/bin/python';folder=self.store.root/'rooms'/room_id
            command=[str(python),str(ROOT/'scripts/build_room.py'),'--store',str(self.store.root),'--room',room_id,'--profile',profile_id]
            if profile_settings(profile['name'])['reuse_existing']:command+=['--reuse-existing']
            if force:command+=['--force']
            env=os.environ.copy();env['PATH']=os.pathsep.join([str(ROOT/'.tools'),str(Path.home()/'.pixi/bin'),env.get('PATH','')]);env['TMPDIR']=str(ROOT/'.tmp');env['PIXI_CACHE_DIR']=str(ROOT/'.cache/pixi');env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
            (folder/'room-build.json').write_text(json.dumps({'state':'queued','room_id':room_id,'stage':'starting','completed':0,'total':len(self.store.rows('SELECT id FROM recordings WHERE room_id=?',(room_id,)))}))
            with (folder/'room-build.log').open('w') as log:self.batch_process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.batch_room=room_id;return self.room_build_state(room_id)
    def cancel_room_build(self,room_id):
        with self.lock:
            if self.batch_room!=room_id or not self.batch_process or self.batch_process.poll() is not None:raise ValueError('No running build for this room.')
            os.killpg(self.batch_process.pid,signal.SIGINT)
    def request_land(self):
        with self.lock:
            if not self.active or self.store.one('sessions',self.active)['kind']!='live':raise ValueError('No live flight session.')
            data=json.dumps({'keys':[],'enabled':False,'action':'land'}).encode()
            try:
                with urlopen(Request(f'http://127.0.0.1:{self.port}/input',data=data,headers={'Content-Type':'application/json'}),timeout=2):pass
            except Exception:raise ValueError('Landing request could not reach the dashboard. Use the flight controls and confirm the drone has landed.')
    def stop(self,landed=False,shutdown=False):
        with self.lock:
            if not self.active:return
            row=self.store.one('sessions',self.active)
            if row['kind']=='live' and not shutdown:
                if landed is not True:raise ValueError('Confirm the drone is landed before ending the session.')
                status=self.state().get('control',{})
                if status.get('phase') not in {'grounded',None}:raise ValueError('Driver still reports flight/arming. Land first; keep the flight controls open.')
            if self.process and self.process.poll() is None:
                self.store.update_session(self.active,state='stopping');self.process.send_signal(signal.SIGINT)
    def snapshot(self,row):
        if row['room_id'] is None:return
        live=Path(row['runtime'])/'live'
        try:data=json.loads((live/'map.json').read_text())
        except (OSError,ValueError):return
        if not data.get('points'):return
        origin=str(data.get('map_origin','unknown'));maps=self.store.rows('SELECT * FROM maps WHERE session_id=? AND origin=?',(row['id'],origin));key=maps[0]['id'] if maps else uid()
        version=(row['id'],origin,data.get('timestamp'))
        if version in self.snapshot_versions:return
        self.snapshot_versions={v:True for v in self.snapshot_versions if v[0]!=row['id'] or v[1]!=origin};self.snapshot_versions[version]=True
        target=self.store.root/'rooms'/row['room_id']/'maps'/key;target.mkdir(parents=True,exist_ok=True)
        (target/'source.json').write_text(json.dumps({'live':str(live),'session_id':row['id']}))
        # Atomic versions preserve the previous map until a complete JSON is available.
        for name in ['map.json','floorplan.json','metric-telemetry.json']:
            try:
                payload=(live/name).read_bytes();json.loads(payload);tmp=target/(name+'.tmp');tmp.write_bytes(payload);tmp.replace(target/name)
            except (OSError,ValueError):pass
        with self.store.connect() as db:
            db.execute('INSERT INTO maps VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(session_id,origin) DO UPDATE SET updated=excluded.updated,landmarks=excluded.landmarks,state=excluded.state',
                (key,row['room_id'],row['id'],origin,str(target),time.time(),len(data['points']),data.get('state','unknown')))
        self.rebuild(row['room_id'])
    def rebuild(self,room_id,force=False):
        with self.lock:self._rebuild(room_id,force)
    def _rebuild(self,room_id,force=False):
        self.pending_rooms.add(room_id)
        if self.batch_process and self.batch_process.poll() is None:return
        if self.rebuild_process and self.rebuild_process.poll() is None:return
        if not force and time.monotonic()-self.last_rebuild<12:return
        python=ROOT/'vision/.venv/bin/python'
        if not python.exists():return
        self.pending_rooms.discard(room_id)
        folder=self.store.root/'rooms'/room_id;handle=(folder/'reconstruction.log').open('a')
        env=os.environ.copy();env.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
        self.rebuild_process=subprocess.Popen([str(python),str(ROOT/'scripts/rebuild_room_map.py'),'--room',str(folder)],cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT);handle.close();self.last_rebuild=time.monotonic()
    def finalize(self):
        row=self.store.one('sessions',self.active);self.snapshot(row)
        code=self.process.returncode
        self.store.update_session(self.active,state='finished' if code==0 else 'failed',ended=time.time(),error=None if code==0 else 'Session stopped with an error; see its log.')
        if self.destination and (self.destination/'metadata.yaml').exists():
            recording=self.store.recording(row['room_id'],self.destination,linked=False)
            # Associate live captures with their resulting bag so a later batch
            # rebuild can supersede them instead of double-counting one flight.
            with self.store.connect() as db:db.execute('UPDATE sessions SET recording_id=? WHERE id=?',(recording['id'],row['id']))
        self.active=None;self.process=None
        if row['room_id']:self.rebuild(row['room_id'],force=True)
    def monitor(self):
        while not self.closing:
            try:self.tick()
            except Exception as error:
                # A reconstruction failure must not stop flight-session supervision.
                if self.active:
                    try:
                        row=self.store.one('sessions',self.active)
                        with Path(row['log']).open('a') as log:log.write(f'\nRoom library update: {error}\n')
                    except Exception:pass
            time.sleep(2)
    def tick(self):
            with self.lock:
                if self.pending_rooms and (not self.rebuild_process or self.rebuild_process.poll() is not None) and time.monotonic()-self.last_rebuild>=12:
                    self.rebuild(next(iter(self.pending_rooms)))
                if self.active:
                    row=self.store.one('sessions',self.active);self.snapshot(row)
                    if self.process.poll() is not None:
                        self.finalize()
                    elif row['state']=='starting' and (Path(row['runtime'])/'live/telemetry.json').exists():self.store.update_session(row['id'],state='running')
    def close(self):
        if self.batch_process and self.batch_process.poll() is None:
            self.cancel_room_build(self.batch_room)
            try:self.batch_process.wait(timeout=20)
            except subprocess.TimeoutExpired:pass
        self.stop(shutdown=True)
        if self.process:
            try:self.process.wait(timeout=55)
            except subprocess.TimeoutExpired:pass
        with self.lock:
            if self.active and self.process.poll() is not None:self.finalize()
        self.closing=True;self.thread.join(timeout=3)
