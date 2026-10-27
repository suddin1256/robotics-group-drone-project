"""Independent latest-frame segmentation/depth workers; no flight commands or ROS imports."""
import argparse
import json
import os
from pathlib import Path
import signal
import time
import traceback
from frame_io import read_packet

ROOT = Path(__file__).resolve().parents[1]

def atomic_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data))
    temporary.replace(path)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['objects', 'depth'], required=True)
    parser.add_argument('--max-fps', type=float, default=15)
    args = parser.parse_args()
    folder = Path(os.environ.get('TELLO_RUNTIME_DIR', str(ROOT/'runtime/live')))
    folder.mkdir(parents=True, exist_ok=True)
    name = 'vision' if args.stage == 'objects' else 'depth'
    status_path = folder / f'{name}-status.json'
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    last_result = {}
    def status(state, message, **extra):
        data = dict(last_result, state=state, message=message, stage=args.stage, stamp_ns=time.time_ns(), **extra)
        atomic_json(status_path, data)
    try:
        status('loading', f'Loading independent {args.stage} model.')
        os.environ.setdefault('ULTRALYTICS_AUTOINSTALL', 'false')
        os.environ.setdefault('HF_HOME', str(ROOT/'vision/models/huggingface'))
        os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT/'vision/models/ultralytics-config'))
        os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'vision/models/matplotlib'))
        import cv2
        import numpy as np
        import torch
        torch.set_num_threads(2)
        cv2.setNumThreads(1)
        device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        def sync():
            if device == 'mps':
                torch.mps.synchronize()
        models = ROOT/'vision/models'
        models.mkdir(parents=True, exist_ok=True)
        os.chdir(models)
        if args.stage == 'objects':
            from ultralytics import YOLO
            model_name = 'yolo11s-seg.pt'
            model = YOLO(str(models/model_name))
        else:
            from transformers import pipeline
            from PIL import Image
            model_name = 'Intel/dpt-hybrid-midas'
            model = pipeline(task='depth-estimation', model=model_name, device=device)
        last_result.update(device=device, model=model_name)
        previous = 0
        processed = 0
        last_idle = 0
        last_complete = None
        status('waiting', 'Model ready; waiting for a fresh frame.')
        while not stopping:
            read_start = time.monotonic()
            packet = read_packet(folder/'frame.bin', previous)
            read_seconds = time.monotonic() - read_start
            if packet is None:
                if time.monotonic() - last_idle > .5:
                    status('waiting', 'Waiting for a new camera frame.')
                    last_idle = time.monotonic()
                time.sleep(.01)
                continue
            stamp, width, height, pixels = packet
            previous = stamp
            frame = np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 3).copy()
            frame_age_at_start = time.time() - stamp
            status('processing', f'Independent {args.stage} inference.')
            sync()
            start = time.monotonic()
            if args.stage == 'objects':
                with torch.inference_mode():
                    result = model.track(frame, persist=True, tracker='bytetrack.yaml', conf=.25,
                                         iou=.5, imgsz=320, device=device, verbose=False)[0]
                sync()
                inference_seconds = time.monotonic() - start
                render_start = time.monotonic()
                display = result.plot()
                count = len(result.boxes) if result.boxes is not None else 0
                cv2.putText(display, 'YOLO only - no distance measurement', (5,15),
                            cv2.FONT_HERSHEY_SIMPLEX,.35,(255,255,255),1)
            else:
                with torch.inference_mode():
                    result = model(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                raw = result['predicted_depth'].squeeze().detach().cpu().numpy()
                sync()
                inference_seconds = time.monotonic() - start
                render_start = time.monotonic()
                raw = cv2.resize(raw, (width,height))
                normalized = cv2.normalize(raw,None,0,255,cv2.NORM_MINMAX).astype(np.uint8)
                display = cv2.applyColorMap(normalized,cv2.COLORMAP_INFERNO)
                count = None
                cv2.putText(display, 'Relative depth - not meters', (5,15),
                            cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
            render_seconds = time.monotonic() - render_start
            encode_start = time.monotonic()
            ok, jpeg = cv2.imencode('.jpg',display,[cv2.IMWRITE_JPEG_QUALITY,80])
            if ok:
                temporary = folder/f'{name}.tmp.jpg'
                temporary.write_bytes(jpeg.tobytes())
                temporary.replace(folder/f'{name}.jpg')
            encode_seconds = time.monotonic() - encode_start
            complete = time.monotonic()
            processed += 1
            last_result.update(frame_stamp_ns=int(stamp*1e9), output_stamp_ns=int(stamp*1e9),
                               inference_seconds=inference_seconds, render_seconds=render_seconds,
                               encode_seconds=encode_seconds, frame_read_seconds=read_seconds,
                               input_age_seconds=frame_age_at_start, objects=count,
                               observed_fps=(1/(complete-last_complete) if last_complete is not None else None),
                               processed_frames=processed)
            last_complete = complete
            status('running', 'Latest-frame processing; old frames are deliberately skipped, never queued.')
            print(f'{args.stage}: model={inference_seconds:.3f}s render={render_seconds:.3f}s '
                  f'encode={encode_seconds:.3f}s input_age={frame_age_at_start:.3f}s '
                  f'output_age={time.time()-stamp:.3f}s device={device}',flush=True)
            time.sleep(max(0, 1/max(args.max_fps,.1) - (complete-start)))
    except Exception as error:
        status('error', str(error))
        traceback.print_exc()
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
