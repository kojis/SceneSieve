import threading
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import scanner

class Capture:
    def set(self,*args):pass
    def read(self):return True,np.zeros((8,8,3),dtype=np.uint8)
    def release(self):pass

class ScanTests(unittest.TestCase):
    @patch('scanner.request')
    def test_rejects_unknown_model_labels(self,request):
        request.return_value={'response':'{"categories":["made-up"]}'}
        with self.assertRaises(ValueError):scanner.classify(np.zeros((8,8,3),dtype=np.uint8),'local',['gore'])
    @patch('scanner.request')
    def test_local_vision_models_only(self,request):
        request.side_effect=[{'models':[{'name':'remote-cloud'},{'name':'local'}]},{'capabilities':['vision']}]
        self.assertEqual(scanner.local_models(),['local'])
    @patch('scanner.cv2.VideoCapture',return_value=Capture())
    @patch('scanner.local_models',return_value=['test'])
    @patch('scanner.classify',return_value=['gore'])
    def test_segments_are_merged_and_unreviewed(self,*_):
        results=scanner.scan('video',4,'test',['gore'],2,threading.Event(),lambda _:None)
        self.assertEqual(len(results),1)
        self.assertEqual((results[0]['start'],results[0]['end']),(0,4))
        self.assertFalse(results[0]['reviewed'])
    @patch('scanner.cv2.VideoCapture',return_value=Capture())
    @patch('scanner.local_models',return_value=['test'])
    def test_cancellation_in_flight_discards_results(self,*_):
        event=threading.Event()
        def classify(*args,**kwargs):event.set();return []
        with patch('scanner.classify',side_effect=classify),self.assertRaises(InterruptedError):
            scanner.scan('video',1,'test',['gore'],2,event,lambda _:None)
    @patch('scanner.request')
    def test_empty_grammar_result_retries_json(self,request):
        request.side_effect=[{'response':''},{'done_reason':'unload'},{'response':'{"categories":["gore"]}'}]
        self.assertEqual(scanner.classify(np.zeros((8,8,3),dtype=np.uint8),'local',['gore'],strict_gore=False),['gore'])
        self.assertEqual(request.call_args_list[1].args[1],{'model':'local','keep_alive':0})
        self.assertEqual(request.call_args_list[2].args[1]['format'],'json')
    @patch('scanner.request')
    def test_grammar_failures_fall_back_to_validated_plain_json(self,request):
        request.side_effect=[scanner.ModelResponseError('invalid API response'),{}, {'response':'not json'},
                             {'response':'```json\n{"categories": []}\n```'}]
        self.assertEqual(scanner.classify(np.zeros((8,8,3),dtype=np.uint8),'local',['gore']),[])
        self.assertNotIn('format',request.call_args_list[3].args[1])
    @patch('scanner.request')
    def test_empty_results_never_mean_no_gore(self,request):
        request.return_value={'response':'   '}
        with self.assertRaisesRegex(scanner.ModelResponseError,'after 3 attempts'):
            scanner.classify(np.zeros((8,8,3),dtype=np.uint8),'local',['gore'])
        self.assertEqual(request.call_count,4)  # Three classifications and one unload.
    def test_invalid_response_shapes(self):
        for value in ['', '[]', '{}', '{"categories":null}', '{"categories":[1]}', '{"categories":["unknown"]}']:
            with self.subTest(value=value),self.assertRaises(scanner.ModelResponseError):
                scanner.parse_categories({'response':value},['gore'])
    @patch('scanner.request')
    def test_cancel_before_retry(self,request):
        event=threading.Event()
        def fail(*args):event.set();return {'response':''}
        request.side_effect=fail
        with self.assertRaises(InterruptedError):
            scanner.classify(np.zeros((8,8,3),dtype=np.uint8),'local',['gore'],cancelled=event)
        self.assertEqual(request.call_count,1)
    @patch('scanner.cv2.VideoCapture',return_value=Capture())
    @patch('scanner.local_models',return_value=['test'])
    def test_resume_reuses_success_and_retries_failure(self,*_):
        with tempfile.TemporaryDirectory() as cache:
            args=('video',6,'test',['gore'],2,threading.Event(),lambda _:None)
            with patch('scanner.classify',side_effect=[[],scanner.ModelResponseError('failed')]):
                with self.assertRaisesRegex(scanner.ModelResponseError,'Completed frames are saved'):
                    scanner.scan(*args,cache_dir=cache,identity={'sha256':'abc'})
            with patch('scanner.classify',return_value=[]) as classify:
                self.assertEqual(scanner.scan(*args,cache_dir=cache,identity={'sha256':'abc'}),[])
                self.assertEqual(classify.call_count,2)
            with patch('scanner.classify',return_value=[]) as classify:
                float_args=('video',6.0,'test',['gore'],2.0,threading.Event(),lambda _:None)
                scanner.scan(*float_args,cache_dir=cache,identity={'sha256':'abc'})
                classify.assert_not_called()
            with patch('scanner.classify',return_value=[]) as classify:
                scanner.scan(*args,cache_dir=cache,identity={'sha256':'different-video'})
                self.assertEqual(classify.call_count,3)
    def test_checkpoint_settings_and_corruption(self):
        with tempfile.TemporaryDirectory() as cache:
            a=scanner.Checkpoint(cache,{'sha256':'abc'},6,'model-a',['gore'],2)
            a.record(0,[])
            b=scanner.Checkpoint(cache,{'sha256':'abc'},6,'model-b',['gore'],2)
            self.assertEqual(b.observations,{})
            a.path.write_text('{corrupt',encoding='utf-8')
            restored=scanner.Checkpoint(cache,{'sha256':'abc'},6,'model-a',['gore'],2)
            self.assertEqual(restored.observations,{})
    @patch('scanner._classify_frame')
    def test_strict_gore_rejects_unconfirmed_gore_keeps_blood(self,classify):
        classify.side_effect=[['gore','blood'],[],['blood']]
        self.assertEqual(scanner.classify(None,'model',['gore','blood']),['blood'])
    @patch('scanner._classify_frame')
    def test_strict_gore_keeps_specific_injury(self,classify):
        classify.side_effect=[['gore'],['exposed internal organs']]
        self.assertEqual(scanner.classify(None,'model',['gore']),['gore'])
    @patch('scanner._classify_frame')
    def test_verification_for_other_categories(self,classify):
        classify.return_value=['violence']
        self.assertEqual(scanner.classify(None,'model',['gore','violence']),['violence'])
        self.assertEqual(classify.call_count,2)
    @patch('scanner._classify_frame')
    def test_verification_failure_not_treated_as_clear(self,classify):
        classify.side_effect=[['gore'],scanner.ModelResponseError('failed')]
        with self.assertRaises(scanner.ModelResponseError):scanner.classify(None,'model',['gore'])
    def test_strict_setting_has_separate_checkpoint(self):
        with tempfile.TemporaryDirectory() as cache:
            a=scanner.Checkpoint(cache,{'sha256':'abc'},6,'model',['gore'],2,True)
            b=scanner.Checkpoint(cache,{'sha256':'abc'},6,'model',['gore'],2,False)
            self.assertNotEqual(a.path,b.path)

if __name__=='__main__':unittest.main()

class PreciseCategoryTests(unittest.TestCase):
    @patch('scanner._classify_frame',side_effect=[['nudity','drugs'],['drugs']])
    def test_generic_verification_removes_unconfirmed_matches(self,classify):
        self.assertEqual(scanner.classify(None,'model',['nudity','drugs']),['drugs'])
    @patch('scanner._classify_frame',return_value=['nudity'])
    def test_disabled_precise_mode_skips_extra_pass(self,classify):
        self.assertEqual(scanner.classify(None,'model',['nudity'],strict_gore=False),['nudity'])
        classify.assert_called_once()
