from __future__ import annotations

import threading
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QDate, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
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
from app.ui.widgets.violation_card import EvidenceImage, ViolationDetailDialog

_ICON_DIR = Path(__file__).resolve().parents[3] / "images"
_PAGE_LIMIT = 120
_SVG_CACHE: dict[tuple[str, str, int], QPixmap] = {}

# ── Design tokens (self-contained) ────────────────────────────────────────────
_BG = _CARD = _CARD2 = _CARD3 = _BDR = _BSOFT = ""
_TEXT = _TEXT2 = _MUTED = ""
_RED = _ORANGE = _AMBER = _GREEN = _LBLUE = _TEAL = _CYAN = ""


def _refresh_theme_tokens() -> None:
    g = globals()
    g["_BG"] = C("bg_main")
    g["_CARD"] = C("bg_card")
    g["_CARD2"] = C("bg_panel")
    g["_CARD3"] = C("bg_panel_alt")
    g["_BDR"] = C("border_panel")
    g["_BSOFT"] = C("border_soft")
    g["_TEXT"] = C("text_primary")
    g["_TEXT2"] = C("text_secondary")
    g["_MUTED"] = C("text_muted")
    g["_RED"] = C("danger")
    g["_ORANGE"] = C("accent")
    g["_AMBER"] = C("warning")
    g["_GREEN"] = C("success")
    g["_LBLUE"] = C("text_link")
    g["_TEAL"] = C("info")
    g["_CYAN"] = C("info")


on_theme_change(_refresh_theme_tokens)


def _rgb(h: str) -> str:
    h = h.lstrip("#")
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"


def _svg_px(name: str, color: str, size: int = 16) -> QPixmap:
    key = (name, color, size)
    cached = _SVG_CACHE.get(key)
    if cached is not None:
        return QPixmap(cached)
    path = _ICON_DIR / name
    src = QPixmap(str(path)) if path.exists() else QPixmap()
    if src.isNull():
        return src
    src = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
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


def _icon_btn(name: str, color: str, size: int = 14) -> QIcon:
    px = _svg_px(name, color, size)
    return QIcon(px) if not px.isNull() else QIcon()


def _fmt(value) -> str:
    return f"{int(value or 0):,}"


def _time_text(value) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value).strftime("%H:%M:%S")
    return "--:--:--"


def _date_text(value) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value).strftime("%d.%m.%Y")
    return "-"


def _type_style(vtype: str) -> tuple[str, str, str]:
    return {
        "no_helmet":      ("NO HELMET",      _RED,    f"rgba({_rgb(_RED)},0.16)"),
        "access_denied":  ("ACCESS DENIED",  _ORANGE, f"rgba({_rgb(_ORANGE)},0.14)"),
        "unknown_person": ("UNKNOWN PERSON", _LBLUE,  f"rgba({_rgb(_LBLUE)},0.12)"),
        "low_confidence": ("LOW CONF.",      _AMBER,  f"rgba({_rgb(_AMBER)},0.14)"),
    }.get(str(vtype or "no_helmet"), ("NO HELMET", _RED, f"rgba({_rgb(_RED)},0.16)"))


# ── Proportional bar (QPainter-based) ─────────────────────────────────────────
class _Bar(QWidget):
    def __init__(self, value: int, max_value: int, color: str, parent=None):
        super().__init__(parent)
        self._v = value
        self._m = max(max_value, 1)
        self._c = color
        self.setFixedHeight(5)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        track = QPainterPath()
        track.addRoundedRect(0, 0, W, H, 2.5, 2.5)
        p.fillPath(track, QColor(15, 35, 60, 100))
        fw = max(6, int(W * self._v / self._m))
        fill = QPainterPath()
        fill.addRoundedRect(0, 0, fw, H, 2.5, 2.5)
        g = QLinearGradient(0, 0, W, 0)
        g.setColorAt(0, QColor(self._c))
        c2 = QColor(self._c)
        c2.setAlpha(90)
        g.setColorAt(1, c2)
        p.fillPath(fill, g)
        p.end()


# ── Evidence tile ─────────────────────────────────────────────────────────────
class _EvidenceTile(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        label, accent, badge_bg = _type_style(str(violation.get("violation_type") or "no_helmet"))
        rgb_a = _rgb(accent)
        self.setMinimumSize(240, 272)
        self.setStyleSheet(
            "QFrame {"
            f"background: {_CARD2};"
            f"border: 1px solid rgba({_rgb(_BDR)},0.30);"
            "border-radius: 10px;"
            "}"
            "QFrame:hover {"
            f"border: 1px solid rgba({rgb_a},0.55);"
            f"background: rgba({rgb_a},0.04);"
            "}"
            "QLabel { background: transparent; border: none; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 12)
        lay.setSpacing(0)

        # Image area
        img_wrap = QWidget()
        img_wrap.setObjectName("imgWrap")
        img_wrap.setStyleSheet(
            "QWidget#imgWrap { background: #030a14; border-radius: 9px 9px 0 0; border: none; }"
        )
        img_lay = QVBoxLayout(img_wrap)
        img_lay.setContentsMargins(0, 0, 0, 0)
        full_path = str(violation.get("full_path") or "")
        crop_path = str(violation.get("crop_path") or "")
        image = EvidenceImage(full_path or crop_path, "NO IMAGE", (240, 144))
        image.setStyleSheet("border-radius: 9px 9px 0 0;")
        img_lay.addWidget(image, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(img_wrap)

        # Badges row (overlays on image via spacing trick)
        meta_outer = QWidget()
        meta_outer.setStyleSheet("background: transparent; border: none;")
        meta_lay = QVBoxLayout(meta_outer)
        meta_lay.setContentsMargins(10, 8, 10, 0)
        meta_lay.setSpacing(6)

        top = QHBoxLayout()
        badge = QLabel(label)
        badge.setStyleSheet(
            f"color: {accent}; background: {badge_bg};"
            f"border: 1px solid rgba({rgb_a},0.35);"
            "border-radius: 5px; padding: 3px 8px; font-size: 9px; font-weight: 900;"
            "letter-spacing: 0.8px;"
        )
        top.addWidget(badge)
        top.addStretch()
        conf = float(violation.get("confidence", 0) or 0) * 100
        conf_lbl = QLabel(f"{conf:.0f}%")
        conf_lbl.setStyleSheet(
            f"color: {_TEXT2}; background: rgba({_rgb(_BDR)},0.45);"
            "border-radius: 5px; padding: 3px 8px; font-size: 10px; font-weight: 900;"
        )
        top.addWidget(conf_lbl)
        meta_lay.addLayout(top)

        camera = QLabel(str(violation.get("camera_name") or "Unknown camera"))
        camera.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: 900;")
        camera.setMaximumWidth(230)
        meta_lay.addWidget(camera)

        foot = QHBoxLayout()
        track_id = QLabel(f"ID {violation.get('track_id', '?')}")
        track_id.setStyleSheet(
            f"color: {_LBLUE}; background: rgba({_rgb(_LBLUE)},0.10);"
            "border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 900;"
        )
        foot.addWidget(track_id)
        foot.addStretch()
        ts = violation.get("timestamp")
        time_lbl = QLabel(f"{_date_text(ts)}  {_time_text(ts)}")
        time_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 700;")
        foot.addWidget(time_lbl)
        meta_lay.addLayout(foot)

        lay.addWidget(meta_outer)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.violation)
            event.accept()
            return
        super().mousePressEvent(event)


# ── Main page ─────────────────────────────────────────────────────────────────
class ViolationsPage(QWidget):
    _data_ready = pyqtSignal(list, str, dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.analytics = AnalyticsService(db)
        self._violations: list[dict] = []
        self._loading = False
        self._pending_reload = False
        self._camera_filter = "All Cameras"
        self._active_period_idx = 1
        self._summary_labels: dict[str, QLabel] = {}
        self._period_btns: list[QPushButton] = []
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._rebuild_grid)
        self._data_ready.connect(self._on_data_ready)
        self._setup_ui()
        self._load_violations()

    # ── Build ─────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setObjectName("reportsPage")
        self.setStyleSheet(f"QWidget#reportsPage {{ background: {_BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_kpi_row())
        root.addWidget(self._build_filter_bar())

        body_wrap = QWidget()
        body_wrap.setStyleSheet("background: transparent;")
        body = QHBoxLayout(body_wrap)
        body.setContentsMargins(14, 10, 14, 14)
        body.setSpacing(10)
        body.addWidget(self._build_board(), 1)
        body.addWidget(self._build_snapshot_panel())
        root.addWidget(body_wrap, 1)

    def _build_header(self) -> QWidget:
        h = QFrame()
        h.setObjectName("reportsHdr")
        h.setFixedHeight(72)
        h.setStyleSheet(
            "QFrame#reportsHdr {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {_CARD3},stop:0.6 {_CARD2},stop:1 {_CARD});"
            f"border-bottom: 1px solid rgba({_rgb(_RED)},0.20); }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(h)
        lay.setContentsMargins(0, 0, 20, 0)
        lay.setSpacing(10)

        bar = QWidget()
        bar.setFixedSize(4, 72)
        bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {_RED},stop:0.6 #9b1c2e,stop:1 transparent); border: none;"
        )
        lay.addWidget(bar)
        lay.addSpacing(12)

        tc = QVBoxLayout()
        tc.setSpacing(3)
        t = QLabel("Reports")
        t.setStyleSheet(f"color: {_TEXT}; font-size: 20px; font-weight: 900;")
        tc.addWidget(t)
        s = QLabel("Evidence board for reviewing helmet-safety violations")
        s.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: 600;")
        tc.addWidget(s)
        lay.addLayout(tc)
        lay.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color: {_MUTED}; background: rgba({_rgb(_BDR)},0.18);"
            "border-radius: 7px; padding: 4px 12px; font-size: 11px; font-weight: 700;"
        )
        lay.addWidget(self._status_lbl)
        return h

    def _build_kpi_row(self) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(14, 10, 14, 0)
        lay.setSpacing(10)
        for key, title, icon, accent in [
            ("today", "BUGUN",  "alerts.svg",    _RED),
            ("week",  "HAFTA",  "analytics.svg", _ORANGE),
            ("month", "OY",     "reports.svg",   _AMBER),
            ("total", "JAMI",   "database.svg",  _LBLUE),
        ]:
            self._summary_labels[key] = self._kpi_card(lay, title, icon, accent)
        return wrap

    def _kpi_card(self, parent_lay: QHBoxLayout, title: str, icon: str, accent: str) -> QLabel:
        rgb = _rgb(accent)
        card = QFrame()
        card.setMinimumHeight(88)
        card.setStyleSheet(
            "QFrame {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 rgba({rgb},0.10),stop:0.5 {_CARD},stop:1 {_CARD});"
            f"border: 1px solid rgba({rgb},0.24);"
            f"border-left: 4px solid {accent};"
            "border-radius: 10px; }"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        ico = QLabel()
        ico.setFixedSize(44, 44)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico.setStyleSheet(
            f"background: rgba({rgb},0.16); border: 1px solid rgba({rgb},0.38); border-radius: 12px;"
        )
        px = _svg_px(icon, accent, 20)
        if not px.isNull():
            ico.setPixmap(px)
        else:
            ico.setText("●")
            ico.setStyleSheet(ico.styleSheet() + f" color: {accent}; font-size: 18px;")
        lay.addWidget(ico)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(
            f"color: rgba({rgb},0.85); font-size: 9px; font-weight: 900; letter-spacing: 1.4px;"
        )
        col.addWidget(t)
        val = QLabel("0")
        val.setStyleSheet(f"color: {_TEXT}; font-size: 26px; font-weight: 900;")
        col.addWidget(val)
        lay.addLayout(col, 1)

        parent_lay.addWidget(card, 1)
        return val

    def _build_filter_bar(self) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        outer = QHBoxLayout(wrap)
        outer.setContentsMargins(14, 10, 14, 0)
        outer.setSpacing(8)

        # Period segment
        seg_wrap = QWidget()
        seg_wrap.setStyleSheet(
            f"QWidget {{ background: {_CARD}; border: 1px solid {_BSOFT}; border-radius: 8px; }}"
        )
        seg_lay = QHBoxLayout(seg_wrap)
        seg_lay.setContentsMargins(4, 4, 4, 4)
        seg_lay.setSpacing(3)
        for i, label in enumerate(["Today", "Week", "Month", "All"]):
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setMinimumWidth(68)
            btn.setCheckable(True)
            btn.setChecked(i == self._active_period_idx)
            btn.setStyleSheet(self._seg_btn_style(i == self._active_period_idx))
            btn.clicked.connect(lambda _, d=[0, 7, 30, -1][i], idx=i: self._quick_filter(d, idx))
            seg_lay.addWidget(btn)
            self._period_btns.append(btn)
        outer.addWidget(seg_wrap)

        # Separator
        outer.addWidget(self._vsep())

        # Date range
        from_lbl = QLabel("From")
        from_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 800;")
        outer.addWidget(from_lbl)
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("dd.MM.yyyy")
        self._date_from.setDate(QDate.currentDate().addDays(-7))
        self._date_from.setFixedSize(120, 34)
        self._date_from.setStyleSheet(self._input_style())
        outer.addWidget(self._date_from)

        to_lbl = QLabel("To")
        to_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 800;")
        outer.addWidget(to_lbl)
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("dd.MM.yyyy")
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setFixedSize(120, 34)
        self._date_to.setStyleSheet(self._input_style())
        outer.addWidget(self._date_to)

        outer.addWidget(self._vsep())

        # Camera filter
        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All Cameras")
        self._camera_combo.setMinimumWidth(160)
        self._camera_combo.setMaximumWidth(220)
        self._camera_combo.setFixedHeight(34)
        self._camera_combo.setStyleSheet(self._input_style())
        self._camera_combo.currentTextChanged.connect(self._on_camera_filter_changed)
        outer.addWidget(self._camera_combo, 1)
        outer.addStretch(1)

        apply_btn = QPushButton("  Apply")
        apply_btn.setFixedSize(86, 34)
        apply_btn.setIcon(_icon_btn("check.svg", C("text_on_accent"), 14))
        apply_btn.setIconSize(QSize(14, 14))
        apply_btn.setStyleSheet(
            f"QPushButton {{ background: {_ORANGE}; color: {C('text_on_accent')};"
            "border: none; border-radius: 8px; font-size: 12px; font-weight: 900; }}"
            f"QPushButton:hover {{ background: #ea6c10; }}"
        )
        apply_btn.clicked.connect(self._on_apply)
        outer.addWidget(apply_btn)

        refresh_btn = QPushButton("  Refresh")
        refresh_btn.setFixedSize(96, 34)
        refresh_btn.setIcon(_icon_btn("refresh.svg", _TEXT2, 13))
        refresh_btn.setIconSize(QSize(13, 13))
        refresh_btn.setStyleSheet(
            f"QPushButton {{ background: rgba({_rgb(_BDR)},0.20); color: {_TEXT2};"
            f"border: 1px solid rgba({_rgb(_BDR)},0.40); border-radius: 8px;"
            "font-size: 12px; font-weight: 800; }}"
            f"QPushButton:hover {{ background: rgba({_rgb(_BDR)},0.35); color: {_TEXT}; }}"
        )
        refresh_btn.clicked.connect(self._load_violations)
        outer.addWidget(refresh_btn)
        return wrap

    def _build_board(self) -> QFrame:
        board = QFrame()
        board.setObjectName("evidenceBoard")
        board.setStyleSheet(
            f"QFrame#evidenceBoard {{ background: {_CARD2};"
            f"border: 1px solid rgba({_rgb(_BDR)},0.22); border-radius: 10px; }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(board)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Board header
        hdr = QWidget()
        hdr.setObjectName("boardHdr")
        hdr.setFixedHeight(46)
        hdr.setStyleSheet(
            "QWidget#boardHdr {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 rgba({_rgb(_TEAL)},0.18),stop:0.5 rgba({_rgb(_TEAL)},0.05),stop:1 transparent);"
            f"border-bottom: 1px solid rgba({_rgb(_TEAL)},0.25);"
            "border-radius: 9px 9px 0 0; }"
            "QLabel { background: transparent; border: none; }"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 14, 0)
        hl.setSpacing(0)

        pill_wrap = QWidget()
        pill_wrap.setFixedSize(16, 46)
        pill_wrap.setStyleSheet("background: transparent; border: none;")
        pwl = QVBoxLayout(pill_wrap)
        pwl.setContentsMargins(5, 10, 5, 10)
        pwl.setSpacing(0)
        pill = QWidget()
        pill.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {_TEAL},stop:1 rgba({_rgb(_TEAL)},0.3));"
            "border-radius: 3px; border: none;"
        )
        pwl.addWidget(pill)
        hl.addWidget(pill_wrap)
        hl.addSpacing(4)

        board_title = QLabel("Evidence Board")
        board_title.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: 900;")
        hl.addWidget(board_title)
        hl.addStretch()

        self._count_badge = QLabel("0 items")
        self._count_badge.setStyleSheet(
            f"color: {_TEAL}; background: rgba({_rgb(_TEAL)},0.12);"
            f"border: 1px solid rgba({_rgb(_TEAL)},0.28);"
            "border-radius: 7px; padding: 3px 10px; font-size: 11px; font-weight: 900;"
        )
        hl.addWidget(self._count_badge)
        lay.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._grid_widget)
        lay.addWidget(scroll, 1)
        self._board = board
        return board

    def _build_snapshot_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("snapshotPanel")
        panel.setFixedWidth(310)
        panel.setStyleSheet(
            f"QFrame#snapshotPanel {{ background: {_CARD2};"
            f"border: 1px solid rgba({_rgb(_ORANGE)},0.18); border-radius: 10px; }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 14)
        lay.setSpacing(0)

        # Panel header
        hdr = QWidget()
        hdr.setObjectName("snapHdr")
        hdr.setFixedHeight(46)
        hdr.setStyleSheet(
            "QWidget#snapHdr {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 rgba({_rgb(_ORANGE)},0.20),stop:0.55 rgba({_rgb(_ORANGE)},0.05),stop:1 transparent);"
            f"border-bottom: 1px solid rgba({_rgb(_ORANGE)},0.25);"
            "border-radius: 9px 9px 0 0; }"
            "QLabel { background: transparent; border: none; }"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 12, 0)
        hl.setSpacing(0)

        pill_wrap = QWidget()
        pill_wrap.setFixedSize(16, 46)
        pill_wrap.setStyleSheet("background: transparent; border: none;")
        pwl = QVBoxLayout(pill_wrap)
        pwl.setContentsMargins(5, 10, 5, 10)
        pwl.setSpacing(0)
        pill = QWidget()
        pill.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {_ORANGE},stop:1 rgba({_rgb(_ORANGE)},0.3));"
            "border-radius: 3px; border: none;"
        )
        pwl.addWidget(pill)
        hl.addWidget(pill_wrap)
        hl.addSpacing(4)

        snap_title = QLabel("Snapshot")
        snap_title.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: 900;")
        hl.addWidget(snap_title)
        hl.addStretch()

        self._snapshot_range = QLabel("Week")
        self._snapshot_range.setStyleSheet(
            f"color: {_ORANGE}; background: rgba({_rgb(_ORANGE)},0.12);"
            f"border: 1px solid rgba({_rgb(_ORANGE)},0.28);"
            "border-radius: 7px; padding: 3px 10px; font-size: 10px; font-weight: 900;"
        )
        hl.addWidget(self._snapshot_range)
        lay.addWidget(hdr)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(14, 12, 14, 0)
        body_lay.setSpacing(8)

        self._insights_layout = QVBoxLayout()
        self._insights_layout.setSpacing(7)
        body_lay.addLayout(self._insights_layout)

        body_lay.addSpacing(6)
        body_lay.addWidget(self._section_label("TOP CAMERAS", "camera.svg", _LBLUE))
        self._camera_breakdown = QVBoxLayout()
        self._camera_breakdown.setSpacing(7)
        body_lay.addLayout(self._camera_breakdown)

        body_lay.addSpacing(6)
        body_lay.addWidget(self._section_label("ACTIONS", "shield-alert.svg", _MUTED))

        for text, icon, color, slot in [
            ("Export CSV",    "download.svg",      _GREEN,  self._export_csv),
            ("Open latest",   "external-link.svg", _LBLUE,  self._open_latest),
            ("Clear filters", "x.svg",             _MUTED,  lambda: self._quick_filter(7, 1)),
        ]:
            btn = self._action_btn(text, icon, color)
            if slot:
                btn.clicked.connect(slot)
            body_lay.addWidget(btn)

        body_lay.addStretch()
        lay.addWidget(body, 1)
        return panel

    # ── Style helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _seg_btn_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {_ORANGE}; color: {C('text_on_accent')};"
                "border: none; border-radius: 6px; font-size: 12px; font-weight: 900; }}"
            )
        return (
            f"QPushButton {{ background: transparent; color: {_MUTED};"
            "border: none; border-radius: 6px; font-size: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ color: {_TEXT2}; background: rgba({_rgb(_BDR)},0.25); }}"
        )

    @staticmethod
    def _input_style() -> str:
        border = f"rgba({_rgb(_BDR)},0.40)"
        return (
            f"QDateEdit {{ background: {_CARD}; color: {_TEXT2};"
            f"border: 1px solid {border}; border-radius: 7px;"
            "padding: 0 10px; font-size: 12px; font-weight: 700; }}"
            f"QDateEdit:hover {{ border-color: rgba({_rgb(_ORANGE)},0.45); }}"
            "QDateEdit::drop-down { border: none; width: 20px; }"
            f"QComboBox {{ background: {_CARD}; color: {_TEXT2};"
            f"border: 1px solid {border}; border-radius: 7px;"
            "padding: 0 10px; font-size: 12px; font-weight: 700; }}"
            f"QComboBox:hover {{ border-color: rgba({_rgb(_ORANGE)},0.45); }}"
            "QComboBox::drop-down { border: none; width: 20px; }"
        )

    @staticmethod
    def _vsep() -> QFrame:
        s = QFrame()
        s.setFixedSize(1, 28)
        s.setStyleSheet(f"background: rgba({_rgb(_BDR)},0.30); border: none;")
        return s

    @staticmethod
    def _section_label(text: str, icon: str, color: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        ico = QLabel()
        ico.setFixedSize(14, 14)
        px = _svg_px(icon, color, 12)
        if not px.isNull():
            ico.setPixmap(px)
        ico.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(ico)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {color}; font-size: 9px; font-weight: 900; letter-spacing: 1.2px;"
        )
        lay.addWidget(lbl)
        lay.addStretch()
        return w

    @staticmethod
    def _action_btn(text: str, icon: str, color: str) -> QPushButton:
        rgb = _rgb(color)
        btn = QPushButton(f"  {text}")
        btn.setFixedHeight(34)
        btn.setIcon(_icon_btn(icon, color, 14))
        btn.setIconSize(QSize(14, 14))
        btn.setStyleSheet(
            f"QPushButton {{ background: rgba({rgb},0.08); color: {color};"
            f"border: 1px solid rgba({rgb},0.22); border-radius: 8px;"
            "font-size: 12px; font-weight: 800; text-align: left; padding-left: 12px; }}"
            f"QPushButton:hover {{ background: rgba({rgb},0.16); border-color: rgba({rgb},0.45); }}"
        )
        return btn

    # ── Data ──────────────────────────────────────────────────────────────────
    def _load_violations(self):
        if self._loading:
            self._pending_reload = True
            return
        self._loading = True
        self._pending_reload = False
        self._status_lbl.setText("Refreshing...")
        if not self._violations:
            self._show_loading_state()

        d_from = self._date_from.date().toPyDate()
        d_to   = self._date_to.date().toPyDate()
        cam    = None if self._camera_filter == "All Cameras" else self._camera_filter

        def _bg():
            try:
                rows = self.db.get_violations(
                    date_from=d_from, date_to=d_to,
                    limit=_PAGE_LIMIT,
                    camera_name=cam,
                )
                camera_names = self.db.get_distinct_camera_names()
                summary = self.analytics.summary_counts(camera_name=cam)
                summary["_camera_names"] = camera_names
                status  = self.analytics.format_range_status(len(rows), d_from, d_to)
                self._data_ready.emit(rows, status, summary)
            except Exception as exc:
                self._data_ready.emit([], f"Xatolik: {exc}", {})

        threading.Thread(target=_bg, daemon=True, name="ViolationsLoad").start()

    def _on_apply(self):
        self._set_active_period(-1)
        self._load_violations()

    def _on_data_ready(self, violations: list, status_text: str, summary: dict):
        self._loading = False
        self._violations = violations
        self._status_lbl.setText(status_text)
        camera_names = summary.pop("_camera_names", [])
        self._update_summary(summary)
        self._sync_camera_filter_options(camera_names)
        self._rebuild_grid()
        self._update_insights()
        if self._pending_reload:
            QTimer.singleShot(300, self._load_violations)

    def _update_summary(self, summary: dict):
        for key, lbl in self._summary_labels.items():
            lbl.setText(_fmt(summary.get(key, 0)))

    def _sync_camera_filter_options(self, camera_names: list[str]):
        current = self._camera_filter
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        self._camera_combo.addItem("All Cameras")
        self._camera_combo.addItems(camera_names)
        idx = self._camera_combo.findText(current)
        self._camera_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._camera_combo.blockSignals(False)

    def _on_camera_filter_changed(self, text: str):
        self._camera_filter = text or "All Cameras"
        self._load_violations()

    def _quick_filter(self, days: int, btn_idx: int):
        self._set_active_period(btn_idx)
        today = date.today()
        d_from = today if days == 0 else (today - timedelta(days=days) if days > 0 else date(2000, 1, 1))
        self._date_from.setDate(QDate(d_from.year, d_from.month, d_from.day))
        self._date_to.setDate(QDate(today.year, today.month, today.day))
        self._load_violations()

    def _set_active_period(self, idx: int):
        self._active_period_idx = idx
        for i, btn in enumerate(self._period_btns):
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._seg_btn_style(i == idx))
        labels = {0: "Today", 1: "Week", 2: "Month", 3: "All"}
        if hasattr(self, "_snapshot_range"):
            self._snapshot_range.setText(labels.get(idx, "Custom"))

    # ── Grid ──────────────────────────────────────────────────────────────────
    def _show_loading_state(self):
        self._clear_grid()
        lbl = QLabel("Loading evidence board...")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 14px; font-weight: 700;")
        lbl.setMinimumHeight(260)
        self._grid.addWidget(lbl, 0, 0)

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_grid(self):
        self._clear_grid()
        n = len(self._violations)
        self._count_badge.setText(f"{n} items")
        if not n:
            lbl = QLabel("No violations found — try another date range or camera filter.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {_MUTED}; font-size: 13px; font-weight: 700;")
            lbl.setMinimumHeight(280)
            self._grid.addWidget(lbl, 0, 0)
            return
        w = self._grid_widget.width()
        cols = max(1, min(5, (w - 24) // 258)) if w > 50 else 3
        for idx, v in enumerate(self._violations):
            card = _EvidenceTile(v)
            card.clicked.connect(self._open_detail)
            self._grid.addWidget(card, idx // cols, idx % cols)

    # ── Snapshot panel data ───────────────────────────────────────────────────
    def _update_insights(self):
        # Clear layouts
        for layout in (self._insights_layout, self._camera_breakdown):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        cameras = Counter(str(v.get("camera_name") or "Unknown") for v in self._violations)
        types   = Counter(str(v.get("violation_type") or "no_helmet") for v in self._violations)
        avg_conf = 0.0
        if self._violations:
            avg_conf = (
                sum(float(v.get("confidence", 0) or 0) for v in self._violations)
                / len(self._violations) * 100
            )
        top_type = types.most_common(1)[0] if types else ("no_helmet", 0)
        type_label, _, _ = _type_style(top_type[0])

        for title, value, color in [
            ("Filtered Events",  _fmt(len(self._violations)), _CYAN),
            (f"Main Type",       f"{type_label} ({top_type[1]})", _RED),
            ("Avg. Confidence",  f"{avg_conf:.1f}%", _AMBER),
        ]:
            self._insights_layout.addWidget(self._insight_row(title, value, color))

        max_count = max((c for _, c in cameras.most_common(5)), default=1)
        cam_colors = [_ORANGE, _LBLUE, _AMBER, _GREEN, _RED]
        for i, (name, count) in enumerate(cameras.most_common(5)):
            self._camera_breakdown.addWidget(
                self._camera_row(name, count, max_count, cam_colors[i % len(cam_colors)])
            )

    @staticmethod
    def _insight_row(title: str, value: str, color: str) -> QFrame:
        rgb = _rgb(color)
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: rgba({rgb},0.07);"
            f"border: 1px solid rgba({rgb},0.20);"
            f"border-left: 3px solid {color}; border-radius: 8px; }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        val = QLabel(value)
        val.setWordWrap(True)
        val.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 900;")
        lay.addWidget(val)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 800;")
        lay.addWidget(lbl)
        return card

    @staticmethod
    def _camera_row(name: str, count: int, max_count: int, color: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none; QLabel { background: transparent; border: none; }")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        lbl = QLabel(name)
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11px; font-weight: 900;")
        top.addWidget(lbl, 1)
        val = QLabel(str(count))
        val.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 900;")
        top.addWidget(val)
        lay.addLayout(top)
        lay.addWidget(_Bar(count, max_count, color))
        return w

    def _export_csv(self):
        if not self._violations:
            self._status_lbl.setText("No data to export.")
            return
        import csv, os
        d_from = self._date_from.date().toPyDate()
        d_to   = self._date_to.date().toPyDate()
        default_name = f"violations_{d_from:%Y%m%d}_{d_to:%Y%m%d}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            os.path.join(os.path.expanduser("~"), "Desktop", default_name),
            "CSV files (*.csv)",
        )
        if not path:
            return
        fields = ["id", "timestamp", "camera_name", "violation_type",
                  "confidence", "track_id", "employee_name", "department_id"]
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for v in self._violations:
                    row = dict(v)
                    ts = row.get("timestamp")
                    if ts:
                        row["timestamp"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow(row)
            self._status_lbl.setText(f"Exported {len(self._violations)} rows → {os.path.basename(path)}")
        except Exception as exc:
            self._status_lbl.setText(f"Export failed: {exc}")

    def _open_detail(self, violation: dict):
        dlg = ViolationDetailDialog(violation, self)
        dlg.exec()

    def _open_latest(self):
        if self._violations:
            self._open_detail(self._violations[0])

    def add_new_violation(self, data: dict):
        if self._loading:
            self._pending_reload = True
        else:
            QTimer.singleShot(500, self._load_violations)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._loading:
            self._resize_timer.start(80)
