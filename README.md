# Robotics group drone project

## Team quick start

On macOS or Ubuntu inside Windows WSL2, after installing Git and Python 3:

```sh
git clone https://github.com/suddin1256/robotics-group-drone-project.git
cd robotics-group-drone-project
python3 bootstrap.py --vision
python3 start.py --demo --no-slam --vision
```

Open **http://127.0.0.1:8082**. The first setup selects Intel Mac, Apple Silicon Mac or x86-64 Linux/WSL2 dependencies and prepares the models online. Omit `--vision` for a lighter ROS/dashboard-only install. Read **[platform setup instructions](docs/team-setup.md)** first, especially on Windows.

Demo images/telemetry are synthetic. For actual vision evaluation, replace `--demo` with `--replay /path/to/video.avi`. This does not need a drone. Replay/demo cannot enable flight.

## Shared updates

Real recorded camera/telemetry playback with dashboard, V4 and SLAM is available through `--bag`. See [ROS bag playback](docs/bag-playback.md). Playback never sends recorded flight-control requests to a drone.

Stop the program, then run:

```sh
python3 update.py
```

This pulls fast-forward changes, checks dependency fingerprints, and reruns setup only when dependencies changed. Selected features are remembered locally. Uncommitted edits cause it to stop rather than overwrite them. Code-only changes normally need no reinstall.

Everyone can clone the public repo. Direct pushes require GitHub collaborator invitations; use branches and pull requests as described in CONTRIBUTING.md.

## Current validation and limitations

- The shared ROS dependency lock resolved on Intel macOS, Apple Silicon macOS and Linux/WSL2.
- Eleven source/launcher tests passed. An end-to-end synthetic demo passed using the existing Intel Mac environment, including dashboard video, telemetry and flight-disabled status.
- Fresh installs/runtime on Apple Silicon and Windows/WSL2 still need teammate verification. Top-level vision packages are pinned; transitive vision dependencies and model weights are not fully locked/checksummed.
- **Stella's source build is optional and experimental:** run `python3 bootstrap.py --slam`. Cross-platform fresh builds/runtime are not yet verified. Use `--no-slam` until that laptop's build succeeds. The original Intel-Mac recipe is retained below.
- Hardware access is optional: `python3 bootstrap.py --hardware`, then `python3 start.py --no-slam` for ground-only live camera/telemetry. Flight additionally requires `--enable-flight`. Direct Tello networking on WSL2 remains unverified.
- Normal vision runs use cached Hugging Face files offline. Prepare models online before TELLO Wi-Fi.
- Shadib's existing `--reuse-existing` launch remains available and preserves the original flight/SLAM setup. Do not delete the old folders yet.

## Prototype and legacy setup notes

Optional teammate YOLO segmentation and MiDaS relative-depth view: see [vision setup](docs/vision.md).

Original Ryze Tello, ROS 2 Jazzy, Stella VSLAM and a local browser dashboard.
Working flight prototype; experimental sparse mapping. No autonomous navigation or collision avoidance is implemented.

## Start on Shadib's existing Mac

Land and stop the old four-terminal session first. From this repository:

```sh
python3 start.py --reuse-existing
```

This connects to Tello, starts ROS video/telemetry, SLAM and the dashboard, but **motor arming is disabled**.
Open http://127.0.0.1:8082. Live hardware requires TELLO Wi-Fi.

For a deliberate flight session:

```sh
cd ~/Documents/robotics-group-drone-project
python3 start.py --no-slam --enable-flight
```

Enable dashboard controls, press T to request motor arming, then hold W to lift.
W/S: rise/descend; A/D: yaw; arrows: forward/back/slide; Space: zero movement request; L: landing request.
Slow and Normal use different stick limits with native fast mode off; Fast requests native fast mode while airborne.
40% battery: red warning. At 20%: steerable descent; W pauses downward input. Firmware can impose its own battery landing.
There is no automatic ceiling or altitude limit. Landing after a network failure cannot be guaranteed.
Land before Ctrl+C. The launcher stops the source first and allows its landing/shutdown logic time to run.
Per-process output is saved in `logs/`. Another process exiting also triggers shutdown.

## Develop without a drone

On the existing Mac:

```sh
python3 start.py --reuse-existing --replay /absolute/path/to/video.avi
```

Replay never imports a drone control library and cannot enable flight. It publishes recorded images and synthetic telemetry; keyboard commands update mock state only. Commands do not change the replay camera view. Restart SLAM when looping the recording breaks tracking.
Use `--no-slam` for camera/dashboard work without a compiled SLAM dependency.

## Legacy standalone SLAM setup (experimental)

The legacy ros/ and slam/ environment locks target **Intel macOS (`osx-64`) only**. Apple Silicon, Linux and Windows require a separately verified environment; do not assume these locks work there.
Install Git, Pixi and Python 3, then run:

```sh
python3 setup.py
python3 start.py --replay /absolute/path/to/video.avi
```



## Layout and team ownership

- `ros/tello_manual_launch.py`: sole hardware connection and flight command owner.
- `ros/flight_dashboard.py`, `ros/dashboard.html`: browser UI and keyboard input.
- `ros/slam_frame_bridge.py`: ROS frames/telemetry to the SLAM runtime.
- `ros/replay.py`: recorded input and mock flight state.
- `slam/src/tello_live_slam/`: C++ SLAM worker, map and annotated-image export.
- `slam/assets/tello_320_dense.yaml`: provisional calibration for 320x240 BGR images.
- `scripts/`: calibration/diagnostic tools preserved from the prototype. These still need path/config cleanup before use.
- `runtime/`, `logs/`, `build/`, `local/`, `vendor/`: generated, excluded from Git.

See `CONTRIBUTING.md` for branches and updates, and `docs/architecture.md` and `docs/roadmap.md` before adding automation.
Run `python3 -m unittest discover -s tests` for launcher safeguards.


