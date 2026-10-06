import tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
import media

class NaturalReplacementTests(unittest.TestCase):
    def test_spoken_tail_is_mixed_beyond_original_mute(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'phrase.wav'
            with wave.open(str(path),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0'*32000)
            scene=dict(start=1,end=1.2,enabled=True,action='replace')
            with patch('replacements.prepare',return_value=path):
                graph=media.audio_filter({'scenes':[scene]},replacement_start=1.5)
            self.assertIn('between(t,1.000000,1.200000)',graph)
            self.assertIn('atrim=start=0.500000:duration=1.500000',graph)
            self.assertIn('adelay=0:',graph)
