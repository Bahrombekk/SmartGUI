"""
MainWindow тАФ asosiy oyna.
SmartHelmet dizayni: maxsus top navbar + dashboard + violations + analytics.
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QMainWindow, QStackedWidget, QStatusBar, QLabel, QPushButton,
    QMessageBox, QSizePolicy, QWidget, QHBoxLayout, QVBoxLayout,
    QApplication, QLineEdit, QAbstractButton, QComboBox, QAbstractSpinBox,
    QAbstractItemView, QTextEdit, QPlainTextEdit, QAbstractSlider,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent
from PyQt6.QtGui import QAction, QKeySequence, QFont, QColor, QIcon, QPixmap, QImage, QPainter, QBrush, QShortcut, QKeyEvent

from app.ui.widgets.app_dialog import AppMessageBox
from app.ui.widgets.toast import show_toast
from app.ui.widgets.frameless import (
    GLYPH_CLOSE, GLYPH_MAX, GLYPH_MIN, GLYPH_RESTORE, EdgeResizer,
)
from app.config.settings_manager import ConfigManager
from app.bootstrap.startup_checks import run_startup_checks
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.ui.controllers.camera_runtime_controller import CameraRuntimeController
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.cameras_page import CamerasPage
from app.ui.pages.violations_page import ViolationsPage
from app.ui.pages.analytics_page import AnalyticsPage
from app.ui.pages.users_page import UsersPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.styles import C, build_main_stylesheet as get_main_stylesheet, set_theme


# тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
#  Top Navbar
# тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

from app.ui.widgets.top_bar import TopNavBar  # Figma top bar

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

        self.setWindowTitle("SafeZone - Jonli xavfsizlik monitoringi")
        self.setMinimumSize(1280, 760)
        # Windows sarlavha qatori o'rniga navbar ishlatiladi (min/max/close navbar'da)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self._edge_resizer = EdgeResizer(self, margin=6)

        self._setup_ui()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._startup_checks = run_startup_checks(self.cfg, self.db)
        failed_checks = [check for check in self._startup_checks if not check.ok]
        self._cam_err_toasts: dict[int, tuple[str, float]] = {}
        self._applied_search: dict[int, str] = {}
        if getattr(self.db, "recovered_from_corruption", False):
            msg = (f"Ma'lumotlar bazasi buzilgan edi va qayta yaratildi: {Path(str(self.db.db_path)).name}."
                   " Eski fayl zaxiraga ko'chirildi.")
            self._sb_status.setText(msg)
            QTimer.singleShot(1500, lambda: show_toast(self, msg, "warning", 10000))
        elif failed_checks:
            details = "; ".join(f"{c.name}: {c.message}" for c in failed_checks[:3])
            more = f" (+{len(failed_checks) - 3})" if len(failed_checks) > 3 else ""
            msg = f"Ishga tushirish tekshiruvi: {len(failed_checks)} ta ogohlantirish — {details}{more}"
            self._sb_status.setText(msg)
            QTimer.singleShot(1500, lambda: show_toast(self, msg, "warning", 8000))
        load_warning = getattr(self.cfg, "load_warning", "")
        if load_warning:
            # settings.json buzilgan edi — zaxiradan tiklandi yoki standartga qaytdi
            QTimer.singleShot(2500, lambda: show_toast(self, load_warning, "warning", 12000))
        self.showMaximized()

        QTimer.singleShot(600, self._start_all_cameras)
        QTimer.singleShot(1200, self._runtime.start_cleanup)
        QTimer.singleShot(1400, self._runtime.start_notifications)
        if self.cfg.needs_setup_wizard:
            QTimer.singleShot(1200, self._open_setup_wizard)

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
        )
        self._navbar._pause_btn.clicked.connect(self._toggle_pause_all)
        self._navbar._restart_btn.clicked.connect(self._restart_all_cameras)
        self._navbar._ss_btn.clicked.connect(self._save_screenshot)
        self._navbar.set_site_name(str(self.cfg.get("site_name", "") or ""))
        self._navbar.set_initials(str(self.cfg.get("operator_initials", "") or ""))
        self._navbar.set_ai_enabled(bool(self.cfg.ai_model_enabled))
        v_lay.addWidget(self._navbar)
        central.setStyleSheet("background: #070e1c;")

        # Ajratgich navbar ichida chiziladi (Figma: y51, 1px #1a2842)
        self._accent_sep = QWidget()
        self._accent_sep.setFixedHeight(0)
        self._accent_sep.hide()

        # Sahifalar
        self._stack = QStackedWidget()
        v_lay.addWidget(self._stack, 1)

        self._dashboard = DashboardPage(self.db, self.cfg)
        self._cameras = CamerasPage(self.db, self.cfg)

        self._stack.addWidget(self._dashboard)   # 0
        self._stack.addWidget(self._cameras)     # 1
        self._stack.addWidget(self._lazy_placeholder("Hodisalar"))    # 2
        self._stack.addWidget(self._lazy_placeholder("Analitika"))  # 3
        self._stack.addWidget(self._lazy_placeholder("Xodimlar"))      # 4
        self._stack.addWidget(self._lazy_placeholder("Sozlamalar"))   # 5

        self._connect_primary_pages()

        cameras = self.cfg.get_enabled_cameras()
        self._dashboard.setup_cameras(cameras)
        self._cameras.setup_cameras(cameras)
        self._update_cam_badge()

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
        self._dashboard.add_camera_requested.connect(self._open_add_camera)
        self._dashboard.ai_pause_requested.connect(self._set_ai_paused)
        if hasattr(self._dashboard, "go_cameras"):
            self._dashboard.go_cameras.connect(lambda: self._switch_page(self.PAGE_CAMERAS))
        self._cameras.add_camera_requested.connect(self._open_add_camera)
        self._dashboard.focus_changed.connect(self._sync_focus_camera)
        self._cameras.focus_changed.connect(self._sync_focus_camera)
        self._cameras.departments_changed.connect(self._on_departments_changed)
        self._cameras.reconnect_requested.connect(self._restart_camera)
        if hasattr(self._cameras, "cameras_changed"):
            self._cameras.cameras_changed.connect(self._on_cameras_changed)

    def _ensure_page(self, page: int) -> QWidget:
        if page == self.PAGE_VIOLATIONS:
            if self._violations is None:
                self._violations = ViolationsPage(self.db, cfg=self.cfg)
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
                self._users = UsersPage(self.cfg, db=self.db)
                self._replace_stack_page(page, self._users)
            return self._users
        if page == self.PAGE_SETTINGS:
            if self._settings is None:
                self._settings = SettingsPage(self.cfg)
                self._connect_settings_page()
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
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._navbar.focus_search)
        QShortcut(QKeySequence("F11"), self).activated.connect(self._navbar._toggle_fullscreen)
        QShortcut(QKeySequence("F5"),     self).activated.connect(
            self._refresh_current
        )
        QShortcut(QKeySequence("Space"), self).activated.connect(self._on_space)

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
        if page == self.PAGE_VIOLATIONS and self._violation_count:
            self._violation_count = 0
            self._navbar.set_notif_count(0)
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
        self._sync_search_box(page)
        self._apply_frame_emission(page)

    def _apply_frame_emission(self, page: int):
        """Faqat Dashboard yoki Cameras sahifasida frame'larni UI ga uzatamiz.
        Boshqa sahifalarda QImage konversiyasi va signal trafigi to'xtatiladi."""
        emit = page in {self.PAGE_DASHBOARD, self.PAGE_CAMERAS}
        self._runtime.set_frame_emission(emit)
        self._sync_focus_camera()

    def _sync_focus_camera(self, *_):
        """Faqat hozir ko'rinib turgan katta oynadagi kamera to'liq sifatda uzatiladi."""
        page = self._stack.currentIndex()
        src = {self.PAGE_DASHBOARD: self._dashboard, self.PAGE_CAMERAS: self._cameras}.get(page)
        self._runtime.set_focus_camera(getattr(src, "_selected", None) if src is not None else None)

    # Qidiruv qaysi sahifalarda ishlaydi (Analitika/Sozlamalarda qidiruv yo'q)
    _SEARCH_PAGES = (PAGE_DASHBOARD, PAGE_CAMERAS, PAGE_VIOLATIONS, PAGE_USERS)

    def _search_target(self, page: int):
        if page == self.PAGE_DASHBOARD:
            return self._dashboard
        if page == self.PAGE_CAMERAS:
            return self._cameras
        if page == self.PAGE_VIOLATIONS:
            return self._violations
        if page == self.PAGE_USERS:
            return self._users
        return None

    def _on_global_search(self, text: str):
        page = self._stack.currentIndex()
        target = self._search_target(page)
        if target is not None and hasattr(target, "set_search_text"):
            target.set_search_text(text)
            self._applied_search[page] = text

    def _sync_search_box(self, page: int):
        """Sahifa almashganda: joriy qidiruv matni yangi sahifaga qo'llanadi;
        qidiruvi yo'q sahifada maydon tozalanib o'chiriladi."""
        edit = self._navbar._search
        if page in self._SEARCH_PAGES:
            edit.setEnabled(True)
            edit.setPlaceholderText("Qidirish")
            # Sahifaning o'z qidiruv maydonidagi matnni bo'sh global matn bilan o'chirmaymiz
            if edit.text() or self._applied_search.get(page):
                self._on_global_search(edit.text())
            return
        if edit.text():
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
            self._navbar._search_box._place()
            # Boshqa sahifalarda qolgan filtr ham bekor qilinsin
            for p in self._SEARCH_PAGES:
                t = self._search_target(p)
                if t is not None and hasattr(t, "set_search_text") and self._applied_search.get(p):
                    t.set_search_text("")
                    self._applied_search[p] = ""
        edit.setPlaceholderText("Bu sahifada qidiruv yo'q")
        edit.setEnabled(False)

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
        r.cleanup_status.connect(self._on_cleanup_status)
        r.all_started.connect(self._on_all_started)
        r.pause_changed.connect(self._on_pause_changed)

    def _set_sb_status(self, text: str):
        self._sb_status.setText(text)

    def _on_cleanup_status(self, text: str):
        self._sb_status.setText(text)
        if "xato" in text.lower():
            show_toast(self, text, "error")

    def _start_all_cameras(self):
        self._runtime.start_all()

    def _on_all_started(self):
        self._navbar.set_pause_enabled(True)
        self._update_cam_badge()

    def _on_pause_changed(self, paused: bool):
        self._navbar._pause_btn.setText("Davom" if paused else "|| Pauza")
        self._navbar.set_ai_active(not paused)

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

    def _on_space(self):
        """Space — faqat kamera sahifalarida pauza. Fokus tugma/checkbox/maydonda
        bo'lsa, oyna shortcut'i bosishni "yutib" yubormasligi uchun klavishni
        o'sha widget'ga qaytaramiz."""
        fw = QApplication.focusWidget()
        if fw is not None and isinstance(fw, (
            QAbstractButton, QComboBox, QAbstractSpinBox, QAbstractItemView,
            QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSlider,
        )):
            for typ in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.sendEvent(fw, QKeyEvent(typ, Qt.Key.Key_Space,
                                                     Qt.KeyboardModifier.NoModifier, " "))
            return
        if self._stack.currentIndex() in (self.PAGE_DASHBOARD, self.PAGE_CAMERAS):
            self._toggle_pause_all()

    def _toggle_pause_all(self):
        paused = self._runtime.toggle_pause_all()
        if paused is None:
            return
        # Tugma matni pause_changed signali orqali yangilanadi.
        msg = "Kameralar pauzada" if paused else "Kameralar davom etmoqda"
        self._sb_status.setText(msg)
        show_toast(self, msg, "info")

    # тФАтФА Worker signallari тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def _set_ai_paused(self, paused: bool):
        if not self._runtime.has_workers():
            return
        self._runtime.set_paused(paused)
        msg = "AI pauza" if paused else "AI davom etmoqda"
        self._sb_status.setText(msg)
        show_toast(self, msg, "info")

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

        if page != self.PAGE_VIOLATIONS:     # Hodisalar ochiq — foydalanuvchi hodisani ko'rib turibdi
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
        self._dashboard.count_face_attempt(bool(data.get("matched")))
        if self._users is not None and hasattr(self._users, "on_face_recognized"):
            self._users.on_face_recognized(data)
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
        # Navbar "AI faol · N fps" — jonli kameralarning o'rtacha FPS'i
        live = [float(s.get("fps", 0) or 0) for s in self._runtime.latest_stats.values()
                if s.get("connected")]
        self._navbar.set_ai_fps(sum(live) / len(live) if live else None)

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
        last = self._cam_err_toasts.get(cam_id)
        now = time.monotonic()
        if last is None or last[0] != msg or now - last[1] > 60:
            self._cam_err_toasts[cam_id] = (msg, now)
            show_toast(self, f"[{name}] {msg[:160]}", "error")
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
        if not self._settings._dirty:      # saqlanmagan tahrirlar ustidan yozmaymiz
            self._settings._load_values()
        self._switch_page(self.PAGE_SETTINGS)

    def _open_add_camera(self):
        """Dashboard / Cameras "+ Add" — sozlamalar ochilib, darhol qo'shish oynasi."""
        self._open_settings()
        self._navbar.set_active_page(TopNavBar.PAGE_SETTINGS)
        self._settings.open_add_camera()

    def _open_setup_wizard(self):
        from app.ui.widgets.setup_wizard import SetupWizard

        if SetupWizard(self.cfg, self).exec() == SetupWizard.DialogCode.Accepted:
            show_toast(self, "Sozlamalar saqlandi — kamera ulanmoqda...", "success")
            if self._settings is not None:
                self._settings._load_values()
            self._on_cameras_changed()

    def _connect_settings_page(self):
        self._settings.wizard_requested.connect(self._open_setup_wizard)
        self._settings.settings_saved.connect(self._on_settings_saved)
        self._settings.cameras_changed.connect(self._on_cameras_changed)
        self._settings.departments_changed.connect(self._on_departments_changed)
        self._settings.branding_changed.connect(self._on_branding_changed)

    def _on_branding_changed(self, site: str, initials: str):
        self._navbar.set_site_name(site or "")
        self._navbar.set_initials(initials or "")

    def _on_cameras_changed(self):
        """Kamera qo'shildi/o'zgardi/o'chirildi — workerlar va sahifalar yangilanadi."""
        self._refresh_sb_cams()
        self._restart_all_cameras()

    def _open_notifications_from_nav(self):
        self._violation_count = 0
        self._switch_page(self.PAGE_VIOLATIONS, 3)

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self._navbar._toggle_fullscreen()

    def _on_settings_saved(self):
        self._navbar.set_ai_enabled(bool(self.cfg.ai_model_enabled))
        self._refresh_sb_cams()
        self._users_loaded = False
        self._restart_all_cameras()

    def _on_departments_changed(self):
        if self._settings is not None:
            # Faqat kamera/bo'lim ro'yxati — boshqa maydonlardagi saqlanmagan
            # tahrirlar (masalan, Telegram token) o'chib ketmasin.
            self._settings._refresh_cameras()
        for page in (self._violations, self._analytics):
            if page is not None:
                page.reload_departments()
        self._users_loaded = False
        self._sb_status.setText("Bo'limlar yangilandi")

    def _save_screenshot(self):
        ss_dir = Path("screenshots")
        ss_dir.mkdir(exist_ok=True)
        ts   = int(time.time())
        path = str(ss_dir / f"screenshot_{ts}.jpg")

        first_panel = next(iter(self._dashboard._panels.values()), None)
        if first_panel:
            video = first_panel._video
            src = video.image() if hasattr(video, "image") else None
            if src is None or src.isNull():
                src = video.pixmap() if hasattr(video, "pixmap") else None
            if src is not None and not src.isNull():
                full = str(Path(path).resolve())
                if src.save(full, "JPEG", 95):
                    self._sb_status.setText(f"Skrinshot saqlandi: {full}")
                    show_toast(self, f"Skrinshot saqlandi: {full}", "success", 5000)
                else:
                    self._sb_status.setText("Skrinshot saqlanmadi")
                    show_toast(self, f"Skrinshot saqlanmadi: {full}", "error")
                return
        self._sb_status.setText("Skrinshot: video kadr topilmadi")
        show_toast(self, "Skrinshot: video kadr topilmadi", "warning")

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
            if not self._settings._dirty:
                self._settings._load_values()

    # тФАтФА Yopish тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА

    def showEvent(self, event):
        super().showEvent(event)
        self._enable_native_min_max()

    def _enable_native_min_max(self):
        """
        Ramkasiz oynada ham taskbar'dan bosib yig'ish/ochish va Win+↑/↓
        ishlashi uchun WS_MINIMIZEBOX / WS_MAXIMIZEBOX / WS_SYSMENU yoqiladi.
        """
        if sys.platform != "win32" or getattr(self, "_native_styles_set", False):
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_STYLE = -16
            WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00080000, 0x00020000, 0x00010000
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
            self._native_styles_set = True
        except Exception:
            pass

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "_navbar"):
            self._navbar.update_window_state(self.isMaximized() or self.isFullScreen())

    def closeEvent(self, event):
        cam_count = self._runtime.worker_count
        reply = AppMessageBox.question(
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

