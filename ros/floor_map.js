/* Observed-feature projection only. No inferred walls, free space or navigation. */
(function(root){
 'use strict';
 const valid=p=>Array.isArray(p)&&p.length===3&&p.every(Number.isFinite);
 function project(points,plane,angle){
  const axes={xz:[0,2],xy:[0,1],yz:[1,2]}[plane]||[0,2];
  const c=Math.cos(angle),s=Math.sin(angle);
  return points.filter(valid).map(p=>[p[axes[0]]*c-p[axes[1]]*s,p[axes[0]]*s+p[axes[1]]*c]);
 }
 function bounds(points){
  if(!points.length)return {center:[0,0],span:1};
  const sorted=[0,1].map(i=>points.map(p=>p[i]).sort((a,b)=>a-b));
  const lo=sorted.map(a=>a[Math.floor((a.length-1)*.02)]);
  const hi=sorted.map(a=>a[Math.ceil((a.length-1)*.98)]);
  return {center:lo.map((v,i)=>(v+hi[i])/2),span:Math.max(hi[0]-lo[0],hi[1]-lo[1],.001)};
 }
 function cells(points,size){
  const bins=new Map();
  for(const p of points){const x=Math.floor(p[0]/size),y=Math.floor(p[1]/size),key=x+','+y;
   const cell=bins.get(key)||{x,y,count:0};cell.count++;bins.set(key,cell);}
  return [...bins.values()];
 }
 root.FloorMapMath={project,bounds,cells};
 if(typeof document==='undefined')return;
 const canvas=document.getElementById('floorView');if(!canvas)return;
 const ctx=canvas.getContext('2d'),plane=document.getElementById('floorPlane'),angle=document.getElementById('floorAngle'),detail=document.getElementById('floorDetail');
 let landmarks=[],path=[],state='Waiting',stamp=0,zoom=1,pan=[0,0],drag=null,objects=[],origin=null,surfaces=[],drone=null;
 function draw(){
  const ratio=window.devicePixelRatio||1;
  canvas.width=Math.max(1,Math.round(canvas.clientWidth*ratio));canvas.height=Math.max(1,Math.round(canvas.clientHeight*ratio));
  const a=Number(angle.value)*Math.PI/180,pts=project(landmarks,plane.value,a),route=project(path,plane.value,a);
  const surfacePoints=project(surfaces,plane.value,a);
  const fit=bounds(pts.concat(route,surfacePoints,drone?project([drone],plane.value,a):[])),size=fit.span/Number(detail.value);
  const scale=Math.min(canvas.width,canvas.height)*.83/fit.span*zoom;
  const xy=p=>[canvas.width/2+(p[0]-fit.center[0])*scale+pan[0]*ratio,canvas.height/2-(p[1]-fit.center[1])*scale+pan[1]*ratio];
  ctx.fillStyle='#101b2c';ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.save();ctx.beginPath();ctx.rect(0,0,canvas.width,canvas.height);ctx.clip();
  if(document.getElementById('floorSurfaces').checked)for(const cell of cells(surfacePoints,size)){
   const p=xy([cell.x*size,(cell.y+1)*size]);ctx.fillStyle='rgba(190,170,225,.25)';
   ctx.fillRect(p[0],p[1],Math.max(2,size*scale),Math.max(2,size*scale));
  }
  for(const cell of document.getElementById('floorFeatures').checked?cells(pts,size):[]){
   const p=xy([cell.x*size,(cell.y+1)*size]);
   ctx.fillStyle=`rgba(91,195,255,${Math.min(.95,.25+Math.log2(cell.count+1)*.16)})`;
   ctx.fillRect(p[0],p[1],Math.max(1,size*scale),Math.max(1,size*scale));
  }
  for(const object of objects){
   const corners=[];
   for(const x of [object.min[0],object.max[0]])for(const y of [object.min[1],object.max[1]])for(const z of [object.min[2],object.max[2]])corners.push([x,y,z]);
   const projected=project(corners,plane.value,a).map(xy);
   const xs=projected.map(p=>p[0]),ys=projected.map(p=>p[1]);
   const x=Math.min(...xs),y=Math.min(...ys),w=Math.max(6*ratio,Math.max(...xs)-x),h=Math.max(6*ratio,Math.max(...ys)-y);
   ctx.fillStyle='rgba(78,177,160,.22)';ctx.strokeStyle=object.tentative?'#b6bdc7':'#7be0c8';
   ctx.lineWidth=2*ratio;ctx.setLineDash(object.tentative?[5*ratio,4*ratio]:[]);
   ctx.fillRect(x,y,w,h);ctx.strokeRect(x,y,w,h);ctx.setLineDash([]);
   ctx.fillStyle='#fff';ctx.font=`${13*ratio}px sans-serif`;
   ctx.fillText(`${object.label}${object.tentative?' ?':''}`,x+3*ratio,y-5*ratio);
  }
  ctx.strokeStyle='#ffae51';ctx.lineWidth=2*ratio;ctx.beginPath();
  route.forEach((p,i)=>{const q=xy(p);if(i)ctx.lineTo(...q);else ctx.moveTo(...q);});ctx.stroke();
  for(const [index,color] of [[0,'#75e4a4'],[route.length-1,'#ffae51']]){
   if(!route[index])continue;const p=xy(route[index]);ctx.fillStyle=color;ctx.beginPath();ctx.arc(...p,5*ratio,0,Math.PI*2);ctx.fill();
  }
  if(drone){const p=xy(project([drone],plane.value,a)[0]);ctx.strokeStyle='#7cecf2';ctx.lineWidth=2*ratio;ctx.beginPath();ctx.arc(...p,7*ratio,0,Math.PI*2);ctx.stroke();}
  ctx.restore();ctx.fillStyle='#fff';ctx.font=`${13*ratio}px sans-serif`;
  ctx.fillText('EXPERIMENTAL · orange: native motion path · cyan: drone · dashed: tentative',12*ratio,22*ratio);
  const age=stamp?Math.max(0,Date.now()/1000-stamp):null;
  document.getElementById('floorSummary').textContent=`${age!==null&&age>3?'STALE SLAM EXPORT — ':''}${state} | ${pts.length} transformed landmarks | ${route.length} onboard motion samples | ${surfacePoints.length} depth surface samples. ${plane.value.toUpperCase()} projection. Drag to pan; scroll to zoom. Units and floor direction are unverified.`;
 }
 for(const control of [plane,angle,detail])control.addEventListener('input',()=>{zoom=1;pan=[0,0];draw();});
 document.getElementById('floorFeatures').onchange=draw;
 document.getElementById('floorSurfaces').onchange=draw;
 async function refreshObjects(){
  try{
   const response=await fetch('floorplan.json?t='+Date.now(),{cache:'no-store'});
   if(!response.ok)throw Error('unavailable');
   const data=await response.json();
   const fresh=Date.now()/1000-data.timestamp<3 && Math.abs(data.map_timestamp-stamp)<2 && data.map_origin===origin;
   objects=fresh?data.objects:[];
   document.getElementById('floorEvidence').textContent=objects.length?objects.map(o=>`${o.label}: ${(o.sources||[]).join(' + ')} | ${o.observations} frame observations | ${o.support} supporting landmark IDs`).join('\n'):'No accepted object geometry yet.';
   if(fresh&&['native_mvo_unverified','slam_arbitrary'].includes(data.world_frame)){
    landmarks=data.landmarks||[];path=data.path||[];surfaces=data.surface_points||[];drone=data.drone_position;
    const i=data.inputs||{},a=data.alignment||{};
    document.getElementById('mapFusionStatus').textContent=`${data.message}\nInputs: ${i.telemetry_frames??0} telemetry frames | ${i.YOLO_frames??0} YOLO frames | ${i.depth_frames??0} relative-depth frames | ${i.SLAM_landmarks??0} SLAM landmarks\n`+
     `Coordinate alignment: ${a.accepted?'accepted experimentally':'waiting/rejected'} (${a.inliers??0}/${a.pairs??0} pose pairs). IMU orientation: ${a.IMU_orientation_accepted?'aligned experimentally':'visual rotation fallback'}\n`+
     `Depth frames contributing: ${data.depth_frames_used??0} | IMU-oriented frames: ${data.imu_frames_used??0} | Rejected frames: ${JSON.stringify(data.rejected_frames||{})}\n`+
     `Geometry trails newest telemetry image by ${data.geometry_lag_seconds?.toFixed(1)??'unknown'} s; native pose is ${data.pose_age_in_recording_seconds?.toFixed(2)??'unknown'} s behind that image.`;
   }
   document.getElementById('floorObjects').textContent=fresh?`${objects.length} tentative object footprints · ${data.matched_frames} matched frames. All inputs are quality-gated; unavailable geometry stays unplaced.`:'Combined map is stale; waiting for matching input data.';
  }catch(_){objects=[];document.getElementById('floorObjects').textContent='Waiting for object placement. Run with --vision and SLAM enabled.';}
  draw();setTimeout(refreshObjects,500);
 }
 document.getElementById('floorFit').onclick=()=>{zoom=1;pan=[0,0];draw();};
 canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};
 canvas.onpointermove=e=>{if(!drag)return;pan[0]+=e.clientX-drag[0];pan[1]+=e.clientY-drag[1];drag=[e.clientX,e.clientY];draw();};
 canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;};
 canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.2,Math.min(20,zoom*Math.exp(-e.deltaY*.001)));draw();},{passive:false});
 window.addEventListener('resize',draw);
 root.floorMapViewer={setData(p,c,s,t,o){if(o!==origin){objects=[];landmarks=[];surfaces=[];}origin=o;state=s||'Unknown';stamp=t||0;draw();}};
 setInterval(draw,1000);draw();refreshObjects();
})(typeof window==='undefined'?globalThis:window);
