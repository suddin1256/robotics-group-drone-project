"""Recording catalogue operations. Original files move only on permanent deletion."""
import json,re,shutil,time
from pathlib import Path

def read(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value));temp.replace(path)
def container(store,room_id):return store.root/'rooms'/room_id if room_id else store.root/'unassigned'
def owned(store,path):
    p=Path(path)
    if p.is_symlink() or not p.resolve().is_relative_to(store.root) or p.resolve()==store.root:raise ValueError('Saved processing path is outside the app library; refusing file operation.')
    return p
def invalidate(store,room_id):
    if not room_id:return
    folder=container(store,room_id)
    # Aggregates may contain this recording. Clear them immediately, then the
    # manager rebuilds from remaining captures; never show removed evidence.
    for name in ['room-map.json','room-mesh.json','occupancy.json','reconstruction-status.json']:
        write(folder/name,{'state':'waiting','points':[],'vertices':[],'triangles':[],'sessions':[],'planning_ready':False,'note':'Recording assignments changed; rebuilding room.'})
    for name in ['room-mesh.ply','room-surfaces.ply','room.ot','occupancy-rays.txt']:(folder/name).unlink(missing_ok=True)

def inventory(store):
    rows=store.rows('SELECT recordings.*,rooms.name AS room_name FROM recordings LEFT JOIN rooms ON rooms.id=recordings.room_id ORDER BY recordings.name DESC')
    for row in rows:
        folder=Path(row['path']);row.update(missing=not folder.is_dir(),incomplete=not (folder/'metadata.yaml').is_file(),size_bytes=0,duration_seconds=None)
        try:
            row['size_bytes']=sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
            text=(folder/'metadata.yaml').read_text();match=re.search(r'duration:\s*\n\s*nanoseconds:\s*(\d+)',text)
            if match:row['duration_seconds']=int(match.group(1))/1e9
        except (OSError,ValueError,UnicodeError,OverflowError):pass
    return rows

def scan(store,folder=None):
    folder=Path(folder) if folder else Path.home()/'Documents/tello-recordings'
    count=0
    for path in sorted(folder.glob('*')):
        if path.is_dir() and not path.is_symlink() and ((path/'metadata.yaml').is_file() or any(path.glob('*.mcap'))):
            if not store.rows('SELECT id FROM recordings WHERE path=?',(str(path.resolve()),)):
                store.recording(None,path);count+=1
    return count

def assign(store,key,room_id):
    row=store.one('recordings',key);old=row['room_id']
    if room_id is not None:store.one('rooms',room_id)
    if old==room_id:return row
    captures=store.rows('SELECT maps.* FROM maps JOIN sessions ON sessions.id=maps.session_id WHERE sessions.recording_id=?',(key,))
    moves=[]
    try:
        for capture in captures:
            source=owned(store,capture['path']);target=container(store,room_id)/'maps'/capture['id']
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():raise ValueError('Saved capture destination already exists; no files overwritten.')
            if source.exists():shutil.move(str(source),str(target));moves.append((source,target))
        with store.connect() as db:
            db.execute('UPDATE recordings SET room_id=? WHERE id=?',(room_id,key))
            db.execute('UPDATE sessions SET room_id=? WHERE recording_id=?',(room_id,key))
            for capture in captures:db.execute('UPDATE maps SET room_id=?,path=? WHERE id=?',(room_id,str(container(store,room_id)/'maps'/capture['id']),capture['id']))
    except Exception:
        for source,target in reversed(moves):source.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(target),str(source))
        raise
    (container(store,old)/'recordings'/(key+'.json')).unlink(missing_ok=True)
    write(container(store,room_id)/'recordings'/(key+'.json'),{'recording':row['path'],'linked':bool(row['linked'])})
    oldcache=read(container(store,old)/'build-cache.json',{});transfer={k:v for k,v in oldcache.items() if k.startswith(key+':')}
    if transfer:
        write(container(store,old)/'build-cache.json',{k:v for k,v in oldcache.items() if k not in transfer})
        newcache=read(container(store,room_id)/'build-cache.json',{});newcache.update(transfer);write(container(store,room_id)/'build-cache.json',newcache)
    ids={c['id'] for c in captures};superseded=set(read(container(store,old)/'superseded-captures.json',[]))&ids
    if superseded:write(container(store,room_id)/'superseded-captures.json',sorted(set(read(container(store,room_id)/'superseded-captures.json',[]))|superseded))
    invalidate(store,old);invalidate(store,room_id)
    return store.one('recordings',key)

def permanently_delete(store,key,confirmation):
    row=store.one('recordings',key)
    if confirmation!=row['name']:raise ValueError('Type the recording name exactly to confirm permanent deletion.')
    bag=Path(row['path'])
    if bag.exists():
        if bag.is_symlink() or bag.resolve()!=bag or store.root.is_relative_to(bag):raise ValueError('Recording path changed or contains the app library; refusing deletion.')
        if not any(bag.glob('*.mcap')) and any(p.name!='metadata.yaml' for p in bag.iterdir()):raise ValueError('Folder does not look like a recording; refusing deletion.')
    sessions=store.rows('SELECT * FROM sessions WHERE recording_id=?',(key,))
    captures=store.rows('SELECT maps.* FROM maps JOIN sessions ON sessions.id=maps.session_id WHERE sessions.recording_id=?',(key,))
    targets=[]
    for session in sessions:
        runtime=owned(store,session['runtime'])
        if runtime.name!='runtime' or runtime.parent.name!=session['id']:raise ValueError('Unexpected processing folder; refusing deletion.')
        targets.append(runtime.parent)
    targets.extend(owned(store,c['path']) for c in captures)
    # Validation above happens before removing any original or derived file.
    if bag.exists():shutil.rmtree(bag)
    for target in targets:
        if target.exists():shutil.rmtree(target)
    with store.connect() as db:
        for session in sessions:db.execute('DELETE FROM maps WHERE session_id=?',(session['id'],))
        db.execute('DELETE FROM sessions WHERE recording_id=?',(key,));db.execute('DELETE FROM recordings WHERE id=?',(key,))
    for folder in [store.root/'unassigned',*(store.root/'rooms').glob('*')]:
        (folder/'recordings'/(key+'.json')).unlink(missing_ok=True)
        cache=read(folder/'build-cache.json',{})
        if any(k.startswith(key+':') for k in cache):write(folder/'build-cache.json',{k:v for k,v in cache.items() if not k.startswith(key+':')})
    invalidate(store,row['room_id'])
    return {'deleted':True,'recording_id':key}
