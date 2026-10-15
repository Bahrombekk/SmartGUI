"""Detection/violation pipeline tuzatishlari uchun testlar (kamera/modelsiz)."""
import json
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import numpy as np

from app.application.services import tracking
from app.application.services.tracking import IoUTracker
from app.application.services.violation_runtime import ViolationRuntime
from app.config.settings_manager import ConfigManager
from app.infrastructure.persistence import file_storage
from app.infrastructure.persistence.file_storage import ViolationFileStorage
from app.workers.detection_worker import DetectionWorker


class DummyCfg:
    telegram_enabled = False
    telegram_token = ""
    telegram_chat_ids = []
    backend_enabled = False
    camera_name = "Kamera 1"
    camera_id = 1
    company_id = ""
    department_id = None
    violations_dir = Path(".")
    save_violations = False
    polygon_points = []

    def __init__(self, **overrides):
        self.values = {
            "violation_save_queue_size": 16,
            "confirmation_threshold": 3,
            "violation_cooldown": 10,
            "tracking_strictness": "balanced",
        }
        self.values.update(overrides)

    def get(self, key, default=None):
        return self.values.get(key, default)


def person(tid, box, has_helmet=False):
    return {"track_id": tid, "box": list(box), "has_helmet": has_helmet, "track_confirmed": True}


def make_runtime(**cfg):
    errors = []
    rt = ViolationRuntime(DummyCfg(**cfg), db=None, emit_payload=lambda p: None,
                          emit_error=errors.append)
    return rt, errors


class ViolationThresholdTests(unittest.TestCase):
    def test_violation_still_new_after_threshold_frame_was_skipped(self):
        rt, _ = make_runtime()
        # Boshqa (o'lik) track yaqinda shu joyda buzilish qoldirgan
        rt.remember_spatial_violation(person(99, [100, 100, 180, 260]), "no_helmet")
        p = lambda: [person(1, [104, 100, 184, 260])]
        flags = [rt.mark_no_helmet_candidates(p())[0]["is_new_violation"] for _ in range(4)]
        self.assertEqual(flags, [False, False, False, False])  # 3-kadr duplicate bilan bloklandi
        # Cooldown o'tdi — keyingi kadrda (threshold dan keyin) baribir yangi
        rt.spatial_violations[0]["ts"] -= 60
        self.assertTrue(rt.mark_no_helmet_candidates(p())[0]["is_new_violation"])

    def test_saved_violation_not_repeated(self):
        rt, _ = make_runtime()
        frame = np.zeros((300, 300, 3), np.uint8)
        for _ in range(3):
            persons = rt.mark_no_helmet_candidates([person(1, [10, 10, 80, 200])])
        self.assertTrue(persons[0]["is_new_violation"])
        rt.handle_violation(frame, persons[0])
        persons = rt.mark_no_helmet_candidates([person(1, [10, 10, 80, 200])])
        self.assertFalse(persons[0]["is_new_violation"])

    def test_person_entering_zone_after_threshold_is_recorded(self):
        # Zona filtri buzilish tekshiruvidan OLDIN: zonadan tashqarida odam
        # ro'yxatda yo'q, zonaga kirgach chegaraga yetganda qayd etiladi.
        rt, _ = make_runtime()
        for _ in range(5):
            rt.mark_no_helmet_candidates([])          # zonadan tashqarida (filtrlangan)
        flags = [rt.mark_no_helmet_candidates([person(1, [10, 10, 80, 200])])[0]["is_new_violation"]
                 for _ in range(3)]
        self.assertEqual(flags, [False, False, True])

    def test_polygon_filter_runs_before_violation_check_in_worker(self):
        import inspect
        src = inspect.getsource(DetectionWorker._run_body)
        self.assertLess(src.index("self._filter_by_polygon(persons, frame)"),
                        src.index("self._check_violations(persons)"))

    def test_side_by_side_workers_both_recorded(self):
        rt, _ = make_runtime()
        frame = np.zeros((400, 600, 3), np.uint8)
        a = [10, 100, 90, 300]
        b = [70, 100, 150, 300]   # ~60 px yonida — max_dist ichida
        for _ in range(3):
            persons = rt.mark_no_helmet_candidates([person(1, a), person(2, b)])
        new = {p["track_id"]: p["is_new_violation"] for p in persons}
        self.assertTrue(new[1])
        rt.handle_violation(frame, persons[0])
        # B: A hali kadrda faol — demak boshqa odam, bloklanmaydi
        persons = rt.mark_no_helmet_candidates([person(1, a), person(2, b)])
        new = {p["track_id"]: p["is_new_violation"] for p in persons}
        self.assertFalse(new[1])
        self.assertTrue(new[2])

    def test_new_track_at_same_place_blocked_only_while_recent(self):
        rt, _ = make_runtime()
        frame = np.zeros((400, 600, 3), np.uint8)
        box = [10, 100, 90, 300]
        for _ in range(3):
            persons = rt.mark_no_helmet_candidates([person(1, box)])
        rt.handle_violation(frame, persons[0])
        # Track 1 yo'qoldi, shu joyda yangi ID (o'sha odam) — cooldown ichida bloklanadi
        for _ in range(4):
            persons = rt.mark_no_helmet_candidates([person(2, box)])
            self.assertFalse(persons[0]["is_new_violation"])
        rt.spatial_violations[0]["ts"] -= 60
        persons = rt.mark_no_helmet_candidates([person(2, box)])
        self.assertTrue(persons[0]["is_new_violation"])

    def test_prune_tracks_drops_dead_ids(self):
        rt, _ = make_runtime()
        rt.saved_violations.update({(1, "no_helmet"), (2, "no_helmet")})
        rt.access_frames.update({1: 3, 2: 5})
        rt.prune_tracks({2})
        self.assertEqual(rt.saved_violations, {(2, "no_helmet")})
        self.assertEqual(rt.access_frames, {2: 5})


class WriterDrainTests(unittest.TestCase):
    def test_stop_writer_drains_queue(self):
        rt, _ = make_runtime()
        done = []

        class SlowService:
            def register_violation(self, **kw):
                time.sleep(0.15)
                done.append(kw["person"]["track_id"])
                return mock.Mock(to_payload=lambda: {})

        class Db:
            def get_today_count(self, *a):
                return 0

        rt.violation_service = SlowService()
        rt.db = Db()
        rt.start_writer(1)
        frame = np.zeros((50, 50, 3), np.uint8)
        for tid in range(1, 11):
            rt.handle_violation(frame, person(tid, [tid * 100, 0, tid * 100 + 40, 40]))
        rt.stop_writer()
        self.assertEqual(sorted(done), list(range(1, 11)))


class FakeDb:
    def __init__(self):
        self.detections = 7
        self.today = 4
        self.cam_today = 2

    def get_daily_detections(self, name):
        return self.detections

    def get_today_count(self, *a):
        return self.today

    def get_today_count_for_camera(self, cid, name):
        return self.cam_today


class DayRolloverTests(unittest.TestCase):
    def test_counters_reset_after_midnight(self):
        w = DetectionWorker(DummyCfg(), db=FakeDb())
        w._stats_date = date.today() - timedelta(days=1)
        w._detections_today = 500
        w._seen_detection_tracks.update({1, 2, 3})
        w._violation_runtime.camera_today = 40
        self.assertTrue(w._check_day_rollover())
        self.assertEqual(w._detections_today, 7)
        self.assertEqual(w._seen_detection_tracks, set())
        self.assertEqual(w._violation_runtime.camera_today, 2)
        self.assertEqual(w._violation_runtime.today_count, 4)
        self.assertFalse(w._check_day_rollover())

    def test_dead_track_state_is_pruned(self):
        w = DetectionWorker(DummyCfg(tracker_max_age=1), db=FakeDb())
        w._process_detections([{"class_id": 0, "box": [10, 10, 80, 140], "score": 0.9}])
        w._update_detection_counter([{"track_id": 1}])
        w._face_last_recog[1] = 1.0
        w._saved_violations.add((1, "no_helmet"))
        for _ in range(3):
            w._process_detections([])
        w._prune_dead_tracks()
        self.assertEqual(w._seen_detection_tracks, set())
        self.assertEqual(w._face_last_recog, {})
        self.assertNotIn((1, "no_helmet"), w._violation_runtime.saved_violations)


class TrackIdTests(unittest.TestCase):
    def test_global_ids_not_reused_across_trackers_and_reset(self):
        det = [{"box": [10, 10, 60, 120], "score": 0.9}]
        t1 = IoUTracker()
        t1.enable_global_ids()
        a = t1.update(det)[0]["track_id"]
        t1.reset()
        b = t1.update(det)[0]["track_id"]
        t2 = IoUTracker()   # "qayta ishga tushgan" worker
        t2.enable_global_ids()
        c = t2.update(det)[0]["track_id"]
        self.assertEqual(len({a, b, c}), 3)
        self.assertGreater(a, 1000)  # vaqtga bog'liq boshlang'ich qiymat

    def test_global_id_start_is_time_based(self):
        with mock.patch.object(tracking, "_global_next_id", None):
            first = tracking.next_global_track_id()
        self.assertGreater(first, int((time.time() - tracking._GLOBAL_ID_EPOCH) * 10) - 50)


class FileStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "buzilishlar_нарушения"
        self.frame = np.full((240, 320, 3), 120, np.uint8)

    def tearDown(self):
        self.tmp.cleanup()

    def _save(self, **kw):
        args = dict(frame=self.frame, box=[50, 50, 120, 200], output_dir=self.dir,
                    track_id=1, timestamp=int(time.time()))
        args.update(kw)
        return ViolationFileStorage().save_violation_images(**args)

    def test_same_second_same_track_different_cameras_do_not_collide(self):
        ts = int(time.time())
        c1, f1, _ = self._save(timestamp=ts, camera_id=1)
        c2, f2, _ = self._save(timestamp=ts, camera_id=2)
        c3, f3, _ = self._save(timestamp=ts)  # camera_id berilmasa ham
        self.assertEqual(len({c1, c2, c3, f1, f2, f3}), 6)
        for p in (c1, c2, c3, f1, f2, f3):
            self.assertTrue(Path(p).is_file(), p)  # kirill papka ham ishlaydi
        self.assertIn("cam2", Path(c2).name)

    def test_failed_write_stores_empty_path(self):
        with mock.patch.object(file_storage.cv2, "imencode", return_value=(False, None)):
            crop, full, crop_frame = self._save()
        self.assertEqual((crop, full), ("", ""))
        self.assertIsNotNone(crop_frame)
        self.assertEqual(list(self.dir.glob("*")), [])


class SettingsBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _good(self):
        cm = ConfigManager(str(self.path))
        cm.set("cameras", [{"id": 1, "name": "Darvoza", "rtsp_url": "rtsp://x/1"}])
        cm.set("setup_completed", True)
        self.assertTrue(cm.save())
        self.assertTrue(cm.save())  # ikkinchi saqlash .bak yaratadi
        return cm

    def test_corrupt_settings_restored_from_backup_and_quarantined(self):
        self._good()
        self.assertTrue((self.path.parent / "settings.json.bak").is_file())
        self.path.write_text("{ buzilgan json", encoding="utf-8")
        cm = ConfigManager(str(self.path))
        self.assertEqual(cm.get_cameras()[0]["name"], "Darvoza")
        self.assertTrue(cm.load_warning)
        bad = list(self.path.parent.glob("settings.json.bad.*"))
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].read_text(encoding="utf-8"), "{ buzilgan json")
        # Keyingi save buzilgan faylni .bak ga yozmaydi — yaxshi zaxira saqlanadi
        self.path.write_text("[1, 2", encoding="utf-8")
        cm.save()
        bak = json.loads((self.path.parent / "settings.json.bak").read_text(encoding="utf-8"))
        self.assertEqual(bak["cameras"][0]["name"], "Darvoza")

    def test_corrupt_settings_without_backup_keeps_copy(self):
        self.path.write_text("not json", encoding="utf-8")
        cm = ConfigManager(str(self.path))
        self.assertTrue(cm.load_warning)
        self.assertEqual(len(list(self.path.parent.glob("settings.json.bad.*"))), 1)
        self.assertTrue(cm.needs_setup_wizard)


class ReaderRetryTests(unittest.TestCase):
    def test_reader_keeps_retrying_after_max_reconnects(self):
        from app.infrastructure.camera import cv2_rtsp_reader as mod
        calls = {"max": 0, "attempt": 0}
        reader = mod.CV2RTSPReader(
            "rtsp://127.0.0.1:1/x", max_reconnects=2,
            on_reconnect_attempt=lambda *a: calls.__setitem__("attempt", calls["attempt"] + 1),
            on_max_retries=lambda: calls.__setitem__("max", calls["max"] + 1),
        )
        waits = []
        reader._interruptible_sleep = waits.append
        for _ in range(6):
            reader._fail_count += 1
            reader._after_failure()
        self.assertTrue(reader._running)
        self.assertEqual(calls["max"], 1)
        self.assertEqual(calls["attempt"], 2)
        self.assertEqual(waits[2:], [reader.MAX_BACKOFF] * 4)
        reader.reset_backoff()
        self.assertFalse(reader._limit_notified)

    def test_abandoned_open_is_released(self):
        from app.infrastructure.camera import cv2_rtsp_reader as mod
        released = threading.Event()
        proceed = threading.Event()

        class FakeCap:
            def __init__(self, *a):
                proceed.wait(2)

            def isOpened(self):
                return True

            def set(self, *a):
                pass

            def read(self):
                return True, np.zeros((32, 32, 3), np.uint8)

            def release(self):
                released.set()

        reader = mod.CV2RTSPReader("rtsp://127.0.0.1:1/x")
        reader.OPEN_TIMEOUT = 0.1
        with mock.patch.object(mod.cv2, "VideoCapture", FakeCap):
            for opts, api in ((mod._RTSP_OPTIONS_UDP, mod.cv2.CAP_FFMPEG),
                              (mod._RTSP_OPTIONS_ANY, mod.cv2.CAP_ANY)):
                released.clear()
                proceed.clear()
                self.assertIsNone(reader._try_open_cap(opts, "t", api=api))
                proceed.set()
                self.assertTrue(released.wait(2), opts)


if __name__ == "__main__":
    unittest.main()
