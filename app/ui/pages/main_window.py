"""
MainWindow тАФ asosiy oyna.
SmartHelmet dizayni: maxsus top navbar + dashboard + violations + analytics.
"""

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

from app.config.settings_manager import ConfigManager
from app.bootstrap.startup_checks import run_startup_checks
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.ui.controllers.camera_runtime_controller import CameraRuntimeController
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.cameras_page import CamerasPage
from app.ui.pages.violations_page import ViolationsPage
from app.ui.pages.analytics_page import AnalyticsPage
from app.ui.pages.users_page import UsersPage
from app.ui.pages.settings_dialog import SettingsPage
from app.ui.styles import C, build_main_stylesheet as get_main_stylesheet, set_theme


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

    def __init__(self, on_page_change, on_settings, on_quit, on_search=None,
                 on_notifications=None, on_theme_change=None, on_refresh=None, parent=None):
        super().__init__(parent)
        self._on_page_change = on_page_change
        self._on_settings    = on_settings
        self._on_quit        = on_quit
        self._on_search      = on_search
        self._on_notifications = on_notifications
        self._on_theme_change = on_theme_change
        self._on_refresh = on_refresh
        self._nav_btns: dict[int, QPushButton] = {}
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"
        self._notif_count = 0
        self._is_light_mode = False
        self._restore_maximized_after_fullscreen = True

        self.setFixedHeight(58)
        self.setStyleSheet("background: #0c1a2e;")
        self._setup_ui()

    def _setup_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(0)

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

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(58)
        self._refresh_btn.setMinimumWidth(86)
        self._refresh_btn.setIcon(self._colored_icon("refresh.svg", C("text_primary"), 16))
        self._refresh_btn.setIconSize(QSize(16, 16))
        self._refresh_btn.setToolTip("Dastur interfeysini to'liq yangilash")
        self._refresh_btn.setStyleSheet(self._nav_style())
        self._refresh_btn.clicked.connect(self._refresh_requested)
        lay.addWidget(self._refresh_btn)

        # ── Logo (markaz) ─────────────────────────────────────────────────────
        lay.addStretch(1)

        logo_w = QWidget()
        logo_w.setStyleSheet("background: transparent;")
        logo_lay = QHBoxLayout(logo_w)
        logo_lay.setContentsMargins(0, 0, 0, 0)
        logo_lay.setSpacing(12)

        self._logo_circle = QLabel("SZ")
        self._logo_circle.setFixedSize(38, 38)
        self._logo_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_circle.setStyleSheet(
            "background: transparent; color: #e2e8f0; border-radius: 0px;"
            " font-size: 12px; font-weight: 900; border: none;"
        )
        logo_lay.addWidget(self._logo_circle)

        self._logo_txt = QLabel()
        self._logo_txt.setTextFormat(Qt.TextFormat.RichText)
        self._apply_logo_text()
        self._logo_txt.setStyleSheet("background: transparent;")
        logo_lay.addWidget(self._logo_txt)

        self._apply_logo_image()
        lay.addWidget(logo_w)

        lay.addStretch(1)

        self._logo_sep = QWidget()
        self._logo_sep.setFixedSize(0, 0)

        # ── O'ng tomon: qidiruv + bell + controls тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search...")
        self._search.setFixedWidth(190)
        self._search.setFixedHeight(32)
        self._search.setStyleSheet(self._search_style())
        self._search.textChanged.connect(self._on_search_changed)
        lay.addWidget(self._search)
        lay.addSpacing(8)

        # Bell
        self._bell_btn = QPushButton()
        self._bell_btn.setFixedSize(30, 30)
        self._bell_btn.setIcon(self._icon("bell.svg"))
        self._bell_btn.setIconSize(QSize(18, 18))
        self._bell_btn.setStyleSheet(self._icon_btn_style())
        self._bell_btn.setToolTip("Reports / violations")
        self._bell_btn.clicked.connect(self._open_notifications)
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
        self._theme_btn = QPushButton()
        self._theme_btn.setFixedSize(30, 30)
        self._theme_btn.setIcon(self._icon("moon.svg"))
        self._theme_btn.setIconSize(QSize(18, 18))
        self._theme_btn.setToolTip("Light mode")
        self._theme_btn.setCheckable(True)
        self._theme_btn.setStyleSheet(self._icon_btn_style())
        self._theme_btn.clicked.connect(self._toggle_theme)
        lay.addWidget(self._theme_btn)

        # Expand (fullscreen)
        self._expand_btn = QPushButton()
        self._expand_btn.setFixedSize(30, 30)
        self._expand_btn.setIcon(self._icon("expand.svg"))
        self._expand_btn.setIconSize(QSize(18, 18))
        self._expand_btn.setToolTip("Fullscreen")
        self._expand_btn.setStyleSheet(self._icon_btn_style())
        self._expand_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(self._expand_btn)

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
        self._quit_btn = QPushButton()
        self._quit_btn.setFixedSize(30, 30)
        self._quit_btn.setIcon(self._icon("close.svg"))
        self._quit_btn.setIconSize(QSize(18, 18))
        self._quit_btn.setStyleSheet(self._quit_btn_style())
        self._quit_btn.setToolTip("Exit")
        self._quit_btn.clicked.connect(self._on_quit)
        lay.addWidget(self._quit_btn)

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

    def _colored_icon(self, filename: str, color: str, size: int) -> QIcon:
        src = QPixmap(str(self._icon_dir / filename))
        if src.isNull():
            return QIcon()
        pix = src.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        tinted = QPixmap(pix.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, pix)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(color))
        painter.end()
        return QIcon(tinted)

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
            background: rgba(148,163,184,0.10);
            color: #ffffff;
        }}
        QPushButton:checked {{
            background: rgba(249,115,22,0.14);
            color: {C('accent')};
        }}
        """

    @staticmethod
    def _search_style() -> str:
        return f"""
            QLineEdit {{
                background: {C('bg_input')};
                color: {C('text_primary')};
                border: 1px solid {C('border')};
                border-radius: 7px;
                padding: 0 10px;
                font-size: 13px;
            }}
            QLineEdit:hover {{
                background: {C('bg_panel')};
                border-color: {C('border_hover')};
            }}
            QLineEdit:focus {{
                background: {C('bg_panel')};
                border: 1px solid {C('accent')};
            }}
        """

    @staticmethod
    def _quit_btn_style() -> str:
        return f"""
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

    def _open_notifications(self):
        self._violation_count_seen()
        if self._on_notifications:
            self._on_notifications()
        else:
            self._nav_click(self.PAGE_REPORTS)

    def _violation_count_seen(self):
        self._notif_count = 0
        self._notif_badge.hide()

    def _toggle_theme(self):
        self._is_light_mode = not self._is_light_mode
        self.apply_theme("light" if self._is_light_mode else "dark")
        if self._on_theme_change:
            self._on_theme_change("light" if self._is_light_mode else "dark")

    def apply_theme(self, theme: str):
        app = QApplication.instance()
        is_light = theme == "light"
        set_theme(theme)
        self._is_light_mode = is_light
        self._theme_btn.setChecked(is_light)
        if app:
            app.setStyleSheet(get_main_stylesheet())
        self.setStyleSheet("background: #0c1a2e;")
        self._theme_btn.setToolTip("Dark mode" if is_light else "Light mode")
        self._apply_navbar_style()

    def _refresh_requested(self):
        if self._on_refresh:
            self._on_refresh()

    def _apply_logo_text(self):
        """Logo matni — SafeZone brand text."""
        primary = C('text_primary')
        accent = C('accent')
        self._logo_txt.setText(
            f'<span style="font-family:Segoe UI Semibold,Segoe UI,sans-serif;'
            f'color:{primary};font-size:18px;font-weight:800;letter-spacing:.2px">Safe</span>'
            f'<span style="font-family:Segoe UI Semibold,Segoe UI,sans-serif;'
            f'color:{accent};font-size:18px;font-weight:900;letter-spacing:.2px">Zone</span>'
        )

    def _apply_logo_image(self):
        logo_path = Path(__file__).resolve().parents[3] / "images" / "logs.png"
        pix = QPixmap(str(logo_path)) if logo_path.exists() else QPixmap()
        if not pix.isNull():
            self._logo_circle.setPixmap(pix.scaled(
                60, 60,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self._logo_circle.setText("")
        else:
            self._logo_circle.clear()
            self._logo_circle.setText("SZ")

    def _apply_navbar_style(self):
        self._apply_logo_text()
        self._apply_logo_image()
        self._logo_circle.setStyleSheet(
            "background: transparent; color: #e2e8f0; border-radius: 0px;"
            " font-size: 12px; font-weight: 900; border: none;"
        )
        self._logo_sep.setStyleSheet(f"background: {C('border')};")
        for btn in self._nav_btns.values():
            btn.setStyleSheet(self._nav_style())
        self._search.setStyleSheet(self._search_style())
        for btn in (self._bell_btn, self._theme_btn, self._expand_btn):
            btn.setStyleSheet(self._icon_btn_style())
        self._refresh_btn.setIcon(self._colored_icon("refresh.svg", C("text_primary"), 16))
        self._refresh_btn.setStyleSheet(self._nav_style())
        self._notif_badge.setStyleSheet(
            f"background: {C('accent_hover')}; color: white; border-radius: 9px;"
            " font-size: 10px; font-weight: bold;"
        )
        self._cam_badge.setStyleSheet(
            f"color: {C('accent')}; font-size: 11px; font-weight: 600;"
            f"background: {C('accent_dim')}; padding: 0 12px;"
            f"border-left: 1px solid {C('border')}; border-right: 1px solid {C('border')};"
        )
        for btn in (self._pause_btn, self._restart_btn, self._ss_btn):
            btn.setStyleSheet(self._action_btn_style())
        self._quit_btn.setStyleSheet(self._quit_btn_style())

    def _toggle_fullscreen(self):
        window = self.window()
        if not window:
            return
        if window.isFullScreen():
            if self._restore_maximized_after_fullscreen:
                window.showMaximized()
            else:
                window.showNormal()
            self._expand_btn.setToolTip("Fullscreen")
            self._expand_btn.setChecked(False)
        else:
            self._restore_maximized_after_fullscreen = window.isMaximized()
            window.showFullScreen()
            self._expand_btn.setToolTip("Exit fullscreen")
            self._expand_btn.setChecked(True)
        QTimer.singleShot(0, self._position_notif_badge)

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
        self._notif_count = max(0, count)
        if count > 0:
            self._notif_badge.setText(str(min(count, 99)))
            self._position_notif_badge()
            self._notif_badge.show()
        else:
            self._notif_badge.hide()

    def _position_notif_badge(self):
        if not hasattr(self, "_notif_badge") or not hasattr(self, "_bell_btn"):
            return
        pos = self._bell_btn.mapTo(self, self._bell_btn.rect().topRight())
        self._notif_badge.move(pos.x() - 8, pos.y() - 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_notif_count", 0) > 0:
            self._position_notif_badge()


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

        # Barcha kamera workerlari shu controllerga tegishli; MainWindow faqat
        # signallarga ulanib UI sahifalarini yangilaydi.
        self._runtime = CameraRuntimeController(self.cfg, self.db, self)
        self._last_total_persons = -1
        self._violation_count = 0
        self._violations_dirty = False
        self._users_loaded = False
        self._violations = None
        self._analytics = None
        self._users = None
        self._settings = None
        self._connect_runtime_signals()

        self.setWindowTitle("SafeZone - Live Safety Monitoring")
        self.setMinimumSize(1280, 760)

        self._setup_ui()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._startup_checks = run_startup_checks(self.cfg, self.db)
        failed_checks = [check for check in self._startup_checks if not check.ok]
        if getattr(self.db, "recovered_from_corruption", False):
            self._sb_status.setText(f"DB tiklandi: {Path(str(self.db.db_path)).name}")
        elif failed_checks:
            self._sb_status.setText(f"Startup checks: {len(failed_checks)} warning")
        self.showMaximized()

        QTimer.singleShot(600, self._start_all_cameras)
        QTimer.singleShot(1200, self._runtime.start_cleanup)

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
            on_notifications = self._open_notifications_from_nav,
            on_theme_change = self._on_theme_changed,
            on_refresh = self._refresh_application,
        )
        self._navbar._pause_btn.clicked.connect(self._toggle_pause_all)
        self._navbar._restart_btn.clicked.connect(self._restart_all_cameras)
        self._navbar._ss_btn.clicked.connect(self._save_screenshot)
        v_lay.addWidget(self._navbar)

        # Aksent rang chizig'i — full width
        self._accent_sep = QWidget()
        self._accent_sep.setFixedHeight(2)
        self._accent_sep.setStyleSheet(f"background: {C('accent')};")
        v_lay.addWidget(self._accent_sep)

        # Sahifalar
        self._stack = QStackedWidget()
        v_lay.addWidget(self._stack, 1)

        self._dashboard = DashboardPage(self.db, self.cfg)
        self._cameras = CamerasPage(self.db, self.cfg)

        self._stack.addWidget(self._dashboard)   # 0
        self._stack.addWidget(self._cameras)     # 1
        self._stack.addWidget(self._lazy_placeholder("Reports"))    # 2
        self._stack.addWidget(self._lazy_placeholder("Analytics"))  # 3
        self._stack.addWidget(self._lazy_placeholder("Users"))      # 4
        self._stack.addWidget(self._lazy_placeholder("Settings"))   # 5

        self._connect_primary_pages()

        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
        self._cameras.setup_cameras(cameras)
        self._update_cam_badge()
        self._navbar.apply_theme(str(self.cfg.get("theme", "dark")).lower())

    def _lazy_placeholder(self, title: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {C('bg_main')};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(f"{title} yuklanmoqda...")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 14px;")
        lay.addWidget(lbl, 1)
        return w

    def _replace_stack_page(self, index: int, widget: QWidget) -> None:
        old = self._stack.widget(index)
        self._stack.removeWidget(old)
        old.deleteLater()
        self._stack.insertWidget(index, widget)

    def _connect_primary_pages(self) -> None:
        self._dashboard.go_violations.connect(
            lambda: self._switch_page(self.PAGE_VIOLATIONS)
        )
        self._dashboard.add_camera_requested.connect(self._open_settings)
        self._dashboard.ai_pause_requested.connect(self._set_ai_paused)
        self._cameras.add_camera_requested.connect(self._open_settings)
        self._cameras.departments_changed.connect(self._on_departments_changed)
        self._cameras.reconnect_requested.connect(self._restart_camera)

    def _rebuild_stack_pages(self) -> None:
        current = self._stack.currentIndex()
        cameras = self.cfg.get_enabled_cameras()

        self._dashboard = DashboardPage(self.db, self.cfg)
        self._cameras = CamerasPage(self.db, self.cfg)
        self._connect_primary_pages()
        self._replace_stack_page(self.PAGE_DASHBOARD, self._dashboard)
        self._replace_stack_page(self.PAGE_CAMERAS, self._cameras)

        if self._violations is not None:
            self._violations = ViolationsPage(self.db)
            self._replace_stack_page(self.PAGE_VIOLATIONS, self._violations)
        if self._analytics is not None:
            self._analytics = AnalyticsPage(self.db, self.cfg)
            self._analytics.go_cameras.connect(lambda: self._switch_page(self.PAGE_CAMERAS))
            self._replace_stack_page(self.PAGE_ANALYTICS, self._analytics)
        if self._users is not None:
            self._users = UsersPage(self.cfg)
            self._replace_stack_page(self.PAGE_USERS, self._users)
            self._users_loaded = False
        if self._settings is not None:
            self._settings = SettingsPage(self.cfg)
            self._settings.settings_saved.connect(self._on_settings_saved)
            self._replace_stack_page(self.PAGE_SETTINGS, self._settings)

        self._dashboard.setup_cameras(cameras)
        self._cameras.setup_cameras(cameras)
        self._stack.setCurrentIndex(current)

        if current in {self.PAGE_DASHBOARD, self.PAGE_CAMERAS}:
            self._apply_cached_camera_state(current)
        elif current == self.PAGE_VIOLATIONS and self._violations is not None:
            self._violations._load_violations()
        elif current == self.PAGE_ANALYTICS and self._analytics is not None:
            self._analytics.refresh()
        elif current == self.PAGE_USERS and self._users is not None:
            self._users.refresh()
            self._users_loaded = True
        elif current == self.PAGE_SETTINGS and self._settings is not None:
            self._settings._load_values()

        self._update_cam_badge()
        self._refresh_sb_cams()
        self._apply_frame_emission(current)
        self.update()
        self.repaint()

    def _ensure_page(self, page: int) -> QWidget:
        if page == self.PAGE_VIOLATIONS:
            if self._violations is None:
                self._violations = ViolationsPage(self.db)
                self._replace_stack_page(page, self._violations)
            return self._violations
        if page == self.PAGE_ANALYTICS:
            if self._analytics is None:
                self._analytics = AnalyticsPage(self.db, self.cfg)
                self._analytics.go_cameras.connect(lambda: self._switch_page(self.PAGE_CAMERAS))
                self._replace_stack_page(page, self._analytics)
            return self._analytics
        if page == self.PAGE_USERS:
            if self._users is None:
                self._users = UsersPage(self.cfg)
                self._replace_stack_page(page, self._users)
            return self._users
        if page == self.PAGE_SETTINGS:
            if self._settings is None:
                self._settings = SettingsPage(self.cfg)
                self._settings.settings_saved.connect(self._on_settings_saved)
                self._replace_stack_page(page, self._settings)
            return self._settings
        return self._stack.widget(page)

    def _setup_statusbar(self):
        self._sb = QStatusBar()
        self._sb.setFixedHeight(24)
        self.setStatusBar(self._sb)

        self._sb_cams   = QLabel("")
        self._sb_status = QLabel("Tayyor")
        self._sb_today  = QLabel("Bugun: 0 buzilish")

        self._apply_statusbar_style()

        self._sb.addPermanentWidget(self._sb_cams)
        self._sb.addPermanentWidget(self._sep_lbl())
        self._sb.addPermanentWidget(self._sb_status, 1)
        self._sb.addPermanentWidget(self._sep_lbl())
        self._sb.addPermanentWidget(self._sb_today)

        self._refresh_sb_cams()
        self._sb.hide()

    def _apply_statusbar_style(self):
        if not hasattr(self, "_sb"):
            return
        self._sb.setStyleSheet(
            f"background: {C('bg_sidebar')}; color: {C('text_muted')};"
            f" border-top: 1px solid {C('border')};"
        )
        for lbl in [self._sb_cams, self._sb_status, self._sb_today]:
            lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")

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
        QShortcut(QKeySequence("Esc"), self).activated.connect(self._exit_fullscreen)
        QShortcut(QKeySequence("F5"),     self).activated.connect(
            self._refresh_current
        )
        QShortcut(QKeySequence("Space"), self).activated.connect(
            self._toggle_pause_all
        )

    # тФАтФА Sahifa almashtirish тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _switch_page(self, page: int, nav_page: int | None = None):
        self._ensure_page(page)
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
        self._apply_frame_emission(page)

    def _apply_frame_emission(self, page: int):
        """Faqat Dashboard yoki Cameras sahifasida frame'larni UI ga uzatamiz.
        Boshqa sahifalarda QImage konversiyasi va signal trafigi to'xtatiladi."""
        emit = page in {self.PAGE_DASHBOARD, self.PAGE_CAMERAS}
        self._runtime.set_frame_emission(emit)

    def _on_global_search(self, text: str):
        if self._stack.currentIndex() == self.PAGE_USERS and self._users is not None:
            self._users.set_search_text(text)
        elif self._stack.currentIndex() == self.PAGE_CAMERAS:
            self._cameras.set_search_text(text)
        else:
            self._dashboard.set_search_text(text)

    # тФАтФА Ko'p kamera worker boshqaruvi тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _connect_runtime_signals(self):
        """CameraRuntimeController signallarini UI yangilash metodlariga ulaydi."""
        r = self._runtime
        r.frame_ready.connect(self._on_frame)
        r.violation_detected.connect(self._on_violation)
        r.face_recognized.connect(self._on_face_recognized)
        r.stats_updated.connect(self._on_stats)
        r.status_changed.connect(self._on_status)
        r.error_occurred.connect(self._on_error)
        r.model_loaded.connect(self._on_model_loaded)
        r.runtime_status.connect(self._set_sb_status)
        r.cleanup_status.connect(self._set_sb_status)
        r.all_started.connect(self._on_all_started)
        r.pause_changed.connect(self._on_pause_changed)

    def _set_sb_status(self, text: str):
        self._sb_status.setText(text)

    def _start_all_cameras(self):
        self._runtime.start_all()

    def _on_all_started(self):
        self._navbar.set_pause_enabled(True)
        self._update_cam_badge()

    def _on_pause_changed(self, paused: bool):
        self._navbar._pause_btn.setText("Davom" if paused else "|| Pauza")

    def _rebuild_camera_pages(self):
        """Restart paytida — to'xtagandan keyin, start dan oldin sahifalarni qayta quradi."""
        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
        self._cameras.setup_cameras(cameras)
        self._update_cam_badge()

    def _restart_all_cameras(self):
        self._navbar.set_pause_enabled(False)
        self._runtime.restart_all(self._rebuild_camera_pages)

    def _restart_camera(self, cam_id: int):
        self._cameras.on_status(cam_id, "Kameraga ulanmoqda...")
        self._runtime.restart_camera(cam_id)

    def _toggle_pause_all(self):
        paused = self._runtime.toggle_pause_all()
        if paused is None:
            return
        # Tugma matni pause_changed signali orqali yangilanadi.
        self._sb_status.setText("Pauza" if paused else "Davom etmoqda")

    # тФАтФА Worker signallari тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _set_ai_paused(self, paused: bool):
        if not self._runtime.has_workers():
            return
        self._runtime.set_paused(paused)
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
        if page == self.PAGE_VIOLATIONS and self._violations is not None:
            self._violations.add_new_violation(data)
        else:
            self._violations_dirty = True

        self._violation_count += 1
        self._navbar.set_notif_count(self._violation_count)

        # today_count worker payload dan keladi тАФ main thread da DB so'rov yo'q
        today = data.get("today_count")
        if today is not None:
            self._sb_today.setText(f"Bugun: {today} buzilish")

    def _on_face_recognized(self, cam_id: int, data: dict):
        crop_frame = data.get("crop_frame")
        if crop_frame is not None and hasattr(crop_frame, "size") and crop_frame.size > 0:
            try:
                rgb = cv2.cvtColor(crop_frame, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                img = QImage(rgb.tobytes(), w, h, 3 * w, QImage.Format.Format_RGB888)
                data["_crop_pixmap"] = QPixmap.fromImage(img)
            except Exception:
                pass
            data["crop_frame"] = None
        cam = self.cfg.get_camera_by_id(cam_id)
        data["camera_name"] = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        if self._stack.currentIndex() == self.PAGE_DASHBOARD:
            self._dashboard.on_face_recognized(data)

    def _on_stats(self, cam_id: int, stats: dict):
        # Cache (latest_stats / persons_per_cam) controllerda yangilanadi;
        # bu yerda faqat ko'rinib turgan sahifani yangilaymiz.
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_stats(cam_id, stats)
            total = sum(self._runtime.persons_per_cam.values())
            if total != self._last_total_persons:
                self._last_total_persons = total
                self._dashboard.set_total_persons(total)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_stats(cam_id, stats)

    def _on_status(self, cam_id: int, text: str):
        cam  = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] {text}")
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_status(cam_id, text)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_status(cam_id, text)

    def _on_error(self, cam_id: int, msg: str):
        cam  = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] XATOLIK: {msg[:50]}")
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_error(cam_id, msg)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_error(cam_id, msg)

    def _on_model_loaded(self, cam_id: int):
        page = self._stack.currentIndex()
        if page == self.PAGE_DASHBOARD:
            self._dashboard.on_model_loaded(cam_id)
        elif page == self.PAGE_CAMERAS:
            self._cameras.on_model_loaded(cam_id)

    def _apply_cached_camera_state(self, page: int):
        runtime = self._runtime
        if page == self.PAGE_DASHBOARD:
            for cam_id in runtime.model_loaded_cameras:
                self._dashboard.on_model_loaded(cam_id)
            for cam_id, stats in runtime.latest_stats.items():
                self._dashboard.on_stats(cam_id, stats)
            for cam_id, msg in runtime.latest_errors.items():
                self._dashboard.on_error(cam_id, msg)
            total = sum(runtime.persons_per_cam.values())
            self._last_total_persons = total
            self._dashboard.set_total_persons(total)
        elif page == self.PAGE_CAMERAS:
            for cam_id in runtime.model_loaded_cameras:
                self._cameras.on_model_loaded(cam_id)
            for cam_id, status in runtime.latest_status.items():
                self._cameras.on_status(cam_id, status)
            for cam_id, stats in runtime.latest_stats.items():
                self._cameras.on_stats(cam_id, stats)
            for cam_id, msg in runtime.latest_errors.items():
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
        self._ensure_page(self.PAGE_SETTINGS)
        self._settings._load_values()
        self._switch_page(self.PAGE_SETTINGS)

    def _open_notifications_from_nav(self):
        self._violation_count = 0
        self._switch_page(self.PAGE_VIOLATIONS, 3)

    def _on_theme_changed(self, theme: str):
        self.cfg.set("theme", theme)
        self.cfg.save()
        self._apply_theme_refresh(theme)

    def _apply_theme_refresh(self, theme: str):
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_main_stylesheet())
        self._navbar.apply_theme(theme)
        if hasattr(self, "_accent_sep"):
            self._accent_sep.setStyleSheet(f"background: {C('accent')};")
        self._apply_statusbar_style()
        self._rebuild_stack_pages()
        self._sb_status.setText("Theme yangilandi")

    def _refresh_application(self):
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_main_stylesheet())
        self._navbar.apply_theme(str(self.cfg.get("theme", "dark")).lower())
        if hasattr(self, "_accent_sep"):
            self._accent_sep.setStyleSheet(f"background: {C('accent')};")
        self._apply_statusbar_style()
        self._rebuild_stack_pages()
        self._sb_status.setText("Dastur to'liq yangilandi")

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self._navbar._toggle_fullscreen()

    def _on_settings_saved(self):
        self._refresh_sb_cams()
        self._users_loaded = False
        self._restart_all_cameras()

    def _on_departments_changed(self):
        if self._settings is not None:
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
        if page == self.PAGE_DASHBOARD:
            self._dashboard.setup_cameras(self.cfg.get_enabled_cameras())
            self._apply_cached_camera_state(page)
            self._update_cam_badge()
        elif page == self.PAGE_CAMERAS:
            self._cameras.setup_cameras(self.cfg.get_enabled_cameras())
            self._apply_cached_camera_state(page)
            self._update_cam_badge()
        elif page == self.PAGE_VIOLATIONS:
            self._ensure_page(self.PAGE_VIOLATIONS)
            self._violations._load_violations()
        elif page == self.PAGE_ANALYTICS:
            self._ensure_page(self.PAGE_ANALYTICS)
            self._analytics.refresh()
        elif page == self.PAGE_USERS:
            self._ensure_page(self.PAGE_USERS)
            self._users.refresh()
        elif page == self.PAGE_SETTINGS:
            self._ensure_page(self.PAGE_SETTINGS)
            self._settings._load_values()

    # тФАтФА Yopish тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def closeEvent(self, event):
        cam_count = self._runtime.worker_count
        reply = QMessageBox.question(
            self, "Dasturdan chiqish",
            f"SafeZone tizimini to'xtatib chiqmoqchimisiz?\n"
            f"({cam_count} ta kamera worker to'xtatiladi)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._runtime.stop_all_blocking()
            self._navbar.set_pause_enabled(False)
            event.accept()
        else:
            event.ignore()

