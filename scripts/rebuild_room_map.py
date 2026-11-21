"""Rebuild a persistent experimental room cloud from checked cross-session matches.

No ICP guessing: independent maps need ORB landmark descriptor matches and a
robust 3D similarity fit. Unaligned maps remain separately viewable in the app.
"""
import argparse,json,sys,time
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision'))
from fusion_geometry import similarity

def registration(source,target,sd,td):
    if len(sd)<20 or len(td)<20:return None,'Not enough descriptor-backed landmarks'
    matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
    forward={m.queryIdx:m.trainIdx for pair in matcher.knnMatch(sd,td,k=2) if len(pair)==2 for m,n in [pair] if m.distance<.7*n.distance and m.distance<60}
    backward={m.queryIdx:m.trainIdx for pair in matcher.knnMatch(td,sd,k=2) if len(pair)==2 for m,n in [pair] if m.distance<.7*n.distance and m.distance<60}
    pairs=[(i,j) for i,j in forward.items() if backward.get(j)==i]
    if len(pairs)<20:return None,'Too few unique matching landmarks'
    x=source[[i for i,j in pairs]];y=target[[j for i,j in pairs]]
    radius=float(np.median(np.linalg.norm(y-np.median(y,axis=0),axis=1)))
    if radius<1e-6:return None,'Insufficient spatial extent'
    gate=.04*radius;rng=np.random.default_rng(11);best=None
    # Reserve descriptor matches for an independent registration check.
    train=np.array([i for i in range(len(x)) if i%5]);held=np.array([i for i in range(len(x)) if not i%5])
    for _ in range(200):
        ids=rng.choice(train,3,replace=False)
        if np.linalg.matrix_rank(x[ids]-x[ids].mean(0),tol=1e-7)<2:continue
        try:s,r,t=similarity(x[ids],y[ids])
        except (ValueError,np.linalg.LinAlgError):continue
        if not .05<s<20:continue
        errors=np.linalg.norm(s*x@r.T+t-y,axis=1);good=errors<gate
        if best is None or good[train].sum()>best[0][train].sum():best=(good,s,r,t)
    if best is None:return None,'No consistent 3D transform'
    good,s,r,t=best
    if good[train].sum()<12 or good[train].mean()<.65 or good[held].sum()<3 or good[held].mean()<.6:return None,'Geometric agreement failed; session kept separate'
    try:s,r,t=similarity(x[train[good[train]]],y[train[good[train]]])
    except (ValueError,np.linalg.LinAlgError):return None,'Degenerate registration'
    errors=np.linalg.norm(s*x@r.T+t-y,axis=1)
    if np.median(errors[held])>gate:return None,'Held-out alignment check failed'
    return {'scale':s,'rotation':r,'translation':t,'matches':len(pairs),'inliers':int((errors<gate).sum()),'heldout_median_error':float(np.median(errors[held])),'threshold':gate},None

def read_map(path):
    d=json.loads(path.read_text());p=np.asarray(d.get('points',[]),float).reshape(-1,3)
    if len(p)<6 or not np.isfinite(p).all():return None
    desc=d.get('landmark_descriptors',[]);indices=[i for i,x in enumerate(desc[:len(p)]) if isinstance(x,list) and len(x)==32]
    indices=indices[::max(1,int(np.ceil(len(indices)/12000)))]
    dp=p[indices];ds=np.array([desc[i] for i in indices],np.uint8).reshape(-1,32)
    surface=np.empty((0,3));floor=path.with_name('floorplan.json')
    if floor.exists():
        f=json.loads(floor.read_text())
        if f.get('map_origin')==d.get('map_origin'):
            surface=np.asarray(f.get('surface_points',[]),float).reshape(-1,3)
            if f.get('world_frame')!='slam_arbitrary':
                trans=f.get('native_from_slam')
                if trans and trans['scale']>0:surface=(surface-np.array(trans['translation']))@np.array(trans['rotation'])/trans['scale']
                else:surface=np.empty((0,3))
    return d,p,dp,ds,surface

def rebuild(room):
    previous={};dest=room/'room-map.json'
    try:previous=json.loads(dest.read_text())
    except (OSError,ValueError):pass
    maps=[]
    try:excluded=set(json.loads((room/'superseded-captures.json').read_text()))
    except (OSError,ValueError):excluded=set()
    for path in (room/'maps').glob('*/map.json'):
        if path.parent.name in excluded:continue
        try:
            item=read_map(path)
            if item:maps.append((path,item))
        except (OSError,ValueError):continue
    maps.sort(key=lambda x:(x[0].parent.name!=previous.get('anchor_id'),x[0].stat().st_mtime))
    clouds=[];rows=[];target_points=[];target_desc=[];paths=[];anchor=None;aligned=[]
    pending=maps
    while pending:
        deferred=[];made_progress=False
        for path,(d,p,dp,ds,surface) in pending:
            key=path.parent.name
            if anchor is None:anchor=key;transform={'scale':1.,'rotation':np.eye(3),'translation':np.zeros(3),'matches':0,'inliers':0,'heldout_median_error':0};reason=None
            else:
                transform,reason=registration(dp,np.concatenate(target_points),ds,np.concatenate(target_desc)) if target_desc else (None,'Anchor lacks matching descriptors; reprocess its flight')
            if transform is None:deferred.append((path,(d,p,dp,ds,surface),reason));continue
            made_progress=True
            def apply(x):return transform['scale']*x@transform['rotation'].T+transform['translation']
            aligned.append((path.parent,d,transform))
            clouds.append(apply(np.concatenate([p,surface])));target_points.append(apply(dp));target_desc.append(ds)
            route=np.asarray(d.get('cameras',[]),float).reshape(-1,3);paths.append({'map_id':key,'points':apply(route).tolist()})
            rows.append({'map_id':key,'aligned':True,'landmarks':len(p),'surface_samples':len(surface),'transform':{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in transform.items()}})
        if not made_progress:
            rows.extend({'map_id':path.parent.name,'aligned':False,'reason':reason} for path,item,reason in deferred)
            break
        pending=[(path,item) for path,item,reason in deferred]
    cloud=np.concatenate(clouds) if clouds else np.empty((0,3));cloud=cloud[np.isfinite(cloud).all(axis=1)]
    voxel=0.;evidence=[]
    if len(cloud):
        lo,hi=np.quantile(cloud,[.01,.99],axis=0);voxel=max(float(np.max(hi-lo))/180,1e-6)
        cells={}
        # Rebuild from one latest snapshot per source, so polling never adds votes.
        for source,points in enumerate(clouds):
            for point in points:
                if not np.isfinite(point).all():continue
                key=tuple(np.floor(point/voxel).astype(int));entry=cells.setdefault(key,[np.zeros(3),0,set()]);entry[0]+=point;entry[1]+=1;entry[2].add(source)
        evidence=[[*v[0]/v[1],len(v[2])] for v in cells.values()]
        if len(evidence)>18000:evidence=evidence[::int(np.ceil(len(evidence)/18000))]
    result={'state':'ready' if evidence else 'waiting','updated':time.time(),'anchor_id':anchor,'units':'arbitrary anchor-map units','points':evidence,'paths':paths,'sessions':rows,'voxel_size':voxel,'aligned_maps':sum(x['aligned'] for x in rows),'separate_maps':sum(not x['aligned'] for x in rows),'note':'Experimental observed surfaces. Repeated-session support is not occupancy probability. Blank space is unknown; metric scale and clearance are not verified.'}
    # The sparse view stays usable when the optional dense dependencies are absent.
    if aligned and voxel>0 and any((path/'source.json').exists() for path,_,_ in aligned):
        try:
            from dense_reconstruction import reconstruct
            dense,semantics=reconstruct(room,aligned,max(voxel*2,1e-5))
            result['dense']=dense;result['semantic_points']=semantics[::max(1,int(np.ceil(len(semantics)/12000)))]
        except ImportError as error:result['dense']={'state':'unavailable','reason':str(error),'planning_ready':False}
        except Exception as error:
            import traceback;traceback.print_exc()
            result['dense']={'state':'error','reason':str(error),'planning_ready':False}
    temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(result,allow_nan=False));temp.replace(dest);print(f'Room rebuilt: {len(evidence)} cells, {result["aligned_maps"]} aligned / {result["separate_maps"]} separate maps',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--room',type=Path,required=True);a=p.parse_args();rebuild(a.room)
