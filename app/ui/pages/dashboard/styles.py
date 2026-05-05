from __future__ import annotations

import datetime

from PyQt6.QtWidgets import QLabel, QPushButton, QHBoxLayout


class DashboardStylesMixin:
    @staticmethod
    def _premium_panel_style(name: str) -> str:
        return (
            f"QFrame#{name} {{"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #0c1520, stop:1 #07101a);"
            "border: 1px solid #1e5fa8;"
            "border-radius: 8px;"
            "}"
        )

    @staticmethod
    def _panel_title_style() -> str:
        return (
            "color: #f8fafc; font-size: 13px; font-weight: 700;"
            "background: transparent; border: none;"
        )

    @staticmethod
    def _panel_meta_style() -> str:
        return (
            "color: #93c5fd; font-size: 10px; font-weight: 700;"
            "background: rgba(30,95,168,0.18);"
            "border: 1px solid rgba(30,95,168,0.60);"
            "border-radius: 7px; padding: 2px 8px;"
        )

    @staticmethod
    def _link_button_style() -> str:
        return """
            QPushButton {
                background: rgba(249,115,22,0.08);
                color: #fdba74;
                border: 1px solid rgba(249,115,22,0.20);
                border-radius: 7px;
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
            }
            QPushButton:hover {
                background: rgba(249,115,22,0.16);
                border-color: rgba(249,115,22,0.38);
                color: #ffffff;
            }
        """

    @staticmethod
    def _soft_status_style(color: str, bg: str) -> str:
        return (
            f"color: {color}; background: {bg};"
            f"border: 1px solid {color};"
            "border-radius: 7px; padding: 2px 8px;"
            "font-size: 10px; font-weight: 800;"
        )

    @staticmethod
    def _time_text(v: dict) -> str:
        ts = v.get("timestamp", "")
        if isinstance(ts, (int, float)) and ts:
            return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        if isinstance(ts, str) and len(ts) > 10:
            return ts[11:19]
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _section_header(self, title: str, meta_text: str = "", link: bool = False) -> QHBoxLayout:
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        t = QLabel(title)
        t.setStyleSheet(self._panel_title_style())
        hdr.addWidget(t)
        if meta_text:
            meta = QLabel(meta_text)
            meta.setStyleSheet(self._panel_meta_style())
            hdr.addWidget(meta)
        hdr.addStretch()
        if link:
            view_all = QPushButton("View All")
            view_all.setStyleSheet(self._link_button_style())
            view_all.clicked.connect(self.go_violations)
            hdr.addWidget(view_all)
        return hdr

