"""Portable SLB v11 body codec. No Android, Unicorn or network access required.

Derived from local Ranger ARM64 execution; see RESULTADO.md for limitations.
"""
import base64,json,re,argparse
from pathlib import Path
import mmh3
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.padding import PKCS7

ALPHABET=b'jWB7YtC3n9iXbEkUcJl1VxF4STpQoOIaRmh2M-efAgLwPqGr6uyD5vNsdH_Kz0Z8'
STANDARD=b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
SEED=0x5f325ab6

class SlbProtocol:
 def __init__(self,key):
  if isinstance(key,bytes):key=key.decode('ascii')
  if not re.fullmatch(r'[0-9a-fA-F]{32}',key):raise ValueError('Expected Ranger internal derived SLB key: 32 hexadecimal characters, not the raw portal key')
  self.key_text=key;self.key=bytes.fromhex(key)
 def iv(self,path,response=True):
  if path not in ['/slb/v11/live','/slb/v11/vod']:raise ValueError('Unsupported resource path')
  resource=('resp:' if response else 'req:')+path
  material=('http://encrypt.io?scheme=aes-cbc-128-o2&key='+self.key_text+'&resource='+resource).encode('ascii')
  # encrypt.io is part of the hash input, not a server to contact.
  return mmh3.hash_bytes(material,SEED,x64arch=True)
 def encode(self,plain,path='/slb/v11/live',response=True):
  if not plain or len(plain)>65536:raise ValueError('Plain body must contain 1..65536 bytes')
  pad=PKCS7(128).padder();padded=pad.update(plain)+pad.finalize()
  enc=Cipher(algorithms.AES(self.key),modes.CBC(self.iv(path,response))).encryptor()
  return base64.b64encode(enc.update(padded)+enc.finalize()).translate(bytes.maketrans(STANDARD,ALPHABET)).rstrip(b'=')
 def decode(self,wire,path='/slb/v11/live',response=True):
  wire=wire.strip()
  if not wire or len(wire)>131072:raise ValueError('Invalid encoded body size')
  if any(c not in ALPHABET+b'=' for c in wire):raise ValueError('Invalid custom base64 character')
  raw=wire.translate(bytes.maketrans(ALPHABET,STANDARD));raw+=b'='*((-len(raw))%4)
  encrypted=base64.b64decode(raw,validate=True)
  if not encrypted or len(encrypted)%16:raise ValueError('Invalid AES block length')
  dec=Cipher(algorithms.AES(self.key),modes.CBC(self.iv(path,response))).decryptor()
  padded=dec.update(encrypted)+dec.finalize();unpad=PKCS7(128).unpadder()
  return unpad.update(padded)+unpad.finalize()

def url_fields(value,path='$'):
 found=[]
 if isinstance(value,dict):
  for k,v in value.items():
   child=path+'.'+k
   if k in ['media_url','play_url','idx_url','torrent_url','snapshot_url'] and isinstance(v,str) and v:found.append({'field':child,'value':v})
   found.extend(url_fields(v,child))
 elif isinstance(value,list):
  for i,v in enumerate(value):found.extend(url_fields(v,path+'['+str(i)+']'))
 return found

if __name__=='__main__':
 p=argparse.ArgumentParser(description='Decode or encode a locally saved SLB body; performs no network requests.')
 p.add_argument('operation',choices=['decode','encode']);p.add_argument('input',type=Path);p.add_argument('output',type=Path)
 p.add_argument('--key-file',type=Path,required=True);p.add_argument('--path',default='/slb/v11/live',choices=['/slb/v11/live','/slb/v11/vod']);p.add_argument('--request',action='store_true')
 a=p.parse_args();codec=SlbProtocol(a.key_file.read_text(encoding='utf8').strip())
 body=getattr(codec,a.operation)(a.input.read_bytes(),a.path,not a.request)
 a.output.write_bytes(body)
 fields=[]
 if a.operation=='decode':
  try:fields=[x['field'] for x in url_fields(json.loads(body))]
  except (ValueError,UnicodeError):pass
 print(json.dumps({'operation':a.operation,'bytes':len(body),'output':str(a.output.resolve()),'url_fields':fields,'network_requests':0}))
