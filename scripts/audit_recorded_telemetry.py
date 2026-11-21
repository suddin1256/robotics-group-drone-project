"""Offline unit evidence across local bags; never connects to a drone.

Run in the ROS Python environment with --recordings and --output directories.
Decoded fields remain raw; evidence does not establish absolute accuracy.
"""
import argparse,json,collections
from pathlib import Path
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from std_msgs.msg import String

def finite_stats(values):
 a=np.asarray(values,float);a=a[np.isfinite(a)]
 return {'count':len(a),'p10_median_p90':np.percentile(a,[10,50,90]).tolist()} if len(a) else {'count':0}

def audit(bag):
 r=rosbag2_py.SequentialReader();r.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('cdr','cdr'))
 topics={t.name for t in r.get_all_topics_and_types()};wanted=['/tello/raw_log','/tello/telemetry','/tello/image_metadata','/tello/control_status']
 r.set_filter(rosbag2_py.StorageFilter(topics=[x for x in wanted if x in topics]))
 counts=collections.Counter();last={};motion=[];imu=[];flight=[];ages=[];phases=[]
 while r.has_next():
  topic,payload,stamp=r.read_next();counts[topic]+=1
  data=json.loads(deserialize_message(payload,String).data)
  if topic=='/tello/raw_log':
   t=data.get('received_stamp_ns',stamp)/1e9;native=data.get('data',{})
   for name,fields,rows in [('mvo',['pos_x','pos_y','pos_z','vel_x','vel_y','vel_z'],motion),('imu',['acc_x','acc_y','acc_z','gyro_x','gyro_y','gyro_z','q0','q1','q2','q3'],imu)]:
    sample=native.get(name,{});count=sample.get('count',0)
    if not count or count==last.get(name):continue
    last[name]=count
    row=[t]+[sample.get(f,float('nan')) for f in fields]
    if all(isinstance(v,(int,float)) for v in row):rows.append(row)
  elif topic=='/tello/telemetry':flight.append((stamp/1e9,data.get('state',{})))
  elif topic=='/tello/control_status':phases.append((stamp/1e9,data.get('phase')))
  elif topic=='/tello/image_metadata':
   ages.append([data.get(n,{}).get('age_ms') for n in ['flight','log']])
 result={'bag':bag.name,'counts':dict(counts),'light_values':dict(collections.Counter(str(s.get('light_strength','missing')) for _,s in flight)), 'height_raw':finite_stats([s.get('height',float('nan')) for _,s in flight])}
 if motion:
  m=np.asarray(motion,float);result['mvo_samples']=len(m);result['position_ranges_raw']=np.ptp(m[:,1:4],axis=0).tolist();result['velocity_norm_raw']=finite_stats(np.linalg.norm(m[:,4:7],axis=1));result['mvo_interval_s']=finite_stats(np.diff(m[:,0]));result['mvo_initial_position_raw']=m[0,1:4].tolist()
  ratios=[];height_slopes=[]
  for i in range(len(m)):
   j=np.searchsorted(m[:,0],m[i,0]+1.)
   if j>=len(m):continue
   dt=m[j,0]-m[i,0]
   if not .8<dt<1.4:continue
   dp=m[j,1:4]-m[i,1:4];speed=np.linalg.norm(dp)/dt;v=np.median(np.linalg.norm(m[i:j+1,4:7],axis=1))
   if .08<speed<2 and v>.05:ratios.append(speed/v)
  result['position_derivative_speed_over_decoded_velocity_norm']=finite_stats(ratios)
  # Height differences remove unknown position origin. Restrict nearby samples.
  if flight:
   ft=np.array([t for t,_ in flight]);heights=np.array([s.get('height',np.nan) for _,s in flight],float)
   ids=np.searchsorted(ft,m[:,0]);ids=np.minimum(ids,len(ft)-1);h=heights[ids];near=abs(ft[ids]-m[:,0])<.3
   for i in range(len(m)):
    j=np.searchsorted(m[:,0],m[i,0]+1.)
    if j>=len(m) or not near[i] or not near[j]:continue
    dh=h[j]-h[i];dz=m[j,3]-m[i,3]
    if abs(dh)>=2 and .05<abs(dz)<1.5 and m[j,0]-m[i,0]<1.4:height_slopes.append(dz/dh)
  result['mvo_z_delta_per_height_raw_unit']=finite_stats(height_slopes)
 if imu:
  a=np.asarray(imu,float);q=a[:,7:11];norm=np.linalg.norm(q,axis=1);result['imu_samples']=len(a);result['acceleration_norm_raw']=finite_stats(np.linalg.norm(a[:,1:4],axis=1));result['gyro_norm_raw']=finite_stats(np.linalg.norm(a[:,4:7],axis=1));result['quaternion_norm']=finite_stats(norm)
  good=norm>.5;q=q[good]/norm[good,None];t=a[good,0];g=np.linalg.norm(a[good,4:7],axis=1);ratios=[]
  for i in range(len(t)):
   j=np.searchsorted(t,t[i]+.3)
   if j>=len(t) or not .2<t[j]-t[i]<.6:continue
   theta=2*np.arccos(np.clip(abs(q[i]@q[j]),0,1));rate=theta/(t[j]-t[i]);gyro=np.median(g[i:j+1])
   if rate>.08 and gyro>.03:ratios.append(rate/gyro)
  result['quaternion_angular_rate_rad_s_over_gyro_norm']=finite_stats(ratios)
 result['image_association_ages_ms']={n:finite_stats([a[i] for a in ages if isinstance(a[i],(int,float))]) for i,n in enumerate(['flight','log'])}
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--recordings',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 results=[]
 for bag in sorted(args.recordings.iterdir()):
  if not (bag/'metadata.yaml').exists():continue
  try:result=audit(bag)
  except Exception as e:result={'bag':bag.name,'error':str(e)}
  results.append(result);print(bag.name,'motion',result.get('mvo_samples',0),'imu',result.get('imu_samples',0),flush=True)
 (args.output/'all_recordings_unit_evidence.json').write_text(json.dumps(results,indent=2,allow_nan=False))

if __name__=='__main__':main()
