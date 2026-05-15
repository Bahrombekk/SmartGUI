"""DetectionWorker uchun violation duplicate/cooldown va yozish navbati.

Worker frame loopni boshqaradi, bu modul esa buzilish eventini saqlash uchun
navbatga qo'yadi, bir odamdan ketma-ket duplicate event chiqmasligini nazorat
qiladi va background writer threadni yuritadi.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from queue import Empty, Full, Queue
from typing import Callable

import numpy as np

from app.application.services.violation_service import ViolationService


class ViolationRuntime:
    """Buzilishlarni throttle qiladi va DB/file/notification yozuvini fon threadga beradi."""

    def __init__(self, cfg, db, *, emit_payload: Callable[[dict], None], emit_error: Callable[[str], None]):
        self.cfg = cfg
        self.db = db
        self.violation_service = ViolationService(db)
        self.emit_payload = emit_payload
        self.emit_error = emit_error

        self.today_count = 0
        self.saved_violations: set[tuple[int, str]] = set()
        self.spatial_violations: deque[dict] = deque(maxlen=256)
        self.no_helmet_frames: dict[int, int] = {}
        self.access_frames: dict[int, int] = {}
        self.notifier = None
        self.backend = None
        self._running = False
        self._save_queue: Queue[dict | None] = Queue(
            maxsize=max(1, int(cfg.get("violation_save_queue_size", 64)))
        )
        self._save_thread: threading.Thread | None = None
        # today_count / no_helmet_count cache — bir necha violation ketma-ket
        # kelganda DB ga ortiqcha COUNT(*) so'rovini oldini olish.
        self._today_cache_ts: float = 0.0
        self._cached_today: int = 0
        self._cached_no_helmet: int = 0

    def set_running(self, running: bool) -> None:
        self._running = running

    def start_writer(self, cam_id: int) -> None:
        if self._save_thread and self._save_thread.is_alive():
            return
        self._save_thread = threading.Thread(
            target=self._writer_loop,
            daemon=True,
            name=f"ViolationWriter-{cam_id}",
        )
        self._save_thread.start()

    def stop_writer(self) -> None:
        if not self._save_thread or not self._save_thread.is_alive():
            return
        try:
            self._save_queue.put(None, timeout=0.3)
        except Full:
            return
        self._save_thread.join(timeout=1.0)

    def mark_no_helmet_candidates(self, persons: list[dict]) -> list[dict]:
        threshold = int(self.cfg.get("confirmation_threshold", 10))
        active_ids = {p["track_id"] for p in persons}
        self.no_helmet_frames = {
            key: value for key, value in self.no_helmet_frames.items() if key in active_ids
        }
        for person in persons:
            track_id = person["track_id"]
            if not person.get("track_confirmed", True):
                self.no_helmet_frames[track_id] = 0
                person["is_new_violation"] = False
                continue
            if person.get("has_helmet") is False:
                self.no_helmet_frames[track_id] = self.no_helmet_frames.get(track_id, 0) + 1
                key = (track_id, "no_helmet")
                person["is_new_violation"] = (
                    self.no_helmet_frames[track_id] == threshold
                    and key not in self.saved_violations
                    and not self.is_spatial_duplicate(person, "no_helmet")
                )
            else:
                self.no_helmet_frames[track_id] = 0
                person["is_new_violation"] = False
        return persons

    def handle_violation(self, frame: np.ndarray, person: dict, violation_type: str = "no_helmet") -> None:
        track_id = person.get("track_id", -1)
        key = (track_id, violation_type)
        if key in self.saved_violations or self.is_spatial_duplicate(person, violation_type):
            return
        self.saved_violations.add(key)
        self.remember_spatial_violation(person, violation_type)
        try:
            self._save_queue.put_nowait({
                "track_id": track_id,
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
            self.saved_violations.discard(key)
            self.emit_error("Buzilish saqlash navbati to'lib qoldi")

    def remember_spatial_violation(self, person: dict, violation_type: str) -> None:
        cx, cy, _ = self.box_center_size(person)
        self.spatial_violations.append({
            "ts": time.time(),
            "type": violation_type,
            "cx": cx,
            "cy": cy,
        })

    def is_spatial_duplicate(self, person: dict, violation_type: str) -> bool:
        now = time.time()
        self.prune_spatial_violations(now)
        cx, cy, size = self.box_center_size(person)
        max_dist = max(48.0, size * 0.65)
        for item in self.spatial_violations:
            if item["type"] != violation_type:
                continue
            dist = ((cx - item["cx"]) ** 2 + (cy - item["cy"]) ** 2) ** 0.5
            if dist <= max_dist:
                return True
        return False

    def prune_spatial_violations(self, now: float) -> None:
        cooldown = float(self.cfg.get("violation_cooldown", 10))
        while self.spatial_violations and now - float(self.spatial_violations[0]["ts"]) > cooldown:
            self.spatial_violations.popleft()

    def clear(self) -> None:
        self.spatial_violations.clear()
        self.no_helmet_frames.clear()
        self.access_frames.clear()

    def _writer_loop(self) -> None:
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
                    frame=item["frame"],
                    person=item["person"],
                    camera_name=item["camera_name"],
                    company_id=item["company_id"],
                    violations_dir=item["violations_dir"],
                    save_files=item["save_files"],
                    violation_type=item.get("violation_type", "no_helmet"),
                    camera_id=item.get("camera_id"),
                    department_id=item.get("department_id"),
                    employee_id=item["person"].get("employee_id"),
                    employee_name=item["person"].get("employee_name", ""),
                    identity_confidence=float(item["person"].get("identity_confidence", 0.0) or 0.0),
                    notifier=self.notifier,
                    backend=self.backend,
                )
                now = time.time()
                # 2 sekundlik cache — yaqin vaqtda kelgan bir nechta violation
                # bir necha COUNT(*) emas, bitta query bilan ko'rsatiladi.
                if now - self._today_cache_ts > 2.0:
                    self._cached_today = self.db.get_today_count()
                    self._cached_no_helmet = self.db.get_today_count("no_helmet")
                    self._today_cache_ts = now
                else:
                    # Yangi violation kirgani uchun cache'ni inkrementlash
                    self._cached_today += 1
                    if item.get("violation_type", "no_helmet") == "no_helmet":
                        self._cached_no_helmet += 1
                self.today_count = self._cached_today
                payload = event.to_payload()
                payload["today_count"] = self._cached_today
                payload["no_helmet_count"] = self._cached_no_helmet
                if self._running:
                    self.emit_payload(payload)
            except Exception as exc:
                track_id = int(item.get("track_id", -1))
                if track_id >= 0:
                    self.saved_violations.discard((track_id, item.get("violation_type", "no_helmet")))
                self.emit_error(f"Buzilishni saqlashda xatolik: {exc}")
            finally:
                self._save_queue.task_done()

    @staticmethod
    def box_center_size(person: dict) -> tuple[float, float, float]:
        box = person.get("box", person.get("bbox_xyxy", []))
        if len(box) != 4:
            return 0.0, 0.0, 1.0
        cx = (float(box[0]) + float(box[2])) * 0.5
        cy = (float(box[1]) + float(box[3])) * 0.5
        width = max(1.0, float(box[2]) - float(box[0]))
        height = max(1.0, float(box[3]) - float(box[1]))
        return cx, cy, max(width, height)
