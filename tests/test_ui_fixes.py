"""UI tuzatishlari: non-ASCII rasm yo'li, Hodisalar SQL filtrlari, xodim dialogi
validatsiyasi, sozlash ustasi thread'i dialog yopilgandan keyin."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import date, datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.infrastructure.persistence.sqlite_db import ViolationsDB  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "images" / "camera-card-factory.jpg"

_app = QApplication.instance() or QApplication(sys.argv)


def _pump(sec: float = 0.2):
    end = time.time() + sec
    while time.time() < end:
        _app.processEvents()
        time.sleep(0.01)


class NonAsciiImagePathTest(unittest.TestCase):
    @unittest.skipUnless(SAMPLE.exists(), "namuna rasm yo'q")
    def test_imread_reads_cyrillic_path(self):
        from app.application.services import faceid_service as fs
        tmp = Path(tempfile.mkdtemp(prefix="фото_"))
        try:
            dst = tmp / "Ходим_ўғил.jpg"
            shutil.copy(SAMPLE, dst)
            img = fs._imread(dst)
            self.assertIsNotNone(img)
            self.assertEqual(img.ndim, 3)
            self.assertEqual(fs.photos_with_face([str(dst)]), fs.photos_with_face([str(SAMPLE)]))
            self.assertIsNone(fs._imread(tmp / "yoq.jpg"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ViolationsFilterSqlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = ViolationsDB(os.path.join(self.tmp, "v.db"))
        now = int(datetime.combine(date.today(), datetime.min.time()).timestamp()) + 3600
        rows = [
            # camera, conf, dept, review, employee, track
            ("Kirish", 0.95, 1, "new", "Ali Valiyev", 12),
            ("Kirish", 0.55, None, "confirmed", "", 13),
            ("Ombor", 0.85, 2, "review", "Vali", 14),
            ("Ombor", 0.90, 2, "rejected", "", 15),
            ("Sex", 0.60, None, None, "", 7),
        ]
        conn = self.db._conn()
        for i, (cam, conf, dept, st, emp, tid) in enumerate(rows):
            conn.execute(
                "INSERT INTO violations (timestamp, track_id, camera_name, confidence, created_at,"
                " department_id, review_status, employee_name) VALUES (?,?,?,?,?,?,?,?)",
                (now + i, tid, cam, conf, "x", dept, st, emp))
        conn.commit()
        self.f0 = {"ts_from": now - 10, "ts_to": now + 100, "cam": None, "dept": None, "dept_cams": [],
                   "conf": 0.0, "search": "", "status": "all"}

    def tearDown(self):
        self.db.close_current_thread()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rows(self, **kw):
        from app.ui.pages.violations_page import _build_where
        f = {**self.f0, **kw}
        where, params = _build_where(f)
        return [dict(r) for r in self.db._conn().execute(
            f"SELECT * FROM violations WHERE {where} ORDER BY timestamp", params)]

    def test_rejected_always_hidden(self):
        self.assertEqual(len(self._rows()), 4)

    def test_status_new_includes_null(self):
        self.assertEqual({r["camera_name"] for r in self._rows(status="new")}, {"Kirish", "Sex"})

    def test_department_falls_back_to_camera(self):
        rows = self._rows(dept=1, dept_cams=["Kirish"])
        self.assertEqual({r["track_id"] for r in rows}, {12, 13})

    def test_confidence_and_search(self):
        self.assertEqual({r["track_id"] for r in self._rows(conf=0.8)}, {12, 14})
        self.assertEqual({r["track_id"] for r in self._rows(search="vali")}, {12, 14})
        self.assertEqual({r["track_id"] for r in self._rows(search="0007")}, {7})

    def test_python_matcher_agrees_with_sql(self):
        from app.ui.pages.violations_page import ViolationsPage
        all_rows = [dict(r) for r in self.db._conn().execute(
            "SELECT * FROM violations WHERE COALESCE(review_status,'') != 'rejected'")]
        for kw in ({}, {"dept": 1, "dept_cams": ["Kirish"]}, {"conf": 0.8}, {"search": "vali"},
                   {"search": "0007"}, {"cam": "Ombor"}):
            f = {**self.f0, **kw}
            sql = {r["id"] for r in self._rows(**kw)}
            py = {r["id"] for r in all_rows if ViolationsPage._matches(r, f)}
            self.assertEqual(sql, py, kw)


class _Cfg:
    def __init__(self, users):
        self.users = users

    def get_users(self):
        return self.users

    def get_departments(self):
        return [{"id": 1, "name": "Sex"}]


class EmployeeDialogValidationTest(unittest.TestCase):
    def test_required_and_duplicate(self):
        from app.ui.pages.users_page import _EmployeeDialog
        cfg = _Cfg([{"id": 1, "first_name": "Ali", "last_name": "V", "employee_id": "X-1"},
                    {"id": 2, "first_name": "Bek", "last_name": "S", "employee_id": "X-2"}])
        dlg = _EmployeeDialog(cfg, None)
        self.assertIn("Kiritilishi shart", dlg.validation_error())
        dlg.fn.setText("Yangi")
        dlg.ln.setText("Xodim")
        dlg.eid.setText("x-1")
        self.assertIn("allaqachon bor", dlg.validation_error())
        dlg._try_accept()
        self.assertFalse(dlg.err.isHidden())          # dialog yopilmadi, xato ko'rsatildi
        dlg.eid.setText("X-3")
        self.assertEqual(dlg.validation_error(), "")

        edit = _EmployeeDialog(cfg, cfg.users[1])
        self.assertEqual(edit.validation_error(), "")  # o'z ID'si — dublikat emas
        edit.eid.setText("X-1")
        self.assertIn("allaqachon bor", edit.validation_error())


class _WizCfg(dict):
    def get_cameras(self):
        return []


class SetupWizardThreadTest(unittest.TestCase):
    def test_thread_outlives_closed_dialog(self):
        from app.ui.widgets import setup_wizard as sw

        orig = sw._CheckThread._check_backend
        sw._CheckThread._check_backend = lambda self: (time.sleep(0.4), (True, "ok"))[1]
        try:
            wiz = sw.SetupWizard(_WizCfg())
            wiz._test_backend()
            self.assertEqual(len(sw._RUNNING_CHECKS), 1)
            wiz.done(0)
            wiz.deleteLater()
            del wiz
            _pump(0.1)
            deadline = time.time() + 5
            while sw._RUNNING_CHECKS and time.time() < deadline:
                _pump(0.05)
            self.assertEqual(len(sw._RUNNING_CHECKS), 0)
        finally:
            sw._CheckThread._check_backend = orig


if __name__ == "__main__":
    unittest.main()
