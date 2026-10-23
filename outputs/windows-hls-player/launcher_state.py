"""Verify the profile's loopback instance before opening a browser."""
import http.client
import json
import os
from pathlib import Path
import time
import urllib.parse


def healthy(saved,diagnostics=None):
    connection=None
    if diagnostics is not None:diagnostics['reason']='invalid_metadata'
    try:
        url=urllib.parse.urlsplit(saved['url'])
        if diagnostics is not None:diagnostics.update(scheme=url.scheme,host=url.hostname,port=url.port,path=url.path,pid_type=type(saved.get('pid')).__name__,pid=saved.get('pid'),instance_length=len(saved.get('instance','')) if isinstance(saved.get('instance'),str) else None)
        if (url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port or
                url.path!='/' or url.query or url.fragment or url.username or url.password):return False
        if type(saved.get('pid')) is not int or saved['pid']<=0:return False
        if not isinstance(saved.get('instance'),str) or len(saved['instance'])!=32:return False
        connection=http.client.HTTPConnection('127.0.0.1',url.port,timeout=1)
        connection.request('GET','/api/launcher/status')
        response=connection.getresponse();body=response.read(4097)
        if diagnostics is not None:diagnostics.update(status=response.status,reason='unexpected_response')
        if response.status!=200 or len(body)>4096:return False
        result=json.loads(body)
        if diagnostics is not None:diagnostics.update(reason='instance_mismatch',application_matches=result.get('application')=='XuperPC',pid_matches=result.get('pid')==saved['pid'],instance_matches=result.get('instance')==saved['instance'])
        return (result.get('application')=='XuperPC' and result.get('pid')==saved['pid']
                and result.get('instance')==saved['instance'])
    except (OSError,ValueError,KeyError,TypeError,AttributeError,http.client.HTTPException) as error:
        if diagnostics is not None:diagnostics.update(error=type(error).__name__,errno=getattr(error,'errno',None),winerror=getattr(error,'winerror',None))
        return False
    finally:
        if connection:connection.close()


def owns_local_listener(saved):
    """Windows-only corroboration if an HTTP self-check cannot connect."""
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    import socket
    process=None
    try:
        url=urllib.parse.urlsplit(saved['url']);engine=Path(saved['engine'])
        if (url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port or url.path!='/' or url.query or url.fragment or url.username or url.password):return False
        if type(saved.get('pid')) is not int or saved['pid']<=0:return False
        if not engine.is_absolute() or engine.name.lower()!='python.exe' or engine.parent.name.lower()!='engine':return False
        if not (engine.parent/'app/portable.py').is_file():return False
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        process=kernel.OpenProcess(0x1000,False,saved['pid'])
        if not process:return False
        name=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(process,0,name,ctypes.byref(length)):return False
        if os.path.normcase(os.path.realpath(name.value))!=os.path.normcase(os.path.realpath(engine)):return False
        class Row(ctypes.Structure):
            _fields_=[(key,wintypes.DWORD) for key in ('state','local_addr','local_port','remote_addr','remote_port','pid')]
        api=ctypes.WinDLL('iphlpapi').GetExtendedTcpTable
        api.argtypes=[ctypes.c_void_p,ctypes.POINTER(wintypes.DWORD),wintypes.BOOL,wintypes.ULONG,wintypes.ULONG,wintypes.ULONG]
        size=wintypes.DWORD();api(None,ctypes.byref(size),False,2,3,0)
        buffer=ctypes.create_string_buffer(size.value)
        if api(buffer,ctypes.byref(size),False,2,3,0)!=0:return False
        count=wintypes.DWORD.from_buffer(buffer).value
        if 4+count*ctypes.sizeof(Row)>len(buffer):return False
        loopback=int.from_bytes(socket.inet_aton('127.0.0.1'),'little')
        return any(row.pid==saved['pid'] and row.state==2 and row.local_addr==loopback and socket.ntohs(row.local_port & 65535)==url.port
                   for row in (Row.from_buffer(buffer,4+i*ctypes.sizeof(Row)) for i in range(count)))
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return False
    finally:
        if process:kernel.CloseHandle(process)


def wait_for_instance(metadata,timeout=20):
    deadline=time.monotonic()+timeout
    while True:
        diagnostic={}
        try:
            saved=json.loads(metadata.read_text(encoding='utf8'))
            if healthy(saved,diagnostic):return saved
            diagnostic['metadata_path']=str(metadata.resolve())
            diagnostic['metadata_bytes']=metadata.stat().st_size
            if diagnostic.get('error') in ('OSError','PermissionError','ConnectionRefusedError','TimeoutError','RemoteDisconnected') and owns_local_listener(saved):
                return saved
        except (OSError,ValueError) as error:diagnostic={'reason':'metadata_read_failed','error':type(error).__name__,'winerror':getattr(error,'winerror',None)}
        if diagnostic:
            try:(metadata.parent/('launcher-check-'+str(os.getpid())+'.json')).write_text(json.dumps(diagnostic),encoding='utf8')
            except OSError:pass
        if time.monotonic()>=deadline:raise RuntimeError('El servidor de XuperPC no respondió. Cierra la instancia anterior y vuelve a abrir XuperPC.')
        time.sleep(.2)


def write_metadata(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value),encoding='utf8');temporary.replace(path)
