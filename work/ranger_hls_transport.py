"""Windows transport for this user's captured, still-valid playback session.

Uses Ranger's original sign_o3 routine offline; does not refresh portal tokens.
Authorization stays on its captured origin; licenses come from the local catalog.
"""
from pathlib import Path
import json,time,urllib.parse,http.client,threading
from ranger_native_runtime import Runtime

# The provider's media backend accepts the native spelling but returns HTTP410
# for identical grants sent with lower-case field names. Preserve SDK framing.
NATIVE_HEADER_NAMES={name.lower():name for name in [
 'Host','Connection','App','App-Version','Content-Auth','Content-License',
 'Pragma','Ranger-Id','User-Agent','X-Buffer']}

class RangerHlsTransport:
 def __init__(self,config_path='work/captured-hls-request.private.json'):
  self.config=dict(config_path) if isinstance(config_path,dict) else json.loads(Path(config_path).read_text())
  self.url=self.config['url'];self.origin=urllib.parse.urlsplit(self.url)
  self.headers=[(k,v) for k,v in self.config['headers_original'] if k.lower()!='range'];auth=self.config['headers'].get('content-auth')
  parsed=urllib.parse.urlsplit(self.url);query_params=urllib.parse.parse_qs(parsed.query)
  self.query_auth=not auth and ('sign2_method' in query_params or self.config.get('authorization_mode')=='query_sign_o3')
  target=urllib.parse.urlunsplit(('','',parsed.path,parsed.query,''))
  self.base=target if self.query_auth else auth
  if self.base:self.base=self.base.split('&sign2_method=')[0]
  params=urllib.parse.parse_qs(auth) if auth else query_params if self.query_auth else urllib.parse.parse_qs(self.config['headers']['content-license']);self.instance=int(params.get('instance',['0'])[0]);self.expires=int(params['expired'][0])
  self.lock=threading.Lock();self.calls=0
  if self.base:self.reset_signer()
 def reset_signer(self):
  self.r=Runtime();self.input=self.r.alloc(24);self.output=self.r.alloc(24);self.r.assign(self.input,self.base);self.calls=0
 def signed_value(self,base=None):
  if time.time()>=self.expires:raise RuntimeError('Captured authorization expired; renewal is required')
  with self.lock:
   if self.calls>=64:self.reset_signer()
   self.r.assign(self.input,self.base if base is None else base)
   self.r.call(0x6752e0,self.input,self.instance,time.time_ns(),result=self.output,count=3000000)
   auth=self.r.string(self.output).decode('ascii');self.calls+=1
  return auth
 def signed_headers(self,license=None):
  if time.time()>=self.expires:raise RuntimeError('Captured authorization expired; renewal is required')
  auth=self.signed_value() if self.base and not self.query_auth else None
  return [(k,auth if k.lower()=='content-auth' else license if k.lower()=='content-license' and license is not None else v) for k,v in self.headers]
 def fetch(self,url,limit=262144,range_header=False,license=None,byte_range=None):
  u=urllib.parse.urlsplit(url)
  if (u.scheme,u.hostname,u.port)!=(self.origin.scheme,self.origin.hostname,self.origin.port):raise ValueError('Cannot forward captured authorization to another origin')
  c=http.client.HTTPConnection(u.hostname,u.port or 80,timeout=10)
  try:
   target=urllib.parse.urlunsplit(('','',u.path,u.query,''))
   if self.query_auth:target=self.signed_value(target.split('&sign2_method=')[0])
   c.putrequest('GET',target,skip_host=True,skip_accept_encoding=True)
   for k,v in self.signed_headers(license):c.putheader(NATIVE_HEADER_NAMES.get(k.lower(),k),v)
   if byte_range:c.putheader('Range',byte_range)
   elif range_header:c.putheader('Range','bytes=0-'+str(limit-1))
   c.endheaders();response=c.getresponse();body=response.read(limit)
   return {'status':response.status,'headers':dict(response.getheaders()),'body':body}
  finally:c.close()

if __name__=='__main__':
 t=RangerHlsTransport();out={'transport':'direct Windows HTTP; original ARM signing under Unicorn','uses_adb':False,'playlist':{},'segments':[]}
 try:
  response=t.fetch(t.url);body=response.pop('body');Path('work/windows-fresh-hls-playlist.body').write_bytes(body)
  text=body.decode('utf8','replace');out['playlist']={'status':response['status'],'bytes':len(body),'hls':text.startswith('#EXTM3U')}
  uris=[l.strip() for l in text.splitlines() if l.strip() and not l.startswith('#')]
  private=[]
  for i,uri in enumerate(uris[-2:]):
   url=urllib.parse.urljoin(t.url,uri);segment=t.fetch(url,range_header=True);data=segment.pop('body');file=Path('work/windows-fresh-hls-segment-'+str(i)+'.bin');file.write_bytes(data)
   sync=next((off for off in range(min(188,len(data))) if all(off+k*188<len(data) and data[off+k*188]==0x47 for k in range(5))),None)
   out['segments'].append({'status':segment['status'],'bytes':len(data),'file':str(file),'mpegts_sync_offset':sync,'prefix_hex':data[:16].hex(),'extension':Path(urllib.parse.urlsplit(url).path).suffix})
   private.append({'url':url,'headers':segment['headers']})
  Path('work/windows-fresh-hls-segments.private.json').write_text(json.dumps(private,indent=2),encoding='utf8')
 except Exception as ex:out['error']=type(ex).__name__+': '+str(ex)
 Path('work/windows-fresh-hls-result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
