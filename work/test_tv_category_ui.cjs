const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const dom=new JSDOM('<select id="group"></select><input id="search"><div id="items"></div><p id="count"></p>');
const source=fs.readFileSync('outputs/windows-hls-player/library.js','utf8');
const document=dom.window.document;
const items=[
  {id:'1',name:'Deporte Premium',kind:'tv',groups:['Deportes','Premium']},
  {id:'2',name:'Cine Premium',kind:'tv',groups:['Cine y series','Premium']},
  {id:'3',name:'Noticias',kind:'tv',groups:['Noticias']},
  {id:'4',name:'Canal adulto',kind:'tv',groups:['Adultos +18']},
];
const ctx=vm.createContext({document,Option:dom.window.Option,$:id=>document.getElementById(id),items,
  view:'tv',kind:'tv',categorySelection:{tv:''},favoriteItems:[],searchItems:[],favoriteFilter:'all',
  groupSeries:list=>list,globalSearch:()=>false,catalogTotals:{},catalogLoading:false,searchLoading:false,
  syncFavoriteControls:()=>{},updateInfiniteStatus:()=>{},emptyState:()=>document.createElement('p'),
  tvCard:item=>{const node=document.createElement('article');node.className='tv-item';node.dataset.id=item.id;return node},
});
vm.runInContext(source.slice(source.indexOf('function tvGroups('),source.indexOf('function setView(')),ctx);
vm.runInContext('render()',ctx);
assert.equal(document.querySelectorAll('.tv-item').length,4);
assert.equal(document.querySelectorAll('.tv-category-section').length,4);
assert.equal(document.querySelectorAll('#group option').length,6);
assert.equal([...document.querySelectorAll('#group option')].find(o=>o.value==='Premium').textContent,'Premium (2)');
vm.runInContext("categorySelection.tv='Premium';render()",ctx);
assert.equal(document.querySelectorAll('.tv-item').length,2);
assert.equal(document.querySelectorAll('.tv-category-section').length,2);
document.getElementById('search').value='deporte';vm.runInContext('render()',ctx);
assert.equal(document.querySelectorAll('.tv-item').length,1);
assert.equal(document.querySelector('.tv-item').dataset.id,'1');
document.getElementById('search').value='';
vm.runInContext("categorySelection.tv='Adultos +18';render()",ctx);
assert.equal(document.querySelectorAll('.tv-item').length,1);
assert.equal(document.querySelector('.tv-item').dataset.id,'4');
vm.runInContext("categorySelection.tv='No existe';render()",ctx);
assert.equal(document.getElementById('group').value,'');
assert.equal(document.querySelectorAll('.tv-item').length,4);
vm.runInContext("view='movies';kind='movies';items.push({id:'m',name:'Pelicula',kind:'movies'});mediaCard=item=>document.createElement('article');render()",ctx);
assert.equal(document.getElementById('items').className,'poster-grid');
assert.equal(document.getElementById('items').children.length,1);
console.log('TV grouping, Premium/adult filters, search, stale category and movie view: OK');
