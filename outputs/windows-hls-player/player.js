function stopVodReadAhead(){const key=/^\/vod\/([a-f0-9]{24})\//.exec(current?.base_stream_url||current?.stream_url||'')?.[1];if(key)fetch('/api/vod/buffer/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key}),keepalive:true}).catch(()=>{});}

const $=id=>document.getElementById(id),video=$('video'),status=$('status'),error=$('error');let selectionRevision=0,vodPreparing=false,vodRequest=0,vodController=null,vodPending=null;let mediaRecoveryAttempts=0;let hls,items=[],kind='tv',selected=null,current=null,vodNote='',hlsDiagnostic={};let catalogPages={movies:1,series:1,anime:1},catalogTotals={},catalogLoading=false,catalogRequest=0;let searchTimer,searchController,searchItems=[],searchTotal=0,searchPage=1,searchLoading=false;
function prepareSelection(c){stopVodReadAhead();cancelVodPreparation();const revision=++selectionRevision;savePlaybackProgress();episodeProgress=null;selected=c;resetTracks();$('tvSessionNote').hidden=c.kind!=='tv';$('episodes').hidden=true;$('episodeLabel').hidden=true;$('episodes').replaceChildren();$('episodeSection').hidden=true;$('episodeList').replaceChildren();video.hidden=false;setContentArtwork(c);$('episodes').disabled=false;syncEpisodeRows();$('sound').disabled=!c.playable;$('title').textContent=c.name;$('selectedType').textContent=c.kind==='tv'?'TV en vivo':c.kind==='series'?'Serie · Ficha':'Película · Ficha';$('info').hidden=c.kind==='tv';$('metadata').textContent=[c.genres,c.score?'Puntuación: '+c.score:null,c.episodes?'Episodios informados: '+c.episodes:null,c.duration].filter(Boolean).join(' · ');$('description').textContent=c.description||'Sin descripción disponible.';$('vodNotice').textContent=c.kind==='series'?'Consultando episodios disponibles…':'Consultando la película…';render();if(c.kind!=='tv'){loadDetail(c,revision);loadRecommendations(c,revision);}else $('recommendationsSection').hidden=true;if(c.playable){current=c;start()}else{showPreview();}}
function showPreview(){savePlaybackProgress();resetTracks();current=null;hlsDiagnostic={};if(hls){hls.destroy();hls=null}video.pause();video.removeAttribute('src');video.controls=false;video.load();$('player').dataset.state='preparing';setPlayerLoading(true);status.textContent='Cargando video';$('details').textContent='';error.textContent='';$('retry').disabled=true;}
function playbackLoadOptions(isLive){
  if(isLive)return {};
  const policy=Hls.DefaultConfig?.fragLoadPolicy||{};
  // The local service may need three origin attempts before returning the first byte.
  return {maxBufferLength:180,maxMaxBufferLength:240,maxBufferSize:192*1024*1024,fragLoadPolicy:{...policy,default:{...policy.default,maxTimeToFirstByteMs:45000,maxLoadTimeMs:120000}}};
}
function bufferedAhead(){
  const t=video.currentTime;
  for(let i=0;i<video.buffered.length;i++)if(video.buffered.start(i)<=t&&video.buffered.end(i)>t)return video.buffered.end(i)-t;
  return 0;
}
function recordPlaybackWait(){
  if(!current||video.paused||video.seeking||hlsDiagnostic.isWaiting)return;
  hlsDiagnostic.isWaiting=true;
  hlsDiagnostic.waitingCount=(hlsDiagnostic.waitingCount||0)+1;
  hlsDiagnostic.lastWaitingUnix=Date.now()/1000;
  hlsDiagnostic.lastWaitingTime=video.currentTime;
  hlsDiagnostic.lastWaitingAhead=bufferedAhead();
  update();
}
function start(resumeTime=0,keepPaused=false){if(!current)return;if(typeof resumeTime!=='number')resumeTime=0;const active=current;current.progressStarted=false;let pendingResume=current.kind!=='tv'&&Number.isFinite(resumeTime)&&resumeTime>0?resumeTime:null;if(pendingResume!==null&&Number.isFinite(current.duration_seconds))pendingResume=Math.min(pendingResume,Math.max(0,current.duration_seconds-.25));const beginPlayback=()=>{if(current!==active)return;if(keepPaused){video.pause();setPlayerLoading(false);status.textContent='Pausado';return}video.play().catch(()=>{if(current===active){setPlayerLoading(false);status.textContent='Pausado'}})};const finishResume=()=>{if(current!==active||pendingResume===null)return;for(let i=0;i<video.buffered.length;i++){if(video.buffered.start(i)<=pendingResume&&video.buffered.end(i)>pendingResume+.05){const target=pendingResume;pendingResume=null;video.currentTime=target;beginPlayback();return}}};mediaRecoveryAttempts=0;$('player').dataset.state='playing';video.controls=true;setPlayerLoading(true);hlsDiagnostic={};$('retry').disabled=false;error.textContent='';status.textContent='Conectando';if(hls)hls.destroy();video.pause();const source=current.stream_url||'/stream/'+current.id+'.m3u8';video.hidden=false;$('sound').disabled=false;if(window.Hls&&Hls.isSupported()){hls=new Hls({lowLatencyMode:false,liveSyncDurationCount:3,liveMaxLatencyDurationCount:6,maxBufferLength:18,maxMaxBufferLength:600,maxBufferSize:60*1000*1000,backBufferLength:12,startPosition:current.kind==='tv'?-1:Math.max(0,(pendingResume??0)-20),...playbackLoadOptions(current.kind==='tv')});hls.on(Hls.Events.AUDIO_TRACKS_UPDATED,syncNativeTracks);hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED,syncNativeTracks);hls.loadSource(source);hls.attachMedia(video);hls.on(Hls.Events.MANIFEST_PARSED,()=>{if(current!==active)return;if(pendingResume!==null){status.textContent='Cargando punto de continuación';finishResume();return}beginPlayback()});hls.on(Hls.Events.FRAG_BUFFERED,(_,d)=>{if(current!==active)return;hlsDiagnostic.lastFragSN=Number(d.frag.sn)||0;hlsDiagnostic.lastFragStart=d.frag.start;hlsDiagnostic.lastFragEnd=d.frag.start+d.frag.duration;finishResume()});hls.on(Hls.Events.ERROR,(_,data)=>{if(current!==active)return;hlsDiagnostic.hlsErrorUnix=Date.now()/1000;hlsDiagnostic.hlsErrorCount=(hlsDiagnostic.hlsErrorCount||0)+1;hlsDiagnostic.hlsError=data.details;hlsDiagnostic.hlsErrorType=data.type;hlsDiagnostic.hlsFatal=!!data.fatal;
if(data.fatal){
  if(data.type==='mediaError'&&mediaRecoveryAttempts<1&&typeof hls.recoverMediaError==='function'){
    mediaRecoveryAttempts++;hlsDiagnostic.recoveries=mediaRecoveryAttempts;status.textContent='Recuperando reproducción';error.textContent='';setPlayerLoading(true);update();hls.recoverMediaError();return;
  }
  if(data.type==='mediaError'&&!current.compatibility_mode&&/^\/vod\/[a-f0-9]{24}\/index\.m3u8$/.test(current.base_stream_url||'')){
    const position=Math.max(video.currentTime||0,resumeTime),audio=$('audioSelect').value;
    current.compatibility_mode=true;current.base_stream_url=current.base_stream_url.replace('/index.m3u8','/compat/index.m3u8');
    current.stream_url=/^\d+$/.test(audio)?current.base_stream_url.replace('/index.m3u8','/audio/'+audio+'/index.m3u8'):current.base_stream_url;
    start(position,keepPaused);status.textContent='Adaptando video para este navegador';return;
  }
  setPlayerLoading(false);status.textContent=data.type==='networkError'?'Conexión interrumpida':'No disponible';
  error.textContent=data.type==='networkError'?'No se pudo descargar el video. Pulsa Reconectar para reintentar.':data.type==='mediaError'?'El navegador no pudo decodificar este video. Prueba Reconectar; si persiste, el formato puede no ser compatible con este navegador.':'No se pudo reproducir este video. Vuelve a conectar o prueba otro título.';update();
}})}else if(video.canPlayType('application/vnd.apple.mpegurl')){video.src=source;video.play().catch(()=>{if(current===active){setPlayerLoading(false);status.textContent='Pausado'}})}else{setPlayerLoading(false);status.textContent='No compatible';error.textContent='Este navegador no permite reproducir el flujo.';}}
video.addEventListener('playing',()=>{if(hlsDiagnostic.isWaiting)hlsDiagnostic.lastWaitingDuration=Date.now()/1000-hlsDiagnostic.lastWaitingUnix;hlsDiagnostic.isWaiting=false;setPlayerLoading(false);if(current)current.progressStarted=true;status.textContent=current?.kind==='tv'?'En vivo':'Reproduciendo';error.textContent=''});video.addEventListener('waiting',()=>{recordPlaybackWait();if(current){setPlayerLoading(!video.paused);status.textContent='Almacenando en búfer'}});video.addEventListener('stalled',()=>{if(current){setPlayerLoading(!video.paused);status.textContent='Esperando datos'}});video.addEventListener('pause',()=>{if(current){setPlayerLoading(false);status.textContent='Pausado'}});$('retry').onclick=()=>{if(current)start(video.currentTime);else if(selected)prepareSelection(selected)};$('sound').onclick=()=>{video.muted=!video.muted;$('sound').textContent=video.muted?'Activar sonido':'Silenciar'};$('search').onkeydown=e=>{if(e.key==='Enter'&&kind!=='tv'&&$('search').value.trim().length>=2){clearTimeout(searchTimer);loadSearch(1)}};document.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>section(b.dataset.kind));
async function update(){const q=video.getVideoPlaybackQuality?video.getVideoPlaybackQuality():{},m={browser:playbackBrowser(),compatibilityMode:!!current?.compatibility_mode,recoveries:mediaRecoveryAttempts,currentTime:video.currentTime,bufferAhead:bufferedAhead(),seeking:video.seeking,readyState:video.readyState,width:video.videoWidth,height:video.videoHeight,frames:q.totalVideoFrames||0,droppedFrames:q.droppedVideoFrames||0,paused:video.paused,error:video.error?video.error.code:null,bufferStart:video.buffered.length?video.buffered.start(0):null,bufferEnd:video.buffered.length?video.buffered.end(video.buffered.length-1):null,liveSync:hls?.liveSyncPosition??null,...hlsDiagnostic};if(current)$('details').textContent=video.videoWidth?`${current?.kind==='tv'?'En vivo · ':''}${video.videoHeight}p${current.kind==='tv'?'':' · Búfer: '+Math.floor(bufferedAhead())+' s'}`:'Esperando video…';try{await fetch('/api/client-metrics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(m)});const s=await(await fetch('/api/status')).json();if(s.portal?.connected&&s.portal?.last_heartbeat_unix&&kind!=='tv'&&!catalogLoading)$('catalogNote').textContent='Sesión del portal mantenida automáticamente. Películas y series con renovación automática de la fuente de video.';if(s.portal?.last_error==='session_conflict'&&kind!=='tv'){$('portalState').textContent='La cuenta se abrió en otro dispositivo. Cierra esa reproducción antes de recuperar la sesión de XuperPC.';$('catalogNote').textContent='La sesión del portal fue reemplazada; se conserva el catálogo cargado.';}$('expiry').textContent=new Date(s.expires_unix*1000).toLocaleString('es-CL',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});if(current?.kind==='tv'&&String(s.last_error||'').includes('returned 409')){status.textContent='Servicio rechazó la solicitud';error.textContent='El servidor de video devolvió 409. La fecha de vencimiento por sí sola no garantiza que acepte la sesión.'}if(!s.remaining_seconds&&s.tv?.source_lookups>0&&current?.kind==='tv'){status.textContent='Sesión vencida';error.textContent='La autorización de TV ha vencido.'}}catch{}}

async function loadDetail(c,revision){try{const progressTask=c.kind==='series'?progressQueue.then(()=>fetch('/api/progress/'+c.id)).then(r=>r.ok?r.json():null).catch(()=>null):Promise.resolve(null);const response=await fetch('/api/vod/detail/'+c.id);if(!response.ok)throw Error();const data=await response.json();const savedProgress=await progressTask;if(selected?.id!==c.id||selectionRevision!==revision)return;episodeProgress=savedProgress?.progress||null;if(data.item.backdrop_url||data.item.poster_url)setContentArtwork({...c,...data.item});$('description').textContent=data.item.description||c.description||'Sin descripción disponible.';for(const e of data.episodes){const option=document.createElement('option');option.value=e.number??'';option.textContent=e.number?'Episodio '+e.number+(e.name?' · '+e.name:''):e.name||'Película';$('episodes').append(option)}const series=c.kind==='series';if(episodeProgress?.last_episode&&Array.from($('episodes').options).some(o=>o.value===episodeProgress.last_episode))$('episodes').value=episodeProgress.last_episode;$('episodeSection').hidden=!series;renderEpisodes(series?data.episodes:[]);$('vodNotice').textContent=series?data.episodes.length+' episodios disponibles. Pulsa un capítulo para reproducirlo.':'Listo para reproducir.';if(data.episodes.length)playVod();else{setPlayerLoading(false);status.textContent='Sin episodios';}}catch{if(selected?.id===c.id&&selectionRevision===revision){setPlayerLoading(false);$('player').dataset.state='error';$('retry').disabled=false;status.textContent='No disponible';$('vodNotice').textContent='No se pudo consultar este título. Vuelve a seleccionarlo.';}}}
function cancelVodPreparation(){vodRequest++;vodController?.abort();vodController=null;vodPending=null;vodPreparing=false;}
async function playVod(){
  const c=selected,revision=selectionRevision;if(!c||c.kind==='tv'||!$('episodes').options.length)return;
  const episode=c.kind==='series'?$('episodes').value:null;
  if(vodPreparing&&vodPending?.id===c.id&&vodPending?.episode===episode)return;
  cancelVodPreparation();const ticket=vodRequest,controller=new AbortController();vodController=controller;vodPending={id:c.id,episode};vodPreparing=true;
  const isActive=()=>selected?.id===c.id&&selectionRevision===revision&&ticket===vodRequest;
  const bookmark=episodeProgress?.episodes?.[episode],resume=bookmark&&!bookmark.completed?bookmark.position:0;
  syncEpisodeRows();$('player').dataset.state='preparing';setPlayerLoading(true);status.textContent='Preparando video';error.textContent='';
  try{
    const response=await fetch('/api/vod/play',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:c.id,episode}),signal:controller.signal});
    const data=await response.json();if(!isActive())return;
    if(!response.ok)throw Error(data.error||'No se pudo preparar el video.');
    current={...c,episode,progressStarted:false,playable:true,stream_url:data.url,base_stream_url:data.url,audio_tracks:data.audio_tracks||[],subtitle_tracks:data.subtitle_tracks||[],track_settings_available:true,duration_seconds:data.duration_seconds};
    configureTracks();$('selectedType').textContent=c.kind==='series'?'Serie · Episodio '+data.episode:'Película';$('vodNotice').textContent='';start(resume);
  }catch(e){
    if(isActive()&&e.name!=='AbortError'){setPlayerLoading(false);status.textContent='No disponible';error.textContent=e.message;$('player').dataset.state='error';$('retry').disabled=false;}
  }finally{
    if(isActive()){vodPreparing=false;vodPending=null;vodController=null;syncEpisodeRows();}
  }
}

function languageName(code,index){const names={spa:'Español',es:'Español',eng:'Inglés',en:'Inglés',por:'Portugués',pt:'Portugués',fra:'Francés',fr:'Francés',deu:'Alemán',de:'Alemán',ita:'Italiano',it:'Italiano'};return names[code]||(code&&code!=='und'?code.toLocaleUpperCase():'Pista '+(index+1));}
function fillOptions(select,tracks,off=false){select.replaceChildren();if(off){const o=document.createElement('option');o.value='-1';o.textContent='Desactivados';select.append(o)}tracks.forEach((t,i)=>{const o=document.createElement('option');o.value=String(t.index??i);o.textContent=languageName(t.language||t.lang,i)+((t.language||t.lang)!=='und'&&tracks.filter(x=>(x.language||x.lang)===(t.language||t.lang)).length>1?' · '+(i+1):'');select.append(o)});select.disabled=!tracks.length;}
function resetTracks(){$('trackPanel').hidden=true;$('trackSettings').setAttribute('aria-expanded','false');video.querySelectorAll('track').forEach(t=>t.remove());$('audioSelect').replaceChildren();$('audioSelect').disabled=true;fillOptions($('subtitleSelect'),[],true);$('trackNote').textContent='Las opciones se detectan al iniciar el video.';}
function configureTracks(){fillOptions($('audioSelect'),current.audio_tracks);fillOptions($('subtitleSelect'),current.subtitle_tracks,true);const saved=localStorage.getItem('audioLanguage');const preferred=current.audio_tracks.find(t=>t.language===saved);if(preferred){$('audioSelect').value=String(preferred.index);if(preferred.index!==0)current.stream_url=current.base_stream_url.replace('/index.m3u8','/audio/'+preferred.index+'/index.m3u8')}current.subtitle_tracks.forEach(t=>{const el=document.createElement('track');el.kind='subtitles';el.label=languageName(t.language,t.index);el.srclang=({spa:'es',eng:'en',por:'pt'})[t.language]||t.language;el.src=t.url;el.dataset.index=String(t.index);el.addEventListener('error',()=>{$('trackNote').textContent='No se pudo cargar este subtítulo. Puedes probar otro idioma.'});video.append(el)});const sub=current.subtitle_tracks.find(t=>t.language===localStorage.getItem('subtitleLanguage'));$('subtitleSelect').value=sub?String(sub.index):'-1';$('trackNote').textContent=(current.audio_tracks.length>1?'Puedes cambiar el idioma sin volver al principio.':(current.audio_tracks.length?'Este video ofrece una sola pista de audio detectada.':'No se identificaron pistas de audio seleccionables.'))+(current.subtitle_tracks.length?'':' No ofrece subtítulos externos disponibles.');applySubtitle();}
function applySubtitle(){if(!current)return;if(current.track_settings_available){video.querySelectorAll('track').forEach(t=>{t.track.mode=t.dataset.index===$('subtitleSelect').value?'showing':'disabled'})}else if(hls){hls.subtitleTrack=Number($('subtitleSelect').value);hls.subtitleDisplay=hls.subtitleTrack>=0;}}
function syncNativeTracks(){if(!current||current.track_settings_available||!hls)return;fillOptions($('audioSelect'),hls.audioTracks||[]);$('audioSelect').value=String(hls.audioTrack);fillOptions($('subtitleSelect'),hls.subtitleTracks||[],true);$('subtitleSelect').value=String(hls.subtitleTrack);$('trackNote').textContent='Se muestran las pistas que publica este canal.';}
$('trackSettings').onclick=()=>{$('trackPanel').hidden=!$('trackPanel').hidden;$('trackSettings').setAttribute('aria-expanded',String(!$('trackPanel').hidden));};
$('audioSelect').onchange=()=>{if(!current)return;const index=Number($('audioSelect').value);if(current.track_settings_available){const track=current.audio_tracks.find(t=>t.index===index);if(!track)return;if(track.language!=='und')localStorage.setItem('audioLanguage',track.language);const position=video.currentTime,paused=video.paused;current.stream_url=current.base_stream_url.replace('/index.m3u8','/audio/'+index+'/index.m3u8');start(position,paused)}else if(hls)hls.audioTrack=index;};
$('subtitleSelect').onchange=()=>{if(current?.track_settings_available){const track=current.subtitle_tracks.find(t=>String(t.index)===$('subtitleSelect').value);if(track)localStorage.setItem('subtitleLanguage',track.language);else localStorage.removeItem('subtitleLanguage')}applySubtitle();};
video.addEventListener('loadedmetadata',applySubtitle);

$('episodes').onchange=()=>{if(selected?.kind==='series'){showPreview();syncEpisodeRows();playVod();}};
$('previous').onclick=()=>{if(!catalogLoading){if(globalSearch()&&searchPage>1)loadSearch(searchPage-1);else if(!globalSearch()&&catalogPages[kind]>1)loadPage(kind,catalogPages[kind]-1)}};$('next').onclick=()=>{if(!catalogLoading){if(globalSearch())loadSearch(searchPage+1);else loadPage(kind,catalogPages[kind]+1)}};


function closeTrackPanel(){$('trackPanel').hidden=true;$('trackSettings').setAttribute('aria-expanded','false');}
document.addEventListener('pointerdown',e=>{if(!$('trackPanel').hidden&&!$('trackPanel').contains(e.target)&&!$('trackSettings').contains(e.target))closeTrackPanel();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('trackPanel').hidden){closeTrackPanel();$('trackSettings').focus();}});


function renderEpisodes(episodes){
  const list=$('episodeList');list.replaceChildren();
  $('episodeCount').textContent=episodes.length+' '+(episodes.length===1?'episodio':'episodios');
  episodes.forEach((episode,index)=>{
    const row=document.createElement('button');row.type='button';row.className='episode-row';row.dataset.episode=String(episode.number??'');
    const number=document.createElement('span');number.className='episode-number';number.textContent=episode.number??index+1;
    const copy=document.createElement('span');copy.className='episode-copy';
    const name=document.createElement('strong');name.textContent=episode.name||'Episodio '+(episode.number??index+1);copy.append(name);
    const duration=document.createElement('span');duration.className='episode-duration';duration.textContent=episode.duration||'';
    const state=document.createElement('span');state.className='episode-state';const progress=document.createElement('span');progress.className='episode-progress';copy.append(progress);
    row.append(number,copy,duration,state);
    row.onclick=()=>{if(row.dataset.episode===$('episodes').value)return;$('episodes').value=row.dataset.episode;$('episodes').dispatchEvent(new Event('change'));};
    list.append(row);
  });
  syncEpisodeRows();
}
function syncEpisodeRows(){
  document.querySelectorAll('.episode-row').forEach(row=>{
    const active=row.dataset.episode===$('episodes').value;
    row.setAttribute('aria-pressed',String(active));row.disabled=false;
    const mark=episodeProgress?.episodes?.[row.dataset.episode];row.querySelector('.episode-progress').textContent=mark?.completed?'Visto':mark?.position>0?'Continuar desde '+formatPosition(mark.position):'';row.querySelector('.episode-state').textContent=active?'Seleccionado':'Seleccionar';
  });
}

let episodeProgress=null,progressQueue=Promise.resolve(),lastProgressSave=0;
function formatPosition(seconds){const s=Math.floor(seconds||0);return [Math.floor(s/3600),Math.floor(s%3600/60),s%60].map((v,i)=>i===0?String(v):String(v).padStart(2,'0')).join(':');}
function savePlaybackProgress(completed=video.ended){
  const active=current;if(active?.kind!=='series'||!active.episode||!active.progressStarted)return progressQueue;
  const position=video.currentTime,duration=Number.isFinite(video.duration)?video.duration:0;
  if(!Number.isFinite(position)||position<0||(!completed&&position===0))return progressQueue;
  const payload={id:active.id,episode:String(active.episode),position,duration,completed};
  if(selected?.id===active.id){episodeProgress??={episodes:{}};episodeProgress.last_episode=payload.episode;episodeProgress.episodes[payload.episode]={position,duration,completed};syncEpisodeRows();}
  lastProgressSave=Date.now();
  progressQueue=progressQueue.catch(()=>{}).then(async()=>{const response=await fetch('/api/progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),keepalive:true});if(!response.ok)throw Error('progress');}).catch(()=>{if(selected?.id===active.id)$('vodNotice').textContent='No se pudo guardar el progreso. Comprueba que XuperPC siga abierto.';});
  return progressQueue;
}
video.addEventListener('timeupdate',()=>{if(Date.now()-lastProgressSave>=10000)savePlaybackProgress();});
video.addEventListener('pause',()=>savePlaybackProgress(video.ended));
video.addEventListener('ended',()=>savePlaybackProgress(true));
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')savePlaybackProgress(video.ended);});
window.addEventListener('pagehide',()=>savePlaybackProgress(video.ended));


function setPlayerLoading(loading){$('playerLoading').hidden=!loading||video.controls;$('player').setAttribute('aria-busy',String(loading));}
video.addEventListener('seeking',()=>{if(current&&!video.paused)setPlayerLoading(true);});
video.addEventListener('seeked',()=>{if(current&&video.readyState>=3)setPlayerLoading(false);});
video.addEventListener('ended',()=>setPlayerLoading(false));
video.addEventListener('error',()=>setPlayerLoading(false));


function setContentArtwork(item){
  const image=$('watchBackdrop'),src=item.backdrop_url||item.poster_url;
  video.removeAttribute('poster');image.removeAttribute('src');image.hidden=!src;
  $('watchDialog').dataset.kind=item.kind||'';
  if(src){video.poster=src;image.src=src;}
}
$('watchBackdrop').onerror=()=>{$('watchBackdrop').hidden=true;};

function playbackBrowser(){const ua=navigator.userAgent||'';return /Edg\//.test(ua)?'edge':/Chrome\//.test(ua)?'chrome':/Firefox\//.test(ua)?'firefox':/Safari\//.test(ua)?'safari':'other';}
