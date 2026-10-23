"""Ordinary first-install enrollment with a persistent installation identity.

No copied session, identity rotation, entitlement changes, or rejected-request retries.
"""
import hashlib,json,platform,secrets,shutil,uuid
from pathlib import Path

class SetupError(RuntimeError):pass

def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8');temporary.replace(path)

def configure(data_root,bundle,client_factory=None):
    root=Path(data_root);bundle=Path(bundle);directory=root/'work/portal-native';directory.mkdir(parents=True,exist_ok=True)
    settings=read(bundle/'outputs/app-bootstrap.json')
    session_file=directory/'active-data.private.json'
    if session_file.exists():
        session=read(session_file)
        complete=all((directory/name).exists() for name in ['client-profile.private.json','media-client.private.json'])
        if complete and session.get('userToken') and session.get('userId'):
            profile_path=directory/'client-profile.private.json';profile=read(profile_path)
            public_dns={'host':'dns.google','path':'/dns-query'}
            if profile.get('dns_resolver')!=public_dns:
                profile.update(dns_resolver=public_dns,resolved={});write(profile_path,profile)
            media_path=directory/'media-client.private.json';media=read(media_path)
            if 'vod_slb_host' not in media and 'vod_slb_ip' not in media:
                media.update(vod_slb_host='yuwc.swzablvpm.com',vod_slb_ip='66.225.197.106');write(media_path,media)
            return {'ready':True,'reused_session':True}
        raise SetupError('La sesión guardada necesita revisión; no se creará otra identidad.')
    identity_file=directory/'installation.private.json'
    if not identity_file.exists():write(identity_file,{'schema':1,'installation_id':uuid.uuid4().hex,'ranger_id':secrets.token_urlsafe(25)})
    identity=read(identity_file)
    if identity.get('schema')!=1 or len(identity.get('installation_id',''))!=32:raise SetupError('El identificador guardado no es válido.')
    (directory/'codec-key.private.txt').write_text(settings['codec_key'],encoding='utf8')
    (root/'outputs').mkdir(exist_ok=True)
    if not (root/'outputs/rutas-portal.json').exists():shutil.copyfile(bundle/'outputs/rutas-portal.json',root/'outputs/rutas-portal.json')
    metadata=dict(settings['metadata'])
    metadata.update(sysVersion=platform.release(),hardwareInfo=platform.machine(),model='Windows PC',product='XuperPC',cpu=platform.machine(),B29='',reserve1='',sn='',portalCode='',deviceToken='',drmId='',sdkVer='0')
    params={key:'' for key in ['display','verId','cpuAbi','hardware','manufacturer','fingerprint','host','device','board','tags','androidId','diskInfo','ramSize','romSize','gatewayMac','cpuId']}
    params.update(display=platform.version(),brand='Windows',cpuAbi=platform.machine(),hardware=platform.machine(),manufacturer='Windows PC',device='XuperPC',serialNumber=identity['installation_id'],wifiMac='02:00:00:00:00:00',etheMac='02:00:00:00:00:00')
    if client_factory is None:
        from portal_client import PortalClient
        client_factory=PortalClient
    client=client_factory(settings['hosts'],settings['headers'],metadata,settings.get('resolved'))
    client.dns_resolver={'host':'dns.google','path':'/dns-query'}
    ledger_file=directory/'enrollment.private.json';ledger=read(ledger_file) if ledger_file.exists() else {}
    def once(stage,endpoint,body):
        response_file=directory/(stage+'-response.private.json')
        if response_file.exists():return read(response_file)
        if ledger.get(stage+'_requested'):raise SetupError('La consulta inicial quedó incompleta. No se repetirá automáticamente.')
        ledger[stage+'_requested']=True;write(ledger_file,ledger)
        _,_,response=client.request(endpoint,body)
        write(response_file,response)
        return response
    token_response=once('sn','/api/portalCore/v3/snToken',params)
    token=token_response.get('data')
    if str(token_response.get('returnCode'))!='0' or not isinstance(token,dict) or not isinstance(token.get('snToken'),str) or not token['snToken']:
        raise SetupError('El servicio no autorizó esta instalación. Puede requerir registro o inicio de sesión.')
    metadata['sn']=token.get('sn') or hashlib.md5((token['snToken']+settings['sn_suffix']).encode()).hexdigest()
    client.metadata.update(metadata)
    write(directory/'client-profile.private.json',{'schema':1,'hosts':settings['hosts'],'headers':settings['headers'],'metadata':metadata,'resolved':settings.get('resolved',{}),'dns_resolver':settings.get('dns_resolver'),'device_params':params})
    response=once('active','/api/portalCore/v8/active',{'snToken':token['snToken'],'authVersion':'','authCode':'','macAddr':'02:00:00:00:00:00','reserve1':'','openNum':1,'channel':'default','matadata':'','signdata':''})
    session=response.get('data')
    if str(response.get('returnCode'))!='0' or not isinstance(session,dict) or not session.get('userId') or not session.get('userToken') or not session.get('portalCodeList'):
        raise SetupError('El servicio no entregó una sesión utilizable. Puede requerir registro o inicio de sesión.')
    headers={**settings['media_headers'],'ranger-id':identity['ranger_id']}
    write(directory/'media-client.private.json',{'schema':1,'headers':headers,'tv_slb_host':settings['tv_slb_host'],'tv_slb_ip':settings['tv_slb_ip'],'vod_slb_host':'yuwc.swzablvpm.com','vod_slb_ip':'66.225.197.106'})
    write(session_file,session)
    return {'ready':True,'reused_session':False}
