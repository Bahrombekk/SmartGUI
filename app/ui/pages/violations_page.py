"""
Hodisalar — Figma "SafeZone — Hodisalar" (16:47) aniq nusxasi.

Sarlavha + davr (Bugun/7 kun/30 kun/Oraliq) + Eksport (CSV) ·
filtr qatori: holat chiplari (r14) | kamera / bo‘lim / ishonch dropdown'lari |
to‘r/ro‘yxat tugmasi · dalil kartalari (245x211, 4 ustun, oraliq 12/10) ·
o‘ngda hodisa tafsiloti paneli (380): dalil kadr, kadrlar lentasi, meta,
Tasdiqlash / Noto‘g‘ri aniqlash / ⋮.

Ko‘rib chiqish holati DB'da `review_status` ustunida saqlanadi. Barcha filtrlar
(davr, kamera, bo‘lim, ishonch, holat, qidiruv) SQL'da qo‘llanadi; chip sonlari
COUNT so‘rovlaridan, CSV eksport — limitsiz alohida so‘rov.
MainWindow API: _load_violations, add_new_violation, set_search_text, reload_departments.
"""
from __future__ import annotations

import csv
import os
import shutil
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QSize, QObject, pyqtSignal, QUrl, QDate
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QImage, QImageReader, QDesktopServices
from PyQt6.QtWidgets import (QWidget, QFrame, QHBoxLayout, QVBoxLayout, QScrollArea, QLabel,
                             QFileDialog, QPushButton, QMenu, QDialog, QDateEdit, QGridLayout)

from app.ui import fz
from app.ui.async_task import run_async
from app.ui.widgets.frameless import FramedDialog
from app.ui.widgets.toast import show_toast

_PAGE_LIMIT = 300
STATUS = {
    "new": ("Yangi", fz.RED),
    "review": ("Ko‘rib chiqilmoqda", fz.MUTED),
    "confirmed": ("Tasdiqlandi", fz.GREEN),
    "rejected": ("Noto‘g‘ri", fz.MUTED),
}
WELL = "#101a2c"


def _vid(v: dict):
    return v.get("id") if v.get("id") is not None else (v.get("track_id"), v.get("timestamp"), v.get("camera_name"))


def _ts_dt(v) -> datetime | None:
    ts = v.get("timestamp") if isinstance(v, dict) else v
    try:
        return datetime.fromtimestamp(float(ts)) if ts else None
    except Exception:
        return None


def _abs(path: str) -> Path | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p if p.exists() else None


# ── fon yuklovchi (rasmlar UI thread'ni to'xtatmasin) ──────────────────────────

class _ImgLoader(QObject):
    """Rasmlarni fon thread'ida o'qiydi; ikki alohida LRU kesh:

    * "thumb" — karta/ro'yxat o'lchamidagi kichik nusxa (ko'p, arzon);
    * "full"  — tafsilot paneli uchun katta nusxa (kam).

    Karta keshi sahifa limitidan katta — yangi hodisa kelganda yoki filtr
    o'zgarganda 300 ta rasm diskdan qayta o'qilmaydi.
    """
    loaded = pyqtSignal(str, QImage, str)          # path, rasm, kind
    _raw = pyqtSignal(str, QImage, str)

    THUMB_BOX = (320, 200)                         # karta ~245x154 (DPR 1.25 gacha)
    FULL_W = 900
    CAPS = {"thumb": _PAGE_LIMIT + 200, "full": 24}

    _inst = None

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = _ImgLoader()
        return cls._inst

    def __init__(self):
        super().__init__()
        self._caches: dict[str, OrderedDict] = {"thumb": OrderedDict(), "full": OrderedDict()}
        self._pending: set[tuple[str, str]] = set()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="viol-img")
        self._raw.connect(self._store)              # GUI thread'da keshga yoziladi

    def cached(self, path: str, kind: str = "thumb") -> QImage | None:
        c = self._caches[kind]
        img = c.get(path)
        if img is not None:
            c.move_to_end(path)
        return img

    def request(self, path: str, kind: str = "thumb") -> QImage | None:
        if not path:
            return None
        img = self.cached(path, kind)
        if img is not None or (kind, path) in self._pending:
            return img
        self._pending.add((kind, path))
        box = self.THUMB_BOX if kind == "thumb" else None

        def job():
            rd = QImageReader(path)
            rd.setAutoTransform(True)
            size = rd.size()
            if size.isValid() and size.width() > 0 and size.height() > 0:
                if box is not None:
                    s = min(1.0, max(box[0] / size.width(), box[1] / size.height()))
                else:
                    s = min(1.0, self.FULL_W / size.width())
                if s < 1.0:
                    rd.setScaledSize(QSize(max(1, round(size.width() * s)), max(1, round(size.height() * s))))
            self._raw.emit(path, rd.read(), kind)
        # 300 ta kartada 300 ta thread ochilmasin — cheklangan pool
        self._pool.submit(job)
        return None

    def _store(self, path: str, img: QImage, kind: str):
        self._pending.discard((kind, path))
        if not img.isNull():
            c = self._caches[kind]
            c[path] = img
            c.move_to_end(path)
            while len(c) > self.CAPS[kind]:
                c.popitem(last=False)
        self.loaded.emit(path, img, kind)


def _cover(p: QPainter, r: QRectF, img: QImage | QPixmap):
    iw, ih = img.width(), img.height()
    if iw <= 0 or ih <= 0:
        return
    s = max(r.width() / iw, r.height() / ih)
    sw, sh = r.width() / s, r.height() / s
    src = QRectF((iw - sw) / 2, (ih - sh) / 2, sw, sh)
    if isinstance(img, QImage):
        p.drawImage(r, img, src)
    else:
        p.drawPixmap(r, img, src)


# ════════════════════════════════════════════════════════════════════════════
#  Dalil kartasi (245x211)
# ════════════════════════════════════════════════════════════════════════════

class _Card(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, v: dict, status: str, selected: bool, parent=None):
        super().__init__(parent)
        self.v, self.status, self.selected = v, status, selected
        self._hover = False
        self._img: QImage | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        p = _abs(v.get("full_path") or "") or _abs(v.get("crop_path") or "")
        self._path = str(p) if p else ""
        if self._path:
            self._img = _ImgLoader.get().request(self._path, "thumb")

    def on_loaded(self, path: str, img: QImage):
        if path == self._path:
            self._img = img
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.v)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        W, H = self.width(), self.height()
        img_h = H - 57
        outer = QRectF(0, 0, W, H)
        clip = QPainterPath()
        clip.addRoundedRect(outer, 10, 10)
        p.setClipPath(clip)
        p.fillRect(outer, QColor(fz.CARD))
        ir = QRectF(0, 0, W, img_h)
        p.fillRect(ir, QColor(WELL))
        if self._img is not None and not self._img.isNull():
            _cover(p, ir, self._img)
        else:
            p.drawPixmap(QPointF(W / 2 - 9, img_h / 2 - 9), fz.svg_pixmap("video_off", 18, 18))
        p.fillRect(QRectF(0, img_h - 1, W, 1), QColor(fz.BORDER))
        # SHLEM YO'Q
        p.setFont(fz.qfont(10.5, 700, mono=True, tracking=0.5))
        t = "SHLEM YO‘Q"
        tw = p.fontMetrics().horizontalAdvance(t) + 14
        pill = QRectF(8, 9, tw, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fz.RED_FILL))
        p.drawRoundedRect(pill, 4, 4)
        p.setPen(QColor("#ffffff"))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, t)
        conf = self.v.get("confidence")
        if conf is not None:
            p.setFont(fz.qfont(11, 700, mono=True))
            p.setPen(QColor(0, 0, 0, 120))
            p.drawText(QRectF(0, 10, W - 11, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{float(conf):.2f}")
            p.setPen(QColor(fz.TEXT))
            p.drawText(QRectF(0, 9, W - 12, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{float(conf):.2f}")
        # matnlar
        d = _ts_dt(self.v)
        p.setFont(fz.qfont(12, 400, mono=True))
        p.setPen(QColor(fz.TEXT2))
        tm = d.strftime("%H:%M") if d else ""
        p.drawText(QRectF(0, img_h + 10, W - 12, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tm)
        tmw = p.fontMetrics().horizontalAdvance(tm)
        p.setFont(fz.qfont(13, 600))
        p.setPen(QColor(fz.TEXT))
        name = p.fontMetrics().elidedText(str(self.v.get("camera_name") or "Kamera"), Qt.TextElideMode.ElideRight,
                                          int(W - 13 - 12 - tmw - 8))
        p.drawText(QRectF(13, img_h + 10, W - 26, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        txt, col = STATUS.get(self.status, STATUS["new"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(col))
        p.drawEllipse(QPointF(16, img_h + 38), 3, 3)
        p.setFont(fz.qfont(12, 400))
        p.setPen(QColor(col))
        p.drawText(QRectF(25, img_h + 30, W - 30, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
        # chegara
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.selected:
            p.setPen(QPen(QColor(fz.ACCENT), 2))
            p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 9.5, 9.5)
        else:
            p.setPen(QPen(QColor(fz.SEG_BORDER if self._hover else fz.BORDER), 1))
            p.drawRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 10, 10)
        p.end()


class _ListRow(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, v: dict, status: str, selected: bool, parent=None):
        super().__init__(parent)
        self.v, self.status, self.selected = v, status, selected
        self.setFixedHeight(57)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        p = _abs(v.get("crop_path") or "") or _abs(v.get("full_path") or "")
        self._path = str(p) if p else ""
        self._img = _ImgLoader.get().request(self._path, "thumb") if self._path else None

    def on_loaded(self, path, img):
        if path == self._path:
            self._img = img
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.v)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        if self.selected:
            p.fillRect(0, 0, W, 56, QColor("#102641"))
            p.fillRect(0, 0, 3, 56, QColor(fz.ACCENT))
        p.fillRect(0, 56, W, 1, QColor(fz.BORDER))
        r = QRectF(13, 9, 64, 38)
        clip = QPainterPath()
        clip.addRoundedRect(r, 4, 4)
        p.save()
        p.setClipPath(clip)
        p.fillRect(r, QColor(WELL))
        if self._img is not None and not self._img.isNull():
            _cover(p, r, self._img)
        p.restore()
        d = _ts_dt(self.v)
        p.setFont(fz.qfont(13, 600))
        p.setPen(QColor(fz.TEXT))
        p.drawText(QRectF(89, 9, W * 0.4, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   str(self.v.get("camera_name") or "Kamera"))
        tid = self.v.get("track_id")
        p.setFont(fz.qfont(12, 400))
        p.setPen(QColor(fz.RED))
        desc = "Shlem yo‘q" + (f" · ID {int(tid):04d}" if isinstance(tid, (int, float)) and tid >= 0 else "")
        p.drawText(QRectF(89, 29, W * 0.4, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, desc)
        txt, col = STATUS.get(self.status, STATUS["new"])
        x = W * 0.55
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(col))
        p.drawEllipse(QPointF(x + 3, 28), 3, 3)
        p.setPen(QColor(col))
        p.drawText(QRectF(x + 12, 20, 160, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
        p.setFont(fz.qfont(12, 400, mono=True))
        p.setPen(QColor(fz.TEXT2))
        conf = self.v.get("confidence")
        p.drawText(QRectF(W * 0.75, 20, 60, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{float(conf):.2f}" if conf is not None else "")
        p.drawText(QRectF(0, 20, W - 14, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   d.strftime("%d.%m %H:%M") if d else "")
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  Tafsilot paneli (380x706)
# ════════════════════════════════════════════════════════════════════════════

class _Evidence(QWidget):
    """344x213 r8 #101A2C + 1px #1A2842; kadr cover; vaqt pill; crop bo'lsa qizil ramka + yorliq."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img: QImage | None = None
        self._is_crop = False
        self._time = ""
        self._label = ""

    def set_data(self, img: QImage | None, is_crop: bool, time_s: str, label: str):
        self._img, self._is_crop, self._time, self._label = img, is_crop, time_s, label
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(0, 0, self.width(), self.height())
        clip = QPainterPath()
        clip.addRoundedRect(r, 8, 8)
        p.setClipPath(clip)
        p.fillRect(r, QColor(WELL))
        img = self._img
        if img is not None and not img.isNull():
            if self._is_crop:
                s = min((r.width() - 40) / img.width(), (r.height() - 70) / img.height())   # tepada vaqt pill + yorliq uchun joy
                w, h = img.width() * s, img.height() * s
                box = QRectF((r.width() - w) / 2, r.height() - h - 12, w, h)
                p.drawImage(box, img)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(fz.RED), 1.5))
                p.drawRect(box.adjusted(0.75, 0.75, -0.75, -0.75))
                if self._label:
                    p.setFont(fz.qfont(10.5, 700, mono=True))
                    tw = p.fontMetrics().horizontalAdvance(self._label) + 12
                    pill = QRectF(min(box.left() - 8, r.width() - tw - 6), box.top() - 21, tw, 18)
                    pill.moveLeft(max(6, pill.left()))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(fz.RED_FILL))
                    p.drawRoundedRect(pill, 3, 3)
                    p.setPen(QColor("#ffffff"))
                    p.drawText(pill, Qt.AlignmentFlag.AlignCenter, self._label)
            else:
                _cover(p, r, img)
        else:
            p.drawPixmap(QPointF(r.width() / 2 - 9, r.height() / 2 - 9), fz.svg_pixmap("video_off", 18, 18))
        if self._time:
            p.setFont(fz.qfont(11, 500, mono=True))
            tw = p.fontMetrics().horizontalAdvance(self._time) + 16
            pill = QRectF(11, 12, tw, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(7, 16, 28, 204))
            p.drawRoundedRect(pill, 5, 5)
            p.setPen(QColor(fz.TEXT))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, self._time)
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(fz.BORDER), 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        p.end()


class _Thumb(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, idx: int, parent=None):
        super().__init__(parent)
        self.idx = idx
        self._img: QImage | None = None
        self._active = False
        self.setFixedSize(82, 52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_data(self, img: QImage | None, active: bool):
        self._img, self._active = img, active
        self.setVisible(img is not None)
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit(self.idx)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, 82, 52)
        clip = QPainterPath()
        clip.addRoundedRect(r, 6, 6)
        p.setClipPath(clip)
        p.fillRect(r, QColor(WELL))
        if self._img is not None and not self._img.isNull():
            _cover(p, r, self._img)
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self._active:
            p.setPen(QPen(QColor(fz.ACCENT), 2))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)
        else:
            p.setPen(QPen(QColor(fz.BORDER), 1))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.end()


class _Detail(QFrame):
    confirm = pyqtSignal(object)
    reject = pyqtSignal(object)
    set_review = pyqtSignal(object)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._v: dict | None = None
        self._frames: list[tuple[QImage | None, bool, str]] = []
        self._fi = 0
        self.setObjectName("fzEvDetail")
        self.setStyleSheet(f"QFrame#fzEvDetail {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:12px; }}")
        self.title = fz.label("Hodisa tanlanmagan", 13.5, 600, fz.TEXT, parent=self)
        self.st_dot = fz.Dot(fz.RED, 6, parent=self)
        self.st_lbl = fz.label("", 12, 500, fz.RED, parent=self)
        self.ev = _Evidence(self)
        self.b_exp = self._ov_btn("expand", "To‘liq o‘lchamda ochish")
        self.b_exp.clicked.connect(self._open_full)
        self.b_dl = self._ov_btn("download", "Rasmni saqlash")
        self.b_dl.clicked.connect(self._save_img)
        self.thumbs = [_Thumb(i, self) for i in range(4)]
        for t in self.thumbs:
            t.clicked.connect(self._pick_frame)
        self.div = fz.hline()
        self.div.setParent(self)
        self.keys, self.vals = [], []
        for k in ("Kamera", "Bo‘lim", "Vaqt", "Track ID", "Ishonch", "Xodim (FaceID)", "Xabarnoma"):
            self.keys.append(fz.label(k, 12.5, 400, fz.MUTED, parent=self))
            self.vals.append(fz.label("—", 12.5, 500, fz.TEXT, parent=self))
        self.sync_dot = fz.Dot(fz.GREEN, 6, parent=self)
        self.b_ok = fz.Button("Tasdiqlash", "primary", icon="check_dark", icon_size=15, h=32, px=13, pad=8, gap=6,
                              radius=7, width=149, parent=self)
        self.b_ok.clicked.connect(lambda: self._v is not None and self.confirm.emit(self._v))
        self.b_no = fz.Button("Noto‘g‘ri aniqlash", "ghost", h=32, px=13, pad=10, radius=7, width=149, parent=self)
        self.b_no.clicked.connect(lambda: self._v is not None and self.reject.emit(self._v))
        self.b_more = fz.Button("", "subtle", icon="more", icon_size=16, h=32, pad=8, radius=7, width=32, parent=self)
        self.b_more.clicked.connect(self._more_menu)
        self._empty = fz.label("Hodisa tanlang", 13, 400, fz.MUTED, parent=self)
        _ImgLoader.get().loaded.connect(self._on_img)
        self.show_empty()

    def _ov_btn(self, icon, tip):
        b = QPushButton(self)
        b.setFixedSize(32, 32)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setIcon(fz.svg_icon(icon, 16))
        b.setIconSize(QSize(16, 16))
        b.setStyleSheet("QPushButton { background:rgba(7,16,28,0.8); border:1px solid #2a3a56; border-radius:7px; }"
                        "QPushButton:hover { border-color:#3a4a66; background:rgba(21,34,59,0.9); }")
        return b

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        W, H = self.width(), self.height()
        inner = W - 34
        self.title.setGeometry(17, 15, inner - 120, 17)
        self.st_lbl.adjustSize()
        self.st_lbl.move(W - 17 - self.st_lbl.width(), 15)
        self.st_dot.move(self.st_lbl.x() - 12, 21)
        eh = int(round(inner * 213 / 344))
        self.ev.setGeometry(18, 46, inner, eh)
        self.b_dl.move(18 + inner - 11 - 32, 46 + eh - 11 - 32)
        self.b_exp.move(self.b_dl.x() - 6 - 32, self.b_dl.y())
        ty = 46 + eh + 12
        tw = (inner - 3 * 6) / 4
        for i, t in enumerate(self.thumbs):
            t.setFixedSize(int(tw), 52)
            t.move(int(17 + i * (tw + 6)), ty)
        dy = ty + 52 + 16
        self.div.setGeometry(17, dy, inner, 1)
        y = dy + 12
        for k, v in zip(self.keys, self.vals):
            k.setGeometry(17, y, 130, 16)
            v.setGeometry(149, y, inner - 132, 16)
            y += 27
        self.sync_dot.move(149, self.vals[-1].y() + 5)
        by = H - 17 - 32
        bw = int((inner - 32 - 16) / 2)
        self.b_ok.setFixedWidth(bw)
        self.b_no.setFixedWidth(bw)
        self.b_ok.move(17, by)
        self.b_no.move(17 + bw + 8, by)
        self.b_more.move(17 + 2 * bw + 16, by)
        self._empty.move(17, 48)

    def _widgets(self):
        return [self.st_dot, self.st_lbl, self.ev, self.b_exp, self.b_dl, self.div, self.sync_dot,
                self.b_ok, self.b_no, self.b_more] + self.keys + self.vals + self.thumbs

    def show_empty(self):
        self._v = None
        self.title.setText("Hodisa tanlanmagan")
        for w in self._widgets():
            w.hide()
        self._empty.show()

    def load(self, v: dict, status: str, related: list[dict]):
        for w in self._widgets():
            w.show()
        self._empty.hide()
        self._v = v
        d = _ts_dt(v)
        vid = v.get("id")
        code = f"#EV-{d:%Y-%m%d}-{int(vid):04d}" if (d and isinstance(vid, int)) else f"#{vid or '—'}"
        self.title.setText(f"Hodisa {code}")
        txt, col = STATUS.get(status, STATUS["new"])
        self.st_lbl.setText(txt)
        fz.restyle(self.st_lbl, 12, 500, col)
        self.st_dot.set_color(col)
        cam = v.get("camera_name") or "—"
        cam_id = ""
        dept = "—"
        if self.cfg:
            c = next((c for c in self.cfg.get_cameras() if c.get("name") == cam or c.get("id") == v.get("camera_id")), None)
            if c:
                cam_id = f" · CAM-{int(c.get('id')):02d}"
                dd = self.cfg.get_department_by_id(v.get("department_id") or c.get("department_id"))
                dept = dd.get("name", "—") if dd else "—"
        conf = v.get("confidence")
        tid = v.get("track_id")
        emp = str(v.get("employee_name") or "").strip()
        sync = str(v.get("sync_status") or "")
        values = [
            (f"{cam}{cam_id}", False, fz.TEXT),
            (dept, False, fz.TEXT),
            (d.strftime("%d.%m.%Y %H:%M:%S") if d else "—", True, fz.TEXT),
            (f"{int(tid):04d}" if isinstance(tid, (int, float)) and tid >= 0 else "—", True, fz.TEXT),
            (f"{float(conf):.2f}" if conf is not None else "—", True, fz.TEXT),
            (emp or "Aniqlanmadi", False, fz.TEXT if emp else fz.TEXT2),
        ]
        for lbl, (t, mono, c) in zip(self.vals, values):
            lbl.setText(t)
            fz.restyle(lbl, 12.5, 500, c, mono=mono)
        if sync in ("synced", "sent"):
            self.vals[-1].setText("    Telegram · backend yuborildi")
            fz.restyle(self.vals[-1], 12.5, 400, fz.GREEN)
            self.sync_dot.set_color(fz.GREEN)
        elif sync == "failed":
            self.vals[-1].setText("    Yuborilmadi — qayta urinadi")
            fz.restyle(self.vals[-1], 12.5, 400, fz.RED)
            self.sync_dot.set_color(fz.RED)
        else:
            self.vals[-1].setText("    Navbatda")
            fz.restyle(self.vals[-1], 12.5, 400, fz.MUTED)
            self.sync_dot.set_color(fz.MUTED)
        self.b_ok.setEnabled(status != "confirmed")
        # kadrlar: to'liq kadr, crop, so'ng shu kameraning qo'shni hodisalari
        self._frames = []
        for key, is_crop in (("full_path", False), ("crop_path", True)):
            p = _abs(v.get(key) or "")
            if p:
                self._frames.append((str(p), is_crop, v))
        for r in related:
            p = _abs(r.get("crop_path") or "") or _abs(r.get("full_path") or "")
            if p and len(self._frames) < 4:
                self._frames.append((str(p), True, r))
        crop_pm = v.get("_crop_pixmap")
        if not self._frames and isinstance(crop_pm, QPixmap):
            self._frames.append(("__pm__", True, v))
        self._fi = 1 if len(self._frames) > 1 and self._frames[1][2] is v else 0
        for path, _, _ in self._frames:
            if path != "__pm__":
                _ImgLoader.get().request(path, "full")
        self._render_frames()
        self._relayout()

    def _img_for(self, path: str):
        if path == "__pm__":
            pm = self._v.get("_crop_pixmap") if self._v else None
            return pm.toImage() if isinstance(pm, QPixmap) else None
        return _ImgLoader.get().cached(path, "full")

    def _render_frames(self):
        for i, t in enumerate(self.thumbs):
            if i < len(self._frames):
                t.set_data(self._img_for(self._frames[i][0]) or QImage(), i == self._fi)
            else:
                t.set_data(None, False)
        if self._frames:
            path, is_crop, ev = self._frames[self._fi]
            d = _ts_dt(ev)
            tid = ev.get("track_id")
            conf = ev.get("confidence")
            label = " · ".join(x for x in (f"ID {int(tid)}" if isinstance(tid, (int, float)) and tid >= 0 else "",
                                         "Shlem yo‘q", f"{float(conf):.2f}" if conf is not None else "") if x)
            self.ev.set_data(self._img_for(path), is_crop, d.strftime("%H:%M:%S") if d else "", label)
        else:
            d = _ts_dt(self._v or {})
            self.ev.set_data(None, False, d.strftime("%H:%M:%S") if d else "", "")

    def _on_img(self, path: str, img: QImage, kind: str):
        if kind == "full" and any(f[0] == path for f in self._frames):
            self._render_frames()

    def _pick_frame(self, i: int):
        if i < len(self._frames):
            self._fi = i
            self._render_frames()

    def _current_path(self) -> str:
        return self._frames[self._fi][0] if self._frames else ""

    def _open_full(self):
        p = self._current_path()
        if p and p != "__pm__":
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def _save_img(self):
        p = self._current_path()
        if not p or p == "__pm__":
            return
        dst, _ = QFileDialog.getSaveFileName(self, "Rasmni saqlash", os.path.join(os.path.expanduser("~"), "Desktop",
                                                                                    Path(p).name), "Rasm (*.jpg *.png)")
        if not dst:
            return
        try:
            shutil.copy(p, dst)
        except OSError as exc:
            show_toast(self, f"Rasm saqlanmadi: {exc}", "error")
            return
        show_toast(self, f"Rasm saqlandi: {dst}", "success", 5000)

    def _more_menu(self):
        if self._v is None:
            return
        m = QMenu(self)
        m.setStyleSheet(
            f"QMenu {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:8px; padding:4px; {fz.css_font(12.5, 500)} }}"
            f"QMenu::item {{ color:{fz.TEXT2}; padding:6px 14px; border-radius:6px; }}"
            f"QMenu::item:selected {{ background:{fz.ACTIVE}; color:{fz.TEXT}; }}")
        a_rev = m.addAction("Ko‘rib chiqilmoqda deb belgilash")
        a_new = m.addAction("Yangi deb belgilash")
        m.addSeparator()
        a_dir = m.addAction("Papkada ko‘rsatish")
        act = m.exec(self.b_more.mapToGlobal(self.b_more.rect().topLeft()))
        m.deleteLater()            # har bosishda yangi menyu — eskisi xotirada qolmasin
        if act is a_rev:
            self._v["_set"] = "review"
            self.set_review.emit(self._v)
        elif act is a_new:
            self._v["_set"] = "new"
            self.set_review.emit(self._v)
        elif act is a_dir:
            p = self._current_path()
            if p and p != "__pm__":
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent)))


# ════════════════════════════════════════════════════════════════════════════
#  Davr segmenti (Bugun / 7 kun / 30 kun / Oraliq)
# ════════════════════════════════════════════════════════════════════════════

class _PeriodSeg(QWidget):
    changed = pyqtSignal(int)
    WIDTHS = (50, 50, 60, 60)
    LABELS = ("Bugun", "7 kun", "30 kun", "Oraliq")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cur = 0
        self._hover = -1
        self.setFixedSize(3 + sum(self.WIDTHS) + 2 * 3 + 3, 31)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _rects(self):
        x = 3.0
        for w in self.WIDTHS:
            yield QRectF(x, 4, w, 23)
            x += w + 2

    def current(self):
        return self._cur

    def set_current(self, i):
        self._cur = i
        self.update()

    def mouseMoveEvent(self, e):
        h = next((i for i, r in enumerate(self._rects()) if r.contains(e.position())), -1)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        for i, r in enumerate(self._rects()):
            if r.contains(e.position()):
                if i != self._cur or i == 3:
                    self._cur = i
                    self.update()
                    self.changed.emit(i)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(fz.BORDER), 1))
        p.setBrush(QColor(fz.CARD))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, 30), 8, 8)
        for i, (r, t) in enumerate(zip(self._rects(), self.LABELS)):
            act = i == self._cur
            if act or i == self._hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(fz.ACTIVE) if act else QColor(21, 34, 59, 110))
                p.drawRoundedRect(r, 6, 6)
            p.setFont(fz.qfont(12.5, 600 if act else 500))
            p.setPen(QColor(fz.TEXT if act else fz.TEXT2))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, t)
        p.end()


class _ViewToggle(QWidget):
    changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cur = 0
        self.setFixedSize(80, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        i = 0 if e.position().x() < 40 else 1
        if i != self._cur:
            self._cur = i
            self.update()
            self.changed.emit(i)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(fz.BORDER), 1))
        p.setBrush(QColor(fz.CARD))
        p.drawRoundedRect(QRectF(0.5, 0.5, 79, 29), 8, 8)
        for i, icon in enumerate(("columns", "file")):
            r = QRectF(3 + 36 * i, 3, 36, 24)
            act = i == self._cur
            if act:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(fz.ACTIVE))
                p.drawRoundedRect(r, 6, 6)
            p.drawPixmap(QPointF(r.x() + 11, r.y() + 5), fz.svg_pixmap(icon, 14, 14, fz.TEXT if act else fz.TEXT2))
        p.end()


class _RangeDialog(FramedDialog):
    def __init__(self, d_from: date, d_to: date, parent=None):
        from app.ui.widgets.frameless import dialog_button, dialog_footer, field_label
        super().__init__(parent)
        self.setWindowTitle("Davr oralig‘i")
        self.setModal(True)
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        lay = QHBoxLayout()
        lay.setContentsMargins(20, 18, 20, 20)
        lay.setSpacing(12)
        self.a = QDateEdit(QDate(d_from.year, d_from.month, d_from.day))
        self.b = QDateEdit(QDate(d_to.year, d_to.month, d_to.day))
        for title, e in (("Boshlanish", self.a), ("Tugash", self.b)):
            e.setCalendarPopup(True)
            e.setDisplayFormat("dd.MM.yyyy")
            e.setMinimumWidth(170)
            col = QVBoxLayout()
            col.setSpacing(6)
            col.addWidget(field_label(title))
            col.addWidget(e)
            lay.addLayout(col)
        outer.addLayout(lay)
        footer, btns = dialog_footer()
        c = dialog_button("Bekor qilish", "ghost")
        c.setAutoDefault(False)
        c.clicked.connect(self.reject)
        ok = dialog_button("Qo‘llash", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btns.addWidget(c)
        btns.addWidget(ok)
        outer.addWidget(footer)

    def values(self):
        return self.a.date().toPyDate(), self.b.date().toPyDate()


# ════════════════════════════════════════════════════════════════════════════
#  ViolationsPage
# ════════════════════════════════════════════════════════════════════════════

_ST_SQL = "COALESCE(NULLIF(review_status,''),'new')"


def _like(text: str) -> str:
    t = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{t}%"


def _track_query(q: str) -> str:
    """Track ID UI'da 0012 ko'rinishida — raqamli qidiruvda boshidagi nollar olib tashlanadi."""
    return (q.lstrip("0") or "0") if q.isdigit() else q


def _build_where(f: dict, with_status: bool = True) -> tuple[str, list]:
    """Hodisalar filtrlari → SQL WHERE (rejected — noto'g'ri aniqlanganlar — doim chiqarib tashlanadi)."""
    cond = [f"{_ST_SQL} != 'rejected'"]
    params: list = []
    if f.get("ts_from") is not None:
        cond.append("timestamp >= ?")
        params.append(f["ts_from"])
    if f.get("ts_to") is not None:
        cond.append("timestamp <= ?")
        params.append(f["ts_to"])
    if f.get("cam"):
        cond.append("camera_name = ?")
        params.append(f["cam"])
    if f.get("dept") is not None:
        cams = list(f.get("dept_cams") or [])
        if cams:
            # Eski yozuvlarda department_id yo'q — kamera bo'limi bo'yicha
            cond.append(f"(department_id = ? OR (department_id IS NULL AND camera_name IN ({','.join('?' * len(cams))})))")
            params += [f["dept"], *cams]
        else:
            cond.append("department_id = ?")
            params.append(f["dept"])
    if f.get("conf"):
        cond.append("COALESCE(confidence,0) >= ?")
        params.append(f["conf"])
    q = f.get("search") or ""
    if q:
        pat = _like(q)
        cond.append("(camera_name LIKE ? ESCAPE '\\' OR employee_name LIKE ? ESCAPE '\\'"
                    " OR employee_id LIKE ? ESCAPE '\\' OR CAST(track_id AS TEXT) LIKE ? ESCAPE '\\')")
        params += [pat, pat, pat, _like(_track_query(q))]
    if with_status and f.get("status", "all") != "all":
        cond.append(f"{_ST_SQL} = ?")
        params.append(f["status"])
    return " AND ".join(cond), params


class ViolationsPage(QWidget):
    CONF_OPTS = [("Ishonch ≥ 0.00", 0.0), ("Ishonch ≥ 0.50", 0.5), ("Ishonch ≥ 0.70", 0.7),
                 ("Ishonch ≥ 0.80", 0.8), ("Ishonch ≥ 0.90", 0.9)]
    _CSV_FIELDS = ["id", "timestamp", "camera_name", "violation_type", "confidence", "track_id",
                   "employee_id", "employee_name", "review_status", "sync_status"]

    def __init__(self, db, parent=None, cfg=None):
        super().__init__(parent)
        fz.init_fonts()
        self.db = db
        self.cfg = cfg
        self._violations: list[dict] = []        # joriy filtrlarga mos, ko'rsatilayotgan qatorlar
        self._review: dict = {}
        self._counts: dict[str, int] = {"new": 0, "review": 0, "confirmed": 0}
        self._today_total = 0
        self._today_new = 0
        self._limit = _PAGE_LIMIT
        self._loading = False
        self._pending_reload = False
        self._exporting = False
        self._period = 0
        self._range = (date.today(), date.today())
        self._status_filter = "all"
        self._cam_filter: str | None = None
        self._dept_filter = None
        self._conf_min = 0.0
        self._search = ""
        self._selected = None
        self._items: list = []
        self._items_by_path: dict[str, list] = {}
        self._view = 0                    # 0 — kartalar, 1 — ro'yxat (_ViewToggle boshlang'ich holati)
        self.setObjectName("fzEvents")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#fzEvents {{ background:{fz.BG}; }}")
        _ImgLoader.get().loaded.connect(self._on_img)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.timeout.connect(self._layout_grid)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._reload_from_start)
        self._build()
        self._load_violations()

    # ── qurilish ──
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 22, 16, 16)
        root.setSpacing(0)
        self.header = fz.PageHeader("Hodisalar", "Shlem kiymaslik holatlari — dalil kadrlar bilan.", gap=9)
        self.period = _PeriodSeg()
        self.period.changed.connect(self._on_period)
        exp = fz.Button("Eksport (CSV)", "ghost", icon="download", icon_size=15, h=31, px=13, weight=500, pad=13, gap=7)
        exp.clicked.connect(self._export_csv)
        self.header.add_right(self.period)
        self.header.add_right(exp)
        root.addWidget(self.header)
        root.addSpacing(17)

        fr = QWidget()
        fr.setFixedHeight(30)
        fr.setStyleSheet("background:transparent;")
        fl = QHBoxLayout(fr)
        fl.setContentsMargins(0, 1, 0, 1)
        fl.setSpacing(8)
        self.chips = {
            "all": fz.Chip("Barchasi", "0", True),
            "new": fz.Chip("Yangi", "0", dot=fz.RED),
            "review": fz.Chip("Ko‘rib chiqilmoqda", "0"),
            "confirmed": fz.Chip("Tasdiqlandi", "0"),
        }
        for k, c in self.chips.items():
            c.clicked.connect(lambda _, kk=k: self._set_status_filter(kk))
            fl.addWidget(c)
        fl.addSpacing(4)
        sep = fz.vline(fz.BORDER, 1, 20)
        fl.addWidget(sep, 0, Qt.AlignmentFlag.AlignVCenter)
        fl.addSpacing(4)
        self.dd_cam = fz.Dropdown(["Barcha kameralar"], 0, icon="box")
        self.dd_cam.changed.connect(self._on_cam)
        self.dd_dept = fz.Dropdown(["Barcha bo‘limlar"], 0, icon="building")
        self.dd_dept.changed.connect(self._on_dept)
        self.dd_conf = fz.Dropdown([o[0] for o in self.CONF_OPTS], 0)
        self.dd_conf.changed.connect(self._on_conf)
        for d in (self.dd_cam, self.dd_dept, self.dd_conf):
            fl.addWidget(d)
        fl.addStretch(1)
        self.view = _ViewToggle()
        self.view.changed.connect(self._on_view)
        fl.addWidget(self.view)
        root.addWidget(fr)
        root.addSpacing(14)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }"
                                  "QScrollArea > QWidget > QWidget { background:transparent; }")
        self.host = QWidget()
        self.scroll.setWidget(self.host)
        self.scroll.viewport().installEventFilter(self)
        self._empty = fz.label("Hodisa topilmadi — filtrlarni o‘zgartiring.", 13, 400, fz.MUTED, parent=self.host)
        self._empty.move(4, 8)
        self._empty.hide()
        # Limitdan ko'p hodisa bo'lsa — "yana yuklash"
        self._more_btn = fz.Button("Yana yuklash", "ghost", h=31, px=13, weight=500, pad=14, parent=self.host)
        self._more_btn.clicked.connect(self._load_more)
        self._more_btn.hide()
        body.addWidget(self.scroll, 1016)
        self.detail = _Detail(self.cfg)
        self.detail.confirm.connect(lambda v: self._set_status(v, "confirmed"))
        self.detail.reject.connect(lambda v: self._set_status(v, "rejected"))
        self.detail.set_review.connect(lambda v: self._set_status(v, v.pop("_set", "review")))
        body.addWidget(self.detail, 380)
        root.addLayout(body, 1)
        self._deps = []
        self.reload_departments()

    def reload_departments(self):
        """Bo'limlar ro'yxati (Sozlamalarda o'zgarganda MainWindow chaqiradi)."""
        deps = self.cfg.get_departments() if self.cfg else []
        self._deps = deps
        ids = [d.get("id") for d in deps]
        cur = ids.index(self._dept_filter) + 1 if self._dept_filter in ids else 0
        self.dd_dept.set_options(["Barcha bo‘limlar"] + [d.get("name", "Bo‘lim") for d in deps], cur)
        if cur == 0 and self._dept_filter is not None:
            self._dept_filter = None          # tanlangan bo'lim o'chirildi — filtr bekor
            self._reload_from_start()

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self.scroll.viewport() and ev.type() == QEvent.Type.Resize:
            self._relayout_timer.start(30)
        return super().eventFilter(obj, ev)

    # ── filtrlar ──
    def _date_range(self):
        t = date.today()
        if self._period == 0:
            return t, t
        if self._period == 1:
            return t - timedelta(days=6), t
        if self._period == 2:
            return t - timedelta(days=29), t
        return self._range

    def _filters(self) -> dict:
        d_from, d_to = self._date_range()
        dept_cams = []
        if self._dept_filter is not None and self.cfg:
            dept_cams = sorted(str(c.get("name")) for c in self.cfg.get_cameras()
                               if c.get("department_id") == self._dept_filter and c.get("name"))
        return {"ts_from": int(datetime.combine(d_from, datetime.min.time()).timestamp()),
                "ts_to": int(datetime.combine(d_to, datetime.max.time()).timestamp()),
                "cam": self._cam_filter, "dept": self._dept_filter, "dept_cams": dept_cams,
                "conf": self._conf_min, "search": self._search, "status": self._status_filter}

    @staticmethod
    def _matches(v: dict, f: dict) -> bool:
        """Jonli hodisa joriy filtrlarga (holatdan tashqari) mosmi — _build_where bilan bir xil mantiq."""
        try:
            ts = int(float(v.get("timestamp") or 0))
        except (TypeError, ValueError):
            return False
        if (f["ts_from"] is not None and ts < f["ts_from"]) or (f["ts_to"] is not None and ts > f["ts_to"]):
            return False
        if f["cam"] and v.get("camera_name") != f["cam"]:
            return False
        if f["dept"] is not None:
            did = v.get("department_id")
            if did is None:
                if v.get("camera_name") not in (f["dept_cams"] or ()):
                    return False
            elif did != f["dept"]:
                return False
        if f["conf"] and float(v.get("confidence") or 0) < f["conf"]:
            return False
        q = f["search"]
        if q:
            hay = " ".join(str(v.get(k) or "") for k in ("camera_name", "employee_name", "employee_id")).lower()
            tid = v.get("track_id")
            if q not in hay and not (tid is not None and _track_query(q) in str(tid)):
                return False
        return True

    def _reload_from_start(self):
        self._limit = _PAGE_LIMIT
        self._load_violations()

    def _on_period(self, i):
        if i == 3:
            dlg = _RangeDialog(*self._date_range(), parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self.period.set_current(self._period)
                return
            a, b = dlg.values()
            self._range = (min(a, b), max(a, b))
        self._period = i
        self._reload_from_start()

    def _set_status_filter(self, key):
        self._status_filter = key
        for k, c in self.chips.items():
            c.set_active(k == key)
        self._reload_from_start()

    def _on_cam(self, i):
        self._cam_filter = None if i == 0 else self.dd_cam.current_text()
        self._reload_from_start()

    def _on_dept(self, i):
        self._dept_filter = None if i == 0 else self._deps[i - 1].get("id")
        self._reload_from_start()

    def _on_conf(self, i):
        self._conf_min = self.CONF_OPTS[i][1]
        self._reload_from_start()

    def _on_view(self, i):
        self._view = i
        self._rebuild_grid()

    def set_search_text(self, text: str):
        """Global qidiruv: kamera nomi / xodim / track ID bo'yicha (SQL'da, kechiktirilgan)."""
        q = (text or "").strip().lower()
        if q == self._search:
            return
        self._search = q
        self._search_timer.start()

    def _load_more(self):
        self._limit += _PAGE_LIMIT
        self._load_violations()

    # ── yuklash ──
    def _load_violations(self):
        if self._loading:
            self._pending_reload = True
            return
        self._loading = True
        self._pending_reload = False
        f = self._filters()
        limit = self._limit
        db = self.db

        def job():
            conn = db._conn()
            where, params = _build_where(f)
            base, bparams = _build_where(f, with_status=False)
            rows = [dict(r) for r in conn.execute(
                f"SELECT * FROM violations WHERE {where} ORDER BY timestamp DESC, id DESC LIMIT ?",
                params + [limit]).fetchall()]
            counts = {r["st"]: int(r["c"]) for r in conn.execute(
                f"SELECT {_ST_SQL} AS st, COUNT(*) AS c FROM violations WHERE {base} GROUP BY st", bparams).fetchall()}
            t = date.today()
            tr = conn.execute(
                f"SELECT COUNT(*) AS c, SUM(CASE WHEN {_ST_SQL} = 'new' THEN 1 ELSE 0 END) AS n FROM violations"
                f" WHERE timestamp BETWEEN ? AND ? AND {_ST_SQL} != 'rejected'",
                (int(datetime.combine(t, datetime.min.time()).timestamp()),
                 int(datetime.combine(t, datetime.max.time()).timestamp()))).fetchone()
            return {"rows": rows, "counts": counts, "today": int(tr["c"] or 0), "today_new": int(tr["n"] or 0),
                    "names": db.get_distinct_camera_names(), "filters": f}

        run_async(self, job, self._on_data_ready, self._on_load_error)

    def _after_load(self):
        self._loading = False
        if self._pending_reload:
            self._pending_reload = False
            QTimer.singleShot(150, self._load_violations)

    def _on_load_error(self, exc):
        self._after_load()
        show_toast(self, f"Hodisalar yuklanmadi: {exc}", "error")

    def _on_data_ready(self, res: dict):
        if res.get("filters") != self._filters():
            # Yuklash paytida filtr o'zgargan — eski natijani ko'rsatmaymiz
            self._loading = False
            self._pending_reload = False
            self._load_violations()
            return
        self._after_load()
        self._violations = res["rows"]
        self._review = {_vid(v): (v.get("review_status") or "new") for v in self._violations}
        self._counts = {k: int(res["counts"].get(k, 0)) for k in ("new", "review", "confirmed")}
        self._today_total, self._today_new = res["today"], res["today_new"]
        cur = self._cam_filter
        opts = ["Barcha kameralar"] + list(res["names"])
        self.dd_cam.set_options(opts, opts.index(cur) if cur in opts else 0)
        self._rebuild_grid()

    def _match_total(self) -> int:
        if self._status_filter == "all":
            return sum(self._counts.values())
        return self._counts.get(self._status_filter, 0)

    def _update_counts(self):
        cnt = dict(self._counts)
        cnt["all"] = sum(self._counts.values())
        for k, c in self.chips.items():
            c.set_count(cnt.get(k, 0))
        sub = (f"Shlem kiymaslik holatlari — dalil kadrlar bilan. Bugun {self._today_total} ta, "
               f"{self._today_new} tasi ko‘rib chiqilmagan.")
        shown, total = len(self._violations), self._match_total()
        if total > shown:
            sub += f" Oxirgi {shown} tasi ko‘rsatilmoqda ({total} tadan)."
        self.header.sub.setText(sub)
        self._more_btn.setVisible(total > shown)
        if total > shown:
            self._more_btn.setText(f"Yana {min(_PAGE_LIMIT, total - shown)} tasini yuklash")

    def _make_item(self, v: dict):
        st = self._review.get(_vid(v), "new")
        sel = _vid(v) == self._selected
        w = _Card(v, st, sel, self.host) if self._view == 0 else _ListRow(v, st, sel, self.host)
        w.clicked.connect(self._on_pick)
        w.show()
        self._items_by_path.setdefault(w._path, []).append(w)
        return w

    def _rebuild_grid(self):
        self._update_counts()
        for w in self._items:
            w.deleteLater()
        self._items = []
        self._items_by_path = {}
        rows = self._violations
        self._empty.setVisible(not rows)
        if rows and (self._selected is None or all(_vid(v) != self._selected for v in rows)):
            self._selected = _vid(rows[0])
        if not rows:
            self._selected = None
            self.detail.show_empty()
        for v in rows:
            self._items.append(self._make_item(v))
        sel_v = next((v for v in rows if _vid(v) == self._selected), None)
        if sel_v is not None:
            self.detail.load(sel_v, self._review.get(_vid(sel_v), "new"), self._related(sel_v))
        self._layout_grid()

    def _related(self, v: dict) -> list[dict]:
        out = []
        for r in self._violations:
            if r is v or r.get("camera_name") != v.get("camera_name"):
                continue
            out.append(r)
            if len(out) >= 2:
                break
        return out

    def _layout_grid(self):
        W = self.scroll.viewport().width()
        if W <= 10:
            return
        if self._view == 0:
            cols = max(1, (W + 12) // (245 + 12))
            cw = (W - 12 * (cols - 1)) / cols
            ch = cw * 154 / 245 + 57
            for i, w in enumerate(self._items):
                r, c = divmod(i, cols)
                w.setGeometry(int(c * (cw + 12)), int(r * (ch + 10)), int(cw), int(ch))
            rows = (len(self._items) + cols - 1) // cols
            bottom = int(rows * (ch + 10))
        else:
            for i, w in enumerate(self._items):
                w.setGeometry(0, i * 57, W, 57)
            bottom = len(self._items) * 57
        if self._more_btn.isVisibleTo(self.host):
            self._more_btn.move(max(0, (W - self._more_btn.width()) // 2), bottom + 6)
            bottom += self._more_btn.height() + 16
        self.host.setMinimumHeight(bottom)
        self.host.setFixedWidth(W)

    def _on_pick(self, v):
        self._selected = _vid(v)
        for w in self._items:
            w.selected = _vid(w.v) == self._selected
            w.update()
        self.detail.load(v, self._review.get(self._selected, "new"), self._related(v))

    def _on_img(self, path, img, kind):
        if kind == "thumb":
            for w in self._items_by_path.get(path, ()):
                w.on_loaded(path, img)

    def _remove_row(self, vid):
        idx = next((i for i, x in enumerate(self._violations) if _vid(x) == vid), None)
        if idx is None:
            return
        self._violations.pop(idx)
        if idx < len(self._items):
            w = self._items.pop(idx)
            lst = self._items_by_path.get(w._path)
            if lst and w in lst:
                lst.remove(w)
            w.deleteLater()
        if self._selected == vid:
            self._selected = None
            if self._violations:
                nxt = self._violations[min(idx, len(self._violations) - 1)]
                self._on_pick(nxt)
            else:
                self.detail.show_empty()
        self._empty.setVisible(not self._violations)
        self._layout_grid()

    def _set_status(self, v, status: str):
        vid = _vid(v)
        old = self._review.get(vid, v.get("review_status") or "new")
        if not isinstance(v.get("id"), int):
            show_toast(self, "Hodisa hali saqlanmoqda — birozdan so‘ng qayta urinib ko‘ring", "info")
            return
        try:
            ok = self.db.set_review_status(v["id"], status)
        except Exception:
            ok = False
        if not ok:
            # DB'ga yozilmagan holatni UI'da ko'rsatmaymiz — keyingi yuklashda qaytib chiqardi
            show_toast(self, "Holat saqlanmadi — ma'lumotlar bazasi band yoki xato", "error")
            return
        v["review_status"] = status
        self._review[vid] = status
        if old == status:
            return
        if old in self._counts:
            self._counts[old] = max(0, self._counts[old] - 1)
        if status in self._counts:
            self._counts[status] += 1
        d = _ts_dt(v)
        if d is not None and d.date() == date.today():
            if status == "rejected":
                self._today_total = max(0, self._today_total - 1)
            if old == "new":
                self._today_new = max(0, self._today_new - 1)
            elif status == "new":
                self._today_new += 1
        if status == "rejected" or (self._status_filter != "all" and status != self._status_filter):
            self._remove_row(vid)
        else:
            for w in self._items:
                if _vid(w.v) == vid:
                    w.status = status
                    w.update()
            if self._selected == vid:
                self.detail.load(v, status, self._related(v))
        self._update_counts()
        self._layout_grid()

    # ── eksport ──
    def _export_csv(self):
        if self._exporting:
            show_toast(self, "Eksport davom etmoqda...", "info")
            return
        total = self._match_total()
        if total <= 0:
            show_toast(self, "Eksport uchun hodisa yo‘q — filtrlarni o‘zgartiring", "info")
            return
        d_from, d_to = self._date_range()
        path, _ = QFileDialog.getSaveFileName(
            self, "CSV eksport", os.path.join(os.path.expanduser("~"), "Desktop", f"hodisalar_{d_from:%Y%m%d}_{d_to:%Y%m%d}.csv"),
            "CSV fayllar (*.csv)")
        if not path:
            return
        self.export_to(path)

    def export_to(self, path: str):
        """Joriy filtrlarga mos BARCHA hodisalar (sahifa limitisiz) fonda CSV ga yoziladi."""
        f = self._filters()
        db = self.db
        fields = self._CSV_FIELDS

        def job():
            where, params = _build_where(f)
            cur = db._conn().execute(
                f"SELECT * FROM violations WHERE {where} ORDER BY timestamp DESC, id DESC", params)
            n = 0
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                wr = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                wr.writeheader()
                for row in cur:
                    r = dict(row)
                    d = _ts_dt(r)
                    r["timestamp"] = d.strftime("%Y-%m-%d %H:%M:%S") if d else ""
                    r["review_status"] = r.get("review_status") or "new"
                    wr.writerow(r)
                    n += 1
            return n

        def done(n):
            self._exporting = False
            show_toast(self, f"{n} ta hodisa eksport qilindi: {path}", "success", 5000)

        def fail(exc):
            self._exporting = False
            show_toast(self, f"Eksport xatosi: {exc}", "error")

        self._exporting = True
        show_toast(self, "Eksport tayyorlanmoqda...", "info")
        run_async(self, job, done, fail)

    # ── jonli hodisa ──
    def add_new_violation(self, data: dict):
        """Yangi hodisa: butun ro'yxat qayta yuklanmaydi — filtrlarga mos bo'lsa
        bitta karta yuqoriga qo'shiladi."""
        if self._loading:
            self._pending_reload = True
            return
        v = {k: val for k, val in data.items() if k not in ("crop_frame", "camera")}
        v["review_status"] = v.get("review_status") or "new"
        d = _ts_dt(v)
        if d is not None and d.date() == date.today():
            self._today_total += 1
            self._today_new += 1
        if self._matches(v, self._filters()):
            self._counts["new"] += 1
            if self._status_filter in ("all", "new"):
                self._insert_top(v)
            self._resolve_id(v)
        self._update_counts()
        self._layout_grid()

    def _insert_top(self, v: dict):
        self._violations.insert(0, v)
        self._review[_vid(v)] = "new"
        self._items.insert(0, self._make_item(v))
        if len(self._violations) > self._limit:          # sahifa limiti saqlanadi
            last = self._violations[-1]
            self._remove_row(_vid(last))
        self._empty.hide()
        if self._selected is None:
            self._on_pick(v)

    def _resolve_id(self, v: dict):
        """Payload'da DB id yo'q — fonda topib, karta lug'atiga qo'shiladi (holat o'zgartirish uchun)."""
        db = self.db
        key = (v.get("track_id"), int(float(v.get("timestamp") or 0)), v.get("camera_name") or "")

        def job():
            r = db._conn().execute(
                "SELECT * FROM violations WHERE track_id = ? AND timestamp = ? AND camera_name = ?"
                " ORDER BY id DESC LIMIT 1", key).fetchone()
            return dict(r) if r else None

        def done(row):
            if not row:
                return
            old = _vid(v)
            for k, val in row.items():
                if k not in ("crop_path", "full_path") or val:
                    v[k] = val
            new = _vid(v)
            if old != new:
                self._review[new] = self._review.pop(old, None) or row.get("review_status") or "new"
                if self._selected == old:
                    self._selected = new

        run_async(self, job, done, lambda _e: None)
