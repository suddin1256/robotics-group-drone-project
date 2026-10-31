# Update log

## October 31, 2026 — current work

- Changed the default Tello connection from our original DIY ROS driver to an adapted community driver based on PedroS235/tello_ros2_driver. The old driver is still available with `--driver legacy`.
- Added more telemetry and flight-log capture, plus image timestamps linked to nearby telemetry samples. Units, axes, and timing still need checking.
- Added a ground/table launch option to record where the flight started.
- Added recording and playback of camera images and real telemetry together, so everyone can develop without flying each time.
- Added an experimental floor-plan mapper using YOLO detections, SLAM landmarks, telemetry, and relative depth when matching data is available.
- Added a visual-map fallback when telemetry cannot be aligned with SLAM. Unaligned telemetry is kept separate rather than mixed into the geometry.
- Tested mapping on recorded flights. It can place some objects, but accuracy, tracking loss, and consistent placement still need work.

## Earlier prototype work

- Connected the Tello camera and telemetry to ROS 2.
- Added manual flight controls, speed modes, and a browser dashboard.
- Built Stella VSLAM and connected it to the camera stream for pose estimates and sparse landmarks.
- Added Rian's V4 vision system to the dashboard.
- Switched the fast object-detection worker to a smaller YOLO nano segmentation model.
- Worked on slowdown by separating YOLO and relative-depth processing and prioritizing fresh images for detection. Relative depth is still slow.
- Added sharper camera previews while keeping smaller images for SLAM processing.
- Added a single startup command and laptop-aware setup/update scripts for the group.

These notes describe the prototype changes, not a claim that every feature is accurate or tested on every laptop.
