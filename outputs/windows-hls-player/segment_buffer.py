"""Bounded VOD read-ahead. Three workers, deduplicated reads, no new origins."""
import collections
import threading
from concurrent.futures import ThreadPoolExecutor


class SegmentBuffer:
    def __init__(self, workers=3, seconds=60, cache_bytes=96*1024*1024):
        self.lock=threading.RLock()
        self.pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='vod-buffer')
        self.workers=workers;self.seconds=seconds;self.limit=cache_bytes
        self.cache=collections.OrderedDict();self.bytes=0;self.jobs={}
        self.wanted={};self.failed=set();self.waiters=collections.Counter()
        self.closed=False;self.active_key=None
        self.hits=0;self.downloads=0;self.active=0;self.peak=0

    def status(self):
        with self.lock:
            return {'parallel_downloads':self.workers,'read_ahead_seconds':self.seconds,
                    'cache_bytes':self.bytes,'cache_limit_bytes':self.limit,'cache_hits':self.hits,
                    'downloads':self.downloads,'active_downloads':self.active,'peak_downloads':self.peak}

    def reset(self):
        with self.lock:
            self.active_key=None;self.wanted={};self.failed.clear()
            self.cache.clear();self.bytes=0
            for ident,future in list(self.jobs.items()):
                if not self.waiters[ident]:future.cancel()

    def close(self):
        with self.lock:self.closed=True;self.reset()
        self.pool.shutdown(wait=False,cancel_futures=True)

    def _read(self, download, number):
        with self.lock:self.active+=1;self.peak=max(self.peak,self.active)
        try:return download(number)
        finally:
            with self.lock:self.active-=1

    def _submit(self, ident, download):
        future=self.pool.submit(self._read,download,ident[1])
        self.jobs[ident]=future
        future.add_done_callback(lambda completed:self._complete(ident,completed))
        return future

    def _complete(self, ident, future):
        with self.lock:
            if self.jobs.get(ident) is not future:return
            del self.jobs[ident]
            if not future.cancelled():
                try:body=future.result()
                except Exception:self.failed.add(ident)
                else:
                    self.downloads+=1
                    if ident in self.wanted and not self.closed:
                        if len(body)>self.limit:
                            self.failed.add(ident);self._pump();return
                        previous=self.cache.pop(ident,None)
                        if previous is not None:self.bytes-=len(previous)
                        self.cache[ident]=body;self.bytes+=len(body)
                        while self.bytes>self.limit and self.cache:
                            _,removed=self.cache.popitem(last=False);self.bytes-=len(removed)
            self._pump()

    def _pump(self):
        if self.closed:return
        for ident,download in list(self.wanted.items()):
            if len(self.jobs)>=self.workers:break
            if ident not in self.cache and ident not in self.jobs and ident not in self.failed:
                self._submit(ident,download)

    def get(self, key, number, segments, download, prefetch=True):
        if not 0<=number<len(segments):raise ValueError('Unknown segment')
        ident=(key,number)
        with self.lock:
            if self.closed:raise RuntimeError('VOD buffer closed')
            # A seek/title change replaces the plan, rather than queueing the movie.
            plan={};duration=0;size=0
            for n in range(number,min(len(segments),number+32)):
                if n>number and (not prefetch or duration>=self.seconds*1000 or size+segments[n]['length']>min(64*1024*1024,self.limit)):break
                plan[(key,n)]=download
                duration+=segments[n]['duration_ms'];size+=segments[n]['length']
            self.active_key=key;self.wanted=plan
            self.failed.intersection_update(plan)
            self.waiters[ident]+=1
            try:
                for old,future in list(self.jobs.items()):
                    if old not in plan and not self.waiters[old]:future.cancel()
                if ident in self.cache:
                    self.hits+=1;self.cache.move_to_end(ident)
                    body=self.cache[ident];self._pump()
                    self.waiters[ident]-=1
                    if not self.waiters[ident]:del self.waiters[ident]
                    return body
                self.failed.discard(ident)
                # Foreground reads may queue behind the at most three active reads.
                future=self.jobs.get(ident) or self._submit(ident,download)
                self._pump()
            except BaseException:
                self.waiters[ident]-=1
                if not self.waiters[ident]:del self.waiters[ident]
                raise
        try:return future.result()
        finally:
            with self.lock:
                self.waiters[ident]-=1
                if not self.waiters[ident]:del self.waiters[ident]
