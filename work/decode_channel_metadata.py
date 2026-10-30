from pathlib import Path
import base64,re,json,subprocess
from cryptography.hazmat.primitives.ciphers import Cipher,modes
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.padding import PKCS7
def sun_base64(text):
 alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
 out=bytearray()
 text=text.replace('\r','').replace('\n','')
 for pos in range(0,len(text),4):
  atom=text[pos:pos+4];v=[alphabet.find(c) for c in atom];v+= [-1]*(4-len(v))
  out.append(((v[0]<<2)&252)|((v[1]>>4)&3))
  if len(atom)>2 and atom[2]!='=':out.append(((v[1]<<4)&240)|((v[2]>>2)&15))
  if len(atom)>3 and atom[3]!='=':out.append(((v[2]<<6)&192)|(v[3]&63))
 return bytes(out)
def decode_value(text,key_text):
 key=sun_base64(key_text)[:24];ciphertext=base64.b64decode(bytes.fromhex(text).decode())
 decrypt=Cipher(TripleDES(key),modes.ECB()).decryptor();padded=decrypt.update(ciphertext)+decrypt.finalize()
 unpad=PKCS7(64).unpadder();return unpad.update(padded)+unpad.finalize()
