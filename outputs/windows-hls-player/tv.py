"""TV source renewal at explicitly authorized original SLB/media destinations."""
import hashlib,http.client,json,threading,time,urllib.parse
from pathlib import Path
from ranger_hls_transport import RangerHlsTransport
from ranger_live_v9 import LiveV9Protocol
from ranger_slb_http import SlbHttpClient
from artwork import artwork
from access_profile import tv_template,tv_route
from channel_groups import channel_groups

SLB_HOST='eijbs.gn5h3hxar2k.com'
SLB_IP='206.253.89.122'
MEDIA_ORIGIN=('http','23.227.144.242',44822)

def make_source(original,response,tag,media_origin=MEDIA_ORIGIN):
    servers=[s for s in response.get('servers',[]) if urllib.parse.parse_qs(urllib.parse.urlsplit(s.get('media_url','')).query).get('tag')==[tag]]
    if not servers:raise ValueError('TV source not authorized for this tag')
    parsed=urllib.parse.urlsplit(servers[0]['media_url'])
    if (parsed.scheme,parsed.hostname,parsed.port)!=media_origin or parsed.path!='/live/' or parsed.username or parsed.password or parsed.fragment:raise ValueError('TV source changed from authorized origin')
    config=dict(original);config['headers']=dict(original['headers'])
    auth=parsed.path+'?'+parsed.query;config['headers']['content-auth']=auth
    config['headers_original']=[(k,auth if k.lower()=='content-auth' else v) for k,v in original['headers_original']]
    return config

class TvService:
    def __init__(self,root,portal,clock=time.time,transport_factory=RangerHlsTransport):
        self.root=Path(root);self.portal=portal;self.clock=clock;self.factory=transport_factory;self.lock=threading.RLock()
        self.original=tv_template(self.root)
        self.slb_host,self.slb_ip,self.media_origin=tv_route(self.root)
        u=urllib.parse.urlsplit(self.original['url'])
        if (u.scheme,u.hostname,u.port)!=self.media_origin:raise ValueError('Unexpected original TV source')
        self.transports={};self.channels={};self.catalog_updated=0;self.protocol=None
        self.state={'source_lookups':0,'source_renewals':0,'authorization_retries':0,'network_retries':0,'last_error':None,'renewal_enabled':True}
        cached=self.root/'work/channel-metadata-decoded.json'
        if cached.exists():self.install_channels(json.loads(cached.read_text(encoding='utf8'))['data']['channelList'])
    def install_channels(self,rows):
        self.channels={hashlib.sha256(('tv:'+str(c['channelCode'])).encode()).hexdigest()[:20]:c for c in rows}
    def refresh_catalog(self):
        with self.portal.lock:
            data=self.portal.request('/api/portalCore/v6/getLiveData',{'columnId':76182,'dataVersion':'','expireTimeStr':'','pageSize':3000,'pageNum':1})
        rows=data.get('channelList',[])
        if not rows or len(rows)>3000:raise ValueError('Invalid TV catalog')
        # The provider serves +18 as a separate catalog, not as a visibility
        # flag in ChannelList. Query it with the same account and permissions.
        try:
            with self.portal.lock:
                adult=self.portal.request('/api/portalCore/v6/getLiveData',{'columnId':76208,'dataVersion':'','expireTimeStr':'','pageSize':3000,'pageNum':1})
            adult_rows=adult.get('channelList',[])
            if not isinstance(adult_rows,list) or len(adult_rows)>3000:raise ValueError('Invalid adult TV catalog')
            merged={str(c['channelCode']):c for c in rows}
            for channel in adult_rows:
                merged[str(channel['channelCode'])]={**channel,'categoryName':'Adultos +18'}
            rows=list(merged.values())
            self.state.update(adult_channel_count=len(adult_rows),adult_catalog_error=None)
        except Exception as error:
            # An unavailable/denied extra category must not hide general TV.
            self.state.update(adult_channel_count=0,adult_catalog_error=type(error).__name__)
        data={**data,'channelList':rows,'channelListTotalSize':len(rows)}
        # Keep this installation's own catalog available across restarts when
        # the portal is slow; licenses are still checked before playback.
        cached=self.root/'work/channel-metadata-decoded.json'
        temporary=cached.with_suffix('.tmp')
        temporary.write_text(json.dumps({'data':data},ensure_ascii=False),encoding='utf8')
        temporary.replace(cached)
        self.install_channels(rows);self.catalog_updated=self.clock()
    def status(self):
        with self.lock:
            remaining=min([int(t.expires-self.clock()) for t in self.transports.values()],default=0)
            return {**self.state,'remaining_seconds':max(0,remaining),'expires_unix':max([t.expires for t in self.transports.values()],default=0),'channel_count':len(self.channels),'last_catalog_unix':self.catalog_updated or None}
    def catalog_items(self):
        with self.lock:
            if self.clock()-self.catalog_updated>=900:
                try:self.refresh_catalog()
                except Exception as ex:self.state['last_error']=type(ex).__name__
            return [{'id':key,'name':c.get('name','Canal'),'kind':'tv','number':str(c.get('channelNumber','')),'codec':c.get('supportVideoType') or '', 'groups':channel_groups(c),'playable':any(str(a.get('cdnType'))=='1' for a in c.get('liveAddressList',[])),**artwork(c)} for key,c in self.channels.items()]
    def selection(self,owner):
        channel=self.channels[owner]
        variants=[a for a in channel.get('liveAddressList',[]) if str(a.get('cdnType'))=='1' and a.get('license')]
        if not variants:raise ValueError('Channel has no supported TV source')
        license=variants[0];params=urllib.parse.parse_qs(license['license'])
        if int(params['expired'][0])<=self.clock():raise ValueError('Channel license expired')
        media=params['media_code'][0]
        return channel,license,'http://'+self.media_origin[1]+':'+str(self.media_origin[2])+'/live/'+urllib.parse.quote(media,safe='')+'.m3u8'
    def renew(self,owner,tag):
        channel,license,_=self.selection(owner)
        session=json.loads((self.root/'work/portal-native/active-data.private.json').read_text(encoding='utf8'))
        with self.portal.lock:
            config=self.portal.request('/api/portalCore/v15/getSlbInfo',{'hasPay':session.get('hasPay','0'),'userIdentity':session.get('userIdentity',''),'type':'merge','appVer':'43404','lang':'es','encMediaSupported':1,'liveCodeList':[channel['channelCode']],'appParams':'','reserve1':'','pipFlag':'0'})
        service=next(s for s in config['cdn_list'] if s['tag']=='live' and str(s['cdn_type'])=='1')
        address=service['main_addr'];address=address if '://' in address else 'https://'+address
        parsed=urllib.parse.urlsplit(address)
        if parsed.scheme!='https' or parsed.hostname!=self.slb_host or parsed.port not in (None,443):raise ValueError('TV SLB destination changed')
        grant=next(a['url'] for a in service['url_list'] if a['tag']==tag)
        if int(urllib.parse.parse_qs(grant)['expired'][0])<=self.clock()+90:raise ValueError('Portal TV grant is near expiry')
        headers={k:v for k,v in self.original['headers'].items() if k in ['app','app-version','ranger-id']};headers['Content-License']=license['license']
        if self.protocol is None:self.protocol=LiveV9Protocol()
        value=SlbHttpClient(self.protocol,lambda host:[self.slb_ip] if host==self.slb_host else [],extra_headers=headers,version=9).request(address,'live',[{'auth':grant,'license':license['license']}])
        candidate=self.factory(make_source(self.original,value,tag,self.media_origin))
        if candidate.expires<=self.clock()+90:raise ValueError('TV source is near expiry')
        self.state['source_lookups']+=1
        if tag in self.transports:self.state['source_renewals']+=1
        self.transports[tag]=candidate
        return candidate
    def current(self,owner,force=False):
        with self.lock:
            if self.clock()-self.catalog_updated>=900:self.refresh_catalog()
            _,license,url=self.selection(owner);tag=license['tag'];transport=self.transports.get(tag)
            if force or transport is None or transport.expires<=self.clock()+90:transport=self.renew(owner,tag)
            return transport,license['license'],url
    def fetch(self,owner,url=None,**kwargs):
        with self.lock:
            transport,license,playlist=self.current(owner)
            def read(t,l):
                for attempt in range(3):
                    try:return t.fetch(url or playlist,license=l,**kwargs)
                    except (TimeoutError,ConnectionError,http.client.RemoteDisconnected):
                        if attempt==2:raise
                        self.state['network_retries']+=1
            result=read(transport,license)
            if result['status'] in (401,403,409,410):
                self.state['authorization_retries']+=1
                transport,license,playlist=self.current(owner,force=True);result=read(transport,license)
            self.state['last_error']=None if result['status'] in (200,206) else 'HTTP '+str(result['status'])
            return result
