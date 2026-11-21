"""Compare baseline/adaptive map geometry on identical frozen SLAM/vision inputs.

This does not rerun SLAM or measure ground-truth accuracy. Writes separate outputs.
"""
from pathlib import Path
import argparse,json,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision'))
import cv2,numpy as np
from fused_floorplan import load_new,lookup,calibrate,frame_geometry,object_map,frame_pose

def run(folder,output):
 data=json.loads((folder/'map.json').read_text());meta={};obs={};det={};dd={}
 load_new(folder/'frame-telemetry',meta);load_new(folder/'observations',obs,limit=2048)
 load_new(folder/'detections',det,limit=2048);load_new(folder/'depth-detections',dd,limit=128)
 fit,orientation,pairs=calibrate(data,meta);aligned=fit is not None
 used_fit=fit if aligned else {'scale':1.,'rotation':np.eye(3),'translation':np.zeros(3),'visual_only':True}
 coordinates=dict(zip(data.get('landmark_ids',[]),np.asarray(data['points'],float)))
 det.update(dd);output.mkdir(parents=True,exist_ok=True);results={}
 for mode in ['off','adaptive']:
  os.environ['TELLO_MAP_FUSION']=mode;candidates=[];surfaces=[];positions=[];rejected={};applied=0;weights=[]
  for key,detection in sorted(det.items())[-512:]:
   stamp=detection['source_stamp']
   if stamp<data.get('map_origin',0):continue
   observation=lookup(obs,stamp);metadata=lookup(meta,stamp)
   if not observation or not metadata:continue
   depth_path=folder/'depth-frames'/(key+'.npz');depth=None
   if depth_path.exists():
    with np.load(depth_path,allow_pickle=False) as pack:depth=pack['depth'].copy()
   try:
    cv2.setRNGSeed(0)
    cs,surface,quality=frame_geometry(observation,detection,depth,metadata,coordinates,used_fit,orientation)
    if quality.get('rejected'):
     reason=quality['rejected'];rejected[reason]=rejected.get(reason,0)+1;continue
    cv2.setRNGSeed(0);camera,reason=frame_pose(observation,metadata,coordinates,used_fit,orientation,fusion_mode=mode)
    if camera:
     positions.append([stamp,*camera['position'].tolist()])
     if camera.get('fusion_applied'):applied+=1;weights.append(camera['fusion_quality']['telemetry_weight'])
    candidates.extend(cs);surfaces.extend(surface.tolist())
   except (ValueError,cv2.error,np.linalg.LinAlgError):rejected['invalid geometry']=rejected.get('invalid geometry',0)+1
  result={'mode':mode,'world_frame':'native_local_metres_experimental' if aligned else 'slam_arbitrary',
   'alignment_accepted':aligned,'pose_pairs':pairs,'positions':positions,'objects':object_map(candidates),
   'surface_points':surfaces,'fusion_applied_frames':applied,'telemetry_weights':weights,'rejected':rejected}
  results[mode]=result;(output/(mode+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False))
 a=results['off'];b=results['adaptive'];pa=np.array(a['positions']);pb=np.array(b['positions']);changes=[]
 if len(pa) and pa.shape==pb.shape:changes=np.linalg.norm(pa[:,1:]-pb[:,1:],axis=1).tolist()
 summary={'input':str(folder),'same_frozen_inputs':True,'alignment_accepted':aligned,'pose_pairs':pairs,
  'modes':{k:{'object_count':len(v['objects']),'surface_samples':len(v['surface_points']),'pose_frames':len(v['positions']),'fused_frames':v['fusion_applied_frames'],'rejected':v['rejected']} for k,v in results.items()},
  'median_position_change_m':float(np.median(changes)) if changes and aligned else None,
  'max_position_change_m':float(max(changes)) if changes and aligned else None,
  'accuracy_improvement_established':False,'notes':['No ground-truth map or camera trajectory available.','Rejected alignment prevents fusion; visual fallback stays unchanged.','Point count, smoothness and agreement do not establish map accuracy.','Only mapping position is blended; rotation and flight controls are unchanged.']}
 (output/'comparison.json').write_text(json.dumps(summary,indent=2,allow_nan=False));print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.input,a.output)
