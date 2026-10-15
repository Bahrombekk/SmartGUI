"""NotificationWorker — notification_jobs navbatini ishonchli yuboruvchi.

`notification_jobs` jadvali yagona haqiqat manbai: bu worker pending joblarni
o'qiydi, kanaliga qarab (telegram/backend) yuboradi va natijaga ko'ra
'sent' / retry / 'failed' qiladi. Eksponensial backoff va max-retry bor.
Ishga tushganda navbatdagi (offline to'plangan) joblarni darhol drain qiladi.

Rasm joblar payload'idagi disk yo'lidan (crop_path/full_path) o'qiladi.
Backend uchun u base64 sifatida JSON ichida ketadi; fayl topilmasa yozuv
rasmsiz yuboriladi.

Startda va keyin har `backfill_interval` sekundda `_backfill_unsent()`
bazadagi yuborilmagan buzilishlarni (sync_status 'queued'/'synced' emas)
navbatga qo'yadi. Backend job'i abadiy xato bo'lsa buzilish 'failed' qilinadi
— shuning uchun uzoq uzilishdan keyin ham keyingi backfill uni qayta yuboradi,
yozuv yo'qolmaydi.

BackendClient bitta nusxada saqlanadi (token keshlanadi) — har job uchun
qayta login qilinmaydi.

Job yuborishdan oldin atomar egallanadi ('pending' -> 'sending'), shuning
uchun ikki worker bitta jobni ikki marta yubormaydi; startda qolib ketgan
'sending' joblar 'pending' ga qaytariladi. Abadiy 4xx xatolar (401/408/429
dan tashqari) 'rejected' bo'ladi — ular hech qachon qayta navbatga qo'yilmaydi.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QThread

from app.application.services.notification_queue_service import NotificationQueueService

_log = logging.getLogger(__name__)

# Ilova yopilayotganda HTTP so'rovlar shu timeout bilan ketadi (sekund)
_SHUTDOWN_HTTP_TIMEOUT = 3.0
_NORMAL_HTTP_TIMEOUT = 15.0

# Shu 4xx kodlar vaqtinchalik (auth yangilanadi / timeout / rate-limit)
_TRANSIENT_4XX = (401, 408, 429)


class _ChannelDisabled(Exception):
    """Kanal cfg da o'chirilgan/sozlanmagan — retry qilmaymiz."""


def is_permanent_error(exc: BaseException) -> bool:
    """Qayta urinish foyda bermaydigan xato (server so'rovni rad etgan)."""
    if getattr(exc, "permanent", False):
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    try:
        status = int(status)
    except (TypeError, ValueError):
        return False
    return 400 <= status < 500 and status not in _TRANSIENT_4XX


class NotificationWorker(QThread):
    """notification_jobs navbatini fon rejimida yuboradi (retry + backoff)."""

    def __init__(self, db, cfg, *, poll_interval: float = 5.0,
                 max_retries: int = 12, batch_limit: int = 20,
                 backfill_limit: int = 5000, backfill_interval: float = 600.0,
                 parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg
        self.queue = NotificationQueueService(db)
        self.poll_interval = float(poll_interval)
        self.max_retries = int(max_retries)
        self.batch_limit = int(batch_limit)
        self.backfill_limit = int(backfill_limit)
        self.backfill_interval = float(backfill_interval)
        self._running = False
        self._stop_event = threading.Event()
        self._http_timeout = _NORMAL_HTTP_TIMEOUT
        self._backend = None
        self._backend_key: tuple = ()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def run(self):
        self._running = True
        try:
            # Oldingi sessiya yuborish paytida yopilgan bo'lsa — joblar qaytadi
            n = self.db.reset_stale_sending_jobs()
            if n:
                _log.info("%s ta tugallanmagan notification job navbatga qaytarildi", n)
        except Exception as exc:
            _log.error("Stale 'sending' joblarni tiklab bo'lmadi: %s", exc)
        try:
            self._backfill_unsent()
            self._drain_all()
        except Exception as exc:
            _log.error("NotificationWorker backfill xatosi: %s", self._safe_error(exc))
        last_backfill = time.monotonic()
        while self._running:
            try:
                if time.monotonic() - last_backfill >= self.backfill_interval:
                    last_backfill = time.monotonic()
                    self._backfill_unsent()
                self._drain_once()
            except Exception as exc:  # navbat ishlashi hech qachon to'xtamasin
                _log.error("NotificationWorker drain xatosi: %s", self._safe_error(exc))
            self._sleep(self.poll_interval)

    def request_stop(self):
        """Bloklamaydigan to'xtatish: sikl to'xtaydi, joriy HTTP so'rov qisqa timeout oladi."""
        self._running = False
        self._stop_event.set()
        self._http_timeout = _SHUTDOWN_HTTP_TIMEOUT
        if self._backend is not None:
            self._backend.timeout = _SHUTDOWN_HTTP_TIMEOUT

    def stop(self, timeout_ms: int = 5000) -> bool:
        """To'xtatadi va timeout_ms gacha kutadi. Thread tugagan bo'lsa True."""
        self.request_stop()
        return self.wait(int(timeout_ms))

    def _sleep(self, seconds: float):
        if self._running:
            self._stop_event.wait(seconds)

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
            self._on_job_given_up(job, "failed")
        for job in to_send:
            if not self._running:
                break
            self._process_job(job)
        return len(to_send) + len(to_fail)

    def _process_job(self, job: dict):
        job_id = job["id"]
        # Atomar egallash: boshqa worker/nusxa olgan bo'lsa — tegmaymiz
        if not self.db.claim_notification_job(job_id):
            return
        channel = job.get("channel", "")
        payload = self.queue.decode_payload(job.get("payload", "{}"))
        try:
            if channel == "telegram":
                self._send_telegram(job_id, payload)
            elif channel == "backend":
                self._send_backend(payload)
            else:
                raise _ChannelDisabled(f"noma'lum kanal: {channel}")
        except _ChannelDisabled as exc:
            self.queue.mark_permanent_failed(job_id, str(exc))
            # Kanal qayta yoqilganda backfill uni yana oladi
            self._on_job_given_up(job, "local")
            _log.warning("Notification job #%s abadiy xato: %s", job_id, exc)
        except Exception as exc:
            err = self._safe_error(exc)
            if is_permanent_error(exc):
                # Server rad etdi (4xx) — retry ham, backfill ham foyda bermaydi
                self.db.update_notification_job(job_id, status="rejected", last_error=err[:500])
                self._on_job_given_up(job, "rejected")
                _log.warning("Notification job #%s rad etildi (retry yo'q): %s", job_id, err)
            else:
                self.queue.mark_failed(job_id, err)
                _log.warning("Notification job #%s yuborilmadi (retry): %s", job_id, err)
        else:
            self.queue.mark_sent(job_id)
            if channel == "backend":
                self._set_violation_status(payload, "synced")

    # ── Yuborish ─────────────────────────────────────────────────────────────

    def _send_telegram(self, job_id: int, payload: dict):
        if not (self.cfg.telegram_enabled and self.cfg.telegram_token and self.cfg.telegram_chat_ids):
            raise _ChannelDisabled("telegram cfg da o'chirilgan")
        from app.infrastructure.notifications.telegram_notifier import TelegramNotifier

        notifier = TelegramNotifier(self.cfg.telegram_token, self.cfg.telegram_chat_ids,
                                    timeout=self._http_timeout)
        delivered = [str(c) for c in payload.get("delivered_chat_ids") or []]

        def on_delivered(chat_id: str):
            # Darhol saqlaymiz — retry (yoki yiqilishdan keyingi start) shu
            # chat'ga qayta yubormasin.
            delivered.append(chat_id)
            payload["delivered_chat_ids"] = list(delivered)
            try:
                self.db.update_notification_job(job_id, payload=payload)
            except Exception as exc:
                _log.warning("Job #%s delivered_chat_ids saqlanmadi: %s", job_id, exc)

        caption = f"⚠️ Shlem yo'q! ID:{payload.get('track_id', '?')}"
        image_bytes = self._load_image(payload)
        if image_bytes is not None:
            notifier.send_photo_bytes(image_bytes, caption, skip_chat_ids=delivered,
                                      on_delivered=on_delivered)
        else:
            # Rasm saqlanmagan (save_violations=False) — matnli xabar
            camera = payload.get("camera_name", "")
            text = caption + (f"\nKamera: {camera}" if camera else "")
            notifier.send_message(text, skip_chat_ids=delivered, on_delivered=on_delivered)

    def _send_backend(self, payload: dict):
        if not (self.cfg.backend_enabled and self.cfg.get("backend_url", "")):
            raise _ChannelDisabled("backend cfg da o'chirilgan")
        from app.infrastructure.notifications.backend_client import make_idempotency_key

        key = payload.get("idempotency_key") or make_idempotency_key(
            payload.get("camera_name", ""), payload.get("track_id"),
            payload.get("timestamp"), payload.get("violation_type", ""),
        )
        self._backend_client().send_event(
            payload.get("camera_name", ""),
            payload.get("company_id", ""),
            timestamp=payload.get("timestamp"),
            crop_bytes=self._read_file(payload.get("crop_path", "")),
            full_bytes=self._read_file(payload.get("full_path", "")),
            idempotency_key=key,
        )

    def _backend_client(self):
        """Bitta BackendClient (JWT keshi bilan); sozlama o'zgarsa qayta yaratiladi."""
        key = (self.cfg.get("backend_url", ""), self.cfg.get("backend_login", ""),
               self.cfg.get("backend_password", ""))
        if self._backend is None or key != self._backend_key:
            from app.infrastructure.notifications.backend_client import BackendClient

            self._backend = BackendClient(api_url=key[0], login=key[1], password=key[2],
                                          timeout=self._http_timeout)
            self._backend_key = key
        return self._backend

    def _safe_error(self, exc) -> str:
        """Xato matnidan maxfiy qiymatlarni (bot token, parol, JWT) olib tashlaydi."""
        from app.infrastructure.notifications.telegram_notifier import redact_token

        text = redact_token(exc, getattr(self.cfg, "telegram_token", "") or None)
        if self._backend is not None:
            text = self._backend.redact(text)
        try:
            password = self.cfg.get("backend_password", "")
        except Exception:
            password = ""
        if password and len(str(password)) >= 4:
            text = text.replace(str(password), "***")
        return text

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
                "violation_id": row.get("id"),
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
    def _read_file(path: str) -> bytes | None:
        """Rasmni o'qiydi; fayl yo'q bo'lsa None (yozuv rasmsiz ketaveradi)."""
        if path and Path(path).is_file():
            return Path(path).read_bytes()
        return None

    @staticmethod
    def _load_image(payload: dict) -> bytes | None:
        """Buzilish rasmi; topilmasa None (telegram matnli xabar yuboradi)."""
        for key in ("crop_path", "full_path"):
            p = payload.get(key, "")
            if p and Path(p).is_file():
                return Path(p).read_bytes()
        return None

    def _on_job_given_up(self, job: dict, status: str):
        """Backend job'idan voz kechildi — buzilish keyingi backfill'ga qoladi."""
        if job.get("channel") != "backend":
            return
        self._set_violation_status(self.queue.decode_payload(job.get("payload", "{}")), status)

    def _set_violation_status(self, payload: dict, status: str):
        try:
            self.db.update_violation_sync_status(
                int(payload.get("track_id", -1)),
                int(payload.get("timestamp", 0)),
                payload.get("camera_name", ""),
                status,
            )
        except Exception:
            pass  # sync_status faqat holat belgisi — kritik emas
