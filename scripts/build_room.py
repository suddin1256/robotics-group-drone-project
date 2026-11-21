"""Headless room job: bags -> all-image SLAM -> keyframe models -> shared room mesh.

No dashboard, ROS publishers, drone connection, or flight commands are started.
"""
import argparse,hashlib,json,os,shutil,signal,struct,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vision')]
from local_app.store import Store,uid
from local_app.capture import capture_session
from project_config import CORE,pixi_executable

STOP=False
class Cancelled(Exception):pass
def stop(*_):
    global STOP
    STOP=True
def atomic(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,allow_nan=False));temp.replace(path)
def read(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default
def fingerprint(bag):
    digest=hashlib.sha256()
    for path in sorted(bag.glob('*')):
        if path.is_file():digest.update(f'{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'.encode())
    for name in ['scripts/build_room.py','ros/extract_mapping_bag.py','slam/src/tello_live_slam/main.cc','slam/assets/tello_320_dense.yaml','vision/room_models.py','vision/dense_reconstruction.py','vision/models/mapping-ready.json']:
        path=ROOT/name
        if path.exists():digest.update(path.read_bytes())
    return digest.hexdigest()
def cache_complete(store,session):
    rows=store.rows('SELECT * FROM sessions WHERE id=? AND state=?',(session,'finished'))
    if not rows:return False
    live=Path(rows[0]['runtime'])/'live'
    return (live/'frames-index.json').is_file() and (live/'map.json').is_file()

def child(command,cwd,env,progress=None):
    process=subprocess.Popen(list(map(str,command)),cwd=cwd,env=env)
    try:
        while process.poll() is None:
            if STOP:raise Cancelled()
            if progress:progress()
            time.sleep(.3)
        if STOP:raise Cancelled()
        if process.returncode:raise RuntimeError(f'Processing step exited with code {process.returncode}; see build log.')
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:process.wait(timeout=4)
                except subprocess.TimeoutExpired:process.kill();process.wait()

def model_keyframes(live,maps,update):
    import cv2,numpy as np,torch
    from room_models import IndoorDepth,RoomStructure,doorway_candidates
    from ultralytics import YOLO
    from stage_worker import masks_json
    torch.set_num_threads(2);cv2.setNumThreads(1)
    depth=IndoorDepth();structure=RoomStructure();yolo=YOLO(str(ROOT/'vision/models/yolo11n-seg.pt'))
    index={round(item['stamp']*1e6):item for item in read(live/'frames-index.json',[])}
    stamps=sorted({round(stamp*1e6) for data in maps for stamp in data.get('camera_times',[])})
    for folder in ['depth-frames','depth-detections','structure-frames']:(live/folder).mkdir(exist_ok=True)
    processed=0
    with (live/'slam-input.bin').open('rb') as stream:
        for number,key in enumerate(stamps):
            if STOP:raise Cancelled()
            item=next((index[key+delta] for delta in [0,-1,1,-2,2] if key+delta in index),None)
            if item is None:continue
            stream.seek(item['offset']);stamp,w,h=struct.unpack('<dII',stream.read(16))
            pixels=stream.read(w*h*3)
            if (w,h)!=(320,240) or len(pixels)!=w*h*3:raise ValueError('Incomplete extracted image packet')
            frame=np.frombuffer(pixels,np.uint8).reshape(h,w,3).copy();name=str(round(stamp*1e6))
            metric=depth.predict(frame);labels,confidence=structure.predict(frame)
            semantic=yolo.predict(frame,imgsz=320,conf=.25,device=depth.device,verbose=False)[0]
            inverse=np.divide(1.,metric,out=np.zeros_like(metric),where=metric>.05)
            target=live/'depth-frames'/(name+'.npz');temp=target.with_suffix('.tmp')
            with temp.open('wb') as output:np.savez_compressed(output,depth=inverse,metric_depth=metric,rgb=frame,labels=labels,confidence=confidence,source_stamp=stamp)
            temp.replace(target)
            atomic(live/'depth-detections'/(name+'.json'),{'source_stamp':stamp,'objects':masks_json(semantic,yolo.names)})
            atomic(live/'structure-frames'/(name+'.json'),{'source_stamp':stamp,'doors':doorway_candidates(frame,labels,confidence,metric)})
            processed+=1;update(stage='depth and room structure',keyframes_done=processed,keyframes_total=len(stamps),frame=number+1)
    return processed

def run(args):
    store=Store(args.store);room=store.one('rooms',args.room);store.one('profiles',args.profile)
    folder=store.root/'rooms'/room['id'];status_path=folder/'room-build.json';cache_path=folder/'build-cache.json'
    recordings=store.rows('SELECT * FROM recordings WHERE room_id=? ORDER BY created',(room['id'],))
    state={'id':uid(),'room_id':room['id'],'state':'running','stage':'preparing','total':len(recordings),'completed':0,'cached':0,'failures':[], 'started':time.time(),'flight_enabled':False}
    def update(**values):state.update(values,updated=time.time());atomic(status_path,state)
    update();cache=read(cache_path,{})
    env=os.environ.copy();env.update(TELLO_ARCHIVE_MAPPING='1',TELLO_SLAM_OFFLINE_JOB='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1')
    env['HF_HOME']=str(ROOT/'vision/models/huggingface');env['YOLO_CONFIG_DIR']=str(ROOT/'vision/models/ultralytics-config');env['ULTRALYTICS_AUTOINSTALL']='false';env['MPLCONFIGDIR']=str(ROOT/'vision/models/matplotlib')
    os.environ.update(env)
    pixi=pixi_executable() or 'pixi'
    manifest=Path.home()/'Documents/tello-ros2/pixi.toml' if args.reuse_existing else CORE
    slam_manifest=Path.home()/'Documents/tello-slam/pixi.toml' if args.reuse_existing else ROOT/'environments/slam/pixi.toml'
    binary=ROOT/('build/adapter-legacy/tello_live_slam' if args.reuse_existing else 'build/live/tello_live_slam')
    vocabulary=Path.home()/'Documents/tello-slam/assets/orb_vocab.fbow' if args.reuse_existing else ROOT/'slam/assets/orb_vocab.fbow'
    current=None
    try:
        if not recordings:raise ValueError('Add recordings to this room first')
        if not (ROOT/'vision/models/mapping-ready.json').exists():raise ValueError('Prepare mapping models in the library first')
        build=[sys.executable,ROOT/'scripts/build_slam_adapter.py']+(['--reuse-existing'] if args.reuse_existing else [])
        child(build,ROOT,env)
        if not vocabulary.exists():raise ValueError('Missing SLAM vocabulary; run laptop setup first')
        for number,recording in enumerate(recordings):
            if STOP:raise Cancelled()
            update(recording=recording['name'],recording_index=number+1,keyframes_done=0,keyframes_total=0,images_done=0,stage='checking saved work')
            bag=Path(recording['path']);key=recording['id']+':'+fingerprint(bag)
            saved=cache.get(key)
            if not args.force and saved and cache_complete(store,saved):
                state['cached']+=1;update(completed=number+1);continue
            session=uid();runtime=folder/'sessions'/session/'runtime';live=runtime/'live';assets=runtime/'assets';live.mkdir(parents=True);assets.mkdir()
            log=runtime.parent/'build.log';log.write_text('Background processing; detailed output in room build log.\n')
            with store.connect() as db:db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(session,room['id'],args.profile,recording['id'],'build','running',str(runtime),str(log),time.time(),None,None))
            current=store.one('sessions',session)
            try:
                if not (bag/'metadata.yaml').exists():raise ValueError('Linked recording folder is missing')
                shutil.copy2(ROOT/'slam/assets/tello_320_dense.yaml',assets/'tello_320_dense.yaml')
                try:os.link(vocabulary,assets/'orb_vocab.fbow')
                except OSError:shutil.copy2(vocabulary,assets/'orb_vocab.fbow')
                update(stage='reading recording')
                child([pixi,'run','--manifest-path',manifest,'python',ROOT/'ros/extract_mapping_bag.py',bag,live],ROOT,env,
                    lambda:update(images_done=(read(live/'extraction-progress.json',{}) or {}).get('images',0)))
                update(stage='locating cameras with SLAM',images_total=len(read(live/'frames-index.json',[])))
                last_snapshot=[None]
                def slam_progress():
                    progress=read(live/'slam-status.json',{}) or {};update(images_done=progress.get('processed_frames',0))
                    data=read(live/'map.json',{}) or {}
                    if data.get('timestamp')!=last_snapshot[0]:capture_session(store,current);last_snapshot[0]=data.get('timestamp')
                child([pixi,'run','--manifest-path',slam_manifest,binary,'--ordered-input','live/slam-input.bin'],runtime,env,slam_progress)
                final_map=read(live/'map.json',{}) or {}
                if final_map.get('processed_frames')!=state['images_total']:raise ValueError('SLAM stopped before processing all extracted images')
                update(images_done=final_map['processed_frames'])
                capture_session(store,current)
                captures=store.rows('SELECT * FROM maps WHERE session_id=?',(session,));maps=[read(Path(c['path'])/'map.json',{}) for c in captures]
                update(stage='loading depth and structure models')
                count=model_keyframes(live,maps,update) if captures else 0
                store.update_session(session,state='finished',ended=time.time(),error=None if captures else 'SLAM found no usable map; recording retained.')
                if not captures:state['failures'].append({'recording':recording['name'],'error':'No usable SLAM map; use reprocess to retry after improving the recording or settings.'})
                cache[key]=session;atomic(cache_path,cache)
                # Preserve prior captures on disk, but exclude older processing of
                # this same recording from the new room fusion (no duplicate votes).
                exclusions=read(folder/'superseded-captures.json',[])
                older=store.rows('SELECT maps.id FROM maps JOIN sessions ON sessions.id=maps.session_id WHERE sessions.recording_id=? AND sessions.id!=?',(recording['id'],session))
                if captures:atomic(folder/'superseded-captures.json',sorted(set(exclusions)|{r['id'] for r in older}))
                # Raw bags remain unchanged; derived keyframe packets are retained.
                if count:(live/'slam-input.bin').unlink(missing_ok=True)
                update(completed=number+1)
            except Cancelled:
                store.update_session(session,state='interrupted',ended=time.time(),error='Room build cancelled; recording unchanged.')
                raise
            except Exception as error:
                store.update_session(session,state='failed',ended=time.time(),error=str(error));state['failures'].append({'recording':recording['name'],'error':str(error)});update(completed=number+1)
            finally:current=None
        update(stage='aligning recordings and building room surfaces')
        child([sys.executable,ROOT/'scripts/rebuild_room_map.py','--room',folder],ROOT,env)
        result=read(folder/'room-map.json',{}) or {}
        update(state='finished' if not state['failures'] else 'finished with warnings',stage='saved',ended=time.time(),aligned_maps=result.get('aligned_maps',0),separate_maps=result.get('separate_maps',0),integrated_frames=result.get('dense',{}).get('integrated_frames',0))
    except Cancelled:
        if current:store.update_session(current['id'],state='interrupted',ended=time.time(),error='Room build cancelled; source recording unchanged.')
        update(state='cancelled',stage='stopped',ended=time.time())
    except Exception as error:
        update(state='failed',stage='stopped',error=str(error),ended=time.time());raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--store',type=Path,required=True);parser.add_argument('--room',required=True);parser.add_argument('--profile',required=True);parser.add_argument('--reuse-existing',action='store_true');parser.add_argument('--force',action='store_true');args=parser.parse_args()
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop);run(args)
