"""Standalone Backend API client — SmartHelmet talab qilmaydi."""
from __future__ import annotations

import threading

import cv2


class BackendClient:
    def __init__(self, api_url: str, login: str, password: str):
        self.api_url = api_url
        self.login = login
        self.password = password

    def send_violation(self, camera_name: str, company_id: str, crop_frame, full_frame):
        if not self.api_url:
            return
        threading.Thread(
            target=self._send,
            args=(camera_name, company_id, crop_frame, full_frame),
            daemon=True,
        ).start()

    def _send(self, camera_name, company_id, crop_frame, full_frame):
        try:
            import requests
        except ImportError:
            return

        try:
            frame = crop_frame if (crop_frame is not None and crop_frame.size > 0) else full_frame
            _, buf = cv2.imencode(".jpg", frame)
            requests.post(
                self.api_url,
                auth=(self.login, self.password),
                files={"image": ("violation.jpg", buf.tobytes(), "image/jpeg")},
                data={"company_id": company_id, "camera_name": camera_name},
                timeout=15,
            )
        except Exception as e:
            print(f"[BackendClient] {e}")
