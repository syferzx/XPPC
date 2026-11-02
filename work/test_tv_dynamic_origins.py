"""Offline tests for HTTPS-issued TV rotations. All grants and addresses synthetic."""
import json,ssl,sys,tempfile,threading,types,unittest,urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work'),str(ROOT/'outputs/windows-hls-player'),str(ROOT/'outputs/ranger-windows')]
from tv import TvService,make_source,media_url

BASE=('http','208.115.233.59',23455)
NEW='http://8.8.8.8:8119'
NEXT='http://1.1.1.1:33984'

def template():
    return {'url':'http://208.115.233.59:23455/live/',
            'headers':{'host':'208.115.233.59:23455','content-auth':'old','app':'synthetic'},
            'headers_original':[('Host','208.115.233.59:23455'),('Content-Auth','old')]}

def reply(uri=NEW+'/live/?tag=free&expired=10000'):
    return {'servers':[{'media_url':uri}]}

class Transport:
    def __init__(self,config):
        self.config=config;self.origin=urllib.parse.urlsplit(config['url'])
        self.expires=int(urllib.parse.parse_qs(config['headers']['content-auth'].split('?',1)[1])['expired'][0])
        self.calls=[]
    def fetch(self,url,**kwargs):
        self.calls.append((url,kwargs));return {'status':200,'body':b'synthetic'}

class DynamicTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('socket.create_connection',side_effect=AssertionError('Offline test attempted networking'))
        self.network.start();self.addCleanup(self.network.stop)
    def source(self,uri):
        return make_source(template(),reply(uri),'free',BASE,verified_slb=True,now=100)
    def service(self):
        folder=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(folder.cleanup)
        s=TvService.__new__(TvService);s.root=Path(folder.name)
        session=s.root/'work/portal-native';session.mkdir(parents=True)
        (session/'active-data.private.json').write_text('{}',encoding='utf8')
        s.lock=threading.RLock();s.clock=lambda:100;s.catalog_updated=100
        s.media_origin=BASE;s.slb_host='slb.example.invalid';s.original=template()
        s.transports={};s.protocol=object()
        s.state={'source_lookups':0,'source_renewals':0,'authorization_retries':0,'network_retries':0,'last_error':None}
        s.selection=lambda owner:({'channelCode':'synthetic'}, {'license':'synthetic','tag':'free'},'http://208.115.233.59:23455/live/synthetic.m3u8')
        s.service_address='https://slb.example.invalid'
        s.portal=types.SimpleNamespace(lock=threading.RLock(),request=lambda endpoint,params:{'cdn_list':[
            {'tag':'live','cdn_type':'1','main_addr':s.service_address,
             'url_list':[{'tag':'free','url':'tag=free&expired=10000'}]}]})
        s.factory=Transport
        return s
    def test_new_public_ip_and_port_from_verified_reply_are_accepted(self):
        original=template()
        config=make_source(original,reply(),'free',BASE,verified_slb=True,now=100)
        self.assertEqual(config['url'],NEW+'/live/')
        self.assertEqual(dict(config['headers_original'])['Host'],'8.8.8.8:8119')
        self.assertEqual(original,template())
    def test_no_unverified_learning(self):
        with self.assertRaises(ValueError):make_source(template(),reply(),'free',BASE)
    def test_private_reserved_local_multicast_and_hostname_destinations_rejected(self):
        for host in ['127.0.0.1','10.0.0.1','192.168.1.1','169.254.169.254','100.64.0.1','0.0.0.0',
                     '192.0.2.1','198.51.100.1','203.0.113.1','224.0.0.1','255.255.255.255',
                     'media.example.invalid','2130706433','0177.0.0.1','[::1]','[2606:4700:4700::1111]']:
            with self.subTest(host=host),self.assertRaises(ValueError):
                self.source('http://'+host+':8119/live/?tag=free&expired=10000')
    def test_malformed_source_and_wrong_channel_never_accepted(self):
        for uri in [NEW+'/other/?tag=free&expired=10000',NEW+'/live/?tag=other&expired=10000',
                    NEW+'/live/?tag=free&tag=other&expired=10000',NEW+'/live/?tag=free',
                    NEW+'/live/?tag=free&expired=190',NEW+'/live/?tag=free&expired=10000&expired=20000',
                    NEW+'/live/?tag=free&expired=not-a-number',NEW+'/live/?tag=free&expired=10000#x',
                    'http://u:p@8.8.8.8:8119/live/?tag=free&expired=10000',
                    'https://8.8.8.8:8119/live/?tag=free&expired=10000',
                    'http://8.8.8.8/live/?tag=free&expired=10000',
                    'http://8.8.8.8:0/live/?tag=free&expired=10000',
                    NEW+'/live/?tag=free&expired=10000\r\nX-Test: bad']:
            with self.subTest(uri=uri),self.assertRaises(ValueError):self.source(uri)
    def test_non_source_list_and_excessive_reply_rejected(self):
        for value in [[],{}, {'servers':None},{'servers':{}},{'servers':[{}]*129}]:
            with self.subTest(value=type(value)),self.assertRaises(ValueError):
                make_source(template(),value,'free',BASE,verified_slb=True,now=100)
    def test_only_matching_tag_selected(self):
        value={'servers':[{'media_url':NEXT+'/live/?tag=other&expired=10000'},*reply()['servers']]}
        self.assertEqual(make_source(template(),value,'free',BASE,verified_slb=True,now=100)['url'],NEW+'/live/')
    def test_renew_learns_and_rebases_old_requests_to_current_node(self):
        s=self.service()
        with patch('tv.SlbHttpClient') as client:
            client.return_value.request.return_value=reply()
            first=s.renew('channel','free')
            client.return_value.request.return_value=reply(NEXT+'/live/?tag=free&expired=20000')
            second=s.renew('channel','free')
        self.assertNotEqual(first.origin.netloc,second.origin.netloc)
        self.assertEqual(media_url(NEW+'/live/a.ts?sequence=3',second,BASE),NEXT+'/live/a.ts?sequence=3')
        self.assertEqual(s.state['dynamic_origin_updates'],2)
        self.assertEqual(s.state['source_renewals'],1)
        self.assertEqual(s.fetch('channel',NEW+'/live/a.ts')['source_url'],NEXT+'/live/a.ts')
        self.assertEqual(len(first.calls),0)
    def test_other_unissued_public_origin_is_rejected_before_transport(self):
        s=self.service()
        with patch('tv.SlbHttpClient') as client:
            client.return_value.request.return_value=reply();t=s.renew('channel','free')
        with self.assertRaises(ValueError):s.fetch('channel',NEXT+'/live/a.ts')
        self.assertFalse(t.calls)
        for uri in [NEW+'/admin',NEW+'/live/a.ts#x','http://u:p@8.8.8.8:8119/live/a.ts']:
            with self.subTest(uri=uri),self.assertRaises(ValueError):media_url(uri,t,BASE)
    def test_slb_plaintext_or_changed_hostname_rejected_before_request(self):
        for address in ['http://slb.example.invalid','https://other.example.invalid','https://slb.example.invalid:444']:
            s=self.service();s.service_address=address
            with patch('tv.SlbHttpClient') as client,self.assertRaises(ValueError):s.renew('channel','free')
            client.assert_not_called();self.assertFalse(s.transports)
    def test_actual_slb_connection_keeps_hostname_and_certificate_verification(self):
        from ranger_slb_http import SlbHttpClient
        conn=SlbHttpClient(object(),lambda host:[]).connection(
            urllib.parse.urlsplit('https://slb.example.invalid'),'8.8.8.8')
        try:
            self.assertEqual(conn.host,'slb.example.invalid')
            self.assertTrue(conn._context.check_hostname)
            self.assertEqual(conn._context.verify_mode,ssl.CERT_REQUIRED)
        finally:conn.close()
    def test_failed_certificate_or_invalid_new_source_keeps_previous_transport(self):
        s=self.service()
        with patch('tv.SlbHttpClient') as client:
            client.return_value.request.return_value=reply();old=s.renew('channel','free')
            client.return_value.request.side_effect=ssl.SSLCertVerificationError('synthetic certificate failure')
            with self.assertRaises(ssl.SSLCertVerificationError):s.renew('channel','free')
            self.assertIs(s.transports['free'],old)
            client.return_value.request.side_effect=None
            client.return_value.request.return_value=reply('http://127.0.0.1:8119/live/?tag=free&expired=10000')
            with self.assertRaises(ValueError):s.renew('channel','free')
            self.assertIs(s.transports['free'],old)
    def test_history_bounded_and_not_shared_between_instances(self):
        s=self.service();other=self.service()
        with patch('tv.SlbHttpClient') as client:
            for port in range(8100,8120):
                client.return_value.request.return_value=reply('http://8.8.8.8:'+str(port)+'/live/?tag=free&expired=10000')
                t=s.renew('channel','free')
            client.return_value.request.return_value=reply(NEXT+'/live/?tag=free&expired=10000')
            isolated=other.renew('channel','free')
        self.assertEqual(len(t._tv_media_origins),8)
        with self.assertRaises(ValueError):media_url('http://8.8.8.8:8100/live/a.ts',t,BASE)
        with self.assertRaises(ValueError):media_url('http://8.8.8.8:8119/live/a.ts',isolated,BASE)

if __name__=='__main__':unittest.main()
