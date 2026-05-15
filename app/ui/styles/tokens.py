"""
Markazlashtirilgan rang tokenlari — barcha UI ranglari shu yerda.

`set_theme("light")` yoki `set_theme("dark")` orqali butun ilova
ranglari almashtiriladi. Hech qaysi UI faylga rang hardcode qilinmasligi
kerak — har doim `C(token_name)` orqali murojaat qilinadi.
"""
from __future__ import annotations


# ── DARK PALETTE ──────────────────────────────────────────────────────────────
DARK: dict[str, str] = {
    # Asosiy fonlar
    "bg_main":         "#03070b",
    "bg_card":         "#0c151c",
    "bg_input":        "#070d12",
    "bg_hover":        "#1e293b",
    "bg_sidebar":      "#05090d",
    "bg_panel":        "#071016",
    "bg_panel_alt":    "#0e1d2e",
    "bg_panel_gradient_a": "#0c1520",
    "bg_panel_gradient_b": "#07101a",
    "bg_header_a":     "#091828",
    "bg_header_b":     "#071016",

    # Aksent — sabzi (orange)
    "accent":          "#fb923c",
    "accent_hover":    "#f97316",
    "accent_dim":      "#1c0e04",
    "accent_dim_2":    "rgba(249,115,22,0.10)",
    "accent_dim_3":    "rgba(249,115,22,0.20)",
    "accent_light":    "#fdba74",
    "accent_subtle":   "#0f0702",

    # Matn
    "text_primary":    "#e2e8f0",
    "text_secondary":  "#94a3b8",
    "text_muted":      "#64748b",
    "text_dim":        "#334155",
    "text_link":       "#22d3ee",
    "text_on_accent":  "#05090d",

    # Holat
    "danger":          "#ef4444",
    "danger_dim":      "#3d1515",
    "danger_dim_2":    "rgba(239,68,68,0.12)",
    "success":         "#34d399",
    "success_dim":     "#064e3b",
    "success_dim_2":   "rgba(52,211,153,0.10)",
    "warning":         "#fbbf24",
    "warning_dim":     "#2d2200",
    "warning_dim_2":   "rgba(251,191,36,0.10)",
    "info":            "#22d3ee",
    "info_dim":        "#0c2a3a",

    # Chegaralar
    "border":          "#1e293b",
    "border_light":    "#0f172a",
    "border_strong":   "#2d80c8",
    "border_accent":   "#f97316",
    "border_hover":    "#334155",
    "border_panel":    "#1e5fa8",
    "border_soft":     "#12314f",

    # Boshqa
    "shadow":          "#00000060",
    "overlay":         "#0000008a",
    "scrollbar":       "#1e293b",
    "scrollbar_hover": "#334155",

    # Kamera
    "cam_active":      "#34d399",
    "cam_idle":        "#64748b",
    "cam_error":       "#ef4444",
    "cam_rec":         "#ef4444",

    # Camera panel maxsus
    "campanel_bg":             "#060e18",
    "campanel_bg_selected":    "rgba(249,115,22,0.10)",
    "campanel_border":         "#1e5fa8",
    "campanel_pill_bg":        "rgba(30,95,168,0.40)",
    "campanel_pill_text":      "#93c5fd",
    "campanel_pill_border":    "rgba(30,95,168,0.70)",
    "campanel_name_text":      "#e8f4ff",
    "campanel_fps_text":       "#60a5fa",
    "campanel_video_bg":       "#0a0e14",

    # Input maxsus
    "input_bg":         "rgba(2,6,23,0.72)",
    "input_bg_hover":   "rgba(15,23,42,0.70)",
    "input_bg_focus":   "rgba(15,23,42,0.86)",
    "input_border":     "rgba(148,163,184,0.22)",
    "input_border_hov": "rgba(148,163,184,0.38)",
    "input_border_foc": "rgba(251,146,60,0.74)",
    "selection_bg":     "rgba(249,115,22,0.24)",
    "combo_view_bg":    "#071016",
    "combo_view_border": "rgba(148,163,184,0.18)",
    "danger_hover_bg":  "#5c2222",
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
