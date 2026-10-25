"""No-network renewal tests: expiry, recovery, bounded retries and secret routing."""
import unittest
from ranger_vod_renewal import RenewingVodSource,source_config
from ranger_slb_http import SlbHttpClient

class Transport:
    def __init__(self,config):self.expires=config['expires'];self.status=config.get('status',200);self.url='http://example.invalid/video'
    def fetch(self,url,**kwargs):return {'status':self.status}

class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.now=0;self.calls=0
    def renew(self):self.calls+=1;return {'expires':self.now+200}
    def test_renew_before_expiry_without_repeating_when_still_valid(self):
        source=RenewingVodSource(self.renew,Transport,lambda:self.now)
        first=source.current();self.assertIs(source.current(),first);self.assertEqual(self.calls,1)
        self.now=111;self.assertIsNot(source.current(),first);self.assertEqual(self.calls,2)
    def test_auth_failure_retries_only_once(self):
        def rejected():self.calls+=1;return {'expires':200,'status':403}
        source=RenewingVodSource(rejected,Transport,lambda:0)
        self.assertEqual(source.fetch()['status'],403);self.assertEqual(self.calls,2)
    def test_auth_failure_recovers_with_new_source(self):
        def renew():self.calls+=1;return {'expires':200,'status':403 if self.calls==1 else 206}
        source=RenewingVodSource(renew,Transport,lambda:0)
        self.assertEqual(source.fetch()['status'],206);self.assertEqual(self.calls,2)
    def test_failed_replacement_preserves_existing_source(self):
        source=RenewingVodSource(self.renew,Transport,lambda:self.now);old=source.current()
        source.renew=lambda:{'expires':0}
        with self.assertRaises(ValueError):source.current(force=True)
        self.assertIs(source.transport,old)
    def test_does_not_retry_non_auth_errors(self):
        def renew():self.calls+=1;return {'expires':200,'status':400}
        self.assertEqual(RenewingVodSource(renew,Transport,lambda:0).fetch()['status'],400);self.assertEqual(self.calls,1)
    def test_network_retries_are_bounded_without_renewing_license(self):
        class Offline(Transport):
            attempts=0
            def fetch(self,url,**kwargs):
                self.attempts+=1
                raise TimeoutError()
        source=RenewingVodSource(self.renew,Offline,lambda:0)
        with self.assertRaises(TimeoutError):source.fetch()
        self.assertEqual(source.transport.attempts,3);self.assertEqual(self.calls,1)
    def test_rejects_unverified_media_origin(self):
        value={'play_infos':[{'media_code':'synthetic','servers':[{'media_url':'http://example.invalid/video'}]}]}
        with self.assertRaises(ValueError):source_config(value,[{'media_code':'synthetic','license':'synthetic'}],{})
    def test_app_headers_cannot_override_host_or_inject_headers(self):
        for headers in [{'Host':'example.invalid'},{'App':'a\r\nHost: example.invalid'}]:
            with self.assertRaises(ValueError):SlbHttpClient(None,None,extra_headers=headers)

if __name__=='__main__':unittest.main()
