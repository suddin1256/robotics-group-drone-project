# Experimental combined mapping

The floor-plan worker now uses telemetry, YOLO, relative depth and SLAM in one
geometry pipeline. This is a quality-gated prototype, not a validated VIO/EKF,
metric floor plan, occupancy estimator or collision-avoidance controller.

```sh
cd ~/Documents/robotics-group-drone-project
python3 start.py --reuse-existing \
  --bag ~/Documents/tello-recordings/flight_20261031_130708 \
  --slam-all-frames --vision
```

The drone remains off for replay. Open http://127.0.0.1:8082. The floor-plan input
panel reports available inputs, accepted coordinate alignment, contributing
depth/IMU frames, rejection reasons and how far geometry trails telemetry.
For live operation, the same worker runs with `--vision` and SLAM enabled;
flight requires the separate existing `--enable-flight` flag.

## Coordinates and drone pose

The map uses raw onboard MVO position coordinates, with native units and axes
explicitly unverified. At least eight exact-frame airborne telemetry/SLAM
keyframe pairs are required to estimate a robust 3D similarity transform.
Degenerate motion, too few inliers or inconsistent estimates reject alignment.
The displayed native drone path can appear before object alignment is ready.
Its position is not treated as ground truth and can drift or jump.

When accepted, the transform relates SLAM geometry to the native frame; it does
not certify real-world metres. An orientation relationship is fitted between
native IMU quaternions and matched visual camera rotations. Insufficient angular
motion or inconsistent rotations cause a visual-rotation fallback. Camera/body
translation is approximated as co-located; camera-to-body extrinsics, clock
offset, native unit conversions and flight-mode camera calibration still need
physical validation. Acceleration and gyro are recorded diagnostics, not directly
integrated as extra position corrections.

Per-frame telemetry must precede its original image and pass the saved freshness
checks. Cached MVO/IMU record age is checked separately when its timestamps are
available. Geometry whose visual position disagrees strongly with telemetry is
rejected. World alignment is recomputed from current optimized keyframes so
SLAM corrections do not silently freeze an old transform.

## Objects and relative depth

YOLO masks are matched to original-frame SLAM feature coordinates and landmark
IDs. PnP against current landmark positions refines stored camera poses when
sufficient matches exist. Object support is transformed into the native map,
anchored at the corresponding telemetry position. Shared landmarks or overlapping
same-class footprints combine observations. Every displayed object remains
tentative; people are excluded from static reconstruction.

The depth worker saves floating-point relative inverse-depth predictions rather
than trying to reconstruct geometry from its colored preview. Because depth is
slow, it also runs a small YOLO pass on the exact image it processed. This adds
some depth-worker cost but never blocks the independent freshest-frame YOLO view.
No newer segmentation mask is attached to an older depth frame.

For each depth frame, at least 16 matching landmark depth samples are used to
fit a robust positive affine relationship between relative inverse depth and
inverse SLAM camera depth. Poor fits, nonpositive depths and extrapolated signal
ranges are rejected. Accepted pixels are undistorted with the existing camera
calibration and projected through the telemetry-led camera pose. This adds
visible surface samples and extends object support where sparse features alone
are insufficient. It is a fitted geometric hypothesis, not a depth measurement.

Grey/purple surface cells show evidence, including possible floors; they do not
mean solid obstacles. Blank cells remain unknown. No free-space ray carving,
floor/wall classification, semantic mesh or measured object dimensions are
implemented. SLAM loss can prevent new depth alignment/object placement even
while native telemetry keeps updating the drone path. Missing or rejected inputs
are counted rather than replaced with invented geometry.

## Storage and validation

Original per-image metadata is archived under `runtime/live/frame-telemetry`,
and exact-frame depth arrays/masks under `depth-frames` and `depth-detections`.
These caches are bounded and cleared on each new launch; bags remain unchanged.
The mapper currently considers up to 512 recent semantic frames and 64 cached
depth frames, and reconstructs the current surviving SLAM map. It is not yet a
persistent building-scale map across SLAM resets or very long recordings.

Synthetic tests cover coordinate/scale recovery with outliers, degenerate
alignment rejection, relative inverse-depth fitting, timing rejection and a
combined case in which telemetry translation moves an object supported by YOLO,
SLAM and depth, with IMU rotation used. A replay of the October 31 multi-room
recording demonstrated contributions from all four sources. This verifies the
integration, not real-world localization or distance accuracy.
