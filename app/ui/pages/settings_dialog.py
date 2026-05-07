"""
SettingsDialog — sozlamalar sahifasi.
Chap sidebar navigatsiyasi bilan: Kameralar, Model, Telegram, Backend, Saqlash.
"""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox,
    QDoubleSpinBox, QSpinBox, QComboBox,
    QFileDialog, QStackedWidget, QWidget,
    QMessageBox, QScrollArea, QFrame,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QTreeWidget, QTreeWidgetItem,
    QInputDialog, QGridLayout, QSizePolicy, QMenu,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor

from app.ui.theme import C


# ── Test Thread ────────────────────────────────────────────────────────────

class _TestThread(QThread):
    result = pyqtSignal(bool, str)

    def __init__(self, mode: str, data: dict):
        super().__init__()
        self.mode = mode
        self.data = data

    def run(self):
        if self.mode == "telegram":
            try:
                import requests
                token = self.data.get("token", "")
                if not token:
                    self.result.emit(False, "Token kiritilmagan")
                    return
                chat_ids = self.data.get("chat_ids", [])
                r = requests.get(
                    f"https://api.telegram.org/bot{token}/getMe", timeout=10
                )
                if r.status_code != 200:
                    self.result.emit(False, f"Xatolik: {r.status_code}")
                    return
                name = r.json().get("result", {}).get("first_name", "Bot")
                if chat_ids:
                    msg = requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        data={"chat_id": chat_ids[0], "text": "SmartHelmet test notification"},
                        timeout=10,
                    )
                    if msg.status_code != 200:
                        self.result.emit(False, f"Bot ulandi, lekin chat test xato: {msg.status_code}")
                        return
                self.result.emit(True, f"Bot ulandi: {name}")
            except Exception as e:
                self.result.emit(False, str(e))
        elif self.mode == "model":
            model_path = self.data.get("path", "")
            if not os.path.exists(model_path):
                self.result.emit(False, f"Fayl topilmadi:\n{model_path}")
                return
            try:
                import numpy as np
                from ultralytics import YOLO

                model = YOLO(model_path, task="detect")
                dummy = np.zeros((320, 320, 3), dtype=np.uint8)
                model.predict([dummy], imgsz=320, conf=0.25, verbose=False, max_det=1, device="cpu")
                size = os.path.getsize(model_path) // (1024 * 1024)
                self.result.emit(True, f"Model yuklandi va sample inference o'tdi ({size} MB)")
            except Exception as e:
                self.result.emit(False, f"Model yuklanmadi: {e}")


# ── Kamera tahrirlash dialogi ──────────────────────────────────────────────

class _ClickableRow(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("pressed", "false")
        self.setProperty("selected", "false")

    def mousePressEvent(self, event):
        self._set_pressed(True)
        self.clicked.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._set_pressed(False)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._set_pressed(False)
        super().leaveEvent(event)

    def _set_pressed(self, pressed: bool):
        self.setProperty("pressed", "true" if pressed else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class CameraEditDialog(QDialog):
    def __init__(self, camera: dict | None = None, departments: list | None = None,
                 parent=None):
        super().__init__(parent)
        self._camera = dict(camera) if camera else {}
        self._departments = departments or []
        is_edit = bool(camera)
        self.setWindowTitle("Kamera tahrirlash" if is_edit else "Yangi kamera qo'shish")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._setup_ui()
        if is_edit:
            self._load_values()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        title_lbl = QLabel(
            "Kamera ma'lumotlarini kiriting" if not self._camera
            else f"Kamera #{self._camera.get('id', '?')} ni tahrirlash"
        )
        title_lbl.setStyleSheet(f"color: {C('accent')}; font-size: 14px; font-weight: bold;")
        root.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C('border')};")
        root.addWidget(sep)

        root.addWidget(self._lbl("Bo'lim:"))
        self._department_combo = QComboBox()
        for dep in self._departments:
            self._department_combo.addItem(dep.get("name", "Bo'lim"), dep.get("id"))
        root.addWidget(self._department_combo)

        root.addWidget(self._lbl("Kamera nomi:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Masalan: Sex № 1, Kirish kamerasi…")
        root.addWidget(self._name_edit)

        root.addWidget(self._lbl("RTSP URL:"))
        self._rtsp_edit = QLineEdit()
        self._rtsp_edit.setPlaceholderText(
            "rtsp://admin:parol@192.168.1.100:554/Streaming/Channels/101"
        )
        root.addWidget(self._rtsp_edit)

        root.addWidget(self._lbl("Company ID:"))
        self._company_edit = QLineEdit()
        self._company_edit.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        root.addWidget(self._company_edit)

        self._enabled_check = QCheckBox("Kamerani yoqish (faollashtirish)")
        self._enabled_check.setChecked(True)
        root.addWidget(self._enabled_check)
        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("  Saqlash  ")
        save_btn.setFixedHeight(34)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('accent')}; color: white; border: none;
                border-radius: 6px; padding: 0 20px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C('accent_hover')}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {C('text_secondary')}; font-size: 12px;")
        return l

    def _load_values(self):
        self._name_edit.setText(self._camera.get("name", ""))
        self._rtsp_edit.setText(self._camera.get("rtsp_url", ""))
        self._company_edit.setText(self._camera.get("company_id", ""))
        self._enabled_check.setChecked(self._camera.get("enabled", True))
        idx = self._department_combo.findData(self._camera.get("department_id"))
        if idx >= 0:
            self._department_combo.setCurrentIndex(idx)

    def _on_save(self):
        name = self._name_edit.text().strip()
        rtsp = self._rtsp_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Xatolik", "Kamera nomi kiritilishi shart.")
            return
        if not rtsp:
            QMessageBox.warning(self, "Xatolik", "RTSP URL kiritilishi shart.")
            return
        self._camera.update({
            "name": name,
            "rtsp_url": rtsp,
            "company_id": self._company_edit.text().strip(),
            "department_id": self._department_combo.currentData(),
            "enabled": self._enabled_check.isChecked(),
        })
        self.accept()

    def get_camera(self) -> dict:
        return dict(self._camera)


# ── Sozlamalar Sahifasi ────────────────────────────────────────────────────

class SettingsPage(QWidget):
    settings_saved = pyqtSignal()

    NAV_CAMERAS  = 0
    NAV_MODEL    = 1
    NAV_FACEID   = 2
    NAV_TELEGRAM = 3
    NAV_BACKEND  = 4
    NAV_STORAGE  = 5
    NAV_PERF     = 6
    NAV_DIAG     = 7

    _NAV_ITEMS = [
        (0, "camera.svg",  "Kameralar"),
        (1, "cpu.svg",     "AI Model"),
        (2, "users.svg",   "FaceID"),
        (3, "send.svg",    "Notifications"),
        (4, "server.svg",  "Backend Sync"),
        (5, "database.svg","Saqlash"),
        (6, "settings.svg","Performance"),
        (7, "info.svg",    "Diagnostics"),
    ]

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self._test_thread = None
        self._nav_btns: dict[int, QPushButton] = {}
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"
        self._setup_ui()
        self._load_values()

    # ── Root layout ───────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setObjectName("settingsPage")
        self.setStyleSheet("""
            QWidget#settingsPage {
                background: #03070b;
            }
            QLabel {
                border: none;
                background: transparent;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: rgba(2,6,23,0.72);
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 7px;
                padding: 0 10px;
                min-height: 34px;
                font-size: 13px;
                selection-background-color: #fb923c;
            }
            QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
                background: rgba(15,23,42,0.70);
                border-color: rgba(148,163,184,0.38);
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                background: rgba(15,23,42,0.86);
                border: 1px solid rgba(251,146,60,0.74);
            }
            QComboBox::drop-down {
                border: none;
                width: 26px;
            }
            QComboBox QAbstractItemView {
                background: #071016;
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.18);
                selection-background-color: rgba(249,115,22,0.14);
            }
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                border: none;
                width: 18px;
                background: transparent;
            }
            QLineEdit::placeholder {
                color: #64748b;
            }
            QCheckBox {
                color: #cbd5e1;
                spacing: 8px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #334155;
                background: #071016;
            }
            QCheckBox::indicator:checked {
                background: #fb923c;
                border-color: #fb923c;
            }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        vsep = QWidget()
        vsep.setFixedWidth(1)
        vsep.setStyleSheet("background: #1e293b;")
        root.addWidget(vsep)

        content_w = QWidget()
        content_w.setStyleSheet("background: #03070b;")
        c_lay = QVBoxLayout(content_w)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._make_cameras_page())
        self._stack.addWidget(self._make_model_page())
        self._stack.addWidget(self._make_faceid_page())
        self._stack.addWidget(self._make_telegram_page())
        self._stack.addWidget(self._make_backend_page())
        self._stack.addWidget(self._make_storage_page())
        self._stack.addWidget(self._make_performance_page())
        self._stack.addWidget(self._make_diagnostics_page())
        c_lay.addWidget(self._stack, 1)
        c_lay.addWidget(self._build_footer())
        root.addWidget(content_w, 1)

        self._switch_nav(self.NAV_CAMERAS)

    # ── Sidebar ───────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setFixedWidth(228)
        sidebar.setObjectName("settingsSidebar")
        sidebar.setStyleSheet(
            "QFrame#settingsSidebar {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #07111b,stop:1 #050a10);"
            "border: none;"
            "}"
        )
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(20, 32, 20, 22)
        lay.setSpacing(8)

        sec_title = QLabel("SOZLAMALAR")
        sec_title.setStyleSheet(
            "color: #475569; font-size: 10px; font-weight: 900; "
            "padding: 0 8px 10px 8px; background: transparent;"
        )
        lay.addWidget(sec_title)

        for idx, icon_file, label in self._NAV_ITEMS:
            btn = QPushButton(f"   {label}")
            btn.setFixedHeight(50)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            icon_path = self._icon_dir / icon_file
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(16, 16))
            btn.setStyleSheet(self._nav_style(False))
            btn.clicked.connect(lambda _, i=idx: self._switch_nav(i))
            lay.addWidget(btn)
            self._nav_btns[idx] = btn

        lay.addStretch()

        # Help box
        help_box = QFrame()
        help_box.setObjectName("helpBox")
        help_box.setStyleSheet(
            "QFrame#helpBox {"
            "background: rgba(15,23,42,0.66);"
            "border: 1px solid rgba(148,163,184,0.12);"
            "border-radius: 10px;"
            "}"
        )
        h = QVBoxLayout(help_box)
        h.setContentsMargins(14, 14, 14, 14)
        h.setSpacing(6)

        icon = QLabel()
        icon.setFixedSize(26, 26)
        icon.setStyleSheet("background: transparent; border: none;")
        pix = self._colored_icon(str(self._icon_dir / "headset.svg"), "#fb923c", 24)
        if pix:
            icon.setPixmap(pix)

        ht = QLabel("Yordam kerakmi?")
        ht.setStyleSheet(
            "color: #f8fafc; font-size: 12px; font-weight: 700; background: transparent; border: none;"
        )
        hd = QLabel("Biz bilan bog'laning,\nyordam beramiz.")
        hd.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 11px; background: transparent; border: none;"
        )
        hd.setWordWrap(True)

        contact_btn = QPushButton("Bog'lanish")
        contact_btn.setFixedHeight(32)
        contact_btn.setStyleSheet(self._secondary_btn_style())

        h.addWidget(icon)
        h.addWidget(ht)
        h.addWidget(hd)
        h.addWidget(contact_btn)
        lay.addWidget(help_box)
        return sidebar

    def _switch_nav(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in self._nav_btns.items():
            active = i == idx
            btn.setChecked(active)
            btn.setStyleSheet(self._nav_style(active))
            # Ikonni rang bilan yangilash
            icon_file = self._NAV_ITEMS[i][1]
            icon_path = self._icon_dir / icon_file
            if icon_path.exists():
                color = "#fb923c" if active else "#64748b"
                pix = self._colored_icon(str(icon_path), color, 16)
                if pix:
                    btn.setIcon(QIcon(pix))

    # ── Footer ────────────────────────────────────────────────────────────

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        footer.setStyleSheet(
            "QFrame#settingsFooter { background: #05090d; border-top: 1px solid rgba(148,163,184,0.12); }"
        )
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(8)

        hint = QLabel("O'zgarishlar saqlangandan keyin kameralar qayta ishga tushiriladi.")
        hint.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        lay.addWidget(hint, 1)

        self._restart_indicator = QLabel("Restart needed after save")
        self._restart_indicator.setStyleSheet(
            "color: #fdba74; background: rgba(249,115,22,0.10);"
            "border: 1px solid rgba(249,115,22,0.20); border-radius: 8px;"
            "padding: 5px 9px; font-size: 11px; font-weight: 800;"
        )
        lay.addWidget(self._restart_indicator)

        cancel_btn = QPushButton("  Bekor qilish")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setStyleSheet(self._secondary_btn_style())
        self._set_button_icon(cancel_btn, "x.svg", "#cbd5e1", 16)
        cancel_btn.clicked.connect(self._load_values)

        save_btn = QPushButton("  Saqlash")
        save_btn.setFixedHeight(36)
        save_btn.setStyleSheet(self._primary_btn_style())
        self._set_button_icon(save_btn, "check.svg", "#ffffff", 16)
        save_btn.clicked.connect(self._save)

        lay.addWidget(cancel_btn)
        lay.addWidget(save_btn)
        return footer

    # ── Style helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _nav_style(active: bool) -> str:
        if active:
            return (
                "QPushButton {"
                "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(249,115,22,0.20),stop:1 rgba(249,115,22,0.06));"
                "  color: #fb923c;"
                "  border: none;"
                "  border-radius: 6px;"
                "  text-align: left;"
                "  font-size: 14px;"
                "  font-weight: 800;"
                "  padding-left: 14px;"
                "}"
            )
        return (
            "QPushButton {"
            "  background: transparent;"
            "  color: #cbd5e1;"
            "  border: none;"
            "  border-radius: 6px;"
            "  text-align: left;"
            "  font-size: 14px;"
            "  padding-left: 14px;"
            "}"
            "QPushButton:hover {"
            "  background: #071016;"
            "  color: #e2e8f0;"
            "}"
        )

    @staticmethod
    def _primary_btn_style() -> str:
        return (
            f"QPushButton {{ background: {C('accent')}; color: #fff; border: none; "
            f"border-radius: 7px; padding: 0 18px; font-weight: 800; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {C('accent_hover')}; }}"
        )

    @staticmethod
    def _secondary_btn_style() -> str:
        return (
            "QPushButton { background: #071016; color: #cbd5e1; "
            "border: 1px solid rgba(148,163,184,0.14); border-radius: 7px; "
            "padding: 0 14px; font-size: 13px; }"
            "QPushButton:hover { border-color: rgba(251,146,60,0.45); color: #f8fafc; background: #0f172a; }"
        )

    @staticmethod
    def _danger_btn_style() -> str:
        return (
            f"QPushButton {{ background: {C('danger_dim')}; color: {C('danger')}; "
            f"border: 1px solid rgba(239,68,68,0.35); border-radius: 7px; "
            f"padding: 0 14px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #5c2222; }}"
        )

    def _panel(self, inner: bool = False) -> QFrame:
        f = QFrame()
        f.setObjectName("settingsInnerPanel" if inner else "settingsPanel")
        bg = "rgba(7,16,22,0.72)" if inner else "rgba(15,23,42,0.58)"
        border = "rgba(148,163,184,0.10)" if inner else "rgba(148,163,184,0.14)"
        name = f.objectName()
        f.setStyleSheet(
            f"QFrame#{name} {{ background: {bg}; border: 1px solid {border}; border-radius: 9px; }}"
        )
        return f

    # ── Scroll page wrapper ───────────────────────────────────────────────

    def _scroll_page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #07111b,stop:0.55 #050a10,stop:1 #071016);"
        )
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        inner_w = QWidget()
        inner_w.setStyleSheet("background: transparent;")
        inner_lay = QVBoxLayout(inner_w)
        inner_lay.setContentsMargins(42, 36, 42, 30)
        inner_lay.setSpacing(18)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(inner_w)
        outer.addWidget(scroll)
        return page, inner_lay

    def _page_header(self, title: str, subtitle: str) -> QHBoxLayout:
        hdr = QHBoxLayout()
        hdr.setSpacing(14)
        icon_map = {
            "Kameralar": ("video.svg", "#fb923c"),
            "Model": ("cpu.svg", "#22d3ee"),
            "Telegram": ("send.svg", "#38bdf8"),
            "Backend API": ("server.svg", "#a78bfa"),
            "Saqlash": ("database.svg", "#34d399"),
        }
        icon_file, icon_color = icon_map.get(title, ("settings.svg", "#fb923c"))
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(38, 38)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        pix = self._colored_icon(str(self._icon_dir / icon_file), icon_color, 30)
        if pix:
            icon_lbl.setPixmap(pix)
        hdr.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(3)
        t = QLabel(title)
        t.setStyleSheet("color: #f8fafc; font-size: 24px; font-weight: 900; background: transparent;")
        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {C('text_muted')}; font-size: 13px; background: transparent;")
        col.addWidget(t)
        col.addWidget(s)
        hdr.addLayout(col, 1)
        return hdr

    # ── Cameras page ──────────────────────────────────────────────────────

    def _make_cameras_page(self) -> QWidget:
        page, lay = self._scroll_page()

        hdr = self._page_header("Kameralar", "Tizimga ulangan RTSP kameralarni boshqarish")
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._settings_summary = QLabel("")
        self._settings_summary.setStyleSheet(
            "color: #34d399; background: rgba(52,211,153,0.10);"
            "border: none; border-radius: 7px;"
            "padding: 4px 12px; font-size: 12px; font-weight: 800;"
        )
        self._cam_count_lbl = QLabel("")
        self._cam_count_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 12px; font-weight: 900;"
        )
        right_col.addWidget(self._settings_summary, 0, Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._cam_count_lbl, 0, Qt.AlignmentFlag.AlignRight)
        hdr.addLayout(right_col)
        lay.addLayout(hdr)

        # Stat cards
        stat_row = QHBoxLayout()
        stat_row.setSpacing(10)
        self._total_stat   = self._stat_card("Jami",   "0", "10 tagacha kamera", "video.svg",   "#312e81", "#7c3aed")
        self._enabled_stat = self._stat_card("Faol",   "0", "ishga tushadi",     "wifi.svg",    "#14532d", "#16a34a")
        self._dept_stat    = self._stat_card("Bo'lim", "0", "lokatsiya",         "map-pin.svg", "#1e3a8a", "#1d4ed8")
        stat_row.addWidget(self._total_stat)
        stat_row.addWidget(self._enabled_stat)
        stat_row.addWidget(self._dept_stat)
        lay.addLayout(stat_row)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(8)
        add_dep = QPushButton("Bo'lim")
        add_dep.setFixedHeight(36)
        add_dep.setStyleSheet(self._secondary_btn_style())
        self._set_button_icon(add_dep, "plus.svg", "#cbd5e1", 16)
        add_dep.clicked.connect(self._add_department)

        add_cam = QPushButton("Kamera")
        add_cam.setFixedHeight(36)
        add_cam.setStyleSheet(self._primary_btn_style())
        self._set_button_icon(add_cam, "plus.svg", "#ffffff", 16)
        add_cam.clicked.connect(self._add_camera)

        edit_btn = QPushButton("  Tahrirlash")
        edit_btn.setFixedHeight(36)
        edit_btn.setStyleSheet(self._secondary_btn_style())
        self._set_button_icon(edit_btn, "pencil.svg", "#cbd5e1", 16)
        edit_btn.clicked.connect(self._edit_camera)

        del_btn = QPushButton("  O'chirish")
        del_btn.setFixedHeight(36)
        del_btn.setStyleSheet(self._danger_btn_style())
        self._set_button_icon(del_btn, "trash.svg", "#ef4444", 16)
        del_btn.clicked.connect(self._delete_camera)

        tb.addWidget(add_dep)
        tb.addWidget(add_cam)
        tb.addWidget(edit_btn)
        tb.addWidget(del_btn)
        tb.addStretch()
        lay.addLayout(tb)

        # Split: departments | cameras
        split = QHBoxLayout()
        split.setSpacing(12)

        # Departments panel
        list_panel = self._panel()
        lp_lay = QVBoxLayout(list_panel)
        lp_lay.setContentsMargins(14, 14, 14, 14)
        lp_lay.setSpacing(10)

        list_title = QLabel("Bo'limlar")
        list_title.setStyleSheet("color: #f8fafc; font-size: 15px; font-weight: 900;")
        lp_lay.addWidget(list_title)

        self._dept_search = QLineEdit()
        self._dept_search.setPlaceholderText("Bo'lim qidirish...")
        self._dept_search.setFixedHeight(34)
        self._dept_search.setStyleSheet("""
            QLineEdit {
                background: rgba(2,6,23,0.72); color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 7px;
                padding: 0 10px; font-size: 12px;
            }
            QLineEdit:hover {
                background: rgba(15,23,42,0.70);
                border-color: rgba(148,163,184,0.38);
            }
            QLineEdit:focus {
                background: rgba(15,23,42,0.86);
                border: 1px solid rgba(251,146,60,0.74);
            }
        """)
        self._dept_search.textChanged.connect(self._filter_department_list)
        lp_lay.addWidget(self._dept_search)

        self._dept_list = QTreeWidget()
        self._dept_list.setObjectName("departmentList")
        self._dept_list.setHeaderHidden(True)
        self._dept_list.setRootIsDecorated(False)
        self._dept_list.setIndentation(0)
        self._dept_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._dept_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._dept_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._dept_list.setAlternatingRowColors(False)
        self._dept_list.setStyleSheet(f"""
            QTreeWidget {{
                background: rgba(7,16,22,0.26);
                border: 1px solid rgba(148,163,184,0.16);
                border-radius: 8px;
                outline: none;
                padding: 4px;
            }}
            QTreeWidget::item {{
                background: transparent;
                border: none;
                padding: 0;
                margin: 0;
                color: #e2e8f0;
            }}
            QTreeWidget::item:selected {{
                background: transparent;
            }}
            QTreeWidget::item:hover:!selected {{
                background: transparent;
            }}
            QTreeWidget::branch {{
                background: transparent;
            }}
            QTreeWidget::branch:has-siblings,
            QTreeWidget::branch:adjoins-item {{
                border-image: none;
            }}
        """)
        self._dept_list.itemClicked.connect(self._on_department_tree_clicked)
        self._dept_list.itemSelectionChanged.connect(self._on_department_selection_changed)
        self._dept_list.itemExpanded.connect(self._sync_department_row_state)
        self._dept_list.itemCollapsed.connect(self._sync_department_row_state)
        lp_lay.addWidget(self._dept_list, 1)
        split.addWidget(list_panel, 2)

        # Camera panel
        detail_panel = self._panel()
        dp_lay = QVBoxLayout(detail_panel)
        dp_lay.setContentsMargins(16, 16, 16, 16)
        dp_lay.setSpacing(10)

        det_hdr = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        detail_title = QLabel("Kamera")
        detail_title.setStyleSheet("color: #f8fafc; font-size: 15px; font-weight: 900;")
        self._detail_name = QLabel("Kamera tanlang")
        self._detail_name.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 700;")
        title_box.addWidget(detail_title)
        title_box.addWidget(self._detail_name)
        det_hdr.addLayout(title_box, 1)
        self._detail_status = QLabel("")
        self._detail_status.setStyleSheet(
            "color: #34d399; background: rgba(52,211,153,0.12);"
            "border: none;"
            "border-radius: 8px; padding: 3px 10px; font-size: 11px; font-weight: 800;"
        )
        det_hdr.addWidget(self._detail_status)
        more_btn = QPushButton("⋮")
        more_btn.setFixedSize(28, 28)
        more_btn.setStyleSheet(self._secondary_btn_style())
        more_btn.setText("")
        self._set_button_icon(more_btn, "more-vertical.svg", "#94a3b8", 16)
        more_menu = QMenu(more_btn)
        more_menu.setStyleSheet("""
            QMenu {
                background: #071016;
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.18);
                border-radius: 7px;
                padding: 4px;
            }
            QMenu::item {
                padding: 7px 22px 7px 10px;
                border-radius: 5px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background: rgba(249,115,22,0.12);
                color: #fb923c;
            }
        """)
        edit_action = QAction("Izmenit", more_menu)
        edit_action.triggered.connect(self._edit_camera)
        more_menu.addAction(edit_action)
        more_btn.clicked.connect(
            lambda: more_menu.exec(more_btn.mapToGlobal(more_btn.rect().bottomRight()))
        )
        det_hdr.addWidget(more_btn)
        dp_lay.addLayout(det_hdr)

        self._cam_list = QListWidget()
        self._cam_list.setObjectName("cameraList")
        self._cam_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._cam_list.setAlternatingRowColors(False)
        self._cam_list.setFixedHeight(58)
        self._cam_list.setStyleSheet("""
            QListWidget {
                background: rgba(7,16,22,0.36); border: none; outline: none;
                border-radius: 8px;
            }
            QListWidget::item {
                border: none; border-radius: 7px;
                padding: 8px 12px; margin: 2px; color: #e2e8f0;
            }
            QListWidget::item:selected {
                background: rgba(249,115,22,0.12);
                color: #f8fafc;
            }
            QListWidget::item:hover:!selected { background: #0f172a; }
        """)
        self._cam_list.itemDoubleClicked.connect(self._edit_camera)
        self._cam_list.itemSelectionChanged.connect(self._update_camera_preview)
        dp_lay.addWidget(self._cam_list)

        self._inline_edit_panel = self._build_inline_camera_editor()
        self._inline_edit_panel.hide()
        dp_lay.addWidget(self._inline_edit_panel)

        self._detail_ip      = self._detail_row("IP", "--")
        self._detail_dep     = self._detail_row("Bo'lim", "--")
        self._detail_company = self._detail_row("Company", "--")
        self._detail_rtsp    = self._detail_row("RTSP", "--")
        dp_lay.addWidget(self._detail_ip)
        dp_lay.addWidget(self._detail_dep)
        dp_lay.addWidget(self._detail_company)
        dp_lay.addWidget(self._detail_rtsp)
        dp_lay.addStretch()

        # Info hint box
        hint_box = QFrame()
        hint_box.setStyleSheet(
            "QFrame { background: rgba(34,211,238,0.06);"
            "border: 1px solid rgba(34,211,238,0.18); border-radius: 7px; }"
        )
        hb = QHBoxLayout(hint_box)
        hb.setContentsMargins(12, 10, 12, 10)
        hb.setSpacing(8)
        hi = QLabel("ℹ")
        hi.setStyleSheet("color: #22d3ee; font-size: 14px; background: transparent; border: none;")
        hi.setText("")
        hi.setFixedSize(18, 18)
        info_pix = self._colored_icon(str(self._icon_dir / "info.svg"), "#22d3ee", 16)
        if info_pix:
            hi.setPixmap(info_pix)
        ht = QLabel("Ikki marta bosish yoki Tahrirlash orqali kamera ma'lumotlarini o'zgartiring.")
        ht.setWordWrap(True)
        ht.setStyleSheet("color: #22d3ee; font-size: 11px; background: transparent; border: none;")
        hb.addWidget(hi)
        hb.addWidget(ht, 1)
        dp_lay.addWidget(hint_box)

        split.addWidget(detail_panel, 3)
        lay.addLayout(split, 1)
        return page

    def _stat_card(self, title: str, value: str, caption: str,
                   icon_file: str = "", icon_bg: str = "#0f172a",
                   icon_color: str = "#64748b") -> QFrame:
        card = self._panel()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        icon_box = QLabel()
        icon_box.setObjectName("statIconBox")
        icon_box.setFixedSize(54, 54)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet(
            f"QLabel#statIconBox {{ background: {icon_bg}; border: none; border-radius: 12px; }}"
        )
        icon_path = self._icon_dir / icon_file
        if icon_file and icon_path.exists():
            colored = self._colored_icon(str(icon_path), icon_color, 26)
            if colored:
                icon_box.setPixmap(colored)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px; font-weight: 800;")
        v = QLabel(value)
        v.setObjectName("statValue")
        v.setStyleSheet("color: #f8fafc; font-size: 28px; font-weight: 900;")
        c = QLabel(caption)
        c.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        text_col.addWidget(t)
        text_col.addWidget(v)
        text_col.addWidget(c)

        lay.addWidget(icon_box)
        lay.addLayout(text_col, 1)
        return card

    def _colored_icon(self, svg_path: str, color: str, size: int = 20) -> "QPixmap | None":
        """SVG faylni berilgan rang bilan QPixmap ga aylantiradi."""
        try:
            import re
            from PyQt6.QtSvg import QSvgRenderer
            from PyQt6.QtCore import QByteArray
            with open(svg_path, "r", encoding="utf-8") as f:
                content = f.read()
            # "none" qiymatlarini saqlab, faqat rang qiymatlarini almashtirish
            content = re.sub(r'stroke="(?!none)[^"]*"', f'stroke="{color}"', content)
            content = re.sub(r'fill="(?!none)[^"]*"', f'fill="{color}"', content)
            renderer = QSvgRenderer(QByteArray(content.encode()))
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return pixmap
        except Exception:
            return None

    def _set_button_icon(self, button: QPushButton, icon_file: str,
                         color: str = "#cbd5e1", size: int = 16):
        pix = self._colored_icon(str(self._icon_dir / icon_file), color, size)
        if pix:
            button.setIcon(QIcon(pix))
            button.setIconSize(QSize(size, size))

    def _department_row_widget(self, item: QTreeWidgetItem, name: str,
                               count: int, enabled_count: int) -> QWidget:
        row = _ClickableRow()
        row.setObjectName("deptRow")
        row.setFixedHeight(58)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet("""
            QWidget#deptRow {
                background: rgba(15,23,42,0.46);
                border: 1px solid rgba(148,163,184,0.18);
                border-radius: 8px;
            }
            QWidget#deptRow:hover {
                background: rgba(15,23,42,0.68);
                border: 1px solid rgba(148,163,184,0.34);
            }
            QWidget#deptRow[pressed="true"] {
                background: rgba(30,41,59,0.78);
                border: 1px solid rgba(203,213,225,0.46);
            }
            QWidget#deptRow[selected="true"] {
                background: rgba(249,115,22,0.10);
                border: 1px solid rgba(251,146,60,0.74);
            }
            QWidget#deptRow[selected="true"]:hover {
                background: rgba(249,115,22,0.14);
                border: 1px solid rgba(251,146,60,0.86);
            }
            QWidget#deptRow[selected="true"][pressed="true"] {
                background: rgba(249,115,22,0.18);
                border: 1px solid rgba(253,186,116,0.90);
            }
        """)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 0, 12, 0)
        lay.setSpacing(10)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("color: #f8fafc; font-size: 14px; font-weight: 800;")
        lay.addWidget(name_lbl, 1)

        count_lbl = QLabel(f"{count}")
        count_lbl.setToolTip(f"{count} ta kamera / {enabled_count} ta faol")
        count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_lbl.setFixedSize(28, 22)
        count_lbl.setStyleSheet(
            "color: #cbd5e1; background: rgba(148,163,184,0.10);"
            "border: none; border-radius: 11px; font-size: 11px; font-weight: 900;"
        )
        lay.addWidget(count_lbl)

        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"background: {'#22c55e' if enabled_count else '#64748b'};"
            "border-radius: 5px; border: none;"
        )
        lay.addWidget(dot)

        arrow = QPushButton()
        arrow.setObjectName("deptArrow")
        arrow.setFixedSize(28, 28)
        arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        arrow.setStyleSheet(
            "QPushButton#deptArrow { background: transparent; border: none; border-radius: 6px; }"
            "QPushButton#deptArrow:hover { background: rgba(148,163,184,0.12); }"
        )
        self._set_button_icon(arrow, "chevron-down.svg" if item.isExpanded() else "chevron-right.svg", "#e2e8f0", 18)
        arrow.clicked.connect(lambda: self._toggle_department_item(item))
        lay.addWidget(arrow)

        row.clicked.connect(lambda: self._select_department_item(item))
        item.setData(0, Qt.ItemDataRole.UserRole + 2, arrow)
        return row

    def _camera_tree_row_widget(self, item: QTreeWidgetItem, cam: dict) -> QWidget:
        enabled = cam.get("enabled", True)
        row = _ClickableRow()
        row.setObjectName("deptCameraRow")
        row.setFixedHeight(42)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet("""
            QWidget#deptCameraRow {
                background: rgba(2,6,23,0.34);
                border: 1px solid rgba(148,163,184,0.14);
                border-radius: 7px;
            }
            QWidget#deptCameraRow:hover {
                background: rgba(15,23,42,0.58);
                border: 1px solid rgba(148,163,184,0.30);
            }
            QWidget#deptCameraRow[pressed="true"] {
                background: rgba(30,41,59,0.70);
                border: 1px solid rgba(203,213,225,0.40);
            }
            QWidget#deptCameraRow[selected="true"] {
                background: rgba(249,115,22,0.09);
                border: 1px solid rgba(251,146,60,0.68);
            }
            QWidget#deptCameraRow[selected="true"]:hover {
                background: rgba(249,115,22,0.13);
                border: 1px solid rgba(251,146,60,0.84);
            }
            QWidget#deptCameraRow[selected="true"][pressed="true"] {
                background: rgba(249,115,22,0.17);
                border: 1px solid rgba(253,186,116,0.88);
            }
        """)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(18, 0, 10, 0)
        lay.setSpacing(10)

        icon = QLabel()
        icon.setFixedSize(20, 20)
        pix = self._colored_icon(str(self._icon_dir / "camera-small.svg"), "#cbd5e1", 16)
        if pix:
            icon.setPixmap(pix)
        lay.addWidget(icon)

        name_lbl = QLabel(cam.get("name", "Kamera"))
        name_lbl.setStyleSheet("color: #e2e8f0; font-size: 13px; font-weight: 700;")
        lay.addWidget(name_lbl, 1)

        status = QLabel(("● Online") if enabled else ("● Offline"))
        status.setStyleSheet(
            f"color: {'#22c55e' if enabled else '#ef4444'};"
            f"background: {'rgba(34,197,94,0.08)' if enabled else 'rgba(239,68,68,0.08)'};"
            "border: none; border-radius: 10px; padding: 2px 9px;"
            "font-size: 11px; font-weight: 900;"
        )
        lay.addWidget(status)

        row.clicked.connect(lambda: self._select_camera_tree_item(item))
        return row

    def _toggle_department_item(self, item: QTreeWidgetItem):
        self._dept_list.setCurrentItem(item)
        item.setExpanded(not item.isExpanded())
        self._sync_department_row_state(item)
        self._refresh_camera_list_for_department()
        self._refresh_department_selection_styles()

    def _select_department_item(self, item: QTreeWidgetItem):
        self._dept_list.setCurrentItem(item)
        self._refresh_camera_list_for_department()
        self._refresh_department_selection_styles()

    def _select_camera_tree_item(self, item: QTreeWidgetItem):
        self._dept_list.setCurrentItem(item)
        cam_id = item.data(0, Qt.ItemDataRole.UserRole)
        self._refresh_camera_list_for_department(cam_id)
        self._refresh_department_selection_styles()

    def _sync_department_row_state(self, item: QTreeWidgetItem):
        if not item or item.parent() is not None:
            return
        arrow = item.data(0, Qt.ItemDataRole.UserRole + 2)
        if isinstance(arrow, QPushButton):
            self._set_button_icon(
                arrow,
                "chevron-down.svg" if item.isExpanded() else "chevron-right.svg",
                "#e2e8f0",
                18,
            )

    def _on_department_selection_changed(self):
        item = self._dept_list.currentItem() if hasattr(self, "_dept_list") else None
        cam_id = item.data(0, Qt.ItemDataRole.UserRole) if item and item.parent() is not None else None
        self._refresh_camera_list_for_department(cam_id)
        self._refresh_department_selection_styles()

    def _refresh_department_selection_styles(self):
        if not hasattr(self, "_dept_list"):
            return
        current = self._dept_list.currentItem()
        for i in range(self._dept_list.topLevelItemCount()):
            dep_item = self._dept_list.topLevelItem(i)
            dep_widget = self._dept_list.itemWidget(dep_item, 0)
            self._set_row_selected(dep_widget, dep_item is current)
            for j in range(dep_item.childCount()):
                child = dep_item.child(j)
                child_widget = self._dept_list.itemWidget(child, 0)
                self._set_row_selected(child_widget, child is current)

    @staticmethod
    def _set_row_selected(widget: QWidget | None, selected: bool):
        if not widget:
            return
        widget.setProperty("selected", "true" if selected else "false")
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _set_stat(self, card: QFrame, value: str):
        label = card.findChild(QLabel, "statValue")
        if label:
            label.setText(value)

    def _build_inline_camera_editor(self) -> QFrame:
        editor = QFrame()
        editor.setObjectName("inlineCameraEditor")
        editor.setStyleSheet("""
            QFrame#inlineCameraEditor {
                background: rgba(7,16,22,0.38);
                border: 1px solid rgba(251,146,60,0.22);
                border-radius: 8px;
            }
        """)
        lay = QGridLayout(editor)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setHorizontalSpacing(12)
        lay.setVerticalSpacing(10)
        lay.setColumnStretch(1, 1)
        lay.setColumnStretch(3, 1)

        title = QLabel("Kamera ma'lumotlarini tahrirlash")
        title.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 900;")
        lay.addWidget(title, 0, 0, 1, 4)

        self._edit_name = QLineEdit()
        self._edit_dep = QComboBox()
        self._edit_company = QLineEdit()
        self._edit_rtsp = QLineEdit()
        self._edit_enabled = QCheckBox("Faol")
        edit_input_style = """
            QLineEdit, QComboBox {
                background: rgba(2,6,23,0.72);
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 7px;
                padding: 0 10px;
                min-height: 34px;
                font-size: 12px;
            }
            QLineEdit:hover, QComboBox:hover {
                border-color: rgba(148,163,184,0.38);
                background: rgba(15,23,42,0.70);
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid rgba(251,146,60,0.74);
                background: rgba(15,23,42,0.86);
            }
            QComboBox::drop-down {
                border: none;
                width: 26px;
            }
            QComboBox QAbstractItemView {
                background: #071016;
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.18);
                selection-background-color: rgba(249,115,22,0.14);
            }
        """
        for widget in (self._edit_name, self._edit_dep, self._edit_company, self._edit_rtsp):
            widget.setFixedHeight(34)
            widget.setStyleSheet(edit_input_style)

        def add_label(text: str, row: int, col: int):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px; font-weight: 800;")
            lay.addWidget(lbl, row, col)

        add_label("Kamera", 1, 0)
        lay.addWidget(self._edit_name, 1, 1)
        add_label("Bo'lim", 1, 2)
        lay.addWidget(self._edit_dep, 1, 3)
        add_label("Company", 2, 0)
        lay.addWidget(self._edit_company, 2, 1)
        lay.addWidget(self._edit_enabled, 2, 3)
        add_label("RTSP", 3, 0)
        lay.addWidget(self._edit_rtsp, 3, 1, 1, 3)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFixedHeight(30)
        cancel_btn.setStyleSheet(self._secondary_btn_style())
        cancel_btn.clicked.connect(self._cancel_inline_camera_edit)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Saqlash")
        save_btn.setFixedHeight(30)
        save_btn.setStyleSheet(self._primary_btn_style())
        save_btn.clicked.connect(self._save_inline_camera_edit)
        btn_row.addWidget(save_btn)
        lay.addLayout(btn_row, 4, 0, 1, 4)
        return editor

    _DETAIL_ICONS = {
        "IP":      "network.svg",
        "Bo'lim":  "building.svg",
        "Company": "briefcase.svg",
        "RTSP":    "link.svg",
    }

    def _detail_row(self, key: str, value: str) -> QFrame:
        row = QFrame()
        row.setObjectName("detailRow")
        row.setStyleSheet(
            "QFrame#detailRow { background: transparent; border: none;"
            "border-bottom: 1px solid #16212c; }"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(22, 22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        icon_file = self._DETAIL_ICONS.get(key, "")
        if icon_file:
            pix = self._colored_icon(str(self._icon_dir / icon_file), "#475569", 18)
            if pix:
                icon_lbl.setPixmap(pix)

        k = QLabel(key)
        k.setFixedWidth(70)
        k.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")

        v = QLabel(value)
        v.setObjectName("detailValue")
        v.setWordWrap(True)
        v.setStyleSheet("color: #e2e8f0; font-size: 12px;")
        v.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        lay.addWidget(icon_lbl)
        lay.addWidget(k)
        lay.addWidget(v, 1)
        return row

    def _set_detail_value(self, row: QWidget, value: str):
        label = row.findChild(QLabel, "detailValue")
        if label:
            label.setText(value)

    def _set_detail_rows_visible(self, visible: bool):
        for row in (
            getattr(self, "_detail_ip", None),
            getattr(self, "_detail_dep", None),
            getattr(self, "_detail_company", None),
            getattr(self, "_detail_rtsp", None),
        ):
            if row:
                row.setVisible(visible)

    def _filter_department_list(self, text: str):
        needle = text.lower()
        for i in range(self._dept_list.topLevelItemCount()):
            dep_item = self._dept_list.topLevelItem(i)
            dep_name = str(dep_item.data(0, Qt.ItemDataRole.UserRole + 3) or "")
            dep_match = needle in dep_name.lower()
            child_match = False
            for j in range(dep_item.childCount()):
                child = dep_item.child(j)
                child_name = str(child.data(0, Qt.ItemDataRole.UserRole + 3) or "")
                visible = not needle or needle in child_name.lower() or dep_match
                child.setHidden(not visible)
                child_match = child_match or visible
            dep_item.setHidden(bool(needle) and not dep_match and not child_match)

    def _refresh_cam_list(self):
        selected_dep_id = self._selected_department_id() if hasattr(self, "_dept_list") else None
        selected_cam_id = self._selected_camera_id() if hasattr(self, "_cam_list") else None
        cameras = self.cfg.get_cameras()

        self._dept_list.clear()
        selected_tree_item = None
        for dep in self.cfg.get_departments():
            dep_id = dep.get("id")
            dep_cameras = [c for c in cameras if c.get("department_id") == dep_id]
            enabled_count = sum(1 for c in dep_cameras if c.get("enabled", True))
            name = dep.get("name", "Bo'lim")
            item = QTreeWidgetItem([""])
            item.setData(0, Qt.ItemDataRole.UserRole, dep_id)
            item.setData(0, Qt.ItemDataRole.UserRole + 3, name)
            item.setToolTip(0, f"{name}\n{len(dep_cameras)} ta kamera / {enabled_count} faol")
            item.setSizeHint(0, QSize(0, 60))
            self._dept_list.addTopLevelItem(item)
            self._dept_list.setItemWidget(
                item, 0, self._department_row_widget(item, name, len(dep_cameras), enabled_count)
            )
            if selected_dep_id == dep_id:
                selected_tree_item = item

            for cam in dep_cameras:
                cam_text = cam.get("name", "Kamera")
                child = QTreeWidgetItem([""])
                child.setData(0, Qt.ItemDataRole.UserRole, cam.get("id"))
                child.setData(0, Qt.ItemDataRole.UserRole + 3, cam_text)
                child.setToolTip(0, f"{cam_text}\n{'Online' if cam.get('enabled', True) else 'Offline'}")
                child.setSizeHint(0, QSize(0, 44))
                item.addChild(child)
                self._dept_list.setItemWidget(child, 0, self._camera_tree_row_widget(child, cam))
                if selected_cam_id == cam.get("id"):
                    selected_tree_item = child
                    item.setExpanded(True)

        count         = len(cameras)
        enabled_count = sum(1 for c in cameras if c.get("enabled", True))
        dep_count     = len(self.cfg.get_departments()) if self.cfg else 0
        self._cam_count_lbl.setText(f"{count} ta kamera  ({enabled_count} ta faol)")
        self._settings_summary.setText(f"{enabled_count}/{count} faol kamera")
        self._set_stat(self._total_stat,   str(count))
        self._set_stat(self._enabled_stat, str(enabled_count))
        self._set_stat(self._dept_stat,    str(dep_count))

        if selected_tree_item is not None:
            self._dept_list.setCurrentItem(selected_tree_item)
        elif self._dept_list.topLevelItemCount():
            self._dept_list.setCurrentItem(self._dept_list.topLevelItem(0))
        for i in range(self._dept_list.topLevelItemCount()):
            self._sync_department_row_state(self._dept_list.topLevelItem(i))
        self._refresh_camera_list_for_department(selected_cam_id)

    def _on_department_tree_clicked(self, item: QTreeWidgetItem | None, column: int):
        if item is None:
            return
        cam_id = item.data(0, Qt.ItemDataRole.UserRole) if item.parent() is not None else None
        self._refresh_camera_list_for_department(cam_id)
        self._refresh_department_selection_styles()

    def _refresh_camera_list_for_department(self, preferred_cam_id: int | None = None):
        if not hasattr(self, "_cam_list"):
            return
        dep_id = self._selected_department_id()
        cameras = [
            cam for cam in self.cfg.get_cameras()
            if dep_id is None or cam.get("department_id") == dep_id
        ]
        current_cam_id = self._selected_camera_id()
        target_cam = None
        if preferred_cam_id is not None:
            target_cam = next((cam for cam in cameras if cam.get("id") == preferred_cam_id), None)
        if target_cam is None and current_cam_id is not None:
            target_cam = next((cam for cam in cameras if cam.get("id") == current_cam_id), None)
        if target_cam is None and cameras:
            target_cam = cameras[0]

        self._cam_list.clear()
        for cam in ([target_cam] if target_cam else []):
            enabled = cam.get("enabled", True)
            status  = "Faol" if enabled else "O'chirilgan"
            name    = cam.get("name", "Kamera")
            ip      = self._camera_ip(cam.get("rtsp_url", ""))
            text = f"{name}\n{status}  |  {ip}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, cam.get("id"))
            item.setSizeHint(QSize(0, 48))
            self._cam_list.addItem(item)
            self._cam_list.setCurrentItem(item)
        self._update_camera_preview()

    @staticmethod
    def _camera_ip(rtsp: str) -> str:
        if "@" in rtsp:
            try:
                return rtsp.split("@", 1)[1].split(":", 1)[0]
            except Exception:
                return rtsp[:32]
        if rtsp.startswith("rtsp://"):
            return rtsp[7:].split("/", 1)[0].split(":", 1)[0]
        return rtsp[:32] or "--"

    def _update_camera_preview(self):
        cam_id = self._selected_camera_id()
        cam    = self.cfg.get_camera_by_id(cam_id) if cam_id is not None else None
        if not cam or not hasattr(self, "_detail_name"):
            if hasattr(self, "_detail_name"):
                self._detail_name.setText("Kamera tanlang")
                self._detail_status.setText("")
                self._set_detail_value(self._detail_ip, "--")
                self._set_detail_value(self._detail_dep, "--")
                self._set_detail_value(self._detail_company, "--")
                self._set_detail_value(self._detail_rtsp, "--")
                if hasattr(self, "_inline_edit_panel"):
                    self._inline_edit_panel.hide()
                    self._set_detail_rows_visible(True)
            return
        enabled = cam.get("enabled", True)
        dep     = self.cfg.get_department_by_id(cam.get("department_id")) if self.cfg else None
        self._detail_name.setText(cam.get("name", "Kamera"))
        self._detail_status.setText("Faol kamera" if enabled else "O'chirilgan")
        self._detail_status.setStyleSheet(
            f"color: {'#34d399' if enabled else C('text_muted')};"
            f"background: {'rgba(52,211,153,0.12)' if enabled else 'rgba(100,116,139,0.10)'};"
            "border: none;"
            "border-radius: 8px; padding: 3px 10px; font-size: 11px; font-weight: 800;"
        )
        self._set_detail_value(self._detail_ip,      self._camera_ip(cam.get("rtsp_url", "")))
        self._set_detail_value(self._detail_dep,     dep.get("name", "Bo'limsiz") if dep else "Bo'limsiz")
        self._set_detail_value(self._detail_company, cam.get("company_id", "--") or "--")
        self._set_detail_value(self._detail_rtsp,    cam.get("rtsp_url", "--") or "--")

    def _show_inline_camera_editor(self, cam: dict):
        self._edit_name.setText(cam.get("name", ""))
        self._edit_company.setText(cam.get("company_id", ""))
        self._edit_rtsp.setText(cam.get("rtsp_url", ""))
        self._edit_enabled.setChecked(cam.get("enabled", True))

        self._edit_dep.clear()
        for dep in self.cfg.get_departments():
            self._edit_dep.addItem(dep.get("name", "Bo'lim"), dep.get("id"))
        idx = self._edit_dep.findData(cam.get("department_id"))
        if idx >= 0:
            self._edit_dep.setCurrentIndex(idx)

        self._inline_edit_panel.show()
        self._set_detail_rows_visible(False)
        self._edit_name.setFocus()

    def _cancel_inline_camera_edit(self):
        self._inline_edit_panel.hide()
        self._set_detail_rows_visible(True)

    def _save_inline_camera_edit(self):
        cam_id = self._selected_camera_id()
        if cam_id is None:
            return
        name = self._edit_name.text().strip()
        rtsp = self._edit_rtsp.text().strip()
        if not name:
            QMessageBox.warning(self, "Xatolik", "Kamera nomi kiritilishi shart.")
            return
        if not rtsp:
            QMessageBox.warning(self, "Xatolik", "RTSP URL kiritilishi shart.")
            return
        self.cfg.update_camera(
            cam_id,
            name=name,
            rtsp_url=rtsp,
            company_id=self._edit_company.text().strip(),
            department_id=self._edit_dep.currentData(),
            enabled=self._edit_enabled.isChecked(),
        )
        self._inline_edit_panel.hide()
        self._set_detail_rows_visible(True)
        self._refresh_cam_list()

    def _selected_camera_id(self) -> int | None:
        item = self._cam_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_department_id(self) -> int | None:
        item = self._dept_list.currentItem() if hasattr(self, "_dept_list") else None
        if item and item.parent() is not None:
            item = item.parent()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def _add_department(self):
        name, ok = QInputDialog.getText(self, "Yangi bo'lim", "Bo'lim nomi:")
        if not ok:
            return
        try:
            self.cfg.add_department(name)
            self._refresh_cam_list()
        except ValueError as e:
            QMessageBox.warning(self, "Xatolik", str(e))

    def _add_camera(self):
        cameras = self.cfg.get_cameras()
        if len(cameras) >= 10:
            QMessageBox.warning(self, "Limit", "Maksimal 10 ta kamera qo'shish mumkin.")
            return
        departments = self.cfg.get_departments()
        if not departments:
            QMessageBox.information(self, "Bo'lim kerak",
                                    "Avval bo'lim yarating, keyin kamera qo'shing.")
            return
        dlg = CameraEditDialog(departments=departments, parent=self)
        dep_id = self._selected_department_id()
        if dep_id is not None:
            idx = dlg._department_combo.findData(dep_id)
            if idx >= 0:
                dlg._department_combo.setCurrentIndex(idx)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cam = dlg.get_camera()
            try:
                self.cfg.add_camera(
                    name=cam["name"],
                    rtsp_url=cam["rtsp_url"],
                    company_id=cam.get("company_id", ""),
                    enabled=cam.get("enabled", True),
                    department_id=cam.get("department_id"),
                )
            except ValueError as e:
                QMessageBox.warning(self, "Xatolik", str(e))
            self._refresh_cam_list()

    def _edit_camera(self):
        cam_id = self._selected_camera_id()
        if cam_id is None:
            QMessageBox.information(self, "Tanlang", "Tahrirlash uchun kamerani tanlang.")
            return
        cam = self.cfg.get_camera_by_id(cam_id)
        if not cam:
            return
        self._show_inline_camera_editor(cam)

    def _delete_camera(self):
        cam_id = self._selected_camera_id()
        if cam_id is None:
            QMessageBox.information(self, "Tanlang", "O'chirish uchun kamerani tanlang.")
            return
        cam  = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"ID:{cam_id}") if cam else f"ID:{cam_id}"
        reply = QMessageBox.question(
            self, "O'chirish tasdiqi",
            f'"{name}" kamerasini o\'chirmoqchimisiz?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if not self.cfg.remove_camera(cam_id):
                QMessageBox.warning(self, "Xatolik", "Kamida 1 ta kamera bo'lishi shart.")
            else:
                self._refresh_cam_list()

    # ── Model page ────────────────────────────────────────────────────────

    def _make_model_page(self) -> QWidget:
        page, lay = self._scroll_page()
        lay.addLayout(self._page_header("Model", "YOLO AI model sozlamalari"))

        card = self._panel()
        g = QVBoxLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setSpacing(12)

        self._ai_enabled_check = QCheckBox("AI modelni yoqish")
        g.addWidget(self._ai_enabled_check)

        g.addWidget(self._form_label("Model fayli (.pt):"))
        h = QHBoxLayout()
        self._model_edit = QLineEdit()
        h.addWidget(self._model_edit, 1)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(38)
        browse_btn.setStyleSheet(self._secondary_btn_style())
        browse_btn.setText("")
        self._set_button_icon(browse_btn, "folder.svg", "#cbd5e1", 16)
        browse_btn.clicked.connect(self._browse_model)
        h.addWidget(browse_btn)
        g.addLayout(h)

        self._test_model_btn = QPushButton("Model tekshirish")
        self._test_model_btn.setFixedHeight(34)
        self._test_model_btn.setStyleSheet(self._secondary_btn_style())
        self._test_model_btn.clicked.connect(self._test_model)
        g.addWidget(self._test_model_btn)
        self._test_model_result = QLabel("")
        self._test_model_result.setWordWrap(True)
        g.addWidget(self._test_model_result)

        g.addWidget(self._hsep())

        conf_row = QHBoxLayout()
        g.addWidget(self._form_label("Ishonch chegarasi:"))
        self._conf_spin = QDoubleSpinBox()
        self._conf_spin.setRange(0.1, 0.99)
        self._conf_spin.setSingleStep(0.05)
        self._conf_spin.setDecimals(2)
        self._conf_spin.setValue(0.6)
        self._conf_spin.setFixedWidth(90)
        conf_row.addWidget(self._conf_spin)
        conf_row.addStretch()
        g.addLayout(conf_row)

        g.addWidget(self._form_label("YOLO imgsz:"))
        imgsz_row = QHBoxLayout()
        self._imgsz_combo = QComboBox()
        self._imgsz_combo.addItems(["416", "640", "1024", "1280"])
        self._imgsz_combo.setCurrentText("640")
        self._imgsz_combo.setFixedWidth(110)
        imgsz_row.addWidget(self._imgsz_combo)
        imgsz_row.addStretch()
        g.addLayout(imgsz_row)

        self._gpu_check  = QCheckBox("GPU ishlatish (CUDA)")
        self._half_check = QCheckBox("Half precision (FP16)")
        g.addWidget(self._gpu_check)
        g.addWidget(self._half_check)

        g.addWidget(self._form_label("Har N ta frameni qayta ishlash:"))
        pn_row = QHBoxLayout()
        self._proc_n_spin = QSpinBox()
        self._proc_n_spin.setRange(1, 5)
        self._proc_n_spin.setValue(1)
        self._proc_n_spin.setFixedWidth(70)
        pn_row.addWidget(self._proc_n_spin)
        pn_row.addStretch()
        g.addLayout(pn_row)

        g.addWidget(self._form_label("AI maksimal FPS (kamera boshiga):"))
        ai_fps_row = QHBoxLayout()
        self._ai_fps_spin = QSpinBox()
        self._ai_fps_spin.setRange(1, 30)
        self._ai_fps_spin.setValue(5)
        self._ai_fps_spin.setFixedWidth(70)
        self._ai_fps_spin.setToolTip(
            "Har bir kamera uchun sekundiga necha marta AI inference ishlatiladi.\n"
            "Kamaytirish CPU/GPU yukini sezilarli kamaytiradi."
        )
        ai_fps_row.addWidget(self._ai_fps_spin)
        ai_fps_note = QLabel("past = kamroq CPU yuki")
        ai_fps_note.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        ai_fps_row.addWidget(ai_fps_note)
        ai_fps_row.addStretch()
        g.addLayout(ai_fps_row)

        lay.addWidget(card)
        lay.addStretch()
        return page

    # ── Telegram page ─────────────────────────────────────────────────────

    def _make_faceid_page(self) -> QWidget:
        page, lay = self._scroll_page()
        lay.addLayout(self._page_header("FaceID", "Hodimlarni yuz orqali tanish va access roster"))

        card = self._panel()
        g = QVBoxLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setSpacing(12)

        self._faceid_enabled = QCheckBox("FaceID ni yoqish")
        self._access_roster_enabled = QCheckBox("Access roster alertlarini yoqish")
        g.addWidget(self._faceid_enabled)
        g.addWidget(self._access_roster_enabled)

        g.addWidget(self._form_label("Match threshold:"))
        row = QHBoxLayout()
        self._faceid_threshold = QDoubleSpinBox()
        self._faceid_threshold.setRange(0.40, 0.95)
        self._faceid_threshold.setDecimals(2)
        self._faceid_threshold.setSingleStep(0.02)
        self._faceid_threshold.setFixedWidth(90)
        row.addWidget(self._faceid_threshold)
        note = QLabel("yuqori = kamroq false match")
        note.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        row.addWidget(note)
        row.addStretch()
        g.addLayout(row)

        g.addWidget(self._hsep())
        roster = QLabel(
            "Hodim rasmlari Users sahifasida qo'shiladi. Startup paytida "
            "yuz embeddinglari lokal DBga tayyorlanadi."
        )
        roster.setWordWrap(True)
        roster.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        g.addWidget(roster)

        lay.addWidget(card)
        lay.addStretch()
        return page

    def _make_telegram_page(self) -> QWidget:
        page, lay = self._scroll_page()
        lay.addLayout(self._page_header("Notifications", "Telegram xabarnomalari va optional sync navbati"))

        card = self._panel()
        g = QVBoxLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setSpacing(12)

        self._tg_enabled = QCheckBox("Telegram xabarnomani yoqish")
        g.addWidget(self._tg_enabled)

        g.addWidget(self._form_label("Bot Token:"))
        self._tg_token = QLineEdit()
        self._tg_token.setPlaceholderText("1234567890:AAH...")
        self._tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        g.addWidget(self._tg_token)

        show_token = QCheckBox("Tokenni ko'rsatish")
        show_token.stateChanged.connect(
            lambda s: self._tg_token.setEchoMode(
                QLineEdit.EchoMode.Normal if s else QLineEdit.EchoMode.Password
            )
        )
        g.addWidget(show_token)

        g.addWidget(self._form_label("Chat ID lar (vergul bilan):"))
        self._tg_chat_ids = QLineEdit()
        self._tg_chat_ids.setPlaceholderText("123456789, 987654321")
        g.addWidget(self._tg_chat_ids)

        g.addWidget(self._hsep())

        test_btn = QPushButton("Telegram ulanishni tekshirish")
        test_btn.setFixedHeight(36)
        test_btn.setStyleSheet(self._secondary_btn_style())
        test_btn.clicked.connect(self._test_telegram)
        g.addWidget(test_btn)

        self._tg_result = QLabel("")
        self._tg_result.setWordWrap(True)
        g.addWidget(self._tg_result)

        lay.addWidget(card)
        lay.addStretch()
        return page

    # ── Backend page ──────────────────────────────────────────────────────

    def _make_backend_page(self) -> QWidget:
        page, lay = self._scroll_page()
        lay.addLayout(self._page_header("Backend Sync", "Optional backend sync sozlamalari"))

        card = self._panel()
        g = QVBoxLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setSpacing(12)

        self._be_enabled = QCheckBox("Backend API ni yoqish")
        g.addWidget(self._be_enabled)

        g.addWidget(self._form_label("API URL:"))
        self._be_url = QLineEdit()
        self._be_url.setPlaceholderText("https://example.com/api/camera/create")
        g.addWidget(self._be_url)

        g.addWidget(self._form_label("Login:"))
        self._be_login = QLineEdit()
        g.addWidget(self._be_login)

        g.addWidget(self._form_label("Parol:"))
        self._be_pass = QLineEdit()
        self._be_pass.setEchoMode(QLineEdit.EchoMode.Password)
        g.addWidget(self._be_pass)

        g.addWidget(self._hsep())

        note = QLabel(
            "ℹ️  Company ID har bir kamera uchun alohida "
            "Kameralar bo'limida sozlanadi."
        )
        note.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        note.setWordWrap(True)
        g.addWidget(note)

        lay.addWidget(card)
        lay.addStretch()
        return page

    # ── Storage page ──────────────────────────────────────────────────────

    def _make_storage_page(self) -> QWidget:
        page, lay = self._scroll_page()
        lay.addLayout(self._page_header("Saqlash", "Fayl saqlash va arxivlash sozlamalari"))

        card = self._panel()
        g = QVBoxLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setSpacing(12)

        self._save_check = QCheckBox("Buzilish rasmlarini saqlash")
        g.addWidget(self._save_check)

        g.addWidget(self._form_label("Rasmlar papkasi:"))
        h = QHBoxLayout()
        self._viol_dir_edit = QLineEdit()
        self._viol_dir_edit.setPlaceholderText("violations/  (bo'sh = SmartGUI/violations/)")
        h.addWidget(self._viol_dir_edit, 1)
        browse_dir = QPushButton("...")
        browse_dir.setFixedWidth(38)
        browse_dir.setStyleSheet(self._secondary_btn_style())
        browse_dir.setText("")
        self._set_button_icon(browse_dir, "folder.svg", "#cbd5e1", 16)
        browse_dir.clicked.connect(self._browse_dir)
        h.addWidget(browse_dir)
        g.addLayout(h)

        g.addWidget(self._hsep())

        g.addWidget(self._form_label("Fayllarni saqlash muddati (kun):"))
        days_row = QHBoxLayout()
        self._keep_days_spin = QSpinBox()
        self._keep_days_spin.setRange(1, 365)
        self._keep_days_spin.setValue(7)
        self._keep_days_spin.setFixedWidth(80)
        days_row.addWidget(self._keep_days_spin)
        days_row.addStretch()
        g.addLayout(days_row)

        self._cleanup_files_check = QCheckBox("Eski image fayllarni ham avtomatik tozalash")
        g.addWidget(self._cleanup_files_check)

        lay.addWidget(card)
        lay.addStretch()
        return page

    def _make_performance_page(self) -> QWidget:
        page, lay = self._scroll_page()
        lay.addLayout(self._page_header("Performance", "Kamera va AI inference yuklamasi"))

        card = self._panel()
        g = QVBoxLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setSpacing(12)

        g.addWidget(self._form_label("Video FPS limit:"))
        self._video_fps_spin = QSpinBox()
        self._video_fps_spin.setRange(1, 60)
        self._video_fps_spin.setFixedWidth(80)
        g.addWidget(self._video_fps_spin)

        g.addWidget(self._form_label("AI FPS limit (kamera boshiga):"))
        self._perf_ai_fps_spin = QSpinBox()
        self._perf_ai_fps_spin.setRange(1, 30)
        self._perf_ai_fps_spin.setFixedWidth(80)
        g.addWidget(self._perf_ai_fps_spin)

        g.addWidget(self._form_label("Inference batch size:"))
        self._batch_spin = QSpinBox()
        self._batch_spin.setRange(1, 8)
        self._batch_spin.setFixedWidth(80)
        g.addWidget(self._batch_spin)

        g.addWidget(self._form_label("Cameras per model:"))
        self._cams_per_model_spin = QSpinBox()
        self._cams_per_model_spin.setRange(1, 8)
        self._cams_per_model_spin.setFixedWidth(80)
        g.addWidget(self._cams_per_model_spin)

        g.addWidget(self._form_label("Violation save queue size:"))
        self._queue_size_spin = QSpinBox()
        self._queue_size_spin.setRange(8, 512)
        self._queue_size_spin.setFixedWidth(90)
        g.addWidget(self._queue_size_spin)

        g.addWidget(self._hsep())
        tracking_title = QLabel("Tracking stability")
        tracking_title.setStyleSheet(f"color: {C('accent_light')}; font-size: 13px; font-weight: 900;")
        g.addWidget(tracking_title)

        g.addWidget(self._form_label("Tracking strictness:"))
        self._tracking_preset_combo = QComboBox()
        self._tracking_preset_combo.addItems(["Stable", "Balanced", "Fast"])
        self._tracking_preset_combo.setFixedWidth(130)
        g.addWidget(self._tracking_preset_combo)

        g.addWidget(self._form_label("ID hold frames:"))
        self._tracker_age_spin = QSpinBox()
        self._tracker_age_spin.setRange(30, 400)
        self._tracker_age_spin.setFixedWidth(90)
        g.addWidget(self._tracker_age_spin)

        g.addWidget(self._form_label("Minimum hits for stable ID:"))
        self._tracker_hits_spin = QSpinBox()
        self._tracker_hits_spin.setRange(1, 10)
        self._tracker_hits_spin.setFixedWidth(90)
        g.addWidget(self._tracker_hits_spin)

        g.addWidget(self._form_label("Helmet vote window / threshold:"))
        helmet_row = QHBoxLayout()
        self._helmet_window_spin = QSpinBox()
        self._helmet_window_spin.setRange(3, 20)
        self._helmet_window_spin.setFixedWidth(80)
        helmet_row.addWidget(self._helmet_window_spin)
        self._helmet_threshold_spin = QSpinBox()
        self._helmet_threshold_spin.setRange(1, 20)
        self._helmet_threshold_spin.setFixedWidth(80)
        helmet_row.addWidget(self._helmet_threshold_spin)
        note = QLabel("ko'pchilik vote = kamroq adashish")
        note.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        helmet_row.addWidget(note)
        helmet_row.addStretch()
        g.addLayout(helmet_row)

        lay.addWidget(card)
        lay.addStretch()
        return page

    def _make_diagnostics_page(self) -> QWidget:
        page, lay = self._scroll_page()
        lay.addLayout(self._page_header("Diagnostics", "Startup checklar va production signal"))

        card = self._panel()
        g = QVBoxLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setSpacing(12)

        self._diag_summary = QLabel("")
        self._diag_summary.setWordWrap(True)
        self._diag_summary.setStyleSheet(f"color: {C('text_secondary')}; font-size: 12px;")
        g.addWidget(self._diag_summary)

        refresh = QPushButton("Diagnostics yangilash")
        refresh.setFixedHeight(36)
        refresh.setStyleSheet(self._secondary_btn_style())
        refresh.clicked.connect(self._refresh_diagnostics)
        g.addWidget(refresh)

        lay.addWidget(card)
        lay.addStretch()
        return page

    # ── Form helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _form_label(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f"color: {C('text_secondary')}; font-size: 12px; font-weight: 700;")
        return l

    @staticmethod
    def _hsep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("background: #1e293b; border: none; max-height: 1px;")
        return f

    # ── Load / Save ───────────────────────────────────────────────────────

    def _load_values(self):
        self._refresh_cam_list()

        c = self.cfg
        self._ai_enabled_check.setChecked(bool(c.get("ai_model_enabled", False)))
        self._model_edit.setText(c.get("model_path", ""))
        self._conf_spin.setValue(float(c.get("confidence", 0.6)))
        imgsz = str(c.get("yolo_imgsz", 640))
        idx = self._imgsz_combo.findText(imgsz)
        self._imgsz_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self._gpu_check.setChecked(bool(c.get("use_gpu", True)))
        self._half_check.setChecked(bool(c.get("half_precision", True)))
        self._proc_n_spin.setValue(int(c.get("process_every_n", 1)))
        self._ai_fps_spin.setValue(int(c.get("ai_fps_limit", 5)))
        self._faceid_enabled.setChecked(bool(c.get("faceid_enabled", False)))
        self._access_roster_enabled.setChecked(bool(c.get("access_roster_enabled", False)))
        self._faceid_threshold.setValue(float(c.get("faceid_threshold", 0.72)))

        self._tg_enabled.setChecked(bool(c.get("telegram_enabled", True)))
        self._tg_token.setText(c.get("telegram_token", ""))
        self._tg_chat_ids.setText(", ".join(c.telegram_chat_ids))

        self._be_enabled.setChecked(bool(c.get("backend_enabled", False)))
        self._be_url.setText(c.get("backend_url", ""))
        self._be_login.setText(c.get("backend_login", ""))
        self._be_pass.setText(c.get("backend_password", ""))

        self._save_check.setChecked(bool(c.get("save_violations", True)))
        self._viol_dir_edit.setText(str(c.get("violations_dir", "")))
        self._keep_days_spin.setValue(int(c.get("keep_files_days", 7)))
        self._cleanup_files_check.setChecked(bool(c.get("cleanup_files", False)))
        self._video_fps_spin.setValue(int(c.get("video_fps_limit", 25)))
        self._perf_ai_fps_spin.setValue(int(c.get("ai_fps_limit", 10)))
        self._batch_spin.setValue(int(c.get("inference_batch_size", 3)))
        self._cams_per_model_spin.setValue(int(c.get("cameras_per_model", 3)))
        self._queue_size_spin.setValue(int(c.get("violation_save_queue_size", 64)))
        preset = str(c.get("tracking_strictness", "balanced")).title()
        idx = self._tracking_preset_combo.findText(preset)
        self._tracking_preset_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self._tracker_age_spin.setValue(int(c.get("tracker_max_age", 150)))
        self._tracker_hits_spin.setValue(int(c.get("tracker_min_hits", 3)))
        self._helmet_window_spin.setValue(int(c.get("helmet_status_window", 8)))
        self._helmet_threshold_spin.setValue(int(c.get("helmet_status_threshold", 5)))
        self._refresh_diagnostics()

    def _save(self):
        ids_raw  = self._tg_chat_ids.text()
        chat_ids = [x.strip() for x in ids_raw.split(",") if x.strip()]

        self.cfg.update({
            "ai_model_enabled":  self._ai_enabled_check.isChecked(),
            "model_path":        self._model_edit.text().strip(),
            "confidence":        self._conf_spin.value(),
            "yolo_imgsz":        int(self._imgsz_combo.currentText()),
            "use_gpu":           self._gpu_check.isChecked(),
            "half_precision":    self._half_check.isChecked(),
            "process_every_n":   self._proc_n_spin.value(),
            "ai_fps_limit":      self._perf_ai_fps_spin.value(),
            "faceid_enabled":    self._faceid_enabled.isChecked(),
            "access_roster_enabled": self._access_roster_enabled.isChecked(),
            "faceid_threshold":  self._faceid_threshold.value(),
            "telegram_enabled":  self._tg_enabled.isChecked(),
            "telegram_token":    self._tg_token.text().strip(),
            "telegram_chat_ids": chat_ids,
            "backend_enabled":   self._be_enabled.isChecked(),
            "backend_url":       self._be_url.text().strip(),
            "backend_login":     self._be_login.text().strip(),
            "backend_password":  self._be_pass.text().strip(),
            "save_violations":   self._save_check.isChecked(),
            "violations_dir":    self._viol_dir_edit.text().strip(),
            "keep_files_days":   self._keep_days_spin.value(),
            "cleanup_files":     self._cleanup_files_check.isChecked(),
            "video_fps_limit":   self._video_fps_spin.value(),
            "inference_batch_size": self._batch_spin.value(),
            "cameras_per_model": self._cams_per_model_spin.value(),
            "violation_save_queue_size": self._queue_size_spin.value(),
            "tracking_strictness": self._tracking_preset_combo.currentText().lower(),
            "tracker_max_age": self._tracker_age_spin.value(),
            "tracker_min_hits": self._tracker_hits_spin.value(),
            "helmet_status_window": self._helmet_window_spin.value(),
            "helmet_status_threshold": min(self._helmet_threshold_spin.value(), self._helmet_window_spin.value()),
        })
        self.cfg.save()
        if hasattr(self, "_restart_indicator"):
            self._restart_indicator.setText("Saved | restart cameras")
        self.settings_saved.emit()
        QMessageBox.information(
            self, "Saqlandi",
            "Sozlamalar saqlandi.\n"
            "O'zgarishlar kuchga kirishi uchun kameralar qayta ishga tushiriladi."
        )

    # ── Utility actions ───────────────────────────────────────────────────

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Model tanlash", "", "PyTorch Model (*.pt);;Barcha fayllar (*)"
        )
        if path:
            self._model_edit.setText(path)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Rasmlar papkasi")
        if path:
            self._viol_dir_edit.setText(path)

    def _test_model(self):
        self._test_model_result.setText("Model yuklanishi tekshirilmoqda...")
        self._test_model_result.setStyleSheet(f"color: {C('text_muted')};")
        t = _TestThread("model", {"path": self._model_edit.text().strip()})
        t.result.connect(self._on_model_test_result)
        self._test_thread = t
        t.start()

    def _on_model_test_result(self, ok: bool, msg: str):
        color = C("success") if ok else C("danger")
        self._test_model_result.setText(("✓ " if ok else "✗ ") + msg)
        self._test_model_result.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _test_telegram(self):
        self._tg_result.setText("Ulanish tekshirilmoqda...")
        self._tg_result.setStyleSheet(f"color: {C('text_muted')};")
        ids_raw  = self._tg_chat_ids.text()
        chat_ids = [x.strip() for x in ids_raw.split(",") if x.strip()]
        t = _TestThread("telegram", {
            "token":    self._tg_token.text().strip(),
            "chat_ids": chat_ids,
        })
        t.result.connect(self._on_tg_test_result)
        self._test_thread = t
        t.start()

    def _on_tg_test_result(self, ok: bool, msg: str):
        color = C("success") if ok else C("danger")
        self._tg_result.setText(("✓ " if ok else "✗ ") + msg)
        self._tg_result.setStyleSheet(f"color: {color}; font-size: 12px;")


    def _refresh_diagnostics(self):
        if not hasattr(self, "_diag_summary"):
            return
        cameras = self.cfg.get_cameras()
        users = self.cfg.get_users()
        active_users = [u for u in users if u.get("active", True)]
        photo_users = [
            u for u in active_users
            if u.get("photo_path") and Path(u.get("photo_path")).exists()
        ]
        lines = [
            f"Kameralar: {len(cameras)} total / {len(self.cfg.get_enabled_cameras())} enabled",
            f"Employees: {len(active_users)} active / {len(photo_users)} with valid photos",
            f"AI: {'enabled' if self.cfg.get('ai_model_enabled', False) else 'disabled'} | imgsz {self.cfg.get('yolo_imgsz', 640)}",
            f"FaceID: {'enabled' if self.cfg.get('faceid_enabled', False) else 'disabled'} | access roster {'on' if self.cfg.get('access_roster_enabled', False) else 'off'}",
            f"Notifications: Telegram {'on' if self.cfg.get('telegram_enabled', False) else 'off'}, Backend {'on' if self.cfg.get('backend_enabled', False) else 'off'}",
        ]
        self._diag_summary.setText("\n".join(lines))


# Backwards-compat alias
SettingsDialog = SettingsPage
