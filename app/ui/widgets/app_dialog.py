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

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from app.ui import fz
from app.ui.widgets.frameless import FramedDialog, dialog_button, dialog_footer

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

# (ikon foni, belgi rangi, belgi) — Figma tokenlari
_KIND_STYLE = {
    "question":    (fz.BLUE_BG, fz.ACCENT, "?"),
    "information": (fz.BLUE_BG, fz.ACCENT, "i"),
    "warning":     ("#2e2410", "#f3b348", "!"),
    "critical":    (fz.RED_BG, fz.RED, "×"),
}


class _KindIcon(QWidget):
    """40x40 radius 10 rangli quti ichida belgi (KPI ikon qutilari uslubida)."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._bg, self._fg, self._glyph = _KIND_STYLE.get(kind, _KIND_STYLE["information"])
        self.setFixedSize(40, 40)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._bg))
        p.drawRoundedRect(QRectF(0, 0, 40, 40), 10, 10)
        p.setPen(QColor(self._fg))
        p.setFont(fz.qfont(20 if self._glyph == "×" else 18, 700))
        p.drawText(QRectF(0, 0, 40, 39), Qt.AlignmentFlag.AlignCenter, self._glyph)
        p.end()


_dialog_button = dialog_button
_footer = dialog_footer


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

        # ── Matn: birinchi qator — asosiy, qolgani — izoh ────────────────
        body = QHBoxLayout()
        body.setContentsMargins(20, 20, 24, 20)
        body.setSpacing(14)
        body.addWidget(_KindIcon(kind), 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setContentsMargins(0, 1, 0, 0)
        col.setSpacing(5)
        head, _, rest = str(text).strip().partition("\n")
        main_lbl = fz.label(head, 14, 600, fz.TEXT, wrap=True)
        main_lbl.setObjectName("appDialogText")
        main_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        main_lbl.setMinimumWidth(320)
        main_lbl.setMaximumWidth(480)
        col.addWidget(main_lbl)
        rest = rest.strip()
        if rest:
            sub = fz.label(rest, 13, 400, fz.TEXT2, wrap=True)
            sub.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            sub.setMinimumWidth(320)
            sub.setMaximumWidth(480)
            col.addWidget(sub)
        col.addStretch(1)
        body.addLayout(col, 1)
        lay.addLayout(body)

        # ── Tugmalar ─────────────────────────────────────────────────────
        footer, btn_row = _footer()
        chosen = [b for b in _BUTTON_ORDER if buttons & b] or [SB.Ok]
        if default_button == SB.NoButton:
            default_button = chosen[-1]
        self._escape_button = next((b for b in chosen if b in _REJECT_BUTTONS), chosen[0])
        for sb in chosen:
            primary = sb not in _REJECT_BUTTONS and sb != SB.Discard
            kind_btn = "primary" if primary else "ghost"
            if kind == "critical" and primary and sb in (SB.Yes, SB.Ok) and len(chosen) > 1:
                kind_btn = "danger"
            btn = _dialog_button(_BUTTON_TEXT.get(sb, "OK"), kind_btn)
            btn.clicked.connect(lambda _=False, s=sb: self._finish(s))
            if sb == default_button:
                btn.setDefault(True)
                btn.setAutoDefault(True)
                btn.setFocus()
            else:
                btn.setAutoDefault(False)
            btn_row.addWidget(btn)
        lay.addWidget(footer)

        self._apply_frame_style()

    def frame_style(self) -> str:
        return ""

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
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        lay = QVBoxLayout()
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(7)
        lbl = fz.label(label, 12.5, 500, fz.TEXT2)
        lay.addWidget(lbl)
        self._edit = fz.line_edit(placeholder, h=36, px=13.5)
        self._edit.setText(text)
        self._edit.setMinimumWidth(360)
        self._edit.returnPressed.connect(self._accept_if_valid)
        lay.addWidget(self._edit)
        self._error = fz.label("", 12, 400, fz.RED, wrap=True)
        self._error.hide()
        lay.addWidget(self._error)
        outer.addLayout(lay)
        footer, row = _footer()
        cancel = _dialog_button("Bekor qilish", "ghost")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        ok = _dialog_button("OK", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self._accept_if_valid)
        row.addWidget(cancel)
        row.addWidget(ok)
        outer.addWidget(footer)
        self._apply_frame_style()
        self._edit.setFocus()

    def frame_style(self) -> str:
        return AppMessageBox.frame_style(self)

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
