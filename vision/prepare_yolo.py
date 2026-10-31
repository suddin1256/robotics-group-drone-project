"""Run once while online to cache the lightweight segmentation model."""
from pathlib import Path
import os

root = Path(__file__).resolve().parents[1]
models = root / 'vision/models'
models.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('YOLO_CONFIG_DIR', str(models / 'ultralytics-config'))
os.environ.setdefault('ULTRALYTICS_AUTOINSTALL', 'false')

if __name__ == '__main__':
    import numpy as np
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(2)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    model = YOLO(str(models / 'yolo11n-seg.pt'))
    model.predict(np.zeros((240, 320, 3), dtype=np.uint8), imgsz=320,
                  device=device, verbose=False)
    print(f'YOLO nano cached and warm-up passed on {device}.')
