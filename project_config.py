"""Shared paths and dependency fingerprint; no third-party imports."""
import hashlib
import json
from pathlib import Path
import platform
import shutil

ROOT = Path(__file__).resolve().parent
STATE = ROOT / '.local/setup.json'
CORE = ROOT / 'environments/core/pixi.toml'

def host_platform(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == 'Darwin' and machine in {'arm64', 'aarch64'}:
        return 'osx-arm64'
    if system == 'Darwin' and machine in {'x86_64', 'amd64'}:
        return 'osx-64'
    if system == 'Linux' and machine in {'x86_64', 'amd64'}:
        return 'linux-64'
    if system == 'Windows':
        raise RuntimeError('On Windows, open Ubuntu in WSL2 and run python3 bootstrap.py there. See docs/team-setup.md.')
    raise RuntimeError(f'Unsupported platform: {system}/{machine}. Do not install another architecture by guessing.')

def pixi_executable():
    local = ROOT / '.tools/pixi'
    if local.is_file():
        return str(local)
    return shutil.which('pixi')

def fingerprint(features, host):
    files = ['environments/core/pixi.toml', 'environments/core/pixi.lock', 'dependencies.json']
    if 'vision' in features:
        files += ['vision/requirements-intel-mac.txt' if host == 'osx-64' else 'vision/requirements-portable.txt']
    if 'slam' in features:
        files += ['environments/slam/pixi.toml', 'environments/slam/pixi.lock',
                  'scripts/build_slam.py','slam/src/tello_live_slam/CMakeLists.txt',
                  'slam/src/tello_live_slam/main.cc']
    digest = hashlib.sha256()
    digest.update(json.dumps({'features': sorted(features), 'platform': host}).encode())
    for filename in files:
        digest.update(filename.encode())
        path = ROOT / filename
        digest.update(path.read_bytes() if path.exists() else b'MISSING')
    return digest.hexdigest()

def read_state():
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return None
