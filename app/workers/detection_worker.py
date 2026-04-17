import sys
import time
from pathlib import Path

import numpy as np
import cv2

from PyQt6.QtCore import QThread, pyqtSignal

from app.application.services.violation_service import ViolationService
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.infrastructure.camera.cv2_rtsp_reader import CV2RTSPReader


# ── DetectionWorker ────────────────────────────────────────────────────────

class DetectionWorker(QThread):
    """
    Arxa fon detection threadi.

    Signals:
        frame_ready(np.ndarray)  — qayta ishlangan frame (GUI ga)
        violation_detected(dict) — yangi buzilish ma'lumoti
        stats_updated(dict)      — fps, today_count, active_persons, connected
        status_changed(str)      — holat matni (status bar uchun)
        error_occurred(str)      — xatolik xabari
        model_loaded()           — model muvaffaqiyatli yuklandi
    """

    frame_ready       = pyqtSignal(object)   # np.ndarray
    violation_detected = pyqtSignal(dict)
    stats_updated     = pyqtSignal(dict)
    status_changed    = pyqtSignal(str)
    error_occurred    = pyqtSignal(str)
    model_loaded      = pyqtSignal()

    def __init__(self, config_manager, db: ViolationsDB, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.db  = db
        self.violation_service = ViolationService(db)

        self._running  = False
        self._paused   = False
        self._reader   = None

        # Statistika
        self._frame_count  = 0
        self._total_time   = 0.0
        self._fps          = 0.0
        self._today_count  = 0

        # Detector / Tracker (SmartHelmet modullaridan)
        self._detector = None
        self._tracker  = None
        self._notifier = None
        self._backend  = None

        # Saqlangan buzilishlar (track_id lar)
        self._saved_violations: set = set()

    # ── SmartHelmet import ─────────────────────────────────────────────────

    def _import_smarthelmet(self) -> bool:
        """SmartHelmet modullarini sys.path orqali import qilish."""
        sh_path = self.cfg.smarthelmet_path
        if not sh_path:
            return False  # Konfiguratsiya qilinmagan — video rejimi
        if not Path(sh_path).exists():
            self.error_occurred.emit(
                f"SmartHelmet papkasi topilmadi: {sh_path}\n"
                "Sozlamalarda to'g'ri yo'lni ko'rsating."
            )
            return False

        if sh_path not in sys.path:
            sys.path.insert(0, sh_path)

        try:
            from core.detector import HelmetDetector
            from core.tracker  import HelmetTracker

            # Config'ni vaqtincha o'zgartirish
            import config.config as conf_module
            conf_module.MODEL_PATH          = self.cfg.model_path
            conf_module.CONFIDENCE_THRESHOLD = self.cfg.confidence
            conf_module.TRACKER_TYPE        = self.cfg.get_tracker_config()
            conf_module.YOLO_IMGSZ          = int(self.cfg.get("yolo_imgsz", 1024))
            conf_module.USE_GPU             = bool(self.cfg.get("use_gpu", True))
            conf_module.HALF_PRECISION      = bool(self.cfg.get("half_precision", True))
            conf_module.HELMET_ZONE_BOTTOM  = float(self.cfg.get("helmet_zone_bottom", 0.35))
            conf_module.VIOLATION_COOLDOWN  = int(self.cfg.get("violation_cooldown", 10))
            conf_module.CONFIRMATION_WINDOW    = int(self.cfg.get("confirmation_window", 10))
            conf_module.CONFIRMATION_THRESHOLD = int(self.cfg.get("confirmation_threshold", 10))
            conf_module.CAMERA_NAME         = self.cfg.camera_name

            self._detector = HelmetDetector()
            self._tracker  = HelmetTracker()

            # Telegram (ixtiyoriy)
            if self.cfg.telegram_enabled:
                try:
                    from core.notifier import TelegramNotifier
                    conf_module.TELEGRAM_BOT_TOKEN = self.cfg.telegram_token
                    conf_module.TELEGRAM_CHAT_ID   = self.cfg.telegram_chat_ids
                    conf_module.TELEGRAM_BOT_ENABLED = True
                    self._notifier = TelegramNotifier()
                except Exception as e:
                    print(f"[Worker] Telegram yuklanmadi: {e}")
                    self._notifier = None

            # Backend (ixtiyoriy)
            if self.cfg.backend_enabled:
                try:
                    from core.backend_client import BackendClient
                    conf_module.BACKEND_API_URL = self.cfg.get("backend_url", "")
                    conf_module.LOGGIN_BK       = self.cfg.get("backend_login", "")
                    conf_module.PASSWORD_BK     = self.cfg.get("backend_password", "")
                    conf_module.COMPANY_ID      = self.cfg.get("company_id", "")
                    conf_module.USE_BACKEND_API = True
                    self._backend = BackendClient()
                except Exception as e:
                    print(f"[Worker] Backend yuklanmadi: {e}")
                    self._backend = None

            return True

        except Exception as e:
            self.error_occurred.emit(f"SmartHelmet import xatosi: {e}")
            return False

    # ── Polygon filter ────────────────────────────────────────────────────

    def _apply_polygon_filter(self, persons: list) -> list:
        """Polygon filtrni qo'llash (agar yoqilgan bo'lsa)."""
        if not self.cfg.use_polygon or not self.cfg.polygon_points:
            return persons

        try:
            import config.config as conf_module
            conf_module.POLYGON_POINTS    = [tuple(p) for p in self.cfg.polygon_points]
            conf_module.USE_POLYGON_FILTER = True

            from core.polygon_filter import PolygonFilter
            pf = PolygonFilter()
            return pf.filter_persons(persons)
        except Exception:
            return persons

    # ── Frame chizish ────────────────────────────────────────────────────

    @staticmethod
    def _draw_overlay(frame, persons, fps, today_count, cam_name, connected):
        """Frame ustiga detection natijalarini chizish."""
        h, w = frame.shape[:2]

        for p in persons:
            box      = p.get("box", [])
            track_id = p.get("track_id", -1)
            has_hel  = p.get("has_helmet", None)
            score    = p.get("score", 0.0)

            if len(box) < 4:
                continue

            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])

            if has_hel is True:
                color = (0, 200, 0)    # Yashil — helmet bor
                label = f"HELMET  ID:{track_id}"
            elif has_hel is False:
                color = (0, 0, 220)    # Qizil — helmet yo'q
                label = f"NO HELMET  ID:{track_id}"
            else:
                color = (0, 140, 255)  # Sariq — noma'lum
                label = f"PERSON  ID:{track_id}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            lsize = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0]
            cv2.rectangle(frame, (x1, y1 - lsize[1] - 8), (x1 + lsize[0] + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        # HUD: status bar
        status_color = (0, 200, 0) if connected else (0, 150, 220)
        status_text  = "ULANGAN" if connected else "ULANMOQDA..."
        cv2.rectangle(frame, (0, 0), (w, 36), (10, 14, 20), -1)
        cv2.putText(frame, f"  {cam_name}", (6, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(frame, f"FPS: {fps:.1f}", (w - 160, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
        cv2.putText(frame, status_text, (w - 280, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 1)

        # Bugungi buzilishlar
        viol_txt = f"Bugun: {today_count} buzilish"
        cv2.rectangle(frame, (0, h - 32), (w, h), (10, 14, 20), -1)
        cv2.putText(frame, viol_txt, (8, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 100, 30), 1)

        return frame

    # ── Buzilish qayta ishlash ────────────────────────────────────────────

    def _handle_violation(self, frame: np.ndarray, person: dict):
        """Yangi buzilishni saqlash va signallar yuborish."""
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
        self._fps_samples: list[float] = []
        self._last_fps_ts: float | None = None

        self.status_changed.emit("Yuklanmoqda...")
        has_detection = self._import_smarthelmet()
        if has_detection:
            self.model_loaded.emit()

        self.status_changed.emit("Kameraga ulanmoqda...")

        # RTSP yoki video ochish
        rtsp_url = self.cfg.rtsp_url
        is_stream = rtsp_url.startswith(("rtsp://", "rtmp://"))

        if is_stream:
            self._reader = CV2RTSPReader(
                rtsp_url,
                reconnect_delay = int(self.cfg.get("reconnect_delay", 3)),
                max_reconnects  = int(self.cfg.get("max_reconnects", 50)),
            )
            self._reader.start()

            deadline = time.time() + 20
            while time.time() < deadline and self._running:
                ok, _ = self._reader.get_frame()
                if ok:
                    break
                time.sleep(0.1)
        else:
            self._reader = cv2.VideoCapture(rtsp_url)

        step = int(self.cfg.get("process_every_n", 1))
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

            # Frame-to-frame FPS hisoblash
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

            # ── Video rejimi (SmartHelmet yo'q) ──────────────────────────
            if not has_detection:
                display = self._draw_overlay(
                    frame.copy(), [],
                    self._fps, self._today_count,
                    self.cfg.camera_name, connected,
                )
                self.frame_ready.emit(display)

                if self._frame_count % 30 == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._today_count,
                        "active_persons": 0,
                        "connected":      connected,
                    })
                    self.status_changed.emit(
                        f"Ulangan  |  FPS: {self._fps:.1f}" if connected
                        else "Qayta ulanmoqda..."
                    )
                continue

            # ── Detection rejimi ──────────────────────────────────────────
            try:
                results = self._detector.detect_objects(frame)

                results["person_detections"] = self._apply_polygon_filter(
                    results.get("person_detections", [])
                )

                updated = self._tracker.update_helmet_status(results, self._detector)

                for person in updated:
                    if person.get("is_new_violation", False):
                        self._handle_violation(frame, person)

                display = self._draw_overlay(
                    frame.copy(), updated,
                    self._fps, self._today_count,
                    self.cfg.camera_name, connected,
                )
                self.frame_ready.emit(display)

                if self._frame_count % 30 == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._today_count,
                        "active_persons": len(updated),
                        "connected":      connected,
                    })
                    if connected:
                        self.status_changed.emit(
                            f"Ulangan  |  FPS: {self._fps:.1f}  |  "
                            f"Bugun: {self._today_count} buzilish"
                        )
                    else:
                        self.status_changed.emit("Qayta ulanmoqda...")

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
