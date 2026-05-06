from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import C
from app.ui.ui_kit import button_style, chip_style, panel_style, soft_card_style

# ── Violation type → (badge_fg, badge_bg, label, accent_color) ───────────────
_VTYPE: dict[str, tuple[str, str, str, str]] = {
    "no_helmet":      ("#fecaca", "rgba(239,68,68,0.18)",    "NO HELMET",     "#ef4444"),
    "access_denied":  ("#fed7aa", "rgba(249,115,22,0.18)",   "ACCESS DENIED", "#f97316"),
    "unknown_person": ("#e2e8f0", "rgba(148,163,184,0.14)",  "UNKNOWN",       "#94a3b8"),
    "low_confidence": ("#fef3c7", "rgba(234,179,8,0.18)",    "LOW CONF.",     "#fbbf24"),
}


def _vtype(vtype: str) -> tuple[str, str, str, str]:
    return _VTYPE.get(str(vtype or "no_helmet"), _VTYPE["no_helmet"])


def _time_text(value) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value).strftime("%d.%m.%Y %H:%M:%S")
    if isinstance(value, str) and value:
        return value
    return "-"


# ── Async image label ─────────────────────────────────────────────────────────

class EvidenceImage(QLabel):
    """
    QImage ni background thread da yuklaydi (fayl I/O va JPEG decode).
    QPixmap ga o'girish va setPixmap — asosiy thread da (signal orqali).
    """
    _img_ready = pyqtSignal(QImage)

    def __init__(self, path: str, empty_text: str,
                 size: tuple[int, int], parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(*size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background: {C('bg_input')}; border-radius: 8px;"
            f"color: {C('text_muted')}; font-size: 10px; font-weight: 700;"
        )
        self.setText(empty_text)
        self._img_ready.connect(self._on_img_ready)
        if path:
            threading.Thread(
                target=self._load_bg, args=(path,), daemon=True
            ).start()

    def _load_bg(self, path: str):
        try:
            p = Path(path) if Path(path).is_absolute() else Path.cwd() / path
            if not p.exists():
                return
            img = QImage(str(p))
            if not img.isNull():
                self._img_ready.emit(img)
        except Exception:
            pass

    def _on_img_ready(self, img: QImage):
        pix = QPixmap.fromImage(img).scaled(
            self._size[0], self._size[1],
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.setText("")
        self.setPixmap(pix)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


# ── ViolationCard ─────────────────────────────────────────────────────────────

class ViolationCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        vtype = str(violation.get("violation_type") or "no_helmet")
        _, _, _, accent = _vtype(vtype)

        self.setMinimumSize(240, 300)
        self.setStyleSheet(
            "ViolationCard {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #0c151c, stop:1 #071016);"
            "border-top: 1px solid rgba(148,163,184,0.13);"
            "border-right: 1px solid rgba(148,163,184,0.13);"
            "border-bottom: 1px solid rgba(148,163,184,0.13);"
            f"border-left: 3px solid {accent};"
            "border-radius: 8px;"
            "}"
            "ViolationCard:hover {"
            "background: #0f1a25;"
            "border-top: 1px solid rgba(249,115,22,0.42);"
            "border-right: 1px solid rgba(249,115,22,0.42);"
            "border-bottom: 1px solid rgba(249,115,22,0.42);"
            f"border-left: 3px solid {accent};"
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(7)

        crop_path = self.violation.get("crop_path", "")
        lay.addWidget(EvidenceImage(crop_path, "NO\nIMAGE", (222, 158)))

        vtype = str(self.violation.get("violation_type") or "no_helmet")
        fg, bg, label, _ = _vtype(vtype)

        top = QHBoxLayout()
        badge = QLabel(label)
        badge.setStyleSheet(chip_style(fg, bg))
        top.addWidget(badge)
        top.addStretch()
        confidence = float(self.violation.get("confidence", 0) or 0)
        conf = QLabel(f"{confidence * 100:.0f}%")
        conf.setStyleSheet(chip_style("#fed7aa", "rgba(249,115,22,0.10)"))
        top.addWidget(conf)
        lay.addLayout(top)

        cam = QLabel(str(self.violation.get("camera_name") or "Unknown"))
        cam.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 13px; font-weight: 900;"
        )
        cam.setMaximumWidth(222)
        lay.addWidget(cam)

        meta = QHBoxLayout()
        track_id = self.violation.get("track_id", "?")
        id_lbl = QLabel(f"ID: {track_id}")
        id_lbl.setStyleSheet(
            f"color: {C('accent_light')}; font-size: 12px; font-weight: 900;"
        )
        meta.addWidget(id_lbl)
        meta.addStretch()
        time_lbl = QLabel(_time_text(self.violation.get("timestamp"))[-8:])
        time_lbl.setStyleSheet(
            chip_style(C("text_secondary"), "rgba(148,163,184,0.08)")
        )
        meta.addWidget(time_lbl)
        lay.addLayout(meta)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit(self.violation)
            return
        super().mousePressEvent(event)


# ── ViolationDetailDialog ─────────────────────────────────────────────────────

class ViolationDetailDialog(QDialog):
    def __init__(self, violation: dict, parent=None):
        super().__init__(parent)
        self.violation = violation
        self.setWindowTitle(
            f"Violation Evidence  —  ID: {violation.get('track_id', '?')}"
        )
        self.setMinimumSize(960, 600)
        self.setStyleSheet(f"QDialog {{ background: {C('bg_main')}; }}")
        self._setup_ui()

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── Sol: rasmlar ──────────────────────────────────────────────────
        image_panel = QFrame()
        image_panel.setObjectName("evidencePanel")
        image_panel.setStyleSheet(panel_style("evidencePanel"))
        image_lay = QVBoxLayout(image_panel)
        image_lay.setContentsMargins(14, 14, 14, 14)
        image_lay.setSpacing(10)

        title = QLabel("Evidence Review")
        title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 18px; font-weight: 900;"
        )
        image_lay.addWidget(title)

        image_lay.addWidget(
            EvidenceImage(
                self.violation.get("full_path", ""),
                "FULL FRAME\nNOT FOUND",
                (580, 360),
            )
        )

        crop_row = QHBoxLayout()
        crop_row.addWidget(
            EvidenceImage(
                self.violation.get("crop_path", ""),
                "CROP\nNOT FOUND",
                (180, 120),
            )
        )
        crop_hint = QLabel(
            "Crop image from detection frame. Full frame is available for context."
        )
        crop_hint.setWordWrap(True)
        crop_hint.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        crop_row.addWidget(crop_hint, 1)
        image_lay.addLayout(crop_row)
        root.addWidget(image_panel, 1)

        # ── O'ng: meta ────────────────────────────────────────────────────
        info = QFrame()
        info.setObjectName("metadataPanel")
        info.setFixedWidth(310)
        info.setStyleSheet(panel_style("metadataPanel"))
        info_lay = QVBoxLayout(info)
        info_lay.setContentsMargins(14, 14, 14, 14)
        info_lay.setSpacing(8)

        vtype = str(self.violation.get("violation_type") or "no_helmet")
        fg, bg, label, _ = _vtype(vtype)
        badge = QLabel(label)
        badge.setStyleSheet(chip_style(fg, bg))
        info_lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

        for lbl, val in [
            ("Violation ID",  self.violation.get("id", "-")),
            ("Track ID",      self.violation.get("track_id", "-")),
            ("Camera",        self.violation.get("camera_name", "-")),
            ("Time",          _time_text(self.violation.get("timestamp"))),
            ("Confidence",    f"{float(self.violation.get('confidence', 0) or 0) * 100:.1f}%"),
            ("Crop path",     self.violation.get("crop_path", "-") or "-"),
            ("Full path",     self.violation.get("full_path", "-") or "-"),
        ]:
            info_lay.addWidget(self._info_row(lbl, val))

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
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)
        k = QLabel(label)
        k.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; font-weight: 800;"
        )
        lay.addWidget(k)
        v = QLabel(str(value))
        v.setWordWrap(True)
        v.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 12px; font-weight: 700;"
        )
        lay.addWidget(v)
        return row
