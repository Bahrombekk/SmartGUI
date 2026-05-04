"""
CamerasPage - production camera operations and inventory view.

Dashboard remains the primary live video wall. This page is for operations:
fleet health, connection status, camera metadata, filtered recent events, and
on-demand preview for the selected camera.
"""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
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

from app.ui.widgets.video_label import VideoLabel


SURFACE = "#071016"
SIDEBAR_BG = "#061827"
SIDEBAR_INSET = "#0b2438"
SURFACE_2 = "#0a111a"
SURFACE_3 = "#0d1621"
BORDER = "#1d3248"
BORDER_STRONG = "#2f4965"
BORDER_SOFT = "#102033"
TEXT = "#f8fafc"
TEXT_2 = "#cbd5e1"
MUTED = "#64748b"
DIM = "#334155"
ACCENT = "#f97316"
LIVE = "#22c55e"
OFFLINE = "#ef4444"
WARN = "#f59e0b"

STATUS_COLORS = {
    "live": LIVE,
    "offline": OFFLINE,
    "error": OFFLINE,
    "connecting": WARN,
}


def _status_label(status: str) -> str:
    return {"live": "Live", "connecting": "Connecting", "error": "Error"}.get(status, "Offline")


def _violation_label(kind: str) -> str:
    return {
        "no_helmet": "No Helmet",
        "unknown_person": "Unknown Person",
        "unauthorized_area": "Unauthorized Area",
    }.get(kind or "no_helmet", "Violation")


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


class CameraGridCard(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, camera: dict, department_name: str, parent=None, *, tall: bool = False):
        super().__init__(parent)
        self.camera = camera
        self.cam_id = int(camera.get("id") or 0)
        self._department_name = department_name
        self._status = "connecting"
        self._selected = False
        self._tall = tall
        self.setObjectName("cameraOpsCard")
        self.setFixedHeight(310 if tall else 220)
        self.setMinimumWidth(210)
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
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(6)

        self._banner = CameraBanner()
        self._banner.setFixedHeight(190 if self._tall else 110)
        self._banner.set_image(self._banner_pixmap())
        lay.addWidget(self._banner)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._cam_code = QLabel(f"CAM {self.cam_id:02d}")
        self._cam_code.setFixedWidth(58)
        self._cam_code.setStyleSheet(f"color: #7ea0bf; font-size: 11px; font-weight: 900;")
        self._name = QLabel(self.camera.get("name", "Camera"))
        self._name.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 900;")
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._badge = QLabel("Connecting")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._cam_code)
        top.addWidget(self._name, 1)
        top.addWidget(self._badge)
        lay.addLayout(top)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        self._department = QLabel(self._department_name or "No department")
        self._department.setStyleSheet(f"color: #8aa6bd; font-size: 11px;")
        self._url = QLabel(self._masked_url(self.camera.get("rtsp_url", "")))
        self._url.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._url.setStyleSheet(f"color: #3f5872; font-size: 10px;")
        self._url.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        meta.addWidget(self._department, 1)
        meta.addWidget(self._url)
        lay.addLayout(meta)

        metrics = QHBoxLayout()
        metrics.setSpacing(6)
        self._fps = self._metric("FPS", "--")
        self._ping = self._metric("PING", "--")
        self._today = self._metric("EVENTS", "0")
        self._ai = self._metric("AI", "Idle")
        metrics.addWidget(self._fps)
        metrics.addWidget(self._ping)
        metrics.addWidget(self._today)
        metrics.addWidget(self._ai)
        lay.addLayout(metrics)

        root.addWidget(body, 1)

    def set_selected(self, selected: bool):
        self._selected = selected
        selected_color = ACCENT if self._status not in {"offline", "error"} else OFFLINE
        border = f"1px solid {selected_color}" if selected else f"1px solid {BORDER}"
        bg = "#0a1017" if selected else SURFACE_2
        self.setStyleSheet(
            "QFrame#cameraOpsCard {"
            f"background: {bg}; border: {border}; border-radius: 8px;"
            f"border-top: 3px solid {STATUS_COLORS.get(self._status, WARN)};"
            "}"
            "QFrame#cameraOpsCard:hover { border-color: rgba(148,163,184,0.30); }"
        )

    def set_status(self, status: str, fps: float = 0.0, detections: int = 0, ping_ms=None):
        self._status = status
        self.set_selected(self._selected)
        self._badge.setText(_status_label(status))
        self._badge.setStyleSheet(self._badge_css(status))
        self._metric_value(self._fps, f"{fps:.0f}" if status == "live" else "--", LIVE if status == "live" else MUTED)
        self._metric_value(self._ping, "--" if ping_ms is None else f"{max(0, int(ping_ms))}", TEXT_2)
        self._metric_value(self._today, str(detections or 0), ACCENT if detections else TEXT_2)
        self._metric_value(self._ai, "Run" if status == "live" else _status_label(status), LIVE if status == "live" else STATUS_COLORS.get(status, MUTED))

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
        return (
            f"color: {color}; background: rgba(15,23,42,0.72);"
            f"border: 1px solid {color}; border-radius: 6px;"
            "padding: 2px 8px; font-size: 10px; font-weight: 900;"
        )

    @staticmethod
    def _metric(title: str, value: str) -> QFrame:
        box = QFrame()
        box.setObjectName("metricBox")
        box.setStyleSheet(
            "QFrame#metricBox { background: rgba(4,10,20,0.74);"
            f"border: 1px solid #20344c; border-radius: 7px; "
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 6, 8, 5)
        lay.setSpacing(1)
        val = QLabel(value)
        val.setObjectName("metricValue")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {TEXT_2}; font-size: 13px; font-weight: 900;")
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: #48627e; font-size: 8px; font-weight: 900;")
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

    def __init__(self, db, cfg, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"
        self._cam_id: int | None = None
        self._cameras: list[dict] = []
        self._preview_active = False
        self._events_ts = 0.0
        self._expanded = False
        self._normal_width = 520
        self._expanded_width = 1120
        self._normal_preview_height = 320
        self._expanded_preview_height = 560
        self.setFixedWidth(self._normal_width)
        self.setObjectName("cameraInspector")
        self.setStyleSheet(
            "QFrame#cameraInspector {"
            f"background: {SURFACE}; border-left: 2px solid {BORDER_STRONG};"
            f"border-top: 1px solid {BORDER_SOFT}; border-bottom: 1px solid {BORDER_SOFT};"
            "}"
        )
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet(f"background: {SURFACE_2}; border-bottom: 1px solid {BORDER};")
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 0, 12, 0)
        h.setSpacing(10)
        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        self._title = QLabel("Camera")
        self._title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 900;")
        self._sub = QLabel("--")
        self._sub.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        title_col.addWidget(self._title)
        title_col.addWidget(self._sub)
        h.addLayout(title_col, 1)
        self._badge = QLabel("Offline")
        h.addWidget(self._badge)
        self._expand_btn = QPushButton(">")
        self._expand_btn.setFixedSize(28, 28)
        self._expand_btn.setToolTip("Expand inspector")
        self._expand_btn.setStyleSheet(self._icon_button_style())
        self._set_button_icon(self._expand_btn, "expand.svg")
        self._expand_btn.clicked.connect(self.toggle_expanded)
        h.addWidget(self._expand_btn)
        close = QPushButton()
        close.setFixedSize(28, 28)
        close.setStyleSheet(self._icon_button_style())
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
        self._preview_box.setStyleSheet(
            "QWidget#cameraPreviewBox {"
            "background: #020509;"
            f"border-top: 1px solid {BORDER};"
            f"border-bottom: 1px solid {BORDER};"
            "}"
        )
        pv = QVBoxLayout(self._preview_box)
        pv.setContentsMargins(0, 0, 0, 0)
        self._video = VideoLabel()
        self._video.setMinimumHeight(self._normal_preview_height)
        pv.addWidget(self._video)
        lay.addWidget(self._preview_box)

        controls = QWidget()
        controls.setFixedHeight(50)
        controls.setStyleSheet(f"background: {SURFACE_3}; border-bottom: 1px solid {BORDER};")
        c = QHBoxLayout(controls)
        c.setContentsMargins(14, 0, 14, 0)
        c.addStretch()
        self._prev_btn = self._ctrl_btn("Preview", "eye.svg")
        self._prev_btn.clicked.connect(self._toggle_preview)
        self._shot_btn = self._ctrl_btn("Snapshot", "camera-small.svg")
        self._shot_btn.setText("Snapshot")
        self._shot_btn.setMinimumWidth(96)
        self._prev_btn.setMinimumWidth(86)
        c.addWidget(self._prev_btn)
        c.addWidget(self._shot_btn)
        c.addStretch()
        lay.addWidget(controls)

        lay.addWidget(self._section_header("LIVE HEALTH"))
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

        lay.addWidget(self._section_header("CAMERA CONFIG"))
        config = QWidget()
        config.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(config)
        cl.setContentsMargins(14, 6, 14, 14)
        cl.setSpacing(8)
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
        edit = QPushButton("Edit Settings")
        edit.setFixedHeight(36)
        edit.setStyleSheet(self._primary_button_style())
        self._set_button_icon(edit, "settings.svg", light=False)
        edit.clicked.connect(self.edit_requested)
        cl.addWidget(edit)
        lay.addWidget(config)
        lay.addWidget(self._divider())

        lay.addWidget(self._section_header("RECENT EVENTS"))
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
        self._title.setText(f"CAM {cam_id:02d}  {name}")
        self._sub.setText(loc)
        self._badge.setText(_status_label(status))
        self._badge.setStyleSheet(self._badge_css(status))
        self._set_info(self._row_name, name)
        self._set_info(self._row_loc, loc)
        self._set_info(self._row_url, CameraGridCard._masked_url(url))
        self._set_info(self._row_access, str(cam.get("access_mode", "department")))
        self._set_info(self._row_last, "Waiting for stream")
        self._update_health(stats)
        self._video._has_frame = False
        self._video.clear()
        self._video.setText("Preview")
        self._events_ts = 0.0
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
        if status in {"offline", "error"} and not self._preview_active:
            self._video.show_error()

    def set_frame(self, frame):
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
            self._video._has_frame = False
            self._video.clear()
            self._video.setText("Preview")

    def _update_health(self, stats: dict):
        fps = float(stats.get("fps") or 0)
        ping = stats.get("ping_ms")
        ok = bool(stats.get("connected", False))
        self._chip_value(self._fps_chip, f"{fps:.0f}", LIVE if ok else MUTED)
        self._chip_value(self._ping_chip, "--" if ping is None else f"{max(0, int(ping))} ms", TEXT_2)
        self._chip_value(self._status_chip, "Online" if ok else "Offline", LIVE if ok else OFFLINE)
        self._set_info(self._row_last, "Now" if ok else "No signal")

    def _rebuild_events(self):
        now = time.monotonic()
        if now - self._events_ts < 1.0:
            return
        self._events_ts = now
        while self._ev_lay.count():
            item = self._ev_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            cam = next((c for c in self._cameras if c.get("id") == self._cam_id), None)
            events = self.db.get_violations(limit=6, camera_name=cam.get("name") if cam else None)
        except Exception:
            events = []

        if not events:
            empty = QLabel("No recent events for this camera")
            empty.setStyleSheet(f"color: {DIM}; font-size: 11px; padding: 8px 0;")
            self._ev_lay.addWidget(empty)
            return

        for event in events:
            row = QFrame()
            row.setFixedHeight(38)
            row.setStyleSheet(
                "QFrame { background: rgba(2,6,23,0.55);"
                f"border: 1px solid {BORDER}; border-radius: 7px; "
                "}"
                "QLabel { background: transparent; border: none; }"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 0, 10, 0)
            rl.setSpacing(8)
            kind = event.get("violation_type", "no_helmet")
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {OFFLINE}; border-radius: 4px;")
            title = QLabel(_violation_label(kind))
            title.setStyleSheet(f"color: {TEXT_2}; font-size: 11px; font-weight: 800;")
            ts = QLabel(str(event.get("created_at", ""))[-8:] or "--")
            ts.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
            rl.addWidget(dot)
            rl.addWidget(title, 1)
            rl.addWidget(ts)
            self._ev_lay.addWidget(row)

    @staticmethod
    def _ctrl_btn(self, text: str, icon_name: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        btn.setStyleSheet(
            "QPushButton { background: rgba(15,23,42,0.72);"
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
        box.setStyleSheet(
            "QFrame { background: rgba(2,6,23,0.55);"
            f"border: 1px solid {BORDER}; border-radius: 7px; "
            "}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        val = QLabel(value)
        val.setObjectName("chipValue")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {TEXT_2}; font-size: 15px; font-weight: 900;")
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DIM}; font-size: 9px; font-weight: 900;")
        lay.addWidget(val)
        lay.addWidget(lbl)
        return box

    @staticmethod
    def _chip_value(chip: QFrame, text: str, color: str):
        val = chip.findChild(QLabel, "chipValue")
        if val:
            val.setText(text)
            val.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: 900;")

    @staticmethod
    def _info_row(key: str, value: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        k = QLabel(key)
        k.setFixedWidth(82)
        k.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        v = QLabel(value)
        v.setObjectName("infoValue")
        v.setStyleSheet(
            "background: rgba(2,6,23,0.55);"
            f"border: 1px solid {BORDER}; border-radius: 6px;"
            f"color: {TEXT_2}; padding: 5px 8px; font-size: 11px;"
        )
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
    def _section_header(text: str) -> QWidget:
        w = QWidget()
        w.setFixedHeight(30)
        w.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 14, 0)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {DIM}; font-size: 9px; font-weight: 900;")
        lay.addWidget(lbl)
        lay.addStretch()
        return w

    @staticmethod
    def _divider() -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER}; border: none;")
        return sep

    @staticmethod
    def _badge_css(status: str) -> str:
        color = STATUS_COLORS.get(status, WARN)
        return (
            f"color: {color}; background: rgba(15,23,42,0.72);"
            f"border: 1px solid {color}; border-radius: 7px;"
            "padding: 3px 9px; font-size: 10px; font-weight: 900;"
        )

    @staticmethod
    def _primary_button_style() -> str:
        return (
            f"QPushButton {{ background: {ACCENT}; color: #05090d; border: none;"
            "border-radius: 7px; font-size: 11px; font-weight: 900; }"
            "QPushButton:hover { background: #fb923c; }"
        )

    @staticmethod
    def _icon_button_style() -> str:
        return (
            "QPushButton { background: transparent;"
            f"color: {MUTED}; border: none; border-radius: 6px;"
            "font-size: 13px; font-weight: 900; }"
            f"QPushButton:hover {{ background: rgba(239,68,68,0.12); color: {OFFLINE}; }}"
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

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = config_manager
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"
        self._cameras: list[dict] = []
        self._cards: dict[int, CameraGridCard] = {}
        self._status: dict[int, str] = {}
        self._stats: dict[int, dict] = {}
        self._selected: int | None = None
        self._filter = "all"
        self._grid_columns = (self.cfg.get("cameras_grid_columns", 5) if self.cfg else 5)
        self._search_text = ""
        self._build_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_side_panels()

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
        self.setStyleSheet(f"QWidget#camerasPage {{ background: #02060a; }}")
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
        row.addWidget(SidebarResizeHandle(self._sidebar, parent=self))
        row.addWidget(self._make_grid_area(), 1)
        self._detail = CameraDetailPanel(self.db, self.cfg)
        self._detail.close_requested.connect(self._close_detail)
        self._detail.edit_requested.connect(self.add_camera_requested)
        self._detail.hide()
        self._detail_handle = SidebarResizeHandle(self._detail, parent=self, reverse=True, min_width=420, max_width=1320)
        self._detail_handle.hide()
        row.addWidget(self._detail_handle)
        row.addWidget(self._detail)
        root.addWidget(body, 1)

    def _make_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("cameraOpsHeader")
        header.setFixedHeight(72)
        header.setStyleSheet(
            f"QFrame#cameraOpsHeader {{ background: {SURFACE}; border-bottom: 1px solid {BORDER_SOFT}; }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QHBoxLayout(header)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Camera Operations")
        title.setStyleSheet(f"color: {TEXT}; font-size: 18px; font-weight: 900;")
        sub = QLabel("Fleet health, access roster status, and on-demand camera diagnostics")
        sub.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        lay.addLayout(title_col, 1)

        add = QPushButton("+ Add Camera")
        add.setFixedSize(126, 36)
        add.setStyleSheet(self._primary_button_style())
        self._set_button_icon(add, "plus.svg", light=False)
        add.clicked.connect(self.add_camera_requested)
        lay.addWidget(add)
        return header

    def _make_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("cameraOpsSidebar")
        sidebar.setFixedWidth(244)
        sidebar.setStyleSheet(
            f"QFrame#cameraOpsSidebar {{ background: {SIDEBAR_BG}; border-right: 1px solid {BORDER}; }}"
            "QFrame#cameraOpsSidebar QLabel { background: transparent; border: none; }"
        )
        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Search ──────────────────────────────────────────────────
        search_wrap = QWidget()
        search_wrap.setStyleSheet("background: transparent;")
        sw = QVBoxLayout(search_wrap)
        sw.setContentsMargins(12, 14, 12, 10)
        sw.setSpacing(0)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search camera...")
        self._search.setFixedHeight(38)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {SIDEBAR_INSET}; color: {TEXT_2};"
            f"border: 1px solid {BORDER}; border-radius: 8px;"
            "padding: 0 10px; font-size: 12px; }"
            f"QLineEdit:focus {{ border-color: {ACCENT}; background: #0d2035; }}"
        )
        search_icon = self._icon_dir / "search.svg"
        if search_icon.exists():
            self._search.addAction(QIcon(str(search_icon)), QLineEdit.ActionPosition.LeadingPosition)
        self._search.textChanged.connect(self.set_search_text)
        sw.addWidget(self._search)
        outer.addWidget(search_wrap)

        # ── View filters ────────────────────────────────────────────
        view_wrap = QWidget()
        view_wrap.setStyleSheet("background: transparent;")
        vw = QVBoxLayout(view_wrap)
        vw.setContentsMargins(12, 2, 12, 10)
        vw.setSpacing(3)
        view_sec = QLabel("VIEW")
        view_sec.setFixedHeight(22)
        view_sec.setStyleSheet(
            f"color: {DIM}; font-size: 9px; font-weight: 900; letter-spacing: 1px;"
        )
        vw.addWidget(view_sec)

        self._fbtn: dict[str, QPushButton] = {}
        for key, label, icon_name in [
            ("all", "All Cameras", "camera.svg"),
            ("live", "Live", "wifi.svg"),
            ("offline", "Offline / Error", "alerts.svg"),
        ]:
            btn = QPushButton(f"  {label}")
            btn.setFixedHeight(36)
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

        # ── Departments ──────────────────────────────────────────────
        dept_wrap = QWidget()
        dept_wrap.setStyleSheet("background: transparent;")
        dw = QVBoxLayout(dept_wrap)
        dw.setContentsMargins(12, 12, 12, 8)
        dw.setSpacing(4)

        dept_hdr = QHBoxLayout()
        dept_hdr.setSpacing(6)
        dep_lbl = QLabel("DEPARTMENTS")
        dep_lbl.setStyleSheet(
            f"color: {DIM}; font-size: 9px; font-weight: 900; letter-spacing: 1px;"
        )
        dept_hdr.addWidget(dep_lbl, 1)
        add_dep = QPushButton()
        add_dep.setFixedSize(22, 22)
        add_dep.setToolTip("Add department")
        add_dep.setStyleSheet(
            f"QPushButton {{ background: {SIDEBAR_INSET}; color: {TEXT_2};"
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
        self._loc_lay.setSpacing(3)
        dw.addLayout(self._loc_lay)
        outer.addWidget(dept_wrap)
        outer.addStretch()

        # ── Fleet stats strip ────────────────────────────────────────
        fleet_bar = QWidget()
        fleet_bar.setStyleSheet(
            f"background: {SIDEBAR_INSET}; border-top: 1px solid {BORDER};"
        )
        fb = QVBoxLayout(fleet_bar)
        fb.setContentsMargins(12, 10, 12, 14)
        fb.setSpacing(8)
        fleet_hdr = QLabel("FLEET STATUS")
        fleet_hdr.setStyleSheet(
            f"color: {DIM}; font-size: 9px; font-weight: 900;"
            "letter-spacing: 1px; background: transparent; border: none;"
        )
        fb.addWidget(fleet_hdr)
        stat_row = QHBoxLayout()
        stat_row.setSpacing(5)
        self._fs_total = self._fleet_stat("0", "TOTAL", TEXT_2)
        self._fs_live = self._fleet_stat("0", "LIVE", LIVE)
        self._fs_offline = self._fleet_stat("0", "OFF", OFFLINE)
        self._fs_conn = self._fleet_stat("0", "CONN", WARN)
        stat_row.addWidget(self._fs_total)
        stat_row.addWidget(self._fs_live)
        stat_row.addWidget(self._fs_offline)
        stat_row.addWidget(self._fs_conn)
        fb.addLayout(stat_row)
        outer.addWidget(fleet_bar)

        return sidebar

    def _make_grid_area(self) -> QWidget:
        area = CameraGridArea()
        area.resized.connect(self._rerender_grid_later)
        area.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(area)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        toolbar = QHBoxLayout()
        self._grid_title = QLabel("All Cameras")
        self._grid_title.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: 900;")
        self._count_lbl = QLabel("0")
        self._count_lbl.setStyleSheet(
            f"color: {TEXT_2}; background: {SURFACE_3}; border: 1px solid {BORDER};"
            "border-radius: 7px; font-size: 11px; font-weight: 900; padding: 2px 8px;"
        )
        self._hint_lbl = QLabel("Live cameras first. Select a camera for preview, health, and recent events.")
        self._hint_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        toolbar.addWidget(self._grid_title)
        toolbar.addWidget(self._count_lbl)
        toolbar.addSpacing(10)
        toolbar.addWidget(self._hint_lbl, 1)
        self._col_btns: dict[int, QPushButton] = {}
        cols_lbl = QLabel("Layout")
        cols_lbl.setStyleSheet(f"color: {DIM}; font-size: 10px; font-weight: 900;")
        toolbar.addWidget(cols_lbl)
        _layout_icons = {
            1: "layout-1.svg",
            2: "layout-2.svg",
            3: "layout-3.svg",
            4: "layout-4x2.svg",
            5: "grid-3.svg",
            6: "grid-4.svg",
        }
        for col in (1, 2, 3, 4, 5, 6):
            btn = QPushButton()
            btn.setFixedSize(32, 28)
            btn.setCheckable(True)
            btn.setToolTip(f"{col} ustunli joy")
            icon_path = self._icon_dir / _layout_icons[col]
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(18, 18))
            else:
                btn.setText(f"{col}")
            btn.clicked.connect(lambda _, c=col: self._set_grid_columns(c))
            self._col_btns[col] = btn
            toolbar.addWidget(btn)
        self._refresh_column_buttons()
        lay.addLayout(toolbar)

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
        lay.addWidget(scroll, 1)

        self._foot = QLabel("")
        self._foot.setStyleSheet(f"color: {DIM}; font-size: 10px;")
        lay.addWidget(self._foot, 0, Qt.AlignmentFlag.AlignRight)
        return area

    def setup_cameras(self, cameras: list):
        self._cameras = list(cameras)
        self._status = {c.get("id"): "connecting" for c in cameras}
        self._stats.clear()
        self._cards.clear()
        self._selected = None
        self._detail.hide()
        self._detail_handle.hide()
        self._rebuild_locations()
        self._render_grid()
        self._update_counts()
        self._set_filter("all")

    def set_search_text(self, text: str):
        self._search_text = (text or "").strip().lower()
        if hasattr(self, "_search") and self._search.text().strip().lower() != self._search_text:
            self._search.setText(text)
        self._render_grid()

    def update_frame(self, cam_id: int, frame):
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

    def on_status(self, cam_id: int, text: str):
        if "ulan" in (text or "").lower():
            self._status[cam_id] = "connecting"

    def on_error(self, cam_id: int, _msg: str):
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
            self._detail._rebuild_events()

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
            return status in {"offline", "error"}
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
            key=lambda c: (
                {"live": 0, "connecting": 1, "offline": 2, "error": 2}.get(self._status.get(c.get("id"), "connecting"), 1),
                str(c.get("name", "")),
            ),
        )
        n = len(visible)
        viewport_w = self._grid_scroll.viewport().width() if hasattr(self, "_grid_scroll") else self.width()
        fit_cols = max(1, min(6, viewport_w // 240))
        cols = max(1, min(self._grid_columns, fit_cols, n if n else 1))
        self._grid_body.setMinimumWidth(0)
        for i, cam in enumerate(visible):
            cid = cam.get("id")
            card = CameraGridCard(cam, self._dept_name(cam.get("department_id")), tall=(cols == 1))
            card.clicked.connect(self._select_camera)
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
        self._foot.setText(f"Showing {n} of {len(self._cameras)} cameras")

    def _rerender_grid_later(self):
        if hasattr(self, "_grid_lay"):
            self._render_grid()

    def _set_grid_columns(self, columns: int):
        self._grid_columns = max(1, min(6, int(columns)))
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

    def _close_detail(self):
        self._detail.hide()
        self._detail_handle.hide()
        self._selected = None
        for card in self._cards.values():
            card.set_selected(False)

    def _rebuild_locations(self):
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
            row.setFixedHeight(34)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setObjectName("deptRow")
            active_bg = "rgba(249,115,22,0.10)" if active else "transparent"
            active_border = f"border: 1px solid rgba(249,115,22,0.35); border-radius: 8px;" if active else "border: 1px solid transparent; border-radius: 8px;"
            row.setStyleSheet(
                f"QWidget#deptRow {{ background: {active_bg}; {active_border} }}"
                f"QWidget#deptRow:hover {{ background: {SIDEBAR_INSET}; border-color: {BORDER}; }}"
                "QLabel { background: transparent; border: none; }"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 0, 8, 0)
            rl.setSpacing(6)

            icon_lbl = QLabel()
            icon_lbl.setFixedSize(14, 14)
            if building_icon.exists():
                pix = QPixmap(str(building_icon)).scaled(
                    14, 14,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon_lbl.setPixmap(pix)
            rl.addWidget(icon_lbl)

            name_lbl = QLabel(dep.get("name", "Department"))
            name_lbl.setStyleSheet(
                f"color: {ACCENT if active else TEXT_2}; font-size: 11px; font-weight: 700;"
            )
            rl.addWidget(name_lbl, 1)

            badge_color = LIVE if live else MUTED
            badge = QLabel(f"{live}/{total}")
            badge.setStyleSheet(
                f"color: {badge_color}; background: rgba(2,6,23,0.60);"
                f"border: 1px solid {BORDER}; border-radius: 5px;"
                "font-size: 9px; font-weight: 900; padding: 1px 5px;"
            )
            rl.addWidget(badge)

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
        if hasattr(self, "_fs_total"):
            self._fleet_stat_set(self._fs_total, str(total))
            self._fleet_stat_set(self._fs_live, str(live))
            self._fleet_stat_set(self._fs_offline, str(offline))
            self._fleet_stat_set(self._fs_conn, str(warn))
        self._rebuild_locations()

    def _dept_name(self, dep_id) -> str:
        dep = self.cfg.get_department_by_id(dep_id) if self.cfg else None
        return dep.get("name", "") if dep else ""

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
    def _filter_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: rgba(249,115,22,0.13); color: {ACCENT};"
                f"border: 1px solid rgba(249,115,22,0.40);"
                f"border-left: 3px solid {ACCENT}; border-radius: 8px;"
                "font-size: 12px; font-weight: 800; text-align: left; padding: 0 10px; }"
            )
        return (
            f"QPushButton {{ background: transparent; color: {MUTED};"
            "border: 1px solid transparent; border-radius: 8px;"
            "font-size: 12px; font-weight: 700; text-align: left; padding: 0 10px; }"
            f"QPushButton:hover {{ color: {TEXT_2}; background: {SIDEBAR_INSET}; border-color: {BORDER}; }}"
        )

    @staticmethod
    def _column_button_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: rgba(249,115,22,0.18); color: {ACCENT};"
                f"border: 1px solid rgba(249,115,22,0.55); border-radius: 7px;"
                "font-size: 12px; font-weight: 900; }"
            )
        return (
            f"QPushButton {{ background: {SURFACE_3}; color: {MUTED};"
            f"border: 1px solid {BORDER}; border-radius: 7px;"
            "font-size: 12px; font-weight: 900; }"
            f"QPushButton:hover {{ color: {TEXT_2}; border-color: {BORDER_STRONG}; }}"
        )

    @staticmethod
    def _fleet_stat(value: str, label: str, color: str) -> QFrame:
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background: rgba(2,6,23,0.50);"
            f"border: 1px solid {BORDER}; border-radius: 7px; }}"
            "QLabel { background: transparent; border: none; }"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(1)
        val = QLabel(value)
        val.setObjectName("fleetValue")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: 900;")
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DIM}; font-size: 8px; font-weight: 900;")
        lay.addWidget(val)
        lay.addWidget(lbl)
        return box

    @staticmethod
    def _fleet_stat_set(chip: QFrame, value: str):
        val = chip.findChild(QLabel, "fleetValue")
        if val:
            val.setText(value)

    @staticmethod
    def _hsep() -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER}; border: none;")
        return sep

    @staticmethod
    def _primary_button_style() -> str:
        return (
            f"QPushButton {{ background: {ACCENT}; color: #05090d; border: none;"
            "border-radius: 7px; font-size: 11px; font-weight: 900; }"
            "QPushButton:hover { background: #fb923c; }"
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
