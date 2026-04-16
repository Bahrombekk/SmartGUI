"""
AnalyticsPage — kunlik / haftalik / soatlik grafik sahifasi.
"""

from datetime import date

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QScrollArea, QPushButton, QComboBox,
                              QSizePolicy)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from app.utils.theme import C
from app.widgets.bar_chart import BarChart, LineChart, HourlyBarChart


class _SectionCard(QFrame):
    """Sarlavhali va chart joylashadigan kartochka."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel(title)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        lbl.setFont(font)
        lbl.setStyleSheet(f"color: {C('text_primary')};")
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._hdr_row = hdr
        layout.addLayout(hdr)

        self._body = QVBoxLayout()
        layout.addLayout(self._body)

    def add_header_widget(self, widget):
        self._hdr_row.addWidget(widget)

    def add_body_widget(self, widget):
        self._body.addWidget(widget)


class AnalyticsPage(QWidget):
    """Analitika sahifasi."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._setup_ui()
        self._load_all()

        # Har 5 daqiqada yangilash
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load_all)
        self._timer.start(300_000)

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(12)

        # Sarlavha + Yangilash tugma
        top = QHBoxLayout()
        title = QLabel("Analitika")
        font  = QFont()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color: {C('text_primary')};")
        top.addWidget(title)
        top.addStretch()

        refresh_btn = QPushButton("⟳  Yangilash")
        refresh_btn.clicked.connect(self._load_all)
        refresh_btn.setFixedHeight(30)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('bg_input')};
                color: {C('text_secondary')};
                border: 1px solid {C('border')};
                border-radius: 5px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{ color: {C('accent')}; border-color: {C('accent')}; }}
        """)
        top.addWidget(refresh_btn)
        root.addLayout(top)

        # Scroll qilish imkoni
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        c_layout  = QVBoxLayout(container)
        c_layout.setSpacing(12)
        c_layout.setContentsMargins(0, 0, 4, 0)

        # ── Umumiy statistika kartalar ───────────────────────────────────
        summary_frame = QFrame()
        summary_frame.setProperty("card", True)
        s_layout = QHBoxLayout(summary_frame)
        s_layout.setContentsMargins(16, 12, 16, 12)
        s_layout.setSpacing(0)

        self._stats_labels = {}
        for key, title_txt, color in [
            ("today",   "Bugun",          C("danger")),
            ("week",    "Bu hafta",       C("accent")),
            ("month",   "Bu oy",          C("warning")),
            ("total",   "Jami",           C("text_primary")),
        ]:
            col = QVBoxLayout()
            col.setSpacing(4)
            val_lbl = QLabel("—")
            val_font = QFont()
            val_font.setPointSize(22)
            val_font.setBold(True)
            val_lbl.setFont(val_font)
            val_lbl.setStyleSheet(f"color: {color}; background: transparent;")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(val_lbl)

            ttl_lbl = QLabel(title_txt)
            ttl_lbl.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 11px; background: transparent;"
            )
            ttl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(ttl_lbl)

            s_layout.addLayout(col, 1)

            # Separator (oxirgidan tashqari)
            if key != "total":
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(f"color: {C('border')};")
                s_layout.addWidget(sep)

            self._stats_labels[key] = val_lbl

        c_layout.addWidget(summary_frame)

        # ── Kunlik chart (oxirgi 30 kun) ──────────────────────────────────
        daily_card = _SectionCard("Kunlik buzilishlar (oxirgi 30 kun)")

        self._days_combo = QComboBox()
        self._days_combo.addItems(["14 kun", "30 kun", "60 kun", "90 kun"])
        self._days_combo.setCurrentIndex(1)
        self._days_combo.setFixedWidth(90)
        self._days_combo.currentIndexChanged.connect(self._load_daily)
        daily_card.add_header_widget(self._days_combo)

        self._bar_chart = BarChart()
        self._bar_chart.setMinimumHeight(200)
        daily_card.add_body_widget(self._bar_chart)
        c_layout.addWidget(daily_card)

        # ── Haftalik trend ────────────────────────────────────────────────
        weekly_card = _SectionCard("Haftalik trend (oxirgi 8 hafta)")
        self._line_chart = LineChart()
        self._line_chart.setMinimumHeight(180)
        weekly_card.add_body_widget(self._line_chart)
        c_layout.addWidget(weekly_card)

        # ── Soatlik taqsimot ──────────────────────────────────────────────
        hourly_card = _SectionCard("Bugungi soatlik taqsimot")
        self._hourly_chart = HourlyBarChart()
        self._hourly_chart.setMinimumHeight(160)
        hourly_card.add_body_widget(self._hourly_chart)

        # Izoh
        legend = QHBoxLayout()
        for color, text in [(C("accent"), "Ish vaqti (08–18)"),
                             (C("success"), "Ish vaqtidan tashqari")]:
            dot = QLabel("■")
            dot.setStyleSheet(f"color: {color}; font-size: 14px;")
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
            legend.addWidget(dot)
            legend.addWidget(lbl)
            legend.addSpacing(12)
        legend.addStretch()
        hourly_card._body.addLayout(legend)

        c_layout.addWidget(hourly_card)
        c_layout.addStretch()

        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    # ── Ma'lumot yuklash ──────────────────────────────────────────────────

    def _load_all(self):
        self._load_summary()
        self._load_daily()
        self._load_weekly()
        self._load_hourly()

    def _load_summary(self):
        from datetime import date, timedelta, datetime

        today = date.today()
        week_start  = today - timedelta(days=today.weekday())
        month_start = date(today.year, today.month, 1)

        today_data = self.db.get_violations(date_from=today, date_to=today, limit=10000)
        week_data  = self.db.get_violations(date_from=week_start, date_to=today, limit=10000)
        month_data = self.db.get_violations(date_from=month_start, date_to=today, limit=10000)
        total      = self.db.get_total_count()

        self._stats_labels["today"].setText(str(len(today_data)))
        self._stats_labels["week"].setText(str(len(week_data)))
        self._stats_labels["month"].setText(str(len(month_data)))
        self._stats_labels["total"].setText(str(total))

    def _load_daily(self):
        days_map = {0: 14, 1: 30, 2: 60, 3: 90}
        days = days_map.get(self._days_combo.currentIndex(), 30)
        data = self.db.get_daily_counts(days=days)
        self._bar_chart.set_data(data)

    def _load_weekly(self):
        data = self.db.get_weekly_counts(weeks=8)
        self._line_chart.set_data(data)

    def _load_hourly(self):
        data = self.db.get_hourly_counts(target_date=date.today())
        self._hourly_chart.set_data(data)

    # ── Tashqi yangilanish ────────────────────────────────────────────────

    def refresh(self):
        """Violations page dan chaqiriladi."""
        self._load_all()
