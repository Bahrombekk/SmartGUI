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
    "department_id": 1,
    "enabled": True,
    "access_mode": "department",
    "allowed_department_ids": [],
    "allowed_employee_ids": [],
    "polygon_points": [],
}

_DEFAULT_DEPARTMENT = {
    "id": 1,
    "name": "Main Building",
    "expanded": True,
}

DEFAULT_SETTINGS = {
    # SmartHelmet yo'li
    "smarthelmet_path": SMARTHELMET_DEFAULT,

    # Ko'p kamera ro'yxati
    "departments": [dict(_DEFAULT_DEPARTMENT)],
    "cameras": [dict(_DEFAULT_CAMERA)],
    "users": [],

    # Qayta ulanish (barcha kameralar uchun umumiy)
    "reconnect_delay": 3,
    "max_reconnects": 20,

    # Model
    "ai_model_enabled": False,
    "model_path": r"app\models\best.pt",
    "confidence": 0.25,
    "yolo_imgsz": 640,
    "use_gpu": True,
    "half_precision": False,
    "process_every_n": 1,

    # Detection
    "helmet_zone_bottom": 0.35,
    "helmet_iou_threshold": 0.15,
    "no_helmet_iou_threshold": 0.05,
    "confirmation_window": 10,
    "confirmation_threshold": 10,
    "violation_cooldown": 10,
    "helmet_class_ids": [0],
    "no_helmet_class_ids": [1],

    # Telegram
    "telegram_enabled": False,
    "telegram_token": "",
    "telegram_chat_ids": [],

    # Backend API (company_id endi kamera ichida)
    "backend_enabled": False,
    "backend_url": "",
    "backend_login": "",
    "backend_password": "",

    # Saqlash
    "save_violations": True,
    "violations_dir": "",
    "keep_files_days": 7,
    "cleanup_files": False,

    # FaceID / access roster
    "faceid_enabled": False,
    "faceid_threshold": 0.72,
    "access_roster_enabled": False,

    # Polygon
    "use_polygon": False,
    "polygon_points": [],

    # Interfeys
    "theme": "dark",
    "language": "uz",
    "display_max_width": 1280,
    "video_fps_limit": 25,
    "ai_fps_limit": 10,
    "inference_batch_size": 3,
    "cameras_per_model": 3,
    "violation_save_queue_size": 64,
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
        self._migrate_users()

    def _migrate_cameras(self):
        """
        Eski single-camera formatini (rtsp_url, camera_name, company_id)
        yangi cameras ro'yxatiga ko'chirish.
        """
        departments = self._settings.get("departments", [])
        if not departments:
            departments = [dict(_DEFAULT_DEPARTMENT)]
            self._settings["departments"] = departments
        for i, dep in enumerate(departments):
            if "id" not in dep:
                dep["id"] = i + 1
            if "expanded" not in dep:
                dep["expanded"] = True

        default_dep_id = departments[0].get("id", 1)
        cameras = self._settings.get("cameras", [])
        if cameras:
            # Har bir kamerada id bo'lishini ta'minlash
            for i, cam in enumerate(cameras):
                if "id" not in cam:
                    cam["id"] = i + 1
                if "department_id" not in cam:
                    cam["department_id"] = default_dep_id
                if "access_mode" not in cam:
                    cam["access_mode"] = "department"
                if "allowed_department_ids" not in cam:
                    cam["allowed_department_ids"] = []
                if "allowed_employee_ids" not in cam:
                    cam["allowed_employee_ids"] = []
                if "polygon_points" not in cam:
                    cam["polygon_points"] = []
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
            "department_id": default_dep_id,
            "enabled": True,
            "access_mode": "department",
            "allowed_department_ids": [],
            "allowed_employee_ids": [],
            "polygon_points": [],
        }]

    def _migrate_users(self):
        users = self._settings.get("users", [])
        if not isinstance(users, list):
            users = []
        default_dep = self.get_departments()[0].get("id", 1)
        for i, user in enumerate(users):
            if "id" not in user:
                user["id"] = i + 1
            if "employee_id" not in user:
                user["employee_id"] = str(user.get("id", i + 1))
            if "first_name" not in user:
                user["first_name"] = ""
            if "last_name" not in user:
                user["last_name"] = ""
            if "photo_path" not in user:
                user["photo_path"] = ""
            if "department_id" not in user:
                user["department_id"] = default_dep
            if "active" not in user:
                user["active"] = True
        self._settings["users"] = users

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

    def get_departments(self) -> list:
        """Barcha bo'limlar ro'yxati."""
        return self._settings.get("departments", [])

    def get_department_by_id(self, dep_id: int) -> dict | None:
        for d in self.get_departments():
            if d.get("id") == dep_id:
                return d
        return None

    def add_department(self, name: str) -> dict:
        departments = self.get_departments()
        name = name.strip()
        if not name:
            raise ValueError("Bo'lim nomi kiritilishi shart")
        if any(d.get("name", "").strip().lower() == name.lower() for d in departments):
            raise ValueError("Bunday nomli bo'lim allaqachon bor")

        existing_ids = {d.get("id", 0) for d in departments}
        new_id = 1
        while new_id in existing_ids:
            new_id += 1

        dep = {"id": new_id, "name": name, "expanded": True}
        departments.append(dep)
        self._settings["departments"] = departments
        return dep

    def update_department(self, dep_id: int, **kwargs):
        departments = self.get_departments()
        for dep in departments:
            if dep.get("id") == dep_id:
                dep.update(kwargs)
                break
        self._settings["departments"] = departments

    def remove_department(self, dep_id: int) -> bool:
        departments = self.get_departments()
        if len(departments) <= 1:
            return False
        self._settings["departments"] = [
            d for d in departments if d.get("id") != dep_id
        ]
        remaining = self._settings["departments"][0].get("id", 1)
        for cam in self.get_cameras():
            if cam.get("department_id") == dep_id:
                cam["department_id"] = remaining
        for user in self.get_users():
            if user.get("department_id") == dep_id:
                user["department_id"] = remaining
        return True

    # в"?в"? Hodimlar boshqaruvi в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?в"?

    def get_users(self) -> list:
        return self._settings.get("users", [])

    def add_user(self, first_name: str, last_name: str, employee_id: str,
                 photo_path: str = "", department_id: int | None = None) -> dict:
        first_name = (first_name or "").strip()
        last_name = (last_name or "").strip()
        employee_id = (employee_id or "").strip()
        if not first_name:
            raise ValueError("Ism kiritilishi shart")
        if not last_name:
            raise ValueError("Familya kiritilishi shart")
        if not employee_id:
            raise ValueError("Hodim ID kiritilishi shart")

        users = self.get_users()
        if any(str(u.get("employee_id", "")).lower() == employee_id.lower() for u in users):
            raise ValueError("Bunday ID bilan hodim allaqachon bor")

        existing_ids = {u.get("id", 0) for u in users}
        new_id = 1
        while new_id in existing_ids:
            new_id += 1

        dep_id = department_id or self.get_departments()[0].get("id", 1)
        user = {
            "id": new_id,
            "first_name": first_name,
            "last_name": last_name,
            "employee_id": employee_id,
            "photo_path": photo_path or "",
            "department_id": dep_id,
            "active": True,
        }
        users.append(user)
        self._settings["users"] = users
        return user

    def update_user(self, user_id: int, **kwargs):
        users = self.get_users()
        for user in users:
            if user.get("id") == user_id:
                user.update(kwargs)
                break
        self._settings["users"] = users

    def remove_user(self, user_id: int) -> bool:
        users = self.get_users()
        before = len(users)
        self._settings["users"] = [u for u in users if u.get("id") != user_id]
        return len(self._settings["users"]) != before

    def get_enabled_cameras(self) -> list:
        """Faqat yoqilgan kameralar."""
        return [c for c in self.get_cameras() if c.get("enabled", True)]

    def get_camera_by_id(self, cam_id: int) -> dict | None:
        for c in self.get_cameras():
            if c.get("id") == cam_id:
                return c
        return None

    def add_camera(self, name: str, rtsp_url: str, company_id: str,
                   enabled: bool = True, department_id: int | None = None) -> dict:
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
            "department_id": department_id or self.get_departments()[0].get("id", 1),
            "enabled": enabled,
            "access_mode": "department",
            "allowed_department_ids": [],
            "allowed_employee_ids": [],
            "polygon_points": [],
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
    def ai_model_enabled(self) -> bool:
        return bool(self._settings.get("ai_model_enabled", False))

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
    def camera_id(self) -> int | None:
        return self._cam.get("id")

    @property
    def rtsp_url(self) -> str:
        return self._cam.get("rtsp_url", self._base.rtsp_url)

    @property
    def camera_name(self) -> str:
        return self._cam.get("name", self._base.camera_name)

    @property
    def company_id(self) -> str:
        return self._cam.get("company_id", self._base.company_id)

    @property
    def department_id(self) -> int | None:
        return self._cam.get("department_id")

    @property
    def camera(self) -> dict:
        return dict(self._cam)

    # Qolgan xususiyatlar → base
    @property
    def model_path(self) -> str:
        return self._base.model_path

    @property
    def ai_model_enabled(self) -> bool:
        return self._base.ai_model_enabled

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
