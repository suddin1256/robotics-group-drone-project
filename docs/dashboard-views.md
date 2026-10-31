# Rian's vision styling and SLAM views

The default independent YOLO view uses Rian's V4 outlined Hershey text, thin segmentation contours and light mask tint instead of Ultralytics' default large IDs, rectangles and labels. It draws on a 640x480 copy for the original annotation scale but keeps inference at 320 pixels; all supplied camera pixels remain visible. Both independent vision panels display at 480 CSS pixels wide with their 4:3 aspect ratio preserved. Browser resizing is not digital zoom or additional field-of-view cropping. Contour polygons are mapped to original image coordinates before rendering, avoiding letterbox-mask stretching.

The split view identifies object classes and does not show the original reference-depth ratio numbers. Those were relative scores, not metric distances. Because YOLO and MiDaS now process different timestamped frames, they are not silently joined into object-distance estimates. The original combined algorithm remains available via `--vision-mode combined`, with reference validation still required.

## Two interactive views of the same map

The newer default **Concept preview** is deliberately a separate, synthetic scene: smooth gray example obstacle volumes, an orange example person and a blue drone marker. A permanent canvas badge and surrounding text identify it as an illustration, not a result from the camera or models. It never uses incoming SLAM points or telemetry to generate its objects, and is not used for flight. **Actual SLAM data** switches back to the existing measured sparse-landmark visualization. No occupancy inference was added by changing the appearance.

For a presentation without running any robot software, open `ros/map_concept.html` in a browser. It loads the local JavaScript beside it and supports rotation, zoom, reset and top view. It needs no drone, ROS environment, model downloads or internet. Explain that depth/pose alignment and occupancy fusion are still development work.

The original sparse landmark map is retained. The second `3D landmark blocks` canvas groups those same points into spatial cells and draws shaded blocks, with orbit, zoom, fit, reset, top-view and block-detail controls. Orange markers show camera keyframe positions, not a continuous ordered trajectory or independently measured drone position. At most 1,800 landmark cells are rendered to bound UI cost; the caption reports any display cap. Changing block detail only changes the visualization.

This does not reconstruct solid surfaces, estimate occupied/free space, assign semantic object labels in 3D, or prove empty regions are traversable. The grid is a reference plane in arbitrary-scale SLAM coordinates, not a detected floor or gravity direction. Auto-fit can be disabled to avoid rescaling as the map changes.

## Telemetry and future pose fusion

Native telemetry is shown as separate context and is not fed into Stella's pose estimation. The handheld recording reports zero height/north/east speed while the camera is physically moved; these fields cannot be assumed to describe that camera trajectory. Native units and coordinate conventions have not been validated, and the current recorded state feed does not include the synchronized raw IMU samples required by a visual-inertial estimator.

Telemetry-assisted estimation is a future integration task: verify each available measurement, timing, units and coordinate frames; calibrate camera-to-body alignment; select an estimator accepting those inputs; and compare against independent ground truth. Simply replacing Stella's pose with raw telemetry would not validate or improve localization. Camera calibration/crop consistency and monocular scale remain separate concerns.

No changes in this UI update add drone commands, depth-based avoidance or telemetry fusion. MiDaS tuning is intentionally deferred.
# Environment floor plan

**Current implementation:** the landmark-only mapper below has been superseded
by the [combined telemetry/YOLO/depth/SLAM mapper](combined-mapping.md). It uses a
native telemetry coordinate frame with gated visual/depth alignment and reports
all inputs and rejected contributions. The description below documents the
earlier landmark-only behavior for context.

The active dashboard replaces the separate sparse projection and synthetic
concept panel with one object-placement floor plan. Run with `--vision` and
SLAM enabled (split or objects-only vision). Combined legacy V4 does not export
the detection masks needed for placement. Existing standalone concept files
remain historical illustrations; they are not loaded by the dashboard.

Each YOLO result stores its segmentation polygon and exact source timestamp.
The SLAM adapter exports original-image feature coordinates and matched landmark
IDs for each tracked frame. The floor-plan worker matches identical timestamps,
selects landmarks within each object mask, requires at least six support points,
and joins observations only when the class and landmark support overlap.
People are excluded from the static map. A single observation is dashed and
marked tentative; repeated matching observations use a solid outline.

Footprints are trimmed extents of visible supporting landmarks, not complete
furniture dimensions or verified occupancy. Coordinates are resolved against
the latest optimized map so they follow SLAM corrections. Associations clear
when the map origin changes. Frames without matching observations, objects
with insufficient 3D evidence, and deleted landmarks are left unplaced.
Nested masks, background features inside masks, calibration errors and tracking
failures can still produce wrong or incomplete placements. There is no collision
avoidance or metric scale. The plane selection still needs a level-camera
assumption; no automatic floor or wall extraction is implemented.

Replay preserves source timestamps separately from delivery freshness, so
ordered SLAM can lag behind YOLO without associating different frames. Per-frame
metadata archives are bounded to 2048 frames and cleared at each launch.
The perception worker never reads or publishes flight commands.

## Supporting feature projection

The dashboard projects actual SLAM landmarks into a selectable X–Z, X–Y or
Y–Z plane and bins them into feature-density cells. Orange connects surviving
camera keyframes in ID order; it is a sparse estimated path, not every pose.
Green marks the first surviving keyframe. Drag to pan, scroll to zoom, and
rotate the projection to orient the view. The default X–Z view assumes the
initial camera was level; there is no automatic floor-plane detection yet.

Blank cells remain unknown. Cells are observed visual features, not confirmed
obstacles or free space, and no walls or metric dimensions are inferred.
YOLO labels, telemetry fusion and depth reconstruction are future work.
The display replaces its data on each SLAM update, including resets, rather
than accumulating inconsistent coordinates from different maps.
