# Tello ROS 2 + visual SLAM flight prototype

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
python3 start.py --reuse-existing --enable-flight
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

## New teammate setup

The committed environment locks target **Intel macOS (`osx-64`) only**. Apple Silicon, Linux and Windows require a separately verified environment; do not assume these locks work there.
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


