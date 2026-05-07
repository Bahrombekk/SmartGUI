from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget


class DashboardBottomPanelsMixin:
    def _build_system_overview(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("systemOverviewPanel")
        frame.setStyleSheet(self._premium_panel_style("systemOverviewPanel"))
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(9)

        hdr = QHBoxLayout()
        ov_title = QLabel("System Overview")
        ov_title.setStyleSheet(self._panel_title_style())
        hdr.addWidget(ov_title, 1)
        meta = QLabel("Live")
        meta.setStyleSheet(self._panel_meta_style())
        hdr.addWidget(meta)
        lay.addLayout(hdr)

        # Total / Online / Offline — 3 ustun
        counts_row = QHBoxLayout()
        counts_row.setSpacing(7)

        for key, label, lbl_color, val_color in [
            ("total",   "Total",   "#94a3b8", "#ffffff"),
            ("online",  "Online",  "#34d399", "#22d3ee"),
            ("offline", "Offline", "#94a3b8", "#94a3b8"),
        ]:
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #0e1d2e;"
                "border: 1px solid #1e5fa8; border-radius: 8px; }"
            )
            col = QVBoxLayout(card)
            col.setContentsMargins(8, 7, 8, 7)
            col.setSpacing(2)

            val = QLabel("—")
            val.setText("0")
            val.setStyleSheet(
                f"color: {val_color}; font-size: 20px; font-weight: 800;"
                " background: transparent; border: none;"
            )
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(val)

            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color: {lbl_color}; font-size: 10px; background: transparent;"
                " border: none;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl)

            counts_row.addWidget(card, 1)
            setattr(self, f"_ov_{key}", val)

        lay.addLayout(counts_row)
        lay.addSpacing(4)

        # StatLine: Detections Today
        lay.addWidget(self._stat_line("Detections Today", "0", "+0%", red=False))

        # StatLine: No Helmet
        lay.addWidget(self._stat_line("No Helmet Detections", "0", "+0%", red=True))

        # Recognition Rate
        rr = QFrame()
        rr.setStyleSheet(
            "QFrame { background: #0e1d2e;"
            "border: 1px solid #1e5fa8; border-radius: 8px; }"
        )
        rr_lay = QVBoxLayout(rr)
        rr_lay.setContentsMargins(10, 8, 10, 8)
        rr_lay.setSpacing(5)

        rl = QLabel("Recognition Rate")
        rl.setStyleSheet("color: #94a3b8; font-size: 11px; background: transparent; border: none;")
        rr_lay.addWidget(rl)

        rv_row = QHBoxLayout()
        rv_row.setSpacing(6)
        rv = QLabel("98.6%")
        rv.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 800; background: transparent; border: none;")
        rv_row.addWidget(rv)
        rd = QLabel("+2.4%")
        rd.setStyleSheet(self._soft_status_style("#34d399", "rgba(52,211,153,0.10)"))
        rv_row.addWidget(rd, 0, Qt.AlignmentFlag.AlignBottom)
        rv_row.addStretch()
        rex = QLabel("Excellent")
        rex.setStyleSheet(self._soft_status_style("#22d3ee", "rgba(34,211,238,0.09)"))
        rv_row.addWidget(rex, 0, Qt.AlignmentFlag.AlignBottom)
        rr_lay.addLayout(rv_row)

        rate_bar = QProgressBar()
        rate_bar.setRange(0, 100)
        rate_bar.setValue(88)
        rate_bar.setFixedHeight(7)
        rate_bar.setTextVisible(False)
        rate_bar.setStyleSheet(
            "QProgressBar { background: rgba(148,163,184,0.16); border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #2dd4bf; border-radius: 3px; }"
        )
        rr_lay.addWidget(rate_bar)
        lay.addWidget(rr)

        return frame

    def _stat_line(self, title: str, value: str, delta: str, red: bool = False) -> QWidget:
        w = QFrame()
        accent = "#ef4444" if red else "#2dd4bf"
        bg = "rgba(239,68,68,0.08)" if red else "rgba(45,212,191,0.07)"
        w.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid #1e5fa8; border-radius: 8px; }}"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        t = QLabel(title)
        t.setStyleSheet("color: #94a3b8; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(t)

        vrow = QHBoxLayout()
        vrow.setSpacing(6)
        v = QLabel(value)
        v.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 800; background: transparent; border: none;")
        if title == "Detections Today":
            self._detections_today_lbl = v
        elif title == "No Helmet Detections":
            self._no_helmet_today_lbl = v
        vrow.addWidget(v)
        d = QLabel(delta)
        d.setStyleSheet(self._soft_status_style(accent, bg))
        vrow.addWidget(d, 0, Qt.AlignmentFlag.AlignBottom)
        vrow.addStretch()
        lay.addLayout(vrow)
        return w


    # ════════════════════════════════════════════════════════════════════════
    #  O'NG ASOSIY KONTENT
    # ════════════════════════════════════════════════════════════════════════

    def _build_bottom_panels(self) -> QWidget:
        bottom = QWidget()
        bottom.setFixedHeight(260)
        bottom.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(bottom)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        panels = [
            self._build_recent_events(),
            self._build_detected_people(),
            self._build_ai_detection(),
            self._build_no_helmet_panel(),
        ]
        for panel in panels:
            lay.addWidget(panel, 1)

        return bottom

    # ── Recent Events ────────────────────────────────────────────────────

    def _build_recent_events(self) -> QWidget:
        w = QFrame()
        w.setObjectName("recentEventsPanel")
        w.setStyleSheet(self._premium_panel_style("recentEventsPanel"))
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        lay.addLayout(self._section_header("Department Stats", "Today"))

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._events_widget = QWidget()
        self._events_widget.setStyleSheet("background: transparent; border: none;")
        self._events_layout = QVBoxLayout(self._events_widget)
        self._events_layout.setContentsMargins(0, 0, 0, 0)
        self._events_layout.setSpacing(6)
        self._events_layout.addStretch()

        scroll.setWidget(self._events_widget)
        lay.addWidget(scroll, 1)
        return w

    # ── Detected People ──────────────────────────────────────────────────

    def _build_detected_people(self) -> QWidget:
        w = QFrame()
        w.setObjectName("detectedPeoplePanel")
        w.setStyleSheet(self._premium_panel_style("detectedPeoplePanel"))
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        lay.addLayout(self._section_header("Detected People", "Tracked", link=True))

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._people_widget = QWidget()
        self._people_widget.setStyleSheet("background: transparent; border: none;")
        self._people_layout = QVBoxLayout(self._people_widget)
        self._people_layout.setContentsMargins(0, 0, 0, 0)
        self._people_layout.setSpacing(6)
        self._people_layout.addStretch()

        scroll.setWidget(self._people_widget)
        lay.addWidget(scroll, 1)
        return w

    # ── AI Detection ─────────────────────────────────────────────────────

    def _build_ai_detection(self) -> QWidget:
        w = QFrame()
        w.setObjectName("aiDetectionPanel")
        w.setStyleSheet(self._premium_panel_style("aiDetectionPanel"))
        w.setMinimumHeight(260)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        lay.addLayout(self._section_header("AI Detection", "Healthy"))

        # Content: person placeholder (left) + text stack (right)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_lay = QHBoxLayout(content)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(12)

        # Left: person silhouette placeholder
        person_box = QFrame()
        person_box.setObjectName("aiPersonBox")
        person_box.setFixedSize(78, 98)
        person_box.setStyleSheet(
            "QFrame#aiPersonBox {"
            "background: rgba(34,211,238,0.08);"
            "border: 1px solid rgba(34,211,238,0.12);"
            "border-radius: 8px;"
            "}"
        )
        pb_lay = QVBoxLayout(person_box)
        pb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        person_icon = QLabel("👤")
        person_icon.setText("AI")
        person_icon.setStyleSheet("font-size: 18px; font-weight: 900; background: transparent; color: #22d3ee; border: none;")
        person_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pb_lay.addWidget(person_icon)
        c_lay.addWidget(person_box)

        # Right: status + description + button
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(8)

        self._ai_active = True
        self._ai_status_lbl = QLabel("Active")
        self._ai_status_lbl.setStyleSheet(
            self._soft_status_style("#22d3ee", "rgba(34,211,238,0.10)")
        )
        r_lay.addWidget(self._ai_status_lbl)

        self._ai_desc_lbl = QLabel("Smart detection is\nrunning smoothly.")
        self._ai_desc_lbl.setStyleSheet(
            "color: #cbd5e1; font-size: 11px; background: transparent; border: none;"
        )
        r_lay.addWidget(self._ai_desc_lbl)

        self._ai_health_lbl = QLabel("0 active cameras | waiting for model")
        self._ai_health_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 10px; background: transparent; border: none;"
        )
        r_lay.addWidget(self._ai_health_lbl)

        self._ai_toggle_btn = QPushButton("Pause AI")
        self._ai_toggle_btn.setFixedHeight(38)
        self._ai_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(249,115,22,0.10);
                color: #ffffff;
                border: 1px solid rgba(249,115,22,0.55);
                border-radius: 8px;
                font-size: 11px;
                font-weight: 800;
                padding: 0 20px;
            }
            QPushButton:hover { background: rgba(249,115,22,0.20); }
        """)
        self._ai_toggle_btn.clicked.connect(self._toggle_ai)
        r_lay.addWidget(self._ai_toggle_btn)
        r_lay.addStretch()

        c_lay.addWidget(right, 1)
        lay.addWidget(content, 1)
        return w

    def _toggle_ai(self):
        self._ai_active = not self._ai_active
        self.ai_pause_requested.emit(not self._ai_active)
        if self._ai_active:
            self._ai_status_lbl.setText("Active")
            self._ai_status_lbl.setStyleSheet(
                self._soft_status_style("#22d3ee", "rgba(34,211,238,0.10)")
            )
            self._ai_desc_lbl.setText("Smart detection is\nrunning smoothly.")
            self._ai_toggle_btn.setText("Pause AI")
            self._update_ai_health()
        else:
            self._ai_status_lbl.setText("Paused")
            self._ai_status_lbl.setStyleSheet(
                self._soft_status_style("#94a3b8", "rgba(148,163,184,0.08)")
            )
            self._ai_desc_lbl.setText("Detection is paused\nfor review.")
            self._ai_toggle_btn.setText("Start AI")
            self._update_ai_health()

    def _update_ai_health(self):
        if not hasattr(self, "_ai_health_lbl"):
            return
        active = int(getattr(self, "_online_count", 0) or 0)
        total = int(getattr(self, "_total_count", 0) or 0)
        persons = int(getattr(self, "_total_persons", 0) or 0)
        models = len(getattr(self, "_model_loaded_cameras", set()))
        state = "paused" if not getattr(self, "_ai_active", True) else "running"
        self._ai_health_lbl.setText(f"{active}/{total} cameras | {models} models | {persons} persons | {state}")

    # ── No Helmet ────────────────────────────────────────────────────────

    def _build_no_helmet_panel(self) -> QWidget:
        w = QFrame()
        w.setObjectName("noHelmetPanel")
        w.setStyleSheet(self._premium_panel_style("noHelmetPanel"))
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        lay.addLayout(self._section_header("No Helmet", "Priority", link=True))

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        self._no_helmet_container = QWidget()
        self._no_helmet_container.setStyleSheet("background: transparent;")
        self._no_helmet_grid = QGridLayout(self._no_helmet_container)
        self._no_helmet_grid.setSpacing(8)
        self._no_helmet_grid.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._no_helmet_container)
        lay.addWidget(scroll, 1)
        return w

    # ════════════════════════════════════════════════════════════════════════
    #  KAMERA PANELLARI BOSHQARUVI
    # ════════════════════════════════════════════════════════════════════════

    def _rebuild_recent_events(self):
        stats = self._department_stats()
        keys = tuple(str(dep.get("key", dep.get("name", ""))) for dep in stats)
        rows = getattr(self, "_department_rows", {})

        if keys != getattr(self, "_department_row_keys", ()) or any(key not in rows for key in keys):
            self._clear_department_stat_rows()
            self._department_rows = {}
            for dep in stats:
                key = str(dep.get("key", dep.get("name", "")))
                row = self._department_stat_row(dep)
                self._department_rows[key] = row
                self._events_layout.addWidget(row)
            self._events_layout.addStretch()
            self._department_row_keys = keys
            return

        for dep in stats:
            key = str(dep.get("key", dep.get("name", "")))
            row = self._department_rows.get(key)
            if row:
                self._update_department_stat_row(row, dep)

    def _clear_department_stat_rows(self):
        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _department_stats(self) -> list[dict]:
        departments = self.cfg.get_departments() if self.cfg else []
        cameras = list(getattr(self, "_all_cameras", []))
        known = {dep.get("id") for dep in departments}
        rows: list[dict] = []

        for dep in departments:
            dep_id = dep.get("id")
            dep_cameras = [cam for cam in cameras if cam.get("department_id") == dep_id]
            if dep_cameras:
                rows.append(self._department_stat(dep.get("name", "Bo'lim"), dep_cameras, f"dep:{dep_id}"))

        ungrouped = [cam for cam in cameras if cam.get("department_id") not in known]
        if ungrouped:
            rows.append(self._department_stat("Bo'limsiz", ungrouped, "ungrouped"))
        if not rows and cameras:
            rows.append(self._department_stat("All Cameras", cameras, "all"))
        return rows

    def _department_stat(self, name: str, cameras: list[dict], key: str) -> dict:
        cam_ids = [cam.get("id") for cam in cameras]
        total = len(cam_ids)
        online = sum(1 for cam_id in cam_ids if self._cam_status.get(cam_id) == "live")
        detections = sum(int(self._today_per_cam.get(cam_id, 0) or 0) for cam_id in cam_ids)
        return {
            "key": key,
            "name": name,
            "total": total,
            "online": online,
            "offline": max(0, total - online),
            "detections": detections,
            "percent": int(online * 100 / total) if total else 0,
        }

    @staticmethod
    def _compact_count(value: int) -> str:
        value = int(value or 0)
        if value >= 1000000:
            compact = value / 1000000
            return f"{compact:.1f}M".replace(".0M", "M")
        if value >= 10000:
            compact = value / 1000
            return f"{compact:.1f}k".replace(".0k", "k")
        return str(value)

    @staticmethod
    def _department_health(percent: int, online: int) -> tuple[str, str, str]:
        if online <= 0:
            return "Offline", "#f87171", "rgba(248,113,113,0.10)"
        if percent >= 70:
            return "Healthy", "#2dd4bf", "rgba(45,212,191,0.10)"
        return "Partial", "#fbbf24", "rgba(251,191,36,0.10)"

    @staticmethod
    def _department_chip(text: str, color: str, bg: str) -> QLabel:
        chip = QLabel(text)
        chip.setStyleSheet(
            f"color: {color}; background: {bg};"
            "border: 1px solid rgba(148,163,184,0.12);"
            "border-radius: 7px; padding: 2px 6px;"
            "font-size: 9px; font-weight: 800;"
        )
        return chip

    @staticmethod
    def _department_status_style(color: str, bg: str) -> str:
        return (
            f"color: {color}; background: {bg};"
            "border: 1px solid rgba(148,163,184,0.12);"
            "border-radius: 7px; padding: 2px 6px;"
            "font-size: 9px; font-weight: 900;"
        )

    @staticmethod
    def _department_bar_style(color: str) -> str:
        return (
            "QProgressBar { background: rgba(148,163,184,0.14); border: none; border-radius: 3px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )

    def _department_stat_row(self, dep: dict) -> QWidget:
        percent = int(dep.get("percent", 0) or 0)
        online = int(dep.get("online", 0) or 0)
        total = int(dep.get("total", 0) or 0)
        offline = int(dep.get("offline", 0) or 0)
        detections = int(dep.get("detections", 0) or 0)
        status, accent, status_bg = self._department_health(percent, online)

        row = QFrame()
        row.setFixedHeight(62)
        row.setStyleSheet(
            "QFrame {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0e1d2e, stop:1 #0a1520);"
            "border: 1px solid #1e5fa8;"
            "border-radius: 8px;"
            "}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(9, 8, 9, 8)
        lay.setSpacing(9)

        accent_bar = QFrame()
        accent_bar.setFixedSize(4, 38)
        accent_bar.setStyleSheet(f"background: {accent}; border: none; border-radius: 2px;")
        lay.addWidget(accent_bar, 0, Qt.AlignmentFlag.AlignVCenter)

        left = QVBoxLayout()
        left.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel(str(dep.get("name", "Bo'lim")))
        title.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 800; background: transparent; border: none;")
        title_row.addWidget(title, 1)

        status_chip = QLabel(status)
        status_chip.setStyleSheet(self._department_status_style(accent, status_bg))
        title_row.addWidget(status_chip)
        left.addLayout(title_row)

        chips = QHBoxLayout()
        chips.setSpacing(5)
        total_chip = self._department_chip(f"{total} cam", "#cbd5e1", "rgba(148,163,184,0.08)")
        online_chip = self._department_chip(f"{online} live", "#5eead4", "rgba(45,212,191,0.08)")
        offline_chip = self._department_chip(f"{offline} offline", "#cbd5e1", "rgba(148,163,184,0.06)")
        chips.addWidget(total_chip)
        chips.addWidget(online_chip)
        chips.addWidget(offline_chip)
        chips.addStretch()
        left.addLayout(chips)
        lay.addLayout(left, 1)

        health = QVBoxLayout()
        health.setSpacing(4)
        pct = QLabel(f"{percent}% online")
        pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        pct.setStyleSheet("color: #94a3b8; font-size: 9px; font-weight: 800; background: transparent; border: none;")
        health.addWidget(pct)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(percent)
        bar.setFixedSize(88, 7)
        bar.setTextVisible(False)
        bar.setStyleSheet(self._department_bar_style(accent))
        health.addWidget(bar)
        lay.addLayout(health)

        det_box = QFrame()
        det_box.setFixedSize(74, 46)
        det_box.setStyleSheet(
            "QFrame {"
            "background: rgba(249,115,22,0.08);"
            "border: 1px solid rgba(249,115,22,0.16);"
            "border-radius: 8px;"
            "}"
        )
        det_lay = QVBoxLayout(det_box)
        det_lay.setContentsMargins(7, 5, 7, 5)
        det_lay.setSpacing(1)

        det_label = QLabel("Today")
        det_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        det_label.setStyleSheet("color: #fed7aa; font-size: 9px; font-weight: 800; background: transparent; border: none;")
        det_lay.addWidget(det_label)

        det = QLabel(self._compact_count(detections))
        det.setAlignment(Qt.AlignmentFlag.AlignCenter)
        det.setToolTip(f"Bugungi detections: {detections}")
        det.setStyleSheet("color: #fdba74; font-size: 18px; font-weight: 900; background: transparent; border: none;")
        det_lay.addWidget(det)
        lay.addWidget(det_box)
        row._dept_widgets = {
            "accent_bar": accent_bar,
            "title": title,
            "status_chip": status_chip,
            "total_chip": total_chip,
            "online_chip": online_chip,
            "offline_chip": offline_chip,
            "pct": pct,
            "bar": bar,
            "det": det,
        }
        return row

    def _update_department_stat_row(self, row: QWidget, dep: dict):
        widgets = getattr(row, "_dept_widgets", {})
        if not widgets:
            return

        percent = int(dep.get("percent", 0) or 0)
        online = int(dep.get("online", 0) or 0)
        total = int(dep.get("total", 0) or 0)
        offline = int(dep.get("offline", 0) or 0)
        detections = int(dep.get("detections", 0) or 0)
        status, accent, status_bg = self._department_health(percent, online)

        widgets["accent_bar"].setStyleSheet(f"background: {accent}; border: none; border-radius: 2px;")
        widgets["title"].setText(str(dep.get("name", "Bo'lim")))
        widgets["status_chip"].setText(status)
        widgets["status_chip"].setStyleSheet(self._department_status_style(accent, status_bg))
        widgets["total_chip"].setText(f"{total} cam")
        widgets["online_chip"].setText(f"{online} live")
        widgets["offline_chip"].setText(f"{offline} offline")
        widgets["pct"].setText(f"{percent}% online")
        widgets["bar"].setValue(percent)
        widgets["bar"].setStyleSheet(self._department_bar_style(accent))
        widgets["det"].setText(self._compact_count(detections))
        widgets["det"].setToolTip(f"Bugungi detections: {detections}")

    def _event_row(self, v: dict) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "background: #0e1d2e;"
            "border: 1px solid #1e5fa8;"
            "border-radius: 8px;"
        )
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        w.setFixedHeight(48)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(9, 0, 9, 0)
        lay.setSpacing(10)

        has_helmet = v.get("has_helmet", False)
        icon = QLabel("✓" if has_helmet else "⚠")
        icon.setText("OK" if has_helmet else "!")
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if has_helmet:
            icon.setStyleSheet(
                "color: #34d399; font-size: 10px; font-weight: 900;"
                " background: rgba(52,211,153,0.10); border: 1px solid rgba(52,211,153,0.18);"
                " border-radius: 8px;"
            )
        else:
            icon.setStyleSheet(
                "color: #fca5a5; font-size: 13px; font-weight: 900;"
                " background: rgba(239,68,68,0.10); border: 1px solid rgba(239,68,68,0.18);"
                " border-radius: 8px;"
            )
        lay.addWidget(icon)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        title = "Helmet Detected" if has_helmet else "No Helmet Detected"
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(
            "color: #f8fafc; font-size: 12px; font-weight: 700; background: transparent;"
        )
        info_col.addWidget(t_lbl)

        cam_name = v.get("camera_name", v.get("camera_id", ""))
        c_lbl = QLabel(f"Camera {cam_name}")
        c_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 10px; background: transparent;"
        )
        info_col.addWidget(c_lbl)
        lay.addLayout(info_col, 1)

        time_str = self._time_text(v)
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            "color: #cbd5e1; font-size: 10px; background: rgba(148,163,184,0.08);"
            "border: 1px solid rgba(148,163,184,0.10); border-radius: 7px; padding: 2px 6px;"
        )
        lay.addWidget(time_lbl)
        return w

    def _rebuild_detected_people(self):
        while self._people_layout.count():
            item = self._people_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for v in self._recent_violations[:4]:
            row = self._person_row(v)
            self._people_layout.addWidget(row)

        self._people_layout.addStretch()

    def _rebuild_no_helmet(self):
        if not hasattr(self, '_no_helmet_grid'):
            return
        while self._no_helmet_grid.count():
            item = self._no_helmet_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        violations = [v for v in self._recent_violations if not v.get("has_helmet", False)]
        for idx, v in enumerate(violations[:4]):
            card = self._no_helmet_card(v)
            self._no_helmet_grid.addWidget(card, idx // 2, idx % 2)

    def _no_helmet_card(self, v: dict) -> QWidget:
        card = QFrame()
        card.setFixedHeight(86)
        card.setStyleSheet(
            "QFrame { background: rgba(239,68,68,0.07); border: 1px solid rgba(239,68,68,0.18);"
            " border-radius: 8px; }"
        )
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(card)
        lay.setContentsMargins(8, 7, 8, 7)
        lay.setSpacing(9)

        crop = QLabel()
        crop.setFixedSize(58, 58)
        crop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crop.setStyleSheet(
            "background: #0a1520;"
            "border: 1px solid #1e5fa8;"
            "border-radius: 8px;"
            "color: #60a5fa; font-size: 9px; font-weight: 800;"
        )
        pix = v.get("_crop_pixmap")
        if pix is None:
            crop_path = str(v.get("crop_path", "") or "")
            if crop_path and os.path.exists(crop_path):
                pix = QPixmap(crop_path) or None
                if pix and pix.isNull():
                    pix = None
        if pix is not None:
            crop.setPixmap(
                pix.scaled(
                    crop.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            crop.setText("NO\nIMG")
        lay.addWidget(crop)

        info = QVBoxLayout()
        info.setSpacing(5)

        # Top row: NO HELMET badge + time
        top = QHBoxLayout()
        top.setSpacing(5)
        badge = QLabel("NO HELMET")
        badge.setStyleSheet(
            "background: rgba(239,68,68,0.18); color: #fecaca; font-size: 9px; font-weight: 900;"
            " border: 1px solid rgba(239,68,68,0.26); border-radius: 6px; padding: 2px 6px;"
        )
        top.addWidget(badge)
        top.addStretch()

        time_str = self._time_text(v)
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(
            "background: rgba(15,23,42,0.64); color: #cbd5e1; font-size: 9px;"
            " border: 1px solid rgba(148,163,184,0.10); border-radius: 6px; padding: 2px 5px;"
        )
        top.addWidget(time_lbl)
        info.addLayout(top)

        info.addStretch()

        # Bottom: ID + camera
        person_id = v.get("track_id", v.get("person_id", "—"))
        id_str = f"ID: {person_id:04d}" if isinstance(person_id, int) else f"ID: {person_id}"
        id_lbl = QLabel(id_str)
        id_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        info.addWidget(id_lbl)

        cam = v.get("camera_name", v.get("camera_id", ""))
        cam_lbl = QLabel(str(cam) if cam else "Unknown camera")
        cam_lbl.setStyleSheet("color: #cbd5e1; font-size: 10px; background: transparent; border: none;")
        info.addWidget(cam_lbl)
        lay.addLayout(info, 1)

        return card

    def _person_row(self, v: dict) -> QWidget:
        has_helmet = v.get("has_helmet", False)
        w = QWidget()
        w.setFixedHeight(58)
        w.setStyleSheet(
            "background: #0e1d2e;"
            "border: 1px solid #1e5fa8;"
            "border-radius: 8px;"
        )
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)

        # Avatar
        avatar = QLabel("ID")
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            "background: rgba(249,115,22,0.14); border-radius: 8px; font-size: 10px;"
            "font-weight: 900; color: #fb923c; border: 1px solid rgba(249,115,22,0.50);"
        )
        pix = v.get("_crop_pixmap")
        if pix is None:
            crop_path = str(v.get("crop_path", "") or "")
            if crop_path and os.path.exists(crop_path):
                pix = QPixmap(crop_path)
                if pix and pix.isNull():
                    pix = None
        if pix is not None:
            avatar.setPixmap(
                pix.scaled(
                    avatar.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        lay.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(3)

        person_id = v.get("track_id", v.get("person_id", "—"))
        id_str = f"ID: {person_id:04d}" if isinstance(person_id, int) else f"ID: {person_id}"
        id_lbl = QLabel(id_str)
        id_lbl.setStyleSheet(
            "color: #fb923c; font-size: 12px; font-weight: 800; background: transparent;"
        )
        info.addWidget(id_lbl)

        cam_name = v.get("camera_name", v.get("camera_id", ""))
        name_lbl = QLabel(str(cam_name) if cam_name else "Unknown")
        name_lbl.setStyleSheet(
            "color: #93c5fd; font-size: 11px; font-weight: 600; background: transparent;"
        )
        info.addWidget(name_lbl)
        lay.addLayout(info, 1)

        if has_helmet:
            status_lbl = QLabel("✓ Helmet")
            status_lbl.setStyleSheet(
                "color: #34d399; background: rgba(52,211,153,0.12);"
                "border: 1px solid rgba(52,211,153,0.55);"
                "border-radius: 7px; padding: 4px 10px;"
                "font-size: 10px; font-weight: 800;"
            )
        else:
            status_lbl = QLabel("! No Helmet")
            status_lbl.setStyleSheet(
                "color: #f87171; background: rgba(239,68,68,0.15);"
                "border: 1px solid rgba(239,68,68,0.60);"
                "border-radius: 7px; padding: 4px 10px;"
                "font-size: 10px; font-weight: 800;"
            )
        lay.addWidget(status_lbl)
        return w
