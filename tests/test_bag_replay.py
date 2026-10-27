import ast
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import start

class BagReplaySafety(unittest.TestCase):
    def test_bag_selects_reader_and_not_drone_or_video_replay(self):
        args=SimpleNamespace(reuse_existing=True,portable=False,bag='recording',rate=.5,
                             demo=False,replay=None,enable_flight=False,no_slam=False,vision=True)
        jobs,_=start.plan(args)
        source=dict(jobs)['source']
        self.assertIn(str(ROOT/'ros/bag_replay.py'),source)
        self.assertIn('0.5',source)
        self.assertFalse(any('tello_manual_launch.py' in value for value in source))
        self.assertIn('slam',dict(jobs));self.assertIn('vision',dict(jobs))

    def test_bag_flight_flag_rejected_before_start(self):
        result=subprocess.run([sys.executable,str(ROOT/'start.py'),'--bag','recording','--enable-flight','--dry-run'],capture_output=True)
        self.assertEqual(result.returncode,2)

    def test_bag_topic_allowlist_excludes_commands(self):
        tree=ast.parse((ROOT/'ros/bag_replay.py').read_text())
        assignment=next(node for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ALLOWED' for t in node.targets))
        topics={key.value for key in assignment.value.keys}
        self.assertEqual(topics,{'/tello/image_raw','/tello/telemetry','/tello/control_status'})
        self.assertNotIn('/tello/manual_control',topics)

    def test_multiple_replay_sources_rejected(self):
        result=subprocess.run([sys.executable,str(ROOT/'start.py'),'--bag','recording','--demo','--dry-run'],capture_output=True)
        self.assertEqual(result.returncode,2)

if __name__=='__main__':unittest.main()
