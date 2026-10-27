"""One launcher; no flight unless --enable-flight is supplied."""
import argparse
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from project_config import CORE, fingerprint, host_platform, pixi_executable, read_state

ROOT = Path(__file__).resolve().parent

def plan(args):
    ros = Path.home() / 'Documents/tello-ros2' if args.reuse_existing else ROOT / 'ros'
    portable = not args.reuse_existing and (getattr(args, 'portable', False) or read_state() is not None)
    manifest = CORE if portable else ros / 'pixi.toml'
    slam = Path.home() / 'Documents/tello-slam' if args.reuse_existing else ROOT / 'slam'
    slam_manifest = ROOT / 'environments/slam/pixi.toml' if portable else slam / 'pixi.toml'
    binary = slam / 'build/live/tello_live_slam' if args.reuse_existing else ROOT / 'build/live/tello_live_slam'
    if getattr(args, 'slam_all_frames', False):
        binary = ROOT/'build/adapter-legacy/tello_live_slam' if args.reuse_existing else ROOT/'build/live/tello_live_slam'
    executable = pixi_executable() or 'pixi'
    run = [executable, 'run', '--manifest-path', str(manifest), 'python']
    if portable:
        run.insert(2, '--locked')
    if getattr(args, 'bag', None):
        source = run + [str(ROOT / 'ros/bag_replay.py'), str(Path(args.bag).resolve()),
                        '--rate', str(getattr(args, 'rate', 1.0))]
    elif getattr(args, 'demo', False):
        source = run + [str(ROOT / 'ros/replay.py'), '--demo']
    elif args.replay:
        source = run + [str(ROOT / 'ros/replay.py'), str(Path(args.replay).resolve())]
    else:
        source = run + [str(ROOT / 'ros/tello_manual_launch.py')]
        if args.enable_flight: source += ['--enable-flight']
    jobs = [('source', source),
            ('bridge', run + [str(ROOT / 'ros/slam_frame_bridge.py')]),
            ('dashboard', run + [str(ROOT / 'ros/flight_dashboard.py')])]
    if not args.no_slam:
        command = [executable,'run','--manifest-path',str(slam_manifest),str(binary)]
        if getattr(args,'slam_all_frames',False): command += ['--ordered-input','live/slam-input.bin']
        jobs.append(('slam', command))
    if getattr(args, 'vision', False):
        python = str(ROOT/'vision/.venv/bin/python')
        mode = getattr(args,'vision_mode','split')
        if mode == 'combined':
            jobs.append(('vision',[python,str(ROOT/'vision/worker.py')]))
        else:
            jobs.append(('vision',[python,str(ROOT/'vision/stage_worker.py'),'--stage','objects']))
            if mode == 'split':
                jobs.append(('depth',[python,str(ROOT/'vision/stage_worker.py'),'--stage','depth']))
    return jobs, binary

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enable-flight', action='store_true')
    p.add_argument('--replay', metavar='VIDEO')
    p.add_argument('--bag', metavar='BAG_FOLDER', help='Replay real recorded images/telemetry; no drone driver')
    p.add_argument('--rate', type=float, default=1.0, help='ROS bag playback speed, default 1.0')
    p.add_argument('--duration', type=float, help='Stop offline replay/demo automatically after this many seconds')
    p.add_argument('--runtime-dir', type=Path, help='Separate runtime workspace for offline tests')
    p.add_argument('--port', type=int, default=8082, help='Local dashboard port')
    p.add_argument('--demo', action='store_true', help='Built-in synthetic camera/telemetry; no drone or recording needed')
    p.add_argument('--portable', action='store_true', help='Use the shared core environment installed by bootstrap.py')
    p.add_argument('--reuse-existing', action='store_true', help='Use original Mac environments and compiled SLAM')
    p.add_argument('--no-slam', action='store_true')
    p.add_argument('--vision', action='store_true', help='Optional V4 segmentation and relative depth')
    p.add_argument('--vision-mode', choices=['split','objects-only','combined'], default='split',
                   help='Independent YOLO/depth by default; combined retains original V4 behavior')
    p.add_argument('--slam-all-frames', action='store_true', help='Bag only: feed every recorded frame to SLAM in order, even if it falls behind')
    p.add_argument('--dry-run', action='store_true', help='Print startup plan; start nothing')
    args = p.parse_args()
    offline = bool(args.replay or args.demo or args.bag)
    if offline and args.enable_flight: p.error('Replay/demo/bag cannot enable flight.')
    if sum(map(bool, [args.replay, args.demo, args.bag])) > 1: p.error('Choose --demo, --replay or --bag, not multiple sources.')
    if not math.isfinite(args.rate) or args.rate <= 0: p.error('--rate must be positive and finite.')
    if args.duration is not None and (not offline or not math.isfinite(args.duration) or args.duration <= 0): p.error('--duration requires offline replay and a positive finite duration.')
    if args.runtime_dir is not None and not offline: p.error('--runtime-dir is for offline testing only.')
    if not 1 <= args.port <= 65535: p.error('Invalid dashboard port.')
    if args.slam_all_frames and (not args.bag or args.no_slam): p.error('--slam-all-frames requires --bag with SLAM enabled.')
    if args.portable and args.reuse_existing: p.error('--portable and --reuse-existing select different environments.')
    jobs, binary = plan(args)
    if args.dry_run:
        for name, command in jobs: print(name, command)
        return
    if os.name == 'nt': p.error('Use Ubuntu in WSL2 on Windows. See docs/team-setup.md.')
    state = read_state() if not args.reuse_existing else None
    if args.portable and state is None: p.error('Run python3 bootstrap.py first.')
    if state is not None:
        host = host_platform()
        if state.get('platform') != host or state.get('fingerprint') != fingerprint(state.get('features', []), host):
            p.error('Dependencies changed or this setup belongs to another laptop. Run python3 bootstrap.py again.')
        if args.vision and 'vision' not in state.get('features', []): p.error('Run python3 bootstrap.py --vision first.')
        if not offline and 'hardware' not in state.get('features', []): p.error('Run python3 bootstrap.py --hardware for direct Tello access.')
    if args.vision and not (ROOT/'vision/.venv/bin/python').is_file(): p.error('Vision environment missing; see docs/vision.md.')
    if args.replay and not Path(args.replay).is_file(): p.error('Replay video does not exist.')
    if args.bag and not Path(args.bag).is_dir(): p.error('Bag folder does not exist.')
    if args.slam_all_frames:
        command = [sys.executable,str(ROOT/'scripts/build_slam_adapter.py')]
        if args.reuse_existing: command += ['--reuse-existing']
        try: subprocess.run(command,check=True)
        except subprocess.CalledProcessError: p.error('Could not rebuild the ordered SLAM adapter; inspect compiler output.')
    if not args.no_slam and not binary.is_file(): p.error('Build SLAM first, or use --no-slam.')
    work = args.runtime_dir.resolve() if args.runtime_dir else ROOT / 'runtime'
    (work / 'live').mkdir(parents=True, exist_ok=True)
    (work / 'assets').mkdir(exist_ok=True)
    import shutil
    shutil.copy2(ROOT/'slam/assets/tello_320_dense.yaml',work/'assets/tello_320_dense.yaml')
    vocabulary = (Path.home()/'Documents/tello-slam/assets/orb_vocab.fbow') if args.reuse_existing else ROOT/'slam/assets/orb_vocab.fbow'
    if not args.no_slam:
        if not vocabulary.is_file(): p.error('Missing ORB vocabulary; run setup.py first.')
        shutil.copy2(vocabulary,work/'assets/orb_vocab.fbow')
    # Never display a previous session as a current live map.
    for name in ['map.json','telemetry.json','frame.bin','video.jpg','preview.jpg','vision.jpg','vision-status.json','playback.json',
                 'depth.jpg','depth-status.json','slam-status.json','slam-input.bin','slam-input.done']:
        (work/'live'/name).unlink(missing_ok=True)
    env = dict(os.environ, TELLO_RUNTIME_DIR=str(work/'live'), ROS_DOMAIN_ID='43' if args.bag else '42')
    env['TELLO_PLAYBACK_ONLY'] = '1' if args.bag else '0'
    env['TELLO_WAIT_FOR_VISION'] = '1' if args.bag and args.vision else '0'
    env['TELLO_VISION_SPLIT'] = '1' if args.vision and args.vision_mode == 'split' else '0'
    env['TELLO_SLAM_ORDERED'] = '1' if args.slam_all_frames else '0'
    env['TELLO_DASHBOARD_PORT'] = str(args.port)
    env.setdefault('HF_HUB_OFFLINE', '1')
    env.setdefault('TRANSFORMERS_OFFLINE', '1')
    children=[]; handles=[]
    (ROOT/'logs').mkdir(exist_ok=True)
    (ROOT/'logs/ros').mkdir(exist_ok=True)
    env['ROS_LOG_DIR'] = str(ROOT/'logs/ros')
    stamp=time.strftime('%Y%m%d_%H%M%S')
    stopping=False
    failed_optional=set()
    def stop(signum, frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    exit_code=0
    try:
        for name, command in jobs:
            handle=(ROOT/'logs'/f'{stamp}_{name}.log').open('w')
            handles.append(handle)
            process=subprocess.Popen(command,cwd=work,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
            children.append((name,process))
        print(f'Dashboard: http://127.0.0.1:{args.port} | logs:', ROOT/'logs', flush=True)
        if args.bag: print('BAG PLAYBACK: ROS domain 43; controls disabled; original recording is read-only.', flush=True)
        print('Flight ENABLED' if args.enable_flight else 'Flight disabled / replay; motor arming blocked',flush=True)
        print('Land before closing. Ctrl+C requests shutdown; it cannot guarantee landing after link loss.',flush=True)
        deadline = time.monotonic() + args.duration if args.duration else None
        while not stopping:
            if deadline is not None and time.monotonic() >= deadline:
                break
            for name, child in children:
                if name in failed_optional: continue
                if child.poll() is not None and name in {'vision','depth'}:
                    print(f'{name} worker exited; camera/control continue. See its log.', flush=True)
                    failed_optional.add(name)
                    continue
                if child.poll() is not None:
                    raise RuntimeError(f'{name} exited ({child.returncode}); inspect its log.')
            time.sleep(0.2)
    except RuntimeError as error:
        print(error,file=sys.stderr)
        exit_code=1
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
    return exit_code

if __name__ == '__main__': raise SystemExit(main())
