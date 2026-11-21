import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ros'))
from telemetry_units import metric_metadata

class TelemetryUnitChecks(unittest.TestCase):
    def sample(self):
        return {'image_stamp_ns':10,'log':{'valid':True,'age_ms':20,'sample':{'data':{
            'recv_time':5.,'mvo':{'count':1,'recv_time':5.,'pos_x':2.,'pos_y':3.,'pos_z':-1.,'vel_x':10.,'vel_y':-5.,'vel_z':0.},
            'imu':{'count':1,'recv_time':5.,'acc_x':0.,'acc_y':0.,'acc_z':1.,'gyro_x':.2,'gyro_y':0.,'gyro_z':0.,'q0':1.,'q1':0.,'q2':0.,'q3':0.}}}}}
    def test_converts_once_without_mutating_or_flipping_raw_axes(self):
        source=self.sample();before=copy.deepcopy(source);a=metric_metadata(source);b=metric_metadata(source)
        self.assertEqual(source,before);self.assertEqual(a,b)
        self.assertEqual(a['position_native_m'],[2.,3.,-1.])
        self.assertEqual(a['velocity_native_m_s'],[1.,-.5,0.])
        self.assertAlmostEqual(a['acceleration_native_m_s2'][2],9.80665)
        self.assertEqual(a['angular_velocity_native_rad_s'],[.2,0.,0.])
        self.assertFalse(a['units_audit']['accuracy_verified'])
    def test_stale_cached_records_are_not_presented_as_fresh(self):
        s=self.sample();s['log']['sample']['data']['mvo']['recv_time']=4.
        s['log']['sample']['data']['imu']['recv_time']=4.
        d=metric_metadata(s);self.assertFalse(d['mvo_valid']);self.assertFalse(d['imu_valid'])
        self.assertIsNone(d['position_native_m']);self.assertIsNone(d['acceleration_native_m_s2'])
    def test_missing_and_nonfinite_fields_remain_unavailable(self):
        self.assertIsNone(metric_metadata({})['position_native_m'])
        s=self.sample();s['log']['sample']['data']['mvo']['pos_x']=float('nan')
        self.assertIsNone(metric_metadata(s)['position_native_m'])

if __name__=='__main__':unittest.main()
