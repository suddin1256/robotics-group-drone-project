# Independent vision workers and ordered SLAM playback

The earlier V4 path ran MiDaS and YOLO serially, limited results to 1 Hz, and refreshed the browser once per second. SLAM read the same overwritten latest-frame file, so it could miss intermediate images when busy. The new paths separate throughput from freshness.

## Full recording experiment

```sh
cd ~/Documents/robotics-group-drone-project
python3 start.py --reuse-existing --bag ~/Documents/tello-recordings/handheld_20261027_185127 --vision --slam-all-frames
```

`--vision` now defaults to two independent processes. YOLO segmentation/ByteTrack reads the latest frame and publishes its own view without waiting for depth. MiDaS reads its own latest frame and publishes a separate depth view. The browser refreshes the views independently. Models are unchanged and no new downloads are needed if existing model preparation passed. Each worker exposes device, inference/render/encoding/read times, input age, output age and observed output FPS. Initial model load/warm-up should be excluded when comparing sustained performance.

Segmentation defaults to a 15 FPS ceiling, not a promise of 15 FPS. MiDaS has its required 384x384 preprocessing; shrinking its input below the model's requirements is not supported. Faster browser refresh does not make inference faster. CPU/GPU contention, memory pressure, model size and unsupported accelerator operations can still limit throughput.

`--slam-all-frames` is **only for recorded ROS bags**. It rebuilds the small adapter against the existing Stella installation, then the bag reader appends every calibrated 320x240 BGR image in order to `runtime/live/slam-input.bin`. Stella reads sequentially at its own pace, using original image timestamps. It no longer discards old frames for this input. The latest-frame ROS/dashboard/V4 path remains independent. Progress shows processed and final expected frame counts; let it drain after playback finishes, until SLAM says finished. All frames being submitted does not guarantee successful tracking or map accuracy.

The temporary spool duplicates image data on disk, about 390 MiB for this recording, and is capped at 2 GiB per run. It is local, ignored by Git and replaced on the next launch. Exceeding the cap stops with an error rather than silently dropping frames. Live flight keeps latest-frame behavior; unbounded old-image backlogs would be inappropriate for live perception.

## Isolate stages

- `--vision --vision-mode objects-only --no-slam`: YOLO alone.
- `--vision --no-slam`: separate YOLO and depth, without SLAM contention.
- Omit `--vision`, keep `--slam-all-frames`: every recorded image through SLAM only.
- `--vision --vision-mode combined`: original V4 reference-ratio visualization, retained for comparison.

Use the same recording, playback rate and resolution for comparisons. The JSON files `vision-status.json`, `depth-status.json` and `slam-status.json` contain diagnostic counters/timings. Each image's own timestamp is shown; a fast YOLO result and an older depth result are not presented as a synchronized measurement.

## Obstacle-detection scope

Current YOLO weights segment learned object categories; they do not identify every possible obstacle, wall, wire or transparent surface. MiDaS is relative depth, not calibrated clearance. The split views do not compute object distances or fuse asynchronous depth with masks. Neither path sends flight commands. Reliable avoidance requires separate evaluation of latency, missed obstacles, depth/pose uncertainty, stopping distance and failure behavior before connecting perception to control.

Next optimization decisions should follow sustained per-stage timings: lighter models, verified accelerator/export backends, reduced inference frequency, or a faster worker machine. The architecture change removes unnecessary waiting between models; it cannot guarantee either heavy model runs at camera speed.

## Initial measured result

On the Intel Mac, the handheld recording was stress-tested at 4x playback with both independent models and ordered SLAM. Every one of the 1,774 recorded images was submitted to Stella and the processed/expected counters matched at completion. Both model views generated output and the test shut down automatically.

There were 69 YOLO and 7 depth output samples. Excluding the first output from each model, median model times were 0.316 seconds for YOLO and 5.008 seconds for MiDaS. This is a limited accelerated-playback test with shared CPU load, not a claim of real-time obstacle detection or a controlled comparison to prior 1x runs. It confirms that depth is still a bottleneck while YOLO can update independently. Nineteen source/launcher tests passed. Next, repeat at 1x with each worker isolated, then select a smaller depth model or optimized backend based on those measurements.
