"""SLB HTTP framing verified against Ranger's offline request assembly.

Wire crypto is supplied separately; this module does not claim playback works.
"""
import http.client
import json
import re
import socket
import ssl
import urllib.parse


class SlbRejected(RuntimeError):
    def __init__(self, status, body_bytes):
        self.status = status
        self.body_bytes = body_bytes
        super().__init__('SLB request rejected: HTTP ' + str(status))


def target(address, kind, wire,version=11):
    if kind not in ('vod','live'):
        raise ValueError('Unsupported SLB resource')
    parsed = urllib.parse.urlsplit(address if '://' in address else 'https://' + address)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username or parsed.password or parsed.path not in ('', '/') or
            parsed.query or parsed.fragment):
        raise ValueError('Expected a provider CDN address')
    wire = wire.decode('ascii') if isinstance(wire, bytes) else wire
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,131072}', wire):
        raise ValueError('Invalid SLB wire alphabet')
    if version not in (9,11):raise ValueError('Unsupported SLB version')
    return parsed, '/slb/v'+str(version)+'/' + kind + '?auth=' + wire


class SlbHttpClient:
    def __init__(self, protocol, resolver, connection_factory=None, extra_headers=None,version=11):
        self.protocol = protocol
        self.resolver = resolver
        self.connection_factory = connection_factory or self.connection
        self.extra_headers = extra_headers or {}
        self.version=version
        if any(k.lower() not in ['app','app-version','ranger-id','content-license'] or '\r' in k+v or '\n' in k+v for k,v in self.extra_headers.items()):
            raise ValueError('Unsupported or malformed app header')

    def connection(self, parsed, ip):
        if parsed.scheme == 'https':
            context = ssl.create_default_context()
            try:
                import certifi
                context.load_verify_locations(certifi.where())
            except ImportError:
                pass
            conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                               timeout=10, context=context)
        else:
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=10)
        # Retain the provider hostname for SNI, certificate and Host; use its DNS answer.
        conn._create_connection = lambda address, timeout=10, source_address=None: socket.create_connection(
            (ip, address[1]), timeout, source_address)
        return conn

    def request(self, address, kind, entries):
        if not isinstance(entries, list) or not 1 <= len(entries) <= 40:
            raise ValueError('Expected 1..40 authorized entries')
        resource = '/slb/v'+str(self.version)+'/' + kind
        plain = json.dumps(entries, separators=(',', ':'), ensure_ascii=False).encode('utf8')
        wire = self.protocol.encode(plain, resource, response=False)
        parsed, path = target(address, kind, wire,self.version)
        answers = self.resolver(parsed.hostname)
        if not answers:
            raise ValueError('No provider DNS answers')
        conn = self.connection_factory(parsed, answers[0])
        try:
            host = parsed.hostname + (':' + str(parsed.port) if parsed.port else '')
            conn.putrequest('GET', path, skip_host=True, skip_accept_encoding=True)
            conn.putheader('Host', host)
            conn.putheader('Connection', 'close')
            conn.putheader('Content-Type', 'application/octet-stream')
            conn.putheader('User-Agent', 'Ranger/4.9.4-17294ac0')
            for key,value in self.extra_headers.items():conn.putheader(key,value)
            conn.endheaders()
            response = conn.getresponse()
            body = response.read(131073)
            if len(body) > 131072:
                raise ValueError('SLB response exceeds limit')
            if response.status != 200:
                raise SlbRejected(response.status, len(body))
            if not body:
                raise ValueError('Empty SLB response')
            try:
                value = json.loads(body)
            except (ValueError, UnicodeError):
                value = json.loads(self.protocol.decode(body, resource))
            if not isinstance(value, (dict, list)):
                raise ValueError('Invalid SLB response')
            return value
        finally:
            conn.close()
