import unittest
import core,media
class AudioLogicTests(unittest.TestCase):
    def doc(self):return {'version':1,'duration':10.,'scenes':[]}
    def scene(self,action,**kw):return dict(start=2.,end=3.,category='test',action=action,enabled=True,reviewed=False,**kw)
    def test_audio_never_cuts_video(self):
        d=self.doc();d['scenes']=[self.scene('duck',level=0),self.scene('gain',gain_db=6)]
        self.assertEqual(core.cuts(d),[]);core.validate(d)
    def test_bad_levels_rejected(self):
        d=self.doc();d['scenes']=[self.scene('duck',level=2)]
        with self.assertRaises(ValueError):core.validate(d)
    def test_subtitle_cut_and_word_filter(self):
        d=self.doc();d['subtitles']=[dict(start=2,end=3,text='bad',precision='word'),dict(start=4,end=5,text='hello',precision='word')]
        d['scenes']=media.word_scenes(d['subtitles'],'bad',10,0)
        text=media.subtitle_text(d,[(1,10)])
        self.assertNotIn('bad',text);self.assertIn('00:00:03,000',text)
        d['scenes'][0]['enabled']=False;self.assertIn('bad',media.subtitle_text(d,[(0,10)]))
    def test_phrase_across_cues(self):
        d=self.doc();d['subtitles']=[dict(start=1,end=2,text='a bad',precision='cue'),dict(start=2,end=3,text='word here',precision='cue')]
        d['scenes']=media.word_scenes(d['subtitles'],'bad word',10,0)
        text=media.subtitle_text(d,[(0,10)])
        self.assertNotIn('bad',text);self.assertNotIn('word',text);self.assertIn('here',text)
    def test_whole_words_only(self):
        cues=[dict(start=0,end=1,text='class glass ass',precision='cue')]
        self.assertEqual(len(media.word_scenes(cues,'ass',2,10)),1)
    def test_normalization_does_not_undo_mute(self):
        d=self.doc();d['scenes']=[self.scene('duck',level=0),self.scene('gain',gain_db=3)]
        f=media.audio_filter(d,normalize=True)
        self.assertLess(f.index('dynaudnorm'),f.index('alimiter'));self.assertLess(f.index('alimiter'),f.index('volume=0.00000000'))
    def test_silence_not_amplified(self):
        self.assertEqual(media.level_scenes({'rms':[0]*100,'step':.05},5),[])
    def test_kodi_mute_and_no_gain(self):
        d=self.doc();d['scenes']=[self.scene('duck',level=0),self.scene('gain',gain_db=3)]
        self.assertEqual(core.kodi_edl(d),'2.000 3.000 1\n')
if __name__=='__main__':unittest.main()
