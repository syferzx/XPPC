"""Expose cached catalog metadata; keep playback licenses on the server."""
import json,hashlib,urllib.parse
from pathlib import Path

def load_catalog(root,transport):
 items={};sources={}
 def uid(kind,code):return hashlib.sha256((kind+':'+str(code)).encode()).hexdigest()[:20]
 live_file=root/'work/channel-metadata-decoded.json'
 live=json.loads(live_file.read_text(encoding='utf-8'))['data']['channelList'] if live_file.exists() else []
 for c in live:
  key=uid('tv',c['channelCode']);variants=[]
  for a in c.get('liveAddressList',[]):
   license=a.get('license','');media=urllib.parse.parse_qs(license).get('media_code',[''])[0]
   if str(a.get('cdnType'))!='1' or not media:continue
   path='/live/'+urllib.parse.quote(media,safe='')+'.m3u8'
   variants.append({'url':urllib.parse.urlunsplit((transport.origin.scheme,transport.origin.netloc,path,'','')),'license':license,'quality':str(a.get('quality',''))})
  items[key]={'id':key,'name':c.get('name','Canal'),'kind':'tv','number':str(c.get('channelNumber','')),'codec':c.get('supportVideoType') or '', 'groups':[], 'playable':bool(variants)}
  if variants:
   sources[key]=variants[0]
   if sources[key]['url']==transport.url:
    sources[key]['license']=transport.config['headers']['content-license']
 for section in ['movies','series']:
  saved=root/('work/vod-'+section+'-decoded.json')
  if not saved.exists():continue
  data=json.loads(saved.read_text(encoding='utf-8'))
  for row in data.get('recommendList',[]):
   for a in row.get('assetList',[]):
    kind='series' if a.get('programType')=='teleplay' else 'movies'
    key=uid(kind,a['contentId'])
    if key in items:
     if row['name'] not in items[key]['groups']:items[key]['groups'].append(row['name'])
     continue
    items[key]={'id':key,'name':a.get('name','Sin título'),'kind':kind,'groups':[row['name']],'description':a.get('description',''),'genres':a.get('tags',''),'cast':a.get('actorDisplay',''),'score':a.get('score'),'episodes':a.get('volumnCount',0),'duration':a.get('duration',''),'programType':a.get('programType',''),'playable':False}
 return list(items.values()),sources
