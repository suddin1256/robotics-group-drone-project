# Community telemetry backend

The default live backend now adapts PedroS235/tello_ros2_driver at commit
`9a2bef366ebe2a2e7b57ef170e4f7cafb483e8e8` (MIT; sources and license under
`third_party/tello_ros2_driver`). This is an adapted backend, not an unmodified
stock launch: it reuses upstream ROS publishers and serializers with our existing
video path, manual motor arming, input timeout and landing state machine. One
TelloPy connection owns the drone. Upstream auto-Wi-Fi switching, startup camera
changes, automatic takeoff and additional flight-command subscribers are not run.
`--driver legacy` selects the previous backend. No raw downward camera access is
provided. Firmware determines which log records are actually available.

## First test (ground only)

Connect the Mac to TELLO Wi-Fi and keep the drone grounded:

```sh
cd ~/Documents/robotics-group-drone-project
python3 start.py --reuse-existing --driver community --no-slam --record
```

Open http://127.0.0.1:8082 and expand **All decoded telemetry and available tools**
and **Latest image / motion association**. The launcher builds the upstream custom
messages locally before connecting. Team laptops using the portable environment
run `python3 bootstrap.py --hardware` first. No elevated install script is run.

After verifying live telemetry, add `--enable-flight` explicitly for manual
flight. Add `--vision --vision-mode objects-only` for objects; omit `--no-slam`
to include mapping. Do not run another drone driver at the same time.

## Data exposed

| Topic | Data |
|---|---|
| `/tello/image_raw` | Calibrated 320x240 RGB stream |
| `/tello/preview/compressed` | Sharper 640x480 JPEG preview |
| `/tello/flight_data` | Upstream FlightStats; native units require validation |
| `/tello/telemetry` | Existing scalar flight state JSON for dashboard |
| `/tello/raw_log` | Decoded native IMU, MVO and other log fields/records available in installed TelloPy, including per-record payloads when supplied |
| `/tello/raw_log_packets` | Original log payload bytes encoded as hex, retained even when some records cannot be decoded |
| `/tello/imu_unverified` | Upstream IMU conversion; unvalidated units/axes, covariance flags mark fields unavailable for fusion |
| `/tello/odometry_unverified` | Upstream motion estimate with velocity-axis copy/paste corrected; deliberately large placeholder covariance, not measured uncertainty |
| `/tello/battery` | Fractional charge (0–1); voltage unknown, not guessed |
| `/tello/image_metadata` | Image timestamp/sequence with preceding flight/log samples and their ages |
| `/tello/capabilities` | Driver provenance, available tools, latest raw fields and capture directory |
| `/tello/control_status` | Flight state, launch surface and optional table height |

The stock odometry source is explicitly described upstream as inaccurate. We do
not broadcast it as TF, use it as ground truth, or feed it to Stella. Copied
conventions are retained on unverified topics rather than silently claiming REP
103/145 compliance. A quaternion/status flag alone does not make valid inertial
odometry. Missing measurements remain unavailable; cached fields inside a log
packet may be older than its receipt time. Consult its individual record timing.

## Images and telemetry timing

Image headers use host decode-completion time, not a hardware exposure timestamp.
Each published image receives the latest *preceding* host-received flight and
log sample within 250 ms, otherwise a null sample with its age. This is an explicit
association, **not synchronized camera/IMU acquisition** and not interpolated
ground-truth motion. Native ticks and record receipt times are retained for
later clock-offset and latency analysis.

The backend automatically writes decoded events and per-image metadata as JSONL
under `runtime/live/captures/<session>/`. These do not contain the image pixels.
`--record` additionally starts an MCAP ROS bag containing images, telemetry,
metadata and control/status topics under `~/Documents/tello-recordings/flight_*`.
Use `--record-dir NEW_PATH` to choose a new directory. Land and confirm motor
stop before closing. Bag replay never republishes flight-control/tool requests.
Keep recordings private unless intentionally sharing them.

## Launch surface and tools

The dashboard defaults to **Ground**. Select **Table** and optionally enter the
measured table height in cm before arming. The driver freezes this annotation
while airborne; changing the field disables keyboard control. This records the
reference surface only: it does not change motor arming, infer ground clearance,
set a ceiling limit, or automatically scale SLAM.

Available controls remain T arm/W lift, L land, Space neutral/manual takeover,
Mode-2 movement, slow/normal/native fast and descent assist. Exposure 0/1/2 is
available in the telemetry/tools panel. Flips, palm landing, throw-and-go,
automatic takeoff, native altitude/attitude settings and video-mode changes are
listed as upstream capabilities but are not wired into flight controls here.
The upstream altitude callback confuses attitude and altitude setters; it is
not used. Future additions need separate validation and calibration handling.

## Offline checks

`scripts/check_community_driver.py`, run with the ROS Python environment, mocks
the radio and checks real ROS serialization, nested logs, image association and
launch-surface handling. `--check` on `ros/community_driver.py` checks imports
without initializing a node or contacting hardware. Actual sensor rates, timing,
units, axis conventions and manual-flight behavior still require hardware tests.
