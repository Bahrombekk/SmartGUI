from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui.theme import C
from app.ui.ui_kit import button_style, chip_style, panel_style, soft_card_style


def _time_text(value) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value).strftime("%d.%m.%Y %H:%M:%S")
    if isinstance(value, str) and value:
        return value
    return "-"


class EvidenceImage(QLabel):
    def __init__(self, path: str, empty_text: str, size: tuple[int, int], expand: bool = False, parent=None):
        super().__init__(parent)
        self._target_size = size
        self._expand = expand
        self.setFixedSize(*size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background: {C('bg_input')}; border: 1px solid rgba(148,163,184,0.14);"
            f"border-radius: 8px; color: {C('text_muted')}; font-size: 11px; font-weight: 800;"
        )
        self._load(path, empty_text)

    def _load(self, path: str, empty_text: str):
        resolved = self._resolve_path(path)
        if not resolved or not resolved.exists():
            self.setText(empty_text)
            return

        pix = QPixmap(str(resolved))
        if pix.isNull():
            self.setText(empty_text)
            return
        self._apply(pix)

    @staticmethod
    def _resolve_path(path: str) -> Path | None:
        if not path:
            return None
        p = Path(path)
        if p.is_absolute():
            return p
        return Path.cwd() / p

    def _apply(self, pix: QPixmap):
        self.setPixmap(
            pix.scaled(
                self._target_size[0],
                self._target_size[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class ViolationCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumSize(238, 294)
        self.setStyleSheet(
            "ViolationCard {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid rgba(148,163,184,0.14); border-radius: 8px;"
            "}"
            "ViolationCard:hover { border-color: rgba(249,115,22,0.62); background: #0f172a; }"
            "QLabel { background: transparent; border: none; }"
        )
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        crop_path = self.violation.get("crop_path", "")
        lay.addWidget(EvidenceImage(crop_path, "NO\nIMAGE", (218, 152), expand=True))

        top = QHBoxLayout()
        badge = QLabel("NO HELMET")
        badge.setStyleSheet(chip_style("#fecaca", "rgba(239,68,68,0.16)"))
        top.addWidget(badge)
        top.addStretch()

        confidence = float(self.violation.get("confidence", 0) or 0)
        conf = QLabel(f"{confidence * 100:.0f}%")
        conf.setStyleSheet(chip_style("#fed7aa", "rgba(249,115,22,0.10)"))
        top.addWidget(conf)
        lay.addLayout(top)

        cam = QLabel(str(self.violation.get("camera_name") or "Unknown camera"))
        cam.setStyleSheet(f"color: {C('text_primary')}; font-size: 13px; font-weight: 900;")
        lay.addWidget(cam)

        meta = QHBoxLayout()
        track_id = self.violation.get("track_id", "?")
        id_lbl = QLabel(f"ID: {track_id}")
        id_lbl.setStyleSheet(f"color: {C('accent_light')}; font-size: 12px; font-weight: 900;")
        meta.addWidget(id_lbl)
        meta.addStretch()
        time_lbl = QLabel(_time_text(self.violation.get("timestamp"))[-8:])
        time_lbl.setStyleSheet(chip_style(C("text_secondary"), "rgba(148,163,184,0.08)"))
        meta.addWidget(time_lbl)
        lay.addLayout(meta)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit(self.violation)
            return
        super().mousePressEvent(event)


class ViolationDetailDialog(QDialog):
    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setWindowTitle(f"Violation Evidence - ID: {violation.get('track_id', '?')}")
        self.setMinimumSize(920, 580)
        self.setStyleSheet(f"QDialog {{ background: {C('bg_main')}; }}")
        self._setup_ui()

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        image_panel = QFrame()
        image_panel.setObjectName("evidencePanel")
        image_panel.setStyleSheet(panel_style("evidencePanel"))
        image_lay = QVBoxLayout(image_panel)
        image_lay.setContentsMargins(14, 14, 14, 14)
        image_lay.setSpacing(10)

        title = QLabel("Evidence Review")
        title.setStyleSheet(f"color: {C('text_primary')}; font-size: 18px; font-weight: 900;")
        image_lay.addWidget(title)
        image_lay.addWidget(EvidenceImage(self.violation.get("full_path", ""), "FULL FRAME\nNOT FOUND", (560, 350)))

        crop_row = QHBoxLayout()
        crop_row.addWidget(EvidenceImage(self.violation.get("crop_path", ""), "CROP\nNOT FOUND", (180, 120), expand=True))
        crop_hint = QLabel("Crop image is taken from the saved detection frame. Full frame remains available for context.")
        crop_hint.setWordWrap(True)
        crop_hint.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        crop_row.addWidget(crop_hint, 1)
        image_lay.addLayout(crop_row)
        root.addWidget(image_panel, 1)

        info = QFrame()
        info.setObjectName("metadataPanel")
        info.setFixedWidth(300)
        info.setStyleSheet(panel_style("metadataPanel"))
        info_lay = QVBoxLayout(info)
        info_lay.setContentsMargins(14, 14, 14, 14)
        info_lay.setSpacing(10)

        badge = QLabel("NO HELMET")
        badge.setStyleSheet(chip_style("#fecaca", "rgba(239,68,68,0.16)"))
        info_lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

        for label, value in [
            ("Violation ID", self.violation.get("id", "-")),
            ("Track ID", self.violation.get("track_id", "-")),
            ("Camera", self.violation.get("camera_name", "-")),
            ("Time", _time_text(self.violation.get("timestamp"))),
            ("Confidence", f"{float(self.violation.get('confidence', 0) or 0) * 100:.1f}%"),
            ("Crop path", self.violation.get("crop_path", "-") or "-"),
            ("Full path", self.violation.get("full_path", "-") or "-"),
        ]:
            info_lay.addWidget(self._info_row(label, value))

        info_lay.addStretch()
        close = QPushButton("Close")
        close.setFixedHeight(36)
        close.setStyleSheet(button_style("primary"))
        close.clicked.connect(self.accept)
        info_lay.addWidget(close)
        root.addWidget(info)

    def _info_row(self, label: str, value) -> QWidget:
        row = QFrame()
        row.setStyleSheet(soft_card_style())
        lay = QVBoxLayout(row)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        k = QLabel(label)
        k.setStyleSheet(f"color: {C('text_muted')}; font-size: 10px; font-weight: 800;")
        lay.addWidget(k)
        v = QLabel(str(value))
        v.setWordWrap(True)
        v.setStyleSheet(f"color: {C('text_primary')}; font-size: 12px; font-weight: 800;")
        lay.addWidget(v)
        return row
