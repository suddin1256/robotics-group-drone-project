# Mapping fusion experiment

The optional `--map-fusion adaptive` mode blends already aligned visual and telemetry positions for mapping. It never controls flight. Default is **off**.

It requires the existing robust scale/coordinate alignment to pass. It retains the existing rejection of large telemetry/visual disagreement. Blending also requires fresh telemetry, at least 12 positive-depth reprojection inliers, and median reprojection error no greater than 3 pixels. A weak frame retains the baseline mapper behavior rather than forcing an average.

Weights vary with sample age, metric speed magnitude, visual support, reprojection error and alignment residual. The noise constants are **prototype tuning assumptions, not calibrated covariances or confidence probabilities**. This is a position blend, not an EKF/VIO implementation. It does not integrate acceleration, infer velocity axes, predict through tracking loss, or solve calibration errors.

## November 21 comparison

Baseline and adaptive modes were evaluated against identical frozen SLAM maps, observations, detections, depth images and frame telemetry. This avoids attributing different SLAM runs to fusion. It does not evaluate how a future closed-loop estimator would behave.

| Input | Baseline | Adaptive |
| --- | --- | --- |
| Forward/back test, November 21 | 54 pose frames, 4,256 depth samples, no objects; alignment rejected (6 pairs) | Identical output; no fusion applied |
| Archived room replay, October 31 | 17 accepted pose frames, 8 tentative objects, 1,970 depth samples | 17 fused frames; same objects/sample counts; median pose adjustment 0.044 m, maximum 0.116 m |

The room comparison rejected the same 42 disagreeing frames in both modes. Adjusting a pose is not evidence it became more accurate. There is no independently measured camera trajectory or object map for these outputs, so **accuracy improvement is not established**. The default remains unchanged.

## Try offline

On Shadib's Mac:

```bash
python3 start.py --reuse-existing \
  --bag ~/Documents/tello-recordings/flight_20261121_093748 \
  --slam-all-frames --vision --map-fusion adaptive
```

For an exact frozen-input comparison, use the vision Python environment:

```bash
vision/.venv/bin/python scripts/compare_mapping_fusion.py \
  --input /path/to/saved/runtime/live \
  --output .local/fusion_comparison/my_test
```

It writes separate `off.json`, `adaptive.json` and `comparison.json` files. Original captures are not modified. Local evidence from this experiment is under `.local/fusion_comparison/` and is excluded from Git.
