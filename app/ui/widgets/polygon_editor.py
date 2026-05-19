"""
PolygonEditorDialog — kamera kadrida zona polygon chizish.

Foydalanish:
    pixmap = QPixmap.fromImage(last_frame)
    dlg = PolygonEditorDialog(pixmap, cam.get("polygon_points", []), cam_name,
                              existing_color=cam.get("polygon_color", "#f97316"))
    if dlg.exec() == QDialog.DialogCode.Accepted:
        pts   = dlg.result_points()   # [[nx, ny], ...] normalized 0-1
        color = dlg.result_color()    # "#rrggbb"
        cfg.update_camera(cam_id, polygon_points=pts, polygon_color=color)
        cfg.save()
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QPixmap, QPolygonF,
)
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from app.ui.styles import C


_PRESET_COLORS = [
    ("#f97316", "To'q sariq"),
    ("#ef4444", "Qizil"),
    ("#22c55e", "Yashil"),
    ("#3b82f6", "Ko'k"),
    ("#a855f7", "Binafsha"),
]


class _ColorDot(QPushButton):
    """Kichik aylana rang tugmasi — polygon rangi tanlash uchun."""

    def __init__(self, hex_color: str, tooltip: str, parent=None):
        super().__init__(parent)
        self._hex = hex_color
        self.setFixedSize(22, 22)
        self.setToolTip(tooltip)
        self.setCheckable(True)
        self._refresh()

    def _refresh(self):
        ring = "white" if self.isChecked() else "rgba(255,255,255,0.18)"
        self.setStyleSheet(
            f"QPushButton {{ background: {self._hex}; border-radius: 11px;"
            f" border: 2.5px solid {ring}; }}"
            f"QPushButton:hover {{ border: 2.5px solid white; }}"
        )

    def setChecked(self, v: bool):
        super().setChecked(v)
        self._refresh()


class _PolygonCanvas(QWidget):
    """Camera frame ustida polygon chizish va tahrirlash widgeti."""

    _FIRST_R = 8
    _PT_R    = 6
    _CLOSE_D = 16   # px — birinchi nuqtaga yaqin bosilsa yopiladi
    _DRAG_D  = 14   # px — nuqtani sudrab harakatlantirish uchun bosish maydoni

    def __init__(self, pixmap: QPixmap, existing_points: list, parent=None):
        super().__init__(parent)
        self._pixmap  = pixmap
        self._points: list[list[float]] = [list(p) for p in existing_points]
        self._frame_rect = QRectF()
        self._hover: QPointF | None = None
        self._drag_idx: int | None = None       # sudraladigan nuqta indeksi
        self._hover_pt_idx: int | None = None   # kursor ustida turgan nuqta
        self._color: QColor = QColor("#f97316")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(480, 300)

    # ── Rang ──────────────────────────────────────────────────────────────

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def get_color(self) -> QColor:
        return self._color

    # ── Koordinat o'girish ────────────────────────────────────────────────

    def _calc_frame_rect(self) -> QRectF:
        if self._pixmap.isNull():
            return QRectF(self.rect())
        sw, sh = float(self.width()), float(self.height())
        iw, ih = float(self._pixmap.width()), float(self._pixmap.height())
        if iw == 0 or ih == 0:
            return QRectF(self.rect())
        ratio = min(sw / iw, sh / ih)
        dw, dh = iw * ratio, ih * ratio
        return QRectF((sw - dw) / 2, (sh - dh) / 2, dw, dh)

    def _to_w(self, nx: float, ny: float) -> QPointF:
        r = self._frame_rect
        return QPointF(r.x() + nx * r.width(), r.y() + ny * r.height())

    def _to_norm(self, wx: float, wy: float) -> tuple[float, float]:
        r = self._frame_rect
        if r.width() == 0 or r.height() == 0:
            return 0.0, 0.0
        return (
            max(0.0, min(1.0, (wx - r.x()) / r.width())),
            max(0.0, min(1.0, (wy - r.y()) / r.height())),
        )

    def _near_first(self, wx: float, wy: float) -> bool:
        if not self._points:
            return False
        fp = self._to_w(*self._points[0])
        return (wx - fp.x()) ** 2 + (wy - fp.y()) ** 2 < self._CLOSE_D ** 2

    def _nearest_point_idx(self, wx: float, wy: float) -> int:
        """wx, wy ga _DRAG_D px dan yaqin nuqta indeksini qaytaradi, topilmasa -1."""
        best_idx = -1
        best_d2  = self._DRAG_D ** 2
        for i, pt in enumerate(self._points):
            wp = self._to_w(*pt)
            d2 = (wx - wp.x()) ** 2 + (wy - wp.y()) ** 2
            if d2 < best_d2:
                best_d2  = d2
                best_idx = i
        return best_idx

    # ── Mouse ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        wx, wy = float(event.pos().x()), float(event.pos().y())
        if event.button() == Qt.MouseButton.LeftButton:
            # Mavjud nuqtaga bosish → sudra rejimi
            idx = self._nearest_point_idx(wx, wy)
            if idx >= 0:
                self._drag_idx = idx
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            # 3+ nuqta va birinchiga yaqin → polygon yopiladi
            if len(self._points) >= 3 and self._near_first(wx, wy):
                self.update()
                return
            nx, ny = self._to_norm(wx, wy)
            self._points.append([nx, ny])
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            if self._points:
                self._points.pop()
                self._drag_idx = None
                self.update()

    def mouseMoveEvent(self, event):
        wx, wy = float(event.pos().x()), float(event.pos().y())
        self._hover = QPointF(wx, wy)

        if self._drag_idx is not None:
            nx, ny = self._to_norm(wx, wy)
            self._points[self._drag_idx] = [nx, ny]
            self.update()
            return

        # Kursor shakli: mavjud nuqtaga yaqin → qo'l kursori
        idx = self._nearest_point_idx(wx, wy)
        prev = self._hover_pt_idx
        self._hover_pt_idx = idx if idx >= 0 else None
        if self._hover_pt_idx != prev:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._hover_pt_idx is not None
                else Qt.CursorShape.CrossCursor
            )
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_idx is not None:
            self._drag_idx = None
            wx, wy = float(event.pos().x()), float(event.pos().y())
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._nearest_point_idx(wx, wy) >= 0
                else Qt.CursorShape.CrossCursor
            )

    def leaveEvent(self, event):
        self._hover = None
        self._hover_pt_idx = None
        self._drag_idx = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        self._frame_rect = self._calc_frame_rect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Fon
        p.fillRect(self.rect(), QColor("#0a0e14"))
        if not self._pixmap.isNull():
            p.drawPixmap(self._frame_rect.toRect(), self._pixmap)
        else:
            p.setPen(QColor("#475569"))
            p.setFont(QFont("Segoe UI", 13))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Kamera frame mavjud emas\nAvval Preview yoqing")

        pts = self._points
        n   = len(pts)
        col = self._color

        # Polygon to'ldirish (3+ nuqta)
        if n >= 3:
            wpoly = QPolygonF([self._to_w(*pt) for pt in pts])
            fill = QColor(col)
            fill.setAlpha(50)
            border = QColor(col)
            border.setAlpha(210)
            p.setBrush(QBrush(fill))
            p.setPen(QPen(border, 2))
            p.drawPolygon(wpoly)
        elif n == 2:
            p.setPen(QPen(col, 2, Qt.PenStyle.DashLine))
            p.drawLine(self._to_w(*pts[0]), self._to_w(*pts[1]))

        # Yopish nishoni (hover birinchi nuqta ustida)
        if self._hover and n >= 3 and self._near_first(self._hover.x(), self._hover.y()):
            fp = self._to_w(*pts[0])
            p.setBrush(QBrush(QColor(34, 197, 94, 100)))
            p.setPen(QPen(QColor("#22c55e"), 2))
            p.drawEllipse(fp, self._FIRST_R + 5, self._FIRST_R + 5)

        # Nuqtalar
        for i, pt in enumerate(pts):
            wp = self._to_w(*pt)
            is_active = (self._drag_idx == i) or (self._hover_pt_idx == i)

            if i == 0:
                color = QColor("#22c55e")
                r     = self._FIRST_R
            else:
                color = QColor(col)
                r     = self._PT_R

            # Aktiv nuqta: glow + kattaroq radius
            if is_active:
                r += 3
                glow = QColor(color)
                glow.setAlpha(55)
                p.setBrush(QBrush(glow))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(wp, r + 5, r + 5)

            p.setBrush(QBrush(color))
            p.setPen(QPen(QColor("#ffffff"), 1.5))
            p.drawEllipse(wp, r, r)
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            label = "▶" if i == 0 else str(i + 1)
            p.drawText(QRectF(wp.x() - r, wp.y() - r, r * 2, r * 2),
                       Qt.AlignmentFlag.AlignCenter, label)

        # Hover yo'naltiruvchi chiziq (drag bo'lmasa)
        if self._hover and n > 0 and self._drag_idx is None:
            p.setPen(QPen(QColor(255, 255, 255, 55), 1, Qt.PenStyle.DotLine))
            p.drawLine(self._to_w(*pts[-1]), self._hover)

        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._frame_rect = self._calc_frame_rect()

    # ── API ───────────────────────────────────────────────────────────────

    def clear(self):
        self._points.clear()
        self._drag_idx = None
        self._hover_pt_idx = None
        self.update()

    def get_points(self) -> list[list[float]]:
        return [list(pt) for pt in self._points]

    def update_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.update()


class PolygonEditorDialog(QDialog):
    """
    Kamera kadrida zona polygon chizish va tahrirlash dialogi.

    Args:
        pixmap          — kamera snapshot (QPixmap)
        existing_pts    — saqlangan nuqtalar [[nx, ny], ...] normalized 0-1
        cam_name        — dialog sarlavhasi
        existing_color  — saqlangan rang hex string (default "#f97316")
    """

    def __init__(self, pixmap: QPixmap, existing_pts: list,
                 cam_name: str = "Camera",
                 existing_color: str = "#f97316",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Zona chizish — {cam_name}")
        self.setMinimumSize(720, 540)
        self.resize(1000, 680)
        self.setModal(True)
        self._result_points: list | None = None
        self._result_color: str = existing_color
        self._color_dots: list[_ColorDot] = []
        self._build(pixmap, list(existing_pts), existing_color)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build(self, pixmap: QPixmap, existing_pts: list, existing_color: str):
        self.setStyleSheet(
            f"QDialog {{ background: {C('bg_main')}; }}"
            f"QLabel  {{ background: transparent; color: {C('text_primary')}; border: none; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # ── Sarlavha satri ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        title = QLabel("Zona chizish")
        title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 16px; font-weight: 900;"
        )
        hdr.addWidget(title)

        # Rang presetlari
        color_lbl = QLabel("Rang:")
        color_lbl.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        hdr.addWidget(color_lbl)

        for hex_col, tip in _PRESET_COLORS:
            dot = _ColorDot(hex_col, tip, self)
            dot.clicked.connect(lambda *_, c=hex_col, d=dot: self._on_color_dot(c, d))
            hdr.addWidget(dot)
            self._color_dots.append(dot)

        # Maxsus rang tugmasi
        custom_btn = QPushButton("+")
        custom_btn.setFixedSize(22, 22)
        custom_btn.setToolTip("Boshqa rang tanlash")
        custom_btn.setStyleSheet(
            f"QPushButton {{ background: {C('bg_hover')}; color: {C('text_secondary')};"
            f" border: 1px solid {C('border')}; border-radius: 11px;"
            f" font-size: 14px; font-weight: 900; }}"
            f"QPushButton:hover {{ background: {C('border')}; color: {C('text_primary')}; }}"
        )
        custom_btn.clicked.connect(self._on_custom_color)
        hdr.addWidget(custom_btn)

        hdr.addStretch()

        hint = QLabel(
            "Chap klik — nuqta qo'sh  ·  Nuqtani suring — tahrirlash  ·  "
            "O'ng klik — o'chirish  ·  3+ nuqta → tayyor"
        )
        hint.setStyleSheet(f"color: {C('text_muted')}; font-size: 10px;")
        hdr.addWidget(hint)
        root.addLayout(hdr)

        # ── Canvas ────────────────────────────────────────────────────────
        self._canvas = _PolygonCanvas(pixmap, existing_pts, self)
        root.addWidget(self._canvas, 1)

        # Boshlang'ich rangni o'rnatish
        self._apply_color(existing_color, animate_dot=True)

        # ── Status satri ──────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self._count_lbl = QLabel("0 nuqta")
        self._count_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 11px;"
        )
        status_row.addWidget(self._count_lbl)
        status_row.addStretch()

        zone_hint = QLabel("Zona ichidagilar aniqlanadi • Tashqarisidagilar e'tiborga olinmaydi")
        zone_hint.setStyleSheet(f"color: {C('text_muted')}; font-size: 10px;")
        status_row.addWidget(zone_hint)
        root.addLayout(status_row)

        # ── Tugmalar ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        clear_btn = QPushButton("Tozalash")
        clear_btn.setFixedHeight(36)
        clear_btn.setStyleSheet(self._secondary_style())
        clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setStyleSheet(self._secondary_style())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Saqlash")
        save_btn.setFixedHeight(36)
        save_btn.setStyleSheet(self._primary_style())
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

        # Nuqta sanagichni yangilash
        self._tick = QTimer(self)
        self._tick.setInterval(150)
        self._tick.timeout.connect(self._update_count)
        self._tick.start()

    # ── Rang boshqaruvi ───────────────────────────────────────────────────

    def _apply_color(self, hex_color: str, animate_dot: bool = False):
        self._result_color = hex_color
        self._canvas.set_color(QColor(hex_color))
        if animate_dot:
            for dot in self._color_dots:
                checked = dot._hex.lower() == hex_color.lower()
                dot.setChecked(checked)

    def _on_color_dot(self, hex_color: str, clicked_dot: _ColorDot):
        for dot in self._color_dots:
            dot.setChecked(dot is clicked_dot)
        self._apply_color(hex_color)

    def _on_custom_color(self):
        initial = QColor(self._result_color)
        color = QColorDialog.getColor(
            initial, self, "Rang tanlash",
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if color.isValid():
            for dot in self._color_dots:
                dot.setChecked(False)
            self._apply_color(color.name())

    # ── Ichki ─────────────────────────────────────────────────────────────

    def _update_count(self):
        n = len(self._canvas.get_points())
        if n == 0:
            msg = "Hali nuqta yo'q — kadrni bosib zona chizishni boshlang"
        elif n < 3:
            msg = f"{n} nuqta — polygon uchun kamida 3 ta kerak"
        else:
            msg = f"{n} nuqta — polygon tayyor ✓"
        self._count_lbl.setText(msg)

    def _on_clear(self):
        self._canvas.clear()

    def _on_save(self):
        pts = self._canvas.get_points()
        if len(pts) < 3:
            QMessageBox.warning(
                self, "Kam nuqta",
                "Polygon kamida 3 ta nuqtadan iborat bo'lishi kerak.\n"
                "Kadr ustiga bosib nuqtalar qo'shing."
            )
            return
        self._result_points = pts
        self.accept()

    # ── API ───────────────────────────────────────────────────────────────

    def result_points(self) -> list | None:
        """Accept dan keyin normalized [[x, y], ...] qaytaradi."""
        return self._result_points

    def result_color(self) -> str:
        """Accept dan keyin tanlangan rang hex string qaytaradi."""
        return self._result_color

    # ── Stilllar ─────────────────────────────────────────────────────────

    @staticmethod
    def _primary_style() -> str:
        return f"""
            QPushButton {{
                background: {C('accent')};
                color: white;
                border: none;
                border-radius: 7px;
                font-size: 12px;
                font-weight: 800;
                padding: 0 24px;
            }}
            QPushButton:hover {{ background: {C('accent_hover')}; }}
        """

    @staticmethod
    def _secondary_style() -> str:
        return f"""
            QPushButton {{
                background: {C('bg_hover')};
                color: {C('text_secondary')};
                border: 1px solid {C('border')};
                border-radius: 7px;
                font-size: 12px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: {C('border')};
                color: {C('text_primary')};
            }}
        """
