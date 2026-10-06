import unittest
from player import source_time,playback_time

class MappingTests(unittest.TestCase):
    def test_filtered_timeline_maps_to_source(self):
        ranges=[(0,2),(4,6)]
        self.assertEqual(source_time(2,ranges),4)
        self.assertEqual(source_time(3,ranges),5)
        self.assertEqual(playback_time(3,ranges),2)
        self.assertEqual(playback_time(5,ranges),3)
    def test_preview_offset(self):
        self.assertEqual(source_time(.5,[(10,20)]),10.5)
        self.assertEqual(playback_time(11,[(10,20)]),1)
    def test_end_is_bounded(self):
        self.assertEqual(source_time(100,[(2,4)]),4)
        self.assertLess(playback_time(100,[(2,4)]),2)

if __name__=='__main__':unittest.main()
