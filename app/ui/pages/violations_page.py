"""
ViolationsPage — barcha buzilishlar galereyasi.
Sana filtri, galereya ko'rinishi.

Non-blocking: DB so'rovlari background thread da ishlaydi.
"""

import threading
from datetime import date, timedelta

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QScrollArea, QGridLayout, QPushButton,
                              QDateEdit, QSizePolicy, QMessageBox)
from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from app.ui.theme import C
from app.ui.widgets.violation_card import ViolationCard, ViolationDetailDialog

# Sahifada ko'rsatiladigan maksimal karta soni
_PAGE_LIMIT = 50


class ViolationsPage(QWidget):
    """Buzilishlar galereyasi sahifasi."""

    # Background thread → main thread
    _data_ready = pyqtSignal(list, str)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._violations = []
        self._loading = False
        self._pending_reload = False

        self._data_ready.connect(self._on_data_ready)
        self._setup_ui()
        self._load_violations()

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        # ── Filtr panel ──────────────────────────────────────────────────
        filter_frame = QFrame()
        filter_frame.setProperty("card", True)
        filter_frame.setFixedHeight(56)
        f_layout = QHBoxLayout(filter_frame)
        f_layout.setContentsMargins(12, 8, 12, 8)
        f_layout.setSpacing(10)

        title = QLabel("Buzilishlar jurnali")
        font  = QFont()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color: {C('text_primary')};")
        f_layout.addWidget(title)

        f_layout.addStretch()

        for label, days in [("Bugun", 0), ("Hafta", 7), ("Oy", 30), ("Barchasi", -1)]:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, d=days: self._quick_filter(d))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C('bg_input')};
                    color: {C('text_secondary')};
                    border: 1px solid {C('border')};
                    border-radius: 5px;
                    padding: 0 12px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    border-color: {C('accent')};
                    color: {C('accent')};
                }}
            """)
            f_layout.addWidget(btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {C('border')};")
        f_layout.addWidget(sep)

        date_lbl = QLabel("Dan:")
        date_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        f_layout.addWidget(date_lbl)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-30))
        self._date_from.setFixedWidth(110)
        f_layout.addWidget(self._date_from)

        to_lbl = QLabel("Gacha:")
        to_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        f_layout.addWidget(to_lbl)

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setFixedWidth(110)
        f_layout.addWidget(self._date_to)

        search_btn = QPushButton("Qidirish")
        search_btn.setFixedHeight(30)
        search_btn.setProperty("accent", True)
        search_btn.clicked.connect(self._load_violations)
        search_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('accent')};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {C('accent_hover')}; }}
        """)
        f_layout.addWidget(search_btn)

        root.addWidget(filter_frame)

        # ── Natija ma'lumoti ─────────────────────────────────────────────
        info_row = QHBoxLayout()
        self._count_lbl = QLabel("Natijalar yuklanmoqda...")
        self._count_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        info_row.addWidget(self._count_lbl)
        info_row.addStretch()

        refresh_btn = QPushButton("⟳  Yangilash")
        refresh_btn.setFixedHeight(26)
        refresh_btn.clicked.connect(self._load_violations)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C('text_muted')};
                border: 1px solid {C('border')};
                border-radius: 4px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {C('text_primary')}; }}
        """)
        info_row.addWidget(refresh_btn)
        root.addLayout(info_row)

        # ── Galereya ─────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self._grid_widget)
        root.addWidget(scroll, 1)

    # ── Ma'lumot yuklash (non-blocking) ──────────────────────────────────

    def _load_violations(self):
        """Background thread da yuklanadi — main thread bloklamaydi."""
        if self._loading:
            # Hozir yuklanmoqda — tugagach qayta yukla
            self._pending_reload = True
            return

        self._loading = True
        self._pending_reload = False
        self._count_lbl.setText("Yuklanmoqda...")

        d_from = self._date_from.date().toPyDate()
        d_to   = self._date_to.date().toPyDate()

        def _bg():
            try:
                violations = self.db.get_violations(
                    date_from=d_from,
                    date_to=d_to,
                    limit=_PAGE_LIMIT,
                )
                status = (
                    f"{len(violations)} ta buzilish  "
                    f"({d_from.strftime('%d.%m.%Y')} – {d_to.strftime('%d.%m.%Y')})"
                )
                self._data_ready.emit(violations, status)
            except Exception as e:
                self._data_ready.emit([], f"Xatolik: {e}")

        threading.Thread(target=_bg, daemon=True, name="ViolLoad").start()

    def _on_data_ready(self, violations: list, status_text: str):
        """Background thread dan kelgan natijani UI ga qo'yish (main thread)."""
        self._loading = False
        self._violations = violations
        self._count_lbl.setText(status_text)
        self._rebuild_grid()

        # Agar yangi reload so'rovi kelgan bo'lsa
        if self._pending_reload:
            QTimer.singleShot(300, self._load_violations)

    def _quick_filter(self, days: int):
        today = date.today()
        if days == 0:
            d_from = today
        elif days > 0:
            d_from = today - timedelta(days=days)
        else:
            d_from = date(2000, 1, 1)

        self._date_from.setDate(QDate(d_from.year, d_from.month, d_from.day))
        self._date_to.setDate(QDate(today.year, today.month, today.day))
        self._load_violations()

    def _rebuild_grid(self):
        """Galereya gridini qayta qurish."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._violations:
            empty = QLabel("Bu davr uchun buzilishlar topilmadi")
            empty.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 13px; padding: 40px;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(empty, 0, 0)
            return

        cols = max(1, self._grid_widget.width() // 175)
        for idx, v in enumerate(self._violations):
            row = idx // cols
            col = idx % cols
            card = ViolationCard(v)
            card.clicked.connect(self._open_detail)
            self._grid.addWidget(card, row, col)

    def _open_detail(self, violation: dict):
        dlg = ViolationDetailDialog(violation, self)
        dlg.exec()

    # ── Tashqi yangilanish ────────────────────────────────────────────────

    def add_new_violation(self, data: dict):
        """Yangi buzilish kelganda — qotmaydigan rejimda deferred reload."""
        if self._loading:
            self._pending_reload = True
        else:
            # 500ms kutib reload — violation writer DB ni yozib tugagunicha
            QTimer.singleShot(500, self._load_violations)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(50, self._rebuild_grid)
