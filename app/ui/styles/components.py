"""
Komponent-darajadagi style helper'lar.

QSS fayllarda yozib bo'lmaydigan dinamik styling (masalan, status bo'yicha
ranglar) shu yerda joylashadi. Hammasi `C()` orqali joriy mavzudan
foydalanadi — hech qanday rang hardcode qilinmagan.
"""
from __future__ import annotations

from app.ui.styles.tokens import C, is_light


# ── Panel / card uslublari ────────────────────────────────────────────────────

def panel_style(object_name: str | None = None) -> str:
    """Asosiy panel fon + chegara."""
    selector = f"QFrame#{object_name}" if object_name else "QFrame"
    return (
        f"{selector} {{"
        f"background: {C('bg_card')};"
        f"border: 1px solid {C('border')};"
        "border-radius: 8px;"
        "}"
    )


def soft_card_style(accent: str | None = None) -> str:
    """Yumshoq fonli kartochka — tarkib joylashtirish uchun."""
    border = accent if accent is not None else C('border_light')
    return (
        "QFrame {"
        f"background: {C('bg_card')};"
        f"border: 1px solid {border};"
        "border-radius: 8px;"
        "}"
        "QLabel { background: transparent; border: none; }"
    )


def premium_panel_style(object_name: str) -> str:
    """Dashboard'dagi yirik bo'limlar uchun gradient yoki yassi fon."""
    if is_light():
        return (
            f"QFrame#{object_name} {{"
            f"background: {C('bg_card')};"
            f"border: 1px solid {C('border')};"
            "border-radius: 8px;"
            "}"
        )
    return (
        f"QFrame#{object_name} {{"
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        f"stop:0 {C('bg_panel_gradient_a')}, stop:1 {C('bg_panel_gradient_b')});"
        f"border: 1px solid {C('border_panel')};"
        "border-radius: 8px;"
        "}"
    )


def header_gradient_style(radius: str = "9px 9px 0 0") -> str:
    """Camera panel header/footer uchun — light mode'da yassi, dark'da gradient."""
    if is_light():
        return f"background: {C('bg_hover')}; border-radius: {radius};"
    return (
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"stop:0 {C('bg_header_a')}, stop:1 {C('bg_header_b')});"
        f"border-radius: {radius};"
    )


# ── Tugma uslublari ───────────────────────────────────────────────────────────

def button_style(kind: str = "secondary") -> str:
    """kind: 'primary' | 'secondary' | 'danger' | 'success'."""
    if kind == "primary":
        return (
            "QPushButton {"
            f"background: {C('accent')}; color: {C('text_on_accent')};"
            "border: none; border-radius: 8px; font-weight: 900; padding: 0 14px;"
            "}"
            f"QPushButton:hover {{ background: {C('accent_hover')}; }}"
        )
    if kind == "danger":
        return (
            "QPushButton {"
            f"background: {C('danger_dim')}; color: {C('danger')};"
            f"border: 1px solid {C('danger')};"
            "border-radius: 8px; padding: 0 12px;"
            "}"
            f"QPushButton:hover {{ background: {C('danger_hover_bg')}; }}"
        )
    if kind == "success":
        return (
            "QPushButton {"
            f"background: {C('success_dim')}; color: {C('success')};"
            f"border: 1px solid {C('success')};"
            "border-radius: 8px; padding: 0 12px; font-weight: 800;"
            "}"
            f"QPushButton:hover {{ background: {C('success')}; color: {C('bg_card')}; }}"
        )
    # secondary
    if is_light():
        return (
            "QPushButton {"
            f"background: {C('bg_card')}; color: {C('text_secondary')};"
            f"border: 1px solid {C('border')};"
            "border-radius: 8px; padding: 0 12px; font-weight: 800;"
            "}"
            f"QPushButton:hover {{ background: {C('bg_hover')}; color: {C('text_primary')}; border-color: {C('accent')}; }}"
        )
    return (
        "QPushButton {"
        f"background: {C('input_bg')}; color: {C('text_secondary')};"
        f"border: 1px solid {C('input_border')};"
        "border-radius: 8px; padding: 0 12px; font-weight: 800;"
        "}"
        f"QPushButton:hover {{ color: {C('text_primary')}; border-color: {C('accent')}; }}"
    )


def link_button_style() -> str:
    """'View All' ko'rinishidagi yengil tugma."""
    return (
        "QPushButton {"
        f"background: {C('accent_dim_2')}; color: {C('accent_hover')};"
        f"border: 1px solid {C('accent_dim_3')};"
        "border-radius: 7px; font-size: 10px; font-weight: 700;"
        "padding: 3px 8px;"
        "}"
        "QPushButton:hover {"
        f"background: {C('accent_dim')};"
        f"color: {C('accent')};"
        "}"
    )


# ── Chip / badge uslublari ────────────────────────────────────────────────────

def chip_style(fg: str, bg: str | None = None) -> str:
    if bg is None:
        bg = C('success_dim_2') if is_light() else C('bg_panel')
    return (
        f"color: {fg}; background: {bg};"
        f"border: 1px solid {C('border_light')};"
        "border-radius: 7px; padding: 2px 7px;"
        "font-size: 10px; font-weight: 900;"
    )


def soft_status_style(fg: str, bg: str) -> str:
    return (
        f"color: {fg}; background: {bg};"
        f"border: 1px solid {fg};"
        "border-radius: 7px; padding: 2px 8px;"
        "font-size: 10px; font-weight: 800;"
    )


def panel_title_style() -> str:
    return (
        f"color: {C('text_primary')}; font-size: 13px; font-weight: 700;"
        "background: transparent; border: none;"
    )


def panel_meta_style() -> str:
    """'Live' ko'rinishidagi panel meta-yorlig'i."""
    if is_light():
        return (
            f"color: {C('success')}; font-size: 10px; font-weight: 700;"
            f"background: {C('success_dim')};"
            f"border: 1px solid {C('success')};"
            "border-radius: 7px; padding: 2px 8px;"
        )
    return (
        f"color: {C('text_link')}; font-size: 10px; font-weight: 700;"
        f"background: {C('info_dim')};"
        f"border: 1px solid {C('border_panel')};"
        "border-radius: 7px; padding: 2px 8px;"
    )


# ── Input uslublari ───────────────────────────────────────────────────────────

def input_style() -> str:
    """QLineEdit/QComboBox/QDateEdit uchun tematik uslub."""
    return (
        "QLineEdit, QComboBox, QDateEdit {"
        f"background: {C('input_bg')};"
        f"color: {C('text_primary')};"
        f"border: 1px solid {C('input_border')};"
        "border-radius: 8px; padding: 0 10px; min-height: 34px;"
        "}"
        "QLineEdit:hover, QComboBox:hover, QDateEdit:hover {"
        f"border-color: {C('input_border_hov')};"
        "}"
        "QLineEdit:focus, QComboBox:focus, QDateEdit:focus {"
        f"border-color: {C('input_border_foc')};"
        f"background: {C('input_bg_focus')};"
        "}"
    )


# ── Camera panel maxsus uslublari ─────────────────────────────────────────────

def campanel_outer_style(selected: bool) -> str:
    """CameraPanel chegara/fon uslubi."""
    if selected:
        border = C('accent')
        bg = C('accent_dim_2') if not is_light() else C('campanel_bg_selected')
    else:
        border = C('campanel_border')
        bg = C('campanel_bg')
    return (
        "QFrame[cam_panel='true'] {"
        f"background: {bg};"
        f"border: 2px solid {border};"
        "border-radius: 10px;"
        "}"
    )


def campanel_id_pill_style() -> str:
    return (
        f"background: {C('campanel_pill_bg')};"
        f"color: {C('campanel_pill_text')};"
        f"border: 1px solid {C('campanel_pill_border')};"
        "border-radius: 5px;"
        "font-size: 10px; font-weight: 800;"
    )


def campanel_name_style() -> str:
    return (
        f"color: {C('campanel_name_text')}; font-size: 12px; font-weight: 700;"
        " background: transparent;"
    )


def campanel_fps_style() -> str:
    return (
        f"color: {C('campanel_fps_text')}; font-size: 10px; font-weight: 700;"
        " background: transparent;"
    )


# ── Misc ──────────────────────────────────────────────────────────────────────

def time_text_chip_style() -> str:
    return (
        f"color: {C('text_secondary')}; font-size: 10px;"
        f"background: {C('bg_hover')};"
        f"border: 1px solid {C('border_light')};"
        "border-radius: 7px; padding: 2px 6px;"
    )
