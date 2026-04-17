"""
AboutPage — tizim haqida ma'lumot sahifasi.
"""

import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QScrollArea, QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from app.ui.theme import C

APP_VERSION = "1.0.0"
APP_NAME    = "SmartHelmet GUI"
DEVELOPER   = "SmartHelmet Team"


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setProperty("card", True)
    return f


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    font = QFont()
    font.setPointSize(12)
    font.setBold(True)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color: {C('accent')}; background: transparent; margin-bottom: 4px;")
    return lbl


def _info_row(label: str, value: str, val_color: str = None) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    l = QLabel(label + ":")
    l.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
    l.setFixedWidth(180)
    v = QLabel(value)
    v.setStyleSheet(
        f"color: {val_color or C('text_primary')}; font-size: 12px; font-weight: bold;"
    )
    v.setWordWrap(True)
    row.addWidget(l)
    row.addWidget(v, 1)
    return row


class AboutPage(QWidget):
    """Haqida sahifasi."""

    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        c_layout  = QVBoxLayout(container)
        c_layout.setSpacing(12)
        c_layout.setContentsMargins(0, 0, 4, 0)

        # ── Sarlavha ──────────────────────────────────────────────────────
        header = _card()
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(20, 18, 20, 18)
        h_layout.setSpacing(4)

        name_lbl = QLabel(APP_NAME)
        name_font = QFont()
        name_font.setPointSize(22)
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        name_lbl.setStyleSheet(f"color: {C('accent')}; background: transparent;")
        h_layout.addWidget(name_lbl)

        desc_lbl = QLabel(
            "Zavod hududidagi xavfsizlik shlemini kiymaganlarni real vaqtda\n"
            "aniqlash va xabarnoma yuborish tizimi."
        )
        desc_lbl.setStyleSheet(f"color: {C('text_secondary')}; font-size: 13px; background: transparent;")
        desc_lbl.setWordWrap(True)
        h_layout.addWidget(desc_lbl)

        ver_lbl = QLabel(f"Versiya: {APP_VERSION}  ·  {DEVELOPER}")
        ver_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px; background: transparent;")
        h_layout.addWidget(ver_lbl)

        c_layout.addWidget(header)

        # ── Tizim ma'lumoti ───────────────────────────────────────────────
        sys_card = _card()
        s_layout = QVBoxLayout(sys_card)
        s_layout.setContentsMargins(16, 14, 16, 14)
        s_layout.setSpacing(8)
        s_layout.addWidget(_section_title("Tizim ma'lumoti"))

        python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        s_layout.addLayout(_info_row("Python", python_ver))

        try:
            import torch
            cuda_ok = torch.cuda.is_available()
            gpu_name = torch.cuda.get_device_name(0) if cuda_ok else "CUDA topilmadi"
            s_layout.addLayout(_info_row("PyTorch", torch.__version__))
            s_layout.addLayout(_info_row(
                "GPU", gpu_name,
                C("success") if cuda_ok else C("warning")
            ))
        except Exception:
            s_layout.addLayout(_info_row("PyTorch", "O'rnatilmagan", C("danger")))

        try:
            from PyQt6.QtCore import PYQT_VERSION_STR
            s_layout.addLayout(_info_row("PyQt6", PYQT_VERSION_STR))
        except Exception:
            pass

        try:
            import cv2
            s_layout.addLayout(_info_row("OpenCV", cv2.__version__))
        except ImportError:
            s_layout.addLayout(_info_row("OpenCV", "O'rnatilmagan", C("danger")))

        try:
            import ultralytics
            s_layout.addLayout(_info_row("Ultralytics", ultralytics.__version__))
        except Exception:
            s_layout.addLayout(_info_row("Ultralytics", "O'rnatilmagan", C("danger")))

        # SmartHelmet yo'li
        if self.cfg:
            sh = self.cfg.smarthelmet_path
            sh_ok = Path(sh).exists()
            s_layout.addLayout(_info_row(
                "SmartHelmet",
                sh if sh_ok else f"{sh} (topilmadi)",
                C("success") if sh_ok else C("danger")
            ))

            model = self.cfg.model_path
            model_ok = os.path.exists(model)
            s_layout.addLayout(_info_row(
                "Model",
                Path(model).name if model_ok else "Topilmadi",
                C("success") if model_ok else C("danger")
            ))

        c_layout.addWidget(sys_card)

        # ── Detection ma'lumoti ───────────────────────────────────────────
        det_card = _card()
        d_layout = QVBoxLayout(det_card)
        d_layout.setContentsMargins(16, 14, 16, 14)
        d_layout.setSpacing(8)
        d_layout.addWidget(_section_title("Detection arxitekturasi"))

        for lbl, val in [
            ("Model",         "YOLOv8 (Ultralytics)"),
            ("Tracker",       "BoT-SORT"),
            ("Klasslar",      "PERSON (0) · HEAD (1) · NO_HEAD (2)"),
            ("Frame pipe",    "FFmpeg → BGR24 pipe → YOLO"),
            ("HW decode",     "Intel QSV → D3D11VA → Software fallback"),
            ("Xabarnoma",     "Telegram Bot API"),
        ]:
            d_layout.addLayout(_info_row(lbl, val))

        c_layout.addWidget(det_card)

        # ── Klaviatura yorliqlari ─────────────────────────────────────────
        keys_card = _card()
        k_layout = QVBoxLayout(keys_card)
        k_layout.setContentsMargins(16, 14, 16, 14)
        k_layout.setSpacing(8)
        k_layout.addWidget(_section_title("Klaviatura yorliqlari"))

        for key, desc in [
            ("Ctrl+1",   "Dashboard sahifasi"),
            ("Ctrl+2",   "Buzilishlar sahifasi"),
            ("Ctrl+3",   "Analitika sahifasi"),
            ("Ctrl+,",   "Sozlamalar"),
            ("F5",       "Yangilash"),
            ("Space",    "Pauza / Davom ettirish"),
            ("Ctrl+S",   "Screenshot saqlash"),
            ("Ctrl+Q",   "Dasturdan chiqish"),
        ]:
            row = _info_row(key, desc)
            k_layout.addLayout(row)

        c_layout.addWidget(keys_card)

        # ── Litsenziya ────────────────────────────────────────────────────
        lic_card = _card()
        l_layout = QVBoxLayout(lic_card)
        l_layout.setContentsMargins(16, 14, 16, 14)
        l_layout.setSpacing(6)
        l_layout.addWidget(_section_title("Litsenziya"))
        lic_text = QLabel(
            "Bu dastur MIT litsenziyasi ostida tarqatiladi.\n"
            "SmartHelmet Detection System © 2024–2026\n\n"
            "Foydalanilgan kutubxonalar: PyQt6, OpenCV, Ultralytics YOLOv8,\n"
            "PyTorch, NumPy, Requests, SQLite3."
        )
        lic_text.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px; background: transparent;")
        lic_text.setWordWrap(True)
        l_layout.addWidget(lic_text)
        c_layout.addWidget(lic_card)

        c_layout.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)
