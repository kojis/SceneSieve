import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import playback_audio

class SoundtrackTests(unittest.TestCase):
    def test_cache_invalidates_for_edits_cuts_and_source(self):
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/'video';video.write_bytes(b'original')
            doc={'duration':4,'scenes':[]}
            first=playback_audio.cache_path(folder,video,doc,{'gore'},0)
            self.assertEqual(first,playback_audio.cache_path(folder,video,doc,{'gore'},0))
            self.assertNotEqual(first,playback_audio.cache_path(folder,video,doc,{'gore'},.5))
            doc['scenes']=[{'action':'bleep','start':1,'end':2}]
            self.assertNotEqual(first,playback_audio.cache_path(folder,video,doc,{'gore'},0))
            second=playback_audio.cache_path(folder,video,doc,{'gore'},0)
            video.write_bytes(b'changed source')
            self.assertNotEqual(second,playback_audio.cache_path(folder,video,doc,{'gore'},0))

    @patch('media.export_media',return_value='audio.flac')
    @patch('media.probe',return_value=[{'codec_type':'audio'}])
    def test_preparation_uses_audio_export_with_normalization(self,probe,export):
        doc={'normalize_audio':True};progress=lambda text:None;cancel=threading.Event()
        self.assertEqual(playback_audio.prepare('audio.flac','video',doc,{'gore'},.5,progress,cancel),'audio.flac')
        export.assert_called_once_with('video',doc,'audio.flac',{'gore'},.5,True,progress,cancel,True)

    @patch('media.export_media')
    @patch('media.probe',return_value=[{'codec_type':'video'}])
    def test_silent_video_does_not_try_to_export_audio(self,probe,export):
        self.assertIsNone(playback_audio.prepare('audio.flac','video',{},set(),0,lambda text:None,None))
        export.assert_not_called()
