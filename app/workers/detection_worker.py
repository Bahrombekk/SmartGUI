"""
DetectionWorker — yaxshilangan versiya.

  - Pool: har 3 ta kameraga 1 ta model (InferenceEnginePool)
  - IoUTracker: velocity prediction + centre-distance fallback
  - FPS: video 25fps, AI 12fps, batch interval 10ms
"""
from __future__ import annotations

import time

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from app.application.services.violation_service import ViolationService
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.infrastructure.camera.cv2_rtsp_reader import CV2RTSPReader
from app.workers.inference_engine import IoUTracker, pool_acquire, pool_release


_NO_HELMET_KEYS = ("no_helmet", "no-helmet", "without", "head", "bare", "violation", "nohel")
_HELMET_KEYS    = ("helmet", "with_helmet", "safe", "hardhat", "hard_hat")


class DetectionWorker(QThread):
    """
    Bitta kamera uchun background detection thread'i.

    Signals:
        frame_ready(QImage)      — ko'rsatishga tayyor frame (BGR→RGB konversiya bu thread'da)
        violation_detected(dict) — yangi buzilish
        stats_updated(dict)      — fps, today_count, active_persons, connected
        status_changed(str)      — holat matni
        error_occurred(str)      — xatolik
        model_loaded()           — model yuklandi
    """

    frame_ready        = pyqtSignal(object)  # QImage yoki numpy (backward compat)
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
        self._reader  = None

        # AI
        self._engine = None  # InferenceEngine | None
        self._tracker = IoUTracker(iou_thresh=0.25, max_age=80)
        self._last_persons: list[dict] = []
        self._last_ai_ts: float = 0.0

        # FPS
        self._frame_count   = 0
        self._fps           = 0.0
        self._fps_samples: list[float] = []
        self._last_fps_ts: float | None = None

        # Violations
        self._today_count         = 0
        self._saved_violations:   set[int]       = set()
        self._no_helmet_frames:   dict[int, int] = {}

        # Notifiers
        self._notifier = None
        self._backend  = None

    # ── Model / Engine ────────────────────────────────────────────────────

    def _init_engine(self) -> bool:
        """Pool'dan engine oladi (har 3 ta kameraga 1 model). False → AI o'chirilgan."""
        if not bool(self.cfg.get("ai_model_enabled", False)):
            self.status_changed.emit("Video rejim (AI o'chirilgan)")
            return False

        self._engine = pool_acquire(id(self), self.cfg)
        if self._engine is None:
            self.error_occurred.emit("InferenceEngine yaratilmadi — video rejimda ishlaydi")
            return False

        self.model_loaded.emit()
        self.status_changed.emit("AI tayyor")
        return True

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
        """'class' nomidan helmet/no-helmet aniqlaydi."""
        cname = person.get("class", "").lower()
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
    def _draw_overlay(frame: np.ndarray, persons: list[dict],
                      fps: float, today_count: int,
                      cam_name: str, connected: bool) -> np.ndarray:
        h, w = frame.shape[:2]

        for p in persons:
            box     = p.get("box", [])
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
            #cv2.putText(frame, label, (x1 + 2, y1 - 4),
                        #cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        status_col  = (0, 200, 0) if connected else (0, 150, 220)
        status_text = "ULANGAN" if connected else "ULANMOQDA..."
        cv2.rectangle(frame, (0, 0), (w, 36), (10, 14, 20), -1)
        #cv2.putText(frame, f"  {cam_name}", (6, 22),
        #            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        # cv2.putText(frame, f"FPS: {fps:.1f}", (w - 160, 22),
        #             cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
        # cv2.putText(frame, status_text, (w - 280, 22),
        #             cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_col, 1)
        #viol_txt = f"Bugun: {today_count} buzilish"
        cv2.rectangle(frame, (0, h - 32), (w, h), (10, 14, 20), -1)
        # cv2.putText(frame, viol_txt, (8, h - 10),
        #             cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 100, 30), 1)
        return frame

    # ── Buzilish saqlash ──────────────────────────────────────────────────

    def _handle_violation(self, frame: np.ndarray, person: dict):
        tid = person.get("track_id", -1)
        if tid in self._saved_violations:
            return
        self._saved_violations.add(tid)
        event = self.violation_service.register_violation(
            frame          = frame,
            person         = person,
            camera_name    = self.cfg.camera_name,
            company_id     = self.cfg.company_id,
            violations_dir = self.cfg.violations_dir,
            save_files     = self.cfg.save_violations,
            notifier       = self._notifier,
            backend        = self._backend,
        )
        self._today_count = self.db.get_today_count()
        self.violation_detected.emit(event.to_payload())

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
        """
        BGR numpy → QImage. BU WORKER THREAD'DA BAJARILADI.
        Asosiy thread faqat QPixmap.fromImage() qiladi → ~10x kam CPU.
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)

    def _emit_frame(self, frame: np.ndarray):
        """Resize + BGR→RGB + QImage → emit. Hammasi worker thread'da."""
        display = self._resize_for_display(frame)
        self.frame_ready.emit(self._to_qimage(display))

    def _update_fps(self, now: float):
        if self._last_fps_ts is not None:
            dt = now - self._last_fps_ts
            self._fps_samples.append(dt)
            if len(self._fps_samples) > 30:
                self._fps_samples.pop(0)
            avg = sum(self._fps_samples) / len(self._fps_samples)
            self._fps = 1.0 / avg if avg > 0 else 0.0
        self._last_fps_ts = now

    def _ping_ms(self) -> float | None:
        if self._reader and hasattr(self._reader, "latency_ms"):
            return float(self._reader.latency_ms)
        return 0.0

    # ── Asosiy loop ───────────────────────────────────────────────────────

    def run(self):
        self._running     = True
        self._today_count = self.db.get_today_count()

        self.status_changed.emit("Yuklanmoqda...")
        has_ai = self._init_engine()
        self._setup_notifiers()

        rtsp_url = self.cfg.rtsp_url
        if not rtsp_url:
            self.error_occurred.emit("RTSP URL ko'rsatilmagan")
            self._running = False
            return

        self.status_changed.emit("Kameraga ulanmoqda...")

        is_stream = rtsp_url.startswith(("rtsp://", "rtmp://"))

        if is_stream:
            self._reader = CV2RTSPReader(
                rtsp_url,
                reconnect_delay = int(self.cfg.get("reconnect_delay", 3)),
                max_reconnects  = int(self.cfg.get("max_reconnects", 999)),
                target_fps      = int(self.cfg.get("video_fps_limit", 25)),
            )
            self._reader.start()
        else:
            self._reader = cv2.VideoCapture(rtsp_url)

        # Interval parametrlari
        video_fps     = max(1, int(self.cfg.get("video_fps_limit", 25)))
        ai_fps        = max(1, int(self.cfg.get("ai_fps_limit", 12)))
        video_interval = 1.0 / video_fps
        ai_interval    = 1.0 / ai_fps

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
            if remaining > 0:
                time.sleep(max(0.001, remaining - 0.001))
                continue

            # Bir xil frame'ni qayta chiqarmaslik (RTSP buffer stuck)
            current_id = getattr(self._reader, "frame_count", self._frame_count)
            if current_id == last_frame_id:
                time.sleep(0.001)
                continue

            last_emit_ts  = now
            last_frame_id = current_id
            self._update_fps(now)
            self._frame_count += 1

            # ── AI inference ──────────────────────────────────────────────
            if has_ai and self._engine is not None:
                should_run_ai = (now - self._last_ai_ts) >= ai_interval

                if should_run_ai:
                    self._engine.submit(id(self), frame)  # id(self) = unique per camera
                    self._last_ai_ts = now

                result = self._engine.get_result(id(self))
                persons = self._last_persons

                if result is not None:
                    raw_detections, det_frame = result

                    # Har bir detectionni classify qil
                    classified = [self._classify_person(dict(d)) for d in raw_detections]

                    # IoU tracker bilan stable IDlar
                    persons = self._tracker.update(classified)

                    # Violation confirmation
                    persons = self._check_violations(persons)
                    self._last_persons = persons

                    for p in persons:
                        if p.get("is_new_violation", False):
                            self._handle_violation(det_frame, p)

                    # Detection aynan qaysi frame'da qilingan bo'lsa, box ham o'sha frame'ga chiziladi.
                    display_frame = self._draw_overlay(
                        det_frame.copy(), persons, self._fps,
                        self._today_count, self.cfg.camera_name, connected,
                    )
                    self._emit_frame(display_frame)
                else:
                    self._emit_frame(frame)

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
                # ── Video-only rejim (AI o'chirilgan) ────────────────────
                # cv2.cvtColor bu yerda — worker thread, asosiy thread EMAS
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
        if self._reader:
            if hasattr(self._reader, "stop"):
                self._reader.stop()
            elif hasattr(self._reader, "release"):
                self._reader.release()
        pool_release(id(self))
        self._tracker.reset()
        self.status_changed.emit("To'xtatildi")

    # ── Tashqi boshqaruv ──────────────────────────────────────────────────

    def stop(self):
        self._running = False
        self.wait(2500)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused
