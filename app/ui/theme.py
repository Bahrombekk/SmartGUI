"""
Qorong'i mavzu — SmartHelmet uchun rang palitrasi.
C(key) funksiya orqali rangga murojaat qilinadi.
"""

from app.ui.design_system import COLORS

_DARK = {
    # Asosiy fonlar — React SmartHelmet dizayni
    "bg_main":        "#03070b",
    "bg_card":        "#0c151c",
    "bg_input":       "#070d12",
    "bg_hover":       "#1e293b",
    "bg_sidebar":     "#05090d",
    "bg_panel":       "#071016",

    # Aksent — orange-400/500
    "accent":         "#fb923c",
    "accent_hover":   "#f97316",
    "accent_dim":     "#1c0e04",
    "accent_light":   "#fdba74",
    "accent_subtle":  "#0f0702",

    # Matn
    "text_primary":   "#e2e8f0",
    "text_secondary": "#94a3b8",
    "text_muted":     "#64748b",
    "text_link":      "#22d3ee",

    # Holat ranglari
    "danger":         "#ef4444",
    "danger_dim":     "#3d1515",
    "success":        "#34d399",
    "success_dim":    "#064e3b",
    "warning":        "#fbbf24",
    "warning_dim":    "#2d2200",
    "info":           "#22d3ee",
    "info_dim":       "#0c2a3a",

    # Chegaralar — slate-800
    "border":         "#1e293b",
    "border_light":   "#0f172a",
    "border_accent":  "#f97316",
    "border_hover":   "#334155",

    # Boshqalar
    "shadow":         "#00000060",
    "overlay":        "#0000008a",
    "scrollbar":      "#1e293b",
    "scrollbar_hover": "#334155",

    # Kamera holat ranglari
    "cam_active":     "#34d399",
    "cam_idle":       "#64748b",
    "cam_error":      "#ef4444",
    "cam_rec":        "#ef4444",
}


def C(key: str) -> str:
    """Mavzu rangini qaytaradi. Noma'lum kalit uchun fallback — oq."""
    return COLORS.get(key, _DARK.get(key, "#ffffff"))


def get_main_stylesheet() -> str:
    """QApplication uchun asosiy QSS uslubi."""
    return f"""
    /* ── Global ─────────────────────────────────────────── */
    QMainWindow, QDialog, QWidget {{
        background-color: {C('bg_main')};
        color: {C('text_primary')};
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
    }}

    /* ── Toolbar ─────────────────────────────────────────── */
    QToolBar {{
        background: {C('bg_sidebar')};
        border-bottom: 1px solid {C('border')};
        spacing: 4px;
        padding: 0 8px;
    }}
    QToolBar QToolButton {{
        background: transparent;
        color: {C('text_secondary')};
        border: none;
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 13px;
    }}
    QToolBar QToolButton:hover {{
        background-color: {C('bg_hover')};
        color: {C('text_primary')};
    }}
    QToolBar QToolButton:checked {{
        background-color: {C('bg_hover')};
        color: {C('accent')};
        font-weight: bold;
        border-bottom: 2px solid {C('accent')};
    }}
    QToolBar::separator {{
        background: {C('border')};
        width: 1px;
        margin: 6px 4px;
    }}

    /* ── StatusBar ───────────────────────────────────────── */
    QStatusBar {{
        background: {C('bg_sidebar')};
        color: {C('text_muted')};
        border-top: 1px solid {C('border')};
        font-size: 12px;
        padding: 2px 8px;
    }}
    QStatusBar::item {{ border: none; }}

    /* ── ScrollBar ───────────────────────────────────────── */
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {C('scrollbar')};
        border-radius: 3px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {C('scrollbar_hover')}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle:horizontal {{
        background: {C('scrollbar')};
        border-radius: 3px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {C('scrollbar_hover')}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* ── QPushButton ─────────────────────────────────────── */
    QPushButton {{
        background-color: {C('bg_panel')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background-color: {C('bg_hover')};
        border-color: {C('border_hover')};
        color: {C('text_primary')};
    }}
    QPushButton:pressed {{ background-color: {C('bg_hover')}; }}
    QPushButton[accent="true"] {{
        background: {C('accent')};
        color: #ffffff;
        border: none;
        font-weight: bold;
        border-radius: 6px;
    }}
    QPushButton[accent="true"]:hover {{ background: {C('accent_hover')}; }}
    QPushButton[danger="true"] {{
        background-color: {C('danger_dim')};
        color: {C('danger')};
        border: 1px solid {C('danger')};
    }}
    QPushButton[danger="true"]:hover {{ background-color: #5c2222; }}
    QPushButton[small="true"] {{
        padding: 4px 10px;
        font-size: 12px;
        border-radius: 4px;
    }}

    /* ── QLineEdit ───────────────────────────────────────── */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
        background: rgba(2,6,23,0.72);
        color: {C('text_primary')};
        border: 1px solid rgba(148,163,184,0.22);
        border-radius: 7px;
        padding: 0 10px;
        min-height: 34px;
        font-size: 13px;
        selection-background-color: rgba(249,115,22,0.24);
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover {{
        background: rgba(15,23,42,0.70);
        border-color: rgba(148,163,184,0.38);
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
        background: rgba(15,23,42,0.86);
        border: 1px solid rgba(251,146,60,0.74);
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled {{
        color: {C('text_muted')};
        border-color: rgba(148,163,184,0.12);
    }}
    QLineEdit::placeholder {{ color: {C('text_muted')}; }}

    /* ── QComboBox ───────────────────────────────────────── */
    QComboBox QAbstractItemView {{
        background-color: #071016;
        color: {C('text_primary')};
        border: 1px solid rgba(148,163,184,0.18);
        selection-background-color: rgba(249,115,22,0.14);
        outline: none;
    }}
    QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 26px; }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        border: none;
        width: 18px;
        background: transparent;
    }}

    /* ── QSlider ─────────────────────────────────────────── */
    QSlider::groove:horizontal {{
        height: 4px;
        background: {C('border')};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {C('accent')};
        border: none;
        width: 16px; height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QSlider::sub-page:horizontal {{
        background: {C('accent')};
        border-radius: 2px;
    }}

    /* ── QLabel ──────────────────────────────────────────── */
    QLabel {{
        color: {C('text_primary')};
        background: transparent;
    }}

    /* ── QFrame card ─────────────────────────────────────── */
    QFrame[card="true"] {{
        background-color: {C('bg_card')};
        border: 1px solid {C('border')};
        border-radius: 10px;
    }}
    QFrame[cam_panel="true"] {{
        background-color: #000000;
        border: 1px solid {C('border')};
        border-radius: 8px;
    }}
    QFrame[cam_panel="true"]:hover {{
        border-color: {C('accent_dim')};
    }}

    /* ── QTableWidget ────────────────────────────────────── */
    QTableWidget {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 6px;
        gridline-color: {C('border_light')};
        selection-background-color: {C('accent_dim')};
        outline: none;
    }}
    QTableWidget::item {{ padding: 6px 10px; border: none; }}
    QTableWidget::item:selected {{ color: {C('accent')}; }}
    QHeaderView::section {{
        background-color: {C('bg_panel')};
        color: {C('text_muted')};
        border: none;
        border-bottom: 1px solid {C('border')};
        padding: 8px 10px;
        font-size: 11px;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* ── QListWidget ─────────────────────────────────────── */
    QListWidget {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 6px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 8px 12px;
        border-bottom: 1px solid {C('border_light')};
    }}
    QListWidget::item:selected {{
        background-color: {C('accent_dim')};
        color: {C('accent_light')};
    }}
    QListWidget::item:hover:!selected {{ background-color: {C('bg_hover')}; }}

    /* ── QScrollArea ─────────────────────────────────────── */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}

    /* ── QSplitter ───────────────────────────────────────── */
    QSplitter::handle {{ background: {C('border')}; width: 1px; }}

    /* ── QCheckBox ───────────────────────────────────────── */
    QCheckBox {{ color: {C('text_primary')}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 2px solid {C('border')};
        border-radius: 3px;
        background: {C('bg_panel')};
    }}
    QCheckBox::indicator:checked {{
        background: {C('accent')};
        border-color: {C('accent')};
    }}
    QCheckBox::indicator:hover {{ border-color: {C('accent')}; }}

    /* ── QSpinBox / QDoubleSpinBox ───────────────────────── */
    QSpinBox, QDoubleSpinBox {{
        background-color: {C('bg_panel')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 5px;
        padding: 6px 8px;
        font-size: 13px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {C('accent')}; }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: transparent; border: none; width: 18px;
    }}

    /* ── QGroupBox ───────────────────────────────────────── */
    QGroupBox {{
        color: {C('accent_light')};
        border: 1px solid {C('border')};
        border-radius: 8px;
        margin-top: 14px;
        font-size: 11px;
        font-weight: bold;
        padding: 12px 8px 8px 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
        color: {C('accent')};
        background: {C('bg_main')};
        letter-spacing: 0.5px;
    }}

    /* ── QTabWidget ──────────────────────────────────────── */
    QTabWidget::pane {{
        border: 1px solid {C('border')};
        border-radius: 6px;
        background: {C('bg_card')};
    }}
    QTabBar::tab {{
        background: {C('bg_panel')};
        color: {C('text_muted')};
        border: 1px solid {C('border')};
        border-bottom: none;
        border-radius: 6px 6px 0 0;
        padding: 8px 18px;
        margin-right: 2px;
        font-size: 12px;
    }}
    QTabBar::tab:selected {{
        background: {C('bg_card')};
        color: {C('accent')};
        border-bottom: 2px solid {C('accent')};
        font-weight: bold;
    }}
    QTabBar::tab:hover:!selected {{ color: {C('accent_light')}; }}

    /* ── QMessageBox ─────────────────────────────────────── */
    QMessageBox {{ background-color: {C('bg_card')}; }}
    QMessageBox QLabel {{ color: {C('text_primary')}; min-width: 280px; }}

    /* ── QDateEdit ───────────────────────────────────────── */
    QDateEdit {{
        background-color: {C('bg_panel')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 5px;
        padding: 6px 10px;
        font-size: 13px;
    }}
    QDateEdit:focus {{ border-color: {C('accent')}; }}
    QDateEdit::drop-down {{ border: none; width: 20px; }}
    QCalendarWidget {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
    }}
    QCalendarWidget QAbstractItemView {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
        selection-background-color: {C('accent_dim')};
    }}

    /* ── QToolTip ────────────────────────────────────────── */
    QToolTip {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
        border: 1px solid {C('border_accent')};
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
    }}

    /* ── QProgressBar ────────────────────────────────────── */
    QProgressBar {{
        background: {C('bg_panel')};
        border: none;
        border-radius: 3px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        border-radius: 3px;
        background: {C('accent')};
    }}
    """
