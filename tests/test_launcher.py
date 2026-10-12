import importlib.util
from pathlib import Path
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('launcher',ROOT/'start.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
class LauncherSafety(unittest.TestCase):
    def test_default_blocks_flight_flag(self):
        from types import SimpleNamespace
        jobs,_=launcher.plan(SimpleNamespace(reuse_existing=False,replay=None,enable_flight=False,no_slam=True))
        self.assertNotIn('--enable-flight',jobs[0][1])
    def test_replay_never_selects_hardware_driver(self):
        from types import SimpleNamespace
        jobs,_=launcher.plan(SimpleNamespace(reuse_existing=False,replay='sample.avi',enable_flight=False,no_slam=True))
        self.assertIn(str(ROOT/'ros/replay.py'),jobs[0][1])
        self.assertFalse(any('tello_manual_launch.py' in item for item in jobs[0][1]))
    def test_replay_and_flight_rejected_before_start(self):
        result=subprocess.run([sys.executable,str(ROOT/'start.py'),'--replay','sample.avi','--enable-flight','--dry-run'],capture_output=True)
        self.assertEqual(result.returncode,2)
if __name__=='__main__':unittest.main()
