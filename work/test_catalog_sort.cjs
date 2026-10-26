const fs=require('node:fs'),assert=require('node:assert/strict'),vm=require('node:vm');
const source=fs.readFileSync('outputs/windows-hls-player/library.js','utf8'),ctx={};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function sortCatalogItems('),source.indexOf('const catalogSnapshots'))+source.slice(source.indexOf('function seriesIdentity('),source.indexOf('async function choose(')),ctx);
const a=[{id:'a',score:7,year:2001},{id:'b',score:9,year:2024},{id:'c',score:null},{id:'d',score:8,year:1995}];
assert.equal(ctx.sortCatalogItems(a,'rating-desc').map(x=>x.id).join(''),'bdac');assert.equal(ctx.sortCatalogItems(a,'rating-asc').map(x=>x.id).join(''),'adbc');assert.equal(ctx.sortCatalogItems(a,'year-desc').map(x=>x.id).join(''),'badc');assert.equal(ctx.sortCatalogItems(a,'year-asc').map(x=>x.id).join(''),'dabc');assert.equal(a.map(x=>x.id).join(''),'abcd');
const versions=[{kind:'series',name:'The Office T9',series_group_key:'US'},{kind:'series',name:'The Office T1',series_group_key:'US'},{kind:'series',name:'The Office T1',series_group_key:'UK'},{kind:'series',name:'The Office T2',series_group_key:'UK'}];assert.equal(ctx.groupSeries(versions).length,2);
console.log('OK: numeric sorting, missing values last, original order preserved and distinct editions');
