const fs=require('node:fs'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const app='outputs/windows-hls-player/';
const dom=new JSDOM(fs.readFileSync(app+'index.html','utf8'),{url:'http://localhost/',runScripts:'dangerously',pretendToBeVisual:true});
const w=dom.window,d=w.document;let sources=[],destroyed=0;
w.scrollTo=()=>{};w.Element.prototype.scrollBy=()=>{};
w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false;setTimeout(()=>this.dispatchEvent(new w.Event('close')),0)};
w.HTMLMediaElement.prototype.load=function(){};w.HTMLMediaElement.prototype.pause=function(){};w.HTMLMediaElement.prototype.play=function(){return Promise.resolve()};
class Hls{static isSupported(){return true}static Events={MANIFEST_PARSED:'manifest',ERROR:'error',AUDIO_TRACKS_UPDATED:'audio',SUBTITLE_TRACKS_UPDATED:'sub',FRAG_BUFFERED:'buffer'};constructor(){this.events={}}on(e,f){this.events[e]=f}loadSource(s){sources.push(s);queueMicrotask(()=>this.events.manifest?.())}attachMedia(){}destroy(){destroyed++}}
w.Hls=Hls;
const channels=[{id:'adult',name:'Adulto',kind:'tv',playable:true,groups:['Adultos +18']},{id:'news',name:'Noticias',kind:'tv',playable:true,groups:['Noticias']},{id:'sport',name:'Deporte',kind:'tv',playable:true,groups:['Deportes']},{id:'movie',name:'Cine',kind:'tv',playable:true,groups:['Cine y series']}];
w.fetch=async(url)=>({ok:true,json:async()=>url==='/api/catalog'?{items:channels}:url==='/api/favorites'?{items:[]}:url.startsWith('/api/vod/home')?{items:[]}:url==='/api/vod/featured'?{banners:[],sections:[]}:url==='/api/status'?{portal:{},tv:{}}:{items:[],total:0,page_size:40,episodes:[],item:{}}});
const run=code=>{const el=d.createElement('script');el.textContent=code;d.body.append(el)};
const flush=()=>new Promise(r=>setTimeout(r,20));
(async()=>{try{
run(fs.readFileSync(app+'player.js','utf8'));run(fs.readFileSync(app+'library.js','utf8'));await flush();
assert.equal(sources.length,0,'home never autoplays');
d.querySelector('[data-view="tv"]').click();await flush();
assert.equal(sources.at(-1),'/stream/news.m3u8','autoplay first non-adult channel, regardless of catalog order');assert(!d.getElementById('watchDialog').open);assert(d.getElementById('livePlayerDock').contains(d.getElementById('video')));assert(d.getElementById('video').muted);
let sections=[...d.querySelectorAll('.tv-category-section')];assert(sections.every(x=>x.tagName==='DETAILS'));assert.equal(sections.at(-1).querySelector('h2').textContent,'Adultos +18');assert.equal(sections.at(-1).open,false);
const sports=sections.find(x=>x.textContent.includes('Deporte'));sports.open=true;await flush();d.querySelector('[aria-label="Ver Deporte en vivo"]').click();await flush();assert.equal(d.getElementById('liveTitle').textContent,'Deporte');assert(d.querySelector('.tv-item.is-playing .tv-name').textContent==='Deporte');assert([...d.querySelectorAll('details')].find(x=>x.querySelector('h2').textContent==='Deportes').open);
const before=sources.length;d.getElementById('search').value='Cine';d.getElementById('search').dispatchEvent(new w.Event('input'));assert.equal(sources.length,before,'search must not restart live playback');assert.equal(d.querySelectorAll('#items .tv-item').length,1);
d.querySelector('[data-view="movies"]').click();await flush();assert(d.querySelector('.watch-overview').contains(d.getElementById('video')));assert.equal(d.getElementById('livePane').hidden,true);assert.equal(d.getElementById('video').muted,false);assert(destroyed>0);
d.querySelector('[data-view="tv"]').click();await flush();assert.equal(sources.at(-1),'/stream/sport.m3u8','return to last selected channel');
run("section('home');choose({id:'film',name:'Película',kind:'movies',playable:false})");await flush();assert(d.getElementById('watchDialog').open);
run("choose({id:'news',name:'Noticias',kind:'tv',playable:true})");await flush();assert.equal(sources.at(-1),'/stream/news.m3u8');assert(d.getElementById('livePlayerDock').contains(d.getElementById('video')));assert(!d.getElementById('watchDialog').open);assert.equal(d.getElementById('livePane').hidden,false,'delayed dialog close must not stop live TV');
console.log('PASS: inline TV autoplay, adult-last collapsed categories, selection, search, navigation, sound restoration and dialog-close race');
}catch(e){console.error(e);process.exitCode=1}finally{w.close();setTimeout(()=>process.exit(process.exitCode||0),20)}})();
