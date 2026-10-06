import copy
import tempfile
import unittest
from pathlib import Path
import core

def document(scenes=None):
    return {'version':1,'duration':10.0,'video':'test.mp4','fingerprint':{'sha256':'abc','size':1},'scenes':scenes or []}

def scene(a,b,category='gore'):
    return {'start':a,'end':b,'category':category,'enabled':True,'reviewed':False,'action':'skip'}

class Tests(unittest.TestCase):
    def test_padding_merges_overlaps_and_clamps(self):
        self.assertEqual(core.cuts(document([scene(0,1),scene(2,4),scene(3,5),scene(9,10)]),padding=.5),[(0,5.5),(8.5,10)])
    def test_category_and_enabled_filters(self):
        disabled=scene(7,8);disabled['enabled']=False
        self.assertEqual(core.cuts(document([scene(1,2),scene(3,4,'blood'),disabled]),{'gore'}),[(1,2)])
        self.assertEqual(core.cuts(document([scene(1,2)]),set()),[])
    def test_complement(self):
        self.assertEqual(core.kept_ranges(10,[(0,1),(3,5),(9,10)]),[(1,3),(5,9)])
    def test_full_cut_cannot_play_original(self):
        with self.assertRaises(ValueError):core.mpv_edl('test.mp4',document([scene(0,10)]))
    def test_fingerprint_mismatch(self):
        with self.assertRaises(ValueError):core.validate(document(),{'sha256':'other','size':1})
    def test_invalid_ranges(self):
        for a,b in [(-1,3),(4,4),(5,2),(0,11),(float('nan'),3),(0,float('inf'))]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):core.validate(document([scene(a,b)]))
    def test_edl_formats(self):
        doc=document([scene(2,4)])
        self.assertEqual(core.kodi_edl(doc),'2.000 4.000 0\n')
        result=core.mpv_edl('a,é;%.mp4',doc)
        path=str(Path('a,é;%.mp4').resolve()).replace('\\','/')
        self.assertIn(f'%{len(path.encode())}%{path},0.000000,2.000000',result)
        self.assertTrue(result.endswith(',4.000000,6.000000\n'))
    def test_time_parser(self):
        self.assertEqual(core.timestamp('01:02:03.500'),3723.5)
        self.assertEqual(core.clock(59.9999),'00:01:00.000')
        for t in ['NaN','-1','1:60','1:2:3:4']:
            with self.assertRaises(ValueError):core.timestamp(t)
    def test_atomic_roundtrip(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'scenes.json';doc=document([scene(1,2)])
            core.save(p,doc);self.assertEqual(json.loads(p.read_text()),doc)

if __name__=='__main__':unittest.main()
