"""
Dashboard — CameraPanel widget.
"""

import numpy as np

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from app.ui.styles import (
    C,
    campanel_outer_style,
    campanel_id_pill_style,
    campanel_name_style,
    campanel_fps_style,
    header_gradient_style,
)
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
        self._panel_style_key = None
        self._stats_state = None
        self._status_state = None

        self.setProperty("cam_panel", True)
        self.setMinimumSize(260, 180)
        self._apply_panel_style(False)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(800)
        self._pulse_timer.timeout.connect(self._pulse_dot)

        self._setup_ui()

    def _apply_panel_style(self, selected: bool):
        if self._panel_style_key == selected:
            return
        self._panel_style_key = selected
        self.setStyleSheet(campanel_outer_style(selected))

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self._apply_panel_style(selected)

    @staticmethod
    def _set_text(label: QLabel, text: str):
        if label.text() != text:
            label.setText(text)

    @staticmethod
    def _set_style(widget: QWidget, style: str):
        if widget.styleSheet() != style:
            widget.setStyleSheet(style)

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
        hdr.setStyleSheet(header_gradient_style("9px 9px 0 0"))
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)

        # Pulsing status dot
        self._dot = QLabel("●")
        self._dot.setFixedSize(18, 18)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dot.setStyleSheet(
            f"color: {C('warning')}; font-size: 13px; background: transparent;"
        )
        lay.addWidget(self._dot)

        # Camera ID pill — theme'ga moslangan
        id_pill = QLabel(f"{self.cam_id:02d}")
        id_pill.setFixedSize(30, 20)
        id_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        id_pill.setStyleSheet(campanel_id_pill_style())
        lay.addWidget(id_pill)

        # Camera name
        name_lbl = QLabel(self.cam_name)
        name_lbl.setStyleSheet(campanel_name_style())
        lay.addWidget(name_lbl, 1)

        # Status badge (LIVE / OFFLINE / connecting)
        self._badge = QLabel("Ulanmoqda")
        self._badge.setStyleSheet(
            f"color: {C('warning')}; font-size: 10px; font-weight: 800;"
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
        ftr.setStyleSheet(header_gradient_style("0 0 9px 9px"))
        lay = QHBoxLayout(ftr)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(0)

        # FPS — left
        self._fps_lbl = QLabel("-- fps")
        self._fps_lbl.setStyleSheet(campanel_fps_style())
        lay.addWidget(self._fps_lbl)

        lay.addStretch()

        # Person count — right with icon dot
        self._persons_dot = QLabel("●")
        self._persons_dot.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 7px; background: transparent;"
        )
        lay.addWidget(self._persons_dot)

        lay.addSpacing(4)

        self._persons_lbl = QLabel("0 kishi")
        self._persons_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 10px; font-weight: 700;"
            " background: transparent;"
        )
        lay.addWidget(self._persons_lbl)

        return ftr

    # ── Pulsing dot ───────────────────────────────────────────────────────

    def _pulse_dot(self):
        # Yashirin bo'lsa pulse ishlamasin (panel boshqa sahifaga o'tganda CPU sarflanmasin)
        if not self.isVisible():
            self._pulse_timer.stop()
            return
        self._pulse_on = not self._pulse_on
        if self._connected:
            col = "#22c55e" if self._pulse_on else "#16a34a"
            self._set_style(self._dot, f"color: {col}; font-size: 13px; background: transparent;")
            if self._pulse_on:
                self._set_style(
                    self._badge,
                    "color: #22c55e; font-size: 10px; font-weight: 800; letter-spacing: 1px;"
                    " background: transparent; border: none; padding: 1px 8px;",
                )
            else:
                self._set_style(
                    self._badge,
                    "color: rgba(34,197,94,0.6); font-size: 10px; font-weight: 800; letter-spacing: 1px;"
                    " background: transparent; border: none; padding: 1px 8px;",
                )

    # ── External updates ──────────────────────────────────────────────────

    def set_frame(self, frame):
        self._video.set_frame(frame)

    def set_stats(self, fps: float, persons: int, today: int, connected: bool):
        state = (round(float(fps or 0)), int(persons or 0), bool(connected))
        if self._stats_state == state:
            return
        self._stats_state = state
        self._status_state = None
        self._set_text(self._fps_lbl, f"{fps:.0f} fps")

        if persons > 0:
            self._set_text(self._persons_lbl, f"{persons} kishi")
            self._set_style(self._persons_lbl, "color: #34d399; font-size: 10px; font-weight: 700; background: transparent;")
            self._set_style(self._persons_dot, "color: #34d399; font-size: 7px; background: transparent;")
        else:
            self._set_text(self._persons_lbl, "0 kishi")
            self._set_style(self._persons_lbl, "color: #475569; font-size: 10px; font-weight: 700; background: transparent;")
            self._set_style(self._persons_dot, "color: #334155; font-size: 7px; background: transparent;")

        self._connected = connected
        if connected:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
            self._dot.setStyleSheet(
                "color: #22c55e; font-size: 13px; background: transparent;"
            )
            self._badge.setText("LIVE")
            self._badge.setStyleSheet(
                "color: #22c55e; font-size: 10px; font-weight: 800;"
                " letter-spacing: 1px;"
                " background: transparent;"
                " border: none; padding: 1px 8px;"
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
        if self._status_state == ("error", msg):
            return
        self._status_state = ("error", msg)
        self._stats_state = None
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
        if self._status_state == ("loading", ""):
            return
        self._status_state = ("loading", "")
        self._stats_state = None
        self._video.show_connecting()
        self._dot.setStyleSheet(
            "color: #fbbf24; font-size: 13px; background: transparent;"
        )
        self._badge.setText("Yuklanmoqda")
        self._badge.setStyleSheet(
            "color: #fbbf24; font-size: 10px; font-weight: 800; background: transparent;"
        )

    def showEvent(self, event):
        super().showEvent(event)
        # Qayta ko'rinadigan bo'lsa va kamera tirik bo'lsa pulse'ni qayta yoqish
        if self._connected and not self._pulse_timer.isActive():
            self._pulse_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        # Yashirin bo'lganda pulse to'xtaydi — CPU sarflanmaydi
        if self._pulse_timer.isActive():
            self._pulse_timer.stop()

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)
        super().mousePressEvent(event)
