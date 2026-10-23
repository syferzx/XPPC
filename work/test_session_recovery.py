import sys,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'outputs/windows-hls-player'),str(ROOT/'work')]
from portal import PortalService,PortalSessionExpired,PortalSessionConflict,recover_existing_session

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.directory=self.root/'work/portal-native';self.directory.mkdir(parents=True)
    def test_expired_session_is_recovered_once_and_original_query_retried(self):
        calls=[];restored=[]
        class Client:
            def request(inner,endpoint,params):
                calls.append(params['userToken'])
                return 200,b'',{'returnCode':'0' if restored else 'aaa100028','data':{'ok':True}}
        client=Client()
        def factory():return client,{'userToken':'new' if restored else 'old'},self.directory
        service=PortalService(self.root,factory,lambda root:restored.append(root))
        self.assertEqual(service.request('/metadata',{}),{'ok':True});self.assertEqual(calls,['old','new']);self.assertEqual(len(restored),1)
    def test_conflict_does_not_trigger_sign_in(self):
        class Client:
            def request(inner,*args):return 200,b'',{'returnCode':'aaa100083'}
        service=PortalService(self.root,lambda:(Client(),{},self.directory),lambda root:self.fail('Unexpected recovery'))
        with self.assertRaises(PortalSessionConflict):service.request('/metadata',{})
    def test_still_expired_is_not_retried_in_a_loop(self):
        restored=[]
        class Client:
            def request(inner,*args):return 200,b'',{'returnCode':'aaa100028'}
        service=PortalService(self.root,lambda:(Client(),{},self.directory),lambda root:restored.append(root))
        for _ in range(2):
            with self.assertRaises(PortalSessionExpired):service.request('/metadata',{})
        self.assertEqual(len(restored),1)
    def profile(self):
        for file,value in [('active-data.private.json',{'userId':'same','userToken':'old'}),
                           ('installation.private.json',{'installation_id':'fixed'}),
                           ('client-profile.private.json',{'device_params':{'serialNumber':'fixed'},'metadata':{'sn':'same-sn'}})]:
            (self.directory/file).write_text(json.dumps(value))
    def test_account_change_is_rejected_without_overwriting_session(self):
        self.profile();before=(self.directory/'active-data.private.json').read_bytes();directory=self.directory
        class Client:
            def request(inner,endpoint,*args):
                data={'snToken':'token','sn':'same-sn','isNew':False} if endpoint.endswith('snToken') else {'userId':'other','userToken':'new','portalCodeList':[{}]}
                return 200,b'',{'returnCode':'0','data':data}
        with patch('probe_portal_session.build_client',return_value=(Client(),{},directory)):
            with self.assertRaises(PortalSessionExpired):recover_existing_session(self.root)
        self.assertEqual((directory/'active-data.private.json').read_bytes(),before)
    def test_same_account_response_is_saved_without_altering_granted_time(self):
        self.profile();directory=self.directory
        class Client:
            def request(inner,endpoint,*args):
                data={'snToken':'token','sn':'same-sn','isNew':False} if endpoint.endswith('snToken') else {'userId':'same','userToken':'new','portalCodeList':[{}],'availableTime':123}
                return 200,b'',{'returnCode':'0','data':data}
        with patch('probe_portal_session.build_client',return_value=(Client(),{},directory)):recover_existing_session(self.root)
        saved=json.loads((directory/'active-data.private.json').read_text());self.assertEqual(saved['userToken'],'new');self.assertEqual(saved['availableTime'],123)

if __name__=='__main__':unittest.main()
