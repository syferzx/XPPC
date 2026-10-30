"""VOD renewal logic for the verified original endpoint; secrets remain server-side.

No network at import/construction. Renewal callback obtains ordinary portal grants.
"""
import json,threading,time,urllib.parse,http.client
from ranger_slb_http import SlbHttpClient
from ranger_hls_transport import RangerHlsTransport

HOST='yuwc.swzablvpm.com'
IP='66.225.197.106'

def authorized_entries(play,configuration):
    movie=play['data']['episodeList'][0]['totalMovieList'][0]['movieList'][0]
    license=next((x for x in movie['licenseList'] if x['tag']=='free'),movie['licenseList'][0])
    services=[s for s in configuration['data']['cdn_list'] if s['tag']=='vod' and str(s['cdn_type'])=='1']
    service=next(s for s in services if urllib.parse.urlsplit(s['main_addr']).hostname==HOST)
    auth=next(a['url'] for a in service['url_list'] if a['tag']==license['tag'])
    if urllib.parse.parse_qs(license['license'])['media_code'][0]!=movie['contentId']:raise ValueError('License does not match requested movie')
    if int(urllib.parse.parse_qs(auth)['expired'][0])<=time.time()+30:raise ValueError('Expired portal authorization')
    return [{'auth':auth,'license':license['license'],'media_code':movie['contentId']}]

def source_config(response,entries,media_headers):
    info=next(i for i in response['play_infos'] if i['media_code']==entries[0]['media_code'])
    if not info.get('servers'):raise ValueError('SLB did not authorize a source: '+str(info.get('code','unknown')))
    server=info['servers'][0];source=urllib.parse.urlsplit(server['media_url'])
    if (source.scheme,source.hostname,source.port) not in [('http',HOST,None),('http',HOST,80)]:raise ValueError('Source changed from verified original origin')
    headers={k.lower():v for k,v in media_headers.items() if k.lower()!='range'}
    headers.update({'host':HOST+':80','content-license':entries[0]['license']})
    source=urllib.parse.urlunsplit(('http',IP+':80',source.path,source.query,''))
    return {'url':source,'headers':headers,'headers_original':list(headers.items()),'authorization_mode':'query_sign_o3'}

class VerifiedVodResolver:
    def __init__(self,protocol,observed_headers,connection_factory=None):
        self.protocol=protocol;self.headers=dict(observed_headers);self.connection_factory=connection_factory
    def resolve(self,play,configuration):
        entries=authorized_entries(play,configuration)
        headers={k:v for k,v in self.headers.items() if k.lower() in ['app','app-version','ranger-id']}
        headers['Content-License']=entries[0]['license']
        client=SlbHttpClient(self.protocol,lambda host:[IP] if host==HOST else [],self.connection_factory,extra_headers=headers)
        for attempt in range(3):
            try:
                value=client.request('http://'+HOST,'vod',entries);break
            except (TimeoutError,ConnectionError,http.client.RemoteDisconnected):
                if attempt==2:raise
        self.last_response=value
        return source_config(value,entries,self.headers),value

class RenewingVodSource:
    """Refresh before expiry, and retry once on authorization rejection."""
    def __init__(self,renew,transport_factory,clock=time.time,margin=90):
        self.renew=renew;self.factory=transport_factory;self.clock=clock;self.margin=margin
        self.lock=threading.RLock();self.transport=None;self.renewals=0
    def current(self,force=False):
        with self.lock:
            if force or self.transport is None or self.transport.expires<=self.clock()+self.margin:
                candidate=self.factory(self.renew())
                if candidate.expires<=self.clock()+self.margin:raise ValueError('Renewed source is already near expiry')
                self.transport=candidate;self.renewals+=1
            return self.transport
    def fetch(self,**kwargs):
        transport=self.current()
        def read(source):
            for attempt in range(3):
                try:return source.fetch(source.url,**kwargs)
                except (TimeoutError,ConnectionError,http.client.RemoteDisconnected):
                    if attempt==2:raise
        # Each request owns its HTTP connection; only signing and renewal are locked.
        result=read(transport)
        if result['status'] in [401,403]:
            with self.lock:
                # Concurrent rejections of the same generation renew just once.
                if self.transport is transport:self.current(force=True)
                transport=self.current()
            result=read(transport)
        return result
