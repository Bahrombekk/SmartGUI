"""
StatCard — statistika kartochkasi widget.
Icon + katta qiymat + nom matnidan iborat.
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from app.ui.theme import C


class StatCard(QFrame):
    """
    Statistika kartochkasi.

    Parametrlar:
        title  — nom (kichik matn)
        value  — qiymat (katta raqam)
        icon   — unicode belgi
        color  — qiymat rangi (None = accent)
    """

    def __init__(
        self,
        title: str,
        value: str = "0",
        icon:  str = "◆",
        color: str = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setFixedHeight(110)
        self.setMinimumWidth(130)

        self._accent = color or C("accent")
        self._setup_ui(title, value, icon)

    def _setup_ui(self, title, value, icon):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        # Yuqori qator: icon + qiymat
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setStyleSheet(
            f"color: {self._accent}; font-size: 22px; background: transparent;"
        )
        top_row.addWidget(self._icon_lbl)

        self._value_lbl = QLabel(value)
        font = QFont()
        font.setPointSize(26)
        font.setBold(True)
        self._value_lbl.setFont(font)
        self._value_lbl.setStyleSheet(
            f"color: {self._accent}; background: transparent;"
        )
        self._value_lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        top_row.addWidget(self._value_lbl, 1)

        layout.addLayout(top_row)

        # Nom
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 11px; background: transparent;"
        )
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._title_lbl)

        self.setStyleSheet(f"""
            StatCard {{
                background-color: {C('bg_card')};
                border: 1px solid {C('border')};
                border-radius: 10px;
            }}
            StatCard:hover {{
                border-color: {self._accent};
            }}
        """)

    def set_value(self, value: str):
        """Qiymatni yangilash."""
        self._value_lbl.setText(str(value))

    def set_title(self, title: str):
        self._title_lbl.setText(title)

    def set_icon(self, icon: str):
        self._icon_lbl.setText(icon)

    def set_color(self, color: str):
        """Rang yangilash."""
        self._accent = color
        self._value_lbl.setStyleSheet(
            f"color: {color}; background: transparent;"
        )
        self._icon_lbl.setStyleSheet(
            f"color: {color}; font-size: 22px; background: transparent;"
        )
        self.setStyleSheet(f"""
            StatCard {{
                background-color: {C('bg_card')};
                border: 1px solid {C('border')};
                border-radius: 10px;
            }}
            StatCard:hover {{
                border-color: {color};
            }}
        """)
