"""Standalone Telegram notifier — SmartHelmet talab qilmaydi."""
from __future__ import annotations

import io
import threading

import cv2


class TelegramNotifier:
    def __init__(self, token: str, chat_ids: list[str]):
        self.token = token
        self.chat_ids = [str(c) for c in chat_ids if c]

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

        caption = f"\u26a0\ufe0f Shlem yo'q! ID:{track_id}"
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"

        for chat_id in self.chat_ids:
            try:
                frame = crop_frame if (crop_frame is not None and crop_frame.size > 0) else full_frame
                _, buf = cv2.imencode(".jpg", frame)
                requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": ("v.jpg", buf.tobytes(), "image/jpeg")},
                    timeout=15,
                )
            except Exception as e:
                print(f"[Telegram] {e}")
