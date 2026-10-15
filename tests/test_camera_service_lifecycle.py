import threading
import time
import unittest
from unittest import mock

from app.workers import camera_service
from app.workers.camera_service import CameraService


class FakeGroup:
    """DetectorGroup o'rnida: model yuklash `load_delay` s davom etadi."""
    load_delay = 0.0
    fail = False
    created: list = []
    lock = threading.Lock()

    def __init__(self, group_id, readers, **_kw):
        time.sleep(FakeGroup.load_delay)
        if FakeGroup.fail:
            raise RuntimeError("model buzilgan")
        self.readers = list(readers)
        self.started = False
        self.stopped = False
        with FakeGroup.lock:
            FakeGroup.created.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        pass


def make_service():
    return CameraService(model_path="x.pt", device="cpu", cameras_per_model=3)


class CameraServiceLifecycleTests(unittest.TestCase):
    def setUp(self):
        FakeGroup.load_delay = 0.0
        FakeGroup.fail = False
        FakeGroup.created = []
        patcher = mock.patch.object(camera_service, "DetectorGroup", FakeGroup)
        patcher.start()
        self.addCleanup(patcher.stop)

    def running(self):
        return [g for g in FakeGroup.created if g.started and not g.stopped]

    def test_overlapping_restarts_leave_no_orphan_groups(self):
        FakeGroup.load_delay = 0.8          # debounce (0.6 s) dan uzoqroq
        svc = make_service()
        r1, r2 = object(), object()
        seq1 = svc.add_camera(1, r1)
        time.sleep(0.7)                     # 1-restart model yuklayapti
        seq2 = svc.add_camera(2, r2)
        self.assertIsNone(svc.wait_ready(seq2, timeout=5))
        self.assertGreaterEqual(seq2, seq1)
        live = self.running()
        self.assertEqual(len(live), 1, "faqat bitta guruh ishlashi kerak")
        self.assertEqual(set(map(id, live[0].readers)), {id(r1), id(r2)})
        svc.stop()

    def test_stop_during_model_load_does_not_start_groups(self):
        FakeGroup.load_delay = 0.5
        svc = make_service()
        seq = svc.add_camera(1, object())
        time.sleep(0.8)                     # Timer ishga tushdi, model yuklanmoqda
        svc.stop()
        self.assertEqual(svc.wait_ready(seq, timeout=1), "AI servis to'xtatildi")
        time.sleep(0.5)
        self.assertEqual(self.running(), [])

    def test_stale_worker_cannot_unregister_new_reader(self):
        svc = make_service()
        old_reader, new_reader = object(), object()
        svc.wait_ready(svc.add_camera(5, old_reader), timeout=5)
        svc.wait_ready(svc.add_camera(5, new_reader), timeout=5)   # yangi worker
        self.assertFalse(svc.remove_camera(5, old_reader))         # eski worker kech to'xtadi
        self.assertIs(svc._readers.get(5), new_reader)
        self.assertTrue(svc.remove_camera(5, new_reader))
        svc.stop()

    def test_model_load_error_is_reported(self):
        FakeGroup.fail = True
        svc = make_service()
        err = svc.wait_ready(svc.add_camera(1, object()), timeout=5)
        self.assertIn("model buzilgan", err or "")
        svc.stop()


if __name__ == "__main__":
    unittest.main()
