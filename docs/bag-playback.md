# Replay a real recording through the full system

This mode reads an existing ROS 2 MCAP bag without modifying it. It republishes recorded images, telemetry and driver status in their recorded order/timing. It deliberately excludes `/tello/manual_control` and never starts the Tello driver. Keep the drone powered off while developing from recordings.

For independent YOLO/depth views and ordered processing of every recorded SLAM frame, add `--vision --slam-all-frames`. See [performance modes](performance.md). The updated small SLAM adapter is rebuilt automatically; live drone code and the original compiled adapter remain available.

On Shadib's original setup:

```sh
cd ~/Documents/robotics-group-drone-project
python3 start.py --reuse-existing --bag ~/Documents/tello-recordings/handheld_20261027_185127 --vision
```

Open http://127.0.0.1:8082. This starts the bag reader, ROS image bridge, dashboard, V4 and the existing compiled Stella worker. The blue banner identifies playback. Model loading can take time; playback waits for consumers and, when V4 is requested, for its models (up to three minutes). V4 failure is nonfatal and reported in its status/log.

On a teammate's portable installation use `--bag /path/to/bag` without `--reuse-existing`. Their SLAM build must already be available, or add `--no-slam`. Add `--vision` only after its setup succeeds. No new packages are required on the existing Intel setup; the shared ROS lock already contains rosbag2_py and MCAP support.

## What is replayed

- `/tello/image_raw`: real recorded camera images, with fresh delivery stamps for existing stale-frame checks.
- `/tello/telemetry`: actual recorded readings; original reception timestamps preserved in `recorded_received_stamp_ns`, delivery time substituted for freshness display.
- `/tello/control_status`: historical state clearly marked PLAYBACK and flight disabled.
- `/tello/replay_status`: bag name, recording position, image count and original/delivery timestamp of the latest image.

The original bag preserves every original timestamp and all recorded control requests. Those control requests are never republished. This is operational replay, not simulated drone behavior or a fresh physical measurement. Existing SLAM/V4 consumers use delivery time rather than ROS simulated time.

Playback uses ROS domain **43**, separately from the usual live domain 42. Dashboard control publishing is disabled and control POST requests are rejected with HTTP 403. Do not run another hardware driver in the playback domain.

The recording plays once. At the end, the dashboard stays open with a finished banner and the last available map/view; image freshness naturally expires. Press Ctrl+C to stop all processes and save the SLAM session. Restart the command to repeat with a clean map; there is no loop that silently merges repeated passes.

## Diagnostic options

`--rate 0.5` plays at half speed. It changes delivery timing, so don't compare timing-sensitive results as if this were original-speed replay.

`--no-slam` isolates V4. Omit `--vision` to isolate SLAM. Running both may increase inference time due to CPU contention.

`--duration 30` stops an offline test automatically after 30 wall-clock seconds, including startup/model loading. `--port 8083 --runtime-dir "$PWD/.tmp/bag-test"` creates a separate test dashboard/runtime workspace.

For ROS inspection in another terminal, use `export ROS_DOMAIN_ID=43` before `pixi run ros2 node list --no-daemon --spin-time 5`. Use the appropriate environment manifest for that laptop.

Recordings remain local outside the Git repo. A 45-second integrated test on the recorded handheld bag produced camera/telemetry output, a V4 segmentation/depth image, and a Stella map with 18 keyframes and 485 landmarks saved at shutdown. It confirmed that control POST requests were rejected; this is pipeline validation, not map-accuracy validation. Full-recording and teammate hardware testing remain separate checks.
