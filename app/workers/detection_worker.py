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

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from app.application.services.detection_analysis import PersonDetectionAnalyzer
from app.application.services.faceid_service import FaceIdService
from app.application.services.violation_runtime import ViolationRuntime
from app.domain.policies import AccessPolicy
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.infrastructure.camera.cv2_rtsp_reader import CV2RTSPReader
from app.workers.camera_service import svc_acquire, svc_register, svc_unregister
from app.shared.utils.frame_display import (
    draw_helmet_overlay,
    frame_to_qimage,
    resize_for_display,
)
import logging

_log = logging.getLogger(__name__)


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
    face_recognized    = pyqtSignal(dict)

    def __init__(self, config_manager, db: ViolationsDB, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.db  = db
        self.access_policy = AccessPolicy()
        self.faceid_service: FaceIdService | None = None
        self._violation_runtime = ViolationRuntime(
            self.cfg,
            self.db,
            emit_payload=self.violation_detected.emit,
            emit_error=self.error_occurred.emit,
        )

        self._running = False
        self._paused  = False
        # UI Dashboard/Cameras sahifasida emas bo'lsa frame ni emit qilmaslik —
        # QImage konversiyasi va Qt signal trafigini drastik kamaytiradi.
        self._emit_frames = True
        self._reader: CV2RTSPReader | None = None

        # CameraService (ai_camera_service arxitekturasi)
        self._svc = None          # CameraService singleton
        self._cam_id: int = id(self)   # unique per worker

        # Detection tahlili alohida servisda; worker faqat loop va signal oqimini yuritadi.
        self._detection_analyzer = PersonDetectionAnalyzer(self.cfg)
        self._tracker = self._detection_analyzer.tracker
        self._track_statuses = self._detection_analyzer.track_statuses
        self._last_persons: list[dict] = []
        self._last_result_ts: float | None = None  # oxirgi qayta ishlangan result

        # Polygon zone cache
        self._poly_np: np.ndarray | None = None
        self._poly_frame_size: tuple | None = None

        # FPS
        self._frame_count   = 0
        self._fps           = 0.0
        self._fps_samples: deque[float] = deque(maxlen=30)
        self._last_fps_ts: float | None = None

        # Eski testlar/private chaqiruvlar sinmasligi uchun aliaslar qoldiriladi.
        self._today_count = 0
        self._detections_today = 0
        self._seen_detection_tracks: set[int] = set()
        self._saved_violations = self._violation_runtime.saved_violations
        self._spatial_violations = self._violation_runtime.spatial_violations
        self._no_helmet_frames = self._violation_runtime.no_helmet_frames
        self._access_frames = self._violation_runtime.access_frames

        self._face_last_recog: dict[int, float] = {}

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
                self._violation_runtime.notifier = self._notifier
            except Exception as e:
                _log.error("Telegram yuklanmadi: %s", e)

        if self.cfg.backend_enabled:
            try:
                from app.infrastructure.notifications.backend_client import BackendClient
                self._backend = BackendClient(
                    api_url  = self.cfg.get("backend_url",      ""),
                    login    = self.cfg.get("backend_login",    ""),
                    password = self.cfg.get("backend_password", ""),
                )
                self._violation_runtime.backend = self._backend
            except Exception as e:
                _log.error("Backend yuklanmadi: %s", e)

    def _setup_faceid(self):
        try:
            full_cfg = getattr(self.cfg, "_base", self.cfg)
            svc = FaceIdService(self.db, full_cfg)
            svc.enroll_from_settings_users()
            self.faceid_service = svc
        except Exception as e:
            self.faceid_service = None
            _log.warning("FaceID tayyorlanmadi: %s", e)

    def _try_recognize_face(self, frame: np.ndarray, person: dict):
        if self.faceid_service is None:
            return
        tid = person.get("track_id", -1)
        now = time.perf_counter()
        if now - self._face_last_recog.get(tid, 0) < 5.0:
            return
        self._face_last_recog[tid] = now
        crop = self._crop_person(frame, person)
        if crop is None:
            return
        # Upper 45% of bounding box — yuz shu qismda bo'ladi
        h = crop.shape[0]
        face_region = crop[:max(32, int(h * 0.45)), :]
        face = self.faceid_service._extract_face(face_region)
        if face is None:
            face = self.faceid_service._extract_face(crop)
        if face is None:
            return
        identity = self.faceid_service.match_person_crop(crop)
        name = identity.employee_name or "Unknown" if identity else "Unknown"
        confidence = identity.confidence if identity else 0.0
        matched = identity.matched if identity else False
        emp_id = identity.employee_id if identity else None
        self.face_recognized.emit({
            "track_id": tid,
            "cam_id": self._cam_id,
            "timestamp": time.time(),
            "crop_frame": face_region,
            "employee_name": name,
            "employee_id": emp_id,
            "confidence": confidence,
            "matched": matched,
        })

    # ── Natijalarni tahlil ────────────────────────────────────────────────

    def _process_detections(self, detections: list[dict]) -> list[dict]:
        return self._detection_analyzer.process(detections)

    @staticmethod
    def _pad_box(box: list, pad: int) -> list:
        return PersonDetectionAnalyzer.pad_box(box, pad)

    def _inner_status(self, person_box: list, green_boxes: list, red_boxes: list) -> str:
        return self._detection_analyzer.inner_status(person_box, green_boxes, red_boxes)

    @staticmethod
    def _box_overlaps(outer: list, inner: list, threshold: float = 0.3) -> bool:
        return PersonDetectionAnalyzer.box_overlaps(outer, inner, threshold)

    def _check_violations(self, persons: list[dict]) -> list[dict]:
        persons = self._violation_runtime.mark_no_helmet_candidates(persons)
        self._no_helmet_frames = self._violation_runtime.no_helmet_frames
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

    # ── Polygon zone filtrlash ────────────────────────────────────────────

    def _get_poly_np(self, fw: int, fh: int) -> np.ndarray | None:
        pts = self.cfg.polygon_points
        if len(pts) < 3:
            return None
        key = (fw, fh)
        if self._poly_frame_size != key:
            self._poly_np = np.array(
                [[p[0] * fw, p[1] * fh] for p in pts], dtype=np.float32
            ).reshape(-1, 1, 2)
            self._poly_frame_size = key
        return self._poly_np

    @staticmethod
    def _in_zone(person: dict, poly: np.ndarray) -> bool:
        box = person.get("box") or person.get("bbox_xyxy", [])
        if len(box) < 4:
            return True
        cx = float((box[0] + box[2]) / 2.0)
        cy = float(box[3])  # feet position
        return cv2.pointPolygonTest(poly, (cx, cy), False) >= 0

    def _filter_by_polygon(self, persons: list[dict], frame: np.ndarray) -> list[dict]:
        if frame is None or frame.size == 0:
            return persons
        h, w = frame.shape[:2]
        poly = self._get_poly_np(w, h)
        if poly is None:
            return persons
        return [p for p in persons if self._in_zone(p, poly)]

    # ── Overlay chizish ───────────────────────────────────────────────────

    def _draw_overlay(self, frame: np.ndarray, persons: list[dict]) -> np.ndarray:
        return draw_helmet_overlay(
            frame, persons,
            self.cfg.polygon_points,
            getattr(self.cfg, "polygon_color", "#f97316"),
        )

    # ── Buzilish saqlash ──────────────────────────────────────────────────

    def _start_violation_writer(self):
        self._violation_runtime.start_writer(self._cam_id)

    def _stop_violation_writer(self):
        self._violation_runtime.stop_writer()

    def _violation_writer_loop(self):
        self._violation_runtime._writer_loop()

    def _handle_violation(self, frame: np.ndarray, person: dict, violation_type: str = "no_helmet"):
        self._violation_runtime.handle_violation(frame, person, violation_type)
        self._today_count = self._violation_runtime.today_count

    def _update_detection_counter(self, persons: list[dict]) -> None:
        for person in persons:
            try:
                track_id = int(person.get("track_id"))
            except (TypeError, ValueError):
                continue
            if track_id not in self._seen_detection_tracks:
                self._seen_detection_tracks.add(track_id)
                self._detections_today += 1

    @staticmethod
    def _box_center_size(person: dict) -> tuple[float, float, float]:
        return ViolationRuntime.box_center_size(person)

    def _prune_spatial_violations(self, now: float):
        self._violation_runtime.prune_spatial_violations(now)

    def _is_spatial_duplicate(self, person: dict, violation_type: str) -> bool:
        return self._violation_runtime.is_spatial_duplicate(person, violation_type)

    def _remember_spatial_violation(self, person: dict, violation_type: str):
        self._violation_runtime.remember_spatial_violation(person, violation_type)

    # ── Yordamchi metodlar ────────────────────────────────────────────────

    def _resize_for_display(self, frame: np.ndarray) -> np.ndarray:
        return resize_for_display(frame, int(self.cfg.get("display_max_width", 640)))

    @staticmethod
    def _to_qimage(frame: np.ndarray):
        return frame_to_qimage(frame)

    def _emit_frame(self, frame: np.ndarray):
        if not self._emit_frames:
            return
        if frame is None or frame.size == 0:
            return
        display = self._resize_for_display(frame)
        qimg = self._to_qimage(display)
        if qimg is None or qimg.isNull():
            return
        self.frame_ready.emit(qimg)

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
        self._violation_runtime.today_count = self._today_count
        self._violation_runtime.set_running(True)
        # Oldingi sessiyada saqlangan deteksiya sonini yuklash
        self._detections_today = self.db.get_daily_detections(self.cfg.camera_name)

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
                reconnect_delay      = int(self.cfg.get("reconnect_delay", 3)),
                max_reconnects       = int(self.cfg.get("max_reconnects", 10)),
                target_fps           = int(self.cfg.get("video_fps_limit", 25)),
                on_reconnect_attempt = self._on_reconnect_attempt,
                on_max_retries       = self._on_max_retries,
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
        last_no_frame_emit = 0.0

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
                time.sleep(remaining)
                continue

            # ── Frame olish ───────────────────────────────────────────────
            if is_stream:
                current_id = getattr(self._reader, "frame_count", self._frame_count)
                if current_id == last_frame_id:
                    if (
                        not self._reader.is_connected
                        or getattr(self._reader, "latency_ms", 0.0) > 15_000
                    ) and now - last_no_frame_emit >= 2.0:
                        last_no_frame_emit = now
                        self.stats_updated.emit({
                            "fps": 0.0, "today_count": self._violation_runtime.today_count,
                            "detections_today": self._detections_today,
                            "active_persons": 0, "connected": False, "ping_ms": None,
                        })
                        self.status_changed.emit("Qayta ulanmoqda...")
                    # Yangi frame yo'q — video_interval yarmigacha kutish (busy-wait kamaytirish)
                    time.sleep(min(0.020, video_interval * 0.5))
                    continue

                ok, frame = self._reader.get_frame()
                connected = self._reader.is_connected
                if not ok:
                    no_frame_count += 1
                    if no_frame_count % 40 == 0:
                        self.stats_updated.emit({
                            "fps": 0.0, "today_count": self._violation_runtime.today_count,
                            "detections_today": self._detections_today,
                            "active_persons": 0, "connected": False, "ping_ms": None,
                        })
                        self.status_changed.emit("Qayta ulanmoqda...")
                    time.sleep(0.1)
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
                    self._update_detection_counter(persons)
                    persons = self._check_violations(persons)
                    persons = self._filter_by_polygon(persons, frame)
                    self._last_persons = persons

                    violation_frame = result.raw_frame if result.raw_frame is not None else frame
                    for p in persons:
                        if p.get("is_new_violation", False):
                            self._handle_violation(violation_frame, p, "no_helmet")
                        if p.get("has_helmet") is False:
                            self._try_recognize_face(violation_frame, p)

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
                        "today_count":    self._violation_runtime.today_count,
                        "detections_today": self._detections_today,
                        "active_persons": len(persons),
                        "connected":      connected,
                        "ping_ms":        self._ping_ms() if connected else None,
                    })
                    self.status_changed.emit(
                        f"Ulangan | FPS: {self._fps:.1f} | Bugun: {self._violation_runtime.today_count}"
                        if connected else "Qayta ulanmoqda..."
                    )
                    self.db.set_daily_detections(self.cfg.camera_name, self._detections_today)

            else:
                # ── Video-only rejim ──────────────────────────────────────
                self._emit_frame(frame)

                if self._frame_count % max(1, video_fps) == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._violation_runtime.today_count,
                        "detections_today": self._detections_today,
                        "active_persons": 0,
                        "connected":      connected,
                        "ping_ms":        self._ping_ms() if connected else None,
                    })
                    self.status_changed.emit(
                        f"Ulangan | FPS: {self._fps:.1f}"
                        if connected else "Qayta ulanmoqda..."
                    )
                    self.db.set_daily_detections(self.cfg.camera_name, self._detections_today)

        self._cleanup()

    # ── Tozalash ──────────────────────────────────────────────────────────

    def _cleanup(self):
        # Deteksiya sonini saqlash (to'xtatishda ham)
        try:
            self.db.set_daily_detections(self.cfg.camera_name, self._detections_today)
        except Exception:
            pass

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
        self._violation_runtime.set_running(False)
        self._stop_violation_writer()
        self._violation_runtime.clear()
        self.status_changed.emit("To'xtatildi")

    # ── Tashqi boshqaruv ──────────────────────────────────────────────────

    def request_stop(self):
        self._running = False
        if self._reader and hasattr(self._reader, "request_stop"):
            self._reader.request_stop()

    def stop(self):
        self.request_stop()
        self.wait(800)

    def reconnect(self):
        """Qayta ulash tugmasidan chaqiriladi — backoff ni reset qilib darhol qayta urinadi."""
        if self._reader and hasattr(self._reader, "reset_backoff"):
            self._reader.reset_backoff()
            self._reader._running = True  # max_retries dan keyin to'xtagan bo'lishi mumkin
            if not self._reader.is_alive():
                self._reader.start()
        self._running = True

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

    def set_emit_frames(self, enabled: bool):
        """UI dan chaqiriladi — sahifa Dashboard/Cameras emas bo'lsa False."""
        self._emit_frames = bool(enabled)

    # ── Reconnect callbacklar (CV2RTSPReader dan) ─────────────────────────

    def _on_reconnect_attempt(self, attempt: int, wait_sec: float):
        self.status_changed.emit(
            f"Qayta ulanmoqda... ({attempt}-urinish, {int(wait_sec)}s dan keyin)"
        )

    def _on_max_retries(self):
        self.error_occurred.emit(
            "Kameraga ulanib bo'lmadi (10 urinish). "
            "\"↻ Reconnect\" tugmasini bosing."
        )
        self._running = False
