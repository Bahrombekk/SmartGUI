"""
ViolationsPage — barcha buzilishlar galereyasi.
Sana filtri, galereya ko'rinishi.
"""

from datetime import date, timedelta

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QScrollArea, QGridLayout, QPushButton,
                              QDateEdit, QSizePolicy, QMessageBox)
from PyQt6.QtCore import Qt, QDate, QTimer
from PyQt6.QtGui import QFont

from app.ui.theme import C
from app.ui.widgets.violation_card import ViolationCard, ViolationDetailDialog


class ViolationsPage(QWidget):
    """Buzilishlar galereyasi sahifasi."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._violations = []
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

        # Sarlavha
        title = QLabel("Buzilishlar jurnali")
        font  = QFont()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color: {C('text_primary')};")
        f_layout.addWidget(title)

        f_layout.addStretch()

        # Tez filtrlar
        for label, days in [("Bugun", 0), ("Hafta", 7), ("Oy", 30), ("Barchasi", -1)]:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setProperty("_days", days)
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

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {C('border')};")
        f_layout.addWidget(sep)

        # Sana range
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

    # ── Ma'lumot yuklash ──────────────────────────────────────────────────

    def _load_violations(self):
        """DB dan filtr bo'yicha yuklash."""
        d_from = self._date_from.date().toPyDate()
        d_to   = self._date_to.date().toPyDate()

        self._violations = self.db.get_violations(
            date_from=d_from, date_to=d_to, limit=300
        )
        self._count_lbl.setText(
            f"{len(self._violations)} ta buzilish topildi  "
            f"({d_from.strftime('%d.%m.%Y')} – {d_to.strftime('%d.%m.%Y')})"
        )
        self._rebuild_grid()

    def _quick_filter(self, days: int):
        """Tez filtr tugmasi."""
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
        # Eski widgetlarni tozalash
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
        """Yangi buzilish kelganda (worker signali)."""
        self._load_violations()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Grid ustunlarini o'lchamga moslash
        QTimer.singleShot(50, self._rebuild_grid)
