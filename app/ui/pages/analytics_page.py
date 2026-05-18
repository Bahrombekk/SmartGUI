"""
AnalyticsPage — fully functional: all filters wired, real deltas, real insights.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtCore import QDate, QPointF, QTimer, Qt, pyqtSignal
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.application.services.analytics_service import AnalyticsService
from app.ui.styles import C, on_theme_change
from app.ui.widgets.bar_chart import BarChart, HourlyBarChart, LineChart

_ICON_DIR = Path(__file__).resolve().parents[3] / "images"
_SVG_CACHE: dict[tuple[str, str, int], QPixmap] = {}


def _svg_pixmap(name: str, color: str, size: int = 16) -> QPixmap:
    key = (name, color, size)
    cached = _SVG_CACHE.get(key)
    if cached is not None:
        return QPixmap(cached)
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
    _SVG_CACHE[key] = QPixmap(result)
    return result


def _hex_rgb(h: str) -> str:
    h = h.lstrip("#")
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"


# ── Design tokens ──────────────────────────────────────────────────────────────
_BG = _CARD = _CARD2 = _CARD3 = _BORDER = _BSOFT = ""
_TEXT = _TEXT2 = _MUTED = ""
_RED = _ORANGE = _AMBER = _GREEN = _BLUE = _LBLUE = _PURPLE = _TEAL = ""


def _refresh_theme_tokens() -> None:
    g = globals()
    g["_BG"] = C("bg_main")
    g["_CARD"] = C("bg_card")
    g["_CARD2"] = C("bg_panel")
    g["_CARD3"] = C("bg_panel_alt")
    g["_BORDER"] = C("border_panel")
    g["_BSOFT"] = C("border_soft")
    g["_TEXT"] = C("text_primary")
    g["_TEXT2"] = C("text_secondary")
    g["_MUTED"] = C("text_muted")
    g["_RED"] = C("danger")
    g["_ORANGE"] = C("accent")
    g["_AMBER"] = C("warning")
    g["_GREEN"] = C("success")
    g["_BLUE"] = "#3b82f6"
    g["_LBLUE"] = C("text_link")
    g["_PURPLE"] = "#8b5cf6"
    g["_TEAL"] = C("info")


on_theme_change(_refresh_theme_tokens)


def _fmt(v) -> str:
    return f"{int(v or 0):,}"


# ── Sparkline ──────────────────────────────────────────────────────────────────
class _Sparkline(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._values: list[int] = [2, 8, 5, 12, 7, 16, 11, 20]
        self.setFixedSize(86, 44)

    def set_values(self, values: list[int]):
        self._values = values[-12:] or self._values
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 5, -2, -4)
        vals = self._values
        if not vals:
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
            g.setColorAt(0, QColor(self._color + "88"))
            g.setColorAt(1, QColor(self._color + "00"))
            p.fillPath(area, g)
            line = QPainterPath()
            line.moveTo(pts[0])
            for pt in pts[1:]:
                line.lineTo(pt)
            p.setPen(QPen(QColor(self._color), 2.0,
                         Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap,
                         Qt.PenJoinStyle.RoundJoin))
            p.drawPath(line)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._color))
            p.drawEllipse(pts[-1], 3.0, 3.0)
        p.end()


# ── KPI card ───────────────────────────────────────────────────────────────────
class _MetricCard(QFrame):
    def __init__(self, title: str, icon: str, accent: str, subtitle: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        rgb = _hex_rgb(accent)
        self.setMinimumHeight(118)
        self.setStyleSheet(
            "QFrame {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 rgba({rgb},0.10),stop:0.55 {_CARD},stop:1 {_CARD});"
            f"border: 1px solid rgba({rgb},0.26);"
            f"border-left: 4px solid {accent};"
            "border-radius: 10px; }"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 16, 16, 16)
        lay.setSpacing(16)

        ico = QLabel()
        ico.setFixedSize(54, 54)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico.setStyleSheet(
            f"background: rgba({rgb},0.16);"
            f"border: 1px solid rgba({rgb},0.42);"
            "border-radius: 14px;"
        )
        pix = _svg_pixmap(icon, accent, 24)
        if not pix.isNull():
            ico.setPixmap(pix)
        else:
            ico.setText("●")
            ico.setStyleSheet(ico.styleSheet() + f" color: {accent}; font-size: 22px; font-weight: 900;")
        lay.addWidget(ico)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(
            f"color: rgba({rgb},0.85); font-size: 9px; font-weight: 900;"
            "letter-spacing: 1.6px;"
        )
        col.addWidget(t)
        self._value_lbl = QLabel("0")
        self._value_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 30px; font-weight: 900;"
        )
        col.addWidget(self._value_lbl)
        self._delta_lbl = QLabel(subtitle)
        self._delta_lbl.setStyleSheet(
            f"color: {_MUTED}; font-size: 11px; font-weight: 700;"
        )
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


# ── Section card ───────────────────────────────────────────────────────────────
class _SectionCard(QFrame):
    def __init__(self, title: str, bar_color: str = _LBLUE, parent=None):
        super().__init__(parent)
        rgb = _hex_rgb(bar_color)
        self.setObjectName("analyticsSection")
        self.setStyleSheet(
            "QFrame#analyticsSection {"
            f"background: {_CARD2};"
            f"border: 1px solid rgba({rgb},0.20);"
            "border-radius: 10px; }"
            "QLabel { background: transparent; border: none; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("secHdr")
        hdr.setFixedHeight(46)
        hdr.setStyleSheet(
            "QWidget#secHdr {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 rgba({rgb},0.22),stop:0.55 rgba({rgb},0.06),stop:1 transparent);"
            f"border-bottom: 1px solid rgba({rgb},0.28);"
            "border-radius: 9px 9px 0 0; }"
            "QLabel { background: transparent; border: none; }"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 12, 0)
        hl.setSpacing(0)

        # left accent pill
        pill_wrap = QWidget()
        pill_wrap.setFixedSize(16, 46)
        pill_wrap.setStyleSheet("background: transparent; border: none;")
        pwl = QVBoxLayout(pill_wrap)
        pwl.setContentsMargins(5, 10, 5, 10)
        pwl.setSpacing(0)
        pill = QWidget()
        pill.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {bar_color},stop:1 rgba({rgb},0.4)); border-radius: 3px; border: none;"
        )
        pwl.addWidget(pill)
        hl.addWidget(pill_wrap)
        hl.addSpacing(4)

        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 13px; font-weight: 900; letter-spacing: 0.3px;"
        )
        hl.addWidget(lbl)
        hl.addStretch()
        self._hdr_row = hl
        root.addWidget(hdr)

        bw = QWidget()
        bw.setStyleSheet("background: transparent;")
        self._body = QVBoxLayout(bw)
        self._body.setContentsMargins(14, 12, 14, 14)
        self._body.setSpacing(8)
        root.addWidget(bw, 1)

    def add_header_widget(self, w: QWidget):
        self._hdr_row.addWidget(w)

    def add_body_widget(self, w: QWidget):
        self._body.addWidget(w)


# ── AI Insight row ─────────────────────────────────────────────────────────────
class _InsightRow(QFrame):
    def __init__(self, title: str, detail: str, accent: str, icon: str, parent=None):
        super().__init__(parent)
        rgb = _hex_rgb(accent)
        self.setMinimumHeight(60)
        self.setStyleSheet(
            "QFrame {"
            f"background: rgba({rgb},0.06);"
            f"border: 1px solid rgba({rgb},0.22);"
            f"border-left: 3px solid {accent};"
            "border-radius: 8px; }"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)

        badge = QLabel()
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: rgba({rgb},0.18);"
            f"border: 1px solid rgba({rgb},0.38); border-radius: 17px;"
        )
        pix = _svg_pixmap(icon, accent, 16)
        if not pix.isNull():
            badge.setPixmap(pix)
        else:
            badge.setText("●")
            badge.setStyleSheet(badge.styleSheet() + f" color: {accent}; font-size: 14px;")
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


# ── Proportional progress bar ──────────────────────────────────────────────────
class _ProportionalBar(QWidget):
    def __init__(self, value: int, max_value: int, color: str, parent=None):
        super().__init__(parent)
        self._value = value
        self._max = max(max_value, 1)
        self._color = color
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        track = QPainterPath()
        track.addRoundedRect(0, 0, W, H, 3, 3)
        p.fillPath(track, QColor(15, 35, 60, 120))
        fw = max(8, int(W * self._value / self._max))
        fill = QPainterPath()
        fill.addRoundedRect(0, 0, fw, H, 3, 3)
        g = QLinearGradient(0, 0, W, 0)
        g.setColorAt(0, QColor(self._color))
        c2 = QColor(self._color)
        c2.setAlpha(100)
        g.setColorAt(1, c2)
        p.fillPath(fill, g)
        p.end()


# ── Progress row ───────────────────────────────────────────────────────────────
class _ProgressRow(QFrame):
    def __init__(self, label: str, value: int, max_value: int,
                 color: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(5)

        top = QHBoxLayout()
        name = QLabel(label)
        name.setStyleSheet(f"color: {_TEXT}; font-size: 12px; font-weight: 800;")
        top.addWidget(name, 1)
        cnt = QLabel(_fmt(value))
        cnt.setAlignment(Qt.AlignmentFlag.AlignRight)
        cnt.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 900;")
        top.addWidget(cnt)
        lay.addLayout(top)

        lay.addWidget(_ProportionalBar(value, max_value, color))

        if detail:
            sub = QLabel(detail)
            sub.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 600;")
            lay.addWidget(sub)


# ── Donut gauge ────────────────────────────────────────────────────────────────
class _SplitGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, int, str]] = []
        self.setMinimumHeight(120)

    def set_items(self, items: list[tuple[str, int, str]]):
        self._items = items
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(v for _, v, _ in self._items) or 1
        cx, cy = self.width() // 2, self.height() // 2
        r = min(50, max(32, min(self.width(), self.height()) // 3))
        start = 90 * 16
        for _, value, color in self._items:
            span = -int(360 * 16 * value / total)
            p.setPen(QPen(QColor(color), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(cx - r, cy - r, r * 2, r * 2, start, span)
            start += span
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_CARD2))
        ir = r - 7
        p.drawEllipse(cx - ir, cy - ir, ir * 2, ir * 2)
        p.setPen(QColor(_TEXT))
        p.setFont(QFont("Segoe UI", 14, QFont.Weight.Black))
        p.drawText(cx - 38, cy - 15, 76, 24, Qt.AlignmentFlag.AlignCenter, _fmt(total))
        p.setPen(QColor(_MUTED))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(cx - 38, cy + 8, 76, 14, Qt.AlignmentFlag.AlignCenter, "events")
        p.end()


# ── Ranking row ────────────────────────────────────────────────────────────────
def _ranking_row(rank: int, name: str, count: int, max_count: int) -> QFrame:
    palette = [_RED, _ORANGE, _AMBER, _BLUE, _GREEN]
    color = palette[rank % len(palette)]
    rgb = _hex_rgb(color)
    w = QFrame()
    w.setStyleSheet(
        f"QFrame {{ background: rgba({rgb},0.06);"
        f"border: 1px solid rgba({rgb},0.20); border-radius: 8px; }}"
        "QLabel { background: transparent; border: none; }"
    )
    lay = QHBoxLayout(w)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(10)

    badge = QLabel(str(rank + 1))
    badge.setFixedSize(26, 26)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"color: {_BG}; background: {color};"
        "border-radius: 13px; font-weight: 900; font-size: 11px;"
    )
    lay.addWidget(badge)

    n = QLabel(name)
    n.setStyleSheet(f"color: {_TEXT}; font-size: 12px; font-weight: 800;")
    lay.addWidget(n, 1)

    lay.addWidget(_ProportionalBar(count, max_count, color))

    cv = QLabel(_fmt(count))
    cv.setMinimumWidth(52)
    cv.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    cv.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 900;")
    lay.addWidget(cv)
    return w


# ── Ops mini card ──────────────────────────────────────────────────────────────
def _ops_card(title: str, value: str, color: str) -> QFrame:
    rgb = _hex_rgb(color)
    card = QFrame()
    card.setMinimumHeight(70)
    card.setStyleSheet(
        "QFrame {"
        f"background: rgba({rgb},0.07);"
        f"border: 1px solid rgba({rgb},0.22);"
        f"border-bottom: 3px solid {color};"
        "border-radius: 8px; }"
        "QLabel { background: transparent; border: none; }"
    )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(1)
    v = QLabel(value)
    v.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 900;")
    lay.addWidget(v)
    t = QLabel(title)
    t.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 0.5px;")
    lay.addWidget(t)
    return card


# ── Main page ──────────────────────────────────────────────────────────────────
class AnalyticsPage(QWidget):
    go_cameras = pyqtSignal()

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

    # ── Build ──────────────────────────────────────────────────────────────────
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
        c.setContentsMargins(16, 16, 16, 20)
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

        # Row 1: daily chart | insights | ranking
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
            "border: none; font-size: 11px; font-weight: 800; text-align: right; }"
            "QPushButton:hover { color: #fb923c; }"
        )
        all_btn.clicked.connect(self.go_cameras)
        ranking.add_body_widget(all_btn)
        r1.addWidget(ranking, 3)
        c.addLayout(r1)

        # Row 2: weekly | hourly
        r2 = QHBoxLayout()
        r2.setSpacing(10)

        weekly = _SectionCard("Weekly Trend", _PURPLE)
        self._weekly_combo = QComboBox()
        self._weekly_combo.addItems(["8 weeks", "16 weeks"])
        self._weekly_combo.setFixedSize(96, 28)
        self._weekly_combo.setStyleSheet(self._combo_style())
        self._weekly_combo.currentIndexChanged.connect(self._load_weekly)
        weekly.add_header_widget(self._weekly_combo)
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
        h.setFixedHeight(76)
        h.setStyleSheet(
            "QFrame#analyticsHdr {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {_CARD3},stop:0.6 {_CARD2},stop:1 {_CARD});"
            f"border-bottom: 1px solid rgba({_hex_rgb(_ORANGE)},0.22); }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(h)
        lay.setContentsMargins(0, 0, 20, 0)
        lay.setSpacing(10)

        # Left accent bar
        bar = QWidget()
        bar.setFixedSize(4, 76)
        bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {_ORANGE},stop:0.6 #c2410c,stop:1 transparent); border: none;"
        )
        lay.addWidget(bar)
        lay.addSpacing(12)

        tc = QVBoxLayout()
        tc.setSpacing(3)
        t = QLabel("Analytics")
        t.setStyleSheet(f"color: {_TEXT}; font-size: 20px; font-weight: 900;")
        tc.addWidget(t)
        s = QLabel("Violation trends by time, camera and operational health")
        s.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: 600;")
        tc.addWidget(s)
        lay.addLayout(tc)
        lay.addStretch()

        # Department filter
        self._zone_combo = QComboBox()
        self._zone_combo.addItem("All Departments")
        if self.cfg:
            for d in self.cfg.get_departments():
                self._zone_combo.addItem(str(d.get("name", "")))
        self._zone_combo.setFixedSize(148, 34)
        self._zone_combo.setStyleSheet(self._combo_style())
        self._zone_combo.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(self._zone_combo)

        # Camera filter
        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All Cameras")
        if self.cfg:
            for cam in self.cfg.get_cameras():
                self._camera_combo.addItem(str(cam.get("name", "")))
        self._camera_combo.setFixedSize(148, 34)
        self._camera_combo.setStyleSheet(self._combo_style())
        self._camera_combo.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(self._camera_combo)

        # Custom date range (shown only when "Custom" is selected)
        self._custom_range_widget = QWidget()
        self._custom_range_widget.setStyleSheet("background: transparent;")
        cr_lay = QHBoxLayout(self._custom_range_widget)
        cr_lay.setContentsMargins(0, 0, 0, 0)
        cr_lay.setSpacing(4)
        self._date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self._date_from.setDisplayFormat("dd MMM yy")
        self._date_from.setCalendarPopup(True)
        self._date_from.setFixedSize(112, 34)
        self._date_from.setStyleSheet(self._combo_style())
        self._date_from.dateChanged.connect(self._on_filter_changed)
        sep = QLabel("→")
        sep.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        self._date_to = QDateEdit(QDate.currentDate())
        self._date_to.setDisplayFormat("dd MMM yy")
        self._date_to.setCalendarPopup(True)
        self._date_to.setFixedSize(112, 34)
        self._date_to.setStyleSheet(self._combo_style())
        self._date_to.dateChanged.connect(self._on_filter_changed)
        cr_lay.addWidget(self._date_from)
        cr_lay.addWidget(sep)
        cr_lay.addWidget(self._date_to)
        self._custom_range_widget.setVisible(False)
        lay.addWidget(self._custom_range_widget)

        # Period segment buttons
        seg = QWidget()
        seg.setStyleSheet("background: transparent;")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self._period_group = QButtonGroup(self)
        for idx, txt in enumerate(["Today", "Week", "Month", "Custom"]):
            btn = QPushButton(txt)
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.setStyleSheet(self._seg_style(idx, 4))
            if idx == 1:
                btn.setChecked(True)
            self._period_group.addButton(btn, idx)
            sl.addWidget(btn)
        self._period_group.buttonClicked.connect(self._on_period_clicked)
        lay.addWidget(seg)

        refresh = QPushButton("Refresh")
        refresh.setFixedSize(88, 34)
        refresh.setStyleSheet(
            f"QPushButton {{ background: rgba({_hex_rgb(_ORANGE)},0.14); color: {_ORANGE};"
            f"border: 1px solid rgba({_hex_rgb(_ORANGE)},0.38); border-radius: 7px;"
            "font-size: 12px; font-weight: 800; }"
            f"QPushButton:hover {{ background: rgba({_hex_rgb(_ORANGE)},0.26); color: #fff; }}"
        )
        refresh.clicked.connect(self._load_all)
        lay.addWidget(refresh)
        return h

    # ── Filter helpers ─────────────────────────────────────────────────────────
    def _on_period_clicked(self):
        is_custom = self._period_group.checkedId() == 3
        self._custom_range_widget.setVisible(is_custom)
        self._on_filter_changed()

    def _on_filter_changed(self):
        self._load_all()

    def _current_range(self) -> tuple[date, date]:
        today = date.today()
        btn_id = self._period_group.checkedId()
        if btn_id == 0:
            return today, today
        elif btn_id == 1:
            return today - timedelta(days=today.weekday()), today
        elif btn_id == 2:
            return date(today.year, today.month, 1), today
        else:
            d_from = self._date_from.date().toPyDate()
            d_to = self._date_to.date().toPyDate()
            return min(d_from, d_to), max(d_from, d_to)

    def _current_camera_name(self) -> str | None:
        idx = self._camera_combo.currentIndex()
        return None if idx == 0 else self._camera_combo.currentText()

    def _current_department_id(self) -> int | None:
        idx = self._zone_combo.currentIndex()
        if idx == 0 or not self.cfg:
            return None
        dept_name = self._zone_combo.currentText()
        for d in self.cfg.get_departments():
            if str(d.get("name", "")) == dept_name:
                return d.get("id")
        return None

    # ── Data loaders ───────────────────────────────────────────────────────────
    def _load_all(self):
        try:
            d_from, d_to = self._current_range()
            cam   = self._current_camera_name()
            dept  = self._current_department_id()
            self._load_summary(cam, dept)
            self._load_daily(cam, dept)
            self._load_weekly(cam, dept)
            self._load_hourly(cam, dept)
            self._load_ranking(d_from, d_to, cam, dept)
            self._load_insights(d_from, d_to, cam, dept)
            self._load_departments(d_from, d_to, cam, dept)
            self._load_violation_mix(d_from, d_to, cam, dept)
            self._load_operations()
        except Exception as exc:
            for card in self._metric_cards.values():
                card.set_delta(f"DB error: {str(exc)[:48]}", _RED)

    def _load_summary(self, camera_name=None, department_id=None):
        data = self.analytics.summary_with_delta(
            camera_name=camera_name, department_id=department_id
        )
        self._metric_cards["today"].set_value(data["today"])
        self._metric_cards["week"].set_value(data["week"])
        self._metric_cards["month"].set_value(data["month"])
        self._metric_cards["total"].set_value(data["total"])

        def _delta_text(pct: float | None, label: str) -> tuple[str, str]:
            if pct is None:
                return f"no prior {label} data", _MUTED
            arrow = "↑" if pct > 0 else "↓"
            color = _RED if pct > 0 else _GREEN
            return f"{arrow} {abs(pct):.1f}% {label}", color

        txt, col = _delta_text(data["today_delta"], "vs yesterday")
        self._metric_cards["today"].set_delta(txt, col)
        txt, col = _delta_text(data["week_delta"], "vs last week")
        self._metric_cards["week"].set_delta(txt, col)
        txt, col = _delta_text(data["month_delta"], "vs last month")
        self._metric_cards["month"].set_delta(txt, col)
        self._metric_cards["total"].set_delta("all time data", _MUTED)

    def _load_daily(self, camera_name=None, department_id=None):
        days = {0: 14, 1: 30, 2: 60, 3: 90}.get(self._days_combo.currentIndex(), 30)
        rows = self.analytics.daily_counts(
            days=days, camera_name=camera_name, department_id=department_id
        )
        self._bar_chart.set_data(rows)
        values = [int(r.get("count", 0)) for r in rows]
        for card in self._metric_cards.values():
            card.set_spark_values(values)

    def _load_weekly(self, camera_name=None, department_id=None):
        weeks = 16 if self._weekly_combo.currentIndex() == 1 else 8
        self._line_chart.set_data(
            self.analytics.weekly_counts(weeks=weeks, camera_name=camera_name, department_id=department_id)
        )

    def _load_hourly(self, camera_name=None, department_id=None):
        self._hourly_chart.set_data(
            self.analytics.hourly_counts(camera_name=camera_name, department_id=department_id)
        )

    def _load_ranking(self, date_from: date, date_to: date, camera_name=None, department_id=None):
        _clear_layout(self._ranking_layout)
        rows = self.analytics.camera_ranking(
            date_from=date_from, date_to=date_to, limit=5,
            camera_name=camera_name, department_id=department_id,
        )
        if not rows:
            lbl = QLabel("No camera data yet")
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
            self._ranking_layout.addWidget(lbl)
            return
        mx = max(r["count"] for r in rows)
        for i, r in enumerate(rows):
            self._ranking_layout.addWidget(_ranking_row(i, r["camera_name"], r["count"], mx))

    def _load_insights(self, date_from: date, date_to: date, camera_name=None, department_id=None):
        _clear_layout(self._insight_layout)
        ins = self.analytics.peak_insights(
            date_from=date_from, date_to=date_to,
            camera_name=camera_name, department_id=department_id,
        )
        peak_h = ins["peak_hour"]
        peak_label = f"{peak_h:02d}:00 – {peak_h+1:02d}:00 ({_fmt(ins['peak_hour_count'])} violations)"
        top_cam = f"{ins['top_camera']} ({_fmt(ins['top_camera_count'])} cases)"
        today_n = self.analytics.summary_counts(
            camera_name=camera_name, department_id=department_id
        ).get("today", 0)
        rows = [
            ("Peak violation time",  peak_label,              _RED,    "bell.svg"),
            ("Highest risk camera",  top_cam,                 _ORANGE, "camera.svg"),
            ("Today's violations",   f"{_fmt(today_n)} today", _LBLUE, "analytics.svg"),
            ("Highest risk zone",    ins["top_dept"],         _GREEN,  "map-pin.svg"),
        ]
        for row in rows:
            self._insight_layout.addWidget(_InsightRow(*row))

    def _load_departments(self, date_from: date, date_to: date, camera_name=None, department_id=None):
        _clear_layout(self._dept_layout)
        rows = self.analytics.department_breakdown(
            date_from=date_from, date_to=date_to,
            camera_name=camera_name, department_id=department_id,
        )
        if not rows and self.cfg:
            dep_names = {d.get("id"): str(d.get("name", "")) for d in self.cfg.get_departments()}
            rows = [
                {"department": dep_names.get(c.get("department_id"), "—"), "count": 0}
                for c in self.cfg.get_cameras()
            ]
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

    def _load_violation_mix(self, date_from: date, date_to: date, camera_name=None, department_id=None):
        _clear_layout(self._type_layout)
        items_raw = self.analytics.violation_type_breakdown(
            date_from=date_from, date_to=date_to,
            camera_name=camera_name, department_id=department_id,
        )
        palette = [_RED, _ORANGE, _LBLUE, _AMBER, _GREEN]
        items = [
            (r["label"], r["count"], palette[i % len(palette)])
            for i, r in enumerate(items_raw)
        ]
        self._type_gauge.set_items(items)
        mx = max(v for _, v, _ in items) or 1
        for label, value, color in items:
            self._type_layout.addWidget(_ProgressRow(label, value, mx, color))

    def _load_operations(self):
        _clear_layout(self._ops_layout)
        enabled, total = self._cam_counts()
        users = self._active_users()
        all_u = len(self.cfg.get_users()) if self.cfg else 0
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

    # ── Helpers ────────────────────────────────────────────────────────────────
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

    # ── Style helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _combo_style() -> str:
        return (
            f"QComboBox {{ background: {_CARD}; color: {_TEXT2};"
            f"border: 1px solid {_BORDER}; border-radius: 7px;"
            "padding: 0 10px; font-size: 12px; font-weight: 700; }"
            f"QComboBox:hover {{ border-color: rgba({_hex_rgb(_ORANGE)},0.55); }}"
            "QComboBox::drop-down { border: none; width: 22px; }"
            f"QDateEdit {{ background: {_CARD}; color: {_TEXT2};"
            f"border: 1px solid {_BORDER}; border-radius: 7px;"
            "padding: 0 10px; font-size: 12px; font-weight: 700; }"
            f"QDateEdit:hover {{ border-color: rgba({_hex_rgb(_ORANGE)},0.55); }}"
            "QDateEdit::drop-down { border: none; width: 22px; }"
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
            "padding: 0 14px; font-size: 12px; font-weight: 800; }"
            f"QPushButton:hover {{ color: {_TEXT2}; background: {_CARD2}; }}"
            f"QPushButton:checked {{ background: {_ORANGE}; color: {C('text_on_accent')};"
            f"border-color: {_ORANGE}; }}"
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


# ── Layout clear helper ────────────────────────────────────────────────────────
def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
