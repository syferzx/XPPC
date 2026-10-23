"""Original live v9 auth builder; bounded response decode, no native network."""
import base64,json
from ranger_native_runtime import Runtime
from portal_client import portal_key
from slb_codec import SlbCodec

class LiveV9Protocol:
    def __init__(self):
        r=self.r=Runtime();self.ctx=r.alloc(64);key=r.alloc(24);r.assign(key,portal_key());r.call(0x2fee80,self.ctx,key);r.putq(self.ctx,0x757950)
        inp=r.alloc(24);out=r.alloc(128);r.assign(inp,'SYNTHETIC-AUTH');r.call(0x2ff160,self.ctx,inp,result=out)
        r.assign(inp,'A'*64)
        def stop(vm):raise RuntimeError('stop-before-response-decoder')
        r.extra[0x6790ac]=stop
        try:r.call(0x2ff7bc,self.ctx,inp,out,count=1000000)
        except RuntimeError as ex:
            if str(ex)!='stop-before-response-decoder':raise
        finally:r.extra.pop(0x6790ac,None)
        self.alphabet=bytes(r.u.mem_read(0x76cb00,64));self.crypto=SlbCodec(r.string(self.ctx+8))
    def encode(self,plain,path,response=False):
        if path!='/slb/v9/live' or response:raise ValueError('Only live v9 request supported')
        entries=json.loads(plain)
        if len(entries)!=1:raise ValueError('Live request requires one current grant')
        # Unlike VOD v11's list, the original TV v9 builder accepts the current
        # auth string. The channel license is still sent in Content-License.
        r=self.r;inp=r.alloc(24);out=r.alloc(24);r.assign(inp,entries[0]['auth']);r.call(0x2ff160,self.ctx,inp,result=out)
        return r.string(out)
    def decode(self,wire,path,response=True):
        if path!='/slb/v9/live' or not response or not 0<len(wire)<=131072:raise ValueError('Invalid live v9 response')
        encoded=wire.translate(bytes.maketrans(self.alphabet,b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'))
        data=base64.b64decode(encoded+b'='*((-len(encoded))%4),validate=True)
        return self.crypto.crypt(data,'resp:'+path,True)
