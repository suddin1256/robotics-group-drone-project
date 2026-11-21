'use strict';
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state={rooms:[],profiles:[],active:null},profileId=localStorage.getItem('tellotubby-profile') || localStorage.getItem('roomflight-profile'),room=null,lastKey='',viewer=null,polling=false;
const date=t=>new Date(t*1000).toLocaleString();
function toast(message){$('toast').textContent=message;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,9000);}
async function api(path,data){const r=await fetch('/api/'+path,{cache:'no-store',...(data?{method:'POST',headers:{'Content-Type':'application/json','X-App-Token':window.APP_TOKEN},body:JSON.stringify(data)}:{})});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
function chosen(){return state.profiles.find(p=>p.id===profileId);}
function route(){return location.hash.slice(1).split('/');}
function navigate(value){location.hash=value;lastKey='';}
function button(label,action,cls='',extra=''){return `<button class="${cls}" data-action="${action}" ${extra}>${label}</button>`;}
function sessionChip(){const a=state.active;$('sessionChip').innerHTML=a?`<a href="#session/${a.id}"><span class="dot"></span>${a.kind==='live'?'Recorded flight':'Playback'} · ${esc(a.state)} →</a>`:'No session running';}
function profileChip(){const p=chosen();$('profileChip').innerHTML=p?`<span class="avatar">${esc(p.name[0].toUpperCase())}</span><strong>${esc(p.name)}</strong> ${button('Change','profile','small')}<p style="font-size:11px;margin:8px 0 0">${esc(p.settings.label)}</p>`:button('Choose profile','profile');}
function library(){
 $('breadcrumb').textContent='Workspace / Room library';
 $('content').innerHTML=`<div class="hero"><div><p class="eyebrow">YOUR FLIGHTS, IN ONE PLACE</p><h1>Room library</h1><p>Collect flights, revisit recordings, and build a persistent 3D view for each room.</p></div>${button('+ Create room','new-room','primary')}</div><div class="section-label">${state.rooms.length} ROOM${state.rooms.length===1?'':'S'} · SAVED ON THIS LAPTOP</div><div class="cards">${state.rooms.map(r=>`<a class="card room-card" href="#room/${r.id}/flights"><div class="room-icon">▱</div><h3>${esc(r.name)}</h3><p>${r.flights} saved flight${r.flights===1?'':'s'} · ${r.maps} map capture${r.maps===1?'':'s'}</p><span class="row"><small>Open room</small><span>↗</span></span></a>`).join('')}</div>${state.rooms.length?'':`<div class="empty"><h3>Your first room starts here.</h3><p>Create “Robotics classroom”, then add a recording or make a new flight.</p>${button('Create your first room','new-room','primary')}</div>`}<details><summary>Where is my data?</summary><p>${esc(state.storage)}<br>Existing recordings are linked, not moved. New flights and reconstruction data are saved inside their room folder. They are excluded from Git.</p></details>`;
}
function roomPage(tab){
 $('breadcrumb').textContent='Room library / '+room.name;
 const active=!!state.active;
 $('content').innerHTML=`<div class="hero"><div><p class="eyebrow">ROOM WORKSPACE</p><h1>${esc(room.name)}</h1><p>${room.recordings.length} recordings · ${room.maps.length} saved map captures</p></div><div class="actions">${button('+ New recorded flight','connect','primary',active?'disabled':'')}${button('Add existing recording','discover')}</div></div><div class="tabs"><a class="${tab==='flights'?'current':''}" href="#room/${room.id}/flights">Flights & recordings</a><a class="${tab==='map'?'current':''}" href="#room/${room.id}/map">3D room view</a></div><div id="roomBody"></div>`;
 if(tab==='map')mapPage();else flightsPage();
}
function flightsPage(){
 $('roomBody').innerHTML=`<div id="importBox" hidden class="card"><h3>Add a recording</h3><p>Choose a complete ROS bag folder from Documents/tello-recordings. Linking keeps the original files in place.</p><label for="existingRecording">Recording folder</label><select id="existingRecording"></select><div class="actions" style="margin-top:14px">${button('Link to this room','import','primary')}${button('Cancel','cancel-import')}</div></div>${room.recordings.length?`<div class="card"><div class="row"><h3>Saved flights</h3><small>Playback never connects to the drone</small></div>${room.recordings.map(r=>`<div class="flight-row"><div><strong>${esc(r.name)}</strong><small>${r.linked?'Linked recording':'Recorded in this room'} · ${date(r.created)}</small></div><div class="actions">${button('View & process →','play','primary',`data-id="${r.id}" ${state.active?'disabled':''}`)}${button('Camera only','quick','',`data-id="${r.id}" ${state.active?'disabled':''}`)}</div></div>`).join('')}</div>`:`<div class="empty"><h3>No flights here yet.</h3><p>Link an existing recording to start building this room, or connect the drone for a new flight.</p>${button('Find existing recordings','discover','primary')}</div>`}<div class="section-label">PROCESSING HISTORY</div>${room.sessions.length?`<div class="card">${room.sessions.map(s=>`<div class="flight-row"><div><strong>${s.kind==='live'?'Recorded flight':'Recording playback'}</strong><small>${date(s.created)} · ${esc(s.state)}</small>${s.error?`<small class="status-warn">${esc(s.error)}</small>`:''}</div>${button('View session','session','',`data-id="${s.id}"`)}</div>`).join('')}</div>`:'<p>No processing sessions yet. Viewing a recording creates a saved session and preserves its map output.</p>'}`;
}
async function mapPage(){
 $('roomBody').innerHTML=`<div class="map-tools"><select id="mapChoice" aria-label="Map capture"><option value="room">Combined room reconstruction</option>${room.maps.map((m,i)=>`<option value="${m.id}">Capture ${room.maps.length-i} · ${m.landmarks} landmarks · ${esc(m.state)}</option>`).join('')}</select>${button('Fit view','fit-map')}${button('Update room map','rebuild')}<span class="pill">Drag to orbit · scroll to zoom</span></div><canvas id="roomCanvas" class="map-view" aria-label="Interactive 3D room reconstruction"></canvas><p id="mapStatus" class="meta-line">Loading saved reconstruction…</p><div class="callout">Experimental observed surfaces. Unknown space is not clear space. Separate flights are combined only when matching landmarks pass geometric checks; otherwise they stay available as individual captures. Path planning comes later.</div><div id="mapSources"></div>`;
 viewer=new CloudViewer($('roomCanvas'));$('mapChoice').onchange=()=>loadMap();await loadMap();
}
async function loadMap(){
 if(!$('mapChoice'))return;
 const choice=$('mapChoice').value;
 try{
  const d=await api(choice==='room'?`room-map/${room.id}/room-map.json`:`map/${choice}/map.json`);
  if(!$('mapStatus'))return;
  const points=d.points||[];viewer.set(points,d.paths||(d.cameras?[{points:d.cameras}]:[]));
  $('mapStatus').textContent=points.length?`${points.length.toLocaleString()} displayed points/cells · ${choice==='room'?d.units:'arbitrary SLAM units'} · ${d.aligned_maps??1} aligned captures · ${d.separate_maps??0} separate. Green points have support from more than one aligned capture.`:'No reconstruction saved yet. Process a recording with all systems to create a map. A low-texture flight may not initialize SLAM.';
  $('mapSources').innerHTML=(d.sessions||[]).length?`<div class="card"><h3>Capture alignment</h3>${d.sessions.map((s,i)=>`<p><span class="${s.aligned?'status-ok':'status-warn'}">${s.aligned?'Aligned':'Kept separate'}</span> · Capture ${i+1}${s.reason?' — '+esc(s.reason):' · '+(s.landmarks||0)+' landmarks'}</p>`).join('')}</div>`:'';
 }catch(e){if($('mapStatus'))$('mapStatus').textContent=e.message;}
}
function sessionPage(id){
 const a=state.active?.id===id?state.active:null;
 $('breadcrumb').textContent='Room workspace / '+(a?.kind==='live'?'Recorded flight':'Playback');
 if(!a){$('content').innerHTML=`<div class="hero"><div><h1>Session saved</h1><p>Return to the room to view the recording and saved map captures.</p></div>${button('Back to room','back-room','primary')}</div><details open><summary>Session output</summary><pre id="sessionLog">Loading…</pre></details>`;api('log/'+id).then(d=>{if($('sessionLog'))$('sessionLog').textContent=d.log;}).catch(e=>toast(e.message));return;}
 $('content').innerHTML=`<div class="hero"><div><p class="eyebrow">${a.kind==='live'?'LIVE · RECORDING TO THIS ROOM':'RECORDED FLIGHT · CONTROLS DISABLED'}</p><h1>${a.kind==='live'?'Flight workspace':'Recording workspace'}</h1><p id="sessionStatus">${esc(a.state)} · All processing output stays with this room.</p></div><div class="actions">${a.kind==='live'?button('Request landing','land','danger'):''}${button(a.kind==='live'?'End flight session':'End playback','stop')}</div></div>${a.kind==='live'?'<label class="check"><input type="checkbox" id="landedCheck"> Drone is physically landed; ready to finish saving.</label>':''}<div id="frameLoading" class="loading"><div class="spinner"></div><h3>Starting your session</h3><p>The camera and processing workers are starting. The flight controls will appear here.</p></div><iframe id="flightFrame" class="session-frame" title="Existing Tello flight and processing dashboard" hidden allow="fullscreen"></iframe><details><summary>Startup and processing log</summary><pre id="sessionLog"></pre></details>`;updateSession(a);
}
function updateSession(a){
 if(!$('sessionStatus'))return;
 $('sessionStatus').textContent=a.state==='stopping'?'Finishing recording and saving maps. Keep this window open.':`${a.state} · Output is being saved to this room.`;
 $('sessionLog').textContent=a.log_tail||'Waiting for startup output…';
 if(a.dashboard_ready&&$('flightFrame').getAttribute('src')!==a.dashboard_url){$('flightFrame').src=a.dashboard_url;$('flightFrame').hidden=false;$('frameLoading').hidden=true;}
}
async function render(force=false){
 const r=route();let key=location.hash;
 if(r[0]==='room'&&r[1]){
  room=await api('rooms/'+r[1]);key+=':'+room.recordings.length+':'+room.sessions.map(s=>s.state).join(',')+':'+room.maps.length;
  if(force||key!==lastKey){lastKey=key;roomPage(r[2]||'flights');}
 }else if(r[0]==='session'&&r[1]){
  const a=state.active?.id===r[1]?state.active:null;if(a)room=await api('rooms/'+a.room_id);
  key+=':'+(a?'active':'done');if(force||key!==lastKey){lastKey=key;sessionPage(r[1]);}else if(a)updateSession(a);
 }else{key+=':'+state.rooms.map(r=>r.id+r.flights+r.maps).join(',');if(force||key!==lastKey){lastKey=key;library();}}
}
async function poll(){
 if(polling)return;polling=true;
 try{state=await api('state');sessionChip();profileChip();if(!chosen()&&!$('profileDialog').open)$('profileDialog').showModal();await render();if(route()[2]==='map')await loadMap();}
 catch(e){toast(e.message);}finally{polling=false;}
}
async function start(kind,recordingId,quick=false){
 if(!chosen()){$('profileDialog').showModal();return;}
 const a=await api('start',{room_id:room.id,profile_id:profileId,kind,recording_id:recordingId,quick,ready:kind==='live'&&$('readyFlight').checked});
 if($('connectDialog').open)$('connectDialog').close();state.active=a;navigate('session/'+a.id);await poll();
}
document.addEventListener('click',async e=>{
 const el=e.target.closest('[data-action]');if(!el)return;const action=el.dataset.action;
 try{
  if(action==='profile'){if(state.active)throw Error('End the current session before switching profiles.');$('profileDialog').showModal();}
  if(action==='new-room')$('roomDialog').showModal();
  if(action==='connect'){$('readyFlight').checked=false;$('connectDialog').showModal();}
  if(action==='discover'){
   if(route()[2]==='map'){navigate('room/'+room.id+'/flights');await render(true);}
   const items=await api('discover');$('importBox').hidden=false;$('existingRecording').innerHTML=items.map(x=>`<option value="${esc(x.path)}">${esc(x.name)}</option>`).join('');if(!items.length)toast('No ROS bag folders found in Documents/tello-recordings. Put transferred recordings there first.');
  }
  if(action==='cancel-import')$('importBox').hidden=true;
  if(action==='import'){await api('import',{room_id:room.id,path:$('existingRecording').value});await render(true);await poll();}
  if(action==='play'||action==='quick')await start('replay',el.dataset.id,action==='quick');
  if(action==='session')navigate('session/'+el.dataset.id);
  if(action==='land'){await api('land',{});toast('Landing requested. Watch the drone and confirm it is landed before ending.');}
  if(action==='stop'){
   await api('stop',{landed:$('landedCheck')?.checked===true});await poll();
  }
  if(action==='back-room')navigate(room?'room/'+room.id+'/flights':'');
  if(action==='fit-map')viewer?.fit();
  if(action==='rebuild'){await api('rebuild',{room_id:room.id});toast('Room reconstruction requested. Existing captures stay saved.');}
 }catch(error){toast(error.message);}
});
$('profileForm').onsubmit=async e=>{e.preventDefault();try{const p=await api('profiles',{name:$('profileName').value});profileId=p.id;localStorage.setItem('tellotubby-profile',profileId);$('profileDialog').close();await poll();}catch(e){toast(e.message);}};
document.querySelectorAll('[data-name]').forEach(b=>b.onclick=()=>{$('profileName').value=b.dataset.name;$('profileForm').requestSubmit();});
$('roomForm').onsubmit=async e=>{e.preventDefault();try{const r=await api('rooms',{name:$('roomName').value});$('roomDialog').close();$('roomForm').reset();navigate('room/'+r.id+'/flights');await poll();}catch(e){toast(e.message);}};
$('cancelRoom').onclick=()=>$('roomDialog').close();$('cancelConnect').onclick=()=>$('connectDialog').close();$('startFlight').onclick=()=>{if(!$('readyFlight').checked){toast('Connect to TELLO Wi-Fi and check the ready box first.');return;}start('live').catch(e=>toast(e.message));};
window.addEventListener('hashchange',()=>{lastKey='';render().catch(e=>toast(e.message));});

class CloudViewer{
 constructor(canvas){this.canvas=canvas;this.yaw=.65;this.pitch=.45;this.zoom=1;this.center=[0,0,0];this.radius=1;this.points=[];this.paths=[];let drag=null;
  canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};canvas.onpointermove=e=>{if(!drag)return;this.yaw+=(e.clientX-drag[0])*.008;this.pitch=Math.max(-1.5,Math.min(1.5,this.pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];this.draw();};canvas.onpointerup=()=>drag=null;canvas.onpointercancel=()=>drag=null;canvas.onwheel=e=>{e.preventDefault();this.zoom=Math.max(.1,Math.min(20,this.zoom*Math.exp(-e.deltaY*.001)));this.draw();};this.resize=new ResizeObserver(()=>this.draw());this.resize.observe(canvas);
 }
 set(points,paths){const first=!this.points.length;this.points=points.filter(p=>p.length>=3&&p.slice(0,3).every(Number.isFinite));this.paths=paths;if(first)this.fit();else this.draw();}
 fit(){if(this.points.length){const axes=[0,1,2].map(i=>this.points.map(p=>p[i]).sort((a,b)=>a-b));const lo=axes.map(a=>a[Math.floor(a.length*.01)]),hi=axes.map(a=>a[Math.min(a.length-1,Math.floor(a.length*.99))]);this.center=lo.map((v,i)=>(v+hi[i])/2);this.radius=Math.max(...hi.map((v,i)=>v-lo[i]),.001)/2;}this.zoom=1;this.draw();}
 project(point){const [x,y,z]=point.map((v,i)=>v-this.center[i]),c=Math.cos(this.yaw),s=Math.sin(this.yaw),a=c*x-s*y,b=s*x+c*y;return [a,Math.cos(this.pitch)*z-Math.sin(this.pitch)*b,Math.sin(this.pitch)*z+Math.cos(this.pitch)*b];}
 draw(){const c=this.canvas;if(!c.isConnected){this.resize.disconnect();return;}const ratio=devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;c.width=w*ratio;c.height=h*ratio;const ctx=c.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#101922';ctx.fillRect(0,0,w,h);const scale=Math.min(w,h)*.36/this.radius*this.zoom;const screen=p=>{const q=this.project(p);return [w/2+q[0]*scale,h/2-q[1]*scale,q[2]];};
  ctx.strokeStyle='#20313e';ctx.lineWidth=1;for(let i=-4;i<=4;i++){ctx.beginPath();ctx.moveTo(w/2+i*50,0);ctx.lineTo(w/2+i*50,h);ctx.stroke();ctx.beginPath();ctx.moveTo(0,h/2+i*50);ctx.lineTo(w,h/2+i*50);ctx.stroke();}
  const pts=this.points.map(p=>[...screen(p),p[3]||1]).sort((a,b)=>a[2]-b[2]);for(const p of pts){if(p[0]<0||p[0]>w||p[1]<0||p[1]>h)continue;ctx.fillStyle=p[3]>1?'#b8e8c6':'#86a6bd';ctx.globalAlpha=p[3]>1?.9:.6;ctx.fillRect(p[0],p[1],p[3]>1?2.8:2,p[3]>1?2.8:2);}ctx.globalAlpha=1;
  this.paths.forEach((route,i)=>{ctx.strokeStyle=['#edba7d','#e99d9d','#90b7ee'][i%3];ctx.lineWidth=1.5;ctx.beginPath();(route.points||[]).forEach((p,j)=>{const q=screen(p);j?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);});ctx.stroke();});ctx.fillStyle='#819baa';ctx.font='12px system-ui';ctx.fillText(this.points.length?'OBSERVED GEOMETRY · experimental alignment':'No saved geometry yet',18,25);
 }
}
poll();setInterval(poll,3000);
