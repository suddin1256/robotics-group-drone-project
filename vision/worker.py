"""Optional V4 worker. Reads bridge frames; never connects to the drone."""
import argparse
import json
import os
from pathlib import Path
import signal
import time
import traceback
from frame_io import read_packet

ROOT = Path(__file__).resolve().parents[1]

def write_status(folder, **data):
    data['stamp_ns'] = time.time_ns()
    temporary = folder / 'vision-status.tmp'
    temporary.write_text(json.dumps(data))
    temporary.replace(folder / 'vision-status.json')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--reference-confirmed', action='store_true',
                        help='Reference object fills ROI and stays 20cm away; labels remain experimental')
    parser.add_argument('--max-fps', type=float, default=1)
    args = parser.parse_args()
    folder = Path(os.environ.get('TELLO_RUNTIME_DIR', str(ROOT / 'runtime/live')))
    folder.mkdir(parents=True, exist_ok=True)
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        write_status(folder, state='loading', message='Loading YOLO and MiDaS; CPU inference may be slow.')
        os.environ.setdefault('ULTRALYTICS_AUTOINSTALL', 'false')
        os.environ.setdefault('HF_HOME', str(ROOT / 'vision/models/huggingface'))
        import cv2
        import numpy as np
        import torch
        from ultralytics import YOLO
        from transformers import pipeline
        from v4_engine import process
        torch.set_num_threads(2)
        cv2.setNumThreads(1)
        device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        models = ROOT / 'vision/models'
        models.mkdir(parents=True, exist_ok=True)
        os.chdir(models)
        segmenter = YOLO(str(models / 'yolo11s-seg.pt'))
        depth = pipeline(task='depth-estimation', model='Intel/dpt-hybrid-midas', device=device)

        if args.prepare:
            process(np.zeros((240, 320, 3), dtype=np.uint8), segmenter, depth, device)
            write_status(folder, state='ready', message='Models cached and inference warm-up passed.')
            print('Models cached and inference warm-up passed.', flush=True)
            return 0
        previous = 0
        output_stamp = None
        while not stopping:
            packet = read_packet(folder / 'frame.bin', previous)
            if packet is None:
                write_status(folder, state='waiting', message='Waiting for a fresh bridge frame.', device=device,
                             output_stamp_ns=output_stamp)
                time.sleep(0.5)
                continue
            stamp, width, height, pixels = packet
            previous = stamp
            frame = np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 3).copy()
            start = time.monotonic()
            write_status(folder, state='processing', message='Processing latest frame.', device=device,
                         frame_stamp_ns=int(stamp * 1e9), output_stamp_ns=output_stamp)
            result, count = process(frame, segmenter, depth, device, args.reference_confirmed)
            elapsed = time.monotonic() - start
            ok, jpeg = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                temporary = folder / 'vision.tmp.jpg'
                temporary.write_bytes(jpeg.tobytes())
                temporary.replace(folder / 'vision.jpg')
                output_stamp = int(stamp * 1e9)
            write_status(folder, state='running', message='Experimental relative depth; not measured distance.',
                         frame_stamp_ns=int(stamp * 1e9), inference_seconds=elapsed,
                         objects=count, device=device, reference_confirmed=args.reference_confirmed,
                         output_stamp_ns=output_stamp)
            print(f'Vision: {elapsed:.2f}s/frame | objects={count} | source age={time.time()-stamp:.1f}s', flush=True)
            time.sleep(max(0, 1 / max(args.max_fps, 0.1) - elapsed))
    except Exception as error:
        write_status(folder, state='error', message=str(error))
        traceback.print_exc()
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
