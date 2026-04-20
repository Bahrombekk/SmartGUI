"""
SettingsDialog — sozlamalar oynasi.
Ko'p kamera boshqaruvi, model, Telegram, Backend, Saqlash.
"""

import os
from pathlib import Path

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QCheckBox, QGroupBox,
                              QDoubleSpinBox, QSpinBox, QComboBox,
                              QFileDialog, QTabWidget, QWidget,
                              QMessageBox, QScrollArea, QFrame, QSlider,
                              QListWidget, QListWidgetItem, QAbstractItemView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from app.ui.theme import C


# ── Test Thread ────────────────────────────────────────────────────────────

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
                r = requests.get(
                    f"https://api.telegram.org/bot{token}/getMe", timeout=10
                )
                if r.status_code == 200:
                    name = r.json().get("result", {}).get("first_name", "Bot")
                    self.result.emit(True, f"Bot ulandi: {name}")
                else:
                    self.result.emit(False, f"Xatolik: {r.status_code}")
            except Exception as e:
                self.result.emit(False, str(e))

        elif self.mode == "model":
            model_path = self.data.get("path", "")
            if os.path.exists(model_path):
                size = os.path.getsize(model_path) // (1024 * 1024)
                self.result.emit(True, f"Model topildi ({size} MB)")
            else:
                self.result.emit(False, f"Fayl topilmadi:\n{model_path}")


# ── Kamera tahrirlash dialogi ──────────────────────────────────────────────

class CameraEditDialog(QDialog):
    """Bitta kamerani qo'shish / tahrirlash dialogi."""

    def __init__(self, camera: dict | None = None, parent=None):
        super().__init__(parent)
        self._camera = dict(camera) if camera else {}
        is_edit = bool(camera)
        self.setWindowTitle("Kamera tahrirlash" if is_edit else "Yangi kamera qo'shish")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._setup_ui()
        if is_edit:
            self._load_values()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        # ── Sarlavha ──
        title_lbl = QLabel(
            "Kamera ma'lumotlarini kiriting" if not self._camera
            else f"Kamera #{self._camera.get('id', '?')} ni tahrirlash"
        )
        title_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 14px; font-weight: bold;"
        )
        root.addWidget(title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C('border')};")
        root.addWidget(sep)

        # ── Nomi ──
        root.addWidget(self._field_label("Kamera nomi:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Masalan: Sex № 1, Kirish kamerasi…")
        root.addWidget(self._name_edit)

        # ── RTSP URL ──
        root.addWidget(self._field_label("RTSP URL (kamera IP manzili):"))
        self._rtsp_edit = QLineEdit()
        self._rtsp_edit.setPlaceholderText(
            "rtsp://admin:parol@192.168.1.100:554/Streaming/Channels/101"
        )
        root.addWidget(self._rtsp_edit)

        # ── Company ID ──
        root.addWidget(self._field_label("Company ID:"))
        self._company_edit = QLineEdit()
        self._company_edit.setPlaceholderText(
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )
        root.addWidget(self._company_edit)

        # ── Yoqish/o'chirish ──
        self._enabled_check = QCheckBox("Kamerani yoqish (faollashtirish)")
        self._enabled_check.setChecked(True)
        root.addWidget(self._enabled_check)

        root.addStretch()

        # ── Tugmalar ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("  Saqlash  ")
        save_btn.setFixedHeight(34)
        save_btn.setProperty("accent", True)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('accent')};
                color: white; border: none;
                border-radius: 6px; padding: 0 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {C('accent_hover')}; }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {C('text_secondary')}; font-size: 12px;")
        return lbl

    def _load_values(self):
        self._name_edit.setText(self._camera.get("name", ""))
        self._rtsp_edit.setText(self._camera.get("rtsp_url", ""))
        self._company_edit.setText(self._camera.get("company_id", ""))
        self._enabled_check.setChecked(self._camera.get("enabled", True))

    def _on_save(self):
        name = self._name_edit.text().strip()
        rtsp = self._rtsp_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Xatolik", "Kamera nomi kiritilishi shart.")
            return
        if not rtsp:
            QMessageBox.warning(self, "Xatolik", "RTSP URL kiritilishi shart.")
            return

        self._camera.update({
            "name":       name,
            "rtsp_url":   rtsp,
            "company_id": self._company_edit.text().strip(),
            "enabled":    self._enabled_check.isChecked(),
        })
        self.accept()

    def get_camera(self) -> dict:
        return dict(self._camera)


# ── Asosiy sozlamalar dialogi ──────────────────────────────────────────────

class SettingsDialog(QDialog):
    """Sozlamalar dialogi."""

    settings_saved = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("Sozlamalar")
        self.setMinimumSize(680, 620)
        self.setModal(True)
        self._test_thread = None
        self._setup_ui()
        self._load_values()

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._tabs.addTab(self._make_cameras_tab(),  "📷 Kameralar")
        self._tabs.addTab(self._make_model_tab(),    "🤖 Model")
        self._tabs.addTab(self._make_telegram_tab(), "✈ Telegram")
        self._tabs.addTab(self._make_backend_tab(),  "🌐 Backend API")
        self._tabs.addTab(self._make_storage_tab(),  "💾 Saqlash")
        root.addWidget(self._tabs, 1)

        # Pastki tugmalar
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 10, 16, 12)
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Bekor qilish")
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("  Saqlash  ")
        save_btn.setFixedHeight(34)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('accent')};
                color: white; border: none;
                border-radius: 6px; padding: 0 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {C('accent_hover')}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

    def _scroll_wrap(self, widget: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    # ── Kameralar tab ─────────────────────────────────────────────────────

    def _make_cameras_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Sarlavha + tavsif
        hdr = QHBoxLayout()
        title = QLabel("Kameralar ro'yxati")
        title.setStyleSheet(
            f"color: {C('text_primary')}; font-size: 14px; font-weight: bold;"
        )
        hdr.addWidget(title)
        hdr.addStretch()
        self._cam_count_lbl = QLabel("")
        self._cam_count_lbl.setStyleSheet(
            f"color: {C('accent')}; font-size: 12px; font-weight: bold;"
        )
        hdr.addWidget(self._cam_count_lbl)
        layout.addLayout(hdr)

        info = QLabel(
            "Har bir kamera uchun alohida nom, IP manzil va Company ID kiriting.\n"
            "Maksimal 10 ta kamera qo'shish mumkin."
        )
        info.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Asboblar paneli (Add / Edit / Delete)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        add_btn = QPushButton("+ Qo'shish")
        add_btn.setFixedHeight(30)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('accent_dim')};
                color: {C('accent_light')};
                border: 1px solid {C('accent_dim')};
                border-radius: 5px; padding: 0 14px;
                font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: {C('accent')};
                color: white;
            }}
        """)
        add_btn.clicked.connect(self._add_camera)

        edit_btn = QPushButton("✎ Tahrirlash")
        edit_btn.setFixedHeight(30)
        edit_btn.setProperty("small", True)
        edit_btn.clicked.connect(self._edit_camera)

        del_btn = QPushButton("🗑 O'chirish")
        del_btn.setFixedHeight(30)
        del_btn.setProperty("danger", True)
        del_btn.setProperty("small", True)
        del_btn.clicked.connect(self._delete_camera)

        toolbar.addWidget(add_btn)
        toolbar.addWidget(edit_btn)
        toolbar.addWidget(del_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Kameralar ro'yxati
        self._cam_list = QListWidget()
        self._cam_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._cam_list.setAlternatingRowColors(False)
        self._cam_list.setMinimumHeight(220)
        self._cam_list.itemDoubleClicked.connect(self._edit_camera)
        layout.addWidget(self._cam_list)

        # Izoh
        note = QLabel(
            "💡 Yashil doira — kamera faol. Kulrang — o'chirilgan. "
            "Ikki marta bosish — tahrirlash."
        )
        note.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch()
        return w

    def _refresh_cam_list(self):
        """Kameralar ro'yxatini qayta chizish."""
        self._cam_list.clear()
        cameras = self.cfg.get_cameras()
        for cam in cameras:
            enabled = cam.get("enabled", True)
            dot     = "🟠" if enabled else "⚫"
            name    = cam.get("name", "—")
            rtsp    = cam.get("rtsp_url", "")
            company = cam.get("company_id", "")

            # IP'ni ajratib olish (ko'rsatish uchun)
            ip_display = ""
            if "@" in rtsp:
                try:
                    ip_display = rtsp.split("@")[1].split(":")[0]
                except Exception:
                    ip_display = rtsp[:30]
            elif rtsp.startswith("rtsp://"):
                ip_display = rtsp[7:].split("/")[0].split(":")[0]
            else:
                ip_display = rtsp[:30]

            company_short = company[:18] + "…" if len(company) > 20 else company

            text = (
                f"{dot}  {name}\n"
                f"     IP: {ip_display}   |   Company: {company_short or '—'}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, cam.get("id"))
            item.setForeground(
                __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                    C("text_primary") if enabled else C("text_muted")
                )
            )
            self._cam_list.addItem(item)

        count = len(cameras)
        enabled_count = sum(1 for c in cameras if c.get("enabled", True))
        self._cam_count_lbl.setText(
            f"{count} ta kamera  ({enabled_count} ta faol)"
        )

    def _selected_camera_id(self) -> int | None:
        item = self._cam_list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _add_camera(self):
        cameras = self.cfg.get_cameras()
        if len(cameras) >= 10:
            QMessageBox.warning(self, "Limit", "Maksimal 10 ta kamera qo'shish mumkin.")
            return
        dlg = CameraEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cam = dlg.get_camera()
            try:
                self.cfg.add_camera(
                    name=cam["name"],
                    rtsp_url=cam["rtsp_url"],
                    company_id=cam.get("company_id", ""),
                    enabled=cam.get("enabled", True),
                )
            except ValueError as e:
                QMessageBox.warning(self, "Xatolik", str(e))
            self._refresh_cam_list()

    def _edit_camera(self):
        cam_id = self._selected_camera_id()
        if cam_id is None:
            QMessageBox.information(self, "Tanlang",
                                    "Tahrirlash uchun kamerani tanlang.")
            return
        cam = self.cfg.get_camera_by_id(cam_id)
        if not cam:
            return
        dlg = CameraEditDialog(camera=cam, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_camera()
            self.cfg.update_camera(
                cam_id,
                name=updated["name"],
                rtsp_url=updated["rtsp_url"],
                company_id=updated.get("company_id", ""),
                enabled=updated.get("enabled", True),
            )
            self._refresh_cam_list()

    def _delete_camera(self):
        cam_id = self._selected_camera_id()
        if cam_id is None:
            QMessageBox.information(self, "Tanlang",
                                    "O'chirish uchun kamerani tanlang.")
            return
        cam = self.cfg.get_camera_by_id(cam_id)
        name = cam.get("name", f"ID:{cam_id}") if cam else f"ID:{cam_id}"
        reply = QMessageBox.question(
            self, "O'chirish tasdiqi",
            f'"{name}" kamerasini o\'chirmoqchimisiz?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if not self.cfg.remove_camera(cam_id):
                QMessageBox.warning(self, "Xatolik",
                                    "Kamida 1 ta kamera bo'lishi shart.")
            else:
                self._refresh_cam_list()

    # ── Model tab ─────────────────────────────────────────────────────────

    def _make_model_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        grp = QGroupBox("YOLO Model")
        g = QVBoxLayout(grp)
        g.setSpacing(10)

        g.addWidget(QLabel("Model fayli (.pt):"))
        h = QHBoxLayout()
        self._model_edit = QLineEdit()
        h.addWidget(self._model_edit, 1)
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(36)
        browse_btn.clicked.connect(self._browse_model)
        h.addWidget(browse_btn)
        g.addLayout(h)

        self._test_model_btn = QPushButton("Model tekshirish")
        self._test_model_btn.clicked.connect(self._test_model)
        self._test_model_result = QLabel("")
        g.addWidget(self._test_model_btn)
        g.addWidget(self._test_model_result)

        conf_row = QHBoxLayout()
        self._conf_spin = QDoubleSpinBox()
        self._conf_spin.setRange(0.1, 0.99)
        self._conf_spin.setSingleStep(0.05)
        self._conf_spin.setDecimals(2)
        self._conf_spin.setValue(0.6)
        conf_row.addWidget(QLabel("Ishonch chegarasi:"))
        conf_row.addWidget(self._conf_spin)
        conf_row.addStretch()
        g.addLayout(conf_row)

        imgsz_row = QHBoxLayout()
        self._imgsz_combo = QComboBox()
        self._imgsz_combo.addItems(["416", "640", "1024", "1280"])
        self._imgsz_combo.setCurrentText("1024")
        imgsz_row.addWidget(QLabel("YOLO imgsz:"))
        imgsz_row.addWidget(self._imgsz_combo)
        imgsz_row.addStretch()
        g.addLayout(imgsz_row)

        self._gpu_check = QCheckBox("GPU ishlatish (CUDA)")
        self._half_check = QCheckBox("Half precision (FP16)")
        g.addWidget(self._gpu_check)
        g.addWidget(self._half_check)

        pn_row = QHBoxLayout()
        self._proc_n_spin = QSpinBox()
        self._proc_n_spin.setRange(1, 5)
        self._proc_n_spin.setValue(1)
        pn_row.addWidget(QLabel("Har N ta frameni qayta ishlash:"))
        pn_row.addWidget(self._proc_n_spin)
        pn_row.addStretch()
        g.addLayout(pn_row)

        layout.addWidget(grp)
        layout.addStretch()
        return self._scroll_wrap(w)

    # ── Telegram tab ──────────────────────────────────────────────────────

    def _make_telegram_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        grp = QGroupBox("Telegram Bot")
        g = QVBoxLayout(grp)
        g.setSpacing(10)

        self._tg_enabled = QCheckBox("Telegram xabarnomani yoqish")
        g.addWidget(self._tg_enabled)

        g.addWidget(QLabel("Bot Token:"))
        self._tg_token = QLineEdit()
        self._tg_token.setPlaceholderText("1234567890:AAH...")
        self._tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        g.addWidget(self._tg_token)

        show_token = QCheckBox("Tokenni ko'rsatish")
        show_token.stateChanged.connect(
            lambda s: self._tg_token.setEchoMode(
                QLineEdit.EchoMode.Normal if s else QLineEdit.EchoMode.Password
            )
        )
        g.addWidget(show_token)

        g.addWidget(QLabel("Chat ID lar (vergul bilan):"))
        self._tg_chat_ids = QLineEdit()
        self._tg_chat_ids.setPlaceholderText("123456789, 987654321")
        g.addWidget(self._tg_chat_ids)

        self._test_tg_btn = QPushButton("Telegram ulanishni tekshirish")
        self._test_tg_btn.clicked.connect(self._test_telegram)
        g.addWidget(self._test_tg_btn)

        self._tg_result = QLabel("")
        self._tg_result.setWordWrap(True)
        g.addWidget(self._tg_result)

        layout.addWidget(grp)
        layout.addStretch()
        return self._scroll_wrap(w)

    # ── Backend tab ───────────────────────────────────────────────────────

    def _make_backend_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        grp = QGroupBox("Backend API")
        g = QVBoxLayout(grp)
        g.setSpacing(10)

        self._be_enabled = QCheckBox("Backend API ni yoqish")
        g.addWidget(self._be_enabled)

        g.addWidget(QLabel("API URL:"))
        self._be_url = QLineEdit()
        self._be_url.setPlaceholderText("https://example.com/api/camera/create")
        g.addWidget(self._be_url)

        g.addWidget(QLabel("Login:"))
        self._be_login = QLineEdit()
        g.addWidget(self._be_login)

        g.addWidget(QLabel("Parol:"))
        self._be_pass = QLineEdit()
        self._be_pass.setEchoMode(QLineEdit.EchoMode.Password)
        g.addWidget(self._be_pass)

        note = QLabel(
            "ℹ️  Company ID har bir kamera uchun alohida 📷 Kameralar tabida sozlanadi."
        )
        note.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px;")
        note.setWordWrap(True)
        g.addWidget(note)

        layout.addWidget(grp)
        layout.addStretch()
        return self._scroll_wrap(w)

    # ── Saqlash tab ───────────────────────────────────────────────────────

    def _make_storage_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        grp = QGroupBox("Fayl saqlash")
        g = QVBoxLayout(grp)
        g.setSpacing(10)

        self._save_check = QCheckBox("Buzilish rasmlarini saqlash")
        g.addWidget(self._save_check)

        g.addWidget(QLabel("Rasmlar papkasi:"))
        h = QHBoxLayout()
        self._viol_dir_edit = QLineEdit()
        self._viol_dir_edit.setPlaceholderText("violations/  (bo'sh = SmartGUI/violations/)")
        h.addWidget(self._viol_dir_edit, 1)
        browse_dir = QPushButton("...")
        browse_dir.setFixedWidth(36)
        browse_dir.clicked.connect(self._browse_dir)
        h.addWidget(browse_dir)
        g.addLayout(h)

        days_row = QHBoxLayout()
        self._keep_days_spin = QSpinBox()
        self._keep_days_spin.setRange(1, 365)
        self._keep_days_spin.setValue(7)
        days_row.addWidget(QLabel("Fayllarni saqlash muddati (kun):"))
        days_row.addWidget(self._keep_days_spin)
        days_row.addStretch()
        g.addLayout(days_row)

        layout.addWidget(grp)
        layout.addStretch()
        return self._scroll_wrap(w)

    # ── Qiymatlarni yuklash / saqlash ─────────────────────────────────────

    def _load_values(self):
        # Kameralar
        self._refresh_cam_list()

        # Model
        c = self.cfg
        self._model_edit.setText(c.get("model_path", ""))
        self._conf_spin.setValue(float(c.get("confidence", 0.6)))
        imgsz = str(c.get("yolo_imgsz", 1024))
        idx = self._imgsz_combo.findText(imgsz)
        self._imgsz_combo.setCurrentIndex(idx if idx >= 0 else 2)
        self._gpu_check.setChecked(bool(c.get("use_gpu", True)))
        self._half_check.setChecked(bool(c.get("half_precision", True)))
        self._proc_n_spin.setValue(int(c.get("process_every_n", 1)))

        # Telegram
        self._tg_enabled.setChecked(bool(c.get("telegram_enabled", True)))
        self._tg_token.setText(c.get("telegram_token", ""))
        self._tg_chat_ids.setText(", ".join(c.telegram_chat_ids))

        # Backend
        self._be_enabled.setChecked(bool(c.get("backend_enabled", False)))
        self._be_url.setText(c.get("backend_url", ""))
        self._be_login.setText(c.get("backend_login", ""))
        self._be_pass.setText(c.get("backend_password", ""))

        # Saqlash
        self._save_check.setChecked(bool(c.get("save_violations", True)))
        self._viol_dir_edit.setText(str(c.get("violations_dir", "")))
        self._keep_days_spin.setValue(int(c.get("keep_files_days", 7)))

    def _save(self):
        ids_raw  = self._tg_chat_ids.text()
        chat_ids = [x.strip() for x in ids_raw.split(",") if x.strip()]

        self.cfg.update({
            "model_path":       self._model_edit.text().strip(),
            "confidence":       self._conf_spin.value(),
            "yolo_imgsz":       int(self._imgsz_combo.currentText()),
            "use_gpu":          self._gpu_check.isChecked(),
            "half_precision":   self._half_check.isChecked(),
            "process_every_n":  self._proc_n_spin.value(),

            "telegram_enabled":  self._tg_enabled.isChecked(),
            "telegram_token":    self._tg_token.text().strip(),
            "telegram_chat_ids": chat_ids,

            "backend_enabled":   self._be_enabled.isChecked(),
            "backend_url":       self._be_url.text().strip(),
            "backend_login":     self._be_login.text().strip(),
            "backend_password":  self._be_pass.text().strip(),

            "save_violations":   self._save_check.isChecked(),
            "violations_dir":    self._viol_dir_edit.text().strip(),
            "keep_files_days":   self._keep_days_spin.value(),
        })
        self.cfg.save()
        self.settings_saved.emit()

        QMessageBox.information(
            self, "Saqlandi",
            "Sozlamalar saqlandi.\n"
            "O'zgarishlar kuchga kirishi uchun kameralar qayta ishga tushiriladi."
        )
        self.accept()

    # ── Yordamchi ─────────────────────────────────────────────────────────

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Model tanlash", "", "PyTorch Model (*.pt);;Barcha fayllar (*)"
        )
        if path:
            self._model_edit.setText(path)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Rasmlar papkasi")
        if path:
            self._viol_dir_edit.setText(path)

    def _test_model(self):
        self._test_model_result.setText("Tekshirilmoqda...")
        self._test_model_result.setStyleSheet(f"color: {C('text_muted')};")
        t = _TestThread("model", {"path": self._model_edit.text().strip()})
        t.result.connect(self._on_model_test_result)
        self._test_thread = t
        t.start()

    def _on_model_test_result(self, ok: bool, msg: str):
        color = C("success") if ok else C("danger")
        self._test_model_result.setText(("✓ " if ok else "✗ ") + msg)
        self._test_model_result.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _test_telegram(self):
        self._tg_result.setText("Ulanish tekshirilmoqda...")
        self._tg_result.setStyleSheet(f"color: {C('text_muted')};")
        ids_raw  = self._tg_chat_ids.text()
        chat_ids = [x.strip() for x in ids_raw.split(",") if x.strip()]
        t = _TestThread("telegram", {
            "token":    self._tg_token.text().strip(),
            "chat_ids": chat_ids,
        })
        t.result.connect(self._on_tg_test_result)
        self._test_thread = t
        t.start()

    def _on_tg_test_result(self, ok: bool, msg: str):
        color = C("success") if ok else C("danger")
        self._tg_result.setText(("✓ " if ok else "✗ ") + msg)
        self._tg_result.setStyleSheet(f"color: {color}; font-size: 12px;")
