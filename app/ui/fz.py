"""
fz — SafeZone Figma dizayn tizimi (aniq qiymatlar, Figma faylidan olingan).

Barcha qiymatlar Figma 1440x900 freymlaridan: ranglar, shriftlar (Inter +
JetBrains Mono), o'lchamlar va komponentlar (toggle, slider, segmented,
tugmalar, kartalar). Sahifalar faqat shu moduldagi tokenlardan foydalanadi.

Shrift o'lchamlari Figma px'da beriladi; Qt'ga pt sifatida (px * 0.75)
uzatiladi — shunda 12.5px kabi kasr o'lchamlar ham aniq chiziladi.
Global QSS butun ilovaga shrift qo'ygani uchun har bir widget shriftini o'z
stylesheet'ida oladi (`css_font`).
"""
from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, pyqtSignal, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QPainter,
                         QPixmap, QIcon, QPen, QBrush, QGuiApplication, QPainterPath)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (QWidget, QLabel, QFrame, QPushButton, QHBoxLayout,
                             QVBoxLayout, QSizePolicy)

ROOT = Path(__file__).resolve().parents[2]
ICONS = ROOT / "images" / "fz"
FONTS = ROOT / "fonts"

# ── Ranglar (Figma faylidagi aniq qiymatlar) ─────────────────────────────────
BG = "#070e1c"            # sahifa / top bar foni
CARD = "#0b1426"          # karta, qidiruv, ghost tugma foni
CARD_DEEP = "#0a1220"     # jonli video kartasi
BORDER = "#1a2842"        # karta chegarasi, ajratgich, slider trek
INPUT = "#0e1a2e"         # input, segmented foni
RAISED = "#111c33"        # yordam kartasi, ogohlantirish pill
ACTIVE = "#15223b"        # faol tab / menyu / segment
SEG_BORDER = "#2a3a56"    # faol segment chegarasi, overlay tugma chegarasi
GHOST_BORDER = "#3a4a66"  # ikkilamchi (outline) tugma chegarasi
TEXT = "#e8f0fb"
TEXT2 = "#b4c0d3"
MUTED = "#7e8ea8"
DIM = "#4a5872"
ACCENT = "#1fb6ff"
ACCENT_HOVER = "#4cc4ff"
ON_ACCENT = "#04121f"     # yorqin tugmadagi to'q matn
RED = "#ff5a6a"           # qizil matn / nuqta
RED_FILL = "#e0303f"      # qizil to'ldirish (LIVE, badge, xavf tugmasi)
RED_BG = "#3a1622"        # qizil pill / ikon qutisi
RED_CARD = "#141629"      # xavf kartasi foni
RED_BORDER = "#5c2434"
RED_BORDER_STRONG = "#6b2433"
GREEN = "#29c992"
GREEN_BG = "#0c2e2a"
GREEN_BORDER = "#16483e"
BLUE_BG = "#0e2a45"       # ko'k ikon qutisi / faol chip foni
CHIP_ACTIVE_BG = "#0d2a45"
BAR = "#1d3b66"
BAR_CURRENT = "#24497d"
BAR_PEAK = "#c8424f"
OVERLAY = "rgba(7,16,28,0.75)"
OVERLAY_STRONG = "rgba(7,16,28,0.85)"
GRID = "rgba(26,40,66,0.5)"

SANS = "Inter"
MONO = "JetBrains Mono"

# Figma "normal" line-height (Inter ~1.21em) — label qutilari shu balandlikda
LINE = 1.21


# ── Shriftlar ────────────────────────────────────────────────────────────────

_fonts_ready = False


def init_fonts() -> None:
    """`fonts/` ichidagi Inter / JetBrains Mono fayllarini yuklaydi.
    Bo'lmasa — eng yaqin tizim shriftlariga almashtiriladi."""
    global _fonts_ready
    if _fonts_ready:
        return
    _fonts_ready = True
    if FONTS.exists():
        for f in list(FONTS.glob("*.ttf")) + list(FONTS.glob("*.otf")):
            QFontDatabase.addApplicationFont(str(f))
    fams = set(QFontDatabase.families())
    if SANS not in fams:
        QFont.insertSubstitutions(SANS, ["Segoe UI Variable Text", "Segoe UI"])
    if MONO not in fams:
        QFont.insertSubstitutions(MONO, ["Cascadia Mono", "Consolas"])


def pt(px: float) -> float:
    return px * 0.75


def qfont(px: float, weight: int = 400, mono: bool = False, tracking: float = 0.0) -> QFont:
    f = QFont(MONO if mono else SANS)
    f.setPointSizeF(pt(px))
    f.setWeight(QFont.Weight(weight))
    if tracking:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking)
    return f


def css_font(px: float, weight: int = 400, mono: bool = False, tracking: float = 0.0) -> str:
    fam = MONO if mono else SANS
    s = f"font-family:'{fam}'; font-size:{pt(px):.3f}pt; font-weight:{weight};"
    if tracking:
        s += f" letter-spacing:{tracking}px;"
    return s


def line_h(px: float) -> int:
    return int(math.ceil(px * LINE))


def text_w(text: str, px: float, weight: int = 400, mono: bool = False, tracking: float = 0.0) -> float:
    fm = QFontMetricsF(qfont(px, weight, mono, tracking))
    return fm.horizontalAdvance(text)


# ── Ikonkalar (SVG → aniq o'lchamdagi pixmap) ───────────────────────────────

_px_cache: dict = {}


def _dpr() -> float:
    app = QGuiApplication.instance()
    scr = app.primaryScreen() if app else None
    return scr.devicePixelRatio() if scr else 1.0


def svg_pixmap(name: str, w: float, h: float | None = None, color: str | None = None) -> QPixmap:
    h = h or w
    dpr = max(1.0, _dpr())
    key = (name, w, h, color, dpr)
    pm = _px_cache.get(key)
    if pm is not None:
        return pm
    path = ICONS / f"{name}.svg"
    pm = QPixmap(int(round(w * dpr)), int(round(h * dpr)))
    pm.fill(Qt.GlobalColor.transparent)
    if path.exists():
        r = QSvgRenderer(str(path))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p, QRectF(0, 0, pm.width(), pm.height()))
        if color:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(pm.rect(), QColor(color))
        p.end()
    pm.setDevicePixelRatio(dpr)
    _px_cache[key] = pm
    return pm


def svg_icon(name: str, size: float, color: str | None = None) -> QIcon:
    return QIcon(svg_pixmap(name, size, size, color))


class Icon(QLabel):
    def __init__(self, name: str, size: float, color: str | None = None, parent=None, h: float | None = None):
        super().__init__(parent)
        self._name, self._w, self._h = name, size, h or size
        self.setFixedSize(int(math.ceil(size)), int(math.ceil(self._h)))
        self.setStyleSheet("background:transparent; border:none;")
        self.set_color(color)

    def set_color(self, color: str | None):
        self.setPixmap(svg_pixmap(self._name, self._w, self._h, color))

    def set_icon(self, name: str, color: str | None = None):
        self._name = name
        self.set_color(color)


# ── Matn ─────────────────────────────────────────────────────────────────────

def label(text: str, px: float, weight: int = 400, color: str = TEXT, mono: bool = False,
          tracking: float = 0.0, parent=None, fixed_h: bool = True, wrap: bool = False,
          align=None) -> QLabel:
    l = QLabel(text, parent)
    l.setStyleSheet(f"color:{color}; background:transparent; border:none; {css_font(px, weight, mono, tracking)}")
    if wrap:
        l.setWordWrap(True)
    elif fixed_h:
        l.setFixedHeight(line_h(px))
    if align is not None:
        l.setAlignment(align)
    return l


def restyle(l: QLabel, px: float, weight: int = 400, color: str = TEXT, mono: bool = False, tracking: float = 0.0):
    l.setStyleSheet(f"color:{color}; background:transparent; border:none; {css_font(px, weight, mono, tracking)}")


def hline(color: str = BORDER, h: int = 1) -> QFrame:
    f = QFrame()
    f.setFixedHeight(h)
    f.setStyleSheet(f"background:{color}; border:none;")
    return f


def vline(color: str = BORDER, w: int = 1, h: int | None = None) -> QFrame:
    f = QFrame()
    f.setFixedWidth(w)
    if h:
        f.setFixedHeight(h)
    f.setStyleSheet(f"background:{color}; border:none;")
    return f


# ── Kartalar ─────────────────────────────────────────────────────────────────

_card_seq = 0


def card(bg: str = CARD, border: str = BORDER, radius: int = 12, bw: float = 1) -> QFrame:
    """Figma kartasi: fon + 1px chegara + radius. Ichidagi QLabel'lar shaffof."""
    global _card_seq
    _card_seq += 1
    f = QFrame()
    name = f"fzCard{_card_seq}"
    f.setObjectName(name)
    f.setStyleSheet(
        f"QFrame#{name} {{ background:{bg}; border:{bw}px solid {border}; border-radius:{radius}px; }}"
    )
    return f


def set_card_style(f: QFrame, bg: str = CARD, border: str = BORDER, radius: int = 12, bw: float = 1):
    name = f.objectName()
    f.setStyleSheet(
        f"QFrame#{name} {{ background:{bg}; border:{bw}px solid {border}; border-radius:{radius}px; }}"
    )


# ── Tugmalar ─────────────────────────────────────────────────────────────────

def _btn(text: str, h: int) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def primary_button(text: str, h: int = 31, px: float = 13, pad: int = 16, radius: int = 8,
                   icon: str | None = None, icon_size: int = 15) -> QPushButton:
    b = _btn(text, h)
    b.setStyleSheet(
        "QPushButton {"
        f"background:{ACCENT}; color:{ON_ACCENT}; border:none; border-radius:{radius}px;"
        f"padding:0 {pad}px; {css_font(px, 600)} }}"
        f"QPushButton:hover {{ background:{ACCENT_HOVER}; }}"
        "QPushButton:pressed { background:#18a0e3; }"
        f"QPushButton:disabled {{ background:{SEG_BORDER}; color:{MUTED}; }}"
    )
    if icon:
        b.setIcon(svg_icon(icon, icon_size, ON_ACCENT))
        b.setIconSize(QSize(icon_size, icon_size))
    return b


def ghost_button(text: str, h: int = 31, px: float = 12.5, pad: int = 13, radius: int = 7,
                 icon: str | None = None, icon_size: int = 14, icon_color: str = TEXT2) -> QPushButton:
    b = _btn(text, h)
    b.setStyleSheet(
        "QPushButton {"
        f"background:{CARD}; color:{TEXT}; border:1px solid {GHOST_BORDER}; border-radius:{radius}px;"
        f"padding:0 {pad}px; {css_font(px, 600)} }}"
        f"QPushButton:hover {{ background:{RAISED}; border-color:#4a5b78; }}"
        f"QPushButton:pressed {{ background:{ACTIVE}; }}"
    )
    if icon:
        b.setIcon(svg_icon(icon, icon_size, icon_color))
        b.setIconSize(QSize(icon_size, icon_size))
    return b


def danger_button(text: str, h: int = 28, px: float = 13, pad: int = 14, radius: int = 6,
                  icon: str | None = None, icon_size: int = 14) -> QPushButton:
    b = _btn(text, h)
    b.setStyleSheet(
        "QPushButton {"
        f"background:{RED_FILL}; color:#ffffff; border:none; border-radius:{radius}px;"
        f"padding:0 {pad}px; {css_font(px, 600)} }}"
        "QPushButton:hover { background:#ea4552; }"
        "QPushButton:pressed { background:#c92734; }"
    )
    if icon:
        b.setIcon(svg_icon(icon, icon_size, "#ffffff"))
        b.setIconSize(QSize(icon_size, icon_size))
    return b


def text_button(text: str, px: float = 13, color: str = TEXT2, weight: int = 500, h: int = 31) -> QPushButton:
    b = _btn(text, h)
    b.setStyleSheet(
        "QPushButton {"
        f"background:transparent; color:{color}; border:none; padding:0 4px; {css_font(px, weight)} }}"
        f"QPushButton:hover {{ color:{TEXT}; }}"
    )
    return b


class LinkButton(QWidget):
    """"Barchasi · 10 →" ko'rinishidagi havola (Inter Medium 12.5 + arrowR 13, gap 3)."""
    clicked = pyqtSignal()

    def __init__(self, text: str, px: float = 12.5, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self._lbl = label(text, px, 500, ACCENT)
        lay.addWidget(self._lbl)
        lay.addWidget(Icon("arrow_r", 13))
        self.setFixedHeight(18)

    def set_text(self, t: str):
        self._lbl.setText(t)

    def mousePressEvent(self, e):
        self.clicked.emit()
        e.accept()


# ── Pill ─────────────────────────────────────────────────────────────────────

class Pill(QFrame):
    """Fonli kichik yorliq: [nuqta] matn. Figma pill'lariga mos."""

    def __init__(self, text: str, bg: str, fg: str, px: float = 11, weight: int = 500, mono: bool = True,
                 h: int = 20, pad: int = 7, radius: int = 6, border: str | None = None,
                 dot: str | None = None, dot_size: int = 6, gap: int = 6, tracking: float = 0.0, parent=None):
        super().__init__(parent)
        self._bg, self._border, self._radius = bg, border, radius
        self.setFixedHeight(h)
        self._apply()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(pad, 0, pad, 0)
        lay.setSpacing(gap)
        self._dot = None
        if dot:
            self._dot = Dot(dot, dot_size)
            lay.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lbl = label(text, px, weight, fg, mono, tracking)
        lay.addWidget(self._lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _apply(self):
        b = f"border:1px solid {self._border};" if self._border else "border:none;"
        self.setStyleSheet(f"Pill {{ background:{self._bg}; {b} border-radius:{self._radius}px; }}")

    def set_text(self, t: str):
        self._lbl.setText(t)
        self.adjustSize()

    def set_colors(self, bg: str, fg: str, border: str | None = None, dot: str | None = None,
                   px: float = 11, weight: int = 500, mono: bool = True, tracking: float = 0.0):
        self._bg, self._border = bg, border
        self._apply()
        restyle(self._lbl, px, weight, fg, mono, tracking)
        if self._dot is not None and dot:
            self._dot.set_color(dot)


class Dot(QWidget):
    def __init__(self, color: str, size: int = 6, glow: bool = False, parent=None):
        super().__init__(parent)
        self._c = color
        self._glow = glow
        s = size + (6 if glow else 0)
        self._size = size
        self.setFixedSize(s, s)

    def set_color(self, c: str):
        self._c = c
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QRectF(self.rect()).center()
        if self._glow:
            g = QColor(self._c)
            g.setAlphaF(0.3)
            p.setPen(QPen(g, 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = self._size / 2 + 1.5
            p.drawEllipse(c, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._c))
        r = self._size / 2
        p.drawEllipse(c, r, r)
        p.end()


class IconBox(QFrame):
    """24x24 radius 6 rangli quti + 14px ikonka (KPI kartalarida)."""

    def __init__(self, icon: str, bg: str, size: int = 24, icon_size: int = 14, color: str | None = None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setObjectName("fzIconBox")
        self.setStyleSheet(f"QFrame#fzIconBox {{ background:{bg}; border:none; border-radius:6px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(Icon(icon, icon_size, color), 0, Qt.AlignmentFlag.AlignCenter)


# ── Toggle 34x20 ─────────────────────────────────────────────────────────────

class Toggle(QWidget):
    """Figma toggle: on — trek #1FB6FF, tugmacha #07101C (cx24); off — #2A3A56 / #C9D3E1 (cx10); r7."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self._checked = bool(checked)
        self._pos = 1.0 if self._checked else 0.0
        self.setFixedSize(34, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):
        self._pos = float(v)
        self.update()

    def is_checked(self) -> bool:
        return self._checked

    isChecked = is_checked

    def set_checked(self, v: bool, animate: bool = False):
        v = bool(v)
        if v == self._checked:
            return
        self._checked = v
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(1.0 if v else 0.0)
            self._anim.start()
        else:
            self._pos = 1.0 if v else 0.0
            self.update()

    setChecked = set_checked

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.set_checked(not self._checked, animate=True)
            self.toggled.emit(self._checked)
            e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._pos
        on_t, off_t = QColor("#1FB6FF"), QColor("#2A3A56")
        track = QColor(
            int(off_t.red() + (on_t.red() - off_t.red()) * t),
            int(off_t.green() + (on_t.green() - off_t.green()) * t),
            int(off_t.blue() + (on_t.blue() - off_t.blue()) * t),
        )
        on_k, off_k = QColor("#07101C"), QColor("#C9D3E1")
        knob = QColor(
            int(off_k.red() + (on_k.red() - off_k.red()) * t),
            int(off_k.green() + (on_k.green() - off_k.green()) * t),
            int(off_k.blue() + (on_k.blue() - off_k.blue()) * t),
        )
        if not self.isEnabled():
            track.setAlphaF(0.45)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 34, 20), 10, 10)
        p.setBrush(knob)
        p.drawEllipse(QPointF(10 + 14 * t, 10), 7, 7)
        p.end()


# ── Slider (trek 4px, thumb 18px) ────────────────────────────────────────────

class Slider(QWidget):
    """Figma slider: trek #1A2842 h4 r2, to'ldirish #1FB6FF, thumb r7.5 #C9E9FF + 3px #1FB6FF."""
    valueChanged = pyqtSignal(float)

    def __init__(self, minimum: float, maximum: float, value: float, step: float = 0.01,
                 track_w: int = 220, parent=None):
        super().__init__(parent)
        self._min, self._max, self._step = float(minimum), float(maximum), float(step)
        self._val = float(value)
        self._tw = track_w
        self.setFixedSize(track_w + 18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def value(self) -> float:
        return self._val

    def set_value(self, v: float, emit: bool = False):
        v = max(self._min, min(self._max, float(v)))
        if self._step > 0:
            v = round((v - self._min) / self._step) * self._step + self._min
            v = round(v, 6)
        if v != self._val:
            self._val = v
            self.update()
            if emit:
                self.valueChanged.emit(v)

    setValue = set_value

    def _ratio(self) -> float:
        span = self._max - self._min
        return 0.0 if span <= 0 else (self._val - self._min) / span

    def _from_x(self, x: float):
        r = max(0.0, min(1.0, (x - 9) / self._tw))
        self.set_value(self._min + r * (self._max - self._min), emit=True)

    def mousePressEvent(self, e):
        self._from_x(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._from_x(e.position().x())

    def wheelEvent(self, e):
        d = 1 if e.angleDelta().y() > 0 else -1
        self.set_value(self._val + d * (self._step or (self._max - self._min) / 100), emit=True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        y = 7
        p.setBrush(QColor("#1A2842"))
        p.drawRoundedRect(QRectF(9, y, self._tw, 4), 2, 2)
        fw = self._ratio() * self._tw
        if fw > 0:
            p.setBrush(QColor("#1FB6FF"))
            p.drawRoundedRect(QRectF(9, y, fw, 4), 2, 2)
        cx = 9 + fw
        p.setPen(QPen(QColor("#1FB6FF"), 3))
        p.setBrush(QColor("#C9E9FF"))
        p.drawEllipse(QPointF(cx, 9), 7.5 - 1.5, 7.5 - 1.5)
        p.end()


# ── Segmented control ────────────────────────────────────────────────────────

class Segmented(QWidget):
    """Figma segmented: konteyner h31 #0E1A2E + 1px #1A2842 r8, ichki pad 3;
    segment h23 r6, matn Inter Medium 12.5 #B4C0D3 (pad 12); faol — #15223B +
    1px #2A3A56, Inter SemiBold 12.5 #E8F0FB."""
    changed = pyqtSignal(int)

    def __init__(self, options: list[str], current: int = 0, h: int = 31, px: float = 12.5,
                 pad: float = 11.5, parent=None, active_bg: str = ACTIVE, active_border: str = SEG_BORDER,
                 active_fg: str = TEXT):
        super().__init__(parent)
        self._opts = list(options)
        self._cur = current
        self._h = h
        self._px = px
        self._pad = pad
        self._abg, self._abd, self._afg = active_bg, active_border, active_fg
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layout_segments()

    def _layout_segments(self):
        self._rects = []
        x = 3.0
        for o in self._opts:
            w = text_w(o, self._px, 500) + self._pad * 2
            self._rects.append(QRectF(x, 3, w, self._h - 8))
            x += w
        self.setFixedSize(int(math.ceil(x + 3)), self._h)

    def current(self) -> int:
        return self._cur

    def set_current(self, i: int):
        """-1 — hech qaysi variant tanlanmagan."""
        if -1 <= i < len(self._opts) and i != self._cur:
            self._cur = i
            self.update()

    def mouseMoveEvent(self, e):
        h = next((i for i, r in enumerate(self._rects) if r.contains(e.position())), -1)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        for i, r in enumerate(self._rects):
            if r.contains(e.position()):
                if i != self._cur:
                    self._cur = i
                    self.update()
                    self.changed.emit(i)
                break

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(INPUT))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self._h - 1), 8, 8)
        for i, (o, r) in enumerate(zip(self._opts, self._rects)):
            active = i == self._cur
            if active:
                p.setPen(QPen(QColor(self._abd), 1))
                p.setBrush(QColor(self._abg))
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
            elif i == self._hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 10))
                p.drawRoundedRect(r, 6, 6)
            p.setFont(qfont(self._px, 600 if active else 500))
            p.setPen(QColor(self._afg if active else TEXT2))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, o)
        p.end()


# ── Sozlamalar kartasi / qatori ──────────────────────────────────────────────

class SettingsCard(QFrame):
    """Sarlavha (Inter SemiBold 13.5, y16) + tavsif (Inter 11.5 #7E8EA8, y38) +
    ajratgich (y62), so'ng qatorlar. Ichki gorizontal chekinish 16px; o'ng
    tomonda ixtiyoriy amal (tugma)."""

    def __init__(self, title: str, desc: str = "", parent=None, action: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("fzSettingsCard")
        self.setStyleSheet(
            f"QFrame#fzSettingsCard {{ background:{CARD}; border:1px solid {BORDER}; border-radius:12px; }}"
        )
        # QFrame chegarasi kontentdan 1px oladi → Figma koordinatalari: kontent x16..w-18
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(15, 0, 17, 0)
        self._lay.setSpacing(0)
        head = QWidget()
        head.setFixedHeight(61)
        head.setStyleSheet("background:transparent;")
        self.title = label(title, 13.5, 600, TEXT, parent=head)
        self.title.move(0, 15)
        self.desc = label(desc, 11.5, 400, MUTED, parent=head)
        self.desc.move(0, 37)
        self._head = head
        self._action = None
        if action is not None:
            self.set_action(action)
        self._lay.addWidget(head)
        self._lay.addWidget(hline())
        self._rows = 0
        self._lay.addStretch(1)

    def set_action(self, w: QWidget):
        self._action = w
        w.setParent(self._head)
        w.show()
        self._place_action()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.title.setFixedWidth(max(10, self._head.width() - (self._action.width() + 12 if self._action else 0)))
        self.desc.setFixedWidth(self.title.width())
        self._place_action()

    def _place_action(self):
        if self._action is not None:
            self._action.adjustSize()
            self._action.move(self._head.width() - self._action.width(), (61 - self._action.height()) // 2)

    def add_row(self, row: QWidget, divider: bool = True):
        idx = self._lay.count() - 1   # stretch'dan oldin
        if self._rows and divider:
            self._lay.insertWidget(idx, hline())
            idx += 1
        self._lay.insertWidget(idx, row)
        self._rows += 1
        return row

    def add_widget(self, w: QWidget):
        self._lay.insertWidget(self._lay.count() - 1, w)
        return w

    def clear_rows(self):
        while self._lay.count() > 3:      # head, divider, stretch qoladi
            it = self._lay.takeAt(2)
            if it.widget():
                it.widget().deleteLater()
        self._rows = 0


def line_edit(placeholder: str = "", mono: bool = False, password: bool = False,
              width: int | None = None, h: int = 31, px: float = 12.5):
    from PyQt6.QtWidgets import QLineEdit
    from PyQt6.QtGui import QPalette
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(h)
    if width:
        e.setFixedWidth(width)
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setStyleSheet(
        "QLineEdit {"
        f"background:{INPUT}; color:{TEXT}; border:1px solid {BORDER}; border-radius:7px;"
        f"padding:0 9px; selection-background-color:{ACCENT}; selection-color:{ON_ACCENT};"
        f"{css_font(px, 400, mono)} }}"
        f"QLineEdit:hover {{ border-color:{SEG_BORDER}; }}"
        f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
    )
    pal = e.palette()
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    e.setPalette(pal)
    return e


class PathInput(QFrame):
    """Figma "Input · model": #0E1A2E, 1px #1A2842, r7, h31, JetBrains Mono 12.5;
    o'ng ichida papka ikonkasi (14px, x=w-27)."""
    browse = pyqtSignal()

    def __init__(self, width: int = 280, placeholder: str = "", mono: bool = True, icon: str = "folder", parent=None):
        super().__init__(parent)
        self.setObjectName("fzPathInput")
        self.setFixedSize(width, 31)
        self.setStyleSheet(
            f"QFrame#fzPathInput {{ background:{INPUT}; border:1px solid {BORDER}; border-radius:7px; }}"
        )
        from PyQt6.QtWidgets import QLineEdit
        from PyQt6.QtGui import QPalette
        self.edit = QLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setStyleSheet(
            f"QLineEdit {{ background:transparent; border:none; color:{TEXT}; padding:0;"
            f" selection-background-color:{ACCENT}; selection-color:{ON_ACCENT}; {css_font(12.5, 400, mono)} }}"
        )
        pal = self.edit.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
        self.edit.setPalette(pal)
        self.edit.setGeometry(10, 1, width - 40, 29)
        self._btn = QPushButton(self)
        self._btn.setFixedSize(22, 22)
        self._btn.setIcon(svg_icon(icon, 14))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(
            "QPushButton { background:transparent; border:none; border-radius:5px; }"
            f"QPushButton:hover {{ background:{ACTIVE}; }}"
        )
        self._btn.move(width - 31, 4)
        self._btn.clicked.connect(self.browse.emit)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, t: str):
        self.edit.setText(t)
        self.edit.setCursorPosition(0)


class SettingRow(QWidget):
    """Figma sozlama qatori: balandlik 67 (yoki berilgan), sarlavha Inter Medium 13
    (row+15), tavsif Inter 11.5 #7E8EA8 (row+37), o'ngda boshqaruv (vertikal markaz)."""

    def __init__(self, title: str, desc: str = "", control: QWidget | None = None,
                 height: int = 66, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setContentsMargins(0, 15 - 1, 0, 0)
        col.setSpacing(37 - 15 - line_h(13))
        self.title = label(title, 13, 500, TEXT)
        col.addWidget(self.title)
        self.desc = label(desc, 11.5, 400, MUTED)
        col.addWidget(self.desc)
        # Uzun matn ustun kengligini majburlamasin (Figma ustunlari teng: 572/572)
        for l in (self.title, self.desc):
            l.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            l.setMinimumWidth(40)
        col.addStretch(1)
        lay.addLayout(col, 1)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.control = control


class SliderValue(QWidget):
    """Slider + qiymat yorlig'i Figma joylashuvida: trek, so'ng `gap` px dan keyin
    `value_w` kenglikdagi yorliq (o'ngga yoki chapga tekislangan)."""

    def __init__(self, slider: "Slider", value: QLabel, gap: int, value_w: int, right_align: bool = True, parent=None):
        super().__init__(parent)
        self.slider, self.value = slider, value
        slider.setParent(self)
        value.setParent(self)
        value.setFixedWidth(value_w)
        value.setAlignment((Qt.AlignmentFlag.AlignRight if right_align else Qt.AlignmentFlag.AlignLeft)
                           | Qt.AlignmentFlag.AlignVCenter)
        tw = slider._tw
        slider.move(0, 0)
        value.move(9 + tw + gap, 0)
        value.setFixedHeight(18)
        self.setFixedSize(9 + tw + gap + value_w, 18)
        self.setStyleSheet("background:transparent;")


def value_label(text: str, px: float = 12.5, width: int | None = None) -> QLabel:
    l = label(text, px, 500, TEXT, mono=True)
    l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if width:
        l.setFixedWidth(width)
    return l


def hbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0)) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for x in widgets:
        if isinstance(x, int):
            lay.addSpacing(x)
        elif x is None:
            lay.addStretch(1)
        else:
            lay.addWidget(x)
    return w


# ── Figma tugmasi (aniq ikonka–matn oralig'i bilan, o'zi chiziladi) ──────────

class Button(QPushButton):
    """kind: primary | ghost | danger | subtle | outline.
    Figma: h31 r8 pad14, ikonka 15 + gap 7 + matn (Inter 13)."""

    STYLES = {
        "primary": (ACCENT, None, ON_ACCENT, ACCENT_HOVER),
        "ghost": (CARD, GHOST_BORDER, TEXT, RAISED),
        "danger": (RED_FILL, None, "#ffffff", "#ea4552"),
        "subtle": (None, None, TEXT2, ACTIVE),
        "outline": (CARD, BORDER, TEXT2, RAISED),
    }

    def __init__(self, text: str = "", kind: str = "ghost", icon: str | None = None, icon_size: int = 15,
                 h: int = 31, px: float = 13, weight: int = 600, pad: int = 14, gap: int = 7,
                 radius: int = 8, fg: str | None = None, width: int | None = None, parent=None):
        super().__init__(parent)
        self._text, self._kind, self._icon = text, kind, icon
        self._isz, self._px, self._w, self._pad, self._gap, self._r = icon_size, px, weight, pad, gap, radius
        self._fg = fg
        self._hover = False
        self._fixed_w = width
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(h)
        self.setFixedWidth(width or self._natural_w())
        self.setStyleSheet("QPushButton { background:transparent; border:none; }")

    def _natural_w(self) -> int:
        w = self._pad * 2
        if self._icon:
            w += self._isz + (self._gap if self._text else 0)
        if self._text:
            w += text_w(self._text, self._px, self._w)
        return int(math.ceil(w))

    def setText(self, t: str):
        self._text = t
        if not self._fixed_w:
            self.setFixedWidth(self._natural_w())
        self.update()

    def text(self) -> str:
        return self._text

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        bg, border, fg, hov = self.STYLES.get(self._kind, self.STYLES["ghost"])
        fg = self._fg or fg
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        fill = hov if (self._hover and self.isEnabled()) else bg
        if self.isDown() and self._kind in ("ghost", "outline"):
            fill = ACTIVE
        p.setBrush(QColor(fill) if fill else Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(border), 1) if border else Qt.PenStyle.NoPen)
        if fill or border:
            p.drawRoundedRect(r, self._r, self._r)
        if not self.isEnabled():
            p.setOpacity(0.45)
        tw = text_w(self._text, self._px, self._w) if self._text else 0
        total = (self._isz if self._icon else 0) + (self._gap if (self._icon and self._text) else 0) + tw
        x = (self.width() - total) / 2
        if self._icon:
            pm = svg_pixmap(self._icon, self._isz, self._isz, fg)
            p.drawPixmap(QPointF(x, (self.height() - self._isz) / 2), pm)
            x += self._isz + (self._gap if self._text else 0)
        if self._text:
            p.setFont(qfont(self._px, self._w))
            p.setPen(QColor(fg))
            p.drawText(QRectF(x, 0, tw + 2, self.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()


class Chip(QPushButton):
    """Filtr chip: h28 r14, pad 13; matn Inter Medium 12.5 + son JBM 11 (gap 6);
    faol — #0D2A45 fon + #1FB6FF chegara/matn; nofaol — #0B1426 + #1A2842, #B4C0D3 / son #7E8EA8."""

    def __init__(self, text: str, count="", active: bool = False, dot: str | None = None, parent=None):
        super().__init__(parent)
        self._t, self._c, self._active, self._dot = text, str(count), active, dot
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(28)
        self.setStyleSheet("QPushButton { background:transparent; border:none; }")
        self._resize()

    def _resize(self):
        w = 13 + text_w(self._t, 12.5, 500) + 13
        if self._dot:
            w += 6 + 6
        if self._c:
            w += 6 + text_w(self._c, 11, 400, mono=True)
        self.setFixedWidth(int(math.ceil(w)))

    def set_count(self, c):
        self._c = str(c)
        self._resize()
        self.update()

    def set_active(self, v: bool):
        self._active = v
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._active:
            p.setBrush(QColor(CHIP_ACTIVE_BG))
            p.setPen(QPen(QColor(ACCENT), 1))
        else:
            p.setBrush(QColor(RAISED if self._hover else CARD))
            p.setPen(QPen(QColor(SEG_BORDER if self._hover else BORDER), 1))
        p.drawRoundedRect(r, 14, 14)
        x = 13.0
        if self._dot:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._dot))
            p.drawEllipse(QPointF(x + 3, 14), 3, 3)
            x += 12
        p.setFont(qfont(12.5, 500))
        p.setPen(QColor(ACCENT if self._active else TEXT2))
        tw = text_w(self._t, 12.5, 500)
        p.drawText(QRectF(x, 0, tw + 2, 28), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._t)
        if self._c:
            x += tw + 6
            p.setFont(qfont(11, 400, mono=True))
            p.setPen(QColor(ACCENT if self._active else MUTED))
            p.drawText(QRectF(x, 0, 60, 28), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._c)
        p.end()


class Dropdown(QPushButton):
    """Figma filtr dropdown: h28 r8 pad12 #0B1426 + #1A2842; [ikonka 13] matn
    Inter Medium 12.5 #B4C0D3 + chevron 13. Bosilganda menyu ochiladi."""
    changed = pyqtSignal(int)

    def __init__(self, options: list, current: int = 0, icon: str | None = None, h: int = 28,
                 min_w: int = 0, bg: str = CARD, fg: str = TEXT2, px: float = 12.5, weight: int = 500,
                 pad: int = 12, radius: int = 8, parent=None):
        super().__init__(parent)
        self._opts, self._cur, self._icon, self._min_w, self._bg = list(options), current, icon, min_w, bg
        self._fg, self._px, self._wt, self._pad, self._rad = fg, px, weight, pad, radius
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(h)
        self.setStyleSheet("QPushButton { background:transparent; border:none; }")
        self.clicked.connect(self._open)
        self._resize()

    def _resize(self):
        t = self.current_text()
        w = self._pad + (13 + 7 if self._icon else 0) + text_w(t, self._px, self._wt) + 7 + 13 + 12
        self.setFixedWidth(max(self._min_w, int(math.ceil(w))))

    def set_options(self, opts: list, current: int = 0):
        self._opts = list(opts)
        self._cur = current if 0 <= current < len(self._opts) else 0
        self._resize()
        self.update()

    def current(self) -> int:
        return self._cur

    def current_text(self) -> str:
        return str(self._opts[self._cur]) if 0 <= self._cur < len(self._opts) else ""

    def set_current(self, i: int):
        if 0 <= i < len(self._opts):
            self._cur = i
            self._resize()
            self.update()

    def _open(self):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.setStyleSheet(
            f"QMenu {{ background:{CARD}; border:1px solid {BORDER}; border-radius:8px; padding:4px; {css_font(12.5, 500)} }}"
            f"QMenu::item {{ color:{TEXT2}; padding:6px 14px; border-radius:6px; }}"
            f"QMenu::item:selected {{ background:{ACTIVE}; color:{TEXT}; }}"
        )
        for i, o in enumerate(self._opts):
            a = m.addAction(str(o))
            a.setData(i)
        act = m.exec(self.mapToGlobal(self.rect().bottomLeft()))
        i = int(act.data()) if act is not None else None
        m.deleteLater()            # har ochilishda yangi menyu — eskisi xotirada qolmasin
        if i is not None:
            if i != self._cur:
                self.set_current(i)
                self.changed.emit(i)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(RAISED if self._hover else self._bg))
        p.setPen(QPen(QColor(SEG_BORDER if self._hover else BORDER), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), self._rad, self._rad)
        x = float(self._pad)
        cy = self.height() / 2
        if self._icon:
            p.drawPixmap(QPointF(x, cy - 6.5), svg_pixmap(self._icon, 13, 13, TEXT2))
            x += 13 + 7
        p.setFont(qfont(self._px, self._wt))
        p.setPen(QColor(self._fg))
        p.drawText(QRectF(x, 0, self.width() - x - 32, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.current_text())
        p.drawPixmap(QPointF(self.width() - 12 - 13, cy - 6.5), svg_pixmap("chevron_down", 13, 13, TEXT2))
        p.end()


class SearchBox(QFrame):
    """Figma qidiruv: #0E1A2E + #1A2842 r8 h31, ikonka 14 (12, 8.5), matn x35 Inter 12.5."""

    def __init__(self, placeholder: str, width: int | None = 260, h: int = 31, bg: str = INPUT, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QLineEdit
        from PyQt6.QtGui import QPalette
        self.setObjectName("fzSearchBox")
        self.setFixedHeight(h)
        if width:
            self.setFixedWidth(width)
        self.setStyleSheet(f"QFrame#fzSearchBox {{ background:{bg}; border:1px solid {BORDER}; border-radius:8px; }}")
        self._ic = Icon("search", 14, parent=self)
        self._ic.move(12, int((h - 14) / 2))
        self.edit = QLineEdit(self)
        self.edit.setFrame(False)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setStyleSheet(
            f"QLineEdit {{ background:transparent; border:none; color:{TEXT}; padding:0;"
            f" selection-background-color:{ACCENT}; selection-color:{ON_ACCENT}; {css_font(12.5, 400)} }}"
        )
        pal = self.edit.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
        self.edit.setPalette(pal)
        self.edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.edit.setGeometry(33, 1, self.width() - 43, self.height() - 2)

    def mousePressEvent(self, e):
        self.edit.setFocus()


class PageHeader(QWidget):
    """Sahifa sarlavhasi: title Inter SemiBold 19 (y0, h23) + subtitle Inter 12.5 #B4C0D3
    (y27, h15); o'ngda tugmalar y12 (h31), oraliq `gap`."""

    def __init__(self, title: str, subtitle: str = "", gap: int = 16, parent=None):
        super().__init__(parent)
        self.setFixedHeight(43)
        self.setStyleSheet("background:transparent;")
        self.title = label(title, 19, 600, TEXT, parent=self)
        self.title.setGeometry(0, 0, 600, 23)
        self.sub = label(subtitle, 12.5, 400, TEXT2, parent=self)
        self.sub.setGeometry(0, 27, 900, 15)
        self._right: list = []
        self._gap = gap

    def add_right(self, w: QWidget, y: int = 12):
        w.setParent(self)
        self._right.append((w, y))
        self._place()
        return w

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        x = self.width()
        for w, y in reversed(self._right):
            if not w.isVisible() and w.isHidden():
                continue
            x -= w.width()
            w.move(x, y)
            x -= self._gap
