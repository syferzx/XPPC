"""Local MP4 export jobs using an independent, normally authorized VOD lease."""
import collections,json,os,re,shutil,subprocess,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from vod import VodService
from media_tracks import ffmpeg
from artwork import artwork,public_image
from portal import series_identity,series_group_token

ACTIVE={'preparing','options','queued','preparing_download','downloading','converting','cancelling'}
WORKING={'preparing_download','downloading','converting','cancelling'}
class DownloadBusy(ValueError):
    def __init__(self,identifier):self.identifier=identifier;super().__init__('Ya hay una descarga activa. Termínala o cancélala antes de iniciar otra.')
class Cancelled(Exception):pass

def confirmed_download(job):
    # An audio choice is committed only by start(), never by opening options.
    return 'audio' in job or job.get('state') in ('ready','interrupted')


def safe_name(value):
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',str(value));value=' '.join(value.split()).strip(' .')[:110]
    if not value or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',value):value='Contenido'
    return value

def export_arguments(executable,source,output,audio,codec,subtitle=None,audio_language='und',subtitle_language='und',container='mp4'):
    args=[executable,'-y','-nostdin','-hide_banner','-loglevel','error','-protocol_whitelist','file,pipe','-i',str(source)]
    if subtitle:args+=['-protocol_whitelist','file,pipe','-i',str(subtitle)]
    args+=['-map','0:v:0','-map','0:a:'+str(audio)+'?']
    if subtitle:args+=['-map','1:s:0','-c:s','mov_text','-metadata:s:s:0','language='+subtitle_language,'-disposition:s:0','default']
    if container=='mkv':
        args+=['-c:v','copy','-c:a','copy','-metadata:s:a:0','language='+audio_language]
        if subtitle:args+=['-c:s','srt']
        return args+['-map_metadata','-1','-avoid_negative_ts','make_zero','-progress','pipe:1','-nostats','-f','matroska',str(output)]
    if str(codec).lower() in ('avc1','h264','avc'):args+=['-c:v','copy']
    else:args+=['-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-threads','2']
    return args+['-c:a','aac','-b:a','192k','-ac','2','-metadata:s:a:0','language='+audio_language,'-map_metadata','-1','-avoid_negative_ts','make_zero','-movflags','+faststart','-progress','pipe:1','-nostats',str(output)]

class DownloadService:
    def __init__(self,root,portal,output=None,vod_factory=VodService,ffmpeg_factory=ffmpeg):
        self.root=Path(root);home=Path(os.environ['XUPERPC_PORTABLE_ROOT']) if os.environ.get('XUPERPC_PORTABLE_ROOT') else self.root
        self.output=Path(output) if output else home/'Descargas';self.output.mkdir(parents=True,exist_ok=True)
        self.ledger=self.root/'work/downloads.json'
        self.base=self.root/'work/download-jobs';self.base.mkdir(parents=True,exist_ok=True)
        self.portal=portal;self.factory=vod_factory;self.ffmpeg_factory=ffmpeg_factory;self.lock=threading.RLock();self.jobs=collections.OrderedDict();self.closed=False;self.wake=threading.Event()
        # Only stale private staging folders owned by this feature are removed.
        for path in self.base.iterdir():
            if re.fullmatch(r'[a-f0-9]{32}',path.name) and path.is_dir() and not path.is_symlink():self._cleanup(path)
        self._restore()
        self.worker=threading.Thread(target=self._queue_loop,daemon=True,name='mp4-queue');self.worker.start()
    def _save(self):
        # Public metadata and content identifiers only; never persist playback grants.
        fields=('id','item_id','episode','name','state','percent','downloaded_bytes','total_bytes','audio_tracks','subtitle_tracks','audio','subtitle','audio_language','subtitle_language','filename','subtitle_filename','destination','error','asset','kind','poster_url','series_title','series_group','season','format')
        payload={'version':1,'output':str(self.output),'jobs':[{k:j[k] for k in fields if k in j} for j in self.jobs.values() if confirmed_download(j) and j['state'] not in ('preparing','options')]}
        temporary=self.ledger.with_suffix('.tmp');temporary.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf8');temporary.replace(self.ledger)
    def _restore(self):
        try:
            if self.ledger.stat().st_size>2*1024**2:return
            payload=json.loads(self.ledger.read_text(encoding='utf8'))
            folder=Path(payload.get('output',''))
            if folder.is_absolute() and not str(folder).startswith('\\\\'):self.output=folder
            for item in payload.get('jobs',[])[:200]:
                if not isinstance(item,dict) or not re.fullmatch(r'[a-f0-9]{32}',str(item.get('id',''))):continue
                if item.get('state') not in ACTIVE|{'ready','error','cancelled','interrupted'}:continue
                for key in ('filename','subtitle_filename'):
                    if item.get(key) and Path(item[key]).name!=item[key]:raise ValueError('Invalid history filename')
                item['poster_url']=public_image(item.get('poster_url'))
                destination=Path(item.get('destination',str(self.output)))
                if not destination.is_absolute() or str(destination).startswith('\\\\'):continue
                # Pending downloads require an explicit retry after restarting the server.
                if item['state'] in ACTIVE:item.update(state='interrupted',error='El programa se cerró antes de terminar. Vuelve a añadir la descarga.')
                if not confirmed_download(item):continue
                item.update(cancel=threading.Event(),created=time.monotonic(),speed_bytes=0,destination=str(destination))
                self.jobs[item['id']]=item
        except (OSError,ValueError,TypeError,KeyError):pass
        # Adopt files made by the previous release, without moving or changing them.
        known={(j.get('destination'),j.get('filename')) for j in self.jobs.values()}
        if self.output.is_dir():
            for path in (list(self.output.glob('*.mp4'))+list(self.output.glob('*.mkv')))[:200]:
                if path.is_symlink() or (str(self.output),path.name) in known or not re.fullmatch(r'.+ - [a-z]{2,3} - [a-f0-9]{8}\.(?:mp4|mkv)',path.name):continue
                identifier=uuid.uuid5(uuid.NAMESPACE_URL,str(path)).hex
                self.jobs[identifier]={'id':identifier,'name':path.stem.rsplit(' - ',2)[0],'state':'ready','percent':100,'downloaded_bytes':path.stat().st_size,'total_bytes':path.stat().st_size,'filename':path.name,'format':path.suffix[1:],'subtitle_filename':path.with_suffix('.srt').name if path.with_suffix('.srt').is_file() else None,'destination':str(self.output),'cancel':threading.Event(),'created':time.monotonic()}
    def listing(self):
        with self.lock:
            positions={j['id']:i+1 for i,j in enumerate(j for j in self.jobs.values() if j['state']=='queued')}
            items=[]
            for job in reversed(list(self.jobs.values())):
                if job['state']=='options' and time.monotonic()-job['created']>600:self.cancel(job['id'])
                if not confirmed_download(job):continue
                item=self._public(job);item['queue_position']=positions.get(job['id']);items.append(item)
            return {'items':items,'folder':str(self.output),'parallel_parts':3}
    def set_folder(self,value):
        if not isinstance(value,str) or len(value)>240 or not value.strip():raise ValueError('Indica una carpeta local válida.')
        folder=Path(value.strip()).expanduser()
        if not folder.is_absolute() or str(folder).startswith('\\\\'):raise ValueError('Elige una ruta local absoluta, por ejemplo C:\\Videos.')
        try:
            folder.mkdir(parents=True,exist_ok=True);folder=folder.resolve();probe=folder/('.xuperpc-'+uuid.uuid4().hex)
            with probe.open('xb'):pass
            probe.unlink()
        except OSError:raise ValueError('No se puede escribir en esa carpeta.')
        with self.lock:
            previous=self.output;self.output=folder
            try:self._save()
            except OSError:
                self.output=previous;raise ValueError('No se pudo guardar la carpeta. Comprueba el espacio libre y los permisos de Datos.')
        return {'folder':str(folder)}
    def choose_folder(self):
        if os.name!='nt':raise ValueError('Introduce la ruta en el campo de carpeta.')
        import ctypes
        from ctypes import wintypes
        class Browse(ctypes.Structure):
            _fields_=[('owner',wintypes.HWND),('root',ctypes.c_void_p),('display',wintypes.LPWSTR),('title',wintypes.LPCWSTR),('flags',wintypes.UINT),('callback',ctypes.c_void_p),('param',wintypes.LPARAM),('image',ctypes.c_int)]
        shell=ctypes.windll.shell32;ole=ctypes.windll.ole32;ole.CoInitializeEx(None,2)
        shell.SHBrowseForFolderW.restype=ctypes.c_void_p;shell.SHBrowseForFolderW.argtypes=[ctypes.POINTER(Browse)]
        shell.SHGetPathFromIDListW.argtypes=[ctypes.c_void_p,wintypes.LPWSTR];ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
        display=ctypes.create_unicode_buffer(32768);info=Browse(None,None,ctypes.cast(display,wintypes.LPWSTR),'Carpeta predeterminada para Mis descargas',0x41,None,0,0);pidl=None
        try:
            pidl=shell.SHBrowseForFolderW(ctypes.byref(info))
            if not pidl:return {'folder':str(self.output),'cancelled':True}
            result=ctypes.create_unicode_buffer(32768)
            if not shell.SHGetPathFromIDListW(pidl,result):raise ValueError('Elige una carpeta local.')
            return self.set_folder(result.value)
        finally:
            if pidl:ole.CoTaskMemFree(pidl)
            ole.CoUninitialize()
    def forget(self,identifier):
        with self.lock:
            job=self.jobs[identifier]
            if job['state'] in ACTIVE:raise ValueError('Cancela la descarga antes de quitarla del historial.')
            del self.jobs[identifier];self._save()
        return {'removed':True}
    def retry(self,identifier):
        with self.lock:
            job=self.jobs[identifier]
            if job['state'] not in ('error','cancelled','interrupted') or not job.get('asset'):raise ValueError('Vuelve a abrir el título para descargarlo.')
            if sum(j['state'] in ACTIVE for j in self.jobs.values())>=20:raise ValueError('La cola está llena.')
            job.update(state='preparing',error=None,percent=0,downloaded_bytes=0,cancel=threading.Event(),created=time.monotonic())
            threading.Thread(target=self._prepare,args=(job,),daemon=True,name='mp4-prepare').start()
            return self._public(job)
    def _queue_loop(self):
        while not self.closed:
            self.wake.wait(1);self.wake.clear()
            while not self.closed:
                with self.lock:
                    job=next((j for j in self.jobs.values() if j['state']=='queued'),None)
                    if not job:break
                    job.update(state='preparing_download',percent=0,downloaded_bytes=0,speed_bytes=0)
                    try:self._save()
                    except OSError:
                        job.update(state='error',error='No se pudo guardar el historial. Revisa el espacio libre y los permisos de Datos.');continue
                try:
                    self._check(job)
                    with self.portal.lock:self.portal.assets.setdefault(job['item_id'],(job['kind'],dict(job['asset'])))
                    source=self.factory(self.root,self.portal);job['source']=source
                    grant=source.start(job['item_id'],job['episode']);self._check(job);key=grant['url'].split('/')[2]
                    # Language and index must still match the user's confirmed choices.
                    for field,tracks in (('audio',grant.get('audio_tracks',[])),('subtitle',grant.get('subtitle_tracks',[]))):
                        if job[field]<0:continue
                        language=next((t.get('language','und') for t in tracks if t['index']==job[field]),None)
                        if language!=job[field+'_language'] and not (field=='audio' and not tracks and job[field]==0):raise ValueError('Las pistas disponibles cambiaron. Vuelve a elegir audio y subtítulos.')
                    size=source.sessions[key]['index']['size']
                    if not 0<size<=16*1024**3:raise ValueError('El contenido supera el límite de descarga de 16 GB.')
                    destination=Path(job['destination']);destination.mkdir(parents=True,exist_ok=True)
                    if min(shutil.disk_usage(self.base).free,shutil.disk_usage(destination).free)<size*3+256*1024**2:raise ValueError('No hay espacio suficiente para preparar el archivo.')
                    with self.lock:
                        self._check(job);job.update(key=key,total_bytes=size,duration=grant.get('duration_seconds',0),state='downloading');self._save()
                    self._download(job)
                except Cancelled:self._finish_error(job,'cancelled')
                except Exception as error:self._finish_error(job,'error',str(error) if isinstance(error,ValueError) else 'No se pudo iniciar la descarga. Comprueba la sesión y vuelve a intentarlo.')
    def _cleanup(self,path):
        path=Path(path)
        if path.parent.resolve()!=self.base.resolve() or not re.fullmatch(r'[a-f0-9]{32}',path.name) or path.is_symlink():raise ValueError('Invalid staging path')
        shutil.rmtree(path,ignore_errors=True)
    def _public(self,job):
        keys=('id','item_id','episode','name','state','percent','downloaded_bytes','total_bytes','speed_bytes','processed_seconds','audio_tracks','subtitle_tracks','error','filename','subtitle_filename','kind','poster_url','series_title','series_group','season','format')
        value={k:job[k] for k in keys if k in job}
        value['destination']=job.get('destination',str(self.output));value['parallel_parts']=3
        if job['state']=='ready':
            path=Path(job.get('destination',str(self.output)))/str(job.get('filename',''))
            value['file_exists']=bool(job.get('filename') and path.is_file() and not path.is_symlink())
            value['subtitle_exists']=bool(job.get('subtitle_filename') and (path.parent/job['subtitle_filename']).is_file())
            value['file_url']='/api/downloads/'+job['id']+'/file';value['subtitle_url']='/api/downloads/'+job['id']+'/subtitle' if job.get('subtitle_filename') else None
        return value
    def status(self,identifier):
        with self.lock:
            job=self.jobs[identifier]
            if job['state']=='options' and time.monotonic()-job['created']>600:self.cancel(identifier)
            return self._public(job)
    def prepare(self,item_id,episode=None,poster=None):
        if not isinstance(item_id,str) or not re.fullmatch(r'[a-f0-9]{20}',item_id):raise ValueError('Invalid title')
        if episode is not None and (type(episode) not in (str,int) or not re.fullmatch(r'[0-9]{1,6}',str(episode))):raise ValueError('Invalid episode')
        with self.portal.lock:
            kind,asset=self.portal.assets[item_id]
            if kind not in ('movies','series'):raise ValueError('Only movies and episodes can be downloaded')
            name=str(asset.get('name') or 'Contenido')+(' - Episodio '+str(episode) if kind=='series' else '')
        with self.lock:
            if self.closed:raise ValueError('Downloader closed')
            for old in self.jobs.values():
                if old.get('item_id')==item_id and old.get('episode')==(None if episode is None else str(episode)) and old['state'] in ACTIVE:raise DownloadBusy(old['id'])
            if sum(j['state'] in ACTIVE for j in self.jobs.values())>=20:raise ValueError('La cola admite hasta 20 descargas pendientes.')
            drafts=[identifier for identifier,old in self.jobs.items() if not confirmed_download(old) and old['state'] not in ACTIVE]
            for identifier in drafts[:-8]:del self.jobs[identifier]
            if len(self.jobs)>=200:raise ValueError('Quita descargas antiguas del historial antes de añadir más.')
            identifier=uuid.uuid4().hex
            job={'id':identifier,'item_id':item_id,'episode':None if episode is None else str(episode),'name':name,'state':'preparing','percent':0,'downloaded_bytes':0,'total_bytes':0,'speed_bytes':0,'error':None,'created':time.monotonic(),'cancel':threading.Event(),'kind':kind,'poster_url':artwork(asset)['poster_url'] or public_image(poster),'series_title':series_identity(asset.get('name',''))[1] if kind=='series' else None,'season':series_identity(asset.get('name',''))[2] if kind=='series' else None,'series_group':series_group_token(asset) if kind=='series' else None,'asset':{k:asset[k] for k in ('contentId','type','name') if k in asset}}
            self.jobs[identifier]=job
            threading.Thread(target=self._prepare,args=(job,),daemon=True,name='mp4-prepare').start()
            return self._public(job)
    def _check(self,job):
        if job['cancel'].is_set() or self.closed:raise Cancelled()
    def _release(self,job):
        source=job.pop('source',None)
        if source:source.stop_buffer();source.buffer.close()
    def _prepare(self,job):
        try:
            with self.portal.lock:self.portal.assets.setdefault(job['item_id'],(job['kind'],dict(job['asset'])))
            source=self.factory(self.root,self.portal);job['source']=source
            grant=source.start(job['item_id'],job['episode']);self._check(job)
            key=grant['url'].split('/')[2];lease=source.sessions[key];size=lease['index']['size']
            if not 0<size<=16*1024**3:raise ValueError('El contenido supera el límite de descarga de 16 GB.')
            self._release(job)
            with self.lock:
                self._check(job)
                job.update(key=key,total_bytes=size,duration=grant.get('duration_seconds',0),audio_tracks=grant.get('audio_tracks',[]),subtitle_tracks=[{'index':t['index'],'language':t['language']} for t in grant.get('subtitle_tracks',[])],state='options')
        except Cancelled:self._finish_error(job,'cancelled')
        except Exception:self._finish_error(job,'error','No se pudo preparar la descarga. Comprueba la sesión y vuelve a intentarlo.')
    def start(self,identifier,audio=0,subtitle=-1,container='mkv'):
        with self.lock:
            job=self.jobs[identifier]
            if job['state']!='options':raise ValueError('La descarga no está lista para elegir opciones.')
            if type(audio) is not int or (job['audio_tracks'] and audio not in [t['index'] for t in job['audio_tracks']]) or (not job['audio_tracks'] and audio!=0):raise ValueError('Audio no disponible.')
            if type(subtitle) is not int or (subtitle!=-1 and subtitle not in [t['index'] for t in job['subtitle_tracks']]):raise ValueError('Subtítulo no disponible.')
            if container not in ('mkv','mp4'):raise ValueError('Formato no disponible.')
            self._check(job)
            previous=dict(job)
            job.update(state='queued',format=container,audio=audio,subtitle=subtitle,destination=str(self.output),
                       audio_language=next((t.get('language','und') for t in job['audio_tracks'] if t['index']==audio),'und'),
                       subtitle_language=next((t.get('language','und') for t in job['subtitle_tracks'] if t['index']==subtitle),'und'))
            try:self._save()
            except OSError:
                job.clear();job.update(previous);raise ValueError('No se pudo guardar la cola. Comprueba el espacio libre y los permisos de Datos.')
            self.wake.set()
            return self._public(job)
    def cancel(self,identifier):
        with self.lock:
            job=self.jobs[identifier]
            if job['state'] not in ACTIVE:return self._public(job)
            old=job['state'];job['cancel'].set();job['state']='cancelling';process=job.get('process')
            if process and process.poll() is None:process.terminate()
            if old in ('options','queued'):self._finish_error(job,'cancelled')
            return self._public(job)
    def _finish_error(self,job,state,message=None):
        self._release(job);self._cleanup(self.base/job['id'])
        with self.lock:
            job.update(state=state,error=message,speed_bytes=0)
            try:self._save()
            except OSError:pass
    def _run(self,job,args,log,duration=0):
        self._check(job)
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        with open(log,'wb') as errors:
            process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors,text=True,creationflags=flags)
            with self.lock:job['process']=process
            def read_progress():
                for line in process.stdout:
                    if line.startswith('out_time_us='):
                        try:seconds=max(0,int(line.split('=',1)[1])/1000000)
                        except ValueError:continue
                        with self.lock:job.update(processed_seconds=seconds,percent=min(99,75+24*seconds/max(duration,1)))
            reader=threading.Thread(target=read_progress,daemon=True);reader.start();started=time.monotonic()
            try:
                while process.poll() is None:
                    self._check(job)
                    if time.monotonic()-started>max(180,duration*4+120):raise ValueError('La conversión tardó más de lo permitido.')
                    if shutil.disk_usage(self.base).free<64*1024**2:raise ValueError('No queda espacio para terminar el archivo.')
                    time.sleep(.15)
                self._check(job)
                if process.returncode:raise ValueError('FFmpeg no pudo crear el archivo seleccionado.')
            finally:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
                reader.join(timeout=2);process.stdout.close()
                with self.lock:job.pop('process',None)
    def _download(self,job):
        folder=self.base/job['id'];source=job['source'];key=job['key']
        try:
            folder.mkdir(exist_ok=True)
            self._check(job);index=source.sessions[key]['index'];started=time.monotonic();raw=folder/'source.ts'
            def fetch_part(number):
                for attempt in range(3):
                    self._check(job)
                    try:return source.segment(key,number,prefetch=False)
                    except (TimeoutError,ConnectionError):
                        if attempt==2:raise
                        if job['cancel'].wait(.4*(attempt+1)):raise Cancelled()
            # Exactly three in-flight parts. Only ordered bytes are appended to disk.
            with ThreadPoolExecutor(max_workers=3,thread_name_prefix='mp4-part') as pool,raw.open('wb') as output:
                count=len(index['segments']);pending={n:pool.submit(fetch_part,n) for n in range(min(3,count))}
                for n in range(count):
                    self._check(job)
                    if shutil.disk_usage(folder).free<64*1024**2:raise ValueError('No queda espacio para terminar la descarga.')
                    body=pending.pop(n).result();self._check(job);output.write(body)
                    if n+3<count:pending[n+3]=pool.submit(fetch_part,n+3)
                    with self.lock:
                        job['downloaded_bytes']+=len(body);job['percent']=75*job['downloaded_bytes']/job['total_bytes'];job['speed_bytes']=job['downloaded_bytes']/max(.1,time.monotonic()-started)
            if raw.stat().st_size!=job['total_bytes']:raise ValueError('La descarga está incompleta.')
            executable=self.ffmpeg_factory(self.root);vtt=None;srt=None;sub_language='und'
            def language(value):return value if isinstance(value,str) and re.fullmatch(r'[a-z]{2,3}',value) else 'und'
            if job['subtitle']>=0:
                self._check(job);vtt=folder/'subtitle.vtt';vtt.write_bytes(source.subtitle(key,job['subtitle']));srt=folder/'subtitle.srt'
                sub_language=language(next(t['language'] for t in job['subtitle_tracks'] if t['index']==job['subtitle']))
                self._run(job,[executable,'-y','-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(vtt),'-c:s','srt',str(srt)],folder/'subtitle.log')
            with self.lock:job.update(state='converting',percent=75,speed_bytes=0)
            audio_language=language(next((t.get('language') for t in job['audio_tracks'] if t['index']==job['audio']),'und'))
            container=job.get('format','mp4')
            mp4=folder/('output.'+container);args=export_arguments(executable,raw,mp4,job['audio'],index.get('video_codec'),vtt,audio_language,sub_language,container)
            self._run(job,args,folder/'encode.log',job['duration']);self._check(job)
            if not mp4.exists() or mp4.stat().st_size<100:raise ValueError('No se generó un archivo válido.')
            destination_folder=Path(job['destination'])
            name=safe_name(job['name'])+' - '+audio_language+' - '+job['id'][:8];destination=destination_folder/(name+'.'+container)
            if destination.exists():raise ValueError('El archivo de salida ya existe.')
            # Copy to an unadvertised partial file on the destination filesystem, then rename.
            partial=destination_folder/(name+'.part');sub_dest=None;partial_created=False;sub_created=False
            try:
                with mp4.open('rb') as src,partial.open('xb') as dst:
                    partial_created=True
                    while True:
                        self._check(job);chunk=src.read(1024*1024)
                        if not chunk:break
                        dst.write(chunk)
                self._check(job)
                if srt:
                    sub_dest=destination_folder/(name+'.srt')
                    if sub_dest.exists():raise ValueError('El subtítulo de salida ya existe.')
                    with sub_dest.open('xb') as dst:sub_created=True;dst.write(srt.read_bytes())
                with self.lock:
                    self._check(job);partial.rename(destination)
                    job.update(state='ready',percent=100,filename=destination.name,subtitle_filename=sub_dest.name if sub_dest else None)
            except BaseException:
                if partial_created:partial.unlink(missing_ok=True)
                if sub_created:sub_dest.unlink(missing_ok=True)
                raise
            self._release(job);self._cleanup(folder)
            with self.lock:
                try:self._save()
                except OSError:pass
        except Cancelled:self._finish_error(job,'cancelled')
        except Exception as error:
            message=str(error) if isinstance(error,ValueError) else 'La descarga se interrumpió. Puedes volver a intentarlo.'
            self._finish_error(job,'error',message)
    def file(self,identifier,subtitle=False):
        with self.lock:
            job=self.jobs[identifier]
            if job['state']!='ready':raise ValueError('File not ready')
            name=job.get('subtitle_filename') if subtitle else job.get('filename')
            if not name or Path(name).name!=name:raise ValueError('Invalid filename')
            folder=Path(job.get('destination',str(self.output)));path=folder/name
            if path.parent.resolve()!=folder.resolve() or path.is_symlink() or not path.is_file():raise ValueError('Invalid export file')
            return path
    def open_folder(self,identifier=None):
        if os.name!='nt':raise ValueError('Abre la carpeta Descargas junto al programa.')
        with self.lock:folder=Path(self.jobs[identifier].get('destination',str(self.output))) if identifier else self.output
        if not folder.is_dir():raise ValueError('La carpeta ya no existe.')
        os.startfile(str(folder))
    def close(self):
        with self.lock:
            self.closed=True;self.wake.set()
            for job in self.jobs.values():
                if job['state'] in ACTIVE:self.cancel(job['id'])
