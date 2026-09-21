"""NotificationWorker — notification_jobs navbatini ishonchli yuboruvchi.

`notification_jobs` jadvali yagona haqiqat manbai: bu worker pending joblarni
o'qiydi, kanaliga qarab (telegram/backend) yuboradi va natijaga ko'ra
'sent' / retry / 'failed' qiladi. Eksponensial backoff va max-retry bor.
Ishga tushganda navbatdagi (offline to'plangan) joblarni darhol drain qiladi.

Telegram uchun rasm joblar payload'idagi disk yo'lidan (crop_path/full_path)
o'qiladi. Backend rasm qabul qilmaydi, shuning uchun backend joblari rasmsiz
ham yuboriladi.

Startda `_backfill_unsent()` bazadagi hech qachon yuborilmagan buzilishlarni
(sync_status 'queued'/'synced' emas) navbatga qo'yadi va hammasi birdan
drain qilinadi.
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
                 max_retries: int = 5, batch_limit: int = 20,
                 backfill_limit: int = 5000, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg
        self.queue = NotificationQueueService(db)
        self.poll_interval = float(poll_interval)
        self.max_retries = int(max_retries)
        self.batch_limit = int(batch_limit)
        self.backfill_limit = int(backfill_limit)
        self._running = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def run(self):
        self._running = True
        try:
            self._backfill_unsent()
            self._drain_all()
        except Exception as exc:
            _log.error("NotificationWorker backfill xatosi: %s", exc)
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

    def _drain_all(self):
        """Navbat bo'shaguncha (yoki backoff'ga qolguncha) ketma-ket drain."""
        while self._running:
            if self._drain_once() == 0:
                break

    def _drain_once(self) -> int:
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
        return len(to_send) + len(to_fail)

    def _process_job(self, job: dict):
        job_id = job["id"]
        channel = job.get("channel", "")
        payload = self.queue.decode_payload(job.get("payload", "{}"))
        try:
            if channel == "telegram":
                self._send_telegram(payload, self._load_image(payload))
            elif channel == "backend":
                self._send_backend(payload)
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

    def _send_backend(self, payload: dict):
        if not (self.cfg.backend_enabled and self.cfg.get("backend_url", "")):
            raise _ChannelDisabled("backend cfg da o'chirilgan")
        from app.infrastructure.notifications.backend_client import BackendClient

        backend = BackendClient(
            api_url=self.cfg.get("backend_url", ""),
            login=self.cfg.get("backend_login", ""),
            password=self.cfg.get("backend_password", ""),
        )
        backend.send_event(
            payload.get("camera_name", ""),
            payload.get("company_id", ""),
            timestamp=payload.get("timestamp"),
        )

    # ── Backfill ─────────────────────────────────────────────────────────────

    def _backfill_unsent(self):
        """Backend yoqilgunga qadar to'plangan buzilishlarni navbatga qo'yadi.

        Faqat bir marta ishlaydi: qo'yilgan qatorning sync_status'i 'queued'
        bo'lib qoladi, shuning uchun keyingi startda qayta olinmaydi.
        """
        if not (self.cfg.backend_enabled and self.cfg.get("backend_url", "")):
            return
        rows = self.db.get_unsynced_violations(limit=self.backfill_limit)
        if not rows:
            return

        queued = 0
        for row in rows:
            if not self._running:
                break
            camera_name = row.get("camera_name", "")
            payload = {
                "track_id": row.get("track_id"),
                "timestamp": row.get("timestamp"),
                "camera_name": camera_name,
                "company_id": self._company_id_for(row.get("camera_id"), camera_name),
                "violation_type": row.get("violation_type", ""),
                "employee_id": row.get("employee_id"),
                "employee_name": row.get("employee_name", ""),
                "crop_path": row.get("crop_path", ""),
                "full_path": row.get("full_path", ""),
            }
            try:
                self.db.add_notification_job("backend", payload)
                self.db.update_violation_sync_status(
                    int(row.get("track_id", -1)),
                    int(row.get("timestamp", 0)),
                    camera_name,
                    "queued",
                )
                queued += 1
            except Exception as exc:
                _log.error("Backfill: buzilish #%s navbatga qo'yilmadi: %s",
                           row.get("id"), exc)

        _log.info("Backfill: %s ta eski buzilish backend navbatiga qo'yildi", queued)

    def _company_id_for(self, camera_id, camera_name: str) -> str:
        """Buzilish qatorida company_id yo'q — uni sozlamadagi kameradan olamiz."""
        try:
            cameras = self.cfg.get_cameras()
        except Exception:
            return ""
        if camera_id is not None:
            for cam in cameras:
                if cam.get("id") == camera_id:
                    return cam.get("company_id", "")
        for cam in cameras:
            if cam.get("name") == camera_name:
                return cam.get("company_id", "")
        return ""

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
