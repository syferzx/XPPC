window.playbackPreferences=(()=>{
 const $=id=>document.getElementById(id);
 const defaults={general:{audio:'original',subtitle:'off'},anime:{audio:'ja',subtitle:'es'}};let values=JSON.parse(JSON.stringify(defaults));
 const canonical=code=>({spa:'es',eng:'en',jpn:'ja',kor:'ko',zho:'zh',chi:'zh',por:'pt',fra:'fr',fre:'fr',deu:'de',ger:'de',ita:'it'}[String(code||'').toLowerCase()]||String(code||'').toLowerCase().split('-')[0]);
 function group(item){return item?._isAnime||item?.is_anime||/\banime\b/i.test((item?.genres||'')+' '+(item?.groups||[]).join(' '))?'anime':'general'}
 function choose(item,audio=[],subs=[]){const pref=values[group(item)],find=(tracks,language)=>tracks.find(t=>canonical(t.language||t.lang)===canonical(language));let track,note='';
  if(pref.audio==='original'){track=audio.find(t=>t.original===true||t.is_original===true)|| (item?.original_language?find(audio,item.original_language):null);if(!track){const countries={'united states':'en','estados unidos':'en','usa':'en','united kingdom':'en','reino unido':'en','japan':'ja','japón':'ja','japon':'ja','south korea':'ko','corea del sur':'ko','germany':'de','alemania':'de','france':'fr','francia':'fr','italy':'it','italia':'it','brazil':'pt','brasil':'pt','spain':'es','españa':'es'};const hint=countries[String(item?.original_country||item?.series_country||'').trim().toLowerCase()];track=hint?find(audio,hint):null;note=track?'Audio original estimado según el país de origen. Puedes cambiarlo manualmente.':'No se identificó el audio original; se usa la pista predeterminada.'}}
  else if(pref.audio!=='default'){track=find(audio,pref.audio);if(!track)note='El audio preferido no está disponible; se usa la pista predeterminada.'}
  const subtitle=pref.subtitle==='off'?null:find(subs,pref.subtitle);if(pref.subtitle!=='off'&&!subtitle)note+=(note?' ':'')+'No hay subtítulos en el idioma preferido.';
  return {audio:String(track?.index??audio[0]?.index??0),subtitle:String(subtitle?.index??-1),note};
 }
 const fields=[['general','prefGeneralAudio','prefGeneralSub'],['anime','prefAnimeAudio','prefAnimeSub']];
 const names={es:'Español',en:'Inglés',ja:'Japonés',ko:'Coreano',zh:'Chino',pt:'Portugués',fr:'Francés',de:'Alemán',it:'Italiano'};
 for(const [,audio,sub] of fields){for(const [id,options] of [[audio,{original:'Audio original',default:'Pista predeterminada',...names}],[sub,{off:'Desactivados',...names}]])for(const [value,label] of Object.entries(options))$(id).append(new Option(label,value))}
 function paint(){for(const [group,audio,sub] of fields){$(audio).value=values[group].audio;$(sub).value=values[group].subtitle}}
 const loaded=fetch('/api/preferences').then(r=>{if(!r.ok)throw Error();return r.json()}).then(data=>{values=data;paint()}).catch(()=>{$('preferencesMessage').textContent='No se pudieron cargar las preferencias guardadas. Puedes volver a abrir Configuración.'});
 $('profileSettings').onclick=async()=>{await loaded;paint();$('preferencesDialog').showModal()};$('preferencesClose').onclick=()=>$('preferencesDialog').close();
 $('preferencesSave').onclick=async()=>{const button=$('preferencesSave');button.disabled=true;const next={};for(const [group,audio,sub] of fields)next[group]={audio:$(audio).value,subtitle:$(sub).value};try{const response=await fetch('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});if(!response.ok)throw Error();values=await response.json();$('preferencesMessage').textContent='Preferencias guardadas. Se aplican al abrir el siguiente contenido y al preparar descargas.';notify('Preferencias de idioma guardadas')}catch{$('preferencesMessage').textContent='No se pudieron guardar las preferencias. Inténtalo de nuevo.'}finally{button.disabled=false}};
 return {choose,group,canonical,ready:loaded};
})();
