"""Experimental telemetry-led semantic surface map. No navigation/flight commands."""
import json
import os
from pathlib import Path
import signal
import time
from collections import Counter
import cv2
import numpy as np
from fusion_geometry import fit_similarity,fit_inverse_depth,native_sample,orientation_alignment

K=np.array([[308.1441842,0,152.73032262],[0,310.03603888,139.18496426],[0,0,1.]])
D=np.array([.05784031,-.40185596,.01793044,-.00400204,.82094307])

def load_new(folder,cache,pattern='*.json',limit=4096):
    paths=sorted(folder.glob(pattern))[-limit:]
    keep={p.stem for p in paths}
    for old in set(cache)-keep:cache.pop(old,None)
    for path in paths:
        if path.stem in cache:continue
        try:cache[path.stem]=json.loads(path.read_text())
        except (FileNotFoundError,json.JSONDecodeError):pass

def lookup(cache,stamp):
    key=round(stamp*1e6)
    for delta in [0,-1,1,-2,2]:
        item=cache.get(str(key+delta))
        if item is None:continue
        actual=item.get('source_stamp',item.get('image_stamp_ns',0)/1e9)
        if abs(actual-stamp)<=.000002:return item
    return None

def calibrate(data,metadata):
    source=[];target=[];rotations=[];visual=[]
    for p,stamp,pose in zip(data.get('cameras',[]),data.get('camera_times',[]),data.get('camera_poses',[])):
        meta=lookup(metadata,stamp)
        sample=native_sample(meta) if meta else None
        if sample is None or not sample['airborne']:continue
        source.append(p);target.append(sample['position'])
        rotations.append(sample['rotation']);visual.append(np.asarray(pose)[:3,:3])
    fit=fit_similarity(source,target)
    if fit is None:return None,None,len(source)
    good=[i for i,ok in enumerate(fit['inliers']) if ok and rotations[i] is not None]
    orientation=orientation_alignment([rotations[i] for i in good],[visual[i] for i in good],fit['rotation'])
    return fit,orientation,len(source)

def refined_pose(observation,coordinates):
    pose=np.asarray(observation.get('camera_to_world'),float)
    if pose.shape!=(4,4) or not np.isfinite(pose).all():return None
    features=[f for f in observation['features'] if f[0] in coordinates]
    if len(features)>=8:
        points=np.array([coordinates[f[0]] for f in features],np.float64)
        uv=np.array([f[1:3] for f in features],np.float64)
        ok,rvec,tvec,inliers=cv2.solvePnPRansac(points,uv,K,D,iterationsCount=60,reprojectionError=3.,flags=cv2.SOLVEPNP_EPNP)
        if ok and inliers is not None and len(inliers)>=8:
            r=cv2.Rodrigues(rvec)[0]
            pose=np.eye(4);pose[:3,:3]=r.T;pose[:3,3]=-r.T@tvec.flatten()
    return pose

def frame_pose(observation,meta,coordinates,fit,orientation):
    if fit.get("visual_only"):
        pose=refined_pose(observation,coordinates)
        if pose is None:return None,"missing visual pose"
        return {"visual":pose,"position":pose[:3,3],"rotation":pose[:3,:3],"imu_used":False},None
    sample=native_sample(meta) if meta else None
    if sample is None:return None,'missing/stale motion'
    pose=refined_pose(observation,coordinates)
    if pose is None:return None,'missing visual pose'
    predicted=fit['scale']*fit['rotation']@pose[:3,3]+fit['translation']
    if np.linalg.norm(predicted-sample['position'])>max(3*fit['error'],.3*fit['spread']):
        return None,'motion/vision disagreement'
    r=fit['rotation']@pose[:3,:3];imu_used=False
    if orientation is not None and sample['rotation'] is not None:
        q=sample['rotation'].T if orientation['transpose'] else sample['rotation']
        candidate=q@orientation['offset']
        error=np.arccos(np.clip((np.trace(candidate.T@r)-1)/2,-1,1))
        if error<np.deg2rad(25):r=candidate;imu_used=True
    return {'visual':pose,'position':sample['position'],'rotation':r,'imu_used':imu_used},None

def inside_mask(uv,polygon):
    contour=np.asarray(polygon,np.float32)
    return np.array([cv2.pointPolygonTest(contour,(float(u),float(v)),False)>=0 for u,v in uv])

def frame_geometry(observation,detection,depth,meta,coordinates,fit,orientation):
    if abs(observation['source_stamp']-detection['source_stamp'])>.000002:
        return [],[],{'rejected':'different image frames'}
    if not meta or abs(meta.get('image_stamp_ns',0)/1e9-observation['source_stamp'])>.000002:
        return [],[],{'rejected':'different telemetry frame'}
    camera,reason=frame_pose(observation,meta,coordinates,fit,orientation)
    if camera is None:return [],[],{'rejected':reason}
    features=[f for f in observation['features'] if f[0] in coordinates]
    uv=np.array([f[1:3] for f in features],float).reshape(-1,2)
    visual_points=np.array([coordinates[f[0]] for f in features],float).reshape(-1,3)
    pose=camera['visual'];relative=(visual_points-pose[:3,3])@pose[:3,:3]
    native_points=camera['position']+fit['scale']*relative@camera['rotation'].T
    depth_uv=np.empty((0,2));depth_points=np.empty((0,3));depth_fit=None
    if depth is not None and len(features)>=16:
        xs=np.clip(np.rint(uv[:,0]).astype(int),0,319);ys=np.clip(np.rint(uv[:,1]).astype(int),0,239)
        depth_fit=fit_inverse_depth(depth[ys,xs],relative[:,2])
        if depth_fit:
            yy,xx=np.mgrid[4:236:8,4:316:8];depth_uv=np.column_stack([xx.ravel(),yy.ravel()]).astype(float)
            signal=depth[yy.ravel(),xx.ravel()]
            inverse=depth_fit['a']*signal+depth_fit['b']
            z=np.divide(1.,inverse,out=np.full_like(inverse,np.nan),where=inverse>0)
            good=np.isfinite(z)&(signal>=depth_fit['min_signal'])&(signal<=depth_fit['max_signal'])&(z>=depth_fit['min_z'])&(z<=depth_fit['max_z'])
            depth_uv=depth_uv[good];z=z[good]
            rays=cv2.undistortPoints(depth_uv.reshape(-1,1,2),K,D).reshape(-1,2) if len(depth_uv) else np.empty((0,2))
            camera_points=np.column_stack([rays,np.ones(len(rays))])*z[:,None]
            depth_points=camera['position']+fit['scale']*camera_points@camera['rotation'].T
    candidates=[];human=np.zeros(len(depth_uv),bool)
    for item in detection['objects']:
        if len(item['polygon'])<3:continue
        selected=inside_mask(uv,item['polygon']) if len(uv) else np.zeros(0,bool)
        dense=inside_mask(depth_uv,item['polygon']) if len(depth_uv) else np.zeros(0,bool)
        if item['label']=='person':human|=dense;continue
        ids={features[i][0] for i in np.flatnonzero(selected)}
        if len(ids)<6 and dense.sum()<12:continue
        points=np.concatenate([native_points[selected],depth_points[dense]])
        candidates.append({'label':item['label'],'ids':ids,'points':points,
                           'stamp':observation['source_stamp'],'depth':bool(dense.any()),'imu':camera['imu_used']})
    return candidates,depth_points[~human],{'depth_fit':depth_fit,'imu_used':camera['imu_used']}

def object_map(candidates):
    tracks=[]
    for c in candidates:
        lo,hi=np.quantile(c['points'],[.1,.9],axis=0);center=(lo+hi)/2
        match=None
        for track in tracks:
            if track['label']!=c['label']:continue
            common=len(track['ids']&c['ids'])
            overlap=np.maximum(0,np.minimum(hi[:2],track['max'][:2])-np.maximum(lo[:2],track['min'][:2]))
            area=min(np.prod(np.maximum(hi[:2]-lo[:2],1e-9)),np.prod(np.maximum(track['max'][:2]-track['min'][:2],1e-9)))
            if common>=3 or np.prod(overlap)/area>.35:match=track;break
        if match is None:
            tracks.append({'label':c['label'],'ids':set(c['ids']),'points':c['points'],
                           'stamps':{c['stamp']},'depth':c['depth'],'imu':c['imu'],'min':lo,'max':hi})
        else:
            match['ids']|=c['ids'];match['stamps'].add(c['stamp']);match['depth']|=c['depth'];match['imu']|=c['imu']
            points=np.concatenate([match['points'],c['points']]);step=max(1,int(np.ceil(len(points)/1500)))
            match['points']=points[::step];match['min'],match['max']=np.quantile(match['points'],[.1,.9],axis=0)
    return [{'id':i,'label':t['label'],'min':t['min'].tolist(),'max':t['max'].tolist(),
             'support':len(t['ids']),'observations':len(t['stamps']),'tentative':True,
             'sources':['telemetry','YOLO','SLAM']+(['relative depth'] if t['depth'] else [])+(['IMU orientation'] if t['imu'] else [])}
            for i,t in enumerate(tracks)]

def run():
    folder=Path(os.environ['TELLO_RUNTIME_DIR']);stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    metadata={};detections={};observations={};depth_detections={};depth_cache={}
    while not stopping:
        began=time.monotonic()
        try:
            data=json.loads((folder/'map.json').read_text())
            load_new(folder/'frame-telemetry',metadata)
            load_new(folder/'detections',detections,limit=2048)
            load_new(folder/'observations',observations,limit=2048)
            load_new(folder/'depth-detections',depth_detections,limit=128)
            paths=sorted((folder/'depth-frames').glob('*.npz'))[-64:]
            keep={p.stem for p in paths}
            for key in set(depth_cache)-keep:depth_cache.pop(key,None)
            for path in paths:
                if path.stem not in depth_cache:
                    with np.load(path,allow_pickle=False) as pack:depth_cache[path.stem]=pack['depth'].copy()
            fit,orientation,pairs=calibrate(data,metadata)
            path=[];last_count=None;current=None;pose_stamp=None;latest_stamp=None
            for key,meta in sorted(metadata.items()):
                latest_stamp=meta['image_stamp_ns']/1e9
                sample=native_sample(meta)
                if sample is None:continue
                current=sample['position'].tolist()
                pose_stamp=meta['image_stamp_ns']/1e9
                if sample['airborne'] and sample['count']!=last_count:
                    path.append(current);last_count=sample['count']
            objects=[];surfaces=[];candidates=[];reasons=Counter();used_depth=used_imu=matched=0
            transformed=[]
            aligned=fit is not None
            geometry_fit=fit if aligned else {"scale":1.,"rotation":np.eye(3),"translation":np.zeros(3),"visual_only":True}
            if len(data.get("points",[])):
                points=np.asarray(data['points'],float).reshape(-1,3)
                transformed=(geometry_fit['scale']*points@geometry_fit['rotation'].T+geometry_fit['translation']).tolist()
                coordinates=dict(zip(data.get('landmark_ids',[]),points))
                combined=dict(detections);combined.update(depth_detections)
                for key,detection in sorted(combined.items())[-512:]:
                    stamp=detection['source_stamp']
                    if stamp < data.get('map_origin',0):continue
                    obs=lookup(observations,stamp);meta=lookup(metadata,stamp)
                    if not obs or not meta:continue
                    depth=depth_cache.get(key)
                    try:
                        cs,surface,quality=frame_geometry(obs,detection,depth,meta,coordinates,geometry_fit,orientation)
                    except (ValueError,cv2.error,np.linalg.LinAlgError):
                        reasons['invalid geometry solve']+=1;continue
                    if quality.get('rejected'):reasons[quality['rejected']]+=1;continue
                    matched+=1;candidates.extend(cs)
                    if len(surface):surfaces.extend(surface.tolist());used_depth+=1
                    if quality.get('imu_used'):used_imu+=1
                objects=object_map(candidates)
            if len(surfaces)>5000:surfaces=surfaces[::int(np.ceil(len(surfaces)/5000))]
            native_path=path
            if not aligned:
                path=data.get("cameras",[])
                current=path[-1] if path else None
                for item in objects:
                    item["sources"]=[v for v in item["sources"] if v not in {"telemetry","IMU orientation"}]
            result={'timestamp':time.time(),'map_timestamp':data['timestamp'],'map_origin':data.get('map_origin'),
                    'state':data['state'],'world_frame':'native_mvo_unverified' if aligned else 'slam_arbitrary','unaligned_native_path':native_path,'objects':objects,
                    'path':path,'drone_position':current,'landmarks':transformed,'surface_points':surfaces,
                    'pose_source_stamp':pose_stamp,
                    'pose_age_in_recording_seconds':max(0,latest_stamp-pose_stamp) if latest_stamp is not None and pose_stamp is not None else None,
                    'geometry_lag_seconds':max(0,latest_stamp-max(c['stamp'] for c in candidates)) if candidates and latest_stamp is not None else None,
                    'matched_frames':matched,'depth_frames_used':used_depth,'imu_frames_used':used_imu,
                    'inputs':{'telemetry_frames':len(metadata),'YOLO_frames':len(detections),
                              'depth_frames':len(depth_cache),'SLAM_landmarks':len(data['points'])},
                    'alignment':{'accepted':fit is not None,'pairs':pairs,
                                 'inliers':int(fit['inliers'].sum()) if fit else 0,
                                 'relative_error':fit['error']/fit['spread'] if fit else None,
                                 'SLAM_to_native_scale':fit['scale'] if fit else None,
                                 'IMU_orientation_accepted':orientation is not None},
                    'rejected_frames':dict(reasons),
                    'message':'EXPERIMENTAL telemetry-led map. Native units/axes unverified; visible surfaces are not verified occupancy. '
                              +('Aligned inputs; slow depth attached to its original frame.' if fit else 'VISUAL MAP FALLBACK: objects use SLAM geometry and matched depth in arbitrary units. Telemetry alignment rejected; native path is stored separately and is not fused.')}
            temporary=folder/'floorplan.tmp';temporary.write_text(json.dumps(result,allow_nan=False));temporary.replace(folder/'floorplan.json')
        except (FileNotFoundError,json.JSONDecodeError):pass
        except (ValueError,cv2.error,np.linalg.LinAlgError) as error:
            print('Mapping frame rejected:',error,flush=True)
        time.sleep(max(.05,1.-(time.monotonic()-began)))
