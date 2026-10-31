from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ros'))
from motion_comparison import MotionComparison

class ComparisonTests(unittest.TestCase):
    def test_original_clock_and_no_duplicate_cached_records(self):
        c=MotionComparison()
        c.observe('/tello/control_status',{'stamp_ns':10_000_000_000,'phase':'airborne'},10_000_000_000)
        d={'received_stamp_ns':11_000_000_000,'data':{'imu':{'count':1,'acc_x':2},'mvo':{'count':0}}}
        c.observe('/tello/raw_log',d,99_000_000_000)
        c.observe('/tello/raw_log',d,100_000_000_000)
        c.image(12_000_000_000)
        result=c.snapshot(12_000_000_000)
        self.assertEqual(result['imu'][0][:2],[1.,2])
        self.assertEqual(len(result['imu']),1)
        self.assertEqual(result['mvo'],[])
        self.assertEqual(result['image_time'],2.)

    def test_missing_values_remain_null_and_history_is_bounded(self):
        c=MotionComparison(limit=2)
        for i in range(4):
            c.observe('/tello/raw_log',{'data':{'mvo':{'count':i,'pos_x':float('nan')}}},i*1_000_000_000)
        self.assertEqual(len(c.mvo),2)
        self.assertIsNone(c.mvo[-1][1])

    def test_image_age_and_validity_are_not_replaced_by_replay_age(self):
        c=MotionComparison()
        c.observe('/tello/image_metadata',{'image_stamp_ns':123,'flight':{'age_ms':900,'valid':False},
                                          'log':{'age_ms':20,'valid':True}},123)
        self.assertEqual(c.ages[0][1:],[900,False,20,True])

if __name__=='__main__':unittest.main()
