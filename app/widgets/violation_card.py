"""
ViolationCard — buzilish foto kartochkasi.
Thumbnail rasm + vaqt + Track ID ko'rsatadi.
Bosish signali: kattalashtirish uchun.
"""

import os
from datetime import datetime

from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QLabel, QSizePolicy,
                              QDialog, QHBoxLayout, QPushButton, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QCursor

from app.utils.theme import C


class ViolationCard(QFrame):
    """
    Buzilish kartochkasi.

    Signals:
        clicked(dict) — karta bosilganda violation ma'lumoti uzatiladi
    """

    clicked = pyqtSignal(dict)

    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setFixedSize(160, 210)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet(f"""
            ViolationCard {{
                background-color: {C('bg_card')};
                border: 1px solid {C('border')};
                border-radius: 8px;
            }}
            ViolationCard:hover {{
                border-color: {C('accent')};
                background-color: {C('bg_hover')};
            }}
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        # Rasm
        self._img_label = QLabel()
        self._img_label.setFixedSize(144, 130)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet(f"""
            QLabel {{
                background-color: {C('bg_input')};
                border: 1px solid {C('border')};
                border-radius: 5px;
                color: {C('text_muted')};
                font-size: 11px;
            }}
        """)
        self._load_image()
        layout.addWidget(self._img_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Vaqt
        ts = self.violation.get("timestamp", 0)
        dt_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y\n%H:%M:%S") if ts else "—"
        time_lbl = QLabel(dt_str)
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_lbl.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px; background: transparent;"
        )
        layout.addWidget(time_lbl)

        # Track ID
        track_id = self.violation.get("track_id", "?")
        id_lbl = QLabel(f"ID: {track_id}")
        id_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        id_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 11px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(id_lbl)

    def _load_image(self):
        """Crop rasmni yuklash."""
        crop_path = self.violation.get("crop_path", "")
        if crop_path and os.path.exists(crop_path):
            px = QPixmap(crop_path).scaled(
                144, 130,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_label.setPixmap(px)
        else:
            self._img_label.setText("Rasm\nyuq")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.violation)
        super().mousePressEvent(event)


# ── Kattalashtirish dialogi ────────────────────────────────────────────────

class ViolationDetailDialog(QDialog):
    """Bosib ochilgan to'liq buzilish dialogi."""

    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setWindowTitle(f"Buzilish — ID: {violation.get('track_id', '?')}")
        self.setMinimumSize(700, 500)
        self.setStyleSheet(f"QDialog {{ background-color: {C('bg_card')}; }}")
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Chap: to'liq rasm
        left = QVBoxLayout()
        full_label = QLabel()
        full_label.setFixedSize(400, 300)
        full_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        full_label.setStyleSheet(
            f"background: {C('bg_input')}; border-radius: 6px; color: {C('text_muted')};"
        )
        full_path = self.violation.get("full_path", "")
        if full_path and os.path.exists(full_path):
            px = QPixmap(full_path).scaled(
                400, 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            full_label.setPixmap(px)
        else:
            full_label.setText("To'liq rasm\ntopilmadi")
        left.addWidget(full_label)

        # Crop rasm
        crop_label = QLabel()
        crop_label.setFixedSize(180, 120)
        crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crop_label.setStyleSheet(
            f"background: {C('bg_input')}; border-radius: 6px; color: {C('text_muted')};"
        )
        crop_path = self.violation.get("crop_path", "")
        if crop_path and os.path.exists(crop_path):
            px2 = QPixmap(crop_path).scaled(
                180, 120,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            crop_label.setPixmap(px2)
        else:
            crop_label.setText("Crop\ntopilmadi")
        left.addWidget(crop_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(left)

        # O'ng: ma'lumotlar
        right = QVBoxLayout()
        right.setSpacing(10)

        def info_row(label, value, color=None):
            row = QHBoxLayout()
            lbl = QLabel(label + ":")
            lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
            lbl.setFixedWidth(130)
            val = QLabel(str(value))
            val.setStyleSheet(
                f"color: {color or C('text_primary')}; font-size: 12px; font-weight: bold;"
            )
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            return row

        ts = self.violation.get("timestamp", 0)
        dt_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y  %H:%M:%S") if ts else "—"

        right.addWidget(QLabel(
            f"<b style='color:{C('accent')}; font-size:18px;'>"
            f"Buzilish #{self.violation.get('id', '?')}</b>"
        ))
        right.addSpacing(10)
        right.addLayout(info_row("Track ID",   self.violation.get("track_id", "?"), C("accent")))
        right.addLayout(info_row("Vaqt",       dt_str))
        right.addLayout(info_row("Kamera",     self.violation.get("camera_name", "—")))
        right.addLayout(info_row("Ishonch",    f"{self.violation.get('confidence', 0)*100:.1f}%"))
        right.addLayout(info_row("Crop fayl",  crop_path or "—"))
        right.addLayout(info_row("Full fayl",  full_path or "—"))
        right.addStretch()

        close_btn = QPushButton("Yopish")
        close_btn.clicked.connect(self.accept)
        close_btn.setProperty("accent", True)
        right.addWidget(close_btn)
        layout.addLayout(right)
