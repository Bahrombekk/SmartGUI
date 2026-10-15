"""
Analitika — Figma "SafeZone — Analitika" (16:137) aniq nusxasi.

Sarlavha + davr (Hafta/Oy/Chorak/Yil) + bo‘lim filtri + Hisobot (PDF) ·
KPI qatori (h84): davrdagi buzilishlar / o‘rtacha muvofiqlik / takror buzganlar /
o‘rtacha javob vaqti · "Kunlik buzilishlar" maydon grafigi (897x389) +
"Eng ko‘p buzilish" reytingi (499) · "Hafta kuni × soat" heatmap (789x249) +
"Bo‘limlar bo‘yicha muvofiqlik" (607) va insight qatori.

Barcha agregatlar fon oqimida bitta SQL to‘plami bilan hisoblanadi.
API: AnalyticsPage(db, config_manager), go_cameras, refresh().
"""
from __future__ import annotations

import math
import os
import threading
from datetime import date, datetime, timedelta

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer, QMarginsF
from PyQt6.QtGui import (QColor, QPainter, QPainterPath, QPen, QLinearGradient, QBrush,
                         QPageLayout, QPageSize, QPdfWriter)
from PyQt6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QFileDialog, QScrollArea

from app.ui import fz

PERIODS = [("Hafta", 7, "7 kunda", "o‘tgan haftaga"), ("Oy", 30, "30 kunda", "o‘tgan oyga"),
           ("Chorak", 90, "90 kunda", "o‘tgan chorakka"), ("Yil", 365, "365 kunda", "o‘tgan yilga")]
WEEKDAYS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
HEAT_ALPHA = [0.0, 0.2, 0.4, 0.68, 1.0]
HEAT_ZERO = "#121f33"


def _ts(d: date, end: bool = False) -> int:
    return int(datetime.combine(d, datetime.max.time() if end else datetime.min.time()).timestamp())


def _mix(c1: str, c2: str, t: float) -> QColor:
    a, b = QColor(c1), QColor(c2)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def _nice_max(v: float) -> tuple[int, int]:
    if v <= 4:
        return 4, 1
    raw = v / 4
    mag = 10 ** int(math.floor(math.log10(raw)))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            step = int(math.ceil(step))
            return step * 4, step
    return int(v), max(1, int(v / 4))


# ════════════════════════════════════════════════════════════════════════════
#  KPI kartasi (343x84)
# ════════════════════════════════════════════════════════════════════════════

class _KPI(QFrame):
    def __init__(self, title: str, icon: str, icon_bg: str, parent=None):
        super().__init__(parent)
        self.setObjectName("fzKPI2")
        self.setFixedHeight(84)
        self._danger = False
        self._style()
        self.box = fz.IconBox(icon, icon_bg, parent=self)
        self.box.move(17, 15)
        self.title = fz.label(title, 12.5, 400, fz.TEXT2, parent=self)
        self.title.setGeometry(49, 19, 260, 15)
        self.value = fz.label("—", 31, 500, fz.TEXT, mono=True, tracking=-1, parent=self)
        self.value.setFixedHeight(38)
        self.value.move(17, 44)
        self.unit = fz.label("", 14, 400, fz.MUTED, mono=True, parent=self)
        self.pill = fz.Pill("", fz.GREEN_BG, fz.GREEN, px=11, weight=500, mono=True, h=20, pad=7, radius=6, parent=self)
        self.pill.hide()

    def _style(self):
        bg, bd = (fz.RED_CARD, fz.RED_BORDER) if self._danger else (fz.CARD, fz.BORDER)
        self.setStyleSheet(f"QFrame#fzKPI2 {{ background:{bg}; border:1px solid {bd}; border-radius:10px; }}")

    def set_title(self, t: str):
        self.title.setText(t)

    def set_data(self, value: str, unit: str = "", pill: str = "", good: bool | None = None, danger: bool = False):
        self._danger = danger
        self._style()
        fz.restyle(self.value, 31, 500, fz.RED if danger else fz.TEXT, mono=True, tracking=-1)
        self.value.setText(value)
        self.value.adjustSize()
        self.unit.setText(unit)
        self.unit.adjustSize()
        x = 17 + self.value.width()
        if unit:
            self.unit.move(x + 1, 60)
            x = self.unit.x() + self.unit.width()
        if pill:
            bg, fg = ((fz.GREEN_BG, fz.GREEN) if good else (fz.RED_BG, fz.RED)) if good is not None else (fz.BORDER, fz.TEXT2)
            self.pill.set_colors(bg, fg, None, None, px=11, weight=500, mono=True)
            self.pill.set_text(pill)
            self.pill.adjustSize()
            self.pill.move(x + (9 if unit else 11), 61)
            self.pill.show()
        else:
            self.pill.hide()


# ════════════════════════════════════════════════════════════════════════════
#  Kunlik grafik
# ════════════════════════════════════════════════════════════════════════════

class _TrendChart(QWidget):
    """Karta ichidagi chizma (karta koordinatalarida): plot x45..W-25, y59..H-42."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._days: list[date] = []
        self._vals: list[int] = []
        self._hover = -1

    def set_data(self, days: list[date], vals: list[int]):
        self._days, self._vals = days, vals
        self._hover = -1
        self.update()

    def _plot(self):
        W, H = self.width(), self.height()
        return 45.0, 59.0, W - 25.0, H - 42.0

    def mouseMoveEvent(self, e):
        if not self._vals:
            return
        x0, y0, x1, y1 = self._plot()
        n = len(self._vals)
        i = round((e.position().x() - x0) / max(1, (x1 - x0)) * (n - 1))
        i = max(0, min(n - 1, i)) if x0 - 10 <= e.position().x() <= x1 + 10 else -1
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, y0, x1, y1 = self._plot()
        vals = self._vals
        n = len(vals)
        top, step = _nice_max(max(vals + [1]))
        p.setFont(fz.qfont(10.5, 400, mono=True))
        for k in range(5):
            y = y1 - (y1 - y0) * k / 4
            p.fillRect(QRectF(x0, y, x1 - x0, 1), QColor(26, 40, 66, 128))
            p.setPen(QColor(fz.MUTED))
            p.drawText(QRectF(0, y - 7, 31, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(step * k))
        if n < 2:
            p.setPen(QColor(fz.MUTED))
            p.setFont(fz.qfont(12, 400))
            p.drawText(QRectF(x0, y0, x1 - x0, y1 - y0), Qt.AlignmentFlag.AlignCenter, "Ma’lumot yo‘q")
            p.end()
            return

        def pt(i, v):
            return QPointF(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * v / top)

        pts = [pt(i, v) for i, v in enumerate(vals)]
        area = QPainterPath(QPointF(pts[0].x(), y1))
        for q in pts:
            area.lineTo(q)
        area.lineTo(QPointF(pts[-1].x(), y1))
        area.closeSubpath()
        g = QLinearGradient(0, y0, 0, y1)
        c0 = QColor(fz.RED)
        c0.setAlphaF(0.30)
        c1 = QColor(fz.RED)
        c1.setAlphaF(0.02)
        g.setColorAt(0, c0)
        g.setColorAt(1, c1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawPath(area)
        line = QPainterPath(pts[0])
        for q in pts[1:]:
            line.lineTo(q)
        pen = QPen(QColor(fz.RED), 1.8)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)
        avg = sum(vals) / n
        ay = y1 - (y1 - y0) * avg / top
        dpen = QPen(QColor(126, 142, 168, 200), 1, Qt.PenStyle.DashLine)
        dpen.setDashPattern([4, 4])
        p.setPen(dpen)
        p.drawLine(QPointF(x0, ay), QPointF(x1, ay))
        # x yorliqlar (7 ta)
        p.setFont(fz.qfont(10.5, 400, mono=True))
        p.setPen(QColor(fz.MUTED))
        step = max(1, math.ceil((n - 1) / 6))              # Figma: har 5 kunda + oxirgi kun
        idxs = list(range(0, n - 1, step))
        if idxs and (n - 1 - idxs[-1]) < step * 0.6 and len(idxs) > 1:
            idxs.pop()
        idxs.append(n - 1)
        for i in idxs:
            x = pts[i].x()
            lab = self._days[i].strftime("%d.%m")
            tw = 32
            rx = max(x - tw / 2, x0 - 15) if i == 0 else (min(x - tw / 2, x1 - tw + 15) if i == n - 1 else x - tw / 2)
            p.drawText(QRectF(rx, y1 + 9, tw, 13), Qt.AlignmentFlag.AlignCenter, lab)
        # cho'qqi yoki hover nuqta + tooltip
        i = self._hover if self._hover >= 0 else max(range(n), key=lambda k: vals[k])
        if vals[i] > 0 or self._hover >= 0:
            q = pts[i]
            p.setPen(QPen(QColor(fz.CARD), 2))
            p.setBrush(QColor(fz.RED))
            p.drawEllipse(q, 4, 4)
            txt = f"{self._days[i]:%d.%m} · {vals[i]}"
            p.setFont(fz.qfont(10.5, 500, mono=True))
            tw = p.fontMetrics().horizontalAdvance(txt) + 16
            tip = QRectF(q.x() - tw / 2, q.y() - 24 - 4, tw, 20)
            tip.moveLeft(max(x0, min(x1 - tw, tip.left())))
            tip.moveTop(max(y0 - 2, tip.top()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(fz.TEXT))
            p.drawRoundedRect(tip, 5, 5)
            p.setPen(QColor(fz.CARD))
            p.drawText(tip, Qt.AlignmentFlag.AlignCenter, txt)
        p.end()


class _Legend(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._avg = "O‘rtacha (0)"
        self.setFixedHeight(15)

    def set_avg(self, t: str):
        self._avg = t
        w = 12 + 6 + fz.text_w("Buzilishlar", 12, 400) + 16 + 12 + 6 + fz.text_w(t, 12, 400)
        self.setFixedWidth(int(math.ceil(w)) + 2)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(fz.qfont(12, 400))
        x = 0.0
        p.fillRect(QRectF(x, 6.5, 12, 2), QColor(fz.RED))
        x += 18
        p.setPen(QColor(fz.TEXT2))
        w = fz.text_w("Buzilishlar", 12, 400)
        p.drawText(QRectF(x, 0, w + 2, 15), Qt.AlignmentFlag.AlignVCenter, "Buzilishlar")
        x += w + 16
        pen = QPen(QColor(fz.MUTED), 2, Qt.PenStyle.DashLine)
        pen.setDashPattern([2, 1.5])
        p.setPen(pen)
        p.drawLine(QPointF(x, 7.5), QPointF(x + 12, 7.5))
        x += 18
        p.setPen(QColor(fz.TEXT2))
        p.drawText(QRectF(x, 0, self.width() - x, 15), Qt.AlignmentFlag.AlignVCenter, self._avg)
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  Reyting, heatmap, bo'limlar
# ════════════════════════════════════════════════════════════════════════════

class _Ranking(QWidget):
    """Karta ichi: sarlavha ostida qatorlar (pitch 33) — # | nom | trek 90x5 | qiymat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[str, int]] = []
        self._other = (0, 0)
        self._total = 0

    def set_data(self, rows, other_n, other_sum, total):
        self._rows, self._other, self._total = rows, (other_n, other_sum), total
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        mx = max([v for _, v in self._rows] + [1])
        y = 0.0
        p.fillRect(QRectF(17, y, W - 34, 1), QColor(fz.BORDER))
        for i, (name, v) in enumerate(self._rows):
            top = y + 1
            p.setFont(fz.qfont(12, 400, mono=True))
            p.setPen(QColor(fz.MUTED))
            p.drawText(QRectF(17, top + 9, 20, 15), Qt.AlignmentFlag.AlignVCenter, str(i + 1))
            p.setFont(fz.qfont(13, 500))
            p.setPen(QColor(fz.TEXT))
            fm = p.fontMetrics()
            tx = W - 151
            p.drawText(QRectF(47, top + 8, tx - 47 - 10, 16), Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(name, Qt.TextElideMode.ElideRight, int(tx - 57)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(fz.BORDER))
            p.drawRoundedRect(QRectF(tx, top + 13.5, 90, 5), 2.5, 2.5)
            p.setBrush(QColor(fz.RED))
            p.drawRoundedRect(QRectF(tx, top + 13.5, max(5.0, 90 * v / mx), 5), 2.5, 2.5)
            p.setFont(fz.qfont(12.5, 500, mono=True))
            p.setPen(QColor(fz.TEXT))
            p.drawText(QRectF(W - 17 - 60, top + 8, 60, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(v))
            y += 33
            p.fillRect(QRectF(17, y, W - 34, 1), QColor(fz.BORDER))
        if self._other[0] > 0:
            p.setFont(fz.qfont(12.5, 400))
            p.setPen(QColor(fz.MUTED))
            p.drawText(QRectF(17, y + 9, 300, 15), Qt.AlignmentFlag.AlignVCenter, f"Boshqa {self._other[0]} kamera")
            p.setFont(fz.qfont(12.5, 500, mono=True))
            p.setPen(QColor(fz.TEXT2))
            p.drawText(QRectF(W - 17 - 60, y + 8, 60, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str(self._other[1]))
            y += 33
            p.fillRect(QRectF(17, y, W - 34, 1), QColor(fz.BORDER))
        p.setFont(fz.qfont(12.5, 600))
        p.setPen(QColor(fz.TEXT))
        p.drawText(QRectF(17, y + 9, 200, 15), Qt.AlignmentFlag.AlignVCenter, "Jami")
        p.setFont(fz.qfont(12.5, 600, mono=True))
        p.drawText(QRectF(W - 17 - 80, y + 8, 80, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   str(self._total))
        if not self._rows:
            p.setFont(fz.qfont(12, 400))
            p.setPen(QColor(fz.MUTED))
            p.drawText(QRectF(17, 8, 300, 16), Qt.AlignmentFlag.AlignVCenter, "Bu davrda buzilish yo‘q")
        p.end()


class _Heatmap(QWidget):
    """Karta koordinatalari: kataklar x46 dan (qadam 45.6, 42x17), y53 dan (qadam 21)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._grid = [[0] * 16 for _ in range(7)]
        self._hover = (-1, -1)

    def set_grid(self, grid):
        self._grid = grid
        self.update()

    def _geom(self):
        W = self.width()
        pitch_x = (W - 17 - 46 - 0.0) / 16
        cw = pitch_x * 42 / 45.6
        return 46.0, pitch_x, cw

    def mouseMoveEvent(self, e):
        x0, px, cw = self._geom()
        c = int((e.position().x() - x0) // px)
        r = int((e.position().y() - 53) // 21)
        h = (r, c) if 0 <= r < 7 and 0 <= c < 16 else (-1, -1)
        if h != self._hover:
            self._hover = h
            if h[0] >= 0:
                self.setToolTip(f"{WEEKDAYS[h[0]]}, {6 + h[1]:02d}:00–{7 + h[1]:02d}:00 · {self._grid[h[0]][h[1]]} ta")
            else:
                self.setToolTip("")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, px, cw = self._geom()
        mx = max(max(r) for r in self._grid) or 1
        p.setFont(fz.qfont(10.5, 400, mono=True))
        for r in range(7):
            y = 53 + 21 * r
            p.setPen(QColor(fz.MUTED))
            p.drawText(QRectF(17, y, 26, 17), Qt.AlignmentFlag.AlignVCenter, WEEKDAYS[r])
            for c in range(16):
                v = self._grid[r][c]
                lvl = 0 if v <= 0 else max(1, min(4, math.ceil(v / mx * 4)))
                col = QColor(HEAT_ZERO) if lvl == 0 else _mix(fz.CARD, fz.RED, HEAT_ALPHA[lvl])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(QRectF(x0 + px * c, y, cw, 17), 3, 3)
        p.setPen(QColor(fz.MUTED))
        for c in range(16):
            p.drawText(QRectF(x0 + px * c, 206, cw, 13), Qt.AlignmentFlag.AlignCenter, f"{6 + c:02d}")
        p.end()


class _DeptList(QWidget):
    """Karta ichi qatorlari (pitch 35): nom | trek 68x4 (W-137) | qiymat (W-39)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[str, float | None]] = []

    def set_rows(self, rows):
        self._rows = rows[:4]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        y = 0.0
        p.fillRect(QRectF(17, 0, W - 34, 1), QColor(fz.BORDER))
        tx = W - 137
        for i, (name, pct) in enumerate(self._rows):
            top = y + 1
            p.setFont(fz.qfont(13, 400))
            p.setPen(QColor(fz.TEXT2))
            p.drawText(QRectF(17, top + 9, tx - 30, 16), Qt.AlignmentFlag.AlignVCenter, name)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(fz.BORDER))
            p.drawRoundedRect(QRectF(tx, top + 15, 68, 4), 2, 2)
            if pct is not None:
                p.setBrush(QColor(fz.ACCENT if pct >= 90 else fz.RED))
                p.drawRoundedRect(QRectF(tx, top + 15, 68 * pct / 100, 4), 2, 2)
            p.setFont(fz.qfont(12, 500, mono=True))
            p.setPen(QColor(fz.TEXT))
            p.drawText(QRectF(W - 17 - 60, top + 9, 60, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "—" if pct is None else f"{pct:.0f}%")
            y += 35
            if i < len(self._rows) - 1:
                p.fillRect(QRectF(17, y, W - 34, 1), QColor(fz.BORDER))
        if not self._rows:
            p.setFont(fz.qfont(12, 400))
            p.setPen(QColor(fz.MUTED))
            p.drawText(QRectF(17, 10, 300, 16), Qt.AlignmentFlag.AlignVCenter, "Bo‘limlar ma’lumoti yo‘q")
        p.end()


class _Insight(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fzInsight")
        self.setFixedHeight(37)
        self.setStyleSheet(f"QFrame#fzInsight {{ background:{fz.RED_BG}; border:1px solid {fz.RED_BORDER}; border-radius:8px; }}")
        self.icon = fz.Icon("shield_alert", 15, fz.RED, parent=self)
        self.icon.move(12, 11)
        self.text = fz.label("", 12.5, 400, fz.RED, parent=self)
        self.text.move(36, 10)

    def set_text(self, t: str, warn: bool = True):
        self.text.setText(t)
        self.text.setFixedWidth(max(50, self.width() - 48))
        col = fz.RED if warn else fz.GREEN
        bg, bd = (fz.RED_BG, fz.RED_BORDER) if warn else (fz.GREEN_BG, fz.GREEN_BORDER)
        self.setStyleSheet(f"QFrame#fzInsight {{ background:{bg}; border:1px solid {bd}; border-radius:8px; }}")
        fz.restyle(self.text, 12.5, 400, col)
        self.icon.set_icon("shield_alert" if warn else "check", col)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.text.setFixedWidth(max(50, self.width() - 48))


class _Card(QFrame):
    """Sarlavha (17,15) Inter SemiBold 13.5 + o'ngda meta; kontent widgeti header ostida."""

    def __init__(self, title: str, meta_text: str = "", title_y: int = 15, parent=None):
        super().__init__(parent)
        self.setObjectName("fzAnCard")
        self.setStyleSheet(f"QFrame#fzAnCard {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:12px; }}")
        self.title = fz.label(title, 13.5, 600, fz.TEXT, parent=self)
        self.title.move(17, title_y - 1)
        self.meta = fz.label(meta_text, 12, 400, fz.MUTED, parent=self)
        self._ty = title_y
        self._right: QWidget | None = None

    def set_right(self, w: QWidget):
        self._right = w
        w.setParent(self)
        self._place()

    def set_meta(self, t: str):
        self.meta.setText(t)
        self.meta.adjustSize()
        self._place()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        W = self.width()
        self.meta.adjustSize()
        self.meta.move(W - 17 - self.meta.width(), self._ty)
        if self._right is not None:
            self._right.move(W - 17 - self._right.width(), self._ty + 0)


# ════════════════════════════════════════════════════════════════════════════
#  Davr segmenti (Hafta/Oy/Chorak/Yil) — 198x31, pad 4, segment h23
# ════════════════════════════════════════════════════════════════════════════

class _Seg(QWidget):
    changed = pyqtSignal(int)
    WIDTHS = (52, 36, 58, 44)

    def __init__(self, cur: int = 1, parent=None):
        super().__init__(parent)
        self._cur = cur
        self._hover = -1
        self.setFixedSize(4 + sum(self.WIDTHS) + 4, 31)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _rects(self):
        x = 4.0
        for w in self.WIDTHS:
            yield QRectF(x, 4, w, 23)
            x += w

    def mouseMoveEvent(self, e):
        h = next((i for i, r in enumerate(self._rects()) if r.contains(e.position())), -1)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        for i, r in enumerate(self._rects()):
            if r.contains(e.position()) and i != self._cur:
                self._cur = i
                self.update()
                self.changed.emit(i)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(fz.BORDER), 1))
        p.setBrush(QColor(fz.CARD))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, 30), 8, 8)
        for i, (r, (t, *_)) in enumerate(zip(self._rects(), PERIODS)):
            act = i == self._cur
            if act or i == self._hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(fz.ACTIVE) if act else QColor(21, 34, 59, 110))
                p.drawRoundedRect(r, 6, 6)
            p.setFont(fz.qfont(12.5, 600 if act else 500))
            p.setPen(QColor(fz.TEXT if act else fz.TEXT2))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, t)
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  AnalyticsPage
# ════════════════════════════════════════════════════════════════════════════

class AnalyticsPage(QWidget):
    go_cameras = pyqtSignal()
    _ready = pyqtSignal(dict)

    def __init__(self, db, config_manager=None, parent=None):
        super().__init__(parent)
        fz.init_fonts()
        self.db = db
        self.cfg = config_manager
        self._period = 1
        self._dept_id = None
        self._busy = False
        self._again = False
        self.setObjectName("fzAnalytics")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#fzAnalytics {{ background:{fz.BG}; }}")
        self._ready.connect(self._apply)
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setStyleSheet("QScrollArea { background:transparent; border:none; }"
                         "QScrollArea > QWidget > QWidget { background:transparent; }")
        outer.addWidget(sa)
        host = QWidget()
        host.setMinimumHeight(832)
        sa.setWidget(host)
        self._scroll, self._host = sa, host
        root = QVBoxLayout(host)
        root.setContentsMargins(16, 22, 16, 16)
        root.setSpacing(0)

        self.header = fz.PageHeader("Analitika", "Buzilishlar trendi — vaqt, kamera va bo‘lim kesimida", gap=12)
        self.seg = _Seg(1)
        self.seg.changed.connect(self._on_period)
        deps = self.cfg.get_departments() if self.cfg else []
        self._deps = deps
        self.dd = fz.Dropdown(["Barcha bo‘limlar"] + [d.get("name", "Bo‘lim") for d in deps], 0, icon="building",
                              h=31, min_w=161)
        self.dd.changed.connect(self._on_dept)
        pdf = fz.Button("Hisobot (PDF)", "ghost", icon="file", icon_size=15, h=31, px=13, weight=600, pad=14, gap=7)
        pdf.clicked.connect(self._export_pdf)
        self.header.add_right(self.seg)
        self.header.add_right(self.dd)
        self.header.add_right(pdf)
        root.addWidget(self.header)
        root.addSpacing(15)

        kr = QHBoxLayout()
        kr.setSpacing(12)
        self.k1 = _KPI("30 kunda buzilishlar", "shield_alert", fz.RED_BG)
        self.k2 = _KPI("O‘rtacha muvofiqlik", "check", fz.BLUE_BG)
        self.k3 = _KPI("Takror buzganlar", "refresh", fz.BLUE_BG)
        self.k4 = _KPI("O‘rtacha javob vaqti", "cpu", fz.GREEN_BG)
        for k in (self.k1, self.k2, self.k3, self.k4):
            kr.addWidget(k, 1)
        root.addLayout(kr)
        root.addSpacing(15)

        mid = QHBoxLayout()
        mid.setSpacing(12)
        self.c_trend = _Card("Kunlik buzilishlar · so‘nggi 30 kun")
        self.legend = _Legend()
        self.c_trend.set_right(self.legend)
        self.chart = _TrendChart(self.c_trend)
        self.c_trend.installEventFilter(self)
        mid.addWidget(self.c_trend, 897)
        self.c_rank = _Card("Eng ko‘p buzilish", "Kameralar · 30 kun")
        self.rank = _Ranking(self.c_rank)
        self.c_rank.installEventFilter(self)
        mid.addWidget(self.c_rank, 499)
        root.addLayout(mid, 389)
        root.addSpacing(15)

        bot = QHBoxLayout()
        bot.setSpacing(12)
        self.c_heat = _Card("Hafta kuni × soat", "Qizilroq — ko‘proq buzilish", title_y=14)
        self.heat = _Heatmap(self.c_heat)
        self.c_heat.installEventFilter(self)
        bot.addWidget(self.c_heat, 789)
        self.c_dept = _Card("Bo‘limlar bo‘yicha muvofiqlik", "30 kun", title_y=14)
        self.depts = _DeptList(self.c_dept)
        self.insight = _Insight(self.c_dept)
        self.c_dept.installEventFilter(self)
        bot.addWidget(self.c_dept, 607)
        self._bottom = bot
        root.addLayout(bot, 249)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if ev.type() == QEvent.Type.Resize:
            W, H = obj.width(), obj.height()
            if obj is self.c_trend:
                self.chart.setGeometry(0, 0, W, H)
            elif obj is self.c_rank:
                self.rank.setGeometry(0, 44, W, H - 44)
            elif obj is self.c_heat:
                self.heat.setGeometry(0, 0, W, H)
            elif obj is self.c_dept:
                self.depts.setGeometry(0, 43, W, 145)
                self.insight.setGeometry(17, H - 16 - 37, W - 34, 37)
        return super().eventFilter(obj, ev)

    # ── filtrlar ──
    def _on_period(self, i):
        self._period = i
        self.refresh()

    def _on_dept(self, i):
        self._dept_id = None if i == 0 else self._deps[i - 1].get("id")
        self.refresh()

    def reload_departments(self):
        """Bo'limlar Sozlamalarda o'zgarganda dropdown qayta quriladi (tanlov saqlanadi)."""
        deps = self.cfg.get_departments() if self.cfg else []
        self._deps = deps
        ids = [d.get("id") for d in deps]
        cur = ids.index(self._dept_id) + 1 if self._dept_id in ids else 0
        if cur == 0 and self._dept_id is not None:
            self._dept_id = None          # tanlangan bo'lim o'chirilgan
        self.dd.set_options(["Barcha bo‘limlar"] + [d.get("name", "Bo‘lim") for d in deps], cur)
        if self.isVisible():
            self.refresh()

    def _range(self):
        days = PERIODS[self._period][1]
        t = date.today()
        return t - timedelta(days=days - 1), t, days

    # ── yuklash ──
    def refresh(self):
        if self._busy:
            self._again = True
            return
        self._busy = True
        d_from, d_to, days = self._range()
        cams = self.cfg.get_cameras() if self.cfg else []
        deps = {d.get("id"): d.get("name", "Bo‘lim") for d in (self.cfg.get_departments() if self.cfg else [])}
        cam_dep = {str(c.get("name") or ""): c.get("department_id") for c in cams}
        dept_id = self._dept_id
        cam_filter = [n for n, did in cam_dep.items() if did == dept_id] if dept_id is not None else None

        def job():
            out = {"days": days, "d_from": d_from, "d_to": d_to}
            try:
                conn = self.db._conn()
                # Noto'g'ri aniqlangan (rejected) hodisalar Hodisalar sahifasida ko'rinmaydi —
                # analitikada ham hisoblanmaydi
                where, params = ("timestamp BETWEEN ? AND ? AND COALESCE(review_status,'new') != 'rejected'",
                                 [_ts(d_from), _ts(d_to, True)])
                if cam_filter is not None:
                    where += f" AND camera_name IN ({','.join('?' * len(cam_filter)) or 'NULL'})"
                    params += cam_filter
                pf, pt_ = d_from - timedelta(days=days), d_from - timedelta(days=1)
                pwhere = where.replace("timestamp BETWEEN ? AND ?", "timestamp BETWEEN ? AND ?")
                pparams = [_ts(pf), _ts(pt_, True)] + params[2:]
                q = lambda sql, ps: conn.execute(sql, ps).fetchall()
                rows = q(f"SELECT date(timestamp,'unixepoch','localtime') d, COUNT(*) c FROM violations WHERE {where} GROUP BY d", params)
                per_day = {r["d"]: int(r["c"]) for r in rows}
                out["series"] = [(d_from + timedelta(days=i)) for i in range(days)]
                out["vals"] = [per_day.get((d_from + timedelta(days=i)).isoformat(), 0) for i in range(days)]
                out["total"] = sum(out["vals"])
                out["prev_total"] = int(q(f"SELECT COUNT(*) c FROM violations WHERE {pwhere}", pparams)[0]["c"])
                out["by_cam"] = [(r["camera_name"] or "Noma’lum", int(r["c"])) for r in
                                 q(f"SELECT camera_name, COUNT(*) c FROM violations WHERE {where} GROUP BY camera_name ORDER BY c DESC", params)]
                grid = [[0] * 16 for _ in range(7)]
                for r in q(f"SELECT CAST(strftime('%w',timestamp,'unixepoch','localtime') AS INT) w,"
                           f" CAST(strftime('%H',timestamp,'unixepoch','localtime') AS INT) h, COUNT(*) c"
                           f" FROM violations WHERE {where} GROUP BY w,h", params):
                    wd = (int(r["w"]) + 6) % 7      # 0=Dushanba
                    h = int(r["h"])
                    if 6 <= h <= 21:
                        grid[wd][h - 6] += int(r["c"])
                out["grid"] = grid
                peak = q(f"SELECT CAST(strftime('%H',timestamp,'unixepoch','localtime') AS INT) h, camera_name, COUNT(*) c"
                         f" FROM violations WHERE {where} GROUP BY h, camera_name", params)
                out["peak_rows"] = [(int(r["h"]), r["camera_name"] or "", int(r["c"])) for r in peak]

                def det_between(a: date, b: date):
                    rs = q("SELECT camera_name, SUM(detections) s FROM daily_stats WHERE date BETWEEN ? AND ? GROUP BY camera_name",
                           [a.isoformat(), b.isoformat()])
                    return {r["camera_name"] or "": int(r["s"] or 0) for r in rs}
                out["det"] = det_between(d_from, d_to)
                out["prev_det"] = det_between(pf, pt_)
                out["prev_by_cam"] = {r["camera_name"] or "": int(r["c"]) for r in
                                      q(f"SELECT camera_name, COUNT(*) c FROM violations WHERE {pwhere} GROUP BY camera_name", pparams)}

                def repeaters(w, ps):
                    rs = q(f"SELECT COALESCE(NULLIF(employee_id,''), NULLIF(employee_name,'')) k, COUNT(*) c FROM violations"
                           f" WHERE {w} AND COALESCE(NULLIF(employee_id,''), NULLIF(employee_name,'')) IS NOT NULL"
                           f" GROUP BY k HAVING c >= 2", ps)
                    return len(rs)
                out["rep"] = repeaters(where, params)
                out["prev_rep"] = repeaters(pwhere, pparams)

                def resp(a, b):
                    r = q("SELECT AVG(sent_at - created_at) s FROM notification_jobs WHERE status='sent' AND sent_at IS NOT NULL"
                          " AND created_at BETWEEN ? AND ?", [_ts(a), _ts(b, True)])
                    return float(r[0]["s"]) if r and r[0]["s"] is not None else None
                out["resp"] = resp(d_from, d_to)
                out["prev_resp"] = resp(pf, pt_)
            except Exception as exc:
                out["error"] = str(exc)
            out["cam_dep"] = cam_dep
            out["deps"] = deps
            out["cam_filter"] = cam_filter
            self._ready.emit(out)

        threading.Thread(target=job, daemon=True, name="AnalyticsLoad").start()

    # ── natijalarni chizish ──
    def _apply(self, d: dict):
        self._busy = False
        if self._again:
            self._again = False
            QTimer.singleShot(0, self.refresh)
        if "vals" not in d:
            return
        lbl, days, kda, prev_lbl = PERIODS[self._period]
        total, prev = d["total"], d["prev_total"]
        if prev:
            pct = (total - prev) / prev * 100
            self.k1.set_data(str(total), "", f"{'+' if pct >= 0 else '−'}{abs(pct):.0f}% {prev_lbl}", good=pct <= 0, danger=total > 0)
        else:
            self.k1.set_data(str(total), "", "", danger=total > 0)
        self.k1.set_title(f"{kda} buzilishlar")

        def comp(det_map, viol_total, filt):
            det = sum(v for k, v in det_map.items() if filt is None or k in filt)
            return None if det <= 0 else max(0.0, 100.0 * (1 - viol_total / max(det, viol_total)))
        c_now = comp(d["det"], total, d["cam_filter"])
        c_prev = comp(d["prev_det"], prev, d["cam_filter"])
        if c_now is None:
            self.k2.set_data("—")
        else:
            pill = f"{'+' if (c_now - c_prev) >= 0 else '−'}{abs(c_now - c_prev):.1f}" if c_prev is not None else ""
            self.k2.set_data(f"{c_now:.1f}", "%", pill, good=(c_prev is None or c_now >= c_prev))
        dr = d["rep"] - d["prev_rep"]
        self.k3.set_data(str(d["rep"]), "", (f"{'+' if dr >= 0 else '−'}{abs(dr)}" if (d["rep"] or d["prev_rep"]) else ""),
                         good=dr <= 0)
        if d["resp"] is None:
            self.k4.set_data("—", "", "")
        else:
            r = d["resp"]
            pill = ""
            good = None
            if d["prev_resp"] is not None:
                dd = r - d["prev_resp"]
                pill, good = f"{'+' if dd >= 0 else '−'}{abs(dd):.1f}s", dd <= 0
            self.k4.set_data(f"{r:.1f}", "s", pill, good=good)

        # trend
        self.c_trend.title.setText(f"Kunlik buzilishlar · so‘nggi {days} kun")
        self.c_trend.title.adjustSize()
        avg = total / max(1, days)
        self.legend.set_avg(f"O‘rtacha ({avg:.1f})")
        self.c_trend._place()
        self.chart.set_data(d["series"], d["vals"])

        # reyting
        by = d["by_cam"]
        top = by[:6]
        rest = by[6:]
        self.rank.set_data(top, len(rest), sum(v for _, v in rest), total)
        self.c_rank.set_meta(f"Kameralar · {days} kun")
        self.heat.set_grid(d["grid"])

        # bo'limlar
        rows = []
        cam_dep, deps = d["cam_dep"], d["deps"]
        by_map = dict(by)
        for did, name in deps.items():
            cams = [c for c, dd in cam_dep.items() if dd == did]
            det = sum(d["det"].get(c, 0) for c in cams)
            v = sum(by_map.get(c, 0) for c in cams)
            pct = None if det <= 0 else max(0.0, 100.0 * (1 - v / max(det, v)))
            if pct is None and v == 0 and det == 0:
                pct = None
            rows.append((name, pct, v))
        if self._dept_id is not None:
            rows = [r for r in rows if r[0] == deps.get(self._dept_id)]
        self.depts.set_rows([(n, p) for n, p, _ in rows])
        self.c_dept.set_meta(f"{days} kun")
        # insight: eng ko'p buzilgan bo'lim va uning cho'qqi soati
        worst = max(rows, key=lambda r: r[2], default=None)
        if worst and worst[2] > 0:
            cams = {c for c, dd in cam_dep.items() if deps.get(dd) == worst[0]}
            hours: dict[int, int] = {}
            for h, cam, c in d["peak_rows"]:
                if cam in cams:
                    hours[h] = hours.get(h, 0) + c
            if hours:
                h = max(hours, key=hours.get)
                self.insight.set_text(f"{worst[0]}da buzilishlar {h:02d}:00–{h + 1:02d}:00 da eng ko‘p — "
                                      f"{hours[h]} ta ({hours[h] * 100 // max(1, worst[2])}%).", warn=True)
            else:
                self.insight.set_text(f"{worst[0]}da {worst[2]} ta buzilish qayd etildi.", warn=True)
        else:
            self.insight.set_text("Bu davrda buzilishlar qayd etilmagan — barcha bo‘limlar me’yorda.", warn=False)

    # ── PDF hisobot ──
    def _export_pdf(self):
        d_from, d_to, days = self._range()
        path, _ = QFileDialog.getSaveFileName(
            self, "Hisobot (PDF)", os.path.join(os.path.expanduser("~"), "Desktop",
                                                f"SafeZone_hisobot_{d_from:%Y%m%d}_{d_to:%Y%m%d}.pdf"), "PDF (*.pdf)")
        if not path:
            return
        from app.ui.widgets.toast import show_toast
        ok, err = self._write_pdf(path, f"SafeZone — Analitika {d_from:%d.%m.%Y}–{d_to:%d.%m.%Y}")
        if ok:
            show_toast(self, f"Hisobot saqlandi: {path}", "success", 5000)
        else:
            show_toast(self, f"Hisobot saqlanmadi: {err}", "error")

    def _write_pdf(self, path: str, title: str) -> tuple[bool, str]:
        """Scroll ichidagi butun sahifani (ko'rinmaydigan qismi ham) PDF ga chizadi;
        sahifa A4 dan baland bo'lsa bir nechta varaqqa bo'linadi."""
        # Faqat ko'rinib turgan qism emas — ichki widget to'liq o'lchamda
        pm = self._host.grab(self._host.rect())
        if pm.isNull() or pm.width() <= 0 or pm.height() <= 0:
            return False, "sahifa rasmi olinmadi"
        w = QPdfWriter(path)
        w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        w.setPageOrientation(QPageLayout.Orientation.Landscape)
        w.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
        w.setTitle(title)
        p = QPainter(w)
        if not p.isActive():            # fayl ochilmadi (band, ruxsat yo'q, noto'g'ri yo'l)
            return False, "faylga yozib bo'lmadi (fayl ochiq yoki ruxsat yo'q)"
        try:
            r = p.viewport()
            s = r.width() / pm.width()               # kenglik bo'yicha moslash
            slice_h = max(1, int(r.height() / s))    # bir varaqqa sig'adigan manba balandligi
            y = 0
            while y < pm.height():
                h = min(slice_h, pm.height() - y)
                p.drawPixmap(QRectF(0, 0, pm.width() * s, h * s), pm, QRectF(0, y, pm.width(), h))
                y += h
                if y < pm.height() and not w.newPage():
                    return False, "yangi varaq qo'shilmadi"
        finally:
            p.end()
        try:
            if os.path.getsize(path) <= 0:
                return False, "fayl bo'sh"
        except OSError as exc:
            return False, str(exc)
        return True, ""
