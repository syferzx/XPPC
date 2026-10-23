"""Portal wire codec and bounded HTTPS client. Secrets stay in local private files.

This does not equate a video token with a portal session or renew credentials.
"""
from pathlib import Path
import base64
import json
import http.client
import re
import socket
import subprocess
import ssl
import urllib.request
import os
import struct,time,ipaddress
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.padding import PKCS7
from decode_channel_metadata import decode_value, sun_base64

ROOT = Path(os.environ.get('XUPERPC_DATA_ROOT',str(Path(__file__).resolve().parent.parent))).resolve()
PUBLIC_DNS_RESOLVER = {'host': 'dns.google', 'path': '/dns-query'}

def portal_key():
    saved = ROOT / 'work/portal-native/codec-key.private.txt'
    if saved.exists():
        return saved.read_text(encoding='utf8').strip()
    bundle=Path(os.environ.get('XUPERPC_RESOURCE_ROOT',str(ROOT)))
    settings=json.loads((bundle/'outputs/app-bootstrap.json').read_text(encoding='utf8'))
    return settings['codec_key']

class PortalCodec:
    def __init__(self, key_text=None):
        self.key_text = key_text if key_text is not None else portal_key()

    def encode(self, value):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf8')
        pad = PKCS7(64).padder()
        padded = pad.update(raw) + pad.finalize()
        enc = Cipher(TripleDES(sun_base64(self.key_text)[:24]), modes.ECB()).encryptor()
        return base64.b64encode(enc.update(padded) + enc.finalize()).hex().encode('ascii')

    def decode(self, body):
        text = body.decode('utf8').strip()
        # Some errors are ordinary JSON, while normal responses use the wire codec.
        if text.startswith(('{', '[')):
            return json.loads(text)
        return json.loads(decode_value(text, self.key_text))

class PortalClient:
    def __init__(self, hosts, headers, metadata=None, resolved=None):
        if not hosts or any(not re.fullmatch(r'[A-Za-z0-9.-]+', h) for h in hosts):
            raise ValueError('Expected APK portal hostnames')
        self.hosts = tuple(dict.fromkeys(hosts))
        self.headers = dict(headers)
        self.metadata = dict(metadata or {})
        self.codec = PortalCodec()
        self.resolved = dict(resolved or {})
        self.dns_resolver=dict(PUBLIC_DNS_RESOLVER)
        self.dns_attempts={}

    def refresh_dns(self,host,context):
        """Resolve this portal through the configured public HTTPS DNS service."""
        settings=self.dns_resolver
        if host not in self.hosts or not settings:raise ConnectionError('No configured portal resolver')
        if time.monotonic()-self.dns_attempts.get(host,-1000)<60:raise ConnectionError('Portal DNS refresh cooldown')
        self.dns_attempts[host]=time.monotonic()
        resolver=settings.get('host','');path=settings.get('path','')
        if not re.fullmatch(r'[A-Za-z0-9.-]+',resolver) or not re.fullmatch(r'/[A-Za-z0-9/_-]{1,180}',path):
            raise ValueError('Invalid configured DNS service')
        identity=os.urandom(2);question=b''.join(bytes([len(part)])+part.encode('ascii') for part in host.split('.'))+b'\0'+struct.pack('>HH',1,1)
        query=identity+struct.pack('>HHHHH',0x0100,1,0,0,0)+question
        encoded=base64.urlsafe_b64encode(query).decode().rstrip('=')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        request=urllib.request.Request('https://'+resolver+path+'?dns='+encoded,headers={'Accept':'application/dns-message'})
        with urllib.request.build_opener(NoRedirect,urllib.request.HTTPSHandler(context=context)).open(request,timeout=5) as response:
            message=response.read(65537)
        if not 12<=len(message)<=65536 or message[:2]!=identity:raise ValueError('Invalid DNS response')
        flags,questions,answers,_,_=struct.unpack_from('>HHHHH',message,2)
        if not flags&0x8000 or flags&0x020f or questions!=1 or answers>64:raise ValueError('DNS answer rejected')
        def skip_name(offset):
            for _ in range(128):
                if offset>=len(message):raise ValueError('Truncated DNS name')
                size=message[offset];offset+=1
                if size==0:return offset
                if size&0xc0==0xc0:
                    if offset>=len(message):raise ValueError('Truncated DNS pointer')
                    return offset+1
                if size>63 or offset+size>len(message):raise ValueError('Invalid DNS label')
                offset+=size
            raise ValueError('DNS name too long')
        offset=skip_name(12)+4;addresses=[]
        for _ in range(answers):
            offset=skip_name(offset)
            if offset+10>len(message):raise ValueError('Truncated DNS record')
            typ,cls,ttl,size=struct.unpack_from('>HHIH',message,offset);offset+=10
            if offset+size>len(message):raise ValueError('Truncated DNS data')
            if typ==1 and cls==1 and size==4:
                address=ipaddress.ip_address(message[offset:offset+4])
                if address.is_global and str(address) not in addresses:addresses.append(str(address))
            offset+=size
        if not addresses:raise ConnectionError('Portal DNS returned no public addresses')
        self.resolved[host]=addresses[:4]
        return addresses[:4]

    def unpack(self, decoded):
        """The outer envelope is JSON; its data can have another encrypted layer."""
        if isinstance(decoded, dict) and isinstance(decoded.get('data'), str):
            value = decoded['data']
            if re.fullmatch(r'[0-9A-Fa-f]+', value or ''):
                try:
                    return {**decoded, 'data': self.codec.decode(value.encode())}
                except (ValueError, UnicodeError):
                    pass
        return decoded

    def request(self, endpoint, params, host_index=0):
        declared = json.loads((ROOT / 'outputs/rutas-portal.json').read_text(encoding='utf8'))
        allowed = {p[p.index('/api/portalCore/'):] for p in declared}
        if endpoint not in allowed:
            raise ValueError('Unexpected portal endpoint')
        payload = dict(params)
        payload.update(self.metadata)
        request = urllib.request.Request('https://' + self.hosts[host_index] + endpoint,
                                        data=self.codec.encode(payload),
                                        headers={'Content-Type': 'application/json;charset=utf-8',
                                                 **self.headers}, method='POST')
        # Preserve TLS verification and never redirect credentials to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        context = ssl.create_default_context()
        try:
            import certifi
            context.load_verify_locations(certifi.where())
        except ImportError:
            pass
        host=self.hosts[host_index];failure=None;connection=None
        for fresh in (False,True):
            if fresh:
                if not self.dns_resolver:break
                addresses=self.refresh_dns(host,context)
            else:addresses=self.resolved.get(host) or [None]
            for address in addresses[:4]:
                candidate=http.client.HTTPSConnection(host,timeout=3,context=context)
                if address is not None:
                    candidate._create_connection=lambda target,timeout=3,source_address=None,ip=address:socket.create_connection((ip,target[1]),timeout,source_address)
                try:
                    # Authenticate TLS before sending any application headers or body.
                    candidate.connect()
                    connection=candidate
                    if address is not None:self.resolved[host]=[address]+[ip for ip in addresses if ip!=address]
                    break
                except OSError as error:
                    failure=error;candidate.close()
            if connection is not None:break
        if connection is None:raise failure or ConnectionError('Portal connection unavailable')
        try:
            connection.timeout=15
            if connection.sock is not None:connection.sock.settimeout(15)
            # A request already sent is never replayed on a read timeout.
            connection.request('POST',endpoint,body=request.data,headers=dict(request.header_items()))
            response=connection.getresponse();body=response.read(4*1024*1024+1)
            if len(body)>4*1024*1024:raise ValueError('Portal response exceeds limit')
            if response.status!=200:raise urllib.error.HTTPError(request.full_url,response.status,'Portal HTTP error',response.headers,None)
            return response.status,body,self.unpack(self.codec.decode(body))
        finally:connection.close()
