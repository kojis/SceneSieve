import unittest
from dialogue import excerpts

class DialogueTests(unittest.TestCase):
    def word(self,text,start,end):return dict(text=text,start=start,end=end,precision='word')
    def test_sentences_and_original_word_timings(self):
        cues=[self.word('Hello',0,.3),self.word('there.',.3,.8),self.word('Next',.9,1.1),self.word('line!',1.1,1.5)]
        grouped=excerpts(cues)
        self.assertEqual([c['text'] for c in grouped],['Hello there.','Next line!'])
        self.assertEqual(grouped[0]['end'],.8);self.assertEqual(cues[0]['end'],.3)
    def test_pause_and_existing_cues(self):
        cues=[self.word('Wait',0,.4),self.word('here',2,2.4),dict(text='Already a complete cue',start=3,end=4)]
        self.assertEqual(len(excerpts(cues)),3)
    def test_punctuation_and_long_passages(self):
        cues=[self.word('Hello',0,.2),self.word(',',.2,.3),self.word('friend!',.3,.7)]
        self.assertEqual(excerpts(cues)[0]['text'],'Hello, friend!')
        long=[self.word('example',i*.4,i*.4+.3) for i in range(60)]
        self.assertTrue(all(c['end']-c['start']<=7 and len(c['text'])<=110 for c in excerpts(long)))

if __name__=='__main__':unittest.main()
