"""
VideoLabel — OpenCV frame larini ko'rsatuvchi QLabel.
Aspect ratio saqlaydi; ulanish, yuklash, xatolik, offline holatlari.

BUG FIX: QImage(rgb.data, ...) — PyQt6 da numpy memoryview egnida qoladi
         va qora ekran berishi mumkin. rgb.tobytes() bilan to'g'irlandi.
"""

import numpy as np
from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QPen, QBrush

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
        self.setMinimumSize(240, 160)

        self._has_frame  = False
        self._mode       = "connecting"   # connecting | loading | offline | live
        self._anim_step  = 0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(500)
        self._anim_timer.timeout.connect(self._tick_anim)

        self._apply_base_style()
        self._anim_timer.start()

    # ── Stil ─────────────────────────────────────────────────────────────

    def _apply_base_style(self):
        self.setStyleSheet(
            "background-color: #0a0e14; border: none;"
            f"color: {C('text_muted')}; font-size: 12px;"
        )

    # ── Animatsiya ────────────────────────────────────────────────────────

    def _tick_anim(self):
        if self._has_frame:
            return
        self._anim_step = (self._anim_step + 1) % 4
        dots = "●" * self._anim_step + "○" * (3 - self._anim_step)
        if self._mode == "connecting":
            self.setText(f"Ulanmoqda  {dots}")
        elif self._mode == "loading":
            self.setText(f"Model yuklanmoqda  {dots}")

    # ── Offline/xatolik holati — custom paint ─────────────────────────────

    def paintEvent(self, event):
        if self._mode == "offline" and not self._has_frame:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            p.fillRect(0, 0, w, h, QColor("#0a0e14"))

            cx, cy = w // 2, h // 2

            # Kamera belgisi
            icon_r = max(min(w, h) // 7, 20)
            rw, rh = icon_r * 2, int(icon_r * 1.4)
            rx, ry = cx - rw // 2, cy - 20 - rh // 2

            pen = QPen(QColor(C('text_muted')), 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rx, ry, rw, rh, 4, 4)

            lens_r = max(icon_r // 2, 8)
            p.drawEllipse(cx - lens_r, cy - 20 - lens_r, lens_r * 2, lens_r * 2)
            p.drawRect(cx + rw // 2 - 6, ry - 6, 12, 6)

            # Diagonal chiziq
            p.drawLine(rx - 4, ry - 4, rx + rw + 4, ry + rh + 4)

            # "Camera is offline" matni
            font = QFont("Segoe UI", 11)
            p.setFont(font)
            p.setPen(QPen(QColor(C('text_muted'))))
            p.drawText(QRect(0, cy + 16, w, 28),
                       Qt.AlignmentFlag.AlignCenter, "Camera is offline")
            p.end()
        else:
            super().paintEvent(event)

    # ── Frame ko'rsatish ─────────────────────────────────────────────────

    def set_frame(self, frame: np.ndarray):
        """BGR numpy frame → QLabel pixmap.

        MUHIM: rgb.tobytes() ishlatiladi — rgb.data PyQt6 da qora ekran berishi
        mumkin chunki numpy array GC dan tushib ketishi bilan data pointer bekor bo'ladi.
        """
        if frame is None or frame.size == 0:
            return
        try:
            import cv2 as _cv2
            rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w

            # tobytes() — ko'chirilgan doimiy bufer, PyQt6 da xavfsiz
            qimg = QImage(
                rgb.tobytes(), w, h,
                bytes_per_line,
                QImage.Format.Format_RGB888
            )
            pixmap = QPixmap.fromImage(qimg)
            scaled = pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.setPixmap(scaled)

            if not self._has_frame:
                self._has_frame = True
                self._mode = "live"
                self._anim_timer.stop()
                self._apply_base_style()

        except Exception as e:
            print(f"[VideoLabel] Frame xatosi: {e}")

    # ── Holat metodlari ───────────────────────────────────────────────────

    def show_connecting(self):
        self._has_frame = False
        self._mode = "connecting"
        self.clear()
        self._apply_base_style()
        self.setText("Ulanmoqda...")
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def show_loading(self):
        self._has_frame = False
        self._mode = "loading"
        self.clear()
        self._apply_base_style()
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def show_error(self, msg: str = ""):
        self._has_frame = False
        self._mode = "offline"
        self._anim_timer.stop()
        self.clear()
        self._apply_base_style()
        self.update()  # paintEvent orqali kamera belgisi chiziladi

    def show_placeholder(self, text: str = ""):
        self.show_connecting()

    def reset_style(self):
        self._apply_base_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._mode == "offline":
            self.update()
        elif self._has_frame and self.pixmap() and not self.pixmap().isNull():
            scaled = self.pixmap().scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self.setPixmap(scaled)
