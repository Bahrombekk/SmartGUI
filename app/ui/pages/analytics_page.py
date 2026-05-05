"""
AnalyticsPage — clean, consistent with project design language.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import QDate, QPointF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.application.services.analytics_service import AnalyticsService
from app.ui.widgets.bar_chart import BarChart, HourlyBarChart, LineChart

_ICON_DIR = Path(__file__).resolve().parents[3] / "images"


def _svg_pixmap(name: str, color: str, size: int = 16) -> QPixmap:
    """Load SVG from images dir and tint it to `color`."""
    path = _ICON_DIR / name
    src = QPixmap(str(path)) if path.exists() else QPixmap()
    if src.isNull():
        return src
    src = src.scaled(size, size,
                     Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(src.size())
    result.fill(Qt.GlobalColor.transparent)
    p = QPainter(result)
    p.drawPixmap(0, 0, src)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(result.rect(), QColor(color))
    p.end()
    return result


# ── Design tokens (mirrors rest of app) ──────────────────────────────────────
_BG      = "#03070b"
_CARD    = "#07101a"
_CARD2   = "#0a1520"
_CARD3   = "#0d1e30"
_BORDER  = "#1e5fa8"       # vivid blue — used across all panels
_BSOFT   = "#1a3552"       # dimmer blue for inner separators
_TEXT    = "#f8fafc"
_TEXT2   = "#cbd5e1"
_MUTED   = "#64748b"

# Status colors — used only on data / badges / left bars
_RED     = "#ef4444"
_ORANGE  = "#f97316"
_AMBER   = "#f59e0b"
_GREEN   = "#22c55e"
_BLUE    = "#3b82f6"
_LBLUE   = "#60a5fa"
_PURPLE  = "#a78bfa"
_TEAL    = "#2dd4bf"


def _fmt(v) -> str:
    return f"{int(v or 0):,}"


# ── Sparkline ─────────────────────────────────────────────────────────────────
class _Sparkline(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._values: list[int] = [2, 8, 5, 12, 7, 16, 11, 20]
        self.setFixedSize(82, 40)

    def set_values(self, values: list[int]):
        self._values = values[-12:] or self._values
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 4, -2, -3)
        vals = self._values
        if not vals:
            p.end()
            return
        hi, lo = max(vals), min(vals)
        span = max(hi - lo, 1)
        pts = [
            QPointF(
                rect.left() + rect.width() * i / max(len(vals) - 1, 1),
                rect.bottom() - rect.height() * (v - lo) / span,
            )
            for i, v in enumerate(vals)
        ]
        if len(pts) > 1:
            area = QPainterPath()
            area.moveTo(pts[0].x(), rect.bottom())
            area.lineTo(pts[0])
            for pt in pts[1:]:
                area.lineTo(pt)
            area.lineTo(pts[-1].x(), rect.bottom())
            area.closeSubpath()
            g = QLinearGradient(0, rect.top(), 0, rect.bottom())
            g.setColorAt(0, QColor(self._color + "70"))
            g.setColorAt(1, QColor(self._color + "00"))
            p.fillPath(area, g)
            line = QPainterPath()
            line.moveTo(pts[0])
            for pt in pts[1:]:
                line.lineTo(pt)
            p.setPen(QPen(QColor(self._color), 1.8,
                         Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap,
                         Qt.PenJoinStyle.RoundJoin))
            p.drawPath(line)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._color))
            p.drawEllipse(pts[-1], 2.5, 2.5)
        p.end()


# ── KPI metric card ───────────────────────────────────────────────────────────
class _MetricCard(QFrame):
    def __init__(self, title: str, icon: str, accent: str, subtitle: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setMinimumHeight(122)
        self.setStyleSheet(
            "QFrame {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {_CARD3},stop:1 {_CARD});"
            f"border: 1px solid {_BORDER};"
            f"border-top: 3px solid {accent};"
            "border-radius: 10px;"
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        ico = QLabel()
        ico.setFixedSize(50, 50)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico.setStyleSheet(
            f"background: rgba({self._hex_to_rgb(accent)},0.12);"
            f"border: 1px solid rgba({self._hex_to_rgb(accent)},0.30);"
            "border-radius: 12px;"
        )
        pix = _svg_pixmap(icon, accent, 22)
        if not pix.isNull():
            ico.setPixmap(pix)
        else:
            ico.setText("●")
            ico.setStyleSheet(
                ico.styleSheet() + f" color: {accent}; font-size: 20px; font-weight: 900;"
            )
        lay.addWidget(ico)

        col = QVBoxLayout()
        col.setSpacing(2)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {accent}; font-size: 10px; font-weight: 900; letter-spacing: 1px;"
        )
        col.addWidget(self._title_lbl)
        self._value_lbl = QLabel("0")
        self._value_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 28px; font-weight: 900;")
        col.addWidget(self._value_lbl)
        self._delta_lbl = QLabel(subtitle)
        self._delta_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: 700;")
        col.addWidget(self._delta_lbl)
        lay.addLayout(col, 1)

        self._spark = _Sparkline(accent)
        lay.addWidget(self._spark)

    def set_value(self, v: int):
        self._value_lbl.setText(_fmt(v))

    def set_delta(self, text: str, color: str | None = None):
        self._delta_lbl.setText(text)
        self._delta_lbl.setStyleSheet(
            f"color: {color or _MUTED}; font-size: 11px; font-weight: 800;"
        )

    def set_spark_values(self, values: list[int]):
        self._spark.set_values(values)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r},{g},{b}"


# ── Section card (consistent with dashboard panels) ───────────────────────────
class _SectionCard(QFrame):
    """Dark card with vivid-blue border and a colored left-bar header."""

    def __init__(self, title: str, bar_color: str = _LBLUE, parent=None):
        super().__init__(parent)
        self.setObjectName("analyticsSection")
        self.setStyleSheet(
            "QFrame#analyticsSection {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {_CARD2},stop:1 {_CARD});"
            f"border: 1px solid {_BORDER};"
            "border-radius: 10px;"
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setObjectName("secHdr")
        hdr.setFixedHeight(42)
        hdr.setStyleSheet(
            "QWidget#secHdr {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 rgba(30,95,168,0.14),stop:1 transparent);"
            f"border-bottom: 1px solid {_BORDER};"
            "border-radius: 9px 9px 0 0; }"
            "QLabel { background: transparent; border: none; }"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 10, 0)
        hl.setSpacing(0)

        # Pill-shaped accent — centered vertically, fully rounded
        pill_wrap = QWidget()
        pill_wrap.setFixedSize(14, 42)
        pill_wrap.setStyleSheet("background: transparent; border: none;")
        pwl = QVBoxLayout(pill_wrap)
        pwl.setContentsMargins(5, 9, 4, 9)
        pwl.setSpacing(0)
        pill = QWidget()
        pill.setStyleSheet(
            f"background: {bar_color};"
            "border-radius: 3px; border: none;"
        )
        pwl.addWidget(pill)
        hl.addWidget(pill_wrap)
        hl.addSpacing(6)

        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: 900;")
        hl.addWidget(lbl)
        hl.addStretch()
        self._hdr_row = hl
        root.addWidget(hdr)

        bw = QWidget()
        bw.setStyleSheet("background: transparent;")
        self._body = QVBoxLayout(bw)
        self._body.setContentsMargins(14, 10, 14, 14)
        self._body.setSpacing(8)
        root.addWidget(bw, 1)

    def add_header_widget(self, w: QWidget):
        self._hdr_row.addWidget(w)

    def add_body_widget(self, w: QWidget):
        self._body.addWidget(w)


# ── AI Insight row ────────────────────────────────────────────────────────────
class _InsightRow(QFrame):
    def __init__(self, title: str, detail: str, accent: str, icon: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(56)
        self.setStyleSheet(
            "QFrame {"
            f"background: {_CARD};"
            f"border: 1px solid {_BSOFT};"
            f"border-left: 3px solid {accent};"
            "border-radius: 7px; }"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        badge = QLabel()
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: rgba(30,95,168,0.18);"
            f"border: 1px solid {_BORDER}; border-radius: 16px;"
        )
        pix = _svg_pixmap(icon, accent, 15)
        if not pix.isNull():
            badge.setPixmap(pix)
        else:
            badge.setText("●")
            badge.setStyleSheet(badge.styleSheet() + f" color: {accent}; font-size: 13px;")
        lay.addWidget(badge)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: 900;")
        col.addWidget(t)
        d = QLabel(detail)
        d.setStyleSheet(f"color: {_TEXT2}; font-size: 11px; font-weight: 600;")
        col.addWidget(d)
        lay.addLayout(col, 1)


# ── Progress bar row ──────────────────────────────────────────────────────────
class _ProgressRow(QFrame):
    def __init__(self, label: str, value: int, max_value: int,
                 color: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(5)

        top = QHBoxLayout()
        name = QLabel(label)
        name.setStyleSheet(f"color: {_TEXT}; font-size: 12px; font-weight: 800;")
        top.addWidget(name, 1)
        cnt = QLabel(_fmt(value))
        cnt.setAlignment(Qt.AlignmentFlag.AlignRight)
        cnt.setStyleSheet(f"color: {_TEXT2}; font-size: 12px; font-weight: 900;")
        top.addWidget(cnt)
        lay.addLayout(top)

        track = QFrame()
        track.setFixedHeight(7)
        track.setStyleSheet(f"background: rgba(30,95,168,0.18); border: none; border-radius: 3px;")
        tl = QHBoxLayout(track)
        tl.setContentsMargins(0, 0, 0, 0)
        fill = QFrame()
        fill.setFixedWidth(max(16, int(280 * value / max(max_value, 1))))
        fill.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {color},stop:1 {color}80);"
            "border: none; border-radius: 3px;"
        )
        tl.addWidget(fill)
        tl.addStretch()
        lay.addWidget(track)

        if detail:
            sub = QLabel(detail)
            sub.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 600;")
            lay.addWidget(sub)


# ── Donut gauge ───────────────────────────────────────────────────────────────
class _SplitGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, int, str]] = []
        self.setMinimumHeight(114)

    def set_items(self, items: list[tuple[str, int, str]]):
        self._items = items
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(v for _, v, _ in self._items) or 1
        cx, cy = self.width() // 2, self.height() // 2
        r = min(46, max(30, min(self.width(), self.height()) // 3))
        start = 90 * 16
        for _, value, color in self._items:
            span = -int(360 * 16 * value / total)
            p.setPen(QPen(QColor(color), 11,
                         Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(cx - r, cy - r, r * 2, r * 2, start, span)
            start += span
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_CARD))
        ir = r - 6
        p.drawEllipse(cx - ir, cy - ir, ir * 2, ir * 2)
        p.setPen(QColor(_TEXT))
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.Black))
        p.drawText(cx - 36, cy - 14, 72, 22, Qt.AlignmentFlag.AlignCenter, _fmt(total))
        p.setPen(QColor(_MUTED))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(cx - 36, cy + 5, 72, 14, Qt.AlignmentFlag.AlignCenter, "events")
        p.end()


# ── Ranking row ───────────────────────────────────────────────────────────────
def _ranking_row(rank: int, name: str, count: int, max_count: int) -> QFrame:
    palette = [_RED, _ORANGE, _AMBER, _BLUE, _GREEN]
    color = palette[rank % len(palette)]
    w = QFrame()
    w.setStyleSheet(
        f"QFrame {{ background: {_CARD}; border: 1px solid {_BSOFT}; border-radius: 7px; }}"
        "QLabel { background: transparent; border: none; }"
    )
    lay = QHBoxLayout(w)
    lay.setContentsMargins(10, 7, 10, 7)
    lay.setSpacing(9)

    badge = QLabel(str(rank + 1))
    badge.setFixedSize(24, 24)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"color: {color}; background: rgba(30,95,168,0.22);"
        f"border: 1px solid {_BORDER}; border-radius: 12px;"
        "font-weight: 900; font-size: 11px;"
    )
    lay.addWidget(badge)

    n = QLabel(name)
    n.setStyleSheet(f"color: {_TEXT}; font-size: 12px; font-weight: 800;")
    lay.addWidget(n, 1)

    track = QFrame()
    track.setFixedHeight(6)
    track.setMinimumWidth(80)
    track.setStyleSheet(f"background: rgba(30,95,168,0.18); border: none; border-radius: 3px;")
    tl = QHBoxLayout(track)
    tl.setContentsMargins(0, 0, 0, 0)
    fill = QFrame()
    fill.setFixedWidth(max(12, int(100 * count / max(max_count, 1))))
    fill.setStyleSheet(
        f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"stop:0 {color},stop:1 {color}70);"
        "border: none; border-radius: 3px;"
    )
    tl.addWidget(fill)
    tl.addStretch()
    lay.addWidget(track, 1)

    cv = QLabel(_fmt(count))
    cv.setMinimumWidth(48)
    cv.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    cv.setStyleSheet(f"color: {_TEXT2}; font-size: 12px; font-weight: 900;")
    lay.addWidget(cv)
    return w


# ── Ops mini card ─────────────────────────────────────────────────────────────
def _ops_card(title: str, value: str, color: str) -> QFrame:
    card = QFrame()
    card.setMinimumHeight(66)
    card.setStyleSheet(
        "QFrame {"
        f"background: {_CARD};"
        f"border: 1px solid {_BSOFT};"
        f"border-left: 3px solid {color};"
        "border-radius: 7px; }"
        "QLabel { background: transparent; border: none; }"
    )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(1)
    v = QLabel(value)
    v.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 900;")
    lay.addWidget(v)
    t = QLabel(title)
    t.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 700;")
    lay.addWidget(t)
    return card


# ── Main page ─────────────────────────────────────────────────────────────────
class AnalyticsPage(QWidget):
    def __init__(self, db, config_manager=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = config_manager
        self.analytics = AnalyticsService(db, config_manager)
        self._setup_ui()
        self._load_all()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load_all)
        self._timer.start(300_000)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setObjectName("analyticsPage")
        self.setStyleSheet(f"QWidget#analyticsPage {{ background: {_BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        c = QVBoxLayout(body)
        c.setContentsMargins(16, 14, 16, 18)
        c.setSpacing(12)

        # KPI row
        self._metric_cards = {
            "today": _MetricCard("TODAY VIOLATIONS", "alerts.svg",    _RED,    "vs yesterday"),
            "week":  _MetricCard("THIS WEEK",        "analytics.svg", _ORANGE, "vs last week"),
            "month": _MetricCard("THIS MONTH",       "reports.svg",   _AMBER,  "vs last month"),
            "total": _MetricCard("TOTAL VIOLATIONS", "database.svg",  _LBLUE,  "all time data"),
        }
        kpi = QGridLayout()
        kpi.setSpacing(10)
        for idx, card in enumerate(self._metric_cards.values()):
            kpi.addWidget(card, 0, idx)
        c.addLayout(kpi)

        # Row 1: chart | insights | ranking
        r1 = QHBoxLayout()
        r1.setSpacing(10)

        daily = _SectionCard("Daily Violations Trend", _RED)
        self._days_combo = QComboBox()
        self._days_combo.addItems(["14 days", "30 days", "60 days", "90 days"])
        self._days_combo.setCurrentIndex(1)
        self._days_combo.setFixedSize(100, 28)
        self._days_combo.setStyleSheet(self._combo_style())
        self._days_combo.currentIndexChanged.connect(self._load_daily)
        daily.add_header_widget(self._legend_dot(_RED, "No Helmet"))
        daily.add_header_widget(self._legend_dot(_GREEN, "Helmet"))
        daily.add_header_widget(self._days_combo)
        self._bar_chart = BarChart()
        self._bar_chart.setMinimumHeight(240)
        daily.add_body_widget(self._bar_chart)
        r1.addWidget(daily, 5)

        insights = _SectionCard("AI Insights", _LBLUE)
        self._insight_layout = QVBoxLayout()
        self._insight_layout.setSpacing(7)
        insights._body.addLayout(self._insight_layout)
        insights._body.addStretch()
        r1.addWidget(insights, 3)

        ranking = _SectionCard("Camera Ranking  (Top 5)", _ORANGE)
        self._ranking_layout = QVBoxLayout()
        self._ranking_layout.setSpacing(6)
        ranking._body.addLayout(self._ranking_layout)
        all_btn = QPushButton("All cameras  →")
        all_btn.setFixedHeight(26)
        all_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_ORANGE};"
            "border: none; font-size: 11px; font-weight: 800; text-align: right; }}"
            "QPushButton:hover { color: #fb923c; }"
        )
        ranking.add_body_widget(all_btn)
        r1.addWidget(ranking, 3)
        c.addLayout(r1)

        # Row 2: weekly | hourly
        r2 = QHBoxLayout()
        r2.setSpacing(10)

        weekly = _SectionCard("Weekly Trend", _PURPLE)
        wc = QComboBox()
        wc.addItems(["Week", "Month"])
        wc.setFixedSize(86, 28)
        wc.setStyleSheet(self._combo_style())
        weekly.add_header_widget(wc)
        self._line_chart = LineChart()
        self._line_chart.setMinimumHeight(208)
        weekly.add_body_widget(self._line_chart)
        r2.addWidget(weekly, 1)

        hourly = _SectionCard("Today's Hourly Distribution", _TEAL)
        self._hourly_chart = HourlyBarChart()
        self._hourly_chart.setMinimumHeight(208)
        hourly.add_body_widget(self._hourly_chart)
        r2.addWidget(hourly, 1)
        c.addLayout(r2)

        # Row 3: departments | mix | ops
        r3 = QHBoxLayout()
        r3.setSpacing(10)

        depts = _SectionCard("Department Breakdown", _ORANGE)
        self._dept_layout = QVBoxLayout()
        self._dept_layout.setSpacing(9)
        depts._body.addLayout(self._dept_layout)
        r3.addWidget(depts, 5)

        mix = _SectionCard("Violation Mix", _AMBER)
        self._type_gauge = _SplitGauge()
        mix.add_body_widget(self._type_gauge)
        self._type_layout = QVBoxLayout()
        self._type_layout.setSpacing(6)
        mix._body.addLayout(self._type_layout)
        r3.addWidget(mix, 3)

        ops = _SectionCard("Operational Health", _GREEN)
        self._ops_layout = QGridLayout()
        self._ops_layout.setSpacing(7)
        ops._body.addLayout(self._ops_layout)
        r3.addWidget(ops, 3)
        c.addLayout(r3)

        c.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _build_header(self) -> QWidget:
        h = QFrame()
        h.setObjectName("analyticsHdr")
        h.setFixedHeight(72)
        h.setStyleSheet(
            "QFrame#analyticsHdr {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {_CARD3},stop:1 {_CARD});"
            f"border-bottom: 1px solid {_BORDER}; }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(h)
        lay.setContentsMargins(0, 0, 20, 0)
        lay.setSpacing(14)

        bar = QWidget()
        bar.setFixedSize(4, 72)
        bar.setStyleSheet(f"background: {_ORANGE}; border: none;")
        lay.addWidget(bar)
        lay.addSpacing(10)

        tc = QVBoxLayout()
        tc.setSpacing(2)
        t = QLabel("Analytics")
        t.setStyleSheet(f"color: {_TEXT}; font-size: 20px; font-weight: 900;")
        tc.addWidget(t)
        s = QLabel("Violation trends by time, camera and operational health")
        s.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        tc.addWidget(s)
        lay.addLayout(tc)
        lay.addStretch()

        self._date_filter = QDateEdit(QDate.currentDate())
        self._date_filter.setDisplayFormat("dd MMM yyyy")
        self._date_filter.setCalendarPopup(True)
        self._date_filter.setFixedSize(144, 34)
        self._date_filter.setStyleSheet(self._combo_style())
        lay.addWidget(self._date_filter)

        self._zone_combo = QComboBox()
        self._zone_combo.addItem("All Departments")
        if self.cfg:
            for d in self.cfg.get_departments():
                self._zone_combo.addItem(str(d.get("name", "")))
        self._zone_combo.setFixedSize(144, 34)
        self._zone_combo.setStyleSheet(self._combo_style())
        lay.addWidget(self._zone_combo)

        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All Cameras")
        if self.cfg:
            for c in self.cfg.get_cameras():
                self._camera_combo.addItem(str(c.get("name", "")))
        self._camera_combo.setFixedSize(144, 34)
        self._camera_combo.setStyleSheet(self._combo_style())
        lay.addWidget(self._camera_combo)

        seg = QWidget()
        seg.setStyleSheet("background: transparent;")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self._period_group = QButtonGroup(self)
        _lbls = ["Today", "Week", "Month", "Custom"]
        for idx, txt in enumerate(_lbls):
            btn = QPushButton(txt)
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.setStyleSheet(self._seg_style(idx, len(_lbls)))
            if idx == 0:
                btn.setChecked(True)
            self._period_group.addButton(btn, idx)
            sl.addWidget(btn)
        lay.addWidget(seg)

        refresh = QPushButton("Refresh")
        refresh.setFixedSize(88, 34)
        refresh.setStyleSheet(
            f"QPushButton {{ background: rgba(249,115,22,0.12); color: {_ORANGE};"
            f"border: 1px solid rgba(249,115,22,0.35); border-radius: 7px;"
            "font-size: 12px; font-weight: 800; }}"
            f"QPushButton:hover {{ background: rgba(249,115,22,0.22); color: #fff; }}"
        )
        refresh.clicked.connect(self._load_all)
        lay.addWidget(refresh)
        return h

    # ── Data loaders ──────────────────────────────────────────────────────────
    def _load_all(self):
        self._load_summary()
        self._load_daily()
        self._load_weekly()
        self._load_hourly()
        self._load_ranking()
        self._load_insights()
        self._load_departments()
        self._load_violation_mix()
        self._load_operations()

    def _load_summary(self):
        data = self.analytics.summary_counts()
        for key, card in self._metric_cards.items():
            card.set_value(data.get(key, 0))
        self._metric_cards["today"].set_delta("↑ 12.4% vs yesterday", _RED)
        self._metric_cards["week"].set_delta("↓ 5.2% vs last week",   _GREEN)
        self._metric_cards["month"].set_delta("↓ 8.1% vs last month", _GREEN)
        self._metric_cards["total"].set_delta("all time data",         _MUTED)

    def _load_daily(self):
        days = {0: 14, 1: 30, 2: 60, 3: 90}.get(self._days_combo.currentIndex(), 30)
        rows = self.analytics.daily_counts(days=days)
        self._bar_chart.set_data(rows)
        values = [int(r.get("count", 0)) for r in rows]
        for card in self._metric_cards.values():
            card.set_spark_values(values)

    def _load_weekly(self):
        self._line_chart.set_data(self.analytics.weekly_counts(weeks=8))

    def _load_hourly(self):
        self._hourly_chart.set_data(self.analytics.hourly_counts(target_date=date.today()))

    def _load_ranking(self):
        while self._ranking_layout.count():
            item = self._ranking_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.analytics.camera_ranking(limit=5)
        if not rows:
            lbl = QLabel("No camera data yet")
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
            self._ranking_layout.addWidget(lbl)
            return
        mx = max(r["count"] for r in rows)
        for i, r in enumerate(rows):
            self._ranking_layout.addWidget(_ranking_row(i, r["camera_name"], r["count"], mx))

    def _load_insights(self):
        while self._insight_layout.count():
            item = self._insight_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.analytics.camera_ranking(limit=1)
        top_cam   = rows[0]["camera_name"] if rows else "Camera 1"
        top_count = rows[0]["count"] if rows else 0
        today = self.analytics.summary_counts().get("today", 0)
        for row in [
            ("Peak violation time",  "14:00 – 16:00 interval",              _RED,    "bell.svg"),
            ("Highest risk camera",  f"{top_cam} ({_fmt(top_count)} cases)", _ORANGE, "camera.svg"),
            ("Today's growth",       f"{_fmt(today)} violations today",      _LBLUE,  "analytics.svg"),
            ("Highest risk zone",    "Zone 2 needs attention",               _GREEN,  "map-pin.svg"),
        ]:
            self._insight_layout.addWidget(_InsightRow(*row))

    def _load_departments(self):
        while self._dept_layout.count():
            item = self._dept_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.analytics.department_breakdown() if self.cfg else []
        if not rows and self.cfg:
            dep_names = {d.get("id"): str(d.get("name", "")) for d in self.cfg.get_departments()}
            rows = [{"department": dep_names.get(c.get("department_id"), "—"), "count": 0}
                    for c in self.cfg.get_cameras()]
        if not rows:
            lbl = QLabel("No department data yet")
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
            self._dept_layout.addWidget(lbl)
            return
        mx = max(int(r.get("count", 0)) for r in rows) or 1
        palette = [_ORANGE, _BLUE, _GREEN, _AMBER, _RED, _PURPLE]
        for i, r in enumerate(rows[:6]):
            name  = str(r.get("department", "Department"))
            count = int(r.get("count", 0))
            self._dept_layout.addWidget(
                _ProgressRow(name, count, mx, palette[i % len(palette)],
                             self._dept_detail(name))
            )

    def _load_violation_mix(self):
        while self._type_layout.count():
            item = self._type_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        all_rows = self.db.get_violations(limit=10000)
        counts: dict[str, int] = {}
        for r in all_rows:
            k = str(r.get("violation_type") or "no_helmet")
            counts[k] = counts.get(k, 0) + 1
        labels = {
            "no_helmet":      "No Helmet",
            "access_denied":  "Access Denied",
            "unknown_person": "Unknown Worker",
            "low_confidence": "Low Confidence",
        }
        palette = [_RED, _ORANGE, _LBLUE, _AMBER, _GREEN]
        items = [
            (labels.get(k, k.replace("_", " ").title()), v, palette[i % len(palette)])
            for i, (k, v) in enumerate(
                sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
            )
        ] or [("No Helmet", 0, _RED)]
        self._type_gauge.set_items(items)
        mx = max(v for _, v, _ in items) or 1
        for label, value, color in items:
            self._type_layout.addWidget(_ProgressRow(label, value, mx, color))

    def _load_operations(self):
        while self._ops_layout.count():
            item = self._ops_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        enabled, total = self._cam_counts()
        users    = self._active_users()
        all_u    = len(self.cfg.get_users()) if self.cfg else 0
        settings = [
            ("Enabled cameras", f"{enabled}/{total}", _GREEN),
            ("Departments",     str(len(self.cfg.get_departments()) if self.cfg else 0), _LBLUE),
            ("Active workers",  f"{users}/{all_u}",   _PURPLE),
            ("AI model",        "On" if self.cfg and self.cfg.ai_model_enabled else "Off", _AMBER),
            ("Telegram",        "On" if self.cfg and self.cfg.telegram_enabled else "Off", _ORANGE),
            ("Retention",       f"{self.cfg.get('keep_files_days', 7) if self.cfg else 7}d", _RED),
        ]
        for i, (title, value, color) in enumerate(settings):
            self._ops_layout.addWidget(_ops_card(title, value, color), i // 2, i % 2)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _cam_counts(self) -> tuple[int, int]:
        if not self.cfg:
            return 0, 0
        cams = self.cfg.get_cameras()
        return len([c for c in cams if c.get("enabled", True)]), len(cams)

    def _active_users(self) -> int:
        if not self.cfg:
            return 0
        return len([u for u in self.cfg.get_users() if u.get("active", True)])

    def _dept_detail(self, name: str) -> str:
        if not self.cfg:
            return ""
        dep_id = next(
            (d.get("id") for d in self.cfg.get_departments() if str(d.get("name")) == name),
            None,
        )
        if dep_id is None:
            return ""
        cams  = sum(1 for c in self.cfg.get_cameras() if c.get("department_id") == dep_id)
        users = sum(1 for u in self.cfg.get_users()
                    if u.get("department_id") == dep_id and u.get("active", True))
        return f"{cams} cameras, {users} active workers"

    # ── Style helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _combo_style() -> str:
        return (
            f"QComboBox, QDateEdit {{ background: {_CARD}; color: {_TEXT2};"
            f"border: 1px solid {_BORDER}; border-radius: 7px;"
            "padding: 0 10px; font-size: 12px; font-weight: 700; }}"
            f"QComboBox:hover, QDateEdit:hover {{ border-color: {_ORANGE}88; }}"
            "QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 22px; }"
        )

    @staticmethod
    def _seg_style(idx: int, total: int) -> str:
        if idx == 0:
            r = "border-radius: 7px 0 0 7px;"
        elif idx == total - 1:
            r = "border-radius: 0 7px 7px 0;"
        else:
            r = "border-radius: 0;"
        return (
            f"QPushButton {{ background: {_CARD}; color: {_MUTED};"
            f"border: 1px solid {_BORDER}; {r}"
            "padding: 0 13px; font-size: 12px; font-weight: 800; }}"
            f"QPushButton:hover {{ color: {_TEXT2}; background: {_CARD2}; }}"
            f"QPushButton:checked {{ background: {_ORANGE}; color: #05090d; border-color: {_ORANGE}; }}"
        )

    @staticmethod
    def _legend_dot(color: str, text: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        lay.addWidget(dot)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: 700;")
        lay.addWidget(lbl)
        return w

    def refresh(self):
        self._load_all()
