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

from app.shared.paths import resource_path
from app.ui.styles import C

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
        QApplication.instance().installEventFilter(self)
        window.destroyed.connect(self._restore_cursor)

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

        bar = _TitleBar(self)
        bar.setFixedHeight(40)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 0, 4, 0)
        bar_lay.setSpacing(8)
        logo = QLabel()
        logo_pix = QPixmap(str(resource_path("images", "app_icon.png")))
        if not logo_pix.isNull():
            logo.setPixmap(logo_pix.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
        logo.setStyleSheet("background: transparent;")
        bar_lay.addWidget(logo)
        self._title_lbl = QLabel(objectName="appFrameTitle")
        bar_lay.addWidget(self._title_lbl, 1)
        self._max_btn = None
        if resizable:
            self._max_btn = self._bar_button(GLYPH_MAX, "Kattalashtirish")
            self._max_btn.clicked.connect(self.toggle_maximize)
            bar_lay.addWidget(self._max_btn)
        close_btn = self._bar_button(GLYPH_CLOSE, "Yopish", object_name="appFrameClose")
        close_btn.clicked.connect(self.reject)
        bar_lay.addWidget(close_btn)
        card_lay.addWidget(bar)

        self.body = QWidget(objectName="appFrameBody")
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card_lay.addWidget(self.body, 1)

        self.windowTitleChanged.connect(self._title_lbl.setText)
        if resizable:
            self._resizer = EdgeResizer(self, margin=6, inset=self.SHADOW)
        self._apply_frame_style()

    def _bar_button(self, glyph: str, tooltip: str, object_name: str = "appFrameBtn") -> QPushButton:
        btn = QPushButton(glyph, objectName=object_name)
        btn.setFixedSize(40, 32)
        btn.setToolTip(tooltip)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def toggle_maximize(self):
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
                self._max_btn.setText(GLYPH_RESTORE if maximized else GLYPH_MAX)
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
        radius = 0 if self.isMaximized() else 12
        self.setStyleSheet(f"""
            QFrame#appFrameCard {{
                background: {C('bg_card')};
                border: 1px solid {C('border_strong')};
                border-radius: {radius}px;
            }}
            QWidget#appFrameBar {{
                background: {C('bg_panel')};
                border-top-left-radius: {max(0, radius - 1)}px;
                border-top-right-radius: {max(0, radius - 1)}px;
                border-bottom: 1px solid {C('border')};
            }}
            QWidget#appFrameBody {{
                background: {C('bg_card')};
                border-bottom-left-radius: {max(0, radius - 1)}px;
                border-bottom-right-radius: {max(0, radius - 1)}px;
            }}
            QWidget#appFrameBody QCheckBox {{ background: transparent; }}
            QLabel#appFrameTitle {{
                color: {C('text_primary')}; font-size: 13px; font-weight: 600;
                background: transparent;
            }}
            QPushButton#appFrameBtn, QPushButton#appFrameClose {{
                background: transparent; color: {C('text_secondary')};
                border: none; border-radius: 6px; padding: 0; min-width: 0;
                font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets"; font-size: 10px;
            }}
            QPushButton#appFrameBtn:hover {{ background: rgba(148,163,184,0.16); color: #ffffff; }}
            QPushButton#appFrameClose:hover {{ background: #e81123; color: #ffffff; }}
        """ + self.frame_style())
