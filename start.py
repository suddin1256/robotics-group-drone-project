"""One launcher; no flight unless --enable-flight is supplied."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

def plan(args):
    ros = Path.home() / 'Documents/tello-ros2' if args.reuse_existing else ROOT / 'ros'
    slam = Path.home() / 'Documents/tello-slam' if args.reuse_existing else ROOT / 'slam'
    binary = slam / 'build/live/tello_live_slam' if args.reuse_existing else ROOT / 'build/live/tello_live_slam'
    run = ['pixi', 'run', '--manifest-path', str(ros / 'pixi.toml'), 'python']
    if args.replay:
        source = run + [str(ROOT / 'ros/replay.py'), str(Path(args.replay).resolve())]
    else:
        source = run + [str(ROOT / 'ros/tello_manual_launch.py')]
        if args.enable_flight: source += ['--enable-flight']
    jobs = [('source', source),
            ('bridge', run + [str(ROOT / 'ros/slam_frame_bridge.py')]),
            ('dashboard', run + [str(ROOT / 'ros/flight_dashboard.py')])]
    if not args.no_slam:
        jobs.append(('slam', ['pixi','run','--manifest-path',str(slam/'pixi.toml'),str(binary)]))
    return jobs, binary

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enable-flight', action='store_true')
    p.add_argument('--replay', metavar='VIDEO')
    p.add_argument('--reuse-existing', action='store_true', help='Use original Mac environments and compiled SLAM')
    p.add_argument('--no-slam', action='store_true')
    p.add_argument('--dry-run', action='store_true', help='Print startup plan; start nothing')
    args = p.parse_args()
    if args.replay and args.enable_flight: p.error('Replay cannot enable flight.')
    jobs, binary = plan(args)
    if args.dry_run:
        for name, command in jobs: print(name, command)
        return
    if args.replay and not Path(args.replay).is_file(): p.error('Replay video does not exist.')
    if not args.no_slam and not binary.is_file(): p.error('Build SLAM first, or use --no-slam.')
    work = ROOT / 'runtime'
    (work / 'live').mkdir(parents=True, exist_ok=True)
    (work / 'assets').mkdir(exist_ok=True)
    import shutil
    shutil.copy2(ROOT/'slam/assets/tello_320_dense.yaml',work/'assets/tello_320_dense.yaml')
    vocabulary = (Path.home()/'Documents/tello-slam/assets/orb_vocab.fbow') if args.reuse_existing else ROOT/'slam/assets/orb_vocab.fbow'
    if not args.no_slam:
        if not vocabulary.is_file(): p.error('Missing ORB vocabulary; run setup.py first.')
        shutil.copy2(vocabulary,work/'assets/orb_vocab.fbow')
    # Never display a previous session as a current live map.
    for name in ['map.json','telemetry.json','frame.bin','video.jpg','preview.jpg']:
        (work/'live'/name).unlink(missing_ok=True)
    env = dict(os.environ, TELLO_RUNTIME_DIR=str(work/'live'), ROS_DOMAIN_ID='42')
    children=[]; handles=[]
    (ROOT/'logs').mkdir(exist_ok=True)
    stamp=time.strftime('%Y%m%d_%H%M%S')
    stopping=False
    def stop(signum, frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    try:
        for name, command in jobs:
            handle=(ROOT/'logs'/f'{stamp}_{name}.log').open('w')
            handles.append(handle)
            process=subprocess.Popen(command,cwd=work,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
            children.append((name,process))
        print('Dashboard: http://127.0.0.1:8082 | logs:', ROOT/'logs', flush=True)
        print('Flight ENABLED' if args.enable_flight else 'Flight disabled / replay; motor arming blocked',flush=True)
        print('Land before closing. Ctrl+C requests shutdown; it cannot guarantee landing after link loss.',flush=True)
        while not stopping:
            for name, child in children:
                if child.poll() is not None:
                    raise RuntimeError(f'{name} exited ({child.returncode}); inspect its log.')
            time.sleep(0.2)
    except RuntimeError as error:
        print(error,file=sys.stderr)
    finally:
        # Keep command input running while the driver requests landing.
        ordered=sorted(children,key=lambda item: item[0]!='source')
        for name, child in ordered:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGINT)
                try: child.wait(timeout=18 if name=='source' else 8)
                except subprocess.TimeoutExpired:
                    print(f'{name} did not stop; terminating process. Confirm drone is landed.',file=sys.stderr)
                    os.killpg(child.pid,signal.SIGTERM)
                    try: child.wait(timeout=3)
                    except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL)
        for handle in handles: handle.close()

if __name__ == '__main__': main()
