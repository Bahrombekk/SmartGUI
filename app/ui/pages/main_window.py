"""
MainWindow тАФ asosiy oyna.
SmartHelmet dizayni: maxsus top navbar + dashboard + violations + analytics.
"""

import os
import time
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QMainWindow, QStackedWidget, QStatusBar, QLabel, QPushButton,
    QMessageBox, QSizePolicy, QWidget, QHBoxLayout, QVBoxLayout,
    QApplication, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction, QKeySequence, QFont, QColor, QIcon, QPixmap, QImage, QPainter, QBrush, QShortcut

from app.config.settings_manager import ConfigManager, CameraConfigProxy
from app.bootstrap.startup_checks import run_startup_checks
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.workers.detection_worker import DetectionWorker
from app.workers.camera_service import svc_destroy
from app.workers.cleanup_worker import CleanupWorker
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.cameras_page import CamerasPage
from app.ui.pages.violations_page import ViolationsPage
from app.ui.pages.analytics_page import AnalyticsPage
from app.ui.pages.users_page import UsersPage
from app.ui.pages.settings_dialog import SettingsPage
from app.ui.theme import C


# тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
#  Top Navbar
# тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

class TopNavBar(QWidget):
    """SmartHelmet dizaynidagi gorizontal top navbar."""

    PAGE_DASHBOARD  = 0
    PAGE_REPORTS    = 3
    PAGE_ANALYTICS  = 2
    PAGE_USERS      = 5
    PAGE_SETTINGS   = 6

    def __init__(self, on_page_change, on_settings, on_quit, on_search=None, parent=None):
        super().__init__(parent)
        self._on_page_change = on_page_change
        self._on_settings    = on_settings
        self._on_quit        = on_quit
        self._on_search      = on_search
        self._nav_btns: dict[int, QPushButton] = {}
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"

        self.setFixedHeight(58)
        self.setStyleSheet(
            "background: #05090d;"
        )
        self._setup_ui()

    def _setup_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(0)

        # тФАтФА Logo тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
        logo_w = QWidget()
        logo_w.setStyleSheet("background: transparent;")
        logo_w.setFixedWidth(245)
        logo_lay = QHBoxLayout(logo_w)
        logo_lay.setContentsMargins(16, 0, 16, 0)
        logo_lay.setSpacing(10)

        # Orange circle with "SH"
        logo_circle = QLabel("SH")
        logo_circle.setFixedSize(32, 32)
        logo_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_circle.setStyleSheet(
            "background: #f97316; color: #000000; border-radius: 16px;"
            " font-size: 12px; font-weight: 900; letter-spacing: -1px;"
        )
        logo_lay.addWidget(logo_circle)

        # "Smart" orange + "Helmet" white
        logo_txt = QLabel()
        logo_txt.setTextFormat(Qt.TextFormat.RichText)
        logo_txt.setText(
            '<span style="color:#fb923c;font-size:16px;font-weight:bold">Smart</span>'
            '<span style="color:#ffffff;font-size:16px;font-weight:bold">Helmet</span>'
        )
        logo_txt.setStyleSheet("background: transparent;")
        logo_lay.addWidget(logo_txt)
        lay.addWidget(logo_w)

        logo_sep = QWidget()
        logo_sep.setFixedWidth(1)
        logo_sep.setStyleSheet("background: #1e293b;")
        lay.addWidget(logo_sep)

        # тФАтФА Nav tugmalari тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
        nav_items = [
            (self.PAGE_DASHBOARD, "Dashboard", "dashboard.svg"),
            (1,                   "Cameras",   "camera.svg"),
            (self.PAGE_ANALYTICS, "Analytics", "analytics.svg"),
            (self.PAGE_REPORTS,   "Reports",   "reports.svg"),
            (self.PAGE_USERS,     "Users",     "users.svg"),
        ]

        for page_id, label, icon_name in nav_items:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(58)
            btn.setMinimumWidth(86)
            btn.setIcon(self._icon(icon_name))
            btn.setIconSize(QSize(16, 16))
            btn.setStyleSheet(self._nav_style())
            btn.clicked.connect(lambda _, p=page_id: self._nav_click(p))
            lay.addWidget(btn)
            self._nav_btns[page_id] = btn

        settings_btn = QPushButton("Settings")
        settings_btn.setCheckable(True)
        settings_btn.setFixedHeight(58)
        settings_btn.setMinimumWidth(86)
        settings_btn.setIcon(self._icon("settings.svg"))
        settings_btn.setIconSize(QSize(16, 16))
        settings_btn.setStyleSheet(self._nav_style())
        settings_btn.clicked.connect(lambda: self._nav_click(self.PAGE_SETTINGS))
        lay.addWidget(settings_btn)
        self._nav_btns[self.PAGE_SETTINGS] = settings_btn

        lay.addStretch()

        # тФАтФА O'ng tomon: qidiruv + bell + controls тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search...")
        self._search.setFixedWidth(190)
        self._search.setFixedHeight(32)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(2,6,23,0.72);
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 7px;
                padding: 0 10px;
                font-size: 13px;
            }}
            QLineEdit:hover {{
                background: rgba(15,23,42,0.70);
                border-color: rgba(148,163,184,0.38);
            }}
            QLineEdit:focus {{
                background: rgba(15,23,42,0.86);
                border: 1px solid rgba(251,146,60,0.74);
            }}
        """)
        self._search.textChanged.connect(self._on_search_changed)
        lay.addWidget(self._search)
        lay.addSpacing(8)

        # Bell
        self._bell_btn = QPushButton()
        self._bell_btn.setFixedSize(30, 30)
        self._bell_btn.setIcon(self._icon("bell.svg"))
        self._bell_btn.setIconSize(QSize(18, 18))
        self._bell_btn.setStyleSheet(self._icon_btn_style())
        self._bell_btn.setToolTip("Reports")
        self._bell_btn.clicked.connect(lambda: self._nav_click(self.PAGE_REPORTS))
        lay.addWidget(self._bell_btn)

        # Notification badge
        self._notif_badge = QLabel("0")
        self._notif_badge.setFixedSize(18, 18)
        self._notif_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notif_badge.setStyleSheet(
            f"background: {C('accent_hover')}; color: white; border-radius: 9px;"
            " font-size: 10px; font-weight: bold;"
        )
        self._notif_badge.setParent(self)
        self._notif_badge.hide()

        # Moon / tema
        moon_btn = QPushButton()
        moon_btn.setFixedSize(30, 30)
        moon_btn.setIcon(self._icon("moon.svg"))
        moon_btn.setIconSize(QSize(18, 18))
        moon_btn.setToolTip("Dark mode")
        moon_btn.setStyleSheet(self._icon_btn_style())
        lay.addWidget(moon_btn)

        # Expand (fullscreen)
        expand_btn = QPushButton()
        expand_btn.setFixedSize(30, 30)
        expand_btn.setIcon(self._icon("expand.svg"))
        expand_btn.setIconSize(QSize(18, 18))
        expand_btn.setToolTip("Fullscreen")
        expand_btn.setStyleSheet(self._icon_btn_style())
        expand_btn.clicked.connect(lambda: self.window().showFullScreen()
                                   if self.window() and not self.window().isFullScreen()
                                   else self.window().showMaximized() if self.window() else None)
        lay.addWidget(expand_btn)

        lay.addSpacing(2)

        # Kamera soni badge
        self._cam_badge = QLabel("0/0 kamera")
        self._cam_badge.setFixedHeight(74)
        self._cam_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_badge.setStyleSheet(
            f"color: {C('accent')}; font-size: 11px; font-weight: 600;"
            f"background: {C('accent_dim')}; padding: 0 12px;"
            f"border-left: 1px solid {C('border')}; border-right: 1px solid {C('border')};"
        )
        lay.addWidget(self._cam_badge)
        self._cam_badge.hide()
        lay.addSpacing(8)

        # Pauza
        self._pause_btn = QPushButton("|| Pauza")
        self._pause_btn.setFixedHeight(32)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setStyleSheet(self._action_btn_style())
        lay.addWidget(self._pause_btn)
        self._pause_btn.hide()

        # Restart
        self._restart_btn = QPushButton("Qayta")
        self._restart_btn.setFixedHeight(32)
        self._restart_btn.setStyleSheet(self._action_btn_style())
        lay.addWidget(self._restart_btn)
        self._restart_btn.hide()

        lay.addSpacing(8)

        # Screenshot
        ss_btn = QPushButton("Screenshot")
        ss_btn.setFixedHeight(32)
        ss_btn.setStyleSheet(self._action_btn_style())
        lay.addWidget(ss_btn)
        self._ss_btn = ss_btn
        self._ss_btn.hide()

        lay.addSpacing(8)

        # Chiqish
        quit_btn = QPushButton()
        quit_btn.setFixedSize(30, 30)
        quit_btn.setIcon(self._icon("close.svg"))
        quit_btn.setIconSize(QSize(18, 18))
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C('text_muted')};
                border: none;
                border-radius: 16px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {C('danger_dim')};
                color: {C('danger')};
            }}
        """)
        quit_btn.setToolTip("Clear search")
        quit_btn.clicked.connect(self._search.clear)
        lay.addWidget(quit_btn)

        # Dashboard boshlang'ich holat
        self._set_active(self.PAGE_DASHBOARD)

    # тФАтФА Uslublar тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    @staticmethod
    def _nav_style() -> str:
        return f"""
        QPushButton {{
            background: transparent;
            color: {C('text_secondary')};
            border: none;
            padding: 0 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            color: #ffffff;
        }}
        QPushButton:checked {{
            color: {C('accent')};
            background: rgba(249,115,22,0.10);
        }}
        """

    def _icon(self, filename: str) -> QIcon:
        return QIcon(str(self._icon_dir / filename))

    @staticmethod
    def _icon_btn_style() -> str:
        return f"""
        QPushButton {{
            background: transparent;
            color: {C('text_secondary')};
            border: none;
            border-radius: 6px;
            font-size: 16px;
        }}
        QPushButton:hover {{
            color: #ffffff;
        }}
        """

    @staticmethod
    def _action_btn_style() -> str:
        return f"""
        QPushButton {{
            background: {C('bg_hover')};
            color: {C('text_secondary')};
            border: 1px solid {C('border')};
            border-radius: 6px;
            padding: 0 10px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background: {C('border')};
            color: {C('text_primary')};
        }}
        QPushButton:disabled {{
            color: {C('text_muted')};
            border-color: {C('border_light')};
        }}
        """

    # тФАтФА Ichki metodlar тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _nav_click(self, page_id: int):
        real_page = {
            0: 0,  # Dashboard
            1: 1,  # Cameras
            2: 3,  # Analytics
            3: 2,  # Reports тЖТ Violations
            5: 4,  # Users тЖТ stack 4
            6: 5,  # Settings тЖТ stack 5
        }.get(page_id, 0)
        self._set_active(page_id)
        if page_id == self.PAGE_SETTINGS:
            self._on_settings()
        else:
            self._on_page_change(real_page, page_id)

    def _on_search_changed(self, text: str):
        if self._on_search:
            self._on_search(text)

    def _set_active(self, page_id: int):
        for pid, btn in self._nav_btns.items():
            btn.setChecked(pid == page_id)

    def set_active_page(self, page_id: int):
        self._set_active(page_id)

    def update_cam_badge(self, active: int, total: int):
        self._cam_badge.setText(f"{active}/{total} kamera")

    def set_pause_enabled(self, enabled: bool):
        self._pause_btn.setEnabled(enabled)

    def set_notif_count(self, count: int):
        if count > 0:
            self._notif_badge.setText(str(min(count, 99)))
            pos = self._bell_btn.mapTo(self, self._bell_btn.rect().topRight())
            self._notif_badge.move(pos.x() - 8, pos.y() - 2)
            self._notif_badge.show()
        else:
            self._notif_badge.hide()


# тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
#  MainWindow
# тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

class MainWindow(QMainWindow):
    """Asosiy ilova oynasi тАФ SmartHelmet dizayni."""

    PAGE_DASHBOARD  = 0
    PAGE_CAMERAS    = 1
    PAGE_VIOLATIONS = 2
    PAGE_ANALYTICS  = 3
    PAGE_USERS      = 4
    PAGE_SETTINGS   = 5

    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        self.db  = ViolationsDB()

        self._workers: dict[int, DetectionWorker] = {}
        self._cleanup_worker: CleanupWorker | None = None
        self._persons_per_cam: dict[int, int] = {}
        self._latest_stats: dict[int, dict] = {}
        self._latest_status: dict[int, str] = {}
        self._latest_errors: dict[int, str] = {}
        self._model_loaded_cameras: set[int] = set()
        self._violation_count = 0
        self._violations_dirty = False
        self._users_loaded = False

        self.setWindowTitle("SmartHelmet - Live Monitoring System")
        self.setMinimumSize(1280, 760)

        self._setup_ui()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._startup_checks = run_startup_checks(self.cfg, self.db)
        failed_checks = [check for check in self._startup_checks if not check.ok]
        if failed_checks:
            self._sb_status.setText(f"Startup checks: {len(failed_checks)} warning")
        self.showMaximized()

        QTimer.singleShot(600, self._start_all_cameras)
        QTimer.singleShot(1200, self._start_cleanup)

    # тФАтФА UI тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _setup_ui(self):
        # Markaziy widget
        central = QWidget()
        self.setCentralWidget(central)
        v_lay = QVBoxLayout(central)
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.setSpacing(0)

        # Top navbar
        self._navbar = TopNavBar(
            on_page_change = self._switch_page,
            on_settings    = self._open_settings,
            on_quit        = self.close,
            on_search      = self._on_global_search,
        )
        self._navbar._pause_btn.clicked.connect(self._toggle_pause_all)
        self._navbar._restart_btn.clicked.connect(self._restart_all_cameras)
        self._navbar._ss_btn.clicked.connect(self._save_screenshot)
        v_lay.addWidget(self._navbar)

        # Orange separator line тАФ full width
        _sep = QWidget()
        _sep.setFixedHeight(2)
        _sep.setStyleSheet("background: #f97316;")
        v_lay.addWidget(_sep)

        # Sahifalar
        self._stack = QStackedWidget()
        v_lay.addWidget(self._stack, 1)

        self._dashboard  = DashboardPage(self.db, self.cfg)
        self._cameras    = CamerasPage(self.db, self.cfg)
        self._violations = ViolationsPage(self.db)
        self._analytics  = AnalyticsPage(self.db, self.cfg)
        self._users      = UsersPage(self.cfg)
        self._settings   = SettingsPage(self.cfg)

        self._stack.addWidget(self._dashboard)   # 0
        self._stack.addWidget(self._cameras)     # 1
        self._stack.addWidget(self._violations)  # 2
        self._stack.addWidget(self._analytics)   # 3
        self._stack.addWidget(self._users)       # 4
        self._stack.addWidget(self._settings)    # 5

        self._dashboard.go_violations.connect(
            lambda: self._switch_page(self.PAGE_VIOLATIONS)
        )
        self._dashboard.add_camera_requested.connect(self._open_settings)
        self._cameras.add_camera_requested.connect(self._open_settings)
        self._cameras.departments_changed.connect(self._on_departments_changed)
        self._cameras.reconnect_requested.connect(self._restart_camera)
        self._dashboard.ai_pause_requested.connect(self._set_ai_paused)
        self._settings.settings_saved.connect(self._on_settings_saved)

        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
        self._cameras.setup_cameras(cameras)
        self._update_cam_badge()

    def _setup_statusbar(self):
        self._sb = QStatusBar()
        self._sb.setFixedHeight(24)
        self.setStatusBar(self._sb)

        self._sb_cams   = QLabel("")
        self._sb_status = QLabel("Tayyor")
        self._sb_today  = QLabel("Bugun: 0 buzilish")

        for lbl in [self._sb_cams, self._sb_status, self._sb_today]:
            lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")

        self._sb.addPermanentWidget(self._sb_cams)
        self._sb.addPermanentWidget(self._sep_lbl())
        self._sb.addPermanentWidget(self._sb_status, 1)
        self._sb.addPermanentWidget(self._sep_lbl())
        self._sb.addPermanentWidget(self._sb_today)

        self._refresh_sb_cams()
        self._sb.hide()

    @staticmethod
    def _sep_lbl(text="  |  ") -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {C('border')}; font-size: 11px;")
        return l

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(
            lambda: self._switch_page(self.PAGE_DASHBOARD)
        )
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(
            lambda: self._switch_page(self.PAGE_CAMERAS)
        )
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(
            lambda: self._switch_page(self.PAGE_VIOLATIONS)
        )
        QShortcut(QKeySequence("Ctrl+4"), self).activated.connect(
            lambda: self._switch_page(self.PAGE_ANALYTICS)
        )
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(
            self._open_settings
        )
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(
            self._save_screenshot
        )
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)
        QShortcut(QKeySequence("F5"),     self).activated.connect(
            self._refresh_current
        )
        QShortcut(QKeySequence("Space"), self).activated.connect(
            self._toggle_pause_all
        )

    # тФАтФА Sahifa almashtirish тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _switch_page(self, page: int, nav_page: int | None = None):
        self._stack.setCurrentIndex(page)
        if nav_page is None:
            nav_page = {
                self.PAGE_DASHBOARD:  0,
                self.PAGE_CAMERAS:    1,
                self.PAGE_VIOLATIONS: 3,
                self.PAGE_ANALYTICS:  2,
                self.PAGE_USERS:      5,
                self.PAGE_SETTINGS:   6,
            }.get(page)
        if nav_page is not None:
            self._navbar.set_active_page(nav_page)
        if page == self.PAGE_ANALYTICS:
            self._analytics.refresh()
        elif page == self.PAGE_VIOLATIONS and self._violations_dirty:
            self._violations_dirty = False
            self._violations._load_violations()
        elif page == self.PAGE_USERS and not self._users_loaded:
            self._users.refresh()
            self._users_loaded = True
        if page in {self.PAGE_DASHBOARD, self.PAGE_CAMERAS}:
            self._apply_cached_camera_state(page)

    def _on_global_search(self, text: str):
        if self._stack.currentIndex() == self.PAGE_USERS:
            self._users.set_search_text(text)
        elif self._stack.currentIndex() == self.PAGE_CAMERAS:
            self._cameras.set_search_text(text)
        else:
            self._dashboard.set_search_text(text)

    # тФАтФА Ko'p kamera worker boshqaruvi тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _start_camera_worker(self, cam: dict) -> bool:
        cam_id = cam.get("id")
        if cam_id in self._workers and self._workers[cam_id].isRunning():
            return False

        proxy = CameraConfigProxy(self.cfg, cam)
        worker = DetectionWorker(proxy, self.db)

        worker.frame_ready.connect(
            lambda frame, cid=cam_id: self._on_frame(cid, frame)
        )
        worker.violation_detected.connect(self._on_violation)
        worker.stats_updated.connect(
            lambda stats, cid=cam_id: self._on_stats(cid, stats)
        )
        worker.status_changed.connect(
            lambda text, cid=cam_id: self._on_status(cid, text)
        )
        worker.error_occurred.connect(
            lambda msg, cid=cam_id: self._on_error(cid, msg)
        )
        worker.model_loaded.connect(
            lambda cid=cam_id: self._on_model_loaded(cid)
        )

        worker.start()
        self._workers[cam_id] = worker
        return True

    def _start_all_cameras(self):
        cameras = self.cfg.get_enabled_cameras()
        if not cameras:
            self._sb_status.setText("Faol kamera yo'q")
            return

        if self.cfg.ai_model_enabled:
            self._sb_status.setText(f"{len(cameras)} ta kamera uchun model yuklanmoqda...")
        else:
            self._sb_status.setText(f"{len(cameras)} ta kameraga ulanmoqda...")

        for cam in cameras:
            self._start_camera_worker(cam)

        self._navbar.set_pause_enabled(True)
        self._update_cam_badge()

    def _stop_all_cameras(self):
        running = [w for w in self._workers.values() if w and w.isRunning()]
        # Hammani bir vaqtda to'xtatish: avval bayroqni o'chiramiz, keyin parallel kutamiz
        for w in running:
            w._running = False
        for w in running:
            w.wait(600)
        self._workers.clear()
        self._persons_per_cam.clear()
        self._navbar.set_pause_enabled(False)
        svc_destroy()  # CameraService va barcha DetectorGroup'larni to'xtatadi

    def _start_cleanup(self):
        if self._cleanup_worker and self._cleanup_worker.isRunning():
            return
        self._cleanup_worker = CleanupWorker(
            self.db,
            self.cfg,
            keep_days=int(self.cfg.get("keep_files_days", 7)),
            cleanup_files=bool(self.cfg.get("cleanup_files", False)),
        )
        self._cleanup_worker.finished_cleanup.connect(
            lambda info: self._sb_status.setText(
                f"Cleanup OK: {info.get('keep_days')} kun, {info.get('deleted_files')} fayl"
            )
        )
        self._cleanup_worker.error_occurred.connect(
            lambda msg: self._sb_status.setText(f"Cleanup xato: {msg[:60]}")
        )
        self._cleanup_worker.start()

    def _restart_all_cameras(self):
        self._stop_all_cameras()
        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
        self._cameras.setup_cameras(cameras)
        self._update_cam_badge()
        QTimer.singleShot(500, self._start_all_cameras)

    def _restart_camera(self, cam_id: int):
        worker = self._workers.pop(cam_id, None)
        if worker and worker.isRunning():
            worker.stop()

        cam = self.cfg.get_camera_by_id(cam_id)
        if not cam or not cam.get("enabled", True):
            self._sb_status.setText(f"CAM {cam_id:02d}: kamera faol emas")
            return

        self._sb_status.setText(f"CAM {cam_id:02d}: qayta ulanmoqda...")
        self._cameras.on_status(cam_id, "Kameraga ulanmoqda...")
        QTimer.singleShot(250, lambda c=cam: self._start_camera_worker(c))

    def _toggle_pause_all(self):
        if not self._workers:
            return
        first = next(iter(self._workers.values()), None)
        if not first:
            return

        if first.is_paused():
            for w in self._workers.values():
                w.resume()
            self._navbar._pause_btn.setText("|| Pauza")
            self._sb_status.setText("Davom etmoqda")
        else:
            for w in self._workers.values():
                w.pause()
            self._navbar._pause_btn.setText("Davom")
            self._sb_status.setText("Pauza")

    # тФАтФА Worker signallari тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _set_ai_paused(self, paused: bool):
        if not self._workers:
            return
        for worker in self._workers.values():
            if paused:
                worker.pause()
            else:
                worker.resume()
        self._navbar._pause_btn.setText("Davom" if paused else "|| Pauza")
        self._sb_status.setText("AI pauza" if paused else "AI davom etmoqda")

    def _on_frame(self, cam_id: int, frame):
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.update_frame(cam_id, frame)
        elif page == self.PAGE_CAMERAS:
            self._cameras.update_frame(cam_id, frame)

    def _on_violation(self, data: dict):
        # crop_frame (numpy) тЖТ QPixmap bir marta main thread da тАФ diskdan o'qimaydi
        crop_frame = data.get("crop_frame")
        if crop_frame is not None and hasattr(crop_frame, "size") and crop_frame.size > 0:
            try:
                rgb = cv2.cvtColor(crop_frame, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                img = QImage(rgb.tobytes(), w, h, 3 * w, QImage.Format.Format_RGB888)
                data["_crop_pixmap"] = QPixmap.fromImage(img)
            except Exception:
                pass
            data["crop_frame"] = None  # numpy xotirani bo'shatish

        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_violation(data)
        if page == self.PAGE_CAMERAS:
            self._cameras.on_violation(data)
        if page == self.PAGE_VIOLATIONS:
            self._violations.add_new_violation(data)
        else:
            self._violations_dirty = True

        self._violation_count += 1
        self._navbar.set_notif_count(self._violation_count)

        # today_count worker payload dan keladi тАФ main thread da DB so'rov yo'q
        today = data.get("today_count")
        if today is not None:
            self._sb_today.setText(f"Bugun: {today} buzilish")

    def _on_stats(self, cam_id: int, stats: dict):
        self._latest_stats[cam_id] = dict(stats)
        if stats.get("connected", False):
            self._latest_errors.pop(cam_id, None)
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_stats(cam_id, stats)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_stats(cam_id, stats)
        persons = stats.get("active_persons", 0)
        self._persons_per_cam[cam_id] = persons
        total_persons = sum(self._persons_per_cam.values())
        if page == self.PAGE_DASHBOARD:
            self._dashboard.set_total_persons(total_persons)

    def _on_status(self, cam_id: int, text: str):
        self._latest_status[cam_id] = text
        cam  = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] {text}")
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_status(cam_id, text)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_status(cam_id, text)

    def _on_error(self, cam_id: int, msg: str):
        self._latest_errors[cam_id] = msg
        cam  = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] XATOLIK: {msg[:50]}")
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_error(cam_id, msg)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_error(cam_id, msg)

    def _on_model_loaded(self, cam_id: int):
        self._model_loaded_cameras.add(cam_id)
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_model_loaded(cam_id)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_model_loaded(cam_id)

    def _apply_cached_camera_state(self, page: int):
        if page == self.PAGE_DASHBOARD:
            for cam_id in self._model_loaded_cameras:
                self._dashboard.on_model_loaded(cam_id)
            for cam_id, stats in self._latest_stats.items():
                self._dashboard.on_stats(cam_id, stats)
            for cam_id, msg in self._latest_errors.items():
                self._dashboard.on_error(cam_id, msg)
            self._dashboard.set_total_persons(sum(self._persons_per_cam.values()))
        elif page == self.PAGE_CAMERAS:
            for cam_id in self._model_loaded_cameras:
                self._cameras.on_model_loaded(cam_id)
            for cam_id, status in self._latest_status.items():
                self._cameras.on_status(cam_id, status)
            for cam_id, stats in self._latest_stats.items():
                self._cameras.on_stats(cam_id, stats)
            for cam_id, msg in self._latest_errors.items():
                self._cameras.on_error(cam_id, msg)

    # тФАтФА Yordamchi тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _update_cam_badge(self):
        cameras = self.cfg.get_enabled_cameras()
        total   = len(self.cfg.get_cameras())
        self._navbar.update_cam_badge(len(cameras), total)

    def _refresh_sb_cams(self):
        cameras = self.cfg.get_cameras()
        enabled = [c for c in cameras if c.get("enabled", True)]
        names   = ", ".join(c.get("name", "?") for c in enabled[:3])
        if len(enabled) > 3:
            names += f" +{len(enabled)-3}"
        self._sb_cams.setText(f"Kameralar: {names}" if names else "Kamera yo'q")

    def _open_settings(self):
        self._settings._load_values()
        self._switch_page(self.PAGE_SETTINGS)

    def _on_settings_saved(self):
        self._refresh_sb_cams()
        self._users_loaded = False
        self._restart_all_cameras()

    def _on_departments_changed(self):
        self._settings._load_values()
        self._users_loaded = False
        self._sb_status.setText("Bo'limlar yangilandi")

    def _save_screenshot(self):
        ss_dir = Path("screenshots")
        ss_dir.mkdir(exist_ok=True)
        ts   = int(time.time())
        path = str(ss_dir / f"screenshot_{ts}.jpg")

        first_panel = next(iter(self._dashboard._panels.values()), None)
        if first_panel:
            pm = first_panel._video.pixmap()
            if pm and not pm.isNull():
                pm.save(path, "JPEG", 95)
                self._sb_status.setText(f"Screenshot saqlandi: {path}")
                return
        self._sb_status.setText("Screenshot: video frame topilmadi")

    def _refresh_current(self):
        page = self._stack.currentIndex()
        if page == self.PAGE_VIOLATIONS:
            self._violations._load_violations()
        elif page == self.PAGE_ANALYTICS:
            self._analytics.refresh()

    # тФАтФА Yopish тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def closeEvent(self, event):
        cam_count = len(self._workers)
        reply = QMessageBox.question(
            self, "Dasturdan chiqish",
            f"SmartHelmet tizimini to'xtatib chiqmoqchimisiz?\n"
            f"({cam_count} ta kamera worker to'xtatiladi)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._stop_all_cameras()
            event.accept()
        else:
            event.ignore()

