const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('outputs/windows-hls-player/index.html','utf8'),{url:'http://127.0.0.1/',runScripts:'dangerously',pretendToBeVisual:true});
const w=dom.window,d=w.document,v=d.getElementById('video'),root=d.getElementById('player');let paused=true,full=null;
Object.defineProperty(v,'duration',{value:1200,configurable:true});Object.defineProperty(v,'paused',{get:()=>paused});Object.defineProperty(v,'buffered',{value:{length:1,start:()=>0,end:()=>300}});v.currentTime=100;
v.play=()=>{paused=false;v.dispatchEvent(new w.Event('playing'));return Promise.resolve()};v.pause=()=>{paused=true;v.dispatchEvent(new w.Event('pause'))};Object.defineProperty(d,'fullscreenElement',{get:()=>full});root.requestFullscreen=async()=>{full=root;d.dispatchEvent(new w.Event('fullscreenchange'))};d.exitFullscreen=async()=>{full=null;d.dispatchEvent(new w.Event('fullscreenchange'))};
root.dataset.state='playing';d.getElementById('audioSelect').disabled=false;d.getElementById('audioSelect').innerHTML='<option value="0">Español</option><option value="1">Inglés</option>';
d.getElementById('subtitleSelect').disabled=false;
const source=fs.readFileSync('outputs/windows-hls-player/player.js','utf8');
w.eval("const $=id=>document.getElementById(id),video=$('video'),status=$('status');let current={kind:'movies'};function setPlayerLoading(){};function closeTrackPanel(){$('trackPanel').hidden=true};"+source.slice(source.indexOf('const customPlayerControls='))+"\nwindow.testControls=customPlayerControls;window.changeKind=kind=>{current.kind=kind;customPlayerControls.sync()};");
const click=id=>d.getElementById(id).click(),wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{try{
 const fullIcon=d.getElementById('videoFullscreen').querySelector('svg');for(let i=0;i<30;i++)w.testControls.sync();assert.equal(d.getElementById('videoFullscreen').querySelector('svg'),fullIcon,'Unchanged icon must survive timeline updates');
 assert.equal(v.controls,false);assert(root.classList.contains('custom-player'));assert.equal(d.getElementById('videoClock').textContent,'1:40 / 20:00');
 click('videoPlay');assert.equal(paused,false);click('videoPlay');assert.equal(paused,true);
 const seek=d.getElementById('videoSeek');seek.value='450';seek.dispatchEvent(new w.Event('input'));assert.equal(v.currentTime,100);seek.dispatchEvent(new w.Event('change'));assert.equal(v.currentTime,450);
 seek.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));assert.equal(v.currentTime,455);click('videoBack');assert.equal(v.currentTime,445);
 assert.equal(d.querySelector('.seek-played').style.width,(445/1200*100)+'%');assert.equal(d.querySelector('.seek-buffered span').style.width,'25%');
 const volume=d.getElementById('videoVolume');volume.value='30';volume.dispatchEvent(new w.Event('input'));assert.equal(v.volume,.3);click('videoMute');assert.equal(v.muted,true);click('videoMute');assert.equal(v.muted,false);
 click('videoAudio');assert.equal(d.getElementById('trackPanel').hidden,false);assert.equal(d.activeElement.id,'audioSelect');assert.equal(d.getElementById('videoAudio').getAttribute('aria-expanded'),'true');
 click('videoSubtitles');assert.equal(d.getElementById('trackPanel').hidden,false);assert.equal(d.getElementById('videoSubtitles').getAttribute('aria-expanded'),'true');click('videoSubtitles');assert.equal(d.getElementById('trackPanel').hidden,true);
 for(let i=0;i<20;i++){click('videoFullscreen');await wait(0);assert.equal(full,root);assert.equal(d.getElementById('trackPanel').closest('#player'),root);const icon=d.getElementById('videoFullscreen').querySelector('svg');w.testControls.sync();assert.equal(d.getElementById('videoFullscreen').querySelector('svg'),icon);click('videoFullscreen');await wait(0);assert.equal(full,null);}
 root.requestFullscreen=async()=>{throw new w.DOMException('Denied','NotAllowedError')};click('videoFullscreen');await wait(0);assert.equal(root.dataset.fullscreenError,'NotAllowedError');assert(d.getElementById('error').textContent.includes('No se pudo cambiar'));
 root.requestFullscreen=async()=>{full=root;d.dispatchEvent(new w.Event('fullscreenchange'))};click('videoFullscreen');await wait(0);assert.equal(d.getElementById('error').textContent,'');d.getElementById('videoFullscreen').focus();d.getElementById('videoFullscreen').dispatchEvent(new w.KeyboardEvent('keydown',{key:'f',bubbles:true,cancelable:true}));await wait(0);assert.equal(full,null);
 w.changeKind('tv');assert(d.querySelector('.video-seek').hidden);assert.equal(d.querySelector('.video-live-label').hidden,false);click('videoForward');assert.equal(v.currentTime,445);
 w.changeKind('movies');root.focus();root.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true,cancelable:true}));assert.equal(v.currentTime,435);
 await v.play();root.dispatchEvent(new w.MouseEvent('pointerdown'));w.testControls.show();await wait(3100);assert.equal(root.classList.contains('controls-visible'),true);d.dispatchEvent(new w.MouseEvent('pointerup'));await wait(3100);assert.equal(root.classList.contains('controls-visible'),false);v.pause();assert(root.classList.contains('controls-visible'));
 console.log('OK: custom play/pause, buffered/played timeline, deferred seek, keyboard, volume/mute, track shortcuts, container fullscreen, live mode and auto-hide');
}finally{w.close()}})().catch(e=>{console.error(e);process.exitCode=1});
