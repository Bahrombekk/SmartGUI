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
        self.db.increment_notification_retry(job_id, str(error)[:500])

    @staticmethod
    def encode_payload(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def decode_payload(payload: str) -> dict:
        try:
            return json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {}
