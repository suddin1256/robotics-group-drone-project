/* Display-only voxelization of sparse landmarks; no occupancy or navigation claims. */
(function(root){
 'use strict';
 function valid(p){return Array.isArray(p)&&p.length===3&&p.every(Number.isFinite);}
 function bounds(input){
  const points=input.filter(valid);
  if(!points.length)return {center:[0,0,0],radius:1};
  const center=[0,1,2].map(i=>{
   const values=points.map(p=>p[i]).sort((a,b)=>a-b);
   return values[Math.floor(values.length/2)];
  });
  const distances=points.map(p=>Math.hypot(...p.map((v,i)=>v-center[i]))).sort((a,b)=>a-b);
  return {center,radius:Math.max(distances[Math.floor(distances.length*.95)],.001)};
 }
 function voxelize(input,size){
  if(!Number.isFinite(size)||size<=0)throw Error('Block size must be positive');
  const cells=new Map();
  for(const point of input){
   if(!valid(point))continue;
   const index=point.map(v=>Math.floor(v/size));
   const key=index.join(',');
   if(!cells.has(key))cells.set(key,{position:index.map(v=>(v+.5)*size),count:0});
   cells.get(key).count++;
  }
  return [...cells.values()];
 }
 root.SlamBlockMath={bounds,voxelize};
 if(typeof document==='undefined')return;
 const canvas=document.getElementById('blockView');
 if(!canvas)return;
 const ctx=canvas.getContext('2d');
 const detail=document.getElementById('blocksDetail');
 const automatic=document.getElementById('blocksAuto');
 const summary=document.getElementById('blocksSummary');
 let points=[],cameras=[],center=[0,0,0],radius=1,cells=[],cellSize=1,totalCells=0;
 let yaw=-.55,pitch=.4,zoom=1,drag=false,lastX=0,lastY=0,pending=false;
 function fit(){const fitted=bounds(points);center=fitted.center;radius=fitted.radius;}
 function rebuild(){
  cellSize=radius/Number(detail.value);
  const all=voxelize(points,cellSize);
  totalCells=all.length;
  cells=all.sort((a,b)=>b.count-a.count).slice(0,1800);
  summary.textContent=`${points.length} sparse landmarks → ${totalCells} landmark blocks`+
   (cells.length<totalCells?` (${cells.length} shown)`:'')+
   `. ${cameras.length} orange camera-keyframe markers. Drag to rotate; scroll to zoom. Scale is arbitrary.`;
 }
 function project(point){
  const a=point.map((v,i)=>(v-center[i])/radius);
  const x=a[0]*Math.cos(yaw)+a[2]*Math.sin(yaw);
  const z=-a[0]*Math.sin(yaw)+a[2]*Math.cos(yaw);
  const y=a[1]*Math.cos(pitch)-z*Math.sin(pitch);
  const depth=a[1]*Math.sin(pitch)+z*Math.cos(pitch);
  const s=Math.min(canvas.width,canvas.height)*.34*zoom;
  return [canvas.width/2+x*s,canvas.height/2+y*s,depth];
 }
 function line(a,b,color,width=1){
  const p=project(a),q=project(b);ctx.strokeStyle=color;ctx.lineWidth=width;
  ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();
 }
 function draw(){
  pending=false;
  const ratio=Math.min(window.devicePixelRatio||1,2);
  canvas.width=Math.max(1,Math.round(canvas.clientWidth*ratio));
  canvas.height=Math.max(1,Math.round(canvas.clientHeight*ratio));
  ctx.fillStyle='#0c1726';ctx.fillRect(0,0,canvas.width,canvas.height);
  // Reference coordinate plane only; never interpreted as a detected floor.
  for(let i=-6;i<=6;i++){
   const value=i*radius/6;
   line([center[0]+value,center[1],center[2]-radius],[center[0]+value,center[1],center[2]+radius],'#243449');
   line([center[0]-radius,center[1],center[2]+value],[center[0]+radius,center[1],center[2]+value],'#243449');
  }
  const signs=[[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
  const faces=[[0,1,2,3],[4,7,6,5],[0,4,5,1],[3,2,6,7],[0,3,7,4],[1,5,6,2]];
  const shades=['#4e9bbd','#78c9dd','#b4e8ed','#3c809e','#66b7cf','#8dd7e2'];
  const ordered=cells.map(cell=>({...cell,depth:project(cell.position)[2]})).sort((a,b)=>b.depth-a.depth);
  for(const cell of ordered){
   const half=cellSize*.43;
   const vertices=signs.map(s=>project(cell.position.map((v,i)=>v+s[i]*half)));
   const visible=faces.map((indices,i)=>({indices,i,z:indices.reduce((sum,j)=>sum+vertices[j][2],0)/4})).sort((a,b)=>b.z-a.z);
   for(const face of visible){
    ctx.beginPath();face.indices.forEach((index,i)=>{
     const v=vertices[index];if(i)ctx.lineTo(v[0],v[1]);else ctx.moveTo(v[0],v[1]);
    });ctx.closePath();ctx.fillStyle=shades[face.i];ctx.fill();
   }
  }
  ctx.fillStyle='#ffae55';
  for(const camera of cameras){
   const p=project(camera);ctx.beginPath();ctx.arc(p[0],p[1],3*ratio,0,Math.PI*2);ctx.fill();
  }
  ctx.font=`${12*ratio}px system-ui`;ctx.fillStyle='#a8bed0';
  ctx.fillText('LANDMARK BLOCKS · arbitrary scale · unknown empty space',12*ratio,22*ratio);
 }
 function requestDraw(){if(!pending){pending=true;requestAnimationFrame(draw);}}
 function setData(newPoints,newCameras){
  points=Array.isArray(newPoints)?newPoints.filter(valid):[];
  cameras=Array.isArray(newCameras)?newCameras.filter(valid):[];
  if(automatic.checked)fit();
  rebuild();requestDraw();
 }
 document.getElementById('blocksFit').onclick=()=>{fit();rebuild();requestDraw();};
 document.getElementById('blocksReset').onclick=()=>{yaw=-.55;pitch=.4;zoom=1;fit();rebuild();requestDraw();};
 document.getElementById('blocksTop').onclick=()=>{yaw=0;pitch=Math.PI/2;requestDraw();};
 detail.oninput=()=>{rebuild();requestDraw();};
 automatic.onchange=()=>{if(automatic.checked){fit();rebuild();requestDraw();}};
 canvas.onpointerdown=e=>{drag=true;lastX=e.clientX;lastY=e.clientY;automatic.checked=false;canvas.setPointerCapture(e.pointerId);};
 canvas.onpointermove=e=>{
  if(!drag)return;yaw+=(e.clientX-lastX)*.008;pitch=Math.max(-1.55,Math.min(1.55,pitch+(e.clientY-lastY)*.008));
  lastX=e.clientX;lastY=e.clientY;requestDraw();
 };
 canvas.onpointerup=canvas.onpointercancel=()=>{drag=false;};
 canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.1,Math.min(15,zoom*Math.exp(-e.deltaY*.001)));requestDraw();},{passive:false});
 window.addEventListener('resize',requestDraw);
 root.slamBlockViewer={setData};
 requestDraw();
})(typeof window==='undefined'?globalThis:window);
