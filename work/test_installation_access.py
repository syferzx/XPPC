"""Meaningful enrollment boundaries, without network requests or real accounts."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'outputs/windows-hls-player'))
from installation_access import configure,SetupError
from access_profile import media_headers,tv_route,vod_route

class Client:
    def __init__(self,hosts,headers,metadata,resolved):self.metadata=metadata;self.calls=[];self.reject=False;self.interrupt=False
    def request(self,endpoint,params):
        self.calls.append((endpoint,dict(params)))
        if self.interrupt:raise OSError('synthetic connection interruption')
        if self.reject:return 200,b'',{'returnCode':'registration_required'}
        data={'snToken':'synthetic-install-token','isNew':'0'} if endpoint.endswith('snToken') else {'userId':'independent-test-user','userToken':'independent-test-grant','portalCodeList':[{'portalCode':'test-portal'}],'hasPay':'0','availableTime':10}
        return 200,b'',{'returnCode':'0','data':data}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.base=Path(self.tmp.name);self.root=self.base/'data';self.bundle=self.base/'bundle'
        (self.bundle/'outputs').mkdir(parents=True)
        settings={'hosts':['provider.example'],'headers':{'apk':'app'},'metadata':{'loginType':'2'},'resolved':{},'codec_key':'synthetic-app-protocol-key','sn_suffix':'synthetic-app-suffix','media_headers':{'app':'app','app-version':'1','user-agent':'Ranger'},'tv_slb_host':'auuy2136a.xh09je1qy.com','tv_slb_ip':'206.253.89.124'}
        (self.bundle/'outputs/app-bootstrap.json').write_text(json.dumps(settings));(self.bundle/'outputs/rutas-portal.json').write_text('[]')
        self.clients=[]
        def factory(*args):
            c=Client(*args);self.clients.append(c);return c
        self.factory=factory
    def tearDown(self):self.tmp.cleanup()
    def test_success_reuses_identity_and_session_without_more_activation(self):
        self.assertTrue(configure(self.root,self.bundle,self.factory)['ready']);directory=self.root/'work/portal-native'
        identity=(directory/'installation.private.json').read_bytes()
        self.assertEqual(len(self.clients[0].calls),2)
        self.assertEqual(json.loads((directory/'active-data.private.json').read_text())['hasPay'],'0')
        self.assertTrue(configure(self.root,self.bundle,self.factory)['reused_session'])
        self.assertEqual(len(self.clients),1);self.assertEqual(identity,(directory/'installation.private.json').read_bytes())
        self.assertNotIn('userToken',media_headers(self.root,'tv'))
        self.assertEqual(tv_route(self.root)[2],('http','208.115.233.59',23455))
    def test_rejection_does_not_retry_or_rotate_identity(self):
        def reject(*args):c=self.factory(*args);c.reject=True;return c
        with self.assertRaises(SetupError):configure(self.root,self.bundle,reject)
        directory=self.root/'work/portal-native';identity=(directory/'installation.private.json').read_bytes()
        with self.assertRaises(SetupError):configure(self.root,self.bundle,reject)
        self.assertEqual([len(c.calls) for c in self.clients],[1,0]);self.assertEqual(identity,(directory/'installation.private.json').read_bytes())
        self.assertFalse((directory/'active-data.private.json').exists())
    def test_dns_migration_preserves_session_and_does_not_register_again(self):
        configure(self.root,self.bundle,self.factory);directory=self.root/'work/portal-native'
        preserved={name:(directory/name).read_bytes() for name in ('active-data.private.json','installation.private.json','media-client.private.json')}
        path=directory/'client-profile.private.json';profile=json.loads(path.read_text())
        profile.update(dns_resolver={'host':'old-mod.example','path':'/private-dns'},resolved={'provider.example':['192.0.2.1']});path.write_text(json.dumps(profile))
        self.assertTrue(configure(self.root,self.bundle,self.factory)['reused_session'])
        self.assertEqual(len(self.clients),1)
        migrated=json.loads(path.read_text());self.assertEqual(migrated['resolved'],{})
        self.assertEqual(migrated['dns_resolver'],{'host':'dns.google','path':'/dns-query'})
        for name,body in preserved.items():self.assertEqual((directory/name).read_bytes(),body)
    def test_uncertain_network_result_is_not_automatically_repeated(self):
        def interrupt(*args):c=self.factory(*args);c.interrupt=True;return c
        with self.assertRaises(OSError):configure(self.root,self.bundle,interrupt)
        with self.assertRaises(SetupError):configure(self.root,self.bundle,interrupt)
        self.assertEqual([len(c.calls) for c in self.clients],[1,0])
    def test_unvalidated_media_destination_fails_before_playback(self):
        configure(self.root,self.bundle,self.factory);path=self.root/'work/portal-native/media-client.private.json'
        value=json.loads(path.read_text());value['tv_slb_host']='other.example';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):tv_route(self.root)
    def test_unvalidated_vod_profile_fails_closed(self):
        configure(self.root,self.bundle,self.factory);path=self.root/'work/portal-native/media-client.private.json'
        self.assertEqual(vod_route(self.root),('yuwc.swzablvpm.com','66.225.197.106'))
        value=json.loads(path.read_text());value['vod_slb_host']='other.example';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):vod_route(self.root)

if __name__=='__main__':unittest.main()
