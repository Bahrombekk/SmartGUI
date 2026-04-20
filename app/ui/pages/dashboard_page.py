import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QScrollArea, QPushButton, QGridLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from app.ui.theme import C
from app.ui.widgets.camera_panel import CameraPanel
from app.ui.widgets.violation_card import ViolationCard, ViolationDetailDialog


# ══════════════════════════════════════════════════════════════════════════════
#  DashboardPage
# ══════════════════════════════════════════════════════════════════════════════

class DashboardPage(QWidget):
    """Asosiy dashboard sahifasi — ko'p kamera qo'llab-quvvatlash."""

    go_violations = pyqtSignal()

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        self.db  = db
        self.cfg = config_manager

        self._recent_violations: list = []
        self._max_recent = 8
        self._panels: dict[int, CameraPanel] = {}
        self._today_per_cam: dict[int, int] = {}

        self._setup_ui()
        self._refresh_stats()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_stats)
        self._timer.start(30_000)

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(10)

        self._cameras_scroll = QScrollArea()
        self._cameras_scroll.setWidgetResizable(True)
        self._cameras_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cameras_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._cameras_container = QWidget()
        self._cameras_grid = QGridLayout(self._cameras_container)
        self._cameras_grid.setSpacing(10)
        self._cameras_grid.setContentsMargins(0, 0, 0, 0)
        self._cameras_scroll.setWidget(self._cameras_container)
        root.addWidget(self._cameras_scroll, 1)

        root.addWidget(self._make_bottom_bar())

    # ── Bottom bar ────────────────────────────────────────────────────────

    def _make_bottom_bar(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        frame.setFixedHeight(200)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        title = QLabel("Oxirgi buzilishlar")
        title.setStyleSheet(
            f"color:{C('text_primary')};font-size:13px;font-weight:bold;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        all_btn = QPushButton("Barchasi →")
        all_btn.setFixedHeight(26)
        all_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent;color:{C('accent')};
                border:none;font-size:12px;
            }}
            QPushButton:hover {{ color:{C('accent_hover')}; }}
        """)
        all_btn.clicked.connect(self.go_violations)
        hdr.addWidget(all_btn)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)

        self._cards_container = QWidget()
        self._cards_row = QHBoxLayout(self._cards_container)
        self._cards_row.setContentsMargins(0, 0, 0, 0)
        self._cards_row.setSpacing(8)
        self._cards_row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._empty_lbl = QLabel("Hali buzilish aniqlanmagan")
        self._empty_lbl.setStyleSheet(
            f"color:{C('text_muted')};font-size:12px;"
        )
        self._cards_row.addWidget(self._empty_lbl)

        scroll.setWidget(self._cards_container)
        lay.addWidget(scroll)
        return frame

    # ── Kamera panellari boshqaruvi ───────────────────────────────────────

    def setup_cameras(self, cameras: list):
        for panel in self._panels.values():
            panel.deleteLater()
        self._panels.clear()
        self._today_per_cam.clear()

        while self._cameras_grid.count():
            item = self._cameras_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not cameras:
            no_lbl = QLabel("Faol kamera yo'q.\nSozlamalarda kamera qo'shing.")
            no_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_lbl.setStyleSheet(
                f"color:{C('text_muted')};font-size:14px;"
            )
            self._cameras_grid.addWidget(no_lbl, 0, 0)
            self._g_cams.setText("0")
            return

        cols = 1 if len(cameras) == 1 else 2 if len(cameras) <= 4 else 3

        for idx, cam in enumerate(cameras):
            cam_id = cam.get("id", idx + 1)
            panel = CameraPanel(
                cam_id     = cam_id,
                cam_name   = cam.get("name", f"Kamera {cam_id}"),
                rtsp_url   = cam.get("rtsp_url", ""),
                company_id = cam.get("company_id", ""),
            )
            self._panels[cam_id] = panel
            self._today_per_cam[cam_id] = 0

            row = idx // cols
            col = idx % cols

            panel.setMinimumHeight(440 if len(cameras) == 1 else 280)
            self._cameras_grid.addWidget(panel, row, col)

        for c in range(cols):
            self._cameras_grid.setColumnStretch(c, 1)

        pass

    # ── Tashqi yangilanishlar ─────────────────────────────────────────────

    def update_frame(self, cam_id: int, frame: np.ndarray):
        panel = self._panels.get(cam_id)
        if panel:
            panel.set_frame(frame)

    def on_violation(self, data: dict):
        self._recent_violations.insert(0, data)
        if len(self._recent_violations) > self._max_recent:
            self._recent_violations.pop()

        self._rebuild_recent_cards()
        self._refresh_stats()

    def on_stats(self, cam_id: int, stats: dict):
        panel = self._panels.get(cam_id)
        if not panel:
            return
        fps     = stats.get("fps", 0.0)
        persons = stats.get("active_persons", 0)
        today   = stats.get("today_count", 0)
        conn    = stats.get("connected", False)
        self._today_per_cam[cam_id] = today
        panel.set_stats(fps, persons, today, conn)

    def on_status(self, _cam_id: int, _text: str):
        pass

    def on_error(self, cam_id: int, msg: str):
        panel = self._panels.get(cam_id)
        if panel:
            panel.set_error(msg)

    def on_model_loaded(self, cam_id: int):
        panel = self._panels.get(cam_id)
        if panel:
            panel.set_model_loading()

    # ── Ichki metodlar ────────────────────────────────────────────────────

    def _refresh_stats(self):
        pass

    def _rebuild_recent_cards(self):
        while self._cards_row.count():
            item = self._cards_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._recent_violations:
            self._cards_row.addWidget(self._empty_lbl)
            return

        for v in self._recent_violations:
            card = ViolationCard(v)
            card.clicked.connect(self._open_detail)
            self._cards_row.addWidget(card)
        self._cards_row.addStretch()

    def _open_detail(self, violation: dict):
        dlg = ViolationDetailDialog(violation, self)
        dlg.exec()

    def set_total_persons(self, count: int):
        pass
