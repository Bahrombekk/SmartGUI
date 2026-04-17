"""
ConfigManager — settings.json ni o'qish/yozish.
Ko'p kamera qo'llab-quvvatlash bilan.
"""

import json
import os
from pathlib import Path

SMARTHELMET_DEFAULT = ""

# Default bitta kamera
_DEFAULT_CAMERA = {
    "id": 1,
    "name": "Elekravoz sex ichki",
    "rtsp_url": "rtsp://admin:qwerty12345@192.168.25.114:554/Streaming/Channels/101",
    "company_id": "61169935-7269-4782-a5d2-bdd42ef28bb0",
    "enabled": True,
}

DEFAULT_SETTINGS = {
    # SmartHelmet yo'li
    "smarthelmet_path": SMARTHELMET_DEFAULT,

    # Ko'p kamera ro'yxati
    "cameras": [dict(_DEFAULT_CAMERA)],

    # Qayta ulanish (barcha kameralar uchun umumiy)
    "reconnect_delay": 3,
    "max_reconnects": 20,

    # Model
    "model_path": r"app\models\best.pt",
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

    # Backend API (company_id endi kamera ichida)
    "backend_enabled": True,
    "backend_url": "https://ai-project.das-uty.uz/api/camera/create",
    "backend_login": "kaska",
    "backend_password": "Kaska2025",

    # Saqlash
    "save_violations": True,
    "violations_dir": "",
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
    "tracker_config": "",
}


class ConfigManager:
    """Ilova sozlamalarini boshqaruvchi klass."""

    def __init__(self, settings_file: str = "settings.json"):
        self.settings_file = Path(settings_file)
        self._settings: dict = {}
        self._load()

    # ── Yuklash / Saqlash ─────────────────────────────────────────────────

    def _load(self):
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._settings = {**DEFAULT_SETTINGS, **saved}
            except Exception as e:
                print(f"[ConfigManager] settings.json o'qishda xatolik: {e}")
                self._settings = dict(DEFAULT_SETTINGS)
        else:
            self._settings = dict(DEFAULT_SETTINGS)
            self.save()

        self._migrate_cameras()

    def _migrate_cameras(self):
        """
        Eski single-camera formatini (rtsp_url, camera_name, company_id)
        yangi cameras ro'yxatiga ko'chirish.
        """
        cameras = self._settings.get("cameras", [])
        if cameras:
            # Har bir kamerada id bo'lishini ta'minlash
            for i, cam in enumerate(cameras):
                if "id" not in cam:
                    cam["id"] = i + 1
            return

        # Eski formatdan migration
        old_url     = self._settings.get("rtsp_url", "")
        old_name    = self._settings.get("camera_name", "Kamera 1")
        old_company = self._settings.get("company_id", "")

        self._settings["cameras"] = [{
            "id": 1,
            "name": old_name or "Kamera 1",
            "rtsp_url": old_url,
            "company_id": old_company,
            "enabled": True,
        }]

    def save(self):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Saqlashda xatolik: {e}")

    # ── Get / Set ─────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        return self._settings.get(key, default)

    def set(self, key: str, value):
        self._settings[key] = value

    def update(self, data: dict):
        self._settings.update(data)

    def get_all(self) -> dict:
        return dict(self._settings)

    # ── Kamera boshqaruvi ─────────────────────────────────────────────────

    def get_cameras(self) -> list:
        """Barcha kameralar ro'yxati."""
        return self._settings.get("cameras", [])

    def get_enabled_cameras(self) -> list:
        """Faqat yoqilgan kameralar."""
        return [c for c in self.get_cameras() if c.get("enabled", True)]

    def get_camera_by_id(self, cam_id: int) -> dict | None:
        for c in self.get_cameras():
            if c.get("id") == cam_id:
                return c
        return None

    def add_camera(self, name: str, rtsp_url: str, company_id: str,
                   enabled: bool = True) -> dict:
        """Yangi kamera qo'shish. Maksimal 10 ta."""
        cameras = self.get_cameras()
        if len(cameras) >= 10:
            raise ValueError("Maksimal 10 ta kamera qo'shish mumkin")

        existing_ids = {c.get("id", 0) for c in cameras}
        new_id = 1
        while new_id in existing_ids:
            new_id += 1

        cam = {
            "id": new_id,
            "name": name,
            "rtsp_url": rtsp_url,
            "company_id": company_id,
            "enabled": enabled,
        }
        cameras.append(cam)
        self._settings["cameras"] = cameras
        return cam

    def update_camera(self, cam_id: int, **kwargs):
        """Mavjud kamerani yangilash."""
        cameras = self.get_cameras()
        for cam in cameras:
            if cam.get("id") == cam_id:
                cam.update(kwargs)
                break
        self._settings["cameras"] = cameras

    def remove_camera(self, cam_id: int) -> bool:
        """Kamerani o'chirish. Kamida 1 ta qolishi kerak."""
        cameras = self.get_cameras()
        if len(cameras) <= 1:
            return False
        self._settings["cameras"] = [c for c in cameras if c.get("id") != cam_id]
        return True

    # ── Qulay xususiyatlar (birinchi kamera asosida) ───────────────────────

    @property
    def rtsp_url(self) -> str:
        cams = self.get_cameras()
        return cams[0].get("rtsp_url", "") if cams else ""

    @property
    def camera_name(self) -> str:
        cams = self.get_cameras()
        return cams[0].get("name", "Kamera") if cams else "Kamera"

    @property
    def company_id(self) -> str:
        cams = self.get_cameras()
        return cams[0].get("company_id", "") if cams else ""

    @property
    def model_path(self) -> str:
        return self._settings.get("model_path", "")

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
    def violations_dir(self) -> Path:
        d = self._settings.get("violations_dir", "")
        return Path(d) if d else Path("violations")

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
        cfg = self._settings.get("tracker_config", "")
        if cfg and os.path.exists(cfg):
            return cfg
        sh = Path(self.smarthelmet_path)
        default = sh / "config" / "botsort_custom.yaml"
        if default.exists():
            return str(default)
        return "botsort.yaml"


# ── CameraConfigProxy ──────────────────────────────────────────────────────

class CameraConfigProxy:
    """
    Bitta kamera uchun ConfigManager wrapper.
    Kamera-specific qiymatlarni (rtsp_url, camera_name, company_id) override qiladi,
    qolgan barcha sozlamalarni base ConfigManager dan oladi.
    """

    def __init__(self, base: ConfigManager, camera: dict):
        self._base = base
        self._cam = camera

    # get/set/update/save → base ga yo'naltirish
    def get(self, key: str, default=None):
        if key == "rtsp_url":
            return self._cam.get("rtsp_url", self._base.get(key, default))
        if key == "camera_name":
            return self._cam.get("name", self._base.get(key, default))
        if key == "company_id":
            return self._cam.get("company_id", self._base.get(key, default))
        return self._base.get(key, default)

    def set(self, key, value):
        self._base.set(key, value)

    def update(self, data: dict):
        self._base.update(data)

    def save(self):
        self._base.save()

    def get_all(self) -> dict:
        return self._base.get_all()

    # Kamera-specific xususiyatlar
    @property
    def rtsp_url(self) -> str:
        return self._cam.get("rtsp_url", self._base.rtsp_url)

    @property
    def camera_name(self) -> str:
        return self._cam.get("name", self._base.camera_name)

    @property
    def company_id(self) -> str:
        return self._cam.get("company_id", self._base.company_id)

    # Qolgan xususiyatlar → base
    @property
    def model_path(self) -> str:
        return self._base.model_path

    @property
    def confidence(self) -> float:
        return self._base.confidence

    @property
    def telegram_enabled(self) -> bool:
        return self._base.telegram_enabled

    @property
    def telegram_token(self) -> str:
        return self._base.telegram_token

    @property
    def telegram_chat_ids(self) -> list:
        return self._base.telegram_chat_ids

    @property
    def backend_enabled(self) -> bool:
        return self._base.backend_enabled

    @property
    def save_violations(self) -> bool:
        return self._base.save_violations

    @property
    def violations_dir(self) -> Path:
        return self._base.violations_dir

    @property
    def smarthelmet_path(self) -> str:
        return self._base.smarthelmet_path

    @property
    def use_polygon(self) -> bool:
        return self._base.use_polygon

    @property
    def polygon_points(self) -> list:
        return self._base.polygon_points

    def get_tracker_config(self) -> str:
        return self._base.get_tracker_config()
