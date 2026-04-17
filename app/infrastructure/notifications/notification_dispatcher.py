from __future__ import annotations

import threading

import numpy as np

from app.domain.entities import ViolationEvent


class NotificationDispatcher:
    """Sends violation payloads to external integrations in background threads."""

    @staticmethod
    def dispatch(
        event: ViolationEvent,
        full_frame: np.ndarray,
        notifier=None,
        backend=None,
    ) -> None:
        if notifier:
            crop_frame = event.crop_frame
            full_copy = full_frame.copy()

            def _send_telegram():
                try:
                    notifier.send_violation_photos(
                        crop_frame, full_copy, event.track_id, event.timestamp
                    )
                except Exception as exc:
                    print(f"[NotificationDispatcher] Telegram xato: {exc}")

            threading.Thread(target=_send_telegram, daemon=True).start()

        if backend:
            crop_frame = event.crop_frame
            full_copy = full_frame.copy()

            def _send_backend():
                try:
                    if crop_frame is not None and crop_frame.size > 0:
                        backend.send_violation(
                            event.camera_name, event.company_id, crop_frame, full_copy
                        )
                    else:
                        backend.send_violation(
                            event.camera_name, event.company_id, full_copy, full_copy
                        )
                except Exception as exc:
                    print(f"[NotificationDispatcher] Backend xato: {exc}")

            threading.Thread(target=_send_backend, daemon=True).start()
