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
function start(resumeTime=0,keepPaused=false){if(!current)return;if(typeof resumeTime!=='number')resumeTime=0;const active=current;current.progressStarted=false;let pendingResume=current.kind!=='tv'&&Number.isFinite(resumeTime)&&resumeTime>0?resumeTime:null;if(pendingResume!==null&&Number.isFinite(current.duration_seconds))pendingResume=Math.min(pendingResume,Math.max(0,current.duration_seconds-.25));const beginPlayback=()=>{if(current!==active)return;if(keepPaused){video.pause();setPlayerLoading(false);status.textContent='Pausado';return}video.play().catch(()=>{if(current===active){setPlayerLoading(false);status.textContent='Pausado'}})};const finishResume=()=>{if(current!==active||pendingResume===null)return;for(let i=0;i<video.buffered.length;i++){if(video.buffered.start(i)<=pendingResume&&video.buffered.end(i)>pendingResume+.05){const target=pendingResume;pendingResume=null;video.currentTime=target;beginPlayback();return}}};mediaRecoveryAttempts=0;$('player').dataset.state='playing';video.controls=!$('player').classList?.contains('custom-player');setPlayerLoading(true);hlsDiagnostic={};$('retry').disabled=false;error.textContent='';status.textContent='Conectando';if(hls)hls.destroy();video.pause();const source=current.stream_url||'/stream/'+current.id+'.m3u8';video.hidden=false;$('sound').disabled=false;if(window.Hls&&Hls.isSupported()){hls=new Hls({lowLatencyMode:false,liveSyncDurationCount:3,liveMaxLatencyDurationCount:6,maxBufferLength:18,maxMaxBufferLength:600,maxBufferSize:60*1000*1000,backBufferLength:12,startPosition:current.kind==='tv'?-1:Math.max(0,(pendingResume??0)-20),...playbackLoadOptions(current.kind==='tv')});hls.on(Hls.Events.AUDIO_TRACKS_UPDATED,syncNativeTracks);hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED,syncNativeTracks);hls.loadSource(source);hls.attachMedia(video);hls.on(Hls.Events.MANIFEST_PARSED,()=>{if(current!==active)return;if(pendingResume!==null){status.textContent='Cargando punto de continuación';finishResume();return}beginPlayback()});hls.on(Hls.Events.FRAG_BUFFERED,(_,d)=>{if(current!==active)return;hlsDiagnostic.lastFragSN=Number(d.frag.sn)||0;hlsDiagnostic.lastFragStart=d.frag.start;hlsDiagnostic.lastFragEnd=d.frag.start+d.frag.duration;finishResume()});hls.on(Hls.Events.ERROR,(_,data)=>{if(current!==active)return;hlsDiagnostic.hlsErrorUnix=Date.now()/1000;hlsDiagnostic.hlsErrorCount=(hlsDiagnostic.hlsErrorCount||0)+1;hlsDiagnostic.hlsError=data.details;hlsDiagnostic.hlsErrorType=data.type;hlsDiagnostic.hlsFatal=!!data.fatal;
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


function focusTrackTrigger(){const button=document.querySelector('[data-track-trigger][aria-expanded="true"]')||$('trackSettings');button.focus();}
function closeTrackPanel(){$('trackPanel').hidden=true;$('trackSettings').setAttribute('aria-expanded','false');}
document.addEventListener('pointerdown',e=>{if(!$('trackPanel').hidden&&!$('trackPanel').contains(e.target)&&!$('trackSettings').contains(e.target)&&!e.target.closest?.('[data-track-trigger]'))closeTrackPanel();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('trackPanel').hidden){closeTrackPanel();focusTrackTrigger();}});


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
    const entry=document.createElement('div');entry.className='episode-entry';
    const download=document.createElement('button');download.type='button';download.className='episode-download';download.append(icon('download'));download.setAttribute('aria-label','Descargar episodio '+(episode.number??index+1)+' en MP4');download.title='Descargar episodio en MP4';download.onclick=()=>{if(selected)window.downloadUI?.open(selected,episode)};
    entry.append(row,download);list.append(entry);
  });
  syncEpisodeRows();
}
function syncEpisodeRows(){
  window.downloadUI?.refresh();
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

/* Custom controls keep the original HTMLVideoElement and HLS playback pipeline. */
const customPlayerControls=(()=>{
  const root=$('player'),panel=$('trackPanel');let hideTimer,clickTimer,dragging=false,keyboardMode=false,lastTrack='audio',pressing=false,fullscreenPending=false;
  const paths={play:'<path d="m9 5 11 7-11 7z" fill="currentColor" stroke="none"/>',pause:'<path d="M8 5v14M16 5v14" stroke-width="4"/>',back:'<path d="M7 7H3V3M3 7a9 9 0 1 1-1 7"/><text x="12" y="15" text-anchor="middle" font-size="8" fill="currentColor" stroke="none">10</text>',forward:'<path d="M17 7h4V3M21 7a9 9 0 1 0 1 7"/><text x="12" y="15" text-anchor="middle" font-size="8" fill="currentColor" stroke="none">10</text>',volume:'<path d="M4 9h4l5-4v14l-5-4H4zM17 8a6 6 0 0 1 0 8M20 5a10 10 0 0 1 0 14"/>',mute:'<path d="M4 9h4l5-4v14l-5-4H4zM17 9l5 6m0-6-5 6"/>',audio:'<path d="M4 13v-2a8 8 0 0 1 16 0v2M4 12h3v7H4zm13 0h3v7h-3z"/>',subtitles:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M6 11h4m4 0h4M6 15h7m3 0h2"/>',fullscreen:'<path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>',exit:'<path d="M3 9h6V3m6 0v6h6M9 21v-6H3m12 6v-6h6"/>'};
  function svg(name){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths[name]+'</svg>';}
  function setControlIcon(button,name){if(button.dataset.icon===name)return;button.dataset.icon=name;button.innerHTML=svg(name);}
  function button(id,label,name){const b=document.createElement('button');b.type='button';b.id=id;b.className='video-control';b.setAttribute('aria-label',label);b.title=label;setControlIcon(b,name);return b;}
  const controls=document.createElement('div');controls.className='video-controls';controls.setAttribute('role','group');controls.setAttribute('aria-label','Controles del reproductor');
  const seekBox=document.createElement('div');seekBox.className='video-seek';
  const rail=document.createElement('div');rail.className='seek-rail';rail.setAttribute('aria-hidden','true');const buffered=document.createElement('div');buffered.className='seek-buffered';const played=document.createElement('div');played.className='seek-played';rail.append(buffered,played);
  const seek=document.createElement('input');seek.type='range';seek.id='videoSeek';seek.min='0';seek.max='0';seek.step='.1';seek.value='0';seek.setAttribute('aria-label','Posición del video');
  const seekTip=document.createElement('span');seekTip.className='seek-time-tip';seekTip.hidden=true;seekBox.append(rail,seek,seekTip);
  const row=document.createElement('div');row.className='video-control-row';const left=document.createElement('div');left.className='video-controls-left';const right=document.createElement('div');right.className='video-controls-right';
  const play=button('videoPlay','Reproducir','play'),back=button('videoBack','Retroceder 10 segundos','back'),forward=button('videoForward','Avanzar 10 segundos','forward'),mute=button('videoMute','Silenciar','volume');
  const volume=document.createElement('input');volume.type='range';volume.id='videoVolume';volume.min='0';volume.max='100';volume.step='1';volume.value='100';volume.setAttribute('aria-label','Volumen');
  const volumeBox=document.createElement('div');volumeBox.className='video-volume';volumeBox.append(mute,volume);
  const time=document.createElement('span');time.className='video-clock';time.id='videoClock';const live=document.createElement('span');live.className='video-live-label';live.textContent='EN VIVO';
  const audio=button('videoAudio','Idioma de audio','audio'),subtitles=button('videoSubtitles','Subtítulos','subtitles'),full=button('videoFullscreen','Pantalla completa','fullscreen');
  for(const b of [audio,subtitles]){b.dataset.trackTrigger='true';b.setAttribute('aria-controls','trackPanel');b.setAttribute('aria-expanded','false');}
  audio.append(Object.assign(document.createElement('span'),{className:'control-label',textContent:'Audio'}));subtitles.append(Object.assign(document.createElement('span'),{className:'control-label',textContent:'Subtítulos'}));
  left.append(play,back,forward,volumeBox,time,live);right.append(audio,subtitles,full);row.append(left,right);controls.append(seekBox,row);root.append(controls);
  const retry=$('retry');retry.classList.add('video-retry');right.insertBefore(retry,full);
  function clock(value){const n=Math.max(0,Math.floor(Number(value)||0)),h=Math.floor(n/3600),m=Math.floor(n%3600/60),s=n%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(s).padStart(2,'0');}
  function liveMode(){return current?.kind==='tv';}
  function duration(){return Number.isFinite(video.duration)&&video.duration>0?video.duration:0;}
  function show(){
    root.classList.add('controls-visible');clearTimeout(hideTimer);
    hideTimer=setTimeout(()=>{if(video.paused||video.ended||dragging||pressing||!panel.hidden||root.getAttribute('aria-busy')==='true'||(keyboardMode&&controls.contains(document.activeElement)))return;root.classList.remove('controls-visible');},3000);
  }
  function setTime(value){if(liveMode()||!duration())return;video.currentTime=Math.max(0,Math.min(duration()-.05,Number(value)||0));sync();show();}
  function toggle(){if(!current||root.dataset.state!=='playing')return;if(video.paused)video.play().catch(()=>{setPlayerLoading(false);status.textContent='Pausado';show()});else video.pause();show();}
  async function fullscreen(){
    if(fullscreenPending)return;fullscreenPending=true;
    const message='No se pudo cambiar la pantalla completa. Vuelve a pulsar el botón; para salir también puedes usar Esc.';
    try{
      if(document.fullscreenElement===root)await document.exitFullscreen();
      else if(root.requestFullscreen)await root.requestFullscreen();
      else if(video.webkitEnterFullscreen)video.webkitEnterFullscreen();
      else throw new Error('FullscreenUnavailable');
      delete root.dataset.fullscreenError;if($('error').textContent===message)$('error').textContent='';
    }catch(reason){root.dataset.fullscreenError=reason.name||'FullscreenError';$('error').textContent=message;}
    finally{fullscreenPending=false;sync();show();}
  }
  function sync(){
    const isLive=liveMode(),d=duration(),position=dragging?Number(seek.value):video.currentTime||0;
    if(root.dataset.state!=='playing'||!current){controls.hidden=true;return;}controls.hidden=false;
    seekBox.hidden=isLive;back.hidden=isLive;forward.hidden=isLive;live.hidden=!isLive;time.hidden=isLive;
    seek.disabled=!d;back.disabled=!d;forward.disabled=!d;
    if(!dragging){seek.max=String(d);seek.value=String(Math.min(d,position));}
    seek.setAttribute('aria-valuetext',clock(position)+' de '+clock(d));time.textContent=clock(position)+' / '+clock(d);
    played.style.width=(d?Math.min(100,position/d*100):0)+'%';buffered.replaceChildren();
    if(d)for(let i=0;i<video.buffered.length;i++){const start=Math.max(0,video.buffered.start(i)),end=Math.min(d,video.buffered.end(i));if(end<=start)continue;const band=document.createElement('span');band.style.left=(start/d*100)+'%';band.style.width=((end-start)/d*100)+'%';buffered.append(band);}
    const playing=!video.paused&&!video.ended;setControlIcon(play,playing?'pause':'play');play.title=playing?'Pausar':'Reproducir';play.setAttribute('aria-label',play.title);
    const silent=video.muted||video.volume===0;setControlIcon(mute,silent?'mute':'volume');mute.title=silent?'Activar sonido':'Silenciar';mute.setAttribute('aria-label',mute.title);mute.setAttribute('aria-pressed',String(silent));volume.value=String(silent?0:Math.round(video.volume*100));volume.style.setProperty('--volume-fill',volume.value+'%');
    audio.setAttribute('aria-expanded',String(!panel.hidden&&lastTrack==='audio'));subtitles.setAttribute('aria-expanded',String(!panel.hidden&&lastTrack==='subtitles'));subtitles.classList.toggle('has-subtitles',$('subtitleSelect').value!=='-1'&&!$('subtitleSelect').disabled);
    const isFull=document.fullscreenElement===root;setControlIcon(full,isFull?'exit':'fullscreen');full.title=isFull?'Salir de pantalla completa':'Pantalla completa';full.setAttribute('aria-label',full.title);
  }
  function openTracks(mode){
    const same=!panel.hidden&&lastTrack===mode;lastTrack=mode;
    if(same)closeTrackPanel();else{panel.hidden=false;panel.dataset.mode=mode;$('trackSettings').setAttribute('aria-expanded','true');const field=$(mode==='audio'?'audioSelect':'subtitleSelect');if(!field.disabled)field.focus({preventScroll:true});}
    sync();show();
  }
  play.onclick=toggle;back.onclick=()=>setTime(video.currentTime-10);forward.onclick=()=>setTime(video.currentTime+10);mute.onclick=()=>{if(video.volume===0){video.volume=.5;video.muted=false;}else video.muted=!video.muted;sync();show();};
  volume.oninput=()=>{video.volume=Number(volume.value)/100;video.muted=video.volume===0;sync();show();};
  seek.addEventListener('pointerdown',()=>{dragging=true;show()});seek.addEventListener('input',()=>{dragging=true;seekTip.hidden=false;seekTip.textContent=clock(seek.value);seekTip.style.left=Math.max(4,Math.min(96,Number(seek.value)/Math.max(duration(),1)*100))+'%';sync();show()});
  seek.addEventListener('change',()=>{const target=seek.value;dragging=false;seekTip.hidden=true;setTime(target)});seek.addEventListener('pointercancel',()=>{dragging=false;seekTip.hidden=true;sync()});
  seek.addEventListener('keydown',e=>{const delta=e.key==='ArrowLeft'?-5:e.key==='ArrowRight'?5:null;if(delta!==null||e.key==='Home'||e.key==='End'){e.preventDefault();e.stopPropagation();dragging=false;setTime(e.key==='Home'?0:e.key==='End'?duration():video.currentTime+delta);}});
  audio.onclick=()=>openTracks('audio');subtitles.onclick=()=>openTracks('subtitles');full.onclick=fullscreen;
  video.addEventListener('click',()=>{clearTimeout(clickTimer);clickTimer=setTimeout(toggle,230)});video.addEventListener('dblclick',()=>{clearTimeout(clickTimer);fullscreen()});
  root.addEventListener('pointermove',show);root.addEventListener('pointerdown',()=>{pressing=true;keyboardMode=false;show()});for(const event of ['pointerup','pointercancel'])document.addEventListener(event,()=>{if(pressing){pressing=false;show()}});window.addEventListener('blur',()=>{pressing=false;});root.addEventListener('focusin',show);
  document.addEventListener('keydown',e=>{
    if(e.key==='Tab')keyboardMode=true;
    if(!(root.contains(document.activeElement)||document.fullscreenElement===root)||e.altKey||e.ctrlKey||e.metaKey||e.target.closest?.('input,select,textarea,[contenteditable=true]'))return;
    const key=e.key.toLowerCase();if(key===' '&&e.target.closest?.('button'))return;if([' ','k','m','f','arrowleft','arrowright'].includes(key)){e.preventDefault();keyboardMode=true;if(key===' '||key==='k')toggle();if(key==='m')mute.click();if(key==='f')fullscreen();if(key==='arrowleft')setTime(video.currentTime-10);if(key==='arrowright')setTime(video.currentTime+10);show();}
  });
  for(const event of ['timeupdate','progress','durationchange','loadedmetadata','volumechange','emptied','seeked'])video.addEventListener(event,sync);
  for(const event of ['playing','pause','waiting','ended','error'])video.addEventListener(event,()=>{sync();show()});
  document.addEventListener('fullscreenchange',()=>{sync();show()});
  new MutationObserver(()=>{sync();show()}).observe(panel,{attributes:true,attributeFilter:['hidden']});new MutationObserver(()=>{if(root.dataset.state!=='playing')dragging=false;sync();show()}).observe(root,{attributes:true,attributeFilter:['data-state']});
  root.tabIndex=0;root.setAttribute('aria-label','Reproductor de video');root.classList.add('custom-player','controls-visible');video.controls=false;
  sync();const timer=setInterval(()=>{if(current&&root.dataset.state==='playing')sync();},500);
  return {sync,show,clock};
})();
