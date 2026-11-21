"""Reintegrate matched depth keyframes into a room TSDF. Never sends flight commands.

SLAM scale is arbitrary until measured validation. Model metric depth is fitted
to current SLAM geometry, not treated as a range sensor. Every rebuild starts
from original keyframe packets so loop-closure pose corrections are respected.
"""
import json,math,subprocess
from pathlib import Path
from collections import Counter
import cv2,numpy as np
from fusion_geometry import fit_inverse_depth,native_sample

def camera_parameters(path):
    # Read only the numerical camera entries from the same config used by SLAM.
    values={}
    for line in path.read_text().splitlines():
        if ':' in line:
            key,value=line.strip().split(':',1)
            try:values[key]=float(value)
            except ValueError:pass
    k=np.array([[values['fx'],0,values['cx']],[0,values['fy'],values['cy']],[0,0,1.]])
    d=np.array([values.get(s,0) for s in ['k1','k2','p1','p2','k3']],dtype=np.float64)
    return k,d,int(values['cols']),int(values['rows'])

def pose_and_depth(observation,coordinates,raw,metric,k,d):
    features=[f for f in observation.get('features',[]) if f[0] in coordinates]
    if len(features)<20:return None,'too few current landmark matches'
    points=np.array([coordinates[f[0]] for f in features],np.float64);uv=np.array([f[1:3] for f in features],np.float64)
    ok,rvec,tvec,inliers=cv2.solvePnPRansac(points,uv,k,d,iterationsCount=100,reprojectionError=2.5,flags=cv2.SOLVEPNP_EPNP)
    if not ok or inliers is None or len(inliers)<16 or len(inliers)<.6*len(points):return None,'pose geometry rejected'
    ids=inliers.ravel();points=points[ids];uv=uv[ids]
    rotation=cv2.Rodrigues(rvec)[0];camera_points=points@rotation.T+tvec.ravel();z=camera_points[:,2]
    xy=np.rint(uv).astype(int);h,w=raw.shape
    valid=(z>1e-5)&(xy[:,0]>=0)&(xy[:,0]<w)&(xy[:,1]>=0)&(xy[:,1]<h)
    xy=xy[valid];z=z[valid]
    if len(z)<20:return None,'too few positive-depth landmarks'
    signal=raw[xy[:,1],xy[:,0]]
    train=np.arange(len(z))%5!=0;held=~train
    fit=fit_inverse_depth(signal[train],z[train])
    if fit is None:return None,'depth shape disagrees with landmarks'
    predicted=1/(fit['a']*signal[held]+fit['b'])
    error=float(np.median(np.abs(predicted-z[held])/z[held]))
    if not np.isfinite(error) or error>.2:return None,'held-out depth check failed'
    baseline=float(np.median(np.abs(np.median(z[train])-z[held])/z[held]))
    if baseline<.015 or error>.75*baseline:return None,'depth has no validated improvement over a flat range'
    inverse=fit['a']*raw+fit['b']
    depth=np.divide(1.,inverse,out=np.zeros_like(raw,dtype=np.float32),where=inverse>1e-6)
    valid=np.isfinite(depth)&(depth>fit['min_z'])&(depth<fit['max_z'])&(raw>=fit['min_signal'])&(raw<=fit['max_signal'])
    if metric is not None:valid&=np.isfinite(metric)&(metric>.15)&(metric<12)
    # Do not bridge strong depth discontinuities into artificial wall surfaces.
    gradient=cv2.morphologyEx(depth,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))
    valid&=gradient<np.maximum(.15*depth,1e-5)
    depth[~valid]=0
    pose=np.eye(4);pose[:3,:3]=rotation.T;pose[:3,3]=-rotation.T@tvec.ravel()
    return {'pose':pose,'depth':depth,'fit_error':error,'support':len(z)},None

def transformed_frame(pose,depth,transform):
    s=float(transform['scale']);r=np.asarray(transform['rotation']);t=np.asarray(transform['translation'])
    output=pose.copy();output[:3,:3]=r@pose[:3,:3];output[:3,3]=s*r@pose[:3,3]+t
    return output,depth*s

def reconstruct(room,aligned,voxel,max_frames=160):
    """aligned: (capture path, current map JSON, source->anchor similarity)."""
    import open3d as o3d
    volume=o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=voxel,sdf_trunc=voxel*4,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    stats=Counter();accepted=[];rays=[];door_evidence=[];semantic_points=[]
    for capture,data,transform in aligned:
        try:source=json.loads((capture/'source.json').read_text());live=Path(source['live']);k,d,w,h=camera_parameters(live.parent/'assets/tello_320_dense.yaml')
        except (OSError,ValueError,KeyError):stats['missing session source']+=1;continue
        coordinates=dict(zip(data.get('landmark_ids',[]),data['points']))
        telemetry_fit=None;metadata={}
        try:
            from fused_floorplan import calibrate
            metadata={p.stem:json.loads(p.read_text()) for p in (live/'frame-telemetry').glob('*.json')}
            telemetry_fit,_,_=calibrate(data,metadata)
            if telemetry_fit is not None:stats['captures with telemetry alignment']+=1
        except (OSError,ValueError,KeyError):pass
        packets=sorted((live/'depth-frames').glob('*.npz'))
        if not source.get('background_build'):packets=packets[::max(1,math.ceil(len(packets)/max_frames))]
        for packet in packets:
            try:
                observation_path=next((live/'observations'/f'{int(packet.stem)+offset}.json' for offset in [0,-1,1,-2,2] if (live/'observations'/f'{int(packet.stem)+offset}.json').exists()),live/'observations'/(packet.stem+'.json'))
                observation=json.loads(observation_path.read_text())
                if abs(observation.get('map_origin',data['map_origin'])-data['map_origin'])>1e-5:stats['different map origin']+=1;continue
                with np.load(packet,allow_pickle=False) as pack:
                    stamp=float(pack['source_stamp'])
                    if abs(stamp-observation['source_stamp'])>2e-6:stats['timestamp mismatch']+=1;continue
                    if 'rgb' not in pack:stats['older packet without RGB']+=1;continue
                    raw=pack['depth'].copy();rgb=pack['rgb'].copy();metric=pack['metric_depth'].copy() if 'metric_depth' in pack else None
                    labels=pack['labels'].copy() if 'labels' in pack else None;confidence=pack['confidence'].copy() if 'confidence' in pack else None
                if raw.shape!=(h,w) or rgb.shape!=(h,w,3):stats['wrong image shape']+=1;continue
                fitted,reason=pose_and_depth(observation,coordinates,raw,metric,k,d)
                if fitted is None:stats[reason]+=1;continue
                sample=native_sample(metadata.get(packet.stem,{})) if packet.stem in metadata else None
                if sample is not None and telemetry_fit is not None:
                    predicted=telemetry_fit['scale']*telemetry_fit['rotation']@fitted['pose'][:3,3]+telemetry_fit['translation']
                    if np.linalg.norm(predicted-sample['position'])>max(.35,3*telemetry_fit['error'],.3*telemetry_fit['spread']):
                        stats['hardware/visual pose disagreement']+=1;continue
                    stats['frames checked against hardware pose']+=1
                depth=fitted['depth'];pose,depth=transformed_frame(fitted['pose'],depth,transform)
                # A person mask is dynamic evidence, never part of a permanent wall.
                if labels is not None:depth[labels==12]=0
                try:
                    detection=json.loads((live/'depth-detections'/(packet.stem+'.json')).read_text())
                    for obj in detection['objects']:
                        if obj['label']=='person':cv2.fillPoly(depth,[np.rint(obj['polygon']).astype(np.int32)],0)
                except (OSError,ValueError,KeyError):pass
                # Open3D uses pinhole rays; rectify both colour and depth consistently.
                map_x,map_y=cv2.initUndistortRectifyMap(k,d,None,k,(w,h),cv2.CV_32FC1)
                rectified=cv2.remap(depth,map_x,map_y,cv2.INTER_NEAREST);colour=cv2.remap(rgb,map_x,map_y,cv2.INTER_LINEAR)
                rectified[rectified<voxel]=0
                image=o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(cv2.cvtColor(colour,cv2.COLOR_BGR2RGB)),
                    o3d.geometry.Image(rectified.astype(np.float32)),depth_scale=1.,depth_trunc=max(float(rectified.max())+voxel,voxel),convert_rgb_to_intensity=False)
                intrinsic=o3d.camera.PinholeCameraIntrinsic(w,h,k[0,0],k[1,1],k[0,2],k[1,2])
                volume.integrate(image,intrinsic,np.linalg.inv(pose))
                yy,xx=np.mgrid[6:h-6:12,6:w-6:12];zs=rectified[yy,xx].ravel();xx=xx.ravel();yy=yy.ravel();good=zs>0
                cp=np.column_stack([(xx-k[0,2])/k[0,0],(yy-k[1,2])/k[1,1],np.ones(len(xx))])*zs[:,None]
                endpoints=cp[good]@pose[:3,:3].T+pose[:3,3]
                rays.append((pose[:3,3],endpoints))
                if labels is not None:
                    rect_labels=cv2.remap(labels,map_x,map_y,cv2.INTER_NEAREST)
                    for point,label in zip(endpoints,rect_labels[yy[good],xx[good]]):
                        if int(label) in {0,3,5,8,14,58}:semantic_points.append([*point.tolist(),int(label)])
                try:
                    structure=json.loads((live/'structure-frames'/(packet.stem+'.json')).read_text())
                    door_evidence.extend([dict(door,source_stamp=stamp,map_id=capture.name) for door in structure.get('doors',[])])
                except (OSError,ValueError):pass
                accepted.append({'map_id':capture.name,'stamp':stamp,'depth_fit_error':fitted['fit_error'],'landmarks':fitted['support']})
            except FileNotFoundError:stats['no matching tracked frame or packet']+=1
            except (OSError,ValueError,KeyError,cv2.error):stats['incomplete packet or invalid pose']+=1
    mesh=volume.extract_triangle_mesh();mesh.compute_vertex_normals();cloud=volume.extract_point_cloud()
    # Build fresh each time: repeated polling never increases occupancy support.
    occupied=Counter();free=Counter()
    for origin,endpoints in rays:
        frame_hit=set();frame_free=set()
        for end in endpoints:
            frame_hit.add(tuple(np.floor(end/voxel).astype(int)))
            distance=np.linalg.norm(end-origin);steps=min(300,int(distance/voxel))
            if steps>3:
                for point in origin+(end-origin)*np.arange(1,steps-2)[:,None]/steps:frame_free.add(tuple(np.floor(point/voxel).astype(int)))
        occupied.update(frame_hit);free.update(frame_free-frame_hit)
    # These are tentative cells from predicted ranges, never certified free space.
    cells=[{'cell':[int(v) for v in key],'state':'occupied_candidate' if occupied[key]>=2 else 'unknown','hits':occupied[key],'misses':free[key]} for key in occupied]
    for key,count in free.items():
        if key not in occupied and count>=3:cells.append({'cell':[int(v) for v in key],'state':'free_candidate','hits':0,'misses':count})
    telemetry_checks={key:stats.pop(key,0) for key in ['captures with telemetry alignment','frames checked against hardware pose']}
    summary={'state':'ready' if accepted else 'waiting','integrated_frames':len(accepted),'rejected':dict(stats),'telemetry_checks':telemetry_checks,'voxel_size':voxel,
        'vertices':len(mesh.vertices),'triangles':len(mesh.triangles),'units':'arbitrary anchor-map units','metric_validated':False,
        'planning_ready':False,'blocking_reasons':['Camera calibration needs validation for the active flight mode.','Metric scale and clearance require measured validation.','Predicted depth is not a range sensor.'],
        'frames':accepted,'doors':door_evidence[-100:],'note':'TSDF surface reconstruction; no automatic navigation or motor commands.'}
    exporter=Path(__file__).resolve().parents[1]/'build/occupancy/octomap_export'
    summary['octomap']='not prepared'
    if exporter.is_file() and rays:
        ray_file=room/'occupancy-rays.txt'
        with ray_file.open('w') as stream:
            for index,(origin,endpoints) in enumerate(rays):
                for point in endpoints:stream.write(' '.join(map(str,[index,*origin,*point]))+'\n')
        output=room/'room.tmp.ot'
        try:
            subprocess.run([str(exporter),str(voxel),str(ray_file),str(output)],check=True,timeout=45)
            output.replace(room/'room.ot');summary['octomap']='exported; arbitrary scale, not validated for navigation'
        except (OSError,subprocess.SubprocessError) as error:summary['octomap']='export failed: '+str(error)
    if accepted:
        temp=room/'room-mesh.tmp.ply';o3d.io.write_triangle_mesh(str(temp),mesh,write_ascii=False);temp.replace(room/'room-mesh.ply')
        o3d.io.write_point_cloud(str(room/'room-surfaces.ply'),cloud)
    else:
        for name in ['room-mesh.ply','room-surfaces.ply','room.ot']:(room/name).unlink(missing_ok=True)
    # Empty outputs deliberately replace stale geometry after a rejected rebuild.
    vertices=np.asarray(mesh.vertices);triangles=np.asarray(mesh.triangles);colors=np.asarray(mesh.vertex_colors)
    structure_colors=np.tile([.4,.48,.52],(len(vertices),1))
    if semantic_points and len(vertices):
        samples=np.asarray(semantic_points);semantic_cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(samples[:,:3]));search=o3d.geometry.KDTreeFlann(semantic_cloud)
        palette={0:[.48,.65,.85],3:[.39,.71,.45],5:[.75,.61,.8],8:[.82,.75,.35],14:[.96,.67,.25],58:[.96,.67,.25]}
        for i,point in enumerate(vertices):
            count,indices,distances=search.search_knn_vector_3d(point,1)
            if count and distances[0]<(voxel*4)**2:structure_colors[i]=palette.get(int(samples[indices[0],3]),[.4,.48,.52])
    result={'vertices':vertices.tolist(),'triangles':triangles.tolist(),'colors':np.clip(colors,0,1).tolist(),'structure_colors':structure_colors.tolist(),'summary':summary}
    atomic(room/'room-mesh.json',result)
    atomic(room/'occupancy.json',{'resolution':voxel,'units':summary['units'],'planning_ready':False,'cells':cells,'unknown_is_blocked':True})
    atomic(room/'reconstruction-status.json',summary)
    return summary,semantic_points

def atomic(path,data):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data,allow_nan=False));temp.replace(path)
