import sys,unittest,threading,json,tempfile,types,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path('outputs/windows-hls-player').resolve()))
from tv import TvService,make_source

class FakeTransport:
    origin=urllib.parse.urlsplit('http://23.227.144.242:44822/live/')
    expires=200
    status=200
    calls=0
    def fetch(self,url,**kwargs):self.calls+=1;return {'status':self.status}

class TvTests(unittest.TestCase):
    def service(self):
        s=TvService.__new__(TvService);s.lock=threading.RLock();s.clock=lambda:100;s.catalog_updated=100;s.media_origin=('http','23.227.144.242',44822);s.transports={'free':FakeTransport()};s.state={'authorization_retries':0,'network_retries':0,'last_error':None}
        s.selection=lambda owner:({}, {'tag':'free','license':'synthetic'},'http://23.227.144.242:44822/live/synthetic.m3u8')
        self.renewals=0
        def renew(owner,tag):self.renewals+=1;s.transports[tag]=FakeTransport();return s.transports[tag]
        s.renew=renew;return s
    def test_reuses_valid_source_then_renews_near_expiry(self):
        s=self.service();first=s.current('a')[0];self.assertIs(first,s.current('b')[0]);self.assertEqual(self.renewals,0)
        first.expires=180;self.assertIsNot(first,s.current('b')[0]);self.assertEqual(self.renewals,1)
    def test_failed_renewal_does_not_replace_existing_source(self):
        s=self.service();old=s.transports['free'];old.expires=180
        def fail(*args):raise ValueError('unavailable')
        s.renew=fail
        with self.assertRaises(ValueError):s.current('a')
        self.assertIs(old,s.transports['free'])
    def test_auth_rejection_renews_once(self):
        s=self.service();s.transports['free'].status=409
        self.assertEqual(s.fetch('a')['status'],200);self.assertEqual(self.renewals,1)
    def test_missing_channel_segment_does_not_renew(self):
        s=self.service();s.transports['free'].status=404
        self.assertEqual(s.fetch('a')['status'],404);self.assertEqual(self.renewals,0)
    def test_rejects_changed_media_origin(self):
        for uri in ['http://example.invalid/live/?tag=free','https://23.227.144.242:44822/live/?tag=free','http://23.227.144.242:44822/other/?tag=free']:
            with self.assertRaises(ValueError):make_source({}, {'servers':[{'media_url':uri}]},'free')
    def test_rejects_other_license_tag(self):
        with self.assertRaises(ValueError):make_source({}, {'servers':[{'media_url':'http://23.227.144.242:44822/live/?tag=other'}]},'free')
    def test_backend_rotation_updates_transport_and_host_without_mutating_template(self):
        origin=('http','208.115.233.59',23455)
        original={'url':'http://208.115.233.59:23455/live/','headers':{'host':'208.115.233.59:23455','content-auth':'old'},'headers_original':[('host','208.115.233.59:23455'),('content-auth','old')]}
        response={'servers':[{'media_url':'http://192.119.15.58:33984/live/?tag=free&expired=9999999999'}]}
        result=make_source(original,response,'free',origin)
        self.assertEqual(result['url'],'http://192.119.15.58:33984/live/')
        self.assertEqual(result['headers']['host'],'192.119.15.58:33984')
        self.assertEqual(dict(result['headers_original'])['host'],'192.119.15.58:33984')
        self.assertEqual(original['headers']['content-auth'],'old')
        self.assertEqual(original['headers']['host'],'208.115.233.59:23455')
    def test_current_uses_selected_transport_origin_for_channel_playlist(self):
        service=self.service()
        service.transports['free'].origin=urllib.parse.urlsplit('http://192.119.15.58:33984/live/')
        self.assertEqual(service.current('a')[2],'http://192.119.15.58:33984/live/synthetic.m3u8')
    def test_rotation_remains_scoped_to_route_and_rejects_unexpected_destinations(self):
        for uri in ['http://127.0.0.1:33984/live/?tag=free','http://192.119.15.58:33985/live/?tag=free','http://192.119.15.58:33984/other/?tag=free','http://user:pass@192.119.15.58:33984/live/?tag=free','http://192.119.15.58:33984/live/?tag=free#x']:
            with self.subTest(uri=uri),self.assertRaises(ValueError):
                make_source({}, {'servers':[{'media_url':uri}]},'free',('http','208.115.233.59',23455))
        with self.assertRaises(ValueError):
            make_source({}, {'servers':[{'media_url':'http://192.119.15.58:33984/live/?tag=free'}]},'free')
    def test_catalog_survives_restart_and_portal_timeout(self):
        with tempfile.TemporaryDirectory(dir=Path('work')) as folder:
            root=Path(folder);(root/'work').mkdir()
            from access_profile import TV_ROUTES
            profile=root/'work/portal-native';profile.mkdir()
            host,ip=next(iter(TV_ROUTES))
            (profile/'media-client.private.json').write_text(json.dumps({'schema':1,'tv_slb_host':host,'tv_slb_ip':ip,'headers':{'app':'test','app-version':'test','ranger-id':'synthetic-test','user-agent':'test'}}))
            rows=[{'channelCode':'test-channel','name':'Test TV','liveAddressList':[]}]
            portal=types.SimpleNamespace(lock=threading.RLock(),request=lambda endpoint,params:{'channelList':rows if params['columnId']==76182 else []})
            original=TvService(root,portal);original.refresh_catalog()
            def timeout(*args):raise TimeoutError('synthetic timeout')
            portal.request=timeout
            reopened=TvService(root,portal)
            self.assertEqual(reopened.catalog_items()[0]['name'],'Test TV')
            self.assertEqual(reopened.catalog_items()[0]['groups'],['General y variedades'])
            self.assertEqual(reopened.state['last_error'],'TimeoutError')
    def test_separate_provider_adult_catalog_is_merged_without_changing_grants(self):
        with tempfile.TemporaryDirectory(dir=Path('work')) as folder:
            root=Path(folder);(root/'work').mkdir()
            base={'channelCode':'base','name':'Noticias','restricted':'0','liveAddressList':[]}
            adult={'channelCode':'adult','name':'Canal adulto','restricted':'1','liveAddressList':[]}
            seen=[]
            def request(endpoint,params):
                seen.append(params['columnId'])
                return {'channelList':[base] if params['columnId']==76182 else [adult]}
            service=TvService.__new__(TvService);service.root=root;service.clock=lambda:100
            service.portal=types.SimpleNamespace(lock=threading.RLock(),request=request)
            service.state={};service.refresh_catalog()
            self.assertEqual(seen,[76182,76208]);self.assertEqual(len(service.channels),2)
            channel=next(c for c in service.channels.values() if c['channelCode']=='adult')
            self.assertEqual(channel['categoryName'],'Adultos +18');self.assertEqual(channel['restricted'],'1')
            self.assertEqual(channel['liveAddressList'],[]);self.assertNotIn('categoryName',adult)
    def test_denied_adult_catalog_does_not_remove_general_channels(self):
        with tempfile.TemporaryDirectory(dir=Path('work')) as folder:
            root=Path(folder);(root/'work').mkdir()
            def request(endpoint,params):
                if params['columnId']==76208:raise PermissionError('Not granted')
                return {'channelList':[{'channelCode':'base','name':'Noticias'}]}
            service=TvService.__new__(TvService);service.root=root;service.clock=lambda:100
            service.portal=types.SimpleNamespace(lock=threading.RLock(),request=request)
            service.state={};service.refresh_catalog()
            self.assertEqual(len(service.channels),1);self.assertEqual(service.state['adult_catalog_error'],'PermissionError')
if __name__=='__main__':unittest.main()

