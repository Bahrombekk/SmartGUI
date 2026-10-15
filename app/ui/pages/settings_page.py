"""
Sozlamalar sahifasi — Figma "SafeZone — Sozlamalar" (16:227) aniq nusxasi.

Sarlavha (Inter SemiBold 19, y22) + o'ngda ogohlantirish pill / "Bekor qilish" /
"Saqlash"; tana y80 dan: chap menyu kartasi (240) | bo'lim kontenti.
"AI model" bo'limi Figma'dagi uchta karta: Detection modeli, Unumdorlik,
Buzilishni qayd etish. Qolgan bo'limlar xuddi shu komponentlardan quriladi.

MainWindow API: SettingsPage(cfg), _load_values(), open_add_camera(),
signallar settings_saved / cameras_changed / departments_changed /
wizard_requested (+ branding_changed).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QUrl
from PyQt6.QtGui import QColor, QPainter, QDesktopServices
from PyQt6.QtWidgets import (QWidget, QFrame, QHBoxLayout, QVBoxLayout, QStackedWidget,
                             QScrollArea, QLabel, QFileDialog, QMessageBox, QDialog,
                             QSizePolicy)

from app import __version__
from app.ui import fz
from app.ui.widgets.app_dialog import AppMessageBox, AppInputDialog
from app.ui.widgets.toast import show_toast
from app.config.settings_manager import MAX_CAMERAS, MODEL_PRESETS, model_preset_index
from app.shared.paths import resolve_model_path

_RESTART_KEYS = {
    "ai_model_enabled", "model_path", "confidence", "yolo_imgsz", "use_gpu",
    "half_precision", "process_every_n", "ai_fps_limit", "video_fps_limit",
    "inference_batch_size", "cameras_per_model", "violation_save_queue_size",
    "tracking_strictness", "helmet_status_window", "helmet_status_threshold",
    "faceid_enabled", "access_roster_enabled", "faceid_threshold",
    "save_violations", "violations_dir", "violation_cooldown",
    "telegram_enabled", "telegram_token", "telegram_chat_ids",
    "backend_enabled", "backend_url", "backend_login", "backend_password",
}

MENU = [
    ("model", "cpu", "AI model"),
    ("cameras", "box", "Kameralar"),
    ("telegram", "send", "Telegram"),
    ("backend", "server", "Backend API"),
    ("faceid", "users", "FaceID"),
    ("storage", "db", "Saqlash"),
    ("appearance", "moon", "Ko‘rinish"),
    ("about", "info", "Dastur haqida"),
]


# ════════════════════════════════════════════════════════════════════════════
#  Menyu elementi (206x35)
# ════════════════════════════════════════════════════════════════════════════

class _MenuItem(QWidget):
    def __init__(self, key: str, icon: str, text: str, on_click, parent=None):
        super().__init__(parent)
        self.key = key
        self._on_click = on_click
        self._active = False
        self._hover = False
        self.setFixedHeight(35)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon = fz.Icon(icon, 15, fz.TEXT2, parent=self)
        self._icon.move(13, 10)
        self._lbl = fz.label(text, 13, 500, fz.TEXT2, parent=self)
        self._lbl.setGeometry(38, 9, 140, fz.line_h(13))
        self._dot = fz.Dot(fz.GREEN, 6, parent=self)
        self._dot.hide()
        self._icon_name = icon

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._dot.move(self.width() - 19, 14)

    def set_active(self, v: bool):
        self._active = v
        self._restyle()

    def set_status(self, connected: bool):
        self._dot.setVisible(bool(connected))

    def _restyle(self):
        c = fz.TEXT if (self._active or self._hover) else fz.TEXT2
        fz.restyle(self._lbl, 13, 600 if self._active else 500, c)
        self._icon.set_color(c)
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self._restyle()

    def leaveEvent(self, e):
        self._hover = False
        self._restyle()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.key)

    def paintEvent(self, _):
        if not (self._active or self._hover):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fz.ACTIVE) if self._active else QColor(21, 34, 59, 110))
        p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        if self._active:
            p.setBrush(QColor(fz.ACCENT))
            p.drawRoundedRect(QRectF(0, 7, 2, 21), 1, 1)
        p.end()


# ════════════════════════════════════════════════════════════════════════════
#  Sarlavha (o'ng guruh mutlaq joylashuvda)
# ════════════════════════════════════════════════════════════════════════════

class _Header(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(43)
        self.title = fz.label("Sozlamalar", 19, 600, fz.TEXT, parent=self)
        self.title.setGeometry(0, 0, 400, 23)
        self.sub = fz.label("AI model, xabarnomalar, saqlash va tizim", 12.5, 400, fz.TEXT2, parent=self)
        self.sub.setGeometry(0, 27, 500, 15)
        self.pill = fz.Pill("Saqlangandan keyin qayta ishga tushirish kerak", fz.RAISED, fz.TEXT2,
                            px=12, weight=500, mono=False, h=24, pad=10, radius=12,
                            dot=fz.ACCENT, dot_size=5, gap=6, parent=self)
        self.cancel = fz.text_button("Bekor qilish", 13, fz.TEXT2, 500, h=31)
        self.cancel.setParent(self)
        self.save = fz.primary_button("Saqlash", h=31, px=13, pad=16, radius=8)
        self.save.setParent(self)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        W = self.width()
        self.save.adjustSize()
        sw = self.save.sizeHint().width()
        self.save.setGeometry(W - sw, 12, sw, 31)
        cw = int(fz.text_w("Bekor qilish", 13, 500)) + 8
        self.cancel.setGeometry(W - sw - 26 - cw + 4, 12, cw, 31)
        self.pill.adjustSize()
        self.pill.move(self.cancel.x() + 4 - 29 - self.pill.width(), 18)


# ════════════════════════════════════════════════════════════════════════════
#  SettingsPage
# ════════════════════════════════════════════════════════════════════════════

class SettingsPage(QWidget):
    settings_saved = pyqtSignal()
    cameras_changed = pyqtSignal()
    departments_changed = pyqtSignal()
    wizard_requested = pyqtSignal()
    branding_changed = pyqtSignal(str, str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        fz.init_fonts()
        self.cfg = config_manager
        self._loading = False
        self._dirty = False
        self._segs: dict[str, tuple] = {}
        self._test_threads: dict = {}
        self.setObjectName("fzSettingsPage")
        self.setStyleSheet(f"QWidget#fzSettingsPage {{ background:{fz.BG}; }}")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 22, 16, 16)
        root.setSpacing(0)
        self._header = _Header()
        self._header.save.clicked.connect(self._save)
        self._header.cancel.clicked.connect(self._cancel)
        root.addWidget(self._header)
        root.addSpacing(15)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_menu())
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent;")
        body.addWidget(self._stack, 1)
        root.addLayout(body, 1)

        self._pages: dict[str, int] = {}
        builders = {
            "model": self._page_model, "cameras": self._page_cameras,
            "telegram": self._page_telegram, "backend": self._page_backend,
            "faceid": self._page_faceid, "storage": self._page_storage,
            "appearance": self._page_appearance, "about": self._page_about,
        }
        for key, _, _ in MENU:
            self._pages[key] = self._stack.addWidget(self._scroll(builders[key]()))
        self._switch("model")
        self._set_dirty(False)

    # ── Yordamchilar ─────────────────────────────────────────────────────
    @staticmethod
    def _scroll(w: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setStyleSheet("QScrollArea { background:transparent; border:none; }"
                         "QScrollArea > QWidget > QWidget { background:transparent; }")
        sa.setWidget(w)
        return sa

    @staticmethod
    def _page() -> tuple[QWidget, QHBoxLayout]:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        return w, lay

    @staticmethod
    def _column(*cards, stretch_last: bool = True) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(12)
        for i, c in enumerate(cards):
            last = i == len(cards) - 1
            col.addWidget(c, 1 if (last and stretch_last) else 0)
        return col

    def _toggle(self) -> fz.Toggle:
        t = fz.Toggle(False)
        t.toggled.connect(lambda _: self._changed())
        return t

    def _seg(self, key: str, values: list, labels: list[str]) -> fz.Segmented:
        s = fz.Segmented(labels, -1)
        s._touched = False

        def on_change(_):
            s._touched = True
            self._changed()
        s.changed.connect(on_change)
        self._segs[key] = (s, values)
        return s

    def _slider(self, lo, hi, step, fmt, track_w=220, unit: bool = False):
        """Figma: son qiymat — trekdan 18px keyin, 30px o'ngga tekis;
        birlikli ("9 kadr") — 3px keyin, 65px chapga tekis."""
        s = fz.Slider(lo, hi, lo, step, track_w)
        v = fz.value_label(fmt(lo), 12.5)

        def upd(val):
            v.setText(fmt(val))
            self._changed()
        s.valueChanged.connect(upd)
        s._fmt, s._vlabel = fmt, v
        box = fz.SliderValue(s, v, 3 if unit else 18, 65 if unit else 30, right_align=not unit)
        return s, box

    @staticmethod
    def _set_slider(s: fz.Slider, val):
        s.set_value(val)
        s._vlabel.setText(s._fmt(s.value()))

    def _edit(self, placeholder="", width=280, mono=False, password=False):
        e = fz.line_edit(placeholder, mono=mono, password=password, width=width)
        e.textEdited.connect(lambda _: self._changed())
        return e

    def _changed(self):
        if not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, v: bool):
        self._dirty = v
        self._header.cancel.setEnabled(v)

    # ── Menyu ────────────────────────────────────────────────────────────
    def _build_menu(self) -> QFrame:
        menu = fz.card(fz.CARD, fz.BORDER, 12)
        menu.setFixedWidth(240)
        lay = QVBoxLayout(menu)
        lay.setContentsMargins(16, 14, 16, 17)
        lay.setSpacing(3)
        self._menu_items: dict[str, _MenuItem] = {}
        for key, icon, text in MENU:
            it = _MenuItem(key, icon, text, self._switch)
            self._menu_items[key] = it
            lay.addWidget(it)
        lay.addStretch(1)

        help_box = fz.card(fz.RAISED, fz.RAISED, 8, 0)
        help_box.setFixedHeight(111)
        hl = QVBoxLayout(help_box)
        hl.setContentsMargins(12, 13, 12, 12)
        hl.setSpacing(0)
        hl.addWidget(fz.label("Yordam kerakmi?", 12.5, 600, fz.TEXT))
        hl.addSpacing(33 - 13 - fz.line_h(12.5) - 1)
        desc = fz.label("Biz bilan bog‘laning — yordam beramiz.", 11.5, 400, fz.TEXT2, wrap=True)
        desc.setFixedWidth(175)
        hl.addWidget(desc)
        hl.addStretch(1)
        btn = fz.ghost_button("Bog‘lanish", h=26, px=12.5, pad=10, radius=6, icon="headphones",
                              icon_size=14, icon_color=fz.TEXT)
        btn.setStyleSheet(btn.styleSheet().replace("font-weight:600", "font-weight:500"))
        btn.clicked.connect(self._contact)
        hl.addWidget(btn)
        lay.addWidget(help_box)
        return menu

    def _switch(self, key: str):
        self._stack.setCurrentIndex(self._pages[key])
        for k, it in self._menu_items.items():
            it.set_active(k == key)
        self._current = key

    def _contact(self):
        url = str(self.cfg.get("support_url", "") or "").strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            self._switch("about")

    # ════════════════════════════════════════════════════════════════════
    #  AI model (Figma)
    # ════════════════════════════════════════════════════════════════════
    def _page_model(self) -> QWidget:
        w, lay = self._page()

        det = fz.SettingsCard("Detection modeli", "Shlemni aniqlaydigan YOLO modeli va uning ishlash rejimi")
        self._ai_enabled = self._toggle()
        det.add_row(fz.SettingRow("AI modelni yoqish", "O‘chirilsa faqat video ko‘rsatiladi", self._ai_enabled))

        # Ilova bilan keladigan modellar — bir bosishda almashtirish
        self._model_preset = fz.Segmented([name for name, _, _ in MODEL_PRESETS], -1)
        self._model_preset.changed.connect(self._on_model_preset)
        self._preset_row = fz.SettingRow("Model", "", self._model_preset)
        det.add_row(self._preset_row)

        self._model_path = fz.PathInput(280)
        self._model_path.edit.textEdited.connect(lambda _: (self._changed(), self._update_model_desc()))
        self._model_path.browse.connect(self._browse_model)
        test = fz.ghost_button("Tekshirish", h=31, px=12.5, pad=13, radius=7)
        test.clicked.connect(self._test_model)
        self._model_row = fz.SettingRow("Model fayli", "", fz.hbox(self._model_path, test, spacing=8), height=102)
        det.add_row(self._model_row)

        self._conf, conf_box = self._slider(0.10, 0.99, 0.01, lambda v: f"{v:.2f}")
        det.add_row(fz.SettingRow("Ishonch chegarasi", "Yuqori — kamroq noto‘g‘ri signal", conf_box))
        self._window, win_box = self._slider(3, 60, 1, lambda v: f"{int(v)} kadr", unit=True)
        self._window.valueChanged.connect(self._sync_threshold_range)
        det.add_row(fz.SettingRow("Ovoz berish oynasi", "Ko‘pchilik ovozi — kamroq adashish", win_box))

        # Kengaytirilgan (Figma'dagi bo'sh joyda — mavjud funksiyalar saqlangan)
        det.add_widget(self._subheader("Kengaytirilgan"))
        self._thresh, thr_box = self._slider(1, 60, 1, lambda v: f"{int(v)} kadr", unit=True)
        det.add_row(fz.SettingRow("Ko‘pchilik chegarasi", "Oynadagi “shlemsiz” kadrlar soni", thr_box), divider=False)
        det.add_row(fz.SettingRow("Kirish o‘lchami", "Kattaroq — aniqroq, lekin sekinroq",
                                  self._seg("yolo_imgsz", [416, 640, 1024, 1280], ["416", "640", "1024", "1280"])))
        det.add_row(fz.SettingRow("Kadr oralig‘i", "Har N-kadrda bir marta tahlil",
                                  self._seg("process_every_n", [1, 2, 3, 4, 5], ["1", "2", "3", "4", "5"])))
        det.add_row(fz.SettingRow("Kuzatish rejimi", "Ishchini kadrlar orasida kuzatish",
                                  self._seg("tracking_strictness", ["stable", "balanced", "fast"],
                                            ["Barqaror", "Muvozanat", "Tezkor"])))

        perf = fz.SettingsCard("Unumdorlik", "")
        perf.setFixedHeight(279)
        self._perf_card = perf
        self._gpu = self._toggle()
        perf.add_row(fz.SettingRow("GPU ishlatish (CUDA)", "Batch inference — bir nechta kamera bitta modelda", self._gpu))
        self._half = self._toggle()
        perf.add_row(fz.SettingRow("Half precision (FP16)", "Tezroq, xotira kamroq", self._half))
        perf.add_row(fz.SettingRow("Tahlil chastotasi", "Past — kamroq GPU yuki",
                                   self._seg("ai_fps_limit", [5, 10, 15], ["5 fps", "10 fps", "15 fps"])))

        viol = fz.SettingsCard("Buzilishni qayd etish", "Takroriy hodisalarni filtrlash")
        self._save_imgs = self._toggle()
        viol.add_row(fz.SettingRow("Buzilish rasmlarini saqlash", "Crop va to‘liq kadr · violations/", self._save_imgs))
        viol.add_row(fz.SettingRow("Takror ogohlantirish oralig‘i", "Bir ishchi uchun",
                                   self._seg("violation_cooldown", [30, 60, 300], ["30 s", "60 s", "5 daq"])))
        self._cleanup = self._toggle()
        self._cleanup_row = fz.SettingRow("Eski fayllarni avtomatik tozalash", "", self._cleanup)
        viol.add_row(self._cleanup_row)

        lay.addLayout(self._column(det), 1)
        lay.addLayout(self._column(perf, viol), 1)
        return w

    def _subheader(self, text: str) -> QWidget:
        w = QWidget()
        w.setFixedHeight(46)
        w.setStyleSheet("background:transparent;")
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 18, 0, 0)
        l.setSpacing(8)
        l.addWidget(fz.label(text.upper(), 10.5, 700, fz.MUTED, mono=True, tracking=1))
        l.addWidget(fz.hline())
        return w

    def _sync_threshold_range(self, window):
        self._thresh._max = float(int(window))
        if self._thresh.value() > window:
            self._set_slider(self._thresh, window)
        self._thresh.update()

    def _on_model_preset(self, i: int):
        if 0 <= i < len(MODEL_PRESETS):
            self._model_path.setText(MODEL_PRESETS[i][1])
            self._changed()
            self._update_model_desc()

    def _sync_model_preset(self):
        """Yo'l presetga mos bo'lsa segment yonadi; boshqa fayl — hech biri tanlanmaydi."""
        i = model_preset_index(self._model_path.text())
        if self._model_preset.current() != i:
            self._model_preset.set_current(i)
        desc = MODEL_PRESETS[i][2] if i >= 0 else "Boshqa model fayli tanlangan"
        fz.restyle(self._preset_row.desc, 11.5, 400, fz.MUTED)
        self._preset_row.desc.setText(desc)

    def _update_model_desc(self):
        self._sync_model_preset()
        p = self._model_path.text().strip()
        path = resolve_model_path(p) if p else None
        if path and path.exists():
            mb = path.stat().st_size / (1024 * 1024)
            state = "yuklangan" if "ultralytics" in sys.modules else "mavjud"
            txt, col = f"{mb:.1f} MB · {state}", fz.MUTED
        elif p:
            txt, col = "Fayl topilmadi", fz.RED
        else:
            txt, col = "Model tanlanmagan", fz.MUTED
        fz.restyle(self._model_row.desc, 11.5, 400, col)
        self._model_row.desc.setText(txt)

    @staticmethod
    def _gpu_text() -> str:
        torch = sys.modules.get("torch")
        if torch is None:
            return "GPU ma‘lumoti AI model yoqilganda aniqlanadi"
        try:
            if torch.cuda.is_available():
                return f"GPU mavjud: {torch.cuda.get_device_name(0)} · CUDA {torch.version.cuda}"
            return "GPU topilmadi — CPU rejimi"
        except Exception:
            return "GPU holati aniqlanmadi"

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Model tanlash", "", "PyTorch model (*.pt);;Barcha fayllar (*)")
        if path:
            self._model_path.setText(path)
            self._changed()
            self._update_model_desc()

    def _test_model(self):
        self._run_test("model", {"path": self._model_path.text().strip()},
                       self._model_row, "Model tekshirilmoqda…")

    def _run_test(self, mode: str, data: dict, row, busy_text: str):
        """Har test turi uchun alohida thread; ishlab turgani qayta ishga tushirilmaydi.
        Thread tugaguncha havola saqlanadi — aks holda GC uni ishlayotgan paytda
        o'chirib, "QThread: Destroyed while thread is still running" bilan qulatadi."""
        from app.ui.pages.settings_common import _TestThread
        running = self._test_threads.get(mode)
        if running is not None and running.isRunning():
            show_toast(self, "Tekshiruv hali davom etmoqda…", "info")
            return
        row.desc.setText(busy_text)
        t = _TestThread(mode, data)
        t.result.connect(lambda ok, msg: self._test_done(row, ok, msg))

        def _finished():
            if self._test_threads.get(mode) is t:
                del self._test_threads[mode]
            t.deleteLater()

        t.finished.connect(_finished)
        self._test_threads[mode] = t
        t.start()

    def _test_done(self, row, ok: bool, msg: str):
        fz.restyle(row.desc, 11.5, 400, fz.GREEN if ok else fz.RED)
        row.desc.setText(("OK: " if ok else "Xato: ") + str(msg)[:90])
        show_toast(self, msg, "success" if ok else "error")

    # ════════════════════════════════════════════════════════════════════
    #  Kameralar
    # ════════════════════════════════════════════════════════════════════
    def _page_cameras(self) -> QWidget:
        w, lay = self._page()
        add = fz.primary_button("Kamera qo‘shish", h=28, px=12.5, pad=12, radius=7, icon="plus", icon_size=14)
        add.clicked.connect(self._add_camera)
        self._cams_card = fz.SettingsCard("Kameralar", "", action=add)
        add_dep = fz.ghost_button("Bo‘lim", h=28, px=12.5, pad=11, radius=7, icon="plus", icon_size=14)
        add_dep.clicked.connect(self._add_department)
        self._deps_card = fz.SettingsCard("Bo‘limlar", "", action=add_dep)

        stream = fz.SettingsCard("Video oqimi", "Ko‘rsatish va inference yuklamasi")
        stream.add_row(fz.SettingRow("Video FPS cheklovi", "Ekranga chiqariladigan kadrlar",
                                     self._seg("video_fps_limit", [10, 15, 25, 30], ["10", "15", "25", "30"])))
        stream.add_row(fz.SettingRow("Batch hajmi", "Bir inference'dagi kadrlar",
                                     self._seg("inference_batch_size", [1, 2, 3, 4, 6, 8], ["1", "2", "3", "4", "6", "8"])))
        stream.add_row(fz.SettingRow("Bitta modelda kameralar", "Model nusxasi qancha kamerani xizmat qiladi",
                                     self._seg("cameras_per_model", [1, 2, 3, 4, 6, 8], ["1", "2", "3", "4", "6", "8"])))
        wiz = fz.ghost_button("Ochish", h=31)
        wiz.clicked.connect(self.wizard_requested.emit)
        stream.add_row(fz.SettingRow("Sozlash ustasi", "Kamera va backend’ni bosqichma-bosqich sozlash", wiz))

        lay.addLayout(self._column(self._cams_card), 1)
        lay.addLayout(self._column(self._deps_card, stream, stretch_last=True), 1)
        return w

    @staticmethod
    def _ip(rtsp: str) -> str:
        try:
            after = rtsp.split("@", 1)[1] if "@" in rtsp else rtsp.split("//", 1)[-1]
            return after.split("/", 1)[0].split(":", 1)[0] or "—"
        except Exception:
            return "—"

    def _icon_btn(self, icon: str, tip: str, danger: bool = False):
        from PyQt6.QtWidgets import QPushButton
        from PyQt6.QtCore import QSize
        b = QPushButton()
        b.setFixedSize(31, 31)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setIcon(fz.svg_icon(icon, 14, fz.RED if danger else fz.TEXT2))
        b.setIconSize(QSize(14, 14))
        b.setStyleSheet(
            f"QPushButton {{ background:{fz.CARD}; border:1px solid {fz.GHOST_BORDER}; border-radius:7px; }}"
            f"QPushButton:hover {{ background:{fz.RAISED}; border-color:{fz.RED if danger else '#4a5b78'}; }}"
        )
        return b

    def _refresh_cameras(self):
        cams = self.cfg.get_cameras()
        deps = {d.get("id"): d.get("name", "Bo‘lim") for d in self.cfg.get_departments()}
        enabled = sum(1 for c in cams if c.get("enabled", True))
        self._cams_card.desc.setText(f"{len(cams)} ta kamera · {enabled} ta yoqilgan · maksimal {MAX_CAMERAS}")
        self._cams_card.clear_rows()
        for c in cams:
            cid = c.get("id")
            tg = fz.Toggle(c.get("enabled", True))
            tg.toggled.connect(lambda v, i=cid: self._set_camera_enabled(i, v))
            ed = self._icon_btn("pencil", "Tahrirlash")
            ed.clicked.connect(lambda _, i=cid: self._edit_camera(i))
            rm = self._icon_btn("trash", "O‘chirish", danger=True)
            rm.clicked.connect(lambda _, i=cid: self._delete_camera(i))
            desc = f"CAM-{int(cid):02d} · {deps.get(c.get('department_id'), '—')} · {self._ip(c.get('rtsp_url', ''))}"
            self._cams_card.add_row(fz.SettingRow(c.get("name", f"Kamera {cid}"), desc,
                                                  fz.hbox(ed, rm, 6, tg, spacing=6)))

        self._deps_card.desc.setText(f"{len(deps)} ta bo‘lim")
        self._deps_card.clear_rows()
        for d in self.cfg.get_departments():
            did = d.get("id")
            n = sum(1 for c in cams if c.get("department_id") == did)
            ren = self._icon_btn("pencil", "Nomini o‘zgartirish")
            ren.clicked.connect(lambda _, i=did: self._rename_department(i))
            rm = self._icon_btn("trash", "O‘chirish", danger=True)
            rm.clicked.connect(lambda _, i=did: self._remove_department(i))
            self._deps_card.add_row(fz.SettingRow(d.get("name", "Bo‘lim"), f"{n} ta kamera", fz.hbox(ren, rm, spacing=6)))

    def _persist(self, success_msg: str) -> bool:
        if self.cfg.save():
            show_toast(self, success_msg, "success")
            return True
        AppMessageBox.critical(self, "Saqlanmadi", "Sozlamalar faylga yozilmadi:\n"
                               + (getattr(self.cfg, "last_save_error", "") or "noma'lum xato"))
        return False

    def open_add_camera(self):
        self._switch("cameras")
        QTimer.singleShot(0, self._add_camera)

    def _add_camera(self):
        from app.ui.pages.settings_common import CameraEditDialog
        cams = self.cfg.get_cameras()
        if len(cams) >= MAX_CAMERAS:
            AppMessageBox.warning(self, "Cheklov", f"Maksimal {MAX_CAMERAS} ta kamera qo‘shish mumkin.")
            return
        deps = self.cfg.get_departments()
        if not deps:
            AppMessageBox.information(self, "Bo‘lim kerak", "Avval bo‘lim yarating, keyin kamera qo‘shing.")
            return
        dlg = CameraEditDialog(departments=deps, parent=self, existing_cameras=cams)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cam = dlg.get_camera()
            try:
                new = self.cfg.add_camera(name=cam["name"], rtsp_url=cam["rtsp_url"],
                                          company_id=cam.get("company_id", ""),
                                          enabled=cam.get("enabled", True),
                                          department_id=cam.get("department_id"))
            except ValueError as e:
                AppMessageBox.warning(self, "Xatolik", str(e))
                return
            self._refresh_cameras()
            if self._persist(f"Kamera qo‘shildi: “{new['name']}” — ulanmoqda…"):
                self.cameras_changed.emit()

    def _edit_camera(self, cam_id):
        from app.ui.pages.settings_common import CameraEditDialog
        cam = self.cfg.get_camera_by_id(cam_id)
        if not cam:
            return
        dlg = CameraEditDialog(camera=cam, departments=self.cfg.get_departments(), parent=self,
                               existing_cameras=self.cfg.get_cameras())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_camera()
            self.cfg.update_camera(cam_id, **{k: data[k] for k in ("name", "rtsp_url", "company_id",
                                                                  "department_id", "enabled") if k in data})
            self._refresh_cameras()
            if self._persist(f"Kamera yangilandi: “{data.get('name', '')}”"):
                self.cameras_changed.emit()

    def _delete_camera(self, cam_id):
        cam = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"ID:{cam_id}") if cam else f"ID:{cam_id}"
        if AppMessageBox.question(self, "O‘chirish", f"“{name}” kamerasini o‘chirmoqchimisiz?",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if not self.cfg.remove_camera(cam_id):
            AppMessageBox.warning(self, "Xatolik", "Kamida 1 ta kamera bo‘lishi shart.")
            return
        self._refresh_cameras()
        if self._persist(f"Kamera o‘chirildi: “{name}”"):
            self.cameras_changed.emit()

    def _set_camera_enabled(self, cam_id, enabled: bool):
        self.cfg.update_camera(cam_id, enabled=bool(enabled))
        self._refresh_cameras()
        if self._persist("Kamera " + ("yoqildi" if enabled else "o‘chirildi")):
            self.cameras_changed.emit()

    def _add_department(self):
        name, ok = AppInputDialog.get_text(self, "Yangi bo‘lim", "Bo‘lim nomi:", placeholder="Masalan: Sex 2, Ombor")
        if not ok:
            return
        try:
            dep = self.cfg.add_department(name)
        except ValueError as e:
            AppMessageBox.warning(self, "Xatolik", str(e))
            return
        self._refresh_cameras()
        if self._persist(f"Bo‘lim qo‘shildi: “{dep['name']}”"):
            self.departments_changed.emit()

    def _rename_department(self, dep_id):
        dep = self.cfg.get_department_by_id(dep_id)
        if not dep:
            return
        name, ok = AppInputDialog.get_text(self, "Bo‘lim nomi", "Yangi nom:", text=dep.get("name", ""))
        name = (name or "").strip()
        if not ok or not name:
            return
        self.cfg.update_department(dep_id, name=name)
        self._refresh_cameras()
        if self._persist(f"Bo‘lim nomi o‘zgartirildi: “{name}”"):
            self.departments_changed.emit()

    def _remove_department(self, dep_id):
        dep = self.cfg.get_department_by_id(dep_id) or {}
        if AppMessageBox.question(self, "Bo‘limni o‘chirish",
                                  f"“{dep.get('name', '')}” o‘chirilsinmi? Kameralar va xodimlar birinchi bo‘limga o‘tkaziladi.",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if not self.cfg.remove_department(dep_id):
            AppMessageBox.warning(self, "Xatolik", "Kamida 1 ta bo‘lim bo‘lishi shart.")
            return
        self._refresh_cameras()
        if self._persist("Bo‘lim o‘chirildi"):
            self.departments_changed.emit()

    # ════════════════════════════════════════════════════════════════════
    #  Telegram / Backend / FaceID / Saqlash / Ko'rinish / Dastur haqida
    # ════════════════════════════════════════════════════════════════════
    def _page_telegram(self) -> QWidget:
        w, lay = self._page()
        c = fz.SettingsCard("Telegram xabarnomalari", "Buzilish aniqlanganda bot orqali rasm bilan xabar yuboriladi")
        self._tg_enabled = self._toggle()
        c.add_row(fz.SettingRow("Telegram’ni yoqish", "O‘chirilsa xabarlar yuborilmaydi", self._tg_enabled))
        self._tg_token = self._edit("123456:ABC-DEF…", 320, mono=True, password=True)
        c.add_row(fz.SettingRow("Bot token", "@BotFather’dan olingan kalit", self._tg_token))
        self._tg_chats = self._edit("-1001234567890, 987654321", 320, mono=True)
        c.add_row(fz.SettingRow("Chat ID’lar", "Bir nechta bo‘lsa vergul bilan ajrating", self._tg_chats))
        test = fz.ghost_button("Tekshirish", h=31)
        test.clicked.connect(self._test_telegram)
        self._tg_test_row = fz.SettingRow("Ulanishni tekshirish", "Sinov xabari yuboriladi", test)
        c.add_row(self._tg_test_row)
        lay.addLayout(self._column(c), 1)
        lay.addLayout(self._column(self._info_card(
            "Qanday ishlaydi", "Xabarnoma oqimi",
            [("1. Aniqlash", "Shlemsiz ishchi ketma-ket kadrlarda tasdiqlanadi"),
             ("2. Navbat", "Xabar fon navbatiga qo‘shiladi, internet uzilsa qayta yuboriladi"),
             ("3. Yuborish", "Rasm, kamera nomi va vaqt chat’larga yuboriladi")])), 1)
        return w

    def _page_backend(self) -> QWidget:
        w, lay = self._page()
        c = fz.SettingsCard("Backend API", "Hodisalar markaziy serverga sinxronlanadi")
        self._be_enabled = self._toggle()
        c.add_row(fz.SettingRow("Backend’ni yoqish", "Hodisalar serverga yuboriladi", self._be_enabled))
        self._be_url = self._edit("https://api.example.uz", 320, mono=True)
        c.add_row(fz.SettingRow("Server manzili", "To‘liq URL (https://…)", self._be_url))
        self._be_login = self._edit("login", 320)
        c.add_row(fz.SettingRow("Login", "Qurilma login’i", self._be_login))
        self._be_pass = self._edit("••••••••", 320, password=True)
        c.add_row(fz.SettingRow("Parol", "Qurilma paroli", self._be_pass))
        test = fz.ghost_button("Tekshirish", h=31)
        test.clicked.connect(self._test_backend)
        self._be_test_row = fz.SettingRow("Ulanishni tekshirish", "Login va kompaniya ID’lari tekshiriladi", test)
        c.add_row(self._be_test_row)
        self._be_info = self._info_card("Kompaniya ID’lari", "", [])
        lay.addLayout(self._column(c), 1)
        lay.addLayout(self._column(self._be_info), 1)
        return w

    def _page_faceid(self) -> QWidget:
        w, lay = self._page()
        c = fz.SettingsCard("FaceID", "Xodimlarni yuz orqali tanish va hududga ruxsat nazorati")
        self._face_enabled = self._toggle()
        c.add_row(fz.SettingRow("FaceID’ni yoqish", "Buzilishda xodim nomi aniqlanadi", self._face_enabled))
        self._roster = self._toggle()
        c.add_row(fz.SettingRow("Kirish ro‘yxati nazorati", "Faqat ruxsat etilgan xodimlar hududga kiradi", self._roster))
        self._face_thr, thr_box = self._slider(0.30, 0.90, 0.01, lambda v: f"{v:.2f}")
        c.add_row(fz.SettingRow("Tanish chegarasi", "Yuqori — qat’iyroq moslik", thr_box))
        self._face_info = self._info_card("Xodimlar bazasi", "", [])
        lay.addLayout(self._column(c), 1)
        lay.addLayout(self._column(self._face_info), 1)
        return w

    def _page_storage(self) -> QWidget:
        w, lay = self._page()
        c = fz.SettingsCard("Saqlash", "Dalil rasmlari va navbatlar")
        self._viol_dir = fz.PathInput(320, "Standart: violations/")
        self._viol_dir.edit.textEdited.connect(lambda _: self._changed())
        self._viol_dir.browse.connect(self._browse_dir)
        c.add_row(fz.SettingRow("Rasmlar papkasi", "Buzilish rasmlari shu yerga yoziladi", self._viol_dir))
        self._keep_days, keep_box = self._slider(1, 90, 1, lambda v: f"{int(v)} kun", unit=True)
        self._keep_days.valueChanged.connect(lambda _: self._update_cleanup_desc())
        c.add_row(fz.SettingRow("Saqlash muddati", "Avtomatik tozalashda shundan eskilari o‘chiriladi", keep_box))
        c.add_row(fz.SettingRow("Bazadagi tarix", "Hodisalar va grafiklar uchun yozuvlar shuncha saqlanadi",
                                self._seg("keep_db_days", [90, 180, 365, 730],
                                          ["3 oy", "6 oy", "1 yil", "2 yil"])))
        c.add_row(fz.SettingRow("Yozish navbati", "Bir vaqtda kutayotgan rasmlar soni",
                                self._seg("violation_save_queue_size", [32, 64, 128, 256], ["32", "64", "128", "256"])))
        lay.addLayout(self._column(c), 1)
        lay.addLayout(self._column(self._info_card(
            "Maslahat", "",
            [("Disk joyi", "Har bir buzilish ~200–400 KB (crop + to‘liq kadr)"),
             ("Tozalash", "“Eski fayllarni avtomatik tozalash” AI model bo‘limida yoqiladi")])), 1)
        return w

    def _page_appearance(self) -> QWidget:
        w, lay = self._page()
        c = fz.SettingsCard("Ko‘rinish", "Yuqori panel ma’lumotlari")
        self._site = self._edit("Zavod №1", 240)
        c.add_row(fz.SettingRow("Obyekt nomi", "Yuqori panelda “SafeZone” yonida ko‘rsatiladi", self._site))
        self._initials = self._edit("BM", 80)
        self._initials.setMaxLength(2)
        c.add_row(fz.SettingRow("Operator", "Avatar bosh harflari (2 ta harf)", self._initials))
        lay.addLayout(self._column(c), 1)
        lay.addStretch(1)
        return w

    def _page_about(self) -> QWidget:
        w, lay = self._page()
        c = fz.SettingsCard("SafeZone", f"Versiya {__version__} · shlem kiyishni AI orqali nazorat qilish")
        self._diag_row = fz.SettingRow("Tizim holati", "", None, height=118)
        self._diag_row.desc.setWordWrap(True)
        self._diag_row.desc.setFixedHeight(84)
        self._diag_row.desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        c.add_row(self._diag_row)
        wiz = fz.ghost_button("Ochish", h=31)
        wiz.clicked.connect(self.wizard_requested.emit)
        c.add_row(fz.SettingRow("Sozlash ustasi", "Birinchi sozlashni qaytadan o‘tkazish", wiz))
        logs = fz.ghost_button("Ochish", h=31)
        logs.clicked.connect(lambda: self._open_dir(Path.cwd() / "logs"))
        c.add_row(fz.SettingRow("Loglar papkasi", "Xatoliklar va ish jurnali", logs))
        conf = fz.ghost_button("Ochish", h=31)
        conf.clicked.connect(lambda: self._open_dir(Path.cwd()))
        c.add_row(fz.SettingRow("Ma’lumotlar papkasi", "settings.json, ma’lumotlar bazasi, rasmlar", conf))
        lay.addLayout(self._column(c), 1)
        lay.addStretch(1)
        return w

    def _info_card(self, title: str, desc: str, rows: list[tuple[str, str]]) -> fz.SettingsCard:
        c = fz.SettingsCard(title, desc)
        self._fill_info(c, rows)
        return c

    @staticmethod
    def _fill_info(card: fz.SettingsCard, rows: list[tuple[str, str]]):
        card.clear_rows()
        for t, d in rows:
            card.add_row(fz.SettingRow(t, d))

    @staticmethod
    def _open_dir(path: Path):
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Rasmlar papkasi")
        if path:
            self._viol_dir.setText(path)
            self._changed()

    def _test_telegram(self):
        chats = [x.strip() for x in self._tg_chats.text().split(",") if x.strip()]
        self._run_test("telegram", {"token": self._tg_token.text().strip(), "chat_ids": chats},
                       self._tg_test_row, "Tekshirilmoqda…")

    def _test_backend(self):
        self._run_test("backend", {"url": self._be_url.text().strip(), "login": self._be_login.text().strip(),
                                   "password": self._be_pass.text().strip(),
                                   "bad_company_ids": self._bad_company_ids()},
                       self._be_test_row, "Tekshirilmoqda…")

    def _bad_company_ids(self) -> list[str]:
        rx = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
        return [c.get("name", "?") for c in self.cfg.get_cameras() if not rx.match(str(c.get("company_id", "")).strip())]

    def _update_cleanup_desc(self):
        self._cleanup_row.desc.setText(f"{int(self._keep_days.value())} kundan eski rasmlar o‘chiriladi")

    # ════════════════════════════════════════════════════════════════════
    #  Yuklash / saqlash
    # ════════════════════════════════════════════════════════════════════
    def _load_values(self):
        self._loading = True
        try:
            c = self.cfg
            self._ai_enabled.set_checked(bool(c.get("ai_model_enabled", False)))
            self._model_path.setText(str(c.get("model_path", "") or ""))
            self._update_model_desc()
            self._set_slider(self._conf, float(c.get("confidence", 0.6)))
            window = int(c.get("helmet_status_window", 50))
            self._window._max = float(max(60, window))
            self._set_slider(self._window, window)
            self._thresh._max = float(window)
            self._set_slider(self._thresh, min(int(c.get("helmet_status_threshold", 30)), window))
            self._gpu.set_checked(bool(c.get("use_gpu", True)))
            self._half.set_checked(bool(c.get("half_precision", False)))
            self._save_imgs.set_checked(bool(c.get("save_violations", True)))
            self._cleanup.set_checked(bool(c.get("cleanup_files", False)))
            self._perf_card.desc.setText(self._gpu_text())

            for key, (seg, values) in self._segs.items():
                v = c.get(key)
                if v in values:
                    idx = values.index(v)
                elif isinstance(v, (int, float)) and all(isinstance(x, (int, float)) for x in values):
                    idx = min(range(len(values)), key=lambda i: abs(values[i] - v))   # eng yaqini
                else:
                    idx = -1
                seg._cur = idx
                seg._touched = False
                seg.update()

            self._tg_enabled.set_checked(bool(c.get("telegram_enabled", False)))
            self._tg_token.setText(str(c.get("telegram_token", "") or ""))
            self._tg_chats.setText(", ".join(getattr(c, "telegram_chat_ids", []) or c.get("telegram_chat_ids", []) or []))
            self._be_enabled.set_checked(bool(c.get("backend_enabled", False)))
            self._be_url.setText(str(c.get("backend_url", "") or ""))
            self._be_login.setText(str(c.get("backend_login", "") or ""))
            self._be_pass.setText(str(c.get("backend_password", "") or ""))
            self._face_enabled.set_checked(bool(c.get("faceid_enabled", False)))
            self._roster.set_checked(bool(c.get("access_roster_enabled", False)))
            self._set_slider(self._face_thr, float(c.get("faceid_threshold", 0.42)))
            self._viol_dir.setText(str(c.get("violations_dir", "") or ""))
            self._set_slider(self._keep_days, int(c.get("keep_files_days", 7)))
            self._update_cleanup_desc()
            self._site.setText(str(c.get("site_name", "") or ""))
            self._initials.setText(str(c.get("operator_initials", "") or ""))

            self._refresh_cameras()
            self._refresh_status()
        finally:
            self._loading = False
        self._set_dirty(False)

    def _refresh_status(self):
        c = self.cfg
        self._menu_items["telegram"].set_status(bool(c.get("telegram_enabled")) and bool(c.get("telegram_token")))
        self._menu_items["backend"].set_status(bool(c.get("backend_enabled")) and bool(c.get("backend_url")))
        self._menu_items["faceid"].set_status(bool(c.get("faceid_enabled")))
        cams = c.get_cameras()
        bad = self._bad_company_ids()
        self._fill_info(self._be_info, [
            ("Kameralar", f"{len(cams)} ta kamera, {len(cams) - len(bad)} tasida to‘g‘ri kompaniya ID"),
            ("Muammoli", ", ".join(bad[:6]) + ("…" if len(bad) > 6 else "") if bad else "Yo‘q — hammasi to‘g‘ri"),
        ])
        self._be_info.desc.setText("Har bir kamera UUID formatidagi kompaniya ID’ga ega bo‘lishi kerak")
        users = c.get_users()
        with_photo = [u for u in users if any(Path(p).exists() for p in (u.get("photo_paths") or [u.get("photo_path", "")]) if p)]
        self._fill_info(self._face_info, [
            ("Jami xodimlar", f"{len(users)} ta"),
            ("Yuz namunasi bor", f"{len(with_photo)} ta"),
            ("Namuna kerak", f"{len(users) - len(with_photo)} ta — Xodimlar sahifasida rasm qo‘shing"),
        ])
        self._face_info.desc.setText("FaceID shu ro‘yxat bo‘yicha tanish qiladi")
        lines = [
            f"Kameralar: jami {len(cams)} ta / {len(c.get_enabled_cameras())} ta yoqilgan",
            f"Xodimlar: {len(users)} ta / {len(with_photo)} ta rasmli",
            f"AI: {'yoqilgan' if c.get('ai_model_enabled') else 'o‘chiq'} · imgsz {c.get('yolo_imgsz', 640)}",
            f"Xabarnoma: Telegram {'yoqilgan' if c.get('telegram_enabled') else 'o‘chiq'}, "
            f"Backend {'yoqilgan' if c.get('backend_enabled') else 'o‘chiq'}",
        ]
        self._diag_row.desc.setText("\n".join(lines))

    def _seg_value(self, key):
        seg, values = self._segs[key]
        i = seg.current()
        if not getattr(seg, "_touched", False):
            return self.cfg.get(key)          # foydalanuvchi o'zgartirmagan — asl qiymat saqlanadi
        return values[i] if 0 <= i < len(values) else self.cfg.get(key)

    def _cancel(self):
        self._load_values()
        show_toast(self, "O‘zgarishlar bekor qilindi", "info")

    def _save(self):
        chats = [x.strip() for x in self._tg_chats.text().split(",") if x.strip()]
        window = int(self._window.value())
        data = {
            "ai_model_enabled": self._ai_enabled.is_checked(),
            "model_path": self._model_path.text().strip(),
            "confidence": round(float(self._conf.value()), 2),
            "helmet_status_window": window,
            "helmet_status_threshold": min(int(self._thresh.value()), window),
            "use_gpu": self._gpu.is_checked(),
            "half_precision": self._half.is_checked(),
            "save_violations": self._save_imgs.is_checked(),
            "cleanup_files": self._cleanup.is_checked(),
            "telegram_enabled": self._tg_enabled.is_checked(),
            "telegram_token": self._tg_token.text().strip(),
            "telegram_chat_ids": chats,
            "backend_enabled": self._be_enabled.is_checked(),
            "backend_url": self._be_url.text().strip(),
            "backend_login": self._be_login.text().strip(),
            "backend_password": self._be_pass.text().strip(),
            "faceid_enabled": self._face_enabled.is_checked(),
            "access_roster_enabled": self._roster.is_checked(),
            "faceid_threshold": round(float(self._face_thr.value()), 2),
            "violations_dir": self._viol_dir.text().strip(),
            "keep_files_days": int(self._keep_days.value()),
            "site_name": self._site.text().strip(),
            "operator_initials": self._initials.text().strip().upper(),
        }
        for key in self._segs:
            data[key] = self._seg_value(key)
        changed = [k for k, v in data.items() if self.cfg.get(k) != v]
        if not changed:
            self._set_dirty(False)
            show_toast(self, "O‘zgarish yo‘q", "info")
            return
        self.cfg.update(data)
        needs_restart = any(k in _RESTART_KEYS for k in changed)
        msg = f"Sozlamalar saqlandi ({len(changed)} ta o‘zgarish)" + (
            " — kameralar qayta ishga tushirilmoqda" if needs_restart else "")
        if not self._persist(msg):
            return
        self._set_dirty(False)
        self._refresh_status()
        if "site_name" in changed or "operator_initials" in changed:
            self.branding_changed.emit(data["site_name"], data["operator_initials"])
        if needs_restart:
            self.settings_saved.emit()
