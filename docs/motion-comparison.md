# Compare recorded video, SLAM and onboard telemetry

```sh
cd ~/Documents/robotics-group-drone-project
python3 start.py --reuse-existing \
  --bag ~/Documents/tello-recordings/flight_20261031_123025 \
  --slam-all-frames
```

Open http://127.0.0.1:8082 and scroll to **Recorded flight: video, SLAM and
telemetry comparison**. Drone power and an internet connection are unnecessary.
This command starts no hardware driver, disables dashboard controls, and does
not replay recorded control requests. Vision/depth models are omitted to reduce
load during motion diagnosis. Add `--vision --vision-mode objects-only` if needed.

The panel provides independently fitted native and SLAM trajectories, position
traces on the same recording timeline, selectable acceleration/rotation-rate/raw
quaternion traces, and flight/log sample ages for each image. The default
trajectory filter selects the recorded driver's `airborne` phase. Uncheck it to
include handling before/after flight. Plane selectors change projections only;
they do not identify equivalent physical axes automatically.

The white marker is the latest replayed camera image's original timestamp.
Orange is the latest processed/exported SLAM frame; when tracking is Lost, that
does not constitute a valid pose. Red bars indicate SLAM states other than
Tracking. SLAM keyframe positions use original timestamps and the latest
optimized coordinates. Surviving keyframes are not a complete continuous pose
history. Camera and raw log clocks remain host-derived, not hardware-synchronized.
Map export is throttled to approximately once per wall-clock second; its marker
may trail the processing counter, especially during accelerated playback.
The comparison origin is the first observed comparison timestamp, so seconds
need not equal the bag's full duration or its first command-only timestamp.

Replay uses separate delivery stamps for live-style freshness checks, while
these charts retain the original sample times and recorded association ages.
`--slam-all-frames` is required for SLAM source-clock alignment. It queues every
image for Stella; charts explicitly show when SLAM is behind the video. Distinct
IMU/MVO updates are selected by native update counters so cached values in other
log packets are not counted repeatedly. Missing/nonfinite values stay null.
Histories are bounded to 6000 entries per series; the original bag is unchanged.

Trajectories are not overlaid or rescaled to imply agreement. Native position,
speed and inertial units/axes still require validation. SLAM scale is arbitrary.
No measurements are fused and the display does not command flight or assert
obstacle clearance. A useful next analysis is to inspect the tracking-loss bars,
video motion, native estimate jumps and stale/missing telemetry together before
designing scale correction or fusion.

Offline verification on the October 31 recording processed all 1860 images and
exposed 1244 distinct IMU updates, 620 distinct onboard motion updates and 1860
per-image metadata entries. Stella ended Lost in that test. Replay speed used
for testing is not a live-system performance claim.
