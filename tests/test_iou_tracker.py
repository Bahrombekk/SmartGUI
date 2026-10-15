import unittest

from app.application.services.tracking import IoUTracker


def det(x1, y1, x2, y2, score=0.9):
    return {
        "class_id": 0,
        "box": [float(x1), float(y1), float(x2), float(y2)],
        "bbox_xyxy": [float(x1), float(y1), float(x2), float(y2)],
        "score": score,
        "confidence": score,
    }


class IoUTrackerTests(unittest.TestCase):
    def test_single_person_keeps_id_while_moving(self):
        tracker = IoUTracker(iou_thresh=0.15, center_thresh=1.25, max_age=40, min_hits=2)
        first_id = None
        for step in range(8):
            rows = tracker.update([det(20 + step * 8, 30, 80 + step * 8, 150)])
            self.assertEqual(len(rows), 1)
            first_id = rows[0]["track_id"] if first_id is None else first_id
            self.assertEqual(rows[0]["track_id"], first_id)
        self.assertTrue(rows[0]["track_confirmed"])

    def test_lost_person_reconnects_to_old_id(self):
        tracker = IoUTracker(iou_thresh=0.15, center_thresh=1.45, max_age=25, min_hits=2)
        first = tracker.update([det(100, 80, 160, 210)])[0]["track_id"]
        tracker.update([det(108, 80, 168, 210)])
        for _ in range(12):
            self.assertEqual(tracker.update([]), [])
        rows = tracker.update([det(122, 82, 182, 212)])
        self.assertEqual(rows[0]["track_id"], first)

    def test_two_people_do_not_collapse_to_one_track(self):
        tracker = IoUTracker(iou_thresh=0.12, center_thresh=1.30, max_age=40, min_hits=2)
        previous_ids = None
        for step in range(7):
            rows = tracker.update([
                det(40 + step * 12, 60, 90 + step * 12, 180),
                det(260 - step * 12, 64, 310 - step * 12, 184),
            ])
            ids = {row["track_id"] for row in rows}
            self.assertEqual(len(ids), 2)
            if previous_ids is not None:
                self.assertEqual(ids, previous_ids)
            previous_ids = ids

    def test_low_confidence_does_not_create_excess_ids_for_same_motion(self):
        tracker = IoUTracker(iou_thresh=0.15, center_thresh=1.25, max_age=20, min_hits=3)
        ids = []
        for step in range(6):
            rows = tracker.update([det(50 + step * 5, 50, 110 + step * 5, 180, score=0.25)])
            ids.append(rows[0]["track_id"])
        self.assertEqual(len(set(ids)), 1)

    def test_confirmed_track_survives_faster_motion_after_gap(self):
        tracker = IoUTracker(iou_thresh=0.12, center_thresh=1.45, max_age=60, min_hits=3)
        first = None
        for step in range(4):
            rows = tracker.update([det(40 + step * 10, 60, 100 + step * 10, 190)])
            first = rows[0]["track_id"] if first is None else first
        for _ in range(8):
            tracker.update([])
        rows = tracker.update([det(112, 62, 172, 192)])
        self.assertEqual(rows[0]["track_id"], first)


if __name__ == "__main__":
    unittest.main()
