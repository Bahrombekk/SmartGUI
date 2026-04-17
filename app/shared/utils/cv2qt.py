"""
OpenCV frame (numpy ndarray BGR) → PyQt6 QPixmap konverter.
"""

import numpy as np
import cv2
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt


def cv2_to_pixmap(frame: np.ndarray, width: int = 0, height: int = 0) -> QPixmap:
    """
    BGR numpy frame ni QPixmap ga aylantirish.

    Args:
        frame: OpenCV BGR frame (HxWx3)
        width:  Maqsad kengligi (0 = asl o'lcham)
        height: Maqsad balandligi (0 = asl o'lcham)

    Returns:
        QPixmap
    """
    if frame is None:
        return QPixmap()

    # BGR → RGB
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w

    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg)

    if width > 0 and height > 0:
        pixmap = pixmap.scaled(
            width, height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
    elif width > 0:
        pixmap = pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    elif height > 0:
        pixmap = pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)

    return pixmap


def frame_to_thumbnail(frame: np.ndarray, size: int = 120) -> QPixmap:
    """
    Kvadrat thumbnail yasash (center crop + resize).

    Args:
        frame: BGR frame
        size:  Thumbnail o'lchami (piksel)

    Returns:
        QPixmap (size x size)
    """
    if frame is None:
        return QPixmap()

    h, w = frame.shape[:2]
    # Markaz bo'yicha kvadrat kesish
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    cropped = frame[y0:y0 + side, x0:x0 + side]
    resized = cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)

    return cv2_to_pixmap(resized)
