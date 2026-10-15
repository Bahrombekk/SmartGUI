"""
Xodimlar — Figma "SafeZone — Xodimlar" (16:182) aniq nusxasi.

Sarlavha (Import (Excel) / Xodim qo‘shish) · chapda jadval kartasi (1016):
qidiruv + chiplar (Barchasi / Ruxsat bor / Buzilgan / Namuna kerak),
ustunlar Xodim/Bo‘lim/Holat/Oxirgi ko‘rilgan/Yuz namunasi (x 13/288/498/721/879),
qator 56 + 1 · o‘ngda profil paneli (380): avatar, statistika chiplari,
yuz namunalari (5 slot), so‘nggi buzilishlar, ruxsat etilgan hududlar.

MainWindow API: UsersPage(cfg, db=None), refresh(), set_search_text(text),
on_face_recognized(data).
"""
from __future__ import annotations

import csv
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QScrollArea,
                             QLabel, QFileDialog, QMessageBox, QDialog, QLineEdit)

from app.application.services.faceid_service import (
    photos_with_face, store_employee_photos, user_photo_paths,
)
from app.ui import fz
from app.ui.async_task import run_async
from app.ui.widgets.toast import persist_config, show_toast
from app.ui.widgets.app_dialog import AppMessageBox
from app.ui.widgets.frameless import FramedDialog, dialog_button, dialog_footer, field_label

COLS = (13, 288, 498, 721, 879)            # Figma, karta kengligi 1016
HEAD = ("Xodim", "Bo‘lim", "Holat", "Oxirgi ko‘rilgan", "Yuz namunasi")
SEL_BG = "#102641"
AV_BLUE = (fz.BLUE_BG, fz.ACCENT)
AV_GREEN = (fz.GREEN_BG, fz.GREEN)
AV_RED = (fz.RED_BG, fz.RED)


def _full(u: dict) -> str:
    return f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()


def _initials(u: dict) -> str:
    return ((u.get("first_name", "")[:1] or "X") + (u.get("last_name", "")[:1] or "")).upper()


# Xodim rasmlari ro'yxati: yo'llar to'plami → mavjud fayllar. Har bir qidiruv
# harfida Path.exists() qayta chaqirilmasin; refresh() da tozalanadi.
_PHOTOS_CACHE: dict[tuple, list[str]] = {}


def _photos(u: dict) -> list[str]:
    key = tuple(user_photo_paths(u))
    hit = _PHOTOS_CACHE.get(key)
    if hit is None:
        hit = [p for p in key if p and Path(p).exists()]
        _PHOTOS_CACHE[key] = hit
    return hit


def _thumb(path: str, w: int, h: int) -> QPixmap:
    """Rasmni to'liq o'lchamda dekodlamasdan kichraytirib o'qiydi (JPEG uchun tez)."""
    rd = QImageReader(path)
    rd.setAutoTransform(True)
    src = rd.size()
    if src.isValid() and src.width() > 0 and src.height() > 0:
        s = max(w / src.width(), h / src.height())
        if s < 1.0:
            rd.setScaledSize(QSize(max(1, round(src.width() * s)), max(1, round(src.height() * s))))
    img = rd.read()
    return QPixmap.fromImage(img) if not img.isNull() else QPixmap()


def _cx(x: float, w: int) -> int:
    return int(round(x * w / 1016.0)) if x > 13 else 13


class _Avatar(QWidget):
    def __init__(self, size: int = 28, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._t, self._bg, self._fg = "", fz.BLUE_BG, fz.ACCENT

    def set_data(self, initials: str, colors: tuple[str, str]):
        self._t = initials
        self._bg, self._fg = colors
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.width()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._bg))
        p.drawEllipse(QRectF(0, 0, s, s))
        p.setFont(fz.qfont(11 if s <= 30 else 17, 600))
        p.setPen(QColor(self._fg))
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, self._t)
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  Jadval qatori
# ════════════════════════════════════════════════════════════════════════════

class _Row(QWidget):
    clicked = pyqtSignal(int)

    def __init__(self, u: dict, dept: str, status: str, nviol: int, last_seen: str,
                 photos: int, colors, parent=None):
        super().__init__(parent)
        self.uid = int(u.get("id"))
        self._sel = False
        self._hover = False
        self.setFixedHeight(57)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.av = _Avatar(28, self)
        self.av.move(13, 14)
        self.av.set_data(_initials(u), colors)
        self.name = fz.label(_full(u) or "Xodim", 13, 600, fz.TEXT, parent=self)
        self.name.move(57, 10)
        self.role = fz.label(u.get("role") or "Xodim", 11.5, 400, fz.MUTED, parent=self)
        self.role.move(57, 30)
        self.dept = fz.label(dept or "—", 13, 400, fz.TEXT2, parent=self)
        if status == "violation":
            st, col = f"{nviol} buzilish", fz.RED
        elif status == "sample":
            st, col = "Yuz namunasi kerak", fz.MUTED
        else:
            st, col = "Ruxsat bor", fz.GREEN
        self.dot = fz.Dot(col, 5, parent=self)
        self.st = fz.label(st, 12, 500, col, parent=self)
        self.seen = fz.label(last_seen, 12, 400, fz.MUTED if last_seen.startswith("—") else fz.TEXT2, mono=True, parent=self)
        fc = fz.TEXT2 if photos >= 5 else (fz.TEXT if photos >= 3 else fz.RED)
        self.face = fz.label(f"{photos}/5", 12, 400, fc, mono=True, parent=self)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        W = self.width()
        xs = [_cx(x, W) for x in COLS]
        self.name.setFixedWidth(max(40, xs[1] - 57 - 10))
        self.role.setFixedWidth(max(40, xs[1] - 57 - 10))
        self.dept.setGeometry(xs[1], 19, xs[2] - xs[1] - 8, 16)
        self.dot.move(xs[2], 25)
        self.st.setGeometry(xs[2] + 11, 19, xs[3] - xs[2] - 18, 16)
        self.seen.setGeometry(xs[3], 19, xs[4] - xs[3] - 8, 16)
        self.face.setGeometry(xs[4], 19, 60, 16)

    def set_selected(self, v):
        self._sel = v
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.uid)

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
#  Profil paneli
# ════════════════════════════════════════════════════════════════════════════

class _Stat(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("fzStat")
        self.setFixedHeight(55)
        self.setStyleSheet(f"QFrame#fzStat {{ background:{fz.RAISED}; border:none; border-radius:8px; }}")
        self.k = fz.label(label, 11, 400, fz.MUTED, parent=self)
        self.k.move(10, 11)
        self.v = fz.label("—", 17, 500, fz.TEXT, mono=True, parent=self)
        self.v.move(10, 25)

    def set_value(self, t: str, color: str = fz.TEXT):
        self.v.setText(t)
        fz.restyle(self.v, 17, 500, color, mono=True)
        self.v.adjustSize()


class _Slot(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 63)
        self._pm: QPixmap | None = None
        self._add = False
        self._filled = False

    def set_state(self, pm: QPixmap | None, filled: bool, add: bool):
        self._pm, self._filled, self._add = pm, filled, add
        self.setCursor(Qt.CursorShape.PointingHandCursor if add else Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, e):
        if self._add:
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._add:
            pen = QPen(QColor(fz.GHOST_BORDER), 1, Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 3])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 8, 8)
            p.drawPixmap(QPointF(23, 22), fz.svg_pixmap("plus", 18, 18, fz.TEXT2))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(fz.RAISED))
            p.drawRoundedRect(r, 8, 8)
            if self._pm is not None and not self._pm.isNull():
                clip = QPainterPath()
                clip.addRoundedRect(r, 8, 8)
                p.setClipPath(clip)
                pm = self._pm
                s = max(r.width() / pm.width(), r.height() / pm.height())
                sw, sh = r.width() / s, r.height() / s
                p.drawPixmap(r, pm, QRectF((pm.width() - sw) / 2, (pm.height() - sh) / 2, sw, sh))
            elif self._filled:
                p.drawPixmap(QPointF(23, 22), fz.svg_pixmap("users", 18, 18, fz.MUTED))
            else:
                p.setPen(QPen(QColor(fz.BORDER), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, 8, 8)
        p.end()


class _ViolRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self._pm: QPixmap | None = None
        self.t = fz.label("", 13, 600, fz.TEXT, parent=self)
        self.t.move(76, 0)
        self.d = fz.label("", 12, 400, fz.RED, parent=self)
        self.d.move(76, 20)
        self.tm = fz.label("", 12, 400, fz.TEXT2, mono=True, parent=self)
        self.tm.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def set_data(self, title, desc, tm, pm):
        self.t.setText(title)
        self.t.adjustSize()
        self.d.setText(desc)
        self.d.adjustSize()
        self.tm.setText(tm)
        self._pm = pm
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.tm.setGeometry(self.width() - 60, 10, 60, 16)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, 64, 38)
        clip = QPainterPath()
        clip.addRoundedRect(r, 4, 4)
        p.setClipPath(clip)
        p.fillRect(r, QColor("#101a2c"))
        pm = self._pm
        if pm is not None and not pm.isNull():
            s = max(r.width() / pm.width(), r.height() / pm.height())
            sw, sh = r.width() / s, r.height() / s
            p.drawPixmap(r, pm, QRectF((pm.width() - sw) / 2, (pm.height() - sh) / 2, sw, sh))
        p.end()


class _Profile(QFrame):
    add_photos = pyqtSignal(int)
    edit_user = pyqtSignal(int)
    remove_user = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._uid: int | None = None
        self.setObjectName("fzProfile")
        self.setStyleSheet(f"QFrame#fzProfile {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:12px; }}")
        self.av = _Avatar(56, self)
        self.name = fz.label("", 15, 600, fz.TEXT, parent=self)
        self.meta = fz.label("", 12, 400, fz.TEXT2, parent=self)
        self.stats = [_Stat("Bu oy buzilish", self), _Stat("Muvofiqlik", self), _Stat("Smena", self)]
        self.s_face = fz.label("Yuz namunalari (FaceID)", 13, 600, fz.TEXT, parent=self)
        self.s_hint = fz.label("", 11.5, 400, fz.MUTED, parent=self)
        self.slots = [_Slot(self) for _ in range(5)]
        for s in self.slots:
            s.clicked.connect(lambda: self._uid is not None and self.add_photos.emit(self._uid))
        self.s_viol = fz.label("So‘nggi buzilishlar", 13, 600, fz.TEXT, parent=self)
        self.v_div = fz.hline()
        self.v_div.setParent(self)
        self.vrows = [_ViolRow(self) for _ in range(3)]
        self.vdivs = [fz.hline() for _ in range(3)]
        for d in self.vdivs:
            d.setParent(self)
        self.v_empty = fz.label("Buzilish qayd etilmagan", 12, 400, fz.MUTED, parent=self)
        self.s_zone = fz.label("Ruxsat etilgan hududlar", 13, 600, fz.TEXT, parent=self)
        self.zone = fz.label("", 12.5, 400, fz.TEXT2, parent=self)
        self.b_edit = fz.Button("Tahrirlash", "ghost", icon="pencil", icon_size=13, h=26, px=12.5, weight=500,
                                pad=12, gap=6, radius=6, parent=self)
        self.b_edit.clicked.connect(lambda: self._uid is not None and self.edit_user.emit(self._uid))
        self.empty = fz.label("Xodim tanlang", 13, 400, fz.MUTED, parent=self)
        self._n_viol = 0

    def _all(self):
        return [self.av, self.name, self.meta, self.s_face, self.s_hint, self.s_viol, self.v_div, self.s_zone,
                self.zone, self.b_edit, self.v_empty] + self.stats + self.slots + self.vrows + self.vdivs

    def show_empty(self):
        self._uid = None
        for w in self._all():
            w.hide()
        self.empty.show()

    def load(self, u: dict, dept: str, colors, viols: list[dict], photos: list[str],
             compliance: str, zones: str, load_pm, photo_pm):
        self._uid = int(u.get("id"))
        for w in self._all():
            w.show()
        self.empty.hide()
        self.av.set_data(_initials(u), colors)
        self.name.setText(_full(u) or "Xodim")
        parts = [u.get("role") or "Xodim", dept or "—", f"ID {u.get('employee_id', '')}"]
        self.meta.setText(" · ".join(parts))
        month = [v for v in viols if (datetime.fromtimestamp(float(v.get("timestamp") or 0)).month == date.today().month)]
        self.stats[0].set_value(str(len(month)), fz.RED if month else fz.TEXT)
        self.stats[1].set_value(compliance)
        self.stats[2].set_value(u.get("shift") or "—")
        n = len(photos)
        self.s_hint.setText(f"Kamida 3 ta, turli burchakdan · {min(n, 5)}/5 yuklangan")
        for i, s in enumerate(self.slots):
            if i < min(n, 5):
                s.set_state(photo_pm(photos[i]), True, False)
            elif i == min(n, 5):
                s.set_state(None, False, True)
            else:
                s.set_state(None, False, False)
        rows = viols[:3]
        self.v_empty.setVisible(not rows)
        today = date.today()
        for i, r in enumerate(self.vrows):
            if i < len(rows):
                v = rows[i]
                d = datetime.fromtimestamp(float(v.get("timestamp") or 0))
                tm = d.strftime("%H:%M") if d.date() == today else d.strftime("%d.%m")
                conf = v.get("confidence")
                r.set_data(v.get("camera_name") or "Kamera",
                           "Shlem yo‘q" + (f" · {float(conf):.2f}" if conf is not None else ""), tm, load_pm(v))
                r.show()
                self.vdivs[i].show()
            else:
                r.hide()
                self.vdivs[i].hide()
        self._n_viol = len(rows)
        self.zone.setText(zones)
        self._relayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        W = self.width()
        inner = W - 34
        self.av.move(17, 15)
        self.name.setGeometry(87, 23, inner - 70, 19)
        self.meta.setGeometry(87, 46, inner - 70, 15)
        sw = (inner - 18) / 3
        for i, s in enumerate(self.stats):
            s.setGeometry(int(17 + i * (sw + 9)), 85, int(sw), 55)
        self.s_face.setGeometry(17, 155, inner, 17)
        self.s_hint.setGeometry(17, 177, inner, 15)
        pitch = (inner - 64) / 4
        for i, s in enumerate(self.slots):
            s.move(int(17 + i * pitch), 203)
        self.s_viol.setGeometry(17, 283, inner, 17)
        self.v_div.setGeometry(17, 305, inner, 1)
        y = 313
        for i, r in enumerate(self.vrows):
            r.setGeometry(17, y + 53 * i, inner, 38)
            self.vdivs[i].setGeometry(17, y + 53 * i + 45, inner, 1)
            self.vdivs[i].setVisible(r.isVisible() and i < self._n_viol - 1)
        self.v_empty.setGeometry(17, 318, inner, 16)
        zy = 313 + 53 * max(1, self._n_viol) + 13
        zy = max(zy, 380)
        self.s_zone.setGeometry(17, zy, inner - 120, 17)
        self.zone.setGeometry(17, zy + 22, inner - 120, 16)
        self.b_edit.move(W - 17 - self.b_edit.width(), zy + 5)
        self.empty.move(17, 20)


# ════════════════════════════════════════════════════════════════════════════
#  Qo'shish / tahrirlash dialogi
# ════════════════════════════════════════════════════════════════════════════

class _EmployeeDialog(FramedDialog):
    def __init__(self, cfg, user: dict | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._user_id = user.get("id") if user else None
        self._photos: list[str] = []
        self.setWindowTitle("Xodimni tahrirlash" if user else "Xodim qo‘shish")
        self.setMinimumWidth(520)
        self.setModal(True)
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        lay = QVBoxLayout()
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(8)
        lay.addWidget(fz.label("Ism, ID va bo‘lim — FaceID shu ma’lumotlar bilan bog‘lanadi", 13, 400, fz.MUTED))
        lay.addSpacing(8)
        grid = QHBoxLayout()
        grid.setSpacing(12)
        c1, c2 = QVBoxLayout(), QVBoxLayout()
        self.fn = fz.line_edit("Ism", h=36, px=13)
        self.ln = fz.line_edit("Familiya", h=36, px=13)
        self.eid = fz.line_edit("Masalan X-0217", mono=True, h=36, px=12.5)
        self.role = fz.line_edit("Lavozim", h=36, px=13)
        self.shift = fz.line_edit("08–17", mono=True, h=36, px=12.5)
        for col in (c1, c2):
            col.setSpacing(0)
        for w, col, t in ((self.fn, c1, "Ism"), (self.ln, c2, "Familiya"), (self.eid, c1, "Xodim ID"),
                          (self.role, c2, "Lavozim"), (self.shift, c1, "Smena")):
            col.addWidget(field_label(t))
            col.addSpacing(6)
            col.addWidget(w)
            col.addSpacing(14)
        deps = cfg.get_departments()
        self._dep_ids = [d.get("id") for d in deps]
        c2.addWidget(field_label("Bo‘lim"))
        c2.addSpacing(6)
        self.dept = QComboBox()
        self.dept.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dept.addItems([d.get("name", "Bo‘lim") for d in deps] or ["—"])
        c2.addWidget(self.dept)
        c2.addSpacing(14)
        c1.addStretch(1)
        c2.addStretch(1)
        grid.addLayout(c1, 1)
        grid.addLayout(c2, 1)
        lay.addLayout(grid)
        if not user:
            lay.addWidget(field_label("Yuz rasmlari (3–5 ta, turli burchakdan)"))
            row = QHBoxLayout()
            row.setSpacing(8)
            self.ph = fz.line_edit("Rasm tanlanmagan", h=36, px=13)
            self.ph.setReadOnly(True)
            row.addWidget(self.ph, 1)
            b = fz.Button("Tanlash", "ghost", icon="folder", icon_size=14, h=36, px=13, weight=500, pad=14, gap=6)
            b.clicked.connect(self._pick)
            row.addWidget(b)
            lay.addLayout(row)
        self.err = fz.label("", 12.5, 500, fz.RED)
        self.err.setWordWrap(True)
        self.err.hide()
        lay.addWidget(self.err)
        outer.addLayout(lay)
        footer, btns = dialog_footer()
        self.deleted = False
        if user:
            rm = fz.Button("O‘chirish", "danger", icon="trash", icon_size=14, h=34, px=13, pad=14, gap=6)
            rm.clicked.connect(self._delete)
            btns.insertWidget(0, rm)
        cancel = dialog_button("Bekor qilish", "ghost")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        ok = dialog_button("Saqlash" if user else "Qo‘shish", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self._try_accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addWidget(footer)
        if user:
            self.fn.setText(user.get("first_name", ""))
            self.ln.setText(user.get("last_name", ""))
            self.eid.setText(str(user.get("employee_id", "")))
            self.role.setText(user.get("role", "") or "")
            self.shift.setText(user.get("shift", "") or "")
            if user.get("department_id") in self._dep_ids:
                self.dept.setCurrentIndex(self._dep_ids.index(user.get("department_id")))

    def _delete(self):
        self.deleted = True
        self.accept()

    def validation_error(self) -> str:
        """Bo'sh satr — hammasi to'g'ri; aks holda foydalanuvchiga ko'rsatiladigan xato."""
        d = self.data()
        missing = [n for k, n in (("first_name", "ism"), ("last_name", "familiya"), ("employee_id", "xodim ID"))
                   if not d[k]]
        if missing:
            return "Kiritilishi shart: " + ", ".join(missing)
        eid = d["employee_id"].lower()
        for u in self.cfg.get_users():
            if u.get("id") != self._user_id and str(u.get("employee_id", "")).strip().lower() == eid:
                return f"“{d['employee_id']}” ID bilan xodim allaqachon bor: {_full(u) or 'Xodim'}"
        return ""

    def _try_accept(self):
        # Xato bo'lsa dialog yopilmaydi — kiritilgan ma'lumot va tanlangan rasmlar saqlanib qoladi
        msg = self.validation_error()
        if msg:
            self.err.setText(msg)
            self.err.show()
            self.adjustSize()
            return
        self.err.hide()
        self.accept()

    def _pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Yuz rasmlari", "", "Rasmlar (*.png *.jpg *.jpeg *.bmp)")
        if paths:
            self._photos = paths
            self.ph.setText(Path(paths[0]).name if len(paths) == 1 else f"{len(paths)} ta rasm")

    def data(self) -> dict:
        i = self.dept.currentIndex()
        return {"first_name": self.fn.text().strip(), "last_name": self.ln.text().strip(),
                "employee_id": self.eid.text().strip(), "role": self.role.text().strip(),
                "shift": self.shift.text().strip(),
                "department_id": self._dep_ids[i] if 0 <= i < len(self._dep_ids) else None,
                "photos": list(self._photos)}


# ════════════════════════════════════════════════════════════════════════════
#  UsersPage
# ════════════════════════════════════════════════════════════════════════════

class UsersPage(QWidget):
    def __init__(self, config_manager, parent=None, db=None):
        super().__init__(parent)
        fz.init_fonts()
        self.cfg = config_manager
        self.db = db
        self._search = ""
        self._filter = "all"
        self._selected: int | None = None
        self._rows: dict[int, _Row] = {}
        self._viols: dict[int, list[dict]] = {}
        self._viol_rows: list[dict] = []
        self._viols_busy = False
        self._viols_again = False
        self._last_seen: dict[str, float] = {}
        self._pm_cache: dict[str, QPixmap] = {}
        self._thumb_cache: dict[str, QPixmap] = {}
        self._user_idx: dict = {}
        self._photo_busy = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)          # har harfda emas — yozish to'xtagach
        self._search_timer.timeout.connect(self._render)
        self.setObjectName("fzUsers")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#fzUsers {{ background:{fz.BG}; }}")
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 22, 16, 16)
        root.setSpacing(0)
        self.header = fz.PageHeader("Xodimlar", "", gap=15)
        imp = fz.Button("Import (Excel)", "ghost", icon="download_15", icon_size=15, h=31, px=13, weight=600, pad=14, gap=7)
        imp.clicked.connect(self._import)
        add = fz.Button("Xodim qo‘shish", "primary", icon="plus", icon_size=15, h=31, px=13, weight=600, pad=14, gap=7)
        add.clicked.connect(self._open_add)
        self.header.add_right(imp)
        self.header.add_right(add)
        root.addWidget(self.header)
        root.addSpacing(15)
        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_table(), 1016)
        self.profile = _Profile()
        self.profile.add_photos.connect(self._add_photos)
        self.profile.edit_user.connect(self._edit_user)
        self.profile.remove_user.connect(self._remove_user)
        body.addWidget(self.profile, 380)
        root.addLayout(body, 1)

    def _build_table(self) -> QFrame:
        card = fz.card(fz.CARD, fz.BORDER, 12)
        self._table = card
        self.search = fz.SearchBox("Ism yoki lavozim", 260, parent=card)
        self.search.move(15, 13)
        self.search.edit.textChanged.connect(self.set_search_text)
        self.chips = {
            "all": fz.Chip("Barchasi", "0", True, parent=card),
            "ok": fz.Chip("Ruxsat bor", "0", parent=card),
            "violation": fz.Chip("Buzilgan", "0", parent=card),
            "sample": fz.Chip("Namuna kerak", "0", parent=card),
        }
        for k, c in self.chips.items():
            c.clicked.connect(lambda _, kk=k: self._set_filter(kk))
        self._head = QWidget(card)
        self._head.setStyleSheet("background:transparent;")
        self._head_lbls = [fz.label(t, 12, 500, fz.MUTED, parent=self._head) for t in HEAD]
        self._d1 = fz.hline()
        self._d1.setParent(card)
        self._d2 = fz.hline()
        self._d2.setParent(card)
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
        self._empty = fz.label("Hali xodim qo‘shilmagan", 13, 400, fz.MUTED, parent=card)
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
        self._d1.setGeometry(1, 57, W - 2, 1)
        self._head.setGeometry(1, 58, W - 2, 36)
        for lbl, cx in zip(self._head_lbls, COLS):
            lbl.move(_cx(cx, W) - 1, 10)
        self._d2.setGeometry(1, 94, W - 2, 1)
        self._scroll.setGeometry(1, 95, W - 2, H - 96)
        self._empty.move(16, 112)

    # ── ma'lumot ──
    def _dept_name(self, u) -> str:
        d = self.cfg.get_department_by_id(u.get("department_id"))
        return d.get("name", "—") if d else "—"

    def _query_viols(self) -> list[dict]:
        """Fon thread'ida: so'nggi ~3 oydagi xodimga bog'langan buzilishlar."""
        since = int(datetime.combine(date.today().replace(day=1), datetime.min.time()).timestamp()) - 60 * 86400
        rows = self.db._conn().execute(
            "SELECT * FROM violations WHERE timestamp >= ? AND (COALESCE(employee_id,'') != ''"
            " OR COALESCE(employee_name,'') != '') AND COALESCE(review_status,'new') != 'rejected'"
            " ORDER BY timestamp DESC LIMIT 2000", (since,)).fetchall()
        return [dict(r) for r in rows]

    def _load_viols(self):
        """So'rov fonda; natija kelgach ro'yxat qayta chiziladi."""
        if self.db is None:
            return
        if self._viols_busy:
            self._viols_again = True
            return
        self._viols_busy = True
        self._viols_again = False
        run_async(self, self._query_viols, self._apply_viols, self._apply_viols)

    def _apply_viols(self, rows):
        self._viols_busy = False
        if isinstance(rows, list):
            self._viol_rows = rows
            self._map_viols()
            self._render()
        if self._viols_again:
            self._load_viols()

    def _map_viols(self):
        users = self.cfg.get_users()
        by_eid = {str(u.get("employee_id", "")).strip().lower(): int(u.get("id")) for u in users}
        by_name = {_full(u).lower(): int(u.get("id")) for u in users}
        self._viols = {}
        for r in self._viol_rows:
            uid = by_eid.get(str(r.get("employee_id") or "").strip().lower()) or                 by_name.get(str(r.get("employee_name") or "").strip().lower())
            if uid is not None:
                self._viols.setdefault(uid, []).append(r)

    def _month_viols(self, uid) -> int:
        m = date.today().month
        return sum(1 for v in self._viols.get(uid, []) if datetime.fromtimestamp(float(v.get("timestamp") or 0)).month == m)

    def _status(self, u) -> str:
        uid = int(u.get("id"))
        if self._month_viols(uid) > 0:
            return "violation"
        if len(_photos(u)) < 3:
            return "sample"
        return "ok"

    def _colors(self, u, status):
        if status == "violation":
            return AV_RED
        idx = self._user_idx.get(u.get("id"))
        if idx is None:               # _render dan tashqarida (masalan, _select) — xarita yangilanadi
            self._user_idx = {x.get("id"): i for i, x in enumerate(self.cfg.get_users())}
            idx = self._user_idx.get(u.get("id"), 0)
        return AV_BLUE if idx % 2 == 0 else AV_GREEN      # Figma: ro'yxat bo'yicha ko'k / yashil

    def _seen_text(self, u, status) -> str:
        if status == "sample":
            return "— (tanilmaydi)"
        ts = self._last_seen.get(str(u.get("employee_id", "")).lower()) or self._last_seen.get(_full(u).lower())
        if not ts:
            return "—"
        d = datetime.fromtimestamp(ts)
        return ("Bugun " if d.date() == date.today() else d.strftime("%d.%m ")) + d.strftime("%H:%M")

    def refresh(self):
        _PHOTOS_CACHE.clear()      # rasmlar qo'shilgan/o'chirilgan bo'lishi mumkin
        self._map_viols()          # foydalanuvchilar o'zgargan bo'lishi mumkin — darhol
        self._render()
        self._load_viols()         # DB'dan yangisi fonda keladi

    def set_search_text(self, text: str):
        self._search = (text or "").strip().lower()
        if self.search.edit.text() != (text or ""):
            self.search.edit.blockSignals(True)
            self.search.edit.setText(text or "")
            self.search.edit.blockSignals(False)
        self._search_timer.start()

    def on_face_recognized(self, data: dict):
        if not data.get("matched"):
            return
        ts = float(data.get("timestamp") or time.time())
        for key in (str(data.get("employee_id") or "").lower(), str(data.get("employee_name") or "").lower()):
            if key:
                self._last_seen[key] = ts

    def _set_filter(self, key):
        self._filter = key
        for k, c in self.chips.items():
            c.set_active(k == key)
        self._render()

    def _render(self):
        if not hasattr(self, "_rows_lay"):
            return
        self._search_timer.stop()
        for r in self._rows.values():
            r.deleteLater()
        self._rows.clear()
        while self._rows_lay.count() > 1:
            it = self._rows_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        users = self.cfg.get_users()
        self._user_idx = {u.get("id"): i for i, u in enumerate(users)}
        counts = {"all": len(users), "ok": 0, "violation": 0, "sample": 0}
        st_map = {}
        for u in users:
            st = self._status(u)
            st_map[int(u.get("id"))] = st
            counts[st] += 1
        for k, c in self.chips.items():
            c.set_count(counts[k])
        self.header.sub.setText(f"FaceID orqali tanish va hududga ruxsat nazorati · {len(users)} xodim")
        shown = []
        for u in users:
            uid = int(u.get("id"))
            hay = f"{_full(u)} {u.get('role', '')} {u.get('employee_id', '')}".lower()
            if self._search and self._search not in hay:
                continue
            if self._filter != "all" and st_map[uid] != self._filter:
                continue
            shown.append(u)
        self._empty.setVisible(not shown)
        self._empty.setText("Hali xodim qo‘shilmagan" if not users else "Xodim topilmadi")
        if shown and (self._selected is None or all(int(u.get("id")) != self._selected for u in shown)):
            self._selected = int(shown[0].get("id"))
        for u in shown:
            uid = int(u.get("id"))
            st = st_map[uid]
            r = _Row(u, self._dept_name(u), st, self._month_viols(uid), self._seen_text(u, st),
                     len(_photos(u)), self._colors(u, st))
            r.clicked.connect(self._select)
            r.set_selected(uid == self._selected)
            self._rows[uid] = r
            self._rows_lay.insertWidget(self._rows_lay.count() - 1, r)
        self._layout_table()
        sel = next((u for u in shown if int(u.get("id")) == self._selected), None)
        if sel is not None:
            self._load_profile(sel, st_map[int(sel.get("id"))])
        else:
            self.profile.show_empty()

    def _select(self, uid: int):
        self._selected = uid
        for i, r in self._rows.items():
            r.set_selected(i == uid)
        u = next((x for x in self.cfg.get_users() if int(x.get("id")) == uid), None)
        if u:
            self._load_profile(u, self._status(u))

    def _load_pm(self, v: dict):
        for key in ("crop_path", "full_path"):
            p = v.get(key)
            if p:
                pp = Path(p) if Path(p).is_absolute() else Path.cwd() / p
                k = str(pp)
                if k in self._pm_cache:
                    return self._pm_cache[k]
                if pp.exists():
                    if len(self._pm_cache) > 300:
                        self._pm_cache.pop(next(iter(self._pm_cache)))
                    self._pm_cache[k] = _thumb(k, 128, 76)
                    return self._pm_cache[k]
        return None

    def _photo_pm(self, path: str) -> QPixmap:
        """Profil yuz namunasi miniatyurasi (kesh — har tanlashda qayta dekodlanmaydi)."""
        pm = self._thumb_cache.get(path)
        if pm is None:
            if len(self._thumb_cache) > 200:
                self._thumb_cache.pop(next(iter(self._thumb_cache)))
            pm = _thumb(path, 128, 126)
            self._thumb_cache[path] = pm
        return pm

    def _zones(self, u) -> str:
        dep = self.cfg.get_department_by_id(u.get("department_id"))
        names = [dep.get("name")] if dep else []
        for c in self.cfg.get_cameras():
            allowed = c.get("allowed_department_ids") or []
            if (c.get("department_id") == u.get("department_id") or u.get("department_id") in allowed) and c.get("name"):
                names.append(c.get("name"))
        seen, out = set(), []
        for n in names:
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return ", ".join(out[:4]) + ("…" if len(out) > 4 else "") if out else "—"

    def _load_profile(self, u, status):
        uid = int(u.get("id"))
        viols = self._viols.get(uid, [])
        m = self._month_viols(uid)
        comp = "—"
        if self._seen_text(u, status) not in ("—", "— (tanilmaydi)"):
            comp = "100%" if m == 0 else "—"
        self.profile.load(u, self._dept_name(u), self._colors(u, status), viols, _photos(u), comp,
                          self._zones(u), self._load_pm, self._photo_pm)

    # ── amallar ──
    # ── yuz tekshiruvi fonda ──
    def _set_photo_busy(self, on: bool, text: str = ""):
        self._photo_busy = on
        if on:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
            if text:
                show_toast(self, text, "info")
        else:
            QApplication.restoreOverrideCursor()

    def _check_photos_async(self, employee_id: str, paths: list[str], on_done):
        """Yuz aniqlash + nusxa olish fon thread'ida. on_done(stored, rejected_count)."""
        def job():
            ok = photos_with_face(paths)
            good = [p for p, h in zip(paths, ok) if h]
            stored = store_employee_photos(employee_id, good) if good else []
            return stored, len(paths) - len(good)

        def done(res):
            self._set_photo_busy(False)
            on_done(*res)

        def fail(exc):
            self._set_photo_busy(False)
            show_toast(self, f"Rasmlarni tekshirib bo‘lmadi: {exc}", "error")

        self._set_photo_busy(True, f"{len(paths)} ta rasm tekshirilmoqda...")
        run_async(self, job, done, fail)

    def _warn_rejected(self, rejected: int, total: int):
        if rejected:
            show_toast(self, f"{total} ta rasmdan {rejected} tasida yuz topilmadi yoki fayl o‘qilmadi — "
                             "ular qo‘shilmadi", "warning", 6000)

    def _open_add(self):
        if self._photo_busy:
            show_toast(self, "Rasmlar hali tekshirilmoqda — biroz kuting", "info")
            return
        dlg = _EmployeeDialog(self.cfg, None, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.data()
        photos = d["photos"]
        if photos:
            self._check_photos_async(d["employee_id"], photos,
                                     lambda stored, rej: self._finish_add(d, stored, rej, len(photos)))
        else:
            self._finish_add(d, [], 0, 0)

    def _finish_add(self, d: dict, stored: list[str], rejected: int, total: int):
        try:
            user = self.cfg.add_user(d["first_name"], d["last_name"], d["employee_id"],
                                     department_id=d["department_id"], photo_paths=stored)
            self.cfg.update_user(user.get("id"), role=d["role"], shift=d["shift"])
        except ValueError as exc:
            AppMessageBox.warning(self, "Xodimlar", str(exc))
            return
        if persist_config(self, self.cfg, f"Xodim qo‘shildi: {d['first_name']} {d['last_name']}"):
            self._selected = user.get("id")
            self.refresh()
        self._warn_rejected(rejected, total)

    def _edit_user(self, uid: int):
        u = next((x for x in self.cfg.get_users() if int(x.get("id")) == uid), None)
        if u is None:
            return
        dlg = _EmployeeDialog(self.cfg, u, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.deleted:
            self._remove_user(uid)
            return
        d = dlg.data()
        d.pop("photos", None)
        self.cfg.update_user(uid, **d)          # validatsiya dialog ichida (_try_accept)
        if persist_config(self, self.cfg, f"Xodim yangilandi: {d['first_name']} {d['last_name']}"):
            self.refresh()

    def _remove_user(self, uid: int):
        u = next((x for x in self.cfg.get_users() if int(x.get("id")) == uid), {})
        if AppMessageBox.question(self, "Xodimni o‘chirish", f"“{_full(u) or 'Xodim'}” o‘chirilsinmi?",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.cfg.remove_user(uid)
        if persist_config(self, self.cfg, f"Xodim o‘chirildi: {_full(u)}"):
            self._selected = None
            self.refresh()

    def _add_photos(self, uid: int):
        u = next((x for x in self.cfg.get_users() if int(x.get("id")) == uid), None)
        if u is None:
            return
        if self._photo_busy:
            show_toast(self, "Rasmlar hali tekshirilmoqda — biroz kuting", "info")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Yuz rasmlari", "", "Rasmlar (*.png *.jpg *.jpeg *.bmp)")
        if not paths:
            return
        self._check_photos_async(u.get("employee_id", ""), paths,
                                 lambda stored, rej: self._finish_add_photos(uid, stored, rej, len(paths)))

    def _finish_add_photos(self, uid: int, stored: list[str], rejected: int, total: int):
        u = next((x for x in self.cfg.get_users() if int(x.get("id")) == uid), None)
        if u is None:                   # tekshiruv paytida xodim o'chirilgan
            return
        if not stored:
            show_toast(self, f"Tanlangan {total} ta rasmning hech birida yuz topilmadi", "warning")
            return
        existing = _photos(u)
        allp = (existing + [p for p in stored if p not in existing])[:5]
        self.cfg.update_user(uid, photo_paths=allp, photo_path=allp[0] if allp else "")
        if persist_config(self, self.cfg, f"{len(stored)} ta rasm qo‘shildi — FaceID yangilanadi"):
            self.refresh()
        self._warn_rejected(rejected, total)

    # ── Import (CSV / XLSX) ──
    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Xodimlarni import qilish", "",
                                              "Excel / CSV (*.xlsx *.csv);;Barcha fayllar (*)")
        if not path:
            return
        try:
            rows = self._read_table(path)
        except Exception as exc:
            AppMessageBox.warning(self, "Import", f"Faylni o‘qib bo‘lmadi:\n{exc}")
            return
        if not rows:
            AppMessageBox.warning(self, "Import", "Faylda ma’lumot topilmadi.")
            return
        head = [str(h).strip().lower() for h in rows[0]]

        def col(*names):
            for n in names:
                if n in head:
                    return head.index(n)
            return None
        ci = {"fn": col("ism", "first_name", "name"), "ln": col("familiya", "last_name", "surname"),
              "id": col("id", "xodim id", "employee_id", "tabel"), "role": col("lavozim", "role", "position"),
              "dept": col("bo‘lim", "bo'lim", "bolim", "department"), "shift": col("smena", "shift")}
        if ci["fn"] is None or ci["id"] is None:
            AppMessageBox.warning(self, "Import", "Sarlavhada kamida “Ism” va “ID” ustunlari bo‘lishi kerak.\n"
                                  "Ustunlar: Ism, Familiya, ID, Lavozim, Bo‘lim, Smena")
            return
        deps = {d.get("name", "").strip().lower(): d.get("id") for d in self.cfg.get_departments()}
        added = skipped = 0
        for r in rows[1:]:
            def g(k):
                i = ci[k]
                return str(r[i]).strip() if i is not None and i < len(r) and r[i] is not None else ""
            fn, ln, eid = g("fn"), g("ln") or "-", g("id")
            if not fn or not eid:
                continue
            try:
                u = self.cfg.add_user(fn, ln, eid, department_id=deps.get(g("dept").lower()))
                self.cfg.update_user(u.get("id"), role=g("role"), shift=g("shift"))
                added += 1
            except ValueError:
                skipped += 1
        if persist_config(self, self.cfg, f"{added} ta xodim import qilindi" + (f", {skipped} ta o‘tkazib yuborildi" if skipped else "")):
            self.refresh()

    @staticmethod
    def _read_table(path: str) -> list[list]:
        if path.lower().endswith(".csv"):
            with open(path, encoding="utf-8-sig", newline="") as fh:
                sample = fh.read(2048)
                fh.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
                return [row for row in csv.reader(fh, dialect)]
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with zipfile.ZipFile(path) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                    shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
            sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            out = []
            for row in sheet.iter("{%s}row" % ns["m"]):
                vals = {}
                for c in row.findall("m:c", ns):
                    ref = c.get("r", "A1")
                    letters = "".join(ch for ch in ref if ch.isalpha())
                    idx = 0
                    for ch in letters:
                        idx = idx * 26 + (ord(ch.upper()) - 64)
                    v = c.find("m:v", ns)
                    is_ = c.find("m:is", ns)
                    if c.get("t") == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif is_ is not None:
                        val = "".join(t.text or "" for t in is_.iter("{%s}t" % ns["m"]))
                    else:
                        val = v.text if v is not None else ""
                    vals[idx - 1] = val
                if vals:
                    out.append([vals.get(i, "") for i in range(max(vals) + 1)])
            return out
