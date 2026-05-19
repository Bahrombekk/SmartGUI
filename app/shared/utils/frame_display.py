"""Video frame'ni UIga tayyorlash helperlari."""
from __future__ import annotations

import cv2
import numpy as np
from PyQt6.QtGui import QImage


def resize_for_display(frame: np.ndarray, max_width: int) -> np.ndarray:
    """Frame kengligini cheklaydi, aspect ratio saqlanadi."""
    if max_width <= 0:
        return frame
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    new_height = max(1, int(height * (max_width / width)))
    return cv2.resize(frame, (max_width, new_height), interpolation=cv2.INTER_AREA)


def frame_to_qimage(frame: np.ndarray) -> QImage | None:
    """OpenCV BGR frame'ni Qt ko'rsatadigan QImage formatiga o'tkazadi."""
    if frame is None or frame.size == 0:
        return None
    if len(frame.shape) < 3 or frame.shape[2] != 3:
        return None  # grayscale yoki buzilgan channel
    height, width = frame.shape[:2]
    if height < 4 or width < 4:
        return None
    try:
        if hasattr(QImage.Format, "Format_BGR888"):
            img = QImage(frame.data, width, height, 3 * width, QImage.Format.Format_BGR888)
            copied = img.copy()
            return copied if not copied.isNull() else None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.tobytes(), width, height, 3 * width, QImage.Format.Format_RGB888)
        return img if not img.isNull() else None
    except Exception:
        return None


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (22, 115, 249)  # fallback orange BGR
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


def draw_helmet_overlay(
    frame: np.ndarray,
    persons: list[dict],
    polygon_points: list | None = None,
    polygon_color: str = "#f97316",
) -> np.ndarray:
    """Display frame ustiga odam boxlari, holat ranglari va polygon zona chizadi."""
    height, width = frame.shape[:2]

    # ── Polygon zona ─────────────────────────────────────────────────────
    if polygon_points and len(polygon_points) >= 3:
        pts = np.array(
            [[int(p[0] * width), int(p[1] * height)] for p in polygon_points],
            dtype=np.int32,
        )
        bgr = _hex_to_bgr(polygon_color)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], bgr)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
        cv2.polylines(frame, [pts], isClosed=True, color=bgr, thickness=2)
        mx = min(p[0] for p in pts)
        my = min(p[1] for p in pts)
        cv2.putText(frame, "ZONE", (mx + 4, my + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, bgr, 1, cv2.LINE_AA)

    # ── Odam boxlari ─────────────────────────────────────────────────────
    if persons:
        for person in persons:
            box = person.get("box", person.get("bbox_xyxy", []))
            if len(box) < 4:
                continue
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            has_helmet = person.get("has_helmet")
            if has_helmet is True:
                color = (0, 200, 0)
            elif has_helmet is False:
                color = (0, 0, 220)
            else:
                color = (0, 255, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    cv2.rectangle(frame, (0, 0), (width, 36), (10, 14, 20), -1)
    cv2.rectangle(frame, (0, height - 32), (width, height), (10, 14, 20), -1)
    return frame
