from __future__ import annotations

"""
SmartHelmet product design system.

This module is the canonical place for UI/UX tokens described in the product
blueprint. PyQt pages can keep using ``app.ui.theme.C`` for compatibility, while
new modular UI code can import these structured tokens directly.
"""

COLORS = {
    "bg_main": "#03070b",
    "bg_card": "#0c151c",
    "bg_input": "#070d12",
    "bg_hover": "#1e293b",
    "bg_sidebar": "#05090d",
    "bg_panel": "#071016",
    "surface_raised": "#0f172a",
    "surface_soft": "#111827",
    "surface_muted": "#020617",
    "accent": "#fb923c",
    "accent_hover": "#f97316",
    "accent_dim": "#1c0e04",
    "accent_light": "#fdba74",
    "accent_subtle": "#0f0702",
    "text_primary": "#e2e8f0",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "text_link": "#22d3ee",
    "danger": "#ef4444",
    "danger_dim": "#3d1515",
    "success": "#34d399",
    "success_dim": "#064e3b",
    "warning": "#fbbf24",
    "warning_dim": "#2d2200",
    "info": "#22d3ee",
    "info_dim": "#0c2a3a",
    "border": "#1e293b",
    "border_light": "#0f172a",
    "border_accent": "#f97316",
    "border_hover": "#334155",
    "shadow": "#00000060",
    "overlay": "#0000008a",
    "scrollbar": "#1e293b",
    "scrollbar_hover": "#334155",
    "cam_active": "#34d399",
    "cam_idle": "#64748b",
    "cam_error": "#ef4444",
    "cam_rec": "#ef4444",
}

TYPOGRAPHY = {
    "font_family": "'Segoe UI', Arial, sans-serif",
    "size_xs": 9,
    "size_sm": 11,
    "size_base": 13,
    "size_md": 16,
    "size_lg": 20,
    "size_xl": 24,
    "weight_regular": 400,
    "weight_semibold": 700,
    "weight_bold": 800,
    "weight_black": 900,
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
}

RADIUS = {
    "xs": 4,
    "sm": 6,
    "md": 8,
    "lg": 10,
    "pill": 999,
}

MOTION = {
    "fast_ms": 120,
    "normal_ms": 180,
    "slow_ms": 260,
}

SHADOWS = {
    "panel": "0 14px 40px rgba(0,0,0,0.28)",
    "popover": "0 18px 60px rgba(0,0,0,0.42)",
}


def color(key: str, fallback: str = "#ffffff") -> str:
    return COLORS.get(key, fallback)


def space(key: str, fallback: int = 0) -> int:
    return SPACING.get(key, fallback)


def radius(key: str, fallback: int = 8) -> int:
    return RADIUS.get(key, fallback)
