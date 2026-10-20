# Teammate V4 camera experiment

The original teammate file is preserved at `vision/V4_original.py`. It used a laptop webcam and a Qt window. The adaptation reads the existing bridge's latest BGR frame, runs the same YOLO11s segmentation/ByteTrack and DPT-Hybrid MiDaS logic, and exports a side-by-side annotated image and depth heatmap to the browser dashboard.

The optional worker has no drone connection, ROS control publisher or flight actions. It drops intermediate frames instead of building an inference queue. The original 320x240 stream is resized to 640x480 for V4; this does not add camera detail. Start without SLAM to reduce CPU/memory use on the 8GB Intel Mac.

## One-time setup on the Intel Mac (while connected to internet)

```sh
cd ~/Documents/robotics-group-drone-project
python3.12 -m venv vision/.venv
vision/.venv/bin/python -m pip install -r vision/requirements-intel-mac.txt
vision/.venv/bin/python vision/worker.py --prepare
```

Do not install these packages into the working ROS Pixi environment. The separate environment pins an older Intel macOS-compatible PyTorch baseline. This requirements file is not a complete transitive lock; installation and real model execution still require verification on the target machine. Models are downloaded into ignored `vision/models/`; keep internet connected until warm-up completes.

## Test without hardware

```sh
python3 start.py --reuse-existing --replay ~/Documents/tello-slam/assets/tello_test.avi --vision --no-slam
```

Open http://127.0.0.1:8082. The V4 section shows processing state, source-frame age, segmentation and relative-depth colors. Remove `--no-slam` to run SLAM too after measuring performance. If the optional worker fails, the camera/dashboard continue; inspect `logs/*_vision.log`.

## Tello camera ground test

Stop replay, connect to TELLO Wi-Fi, power on the drone and run:

```sh
python3 start.py --reuse-existing --vision --no-slam
```

Motor arming stays disabled. Do not add flight until inference load and control responsiveness are evaluated. This worker is for viewing only and is not collision avoidance.

## Relative depth and reference limitations

MiDaS produces relative inverse-depth scores; scores and ratios are not centimeters or calibrated distances. The original fixed ROI `(120,260,190,440)` assumes a reference surface remains 20cm away. Ordinary Tello views/replay do not satisfy that assumption, so experimental proximity labels default to UNKNOWN. Segmentation and the heatmap still display. Reference validity currently cannot be inferred automatically.

For a deliberate stationary reference experiment, run the worker directly with `--reference-confirmed` instead of launcher `--vision`, after verifying the surface fills that ROI and stays 20cm from the camera. This only enables the original experimental ratio labels; it does not calibrate metric depth. Heatmap colors are normalized per image, so equal colors across frames do not imply equal distance. A closer unrelated object inside the fixed ROI can invalidate comparisons.

The V4 processing was adapted, not independently redesigned. The original code remains available for comparison. No model weights or package environments belong in Git. Review Ultralytics/model licensing before redistribution or broader deployment.
