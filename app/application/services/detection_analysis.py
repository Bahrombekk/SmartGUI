"""Model natijalarini odam/shlem holatiga aylantirish logikasi.

Bu modul PyQt yoki kamera oqimini bilmaydi. U faqat detection ro'yxatini olib,
tracker orqali odamlarni barqaror track ID bilan qaytaradi va rolling vote
asosida shlem bor-yo'qligini belgilaydi.
"""
from __future__ import annotations

from collections import deque

from app.application.services.tracking import IoUTracker


class PersonDetectionAnalyzer:
    """Person classini track qiladi va ichki helmet/no-helmet boxlarni baholaydi."""

    def __init__(self, cfg):
        preset = str(cfg.get("tracking_strictness", "balanced")).lower()
        preset_defaults = {
            "stable": {"iou": 0.10, "center": 1.75, "age": 260, "hits": 4},
            "balanced": {"iou": 0.12, "center": 1.45, "age": 180, "hits": 3},
            "fast": {"iou": 0.20, "center": 0.95, "age": 80, "hits": 2},
        }.get(preset, {"iou": 0.12, "center": 1.45, "age": 180, "hits": 3})
        self.tracker = IoUTracker(
            iou_thresh=float(cfg.get("tracker_iou_threshold", preset_defaults["iou"])),
            center_thresh=float(cfg.get("tracker_center_threshold", preset_defaults["center"])),
            max_age=int(cfg.get("tracker_max_age", preset_defaults["age"])),
            min_hits=int(cfg.get("tracker_min_hits", preset_defaults["hits"])),
        )
        self.person_class_id = int(cfg.get("person_class_id", 0))
        self.green_class_ids = set(int(x) for x in cfg.get("helmet_class_ids", [1]))
        self.red_class_ids = set(int(x) for x in cfg.get("no_helmet_class_ids", [2]))
        self.box_pad = int(cfg.get("class0_box_pad", 50))
        self.helmet_status_window = max(3, int(cfg.get("helmet_status_window", 50)))
        self.helmet_status_threshold = max(1, int(cfg.get("helmet_status_threshold", 30)))
        self.helmet_status_keep_age = max(1, int(cfg.get("helmet_status_keep_age", 120)))
        self.track_statuses: dict[int, deque[str]] = {}
        self.track_status_missed: dict[int, int] = {}

    def process(self, detections: list[dict]) -> list[dict]:
        persons = [d for d in detections if d.get("class_id") == self.person_class_id]
        green_boxes = [d["box"] for d in detections if d.get("class_id") in self.green_class_ids]
        red_boxes = [d["box"] for d in detections if d.get("class_id") in self.red_class_ids]

        tracked = self.tracker.update(persons)
        active_ids = {p["track_id"] for p in tracked}
        for track_id in list(self.track_statuses):
            if track_id not in active_ids:
                missed = self.track_status_missed.get(track_id, 0) + 1
                self.track_status_missed[track_id] = missed
                if missed > self.helmet_status_keep_age:
                    self.track_statuses.pop(track_id, None)
                    self.track_status_missed.pop(track_id, None)
            else:
                self.track_status_missed[track_id] = 0

        for person in tracked:
            track_id = person["track_id"]
            padded = self.pad_box(person["box"], self.box_pad)
            status = self.inner_status(padded, green_boxes, red_boxes)
            history = self.track_statuses.setdefault(
                track_id,
                deque(maxlen=self.helmet_status_window),
            )
            if status in ("green", "red"):
                history.append(status)

            green = sum(1 for item in history if item == "green")
            red = sum(1 for item in history if item == "red")
            total = green + red
            # Yashil class ustun: kam miqdor green topilsa ham shlem bor deb qabul qilamiz.
            if total > 0 and (green / total) > 0.05:
                person["has_helmet"] = True
            elif red >= self.helmet_status_threshold and red > green:
                person["has_helmet"] = False
            else:
                person["has_helmet"] = None

        return tracked

    def reset(self) -> None:
        self.tracker.reset()
        self.track_statuses.clear()
        self.track_status_missed.clear()

    @staticmethod
    def pad_box(box: list, pad: int) -> list:
        return [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad]

    def inner_status(self, person_box: list, green_boxes: list, red_boxes: list) -> str:
        for box in green_boxes:
            if self.box_overlaps(person_box, box):
                return "green"
        for box in red_boxes:
            if self.box_overlaps(person_box, box):
                return "red"
        return "yellow"

    @staticmethod
    def box_overlaps(outer: list, inner: list, threshold: float = 0.3) -> bool:
        """inner box ning kamida threshold qismi outer box ichida bo'lsa True."""
        x1 = max(outer[0], inner[0])
        y1 = max(outer[1], inner[1])
        x2 = min(outer[2], inner[2])
        y2 = min(outer[3], inner[3])
        if x2 <= x1 or y2 <= y1:
            return False
        inter = (x2 - x1) * (y2 - y1)
        inner_area = max(1.0, (inner[2] - inner[0]) * (inner[3] - inner[1]))
        return (inter / inner_area) >= threshold
