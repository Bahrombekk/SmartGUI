"""
ConfigManager — settings.json ni o'qish/yozish.
Barcha GUI sozlamalari shu yerda saqlanadi.
"""

import json
import os
from pathlib import Path

# SmartHelmet loyihasi joylashuvi (default)
SMARTHELMET_DEFAULT = r"C:\Users\User\Desktop\SmartHelmet"

DEFAULT_SETTINGS = {
    # SmartHelmet yo'li (import uchun)
    "smarthelmet_path": SMARTHELMET_DEFAULT,

    # Kamera
    "rtsp_url": "rtsp://admin:qwerty12345@192.168.25.114:554/Streaming/Channels/101",
    "camera_name": "Elekravoz sex ichki",
    "reconnect_delay": 3,
    "max_reconnects": 20,

    # Model
    "model_path": r"C:\Users\User\Desktop\SmartHelmet\runs\detect\train14\weights\best.pt",
    "confidence": 0.6,
    "yolo_imgsz": 1024,
    "use_gpu": True,
    "half_precision": True,
    "process_every_n": 1,

    # Detection
    "helmet_zone_bottom": 0.35,
    "helmet_iou_threshold": 0.15,
    "no_helmet_iou_threshold": 0.05,
    "confirmation_window": 10,
    "confirmation_threshold": 10,
    "violation_cooldown": 10,

    # Telegram
    "telegram_enabled": True,
    "telegram_token": "7688030501:AAH-vPO2a7FIu0oDGUzHpJa3Je7LASi505M",
    "telegram_chat_ids": ["6036366867", "18367996"],

    # Backend API
    "backend_enabled": True,
    "backend_url": "https://ai-project.das-uty.uz/api/camera/create",
    "backend_login": "kaska",
    "backend_password": "Kaska2025",
    "company_id": "61169935-7269-4782-a5d2-bdd42ef28bb0",

    # Saqlash
    "save_violations": True,
    "violations_dir": "",   # bo'sh = SmartGUI/violations/
    "keep_files_days": 7,

    # Polygon
    "use_polygon": False,
    "polygon_points": [],

    # Interfeys
    "theme": "dark",
    "language": "uz",
    "display_max_width": 1280,
    "show_fps": True,
    "show_stats": True,

    # Tracker
    "tracker_config": "",   # bo'sh = SmartHelmet config ishlatiladi
}


class ConfigManager:
    """Ilova sozlamalarini boshqaruvchi klass."""

    def __init__(self, settings_file: str = "settings.json"):
        self.settings_file = Path(settings_file)
        self._settings: dict = {}
        self._load()

    # ── Yuklash / Saqlash ──────────────────────────────────────────────────

    def _load(self):
        """settings.json dan yuklash. Yo'q bo'lsa — default."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Default ustiga saved qo'yish (yangi kalitlar uchun)
                self._settings = {**DEFAULT_SETTINGS, **saved}
            except Exception as e:
                print(f"[ConfigManager] settings.json o'qishda xatolik: {e}")
                self._settings = dict(DEFAULT_SETTINGS)
        else:
            self._settings = dict(DEFAULT_SETTINGS)
            self.save()

    def save(self):
        """Joriy sozlamalarni settings.json ga yozish."""
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Saqlashda xatolik: {e}")

    # ── Get / Set ──────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        return self._settings.get(key, default)

    def set(self, key: str, value):
        self._settings[key] = value

    def update(self, data: dict):
        """Ko'p kalit-qiymat juftini bir vaqtda yangilash."""
        self._settings.update(data)

    def get_all(self) -> dict:
        return dict(self._settings)

    # ── Qulay xususiyatlar ─────────────────────────────────────────────────

    @property
    def rtsp_url(self) -> str:
        return self._settings.get("rtsp_url", "")

    @property
    def model_path(self) -> str:
        return self._settings.get("model_path", "")

    @property
    def camera_name(self) -> str:
        return self._settings.get("camera_name", "Kamera")

    @property
    def confidence(self) -> float:
        return float(self._settings.get("confidence", 0.6))

    @property
    def telegram_enabled(self) -> bool:
        return bool(self._settings.get("telegram_enabled", True))

    @property
    def telegram_token(self) -> str:
        return self._settings.get("telegram_token", "")

    @property
    def telegram_chat_ids(self) -> list:
        ids = self._settings.get("telegram_chat_ids", [])
        if isinstance(ids, str):
            return [x.strip() for x in ids.split(",") if x.strip()]
        return ids

    @property
    def backend_enabled(self) -> bool:
        return bool(self._settings.get("backend_enabled", False))

    @property
    def save_violations(self) -> bool:
        return bool(self._settings.get("save_violations", True))

    @property
    def company_id(self) -> str:
        return self._settings.get("company_id", "")

    @property
    def violations_dir(self) -> Path:
        d = self._settings.get("violations_dir", "")
        if d:
            return Path(d)
        return Path("violations")

    @property
    def smarthelmet_path(self) -> str:
        return self._settings.get("smarthelmet_path", SMARTHELMET_DEFAULT)

    @property
    def use_polygon(self) -> bool:
        return bool(self._settings.get("use_polygon", False))

    @property
    def polygon_points(self) -> list:
        return self._settings.get("polygon_points", [])

    def get_tracker_config(self) -> str:
        """BoT-SORT config yo'li."""
        cfg = self._settings.get("tracker_config", "")
        if cfg and os.path.exists(cfg):
            return cfg
        # SmartHelmet ichidagi default config
        sh = Path(self.smarthelmet_path)
        default = sh / "config" / "botsort_custom.yaml"
        if default.exists():
            return str(default)
        return "botsort.yaml"
