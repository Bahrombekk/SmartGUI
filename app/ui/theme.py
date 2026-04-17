"""
Qorong'i mavzu — SmartHelmet uchun rang palitrasi (sabzi-oranj uslub).
C(key) funksiya orqali rangga murojaat qilinadi.
"""

_DARK = {
    # Asosiy fonlar (iliq qoʻngʻir-qora)
    "bg_main":        "#0e0b08",
    "bg_card":        "#181210",
    "bg_input":       "#221a12",
    "bg_hover":       "#2e2016",
    "bg_sidebar":     "#130e08",
    "bg_panel":       "#1c1510",

    # Aksent rang — yorqin sabzi-oranj
    "accent":         "#ff6b1a",
    "accent_hover":   "#ff4d00",
    "accent_dim":     "#4d1f08",
    "accent_light":   "#ffa060",
    "accent_subtle":  "#3a1808",

    # Matn
    "text_primary":   "#f2e8dc",
    "text_secondary": "#c8a882",
    "text_muted":     "#7a6554",
    "text_link":      "#ff6b1a",

    # Holat ranglari
    "danger":         "#f85149",
    "danger_dim":     "#5c2222",
    "success":        "#3fb950",
    "success_dim":    "#1a3a20",
    "warning":        "#e3a020",
    "warning_dim":    "#4a3000",
    "info":           "#58a6ff",
    "info_dim":       "#1a2e4a",

    # Chegaralar (iliq)
    "border":         "#3d2a1a",
    "border_light":   "#281e14",
    "border_accent":  "#ff6b1a",
    "border_hover":   "#5a3a20",

    # Boshqalar
    "shadow":         "#00000090",
    "overlay":        "#0000009a",
    "scrollbar":      "#3d2a1a",
    "scrollbar_hover": "#5a3f28",

    # Kamera status badge ranglari
    "cam_active":     "#ff6b1a",
    "cam_idle":       "#4a3520",
    "cam_error":      "#f85149",
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
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1c1208, stop:1 {C('bg_sidebar')});
        border-bottom: 2px solid {C('accent_dim')};
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
        background-color: {C('accent_subtle')};
        color: {C('accent_light')};
    }}
    QToolBar QToolButton:checked {{
        background-color: {C('accent_dim')};
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
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {C('bg_sidebar')}, stop:1 #0a0705);
        color: {C('text_muted')};
        border-top: 1px solid {C('border')};
        font-size: 12px;
        padding: 2px 8px;
    }}
    QStatusBar::item {{ border: none; }}

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
    QScrollBar::handle:vertical:hover {{ background: {C('scrollbar_hover')}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
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
    QScrollBar::handle:horizontal:hover {{ background: {C('scrollbar_hover')}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

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
        background-color: {C('accent_subtle')};
        border-color: {C('accent')};
        color: {C('accent_light')};
    }}
    QPushButton:pressed {{ background-color: {C('accent_dim')}; }}
    QPushButton[accent="true"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {C('accent')}, stop:1 #e85000);
        color: #ffffff;
        border: none;
        font-weight: bold;
    }}
    QPushButton[accent="true"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {C('accent_hover')}, stop:1 #cc4400);
    }}
    QPushButton[danger="true"] {{
        background-color: {C('danger_dim')};
        color: {C('danger')};
        border: 1px solid {C('danger')};
    }}
    QPushButton[danger="true"]:hover {{
        background-color: #7a2828;
    }}
    QPushButton[small="true"] {{
        padding: 4px 10px;
        font-size: 12px;
        border-radius: 4px;
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
    QLineEdit:focus {{ border-color: {C('accent')}; }}
    QLineEdit:disabled {{ color: {C('text_muted')}; }}
    QLineEdit:hover {{ border-color: {C('border_hover')}; }}

    /* ── QComboBox ───────────────────────────────────────── */
    QComboBox {{
        background-color: {C('bg_input')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        border-radius: 5px;
        padding: 6px 10px;
        font-size: 13px;
    }}
    QComboBox:focus {{ border-color: {C('accent')}; }}
    QComboBox QAbstractItemView {{
        background-color: {C('bg_card')};
        color: {C('text_primary')};
        border: 1px solid {C('border')};
        selection-background-color: {C('accent_dim')};
        outline: none;
    }}
    QComboBox::drop-down {{ border: none; width: 24px; }}

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
        background-color: {C('bg_panel')};
        border: 1px solid {C('border')};
        border-radius: 10px;
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
    QListWidget::item:hover:!selected {{
        background-color: {C('accent_subtle')};
    }}

    /* ── QScrollArea ─────────────────────────────────────── */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}

    /* ── QSplitter ───────────────────────────────────────── */
    QSplitter::handle {{
        background: {C('border')};
        width: 1px;
    }}

    /* ── QCheckBox ───────────────────────────────────────── */
    QCheckBox {{ color: {C('text_primary')}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 2px solid {C('border')};
        border-radius: 3px;
        background: {C('bg_input')};
    }}
    QCheckBox::indicator:checked {{
        background: {C('accent')};
        border-color: {C('accent')};
    }}
    QCheckBox::indicator:hover {{ border-color: {C('accent')}; }}

    /* ── QSpinBox / QDoubleSpinBox ───────────────────────── */
    QSpinBox, QDoubleSpinBox {{
        background-color: {C('bg_input')};
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
        background: {C('bg_input')};
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
        background-color: {C('bg_input')};
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
    """
