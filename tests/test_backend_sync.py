"""Backend yuborish zanjiri: BackendClient + NotificationWorker + SQLite navbat.

Haqiqiy server o'rniga lokal soxta HTTP server ishlatiladi.
"""
import base64
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.infrastructure.notifications.backend_client import BackendClient
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.workers.notification_worker import NotificationWorker

COMPANY_UUID = "6b1e6e0a-4c3a-4b7e-9c51-5afe20e0a001"


def _jwt(exp: float) -> str:
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"


class _FakeBackend:
    def __init__(self):
        self.logins = 0
        self.events: list[dict] = []
        self.down = False
        self.reject_token_once = False
        self._tokens: set[str] = set()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if fake.down:
                    return self._json(503, {"message": "down"})
                if self.path == "/api/auth/device-login":
                    if body != {"login": "kaska", "password": "secret"}:
                        return self._json(401, {"message": "bad creds"})
                    fake.logins += 1
                    tok = _jwt(time.time() + 1800) + str(fake.logins)
                    fake._tokens.add(tok)
                    return self._json(201, {"data": {"token": {"access": tok, "refresh": ""}}})
                if self.path == "/api/camera/create":
                    tok = self.headers.get("Authorization", "").removeprefix("Bearer ")
                    if tok not in fake._tokens or fake.reject_token_once:
                        fake.reject_token_once = False
                        fake._tokens.discard(tok)
                        return self._json(401, {"message": "expired"})
                    fake.events.append(body)
                    return self._json(201, {"ok": True})
                return self._json(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class _Cfg:
    def __init__(self, url):
        self.data = {"backend_url": url, "backend_login": "kaska", "backend_password": "secret"}
        self.backend_enabled = True
        self.telegram_enabled = False
        self.telegram_token = ""
        self.telegram_chat_ids = []

    def get(self, key, default=None):
        return self.data.get(key, default)

    def get_cameras(self):
        return [{"id": 1, "name": "Kamera 1", "company_id": COMPANY_UUID}]


class BackendSyncTests(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeBackend()
        self.tmp = tempfile.TemporaryDirectory()
        self.db = ViolationsDB(str(Path(self.tmp.name) / "t.db"))
        self.crop = Path(self.tmp.name) / "crop.jpg"
        self.crop.write_bytes(b"\xff\xd8crop\xff\xd9")
        self.cfg = _Cfg(self.fake.url)

    def tearDown(self):
        self.fake.close()
        try:
            self.db.close_current_thread()
        except Exception:
            pass
        self.tmp.cleanup()

    def _worker(self, **kw):
        w = NotificationWorker(self.db, self.cfg, **kw)
        w._running = True  # threadsiz — metodlarni to'g'ridan-to'g'ri chaqiramiz
        return w

    def _add_violation(self, track_id, ts, status="local"):
        self.db.add_violation(track_id=track_id, crop_path=str(self.crop), camera_name="Kamera 1",
                              timestamp=ts, camera_id=1, sync_status=status)

    def _statuses(self):
        conn = self.db._conn()
        return [r[0] for r in conn.execute("SELECT sync_status FROM violations ORDER BY track_id")]

    def test_payload_has_utc_time_images_and_company(self):
        client = BackendClient(self.fake.url, "kaska", "secret")
        client.send_event("Kamera 1", COMPANY_UUID, timestamp=1_700_000_000,
                          crop_bytes=b"abc", full_bytes=b"xyz")
        ev = self.fake.events[0]
        self.assertEqual(ev["cameraName"], "Kamera 1")
        self.assertEqual(ev["time"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(ev["companyXId"], COMPANY_UUID)
        self.assertEqual(base64.b64decode(ev["definedImageBase64"]), b"abc")
        self.assertEqual(base64.b64decode(ev["fullPictureBase64"]), b"xyz")

    def test_non_uuid_company_is_not_sent(self):
        BackendClient(self.fake.url, "kaska", "secret").send_event("K", "www")
        self.assertNotIn("companyXId", self.fake.events[0])

    def test_expired_token_relogins_once(self):
        client = BackendClient(self.fake.url, "kaska", "secret")
        client.send_event("K", "")
        self.fake.reject_token_once = True
        client.send_event("K", "")
        self.assertEqual(len(self.fake.events), 2)
        self.assertEqual(self.fake.logins, 2)

    def test_backfill_sends_all_with_single_login(self):
        for i in range(5):
            self._add_violation(i, 1_700_000_000 + i)
        w = self._worker()
        w._backfill_unsent()
        w._drain_all()
        self.assertEqual(len(self.fake.events), 5)
        self.assertEqual(self.fake.logins, 1)  # token keshlanadi
        self.assertEqual(self._statuses(), ["synced"] * 5)
        self.assertTrue(all("definedImageBase64" in e for e in self.fake.events))

    def test_long_outage_is_recovered_by_next_backfill(self):
        self._add_violation(1, 1_700_000_000)
        w = self._worker(max_retries=2)
        w.queue.backoff_seconds = lambda retry, **_: 0.0  # testda kutmaymiz
        self.fake.down = True
        w._backfill_unsent()
        for _ in range(4):
            w._drain_once()
        self.assertEqual(self._statuses(), ["failed"])  # yo'qolmadi, belgilandi
        self.fake.down = False
        w._backfill_unsent()
        w._drain_all()
        self.assertEqual(self._statuses(), ["synced"])
        self.assertEqual(len(self.fake.events), 1)

    def test_disabled_backend_keeps_violation_for_later(self):
        self._add_violation(1, 1_700_000_000)
        w = self._worker()
        w._backfill_unsent()
        self.cfg.backend_enabled = False
        w._drain_all()
        self.assertEqual(self._statuses(), ["local"])
        self.cfg.backend_enabled = True
        w._backfill_unsent()
        w._drain_all()
        self.assertEqual(self._statuses(), ["synced"])


if __name__ == "__main__":
    unittest.main()
