import unittest
from unittest.mock import patch
import core,media,visual_effects,playback_audio,player_exports

def scene(action,start=1,end=3,enabled=True,category='test'):
    return dict(action=action,start=start,end=end,enabled=enabled,category=category,reviewed=False)

def document(*scenes):return dict(version=1,duration=5,scenes=list(scenes))

class EffectTests(unittest.TestCase):
    def test_actions_round_trip_and_only_skip_removes_time(self):
        for action in (*visual_effects.ACTIONS,'distort'):
            doc=document(scene(action));core.validate(doc)
            self.assertEqual(core.cuts(doc),[])
        self.assertEqual(visual_effects.OPTIONS[0],('Skip','skip'))

    def test_overlap_precedence_and_skip_keep_source_clock(self):
        doc=document(scene('blur',0,4),scene('pixelate',1,2),scene('freeze',2,4),scene('skip',2.5,3))
        plan=visual_effects.segments(doc,core.kept_ranges(5,core.cuts(doc)))
        self.assertEqual([(a,b,e['action'] if e else None) for a,b,e in plan],
                         [(0,1,'blur'),(1,2,'pixelate'),(2,2.5,'freeze'),(3,4,'freeze'),(4,5,None)])
        self.assertEqual(plan[3][2]['start'],2)

    def test_selection_disabled_and_padding(self):
        doc=document(scene('blur',1,2),scene('freeze',0,5,False),scene('pixelate',2,4,category='other'))
        effects=visual_effects.scenes(doc,{'test'},.5)
        self.assertEqual([(s['start'],s['end'],s['action']) for s in effects],[(.5,2.5,'blur')])
        self.assertEqual(visual_effects.scenes(doc,set()),[])

    def test_distort_redacts_subtitles_and_sidecars_fallback_to_mute(self):
        doc=document({**scene('distort'),'text':'bad'})
        doc['subtitles']=[dict(start=1,end=2,text='a bad word',precision='cue')]
        self.assertIn('a word',media.subtitle_text(doc,[(0,5)]))
        self.assertEqual(core.kodi_edl(doc),'1.000 3.000 1\n')
        self.assertEqual(player_exports.mplayer_edl(doc,None,0),'1.000 3.000 1\n')
        self.assertIn('Freeze frame',player_exports.limitation('Kodi EDL',doc))

    @patch('media.export_media',return_value='preview.mp4')
    def test_video_preview_renders_even_without_audio(self,export):
        doc=document(scene('freeze'))
        result=playback_audio.prepare('preview.mp4','source',doc,{'test'},0,print,None,True)
        self.assertEqual(result,'preview.mp4')
        self.assertFalse(export.call_args.args[-1])

    def test_distort_keeps_source_offset(self):
        graph=media.audio_filter(document(scene('distort')),start=.5)
        self.assertIn('between(t,0.500000,2.500000)',graph)
        self.assertIn('val(ch)',graph)
