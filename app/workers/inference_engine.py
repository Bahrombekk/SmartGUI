from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np


# ── Engine Pool (har 3 ta kameraga 1 model) ───────────────────────────────────
MAX_CAMS_PER_ENGINE = 3

_pool_lock   = threading.Lock()
_engines:    list["InferenceEngine"] = []
_eng_counts: list[int] = []       # har engine uchun kameralar soni
_cam_to_eng: dict[int, int] = {}  # cam_id → engine indeksi


def pool_acquire(cam_id: int, cfg) -> "InferenceEngine | None":
    """Kamera uchun engine oladi; zarur bo'lsa yangi yaratadi (max 3 kamera/engine)."""
    if not bool(cfg.get("ai_model_enabled", False)):
        return None
    with _pool_lock:
        if cam_id in _cam_to_eng:
            return _engines[_cam_to_eng[cam_id]]
        # Bo'sh slot bor engine topamiz
        for i, cnt in enumerate(_eng_counts):
            if cnt < MAX_CAMS_PER_ENGINE:
                _cam_to_eng[cam_id] = i
                _eng_counts[i] += 1
                print(f"[Pool] cam={cam_id} → engine#{i} ({_eng_counts[i]}/{MAX_CAMS_PER_ENGINE})")
                return _engines[i]
        # Yangi engine kerak
        eng = _build_engine(cfg)
        if eng is None:
            return None
        idx = len(_engines)
        _engines.append(eng)
        _eng_counts.append(1)
        _cam_to_eng[cam_id] = idx
        print(f"[Pool] cam={cam_id} → new engine#{idx}")
        return eng


def pool_release(cam_id: int):
    """Worker to'xtaganda slot bo'shatadi."""
    with _pool_lock:
        idx = _cam_to_eng.pop(cam_id, None)
        if idx is not None and idx < len(_eng_counts):
            _eng_counts[idx] = max(0, _eng_counts[idx] - 1)


def pool_destroy():
    """Barcha enginelarni to'xtatib, poolni tozalaydi."""
    with _pool_lock:
        for eng in _engines:
            try:
                eng.stop()
            except Exception:
                pass
        _engines.clear()
        _eng_counts.clear()
        _cam_to_eng.clear()


def _build_engine(cfg) -> "InferenceEngine | None":
    try:
        import torch
        from pathlib import Path

        use_gpu = bool(cfg.get("use_gpu", True))
        device  = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
        p = Path(cfg.get("model_path", ""))
        if not p.is_absolute():
            p = Path(__file__).parent.parent.parent / p
        if not p.exists():
            print(f"[InferenceEngine] Model topilmadi: {p}")
            return None
        eng = InferenceEngine(
            model_path = str(p),
            device     = device,
            imgsz      = int(cfg.get("yolo_imgsz", 640)),
            conf       = float(cfg.get("confidence", 0.25)),
            half       = bool(cfg.get("half_precision", False)),
        )
        return eng if eng.is_loaded else None
    except Exception as e:
        print(f"[InferenceEngine] Yaratishda xato: {e}")
        return None


# Eski singleton — pool orqali ishlaydi (backward compat)
_legacy_lock: threading.Lock = threading.Lock()
_legacy_cam_id: int = -999_999


# ── IoU Tracker (velocity + centre-dist fallback) ─────────────────────────────

class IoUTracker:
    """
    Greedy IoU tracker + velocity prediction + centre-distance fallback.

    Yaxshilanishlar (eski versiyaga nisbatan):
      - har bir track uchun EMA tezligi (vx, vy) — tez harakatda track yo'qolmaydi
      - predicted box → IoU matching (kamera tebranishida ham ishlaydi)
      - IoU=0 bo'lsa markaz masofasi orqali zaxira matching
      - max_age 80 ga oshirildi — qisqa to'siqlardan keyin qayta topiladi
    """

    def __init__(self, iou_thresh: float = 0.25, max_age: int = 80):
        self._thresh  = iou_thresh
        self._max_age = max_age
        self._tracks: dict[int, dict] = {}
        self._next_id = 1

    # ── ichki yordamchilar ─────────────────────────────────────────────────

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
        """IoU ≥ threshold → IoU qaytaradi. Aks holda normalangan markaz masofasi."""
        iou = self._iou(pred, det_box)
        if iou >= self._thresh:
            return iou
        # markaz masofasi: o'rtacha qutilar diagonaliga nisbatan
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

    # ── ommaviy API ────────────────────────────────────────────────────────

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
                tid   = self._next_id
                self._next_id += 1
                vx = vy = 0.0
            else:
                old   = self._tracks[tid]["box"]
                new   = det["box"]
                alpha = 0.35  # EMA og'irligi: yangi o'lchov
                cx_old, cy_old = self._center(old)
                cx_new, cy_new = self._center(new)
                vx = (1 - alpha) * self._tracks[tid].get("vx", 0.0) + alpha * (cx_new - cx_old)
                vy = (1 - alpha) * self._tracks[tid].get("vy", 0.0) + alpha * (cy_new - cy_old)

            self._tracks[tid] = {"box": det["box"], "age": 0, "vx": vx, "vy": vy}
            result.append({**det, "track_id": tid})
        return result

    def reset(self):
        self._tracks.clear()
        self._next_id = 1


# ── InferenceEngine ────────────────────────────────────────────────────────────

class InferenceEngine:
    """Batch GPU inference engine. Pool orqali yaratiladi."""

    BATCH_INTERVAL_MS = 10  # 15 → 10 ms: kichikroq batch, kamroq kechikish

    def __init__(self, model_path: str, device: str, imgsz: int, conf: float, half: bool):
        self._model_path = model_path
        self._device     = device
        self._imgsz      = imgsz
        self._conf       = conf
        self._half       = half
        self._model      = None
        self._names: dict = {}
        self.is_loaded    = False
        self._last_debug_ts = 0.0

        self._pending:      dict[int, np.ndarray] = {}
        self._pending_lock  = threading.Lock()
        self._cache:        dict[int, tuple[list[dict], np.ndarray]] = {}
        self._cache_lock    = threading.Lock()
        self._urgent_event  = threading.Event()
        self._worker_ready  = threading.Event()

        self._running = False
        self._load_model()
        if self.is_loaded:
            self._start_worker()

    # ── Backward compat singleton (pool wraps this) ────────────────────────

    @classmethod
    def get_instance(cls, cfg) -> "InferenceEngine | None":
        global _legacy_cam_id
        return pool_acquire(_legacy_cam_id, cfg)

    @classmethod
    def destroy(cls):
        pool_destroy()

    # ── Model yuklash ──────────────────────────────────────────────────────

    def _load_model(self):
        try:
            from ultralytics import YOLO

            self._model = YOLO(self._model_path)
            if self._device == "cuda":
                import torch

                self._model.to("cuda")
                torch.backends.cudnn.benchmark = True
                try:
                    torch.set_float32_matmul_precision("high")
                except Exception:
                    pass
                print(f"[InferenceEngine] GPU: {torch.cuda.get_device_name(0)}")
            else:
                print("[InferenceEngine] CPU rejimda ishlaydi")
            self._names    = self._model.names
            self.is_loaded = True
            print("[InferenceEngine] Model yuklandi")
        except Exception as e:
            print(f"[InferenceEngine] Model yuklanmadi: {e}")
            self.is_loaded = False

    # ── Worker thread ──────────────────────────────────────────────────────

    def _start_worker(self):
        self._running = True
        old_stack = threading.stack_size(8 * 1024 * 1024)
        t = threading.Thread(target=self._batch_loop, daemon=True, name="InferenceBatch")
        t.start()
        threading.stack_size(old_stack)
        if not self._worker_ready.wait(timeout=120.0):
            print("[InferenceEngine] Worker warmup vaqti tugadi")

    def _batch_loop(self):
        self._warmup_worker()
        interval = self.BATCH_INTERVAL_MS / 1000.0
        while self._running:
            self._urgent_event.wait(timeout=interval)
            self._urgent_event.clear()

            with self._pending_lock:
                batch = list(self._pending.items())
                self._pending.clear()

            if batch and self._model is not None:
                self._run_batch(batch)

    def _warmup_worker(self):
        try:
            dummy = [np.zeros((720, 1280, 3), dtype=np.uint8)]
            self._model.predict(
                dummy,
                imgsz   = self._imgsz,
                conf    = self._conf,
                device  = 0 if self._device == "cuda" else "cpu",
                half    = self._half and self._device == "cuda",
                verbose = False,
                max_det = 50,
            )
            if self._device == "cuda":
                import torch
                torch.cuda.synchronize()
            print("[InferenceEngine] Worker warmup bajarildi, tayyor")
        except Exception as e:
            self._running  = False
            self.is_loaded = False
            print(f"[InferenceEngine] Worker warmup xato: {e}")
        finally:
            self._worker_ready.set()

    def _run_batch(self, batch: list[tuple[int, np.ndarray]]):
        try:
            cam_ids = [c for c, _ in batch]
            frames  = [f for _, f in batch]
            results = self._model.predict(
                frames,
                imgsz   = self._imgsz,
                conf    = self._conf,
                device  = 0 if self._device == "cuda" else "cpu",
                half    = self._half and self._device == "cuda",
                verbose = False,
                max_det = 50,
            )

            parsed: dict[int, tuple[list[dict], np.ndarray]] = {}
            total = 0
            for cam_id, result, frame in zip(cam_ids, results, frames):
                dets = self._parse(result, frame.shape[:2])
                total += len(dets)
                parsed[cam_id] = (dets, frame)

            with self._cache_lock:
                self._cache.update(parsed)

            now = time.perf_counter()
            if now - self._last_debug_ts > 5.0:
                print(
                    f"[InferenceEngine] batch={len(batch)} det={total} "
                    f"conf={self._conf:.2f} imgsz={self._imgsz} "
                    f"device={self._device} half={self._half}"
                )
                self._last_debug_ts = now
        except Exception as e:
            print(f"[InferenceEngine] Batch xato: {e}")

    def _parse(self, result, frame_shape: tuple[int, int]) -> list[dict]:
        out = []
        if result.boxes is None:
            return out
        orig_h, orig_w = frame_shape
        for box in result.boxes:
            cls_id      = int(box.cls[0].item())
            x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()
            x1 = max(0.0, min(float(x1), float(orig_w)))
            x2 = max(0.0, min(float(x2), float(orig_w)))
            y1 = max(0.0, min(float(y1), float(orig_h)))
            y2 = max(0.0, min(float(y2), float(orig_h)))
            if x2 <= x1 + 1.0 or y2 <= y1 + 1.0:
                continue
            out.append({
                "box":      [x1, y1, x2, y2],
                "score":    float(box.conf[0].item()),
                "class":    self._names.get(cls_id, str(cls_id)).lower(),
                "track_id": -1,
            })
        return out

    # ── Tashqi API ─────────────────────────────────────────────────────────

    def submit(self, cam_id: int, frame: np.ndarray):
        """Eng yangi frameni qo'yadi; eskisi tashlanadi."""
        with self._pending_lock:
            self._pending[cam_id] = frame
        self._urgent_event.set()

    def get_result(self, cam_id: int) -> tuple[list[dict], np.ndarray] | None:
        with self._cache_lock:
            cached = self._cache.pop(cam_id, None)
        if cached is None:
            return None
        dets, frame = cached
        return list(dets), frame

    def stop(self):
        self._running = False
        self._urgent_event.set()
