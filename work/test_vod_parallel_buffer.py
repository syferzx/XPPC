"""Offline behavioral checks for concurrency, seeks, deduplication and renewal."""
import sys,threading,time,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'work'),str(ROOT/'outputs/windows-hls-player'),str(ROOT/'outputs/ranger-windows')]
from segment_buffer import SegmentBuffer
from ranger_vod_renewal import RenewingVodSource
from vod import VodService

def segments(count=40):
    return [{'length':4,'duration_ms':5000,'offset':i*4} for i in range(count)]

class BufferTests(unittest.TestCase):
    def test_three_downloads_overlap_and_results_stay_in_order(self):
        buffer=SegmentBuffer();self.addCleanup(buffer.close)
        gate=threading.Barrier(3,timeout=3);first=True
        def read(n):
            if n<3:gate.wait()
            time.sleep(.005*(3-n%3));return bytes([n])*4
        self.assertEqual(buffer.get('movie',0,segments(),read),bytes(4))
        self.assertEqual([buffer.get('movie',n,segments(),read) for n in range(1,8)],
                         [bytes([n])*4 for n in range(1,8)])
        self.assertEqual(buffer.status()['peak_downloads'],3)
        self.assertLessEqual(buffer.status()['active_downloads'],3)

    def test_duplicate_requests_download_only_once(self):
        buffer=SegmentBuffer();self.addCleanup(buffer.close);calls=[]
        def read(n):calls.append(n);time.sleep(.08);return b'abcd'
        with ThreadPoolExecutor(max_workers=12) as pool:
            result=list(pool.map(lambda _:buffer.get('series',0,segments(),read,prefetch=False),range(12)))
        self.assertEqual(result,[b'abcd']*12);self.assertEqual(calls,[0])

    def test_seek_discards_old_read_ahead_and_memory_is_bounded(self):
        buffer=SegmentBuffer(cache_bytes=16);self.addCleanup(buffer.close)
        old_release=threading.Event();old_started=threading.Event();calls=[]
        def read(n):
            calls.append(n)
            if n in (1,2):old_started.set();old_release.wait(3)
            return bytes([n])*4
        buffer.get('movie',0,segments(),read);self.assertTrue(old_started.wait(2))
        with ThreadPoolExecutor(max_workers=1) as pool:
            seek=pool.submit(buffer.get,'movie',25,segments(),read)
            time.sleep(.05);old_release.set()
            self.assertEqual(seek.result(3),bytes([25])*4)
        time.sleep(.05)
        self.assertLessEqual(buffer.status()['cache_bytes'],16)
        self.assertNotIn(10,calls)
        self.assertTrue(all(ident[1]>=25 for ident in buffer.wanted))

    def test_background_failure_does_not_loop_and_foreground_can_retry(self):
        buffer=SegmentBuffer();self.addCleanup(buffer.close);calls=[]
        def read(n):
            calls.append(n)
            if n==1 and calls.count(1)==1:raise TimeoutError()
            return bytes([n])*4
        buffer.get('movie',0,segments(3),read);time.sleep(.05)
        self.assertEqual(calls.count(1),1)
        self.assertEqual(buffer.get('movie',1,segments(3),read),b'\x01'*4)
        self.assertEqual(calls.count(1),2)

    def test_stop_prevents_new_background_downloads(self):
        buffer=SegmentBuffer();self.addCleanup(buffer.close);release=threading.Event()
        def read(n):
            if n:release.wait(3)
            return bytes([n])*4
        buffer.get('movie',0,segments(),read);buffer.reset();release.set();time.sleep(.05)
        self.assertFalse(buffer.wanted);self.assertEqual(buffer.status()['cache_bytes'],0)

    def test_source_allows_parallel_http_and_renews_rejected_generation_once(self):
        gate=threading.Barrier(3,timeout=3);generations=[]
        class Transport:
            def __init__(self,c):self.expires=1000;self.url='http://example.invalid';self.generation=c
            def fetch(self,url,**kw):
                if self.generation==1:gate.wait();return {'status':403}
                return {'status':206}
        def renew():generations.append(1);return len(generations)
        source=RenewingVodSource(renew,Transport,clock=lambda:0)
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(list(pool.map(lambda _:source.fetch()['status'],range(3))),[206]*3)
        self.assertEqual(len(generations),2)

    def test_invalid_range_never_enters_cache(self):
        class Source:
            def fetch(self,**kw):return {'status':206,'headers':{'Content-Range':'bytes 8-11/12'},'body':b'bad!'}
        service=VodService(ROOT,None);self.addCleanup(service.buffer.close)
        service.sessions['movie']={'index':{'segments':segments(3),'size':12},'source':Source()}
        with self.assertRaisesRegex(ValueError,'range rejected'):service.segment('movie',0,prefetch=False)
        self.assertEqual(service.buffer.status()['cache_bytes'],0)

if __name__=='__main__':unittest.main()
