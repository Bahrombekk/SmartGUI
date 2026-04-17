"""
MainWindow — asosiy oyna.
Ko'p kamera qo'llab-quvvatlash: har yoqilgan kamera uchun alohida DetectionWorker.
"""

import os
import time
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtWidgets import (QMainWindow, QStackedWidget, QStatusBar,
                              QToolBar, QLabel, QPushButton, QMessageBox,
                              QSizePolicy, QWidget, QHBoxLayout)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QFont, QColor

from app.config.settings_manager import ConfigManager, CameraConfigProxy
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.workers.detection_worker import DetectionWorker
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.violations_page import ViolationsPage
from app.ui.pages.analytics_page import AnalyticsPage
from app.ui.pages.settings_dialog import SettingsDialog
from app.ui.pages.about_page import AboutPage
from app.ui.theme import C


class MainWindow(QMainWindow):
    """Asosiy ilova oynasi — ko'p kamera."""

    PAGE_DASHBOARD  = 0
    PAGE_VIOLATIONS = 1
    PAGE_ANALYTICS  = 2
    PAGE_ABOUT      = 3

    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        self.db  = ViolationsDB()

        # camera_id → DetectionWorker
        self._workers: dict[int, DetectionWorker] = {}

        # Umumiy odamlar soni (har kameradan yig'iladi)
        self._persons_per_cam: dict[int, int] = {}

        self.setWindowTitle("SmartHelmet — Ko'p Kamera Kuzatuv Tizimi")
        self.setMinimumSize(1200, 760)

        self._setup_ui()
        self._setup_statusbar()
        self._setup_shortcuts()
        self.showMaximized()

        QTimer.singleShot(600, self._start_all_cameras)

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._dashboard  = DashboardPage(self.db, self.cfg)
        self._violations = ViolationsPage(self.db)
        self._analytics  = AnalyticsPage(self.db)
        self._about      = AboutPage(self.cfg)

        self._stack.addWidget(self._dashboard)   # 0
        self._stack.addWidget(self._violations)  # 1
        self._stack.addWidget(self._analytics)   # 2
        self._stack.addWidget(self._about)        # 3

        self._dashboard.go_violations.connect(
            lambda: self._switch_page(self.PAGE_VIOLATIONS)
        )

        # Dashboard'ga faol kameralani ko'rsatish
        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)

        self._setup_toolbar()

    def _setup_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setFixedHeight(52)
        tb.setStyleSheet(f"""
            QToolBar {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #211508, stop:1 {C('bg_sidebar')});
                border-bottom: 2px solid {C('accent_dim')};
                spacing: 2px; padding: 0 6px;
            }}
            QToolBar QToolButton {{
                background: transparent;
                color: {C('text_secondary')};
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
                min-height: 32px;
            }}
            QToolBar QToolButton:hover {{
                background: {C('accent_subtle')};
                color: {C('accent_light')};
            }}
            QToolBar QToolButton:checked {{
                background: {C('accent_dim')};
                color: {C('accent')};
                font-weight: bold;
                border-bottom: 2px solid {C('accent')};
            }}
            QToolBar::separator {{
                background: {C('border')};
                width: 1px;
                margin: 8px 4px;
            }}
        """)
        self.addToolBar(tb)

        # Logo
        logo_wrap = QWidget()
        logo_wrap.setStyleSheet("background: transparent;")
        logo_lay = QHBoxLayout(logo_wrap)
        logo_lay.setContentsMargins(6, 0, 6, 0)
        logo_lay.setSpacing(0)
        logo_lbl = QLabel("⛑  SmartHelmet")
        logo_lbl.setStyleSheet(
            f"color:{C('accent')};font-size:15px;font-weight:bold;"
            f"letter-spacing:0.5px;background:transparent;"
        )
        logo_lay.addWidget(logo_lbl)
        tb.addWidget(logo_wrap)
        tb.addSeparator()

        # Nav tugmalari
        self._nav_actions = {}
        nav_items = [
            ("🖥  Dashboard",   self.PAGE_DASHBOARD,  "Ctrl+1"),
            ("⚠  Buzilishlar", self.PAGE_VIOLATIONS, "Ctrl+2"),
            ("📊  Analitika",   self.PAGE_ANALYTICS,  "Ctrl+3"),
        ]
        for label, page, shortcut in nav_items:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setShortcut(shortcut)
            act.triggered.connect(lambda _, p=page: self._switch_page(p))
            tb.addAction(act)
            self._nav_actions[page] = act
        self._nav_actions[self.PAGE_DASHBOARD].setChecked(True)

        tb.addSeparator()

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)

        # Kamera soni badge
        self._cam_count_act_widget = QLabel("")
        self._cam_count_act_widget.setStyleSheet(
            f"color:{C('accent_light')};font-size:12px;"
            f"background:{C('accent_dim')};"
            f"border:1px solid {C('border_hover')};"
            f"border-radius:5px;padding:4px 12px;"
        )
        tb.addWidget(self._cam_count_act_widget)
        self._update_cam_count_label()

        tb.addSeparator()

        # Pauza / Davom
        self._pause_act = QAction("⏸  Pauza", self)
        self._pause_act.setShortcut("Space")
        self._pause_act.triggered.connect(self._toggle_pause_all)
        self._pause_act.setEnabled(False)
        tb.addAction(self._pause_act)

        # Qayta ishga tushirish
        restart_act = QAction("⟳  Qayta", self)
        restart_act.setToolTip("Barcha kameralarni qayta ishga tushirish")
        restart_act.triggered.connect(self._restart_all_cameras)
        tb.addAction(restart_act)

        tb.addSeparator()

        # Screenshot
        screen_act = QAction("📷  Screenshot", self)
        screen_act.setToolTip("Screenshot saqlash (Ctrl+S)")
        screen_act.setShortcut("Ctrl+S")
        screen_act.triggered.connect(self._save_screenshot)
        tb.addAction(screen_act)

        # Sozlamalar
        settings_act = QAction("⚙  Sozlamalar", self)
        settings_act.setShortcut("Ctrl+,")
        settings_act.triggered.connect(self._open_settings)
        tb.addAction(settings_act)

        # Haqida
        about_act = QAction("ℹ  Haqida", self)
        about_act.triggered.connect(lambda: self._switch_page(self.PAGE_ABOUT))
        tb.addAction(about_act)

        tb.addSeparator()

        # Chiqish
        quit_act = QAction("✕", self)
        quit_act.setToolTip("Dasturdan chiqish (Ctrl+Q)")
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        tb.addAction(quit_act)

    def _setup_statusbar(self):
        self._sb = QStatusBar()
        self._sb.setFixedHeight(26)
        self.setStatusBar(self._sb)

        self._sb_cams   = QLabel("")
        self._sb_status = QLabel("Tayyor")
        self._sb_today  = QLabel("Bugun: 0 buzilish")

        for lbl in [self._sb_cams, self._sb_status, self._sb_today]:
            lbl.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 12px;"
            )

        self._sb.addPermanentWidget(self._sb_cams)
        self._sb.addPermanentWidget(self._sep_lbl("|"))
        self._sb.addPermanentWidget(self._sb_status, 1)
        self._sb.addPermanentWidget(self._sep_lbl("|"))
        self._sb.addPermanentWidget(self._sb_today)

        self._refresh_sb_cams()

    @staticmethod
    def _sep_lbl(text="  |  ") -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {C('border')}; font-size: 12px;")
        return l

    def _setup_shortcuts(self):
        from PyQt6.QtGui import QShortcut
        f5 = QShortcut(QKeySequence("F5"), self)
        f5.activated.connect(self._refresh_current)

    # ── Sahifa almashtirish ───────────────────────────────────────────────

    def _switch_page(self, page: int):
        self._stack.setCurrentIndex(page)
        for p, act in self._nav_actions.items():
            act.setChecked(p == page)
        if page == self.PAGE_ANALYTICS:
            self._analytics.refresh()

    # ── Ko'p kamera worker boshqaruvi ─────────────────────────────────────

    def _start_all_cameras(self):
        """Yoqilgan barcha kameralar uchun worker ishga tushirish."""
        cameras = self.cfg.get_enabled_cameras()
        if not cameras:
            self._sb_status.setText("Faol kamera yo'q")
            return

        self._sb_status.setText(f"{len(cameras)} ta kamera uchun model yuklanmoqda...")

        for cam in cameras:
            cam_id = cam.get("id")
            if cam_id in self._workers and self._workers[cam_id].isRunning():
                continue  # Allaqachon ishlayapti

            proxy = CameraConfigProxy(self.cfg, cam)
            worker = DetectionWorker(proxy, self.db)

            # Har worker uchun camera_id bog'lash
            worker.frame_ready.connect(
                lambda frame, cid=cam_id: self._dashboard.update_frame(cid, frame)
            )
            worker.violation_detected.connect(
                lambda data: self._on_violation(data)
            )
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

        self._pause_act.setEnabled(True)
        self._update_cam_count_label()

    def _stop_all_cameras(self):
        """Barcha workerlarni to'xtatish."""
        for worker in list(self._workers.values()):
            if worker and worker.isRunning():
                worker.stop()
        self._workers.clear()
        self._persons_per_cam.clear()
        self._pause_act.setEnabled(False)

    def _restart_all_cameras(self):
        """Barcha kameralani qayta ishga tushirish."""
        self._stop_all_cameras()
        # Dashboard'ni ham yangilash
        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
        self._update_cam_count_label()
        QTimer.singleShot(500, self._start_all_cameras)

    def _toggle_pause_all(self):
        """Barcha workerlarni pauza / davom ettirish."""
        if not self._workers:
            return

        # Birinchi worker holatiga qarab qaror qilish
        first_worker = next(iter(self._workers.values()), None)
        if not first_worker:
            return

        if first_worker.is_paused():
            for w in self._workers.values():
                w.resume()
            self._pause_act.setText("⏸  Pauza")
            self._sb_status.setText("Davom etmoqda")
        else:
            for w in self._workers.values():
                w.pause()
            self._pause_act.setText("▶  Davom")
            self._sb_status.setText("Pauza")

    # ── Worker signallari ─────────────────────────────────────────────────

    def _on_violation(self, data: dict):
        self._dashboard.on_violation(data)
        self._violations.add_new_violation(data)

        today = self.db.get_today_count()
        self._sb_today.setText(f"Bugun: {today} buzilish")

    def _on_stats(self, cam_id: int, stats: dict):
        self._dashboard.on_stats(cam_id, stats)

        persons = stats.get("active_persons", 0)
        self._persons_per_cam[cam_id] = persons
        total_persons = sum(self._persons_per_cam.values())
        self._dashboard.set_total_persons(total_persons)

    def _on_status(self, cam_id: int, text: str):
        cam = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] {text}")
        self._dashboard.on_status(cam_id, text)

    def _on_error(self, cam_id: int, msg: str):
        cam = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"Cam{cam_id}") if cam else f"Cam{cam_id}"
        self._sb_status.setText(f"[{name}] XATOLIK: {msg[:50]}")
        self._dashboard.on_error(cam_id, msg)

    # ── Yordamchi ─────────────────────────────────────────────────────────

    def _update_cam_count_label(self):
        cameras = self.cfg.get_enabled_cameras()
        count = len(cameras)
        total = len(self.cfg.get_cameras())
        self._cam_count_act_widget.setText(
            f"📷 {count}/{total} kamera"
        )

    def _refresh_sb_cams(self):
        cameras = self.cfg.get_cameras()
        enabled = [c for c in cameras if c.get("enabled", True)]
        names = ", ".join(c.get("name", "?") for c in enabled[:3])
        if len(enabled) > 3:
            names += f" +{len(enabled)-3}"
        self._sb_cams.setText(f"Kameralar: {names}" if names else "Kamera yo'q")

    # ── Sozlamalar ────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self):
        self._refresh_sb_cams()
        self._restart_all_cameras()

    # ── Screenshot ────────────────────────────────────────────────────────

    def _save_screenshot(self):
        """Birinchi faol paneldan screenshot saqlash."""
        ss_dir = Path("screenshots")
        ss_dir.mkdir(exist_ok=True)
        ts   = int(time.time())
        path = str(ss_dir / f"screenshot_{ts}.jpg")

        # Birinchi panelni topish
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
