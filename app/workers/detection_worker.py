"""
DetectionWorker — CameraService (ai_camera_service arxitekturasi) asosida.

  - CV2RTSPReader: video oqim (GPU NVDEC, 4-usul fallback, lock-free buffer)
  - CameraService / DetectorGroup: batch GPU inference (ai_camera_service dan)
  - IoUTracker: velocity prediction + centre-distance fallback
  - ViolationService: buzilishni saqlash, Telegram/Backend xabarlash
"""
from __future__ import annotations

import threading
import time
from collections import deque
from queue import Empty, Full, Queue

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from app.application.services.violation_service import ViolationService
from app.application.services.faceid_service import FaceIdService
from app.domain.policies import AccessPolicy
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.infrastructure.camera.cv2_rtsp_reader import CV2RTSPReader
from app.workers.camera_service import svc_acquire, svc_register, svc_unregister
from app.workers.inference_engine import IoUTracker


class DetectionWorker(QThread):
    """
    Bitta kamera uchun background detection thread'i.

    Arxitektura:
        CV2RTSPReader  →  video display (video_fps_limit)
        CameraService  →  batch YOLO inference (DetectorGroup thread)
        IoUTracker     →  stable track ID lar
        ViolationService → buzilishni qayd etish

    Signals:
        frame_ready(QImage)      — ko'rsatishga tayyor frame
        violation_detected(dict) — yangi buzilish
        stats_updated(dict)      — fps, today_count, active_persons, connected
        status_changed(str)      — holat matni
        error_occurred(str)      — xatolik
        model_loaded()           — model yuklandi
    """

    frame_ready        = pyqtSignal(object)
    violation_detected = pyqtSignal(dict)
    stats_updated      = pyqtSignal(dict)
    status_changed     = pyqtSignal(str)
    error_occurred     = pyqtSignal(str)
    model_loaded       = pyqtSignal()

    def __init__(self, config_manager, db: ViolationsDB, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.db  = db
        self.violation_service = ViolationService(db)
        self.access_policy = AccessPolicy()
        self.faceid_service: FaceIdService | None = None

        self._running = False
        self._paused  = False
        self._reader: CV2RTSPReader | None = None

        # CameraService (ai_camera_service arxitekturasi)
        self._svc = None          # CameraService singleton
        self._cam_id: int = id(self)   # unique per worker

        # Tracker
        preset = str(self.cfg.get("tracking_strictness", "balanced")).lower()
        preset_defaults = {
            "stable":   {"iou": 0.12, "center": 1.55, "age": 220, "hits": 4},
            "balanced": {"iou": 0.15, "center": 1.25, "age": 150, "hits": 3},
            "fast":     {"iou": 0.20, "center": 0.95, "age": 80,  "hits": 2},
        }.get(preset, {"iou": 0.15, "center": 1.25, "age": 150, "hits": 3})
        self._tracker = IoUTracker(
            iou_thresh=float(self.cfg.get("tracker_iou_threshold", preset_defaults["iou"])),
            center_thresh=float(self.cfg.get("tracker_center_threshold", preset_defaults["center"])),
            max_age=int(self.cfg.get("tracker_max_age", preset_defaults["age"])),
            min_hits=int(self.cfg.get("tracker_min_hits", preset_defaults["hits"])),
        )
        self._last_persons: list[dict] = []
        self._last_result_ts: float | None = None  # oxirgi qayta ishlangan result

        # Class separation config (class 0 = person, 1 = green inner, 2 = red inner)
        self._person_class_id = int(self.cfg.get("person_class_id", 0))
        self._green_class_ids = set(int(x) for x in self.cfg.get("helmet_class_ids", [1]))
        self._red_class_ids   = set(int(x) for x in self.cfg.get("no_helmet_class_ids", [2]))
        self._box_pad         = int(self.cfg.get("class0_box_pad", 50))
        self._helmet_status_window = max(3, int(self.cfg.get("helmet_status_window", 50)))
        self._helmet_status_threshold = max(1, int(self.cfg.get("helmet_status_threshold", 30)))
        self._track_statuses: dict[int, deque[str]] = {}

        # FPS
        self._frame_count   = 0
        self._fps           = 0.0
        self._fps_samples: deque[float] = deque(maxlen=30)
        self._last_fps_ts: float | None = None

        # Violations
        self._today_count         = 0
        self._saved_violations:   set[tuple[int, str]] = set()
        self._spatial_violations: deque[dict] = deque(maxlen=256)
        self._no_helmet_frames:   dict[int, int] = {}
        self._access_frames:      dict[int, int] = {}
        self._save_queue: Queue[dict | None] = Queue(
            maxsize=max(1, int(self.cfg.get("violation_save_queue_size", 64)))
        )
        self._save_thread: threading.Thread | None = None

        # Notifiers
        self._notifier = None
        self._backend  = None

    # ── Service / Model ───────────────────────────────────────────────────

    def _init_service(self) -> bool:
        """
        Global CameraService singleton oladi (model yuklamaydi, faqat singleton).
        False → AI o'chirilgan yoki model topilmadi.
        """
        if not bool(self.cfg.get("ai_model_enabled", False)):
            self.status_changed.emit("Video rejim (AI o'chirilgan)")
            return False

        self._svc = svc_acquire(self.cfg)
        if self._svc is None:
            self.error_occurred.emit("CameraService yaratilmadi — video rejimda ishlaydi")
            return False

        # model_loaded signali _register_with_service() ichida emit qilinadi
        return True

    def _register_with_service(self):
        """
        Background thread'da ishlaydi — video display ni bloklamaydi.
        svc_register() model yuklashni (sekin) shu yerda bajaradi.
        """
        self.status_changed.emit("AI model yuklanmoqda...")
        svc_register(self._cam_id, self._reader)
        if self._running:
            self.model_loaded.emit()
            self.status_changed.emit("AI tayyor")

    # ── Notifiers ─────────────────────────────────────────────────────────

    def _setup_notifiers(self):
        if self.cfg.telegram_enabled and self.cfg.telegram_token and self.cfg.telegram_chat_ids:
            try:
                from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
                self._notifier = TelegramNotifier(
                    self.cfg.telegram_token, self.cfg.telegram_chat_ids
                )
            except Exception as e:
                print(f"[Worker] Telegram yuklanmadi: {e}")

        if self.cfg.backend_enabled:
            try:
                from app.infrastructure.notifications.backend_client import BackendClient
                self._backend = BackendClient(
                    api_url  = self.cfg.get("backend_url",      ""),
                    login    = self.cfg.get("backend_login",    ""),
                    password = self.cfg.get("backend_password", ""),
                )
            except Exception as e:
                print(f"[Worker] Backend yuklanmadi: {e}")

    def _setup_faceid(self):
        if not bool(self.cfg.get("faceid_enabled", False) or self.cfg.get("access_roster_enabled", False)):
            return
        try:
            svc = FaceIdService(self.db, self.cfg)
            svc.enroll_from_settings_users()
            self.faceid_service = svc
        except Exception as e:
            self.faceid_service = None
            self.error_occurred.emit(f"FaceID tayyorlanmadi: {e}")

    # ── Natijalarni tahlil ────────────────────────────────────────────────

    def _process_detections(self, detections: list[dict]) -> list[dict]:
        """
        Faqat class 0 ni track qiladi.
        Har bir class 0 box ichida class 1 (yashil) yoki class 2 (qizil) borligini
        bir marta tekshiradi va natijani cache'da saqlaydi.
        """
        persons    = [d for d in detections if d.get("class_id") == self._person_class_id]
        green_boxes = [d["box"] for d in detections if d.get("class_id") in self._green_class_ids]
        red_boxes   = [d["box"] for d in detections if d.get("class_id") in self._red_class_ids]

        tracked = self._tracker.update(persons)

        active_ids = {p["track_id"] for p in tracked}
        self._track_statuses = {
            tid: s for tid, s in self._track_statuses.items() if tid in active_ids
        }

        for p in tracked:
            tid = p["track_id"]
            padded = self._pad_box(p["box"], self._box_pad)
            status = self._inner_status(padded, green_boxes, red_boxes)
            history = self._track_statuses.setdefault(
                tid, deque(maxlen=self._helmet_status_window)
            )
            if status in ("green", "red"):
                history.append(status)

            green = sum(1 for item in history if item == "green")
            red = sum(1 for item in history if item == "red")
            total = green + red
            # Class 1 ishonchli: agar 5%+ green bo'lsa — shlem bor (class 2 adashsa ham)
            if total > 0 and (green / total) > 0.05:
                p["has_helmet"] = True
            elif red >= self._helmet_status_threshold and red > green:
                p["has_helmet"] = False
            else:
                p["has_helmet"] = None

        return tracked

    @staticmethod
    def _pad_box(box: list, pad: int) -> list:
        return [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad]

    def _inner_status(self, person_box: list, green_boxes: list, red_boxes: list) -> str:
        # Class 1 (helmet/yashil) ustun: agar class 1 va class 2 bir vaqtda aniqlansa,
        # class 1 g'olib — shlemsiz xulosa chiqarmaydi.
        for box in green_boxes:
            if self._box_overlaps(person_box, box):
                return "green"
        for box in red_boxes:
            if self._box_overlaps(person_box, box):
                return "red"
        return "yellow"

    @staticmethod
    def _box_overlaps(outer: list, inner: list, threshold: float = 0.3) -> bool:
        """inner box ning kamida threshold qismi outer ichida bo'lsa True."""
        x1 = max(outer[0], inner[0]); y1 = max(outer[1], inner[1])
        x2 = min(outer[2], inner[2]); y2 = min(outer[3], inner[3])
        if x2 <= x1 or y2 <= y1:
            return False
        inter = (x2 - x1) * (y2 - y1)
        inner_area = max(1.0, (inner[2] - inner[0]) * (inner[3] - inner[1]))
        return (inter / inner_area) >= threshold

    def _check_violations(self, persons: list[dict]) -> list[dict]:
        threshold  = int(self.cfg.get("confirmation_threshold", 10))
        active_ids = {p["track_id"] for p in persons}
        self._no_helmet_frames = {
            k: v for k, v in self._no_helmet_frames.items() if k in active_ids
        }
        for p in persons:
            tid = p["track_id"]
            if not p.get("track_confirmed", True):
                self._no_helmet_frames[tid] = 0
                p["is_new_violation"] = False
                continue
            if p.get("has_helmet") is False:
                self._no_helmet_frames[tid] = self._no_helmet_frames.get(tid, 0) + 1
                p["is_new_violation"] = (
                    self._no_helmet_frames[tid] == threshold
                    and (tid, "no_helmet") not in self._saved_violations
                    and not self._is_spatial_duplicate(p, "no_helmet")
                )
            else:
                self._no_helmet_frames[tid] = 0
                p["is_new_violation"] = False
        return persons

    def _check_access_violation(self, frame: np.ndarray, person: dict):
        if self.faceid_service is None:
            return None
        tid = person.get("track_id", -1)
        if not person.get("track_confirmed", True):
            self._access_frames[tid] = 0
            return None
        if (tid, "unknown_person") in self._saved_violations or (tid, "unauthorized_area") in self._saved_violations:
            return None

        threshold = int(self.cfg.get("confirmation_threshold", 10))
        self._access_frames[tid] = self._access_frames.get(tid, 0) + 1
        if self._access_frames[tid] < threshold:
            return None

        crop = self._crop_person(frame, person)
        identity = self.faceid_service.match_person_crop(crop) if crop is not None else None
        camera = getattr(self.cfg, "camera", {})
        violation = self.access_policy.evaluate(camera, identity)
        if violation is None:
            return None
        person["employee_id"] = violation.employee_id
        person["employee_name"] = violation.employee_name
        person["identity_confidence"] = violation.identity_confidence
        return violation.violation_type

    @staticmethod
    def _crop_person(frame: np.ndarray, person: dict) -> np.ndarray | None:
        box = person.get("box", person.get("bbox_xyxy", []))
        if len(box) != 4 or frame is None or frame.size == 0:
            return None
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in box]
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2].copy()

    @staticmethod
    def _extrapolate_box(p: dict, t: float) -> dict:
        """Box pozitsiyasini velocity asosida t detection-frame oldinga suradi."""
        vx = p.get("vx", 0.0)
        vy = p.get("vy", 0.0)
        if abs(vx) < 0.3 and abs(vy) < 0.3:
            return p
        p = dict(p)
        box = list(p.get("box", p.get("bbox_xyxy", [])))
        if len(box) == 4:
            dx, dy = vx * t, vy * t
            box = [box[0]+dx, box[1]+dy, box[2]+dx, box[3]+dy]
            p["box"] = box
            p["bbox_xyxy"] = box
        return p

    # ── Overlay chizish ───────────────────────────────────────────────────

    @staticmethod
    def _draw_overlay(frame: np.ndarray, persons: list[dict]) -> np.ndarray:
        h, w = frame.shape[:2]

        for p in persons:
            box = p.get("box", p.get("bbox_xyxy", []))
            if len(box) < 4:
                continue
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            has_hel = p.get("has_helmet")
            if has_hel is True:
                color = (0, 200, 0)    # yashil  — class 1 aniqlandi
            elif has_hel is False:
                color = (0, 0, 220)    # qizil   — class 2 aniqlandi
            else:
                color = (0, 255, 255)  # sariq   — hech narsa aniqlanmadi
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        cv2.rectangle(frame, (0, 0), (w, 36), (10, 14, 20), -1)
        cv2.rectangle(frame, (0, h - 32), (w, h), (10, 14, 20), -1)
        return frame

    # ── Buzilish saqlash ──────────────────────────────────────────────────

    def _start_violation_writer(self):
        if self._save_thread and self._save_thread.is_alive():
            return
        self._save_thread = threading.Thread(
            target=self._violation_writer_loop,
            daemon=True,
            name=f"ViolationWriter-{self._cam_id}",
        )
        self._save_thread.start()

    def _stop_violation_writer(self):
        if not self._save_thread or not self._save_thread.is_alive():
            return
        try:
            self._save_queue.put(None, timeout=0.3)
        except Full:
            return
        # Daemon thread — ilova yopilganda o'zi to'xtaydi
        self._save_thread.join(timeout=1.0)

    def _violation_writer_loop(self):
        while True:
            try:
                item = self._save_queue.get(timeout=0.2)
            except Empty:
                continue

            if item is None:
                self._save_queue.task_done()
                break

            try:
                event = self.violation_service.register_violation(
                    frame          = item["frame"],
                    person         = item["person"],
                    camera_name    = item["camera_name"],
                    company_id     = item["company_id"],
                    violations_dir = item["violations_dir"],
                    save_files     = item["save_files"],
                    violation_type = item.get("violation_type", "no_helmet"),
                    camera_id      = item.get("camera_id"),
                    department_id  = item.get("department_id"),
                    employee_id    = item["person"].get("employee_id"),
                    employee_name  = item["person"].get("employee_name", ""),
                    identity_confidence = float(item["person"].get("identity_confidence", 0.0) or 0.0),
                    notifier       = self._notifier,
                    backend        = self._backend,
                )
                self._today_count = self.db.get_today_count()
                payload = event.to_payload()
                payload["today_count"] = self._today_count
                if self._running:
                    self.violation_detected.emit(payload)
            except Exception as e:
                tid = int(item.get("track_id", -1))
                if tid >= 0:
                    self._saved_violations.discard((tid, item.get("violation_type", "no_helmet")))
                self.error_occurred.emit(f"Buzilishni saqlashda xatolik: {e}")
            finally:
                self._save_queue.task_done()

    def _handle_violation(self, frame: np.ndarray, person: dict, violation_type: str = "no_helmet"):
        tid = person.get("track_id", -1)
        key = (tid, violation_type)
        if key in self._saved_violations or self._is_spatial_duplicate(person, violation_type):
            return
        self._saved_violations.add(key)
        self._remember_spatial_violation(person, violation_type)
        try:
            self._save_queue.put_nowait({
                "track_id": tid,
                "violation_type": violation_type,
                "frame": frame.copy(),
                "person": dict(person),
                "camera_name": self.cfg.camera_name,
                "camera_id": getattr(self.cfg, "camera_id", None),
                "department_id": getattr(self.cfg, "department_id", None),
                "company_id": self.cfg.company_id,
                "violations_dir": self.cfg.violations_dir,
                "save_files": self.cfg.save_violations,
            })
        except Full:
            self._saved_violations.discard(key)
            self.error_occurred.emit("Buzilish saqlash navbati to'lib qoldi")

    @staticmethod
    def _box_center_size(person: dict) -> tuple[float, float, float]:
        box = person.get("box", person.get("bbox_xyxy", []))
        if len(box) != 4:
            return 0.0, 0.0, 1.0
        cx = (float(box[0]) + float(box[2])) * 0.5
        cy = (float(box[1]) + float(box[3])) * 0.5
        w = max(1.0, float(box[2]) - float(box[0]))
        h = max(1.0, float(box[3]) - float(box[1]))
        return cx, cy, max(w, h)

    def _prune_spatial_violations(self, now: float):
        cooldown = float(self.cfg.get("violation_cooldown", 10))
        while self._spatial_violations and now - float(self._spatial_violations[0]["ts"]) > cooldown:
            self._spatial_violations.popleft()

    def _is_spatial_duplicate(self, person: dict, violation_type: str) -> bool:
        now = time.time()
        self._prune_spatial_violations(now)
        cx, cy, size = self._box_center_size(person)
        max_dist = max(48.0, size * 0.65)
        for item in self._spatial_violations:
            if item["type"] != violation_type:
                continue
            dist = ((cx - item["cx"]) ** 2 + (cy - item["cy"]) ** 2) ** 0.5
            if dist <= max_dist:
                return True
        return False

    def _remember_spatial_violation(self, person: dict, violation_type: str):
        cx, cy, _ = self._box_center_size(person)
        self._spatial_violations.append({
            "ts": time.time(),
            "type": violation_type,
            "cx": cx,
            "cy": cy,
        })

    # ── Yordamchi metodlar ────────────────────────────────────────────────

    def _resize_for_display(self, frame: np.ndarray) -> np.ndarray:
        max_w = int(self.cfg.get("display_max_width", 640))
        if max_w <= 0:
            return frame
        h, w = frame.shape[:2]
        if w <= max_w:
            return frame
        new_h = max(1, int(h * (max_w / w)))
        return cv2.resize(frame, (max_w, new_h), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _to_qimage(frame: np.ndarray) -> QImage:
        h, w = frame.shape[:2]
        # Format_BGR888 (Qt 6): cvtColor dan qochadi, CPU yukini kamaytiradi
        if hasattr(QImage.Format, "Format_BGR888"):
            img = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_BGR888)
            return img.copy()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return QImage(rgb.tobytes(), w, h, 3 * w, QImage.Format.Format_RGB888)

    def _emit_frame(self, frame: np.ndarray):
        display = self._resize_for_display(frame)
        self.frame_ready.emit(self._to_qimage(display))

    def _update_fps(self, now: float):
        if self._last_fps_ts is not None:
            self._fps_samples.append(now - self._last_fps_ts)
            avg = sum(self._fps_samples) / len(self._fps_samples)
            self._fps = 1.0 / avg if avg > 0 else 0.0
        self._last_fps_ts = now

    def _ping_ms(self) -> float:
        if self._reader and hasattr(self._reader, "latency_ms"):
            return float(self._reader.latency_ms)
        return 0.0

    # ── Asosiy loop ───────────────────────────────────────────────────────

    def run(self):
        self._running     = True
        self._today_count = self.db.get_today_count()

        self.status_changed.emit("Yuklanmoqda...")
        has_ai = self._init_service()
        self._setup_notifiers()
        self._setup_faceid()

        rtsp_url = self.cfg.rtsp_url
        if not rtsp_url:
            self.error_occurred.emit("RTSP URL ko'rsatilmagan")
            self._running = False
            return

        self._start_violation_writer()
        self.status_changed.emit("Kameraga ulanmoqda...")

        is_stream = rtsp_url.startswith(("rtsp://", "rtmp://"))

        if is_stream:
            self._reader = CV2RTSPReader(
                rtsp_url,
                reconnect_delay = int(self.cfg.get("reconnect_delay", 3)),
                max_reconnects  = int(self.cfg.get("max_reconnects", 999)),
                target_fps      = int(self.cfg.get("video_fps_limit", 25)),
            )
            self._reader.cam_id = self._cam_id
            self._reader.start()  # Video darhol boshlanadi

            # CameraService ga registratsiya — background thread'da (model yuklanishi sekin)
            if has_ai and self._svc is not None:
                threading.Thread(
                    target=self._register_with_service,
                    daemon=True,
                    name=f"SvcReg-{self._cam_id}",
                ).start()
        else:
            self._reader = cv2.VideoCapture(rtsp_url)

        video_fps      = max(1, int(self.cfg.get("video_fps_limit", 25)))
        video_interval = 1.0 / video_fps

        last_emit_ts   = 0.0
        last_frame_id  = -1
        no_frame_count = 0

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            # ── Video rate limiting (frame copy dan OLDIN) ────────────────
            now = time.perf_counter()
            remaining = video_interval - (now - last_emit_ts)
            if remaining > 0.008:
                time.sleep(remaining - 0.005)
                continue
            elif remaining > 0:
                time.sleep(0.001)   # spin o'rniga qisqa uxlash
                continue

            # ── Frame olish ───────────────────────────────────────────────
            if is_stream:
                current_id = getattr(self._reader, "frame_count", self._frame_count)
                if current_id == last_frame_id:
                    time.sleep(0.005)
                    continue

                ok, frame = self._reader.get_frame()
                connected = self._reader.is_connected
                if not ok:
                    no_frame_count += 1
                    if no_frame_count % 40 == 0:
                        self.stats_updated.emit({
                            "fps": 0.0, "today_count": self._today_count,
                            "active_persons": 0, "connected": False, "ping_ms": None,
                        })
                        self.status_changed.emit("Qayta ulanmoqda...")
                    time.sleep(0.05)
                    continue
                no_frame_count = 0
            else:
                current_id = self._frame_count
                ok, frame = self._reader.read()
                connected = ok
                if not ok:
                    self._running = False
                    self.status_changed.emit("Video fayl tugadi")
                    break

            last_emit_ts  = now
            last_frame_id = current_id
            self._update_fps(now)
            self._frame_count += 1

            # ── AI natija (CameraService dan) ─────────────────────────────
            if has_ai and self._svc is not None:
                result = self._svc.latest_result(self._cam_id)
                new_det = result is not None and result.timestamp != self._last_result_ts

                if new_det:
                    self._last_result_ts = result.timestamp
                    persons = self._process_detections(result.detections)
                    persons = self._check_violations(persons)
                    self._last_persons = persons

                    violation_frame = result.raw_frame if result.raw_frame is not None else frame
                    for p in persons:
                        if p.get("is_new_violation", False):
                            self._handle_violation(violation_frame, p, "no_helmet")
                        access_type = self._check_access_violation(violation_frame, p)
                        if access_type:
                            self._handle_violation(violation_frame, p, access_type)

                persons = self._last_persons

                # AI result kelmaganida velocity bilan box pozitsiyasini oldinlash
                if persons and self._last_result_ts is not None:
                    elapsed = now - self._last_result_ts
                    ai_fps  = max(1, int(self.cfg.get("ai_fps_limit", 10)))
                    t = min(elapsed * ai_fps, 2.5)
                    if t > 0.1:
                        persons = [self._extrapolate_box(p, t) for p in persons]

                # Display doim live framedan quriladi; raw_frame faqat violation
                # saqlash uchun ishlatiladi.
                display_frame = self._draw_overlay(frame, persons)
                self._emit_frame(display_frame)

                if self._frame_count % 30 == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._today_count,
                        "active_persons": len(persons),
                        "connected":      connected,
                        "ping_ms":        self._ping_ms() if connected else None,
                    })
                    self.status_changed.emit(
                        f"Ulangan | FPS: {self._fps:.1f} | Bugun: {self._today_count}"
                        if connected else "Qayta ulanmoqda..."
                    )

            else:
                # ── Video-only rejim ──────────────────────────────────────
                self._emit_frame(frame)

                if self._frame_count % max(1, video_fps) == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._today_count,
                        "active_persons": 0,
                        "connected":      connected,
                        "ping_ms":        self._ping_ms() if connected else None,
                    })
                    self.status_changed.emit(
                        f"Ulangan | FPS: {self._fps:.1f}"
                        if connected else "Qayta ulanmoqda..."
                    )

        self._cleanup()

    # ── Tozalash ──────────────────────────────────────────────────────────

    def _cleanup(self):
        # CameraService dan reader ni olib tashlaymiz
        if self._svc is not None:
            svc_unregister(self._cam_id)

        if self._reader:
            if hasattr(self._reader, "stop"):
                self._reader.stop()
            elif hasattr(self._reader, "release"):
                self._reader.release()

        self._tracker.reset()
        self._track_statuses.clear()
        self._spatial_violations.clear()
        self._stop_violation_writer()
        self.status_changed.emit("To'xtatildi")

    # ── Tashqi boshqaruv ──────────────────────────────────────────────────

    def stop(self):
        self._running = False
        self.wait(400)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused
