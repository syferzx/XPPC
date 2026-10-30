const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('outputs/windows-hls-player/player.js','utf8');
const start=source.slice(source.indexOf('function start('),source.indexOf("video.addEventListener('playing'"));
function scenario(target,paused=false,live=false){
 let playCalls=0,range=[],instances=[];const elements={};
 class Hls{static isSupported(){return true}static Events={MANIFEST_PARSED:'manifest',FRAG_BUFFERED:'buffer',AUDIO_TRACKS_UPDATED:'audio',SUBTITLE_TRACKS_UPDATED:'sub',ERROR:'error'};constructor(options){this.options=options;this.events={};instances.push(this)}on(n,f){this.events[n]=f}loadSource(){}attachMedia(){}destroy(){}}
 const video={currentTime:0,controls:false,hidden:false,buffered:{get length(){return range.length},start:i=>range[i][0],end:i=>range[i][1]},pause(){},play(){playCalls++;return Promise.resolve()}};
 const current={kind:live?'tv':'series',stream_url:'/vod/test/index.m3u8',progressStarted:true,duration_seconds:2500};
 const ctx={Hls,window:{Hls},video,current,hls:null,hlsDiagnostic:{},mediaRecoveryAttempts:0,status:{},error:{},$:id=>elements[id]??={dataset:{},value:'0'},setPlayerLoading(){},playbackLoadOptions:()=>({}),syncNativeTracks(){},update(){},Date};
 vm.createContext(ctx);vm.runInContext(start,ctx);ctx.start(target,paused);const instance=instances[0];
 instance.events.manifest();
 return {ctx,video,instance,current,get plays(){return playCalls},buffer(a,b){range=[[a,b]];instance.events.buffer(null,{frag:{sn:1,start:a,duration:b-a}})}};
}
const resume=scenario(1365.377);assert.equal(resume.instance.options.startPosition,1345.377);assert.equal(resume.plays,0);assert.equal(resume.video.currentTime,0);assert.equal(resume.current.progressStarted,false);
resume.buffer(1345,1350);assert.equal(resume.plays,0);assert.equal(resume.video.currentTime,0);
resume.buffer(1345,1370);assert.equal(resume.video.currentTime,1365.377);assert.equal(resume.plays,1);
resume.buffer(1345,1380);assert.equal(resume.plays,1);
const paused=scenario(125,true);paused.buffer(105,130);assert.equal(paused.plays,0);assert.equal(paused.video.currentTime,125);
const fresh=scenario(0);assert.equal(fresh.instance.options.startPosition,0);assert.equal(fresh.plays,1);
const live=scenario(100,false,true);assert.equal(live.instance.options.startPosition,-1);assert.equal(live.plays,1);
const stale=scenario(125);stale.ctx.current={kind:'series'};stale.buffer(105,150);assert.equal(stale.plays,0);
console.log('OK: resume preroll waits for target buffer, exact bookmark, single play, paused audio changes, fresh/live and stale callbacks');
