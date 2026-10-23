"""Portable, bounded parser for Ranger's observed version-0 TS IDXG index."""
import math,re,struct

def parse_idxg(body):
    if not isinstance(body,bytes) or not 64<=len(body)<=4*1024*1024:raise ValueError('IDXG outside bounds')
    if body[4:8]!=b'idxg' or struct.unpack_from('>I',body)[0]!=len(body) or body[8:12]!=bytes(4):raise ValueError('Unsupported IDXG box/version')
    size=body[12];base=13+size
    if not size or base+38>len(body):raise ValueError('Truncated IDXG header')
    name=body[13:base].decode('ascii')
    if not re.fullmatch(r'[A-Fa-f0-9]{32}\.ts',name):raise ValueError('Unsupported media filename')
    total,duration=struct.unpack_from('>QI',body,base)
    if not 0<total<=32*1024**3 or not 0<duration<=48*3600*1000:raise ValueError('Invalid movie size/duration')
    count=struct.unpack_from('>I',body,base+34)[0];start=base+38
    if not 1<=count<=100000 or start+count*12!=len(body):raise ValueError('Invalid IDXG record count')
    points=[struct.unpack_from('>IQ',body,start+i*12) for i in range(count)]
    if points[0]!=(0,0):raise ValueError('Unsupported initial index point')
    if any(t>=duration or off>=total or off%188 for t,off in points):raise ValueError('Invalid TS index point')
    if any(t2<=t1 or o2<=o1 for (t1,o1),(t2,o2) in zip(points,points[1:])):raise ValueError('Non-monotonic index')
    segments=[]
    for i,(time_ms,offset) in enumerate(points):
        end_ms,end=points[i+1] if i+1<count else (duration,total)
        segments.append({'offset':offset,'length':end-offset,'time_ms':time_ms,'duration_ms':end_ms-time_ms})
    return {'filename':name,'size':total,'duration_ms':duration,'video_codec':body[base+18:base+22].rstrip(b'\0').decode('ascii'),
        'width':struct.unpack_from('>H',body,base+26)[0],'height':struct.unpack_from('>H',body,base+28)[0],'segments':segments}

def hls_playlist(index,prefix):
    if not re.fullmatch(r'/vod/[a-f0-9]{20,32}(/audio/\d+)?/segment',prefix):raise ValueError('Expected opaque local VOD segment route')
    segments=index['segments'];target=math.ceil(max(x['duration_ms'] for x in segments)/1000)
    lines=['#EXTM3U','#EXT-X-VERSION:3','#EXT-X-PLAYLIST-TYPE:VOD','#EXT-X-TARGETDURATION:'+str(target),'#EXT-X-MEDIA-SEQUENCE:0']
    for i,s in enumerate(segments):lines+=['#EXTINF:'+format(s['duration_ms']/1000,'.3f')+',',prefix+'/'+str(i)+'.ts']
    lines.append('#EXT-X-ENDLIST');return ('\n'.join(lines)+'\n').encode('ascii')
