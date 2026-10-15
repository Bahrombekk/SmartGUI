"""
Markazlashtirilgan rang tokenlari — barcha UI ranglari shu yerda.

`set_theme("light")` yoki `set_theme("dark")` orqali butun ilova
ranglari almashtiriladi. Hech qaysi UI faylga rang hardcode qilinmasligi
kerak — har doim `C(token_name)` orqali murojaat qilinadi.
"""
from __future__ import annotations

from app.ui import fz   # yagona rang manbai — DARK qiymatlari Figma konstantalaridan


# ── DARK PALETTE ──────────────────────────────────────────────────────────────
DARK: dict[str, str] = {
    # Asosiy fonlar — Figma aniq qiymatlari (6 ekran rang qo'llanmasi)
    "bg_main":         fz.BG,
    "bg_card":         fz.CARD,
    "bg_input":        fz.INPUT,
    "bg_hover":        fz.ACTIVE,
    "bg_sidebar":      fz.BG,
    "bg_panel":        fz.CARD,
    "bg_panel_alt":    fz.RAISED,
    "bg_panel_gradient_a": "#0d1d33",
    "bg_panel_gradient_b": "#071122",
    "bg_header_a":     "#0d1d33",
    "bg_header_b":     "#091528",

    # Aksent — MOVIY cyan (asosiy tugma, havola, tanlash)
    "accent":          fz.ACCENT,
    "accent_hover":    fz.ACCENT_HOVER,
    "accent_dim":      fz.CHIP_ACTIVE_BG,
    "accent_dim_2":    "rgba(31,182,255,0.12)",
    "accent_dim_3":    "rgba(31,182,255,0.22)",
    "accent_light":    "#7fe0f7",
    "accent_subtle":   "#08202e",

    # Matn
    "text_primary":    fz.TEXT,
    "text_secondary":  "#b4c0d3",
    "text_muted":      fz.MUTED,
    "text_dim":        fz.DIM,
    "text_link":       fz.ACCENT,
    "text_on_accent":  fz.ON_ACCENT,

    # Holat
    "danger":          fz.RED,
    "danger_dim":      fz.RED_BG,
    "danger_dim_2":    "rgba(255,73,100,0.12)",
    "success":         fz.GREEN,
    "success_dim":     fz.GREEN_BG,
    "success_dim_2":   "rgba(25,215,151,0.12)",
    "warning":         "#f3b348",
    "warning_dim":     "#2e2410",
    "warning_dim_2":   "rgba(243,179,72,0.12)",
    "info":            fz.ACCENT,
    "info_dim":        fz.BLUE_BG,

    # Chegaralar
    "border":          fz.BORDER,
    "border_light":    fz.ACTIVE,
    "border_strong":   fz.ACCENT,
    "border_accent":   fz.ACCENT,
    "border_hover":    fz.GHOST_BORDER,
    "border_panel":    fz.BORDER,
    "border_soft":     "#11223a",

    # Boshqa
    "shadow":          "#00000066",
    "overlay":         "#030815cc",
    "scrollbar":       "#172a46",
    "scrollbar_hover": "#2a3f61",

    # Kamera
    "cam_active":      "#19d797",
    "cam_idle":        "#60738e",
    "cam_error":       "#ff4964",
    "cam_rec":         "#ff4964",

    # Camera panel maxsus
    "campanel_bg":             "#091528",
    "campanel_bg_selected":    "rgba(31,182,255,0.10)",
    "campanel_border":         "#172a46",
    "campanel_pill_bg":        "rgba(31,182,255,0.18)",
    "campanel_pill_text":      "#7fe0f7",
    "campanel_pill_border":    "rgba(31,182,255,0.35)",
    "campanel_name_text":      "#e7eef8",
    "campanel_fps_text":       "#19c8f3",
    "campanel_video_bg":       "#050d1b",

    # Input maxsus
    "input_bg":         fz.INPUT,
    "input_bg_hover":   "#0d1d33",
    "input_bg_focus":   "#0d1d33",
    "input_border":     fz.BORDER,
    "input_border_hov": "#2a3f61",
    "input_border_foc": fz.ACCENT,
    "selection_bg":     "rgba(31,182,255,0.24)",
    "combo_view_bg":    fz.CARD,
    "combo_view_border": fz.BORDER,
    "danger_hover_bg":  "#4a1b28",
}


# ── LIGHT PALETTE — tiyomniy o'tkir yashil + sabzi (orange) ───────────────────
LIGHT: dict[str, str] = {
    # Asosiy fonlar — to'q, keskin yashil qatlamlar
    "bg_main":         "#03190f",
    "bg_card":         "#082718",
    "bg_input":        "#062113",
    "bg_hover":        "#0b3f25",
    "bg_sidebar":      "#04170e",
    "bg_panel":        "#062113",
    "bg_panel_alt":    "#092d1b",
    "bg_panel_gradient_a": "#082718",
    "bg_panel_gradient_b": "#03190f",
    "bg_header_a":     "#082718",
    "bg_header_b":     "#04170e",

    # Aksent — sabzi: action, tanlangan holat, muhim urg'u
    "accent":          "#ff7a1a",
    "accent_hover":    "#f0640c",
    "accent_dim":      "#4b2208",
    "accent_dim_2":    "rgba(255,122,26,0.16)",
    "accent_dim_3":    "rgba(255,122,26,0.28)",
    "accent_light":    "#ff9a45",
    "accent_subtle":   "#211307",

    # Matn — dark-green fonlarda aniq o'qiladigan och mint
    "text_primary":    "#ecfff2",
    "text_secondary":  "#b7e6c7",
    "text_muted":      "#7fb391",
    "text_dim":        "#4f7d5f",
    "text_link":       "#43e071",
    "text_on_accent":  "#06140b",

    # Holat — yashil ustun, orange ogohlantirish
    "danger":          "#ff4d4d",
    "danger_dim":      "#351111",
    "danger_dim_2":    "rgba(255,77,77,0.12)",
    "success":         "#22e06d",
    "success_dim":     "#0b4a2b",
    "success_dim_2":   "rgba(34,224,109,0.12)",
    "warning":         "#ff9a2e",
    "warning_dim":     "#3a2408",
    "warning_dim_2":   "rgba(255,154,46,0.13)",
    "info":            "#43e071",
    "info_dim":        "#0b3a24",

    # Chegaralar — o'tkir yashil chiziqlar
    "border":          "#116b3a",
    "border_light":    "#0b4428",
    "border_strong":   "#23c45b",
    "border_accent":   "#ff7a1a",
    "border_hover":    "#1f9b4e",
    "border_panel":    "#168047",
    "border_soft":     "#0a3521",

    "shadow":          "#00000066",
    "overlay":         "#02100999",
    "scrollbar":       "#0b4428",
    "scrollbar_hover": "#1f9b4e",

    "cam_active":      "#22e06d",
    "cam_idle":        "#4f7d5f",
    "cam_error":       "#ff4d4d",
    "cam_rec":         "#ff4d4d",

    # Camera panel light variant
    "campanel_bg":             "#082718",
    "campanel_bg_selected":    "#211307",
    "campanel_border":         "#168047",
    "campanel_pill_bg":        "#0b3a24",
    "campanel_pill_text":      "#43e071",
    "campanel_pill_border":    "#23c45b",
    "campanel_name_text":      "#ecfff2",
    "campanel_fps_text":       "#43e071",
    "campanel_video_bg":       "#03190f",

    # Input maxsus — light
    "input_bg":         "#041b10",
    "input_bg_hover":   "#062816",
    "input_bg_focus":   "#082f1b",
    "input_border":     "rgba(35,196,91,0.28)",
    "input_border_hov": "rgba(35,196,91,0.52)",
    "input_border_foc": "rgba(255,122,26,0.82)",
    "selection_bg":     "rgba(255,122,26,0.26)",
    "combo_view_bg":    "#062113",
    "combo_view_border": "rgba(35,196,91,0.26)",
    "danger_hover_bg":  "#4a1717",
}


# Joriy faol palette — boshlang'ich qiymat DARK
_ACTIVE: dict[str, str] = dict(DARK)
_THEME_NAME: str = "dark"

# Mavzu o'zgarganda chaqiriluvchi callback'lar (sahifalar
# o'z modul darajasidagi rang konstantalarini yangilaydi)
_THEME_CALLBACKS: list = []


def on_theme_change(callback) -> None:
    """`set_theme` chaqirilganda ishga tushadigan callback ro'yxatga qo'shadi.

    Modul birinchi yuklanganda darhol bir marta ham chaqiriladi
    (joriy mavzudagi konstantalarni o'rnatish uchun).
    """
    if callback not in _THEME_CALLBACKS:
        _THEME_CALLBACKS.append(callback)
    try:
        callback()
    except Exception:
        pass


def set_theme(theme: str) -> None:
    """Joriy mavzuni o'zgartiradi: "dark" yoki "light".

    `design_system.COLORS` ham shu palette bilan sinxron yangilanadi —
    eski kod (legacy) `color(token)` orqali to'g'ri qiymatni oladi.
    Barcha ro'yxatga olingan callback'lar ham ishga tushiriladi.
    """
    global _ACTIVE, _THEME_NAME
    name = str(theme).lower()
    _ACTIVE = dict(LIGHT if name == "light" else DARK)
    _THEME_NAME = "light" if name == "light" else "dark"

    # Legacy: design_system.COLORS ni sinxronlash
    try:
        from app.ui.design_system import COLORS as _LEGACY_COLORS
        _LEGACY_COLORS.clear()
        _LEGACY_COLORS.update(_ACTIVE)
    except Exception:
        pass

    # Mavzu o'zgarganda obuna bo'lganlarga xabar berish
    for cb in list(_THEME_CALLBACKS):
        try:
            cb()
        except Exception:
            pass


def C(key: str, fallback: str = "#ffffff") -> str:
    """Joriy mavzuda berilgan token qiymatini qaytaradi."""
    return _ACTIVE.get(key, fallback)


def is_light() -> bool:
    return _THEME_NAME == "light"


def current_theme() -> str:
    return _THEME_NAME


def active_palette() -> dict[str, str]:
    """Joriy palette nusxasini qaytaradi (read-only foydalanish uchun)."""
    return dict(_ACTIVE)
