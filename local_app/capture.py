"""Shared snapshot writer for interactive sessions and background room jobs."""
import json,time
from pathlib import Path
from .store import uid

def capture_session(store,row):
    live=Path(row['runtime'])/'live'
    try:data=json.loads((live/'map.json').read_text())
    except (OSError,ValueError):return False
    if not data.get('points'):return False
    origin=str(data.get('map_origin','unknown'))
    matches=store.rows('SELECT * FROM maps WHERE session_id=? AND origin=?',(row['id'],origin))
    key=matches[0]['id'] if matches else uid();target=store.root/'rooms'/row['room_id']/'maps'/key;target.mkdir(parents=True,exist_ok=True)
    (target/'source.json').write_text(json.dumps({'live':str(live),'session_id':row['id'],'recording_id':row.get('recording_id'),'background_build':row['kind']=='build'}))
    for name in ['map.json','floorplan.json','metric-telemetry.json']:
        try:
            payload=(live/name).read_bytes();json.loads(payload);temporary=target/(name+'.tmp');temporary.write_bytes(payload);temporary.replace(target/name)
        except (OSError,ValueError):pass
    with store.connect() as db:db.execute('INSERT INTO maps VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(session_id,origin) DO UPDATE SET updated=excluded.updated,landmarks=excluded.landmarks,state=excluded.state',
        (key,row['room_id'],row['id'],origin,str(target),time.time(),len(data['points']),data.get('state','unknown')))
    return True
