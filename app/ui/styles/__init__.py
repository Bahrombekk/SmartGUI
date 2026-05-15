"""
SmartGUI uslublar markazi.

Barcha ranglar va UI uslublari shu paketda boshqariladi:
    - tokens.py   — DARK va LIGHT palettelar, set_theme/C/is_light
    - loader.py   — qss/ papkasidagi QSS fayllarni token bilan to'ldirib o'qish
    - components.py — Python funksiyalari orqali dinamik uslublar
    - qss/        — global QSS fayllar (base, inputs, buttons, lists, misc)

Foydalanish:

    from app.ui.styles import C, set_theme, build_main_stylesheet
    from app.ui.styles import button_style, input_style, panel_style

    set_theme("light")
    app.setStyleSheet(build_main_stylesheet())

    btn.setStyleSheet(button_style("primary"))
"""
from __future__ import annotations

from app.ui.styles.tokens import (
    DARK,
    LIGHT,
    C,
    set_theme,
    is_light,
    current_theme,
    active_palette,
    on_theme_change,
)
from app.ui.styles.loader import build_main_stylesheet, load_qss
from app.ui.styles.components import (
    panel_style,
    soft_card_style,
    premium_panel_style,
    header_gradient_style,
    button_style,
    link_button_style,
    chip_style,
    soft_status_style,
    panel_title_style,
    panel_meta_style,
    input_style,
    campanel_outer_style,
    campanel_id_pill_style,
    campanel_name_style,
    campanel_fps_style,
    time_text_chip_style,
)


__all__ = [
    # tokens
    "DARK", "LIGHT", "C", "set_theme", "is_light", "current_theme", "active_palette",
    "on_theme_change",
    # loader
    "build_main_stylesheet", "load_qss",
    # components
    "panel_style", "soft_card_style", "premium_panel_style", "header_gradient_style",
    "button_style", "link_button_style", "chip_style", "soft_status_style",
    "panel_title_style", "panel_meta_style", "input_style",
    "campanel_outer_style", "campanel_id_pill_style", "campanel_name_style",
    "campanel_fps_style", "time_text_chip_style",
]
