"""Expose only public original artwork; never session-bearing image URLs."""
import urllib.parse

# Public image origins observed in the original catalog and checked with TLS.
IMAGE_HOSTS=frozenset(('dio3ka.lpsyujwj.xyz','joqotx.p27i1en9.com',
                      'cftpbe.39114gi1.com','rzpncf.jhgc9hga.xyz','jhxdvb.o8za4kpx.xyz'))
# The legacy origin fails; its same object path is served by both current CDNs.
IMAGE_MIRRORS={'sqacjy.s5lm5aydc.xyz':'joqotx.p27i1en9.com'}

def public_image(value):
    if not isinstance(value,str):return None
    try:u=urllib.parse.urlsplit(value);port=u.port
    except ValueError:return None
    if (u.scheme!='https' or u.hostname not in IMAGE_HOSTS|IMAGE_MIRRORS.keys() or port not in (None,443)
        or u.username or u.password or u.query or u.fragment or not u.path.startswith('/public/images/')):return None
    if u.hostname in IMAGE_MIRRORS:
        return urllib.parse.urlunsplit(('https',IMAGE_MIRRORS[u.hostname],u.path,'',''))
    return value

def artwork(asset):
    posters=asset.get('posterList') or []
    def find(kind):return next((url for p in posters if p.get('fileType')==kind and (url:=public_image(p.get('fileUrl')))),None)
    cover=find('icon') or public_image(asset.get('posterUrl')) or find('poster')
    return {'poster_url':cover,'backdrop_url':find('poster') or find('stage') or cover}
