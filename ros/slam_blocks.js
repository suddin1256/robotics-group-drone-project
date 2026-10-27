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
 let yaw=.3,pitch=.8,zoom=1.15,drag=false,lastX=0,lastY=0,pending=false,concept=true;
 function fit(){
  if(concept){center=[0,-.6,.6];radius=3.4;return;}
  const fitted=bounds(points);center=fitted.center;radius=fitted.radius;
 }
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
 function ring(position,rx,rz,color,width=1,fill=null){
  ctx.beginPath();
  for(let i=0;i<=48;i++){
   const a=i*Math.PI*2/48,p=project([position[0]+Math.cos(a)*rx,position[1],position[2]+Math.sin(a)*rz]);
   if(i)ctx.lineTo(p[0],p[1]);else ctx.moveTo(p[0],p[1]);
  }
  ctx.closePath();if(fill){ctx.fillStyle=fill;ctx.fill();}ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();
 }
 function conceptScene(ratio){
  const background=ctx.createLinearGradient(0,0,0,canvas.height);
  background.addColorStop(0,'#ffffff');background.addColorStop(1,'#e9edf1');
  ctx.fillStyle=background;ctx.fillRect(0,0,canvas.width,canvas.height);
  for(let i=-5;i<=5;i++){
   line([i,0,-4],[i,0,5],'#dfe5ea');line([-5,0,i],[5,0,i],'#dfe5ea');
  }
  const shapes=[
   {p:[-2.1,-.85,.6],r:[.75,.85,2.1],c:[178,187,193]},
   {p:[2.25,-.65,1.9],r:[.7,.65,1.6],c:[185,193,199]},
   {p:[-.35,-.55,3.65],r:[1.4,.55,.62],c:[194,200,204]},
   {p:[1.25,-.75,-.1],r:[.24,.65,.25],c:[235,153,57]},
   {p:[1.25,-1.5,-.1],r:[.22,.22,.22],c:[242,171,77]},
   {p:[0,-.32,-1.75],r:[.25,.09,.32],c:[46,143,166]}
  ];
  for(const shape of shapes)ring([shape.p[0],.015,shape.p[2]],shape.r[0]*1.1,shape.r[2]*1.08,'transparent',0,'rgba(60,70,80,.065)');
  ring([0,0,-1.75],1,1,'#95c5d0',ratio);ring([0,0,-1.75],1.65,1.65,'#c3dce1',ratio);
  const polygons=[];
  for(const shape of shapes){
   const rows=18,columns=32;
   function vertex(row,column){
    const latitude=-Math.PI/2+row*Math.PI/rows,longitude=column*Math.PI*2/columns;
    return [shape.p[0]+shape.r[0]*Math.cos(latitude)*Math.cos(longitude),
            shape.p[1]+shape.r[1]*Math.sin(latitude),
            shape.p[2]+shape.r[2]*Math.cos(latitude)*Math.sin(longitude)];
   }
   for(let row=0;row<rows;row++)for(let column=0;column<columns;column++){
    const world=[vertex(row,column),vertex(row+1,column),vertex(row+1,column+1),vertex(row,column+1)];
    const projected=world.map(project);
    const middle=[0,1,2].map(i=>world.reduce((sum,p)=>sum+p[i],0)/4);
    const normal=middle.map((v,i)=>(v-shape.p[i])/(shape.r[i]*shape.r[i]));
    const length=Math.hypot(...normal)||1;
    const light=Math.max(0,(-.35*normal[0]-.85*normal[1]-.4*normal[2])/length);
    const shade=.65+.35*light;
    polygons.push({vertices:projected,z:projected.reduce((sum,p)=>sum+p[2],0)/4,
                   color:`rgb(${shape.c.map(v=>Math.round(v*shade)).join(',')})`});
   }
  }
  polygons.sort((a,b)=>b.z-a.z);
  for(const polygon of polygons){
   ctx.beginPath();polygon.vertices.forEach((p,i)=>{if(i)ctx.lineTo(p[0],p[1]);else ctx.moveTo(p[0],p[1]);});
   ctx.closePath();ctx.fillStyle=polygon.color;ctx.fill();ctx.strokeStyle=polygon.color;ctx.lineWidth=.5;ctx.stroke();
  }
  const drone=[0,-.32,-1.75];
  for(const x of [-.36,.36])for(const z of [-.36,.36]){
   const rotor=[x,drone[1],drone[2]+z];
   line(drone,rotor,'#3e535c',3*ratio);
   ring(rotor,.23,.23,'#397f91',1.5*ratio,'rgba(255,255,255,.7)');
  }
  const droneLabel=project([0,-.32,-2.35]);
  ctx.fillStyle='#286478';ctx.font=`${11*ratio}px system-ui`;
  ctx.fillText('DRONE · illustration',droneLabel[0]-48*ratio,droneLabel[1]+18*ratio);
  ctx.fillStyle='#fff2d9';ctx.fillRect(10*ratio,10*ratio,Math.min(canvas.width-20*ratio,420*ratio),49*ratio);
  ctx.fillStyle='#825417';ctx.font=`bold ${13*ratio}px system-ui`;
  ctx.fillText('CONCEPT PREVIEW · synthetic obstacles',18*ratio,29*ratio);
  ctx.font=`${11*ratio}px system-ui`;ctx.fillText('Not camera-derived · no measured distances · no flight control',18*ratio,47*ratio);
 }
 function draw(){
  pending=false;
  const ratio=Math.min(window.devicePixelRatio||1,2);
  canvas.width=Math.max(1,Math.round(canvas.clientWidth*ratio));
  canvas.height=Math.max(1,Math.round(canvas.clientHeight*ratio));
  if(concept){conceptScene(ratio);return;}
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
  if(concept)return;
  if(automatic.checked)fit();
  rebuild();requestDraw();
 }
 function setMode(isConcept){
  concept=isConcept;detail.disabled=concept;automatic.disabled=concept;
  detail.parentElement.style.display=concept?'none':'';
  automatic.parentElement.style.display=concept?'none':'';
  const telemetry=document.getElementById('mapTelemetry');
  if(telemetry)telemetry.style.display=concept?'none':'';
  document.getElementById('blocksConcept').setAttribute('aria-pressed',String(concept));
  document.getElementById('blocksData').setAttribute('aria-pressed',String(!concept));
  fit();
  if(concept)summary.textContent='Planned appearance only: gray example obstacles, orange example person, blue drone. The scene is synthetic and does not use YOLO, MiDaS, telemetry or SLAM measurements. Drag to orbit; scroll to zoom.';
  else rebuild();
  requestDraw();
 }
 document.getElementById('blocksConcept').onclick=()=>setMode(true);
 document.getElementById('blocksData').onclick=()=>setMode(false);
 document.getElementById('blocksFit').onclick=()=>{fit();if(!concept)rebuild();requestDraw();};
 document.getElementById('blocksReset').onclick=()=>{yaw=.3;pitch=.8;zoom=1.15;fit();if(!concept)rebuild();requestDraw();};
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
 setMode(true);
})(typeof window==='undefined'?globalThis:window);
