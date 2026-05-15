"""
LEGACY shim — uslublar endi `app.ui.styles` ichida.

Bu fayl eski importlar uchun yo'naltirish vositasi. Yangi kod
to'g'ridan-to'g'ri `from app.ui.styles import ...` ishlatishi kerak.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.ui.styles import (
    C,
    panel_style,
    soft_card_style,
    button_style,
    chip_style,
    input_style,
)
# `color` legacy import — design_system'dan
from app.ui.design_system import color


def make_empty_state(title: str, detail: str = "", tone: str = "muted") -> QFrame:
    """Bo'sh holatda chiqariladigan oddiy joker karta."""
    frame = QFrame()
    border = C('info') if tone == "info" else C('border_light')
    frame.setStyleSheet(soft_card_style(border))
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 22, 18, 22)
    lay.setSpacing(6)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

    title_lbl = QLabel(title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_lbl.setStyleSheet(f"color: {C('text_primary')}; font-size: 15px; font-weight: 900;")
    lay.addWidget(title_lbl)

    if detail:
        detail_lbl = QLabel(detail)
        detail_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_lbl.setWordWrap(True)
        detail_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        lay.addWidget(detail_lbl)
    return frame


def add_summary_metric(parent: QHBoxLayout, title: str, value: str, accent: str) -> QLabel:
    """Yon-yon joylashgan metric kartalari."""
    card = QFrame()
    card.setStyleSheet(soft_card_style(C('border_light')))
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 9, 12, 9)
    lay.setSpacing(2)

    value_lbl = QLabel(value)
    value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    value_lbl.setStyleSheet(f"color: {accent}; font-size: 22px; font-weight: 900;")
    lay.addWidget(value_lbl)

    title_lbl = QLabel(title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px; font-weight: 700;")
    lay.addWidget(title_lbl)

    parent.addWidget(card, 1)
    return value_lbl


def responsive_columns(width: int, card_width: int = 240, minimum: int = 1, maximum: int = 5) -> int:
    return max(minimum, min(maximum, max(1, int(width // max(1, card_width)))))


__all__ = [
    "panel_style",
    "soft_card_style",
    "button_style",
    "chip_style",
    "input_style",
    "make_empty_state",
    "add_summary_metric",
    "responsive_columns",
    "color",
]
