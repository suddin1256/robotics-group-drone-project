"""Adapted teammate V4 processing; no webcam, ROS, or drone connection.
MiDaS produces relative inverse-depth scores, not centimeters.
"""
import cv2
import torch
import numpy as np
from PIL import Image
W, H = 640, 480
REFERENCE_BOX = (120, 260, 190, 440)
THRESHOLDS = [(0.80, "VERY CLOSE", (0,0,255)), (0.50, "CLOSE", (0,140,255)),
              (0.30, "MEDIUM", (0,255,255)), (0.15, "FAR", (0,255,0))]

def proximity_label(value, reference):
    ratio = value / max(reference, 1e-6)

    for threshold, label, color in THRESHOLDS:
        if ratio >= threshold:
            return label, color

    return "VERY FAR", (255, 180, 0)

def draw_text(image, text, x, y, color, scale=0.45):
    cv2.putText(
        image,
        text,
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (0, 0, 0),
        4,
        cv2.LINE_AA
    )

    cv2.putText(
        image,
        text,
        (int(x), int(y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        2,
        cv2.LINE_AA
    )

def process(frame, segmenter, depth_model, device="cpu", reference_confirmed=False):
    frame = cv2.resize(frame, (W, H))
    display = frame.copy()

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # =====================================
    # 1. DEPTH ESTIMATION
    # =====================================

    with torch.inference_mode():
        result = depth_model(Image.fromarray(rgb))

    raw = (
        result["predicted_depth"]
        .squeeze()
        .detach()
        .cpu()
        .numpy()
    )

    raw = cv2.resize(raw, (W, H))
    raw = cv2.GaussianBlur(raw, (5, 5), 0)

    normalized = cv2.normalize(
        raw,
        None,
        0,
        255,
        cv2.NORM_MINMAX
    ).astype(np.uint8)

    heatmap = cv2.applyColorMap(
        normalized,
        cv2.COLORMAP_INFERNO
    )

    # =====================================
    # 2. REFERENCE OBJECT
    # =====================================

    rx1, ry1, rx2, ry2 = REFERENCE_BOX

    reference_region = raw[ry1:ry2, rx1:rx2]

    if reference_region.size > 0:
        # Upper percentile reduces the influence
        # of farther background inside the box.
        reference_depth = float(
            np.percentile(reference_region, 85)
        )
    else:
        reference_depth = float("nan")

    reference_valid = reference_confirmed and (
        np.isfinite(reference_depth)
        and reference_depth > 0
    )

    cv2.rectangle(
        display,
        (rx1, ry1),
        (rx2, ry2),
        (255, 255, 255),
        2
    )

    if reference_valid:
        reference_text = f"REFERENCE SCORE: {reference_depth:.0f}"
    else:
        reference_text = "REFERENCE UNCONFIRMED"

    draw_text(
        display,
        reference_text,
        rx1,
        max(20, ry1 - 12),
        (255, 255, 255)
    )

    # =====================================
    # 3. YOLO INSTANCE SEGMENTATION
    # =====================================

    detections = segmenter.track(
        frame,
        persist=True,
        tracker="bytetrack.yaml",
        conf=0.15,
        iou=0.5,
        imgsz=320,
        device=device,
        verbose=False
    )[0]
    object_count = 0

    if detections.masks is not None:

        masks = detections.masks.data.cpu().numpy()
        boxes = detections.boxes

        for i, mask in enumerate(masks):

            confidence = float(boxes.conf[i].item())

            if confidence < 0.25:
                continue

            class_id = int(boxes.cls[i].item())
            class_name = segmenter.names[class_id]

            object_type = (
                "HUMAN"
                if class_name == "person"
                else "OBJECT"
            )

            # Resize each segmentation mask
            mask = cv2.resize(
                mask.astype(np.float32),
                (W, H),
                interpolation=cv2.INTER_LINEAR
            )

            object_mask = mask > 0.5

            if np.count_nonzero(object_mask) < 100:
                continue

            # Measure depth from the object's
            # actual mask, not its bounding box.
            values = raw[object_mask]
            values = values[np.isfinite(values)]

            if values.size == 0:
                continue

            # 75th percentile emphasizes nearer
            # portions of the detected object.
            object_depth = float(
                np.percentile(values, 75)
            )

            if reference_valid:
                label, color = proximity_label(
                    object_depth,
                    reference_depth
                )
            else:
                label = "UNKNOWN"
                color = (255, 200, 0)

            # Draw individual object outline
            mask_uint8 = (
                object_mask.astype(np.uint8) * 255
            )

            contours, _ = cv2.findContours(
                mask_uint8,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            cv2.drawContours(
                display,
                contours,
                -1,
                color,
                2
            )

            # Transparent segmentation overlay
            overlay = display.copy()
            overlay[object_mask] = (
                0.85 * overlay[object_mask]
                + 0.15 * np.array(color)
            ).astype(np.uint8)

            display = overlay

            # Bounding rectangle for text placement
            x1, y1, x2, y2 = map(
                int,
                boxes.xyxy[i].cpu().tolist()
            )

            text = (
                f"{object_type}: {label} "
                f"({object_depth:.0f})"
            )

            draw_text(
                display,
                text,
                max(0, x1),
                max(20, y1 - 8),
                color
            )

            object_count += 1

    # =====================================
    # 4. STATUS
    # =====================================

    draw_text(
        display,
        f"Objects detected: {object_count}",
        10,
        H - 15,
        (255, 255, 255),
        0.55
    )

    draw_text(
        heatmap,
        "RELATIVE DEPTH",
        10,
        28,
        (255, 255, 255),
        0.6
    )

    # =====================================
    # 5. DISPLAY
    # =====================================

    combined = np.hstack((display, heatmap))

    return combined, object_count
