import ast
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import project_config
import start

class PortableSetup(unittest.TestCase):
    def test_platform_detection(self):
        for system, cpu, expected in [('Darwin','arm64','osx-arm64'), ('Darwin','x86_64','osx-64'), ('Linux','x86_64','linux-64')]:
            self.assertEqual(project_config.host_platform(system,cpu),expected)
        with self.assertRaisesRegex(RuntimeError,'WSL2'):
            project_config.host_platform('Windows','AMD64')
        with self.assertRaisesRegex(RuntimeError,'Unsupported'):
            project_config.host_platform('Linux','aarch64')

    def test_portable_demo_uses_repo_manifest_and_never_driver(self):
        args=SimpleNamespace(reuse_existing=False,portable=True,demo=True,replay=None,
                             enable_flight=False,no_slam=True,vision=False)
        jobs,_=start.plan(args)
        command=dict(jobs)['source']
        self.assertIn(str(project_config.CORE),command)
        self.assertIn('--locked',command)
        self.assertIn('--demo',command)
        self.assertFalse(any('tello_manual_launch.py' in item for item in command))

    def test_demo_rejects_flight_before_any_process_starts(self):
        result=subprocess.run([sys.executable,str(ROOT/'start.py'),'--demo','--enable-flight','--dry-run'],capture_output=True)
        self.assertEqual(result.returncode,2)

    def test_fingerprint_changes_when_dependency_content_changes(self):
        with patch.object(Path,'exists',return_value=True), patch.object(Path,'read_bytes',return_value=b'first'):
            first=project_config.fingerprint(['core'],'osx-arm64')
        with patch.object(Path,'exists',return_value=True), patch.object(Path,'read_bytes',return_value=b'second'):
            self.assertNotEqual(first,project_config.fingerprint(['core'],'osx-arm64'))

    def test_all_application_python_parses(self):
        for path in list(ROOT.glob('*.py')) + [ROOT/'scripts/build_slam.py']:
            ast.parse(path.read_text())
        for directory in [ROOT/'ros',ROOT/'vision']:
            for path in directory.glob('*.py'):
                ast.parse(path.read_text())

if __name__=='__main__':unittest.main()
