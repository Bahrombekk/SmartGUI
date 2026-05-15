from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.ui.styles import C


class CameraTreeBranch(QWidget):
    """Compact tree connector for grouped camera rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(38)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#1e5fa8"), 1))
        x = 16
        y_mid = self.height() // 2
        p.drawLine(x, 0, x, self.height())
        p.drawLine(x, y_mid, self.width() - 6, y_mid)
        p.end()


class CameraGroupChevron(QWidget):
    """Small painted chevron, wider than a text glyph."""

    def __init__(self, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self.setFixedSize(18, 18)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#e2e8f0"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self._expanded:
            p.drawLine(5, 7, 9, 12)
            p.drawLine(9, 12, 13, 7)
        else:
            p.drawLine(7, 5, 12, 9)
            p.drawLine(12, 9, 7, 13)
        p.end()


class CameraListItem(QWidget):
    """Sidebar kamera ro'yxati elementi."""

    clicked = pyqtSignal(int)

    def __init__(self, cam_id: int, cam_name: str, is_active: bool = False,
                 grouped: bool = False, parent=None):
        super().__init__(parent)
        self.cam_id = cam_id
        self._grouped = grouped
        self._status = "connecting"
        self._active = is_active
        self.setFixedHeight(56 if grouped else 48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")
        self._setup_ui(cam_name)

    def _setup_ui(self, cam_name: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(0)

        if self._grouped:
            lay.addWidget(CameraTreeBranch())

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent; border: none;")
        content_lay = QHBoxLayout(self._content)
        content_lay.setContentsMargins(10, 4, 10, 4)
        content_lay.setSpacing(10)
        lay.addWidget(self._content, 1)

        # Status indicator dot
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dot.setStyleSheet(
            f"color: {C('warning')}; font-size: 9px; background: transparent; border: none;"
        )
        content_lay.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)

        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(1)

        self._name_lbl = QLabel(f"{self.cam_id:02d} {cam_name}")
        self._name_lbl.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 13px; font-weight: 500; background: transparent; border: none;"
        )
        name_col.addWidget(self._name_lbl)

        self._status_lbl = QLabel("Ulanmoqda")
        self._status_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 12px; background: transparent; border: none;"
        )
        name_col.addWidget(self._status_lbl)
        content_lay.addLayout(name_col, 1)

        self._menu_lbl = QLabel()
        self._menu_lbl.setFixedSize(20, 20)
        menu_path = Path(__file__).resolve().parents[3] / "images" / "more-vertical.svg"
        self._menu_lbl.setPixmap(QPixmap(str(menu_path)).scaled(
            15, 15, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        self._menu_lbl.setStyleSheet("background: transparent; border: none;")
        self._menu_lbl.setVisible(self._active)
        content_lay.addWidget(self._menu_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        self._apply_active_style()

    def set_status(self, status: str):
        """status: 'live' | 'offline' | 'connecting' | 'error'"""
        if self._status == status:
            return
        self._status = status
        if status == "live":
            self._dot.setStyleSheet(
                f"color: {C('success')}; font-size: 11px; background: transparent; border: none;"
            )
            self._status_lbl.setText("Live")
            self._status_lbl.setStyleSheet(
                f"color: {C('success')}; font-size: 12px; background: transparent; border: none;"
            )
        elif status == "offline" or status == "error":
            self._dot.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 11px; background: transparent; border: none;"
            )
            self._status_lbl.setText("Offline")
            self._status_lbl.setStyleSheet(
                f"color: {C('text_muted')}; font-size: 12px; background: transparent; border: none;"
            )
        else:
            self._dot.setStyleSheet(
                f"color: {C('warning')}; font-size: 11px; background: transparent; border: none;"
            )
            self._status_lbl.setText("Ulanmoqda")
            self._status_lbl.setStyleSheet(
                f"color: {C('warning')}; font-size: 12px; background: transparent; border: none;"
            )

    def set_selected(self, selected: bool):
        if self._active == selected:
            return
        self._active = selected
        self._menu_lbl.setVisible(selected)
        self._apply_active_style()

    def _apply_active_style(self):
        if self._active:
            self._content.setStyleSheet(
                f"background: {C('accent_dim_3')}; border: none; border-radius: 7px;"
            )
        else:
            self._content.setStyleSheet("background: transparent; border: none;")

    def mousePressEvent(self, event):
        self.clicked.emit(self.cam_id)

    def enterEvent(self, event):
        if not self._active:
            self._content.setStyleSheet(
                f"background: {C('bg_hover')}; border: none; border-radius: 7px;"
            )

    def leaveEvent(self, event):
        self._apply_active_style()


class CameraGroupHeader(QWidget):
    """Sidebar bo'lim sarlavhasi."""

    toggled = pyqtSignal(int)

    def __init__(self, dep_id: int, title: str, count: int, expanded: bool = True,
                 parent=None):
        super().__init__(parent)
        self.dep_id = dep_id
        self.expanded = expanded
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 8, 0)
        lay.setSpacing(8)

        arrow = CameraGroupChevron(expanded)
        lay.addWidget(arrow)

        name = QLabel(title)
        name.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )
        lay.addWidget(name, 1)

        badge = QLabel(str(count))
        badge.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent; border: none;"
        )
        badge.setVisible(False)
        lay.addWidget(badge)

    def mousePressEvent(self, event):
        self.toggled.emit(self.dep_id)

    def enterEvent(self, event):
        self.setStyleSheet(f"background: {C('bg_hover')}; border-radius: 5px;")

    def leaveEvent(self, event):
        self.setStyleSheet("background: transparent;")




class DashboardSidebarMixin:
    def _build_left_sidebar(self) -> QWidget:
        # Tashqi konteyner — shaffof, panellar ichida bo'ladi
        sidebar = QWidget()
        sidebar.setFixedWidth(290)
        sidebar.setStyleSheet("background: transparent;")

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # ── Kamera paneli (flex-[7]) ─────────────────────────────────────
        from app.ui.styles import premium_panel_style
        cam_panel = QFrame()
        cam_panel.setObjectName("cameraSidebarPanel")
        cam_panel.setStyleSheet(premium_panel_style("cameraSidebarPanel"))
        cam_lay = QVBoxLayout(cam_panel)
        cam_lay.setContentsMargins(16, 14, 16, 14)
        cam_lay.setSpacing(0)

        # Sarlavha
        hdr_lay = QHBoxLayout()
        hdr_lay.setContentsMargins(0, 0, 0, 12)

        cam_title = QLabel("CAMERAS")
        cam_title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 11px; font-weight: bold;"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        hdr_lay.addWidget(cam_title, 1)

        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('bg_hover')};
                color: {C('text_primary')};
                border: 1px solid {C('border')};
                border-radius: 7px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {C('accent')};
                color: {C('text_on_accent')};
                border-color: {C('accent')};
            }}
        """)
        add_btn.clicked.connect(self.add_camera_requested)
        hdr_lay.addWidget(add_btn)
        cam_lay.addLayout(hdr_lay)

        # "All Cameras" tugma
        all_cam = QPushButton()
        all_cam.setFixedHeight(44)
        all_cam_lay = QHBoxLayout(all_cam)
        all_cam_lay.setContentsMargins(12, 0, 12, 0)
        all_cam_lay.setSpacing(8)

        cam_icon = QLabel()
        cam_icon.setFixedSize(22, 22)
        cam_icon.setPixmap(QPixmap(str(Path(__file__).resolve().parents[3] / "images" / "camera-small.svg")).scaled(
            16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        cam_icon.setStyleSheet("background: transparent; border: none;")
        all_cam_lay.addWidget(cam_icon)

        all_lbl = QLabel("All Cameras")
        all_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 13px; font-weight: bold; background: transparent; border: none;"
        )
        all_cam_lay.addWidget(all_lbl, 1)

        self._all_count_lbl = QLabel("0")
        self._all_count_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 12px; font-weight: bold;"
            f" background: {C('accent_dim_2')}; border: none; border-radius: 11px; padding: 2px 8px;"
        )
        all_cam_lay.addWidget(self._all_count_lbl)

        all_cam.setStyleSheet(f"""
            QPushButton {{
                background: {C('bg_hover')};
                border: 1px solid {C('border')};
                border-radius: 8px;
                text-align: left;
            }}
            QPushButton:hover {{ background: {C('accent_dim_2')}; }}
        """)
        cam_lay.addWidget(all_cam)
        cam_lay.addSpacing(14)

        # Kamera ro'yxati (scroll)
        cam_scroll = QScrollArea()
        cam_scroll.setWidgetResizable(True)
        cam_scroll.setFrameShape(QFrame.Shape.NoFrame)
        cam_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cam_scroll.setStyleSheet("background: transparent;")

        self._cam_list_widget = QWidget()
        self._cam_list_widget.setStyleSheet("background: transparent;")
        self._cam_list_layout = QVBoxLayout(self._cam_list_widget)
        self._cam_list_layout.setContentsMargins(0, 0, 0, 0)
        self._cam_list_layout.setSpacing(2)
        self._cam_list_layout.addStretch()

        cam_scroll.setWidget(self._cam_list_widget)
        cam_lay.addWidget(cam_scroll, 1)

        lay.addWidget(cam_panel, 7)

        # ── Tizim holati paneli (flex-[3]) ────────────────────────────────
        lay.addWidget(self._build_system_overview(), 3)

        return sidebar

    def _clear_camera_sidebar(self):
        while self._cam_list_layout.count():
            item = self._cam_list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _rebuild_camera_sidebar(self):
        self._clear_camera_sidebar()
        self._cam_items.clear()

        cameras = self._sidebar_cameras
        departments = self.cfg.get_departments() if self.cfg else []
        if departments:
            for dep in departments:
                dep_id = dep.get("id")
                dep_cameras = [c for c in cameras if c.get("department_id") == dep_id]
                if not dep_cameras:
                    continue
                expanded = bool(dep.get("expanded", True))
                header = CameraGroupHeader(
                    dep_id, dep.get("name", "Bo'lim"), len(dep_cameras), expanded
                )
                header.toggled.connect(self._toggle_department)
                self._cam_list_layout.addWidget(header)
                if expanded:
                    for cam in dep_cameras:
                        self._add_sidebar_camera_item(cam, grouped=True)

            known_deps = {d.get("id") for d in departments}
            ungrouped = [c for c in cameras if c.get("department_id") not in known_deps]
            if ungrouped:
                header = CameraGroupHeader(0, "Bo'limsiz", len(ungrouped), True)
                self._cam_list_layout.addWidget(header)
                for cam in ungrouped:
                    self._add_sidebar_camera_item(cam, grouped=True)
        else:
            for cam in cameras:
                self._add_sidebar_camera_item(cam, grouped=False)

        self._cam_list_layout.addStretch()
        self._recalc_online()

    def _add_sidebar_camera_item(self, cam: dict, grouped: bool):
        cam_id = cam.get("id")
        item = CameraListItem(
            cam_id,
            cam.get("name", f"Kamera {cam_id}"),
            grouped=grouped,
        )
        item.set_status(self._cam_status.get(cam_id, "connecting"))
        item.clicked.connect(self._select_camera)
        self._cam_items[cam_id] = item
        self._cam_list_layout.addWidget(item)

    def _toggle_department(self, dep_id: int):
        dep = self.cfg.get_department_by_id(dep_id) if self.cfg else None
        if not dep:
            return
        self.cfg.update_department(dep_id, expanded=not bool(dep.get("expanded", True)))
        self.cfg.save()
        self._rebuild_camera_sidebar()

