"""Persistensiya / navbat ishonchliligi: retention, job claiming, Telegram
chat-lar bo'yicha yetkazish, abadiy xatolar, tranzaksion enqueue, karantin.

Tarmoq ishlatilmaydi — requests.post mock qilinadi.
"""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from app.application.services.violation_service import ViolationService
from app.infrastructure.notifications.telegram_notifier import (
    TelegramNotifier, TelegramSendError, redact_token,
)
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.workers.cleanup_worker import CleanupWorker
from app.workers.notification_worker import NotificationWorker, is_permanent_error

TOKEN = "123456789:AAHsecretTOKENvalue_xyz-abc"


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {"ok": status < 400}
        self.reason = "ERR" if status >= 400 else "OK"

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} for url", response=self)


class _Cfg:
    def __init__(self, **kw):
        self.data = {"backend_url": "", "backend_login": "", "backend_password": ""}
        self.backend_enabled = kw.get("backend_enabled", False)
        self.telegram_enabled = kw.get("telegram_enabled", True)
        self.telegram_token = TOKEN
        self.telegram_chat_ids = kw.get("chat_ids", ["111", "222"])
        self.violations_dir = kw.get("violations_dir", Path("violations"))

    def get(self, key, default=None):
        return self.data.get(key, default)

    def get_cameras(self):
        return []


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = ViolationsDB(str(self.root / "t.db"))

    def tearDown(self):
        try:
            self.db.close_current_thread()
        except Exception:
            pass
        self.tmp.cleanup()

    def _jobs(self):
        rows = self.db._conn().execute("SELECT * FROM notification_jobs ORDER BY id").fetchall()
        return [dict(r) for r in rows]


# ── 1. Retention ────────────────────────────────────────────────────────────

class RetentionTests(_Base):
    def _add(self, days_ago, status):
        ts = int(time.time() - days_ago * 86400)
        return self.db.add_violation(track_id=1, timestamp=ts, camera_name="K", sync_status=status)

    def _count(self):
        return self.db._conn().execute("SELECT COUNT(*) FROM violations").fetchone()[0]

    def test_db_retention_keeps_recent_and_unsynced_rows(self):
        self._add(30, "synced")        # 30 kunlik grafik uchun kerak
        self._add(400, "synced")       # o'chiriladi
        for st in ("queued", "local", "failed"):
            self._add(400, st)         # yuborilmagan — saqlanadi
        deleted = self.db.cleanup_old(365)
        self.assertEqual(deleted, 1)
        self.assertEqual(self._count(), 4)

    def test_worker_uses_separate_db_retention_and_respects_cleanup_files(self):
        vdir = self.root / "violations"
        vdir.mkdir()
        old = vdir / "old.jpg"
        old.write_bytes(b"x")
        past = time.time() - 30 * 86400
        os.utime(old, (past, past))
        self._add(30, "synced")
        cfg = _Cfg(violations_dir=vdir)

        CleanupWorker(self.db, cfg, keep_days=7, cleanup_files=False, keep_db_days=365).run()
        self.assertTrue(old.exists())          # cleanup_files=False — fayl tegilmaydi
        self.assertEqual(self._count(), 1)     # 7 kunlik fayl retention DB'ga ta'sir qilmaydi

        CleanupWorker(self.db, cfg, keep_days=7, cleanup_files=True, keep_db_days=365).run()
        self.assertFalse(old.exists())
        self.assertEqual(self._count(), 1)

    def test_files_of_unsynced_violations_are_protected_when_backend_enabled(self):
        vdir = self.root / "violations"
        vdir.mkdir()
        keep = vdir / "keep.jpg"
        keep.write_bytes(b"x")
        past = time.time() - 30 * 86400
        os.utime(keep, (past, past))
        self.db.add_violation(track_id=1, crop_path=str(keep), camera_name="K",
                              timestamp=int(past), sync_status="queued")
        cfg = _Cfg(violations_dir=vdir, backend_enabled=True)
        CleanupWorker(self.db, cfg, keep_days=7, cleanup_files=True).run()
        self.assertTrue(keep.exists())


# ── 3. Atomar job claiming ─────────────────────────────────────────────────

class ClaimTests(_Base):
    def test_claim_is_exclusive_and_stale_sending_is_reset(self):
        job = self.db.add_notification_job("telegram", {"track_id": 1})
        self.assertTrue(self.db.claim_notification_job(job))
        self.assertFalse(self.db.claim_notification_job(job))   # ikkinchi marta olinmaydi
        self.assertEqual(self.db.get_pending_notification_jobs(), [])
        self.assertEqual(self.db.reset_stale_sending_jobs(), 1)
        self.assertEqual(self._jobs()[0]["status"], "pending")

    def test_worker_skips_job_claimed_elsewhere(self):
        job = self.db.add_notification_job("telegram", {"track_id": 1})
        w = NotificationWorker(self.db, _Cfg())
        w._running = True
        jobs = self.db.get_pending_notification_jobs()
        self.db.claim_notification_job(job)      # boshqa worker oldin oldi
        with mock.patch("requests.post") as post:
            w._process_job(jobs[0])
        post.assert_not_called()
        self.assertEqual(self._jobs()[0]["status"], "sending")


# ── 2/4. Telegram: token yashirish, chat bo'yicha yetkazish ────────────────

class TelegramTests(_Base):
    def _worker(self, **kw):
        w = NotificationWorker(self.db, _Cfg(**kw))
        w._running = True
        w.queue.backoff_seconds = lambda retry, **_: 0.0
        return w

    def test_redact_token(self):
        msg = f"Max retries for url: /bot{TOKEN}/sendPhoto"
        self.assertNotIn(TOKEN, redact_token(msg))
        self.assertNotIn(TOKEN, redact_token(msg, TOKEN))

    def test_retry_skips_already_delivered_chats(self):
        import requests
        img = self.root / "c.jpg"
        img.write_bytes(b"jpg")
        self.db.add_notification_job("telegram", {"track_id": 5, "crop_path": str(img)})
        w = self._worker()
        calls = []

        def flaky(url, data=None, **kw):
            calls.append(data["chat_id"])
            if data["chat_id"] == "222" and calls.count("222") == 1:
                raise requests.ConnectionError(f"failed: https://api.telegram.org/bot{TOKEN}/sendPhoto")
            return _Resp(200)

        with mock.patch("requests.post", side_effect=flaky):
            w._drain_once()
            job = self._jobs()[0]
            self.assertEqual(job["status"], "pending")
            self.assertNotIn(TOKEN, job["last_error"])        # token bazaga tushmaydi
            self.assertEqual(json.loads(job["payload"])["delivered_chat_ids"], ["111"])
            w._drain_once()
        self.assertEqual(calls, ["111", "222", "222"])       # 111 ga qayta yuborilmadi
        self.assertEqual(self._jobs()[0]["status"], "sent")

    def test_no_image_sends_text_message(self):
        self.db.add_notification_job("telegram", {"track_id": 5, "crop_path": ""})
        w = self._worker(chat_ids=["111"])
        with mock.patch("requests.post", return_value=_Resp(200)) as post:
            w._drain_once()
        self.assertTrue(post.call_args[0][0].endswith("/sendMessage"))
        self.assertEqual(self._jobs()[0]["status"], "sent")

    def test_notifier_permanent_flag(self):
        n = TelegramNotifier(TOKEN, ["1", "2"])
        with mock.patch("requests.post", return_value=_Resp(400, {"description": "chat not found"})):
            with self.assertRaises(TelegramSendError) as ctx:
                n.send_message("x")
        self.assertTrue(ctx.exception.permanent)
        with mock.patch("requests.post", return_value=_Resp(429)):
            with self.assertRaises(TelegramSendError) as ctx:
                n.send_message("x")
        self.assertFalse(ctx.exception.permanent)


# ── 6. Abadiy 4xx -> 'rejected' ───────────────────────────────────────────

class PermanentErrorTests(_Base):
    def test_classification(self):
        for code, expected in ((400, True), (403, True), (422, True), (401, False),
                               (408, False), (429, False), (500, False), (503, False)):
            exc = Exception("x")
            exc.response = _Resp(code)
            self.assertEqual(is_permanent_error(exc), expected, code)
        self.assertFalse(is_permanent_error(ConnectionError("down")))

    def test_backend_400_is_rejected_and_not_backfilled(self):
        cfg = _Cfg(backend_enabled=True, telegram_enabled=False)
        cfg.data.update(backend_url="http://127.0.0.1:9", backend_login="u",
                        backend_password="pw-secret")
        self.db.add_violation(track_id=7, camera_name="K", timestamp=1_700_000_000,
                              sync_status="local")
        w = NotificationWorker(self.db, cfg)
        w._running = True
        w._backfill_unsent()

        def fake_post(url, json=None, headers=None, **kw):
            if url.endswith("/device-login"):
                return _Resp(200, {"data": {"token": {"access": "a.b.c", "refresh": ""}}})
            return _Resp(400, {"message": "bad"})

        with mock.patch("requests.post", side_effect=fake_post):
            w._drain_all()
        self.assertEqual(self._jobs()[0]["status"], "rejected")
        st = self.db._conn().execute("SELECT sync_status FROM violations").fetchone()[0]
        self.assertEqual(st, "rejected")
        w._backfill_unsent()
        self.assertEqual(len(self._jobs()), 1)   # qayta navbatga qo'yilmadi

    def test_backend_sends_stable_idempotency_key(self):
        cfg = _Cfg(backend_enabled=True, telegram_enabled=False)
        cfg.data.update(backend_url="http://127.0.0.1:9", backend_login="u", backend_password="p")
        self.db.add_notification_job("backend", {"track_id": 1, "timestamp": 1_700_000_000,
                                                 "camera_name": "K"})
        w = NotificationWorker(self.db, cfg)
        w._running = True
        w.queue.backoff_seconds = lambda retry, **_: 0.0
        keys = []

        def fake_post(url, json=None, headers=None, **kw):
            if url.endswith("/device-login"):
                return _Resp(200, {"data": {"token": {"access": "a.b.c", "refresh": ""}}})
            keys.append(headers.get("Idempotency-Key"))
            return _Resp(503 if len(keys) == 1 else 201)

        with mock.patch("requests.post", side_effect=fake_post):
            w._drain_once()
            w._drain_once()
        self.assertEqual(len(keys), 2)
        self.assertTrue(keys[0])
        self.assertEqual(keys[0], keys[1])


# ── 8. Tranzaksion enqueue ──────────────────────────────────────────────────

class _NoFiles:
    def save_violation_images(self, **kw):
        return "", "", None


class ViolationServiceTests(_Base):
    def _register(self, **kw):
        svc = ViolationService(self.db, file_storage=_NoFiles())
        return svc.register_violation(
            frame=np.zeros((10, 10, 3), np.uint8), person={"track_id": 3, "box": []},
            camera_name="K", company_id="", violations_dir=self.root, save_files=False, **kw)

    def test_jobs_enqueued_even_without_images(self):
        self._register(notifier=object(), backend=object())
        jobs = self._jobs()
        self.assertEqual(sorted(j["channel"] for j in jobs), ["backend", "telegram"])
        vid = self.db._conn().execute("SELECT id FROM violations").fetchone()[0]
        for j in jobs:
            p = json.loads(j["payload"])
            self.assertEqual(p["violation_id"], vid)
            self.assertTrue(p["idempotency_key"])

    def test_violation_and_jobs_rollback_together(self):
        real = self.db._insert_job

        def boom(*a, **kw):
            raise sqlite3.OperationalError("disk full")

        self.db._insert_job = boom
        with self.assertRaises(sqlite3.OperationalError):
            self._register(backend=object())
        self.db._insert_job = real
        n = self.db._conn().execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        self.assertEqual(n, 0)


# ── 9. Karantin faqat haqiqiy buzilishda ───────────────────────────────────

class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "q.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_garbage_file_is_quarantined(self):
        self.path.write_bytes(b"this is definitely not sqlite" * 100)
        db = ViolationsDB(str(self.path))
        self.assertTrue(db.recovered_from_corruption)
        self.assertTrue(db.recovery_backup_paths)
        db.add_violation(track_id=1)
        db.close_current_thread()

    def test_locked_db_is_not_quarantined(self):
        ViolationsDB(str(self.path)).close_current_thread()
        with mock.patch.object(ViolationsDB, "_ensure_healthy",
                               side_effect=sqlite3.OperationalError("database is locked")):
            with self.assertRaises(sqlite3.OperationalError):
                ViolationsDB(str(self.path))
        self.assertTrue(self.path.exists())
        self.assertEqual(list(Path(self.tmp.name).glob("*.corrupt.*")), [])


if __name__ == "__main__":
    unittest.main()
