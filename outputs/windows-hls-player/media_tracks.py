"""Inspect authorized TS, select tracks and convert locally when decoding fails."""
import re,subprocess,sys,urllib.parse,http.client,os
from pathlib import Path

def ffmpeg(root):
    if not os.environ.get('XUPERPC_PORTABLE_ROOT'):sys.path.insert(0,str(Path(root)/'work/ffmpeg-tools'))
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def audio_tracks(root,body):
    p=subprocess.run([ffmpeg(root),'-nostdin','-hide_banner','-i','pipe:0','-map','0:a?','-c','copy','-t','0','-f','null','-'],input=body,capture_output=True,timeout=15)
    text=p.stderr.decode('utf8','replace').split('Stream mapping:')[0];tracks=[]
    for line in text.splitlines():
        m=re.search(r'Stream #0:\d+\[(0x[0-9a-fA-F]+)\](?:\(([^)]+)\))?: Audio: ([^,]+)',line)
        if m:tracks.append({'index':len(tracks),'pid':int(m[1],16),'language':m[2] or 'und','codec':m[3].strip()})
    return tracks

_compat_encoders=__import__('threading').BoundedSemaphore(2)

def compatible_segment(root,body,audio=0):
    """Convert a single indexed GOP to independently decodable H.264/AAC TS."""
    if type(audio) is not int or not 0<=audio<=32:raise ValueError('Invalid audio index')
    with _compat_encoders:
        result=subprocess.run([ffmpeg(root),'-nostdin','-hide_banner','-loglevel','error',
            '-i','pipe:0','-map','0:v:0','-map','0:a:'+str(audio)+'?',
            '-c:v','libx264','-preset','ultrafast','-crf','22','-pix_fmt','yuv420p',
            '-c:a','aac','-b:a','128k','-ac','2','-avoid_negative_ts','make_zero',
            '-mpegts_flags','+resend_headers','-muxdelay','0','-f','mpegts','pipe:1'],
            input=body,capture_output=True,timeout=45,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode or not result.stdout or len(result.stdout)>32*1024*1024:
        raise ValueError('Compatibility conversion failed')
    return result.stdout

def mpeg_crc(data):
    crc=0xffffffff
    for value in data:
        crc^=value<<24
        for _ in range(8):crc=((crc<<1)^0x04c11db7 if crc&0x80000000 else crc<<1)&0xffffffff
    return crc.to_bytes(4,'big')

def select_audio(root,body,index,tracks=None):
    """Keep original PES/PTS; rewrite single-packet PMTs and drop other audio PIDs.

    Tiny index ranges may have no audio frames. Filtering, unlike independent
    FFmpeg muxers, keeps those ranges valid and preserves continuity counters.
    """
    tracks=tracks if tracks is not None else audio_tracks(root,body)
    if not 0<=index<len(tracks) or len(body)%188:raise ValueError('Invalid audio selection/TS framing')
    keep=tracks[index]['pid'];drop={t['pid'] for t in tracks if t['pid']!=keep};out=bytearray()
    for offset in range(0,len(body),188):
        packet=bytearray(body[offset:offset+188])
        if packet[0]!=0x47:raise ValueError('Invalid TS sync')
        pid=((packet[1]&31)<<8)|packet[2]
        if pid in drop:continue
        afc=(packet[3]>>4)&3;start=4
        if afc in (2,3):start+=1+packet[4]
        if afc in (1,3) and start<188 and packet[1]&0x40:
            section=start+1+packet[start]
            if section+12<=188 and packet[section]==2:
                size=3+(((packet[section+1]&15)<<8)|packet[section+2]);end=section+size
                if end>188:raise ValueError('Unsupported multi-packet PMT')
                data=packet[section:end]
                if mpeg_crc(data[:-4])!=bytes(data[-4:]):raise ValueError('Invalid PMT CRC')
                cursor=12+(((data[10]&15)<<8)|data[11]);selected=bytearray(data[:cursor])
                while cursor<len(data)-4:
                    length=5+(((data[cursor+3]&15)<<8)|data[cursor+4]);entry_pid=((data[cursor+1]&31)<<8)|data[cursor+2]
                    if cursor+length>len(data)-4:raise ValueError('Invalid PMT stream descriptor')
                    if entry_pid not in drop:selected.extend(data[cursor:cursor+length])
                    cursor+=length
                length=len(selected)+4-3;selected[1]=(selected[1]&240)|(length>>8);selected[2]=length&255
                selected.extend(mpeg_crc(selected));packet[section:]=selected+b'\xff'*(188-section-len(selected))
        out.extend(packet)
    if not out:raise ValueError('Selected audio has no TS data')
    return bytes(out)

SUB_HOSTS={'vpnwqk.k9ijj2.com','joqotx.p27i1en9.com','dio3ka.lpsyujwj.xyz'}
def subtitle_tracks(episode):
    tracks=[]
    for entry in episode.get('subtitleList',[]):
        for file in entry.get('file',[]):
            raw=file.get('url','');u=urllib.parse.urlsplit(raw)
            if (u.scheme in ('http','https') and u.hostname in SUB_HOSTS and not u.username and not u.password and not u.query and not u.fragment
                and u.port in (None,80 if u.scheme=='http' else 443) and re.fullmatch(r'/public/subs/[A-Za-z0-9-]+\.(srt|vtt)',u.path)):
                tracks.append({'language':entry.get('language') or 'und','url':raw});break
    return tracks

def webvtt(body):
    text=body.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
    if text.lstrip().startswith('WEBVTT'):return text.lstrip().encode('utf8')
    text=re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})',r'\1.\2',text)
    if not re.search(r'\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}',text):raise ValueError('Unsupported subtitle format')
    return ('WEBVTT\n\n'+text.strip()+'\n').encode('utf8')

def fetch_subtitle(track):
    u=urllib.parse.urlsplit(track['url'])
    if u.hostname not in SUB_HOSTS or not re.fullmatch(r'/public/subs/[A-Za-z0-9-]+\.(srt|vtt)',u.path):raise ValueError('Unrecognized public subtitle')
    # Both original public artwork CDNs were verified to serve these same
    # subtitle objects. Use their validated TLS endpoints: the legacy subtitle
    # hostname resolves to an unrelated Azure gateway in system DNS.
    for host in ['joqotx.p27i1en9.com','dio3ka.lpsyujwj.xyz']:
        connection=http.client.HTTPSConnection(host,timeout=10)
        try:
            connection.request('GET',u.path,headers={'Connection':'close'})
            response=connection.getresponse();body=response.read(2*1024*1024+1)
            if response.status==200 and len(body)<=2*1024*1024:return webvtt(body)
        except (TimeoutError,ConnectionError):pass
        finally:connection.close()
    raise ValueError('Subtitle unavailable')
