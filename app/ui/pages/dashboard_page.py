"""
DashboardPage — SmartHelmet asosiy boshqaruv paneli.
Layout: Chap sidebar (kamera ro'yxati + tizim holati) | O'ng: jonli monitoring.
"""

import datetime
import random
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QGridLayout, QSizePolicy,
    QProgressBar, QComboBox, QSpacerItem, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QIcon, QPixmap

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
        self.setFixedHeight(38)
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


class CameraTreeBranch(QWidget):
    """Compact tree connector for grouped camera rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(38)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#2b3d52"), 1))
        x = 16
        y_mid = self.height() // 2
        p.drawLine(x, 0, x, self.height())
        p.drawLine(x, y_mid, self.width() - 6, y_mid)
        p.end()


class CameraGroupChevron(QWidget):
    """Small painted chevron, wider than a text glyph."""

    def __init__(self, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self.setFixedSize(18, 18)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#e2e8f0"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self._expanded:
            p.drawLine(5, 7, 9, 12)
            p.drawLine(9, 12, 13, 7)
        else:
            p.drawLine(7, 5, 12, 9)
            p.drawLine(12, 9, 7, 13)
        p.end()


class CameraListItem(QWidget):
    """Sidebar kamera ro'yxati elementi."""

    clicked = pyqtSignal(int)

    def __init__(self, cam_id: int, cam_name: str, is_active: bool = False,
                 grouped: bool = False, parent=None):
        super().__init__(parent)
        self.cam_id = cam_id
        self._grouped = grouped
        self._status = "connecting"
        self._active = is_active
        self.setFixedHeight(56 if grouped else 48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")
        self._setup_ui(cam_name)

    def _setup_ui(self, cam_name: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(0)

        if self._grouped:
            lay.addWidget(CameraTreeBranch())

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent; border: none;")
        content_lay = QHBoxLayout(self._content)
        content_lay.setContentsMargins(10, 4, 10, 4)
        content_lay.setSpacing(10)
        lay.addWidget(self._content, 1)

        # Camera icon circle
        self._dot = QLabel("◉")
        self._dot.setFixedSize(20, 20)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = Path(__file__).resolve().parents[3] / "images" / "camera-small.svg"
        self._dot.setPixmap(QPixmap(str(icon_path)).scaled(
            15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        self._dot.setText("")
        self._dot.setStyleSheet("background: transparent; border: none;")
        content_lay.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignTop)

        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(1)

        self._name_lbl = QLabel(f"{self.cam_id:02d} {cam_name}")
        self._name_lbl.setStyleSheet(
            "color: #f8fafc; font-size: 13px; font-weight: 500; background: transparent; border: none;"
        )
        name_col.addWidget(self._name_lbl)

        self._status_lbl = QLabel("Ulanmoqda")
        self._status_lbl.setStyleSheet(
            "color: #64748b; font-size: 12px; background: transparent; border: none;"
        )
        name_col.addWidget(self._status_lbl)
        content_lay.addLayout(name_col, 1)

        self._menu_lbl = QLabel()
        self._menu_lbl.setFixedSize(20, 20)
        menu_path = Path(__file__).resolve().parents[3] / "images" / "more-vertical.svg"
        self._menu_lbl.setPixmap(QPixmap(str(menu_path)).scaled(
            15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        self._menu_lbl.setStyleSheet("background: transparent; border: none;")
        self._menu_lbl.setVisible(self._active)
        content_lay.addWidget(self._menu_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        self._apply_active_style()

    def set_status(self, status: str):
        """status: 'live' | 'offline' | 'connecting' | 'error'"""
        self._status = status
        if status == "live":
            self._dot.setStyleSheet(
                "color: #34d399; font-size: 11px; background: transparent; border: none;"
            )
            self._status_lbl.setText("Live")
            self._status_lbl.setStyleSheet(
                "color: #34d399; font-size: 12px; background: transparent; border: none;"
            )
        elif status == "offline" or status == "error":
            self._dot.setStyleSheet(
                "color: #64748b; font-size: 11px; background: transparent; border: none;"
            )
            self._status_lbl.setText("Offline")
            self._status_lbl.setStyleSheet(
                "color: #64748b; font-size: 12px; background: transparent; border: none;"
            )
        else:
            self._dot.setStyleSheet(
                "color: #fbbf24; font-size: 11px; background: transparent; border: none;"
            )
            self._status_lbl.setText("Ulanmoqda")
            self._status_lbl.setStyleSheet(
                "color: #fbbf24; font-size: 12px; background: transparent; border: none;"
            )

    def set_selected(self, selected: bool):
        self._active = selected
        self._menu_lbl.setVisible(selected)
        self._apply_active_style()

    def _apply_active_style(self):
        if self._active:
            self._content.setStyleSheet(
                "background: rgba(249,115,22,0.20); border: none; border-radius: 7px;"
            )
        else:
            self._content.setStyleSheet("background: transparent; border: none;")

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)

    def enterEvent(self, event):
        if not self._active:
            self._content.setStyleSheet(
                "background: rgba(30,41,59,0.45); border: none; border-radius: 7px;"
            )

    def leaveEvent(self, event):
        self._apply_active_style()


class CameraGroupHeader(QWidget):
    """Sidebar bo'lim sarlavhasi."""

    toggled = pyqtSignal(int)

    def __init__(self, dep_id: int, title: str, count: int, expanded: bool = True,
                 parent=None):
        super().__init__(parent)
        self.dep_id = dep_id
        self.expanded = expanded
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 8, 0)
        lay.setSpacing(8)

        arrow = QLabel("⌄" if expanded else "›")
        arrow.setText("v" if expanded else ">")
        arrow.setFixedWidth(18)
        arrow.setStyleSheet(
            "color: #e2e8f0; font-size: 12px; background: transparent; border: none;"
        )
        arrow = CameraGroupChevron(expanded)
        lay.addWidget(arrow)

        name = QLabel(title)
        name.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )
        lay.addWidget(name, 1)

        badge = QLabel(str(count))
        badge.setStyleSheet(
            "color: #64748b; font-size: 10px; background: transparent; border: none;"
        )
        badge.setVisible(False)
        lay.addWidget(badge)

    def mousePressEvent(self, event):
        self.toggled.emit(self.dep_id)

    def enterEvent(self, event):
        self.setStyleSheet(f"background: {C('bg_hover')}; border-radius: 5px;")

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
        self.setFixedHeight(96)
        self.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b;"
            "border-radius: 10px;"
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
    add_camera_requested = pyqtSignal()
    ai_pause_requested = pyqtSignal(bool)

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        self.db  = db
        self.cfg = config_manager

        self._panels: dict[int, CameraPanel]      = {}
        self._cam_items: dict[int, CameraListItem] = {}
        self._cam_status: dict[int, str]           = {}
        self._sidebar_cameras: list                = []
        self._all_cameras: list                    = []
        self._visible_cameras: list                = []
        self._selected_cam_id: int | None          = None
        self._search_text = ""
        self._stream_filter = "all"
        self._grid_columns = 4
        self._grid_btns: dict[int, QPushButton] = {}
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_visible_cameras"):
            QTimer.singleShot(0, self._relayout_grid)

    # ── Ana UI ───────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        self.setStyleSheet("background: #03070b;")
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(14)

        # Chap sidebar
        root.addWidget(self._build_left_sidebar())

        # O'ng tomon separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(0)
        sep.setStyleSheet("background: transparent; border: none;")
        root.addWidget(sep)

        # Asosiy kontent
        root.addWidget(self._build_main_content(), 1)

    # ════════════════════════════════════════════════════════════════════════
    #  CHAP SIDEBAR
    # ════════════════════════════════════════════════════════════════════════

    def _build_left_sidebar(self) -> QWidget:
        # Tashqi konteyner — shaffof, panellar ichida bo'ladi
        sidebar = QWidget()
        sidebar.setFixedWidth(290)
        sidebar.setStyleSheet("background: transparent;")

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # ── Kamera paneli (flex-[7]) ─────────────────────────────────────
        cam_panel = QFrame()
        cam_panel.setObjectName("cameraSidebarPanel")
        cam_panel.setStyleSheet(
            "QFrame#cameraSidebarPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b;"
            "border-radius: 12px;"
            "}"
        )
        cam_lay = QVBoxLayout(cam_panel)
        cam_lay.setContentsMargins(16, 14, 16, 14)
        cam_lay.setSpacing(0)

        # Sarlavha
        hdr_lay = QHBoxLayout()
        hdr_lay.setContentsMargins(0, 0, 0, 12)

        cam_title = QLabel("CAMERAS")
        cam_title.setStyleSheet(
            "color: #ffffff; font-size: 11px; font-weight: bold;"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        hdr_lay.addWidget(cam_title, 1)

        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #1e293b;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #334155;
            }}
        """)
        add_btn.clicked.connect(self.add_camera_requested)
        hdr_lay.addWidget(add_btn)
        cam_lay.addLayout(hdr_lay)

        # "All Cameras" tugma
        all_cam = QPushButton()
        all_cam.setFixedHeight(44)
        all_cam_lay = QHBoxLayout(all_cam)
        all_cam_lay.setContentsMargins(12, 0, 12, 0)
        all_cam_lay.setSpacing(8)

        cam_icon = QLabel("◉")
        cam_icon.setText("")
        cam_icon.setFixedSize(22, 22)
        cam_icon.setPixmap(QPixmap(str(Path(__file__).resolve().parents[3] / "images" / "camera-small.svg")).scaled(
            16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        cam_icon.setStyleSheet("background: transparent; border: none;")
        all_cam_lay.addWidget(cam_icon)

        all_lbl = QLabel("All Cameras")
        all_lbl.setStyleSheet(
            "color: #fb923c; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        all_cam_lay.addWidget(all_lbl, 1)

        self._all_count_lbl = QLabel("0")
        self._all_count_lbl.setStyleSheet(
            "color: #fb923c; font-size: 12px; font-weight: bold;"
            " background: rgba(249,115,22,0.18); border: none; border-radius: 11px; padding: 2px 8px;"
        )
        all_cam_lay.addWidget(self._all_count_lbl)

        all_cam.setStyleSheet("""
            QPushButton {
                background: rgba(30,41,59,0.55);
                border: none;
                border-radius: 8px;
                text-align: left;
            }
            QPushButton:hover { background: rgba(30,41,59,0.8); }
        """)
        cam_lay.addWidget(all_cam)
        cam_lay.addSpacing(14)

        # Kamera ro'yxati (scroll)
        cam_scroll = QScrollArea()
        cam_scroll.setWidgetResizable(True)
        cam_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cam_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cam_scroll.setStyleSheet("background: transparent;")

        self._cam_list_widget = QWidget()
        self._cam_list_widget.setStyleSheet("background: transparent;")
        self._cam_list_layout = QVBoxLayout(self._cam_list_widget)
        self._cam_list_layout.setContentsMargins(0, 0, 0, 0)
        self._cam_list_layout.setSpacing(2)
        self._cam_list_layout.addStretch()

        cam_scroll.setWidget(self._cam_list_widget)
        cam_lay.addWidget(cam_scroll, 1)

        lay.addWidget(cam_panel, 7)

        # ── Tizim holati paneli (flex-[3]) ────────────────────────────────
        lay.addWidget(self._build_system_overview(), 3)

        return sidebar

    def _build_system_overview(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("systemOverviewPanel")
        frame.setStyleSheet(
            "QFrame#systemOverviewPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b;"
            "border-radius: 12px;"
            "}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(0)

        # Sarlavha
        ov_title = QLabel("SYSTEM OVERVIEW")
        ov_title.setStyleSheet(
            "color: #94a3b8; font-size: 10px; font-weight: bold;"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        lay.addWidget(ov_title)
        lay.addSpacing(12)

        # Total / Online / Offline — 3 ustun
        counts_row = QHBoxLayout()
        counts_row.setSpacing(0)

        for key, label, lbl_color, val_color in [
            ("total",   "Total",   "#94a3b8", "#ffffff"),
            ("online",  "Online",  "#34d399", "#22d3ee"),
            ("offline", "Offline", "#94a3b8", "#94a3b8"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(3)

            val = QLabel("—")
            val.setText("0")
            val.setStyleSheet(
                f"color: {val_color}; font-size: 22px; font-weight: 600;"
                " background: transparent; border: none;"
            )
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(val)

            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color: {lbl_color}; font-size: 10px; background: transparent;"
                " border: none;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl)

            counts_row.addLayout(col, 1)
            setattr(self, f"_ov_{key}", val)

        lay.addLayout(counts_row)
        lay.addSpacing(4)

        # StatLine: Detections Today
        lay.addWidget(self._stat_line("Detections Today", "0", "+0%", red=False))

        # StatLine: No Helmet
        lay.addWidget(self._stat_line("No Helmet Detections", "0", "+0%", red=True))

        # Recognition Rate
        rr = QWidget()
        rr.setStyleSheet("background: transparent;")
        rr_lay = QVBoxLayout(rr)
        rr_lay.setContentsMargins(0, 8, 0, 4)
        rr_lay.setSpacing(4)

        rl = QLabel("Recognition Rate")
        rl.setStyleSheet("color: #94a3b8; font-size: 11px; background: transparent; border: none;")
        rr_lay.addWidget(rl)

        rv_row = QHBoxLayout()
        rv_row.setSpacing(6)
        rv = QLabel("98.6%")
        rv.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: bold; background: transparent; border: none;")
        rv_row.addWidget(rv)
        rd = QLabel("+2.4%")
        rd.setStyleSheet("color: #34d399; font-size: 11px; background: transparent; border: none;")
        rv_row.addWidget(rd, 0, Qt.AlignmentFlag.AlignBottom)
        rv_row.addStretch()
        rex = QLabel("Excellent")
        rex.setStyleSheet("color: #22d3ee; font-size: 11px; background: transparent; border: none;")
        rv_row.addWidget(rex, 0, Qt.AlignmentFlag.AlignBottom)
        rr_lay.addLayout(rv_row)

        rate_bar = QProgressBar()
        rate_bar.setRange(0, 100)
        rate_bar.setValue(88)
        rate_bar.setFixedHeight(6)
        rate_bar.setTextVisible(False)
        rate_bar.setStyleSheet(
            "QProgressBar { background: #1e293b; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #34d399; border-radius: 3px; }"
        )
        rr_lay.addWidget(rate_bar)
        lay.addWidget(rr)

        return frame

    def _stat_line(self, title: str, value: str, delta: str, red: bool = False) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #1e293b; border: none; max-height: 1px;")
        lay.addWidget(sep)

        lay.addSpacing(6)

        t = QLabel(title)
        t.setStyleSheet("color: #cbd5e1; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(t)

        vrow = QHBoxLayout()
        vrow.setSpacing(6)
        v = QLabel(value)
        v.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: bold; background: transparent; border: none;")
        if title == "Detections Today":
            self._detections_today_lbl = v
        elif title == "No Helmet Detections":
            self._no_helmet_today_lbl = v
        vrow.addWidget(v)
        dc = "#ef4444" if red else "#34d399"
        d = QLabel(delta)
        d.setStyleSheet(f"color: {dc}; font-size: 11px; background: transparent; border: none;")
        vrow.addWidget(d, 0, Qt.AlignmentFlag.AlignBottom)
        vrow.addStretch()
        lay.addLayout(vrow)

        line = QFrame()
        line.setFixedHeight(2)
        lc = "#7f1d1d" if red else "#065f46"
        line.setStyleSheet(f"background: {lc}; border: none; border-radius: 1px;")
        lay.addWidget(line)

        lay.addSpacing(4)
        return w


    # ════════════════════════════════════════════════════════════════════════
    #  O'NG ASOSIY KONTENT
    # ════════════════════════════════════════════════════════════════════════

    def _build_main_content(self) -> QWidget:
        main = QWidget()
        self._main_content = main
        main.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Live Monitoring paneli (header + kamera grid bir panel ichida)
        monitor_panel = QFrame()
        self._monitor_panel = monitor_panel
        monitor_panel.setObjectName("monitorPanel")
        monitor_panel.setStyleSheet(
            "QFrame#monitorPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b;"
            "border-radius: 12px;"
            "}"
        )
        mp_lay = QVBoxLayout(monitor_panel)
        mp_lay.setContentsMargins(14, 12, 14, 12)
        mp_lay.setSpacing(10)
        mp_lay.addWidget(self._build_monitor_header())
        mp_lay.addWidget(self._build_camera_grid_area(), 1)

        lay.addWidget(monitor_panel, 1)
        bottom_panels = self._build_bottom_panels()
        self._bottom_panels = bottom_panels
        lay.addWidget(bottom_panels)

        return main

    def _build_monitor_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(46)
        hdr.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Jonli monitoring sarlavhasi
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {C('success')}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(dot)
        dot.setText("●")
        dot.setStyleSheet(f"color: {C('success')}; font-size: 12px; background: transparent; border: none;")

        title = QLabel("Live Monitoring")
        title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 15px; font-weight: bold;"
            " background: transparent; border: none;"
        )
        lay.addWidget(title)
        title.setStyleSheet(f"color: {C('text_primary')}; font-size: 16px; font-weight: 800; background: transparent; border: none;")

        self._cam_count_badge = QLabel("● 0 Cameras")
        self._cam_count_badge.setText("0 Cameras")
        self._cam_count_badge.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 12px; background: transparent; border: none;"
        )
        lay.addWidget(self._cam_count_badge)
        self._cam_count_badge.setStyleSheet(f"color: {C('text_secondary')}; font-size: 12px; background: transparent; border: none;")
        lay.removeWidget(dot)
        lay.insertWidget(1, dot)
        lay.addStretch()

        # Grid tartibi tugmalari
        icon_dir = Path(__file__).resolve().parents[3] / "images"
        grid_options = [
            (1, "1 ustun", "layout-1.svg"),
            (2, "2 ustun", "layout-2.svg"),
            (3, "3 ustun", "layout-3.svg"),
            (4, "4 ustun / 2 qator", "layout-4x2.svg"),
        ]
        for columns, tip, icon_name in grid_options:
            btn = QPushButton(str(columns))
            btn.setFixedSize(32, 32)
            btn.setText("")
            btn.setIcon(QIcon(str(icon_dir / icon_name)))
            btn.setIconSize(QSize(17, 17))
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _, cols=columns: self.set_grid_columns(cols))
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
            active = columns == self._grid_columns
            btn.setFixedSize(34, 34)
            btn.setStyleSheet(self._grid_btn_style(active))
            lay.addWidget(btn)
            self._grid_btns[columns] = btn

        lay.addSpacing(8)

        # Stream tanlash
        stream_combo = QComboBox()
        stream_combo.addItems(["All Streams", "Main Building", "Secondary Area"])
        stream_combo.clear()
        stream_combo.addItems(["All Streams", "Online", "Offline", "Main Building", "Secondary Area"])
        stream_combo.setFixedWidth(130)
        stream_combo.setFixedHeight(32)
        self._stream_combo = stream_combo
        stream_combo.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(stream_combo)

        # Kengaytirish
        expand_btn = QPushButton("⤢")
        expand_btn.setFixedSize(32, 32)
        expand_btn.setText("[]")
        expand_btn.setText("")
        expand_btn.setFixedSize(34, 34)
        expand_btn.setIcon(QIcon(str(icon_dir / "expand.svg")))
        expand_btn.setIconSize(QSize(17, 17))
        expand_btn.setToolTip("Expand selected camera")
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
        expand_btn.clicked.connect(self._expand_selected_camera)
        lay.addWidget(expand_btn)

        return hdr

    def _build_camera_grid_area(self) -> QScrollArea:
        scroll = QScrollArea()
        self._camera_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setStyleSheet(self._camera_scroll_style())

        self._cam_container = QWidget()
        self._cam_container.setStyleSheet("background: transparent;")
        self._cam_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._cam_grid = QGridLayout(self._cam_container)
        self._cam_grid.setSpacing(10)
        self._cam_grid.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._cam_container)
        return scroll

    @staticmethod
    def _camera_scroll_style() -> str:
        return """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #050a0f;
                width: 8px;
                margin: 2px 0 2px 6px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 4px;
                min-height: 36px;
            }
            QScrollBar::handle:vertical:hover {
                background: #fb923c;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """

    def _build_bottom_panels(self) -> QWidget:
        bottom = QWidget()
        bottom.setFixedHeight(260)
        bottom.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(bottom)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        panels = [
            self._build_recent_events(),
            self._build_detected_people(),
            self._build_ai_detection(),
            self._build_no_helmet_panel(),
        ]
        for panel in panels:
            lay.addWidget(panel, 1)

        return bottom

    # ── Recent Events ────────────────────────────────────────────────────

    def _build_recent_events(self) -> QWidget:
        w = QFrame()
        w.setObjectName("recentEventsPanel")
        w.setStyleSheet(
            "QFrame#recentEventsPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b; border-radius: 12px;"
            "}"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        t = QLabel("Recent Events")
        t.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        hdr.addWidget(t)
        hdr.addStretch()

        view_all = QPushButton("View All")
        view_all.setStyleSheet(
            "QPushButton { background: transparent; color: #fb923c; border: none;"
            " font-size: 11px; font-weight: bold; padding: 0; }"
            "QPushButton:hover { color: #fdba74; }"
        )
        view_all.clicked.connect(self.go_violations)
        hdr.addWidget(view_all)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._events_widget = QWidget()
        self._events_widget.setStyleSheet("background: transparent; border: none;")
        self._events_layout = QVBoxLayout(self._events_widget)
        self._events_layout.setContentsMargins(0, 0, 0, 0)
        self._events_layout.setSpacing(4)
        self._events_layout.addStretch()

        scroll.setWidget(self._events_widget)
        lay.addWidget(scroll, 1)
        return w

    # ── Detected People ──────────────────────────────────────────────────

    def _build_detected_people(self) -> QWidget:
        w = QFrame()
        w.setObjectName("detectedPeoplePanel")
        w.setStyleSheet(
            "QFrame#detectedPeoplePanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b; border-radius: 12px;"
            "}"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        t = QLabel("Detected People")
        t.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        hdr.addWidget(t)
        hdr.addStretch()
        view_all = QPushButton("View All")
        view_all.setStyleSheet(
            "QPushButton { background: transparent; color: #fb923c; border: none;"
            " font-size: 11px; font-weight: bold; padding: 0; }"
            "QPushButton:hover { color: #fdba74; }"
        )
        view_all.clicked.connect(self.go_violations)
        hdr.addWidget(view_all)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._people_widget = QWidget()
        self._people_widget.setStyleSheet("background: transparent; border: none;")
        self._people_layout = QVBoxLayout(self._people_widget)
        self._people_layout.setContentsMargins(0, 0, 0, 0)
        self._people_layout.setSpacing(6)
        self._people_layout.addStretch()

        scroll.setWidget(self._people_widget)
        lay.addWidget(scroll, 1)
        return w

    # ── AI Detection ─────────────────────────────────────────────────────

    def _build_ai_detection(self) -> QWidget:
        w = QFrame()
        w.setObjectName("aiDetectionPanel")
        w.setStyleSheet(
            "QFrame#aiDetectionPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b; border-radius: 12px;"
            "}"
        )
        w.setMinimumHeight(260)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(0)

        t = QLabel("AI Detection")
        t.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        lay.addWidget(t)
        lay.addSpacing(14)

        # Content: person placeholder (left) + text stack (right)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_lay = QHBoxLayout(content)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(14)

        # Left: person silhouette placeholder
        person_box = QFrame()
        person_box.setObjectName("aiPersonBox")
        person_box.setFixedSize(88, 120)
        person_box.setStyleSheet(
            "QFrame#aiPersonBox {"
            "background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0f2030,stop:1 #071016);"
            "border-radius: 8px; border: none;"
            "}"
        )
        pb_lay = QVBoxLayout(person_box)
        pb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        person_icon = QLabel("👤")
        person_icon.setStyleSheet("font-size: 36px; background: transparent; color: #334155; border: none;")
        person_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pb_lay.addWidget(person_icon)
        c_lay.addWidget(person_box)

        # Right: status + description + button
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(8)

        self._ai_active = True
        self._ai_status_lbl = QLabel("Active")
        self._ai_status_lbl.setStyleSheet(
            "color: #22d3ee; font-size: 22px; font-weight: bold; background: transparent; border: none;"
        )
        r_lay.addWidget(self._ai_status_lbl)

        self._ai_desc_lbl = QLabel("Smart detection is\nrunning smoothly.")
        self._ai_desc_lbl.setStyleSheet(
            "color: #cbd5e1; font-size: 11px; background: transparent; border: none;"
        )
        r_lay.addWidget(self._ai_desc_lbl)

        self._ai_toggle_btn = QPushButton("Pause AI")
        self._ai_toggle_btn.setFixedHeight(38)
        self._ai_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(249,115,22,0.10);
                color: #ffffff;
                border: 1px solid rgba(249,115,22,0.55);
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 20px;
            }
            QPushButton:hover { background: rgba(249,115,22,0.20); }
        """)
        self._ai_toggle_btn.clicked.connect(self._toggle_ai)
        r_lay.addWidget(self._ai_toggle_btn)
        r_lay.addStretch()

        c_lay.addWidget(right, 1)
        lay.addWidget(content, 1)
        return w

    def _toggle_ai(self):
        self._ai_active = not self._ai_active
        self.ai_pause_requested.emit(not self._ai_active)
        if self._ai_active:
            self._ai_status_lbl.setText("Active")
            self._ai_status_lbl.setStyleSheet(
                "color: #22d3ee; font-size: 22px; font-weight: bold; background: transparent;"
            )
            self._ai_desc_lbl.setText("Smart detection is\nrunning smoothly.")
            self._ai_toggle_btn.setText("Pause AI")
        else:
            self._ai_status_lbl.setText("Paused")
            self._ai_status_lbl.setStyleSheet(
                "color: #64748b; font-size: 22px; font-weight: bold; background: transparent;"
            )
            self._ai_desc_lbl.setText("Detection is paused\nfor review.")
            self._ai_toggle_btn.setText("Start AI")

    # ── No Helmet ────────────────────────────────────────────────────────

    def _build_no_helmet_panel(self) -> QWidget:
        w = QFrame()
        w.setObjectName("noHelmetPanel")
        w.setStyleSheet(
            "QFrame#noHelmetPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b; border-radius: 12px;"
            "}"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        t = QLabel("No Helmet")
        t.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        hdr.addWidget(t)
        hdr.addStretch()
        va = QPushButton("View All")
        va.setStyleSheet(
            "QPushButton { background: transparent; color: #fb923c; border: none;"
            " font-size: 11px; font-weight: bold; padding: 0; }"
            "QPushButton:hover { color: #fdba74; }"
        )
        va.clicked.connect(self.go_violations)
        hdr.addWidget(va)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        self._no_helmet_container = QWidget()
        self._no_helmet_container.setStyleSheet("background: transparent;")
        self._no_helmet_grid = QGridLayout(self._no_helmet_container)
        self._no_helmet_grid.setSpacing(8)
        self._no_helmet_grid.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._no_helmet_container)
        lay.addWidget(scroll, 1)
        return w

    # ════════════════════════════════════════════════════════════════════════
    #  KAMERA PANELLARI BOSHQARUVI
    # ════════════════════════════════════════════════════════════════════════

    def _clear_camera_sidebar(self):
        while self._cam_list_layout.count():
            item = self._cam_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_camera_sidebar(self):
        self._clear_camera_sidebar()
        self._cam_items.clear()

        cameras = self._sidebar_cameras
        departments = self.cfg.get_departments() if self.cfg else []
        if departments:
            for dep in departments:
                dep_id = dep.get("id")
                dep_cameras = [c for c in cameras if c.get("department_id") == dep_id]
                if not dep_cameras:
                    continue
                expanded = bool(dep.get("expanded", True))
                header = CameraGroupHeader(
                    dep_id, dep.get("name", "Bo'lim"), len(dep_cameras), expanded
                )
                header.toggled.connect(self._toggle_department)
                self._cam_list_layout.addWidget(header)
                if expanded:
                    for cam in dep_cameras:
                        self._add_sidebar_camera_item(cam, grouped=True)

            known_deps = {d.get("id") for d in departments}
            ungrouped = [c for c in cameras if c.get("department_id") not in known_deps]
            if ungrouped:
                header = CameraGroupHeader(0, "Bo'limsiz", len(ungrouped), True)
                self._cam_list_layout.addWidget(header)
                for cam in ungrouped:
                    self._add_sidebar_camera_item(cam, grouped=True)
        else:
            for cam in cameras:
                self._add_sidebar_camera_item(cam, grouped=False)

        self._cam_list_layout.addStretch()
        self._recalc_online()

    def _add_sidebar_camera_item(self, cam: dict, grouped: bool):
        cam_id = cam.get("id")
        item = CameraListItem(
            cam_id,
            cam.get("name", f"Kamera {cam_id}"),
            grouped=grouped,
        )
        item.set_status(self._cam_status.get(cam_id, "connecting"))
        item.clicked.connect(self._select_camera)
        self._cam_items[cam_id] = item
        self._cam_list_layout.addWidget(item)

    def _toggle_department(self, dep_id: int):
        dep = self.cfg.get_department_by_id(dep_id) if self.cfg else None
        if not dep:
            return
        self.cfg.update_department(dep_id, expanded=not bool(dep.get("expanded", True)))
        self.cfg.save()
        self._rebuild_camera_sidebar()

    def set_search_text(self, text: str):
        self._search_text = (text or "").strip().lower()
        self._apply_camera_view()

    def set_grid_columns(self, columns: int):
        self._grid_columns = max(1, min(4, int(columns or 4)))
        for cols, btn in self._grid_btns.items():
            btn.setStyleSheet(self._grid_btn_style(cols == self._grid_columns))
        self._apply_camera_view()

    @staticmethod
    def _grid_btn_style(active: bool = False) -> str:
        bg = "rgba(249,115,22,0.18)" if active else "#0f172a"
        border = "rgba(249,115,22,0.55)" if active else "#1e293b"
        return f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 7px;
            }}
            QPushButton:hover {{
                background: rgba(30,41,59,0.9);
                border-color: rgba(249,115,22,0.45);
            }}
        """

    def _on_filter_changed(self):
        combo = getattr(self, "_stream_combo", None)
        self._stream_filter = combo.currentText().lower() if combo else "all streams"
        self._apply_camera_view()

    def _camera_matches_view(self, cam: dict) -> bool:
        cam_id = cam.get("id")
        haystack = " ".join([
            str(cam_id or ""),
            cam.get("name", ""),
            cam.get("rtsp_url", ""),
            cam.get("company_id", ""),
            self._department_name(cam.get("department_id")),
        ]).lower()
        if self._search_text and self._search_text not in haystack:
            return False

        status = self._cam_status.get(cam_id, "connecting")
        filt = self._stream_filter
        if "online" in filt:
            return status == "live"
        if "offline" in filt:
            return status in {"offline", "error"}
        if "main building" in filt or "secondary area" in filt:
            return self._department_name(cam.get("department_id")).lower() == filt
        return True

    def _department_name(self, dep_id) -> str:
        dep = self.cfg.get_department_by_id(dep_id) if self.cfg else None
        return dep.get("name", "") if dep else ""

    def _apply_camera_view(self):
        if not hasattr(self, "_cam_grid"):
            return
        visible = [cam for cam in self._all_cameras if self._camera_matches_view(cam)]
        self._visible_cameras = visible
        self._render_camera_grid(visible)

    def _render_camera_grid(self, cameras: list):
        """Kamera panellarini grid ichiga joylashtiradi.

        1/2/3 ustun: har qator = viewport to'liq balandligi — 1 qator ko'rinadi, qolganlari scroll.
        4 ustun (4x2): har qator = viewport/2 — 2 qator ko'rinadi, qolganlari scroll.
        """
        while self._cam_grid.count():
            item = self._cam_grid.takeAt(0)
            widget = item.widget()
            if widget:
                if widget in self._panels.values():
                    widget.setParent(None)
                else:
                    widget.deleteLater()

        for r in range(10):
            self._cam_grid.setRowStretch(r, 0)
            self._cam_grid.setRowMinimumHeight(r, 0)
        for c in range(4):
            self._cam_grid.setColumnStretch(c, 0)

        if not cameras:
            no_lbl = QLabel("Bu ko'rinishga mos kamera topilmadi.")
            no_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 14px;")
            self._cam_grid.addWidget(no_lbl, 0, 0)
            self._cam_grid.setColumnStretch(0, 1)
            self._cam_grid.setRowStretch(0, 1)
            return

        cols = 1 if len(cameras) == 1 else min(self._grid_columns, len(cameras))
        panel_h = self._calc_panel_height(cols)

        for idx, cam in enumerate(cameras):
            cam_id = cam.get("id")
            panel = self._panels.get(cam_id)
            if not panel:
                continue
            r = idx // cols
            c = idx % cols
            panel.setFixedHeight(panel_h)
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._cam_grid.addWidget(panel, r, c)

        for c in range(cols):
            self._cam_grid.setColumnStretch(c, 1)

    def _calc_panel_height(self, cols: int) -> int:
        """Har bir kamera paneli balandligini viewport asosida hisoblaydi.

        1/2/3 ustun: to'liq viewport balandligi (1 qator ko'rinadi).
        4 ustun:     viewport / 2 (2 qator ko'rinadi, 4x2 rejimi).
        """
        viewport_h = self._camera_scroll.viewport().height()
        if viewport_h < 100:
            viewport_h = self._camera_scroll.height()
        if viewport_h < 100:
            return 360 if cols <= 2 else 240

        spacing = self._cam_grid.spacing()
        if cols == 4:
            return max(180, (viewport_h - spacing) // 2)
        return max(200, viewport_h)

    def _relayout_grid(self):
        """Oyna o'lchami o'zgarganda panel balandliklarini yangilaydi."""
        if not hasattr(self, "_visible_cameras") or not self._visible_cameras:
            return
        cameras = self._visible_cameras
        cols = 1 if len(cameras) == 1 else min(self._grid_columns, len(cameras))
        panel_h = self._calc_panel_height(cols)

        for cam in cameras:
            cam_id = cam.get("id")
            panel = self._panels.get(cam_id)
            if panel:
                panel.setFixedHeight(panel_h)

    def _select_camera(self, cam_id: int):
        self._selected_cam_id = cam_id
        for pid, panel in self._panels.items():
            if hasattr(panel, "set_selected"):
                panel.set_selected(pid == cam_id)
        for pid, item in self._cam_items.items():
            item.set_selected(pid == cam_id)

    def _expand_selected_camera(self):
        cam_id = self._selected_cam_id
        if cam_id is None and self._visible_cameras:
            cam_id = self._visible_cameras[0].get("id")
        panel = self._panels.get(cam_id)
        if not panel:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(panel.cam_name)
        dlg.resize(1000, 650)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        title = QLabel(f"{panel.cam_id:02d} {panel.cam_name}")
        title.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        lay.addWidget(title)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setStyleSheet("background: #000000; border: 1px solid #1e293b; border-radius: 8px;")
        pixmap = panel._video.pixmap()
        if pixmap and not pixmap.isNull():
            image.setPixmap(pixmap.scaled(960, 560, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            image.setText("Video frame hali mavjud emas")
            image.setStyleSheet(image.styleSheet() + f"color: {C('text_muted')};")
        lay.addWidget(image, 1)
        dlg.exec()

    def setup_cameras(self, cameras: list):
        # Eski panellarni tozalash
        for p in self._panels.values():
            p.deleteLater()
        self._panels.clear()
        self._sidebar_cameras = list(cameras)
        self._all_cameras = list(cameras)
        self._visible_cameras = list(cameras)
        self._selected_cam_id = cameras[0].get("id") if cameras else None
        self._cam_status = {
            cam.get("id", idx + 1): "connecting"
            for idx, cam in enumerate(cameras)
        }
        self._today_per_cam.clear()

        while self._cam_grid.count():
            item = self._cam_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._clear_camera_sidebar()

        n = len(cameras)
        self._total_count  = n
        self._online_count = 0
        self._ov_total.setText(str(n))
        self._all_count_lbl.setText(str(n))
        self._cam_count_badge.setText(f"● {n} Cameras")
        self._ov_online.setText("0")
        self._cam_count_badge.setText(f"{n} Cameras")
        self._ov_offline.setText(str(n))

        if not cameras:
            no_lbl = QLabel("Faol kamera yo'q.\nSozlamalarda kamera qo'shing.")
            no_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 14px;")
            self._cam_grid.addWidget(no_lbl, 0, 0)
            self._cam_list_layout.addStretch()
            return

        for idx, cam in enumerate(cameras):
            cam_id = cam.get("id", idx + 1)
            cam_name = cam.get("name", f"Kamera {cam_id}")

            panel = CameraPanel(
                cam_id     = cam_id,
                cam_name   = cam_name,
                rtsp_url   = cam.get("rtsp_url", ""),
                company_id = cam.get("company_id", ""),
            )
            panel.clicked.connect(self._select_camera)
            self._panels[cam_id] = panel
            self._today_per_cam[cam_id] = 0

        self._rebuild_camera_sidebar()
        self._apply_camera_view()
        if self._selected_cam_id is not None:
            self._select_camera(self._selected_cam_id)

    # ── Tashqi yangilanishlar (workerdan) ─────────────────────────────────

    def update_frame(self, cam_id: int, frame):
        p = self._panels.get(cam_id)
        if p:
            p.set_frame(frame)

    def on_violation(self, data: dict):
        self._recent_violations.insert(0, data)
        if len(self._recent_violations) > self._max_recent:
            self._recent_violations.pop()
        self._rebuild_recent_events()
        self._rebuild_detected_people()
        self._rebuild_no_helmet()
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
        self._cam_status[cam_id] = "live" if conn else "offline"
        item = self._cam_items.get(cam_id)
        if item:
            item.set_status(self._cam_status[cam_id])

        # Online/offline hisoblagich
        self._recalc_online()
        if "online" in self._stream_filter or "offline" in self._stream_filter:
            self._apply_camera_view()

    def on_status(self, cam_id: int, text: str):
        pass

    def on_error(self, cam_id: int, msg: str):
        p = self._panels.get(cam_id)
        if p:
            p.set_error(msg)
        item = self._cam_items.get(cam_id)
        self._cam_status[cam_id] = "error"
        if item:
            item.set_status("error")
        self._recalc_online()
        if "online" in self._stream_filter or "offline" in self._stream_filter:
            self._apply_camera_view()

    def on_model_loaded(self, cam_id: int):
        p = self._panels.get(cam_id)
        if p:
            p.set_model_loading()

    def set_total_persons(self, count: int):
        self._total_persons = max(0, int(count or 0))

    # ── Ichki metodlar ────────────────────────────────────────────────────

    def _recalc_online(self):
        online = sum(1 for status in self._cam_status.values() if status == "live")
        self._online_count = online
        self._ov_online.setText(str(online))
        self._ov_offline.setText(str(self._total_count - online))

    def _refresh_stats(self):
        try:
            today = self.db.get_today_count()
            self._ov_total.setText(str(self._total_count))
            if hasattr(self, "_detections_today_lbl"):
                self._detections_today_lbl.setText(str(today))
            if hasattr(self, "_no_helmet_today_lbl"):
                self._no_helmet_today_lbl.setText(str(today))
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
            "background: transparent; border-radius: 6px;"
        )
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        w.setFixedHeight(46)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(10)

        has_helmet = v.get("has_helmet", False)
        icon = QLabel("✓" if has_helmet else "⚠")
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if has_helmet:
            icon.setStyleSheet(
                "color: #34d399; font-size: 13px; font-weight: bold;"
                " background: #064e3b; border-radius: 11px;"
            )
        else:
            icon.setStyleSheet(
                "color: #ef4444; font-size: 13px; font-weight: bold;"
                " background: #450a0a; border-radius: 11px;"
            )
        lay.addWidget(icon)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        title = "Helmet Detected" if has_helmet else "No Helmet Detected"
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(
            "color: #ffffff; font-size: 12px; font-weight: 600; background: transparent;"
        )
        info_col.addWidget(t_lbl)

        cam_name = v.get("camera_name", v.get("camera_id", ""))
        c_lbl = QLabel(f"Camera {cam_name}")
        c_lbl.setStyleSheet(
            "color: #64748b; font-size: 10px; background: transparent;"
        )
        info_col.addWidget(c_lbl)
        lay.addLayout(info_col, 1)

        ts = v.get("timestamp", "")
        if isinstance(ts, (int, float)) and ts:
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        elif isinstance(ts, str) and len(ts) > 10:
            time_str = ts[11:19]
        else:
            time_str = datetime.datetime.now().strftime("%H:%M:%S")
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 10px; background: transparent;"
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

    def _rebuild_no_helmet(self):
        if not hasattr(self, '_no_helmet_grid'):
            return
        while self._no_helmet_grid.count():
            item = self._no_helmet_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        violations = [v for v in self._recent_violations if not v.get("has_helmet", False)]
        for idx, v in enumerate(violations[:4]):
            card = self._no_helmet_card(v)
            self._no_helmet_grid.addWidget(card, idx // 2, idx % 2)

    def _no_helmet_card(self, v: dict) -> QWidget:
        card = QFrame()
        card.setFixedHeight(90)
        card.setStyleSheet(
            "QFrame { background: #0a0a0a; border: 1px solid rgba(239,68,68,0.4);"
            " border-radius: 8px; }"
        )
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        # Top row: NO HELMET badge + time
        top = QHBoxLayout()
        badge = QLabel("NO HELMET")
        badge.setStyleSheet(
            "background: #ef4444; color: white; font-size: 9px; font-weight: bold;"
            " border-radius: 3px; padding: 1px 5px;"
        )
        top.addWidget(badge)
        top.addStretch()

        ts = v.get("timestamp", "")
        if isinstance(ts, (int, float)) and ts:
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        elif isinstance(ts, str) and len(ts) > 10:
            time_str = ts[11:19]
        else:
            time_str = datetime.datetime.now().strftime("%H:%M:%S")
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            "background: rgba(0,0,0,0.7); color: white; font-size: 9px;"
            " border-radius: 3px; padding: 1px 4px;"
        )
        top.addWidget(time_lbl)
        lay.addLayout(top)

        lay.addStretch()

        # Bottom: ID + camera
        person_id = v.get("track_id", v.get("person_id", "—"))
        id_str = f"ID: {person_id:04d}" if isinstance(person_id, int) else f"ID: {person_id}"
        id_lbl = QLabel(id_str)
        id_lbl.setStyleSheet("color: white; font-size: 11px; font-weight: bold; background: transparent;")
        lay.addWidget(id_lbl)

        cam = v.get("camera_name", v.get("camera_id", ""))
        cam_lbl = QLabel(str(cam) if cam else "Unknown camera")
        cam_lbl.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")
        lay.addWidget(cam_lbl)

        return card

    def _person_row(self, v: dict) -> QWidget:
        has_helmet = v.get("has_helmet", False)
        w = QWidget()
        w.setFixedHeight(62)
        w.setStyleSheet(
            "background: rgba(30,41,59,0.45); border-radius: 8px;"
        )
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)

        # Avatar placeholder
        avatar = QLabel("👤")
        avatar.setFixedSize(44, 44)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            "background: #0f1e2d; border-radius: 6px; font-size: 22px;"
            " border: 1px solid #1e293b;"
        )
        lay.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(2)

        person_id = v.get("track_id", v.get("person_id", "—"))
        id_str = f"ID: {person_id:04d}" if isinstance(person_id, int) else f"ID: {person_id}"
        id_lbl = QLabel(id_str)
        id_lbl.setStyleSheet(
            "color: #fb923c; font-size: 12px; font-weight: bold; background: transparent;"
        )
        info.addWidget(id_lbl)

        cam_name = v.get("camera_name", v.get("camera_id", ""))
        name_lbl = QLabel(str(cam_name) if cam_name else "Unknown")
        name_lbl.setStyleSheet(
            "color: #e2e8f0; font-size: 11px; background: transparent;"
        )
        info.addWidget(name_lbl)
        lay.addLayout(info, 1)

        status_lbl = QLabel("OK Helmet" if has_helmet else "! No Helmet")
        status_lbl.setStyleSheet(
            f"color: {'#34d399' if has_helmet else '#ef4444'};"
            " font-size: 11px; font-weight: 600; background: transparent;"
        )
        lay.addWidget(status_lbl)
        return w
