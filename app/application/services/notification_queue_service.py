from __future__ import annotations

import json
import time


class NotificationQueueService:
    """Persistent notification job facade backed by SQLite."""

    def __init__(self, db):
        self.db = db

    def enqueue_violation_jobs(self, event, *, telegram_enabled: bool, backend_enabled: bool) -> list[int]:
        payload = {
            "track_id": event.track_id,
            "timestamp": event.timestamp,
            "camera_name": event.camera_name,
            "company_id": event.company_id,
            "violation_type": event.violation_type,
            "employee_id": event.employee_id,
            "employee_name": event.employee_name,
            "crop_path": event.crop_path,
            "full_path": event.full_path,
        }
        ids = []
        if telegram_enabled:
            ids.append(self.db.add_notification_job("telegram", payload))
        if backend_enabled:
            ids.append(self.db.add_notification_job("backend", payload))
        return ids

    def mark_sent(self, job_id: int) -> None:
        self.db.update_notification_job(job_id, status="sent", last_error="", sent_at=int(time.time()))

    def mark_failed(self, job_id: int, error: str) -> None:
        """Vaqtinchalik xato — job 'pending' ga qaytadi, retry_count +1."""
        self.db.increment_notification_retry(job_id, str(error)[:500])

    def mark_permanent_failed(self, job_id: int, error: str) -> None:
        """Abadiy xato — boshqa retry qilinmaydi (max retry yoki kanal o'chirilgan)."""
        self.db.update_notification_job(job_id, status="failed", last_error=str(error)[:500])

    @staticmethod
    def backoff_seconds(retry_count: int, base: float = 10.0, cap: float = 600.0) -> float:
        """Eksponensial backoff: 10s, 20s, 40s, ... cap (10 daqiqa) gacha."""
        if retry_count <= 0:
            return 0.0
        return min(cap, base * (2 ** (retry_count - 1)))

    def due_jobs(self, now: float, *, limit: int = 20, max_retries: int = 5) -> tuple[list[dict], list[dict]]:
        """Navbatdagi joblarni ikkiga ajratadi:

        - to_send: hozir yuborishga tayyor (backoff o'tgan, retry < max)
        - to_fail: max retry dan oshgan → abadiy xato qilinishi kerak

        Backoff hali o'tmagan joblar ikkala ro'yxatga ham kirmaydi.
        """
        to_send, to_fail = [], []
        for job in self.db.get_pending_notification_jobs(limit=limit):
            retry = int(job.get("retry_count", 0))
            if retry >= max_retries:
                to_fail.append(job)
                continue
            updated = float(job.get("updated_at", 0) or 0)
            if retry > 0 and (now - updated) < self.backoff_seconds(retry):
                continue
            to_send.append(job)
        return to_send, to_fail

    @staticmethod
    def encode_payload(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def decode_payload(payload: str) -> dict:
        try:
            return json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {}
