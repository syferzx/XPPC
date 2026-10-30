const fs=require('node:fs'),assert=require('node:assert/strict');const {JSDOM}=require('jsdom');const dom=new JSDOM(fs.readFileSync('outputs/windows-hls-player/index.html','utf8'),{url:'http://127.0.0.1/',runScripts:'outside-only'}),w=dom.window,d=w.document,v=d.getElementById('video');
const native=[];Object.defineProperty(v,'textTracks',{get:()=>native});const tracks=new WeakMap();
function fakeTrack(){return {mode:'showing',cues:[{text:'Anterior'}],removeCue(cue){this.cues.splice(this.cues.indexOf(cue),1)}}}
Object.defineProperty(w.HTMLTrackElement.prototype,'track',{get(){if(!tracks.has(this)){const track=fakeTrack();tracks.set(this,track);native.push(track)}return tracks.get(this)}});
const orphan=fakeTrack();native.push(orphan);const old=d.createElement('track');old.src='/old.vtt';v.append(old);const oldTrack=old.track;
const source=fs.readFileSync('outputs/windows-hls-player/player.js','utf8');
w.eval("var $=id=>document.getElementById(id),video=$('video'),selectionRevision=1,current={kind:'series',audio_tracks:[{index:0,language:'ja'}],subtitle_tracks:[{index:0,language:'es',url:'/new.vtt'}],track_settings_available:true,base_stream_url:'/vod/new/index.m3u8'},hls={subtitleDisplay:true,subtitleTrack:1};"+source.slice(source.indexOf('function languageName'),source.indexOf("$('trackSettings').onclick")));
w.playbackPreferences={choose:()=>({audio:'0',subtitle:'0',note:''})};
w.eval('resetTracks()');assert.equal(orphan.mode,'disabled');assert.equal(orphan.cues.length,0);assert.equal(oldTrack.mode,'disabled');assert.equal(oldTrack.cues.length,0);assert(!old.isConnected);
w.eval('configureTracks()');const currentTrack=v.querySelector('track');assert.equal(currentTrack.track.mode,'showing');d.getElementById('subtitleSelect').value='-1';w.eval('applySubtitle()');assert(native.every(t=>t.mode==='disabled'));
w.eval("selectionRevision++;resetTracks();current=null");const note=d.getElementById('trackNote').textContent;currentTrack.dispatchEvent(new w.Event('error'));currentTrack.dispatchEvent(new w.Event('load'));assert.equal(d.getElementById('trackNote').textContent,note);assert(native.every(t=>t.mode==='disabled'&&t.cues.length===0));
console.log('PASS: detached/native cues cleared, subtitles off, title change and late track callbacks ignored');w.close();
