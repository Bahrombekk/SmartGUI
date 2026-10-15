"""
inference_engine.py - lightweight tracking utilities.

CameraService does YOLO inference; this module keeps the custom tracker used by
DetectionWorker. It intentionally has no heavy dependencies so it can run for
many cameras without adding ReID/model overhead.
"""
from __future__ import annotations

import threading
import time

try:  # Vengr algoritmi — yaqin turgan odamlarda ID almashinuvini kamaytiradi
    from scipy.optimize import linear_sum_assignment as _lsa
except Exception:  # pragma: no cover — scipy bo'lmasa ochko'z juftlash
    _lsa = None

# Jarayon bo'yicha yagona track ID manbasi. Worker qayta ishga tushganda
# tracker ID lari 1 dan boshlansa, eski buzilish yozuvlari (track_id bo'yicha
# FaceID yangilanishi, rasm nomlari) boshqa odamniki bilan aralashib ketardi.
# Boshlang'ich qiymat vaqtga bog'liq (2026-01-01 dan beri 0.1 s birlikda) —
# ilova qayta ishga tushganda ham avvalgi ID lar takrorlanmaydi.
_GLOBAL_ID_EPOCH = 1_767_225_600  # 2026-01-01 00:00:00 UTC
_global_id_lock = threading.Lock()
_global_next_id: int | None = None


def next_global_track_id() -> int:
    """Jarayon davomida takrorlanmaydigan (monoton o'suvchi) track ID."""
    global _global_next_id
    with _global_id_lock:
        if _global_next_id is None:
            _global_next_id = max(1, int((time.time() - _GLOBAL_ID_EPOCH) * 10))
        tid = _global_next_id
        _global_next_id += 1
        return tid


class IoUTracker:
    """
    Greedy multi-signal tracker with short lost-track recovery.

    Matching score combines:
      - predicted-box IoU
      - normalized center distance
      - box size/aspect compatibility
      - detection confidence

    The tracker still returns every detection, but each result includes
    `track_hits` and `track_confirmed`; callers can delay side effects until a
    track is stable.
    """

    def __init__(
        self,
        iou_thresh: float = 0.15,
        center_thresh: float = 1.25,
        max_age: int = 150,
        min_hits: int = 3,
        high_thresh: float = 0.0,
        coast_s: float = 0.6,
        max_predict_s: float = 1.0,
        low_max_age: int = 3,
    ):
        self._iou_thresh = float(iou_thresh)
        self._center_thresh = float(center_thresh)
        self._max_age = int(max_age)
        self._min_hits = max(1, int(min_hits))
        # ByteTrack: score >= high_thresh — yangi track ochishi mumkin; pastroqlari
        # faqat mavjud (yaqinda ko'ringan) track'ni davom ettiradi. 0 — hammasi "yuqori".
        self._high_thresh = float(high_thresh)
        # Detection tushib qolganda tasdiqlangan track shuncha vaqt bashorat bilan
        # ko'rsatiladi ("coasting") — quti miltillamaydi; qarorlarda ishlatilmaydi.
        self._coast_s = float(coast_s)
        self._max_predict_s = float(max_predict_s)
        # 2-bosqich (kuchsiz detection) faqat shuncha yangilanish ichida ko'ringan track'larga
        self._low_max_age = int(low_max_age)
        self._last_ts: float | None = None
        self._tracks: dict[int, dict] = {}
        self._next_id = 1
        # True bo'lsa ID lar jarayon bo'yicha yagona hisoblagichdan olinadi
        self._global_ids = False

    def enable_global_ids(self, enabled: bool = True) -> None:
        """Yangi track ID larni jarayon bo'yicha yagona (qayta ishlatilmaydigan) qiladi."""
        self._global_ids = bool(enabled)

    def _new_id(self) -> int:
        if self._global_ids:
            return next_global_track_id()
        tid = self._next_id
        self._next_id += 1
        return tid

    def live_track_ids(self) -> set[int]:
        """Hali unutilmagan (ko'rinayotgan yoki qisqa yo'qolgan) track ID lari."""
        return set(self._tracks.keys())

    @staticmethod
    def _center(b: list) -> tuple[float, float]:
        return (b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5

    @staticmethod
    def _size(b: list) -> tuple[float, float]:
        return max(1.0, b[2] - b[0]), max(1.0, b[3] - b[1])

    @staticmethod
    def _iou(a: list, b: list) -> float:
        ix1 = max(a[0], b[0])
        iy1 = max(a[1], b[1])
        ix2 = min(a[2], b[2])
        iy2 = min(a[3], b[3])
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        ua = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
        ub = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
        return inter / (ua + ub - inter)

    def _predict(self, t: dict, ts: float | None = None) -> list:
        x1, y1, x2, y2 = t["box"]
        if ts is not None and t.get("ts") is not None:
            # Vaqt rejimi: tezlik px/s, oraliq — oxirgi ko'ringan paytdan beri
            dt = min(self._max_predict_s, max(0.0, ts - t["ts"]))
            vx, vy = t.get("vxs", 0.0) * dt, t.get("vys", 0.0) * dt
            return [x1 + vx, y1 + vy, x2 + vx, y2 + vy]
        age = max(1, int(t.get("age", 0)) + 1)
        vx, vy = t.get("vx", 0.0), t.get("vy", 0.0)
        # Do not let old velocity fling a lost track too far.
        scale = min(3.0, age)
        return [x1 + vx * scale, y1 + vy * scale, x2 + vx * scale, y2 + vy * scale]

    def _distance_score(self, pred: list, det_box: list) -> tuple[float, float]:
        cx1, cy1 = self._center(pred)
        cx2, cy2 = self._center(det_box)
        dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
        pw, ph = self._size(pred)
        dw, dh = self._size(det_box)
        diag = max(1.0, (((pw + dw) * 0.5) ** 2 + ((ph + dh) * 0.5) ** 2) ** 0.5)
        nd = dist / diag
        if nd > self._center_thresh:
            return 0.0, nd
        return max(0.0, 1.0 - (nd / self._center_thresh)), nd

    def _shape_score(self, pred: list, det_box: list) -> float:
        pw, ph = self._size(pred)
        dw, dh = self._size(det_box)
        area_ratio = min(pw * ph, dw * dh) / max(pw * ph, dw * dh)
        aspect_a = pw / ph
        aspect_b = dw / dh
        aspect_ratio = min(aspect_a, aspect_b) / max(aspect_a, aspect_b)
        return max(0.0, min(1.0, 0.65 * area_ratio + 0.35 * aspect_ratio))

    def _score(self, track: dict, det: dict, ts: float | None = None) -> float:
        det_box = det["box"]
        pred = self._predict(track, ts)
        iou = self._iou(pred, det_box)
        dist_score, _ = self._distance_score(pred, det_box)
        if iou < self._iou_thresh and dist_score <= 0.0:
            return 0.0

        shape = self._shape_score(pred, det_box)
        conf = max(0.0, min(1.0, float(det.get("score", det.get("confidence", 0.5)) or 0.0)))
        age = int(track.get("age", 0))
        age_penalty = max(0.70, 1.0 - min(age, self._max_age) / max(1, self._max_age) * 0.30)
        hits = int(track.get("hits", 1))
        confirmed_bonus = 0.08 if hits >= self._min_hits else 0.0
        score = (0.48 * iou) + (0.34 * dist_score) + (0.13 * shape) + (0.05 * conf)
        return min(1.0, score * age_penalty + confirmed_bonus)

    def _match_threshold(self, track: dict) -> float:
        hits = int(track.get("hits", 1))
        age = int(track.get("age", 0))
        if hits >= self._min_hits:
            return 0.12 if age <= 12 else 0.10
        return 0.20

    @staticmethod
    def _smooth_box(old: list, new: list, alpha: float = 0.88) -> list:
        return [
            old[i] * (1.0 - alpha) + new[i] * alpha
            for i in range(4)
        ]

    def _assign(self, tids: list[int], dets: list[tuple[int, dict]], ts, min_score_fn) -> list[tuple[int, int]]:
        """(track_index, det_index) juftlari — Vengr algoritmi (bo'lmasa ochko'z)."""
        if not tids or not dets:
            return []
        scores = [[0.0] * len(dets) for _ in tids]
        for ti, tid in enumerate(tids):
            track = self._tracks[tid]
            for dj, (_, det) in enumerate(dets):
                sc = self._score(track, det, ts)
                if sc >= min_score_fn(track):
                    scores[ti][dj] = sc
        pairs: list[tuple[int, int]] = []
        if _lsa is not None:
            import numpy as _np
            cost = 1.0 - _np.asarray(scores, dtype=float)
            rows, cols = _lsa(cost)
            for ti, dj in zip(rows, cols):
                if scores[ti][dj] > 0.0:
                    pairs.append((int(ti), int(dj)))
            return pairs
        flat = sorted(((scores[ti][dj], ti, dj) for ti in range(len(tids))
                       for dj in range(len(dets)) if scores[ti][dj] > 0.0), reverse=True)
        used_t, used_d = set(), set()
        for _, ti, dj in flat:
            if ti in used_t or dj in used_d:
                continue
            used_t.add(ti)
            used_d.add(dj)
            pairs.append((ti, dj))
        return pairs

    def update(self, detections: list[dict], ts: float | None = None,
               include_coasting: bool = False) -> list[dict]:
        """`ts` (sekund, kadr vaqti) berilsa tezlik px/s da hisoblanadi va bashorat
        haqiqiy oraliq bo'yicha qilinadi (notekis kelgan kadrlarda to'g'ri ishlaydi)."""
        for track in self._tracks.values():
            track["age"] += 1
        self._tracks = {
            tid: t for tid, t in self._tracks.items()
            if int(t.get("age", 0)) <= self._max_age
        }
        if ts is not None:
            self._last_ts = ts

        valid: list[tuple[int, dict]] = []
        for di, det in enumerate(detections or []):
            box = det.get("box", det.get("bbox_xyxy"))
            if not box or len(box) != 4:
                continue
            valid.append((di, {**det, "box": [float(v) for v in box]}))

        def conf(d: dict) -> float:
            return float(d.get("score", d.get("confidence", 0.5)) or 0.0)

        high = [(di, d) for di, d in valid if conf(d) >= self._high_thresh]
        low = [(di, d) for di, d in valid if conf(d) < self._high_thresh]

        # 1-bosqich: yuqori ishonchli detectionlar — barcha track'lar bilan
        tids = list(self._tracks.keys())
        d2t: dict[int, int] = {}
        for ti, dj in self._assign(tids, high, ts, self._match_threshold):
            d2t[high[dj][0]] = tids[ti]
        # 2-bosqich: past ishonchlilar — faqat qolgan, yaqinda ko'ringan track'lar bilan
        # (qisman to'silgan odam track'ini uzmaslik uchun; yangi track ochmaydi)
        if low:
            used = set(d2t.values())
            rest = [tid for tid in tids if tid not in used and int(self._tracks[tid]["age"]) <= self._low_max_age]
            for ti, dj in self._assign(rest, low, ts, lambda _t: 0.30):
                d2t[low[dj][0]] = rest[ti]

        result = []
        for di, det in valid:
            tid = d2t.get(di)
            if tid is None and conf(det) < self._high_thresh:
                continue   # kuchsiz detection yangi odam hisoblanmaydi
            det = {**det, "bbox_xyxy": list(det["box"])}
            raw_center = self._center(det["box"])
            if tid is None:
                tid = self._new_id()
                vx = vy = vxs = vys = 0.0
                hits = 1
            else:
                tr = self._tracks[tid]
                old = tr["box"]
                cx_old, cy_old = tr.get("raw_center") or self._center(old)
                cx_new, cy_new = raw_center
                gap = max(1, int(tr.get("age", 1)))   # necha yangilanishdan keyin ko'rindi
                alpha = 0.30
                # Bir yangilanishdagi siljish: yo'qolgan oraliqqa bo'linadi (aks holda
                # bir necha kadrlik siljish "bir qadam" bo'lib, quti uchib ketardi)
                vx = (1 - alpha) * tr.get("vx", 0.0) + alpha * (cx_new - cx_old) / gap
                vy = (1 - alpha) * tr.get("vy", 0.0) + alpha * (cy_new - cy_old) / gap
                vxs, vys = tr.get("vxs", 0.0), tr.get("vys", 0.0)
                if ts is not None and tr.get("ts") is not None and ts - tr["ts"] > 1e-3:
                    dt = ts - tr["ts"]
                    a = 0.4
                    vxs = (1 - a) * vxs + a * (cx_new - cx_old) / dt
                    vys = (1 - a) * vys + a * (cy_new - cy_old) / dt
                hits = int(tr.get("hits", 1)) + 1
                det["box"] = self._smooth_box(self._predict(tr, ts) if ts is not None else old, det["box"])
                det["bbox_xyxy"] = list(det["box"])

            self._tracks[tid] = {
                "box": det["box"],
                "raw_center": raw_center,
                "age": 0,
                "vx": vx,
                "vy": vy,
                "vxs": vxs,
                "vys": vys,
                "ts": ts,
                "hits": hits,
                "last": det,
            }
            result.append({
                **det,
                "track_id": tid,
                "vx": vx,
                "vy": vy,
                "vxs": vxs,
                "vys": vys,
                "track_hits": hits,
                "track_confirmed": hits >= self._min_hits,
                "coasting": False,
            })

        if include_coasting and ts is not None:
            seen = {r["track_id"] for r in result}
            for tid, tr in self._tracks.items():
                if tid in seen or tr.get("ts") is None or int(tr.get("hits", 0)) < self._min_hits:
                    continue
                if ts - tr["ts"] > self._coast_s:
                    continue
                box = self._predict(tr, ts)
                base = dict(tr.get("last") or {})
                base.update({
                    "box": box, "bbox_xyxy": list(box), "track_id": tid,
                    "vx": tr.get("vx", 0.0), "vy": tr.get("vy", 0.0),
                    "vxs": tr.get("vxs", 0.0), "vys": tr.get("vys", 0.0),
                    "track_hits": int(tr.get("hits", 0)), "track_confirmed": True,
                    "coasting": True,
                })
                result.append(base)
        return result

    def reset(self):
        self._tracks.clear()
        # Global rejimda bu hisoblagich ishlatilmaydi — ID lar qayta takrorlanmaydi
        self._next_id = 1
