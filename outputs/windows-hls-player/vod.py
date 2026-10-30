"""Loopback VOD relay with ordinary portal grants and automatic source renewal."""
import collections,json,re,threading,time,urllib.parse,uuid,http.client
from pathlib import Path
from probe_fresh_vod_slb import codec
from ranger_hls_transport import RangerHlsTransport
from ranger_vod_renewal import VerifiedVodResolver,RenewingVodSource,HOST,IP
from ranger_vod_index import parse_idxg,hls_playlist
from media_tracks import audio_tracks,select_audio,subtitle_tracks,fetch_subtitle,compatible_segment
from access_profile import media_headers,vod_route
from segment_buffer import SegmentBuffer

class VodService:
    def __init__(self,root,portal):
        self.root=Path(root);self.portal=portal;self.lock=threading.RLock()
        self.sessions=collections.OrderedDict();self.cache=collections.OrderedDict()
        self.buffer=SegmentBuffer();self.generation=0
        self.state={'source_lookups':0,'source_renewals':0,'segment_requests':0,'segment_bytes':0,'last_error':None}
    def status(self):
        with self.lock:state=dict(self.state)
        state['buffer']=self.buffer.status()
        return state
    def stop_buffer(self,key=None):
        with self.lock:
            if key is not None:
                if key in self.sessions:self.sessions[key]['stopped']=True
            else:
                for lease in self.sessions.values():lease['stopped']=True
        with self.buffer.lock:
            if key is None or self.buffer.active_key==key:self.buffer.reset()
    def start(self,item_id,episode=None):
        with self.lock:self.generation+=1;generation=self.generation
        self.stop_buffer()
        with self.portal.lock:
            kind,asset=self.portal.assets[item_id]
            detail=self.portal.title_detail(item_id)
        programs=detail.get('simpleProgramList',[])
        if not programs:raise ValueError('No programs available')
        program=programs[0] if episode is None else next(p for p in programs if str(p.get('seriesNumber'))==str(episode))
        verified_host,verified_ip=vod_route(self.root)
        if verified_ip!=IP or verified_host!=HOST:raise ValueError('Unverified VOD endpoint')
        resolver=VerifiedVodResolver(codec(),media_headers(self.root,'vod'));lease={'media_id':None,'response':None,'lock':threading.RLock()}
        def renew():
            with self.portal.lock:
                play=self.portal.request('/api/portalCore/v10/startPlayVOD',{'columnId':self.portal.columns[kind],'contentId':program['contentId'],'seriesContentId':asset['contentId'] if kind=='series' else '','type':'1','startTime':0})
                active=json.loads((self.root/'work/portal-native/active-data.private.json').read_text(encoding='utf8'))
                configuration=self.portal.request('/api/portalCore/v15/getSlbInfo',{'hasPay':active.get('hasPay','0'),'userIdentity':active.get('userIdentity',''),'type':'merge','appVer':'43404','lang':'es','encMediaSupported':1,'liveCodeList':['ba397e42-b664-11ed-8c55-768dd7bc60d3'],'appParams':'','reserve1':'','pipFlag':'0'})
            config,response=resolver.resolve({'data':play},{'data':configuration})
            media=urllib.parse.parse_qs(urllib.parse.urlsplit(config['url']).query)['media_code'][0]
            if lease['media_id'] is not None and media!=lease['media_id']:raise ValueError('Media changed; reopen this title')
            with self.lock:
                self.state['source_lookups']+=1
                if lease['media_id'] is not None:self.state['source_renewals']+=1
            lease.update(media_id=media,response=response,subtitles=subtitle_tracks(play['episodeList'][0]))
            return config
        lease['source']=RenewingVodSource(renew,RangerHlsTransport)
        transport=lease['source'].current();server=lease['response']['play_infos'][0]['servers'][0]
        u=urllib.parse.urlsplit(server['idx_url'])
        if u.hostname!=HOST or u.scheme!='http':raise ValueError('Unexpected index origin')
        index_url=urllib.parse.urlunsplit(('http',IP+':80',u.path,u.query,''))
        for attempt in range(3):
            try:
                result=transport.fetch(index_url,limit=4*1024*1024);break
            except (TimeoutError,ConnectionError,http.client.RemoteDisconnected):
                if attempt==2:raise
        if result['status']!=200:raise ValueError('Video index unavailable')
        index=parse_idxg(result['body']);lease['index']=index
        key=uuid.uuid4().hex[:24]
        with self.lock:
            if generation!=self.generation:raise ValueError('Playback replaced during preparation')
            self.sessions[key]=lease
            while len(self.sessions)>8:
                dropped,_=self.sessions.popitem(last=False)
                for entry in list(self.cache):
                    if entry[0]==dropped:del self.cache[entry]
        try:lease['audio_tracks']=audio_tracks(self.root,self.segment(key,0,prefetch=False))
        except Exception:lease['audio_tracks']=[]
        return {'url':'/vod/'+key+'/index.m3u8','duration_seconds':index['duration_ms']/1000,'width':index['width'],'height':index['height'],'episode':program.get('seriesNumber'),'renewal_enabled':True,
            'original_country':str(detail.get('originalCountry') or '')[:120],'original_language':str(detail.get('language') or '')[:40],
            'audio_tracks':lease['audio_tracks'],'subtitle_tracks':[{'index':i,'language':s['language'],'url':'/vod/'+key+'/subtitles/'+str(i)+'.vtt'} for i,s in enumerate(lease.get('subtitles',[]))]}
    def playlist(self,key,audio=None):
        with self.lock:lease=self.sessions[key]
        if audio is not None and not 0<=audio<len(lease.get('audio_tracks',[])):raise ValueError('Unknown audio track')
        return hls_playlist(lease['index'],'/vod/'+key+('/audio/'+str(audio) if audio is not None else '')+'/segment')
    def compatible_playlist(self,key,audio=None):
        with self.lock:lease=self.sessions[key]
        if audio is not None and not 0<=audio<len(lease.get('audio_tracks',[])):raise ValueError('Unknown audio track')
        prefix='/vod/'+key+'/segment'
        playlist=hls_playlist(lease['index'],prefix).decode('utf8')
        playlist=playlist.replace(prefix,'/vod/'+key+'/compat'+('/audio/'+str(audio) if audio is not None else '')+'/segment')
        # Each local encoder starts a fresh timestamp sequence and emits its own headers.
        playlist=playlist.replace('#EXTINF:','#EXT-X-DISCONTINUITY\n#EXTINF:')
        return playlist.encode('utf8')
    def compatible_segment(self,key,number,audio=None):
        with self.lock:
            lease=self.sessions[key]
            if audio is not None and not 0<=audio<len(lease.get('audio_tracks',[])):raise ValueError('Unknown audio track')
            encoder_lock=lease.setdefault('compat_lock',threading.Lock())
        cache_key=(key,number,'compat',audio)
        with encoder_lock:
            with self.lock:
                if cache_key in self.cache:self.cache.move_to_end(cache_key);return self.cache[cache_key]
            body=compatible_segment(self.root,self.segment(key,number),audio or 0)
            with self.lock:
                self.cache[cache_key]=body
                while sum(map(len,self.cache.values()))>32*1024*1024:self.cache.popitem(last=False)
            return body
    def subtitle(self,key,number):
        with self.lock:lease=self.sessions[key]
        with lease['lock']:
            tracks=lease.get('subtitles',[])
            if not 0<=number<len(tracks):raise ValueError('Unknown subtitle track')
            cache=lease.setdefault('subtitle_cache',{})
            if number not in cache:cache[number]=fetch_subtitle(tracks[number])
            return cache[number]
    def segment(self,key,number,audio=None,prefetch=True):
        if audio is not None:
            with self.lock:
                lease=self.sessions[key]
                if not 0<=audio<len(lease.get('audio_tracks',[])):raise ValueError('Unknown audio track')
                if (key,number,audio) in self.cache:return self.cache[(key,number,audio)]
            with lease['lock']:
                body=select_audio(self.root,self.segment(key,number),audio,lease['audio_tracks'])
                with self.lock:
                    self.cache[(key,number,audio)]=body
                    while sum(map(len,self.cache.values()))>32*1024*1024:self.cache.popitem(last=False)
                return body
        with self.lock:
            lease=self.sessions[key]
            if lease.get('stopped'):raise ValueError('Playback stopped')
        return self.buffer.get(key,number,lease['index']['segments'],
                               lambda n:self._download(lease,n),prefetch=prefetch)
    def _download(self,lease,number):
        # Range validation remains mandatory for foreground and read-ahead alike.
        index=lease['index'];segments=index['segments']
        if not 0<=number<len(segments):raise ValueError('Unknown segment')
        s=segments[number];size=s['length'];start=s['offset'];end=start+size-1
        if not 0<size<=16*1024*1024:raise ValueError('Invalid segment size')
        result=lease['source'].fetch(limit=size,byte_range='bytes='+str(start)+'-'+str(end))
        headers={k.lower():v for k,v in result['headers'].items()};span=headers.get('content-range','')
        expected='bytes '+str(start)+'-'+str(end)+'/'+str(index['size'])
        if result['status']!=206 or span!=expected or len(result['body'])!=size:raise ValueError('Video range rejected')
        body=result['body']
        with self.lock:
            self.state['segment_requests']+=1;self.state['segment_bytes']+=len(body);self.state['last_error']=None
        return body
