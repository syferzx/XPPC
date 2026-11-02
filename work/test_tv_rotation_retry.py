"""Offline regressions: an allowed backend rotation must not reuse old URLs."""
import ast,collections,hashlib,sys,threading,unittest,urllib.parse,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work'),str(ROOT/'outputs/windows-hls-player'),str(ROOT/'outputs/ranger-windows')]
from tv import TvService,make_source,media_url

OLD='http://208.115.233.59:23455'
NEW='http://192.119.15.58:33984'
class Transport:
    def __init__(self,origin,status=200):
        self.origin=urllib.parse.urlsplit(origin);self.expires=10000;self.status=status;self.calls=[]
    def fetch(self,url,**kwargs):
        parsed=urllib.parse.urlsplit(url)
        if (parsed.scheme,parsed.hostname,parsed.port)!=(self.origin.scheme,self.origin.hostname,self.origin.port):
            raise ValueError('Cross-origin authorization rejected')
        self.calls.append((url,kwargs))
        return {'status':self.status,'body':b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\nsegment.ts\n'}

class Tests(unittest.TestCase):
    def test_fresh_install_assigned_backend_is_scoped_and_rebased(self):
        original={'url':OLD+'/live/','headers':{'host':'208.115.233.59:23455','content-auth':'old'},'headers_original':[('host','208.115.233.59:23455'),('content-auth','old')]}
        assigned='http://149.34.241.153:8119'
        origin=('http','208.115.233.59',23455)
        response={'servers':[{'media_url':assigned+'/live/?tag=free&expired=9999999999'}]}
        result=make_source(original,response,'free',origin)
        self.assertEqual(result['url'],assigned+'/live/')
        self.assertEqual(result['headers']['host'],'149.34.241.153:8119')
        transport=Transport(assigned)
        self.assertEqual(media_url(NEW+'/live/a.ts?sequence=2',transport,origin),assigned+'/live/a.ts?sequence=2')
        for uri in (assigned.replace(':8119',':8120')+'/live/?tag=free',assigned+'/other/?tag=free',assigned+'/live/?tag=other'):
            with self.subTest(uri=uri),self.assertRaises(ValueError):
                make_source(original,{'servers':[{'media_url':uri}]},'free',origin)
        with self.assertRaises(ValueError):make_source(original,response,'free',('http','23.227.144.242',44822))

    def service(self,status=409):
        s=TvService.__new__(TvService);s.lock=threading.RLock();s.clock=lambda:100;s.catalog_updated=100
        s.media_origin=('http','208.115.233.59',23455);s.transports={'free':Transport(OLD,status)}
        s.state={'authorization_retries':0,'network_retries':0,'last_error':None}
        s.selection=lambda owner:({}, {'tag':'free','license':'synthetic'},OLD+'/live/channel.m3u8')
        def renew(owner,tag):s.transports[tag]=Transport(NEW);return s.transports[tag]
        s.renew=renew
        return s
    def test_auth_retry_rebases_explicit_playlist_and_segment_urls(self):
        for path in ('/live/channel.m3u8','/live/segment.ts?sequence=12'):
            with self.subTest(path=path):
                s=self.service();result=s.fetch('channel',OLD+path,limit=123)
                self.assertEqual(result['status'],200);self.assertEqual(result['source_url'],NEW+path)
                self.assertEqual(s.transports['free'].calls[0],(NEW+path,{'license':'synthetic','limit':123}))
                self.assertEqual(s.state['authorization_retries'],1)
    def test_near_expiry_rebases_before_first_fetch(self):
        s=self.service();s.transports['free'].expires=180
        self.assertEqual(s.fetch('channel',OLD+'/live/segment.ts')['source_url'],NEW+'/live/segment.ts')
    def test_default_playlist_uses_new_origin_after_retry(self):
        self.assertEqual(self.service().fetch('channel')['source_url'],NEW+'/live/channel.m3u8')
    def test_cached_old_resources_follow_current_transport(self):
        s=self.service();s.renew('channel','free')
        self.assertEqual(s.resource_url('channel',OLD+'/live/segment.ts'),NEW+'/live/segment.ts')
    def test_invalid_origins_credentials_and_fragments_never_reach_transport(self):
        for uri in ('http://127.0.0.1/live/a.ts',NEW+':1/live/a.ts','https://192.119.15.58:33984/live/a.ts',NEW+'/live/a.ts#x','http://u:p@192.119.15.58:33984/live/a.ts'):
            with self.subTest(uri=uri):
                s=self.service(200)
                with self.assertRaises(ValueError):s.fetch('channel',uri)
                self.assertFalse(s.transports['free'].calls)
    def test_playlist_rewrites_relative_keys_and_segments_after_renewal(self):
        source=ast.parse((ROOT/'outputs/windows-hls-player/app.py').read_text(encoding='utf-8-sig'))
        nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('resource','playlist')]
        s=self.service();resources=collections.OrderedDict()
        ns={'tv':s,'default_id':'channel','urllib':urllib,'hashlib':hashlib,'re':re,
            'lock':threading.Lock(),'resources':resources,'stats':{'playlist_requests':0}}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'app-functions','exec'),ns)
        body=ns['playlist']('channel',OLD+'/live/channel.m3u8')
        self.assertIn(b'/segment/',body)
        self.assertEqual({url for url,owner in resources.values()},{NEW+'/live/segment.ts',NEW+'/live/key.bin'})
        self.assertTrue(all(owner=='channel' for url,owner in resources.values()))

if __name__=='__main__':unittest.main()
