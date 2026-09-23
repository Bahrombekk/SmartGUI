"""
AppMessageBox — ilova dizaynidagi xabar/tasdiq dialogi (QMessageBox o'rniga).

FramedDialog asosida (ilova sarlavha qatori); tema tokenlaridan rang oladi.
API QMessageBox static metodlariga mos — qaytadigan qiymat
QMessageBox.StandardButton, shuning uchun chaqiruvchi kod o'zgarmaydi:

    reply = AppMessageBox.question(self, "Sarlavha", "Matn",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QFont
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from app.ui.styles import C
from app.ui.widgets.frameless import FramedDialog

SB = QMessageBox.StandardButton

_BUTTON_TEXT = {
    SB.Yes: "Ha",
    SB.No: "Yo'q",
    SB.Ok: "OK",
    SB.Cancel: "Bekor qilish",
    SB.Close: "Yopish",
    SB.Save: "Saqlash",
    SB.Discard: "Saqlamaslik",
    SB.Retry: "Qayta urinish",
}
# Chapdan o'ngga tartib; "tasdiqlovchi" tugma eng o'ngda turadi
_BUTTON_ORDER = [SB.Cancel, SB.No, SB.Discard, SB.Close, SB.Retry, SB.Save, SB.Ok, SB.Yes]
_REJECT_BUTTONS = (SB.No, SB.Cancel, SB.Close)

_KIND_COLOR = {
    "question": "info",
    "information": "info",
    "warning": "warning",
    "critical": "danger",
}


def _kind_icon(kind: str, size: int = 40) -> QPixmap:
    """Doira ichida belgi: ?, i, !, ×."""
    color = QColor(C(_KIND_COLOR.get(kind, "info")))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QColor(color)
    bg.setAlpha(38)
    p.setPen(QPen(color, 1.6))
    p.setBrush(bg)
    p.drawEllipse(QRectF(1.5, 1.5, size - 3, size - 3))
    p.setPen(color)
    if kind == "critical":
        pen = QPen(color, 2.6, cap=Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = size * 0.34
        p.drawLine(QPoint(int(m), int(m)), QPoint(int(size - m), int(size - m)))
        p.drawLine(QPoint(int(size - m), int(m)), QPoint(int(m), int(size - m)))
    else:
        glyph = {"question": "?", "warning": "!", "information": "i"}.get(kind, "i")
        f = QFont("Segoe UI", int(size * 0.42))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return pix


class AppMessageBox(FramedDialog):
    def __init__(self, parent, kind: str, title: str, text: str,
                 buttons=SB.Ok, default_button=SB.NoButton):
        super().__init__(parent)
        self._result = SB.NoButton
        self._kind = kind
        self.setWindowTitle(title)
        self.setModal(True)

        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Matn ─────────────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(22, 20, 24, 8)
        body.setSpacing(16)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_kind_icon(kind))
        icon_lbl.setFixedSize(40, 40)
        body.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
        text_lbl = QLabel(text, objectName="appDialogText")
        text_lbl.setWordWrap(True)
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_lbl.setMinimumWidth(300)
        text_lbl.setMaximumWidth(460)
        body.addWidget(text_lbl, 1)
        lay.addLayout(body)

        # ── Tugmalar ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(22, 14, 18, 18)
        btn_row.setSpacing(10)
        btn_row.addStretch(1)
        chosen = [b for b in _BUTTON_ORDER if buttons & b] or [SB.Ok]
        if default_button == SB.NoButton:
            default_button = chosen[-1]
        self._escape_button = next((b for b in chosen if b in _REJECT_BUTTONS), chosen[0])
        for sb in chosen:
            btn = QPushButton(_BUTTON_TEXT.get(sb, "OK"))
            btn.setMinimumSize(96, 34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            primary = sb not in _REJECT_BUTTONS and sb != SB.Discard
            btn.setObjectName("appDialogPrimary" if primary else "appDialogSecondary")
            if kind == "critical" and primary and sb in (SB.Yes, SB.Ok):
                btn.setObjectName("appDialogDanger" if len(chosen) > 1 else "appDialogPrimary")
            btn.clicked.connect(lambda _=False, s=sb: self._finish(s))
            if sb == default_button:
                btn.setDefault(True)
                btn.setAutoDefault(True)
                btn.setFocus()
            else:
                btn.setAutoDefault(False)
            btn_row.addWidget(btn)
        lay.addLayout(btn_row)

        self._apply_frame_style()

    def frame_style(self) -> str:
        accent = C("accent")
        return f"""
            QLabel#appDialogText {{
                color: {C('text_primary')}; font-size: 14px; background: transparent;
            }}
            QPushButton#appDialogPrimary {{
                background: {accent}; color: {C('text_on_accent')};
                border: 1px solid {accent}; border-radius: 8px;
                font-size: 13px; font-weight: 600; padding: 0 18px;
            }}
            QPushButton#appDialogPrimary:hover {{ background: {C('accent_hover')}; }}
            QPushButton#appDialogDanger {{
                background: {C('danger')}; color: #ffffff;
                border: 1px solid {C('danger')}; border-radius: 8px;
                font-size: 13px; font-weight: 600; padding: 0 18px;
            }}
            QPushButton#appDialogSecondary {{
                background: transparent; color: {C('text_secondary')};
                border: 1px solid {C('border_strong')}; border-radius: 8px;
                font-size: 13px; padding: 0 18px;
            }}
            QPushButton#appDialogSecondary:hover {{
                background: {C('bg_hover')}; color: {C('text_primary')};
            }}
            QPushButton:focus {{ outline: none; }}
        """

    def _finish(self, sb):
        self._result = sb
        self.accept()

    def reject(self):
        # Esc / ✕ — rad etuvchi tugma natijasi
        if self._result == SB.NoButton:
            self._result = self._escape_button
        super().reject()

    def exec_result(self):
        self.adjustSize()
        self.exec()
        return self._result

    # ── QMessageBox bilan mos static API ─────────────────────────────────

    @classmethod
    def question(cls, parent, title, text, buttons=SB.Yes | SB.No, default_button=SB.NoButton):
        return cls(parent, "question", title, text, buttons, default_button).exec_result()

    @classmethod
    def information(cls, parent, title, text, buttons=SB.Ok, default_button=SB.NoButton):
        return cls(parent, "information", title, text, buttons, default_button).exec_result()

    @classmethod
    def warning(cls, parent, title, text, buttons=SB.Ok, default_button=SB.NoButton):
        return cls(parent, "warning", title, text, buttons, default_button).exec_result()

    @classmethod
    def critical(cls, parent, title, text, buttons=SB.Ok, default_button=SB.NoButton):
        return cls(parent, "critical", title, text, buttons, default_button).exec_result()


class AppInputDialog(FramedDialog):
    """QInputDialog.getText o'rniga — ilova dizaynidagi bitta maydonli kiritish oynasi."""

    def __init__(self, parent, title: str, label: str, text: str = "", placeholder: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        lbl = QLabel(label, objectName="appDialogText")
        lay.addWidget(lbl)
        self._edit = QLineEdit(text)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumWidth(340)
        self._edit.setFixedHeight(36)
        self._edit.returnPressed.connect(self._accept_if_valid)
        lay.addWidget(self._edit)
        self._error = QLabel("", objectName="appInputError")
        self._error.hide()
        lay.addWidget(self._error)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        cancel = QPushButton("Bekor qilish", objectName="appDialogSecondary")
        cancel.setMinimumSize(96, 34)
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK", objectName="appDialogPrimary")
        ok.setMinimumSize(96, 34)
        ok.setDefault(True)
        ok.clicked.connect(self._accept_if_valid)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self._apply_frame_style()
        self._edit.setFocus()

    def frame_style(self) -> str:
        return AppMessageBox.frame_style(self) + f"""
            QLineEdit {{
                background: {C('input_bg')}; color: {C('text_primary')};
                border: 1px solid {C('input_border')}; border-radius: 8px; padding: 0 10px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {C('accent')}; }}
            QLabel#appInputError {{ color: {C('danger')}; font-size: 12px; background: transparent; }}
        """

    def _accept_if_valid(self):
        if not self._edit.text().strip():
            self._error.setText("Maydon bo'sh bo'lmasligi kerak")
            self._error.show()
            return
        self.accept()

    @classmethod
    def get_text(cls, parent, title: str, label: str, text: str = "",
                 placeholder: str = "") -> tuple[str, bool]:
        dlg = cls(parent, title, label, text, placeholder)
        dlg.adjustSize()
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return (dlg._edit.text().strip() if ok else "", ok)
