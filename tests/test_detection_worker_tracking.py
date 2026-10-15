import unittest
from collections import deque

from app.workers.detection_worker import DetectionWorker


class DummyCfg:
    telegram_enabled = False
    telegram_token = ""
    telegram_chat_ids = []
    backend_enabled = False

    def get(self, key, default=None):
        values = {
            "violation_save_queue_size": 8,
            "helmet_status_window": 4,
            "helmet_status_threshold": 3,
            "helmet_status_keep_age": 5,
            "violation_cooldown": 10,
            "tracking_strictness": "balanced",
        }
        return values.get(key, default)


class DetectionWorkerTrackingTests(unittest.TestCase):
    def setUp(self):
        self.worker = DetectionWorker(DummyCfg(), db=None)

    def test_helmet_status_uses_rolling_votes(self):
        history = deque(["red", "red"], maxlen=4)
        self.worker._track_statuses[1] = history
        detections = [
            {"class_id": 0, "box": [10, 10, 80, 140], "score": 0.9},
            {"class_id": 2, "box": [25, 20, 55, 55], "score": 0.9},
        ]
        people = self.worker._process_detections(detections)
        self.assertEqual(len(people), 1)
        self.assertFalse(people[0]["has_helmet"])

    def test_spatial_duplicate_blocks_new_track_near_same_place(self):
        first = {"box": [100, 100, 180, 260]}
        second = {"box": [108, 106, 188, 266]}
        self.worker._remember_spatial_violation(first, "no_helmet")
        self.assertTrue(self.worker._is_spatial_duplicate(second, "no_helmet"))

    def test_spatial_duplicate_allows_far_person(self):
        first = {"box": [100, 100, 180, 260]}
        far = {"box": [420, 100, 500, 260]}
        self.worker._remember_spatial_violation(first, "no_helmet")
        self.assertFalse(self.worker._is_spatial_duplicate(far, "no_helmet"))

    def test_helmet_status_history_survives_short_occlusion(self):
        self.worker._track_statuses[1] = deque(["red", "red", "red"], maxlen=4)
        self.worker._process_detections([])
        self.worker._process_detections([])
        self.assertIn(1, self.worker._track_statuses)


if __name__ == "__main__":
    unittest.main()
