import unittest

from app.application.services.detection_analysis import PersonDetectionAnalyzer

assign = PersonDetectionAnalyzer.assign_head_statuses


def head(kind, cx, cy, size=40, conf=0.8):
    return (kind, [cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2], conf)


class HeadAssignmentTests(unittest.TestCase):
    def test_neighbour_helmet_is_not_shared(self):
        # Ikki ishchi yonma-yon (oralig'i 20 px): chapdagi shlemli, o'ngdagi shlemsiz
        left, right = [100, 100, 220, 460], [240, 100, 360, 460]
        heads = [head("green", 160, 130), head("red", 300, 130)]
        self.assertEqual(assign([left, right], heads), ["green", "red"])

    def test_one_helmet_goes_to_one_person_only(self):
        # Shlem ikki odam orasida — faqat bittasiga beriladi, ikkinchisi noma'lum qoladi
        a, b = [100, 100, 220, 460], [200, 100, 320, 460]
        st = assign([a, b], [head("green", 210, 130)])
        self.assertEqual(sorted(st), ["green", "yellow"])

    def test_head_must_be_in_upper_part(self):
        # Qo'ldagi shlem (tananing pastki qismi) bosh hisoblanmaydi
        person = [100, 100, 220, 460]
        self.assertEqual(assign([person], [head("green", 160, 380)]), ["yellow"])

    def test_no_heads(self):
        self.assertEqual(assign([[0, 0, 10, 10]], []), ["yellow"])

    def test_single_false_green_does_not_override_red_history(self):
        cfg = {"helmet_status_threshold": 5, "tracker_min_hits": 1}
        an = PersonDetectionAnalyzer(cfg)
        person = {"class_id": 0, "box": [100, 100, 220, 460], "score": 0.9, "confidence": 0.9}

        def red_head():
            return {"class_id": 2, "box": [140, 110, 180, 150], "score": 0.8, "confidence": 0.8}

        def green_head():
            return {"class_id": 1, "box": [140, 110, 180, 150], "score": 0.8, "confidence": 0.8}

        out = None
        for i in range(12):
            dets = [dict(person), green_head() if i == 6 else red_head()]
            out = an.process(dets)
        self.assertTrue(out)
        self.assertIs(out[0]["has_helmet"], False)


if __name__ == "__main__":
    unittest.main()
