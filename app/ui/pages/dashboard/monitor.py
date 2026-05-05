from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app.ui.theme import C
from app.ui.widgets.camera_panel import CameraPanel
from app.ui.pages.dashboard.timeline import TimelineWidget


class DashboardMonitorMixin:
    def _build_main_content(self) -> QWidget:
        main = QWidget()
        self._main_content = main
        main.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Live Monitoring paneli (header + kamera grid bir panel ichida)
        monitor_panel = QFrame()
        self._monitor_panel = monitor_panel
        monitor_panel.setObjectName("monitorPanel")
        monitor_panel.setStyleSheet(
            "QFrame#monitorPanel {"
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c1520,stop:1 #07101a);"
            "border: 2px solid #1e5fa8;"
            "border-radius: 12px;"
            "}"
        )
        mp_lay = QVBoxLayout(monitor_panel)
        mp_lay.setContentsMargins(14, 12, 14, 12)
        mp_lay.setSpacing(10)
        mp_lay.addWidget(self._build_monitor_header())
        mp_lay.addWidget(self._build_camera_grid_area(), 1)

        lay.addWidget(monitor_panel, 1)
        bottom_panels = self._build_bottom_panels()
        self._bottom_panels = bottom_panels
        lay.addWidget(bottom_panels)

        return main

    def _build_monitor_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(46)
        hdr.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        title = QLabel("Live Monitoring")
        title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 16px; font-weight: 800;"
            " background: transparent; border: none;"
        )
        lay.addWidget(title)

        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {C('success')}; font-size: 12px; background: transparent; border: none;"
        )
        lay.addWidget(dot)

        self._cam_count_badge = QLabel("0 Cameras")
        self._cam_count_badge.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 12px; background: transparent; border: none;"
        )
        lay.addWidget(self._cam_count_badge)
        lay.addStretch()

        # Grid tartibi tugmalari
        icon_dir = Path(__file__).resolve().parents[4] / "images"
        grid_options = [
            (1, "1 ustun", "layout-1.svg"),
            (2, "2 ustun", "layout-2.svg"),
            (3, "3 ustun", "layout-3.svg"),
            (4, "4 ustun / 2 qator", "layout-4x2.svg"),
        ]
        for columns, tip, icon_name in grid_options:
            btn = QPushButton(str(columns))
            btn.setFixedSize(32, 32)
            icon_path = icon_dir / icon_name
            if icon_path.exists():
                btn.setText("")
                btn.setIcon(QIcon(str(icon_path)))
            else:
                btn.setText(str(columns))
            btn.setIconSize(QSize(17, 17))
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _, cols=columns: self.set_grid_columns(cols))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C('bg_panel')};
                    color: {C('text_secondary')};
                    border: 1px solid {C('border')};
                    border-radius: 5px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {C('bg_hover')};
                    color: {C('text_primary')};
                }}
            """)
            active = columns == self._grid_columns
            btn.setFixedSize(34, 34)
            btn.setStyleSheet(self._grid_btn_style(active))
            lay.addWidget(btn)
            self._grid_btns[columns] = btn

        lay.addSpacing(8)

        # Stream tanlash
        stream_combo = QComboBox()
        stream_combo.addItems(["All Streams", "Online", "Offline", "Main Building", "Secondary Area"])
        stream_combo.setFixedWidth(130)
        stream_combo.setFixedHeight(32)
        self._stream_combo = stream_combo
        stream_combo.currentIndexChanged.connect(self._on_filter_changed)
        lay.addWidget(stream_combo)

        # Kengaytirish
        expand_btn = QPushButton()
        expand_btn.setFixedSize(34, 34)
        expand_path = icon_dir / "expand.svg"
        if expand_path.exists():
            expand_btn.setIcon(QIcon(str(expand_path)))
        else:
            expand_btn.setText("[]")
        expand_btn.setIconSize(QSize(17, 17))
        expand_btn.setToolTip("Expand selected camera")
        expand_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('bg_panel')};
                color: {C('text_secondary')};
                border: 1px solid {C('border')};
                border-radius: 5px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {C('bg_hover')};
                color: {C('text_primary')};
            }}
        """)
        expand_btn.clicked.connect(self._expand_selected_camera)
        lay.addWidget(expand_btn)

        return hdr

    def _build_camera_grid_area(self) -> QScrollArea:
        scroll = QScrollArea()
        self._camera_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setStyleSheet(self._camera_scroll_style())

        self._cam_container = QWidget()
        self._cam_container.setStyleSheet("background: transparent;")
        self._cam_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._cam_grid = QGridLayout(self._cam_container)
        self._cam_grid.setSpacing(6)
        self._cam_grid.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._cam_container)
        return scroll

    @staticmethod
    def _camera_scroll_style() -> str:
        return """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #050a0f;
                width: 8px;
                margin: 2px 0 2px 6px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 4px;
                min-height: 36px;
            }
            QScrollBar::handle:vertical:hover {
                background: #fb923c;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """

    def set_search_text(self, text: str):
        self._search_text = (text or "").strip().lower()
        self._apply_camera_view()

    def set_grid_columns(self, columns: int):
        self._grid_columns = max(1, min(4, int(columns or 4)))
        for cols, btn in self._grid_btns.items():
            btn.setStyleSheet(self._grid_btn_style(cols == self._grid_columns))
        self._apply_camera_view()

    @staticmethod
    def _grid_btn_style(active: bool = False) -> str:
        bg = "rgba(249,115,22,0.18)" if active else "#0f172a"
        border = "rgba(249,115,22,0.55)" if active else "#1e293b"
        return f"""
            QPushButton {{
                background: {bg};
                color: #cbd5e1;
                border: 1px solid {border};
                border-radius: 7px;
                font-size: 11px;
                font-weight: 800;
            }}
            QPushButton:hover {{
                background: rgba(30,41,59,0.9);
                color: #ffffff;
                border-color: rgba(249,115,22,0.45);
            }}
        """

    def _on_filter_changed(self):
        combo = getattr(self, "_stream_combo", None)
        self._stream_filter = combo.currentText().lower() if combo else "all streams"
        self._apply_camera_view()

    def _camera_matches_view(self, cam: dict) -> bool:
        cam_id = cam.get("id")
        haystack = " ".join([
            str(cam_id or ""),
            cam.get("name", ""),
            cam.get("rtsp_url", ""),
            cam.get("company_id", ""),
            self._department_name(cam.get("department_id")),
        ]).lower()
        if self._search_text and self._search_text not in haystack:
            return False

        status = self._cam_status.get(cam_id, "connecting")
        filt = self._stream_filter
        if "online" in filt:
            return status == "live"
        if "offline" in filt:
            return status in {"offline", "error"}
        if "main building" in filt or "secondary area" in filt:
            return self._department_name(cam.get("department_id")).lower() == filt
        return True

    def _department_name(self, dep_id) -> str:
        dep = self.cfg.get_department_by_id(dep_id) if self.cfg else None
        return dep.get("name", "") if dep else ""

    def _apply_camera_view(self):
        if not hasattr(self, "_cam_grid"):
            return
        visible = [cam for cam in self._all_cameras if self._camera_matches_view(cam)]
        self._visible_cameras = visible
        self._render_camera_grid(visible)

    def _render_camera_grid(self, cameras: list):
        """Kamera panellarini grid ichiga joylashtiradi.

        1/2/3 ustun: har qator = viewport to'liq balandligi — 1 qator ko'rinadi, qolganlari scroll.
        4 ustun (4x2): har qator = viewport/2 — 2 qator ko'rinadi, qolganlari scroll.
        """
        while self._cam_grid.count():
            item = self._cam_grid.takeAt(0)
            widget = item.widget()
            if widget:
                if widget in self._panels.values():
                    widget.setParent(None)
                else:
                    widget.deleteLater()

        for r in range(10):
            self._cam_grid.setRowStretch(r, 0)
            self._cam_grid.setRowMinimumHeight(r, 0)
        for c in range(4):
            self._cam_grid.setColumnStretch(c, 0)

        if not cameras:
            no_lbl = QLabel("Bu ko'rinishga mos kamera topilmadi.")
            no_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 14px;")
            self._cam_grid.addWidget(no_lbl, 0, 0)
            self._cam_grid.setColumnStretch(0, 1)
            self._cam_grid.setRowStretch(0, 1)
            return

        cols = 1 if len(cameras) == 1 else min(self._grid_columns, len(cameras))
        panel_h = self._calc_panel_height(cols)

        for idx, cam in enumerate(cameras):
            cam_id = cam.get("id")
            panel = self._panels.get(cam_id)
            if not panel:
                continue
            r = idx // cols
            c = idx % cols
            panel.setFixedHeight(panel_h)
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._cam_grid.addWidget(panel, r, c)

        for c in range(cols):
            self._cam_grid.setColumnStretch(c, 1)

    def _calc_panel_height(self, cols: int) -> int:
        """Har bir kamera paneli balandligini viewport asosida hisoblaydi.

        1/2/3 ustun: to'liq viewport balandligi (1 qator ko'rinadi).
        4 ustun:     viewport / 2 (2 qator ko'rinadi, 4x2 rejimi).
        """
        viewport_h = self._camera_scroll.viewport().height()
        if viewport_h < 100:
            viewport_h = self._camera_scroll.height()
        if viewport_h < 100:
            return 360 if cols <= 2 else 240

        spacing = self._cam_grid.spacing()
        if cols == 4:
            return max(180, (viewport_h - spacing) // 2)
        return max(200, viewport_h)

    def _relayout_grid(self):
        """Oyna o'lchami o'zgarganda panel balandliklarini yangilaydi."""
        if not hasattr(self, "_visible_cameras") or not self._visible_cameras:
            return
        cameras = self._visible_cameras
        cols = 1 if len(cameras) == 1 else min(self._grid_columns, len(cameras))
        panel_h = self._calc_panel_height(cols)

        for cam in cameras:
            cam_id = cam.get("id")
            panel = self._panels.get(cam_id)
            if panel:
                panel.setFixedHeight(panel_h)

    def _select_camera(self, cam_id: int):
        self._selected_cam_id = cam_id
        for pid, panel in self._panels.items():
            if hasattr(panel, "set_selected"):
                panel.set_selected(pid == cam_id)
        for pid, item in self._cam_items.items():
            item.set_selected(pid == cam_id)

    def _expand_selected_camera(self):
        cam_id = self._selected_cam_id
        if cam_id is None and self._visible_cameras:
            cam_id = self._visible_cameras[0].get("id")
        panel = self._panels.get(cam_id)
        if not panel:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(panel.cam_name)
        dlg.resize(1000, 650)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        title = QLabel(f"{panel.cam_id:02d} {panel.cam_name}")
        title.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        lay.addWidget(title)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setStyleSheet("background: #000000; border: 1px solid #1e293b; border-radius: 8px;")
        pixmap = panel._video.pixmap()
        if pixmap and not pixmap.isNull():
            image.setPixmap(pixmap.scaled(960, 560, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            image.setText("Video frame hali mavjud emas")
            image.setStyleSheet(image.styleSheet() + f"color: {C('text_muted')};")
        lay.addWidget(image, 1)
        dlg.exec()

