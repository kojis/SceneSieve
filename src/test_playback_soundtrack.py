import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import playback_audio

def scene(action,a,b,**kw):return dict(action=action,start=a,end=b,category='test',enabled=True,reviewed=False,**kw)
class SoundtrackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name);self.video=self.folder/'source.mp4';self.video.write_bytes(b'source')
        self.doc=dict(version=1,duration=40,scenes=[scene('blur',2,4),scene('bleep',22,24)])
        self.calls=[]
        def render(video,doc,path,*args,**kwargs):self.calls.append(doc);Path(path).write_bytes(b'clip');return str(path)
        self.render=patch('media.export_media',side_effect=render);self.render.start();self.addCleanup(self.render.stop)
        self.probe=patch('media.probe',return_value=[{'codec_type':'video'},{'codec_type':'audio'}]);self.probe.start();self.addCleanup(self.probe.stop)
    def prepare(self):
        path=playback_audio.cache_path(self.folder,self.video,self.doc,{'test'},0)
        playback_audio.prepare(path,self.video,self.doc,{'test'},0,lambda _:None,threading.Event(),True)
        return path.read_text()
    def test_local_change_only_renders_changed_span(self):
        first=self.prepare();self.assertEqual(len(self.calls),2);self.assertIn(str(self.video).replace('\\','/'),first)
        self.doc['scenes'][0]['action']='pixelate';self.prepare()
        self.assertEqual(len(self.calls),3);self.assertEqual(self.calls[-1]['_preview_range'],[2,4])
    def test_review_and_subtitle_changes_reuse_all_clips(self):
        self.prepare();self.doc['scenes'][0]['reviewed']=True;self.doc['subtitles']=[dict(start=1,end=2,text='Hello')];self.prepare();self.assertEqual(len(self.calls),2)
    def test_preview_only_builds_overlapping_clip_and_reuses_it(self):
        self.doc['_preview_range']=[1,5];self.prepare();self.assertEqual(len(self.calls),1)
        del self.doc['_preview_range'];self.prepare();self.assertEqual(len(self.calls),2)
    def test_silent_audio_edit_uses_original_without_render(self):
        self.doc['scenes']=[scene('bleep',2,4)]
        with patch('media.probe',return_value=[{'codec_type':'video'}]):text=self.prepare()
        self.assertFalse(self.calls);self.assertIn(',0.000000,40.000000',text)
    def test_source_change_invalidates_clips(self):
        self.prepare();self.video.write_bytes(b'new source');self.prepare();self.assertEqual(len(self.calls),4)
    def test_disabled_effect_does_not_render(self):
        for s in self.doc['scenes']:s['enabled']=False
        self.prepare();self.assertFalse(self.calls)
    def test_speech_tail_remains_in_plan(self):
        self.doc['scenes']=[scene('replace',2,3,replacement='Long phrase')]
        with patch('replacements.duration',return_value=3):self.prepare()
        self.assertEqual(self.calls[0]['_preview_range'],[2,5])
    def test_long_effect_is_bounded_to_ten_second_chunks(self):
        self.doc['scenes']=[scene('blur',0,40)];self.prepare()
        self.assertEqual([s['_preview_range'] for s in self.calls],[[0,10],[10,20],[20,30],[30,40]])

    def test_normalization_reuses_cache_for_review_changes(self):
        self.doc['normalize_audio']=True;self.prepare();self.assertEqual(len(self.calls),1)
        self.doc['scenes'][0]['reviewed']=True;self.prepare();self.assertEqual(len(self.calls),1)
    def test_cancel_does_not_publish_incomplete_plan(self):
        cancel=threading.Event();cancel.set();path=self.folder/'cancelled.edl'
        with self.assertRaises(InterruptedError):playback_audio.prepare(path,self.video,self.doc,{'test'},0,lambda _:None,cancel)
        self.assertFalse(path.exists());self.assertFalse(self.calls)
