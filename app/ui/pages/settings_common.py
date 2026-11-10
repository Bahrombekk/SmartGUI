"""
Sozlamalar uchun umumiy qismlar: ulanish testi thread'i, kamera maydonlarini
tekshirish va kamerani qo'shish/tahrirlash dialogi.
"""

import os
import re

from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QComboBox, QMessageBox
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from app.ui.widgets.frameless import FramedDialog
from app.ui.widgets.app_dialog import AppMessageBox
from app.shared.paths import resolve_model_path


# ── Ulanish testi ─────────────────────────────────────────────────────────────

class _TestThread(QThread):
    result = pyqtSignal(bool, str)

    def __init__(self, mode: str, data: dict):
        super().__init__()
        self.mode = mode
        self.data = data

    def run(self):
        if self.mode == "telegram":
            try:
                import requests
                token = self.data.get("token", "")
                if not token:
                    self.result.emit(False, "Token kiritilmagan")
                    return
                chat_ids = self.data.get("chat_ids", [])
                r = requests.get(
                    f"https://api.telegram.org/bot{token}/getMe", timeout=10
                )
                if r.status_code != 200:
                    self.result.emit(False, f"Xatolik: {r.status_code}")
                    return
                name = r.json().get("result", {}).get("first_name", "Bot")
                if chat_ids:
                    msg = requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        data={"chat_id": chat_ids[0], "text": "SmartHelmet test xabari"},
                        timeout=10,
                    )
                    if msg.status_code != 200:
                        self.result.emit(False, f"Bot ulandi, lekin chat test xato: {msg.status_code}")
                        return
                self.result.emit(True, f"Bot ulandi: {name}")
            except Exception as e:
                self.result.emit(False, str(e))
        elif self.mode == "backend":
            # Faqat autentifikatsiya — backend'da hech qanday yozuv yaratilmaydi
            try:
                import requests
                from app.infrastructure.notifications.backend_client import BackendClient

                client = BackendClient(self.data.get("url", ""), self.data.get("login", ""),
                                       self.data.get("password", ""))
                if not client.base_url:
                    self.result.emit(False, "API URL kiritilmagan")
                    return
                if not client._access_token(requests):
                    self.result.emit(False, "Login javobida token yo'q")
                    return
                msg = f"Login muvaffaqiyatli: {client.base_url}"
                if client.base_url.startswith("http://"):
                    msg += "\nDiqqat: http:// — parol shifrlanmasdan ketadi, https:// tavsiya etiladi."
                bad = self.data.get("bad_company_ids") or []
                if bad:
                    msg += ("\nDiqqat: bu kameralarda Kompaniya ID UUID emas, yozuvlar kompaniyaga "
                            "bog'lanmaydi: " + ", ".join(bad))
                self.result.emit(True, msg)
            except Exception as e:
                self.result.emit(False, f"Backend'ga ulanib bo'lmadi: {e}")
        elif self.mode == "model":
            model_path = str(resolve_model_path(self.data.get("path", "")))
            if not os.path.exists(model_path):
                self.result.emit(False, f"Fayl topilmadi:\n{model_path}")
                return
            try:
                import numpy as np
                from app.infrastructure.detection.sarbon_backend import load_model

                model = load_model(model_path)
                dummy = np.zeros((320, 320, 3), dtype=np.uint8)
                model.predict([dummy], imgsz=320, conf=0.25, verbose=False, max_det=1, device="cpu")
                size = os.path.getsize(model_path) // (1024 * 1024)
                self.result.emit(True, f"Model yuklandi va sinov tekshiruvidan o'tdi ({size} MB)")
            except Exception as e:
                self.result.emit(False, f"Model yuklanmadi: {e}")


# тФАтФА Kamera tahrirlash dialogi тФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФАтФА


# ── Kamera maydonlari va tahrirlash dialogi ─────────────────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_STREAM_SCHEMES = ("rtsp://", "rtsps://", "http://", "https://", "rtmp://")


def validate_camera_fields(name: str, rtsp: str, company_id: str,
                           cameras: list, exclude_id=None) -> tuple[list[str], list[str]]:
    """Kamera maydonlarini tekshiradi -> (xatolar, ogohlantirishlar)."""
    errors: list[str] = []
    warnings: list[str] = []
    others = [c for c in cameras if c.get("id") != exclude_id]
    if not name:
        errors.append("Kamera nomi kiritilishi shart.")
    elif any(str(c.get("name", "")).strip().lower() == name.lower() for c in others):
        errors.append(f'"{name}" nomli kamera allaqachon bor.')
    if not rtsp:
        errors.append("RTSP URL kiritilishi shart.")
    elif not rtsp.lower().startswith(_STREAM_SCHEMES):
        errors.append("RTSP URL rtsp:// (yoki http://) bilan boshlanishi kerak.")
    elif any(str(c.get("rtsp_url", "")).strip() == rtsp for c in others):
        dup = next(c for c in others if str(c.get("rtsp_url", "")).strip() == rtsp)
        warnings.append(f'Bu RTSP URL "{dup.get("name", "?")}" kamerasida ham ishlatilgan.')
    if company_id and not _UUID_RE.match(company_id):
        warnings.append(
            "Kompaniya ID UUID formatida emas (masalan 6b1e6e0a-4c3a-4b7e-9c51-5afe20e0a001) — "
            "backend'da yozuvlar kompaniyaga bog'lanmaydi."
        )
    return errors, warnings


def confirm_camera_fields(parent, name, rtsp, company_id, cameras, exclude_id=None) -> bool:
    """Xato bo'lsa ko'rsatadi va False; ogohlantirish bo'lsa tasdiq so'raydi."""
    errors, warnings = validate_camera_fields(name, rtsp, company_id, cameras, exclude_id)
    if errors:
        AppMessageBox.warning(parent, "Kamera ma'lumotida xato", "\n".join(errors))
        return False
    if warnings:
        reply = AppMessageBox.question(
            parent, "Diqqat",
            "\n\n".join(warnings) + "\n\nBaribir saqlansinmi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes
    return True


class CameraEditDialog(FramedDialog):
    def __init__(self, camera: dict | None = None, departments: list | None = None,
                 parent=None, existing_cameras: list | None = None):
        super().__init__(parent)
        self._camera = dict(camera) if camera else {}
        self._departments = departments or []
        self._existing_cameras = existing_cameras or []
        is_edit = bool(camera)
        self.setWindowTitle("Kamera tahrirlash" if is_edit else "Yangi kamera qo'shish")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._setup_ui()
        if is_edit:
            self._load_values()

    def _setup_ui(self):
        from app.ui import fz
        from app.ui.widgets.frameless import dialog_button, dialog_footer, field_label
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        root = QVBoxLayout()
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(0)

        hint = fz.label(
            "Kamera RTSP manzili va bo‘limini kiriting" if not self._camera
            else f"CAM-{int(self._camera.get('id', 0) or 0):02d} · ma’lumotlarni tahrirlash",
            13, 400, fz.MUTED)
        root.addWidget(hint)
        root.addSpacing(16)

        def field(title: str, widget, gap_after: int = 14):
            root.addWidget(field_label(title))
            root.addSpacing(6)
            root.addWidget(widget)
            root.addSpacing(gap_after)

        self._department_combo = QComboBox()
        self._department_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for dep in self._departments:
            self._department_combo.addItem(dep.get("name", "Bo'lim"), dep.get("id"))
        field("Bo‘lim", self._department_combo)

        self._name_edit = fz.line_edit("Masalan: Sex 1, Kirish kamerasi", h=36, px=13)
        field("Kamera nomi", self._name_edit)

        self._rtsp_edit = fz.line_edit("rtsp://admin:parol@192.168.1.100:554/Streaming/Channels/101",
                                       mono=True, h=36, px=12.5)
        field("RTSP manzil", self._rtsp_edit)

        self._company_edit = fz.line_edit("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", mono=True, h=36, px=12.5)
        field("Kompaniya ID", self._company_edit, gap_after=16)

        # Faollik — Figma toggle qatori
        row = QHBoxLayout()
        row.setSpacing(12)
        txt = QVBoxLayout()
        txt.setSpacing(3)
        txt.addWidget(fz.label("Kamerani yoqish", 13, 500, fz.TEXT))
        txt.addWidget(fz.label("O‘chirilsa oqim va AI tahlili to‘xtaydi", 12, 400, fz.MUTED))
        row.addLayout(txt, 1)
        self._enabled_check = fz.Toggle(True)
        row.addWidget(self._enabled_check, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(row)
        outer.addLayout(root)
        outer.addStretch(1)

        footer, btn_row = dialog_footer()
        cancel_btn = dialog_button("Bekor qilish", "ghost")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = dialog_button("Saqlash" if self._camera else "Qo‘shish", "primary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        outer.addWidget(footer)
        self.setMinimumWidth(500)

    def _load_values(self):
        self._name_edit.setText(self._camera.get("name", ""))
        self._rtsp_edit.setText(self._camera.get("rtsp_url", ""))
        self._company_edit.setText(self._camera.get("company_id", ""))
        self._enabled_check.setChecked(self._camera.get("enabled", True))
        idx = self._department_combo.findData(self._camera.get("department_id"))
        if idx >= 0:
            self._department_combo.setCurrentIndex(idx)

    def _on_save(self):
        name = self._name_edit.text().strip()
        rtsp = self._rtsp_edit.text().strip()
        company = self._company_edit.text().strip()
        if not confirm_camera_fields(self, name, rtsp, company, self._existing_cameras,
                                     exclude_id=self._camera.get("id")):
            return
        self._camera.update({
            "name": name,
            "rtsp_url": rtsp,
            "company_id": company,
            "department_id": self._department_combo.currentData(),
            "enabled": self._enabled_check.isChecked(),
        })
        self.accept()

    def get_camera(self) -> dict:
        return dict(self._camera)
