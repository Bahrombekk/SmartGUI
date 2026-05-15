"""
Dashboard sahifasi uchun styles mixin — endi `app.ui.styles` ga delegate qiladi.

Yangi kod to'g'ridan-to'g'ri `from app.ui.styles import ...` ishlatishi kerak.
"""
from __future__ import annotations

import datetime

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from app.ui.styles import (
    C,
    is_light as _is_light,
    premium_panel_style,
    panel_title_style,
    panel_meta_style,
    link_button_style,
    soft_status_style,
)


class DashboardStylesMixin:
    @staticmethod
    def _premium_panel_style(name: str) -> str:
        return premium_panel_style(name)

    @staticmethod
    def _panel_title_style() -> str:
        return panel_title_style()

    @staticmethod
    def _panel_meta_style() -> str:
        return panel_meta_style()

    @staticmethod
    def _link_button_style() -> str:
        return link_button_style()

    @staticmethod
    def _soft_status_style(color: str, bg: str) -> str:
        return soft_status_style(color, bg)

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
        t.setStyleSheet(panel_title_style())
        hdr.addWidget(t)
        if meta_text:
            meta = QLabel(meta_text)
            meta.setStyleSheet(panel_meta_style())
            hdr.addWidget(meta)
        hdr.addStretch()
        if link:
            view_all = QPushButton("View All")
            view_all.setStyleSheet(link_button_style())
            view_all.clicked.connect(self.go_violations)
            hdr.addWidget(view_all)
        return hdr


# Eski local helper — boshqa fayllar `from app.ui.pages.dashboard.styles import _is_light`
# qilib chaqirgan bo'lishi mumkin
def _is_light_legacy() -> bool:
    return _is_light()


# Re-export
_is_light = _is_light
