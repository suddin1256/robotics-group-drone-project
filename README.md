# Robotics group drone project

Our robotics class project uses a Ryze Tello, ROS 2, Stella VSLAM, YOLO, and the MiDas vision systems. The dashboard shows the camera, telemetry, object detection, relative depth, and an experimental floor-plan map. We can fly manually or develop using recorded flights without connecting the drone.

The connections and manual flight work. Mapping is still a work in progress: positions and distances are not yet reliable, and automatic obstacle avoidance is not implemented.

## First-time setup

Install Git and Python 3 first. On Windows, use Ubuntu inside WSL2. See [laptop setup notes](docs/team-setup.md) for platform details.

Run these while connected to the internet, before switching to the Tello Wi-Fi:

```bash
git clone https://github.com/suddin1256/robotics-group-drone-project.git
cd robotics-group-drone-project
python3 bootstrap.py --hardware --vision --slam
```

Setup detects the supported platform and downloads the dependencies and models. The SLAM build can take a while; fresh builds on other laptops still need testing. If it fails, use `--no-slam` for camera and vision testing until the build is fixed.

For later updates, stop the program and run:

```bash
python3 update.py
```

This downloads code updates and reruns setup when dependencies change. It stops if you have uncommitted changes so it does not overwrite your work.

## Commands

Run commands from the project folder. Open **[the dashboard](http://127.0.0.1:8082)** manually after starting.

### Play a recorded flight with all systems

```bash
python3 start.py --bag /path/to/recording_folder --slam-all-frames --vision
```

Use the whole ROS bag folder, not just its `.mcap` file. Playback uses real recorded video and telemetry and cannot fly the drone. Recordings are stored separately from GitHub; each teammate needs a local copy.

On Shadib's Mac, using the existing environments and test recording:

```bash
cd ~/Documents/robotics-group-drone-project
python3 start.py --reuse-existing \
  --bag ~/Documents/tello-recordings/flight_20261031_130708 \
  --slam-all-frames --vision
```

Add `--rate 0.5` for half-speed playback. `--slam-all-frames` lets SLAM process every recorded image in order; the vision models process selected fresh frames independently.

### Connect to the drone without enabling flight

Turn on the Tello, connect the laptop to its TELLO Wi-Fi, and close other apps connected to the drone.

```bash
python3 start.py --driver community --vision
```

This starts the camera, telemetry, SLAM, vision models, map, and dashboard. Motor arming is disabled.

### Fly with all systems and record the flight

```bash
python3 start.py --driver community --vision --enable-flight --record
```

On Shadib's existing Mac setup:

```bash
cd ~/Documents/robotics-group-drone-project
python3 start.py --reuse-existing --driver community --vision --enable-flight --record
```

Recordings save to `~/Documents/tello-recordings/flight_<date_time>`. Leave off `--record` if you do not want to save a session.

Enable controls in the dashboard, then use:

| Key | Control |
| --- | --- |
| T | Request motor arming |
| W / S | Up / down; hold W to lift after arming |
| A / D | Yaw left / right |
| Up / Down arrows | Forward / backward |
| Left / Right arrows | Slide left / right |
| Space | Request neutral movement / manual takeover |
| L | Request landing |

Slow, Normal, and Fast modes are selected in the dashboard. The launch-surface selector records ground/table information; it does not enforce a height limit. At 40% battery the dashboard turns red; at 20% descent assistance activates. The drone's firmware may also impose landing.

Land before pressing Ctrl+C. There is no automatic ceiling limit, and commands or landing cannot be guaranteed after a connection loss.

### Quick test without a drone or recording

```bash
python3 start.py --demo --no-slam --vision
```

This uses synthetic images and telemetry to check the dashboard and connections, not mapping accuracy.

## What changed

- Rian added two vision models: YOLO for object detection and segmentation, and MiDaS for relative depth.
- Worked on processing speed for Rian’s vision system by using a smaller YOLO model and running detection and depth separately.
- Changed the original DIY driver to an adapted community Tello driver to access more telemetry and tools.
- Added video and telemetry recording so the group can test using the same flights.
- Connected Stella VSLAM to estimate the camera path and build a landmark map.
- Added a simple experimental floor-plan map using available detections, landmarks, telemetry, and relative depth.
- Added setup and update scripts for the group’s laptops.

See [UPDATE_LOG.md](UPDATE_LOG.md) for more details.

## Issues / next to fix

- The vision system is not fully optimized and can still be very laggy.
- MiDaS cannot keep up with the full video frame rate on our current setup.
- Relative depth is not a measured distance. We still need to test and improve distance estimates.
- SLAM can lose tracking, and the floor-plan objects are not consistently accurate.
- Telemetry units, coordinate axes, and timing need checking before we trust them for mapping.
- Telemetry and SLAM do not always agree. The map uses a visual fallback when they cannot be aligned.
- We need more short, well-lit flight recordings with measured reference distances.
- Setup and performance still need checking on each group member’s laptop.

## Where things are

- `ros/`: drone drivers, ROS nodes, recording playback, and dashboard.
- `vision/`: YOLO, relative depth, and floor-plan mapping.
- `slam/`: Stella VSLAM setup and our adapter.
- `docs/`: extra setup and testing notes.
- `logs/`: output from each running program, useful when something fails.

Keep recordings, downloaded models, and installed environments out of Git. Shadib's `--reuse-existing` option still depends on the old `tello-ros2` and `tello-slam` folders, so do not delete those yet.
