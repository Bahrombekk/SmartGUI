import numpy as np
from datetime import datetime
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

        root.addWidget(self._make_top_bar())

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

    # ── Top bar (stat kartalar) ───────────────────────────────────────────

    def _make_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(72)
        bar.setStyleSheet(
            f"background:{C('bg_panel')};"
            f"border:1px solid {C('border')};"
            f"border-radius:10px;"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(6)

        self._g_today   = self._stat_card(lay, "⚠", "Bugungi",   C('warning'),  C('warning_dim'))
        lay.addWidget(self._vsep())
        self._g_total   = self._stat_card(lay, "◆", "Jami",      C('info'),     C('info_dim'))
        lay.addWidget(self._vsep())
        self._g_cams    = self._stat_card(lay, "📷", "Kameralar", C('accent'),   C('accent_dim'))
        lay.addWidget(self._vsep())
        self._g_persons = self._stat_card(lay, "◉", "Odamlar",   C('success'),  C('success_dim'))

        lay.addStretch()

        # Oxirgi buzilish
        right = QVBoxLayout()
        right.setSpacing(2)
        top_r = QLabel("Oxirgi buzilish")
        top_r.setStyleSheet(
            f"color:{C('text_muted')};font-size:10px;background:transparent;"
        )
        self._last_viol_lbl = QLabel("—")
        self._last_viol_lbl.setStyleSheet(
            f"color:{C('text_secondary')};font-size:12px;background:transparent;"
        )
        self._last_viol_lbl.setWordWrap(True)
        self._last_viol_lbl.setMaximumWidth(260)
        right.addWidget(top_r)
        right.addWidget(self._last_viol_lbl)
        lay.addLayout(right)

        return bar

    def _stat_card(self, parent_lay: QHBoxLayout,
                   icon: str, label: str,
                   color: str, bg: str) -> QLabel:
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(8, 0, 8, 0)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(5)

        icon_bg = QLabel(icon)
        icon_bg.setFixedSize(24, 24)
        icon_bg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_bg.setStyleSheet(
            f"color:{color};font-size:14px;"
            f"background:{bg};border-radius:5px;"
        )
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color:{C('text_muted')};font-size:10px;background:transparent;"
        )
        icon_row.addWidget(icon_bg)
        icon_row.addWidget(lbl)
        icon_row.addStretch()

        val_lbl = QLabel("0")
        val_lbl.setStyleSheet(
            f"color:{color};font-size:22px;font-weight:bold;background:transparent;"
        )
        col.addLayout(icon_row)
        col.addWidget(val_lbl)

        parent_lay.addLayout(col)
        return val_lbl

    @staticmethod
    def _vsep() -> QFrame:
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setFixedHeight(44)
        sep.setStyleSheet(f"background:{C('border')};")
        return sep

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

        self._g_cams.setText(str(len(cameras)))

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

        ts = data.get("timestamp", 0)
        dt = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M:%S") if ts else "—"
        cam = data.get("camera", "?")
        self._last_viol_lbl.setText(
            f"{dt}  ·  {cam}  (ID:{data.get('track_id','?')})"
        )

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
        today = self.db.get_today_count()
        total = self.db.get_total_count()
        self._g_today.setText(str(today))
        self._g_total.setText(str(total))

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

    # ── Eski API compat ───────────────────────────────────────────────────

    def update_frame_single(self, frame: np.ndarray):
        if self._panels:
            first_id = next(iter(self._panels))
            self._panels[first_id].set_frame(frame)

    def set_active_cameras_count(self, count: int):
        self._g_cams.setText(str(count))

    def set_total_persons(self, count: int):
        self._g_persons.setText(str(count))
