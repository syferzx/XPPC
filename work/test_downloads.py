import sys,tempfile,threading,time,subprocess,unittest,json
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
for path in ('work','work/analysis-tools','outputs/ranger-windows','outputs/windows-hls-player'):sys.path.insert(0,str(ROOT/path))
from downloads import DownloadService,DownloadBusy,safe_name
import imageio_ffmpeg
FF=Path(imageio_ffmpeg.get_ffmpeg_exe())
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  source=self.root/'fixture.ts'
  subprocess.run([str(FF),'-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10:duration=3','-f','lavfi','-i','sine=frequency=440:duration=3','-f','lavfi','-i','sine=frequency=880:duration=3','-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-metadata:s:a:0','language=spa','-metadata:s:a:1','language=eng','-f','mpegts',str(source)],check=True,capture_output=True)
  self.body=source.read_bytes();self.created=[];self.counter_lock=threading.Lock();self.running=0;self.peak=0;owner=self
  class Fake:
   def __init__(self,*args):self.closed=False;self.buffer=SimpleNamespace(close=lambda:setattr(self,'closed',True));owner.created.append(self)
   def start(self,*args):
    self.sessions={'a'*24:{'index':{'size':len(owner.body),'segments':[0,1,2],'video_codec':'avc1'}}}
    return {'url':'/vod/'+('a'*24)+'/index.m3u8','duration_seconds':3,'audio_tracks':[{'index':0,'language':'spa'},{'index':1,'language':'eng'}],'subtitle_tracks':[{'index':0,'language':'spa','url':'private'}]}
   def segment(self,key,n,prefetch=True):
    with owner.counter_lock:owner.running+=1;owner.peak=max(owner.peak,owner.running)
    try:return self.read_segment(n)
    finally:
     with owner.counter_lock:owner.running-=1
   def read_segment(self,n):
    if getattr(owner,'gate',None):owner.gate.wait(5)
    if getattr(owner,'slow',False):time.sleep(.2)
    if getattr(owner,'network_failure',False):raise ConnectionError()
    cut=len(owner.body)//188//3*188;return owner.body[n*cut:(n+1)*cut] if n<2 else owner.body[2*cut:]
   def subtitle(self,*args):return b'WEBVTT\n\n00:00:00.300 --> 00:00:02.500\nTexto de prueba\n'
   def stop_buffer(self):pass
  self.portal=SimpleNamespace(lock=threading.RLock(),assets={'a'*20:('series',{'name':'Serie / prueba'})})
  self.service=DownloadService(self.root,self.portal,self.root/'exports',vod_factory=Fake,ffmpeg_factory=lambda _:str(FF));self.addCleanup(lambda:(self.service.close(),self.service.worker.join(3)))
 def wait(self,id,states):
  limit=time.monotonic()+20
  while time.monotonic()<limit:
   value=self.service.status(id)
   if value['state'] in states and (value['state'] not in ('ready','error','cancelled') or (not (self.service.base/id).exists() and 'source' not in self.service.jobs[id])):return value
   time.sleep(.05)
  self.fail('Timeout '+str(value))
 def options(self):
  id=self.service.prepare('a'*20,'2')['id'];self.wait(id,{'options','error'});return id
 def test_mp4_audio_subtitle_and_cleanup(self):
  id=self.options()
  with self.assertRaises(DownloadBusy):self.service.prepare('a'*20,'2')
  with self.assertRaises(ValueError):self.service.start(id,44,0)
  self.service.start(id,1,0,'mp4');result=self.wait(id,{'ready','error'});self.assertEqual(result['state'],'ready',result)
  path=self.service.file(id);self.assertGreater(path.stat().st_size,1000)
  probe=subprocess.run([str(FF),'-hide_banner','-i',str(path),'-t','0','-f','null','-'],capture_output=True).stderr.decode()
  self.assertIn('(eng): Audio: aac',probe);self.assertIn('Video: h264',probe);self.assertIn('Subtitle: mov_text',probe);self.assertNotIn('(spa): Audio:',probe)
  srt=self.service.file(id,True);self.assertIn('Texto de prueba',srt.read_text());self.assertFalse((self.service.base/id).exists());self.assertTrue(self.created[0].closed)
  self.assertNotIn('private',json.dumps(result));self.assertEqual(len(list(self.service.output.glob('*.part'))),0)
 def test_cancel_options_and_network(self):
  id=self.options();self.assertEqual(self.service.cancel(id)['state'],'cancelled');self.assertTrue(self.created[0].closed)
  self.slow=True;id=self.options();self.service.start(id);self.service.cancel(id);self.assertEqual(self.wait(id,{'cancelled','error'})['state'],'cancelled');self.assertFalse(list(self.service.output.iterdir()))
 def test_failure_cleanup_and_names(self):
  self.network_failure=True;id=self.options();self.service.start(id);self.assertEqual(self.wait(id,{'error'})['state'],'error');self.assertTrue(self.created[0].closed);self.assertFalse(list(self.service.base.iterdir()));self.assertFalse(list(self.service.output.iterdir()))
  self.assertEqual(safe_name('NUL'),'Contenido');self.assertNotIn('/',safe_name('../../bad/name'))
  with self.assertRaises(ValueError):self.service.prepare('../bad')
 def test_queue_parallel_parts_and_cancel_waiting(self):
  self.gate=threading.Event();self.slow=True
  first=self.options();self.service.start(first)
  deadline=time.monotonic()+3
  while self.running<3 and time.monotonic()<deadline:time.sleep(.02)
  self.assertEqual(self.peak,3)
  second=self.service.prepare('a'*20,'3')['id'];self.wait(second,{'options'});self.service.start(second)
  self.assertEqual(self.service.status(second)['state'],'queued');self.assertEqual(next(j for j in self.service.listing()['items'] if j['id']==second)['queue_position'],1)
  self.assertEqual(self.service.cancel(second)['state'],'cancelled');self.gate.set();self.wait(first,{'ready','error'})
  self.assertEqual(self.service.status(first)['state'],'ready');self.assertEqual(self.peak,3)
 def test_history_missing_file_and_destination_snapshot(self):
  first=self.options();self.service.start(first);self.assertEqual(self.wait(first,{'ready','error'})['state'],'ready')
  path=self.service.file(first);self.assertTrue(self.service.status(first)['file_exists']);old=path.parent
  folder=self.root/'different';self.service.set_folder(str(folder));self.assertEqual(self.service.file(first).parent,old)
  self.service.close();self.service.worker.join(2)
  restored=DownloadService(self.root,self.portal,ffmpeg_factory=lambda _:str(FF));self.addCleanup(restored.close)
  self.assertEqual(restored.output,folder);self.assertTrue(restored.status(first)['file_exists']);path.unlink();self.assertFalse(restored.status(first)['file_exists'])
  with self.assertRaises(ValueError):restored.file(first)
  restored.forget(first);self.assertFalse(restored.listing()['items']);self.assertFalse(path.exists())
 def test_forget_keeps_exported_file(self):
  id=self.options();self.service.start(id);self.wait(id,{'ready','error'});path=self.service.file(id)
  self.service.forget(id);self.assertTrue(path.exists())
 def test_interrupted_state_restored_without_grant_or_automatic_network(self):
  self.service.close();self.service.worker.join(2)
  id='c'*32
  self.service.ledger.write_text(json.dumps({'output':str(self.service.output),'jobs':[{'id':id,'name':'Example','state':'downloading','destination':str(self.service.output),'filename':None}]}))
  restored=DownloadService(self.root,self.portal);self.addCleanup(restored.close)
  self.assertEqual(restored.status(id)['state'],'interrupted');self.assertNotIn('source',restored.jobs[id])
 def test_unconfirmed_options_never_enter_history(self):
  id=self.options();self.assertEqual(self.service.listing()['items'],[])
  self.service.cancel(id);self.assertEqual(self.service.listing()['items'],[])
  payload=json.loads(self.service.ledger.read_text());self.assertEqual(payload['jobs'],[])
  restored=DownloadService(self.root,self.portal);self.addCleanup(restored.close)
  self.assertEqual(restored.listing()['items'],[])
 def test_cancel_confirmed_download_keeps_history(self):
  self.gate=threading.Event()
  id=self.options();self.service.start(id);self.service.cancel(id);self.gate.set()
  self.wait(id,{'cancelled'});items=self.service.listing()['items']
  self.assertEqual(len(items),1);self.assertEqual(items[0]['state'],'cancelled')
 def test_default_mkv_preserves_video_audio_packets_and_subtitles(self):
  id=self.options();self.service.start(id,1,0);result=self.wait(id,{'ready','error'})
  self.assertEqual(result['state'],'ready',result);self.assertEqual(result['format'],'mkv');path=self.service.file(id);self.assertEqual(path.suffix,'.mkv')
  probe=subprocess.run([str(FF),'-hide_banner','-i',str(path),'-t','0','-f','null','-'],capture_output=True).stderr.decode()
  self.assertIn('matroska',probe);self.assertIn('(eng): Audio: aac',probe);self.assertIn('Subtitle: subrip',probe)
  def packet_hash(file,stream):
   return subprocess.run([str(FF),'-v','error','-i',str(file),'-map',stream,'-c','copy','-f','adts','-'],capture_output=True,check=True).stdout.strip()
  def frames(file):
   text=subprocess.run([str(FF),'-v','error','-i',str(file),'-map','0:v:0','-f','framemd5','-'],capture_output=True,check=True).stdout.decode()
   return [line.rsplit(',',1)[-1].strip() for line in text.splitlines() if line and not line.startswith('#')]
  self.assertEqual(frames(self.root/'fixture.ts'),frames(path))
  self.assertEqual(packet_hash(self.root/'fixture.ts','0:a:1'),packet_hash(path,'0:a:0'))
  self.assertIn('Texto de prueba',self.service.file(id,True).read_text())
  from downloads import export_arguments
  args=export_arguments(str(FF),'in.ts','out.mkv',0,'hevc',container='mkv');self.assertEqual(args[args.index('-c:v')+1],'copy');self.assertEqual(args[args.index('-c:a')+1],'copy');self.assertNotIn('libx264',args)
if __name__=='__main__':unittest.main()

