# Rian's vision styling and SLAM views

The default independent YOLO view uses Rian's V4 outlined Hershey text, thin segmentation contours and light mask tint instead of Ultralytics' default large IDs, rectangles and labels. It draws on a 640x480 copy for the original annotation scale but keeps inference at 320 pixels; all supplied camera pixels remain visible. Both independent vision panels display at 480 CSS pixels wide with their 4:3 aspect ratio preserved. Browser resizing is not digital zoom or additional field-of-view cropping. Contour polygons are mapped to original image coordinates before rendering, avoiding letterbox-mask stretching.

The split view identifies object classes and does not show the original reference-depth ratio numbers. Those were relative scores, not metric distances. Because YOLO and MiDaS now process different timestamped frames, they are not silently joined into object-distance estimates. The original combined algorithm remains available via `--vision-mode combined`, with reference validation still required.

## Two interactive views of the same map

The original sparse landmark map is retained. The second `3D landmark blocks` canvas groups those same points into spatial cells and draws shaded blocks, with orbit, zoom, fit, reset, top-view and block-detail controls. Orange markers show camera keyframe positions, not a continuous ordered trajectory or independently measured drone position. At most 1,800 landmark cells are rendered to bound UI cost; the caption reports any display cap. Changing block detail only changes the visualization.

This does not reconstruct solid surfaces, estimate occupied/free space, assign semantic object labels in 3D, or prove empty regions are traversable. The grid is a reference plane in arbitrary-scale SLAM coordinates, not a detected floor or gravity direction. Auto-fit can be disabled to avoid rescaling as the map changes.

## Telemetry and future pose fusion

Native telemetry is shown as separate context and is not fed into Stella's pose estimation. The handheld recording reports zero height/north/east speed while the camera is physically moved; these fields cannot be assumed to describe that camera trajectory. Native units and coordinate conventions have not been validated, and the current recorded state feed does not include the synchronized raw IMU samples required by a visual-inertial estimator.

Telemetry-assisted estimation is a future integration task: verify each available measurement, timing, units and coordinate frames; calibrate camera-to-body alignment; select an estimator accepting those inputs; and compare against independent ground truth. Simply replacing Stella's pose with raw telemetry would not validate or improve localization. Camera calibration/crop consistency and monocular scale remain separate concerns.

No changes in this UI update add drone commands, depth-based avoidance or telemetry fusion. MiDaS tuning is intentionally deferred.
