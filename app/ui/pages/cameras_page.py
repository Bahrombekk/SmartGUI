"""
CamerasPage - production camera operations and inventory view.

Dashboard remains the primary live video wall. This page is for operations:
fleet health, connection status, camera metadata, filtered recent events, and
on-demand preview for the selected camera.
"""

from __future__ import annotations

import datetime
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QRectF, Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpacerItem,
    QSizePolicy,
    QWidget,
    QVBoxLayout,
)

from app.ui.styles import C, is_light, on_theme_change
from app.ui.widgets.video_label import VideoLabel


# ── Module-level rang konstantalari — mavzu o'zgarsa yangilanadi ─────────────
SURFACE = SIDEBAR_BG = SIDEBAR_INSET = SURFACE_2 = SURFACE_3 = ""
BORDER = BORDER_STRONG = BORDER_SOFT = ""
TEXT = TEXT_2 = MUTED = DIM = ACCENT = ""
LIVE = OFFLINE = WARN = ""
STATUS_COLORS: dict[str, str] = {}


def _refresh_module_colors() -> None:
    """Modul darajasidagi rang konstantalarini joriy mavzudan yangilaydi.

    `set_theme()` chaqirilganda avtomatik ishga tushadi.
    """
    g = globals()
    g['SURFACE']       = C('bg_panel')
    g['SIDEBAR_BG']    = C('bg_sidebar')
    g['SIDEBAR_INSET'] = C('bg_panel_alt')
    g['SURFACE_2']     = C('bg_panel')
    g['SURFACE_3']     = C('bg_panel_alt')
    g['BORDER']        = C('border_panel')
    g['BORDER_STRONG'] = C('border_strong')
    g['BORDER_SOFT']   = C('border_soft')
    g['TEXT']          = C('text_primary')
    g['TEXT_2']        = C('text_secondary')
    g['MUTED']         = C('text_muted')
    g['DIM']           = C('text_dim')
    g['ACCENT']        = C('accent')
    g['LIVE']          = C('success')
    g['OFFLINE']       = C('danger')
    g['WARN']          = C('warning')
    g['STATUS_COLORS'] = {
        "live":       g['LIVE'],
        "offline":    g['OFFLINE'],
        "error":      g['OFFLINE'],
        "connecting": g['WARN'],
    }


# Modul import qilinganda + har mavzu almashganda chaqiriladi
on_theme_change(_refresh_module_colors)


def _status_label(status: str) -> str:
    return {"live": "Live", "connecting": "Connecting", "error": "Error"}.get(status, "Offline")


class FleetStatusBar(QWidget):
    """Thin horizontal bar: one colored segment per camera (live=green, error=red, connecting=amber)."""

    _COLORS = {
        "live":       (34, 197, 94, 210),
        "offline":    (239, 68, 68, 200),
        "error":      (239, 68, 68, 200),
        "connecting": (245, 158, 11, 180),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[str] = []
        self.setFixedHeight(5)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Fleet status — each segment = one camera")

    def set_segments(self, segments: list[str]):
        self._segments = segments
        self.update()

    def paintEvent(self, event):
        if not self._segments:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self._segments)
        w, h = float(self.width()), float(self.height())
        gap = 3.0
        seg_w = max(1.0, (w - gap * (n - 1)) / n)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 3, 3)
        painter.setClipPath(path)
        for i, status in enumerate(self._segments):
            x = i * (seg_w + gap)
            r, g, b, a = self._COLORS.get(status, (100, 116, 139, 150))
            painter.fillRect(QRectF(x, 0, seg_w, h), QColor(r, g, b, a))
        painter.end()


class DeptProgressBadge(QWidget):
    """Department live/total badge with a mini colored progress bar."""

    def __init__(self, live: int, total: int, parent=None):
        super().__init__(parent)
        self._live = live
        self._total = total
        self.setFixedSize(46, 30)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def update_counts(self, live: int, total: int):
        self._live = live
        self._total = total
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        live_c = QColor(34, 197, 94) if self._live > 0 else QColor(100, 116, 139)
        painter.setPen(live_c)
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, 1, w, h - 6),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._live}/{self._total}",
        )
        bar_y = float(h - 4)
        painter.fillRect(QRectF(0, bar_y, w, 3), QColor(30, 95, 168, 40))
        fill_w = (w * self._live / self._total) if self._total > 0 else 0.0
        if fill_w > 0:
            painter.fillRect(
                QRectF(0, bar_y, fill_w, 3),
                QColor(34, 197, 94, 200) if self._live > 0 else QColor(100, 116, 139, 140),
            )
        painter.end()


class CameraBanner(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_image(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), QColor("#06101a"))

        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.fillRect(self.rect(), QColor(2, 8, 16, 82))
        else:
            painter.setPen(QColor("#49647f"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "CAMERA AREA")
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#17283b"), 1))
        painter.drawPath(path)
        painter.end()


class BannerWithOverlay(QWidget):
    reconnect_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._banner = CameraBanner(self)

        self._count_badge = QLabel(self)
        self._count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_badge.setStyleSheet(
            "background: rgba(239,68,68,0.82); color: #fff;"
            "border: 1px solid rgba(239,68,68,0.90); border-radius: 7px;"
            "font-size: 10px; font-weight: 900; padding: 2px 7px;"
        )
        self._count_badge.hide()

        self._viol_thumb = QLabel(self)
        self._viol_thumb.setFixedSize(58, 44)
        self._viol_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._viol_thumb.setStyleSheet(
            "border: 2px solid rgba(239,68,68,0.70); border-radius: 4px;"
            "background: #050c14;"
        )
        self._viol_thumb.hide()

        self._reconnect_btn = QPushButton("Reconnect", self)
        self._reconnect_btn.setFixedHeight(32)
        self._reconnect_btn.setMinimumWidth(110)
        self._reconnect_btn.setStyleSheet(
            "QPushButton { background: rgba(30,95,168,0.85); color: #e0f0ff;"
            "border: 1px solid #1e5fa8; border-radius: 8px;"
            "font-size: 11px; font-weight: 800; padding: 0 18px; }"
            "QPushButton:hover { background: rgba(45,128,200,0.95); color: #fff; }"
        )
        self._reconnect_btn.clicked.connect(self.reconnect_clicked)
        self._reconnect_btn.hide()

        self._offline_badge = QLabel("OFFLINE", self)
        self._offline_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._offline_badge.setStyleSheet(
            "background: rgba(239,68,68,0.88); color: #fff;"
            "border: 1px solid rgba(255,255,255,0.18); border-radius: 8px;"
            "font-size: 12px; font-weight: 900; padding: 4px 16px;"
        )
        self._offline_badge.hide()

        # Hover overlay — shows on live cameras when mouse enters
        self._hover_bar = QWidget(self)
        self._hover_bar.setStyleSheet(
            "background: rgba(0,0,0,0.48); border-radius: 6px;"
        )
        _hlbl = QLabel("INSPECT", self._hover_bar)
        _hlbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _hlbl.setStyleSheet(
            "color: rgba(255,255,255,0.90); font-size: 11px; font-weight: 900;"
            "letter-spacing: 3px; background: transparent;"
        )
        _hlay = QVBoxLayout(self._hover_bar)
        _hlay.setContentsMargins(0, 0, 0, 0)
        _hlay.addWidget(_hlbl)
        self._hover_bar.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._banner.resize(self.size())
        self._reposition_overlays()

    def _reposition_overlays(self):
        w, h = self.width(), self.height()
        self._count_badge.adjustSize()
        self._count_badge.move(8, 8)
        self._viol_thumb.move(max(0, w - 64), 6)
        bw = max(self._reconnect_btn.sizeHint().width(), 110)
        self._reconnect_btn.resize(bw, 32)
        self._reconnect_btn.move((w - bw) // 2, (h - 32) // 2)
        self._offline_badge.adjustSize()
        ow = max(self._offline_badge.width(), 104)
        self._offline_badge.resize(ow, 30)
        self._offline_badge.move((w - ow) // 2, max(8, (h - 30) // 2 - 22))
        self._hover_bar.setGeometry(0, 0, w, h)

    def set_hover(self, hovered: bool):
        live_mode = self._reconnect_btn.isHidden() and self._offline_badge.isHidden()
        if hovered and live_mode:
            self._hover_bar.show()
            self._hover_bar.raise_()
        else:
            self._hover_bar.hide()

    def set_image(self, pixmap: QPixmap):
        self._banner.set_image(pixmap)

    def set_offline_visible(self, visible: bool, text: str = "OFFLINE"):
        self._offline_badge.setText(text)
        if visible:
            self._offline_badge.show()
            self._offline_badge.raise_()
            self._reposition_overlays()
        else:
            self._offline_badge.hide()

    def set_count(self, count: int):
        if count > 0:
            self._count_badge.setText(str(count))
            self._count_badge.adjustSize()
            self._count_badge.move(8, 8)
            self._count_badge.show()
            self._count_badge.raise_()
        else:
            self._count_badge.hide()

    def set_last_violation(self, path: str):
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self.set_last_violation_pixmap(pix)
                return
        self._viol_thumb.hide()

    def set_last_violation_pixmap(self, pix: QPixmap):
        if pix and not pix.isNull():
            pix = pix.scaled(
                58, 44,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._viol_thumb.setPixmap(pix)
            self._viol_thumb.show()
            self._viol_thumb.raise_()
        else:
            self._viol_thumb.hide()

    def set_reconnect_visible(self, visible: bool):
        if visible:
            self._reconnect_btn.show()
            self._reconnect_btn.raise_()
            self._reposition_overlays()
        else:
            self._reconnect_btn.hide()


class CameraGridCard(QFrame):
    clicked = pyqtSignal(int)
    reconnect_requested = pyqtSignal(int)
    _shared_banner_pixmap: QPixmap | None = None

    def __init__(self, camera: dict, department_name: str, parent=None, *, tall: bool = False):
        super().__init__(parent)
        self.camera = camera
        self.cam_id = int(camera.get("id") or 0)
        self._department_name = department_name
        self._status = "connecting"
        self._selected = False
        self._tall = tall
        self._style_key = None
        self._status_key = None
        self._pulse_phase = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(950)
        self._pulse_timer.timeout.connect(self._pulse_badge)
        self.setObjectName("cameraOpsCard")
        self.setFixedHeight(290 if tall else 215)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()
        self.set_selected(False)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(7)

        self._banner = BannerWithOverlay()
        self._banner.setFixedHeight(170 if self._tall else 108)
        self._banner.set_image(self._banner_pixmap())
        self._banner.reconnect_clicked.connect(lambda: self.reconnect_requested.emit(self.cam_id))
        lay.addWidget(self._banner)

        # Info row: pill badge + name + status
        top = QHBoxLayout()
        top.setSpacing(7)
        self._cam_code = QLabel(f"CAM {self.cam_id:02d}")
        self._cam_code.setObjectName("cameraCodePill")
        self._cam_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name = QLabel(self.camera.get("name", "Camera"))
        self._name.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 900;")
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._badge = QLabel("Connecting")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._cam_code)
        top.addWidget(self._name, 1)
        top.addWidget(self._badge)
        lay.addLayout(top)

        # Department + URL
        meta = QHBoxLayout()
        meta.setSpacing(6)
        self._department = QLabel(self._department_name or "No department")
        self._department.setObjectName("cameraCardDepartment")
        self._department.setStyleSheet("font-size: 10px; font-weight: 600;")
        self._url = QLabel(self._masked_url(self.camera.get("rtsp_url", "")))
        self._url.setObjectName("cameraCardUrl")
        self._url.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._url.setStyleSheet("font-size: 9px;")
        self._url.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        meta.addWidget(self._department, 1)
        meta.addWidget(self._url)
        lay.addLayout(meta)

        # Metrics
        metrics = QHBoxLayout()
        metrics.setSpacing(5)
        self._fps   = self._metric("FPS",    "--")
        self._ping  = self._metric("PING",   "--")
        self._today = self._metric("EVENTS", "0")
        self._ai    = self._metric("AI",     "Idle")
        metrics.addWidget(self._fps)
        metrics.addWidget(self._ping)
        metrics.addWidget(self._today)
        metrics.addWidget(self._ai)
        lay.addLayout(metrics)

        root.addWidget(body, 1)

    def set_selected(self, selected: bool):
        self._selected = selected
        style_key = (self._status, selected)
        if self._style_key == style_key:
            return
        self._style_key = style_key
        status_color = STATUS_COLORS.get(self._status, WARN)
        palette = {
            "live": {
                "border": C("success"),
                "bg": C("bg_card"),
                "hover": C("success_dim"),
            },
            "offline": {
                "border": C("danger"),
                "bg": C("bg_card"),
                "hover": C("danger_dim"),
            },
            "error": {
                "border": C("danger"),
                "bg": C("bg_card"),
                "hover": C("danger_dim"),
            },
            "connecting": {
                "border": C("warning"),
                "bg": C("bg_card"),
                "hover": C("warning_dim"),
            },
        }.get(self._status, {
            "border": C("border_panel"),
            "bg": C("bg_card"),
            "hover": C("bg_hover"),
        })
        if selected:
            border = f"3px solid {ACCENT}"
            bg = C("accent_subtle")
            top_color = ACCENT
        else:
            border = f"1px solid {palette['border']}"
            bg = palette["bg"]
            top_color = status_color
        self.setStyleSheet(
            "QFrame#cameraOpsCard {"
            f"background: {bg}; border: {border}; border-radius: 10px;"
            f"border-top: {'5px' if selected else '3px'} solid {top_color};"
            "}"
            "QFrame#cameraOpsCard:hover {"
            f"border-color: {ACCENT if selected else palette['border']};"
            f"background: {palette['hover']};"
            "}"
        )

    def set_status(self, status: str, fps: float = 0.0, detections: int = 0, ping_ms=None):
        status_key = (status, round(float(fps or 0)), int(detections or 0), None if ping_ms is None else int(ping_ms))
        if self._status_key == status_key:
            return
        self._status_key = status_key
        self._status = status
        self._style_key = None
        self.set_selected(self._selected)
        self._badge.setText(_status_label(status))
        self._badge.setStyleSheet(self._badge_css(status))
        self._metric_value(self._fps, f"{fps:.0f}" if status == "live" else "--", LIVE if status == "live" else MUTED)
        self._metric_value(self._ping, "--" if ping_ms is None else f"{max(0, int(ping_ms))}", TEXT_2)
        self._metric_value(self._today, str(detections or 0), ACCENT if detections else TEXT_2)
        self._metric_value(self._ai, "Run" if status == "live" else _status_label(status), LIVE if status == "live" else STATUS_COLORS.get(status, MUTED))
        self._banner.set_count(detections or 0)
        offline_like = status in {"offline", "error", "connecting"}
        self._banner.set_offline_visible(offline_like, "OFFLINE" if status in {"offline", "error"} else "NO SIGNAL")
        self._banner.set_reconnect_visible(status in {"offline", "error"})
        if status == "live":
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            if self._pulse_timer.isActive():
                self._pulse_timer.stop()
            self._pulse_phase = 0

    def _pulse_badge(self):
        # Yashirin bo'lsa pulse to'xtaydi — boshqa sahifada CPU sarflanmaydi
        if not self.isVisible():
            self._pulse_timer.stop()
            return
        self._pulse_phase ^= 1
        if self._pulse_phase:
            self._badge.setStyleSheet(
                f"color: {LIVE}; background: transparent;"
                "border: none; padding: 2px 10px; font-size: 10px; font-weight: 900;"
            )
        else:
            self._badge.setStyleSheet(
                f"color: rgba(34,197,94,0.6); background: transparent;"
                "border: none; padding: 2px 10px; font-size: 10px; font-weight: 900;"
            )

    def showEvent(self, event):
        super().showEvent(event)
        if self._status == "live" and not self._pulse_timer.isActive():
            self._pulse_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._pulse_timer.isActive():
            self._pulse_timer.stop()

    def enterEvent(self, event):
        if self._status == "live":
            self._banner.set_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._banner.set_hover(False)
        super().leaveEvent(event)

    def set_preview_frame(self, frame):
        pix = QPixmap()
        if isinstance(frame, QImage):
            pix = QPixmap.fromImage(frame)
        elif isinstance(frame, QPixmap):
            pix = frame
        if not pix.isNull():
            self._banner.set_image(pix)

    def set_last_violation(self, path: str):
        self._banner.set_last_violation(path)

    def set_last_violation_pixmap(self, pix: QPixmap):
        self._banner.set_last_violation_pixmap(pix)

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)
        super().mousePressEvent(event)

    @staticmethod
    def _masked_url(url: str) -> str:
        if not url:
            return "No RTSP"
        safe = url
        if "@" in safe:
            safe = "rtsp://***@" + safe.split("@", 1)[1]
        return safe[:36] + "..." if len(safe) > 39 else safe

    def _banner_pixmap(self) -> QPixmap:
        root = Path(__file__).resolve().parents[3]
        requested = root / "images" / "image.png"
        if requested.exists():
            if CameraGridCard._shared_banner_pixmap is None:
                CameraGridCard._shared_banner_pixmap = QPixmap(str(requested))
            if not CameraGridCard._shared_banner_pixmap.isNull():
                return CameraGridCard._shared_banner_pixmap
        snapshots = sorted((root / "screenshots" / "camera_snapshots").glob("*.jpg"))
        if snapshots:
            index = max(0, self.cam_id - 1) % len(snapshots)
            pix = QPixmap(str(snapshots[index]))
            if not pix.isNull():
                return pix
        fallback = root / "images" / "camera.svg"
        return QPixmap(str(fallback)) if fallback.exists() else QPixmap()

    @staticmethod
    def _badge_css(status: str) -> str:
        color = STATUS_COLORS.get(status, WARN)
        bg_map = {
            "live":       "rgba(34,197,94,0.12)",
            "offline":    "rgba(239,68,68,0.12)",
            "error":      "rgba(239,68,68,0.12)",
            "connecting": "rgba(245,158,11,0.12)",
        }
        bg = bg_map.get(status, "rgba(245,158,11,0.12)")
        return (
            f"color: {color}; background: transparent;"
            "border: none;"
            "padding: 2px 10px; font-size: 10px; font-weight: 900;"
        )

    @staticmethod
    def _metric(title: str, value: str) -> QFrame:
        box = QFrame()
        box.setObjectName("cameraMetricBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(6, 6, 6, 5)
        lay.setSpacing(1)
        val = QLabel(value)
        val.setObjectName("metricValue")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {TEXT_2}; font-size: 13px; font-weight: 900;")
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DIM}; font-size: 8px; font-weight: 900; letter-spacing: 1px;")
        lay.addWidget(val)
        lay.addWidget(lbl)
        return box

    @staticmethod
    def _metric_value(box: QFrame, text: str, color: str):
        val = box.findChild(QLabel, "metricValue")
        if val:
            val.setText(text)
            val.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 900;")


class CameraGridArea(QWidget):
    resized = pyqtSignal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class CameraDetailPanel(QFrame):
    close_requested = pyqtSignal()
    edit_requested = pyqtSignal()
    restart_requested = pyqtSignal(int)
    _stats_loaded  = pyqtSignal(int, int)   # today_count, total_count
    _events_loaded = pyqtSignal(list)        # events list

    def __init__(self, db, cfg, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"
        self._cam_id: int | None = None
        self._cameras: list[dict] = []
        self._current_rtsp = ""
        self._preview_active = False
        self._last_frame: QImage | None = None
        self._events_ts = 0.0
        self._expanded = False
        self._stats_loading  = False
        self._events_loading = False
        self._stats_loaded.connect(self._on_stats_loaded)
        self._events_loaded.connect(self._on_events_loaded)
        self._normal_width = 460
        self._expanded_width = 980
        self._normal_preview_height = 260
        self._expanded_preview_height = 560
        self.setFixedWidth(self._normal_width)
        self.setObjectName("cameraInspector")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("cameraInspectorHeader")
        header.setFixedHeight(64)
        h = QHBoxLayout(header)
        h.setContentsMargins(0, 0, 8, 0)
        h.setSpacing(0)

        # Burgundy-crimson left accent bar
        accent_bar = QWidget()
        accent_bar.setObjectName("cameraInspectorAccent")
        accent_bar.setFixedSize(3, 64)
        h.addWidget(accent_bar)
        h.addSpacing(12)

        # CAM pill — dark red tinted
        self._cam_pill = QLabel("CAM --")
        self._cam_pill.setObjectName("cameraInspectorPill")
        self._cam_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_pill.setFixedHeight(24)
        h.addWidget(self._cam_pill)
        h.addSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title_col.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("Camera")
        self._title.setStyleSheet(
            f"color: {TEXT}; font-size: 14px; font-weight: 900; background: transparent;"
        )
        self._sub = QLabel("--")
        self._sub.setObjectName("cameraInspectorSubtitle")
        title_col.addWidget(self._title)
        title_col.addWidget(self._sub)
        h.addLayout(title_col, 1)

        h.addSpacing(6)

        self._badge = QLabel("Offline")
        self._badge.setFixedHeight(26)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self._badge)
        h.addSpacing(4)

        self._expand_btn = QPushButton()
        self._expand_btn.setObjectName("cameraInspectorIcon")
        self._expand_btn.setFixedSize(28, 28)
        self._expand_btn.setToolTip("Expand inspector")
        self._set_button_icon(self._expand_btn, "expand.svg")
        self._expand_btn.clicked.connect(self.toggle_expanded)
        h.addWidget(self._expand_btn)

        close = QPushButton()
        close.setObjectName("cameraInspectorIcon")
        close.setFixedSize(28, 28)
        self._set_button_icon(close, "x.svg")
        close.clicked.connect(self.close_requested)
        h.addWidget(close)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 16)
        lay.setSpacing(0)

        self._preview_box = QWidget()
        self._preview_box.setObjectName("cameraPreviewBox")
        self._preview_box.setFixedHeight(self._normal_preview_height)
        pv = QVBoxLayout(self._preview_box)
        pv.setContentsMargins(0, 0, 0, 0)
        self._video = VideoLabel()
        self._video.setMinimumHeight(self._normal_preview_height)
        pv.addWidget(self._video)
        lay.addWidget(self._preview_box)

        controls = QWidget()
        controls.setObjectName("cameraInspectorControls")
        controls.setFixedHeight(58)
        c = QHBoxLayout(controls)
        c.setContentsMargins(14, 11, 14, 11)
        c.setSpacing(10)
        self._prev_btn = QPushButton("Preview")
        self._prev_btn.setObjectName("cameraPreviewButton")
        self._prev_btn.setFixedHeight(36)
        self._prev_btn.clicked.connect(self._toggle_preview)

        self._shot_btn = QPushButton("Snapshot")
        self._shot_btn.setObjectName("cameraSnapshotButton")
        self._shot_btn.setFixedHeight(36)
        self._shot_btn.clicked.connect(self._save_snapshot)

        self._zone_btn = QPushButton("Draw Zone")
        self._zone_btn.setObjectName("cameraZoneButton")
        self._zone_btn.setFixedHeight(36)
        self._zone_btn.clicked.connect(self._edit_zone)

        c.addWidget(self._prev_btn, 1)
        c.addWidget(self._shot_btn, 1)
        c.addWidget(self._zone_btn, 1)
        lay.addWidget(controls)

        lay.addWidget(self._section_header("LIVE HEALTH", LIVE))
        health = QWidget()
        health.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(health)
        hl.setContentsMargins(14, 6, 14, 12)
        hl.setSpacing(8)
        self._fps_chip = self._chip("FPS", "--")
        self._ping_chip = self._chip("PING", "--")
        self._status_chip = self._chip("STATUS", "--")
        hl.addWidget(self._fps_chip)
        hl.addWidget(self._ping_chip)
        hl.addWidget(self._status_chip)
        lay.addWidget(health)
        lay.addWidget(self._divider())

        lay.addWidget(self._section_header("TODAY'S ACTIVITY", "#3b82f6"))
        activity = QWidget()
        activity.setStyleSheet("background: transparent;")
        al = QHBoxLayout(activity)
        al.setContentsMargins(14, 6, 14, 12)
        al.setSpacing(8)
        self._today_chip = self._chip("TODAY", "0")
        self._total_chip = self._chip("TOTAL", "0")
        self._uptime_chip = self._chip("HEALTH", "--")
        al.addWidget(self._today_chip)
        al.addWidget(self._total_chip)
        al.addWidget(self._uptime_chip)
        lay.addWidget(activity)
        lay.addWidget(self._divider())

        lay.addWidget(self._section_header("CAMERA CONFIG", ACCENT))
        config = QWidget()
        config.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(config)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self._row_name = self._info_row("Name", "--")
        self._row_loc = self._info_row("Department", "--")
        self._row_url = self._info_row("RTSP", "--")
        self._row_access = self._info_row("Access", "--")
        self._row_last = self._info_row("Last signal", "--")
        cl.addWidget(self._row_name)
        cl.addWidget(self._row_loc)
        cl.addWidget(self._row_url)
        cl.addWidget(self._row_access)
        cl.addWidget(self._row_last)

        btn_wrap = QWidget()
        btn_wrap.setStyleSheet("background: transparent;")
        bwl = QVBoxLayout(btn_wrap)
        bwl.setContentsMargins(14, 12, 14, 4)
        bwl.setSpacing(8)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        copy_rtsp = QPushButton("Copy RTSP")
        copy_rtsp.setFixedHeight(34)
        copy_rtsp.setStyleSheet(self._secondary_button_style())
        copy_rtsp.clicked.connect(self._copy_rtsp)
        restart = QPushButton("Restart Camera")
        restart.setFixedHeight(34)
        restart.setStyleSheet(self._danger_button_style())
        restart.clicked.connect(self._restart_camera)
        actions.addWidget(copy_rtsp)
        actions.addWidget(restart)
        bwl.addLayout(actions)

        edit = QPushButton("Edit Settings")
        edit.setFixedHeight(38)
        edit.setStyleSheet(self._primary_button_style())
        self._set_button_icon(edit, "settings.svg", light=False)
        edit.clicked.connect(self.edit_requested)
        bwl.addWidget(edit)
        cl.addWidget(btn_wrap)
        lay.addWidget(config)
        lay.addWidget(self._divider())

        lay.addWidget(self._section_header("RECENT EVENTS", WARN))
        events = QWidget()
        events.setStyleSheet("background: transparent;")
        self._ev_lay = QVBoxLayout(events)
        self._ev_lay.setContentsMargins(14, 6, 14, 12)
        self._ev_lay.setSpacing(6)
        lay.addWidget(events)
        lay.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def load_camera(self, cam_id: int, cameras: list, dept_fn, status: str, stats: dict):
        self._cam_id = cam_id
        self._cameras = cameras
        self._preview_active = False
        self._prev_btn.setText("Preview")
        cam = next((c for c in cameras if c.get("id") == cam_id), None)
        if not cam:
            return

        name = cam.get("name", f"Camera {cam_id}")
        loc = dept_fn(cam.get("department_id")) or "No department"
        url = cam.get("rtsp_url", "")
        self._current_rtsp = url
        self._cam_pill.setText(f"CAM {cam_id:02d}")
        self._title.setText(name)
        self._sub.setText(loc)
        self._badge.setText(_status_label(status))
        self._badge.setStyleSheet(self._badge_css(status))
        self._set_info(self._row_name, name)
        self._set_info(self._row_loc, loc)
        self._set_info(self._row_url, CameraGridCard._masked_url(url))
        self._set_info(self._row_access, str(cam.get("access_mode", "department")))
        self._set_info(self._row_last, "Waiting for stream")
        self._update_health(stats)
        self._chip_value(self._uptime_chip, "Online" if stats.get("connected") else "Offline",
                         LIVE if stats.get("connected") else OFFLINE)
        if status == "live":
            self._video.show_idle("Preview available")
        elif status == "connecting":
            self._video.show_connecting()
        else:
            self._video.show_error()
        self._last_frame = None
        self._events_ts = 0.0
        self._rebuild_stats()
        self._rebuild_events()

    def toggle_expanded(self):
        self._expanded = not self._expanded
        self.setFixedWidth(self._expanded_width if self._expanded else self._normal_width)
        preview_height = self._expanded_preview_height if self._expanded else self._normal_preview_height
        self._preview_box.setFixedHeight(preview_height)
        self._video.setMinimumHeight(preview_height)
        self._expand_btn.setText("<" if self._expanded else ">")
        self._expand_btn.setToolTip("Collapse inspector" if self._expanded else "Expand inspector")

    def update_status(self, status: str, stats: dict):
        self._badge.setText(_status_label(status))
        self._badge.setStyleSheet(self._badge_css(status))
        self._update_health(stats)
        self._chip_value(self._uptime_chip, "Online" if stats.get("connected") else "Offline",
                         LIVE if stats.get("connected") else OFFLINE)
        if self._preview_active:
            return
        if status == "live":
            self._video.show_idle("Preview available")
        elif status == "connecting":
            self._video.show_connecting()
        elif status in {"offline", "error"}:
            self._video.show_error()

    def set_frame(self, frame):
        if isinstance(frame, QImage):
            self._last_frame = frame.copy()
        if self._preview_active:
            self._video.set_frame(frame)

    def _toggle_preview(self):
        self._preview_active = not self._preview_active
        if self._preview_active:
            self._prev_btn.setText("Stop")
            self._video._has_frame = True
            self._video.clear()
            self._video.setText("Waiting for frame...")
        else:
            self._prev_btn.setText("Preview")
            self._video.show_idle("Preview available")

    def _save_snapshot(self):
        if self._cam_id is None or self._last_frame is None or self._last_frame.isNull():
            self._shot_btn.setText("No frame")
            QTimer.singleShot(1200, lambda: self._shot_btn.setText("Snapshot"))
            return

        root = Path(__file__).resolve().parents[3]
        shot_dir = root / "screenshots" / "camera_snapshots"
        shot_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = shot_dir / f"camera_{self._cam_id}_{ts}.jpg"
        self._shot_btn.setText("Saved" if self._last_frame.save(str(path), "JPEG", 95) else "Save failed")
        QTimer.singleShot(1400, lambda: self._shot_btn.setText("Snapshot"))

    def _copy_rtsp(self):
        if not self._current_rtsp:
            return
        QApplication.clipboard().setText(self._current_rtsp)
        self._set_info(self._row_last, "RTSP copied")
        QTimer.singleShot(1400, lambda: self._set_info(self._row_last, "Now"))

    def _restart_camera(self):
        if self._cam_id is None:
            return
        self._set_info(self._row_last, "Restart requested")
        self.restart_requested.emit(self._cam_id)

    def _edit_zone(self):
        if self._cam_id is None:
            return
        cam = next((c for c in self._cameras if c.get("id") == self._cam_id), None)
        if cam is None:
            return
        if self._last_frame is None or self._last_frame.isNull():
            QMessageBox.information(
                self, "Frame yo'q",
                "Zona chizish uchun avval Preview tugmasini bosing va\n"
                "kamera frameni kutib oling."
            )
            return
        pixmap = QPixmap.fromImage(self._last_frame)
        existing_pts = cam.get("polygon_points", [])
        from app.ui.widgets.polygon_editor import PolygonEditorDialog
        dlg = PolygonEditorDialog(
            pixmap, existing_pts,
            cam.get("name", f"Camera {self._cam_id}"),
            existing_color=cam.get("polygon_color", "#f97316"),
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            pts   = dlg.result_points()
            color = dlg.result_color()
            if pts is not None:
                self.cfg.update_camera(self._cam_id, polygon_points=pts, polygon_color=color)
                self.cfg.save()
                for c in self._cameras:
                    if c.get("id") == self._cam_id:
                        c["polygon_points"] = pts
                        c["polygon_color"]  = color
                        break
                self._zone_btn.setText("Zone Saved ✓")
                QTimer.singleShot(1500, lambda: self._zone_btn.setText("Draw Zone"))

    def _update_health(self, stats: dict):
        fps = float(stats.get("fps") or 0)
        ping = stats.get("ping_ms")
        ok = bool(stats.get("connected", False))
        self._chip_value(self._fps_chip, f"{fps:.0f}", LIVE if ok else MUTED)
        self._chip_value(self._ping_chip, "--" if ping is None else f"{max(0, int(ping))} ms", TEXT_2)
        self._chip_value(self._status_chip, "Online" if ok else "Offline", LIVE if ok else OFFLINE)
        self._set_info(self._row_last, "Now" if ok else "No signal")

    def _rebuild_stats(self):
        if self._stats_loading:
            return
        self._stats_loading = True
        cam = next((c for c in self._cameras if c.get("id") == self._cam_id), None)
        cam_name = cam.get("name") if cam else None

        def _fetch():
            try:
                events = self.db.get_violations(limit=200, camera_name=cam_name)
                today_str = datetime.date.today().isoformat()
                today_count = sum(1 for e in events if str(e.get("created_at", "")).startswith(today_str))
                total_count = len(events)
            except Exception:
                today_count, total_count = 0, 0
            finally:
                self._stats_loading = False
            self._stats_loaded.emit(today_count, total_count)

        threading.Thread(target=_fetch, daemon=True, name="DetailStatsLoad").start()

    def _on_stats_loaded(self, today_count: int, total_count: int):
        self._chip_value(self._today_chip, str(today_count), ACCENT if today_count else MUTED)
        self._chip_value(self._total_chip, str(total_count), TEXT_2)

    def _rebuild_events(self):
        now = time.monotonic()
        if now - self._events_ts < 1.0 or self._events_loading:
            return
        self._events_ts = now
        self._events_loading = True
        cam = next((c for c in self._cameras if c.get("id") == self._cam_id), None)
        cam_name = cam.get("name") if cam else None

        def _fetch():
            try:
                events = self.db.get_violations(limit=6, camera_name=cam_name)
            except Exception:
                events = []
            finally:
                self._events_loading = False
            self._events_loaded.emit(events)

        threading.Thread(target=_fetch, daemon=True, name="DetailEventsLoad").start()

    def _on_events_loaded(self, events: list):
        while self._ev_lay.count():
            item = self._ev_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not events:
            empty = QLabel("No recent events for this camera")
            empty.setStyleSheet(f"color: {DIM}; font-size: 11px; padding: 8px 0;")
            self._ev_lay.addWidget(empty)
            return

        for event in events:
            row = QWidget()
            row.setObjectName("cameraEventRow")
            row.setFixedHeight(36)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 0, 12, 0)
            rl.setSpacing(10)
            badge = QLabel("⚠ NO HELMET")
            badge.setStyleSheet(
                f"color: {OFFLINE}; font-size: 10px; font-weight: 800;"
            )
            ts = QLabel(str(event.get("created_at", ""))[-8:] or "--")
            ts.setObjectName("cameraEventTime")
            ts.setStyleSheet("font-size: 10px; font-weight: 700;")
            rl.addWidget(badge, 1)
            rl.addWidget(ts)
            self._ev_lay.addWidget(row)

    @staticmethod
    def _ctrl_btn(self, text: str, icon_name: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        btn.setStyleSheet(
            f"QPushButton {{ background: {C('bg_panel_alt')};"
            f"color: {TEXT_2}; border: 1px solid {BORDER}; border-radius: 6px;"
            "font-size: 11px; font-weight: 800; padding: 0 14px; }"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
        )
        if icon_name:
            self._set_button_icon(btn, icon_name)
        return btn

    def _set_button_icon(self, btn: QPushButton, icon_name: str, *, light: bool = True):
        path = self._icon_dir / icon_name
        if path.exists():
            btn.setIcon(QIcon(str(path)))
            btn.setIconSize(QSize(14, 14))

    @staticmethod
    def _chip(title: str, value: str) -> QFrame:
        box = QFrame()
        box.setObjectName("cameraInspectorChip")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 11, 10, 9)
        lay.setSpacing(3)
        val = QLabel(value)
        val.setObjectName("chipValue")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {TEXT_2}; font-size: 19px; font-weight: 900;")
        lbl = QLabel(title)
        lbl.setObjectName("cameraChipLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 8px; font-weight: 900; letter-spacing: 1px;")
        lay.addWidget(val)
        lay.addWidget(lbl)
        return box

    @staticmethod
    def _chip_value(chip: QFrame, text: str, color: str):
        val = chip.findChild(QLabel, "chipValue")
        if val:
            val.setText(text)
            val.setStyleSheet(f"color: {color}; font-size: 19px; font-weight: 900;")

    @staticmethod
    def _info_row(key: str, value: str) -> QWidget:
        row = QWidget()
        row.setObjectName("cameraInfoRow")
        row.setFixedHeight(36)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(14)
        k = QLabel(key)
        k.setObjectName("cameraInfoKey")
        k.setFixedWidth(82)
        k.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        k.setStyleSheet("font-size: 10px; font-weight: 700;")
        v = QLabel(value)
        v.setObjectName("infoValue")
        v.setStyleSheet(f"color: {TEXT}; font-size: 11px; font-weight: 600;")
        v.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(k)
        lay.addWidget(v, 1)
        return row

    @staticmethod
    def _set_info(row: QWidget, text: str):
        label = row.findChild(QLabel, "infoValue")
        if label:
            label.setText(text or "--")

    @staticmethod
    def _section_header(text: str, color: str = "") -> QWidget:
        w = QWidget()
        w.setObjectName("cameraSectionHeader")
        w.setFixedHeight(32)
        color = color or ACCENT
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(7)

        dot = QLabel("◆")
        dot.setFixedWidth(10)
        dot.setStyleSheet(
            f"color: {color}; font-size: 7px; background: transparent; border: none;"
        )
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {color}; font-size: 9px; font-weight: 900;"
            "letter-spacing: 1.5px; background: transparent; border: none;"
        )
        lay.addWidget(dot)
        lay.addWidget(lbl, 1)
        return w

    @staticmethod
    def _divider() -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C('border_light')}; border: none;")
        return sep

    @staticmethod
    def _badge_css(status: str) -> str:
        color = STATUS_COLORS.get(status, WARN)
        return (
            f"color: {color}; background: {C('bg_panel_alt')};"
            f"border: 1px solid {color}; border-radius: 7px;"
            "padding: 3px 9px; font-size: 10px; font-weight: 900;"
        )

    @staticmethod
    def _primary_button_style() -> str:
        return (
            f"QPushButton {{ background: {ACCENT}; color: {C('text_on_accent')}; border: none;"
            "border-radius: 8px; font-size: 12px; font-weight: 900; }"
            f"QPushButton:hover {{ background: {C('accent_hover')}; }}"
        )

    @staticmethod
    def _secondary_button_style() -> str:
        return (
            f"QPushButton {{ background: {C('success_dim_2')}; color: {TEXT_2};"
            f"border: 1px solid {BORDER}; border-radius: 8px;"
            "font-size: 11px; font-weight: 800; }"
            f"QPushButton:hover {{ background: {C('bg_hover')}; color: {TEXT};"
            f"border-color: {C('border_hover')}; }}"
        )

    @staticmethod
    def _danger_button_style() -> str:
        return (
            f"QPushButton {{ background: {C('danger_dim_2')}; color: {OFFLINE};"
            f"border: 1px solid {OFFLINE}; border-radius: 8px;"
            "font-size: 11px; font-weight: 800; }"
            f"QPushButton:hover {{ background: {C('danger_dim')}; color: {TEXT};"
            f"border-color: {OFFLINE}; }}"
        )

    @staticmethod
    def _icon_button_style() -> str:
        return (
            "QPushButton { background: transparent;"
            f"color: {MUTED}; border: none; border-radius: 6px;"
            "font-size: 13px; font-weight: 900; }"
            f"QPushButton:hover {{ background: {C('danger_dim_2')}; color: {OFFLINE}; }}"
        )


class SidebarResizeHandle(QWidget):
    """Thin drag handle that resizes a side panel."""

    def __init__(
        self,
        target: QWidget,
        parent=None,
        *,
        reverse: bool = False,
        min_width: int = 180,
        max_width: int = 360,
    ):
        super().__init__(parent)
        self._target = target
        self._reverse = reverse
        self._dragging = False
        self._start_x = 0
        self._start_width = 0
        self._min_width = min_width
        self._max_width = max_width
        self.setFixedWidth(6)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setMouseTracking(True)
        self.setStyleSheet(
            f"QWidget {{ background: {BORDER_SOFT}; border-left: 1px solid {BORDER}; border-right: 1px solid #07111a; }}"
            f"QWidget:hover {{ background: {ACCENT}; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_x = event.globalPosition().toPoint().x()
            self._start_width = self._target.width()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            dx = event.globalPosition().toPoint().x() - self._start_x
            width = self._start_width - dx if self._reverse else self._start_width + dx
            width = max(self._min_width, min(self._max_width, width))
            self._target.setFixedWidth(width)
            owner = self.parent()
            if owner and hasattr(owner, "_fit_side_panels"):
                owner._fit_side_panels()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CamerasPage(QWidget):
    add_camera_requested = pyqtSignal()
    departments_changed = pyqtSignal()
    reconnect_requested = pyqtSignal(int)

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = config_manager
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"
        self._cameras: list[dict] = []
        self._cards: dict[int, CameraGridCard] = {}
        self._status: dict[int, str] = {}
        self._stats: dict[int, dict] = {}
        self._latest_frames: dict[int, QImage] = {}
        self._dept_badges: dict[int, QLabel] = {}
        self._selected: int | None = None
        self._filter = "all"
        self._grid_columns = max(3, self.cfg.get("cameras_grid_columns", 4) if self.cfg else 4)
        self._search_text = ""
        self._sort_mode = "default"
        self._grid_render_timer = QTimer(self)
        self._grid_render_timer.setSingleShot(True)
        self._grid_render_timer.timeout.connect(self._render_grid)
        self._build_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_side_panels()
        if hasattr(self, "_grid_render_timer") and not self._grid_render_timer.isActive():
            self._grid_render_timer.start(80)

    def eventFilter(self, obj, event):
        if (
            hasattr(self, "_grid_scroll")
            and obj is self._grid_scroll.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._rerender_grid_later()
        return super().eventFilter(obj, event)

    def _fit_side_panels(self):
        if not hasattr(self, "_sidebar") or not hasattr(self, "_detail"):
            return

        total = max(900, self.width())
        max_sidebar = min(360, max(180, total // 4))
        sidebar_w = min(max(self._sidebar.width(), 180), max_sidebar)
        self._sidebar.setFixedWidth(sidebar_w)

        if self._detail.isVisible():
            reserve_for_grid = 430
            handles = 12
            max_detail = max(360, total - sidebar_w - reserve_for_grid - handles)
            min_detail = min(420, max_detail)
            detail_w = min(max(self._detail.width(), min_detail), max_detail)
            self._detail.setFixedWidth(detail_w)

    def _build_ui(self):
        self.setObjectName("camerasPage")
        self.setStyleSheet(f"QWidget#camerasPage {{ background: {C('bg_main')}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._make_header())

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._sidebar = self._make_sidebar()
        row.addWidget(self._sidebar)
        self._sidebar_handle = SidebarResizeHandle(self._sidebar, parent=self)
        row.addWidget(self._sidebar_handle)
        row.addWidget(self._make_grid_area(), 1)
        self._detail = CameraDetailPanel(self.db, self.cfg)
        self._detail.close_requested.connect(self._close_detail)
        self._detail.edit_requested.connect(self.add_camera_requested)
        self._detail.restart_requested.connect(self._on_reconnect_requested)
        self._detail.hide()
        self._detail_handle = SidebarResizeHandle(self._detail, parent=self, reverse=True, min_width=420, max_width=1320)
        self._detail_handle.hide()
        row.addWidget(self._detail_handle)
        row.addWidget(self._detail)
        root.addWidget(body, 1)

    def _make_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("cameraOpsHeader")
        header.setFixedHeight(64)
        header.setStyleSheet(
            "QFrame#cameraOpsHeader {"
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {C('bg_header_a')}, stop:0.48 {C('bg_header_b')}, stop:1 {C('bg_panel')});"
            f"border-bottom: 1px solid {BORDER};"
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(header)
        lay.setContentsMargins(14, 0, 20, 0)
        lay.setSpacing(10)

        menu_btn = QPushButton("☰")
        menu_btn.setFixedSize(36, 36)
        menu_btn.setToolTip("Toggle sidebar")
        menu_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_2};"
            "border: 1px solid transparent; border-radius: 8px; font-size: 16px; }"
            f"QPushButton:hover {{ background: {C('bg_hover')}; color: {ACCENT};"
            f"border-color: {BORDER}; }}"
        )
        menu_btn.clicked.connect(self._toggle_sidebar)
        lay.addWidget(menu_btn)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("Camera Operations")
        title.setStyleSheet(f"color: {TEXT}; font-size: 17px; font-weight: 900;")
        sub = QLabel("Fleet health, access roster status, and on-demand diagnostics")
        sub.setStyleSheet(f"color: {MUTED}; font-size: 11px; font-weight: 600;")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        lay.addLayout(title_col, 1)

        self._hdr_total = self._header_chip("0 total", C("text_link"))
        self._hdr_live = self._header_chip("0 live", LIVE)
        self._hdr_offline = self._header_chip("0 off", OFFLINE)
        self._hdr_updated = self._header_chip("Updated --", TEXT_2)
        lay.addWidget(self._hdr_total)
        lay.addWidget(self._hdr_live)
        lay.addWidget(self._hdr_offline)
        lay.addWidget(self._hdr_updated)
        lay.addSpacing(8)

        add = QPushButton("+ Add Camera")
        add.setFixedSize(126, 34)
        add.setStyleSheet(self._primary_button_style())
        self._set_button_icon(add, "plus.svg", light=False)
        add.clicked.connect(self.add_camera_requested)
        lay.addWidget(add)
        return header

    def _make_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("cameraOpsSidebar")
        sidebar.setFixedWidth(254)
        sidebar.setStyleSheet(
            "QFrame#cameraOpsSidebar {"
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {C('bg_sidebar')}, stop:0.58 {C('bg_sidebar')}, stop:1 {C('bg_panel_alt')});"
            f"border-right: 1px solid {BORDER};"
            "}"
            "QFrame#cameraOpsSidebar QLabel { background: transparent; border: none; }"
        )
        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        view_wrap = QWidget()
        view_wrap.setStyleSheet("background: transparent;")
        vw = QVBoxLayout(view_wrap)
        vw.setContentsMargins(12, 8, 12, 12)
        vw.setSpacing(7)
        view_sec = QLabel("VIEW")
        view_sec.setFixedHeight(22)
        view_sec.setStyleSheet(
            f"color: {TEXT_2}; font-size: 9px; font-weight: 900; letter-spacing: 1px;"
        )
        vw.addWidget(view_sec)

        self._fbtn: dict[str, QPushButton] = {}
        self._filter_labels = {
            "all": "All Cameras",
            "live": "Live",
            "offline": "Offline / Error",
        }
        for key, label, icon_name in [
            ("all", "All Cameras", "camera.svg"),
            ("live", "Live", "wifi.svg"),
            ("offline", "Offline / Error", "alerts.svg"),
        ]:
            btn = QPushButton(f"  {label}")
            btn.setFixedHeight(44)
            btn.setCheckable(True)
            btn.setStyleSheet(self._filter_style(False))
            icon_path = self._icon_dir / icon_name
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(15, 15))
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            self._fbtn[key] = btn
            vw.addWidget(btn)

        outer.addWidget(view_wrap)
        outer.addWidget(self._hsep())

        dept_wrap = QWidget()
        dept_wrap.setStyleSheet("background: transparent;")
        dw = QVBoxLayout(dept_wrap)
        dw.setContentsMargins(12, 14, 12, 8)
        dw.setSpacing(8)

        dept_hdr = QHBoxLayout()
        dept_hdr.setSpacing(6)
        dep_lbl = QLabel("DEPARTMENTS")
        dep_lbl.setStyleSheet(
            f"color: {TEXT_2}; font-size: 9px; font-weight: 900; letter-spacing: 1px;"
        )
        dept_hdr.addWidget(dep_lbl, 1)
        add_dep = QPushButton()
        add_dep.setFixedSize(22, 22)
        add_dep.setToolTip("Add department")
        add_dep.setStyleSheet(
            f"QPushButton {{ background: {C('bg_panel_alt')}; color: {TEXT_2};"
            f"border: 1px solid {BORDER}; border-radius: 6px; font-size: 14px; font-weight: 900; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
        )
        plus_icon = self._icon_dir / "plus.svg"
        if plus_icon.exists():
            add_dep.setIcon(QIcon(str(plus_icon)))
            add_dep.setIconSize(QSize(12, 12))
        else:
            add_dep.setText("+")
        add_dep.clicked.connect(self._add_department)
        dept_hdr.addWidget(add_dep)
        dw.addLayout(dept_hdr)

        self._loc_lay = QVBoxLayout()
        self._loc_lay.setSpacing(8)
        dw.addLayout(self._loc_lay)
        outer.addWidget(dept_wrap)
        outer.addStretch()

        ops_bar = QWidget()
        ops_bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {C('bg_panel')}, stop:1 {C('bg_sidebar')});"
            f"border-top: 1px solid {BORDER};"
        )
        ob = QVBoxLayout(ops_bar)
        ob.setContentsMargins(12, 12, 12, 16)
        ob.setSpacing(8)
        ops_hdr = QLabel("OPERATIONS")
        ops_hdr.setStyleSheet(
            f"color: {TEXT_2}; font-size: 9px; font-weight: 900;"
            "letter-spacing: 1px; background: transparent; border: none;"
        )
        ob.addWidget(ops_hdr)
        self._ops_health = self._ops_row("Online health", "0%", LIVE)
        self._ops_events = self._ops_row("Today events", "0", ACCENT)
        self._ops_risk = self._ops_row("Top activity", "--", WARN)
        self._ops_ai = self._ops_row("AI model", "Off", C("text_link"))
        ob.addWidget(self._ops_health)
        ob.addWidget(self._ops_events)
        ob.addWidget(self._ops_risk)
        ob.addWidget(self._ops_ai)
        outer.addWidget(ops_bar)

        return sidebar

    def _make_grid_area(self) -> QWidget:
        area = CameraGridArea()
        area.resized.connect(self._rerender_grid_later)
        area.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(area)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(10)

        # ── Top search + sort bar ─────────────────────────────────────────
        search_bar = QWidget()
        search_bar.setFixedHeight(48)
        search_bar.setStyleSheet(
            f"QWidget {{ background: {C('bg_panel')};"
            f"border: 1px solid {C('border_light')}; border-radius: 10px; }}"
            "QLabel { background: transparent; border: none; }"
        )
        sb = QHBoxLayout(search_bar)
        sb.setContentsMargins(12, 0, 10, 0)
        sb.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search camera...")
        self._search.setFixedHeight(34)
        self._search.setMinimumWidth(80)
        self._search.setMaximumWidth(200)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {C('input_bg')}; color: {TEXT};"
            f"border: 1px solid {C('input_border')}; border-radius: 8px;"
            "padding: 0 10px; font-size: 12px; font-weight: 600; }"
            f"QLineEdit:hover {{ border-color: {C('input_border_hov')}; }}"
            f"QLineEdit:focus {{ border-color: {ACCENT}; background: {C('input_bg_focus')}; }}"
        )
        search_icon = self._icon_dir / "search.svg"
        if search_icon.exists():
            self._search.addAction(QIcon(str(search_icon)), QLineEdit.ActionPosition.LeadingPosition)
        self._search.textChanged.connect(self.set_search_text)
        sb.addWidget(self._search)

        _vsep = QFrame()
        _vsep.setFixedSize(1, 24)
        _vsep.setStyleSheet(f"background: {BORDER_SOFT}; border: none;")
        sb.addWidget(_vsep)

        sort_lbl = QLabel("Sort:")
        sort_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px; font-weight: 700;")
        sb.addWidget(sort_lbl)
        self._sort_btns: dict[str, QPushButton] = {}
        for key, label in [("default", "Default"), ("events", "Events"), ("offline", "Health"), ("az", "A–Z")]:
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.setCheckable(True)
            btn.setStyleSheet(self._sort_chip_style(key == "default"))
            btn.clicked.connect(lambda _, k=key: self._set_sort(k))
            self._sort_btns[key] = btn
            sb.addWidget(btn)

        sb.addStretch()

        self._updated_lbl = QLabel()  # kept for _render_grid update; not shown in toolbar

        _vsep2 = QFrame()
        _vsep2.setFixedSize(1, 24)
        _vsep2.setStyleSheet(f"background: {BORDER_SOFT}; border: none;")
        sb.addWidget(_vsep2)

        self._col_btns: dict[int, QPushButton] = {}
        _layout_icons = {
            3: "layout-3.svg",
            4: "layout-4x2.svg",
            5: "grid-3.svg",
            6: "grid-4.svg",
        }
        for col in (3, 4, 5, 6):
            btn = QPushButton()
            btn.setFixedSize(30, 28)
            btn.setCheckable(True)
            btn.setToolTip(f"{col} columns")
            icon_path = self._icon_dir / _layout_icons[col]
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(16, 16))
            else:
                btn.setText(f"{col}")
            btn.clicked.connect(lambda _, c=col: self._set_grid_columns(c))
            self._col_btns[col] = btn
            sb.addWidget(btn)
        self._refresh_column_buttons()
        lay.addWidget(search_bar)

        # ── Fleet status bar (one segment per camera) ─────────────────────
        self._fleet_bar = FleetStatusBar()
        lay.addWidget(self._fleet_bar)

        # ── Section title strip ───────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._grid_title = QLabel("All Cameras")
        self._grid_title.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 900;")
        self._count_lbl = QLabel("0")
        self._count_lbl.setFixedHeight(22)
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count_lbl.setStyleSheet(
            f"color: {C('text_link')}; background: {C('info_dim')};"
            f"border: 1px solid {C('border_light')};"
            "border-radius: 6px; font-size: 10px; font-weight: 900; padding: 0 8px;"
        )
        self._hint_lbl = QLabel("Showing 0 of 0 cameras")
        self._hint_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px; font-weight: 600;")
        title_row.addWidget(self._grid_title)
        title_row.addWidget(self._count_lbl)
        title_row.addStretch()
        title_row.addWidget(self._hint_lbl)
        lay.addLayout(title_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._grid_scroll = scroll
        self._grid_body = QWidget()
        self._grid_body.setStyleSheet("background: transparent;")
        self._grid_lay = QGridLayout(self._grid_body)
        self._grid_lay.setContentsMargins(0, 0, 0, 0)
        self._grid_lay.setHorizontalSpacing(12)
        self._grid_lay.setVerticalSpacing(12)
        scroll.setWidget(self._grid_body)
        scroll.viewport().installEventFilter(self)
        lay.addWidget(scroll, 1)

        self._foot = QLabel("")
        self._foot.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        lay.addWidget(self._foot, 0, Qt.AlignmentFlag.AlignRight)
        return area

    def _toggle_sidebar(self):
        visible = self._sidebar.isVisible()
        self._sidebar.setVisible(not visible)
        self._sidebar_handle.setVisible(not visible)
        self._rerender_grid_later()

    def setup_cameras(self, cameras: list):
        self._cameras = list(cameras)
        self._status = {c.get("id"): "connecting" for c in cameras}
        self._stats.clear()
        self._latest_frames.clear()
        self._cards.clear()
        self._selected = None
        self._detail.hide()
        self._detail_handle.hide()
        self._rebuild_locations()
        self._render_grid()
        self._update_counts()
        self._set_filter("all")
        if self._cameras:
            first_id = self._cameras[0].get("id")
            if first_id is not None:
                QTimer.singleShot(0, lambda cid=int(first_id): self._select_camera(cid))

    def set_search_text(self, text: str):
        self._search_text = (text or "").strip().lower()
        if hasattr(self, "_search") and self._search.text().strip().lower() != self._search_text:
            self._search.setText(text)
        self._render_grid()

    def update_frame(self, cam_id: int, frame):
        if isinstance(frame, QImage):
            if cam_id not in self._latest_frames:
                self._latest_frames[cam_id] = frame.copy()
        if cam_id == self._selected:
            self._detail.set_frame(frame)

    def on_stats(self, cam_id: int, stats: dict):
        self._stats[cam_id] = dict(stats)
        new_status = "live" if stats.get("connected", False) else "offline"
        old_status = self._status.get(cam_id)
        if old_status != new_status:
            self._status[cam_id] = new_status
            self._update_counts()
            if self._filter in {"live", "offline"}:
                self._render_grid()
        card = self._cards.get(cam_id)
        if card:
            card.set_status(new_status, stats.get("fps", 0.0), stats.get("today_count", 0), stats.get("ping_ms"))
        if cam_id == self._selected:
            self._detail.update_status(new_status, stats)
        self._update_operations_summary()

    def on_status(self, cam_id: int, text: str):
        text_l = (text or "").lower()
        if "ulangan" in text_l:
            status = "live"
        elif "qayta" in text_l:
            status = "offline"
        elif "ulanmoqda" in text_l or "yuklanmoqda" in text_l:
            status = "connecting"
        else:
            return

        old_status = self._status.get(cam_id)
        if old_status == status:
            return
        self._status[cam_id] = status
        card = self._cards.get(cam_id)
        if card:
            stats = self._stats.get(cam_id, {})
            card.set_status(status, stats.get("fps", 0.0), stats.get("today_count", 0), stats.get("ping_ms"))
        if cam_id == self._selected:
            self._detail.update_status(status, self._stats.get(cam_id, {}))
        self._update_counts()

    def on_error(self, cam_id: int, _msg: str):
        if self._status.get(cam_id) == "error":
            return
        self._status[cam_id] = "error"
        card = self._cards.get(cam_id)
        if card:
            card.set_status("error")
        if cam_id == self._selected:
            self._detail.update_status("error", {})
        self._update_counts()

    def on_model_loaded(self, cam_id: int):
        card = self._cards.get(cam_id)
        if card:
            stats = self._stats.get(cam_id, {})
            card.set_status(self._status.get(cam_id, "live"), stats.get("fps", 0.0), stats.get("today_count", 0), stats.get("ping_ms"))

    def on_violation(self, data: dict):
        if self._selected is not None and self._detail.isVisible():
            QTimer.singleShot(100, self._detail._rebuild_events)
            QTimer.singleShot(200, self._detail._rebuild_stats)
        cam_name = data.get("camera_name", "")
        if not cam_name:
            return
        cam = next((c for c in self._cameras if c.get("name") == cam_name), None)
        if not cam:
            return
        card = self._cards.get(cam.get("id"))
        if not card:
            return
        # _crop_pixmap mavjud bo'lsa diskdan o'qimaydi (main thread bloklanmaydi)
        pix = data.get("_crop_pixmap")
        if pix is not None and not pix.isNull():
            card.set_last_violation_pixmap(pix)
        else:
            crop_path = data.get("crop_path") or data.get("violation_image") or data.get("image_path") or ""
            if crop_path:
                card.set_last_violation(str(crop_path))

    def _set_filter(self, key: str):
        self._filter = key
        for k, btn in self._fbtn.items():
            active = k == key
            btn.setChecked(active)
            btn.setStyleSheet(self._filter_style(active))
        titles = {"all": "All Cameras", "live": "Live Cameras", "offline": "Offline / Error"}
        if key.startswith("dep:"):
            dep_id = key.split(":", 1)[1]
            dep = self.cfg.get_department_by_id(int(dep_id)) if dep_id.isdigit() and self.cfg else None
            self._grid_title.setText(dep.get("name", "Department") if dep else "Department")
        else:
            self._grid_title.setText(titles.get(key, "Cameras"))
        self._rebuild_locations()
        self._render_grid()

    def _matches(self, cam: dict) -> bool:
        cid = cam.get("id")
        if self._search_text:
            haystack = " ".join([
                str(cid or ""),
                str(cam.get("name", "")),
                self._dept_name(cam.get("department_id")),
                str(cam.get("rtsp_url", "")),
            ]).lower()
            if self._search_text not in haystack:
                return False
        status = self._status.get(cid, "connecting")
        if self._filter == "live":
            return status == "live"
        if self._filter == "offline":
            return status in {"offline", "error", "connecting"}
        if self._filter.startswith("dep:"):
            return str(cam.get("department_id")) == self._filter.split(":", 1)[1]
        return True

    def _render_grid(self):
        while self._grid_lay.count():
            item = self._grid_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for c in range(6):
            self._grid_lay.setColumnStretch(c, 0)
        for r in range(20):
            self._grid_lay.setRowStretch(r, 0)
        self._cards.clear()
        visible = sorted(
            [c for c in self._cameras if self._matches(c)],
            key=self._card_sort_key,
        )
        n = len(visible)
        avail_w = self._grid_scroll.viewport().width()
        if avail_w < 50:
            avail_w = max(300, self.width() - 260)
        min_card_w = 200
        auto_cols = max(1, avail_w // min_card_w)
        cols = max(1, min(self._grid_columns, auto_cols, n if n else 1))
        self._grid_body.setMinimumWidth(0)
        for i, cam in enumerate(visible):
            cid = cam.get("id")
            card = CameraGridCard(cam, self._dept_name(cam.get("department_id")))
            card.clicked.connect(self._select_camera)
            card.reconnect_requested.connect(self._on_reconnect_requested)
            latest = self._latest_frames.get(cid)
            if latest is not None and not (self._icon_dir / "image.png").exists():
                card.set_preview_frame(latest)
            stats = self._stats.get(cid, {})
            card.set_status(
                self._status.get(cid, "connecting"),
                stats.get("fps", 0.0),
                stats.get("today_count", 0),
                stats.get("ping_ms"),
            )
            card.set_selected(cid == self._selected)
            self._cards[cid] = card
            self._grid_lay.addWidget(card, i // cols, i % cols)
        for c in range(max(1, cols)):
            self._grid_lay.setColumnStretch(c, 1)
        rows = (n + cols - 1) // cols if n else 0
        if rows:
            self._grid_lay.addItem(
                QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding),
                rows,
                0,
                1,
                cols,
            )
            self._grid_lay.setRowStretch(rows, 1)
        self._count_lbl.setText(str(n))
        visible_text = f"Showing {n} of {len(self._cameras)} cameras"
        self._hint_lbl.setText(visible_text)
        self._foot.setText(visible_text)
        if hasattr(self, "_updated_lbl"):
            updated = datetime.datetime.now().strftime("Updated %H:%M:%S")
            self._updated_lbl.setText(f"Last {updated}")
            if hasattr(self, "_hdr_updated"):
                self._hdr_updated.setText(updated)

    def _rerender_grid_later(self):
        if hasattr(self, "_grid_render_timer") and not self._grid_render_timer.isActive():
            self._grid_render_timer.start(150)

    def _set_grid_columns(self, columns: int):
        self._grid_columns = max(3, min(6, int(columns)))
        if self.cfg:
            self.cfg.set("cameras_grid_columns", self._grid_columns)
            self.cfg.save()
        self._refresh_column_buttons()
        self._render_grid()

    def _refresh_column_buttons(self):
        if not hasattr(self, "_col_btns"):
            return
        for col, btn in self._col_btns.items():
            active = col == self._grid_columns
            btn.setChecked(active)
            btn.setStyleSheet(self._column_button_style(active))

    def _select_camera(self, cam_id: int):
        self._selected = cam_id
        for cid, card in self._cards.items():
            card.set_selected(cid == cam_id)
        self._detail.load_camera(
            cam_id,
            self._cameras,
            self._dept_name,
            self._status.get(cam_id, "connecting"),
            self._stats.get(cam_id, {}),
        )
        self._detail_handle.show()
        self._detail.show()
        self._fit_side_panels()
        self._rerender_grid_later()

    def _close_detail(self):
        self._detail.hide()
        self._detail_handle.hide()
        self._selected = None
        for card in self._cards.values():
            card.set_selected(False)
        self._rerender_grid_later()

    def _rebuild_locations(self):
        self._dept_badges.clear()
        while self._loc_lay.count():
            item = self._loc_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        building_icon = self._icon_dir / "building.svg"
        for dep in (self.cfg.get_departments() if self.cfg else []):
            dep_id = dep.get("id")
            total = sum(1 for c in self._cameras if c.get("department_id") == dep_id)
            live = sum(1 for c in self._cameras if c.get("department_id") == dep_id and self._status.get(c.get("id")) == "live")
            active = self._filter == f"dep:{dep_id}"

            row = QWidget()
            row.setFixedHeight(48)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setObjectName("deptRow")
            active_bg = C("accent_subtle") if active else C("bg_panel")
            active_border = (
                f"border: 1px solid {C('border_accent')}; border-left: 3px solid {ACCENT}; border-radius: 10px;"
                if active
                else f"border: 1px solid {C('border_light')}; border-left: 3px solid transparent; border-radius: 10px;"
            )
            row.setStyleSheet(
                f"QWidget#deptRow {{ background: {active_bg}; {active_border} }}"
                f"QWidget#deptRow:hover {{ background: {C('bg_hover')};"
                f"border-color: {BORDER}; border-left-color: {BORDER_STRONG}; }}"
                "QLabel { background: transparent; border: none; }"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 0, 10, 0)
            rl.setSpacing(8)

            icon_lbl = QLabel()
            icon_lbl.setFixedSize(14, 14)
            if building_icon.exists():
                pix = QPixmap(str(building_icon))
                if not pix.isNull():
                    icon_lbl.setPixmap(pix.scaled(
                        14, 14,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    ))
            rl.addWidget(icon_lbl)

            text_col = QVBoxLayout()
            text_col.setSpacing(4)
            name_lbl = QLabel(dep.get("name", "Department"))
            name_lbl.setStyleSheet(
                f"color: {ACCENT if active else TEXT}; font-size: 12px; font-weight: 800;"
            )
            progress = QWidget()
            progress.setFixedHeight(4)
            pct = 0 if total <= 0 else max(0, min(100, int(live * 100 / total)))
            progress.setStyleSheet(
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {LIVE}, stop:{pct / 100:.2f} {LIVE},"
                f"stop:{pct / 100:.2f} {C('border_light')}, stop:1 {C('border_light')});"
                "border: none; border-radius: 2px;"
            )
            text_col.addWidget(name_lbl)
            text_col.addWidget(progress)
            rl.addLayout(text_col, 1)

            badge = DeptProgressBadge(live, total)
            rl.addWidget(badge)
            if dep_id is not None:
                self._dept_badges[int(dep_id)] = badge

            row.mousePressEvent = lambda _, d=dep_id: self._set_filter(f"dep:{d}")
            self._loc_lay.addWidget(row)

    def _add_department(self):
        name, ok = QInputDialog.getText(self, "Yangi bo'lim", "Bo'lim nomi:")
        if not ok or not name.strip():
            return
        try:
            self.cfg.add_department(name.strip())
            self.cfg.save()
        except ValueError as exc:
            QMessageBox.warning(self, "Xatolik", str(exc))
            return
        self._rebuild_locations()
        self.departments_changed.emit()

    def _update_counts(self):
        total = len(self._cameras)
        live = sum(1 for c in self._cameras if self._status.get(c.get("id")) == "live")
        offline = sum(1 for c in self._cameras if self._status.get(c.get("id")) in {"offline", "error"})
        warn = sum(1 for c in self._cameras if self._status.get(c.get("id")) == "connecting")
        if hasattr(self, "_hdr_total"):
            self._hdr_total.setText(f"{total} total")
            self._hdr_live.setText(f"{live} live")
            self._hdr_offline.setText(f"{offline + warn} off")
        if hasattr(self, "_fleet_bar"):
            self._fleet_bar.set_segments(
                [self._status.get(c.get("id"), "connecting") for c in self._cameras]
            )
        if hasattr(self, "_fbtn"):
            counts = {
                "all": total,
                "live": live,
                "offline": offline + warn,
            }
            for key, btn in self._fbtn.items():
                base = self._filter_labels.get(key, btn.text().strip())
                btn.setText(f"  {base}   {counts.get(key, 0)}")
        self._update_department_badges()
        self._update_operations_summary()

    def _update_operations_summary(self):
        if not hasattr(self, "_ops_health"):
            return
        total = len(self._cameras)
        live = sum(1 for c in self._cameras if self._status.get(c.get("id")) == "live")
        health = 0 if total <= 0 else round(live * 100 / total)
        today_events = sum(int(s.get("today_count", 0) or 0) for s in self._stats.values())
        top_cam = "--"
        if self._stats:
            top_id, top_stats = max(
                self._stats.items(),
                key=lambda item: int(item[1].get("today_count", 0) or 0),
            )
            top_count = int(top_stats.get("today_count", 0) or 0)
            if top_count:
                cam = next((c for c in self._cameras if c.get("id") == top_id), None)
                fallback_name = f"CAM {int(top_id):02d}" if isinstance(top_id, int) else "Camera"
                cam_name = cam.get("name", fallback_name) if cam else fallback_name
                top_cam = f"{cam_name}  {top_count}"
        ai_on = bool(self.cfg and self.cfg.get("ai_model_enabled", False))
        self._ops_row_set(self._ops_health, f"{health}%", LIVE if health >= 70 else WARN if health >= 40 else OFFLINE)
        self._ops_row_set(self._ops_events, str(today_events), ACCENT if today_events else MUTED)
        self._ops_row_set(self._ops_risk, top_cam, WARN if top_cam != "--" else MUTED)
        self._ops_row_set(self._ops_ai, "On" if ai_on else "Off", LIVE if ai_on else MUTED)

    def _update_department_badges(self):
        if not self._dept_badges:
            return
        for dep in (self.cfg.get_departments() if self.cfg else []):
            dep_id = dep.get("id")
            badge = self._dept_badges.get(int(dep_id)) if dep_id is not None else None
            if not badge:
                continue
            total = sum(1 for c in self._cameras if c.get("department_id") == dep_id)
            live = sum(
                1 for c in self._cameras
                if c.get("department_id") == dep_id and self._status.get(c.get("id")) == "live"
            )
            badge.update_counts(live, total)

    def _card_sort_key(self, c):
        cid = c.get("id")
        status = self._status.get(cid, "connecting")
        name = str(c.get("name", "")).lower()
        status_order = {"live": 0, "connecting": 1, "offline": 2, "error": 2}.get(status, 1)
        events = self._stats.get(cid, {}).get("today_count", 0)
        if self._sort_mode == "events":
            return (-events, status_order, name)
        if self._sort_mode == "offline":
            offline_order = {"offline": 0, "error": 0, "connecting": 1, "live": 2}.get(status, 1)
            return (offline_order, status_order, name)
        if self._sort_mode == "az":
            return (0, 0, name)
        return (status_order, 0, name)

    def _set_sort(self, key: str):
        self._sort_mode = key
        for k, btn in self._sort_btns.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._sort_chip_style(k == key))
        self._render_grid()

    def _on_reconnect_requested(self, cam_id: int):
        self._status[cam_id] = "connecting"
        card = self._cards.get(cam_id)
        if card:
            card.set_status("connecting")
        self.reconnect_requested.emit(cam_id)

    def _dept_name(self, dep_id) -> str:
        dep = self.cfg.get_department_by_id(dep_id) if self.cfg else None
        return dep.get("name", "") if dep else ""

    @staticmethod
    def _header_chip(text: str, color: str) -> QLabel:
        chip = QLabel(text)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setFixedHeight(28)
        chip.setMinimumWidth(72)
        chip.setStyleSheet(
            f"color: {color}; background: {C('bg_panel_alt') if is_light() else 'rgba(5,14,24,0.92)'};"
            f"border: 1px solid {color}44; border-radius: 7px;"
            "font-size: 11px; font-weight: 800; padding: 0 10px;"
        )
        return chip

    @staticmethod
    def _stat_chip(label: str, value: str, color: str) -> QFrame:
        box = QFrame()
        box.setFixedSize(82, 48)
        box.setStyleSheet(
            "QFrame { background: rgba(2,6,23,0.42);"
            f"border: 1px solid {BORDER}; border-radius: 7px; "
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(1)
        val = QLabel(value)
        val.setObjectName("statValue")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {color}; font-size: 17px; font-weight: 900;")
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DIM}; font-size: 8px; font-weight: 900;")
        lay.addWidget(val)
        lay.addWidget(lbl)
        return box

    @staticmethod
    def _set_chip(chip: QFrame, value):
        label = chip.findChild(QLabel, "statValue")
        if label:
            label.setText(str(value))

    @staticmethod
    def _ops_row(label: str, value: str, color: str) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {C('bg_panel')}; border: 1px solid {C('border_light')};"
            "border-radius: 10px; }}"
            f"QFrame:hover {{ background: {C('bg_hover')}; border-color: {BORDER}; }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)

        left = QVBoxLayout()
        left.setSpacing(2)
        title = QLabel(label)
        title.setStyleSheet(f"color: {DIM}; font-size: 9px; font-weight: 900; letter-spacing: 0.6px;")
        value_lbl = QLabel(value)
        value_lbl.setObjectName("opsValue")
        value_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 900;")
        left.addWidget(title)
        left.addWidget(value_lbl)
        lay.addLayout(left, 1)

        dot = QLabel("●")
        dot.setObjectName("opsDot")
        dot.setFixedWidth(12)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        lay.addWidget(dot)
        return row

    @staticmethod
    def _ops_row_set(row: QFrame, value: str, color: str):
        value_lbl = row.findChild(QLabel, "opsValue")
        if value_lbl:
            value_lbl.setText(str(value))
            value_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 900;")
        dot = row.findChild(QLabel, "opsDot")
        if dot:
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")

    @staticmethod
    def _filter_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {C('accent_subtle')}; color: {ACCENT};"
                f"border: 1px solid {C('border_accent')};"
                f"border-left: 4px solid {ACCENT}; border-radius: 11px;"
                "font-size: 12px; font-weight: 900; text-align: left; padding: 0 12px; }"
            )
        return (
            f"QPushButton {{ background: {C('bg_panel')}; color: {TEXT_2};"
            f"border: 1px solid {C('border_light')}; border-left: 4px solid transparent; border-radius: 11px;"
            "font-size: 12px; font-weight: 700; text-align: left; padding: 0 12px; }"
            f"QPushButton:hover {{ color: {TEXT}; background: {C('bg_hover')};"
            f"border-color: {BORDER}; border-left-color: {BORDER_STRONG}; }}"
        )

    @staticmethod
    def _column_button_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {C('accent_subtle')}; color: {ACCENT};"
                f"border: 1px solid {C('border_accent')}; border-radius: 6px;"
                "font-size: 11px; font-weight: 900; }"
            )
        return (
            f"QPushButton {{ background: transparent; color: {MUTED};"
            f"border: 1px solid {C('border_light')}; border-radius: 6px;"
            "font-size: 11px; font-weight: 800; }"
            f"QPushButton:hover {{ color: {TEXT}; border-color: {BORDER_STRONG}; }}"
        )

    @staticmethod
    def _sort_chip_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {C('info_dim')}; color: {C('text_link')};"
                f"border: 1px solid {BORDER}; border-radius: 6px;"
                "font-size: 10px; font-weight: 800; padding: 0 9px; }"
            )
        return (
            f"QPushButton {{ background: transparent; color: {MUTED};"
            f"border: 1px solid {C('border_light')}; border-radius: 6px;"
            "font-size: 10px; font-weight: 600; padding: 0 9px; }"
            f"QPushButton:hover {{ color: {TEXT}; border-color: {BORDER_STRONG}; }}"
        )

    @staticmethod
    def _hsep() -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER_SOFT}; border: none;")
        return sep

    @staticmethod
    def _primary_button_style() -> str:
        return (
            f"QPushButton {{ background: {ACCENT}; color: {C('text_on_accent')}; border: none;"
            "border-radius: 7px; font-size: 11px; font-weight: 900; }"
            f"QPushButton:hover {{ background: {C('accent_hover')}; }}"
        )

    @staticmethod
    def _small_button_style() -> str:
        return (
            f"QPushButton {{ background: {SIDEBAR_INSET}; color: {TEXT_2};"
            f"border: 1px solid {BORDER}; border-radius: 6px;"
            "font-size: 13px; font-weight: 900; }"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}"
        )

    def _set_button_icon(self, btn: QPushButton, icon_name: str, *, light: bool = True):
        path = self._icon_dir / icon_name
        if path.exists():
            btn.setIcon(QIcon(str(path)))
            btn.setIconSize(QSize(14, 14))

