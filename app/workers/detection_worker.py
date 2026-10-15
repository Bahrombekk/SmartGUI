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
from datetime import date

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from app.application.services.detection_analysis import PersonDetectionAnalyzer
from app.application.services.faceid_service import FaceIdService, TrackIdentity
from app.application.services.violation_runtime import ViolationRuntime
from app.domain.policies import AccessPolicy
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.infrastructure.camera.cv2_rtsp_reader import CV2RTSPReader
from app.workers.camera_service import svc_acquire, svc_register, svc_unregister
from app.shared.utils.rate_gate import RateGate
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
        self._last_result_completed_at: float | None = None
        self._prev_result_ts: float | None = None      # bir oldingi result timestamp
        self._det_interval_ema: float | None = None     # detection orasidagi real interval (sek)
        self._last_display_emit_ts: float = 0.0
        self._display_gate: RateGate | None = None
        # None — config'dagi display_max_width (kichik plitka); katta oynadagi
        # kamera uchun controller kattaroq o'lcham beradi (set_display_width)
        self._display_width: int | None = None

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
        self._stats_date: date = date.today()   # kunlik hisoblagichlar qaysi kunga tegishli
        self._saved_violations = self._violation_runtime.saved_violations
        self._spatial_violations = self._violation_runtime.spatial_violations
        self._no_helmet_frames = self._violation_runtime.no_helmet_frames
        self._access_frames = self._violation_runtime.access_frames

        self._face_last_recog: dict[int, float] = {}
        self._track_ident: TrackIdentity | None = None
        self._face_last_any = 0.0

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
        reader = self._reader
        error = svc_register(self._cam_id, reader, svc=self._svc)
        if not self._running or reader is not self._reader:
            return
        if error:
            # Model yuklanmadi — video ishlashda davom etadi, lekin foydalanuvchi bilsin
            _log.error("Kamera %s: %s", self._cam_id, error)
            self.error_occurred.emit(f"{error}\nVideo AI tahlilisiz ko'rsatilmoqda.")
            self.status_changed.emit("Video rejim (AI xato)")
            return
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
        if not (self.cfg.get("faceid_enabled", False) or self.cfg.get("access_roster_enabled", False)):
            self.faceid_service = None
            return
        try:
            full_cfg = getattr(self.cfg, "_base", self.cfg)
            svc = FaceIdService(self.db, full_cfg)
            svc.enroll_from_settings_users()
            self.faceid_service = svc
            self._track_ident = TrackIdentity(svc)
        except Exception as e:
            self.faceid_service = None
            _log.warning("FaceID tayyorlanmadi: %s", e)

    FACE_SAMPLE_INTERVAL = 1.0   # bitta odam uchun soniyasiga ko'pi bilan 1 ta yuz tahlili
    FACE_CAMERA_INTERVAL = 0.25  # kamera bo'yicha: 0.25 s da ko'pi bilan 1 ta (~30–40 ms CPU)

    def _try_recognize_face(self, frame: np.ndarray, person: dict, force: bool = False):
        """
        Shlemsiz odamning yuzini track bo'yicha yig'ib taniydi (TrackIdentity):
        uzoq kamerada bitta kadr emas, eng yaxshi bir necha kadr birlashtiriladi.
        Tanilgan bo'lsa natija `person` ga yoziladi; buzilish avvalroq xodimsiz
        saqlangan bo'lsa, u ham yangilanadi. Xodim aniqlangach bu track uchun hisob to'xtaydi.
        """
        if self.faceid_service is None or self._track_ident is None \
                or not self.cfg.get("faceid_enabled", False):
            return
        tid = person.get("track_id", -1)
        known = self._track_ident.identity(tid)
        if known is not None:
            self._apply_identity(person, known)
            return
        now = time.perf_counter()
        if not force and (now - self._face_last_recog.get(tid, 0) < self.FACE_SAMPLE_INTERVAL
                          or now - self._face_last_any < self.FACE_CAMERA_INTERVAL):
            return
        if len(self._face_last_recog) > 2000:   # uzoq ishlaganda lug'at cheksiz o'smasin
            self._face_last_recog.clear()
        self._face_last_recog[tid] = now
        self._face_last_any = now
        crop = self._crop_person(frame, person)
        if crop is None:
            return
        sample = self.faceid_service.analyze(crop)
        if sample is None:
            return  # yuz topilmadi, juda kichik yoki burilgan
        identity = self._track_ident.add(tid, sample)
        if identity is None:
            return  # hali yetarli kadr yo'q
        h = crop.shape[0]
        face_region = crop[:max(32, int(h * 0.45)), :]
        matched = identity.matched
        name = identity.employee_name if matched else "Noma'lum"
        confidence = identity.confidence
        emp_id = identity.employee_id if matched else None
        if matched:
            self._apply_identity(person, identity)
            try:
                self.db.update_violation_identity(
                    int(tid), self.cfg.camera_name, emp_id, name, confidence,
                    since_ts=int(time.time()) - 900)
            except Exception as exc:
                _log.debug("Buzilishga xodimni qo'shib bo'lmadi: %s", exc)
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

    @staticmethod
    def _apply_identity(person: dict, identity) -> None:
        person["employee_id"] = identity.employee_id
        person["employee_name"] = identity.employee_name
        person["identity_confidence"] = identity.confidence

    # ── Natijalarni tahlil ────────────────────────────────────────────────

    def _process_detections(self, detections: list[dict], ts: float | None = None) -> list[dict]:
        return self._detection_analyzer.process(detections, ts=ts)

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
    def _extrapolate_box(p: dict, t: float, frame_shape: tuple[int, int] | None = None) -> dict:
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
            if frame_shape is not None:
                h, w = frame_shape[:2]
                box = [
                    max(0.0, min(float(w - 1), box[0])),
                    max(0.0, min(float(h - 1), box[1])),
                    max(0.0, min(float(w), box[2])),
                    max(0.0, min(float(h), box[3])),
                ]
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

    def _check_day_rollover(self, today: date | None = None) -> bool:
        """Yarim tun o'tgan bo'lsa kunlik hisoblagichlarni yangi kunga o'tkazadi.

        Aks holda kechagi deteksiya soni bugungi daily_stats qatoriga yozilardi va
        _seen_detection_tracks cheksiz o'sardi. True — kun almashdi."""
        today = today or date.today()
        if today == self._stats_date:
            return False
        self._stats_date = today
        self._seen_detection_tracks.clear()
        try:
            self._detections_today = int(self.db.get_daily_detections(self.cfg.camera_name))
        except Exception:
            self._detections_today = 0
        try:
            today_count = int(self.db.get_today_count())
            camera_today = int(self.db.get_today_count_for_camera(
                getattr(self.cfg, "camera_id", None), self.cfg.camera_name))
        except Exception:
            today_count = camera_today = 0
        self._today_count = today_count
        self._violation_runtime.reset_day(today_count, camera_today)
        return True

    def _prune_dead_tracks(self) -> None:
        """Tracker unutgan track ID lariga oid lug'atlarni tozalaydi."""
        live = getattr(self._tracker, "live_track_ids", None)
        if live is None:
            return
        live_ids = live()
        if self._seen_detection_tracks:
            self._seen_detection_tracks &= live_ids
        for tid in [t for t in self._face_last_recog if t not in live_ids]:
            del self._face_last_recog[tid]
        self._violation_runtime.prune_tracks(live_ids)

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
        width = self._display_width or int(self.cfg.get("display_max_width", 640))
        return resize_for_display(frame, width)

    def set_display_width(self, width: int | None):
        """UI dan: katta oynadagi kamera to'liq sifatda, plitkalar kichik o'lchamda."""
        self._display_width = int(width) if width else None

    @staticmethod
    def _to_qimage(frame: np.ndarray):
        return frame_to_qimage(frame)

    def _should_emit_frame(self) -> bool:
        """display_fps_limit ga ko'ra frame emit qilish vaqti kelganini tekshiradi.
        True qaytarsa — emit oynasini band qiladi (timestamp yangilanadi), shuning
        uchun overlay chizish faqat haqiqatan emit qilinadigan framelar uchun bajariladi.
        """
        if not self._emit_frames:
            return False
        now = time.perf_counter()
        if self._display_gate is None:
            display_fps = max(1, int(self.cfg.get(
                "display_fps_limit",
                min(int(self.cfg.get("video_fps_limit", 25)), 25),
            )))
            # Token-bucket: qattiq interval notekis keladigan RTSP kadrlarning
            # yarmini tashlardi (o'lchangan: 15.7 → 7.7 fps).
            self._display_gate = RateGate(display_fps, burst=2.0)
        if not self._display_gate.try_take(now):
            return False
        self._last_display_emit_ts = now
        return True

    def _emit_frame(self, frame: np.ndarray):
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
        try:
            self._run_body()
        except Exception as e:
            _log.error("DetectionWorker (%s) kutilmagan xato: %s",
                       self.cfg.camera_name, e)
            self.error_occurred.emit(f"Kamera xatoligi: {e}")
        finally:
            self._cleanup()

    def _run_body(self):
        self._running     = True
        # Track ID lar jarayon bo'yicha yagona — worker qayta ishga tushganda eski
        # buzilishlar (FaceID yangilanishi track_id bo'yicha) boshqa odamga o'tmasin
        self._tracker.enable_global_ids()
        self._stats_date  = date.today()
        self._today_count = self.db.get_today_count()
        self._violation_runtime.today_count = self._today_count
        self._violation_runtime.camera_today = self.db.get_today_count_for_camera(
            self.cfg.camera_id, self.cfg.camera_name)
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
        if "<kamera-ip>" in rtsp_url or "<login>" in rtsp_url:
            # Standart namuna manzil — ulanishga urinish befoyda
            self.error_occurred.emit("Kamera manzili hali kiritilmagan — Sozlamalar → Kameralar")
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
            # Ekran uchun tartibli navbat — start()dan oldin (birinchi kadrlar ham tushsin)
            self._reader.subscribe("display", maxlen=40)
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

        if is_stream:
            self._run_stream_loop(has_ai)
            return

        video_fps      = max(1, int(self.cfg.get("video_fps_limit", 25)))
        video_interval = 1.0 / video_fps
        # Stream: token-bucket — o'rtacha tezlik video_fps bilan cheklanadi, lekin
        # to'p-to'p kelgan kadrlar tashlanmaydi (qattiq interval 20 FPS kamerani
        # ~7 FPS gacha tushirardi va trekingni buzardi).
        video_gate     = RateGate(video_fps, burst=2.0)

        last_emit_ts   = 0.0
        last_frame_id  = -1
        no_frame_count = 0
        last_no_frame_emit = 0.0

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            # ── Frame olish ───────────────────────────────────────────────
            if is_stream:
                # Yangi kadrni polling'siz kutamiz (kelishi bilan uyg'onadi)
                wait_new = getattr(self._reader, "wait_new_frame", None)
                if wait_new is not None:
                    has_new = wait_new(last_frame_id, 0.25)
                else:  # pragma: no cover — eski reader
                    time.sleep(0.01)
                    has_new = getattr(self._reader, "frame_count", self._frame_count) != last_frame_id
                now = time.perf_counter()
                current_id = getattr(self._reader, "frame_count", self._frame_count)
                if not has_new or current_id == last_frame_id:
                    if (
                        not self._reader.is_connected
                        or getattr(self._reader, "latency_ms", 0.0) > 15_000
                    ) and now - last_no_frame_emit >= 2.0:
                        last_no_frame_emit = now
                        self.stats_updated.emit({
                            "fps": 0.0, "today_count": self._violation_runtime.camera_today,
                            "detections_today": self._detections_today,
                            "active_persons": 0, "connected": False, "ping_ms": None,
                        })
                        self.status_changed.emit("Qayta ulanmoqda...")
                    if not self._reader.is_connected:
                        time.sleep(0.05)   # ulanmagan kamera — CPU/GIL band qilinmasin
                    continue
                if not video_gate.try_take(now):
                    last_frame_id = current_id   # limitdan tez — bu kadr o'tkaziladi
                    continue
            else:
                # ── Video fayl: qattiq interval (fayl o'z tezligida o'qiladi) ──
                now = time.perf_counter()
                remaining = video_interval - (now - last_emit_ts)
                if remaining > 0.008:
                    time.sleep(remaining - 0.005)
                    continue
                elif remaining > 0:
                    time.sleep(remaining)
                    continue

            if is_stream:
                ok, frame = self._reader.get_frame()
                connected = self._reader.is_connected
                if not ok:
                    no_frame_count += 1
                    if no_frame_count % 40 == 0:
                        self.stats_updated.emit({
                            "fps": 0.0, "today_count": self._violation_runtime.camera_today,
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
                    # Detectionlar orasidagi REAL intervalni o'lchaymiz (capture
                    # timestamplari bo'yicha). Velocity px/detection-update da
                    # bo'lgani uchun extrapolyatsiya shu interval bilan to'g'ri
                    # masshtablanadi — ai_fps_limit ga tayanmaymiz.
                    self._prev_result_ts = self._last_result_ts
                    self._last_result_ts = result.timestamp
                    self._last_result_completed_at = getattr(result, "completed_at", None) or time.perf_counter()
                    if (
                        self._prev_result_ts is not None
                        and result.timestamp is not None
                    ):
                        di = result.timestamp - self._prev_result_ts
                        if 0.0 < di < 2.0:
                            self._det_interval_ema = (
                                di if self._det_interval_ema is None
                                else 0.6 * self._det_interval_ema + 0.4 * di
                            )
                    self._check_day_rollover()
                    persons = self._process_detections(result.detections)
                    self._prune_dead_tracks()
                    self._update_detection_counter(persons)
                    # Avval zona filtri, keyin buzilish tekshiruvi: zonadan tashqarida
                    # chegaraga yetgan odam zonaga kirganda ham qayd etilsin.
                    persons = self._filter_by_polygon(persons, frame)
                    persons = self._check_violations(persons)
                    self._last_persons = persons

                    violation_frame = result.raw_frame if result.raw_frame is not None else frame
                    for p in persons:
                        if p.get("is_new_violation", False):
                            # Avval yuz — buzilish yozuvi xodim bilan saqlansin
                            self._try_recognize_face(violation_frame, p, force=True)
                            self._handle_violation(violation_frame, p, "no_helmet")
                        elif p.get("has_helmet") is False:
                            self._try_recognize_face(violation_frame, p)

                persons = self._last_persons

                # Display doim live framedan quriladi; raw_frame faqat violation
                # saqlash uchun ishlatiladi. Overlay/extrapolyatsiya faqat
                # haqiqatan emit qilinadigan framelar uchun bajariladi (CPU tejash).
                if self._should_emit_frame():
                    draw_persons = persons
                    # Detection eskirgan bo'lsa boxni velocity bilan oldinga suramiz.
                    if persons and self._last_result_ts is not None:
                        source_elapsed = max(0.0, now - self._last_result_ts)
                        interval = self._det_interval_ema or (
                            1.0 / max(1, int(self.cfg.get("ai_fps_limit", 10)))
                        )
                        interval = max(0.02, interval)
                        # t = nechta detection-update oldinga (velocity birligi bilan mos)
                        t = min(source_elapsed / interval, 2.0)
                        if t > 0.1:
                            draw_persons = [
                                self._extrapolate_box(p, t, frame.shape) for p in persons
                            ]
                    display_frame = self._draw_overlay(frame, draw_persons)
                    self._emit_frame(display_frame)

                if self._frame_count % 30 == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._violation_runtime.camera_today,
                        "detections_today": self._detections_today,
                        "active_persons": len(persons),
                        "connected":      connected,
                        "ping_ms":        self._ping_ms() if connected else None,
                    })
                    self.status_changed.emit(
                        f"Ulangan | FPS: {self._fps:.1f} | Bugun: {self._violation_runtime.camera_today} buzilish"
                        if connected else "Qayta ulanmoqda..."
                    )
                    self._check_day_rollover()
                    self.db.set_daily_detections(self.cfg.camera_name, self._detections_today)

            else:
                # ── Video-only rejim ──────────────────────────────────────
                if self._should_emit_frame():
                    self._emit_frame(frame)

                if self._frame_count % max(1, video_fps) == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._violation_runtime.camera_today,
                        "detections_today": self._detections_today,
                        "active_persons": 0,
                        "connected":      connected,
                        "ping_ms":        self._ping_ms() if connected else None,
                    })
                    self.status_changed.emit(
                        f"Ulangan | FPS: {self._fps:.1f}"
                        if connected else "Qayta ulanmoqda..."
                    )
                    self._check_day_rollover()
                    self.db.set_daily_detections(self.cfg.camera_name, self._detections_today)

    # ── Oqim sikli: tartibli AI natijalari + jitter buffer ────────────────

    def _handle_result(self, result) -> list[dict]:
        """Bitta AI natijasini (vaqt tartibida) tracker va qaror mantiqidan o'tkazadi."""
        ts = result.timestamp
        if self._last_result_ts is not None and ts is not None:
            di = ts - self._last_result_ts
            if 0.0 < di < 2.0:
                self._det_interval_ema = (di if self._det_interval_ema is None
                                          else 0.6 * self._det_interval_ema + 0.4 * di)
        self._prev_result_ts = self._last_result_ts
        self._last_result_ts = ts
        self._last_result_completed_at = getattr(result, "completed_at", None) or time.perf_counter()

        frame = result.raw_frame
        self._check_day_rollover()
        persons = self._process_detections(result.detections, ts=ts)
        self._prune_dead_tracks()
        self._update_detection_counter([p for p in persons if not p.get("coasting")])
        # Avval zona filtri, keyin buzilish tekshiruvi: zonadan tashqarida
        # chegaraga yetgan odam zonaga kirganda ham qayd etilsin.
        persons = self._filter_by_polygon(persons, frame)
        persons = self._check_violations(persons)
        self._last_persons = persons
        if frame is not None:
            for p in persons:
                if p.get("coasting"):
                    continue
                if p.get("is_new_violation", False):
                    # Avval yuz — buzilish yozuvi xodim bilan saqlansin
                    self._try_recognize_face(frame, p, force=True)
                    self._handle_violation(frame, p, "no_helmet")
                elif p.get("has_helmet") is False:
                    self._try_recognize_face(frame, p)
        return persons

    def _persons_for(self, ts: float, hist) -> list[dict]:
        """Ko'rsatilayotgan kadr vaqtiga mos odamlar: shu vaqtgacha bo'lgan oxirgi
        AI natijasi, kadr vaqtigacha tezlik (px/s) bilan suriladi."""
        if not hist:
            return []
        entry = None
        for h in reversed(hist):
            if h[0] <= ts:
                entry = h
                break
        if entry is None:
            entry = hist[0]
        dt = ts - entry[0]
        if dt > 1.0:          # AI natijasi juda eski — quti chizilmaydi (noto'g'ri joyda turmasin)
            return []
        dt = max(-0.3, min(dt, 0.5))
        if abs(dt) < 0.005:
            return entry[1]
        out = []
        for p in entry[1]:
            vxs, vys = p.get("vxs", 0.0), p.get("vys", 0.0)
            if abs(vxs) < 1.0 and abs(vys) < 1.0:
                out.append(p)
                continue
            q = dict(p)
            b = list(p.get("box", p.get("bbox_xyxy", [])))
            if len(b) == 4:
                dx, dy = vxs * dt, vys * dt
                q["box"] = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]
                q["bbox_xyxy"] = q["box"]
            out.append(q)
        return out

    def _run_stream_loop(self, has_ai: bool):
        """Kadrlar kamera vaqti (PTS) bo'yicha tekis ko'rsatiladi.

        Tarmoq kadrlarni to'p-to'p yetkazadi (1.2 s jimlikdan keyin 30 kadr birdan —
        o'lchangan). Oldin faqat oxirgi kadr olinardi: video sakrardi, tracker odamni
        yo'qotardi. Endi: kadr `ts + D` paytida ko'rsatiladi, D — so'nggi kelish
        kechikishlarining 90-persentili (moslashuvchan, `video_buffer_max_ms` gacha).
        AI natijalari ham tartib bilan qayta ishlanadi va qutilar aynan ko'rsatilayotgan
        kadr vaqtidagi natijadan chiziladi (video bilan sinxron)."""
        reader = self._reader
        max_d = max(0.0, float(self.cfg.get("video_buffer_max_ms", 600)) / 1000.0)
        buffer_on = bool(self.cfg.get("video_jitter_buffer", True)) and max_d > 0
        pending: deque = deque()
        lateness: deque = deque(maxlen=200)
        delay = 0.12 if buffer_on else 0.0
        hist: deque = deque(maxlen=60)     # (ts, persons) — AI natijalari tarixi
        last_total = -1
        last_no_frame_emit = 0.0
        n_seen = 0
        connected = False

        while self._running:
            if self._paused:
                reader.pop_frames("display")
                time.sleep(0.05)
                continue

            # ── AI natijalari (tartib bilan) ─────────────────────────────
            if has_ai and self._svc is not None:
                for res in self._svc.pop_results(self._cam_id):
                    persons = self._handle_result(res)
                    hist.append((res.timestamp, persons))

            # ── Yangi kadrlar ────────────────────────────────────────────
            for pk in reader.pop_frames("display"):
                n_seen += 1
                lateness.append(max(0.0, pk.arrival - pk.ts))
                if not pk.corrupt:          # buzilgan kadr ko'rsatilmaydi — oxirgi toza kadr turadi
                    pending.append(pk)
            if buffer_on and n_seen >= 25 and lateness:
                n_seen = 0
                lat = sorted(lateness)
                delay = min(max_d, max(0.06, lat[int(len(lat) * 0.9)] + 0.04))
            last_total = reader.frame_count

            now = time.perf_counter()
            connected = reader.is_connected
            if not pending:
                if (not connected or reader.latency_ms > 15_000) and now - last_no_frame_emit >= 2.0:
                    last_no_frame_emit = now
                    self.stats_updated.emit({
                        "fps": 0.0, "today_count": self._violation_runtime.camera_today,
                        "detections_today": self._detections_today,
                        "active_persons": 0, "connected": False, "ping_ms": None,
                    })
                    self.status_changed.emit("Qayta ulanmoqda...")
                reader.wait_new_frame(last_total, 0.05 if connected else 0.25)
                continue

            # ── Playout: vaqti kelgan kadrlar; kechiksak — eng yangi vaqtidagisi ──
            due = None
            while pending and pending[0].ts + delay <= now:
                due = pending.popleft()
            # Buferda juda ko'p to'plansa (uzoq jimlikdan keyin) — kechikish oshib ketmasin
            while len(pending) > 30:
                due = pending.popleft()
            if due is None:
                wait = pending[0].ts + delay - now
                if wait > 0.002:
                    reader.wait_new_frame(last_total, min(wait, 0.02))
                continue

            self._update_fps(due.ts)
            self._frame_count += 1
            persons = self._persons_for(due.ts, hist) if has_ai else []
            if self._emit_frames and self._should_emit_frame_at(due.ts):
                frame = due.frame.copy()          # kadr AI bilan umumiy — ustiga chizmaymiz
                display_frame = self._draw_overlay(frame, persons) if persons else frame
                self._emit_frame(display_frame)

            if self._frame_count % 30 == 0:
                live = [p for p in self._last_persons if not p.get("coasting")]
                self.stats_updated.emit({
                    "fps":            self._fps,
                    "today_count":    self._violation_runtime.camera_today,
                    "detections_today": self._detections_today,
                    "active_persons": len(live) if has_ai else 0,
                    "connected":      connected,
                    "ping_ms":        self._ping_ms() if connected else None,
                    "buffer_ms":      round(delay * 1000),
                    "corrupt_frames": getattr(reader, "corrupt_frames", 0),
                })
                if has_ai:
                    status = (f"Ulangan | FPS: {self._fps:.1f} | Bugun: "
                              f"{self._violation_runtime.camera_today} buzilish")
                else:
                    status = f"Ulangan | FPS: {self._fps:.1f}"
                self.status_changed.emit(status if connected else "Qayta ulanmoqda...")
                self._check_day_rollover()
                self.db.set_daily_detections(self.cfg.camera_name, self._detections_today)

    def _should_emit_frame_at(self, ts: float) -> bool:
        """Ekran tezligi limiti — kadr vaqti bo'yicha (playout allaqachon tekis)."""
        if self._display_gate is None:
            display_fps = max(1, int(self.cfg.get(
                "display_fps_limit", min(int(self.cfg.get("video_fps_limit", 25)), 25))))
            self._display_gate = RateGate(display_fps, burst=2.0)
        if not self._display_gate.try_take(ts):
            return False
        self._last_display_emit_ts = ts
        return True

    # ── Tozalash ──────────────────────────────────────────────────────────

    def _cleanup(self):
        # Deteksiya sonini saqlash (to'xtatishda ham)
        try:
            self.db.set_daily_detections(self.cfg.camera_name, self._detections_today)
        except Exception:
            pass

        # CameraService dan reader ni olib tashlaymiz
        if self._svc is not None:
            # Faqat o'z reader'imizni va o'z servisimizdan — yangi worker'nikiga tegmaymiz
            svc_unregister(self._cam_id, self._reader, svc=self._svc)

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

    def reconnect(self) -> bool:
        """Qayta ulash tugmasidan chaqiriladi — backoff ni reset qilib darhol qayta urinadi.

        False — reader yoki worker allaqachon to'xtagan (masalan max_reconnects'dan
        keyin). Tugagan thread'ni qayta start() qilib bo'lmaydi, shuning uchun
        chaqiruvchi worker'ni to'liq qayta yaratishi kerak."""
        reader = self._reader
        if not self._running or reader is None or not hasattr(reader, "reset_backoff"):
            return False
        if not reader.is_alive() or not getattr(reader, "_running", True):
            return False
        reader.reset_backoff()
        return True

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

    def _on_reconnect_attempt(self, attempt: int, wait_sec: float, reason: str = ""):
        if reason:
            # Xato sababi panelda ko'rinsin (masalan "Login yoki parol noto'g'ri")
            self.error_occurred.emit(f"{reason}\nQayta urinish {int(wait_sec)} s dan keyin ({attempt})")
        else:
            self.status_changed.emit(
                f"Qayta ulanmoqda... ({attempt}-urinish, {int(wait_sec)}s dan keyin)"
            )

    def _on_max_retries(self):
        """Reader max_reconnects dan keyin ham to'xtamaydi (har 60 s qayta urinadi) —
        worker ham ishlashda davom etadi, aks holda tungi uzilishdan keyin kamera
        qo'lda bosilmaguncha o'lik qolardi. Xabar har uzilish davrida bir marta chiqadi
        (reader har limitga yetganda bir marta chaqiradi)."""
        reason = getattr(self._reader, "last_error", "") if self._reader is not None else ""
        attempts = int(self.cfg.get("max_reconnects", 10))
        self.error_occurred.emit(
            (f"{reason}\n" if reason else "")
            + f"Kameraga ulanib bo'lmadi ({attempts} urinish). Har 60 s da qayta urinilmoqda —"
            " darhol urinish uchun \"Qayta ulash\" tugmasini bosing."
        )
