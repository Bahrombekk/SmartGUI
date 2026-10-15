"""
Kameralar — Figma "SafeZone — Kameralar" (16:92) aniq nusxasi.

Sarlavha (Diagnostika / Kamera qo‘shish) · chapda jadval kartasi (976):
qidiruv + chiplar + bo‘lim filtri, ustunlar Kamera/Bo‘lim/IP manzil/Holat/FPS/
Kadrda/Faol (x 13/283/473/614/759/827/911), qator 56px + 1px ajratgich ·
o‘ngda (420) jonli preview (236) va sozlamalar kartasi (Umumiy/Zona/AI/
Diagnostika tablari, O‘chirish / Qayta ishga tushirish / Saqlash).

MainWindow API: setup_cameras, update_frame, on_stats, on_status, on_error,
on_model_loaded, on_violation, set_search_text; signallar add_camera_requested,
departments_changed, reconnect_requested, cameras_changed.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF, QPixmap
from PyQt6.QtWidgets import (QWidget, QFrame, QHBoxLayout, QVBoxLayout, QScrollArea,
                             QStackedWidget, QLabel, QApplication)

from app.ui import fz
from app.ui.async_task import run_async
from app.ui.widgets.feed_view import FeedView

COLS = (13, 283, 473, 614, 759, 827, 911)       # Figma, karta kengligi 976
HEAD = ("Kamera", "Bo‘lim", "IP manzil", "Holat", "FPS", "Kadrda", "Faol")
SEL_BG = "#102641"


def _ip(rtsp: str) -> str:
    try:
        after = rtsp.split("@", 1)[1] if "@" in rtsp else rtsp.split("//", 1)[-1]
        return after.split("/", 1)[0].split(":", 1)[0] or "—"
    except Exception:
        return "—"


def _mask_rtsp(rtsp: str) -> str:
    if "@" in rtsp and "://" in rtsp:
        scheme, rest = rtsp.split("://", 1)
        cred, host = rest.split("@", 1)
        user = cred.split(":", 1)[0]
        return f"{scheme}://{user}:••••@{host}"
    return rtsp


def _cx(x: float, w: int) -> int:
    return int(round(x * w / 976.0)) if x > 13 else 13


# ════════════════════════════════════════════════════════════════════════════
#  Jadval qatori (56px)
# ════════════════════════════════════════════════════════════════════════════

class _Row(QWidget):
    clicked = pyqtSignal(int)
    toggled = pyqtSignal(int, bool)

    def __init__(self, cam: dict, dept: str, parent=None):
        super().__init__(parent)
        self.cam_id = int(cam.get("id"))
        self._sel = False
        self._hover = False
        self._status = "connecting"
        self._offline_since: float | None = None
        self.setFixedHeight(57)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb = FeedView(radius=4, bg="#101a2c", offline_text="", connecting_text="", parent=self)
        self.thumb.setGeometry(13, 12, 56, 32)
        self._off_icon = fz.Icon("win_min", 14, fz.MUTED, parent=self.thumb)
        self._off_icon.move(21, 9)
        self._off_icon.hide()
        self.name = fz.label(cam.get("name", f"Kamera {self.cam_id}"), 13, 500, fz.TEXT, parent=self)
        self.name.move(79, 10)
        self.cid = fz.label(f"CAM-{self.cam_id:02d}", 11, 400, fz.MUTED, mono=True, parent=self)
        self.cid.move(79, 30)
        self.dept = fz.label(dept or "—", 13, 400, fz.TEXT2, parent=self)
        self.ip = fz.label(_ip(cam.get("rtsp_url", "")), 12, 400, fz.TEXT2, mono=True, parent=self)
        self.dot = fz.Dot(fz.MUTED, 5, parent=self)
        self.st = fz.label("Ulanmoqda", 12.5, 500, fz.MUTED, parent=self)
        self.fps = fz.label("–", 12, 400, fz.TEXT, mono=True, parent=self)
        self.persons = fz.label("–", 12, 400, fz.TEXT, mono=True, parent=self)
        self.toggle = fz.Toggle(bool(cam.get("enabled", True)), parent=self)
        self.toggle.toggled.connect(lambda v: self.toggled.emit(self.cam_id, v))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        W = self.width()
        xs = [_cx(x, W) for x in COLS]
        self.name.setFixedWidth(max(40, xs[1] - 79 - 10))
        self.dept.setGeometry(xs[1], 19, xs[2] - xs[1] - 8, 16)
        self.ip.setGeometry(xs[2], 19, xs[3] - xs[2] - 8, 16)
        self.dot.move(xs[3], 25)
        self.st.setGeometry(xs[3] + 11, 19, xs[4] - xs[3] - 18, 16)
        self.fps.setGeometry(xs[4], 19, xs[5] - xs[4] - 6, 16)
        self.persons.setGeometry(xs[5], 19, xs[6] - xs[5] - 6, 16)
        self.toggle.move(xs[6], 18)

    def set_selected(self, v: bool):
        self._sel = v
        self.update()

    def set_status(self, status: str, fps: float | None = None, persons: int | None = None):
        if status == "offline" and self._status != "offline":
            self._offline_since = time.time()
        if status != "offline":
            self._offline_since = None
        self._status = status
        if status == "live":
            txt, col = "Onlayn", fz.GREEN
        elif status == "alert":
            txt, col = "Buzilish", fz.RED
        elif status == "offline":
            mins = int((time.time() - (self._offline_since or time.time())) // 60)
            txt, col = (f"Oflayn · {mins} daq" if mins else "Oflayn"), fz.MUTED
        elif status == "disabled":
            txt, col = "O‘chirilgan", fz.MUTED
        else:
            txt, col = "Ulanmoqda", fz.MUTED
        self.st.setText(txt)
        fz.restyle(self.st, 12.5, 500, col)
        self.dot.set_color(col)
        live = status in ("live", "alert")
        self.fps.setText(f"{fps:.1f}" if (live and fps is not None) else "–")
        self.persons.setText(str(persons) if (live and persons is not None) else "–")
        off = status in ("offline", "disabled")
        self._off_icon.setVisible(off)
        if off:
            self.thumb.show_offline("")

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.cam_id)

    def paintEvent(self, _):
        p = QPainter(self)
        W = self.width()
        if self._sel:
            p.fillRect(0, 0, W, 56, QColor(SEL_BG))
            p.fillRect(0, 0, 3, 56, QColor(fz.ACCENT))
        elif self._hover:
            p.fillRect(0, 0, W, 56, QColor(fz.INPUT))
        p.fillRect(0, 56, W, 1, QColor(fz.BORDER))
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  Jonli preview (420x236)
# ════════════════════════════════════════════════════════════════════════════

class _Preview(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fzPrev")
        self.setStyleSheet(f"QFrame#fzPrev {{ background:{fz.CARD_DEEP}; border:1px solid {fz.BORDER}; border-radius:12px; }}")
        self.feed = FeedView(radius=11, bg=fz.CARD_DEEP, parent=self)
        self._pts: list = []
        self.zone_layer = _ZonePaint(self)
        self.feed.frame_size_changed.connect(self._place)
        self.feed.live_changed.connect(lambda _live: self._sync_zone())
        self.live = fz.Pill("LIVE", fz.RED_FILL, "#ffffff", px=11, weight=700, mono=True, h=22, pad=8, radius=5,
                            dot="#ffffff", dot_size=6, gap=6, tracking=1, parent=self)
        self.cam = fz.Pill("CAM-01", fz.OVERLAY, fz.TEXT, px=11, weight=500, mono=True, h=22, pad=7, radius=5, parent=self)
        self.fps = fz.Pill("— fps", fz.OVERLAY, fz.TEXT, px=11, weight=500, mono=True, h=22, pad=7, radius=5, parent=self)
        self.zone = fz.Pill("Zona", fz.OVERLAY_STRONG, fz.TEXT, px=11, weight=500, mono=False, h=22, pad=9, radius=6,
                            border="rgba(31,182,255,0.55)", parent=self)
        self.zone.layout().insertWidget(0, fz.Icon("map_pin", 13))
        self.zone.layout().setSpacing(5)
        self.zone.hide()

    def set_zone(self, pts):
        self._pts = list(pts or [])
        self.zone.set_text(f"Xavfli zona · {len(self._pts)} nuqta")
        self._sync_zone()

    def zone_visible(self) -> bool:
        # Kamera oflayn / hali ulanmagan — zona ko'rsatilmaydi
        return self.feed.is_live() and len(self._pts) >= 3

    def _sync_zone(self):
        self.zone.setVisible(self.zone_visible())
        self._place()
        self.zone_layer.update()

    def set_header(self, cam_id: int, fps: float | None, live: bool):
        self.cam.set_text(f"CAM-{cam_id:02d}")
        self.fps.set_text(f"{fps:.1f} fps" if (live and fps) else "— fps")
        self.live.setVisible(live)
        self._place()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        W, H = self.width(), self.height()
        self.feed.setGeometry(1, 1, W - 2, H - 2)
        self.zone_layer.setGeometry(1, 1, W - 2, H - 2)
        for pl in (self.live, self.cam, self.fps, self.zone):
            pl.adjustSize()
            pl.raise_()
        self.live.move(12, 14)
        self.cam.move(80 if self.live.isVisible() else 12, 14)
        self.fps.move(W - 12 - self.fps.width(), 14)
        if self.zone_visible():
            top = min(self._pts, key=lambda q: q[1])
            tp = self.feed.map_norm(float(top[0]), float(top[1]))
            x = int(1 + tp.x() - self.zone.width() / 2)
            y = int(1 + tp.y() - 22 - 6)
            self.zone.move(max(8, min(W - self.zone.width() - 8, x)), max(42, y))


class _ZonePaint(QWidget):
    def __init__(self, preview: _Preview):
        super().__init__(preview)
        self._pv = preview
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        pts = self._pv._pts
        if not self._pv.zone_visible():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        feed = self._pv.feed
        pen = QPen(QColor(31, 182, 255, 220), 1.5, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.setBrush(QColor(31, 182, 255, 18))
        p.drawPolygon(QPolygonF([feed.map_norm(float(x), float(y)) for x, y in pts]))
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  Sozlamalar kartasi (420x504) — tablar
# ════════════════════════════════════════════════════════════════════════════

class _Tabs(QWidget):
    changed = pyqtSignal(int)

    def __init__(self, names: list[str], parent=None):
        super().__init__(parent)
        self._names = names
        self._cur = 0
        self._hover = -1
        self.setFixedHeight(33)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rects = []
        x = 0.0
        for n in names:
            w = 12 + fz.text_w(n, 13, 500) + 8         # Figma: matn x+12, o'ng 8, oraliq 3
            self._rects.append(QRectF(x, 0, w, 32))
            x += w + 3

    def mousePressEvent(self, e):
        for i, r in enumerate(self._rects):
            if r.contains(e.position()) and i != self._cur:
                self._cur = i
                self.update()
                self.changed.emit(i)

    def mouseMoveEvent(self, e):
        h = next((i for i, r in enumerate(self._rects) if r.contains(e.position())), -1)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0, 32, self.width(), 1, QColor(fz.BORDER))
        for i, (n, r) in enumerate(zip(self._names, self._rects)):
            act = i == self._cur
            p.setFont(fz.qfont(13, 600 if act else 500))
            p.setPen(QColor(fz.TEXT if (act or i == self._hover) else fz.TEXT2))
            p.drawText(QRectF(r.x() + 12, 3, r.width(), 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, n)
            if act:
                p.fillRect(QRectF(r.x(), 31, r.width(), 2), QColor(fz.ACCENT))
        p.end()


def _field_label(text: str) -> QLabel:
    return fz.label(text, 12, 500, fz.MUTED)


class _Input(QFrame):
    """#0E1A2E + #1A2842 r7 h31; matn x11; ixtiyoriy o'ng element."""

    def __init__(self, mono: bool = False, px: float = 13, right: QWidget | None = None, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QLineEdit
        self.setObjectName("fzInput")
        self.setFixedHeight(31)
        self.setStyleSheet(f"QFrame#fzInput {{ background:{fz.INPUT}; border:1px solid {fz.BORDER}; border-radius:7px; }}")
        self.edit = QLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setStyleSheet(
            f"QLineEdit {{ background:transparent; border:none; color:{fz.TEXT}; padding:0;"
            f" selection-background-color:{fz.ACCENT}; selection-color:{fz.ON_ACCENT}; {fz.css_font(px, 400, mono)} }}"
        )
        self._right = right
        if right is not None:
            right.setParent(self)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        rw = (self._right.width() + 14) if self._right is not None else 10
        self.edit.setGeometry(11, 1, self.width() - 11 - rw, 29)
        if self._right is not None:
            self._right.move(self.width() - self._right.width() - 12, (31 - self._right.height()) // 2)


class _LinkText(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"color:{fz.TEXT2}; background:transparent; border:none; {fz.css_font(12, 500)}")
        self.adjustSize()

    def mousePressEvent(self, e):
        self.clicked.emit()


class _SettingsCard(QFrame):
    save_requested = pyqtSignal(int, dict)
    delete_requested = pyqtSignal(int)
    restart_requested = pyqtSignal(int)
    zone_requested = pyqtSignal(int)
    zone_clear_requested = pyqtSignal(int)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._cam_id: int | None = None
        self._dept_ids: list = []
        self.setObjectName("fzCamSet")
        self.setStyleSheet(f"QFrame#fzCamSet {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:12px; }}")
        self.tabs = _Tabs(["Umumiy", "Zona", "AI", "Diagnostika"], self)
        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background:transparent;")
        self.tabs.changed.connect(self.stack.setCurrentIndex)
        self.stack.addWidget(self._page_general())
        self.stack.addWidget(self._page_zone())
        self.stack.addWidget(self._page_ai())
        self.stack.addWidget(self._page_diag())
        self.btn_del = fz.Button("O‘chirish", "danger", icon="trash", icon_size=14, h=31, px=13, pad=12, gap=6, radius=8, parent=self)
        self.btn_restart = fz.Button("Qayta ishga tushirish", "ghost", icon="refresh", icon_size=14, h=31, px=13,
                                     pad=13, gap=6, radius=8, parent=self)
        self.btn_save = fz.Button("Saqlash", "primary", h=31, px=13, pad=16, radius=8, parent=self)
        self.btn_del.clicked.connect(lambda: self._cam_id is not None and self.delete_requested.emit(self._cam_id))
        self.btn_restart.clicked.connect(lambda: self._cam_id is not None and self.restart_requested.emit(self._cam_id))
        self.btn_save.clicked.connect(self._emit_save)

    # ── tab sahifalari ──
    def _page_general(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        self.l_name = _field_label("Kamera nomi")
        self.l_name.setParent(w)
        self.l_dept = _field_label("Bo‘lim")
        self.l_dept.setParent(w)
        self.in_name = _Input(parent=w)
        self.in_dept = fz.Dropdown(["—"], 0, h=31, bg=fz.INPUT, fg=fz.TEXT, px=13, weight=400, pad=11, radius=7, parent=w)
        self.l_rtsp = _field_label("RTSP manzil")
        self.l_rtsp.setParent(w)
        self.copy = _LinkText("Nusxa")
        self.copy.clicked.connect(self._copy)
        self.in_rtsp = _Input(mono=False, px=12.5, right=self.copy, parent=w)
        self.in_rtsp.edit.textEdited.connect(lambda _: setattr(self, "_rtsp_edited", True))
        self.en_t = fz.label("Kamerani yoqish", 13, 500, fz.TEXT, parent=w)
        self.en_d = fz.label("O‘chirilsa oqim va AI tahlili to‘xtaydi", 11.5, 400, fz.MUTED, parent=w)
        self.en_tg = fz.Toggle(True, parent=w)
        self.div = fz.hline()
        self.div.setParent(w)
        self.z_t = fz.label("Xavfli zona", 13, 500, fz.TEXT, parent=w)
        self.z_d = fz.label("Faqat zona ichidagi ishchilar tekshiriladi", 11.5, 400, fz.MUTED, parent=w)
        self.z_btn = fz.Button("Zonani chizish", "ghost", icon="pencil", icon_size=13, h=28, px=12.5, weight=500,
                               pad=12, gap=6, radius=7, parent=w)
        self.z_btn.clicked.connect(lambda: self._cam_id is not None and self.zone_requested.emit(self._cam_id))
        self._gen = w
        return w

    def _info_page(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(17, 6, 17, 0)
        lay.setSpacing(0)
        return w, lay

    def _kv(self, lay: QVBoxLayout, key: str) -> QLabel:
        row = QWidget()
        row.setFixedHeight(40)
        row.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(fz.label(key, 12.5, 400, fz.MUTED))
        rl.addStretch(1)
        v = fz.label("—", 12.5, 500, fz.TEXT, mono=True)
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rl.addWidget(v)
        lay.addWidget(row)
        lay.addWidget(fz.hline())
        return v

    def _page_zone(self) -> QWidget:
        w, lay = self._info_page()
        self.zv_points = self._kv(lay, "Nuqtalar soni")
        self.zv_state = self._kv(lay, "Holat")
        lay.addSpacing(14)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        draw = fz.Button("Zonani chizish", "ghost", icon="pencil", icon_size=13, h=31, px=12.5, weight=500, pad=12, gap=6, radius=7)
        draw.clicked.connect(lambda: self._cam_id is not None and self.zone_requested.emit(self._cam_id))
        clear = fz.Button("Tozalash", "outline", icon="trash", icon_size=13, h=31, px=12.5, weight=500, pad=12, gap=6, radius=7)
        clear.clicked.connect(lambda: self._cam_id is not None and self.zone_clear_requested.emit(self._cam_id))
        btns.addWidget(draw)
        btns.addWidget(clear)
        btns.addStretch(1)
        lay.addLayout(btns)
        lay.addStretch(1)
        return w

    def _page_ai(self) -> QWidget:
        w, lay = self._info_page()
        self.ai_fps = self._kv(lay, "Tahlil FPS")
        self.ai_persons = self._kv(lay, "Kadrdagi ishchilar")
        self.ai_det = self._kv(lay, "Bugungi aniqlashlar")
        self.ai_viol = self._kv(lay, "Bugungi buzilishlar")
        lay.addStretch(1)
        return w

    def _page_diag(self) -> QWidget:
        w, lay = self._info_page()
        self.dg_state = self._kv(lay, "Ulanish")
        self.dg_host = self._kv(lay, "Manzil")
        self.dg_err = self._kv(lay, "Oxirgi xato")
        lay.addStretch(1)
        return w

    # ── joylashuv (Figma koordinatalari, karta ichida) ──
    def resizeEvent(self, e):
        super().resizeEvent(e)
        W, H = self.width(), self.height()
        inner = W - 34
        self.tabs.setGeometry(17, 17, inner, 33)
        self.stack.setGeometry(0, 50, W, H - 50 - 63)
        half = (inner - 12) // 2
        self.l_name.setGeometry(17, 13, half, 15)
        self.l_dept.setGeometry(17 + half + 12, 13, half, 15)
        self.in_name.setGeometry(17, 34, half, 31)
        self.in_dept.move(17 + half + 12, 34)
        self.in_dept.setFixedWidth(half)
        self.l_rtsp.setGeometry(17, 79, inner, 15)
        self.in_rtsp.setGeometry(17, 100, inner, 31)
        self.en_t.setGeometry(17, 152, inner - 50, 17)
        self.en_d.setGeometry(17, 174, inner - 50, 14)
        self.en_tg.move(W - 17 - 34, 161)
        self.div.setGeometry(17, 204, inner, 1)
        self.z_t.setGeometry(17, 218, inner - 140, 17)
        self.z_d.setGeometry(17, 240, inner - 140, 14)
        self.z_btn.move(W - 17 - self.z_btn.width(), 223)
        y = H - 16 - 31
        self.btn_del.move(17, y)
        self.btn_save.move(W - 17 - self.btn_save.width(), y)
        self.btn_restart.move(self.btn_save.x() - 8 - self.btn_restart.width(), y)

    # ── ma'lumot ──
    def load(self, cam: dict):
        self._cam_id = int(cam.get("id"))
        self._rtsp_full = cam.get("rtsp_url", "")
        self._rtsp_edited = False
        self.in_name.edit.setText(cam.get("name", ""))
        self.in_rtsp.edit.setText(_mask_rtsp(self._rtsp_full))
        self.in_rtsp.edit.setCursorPosition(0)
        self.en_tg.set_checked(bool(cam.get("enabled", True)))
        deps = self.cfg.get_departments() if self.cfg else []
        self._dept_ids = [d.get("id") for d in deps]
        cur = self._dept_ids.index(cam.get("department_id")) if cam.get("department_id") in self._dept_ids else 0
        self.in_dept.set_options([d.get("name", "Bo‘lim") for d in deps] or ["—"], cur)
        if self.width() > 100:
            self.in_dept.setFixedWidth((self.width() - 34 - 12) // 2)
        pts = cam.get("polygon_points") or []
        self.zv_points.setText(f"{len(pts)} ta" if pts else "—")
        self.zv_state.setText("Faol" if len(pts) >= 3 else "Butun kadr tekshiriladi")
        self.dg_host.setText(_ip(self._rtsp_full))

    def set_runtime(self, status: str, fps, persons, det, viol, err: str = ""):
        self.ai_fps.setText(f"{fps:.1f}" if fps else "—")
        self.ai_persons.setText(str(persons) if persons is not None else "—")
        self.ai_det.setText(str(det) if det is not None else "—")
        self.ai_viol.setText(str(viol) if viol is not None else "—")
        self.dg_state.setText({"live": "Onlayn", "alert": "Onlayn", "offline": "Oflayn",
                               "connecting": "Ulanmoqda", "disabled": "O‘chirilgan"}.get(status, status))
        self.dg_err.setText((err or "—")[:40])
        self.dg_err.setToolTip(err or "")

    def _copy(self):
        QApplication.clipboard().setText(getattr(self, "_rtsp_full", "") or "")
        try:
            from app.ui.widgets.toast import show_toast
            show_toast(self, "RTSP manzil nusxalandi", "success")
        except Exception:
            pass

    def _emit_save(self):
        if self._cam_id is None:
            return
        i = self.in_dept.current()
        data = {
            "name": self.in_name.edit.text().strip() or f"Kamera {self._cam_id}",
            "enabled": self.en_tg.is_checked(),
            "department_id": self._dept_ids[i] if 0 <= i < len(self._dept_ids) else None,
        }
        if getattr(self, "_rtsp_edited", False):
            data["rtsp_url"] = self.in_rtsp.edit.text().strip()
        self.save_requested.emit(self._cam_id, {k: v for k, v in data.items() if v is not None})


# ════════════════════════════════════════════════════════════════════════════
#  CamerasPage
# ════════════════════════════════════════════════════════════════════════════

class CamerasPage(QWidget):
    add_camera_requested = pyqtSignal()
    focus_changed = pyqtSignal(int)        # o'ngdagi katta preview kamerasi
    departments_changed = pyqtSignal()
    reconnect_requested = pyqtSignal(int)
    cameras_changed = pyqtSignal()

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        fz.init_fonts()
        self.db = db
        self.cfg = config_manager
        self._cameras: list[dict] = []
        self._rows: dict[int, _Row] = {}
        self._status: dict[int, str] = {}
        self._stats: dict[int, dict] = {}
        self._errors: dict[int, str] = {}
        self._alert_until: dict[int, float] = {}
        self._selected: int | None = None
        self._filter = "all"
        self._dept_filter = None
        self._dept_list: list = []
        self._search = ""
        self._viol_counts: dict = {}
        self._viol_counts_ts = 0.0
        self._viol_busy = False
        self.setObjectName("fzCameras")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#fzCameras {{ background:{fz.BG}; }}")
        self._build()
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh_alerts)
        self._tick.start(5000)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 22, 16, 16)
        root.setSpacing(0)
        self.header = fz.PageHeader("Kameralar", "")
        diag = fz.Button("Diagnostika", "ghost", icon="refresh", icon_size=15, h=31, px=13, weight=500, pad=14, gap=7)
        diag.clicked.connect(self._diagnose)
        add = fz.Button("Kamera qo‘shish", "primary", icon="plus", icon_size=15, h=31, px=13, weight=600, pad=14, gap=7)
        add.clicked.connect(self.add_camera_requested.emit)
        self.header.add_right(diag)
        self.header.add_right(add)
        root.addWidget(self.header)
        root.addSpacing(15)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_table(), 976)
        right = QWidget()
        right.setStyleSheet("background:transparent;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        self.preview = _Preview()
        rl.addWidget(self.preview)
        self.settings = _SettingsCard(self.cfg)
        self.settings.save_requested.connect(self._on_save)
        self.settings.delete_requested.connect(self._on_delete)
        self.settings.restart_requested.connect(self._on_restart)
        self.settings.zone_requested.connect(self._on_zone)
        self.settings.zone_clear_requested.connect(self._on_zone_clear)
        rl.addWidget(self.settings, 1)
        self._right = right
        body.addWidget(right, 420)
        root.addLayout(body, 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._fit_preview)

    def _fit_preview(self):
        w = self._right.width()
        if w > 50:
            self.preview.setFixedHeight(int(round(w * 236 / 420)))

    def _build_table(self) -> QFrame:
        card = fz.card(fz.CARD, fz.BORDER, 12)
        self._table = card
        self.search = fz.SearchBox("Kamera qidirish", 260, parent=card)
        self.search.move(15, 13)
        self.search.edit.textChanged.connect(self.set_search_text)
        self.chips = {
            "all": fz.Chip("Barchasi", "0", True, parent=card),
            "live": fz.Chip("Onlayn", "0", parent=card),
            "offline": fz.Chip("Oflayn", "0", parent=card),
        }
        for k, c in self.chips.items():
            c.clicked.connect(lambda _, kk=k: self._set_filter(kk))
        self.dept_dd = fz.Dropdown(["Bo‘lim"], 0, icon="building", parent=card)
        self.dept_dd.changed.connect(self._on_dept_filter)
        self._head = QWidget(card)
        self._head.setStyleSheet("background:transparent;")
        self._head_lbls = [fz.label(t, 12, 500, fz.MUTED, parent=self._head) for t in HEAD]
        self._div1 = fz.hline()
        self._div1.setParent(card)
        self._div2 = fz.hline()
        self._div2.setParent(card)
        self._scroll = QScrollArea(card)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }"
                                   "QScrollArea > QWidget > QWidget { background:transparent; }")
        host = QWidget()
        self._rows_lay = QVBoxLayout(host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(0)
        self._rows_lay.addStretch(1)
        self._scroll.setWidget(host)
        self._empty = fz.label("Kamera topilmadi", 13, 400, fz.MUTED, parent=card)
        self._empty.hide()
        card.installEventFilter(self)
        return card

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self._table and ev.type() == QEvent.Type.Resize:
            self._layout_table()
        return super().eventFilter(obj, ev)

    def _layout_table(self):
        W, H = self._table.width(), self._table.height()
        x = 15 + 260 + 8
        for c in self.chips.values():
            c.move(x, 15)
            x += c.width() + 8
        self.dept_dd.move(x, 15)
        self._div1.setGeometry(1, 57, W - 2, 1)
        self._head.setGeometry(1, 58, W - 2, 36)
        for lbl, cx in zip(self._head_lbls, COLS):
            lbl.move(_cx(cx, W) - 1, 10)
        self._div2.setGeometry(1, 94, W - 2, 1)
        self._scroll.setGeometry(1, 95, W - 2, H - 96)
        self._empty.move(16, 112)

    # ── ma'lumot ──
    def _dept_name(self, cam) -> str:
        try:
            d = self.cfg.get_department_by_id(cam.get("department_id"))
            return d.get("name", "—") if d else "—"
        except Exception:
            return "—"

    def setup_cameras(self, cameras: list):
        all_cams = list(self.cfg.get_cameras()) if self.cfg else list(cameras)
        self._cameras = all_cams or list(cameras)
        enabled_ids = {int(c.get("id")) for c in cameras}
        self._status = {int(c.get("id")): ("connecting" if int(c.get("id")) in enabled_ids else "disabled")
                        for c in self._cameras}
        self._stats.clear()
        self._errors.clear()
        self._dept_list = self.cfg.get_departments() if self.cfg else []
        # Saqlash/qayta ishga tushirishdan keyin ham foydalanuvchi tanlovi saqlanadi
        dep_ids = [d.get("id") for d in self._dept_list]
        if self._dept_filter not in dep_ids:
            self._dept_filter = None
        dep_idx = 0 if self._dept_filter is None else dep_ids.index(self._dept_filter) + 1
        self.dept_dd.set_options(["Bo‘lim"] + [d.get("name", "Bo‘lim") for d in self._dept_list], dep_idx)
        self._viol_counts_ts = 0.0
        self._render_rows()
        self._update_counts()
        all_ids = {int(c.get("id")) for c in self._cameras}
        first = self._selected if self._selected in all_ids else None
        if first is None:
            first = next((int(c.get("id")) for c in self._cameras if int(c.get("id")) in enabled_ids), None)
        if first is None and self._cameras:
            first = int(self._cameras[0].get("id"))
        if first is not None:
            self._select(first)
        self._layout_table()

    def _filtered(self) -> list[dict]:
        out = []
        for c in self._cameras:
            cid = int(c.get("id"))
            st = self._status.get(cid, "connecting")
            if self._filter == "live" and st not in ("live", "alert"):
                continue
            if self._filter == "offline" and st not in ("offline", "disabled"):
                continue
            if self._dept_filter is not None and c.get("department_id") != self._dept_filter:
                continue
            if self._search and self._search not in c.get("name", "").lower() \
                    and self._search not in _ip(c.get("rtsp_url", "")):
                continue
            out.append(c)
        return out

    def _render_rows(self):
        for r in self._rows.values():
            r.deleteLater()
        self._rows.clear()
        while self._rows_lay.count() > 1:
            it = self._rows_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        rows = self._filtered()
        self._empty.setVisible(not rows)
        for c in rows:
            cid = int(c.get("id"))
            r = _Row(c, self._dept_name(c))
            r.clicked.connect(self._select)
            r.toggled.connect(self._on_toggle)
            self._rows[cid] = r
            self._rows_lay.insertWidget(self._rows_lay.count() - 1, r)
            self._apply_row(cid)
        if self._selected in self._rows:
            self._rows[self._selected].set_selected(True)

    def _row_status(self, cid: int) -> str:
        st = self._status.get(cid, "connecting")
        if st == "live" and self._alert_until.get(cid, 0) > time.time():
            return "alert"
        return st

    def _apply_row(self, cid: int):
        r = self._rows.get(cid)
        if r is None:
            return
        s = self._stats.get(cid, {})
        r.set_status(self._row_status(cid), s.get("fps"), s.get("active_persons"))

    def _update_counts(self):
        total = len(self._cameras)
        online = sum(1 for s in self._status.values() if s in ("live", "alert"))
        offline = sum(1 for s in self._status.values() if s in ("offline", "disabled"))
        deps = len({c.get("department_id") for c in self._cameras})
        self.header.sub.setText(f"{total} ta kamera · {online} onlayn · {deps} bo‘limda")
        self.chips["all"].set_count(total)
        self.chips["live"].set_count(online)
        self.chips["offline"].set_count(offline)
        self._layout_table()

    def _set_filter(self, key: str):
        self._filter = key
        for k, c in self.chips.items():
            c.set_active(k == key)
        self._render_rows()

    def _on_dept_filter(self, i: int):
        self._dept_filter = None if i == 0 else self._dept_list[i - 1].get("id")
        self._render_rows()

    def set_search_text(self, text: str):
        self._search = (text or "").strip().lower()
        if self.search.edit.text() != (text or ""):
            self.search.edit.blockSignals(True)
            self.search.edit.setText(text or "")
            self.search.edit.blockSignals(False)
        self._render_rows()

    def _select(self, cam_id: int):
        self._selected = int(cam_id)
        self.focus_changed.emit(self._selected)
        for cid, r in self._rows.items():
            r.set_selected(cid == self._selected)
        cam = self.cfg.get_camera_by_id(self._selected) if self.cfg else None
        if not cam:
            return
        self.preview.feed.clear()
        st = self._status.get(self._selected)
        if st in ("offline", "disabled"):
            self.preview.feed.show_offline("Signal yo‘q · qayta ulanmoqda" if st == "offline" else "Kamera o‘chirilgan")
        self.preview.set_zone(cam.get("polygon_points") or [])
        self.settings.load(cam)
        self._update_selected_runtime()

    def _update_selected_runtime(self):
        cid = self._selected
        if cid is None:
            return
        s = self._stats.get(cid, {})
        st = self._row_status(cid)
        self.preview.set_header(cid, s.get("fps"), st in ("live", "alert"))
        viol = self._viol_counts.get(cid)
        self._refresh_viol_counts()
        self.settings.set_runtime(st, s.get("fps"), s.get("active_persons"), s.get("detections_today"),
                                  viol, self._errors.get(cid, ""))

    def _refresh_viol_counts(self):
        """Bugungi buzilishlar soni — fonda, ko'pi bilan 10 s da bir marta
        (on_stats har soniyada keladi, GROUP BY'ni GUI thread'da qilmaymiz)."""
        if self._viol_busy or time.time() - self._viol_counts_ts < 10:
            return
        self._viol_busy = True

        def done(counts):
            self._viol_busy = False
            self._viol_counts_ts = time.time()
            self._viol_counts = {int(k): int(v) for k, v in (counts or {}).items()
                                 if str(k).lstrip("-").isdigit()}
            self._update_selected_runtime()

        def failed(_exc):
            self._viol_busy = False
            self._viol_counts_ts = time.time()

        run_async(self, self.db.get_today_counts_by_camera, done, failed)

    # ── worker yangilanishlari ──
    def update_frame(self, cam_id: int, frame):
        r = self._rows.get(cam_id)
        if r is not None and r.isVisible():
            r.thumb.set_frame(frame)
        if cam_id == self._selected:
            self.preview.feed.set_frame(frame)

    def on_stats(self, cam_id: int, stats: dict):
        cam_id = int(cam_id)
        self._stats[cam_id] = dict(stats)
        old = self._status.get(cam_id)
        new = "live" if stats.get("connected") else ("offline" if old in ("live", "offline") else "connecting")
        self._status[cam_id] = new
        self._apply_row(cam_id)
        if old != new:
            self._update_counts()
            if self._filter != "all":
                self._render_rows()
        if cam_id == self._selected:
            self._update_selected_runtime()

    def on_status(self, cam_id: int, text: str):
        pass

    def on_error(self, cam_id: int, msg: str):
        cam_id = int(cam_id)
        self._errors[cam_id] = msg or ""
        self._status[cam_id] = "offline"
        self._apply_row(cam_id)
        self._update_counts()
        if cam_id == self._selected:
            self.preview.feed.show_offline("Signal yo‘q · qayta ulanmoqda")
            self._update_selected_runtime()

    def on_model_loaded(self, cam_id: int):
        pass

    def on_violation(self, data: dict):
        try:
            cid = int(data.get("camera_id"))
        except (TypeError, ValueError):
            return
        self._alert_until[cid] = time.time() + 90
        self._apply_row(cid)

    def _refresh_alerts(self):
        now = time.time()
        for cid in [c for c, t in self._alert_until.items() if t <= now]:
            self._alert_until.pop(cid, None)
            self._apply_row(cid)
        for cid in list(self._rows):
            if self._status.get(cid) == "offline":
                self._apply_row(cid)

    # ── CRUD ──
    def _persist(self, msg: str) -> bool:
        ok = self.cfg.save()
        try:
            from app.ui.widgets.toast import show_toast
            show_toast(self, msg if ok else "Saqlanmadi: " + (getattr(self.cfg, "last_save_error", "") or ""),
                       "success" if ok else "error")
        except Exception:
            pass
        return ok

    def _on_toggle(self, cam_id: int, enabled: bool):
        self.cfg.update_camera(cam_id, enabled=bool(enabled))
        if self._persist("Kamera " + ("yoqildi" if enabled else "o‘chirildi")):
            self.cameras_changed.emit()

    def _on_save(self, cam_id: int, data: dict):
        self.cfg.update_camera(cam_id, **data)
        if self._persist("Kamera sozlamalari saqlandi"):
            self.cameras_changed.emit()

    def _on_delete(self, cam_id: int):
        from PyQt6.QtWidgets import QMessageBox
        from app.ui.widgets.app_dialog import AppMessageBox
        cam = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", "kamera") if cam else "kamera"
        if AppMessageBox.question(self, "Kamerani o‘chirish", f"“{name}” kamerasini o‘chirmoqchimisiz?",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if not self.cfg.remove_camera(cam_id):
            AppMessageBox.warning(self, "Xatolik", "Kamida 1 ta kamera bo‘lishi shart.")
            return
        self._selected = None
        if self._persist(f"Kamera o‘chirildi: “{name}”"):
            self.cameras_changed.emit()

    def _on_restart(self, cam_id: int):
        self.reconnect_requested.emit(int(cam_id))

    def _diagnose(self):
        off = [int(c.get("id")) for c in self._cameras if self._status.get(int(c.get("id"))) == "offline"]
        for cid in off:
            self.reconnect_requested.emit(cid)
        try:
            from app.ui.widgets.toast import show_toast
            show_toast(self, f"{len(off)} ta oflayn kamera qayta ulanmoqda" if off else "Barcha kameralar ishlayapti", "info")
        except Exception:
            pass

    def _on_zone(self, cam_id: int):
        try:
            from app.ui.widgets.polygon_editor import PolygonEditorDialog
        except Exception:
            return
        cam = self.cfg.get_camera_by_id(cam_id)
        if not cam:
            return
        img = self.preview.feed.image()
        if img is not None:
            pix = QPixmap.fromImage(img)
        else:
            pix = QPixmap(1280, 720)
            pix.fill(QColor("#0a1220"))
        dlg = PolygonEditorDialog(pix, cam.get("polygon_points", []), cam_name=cam.get("name", "Kamera"),
                                  existing_color=cam.get("polygon_color", "#1fb6ff"), parent=self)
        if dlg.exec():
            pts = dlg.result_points()
            if pts is not None:
                self.cfg.update_camera(cam_id, polygon_points=pts, polygon_color=dlg.result_color())
                if self._persist("Zona saqlandi"):
                    self.preview.set_zone(pts)
                    self.settings.load(self.cfg.get_camera_by_id(cam_id))
                    self.cameras_changed.emit()

    def _on_zone_clear(self, cam_id: int):
        self.cfg.update_camera(cam_id, polygon_points=[])
        if self._persist("Zona tozalandi"):
            self.preview.set_zone([])
            self.settings.load(self.cfg.get_camera_by_id(cam_id))
            self.cameras_changed.emit()
