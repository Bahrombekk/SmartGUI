from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.design_system import color


def panel_style(object_name: str | None = None) -> str:
    selector = f"QFrame#{object_name}" if object_name else "QFrame"
    return (
        f"{selector} {{"
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        f"stop:0 {color('bg_card')}, stop:1 {color('bg_panel')});"
        "border: 1px solid rgba(148,163,184,0.14);"
        "border-radius: 8px;"
        "}"
    )


def soft_card_style(accent: str | None = None) -> str:
    border = "rgba(148,163,184,0.12)" if accent is None else accent
    return (
        "QFrame {"
        "background: rgba(15,23,42,0.58);"
        f"border: 1px solid {border};"
        "border-radius: 8px;"
        "}"
        "QLabel { background: transparent; border: none; }"
    )


def button_style(kind: str = "secondary") -> str:
    if kind == "primary":
        return (
            "QPushButton {"
            f"background: {color('accent_hover')}; color: #05090d;"
            "border: none; border-radius: 8px; font-weight: 900; padding: 0 14px;"
            "}"
            f"QPushButton:hover {{ background: {color('accent')}; }}"
        )
    if kind == "danger":
        return (
            "QPushButton {"
            "background: rgba(239,68,68,0.10); color: #fecaca;"
            "border: 1px solid rgba(239,68,68,0.30); border-radius: 8px; padding: 0 12px;"
            "}"
            "QPushButton:hover { background: rgba(239,68,68,0.18); }"
        )
    return (
        "QPushButton {"
        "background: rgba(15,23,42,0.72);"
        f"color: {color('text_secondary')};"
        "border: 1px solid rgba(148,163,184,0.18);"
        "border-radius: 8px; padding: 0 12px; font-weight: 800;"
        "}"
        f"QPushButton:hover {{ color: {color('text_primary')}; border-color: rgba(251,146,60,0.55); }}"
    )


def chip_style(fg: str, bg: str = "rgba(148,163,184,0.08)") -> str:
    return (
        f"color: {fg}; background: {bg};"
        "border: 1px solid rgba(148,163,184,0.14);"
        "border-radius: 7px; padding: 2px 7px;"
        "font-size: 10px; font-weight: 900;"
    )


def input_style() -> str:
    return (
        "QLineEdit, QComboBox, QDateEdit {"
        "background: rgba(2,6,23,0.72);"
        f"color: {color('text_primary')};"
        "border: 1px solid rgba(148,163,184,0.22);"
        "border-radius: 8px; padding: 0 10px; min-height: 34px;"
        "}"
        "QLineEdit:focus, QComboBox:focus, QDateEdit:focus {"
        "border-color: rgba(251,146,60,0.72); background: rgba(15,23,42,0.86);"
        "}"
    )


def make_empty_state(title: str, detail: str = "", tone: str = "muted") -> QFrame:
    frame = QFrame()
    border = "rgba(34,211,238,0.16)" if tone == "info" else "rgba(148,163,184,0.12)"
    frame.setStyleSheet(soft_card_style(border))
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 22, 18, 22)
    lay.setSpacing(6)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

    title_lbl = QLabel(title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_lbl.setStyleSheet(f"color: {color('text_primary')}; font-size: 15px; font-weight: 900;")
    lay.addWidget(title_lbl)

    if detail:
        detail_lbl = QLabel(detail)
        detail_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_lbl.setWordWrap(True)
        detail_lbl.setStyleSheet(f"color: {color('text_muted')}; font-size: 12px;")
        lay.addWidget(detail_lbl)
    return frame


def add_summary_metric(parent: QHBoxLayout, title: str, value: str, accent: str) -> QLabel:
    card = QFrame()
    card.setStyleSheet(soft_card_style("rgba(148,163,184,0.12)"))
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 9, 12, 9)
    lay.setSpacing(2)

    value_lbl = QLabel(value)
    value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    value_lbl.setStyleSheet(f"color: {accent}; font-size: 22px; font-weight: 900;")
    lay.addWidget(value_lbl)

    title_lbl = QLabel(title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_lbl.setStyleSheet(f"color: {color('text_muted')}; font-size: 11px; font-weight: 700;")
    lay.addWidget(title_lbl)

    parent.addWidget(card, 1)
    return value_lbl


def responsive_columns(width: int, card_width: int = 240, minimum: int = 1, maximum: int = 5) -> int:
    return max(minimum, min(maximum, max(1, int(width // max(1, card_width)))))
