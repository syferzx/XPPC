const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const app=path.resolve('outputs/windows-hls-player');
const movie={id:'a'.repeat(20),kind:'movies',name:'Horizontes reales',groups:[],genres:'Aventura,Drama',description:'Una historia del catálogo real.',poster_url:'https://joqotx.p27i1en9.com/public/images/test',backdrop_url:'https://joqotx.p27i1en9.com/public/images/wide',playable:false};
const series={...movie,id:'b'.repeat(20),kind:'series',name:'Las historias del bosque'};
const tv={id:'c'.repeat(20),kind:'tv',name:'Canal de prueba',number:'7',groups:[],playable:true};
let saved=[],requests=[],failSave=false,hlsSources=[],favoriteDelays=[],bookmarks={},detailDelays=[],failVod=false,rejectNextPlay=false,deferredPlays=[],infiniteTest=false,failMore=false,releaseMore=null,seasonTest=false;
const dom=new JSDOM(fs.readFileSync(path.join(app,'index.html'),'utf8'),{url:'http://127.0.0.1:60000/',runScripts:'dangerously',pretendToBeVisual:true});
const w=dom.window,d=w.document;
d.getElementById('loadMoreStatus').getBoundingClientRect=()=>({top:10000});
w.scrollTo=()=>{};w.Element.prototype.scrollBy=()=>{};
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','')};
w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new w.Event('close'))};
w.HTMLMediaElement.prototype.load=function(){this.currentTime=0};w.HTMLMediaElement.prototype.pause=function(){};w.HTMLMediaElement.prototype.play=function(){if(rejectNextPlay){rejectNextPlay=false;return Promise.reject(new w.DOMException('Autoplay blocked','NotAllowedError'))}this.dispatchEvent(new w.Event('playing'));return Promise.resolve()};
class Hls{static isSupported(){return true}static Events={MANIFEST_PARSED:'manifest',AUDIO_TRACKS_UPDATED:'audio',SUBTITLE_TRACKS_UPDATED:'sub',FRAG_BUFFERED:'buffer',ERROR:'error'};constructor(options){this.options=options;this.events={}}on(name,fn){this.events[name]=fn}loadSource(url){hlsSources.push(url);queueMicrotask(()=>{this.events.manifest?.();const start=Math.max(0,this.options.startPosition);Object.defineProperty(d.getElementById('video'),'buffered',{configurable:true,value:{length:1,start:()=>start,end:()=>start+200}});this.events.buffer?.(null,{frag:{sn:1,start,duration:200}})})}attachMedia(){}destroy(){Object.defineProperty(d.getElementById('video'),'buffered',{configurable:true,value:{length:0}})}}
w.Hls=Hls;
w.fetch=async(url,options={})=>{
  requests.push({url,method:options.method||'GET',signal:options.signal});let value={};const u=new URL(url,w.location.href);
  if(u.pathname==='/api/catalog')value={items:[tv],default_id:tv.id,vod_note:''};
  else if(u.pathname==='/api/favorites'){
    if(options.method==='POST'){
      if(failSave)return {ok:false,status:500,json:async()=>({})};
      const body=JSON.parse(options.body);if(body.action==='add'){const item=[movie,series,tv].find(x=>x.id===body.id);if(!saved.some(x=>x.id===item.id))saved.unshift(item)}else saved=saved.filter(x=>x.id!==body.id);
    }value={items:saved.map(x=>({...x})),storage:'local_profile'};if(options.method==='POST'){const ms=favoriteDelays.shift()||0;if(ms)await new Promise(resolve=>setTimeout(resolve,ms))}
  }else if(u.pathname==='/api/vod/featured')value={banners:[movie],sections:[{name:'Destacados actuales',items:[movie,series]}]};
  else if(u.pathname==='/api/vod/categories')value={items:[{id:'123',name:'Acción'},{id:'456',name:'Drama'}]};
  else if(u.pathname==='/api/vod/home')value={items:u.searchParams.get('kind')==='movies'?[movie]:[series],selection_label:'Novedades · 2026'};
  else if(u.pathname==='/api/vod/catalog'){const kind=u.searchParams.get('kind'),page=Number(u.searchParams.get('page'));if(infiniteTest&&page>1){if(releaseMore)await releaseMore;if(failMore)return {ok:false,status:500,json:async()=>({})};value={items:[movie,{...movie,id:'d'.repeat(20),name:'Nueva película al bajar'}],page,total:2,page_size:1,has_more:false}}else value={items:kind==='movies'?[movie]:[series],page,total:81,page_size:40,has_more:true}}
  else if(u.pathname==='/api/vod/search')value=infiniteTest?(Number(u.searchParams.get('page'))>1?{items:[series,{...movie,id:'e'.repeat(20),name:'Otra coincidencia'}],total:3,page_size:2,has_more:false}:{items:[movie,series],total:3,page_size:2,has_more:true}):{items:[movie,series],total:2,page_size:40,has_more:false};
  else if(u.pathname.startsWith('/api/vod/detail/')){const item=u.pathname.endsWith(series.id)||(seasonTest&&u.pathname.endsWith('f'.repeat(20)))?series:movie;value={item,episodes:item.kind==='series'?[{number:1,name:'Uno'},{number:2,name:'Dos'}]:[{number:1,name:'Película'}]};const delay=detailDelays.shift()||0;if(delay)await new Promise(resolve=>setTimeout(resolve,delay));}
  else if(u.pathname.startsWith('/api/progress/'))value={progress:bookmarks[u.pathname.split('/').pop()]||null};
  else if(u.pathname.startsWith('/api/vod/seasons/'))value=seasonTest?{title:'Bosque',items:[{...series,id:'f'.repeat(20),name:'Bosque T1',season_number:1},{...series,name:'Bosque T2',season_number:2}],resume_id:bookmarks['f'.repeat(20)]?'f'.repeat(20):series.id,complete:true}:{title:series.name,items:[{...series,season_number:1}],complete:true};
  else if(u.pathname.startsWith('/api/vod/recommendations/'))value={items:[{...movie,id:'9'.repeat(20),name:'Otra historia recomendada'}]};
  else if(u.pathname==='/api/progress'){const b=JSON.parse(options.body);const entry=bookmarks[b.id]??={episodes:{}};entry.last_episode=b.episode;entry.episodes[b.episode]=b;value={progress:entry};}
  else if(u.pathname==='/api/vod/play'){const delayed=deferredPlays.shift();if(delayed){await delayed.promise;if(delayed.fail)return {ok:false,status:502,json:async()=>({error:'Respuesta antigua'})};}if(failVod)return {ok:false,status:502,json:async()=>({error:'Fallo de prueba'})};value={url:delayed?'/vod/late/index.m3u8':'/vod/test/index.m3u8',audio_tracks:[{index:0,language:'spa'},{index:1,language:'eng'}],subtitle_tracks:[],episode:JSON.parse(options.body).episode||1};}
  else if(u.pathname==='/api/status')value={portal:{connected:true},tv:{},expires_unix:0};
  return {ok:true,status:200,json:async()=>structuredClone(value)};
};
const flush=(ms=15)=>new Promise(resolve=>setTimeout(resolve,ms));
const click=selector=>{const el=d.querySelector(selector);assert(el,'Missing '+selector);el.click();return el};
const result={};
(async()=>{
 try{
  const scriptErrors=[];w.addEventListener('error',event=>scriptErrors.push(event.message));
  const style=d.createElement('style');style.textContent=fs.readFileSync(path.join(app,'app.css'),'utf8');d.head.append(style);assert(style.sheet.cssRules.length>100);
  for(const name of ['player.js','library.js']){const script=d.createElement('script');script.textContent=fs.readFileSync(path.join(app,name),'utf8');d.body.append(script)}await flush();assert.deepEqual(scriptErrors,[]);
  assert.equal(d.getElementById('homeView').hidden,false);assert.equal(d.getElementById('heroTitle').textContent,movie.name);
  assert.equal(d.querySelectorAll('#movieShelf .media-card').length,1);assert.equal(d.querySelectorAll('#seriesShelf .media-card').length,1);
  assert.equal(d.querySelectorAll('.card-fallback').length,0);result.cover_initials_absent=true;
  assert.equal(hlsSources.length,0);assert.equal(requests.filter(r=>r.url==='/api/vod/play').length,0);result.home_uses_catalog_without_autoplay=true;
  click('[data-view="movies"]');await flush();click('#items .card-open');await flush();
  assert(d.getElementById('watchDialog').open);assert.equal(d.getElementById('video').controls,false);assert.equal(d.getElementById('playVod'),null);
  assert.equal(d.getElementById('video').muted,false);assert.equal(d.getElementById('video').hasAttribute('muted'),false);assert.equal(d.getElementById('sound').textContent,'Silenciar');result.sound_enabled_by_default=true;
  click('#sound');assert.equal(d.getElementById('video').muted,true);click('#sound');assert.equal(d.getElementById('video').muted,false);result.sound_toggle_still_works=true;
  assert.equal(requests.filter(r=>r.url==='/api/vod/play').length,1);assert(d.getElementById('playerLoading').hidden);result.movie_starts_on_open=true;
  click('#selectedFavorite');await flush();assert.equal(saved.length,1);assert.equal(d.getElementById('favoriteCount').textContent,'1');click('#closePlayer');
  click('[data-view="favorites"]');assert.equal(d.querySelectorAll('#items .media-card').length,1);click('#items .card-open');await flush();
  assert.equal(requests.filter(r=>r.url==='/api/vod/play').length,2);assert(hlsSources.includes('/vod/test/index.m3u8'));result.favorite_opens_and_starts_movie=true;
  click('#trackSettings');assert.equal(d.getElementById('trackPanel').hidden,false);
  d.getElementById('title').dispatchEvent(new w.Event('pointerdown',{bubbles:true}));assert.equal(d.getElementById('trackPanel').hidden,true);
  click('#trackSettings');const escape=new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});d.getElementById('watchDialog').dispatchEvent(escape);
  assert.equal(escape.defaultPrevented,true);assert.equal(d.getElementById('watchDialog').open,true);assert.equal(d.getElementById('trackPanel').hidden,true);result.audio_panel_outside_and_escape_close_correctly=true;
  click('#selectedFavorite');await flush();click('#closePlayer');assert.equal(saved.length,0);assert(d.getElementById('items').textContent.includes('Tu próxima historia empieza aquí'));result.remove_updates_empty_favorites=true;
  click('[data-view="tv"]');assert.equal(d.querySelectorAll('#items .tv-item').length,1);assert.equal(d.querySelectorAll('#items .media-card').length,0);
  click('#items .favorite-button');await flush();click('#items .tv-open');assert(hlsSources.some(x=>x.includes('/stream/'+tv.id)));click('#closePlayer');result.tv_icons_list_and_favorites_work=true;
  click('[data-view="movies"]');await flush();const search=d.getElementById('search');search.value='alias';search.dispatchEvent(new w.Event('input'));await flush(380);
  assert.equal(d.querySelectorAll('#items .media-card').length,2);assert(d.getElementById('items').textContent.includes(series.name));result.global_search_preserves_alias_matches=true;
  const seriesFavorite=[...d.querySelectorAll('#items [data-favorite]')].find(x=>x.dataset.favorite===series.id);seriesFavorite.click();await flush();assert.equal(saved.length,2);
  search.value='';search.dispatchEvent(new w.Event('input'));await flush();assert.equal(d.getElementById('catalogTitle').textContent,'Películas');result.clearing_search_restores_previous_section=true;
  click('[data-view="favorites"]');click('[data-filter="series"]');assert.equal(d.querySelectorAll('#items .media-card').length,1);click('[data-filter="tv"]');assert.equal(d.querySelectorAll('#items .tv-item').length,1);result.favorite_type_filters_work=true;
  failSave=true;click('#items .favorite-button');await flush();assert.equal(saved.length,2);assert.equal(d.querySelector('#items [data-favorite]').getAttribute('aria-pressed'),'true');assert(d.getElementById('toast').textContent.includes('No se pudo'));result.failed_save_preserves_list=true;
  failSave=false;click('[data-view="movies"]');await flush();search.value='alias';search.dispatchEvent(new w.Event('input'));await flush(380);favoriteDelays=[70,0];
  const buttons=[...d.querySelectorAll('#items [data-favorite]')];buttons.find(x=>x.dataset.favorite===movie.id).click();buttons.find(x=>x.dataset.favorite===series.id).click();await flush(110);
  assert.equal(d.querySelector('#items [data-favorite="'+movie.id+'"]').getAttribute('aria-pressed'),'true');assert.equal(d.querySelector('#items [data-favorite="'+series.id+'"]').getAttribute('aria-pressed'),'false');assert.equal(saved.length,2);result.rapid_favorite_changes_keep_latest_state=true;
  click('[data-view="series"]');await flush();click('#items .card-open');await flush();
  assert.equal(d.getElementById('episodeSection').hidden,false);assert.equal(d.querySelectorAll('.episode-row').length,2);
  assert.equal(d.getElementById('player').contains(d.getElementById('episodeSection')),false);
  assert.equal(d.getElementById('episodes').hidden,true);
  const playRequests=requests.filter(r=>r.url==='/api/vod/play').length;
  click('.episode-row[data-episode="2"]');await flush();assert.equal(d.getElementById('episodes').value,'2');assert.equal(requests.filter(r=>r.url==='/api/vod/play').length,playRequests+1);
  assert.equal(d.querySelector('.episode-row[data-episode="2"]').getAttribute('aria-pressed'),'true');result.episodes_below_player_start_on_click=true;
  d.getElementById('video').currentTime=125;Object.defineProperty(d.getElementById('video'),'duration',{value:1800,configurable:true});d.getElementById('video').dispatchEvent(new w.Event('pause'));await flush();
  assert.equal(bookmarks[series.id].last_episode,'2');assert.equal(bookmarks[series.id].episodes['2'].position,125);
  click('#closePlayer');await flush();click('#items .card-open');await flush();
  assert.equal(d.getElementById('episodes').value,'2');assert(d.querySelector('.episode-row[data-episode="2"]').textContent.includes('0:02:05'));
  assert.equal(d.getElementById('video').currentTime,125);result.series_resumes_saved_episode_and_position=true;
  d.getElementById('video').currentTime=1800;Object.defineProperty(d.getElementById('video'),'ended',{value:true,configurable:true});d.getElementById('video').dispatchEvent(new w.Event('ended'));await flush();
  assert.equal(bookmarks[series.id].episodes['2'].completed,true);click('#closePlayer');await flush();click('#items .card-open');await flush();assert(d.querySelector('.episode-row[data-episode="2"]').textContent.includes('Visto'));
  assert.equal(d.getElementById('video').currentTime,0);result.completed_episode_starts_from_beginning=true;
  click('#closePlayer');click('[data-view="movies"]');await flush();click('#items .card-open');await flush();assert.equal(d.getElementById('episodeSection').hidden,true);result.movies_hide_episode_section=true;
  click('#closePlayer');detailDelays=[60,0];const beforeReopen=requests.filter(r=>r.url==='/api/vod/play').length;
  click('#items .card-open');click('#closePlayer');click('#items .card-open');await flush(90);
  assert.equal(requests.filter(r=>r.url==='/api/vod/play').length,beforeReopen+1);result.reopening_same_title_ignores_stale_detail=true;
  click('#closePlayer');detailDelays=[50];const beforeClose=requests.filter(r=>r.url==='/api/vod/play').length;click('#items .card-open');click('#closePlayer');await flush(70);
  assert.equal(requests.filter(r=>r.url==='/api/vod/play').length,beforeClose);result.closed_dialog_does_not_start_playback=true;
  detailDelays=[50];click('#items .card-open');assert.equal(d.getElementById('playerLoading').hidden,false);assert.equal(d.getElementById('player').getAttribute('aria-busy'),'true');await flush(70);
  assert.equal(d.getElementById('playerLoading').hidden,true);assert.equal(d.getElementById('playerPrompt'),null);assert.equal(d.getElementById('playerLoading').textContent,'Cargando…');assert.equal(d.querySelector('.buffering-spinner'),null);result.preparation_shows_text_without_extra_spinner=true;
  const video=d.getElementById('video');Object.defineProperty(video,'paused',{value:false,configurable:true});video.dispatchEvent(new w.Event('waiting'));assert.equal(d.getElementById('playerLoading').hidden,false);
  video.dispatchEvent(new w.Event('playing'));assert.equal(d.getElementById('playerLoading').hidden,true);video.dispatchEvent(new w.Event('waiting'));video.dispatchEvent(new w.Event('pause'));assert.equal(d.getElementById('playerLoading').hidden,true);delete video.paused;result.buffering_uses_only_custom_indicator=true;
  click('#closePlayer');failVod=true;click('#items .card-open');await flush();assert.equal(d.getElementById('playerLoading').hidden,true);assert.equal(d.getElementById('error').textContent,'Fallo de prueba');result.failed_preparation_stops_spinner=true;
  failVod=false;click('#retry');await flush();assert.equal(d.getElementById('video').controls,false);assert.equal(d.getElementById('playerLoading').hidden,true);result.retry_recovers_failed_preparation=true;
  click('#closePlayer');rejectNextPlay=true;click('#items .card-open');await flush();assert.equal(d.getElementById('playerLoading').hidden,true);assert.equal(video.muted,false);assert.equal(video.controls,false);assert.equal(d.getElementById('status').textContent,'Pausado');result.blocked_audio_autoplay_stops_spinner_and_keeps_custom_controls=true;
  click('#closePlayer');click('[data-view="series"]');await flush();let release;deferredPlays=[{promise:new Promise(r=>{release=r})}];click('#items .card-open');await flush();
  assert([...d.querySelectorAll('.episode-row')].every(row=>!row.disabled));const oldRequest=requests.filter(r=>r.url==='/api/vod/play').at(-1);
  const selectedEpisode=d.getElementById('episodes').value,otherEpisode=selectedEpisode==='1'?'2':'1';click('.episode-row[data-episode="'+otherEpisode+'"]');await flush();
  assert.equal(oldRequest.signal.aborted,true);assert(d.getElementById('selectedType').textContent.endsWith(otherEpisode));const started=hlsSources.length;release();await flush();
  assert.equal(hlsSources.length,started);assert(!hlsSources.includes('/vod/late/index.m3u8'));assert(d.getElementById('selectedType').textContent.endsWith(otherEpisode));result.switch_during_preparation_aborts_and_ignores_late_success=true;
  Object.defineProperty(video,'paused',{value:false,configurable:true});video.dispatchEvent(new w.Event('waiting'));assert.equal(d.getElementById('playerLoading').hidden,false);assert([...d.querySelectorAll('.episode-row')].every(row=>!row.disabled));
  click('.episode-row[data-episode="'+selectedEpisode+'"]');await flush();assert(d.getElementById('selectedType').textContent.endsWith(selectedEpisode));delete video.paused;result.switch_during_buffering_stays_enabled=true;
  let rejectOld;deferredPlays=[{promise:new Promise(r=>{rejectOld=r}),fail:true}];click('.episode-row[data-episode="'+otherEpisode+'"]');await flush();click('.episode-row[data-episode="'+selectedEpisode+'"]');await flush();rejectOld();await flush();
  assert.equal(d.getElementById('error').textContent,'');assert(d.getElementById('selectedType').textContent.endsWith(selectedEpisode));result.late_failure_does_not_replace_new_episode=true;
  click('#closePlayer');click('[data-view="movies"]');await flush();assert.equal(d.getElementById('group').hidden,false);assert.equal(d.getElementById('group').options.length,3);
  d.getElementById('group').value='123';d.getElementById('group').dispatchEvent(new w.Event('change'));await flush();assert(requests.some(r=>r.url.includes('category=123')));result.provider_categories_filter_full_catalog=true;
  click('[data-view="home"]');await flush();assert(d.getElementById('providerSections').textContent.includes('Destacados actuales'));assert.equal(d.getElementById('group').hidden,true);result.provider_featured_sections_render=true;
  infiniteTest=true;click('[data-view="movies"]');await flush();const firstCard=d.querySelector('#items .media-card');const beforeMore=requests.filter(r=>r.url.startsWith('/api/vod/catalog')).length;
  let resumeMore;releaseMore=new Promise(r=>resumeMore=r);d.getElementById('loadMoreStatus').getBoundingClientRect=()=>({top:0});w.dispatchEvent(new w.Event('scroll'));await flush(180);w.dispatchEvent(new w.Event('scroll'));await flush(180);
  assert.equal(requests.filter(r=>r.url.startsWith('/api/vod/catalog')).length,beforeMore+1);assert.equal(d.querySelector('#items .media-card'),firstCard);assert.equal(d.getElementById('catalogSpinner').hidden,false);assert(d.getElementById('loadMoreText').classList.contains('sr-only'));resumeMore();releaseMore=null;await flush(40);
  assert.equal(d.getElementById('catalogSpinner').hidden,true);assert.equal(d.getElementById('loadMoreText').classList.contains('sr-only'),false);result.catalogue_spinner_replaces_visible_loading_text_and_stops_on_completion=true;
  assert.equal(d.querySelectorAll('#items .media-card').length,2);assert.equal(d.querySelector('#items .media-card'),firstCard);assert(d.getElementById('loadMoreText').textContent.includes('final'));assert.equal(d.getElementById('paging').hidden,true);result.infinite_scroll_appends_preserves_nodes_and_deduplicates=true;
  w.dispatchEvent(new w.Event('scroll'));await flush(180);assert.equal(requests.filter(r=>r.url.startsWith('/api/vod/catalog')).length,beforeMore+1);result.infinite_scroll_stops_at_end_and_prevents_duplicate_requests=true;
  d.getElementById('loadMoreStatus').getBoundingClientRect=()=>({top:10000});click('[data-view="movies"]');await flush();failMore=true;d.getElementById('loadMoreStatus').getBoundingClientRect=()=>({top:0});w.dispatchEvent(new w.Event('scroll'));await flush(180);
  assert.equal(d.querySelectorAll('#items .media-card').length,1);assert.equal(d.getElementById('retryMore').hidden,false);failMore=false;click('#retryMore');await flush();assert.equal(d.querySelectorAll('#items .media-card').length,2);result.failed_infinite_load_preserves_cards_and_retries=true;
  Object.defineProperty(w,'scrollY',{value:900,configurable:true});w.dispatchEvent(new w.Event('scroll'));assert(d.getElementById('backToTop').classList.contains('visible'));let scrollOptions;w.scrollTo=o=>scrollOptions=o;w.matchMedia=()=>({matches:false});click('#backToTop');assert.equal(scrollOptions.top,0);assert.equal(scrollOptions.behavior,'smooth');w.matchMedia=()=>({matches:true});click('#backToTop');assert.equal(scrollOptions.behavior,'instant');result.back_to_top_smooth_and_reduced_motion=true;
  d.getElementById('loadMoreStatus').getBoundingClientRect=()=>({top:10000});search.value='global';search.dispatchEvent(new w.Event('input'));await flush(390);assert.equal(d.querySelectorAll('#items .media-card').length,2);
  const firstSearch=d.querySelector('#items .media-card');d.getElementById('loadMoreStatus').getBoundingClientRect=()=>({top:0});w.dispatchEvent(new w.Event('scroll'));await flush(180);assert.equal(d.querySelectorAll('#items .media-card').length,3);assert.equal(d.querySelector('#items .media-card'),firstSearch);result.global_search_also_appends_on_scroll=true;
  d.getElementById('loadMoreStatus').getBoundingClientRect=()=>({top:10000});infiniteTest=false;seasonTest=true;series.name='Bosque T2';Object.defineProperty(video,'ended',{value:false,configurable:true});click('[data-view="series"]');await flush();
  const injected=d.createElement('script');injected.textContent='items.push({...items.find(i=>i.kind==="series"),id:"ffffffffffffffffffff",name:"Bosque T1"});render();';d.body.append(injected);
  assert.equal(d.querySelectorAll('#items .media-card').length,1);assert.equal(d.querySelector('#items .card-title').textContent,'Bosque');click('#items .card-open');await flush();assert.equal(d.getElementById('seasonSelect').options.length,2);assert.equal(d.getElementById('seasonSelect').value,series.id);
  d.getElementById('seasonSelect').value='f'.repeat(20);d.getElementById('seasonSelect').dispatchEvent(new w.Event('change'));await flush();assert.equal(d.getElementById('title').textContent,'Bosque');assert.equal(d.querySelectorAll('.episode-row').length,2);
  video.currentTime=45;video.dispatchEvent(new w.Event('pause'));await flush();click('#closePlayer');await flush();click('#items .card-open');await flush();assert.equal(d.getElementById('seasonSelect').value,'f'.repeat(20));assert.equal(video.currentTime,45);result.grouped_series_season_picker_and_cross_season_resume=true;
  assert.equal(d.getElementById('recommendationsSection').hidden,false);assert(d.getElementById('recommendationsItems').textContent.includes('Otra historia recomendada'));d.getElementById('watchDialog').scrollTop=900;
  click('#recommendationsItems .card-open');await flush();assert.equal(d.getElementById('title').textContent,'Otra historia recomendada');assert.equal(d.getElementById('watchDialog').scrollTop,0);result.provider_recommendations_open_in_same_player=true;
  assert.equal(d.querySelectorAll('button button').length,0);result.no_nested_buttons=true;
  click('#closePlayer');video.poster='https://example.com/old.jpg';
  const posterSwitch=d.createElement('script');posterSwitch.textContent='choose({id:"bbbbbbbbbbbbbbbbbbbb",kind:"series",name:"Nueva serie",backdrop_url:"https://example.com/new.jpg"});';d.body.append(posterSwitch);
  assert.equal(video.getAttribute('poster'),'https://example.com/new.jpg');assert.equal(video.hasAttribute('src'),false);result.poster_switches_before_season_response=true;
  click('#closePlayer');assert.equal(video.hasAttribute('poster'),false);
  video.poster='https://example.com/old.jpg';const noPoster=d.createElement('script');noPoster.textContent='choose({id:"bbbbbbbbbbbbbbbbbbbb",kind:"series",name:"Sin imagen"});';d.body.append(noPoster);
  assert.equal(video.hasAttribute('poster'),false);click('#closePlayer');await flush();assert.equal(video.hasAttribute('poster'),false);result.missing_poster_and_closed_dialog_never_reuse_old_art=true;
  click('[data-view="anime"]');await flush();assert.equal(d.getElementById('catalogTitle').textContent,'Anime');assert.equal(d.getElementById('group').hidden,false);assert(d.querySelector('#items .media-card'));assert(requests.some(r=>r.url.startsWith('/api/vod/catalog?kind=anime')));click('#items .card-open');await flush();assert.equal(d.getElementById('episodeSection').hidden,false);click('#closePlayer');result.anime_navigation_preserves_series_playback=true;
  click('[data-view="home"]');await flush();const baseFetch=w.fetch;let finishSeries;const waitingSeries=new Promise(r=>finishSeries=r);
  w.fetch=async(url,options)=>{if(url==='/api/vod/home?kind=series')await waitingSeries;return baseFetch(url,options)};
  const progressive=d.createElement('script');progressive.textContent='shelves={movies:[],series:[]};heroItems=[];loadHome();';d.body.append(progressive);await flush();
  assert(d.querySelector('#movieShelf .media-card'));assert(d.querySelector('#seriesShelf .shelf-loading'));assert.equal(d.getElementById('heroTitle').textContent,movie.name);finishSeries();await flush();assert(d.querySelector('#seriesShelf .media-card'));w.fetch=baseFetch;result.home_renders_first_response_before_slower_section=true;
  for(const target of ['movies','series','anime']){
    click('[data-view="'+target+'"]');await flush();const cachedName=d.querySelector('#items .card-title').textContent;
    click('[data-view="home"]');let releaseCatalogue;const slowCatalogue=new Promise(r=>releaseCatalogue=r);
    w.fetch=async(url,options)=>{if(url.startsWith('/api/vod/catalog?kind='+target)){await slowCatalogue;return {ok:false,status:502,json:async()=>({})}}return baseFetch(url,options)};
    click('[data-view="'+target+'"]');assert.equal(d.querySelector('#items .card-title').textContent,cachedName);assert.equal(d.getElementById('group').disabled,false);
    releaseCatalogue();await flush();assert.equal(d.querySelector('#items .card-title').textContent,cachedName);w.fetch=baseFetch;
  }
  result.catalogue_tabs_show_cached_titles_before_network_and_keep_them_on_failure=true;
  click('[data-view="movies"]');await flush();let releaseCategory;const slowCategory=new Promise(r=>releaseCategory=r);
  w.fetch=async(url,options)=>{if(url.includes('/api/vod/catalog?kind=movies')&&url.includes('category=456'))await slowCategory;return baseFetch(url,options)};
  d.getElementById('group').value='456';d.getElementById('group').dispatchEvent(new w.Event('change'));assert.equal(d.querySelectorAll('#items .media-card').length,0);
  click('[data-view="anime"]');await flush();releaseCategory();await flush();assert.equal(d.getElementById('catalogTitle').textContent,'Anime');assert.equal(d.querySelector('#items .card-title').textContent,'Bosque');w.fetch=baseFetch;result.category_switch_hides_unrelated_titles_and_ignores_late_response=true;
  assert(d.querySelector('#backToTop svg path'));assert.equal(d.querySelector('#backToTop span'),null);
  assert.equal(d.getElementById('castHelpButton'),null);assert.equal(d.getElementById('castHelpPanel'),null);
  click('#items .card-open');await flush();assert.equal(d.getElementById('info').closest('.watch-overview').className,'watch-overview');assert(d.getElementById('player').closest('.watch-playback'));assert(d.getElementById('episodeSection').closest('.watch-extras'));assert(d.getElementById('recommendationsSection').closest('.watch-extras'));assert.equal(d.getElementById('watchBackdrop').getAttribute('src'),video.getAttribute('poster'));assert.equal(d.getElementById('watchBackdrop').hidden,false);click('#closePlayer');assert.equal(d.getElementById('watchBackdrop').hasAttribute('src'),false);assert.equal(d.getElementById('watchBackdrop').hidden,true);result.compact_modal_groups_synopsis_player_and_extras_and_clears_backdrop=true;
  click('#items .card-open');await flush();Hls.prototype.recoverMediaError=function(){this.recoveries=(this.recoveries||0)+1;};
  function hlsFailure(type){const event=d.createElement('script');event.textContent='hls.events.error(null,{type:'+JSON.stringify(type)+',details:"bufferAppendError",fatal:true});';d.body.append(event);}
  hlsFailure('mediaError');assert.equal(d.getElementById('status').textContent,'Recuperando reproducción');assert.equal(d.getElementById('error').textContent,'');
  hlsFailure('mediaError');assert(d.getElementById('error').textContent.includes('decodificar'));assert.equal(d.getElementById('status').textContent,'No disponible');
  click('#retry');await flush();hlsFailure('networkError');assert.equal(d.getElementById('status').textContent,'Conexión interrumpida');assert(d.getElementById('error').textContent.includes('descargar'));result.media_recovery_is_bounded_and_network_errors_are_distinct=true;
  const compatible=d.createElement('script');compatible.textContent='current.base_stream_url="/vod/aaaaaaaaaaaaaaaaaaaaaaaa/index.m3u8";current.stream_url=current.base_stream_url;start();';d.body.append(compatible);await flush();video.currentTime=27;
  hlsFailure('mediaError');hlsFailure('mediaError');await flush();assert(hlsSources.at(-1).includes('/compat/'));assert.equal(video.currentTime,27);const compatibilitySources=hlsSources.length;
  hlsFailure('mediaError');hlsFailure('mediaError');await flush();assert.equal(hlsSources.length,compatibilitySources);assert(d.getElementById('error').textContent.includes('decodificar'));result.compatibility_fallback_preserves_position_and_does_not_loop=true;
  const previousFetch=w.fetch;let exportJob=null,exportCalls=[];
  w.fetch=async(url,options={})=>{
    if(!url.startsWith('/api/downloads'))return previousFetch(url,options);
    const body=JSON.parse(options.body||'{}');exportCalls.push({url,body});
    if(url==='/api/downloads')return {ok:true,json:async()=>({items:exportJob?[exportJob]:[],folder:'C:\\Exports'})};
    if(url.endsWith('/prepare'))exportJob={id:'d'.repeat(32),state:'options',name:'Export test',audio_tracks:[{index:0,language:'spa'}],subtitle_tracks:[],total_bytes:1000};
    else if(url.endsWith('/start'))exportJob={...exportJob,state:'queued',queue_position:1};
    else if(url.endsWith('/cancel'))exportJob={...exportJob,state:'cancelled'};
    return {ok:true,json:async()=>({...exportJob})};
  };
  const downloadScript=d.createElement('script');downloadScript.textContent=fs.readFileSync(path.join(app,'downloads.js'),'utf8');d.body.append(downloadScript);await flush();
  click('#closePlayer');click('[data-view="movies"]');await flush();const playsBeforeDirectExport=requests.filter(r=>r.url==='/api/vod/play').length;
  click('#items .card-download');await flush();assert.equal(requests.filter(r=>r.url==='/api/vod/play').length,playsBeforeDirectExport);assert.equal(d.getElementById('watchDialog').open,false);assert.equal(d.getElementById('downloadDialog').open,true);result.cover_download_does_not_start_playback=true;
  click('#downloadClose');await flush();click('#items .card-open');await flush();const playingHlsCount=hlsSources.length;
  click('#downloadContent');await flush();assert.equal(d.getElementById('watchDialog').open,false);assert.equal(video.hasAttribute('src'),false);assert.equal(video.buffered.length,0);assert(requests.some(r=>r.url==='/api/vod/buffer/stop'));assert.equal(hlsSources.length,playingHlsCount);result.download_stops_player_and_server_read_ahead=true;
  click('#downloadStart');await flush();assert.equal(d.getElementById('downloadDialog').open,false);assert.equal(d.getElementById('downloadAdded').hidden,false);click('#downloadAddedOpen');await flush();assert.equal(d.getElementById('downloadsView').hidden,false);assert.equal(d.getElementById('catalogView').hidden,true);assert.equal(d.getElementById('homeView').hidden,true);assert(d.querySelector('.download-row-status').textContent.includes('En cola'));result.queue_animation_and_downloads_navigation_work=true;
  result.success=true;
 }catch(error){result.success=false;result.error=error.stack;process.exitCode=1}
 finally{fs.writeFileSync(path.join(app,'pruebas/library-redesign-dom.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));w.close()}
})();

