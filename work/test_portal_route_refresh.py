import sys,json,tempfile,unittest,ssl,types,urllib.parse,base64,struct,io
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'work'))
import portal_client

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);(root/'outputs').mkdir();(root/'outputs/rutas-portal.json').write_text(json.dumps(['/api/portalCore/check']))
        self.addCleanup(patch.stopall);patch.object(portal_client,'ROOT',root).start()
        self.client=portal_client.PortalClient.__new__(portal_client.PortalClient)
        self.client.hosts=('portal.example.invalid',);self.client.headers={};self.client.metadata={};self.client.resolved={self.client.hosts[0]:['old']};self.client.dns_resolver={'host':'dns.example.invalid','path':'/dns-query'};self.client.dns_attempts={}
        self.client.codec=types.SimpleNamespace(encode=lambda value:b'body',decode=lambda raw:json.loads(raw))
    def connection(self,connect_error=None,read_error=None):
        connection=Mock();connection.sock=Mock();connection.connect.side_effect=connect_error
        if read_error:connection.getresponse.side_effect=read_error
        else:connection.getresponse.return_value=types.SimpleNamespace(status=200,headers={},read=lambda size:b'{"data":{}}')
        return connection
    def test_failed_connection_refreshes_dns_before_one_post(self):
        old=self.connection(TimeoutError());new=self.connection()
        self.client.refresh_dns=Mock(return_value=['new'])
        with patch.object(portal_client.http.client,'HTTPSConnection',side_effect=[old,new]) as factory:
            self.client.request('/api/portalCore/check',{})
        old.request.assert_not_called();new.request.assert_called_once();self.client.refresh_dns.assert_called_once()
        for call in factory.call_args_list:
            self.assertEqual(call.args[0],'portal.example.invalid');self.assertEqual(call.kwargs['context'].verify_mode,ssl.CERT_REQUIRED);self.assertTrue(call.kwargs['context'].check_hostname)
    def test_read_timeout_never_replays_already_sent_request(self):
        connection=self.connection(read_error=TimeoutError());self.client.refresh_dns=Mock()
        with patch.object(portal_client.http.client,'HTTPSConnection',return_value=connection):
            with self.assertRaises(TimeoutError):self.client.request('/api/portalCore/check',{})
        connection.request.assert_called_once();self.client.refresh_dns.assert_not_called()
    def test_invalid_certificate_never_receives_credentials(self):
        connections=[self.connection(ssl.SSLCertVerificationError()) for _ in range(2)];self.client.refresh_dns=Mock(return_value=['new'])
        with patch.object(portal_client.http.client,'HTTPSConnection',side_effect=connections):
            with self.assertRaises(ssl.SSLCertVerificationError):self.client.request('/api/portalCore/check',{})
        for connection in connections:connection.request.assert_not_called()
    def resolver(self,address=b'\x08\x08\x08\x08'):
        def open_response(request,timeout):
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)['dns'][0]
            question=base64.urlsafe_b64decode(query+'='*((-len(query))%4))
            message=question[:2]+struct.pack('>HHHHH',0x8180,1,1,0,0)+question[12:]+b'\xc0\x0c'+struct.pack('>HHIH',1,1,60,4)+address
            return io.BytesIO(message)
        return types.SimpleNamespace(open=open_response)
    def test_dns_answer_parsing_and_cooldown(self):
        with patch.object(portal_client.urllib.request,'build_opener',return_value=self.resolver()):
            self.assertEqual(self.client.refresh_dns(self.client.hosts[0],ssl.create_default_context()),['8.8.8.8'])
            with self.assertRaises(ConnectionError):self.client.refresh_dns(self.client.hosts[0],ssl.create_default_context())
    def test_private_address_is_rejected(self):
        with patch.object(portal_client.urllib.request,'build_opener',return_value=self.resolver(b'\x7f\x00\x00\x01')):
            with self.assertRaises(ConnectionError):self.client.refresh_dns(self.client.hosts[0],ssl.create_default_context())

if __name__=='__main__':unittest.main()
