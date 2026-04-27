"""
MainWindow — asosiy oyna.
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
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QFont, QColor, QIcon, QPixmap, QPainter, QBrush, QShortcut

from app.config.settings_manager import ConfigManager, CameraConfigProxy
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.workers.detection_worker import DetectionWorker
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.violations_page import ViolationsPage
from app.ui.pages.analytics_page import AnalyticsPage
from app.ui.pages.settings_dialog import SettingsDialog
from app.ui.pages.about_page import AboutPage
from app.ui.theme import C


# ─────────────────────────────────────────────────────────────────────────────
#  Top Navbar
# ─────────────────────────────────────────────────────────────────────────────

class TopNavBar(QWidget):
    """SmartHelmet dizaynidagi gorizontal top navbar."""

    PAGE_DASHBOARD  = 0
    PAGE_REPORTS    = 1
    PAGE_ANALYTICS  = 2
    PAGE_ABOUT      = 3

    def __init__(self, on_page_change, on_settings, on_quit, parent=None):
        super().__init__(parent)
        self._on_page_change = on_page_change
        self._on_settings    = on_settings
        self._on_quit        = on_quit
        self._nav_btns: dict[int, QPushButton] = {}

        self.setFixedHeight(56)
        self.setStyleSheet(
            f"background: {C('bg_sidebar')};"
            f"border-bottom: 1px solid {C('border')};"
        )
        self._setup_ui()

    def _setup_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(0)

        # ── Logo ──────────────────────────────────────────────────────────
        logo_w = QWidget()
        logo_w.setStyleSheet("background: transparent;")
        logo_lay = QHBoxLayout(logo_w)
        logo_lay.setContentsMargins(0, 0, 20, 0)
        logo_lay.setSpacing(8)

        helmet = QLabel("⛑")          # ⛑ helmet unicode
        helmet.setStyleSheet(
            f"color: {C('accent')}; font-size: 22px; background: transparent;"
        )
        logo_lay.addWidget(helmet)

        logo_txt = QLabel("SmartHelmet")
        logo_txt.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 15px; font-weight: bold;"
            " letter-spacing: 0.5px; background: transparent;"
        )
        logo_lay.addWidget(logo_txt)
        lay.addWidget(logo_w)

        # ── Nav tugmalari ─────────────────────────────────────────────────
        nav_items = [
            (self.PAGE_DASHBOARD, "Dashboard",   "Ctrl+1"),
            (1,                   "Cameras",     "Ctrl+2"),
            (self.PAGE_ANALYTICS, "Analytics",   "Ctrl+3"),
            (self.PAGE_REPORTS,   "Reports",     "Ctrl+4"),
            (4,                   "Alerts",      "Ctrl+5"),
        ]

        for page_id, label, shortcut in nav_items:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setStyleSheet(self._nav_style())
            btn.clicked.connect(lambda _, p=page_id: self._nav_click(p))
            lay.addWidget(btn)
            self._nav_btns[page_id] = btn

        # Sozlamalar (dialog ochadi)
        settings_btn = QPushButton("⚙  Settings")   # ⚙
        settings_btn.setFixedHeight(40)
        settings_btn.setStyleSheet(self._nav_style())
        settings_btn.clicked.connect(self._on_settings)
        lay.addWidget(settings_btn)

        lay.addStretch()

        # ── O'ng tomon: qidiruv + bell + controls ────────────────────────
        search = QLineEdit()
        search.setPlaceholderText("Search...")
        search.setFixedWidth(180)
        search.setFixedHeight(32)
        search.setStyleSheet(f"""
            QLineEdit {{
                background: {C('bg_panel')};
                color: {C('text_secondary')};
                border: 1px solid {C('border')};
                border-radius: 16px;
                padding: 0 14px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border-color: {C('accent')}; }}
        """)
        lay.addWidget(search)
        lay.addSpacing(8)

        # Bell
        self._bell_btn = QPushButton("▲")
        self._bell_btn.setFixedSize(36, 36)
        self._bell_btn.setStyleSheet(self._icon_btn_style())
        lay.addWidget(self._bell_btn)

        # Notification badge
        self._notif_badge = QLabel("0")
        self._notif_badge.setFixedSize(18, 18)
        self._notif_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notif_badge.setStyleSheet(
            f"background: {C('danger')}; color: white; border-radius: 9px;"
            " font-size: 10px; font-weight: bold;"
        )
        self._notif_badge.setParent(self)
        self._notif_badge.hide()

        # Moon / tema
        moon_btn = QPushButton("☾")           # ☾
        moon_btn.setFixedSize(36, 36)
        moon_btn.setStyleSheet(self._icon_btn_style())
        lay.addWidget(moon_btn)

        # Kamera soni badge
        self._cam_badge = QLabel("0/0 kamera")
        self._cam_badge.setStyleSheet(
            f"color: {C('accent_light')}; font-size: 11px;"
            f" background: {C('accent_dim')};"
            f" border: 1px solid {C('accent_dim')};"
            " border-radius: 4px; padding: 4px 10px;"
        )
        lay.addWidget(self._cam_badge)
        lay.addSpacing(8)

        # Pauza
        self._pause_btn = QPushButton("|| Pauza")
        self._pause_btn.setFixedHeight(32)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setStyleSheet(self._action_btn_style())
        lay.addWidget(self._pause_btn)

        # Restart
        self._restart_btn = QPushButton("↺ Qayta")
        self._restart_btn.setFixedHeight(32)
        self._restart_btn.setStyleSheet(self._action_btn_style())
        lay.addWidget(self._restart_btn)

        lay.addSpacing(8)

        # Screenshot
        ss_btn = QPushButton("Screenshot")
        ss_btn.setFixedHeight(32)
        ss_btn.setStyleSheet(self._action_btn_style())
        lay.addWidget(ss_btn)
        self._ss_btn = ss_btn

        lay.addSpacing(8)

        # Chiqish
        quit_btn = QPushButton("✕")   # ✕
        quit_btn.setFixedSize(36, 36)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C('text_muted')};
                border: none;
                border-radius: 18px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {C('danger_dim')};
                color: {C('danger')};
            }}
        """)
        quit_btn.clicked.connect(self._on_quit)
        lay.addWidget(quit_btn)

        # Dashboard boshlang'ich holat
        self._set_active(self.PAGE_DASHBOARD)

    # ── Uslublar ─────────────────────────────────────────────────────────

    @staticmethod
    def _nav_style() -> str:
        return f"""
        QPushButton {{
            background: transparent;
            color: {C('text_secondary')};
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background: {C('bg_hover')};
            color: {C('text_primary')};
        }}
        QPushButton:checked {{
            color: {C('accent')};
            border-bottom: 2px solid {C('accent')};
            font-weight: bold;
        }}
        """

    @staticmethod
    def _icon_btn_style() -> str:
        return f"""
        QPushButton {{
            background: transparent;
            color: {C('text_secondary')};
            border: none;
            border-radius: 18px;
            font-size: 16px;
        }}
        QPushButton:hover {{
            background: {C('bg_hover')};
            color: {C('text_primary')};
        }}
        """

    @staticmethod
    def _action_btn_style() -> str:
        return f"""
        QPushButton {{
            background: {C('bg_panel')};
            color: {C('text_secondary')};
            border: 1px solid {C('border')};
            border-radius: 5px;
            padding: 0 10px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background: {C('bg_hover')};
            color: {C('text_primary')};
            border-color: {C('border_hover')};
        }}
        QPushButton:disabled {{
            color: {C('text_muted')};
            border-color: {C('border_light')};
        }}
        """

    # ── Ichki metodlar ────────────────────────────────────────────────────

    def _nav_click(self, page_id: int):
        # Cameras va Alerts → dashboard-ga o'xshash sahifaga
        real_page = {
            0: 0,   # Dashboard
            1: 0,   # Cameras → Dashboard (camera view)
            2: 2,   # Analytics
            3: 1,   # Reports → Violations
            4: 1,   # Alerts → Violations
        }.get(page_id, 0)
        self._set_active(page_id)
        self._on_page_change(real_page)

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
            self._notif_badge.show()
        else:
            self._notif_badge.hide()


# ─────────────────────────────────────────────────────────────────────────────
#  MainWindow
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Asosiy ilova oynasi — SmartHelmet dizayni."""

    PAGE_DASHBOARD  = 0
    PAGE_VIOLATIONS = 1
    PAGE_ANALYTICS  = 2
    PAGE_ABOUT      = 3

    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        self.db  = ViolationsDB()

        self._workers: dict[int, DetectionWorker] = {}
        self._persons_per_cam: dict[int, int] = {}
        self._violation_count = 0

        self.setWindowTitle("SmartHelmet — Live Monitoring System")
        self.setMinimumSize(1280, 760)

        self._setup_ui()
        self._setup_statusbar()
        self._setup_shortcuts()
        self.showMaximized()

        QTimer.singleShot(600, self._start_all_cameras)

    # ── UI ────────────────────────────────────────────────────────────────

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
        )
        self._navbar._pause_btn.clicked.connect(self._toggle_pause_all)
        self._navbar._restart_btn.clicked.connect(self._restart_all_cameras)
        self._navbar._ss_btn.clicked.connect(self._save_screenshot)
        v_lay.addWidget(self._navbar)

        # Sahifalar
        self._stack = QStackedWidget()
        v_lay.addWidget(self._stack, 1)

        self._dashboard  = DashboardPage(self.db, self.cfg)
        self._violations = ViolationsPage(self.db)
        self._analytics  = AnalyticsPage(self.db)
        self._about      = AboutPage(self.cfg)

        self._stack.addWidget(self._dashboard)   # 0
        self._stack.addWidget(self._violations)  # 1
        self._stack.addWidget(self._analytics)   # 2
        self._stack.addWidget(self._about)       # 3

        self._dashboard.go_violations.connect(
            lambda: self._switch_page(self.PAGE_VIOLATIONS)
        )

        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
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
            lambda: self._switch_page(self.PAGE_VIOLATIONS)
        )
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(
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

    # ── Sahifa almashtirish ───────────────────────────────────────────────

    def _switch_page(self, page: int):
        self._stack.setCurrentIndex(page)
        if page == self.PAGE_ANALYTICS:
            self._analytics.refresh()

    # ── Ko'p kamera worker boshqaruvi ─────────────────────────────────────

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
            cam_id = cam.get("id")
            if cam_id in self._workers and self._workers[cam_id].isRunning():
                continue

            proxy  = CameraConfigProxy(self.cfg, cam)
            worker = DetectionWorker(proxy, self.db)

            worker.frame_ready.connect(
                lambda frame, cid=cam_id: self._dashboard.update_frame(cid, frame)
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
                lambda cid=cam_id: self._dashboard.on_model_loaded(cid)
            )

            worker.start()
            self._workers[cam_id] = worker

        self._navbar.set_pause_enabled(True)
        self._update_cam_badge()

    def _stop_all_cameras(self):
        for worker in list(self._workers.values()):
            if worker and worker.isRunning():
                worker.stop()
        self._workers.clear()
        self._persons_per_cam.clear()
        self._navbar.set_pause_enabled(False)

    def _restart_all_cameras(self):
        self._stop_all_cameras()
        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
        self._update_cam_badge()
        QTimer.singleShot(500, self._start_all_cameras)

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
            self._navbar._pause_btn.setText("▶ Davom")
            self._sb_status.setText("Pauza")

    # ── Worker signallari ─────────────────────────────────────────────────

    def _on_violation(self, data: dict):
        self._dashboard.on_violation(data)
        self._violations.add_new_violation(data)

        self._violation_count += 1
        self._navbar.set_notif_count(self._violation_count)

        today = self.db.get_today_count()
        self._sb_today.setText(f"Bugun: {today} buzilish")

    def _on_stats(self, cam_id: int, stats: dict):
        self._dashboard.on_stats(cam_id, stats)
        persons = stats.get("active_persons", 0)
        self._persons_per_cam[cam_id] = persons
        total_persons = sum(self._persons_per_cam.values())
        self._dashboard.set_total_persons(total_persons)

    def _on_status(self, cam_id: int, text: str):
        cam  = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] {text}")
        self._dashboard.on_status(cam_id, text)

    def _on_error(self, cam_id: int, msg: str):
        cam  = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] XATOLIK: {msg[:50]}")
        self._dashboard.on_error(cam_id, msg)

    # ── Yordamchi ─────────────────────────────────────────────────────────

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
        dlg = SettingsDialog(self.cfg, self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self):
        self._refresh_sb_cams()
        self._restart_all_cameras()

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

    # ── Yopish ────────────────────────────────────────────────────────────

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
