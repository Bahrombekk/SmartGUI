"""DAS UTY AI backend API mijozi (`POST /api/camera/create`).

Backend JWT talab qiladi va faqat JSON qabul qiladi:

    POST /api/auth/login        {login, password}          -> tempToken + accountRoles
    POST /api/auth/select-role  {accountRoleId, tempToken} -> access + refresh
    POST /api/camera/create     {cameraName, time, companyXId}

DTO qat'iy whitelist bilan himoyalangan — faqat shu uch maydon o'tadi.
Rasm yuborish qo'llab-quvvatlanmaydi (endpoint multipart body ni o'qimaydi),
shuning uchun frame/bytes argumentlari qabul qilinadi-yu, yuborilmaydi.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import threading
import time
from datetime import datetime

_log = logging.getLogger(__name__)

_CREATE_PATH = "/api/camera/create"
_LOGIN_PATH = "/api/auth/login"
_SELECT_ROLE_PATH = "/api/auth/select-role"
_REFRESH_PATH = "/api/auth/refresh"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

# Tokenni muddati tugashidan shuncha sekund oldin yangilaymiz.
_TOKEN_SKEW = 60.0


class BackendClient:
    def __init__(self, api_url: str, login: str, password: str):
        self.base_url = self._normalize_base(api_url)
        self.login = login
        self.password = password

        self._lock = threading.Lock()
        self._access = ""
        self._access_exp = 0.0
        self._refresh = ""
        self._warned_company_ids: set[str] = set()

    # ── URL ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_base(api_url: str) -> str:
        """Sozlamadagi URL ni host ildiziga keltiradi.

        Foydalanuvchi ham `https://host/`, ham to'liq `.../api/camera/create`
        yozishi mumkin — ikkalasi ham ishlasin.
        """
        url = (api_url or "").strip().rstrip("/")
        if not url:
            return ""
        if url.endswith(_CREATE_PATH):
            url = url[: -len(_CREATE_PATH)]
        elif url.endswith("/api"):
            url = url[: -len("/api")]
        return url.rstrip("/")

    @property
    def api_url(self) -> str:
        """Eski kod shu atributga qarab 'sozlanganmi' deb tekshiradi."""
        return f"{self.base_url}{_CREATE_PATH}" if self.base_url else ""

    # ── Auth ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _jwt_expiry(token: str) -> float:
        """JWT payload'idan `exp` ni oladi; o'qib bo'lmasa 0 qaytaradi."""
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
        except (IndexError, ValueError, KeyError, TypeError, binascii.Error):
            return 0.0

    def _store_tokens(self, data: dict) -> None:
        self._access = data.get("access", "")
        self._refresh = data.get("refresh", self._refresh)
        exp = self._jwt_expiry(self._access)
        # exp o'qilmasa 25 daqiqa deb hisoblaymiz (server 30 daqiqa beradi).
        self._access_exp = exp if exp else time.time() + 25 * 60

    def _full_login(self, requests) -> None:
        r = requests.post(
            f"{self.base_url}{_LOGIN_PATH}",
            json={"login": self.login, "password": self.password},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        roles = data.get("accountRoles") or []
        if not roles:
            raise RuntimeError("Backend: hisobda hech qanday rol yo'q")

        r2 = requests.post(
            f"{self.base_url}{_SELECT_ROLE_PATH}",
            json={"accountRoleId": roles[0]["id"], "tempToken": data["tempToken"]},
            timeout=15,
        )
        r2.raise_for_status()
        self._store_tokens(r2.json())

    def _try_refresh(self, requests) -> bool:
        if not self._refresh:
            return False
        try:
            r = requests.post(
                f"{self.base_url}{_REFRESH_PATH}",
                json={"refresh": self._refresh},
                timeout=15,
            )
            r.raise_for_status()
            self._store_tokens(r.json())
            return bool(self._access)
        except Exception as e:
            _log.info("Backend refresh ishlamadi, qayta login qilinadi: %s", e)
            self._refresh = ""
            return False

    def _access_token(self, requests, *, force: bool = False) -> str:
        with self._lock:
            if not force and self._access and time.time() < self._access_exp - _TOKEN_SKEW:
                return self._access
            if force:
                self._access = ""
            if not self._try_refresh(requests):
                self._full_login(requests)
            return self._access

    # ── Payload ──────────────────────────────────────────────────────────────

    def _build_payload(self, camera_name: str, company_id: str, timestamp=None) -> dict:
        when = datetime.fromtimestamp(float(timestamp)) if timestamp else datetime.now()
        # Mahalliy vaqt (tz'siz) — backenddagi mavjud yozuvlar ham shu formatda.
        payload = {"cameraName": camera_name or "", "time": when.isoformat()}

        cid = (company_id or "").strip()
        if _UUID_RE.match(cid):
            payload["companyXId"] = cid
        elif cid and cid not in self._warned_company_ids:
            self._warned_company_ids.add(cid)
            _log.warning(
                "Kamera '%s' uchun Company ID UUID emas (%r) — companyXId yuborilmaydi, "
                "yozuv kompaniyaga bog'lanmaydi.",
                camera_name, cid,
            )
        return payload

    def _post_event(self, requests, payload: dict):
        token = self._access_token(requests)
        url = f"{self.base_url}{_CREATE_PATH}"
        resp = requests.post(
            url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15
        )
        if resp.status_code == 401:
            # Token muddati tugagan bo'lishi mumkin — yangilab bir marta qayta urinamiz.
            token = self._access_token(requests, force=True)
            resp = requests.post(
                url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15
            )
        resp.raise_for_status()
        return resp

    # ── Ommaviy API ──────────────────────────────────────────────────────────

    def send_violation(self, camera_name: str, company_id: str, crop_frame, full_frame,
                       timestamp=None):
        """Fon rejimida yuboradi (xatolar faqat logga tushadi).

        crop_frame/full_frame ishlatilmaydi: backend rasm qabul qilmaydi.
        """
        if not self.base_url:
            return
        threading.Thread(
            target=self._send_quiet,
            args=(camera_name, company_id, timestamp),
            daemon=True,
        ).start()

    def _send_quiet(self, camera_name, company_id, timestamp=None):
        try:
            self.send_event(camera_name, company_id, timestamp)
        except Exception as e:
            _log.error("Yuborish xatosi: %s", e)

    def send_event(self, camera_name: str, company_id: str, timestamp=None) -> None:
        """Sinxron yuborish. Xatoda istisno ko'taradi — queue worker retry qiladi."""
        if not self.base_url:
            raise RuntimeError("Backend URL yo'q")
        import requests

        payload = self._build_payload(camera_name, company_id, timestamp)
        resp = self._post_event(requests, payload)
        _log.info("Backend'ga yuborildi: %s (%s)", payload["cameraName"], resp.status_code)

    def send_image_bytes(self, camera_name: str, company_id: str, image_bytes: bytes,
                         timestamp=None) -> None:
        """Navbat worker'i chaqiradi. Rasm yuborilmaydi — endpoint qo'llamaydi."""
        self.send_event(camera_name, company_id, timestamp)
