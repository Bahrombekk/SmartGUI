"""FaceID: ro'yxatga olish, tanish, rasm almashtirilganda yangilash, nofaol xodim."""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import cv2

from app.application.services.faceid_service import FaceIdService
from app.infrastructure.persistence.sqlite_db import ViolationsDB

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "images" / "camera-card-factory.jpg"


class _Cfg:
    def __init__(self, users, **extra):
        self.users = users
        self.data = {"faceid_threshold": 0.42, "faceid_min_face_px": 40, **extra}

    def get(self, k, default=None):
        return self.data.get(k, default)

    def get_users(self):
        return self.users


@unittest.skipUnless(SAMPLE.exists() and (ROOT / "app" / "models" / "sface.onnx").exists(),
                     "namuna rasm yoki SFace modeli yo'q")
class FaceIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = ViolationsDB(os.path.join(self.tmp, "t.db"))
        self.photo = os.path.join(self.tmp, "emp.jpg")
        shutil.copy(SAMPLE, self.photo)
        self.users = [{"employee_id": "E1", "first_name": "Ali", "last_name": "Valiyev",
                       "photo_path": self.photo, "active": True}]

    def tearDown(self):
        try:
            self.db.close_current_thread()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enroll_and_match_same_person(self):
        svc = FaceIdService(self.db, _Cfg(self.users))
        self.assertEqual(svc.enroll_from_settings_users(), 1)
        img = cv2.imread(self.photo)
        small = cv2.resize(img, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA)
        ident = svc.match_person_crop(small)
        self.assertIsNotNone(ident)
        self.assertTrue(ident.matched)
        self.assertEqual(ident.employee_id, "E1")

    def test_unchanged_photo_is_not_reenrolled_changed_photo_is(self):
        svc = FaceIdService(self.db, _Cfg(self.users))
        self.assertEqual(svc.enroll_from_settings_users(), 1)
        self.assertEqual(svc.enroll_from_settings_users(), 0)
        time.sleep(1.1)
        img = cv2.imread(self.photo)
        cv2.imwrite(self.photo, cv2.flip(img, 1))  # rasm almashtirildi
        self.assertEqual(svc.enroll_from_settings_users(), 1)

    def test_inactive_employee_is_not_matched(self):
        svc = FaceIdService(self.db, _Cfg(self.users))
        svc.enroll_from_settings_users()
        self.users[0]["active"] = False
        svc._cache_loaded = False
        self.assertIsNone(svc.match_person_crop(cv2.imread(self.photo)))

    def test_employee_added_later_is_recognized_without_restart(self):
        users = []
        svc = FaceIdService(self.db, _Cfg(users))
        svc.enroll_from_settings_users()
        img = cv2.imread(self.photo)
        self.assertIsNone(svc.match_person_crop(img))  # hali xodim yo'q
        users.extend(self.users)                       # UI xodim qo'shdi
        svc._last_sync -= svc.SYNC_INTERVAL + 1        # 30 s o'tdi
        ident = svc.match_person_crop(img)
        self.assertTrue(ident and ident.matched)

    def test_photos_are_copied_and_checked(self):
        from app.application.services import faceid_service as fs
        from unittest import mock
        with mock.patch.object(fs, "data_path", lambda *p: Path(self.tmp, "data", *p)):
            stored = fs.store_employee_photos("E 1/x", [self.photo, os.path.join(self.tmp, "yoq.jpg")])
        self.assertEqual(len(stored), 1)
        self.assertTrue(Path(stored[0]).is_file())
        self.assertIn(str(Path(self.tmp, "data", "faces")), stored[0])
        blank = os.path.join(self.tmp, "blank.jpg")
        cv2.imwrite(blank, (cv2.imread(self.photo) * 0))
        self.assertEqual(fs.photos_with_face([self.photo, blank]), [True, False])

    def test_tiny_face_is_ignored(self):
        svc = FaceIdService(self.db, _Cfg(self.users))
        svc.enroll_from_settings_users()
        img = cv2.imread(self.photo)
        tiny = cv2.resize(img, None, fx=0.08, fy=0.08, interpolation=cv2.INTER_AREA)
        self.assertFalse(svc.has_face(tiny))
        self.assertIsNone(svc.match_person_crop(tiny))



@unittest.skipUnless(SAMPLE.exists() and (ROOT / "app" / "models" / "sface.onnx").exists(),
                     "namuna rasm yoki SFace modeli yo'q")
class TrackIdentityTests(unittest.TestCase):
    """Uzoq kamera: bitta kichik kadr emas, bir necha kadr birlashtirilib qaror qilinadi."""

    def setUp(self):
        from app.application.services.faceid_service import TrackIdentity
        self.tmp = tempfile.mkdtemp()
        self.photo = os.path.join(self.tmp, "emp.jpg")
        shutil.copy(SAMPLE, self.photo)
        users = [{"employee_id": "E1", "first_name": "Ali", "last_name": "V",
                  "photo_path": self.photo, "active": True}]
        self.db = ViolationsDB(os.path.join(self.tmp, "t.db"))
        self.svc = FaceIdService(self.db, _Cfg(users, faceid_min_face_px=24))
        self.svc.enroll_from_settings_users()
        self.track = TrackIdentity(self.svc)
        img = cv2.imread(self.photo)
        face_w = self.svc._detect_face(img)[2]
        s = 30.0 / face_w            # yuz ~30 px — 5–6 m dagi kamera kabi
        small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        self.frame = cv2.imdecode(cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])[1], 1)

    def tearDown(self):
        try:
            self.db.close_current_thread()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_small_face_decided_after_several_frames(self):
        sample = self.svc.analyze(self.frame)
        self.assertIsNotNone(sample, "30 px yuz kattalashtirish bilan topilishi kerak")
        self.assertIsNone(self.track.add(7, sample))          # 1 kadr — hali qaror yo'q
        self.assertIsNone(self.track.add(7, self.svc.analyze(self.frame)))
        ident = self.track.add(7, self.svc.analyze(self.frame))  # 3-kadr — qaror
        self.assertTrue(ident is not None and ident.matched)
        self.assertEqual(self.track.identity(7).employee_id, "E1")
        self.assertIsNone(self.track.add(7, sample))          # aniqlangach qayta hisoblanmaydi


if __name__ == "__main__":
    unittest.main()
