"""
CamerasPage - camera operations view inspired by the provided SmartHelmet mockup.
"""

import datetime
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QWidget,
    QVBoxLayout,
)

from app.ui.theme import C
from app.ui.widgets.video_label import VideoLabel


class CameraListRow(QFrame):
    clicked = pyqtSignal(int)
    preview_requested = pyqtSignal(int)
    settings_requested = pyqtSignal(int)

    def __init__(self, camera: dict, department_name: str, icon_dir: Path, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.cam_id = camera.get("id")
        self._icon_dir = icon_dir
        self._selected = False
        self._status = "connecting"
        self._fps = 0
        self._ping_ms: float | None = None
        self._detections = 0
        self._last_seen = "--"

        self.setFixedHeight(58)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("cameraListRow")
        self._build_ui(department_name)
        self.set_selected(False)

    def _build_ui(self, department_name: str):
        lay = QGridLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setHorizontalSpacing(12)
        lay.setVerticalSpacing(0)
        lay.setColumnStretch(1, 2)
        lay.setColumnStretch(2, 1)
        lay.setColumnStretch(3, 1)
        lay.setColumnStretch(4, 1)
        lay.setColumnStretch(5, 1)
        lay.setColumnStretch(6, 1)

        self._thumb = QLabel()
        self._thumb.setFixedSize(58, 40)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet("background: transparent; border: none;")
        _cam_pix = QPixmap(str(self._icon_dir / "camera-small.svg"))
        if not _cam_pix.isNull():
            self._thumb.setPixmap(_cam_pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self._thumb.setText("CAM")
            self._thumb.setStyleSheet("background: transparent; color: #64748b; font-size: 10px;")
        lay.addWidget(self._thumb, 0, 0, 2, 1)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(1)
        name = QLabel(f"{self.cam_id:02d} {self.camera.get('name', 'Camera')}")
        name.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 800;")
        title_col.addWidget(name)
        dep = QLabel(department_name or "No location")
        dep.setStyleSheet("color: #94a3b8; font-size: 11px;")
        title_col.addWidget(dep)
        lay.addLayout(title_col, 0, 1, 2, 1)

        self._status_lbl = QLabel("Connecting")
        self._status_lbl.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 700;")
        lay.addWidget(self._status_lbl, 0, 2, 2, 1)

        self._fps_lbl = QLabel("0 fps")
        self._fps_lbl.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        lay.addWidget(self._fps_lbl, 0, 3, 2, 1)

        self._ping_lbl = QLabel("--")
        self._ping_lbl.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        lay.addWidget(self._ping_lbl, 0, 4, 2, 1)

        self._seen_lbl = QLabel("--")
        self._seen_lbl.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        lay.addWidget(self._seen_lbl, 0, 5, 2, 1)

        self._det_lbl = QLabel("0")
        self._det_lbl.setStyleSheet("color: #c084fc; font-size: 11px; font-weight: 800;")
        lay.addWidget(self._det_lbl, 0, 6, 2, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self._preview_btn = self._make_icon_button("eye.svg", "Preview")
        self._preview_btn.clicked.connect(lambda: self.preview_requested.emit(self.cam_id))
        actions.addWidget(self._preview_btn)

        self._settings_btn = self._make_icon_button("settings.svg", "Settings")
        self._settings_btn.clicked.connect(lambda: self.settings_requested.emit(self.cam_id))
        actions.addWidget(self._settings_btn)
        lay.addLayout(actions, 0, 7, 2, 1)

    def _make_icon_button(self, icon_name: str, tip: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(30, 30)
        btn.setToolTip(tip)
        btn.setIcon(QIcon(str(self._icon_dir / icon_name)))
        btn.setIconSize(QSize(18, 18))
        btn.setStyleSheet(self._icon_button_style())
        return btn

    @staticmethod
    def _icon_button_style() -> str:
        return """
            QPushButton {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #cbd5e1;
                font-size: 9px;
                padding: 0;
            }
            QPushButton:hover {
                border-color: #fb923c;
                color: #fb923c;
            }
        """

    def set_selected(self, selected: bool):
        self._selected = selected
        bg = "rgba(249,115,22,0.10)" if selected else "transparent"
        border = "rgba(249,115,22,0.55)" if selected else "#16212c"
        self.setStyleSheet(
            "QFrame#cameraListRow {"
            f"background: {bg}; border-bottom: 1px solid {border}; border-radius: 0;"
            "}"
        )

    def set_status(self, status: str, fps: float = 0.0, detections: int = 0, ping_ms: float | None = None):
        self._status = status
        self._fps = fps
        self._ping_ms = ping_ms
        self._detections = detections
        live = status == "live"
        self._status_lbl.setText("Live" if live else "Offline" if status in {"offline", "error"} else "Connecting")
        self._status_lbl.setStyleSheet(
            f"color: {'#34d399' if live else '#ef4444' if status in {'offline', 'error'} else '#fbbf24'};"
            "font-size: 11px; font-weight: 800;"
        )
        self._fps_lbl.setText(f"{fps:.0f} fps" if live else "0 fps")
        self._ping_lbl.setText(self._format_ping(ping_ms) if live else "--")
        self._seen_lbl.setText("Now" if live else self._last_seen)
        self._det_lbl.setText(str(detections))

    @staticmethod
    def _format_ping(ping_ms: float | None) -> str:
        if ping_ms is None:
            return "--"
        return f"{max(0, int(round(ping_ms)))} ms"

    def set_frame(self, frame: np.ndarray):
        pass

    def mark_seen(self):
        self._last_seen = datetime.datetime.now().strftime("%H:%M:%S")

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)
        super().mousePressEvent(event)


class RingStatus(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.total = 0
        self.live = 0
        self.setFixedSize(118, 118)
        self.setStyleSheet("background: transparent;")

    def set_counts(self, live: int, total: int):
        self.live = max(0, live)
        self.total = max(0, total)
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QColor, QPainter, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(16, 16, -16, -16)
        pen_bg = QPen(QColor("#1e293b"), 10)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0, 360 * 16)

        if self.total:
            pen_live = QPen(QColor("#34d399"), 10)
            pen_live.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen_live)
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * self.live / self.total))
            if self.live < self.total:
                pen_off = QPen(QColor("#ef4444"), 10)
                pen_off.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen_off)
                painter.drawArc(rect, int((90 - 360 * self.live / self.total) * 16), int(-360 * 16 * (self.total - self.live) / self.total))

        painter.setPen(QColor("#f8fafc"))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.total}\nTotal")
        painter.end()


def frame_to_pixmap(frame: np.ndarray, width: int, height: int) -> QPixmap | None:
    if frame is None or frame.size == 0:
        return None
    try:
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(img).scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception:
        return None


class CamerasPage(QWidget):
    add_camera_requested = pyqtSignal()
    departments_changed = pyqtSignal()

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = config_manager
        self._cameras: list[dict] = []
        self._rows: dict[int, CameraListRow] = {}
        self._status: dict[int, str] = {}
        self._stats: dict[int, dict] = {}
        self._frames: dict[int, QPixmap] = {}
        self._selected_cam_id: int | None = None
        self._search_text = ""
        self._filter = "all"
        self._frame_ts: dict[int, float] = {}
        self._icon_dir = Path(__file__).resolve().parents[3] / "images"
        self._events_last_ts: float = 0.0  # _rebuild_events debounce
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("camerasPage")
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        self.setStyleSheet("QWidget#camerasPage { background: #03070b; }")

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_camera_list(), 1)
        root.addWidget(self._build_detail_panel())

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(285)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        cam_panel = self._panel()
        cam_lay = QVBoxLayout(cam_panel)
        cam_lay.setContentsMargins(14, 14, 14, 14)
        cam_lay.setSpacing(10)
        hdr = QHBoxLayout()
        title = self._section_title("CAMERAS")
        hdr.addWidget(title, 1)
        add = QPushButton("+ Add Camera")
        add.setFixedHeight(30)
        add.setStyleSheet(self._secondary_btn_style())
        add.clicked.connect(self.add_camera_requested)
        hdr.addWidget(add)
        cam_lay.addLayout(hdr)

        self._all_filter_btn = QPushButton("  All Cameras")
        self._all_filter_btn.setFixedHeight(36)
        self._all_filter_btn.clicked.connect(lambda: self._set_filter("all"))
        cam_lay.addWidget(self._all_filter_btn)

        cam_lay.addSpacing(6)
        loc_hdr = QHBoxLayout()
        loc = self._section_title("LOCATIONS")
        loc.setStyleSheet(loc.styleSheet() + "color: #94a3b8;")
        loc_hdr.addWidget(loc, 1)
        add_dep = QPushButton("+ Bo'lim")
        add_dep.setFixedHeight(28)
        add_dep.setStyleSheet(self._secondary_btn_style())
        add_dep.clicked.connect(self._add_department)
        loc_hdr.addWidget(add_dep)
        cam_lay.addLayout(loc_hdr)
        self._location_box = QVBoxLayout()
        self._location_box.setSpacing(2)
        cam_lay.addLayout(self._location_box)
        cam_lay.addStretch()
        lay.addWidget(cam_panel, 7)

        status_panel = self._panel()
        st_lay = QVBoxLayout(status_panel)
        st_lay.setContentsMargins(14, 14, 14, 14)
        st_lay.setSpacing(8)
        st_lay.addWidget(self._section_title("STATUS OVERVIEW"))
        ring_row = QHBoxLayout()
        self._ring = RingStatus()
        ring_row.addWidget(self._ring)
        legend = QVBoxLayout()
        self._live_legend = QLabel("Live   0 (0%)")
        self._off_legend = QLabel("Offline   0 (0%)")
        self._live_legend.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        self._off_legend.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        legend.addStretch()
        legend.addWidget(self._live_legend)
        legend.addWidget(self._off_legend)
        legend.addStretch()
        ring_row.addLayout(legend, 1)
        st_lay.addLayout(ring_row)
        lay.addWidget(status_panel, 3)
        return sidebar

    def _build_camera_list(self) -> QFrame:
        frame = self._panel()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        self._title_lbl = QLabel("All Cameras")
        self._title_lbl.setStyleSheet("color: #f8fafc; font-size: 16px; font-weight: 900;")
        hdr.addWidget(self._title_lbl)
        self._count_lbl = QLabel("0 Cameras")
        self._count_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        hdr.addWidget(self._count_lbl)
        hdr.addStretch()
        lay.addLayout(hdr)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search camera...")
        self._search.setFixedHeight(32)
        self._search.setStyleSheet(self._input_style())
        self._search.textChanged.connect(self.set_search_text)
        toolbar.addWidget(self._search, 2)
        for key, label in [("all", "All"), ("live", "Live"), ("offline", "Offline"), ("detection", "With Detection")]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            setattr(self, f"_{key}_btn", btn)
            toolbar.addWidget(btn)
        sort = QComboBox()
        sort.addItems(["Sort by: Name", "Sort by: Status", "Sort by: Detections"])
        sort.setFixedHeight(32)
        sort.setStyleSheet(self._combo_style())
        toolbar.addWidget(sort)
        grid = QPushButton()
        grid.setIcon(QIcon(str(self._icon_dir / "grid-3.svg")))
        grid.setIconSize(QSize(16, 16))
        grid.setFixedSize(34, 32)
        grid.setStyleSheet(self._icon_button_style())
        toolbar.addWidget(grid)
        lay.addLayout(toolbar)

        headers = QGridLayout()
        headers.setContentsMargins(72, 2, 8, 2)
        headers.setColumnStretch(0, 2)
        headers.setColumnStretch(1, 1)
        headers.setColumnStretch(2, 1)
        headers.setColumnStretch(3, 1)
        headers.setColumnStretch(4, 1)
        headers.setColumnStretch(5, 1)
        for col, text in enumerate(["Camera Name", "Status", "FPS", "Ping", "Last Seen", "Detections"]):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            headers.addWidget(lbl, 0, col)
        lay.addLayout(headers)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_body = QWidget()
        self._list_body.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_body)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_body)
        lay.addWidget(scroll, 1)

        foot = QHBoxLayout()
        self._page_lbl = QLabel("Showing 0 to 0 of 0")
        self._page_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        foot.addStretch()
        foot.addWidget(self._page_lbl)
        lay.addLayout(foot)
        return frame

    def _build_detail_panel(self) -> QFrame:
        frame = self._panel()
        frame.setFixedWidth(560)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        self._detail_title = QLabel("Select Camera")
        self._detail_title.setStyleSheet("color: #f8fafc; font-size: 14px; font-weight: 900;")
        hdr.addWidget(self._detail_title, 1)
        self._detail_badge = QLabel("Offline")
        self._detail_badge.setStyleSheet(self._badge_style("#64748b", "rgba(100,116,139,0.14)"))
        hdr.addWidget(self._detail_badge)
        lay.addLayout(hdr)

        preview_box = QFrame()
        preview_box.setStyleSheet("background: #020509; border: 1px solid #16212c; border-radius: 8px;")
        preview_lay = QVBoxLayout(preview_box)
        preview_lay.setContentsMargins(0, 0, 0, 0)
        self._video = VideoLabel()
        self._video.setMinimumHeight(235)
        preview_lay.addWidget(self._video)
        lay.addWidget(preview_box)

        controls = QHBoxLayout()
        controls.addStretch()
        for text in ["shot", "rec", "vol", "full"]:
            btn = QPushButton(text)
            btn.setFixedSize(34, 30)
            btn.setStyleSheet(self._icon_button_style())
            controls.addWidget(btn)
        controls.addStretch()
        lay.addLayout(controls)

        timeline = self._panel(inner=True)
        tl = QVBoxLayout(timeline)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.addWidget(self._section_title("Timeline"))
        row = QHBoxLayout()
        for i in range(6):
            thumb = QLabel(datetime.datetime.now().strftime("%H:%M"))
            thumb.setFixedSize(55, 42)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            border = "#fb923c" if i == 3 else "#1e293b"
            thumb.setStyleSheet(f"background: transparent; color: #94a3b8; border: 1px solid {border}; border-radius: 5px; font-size: 9px;")
            row.addWidget(thumb)
        tl.addLayout(row)
        lay.addWidget(timeline)

        bottom = QHBoxLayout()
        bottom.addWidget(self._build_events_panel(), 1)
        bottom.addWidget(self._build_settings_panel(), 1)
        lay.addLayout(bottom, 1)
        return frame

    def _build_events_panel(self) -> QFrame:
        frame = self._panel(inner=True)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        hdr = QHBoxLayout()
        hdr.addWidget(self._section_title("Recent Events"))
        hdr.addStretch()
        view = QLabel("View All")
        view.setStyleSheet("color: #fb923c; font-size: 10px; font-weight: 800;")
        hdr.addWidget(view)
        lay.addLayout(hdr)
        self._events_layout = QVBoxLayout()
        self._events_layout.setSpacing(6)
        lay.addLayout(self._events_layout)
        lay.addStretch()
        return frame

    def _build_settings_panel(self) -> QFrame:
        frame = self._panel(inner=True)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        lay.addWidget(self._section_title("Camera Settings"))
        self._name_value = self._setting_value("Camera Name", "--")
        self._loc_value = self._setting_value("Location", "--")
        self._url_value = self._setting_value("RTSP URL", "--")
        self._res_value = self._setting_value("Resolution", "1920 x 1080 (Full HD)")
        lay.addWidget(self._name_value)
        lay.addWidget(self._loc_value)
        lay.addWidget(self._url_value)
        lay.addWidget(self._res_value)
        ai = QHBoxLayout()
        ai.addWidget(QLabel("AI Detection"))
        ai.addStretch()
        on = QLabel("ON")
        on.setStyleSheet("background: #f97316; color: #ffffff; border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 800;")
        ai.addWidget(on)
        lay.addLayout(ai)
        checks = QHBoxLayout()
        for text, checked in [("Helmet", True), ("Person", True), ("Vehicle", False)]:
            cb = QCheckBox(text)
            cb.setChecked(checked)
            cb.setStyleSheet("color: #e2e8f0; font-size: 10px;")
            checks.addWidget(cb)
        lay.addLayout(checks)
        lay.addStretch()
        save = QPushButton("Save Changes")
        save.setFixedHeight(30)
        save.setProperty("accent", True)
        lay.addWidget(save)
        return frame

    def _setting_value(self, label: str, value: str) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        key = QLabel(label)
        key.setFixedWidth(82)
        key.setStyleSheet("background: transparent; color: #cbd5e1; font-size: 10px;")
        val = QLabel(value)
        val.setObjectName("valueLabel")
        val.setStyleSheet("background: transparent; border: none; color: #e2e8f0; padding: 5px 7px; font-size: 10px;")
        val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(key)
        lay.addWidget(val, 1)
        return row

    def _panel(self, inner: bool = False) -> QFrame:
        frame = QFrame()
        frame.setProperty("panel", True)
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bg = "#071016" if inner else "#0a1118"
        border = "#16212c" if inner else "#1e293b"
        frame.setStyleSheet(
            "QFrame[panel='true'] {"
            f"background: {bg};"
            f"border: 1px solid {border}; border-radius: 8px;"
            "}"
        )
        return frame

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
        "background: transparent; color: #f8fafc; font-size: 11px; font-weight: 900; letter-spacing: 0px;"
        )
        return lbl

    @staticmethod
    def _secondary_btn_style() -> str:
        return """
            QPushButton { background: transparent; color: #e2e8f0; border: 1px solid #243244; border-radius: 6px; font-size: 11px; }
            QPushButton:hover { background: #0f172a; border-color: #fb923c; color: #fb923c; }
        """

    @staticmethod
    def _icon_button_style() -> str:
        return """
            QPushButton { background: transparent; color: #cbd5e1; border: 1px solid #243244; border-radius: 6px; font-size: 9px; padding: 0; }
            QPushButton:hover { background: #0f172a; border-color: #fb923c; color: #fb923c; }
        """

    @staticmethod
    def _input_style() -> str:
        return """
            QLineEdit {
                background: rgba(2,6,23,0.72);
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 7px;
                padding: 0 10px;
                font-size: 12px;
            }
            QLineEdit:hover {
                background: rgba(15,23,42,0.70);
                border-color: rgba(148,163,184,0.38);
            }
            QLineEdit:focus {
                background: rgba(15,23,42,0.86);
                border: 1px solid rgba(251,146,60,0.74);
            }
        """

    @staticmethod
    def _combo_style() -> str:
        return """
            QComboBox {
                background: rgba(2,6,23,0.72);
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 7px;
                padding: 0 10px;
                font-size: 12px;
            }
            QComboBox:hover {
                background: rgba(15,23,42,0.70);
                border-color: rgba(148,163,184,0.38);
            }
            QComboBox:focus {
                background: rgba(15,23,42,0.86);
                border: 1px solid rgba(251,146,60,0.74);
            }
            QComboBox::drop-down { border: none; width: 26px; }
            QComboBox QAbstractItemView {
                background: #071016;
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.18);
                selection-background-color: rgba(249,115,22,0.14);
            }
        """

    @staticmethod
    def _badge_style(color: str, bg: str) -> str:
        return f"color: {color}; background: {bg}; border-radius: 9px; padding: 3px 9px; font-size: 10px; font-weight: 900;"

    def setup_cameras(self, cameras: list):
        self._cameras = list(cameras)
        self._selected_cam_id = cameras[0].get("id") if cameras else None
        self._status = {cam.get("id"): "connecting" for cam in cameras}
        self._stats.clear()
        self._rows.clear()
        self._frames.clear()
        self._rebuild_locations()
        self._render_rows()
        self._update_counts()
        self._set_filter("all")
        self._select_camera(self._selected_cam_id)

    def _add_department(self):
        name, ok = QInputDialog.getText(self, "Yangi bo'lim", "Bo'lim nomi:")
        if not ok:
            return
        try:
            self.cfg.add_department(name)
            self.cfg.save()
        except ValueError as e:
            QMessageBox.warning(self, "Xatolik", str(e))
            return
        self._rebuild_locations()
        self.departments_changed.emit()

    def _rebuild_locations(self):
        while self._location_box.count():
            item = self._location_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        departments = self.cfg.get_departments() if self.cfg else []
        for dep in departments:
            dep_id = dep.get("id")
            count = sum(1 for cam in self._cameras if cam.get("department_id") == dep_id)
            btn = QPushButton(f"  {dep.get('name', 'Location')}    {count}")
            btn.setFixedHeight(30)
            btn.setStyleSheet(
                "QPushButton { text-align: left; background: transparent; border: 1px solid transparent;"
                " color: #cbd5e1; font-size: 12px; padding-right: 10px; border-radius: 6px; }"
                "QPushButton:hover { color: #fb923c; background: rgba(15,23,42,0.70); border-color: #1e293b; }"
            )
            btn.clicked.connect(lambda _, did=dep_id: self._set_filter(f"dep:{did}"))
            self._location_box.addWidget(btn)

    def _render_rows(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._rows.clear()

        visible = [cam for cam in self._cameras if self._matches(cam)]
        for cam in visible:
            cam_id = cam.get("id")
            row = CameraListRow(cam, self._department_name(cam.get("department_id")), self._icon_dir)
            row.clicked.connect(self._select_camera)
            row.preview_requested.connect(self._preview_camera)
            row.settings_requested.connect(self._select_camera)
            stats = self._stats.get(cam_id, {})
            row.set_status(
                self._status.get(cam_id, "connecting"),
                stats.get("fps", 0.0),
                stats.get("today_count", 0),
                stats.get("ping_ms"),
            )
            row.set_selected(cam_id == self._selected_cam_id)
            self._rows[cam_id] = row
            self._list_layout.addWidget(row)
        self._list_layout.addStretch()
        self._page_lbl.setText(f"Showing {1 if visible else 0} to {len(visible)} of {len(self._cameras)}")

    def _matches(self, cam: dict) -> bool:
        cam_id = cam.get("id")
        text = " ".join([
            str(cam_id or ""),
            cam.get("name", ""),
            cam.get("rtsp_url", ""),
            self._department_name(cam.get("department_id")),
        ]).lower()
        if self._search_text and self._search_text not in text:
            return False
        status = self._status.get(cam_id, "connecting")
        if self._filter == "live":
            return status == "live"
        if self._filter == "offline":
            return status in {"offline", "error"}
        if self._filter == "detection":
            return self._stats.get(cam_id, {}).get("today_count", 0) > 0
        if self._filter.startswith("dep:"):
            return str(cam.get("department_id")) == self._filter.split(":", 1)[1]
        return True

    def _set_filter(self, key: str):
        self._filter = key
        for name in ["all", "live", "offline", "detection"]:
            btn = getattr(self, f"_{name}_btn", None)
            if btn:
                active = key == name
                btn.setStyleSheet(
                    "QPushButton {"
                    f"background: {'rgba(249,115,22,0.18)' if active else 'transparent'};"
                    f"border: 1px solid {'#f97316' if active else '#1e293b'};"
                    f"color: {'#fb923c' if active else '#cbd5e1'};"
                    "border-radius: 6px; font-size: 11px; font-weight: 800;"
                    "padding: 0 12px;"
                    "}"
                    "QPushButton:hover { background: #0f172a; border-color: #334155; }"
                )
        self._all_filter_btn.setStyleSheet(
            "QPushButton { text-align: left; border-radius: 6px; font-size: 11px; font-weight: 800;"
            f"background: {'rgba(249,115,22,0.16)' if key == 'all' else 'transparent'};"
            f"border: 1px solid {'#f97316' if key == 'all' else 'transparent'};"
            f"color: {'#fb923c' if key == 'all' else '#cbd5e1'};"
            "}"
            "QPushButton:hover { background: #0f172a; color: #fb923c; }"
        )
        visible_count = sum(1 for cam in self._cameras if self._matches(cam))
        if key.startswith("dep:"):
            dep_id = key.split(":", 1)[1]
            dep_name = self._department_name(int(dep_id)) if dep_id.isdigit() else "Location"
            self._title_lbl.setText(dep_name or "Location")
            self._count_lbl.setText(f"{visible_count} Cameras")
        else:
            titles = {
                "all": "All Cameras",
                "live": "Live Cameras",
                "offline": "Offline Cameras",
                "detection": "Cameras With Detection",
            }
            self._title_lbl.setText(titles.get(key, "All Cameras"))
            self._count_lbl.setText(f"{visible_count} Cameras")
        self._render_rows()

    def set_search_text(self, text: str):
        self._search_text = (text or "").strip().lower()
        if hasattr(self, "_search") and self._search.text().strip().lower() != self._search_text:
            self._search.setText(text)
        self._render_rows()

    def _select_camera(self, cam_id: int | None):
        self._selected_cam_id = cam_id
        for rid, row in self._rows.items():
            row.set_selected(rid == cam_id)
        cam = self._camera(cam_id)
        if not cam:
            self._detail_title.setText("Select Camera")
            self._video.show_connecting()
            return
        self._detail_title.setText(f"{cam.get('id', 0):02d} {cam.get('name', 'Camera')}")
        self._set_detail_badge(self._status.get(cam_id, "connecting"))
        self._set_value(self._name_value, cam.get("name", "Camera"))
        self._set_value(self._loc_value, self._department_name(cam.get("department_id")) or "No location")
        self._set_value(self._url_value, cam.get("rtsp_url", "--"))
        self._video.show_connecting()
        self._video._has_frame = False
        self._video._mode = "idle"
        self._video._anim_timer.stop()
        self._video.clear()
        self._video.setText("Ko'z iconini bosing")

    def _preview_camera(self, cam_id: int):
        self._select_camera(cam_id)
        self._selected_cam_id = cam_id
        status = self._status.get(cam_id, "connecting")
        if status in {"offline", "error"}:
            self._video.show_error()
            return
        last_pixmap = self._frames.get(cam_id)
        if last_pixmap and not last_pixmap.isNull():
            self._show_preview_pixmap(last_pixmap)
        self._video._has_frame = True
        self._video._mode = "live"
        self._video._anim_timer.stop()

    def _show_preview_pixmap(self, pixmap: QPixmap):
        self._video._has_frame = True
        self._video._mode = "live"
        self._video._anim_timer.stop()
        self._video.clear()
        self._video.setPixmap(pixmap.scaled(
            self._video.width(),
            self._video.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def _show_preview_message(self, text: str):
        self._video._has_frame = True
        self._video._mode = "idle"
        self._video._anim_timer.stop()
        self._video.clear()
        self._video.setText(text)

    def _set_value(self, row: QWidget, text: str):
        label = row.findChild(QLabel, "valueLabel")
        if label:
            label.setText(text)

    def _camera(self, cam_id: int | None) -> dict | None:
        for cam in self._cameras:
            if cam.get("id") == cam_id:
                return cam
        return None

    def _department_name(self, dep_id) -> str:
        dep = self.cfg.get_department_by_id(dep_id) if self.cfg else None
        return dep.get("name", "") if dep else ""

    def update_frame(self, cam_id: int, frame):
        row = self._rows.get(cam_id)
        if row:
            row.mark_seen()

        # VideoLabel QImage va numpy ikkalasini ham qabul qiladi
        if cam_id == self._selected_cam_id:
            self._video.set_frame(frame)

        # Thumbnail: har 1 soniyada bir marta, past sifatda
        now = time.monotonic()
        if now - self._frame_ts.get(cam_id, 0) < 1.0:
            return
        self._frame_ts[cam_id] = now

        if isinstance(frame, QImage):
            pixmap = QPixmap.fromImage(frame).scaled(
                640, 360,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        else:
            pixmap = frame_to_pixmap(frame, 640, 360)
        if pixmap and not pixmap.isNull():
            self._frames[cam_id] = pixmap

    def on_stats(self, cam_id: int, stats: dict):
        self._stats[cam_id] = dict(stats)
        new_status = "live" if stats.get("connected", False) else "offline"
        old_status = self._status.get(cam_id)
        status_changed = old_status != new_status
        if status_changed:
            self._status[cam_id] = new_status

        # Row label lari (FPS, ping) har doim yangilanadi — ular arzon
        row = self._rows.get(cam_id)
        if row:
            row.set_status(new_status, stats.get("fps", 0.0), stats.get("today_count", 0), stats.get("ping_ms"))
        if cam_id == self._selected_cam_id:
            self._set_detail_badge(new_status)

        # Qimmat operatsiyalar faqat holat o'zgarganda
        if status_changed:
            self._update_counts()
            if self._filter in {"live", "offline", "detection"}:
                self._render_rows()

    def on_status(self, cam_id: int, text: str):
        if "ulan" in (text or "").lower():
            self._status[cam_id] = "connecting"

    def on_error(self, cam_id: int, msg: str):
        self._status[cam_id] = "error"
        row = self._rows.get(cam_id)
        if row:
            row.set_status("error", 0.0, self._stats.get(cam_id, {}).get("today_count", 0), None)
        if cam_id == self._selected_cam_id:
            self._set_detail_badge("error")
            self._video.show_error(msg)
        self._update_counts()

    def on_model_loaded(self, cam_id: int):
        pass

    def on_violation(self, data: dict):
        self._rebuild_events()

    def _set_detail_badge(self, status: str):
        live = status == "live"
        self._detail_badge.setText("Live" if live else "Offline")
        self._detail_badge.setStyleSheet(
            self._badge_style("#34d399", "rgba(52,211,153,0.14)") if live
            else self._badge_style("#ef4444", "rgba(239,68,68,0.14)")
        )

    def _update_counts(self):
        total = len(self._cameras)
        live = sum(1 for cam in self._cameras if self._status.get(cam.get("id")) == "live")
        offline = max(0, total - live)
        self._title_lbl.setText("All Cameras")
        self._count_lbl.setText(f"{total} Cameras")
        self._all_filter_btn.setText(f"  All Cameras    {total}")
        self._ring.set_counts(live, total)
        lp = int(live * 100 / total) if total else 0
        op = 100 - lp if total else 0
        self._live_legend.setText(f"Live   {live} ({lp}%)")
        self._off_legend.setText(f"Offline   {offline} ({op}%)")
        self._rebuild_events()

    def _rebuild_events(self):
        # Debounce: DB query ni sekundiga ko'p marta chaqirishdan saqlaydi
        now = time.monotonic()
        if now - self._events_last_ts < 2.0:
            return
        self._events_last_ts = now

        while self._events_layout.count():
            item = self._events_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            events = self.db.get_violations(limit=5)
        except Exception:
            events = []
        for event in events:
            row = QLabel(f"No Helmet Detected      {event.get('created_at', '')[-8:]}")
            row.setStyleSheet("background: transparent; color: #e2e8f0; font-size: 10px; padding: 5px 0;")
            self._events_layout.addWidget(row)
