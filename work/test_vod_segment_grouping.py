import sys,unittest,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ranger_vod_index import playback_segments,parse_idxg,hls_playlist

def ranges(durations,lengths=None):
 result=[];offset=0;t=0
 for i,d in enumerate(durations):
  size=(lengths or [188]*len(durations))[i]
  result.append(dict(time_ms=t,duration_ms=d,offset=offset,length=size));t+=d;offset+=size
 return result
class SegmentTests(unittest.TestCase):
 def test_tiny_fragment_and_byte_timeline_are_preserved(self):
  original=ranges([668,1585,2335,417,4922,83,2086,2502,417,751,2920,1209])
  grouped=playback_segments(original)
  self.assertLess(len(grouped),len(original));self.assertFalse(any(s['duration_ms']==83 for s in grouped))
  self.assertEqual(sum(s['length'] for s in grouped),sum(s['length'] for s in original))
  self.assertEqual(sum(s['duration_ms'] for s in grouped),sum(s['duration_ms'] for s in original))
  for a,b in zip(grouped,grouped[1:]):
   self.assertEqual(a['offset']+a['length'],b['offset']);self.assertEqual(a['time_ms']+a['duration_ms'],b['time_ms'])
  self.assertEqual(original[0]['duration_ms'],668)
 def test_size_ceiling_and_gaps(self):
  grouped=playback_segments(ranges([100,100,100],[188*3]*3),max_bytes=188*4)
  self.assertEqual(len(grouped),3)
  gapped=ranges([100,100]);gapped[1]['offset']+=188
  self.assertEqual(len(playback_segments(gapped)),2)
 def test_parser_and_manifest_cover_whole_media(self):
  ds=[1000,83,2917,1000,3000,200];points=ranges(ds)
  header=bytearray(38);struct.pack_into('>QI',header,0,188*len(ds),sum(ds));header[18:22]=b'avc1';struct.pack_into('>HH',header,26,1280,720);struct.pack_into('>I',header,34,len(ds))
  name=b'a'*32+b'.ts';body=bytearray(b'\0'*4+b'idxg'+b'\0'*4+bytes([len(name)])+name+header)
  for p in points:body+=struct.pack('>IQ',p['time_ms'],p['offset'])
  struct.pack_into('>I',body,0,len(body));index=parse_idxg(bytes(body))
  self.assertEqual(sum(s['length'] for s in index['segments']),index['size']);self.assertEqual(sum(s['duration_ms'] for s in index['segments']),index['duration_ms'])
  playlist=hls_playlist(index,'/vod/'+'a'*24+'/segment').decode()
  self.assertIn('#EXTINF:4.000',playlist);self.assertTrue(playlist.endswith('#EXT-X-ENDLIST\n'));self.assertNotIn('#EXTINF:0.083',playlist)
if __name__=='__main__':unittest.main()
