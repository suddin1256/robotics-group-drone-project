# Room surfaces and doorway prototypes

Start TelloTubby with `python3 app.py`. In the library, **Prepare mapping models** installs the mapping dependencies, caches the models while online, and builds the OctoMap exporter. On this Intel Mac this preparation has already been completed. Restart an already-running app after code changes.

## Build a room without watching recordings

Open a room's **3D room view** and click **Build room from all recordings**. Keep the app running; you can leave that tab or browse other rooms. No playback window, dashboard, ROS publisher, or drone connection is started.

The background worker processes the room's recording list sequentially:

1. Read each original bag directly, retaining its original image timestamps and image-associated telemetry.
2. Send **every camera image** through ordered SLAM to estimate poses and landmarks. There is no real-time playback clock or latest-frame dropping.
3. Run indoor depth, YOLO masks, and room-structure segmentation on saved SLAM keyframes. Dense models use these selected views rather than repeating inference on every adjacent video frame.
4. Register overlapping captures into the room's common coordinate frame, then reconstruct surfaces and occupancy. A later flight that bridges two views can connect a previously unmatched capture. Unmatched captures remain separate instead of being placed arbitrarily.

The panel shows the recording, processing stage, SLAM image count and model keyframe count. **Stop room build** cancels processing and retains completed work and the original recordings. Live flight/playback and model changes are blocked while a background build runs.

Click the build button again after adding flights. Completed work is cached using recording file metadata and the processing/configuration version. New or changed recordings are processed; previous results are reused. Check **Reprocess recordings even if they already have saved results** to force another pass. Old map captures remain available, but superseded processing of the same recording is excluded from fusion to avoid duplicate votes. If the app is closed, the next build reuses completed recordings and retries unfinished ones.

Background jobs retain all derived keyframe packets and observations. The interactive 160-packet reconstruction sampling limit does not apply to background-build captures. The temporary ordered image spool is removed after successful keyframe inference; original bags remain unchanged.

Open a room and choose **View & process** for a recording. End playback after processing, then open **3D room view**. Choose textured surfaces, wall/floor/door colours, or the original SLAM points. **Update room map** rebuilds from saved packets. Earlier sessions without RGB/depth packets need to be replayed once with the new models.

## What runs

- YOLO nano remains the independent object detector and supplies person masks to exclude people from static surfaces.
- Depth Anything V2 **Metric Indoor Small** predicts distances. It is different from the older relative-depth ONNX checkpoint. It uses PyTorch CPU on Intel and CPU/MPS on supported Apple Silicon installations.
- SegFormer B0 (ADE20K) supplies wall, floor, ceiling, window and door masks. These classes are not provided by our existing COCO YOLO weights.
- Door-leaf masks and paired vertical image edges produce tentative door/frame proposals. Relative depth across the jamb/interior produces **possibly open**, **possibly closed**, or **unknown**. This is a heuristic, not a trained door-state model. Truncated image-border proposals remain unknown. Every proposal is `verified: false` and `traversable: false`.
- Open3D 0.19 integrates accepted depth frames into a coloured TSDF surface mesh. This version retains both Intel and Apple Silicon wheels. No CUDA is required. The Apple Silicon path still needs a test on the group's laptop.
- OctoMap 1.10.1 exports a tentative `.ot` occupancy tree using per-frame point clouds and their camera origins. Source is pinned by version and checksum, and is built locally without a system-wide install.

## Matching and validation

Each depth packet retains its exact image timestamp, RGB image, depth, semantic labels and confidence. SLAM observations include their map origin. A late depth frame is never paired with the newest camera pose.

The reconstruction refits camera pose against current SLAM landmark coordinates, allowing reconstruction to use corrected geometry after optimization. A depth-to-SLAM fit must pass held-out landmark checks and outperform a constant-range prediction. Strong discontinuities and people are excluded. Accepted telemetry/visual alignment adds a hardware-pose disagreement rejection check; unavailable or rejected telemetry is not forced into the reconstruction.

Depth is converted into the anchor map's coordinate scale. **Model-predicted metres are not accepted as measured metres.** The active camera calibration is read from the same configuration as SLAM; the previous checkerboard candidates have not been automatically promoted to validated calibration.

Cross-flight merging uses the existing descriptor/3D registration checks. Unmatched flights stay separate. Reconstruction starts from saved packets on every rebuild; viewing a map repeatedly does not add votes. There is a 160-depth-frame-per-capture sampling limit to bound reconstruction cost. During app sessions the original packets are retained so this limit can be changed later. Disk use grows with recording/processing history.

## Outputs

Each room can contain:

- `room-mesh.ply`: surface mesh for external viewers.
- `room-surfaces.ply`: coloured surface points.
- `room-mesh.json`: mesh and structural colours for the app.
- `room.ot`: experimental OctoMap, when the exporter is prepared.
- `occupancy.json`: tentative occupied/free cells; unknown space stays blocked.
- `reconstruction-status.json`: accepted/rejected frames and validation limits.

The separate `mapping/path_preview.py` implements an offline 3D A* preview with clearance inflation. Unknown space is blocked. Its results always have `autonomous_allowed: false`; it does not publish ROS commands and is not wired to flight controls.

## Recorded test on November 21, 2026

An offline 95-second replay of `flight_20261031_130708` produced 62 depth packets. Eleven passed tracking, depth-shape and hardware-pose consistency checks, producing 5,635 vertices and 9,843 mesh triangles. Other packets lacked tracking or failed depth checks. The OctoMap exporter produced 22,547 nodes. These are coverage/integration results, **not measured mapping-accuracy results**.

In that Intel CPU run, depth-only inference was often about 0.5–0.7 seconds, with some slower frames. Segmentation, same-frame YOLO and file output add processing time. This background mapper does not provide full-frame-rate collision avoidance.

Before autonomous flights: validate flight-mode calibration, metric dimensions and clearance, test relocalization across actual separate flights, obtain labelled open/closed/frame examples, and evaluate obstacle detection latency. A visible mesh or a predicted open door is not evidence of a safe passage.

Models: [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2), [SegFormer checkpoint](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512). Libraries: [Open3D](https://www.open3d.org/), [OctoMap](https://octomap.github.io/).
