"""Bounded HTTPS DNS consensus for the existing VOD hostname, without IP pins.

No sessions or playback authorizations are sent to DNS resolvers. This validates
DNS provenance, not the identity or encryption of the existing HTTP media server.
"""
import ipaddress,json,ssl,threading,time,urllib.parse,urllib.request

HOST='yuwc.swzablvpm.com'
RESOLVERS=('https://dns.google/resolve','https://cloudflare-dns.com/dns-query')

def public_ipv4(value):
    try:address=ipaddress.ip_address(value)
    except (ValueError,TypeError) as error:raise ValueError('Invalid VOD DNS address') from error
    if (not isinstance(value,str) or address.version!=4 or not address.is_global or
            address.is_multicast or address.is_reserved):
        raise ValueError('VOD DNS destination is not public IPv4')
    return str(address)

def _name(value):
    if not isinstance(value,str) or not value.isascii() or any(c.isspace() for c in value):
        raise ValueError('Invalid DNS record name')
    return value.rstrip('.').lower()

def parse_answer(value):
    if (not isinstance(value,dict) or value.get('Status')!=0 or
            not any(isinstance(q,dict) and q.get('type')==1 and _name(q.get('name'))==HOST
                    for q in value.get('Question',[]))):
        raise ValueError('DNS response does not match VOD question')
    rows=value.get('Answer',[])
    if not isinstance(rows,list) or not 1<=len(rows)<=128:
        raise ValueError('Invalid VOD DNS answer count')
    owners={HOST};ttls=[]
    for _ in range(8):
        added=False
        for row in rows:
            if isinstance(row,dict) and row.get('type')==5 and _name(row.get('name')) in owners:
                alias=_name(row.get('data'))
                if alias not in owners:owners.add(alias);added=True
                ttl=row.get('TTL')
                if type(ttl) is not int or ttl<0:raise ValueError('Invalid DNS TTL')
                ttls.append(ttl)
        if not added:break
    addresses=[]
    for row in rows:
        if isinstance(row,dict) and row.get('type')==1 and _name(row.get('name')) in owners:
            addresses.append(public_ipv4(row.get('data')))
            ttl=row.get('TTL')
            if type(ttl) is not int or ttl<0:raise ValueError('Invalid DNS TTL')
            ttls.append(ttl)
    addresses=list(dict.fromkeys(addresses))
    if not 1<=len(addresses)<=8:raise ValueError('No bounded public VOD DNS addresses')
    return addresses,min(ttls)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def query(resolver):
    if resolver not in RESOLVERS:raise ValueError('Unknown public DNS resolver')
    context=ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(certifi.where())
    except ImportError:pass
    opener=urllib.request.build_opener(_NoRedirect(),urllib.request.HTTPSHandler(context=context))
    request=urllib.request.Request(resolver+'?'+urllib.parse.urlencode({'name':HOST,'type':'A'}),
                                   headers={'Accept':'application/dns-json'})
    with opener.open(request,timeout=6) as response:
        body=response.read(65537)
        if len(body)>65536:raise ValueError('Oversized public DNS response')
    return json.loads(body)

class VodDnsResolver:
    def __init__(self,fetch=query,clock=time.monotonic):
        self.fetch=fetch;self.clock=clock;self.lock=threading.RLock()
        self.answers=();self.expires=0
    def resolve(self,host=HOST,*,force=False):
        if host!=HOST:raise ValueError('Unexpected VOD DNS hostname')
        with self.lock:
            if not force and self.answers and self.clock()<self.expires:return list(self.answers)
            first,ttl1=parse_answer(self.fetch(RESOLVERS[0]))
            second,ttl2=parse_answer(self.fetch(RESOLVERS[1]))
            common=tuple(ip for ip in first if ip in second)
            if not common:raise ValueError('Public VOD DNS resolvers disagree')
            self.answers=common
            # Honor short TTLs; cap longer ones to observe rotations promptly.
            self.expires=self.clock()+min(300,ttl1,ttl2)
            return list(common)

_shared=VodDnsResolver()
def resolve_vod_ips(host=HOST,*,force=False):return _shared.resolve(host,force=force)
