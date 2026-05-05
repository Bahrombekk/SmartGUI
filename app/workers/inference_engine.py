"""
inference_engine.py — faqat IoUTracker saqlanadi.

Eski InferenceEngine + pool funksiyalari camera_service.py (CameraService /
DetectorGroup) bilan almashtirildi. Bu fayl backward-compat uchun saqlanadi.
"""
from __future__ import annotations


# ── IoU Tracker (velocity + centre-dist fallback) ─────────────────────────────

class IoUTracker:
    """
    Greedy IoU tracker + velocity prediction + centre-distance fallback.

      - Har bir track uchun EMA tezligi (vx, vy) — tez harakatda track yo'qolmaydi
      - Predicted box → IoU matching
      - IoU=0 bo'lsa markaz masofasi orqali zaxira matching
      - max_age=80 — qisqa to'siqlardan keyin qayta topiladi
    """

    def __init__(self, iou_thresh: float = 0.25, max_age: int = 80):
        self._thresh  = iou_thresh
        self._max_age = max_age
        self._tracks: dict[int, dict] = {}
        self._next_id = 1

    def _predict(self, t: dict) -> list:
        x1, y1, x2, y2 = t["box"]
        vx, vy = t.get("vx", 0.0), t.get("vy", 0.0)
        return [x1 + vx, y1 + vy, x2 + vx, y2 + vy]

    @staticmethod
    def _center(b: list) -> tuple[float, float]:
        return (b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5

    @staticmethod
    def _iou(a: list, b: list) -> float:
        ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1])
        ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        ua = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
        ub = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
        return inter / (ua + ub - inter)

    def _score(self, pred: list, det_box: list) -> float:
        iou = self._iou(pred, det_box)
        if iou >= self._thresh:
            return iou
        cx1, cy1 = self._center(pred)
        cx2, cy2 = self._center(det_box)
        dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
        w = (pred[2] - pred[0] + det_box[2] - det_box[0]) * 0.5
        h = (pred[3] - pred[1] + det_box[3] - det_box[1]) * 0.5
        diag = max(1.0, (w ** 2 + h ** 2) ** 0.5)
        nd = dist / diag
        if nd < 1.0:
            return max(0.01, 0.12 * (1.0 - nd))
        return 0.0

    def update(self, detections: list[dict]) -> list[dict]:
        for t in self._tracks.values():
            t["age"] += 1
        self._tracks = {
            tid: t for tid, t in self._tracks.items()
            if t["age"] <= self._max_age
        }

        if not detections:
            return []

        tids = list(self._tracks.keys())

        pairs: list[tuple[float, int, int]] = []
        for ti, tid in enumerate(tids):
            pred = self._predict(self._tracks[tid])
            for di, det in enumerate(detections):
                s = self._score(pred, det["box"])
                if s > 0:
                    pairs.append((s, ti, di))
        pairs.sort(key=lambda x: x[0], reverse=True)

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
            tid = d2t.get(di)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
                vx = vy = 0.0
            else:
                old = self._tracks[tid]["box"]
                new = det["box"]
                alpha = 0.5
                cx_old, cy_old = self._center(old)
                cx_new, cy_new = self._center(new)
                vx = (1 - alpha) * self._tracks[tid].get("vx", 0.0) + alpha * (cx_new - cx_old)
                vy = (1 - alpha) * self._tracks[tid].get("vy", 0.0) + alpha * (cy_new - cy_old)

            self._tracks[tid] = {"box": det["box"], "age": 0, "vx": vx, "vy": vy}
            result.append({**det, "track_id": tid, "vx": vx, "vy": vy})
        return result

    def reset(self):
        self._tracks.clear()
        self._next_id = 1
