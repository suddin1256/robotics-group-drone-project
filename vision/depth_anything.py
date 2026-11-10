"""Depth Anything V2 Small through ONNX Runtime; relative inverse depth, not meters.
Heavy imports stay inside the class so launcher tests run without vision packages.
"""
REPO = 'onnx-community/depth-anything-v2-small'
MODEL_FILE = 'onnx/model_int8.onnx'
# Bridge frames are 240 pixels tall; larger inputs only upscale the same detail.
DEFAULT_SIZE = 238

def input_shape(width, height, size=DEFAULT_SIZE):
    """Model input (width, height): both multiples of 14 (ViT patch size), aspect kept."""
    rows = max(14, round(size / 14) * 14)
    columns = max(14, round(size * width / height / 14) * 14)
    return columns, rows

class DepthAnything:
    def __init__(self, size=DEFAULT_SIZE, download=False):
        import numpy as np
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        # Normal runs are offline; only model preparation may download.
        path = hf_hub_download(REPO, MODEL_FILE, local_files_only=not download)
        ort.set_default_logger_severity(3)
        # On an M1, CoreML measured slower than CPU for this model, so CPU only.
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(path, options, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.size = size
        self.mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self.std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def predict(self, frame):
        """BGR uint8 frame -> float32 relative inverse depth (larger = closer), frame-sized."""
        import cv2
        height, width = frame.shape[:2]
        resized = cv2.resize(frame, input_shape(width, height, self.size), interpolation=cv2.INTER_CUBIC)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pixels = ((rgb.astype('float32') / 255 - self.mean) / self.std).transpose(2, 0, 1)[None]
        depth = self.session.run(None, {self.input_name: pixels})[0].squeeze()
        return cv2.resize(depth, (width, height))
