/* Replay-only diagnostics. Coordinates/scale stay separate; never sends commands. */
(function(root){
 'use strict';
 function phaseAt(phases,t){
  let lo=0,hi=phases.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(phases[mid][0]<=t)lo=mid+1;else hi=mid;}
  return lo?phases[lo-1][1]:'unknown';
 }
 function median(values){const a=values.filter(Number.isFinite).sort((x,y)=>x-y);return a.length?a[Math.floor(a.length/2)]:null;}
 function selected(rows,phases,airborne){return rows.filter(r=>!airborne||phaseAt(phases,r[0])==='airborne');}
 root.MotionComparisonMath={phaseAt,median,selected};
 if(typeof document==='undefined')return;
 const panel=document.getElementById('comparisonPanel');if(!panel)return;
 let data=null,map=null;
 const colors=['#72bbff','#6edac4','#ffb25c','#dba2ff'];
 const axes={xy:[1,2],xz:[1,3],yz:[2,3]};
 function surface(id){
  const c=document.getElementById(id),ratio=window.devicePixelRatio||1;
  c.width=Math.max(1,Math.round(c.clientWidth*ratio));c.height=Math.round(c.clientHeight*ratio);
  const x=c.getContext('2d');x.setTransform(ratio,0,0,ratio,0,0);
  const w=c.width/ratio,h=c.height/ratio;x.fillStyle='#101b2c';x.fillRect(0,0,w,h);
  x.font='12px sans-serif';return {x,w,h};
 }
 function text(x,value,a,b,color='#c5d0df'){x.fillStyle=color;x.fillText(value,a,b);}
 function trajectory(id,rows,projection){
  const {x,w,h}=surface(id),[a,b]=axes[projection];
  const pts=rows.filter(r=>Number.isFinite(r[a])&&Number.isFinite(r[b]));
  if(!pts.length){text(x,'No selected trajectory data yet',16,30);return;}
  const xs=pts.map(r=>r[a]),ys=pts.map(r=>r[b]);
  const lo=[Math.min(...xs),Math.min(...ys)],hi=[Math.max(...xs),Math.max(...ys)];
  const span=Math.max(hi[0]-lo[0],hi[1]-lo[1],.001),scale=Math.min(w-50,h-50)/span;
  const q=r=>[w/2+(r[a]-(lo[0]+hi[0])/2)*scale,h/2-(r[b]-(lo[1]+hi[1])/2)*scale];
  x.strokeStyle='#23354d';for(let i=1;i<5;i++){x.beginPath();x.moveTo(w*i/5,15);x.lineTo(w*i/5,h-15);x.stroke();}
  x.strokeStyle=colors[0];x.lineWidth=1.7;x.beginPath();let previous=null;
  for(const r of pts){const p=q(r);if(!previous||r[0]-previous[0]>2)x.moveTo(...p);else x.lineTo(...p);previous=r;}x.stroke();
  for(const [r,color] of [[pts[0],'#8ee6a7'],[pts[pts.length-1],'#ffb25c']]){x.fillStyle=color;x.beginPath();x.arc(...q(r),4,0,Math.PI*2);x.fill();}
  text(x,`${pts.length} samples · ${projection.toUpperCase()} · independently fitted`,12,h-9);
 }
 function chart(id,rows,columns,labels,duration,videoTime,slamTime,cutoff=null){
  const {x,w,h}=surface(id),left=58,right=w-12,top=28,bottom=h-28;
  const values=rows.flatMap(r=>columns.map(i=>r[i])).filter(Number.isFinite);
  if(!values.length){text(x,'No selected samples yet',16,30);return;}
  let low=Math.min(...values),high=Math.max(...values);
  if(cutoff!==null){low=Math.min(low,0);high=Math.max(high,cutoff);}
  const pad=Math.max((high-low)*.08,.001);low-=pad;high+=pad;
  const px=t=>left+Math.max(0,Math.min(duration,t))/duration*(right-left),py=v=>bottom-(v-low)/(high-low)*(bottom-top);
  // Recorded driver phase is context, not independent evidence of flight.
  for(let i=0;i<data.phases.length;i++){
   if(data.phases[i][1]!=='airborne')continue;
   const begin=data.phases[i][0],end=data.phases[i+1]?.[0]??duration;
   x.fillStyle='rgba(85,166,123,.13)';x.fillRect(px(begin),top,Math.max(0,px(end)-px(begin)),bottom-top);
  }
  if(map?.ordered)for(let i=0;i<(map.tracking_history||[]).length;i++){
   const row=map.tracking_history[i];if(row[1]==='Tracking')continue;
   const start=row[0]-data.start_stamp_ns/1e9;
   const end=(map.tracking_history[i+1]?.[0]??map.frame_timestamp)-data.start_stamp_ns/1e9;
   x.fillStyle='#d06767';x.fillRect(px(start),bottom-5,Math.max(0,px(end)-px(start)),5);
  }
  x.strokeStyle='#2b3a50';x.lineWidth=1;
  for(let i=0;i<=4;i++){
   const y=top+(bottom-top)*i/4;x.beginPath();x.moveTo(left,y);x.lineTo(right,y);x.stroke();
   text(x,(high-(high-low)*i/4).toPrecision(3),3,y+4);
   const t=duration*i/4;text(x,t.toFixed(0)+'s',px(t)-9,h-8);
  }
  columns.forEach((column,index)=>{
   x.strokeStyle=colors[index];x.lineWidth=1.3;x.beginPath();let previous=null;
   for(const row of rows){const v=row[column];if(!Number.isFinite(v)){previous=null;continue;}
    if(!previous||row[0]-previous[0]>1)x.moveTo(px(row[0]),py(v));else x.lineTo(px(row[0]),py(v));previous=row;
   }x.stroke();
   if(id==='slamPosition'){x.fillStyle=colors[index];for(const row of rows){if(!Number.isFinite(row[column]))continue;x.beginPath();x.arc(px(row[0]),py(row[column]),2,0,Math.PI*2);x.fill();}}
   text(x,labels[index],left+index*75,16,colors[index]);
  });
  if(cutoff!==null){x.setLineDash([4,4]);x.strokeStyle='#ff7474';x.beginPath();x.moveTo(left,py(cutoff));x.lineTo(right,py(cutoff));x.stroke();x.setLineDash([]);}
  for(const [time,color] of [[videoTime,'#fff'],[slamTime,'#ffb25c']]){
   if(!Number.isFinite(time)||time<0||time>duration)continue;
   x.strokeStyle=color;x.beginPath();x.moveTo(px(time),top);x.lineTo(px(time),bottom);x.stroke();
  }
 }
 function draw(){
  if(!data||!data.start_stamp_ns)return;
  const airborne=document.getElementById('comparisonAirborne').checked;
  const video=data.image_time,origin=data.start_stamp_ns/1e9;
  const aligned=map?.ordered===true;
  const slamTime=aligned?map.frame_timestamp-origin:null;
  const slamRows=aligned?(map.cameras||[]).map((p,i)=>[(map.camera_times?.[i]??NaN)-origin,...p]).filter(r=>Number.isFinite(r[0])):[];
  const rows=selected(data.mvo,data.phases,airborne),slam=selected(slamRows,data.phases,airborne);
  const duration=Math.max(1,video||0,data.phases.at(-1)?.[0]||0,data.imu.at(-1)?.[0]||0);
  trajectory('nativeTrajectory',rows,document.getElementById('nativeProjection').value);
  trajectory('slamTrajectory',slam,document.getElementById('slamProjection').value);
  chart('nativePosition',rows,[1,2,3],['X','Y','Z'],duration,video,slamTime);
  chart('slamPosition',slam,[1,2,3],['X','Y','Z'],duration,video,slamTime);
  const signal=document.getElementById('imuSignal').value;
  const columns=signal==='acc'?[1,2,3]:signal==='gyro'?[4,5,6]:[7,8,9,10];
  chart('imuHistory',data.imu,columns,signal==='quat'?['q0','q1','q2','q3']:['X','Y','Z'],duration,video,slamTime);
  chart('ageHistory',data.ages,[1,3],['Flight ms','Log ms'],duration,video,slamTime,250);
  const age=Date.now()/1000-data.stamp_ns/1e9;
  document.getElementById('comparisonStatus').textContent=`${age>3?'STALE — ':''}${data.playback_state} | Video: ${video?.toFixed(2)??'waiting'} s | SLAM: ${aligned?map.state+' at '+slamTime.toFixed(2)+' s':'waiting for ordered SLAM'} | `+
   (Number.isFinite(video)&&Number.isFinite(slamTime)?`Frame-time difference (video minus SLAM): ${Math.abs(video-slamTime)<.005?'0.00':(video-slamTime).toFixed(2)} s. `:'Use --slam-all-frames for matching source clocks. ')+
   (aligned&&map.last_tracked_timestamp>0?`Last exported tracked frame: ${(map.last_tracked_timestamp-origin).toFixed(2)} s.`:'');
  const flight=median(data.ages.map(r=>r[1])),log=median(data.ages.map(r=>r[3]));
  const gaps=data.images.slice(1).map((t,i)=>t-data.images[i]);
  const valid=data.ages.filter(r=>r[2]&&r[4]).length;
  document.getElementById('comparisonMetrics').textContent=`${data.images.length} images · ${data.imu.length} distinct IMU updates · ${data.mvo.length} distinct motion updates. `+
   `Median sample ages: flight ${flight?.toFixed(1)??'—'} ms, log ${log?.toFixed(1)??'—'} ms. `+
   `${valid}/${data.ages.length} image metadata entries have both preceding samples within 250 ms. `+
   `${gaps.filter(t=>t>.25).length} video gaps exceed 250 ms; longest ${gaps.length?Math.max(...gaps).toFixed(2):'—'} s.`;
 }
 root.motionComparison={setMap(value){map=value;draw();}};
 for(const id of ['comparisonAirborne','nativeProjection','slamProjection','imuSignal'])document.getElementById(id).addEventListener('change',draw);
 window.addEventListener('resize',draw);
 async function refresh(){
  if(!window.TELLO_PLAYBACK_ONLY)return;
  try{const response=await fetch('comparison.json?t='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('waiting');data=await response.json();panel.hidden=false;draw();}
  catch(_){if(data)document.getElementById('comparisonStatus').textContent='Comparison data unavailable; last view retained.';}
  setTimeout(refresh,500);
 }
 refresh();
})(typeof window==='undefined'?globalThis:window);
