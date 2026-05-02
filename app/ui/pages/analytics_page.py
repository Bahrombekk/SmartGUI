from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.application.services.analytics_service import AnalyticsService
from app.ui.theme import C
from app.ui.ui_kit import add_summary_metric, button_style, chip_style, panel_style, soft_card_style
from app.ui.widgets.bar_chart import BarChart, HourlyBarChart, LineChart


class _SectionCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("analyticsSection")
        self.setStyleSheet(panel_style("analyticsSection"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {C('text_primary')}; font-size: 14px; font-weight: 900;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._hdr_row = hdr
        lay.addLayout(hdr)

        self._body = QVBoxLayout()
        self._body.setSpacing(8)
        lay.addLayout(self._body)

    def add_header_widget(self, widget):
        self._hdr_row.addWidget(widget)

    def add_body_widget(self, widget):
        self._body.addWidget(widget)


class AnalyticsPage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.analytics = AnalyticsService(db)
        self._setup_ui()
        self._load_all()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load_all)
        self._timer.start(300_000)

    def _setup_ui(self):
        self.setStyleSheet(f"background: {C('bg_main')};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        top = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Analytics")
        title.setStyleSheet(f"color: {C('text_primary')}; font-size: 22px; font-weight: 900;")
        title_col.addWidget(title)
        subtitle = QLabel("Violation trends by time, camera and operational health")
        subtitle.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        title_col.addWidget(subtitle)
        top.addLayout(title_col)
        top.addStretch()
        refresh = QPushButton("Refresh")
        refresh.setFixedHeight(34)
        refresh.setStyleSheet(button_style("secondary"))
        refresh.clicked.connect(self._load_all)
        top.addWidget(refresh)
        root.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        c = QVBoxLayout(container)
        c.setContentsMargins(0, 0, 4, 0)
        c.setSpacing(12)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        self._stats_labels = {
            "today": add_summary_metric(summary, "Today", "0", C("danger")),
            "week": add_summary_metric(summary, "This Week", "0", C("accent_light")),
            "month": add_summary_metric(summary, "This Month", "0", C("warning")),
            "total": add_summary_metric(summary, "Total", "0", C("text_primary")),
        }
        c.addLayout(summary)

        daily = _SectionCard("Daily violations")
        self._days_combo = QComboBox()
        self._days_combo.addItems(["14 days", "30 days", "60 days", "90 days"])
        self._days_combo.setCurrentIndex(1)
        self._days_combo.setFixedWidth(100)
        self._days_combo.currentIndexChanged.connect(self._load_daily)
        daily.add_header_widget(self._days_combo)
        self._bar_chart = BarChart()
        self._bar_chart.setMinimumHeight(210)
        daily.add_body_widget(self._bar_chart)
        c.addWidget(daily)

        middle = QHBoxLayout()
        weekly = _SectionCard("Weekly trend")
        self._line_chart = LineChart()
        self._line_chart.setMinimumHeight(190)
        weekly.add_body_widget(self._line_chart)
        middle.addWidget(weekly, 2)

        ranking = _SectionCard("Camera ranking")
        self._ranking_layout = QVBoxLayout()
        self._ranking_layout.setSpacing(7)
        ranking._body.addLayout(self._ranking_layout)
        middle.addWidget(ranking, 1)
        c.addLayout(middle)

        hourly = _SectionCard("Today's hourly distribution")
        self._hourly_chart = HourlyBarChart()
        self._hourly_chart.setMinimumHeight(170)
        hourly.add_body_widget(self._hourly_chart)
        c.addWidget(hourly)
        c.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def _load_all(self):
        self._load_summary()
        self._load_daily()
        self._load_weekly()
        self._load_hourly()
        self._load_ranking()

    def _load_summary(self):
        data = self.analytics.summary_counts()
        for key, label in self._stats_labels.items():
            label.setText(str(data.get(key, 0)))

    def _load_daily(self):
        days = {0: 14, 1: 30, 2: 60, 3: 90}.get(self._days_combo.currentIndex(), 30)
        self._bar_chart.set_data(self.analytics.daily_counts(days=days))

    def _load_weekly(self):
        self._line_chart.set_data(self.analytics.weekly_counts(weeks=8))

    def _load_hourly(self):
        self._hourly_chart.set_data(self.analytics.hourly_counts(target_date=date.today()))

    def _load_ranking(self):
        while self._ranking_layout.count():
            item = self._ranking_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.analytics.camera_ranking(limit=6)
        if not rows:
            empty = QLabel("No camera data yet")
            empty.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
            self._ranking_layout.addWidget(empty)
            return
        max_count = max(row["count"] for row in rows)
        for row in rows:
            self._ranking_layout.addWidget(self._ranking_row(row["camera_name"], row["count"], max_count))

    def _ranking_row(self, name: str, count: int, max_count: int) -> QWidget:
        w = QFrame()
        w.setStyleSheet(soft_card_style())
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        n = QLabel(name)
        n.setStyleSheet(f"color: {C('text_primary')}; font-size: 12px; font-weight: 800;")
        lay.addWidget(n, 1)
        bar = QFrame()
        bar.setFixedSize(max(24, int(118 * count / max(max_count, 1))), 7)
        bar.setStyleSheet(f"background: {C('accent')}; border: none; border-radius: 3px;")
        lay.addWidget(bar)
        c = QLabel(str(count))
        c.setStyleSheet(chip_style(C("accent_light"), "rgba(249,115,22,0.10)"))
        lay.addWidget(c)
        return w

    def refresh(self):
        self._load_all()
