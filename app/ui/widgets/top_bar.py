"""
TopNavBar — Figma "Top bar" (h52) aniq nusxasi.

Chap guruh Figma koordinatalarida (x22 logo, x52 "SafeZone", x131 ajratgich,
x141 "Zavod №1", x217 dan tablar), o'ng guruh o'ng chetga bog'langan
(qidiruv W-616, AI holati W-437, soat W-306, qo'ng'iroq W-223, avatar W-187,
oyna tugmalari 46px). Oyna 1440 dan tor bo'lsa — "Zavod №1" yashiriladi va
qidiruv qisqaradi.

MainWindow bilan API eski TopNavBar bilan bir xil.
"""
from __future__ import annotations

import math
import time
import sys

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QPalette, QShortcut, QKeySequence
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QLineEdit, QLabel, QFrame

from app.ui import fz

TAB_W = {0: 88, 3: 106, 1: 83, 2: 73, 5: 73, 6: 90}
TAB_ORDER = [(0, "Monitoring"), (3, "Hodisalar"), (1, "Kameralar"),
             (2, "Analitika"), (5, "Xodimlar"), (6, "Sozlamalar")]


class _NavTab(QWidget):
    def __init__(self, page_id: int, text: str, on_click, parent=None):
        super().__init__(parent)
        self.page_id = page_id
        self._on_click = on_click
        self._active = False
        self._hover = False
        self.setFixedSize(TAB_W[page_id], 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl = QLabel(text, self)
        self._lbl.setGeometry(10, 6, TAB_W[page_id] - 10, 16)
        self._badge = None
        if page_id == 3:
            self._badge = QLabel("", self)
            self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._badge.setStyleSheet(
                f"background:{fz.RED_FILL}; color:{fz.TEXT}; border:none; border-radius:4px; {fz.css_font(10.5, 700)}"
            )
            self._badge.setGeometry(76, 6, 20, 16)
            self._badge.hide()
        self._restyle()

    def set_active(self, v: bool):
        if v != self._active:
            self._active = v
            self._restyle()
            self.update()

    def set_badge(self, n: int):
        if self._badge is None:
            return
        if n <= 0:
            self._badge.hide()
            self.setFixedWidth(int(math.ceil(10 + fz.text_w(self._lbl.text(), 13, 500) + 10)))
            return
        txt = str(min(n, 99))
        w = 20 if len(txt) == 1 else 26
        self._badge.setText(txt)
        self._badge.setGeometry(76, 6, w, 16)
        self.setFixedWidth(max(TAB_W[3], 76 + w + 10))
        self._badge.show()

    def _restyle(self):
        if self._active:
            fz.restyle(self._lbl, 13, 600, fz.TEXT)
        else:
            fz.restyle(self._lbl, 13, 500, fz.TEXT if self._hover else fz.TEXT2)

    def enterEvent(self, e):
        self._hover = True
        self._restyle()
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._restyle()
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.page_id)
            e.accept()

    def paintEvent(self, _):
        if not (self._active or self._hover):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fz.ACTIVE) if self._active else QColor(21, 34, 59, 110))
        p.drawRoundedRect(QRectF(self.rect()), 6, 6)
        p.end()


class _Search(QFrame):
    def __init__(self, on_text, parent=None):
        super().__init__(parent)
        self.setObjectName("fzSearch")
        self.setStyleSheet(
            f"QFrame#fzSearch {{ background:{fz.CARD}; border:1px solid {fz.BORDER}; border-radius:8px; }}"
        )
        self.setFixedHeight(30)
        self._icon = fz.Icon("search", 14, parent=self)
        self._icon.move(11, 7)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Qidirish")
        self.edit.setFrame(False)
        self.edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.edit.setStyleSheet(
            f"QLineEdit {{ background:transparent; border:none; color:{fz.TEXT}; padding:0;"
            f" selection-background-color:{fz.ACCENT}; selection-color:{fz.ON_ACCENT}; {fz.css_font(13, 400)} }}"
        )
        pal = self.edit.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(fz.MUTED))
        self.edit.setPalette(pal)
        self.edit.textChanged.connect(on_text)
        self.edit.textChanged.connect(lambda _: self._place())
        self._kbd = QLabel("Ctrl K", self)
        self._kbd.setStyleSheet(
            f"QLabel {{ background:transparent; color:{fz.MUTED}; border:1px solid {fz.BORDER};"
            f" border-radius:4px; padding-left:6px; padding-top:1px; {fz.css_font(10.5, 400, mono=True)} }}"
        )
        self._kbd.setFixedSize(54, 18)
        self._show_kbd = True

    def set_kbd_visible(self, v: bool):
        self._show_kbd = v
        self._place()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        w = self.width()
        kbd = self._show_kbd and not self.edit.text()
        self._kbd.setVisible(kbd)
        self._kbd.move(w - 64, 5)
        right = (w - 68) if kbd else (w - 10)
        self.edit.setGeometry(33, 0, max(20, right - 33), 27)

    def mousePressEvent(self, e):
        self.edit.setFocus()


class _Avatar(QWidget):
    def __init__(self, initials: str = "", parent=None):
        super().__init__(parent)
        self._t = initials
        self.setFixedSize(28, 28)

    def set_initials(self, t: str):
        self._t = (t or "")[:2].upper()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#1B5A86"), 1))
        p.setBrush(QColor("#0B2C4A"))
        p.drawEllipse(QPointF(14, 14), 13.5, 13.5)
        if self._t:
            p.setFont(fz.qfont(11, 700))
            p.setPen(QColor(fz.ACCENT))
            p.drawText(QRectF(0, 0, 28, 28), Qt.AlignmentFlag.AlignCenter, self._t)
        else:
            # Bosh harflar kiritilmagan — umumiy foydalanuvchi ikonkasi
            p.drawPixmap(7, 7, fz.svg_pixmap("users_cyan", 14, 14))
        p.end()


class _WinBtn(QPushButton):
    def __init__(self, icon: str, tooltip: str, close: bool = False, parent=None):
        super().__init__(parent)
        self._icon_name = icon
        self._close = close
        self.setFixedSize(46, 51)
        self.setToolTip(tooltip)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIconSize(self.size().__class__(14, 14))
        self.set_icon(icon)
        hover = "#e81123" if close else "rgba(255,255,255,0.06)"
        self.setStyleSheet(
            "QPushButton { background:transparent; border:none; border-radius:0; }"
            f"QPushButton:hover {{ background:{hover}; }}"
            f"QPushButton:pressed {{ background:{'#f1707a' if close else 'rgba(255,255,255,0.10)'}; }}"
        )

    def set_icon(self, name: str):
        self._icon_name = name
        self.setIcon(fz.svg_icon(name, 14))

    def enterEvent(self, e):
        if self._close:
            self.setIcon(fz.svg_icon(self._icon_name, 14, "#ffffff"))
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._close:
            self.setIcon(fz.svg_icon(self._icon_name, 14))
        super().leaveEvent(e)


class TopNavBar(QWidget):
    """Figma top bar."""

    PAGE_DASHBOARD = 0
    PAGE_REPORTS = 3
    PAGE_ANALYTICS = 2
    PAGE_USERS = 5
    PAGE_SETTINGS = 6

    def __init__(self, on_page_change, on_settings, on_quit, on_search=None,
                 on_notifications=None, parent=None):
        super().__init__(parent)
        fz.init_fonts()
        self._on_page_change = on_page_change
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._on_search = on_search
        self._on_notifications = on_notifications
        self._notif_count = 0
        self._ai_active = True
        self._ai_enabled = True
        self._ai_fps: float | None = None
        self._restore_maximized_after_fullscreen = True
        self._restored_once = False
        self.setFixedHeight(52)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"TopNavBar {{ background:{fz.BG}; }}")

        # ── Chap guruh ──
        self._logo = fz.Icon("logo", 17, parent=self)
        self._brand = fz.label("SafeZone", 15, 700, fz.TEXT, parent=self)
        self._brand.setFixedHeight(18)
        self._sep = fz.vline(fz.BORDER, 1, 20)
        self._sep.setParent(self)
        self._site = fz.label("", 12.5, 400, fz.MUTED, parent=self)
        self._site.setFixedHeight(15)

        self._tabs: dict[int, _NavTab] = {}
        for pid, text in TAB_ORDER:
            t = _NavTab(pid, text, self._nav_click, self)
            self._tabs[pid] = t
        self._nav_btns = self._tabs   # moslik
        self._tabs[3].set_badge(0)

        # ── O'ng guruh ──
        self._search_box = _Search(self._on_search_changed, self)
        self._search = self._search_box.edit
        self._ai_pill = fz.Pill("AI faol", fz.GREEN_BG, fz.GREEN, px=12, weight=500, mono=False,
                                h=26, pad=9, radius=7, border=fz.GREEN_BORDER, dot=fz.GREEN,
                                dot_size=6, gap=6, parent=self)
        self._clock = fz.label("00:00:00", 14, 700, fz.TEXT, mono=True, parent=self)
        self._clock.setFixedHeight(17)
        self._bell = QPushButton(self)
        self._bell.setFixedSize(18, 18)
        self._bell.setIcon(fz.svg_icon("bell", 18))
        self._bell.setIconSize(self._bell.size())
        self._bell.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bell.setToolTip("Hodisalar")
        self._bell.setStyleSheet("QPushButton { background:transparent; border:none; }")
        self._bell.clicked.connect(self._open_notifications)
        self._bell_btn = self._bell
        self._notif_dot = fz.Dot(fz.RED, 6, parent=self)
        self._notif_dot.hide()
        self._avatar = _Avatar("", self)

        self._min_btn = _WinBtn("win_min", "Kichraytirish", parent=self)
        self._min_btn.clicked.connect(lambda: self.window().showMinimized())
        self._max_btn = _WinBtn("win_max", "Kattalashtirish", parent=self)
        self._max_btn.clicked.connect(self._toggle_maximize)
        self._quit_btn = _WinBtn("win_close", "Yopish", close=True, parent=self)
        self._quit_btn.clicked.connect(self._on_quit)

        # Figma'da yo'q, lekin MainWindow ulanadigan yashirin tugmalar
        self._pause_btn = QPushButton("|| Pauza", self)
        self._restart_btn = QPushButton("Qayta", self)
        self._ss_btn = QPushButton("Skrinshot", self)
        for b in (self._pause_btn, self._restart_btn, self._ss_btn):
            b.hide()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start(1000)
        self._tick()
        self._update_ai_text()
        self._set_active(self.PAGE_DASHBOARD)

    # ── Joylashuv ────────────────────────────────────────────────────────
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        W = self.width()
        tabs_total = sum(t.width() for t in self._tabs.values()) + 4 * (len(self._tabs) - 1)
        right_start = W - 616
        # siqish: avval "Zavod" yashiriladi, so'ng qidiruv qisqaradi
        has_site = bool(self._site.text())
        compact = (not has_site) or right_start - (217 + tabs_total) < 24
        self._sep.setVisible(not compact)
        self._site.setVisible(not compact)
        tab_x = 147 if compact else 217
        left_end = tab_x + tabs_total
        search_w = 167
        if right_start - left_end < 24:
            search_w = max(110, 167 - (left_end + 24 - right_start))
        self._search_box.set_kbd_visible(search_w >= 150)

        self._logo.move(22, 17)
        self._brand.setGeometry(52, 16, 78, 18)
        self._sep.setGeometry(131, 15, 1, 20)
        self._site.setGeometry(141, 18, 70, 15)
        x = tab_x
        for pid, _ in TAB_ORDER:
            t = self._tabs[pid]
            t.move(x, 12)
            x += t.width() + 4

        sx = W - 616 + (167 - search_w)
        self._search_box.setGeometry(sx, 11, search_w, 30)
        self._ai_pill.adjustSize()
        self._ai_pill.move(W - 437, 13)
        self._clock.setGeometry(W - 306, 17, 80, 17)
        self._bell.move(W - 223, 16)
        self._notif_dot.move(W - 211, 13)
        self._avatar.move(W - 187, 12)
        self._min_btn.move(W - 138, 0)
        self._max_btn.move(W - 92, 0)
        self._quit_btn.move(W - 46, 0)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(fz.BG))
        p.fillRect(0, self.height() - 1, self.width(), 1, QColor(fz.BORDER))
        p.end()

    # ── Holatlar ─────────────────────────────────────────────────────────
    def _tick(self):
        self._clock.setText(time.strftime("%H:%M:%S"))

    def _update_ai_text(self):
        if not self._ai_enabled:
            txt = "AI o‘chiq"
            self._ai_pill.set_colors(fz.ACTIVE, fz.MUTED, fz.SEG_BORDER, fz.MUTED, px=12, mono=False)
        elif self._ai_active:
            txt = "AI faol" if self._ai_fps is None else f"AI faol · {self._ai_fps:.1f} fps"
            self._ai_pill.set_colors(fz.GREEN_BG, fz.GREEN, fz.GREEN_BORDER, fz.GREEN, px=12, mono=False)
        else:
            txt = "AI pauza"
            self._ai_pill.set_colors(fz.ACTIVE, fz.MUTED, fz.SEG_BORDER, fz.MUTED, px=12, mono=False)
        self._ai_pill.set_text(txt)
        self._ai_pill.adjustSize()

    def set_ai_active(self, active: bool):
        self._ai_active = bool(active)
        self._update_ai_text()

    def set_ai_enabled(self, enabled: bool):
        """AI model sozlamalarda o'chirilgan bo'lsa "AI faol" ko'rsatilmaydi."""
        self._ai_enabled = bool(enabled)
        self._update_ai_text()
        self._relayout()

    def set_ai_fps(self, fps: float | None):
        fps = None if fps is None else round(float(fps), 1)
        if fps != self._ai_fps:
            self._ai_fps = fps
            self._update_ai_text()

    def set_site_name(self, name: str):
        self._site.setText(name or "")
        self._site.adjustSize()
        self._relayout()

    def set_initials(self, initials: str):
        self._avatar.set_initials(initials)

    def focus_search(self):
        self._search.setFocus()
        self._search.selectAll()

    # ── Navigatsiya ──────────────────────────────────────────────────────
    def _nav_click(self, page_id: int):
        real_page = {0: 0, 1: 1, 2: 3, 3: 2, 5: 4, 6: 5}.get(page_id, 0)
        self._set_active(page_id)
        if page_id == self.PAGE_SETTINGS:
            self._on_settings()
        else:
            self._on_page_change(real_page, page_id)

    def _set_active(self, page_id: int):
        for pid, t in self._tabs.items():
            t.set_active(pid == page_id)

    def set_active_page(self, page_id: int):
        self._set_active(page_id)

    def _on_search_changed(self, text: str):
        if self._on_search:
            self._on_search(text)

    def _open_notifications(self):
        self._violation_count_seen()
        if self._on_notifications:
            self._on_notifications()
        else:
            self._nav_click(self.PAGE_REPORTS)

    def _violation_count_seen(self):
        self.set_notif_count(0)

    def set_notif_count(self, count: int):
        self._notif_count = max(0, int(count or 0))
        self._tabs[3].set_badge(self._notif_count)
        self._notif_dot.setVisible(self._notif_count > 0)
        self._relayout()

    def update_cam_badge(self, active: int, total: int):
        self._cam_counts = (active, total)

    def set_pause_enabled(self, enabled: bool):
        self._pause_btn.setEnabled(enabled)

    # ── Mavzu (Figma'da navbarda tugma yo'q — sozlamalardan boshqariladi) ──
    def apply_theme(self, theme: str):
        from PyQt6.QtWidgets import QApplication
        from app.ui.styles import set_theme, build_main_stylesheet
        set_theme("dark")          # Figma dizayni faqat qorong'i mavzuda
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_main_stylesheet())
        self.update()

    # ── Oyna ─────────────────────────────────────────────────────────────
    @staticmethod
    def _native_zoomed(w) -> bool | None:
        """Windows'dagi haqiqiy holat (Qt holati ramkasiz oynada kechikadi)."""
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            return bool(ctypes.windll.user32.IsZoomed(int(w.winId())))
        except Exception:
            return None

    @staticmethod
    def _native_show(w, cmd: int) -> bool:
        """ShowWindow — SW_MAXIMIZE=3, SW_RESTORE=9. Qt'ning showNormal() ramkasiz
        oynada Windows oynasini "zoomed" holatda qoldiradi, shuning uchun
        Windows'da to'g'ridan-to'g'ri API ishlatiladi."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(int(w.winId()), cmd)
            return True
        except Exception:
            return False

    def _is_maximized(self, w) -> bool:
        z = self._native_zoomed(w)
        return w.isMaximized() if z is None else z

    def _maximize(self, w):
        if not self._native_show(w, 3):
            w.showMaximized()

    def _restore(self, w):
        # Oyna doim kattalashtirilgan holda ochiladi — "oddiy" o'lchami hech qachon
        # foydalanuvchi tomonidan berilmagan (minimal yoki butun ekran). Birinchi
        # tiklashda ekranning ~3/4 qismi markazda beriladi; keyin — oxirgi o'lcham.
        screen = w.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        normal = w.normalGeometry()
        first = not self._restored_once
        self._restored_once = True
        if not self._native_show(w, 9):
            w.showNormal()
        if avail is not None and (first or not normal.isValid() or normal.width() >= avail.width() - 16
                                  or normal.height() >= avail.height() - 16):
            ww = min(max(w.minimumWidth(), int(avail.width() * 0.72)), avail.width())
            hh = min(max(w.minimumHeight(), int(avail.height() * 0.8)), avail.height())
            QTimer.singleShot(60, lambda: w.setGeometry(avail.x() + (avail.width() - ww) // 2,
                                                        avail.y() + (avail.height() - hh) // 2, ww, hh))

    def _toggle_maximize(self):
        w = self.window()
        if w.isFullScreen():
            return
        if self._is_maximized(w):
            self._restore(w)
        else:
            self._maximize(w)

    def update_window_state(self, maximized: bool):
        self._max_btn.set_icon("win_restore" if maximized else "win_max")
        self._max_btn.setToolTip("Tiklash" if maximized else "Kattalashtirish")

    def _toggle_fullscreen(self):
        w = self.window()
        if not w:
            return
        if w.isFullScreen():
            w.showNormal()
            if self._restore_maximized_after_fullscreen:
                QTimer.singleShot(0, lambda: self._maximize(w))
        else:
            self._restore_maximized_after_fullscreen = self._is_maximized(w)
            w.showFullScreen()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.window().isFullScreen():
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
