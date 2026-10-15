from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

_log = logging.getLogger(__name__)


def write_jpeg(path: str | Path, image: np.ndarray, quality: int = 92) -> bool:
    """JPEG ni diskka yozadi; muvaffaqiyatli bo'lsa True.

    cv2.imwrite Windows'da lotin bo'lmagan (masalan kirill) yo'llarda jimgina
    False qaytaradi — shuning uchun imencode + oddiy fayl yozuvi ishlatiladi.
    Avval .tmp ga yoziladi, keyin almashtiriladi (yarim yozilgan rasm qolmasin)."""
    if image is None or getattr(image, "size", 0) == 0:
        return False
    try:
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if not ok:
            return False
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(buf.tobytes())
        os.replace(tmp, path)
        return True
    except Exception as exc:
        _log.error("Rasmni yozib bo'lmadi (%s): %s", path, exc)
        try:
            Path(str(path) + ".tmp").unlink(missing_ok=True)
        except OSError:
            pass
        return False


def violation_file_stem(timestamp: float, track_id: int, camera_id=None) -> str:
    """Takrorlanmas fayl nomi asosi: sana_vaqt_ms + kamera + track + qisqa uuid.

    Avval `crop_{soniya}_id{track}` edi — bir xil papkadagi turli kameralar
    (yoki qayta ishga tushgandan keyingi bir xil track ID) bir-birining
    dalil rasmini ustidan yozib yuborardi."""
    ts = float(timestamp)
    dt = datetime.fromtimestamp(ts)
    ms = int(round((ts - int(ts)) * 1000)) % 1000
    cam = f"cam{camera_id}" if camera_id not in (None, "") else "cam0"
    return f"{dt.strftime('%Y%m%d_%H%M%S')}_{ms:03d}_{cam}_id{track_id}_{uuid.uuid4().hex[:6]}"


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
        camera_id=None,
    ) -> tuple[str, str, np.ndarray | None]:
        if not enabled or len(box) != 4:
            return "", "", None

        x1, y1, x2, y2 = map(int, box)

        full = frame.copy()
        cv2.rectangle(full, (x1, y1), (x2, y2), (0, 0, 220), 3)

        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        pad_x = max(40, int(bw * 0.5))
        pad_y = max(60, int(bh * 0.6))
        cx1 = max(x1 - pad_x, 0)
        cy1 = max(y1 - pad_y, 0)
        cx2 = min(x2 + pad_x, frame.shape[1])
        cy2 = min(y2 + pad_y, frame.shape[0])
        crop = frame[cy1:cy2, cx1:cx2].copy()

        output_dir = Path(output_dir)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log.error("Buzilishlar papkasini yaratib bo'lmadi (%s): %s", output_dir, exc)
            return "", "", crop if crop.size > 0 else None

        # Soniyali timestamp ga joriy millisekund qo'shiladi (nom takrorlanmasin)
        now = time.time()
        ts = float(timestamp) + (now - int(now)) if int(timestamp) == int(now) else float(timestamp)
        stem = violation_file_stem(ts, track_id, camera_id)
        crop_path = str(output_dir / f"crop_{stem}.jpg")
        full_path = str(output_dir / f"full_{stem}.jpg")

        # Yozilmagan fayl yo'li DB ga tushmasin — muvaffaqiyatsiz bo'lsa bo'sh yo'l
        if crop.size == 0 or not write_jpeg(crop_path, crop):
            crop_path = ""
        if not write_jpeg(full_path, full):
            full_path = ""

        return crop_path, full_path, crop if crop.size > 0 else None
