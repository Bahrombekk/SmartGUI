"""
VideoLabel — OpenCV frame larini ko'rsatuvchi QLabel.
Aspect ratio saqlaydi; ulanish, yuklash, xatolik, offline holatlari.

BUG FIX: QImage(rgb.data, ...) — PyQt6 da numpy memoryview egnida qoladi
         va qora ekran berishi mumkin. rgb.tobytes() bilan to'g'irlandi.
"""

import numpy as np
from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QPointF
from PyQt6.QtGui import (QPixmap, QImage, QPainter, QColor, QFont, QPen, QBrush,
                          QRadialGradient, QPolygonF)

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
        self._qimage: QImage | None = None

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
        if self._has_frame and self._qimage is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            iw, ih = self._qimage.width(), self._qimage.height()
            sw, sh = self.width(), self.height()
            if iw > 0 and ih > 0 and sw > 0 and sh > 0:
                ratio = min(sw / iw, sh / ih)
                dw, dh = int(iw * ratio), int(ih * ratio)
                dx, dy = (sw - dw) // 2, (sh - dh) // 2
                p.fillRect(0, 0, sw, sh, QColor("#0a0e14"))
                p.drawImage(QRect(dx, dy, dw, dh), self._qimage)
            p.end()
            return
        if self._mode == "offline" and not self._has_frame:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            cx, cy_mid = w / 2, h / 2

            # Fon
            p.fillRect(0, 0, w, h, QColor("#0a0e14"))
            grad = QRadialGradient(cx, cy_mid, min(w, h) * 0.45)
            grad.setColorAt(0.0, QColor(22, 44, 60, 55))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(0, 0, w, h, QBrush(grad))

            sc = min(w, h) / 260.0
            u  = 30.0 * sc
            sw = max(1.5, 2.0 * sc)  # stroke width

            icx = cx
            icy = cy_mid - u * 0.35

            # ── Kamera body ──
            bw, bh = u * 3.6, u * 2.0
            body = QRectF(icx - bw/2, icy - bh/2, bw, bh)
            p.setPen(QPen(QColor("#2d4d63"), sw))
            p.setBrush(QBrush(QColor(12, 24, 36, 160)))
            p.drawRoundedRect(body, u * 0.38, u * 0.38)

            # ── Viewfinder bump (tepada) ──
            vfw, vfh = u * 0.9, u * 0.5
            vf = QRectF(icx - vfw/2, icy - bh/2 - vfh + 2, vfw, vfh)
            p.setBrush(QBrush(QColor(12, 24, 36, 160)))
            p.drawRoundedRect(vf, u * 0.15, u * 0.15)

            # ── Linza ──
            lo, lm, li = u * 0.78, u * 0.53, u * 0.24
            lx, ly = icx - u * 0.22, icy

            p.setPen(QPen(QColor("#2d4d63"), sw))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(lx - lo, ly - lo, lo * 2, lo * 2))

            p.setPen(QPen(QColor("#1e3548"), max(1.0, sw - 0.5)))
            p.setBrush(QBrush(QColor(8, 18, 30, 220)))
            p.drawEllipse(QRectF(lx - lm, ly - lm, lm * 2, lm * 2))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(24, 46, 66, 180)))
            p.drawEllipse(QRectF(lx - li, ly - li, li * 2, li * 2))

            # ── Yozuv nuqtasi (o'ng yuqori, qizil — offline) ──
            dr = u * 0.16
            dx = icx + bw/2 - u * 0.5
            dy = icy - bh/2 + u * 0.4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(160, 40, 40, 200)))
            p.drawEllipse(QRectF(dx - dr, dy - dr, dr * 2, dr * 2))

            # ── Qizil X badge (pastki o'ng burchak) ──
            badge_r = u * 0.62
            bx_ = icx + bw/2 - u * 0.1
            by_ = icy + bh/2 - u * 0.1

            p.setPen(QPen(QColor("#0a0e14"), max(2.0, sw + 0.5)))
            p.setBrush(QBrush(QColor(170, 35, 35, 235)))
            p.drawEllipse(QRectF(bx_ - badge_r, by_ - badge_r, badge_r * 2, badge_r * 2))

            xp = QPen(QColor("#ffffff"), max(1.5, sw))
            xp.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(xp)
            xo = badge_r * 0.42
            p.drawLine(QPointF(bx_ - xo, by_ - xo), QPointF(bx_ + xo, by_ + xo))
            p.drawLine(QPointF(bx_ + xo, by_ - xo), QPointF(bx_ - xo, by_ + xo))

            # ── Matn ──
            ty = int(icy + bh / 2 + u * 0.85)

            f1 = QFont("Segoe UI", max(9, int(11.5 * sc)), QFont.Weight.DemiBold)
            p.setFont(f1)
            p.setPen(QColor("#4e6e84"))
            p.drawText(QRect(0, ty, w, int(u) + 10),
                       Qt.AlignmentFlag.AlignCenter, "Kamera offline")

            f2 = QFont("Segoe UI", max(7, int(9 * sc)))
            p.setFont(f2)
            p.setPen(QColor("#2b3e4e"))
            p.drawText(QRect(0, ty + int(u * 0.88), w, int(u * 0.85) + 8),
                       Qt.AlignmentFlag.AlignCenter, "Ulanish yo'q")

            p.end()
        elif self._mode == "live" and not self._has_frame:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            cx, cy = w / 2, h / 2

            p.fillRect(0, 0, w, h, QColor("#06101a"))
            grad = QRadialGradient(cx, cy, min(w, h) * 0.55)
            grad.setColorAt(0.0, QColor(30, 95, 168, 70))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(0, 0, w, h, QBrush(grad))

            r = max(28, min(w, h) * 0.14)
            p.setPen(QPen(QColor(30, 95, 168, 160), 2))
            p.setBrush(QBrush(QColor(10, 28, 48, 210)))
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

            tri = QPolygonF([
                QPointF(cx - r * 0.22, cy - r * 0.40),
                QPointF(cx - r * 0.22, cy + r * 0.40),
                QPointF(cx + r * 0.46, cy),
            ])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#e0f2fe")))
            p.drawPolygon(tri)

            p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            p.setPen(QColor("#7fb3df"))
            p.drawText(QRect(0, int(cy + r + 14), w, 28), Qt.AlignmentFlag.AlignCenter, self.text() or "Preview available")
            p.end()
        else:
            super().paintEvent(event)

    # ── Frame ko'rsatish ─────────────────────────────────────────────────

    def set_frame(self, frame):
        """frame: QImage (worker thread'dan) yoki np.ndarray (legacy)."""
        if frame is None:
            return
        try:
            if isinstance(frame, QImage):
                self._qimage = frame
            else:
                if frame.size == 0:
                    return
                import cv2 as _cv2
                rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                self._qimage = QImage(rgb.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)

            if not self._has_frame:
                self._has_frame = True
                self._mode = "live"
                self._anim_timer.stop()
                self._apply_base_style()

            self.update()

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

    def show_idle(self, text: str = "Preview"):
        """Kamera online, lekin preview hali yoqilmagan holat."""
        self._has_frame = False
        self._mode = "live"
        self._anim_timer.stop()
        self.clear()
        self._apply_base_style()
        self.setText(text)
        self.update()

    def show_placeholder(self, text: str = ""):
        self.show_connecting()

    def reset_style(self):
        self._apply_base_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._mode == "offline" or self._has_frame:
            self.update()
