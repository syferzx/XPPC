"""Offline SLB codec, executing Ranger ARM64 routines under Unicorn on Windows.

No network access. JSON serialization in the request bootstrap is a Python stub.
The cipher, URI derivation and custom alphabet encoder/decoder run original code.
"""
from ranger_native_runtime import Runtime
import struct,json

class SlbCodec:
 def __init__(self,key):
  self.r=Runtime();r=self.r;ctx=r.arena+0x1000;head=r.arena+0x2000;node=r.arena+0x3000
  self.key=ctx+8;r.putq(ctx,0x7579d0);r.assign(self.key,key)
  r.putq(head,node);r.putq(head+8,node);r.putq(head+16,1);r.putq(node,head);r.putq(node+8,head)
  r.assign(node+0x10,b'SYNTHETIC-MEDIA');r.assign(node+0x28,b'SYNTHETIC-AUTH');r.assign(node+0x40,b'')
  r.call(0x30158c,ctx,head,result=r.arena+0x8000)
  self.bootstrap=r.string(r.arena+0x8000)
  # Execute the response parser's original literal initialization, stopping
  # before any parsing or allocations that require a server response.
  import unicorn.arm64_const as regs
  r.u.reg_write(regs.UC_ARM64_REG_SP,r.arena+0xf0000)
  r.setx(0,ctx);r.setx(1,r.arena+0x8000);r.setx(2,r.arena+0x9000)
  r.u.emu_start(0x301fa4,0x30313c,count=10000)
 def uri(self,resource):
  r=self.r;p=r.alloc(24);out=r.alloc(24);r.assign(p,resource)
  r.call(0x2fe9c0,self.key,p,result=out);return out
 def crypt(self,body,resource,decrypt=False):
  if not body or len(body)>65536:raise ValueError('Body must contain 1..65536 bytes')
  r=self.r;uri=self.uri(resource);inp=r.alloc(len(body)+1);r.u.mem_write(inp,body+b'\0');out=r.alloc(len(body)+64);size=r.alloc(8)
  code=r.call(0x678cf0 if decrypt else 0x678b14,self.key,uri,inp,len(body),out,size)
  if code:raise ValueError('Native cipher status '+str(code))
  n=r.q(size)
  if n>len(body)+32:raise ValueError('Unexpected native cipher output length')
  return bytes(r.u.mem_read(out,n))
 def alphabet(self,body,decode=False,response=True):
  if not body or len(body)>131072:raise ValueError('Invalid encoded body length')
  r=self.r;inp=r.alloc(len(body)+1);r.u.mem_write(inp,body+b'\0');out=r.alloc(len(body)*2+16);size=r.alloc(8)
  code=r.call(0x6790ac if decode else 0x678f48,0x76ccb0 if response else 0x76cc50,inp,len(body),out,size)
  if code:raise ValueError('Native alphabet status '+str(code))
  n=struct.unpack('<I',r.u.mem_read(size,4))[0]
  if n>len(body)*2+8:raise ValueError('Unexpected alphabet output length')
  return bytes(r.u.mem_read(out,n))
 def decode(self,body,path='/slb/v11/live',response=True):
  return self.crypt(self.alphabet(body,True,response),('resp:' if response else 'req:')+path,True)
 def encode(self,body,path='/slb/v11/live',response=True):
  return self.alphabet(self.crypt(body,('resp:' if response else 'req:')+path),response=response)

if __name__=='__main__':
 from pathlib import Path
 import hashlib
 codec=SlbCodec(b'0123456789abcdef0123456789abcdef')
 # This test object uses the VOD resource getter at vtable slot +0x18.
 request=json.loads(codec.decode(codec.bootstrap,path='/slb/v11/vod',response=False))
 cases=[]
 for path in ['/slb/v11/live','/slb/v11/vod']:
  for body in [b'{}',b'1234567890123456',json.dumps({'status_code':0,'media_url':'https://example.invalid/test.m3u8'}).encode()]:
   wire=codec.encode(body,path);plain=codec.decode(wire,path)
   cases.append({'path':path,'plain_bytes':len(body),'wire_bytes':len(wire),'roundtrip':plain==body})
 result={'synthetic_only':True,'network_requests':0,'bootstrap_request_decoded':request==[{'auth':'SYNTHETIC-AUTH','license':'','media_code':'SYNTHETIC-MEDIA'}],'cases':cases,'passed':all(x['roundtrip'] for x in cases)}
 Path('work/slb-codec-tests.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
