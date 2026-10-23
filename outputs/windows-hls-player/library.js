let animeItems=[];
const catalogSnapshots=new Map(),categorySnapshots=new Map();
function applyCatalogPage(target,page,data,append){
  const prior=append?(target==='anime'?animeItems:items.filter(item=>item.kind===target)):[];
  const seen=new Set(prior.map(item=>item.id)),nextItems=prior.concat(data.items.filter(item=>!seen.has(item.id)));
  if(target==='anime')animeItems=nextItems;else items=items.filter(item=>item.kind!==target).concat(nextItems);
  moreAvailable=!!data.has_more;catalogPages[target]=page;catalogTotals[target]=data.total;
  $('pageLabel').textContent=page+' / '+Math.max(1,Math.ceil(data.total/data.page_size));$('previous').disabled=page<=1;$('next').disabled=!data.has_more;
}
let seasonCollection=null,seasonGroupTitle='',seriesOpening=0;
let moreAvailable=false,infiniteError=false,infiniteTimer;
let categorySelection={movies:'',series:'',anime:''},categoryTicket=0,featuredTask=null,lastFeaturedRefresh=0;
/* Catalog presentation; playback remains in player.js. Favorites live in the PC profile. */
let view='home',favoriteItems=[],favoriteFilter='all',favoriteBusy=new Set(),favoriteReady=false,favoriteSaveQueue=Promise.resolve(),heroIndex=0,heroItems=[];
let shelves={movies:[],series:[]},homeLoading=true,homeErrors={},toastTimer,searchReturnView='home';
const icons={heart:'i-heart',plus:'i-plus',check:'i-check',tv:'i-tv',search:'i-search'};
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#'+icons[name]);svg.setAttribute('aria-hidden','true');svg.append(use);return svg;}
function favoriteMatches(item){return favoriteItems.filter(saved=>saved.id===item.id||(item.kind==='series'&&saved.kind==='series'&&seriesIdentity(saved.name).key===seriesIdentity(item.name).key));}
function isFavorite(id){const entry=[selected,...items,...searchItems,...favoriteItems,...heroItems,...(seasonCollection||[])].find(item=>item?.id===id);return entry?favoriteMatches(entry).length>0:favoriteItems.some(item=>item.id===id);}
function notify(message){clearTimeout(toastTimer);$('toast').textContent=message;$('toast').hidden=false;toastTimer=setTimeout(()=>{$('toast').hidden=true},3500);}
function favoriteButton(item){const button=document.createElement('button');button.className='favorite-button';button.dataset.favorite=item.id;button.dataset.name=item.name;button.setAttribute('aria-pressed',String(isFavorite(item.id)));button.setAttribute('aria-label',(isFavorite(item.id)?'Quitar de Mi lista: ':'Añadir a Mi lista: ')+item.name);button.disabled=!favoriteReady||favoriteBusy.has(item.id);button.append(icon('heart'));button.onclick=event=>{event.stopPropagation();toggleFavorite(item)};return button;}
function mediaCard(item,landscape=false){
  const card=document.createElement('article');card.className='media-card';const open=document.createElement('button');open.className='card-open';open.setAttribute('aria-label','Ver '+item.name);
  const picture=document.createElement('span');picture.className='card-image';
  const url=landscape?(item.backdrop_url||item.poster_url):item.poster_url;
  if(url){const img=document.createElement('img');img.alt='';img.loading='lazy';img.decoding='async';img.referrerPolicy='no-referrer';img.src=url;img.onerror=()=>img.remove();picture.append(img)}
  const tag=document.createElement('span');tag.className='card-tag';tag.textContent=item.kind==='series'?'SERIE':'PELÍCULA';picture.append(tag);
  const displayName=item.kind==='series'?seriesIdentity(item.name).title:item.name;const title=document.createElement('span');title.className='card-title';title.textContent=displayName;title.title=displayName;open.append(picture,title);
  if(!landscape){const meta=document.createElement('span');meta.className='card-meta';meta.textContent=(item.genres||'').split(',').slice(0,2).join(' · ')||(item.kind==='series'?'Serie':'Película');open.append(meta)}
  open.onclick=()=>choose(item);card.append(open,favoriteButton(item));return card;
}
function tvCard(item){
  const card=document.createElement('article');card.className='tv-item';const open=document.createElement('button');open.className='tv-open';open.setAttribute('aria-label','Ver '+item.name+' en vivo');
  const art=document.createElement('span');art.className='tv-icon';art.textContent=item.name.slice(0,2);
  if(item.poster_url){const img=document.createElement('img');img.src=item.poster_url;img.loading='lazy';img.alt='';img.referrerPolicy='no-referrer';img.onerror=()=>img.remove();art.append(img)}
  const copy=document.createElement('span');copy.className='tv-copy';const name=document.createElement('span');name.className='tv-name';name.textContent=item.name;const number=document.createElement('span');number.className='tv-number';number.textContent=(item.number?'Canal '+item.number+' · ':'')+'En vivo';copy.append(name,number);open.append(art,copy);open.onclick=()=>choose({...item,playable:true});card.append(open,favoriteButton(item));return card;
}
function emptyState(title,message,name='search'){
  const box=document.createElement('div');box.className='empty-state';const h=document.createElement('h2'),p=document.createElement('p');h.textContent=title;p.textContent=message;box.append(icon(name),h,p);return box;
}
function syncFavoriteControls(){
  $('favoriteCount').textContent=String(groupSeries(favoriteItems).length);$('favoriteCount').hidden=!favoriteItems.length;
  document.querySelectorAll('[data-favorite]').forEach(button=>{const id=button.dataset.favorite;button.setAttribute('aria-pressed',String(isFavorite(id)));button.disabled=!favoriteReady||favoriteBusy.has(id);button.setAttribute('aria-label',(isFavorite(id)?'Quitar de Mi lista: ':'Añadir a Mi lista: ')+button.dataset.name)});
  if(selected){$('selectedFavorite').setAttribute('aria-pressed',String(isFavorite(selected.id)));$('selectedFavorite').setAttribute('aria-label',isFavorite(selected.id)?'Quitar de Mi lista':'Añadir a Mi lista');$('selectedFavorite').disabled=!favoriteReady||favoriteBusy.has(selected.id)}
  const featured=heroItems[heroIndex];if(featured){const saved=isFavorite(featured.id);$('heroFavorite').replaceChildren(icon(saved?'check':'plus'),document.createTextNode(saved?'En mi lista':'Mi lista'));$('heroFavorite').setAttribute('aria-pressed',String(saved));$('heroFavorite').disabled=!favoriteReady||favoriteBusy.has(featured.id)}
}
async function toggleFavorite(item){
  if(!item||!favoriteReady||favoriteBusy.has(item.id))return;const saved=isFavorite(item.id);favoriteBusy.add(item.id);syncFavoriteControls();
  try{const task=favoriteSaveQueue.then(async()=>{const targets=saved?favoriteMatches(item):[item];for(const target of targets){const response=await fetch('/api/favorites',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:target.id,action:saved?'remove':'add'})});if(!response.ok)throw Error();const data=await response.json();favoriteItems=data.items;}notify(saved?'Quitado de Mi lista':'Añadido a Mi lista');if(view==='favorites')render()});favoriteSaveQueue=task.catch(()=>{});await task}
  catch{notify('No se pudo guardar el cambio. Intenta de nuevo.')}
  finally{favoriteBusy.delete(item.id);syncFavoriteControls()}
}
function renderHero(){
  if(!heroItems.length)return;heroIndex=Math.max(0,Math.min(heroIndex,heroItems.length-1));const item=heroItems[heroIndex];
  $('heroTitle').textContent=item.name;$('heroMetadata').textContent=[item.kind==='series'?'Serie':'Película',...(item.genres||'').split(',').filter(Boolean).slice(0,2),item.duration].filter(Boolean).join(' · ');
  $('heroDescription').textContent=item.description||'Descubre esta historia y encuentra tu próximo favorito en la biblioteca.';
  const image=$('heroImage');image.onerror=()=>image.removeAttribute('src');const src=item.backdrop_url||item.poster_url;if(src)image.src=src;else image.removeAttribute('src');
  $('heroOpen').disabled=false;$('heroFavorite').disabled=false;$('heroDots').replaceChildren();heroItems.forEach((entry,index)=>{const dot=document.createElement('button');dot.setAttribute('aria-label','Destacar '+entry.name);dot.setAttribute('aria-pressed',String(index===heroIndex));dot.onclick=()=>{heroIndex=index;renderHero()};$('heroDots').append(dot)});syncFavoriteControls();
}
function renderShelves(){
  for(const target of ['movies','series']){const box=$(target==='movies'?'movieShelf':'seriesShelf');box.replaceChildren();if(homeLoading&&!shelves[target].length){for(let i=0;i<6;i++){const skeleton=document.createElement('div');skeleton.className='shelf-loading';skeleton.setAttribute('aria-hidden','true');box.append(skeleton)}}else if(!shelves[target].length){const p=document.createElement('p');p.className='load-error';p.textContent=homeErrors[target]?'No pudimos cargar esta sección. Vuelve a abrirla para reintentar.':'No hay títulos disponibles.';box.append(p)}else groupSeries(shelves[target]).slice(0,18).forEach(item=>box.append(mediaCard(item,true)))}
  if(!heroItems.length&&shelves.movies.length){heroItems=shelves.movies.filter(item=>item.backdrop_url||item.poster_url).slice(0,5);renderHero()}
  syncFavoriteControls();
}
function globalSearch(){return view==='search';}
function render(append=false){
  if(view==='home'){renderShelves();return}
  const query=$('search').value.trim().toLocaleLowerCase();let list;
  if(view==='favorites')list=favoriteItems.filter(item=>favoriteFilter==='all'||item.kind===favoriteFilter);
  else if(globalSearch())list=searchItems;
  else list=view==='anime'?animeItems:items.filter(item=>item.kind===kind);
  if(view==='tv'&&query)list=list.filter(item=>(item.name+' '+(item.number||'')+' '+(item.genres||'')).toLocaleLowerCase().includes(query));
  list=groupSeries(list);
  $('items').className=view==='tv'?'tv-list':'poster-grid';const existing=append?$('items').children.length:0;if(!append)$('items').replaceChildren();
  if(view==='favorites')$('count').textContent=favoriteItems.length+' '+(favoriteItems.length===1?'favorito guardado':'favoritos guardados')+' en este PC';
  else if(globalSearch())$('count').textContent=searchLoading?'Buscando en todo el catálogo…':searchTotal.toLocaleString('es-CL')+' resultados · películas y series';
  else $('count').textContent=view==='tv'?list.length.toLocaleString('es-CL')+' canales':(catalogTotals[kind]||list.length).toLocaleString('es-CL')+' títulos';
  if(!list.length){if(searchLoading||catalogLoading){const pending=document.createElement('p');pending.className='catalog-loading';pending.textContent='Buscando tu próxima historia…';$('items').append(pending)}else if(view==='favorites')$('items').append(emptyState(favoriteItems.length?'No hay favoritos en esta sección':'Tu próxima historia empieza aquí',favoriteItems.length?'Prueba otro filtro para ver tus títulos guardados.':'Pulsa el corazón de una película, serie o canal para guardarlo en Mi lista.','heart'));else if(globalSearch()&&query.length<2)$('items').append(emptyState('¿Qué te gustaría ver?','Escribe al menos dos caracteres para buscar en todo el catálogo.'));else $('items').append(emptyState('No encontramos resultados','Prueba con otro título o vuelve a explorar la biblioteca.'))}
  else list.slice(existing).forEach(item=>$('items').append(item.kind==='tv'?tvCard(item):mediaCard(item)));
  syncFavoriteControls();updateInfiniteStatus();
}
function setView(next){
  view=next;$('homeView').hidden=next!=='home';$('catalogView').hidden=next==='home';$('favoriteFilters').hidden=next!=='favorites';$('paging').hidden=true;$('loadMoreStatus').hidden=!['movies','series','anime','search'].includes(next);
  const headings={movies:'Películas',series:'Series',anime:'Anime',tv:'TV en vivo',favorites:'Mi lista',search:'Resultados de búsqueda'};
  $('catalogTitle').textContent=headings[next]||'';$('catalogEyebrow').textContent=next==='favorites'?'TUS HISTORIAS, SIEMPRE A MANO':next==='tv'?'LO QUE ESTÁ PASANDO AHORA':'EXPLORA LA BIBLIOTECA';
  document.querySelectorAll('[data-view]').forEach(button=>{if(button.dataset.view===next)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current')});
  $('search').placeholder=next==='tv'?'Buscar canal…':'Buscar películas y series…';$('group').hidden=!['movies','series','anime'].includes(next);$('categoryLabel').hidden=$('group').hidden;
}
function section(next){
  clearTimeout(searchTimer);searchController?.abort();++catalogRequest;moreAvailable=false;infiniteError=false;catalogLoading=false;searchLoading=false;searchItems=[];searchTotal=0;$('search').value='';$('portalState').textContent='';
  if(['tv','movies','series','anime'].includes(next))kind=next;
  setView(next);render();if(['movies','series','anime'].includes(next)){const firstPage=loadPage(next,1);loadCategories(next,firstPage);}if(next==='home'){loadHome();refreshFeatured();}
  window.scrollTo({top:0,behavior:'instant'});
}
async function loadPage(target,page,append=false){
  const ticket=++catalogRequest,key=target+':'+(categorySelection[target]||'')+':'+page;
  catalogLoading=true;infiniteError=false;$('previous').disabled=true;$('next').disabled=true;$('portalState').textContent='';
  const snapshot=catalogSnapshots.get(key);
  if(!append&&snapshot)applyCatalogPage(target,page,snapshot,false);
  else if(!append&&categorySelection[target]){if(target==='anime')animeItems=[];else items=items.filter(item=>item.kind!==target);}
  render(append);
  try{const response=await fetch('/api/vod/catalog?kind='+target+'&page='+page+(categorySelection[target]?'&category='+encodeURIComponent(categorySelection[target]):''));if(!response.ok)throw Error();const data=await response.json();if(ticket!==catalogRequest||view!==target)return;
    catalogSnapshots.delete(key);catalogSnapshots.set(key,data);while(catalogSnapshots.size>24)catalogSnapshots.delete(catalogSnapshots.keys().next().value);
    applyCatalogPage(target,page,data,append);
  }catch{if(ticket===catalogRequest){infiniteError=true;$('portalState').textContent='No pudimos cargar más títulos. Los anteriores se conservan.';}}
  finally{if(ticket===catalogRequest){catalogLoading=false;render(append);scheduleInfiniteCheck()}}
}
function searchInput(){
  clearTimeout(searchTimer);searchController?.abort();++catalogRequest;moreAvailable=false;infiniteError=false;catalogLoading=false;searchLoading=false;
  if(view==='tv'){render();return}
  const query=$('search').value.trim();searchItems=[];searchTotal=0;searchPage=1;
  if(!query){section(searchReturnView);return}
  if(view!=='search')searchReturnView=view;
  kind='movies';setView('search');$('catalogTitle').textContent='Buscar: '+query;$('portalState').textContent='';$('pageLabel').textContent='—';$('previous').disabled=true;$('next').disabled=true;
  searchLoading=query.length>=2;render();if(searchLoading)searchTimer=setTimeout(()=>loadSearch(1),350);
}
async function loadSearch(page=1,append=false){
  const query=$('search').value.trim();if(view!=='search'||query.length<2)return;const ticket=++catalogRequest;searchController?.abort();const controller=searchController=new AbortController();catalogLoading=true;searchLoading=true;infiniteError=false;$('previous').disabled=true;$('next').disabled=true;render(append);
  try{const response=await fetch('/api/vod/search?q='+encodeURIComponent(query)+'&page='+page,{signal:controller.signal});if(!response.ok)throw Error();const data=await response.json();if(ticket!==catalogRequest||view!=='search'||$('search').value.trim()!==query)return;
    const seen=new Set(append?searchItems.map(item=>item.id):[]);searchItems=(append?searchItems:[]).concat(data.items.filter(item=>!seen.has(item.id)));moreAvailable=!!data.has_more;searchTotal=data.total;searchPage=page;$('pageLabel').textContent=page+' / '+Math.max(1,Math.ceil(data.total/data.page_size));$('previous').disabled=page<=1;$('next').disabled=!data.has_more;$('portalState').textContent='';
  }catch(error){if(ticket===catalogRequest&&error.name!=='AbortError'){infiniteError=true;$('portalState').textContent='No pudimos cargar más resultados. Puedes reintentar.';if(!append)searchItems=[]}}
  finally{if(ticket===catalogRequest){catalogLoading=false;searchLoading=false;render(append);scheduleInfiniteCheck()}}
}
function seriesIdentity(name){
  const full=String(name||'').trim().replace(/\s+/g,' '),match=full.match(/\s+(?:T|Temp\.?|Temporada|Season)\s*(\d+)\s*$/i);
  const title=match?full.slice(0,match.index).trim():full;
  return {title,key:title.normalize('NFC').toLocaleLowerCase(),number:match?Number(match[1]):null};
}
function groupSeries(list){
  const seen=new Set();return list.filter(item=>{if(item.kind!=='series')return true;const key=seriesIdentity(item.name).key;if(seen.has(key))return false;seen.add(key);return true;});
}
async function choose(item){
  const opening=++seriesOpening;savePlaybackProgress(video.ended);cancelVodPreparation();selectionRevision++;
  if(!$('watchDialog').open)$('watchDialog').showModal();
  $('watchDialog').scrollTop=0;
  seasonCollection=null;$('seasonBar').hidden=true;$('recommendationsSection').hidden=true;$('recommendationsItems').replaceChildren();
  if(item.kind!=='series'){prepareSelection(item);syncFavoriteControls();return;}
  selected=item;setContentArtwork(item);showPreview();$('title').textContent=seriesIdentity(item.name).title;$('selectedType').textContent='Serie';$('info').hidden=false;$('metadata').textContent=[item.genres,item.duration].filter(Boolean).join(' · ');$('description').textContent=item.description||'Consultando la reseña…';$('vodNotice').textContent='Consultando temporadas…';$('episodeSection').hidden=true;
  try{
    const response=await fetch('/api/vod/seasons/'+item.id);if(!response.ok)throw Error();const data=await response.json();
    if(opening!==seriesOpening||!$('watchDialog').open)return;
    if(!Array.isArray(data.items)||!data.items.length)throw Error();
    seasonCollection=data.items;seasonGroupTitle=data.title||seriesIdentity(item.name).title;
    $('seasonSelect').replaceChildren();data.items.forEach(entry=>{$('seasonSelect').append(new Option(entry.season_number!=null?'Temporada '+entry.season_number:entry.name,entry.id));});
    const chosen=data.items.find(entry=>entry.id===data.resume_id)||data.items[0];
    $('seasonSelect').value=chosen.id;$('seasonNote').textContent=data.complete?'': 'Hay más coincidencias de las que se pudieron consultar.';
    openSeason(chosen);
  }catch{
    if(opening!==seriesOpening||!$('watchDialog').open)return;
    prepareSelection(item);$('seasonBar').hidden=false;$('seasonSelect').replaceChildren(new Option(item.name,item.id));$('seasonSelect').disabled=true;$('seasonNote').textContent='No se pudieron consultar las otras temporadas. Vuelve a abrir la serie para reintentar.';
  }
}
function openSeason(item){prepareSelection(item);$('seasonBar').hidden=false;$('seasonSelect').disabled=false;$('title').textContent=seasonGroupTitle;syncFavoriteControls();}
$('seasonSelect').onchange=()=>{const item=seasonCollection?.find(entry=>entry.id===$('seasonSelect').value);if(item)openSeason(item);};

function stopPlayer(){
  seriesOpening++;seasonCollection=null;$('seasonBar').hidden=true;$('recommendationsSection').hidden=true;$('recommendationsItems').replaceChildren();
  selectionRevision++;cancelVodPreparation();setPlayerLoading(false);savePlaybackProgress(video.ended);current=null;selected=null;if(hls){hls.destroy();hls=null}video.pause();video.removeAttribute('src');setContentArtwork({});video.load();resetTracks();error.textContent='';
}
async function loadHome(){
  homeLoading=true;homeErrors={};renderShelves();
  const results=await Promise.allSettled(['movies','series'].map(async target=>{
    const response=await fetch('/api/vod/home?kind='+target);if(!response.ok)throw Error();const data=await response.json();shelves[target]=data.items;
    document.getElementById(target==='movies'?'movieShelfHeading':'seriesShelfHeading').textContent=(target==='movies'?'Películas':'Series')+' · '+(data.selection_label||'Novedades');
    if(view==='home'||!items.some(item=>item.kind===target))items=items.filter(item=>item.kind!==target).concat(data.items);
    if(view==='home')renderShelves();
  }));results.forEach((result,index)=>{if(result.status==='rejected')homeErrors[['movies','series'][index]]=true});homeLoading=false;if(view==='home')renderShelves();
}
async function init(){
  setView('home');const homeTask=loadHome();homeTask.finally(()=>refreshFeatured());
  const results=await Promise.allSettled([fetch('/api/catalog').then(async response=>{if(!response.ok)throw Error();const data=await response.json();items=data.items.filter(item=>item.kind==='tv').concat(items.filter(item=>item.kind!=='tv'));vodNote=data.vod_note||''}),fetch('/api/favorites').then(async response=>{if(!response.ok)throw Error();favoriteItems=(await response.json()).items;favoriteReady=true;syncFavoriteControls()})]);
  if(results[0].status==='rejected')notify('No pudimos actualizar los canales. Las otras secciones siguen disponibles.');
  if(results[1].status==='rejected')notify('No pudimos cargar Mi lista. Tus favoritos guardados se conservan.');
  if(view==='tv'||view==='favorites')render();await homeTask;
}
$('search').oninput=searchInput;$('group').onchange=render;
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>section(button.dataset.view));
document.querySelectorAll('[data-browse]').forEach(button=>button.onclick=()=>section(button.dataset.browse));
document.querySelectorAll('[data-scroll]').forEach(button=>button.onclick=()=>$(button.dataset.scroll).scrollBy({left:$(button.dataset.scroll).clientWidth*.8,behavior:'smooth'}));
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{favoriteFilter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));render()});
document.querySelectorAll('a.brand').forEach(link=>link.onclick=event=>{event.preventDefault();section('home')});
$('heroOpen').onclick=()=>{if(heroItems[heroIndex])choose(heroItems[heroIndex])};$('heroFavorite').onclick=()=>toggleFavorite(heroItems[heroIndex]);
$('heroPrevious').onclick=()=>{if(heroItems.length){heroIndex=(heroIndex+heroItems.length-1)%heroItems.length;renderHero()}};
$('heroNext').onclick=()=>{if(heroItems.length){heroIndex=(heroIndex+1)%heroItems.length;renderHero()}};
$('selectedFavorite').onclick=()=>toggleFavorite(selected);$('closePlayer').onclick=()=>$('watchDialog').close();
$('watchDialog').addEventListener('close',stopPlayer);
$('watchDialog').addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('trackPanel').hidden){event.preventDefault();event.stopPropagation();closeTrackPanel();$('trackSettings').focus()}});
$('watchDialog').addEventListener('click',event=>{if(event.target!==$('watchDialog'))return;const box=$('watchDialog').getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)$('watchDialog').close()});
setInterval(()=>{if($('watchDialog').open&&current)update()},3000);init();


async function loadCategories(target,firstPage){
  const ticket=++categoryTicket;
  function display(data){$('group').replaceChildren(new Option('Todas las categorías',''));for(const row of data.items)$('group').append(new Option(row.name,row.id));$('group').value=categorySelection[target]||'';}
  const snapshot=categorySnapshots.get(target);display(snapshot||{items:[]});$('group').disabled=!snapshot;
  try{await firstPage;if(ticket!==categoryTicket||view!==target)return;const response=await fetch('/api/vod/categories?kind='+target);if(!response.ok)throw Error();const data=await response.json();if(ticket!==categoryTicket||view!==target)return;
    categorySnapshots.set(target,data);display(data);
  }catch{if(ticket===categoryTicket&&view===target)notify('No pudimos cargar las categorías. Puedes explorar todos los títulos.');}
  finally{if(ticket===categoryTicket)$('group').disabled=false;}
}
$('group').onchange=()=>{if(!['movies','series','anime'].includes(view))return;categorySelection[view]=$('group').value;catalogPages[view]=1;loadPage(view,1);};
async function refreshFeatured(){
  if(featuredTask)return featuredTask;
  featuredTask=(async()=>{try{
    const response=await fetch('/api/vod/featured');if(!response.ok)throw Error();const data=await response.json();
    const previous=heroItems[heroIndex]?.id;
    if(data.banners.length){heroItems=data.banners;heroIndex=Math.max(0,heroItems.findIndex(i=>i.id===previous));renderHero();}
    const container=$('providerSections');container.replaceChildren();
    data.sections.forEach(row=>{
      if(!row.items.length)return;const section=document.createElement('section');section.className='shelf-section';
      const heading=document.createElement('div');heading.className='section-heading';const title=document.createElement('h2');title.textContent=row.name;heading.append(title);
      const shelf=document.createElement('div');shelf.className='shelf';shelf.setAttribute('aria-label',row.name);groupSeries(row.items).forEach(item=>shelf.append(mediaCard(item,true)));section.append(heading,shelf);container.append(section);
    });
    lastFeaturedRefresh=Date.now();
  }catch{if(!lastFeaturedRefresh)notify('No pudimos actualizar Destacados. Las otras secciones siguen disponibles.');}
  finally{featuredTask=null;}})();return featuredTask;
}
setInterval(()=>{if(view==='home'&&document.visibilityState!=='hidden'){refreshFeatured();loadHome();}},300000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&view==='home'&&Date.now()-lastFeaturedRefresh>300000){refreshFeatured();loadHome();}});

function updateInfiniteStatus(){
  const active=['movies','series','anime','search'].includes(view);$('loadMoreStatus').hidden=!active;
  $('catalogSpinner').hidden=!catalogLoading;$('loadMoreText').classList.toggle('sr-only',catalogLoading);
  $('loadMoreText').textContent=catalogLoading?(globalSearch()?'Buscando más resultados…':'Cargando más títulos…'):infiniteError?'La carga se interrumpió.':moreAvailable?'Sigue bajando para ver más':(globalSearch()?searchItems.length:(view==='anime'?animeItems:items.filter(i=>i.kind===kind)).length)?'Has llegado al final':'';
  $('retryMore').hidden=!infiniteError;$('loadMoreStatus').setAttribute('aria-busy',String(catalogLoading));
}
function requestMore(){
  if(catalogLoading||!moreAvailable||infiniteError||!['movies','series','anime','search'].includes(view)||$('watchDialog').open)return;
  if(globalSearch())loadSearch(searchPage+1,true);else loadPage(view,catalogPages[view]+1,true);
}
function checkInfinite(){
  if(!$('loadMoreStatus').hidden&&$('loadMoreStatus').getBoundingClientRect().top<window.innerHeight+500)requestMore();
}
function scheduleInfiniteCheck(){clearTimeout(infiniteTimer);infiniteTimer=setTimeout(checkInfinite,150);}
$('retryMore').onclick=()=>{infiniteError=false;const loaded=globalSearch()?searchItems.length:(view==='anime'?animeItems:items.filter(i=>i.kind===kind)).length;if(!loaded){if(globalSearch())loadSearch(1);else loadPage(view,1);}else{moreAvailable=true;requestMore();}};
window.addEventListener('scroll',()=>{scheduleInfiniteCheck();$('backToTop').classList.toggle('visible',window.scrollY>600);},{passive:true});
window.addEventListener('resize',scheduleInfiniteCheck);
$('backToTop').onclick=()=>window.scrollTo({top:0,behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});


async function loadRecommendations(item,revision){
  $('recommendationsSection').hidden=false;$('recommendationsItems').replaceChildren();$('recommendationsNote').textContent='Buscando recomendaciones…';
  try{
    const response=await fetch('/api/vod/recommendations/'+item.id);if(!response.ok)throw Error();const data=await response.json();
    if(selected?.id!==item.id||selectionRevision!==revision)return;
    const rows=groupSeries(data.items);$('recommendationsNote').textContent=rows.length?'':'No hay recomendaciones disponibles para este título.';
    rows.forEach(entry=>$('recommendationsItems').append(mediaCard(entry)));syncFavoriteControls();
  }catch{if(selected?.id===item.id&&selectionRevision===revision)$('recommendationsNote').textContent='No se pudieron cargar las recomendaciones.';}
}
