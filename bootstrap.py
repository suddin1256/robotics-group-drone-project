"""Hardware-aware setup. Re-run after dependency changes; code-only pulls need no setup."""
import argparse
import io
import json
import os
import re
from pathlib import Path
import subprocess
import ssl
import sys
import tarfile
import urllib.request
from project_config import ROOT, CORE, STATE, host_platform, pixi_executable, fingerprint, read_state

PIXI_VERSION = '0.81.0'

def run(command, env=None):
    print('+', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)

def install_pixi(host):
    found = pixi_executable()
    if found:
        version = subprocess.check_output([found,'--version'],text=True)
        numbers = re.search(r'(\d+)\.(\d+)\.(\d+)',version)
        if numbers and tuple(map(int,numbers.groups())) >= (0,81,0):
            return found
        print('Existing Pixi is older than the project baseline; installing a local copy.')
    target = {'osx-64': 'x86_64-apple-darwin', 'osx-arm64': 'aarch64-apple-darwin',
              'linux-64': 'x86_64-unknown-linux-musl'}[host]
    url = f'https://github.com/prefix-dev/pixi/releases/download/v{PIXI_VERSION}/pixi-{target}.tar.gz'
    print('Downloading Pixi from official prefix-dev release:', url, flush=True)
    certificate = Path('/etc/ssl/cert.pem')
    context = ssl.create_default_context(cafile=str(certificate)) if certificate.is_file() else ssl.create_default_context()
    with urllib.request.urlopen(url, context=context, timeout=120) as response:
        archive = response.read()
    destination = ROOT / '.tools/pixi'
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Extract only the executable's bytes; never extract archive paths/symlinks.
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        members = [m for m in bundle.getmembers() if m.isfile() and Path(m.name).name == 'pixi']
        if len(members) != 1:
            raise RuntimeError('Unexpected Pixi archive layout.')
        with bundle.extractfile(members[0]) as executable:
            destination.write_bytes(executable.read())
    destination.chmod(0o755)
    return str(destination)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vision', action='store_true', help='Install V4 packages and cache model weights')
    parser.add_argument('--hardware', action='store_true', help='Install TelloPy for direct drone access')
    parser.add_argument('--slam', action='store_true', help='Experimental pinned Stella source build (can take a while)')
    parser.add_argument('--check', action='store_true', help='Report dependency status without installing')
    parser.add_argument('--dry-run', action='store_true', help='Describe platform/features without installing')
    args = parser.parse_args()
    host = host_platform()
    previous = read_state() or {}
    features = set(previous.get('features', [])) | {'core'}
    if args.vision:
        features.add('vision')
    if args.hardware:
        features.add('hardware')
    if args.slam:
        features.add('slam')
    print('Platform:', host, '| Features:', ', '.join(sorted(features)))
    if args.dry_run:
        return 0
    if args.check:
        matches = previous.get('platform') == host and previous.get('fingerprint') == fingerprint(features, host)
        print('Dependencies current.' if matches else 'Setup missing or dependencies changed. Run python3 bootstrap.py again.')
        return 0 if matches else 1
    pixi = install_pixi(host)
    run([pixi, 'install', '--manifest-path', CORE, '--locked'])
    core_python = [pixi, 'run', '--manifest-path', CORE, 'python']
    run(core_python + ['-c', 'import rclpy, cv2, av, numpy; from cv_bridge import CvBridge; print("ROS/video imports OK")'])
    if 'slam' in features:
        run([pixi,'install','--manifest-path',ROOT/'environments/slam/pixi.toml','--locked'])
        run([sys.executable,ROOT/'scripts/build_slam.py'])
    if 'hardware' in features:
        deps = json.loads((ROOT / 'dependencies.json').read_text())['tellopy']
        run(core_python + ['-m', 'pip', 'install', '--no-deps', f"git+{deps['url']}@{deps['commit']}"])
        run(core_python + ['-c', 'import tellopy; assert hasattr(tellopy.Tello, "manual_takeoff"); print("TelloPy import OK; no connection started")'])
    if 'vision' in features:
        venv = ROOT / 'vision/.venv'
        python = venv / 'bin/python'
        marker = venv / '.tello-platform'
        if python.exists() and marker.exists() and marker.read_text().strip() != host:
            raise RuntimeError('Vision environment belongs to another platform. Move it aside and re-run setup.')
        if not python.exists():
            run(core_python + ['-m', 'venv', venv])
        requirement = ROOT / 'vision' / ('requirements-intel-mac.txt' if host == 'osx-64' else 'requirements-portable.txt')
        # Avoid downloading CUDA packages for the initial Linux/WSL CPU baseline.
        if host == 'linux-64':
            run([python, '-m', 'pip', 'install', 'torch==2.5.1', 'torchvision==0.20.1',
                 '--index-url', 'https://download.pytorch.org/whl/cpu'])
        run([python, '-m', 'pip', 'install', '-r', requirement])
        marker.write_text(host)
        # Setup is online; normal runs will use the cache offline.
        env = dict(os.environ)
        env.pop('HF_HUB_OFFLINE', None)
        env.pop('TRANSFORMERS_OFFLINE', None)
        run([python, ROOT / 'vision/worker.py', '--prepare'], env=env)
    STATE.parent.mkdir(exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps({'platform': host, 'features': sorted(features),
                                     'fingerprint': fingerprint(features, host)}, indent=2))
    temporary.replace(STATE)
    print('\nSetup passed. No drone connection was started.')
    print('Start demo: python3 start.py --demo --no-slam' + (' --vision' if 'vision' in features else ''))
    print('Dashboard: http://127.0.0.1:8082')
    print('Use your own video with --replay /path/to/video.avi; demo patterns are not a SLAM/vision accuracy test.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print(f'Setup failed: {error}', file=sys.stderr)
        raise SystemExit(1)
