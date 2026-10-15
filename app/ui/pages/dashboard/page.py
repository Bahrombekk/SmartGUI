"""
Monitoring — Figma "SafeZone — Monitoring" (16:2) aniq nusxasi.

Sahifa koordinatalari (top bar 52px'dan keyin):
  KPI qatori y20 h96 (4 karta, oraliq 12)
  Chap ustun (858): jonli video y130 h448 + timeline (+10) h32
  O'ng ustun (538): faol ogohlantirish h146, "Kameralar" sarlavhasi, 2x2 plitka
  Pastki qator y636 h196: soatlik grafik 580 | so'nggi hodisalar 447 | bo'limlar 357
Kenglik/balandlik oshganda ustunlar Figma nisbatlarida cho'ziladi, video va
kamera to'ri vertikal bo'sh joyni egallaydi.

MainWindow API: setup_cameras, update_frame, on_violation, on_stats, on_status,
on_error, on_model_loaded, on_face_recognized, count_face_attempt,
set_total_persons, set_search_text, `_panels`; signallar go_violations,
add_camera_requested, ai_pause_requested, go_cameras.
"""
from __future__ import annotations

import datetime as dt
import math
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize
from PyQt6.QtGui import (QColor, QPainter, QPen, QBrush, QPainterPath, QPixmap, QImage,
                         QPolygonF)
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout,
                             QPushButton, QSizePolicy)

from app.ui import fz
from app.ui.async_task import run_async
from app.ui.widgets.feed_view import FeedView

ALERT_HOLD_S = 90          # plitkada "SHLEM YO'Q" qancha turadi
NEW_EVENT_S = 15 * 60      # "yangi" nuqtasi


def _load_image(ev: dict) -> QImage | None:
    """Hodisa rasmini kichraytirib o'qiydi (QImage — fon thread'ida ham xavfsiz)."""
    for key in ("crop_path", "full_path"):
        pth = ev.get(key)
        if pth:
            p = Path(pth) if Path(pth).is_absolute() else Path.cwd() / pth
            if p.exists():
                img = QImage(str(p))
                if not img.isNull():
                    return img.scaled(220, 160, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
    return None


def _dept_name(cfg, cam: dict | None) -> str:
    if not cam:
        return ""
    try:
        d = cfg.get_department_by_id(cam.get("department_id"))
        return d.get("name", "") if d else ""
    except Exception:
        return ""


# ════════════════════════════════════════════════════════════════════════════
#  KPI kartasi (343x96, radius 10)
# ════════════════════════════════════════════════════════════════════════════

class _Ring(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 52)
        self._v = 0.0

    def set_value(self, pct: float):
        self._v = max(0.0, min(100.0, float(pct)))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(2, 2, 48, 48)
        p.setPen(QPen(QColor("#1A2842"), 4.5))
        p.drawEllipse(rect)
        pen = QPen(QColor("#1FB6FF"), 4.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, -int(self._v / 100 * 360 * 16))
        p.end()


class _Spark(QWidget):
    def __init__(self, color: str, h: int, parent=None):
        super().__init__(parent)
        self._c = QColor(color)
        self.setFixedSize(122, h)
        self._vals: list[float] = []

    def set_values(self, vals):
        self._vals = [float(v) for v in vals]
        self.update()

    def paintEvent(self, _):
        # Ma'lumot yo'q (hammasi 0) — soxta tekis chiziq chizilmaydi
        if len(self._vals) < 2 or not any(self._vals):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lo, hi = min(self._vals), max(self._vals)
        rng = (hi - lo) or 1.0
        w, h = self.width(), self.height()
        n = len(self._vals)
        pts = [QPointF(1 + (w - 2) * i / (n - 1), 3 + (h - 6) * (1 - (v - lo) / rng)) for i, v in enumerate(self._vals)]
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        pen = QPen(self._c, 1.6)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)
        p.end()


class _StatusGrid(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._states: list[bool] = []
        self.setFixedSize(66, 24)

    def set_states(self, states: list[bool]):
        self._states = list(states)
        cols = max(1, math.ceil(len(self._states) / 2))
        self.setFixedSize(cols * 14 - 4, 24)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        cols = max(1, math.ceil(len(self._states) / 2))
        for i, st in enumerate(self._states):
            r, c = divmod(i, cols)
            col = fz.GREEN if st in (True, "live") else (fz.RED if st in (False, "offline") else fz.BORDER)
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(c * 14, r * 14, 10, 10), 2, 2)
        p.end()


class _KPI(QFrame):
    def __init__(self, title: str, icon: str, icon_bg: str, visual: QWidget | None, vis_pos: tuple, parent=None):
        super().__init__(parent)
        self.setObjectName("fzKPI")
        self.setFixedHeight(96)
        self._style(False)
        self._box = fz.IconBox(icon, icon_bg, parent=self)
        self._box.move(16, 14)
        self._title = fz.label(title, 12.5, 400, fz.TEXT2, parent=self)
        self._title.setGeometry(48, 18, 250, 15)
        self._value = fz.label("—", 31, 500, fz.TEXT, mono=True, tracking=-1, parent=self)
        self._value.setFixedHeight(38)
        self._value.move(16, 43)
        self._unit = fz.label("", 14, 400, fz.MUTED, mono=True, parent=self)
        self._pill = fz.Pill("", fz.GREEN_BG, fz.GREEN, px=11, weight=500, mono=True, h=20, pad=7, radius=6, parent=self)
        self._visual = visual
        self._vis_pos = vis_pos            # (o'ngdan masofa, y)
        if visual is not None:
            visual.setParent(self)
        self._unit_y = 60
        self._unit_px = 14

    def _style(self, danger: bool):
        bg, bd = (fz.RED_CARD, fz.RED_BORDER) if danger else (fz.CARD, fz.BORDER)
        self.setStyleSheet(f"QFrame#fzKPI {{ background:{bg}; border:1px solid {bd}; border-radius:10px; }}")

    def set_danger(self, v: bool):
        self._style(v)
        fz.restyle(self._value, 31, 500, fz.RED if v else fz.TEXT, mono=True, tracking=-1)

    def set_value(self, value: str, unit: str = "", unit_px: float = 14, unit_y: int = 60):
        self._value.setText(value)
        self._value.adjustSize()
        self._unit.setText(unit)
        fz.restyle(self._unit, unit_px, 400, fz.MUTED, mono=True)
        self._unit.adjustSize()
        self._unit_y = unit_y
        self._layout()

    def set_pill(self, text: str, kind: str = "green"):
        if not text:
            self._pill.hide()
            return
        bg, fg = {"green": (fz.GREEN_BG, fz.GREEN), "red": (fz.RED_BG, fz.RED),
                  "grey": (fz.BORDER, fz.TEXT2)}[kind]
        self._pill.set_colors(bg, fg, None, None, px=11, weight=500, mono=True)
        self._pill.set_text(text)
        self._pill.adjustSize()
        self._pill.show()
        self._layout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()

    def _layout(self):
        vw = self._value.width()
        x = 16 + vw
        if self._unit.text():
            self._unit.move(x + 1, self._unit_y)
            x = self._unit.x() + self._unit.width()
        self._pill.move(x + 8 if self._unit.text() else x + 11, 61)
        if self._visual is not None:
            dx, y = self._vis_pos
            self._visual.move(self.width() - dx - self._visual.width(), y)


# ════════════════════════════════════════════════════════════════════════════
#  Jonli video kartasi (858x448) + overlay'lar
# ════════════════════════════════════════════════════════════════════════════

class _OverlayBtn(QPushButton):
    def __init__(self, icon: str, tip: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIcon(fz.svg_icon(icon, 16))
        self.setIconSize(QSize(16, 16))
        self.setStyleSheet(
            f"QPushButton {{ background:{fz.OVERLAY}; border:1px solid {fz.SEG_BORDER}; border-radius:7px; }}"
            "QPushButton:hover { background:rgba(21,34,59,0.9); border-color:#3a4a66; }"
        )


class _ZoneLayer(QWidget):
    """Kamera polygon zonasi — ko'k uzuq chiziq + "Xavfli zona" pill."""

    def __init__(self, parent=None, feed=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pts: list = []
        self._feed = feed

    def map(self, x, y) -> QPointF:
        if self._feed is not None:
            return self._feed.map_norm(float(x), float(y))
        return QPointF(float(x) * self.width(), float(y) * self.height())

    def set_points(self, pts):
        self._pts = list(pts or [])
        self.update()

    def visible_zone(self) -> bool:
        # Kamera oflayn / hali ulanmagan — zona ko'rsatilmaydi (kadr yo'q)
        live = self._feed is None or self._feed.is_live()
        return live and len(self._pts) >= 3

    def paintEvent(self, _):
        if not self.visible_zone():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        poly = QPolygonF([self.map(x, y) for x, y in self._pts])
        fill = QColor(31, 182, 255, 18)
        pen = QPen(QColor(31, 182, 255, 220), 1.5, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.setBrush(fill)
        p.drawPolygon(poly)
        p.end()


class _LiveCard(QFrame):
    prev_requested = pyqtSignal()
    next_requested = pyqtSignal()
    expand_requested = pyqtSignal()
    snapshot_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fzLive")
        self.setStyleSheet(f"QFrame#fzLive {{ background:{fz.CARD_DEEP}; border:1px solid {fz.BORDER}; border-radius:12px; }}")
        self.feed = FeedView(radius=11, bg=fz.CARD_DEEP, gradient_h=110, parent=self)
        self._video = self.feed
        self.zone = _ZoneLayer(self, self.feed)
        self.feed.frame_size_changed.connect(self._place)
        self.feed.live_changed.connect(lambda _live: self._sync_zone())
        self.zone_pill = fz.Pill("Xavfli zona", fz.OVERLAY_STRONG, fz.TEXT, px=11, weight=500, mono=False,
                                 h=22, pad=8, radius=6, border="rgba(31,182,255,0.55)", parent=self)
        self._zone_icon = fz.Icon("map_pin", 13)
        self.zone_pill.layout().insertWidget(0, self._zone_icon)
        self.zone_pill.layout().setSpacing(5)
        self.zone_pill.hide()
        self.br_tl = fz.Icon("bracket_tl", 26, parent=self)
        self.br_tr = fz.Icon("bracket_tr", 26, parent=self)
        self.live = fz.Pill("LIVE", fz.RED_FILL, "#ffffff", px=11, weight=700, mono=True, h=24, pad=9, radius=5,
                            dot="#ffffff", dot_size=6, gap=6, tracking=1, parent=self)
        self.cam = fz.Pill("CAM-01", fz.OVERLAY, fz.TEXT, px=11, weight=500, mono=True, h=24, pad=8, radius=5, parent=self)
        self.rec = fz.Pill("REC 00:00:00", fz.OVERLAY, fz.TEXT, px=11, weight=500, mono=True, h=24, pad=8, radius=5,
                           dot=fz.RED, dot_size=8, gap=6, parent=self)
        self.rec.hide()                    # ilova video yozmaydi — soxta REC taymeri ko'rsatilmaydi
        self.res = fz.Pill("— fps", fz.OVERLAY, fz.TEXT, px=11, weight=500, mono=True, h=24, pad=8, radius=5, parent=self)
        self.title = fz.label("—", 18, 600, fz.TEXT, parent=self)
        self.sub = fz.label("", 12, 400, fz.TEXT2, parent=self)
        self.btns = []
        for icon, tip, sig in (("chev_l", "Oldingi kamera", self.prev_requested),
                               ("expand", "Kattalashtirish", self.expand_requested),
                               ("download", "Kadrni saqlash", self.snapshot_requested),
                               ("chev_r", "Keyingi kamera", self.next_requested)):
            b = _OverlayBtn(icon, tip, self)
            b.clicked.connect(sig.emit)
            self.btns.append(b)

    def set_zone(self, pts, label: str = "Xavfli zona"):
        self.zone.set_points(pts)
        self.zone_pill.set_text(label)
        self.zone_pill.adjustSize()
        self._sync_zone()

    def _sync_zone(self):
        """Zona va "Xavfli zona" pill faqat jonli kadr bor paytda ko'rinadi."""
        self.zone_pill.setVisible(self.zone.visible_zone())
        self.zone.update()
        self._place()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        W, H = self.width(), self.height()
        self.feed.setGeometry(1, 1, W - 2, H - 2)
        self.zone.setGeometry(1, 1, W - 2, H - 2)
        self.br_tl.move(14, 15)
        self.br_tr.move(W - 41, 15)
        for pl in (self.live, self.cam, self.rec, self.res, self.zone_pill):
            pl.adjustSize()
        self.live.move(24, 24)
        self.cam.move(self.live.x() + self.live.width() + 4, 24)
        self.res.move(W - 26 - self.res.width(), 24)
        self.rec.move(self.res.x() - 11 - self.rec.width(), 24)
        self.title.adjustSize()
        self.sub.adjustSize()
        self.title.move(20, H - 60)
        self.sub.move(20, H - 35)
        x = W - 20
        for b in reversed(self.btns):
            x -= 32
            b.move(x, H - 51)
            x -= 6
        pts = self.zone._pts
        if not self.zone_pill.isHidden() and len(pts) >= 3:
            top = min(pts, key=lambda q: q[1])
            tp = self.zone.map(top[0], top[1])
            px = int(1 + tp.x() - self.zone_pill.width() / 2)
            py = int(1 + tp.y() - 22 - 6)
            self.zone_pill.move(max(8, min(W - self.zone_pill.width() - 8, px)), max(56, py))


class _Timeline(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fzTimeline")
        self.setFixedHeight(32)
        self.setStyleSheet(f"QFrame#fzTimeline {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:8px; }}")
        self._events: list[float] = []      # soat (kasr) 6..22

    def set_events(self, hours: list[float]):
        self._events = [h for h in hours if 6 <= h <= 22]
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        p.setFont(fz.qfont(11, 400, mono=True))
        p.setPen(QColor(fz.MUTED))
        p.drawText(QRectF(12, 8, 40, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "06:00")
        p.drawText(QRectF(W - 46, 8, 40, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "22:00")
        x0, x1 = 58.0, W - 57.0
        span = x1 - x0

        def X(hh):
            return x0 + span * (hh - 6) / 16.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fz.BORDER))
        p.drawRoundedRect(QRectF(x0, 14, span, 2), 1, 1)
        now = dt.datetime.now()
        cur = now.hour + now.minute / 60 + now.second / 3600
        if cur > 6:
            p.setBrush(QColor(31, 182, 255, 89))
            p.drawRoundedRect(QRectF(x0, 14, X(min(cur, 22)) - x0, 2), 1, 1)
        p.setBrush(QColor(126, 142, 168, 89))
        for hh in range(7, 22):
            p.drawRoundedRect(QRectF(X(hh) - 1, 11, 2, 8), 1, 1)
        p.setBrush(QColor(fz.RED))
        for hh in self._events:
            p.drawRoundedRect(QRectF(X(hh) - 1, 9, 2, 12), 1, 1)
        if 6 <= cur <= 22:
            p.setBrush(QColor(fz.ACCENT))
            p.drawRoundedRect(QRectF(X(cur) - 1, 5, 2, 20), 1, 1)
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  Faol ogohlantirish kartasi (538x146)
# ════════════════════════════════════════════════════════════════════════════

class _Thumb(QWidget):
    """148x110 r6: kadr (crop) + qizil ramka + ishonch pill."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 110)
        self._pm: QPixmap | None = None
        self._conf: float | None = None
        self._alert = True

    def set_data(self, pm: QPixmap | None, conf: float | None, alert: bool = True):
        self._pm, self._conf, self._alert = pm, conf, alert
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 6, 6)
        p.setClipPath(clip)
        p.fillRect(r, QColor("#101a2c"))
        if self._pm is not None and not self._pm.isNull():
            pm = self._pm
            s = min(r.width() / pm.width(), (r.height() - 8) / pm.height())
            w, h = pm.width() * s, pm.height() * s
            box = QRectF((r.width() - w) / 2, r.height() - h - 4, w, h)
            p.drawPixmap(box, pm, QRectF(pm.rect()))
            if self._alert:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(fz.RED), 1.5))
                p.drawRect(box.adjusted(0.75, 0.75, -0.75, -0.75))
            if self._conf is not None:
                txt = f"{self._conf:.2f}"
                p.setFont(fz.qfont(10.5, 700, mono=True))
                tw = p.fontMetrics().horizontalAdvance(txt) + 12
                pill = QRectF(box.center().x() - tw / 2, 3, tw, 18)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(fz.RED_FILL))
                p.drawRoundedRect(pill, 3, 3)
                p.setPen(QColor("#ffffff"))
                p.drawText(pill, Qt.AlignmentFlag.AlignCenter, txt)
        else:
            ic = fz.svg_pixmap("check", 22, 22, fz.GREEN if not self._alert else fz.MUTED)
            p.drawPixmap(int(r.width() / 2 - 11), int(r.height() / 2 - 11), ic)
        p.end()


class _AlertCard(QFrame):
    review_clicked = pyqtSignal()
    dismiss_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fzAlert")
        self.setFixedHeight(146)
        self.thumb = _Thumb(self)
        self.thumb.move(12, 11)
        self.dot = fz.Dot(fz.RED, 10, glow=True, parent=self)
        self.dot.move(171, 11)
        self.kicker = fz.label("FAOL OGOHLANTIRISH", 10.5, 700, fz.RED, mono=True, tracking=1, parent=self)
        self.kicker.setGeometry(190, 11, 300, 13)
        self.title = fz.label("", 16.5, 600, fz.TEXT, parent=self)
        self.title.setGeometry(174, 31, 340, 20)
        self.meta = QLabel(self)
        self.meta.setTextFormat(Qt.TextFormat.RichText)
        self.meta.setStyleSheet("background:transparent; border:none;")
        self.meta.setGeometry(174, 58, 340, 16)
        self.time = QLabel(self)
        self.time.setTextFormat(Qt.TextFormat.RichText)
        self.time.setStyleSheet("background:transparent; border:none;")
        self.time.setGeometry(174, 80, 340, 15)
        self.review = fz.danger_button("Ko‘rib chiqish", h=28, px=13, pad=0, radius=6)
        self.review.setParent(self)
        self.review.clicked.connect(self.review_clicked.emit)
        self.dismiss = fz.ghost_button("Yopish", h=28, px=13, pad=0, radius=6)
        self.dismiss.setParent(self)
        self.dismiss.clicked.connect(self._on_dismiss)
        self._ts: float | None = None
        self._active = False
        self._health = (0, 0, 0)            # (onlayn, oflayn, jami) — haqiqiy holat
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_time)
        self._tick.start(1000)
        self.set_idle(None)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        W = self.width()
        bw = (W - 174 - 15 - 7) / 2
        self.review.setGeometry(174, 102, int(bw), 28)
        self.dismiss.setGeometry(174 + int(bw) + 7, 102, int(W - 15 - (174 + int(bw) + 7)), 28)
        for l in (self.kicker, self.title, self.meta, self.time):
            l.setFixedWidth(max(50, W - l.x() - 12))

    def _style(self, danger: bool):
        bg, bd = (fz.RED_CARD, fz.RED_BORDER_STRONG) if danger else (fz.CARD, fz.BORDER)
        self.setStyleSheet(f"QFrame#fzAlert {{ background:{bg}; border:1px solid {bd}; border-radius:12px; }}")

    @staticmethod
    def _rich(parts):
        out = []
        for text, px, w, color, mono in parts:
            fam = fz.MONO if mono else fz.SANS
            out.append(f"<span style=\"font-family:'{fam}'; font-size:{fz.pt(px):.2f}pt; font-weight:{w}; color:{color};\">{text}</span>")
        return "".join(out)

    def set_alert(self, data: dict, pm: QPixmap | None):
        self._active = True
        self._style(True)
        self.dot.set_color(fz.RED)
        fz.restyle(self.kicker, 10.5, 700, fz.RED, mono=True, tracking=1)
        self.kicker.setText("FAOL OGOHLANTIRISH")
        self.title.setText("Shlemsiz ishchi aniqlandi")
        cam = data.get("camera_name") or "Kamera"
        tid = data.get("track_id")
        tid_s = f"{int(tid):04d}" if isinstance(tid, (int, float)) and tid >= 0 else "—"
        self.meta.setText(self._rich([(f"{cam} · ID&nbsp;", 12.5, 400, fz.TEXT2, False),
                                      (tid_s, 12.5, 700, fz.TEXT, True)]))
        self._ts = float(data.get("timestamp") or time.time())
        conf = data.get("confidence")
        self.thumb.set_data(pm, float(conf) if conf is not None else None, True)
        self.review.show()
        self.dismiss.show()
        self._update_time()

    def set_idle(self, last_ts: float | None):
        self._active = False
        self._style(False)
        self.dot.set_color(fz.GREEN)
        fz.restyle(self.kicker, 10.5, 700, fz.GREEN, mono=True, tracking=1)
        self.kicker.setText("TIZIM HOLATI")
        self.title.setText("Faol ogohlantirish yo‘q")
        self._ts = last_ts
        self._render_health()
        self.thumb.set_data(None, None, False)
        self.review.hide()
        self.dismiss.hide()
        self._update_time()

    def set_health(self, online: int, offline: int, total: int):
        self._health = (int(online), int(offline), int(total))
        if not self._active:
            self._render_health()

    def _render_health(self):
        online, offline, total = self._health
        if total <= 0:
            text, color = "Kamera ulanmagan", fz.TEXT2
        elif offline:
            text, color = f"{offline} ta kamera oflayn · {online}/{total} onlayn", fz.RED
        elif online == total:
            text, color = f"Barcha kameralar onlayn · {total} ta", fz.TEXT2
        else:
            text, color = f"Kameralar ulanmoqda · {online}/{total} onlayn", fz.TEXT2
        self.dot.set_color(fz.RED if offline else fz.GREEN)
        fz.restyle(self.kicker, 10.5, 700, fz.RED if offline else fz.GREEN, mono=True, tracking=1)
        self.meta.setText(self._rich([(text, 12.5, 400, color, False)]))

    def _on_dismiss(self):
        self.set_idle(self._ts)
        self.dismiss_clicked.emit()

    def _update_time(self):
        if self._ts is None:
            self.time.setText(self._rich([("Bugun hodisa qayd etilmagan", 12, 400, fz.TEXT2, False)]))
            return
        t = dt.datetime.fromtimestamp(self._ts)
        ago = max(0, int(time.time() - self._ts))
        if ago < 60:
            rel = f"{ago} soniya oldin"
        elif ago < 3600:
            rel = f"{ago // 60} daqiqa oldin"
        else:
            rel = f"{ago // 3600} soat oldin"
        prefix = "" if self._active else "Oxirgi hodisa: "
        self.time.setText(self._rich([(prefix, 12, 400, fz.TEXT2, False),
                                      (t.strftime("%H:%M:%S"), 12, 700, fz.TEXT, True),
                                      (f"&nbsp;· {rel}", 12, 400, fz.TEXT2, False)]))


# ════════════════════════════════════════════════════════════════════════════
#  Kamera plitkasi (266x150, radius 10)
# ════════════════════════════════════════════════════════════════════════════

class _CamTile(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, cam: dict, parent=None):
        super().__init__(parent)
        self.cam_id = int(cam.get("id"))
        self.cam_name = cam.get("name", f"Kamera {self.cam_id}")
        self.setObjectName("fzTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._alert = False
        self._status = "connecting"
        self.feed = FeedView(radius=9, bg=fz.CARD, gradient_h=56, parent=self)
        self.feed.set_reserve_bottom(30)    # nom qatori bilan ustma-ust tushmasin
        self._video = self.feed
        self.badge = fz.Pill("SHLEM YO‘Q", fz.RED_FILL, "#ffffff", px=10.5, weight=700, mono=True, h=20, pad=7,
                             radius=4, dot="#ffffff", dot_size=6, gap=6, tracking=0.5, parent=self)
        self.badge.hide()
        self.dot = fz.Dot(fz.MUTED, 6, parent=self)
        self.name = fz.label(self.cam_name, 12.5, 500, fz.TEXT, parent=self)
        self.fps = fz.label("", 10.5, 400, fz.TEXT2, mono=True, parent=self)
        self.fps.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._apply()

    def _apply(self):
        bd, bw = (fz.RED_FILL, 2) if self._alert else (fz.BORDER, 1)
        self.setStyleSheet(f"QFrame#fzTile {{ background:{fz.CARD}; border:{bw}px solid {bd}; border-radius:10px; }}")
        self._place()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        W, H = self.width(), self.height()
        b = 2 if self._alert else 1
        self.feed.setGeometry(b, b, W - 2 * b, H - 2 * b)
        self.badge.adjustSize()
        self.badge.move(8, 7)
        y = H - 30
        self.dot.move(9, y + 6)
        fps_w = 66 if self.fps.text() else 0
        name_w = max(20, W - 22 - 10 - (fps_w + 8 if fps_w else 0))
        fm = self.name.fontMetrics()
        self.name.setText(fm.elidedText(self.cam_name, Qt.TextElideMode.ElideRight, name_w))
        self.name.setToolTip(self.cam_name)
        self.name.setGeometry(22, y, name_w, 18)
        self.fps.setGeometry(W - 80, y + 1, 66, 16)

    def set_alert(self, v: bool):
        if v != self._alert:
            self._alert = v
            self.badge.setVisible(v)
            self._apply()
            self._update_dot()

    def set_status(self, status: str, fps: float | None = None):
        self._status = status
        if status == "offline":
            self.feed.show_offline()
            self.fps.setText("")
        elif status == "connecting" and not self.feed.has_frame():
            self.feed.show_connecting()
        had = bool(self.fps.text())
        if fps is not None and status == "live":
            self.fps.setText(f"{fps:.1f} fps")
        if had != bool(self.fps.text()):
            self._place()
        self._update_dot()

    def _update_dot(self):
        if self._alert:
            c = fz.RED
        elif self._status == "live":
            c = fz.GREEN
        else:
            c = fz.MUTED
        self.dot.set_color(c)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.cam_id)


# ════════════════════════════════════════════════════════════════════════════
#  Pastki panellar
# ════════════════════════════════════════════════════════════════════════════

class _Panel(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("fzPanel")
        self.setFixedHeight(196)
        self.setStyleSheet(f"QFrame#fzPanel {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:10px; }}")
        self.title = fz.label(title, 13.5, 600, fz.TEXT, parent=self)
        self.title.move(15, 12)
        self.right: QWidget | None = None

    def set_right(self, w: QWidget):
        self.right = w
        w.setParent(self)
        self._place_right()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_right()

    def _place_right(self):
        if self.right is not None:
            self.right.adjustSize()
            self.right.move(self.width() - 16 - self.right.width(), 12)


class _HourlyChart(QWidget):
    """06..21 soatlar; o'tgan — #1D3B66, joriy — #24497D, eng ko'p — #C8424F + tooltip,
    kelajak — 2px #1A2842 + kulrang yorliq."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = [0] * 24

    def set_counts(self, counts: list[int]):
        self._counts = list(counts) + [0] * (24 - len(counts))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        hours = list(range(6, 22))
        vals = [int(self._counts[h]) for h in hours]
        now_h = dt.datetime.now().hour
        mx = max(vals + [1])
        step = max(1, math.ceil(mx / 4))
        top_v = step * 4
        gx0, gx1 = 46.0, W - 18.0
        gy0, gy1 = 49.0, 161.0
        p.setFont(fz.qfont(10, 400, mono=True))
        for i in range(5):
            y = gy1 - (gy1 - gy0) * i / 4
            p.fillRect(QRectF(gx0, y, gx1 - gx0, 1), QColor(26, 40, 66, 128))
            p.setPen(QColor(fz.MUTED))
            p.drawText(QRectF(0, y - 7, 38, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(step * i))
        n = len(hours)
        # Figma: x0=49, qadam 32.4, ustun 26 → oxirgi ustun gx1-1 da tugaydi
        pitch = (gx1 - 1 - 49) / ((n - 1) + 26 / 32.4) if n > 1 else 0
        pitch = max(pitch, 1)
        bw = pitch * 26 / 32.4
        peak_i = max(range(n), key=lambda i: vals[i]) if any(v > 0 for v in vals) else -1
        p.setPen(Qt.PenStyle.NoPen)
        for i, (h, v) in enumerate(zip(hours, vals)):
            x = 49 + pitch * i
            future = h > now_h
            if future:
                p.setBrush(QColor(fz.BORDER))
                p.drawRoundedRect(QRectF(x, gy1 - 2, bw, 2), 1, 1)
            elif v > 0:
                bh = (gy1 - gy0) * v / top_v
                col = fz.BAR_PEAK if i == peak_i else (fz.BAR_CURRENT if h == now_h else fz.BAR)
                p.setBrush(QColor(col))
                p.drawRoundedRect(QRectF(x, gy1 - bh, bw, bh), 3, 3)
            p.setPen(QColor(fz.DIM if future else fz.MUTED))
            p.drawText(QRectF(x - 6, 171, bw + 12, 13), Qt.AlignmentFlag.AlignCenter, f"{h:02d}")
            p.setPen(Qt.PenStyle.NoPen)
        if peak_i >= 0:
            h, v = hours[peak_i], vals[peak_i]
            x = 49 + pitch * peak_i
            bh = (gy1 - gy0) * v / top_v
            txt = f"{h:02d}:00 · {v} ta"
            p.setFont(fz.qfont(10.5, 500, mono=True))
            tw = p.fontMetrics().horizontalAdvance(txt) + 16
            tip = QRectF(x + bw / 2 - tw / 2, gy1 - bh - 24, tw, 20)
            tip.moveLeft(max(4, min(W - tw - 4, tip.left())))
            tip.moveTop(max(26, tip.top()))
            p.setBrush(QColor(fz.TEXT))
            p.drawRoundedRect(tip, 5, 5)
            p.setPen(QColor(fz.CARD))
            p.drawText(tip, Qt.AlignmentFlag.AlignCenter, txt)
        p.end()


class _EventRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self._pm: QPixmap | None = None
        self.name = fz.label("", 13, 600, fz.TEXT, parent=self)
        self.name.move(76, 0)
        self.newdot = fz.Dot(fz.RED, 6, parent=self)
        self.desc = fz.label("", 12, 400, fz.RED, parent=self)
        self.desc.move(76, 19)
        self.time = fz.label("", 12, 400, fz.TEXT2, mono=True, parent=self)
        self.time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def set_event(self, name: str, desc: str, tstr: str, is_new: bool, pm: QPixmap | None):
        self.name.setText(name)
        self.name.adjustSize()
        self.desc.setText(desc)
        self.desc.adjustSize()
        self.time.setText(tstr)
        self.newdot.setVisible(is_new)
        self._pm = pm
        self._place()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        self.newdot.move(76 + self.name.width() + 6, 6)
        self.time.setGeometry(self.width() - 60, 10, 60, 15)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
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


class _DeptRow(QWidget):
    """Panel kengligidagi qator (panel koordinatalari): nom x16, trek 0.613W..W-70 (h4),
    qiymat x=W-40 (JetBrains Mono Medium 12)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self.name = fz.label("", 13, 400, fz.TEXT2, parent=self)
        self.name.move(16, 0)
        self.value = fz.label("", 12, 500, fz.TEXT, mono=True, parent=self)
        self._pct = 0.0

    def set_data(self, name: str, pct: float | None):
        self.name.setText(name)
        self._pct = pct if pct is not None else -1
        self.value.setText("—" if pct is None else f"{pct:.0f}%")
        self.value.adjustSize()
        self._place()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _track(self):
        W = self.width()
        return W * 0.6134, W - 70.0

    def _place(self):
        x0, _ = self._track()
        self.name.setFixedWidth(max(40, int(x0 - 16 - 12)))
        self.value.move(int(self.width() - 40), 0)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        x0, x1 = self._track()
        p.setBrush(QColor(fz.BORDER))
        p.drawRoundedRect(QRectF(x0, 6, x1 - x0, 4), 2, 2)
        if self._pct >= 0:
            p.setBrush(QColor(fz.ACCENT if self._pct >= 90 else fz.RED))
            p.drawRoundedRect(QRectF(x0, 6, (x1 - x0) * self._pct / 100.0, 4), 2, 2)
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  DashboardPage
# ════════════════════════════════════════════════════════════════════════════

class DashboardPage(QWidget):
    go_violations = pyqtSignal()
    focus_changed = pyqtSignal(int)        # katta oynadagi kamera
    add_camera_requested = pyqtSignal()
    ai_pause_requested = pyqtSignal(bool)
    go_cameras = pyqtSignal()

    def __init__(self, db, config_manager, parent=None):
        super().__init__(parent)
        fz.init_fonts()
        self.db = db
        self.cfg = config_manager
        self.setObjectName("fzMonitoring")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#fzMonitoring {{ background:{fz.BG}; }}")

        self._cameras: list[dict] = []
        self._selected: int | None = None
        self._status: dict[int, str] = {}
        self._fps: dict[int, float] = {}
        self._persons: dict[int, int] = {}
        self._det_today: dict[int, int] = {}
        self._viol_today_cam: dict[int, int] = {}
        self._alert_until: dict[int, float] = {}
        self._tiles: dict[int, _CamTile] = {}
        self._panels: dict = {}
        self._recent: list[dict] = []
        self._hourly = [0] * 24
        self._event_hours: list[float] = []
        self._no_helmet_today = 0
        self._total_persons = 0
        self._helmet_counts: dict[int, dict] = {}
        self._persons_hist: list[int] = []
        self._yesterday_comp: float | None = None
        self._focus_mode = False
        self._rec_start = time.time()
        self._last_event_ts: float | None = None
        self._search = ""

        self._db_busy = False
        self._db_again = False
        self._build()
        self._refresh_db()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_db)
        self._timer.start(30_000)
        self._sec = QTimer(self)
        self._sec.timeout.connect(self._tick)
        self._sec.start(1000)
        self._min = QTimer(self)
        self._min.timeout.connect(self._sample_persons)
        self._min.start(60_000)

    # ── qurilish ─────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 20, 16, 16)
        root.setSpacing(14)

        # KPI
        self._kpi_row = QWidget()
        self._kpi_row.setStyleSheet("background:transparent;")
        kl = QHBoxLayout(self._kpi_row)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(12)
        self._ring = _Ring()
        self.k_comp = _KPI("Muvofiqlik darajasi", "check", fz.BLUE_BG, self._ring, (19, 21))
        self._spark_v = _Spark(fz.RED, 30)
        self.k_viol = _KPI("Bugungi buzilishlar", "shield_alert", fz.RED_BG, self._spark_v, (18, 27))
        self._spark_p = _Spark(fz.ACCENT, 20)
        self.k_people = _KPI("Kadrdagi ishchilar", "users_cyan", fz.BLUE_BG, self._spark_p, (18, 37))
        self._grid = _StatusGrid()
        self.k_cams = _KPI("Kameralar", "video", fz.GREEN_BG, self._grid, (18, 48))
        for k in (self.k_comp, self.k_viol, self.k_people, self.k_cams):
            kl.addWidget(k, 1)
        root.addWidget(self._kpi_row)

        # O'rta: chap (video + timeline) | o'ng (alert + kameralar)
        mid = QHBoxLayout()
        mid.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(10)
        self.live = _LiveCard()
        self.live.prev_requested.connect(lambda: self._step_camera(-1))
        self.live.next_requested.connect(lambda: self._step_camera(1))
        self.live.expand_requested.connect(self._toggle_focus)
        self.live.snapshot_requested.connect(self._snapshot)
        left.addWidget(self.live, 1)
        self.timeline = _Timeline()
        left.addWidget(self.timeline)
        mid.addLayout(left, 858)

        self._right = QWidget()
        self._right.setStyleSheet("background:transparent;")
        rl = QVBoxLayout(self._right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.alert = _AlertCard()
        self.alert.review_clicked.connect(self.go_violations.emit)
        rl.addWidget(self.alert)
        rl.addSpacing(10)
        hdr = QWidget()
        hdr.setFixedHeight(18)
        hdr.setStyleSheet("background:transparent;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(1, 0, 0, 0)
        hl.addWidget(fz.label("Kameralar", 13.5, 600, fz.TEXT))
        hl.addStretch(1)
        self._all_link = fz.LinkButton("Barchasi · 0")
        self._all_link.clicked.connect(self.go_cameras.emit)
        hl.addWidget(self._all_link)
        rl.addWidget(hdr)
        rl.addSpacing(10)
        self._tile_area = QWidget()
        self._tile_area.setStyleSheet("background:transparent;")
        rl.addWidget(self._tile_area, 1)
        mid.addWidget(self._right, 538)
        root.addLayout(mid, 1)

        # Pastki qator
        self._bottom = QWidget()
        self._bottom.setStyleSheet("background:transparent;")
        bl = QHBoxLayout(self._bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)
        self.p_hourly = _Panel("Soatlar bo‘yicha buzilishlar")
        self._hourly_meta = fz.label("Bugun · jami 0", 12, 400, fz.MUTED)
        self.p_hourly.set_right(self._hourly_meta)
        self.chart = _HourlyChart(self.p_hourly)
        bl.addWidget(self.p_hourly, 580)
        self.p_recent = _Panel("So‘nggi hodisalar")
        link = fz.LinkButton("Hammasi")
        link.clicked.connect(self.go_violations.emit)
        self.p_recent.set_right(link)
        self._ev_rows = [_EventRow(self.p_recent) for _ in range(3)]
        self._ev_divs = [fz.hline() for _ in range(2)]
        for d in self._ev_divs:
            d.setParent(self.p_recent)
        self._ev_empty = fz.label("Bugun hodisa qayd etilmagan", 12, 400, fz.MUTED, parent=self.p_recent)
        bl.addWidget(self.p_recent, 447)
        self.p_dept = _Panel("Bo‘limlar")
        self.p_dept.set_right(fz.label("Muvofiqlik", 12, 400, fz.MUTED))
        self._dept_rows = [_DeptRow(self.p_dept) for _ in range(4)]
        bl.addWidget(self.p_dept, 357)
        root.addWidget(self._bottom)

        for p in (self.p_hourly, self.p_recent, self.p_dept):
            p.installEventFilter(self)
        self._tile_area.installEventFilter(self)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if ev.type() == QEvent.Type.Resize:
            if obj is self.p_hourly:
                self.chart.setGeometry(0, 0, obj.width(), obj.height())
            elif obj is self.p_recent:
                self._place_events()
            elif obj is self.p_dept:
                for i, r in enumerate(self._dept_rows):
                    r.setGeometry(0, 44 + 35 * i, obj.width() - 1, 16)
            elif obj is self._tile_area:
                self._layout_tiles()
        return super().eventFilter(obj, ev)

    def _place_events(self):
        W = self.p_recent.width()
        for i, r in enumerate(self._ev_rows):
            r.setGeometry(16, 43 + 53 * i, W - 33, 38)
        for i, d in enumerate(self._ev_divs):
            d.setGeometry(16, 88 + 53 * i, W - 33, 1)
        self._ev_empty.setGeometry(16, 48, W - 32, 16)

    # ── kameralar ────────────────────────────────────────────────────────
    def setup_cameras(self, cameras: list):
        self._cameras = list(cameras)
        for t in self._tiles.values():
            t.deleteLater()
        self._tiles.clear()
        self._status = {int(c.get("id")): "connecting" for c in cameras}
        for c in cameras:
            t = _CamTile(c, self._tile_area)
            t.clicked.connect(self._select)
            t.hide()
            self._tiles[t.cam_id] = t
        self._all_link.set_text(f"Barchasi · {len(cameras)}")
        prev = self._selected
        self._selected = None
        if cameras:
            ids = [int(c.get("id")) for c in cameras]
            self._select(prev if prev in ids else ids[0])
        else:
            self.live.title.setText("Kamera ulanmagan")
            self.live.sub.setText("Sozlamalar → Kameralar bo‘limidan kamera qo‘shing")
            self.live.feed.show_offline("Kamera yo‘q")
        self._update_cams_kpi()
        self._refresh_db()

    def _cam(self, cid):
        return next((c for c in self._cameras if int(c.get("id")) == cid), None)

    def _select(self, cam_id: int):
        self._selected = int(cam_id)
        self.focus_changed.emit(self._selected)
        cam = self._cam(self._selected) or {}
        self._panels = {self._selected: self.live}
        self.live.feed.clear()
        st = self._status.get(self._selected, "connecting")
        if st == "offline":
            self.live.feed.show_offline()
        self.live.cam.set_text(f"CAM-{self._selected:02d}")
        self.live.set_zone(cam.get("polygon_points") or [], "Xavfli zona")
        self._update_live_text()
        self._layout_tiles()

    def _step_camera(self, d: int):
        if not self._cameras:
            return
        ids = [int(c.get("id")) for c in self._cameras]
        i = ids.index(self._selected) if self._selected in ids else 0
        self._select(ids[(i + d) % len(ids)])

    def _visible_tile_ids(self, n: int) -> list[int]:
        now = time.time()
        order = {"live": 1, "connecting": 2, "offline": 3}
        ids = [int(c.get("id")) for c in self._cameras if int(c.get("id")) != self._selected]
        if self._search:
            ids = [i for i in ids if self._search in self._tiles[i].cam_name.lower()]
        ids.sort(key=lambda i: (0 if self._alert_until.get(i, 0) > now else 1,
                                order.get(self._status.get(i, "connecting"), 2), i))
        return ids[:n]

    def _layout_tiles(self):
        """Plitkalar 266:150 (16:9) nisbatda; ustunlar soni maydonga moslanadi —
        iloji bo'lsa barcha kameralar sig'adi, aks holda eng ko'p sig'adigani."""
        area = self._tile_area
        W, H = area.width(), area.height()
        if W <= 0 or H <= 0:
            return
        gap_x, gap_y = 6, 8
        n_avail = len(self._visible_tile_ids(999))
        best = None
        for cols in range(2, 9):
            tw = (W - gap_x * (cols - 1)) / cols
            if tw < 150:
                break
            th = tw * 150 / 266
            rows = max(1, int((H + gap_y) // (th + gap_y)))
            fit = min(n_avail, cols * rows)
            key = (fit >= n_avail, fit, tw)
            if best is None or key > best[0]:
                best = (key, cols, rows, tw, th)
            if fit >= n_avail:
                break
        if best is None:                             # juda tor maydon — bitta ustun
            tw = float(W)
            th = tw * 150 / 266
            best = (None, 1, max(1, int((H + gap_y) // (th + gap_y))), tw, th)
        _, cols, rows, tw, th = best
        if rows * (th + gap_y) - gap_y > H:          # bitta qator ham sig'masa — balandlikka moslash
            th = H
        show = self._visible_tile_ids(cols * rows)
        for cid, t in self._tiles.items():
            if cid not in show:
                t.hide()
        for k, cid in enumerate(show):
            r, c = divmod(k, cols)
            t = self._tiles[cid]
            t.setGeometry(int(c * (tw + gap_x)), int(r * (th + gap_y)), int(tw), int(th))
            t.show()

    # ── worker yangilanishlari ───────────────────────────────────────────
    def update_frame(self, cam_id: int, frame):
        if cam_id == self._selected:
            self.live.feed.set_frame(frame)
        t = self._tiles.get(cam_id)
        if t is not None and t.isVisible():
            t.feed.set_frame(frame)

    def on_stats(self, cam_id: int, stats: dict):
        cam_id = int(cam_id)
        conn = bool(stats.get("connected", False))
        fps = float(stats.get("fps", 0.0) or 0.0)
        self._fps[cam_id] = fps
        self._persons[cam_id] = int(stats.get("active_persons", 0) or 0)
        if stats.get("helmet_counts") is not None:
            self._helmet_counts[cam_id] = dict(stats["helmet_counts"])
        det = stats.get("detections_today")
        if det is not None:
            self._det_today[cam_id] = int(det or 0)
        old = self._status.get(cam_id)
        new = "live" if conn else ("offline" if old in ("live", "offline") else "connecting")
        self._status[cam_id] = new
        t = self._tiles.get(cam_id)
        if t is not None:
            t.set_status(new, fps)
        if cam_id == self._selected:
            if new == "offline":
                self.live.feed.show_offline()
            self._update_live_text()
        if old != new:
            self._update_cams_kpi()
            self._layout_tiles()
        self._update_compliance()

    def on_status(self, cam_id: int, text: str):
        pass

    def on_error(self, cam_id: int, msg: str):
        cam_id = int(cam_id)
        self._status[cam_id] = "offline"
        t = self._tiles.get(cam_id)
        if t is not None:
            t.set_status("offline")
        if cam_id == self._selected:
            self.live.feed.show_offline()
            self._update_live_text()
        self._update_cams_kpi()
        self._layout_tiles()

    def on_model_loaded(self, cam_id: int):
        pass

    def on_face_recognized(self, data: dict):
        pass

    def count_face_attempt(self, matched: bool):
        pass

    def set_total_persons(self, count: int):
        self._total_persons = max(0, int(count or 0))
        self._update_people_kpi()
        if self._selected is not None:
            self._update_live_text()

    def set_search_text(self, text: str):
        self._search = (text or "").strip().lower()
        self._layout_tiles()

    def on_violation(self, data: dict):
        data = dict(data)
        ts = float(data.get("timestamp") or time.time())
        data["timestamp"] = ts
        pm = data.get("_crop_pixmap")
        self._recent.insert(0, data)
        self._recent = self._recent[:10]
        cid = data.get("camera_id")
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            cid = None
        if cid is not None:
            self._viol_today_cam[cid] = self._viol_today_cam.get(cid, 0) + 1
            self._alert_until[cid] = time.time() + ALERT_HOLD_S
            t = self._tiles.get(cid)
            if t is not None:
                t.set_alert(True)
        d = dt.datetime.fromtimestamp(ts)
        self._hourly[d.hour] += 1
        self._event_hours.append(d.hour + d.minute / 60)
        nh = data.get("no_helmet_count")
        self._no_helmet_today = int(nh) if nh is not None else self._no_helmet_today + 1
        self._last_event_ts = ts
        self.alert.set_alert(data, pm if isinstance(pm, QPixmap) else self._load_pm(data))
        self._render_events()
        self._render_hourly()
        self._update_viol_kpi()
        self._update_compliance()
        self._layout_tiles()
        if cid == self._selected:
            self._update_live_text()

    # ── yangilash ────────────────────────────────────────────────────────
    def _tick(self):
        now = time.time()
        expired = [cid for cid, until in self._alert_until.items() if until <= now]
        for cid in expired:
            self._alert_until.pop(cid, None)
            t = self._tiles.get(cid)
            if t is not None:
                t.set_alert(False)
        if expired:
            self._layout_tiles()
        if int(now) % 60 == 0:
            self.timeline.update()

    def _sample_persons(self):
        self._persons_hist.append(self._total_persons)
        self._persons_hist = self._persons_hist[-30:]
        self._spark_p.set_values(self._persons_hist)

    def _update_live_text(self):
        cam = self._cam(self._selected) or {}
        name = cam.get("name", f"Kamera {self._selected}")
        dept = _dept_name(self.cfg, cam)
        self.live.title.setText(name)
        st = self._status.get(self._selected, "connecting")
        if st == "live":
            n = self._persons.get(self._selected, 0)
            alert = self._alert_until.get(self._selected, 0) > time.time()
            hc = self._helmet_counts.get(self._selected, {})
            if alert or hc.get("no_helmet", 0) > 0:
                state = "shlemsiz ishchi bor"
            elif not n:
                state = "kadrda ishchi yo‘q"
            elif hc.get("unknown", 0) > 0:
                # sariq quti — shlem hali aniqlanmagan; "barchasi shlemda" deyish noto'g'ri edi
                state = "shlem holati aniqlanmoqda"
            else:
                state = "barchasi shlemda"
            parts = [dept, f"{n} ishchi kadrda", state] if n else [dept, state]
            self.live.sub.setText(" · ".join(p for p in parts if p))
            self.live.live.show()
            fps = self._fps.get(self._selected, 0.0)
            img = self.live.feed.image()
            res = f"{img.height()}p · " if img is not None else ""
            self.live.res.set_text(f"{res}{fps:.0f} fps")
        else:
            self.live.sub.setText(" · ".join(p for p in [dept, "signal yo‘q" if st == "offline" else "ulanmoqda"] if p))
            self.live.live.setVisible(False)
            self.live.res.set_text("— fps")
        self.live._place()

    def _update_cams_kpi(self):
        total = len(self._cameras)
        online = sum(1 for c in self._cameras if self._status.get(int(c.get("id"))) == "live")
        self.k_cams.set_value(str(online), f"/{total}", 17, 58)
        off = sum(1 for c in self._cameras if self._status.get(int(c.get("id"))) == "offline")
        if off:
            self.k_cams.set_pill(f"{off} oflayn", "red")
        elif total and online == total:
            self.k_cams.set_pill("barchasi onlayn", "green")
        else:
            self.k_cams.set_pill("ulanmoqda" if total else "", "grey")
        self._grid.set_states([self._status.get(int(c.get("id")), "connecting") for c in self._cameras])
        self.alert.set_health(online, off, total)
        self.k_cams._layout()
        self._update_people_kpi()

    def _update_people_kpi(self):
        self.k_people.set_value(str(self._total_persons))
        online = sum(1 for c in self._cameras if self._status.get(int(c.get("id"))) == "live")
        self.k_people.set_pill(f"{online} kamera", "grey")

    def _update_viol_kpi(self):
        n = self._no_helmet_today
        self.k_viol.set_danger(n > 0)
        self.k_viol.set_value(str(n))
        hour_ago = time.time() - 3600
        last_hour = sum(1 for e in self._recent if float(e.get("timestamp", 0)) >= hour_ago)
        last_hour = max(last_hour, self._hourly[dt.datetime.now().hour])
        self.k_viol.set_pill(f"+{last_hour} / soat" if n else "", "red")
        now_h = dt.datetime.now().hour
        series = self._hourly[6:max(7, now_h + 1)] if now_h >= 6 else self._hourly[:now_h + 1]
        self._spark_v.set_values(series if len(series) >= 2 else [])

    def _compliance(self) -> float | None:
        det = sum(self._det_today.values())
        v = self._no_helmet_today
        if det <= 0:
            return None                     # aniqlash statistikasi yo'q — soxta 0% ko'rsatilmaydi
        return max(0.0, 100.0 * (1 - v / max(det, v)))

    def _update_compliance(self):
        comp = self._compliance()
        if comp is None:
            self.k_comp.set_value("—", "")
            self._ring.set_value(0)
            self.k_comp.set_pill("", "green")
        else:
            self.k_comp.set_value(f"{comp:.1f}", "%", 14, 60)
            self._ring.set_value(comp)
            if self._yesterday_comp is not None:
                d = comp - self._yesterday_comp
                self.k_comp.set_pill(f"{'+' if d >= 0 else '−'}{abs(d):.1f}", "green" if d >= 0 else "red")
            else:
                self.k_comp.set_pill("", "green")
        self._render_depts()

    def _render_hourly(self):
        self.chart.set_counts(self._hourly)
        self._hourly_meta.setText(f"Bugun · jami {sum(self._hourly)}")
        self.p_hourly._place_right()
        self.timeline.set_events(self._event_hours)

    def _load_pm(self, ev: dict) -> QPixmap | None:
        img = ev.get("_img")
        if img is None and "_img" not in ev:
            img = _load_image(ev)
            ev["_img"] = img
        return QPixmap.fromImage(img) if img is not None else None

    def _render_events(self):
        evs = self._recent[:3]
        now = time.time()
        self._ev_empty.setVisible(not evs)
        for i, r in enumerate(self._ev_rows):
            if i < len(evs):
                e = evs[i]
                ts = float(e.get("timestamp", 0) or 0)
                tid = e.get("track_id")
                tid_s = f"ID {int(tid):04d}" if isinstance(tid, (int, float)) and tid >= 0 else ""
                pm = e.get("_crop_pixmap") if isinstance(e.get("_crop_pixmap"), QPixmap) else e.get("_pm")
                if pm is None and "_pm" not in e:
                    pm = self._load_pm(e)
                    e["_pm"] = pm
                r.set_event(e.get("camera_name") or "Kamera",
                            " · ".join(x for x in ("Shlem yo‘q", tid_s) if x),
                            dt.datetime.fromtimestamp(ts).strftime("%H:%M") if ts else "",
                            now - ts < NEW_EVENT_S, pm)
                r.show()
            else:
                r.hide()
        for i, d in enumerate(self._ev_divs):
            d.setVisible(i + 1 < len(evs))

    def _render_depts(self):
        deps = []
        try:
            deps = self.cfg.get_departments() or []
        except Exception:
            pass
        rows = []
        for d in deps:
            ids = [int(c.get("id")) for c in self._cameras if c.get("department_id") == d.get("id")]
            det = sum(self._det_today.get(i, 0) for i in ids)
            v = sum(self._viol_today_cam.get(i, 0) for i in ids)
            if det > 0:
                pct = max(0.0, 100.0 * (1 - v / max(det, v)))
            else:
                pct = None
            rows.append((d.get("name", "Bo‘lim"), pct))
        for i, r in enumerate(self._dept_rows):
            if i < len(rows):
                r.set_data(*rows[i])
                r.show()
            else:
                r.hide()

    def _refresh_db(self):
        """DB so'rovlari fonda bajariladi (GUI qotmasligi uchun); bir vaqtda bittadan."""
        if self._db_busy:
            self._db_again = True
            return
        self._db_busy = True
        self._db_again = False
        run_async(self, self._query_db, self._apply_db, self._apply_db_error)

    def _query_db(self) -> dict:
        """Fon thread'ida ishlaydi — faqat ma'lumot va QImage qaytaradi."""
        out: dict = {}
        today = dt.date.today()
        try:
            out["no_helmet"] = int(self.db.get_today_count("no_helmet"))
        except Exception:
            pass
        try:
            out["hourly"] = [int(h.get("count", 0)) for h in self.db.get_hourly_counts()]
        except Exception:
            pass
        try:
            by_cam = self.db.get_today_counts_by_camera() or {}
            out["by_cam"] = {int(k): int(v) for k, v in by_cam.items() if str(k).lstrip("-").isdigit()}
        except Exception:
            pass
        try:
            rows = [dict(r) for r in self.db.get_violations(date_from=today, date_to=today, limit=200)]
            for r in rows[:10]:
                r["_img"] = _load_image(r)
            out["rows"] = rows
        except Exception:
            pass
        try:
            out["yesterday"] = self._compliance_for(today - dt.timedelta(days=1))
        except Exception:
            out["yesterday"] = None
        return out

    def _apply_db_error(self, exc):
        self._db_busy = False
        if self._db_again:
            self._refresh_db()

    def _apply_db(self, res: dict):
        self._db_busy = False
        if "no_helmet" in res:
            self._no_helmet_today = res["no_helmet"]
        if "hourly" in res:
            self._hourly = res["hourly"]
        if "by_cam" in res:
            self._viol_today_cam = res["by_cam"]
        rows = res.get("rows")
        if rows is not None:
            self._event_hours = []
            for r in rows:
                ts = float(r.get("timestamp") or 0)
                if ts:
                    d = dt.datetime.fromtimestamp(ts)
                    self._event_hours.append(d.hour + d.minute / 60)
            if rows:
                self._last_event_ts = max(float(r.get("timestamp") or 0) for r in rows)
            live_keys = {(e.get("track_id"), int(e.get("timestamp", 0))) for e in self._recent}
            merged = list(self._recent)
            for r in rows[:10]:
                if (r.get("track_id"), int(r.get("timestamp", 0))) not in live_keys:
                    merged.append(r)
            merged.sort(key=lambda e: float(e.get("timestamp", 0) or 0), reverse=True)
            self._recent = merged[:10]
        self._yesterday_comp = res.get("yesterday")
        if not self.alert._active:
            self.alert.set_idle(self._last_event_ts)
        self._render_hourly()
        self._render_events()
        self._update_viol_kpi()
        self._update_compliance()
        self._update_cams_kpi()
        if self._db_again:
            self._refresh_db()

    def _compliance_for(self, day: dt.date) -> float | None:
        conn = self.db._conn()
        row = conn.execute("SELECT SUM(detections) AS d FROM daily_stats WHERE date = ?", (day.isoformat(),)).fetchone()
        det = int(row["d"] or 0) if row else 0
        if det <= 0:
            return None
        t0 = int(dt.datetime.combine(day, dt.time.min).timestamp())
        t1 = int(dt.datetime.combine(day, dt.time.max).timestamp())
        v = conn.execute("SELECT COUNT(*) AS c FROM violations WHERE timestamp BETWEEN ? AND ? AND violation_type = 'no_helmet'",
                         (t0, t1)).fetchone()
        v = int(v["c"] or 0) if v else 0
        return max(0.0, 100.0 * (1 - v / max(det, v)))

    # ── harakatlar ───────────────────────────────────────────────────────
    def _toggle_focus(self):
        self._focus_mode = not self._focus_mode
        for w in (self._kpi_row, self._right, self._bottom, self.timeline):
            w.setVisible(not self._focus_mode)
        self.live.btns[1].setToolTip("Kichraytirish" if self._focus_mode else "Kattalashtirish")

    def _snapshot(self):
        img = self.live.feed.image()
        if img is None:
            return
        out = Path.cwd() / "screenshots"
        out.mkdir(exist_ok=True)
        path = out / f"cam{self._selected:02d}_{dt.datetime.now():%Y%m%d_%H%M%S}.jpg"
        img.save(str(path), "JPEG", 95)
        try:
            from app.ui.widgets.toast import show_toast
            show_toast(self, f"Kadr saqlandi: {path.name}", "success")
        except Exception:
            pass
