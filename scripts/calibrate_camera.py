from pathlib import Path
import json
import cv2
import numpy as np

folder = Path("calibration_images/20261012_140301")
pattern = (7, 5)
square_m = 0.0235

board = np.zeros((pattern[0] * pattern[1], 3), np.float32)
board[:, :2] = np.mgrid[0:7, 0:5].T.reshape(-1, 2)
board *= square_m

objects, points, names = [], [], []
size = None

for path in sorted(folder.glob("image_*.png")):
    image = cv2.imread(str(path))
    if image is None:
        continue
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    current_size = (gray.shape[1], gray.shape[0])
    if size is not None and current_size != size:
        raise RuntimeError("Images have different resolutions.")
    size = current_size
    found, corners = cv2.findChessboardCornersSB(gray, pattern)
    if found:
        objects.append(board.copy())
        points.append(corners)
        names.append(path.name)

if len(points) < 10:
    raise RuntimeError(f"Only {len(points)} usable images; need more views.")

rms, matrix, distortion, rotations, translations = cv2.calibrateCamera(
    objects, points, size, None, None
)

errors = {}
for name, obj, measured, rotation, translation in zip(
        names, objects, points, rotations, translations):
    projected, _ = cv2.projectPoints(
        obj, rotation, translation, matrix, distortion)
    error = np.sqrt(np.mean(np.sum(
        (measured.reshape(-1, 2) - projected.reshape(-1, 2))**2,
        axis=1)))
    errors[name] = float(error)

result = {
    "image_width": size[0],
    "image_height": size[1],
    "square_size_m": square_m,
    "usable_images": len(points),
    "rms_reprojection_error_px": float(rms),
    "camera_matrix": matrix.tolist(),
    "distortion_coefficients": distortion.flatten().tolist(),
    "per_image_error_px": errors
}

output = folder / "calibration.json"
output.write_text(json.dumps(result, indent=2))
print(f"Usable images: {len(points)}; resolution: {size}")
print(f"RMS reprojection error: {rms:.3f} pixels")
print("Camera matrix:\n", matrix)
print("Distortion:", distortion.flatten())
print("Per-image errors:")
for name, error in sorted(errors.items(), key=lambda item: -item[1]):
    print(f"  {name}: {error:.3f} px")
print(f"Saved {output}")
