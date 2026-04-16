"""
Dashboard — asosiy sahifa.
Chap: live video feed.
O'ng: 4 ta statistika kartochkasi + oxirgi buzilishlar qatori.
"""

import numpy as np
from datetime import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QScrollArea, QSizePolicy, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from app.utils.theme import C
from app.widgets.video_label import VideoLabel
from app.widgets.stat_card import StatCard
from app.widgets.violation_card import ViolationCard, ViolationDetailDialog


class DashboardPage(QWidget):
    """Asosiy dashboard sahifasi."""

    # Violations sahifasiga o'tish signali
    go_violations = pyqtSignal()

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        self.db  = db
        self.cfg = config_manager

        self._recent_violations = []   # oxirgi N ta
        self._max_recent = 6

        self._setup_ui()
        self._refresh_stats()

        # Har 60 sekundda statistikani yangilash
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_stats)
        self._timer.start(60_000)

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        # ── Yuqori qism: video + stat kartalar ──────────────────────────
        top = QHBoxLayout()
        top.setSpacing(12)

        # Video
        self._video = VideoLabel()
        self._video.setMinimumSize(560, 380)
        self._video.show_connecting()
        top.addWidget(self._video, 3)

        # O'ng panel: stat kartalar + kamera info
        right = QVBoxLayout()
        right.setSpacing(10)

        # Sarlavha
        cam_lbl = QLabel(self.cfg.camera_name)
        cam_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 12px; font-weight: bold;"
        )
        right.addWidget(cam_lbl)

        # Ulanish holati
        self._status_lbl = QLabel("● Ulanmoqda...")
        self._status_lbl.setStyleSheet(f"color: {C('warning')}; font-size: 12px;")
        right.addWidget(self._status_lbl)

        right.addSpacing(6)

        # Stat kartalar
        cards_grid = QVBoxLayout()
        cards_grid.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._card_today = StatCard("Bugungi buzilishlar", "0",
                                    icon="⚠", color=C("danger"))
        self._card_total = StatCard("Jami buzilishlar", "0",
                                    icon="◆", color=C("accent"))
        row1.addWidget(self._card_today)
        row1.addWidget(self._card_total)
        cards_grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self._card_persons = StatCard("Hozirgi odamlar", "0",
                                      icon="◉", color=C("success"))
        self._card_fps = StatCard("FPS", "0",
                                   icon="⚡", color=C("text_secondary"))
        self._card_fps.set_color(C("text_secondary"))
        row2.addWidget(self._card_persons)
        row2.addWidget(self._card_fps)
        cards_grid.addLayout(row2)

        right.addLayout(cards_grid)
        right.addStretch()

        # Oxirgi buzilish vaqti
        self._last_viol_lbl = QLabel("Oxirgi buzilish: —")
        self._last_viol_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 11px;"
        )
        self._last_viol_lbl.setWordWrap(True)
        right.addWidget(self._last_viol_lbl)

        top.addLayout(right, 1)
        root.addLayout(top, 1)

        # ── Pastki qism: oxirgi buzilishlar thumbnaillari ────────────────
        bottom_frame = QFrame()
        bottom_frame.setProperty("card", True)
        bottom_frame.setFixedHeight(230)
        b_layout = QVBoxLayout(bottom_frame)
        b_layout.setContentsMargins(10, 8, 10, 8)
        b_layout.setSpacing(6)

        # Sarlavha + "Barchasi" tugma
        hdr = QHBoxLayout()
        recent_lbl = QLabel("Oxirgi buzilishlar")
        recent_lbl.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 13px; font-weight: bold;"
        )
        hdr.addWidget(recent_lbl)
        hdr.addStretch()

        all_btn = QPushButton("Barchasi →")
        all_btn.setFixedHeight(26)
        all_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C('accent')};
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{ color: {C('accent_hover')}; }}
        """)
        all_btn.clicked.connect(self.go_violations)
        hdr.addWidget(all_btn)
        b_layout.addLayout(hdr)

        # Scroll area (kartalar)
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
            f"color: {C('text_muted')}; font-size: 12px;"
        )
        self._cards_row.addWidget(self._empty_lbl)

        scroll.setWidget(self._cards_container)
        b_layout.addWidget(scroll)

        root.addWidget(bottom_frame)

    # ── Tashqi yangilanishlar ─────────────────────────────────────────────

    def update_frame(self, frame: np.ndarray):
        """DetectionWorker.frame_ready → video widget yangilash."""
        self._video.set_frame(frame)

    def on_violation(self, data: dict):
        """Yangi buzilish kelganda chaqiriladi."""
        self._recent_violations.insert(0, data)
        if len(self._recent_violations) > self._max_recent:
            self._recent_violations.pop()

        self._rebuild_recent_cards()
        self._refresh_stats()

        # Oxirgi buzilish vaqti
        ts = data.get("timestamp", 0)
        dt = datetime.fromtimestamp(ts).strftime("%d.%m.%Y  %H:%M:%S") if ts else "—"
        self._last_viol_lbl.setText(f"Oxirgi buzilish: {dt}  (ID: {data.get('track_id', '?')})")

    def on_stats(self, stats: dict):
        """DetectionWorker.stats_updated → kartalar yangilash."""
        fps     = stats.get("fps", 0.0)
        persons = stats.get("active_persons", 0)
        today   = stats.get("today_count", 0)
        conn    = stats.get("connected", False)

        self._card_fps.set_value(f"{fps:.1f}")
        self._card_persons.set_value(str(persons))
        self._card_today.set_value(str(today))

        if conn:
            self._status_lbl.setText("● Ulanган")
            self._status_lbl.setStyleSheet(f"color: {C('success')}; font-size: 12px;")
            self._video.reset_style()
        else:
            self._status_lbl.setText("● Qayta ulanmoqda...")
            self._status_lbl.setStyleSheet(f"color: {C('warning')}; font-size: 12px;")

    def on_status(self, text: str):
        """DetectionWorker.status_changed → holat matni."""
        pass  # StatusBar orqali main_window da ko'rsatiladi

    def on_error(self, msg: str):
        """Xatolik holati."""
        self._video.show_error(msg)
        self._status_lbl.setText("● Xatolik")
        self._status_lbl.setStyleSheet(f"color: {C('danger')}; font-size: 12px;")

    def on_model_loaded(self):
        """Model yuklandi — video kutmoqda."""
        self._video.show_connecting()
        self._status_lbl.setText("● Kameraga ulanmoqda...")
        self._status_lbl.setStyleSheet(f"color: {C('warning')}; font-size: 12px;")

    # ── Ichki metodlar ────────────────────────────────────────────────────

    def _refresh_stats(self):
        """DB dan yangi statistika olish."""
        today = self.db.get_today_count()
        total = self.db.get_total_count()
        self._card_today.set_value(str(today))
        self._card_total.set_value(str(total))

    def _rebuild_recent_cards(self):
        """Oxirgi buzilishlar qatorini qayta qurish."""
        # Eski widgetlarni o'chirish
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
