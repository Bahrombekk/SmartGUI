"""
Ramkasiz oynalar uchun umumiy qismlar.

EdgeResizer   — ramkasiz oynani chetlaridan tortib o'lchamini o'zgartirish.
FramedDialog  — Windows sarlavhasi o'rniga ilova dizaynidagi sarlavha qatori
                bo'lgan dialog. Subklass o'z layout'ini `self.body` ga quradi:

    class MyDialog(FramedDialog):
        def __init__(self, parent=None):
            super().__init__(parent, resizable=True)
            self.setWindowTitle("Sarlavha")
            lay = QVBoxLayout(self.body)
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui import fz

# Segoe Fluent Icons / MDL2 Assets — Windows'ning o'z sarlavha belgilari
GLYPH_MIN = "\uE921"
GLYPH_MAX = "\uE922"
GLYPH_RESTORE = "\uE923"
GLYPH_CLOSE = "\uE8BB"


class EdgeResizer(QObject):
    """
    Butun ilovadagi sichqoncha harakatini kuzatadi, lekin faqat `window`
    chetidagi zonada ishlaydi. `inset` — oyna chetidan ichkaridagi shaffof
    (soya) qism; zona shu joydan boshlanib `margin` px ichkariga kiradi.
    O'lchashni Windows bajaradi (startSystemResize) — snap ham ishlaydi.
    """

    def __init__(self, window: QWidget, margin: int = 6, inset: int = 0):
        super().__init__(window)
        self._window = window
        self.margin = margin
        self.inset = inset
        self._cursor_set = False
        self._app_filter = False
        # Butun ilova filtri faqat oyna ko'rinib turganda — yopilgan dialoglar
        # har bir Qt hodisasiga (25–30 fps kadrlar ham) Python chaqiruvi qo'shmasin.
        window.installEventFilter(self)
        if window.isVisible():
            self._set_app_filter(True)
        window.destroyed.connect(self._restore_cursor)

    def _set_app_filter(self, on: bool):
        app = QApplication.instance()
        if app is None or on == self._app_filter:
            return
        if on:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)
            self._restore_cursor()
        self._app_filter = on

    def _edges_at(self, gpos) -> Qt.Edge:
        w = self._window
        if w.isMaximized() or w.isFullScreen() or not w.isVisible():
            return Qt.Edge(0)
        g = w.frameGeometry().adjusted(self.inset, self.inset, -self.inset, -self.inset)
        m = self.margin
        x, y = gpos.x(), gpos.y()
        if not (g.left() - self.inset <= x <= g.right() + self.inset
                and g.top() - self.inset <= y <= g.bottom() + self.inset):
            return Qt.Edge(0)
        edges = Qt.Edge(0)
        if x <= g.left() + m:
            edges |= Qt.Edge.LeftEdge
        elif x >= g.right() - m:
            edges |= Qt.Edge.RightEdge
        if y <= g.top() + m:
            edges |= Qt.Edge.TopEdge
        elif y >= g.bottom() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges: Qt.Edge) -> Qt.CursorShape:
        E = Qt.Edge
        if edges in (E.LeftEdge | E.TopEdge, E.RightEdge | E.BottomEdge):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (E.RightEdge | E.TopEdge, E.LeftEdge | E.BottomEdge):
            return Qt.CursorShape.SizeBDiagCursor
        if edges & (E.LeftEdge | E.RightEdge):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _set_cursor(self, edges: Qt.Edge):
        if edges:
            shape = self._cursor_for(edges)
            if self._cursor_set:
                QApplication.changeOverrideCursor(shape)
            else:
                QApplication.setOverrideCursor(shape)
                self._cursor_set = True
        else:
            self._restore_cursor()

    def _restore_cursor(self, *_):
        if self._cursor_set:
            QApplication.restoreOverrideCursor()
            self._cursor_set = False

    def eventFilter(self, obj, event):
        et = event.type()
        if obj is self._window and et in (QEvent.Type.Show, QEvent.Type.Hide):
            self._set_app_filter(et == QEvent.Type.Show)
            return False
        if et not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            return False
        if not isinstance(obj, QWidget) or obj.window() is not self._window:
            return False
        edges = self._edges_at(event.globalPosition().toPoint())
        if et == QEvent.Type.MouseMove:
            if not event.buttons():
                self._set_cursor(edges)
            return False
        if edges and event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemResize(edges):
                self._restore_cursor()
                return True
        return False


def _remove_native_border(widget: QWidget) -> None:
    """
    Windows 11 ramkasiz shaffof oynalar atrofida ham 1px chegara va yumaloq
    burchak chizadi — u karta tashqarisidagi shaffof soya hoshiyasini ramka
    qilib ko'rsatadi. DWM ga chegara rangi "yo'q" va burchak "yumaloqlanmasin" deymiz.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = wintypes.HWND(int(widget.winId()))
        dwm = ctypes.windll.dwmapi
        DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND = 33, 1
        DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE = 34, 0xFFFFFFFE
        pref = ctypes.c_int(DWMWCP_DONOTROUND)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                  ctypes.byref(pref), ctypes.sizeof(pref))
        color = ctypes.c_uint(DWMWA_COLOR_NONE)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR,
                                  ctypes.byref(color), ctypes.sizeof(color))
    except Exception:
        pass  # Windows 10 yoki DWM yo'q — atribut shunchaki qo'llanmaydi


class _TitleBar(QWidget):
    """Sudrab ko'chirish; ikki marta bosish — kattalashtirish (resizable bo'lsa)."""

    def __init__(self, dialog: "FramedDialog"):
        super().__init__(objectName="appFrameBar")
        self._dialog = dialog
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dialog.resizable:
            self._dialog.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def _form_qss() -> str:
    """Dialog ichidagi standart forma elementlari — Figma tokenlari.

    Ota oyna (sahifa) uslubi meros bo'lib o'tmasligi uchun aniq beriladi;
    o'z stylesheet'i bor widgetlar o'z ko'rinishini saqlaydi.
    """
    chev = str(fz.ICONS / "chevron_down.svg").replace("\\", "/")
    check = str(fz.ICONS / "check_dark.svg").replace("\\", "/")
    font = fz.css_font(13, 400)
    return f"""
        QWidget#appFrameBody QLabel {{ background: transparent; border: none; color: {fz.TEXT2}; }}
        QWidget#appFrameBody QLineEdit, QWidget#appFrameBody QComboBox,
        QWidget#appFrameBody QDateEdit, QWidget#appFrameBody QSpinBox,
        QWidget#appFrameBody QDoubleSpinBox {{
            background: {fz.INPUT}; color: {fz.TEXT}; border: 1px solid {fz.BORDER};
            border-radius: 7px; padding: 0 10px; min-height: 34px; {font}
            selection-background-color: {fz.ACCENT}; selection-color: {fz.ON_ACCENT};
        }}
        QWidget#appFrameBody QLineEdit:hover, QWidget#appFrameBody QComboBox:hover,
        QWidget#appFrameBody QDateEdit:hover {{ border-color: {fz.SEG_BORDER}; }}
        QWidget#appFrameBody QLineEdit:focus, QWidget#appFrameBody QComboBox:focus,
        QWidget#appFrameBody QDateEdit:focus, QWidget#appFrameBody QComboBox:on {{ border-color: {fz.ACCENT}; }}
        QWidget#appFrameBody QComboBox::drop-down, QWidget#appFrameBody QDateEdit::drop-down {{
            border: none; width: 30px; subcontrol-origin: padding; subcontrol-position: center right;
        }}
        QWidget#appFrameBody QComboBox::down-arrow, QWidget#appFrameBody QDateEdit::down-arrow {{
            image: url("{chev}"); width: 13px; height: 13px;
        }}
        QWidget#appFrameBody QComboBox QAbstractItemView {{
            background: {fz.CARD}; color: {fz.TEXT}; border: 1px solid {fz.SEG_BORDER};
            border-radius: 8px; padding: 4px; outline: 0;
            selection-background-color: {fz.ACTIVE}; selection-color: {fz.TEXT}; {font}
        }}
        QWidget#appFrameBody QCheckBox {{ background: transparent; color: {fz.TEXT}; spacing: 9px; {font} }}
        QWidget#appFrameBody QCheckBox::indicator {{
            width: 16px; height: 16px; border-radius: 4px;
            border: 1px solid {fz.SEG_BORDER}; background: {fz.INPUT};
        }}
        QWidget#appFrameBody QCheckBox::indicator:checked {{
            background: {fz.ACCENT}; border-color: {fz.ACCENT}; image: url("{check}");
        }}
        QWidget#appDialogFooter {{ background: transparent; border-top: 1px solid {fz.BORDER}; }}
        QWidget#appFrameBody QPushButton:focus {{ outline: none; }}
    """


def dialog_footer() -> tuple[QWidget, QHBoxLayout]:
    """Dialog pastki tugmalar qatori (ustida ajratgich). Tugmalar o'ngga tekislanadi."""
    w = QWidget(objectName="appDialogFooter")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    row = QHBoxLayout(w)
    row.setContentsMargins(20, 14, 20, 16)
    row.setSpacing(8)
    row.addStretch(1)
    return w, row


def dialog_button(text: str, kind: str = "ghost") -> QPushButton:
    """Figma dialog tugmasi (h34): primary | ghost | danger."""
    if kind == "primary":
        b = fz.primary_button(text, h=34, px=13, pad=18, radius=8)
    elif kind == "danger":
        b = fz.danger_button(text, h=34, px=13, pad=16, radius=8)
    else:
        b = fz.ghost_button(text, h=34, px=13, pad=16, radius=8)
    b.setMinimumWidth(96)
    b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return b


def field_label(text: str) -> QLabel:
    return fz.label(text, 12.5, 500, fz.TEXT2)


class _BarButton(QPushButton):
    """Sarlavha qatori tugmasi — Figma SVG ikonka, yopishda hover qizil + oq ikonka."""

    def __init__(self, icon: str, close: bool = False):
        super().__init__()
        self._icon = icon
        self._close = close
        self.setFixedSize(28, 28)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_icon(icon)

    def set_icon(self, icon: str, color: str | None = None):
        self._icon = icon
        self.setIcon(fz.svg_icon(icon, 12, color or fz.MUTED))
        from PyQt6.QtCore import QSize
        self.setIconSize(QSize(12, 12))

    def enterEvent(self, e):
        self.set_icon(self._icon, fz.RED if self._close else fz.TEXT)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.set_icon(self._icon)
        super().leaveEvent(e)


class FramedDialog(QDialog):
    SHADOW = 16

    def __init__(self, parent=None, *, resizable: bool = False):
        super().__init__(parent)
        self.resizable = resizable
        # NoDropShadowWindowHint: Windows'ning o'z soyasi/chegarasi shaffof hoshiya
        # atrofida ortiqcha ramka chizmasin (soyani o'zimiz chizamiz)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(*(self.SHADOW,) * 4)

        self._card = QFrame(objectName="appFrameCard")
        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 150))
        self._card.setGraphicsEffect(shadow)
        self._outer.addWidget(self._card)

        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(1, 1, 1, 1)
        card_lay.setSpacing(0)

        fz.init_fonts()
        bar = _TitleBar(self)
        bar.setFixedHeight(48)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(16, 0, 10, 0)
        bar_lay.setSpacing(9)
        logo = fz.Icon("logo", 16)
        logo.setStyleSheet("background: transparent;")
        bar_lay.addWidget(logo)
        self._title_lbl = QLabel(objectName="appFrameTitle")
        bar_lay.addWidget(self._title_lbl, 1)
        self._max_btn = None
        if resizable:
            self._max_btn = self._bar_button("win_max", "Kattalashtirish")
            self._max_btn.clicked.connect(self.toggle_maximize)
            bar_lay.addWidget(self._max_btn)
        close_btn = self._bar_button("win_close", "Yopish", object_name="appFrameClose")
        close_btn.clicked.connect(self.reject)
        self._close_btn = close_btn
        bar_lay.addWidget(close_btn)
        card_lay.addWidget(bar)

        self.body = QWidget(objectName="appFrameBody")
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_lay.addWidget(self.body, 1)

        self.windowTitleChanged.connect(self._title_lbl.setText)
        if resizable:
            self._resizer = EdgeResizer(self, margin=6, inset=self.SHADOW)
        self._apply_frame_style()

    def exec(self) -> int:
        """Yopilgach dialog ota-widget'dan ajratiladi: chaqiruvchi havolani
        qo'yib yuborganda Python uni o'chiradi (aks holda har ochilgan dialog
        ota-widget o'chguncha xotirada qolardi)."""
        res = super().exec()
        flags = self.windowFlags()
        self.setParent(None)
        self.setWindowFlags(flags)
        return res

    def _bar_button(self, icon: str, tooltip: str, object_name: str = "appFrameBtn") -> QPushButton:
        btn = _BarButton(icon, object_name == "appFrameClose")
        btn.setObjectName(object_name)
        btn.setToolTip(tooltip)
        return btn

    def toggle_maximize(self):
        # Qt'ning showNormal() ramkasiz oynada Windows oynasini "zoomed" holatda
        # qoldiradi — Windows'da ShowWindow (SW_RESTORE=9 / SW_MAXIMIZE=3) ishlatiladi.
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                zoomed = bool(ctypes.windll.user32.IsZoomed(hwnd))
                ctypes.windll.user32.ShowWindow(hwnd, 9 if zoomed else 3)
                return
            except Exception:
                pass
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            maximized = self.isMaximized()
            self._outer.setContentsMargins(*((0 if maximized else self.SHADOW),) * 4)
            if self._max_btn is not None:
                self._max_btn.set_icon("win_restore" if maximized else "win_max")
                self._max_btn.setToolTip("Tiklash" if maximized else "Kattalashtirish")
            self._apply_frame_style()

    def showEvent(self, event):
        super().showEvent(event)
        _remove_native_border(self)
        if not getattr(self, "_centered", False):
            self._centered = True
            parent = self.parentWidget()
            ref = (parent.window().frameGeometry() if parent
                   else QApplication.primaryScreen().availableGeometry())
            self.move(ref.center() - self.rect().center())

    def frame_style(self) -> str:
        """Subklass qo'shimcha QSS qo'shishi uchun (`self.body` ichidagi widgetlar)."""
        return ""

    def _apply_frame_style(self):
        # Figma tokenlari: karta #0b1426, chegara #2a3a56, ajratgich #1a2842, Inter
        radius = 0 if self.isMaximized() else 12
        r1 = max(0, radius - 1)
        self.setStyleSheet(f"""
            QFrame#appFrameCard {{
                background: {fz.CARD};
                border: 1px solid {fz.SEG_BORDER};
                border-radius: {radius}px;
            }}
            QWidget#appFrameBar {{
                background: {fz.CARD};
                border-top-left-radius: {r1}px;
                border-top-right-radius: {r1}px;
                border-bottom: 1px solid {fz.BORDER};
            }}
            QWidget#appFrameBody {{
                background: {fz.CARD};
                border-bottom-left-radius: {r1}px;
                border-bottom-right-radius: {r1}px;
            }}
            QWidget#appFrameBody QCheckBox {{ background: transparent; }}
            QLabel#appFrameTitle {{
                color: {fz.TEXT}; background: transparent; {fz.css_font(14, 600)}
            }}
            QPushButton#appFrameBtn, QPushButton#appFrameClose {{
                background: transparent; border: none; border-radius: 7px; padding: 0; min-width: 0;
            }}
            QPushButton#appFrameBtn:hover {{ background: {fz.RAISED}; }}
            QPushButton#appFrameClose:hover {{ background: {fz.RED_BG}; }}
        """ + _form_qss() + self.frame_style())
