"""
VideoLabel — OpenCV frame larini ko'rsatuvchi QLabel.
Aspect ratio saqlaydi, animatsiyali "Ulanmoqda..." placeholder ko'rsatadi.
"""

import numpy as np
from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QPen

from app.ui.theme import C


class VideoLabel(QLabel):
    """Live video feed uchun QLabel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(320, 200)
        self._has_frame = False
        self._mode = "connecting"   # connecting | error | live
        self._anim_step = 0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(500)
        self._anim_timer.timeout.connect(self._tick_anim)

        self._apply_base_style()
        self._anim_timer.start()

    # ── Stil ─────────────────────────────────────────────────────────────

    def _apply_base_style(self):
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {C('bg_card')};
                border: 2px solid {C('border')};
                border-radius: 0px;
                color: {C('text_muted')};
                font-size: 13px;
            }}
        """)

    def _apply_error_style(self):
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {C('bg_card')};
                border: 2px solid {C('danger')};
                border-radius: 0px;
                color: {C('danger')};
                font-size: 13px;
            }}
        """)

    # ── Animatsiya ────────────────────────────────────────────────────────

    def _tick_anim(self):
        if self._has_frame:
            return
        self._anim_step = (self._anim_step + 1) % 4
        dots = "●" * self._anim_step + "○" * (3 - self._anim_step)

        if self._mode == "connecting":
            self.setText(f"📡  Ulanmoqda...  {dots}")
        elif self._mode == "loading":
            self.setText(f"⚙  Model yuklanmoqda...  {dots}")

    # ── Tashqi API ────────────────────────────────────────────────────────

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
            if not self._has_frame:
                self._has_frame = True
                self._mode = "live"
                self._apply_base_style()
        except Exception as e:
            print(f"[VideoLabel] Frame xatosi: {e}")

    def show_placeholder(self, text: str = ""):
        self._has_frame = False
        self._mode = "connecting"
        self.clear()
        self._apply_base_style()
        self.setText(text or "📡  Ulanmoqda...")
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def show_connecting(self):
        self._mode = "connecting"
        self.show_placeholder()

    def show_loading(self):
        self._has_frame = False
        self._mode = "loading"
        self.clear()
        self._apply_base_style()
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def show_error(self, msg: str = ""):
        self._has_frame = False
        self._mode = "error"
        self._anim_timer.stop()
        self.clear()
        self._apply_error_style()
        self.setText(f"⚠  {msg}" if msg else "⚠  Ulanishda xatolik")

    def reset_style(self):
        self._apply_base_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._has_frame and self.pixmap() and not self.pixmap().isNull():
            scaled = self.pixmap().scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)
