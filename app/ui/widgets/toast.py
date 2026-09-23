"""
Toast — oyna ustida qisqa muddat ko'rinadigan xabar (saqlandi / xato / info).

    from app.ui.widgets.toast import show_toast
    show_toast(self, "Kamera qo'shildi", "success")

Asosiy oynaning pastki o'ng burchagida chiqadi (sahifa tugmalarini yopmaydi),
bir nechta toast ustma-ust taxlanadi va o'zi yo'qoladi. Xato toast'lari uzoqroq turadi.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from app.ui.styles import C

_KINDS = {
    # kind: (belgi, rang tokeni)
    "success": ("✓", "success"),
    "error": ("!", "danger"),
    "warning": ("!", "warning"),
    "info": ("i", "info"),
}
_BOTTOM_OFFSET = 44   # status satridan yuqorida
_RIGHT_OFFSET = 20
_GAP = 8
_MSG_WIDTH = 360


class _Toast(QFrame):
    def __init__(self, host: QWidget, text: str, kind: str, duration_ms: int):
        super().__init__(host)
        glyph, token = _KINDS.get(kind, _KINDS["info"])
        color = C(token)
        self.setObjectName("appToast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet(f"""
            QFrame#appToast {{
                background: {C('bg_card')};
                border: 1px solid {C('border_strong')};
                border-left: 4px solid {color};
                border-radius: 10px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 16, 10)
        lay.setSpacing(10)
        icon = QLabel(glyph)
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {color}; color: #ffffff; border-radius: 11px;"
            " font-size: 12px; font-weight: 800;"
        )
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {C('text_primary')}; font-size: 13px;")
        # Qat'iy kenglik: word-wrap balandligi to'g'ri hisoblansin (oxirgi qator kesilmasin)
        msg.setFixedWidth(_MSG_WIDTH)
        msg.setMinimumHeight(msg.heightForWidth(_MSG_WIDTH))
        lay.addWidget(msg, 1)
        self.adjustSize()

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        QTimer.singleShot(duration_ms, self.dismiss)

    def appear(self):
        self.show()
        self.raise_()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def dismiss(self):
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._remove)
        self._anim.start()

    def mousePressEvent(self, event):
        self.dismiss()

    def _remove(self):
        host = self.parentWidget()
        self.deleteLater()
        if host is not None:
            QTimer.singleShot(0, lambda: _relayout(host))


def _alive_toasts(host: QWidget) -> list[_Toast]:
    return [t for t in host.findChildren(_Toast, options=Qt.FindChildOption.FindDirectChildrenOnly)
            if t.isVisible()]


def _relayout(host: QWidget):
    # Pastdan yuqoriga: eng yangisi eng pastda
    y = host.height() - _BOTTOM_OFFSET
    for t in reversed(_alive_toasts(host)):
        y -= t.height()
        t.move(host.width() - t.width() - _RIGHT_OFFSET, y)
        y -= _GAP


def show_toast(widget: QWidget | None, text: str, kind: str = "success",
               duration_ms: int | None = None) -> None:
    """`widget` qaysi oynada bo'lsa, o'sha oynaning burchagida xabar chiqaradi."""
    if widget is None:
        return
    host = widget.window()
    if duration_ms is None:
        duration_ms = 6000 if kind == "error" else 3000
    toast = _Toast(host, text, kind, duration_ms)
    toast.appear()
    _relayout(host)


def persist_config(widget: QWidget, cfg, success_msg: str) -> bool:
    """cfg.save() + natija toast'i. Xato bo'lsa sababi bilan qizil toast."""
    if cfg.save():
        show_toast(widget, success_msg, "success")
        return True
    reason = getattr(cfg, "last_save_error", "") or "noma'lum xato"
    show_toast(widget, f"Saqlanmadi: {reason}", "error")
    return False
