"""NotificationWorker — notification_jobs navbatini ishonchli yuboruvchi.

`notification_jobs` jadvali yagona haqiqat manbai: bu worker pending joblarni
o'qiydi, kanaliga qarab (telegram/backend) yuboradi va natijaga ko'ra
'sent' / retry / 'failed' qiladi. Eksponensial backoff va max-retry bor.
Ishga tushganda navbatdagi (offline to'plangan) joblarni darhol drain qiladi.

Rasm joblar payload'idagi disk yo'lidan (crop_path/full_path) o'qiladi — shu
sabab faqat save_violations=True bo'lgan buzilishlar navbatga qo'yiladi.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PyQt6.QtCore import QThread

from app.application.services.notification_queue_service import NotificationQueueService

_log = logging.getLogger(__name__)


class _ChannelDisabled(Exception):
    """Kanal cfg da o'chirilgan/sozlanmagan — retry qilmaymiz."""


class NotificationWorker(QThread):
    """notification_jobs navbatini fon rejimida yuboradi (retry + backoff)."""

    def __init__(self, db, cfg, *, poll_interval: float = 5.0,
                 max_retries: int = 5, batch_limit: int = 20, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg
        self.queue = NotificationQueueService(db)
        self.poll_interval = float(poll_interval)
        self.max_retries = int(max_retries)
        self.batch_limit = int(batch_limit)
        self._running = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def run(self):
        self._running = True
        while self._running:
            try:
                self._drain_once()
            except Exception as exc:  # navbat ishlashi hech qachon to'xtamasin
                _log.error("NotificationWorker drain xatosi: %s", exc)
            self._sleep(self.poll_interval)

    def stop(self):
        self._running = False
        self.wait(2000)

    def _sleep(self, seconds: float):
        end = time.perf_counter() + seconds
        while self._running and time.perf_counter() < end:
            time.sleep(0.2)

    # ── Drain ──────────────────────────────────────────────────────────────

    def _drain_once(self):
        now = time.time()
        to_send, to_fail = self.queue.due_jobs(
            now, limit=self.batch_limit, max_retries=self.max_retries
        )
        for job in to_fail:
            self.queue.mark_permanent_failed(
                job["id"], f"max retries ({self.max_retries}) oshib ketdi"
            )
        for job in to_send:
            if not self._running:
                break
            self._process_job(job)

    def _process_job(self, job: dict):
        job_id = job["id"]
        channel = job.get("channel", "")
        payload = self.queue.decode_payload(job.get("payload", "{}"))
        try:
            image_bytes = self._load_image(payload)
            if channel == "telegram":
                self._send_telegram(payload, image_bytes)
            elif channel == "backend":
                self._send_backend(payload, image_bytes)
            else:
                raise _ChannelDisabled(f"noma'lum kanal: {channel}")
        except _ChannelDisabled as exc:
            self.queue.mark_permanent_failed(job_id, str(exc))
            _log.warning("Notification job #%s abadiy xato: %s", job_id, exc)
        except Exception as exc:
            self.queue.mark_failed(job_id, str(exc))
            _log.warning("Notification job #%s yuborilmadi (retry): %s", job_id, exc)
        else:
            self.queue.mark_sent(job_id)
            self._mark_violation_synced(payload)

    # ── Yuborish ─────────────────────────────────────────────────────────────

    def _send_telegram(self, payload: dict, image_bytes: bytes):
        if not (self.cfg.telegram_enabled and self.cfg.telegram_token and self.cfg.telegram_chat_ids):
            raise _ChannelDisabled("telegram cfg da o'chirilgan")
        from app.infrastructure.notifications.telegram_notifier import TelegramNotifier

        notifier = TelegramNotifier(self.cfg.telegram_token, self.cfg.telegram_chat_ids)
        caption = f"⚠️ Shlem yo'q! ID:{payload.get('track_id', '?')}"
        notifier.send_photo_bytes(image_bytes, caption)

    def _send_backend(self, payload: dict, image_bytes: bytes):
        if not (self.cfg.backend_enabled and self.cfg.get("backend_url", "")):
            raise _ChannelDisabled("backend cfg da o'chirilgan")
        from app.infrastructure.notifications.backend_client import BackendClient

        backend = BackendClient(
            api_url=self.cfg.get("backend_url", ""),
            login=self.cfg.get("backend_login", ""),
            password=self.cfg.get("backend_password", ""),
        )
        backend.send_image_bytes(
            payload.get("camera_name", ""),
            payload.get("company_id", ""),
            image_bytes,
        )

    # ── Yordamchi ────────────────────────────────────────────────────────────

    @staticmethod
    def _load_image(payload: dict) -> bytes:
        for key in ("crop_path", "full_path"):
            p = payload.get(key, "")
            if p and Path(p).is_file():
                return Path(p).read_bytes()
        raise FileNotFoundError("buzilish rasmi topilmadi (crop_path/full_path)")

    def _mark_violation_synced(self, payload: dict):
        try:
            self.db.update_violation_sync_status(
                int(payload.get("track_id", -1)),
                int(payload.get("timestamp", 0)),
                payload.get("camera_name", ""),
                "synced",
            )
        except Exception:
            pass  # sync_status faqat ko'rsatuv uchun — kritik emas
