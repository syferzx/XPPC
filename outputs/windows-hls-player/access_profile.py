"""Use only this installation's media profile and verified provider destinations."""
import json
import ipaddress
from pathlib import Path

TV_ROUTES={
    ('eijbs.gn5h3hxar2k.com','206.253.89.122'):('http','23.227.144.242',44822),
    ('auuy2136a.xh09je1qy.com','206.253.89.124'):('http','208.115.233.59',23455),
}

def vod_route(root):
    value=json.loads((Path(root)/'work/portal-native/media-client.private.json').read_text(encoding='utf8'))
    key=(value.get('vod_slb_host'),value.get('vod_slb_ip'))
    if value.get('schema')!=1 or key[0]!='yuwc.swzablvpm.com':
        raise ValueError('VOD destination has not been validated')
    # The saved IP is legacy metadata, not a connection pin. Live destinations
    # come from vod_dns; retain validation for older profiles and diagnostics.
    try:address=ipaddress.ip_address(key[1])
    except (ValueError,TypeError) as error:raise ValueError('Invalid historical VOD address') from error
    if address.version!=4 or not address.is_global or address.is_multicast or address.is_reserved:raise ValueError('Invalid historical VOD address')
    return key

def tv_route(root):
    path=Path(root)/'work/portal-native/media-client.private.json'
    if not path.exists():raise ValueError('Installation media profile missing')
    value=json.loads(path.read_text(encoding='utf8'))
    key=(value.get('tv_slb_host'),value.get('tv_slb_ip'))
    if key not in TV_ROUTES:raise ValueError('TV destination has not been validated')
    return *key,TV_ROUTES[key]

def media_headers(root,kind):
    root=Path(root);profile=root/'work/portal-native/media-client.private.json'
    if profile.exists():
        value=json.loads(profile.read_text(encoding='utf8'))
        if value.get('schema')!=1:raise ValueError('Unsupported media profile')
        headers={k.lower():v for k,v in value['headers'].items()}
        if set(headers)!={'app','app-version','ranger-id','user-agent'}:raise ValueError('Unexpected persistent media headers')
        if not all(isinstance(v,str) and v and '\r' not in v and '\n' not in v for v in headers.values()):raise ValueError('Invalid media headers')
        return headers
    raise ValueError('Installation media profile missing')

def tv_template(root):
    root=Path(root)
    _,_,origin=tv_route(root);address=origin[1]+':'+str(origin[2])
    headers={**media_headers(root,'tv'),'host':address,'content-auth':'','content-license':''}
    return {'url':'http://'+address+'/live/','headers':headers,'headers_original':list(headers.items())}
