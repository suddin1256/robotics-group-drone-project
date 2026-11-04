import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('frame_io', ROOT/'vision/frame_io.py')
frame_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frame_io)
spec = importlib.util.spec_from_file_location('depth_anything', ROOT/'vision/depth_anything.py')
depth_anything = importlib.util.module_from_spec(spec)
spec.loader.exec_module(depth_anything)
spec = importlib.util.spec_from_file_location('launcher_vision', ROOT/'start.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

class VisionIntegration(unittest.TestCase):
    def packet(self, stamp=99, width=320, height=240):
        return struct.pack('<dII', stamp, width, height) + bytes(width*height*3)

    def test_packet_accepts_fresh_and_rejects_duplicate_stale_or_truncated(self):
        path = Mock()
        path.read_bytes.return_value = self.packet()
        with patch.object(frame_io.time, 'time', return_value=100):
            self.assertEqual(frame_io.read_packet(path)[1:3], (320, 240))
            self.assertIsNone(frame_io.read_packet(path, previous=99))
        with patch.object(frame_io.time, 'time', return_value=110):
            self.assertIsNone(frame_io.read_packet(path))
        path.read_bytes.return_value = self.packet()[:-1]
        self.assertIsNone(frame_io.read_packet(path))

    def test_missing_frame_is_normal_waiting_state(self):
        path = Mock()
        path.read_bytes.side_effect = FileNotFoundError
        self.assertIsNone(frame_io.read_packet(path))

    def test_depth_anything_input_is_patch_aligned_and_keeps_aspect(self):
        self.assertEqual(depth_anything.input_shape(320, 240), (322, 238))
        self.assertEqual(depth_anything.input_shape(1280, 720, 266), (476, 266))
        for width, height in [(320, 240), (640, 480), (100, 7)]:
            columns, rows = depth_anything.input_shape(width, height)
            self.assertEqual((columns % 14, rows % 14), (0, 0))
            self.assertGreaterEqual(min(columns, rows), 14)

    def test_optional_vision_is_separate_process_with_no_flight_flag(self):
        jobs, _ = launcher.plan(SimpleNamespace(reuse_existing=True, replay='sample.avi',
                                               enable_flight=False, no_slam=True, vision=True))
        vision = dict(jobs)['vision']
        self.assertEqual(Path(vision[0]), ROOT/'vision/.venv/bin/python')
        self.assertNotIn('--enable-flight', vision)
        self.assertNotIn('slam', dict(jobs))

if __name__ == '__main__':
    unittest.main()
