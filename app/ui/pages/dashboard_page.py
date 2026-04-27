"""
DashboardPage — SmartHelmet asosiy boshqaruv paneli.
Layout: Chap sidebar (kamera ro'yxati + tizim holati) | O'ng: jonli monitoring.
"""

import datetime
import random

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QGridLayout, QSizePolicy,
    QProgressBar, QComboBox, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QDateTime
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient

from app.ui.theme import C
from app.ui.widgets.camera_panel import CameraPanel
from app.ui.widgets.violation_card import ViolationCard, ViolationDetailDialog


# ─────────────────────────────────────────────────────────────────────────────
#  Yordamchi kichik widgetlar
# ─────────────────────────────────────────────────────────────────────────────

class MiniSparkline(QWidget):
    """Kichik chiziqli grafik (sparkline)."""

    def __init__(self, color: str = "#3fb950", parent=None):
        super().__init__(parent)
        self._color  = QColor(color)
        self._data: list[float] = [random.uniform(0.3, 1.0) for _ in range(20)]
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")

    def set_data(self, values: list[float]):
        self._data = values or [0.0]
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        mn, mx = min(self._data), max(self._data)
        rng = mx - mn if mx != mn else 1.0

        pts = []
        for i, v in enumerate(self._data):
            x = i * w / max(len(self._data) - 1, 1)
            y = h - (v - mn) / rng * (h - 4) - 2
            pts.append((x, y))

        pen = QPen(self._color, 1.5)
        p.setPen(pen)
        for i in range(1, len(pts)):
            p.drawLine(int(pts[i-1][0]), int(pts[i-1][1]),
                       int(pts[i][0]),   int(pts[i][1]))
        p.end()


class CameraListItem(QWidget):
    """Sidebar kamera ro'yxati elementi."""

    clicked = pyqtSignal(int)

    def __init__(self, cam_id: int, cam_name: str, is_active: bool = False,
                 parent=None):
        super().__init__(parent)
        self.cam_id = cam_id
        self._status = "connecting"
        self._active = is_active
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")
        self._setup_ui(cam_name)

    def _setup_ui(self, cam_name: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)
        lay.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(12)
        self._dot.setStyleSheet(
            f"color: {C('cam_idle')}; font-size: 9px; background: transparent;"
        )
        lay.addWidget(self._dot)

        name_col = QVBoxLayout()
        name_col.setSpacing(1)

        self._name_lbl = QLabel(f"{self.cam_id:02d} {cam_name}")
        self._name_lbl.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 12px; background: transparent;"
        )
        name_col.addWidget(self._name_lbl)

        self._status_lbl = QLabel("Ulanmoqda")
        self._status_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        name_col.addWidget(self._status_lbl)
        lay.addLayout(name_col, 1)

        menu_btn = QLabel("⋮")
        menu_btn.setFixedWidth(18)
        menu_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        menu_btn.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 14px; background: transparent;"
        )
        lay.addWidget(menu_btn)

    def set_status(self, status: str):
        """status: 'live' | 'offline' | 'connecting' | 'error'"""
        self._status = status
        if status == "live":
            self._dot.setStyleSheet(
                f"color: {C('success')}; font-size: 9px; background: transparent;"
            )
            self._status_lbl.setText("Live")
            self._status_lbl.setStyleSheet(
                f"color: {C('success')}; font-size: 10px; background: transparent;"
            )
        elif status == "offline" or status == "error":
            self._dot.setStyleSheet(
                f"color: {C('cam_idle')}; font-size: 9px; background: transparent;"
            )
            self._status_lbl.setText("Offline")
            self._status_lbl.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
            )
        else:
            self._dot.setStyleSheet(
                f"color: {C('warning')}; font-size: 9px; background: transparent;"
            )
            self._status_lbl.setText("Ulanmoqda")
            self._status_lbl.setStyleSheet(
                f"color: {C('warning')}; font-size: 10px; background: transparent;"
            )

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)

    def enterEvent(self, event):
        self.setStyleSheet(f"background: {C('bg_hover')}; border-radius: 6px;")

    def leaveEvent(self, event):
        self.setStyleSheet("background: transparent;")


class AIBrainWidget(QWidget):
    """AI animatsiya — aylanuvchi halqa bilan AI logotipi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(68, 68)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def _tick(self):
        self._angle = (self._angle + 3) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = self.width() // 2, self.height() // 2, 27

        # Outer glow ring
        pen = QPen(QColor("#1a3a5a"), 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Animated arc
        pen2 = QPen(QColor("#58a6ff"), 2)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen2)
        p.drawArc(cx - r, cy - r, r * 2, r * 2,
                  (self._angle * 16), 100 * 16)

        # Inner circle
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#0d2a4a")))
        p.drawEllipse(cx - r + 6, cy - r + 6, (r - 6) * 2, (r - 6) * 2)

        # "AI" text
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QPen(QColor("#58a6ff")))
        p.drawText(cx - 10, cy + 5, "AI")
        p.end()


class SystemStatusBar(QWidget):
    """Tizim holati progress bar elementi."""

    def __init__(self, icon: str, label: str, value: int, color: str,
                 parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(3)

        row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent;"
        )
        icon_lbl.setFixedWidth(18)
        row.addWidget(icon_lbl)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 11px; background: transparent;"
        )
        row.addWidget(name_lbl, 1)

        self._val_lbl = QLabel(f"{value}%")
        self._val_lbl.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px; font-weight: bold;"
            " background: transparent;"
        )
        row.addWidget(self._val_lbl)
        lay.addLayout(row)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(value)
        self._bar.setFixedHeight(5)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C('bg_panel')};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 3px;
            }}
        """)
        lay.addWidget(self._bar)

    def set_value(self, v: int):
        self._val_lbl.setText(f"{v}%")
        self._bar.setValue(v)


class TimelineWidget(QWidget):
    """Vaqt chizig'i — sana + vaqt ko'rsatgich + kichik thumbnail qatorlar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        self.setStyleSheet(
            f"background: {C('bg_card')};"
            f"border-top: 1px solid {C('border')};"
        )
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_time)
        self._timer.start(1000)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 6)
        root.setSpacing(4)

        # Yuqori qator: sana + vaqt chizig'i
        top = QHBoxLayout()

        date_str = QDateTime.currentDateTime().toString("dd.MM.yyyy")
        self._date_lbl = QLabel(f"→  {date_str}  ■")
        self._date_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 11px; background: transparent;"
        )
        top.addWidget(self._date_lbl)
        top.addStretch()

        self._time_lbl = QLabel(datetime.datetime.now().strftime("%H:%M:%S"))
        self._time_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 12px; font-weight: bold;"
            " background: transparent;"
        )
        top.addWidget(self._time_lbl)
        root.addLayout(top)

        # Vaqt chizig'i
        tl_row = QHBoxLayout()
        tl_row.setSpacing(0)

        prev_btn = QLabel("◀")
        prev_btn.setFixedWidth(20)
        prev_btn.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        tl_row.addWidget(prev_btn)

        self._timeline_bar = _TimelineBar()
        tl_row.addWidget(self._timeline_bar, 1)

        next_btn = QLabel("▶")
        next_btn.setFixedWidth(20)
        next_btn.setAlignment(Qt.AlignmentFlag.AlignRight)
        next_btn.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        tl_row.addWidget(next_btn)
        root.addLayout(tl_row)

    def _update_time(self):
        now = datetime.datetime.now()
        self._time_lbl.setText(now.strftime("%H:%M:%S"))
        self._date_lbl.setText(f"→  {now.strftime('%d.%m.%Y')}  ■")
        self._timeline_bar.update()


class _TimelineBar(QWidget):
    """Vaqt chizig'i chizuvchi widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        now = datetime.datetime.now()
        current_min = now.hour * 60 + now.minute

        # 3 soatlik oyna: hozirgi vaqtdan 1.5 soat oldin va keyin
        window_min = 90
        start_min = current_min - window_min
        total_span = window_min * 2

        # Placeholder thumbnail qutilari
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(C('bg_panel'))))
        thumb_w = 38
        thumb_h = 28
        cols = w // (thumb_w + 4)
        for i in range(int(cols)):
            x = i * (thumb_w + 4)
            p.drawRoundedRect(x, 2, thumb_w, thumb_h, 3, 3)

        # Vaqt belgilari
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        p.setPen(QPen(QColor(C('text_muted'))))

        # Har 15 daqiqada belgi
        for delta in range(-90, 91, 15):
            t = start_min + window_min + delta
            x = int((delta + window_min) / total_span * w)
            hh = (t // 60) % 24
            mm = t % 60
            label = f"{hh:02d}:{mm:02d}"
            p.drawText(x - 16, h - 2, label)
            p.setPen(QPen(QColor(C('border'))))
            p.drawLine(x, 32, x, 38)
            p.setPen(QPen(QColor(C('text_muted'))))

        # Joriy vaqt ko'rsatgich (to'q sariq chiziq)
        cx = w // 2
        p.setPen(QPen(QColor(C('accent')), 2))
        p.drawLine(cx, 0, cx, 34)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  Asosiy DashboardPage
# ─────────────────────────────────────────────────────────────────────────────

class DashboardPage(QWidget):
    """Asosiy dashboard sahifasi — SmartHelmet dizayni."""

    go_violations = pyqtSignal()

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        self.db  = db
        self.cfg = config_manager

        self._panels: dict[int, CameraPanel]      = {}
        self._cam_items: dict[int, CameraListItem] = {}
        self._today_per_cam: dict[int, int]        = {}
        self._recent_violations: list              = []
        self._recent_persons: list                 = []
        self._max_recent = 10
        self._online_count = 0
        self._total_count  = 0
        self._prev_net   = None
        self._prev_net_t = None

        self._setup_ui()
        self._refresh_stats()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_stats)
        self._refresh_timer.start(30_000)

        self._sys_timer = QTimer(self)
        self._sys_timer.timeout.connect(self._update_sys_status)
        self._sys_timer.start(3_000)

    # ── Ana UI ───────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Chap sidebar
        root.addWidget(self._build_left_sidebar())

        # O'ng tomon separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {C('border')};")
        root.addWidget(sep)

        # Asosiy kontent
        root.addWidget(self._build_main_content(), 1)

    # ════════════════════════════════════════════════════════════════════════
    #  CHAP SIDEBAR
    # ════════════════════════════════════════════════════════════════════════

    def _build_left_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(235)
        sidebar.setStyleSheet(f"background: {C('bg_sidebar')};")

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Sarlavha ─────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(
            f"background: {C('bg_sidebar')};"
            f"border-bottom: 1px solid {C('border')};"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(14, 0, 8, 0)
        hdr_lay.setSpacing(0)

        cam_title = QLabel("CAMERAS")
        cam_title.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; font-weight: bold;"
            " letter-spacing: 1px; background: transparent;"
        )
        hdr_lay.addWidget(cam_title, 1)

        add_btn = QPushButton("+ Add Camera")
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('accent_dim')};
                color: {C('accent')};
                border: 1px solid {C('accent_dim')};
                border-radius: 5px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {C('accent')};
                color: white;
            }}
        """)
        hdr_lay.addWidget(add_btn)
        lay.addWidget(hdr)

        # ── "All Cameras" elementi ────────────────────────────────────────
        all_cam = QWidget()
        all_cam.setFixedHeight(38)
        all_cam.setStyleSheet("background: transparent;")
        all_lay = QHBoxLayout(all_cam)
        all_lay.setContentsMargins(14, 0, 10, 0)
        all_lay.setSpacing(8)

        all_dot = QLabel("●")
        all_dot.setFixedWidth(14)
        all_dot.setStyleSheet(
            f"color: {C('accent')}; font-size: 10px; background: transparent;"
        )
        all_lay.addWidget(all_dot)

        all_lbl = QLabel("All Cameras")
        all_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 12px; font-weight: bold;"
            " background: transparent;"
        )
        all_lay.addWidget(all_lbl, 1)

        self._all_count_lbl = QLabel("0")
        self._all_count_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 12px; font-weight: bold;"
            f" background: {C('accent_dim')}; border-radius: 10px;"
            " padding: 0 7px; background: transparent;"
        )
        all_lay.addWidget(self._all_count_lbl)
        lay.addWidget(all_cam)

        # ── Kamera ro'yxati (scroll) ──────────────────────────────────────
        cam_scroll = QScrollArea()
        cam_scroll.setWidgetResizable(True)
        cam_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cam_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._cam_list_widget = QWidget()
        self._cam_list_widget.setStyleSheet("background: transparent;")
        self._cam_list_layout = QVBoxLayout(self._cam_list_widget)
        self._cam_list_layout.setContentsMargins(4, 4, 4, 4)
        self._cam_list_layout.setSpacing(2)
        self._cam_list_layout.addStretch()

        cam_scroll.setWidget(self._cam_list_widget)
        cam_scroll.setMaximumHeight(260)
        lay.addWidget(cam_scroll)

        # ── Tizim holati ──────────────────────────────────────────────────
        lay.addWidget(self._build_system_overview())
        lay.addStretch()

        return sidebar

    def _build_system_overview(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"background: {C('bg_sidebar')};"
            f"border-top: 1px solid {C('border')};"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # Sarlavha
        ov_title = QLabel("SYSTEM OVERVIEW")
        ov_title.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; font-weight: bold;"
            " letter-spacing: 1px; background: transparent;"
        )
        lay.addWidget(ov_title)

        # Total / Online / Offline
        counts_row = QHBoxLayout()
        counts_row.setSpacing(0)

        for key, label, color in [
            ("total",   "Total Cameras", C('text_primary')),
            ("online",  "Online",        C('accent')),
            ("offline", "Offline",       C('text_muted')),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            val = QLabel("—")
            val.setStyleSheet(
                f"color: {color}; font-size: 20px; font-weight: bold;"
                " background: transparent;"
            )
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(val)
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 9px; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl)
            counts_row.addLayout(col, 1)

            if key != "offline":
                sep_v = QFrame()
                sep_v.setFrameShape(QFrame.Shape.VLine)
                sep_v.setFixedHeight(30)
                sep_v.setStyleSheet(f"color: {C('border')};")
                counts_row.addWidget(sep_v)

            # Store references
            setattr(self, f"_ov_{key}", val)

        lay.addLayout(counts_row)

        # Bugungi aniqlanishlar
        lay.addWidget(self._stat_row(
            "Detections Today", "38", "+12%", C('success'),
            C('success'), "_det_today_lbl"
        ))
        self._det_sparkline = MiniSparkline(C('success'))
        lay.addWidget(self._det_sparkline)

        # Kask yo'q
        lay.addWidget(self._stat_row(
            "No Helmet Detections", "12", "+8%", C('danger'),
            C('danger'), "_no_helmet_lbl"
        ))
        self._no_helmet_sparkline = MiniSparkline(C('danger'))
        lay.addWidget(self._no_helmet_sparkline)

        # Recognition rate
        rate_row = QHBoxLayout()
        rate_lbl = QLabel("Recognition Rate")
        rate_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 11px; background: transparent;"
        )
        rate_row.addWidget(rate_lbl, 1)

        rate_val = QLabel("98.6%")
        rate_val.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px; font-weight: bold;"
            " background: transparent;"
        )
        rate_row.addWidget(rate_val)

        excellent = QLabel("+2.4% Excellent")
        excellent.setStyleSheet(
            f"color: {C('success')}; font-size: 10px; background: transparent;"
        )
        rate_row.addWidget(excellent)
        lay.addLayout(rate_row)

        rate_bar = QProgressBar()
        rate_bar.setRange(0, 100)
        rate_bar.setValue(99)
        rate_bar.setFixedHeight(5)
        rate_bar.setTextVisible(False)
        rate_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C('bg_panel')};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {C('success')};
                border-radius: 3px;
            }}
        """)
        lay.addWidget(rate_bar)

        return frame

    @staticmethod
    def _stat_row(title: str, value: str, delta: str,
                  val_color: str, delta_color: str,
                  attr_name: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 11px; background: transparent;"
        )
        lay.addWidget(title_lbl, 1)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"color: {val_color}; font-size: 14px; font-weight: bold;"
            " background: transparent;"
        )
        lay.addWidget(val_lbl)

        delta_lbl = QLabel(delta)
        delta_lbl.setStyleSheet(
            f"color: {delta_color}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(delta_lbl)
        return w

    # ════════════════════════════════════════════════════════════════════════
    #  O'NG ASOSIY KONTENT
    # ════════════════════════════════════════════════════════════════════════

    def _build_main_content(self) -> QWidget:
        main = QWidget()
        main.setStyleSheet(f"background: {C('bg_main')};")
        lay = QVBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_monitor_header())
        lay.addWidget(self._build_camera_grid_area(), 1)
        lay.addWidget(TimelineWidget())
        lay.addWidget(self._build_bottom_panels())

        return main

    def _build_monitor_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(
            f"background: {C('bg_sidebar')};"
            f"border-bottom: 1px solid {C('border')};"
        )
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        # Jonli monitoring sarlavhasi
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {C('success')}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(dot)

        title = QLabel("Live Monitoring")
        title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 15px; font-weight: bold;"
            " background: transparent;"
        )
        lay.addWidget(title)

        self._cam_count_badge = QLabel("● 0 Cameras")
        self._cam_count_badge.setStyleSheet(
            f"color: {C('success')}; font-size: 12px; background: transparent;"
        )
        lay.addWidget(self._cam_count_badge)
        lay.addStretch()

        # Grid tartibi tugmalari
        for icon, tip in [("⊞", "1x1"), ("⊞⊞", "2x2"), ("⊞⊞⊞", "3x3")]:
            btn = QPushButton(icon)
            btn.setFixedSize(32, 32)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C('bg_panel')};
                    color: {C('text_secondary')};
                    border: 1px solid {C('border')};
                    border-radius: 5px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {C('bg_hover')};
                    color: {C('text_primary')};
                }}
            """)
            lay.addWidget(btn)

        lay.addSpacing(8)

        # Stream tanlash
        stream_combo = QComboBox()
        stream_combo.addItems(["All Streams", "Main Building", "Secondary Area"])
        stream_combo.setFixedWidth(130)
        stream_combo.setFixedHeight(32)
        lay.addWidget(stream_combo)

        # Kengaytirish
        expand_btn = QPushButton("⤢")
        expand_btn.setFixedSize(32, 32)
        expand_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('bg_panel')};
                color: {C('text_secondary')};
                border: 1px solid {C('border')};
                border-radius: 5px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {C('bg_hover')};
                color: {C('text_primary')};
            }}
        """)
        lay.addWidget(expand_btn)

        return hdr

    def _build_camera_grid_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._cam_container = QWidget()
        self._cam_container.setStyleSheet(f"background: {C('bg_main')};")
        self._cam_grid = QGridLayout(self._cam_container)
        self._cam_grid.setSpacing(6)
        self._cam_grid.setContentsMargins(8, 8, 8, 8)

        scroll.setWidget(self._cam_container)
        return scroll

    def _build_bottom_panels(self) -> QWidget:
        bottom = QWidget()
        bottom.setFixedHeight(240)
        bottom.setStyleSheet(
            f"background: {C('bg_sidebar')};"
            f"border-top: 1px solid {C('border')};"
        )
        lay = QHBoxLayout(bottom)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        panels = [
            self._build_recent_events(),
            self._build_detected_people(),
            self._build_ai_detection(),
            self._build_system_status(),
        ]
        for i, panel in enumerate(panels):
            lay.addWidget(panel, [30, 25, 25, 20][i])
            if i < len(panels) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(f"color: {C('border')};")
                lay.addWidget(sep)

        return bottom

    # ── Recent Events ────────────────────────────────────────────────────

    def _build_recent_events(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        t = QLabel("Recent Events")
        t.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 12px; font-weight: bold;"
            " background: transparent;"
        )
        hdr.addWidget(t)
        hdr.addStretch()

        view_all = QPushButton("View All")
        view_all.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C('accent')};
                border: none;
                font-size: 11px;
                padding: 0;
            }}
            QPushButton:hover {{ color: {C('accent_hover')}; }}
        """)
        view_all.clicked.connect(self.go_violations)
        hdr.addWidget(view_all)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._events_widget = QWidget()
        self._events_widget.setStyleSheet("background: transparent;")
        self._events_layout = QVBoxLayout(self._events_widget)
        self._events_layout.setContentsMargins(0, 0, 0, 0)
        self._events_layout.setSpacing(3)
        self._events_layout.addStretch()

        scroll.setWidget(self._events_widget)
        lay.addWidget(scroll, 1)
        return w

    # ── Detected People ──────────────────────────────────────────────────

    def _build_detected_people(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        t = QLabel("Detected People")
        t.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 12px; font-weight: bold;"
            " background: transparent;"
        )
        hdr.addWidget(t)
        hdr.addStretch()
        view_all = QPushButton("View All")
        view_all.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C('accent')};
                border: none;
                font-size: 11px;
                padding: 0;
            }}
            QPushButton:hover {{ color: {C('accent_hover')}; }}
        """)
        view_all.clicked.connect(self.go_violations)
        hdr.addWidget(view_all)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._people_widget = QWidget()
        self._people_widget.setStyleSheet("background: transparent;")
        self._people_layout = QVBoxLayout(self._people_widget)
        self._people_layout.setContentsMargins(0, 0, 0, 0)
        self._people_layout.setSpacing(3)
        self._people_layout.addStretch()

        scroll.setWidget(self._people_widget)
        lay.addWidget(scroll, 1)
        return w

    # ── AI Detection ─────────────────────────────────────────────────────

    def _build_ai_detection(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(6)

        t = QLabel("AI Detection")
        t.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 12px; font-weight: bold;"
            " background: transparent;"
        )
        lay.addWidget(t)

        center = QWidget()
        center.setStyleSheet("background: transparent;")
        c_lay = QVBoxLayout(center)
        c_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_lay.setSpacing(6)

        brain = AIBrainWidget()
        c_lay.addWidget(brain, 0, Qt.AlignmentFlag.AlignCenter)

        active_lbl = QLabel("Active")
        active_lbl.setStyleSheet(
            f"color: {C('success')}; font-size: 14px; font-weight: bold;"
            " background: transparent;"
        )
        active_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_lay.addWidget(active_lbl)

        desc = QLabel("Smart detection is\nrunning smoothly.")
        desc.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 11px; background: transparent;"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_lay.addWidget(desc)

        analytics_btn = QPushButton("View Analytics")
        analytics_btn.setFixedHeight(28)
        analytics_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('bg_panel')};
                color: {C('text_primary')};
                border: 1px solid {C('border')};
                border-radius: 5px;
                font-size: 11px;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background: {C('bg_hover')};
                border-color: {C('accent')};
                color: {C('accent')};
            }}
        """)
        c_lay.addWidget(analytics_btn, 0, Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(center, 1)
        return w

    # ── System Status ────────────────────────────────────────────────────

    def _build_system_status(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(6)

        t = QLabel("System Status")
        t.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 12px; font-weight: bold;"
            " background: transparent;"
        )
        lay.addWidget(t)

        self._cpu_bar  = SystemStatusBar("⬤", "CPU Usage",    42, C('accent'))
        self._mem_bar  = SystemStatusBar("⬤", "Memory Usage", 58, "#bc8cff")
        self._disk_bar = SystemStatusBar("⬤", "Disk Usage",   72, C('info'))
        lay.addWidget(self._cpu_bar)
        lay.addWidget(self._mem_bar)
        lay.addWidget(self._disk_bar)

        # Network
        net_row = QHBoxLayout()
        net_icon = QLabel("⬤")
        net_icon.setStyleSheet(
            f"color: {C('success')}; font-size: 12px; background: transparent;"
        )
        net_icon.setFixedWidth(18)
        net_row.addWidget(net_icon)

        net_lbl = QLabel("Network")
        net_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 11px; background: transparent;"
        )
        net_row.addWidget(net_lbl, 1)

        self._net_val = QLabel("— Mbps")
        self._net_val.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px; font-weight: bold;"
            " background: transparent;"
        )
        net_row.addWidget(self._net_val)
        lay.addLayout(net_row)

        # Uptime
        self._uptime_lbl = QLabel("Uptime: —")
        self._uptime_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(self._uptime_lbl)
        lay.addStretch()
        return w

    # ════════════════════════════════════════════════════════════════════════
    #  KAMERA PANELLARI BOSHQARUVI
    # ════════════════════════════════════════════════════════════════════════

    def setup_cameras(self, cameras: list):
        # Eski panellarni tozalash
        for p in self._panels.values():
            p.deleteLater()
        self._panels.clear()
        self._cam_items.clear()
        self._today_per_cam.clear()

        while self._cam_grid.count():
            item = self._cam_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        while self._cam_list_layout.count():
            item = self._cam_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        n = len(cameras)
        self._total_count  = n
        self._online_count = 0
        self._ov_total.setText(str(n))
        self._all_count_lbl.setText(str(n))
        self._cam_count_badge.setText(f"● {n} Cameras")
        self._ov_online.setText("0")
        self._ov_offline.setText(str(n))

        if not cameras:
            no_lbl = QLabel("Faol kamera yo'q.\nSozlamalarda kamera qo'shing.")
            no_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 14px;")
            self._cam_grid.addWidget(no_lbl, 0, 0)
            self._cam_list_layout.addStretch()
            return

        cols = 1 if n == 1 else 2 if n <= 4 else 4

        for idx, cam in enumerate(cameras):
            cam_id = cam.get("id", idx + 1)
            cam_name = cam.get("name", f"Kamera {cam_id}")

            # Grid panel
            panel = CameraPanel(
                cam_id     = cam_id,
                cam_name   = cam_name,
                rtsp_url   = cam.get("rtsp_url", ""),
                company_id = cam.get("company_id", ""),
            )
            self._panels[cam_id] = panel
            self._today_per_cam[cam_id] = 0

            row = idx // cols
            col = idx % cols
            min_h = 400 if n == 1 else 220 if n <= 4 else 180
            panel.setMinimumHeight(min_h)
            self._cam_grid.addWidget(panel, row, col)

            # Sidebar elementi
            item = CameraListItem(cam_id, cam_name)
            self._cam_items[cam_id] = item
            self._cam_list_layout.addWidget(item)

        self._cam_list_layout.addStretch()

        for c in range(cols):
            self._cam_grid.setColumnStretch(c, 1)

    # ── Tashqi yangilanishlar (workerdan) ─────────────────────────────────

    def update_frame(self, cam_id: int, frame: np.ndarray):
        p = self._panels.get(cam_id)
        if p:
            p.set_frame(frame)

    def on_violation(self, data: dict):
        self._recent_violations.insert(0, data)
        if len(self._recent_violations) > self._max_recent:
            self._recent_violations.pop()
        self._rebuild_recent_events()
        self._rebuild_detected_people()
        self._refresh_stats()

    def on_stats(self, cam_id: int, stats: dict):
        p = self._panels.get(cam_id)
        if not p:
            return
        fps     = stats.get("fps", 0.0)
        persons = stats.get("active_persons", 0)
        today   = stats.get("today_count", 0)
        conn    = stats.get("connected", False)
        self._today_per_cam[cam_id] = today
        p.set_stats(fps, persons, today, conn)

        # Sidebar item statusini yangilash
        item = self._cam_items.get(cam_id)
        if item:
            item.set_status("live" if conn else "offline")

        # Online/offline hisoblagich
        self._recalc_online()

    def on_status(self, cam_id: int, text: str):
        pass

    def on_error(self, cam_id: int, msg: str):
        p = self._panels.get(cam_id)
        if p:
            p.set_error(msg)
        item = self._cam_items.get(cam_id)
        if item:
            item.set_status("error")
        self._recalc_online()

    def on_model_loaded(self, cam_id: int):
        p = self._panels.get(cam_id)
        if p:
            p.set_model_loading()

    def set_total_persons(self, count: int):
        pass

    # ── Ichki metodlar ────────────────────────────────────────────────────

    def _recalc_online(self):
        online = 0
        for cam_id, item in self._cam_items.items():
            if item._status == "live":
                online += 1
        self._online_count = online
        self._ov_online.setText(str(online))
        self._ov_offline.setText(str(self._total_count - online))

    def _refresh_stats(self):
        try:
            today = self.db.get_today_count()
            self._ov_total.setText(str(self._total_count))
        except Exception:
            pass

    def _rebuild_recent_events(self):
        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for v in self._recent_violations[:5]:
            row = self._event_row(v)
            self._events_layout.addWidget(row)

        self._events_layout.addStretch()

    def _event_row(self, v: dict) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "background: transparent;"
            f"border-bottom: 1px solid {C('border_light')};"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)

        has_helmet = v.get("has_helmet", False)
        icon = QLabel("✓" if has_helmet else "⚠")
        icon.setFixedSize(20, 20)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color = C('success') if has_helmet else C('danger')
        icon.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: bold;"
            f" background: {'#0f2a15' if has_helmet else '#3d1515'};"
            " border-radius: 10px;"
        )
        lay.addWidget(icon)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        title = "Helmet Detected" if has_helmet else "No Helmet Detected"
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px;"
            " background: transparent;"
        )
        info_col.addWidget(t_lbl)

        cam_name = v.get("camera_name", v.get("camera_id", ""))
        c_lbl = QLabel(f"Camera {cam_name}")
        c_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        info_col.addWidget(c_lbl)
        lay.addLayout(info_col, 1)

        ts = v.get("timestamp", "")
        if ts and len(ts) > 10:
            time_str = ts[11:19]
        else:
            time_str = datetime.datetime.now().strftime("%H:%M:%S")
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(time_lbl)
        return w

    def _rebuild_detected_people(self):
        while self._people_layout.count():
            item = self._people_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for v in self._recent_violations[:4]:
            row = self._person_row(v)
            self._people_layout.addWidget(row)

        self._people_layout.addStretch()

    def _person_row(self, v: dict) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "background: transparent;"
            f"border-bottom: 1px solid {C('border_light')};"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)

        # Avatar placeholder
        avatar = QLabel()
        avatar.setFixedSize(36, 36)
        avatar.setStyleSheet(
            f"background: {C('bg_panel')}; border-radius: 4px;"
            f" border: 1px solid {C('border')};"
        )
        lay.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(2)

        person_id = v.get("track_id", v.get("person_id", "—"))
        id_lbl = QLabel(f"ID: {person_id:04d}" if isinstance(person_id, int) else f"ID: {person_id}")
        id_lbl.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px; font-weight: bold;"
            " background: transparent;"
        )
        info.addWidget(id_lbl)

        has_helmet = v.get("has_helmet", False)
        badge = QLabel("● Helmet" if has_helmet else "● No Helmet")
        badge.setStyleSheet(
            f"color: {'#3fb950' if has_helmet else '#f85149'};"
            " font-size: 10px; background: transparent;"
        )
        info.addWidget(badge)
        lay.addLayout(info, 1)

        ts = v.get("timestamp", "")
        if ts and len(ts) > 10:
            time_str = ts[11:19]
        else:
            time_str = datetime.datetime.now().strftime("%H:%M:%S")
        t_lbl = QLabel(time_str)
        t_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(t_lbl)
        return w

    def _update_sys_status(self):
        try:
            import psutil, time as _time
            cpu  = int(psutil.cpu_percent(interval=None))
            mem  = int(psutil.virtual_memory().percent)
            try:
                disk = int(psutil.disk_usage('/').percent)
            except Exception:
                disk = int(psutil.disk_usage('C:\\').percent)
            net  = psutil.net_io_counters()
            now  = _time.monotonic()

            if self._prev_net is not None:
                dt = now - self._prev_net_t
                if dt > 0:
                    delta = (
                        (net.bytes_sent + net.bytes_recv)
                        - (self._prev_net.bytes_sent + self._prev_net.bytes_recv)
                    )
                    mbps = max(round(delta / 1_000_000 / dt, 1), 0.0)
                else:
                    mbps = 0.0
            else:
                mbps = 0.0
            self._prev_net   = net
            self._prev_net_t = now

            self._cpu_bar.set_value(cpu)
            self._mem_bar.set_value(mem)
            self._disk_bar.set_value(disk)
            self._net_val.setText(f"{mbps:.1f} Mbps")

            uptime_secs = int(_time.time() - psutil.boot_time())
            days  = uptime_secs // 86400
            hours = (uptime_secs % 86400) // 3600
            mins  = (uptime_secs % 3600) // 60
            self._uptime_lbl.setText(f"Uptime: {days}d {hours}h {mins}m")
        except Exception:
            pass
