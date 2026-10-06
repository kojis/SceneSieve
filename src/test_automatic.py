import unittest,tempfile,threading
from pathlib import Path
from unittest.mock import patch
import scanner,automated_mode,presets
class AutomaticTests(unittest.TestCase):
    def test_categories_exclude_only_insects(self):
        self.assertEqual(automated_mode.automatic_categories(),[v for k,(_,v) in presets.VIDEO.items() if k!='Insects and Spiders'])
        self.assertNotIn('bugs and spiders',automated_mode.automatic_categories())
    @patch('scanner._classify_frame',return_value=['gore'])
    def test_inclusive_policy_keeps_uncertain_without_verification(self,classify):
        self.assertEqual(scanner.classify(None,'model',['gore'],precision=0),['gore']);self.assertEqual(classify.call_count,1)
        self.assertIn('ambiguous',classify.call_args.kwargs['prompt'])
    @patch('scanner._classify_frame',side_effect=[['gore'],[]])
    def test_precise_policy_requires_confirmation(self,classify):
        self.assertEqual(scanner.classify(None,'model',['gore'],precision=100),[]);self.assertEqual(classify.call_count,2)
    def test_checkpoints_are_isolated_by_slider_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            a=scanner.Checkpoint(folder,{},10,'model',['gore'],.5,precision=0)
            b=scanner.Checkpoint(folder,{},10,'model',['gore'],.5,precision=100)
            self.assertNotEqual(a.path,b.path)
    def test_pipeline_covers_all_word_presets_and_skips_matches(self):
        with patch('scanner.probe',return_value=10),patch('core.fingerprint',return_value={}),patch('local_ai.start'),patch('models.ensure_model'),patch('scanner.scan',return_value=[]) as scan,patch('media.probe',return_value=[{'codec_type':'audio'}]),patch('media.transcribe',return_value=[dict(start=2,end=3,text='fuck',precision='word')]) as transcribe:
            doc=automated_mode.process('video.mp4','model',lambda _:None,threading.Event())
        self.assertEqual(scan.call_args.args[4],.5);self.assertEqual(scan.call_args.kwargs['precision'],0)
        self.assertEqual(doc['scenes'][0]['action'],'skip');self.assertEqual(doc['automatic_settings']['audio_presets'],list(presets.AUDIO))
    def test_scan_failure_is_not_returned_as_complete(self):
        with patch('scanner.probe',return_value=10),patch('core.fingerprint',return_value={}),patch('local_ai.start'),patch('models.ensure_model'),patch('scanner.scan',side_effect=RuntimeError('failed')):
            with self.assertRaisesRegex(RuntimeError,'failed'):automated_mode.process('video.mp4','model',lambda _:None,threading.Event())
