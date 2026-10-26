"""Loopback-only player using this installation's own authorized session."""
from pathlib import Path
import os,sys,json,time,threading,collections,hashlib,re,urllib.parse,argparse,webbrowser
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
APP=Path(__file__).resolve().parent;ROOT=Path(os.environ.get('XUPERPC_DATA_ROOT',str(APP.parents[1]))).resolve()
os.chdir(ROOT)
if not os.environ.get('XUPERPC_PORTABLE_ROOT'):sys.path.insert(0,str(ROOT/'work'))
from types import SimpleNamespace
from catalog import load_catalog
from portal import PortalService
from vod import VodService
from tv import TvService
from favorites import Favorites
from progress import Progress
from downloads import DownloadService,DownloadBusy

lock=threading.Lock();resources=collections.OrderedDict();cache=collections.OrderedDict()
portal=PortalService(ROOT)
vod=VodService(ROOT,portal)
downloads=DownloadService(ROOT,portal)
tv=TvService(ROOT,portal)
favorites=Favorites(ROOT,portal,tv)
progress=Progress(ROOT)
transport=SimpleNamespace(url=tv.original['url'],origin=urllib.parse.urlsplit(tv.original['url']),config=tv.original)
catalog,sources=load_catalog(ROOT,transport)
default_id=next((c['id'] for c in catalog if c['kind']=='tv' and c['name']=='AMC HD'),None)
stats={'playlist_requests':0,'segment_requests':0,'segment_bytes':0,'last_error':None,'client_metrics':None,'started_unix':time.time()}
def resource(url,owner):
 parsed=urllib.parse.urlsplit(url)
 if (parsed.scheme,parsed.hostname,parsed.port)!=(transport.origin.scheme,transport.origin.hostname,transport.origin.port):raise ValueError('Unexpected stream origin')
 key=hashlib.sha256((owner+':'+url).encode()).hexdigest()[:24]
 with lock:
  resources[key]=(url,owner)
  while len(resources)>2048:resources.popitem(last=False)
 return '/segment/'+key+'.ts'

def playlist(owner=default_id,url=None):
 if owner is None:
  rows=tv.catalog_items()
  owner=next((c['id'] for c in rows if c['name']=='AMC HD'),rows[0]['id'] if rows else None)
  if owner is None:raise ValueError('No channels available')
 url=url or tv.current(owner)[2]
 result=tv.fetch(owner,url,limit=1024*1024)
 if result['status']!=200 or not result['body'].startswith(b'#EXTM3U'):raise RuntimeError('HLS service returned '+str(result['status']))
 lines=[]
 for line in result['body'].decode('utf8').splitlines():
  if line.startswith('#EXT-SEGMENT:'):continue
  if line and not line.startswith('#'):line=resource(urllib.parse.urljoin(url,line.strip()),owner)
  elif 'URI="' in line:
   line=re.sub(r'URI="([^"]+)"',lambda m:'URI="'+resource(urllib.parse.urljoin(url,m.group(1)),owner)+'"',line)
  lines.append(line)
 with lock:stats['playlist_requests']+=1;stats['last_error']=None
 return ('\n'.join(lines)+'\n').encode()

def segment(key):
 with lock:
  if key in cache:cache.move_to_end(key);return cache[key],'application/octet-stream'
  entry=resources.get(key)
 if not entry:raise FileNotFoundError('Unknown segment')
 url,owner=entry
 if urllib.parse.urlsplit(url).path.endswith('.m3u8'):return playlist(owner,url),'application/vnd.apple.mpegurl'
 result=tv.fetch(owner,url,limit=16*1024*1024)
 if result['status'] not in [200,206]:raise RuntimeError('Segment service returned '+str(result['status']))
 data=result['body']
 if not data or len(data)>=16*1024*1024:raise RuntimeError('Unexpected segment length')
 with lock:
  cache[key]=data
  while sum(map(len,cache.values()))>32*1024*1024:cache.popitem(last=False)
  stats['segment_requests']+=1;stats['segment_bytes']+=len(data);stats['last_error']=None
 return data,'application/octet-stream'

class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def handle(self):
  try:super().handle()
  except ConnectionError:self.close_connection=True
 def log_message(self,*args):pass
 def valid_host(self):
  return self.headers.get('Host') in ['127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)]
 def send(self,status,body=b'',content_type='application/json'):
  try:
   self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
   self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.end_headers();self.wfile.write(body)
  except ConnectionError:self.close_connection=True
 def do_GET(self):
  if not self.valid_host():return self.send(403)
  path=urllib.parse.urlsplit(self.path).path
  try:
   if path=='/':return self.send(200,(APP/'index.html').read_bytes(),'text/html; charset=utf-8')
   if path=='/api/launcher/status':return self.send(200,json.dumps({'application':'XuperPC','pid':os.getpid(),'instance':getattr(self.server,'launcher_id',None)}).encode())
   if path in ('/app.css','/player.js','/library.js','/downloads.js'):
    return self.send(200,(APP/path[1:]).read_bytes(),'text/css; charset=utf-8' if path.endswith('.css') else 'application/javascript; charset=utf-8')
   if path=='/api/downloads':return self.send(200,json.dumps(downloads.listing(),ensure_ascii=False).encode('utf8'))
   m=re.fullmatch(r'/api/downloads/([a-f0-9]{32})(/(file|subtitle))?',path)
   if m:
    try:
     if m[3]:return self.send_export(downloads.file(m[1],m[3]=='subtitle'))
     return self.send(200,json.dumps(downloads.status(m[1]),ensure_ascii=False).encode('utf8'))
    except KeyError:return self.send(404)
    except ValueError:return self.send(409)
   if path=='/api/favorites':return self.send(200,json.dumps(favorites.list(),ensure_ascii=False).encode('utf8'))
   if path.startswith('/api/progress/'):
    try:return self.send(200,json.dumps(progress.get(path.rsplit('/',1)[-1])).encode())
    except ValueError:return self.send(400)
   if path=='/prueba-vod':return self.send(200,(APP/'vod-test.html').read_bytes(),'text/html; charset=utf-8')
   sample=re.fullmatch(r'/vod-hevc-hls/(index\.m3u8|init\.mp4|segment\d{3}\.m4s)',path)
   if sample:
    file=ROOT/'outputs/windows-hls-player/pruebas/vod-hevc-hls'/sample[1]
    if not file.exists():return self.send(404)
    return self.send(200,file.read_bytes(),'application/vnd.apple.mpegurl' if file.suffix=='.m3u8' else 'video/mp4')
   if path in ['/prueba-vod.mp4','/prueba-hevc.mp4']:
    file=ROOT/'outputs/windows-hls-player/pruebas'/('vod-muestra.mp4' if path=='/prueba-vod.mp4' else 'vod-hevc.mp4')
    if not file.exists():return self.send(404)
    data=file.read_bytes();size=len(data);header=self.headers.get('Range')
    if not header:return self.send(200,data,'video/mp4')
    match=re.fullmatch(r'bytes=(\d+)-(\d*)',header)
    if not match:return self.send(416)
    start=int(match[1]);end=min(size-1,int(match[2]) if match[2] else size-1)
    if start>end:return self.send(416)
    self.send_response(206);self.send_header('Content-Type','video/mp4');self.send_header('Content-Length',str(end-start+1));self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.end_headers()
    try:self.wfile.write(data[start:end+1])
    except (BrokenPipeError,ConnectionResetError):pass
    return
   if path=='/vendor/hls.min.js':return self.send(200,(APP/'vendor/hls.min.js').read_bytes(),'application/javascript')
   if path=='/api/status':
    with lock:out=dict(stats)
    tv_state=tv.status()
    out.update({'expires_unix':tv_state['expires_unix'],'remaining_seconds':tv_state['remaining_seconds'],'uses_adb':False,'tv':tv_state})
    out['portal']=portal.status()
    out['vod']=vod.status()
    return self.send(200,json.dumps(out).encode())
   if path=='/api/vod/featured':return self.send(200,json.dumps(portal.featured(),ensure_ascii=False).encode('utf8'))
   if path=='/api/vod/categories':
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
    kind=query.get('kind',['movies'])[0]
    if kind not in ('movies','series','anime'):return self.send(400)
    return self.send(200,json.dumps(portal.categories(kind),ensure_ascii=False).encode('utf8'))
   if path=='/api/vod/home':
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
    kind=query.get('kind',['movies'])[0]
    if kind not in ('movies','series','anime'):return self.send(400)
    return self.send(200,json.dumps(portal.home(kind),ensure_ascii=False).encode('utf8'))
   if path=='/api/vod/catalog':
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
    kind=query.get('kind',['movies'])[0]
    page=int(query.get('page',['1'])[0])
    category=query.get('category',[None])[0]
    try:return self.send(200,json.dumps(portal.page(kind,page,category=category),ensure_ascii=False).encode('utf8'))
    except ValueError:return self.send(400)
   if path=='/api/vod/search':
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
    try:
     term=query.get('q',[''])[0];page=int(query.get('page',['1'])[0])
     if not 2<=len(term.strip())<=120 or not 1<=page<=2000:return self.send(400)
    except ValueError:return self.send(400)
    return self.send(200,json.dumps(portal.search(term,page),ensure_ascii=False).encode('utf8'))
   m=re.fullmatch(r'/api/vod/recommendations/([a-f0-9]{20})',path)
   if m:
    try:return self.send(200,json.dumps(portal.recommendations(m[1]),ensure_ascii=False).encode('utf8'))
    except KeyError:return self.send(404)
   m=re.fullmatch(r'/api/vod/seasons/([a-f0-9]{20})',path)
   if m:
    try:return self.send(200,json.dumps(portal.seasons(m[1]),ensure_ascii=False).encode('utf8'))
    except (KeyError,ValueError):return self.send(404)
   m=re.fullmatch(r'/api/vod/detail/([a-f0-9]{20})',path)
   if m:return self.send(200,json.dumps(portal.detail(m[1]),ensure_ascii=False).encode('utf8'))
   m=re.fullmatch(r'/vod/([a-f0-9]{24})/compat/(?:audio/(\d+)/)?index\.m3u8',path)
   if m:return self.send(200,vod.compatible_playlist(m[1],int(m[2]) if m[2] else None),'application/vnd.apple.mpegurl')
   m=re.fullmatch(r'/vod/([a-f0-9]{24})/compat/(?:audio/(\d+)/)?segment/(\d+)\.ts',path)
   if m:return self.send(200,vod.compatible_segment(m[1],int(m[3]),int(m[2]) if m[2] else None),'video/mp2t')
   m=re.fullmatch(r'/vod/([a-f0-9]{24})/index\.m3u8',path)
   if m:return self.send(200,vod.playlist(m[1]),'application/vnd.apple.mpegurl')
   m=re.fullmatch(r'/vod/([a-f0-9]{24})/audio/(\d+)/index\.m3u8',path)
   if m:return self.send(200,vod.playlist(m[1],int(m[2])),'application/vnd.apple.mpegurl')
   m=re.fullmatch(r'/vod/([a-f0-9]{24})/audio/(\d+)/segment/(\d+)\.ts',path)
   if m:return self.send(200,vod.segment(m[1],int(m[3]),int(m[2])),'video/mp2t')
   m=re.fullmatch(r'/vod/([a-f0-9]{24})/subtitles/(\d+)\.vtt',path)
   if m:return self.send(200,vod.subtitle(m[1],int(m[2])),'text/vtt; charset=utf-8')
   m=re.fullmatch(r'/vod/([a-f0-9]{24})/segment/(\d+)\.ts',path)
   if m:return self.send(200,vod.segment(m[1],int(m[2])),'video/mp2t')
   if path=='/api/catalog':
    channels=tv.catalog_items();selected=default_id or next((c['id'] for c in channels if c['name']=='AMC HD'),channels[0]['id'] if channels else None)
    return self.send(200,json.dumps({'items':channels+[c for c in catalog if c['kind']!='tv'],'default_id':selected,'vod_note':'Películas y series del portal. Selecciona un título y pulsa Reproducir.'},ensure_ascii=False).encode('utf-8'))
   if path=='/stream.m3u8':return self.send(200,playlist(),'application/vnd.apple.mpegurl')
   m=re.fullmatch(r'/stream/([a-f0-9]{20})\.m3u8',path)
   if m:
    if m.group(1) not in tv.channels:return self.send(404)
    return self.send(200,playlist(m.group(1)),'application/vnd.apple.mpegurl')
   m=re.fullmatch(r'/segment/([a-f0-9]{24})\.ts',path)
   if m:
    data,mime=segment(m.group(1));return self.send(200,data,mime)
   return self.send(404)
  except Exception as ex:
   with lock:stats['last_error']=str(ex)
   if os.environ.get('XUPERPC_PORTABLE_ROOT'):
    import traceback
    (ROOT/'work/portable-request.private.log').write_text(traceback.format_exc(),encoding='utf8')
   return self.send(502,json.dumps({'error':'No se pudo obtener el flujo. Revisa la sesión y vuelve a intentar.'}).encode())
 def send_export(self,path):
  size=path.stat().st_size;start=0;end=size-1;partial=False
  value=self.headers.get('Range')
  if value:
   match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
   if not match or not any(match.groups()):return self.send(416)
   if match[1]:start=int(match[1]);end=min(end,int(match[2])) if match[2] else end
   else:start=max(0,size-int(match[2]))
   if start>end or start>=size:
    self.send_response(416);self.send_header('Content-Range','bytes */'+str(size));self.send_header('Content-Length','0');self.end_headers();return
   partial=True
  try:
   self.send_response(206 if partial else 200);self.send_header('Content-Type','video/mp4' if path.suffix=='.mp4' else 'application/x-subrip; charset=utf-8')
   self.send_header('Content-Disposition',"attachment; filename=download"+path.suffix+"; filename*=UTF-8''"+urllib.parse.quote(path.name,safe=''))
   self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(end-start+1))
   if partial:self.send_header('Content-Range','bytes '+str(start)+'-'+str(end)+'/'+str(size))
   self.end_headers()
   with path.open('rb') as source:
    source.seek(start);remaining=end-start+1
    while remaining:
     chunk=source.read(min(1024*1024,remaining))
     if not chunk:break
     self.wfile.write(chunk);remaining-=len(chunk)
  except ConnectionError:self.close_connection=True
 def do_POST(self):
  if not self.valid_host() or self.path not in ['/api/client-metrics','/api/vod/play','/api/vod/buffer/stop','/api/favorites','/api/progress','/api/downloads/prepare','/api/downloads/start','/api/downloads/cancel','/api/downloads/open-folder','/api/downloads/set-folder','/api/downloads/choose-folder','/api/downloads/forget','/api/downloads/retry']:return self.send(404)
  origin=self.headers.get('Origin')
  if origin and origin!='http://'+self.headers.get('Host'):return self.send(403)
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=2048:return self.send(400)
   data=json.loads(self.rfile.read(n))
   if not isinstance(data,dict):return self.send(400)
   allowed=['currentTime','readyState','width','height','frames','droppedFrames','paused','error','bufferStart','bufferEnd','liveSync','lastFragSN','lastFragStart','lastFragEnd','recoveries','hlsFatal','compatibilityMode','bufferAhead','seeking','isWaiting','waitingCount','lastWaitingUnix','lastWaitingTime','lastWaitingAhead','lastWaitingDuration','hlsErrorUnix','hlsErrorCount']
   if self.path.startswith('/api/downloads/'):
    try:
     if self.path=='/api/downloads/prepare':result=downloads.prepare(data.get('id'),data.get('episode'),data.get('poster_url'))
     elif self.path=='/api/downloads/open-folder':downloads.open_folder(data.get('job'));result={'opened':True}
     elif self.path=='/api/downloads/set-folder':result=downloads.set_folder(data.get('folder'))
     elif self.path=='/api/downloads/choose-folder':result=downloads.choose_folder()
     else:
      if not re.fullmatch(r'[a-f0-9]{32}',str(data.get('job',''))):return self.send(400)
      if self.path.endswith('/cancel'):result=downloads.cancel(data['job'])
      elif self.path.endswith('/forget'):result=downloads.forget(data['job'])
      elif self.path.endswith('/retry'):result=downloads.retry(data['job'])
      else:result=downloads.start(data['job'],data.get('audio',0),data.get('subtitle',-1))
     return self.send(200,json.dumps(result,ensure_ascii=False).encode('utf8'))
    except DownloadBusy as error:return self.send(409,json.dumps({'error':str(error),'active_id':error.identifier}).encode('utf8'))
    except KeyError:return self.send(404)
    except (ValueError,RuntimeError) as error:return self.send(400,json.dumps({'error':str(error)}).encode('utf8'))
   if self.path=='/api/vod/buffer/stop':
    if not re.fullmatch(r'[a-f0-9]{24}',str(data.get('key',''))):return self.send(400)
    vod.stop_buffer(data['key']);return self.send(200,b'{"stopped":true}')
   if self.path=='/api/progress':
    try:return self.send(200,json.dumps(progress.save(data)).encode())
    except (ValueError,TypeError):return self.send(400)
   if self.path=='/api/favorites':
    if not re.fullmatch(r'[a-f0-9]{20}',str(data.get('id',''))) or data.get('action') not in ('add','remove'):return self.send(400)
    try:return self.send(200,json.dumps(favorites.change(data['id'],data['action']),ensure_ascii=False).encode('utf8'))
    except ValueError:return self.send(400,json.dumps({'error':'No se pudo guardar este favorito.'}).encode())
   if self.path=='/api/vod/play':
    if not re.fullmatch(r'[a-f0-9]{20}',str(data.get('id',''))):return self.send(400)
    try:return self.send(200,json.dumps(vod.start(data['id'],data.get('episode'))).encode())
    except Exception as ex:
     import traceback
     with vod.lock:vod.state['last_error']=type(ex).__name__
     (ROOT/'work/vod-prepare.private.log').write_text(traceback.format_exc(),encoding='utf8')
     return self.send(502,json.dumps({'error':'No se pudo preparar este video. Revisa la sesión e intenta de nuevo.'}).encode())
   safe={k:v for k,v in data.items() if k in allowed and isinstance(v,(int,float,bool,type(None)))}
   if isinstance(data.get('hlsError'),str) and re.fullmatch(r'[a-zA-Z0-9_]{1,80}',data['hlsError']):safe['hlsError']=data['hlsError']
   if isinstance(data.get('hlsErrorType'),str) and re.fullmatch(r'[a-zA-Z0-9_]{1,40}',data['hlsErrorType']):safe['hlsErrorType']=data['hlsErrorType']
   browser=data.get('browser')
   if browser not in ('edge','chrome','firefox','safari','other'):browser='other'
   safe['browser']=browser
   with lock:
    stats['client_metrics']=safe
    stats.setdefault('client_metrics_by_browser',{})[browser]=safe
   (ROOT/('work/web-player-metrics-'+browser+'.json')).write_text(json.dumps(safe,indent=2),encoding='utf8')
   (ROOT/'work/web-player-metrics.json').write_text(json.dumps(safe,indent=2),encoding='utf8')
   return self.send(204)
  except (ValueError,OSError):return self.send(400)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--open',action='store_true');args=parser.parse_args()
 server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);url='http://127.0.0.1:'+str(server.server_port)+'/'
 (ROOT/'work/web-player-server.json').write_text(json.dumps({'url':url,'pid':os.getpid(),'started_unix':time.time()},indent=2))
 print('Reproductor local: '+url,flush=True)
 if args.open:webbrowser.open(url)
 portal.start()
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:portal.stop.set();downloads.close();vod.buffer.close();server.server_close()
