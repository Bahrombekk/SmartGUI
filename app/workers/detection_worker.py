"""
DetectionWorker — SmartHelmet'ga bog'liq bo'lmagan standalone detection.
Ultralytics YOLO + CV2RTSPReader orqali ishlaydi.
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal

from app.application.services.violation_service import ViolationService
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.infrastructure.camera.cv2_rtsp_reader import CV2RTSPReader


_NO_HELMET_KEYS = ("no_helmet", "no-helmet", "without", "head", "bare", "violation", "nohel")
_HELMET_KEYS    = ("helmet", "with_helmet", "safe", "hardhat", "hard_hat")


class DetectionWorker(QThread):
    """
    Arxa fon detection threadi.

    Signals:
        frame_ready(np.ndarray)  — qayta ishlangan frame
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

        self._running  = False
        self._paused   = False
        self._reader   = None
        self._model    = None

        self._frame_count   = 0
        self._fps           = 0.0
        self._today_count   = 0
        self._fps_samples: list[float] = []
        self._last_fps_ts: float | None = None

        self._saved_violations: set[int] = set()
        self._no_helmet_frames: dict[int, int] = {}

        self._notifier = None
        self._backend  = None

    # ── Model yuklash ─────────────────────────────────────────────────────

    def _load_model(self) -> bool:
        model_path = self.cfg.model_path
        if not model_path:
            self.status_changed.emit("Model yo'li ko'rsatilmagan — video rejim")
            return False

        p = Path(model_path)
        if not p.is_absolute():
            p = Path(__file__).parent.parent.parent / model_path
        if not p.exists():
            self.error_occurred.emit(f"Model topilmadi: {p}")
            return False

        try:
            from ultralytics import YOLO
            self._model = YOLO(str(p))

            use_gpu = bool(self.cfg.get("use_gpu", True))
            if use_gpu:
                try:
                    import torch
                    if torch.cuda.is_available():
                        self._model.to("cuda")
                except Exception:
                    pass

            self.model_loaded.emit()
            return True
        except Exception as e:
            self.error_occurred.emit(f"Model yuklanmadi: {e}")
            return False

    # ── Xabarnomalar ──────────────────────────────────────────────────────

    def _setup_notifiers(self):
        if self.cfg.telegram_enabled and self.cfg.telegram_token and self.cfg.telegram_chat_ids:
            try:
                from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
                self._notifier = TelegramNotifier(
                    self.cfg.telegram_token,
                    self.cfg.telegram_chat_ids,
                )
            except Exception as e:
                print(f"[Worker] Telegram yuklanmadi: {e}")

        if self.cfg.backend_enabled:
            try:
                from app.infrastructure.notifications.backend_client import BackendClient
                self._backend = BackendClient(
                    api_url  = self.cfg.get("backend_url", ""),
                    login    = self.cfg.get("backend_login", ""),
                    password = self.cfg.get("backend_password", ""),
                )
            except Exception as e:
                print(f"[Worker] Backend yuklanmadi: {e}")

    # ── Natijalarni tahlil qilish ─────────────────────────────────────────

    def _parse_results(self, results) -> list[dict]:
        persons = []
        if not results:
            return persons
        r = results[0]
        if r.boxes is None:
            return persons

        names = self._model.names
        for box in r.boxes:
            cls_id   = int(box.cls[0])
            conf     = float(box.conf[0])
            track_id = int(box.id[0]) if box.id is not None else -1
            xyxy     = box.xyxy[0].cpu().tolist()
            cname    = names.get(cls_id, str(cls_id)).lower()

            if any(k in cname for k in _NO_HELMET_KEYS):
                has_helmet = False
            elif any(k in cname for k in _HELMET_KEYS):
                has_helmet = True
            else:
                has_helmet = None

            persons.append({
                "track_id":  track_id,
                "box":       xyxy,
                "has_helmet": has_helmet,
                "score":     conf,
                "class":     cname,
            })
        return persons

    # ── Confirmation window ───────────────────────────────────────────────

    def _check_violations(self, persons: list[dict]) -> list[dict]:
        threshold = int(self.cfg.get("confirmation_threshold", 10))
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

    # ── Frame chizish ─────────────────────────────────────────────────────

    @staticmethod
    def _draw_overlay(frame, persons, fps, today_count, cam_name, connected):
        h, w = frame.shape[:2]

        for p in persons:
            box      = p.get("box", [])
            track_id = p.get("track_id", -1)
            has_hel  = p.get("has_helmet", None)
            if len(box) < 4:
                continue
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])

            if has_hel is True:
                color = (0, 200, 0)
                label = f"HELMET  ID:{track_id}"
            elif has_hel is False:
                color = (0, 0, 220)
                label = f"NO HELMET  ID:{track_id}"
            else:
                color = (0, 140, 255)
                label = f"PERSON  ID:{track_id}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            lsize = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0]
            cv2.rectangle(frame, (x1, y1 - lsize[1] - 8), (x1 + lsize[0] + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        status_color = (0, 200, 0) if connected else (0, 150, 220)
        status_text  = "ULANGAN" if connected else "ULANMOQDA..."
        cv2.rectangle(frame, (0, 0), (w, 36), (10, 14, 20), -1)
        cv2.putText(frame, f"  {cam_name}", (6, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(frame, f"FPS: {fps:.1f}", (w - 160, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
        cv2.putText(frame, status_text, (w - 280, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 1)

        viol_txt = f"Bugun: {today_count} buzilish"
        cv2.rectangle(frame, (0, h - 32), (w, h), (10, 14, 20), -1)
        cv2.putText(frame, viol_txt, (8, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 100, 30), 1)
        return frame

    # ── Buzilish qayta ishlash ────────────────────────────────────────────

    def _handle_violation(self, frame: np.ndarray, person: dict):
        track_id = person.get("track_id", -1)
        if track_id in self._saved_violations:
            return
        self._saved_violations.add(track_id)

        event = self.violation_service.register_violation(
            frame=frame,
            person=person,
            camera_name=self.cfg.camera_name,
            company_id=self.cfg.company_id,
            violations_dir=self.cfg.violations_dir,
            save_files=self.cfg.save_violations,
            notifier=self._notifier,
            backend=self._backend,
        )
        self._today_count = self.db.get_today_count()
        self.violation_detected.emit(event.to_payload())

    # ── QThread.run() ─────────────────────────────────────────────────────

    def run(self):
        self._running = True
        self._today_count = self.db.get_today_count()

        self.status_changed.emit("Yuklanmoqda...")
        has_detection = self._load_model()
        self._setup_notifiers()

        self.status_changed.emit("Kameraga ulanmoqda...")

        rtsp_url  = self.cfg.rtsp_url
        is_stream = rtsp_url.startswith(("rtsp://", "rtmp://"))

        if is_stream:
            self._reader = CV2RTSPReader(
                rtsp_url,
                reconnect_delay=int(self.cfg.get("reconnect_delay", 3)),
                max_reconnects=int(self.cfg.get("max_reconnects", 999)),
            )
            self._reader.start()
            deadline = time.time() + 25
            while time.time() < deadline and self._running:
                ok, _ = self._reader.get_frame()
                if ok:
                    break
                time.sleep(0.1)
        else:
            self._reader = cv2.VideoCapture(rtsp_url)

        step      = int(self.cfg.get("process_every_n", 1))
        raw_count = 0

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            if is_stream:
                ok, frame = self._reader.get_frame()
                connected = self._reader.is_connected
                if not ok:
                    self.status_changed.emit("Qayta ulanmoqda...")
                    time.sleep(0.05)
                    continue
            else:
                ok, frame = self._reader.read()
                connected = ok
                if not ok:
                    self._running = False
                    self.status_changed.emit("Video fayl tugadi")
                    break

            raw_count += 1
            if raw_count % step != 0:
                continue

            now = time.perf_counter()
            if self._last_fps_ts is not None:
                dt = now - self._last_fps_ts
                self._fps_samples.append(dt)
                if len(self._fps_samples) > 30:
                    self._fps_samples.pop(0)
                avg = sum(self._fps_samples) / len(self._fps_samples)
                self._fps = 1.0 / avg if avg > 0 else 0.0
            self._last_fps_ts = now
            self._frame_count += 1

            if not has_detection:
                display = self._draw_overlay(
                    frame.copy(), [], self._fps, self._today_count,
                    self.cfg.camera_name, connected,
                )
                self.frame_ready.emit(display)
                if self._frame_count % 30 == 0:
                    self.stats_updated.emit({
                        "fps": self._fps, "today_count": self._today_count,
                        "active_persons": 0, "connected": connected,
                    })
                    self.status_changed.emit(
                        f"Ulangan  |  FPS: {self._fps:.1f}" if connected
                        else "Qayta ulanmoqda..."
                    )
                continue

            try:
                half   = bool(self.cfg.get("half_precision", False))
                imgsz  = int(self.cfg.get("yolo_imgsz", 640))
                conf   = float(self.cfg.confidence)

                results = self._model.track(
                    frame,
                    persist=True,
                    conf=conf,
                    imgsz=imgsz,
                    half=half,
                    verbose=False,
                    tracker="bytetrack.yaml",
                )

                persons = self._parse_results(results)
                persons = self._check_violations(persons)

                for p in persons:
                    if p.get("is_new_violation", False):
                        self._handle_violation(frame, p)

                display = self._draw_overlay(
                    frame.copy(), persons, self._fps, self._today_count,
                    self.cfg.camera_name, connected,
                )
                self.frame_ready.emit(display)

                if self._frame_count % 30 == 0:
                    self.stats_updated.emit({
                        "fps": self._fps, "today_count": self._today_count,
                        "active_persons": len(persons), "connected": connected,
                    })
                    self.status_changed.emit(
                        f"Ulangan  |  FPS: {self._fps:.1f}  |  Bugun: {self._today_count}"
                        if connected else "Qayta ulanmoqda..."
                    )

            except Exception as e:
                print(f"[Worker] Frame xatosi: {e}")
                self.frame_ready.emit(frame)

        self._cleanup()

    def _cleanup(self):
        if self._reader:
            if hasattr(self._reader, "stop"):
                self._reader.stop()
            elif hasattr(self._reader, "release"):
                self._reader.release()
        self.status_changed.emit("To'xtatildi")

    # ── Tashqi boshqaruv ─────────────────────────────────────────────────

    def stop(self):
        self._running = False
        self.wait(8000)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused
