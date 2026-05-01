from __future__ import annotations

import datetime

from PyQt6.QtCore import QDateTime, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.theme import C


class TimelineWidget(QWidget):
    """Vaqt chizig'i — sana + vaqt ko'rsatgich + kichik thumbnail qatorlar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(96)
        self.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);"
            "border: 1px solid #1e293b;"
            "border-radius: 10px;"
        )
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_time)
        self._timer.start(1000)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 6)
        root.setSpacing(4)

        # Yuqori qator: sana + vaqt chizig'i
        top = QHBoxLayout()

        date_str = QDateTime.currentDateTime().toString("dd.MM.yyyy")
        self._date_lbl = QLabel(f"→  {date_str}  ■")
        self._date_lbl.setStyleSheet(
            f"color: {C('text_secondary')}; font-size: 11px; background: transparent;"
        )
        top.addWidget(self._date_lbl)
        top.addStretch()

        self._time_lbl = QLabel(datetime.datetime.now().strftime("%H:%M:%S"))
        self._time_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 12px; font-weight: bold;"
            " background: transparent;"
        )
        top.addWidget(self._time_lbl)
        root.addLayout(top)

        # Vaqt chizig'i
        tl_row = QHBoxLayout()
        tl_row.setSpacing(0)

        prev_btn = QLabel("◀")
        prev_btn.setFixedWidth(20)
        prev_btn.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        tl_row.addWidget(prev_btn)

        self._timeline_bar = _TimelineBar()
        tl_row.addWidget(self._timeline_bar, 1)

        next_btn = QLabel("▶")
        next_btn.setFixedWidth(20)
        next_btn.setAlignment(Qt.AlignmentFlag.AlignRight)
        next_btn.setStyleSheet(
            f"color: {C('text_muted')}; font-size: 10px; background: transparent;"
        )
        tl_row.addWidget(next_btn)
        root.addLayout(tl_row)

    def _update_time(self):
        now = datetime.datetime.now()
        self._time_lbl.setText(now.strftime("%H:%M:%S"))
        self._date_lbl.setText(f"→  {now.strftime('%d.%m.%Y')}  ■")
        self._timeline_bar.update()


class _TimelineBar(QWidget):
    """Vaqt chizig'i chizuvchi widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        now = datetime.datetime.now()
        current_min = now.hour * 60 + now.minute

        # 3 soatlik oyna: hozirgi vaqtdan 1.5 soat oldin va keyin
        window_min = 90
        start_min = current_min - window_min
        total_span = window_min * 2

        # Placeholder thumbnail qutilari
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(C('bg_panel'))))
        thumb_w = 38
        thumb_h = 28
        cols = w // (thumb_w + 4)
        for i in range(int(cols)):
            x = i * (thumb_w + 4)
            p.drawRoundedRect(x, 2, thumb_w, thumb_h, 3, 3)

        # Vaqt belgilari
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        p.setPen(QPen(QColor(C('text_muted'))))

        # Har 15 daqiqada belgi
        for delta in range(-90, 91, 15):
            t = start_min + window_min + delta
            x = int((delta + window_min) / total_span * w)
            hh = (t // 60) % 24
            mm = t % 60
            label = f"{hh:02d}:{mm:02d}"
            p.drawText(x - 16, h - 2, label)
            p.setPen(QPen(QColor(C('border'))))
            p.drawLine(x, 32, x, 38)
            p.setPen(QPen(QColor(C('text_muted'))))

        # Joriy vaqt ko'rsatgich (to'q sariq chiziq)
        cx = w // 2
        p.setPen(QPen(QColor(C('accent')), 2))
        p.drawLine(cx, 0, cx, 34)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
