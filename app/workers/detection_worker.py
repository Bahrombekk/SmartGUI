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
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.infrastructure.camera.cv2_rtsp_reader import CV2RTSPReader
from app.workers.camera_service import svc_acquire, svc_register, svc_unregister
from app.workers.inference_engine import IoUTracker


_NO_HELMET_KEYS = ("no_helmet", "no-helmet", "without", "head", "bare", "violation", "nohel")
_HELMET_KEYS    = ("helmet", "with_helmet", "safe", "hardhat", "hard_hat")


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

        self._running = False
        self._paused  = False
        self._reader: CV2RTSPReader | None = None

        # CameraService (ai_camera_service arxitekturasi)
        self._svc = None          # CameraService singleton
        self._cam_id: int = id(self)   # unique per worker

        # Tracker
        self._tracker = IoUTracker(iou_thresh=0.25, max_age=80)
        self._last_persons: list[dict] = []
        self._last_result_ts: float | None = None  # oxirgi qayta ishlangan result

        # FPS
        self._frame_count   = 0
        self._fps           = 0.0
        self._fps_samples: deque[float] = deque(maxlen=30)
        self._last_fps_ts: float | None = None

        # Violations
        self._today_count         = 0
        self._saved_violations:   set[int]       = set()
        self._no_helmet_frames:   dict[int, int] = {}
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

    # ── Natijalarni tahlil ────────────────────────────────────────────────

    def _classify_person(self, person: dict) -> dict:
        cname = person.get("class_name", person.get("class", "")).lower()
        if any(k in cname for k in _NO_HELMET_KEYS):
            person["has_helmet"] = False
        elif any(k in cname for k in _HELMET_KEYS):
            person["has_helmet"] = True
        else:
            person["has_helmet"] = None
        return person

    def _check_violations(self, persons: list[dict]) -> list[dict]:
        threshold  = int(self.cfg.get("confirmation_threshold", 10))
        active_ids = {p["track_id"] for p in persons}
        self._no_helmet_frames = {
            k: v for k, v in self._no_helmet_frames.items() if k in active_ids
        }
        for p in persons:
            tid = p["track_id"]
            if p.get("has_helmet") is False:
                self._no_helmet_frames[tid] = self._no_helmet_frames.get(tid, 0) + 1
                p["is_new_violation"] = (
                    self._no_helmet_frames[tid] == threshold
                    and tid not in self._saved_violations
                )
            else:
                self._no_helmet_frames[tid] = 0
                p["is_new_violation"] = False
        return persons

    # ── Overlay chizish ───────────────────────────────────────────────────

    @staticmethod
    def _draw_overlay(frame: np.ndarray, persons: list[dict]) -> np.ndarray:
        h, w = frame.shape[:2]

        for p in persons:
            box     = p.get("box", p.get("bbox_xyxy", []))
            tid     = p.get("track_id", -1)
            has_hel = p.get("has_helmet")
            if len(box) < 4:
                continue
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])

            if has_hel is True:
                color = (0, 200, 0);   label = f"HELMET  ID:{tid}"
            elif has_hel is False:
                color = (0, 0, 220);   label = f"NO HELMET  ID:{tid}"
            else:
                color = (0, 140, 255); label = f"PERSON  ID:{tid}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            lsz = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0]
            cv2.rectangle(frame, (x1, y1 - lsz[1] - 8), (x1 + lsz[0] + 4, y1), color, -1)

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
                    notifier       = self._notifier,
                    backend        = self._backend,
                )
                self._today_count = self.db.get_today_count()
                payload = event.to_payload()
                payload["today_count"] = self._today_count
                self.violation_detected.emit(payload)
            except Exception as e:
                tid = int(item.get("track_id", -1))
                if tid >= 0:
                    self._saved_violations.discard(tid)
                self.error_occurred.emit(f"Buzilishni saqlashda xatolik: {e}")
            finally:
                self._save_queue.task_done()

    def _handle_violation(self, frame: np.ndarray, person: dict):
        tid = person.get("track_id", -1)
        if tid in self._saved_violations:
            return
        self._saved_violations.add(tid)
        try:
            self._save_queue.put_nowait({
                "track_id": tid,
                "frame": frame.copy(),
                "person": dict(person),
                "camera_name": self.cfg.camera_name,
                "company_id": self.cfg.company_id,
                "violations_dir": self.cfg.violations_dir,
                "save_files": self.cfg.save_violations,
            })
        except Full:
            self._saved_violations.discard(tid)
            self.error_occurred.emit("Buzilish saqlash navbati to'lib qoldi")

    # ── Yordamchi metodlar ────────────────────────────────────────────────

    def _resize_for_display(self, frame: np.ndarray) -> np.ndarray:
        max_w = int(self.cfg.get("display_max_width", 960))
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

            # ── Frame olish ───────────────────────────────────────────────
            if is_stream:
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
                ok, frame = self._reader.read()
                connected = ok
                if not ok:
                    self._running = False
                    self.status_changed.emit("Video fayl tugadi")
                    break

            # ── Video rate limiting ───────────────────────────────────────
            now = time.perf_counter()
            remaining = video_interval - (now - last_emit_ts)
            if remaining > 0.008:
                # Uzoq kutish — to'liq uxla
                time.sleep(remaining - 0.005)
                continue
            elif remaining > 0:
                # Qisqa kutish — spin (Windows timer 15ms dan yaxshiroq)
                continue

            current_id = getattr(self._reader, "frame_count", self._frame_count)
            if current_id == last_frame_id:
                time.sleep(0.005)
                continue

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
                    classified = [self._classify_person(dict(d)) for d in result.detections]
                    persons    = self._tracker.update(classified)
                    persons    = self._check_violations(persons)
                    self._last_persons = persons

                    violation_frame = result.raw_frame if result.raw_frame is not None else frame
                    for p in persons:
                        if p.get("is_new_violation", False):
                            self._handle_violation(violation_frame, p)

                persons = self._last_persons

                # Display doim live framedan quriladi; raw_frame faqat violation
                # saqlash uchun ishlatiladi.
                display_frame = self._draw_overlay(frame.copy(), persons)
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
