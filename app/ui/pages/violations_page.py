from __future__ import annotations

import threading
from collections import Counter
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QDate, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor
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
from app.ui.ui_kit import button_style, input_style, make_empty_state, panel_style, responsive_columns
from app.ui.widgets.violation_card import EvidenceImage, ViolationDetailDialog

_PAGE_LIMIT = 60

_BTN_ACTIVE = (
    "QPushButton {"
    f"background: {C('accent_hover')}; color: #05090d;"
    "border: none; border-radius: 8px; font-weight: 900; padding: 0 14px;"
    "}"
)
_BTN_INACTIVE = button_style("secondary")


def _fmt(value: int | float | None) -> str:
    return f"{int(value or 0):,}"


def _time_text(value) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value).strftime("%H:%M:%S")
    return "--:--:--"


def _date_text(value) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value).strftime("%d.%m.%Y")
    return "-"


def _type_style(vtype: str) -> tuple[str, str, str]:
    styles = {
        "no_helmet": ("NO HELMET", C("danger"), "rgba(239,68,68,0.14)"),
        "access_denied": ("ACCESS DENIED", C("accent"), "rgba(249,115,22,0.14)"),
        "unknown_person": ("UNKNOWN", C("text_secondary"), "rgba(148,163,184,0.12)"),
        "low_confidence": ("LOW CONF.", C("warning"), "rgba(251,191,36,0.14)"),
    }
    return styles.get(str(vtype or "no_helmet"), styles["no_helmet"])


class _EvidenceTile(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        label, accent, badge_bg = _type_style(str(violation.get("violation_type") or "no_helmet"))
        self.setMinimumSize(250, 276)
        self.setStyleSheet(
            "QFrame {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 rgba(13,23,32,0.96), stop:1 rgba(7,16,22,0.96));"
            "border: 1px solid rgba(148,163,184,0.13);"
            "border-radius: 8px;"
            "}"
            "QFrame:hover {"
            "border: 1px solid rgba(34,211,238,0.34);"
            "background: rgba(15,27,38,0.98);"
            "}"
            "QLabel { background: transparent; border: none; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(9)

        full_path = str(violation.get("full_path") or "")
        crop_path = str(violation.get("crop_path") or "")
        image = EvidenceImage(full_path or crop_path, "NO\nIMAGE", (250, 150))
        lay.addWidget(image, 0, Qt.AlignmentFlag.AlignCenter)

        top = QHBoxLayout()
        badge = QLabel(label)
        badge.setStyleSheet(
            f"color: {accent}; background: {badge_bg};"
            "border-radius: 6px; padding: 4px 8px; font-size: 9px; font-weight: 900;"
        )
        top.addWidget(badge)
        top.addStretch()
        conf = float(violation.get("confidence", 0) or 0) * 100
        conf_lbl = QLabel(f"{conf:.0f}%")
        conf_lbl.setStyleSheet(
            f"color: {C('accent_light')}; background: rgba(249,115,22,0.10);"
            "border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: 900;"
        )
        top.addWidget(conf_lbl)
        lay.addLayout(top)

        camera = QLabel(str(violation.get("camera_name") or "Unknown camera"))
        camera.setStyleSheet(f"color: {C('text_primary')}; font-size: 13px; font-weight: 900;")
        camera.setMaximumWidth(240)
        lay.addWidget(camera)

        meta = QHBoxLayout()
        track_id = QLabel(f"ID {violation.get('track_id', '?')}")
        track_id.setStyleSheet(f"color: {C('info')}; font-size: 11px; font-weight: 900;")
        meta.addWidget(track_id)
        meta.addStretch()
        time_lbl = QLabel(f"{_date_text(violation.get('timestamp'))}  {_time_text(violation.get('timestamp'))}")
        time_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 10px; font-weight: 700;")
        meta.addWidget(time_lbl)
        lay.addLayout(meta)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.violation)
            event.accept()
            return
        super().mousePressEvent(event)


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
        self._active_period_idx = 1
        self._summary_labels: dict[str, QLabel] = {}
        self._period_btns: list[QPushButton] = []
        self._data_ready.connect(self._on_data_ready)
        self._setup_ui()
        self._load_violations()

    def _setup_ui(self):
        self.setStyleSheet(f"background: {C('bg_main')};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Reports")
        title.setStyleSheet(f"color: {C('text_primary')}; font-size: 22px; font-weight: 900;")
        title_col.addWidget(title)
        subtitle = QLabel("Evidence board for reviewing no-helmet detections")
        subtitle.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {C('text_secondary')}; font-size: 12px;")
        header.addWidget(self._status_lbl)
        root.addLayout(header)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        for key, label, color, bg_tint in [
            ("today", "Bugun", C("danger"), "rgba(239,68,68,0.055)"),
            ("week", "Hafta", C("accent"), "rgba(249,115,22,0.055)"),
            ("month", "Oy", C("warning"), "rgba(251,191,36,0.055)"),
            ("total", "Jami", C("info"), "rgba(34,211,238,0.055)"),
        ]:
            self._summary_labels[key] = self._metric_card(summary, label, "0", color, bg_tint)
        root.addLayout(summary)

        root.addWidget(self._build_filter_panel())

        body = QHBoxLayout()
        body.setSpacing(10)

        board = QFrame()
        board.setObjectName("reportsBoard")
        board.setStyleSheet(panel_style("reportsBoard"))
        board_lay = QVBoxLayout(board)
        board_lay.setContentsMargins(12, 12, 12, 12)
        board_lay.setSpacing(10)

        board_head = QHBoxLayout()
        board_title = QLabel("Evidence Board")
        board_title.setStyleSheet(f"color: {C('text_primary')}; font-size: 15px; font-weight: 900;")
        board_head.addWidget(board_title)
        board_head.addStretch()
        self._count_badge = QLabel("0 items")
        self._count_badge.setStyleSheet(
            f"color: {C('info')}; background: rgba(34,211,238,0.10);"
            "border-radius: 7px; padding: 3px 8px; font-size: 11px; font-weight: 900;"
        )
        board_head.addWidget(self._count_badge)
        board_lay.addLayout(board_head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(0, 0, 4, 0)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._grid_widget)
        board_lay.addWidget(scroll, 1)
        body.addWidget(board, 1)

        insights = self._build_snapshot_panel()
        body.addWidget(insights)
        root.addLayout(body, 1)

    def _build_filter_panel(self) -> QFrame:
        filters = QFrame()
        filters.setObjectName("reportsFilters")
        filters.setStyleSheet(panel_style("reportsFilters"))
        outer = QHBoxLayout(filters)
        outer.setContentsMargins(10, 9, 10, 9)
        outer.setSpacing(10)

        period = QFrame()
        period.setStyleSheet("QFrame { background: rgba(2,6,23,0.32); border: 1px solid rgba(148,163,184,0.10); border-radius: 8px; }")
        p = QHBoxLayout(period)
        p.setContentsMargins(4, 4, 4, 4)
        p.setSpacing(4)
        for i, (label, days) in enumerate([("Today", 0), ("Week", 7), ("Month", 30), ("All", -1)]):
            btn = QPushButton(label)
            btn.setMinimumWidth(72)
            btn.setFixedHeight(32)
            btn.setStyleSheet(_BTN_ACTIVE if i == self._active_period_idx else _BTN_INACTIVE)
            btn.clicked.connect(lambda _, d=days, idx=i: self._quick_filter(d, idx))
            p.addWidget(btn)
            self._period_btns.append(btn)
        outer.addWidget(period, 0)

        date_group = QFrame()
        date_group.setStyleSheet("QFrame { background: transparent; border: none; } QLabel { background: transparent; border: none; }")
        d = QHBoxLayout(date_group)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(7)
        d.addWidget(self._filter_label("From"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("dd.MM.yyyy")
        self._date_from.setDate(QDate.currentDate().addDays(-7))
        self._date_from.setFixedSize(126, 34)
        self._date_from.setStyleSheet(input_style())
        d.addWidget(self._date_from)
        d.addWidget(self._filter_label("To"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("dd.MM.yyyy")
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setFixedSize(126, 34)
        self._date_to.setStyleSheet(input_style())
        d.addWidget(self._date_to)
        outer.addWidget(date_group, 0)

        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All Cameras")
        self._camera_combo.setMinimumWidth(170)
        self._camera_combo.setMaximumWidth(240)
        self._camera_combo.setFixedHeight(34)
        self._camera_combo.setStyleSheet(input_style())
        self._camera_combo.currentTextChanged.connect(self._on_camera_filter_changed)
        outer.addWidget(self._camera_combo, 1)
        outer.addStretch(2)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedSize(72, 34)
        apply_btn.setStyleSheet(button_style("primary"))
        apply_btn.clicked.connect(self._on_apply)
        outer.addWidget(apply_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedSize(82, 34)
        refresh_btn.setStyleSheet(button_style("secondary"))
        refresh_btn.clicked.connect(self._load_violations)
        outer.addWidget(refresh_btn)
        return filters

    def _build_snapshot_panel(self) -> QFrame:
        insights = QFrame()
        insights.setObjectName("reportsInsights")
        insights.setFixedWidth(328)
        insights.setStyleSheet(panel_style("reportsInsights"))
        i_lay = QVBoxLayout(insights)
        i_lay.setContentsMargins(12, 12, 12, 12)
        i_lay.setSpacing(10)

        head = QHBoxLayout()
        i_title = QLabel("Snapshot")
        i_title.setStyleSheet(f"color: {C('text_primary')}; font-size: 15px; font-weight: 900;")
        head.addWidget(i_title)
        head.addStretch()
        self._snapshot_range = QLabel("Week")
        self._snapshot_range.setStyleSheet(
            f"color: {C('accent_light')}; background: rgba(249,115,22,0.10);"
            "border-radius: 7px; padding: 3px 8px; font-size: 10px; font-weight: 900;"
        )
        head.addWidget(self._snapshot_range)
        i_lay.addLayout(head)

        self._insights_layout = QVBoxLayout()
        self._insights_layout.setSpacing(8)
        i_lay.addLayout(self._insights_layout)

        i_lay.addSpacing(4)
        section = QLabel("Top Cameras")
        section.setStyleSheet(f"color: {C('text_secondary')}; font-size: 11px; font-weight: 900;")
        i_lay.addWidget(section)
        self._camera_breakdown = QVBoxLayout()
        self._camera_breakdown.setSpacing(7)
        i_lay.addLayout(self._camera_breakdown)

        i_lay.addSpacing(4)
        actions = QLabel("Actions")
        actions.setStyleSheet(f"color: {C('text_secondary')}; font-size: 11px; font-weight: 900;")
        i_lay.addWidget(actions)
        for text in ["Export PDF", "Open latest", "Clear filters"]:
            btn = QPushButton(text)
            btn.setFixedHeight(32)
            btn.setStyleSheet(button_style("secondary"))
            if text == "Clear filters":
                btn.clicked.connect(lambda: self._quick_filter(7, 1))
            elif text == "Open latest":
                btn.clicked.connect(self._open_latest)
            i_lay.addWidget(btn)
        i_lay.addStretch()
        return insights

    @staticmethod
    def _metric_card(parent: QHBoxLayout, title: str, value: str, accent: str, bg_tint: str) -> QLabel:
        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            f"background: {bg_tint}; border-radius: 8px;"
            f"border-top: 2px solid {accent};"
            "border-left: 1px solid rgba(148,163,184,0.09);"
            "border-right: 1px solid rgba(148,163,184,0.09);"
            "border-bottom: 1px solid rgba(148,163,184,0.09);"
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(3)
        val_lbl = QLabel(value)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setStyleSheet(f"color: {accent}; font-size: 26px; font-weight: 900;")
        lay.addWidget(val_lbl)
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px; font-weight: 800;")
        lay.addWidget(title_lbl)
        parent.addWidget(card, 1)
        return val_lbl

    @staticmethod
    def _sep() -> QFrame:
        line = QFrame()
        line.setFixedWidth(1)
        line.setFixedHeight(24)
        line.setStyleSheet("background: rgba(148,163,184,0.18); border: none;")
        return line

    @staticmethod
    def _filter_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 10px; font-weight: 900;")
        return lbl

    def _load_violations(self):
        if self._loading:
            self._pending_reload = True
            return
        self._loading = True
        self._pending_reload = False
        self._status_lbl.setText("Refreshing...")
        if not self._violations:
            self._show_loading_state()

        d_from = self._date_from.date().toPyDate()
        d_to = self._date_to.date().toPyDate()
        camera_filter = self._camera_filter

        def _bg():
            try:
                rows = self.db.get_violations(date_from=d_from, date_to=d_to, limit=_PAGE_LIMIT)
                if camera_filter != "All Cameras":
                    rows = [v for v in rows if str(v.get("camera_name") or "") == camera_filter]
                summary = self.analytics.summary_counts()
                status = self.analytics.format_range_status(len(rows), d_from, d_to)
                self._data_ready.emit(rows, status, summary)
            except Exception as exc:
                self._data_ready.emit([], f"Xatolik: {exc}", {})

        threading.Thread(target=_bg, daemon=True, name="ViolationsLoad").start()

    def _on_apply(self):
        self._set_active_period(-1)
        self._load_violations()

    def _on_data_ready(self, violations: list, status_text: str, summary: dict):
        self._loading = False
        self._violations = violations
        self._status_lbl.setText(status_text)
        self._update_summary(summary)
        self._sync_camera_filter_options(violations)
        self._rebuild_grid()
        self._update_insights()
        if self._pending_reload:
            QTimer.singleShot(300, self._load_violations)

    def _update_summary(self, summary: dict):
        for key, label in self._summary_labels.items():
            label.setText(_fmt(summary.get(key, 0)))

    def _sync_camera_filter_options(self, violations: list[dict]):
        cameras = sorted({str(v.get("camera_name") or "Unknown") for v in violations})
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
        labels = {0: "Today", 1: "Week", 2: "Month", 3: "All"}
        if hasattr(self, "_snapshot_range"):
            self._snapshot_range.setText(labels.get(idx, "Custom"))

    def _show_loading_state(self):
        self._clear_grid()
        state = make_empty_state("Loading evidence", "Evidence board is loading.", "info")
        state.setMinimumHeight(260)
        self._grid.addWidget(state, 0, 0)

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_grid(self):
        self._clear_grid()
        self._count_badge.setText(f"{len(self._violations)} items")
        if not self._violations:
            state = make_empty_state("No violations found", "Try another date range or camera filter.")
            state.setMinimumHeight(280)
            self._grid.addWidget(state, 0, 0)
            return

        cols = responsive_columns(self._grid_widget.width(), card_width=278, minimum=1, maximum=5)
        for idx, violation in enumerate(self._violations):
            card = _EvidenceTile(violation)
            card.clicked.connect(self._open_detail)
            self._grid.addWidget(card, idx // cols, idx % cols)

    def _open_detail(self, violation: dict):
        dlg = ViolationDetailDialog(violation, self)
        dlg.exec()

    def _open_latest(self):
        if self._violations:
            self._open_detail(self._violations[0])

    def _update_insights(self):
        while self._insights_layout.count():
            item = self._insights_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        while self._camera_breakdown.count():
            item = self._camera_breakdown.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cameras = Counter(str(v.get("camera_name") or "Unknown") for v in self._violations)
        types = Counter(str(v.get("violation_type") or "no_helmet") for v in self._violations)
        avg_conf = 0.0
        if self._violations:
            avg_conf = sum(float(v.get("confidence", 0) or 0) for v in self._violations) / len(self._violations) * 100
        top_camera = cameras.most_common(1)[0] if cameras else ("-", 0)
        top_type = types.most_common(1)[0] if types else ("no_helmet", 0)
        type_label, _, _ = _type_style(top_type[0])
        for title, value, color in [
            ("Filtered Events", _fmt(len(self._violations)), C("info")),
            ("Main Type", f"{type_label} ({top_type[1]})", C("danger")),
            ("Avg. Confidence", f"{avg_conf:.1f}%", C("warning")),
        ]:
            self._insights_layout.addWidget(self._insight_card(title, value, color))
        max_count = top_camera[1] or 1
        for idx, (name, count) in enumerate(cameras.most_common(5)):
            self._camera_breakdown.addWidget(self._camera_row(name, count, max_count, idx))

    @staticmethod
    def _insight_card(title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: rgba(15,23,42,0.50); border: 1px solid rgba(148,163,184,0.11); border-radius: 8px; }"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(11, 9, 11, 9)
        lay.setSpacing(3)
        value_lbl = QLabel(value)
        value_lbl.setWordWrap(True)
        value_lbl.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 900;")
        lay.addWidget(value_lbl)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 10px; font-weight: 800;")
        lay.addWidget(title_lbl)
        return card

    @staticmethod
    def _camera_row(name: str, count: int, max_count: int, idx: int) -> QFrame:
        row = QFrame()
        row.setStyleSheet("QFrame { background: transparent; border: none; } QLabel { background: transparent; border: none; }")
        lay = QVBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        label = QLabel(name)
        label.setStyleSheet(f"color: {C('text_primary')}; font-size: 11px; font-weight: 900;")
        top.addWidget(label, 1)
        value = QLabel(str(count))
        value.setStyleSheet(f"color: {C('text_secondary')}; font-size: 11px; font-weight: 900;")
        top.addWidget(value)
        lay.addLayout(top)
        track = QFrame()
        track.setFixedHeight(6)
        track.setStyleSheet("background: rgba(30,41,59,0.75); border: none; border-radius: 3px;")
        t = QHBoxLayout(track)
        t.setContentsMargins(0, 0, 0, 0)
        fill = QFrame()
        colors = [C("accent"), C("info"), C("warning"), C("success"), C("danger")]
        fill.setFixedWidth(max(24, int(220 * count / max(max_count, 1))))
        fill.setStyleSheet(f"background: {colors[idx % len(colors)]}; border: none; border-radius: 3px;")
        t.addWidget(fill)
        t.addStretch()
        lay.addWidget(track)
        return row

    def add_new_violation(self, data: dict):
        if self._loading:
            self._pending_reload = True
        else:
            QTimer.singleShot(500, self._load_violations)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._loading:
            QTimer.singleShot(50, self._rebuild_grid)
