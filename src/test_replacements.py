import unittest
from pathlib import Path
from unittest.mock import patch
import core,media,replacements
class ReplacementTests(unittest.TestCase):
    def scene(self,action):return dict(start=1.,end=2.,action=action,category='spoken word',enabled=True,reviewed=False,replacement='Darn!',frequency=1000,replacement_level=.15,text='bad')
    def test_replacements_do_not_cut(self):
        d={'version':1,'duration':4,'scenes':[self.scene('bleep'),self.scene('replace')]}
        self.assertEqual(core.cuts(d),[])
        self.assertEqual(core.kodi_edl(d).count('1.000 2.000 1'),2)
    def test_substitute_in_subtitles(self):
        cues=[dict(start=1,end=2,text='bad',precision='word')]
        scenes=media.word_scenes(cues,'bad',4,0);scenes[0].update(action='replace',replacement='Darn!')
        text=media.subtitle_text({'scenes':scenes,'subtitles':cues},[(0,4)])
        self.assertIn('Darn!',text);self.assertNotIn('bad',text)
        scenes[0]['enabled']=False;self.assertIn('bad',media.subtitle_text({'scenes':scenes,'subtitles':cues},[(0,4)]))
    def test_invalid_replacement(self):
        s=self.scene('replace');s['replacement']=''
        with self.assertRaises(ValueError):core.validate({'version':1,'duration':4,'scenes':[s]})
    @patch('replacements.prepare',return_value=Path('C:/cache/test.wav'))
    def test_export_after_cut_uses_clip_offset(self,_):
        graph=media.audio_filter({'scenes':[self.scene('replace')]},start=1.5)
        self.assertIn('atrim=start=0.500000:duration=0.500000',graph)
        self.assertIn('volume=0:',graph)
    @patch('replacements.prepare',return_value=Path('C:/cache/test.wav'))
    def test_overlap_does_not_double_replacement_volume(self,_):
        scene=self.scene('bleep')
        graph=media.audio_filter({'scenes':[scene,dict(scene)]})
        self.assertEqual(graph.count('amovie='),1)
if __name__=='__main__':unittest.main()
