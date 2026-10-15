"""
FeedView — Figma kamera kadri: rasm "cover" (bo'sh joysiz to'ldirish),
yumaloq burchak bilan kesiladi; holatlar: ulanmoqda / signal yo'q.

Worker thread'dan QImage (yoki legacy np.ndarray) qabul qiladi.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QLinearGradient, QBrush, QPixmap
from PyQt6.QtWidgets import QWidget

from app.ui import fz

_log = logging.getLogger(__name__)


class FeedView(QWidget):
    frame_size_changed = pyqtSignal()
    live_changed = pyqtSignal(bool)        # kadr ko'rinadimi (zona overlay shunga bog'liq)

    def __init__(self, radius: float = 10, bg: str = fz.CARD_DEEP, gradient_h: int = 0,
                 offline_text: str = "Signal yo‘q · qayta ulanmoqda", connecting_text: str = "Ulanmoqda",
                 parent=None):
        super().__init__(parent)
        self._r = radius
        self._bg = QColor(bg)
        self._img: QImage | None = None
        self._mode = "connecting"           # connecting | live | offline
        self._grad_h = gradient_h
        self._offline_text = offline_text
        self._connecting_text = connecting_text
        self._dots = 0
        self._cover = True
        self._src_size = (16, 9)            # oxirgi kadr o'lchami (zona mapping uchun)
        self._reserve_bottom = 0            # pastdagi overlay (nom qatori) egallagan joy
        self._was_live = False
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._anim = QTimer(self)
        self._anim.setInterval(450)
        self._anim.timeout.connect(self._tick)
        self._anim.start()

    # ── holatlar ──
    def _tick(self):
        if self._mode != "connecting" or self._img is not None or not self.isVisible():
            if self._mode != "connecting":
                self._anim.stop()
            return
        self._dots = (self._dots + 1) % 4
        self.update()

    def set_frame(self, frame):
        if frame is None:
            return
        try:
            if isinstance(frame, QImage):
                img = frame
            else:
                if getattr(frame, "size", 0) == 0:
                    return
                import cv2
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                img = QImage(rgb.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888).copy()
            self._img = img
            size = (img.width(), img.height())
            if size != self._src_size:
                self._src_size = size
                self.frame_size_changed.emit()
            if self._mode != "live":
                self._mode = "live"
                self._anim.stop()
            self._notify_live()
            self.update()
        except Exception as e:  # pragma: no cover
            _log.warning("Kadr xatosi: %s", e)

    def has_frame(self) -> bool:
        return self._img is not None

    def is_live(self) -> bool:
        """Haqiqiy kadr ko'rsatilyaptimi (oflayn/ulanmoqda — yo'q)."""
        return self._img is not None and self._mode != "offline"

    def _notify_live(self):
        live = self.is_live()
        if live != self._was_live:
            self._was_live = live
            self.live_changed.emit(live)

    def image(self) -> QImage | None:
        return self._img

    def set_reserve_bottom(self, px: int):
        """Holat matni/ikonka pastki overlay (masalan kamera nomi) bilan ustma-ust tushmasin."""
        self._reserve_bottom = max(0, int(px))
        self.update()

    def _fit_text(self, p: QPainter, text: str, width: float) -> str:
        """Matn sig'masa — qisqa variant ("·" dan oldingi qism), so'ng elide."""
        fm = p.fontMetrics()
        if fm.horizontalAdvance(text) <= width:
            return text
        short = text.split("·")[0].strip()
        if short and fm.horizontalAdvance(short) <= width:
            return short
        return fm.elidedText(short or text, Qt.TextElideMode.ElideRight, int(width))

    def map_norm(self, nx: float, ny: float) -> QPointF:
        """Kadrga nisbatan normallashgan (0–1) nuqtani widget koordinatasiga
        o'tkazadi — "cover" kesish hisobga olinadi (zona overlay uchun)."""
        w, h = float(self.width()), float(self.height())
        iw, ih = self._src_size
        if iw <= 0 or ih <= 0 or w <= 0 or h <= 0:
            return QPointF(nx * w, ny * h)
        s = max(w / iw, h / ih) if self._cover else min(w / iw, h / ih)
        dw, dh = iw * s, ih * s
        return QPointF((w - dw) / 2 + nx * dw, (h - dh) / 2 + ny * dh)

    def show_connecting(self):
        self._mode = "connecting"
        if not self._anim.isActive():
            self._anim.start()
        self._notify_live()
        self.update()

    def show_offline(self, text: str | None = None):
        self._mode = "offline"
        self._img = None
        if text is not None:
            self._offline_text = text
        self._anim.stop()
        self._notify_live()
        self.update()

    def clear(self):
        self._img = None
        self.show_connecting()

    # ── chizish ──
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, self._r, self._r)
        p.setClipPath(clip)
        p.fillRect(r, self._bg)
        img = self._img
        if img is not None and self._mode != "offline":
            iw, ih = img.width(), img.height()
            if iw > 0 and ih > 0:
                if self._cover:
                    s = max(r.width() / iw, r.height() / ih)
                    sw, sh = r.width() / s, r.height() / s
                    src = QRectF((iw - sw) / 2, (ih - sh) / 2, sw, sh)
                    p.drawImage(r, img, src)
                else:
                    s = min(r.width() / iw, r.height() / ih)
                    dw, dh = iw * s, ih * s
                    p.drawImage(QRectF((r.width() - dw) / 2, (r.height() - dh) / 2, dw, dh), img)
            if self._grad_h:
                g = QLinearGradient(0, r.height() - self._grad_h, 0, r.height())
                g.setColorAt(0, QColor(8, 13, 26, 0))
                g.setColorAt(1, QColor(8, 13, 26, int(0.85 * 255)))
                p.fillRect(QRectF(0, r.height() - self._grad_h, r.width(), self._grad_h), QBrush(g))
        elif self._mode == "offline":
            if not self._offline_text:
                p.end()
                return
            avail_h = r.height() - self._reserve_bottom
            cx, cy = r.width() / 2, avail_h / 2
            p.setFont(fz.qfont(12, 400))
            p.setPen(QColor(fz.MUTED))
            text = self._fit_text(p, self._offline_text, r.width() - 16)
            if avail_h >= 52:
                icon = fz.svg_pixmap("video_off", 18, 18)
                p.drawPixmap(int(cx - 9), int(cy - 22), icon)
                p.drawText(QRectF(8, cy + 3, r.width() - 16, 16), Qt.AlignmentFlag.AlignCenter, text)
            else:
                p.drawText(QRectF(8, cy - 8, r.width() - 16, 16), Qt.AlignmentFlag.AlignCenter, text)
        elif self._connecting_text:
            p.setFont(fz.qfont(12, 400))
            p.setPen(QColor(fz.MUTED))
            dots = "•" * self._dots + " " * (3 - self._dots)
            text = self._fit_text(p, f"{self._connecting_text} {dots}", r.width() - 16)
            p.drawText(QRectF(8, 0, r.width() - 16, r.height() - self._reserve_bottom),
                       Qt.AlignmentFlag.AlignCenter, text)
        p.end()
