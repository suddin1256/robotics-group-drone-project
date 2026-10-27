from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import start

class PerformanceModes(unittest.TestCase):
    def args(self, **changes):
        data=dict(reuse_existing=True,portable=False,bag='recording',rate=1,demo=False,
                  replay=None,enable_flight=False,no_slam=False,vision=True,
                  vision_mode='split',slam_all_frames=False)
        data.update(changes)
        return SimpleNamespace(**data)

    def test_split_models_are_separate_processes(self):
        jobs,_=start.plan(self.args())
        jobs=dict(jobs)
        self.assertEqual(jobs['vision'][-1],'objects')
        self.assertEqual(jobs['depth'][-1],'depth')
        self.assertNotIn('--max-fps',jobs['vision'])

    def test_objects_only_does_not_start_depth(self):
        jobs,_=start.plan(self.args(vision_mode='objects-only'))
        self.assertNotIn('depth',dict(jobs))

    def test_ordered_slam_requires_updated_adapter(self):
        jobs,binary=start.plan(self.args(slam_all_frames=True))
        self.assertEqual(binary,ROOT/'build/adapter-legacy/tello_live_slam')
        self.assertIn('--ordered-input',dict(jobs)['slam'])

    def test_ordered_slam_rejected_for_live_source(self):
        result=subprocess.run([sys.executable,str(ROOT/'start.py'),'--slam-all-frames','--dry-run'],capture_output=True)
        self.assertEqual(result.returncode,2)

if __name__=='__main__':unittest.main()
