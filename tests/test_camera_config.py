"""Kamera qo'shish/saqlash: validatsiya va settings.json ga yozish."""
import json
import tempfile
import unittest
from pathlib import Path

from app.config.settings_manager import ConfigManager
from app.ui.pages.settings_common import validate_camera_fields

CAMS = [{"id": 1, "name": "Stansiya", "rtsp_url": "rtsp://10.0.0.1/s"}]


class ValidateCameraTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(validate_camera_fields("Yangi", "rtsp://10.0.0.2/s", "", CAMS), ([], []))

    def test_required_fields(self):
        errors, _ = validate_camera_fields("", "", "", CAMS)
        self.assertEqual(len(errors), 2)

    def test_duplicate_name_case_insensitive(self):
        errors, _ = validate_camera_fields("stansiya", "rtsp://10.0.0.2/s", "", CAMS)
        self.assertTrue(errors)

    def test_editing_same_camera_keeps_its_name(self):
        errors, _ = validate_camera_fields("Stansiya", "rtsp://10.0.0.1/s", "", CAMS, exclude_id=1)
        self.assertEqual(errors, [])

    def test_bad_scheme(self):
        errors, _ = validate_camera_fields("X", "10.0.0.2/stream", "", CAMS)
        self.assertTrue(errors)

    def test_duplicate_rtsp_and_non_uuid_company_are_warnings(self):
        errors, warnings = validate_camera_fields("X", "rtsp://10.0.0.1/s", "www", CAMS)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 2)


class ConfigSaveTests(unittest.TestCase):
    def test_added_camera_is_written_to_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            cfg = ConfigManager(str(path))
            before = len(cfg.get_cameras())
            cfg.add_camera("Ikkinchi", "rtsp://10.0.0.9/s", "")
            self.assertTrue(cfg.save())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["cameras"]), before + 1)
            self.assertFalse((Path(d) / "settings.json.tmp").exists())

    def test_save_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = ConfigManager(str(Path(d) / "settings.json"))
            cfg.settings_file = Path(d) / "missing_dir" / "settings.json"
            self.assertFalse(cfg.save())
            self.assertIn("missing_dir", cfg.last_save_error)


if __name__ == "__main__":
    unittest.main()
