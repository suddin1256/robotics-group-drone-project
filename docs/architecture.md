# Interfaces

Video: `sensor_msgs/msg/Image`, `/tello/image_raw`, 320x240 RGB8, sensor-data QoS, target 15 Hz. The bridge converts to BGR for Stella. Frame timestamps currently describe host processing, not exposure times.
Telemetry: `std_msgs/msg/String`, `/tello/telemetry`, JSON with `received_stamp_ns` and `state`. Native TelloPy scalar fields remain raw; `bat` aliases battery percentage. Do not claim native height/velocity units without validating them.
Input: `std_msgs/msg/String`, `/tello/manual_control`, prototype JSON containing RC channels `[slide, forward, up, yaw]`, mode, input freshness, actions and wall timestamp.
Status: `std_msgs/msg/String`, `/tello/control_status`, JSON driver phase, commanded RC, freshness and battery.
Native fast flag means requested, not independently acknowledged.

The launcher assigns ROS_DOMAIN_ID=42. Use that same domain for additional development nodes. Ports: dashboard 8082; Tello native protocol owns its network ports. Only one hardware driver may run.

The bridge atomically replaces frame, JPEG and telemetry files in TELLO_RUNTIME_DIR. The C++ worker reads the latest frame and exports live/map.json and live/preview.jpg. The launcher sets the working directory so C++ relative paths refer to runtime assets and live files.

The map is a sparse point cloud with arbitrary monocular scale. Tracking can be lost. It is not a verified obstacle map and does not control flight. The SDK does not provide a raw downward optical-flow camera stream. Replay synthetic data must not be confused with measured telemetry.

Automation must eventually submit commands to an arbiter, with manual takeover priority, heartbeat expiration, stale-state checks and a separately armed automation state. Do not let a new node connect directly to Tello or bypass the hardware driver. The current Space action zeros manual motion; no automation arbiter exists yet.
