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
        # Qaror chegarasi: model endi pastroq ishonch bilan chaqiriladi (kuchsiz
        # detectionlar faqat track'ni davom ettiradi), shuning uchun yangi odam va
        # shlem/bosh qutilari uchun asosiy `confidence` shu yerda qo'llanadi.
        self.decision_conf = float(cfg.get("confidence", 0.35) or 0.0)
        self.tracker = IoUTracker(
            iou_thresh=float(cfg.get("tracker_iou_threshold", preset_defaults["iou"])),
            center_thresh=float(cfg.get("tracker_center_threshold", preset_defaults["center"])),
            max_age=int(cfg.get("tracker_max_age", preset_defaults["age"])),
            min_hits=int(cfg.get("tracker_min_hits", preset_defaults["hits"])),
            high_thresh=self.decision_conf,
            coast_s=float(cfg.get("tracker_coast_s", 0.6)),
            # Yozib olingan videoda o'lchangan: 3 → 10 track davomiyligini 7.7 → 11.6 s,
            # uzilishlarni 81 → 67 ga yaxshiladi (ID soni ham kamaydi)
            low_max_age=int(cfg.get("tracker_low_max_age", 10)),
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

    def process(self, detections: list[dict], ts: float | None = None) -> list[dict]:
        """`ts` — kadr vaqti (sekund). Berilsa tracker vaqtga asoslangan ishlaydi va
        detection tushib qolgan tasdiqlangan odamlar qisqa vaqt `coasting=True`
        bilan qaytadi (ko'rsatish uchun; qaror hisoblagichlariga qo'shilmaydi)."""
        persons = [d for d in detections if d.get("class_id") == self.person_class_id]

        def conf(d):
            return float(d.get("confidence", d.get("score", 0.0)) or 0.0)

        heads = [
            ("green" if d.get("class_id") in self.green_class_ids else "red", d["box"], conf(d))
            for d in detections
            if (d.get("class_id") in self.green_class_ids or d.get("class_id") in self.red_class_ids)
            and conf(d) >= self.decision_conf
        ]

        tracked = self.tracker.update(persons, ts=ts, include_coasting=ts is not None)
        live = [p for p in tracked if not p.get("coasting")]
        live_statuses = self.assign_head_statuses([p["box"] for p in live], heads)
        status_by_id = {p["track_id"]: st for p, st in zip(live, live_statuses)}
        statuses = [status_by_id.get(p["track_id"], "yellow") for p in tracked]
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

        for person, status in zip(tracked, statuses):
            track_id = person["track_id"]
            history = self.track_statuses.setdefault(
                track_id,
                deque(maxlen=self.helmet_status_window),
            )
            if status in ("green", "red") and not person.get("coasting"):
                history.append(status)

            green = sum(1 for item in history if item == "green")
            red = sum(1 for item in history if item == "red")
            total = green + red
            # Yashil class ustun (noto'g'ri buzilishdan saqlanish uchun), lekin bitta
            # tasodifiy "green" butun tarixni bekor qilmasin: kamida 15% bo'lsin.
            if total > 0 and (green / total) >= 0.15:
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
    def assign_head_statuses(person_boxes: list, heads: list) -> list[str]:
        """Har bir shlem / shlemsiz-bosh qutisini ko'pi bilan BITTA odamga bog'laydi.

        Oldin har odam qutisi 50 px kengaytirilib, ichiga tushgan istalgan shlem
        hisoblanardi — yonma-yon turgan ishchilarda qo'shnining shlemi shlemsiz
        odamga ham "tegishli" bo'lib, buzilish yozilmay qolardi.

        Bosh qutisining markazi odam qutisining yuqori qismida (gorizontal
        bo'yicha kenglikning 15% hoshiyasi bilan, vertikal bo'yicha tepadan 25%
        yuqorigacha va balandlikning 45% igacha) bo'lishi kerak. Nomzodlar
        "bosh nuqtasi"ga (yuqori-markaz) yaqinligi bo'yicha ochko'z usulda
        juftlanadi. Qaytaradi: har odam uchun "green" | "red" | "yellow".
        """
        statuses = ["yellow"] * len(person_boxes)
        pairs = []
        for hi, (_kind, hb, conf) in enumerate(heads):
            cx, cy = (hb[0] + hb[2]) / 2.0, (hb[1] + hb[3]) / 2.0
            for pi, pb in enumerate(person_boxes):
                w = max(1.0, pb[2] - pb[0])
                h = max(1.0, pb[3] - pb[1])
                mx = 0.15 * w
                if not (pb[0] - mx <= cx <= pb[2] + mx):
                    continue
                if not (pb[1] - 0.25 * h <= cy <= pb[1] + 0.45 * h):
                    continue
                head_x, head_y = (pb[0] + pb[2]) / 2.0, pb[1] + 0.12 * h
                cost = abs(cx - head_x) / w + abs(cy - head_y) / h - 0.05 * conf
                pairs.append((cost, pi, hi))
        used_p, used_h = set(), set()
        for _cost, pi, hi in sorted(pairs):
            if pi in used_p or hi in used_h:
                continue
            used_p.add(pi)
            used_h.add(hi)
            statuses[pi] = heads[hi][0]
        return statuses

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
