"""
DetectionWorker — QThread asosida real-time helmet detection.

SmartHelmet loyihasini sys.path orqali import qilib,
HelmetDetector + HelmetTracker + TelegramNotifier ishlatadi.
Frame'larni signal orqali GUI ga uzatadi.
"""

import sys
import os
import time
import threading
import subprocess
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import cv2

from PyQt6.QtCore import QThread, pyqtSignal

from app.core.database import ViolationsDB


# ── FFmpeg RTSP o'quvchi (SmartHelmet dan ko'chirilgan, standalone) ────────

class _FFmpegReader(threading.Thread):
    """Minimal FFmpeg RTSP reader — GUI threadidan mustaqil."""

    def __init__(self, rtsp_url: str, reconnect_delay: int = 3, max_reconnects: int = 20):
        super().__init__(daemon=True)
        self.rtsp_url        = rtsp_url
        self.reconnect_delay = reconnect_delay
        self.max_reconnects  = max_reconnects

        self._frame          = None
        self._lock           = threading.Lock()
        self._running        = True
        self._connected      = False
        self._reconnect_count = 0
        self._proc           = None
        self._hw_mode        = "unknown"

        self.out_width  = 1280
        self.out_height = 720
        self.fps        = 25.0

    def _probe(self):
        try:
            cmd = [
                "ffprobe", "-v", "error", "-rtsp_transport", "tcp",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json", self.rtsp_url,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            d = json.loads(r.stdout).get("streams", [])
            if d:
                s = d[0]
                w = int(s.get("width", 1280))
                h = int(s.get("height", 720))
                num, den = s.get("r_frame_rate", "25/1").split("/")
                fps = float(num) / max(float(den), 1.0)
                return w, h, fps
        except Exception:
            pass
        return 1280, 720, 25.0

    @staticmethod
    def _scale(w, h, max_w=1280):
        if w <= max_w:
            return (w // 2) * 2, (h // 2) * 2
        scale = max_w / w
        return max_w, (int(h * scale) // 2) * 2

    def _try_first_frame(self, proc, frame_size, timeout=5.0):
        result = {"data": None}
        def _r():
            try:
                result["data"] = proc.stdout.read(frame_size)
            except Exception:
                pass
        t = threading.Thread(target=_r, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            try:
                proc.kill()
            except Exception:
                pass
            return None
        return result["data"]

    def _open_ffmpeg(self, w, h):
        ow, oh = self._scale(w, h)
        fsize  = ow * oh * 3
        pre  = [
            "ffmpeg", "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer+discardcorrupt",
            "-flags", "low_delay",
            "-strict", "experimental",
        ]
        post = [
            "-i", self.rtsp_url, "-an",
            "-vf", f"scale={ow}:{oh}",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
        ]
        for name, opts in [
            ("Intel QSV", ["-hwaccel", "qsv", "-c:v", "h264_qsv"]),
            ("D3D11VA",   ["-hwaccel", "d3d11va"]),
            ("Software",  []),
        ]:
            try:
                proc = subprocess.Popen(
                    pre + opts + post,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=fsize * 2,
                )
                raw = self._try_first_frame(proc, fsize, timeout=5.0)
                if raw and len(raw) == fsize:
                    frame = np.frombuffer(raw, np.uint8).reshape((oh, ow, 3))
                    with self._lock:
                        self._frame = frame
                    self._hw_mode   = name
                    self.out_width  = ow
                    self.out_height = oh
                    return proc, fsize
                else:
                    try:
                        proc.kill(); proc.wait(timeout=2)
                    except Exception:
                        pass
            except Exception:
                pass
        return None, fsize

    def run(self):
        while self._running:
            if self._reconnect_count > self.max_reconnects:
                break
            proc = None
            try:
                w, h, self.fps = self._probe()
                proc, fsize = self._open_ffmpeg(w, h)
                if proc is None:
                    raise RuntimeError("FFmpeg ochilmadi")
                self._proc = proc
                self._connected = True
                self._reconnect_count = 0

                while self._running:
                    raw = proc.stdout.read(fsize)
                    if len(raw) < fsize:
                        break
                    frame = np.frombuffer(raw, np.uint8).reshape(
                        (self.out_height, self.out_width, 3)
                    )
                    with self._lock:
                        self._frame = frame
            except Exception:
                pass
            finally:
                self._connected = False
                self._proc = None
                if proc:
                    try:
                        proc.kill(); proc.wait(timeout=3)
                    except Exception:
                        pass

            if self._running:
                self._reconnect_count += 1
                time.sleep(self.reconnect_delay)

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    @property
    def is_connected(self):
        return self._connected

    def stop(self):
        self._running = False
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass
        self.join(timeout=5.0)


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
        if not sh_path or not Path(sh_path).exists():
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
        status_color = (0, 200, 0) if connected else (0, 0, 220)
        status_text  = "ULANГАН" if connected else "ULANMOQDA..."
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

        timestamp = int(time.time())
        box = person.get("box", [])

        # Rasm kesish
        crop_path = ""
        full_path = ""
        if len(box) == 4 and self.cfg.save_violations:
            x1, y1, x2, y2 = map(int, box)
            y1a = max(y1 - 10, 0)
            x1a = max(x1 - 5,  0)
            x2a = min(x2 + 5,  frame.shape[1])
            y2a = min(y2 + 5,  frame.shape[0])

            crop = frame[y1a:y2a, x1a:x2a].copy()
            full = frame.copy()
            cv2.rectangle(full, (x1, y1), (x2, y2), (0, 0, 220), 3)

            vdir = self.cfg.violations_dir
            vdir.mkdir(parents=True, exist_ok=True)

            dt_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S")
            crop_path = str(vdir / f"crop_{dt_str}_id{track_id}.jpg")
            full_path = str(vdir / f"full_{dt_str}_id{track_id}.jpg")

            if crop.size > 0:
                cv2.imwrite(crop_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            cv2.imwrite(full_path, full, [cv2.IMWRITE_JPEG_QUALITY, 92])

        # DB ga yozish
        self.db.add_violation(
            track_id    = track_id,
            crop_path   = crop_path,
            full_path   = full_path,
            camera_name = self.cfg.camera_name,
            confidence  = float(person.get("score", 0.0)),
            timestamp   = timestamp,
        )
        self._today_count = self.db.get_today_count()

        # Signal
        violation_data = {
            "track_id":   track_id,
            "timestamp":  timestamp,
            "crop_path":  crop_path,
            "full_path":  full_path,
            "camera":     self.cfg.camera_name,
            "confidence": float(person.get("score", 0.0)),
            "crop_frame": frame[
                max(int(box[1]) - 10, 0):min(int(box[3]) + 5, frame.shape[0]),
                max(int(box[0]) - 5,  0):min(int(box[2]) + 5, frame.shape[1]),
            ].copy() if len(box) == 4 else None,
        }
        self.violation_detected.emit(violation_data)

        # Telegram
        if self._notifier:
            try:
                self._notifier.send_violation_photos(
                    violation_data.get("crop_frame"),
                    frame.copy(),
                    track_id, timestamp
                )
            except Exception as e:
                print(f"[Worker] Telegram xato: {e}")

    # ── QThread.run() ─────────────────────────────────────────────────────

    def run(self):
        self._running = True
        self._today_count = self.db.get_today_count()

        # Model yuklash
        self.status_changed.emit("Model yuklanmoqda...")
        if not self._import_smarthelmet():
            self._running = False
            return
        self.model_loaded.emit()
        self.status_changed.emit("Kameraga ulanmoqda...")

        # RTSP yoki video ochish
        rtsp_url = self.cfg.rtsp_url
        is_stream = rtsp_url.startswith(("rtsp://", "rtmp://"))

        if is_stream:
            self._reader = _FFmpegReader(
                rtsp_url,
                reconnect_delay = int(self.cfg.get("reconnect_delay", 3)),
                max_reconnects  = int(self.cfg.get("max_reconnects", 20)),
            )
            self._reader.start()

            # Birinchi frame'ni kutish (20 soniya)
            deadline = time.time() + 20
            while time.time() < deadline and self._running:
                ok, _ = self._reader.get_frame()
                if ok:
                    break
                time.sleep(0.1)
        else:
            # Fayl
            self._reader = cv2.VideoCapture(rtsp_url)

        step = int(self.cfg.get("process_every_n", 1))
        raw_count = 0

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            # Frame o'qish
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

            t0 = time.perf_counter()

            try:
                # Detection
                results = self._detector.detect_objects(frame)

                # Polygon filter
                results["person_detections"] = self._apply_polygon_filter(
                    results.get("person_detections", [])
                )

                # Tracker
                updated = self._tracker.update_helmet_status(results, self._detector)

                # Buzilishlarni tekshirish
                for person in updated:
                    if person.get("is_new_violation", False):
                        self._handle_violation(frame, person)

                # Overlay chizish
                dt = time.perf_counter() - t0
                self._frame_count += 1
                self._total_time  += dt
                self._fps = 1.0 / (self._total_time / self._frame_count) if self._frame_count else 0

                display = self._draw_overlay(
                    frame.copy(), updated,
                    self._fps, self._today_count,
                    self.cfg.camera_name, connected,
                )

                self.frame_ready.emit(display)

                # Stats signali (har 30 frame)
                if self._frame_count % 30 == 0:
                    self.stats_updated.emit({
                        "fps":            self._fps,
                        "today_count":    self._today_count,
                        "active_persons": len(updated),
                        "connected":      connected,
                    })
                    if connected:
                        self.status_changed.emit(
                            f"Ulanган  |  FPS: {self._fps:.1f}  |  "
                            f"Bugun: {self._today_count} buzilish"
                        )
                    else:
                        self.status_changed.emit("Qayta ulanmoqda...")

            except Exception as e:
                print(f"[Worker] Frame xatosi: {e}")
                self.frame_ready.emit(frame)

        # Tozalash
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
