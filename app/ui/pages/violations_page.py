from __future__ import annotations

import threading
from datetime import date, timedelta

from PyQt6.QtCore import QDate, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.application.services.analytics_service import AnalyticsService
from app.ui.theme import C
from app.ui.ui_kit import (
    add_summary_metric,
    button_style,
    input_style,
    make_empty_state,
    panel_style,
    responsive_columns,
)
from app.ui.widgets.violation_card import ViolationCard, ViolationDetailDialog

_PAGE_LIMIT = 60

_BTN_ACTIVE = (
    "QPushButton {"
    f"background: {C('accent_hover')}; color: #05090d;"
    "border: none; border-radius: 8px; font-weight: 900; padding: 0 14px;"
    "}"
)
_BTN_INACTIVE = button_style("secondary")


class ViolationsPage(QWidget):
    _data_ready = pyqtSignal(list, str, dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.analytics = AnalyticsService(db)
        self._violations: list[dict] = []
        self._loading = False
        self._pending_reload = False
        self._camera_filter = "All Cameras"
        self._active_period_idx = 1          # Week bosib turiladi default
        self._summary_labels: dict[str, QLabel] = {}
        self._period_btns: list[QPushButton] = []
        self._data_ready.connect(self._on_data_ready)
        self._setup_ui()
        self._load_violations()

    # ── UI qurish ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(f"background: {C('bg_main')};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # ── Sarlavha ───────────────────────────────────────────────────────
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Reports")
        title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 22px; font-weight: 900;"
        )
        title_col.addWidget(title)
        subtitle = QLabel("No Helmet evidence gallery — crop and full-frame review")
        subtitle.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 12px;"
        )
        header.addWidget(self._status_lbl)
        root.addLayout(header)

        # ── Summary kartalar ───────────────────────────────────────────────
        summary = QHBoxLayout()
        summary.setSpacing(10)
        self._summary_labels["today"] = add_summary_metric(
            summary, "Today", "—", C("danger")
        )
        self._summary_labels["week"] = add_summary_metric(
            summary, "Week", "—", C("accent_light")
        )
        self._summary_labels["month"] = add_summary_metric(
            summary, "Month", "—", C("warning")
        )
        self._summary_labels["total"] = add_summary_metric(
            summary, "Total", "—", C("text_primary")
        )
        root.addLayout(summary)

        # ── Filter panel ───────────────────────────────────────────────────
        filters = QFrame()
        filters.setObjectName("reportsFilters")
        filters.setStyleSheet(panel_style("reportsFilters"))
        f = QHBoxLayout(filters)
        f.setContentsMargins(12, 10, 12, 10)
        f.setSpacing(8)

        for i, (label, days) in enumerate(
            [("Today", 0), ("Week", 7), ("Month", 30), ("All", -1)]
        ):
            btn = QPushButton(label)
            btn.setFixedHeight(34)
            btn.setStyleSheet(
                _BTN_ACTIVE if i == self._active_period_idx else _BTN_INACTIVE
            )
            btn.clicked.connect(lambda _, d=days, idx=i: self._quick_filter(d, idx))
            f.addWidget(btn)
            self._period_btns.append(btn)

        f.addWidget(self._sep())

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-7))
        self._date_from.setFixedHeight(34)
        self._date_from.setStyleSheet(input_style())
        f.addWidget(self._date_from)

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setFixedHeight(34)
        self._date_to.setStyleSheet(input_style())
        f.addWidget(self._date_to)

        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All Cameras")
        self._camera_combo.setMinimumWidth(150)
        self._camera_combo.setFixedHeight(34)
        self._camera_combo.setStyleSheet(input_style())
        self._camera_combo.currentTextChanged.connect(self._on_camera_filter_changed)
        f.addWidget(self._camera_combo)

        f.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedHeight(34)
        apply_btn.setStyleSheet(button_style("primary"))
        apply_btn.clicked.connect(self._on_apply)
        f.addWidget(apply_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(34)
        refresh_btn.setStyleSheet(button_style("secondary"))
        refresh_btn.clicked.connect(self._load_violations)
        f.addWidget(refresh_btn)

        root.addWidget(filters)

        # ── Karta grid ─────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(0, 0, 4, 0)
        self._grid.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        scroll.setWidget(self._grid_widget)
        root.addWidget(scroll, 1)

    @staticmethod
    def _sep() -> QFrame:
        line = QFrame()
        line.setFixedWidth(1)
        line.setFixedHeight(24)
        line.setStyleSheet("background: rgba(148,163,184,0.18); border: none;")
        return line

    # ── Ma'lumot yuklash ──────────────────────────────────────────────────

    def _load_violations(self):
        if self._loading:
            self._pending_reload = True
            return
        self._loading = True
        self._pending_reload = False
        self._status_lbl.setText("Refreshing...")

        # Birinchi yuklanishda (grid bo'sh) placeholder ko'rsat
        if not self._violations:
            self._show_loading_state()

        d_from = self._date_from.date().toPyDate()
        d_to = self._date_to.date().toPyDate()
        camera_filter = self._camera_filter

        def _bg():
            try:
                rows = self.db.get_violations(
                    date_from=d_from, date_to=d_to, limit=_PAGE_LIMIT
                )
                if camera_filter != "All Cameras":
                    rows = [
                        v for v in rows
                        if str(v.get("camera_name") or "") == camera_filter
                    ]
                summary = self.analytics.summary_counts()
                status = self.analytics.format_range_status(len(rows), d_from, d_to)
                self._data_ready.emit(rows, status, summary)
            except Exception as exc:
                self._data_ready.emit([], f"Xatolik: {exc}", {})

        threading.Thread(target=_bg, daemon=True, name="ViolationsLoad").start()

    def _on_apply(self):
        self._set_active_period(-1)   # hech bir period tanlanganda aktiv emas
        self._load_violations()

    def _on_data_ready(self, violations: list, status_text: str, summary: dict):
        self._loading = False
        self._violations = violations
        self._status_lbl.setText(status_text)
        self._update_summary(summary)
        self._sync_camera_filter_options(violations)
        self._rebuild_grid()
        if self._pending_reload:
            QTimer.singleShot(300, self._load_violations)

    def _update_summary(self, summary: dict):
        for key, label in self._summary_labels.items():
            label.setText(str(summary.get(key, 0)))

    def _sync_camera_filter_options(self, violations: list[dict]):
        cameras = sorted(
            {str(v.get("camera_name") or "Unknown") for v in violations}
        )
        current = self._camera_filter
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        self._camera_combo.addItem("All Cameras")
        self._camera_combo.addItems(cameras)
        idx = self._camera_combo.findText(current)
        self._camera_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._camera_combo.blockSignals(False)

    def _on_camera_filter_changed(self, text: str):
        self._camera_filter = text or "All Cameras"
        self._load_violations()

    # ── Tez filter tugmalar ───────────────────────────────────────────────

    def _quick_filter(self, days: int, btn_idx: int):
        self._set_active_period(btn_idx)
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

    def _set_active_period(self, idx: int):
        self._active_period_idx = idx
        for i, btn in enumerate(self._period_btns):
            btn.setStyleSheet(_BTN_ACTIVE if i == idx else _BTN_INACTIVE)

    # ── Grid qurilishi ────────────────────────────────────────────────────

    def _show_loading_state(self):
        self._clear_grid()
        state = make_empty_state(
            "Loading evidence", "Violation gallery is loading.", "info"
        )
        state.setMinimumHeight(260)
        self._grid.addWidget(state, 0, 0)

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_grid(self):
        self._clear_grid()
        if not self._violations:
            state = make_empty_state(
                "No violations found",
                "Try another date range or camera filter.",
            )
            state.setMinimumHeight(280)
            self._grid.addWidget(state, 0, 0)
            return

        cols = responsive_columns(
            self._grid_widget.width(), card_width=256, minimum=1, maximum=5
        )
        for idx, violation in enumerate(self._violations):
            card = ViolationCard(violation)
            card.clicked.connect(self._open_detail)
            self._grid.addWidget(card, idx // cols, idx % cols)

    def _open_detail(self, violation: dict):
        dlg = ViolationDetailDialog(violation, self)
        dlg.exec()

    # ── Tashqi API ────────────────────────────────────────────────────────

    def add_new_violation(self, data: dict):
        if self._loading:
            self._pending_reload = True
        else:
            QTimer.singleShot(500, self._load_violations)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._loading:
            QTimer.singleShot(50, self._rebuild_grid)
