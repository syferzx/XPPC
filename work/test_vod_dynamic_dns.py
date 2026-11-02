"""Offline VOD DNS rotation, origin confinement and renewal regressions."""
import concurrent.futures,json,sys,threading,time,types,unittest,urllib.parse,tempfile
from pathlib import Path
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work'),str(ROOT/'outputs/windows-hls-player'),str(ROOT/'outputs/ranger-windows')]
from vod_dns import HOST,RESOLVERS,VodDnsResolver,parse_answer,public_ipv4
from ranger_vod_renewal import VerifiedVodResolver,RenewingVodSource,source_config

def dns(address='8.8.8.8',ttl=300):
    return {'Status':0,'Question':[{'name':HOST+'.','type':1}],
            'Answer':[{'name':HOST+'.','type':1,'TTL':ttl,'data':address}]}

def playback():
    movie={'contentId':'synthetic','licenseList':[{'tag':'free','license':'media_code=synthetic&expired=10000'}]}
    return {'data':{'episodeList':[{'totalMovieList':[{'movieList':[movie]}]}]}}

def configuration():
    return {'data':{'cdn_list':[{'tag':'vod','cdn_type':'1','main_addr':'http://'+HOST,
                               'url_list':[{'tag':'free','url':'tag=free&expired=10000'}]}]}}

def response():
    return {'play_infos':[{'media_code':'other','servers':[{'media_url':'http://other.invalid/never'}]},
                         {'media_code':'synthetic','servers':[{
                             'media_url':'http://'+HOST+'/vod/movie.ts?media_code=synthetic&expired=10000',
                             'idx_url':'http://'+HOST+'/vod/movie.idx?media_code=synthetic&expired=10000'}]}]}

class Tests(unittest.TestCase):
    def setUp(self):
        p=patch('socket.create_connection',side_effect=AssertionError('Offline test attempted networking'))
        p.start();self.addCleanup(p.stop)
    def test_cache_honors_ttl_and_force_discovers_new_ip(self):
        clock=[0];fetch=Mock(return_value=dns(ttl=60));r=VodDnsResolver(fetch,lambda:clock[0])
        self.assertEqual(r.resolve(),['8.8.8.8']);self.assertEqual(fetch.call_count,2)
        clock[0]=59;self.assertEqual(r.resolve(),['8.8.8.8']);self.assertEqual(fetch.call_count,2)
        fetch.return_value=dns('1.1.1.1',60);clock[0]=60
        self.assertEqual(r.resolve(),['1.1.1.1']);self.assertEqual(fetch.call_count,4)
        fetch.return_value=dns('9.9.9.9');self.assertEqual(r.resolve(force=True),['9.9.9.9'])
        self.assertEqual(fetch.call_count,6)
    def test_cache_does_not_outlive_short_or_long_ttls(self):
        for ttl,expected in [(0,0),(5,5),(3600,300)]:
            with self.subTest(ttl=ttl):
                r=VodDnsResolver(lambda resolver:dns(ttl=ttl),lambda:100)
                r.resolve();self.assertEqual(r.expires,100+expected)
    def test_concurrent_titles_share_one_dns_lookup_pair(self):
        fetch=Mock(return_value=dns());r=VodDnsResolver(fetch,lambda:0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(list(pool.map(lambda _:r.resolve(),range(12))),[['8.8.8.8']]*12)
        self.assertEqual(fetch.call_count,2)
    def test_resolvers_must_agree_and_do_not_overwrite_valid_cache_on_failure(self):
        fetch=Mock(return_value=dns());r=VodDnsResolver(fetch,lambda:0);r.resolve()
        fetch.side_effect=[dns('1.1.1.1'),dns('9.9.9.9')]
        with self.assertRaises(ValueError):r.resolve(force=True)
        self.assertEqual(r.answers,('8.8.8.8',));self.assertEqual(r.expires,300)
    def test_single_resolver_failure_does_not_silently_trust_the_other(self):
        r=VodDnsResolver(Mock(side_effect=[dns(),TimeoutError()]),lambda:0)
        with self.assertRaises(TimeoutError):r.resolve()
        self.assertFalse(r.answers)
    def test_unexpected_hostname_rejected_without_queries(self):
        fetch=Mock();r=VodDnsResolver(fetch)
        with self.assertRaises(ValueError):r.resolve('other.invalid')
        fetch.assert_not_called()
    def test_dns_response_must_match_question_status_and_owner(self):
        malformed=[{'Status':3}, {'Status':0,'Question':[{'name':'other.invalid','type':1}],'Answer':dns()['Answer']},
                   {'Status':0,'Question':dns()['Question'],'Answer':[{'name':'other.invalid','type':1,'TTL':60,'data':'8.8.8.8'}]},
                   {**dns(),'Answer':[]}, {**dns(),'Answer':[{}]*129},dns(ttl=-1),dns(ttl=True)]
        for value in malformed:
            with self.subTest(value=value),self.assertRaises(ValueError):parse_answer(value)
    def test_cname_chain_must_start_at_queried_host(self):
        value=dns();value['Answer']=[{'name':HOST,'type':5,'TTL':20,'data':'cdn.example.invalid.'},
                                   {'name':'cdn.example.invalid','type':1,'TTL':100,'data':'8.8.8.8'}]
        self.assertEqual(parse_answer(value),(['8.8.8.8'],20))
        value['Answer'][0]['name']='other.invalid'
        with self.assertRaises(ValueError):parse_answer(value)
    def test_private_reserved_multicast_non_ip_and_ipv6_rejected(self):
        for ip in ['127.0.0.1','10.0.0.1','192.168.1.1','169.254.169.254','100.64.0.1','0.0.0.0',
                   '192.0.2.1','203.0.113.1','224.0.0.1','255.255.255.255','::1','2606:4700:4700::1111',
                   'media.example.invalid','2130706433',1,None]:
            with self.subTest(ip=ip),self.assertRaises(ValueError):public_ipv4(ip)
    def test_source_and_index_use_selected_dns_ip_and_preserve_host(self):
        value=source_config(response(),[{'media_code':'synthetic','license':'synthetic'}],{'App':'test'},resolved_ip='8.8.8.8')
        self.assertEqual(urllib.parse.urlsplit(value['url']).netloc,'8.8.8.8:80')
        self.assertEqual(urllib.parse.urlsplit(value['vod_index_url']).netloc,'8.8.8.8:80')
        self.assertTrue(urllib.parse.urlsplit(value['vod_index_url']).path.endswith('movie.idx'))
        self.assertEqual(value['headers']['host'],HOST+':80')
    def test_unknown_media_or_index_origins_and_wrong_media_never_forward_license(self):
        for field,uri in [('media_url','http://other.invalid/vod/x'),('idx_url','http://other.invalid/vod/x'),
                          ('idx_url','http://u:p@'+HOST+'/vod/x'),('idx_url','https://'+HOST+'/vod/x'),
                          ('media_url','http://'+HOST+'/vod/x?media_code=other')]:
            value=response();value['play_infos'][1]['servers'][0][field]=uri
            with self.subTest(field=field,uri=uri),self.assertRaises(ValueError):
                source_config(value,[{'media_code':'synthetic','license':'synthetic'}],{},resolved_ip='8.8.8.8')
        with self.assertRaises(ValueError):source_config(response(),[{'media_code':'synthetic','license':'synthetic'}],{})
    def test_resolver_refreshes_dns_after_connection_failure_and_uses_new_answer(self):
        dns_callback=Mock(side_effect=[['8.8.8.8'],['1.1.1.1']])
        first=Mock();first.request.side_effect=TimeoutError();second=Mock();second.request.return_value=response()
        resolver=VerifiedVodResolver(object(),{},dns_resolver=dns_callback)
        with patch('ranger_vod_renewal.time.time',return_value=100),patch('ranger_vod_renewal.SlbHttpClient',side_effect=[first,second]) as client:
            result,_=resolver.resolve(playback(),configuration())
        self.assertEqual(dns_callback.call_args_list[0].kwargs,{'force':False})
        self.assertEqual(dns_callback.call_args_list[1].kwargs,{'force':True})
        self.assertEqual(urllib.parse.urlsplit(result['url']).hostname,'1.1.1.1')
        self.assertEqual(client.call_args_list[1].args[1](HOST),['1.1.1.1'])
        self.assertEqual(client.call_args_list[1].args[1]('other.invalid'),[])
    def test_rejected_slb_request_not_replayed_or_sent_to_alternative_host(self):
        from ranger_slb_http import SlbRejected
        client=Mock();client.request.side_effect=SlbRejected(403,0);callback=Mock(return_value=['8.8.8.8'])
        resolver=VerifiedVodResolver(object(),{},dns_resolver=callback)
        with patch('ranger_vod_renewal.time.time',return_value=100),patch('ranger_vod_renewal.SlbHttpClient',return_value=client):
            with self.assertRaises(SlbRejected):resolver.resolve(playback(),configuration())
        self.assertEqual(client.request.call_count,1);self.assertEqual(callback.call_count,1)
    def test_network_failure_renews_once_and_preserves_requested_byte_range(self):
        seen=[];calls=[]
        class Transport:
            def __init__(self,config):self.url=config['url'];self.expires=10000
            def fetch(self,url,**kwargs):
                seen.append((url,kwargs))
                if '8.8.8.8' in url:raise TimeoutError()
                return {'status':206,'body':b'example'}
        def renew():
            calls.append(1)
            return {'url':('http://8.8.8.8' if len(calls)==1 else 'http://1.1.1.1')+'/vod/x'}
        source=RenewingVodSource(renew,Transport,clock=lambda:100)
        self.assertEqual(source.fetch(byte_range='bytes=100-199')['status'],206)
        self.assertEqual(len(calls),2);self.assertEqual(len(seen),2)
        self.assertEqual(seen[1],('http://1.1.1.1/vod/x',{'byte_range':'bytes=100-199'}))
    def test_gone_and_conflict_status_renew_once(self):
        for status in (409,410):
            calls=[]
            class Transport:
                def __init__(self,config):self.expires=10000;self.url='http://synthetic.invalid';self.status=config
                def fetch(self,*args,**kwargs):return {'status':self.status}
            def renew():calls.append(1);return status
            self.assertEqual(RenewingVodSource(renew,Transport,clock=lambda:100).fetch()['status'],status)
            self.assertEqual(len(calls),2)

    def test_vod_service_index_retry_follows_renewed_dns_transport(self):
        from vod import VodService
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder);directory=root/'work/portal-native';directory.mkdir(parents=True)
            (directory/'active-data.private.json').write_text('{}',encoding='utf8')
            profile={'schema':1,'vod_slb_host':HOST,'vod_slb_ip':'8.8.8.8','headers':{
                'app':'test','app-version':'test','ranger-id':'synthetic','user-agent':'test'}}
            (directory/'media-client.private.json').write_text(json.dumps(profile),encoding='utf8')
            asset={'contentId':'synthetic','name':'Test movie'}
            portal=types.SimpleNamespace(lock=threading.RLock(),assets={'item':('movies',asset)},columns={'movies':76263},
                title_detail=lambda item:{'simpleProgramList':[{'contentId':'synthetic'}]},
                request=lambda endpoint,params:playback()['data'] if 'startPlayVOD' in endpoint else configuration()['data'])
            lookups=[];requests=[]
            class Resolver:
                def __init__(self,*args):pass
                def resolve(self,*args,force_dns=False):
                    lookups.append(force_dns);ip='8.8.8.8' if len(lookups)==1 else '1.1.1.1'
                    return source_config(response(),[{'media_code':'synthetic','license':'synthetic'}],{},resolved_ip=ip),response()
            class Transport:
                def __init__(self,config):self.config=config;self.url=config['url'];self.expires=time.time()+3600
                def fetch(self,url,**kwargs):
                    requests.append(url)
                    if '8.8.8.8' in url:raise TimeoutError()
                    return {'status':200,'body':b'synthetic-index'}
            index={'duration_ms':1000,'width':1280,'height':720,'segments':[],'size':188}
            with patch('vod.codec',return_value=object()),patch('vod.VerifiedVodResolver',Resolver),\
                    patch('vod.RangerHlsTransport',Transport),patch('vod.parse_idxg',return_value=index),\
                    patch.object(VodService,'segment',return_value=b'synthetic'),patch('vod.audio_tracks',return_value=[]):
                service=VodService(root,portal);result=service.start('item')
            self.assertEqual(lookups,[False,True])
            self.assertEqual([urllib.parse.urlsplit(url).hostname for url in requests],['8.8.8.8','1.1.1.1'])
            self.assertTrue(all(urllib.parse.urlsplit(url).path.endswith('movie.idx') for url in requests))
            self.assertEqual(service.state['source_renewals'],1)
            self.assertEqual(result['duration_seconds'],1)

if __name__=='__main__':unittest.main()
