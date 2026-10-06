import unittest
from unittest.mock import patch
from pathlib import Path
import media

class PlaybackAudioTests(unittest.TestCase):
    def doc(self,action='replace'):
        return {'duration':4,'scenes':[dict(start=1,end=2,action=action,enabled=True,replacement='Darn!',text='bad')],
                'subtitles':[dict(start=1,end=2,text='bad',precision='word')]}
    @patch('replacements.prepare',return_value=Path('C:/cache/test.wav'))
    def test_seek_crops_replacement_without_shifting_mute(self,_):
        graph=media.audio_filter(self.doc(),replacement_start=1.25)
        self.assertIn('between(t,1.000000,2.000000)',graph)
        self.assertIn('atrim=start=0.250000:duration=0.750000',graph)
        self.assertIn('adelay=0:',graph)
    def test_sidebar_matches_treatment(self):
        self.assertEqual(media.display_subtitles(self.doc())[0]['text'],'Darn!')
        self.assertEqual(media.display_subtitles(self.doc('bleep')),[])
        doc=self.doc();doc['scenes'][0]['enabled']=False
        self.assertEqual(media.display_subtitles(doc)[0]['text'],'bad')
    def test_manual_word_replacement(self):
        doc=self.doc();doc['scenes'][0].pop('text')
        self.assertIn('Darn!',media.subtitle_text(doc,[(0,4)]))
