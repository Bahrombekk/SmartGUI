"""Standalone Telegram notifier — SmartHelmet talab qilmaydi.

Bot token so'rov URL'ida (`/bot<TOKEN>/`) bo'ladi va requests xatolari matnida
ham chiqadi — shuning uchun barcha xato matnlari `redact_token()` dan o'tadi
(log va notification_jobs.last_error'ga token tushmasin).
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Callable, Iterable

import cv2

_log = logging.getLogger(__name__)

_BOT_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

# Shu HTTP kodlar vaqtinchalik — qolgan 4xx abadiy (chat topilmadi, bot bloklangan...)
_TRANSIENT_4XX = (401, 408, 429)


def redact_token(text, token: str | None = None) -> str:
    """Matndan Telegram bot tokenini olib tashlaydi (*** bilan almashtiradi)."""
    s = str(text)
    if token:
        s = s.replace(str(token), "***")
    return _BOT_TOKEN_RE.sub("bot***", s)


class TelegramSendError(RuntimeError):
    """Ba'zi chat'larga yuborilmadi.

    delivered — shu urinishda muvaffaqiyatli yuborilgan chat_id'lar;
    permanent — barcha xatolar abadiy (4xx, 401/408/429 dan tashqari).
    """

    def __init__(self, message: str, *, delivered: list[str], permanent: bool):
        super().__init__(message)
        self.delivered = list(delivered)
        self.permanent = bool(permanent)


class TelegramNotifier:
    def __init__(self, token: str, chat_ids: list[str], timeout: float = 15.0):
        self.token = token
        self.chat_ids = [str(c) for c in chat_ids if c]
        self.timeout = float(timeout)

    def _redact(self, text) -> str:
        return redact_token(text, self.token)

    def send_violation_photos(self, crop_frame, full_frame, track_id, timestamp):
        if not self.token or not self.chat_ids:
            return
        threading.Thread(
            target=self._send,
            args=(crop_frame, full_frame, track_id, timestamp),
            daemon=True,
        ).start()

    def _send(self, crop_frame, full_frame, track_id, timestamp):
        try:
            import requests
        except ImportError:
            return

        caption = f"⚠️ Shlem yo'q! ID:{track_id}"
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"

        for chat_id in self.chat_ids:
            try:
                frame = crop_frame if (crop_frame is not None and crop_frame.size > 0) else full_frame
                _, buf = cv2.imencode(".jpg", frame)
                requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": ("v.jpg", buf.tobytes(), "image/jpeg")},
                    timeout=self.timeout,
                )
            except Exception as e:
                _log.error("Telegram yuborish xatosi (chat_id=%s): %s", chat_id, self._redact(e))

    # ── Sinxron yuborish (navbat worker'i uchun) ────────────────────────────

    def send_photo_bytes(self, image_bytes: bytes, caption: str, *,
                         skip_chat_ids: Iterable[str] = (),
                         on_delivered: Callable[[str], None] | None = None) -> list[str]:
        """Rasmni barcha chat_id larga yuboradi (skip_chat_ids dagilardan tashqari).

        Xatoda TelegramSendError ko'taradi — unda qaysi chat'lar yetkazilgani
        bor, shunda retry faqat qolganlarga yuboradi (dublikat bo'lmaydi).
        Yetkazilgan chat_id'lar ro'yxatini qaytaradi.
        """
        def post(requests, url_base, chat_id):
            return requests.post(
                f"{url_base}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": ("v.jpg", image_bytes, "image/jpeg")},
                timeout=self.timeout,
            )
        return self._send_each(post, skip_chat_ids, on_delivered)

    def send_message(self, text: str, *, skip_chat_ids: Iterable[str] = (),
                     on_delivered: Callable[[str], None] | None = None) -> list[str]:
        """Rasmsiz matnli xabar (rasm saqlanmagan buzilishlar uchun)."""
        def post(requests, url_base, chat_id):
            return requests.post(
                f"{url_base}/sendMessage",
                data={"chat_id": chat_id, "text": text},
                timeout=self.timeout,
            )
        return self._send_each(post, skip_chat_ids, on_delivered)

    def _send_each(self, post, skip_chat_ids, on_delivered) -> list[str]:
        if not self.token or not self.chat_ids:
            raise RuntimeError("Telegram token yoki chat_id yo'q")
        import requests

        url_base = f"https://api.telegram.org/bot{self.token}"
        skip = {str(c) for c in skip_chat_ids}
        delivered: list[str] = []
        errors: list[str] = []
        all_permanent = True
        for chat_id in self.chat_ids:
            if chat_id in skip:
                continue
            try:
                resp = post(requests, url_base, chat_id)
                status = int(getattr(resp, "status_code", 200) or 200)
            except Exception as e:
                errors.append(f"{chat_id}: {self._redact(e)}")
                all_permanent = False  # tarmoq xatosi — vaqtinchalik
                continue
            if status >= 400:
                errors.append(f"{chat_id}: HTTP {status} {self._describe(resp)}")
                if not (400 <= status < 500 and status not in _TRANSIENT_4XX):
                    all_permanent = False
                continue
            delivered.append(chat_id)
            if on_delivered is not None:
                on_delivered(chat_id)
        if errors:
            raise TelegramSendError(self._redact("; ".join(errors)),
                                    delivered=delivered, permanent=all_permanent)
        return delivered

    def _describe(self, resp) -> str:
        try:
            desc = resp.json().get("description", "")
        except Exception:
            desc = getattr(resp, "reason", "") or ""
        return self._redact(desc)[:200]
