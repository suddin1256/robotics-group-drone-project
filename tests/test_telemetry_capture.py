from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ros'))
from telemetry_capture import plain, previous_sample

class CaptureTests(unittest.TestCase):
    def test_no_future_or_stale_measurement_attached_to_frame(self):
        values=[{'received_stamp_ns':1_000_000_000}, {'received_stamp_ns':2_000_000_000}]
        self.assertIsNone(previous_sample(values,900_000_000)['sample'])
        self.assertEqual(previous_sample(values,1_100_000_000)['sample'],values[0])
        self.assertIsNone(previous_sample(values,1_500_000_000)['sample'])

    def test_nested_log_and_raw_payload_retained_without_logger(self):
        value=SimpleNamespace(log=object(),imu=SimpleNamespace(acc_x=1.5),payload=b'\x01\x02',invalid=float('nan'))
        result=plain(value)
        self.assertNotIn('log',result)
        self.assertEqual(result['payload'],{'hex':'0102'})
        self.assertEqual(result['imu']['acc_x'],1.5)
        self.assertIsNone(result['invalid'])
