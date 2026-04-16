"""
Qorong'i mavzu — SmartHelmet uchun rang palitrasi.
C(key) funksiya orqali rangga murojaat qilinadi.
"""

_DARK = {
    # Asosiy fonlar
    "bg_main":       "#0d1117",
    "bg_card":       "#161b22",
    "bg_input":      "#21262d",
    "bg_hover":      "#1f2937",
    "bg_sidebar":    "#13181f",

    # Aksent rang (xavfsizlik — oranj)
    "accent":        "#f97316",
    "accent_hover":  "#ea6a00",
    "accent_dim":    "#7c3d18",

    # Matn
    "text_primary":  "#e6edf3",
    "text_secondary":"#b0bec5",
    "text_muted":    "#6b7280",
    "text_link":     "#f97316",

    # Holat ranglari
    "danger":        "#f85149",
    "danger_dim":    "#5c2222",
    "success":       "#3fb950",
    "success_dim":   "#1a3a20",
    "warning":       "#d29922",
    "warning_dim":   "#3d2e00",

    # Chegaralar
    "border":        "#30363d",
    "border_light":  "#21262d",
    "border_accent": "#f97316",

    # Boshqalar
    "shadow":        "#00000080",
    "overlay":       "#00000099",
    "scrollbar":     "#30363d",
    "scrollbar_hover":"#484f58",
}


def C(key: str) -> str:
    """Mavzu rangini qaytaradi. Noma'lum kalit uchun fallback — oq."""
    return _DARK.get(key, "#ffffff")


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
        background-color: {C('bg_sidebar')};
        border-bottom: 1px solid {C('border')};
        spacing: 4px;
        padding: 0 8px;
    }}
    QToolBar QToolButton {{
        background: transparent;
        color: {C('text_secondary')};
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        font-size: 13px;
    }}
    QToolBar QToolButton:hover {{
        background-color: {C('bg_hover')};
        color: {C('text_primary')};
    }}
    QToolBar QToolButton:checked {{
        background-color: {C('accent_dim')};
        color: {C('accent')};
        font-weight: bold;
    }}
    QToolBar::separator {{
        background: {C('border')};
        width: 1px;
        margin: 6px 4px;
    }}

    /* ── StatusBar ───────────────────────────────────────── */
    QStatusBar {{
        background-color: {C('bg_sidebar')};
        color: {C('text_muted')};
        border-top: 1px solid {C('border')};
        font-size: 12px;
        padding: 2px 8px;
    }}
    QStatusBar::item {{
        border: none;
    }}

    /* ── ScrollBar ───────────────────────────────────────── */
    QScrollBar:vertical {{
        background: {C('bg_card')};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {C('scrollbar')};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {C('scrollbar_hover')};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: {C('bg_card')};
        height: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {C('scrollbar')};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {C('scrollbar_hover')};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ── QPushButton ─────────────────────────────────────── */
    QPushButton {{
        background-color: {C('bg_input')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background-color: {C('bg_hover')};
        border-color: {C('accent')};
        color: {C('accent')};
    }}
    QPushButton:pressed {{
        background-color: {C('accent_dim')};
    }}
    QPushButton[accent="true"] {{
        background-color: {C('accent')};
        color: #ffffff;
        border: none;
        font-weight: bold;
    }}
    QPushButton[accent="true"]:hover {{
        background-color: {C('accent_hover')};
    }}
    QPushButton[danger="true"] {{
        background-color: {C('danger_dim')};
        color: {C('danger')};
        border: 1px solid {C('danger')};
    }}

    /* ── QLineEdit ───────────────────────────────────────── */
    QLineEdit {{
        background-color: {C('bg_input')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 5px;
        padding: 7px 10px;
        font-size: 13px;
        selection-background-color: {C('accent_dim')};
    }}
    QLineEdit:focus {{
        border-color: {C('accent')};
    }}
    QLineEdit:disabled {{
        color: {C('text_muted')};
    }}

    /* ── QComboBox ───────────────────────────────────────── */
    QComboBox {{
        background-color: {C('bg_input')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 5px;
        padding: 6px 10px;
        font-size: 13px;
    }}
    QComboBox:focus {{
        border-color: {C('accent')};
    }}
    QComboBox QAbstractItemView {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        selection-background-color: {C('accent_dim')};
        outline: none;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
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
        width: 16px;
        height: 16px;
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

    /* ── QFrame ──────────────────────────────────────────── */
    QFrame[card="true"] {{
        background-color: {C('bg_card')};
        border: 1px solid {C('border')};
        border-radius: 8px;
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
    QTableWidget::item {{
        padding: 6px 10px;
        border: none;
    }}
    QTableWidget::item:selected {{
        color: {C('accent')};
    }}
    QHeaderView::section {{
        background-color: {C('bg_input')};
        color: {C('text_muted')};
        border: none;
        border-bottom: 1px solid {C('border')};
        padding: 8px 10px;
        font-size: 11px;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* ── QScrollArea ─────────────────────────────────────── */
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    /* ── QSplitter ───────────────────────────────────────── */
    QSplitter::handle {{
        background: {C('border')};
        width: 1px;
    }}

    /* ── QCheckBox ───────────────────────────────────────── */
    QCheckBox {{
        color: {C('text_primary')};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {C('border')};
        border-radius: 3px;
        background: {C('bg_input')};
    }}
    QCheckBox::indicator:checked {{
        background: {C('accent')};
        border-color: {C('accent')};
    }}

    /* ── QSpinBox / QDoubleSpinBox ───────────────────────── */
    QSpinBox, QDoubleSpinBox {{
        background-color: {C('bg_input')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 5px;
        padding: 6px 8px;
        font-size: 13px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {C('accent')};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: transparent;
        border: none;
        width: 18px;
    }}

    /* ── QGroupBox ───────────────────────────────────────── */
    QGroupBox {{
        color: {C('text_muted')};
        border: 1px solid {C('border')};
        border-radius: 6px;
        margin-top: 12px;
        font-size: 11px;
        font-weight: bold;
        padding: 10px 8px 8px 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 6px;
        color: {C('text_muted')};
        background: {C('bg_main')};
    }}

    /* ── QTabWidget ──────────────────────────────────────── */
    QTabWidget::pane {{
        border: 1px solid {C('border')};
        border-radius: 6px;
        background: {C('bg_card')};
    }}
    QTabBar::tab {{
        background: {C('bg_input')};
        color: {C('text_muted')};
        border: 1px solid {C('border')};
        border-bottom: none;
        border-radius: 4px 4px 0 0;
        padding: 8px 18px;
        margin-right: 2px;
        font-size: 12px;
    }}
    QTabBar::tab:selected {{
        background: {C('bg_card')};
        color: {C('accent')};
        border-bottom: 2px solid {C('accent')};
    }}
    QTabBar::tab:hover:!selected {{
        color: {C('text_primary')};
    }}

    /* ── QMessageBox ─────────────────────────────────────── */
    QMessageBox {{
        background-color: {C('bg_card')};
    }}
    QMessageBox QLabel {{
        color: {C('text_primary')};
        min-width: 280px;
    }}

    /* ── QDateEdit ───────────────────────────────────────── */
    QDateEdit {{
        background-color: {C('bg_input')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 5px;
        padding: 6px 10px;
        font-size: 13px;
    }}
    QDateEdit:focus {{
        border-color: {C('accent')};
    }}
    QDateEdit::drop-down {{
        border: none;
        width: 20px;
    }}
    QCalendarWidget {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
    }}
    QCalendarWidget QAbstractItemView {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
        selection-background-color: {C('accent_dim')};
    }}
    """
