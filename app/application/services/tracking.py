"""
inference_engine.py - lightweight tracking utilities.

CameraService does YOLO inference; this module keeps the custom tracker used by
DetectionWorker. It intentionally has no heavy dependencies so it can run for
many cameras without adding ReID/model overhead.
"""
from __future__ import annotations


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
    ):
        self._iou_thresh = float(iou_thresh)
        self._center_thresh = float(center_thresh)
        self._max_age = int(max_age)
        self._min_hits = max(1, int(min_hits))
        self._tracks: dict[int, dict] = {}
        self._next_id = 1

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

    def _predict(self, t: dict) -> list:
        x1, y1, x2, y2 = t["box"]
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

    def _score(self, track: dict, det: dict) -> float:
        det_box = det["box"]
        pred = self._predict(track)
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

    def update(self, detections: list[dict]) -> list[dict]:
        for track in self._tracks.values():
            track["age"] += 1
        self._tracks = {
            tid: t for tid, t in self._tracks.items()
            if int(t.get("age", 0)) <= self._max_age
        }

        if not detections:
            return []

        tids = list(self._tracks.keys())
        pairs: list[tuple[float, int, int]] = []
        for ti, tid in enumerate(tids):
            track = self._tracks[tid]
            for di, det in enumerate(detections):
                box = det.get("box", det.get("bbox_xyxy"))
                if not box or len(box) != 4:
                    continue
                det = {**det, "box": box}
                score = self._score(track, det)
                if score >= self._match_threshold(track):
                    pairs.append((score, ti, di))
        pairs.sort(key=lambda item: item[0], reverse=True)

        matched_t: set[int] = set()
        matched_d: set[int] = set()
        d2t: dict[int, int] = {}
        for _, ti, di in pairs:
            if ti in matched_t or di in matched_d:
                continue
            matched_t.add(ti)
            matched_d.add(di)
            d2t[di] = tids[ti]

        result = []
        for di, det in enumerate(detections):
            box = det.get("box", det.get("bbox_xyxy"))
            if not box or len(box) != 4:
                continue
            det = {**det, "box": list(box), "bbox_xyxy": list(box)}
            tid = d2t.get(di)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
                vx = vy = 0.0
                hits = 1
            else:
                old = self._tracks[tid]["box"]
                cx_old, cy_old = self._center(old)
                cx_new, cy_new = self._center(det["box"])
                alpha = 0.30
                vx = (1 - alpha) * self._tracks[tid].get("vx", 0.0) + alpha * (cx_new - cx_old)
                vy = (1 - alpha) * self._tracks[tid].get("vy", 0.0) + alpha * (cy_new - cy_old)
                hits = int(self._tracks[tid].get("hits", 1)) + 1
                det["box"] = self._smooth_box(old, det["box"])
                det["bbox_xyxy"] = list(det["box"])

            self._tracks[tid] = {
                "box": det["box"],
                "age": 0,
                "vx": vx,
                "vy": vy,
                "hits": hits,
            }
            result.append({
                **det,
                "track_id": tid,
                "vx": vx,
                "vy": vy,
                "track_hits": hits,
                "track_confirmed": hits >= self._min_hits,
            })
        return result

    def reset(self):
        self._tracks.clear()
        self._next_id = 1
