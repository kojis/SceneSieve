import unittest,tempfile,struct
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
import models,subtitle_sources as subs,player_exports as exports
class DiscoveryExportTests(unittest.TestCase):
 def doc(self):return {'version':1,'duration':6,'scenes':[dict(start=2,end=4,action='skip',category='gore',enabled=True,reviewed=True),dict(start=1,end=5,action='bleep',category='word',enabled=True,reviewed=True)]}
 def test_group_models(self):
  groups=models.group_variants(['gemma3:4b','gemma3:12b','qwen3-vl:2b']);self.assertEqual(len(groups),2);self.assertEqual(len(groups['gemma3']),2)
 def test_moviehash(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'v.mkv';p.write_bytes(struct.pack('<Q',1)*16384)
   self.assertEqual(subs.movie_hash(p),f'{131072+16384:016x}')
 def test_title_guess(self):self.assertEqual(subs.title_guess('The.Movie.2024.1080p.mkv'),'The Movie')
 def test_mplayer_nonoverlapping(self):
  self.assertEqual(exports.export_text('MPlayer EDL','x.mkv',self.doc(),{'gore'},0),'1.000 2.000 1\n2.000 4.000 0\n4.000 5.000 1\n')
 def test_vlc_intervals(self):
  root=ET.fromstring(exports.export_text('VLC playlist','a & b.mp4',self.doc(),{'gore'},0));options=[e.text for e in root.iter() if e.tag.endswith('}option')]
  self.assertEqual(options,['start-time=0.000000','stop-time=2.000000','start-time=4.000000','stop-time=6.000000'])
 def test_mpv_intervals(self):self.assertIn(',4.000000,2.000000',exports.export_text('mpv EDL','a.mp4',self.doc(),{'gore'},0))
 def test_warning(self):self.assertIn('become mutes',exports.limitation('Kodi EDL',self.doc()));self.assertIn('cuts only',exports.limitation('VLC playlist',self.doc()))
 @patch('subtitle_sources.request')
 @patch('subtitle_sources.movie_hash',return_value='1234')
 def test_opensubtitles_matching_contract(self,hash,request):
  request.return_value={'data':[{'attributes':{'moviehash_match':True,'language':'en','feature_details':{'title':'Movie'},'files':[{'file_name':'a.srt','file_id':42}]}}]}
  results=subs.search_opensubtitles('video.mkv','Movie','en','test-key');self.assertEqual(results[0]['match'],'File hash match');self.assertIn('moviehash=1234',request.call_args.args[0])
 @patch('media.download_subtitles',return_value=[{'text':'hi'}])
 @patch('subtitle_sources.request',return_value={'link':'https://example.com/test.srt'})
 def test_opensubtitles_download_contract(self,request,download):
  self.assertTrue(subs.download({'provider':'OpenSubtitles','file_id':42},6,'test-key'));self.assertEqual(request.call_args.args[1],{'file_id':42})
if __name__=='__main__':unittest.main()
