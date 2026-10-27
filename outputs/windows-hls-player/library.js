let animeItems=[];
const catalogSort={movies:'provider',series:'provider',anime:'provider'};
function sortCatalogItems(list,mode){
  if(!mode||mode==='provider')return list;
  const field=mode.startsWith('rating')?'score':'year',direction=mode.endsWith('asc')?1:-1;
  const numeric=item=>{const value=Number(String(item[field]??'').replace(',','.'));return Number.isFinite(value)&&value>0&&(field!=='score'||value<=10)?value:null;};
  return list.map((item,index)=>({item,index,value:numeric(item)})).sort((a,b)=>a.value===null?(b.value===null?a.index-b.index:1):b.value===null?-1:(a.value-b.value)*direction||a.index-b.index).map(entry=>entry.item);
}
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
let categorySelection={movies:'',series:'',anime:'',tv:''},categoryTicket=0,featuredTask=null,lastFeaturedRefresh=0;
/* Catalog presentation; playback remains in player.js. Favorites live in the PC profile. */
let view='home',favoriteItems=[],favoriteFilter='all',favoriteBusy=new Set(),favoriteReady=false,favoriteSaveQueue=Promise.resolve(),heroIndex=0,heroItems=[];
let shelves={movies:[],series:[]},homeLoading=true,homeErrors={},toastTimer,searchReturnView='home';
const icons={download:'i-download',heart:'i-heart',plus:'i-plus',check:'i-check',tv:'i-tv',search:'i-search'};
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#'+icons[name]);svg.setAttribute('aria-hidden','true');svg.append(use);return svg;}
function favoriteMatches(item){return favoriteItems.filter(saved=>saved.id===item.id||(item.kind==='series'&&saved.kind==='series'&&seriesGroupKey(saved)===seriesGroupKey(item)));}
function isFavorite(id){const entry=[selected,...items,...searchItems,...favoriteItems,...heroItems,...(seasonCollection||[])].find(item=>item?.id===id);return entry?favoriteMatches(entry).length>0:favoriteItems.some(item=>item.id===id);}
function notify(message){clearTimeout(toastTimer);$('toast').textContent=message;$('toast').hidden=false;toastTimer=setTimeout(()=>{$('toast').hidden=true},3500);}
function favoriteButton(item){const button=document.createElement('button');button.className='favorite-button';button.dataset.favorite=item.id;button.dataset.name=item.name;button.setAttribute('aria-pressed',String(isFavorite(item.id)));button.setAttribute('aria-label',(isFavorite(item.id)?'Quitar de Mi lista: ':'Añadir a Mi lista: ')+item.name);button.disabled=!favoriteReady||favoriteBusy.has(item.id);button.append(icon('heart'));button.onclick=event=>{event.stopPropagation();toggleFavorite(item)};return button;}
/* One shared preview: no playback, delayed detail lookup, bounded metadata cache. */
const cardPreview=(()=>{
  const cache=new Map();let panel,surface,active=null,openTimer,closeTimer,controller,revision=0,suppressed=null;
  function node(tag,className,text){const el=document.createElement(tag);if(className)el.className=className;if(text!==undefined)el.textContent=text;return el;}
  function duration(value){
    if(!value||/^0+(?::0+)*$/.test(String(value)))return '';
    const match=/^(\d{1,3}):(\d{2})(?::(\d{2}))?$/.exec(String(value));
    if(!match)return String(value);
    const hours=Number(match[1]),minutes=Number(match[2]);
    return [hours?hours+' h':'',minutes?minutes+' min':'',!hours&&!minutes&&Number(match[3])?match[3]+' s':''].filter(Boolean).join(' ');
  }
  function mount(card){
    if(!panel){
      panel=node('section','media-preview');panel.id='mediaPreview';panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Vista previa del contenido');panel.setAttribute('popover','manual');
      surface=node('div','preview-surface');panel.append(surface);
      panel.addEventListener('pointerenter',()=>clearTimeout(closeTimer));panel.addEventListener('pointerleave',leave);
      panel.addEventListener('focusin',()=>clearTimeout(closeTimer));panel.addEventListener('focusout',e=>{if(!panel.contains(e.relatedTarget)&&!active?.card.contains(e.relatedTarget))leave()});
    }
    const parent=card.closest('dialog[open]')||document.body;if(panel.parentElement!==parent)parent.append(panel);
    return panel;
  }
  function position(){
    if(!active||panel.hidden)return;
    if(!active.card.isConnected){hide();return;}
    const rect=active.card.getBoundingClientRect(),pad=12,gap=14,width=Math.min(370,window.innerWidth-pad*2);
    panel.style.width=width+'px';const height=Math.min(panel.getBoundingClientRect().height,window.innerHeight-pad*2);
    let side='right',left=rect.right+gap,top=Math.max(pad,Math.min(rect.top-12,window.innerHeight-height-pad));
    if(left+width>window.innerWidth-pad){side='left';left=rect.left-gap-width;}
    if(left<pad){side='below';left=Math.max(pad,Math.min(rect.left+(rect.width-width)/2,window.innerWidth-width-pad));top=Math.max(pad,Math.min(rect.bottom+gap,window.innerHeight-height-pad));}
    panel.dataset.side=side;panel.style.left=left+'px';panel.style.top=top+'px';
    panel.style.setProperty('--preview-arrow-y',Math.max(25,Math.min(height-25,rect.top+Math.min(rect.height/2,105)-top))+'px');
    panel.style.setProperty('--preview-arrow-x',Math.max(25,Math.min(width-25,rect.left+rect.width/2-left))+'px');
  }
  function paint(item,loading=false,failed=false){
    if(!active)return;const focused=surface.contains(document.activeElement)?document.activeElement.className:null;surface.replaceChildren();
    const header=node('div','preview-heading'),type=node('span','preview-type',item.kind==='series'?'SERIE'+(item.series_country?' · '+item.series_country:''):'PELÍCULA');
    const close=node('button','preview-close','×');close.type='button';close.setAttribute('aria-label','Cerrar vista previa');close.onclick=()=>hide(true);header.append(type,close);surface.append(header);
    const title=node('h3','preview-title',item.kind==='series'?seriesIdentity(item.name).title:item.name);title.id='previewTitle';panel.setAttribute('aria-labelledby',title.id);surface.append(title);
    const facts=node('div','preview-facts'),score=Number(item.score),time=duration(item.duration);
    if(Number.isFinite(score)&&score>0)facts.append(node('span','preview-score','★ '+score.toLocaleString('es-CL',{maximumFractionDigits:1})+' / 10'));
    if(item.year)facts.append(node('span','',String(item.year)));
    if(time)facts.append(node('span','preview-duration','Duración: '+time));
    if(item.kind==='series'&&Number(item.episodes)>0)facts.append(node('span','',''+item.episodes+' episodios informados'));
    if(facts.childNodes.length)surface.append(facts);
    if(item.genres){const genres=node('div','preview-genres');String(item.genres).split(/[,·]/).map(x=>x.trim()).filter(Boolean).slice(0,5).forEach(x=>genres.append(node('span','',x)));surface.append(genres);}
    surface.append(node('p','preview-description',item.description||'La reseña no está disponible para este título.'));
    if(item.cast){const cast=node('p','preview-cast');cast.append(node('strong','','Reparto: '),document.createTextNode(String(item.cast)));surface.append(cast);}
    if(loading||failed)surface.append(node('p','preview-note',loading?'Consultando más información…':'No se pudo ampliar la ficha. Puedes abrir el contenido para reintentar.'));
    const open=node('button','preview-open','Ver contenido');open.type='button';open.onclick=()=>{const entry=active?.item;hide();if(entry)choose(entry)};surface.append(open);if(focused==='preview-close')close.focus({preventScroll:true});else if(focused==='preview-open')open.focus({preventScroll:true});position();
  }
  async function show(card,item){
    if(!card.isConnected||suppressed===card)return;
    hide();active={card,item};const ticket=revision;mount(card);panel.hidden=false;
    if(typeof panel.showPopover==='function'){try{panel.showPopover()}catch{}}
    card.querySelector('.card-open')?.setAttribute('aria-details','mediaPreview');
    const saved=cache.get(item.id),fresh=saved&&Date.now()-saved.time<300000;
    paint(fresh?{...item,...saved.item,name:item.name}:item,!fresh);panel.classList.add('is-visible');position();
    if(fresh)return;
    const request=new AbortController();controller=request;
    try{
      const response=await fetch('/api/vod/detail/'+encodeURIComponent(item.id),{signal:request.signal});if(!response.ok)throw Error('detail');
      const data=await response.json();if(!data.item)throw Error('detail');
      const detail={...item,...data.item};for(const field of ['description','duration','cast','genres'])if(!detail[field])detail[field]=item[field];if(!detail.duration&&Array.isArray(data.episodes))detail.duration=data.episodes.find(e=>e.duration)?.duration||'';
      if(request.signal.aborted||ticket!==revision||active?.card!==card)return;
      cache.delete(item.id);cache.set(item.id,{item:detail,time:Date.now()});while(cache.size>100)cache.delete(cache.keys().next().value);
      paint({...detail,name:item.name});
    }catch(error){if(error.name!=='AbortError'&&ticket===revision&&active?.card===card)paint(item,false,true);}
    finally{if(controller===request)controller=null;}
  }
  function hide(restoreFocus=false){
    clearTimeout(openTimer);clearTimeout(closeTimer);revision++;controller?.abort();controller=null;
    const card=active?.card;card?.querySelector('.card-open')?.removeAttribute('aria-details');active=null;
    if(panel){panel.classList.remove('is-visible');if(typeof panel.hidePopover==='function'){try{panel.hidePopover()}catch{}}panel.hidden=true;}
    if(restoreFocus&&card?.isConnected){suppressed=card;card.querySelector('.card-open')?.focus({preventScroll:true});}
  }
  function leave(){clearTimeout(openTimer);clearTimeout(closeTimer);closeTimer=setTimeout(()=>hide(),180);}
  function bind(card,item){
    const schedule=()=>{if(suppressed===card)return;clearTimeout(closeTimer);clearTimeout(openTimer);if(active?.card===card)return;hide();openTimer=setTimeout(()=>show(card,item),480);};
    card.addEventListener('pointerenter',e=>{if(e.pointerType==='touch')return;suppressed=null;schedule()});card.addEventListener('pointerleave',()=>{suppressed=null;leave()});
    card.addEventListener('focusin',schedule);card.addEventListener('focusout',e=>{if(!card.contains(e.relatedTarget)&&!panel?.contains(e.relatedTarget))leave()});
  }
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&active){e.preventDefault();e.stopPropagation();hide(true);}},true);
  document.addEventListener('pointerdown',e=>{if(active&&!panel.contains(e.target)&&!active.card.contains(e.target))hide();},true);
  document.addEventListener('scroll',e=>{if(active&&!panel.contains(e.target))hide();},true);window.addEventListener('resize',()=>hide());
  return {bind,hide};
})();

function cardRating(value){
  const row=document.createElement('span');row.className='card-rating';
  const score=Number(String(value??'').replace(',','.'));
  if(!Number.isFinite(score)||score<=0||score>10){row.classList.add('unrated');row.textContent='Sin nota';return row;}
  const label=score.toLocaleString('es-CL',{maximumFractionDigits:1});
  row.setAttribute('role','img');row.setAttribute('aria-label','Calificación: '+label+' de 10');
  const stars=document.createElement('span');stars.className='rating-stars';stars.setAttribute('aria-hidden','true');stars.textContent='★';
  const number=document.createElement('span');number.className='rating-value';number.textContent=label+' / 10';number.setAttribute('aria-hidden','true');row.append(stars,number);return row;
}
function mediaCard(item,landscape=false){
  const card=document.createElement('article');card.className='media-card';const open=document.createElement('button');open.className='card-open';open.setAttribute('aria-label','Ver '+item.name);
  const picture=document.createElement('span');picture.className='card-image';
  const url=landscape?(item.backdrop_url||item.poster_url):item.poster_url;
  if(url){const img=document.createElement('img');img.alt='';img.loading='lazy';img.decoding='async';img.referrerPolicy='no-referrer';img.src=url;img.onerror=()=>img.remove();picture.append(img)}
  const tag=document.createElement('span');tag.className='card-tag';tag.textContent=item.kind==='series'?'SERIE':'PELÍCULA';picture.append(tag);
  const displayName=item.kind==='series'?seriesIdentity(item.name).title:item.name;const title=document.createElement('span');title.className='card-title';title.textContent=displayName;title.title=displayName;open.append(picture,title);
  if(!landscape){const meta=document.createElement('span');meta.className='card-meta';meta.textContent=[item.year,item.series_country,(item.genres||'').split(',').slice(0,2).join(' · ')].filter(Boolean).join(' · ')||(item.kind==='series'?'Serie':'Película');open.append(meta)}
  picture.append(cardRating(item.score));open.onclick=()=>choose(item);card.append(open,favoriteButton(item));if(item.kind==='movies'){const download=document.createElement('button');download.className='card-download';download.append(icon('download'));download.title='Descargar';download.setAttribute('aria-label','Descargar '+item.name+' en MKV o MP4');download.onclick=()=>window.downloadUI?.open(item);card.append(download)}cardPreview.bind(card,item);return card;
}
function tvCard(item){
  const card=document.createElement('article');card.className='tv-item';const open=document.createElement('button');open.className='tv-open';open.setAttribute('aria-label','Ver '+item.name+' en vivo');
  const art=document.createElement('span');art.className='tv-icon';art.textContent=item.name.slice(0,2);
  if(item.poster_url){const img=document.createElement('img');img.src=item.poster_url;img.loading='lazy';img.alt='';img.referrerPolicy='no-referrer';img.onerror=()=>img.remove();art.append(img)}
  const copy=document.createElement('span');copy.className='tv-copy';const name=document.createElement('span');name.className='tv-name';name.textContent=item.name;const number=document.createElement('span');number.className='tv-number';number.textContent=(item.number?'Canal '+item.number+' · ':'')+'En vivo';copy.append(name,number);open.append(art,copy);open.onclick=()=>choose({...item,playable:item.playable!==false});open.setAttribute('aria-pressed',String(selected?.kind==='tv'&&selected.id===item.id));card.classList.toggle('is-playing',selected?.kind==='tv'&&selected.id===item.id);card.append(open,favoriteButton(item));return card;
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
const tvCategoryOpen=new Map();
let lastLiveChannel=null,liveMutedBefore=false,tvCatalogLoading=true;
function tvCategoryOrder(a,b){return Number(a==='Adultos +18')-Number(b==='Adultos +18')||a.localeCompare(b,'es');}
function tvGroups(item){
  const groups=Array.isArray(item.groups)&&item.groups.length?item.groups:['General y variedades'];
  // Reclassify older cached catalogs without restarting the active TV stream.
  if(!groups.includes('Adultos +18')&&/(?<!\d)24\s*[/x×-]\s*7(?!\d)/i.test(item.name||''))return ['24/7',...groups.filter(group=>group==='Premium')];
  return groups;
}
function fillTvCategories(){
  const channels=items.filter(item=>item.kind==='tv'),counts=new Map();
  channels.forEach(item=>new Set(tvGroups(item)).forEach(name=>counts.set(name,(counts.get(name)||0)+1)));
  if(!counts.has('Adultos +18'))counts.set('Adultos +18',0);
  const names=[...counts.keys()].sort(tvCategoryOrder);
  if(!counts.has(categorySelection.tv))categorySelection.tv='';
  $('group').replaceChildren(new Option('Todas las categorías',''));
  names.forEach(name=>$('group').append(new Option(name+' ('+counts.get(name)+')',name)));
  $('group').value=categorySelection.tv;$('group').disabled=false;
}
function renderTvGroups(list){
  const sections=new Map();
  list.forEach(item=>{const group=tvGroups(item)[0];if(!sections.has(group))sections.set(group,[]);sections.get(group).push(item)});
  const names=[...sections.keys()].sort(tvCategoryOrder),query=$('search').value.trim();
  names.forEach((name,index)=>{
    const section=document.createElement('details');section.className='tv-category-section';
    section.open=!!query||!!categorySelection.tv||(tvCategoryOpen.has(name)?tvCategoryOpen.get(name):name!=='Adultos +18'&&sections.get(name).some(item=>item.id===selected?.id));
    const heading=document.createElement('summary');heading.className='tv-category-heading';
    const title=document.createElement('h2');title.textContent=name;
    const count=document.createElement('span');count.className='tv-category-count';count.textContent=String(sections.get(name).length);
    const arrow=document.createElement('span');arrow.className='tv-category-chevron';arrow.textContent='⌄';arrow.setAttribute('aria-hidden','true');heading.append(title,count,arrow);
    const grid=document.createElement('div');grid.className='tv-list';grid.setAttribute('aria-label',name);
    sections.get(name).forEach(item=>grid.append(tvCard(item)));section.append(heading,grid);$('items').append(section);
    // Ignore queued toggle events from detached lists after a search or channel change.
    section.ontoggle=()=>{if(section.isConnected&&!query&&!categorySelection.tv)tvCategoryOpen.set(name,section.open)};
  });
}
function dockLivePlayer(live){
  const playback=$('watchPlayback');
  if(live){$('livePlayerDock').append(playback);}
  else document.querySelector('.watch-overview').append(playback);
  $('livePane').hidden=!live;$('catalogLayout').classList.toggle('live-layout',live);
}
function ensureLiveChannel(){
  if(view!=='tv'||selected?.kind==='tv')return;
  const channels=items.filter(item=>item.kind==='tv'&&item.playable!==false&&!item.restricted&&!tvGroups(item).includes('Adultos +18'));
  const first=channels.find(item=>item.id===lastLiveChannel)||channels[0];
  if(first){video.muted=true;$('sound').textContent='Activar sonido';choose({...first,playable:true});}
}
function render(append=false){
  if(view==='downloads'){window.downloadUI?.loadList();return;}
  if(catalogSort[view]&&catalogSort[view]!=='provider')append=false;
  if(!append)cardPreview.hide();
  if(view==='home'){renderShelves();return}
  const query=$('search').value.trim().toLocaleLowerCase();let list;
  if(view==='favorites')list=favoriteItems.filter(item=>favoriteFilter==='all'||item.kind===favoriteFilter);
  else if(globalSearch())list=searchItems;
  else list=view==='anime'?animeItems:items.filter(item=>item.kind===kind);
  if(view==='tv'){
    fillTvCategories();
    if(categorySelection.tv)list=list.filter(item=>tvGroups(item).includes(categorySelection.tv));
    if(query)list=list.filter(item=>(item.name+' '+(item.number||'')+' '+tvGroups(item).join(' ')).toLocaleLowerCase().includes(query));
  }
  list=sortCatalogItems(groupSeries(list),catalogSort[view]);
  $('sortScope').hidden=!catalogSort[view]||catalogSort[view]==='provider';
  $('sortScope').textContent='Orden aplicado a '+list.length+' títulos cargados. Al bajar se incorporan más; los que no tienen ese dato quedan al final.';
  $('items').className=view==='tv'?'tv-sections':'poster-grid';const existing=append?$('items').children.length:0;if(!append)$('items').replaceChildren();
  if(view==='favorites')$('count').textContent=favoriteItems.length+' '+(favoriteItems.length===1?'favorito guardado':'favoritos guardados')+' en este PC';
  else if(globalSearch())$('count').textContent=searchLoading?'Buscando en todo el catálogo…':searchTotal.toLocaleString('es-CL')+' resultados · películas y series';
  else $('count').textContent=view==='tv'?list.length.toLocaleString('es-CL')+' canales':(catalogTotals[kind]||list.length).toLocaleString('es-CL')+' títulos';
  if(!list.length&&view==='tv'&&tvCatalogLoading){const loading=document.createElement('div');loading.className='live-catalog-loading';loading.setAttribute('role','status');const spinner=document.createElement('span');spinner.className='catalog-spinner';spinner.setAttribute('aria-hidden','true');loading.append(spinner,document.createTextNode('Cargando canales…'));$('items').append(loading);}
  else if(!list.length&&view==='tv'&&categorySelection.tv==='Adultos +18')$('items').append(emptyState('Sin canales +18 disponibles','El catálogo que entrega tu sesión no contiene canales en esta categoría.'));
  else if(!list.length){if(searchLoading||catalogLoading){const pending=document.createElement('p');pending.className='catalog-loading';pending.textContent='Buscando tu próxima historia…';$('items').append(pending)}else if(view==='favorites')$('items').append(emptyState(favoriteItems.length?'No hay favoritos en esta sección':'Tu próxima historia empieza aquí',favoriteItems.length?'Prueba otro filtro para ver tus títulos guardados.':'Pulsa el corazón de una película, serie o canal para guardarlo en Mi lista.','heart'));else if(globalSearch()&&query.length<2)$('items').append(emptyState('¿Qué te gustaría ver?','Escribe al menos dos caracteres para buscar en todo el catálogo.'));else $('items').append(emptyState('No encontramos resultados','Prueba con otro título o vuelve a explorar la biblioteca.'))}
  else if(view==='tv')renderTvGroups(list);
  else list.slice(existing).forEach(item=>$('items').append(item.kind==='tv'?tvCard(item):mediaCard(item)));
  syncFavoriteControls();updateInfiniteStatus();
}
function setView(next){
  cardPreview.hide();
  if(view==='tv'&&next!=='tv'){stopPlayer();dockLivePlayer(false);video.muted=liveMutedBefore;$('sound').textContent=video.muted?'Activar sonido':'Silenciar';}
  if(view!=='tv'&&next==='tv')liveMutedBefore=video.muted;
  view=next;$('sortControl').hidden=!['movies','series','anime'].includes(next);if(catalogSort[next])$('sortOrder').value=catalogSort[next];dockLivePlayer(next==='tv');$('homeView').hidden=next!=='home';$('catalogView').hidden=next==='home'||next==='downloads';if($('downloadsView'))$('downloadsView').hidden=next!=='downloads';$('favoriteFilters').hidden=next!=='favorites';$('paging').hidden=true;$('loadMoreStatus').hidden=!['movies','series','anime','search'].includes(next);
  const headings={movies:'Películas',series:'Series',anime:'Anime',tv:'TV en vivo',favorites:'Mi lista',search:'Resultados de búsqueda'};
  $('catalogTitle').textContent=headings[next]||'';$('catalogEyebrow').textContent=next==='favorites'?'TUS HISTORIAS, SIEMPRE A MANO':next==='tv'?'LO QUE ESTÁ PASANDO AHORA':'EXPLORA LA BIBLIOTECA';
  document.querySelectorAll('[data-view]').forEach(button=>{if(button.dataset.view===next)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current')});
  $('search').placeholder=next==='tv'?'Buscar canal o categoría…':'Buscar películas y series…';$('group').hidden=!['movies','series','anime','tv'].includes(next);$('categoryLabel').hidden=$('group').hidden;
}
function section(next){
  clearTimeout(searchTimer);searchController?.abort();++catalogRequest;moreAvailable=false;infiniteError=false;catalogLoading=false;searchLoading=false;searchItems=[];searchTotal=0;$('search').value='';$('portalState').textContent='';
  if(['tv','movies','series','anime'].includes(next))kind=next;
  setView(next);render();if(['movies','series','anime'].includes(next)){const firstPage=loadPage(next,1);loadCategories(next,firstPage);}if(next==='home'){loadHome();refreshFeatured();}
  if(next==='downloads'){stopPlayer();window.downloadUI?.loadList();}
  if(next==='tv')ensureLiveChannel();
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
function seriesGroupKey(item){return item.series_group_key||(seriesIdentity(item.name).key+'|'+String(item.series_country||'').toLocaleLowerCase());}
function groupSeries(list){
  const seen=new Set();return list.filter(item=>{if(item.kind!=='series')return true;const key=seriesGroupKey(item);if(seen.has(key))return false;seen.add(key);return true;});
}
async function choose(item){
  if(view==='anime')item={...item,_isAnime:true};
  cardPreview.hide();
  if(item.kind==='tv'){
    if($('watchDialog').open)$('watchDialog').close();
    if(view!=='tv'){kind='tv';setView('tv');}
    dockLivePlayer(true);lastLiveChannel=item.id;$('liveTitle').textContent=item.name;
    prepareSelection({...item,playable:item.playable!==false});syncFavoriteControls();return;
  }
  // A single player is shared by inline TV and the movie/series dialog.
  if(view==='tv')section(item.kind==='series'?'series':'movies');
  const opening=++seriesOpening;savePlaybackProgress(video.ended);cancelVodPreparation();selectionRevision++;
  if(!$('watchDialog').open)$('watchDialog').showModal();
  $('watchDialog').scrollTop=0;
  seasonCollection=null;$('seasonBar').hidden=true;$('recommendationsSection').hidden=true;$('recommendationsItems').replaceChildren();
  if(item.kind!=='series'){prepareSelection(item);syncFavoriteControls();return;}
  selected=item;window.downloadUI?.refresh();setContentArtwork(item);showPreview();$('title').textContent=seriesIdentity(item.name).title;$('selectedType').textContent='Serie';$('info').hidden=false;$('metadata').textContent=[item.genres,item.duration].filter(Boolean).join(' · ');$('description').textContent=item.description||'Consultando la reseña…';$('vodNotice').textContent='Consultando temporadas…';$('episodeSection').hidden=true;
  try{
    const response=await fetch('/api/vod/seasons/'+item.id);if(!response.ok)throw Error();const data=await response.json();
    if(opening!==seriesOpening||!$('watchDialog').open)return;
    if(!Array.isArray(data.items)||!data.items.length)throw Error();
    seasonCollection=data.items;seasonGroupTitle=(data.title||seriesIdentity(item.name).title)+(data.country?' · '+data.country:'');
    $('seasonSelect').replaceChildren();data.items.forEach(entry=>{$('seasonSelect').append(new Option(entry.season_number!=null?'Temporada '+entry.season_number:entry.name,entry.id));});
    const chosen=data.items.find(entry=>entry.id===data.resume_id)||data.items[0];
    $('seasonSelect').value=chosen.id;$('seasonNote').textContent=data.complete?'': 'Hay más coincidencias de las que se pudieron consultar.';
    openSeason(chosen);
  }catch{
    if(opening!==seriesOpening||!$('watchDialog').open)return;
    prepareSelection(item);$('seasonBar').hidden=false;$('seasonSelect').replaceChildren(new Option(item.name,item.id));$('seasonSelect').disabled=true;$('seasonNote').textContent='No se pudieron consultar las otras temporadas. Vuelve a abrir la serie para reintentar.';
  }
}
function openSeason(item){if(selected?._isAnime)item={...item,_isAnime:true};prepareSelection(item);$('seasonBar').hidden=false;$('seasonSelect').disabled=false;$('title').textContent=seasonGroupTitle;syncFavoriteControls();}
$('seasonSelect').onchange=()=>{const item=seasonCollection?.find(entry=>entry.id===$('seasonSelect').value);if(item)openSeason(item);};

function stopPlayer(){
  stopVodReadAhead();
  seriesOpening++;seasonCollection=null;$('seasonBar').hidden=true;$('recommendationsSection').hidden=true;$('recommendationsItems').replaceChildren();
  selectionRevision++;cancelVodPreparation();setPlayerLoading(false);savePlaybackProgress(video.ended);resetTracks();current=null;selected=null;if(hls){hls.destroy();hls=null}video.pause();video.removeAttribute('src');setContentArtwork({});video.load();resetTracks();error.textContent='';
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
  tvCatalogLoading=false;
  if(results[0].status==='rejected')notify('No pudimos actualizar los canales. Las otras secciones siguen disponibles.');
  if(results[1].status==='rejected')notify('No pudimos cargar Mi lista. Tus favoritos guardados se conservan.');
  if(view==='tv'||view==='favorites')render();ensureLiveChannel();await homeTask;
}
$('sortOrder').onchange=()=>{if(!catalogSort[view])return;catalogSort[view]=$('sortOrder').value;render();};
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
$('watchDialog').addEventListener('close',()=>{if(view!=='tv'||selected?.kind!=='tv')stopPlayer();});
$('watchDialog').addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('trackPanel').hidden){event.preventDefault();event.stopPropagation();closeTrackPanel();focusTrackTrigger()}});
$('watchDialog').addEventListener('click',event=>{if(event.target!==$('watchDialog'))return;const box=$('watchDialog').getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)$('watchDialog').close()});
setInterval(()=>{if(($('watchDialog').open||view==='tv')&&current)update()},3000);init();


async function loadCategories(target,firstPage){
  const ticket=++categoryTicket;
  function display(data){$('group').replaceChildren(new Option('Todas las categorías',''));for(const row of data.items)$('group').append(new Option(row.name,row.id));$('group').value=categorySelection[target]||'';}
  const snapshot=categorySnapshots.get(target);display(snapshot||{items:[]});$('group').disabled=!snapshot;
  try{await firstPage;if(ticket!==categoryTicket||view!==target)return;const response=await fetch('/api/vod/categories?kind='+target);if(!response.ok)throw Error();const data=await response.json();if(ticket!==categoryTicket||view!==target)return;
    categorySnapshots.set(target,data);display(data);
  }catch{if(ticket===categoryTicket&&view===target)notify('No pudimos cargar las categorías. Puedes explorar todos los títulos.');}
  finally{if(ticket===categoryTicket)$('group').disabled=false;}
}
$('group').onchange=()=>{if(view==='tv'){categorySelection.tv=$('group').value;render();return;}if(!['movies','series','anime'].includes(view))return;categorySelection[view]=$('group').value;catalogPages[view]=1;loadPage(view,1);};
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
