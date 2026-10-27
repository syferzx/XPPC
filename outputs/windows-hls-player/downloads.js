/* Local queue manager: playback is stopped before preparing an export. */
window.downloadUI=(()=>{
  const dialog=$('downloadDialog'),entry=$('downloadContent'),tray=$('downloadTray');
  const active=new Set(['queued','preparing_download','downloading','converting','cancelling']);
  let job=null,target=null,ticket=0,configured=null,preparing=false,submitting=false,timer,listTimer,listBusy=false,folderDirty=false,noticeTimer;
  const cards=new Map(),seriesGroups=new Map();
  const labels={preparing:'Consultando pistas…',options:'Elige audio y subtítulos',queued:'En cola',preparing_download:'Preparando descarga…',downloading:'Descargando',converting:'Preparando archivo',cancelling:'Cancelando…',cancelled:'Cancelada',ready:'Completada',error:'No se pudo descargar',interrupted:'Interrumpida al cerrar el programa'};
  function bytes(n){return !Number.isFinite(n)||n<=0?'0 MB':n>=1024**3?(n/1024**3).toFixed(2)+' GB':(n/1024**2).toFixed(1)+' MB';}
  async function post(path,data={}){const response=await fetch('/api/downloads/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let value={};try{value=await response.json()}catch{}if(!response.ok){const error=new Error(value.error||'No se pudo completar la solicitud.');error.active_id=value.active_id;throw error}return value;}
  function refresh(){entry.hidden=!selected||selected.kind==='tv';entry.disabled=!selected||selected.kind==='tv'||!$('episodes').options.length;}
  function halt(){if(typeof cardPreview!=='undefined')cardPreview.hide();if($('watchDialog').open)$('watchDialog').close();if(typeof stopPlayer==='function')stopPlayer();}
  function paint(value){
    job=value;const state=job.state;$('downloadTitle').textContent=job.name||'Descargar';$('downloadState').textContent=state==='options'?'Elige las pistas que quieres guardar.':job.error||labels[state]||state;
    $('downloadOptions').hidden=state!=='options';$('downloadStart').hidden=state!=='options';$('downloadStart').disabled=state!=='options'||submitting;
    $('downloadCancel').hidden=!['preparing','options'].includes(state);$('downloadCancel').disabled=false;
    $('downloadProgressBox').hidden=true;$('downloadReady').hidden=true;$('downloadAgain').hidden=true;
    if(state==='options'&&configured!==job.id){
      $('downloadFormat').value='mkv';const audio=$('downloadAudio'),sub=$('downloadSubtitle');fillOptions(audio,job.audio_tracks||[]);
      if(!audio.options.length){audio.append(new Option('Audio predeterminado','0'));audio.disabled=false}
      fillOptions(sub,job.subtitle_tracks||[],true);sub.disabled=false;
      const preferred=window.playbackPreferences?.choose(target?.item,job.audio_tracks||[],job.subtitle_tracks||[]);if(preferred){target={...target,audio:preferred.audio,subtitle:preferred.subtitle}}
      if([...audio.options].some(o=>o.value===target?.audio))audio.value=target.audio;
      if([...sub.options].some(o=>o.value===target?.subtitle))sub.value=target.subtitle;
      $('downloadSize').textContent='Origen: '+bytes(job.total_bytes)+' · Tres partes en paralelo. Carpeta: '+(job.destination||'Descargas');configured=job.id;
    }
    clearTimeout(timer);if(state==='preparing'||state==='cancelling')timer=setTimeout(poll,750);
  }
  async function poll(){const id=job?.id,revision=ticket;if(!id)return;try{const response=await fetch('/api/downloads/'+id);if(!response.ok)throw Error('No se pudo consultar la descarga.');const result=await response.json();if(revision===ticket&&id===job?.id)paint(result);}catch(error){if(revision===ticket){$('downloadState').textContent=error.message;timer=setTimeout(poll,2000)}}}
  function show(){if(!dialog.open)dialog.showModal();}
  async function prepare(){
    if(!target||preparing)return;preparing=true;job=null;configured=null;const revision=++ticket;clearTimeout(timer);halt();
    $('downloadTitle').textContent=target.name;$('downloadState').textContent='Preparando opciones de descarga…';for(const id of ['downloadOptions','downloadStart','downloadCancel','downloadProgressBox','downloadReady','downloadAgain'])$(id).hidden=true;show();
    try{if(window.playbackPreferences)await window.playbackPreferences.ready;const data=await post('prepare',{id:target.id,episode:target.episode,poster_url:target.poster_url});if(revision!==ticket){post('cancel',{job:data.id}).catch(()=>{});return}paint(data);}
    catch(error){if(revision!==ticket)return;if(error.active_id){dialog.close();notify('Este contenido ya está en Mis descargas.');section('downloads')}else $('downloadState').textContent=error.message;}
    finally{preparing=false;}
  }
  function open(item,episode=null){const number=typeof episode==='object'?episode?.number:episode;target={item:{...item,_isAnime:item._isAnime||(typeof view!=='undefined'&&view==='anime')},id:item.id,episode:item.kind==='series'?String(number??$('episodes').value):null,name:item.name,poster_url:item.poster_url,audio:$('audioSelect').value,subtitle:$('subtitleSelect').value};prepare();}
  function added(){
    const notice=$('downloadAdded'),nav=document.querySelector('[data-view="downloads"]');notice.hidden=false;notice.classList.remove('is-added');void notice.offsetWidth;notice.classList.add('is-added');nav?.classList.remove('download-nav-pulse');void nav?.offsetWidth;nav?.classList.add('download-nav-pulse');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{notice.hidden=true;nav?.classList.remove('download-nav-pulse')},5000);
  }
  function action(label,handler){const button=document.createElement('button');button.className='secondary';button.textContent=label;button.onclick=async()=>{button.disabled=true;try{await handler();await loadList()}catch(error){$('downloadsError').textContent=error.message}finally{button.disabled=false}};return button;}
  function row(value){
    let node=cards.get(value.id);
    if(!node){node=document.createElement('article');node.className='download-row';const mark=document.createElement('span');mark.className='download-row-icon';mark.textContent='↓';const copy=document.createElement('div');copy.className='download-row-copy';const name=document.createElement('h2');name.className='download-row-name';const status=document.createElement('p');status.className='download-row-status';const progress=document.createElement('progress');progress.max=100;progress.setAttribute('aria-label','Progreso de descarga');const detail=document.createElement('p');detail.className='download-row-detail';const folder=document.createElement('p');folder.className='download-row-folder';const actions=document.createElement('div');actions.className='download-row-actions';copy.append(name,status,progress,detail,folder);node.append(mark,copy,actions);node.parts={mark,name,status,progress,detail,folder,actions};cards.set(value.id,node)}
    const p=node.parts,missing=value.state==='ready'&&!value.file_exists;node.dataset.state=missing?'missing':value.state;p.name.textContent=value.kind==='series'?'Episodio '+(value.episode||'') : value.name;
    if(!p.mark.querySelector('img'))p.mark.textContent=missing?'!':value.state==='ready'?'✓':value.state==='queued'?'⋯':'↓';
    const known=[...(typeof favoriteItems!=='undefined'&&Array.isArray(favoriteItems)?favoriteItems:[]),...(typeof items!=='undefined'&&Array.isArray(items)?items:[])].find(item=>item.id===value.item_id);
    const poster=value.poster_url||known?.poster_url;
    if(node.dataset.poster!==(poster||'')){node.dataset.poster=poster||'';p.mark.replaceChildren();if(poster){const image=document.createElement('img');image.src=poster;image.alt='';image.loading='lazy';image.referrerPolicy='no-referrer';image.onerror=()=>{image.remove();p.mark.textContent='↓'};p.mark.append(image)}else p.mark.textContent='↓'}
    p.status.textContent=missing?'Archivo no encontrado':value.state==='queued'?'En cola · posición '+value.queue_position:(labels[value.state]||value.state)+(value.format?' · '+value.format.toUpperCase():'');
    p.progress.hidden=!active.has(value.state);p.progress.value=value.percent||0;
    p.detail.textContent=missing?'El archivo fue movido o borrado fuera de XuperPC.':value.error||value.state==='ready'&&value.filename||active.has(value.state)&&(Math.floor(value.percent||0)+' % · '+bytes(value.downloaded_bytes)+' de '+bytes(value.total_bytes)+(value.speed_bytes>0?' · '+bytes(value.speed_bytes)+'/s':'')+' · 3 partes en paralelo')||'';
    p.folder.textContent=value.destination||'';p.folder.title=value.destination||'';
    const signature=[value.state,missing,value.subtitle_exists].join(':');
    if(node.dataset.actions!==signature){node.dataset.actions=signature;p.actions.replaceChildren();
      if(active.has(value.state)||['preparing','options'].includes(value.state)){const cancel=action(value.state==='cancelling'?'Cancelando…':'Cancelar',()=>post('cancel',{job:value.id}));cancel.disabled=value.state==='cancelling';p.actions.append(cancel)}
      else{
        if(value.state==='ready'&&!missing){p.actions.append(action('Abrir carpeta',()=>post('open-folder',{job:value.id})));const link=document.createElement('a');link.className='secondary';link.textContent='Guardar otra copia';link.href=value.file_url;link.download=value.filename;p.actions.append(link);if(value.subtitle_exists){const sub=document.createElement('a');sub.textContent='SRT';sub.className='secondary';sub.href=value.subtitle_url;sub.download=value.subtitle_filename;p.actions.append(sub)}}
        if(['interrupted','error','cancelled'].includes(value.state))p.actions.append(action('Volver a intentar',async()=>{halt();target=null;configured=null;ticket++;paint(await post('retry',{job:value.id}));show()}));
        p.actions.append(action('Quitar del historial',()=>post('forget',{job:value.id})));
      }
    }
    return node;
  }
  function groupRow(value){
    const key=value.series_group||value.item_id;let group=seriesGroups.get(key);
    if(!group){const node=document.createElement('details');node.className='download-series';node.open=true;const summary=document.createElement('summary'),cover=document.createElement('img'),copy=document.createElement('div'),title=document.createElement('h2'),count=document.createElement('p');cover.alt='';cover.loading='lazy';cover.referrerPolicy='no-referrer';copy.append(title,count);summary.append(cover,copy);node.append(summary);group={node,cover,title,count,seasons:new Map(),ids:new Set()};seriesGroups.set(key,group)}
    group.title.textContent=value.series_title||value.name.replace(/\s*- Episodio.*$/,'');
    if(value.poster_url&&group.cover.getAttribute('src')!==value.poster_url)group.cover.src=value.poster_url;
    group.cover.hidden=!group.cover.hasAttribute('src');group.ids.add(value.id);group.count.textContent=group.ids.size+' episodios';
    const season=String(value.season||'');let block=group.seasons.get(season);
    if(!block){const node=document.createElement('details');node.className='download-season';node.open=true;const summary=document.createElement('summary');summary.textContent=season?'Temporada '+season:'Episodios';const episodes=document.createElement('div');node.append(summary,episodes);group.node.append(node);block={node,episodes};group.seasons.set(season,block)}
    const episode=row(value);episode.dataset.episode=value.episode||'';block.episodes.append(episode);return group.node;
  }
  async function loadList(){
    if(listBusy)return;listBusy=true;clearTimeout(listTimer);
    try{const response=await fetch('/api/downloads');if(!response.ok)throw Error('No se pudieron consultar las descargas.');const data=await response.json(),values=data.items||[],list=$('downloadsList'),ids=new Set(values.map(v=>v.id));$('downloadsError').textContent='';
      if(!folderDirty&&document.activeElement!==$('downloadsPath'))$('downloadsPath').value=data.folder||'';
      const count=values.filter(v=>active.has(v.state)).length,badge=$('downloadNavCount');badge.hidden=!count;badge.textContent=count;$('downloadsCount').textContent=values.length?values.length:'';tray.hidden=!count;tray.textContent='↓ Mis descargas · '+count;
      for(const [id,node] of cards)if(!ids.has(id)){node.remove();cards.delete(id)}
      list.querySelector('.downloads-empty')?.remove();
      for(const group of seriesGroups.values())group.ids.clear();
      const top=[];
      for(const value of values){const node=value.kind==='series'?groupRow(value):row(value);if(!top.includes(node))top.push(node)}
      for(const [key,group] of seriesGroups){if(!group.ids.size){group.node.remove();seriesGroups.delete(key);continue}for(const [season,block] of group.seasons){if(!block.episodes.children.length){block.node.remove();group.seasons.delete(season);continue}const ordered=[...block.episodes.children].sort((a,b)=>Number(a.dataset.episode)-Number(b.dataset.episode));for(const node of ordered)block.episodes.append(node)}}
      for(let i=0;i<top.length;i++)if(list.children[i]!==top[i])list.insertBefore(top[i],list.children[i]||null);

      if(!values.length){const empty=document.createElement('div');empty.className='downloads-empty';const title=document.createElement('h2');title.textContent='Tus películas, listas para llevar';const text=document.createElement('p');text.textContent='Añade películas o episodios con el botón Descargar. Aquí verás la cola y los archivos terminados.';empty.append(title,text);list.append(empty)}
      if(dialog.open&&job){const value=values.find(v=>v.id===job.id);if(value)paint(value)}
      listTimer=setTimeout(loadList,count||view==='downloads'?2000:15000);
    }catch(error){$('downloadsError').textContent=error.message;listTimer=setTimeout(loadList,5000)}finally{listBusy=false}
  }
  entry.onclick=()=>{if(selected)open(selected,selected.kind==='series'?$('episodes').value:null)};tray.onclick=()=>section('downloads');
  $('downloadClose').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{if(submitting)return;if(preparing)ticket++;clearTimeout(timer);if(job&&['preparing','options'].includes(job.state)){const id=job.id;job=null;post('cancel',{job:id}).then(loadList).catch(()=>{})}});
  $('downloadStart').onclick=async()=>{if(!job||submitting)return;submitting=true;$('downloadStart').disabled=true;const id=job.id;
    try{halt();const result=await post('start',{job:id,audio:Number($('downloadAudio').value),subtitle:Number($('downloadSubtitle').value),format:$('downloadFormat').value});job=result;dialog.close();added();loadList();}
    catch(error){$('downloadState').textContent=error.message;$('downloadStart').disabled=false}finally{submitting=false}};
  $('downloadCancel').onclick=async()=>{if(!job)return;const id=job.id;try{await post('cancel',{job:id});job=null;dialog.close();loadList()}catch(error){$('downloadState').textContent=error.message}};
  $('downloadAddedOpen').onclick=()=>{$('downloadAdded').hidden=true;section('downloads')};$('downloadsRefresh').onclick=loadList;
  $('downloadsPath').oninput=()=>folderDirty=true;
  async function folderRequest(path,data,button){button.disabled=true;try{const result=await post(path,data);$('downloadsPath').value=result.folder;folderDirty=false;$('downloadsFolderMessage').textContent=result.cancelled?'La carpeta no cambió.':'Carpeta guardada. Se usará en las nuevas descargas.';await loadList()}catch(error){$('downloadsFolderMessage').textContent=error.message}finally{button.disabled=false}}
  $('downloadsSavePath').onclick=()=>folderRequest('set-folder',{folder:$('downloadsPath').value},$('downloadsSavePath'));
  $('downloadsChoosePath').onclick=()=>folderRequest('choose-folder',{},$('downloadsChoosePath'));
  $('downloadsOpenPath').onclick=()=>post('open-folder').catch(error=>$('downloadsFolderMessage').textContent=error.message);
  window.addEventListener('pagehide',()=>{if(job&&['preparing','options'].includes(job.state)&&!submitting)fetch('/api/downloads/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job:job.id}),keepalive:true}).catch(()=>{})});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')loadList()});
  refresh();setTimeout(loadList,0);return {open,refresh,loadList};
})();
