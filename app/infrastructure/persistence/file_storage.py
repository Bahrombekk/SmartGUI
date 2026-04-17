from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


class ViolationFileStorage:
    """Stores crop and full-frame images for a detected violation."""

    def save_violation_images(
        self,
        frame: np.ndarray,
        box: list,
        output_dir: Path,
        track_id: int,
        timestamp: int,
        enabled: bool = True,
    ) -> tuple[str, str, np.ndarray | None]:
        if not enabled or len(box) != 4:
            return "", "", None

        x1, y1, x2, y2 = map(int, box)
        y1a = max(y1 - 10, 0)
        x1a = max(x1 - 5, 0)
        x2a = min(x2 + 5, frame.shape[1])
        y2a = min(y2 + 5, frame.shape[0])

        crop = frame[y1a:y2a, x1a:x2a].copy()
        full = frame.copy()
        cv2.rectangle(full, (x1, y1), (x2, y2), (0, 0, 220), 3)

        output_dir.mkdir(parents=True, exist_ok=True)
        dt_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S")
        crop_path = str(output_dir / f"crop_{dt_str}_id{track_id}.jpg")
        full_path = str(output_dir / f"full_{dt_str}_id{track_id}.jpg")

        if crop.size > 0:
            cv2.imwrite(crop_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(full_path, full, [cv2.IMWRITE_JPEG_QUALITY, 92])

        return crop_path, full_path, crop if crop.size > 0 else None
