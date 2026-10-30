"""Bounded ARM64 runtime for offline protocol experiments. No native networking."""
from pathlib import Path
import sys,io,struct,json,collections,re,os
if not os.environ.get('XUPERPC_PORTABLE_ROOT'):sys.path.insert(0,str(Path('work/analysis-tools').resolve()))
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
import unicorn.arm64_const as regs
class Cell:
 def __init__(self,value=None):self.value=value
class Runtime:
 def __init__(self):
  self.binary=(Path(os.environ.get('XUPERPC_RESOURCE_ROOT','.'))/'outputs/xuper-apk/lib/arm64-v8a/libranger-jni.so').read_bytes();self.elf=ELFFile(io.BytesIO(self.binary));self.u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
  segs=[s for s in self.elf.iter_segments() if s['p_type']=='PT_LOAD'];lo=min(s['p_vaddr'] for s in segs)&~4095;hi=(max(s['p_vaddr']+s['p_memsz'] for s in segs)+4095)&~4095
  self.u.mem_map(lo,hi-lo)
  for s in segs:self.u.mem_write(s['p_vaddr'],s.data())
  for sec in self.elf.iter_sections():
   if sec['sh_type']=='SHT_RELA':
    for r in sec.iter_relocations():
     if r['r_info_type']==1027:self.putq(r['r_offset'],r['r_addend'])
  self.arena=0x10000000;self.u.mem_map(self.arena,0x100000);self.heap=0x11000000;self.u.mem_map(self.heap,0x2000000);self.next=self.heap
  self.stop=self.arena+0xff000;self.imports={};self.cells={};self.seen=collections.Counter();self.trace=collections.deque(maxlen=60);self.extra={}
  syms=self.elf.get_section_by_name('.dynsym');plt=self.elf.get_section_by_name('.plt');rela=self.elf.get_section_by_name('.rela.plt')
  for i,r in enumerate(rela.iter_relocations()):self.imports[plt['sh_addr']+32+16*i]=syms.get_symbol(r['r_info_sym']).name
  self.u.hook_add(UC_HOOK_CODE,self.hook)
 def x(self,i):return self.u.reg_read(getattr(regs,'UC_ARM64_REG_X'+str(i)))
 def setx(self,i,v):self.u.reg_write(getattr(regs,'UC_ARM64_REG_X'+str(i)),v&0xffffffffffffffff)
 def putq(self,a,v):self.u.mem_write(a,struct.pack('<Q',v))
 def q(self,a):return struct.unpack('<Q',self.u.mem_read(a,8))[0]
 def alloc(self,n):
  if n<0 or n>0x1000000:raise RuntimeError('allocation outside bounds')
  a=self.next;self.next+=(n+15)&~15
  if self.next>=self.heap+0x2000000:raise RuntimeError('heap exhausted')
  return a
 def cstr(self,a,limit=100000):
  out=bytearray()
  for i in range(0,limit,128):
   b=bytes(self.u.mem_read(a+i,128));p=b.find(b'\0')
   if p>=0:return bytes(out)+b[:p]
   out.extend(b)
  raise RuntimeError('unterminated string')
 def string(self,a):
  first=self.u.mem_read(a,1)[0]
  if first&1:return bytes(self.u.mem_read(self.q(a+16),self.q(a+8)))
  return bytes(self.u.mem_read(a+1,first>>1))
 def assign(self,a,data):
  if isinstance(data,str):data=data.encode()
  self.u.mem_write(a,bytes(24))
  if len(data)<=22:self.u.mem_write(a,bytes([len(data)*2])+data+b'\0')
  else:
   p=self.alloc(len(data)+1);self.u.mem_write(p,data+b'\0');self.u.mem_write(a,struct.pack('<QQQ',(len(data)+1)|1,len(data),p))
  return a
 def cell(self,a):return self.cells.setdefault(a,Cell())
 def export(self,v):
  if isinstance(v,Cell):return self.export(v.value)
  if isinstance(v,dict):return {k:self.export(x) for k,x in v.items()}
  if isinstance(v,list):return [self.export(x) for x in v]
  return v
 def finish(self,value=None):
  if value is not None:self.setx(0,value)
  self.u.reg_write(regs.UC_ARM64_REG_PC,self.x(30))
 def hook(self,u,a,size,user):
  self.trace.append(a)
  if a in self.extra:self.extra[a](self);return
  x=[self.x(i) for i in range(9)]
  if a in [0x73c50c,0x73c780,0x73e358,0x73cb9c,0x73e3ac,0x73caf8,0x73f8c4,0x73f8dc,0x73f8c0]:
   self.seen['json:'+hex(a)]+=1
   if a==0x73c50c:self.cells[x[0]]=Cell([] if x[1]==6 else {} if x[1]==7 else None)
   elif a==0x73c780:self.cells[x[0]]=Cell(self.string(x[1]).decode())
   elif a==0x73e358:
    c=self.cell(x[0]);key=self.cstr(x[1]).decode()
    if c.value is None:c.value={}
    if key not in c.value:c.value[key]=Cell()
    p=self.alloc(32);self.cells[p]=c.value[key];self.finish(p);return
   elif a==0x73cb9c:self.cell(x[0]).value=self.cell(x[1]).value
   elif a==0x73e3ac:
    c=self.cell(x[0])
    if c.value is None:c.value=[]
    c.value.append(Cell(self.cell(x[1]).value))
   elif a==0x73f8dc:
    self.last_json=self.export(self.cell(x[1]));self.assign(x[8],json.dumps(self.last_json,separators=(',',':')))
   self.finish(x[0]);return
  if a not in self.imports:return
  name=self.imports[a];self.seen[name]+=1
  if name in ['malloc','_Znwm','_Znam']:self.finish(self.alloc(x[0]));return
  if name=='calloc':self.finish(self.alloc(x[0]*x[1]));return
  if name in ['free','_ZdlPv','_ZdaPv','__cxa_atexit','__cxa_finalize'] or name.startswith('pthread_mutex_'):self.finish(0);return
  if name in ['memcpy','memmove']:
   if x[2]>0x1000000:raise RuntimeError('copy outside bounds')
   u.mem_write(x[0],bytes(u.mem_read(x[1],x[2])));self.finish(x[0]);return
  if name=='memset':u.mem_write(x[0],bytes([x[1]&255])*x[2]);self.finish(x[0]);return
  if name=='strlen':self.finish(len(self.cstr(x[0])));return
  if name=='strstr':
   idx=self.cstr(x[0]).find(self.cstr(x[1]));self.finish(x[0]+idx if idx>=0 else 0);return
  if name in ['strchr','strrchr']:
   data=self.cstr(x[0])+b'\0';needle=bytes([x[1]&255]);idx=data.find(needle) if name=='strchr' else data.rfind(needle)
   self.finish(x[0]+idx if idx>=0 else 0);return
  if name=='snprintf':
   fmt=self.cstr(x[2]);parts=[];at=0;arg=3
   for m in re.finditer(rb'%(?:0?[0-9]+)?(?:ll|l|z)?[duxXsc%]',fmt):
    parts.append(fmt[at:m.start()]);spec=m.group();at=m.end()
    if spec==b'%%':parts.append(b'%');continue
    if arg>7:raise RuntimeError('snprintf argument bounds')
    v=x[arg];arg+=1;kind=spec[-1:]
    if kind==b's':v=self.cstr(v)
    elif kind==b'd' and v>>63:v-=1<<64
    normal=re.sub(rb'(ll|l|z)(?=[duxXsc]$)',b'',spec)
    parts.append(normal%v)
   parts.append(fmt[at:]);data=b''.join(parts)
   if x[1]:u.mem_write(x[0],data[:max(0,x[1]-1)]+b'\0')
   self.finish(len(data));return
  if name in ['strcmp','strncmp','memcmp']:
   aa=bytes(u.mem_read(x[0],x[2])) if name=='memcmp' else self.cstr(x[0]);bb=bytes(u.mem_read(x[1],x[2])) if name=='memcmp' else self.cstr(x[1])
   if name=='strncmp':aa=aa[:x[2]];bb=bb[:x[2]]
   self.finish((aa>bb)-(aa<bb));return
  if name=='memchr':
   data=bytes(u.mem_read(x[0],x[2]));idx=data.find(bytes([x[1]&255]));self.finish(x[0]+idx if idx>=0 else 0);return
  if 'basic_string' in name:
   if 'D1Ev' in name or 'D2Ev' in name:self.finish(x[0]);return
   if '6__initEPKcm' in name:self.finish(self.assign(x[0],bytes(u.mem_read(x[1],x[2]))));return
   if 'aSERKS5_' in name or 'C1ERKS5_' in name or 'C2ERKS5_' in name:self.finish(self.assign(x[0],self.string(x[1])));return
   if '6assignEPKc' in name:self.finish(self.assign(x[0],self.cstr(x[1])));return
   if '6appendEPKcm' in name:self.finish(self.assign(x[0],self.string(x[0])+bytes(u.mem_read(x[1],x[2]))));return
   if '6appendEPKc' in name:self.finish(self.assign(x[0],self.string(x[0])+self.cstr(x[1])));return
   if '6insertEmPKc' in name:
    s=self.string(x[0]);self.finish(self.assign(x[0],s[:x[1]]+self.cstr(x[2])+s[x[1]:]));return
   if name.startswith('_ZNSt6__ndk1pl') and 'EPKS6_RKS9_' in name:self.assign(x[8],self.cstr(x[0])+self.string(x[1]));self.finish();return
  raise RuntimeError('Unsupported import '+name+' at '+hex(a))
 def call(self,fn,*args,result=None,count=1000000):
  for i,v in enumerate(args):self.setx(i,v)
  if result is not None:self.setx(8,result)
  self.u.reg_write(regs.UC_ARM64_REG_SP,self.arena+0xf0000);self.setx(30,self.stop)
  self.u.emu_start(fn,self.stop,timeout=15000000,count=count)
  if self.u.reg_read(regs.UC_ARM64_REG_PC)!=self.stop:raise RuntimeError('Call did not return: '+hex(self.u.reg_read(regs.UC_ARM64_REG_PC)))
  return self.x(0)
