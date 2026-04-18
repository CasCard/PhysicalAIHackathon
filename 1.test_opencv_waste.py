import cv2
import numpy as np
import json
import sys

# ── Detection result (paste your JSON here or load from file) ──────────────
DETECTION = {
    "image_width": 640,
    "image_height": 960,
    "objects": [
        {
            "id": "obj1",
            "class": "apple/fruit waste",
            "bin": "green",
            "confidence": 0.95,
            "bbox": {"x_min": 320, "y_min": 740, "x_max": 410, "y_max": 830},
            "pick_point": {"x": 365, "y": 785},
            "reason_ml": "Fruit waste → Green bin",
            "carbon_g": 10,
            "action": "PICK",
        },
        {
            "id": "obj2",
            "class": "apple/fruit waste",
            "bin": "green",
            "confidence": 0.92,
            "bbox": {"x_min": 415, "y_min": 730, "x_max": 500, "y_max": 810},
            "pick_point": {"x": 457, "y": 770},
            "reason_ml": "Fruit waste → Green bin",
            "carbon_g": 10,
            "action": "PICK",
        },
        {
            "id": "obj3",
            "class": "apple/fruit waste",
            "bin": "green",
            "confidence": 0.90,
            "bbox": {"x_min": 510, "y_min": 780, "x_max": 600, "y_max": 840},
            "pick_point": {"x": 555, "y": 810},
            "reason_ml": "Organic waste → Green bin",
            "carbon_g": 10,
            "action": "PICK",
        },
        {
            "id": "obj4",
            "class": "apple/fruit waste",
            "bin": "green",
            "confidence": 0.88,
            "bbox": {"x_min": 615, "y_min": 730, "x_max": 700, "y_max": 810},
            "pick_point": {"x": 657, "y": 770},
            "reason_ml": "Organic waste → Green bin",
            "carbon_g": 10,
            "action": "PICK",
        },
        {
            "id": "obj5",
            "class": "apple/fruit waste",
            "bin": "green",
            "confidence": 0.85,
            "bbox": {"x_min": 710, "y_min": 820, "x_max": 800, "y_max": 900},
            "pick_point": {"x": 755, "y": 860},
            "reason_ml": "Organic waste → Green bin",
            "carbon_g": 10,
            "action": "PICK",
        },
    ],
}

# Bin → BGR colour mapping
BIN_COLORS = {
    "green":  (34, 139, 34),
    "blue":   (200, 80, 20),
    "red":    (30, 30, 200),
    "yellow": (20, 200, 200),
    "black":  (50, 50, 50),
}

def draw_detections(image: np.ndarray, detection: dict) -> np.ndarray:
    """Resize image to detection canvas, then draw all annotations 1-to-1."""
    det_w = detection["image_width"]
    det_h = detection["image_height"]

    # Resize to detection resolution so coordinates map exactly
    image = cv2.resize(image, (det_w, det_h), interpolation=cv2.INTER_LINEAR)

    sx, sy = 1.0, 1.0   # no further scaling needed

    overlay = image.copy()

    for obj in detection["objects"]:
        color = BIN_COLORS.get(obj["bin"].lower(), (255, 255, 255))

        bbox = obj["bbox"]
        x1 = int(bbox["x_min"] * sx)
        y1 = int(bbox["y_min"] * sy)
        x2 = int(bbox["x_max"] * sx)
        y2 = int(bbox["y_max"] * sy)

        px = int(obj["pick_point"]["x"] * sx)
        py = int(obj["pick_point"]["y"] * sy)

        # Semi-transparent filled rectangle
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)

        # Solid border
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

        # Pick-point crosshair
        cv2.drawMarker(image, (px, py), (255, 255, 255),
                       cv2.MARKER_CROSS, markerSize=14, thickness=2)

        # ── Label background ────────────────────────────────────────────────
        label_lines = [
            f"{obj['id']}  [{obj['bin'].upper()} BIN]",
            f"{obj['class']}  {obj['confidence']*100:.0f}%",
            f"Carbon: {obj['carbon_g']}g  |  {obj['action']}",
        ]
        font       = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.45
        thickness  = 1
        line_h     = 16
        pad        = 4

        text_w = max(cv2.getTextSize(l, font, font_scale, thickness)[0][0]
                     for l in label_lines)
        text_h = len(label_lines) * line_h

        lx1 = x1
        ly1 = max(0, y1 - text_h - 2 * pad)
        lx2 = x1 + text_w + 2 * pad
        ly2 = y1

        cv2.rectangle(image, (lx1, ly1), (lx2, ly2), color, -1)
        for i, line in enumerate(label_lines):
            ty = ly1 + pad + (i + 1) * line_h - 3
            cv2.putText(image, line, (lx1 + pad, ty),
                        font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

    # Blend overlay for transparent fill
    alpha = 0.25
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
    return image


def main():
    # Accept image path as CLI argument or use a default
    image_path = sys.argv[1] if len(sys.argv) > 1 else "waste.jpg"

    image = cv2.imread(image_path)
    if image is None:
        print(f"[ERROR] Could not load image: {image_path}")
        print("Usage:  python 1.test_opencv_waste.py <path_to_image>")
        sys.exit(1)

    result = draw_detections(image, DETECTION)

    # ── Summary overlay (bottom-left) ──────────────────────────────────────
    total_carbon = sum(o["carbon_g"] for o in DETECTION["objects"])
    summary = (f"Objects: {len(DETECTION['objects'])}  |  "
               f"Total Carbon Saved: {total_carbon}g  |  All → GREEN BIN")
    cv2.rectangle(result, (0, result.shape[0] - 28), (result.shape[1], result.shape[0]),
                  (20, 20, 20), -1)
    cv2.putText(result, summary, (8, result.shape[0] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 255, 200), 1, cv2.LINE_AA)

    out_path = "output_detections.jpg"
    cv2.imwrite(out_path, result)
    print(f"[OK] Saved annotated image → {out_path}")

    # Scale display window to fit screen (max 900 px tall)
    display_h = 900
    display_w = int(result.shape[1] * display_h / result.shape[0])
    display = cv2.resize(result, (display_w, display_h), interpolation=cv2.INTER_AREA)

    cv2.imshow("Waste Detection", display)
    print("Press any key to close …")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
