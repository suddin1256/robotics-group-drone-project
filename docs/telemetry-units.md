# Telemetry units for the prototype

Audit date: November 21, 2026. These conventions apply to our **TelloPy native protocol**, not the separate text SDK. Units do not establish positioning accuracy.

## Conventions to use

| Field | Prototype interpretation | Conversion | Evidence / limit |
| --- | --- | --- | --- |
| `mvo.pos_x/y/z` | metres, native local frame | Keep scale; subtract a settled-hover origin when comparing flights | Measured forward/right/left tests give 0.938 / 0.898 / 0.721 for intended 0.914 m movements. Not an accuracy guarantee. |
| `mvo.vel_x/y/z` as saved in JSON | effective decimetres per second | Multiply decoded values by **0.1** for m/s | Across moving recordings, position-change speed / decoded velocity magnitude has median about 0.09–0.10. The decoder already divides packet integers by 100; do not apply the packet conversion again. Absolute velocity frame still needs checking. |
| Native flight `height` | decimetres | Multiply by **0.1** for metres | Changes are generally consistent with about -0.1 m of native position Z per height increment. Coarse and not interchangeable with a calibrated floor range. |
| `imu.acc_x/y/z` | g-scale acceleration including gravity | Multiply by **9.80665** for m/s² | Median magnitude is about 1.03–1.04 across recordings, not 9.81. Bias remains; do not integrate directly into position. |
| `imu.gyro_x/y/z` | radians per second, provisional | Scale 1 | Quaternion angular-rate / gyro magnitude is near 1 on aggregate, with wide scatter from timing and sampling. This supports rad/s rather than deg/s; axes still need alignment. |
| `imu.q0/q1/q2/q3` | dimensionless quaternion, scalar-first in decoder | Reorder to ROS x/y/z/w only when needed; normalize | Norm is approximately 1. Relative rotations are usable; world/body direction and camera extrinsics are not verified. |
| `battery_percentage`, `bat` | percent | Divide by 100 for ROS BatteryState percentage | Protocol byte and driver mapping. Not a voltage measurement. |
| `received_stamp_ns`, `image_stamp_ns` | host nanoseconds | Divide by 1e9 for seconds | Host receipt/decode times; not hardware exposure synchronization. |
| `light_strength` | unavailable in installed decoder | Do not use | Initialized to zero without a subsequent decoder assignment. Zero is not a darkness reading. |

## Axes and origin

In the controlled tests, forward mainly increased native X, right mainly increased native Y, and left mainly decreased native Y. Native Z generally **decreases on ascent**. These are observations for these headings, not proof that coordinates remain body-fixed after yaw. Do not label native axes as global north/east or publish a trusted ROS TF from these observations.

Position does not necessarily start at zero or reset between sessions. Relative displacement is more useful than absolute native coordinates. Our measured tests compare settled airborne hover positions; the actual takeoff and touchdown spots are different references after manual repositioning.

## Scope and practical decision

All 14 locally available recordings were inspected. Eleven contain raw motion/IMU evidence: **5,949 distinct MVO samples and 11,882 distinct IMU samples**. Two brief sessions have no motion samples; the older handheld recording has no native raw logs. Those recordings cannot independently verify units.

Use position as a **provisional metric motion constraint**, not ground truth. Convert speed and acceleration before any SI-based filter. Reject stale samples, reset relative origins deliberately, and check visual tracking separately. Do not use fixed 70/30 weights yet. The existing `_unverified` ROS topics retain their current raw/adapted values; this audit does not silently change their contracts, enable fusion, or alter flight control.

The three measured outward displacements differ by roughly +3%, -2%, and -21% from the intended 3-foot reference under the metre interpretation. These percentages combine pilot positioning, sensor error, and reference uncertainty; they are **not measured sensor accuracy**. No new flights are required to start an experimental reconstruction using these explicit conventions.

## Reproduce

Run in the ROS environment (Shadib's existing Mac):

```bash
cd ~/Documents/robotics-group-drone-project
pixi run --manifest-path ~/Documents/tello-ros2/pixi.toml python \
  scripts/audit_recorded_telemetry.py \
  --recordings ~/Documents/tello-recordings \
  --output .local/telemetry_tests/unit_audit
```

The local output JSON contains per-recording distributions and sample counts. Recordings and private output stay outside Git.

## Applied conversion layer

`ros/telemetry_units.py` provides non-mutating conversion helpers. The image bridge writes `metric-telemetry.json` for the dashboard with per-sensor freshness flags. The mapper uses the same helper for its motion input. Position scale stays 1; velocity and acceleration now have explicit metric fields available to mapping. They are not automatically integrated into a new motion filter. Quaternion alignment and visual/telemetry rejection checks remain in place.

The dashboard labels this as **units checked for prototype use**, shows converted values, and distinguishes live, recorded, stale, and missing samples. The floor-plan output reports experimental metres only when coordinate alignment passes; visual fallback remains in arbitrary SLAM units. Raw recordings and existing ROS topic values are preserved for comparison.
