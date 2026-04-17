"""
BarChart, LineChart, HourlyChart — oddiy chizilgan chartlar.
QPainter orqali to'g'ridan-to'g'ri chiziladi, tashqi kutubxona kerak emas.
"""

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import (QPainter, QColor, QFont, QPen, QBrush,
                          QPainterPath, QLinearGradient)

from app.ui.theme import C


# ── Asosiy yordamchi ──────────────────────────────────────────────────────

def _safe_max(values: list, default: int = 1) -> int:
    v = [x for x in values if isinstance(x, (int, float))]
    return max(v) if v else default


# ── BarChart ──────────────────────────────────────────────────────────────

class BarChart(QWidget):
    """
    Kunlik buzilishlar uchun vertikal bar chart.

    data: [{'date': '04/15', 'count': 12}, ...]
    """

    def __init__(self, data: list = None, parent=None):
        super().__init__(parent)
        self._data = data or []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(180)
        self.setStyleSheet(f"background: {C('bg_card')}; border-radius: 8px;")

    def set_data(self, data: list):
        self._data = data or []
        self.update()

    def paintEvent(self, event):
        if not self._data:
            self._draw_empty()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        pad_l, pad_r = 44, 16
        pad_t, pad_b = 20, 36

        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        counts = [d.get("count", 0) for d in self._data]
        max_v  = _safe_max(counts)

        # Y grid chiziqlari
        p.setPen(QPen(QColor(C("border")), 1, Qt.PenStyle.DashLine))
        for i in range(5):
            y = pad_t + int(chart_h * i / 4)
            p.drawLine(pad_l, y, W - pad_r, y)
            val = int(max_v * (4 - i) / 4)
            p.setPen(QColor(C("text_muted")))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(2, y + 4, str(val))
            p.setPen(QPen(QColor(C("border")), 1, Qt.PenStyle.DashLine))

        n = len(self._data)
        bar_w = max(4, chart_w // n - 3)

        for i, d in enumerate(self._data):
            cnt = d.get("count", 0)
            bh  = int(chart_h * cnt / max_v) if max_v else 0
            x   = pad_l + int(chart_w * i / n) + 1
            y   = pad_t + chart_h - bh

            # Gradient bar
            grad = QLinearGradient(x, y, x, y + bh)
            grad.setColorAt(0.0, QColor(C("accent")))
            grad.setColorAt(1.0, QColor(C("accent_dim")))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)

            path = QPainterPath()
            r    = min(3, bar_w // 2)
            path.addRoundedRect(x, y, bar_w, bh, r, r)
            p.drawPath(path)

            # X label (har 3 chi)
            if i % max(1, n // 10) == 0:
                p.setPen(QColor(C("text_muted")))
                p.setFont(QFont("Segoe UI", 7))
                lbl = d.get("date", "")
                p.drawText(x - 4, H - 4, lbl)

        p.end()

    def _draw_empty(self):
        p = QPainter(self)
        p.setPen(QColor(C("text_muted")))
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Ma'lumot yo'q")
        p.end()


# ── LineChart ─────────────────────────────────────────────────────────────

class LineChart(QWidget):
    """
    Haftalik trend line chart.
    data: [{'week': 'W15', 'count': 47}, ...]
    """

    def __init__(self, data: list = None, parent=None):
        super().__init__(parent)
        self._data = data or []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(160)
        self.setStyleSheet(f"background: {C('bg_card')}; border-radius: 8px;")

    def set_data(self, data: list):
        self._data = data or []
        self.update()

    def paintEvent(self, event):
        if not self._data:
            p = QPainter(self)
            p.setPen(QColor(C("text_muted")))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Ma'lumot yo'q")
            p.end()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        pad_l, pad_r = 44, 16
        pad_t, pad_b = 20, 36

        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        counts = [d.get("count", 0) for d in self._data]
        max_v  = _safe_max(counts)
        n      = len(self._data)

        # Grid
        p.setPen(QPen(QColor(C("border")), 1, Qt.PenStyle.DashLine))
        for i in range(5):
            y = pad_t + int(chart_h * i / 4)
            p.drawLine(pad_l, y, W - pad_r, y)
            val = int(max_v * (4 - i) / 4)
            p.setPen(QColor(C("text_muted")))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(2, y + 4, str(val))
            p.setPen(QPen(QColor(C("border")), 1, Qt.PenStyle.DashLine))

        # Nuqtalar koordinatalari
        pts = []
        for i, d in enumerate(self._data):
            cnt = d.get("count", 0)
            x   = pad_l + int(chart_w * i / max(n - 1, 1))
            y   = pad_t + chart_h - (int(chart_h * cnt / max_v) if max_v else 0)
            pts.append(QPoint(x, y))

        # Fill area (gradient)
        if len(pts) >= 2:
            path = QPainterPath()
            path.moveTo(pts[0].x(), pad_t + chart_h)
            path.lineTo(pts[0].x(), pts[0].y())
            for pt in pts[1:]:
                path.lineTo(pt.x(), pt.y())
            path.lineTo(pts[-1].x(), pad_t + chart_h)
            path.closeSubpath()

            grad = QLinearGradient(0, pad_t, 0, pad_t + chart_h)
            grad.setColorAt(0.0, QColor(C("accent") + "60"))
            grad.setColorAt(1.0, QColor(C("accent") + "00"))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)

        # Chiziq
        if len(pts) >= 2:
            p.setPen(QPen(QColor(C("accent")), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            line = QPainterPath()
            line.moveTo(pts[0].x(), pts[0].y())
            for pt in pts[1:]:
                line.lineTo(pt.x(), pt.y())
            p.drawPath(line)

        # Nuqtalar
        p.setBrush(QBrush(QColor(C("accent"))))
        p.setPen(QPen(QColor(C("bg_card")), 2))
        for pt in pts:
            p.drawEllipse(pt.x() - 4, pt.y() - 4, 8, 8)

        # X labellar
        p.setPen(QColor(C("text_muted")))
        p.setFont(QFont("Segoe UI", 8))
        for i, d in enumerate(self._data):
            if i % max(1, n // 8) == 0:
                x = pad_l + int(chart_w * i / max(n - 1, 1))
                p.drawText(x - 10, H - 4, d.get("week", ""))

        p.end()


# ── HourlyBarChart ────────────────────────────────────────────────────────

class HourlyBarChart(QWidget):
    """
    24 soatlik taqsimot chart.
    data: [{'hour': 0, 'count': 2}, ..., {'hour': 23, 'count': 0}]
    """

    def __init__(self, data: list = None, parent=None):
        super().__init__(parent)
        self._data = data or [{"hour": i, "count": 0} for i in range(24)]
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(150)
        self.setStyleSheet(f"background: {C('bg_card')}; border-radius: 8px;")

    def set_data(self, data: list):
        self._data = data or []
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        pad_l, pad_r = 36, 12
        pad_t, pad_b = 16, 28

        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        counts = [d.get("count", 0) for d in self._data]
        max_v  = _safe_max(counts)
        n      = len(self._data)

        if n == 0:
            p.setPen(QColor(C("text_muted")))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Ma'lumot yo'q")
            p.end()
            return

        bar_w = max(3, chart_w // n - 2)

        for i, d in enumerate(self._data):
            cnt = d.get("count", 0)
            bh  = int(chart_h * cnt / max_v) if max_v else 0
            x   = pad_l + int(chart_w * i / n)
            y   = pad_t + chart_h - bh

            hour = d.get("hour", i)
            # Ish vaqti (8–18) — boshqa rang
            if 8 <= hour < 18:
                color = C("accent")
                dim   = C("accent_dim")
            else:
                color = C("success")
                dim   = C("success_dim")

            grad = QLinearGradient(x, y, x, y + bh)
            grad.setColorAt(0.0, QColor(color))
            grad.setColorAt(1.0, QColor(dim))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)

            if bh > 0:
                path = QPainterPath()
                r    = min(2, bar_w // 2)
                path.addRoundedRect(x, y, bar_w, bh, r, r)
                p.drawPath(path)

            # Soat label (har 2 soatda)
            if hour % 2 == 0:
                p.setPen(QColor(C("text_muted")))
                p.setFont(QFont("Segoe UI", 7))
                p.drawText(x - 2, H - 4, f"{hour:02d}")

        p.end()
