"""
MainWindow — asosiy oyna.
Toolbar, sahifalar (QStackedWidget), StatusBar, DetectionWorker.
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

from app.core.config_manager import ConfigManager
from app.core.database import ViolationsDB
from app.core.detection_worker import DetectionWorker
from app.pages.dashboard_page import DashboardPage
from app.pages.violations_page import ViolationsPage
from app.pages.analytics_page import AnalyticsPage
from app.pages.settings_dialog import SettingsDialog
from app.pages.about_page import AboutPage
from app.utils.theme import C


class MainWindow(QMainWindow):
    """Asosiy ilova oynasi."""

    PAGE_DASHBOARD   = 0
    PAGE_VIOLATIONS  = 1
    PAGE_ANALYTICS   = 2
    PAGE_ABOUT       = 3

    def __init__(self):
        super().__init__()
        self.cfg    = ConfigManager()
        self.db     = ViolationsDB()
        self.worker = None

        self.setWindowTitle("SmartHelmet — Xavfsizlik Kuzatuv Tizimi")
        self.setMinimumSize(1100, 720)

        self._setup_ui()
        self._setup_statusbar()
        self._setup_shortcuts()
        self.showMaximized()

        # Dastur ishga tushganda detection'ni biroz kechiktirish
        QTimer.singleShot(600, self._start_detection)

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        """Asosiy layout: toolbar + stacked pages."""
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Sahifalar
        self._dashboard  = DashboardPage(self.db, self.cfg)
        self._violations = ViolationsPage(self.db)
        self._analytics  = AnalyticsPage(self.db)
        self._about      = AboutPage(self.cfg)

        self._stack.addWidget(self._dashboard)    # 0
        self._stack.addWidget(self._violations)   # 1
        self._stack.addWidget(self._analytics)    # 2
        self._stack.addWidget(self._about)        # 3

        # Dashboard → violations sahifasiga o'tish signali
        self._dashboard.go_violations.connect(
            lambda: self._switch_page(self.PAGE_VIOLATIONS)
        )

        self._setup_toolbar()

    def _setup_toolbar(self):
        """Yagona toolbar."""
        tb = QToolBar()
        tb.setMovable(False)
        tb.setFixedHeight(44)
        tb.setStyleSheet(f"""
            QToolBar {{
                background: {C('bg_sidebar')};
                border-bottom: 1px solid {C('border')};
                spacing: 2px;
                padding: 0 6px;
            }}
        """)
        self.addToolBar(tb)

        # Logo / nomi
        logo = QLabel("  ⛑ SmartHelmet  ")
        logo.setStyleSheet(
            f"color: {C('accent')}; font-size: 14px; font-weight: bold;"
            f" padding: 0 8px;"
        )
        tb.addWidget(logo)
        tb.addSeparator()

        # Nav tugmalari
        self._nav_actions = {}
        nav_items = [
            ("Dashboard",    self.PAGE_DASHBOARD,  "Ctrl+1"),
            ("Buzilishlar",  self.PAGE_VIOLATIONS, "Ctrl+2"),
            ("Analitika",    self.PAGE_ANALYTICS,  "Ctrl+3"),
        ]
        for label, page, shortcut in nav_items:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setShortcut(shortcut)
            act.triggered.connect(lambda _, p=page: self._switch_page(p))
            tb.addAction(act)
            self._nav_actions[page] = act

        # Birinchi sahifa active
        self._nav_actions[self.PAGE_DASHBOARD].setChecked(True)

        # Spacer (o'rta bo'sh joy)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)

        # Detection boshqaruv
        self._pause_act = QAction("⏸  Pauza", self)
        self._pause_act.setShortcut("Space")
        self._pause_act.triggered.connect(self._toggle_pause)
        self._pause_act.setEnabled(False)
        tb.addAction(self._pause_act)

        self._restart_act = QAction("⟳  Qayta", self)
        self._restart_act.triggered.connect(self._restart_detection)
        tb.addAction(self._restart_act)

        tb.addSeparator()

        # Screenshot
        screen_act = QAction("📷", self)
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
        about_act = QAction("?  Haqida", self)
        about_act.triggered.connect(lambda: self._switch_page(self.PAGE_ABOUT))
        tb.addAction(about_act)

        # Chiqish
        quit_act = QAction("✕", self)
        quit_act.setToolTip("Dasturdan chiqish (Ctrl+Q)")
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        tb.addAction(quit_act)

        self.addToolBar(tb)

    def _setup_statusbar(self):
        """StatusBar."""
        self._sb = QStatusBar()
        self._sb.setFixedHeight(26)
        self.setStatusBar(self._sb)

        self._sb_cam   = QLabel("Kamera: —")
        self._sb_status = QLabel("Tayyor")
        self._sb_today  = QLabel("Bugun: 0 buzilish")

        for lbl in [self._sb_cam, self._sb_status, self._sb_today]:
            lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")

        self._sb.addPermanentWidget(self._sb_cam)
        self._sb.addPermanentWidget(self._sep_lbl("|"))
        self._sb.addPermanentWidget(self._sb_status, 1)
        self._sb.addPermanentWidget(self._sep_lbl("|"))
        self._sb.addPermanentWidget(self._sb_today)

        self._sb_cam.setText(f"Kamera: {self.cfg.camera_name}")

    @staticmethod
    def _sep_lbl(text="  |  ") -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {C('border')}; font-size: 12px;")
        return l

    def _setup_shortcuts(self):
        """F5 — yangilash."""
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

    # ── Detection boshqaruvi ──────────────────────────────────────────────

    def _start_detection(self):
        """DetectionWorker ni ishga tushirish."""
        if self.worker and self.worker.isRunning():
            return

        self.worker = DetectionWorker(self.cfg, self.db)
        self.worker.frame_ready.connect(self._dashboard.update_frame)
        self.worker.violation_detected.connect(self._on_violation)
        self.worker.stats_updated.connect(self._on_stats)
        self.worker.status_changed.connect(self._on_status)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.model_loaded.connect(self._dashboard.on_model_loaded)

        self.worker.start()
        self._pause_act.setEnabled(True)
        self._sb_status.setText("Model yuklanmoqda...")
        self._sb_cam.setText(f"Kamera: {self.cfg.camera_name}")

    def _stop_detection(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self._pause_act.setEnabled(False)

    def _restart_detection(self):
        self._stop_detection()
        QTimer.singleShot(500, self._start_detection)

    def _toggle_pause(self):
        if not self.worker:
            return
        if self.worker.is_paused():
            self.worker.resume()
            self._pause_act.setText("⏸  Pauza")
            self._sb_status.setText("Qayta ishlash davom etmoqda")
        else:
            self.worker.pause()
            self._pause_act.setText("▶  Davom")
            self._sb_status.setText("Pauza")

    # ── Worker signallari ─────────────────────────────────────────────────

    def _on_violation(self, data: dict):
        """Yangi buzilish."""
        self._dashboard.on_violation(data)
        self._violations.add_new_violation(data)

        today = self.db.get_today_count()
        self._sb_today.setText(f"Bugun: {today} buzilish")

    def _on_stats(self, stats: dict):
        self._dashboard.on_stats(stats)

    def _on_status(self, text: str):
        self._sb_status.setText(text)
        self._dashboard.on_status(text)

    def _on_error(self, msg: str):
        self._sb_status.setText(f"XATOLIK: {msg[:60]}")
        self._dashboard.on_error(msg)

    # ── Sozlamalar ────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec()

    def _on_settings_saved(self):
        """Sozlamalar saqlangandan so'ng detection'ni qayta ishga tushirish."""
        self._sb_cam.setText(f"Kamera: {self.cfg.camera_name}")
        self._restart_detection()

    # ── Yordamchi ─────────────────────────────────────────────────────────

    def _save_screenshot(self):
        """Dashboard video frame'ini screenshot sifatida saqlash."""
        ss_dir = Path("screenshots")
        ss_dir.mkdir(exist_ok=True)
        ts   = int(time.time())
        path = str(ss_dir / f"screenshot_{ts}.jpg")

        # VideoLabel dan pixmap olish
        pm = self._dashboard._video.pixmap()
        if pm and not pm.isNull():
            pm.save(path, "JPEG", 95)
            self._sb_status.setText(f"Screenshot saqlandi: {path}")
        else:
            self._sb_status.setText("Screenshot: video frame topilmadi")

    def _refresh_current(self):
        page = self._stack.currentIndex()
        if page == self.PAGE_VIOLATIONS:
            self._violations._load_violations()
        elif page == self.PAGE_ANALYTICS:
            self._analytics.refresh()

    # ── Yopish ────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Dasturdan chiqish",
            "SmartHelmet tizimini to'xtatib chiqmoqchimisiz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._stop_detection()
            event.accept()
        else:
            event.ignore()
