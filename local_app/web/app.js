'use strict';
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state={rooms:[],profiles:[],active:null},profileId=localStorage.getItem('tellotubby-profile') || localStorage.getItem('roomflight-profile'),room=null,lastKey='',viewer=null,polling=false;
let recordingItems=[],recordingsScanned=false,managedRecording=null,deleteRecording=null;
let recordingQuery='',recordingFilterChoice='all';
const date=t=>new Date(t*1000).toLocaleString();
// Show on every page load, including when a profile was previously selected.
const welcome=$('welcomeDialog');
welcome.showModal();
welcome.addEventListener('cancel',event=>event.preventDefault());
let welcomeDismissed=false;
function dismissWelcome(){
 if(welcomeDismissed)return;
 welcomeDismissed=true;clearTimeout(welcomeTimer);
 welcome.classList.add('welcome-fading');
 setTimeout(()=>{welcome.close();welcome.remove();poll();},600);
}
// Backdrop clicks target the modal dialog too, so any click dismisses it.
welcome.addEventListener('click',dismissWelcome);
const welcomeTimer=setTimeout(dismissWelcome,7400);
function toast(message){$('toast').textContent=message;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,9000);}
async function api(path,data){const r=await fetch('/api/'+path,{cache:'no-store',...(data?{method:'POST',headers:{'Content-Type':'application/json','X-App-Token':window.APP_TOKEN},body:JSON.stringify(data)}:{})});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
function chosen(){return state.profiles.find(p=>p.id===profileId);}
function buildRunning(job){return ['queued','running','stopping'].includes(job?.state);}
function busy(){return !!state.active||buildRunning(state.background_build);}
function route(){return location.hash.slice(1).split('/');}
function navigate(value){location.hash=value;lastKey='';}
function button(label,action,cls='',extra=''){return `<button class="${cls}" data-action="${action}" ${extra}>${label}</button>`;}
function sessionChip(){if(buildRunning(state.background_build)){$('sessionChip').innerHTML=`<a href="#room/${state.background_build.room_id}/map">Building room in background →</a>`;return;}const a=state.active;$('sessionChip').innerHTML=a?`<a href="#session/${a.id}"><span class="dot"></span>${a.kind==='live'?'Recorded flight':'Playback'} · ${esc(a.state)} →</a>`:'No session running';}
function profileChip(){const p=chosen();$('profileChip').innerHTML=p?`<span class="avatar">${esc(p.name[0].toUpperCase())}</span><strong>${esc(p.name)}</strong> ${button('Change','profile','small')}<p style="font-size:11px;margin:8px 0 0">${esc(p.settings.label)}</p>`:button('Choose profile','profile');}
function roomOptions(selected){return `<option value="">Unassigned</option>${state.rooms.map(r=>`<option value="${r.id}" ${r.id===selected?'selected':''}>${esc(r.name)}</option>`).join('')}<option value="__new__">+ Create a new room…</option>`;}
function recordingById(id){return recordingItems.find(r=>r.id===id)||room?.recordings.find(r=>r.id===id)||(state.active?.recording?.id===id?state.active.recording:null);}
function recordingRows(items){return items.map(r=>`<div class="flight-row"><div><strong>${esc(r.name)}</strong><small>${r.room_id?esc(state.rooms.find(x=>x.id===r.room_id)?.name||r.room_name||'Assigned room'):'Unassigned'}${r.duration_seconds!=null?' · '+Math.floor(r.duration_seconds/60)+'m '+Math.round(r.duration_seconds%60)+'s':''}${r.size_bytes!=null?' · '+(r.size_bytes/1024**2).toFixed(1)+' MiB':''}${r.missing?' · Folder missing':r.incomplete?' · Incomplete recording':''}</small><small style="overflow-wrap:anywhere">${esc(r.path)}</small></div><div class="actions">${button('Preview','preview-recording','',`data-id="${r.id}" ${busy()||r.missing||r.incomplete?'disabled':''}`)}${button('Manage','manage-recording','',`data-id="${r.id}"`)}</div></div>`).join('');}
function recordingsPage(){
 $('breadcrumb').textContent='Workspace / All recordings';
 $('content').innerHTML=`<div class="hero"><div><p class="eyebrow">SORT THE FLIGHT PILE</p><h1>All recordings</h1><p>Preview a flight, choose its room, or clear recordings you no longer need.</p></div>${button('Scan for recordings','scan-recordings')}</div><div class="card"><div class="actions"><input id="recordingSearch" aria-label="Search recordings" placeholder="Search recording name or room"><select id="recordingFilter" aria-label="Filter recordings"><option value="all">All recordings</option><option value="unassigned">Unassigned only</option>${state.rooms.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join('')}</select></div><p id="recordingCount"></p><div id="recordingRows"></div></div>`;
 $('recordingSearch').value=recordingQuery;$('recordingFilter').value=recordingFilterChoice;
 $('recordingSearch').oninput=filterRecordings;$('recordingFilter').onchange=filterRecordings;filterRecordings();
}
function filterRecordings(){
 if(!$('recordingRows'))return;
 const query=$('recordingSearch').value.toLowerCase(),filter=$('recordingFilter').value;
 recordingQuery=$('recordingSearch').value;recordingFilterChoice=filter;
 const items=recordingItems.filter(r=>(filter==='all'||filter==='unassigned'&&!r.room_id||filter===r.room_id)&&[r.name,r.room_name,r.path].join(' ').toLowerCase().includes(query));
 $('recordingCount').textContent=`${items.length} shown · ${recordingItems.filter(r=>!r.room_id).length} unassigned`;
 $('recordingRows').innerHTML=recordingRows(items)||'<p>No matching recordings. Scan finds ROS bag folders in Documents/tello-recordings.</p>';
}
function openRecordingManager(recording){
 managedRecording=recording;
 if(!$('recordingManager'))document.body.insertAdjacentHTML('beforeend','<dialog id="recordingManager"></dialog>');
 $('recordingManager').innerHTML=`<div class="modal-body"><h2>${esc(recording.name)}</h2><p style="overflow-wrap:anywhere">${esc(recording.path)}</p><label for="managedRoom">Room</label><select id="managedRoom">${roomOptions(recording.room_id)}</select><input id="managedNewRoom" aria-label="New room name" placeholder="New room name" hidden><p>Unlinking keeps the original files and saved processing results in the recording library.</p><div class="actions">${button('Save room assignment','save-recording-room','primary')}${recording.room_id?button('Unlink from room','unlink-recording'):''}${button('Close','close-recording-manager')}</div><hr><p>Permanent deletion removes the original folder and saved processing results.</p>${button('Delete recording permanently…','confirm-delete-recording','danger',state.active?.recording_id===recording.id?'disabled':'')}</div>`;
 $('managedRoom').onchange=()=>$('managedNewRoom').hidden=$('managedRoom').value!=='__new__';$('recordingManager').showModal();
}
function confirmRecordingDeletion(recording){
 deleteRecording=recording;
 if(!$('deleteRecordingDialog'))document.body.insertAdjacentHTML('beforeend','<dialog id="deleteRecordingDialog"></dialog>');
 $('deleteRecordingDialog').innerHTML=`<div class="modal-body"><h2>Permanently delete this recording?</h2><p>This deletes the original recording folder and its saved processing results. It cannot be undone. The room map will be refreshed.</p><p style="overflow-wrap:anywhere">${esc(recording.path)}</p><label for="deleteRecordingName">Type ${esc(recording.name)} to confirm</label><input id="deleteRecordingName" autocomplete="off"><div class="actions">${button('Cancel','cancel-delete-recording')}${button('Delete permanently','delete-recording','danger')}</div></div>`;$('deleteRecordingDialog').showModal();
}
async function assignRecording(id,selectId,newNameId){
 let roomId=$(selectId).value||null;
 if(roomId==='__new__'){
  const name=$(newNameId).value.trim();if(!name)throw Error('Enter a room name.');
  const created=await api('rooms',{name});state.rooms.push(created);roomId=created.id;
  $(selectId).insertAdjacentHTML('beforeend',`<option value="${created.id}">${esc(created.name)}</option>`);$(selectId).value=created.id;$(newNameId).hidden=true;
 }
 await api('assign-recording',{recording_id:id,room_id:roomId});toast(roomId?'Recording linked to its room.':'Recording unlinked; original files kept.');
 if($('recordingManager')?.open)$('recordingManager').close();
 lastKey='';if(route()[0]==='session')lastKey=location.hash+':active';await poll();
}
function library(){
 $('breadcrumb').textContent='Workspace / Room library';
 $('content').innerHTML=`<div class="hero"><div><p class="eyebrow">YOUR FLIGHTS, IN ONE PLACE</p><h1>Room library</h1><p>Collect flights, revisit recordings, and build a persistent 3D view for each room.</p></div>${button('+ Create room','new-room','primary')}</div><div class="section-label">${state.rooms.length} ROOM${state.rooms.length===1?'':'S'} · SAVED ON THIS LAPTOP</div><div class="cards">${state.rooms.map(r=>`<a class="card room-card" href="#room/${r.id}/flights"><div class="room-icon">▱</div><h3>${esc(r.name)}</h3><p>${r.flights} saved flight${r.flights===1?'':'s'} · ${r.maps} map capture${r.maps===1?'':'s'}</p><span class="row"><small>Open room</small><span>↗</span></span></a>`).join('')}</div>${state.rooms.length?'':`<div class="empty"><h3>Your first room starts here.</h3><p>Create “Robotics classroom”, then add a recording or make a new flight.</p>${button('Create your first room','new-room','primary')}</div>`}<details><summary>Where is my data?</summary><p>${esc(state.storage)}<br>Existing recordings are linked, not moved. New flights and reconstruction data are saved inside their room folder. They are excluded from Git.</p></details>`;
 $('content').insertAdjacentHTML('beforeend',`<div class="card"><h3>Room mapping models</h3><p>Indoor metric depth + wall/door segmentation · ${esc(state.mapping_setup?.state||'not prepared')}. Prepare once while online, before connecting to TELLO Wi-Fi. Original MiDaS / Apple Silicon vision modes remain as fallbacks.</p>${button('Prepare mapping models','prepare-mapping','',state.active||state.mapping_setup?.state==='running'?'disabled':'')}<details><summary>Model setup output</summary><pre>${esc(state.mapping_setup?.log||'No setup run yet.')}</pre></details></div>`);
 $('content').insertAdjacentHTML('afterbegin','<p><a href="#recordings">Browse all recordings, including unassigned flights →</a></p>');
}
function roomPage(tab){
 $('breadcrumb').textContent='Room library / '+room.name;
 const active=busy();
 $('content').innerHTML=`<div class="hero"><div><p class="eyebrow">ROOM WORKSPACE</p><h1>${esc(room.name)}</h1><p>${room.recordings.length} recordings · ${room.maps.length} saved map captures</p></div><div class="actions">${button('+ New recorded flight','connect','primary',active?'disabled':'')}${button('Add existing recording','discover')}</div></div><div class="tabs"><a class="${tab==='flights'?'current':''}" href="#room/${room.id}/flights">Flights & recordings</a><a class="${tab==='map'?'current':''}" href="#room/${room.id}/map">3D room view</a></div><div id="roomBody"></div>`;
 if(tab==='map')mapPage();else flightsPage();
}
function flightsPage(){
 $('roomBody').innerHTML=`<div id="importBox" hidden class="card"><h3>Add a recording</h3><p>Choose a complete ROS bag folder from Documents/tello-recordings. Linking keeps the original files in place.</p><label for="existingRecording">Recording folder</label><select id="existingRecording"></select><div class="actions" style="margin-top:14px">${button('Link to this room','import','primary')}${button('Cancel','cancel-import')}</div></div>${room.recordings.length?`<div class="card"><div class="row"><h3>Saved flights</h3><small>Playback never connects to the drone</small></div>${room.recordings.map(r=>`<div class="flight-row"><div><strong>${esc(r.name)}</strong><small>${r.linked?'Linked recording':'Recorded in this room'} · ${date(r.created)}</small></div><div class="actions">${button('View & process →','play','primary',`data-id="${r.id}" ${busy()?'disabled':''}`)}${button('Camera only','quick','',`data-id="${r.id}" ${busy()?'disabled':''}`)}</div></div>`).join('')}</div>`:`<div class="empty"><h3>No flights here yet.</h3><p>Link an existing recording to start building this room, or connect the drone for a new flight.</p>${button('Find existing recordings','discover','primary')}</div>`}<div class="section-label">PROCESSING HISTORY</div>${room.sessions.length?`<div class="card">${room.sessions.map(s=>`<div class="flight-row"><div><strong>${s.kind==='live'?'Recorded flight':'Recording playback'}</strong><small>${date(s.created)} · ${esc(s.state)}</small>${s.error?`<small class="status-warn">${esc(s.error)}</small>`:''}</div>${button('View session','session','',`data-id="${s.id}"`)}</div>`).join('')}</div>`:'<p>No processing sessions yet. Viewing a recording creates a saved session and preserves its map output.</p>'}`;
 for(const recording of room.recordings){
  const play=$('roomBody').querySelector(`[data-action="play"][data-id="${recording.id}"]`);
  play?.parentElement.insertAdjacentHTML('beforeend',button('Manage','manage-recording','',`data-id="${recording.id}"`));
 }
}
async function mapPage(){
 $('roomBody').innerHTML=`<div class="map-tools"><select id="mapChoice" aria-label="Map capture"><option value="room">Combined room reconstruction</option>${room.maps.map((m,i)=>`<option value="${m.id}">Capture ${room.maps.length-i} · ${m.landmarks} landmarks · ${esc(m.state)}</option>`).join('')}</select>${button('Fit view','fit-map')}${button('Update room map','rebuild')}<span class="pill">Drag to orbit · scroll to zoom</span></div><canvas id="roomCanvas" class="map-view" aria-label="Interactive 3D room reconstruction"></canvas><p id="mapStatus" class="meta-line">Loading saved reconstruction…</p><div class="callout">Experimental observed surfaces. Unknown space is not clear space. Separate flights are combined only when matching landmarks pass geometric checks; otherwise they stay available as individual captures. Path planning comes later.</div><div id="mapSources"></div>`;
 $('roomBody').insertAdjacentHTML('afterbegin',`<div class="card" id="buildPanel"><h3>Build this room from its recordings</h3><p>Process every saved flight in the background. No video viewing or drone connection needed. All images go through SLAM; tracked keyframes get depth, YOLO and room-structure processing.</p><div class="actions">${button('Build room from all recordings','build-room','primary')}${button('Stop room build','cancel-build')}</div><label class="check"><input type="checkbox" id="forceRoomBuild"> Reprocess recordings even if they already have saved results</label><p id="buildProgress" role="status"></p><details><summary>Background build log</summary><pre id="buildLog"></pre></details></div>`);
 updateBuildPanel(room.build);
 $('mapChoice').insertAdjacentHTML('afterend','<select id="roomLayer" aria-label="Reconstruction layer"><option value="surface">Textured surfaces</option><option value="structure">Wall / floor / door labels</option><option value="points">SLAM point evidence</option></select>');
 viewer=new CloudViewer($('roomCanvas'));$('mapChoice').onchange=()=>loadMap();$('roomLayer').onchange=()=>loadMap();await loadMap();
}
function updateBuildPanel(job){
 if(!$('buildPanel'))return;
 const running=buildRunning(job);
 $('buildPanel').querySelector('[data-action="build-room"]').disabled=busy()||!room.recordings.length;
 $('buildPanel').querySelector('[data-action="cancel-build"]').hidden=!running;
 $('forceRoomBuild').disabled=running;
 $('buildProgress').textContent=job?`${job.state} · ${job.stage} · ${job.completed||0}/${job.total||0} recordings completed · ${job.cached||0} reused`+(job.recording?' · '+job.recording:'')+(job.images_total?` · SLAM ${job.images_done||0}/${job.images_total} images`:'')+(job.keyframes_total?` · Models ${job.keyframes_done||0}/${job.keyframes_total} keyframes`:'')+(job.error?' · '+job.error:'')+(job.failures?.length?` · ${job.failures.length} recordings need attention`:''):'Ready. Completed recordings are reused automatically; new flights are added on the next build.';
 $('buildLog').textContent=job?.log||'No background room build yet.';
}
async function loadMap(){
 if(!$('mapChoice'))return;
 const choice=$('mapChoice').value;
 try{
  const d=await api(choice==='room'?`room-map/${room.id}/room-map.json`:`map/${choice}/map.json`);
  if(!$('mapStatus'))return;
  const points=d.points||[];viewer.set(points,d.paths||(d.cameras?[{points:d.cameras}]:[]));
  if(choice==='room'&&d.dense&&$('roomLayer')?.value!=='points'){
   const mesh=await api(`room-map/${room.id}/room-mesh.json`);
   if(mesh.vertices?.length&&$('mapChoice')?.value===choice)viewer.setMesh({...mesh,colors:$('roomLayer')?.value==='structure'?mesh.structure_colors:mesh.colors});
  }
  $('mapStatus').textContent=points.length?`${points.length.toLocaleString()} displayed points/cells · ${choice==='room'?d.units:'arbitrary SLAM units'} · ${d.aligned_maps??1} aligned captures · ${d.separate_maps??0} separate. Green points have support from more than one aligned capture.`:'No reconstruction saved yet. Process a recording with all systems to create a map. A low-texture flight may not initialize SLAM.';
  $('mapSources').innerHTML=(d.sessions||[]).length?`<div class="card"><h3>Capture alignment</h3>${d.sessions.map((s,i)=>`<p><span class="${s.aligned?'status-ok':'status-warn'}">${s.aligned?'Aligned':'Kept separate'}</span> · Capture ${i+1}${s.reason?' — '+esc(s.reason):' · '+(s.landmarks||0)+' landmarks'}</p>`).join('')}</div>`:'';
  if(d.dense)$('mapSources').insertAdjacentHTML('afterbegin',`<div class="card"><h3>Reconstructed surfaces</h3><p>${d.dense.integrated_frames||0} matched depth frames · ${d.dense.triangles||0} mesh triangles. ${esc(d.dense.reason||'Metric scale and door clearance are not verified. Path planning / autonomous flight remain blocked.')}</p><p>${esc(JSON.stringify(d.dense.rejected||{}))}</p><a href="/api/room-map/${room.id}/room-mesh.ply" download>Download surface mesh</a> · <a href="/api/room-map/${room.id}/occupancy.json" download>Download tentative occupancy</a></div>`);
  if(viewer.mesh)$('mapStatus').textContent=`${viewer.mesh.vertices.length.toLocaleString()} surface vertices · ${viewer.mesh.triangles.length.toLocaleString()} triangles · arbitrary map units. `+($('roomLayer').value==='structure'?'Blue: wall · green: floor · pink: ceiling · orange: door candidates.':'Textured surface reconstruction.');
  if(d.dense?.octomap?.startsWith('exported'))$('mapSources').insertAdjacentHTML('beforeend',`<p><a href="/api/room-map/${room.id}/room.ot" download>Download experimental OctoMap</a> · clearance and metric scale unverified</p>`);
 }catch(e){if($('mapStatus'))$('mapStatus').textContent=e.message;}
}
function sessionPage(id){
 const a=state.active?.id===id?state.active:null;
 $('breadcrumb').textContent='Room workspace / '+(a?.kind==='live'?'Recorded flight':'Playback');
 if(!a){$('content').innerHTML=`<div class="hero"><div><h1>Session saved</h1><p>Return to the room to view the recording and saved map captures.</p></div>${button('Back to room','back-room','primary')}</div><details open><summary>Session output</summary><pre id="sessionLog">Loading…</pre></details>`;api('log/'+id).then(d=>{if($('sessionLog'))$('sessionLog').textContent=d.log;}).catch(e=>toast(e.message));return;}
 $('content').innerHTML=`<div class="hero"><div><p class="eyebrow">${a.kind==='live'?'LIVE · RECORDING TO THIS ROOM':'RECORDED FLIGHT · CONTROLS DISABLED'}</p><h1>${a.kind==='live'?'Flight workspace':esc(a.recording?.name||'Recording workspace')}</h1><p id="sessionStatus">${esc(a.state)}</p></div><div class="actions">${a.kind==='live'?button('Request landing','land','danger'):''}${button(a.kind==='live'?'End flight session':'End playback','stop')}<a href="#recordings">All recordings</a></div></div>${a.kind==='live'?'<label class="check"><input type="checkbox" id="landedCheck"> Drone is physically landed; ready to finish saving.</label>':''}<div id="frameLoading" class="loading"><div class="spinner"></div><h3>Starting your session</h3><p>The camera and processing workers are starting. The flight controls will appear here.</p></div><iframe id="flightFrame" class="session-frame" title="Existing Tello flight and processing dashboard" hidden allow="fullscreen"></iframe><details><summary>Startup and processing log</summary><pre id="sessionLog"></pre></details>`;
 if(a.kind==='replay'&&a.recording){
  $('frameLoading').insertAdjacentHTML('beforebegin',`<div class="card"><h3>Which room is this flight?</h3><p id="previewAssignment"></p><div class="actions"><select id="previewRoom" aria-label="Room for this recording">${roomOptions(a.room_id)}</select><input id="previewNewRoom" aria-label="New room name" placeholder="New room name" hidden>${button('Save room assignment','assign-preview','primary')}</div></div>`);
  $('previewRoom').onchange=()=>$('previewNewRoom').hidden=$('previewRoom').value!=='__new__';
 }
 updateSession(a);
}
function updateSession(a){
 if(!$('sessionStatus'))return;
 $('sessionStatus').textContent=a.state==='stopping'?'Finishing recording and saving maps. Keep this window open.':`${a.state} · ${a.room_id?'Output stays with this room.':'Unassigned preview; recording stays in the library.'}`;
 if($('previewAssignment'))$('previewAssignment').textContent=a.room_id?'Currently linked to '+(state.rooms.find(r=>r.id===a.room_id)?.name||'its room')+'. You can change it while watching.':'Not linked to a room yet. Choose a room or create one while watching.';
 $('sessionLog').textContent=a.log_tail||'Waiting for startup output…';
 if(a.dashboard_ready&&$('flightFrame').getAttribute('src')!==a.dashboard_url){$('flightFrame').src=a.dashboard_url;$('flightFrame').hidden=false;$('frameLoading').hidden=true;}
}
async function render(force=false){
 const r=route();let key=location.hash;
 if(r[0]==='recordings'){
  if(!recordingsScanned){recordingsScanned=true;await api('scan-recordings',{});}
  recordingItems=await api('recordings');key+=':'+recordingItems.map(x=>x.id+x.room_id+x.missing+x.incomplete).join(',')+':'+busy();
  if(force||key!==lastKey){lastKey=key;recordingsPage();}
 }else if(r[0]==='room'&&r[1]){
  room=await api('rooms/'+r[1]);key+=':'+room.recordings.length+':'+room.sessions.map(s=>s.state).join(',')+':'+room.maps.length+':'+room.build?.state;
  if(force||key!==lastKey){lastKey=key;roomPage(r[2]||'flights');}else updateBuildPanel(room.build);
 }else if(r[0]==='session'&&r[1]){
  const a=state.active?.id===r[1]?state.active:null;if(a)room=a.room_id?await api('rooms/'+a.room_id):null;
  key+=':'+(a?'active':'done');if(force||key!==lastKey){lastKey=key;sessionPage(r[1]);}else if(a)updateSession(a);
 }else{key+=':'+state.rooms.map(r=>r.id+r.flights+r.maps).join(',')+':'+state.mapping_setup?.state;if(force||key!==lastKey){lastKey=key;library();}}
}
async function poll(){
 if(polling)return;polling=true;
 try{state=await api('state');sessionChip();profileChip();if(!chosen()&&!$('profileDialog').open&&!welcome.open)$('profileDialog').showModal();await render();if(route()[2]==='map')await loadMap();}
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
  if(action==='scan-recordings'){const result=await api('scan-recordings',{});toast(`Found ${result.found} new recordings.`);lastKey='';await poll();}
  if(action==='preview-recording'){
   if(!chosen()){$('profileDialog').showModal();return;}
   const active=await api('preview-recording',{recording_id:el.dataset.id,profile_id:profileId});state.active=active;navigate('session/'+active.id);await poll();
  }
  if(action==='manage-recording'){const recording=recordingById(el.dataset.id);if(recording)openRecordingManager(recording);}
  if(action==='close-recording-manager')$('recordingManager').close();
  if(action==='save-recording-room')await assignRecording(managedRecording.id,'managedRoom','managedNewRoom');
  if(action==='unlink-recording'){await api('assign-recording',{recording_id:managedRecording.id,room_id:null});$('recordingManager').close();lastKey='';await poll();toast('Unlinked from room. Recording files kept.');}
  if(action==='assign-preview')await assignRecording(state.active.recording_id,'previewRoom','previewNewRoom');
  if(action==='confirm-delete-recording')confirmRecordingDeletion(managedRecording);
  if(action==='cancel-delete-recording')$('deleteRecordingDialog').close();
  if(action==='delete-recording'){
   await api('delete-recording',{recording_id:deleteRecording.id,confirmation:$('deleteRecordingName').value,permanent:true});
   $('deleteRecordingDialog').close();if($('recordingManager')?.open)$('recordingManager').close();lastKey='';await poll();toast('Recording and saved processing files permanently deleted.');
  }
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
  if(action==='back-room')navigate(room?'room/'+room.id+'/flights':'recordings');
  if(action==='fit-map')viewer?.fit();
  if(action==='rebuild'){await api('rebuild',{room_id:room.id});toast('Room reconstruction requested. Existing captures stay saved.');}
  if(action==='prepare-mapping'){await api('prepare-mapping',{});toast('Preparing models. Stay connected to the internet; progress is shown in the library.');await poll();}
  if(action==='build-room'){
   if(!chosen()){$('profileDialog').showModal();return;}
   await api('build-room',{room_id:room.id,profile_id:profileId,force:$('forceRoomBuild').checked});await poll();
  }
  if(action==='cancel-build'){await api('cancel-room-build',{room_id:room.id});toast('Stopping the background build; completed work and source recordings are retained.');await poll();}
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
 set(points,paths){this.mesh=null;const first=!this.points.length;this.points=points.filter(p=>p.length>=3&&p.slice(0,3).every(Number.isFinite));this.paths=paths;if(first)this.fit();else this.draw();}
 setMesh(mesh){this.mesh=mesh;this.points=mesh.vertices;this.draw();}
 fit(){if(this.points.length){const axes=[0,1,2].map(i=>this.points.map(p=>p[i]).sort((a,b)=>a-b));const lo=axes.map(a=>a[Math.floor(a.length*.01)]),hi=axes.map(a=>a[Math.min(a.length-1,Math.floor(a.length*.99))]);this.center=lo.map((v,i)=>(v+hi[i])/2);this.radius=Math.max(...hi.map((v,i)=>v-lo[i]),.001)/2;}this.zoom=1;this.draw();}
 project(point){const [x,y,z]=point.map((v,i)=>v-this.center[i]),c=Math.cos(this.yaw),s=Math.sin(this.yaw),a=c*x-s*y,b=s*x+c*y;return [a,Math.cos(this.pitch)*z-Math.sin(this.pitch)*b,Math.sin(this.pitch)*z+Math.cos(this.pitch)*b];}
 draw(){const c=this.canvas;if(!c.isConnected){this.resize.disconnect();return;}const ratio=devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;c.width=w*ratio;c.height=h*ratio;const ctx=c.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#101922';ctx.fillRect(0,0,w,h);const scale=Math.min(w,h)*.36/this.radius*this.zoom;const screen=p=>{const q=this.project(p);return [w/2+q[0]*scale,h/2-q[1]*scale,q[2]];};
  ctx.strokeStyle='#20313e';ctx.lineWidth=1;for(let i=-4;i<=4;i++){ctx.beginPath();ctx.moveTo(w/2+i*50,0);ctx.lineTo(w/2+i*50,h);ctx.stroke();ctx.beginPath();ctx.moveTo(0,h/2+i*50);ctx.lineTo(w,h/2+i*50);ctx.stroke();}
  if(this.mesh){
   const vertices=this.mesh.vertices.map(screen),colors=this.mesh.colors||[],triangles=this.mesh.triangles||[];
   const stride=Math.max(1,Math.ceil(triangles.length/12000));const faces=[];
   for(let i=0;i<triangles.length;i+=stride){const ids=triangles[i];faces.push({ids,z:ids.reduce((sum,id)=>sum+vertices[id][2],0)/3});}
   faces.sort((a,b)=>a.z-b.z);ctx.globalAlpha=.92;
   for(const face of faces){const ids=face.ids,c=colors[ids[0]]||[.5,.65,.7];ctx.fillStyle=`rgb(${c.map(v=>Math.round(v*255)).join(',')})`;ctx.beginPath();ids.forEach((id,i)=>{const p=vertices[id];i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);});ctx.closePath();ctx.fill();}
   ctx.globalAlpha=1;
  }
  const pts=this.points.map(p=>[...screen(p),p[3]||1]).sort((a,b)=>a[2]-b[2]);for(const p of (this.mesh?[]:pts)){if(p[0]<0||p[0]>w||p[1]<0||p[1]>h)continue;ctx.fillStyle=p[3]>1?'#b8e8c6':'#86a6bd';ctx.globalAlpha=p[3]>1?.9:.6;ctx.fillRect(p[0],p[1],p[3]>1?2.8:2,p[3]>1?2.8:2);}ctx.globalAlpha=1;
  this.paths.forEach((route,i)=>{ctx.strokeStyle=['#edba7d','#e99d9d','#90b7ee'][i%3];ctx.lineWidth=1.5;ctx.beginPath();(route.points||[]).forEach((p,j)=>{const q=screen(p);j?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]);});ctx.stroke();});ctx.fillStyle='#819baa';ctx.font='12px system-ui';ctx.fillText(this.points.length?'OBSERVED GEOMETRY · experimental alignment':'No saved geometry yet',18,25);
 }
}
poll();setInterval(poll,3000);
