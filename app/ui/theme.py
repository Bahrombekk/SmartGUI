"""
LEGACY shim — barcha ranglar va QSS endi `app.ui.styles` ichida.

Bu fayl eski kod uchun yo'naltirish vositasi sifatida qoldirildi.
Yangi kod `from app.ui.styles import ...` orqali to'g'ridan-to'g'ri
ishlatishi kerak.
"""
from __future__ import annotations

from app.ui.styles import (
    C,
    set_theme,
    is_light,
    current_theme,
    build_main_stylesheet,
)
# design_system.COLORS shu paket bilan sinxron qoladi
from app.ui.design_system import COLORS  # noqa: F401


def get_main_stylesheet() -> str:
    """Joriy mavzu uchun to'liq QSS uslubni qaytaradi (legacy nom)."""
    return build_main_stylesheet()


__all__ = [
    "C",
    "set_theme",
    "is_light",
    "current_theme",
    "get_main_stylesheet",
    "build_main_stylesheet",
]
