"""
Dashboard — CameraPanel widget.
"""

import numpy as np

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from app.ui.theme import C
from app.ui.widgets.video_label import VideoLabel


class CameraPanel(QFrame):
    clicked = pyqtSignal(int)

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
        self._apply_panel_style(False)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(800)
        self._pulse_timer.timeout.connect(self._pulse_dot)

        self._setup_ui()

    def _apply_panel_style(self, selected: bool):
        border = C("accent") if selected else "#1e5fa8"
        bg     = "rgba(249,115,22,0.10)" if selected else "#060e18"
        self.setStyleSheet(
            "QFrame[cam_panel='true'] {"
            f"background: {bg};"
            f"border: 2px solid {border};"
            "border-radius: 10px;"
            "}"
        )

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_panel_style(selected)

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
        hdr.setFixedHeight(38)
        hdr.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #091828, stop:1 #071016);"
            "border-radius: 9px 9px 0 0;"
        )
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        # Pulsing status dot
        self._dot = QLabel("●")
        self._dot.setFixedSize(18, 18)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dot.setStyleSheet(
            "color: #fbbf24; font-size: 13px; background: transparent;"
        )
        lay.addWidget(self._dot)

        # Camera ID pill
        id_pill = QLabel(f"{self.cam_id:02d}")
        id_pill.setFixedSize(30, 20)
        id_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        id_pill.setStyleSheet(
            "background: rgba(30,95,168,0.40);"
            "color: #93c5fd;"
            "border: 1px solid rgba(30,95,168,0.70);"
            "border-radius: 5px;"
            "font-size: 10px; font-weight: 800;"
        )
        lay.addWidget(id_pill)

        # Camera name
        name_lbl = QLabel(self.cam_name)
        name_lbl.setStyleSheet(
            "color: #e8f4ff; font-size: 12px; font-weight: 700;"
            " background: transparent;"
        )
        lay.addWidget(name_lbl, 1)

        # Status badge (LIVE / OFFLINE / connecting)
        self._badge = QLabel("Ulanmoqda")
        self._badge.setStyleSheet(
            "color: #fbbf24; font-size: 10px; font-weight: 800;"
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
        ftr.setFixedHeight(28)
        ftr.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #091828, stop:1 #071016);"
            "border-radius: 0 0 9px 9px;"
        )
        lay = QHBoxLayout(ftr)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(0)

        # FPS — left
        self._fps_lbl = QLabel("-- fps")
        self._fps_lbl.setStyleSheet(
            "color: #60a5fa; font-size: 10px; font-weight: 700;"
            " background: transparent;"
        )
        lay.addWidget(self._fps_lbl)

        lay.addStretch()

        # Person count — right with icon dot
        self._persons_dot = QLabel("●")
        self._persons_dot.setStyleSheet(
            "color: #475569; font-size: 7px; background: transparent;"
        )
        lay.addWidget(self._persons_dot)

        lay.addSpacing(4)

        self._persons_lbl = QLabel("0 kishi")
        self._persons_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 10px; font-weight: 700;"
            " background: transparent;"
        )
        lay.addWidget(self._persons_lbl)

        return ftr

    # ── Pulsing dot ───────────────────────────────────────────────────────

    def _pulse_dot(self):
        self._pulse_on = not self._pulse_on
        if self._connected:
            col = "#22c55e" if self._pulse_on else "#14532d"
            self._dot.setStyleSheet(
                f"color: {col}; font-size: 13px; background: transparent;"
            )

    # ── External updates ──────────────────────────────────────────────────

    def set_frame(self, frame):
        self._video.set_frame(frame)

    def set_stats(self, fps: float, persons: int, today: int, connected: bool):
        self._fps_lbl.setText(f"{fps:.0f} fps")

        if persons > 0:
            self._persons_lbl.setText(f"{persons} kishi")
            self._persons_lbl.setStyleSheet(
                "color: #34d399; font-size: 10px; font-weight: 700; background: transparent;"
            )
            self._persons_dot.setStyleSheet(
                "color: #34d399; font-size: 7px; background: transparent;"
            )
        else:
            self._persons_lbl.setText("0 kishi")
            self._persons_lbl.setStyleSheet(
                "color: #475569; font-size: 10px; font-weight: 700; background: transparent;"
            )
            self._persons_dot.setStyleSheet(
                "color: #334155; font-size: 7px; background: transparent;"
            )

        self._connected = connected
        if connected:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
            self._dot.setStyleSheet(
                "color: #22c55e; font-size: 13px; background: transparent;"
            )
            self._badge.setText("● LIVE")
            self._badge.setStyleSheet(
                "color: #ef4444; font-size: 10px; font-weight: 900;"
                " background: rgba(239,68,68,0.12);"
                " border: 1px solid rgba(239,68,68,0.30);"
                " border-radius: 5px; padding: 0 6px;"
            )
            self._fps_lbl.setStyleSheet(
                "color: #60a5fa; font-size: 10px; font-weight: 700; background: transparent;"
            )
        else:
            self._pulse_timer.stop()
            self._dot.setStyleSheet(
                "color: #374151; font-size: 13px; background: transparent;"
            )
            self._badge.setText("Offline")
            self._badge.setStyleSheet(
                "color: #64748b; font-size: 10px; font-weight: 800;"
                " background: transparent;"
            )
            self._fps_lbl.setStyleSheet(
                "color: #334155; font-size: 10px; font-weight: 700; background: transparent;"
            )
            if not self._video._has_frame:
                self._video.show_error()

    def set_error(self, msg: str):
        self._video.show_error(msg)
        self._pulse_timer.stop()
        self._connected = False
        self._dot.setStyleSheet(
            "color: #ef4444; font-size: 13px; background: transparent;"
        )
        self._badge.setText("Offline")
        self._badge.setStyleSheet(
            "color: #64748b; font-size: 10px; font-weight: 800; background: transparent;"
        )

    def set_model_loading(self):
        self._video.show_connecting()
        self._dot.setStyleSheet(
            "color: #fbbf24; font-size: 13px; background: transparent;"
        )
        self._badge.setText("Yuklanmoqda")
        self._badge.setStyleSheet(
            "color: #fbbf24; font-size: 10px; font-weight: 800; background: transparent;"
        )

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)
        super().mousePressEvent(event)
