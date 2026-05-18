"""Kamera workerlarini boshqaradigan runtime controller.

Bu modul GUI chizmaydi. Uning vazifasi: kameralarni ishga tushirish,
to'xtatish, qayta ulash, pauza qilish va workerlardan kelgan oxirgi holatlarni
cache qilib UIga signal orqali uzatish.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.config.settings_manager import CameraConfigProxy
from app.workers.camera_service import svc_destroy
from app.workers.cleanup_worker import CleanupWorker
from app.workers.detection_worker import DetectionWorker


class CameraRuntimeController(QObject):
    """Barcha kamera workerlari uchun yagona lifecycle boshqaruvchisi."""

    frame_ready = pyqtSignal(int, object)
    violation_detected = pyqtSignal(dict)
    stats_updated = pyqtSignal(int, dict)
    status_changed = pyqtSignal(int, str)
    error_occurred = pyqtSignal(int, str)
    model_loaded = pyqtSignal(int)
    runtime_status = pyqtSignal(str)
    cleanup_status = pyqtSignal(str)
    pause_changed = pyqtSignal(bool)

    def __init__(self, config_manager, db, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.db = db

        self._workers: dict[int, DetectionWorker] = {}
        self._stopping_workers: list[DetectionWorker] = []
        self._cleanup_worker: CleanupWorker | None = None
        self.persons_per_cam: dict[int, int] = {}
        self.latest_stats: dict[int, dict] = {}
        self.latest_status: dict[int, str] = {}
        self.latest_errors: dict[int, str] = {}
        self.model_loaded_cameras: set[int] = set()

    @property
    def worker_count(self) -> int:
        return len(self._workers)

    def start_camera(self, cam: dict) -> bool:
        """Bitta kamera uchun DetectionWorker yaratadi va signallarni ulaydi."""
        cam_id = cam.get("id")
        if cam_id in self._workers and self._workers[cam_id].isRunning():
            return False

        proxy = CameraConfigProxy(self.cfg, cam)
        worker = DetectionWorker(proxy, self.db)
        worker.frame_ready.connect(lambda frame, cid=cam_id: self.frame_ready.emit(cid, frame))
        worker.violation_detected.connect(self.violation_detected.emit)
        worker.stats_updated.connect(lambda stats, cid=cam_id: self._on_stats(cid, stats))
        worker.status_changed.connect(lambda text, cid=cam_id: self._on_status(cid, text))
        worker.error_occurred.connect(lambda msg, cid=cam_id: self._on_error(cid, msg))
        worker.model_loaded.connect(lambda cid=cam_id: self._on_model_loaded(cid))
        worker.finished.connect(lambda w=worker: self._forget_stopping_worker(w))

        worker.start()
        self._workers[cam_id] = worker
        return True

    def start_all(self) -> bool:
        cameras = self.cfg.get_enabled_cameras()
        if not cameras:
            self.runtime_status.emit("Faol kamera yo'q")
            return False

        if self.cfg.ai_model_enabled:
            self.runtime_status.emit(f"{len(cameras)} ta kamera uchun model yuklanmoqda...")
        else:
            self.runtime_status.emit(f"{len(cameras)} ta kameraga ulanmoqda...")

        for cam in cameras:
            self.start_camera(cam)
        self.pause_changed.emit(False)
        return True

    def stop_all(self) -> None:
        running = [w for w in self._workers.values() if w and w.isRunning()]
        for worker in running:
            if hasattr(worker, "request_stop"):
                worker.request_stop()
            else:
                worker._running = False
        for worker in running:
            worker.wait(1200)
        pending = [w for w in running if w.isRunning()]
        self._stopping_workers.extend(w for w in pending if w not in self._stopping_workers)

        self._workers.clear()
        self.persons_per_cam.clear()
        self.pause_changed.emit(False)
        svc_destroy()

    def restart_all(self, after_ms: int = 500) -> None:
        self.stop_all()
        QTimer.singleShot(after_ms, self.start_all)

    def reconnect_camera(self, cam_id: int) -> bool:
        """
        Yengil qayta ulanish — worker to'xtatilmaydi, faqat backoff reset qilinadi.
        Worker allaqachon to'xtatilgan bo'lsa to'liq restart qilinadi.
        """
        worker = self._workers.get(cam_id)
        if worker and worker.isRunning():
            worker.reconnect()
            self.runtime_status.emit(f"CAM {cam_id:02d}: qayta ulanmoqda...")
            return True
        return self.restart_camera(cam_id)

    def restart_camera(self, cam_id: int, after_ms: int = 250) -> bool:
        worker = self._workers.pop(cam_id, None)
        if worker and worker.isRunning():
            worker.stop()
            if worker.isRunning() and worker not in self._stopping_workers:
                self._stopping_workers.append(worker)

        cam = self.cfg.get_camera_by_id(cam_id)
        if not cam or not cam.get("enabled", True):
            self.runtime_status.emit(f"CAM {cam_id:02d}: kamera faol emas")
            return False

        self.runtime_status.emit(f"CAM {cam_id:02d}: qayta ulanmoqda...")
        QTimer.singleShot(after_ms, lambda c=cam: self.start_camera(c))
        return True

    def start_cleanup(self) -> None:
        if self._cleanup_worker and self._cleanup_worker.isRunning():
            return
        self._cleanup_worker = CleanupWorker(
            self.db,
            self.cfg,
            keep_days=int(self.cfg.get("keep_files_days", 7)),
            cleanup_files=bool(self.cfg.get("cleanup_files", False)),
        )
        self._cleanup_worker.finished_cleanup.connect(
            lambda info: self.cleanup_status.emit(
                f"Cleanup OK: {info.get('keep_days')} kun, {info.get('deleted_files')} fayl"
            )
        )
        self._cleanup_worker.error_occurred.connect(
            lambda msg: self.cleanup_status.emit(f"Cleanup xato: {msg[:60]}")
        )
        self._cleanup_worker.start()

    def toggle_pause_all(self) -> bool | None:
        if not self._workers:
            return None
        first = next(iter(self._workers.values()), None)
        if not first:
            return None

        paused = not first.is_paused()
        self.set_paused(paused)
        return paused

    def set_paused(self, paused: bool) -> None:
        for worker in self._workers.values():
            if paused:
                worker.pause()
            else:
                worker.resume()
        self.pause_changed.emit(paused)

    def _on_stats(self, cam_id: int, stats: dict) -> None:
        self.latest_stats[cam_id] = dict(stats)
        if stats.get("connected", False):
            self.latest_errors.pop(cam_id, None)
        self.persons_per_cam[cam_id] = stats.get("active_persons", 0)
        self.stats_updated.emit(cam_id, stats)

    def _on_status(self, cam_id: int, text: str) -> None:
        self.latest_status[cam_id] = text
        self.status_changed.emit(cam_id, text)

    def _on_error(self, cam_id: int, msg: str) -> None:
        self.latest_errors[cam_id] = msg
        self.error_occurred.emit(cam_id, msg)

    def _on_model_loaded(self, cam_id: int) -> None:
        self.model_loaded_cameras.add(cam_id)
        self.model_loaded.emit(cam_id)

    def _forget_stopping_worker(self, worker: DetectionWorker) -> None:
        if worker in self._stopping_workers:
            self._stopping_workers.remove(worker)
