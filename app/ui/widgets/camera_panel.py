"""
Dashboard — CameraPanel widget.
SmartHelmet dizayniga mos: header (status + nom) + video + footer (vaqt + fps).
"""

import datetime
import numpy as np

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPen

from app.ui.theme import C
from app.ui.widgets.video_label import VideoLabel


class CameraPanel(QFrame):
    clicked = pyqtSignal(int)
    """
    Bitta kamera uchun widget:
      ┌─ header: status dot | #NN CamName  |  ● REC / Live / Offline ──┐
      │  VideoLabel                                                      │
      └─ footer: 10:20:58  ───────────────────────── 30 fps  2 kishi ──┘
    """

    def __init__(self, cam_id: int, cam_name: str, rtsp_url: str,
                 company_id: str, parent=None):
        super().__init__(parent)
        self.cam_id     = cam_id
        self.cam_name   = cam_name
        self.rtsp_url   = rtsp_url
        self.company_id = company_id

        self._connected = False
        self._pulse_on  = True
        self._selected  = False

        self.setProperty("cam_panel", True)
        self.setMinimumSize(260, 180)
        self.setStyleSheet(
            "QFrame[cam_panel='true'] {"
            "background: #000000;"
            "border: none;"
            "border-radius: 10px;"
            "}"
        )

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(900)
        self._pulse_timer.timeout.connect(self._pulse_dot)

        self._setup_ui()

    def set_selected(self, selected: bool):
        self._selected = selected
        border = C("accent") if selected else "#1e293b"
        ring = "rgba(249,115,22,0.25)" if selected else "#000000"
        self.setStyleSheet(
            "QFrame[cam_panel='true'] {"
            f"background: {ring};"
            f"border: 2px solid {border};"
            "border-radius: 10px;"
            "}"
        )

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_video(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            "background: rgba(7,16,22,0.92);"
            "border-radius: 10px 10px 0 0;"
        )
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(6)

        # Status dot
        self._dot = QLabel("●")
        self._dot.setText("o")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet(
            f"color: {C('cam_idle')}; font-size: 9px; background: transparent;"
        )
        lay.addWidget(self._dot)

        # Camera number
        num = QLabel(f"{self.cam_id:02d}")
        num.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 11px; font-weight: bold;"
            " background: transparent;"
        )
        lay.addWidget(num)

        # Camera name
        name = QLabel(self.cam_name)
        name.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px; font-weight: 600;"
            " background: transparent;"
        )
        lay.addWidget(name, 1)

        # Status badge
        self._badge = QLabel("Ulanmoqda")
        self._badge.setStyleSheet(
            f"color: {C('warning')}; font-size: 10px; font-weight: bold;"
            " background: transparent;"
        )
        lay.addWidget(self._badge)

        return hdr

    def _build_video(self) -> VideoLabel:
        self._video = VideoLabel()
        self._video.show_connecting()
        self._video.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        return self._video

    def _build_footer(self) -> QWidget:
        ftr = QWidget()
        ftr.setFixedHeight(26)
        ftr.setStyleSheet(
            "background: rgba(7,16,22,0.92);"
            "border-radius: 0 0 10px 10px;"
        )
        lay = QHBoxLayout(ftr)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        self._time_lbl = QLabel("--:--:--")
        self._time_lbl.setStyleSheet(
            "color: #dce5ef; font-size: 10px; background: rgba(0,0,0,0.55);"
            "border-radius: 4px; padding: 2px 6px;"
        )
        lay.addWidget(self._time_lbl)
        lay.addStretch()

        self._fps_lbl = QLabel("-- fps")
        self._fps_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(self._fps_lbl)

        lay.addWidget(self._vsep())

        self._persons_lbl = QLabel("0 kishi")
        self._persons_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 10px; background: transparent;"
        )
        lay.addWidget(self._persons_lbl)

        return ftr

    @staticmethod
    def _vsep() -> QLabel:
        s = QLabel("|")
        s.setStyleSheet(f"color: {C('border')}; font-size: 11px; background: transparent;")
        return s

    # ── Pulsing dot ───────────────────────────────────────────────────────

    def _pulse_dot(self):
        self._pulse_on = not self._pulse_on
        if self._connected:
            col = C('success') if self._pulse_on else "#1a5a28"
            self._dot.setStyleSheet(
                f"color: {col}; font-size: 9px; background: transparent;"
            )

    # ── Tashqi yangilanishlar ─────────────────────────────────────────────

    def set_frame(self, frame):
        self._video.set_frame(frame)
        self._time_lbl.setText(datetime.datetime.now().strftime("%H:%M:%S"))

    def set_stats(self, fps: float, persons: int, today: int, connected: bool):
        self._fps_lbl.setText(f"{fps:.0f} fps")
        self._persons_lbl.setText(f"{persons} kishi")

        self._connected = connected
        if connected:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
            self._dot.setStyleSheet(
                f"color: {C('success')}; font-size: 9px; background: transparent;"
            )
            self._badge.setStyleSheet(
                f"color: {C('danger')}; font-size: 10px; font-weight: bold;"
                " background: transparent;"
            )
            self._badge.setText("Live")
        else:
            self._pulse_timer.stop()
            self._dot.setStyleSheet(
                f"color: {C('cam_idle')}; font-size: 9px; background: transparent;"
            )
            self._badge.setText("Offline")
            self._badge.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
            )
            if not self._video._has_frame:
                self._video.show_error()

    def set_error(self, msg: str):
        self._video.show_error(msg)
        self._pulse_timer.stop()
        self._connected = False
        self._dot.setStyleSheet(
            f"color: {C('danger')}; font-size: 9px; background: transparent;"
        )
        self._badge.setText("Offline")
        self._badge.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )

    def set_model_loading(self):
        self._video.show_connecting()
        self._dot.setStyleSheet(
            f"color: {C('warning')}; font-size: 9px; background: transparent;"
        )
        self._badge.setText("Yuklanmoqda")
        self._badge.setStyleSheet(
            f"color: {C('warning')}; font-size: 10px; background: transparent;"
        )

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)
        super().mousePressEvent(event)
