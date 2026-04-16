"""
VideoLabel — OpenCV frame larini ko'rsatuvchi QLabel.
Aspect ratio saqlaydi, "Ulanmoqda..." placeholder ko'rsatadi.
"""

import numpy as np
from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFont

from app.utils.theme import C


class VideoLabel(QLabel):
    """Live video feed uchun QLabel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(480, 270)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {C('bg_card')};
                border: 2px solid {C('border')};
                border-radius: 8px;
                color: {C('text_muted')};
            }}
        """)
        self._has_frame = False
        self._placeholder_text = "Kamera kutilmoqda..."
        self.setText(self._placeholder_text)

    def set_frame(self, frame: np.ndarray):
        """BGR numpy frame ni ko'rsatish."""
        if frame is None:
            return

        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(
                rgb.data, w, h, ch * w,
                QImage.Format.Format_RGB888
            )
            pixmap = QPixmap.fromImage(qimg)
            scaled = pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)
            self._has_frame = True
        except Exception as e:
            print(f"[VideoLabel] Frame xatosi: {e}")

    def show_placeholder(self, text: str = ""):
        """Placeholder matnini ko'rsatish (kamera yo'q holda)."""
        self._has_frame = False
        self.clear()
        self._placeholder_text = text or "Kamera kutilmoqda..."
        self.setText(self._placeholder_text)

    def show_connecting(self):
        self.show_placeholder("Kameraga ulanmoqda...")

    def show_error(self, msg: str = ""):
        self.show_placeholder(msg or "Ulanishda xatolik")
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {C('bg_card')};
                border: 2px solid {C('danger')};
                border-radius: 8px;
                color: {C('danger')};
            }}
        """)

    def reset_style(self):
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {C('bg_card')};
                border: 2px solid {C('border')};
                border-radius: 8px;
                color: {C('text_muted')};
            }}
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Yenidan render (pixmap bo'lsa)
        if self._has_frame and self.pixmap() and not self.pixmap().isNull():
            scaled = self.pixmap().scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)
