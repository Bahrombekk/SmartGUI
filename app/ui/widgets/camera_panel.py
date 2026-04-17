"""
Dashboard — CameraPanel widget.
Har kamera uchun: header (nom + status badge) + video + footer (metrikalar).
"""

import numpy as np

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer
from app.ui.theme import C
from app.ui.widgets.video_label import VideoLabel


# ══════════════════════════════════════════════════════════════════════════════
#  CameraPanel
# ══════════════════════════════════════════════════════════════════════════════

class CameraPanel(QFrame):
    """
    Bitta kamera uchun widget:
      ┌─ header: nom | #id | status badge ──────────┐
      │  VideoLabel                                  │
      └─ footer: FPS · Odamlar · Bugungi buzilish ──┘
    """

    def __init__(self, cam_id: int, cam_name: str, rtsp_url: str,
                 company_id: str, parent=None):
        super().__init__(parent)
        self.cam_id     = cam_id
        self.cam_name   = cam_name
        self.rtsp_url   = rtsp_url
        self.company_id = company_id

        self._connected  = False
        self._pulse_on   = True

        self.setProperty("cam_panel", True)
        self.setMinimumSize(320, 240)

        # Pulsing LIVE dot
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(900)
        self._pulse_timer.timeout.connect(self._pulse_dot)

        self._setup_ui()

    # ── IP qisqartirish ───────────────────────────────────────────────────

    def _short_ip(self) -> str:
        url = self.rtsp_url
        try:
            if "@" in url:
                return url.split("@")[1].split(":")[0]
            elif url.startswith("rtsp://"):
                return url[7:].split("/")[0].split(":")[0]
        except Exception:
            pass
        return url[:18]

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_video(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(42)
        header.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C('accent_dim')}, stop:0.55 {C('bg_panel')}, stop:1 {C('bg_panel')});"
            f"border-radius: 10px 10px 0 0;"
        )
        lay = QHBoxLayout(header)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(8)

        # Kamera nomi
        name_lbl = QLabel(f"📷  {self.cam_name}")
        name_lbl.setStyleSheet(
            f"color:{C('accent_light')};font-size:13px;font-weight:bold;"
            f"background:transparent;"
        )
        lay.addWidget(name_lbl, 1)

        # IP badge
        ip_lbl = QLabel(self._short_ip())
        ip_lbl.setStyleSheet(
            f"color:{C('text_muted')};font-size:10px;"
            f"background:{C('bg_main')};border:1px solid {C('border')};"
            f"border-radius:3px;padding:1px 6px;"
        )
        lay.addWidget(ip_lbl)

        # ID badge
        id_lbl = QLabel(f"#{self.cam_id}")
        id_lbl.setStyleSheet(
            f"color:{C('accent')};font-size:10px;font-weight:bold;"
            f"background:{C('accent_subtle')};border:1px solid {C('accent_dim')};"
            f"border-radius:3px;padding:1px 6px;"
        )
        lay.addWidget(id_lbl)

        # Status badge
        self._status_badge = QLabel("◌  ULANMOQDA")
        self._status_badge.setStyleSheet(self._badge_style(C('warning'), C('warning_dim')))
        lay.addWidget(self._status_badge)

        return header

    def _build_video(self) -> VideoLabel:
        self._video = VideoLabel()
        self._video.show_connecting()
        self._video.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        return self._video

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(36)
        footer.setStyleSheet(
            f"background:{C('bg_main')};"
            f"border-radius:0 0 10px 10px;"
            f"border-top:1px solid {C('border')};"
        )
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(6)

        self._fps_lbl     = self._metric_lbl("⚡", "—", C('info'))
        self._persons_lbl = self._metric_lbl("◉", "—", C('text_secondary'))
        self._viol_lbl    = self._metric_lbl("⚠", "—", C('text_muted'))

        lay.addWidget(self._fps_lbl)
        lay.addWidget(self._sep())
        lay.addWidget(self._persons_lbl)
        lay.addWidget(self._sep())
        lay.addWidget(self._viol_lbl)
        lay.addStretch()

        if self.company_id:
            short = self.company_id[:10] + ("…" if len(self.company_id) > 10 else "")
            co = QLabel(f"🏢 {short}")
            co.setStyleSheet(
                f"color:{C('text_muted')};font-size:10px;background:transparent;"
            )
            lay.addWidget(co)

        return footer

    @staticmethod
    def _metric_lbl(icon: str, value: str, icon_color: str) -> QLabel:
        lbl = QLabel(f"{icon} {value}")
        lbl.setStyleSheet(
            f"color:{icon_color};font-size:11px;background:transparent;"
        )
        lbl.setMinimumWidth(50)
        return lbl

    @staticmethod
    def _sep() -> QLabel:
        s = QLabel("│")
        s.setStyleSheet(f"color:{C('border')};font-size:12px;background:transparent;")
        return s

    @staticmethod
    def _badge_style(color: str, bg: str) -> str:
        return (
            f"color:{color};font-size:10px;font-weight:bold;"
            f"background:{bg};border-radius:4px;padding:2px 8px;"
        )

    # ── Pulsing dot ───────────────────────────────────────────────────────

    def _pulse_dot(self):
        self._pulse_on = not self._pulse_on
        if self._connected:
            dot = "●" if self._pulse_on else "○"
            self._status_badge.setText(f"{dot}  JONLI")

    # ── Tashqi yangilanishlar ─────────────────────────────────────────────

    def set_frame(self, frame: np.ndarray):
        self._video.set_frame(frame)

    def set_stats(self, fps: float, persons: int, today: int, connected: bool):
        self._fps_lbl.setText(f"⚡ {fps:.1f}")
        self._persons_lbl.setText(f"◉ {persons}")

        if today > 0:
            self._viol_lbl.setText(f"⚠ {today}")
            self._viol_lbl.setStyleSheet(
                f"color:{C('danger')};font-size:11px;font-weight:bold;background:transparent;"
            )
        else:
            self._viol_lbl.setText("⚠ 0")
            self._viol_lbl.setStyleSheet(
                f"color:{C('text_muted')};font-size:11px;background:transparent;"
            )

        self._connected = connected
        if connected:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
            self._status_badge.setText("●  JONLI")
            self._status_badge.setStyleSheet(
                self._badge_style(C('success'), C('success_dim'))
            )
        else:
            self._pulse_timer.stop()
            self._status_badge.setText("◌  ULANMOQDA")
            self._status_badge.setStyleSheet(
                self._badge_style(C('warning'), C('warning_dim'))
            )

    def set_error(self, msg: str):
        self._video.show_error(msg)
        self._pulse_timer.stop()
        self._connected = False
        self._status_badge.setText("✕  XATOLIK")
        self._status_badge.setStyleSheet(
            self._badge_style(C('danger'), C('danger_dim'))
        )

    def set_model_loading(self):
        self._video.show_loading()
        self._status_badge.setText("◌  YUKLANMOQDA")
        self._status_badge.setStyleSheet(
            self._badge_style(C('warning'), C('warning_dim'))
        )
