"""
SettingsDialog — sozlamalar oynasi.
Kamera, model, Telegram, Backend, saqlash guruhlaridan iborat.
"""

import os
from pathlib import Path

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QCheckBox, QGroupBox,
                              QDoubleSpinBox, QSpinBox, QComboBox,
                              QFileDialog, QTabWidget, QWidget,
                              QMessageBox, QScrollArea, QFrame, QSlider)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from app.utils.theme import C


class _TestThread(QThread):
    """Kamera yoki Telegram test uchun arxa fon thread."""
    result = pyqtSignal(bool, str)

    def __init__(self, mode: str, data: dict):
        super().__init__()
        self.mode = mode
        self.data = data

    def run(self):
        if self.mode == "telegram":
            try:
                import requests
                token  = self.data.get("token", "")
                chat_ids = self.data.get("chat_ids", [])
                if not token:
                    self.result.emit(False, "Token kiritilmagan")
                    return
                r = requests.get(
                    f"https://api.telegram.org/bot{token}/getMe", timeout=10
                )
                if r.status_code == 200:
                    name = r.json().get("result", {}).get("first_name", "Bot")
                    self.result.emit(True, f"Bot ulanди: {name}")
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


class SettingsDialog(QDialog):
    """Sozlamalar dialogi."""

    settings_saved = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("Sozlamalar")
        self.setMinimumSize(600, 580)
        self.setModal(True)
        self._test_thread = None
        self._setup_ui()
        self._load_values()

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._tabs.addTab(self._make_camera_tab(),   "Kamera")
        self._tabs.addTab(self._make_model_tab(),    "Model")
        self._tabs.addTab(self._make_telegram_tab(), "Telegram")
        self._tabs.addTab(self._make_backend_tab(),  "Backend API")
        self._tabs.addTab(self._make_storage_tab(),  "Saqlash")
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

        save_btn = QPushButton("Saqlash")
        save_btn.setFixedHeight(34)
        save_btn.setProperty("accent", True)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C('accent')};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 24px;
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

    # ── Kamera tab ────────────────────────────────────────────────────────

    def _make_camera_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        grp = QGroupBox("RTSP Kamera")
        g   = QVBoxLayout(grp)
        g.setSpacing(10)

        g.addWidget(QLabel("RTSP URL:"))
        self._rtsp_edit = QLineEdit()
        self._rtsp_edit.setPlaceholderText("rtsp://user:pass@192.168.1.100:554/stream")
        g.addWidget(self._rtsp_edit)

        g.addWidget(QLabel("Kamera nomi:"))
        self._cam_name_edit = QLineEdit()
        g.addWidget(self._cam_name_edit)

        h = QHBoxLayout()
        h.setSpacing(8)
        reconnect_lbl = QLabel("Qayta ulanish kechikishi (s):")
        self._reconnect_spin = QSpinBox()
        self._reconnect_spin.setRange(1, 30)
        self._reconnect_spin.setValue(3)
        h.addWidget(reconnect_lbl)
        h.addWidget(self._reconnect_spin)
        h.addStretch()
        g.addLayout(h)

        h2 = QHBoxLayout()
        max_lbl = QLabel("Maksimal qayta ulanish:")
        self._max_reconnect_spin = QSpinBox()
        self._max_reconnect_spin.setRange(1, 100)
        self._max_reconnect_spin.setValue(20)
        h2.addWidget(max_lbl)
        h2.addWidget(self._max_reconnect_spin)
        h2.addStretch()
        g.addLayout(h2)

        layout.addWidget(grp)
        layout.addStretch()
        return self._scroll_wrap(w)

    # ── Model tab ─────────────────────────────────────────────────────────

    def _make_model_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # SmartHelmet yo'li
        sh_grp = QGroupBox("SmartHelmet loyihasi")
        sh_layout = QVBoxLayout(sh_grp)
        sh_layout.addWidget(QLabel("SmartHelmet papkasi yo'li:"))
        h_sh = QHBoxLayout()
        self._sh_path_edit = QLineEdit()
        h_sh.addWidget(self._sh_path_edit, 1)
        sh_browse = QPushButton("...")
        sh_browse.setFixedWidth(36)
        sh_browse.clicked.connect(self._browse_sh)
        h_sh.addWidget(sh_browse)
        sh_layout.addLayout(h_sh)
        layout.addWidget(sh_grp)

        # Model
        grp = QGroupBox("YOLO Model")
        g   = QVBoxLayout(grp)
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

        # Confidence
        conf_row = QHBoxLayout()
        conf_lbl = QLabel("Ishonch chegarasi:")
        self._conf_spin = QDoubleSpinBox()
        self._conf_spin.setRange(0.1, 0.99)
        self._conf_spin.setSingleStep(0.05)
        self._conf_spin.setDecimals(2)
        self._conf_spin.setValue(0.6)
        conf_row.addWidget(conf_lbl)
        conf_row.addWidget(self._conf_spin)
        conf_row.addStretch()
        g.addLayout(conf_row)

        # IMGSZ
        imgsz_row = QHBoxLayout()
        imgsz_lbl = QLabel("YOLO imgsz:")
        self._imgsz_combo = QComboBox()
        self._imgsz_combo.addItems(["416", "640", "1024", "1280"])
        self._imgsz_combo.setCurrentText("1024")
        imgsz_row.addWidget(imgsz_lbl)
        imgsz_row.addWidget(self._imgsz_combo)
        imgsz_row.addStretch()
        g.addLayout(imgsz_row)

        # GPU
        self._gpu_check = QCheckBox("GPU ishlatish (CUDA)")
        self._half_check = QCheckBox("Half precision (FP16) — GPU tezroq")
        g.addWidget(self._gpu_check)
        g.addWidget(self._half_check)

        # Process every N
        pn_row = QHBoxLayout()
        pn_lbl = QLabel("Har N ta frameni qayta ishlash:")
        self._proc_n_spin = QSpinBox()
        self._proc_n_spin.setRange(1, 5)
        self._proc_n_spin.setValue(1)
        pn_row.addWidget(pn_lbl)
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
        g   = QVBoxLayout(grp)
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

        g.addWidget(QLabel("Chat ID lar (vergul bilan ajratiing):"))
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
        g   = QVBoxLayout(grp)
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

        g.addWidget(QLabel("Company ID:"))
        self._be_company = QLineEdit()
        g.addWidget(self._be_company)

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
        g   = QVBoxLayout(grp)
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
        days_lbl = QLabel("Fayllarni saqlash muddati (kun):")
        self._keep_days_spin = QSpinBox()
        self._keep_days_spin.setRange(1, 365)
        self._keep_days_spin.setValue(7)
        days_row.addWidget(days_lbl)
        days_row.addWidget(self._keep_days_spin)
        days_row.addStretch()
        g.addLayout(days_row)

        layout.addWidget(grp)
        layout.addStretch()
        return self._scroll_wrap(w)

    # ── Qiymatlarni yuklash / saqlash ─────────────────────────────────────

    def _load_values(self):
        c = self.cfg
        self._rtsp_edit.setText(c.get("rtsp_url", ""))
        self._cam_name_edit.setText(c.get("camera_name", ""))
        self._reconnect_spin.setValue(int(c.get("reconnect_delay", 3)))
        self._max_reconnect_spin.setValue(int(c.get("max_reconnects", 20)))

        self._sh_path_edit.setText(c.get("smarthelmet_path", ""))
        self._model_edit.setText(c.get("model_path", ""))
        self._conf_spin.setValue(float(c.get("confidence", 0.6)))
        imgsz = str(c.get("yolo_imgsz", 1024))
        idx = self._imgsz_combo.findText(imgsz)
        self._imgsz_combo.setCurrentIndex(idx if idx >= 0 else 2)
        self._gpu_check.setChecked(bool(c.get("use_gpu", True)))
        self._half_check.setChecked(bool(c.get("half_precision", True)))
        self._proc_n_spin.setValue(int(c.get("process_every_n", 1)))

        self._tg_enabled.setChecked(bool(c.get("telegram_enabled", True)))
        self._tg_token.setText(c.get("telegram_token", ""))
        ids = c.telegram_chat_ids
        self._tg_chat_ids.setText(", ".join(ids))

        self._be_enabled.setChecked(bool(c.get("backend_enabled", False)))
        self._be_url.setText(c.get("backend_url", ""))
        self._be_login.setText(c.get("backend_login", ""))
        self._be_pass.setText(c.get("backend_password", ""))
        self._be_company.setText(c.get("company_id", ""))

        self._save_check.setChecked(bool(c.get("save_violations", True)))
        self._viol_dir_edit.setText(str(c.get("violations_dir", "")))
        self._keep_days_spin.setValue(int(c.get("keep_files_days", 7)))

    def _save(self):
        ids_raw = self._tg_chat_ids.text()
        chat_ids = [x.strip() for x in ids_raw.split(",") if x.strip()]

        self.cfg.update({
            "rtsp_url":          self._rtsp_edit.text().strip(),
            "camera_name":       self._cam_name_edit.text().strip(),
            "reconnect_delay":   self._reconnect_spin.value(),
            "max_reconnects":    self._max_reconnect_spin.value(),

            "smarthelmet_path":  self._sh_path_edit.text().strip(),
            "model_path":        self._model_edit.text().strip(),
            "confidence":        self._conf_spin.value(),
            "yolo_imgsz":        int(self._imgsz_combo.currentText()),
            "use_gpu":           self._gpu_check.isChecked(),
            "half_precision":    self._half_check.isChecked(),
            "process_every_n":   self._proc_n_spin.value(),

            "telegram_enabled":  self._tg_enabled.isChecked(),
            "telegram_token":    self._tg_token.text().strip(),
            "telegram_chat_ids": chat_ids,

            "backend_enabled":   self._be_enabled.isChecked(),
            "backend_url":       self._be_url.text().strip(),
            "backend_login":     self._be_login.text().strip(),
            "backend_password":  self._be_pass.text().strip(),
            "company_id":        self._be_company.text().strip(),

            "save_violations":   self._save_check.isChecked(),
            "violations_dir":    self._viol_dir_edit.text().strip(),
            "keep_files_days":   self._keep_days_spin.value(),
        })
        self.cfg.save()
        self.settings_saved.emit()

        QMessageBox.information(
            self, "Saqlandi",
            "Sozlamalar saqlandi.\n"
            "O'zgarishlar kuchga kirishi uchun detection qayta ishga tushiriladi."
        )
        self.accept()

    # ── Yordamchi ─────────────────────────────────────────────────────────

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Model tanlash", "", "PyTorch Model (*.pt);;Barcha fayllar (*)"
        )
        if path:
            self._model_edit.setText(path)

    def _browse_sh(self):
        path = QFileDialog.getExistingDirectory(self, "SmartHelmet papkasi")
        if path:
            self._sh_path_edit.setText(path)

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
