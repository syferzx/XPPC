"""Portable launcher. The distribution never contains a user's access profile."""
import argparse,json,os,sys,webbrowser,shutil,traceback,threading,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from launcher_state import wait_for_instance,write_metadata

FROZEN=bool(getattr(sys,'frozen',False))
PACKAGED=bool(os.environ.get('XUPERPC_PORTABLE_ROOT'))
BUNDLE=Path(os.environ['XUPERPC_ENGINE_ROOT']) if PACKAGED else Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parents[2]
os.environ['XUPERPC_RESOURCE_ROOT']=str(BUNDLE)
if not FROZEN and not PACKAGED:
    sys.path[:0]=[str(BUNDLE/'work'),str(BUNDLE/'work/analysis-tools'),str(BUNDLE/'work/ffmpeg-tools'),str(BUNDLE/'outputs/ranger-windows')]

def verify(report_file=None):
    def mark(stage):
        if report_file:report_file.write_text(json.dumps({'stage':stage,'success':False}),encoding='utf8')
    mark('imports')
    import mmh3,cryptography,unicorn,imageio_ffmpeg,certifi
    mark('runtime_import')
    from ranger_native_runtime import Runtime
    from slb_protocol import SlbProtocol
    mark('runtime_construct');r=Runtime()
    mark('runtime_execute');r.call(0x5d8f08)
    mark('protocol')
    codec=SlbProtocol('0123456789abcdef0123456789abcdef');wire=codec.encode(b'{"test":true}')
    mark('ffmpeg')
    result={'standalone_runtime':FROZEN or PACKAGED,'native_emulation':True,'protocol_roundtrip':codec.decode(wire)==b'{"test":true}','ffmpeg_bundled':Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file() and Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve().is_relative_to(BUNDLE),'tls_ca_bundled':Path(certifi.where()).is_file(),
        'modules_from_bundle':all(Path(m.__file__).resolve().is_relative_to(BUNDLE) for m in [unicorn,cryptography,imageio_ffmpeg]) if FROZEN or PACKAGED else False}
    result['success']=all(result.values());return result

SETUP='''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>XuperPC · Preparando tu biblioteca</title><style>body{font:16px Segoe UI,system-ui;background:#090a0c;color:#f5f5f7;margin:0;display:grid;place-items:center;min-height:100vh}main{max-width:480px;padding:40px;text-align:center;margin:24px}h1{margin:24px 0 12px;font-size:26px}p{color:#a9a9b2;line-height:1.7}.brand{font-size:32px;font-weight:800;letter-spacing:-1px}.brand span{color:#ed182a}.spinner{height:44px;width:44px;border:4px solid #ffffff20;border-top-color:#ed182a;border-radius:50%;margin:32px auto 0;animation:spin .85s linear infinite}[hidden]{display:none!important}#message{min-height:54px;font-size:14px}.failed{color:#ff9eaa}@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.spinner{animation:none;border-right-color:#ed182a}}</style><main aria-busy="true" id="setup"><div class="brand">Xuper<span>PC</span></div><div id="spinner" class="spinner" aria-hidden="true"></div><h1 id="heading">Preparando tu biblioteca</h1><p id="message" role="status" aria-live="polite">Conectando… La primera apertura puede tardar un momento.</p></main><script>
const setup=document.getElementById('setup'),spinner=document.getElementById('spinner'),message=document.getElementById('message'),heading=document.getElementById('heading');
async function initialize(){
  try{
    const response=await fetch('/api/setup/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({configure:true})});
    const result=await response.json();
    if(!response.ok||!result.ready)throw Error(result.error||'No se pudo completar la configuración. Cierra y vuelve a abrir XuperPC para revisar el estado.');
    message.textContent='Abriendo tu biblioteca…';location.reload();
  }catch(error){spinner.hidden=true;setup.setAttribute('aria-busy','false');heading.textContent='No pudimos abrir tu biblioteca';message.className='failed';message.textContent=error.message||'No se pudo conectar. Comprueba tu conexión y vuelve a abrir XuperPC.';}
}
initialize();
</script></html>'''.encode('utf8')

class SetupHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.headers.get('Host') not in ['127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)]:self.send_error(403);return
        if self.path not in ['/','/api/setup/status','/api/launcher/status']:self.send_error(404);return
        body=SETUP if self.path=='/' else json.dumps({'application':'XuperPC','pid':os.getpid(),'instance':self.server.launcher_id}).encode() if self.path=='/api/launcher/status' else b'{"requires_access_setup":true,"portable":true}'
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8' if self.path=='/' else 'application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Frame-Options','DENY');self.end_headers()
        try:self.wfile.write(body)
        except ConnectionError:pass
    def do_POST(self):
        origin='http://127.0.0.1:'+str(self.server.server_port)
        if self.path!='/api/setup/activate' or self.headers.get('Host')!=origin[7:] or self.headers.get('Origin') not in (None,origin):self.send_error(403);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=128 or self.headers.get('Content-Type')!='application/json' or json.loads(self.rfile.read(size))!={'configure':True}:self.send_error(400);return
        except (ValueError,UnicodeError):self.send_error(400);return
        try:
            with self.server.setup_lock:
                from installation_access import configure
                result=configure(self.server.data_root,BUNDLE)
                self.server.load_application()
            status=200;body=json.dumps(result).encode('utf8')
        except Exception as error:
            from installation_access import SetupError
            message=str(error) if isinstance(error,SetupError) else 'No se pudo conectar con el servicio. La instalación guardada se conserva.'
            status=502;body=json.dumps({'error':message},ensure_ascii=False).encode('utf8')
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except ConnectionError:pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',type=Path);parser.add_argument('--data-root',type=Path);parser.add_argument('--port',type=int,default=0);parser.add_argument('--no-open',action='store_true');args=parser.parse_args()
    if args.self_test:
        report=verify(args.self_test);args.self_test.write_text(json.dumps(report,indent=2),encoding='utf8');return 0 if report['success'] else 1
    home=Path(os.environ['XUPERPC_PORTABLE_ROOT']) if PACKAGED else Path(sys.executable).parent if FROZEN else BUNDLE/'work/portable-data'
    # A sibling folder is portable and is not redirected into an MSIX parent's
    # private AppData cache when launched from packaged tools.
    default_data=home/'Datos'
    data=(args.data_root or default_data).resolve()
    os.environ['XUPERPC_DATA_ROOT']=str(data)
    (data/'work/portal-native').mkdir(parents=True,exist_ok=True)
    def launch_result(state,active_pid=None):
        # Keep only the latest launch outcome; no session or provider data.
        try:
            target=data/'work/launcher-last-open.json';temporary=target.with_suffix('.'+str(os.getpid())+'.tmp')
            temporary.write_text(json.dumps({'launcher_pid':os.getpid(),'state':state,'active_pid':active_pid}),encoding='utf8');temporary.replace(target)
        except OSError:pass
    launch_result('starting')
    if os.name=='nt':
        import ctypes,hashlib,urllib.parse
        from ctypes import wintypes
        kernel=ctypes.windll.kernel32;kernel.CreateMutexW.restype=wintypes.HANDLE
        mutex=kernel.CreateMutexW(None,False,'Local\\XuperPC-'+hashlib.sha256(str(data).casefold().encode()).hexdigest()[:32])
        if not mutex:raise OSError('Cannot acquire application mutex')
        if kernel.GetLastError()==183:
            try:
                saved=wait_for_instance(data/'work/portable-server.json')
                if not args.no_open:webbrowser.open(saved['url'])
                launch_result('reused',saved['pid'])
            finally:
                kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(mutex)
            return 0
    os.environ['XUPERPC_DATA_ROOT']=str(data);os.chdir(data)
    independent=['work/portal-native/client-profile.private.json','work/portal-native/media-client.private.json','work/portal-native/active-data.private.json','work/portal-native/codec-key.private.txt']
    ready=all((data/name).is_file() for name in independent)
    app=None
    if ready:
        from installation_access import configure
        configure(data,BUNDLE)
        shared=BUNDLE/'outputs/rutas-portal.json';target=data/'outputs/rutas-portal.json';target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(shared,target)
        import app as application
        app=application;handler=app.Handler
    else:handler=SetupHandler
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler);url='http://127.0.0.1:'+str(server.server_port)+'/'
    server.data_root=data;server.setup_lock=threading.Lock();server.application=app;server.launcher_id=uuid.uuid4().hex
    metadata={'pid':os.getpid(),'url':url,'requires_access_setup':not ready,'instance':server.launcher_id,'engine':str(Path(sys.executable).resolve())}
    def load_application():
        if server.application is None:
            import app as application
            server.application=application;application.portal.start()
            server.RequestHandlerClass=application.Handler
            metadata['requires_access_setup']=False
            write_metadata(data/'work/portable-server.json',metadata)
    server.load_application=load_application
    write_metadata(data/'work/portable-server.json',metadata)
    if app:app.portal.start()
    serving=threading.Thread(target=server.serve_forever,daemon=True);serving.start()
    try:
        wait_for_instance(data/'work/portable-server.json')
        if not args.no_open:webbrowser.open(url)
        launch_result('ready',os.getpid())
        serving.join()
    finally:
        if server.application:
            server.application.portal.stop.set()
            server.application.vod.buffer.close()
        server.shutdown()
        server.server_close()
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception:
        log=Path(os.environ.get('XUPERPC_DATA_ROOT',str(Path.home()/'XuperPC')))/'work/XuperPC-error.log'
        log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text(traceback.format_exc(),encoding='utf8')
        if os.name=='nt' and '--self-test' not in sys.argv and '--no-open' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'No se pudo iniciar XuperPC. Revisa el registro en '+str(log),'XuperPC',16)
        sys.exit(1)
