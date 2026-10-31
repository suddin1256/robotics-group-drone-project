import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vision'))
from floorplan_worker import match, merge, summarize


class FloorPlanTests(unittest.TestCase):
    def test_exact_frame_and_mask_support_required(self):
        d={'source_stamp': 10., 'objects':[{'label':'chair','confidence':.9,
                                          'polygon':[[0,0],[10,0],[10,10],[0,10]]}]}
        o={'source_stamp': 10., 'features':[[i,i+1,3] for i in range(6)]+[[99,20,20]]}
        result=match(d,o)
        self.assertEqual(result[0]['ids'],set(range(6)))
        o['source_stamp']=10.01
        self.assertEqual(match(d,o),[])
        o['source_stamp']=10.
        d['objects'][0]['label']='person'
        self.assertEqual(match(d,o),[])

    def test_instances_merge_by_shared_landmarks_not_just_class(self):
        tracks=[]
        for ids in [set(range(6)),set(range(3,9)),set(range(20,26))]:
            merge(tracks,{'label':'chair','ids':ids,'confidence':.9})
        self.assertEqual(len(tracks),2)
        self.assertEqual(tracks[0]['observations'],2)
        data={'landmark_ids':list(range(9)), 'points':[[i,0,i] for i in range(9)]}
        objects=summarize(tracks,data)
        self.assertEqual(len(objects),1)
        self.assertFalse(objects[0]['tentative'])
        # Updated map coordinates move the footprints, rather than freezing old poses.
        data['points']=[[i+100,0,i] for i in range(9)]
        self.assertGreater(summarize(tracks,data)[0]['min'][0],99)


if __name__=='__main__': unittest.main()
