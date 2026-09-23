"""
SetupWizard — birinchi ishga tushirishda qadam-baqadam sozlash.

Qadamlar: Xush kelibsiz → Kamera (ulanishni tekshirish) → AI va FaceID →
Backend (ixtiyoriy) → Tayyor. "Boshlash" bosilganda sozlamalar diskka yoziladi.
Settings > Diagnostika dan qayta ochish mumkin.
"""
from __future__ import annotations

import os
import threading

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from app.ui.styles import C
from app.ui.widgets.app_dialog import AppMessageBox
from app.ui.widgets.frameless import FramedDialog

_RTSP_HINT = "rtsp://login:parol@192.168.1.10:554/Streaming/Channels/101"


class _CheckThread(QThread):
    """Kamera yoki backend ulanishini fon rejimida tekshiradi."""
    done = pyqtSignal(bool, str)

    def __init__(self, mode: str, data: dict):
        super().__init__()
        self.mode, self.data = mode, data

    def run(self):
        try:
            if self.mode == "camera":
                self.done.emit(*self._check_camera(self.data["url"]))
            else:
                self.done.emit(*self._check_backend())
        except Exception as exc:
            self.done.emit(False, str(exc))

    @staticmethod
    def _check_camera(url: str) -> tuple[bool, str]:
        import cv2
        from app.infrastructure.camera.rtsp_probe import diagnose

        result: list = [None]

        def _open():
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000|threads;1"
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            try:
                if cap.isOpened():
                    for _ in range(10):
                        ok, frame = cap.read()
                        if ok and frame is not None:
                            result[0] = frame.shape
                            break
            finally:
                cap.release()

        t = threading.Thread(target=_open, daemon=True)
        t.start()
        t.join(15)
        if result[0] is not None:
            h, w = result[0][:2]
            return True, f"Kamera ishlayapti: {w}×{h}"
        return False, diagnose(url) or "Video oqim ochilmadi"

    def _check_backend(self) -> tuple[bool, str]:
        import requests
        from app.infrastructure.notifications.backend_client import BackendClient

        client = BackendClient(self.data["url"], self.data["login"], self.data["password"])
        if not client.base_url:
            return False, "API URL kiritilmagan"
        client._access_token(requests)
        return True, f"Login muvaffaqiyatli: {client.base_url}"


class SetupWizard(FramedDialog):
    STEPS = ["Xush kelibsiz", "Kamera", "AI va FaceID", "Backend", "Tayyor"]

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._thread: _CheckThread | None = None
        self.setWindowTitle("SafeZone — sozlash ustasi")
        self.setModal(True)
        self.setMinimumSize(640, 540)

        root = QVBoxLayout(self.body)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        self._steps_bar = QHBoxLayout()
        self._step_lbls: list[QLabel] = []
        for i, name in enumerate(self.STEPS):
            lbl = QLabel(f"{i + 1}. {name}")
            self._step_lbls.append(lbl)
            self._steps_bar.addWidget(lbl)
        self._steps_bar.addStretch()
        root.addLayout(self._steps_bar)

        self._stack = QStackedWidget(objectName="wizStack")
        root.addWidget(self._stack, 1)
        for build in (self._page_welcome, self._page_camera, self._page_ai,
                      self._page_backend, self._page_done):
            self._stack.addWidget(build())

        nav = QHBoxLayout()
        self._skip_btn = QPushButton("Keyinroq sozlayman", objectName="appDialogSecondary")
        self._skip_btn.clicked.connect(self._skip)
        nav.addWidget(self._skip_btn)
        nav.addStretch()
        self._back_btn = QPushButton("Orqaga", objectName="appDialogSecondary")
        self._back_btn.clicked.connect(lambda: self._go(self._stack.currentIndex() - 1))
        self._next_btn = QPushButton("Keyingi", objectName="appDialogPrimary")
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._next)
        for b in (self._skip_btn, self._back_btn, self._next_btn):
            b.setMinimumSize(110, 36)
        nav.addWidget(self._back_btn)
        nav.addWidget(self._next_btn)
        root.addLayout(nav)

        self._apply_frame_style()
        self._go(0)

    # ── Sahifalar ──────────────────────────────────────────────────────────

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget(objectName="wizPage")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(10)
        t = QLabel(title, objectName="wizTitle")
        lay.addWidget(t)
        s = QLabel(subtitle, objectName="wizText")
        s.setWordWrap(True)
        lay.addWidget(s)
        return w, lay

    def _field(self, lay: QVBoxLayout, label: str, placeholder: str = "", text: str = "",
               password: bool = False) -> QLineEdit:
        lay.addWidget(QLabel(label, objectName="wizLabel"))
        e = QLineEdit(text)
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(36)
        if password:
            e.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(e)
        return e

    def _page_welcome(self) -> QWidget:
        w, lay = self._page(
            "SafeZone'ga xush kelibsiz",
            "Tizimni 4 qadamda ishga tayyorlaymiz. Tayyorlab qo'ying:",
        )
        for icon, head, text in [
            ("1", "Kamera manzili", "RTSP URL: kamera IP manzili, login va paroli"),
            ("2", "Videokarta (ixtiyoriy)", "NVIDIA bo'lsa AI tez ishlaydi, bo'lmasa protsessorda"),
            ("3", "Backend (ixtiyoriy)", "Buzilishlarni markaziy serverga yuborish uchun"),
        ]:
            lay.addWidget(self._info_row(icon, head, text))
        lay.addSpacing(6)
        foot = QLabel("Hamma sozlamani keyin «Sozlamalar» bo'limida o'zgartirish mumkin.",
                      objectName="wizHint")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        lay.addStretch()
        return w

    def _info_row(self, num: str, head: str, text: str) -> QWidget:
        row = QWidget(objectName="wizInfoRow")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(row)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(12)
        badge = QLabel(num, objectName="wizNum")
        badge.setFixedSize(26, 26)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(QLabel(head, objectName="wizRowHead"))
        t = QLabel(text, objectName="wizHint")
        t.setWordWrap(True)
        col.addWidget(t)
        h.addLayout(col, 1)
        return row

    def _page_camera(self) -> QWidget:
        w, lay = self._page("Birinchi kamera",
                            "Kamera nomi va RTSP manzilini kiriting, keyin ulanishni tekshiring.")
        cam = self._first_camera()
        placeholder = "<kamera-ip>" in str(cam.get("rtsp_url", "")) if cam else True
        self._cam_name = self._field(lay, "Kamera nomi", "Masalan: Kirish darvozasi",
                                     "" if placeholder else cam.get("name", ""))
        self._cam_url = self._field(lay, "RTSP URL", _RTSP_HINT,
                                    "" if placeholder else cam.get("rtsp_url", ""))
        hint = QLabel("Hikvision: /Streaming/Channels/101 · Dahua: /cam/realmonitor?channel=1&subtype=0",
                      objectName="wizHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        row = QHBoxLayout()
        self._cam_test_btn = QPushButton("Ulanishni tekshirish", objectName="appDialogSecondary")
        self._cam_test_btn.setMinimumHeight(34)
        self._cam_test_btn.clicked.connect(self._test_camera)
        row.addWidget(self._cam_test_btn)
        row.addStretch()
        lay.addLayout(row)
        self._cam_result = QLabel("", objectName="wizResult")
        self._cam_result.setWordWrap(True)
        lay.addWidget(self._cam_result)
        lay.addStretch()
        return w

    def _page_ai(self) -> QWidget:
        w, lay = self._page("AI va FaceID", "Shlemsiz odamlarni aniqlash va xodimlarni yuzidan tanish.")
        gpu = self._gpu_name()
        self._ai_check = QCheckBox("AI aniqlashni yoqish (shlem nazorati)")
        self._ai_check.setChecked(bool(self.cfg.get("ai_model_enabled", False)) or bool(gpu))
        lay.addWidget(self._ai_check)
        lay.addWidget(QLabel(f"Videokarta: {gpu}" if gpu else
                             "NVIDIA videokarta topilmadi — AI CPU da sekinroq ishlaydi",
                             objectName="wizHint"))
        self._face_check = QCheckBox("FaceID — buzilishni xodim bilan bog'lash")
        self._face_check.setChecked(bool(self.cfg.get("faceid_enabled", False)))
        lay.addWidget(self._face_check)
        note = QLabel("FaceID uchun xodimlar va ularning rasmlari «Xodimlar» sahifasida qo'shiladi. "
                      "Kamera yuzlarni yaqindan (2–4 m) ko'rishi kerak.", objectName="wizHint")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch()
        return w

    def _page_backend(self) -> QWidget:
        w, lay = self._page("Backend (ixtiyoriy)",
                            "Buzilishlar markaziy serverga yuborilsin desangiz, ma'lumotlarni kiriting. "
                            "Kerak bo'lmasa «Keyingi» ni bosing.")
        self._be_check = QCheckBox("Buzilishlarni backend'ga yuborish")
        self._be_check.setChecked(bool(self.cfg.get("backend_enabled", False)))
        lay.addWidget(self._be_check)
        self._be_url = self._field(lay, "API URL", "https://server.uz", self.cfg.get("backend_url", ""))
        self._be_login = self._field(lay, "Login", "", self.cfg.get("backend_login", ""))
        self._be_pass = self._field(lay, "Parol", "", self.cfg.get("backend_password", ""), password=True)
        row = QHBoxLayout()
        self._be_test_btn = QPushButton("Backend'ni tekshirish", objectName="appDialogSecondary")
        self._be_test_btn.setMinimumHeight(34)
        self._be_test_btn.clicked.connect(self._test_backend)
        row.addWidget(self._be_test_btn)
        row.addStretch()
        lay.addLayout(row)
        self._be_result = QLabel("", objectName="wizResult")
        self._be_result.setWordWrap(True)
        lay.addWidget(self._be_result)
        lay.addStretch()
        return w

    def _page_done(self) -> QWidget:
        w, lay = self._page("Hammasi tayyor", "")
        self._summary = QLabel("", objectName="wizText")
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._summary)
        lay.addStretch()
        return w

    # ── Navigatsiya ────────────────────────────────────────────────────────

    def _go(self, idx: int):
        idx = max(0, min(idx, self._stack.count() - 1))
        self._stack.setCurrentIndex(idx)
        for i, lbl in enumerate(self._step_lbls):
            color = C("accent") if i == idx else (C("success") if i < idx else C("text_muted"))
            weight = 800 if i == idx else 600
            lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: {weight};"
                              " background: transparent; margin-right: 10px;")
        self._back_btn.setVisible(idx > 0)
        last = idx == self._stack.count() - 1
        self._next_btn.setText("Boshlash" if last else "Keyingi")
        self._skip_btn.setVisible(not last)
        if last:
            self._summary.setText(self._summary_html())

    def _next(self):
        idx = self._stack.currentIndex()
        if idx == 1 and not self._validate_camera():
            return
        if idx == 3 and self._be_check.isChecked() and not self._be_url.text().strip():
            self._be_result.setText("API URL kiritilmagan")
            self._be_result.setStyleSheet(f"color: {C('danger')};")
            return
        if idx == self._stack.count() - 1:
            self._finish()
            return
        self._go(idx + 1)

    def _skip(self):
        reply = AppMessageBox.question(
            self, "Sozlashni keyinga qoldirish",
            "Usta yopiladi. Keyinroq «Sozlamalar → Diagnostika» dan qayta ochishingiz mumkin.\n\n"
            "Yopilsinmi?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.reject()

    # ── Tekshiruvlar ───────────────────────────────────────────────────────

    def _validate_camera(self) -> bool:
        from app.ui.pages.settings_dialog import confirm_camera_fields

        name, url = self._cam_name.text().strip(), self._cam_url.text().strip()
        cam = self._first_camera()
        others = [c for c in self.cfg.get_cameras() if not cam or c.get("id") != cam.get("id")]
        return confirm_camera_fields(self, name, url, "", others)

    def _run_check(self, mode: str, data: dict, btn: QPushButton, out: QLabel):
        if self._thread is not None and self._thread.isRunning():
            return
        btn.setEnabled(False)
        out.setText("Tekshirilmoqda...")
        out.setStyleSheet(f"color: {C('text_secondary')};")
        t = _CheckThread(mode, data)

        def _done(ok: bool, msg: str):
            btn.setEnabled(True)
            out.setText(("✓ " if ok else "✗ ") + msg)
            out.setStyleSheet(f"color: {C('success') if ok else C('danger')}; font-weight: 600;")

        t.done.connect(_done)
        self._thread = t
        t.start()

    def _test_camera(self):
        url = self._cam_url.text().strip()
        if not url:
            self._cam_result.setText("Avval RTSP URL ni kiriting")
            return
        self._run_check("camera", {"url": url}, self._cam_test_btn, self._cam_result)

    def _test_backend(self):
        self._run_check("backend", {
            "url": self._be_url.text().strip(),
            "login": self._be_login.text().strip(),
            "password": self._be_pass.text().strip(),
        }, self._be_test_btn, self._be_result)

    # ── Saqlash ────────────────────────────────────────────────────────────

    def _first_camera(self) -> dict | None:
        cams = self.cfg.get_cameras()
        return cams[0] if cams else None

    @staticmethod
    def _gpu_name() -> str:
        try:
            import torch
            return torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
        except Exception:
            return ""

    def _summary_html(self) -> str:
        def row(k, v):
            return f"<tr><td style='color:{C('text_muted')};padding:4px 16px 4px 0'>{k}</td><td>{v}</td></tr>"
        be = (self._be_url.text().strip() or "—") if self._be_check.isChecked() else "o'chiq"
        return (
            "<p>Quyidagi sozlamalar saqlanadi. «Boshlash» dan keyin kamera ulanadi.</p><table>"
            + row("Kamera", self._cam_name.text().strip())
            + row("RTSP", self._cam_url.text().strip())
            + row("AI aniqlash", "yoqilgan" if self._ai_check.isChecked() else "o'chiq")
            + row("FaceID", "yoqilgan" if self._face_check.isChecked() else "o'chiq")
            + row("Backend", be)
            + "</table>"
        )

    def _finish(self):
        name, url = self._cam_name.text().strip(), self._cam_url.text().strip()
        cam = self._first_camera()
        if cam is not None:
            self.cfg.update_camera(cam.get("id"), name=name, rtsp_url=url, enabled=True)
        else:
            self.cfg.add_camera(name=name, rtsp_url=url, company_id="")
        self.cfg.update({
            "ai_model_enabled": self._ai_check.isChecked(),
            "faceid_enabled": self._face_check.isChecked(),
            "backend_enabled": self._be_check.isChecked(),
            "backend_url": self._be_url.text().strip(),
            "backend_login": self._be_login.text().strip(),
            "backend_password": self._be_pass.text().strip(),
            "setup_completed": True,
        })
        if not self.cfg.save():
            AppMessageBox.critical(self, "Saqlanmadi",
                                   "Sozlamalar yozilmadi:\n" + (self.cfg.last_save_error or ""))
            return
        self.accept()

    def frame_style(self) -> str:
        return AppMessageBox.frame_style(self) + f"""
            QStackedWidget#wizStack, QWidget#wizPage {{ background: transparent; }}
            QLabel#wizTitle {{ color: {C('text_primary')}; font-size: 20px; font-weight: 800; background: transparent; }}
            QLabel#wizText {{ color: {C('text_secondary')}; font-size: 13px; background: transparent; }}
            QLabel#wizLabel {{ color: {C('text_secondary')}; font-size: 12px; background: transparent; }}
            QLabel#wizHint {{ color: {C('text_muted')}; font-size: 11px; background: transparent; }}
            QLabel#wizResult {{ font-size: 12px; background: transparent; }}
            QWidget#wizInfoRow {{
                background: {C('bg_panel')}; border: 1px solid {C('border')}; border-radius: 10px;
            }}
            QLabel#wizNum {{
                background: {C('accent_dim_2')}; color: {C('accent')}; border-radius: 13px;
                font-size: 12px; font-weight: 800;
            }}
            QLabel#wizRowHead {{ color: {C('text_primary')}; font-size: 13px; font-weight: 700; background: transparent; }}
            QLineEdit {{
                background: {C('input_bg')}; color: {C('text_primary')};
                border: 1px solid {C('input_border')}; border-radius: 8px; padding: 0 10px; font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {C('accent')}; }}
            QCheckBox {{ color: {C('text_primary')}; font-size: 13px; background: transparent; spacing: 8px; }}
        """
