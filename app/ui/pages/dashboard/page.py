from __future__ import annotations

import datetime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QFrame

from app.ui.pages.dashboard.bottom_panels import DashboardBottomPanelsMixin
from app.ui.pages.dashboard.monitor import DashboardMonitorMixin
from app.ui.pages.dashboard.sidebar import DashboardSidebarMixin
from app.ui.pages.dashboard.styles import DashboardStylesMixin
from app.ui.widgets.camera_panel import CameraPanel


class DashboardPage(
    DashboardSidebarMixin,
    DashboardMonitorMixin,
    DashboardBottomPanelsMixin,
    DashboardStylesMixin,
    QWidget,
):
    """Asosiy dashboard sahifasi - SmartHelmet dizayni."""

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
        self._department_rows: dict[str, QFrame]   = {}
        self._department_row_keys: tuple[str, ...] = ()
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

    def setup_cameras(self, cameras: list):
        # Eski panellarni tozalash
        for p in self._panels.values():
            p.hide()
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
                item.widget().hide()
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
            self._rebuild_recent_events()
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
        self._rebuild_recent_events()
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
        today = data.get("today_count")
        if today is not None:
            if hasattr(self, "_detections_today_lbl"):
                self._detections_today_lbl.setText(str(today))
            if hasattr(self, "_no_helmet_today_lbl"):
                self._no_helmet_today_lbl.setText(str(today))

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
        self._rebuild_recent_events()
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

