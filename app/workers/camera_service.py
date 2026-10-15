"""
CameraService — ai_camera_service dan ko'chirildi, SmartGUI ga moslashtirildi.

CV2RTSPReader.snapshot() orqali ishlaydi (CameraReader o'rniga).
DetectorGroup: bir guruh kameralar uchun batch YOLO inference.
CameraService: global singleton, barcha kameralarni boshqaradi.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

from app.shared.paths import resolve_model_path
from app.shared.utils.rate_gate import RateGate

import logging

_log = logging.getLogger(__name__)


BOX_COLORS = [
    (0, 255, 0), (0, 255, 255), (255, 0, 0),
    (255, 0, 255), (0, 128, 255), (255, 255, 0),
]


@dataclass
class DetectionResult:
    camera_id: int
    timestamp: float | None = None
    completed_at: float | None = None
    fps: float = 0.0
    frame_width: int = 0
    frame_height: int = 0
    detections: list[dict] = field(default_factory=list)
    raw_frame: object | None = None  # detection bajarilgan original frame (umumiy — o'zgartirmang)
    seq: int = 0                     # reader kadr raqami


def parse_detections(result, names: dict) -> list[dict]:
    """YOLO result → SmartGUI detection dict list (IoUTracker bilan mos)."""
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []
    xyxy = boxes.xyxy.cpu().numpy().astype(float)
    confs = boxes.conf.cpu().numpy()
    clss = boxes.cls.cpu().numpy().astype(int)
    out = []
    for box, conf, cls in zip(xyxy, confs, clss):
        x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
        if x2 <= x1 + 1.0 or y2 <= y1 + 1.0:
            continue
        cls_name = str(names.get(int(cls), str(cls))).lower()
        out.append({
            "class_id": int(cls),
            "class_name": cls_name,
            "class": cls_name,          # IoUTracker / _classify_person uchun
            "confidence": float(conf),
            "bbox_xyxy": [x1, y1, x2, y2],
            "box": [x1, y1, x2, y2],   # IoUTracker uchun
            "score": float(conf),
            "track_id": -1,
        })
    return out


def draw_detections(frame, detections: list[dict]):
    """Debug uchun — annotated frame chizish."""
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox_xyxy"]]
        color = BOX_COLORS[det["class_id"] % len(BOX_COLORS)]
        label = f'{det["class_name"]} {det["confidence"]:.2f}'
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        y_txt = max(y1 - th - 6, 0)
        cv2.rectangle(frame, (x1, y_txt), (x1 + tw + 4, y_txt + th + 6), color, -1)
        cv2.putText(frame, label, (x1 + 2, y_txt + th + 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    return frame


# ── DetectorGroup ─────────────────────────────────────────────────────────────

class DetectorGroup(threading.Thread):
    """
    Kameralar guruhi uchun batch YOLO inference thread'i.

    readers — CV2RTSPReader nusxalari (har birida .snapshot() va .cam_id bor).
    """

    def __init__(self, group_id: int, readers: list,
                 model_path: str, device: str,
                 imgsz: int, confidence: float, batch_size: int,
                 ai_fps_limit: int = 10, process_every_n: int = 1, half: bool = False,
                 track_conf: float | None = None):
        super().__init__(daemon=True, name=f"DetectorGroup-{group_id}")
        # Model past ishonch bilan chaqiriladi: kuchsiz (qisman to'silgan) odamlar
        # tracker'da faqat MAVJUD track'ni davom ettirish uchun ishlatiladi (ByteTrack
        # usuli). Qaror (shlem/buzilish) uchun `confidence` chegarasi o'zgarmaydi.
        self.predict_conf = min(float(confidence), float(track_conf if track_conf is not None else 0.2))
        # FP16 — faqat sozlamada yoqilsa. RTX 5090'da FP32 tezroq va barqarorroq
        # (9.5 ms vs 20–100 ms, o'lchangan), shuning uchun standart — o'chiq.
        self.half = bool(half) and device != "cpu"
        self.group_id = group_id
        self.readers = readers
        self.device = device
        self.imgsz = imgsz
        self.confidence = confidence
        self.batch_size = batch_size
        self.ai_interval = 1.0 / max(1, int(ai_fps_limit or 10))
        self.process_every_n = max(1, int(process_every_n or 1))

        # Model yuklash
        self._is_engine = model_path.endswith(".engine")
        self.model = YOLO(model_path, task="detect")
        if device != "cpu" and not self._is_engine:
            self.model.to(device)
            try:
                self.model.fuse()
            except Exception as e:
                _log.warning("DetectorGroup-%s model.fuse() bajarilmadi: %s", group_id, e)

        # Cache
        self._results: dict[int, DetectionResult] = {
            r.cam_id: DetectionResult(camera_id=r.cam_id) for r in readers
        }
        self._last_snaps: list = [None] * len(readers)
        self._processed_ts: list = [None] * len(readers)  # takroriy inference oldini olish
        self._last_infer_time: list[float] = [0.0] * len(readers)
        self._seen_counts: list[int] = [0] * len(readers)
        # Token-bucket (kamera boshiga): o'rtacha AI tezligi ai_fps_limit bilan
        # cheklanadi, to'p-to'p kelgan kadrlar esa tashlanmaydi.
        self._gates = [RateGate(1.0 / self.ai_interval, burst=2.0) for _ in readers]
        self._seen_ids: list[int] = [-1] * len(readers)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        # Tartibli rejim: reader kadrlarini vaqt tartibida oladi (tarmoq to'p qilib
        # yetkazganlari ham AI'dan o'tadi — tracker uzilishsiz harakatni ko'radi),
        # natijalar ham navbatga tushadi (worker har birini tartib bilan qayta ishlaydi).
        self._ordered = all(hasattr(r, "pop_frames") and hasattr(r, "subscribe") for r in readers)
        if self._ordered:
            for r in readers:
                r.subscribe("ai", maxlen=12)
        self._result_q: dict[int, deque] = {r.cam_id: deque(maxlen=64) for r in readers}
        self.corrupt_skipped = 0

        self.fps = 0.0
        self._count = 0
        self._fps_time = time.time()

    def _warmup(self):
        """
        CUDA kernel kompilatsiyasini oldindan bajaradi.
        Birinchi real frameda qotib qolishni oldini oladi.
        """
        try:
            import numpy as np
            dummy = np.zeros((360, 640, 3), dtype=np.uint8)
            kwargs: dict = {
                "conf": self.confidence, "imgsz": self.imgsz,
                "verbose": False, "max_det": 1,
            }
            if not self._is_engine:
                kwargs["device"] = self.device
                kwargs["half"] = self.half
            self.model.predict([dummy], **kwargs)
            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            _log.info("DetectorGroup-%s warmup tayyor (%s)", self.group_id, self.device)
        except Exception as exc:
            _log.warning("DetectorGroup-%s warmup xato: %s", self.group_id, exc)

    def run(self):
        # CUDA warmup — birinchi real frameni kutmasdan oldin bajar
        self._warmup()

        while not self._stop_event.is_set():
            now = time.perf_counter()

            ready, skipped = (self._collect_ordered(now) if self._ordered
                              else self._collect_latest(now))
            if not ready:
                if not skipped:
                    time.sleep(0.004)  # yangi frame kutish
                continue

            processed = 0
            for start in range(0, len(ready), self.batch_size):
                chunk = ready[start:start + self.batch_size]
                frames = [snap.frame for _, snap in chunk]

                kwargs: dict = {
                    "conf": self.predict_conf,
                    "imgsz": self.imgsz,
                    "verbose": False,
                    "max_det": 100,
                    "save": False,
                    "save_txt": False,
                }
                if not self._is_engine:
                    kwargs["device"] = self.device
                    kwargs["half"] = self.half

                try:
                    predictions = self.model.predict(frames, **kwargs)
                except Exception as exc:
                    _log.error("DetectorGroup-%s inference xato: %s", self.group_id, exc)
                    time.sleep(1)
                    continue

                with self._lock:
                    for (idx, snap), frame, pred in zip(chunk, frames, predictions):
                        reader = self.readers[idx]
                        dets = parse_detections(pred, self.model.names)
                        h, w = frame.shape[:2]
                        res = DetectionResult(
                            camera_id=reader.cam_id,
                            timestamp=snap.timestamp,
                            completed_at=time.perf_counter(),
                            fps=getattr(snap, "fps", 0.0) or getattr(reader, "fps", 0.0),
                            frame_width=w,
                            frame_height=h,
                            detections=dets,
                            raw_frame=frame,
                            seq=int(getattr(snap, "seq", 0) or 0),
                        )
                        self._results[reader.cam_id] = res
                        self._result_q[reader.cam_id].append(res)
                        processed += 1

            now = time.time()
            self._count += processed
            elapsed = now - self._fps_time
            if elapsed >= 1.0:
                self.fps = self._count / elapsed
                self._count = 0
                self._fps_time = now

    def _collect_ordered(self, now: float) -> tuple[list, bool]:
        """Har reader'ning tartibli navbatidan kadrlar (PTS vaqti bilan).
        Buzilgan kadrlar AI'ga berilmaydi; limit kamera vaqti bo'yicha."""
        ready, skipped = [], False
        for i, reader in enumerate(self.readers):
            for pk in reader.pop_frames("ai"):
                if pk.corrupt:
                    self.corrupt_skipped += 1
                    skipped = True
                    continue
                self._seen_counts[i] += 1
                if self._seen_counts[i] % self.process_every_n != 0:
                    skipped = True
                    continue
                if not self._gates[i].try_take(pk.ts):
                    skipped = True
                    continue
                pk.fps = getattr(reader, "fps", 0.0)
                pk.timestamp = pk.ts
                self._last_infer_time[i] = time.time()
                ready.append((i, pk))
        return ready, skipped

    def _collect_latest(self, now: float) -> tuple[list, bool]:
        """Eski usul (pop_frames'siz reader): faqat eng so'nggi kadr."""
        for i, reader in enumerate(self.readers):
            fid = getattr(reader, "frame_count", None)
            if fid is not None and fid == self._seen_ids[i]:
                continue
            if not self._gates[i].ready(now):
                continue
            snap = reader.snapshot()
            if snap.frame is not None and not getattr(snap, "corrupt", False):
                self._last_snaps[i] = snap
                if fid is not None:
                    self._seen_ids[i] = fid
        ready, skipped = [], False
        for i, snap in enumerate(self._last_snaps):
            if snap is None or snap.timestamp == self._processed_ts[i]:
                continue
            if (self._seen_counts[i] + 1) % self.process_every_n != 0:
                self._seen_counts[i] += 1
                self._processed_ts[i] = snap.timestamp
                skipped = True
                continue
            if not self._gates[i].try_take(now):
                continue
            self._seen_counts[i] += 1
            self._processed_ts[i] = snap.timestamp
            self._last_infer_time[i] = time.time()
            ready.append((i, snap))
        return ready, skipped

    def get_result(self, cam_id: int) -> DetectionResult | None:
        with self._lock:
            return self._results.get(cam_id)

    def pop_results(self, cam_id: int) -> list[DetectionResult]:
        """Oxirgi chaqiruvdan beri chiqqan natijalar — vaqt tartibida."""
        with self._lock:
            q = self._result_q.get(cam_id)
            if not q:
                return []
            out = list(q)
            q.clear()
            return out

    def stop(self):
        self._stop_event.set()


# ── CameraService ─────────────────────────────────────────────────────────────

class CameraService:
    """
    Ko'p kamerali detection service.

    add_camera() / remove_camera() chaqirilganda DetectorGroup'larni qayta
    tashkil etadi (har cameras_per_model ta kameraga 1 ta YOLO model).
    """

    def __init__(self, model_path: str, imgsz: int = 640,
                 confidence: float = 0.35, device: str = "auto",
                 cameras_per_model: int = 3, batch_size: int = 3,
                 ai_fps_limit: int = 10, process_every_n: int = 1, half: bool = False):
        self.model_path = model_path
        self.half = bool(half)
        self.imgsz = imgsz
        self.confidence = confidence
        self.cameras_per_model = cameras_per_model
        self.batch_size = batch_size
        self.ai_fps_limit = ai_fps_limit
        self.process_every_n = process_every_n
        self.device = self._resolve_device(device)

        if self.device != "cpu":
            # cudnn.benchmark YOQILMAYDI: RTX 50xx (sm_120) da u model yuklashni
            # 0.5 s → 17 s, warmup'ni 0.1 s → 30–90 s ga cho'zadi (har restartda
            # AI 1–2 daqiqa ishlamaydi), inference tezligi esa o'zgarmaydi (o'lchangan).
            torch.backends.cudnn.benchmark = False
            try:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
            except Exception:
                pass

        self._readers: dict[int, object] = {}   # cam_id → CV2RTSPReader
        self._groups: list[DetectorGroup] = []
        self._lock = threading.Lock()

        # Debounce: bir nechta kamera bir vaqtda qo'shilganda faqat 1 ta restart
        self._timer_lock = threading.Lock()
        self._restart_timer: threading.Timer | None = None
        # Restart'lar ketma-ket bajariladi: ikkita Timer bir vaqtda model yuklasa,
        # biri yaratgan guruhlar hech kim to'xtatmaydigan "yetim" bo'lib qolardi.
        self._restart_lock = threading.Lock()
        self._stopped = False
        # Kutish: so'ralgan restart (seq) bajarilganini worker bilishi uchun
        self._cond = threading.Condition()
        self._scheduled_seq = 0
        self._done_seq = 0
        self.last_error: str | None = None

    @staticmethod
    def _resolve_device(cfg: str) -> str:
        if cfg != "auto":
            return cfg
        return "cuda" if torch.cuda.is_available() else "cpu"

    # ── Kamera boshqaruvi ──────────────────────────────────────────────────

    def add_camera(self, cam_id: int, reader) -> int:
        """Reader'ni qo'shadi (shu cam_id'dagi eskisini almashtiradi).
        Qaytaradi: kutish uchun restart raqami (wait_ready ga beriladi), 0 — servis to'xtagan."""
        with self._lock:
            if self._stopped:
                return 0
            if self._readers.get(cam_id) is reader:
                with self._cond:
                    return self._scheduled_seq
            # Kamera restartida eski worker hali to'xtamagan bo'lishi mumkin —
            # yangi reader ustun turadi (aks holda AI jimgina eski reader'da qolardi).
            self._readers[cam_id] = reader
        return self._schedule_restart()

    def remove_camera(self, cam_id: int, reader=None) -> bool:
        """`reader` berilsa, faqat aynan shu reader ro'yxatda bo'lsa olib tashlaydi:
        kechikib to'xtagan eski worker yangi worker'ning reader'ini o'chirmasin."""
        with self._lock:
            cur = self._readers.get(cam_id)
            if cur is None or (reader is not None and cur is not reader):
                return False
            del self._readers[cam_id]
        self._schedule_restart()
        return True

    def _schedule_restart(self, delay: float = 0.6) -> int:
        """
        Debounce: 600ms ichida boshqa kamera qo'shilmasa restart qiladi.
        Shu tufayli 5 ta kamera bir vaqtda qo'shilsa — faqat 1 ta model load.
        """
        with self._timer_lock:
            if self._stopped:
                return 0
            if self._restart_timer is not None:
                self._restart_timer.cancel()
            with self._cond:
                self._scheduled_seq += 1
                seq = self._scheduled_seq
            t = threading.Timer(delay, self._restart_groups)
            t.daemon = True
            self._restart_timer = t
            t.start()
            return seq

    def wait_ready(self, seq: int, timeout: float = 180.0) -> str | None:
        """`seq` raqamli restart tugaguncha kutadi. Qaytaradi: xato matni yoki None."""
        with self._cond:
            ok = self._cond.wait_for(lambda: self._done_seq >= seq or self._stopped, timeout)
            if self._stopped:
                return "AI servis to'xtatildi"
            if not ok:
                return "AI model yuklanishi juda uzoq davom etdi"
            return self.last_error

    def _restart_groups(self):
        with self._restart_lock:
            with self._cond:
                seq = self._scheduled_seq
            error = None
            try:
                self._rebuild_groups()
            except Exception as exc:
                error = f"AI model yuklanmadi: {exc}"
                _log.exception("DetectorGroup yaratilmadi")
            with self._cond:
                self.last_error = error
                self._done_seq = max(self._done_seq, seq)
                self._cond.notify_all()

    def _rebuild_groups(self):
        with self._lock:
            if self._stopped:
                return
            readers = list(self._readers.values())

        # Model yuklash (sekin) — lock tashqarisida
        new_groups: list[DetectorGroup] = []
        for i in range(0, len(readers), self.cameras_per_model):
            chunk = readers[i:i + self.cameras_per_model]
            new_groups.append(DetectorGroup(
                group_id=len(new_groups) + 1,
                readers=chunk,
                model_path=self.model_path,
                device=self.device,
                imgsz=self.imgsz,
                confidence=self.confidence,
                batch_size=self.batch_size,
                ai_fps_limit=self.ai_fps_limit,
                process_every_n=self.process_every_n,
                half=self.half,
            ))

        # Almashtirish va ishga tushirish bitta lock ostida: stop() oraliqda
        # kelsa, yangi guruhlar umuman ishga tushmaydi (yetim thread qolmaydi).
        with self._lock:
            if self._stopped:
                return
            old_groups = self._groups
            self._groups = new_groups
            for g in old_groups:
                g.stop()
            for g in new_groups:
                g.start()

        for g in old_groups:
            g.join(timeout=2)

    # ── Natijalar ──────────────────────────────────────────────────────────

    def pop_results(self, cam_id: int) -> list[DetectionResult]:
        with self._lock:
            groups = list(self._groups)
        out: list[DetectionResult] = []
        for group in groups:
            out.extend(group.pop_results(cam_id))
        out.sort(key=lambda r: r.timestamp or 0.0)
        return out

    def latest_result(self, cam_id: int) -> DetectionResult | None:
        with self._lock:
            groups = list(self._groups)
        for group in groups:
            result = group.get_result(cam_id)
            if result is not None:
                return result
        return None

    def metrics(self) -> dict:
        with self._lock:
            groups = list(self._groups)
            cam_count = len(self._readers)
        return {
            "total_cameras": cam_count,
            "yolo_fps": sum(g.fps for g in groups),
            "model_path": self.model_path,
            "device": self.device,
        }

    def stop(self):
        with self._timer_lock:
            if self._restart_timer is not None:
                self._restart_timer.cancel()
                self._restart_timer = None
        with self._lock:
            self._stopped = True
            groups = list(self._groups)
            self._groups = []
            self._readers = {}
        with self._cond:
            self._cond.notify_all()
        for g in groups:
            g.stop()
        for g in groups:
            g.join(timeout=2)


# ── Global singleton (pool_acquire/pool_release o'rniga) ─────────────────────

_svc_lock = threading.Lock()
_svc: CameraService | None = None


def svc_acquire(cfg) -> CameraService | None:
    """
    Config asosida global CameraService singleton oladi yoki yaratadi.
    ai_model_enabled=False bo'lsa None qaytaradi.
    """
    global _svc
    if not bool(cfg.get("ai_model_enabled", False)):
        return None

    with _svc_lock:
        if _svc is not None:
            return _svc

    model_path = cfg.get("model_path", "")
    p = resolve_model_path(model_path)
    if not p.exists():
        _log.error("Model topilmadi: %s", p)
        return None

    use_gpu = bool(cfg.get("use_gpu", True))
    device = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"

    with _svc_lock:
        if _svc is None:
            _svc = CameraService(
                model_path=str(p),
                imgsz=int(cfg.get("yolo_imgsz", 640)),
                confidence=float(cfg.get("confidence", 0.35)),
                device=device,
                cameras_per_model=int(cfg.get("cameras_per_model", 3)),
                batch_size=int(cfg.get("inference_batch_size", 3)),
                ai_fps_limit=int(cfg.get("ai_fps_limit", 10)),
                process_every_n=int(cfg.get("process_every_n", 1)),
                half=bool(cfg.get("half_precision", False)),
            )
        return _svc


def svc_register(cam_id: int, reader, svc: CameraService | None = None) -> str | None:
    """Reader ni servicega qo'shadi va DetectorGroup'lar qayta qurilishini kutadi.
    Qaytaradi: xato matni yoki None (AI tayyor)."""
    if svc is None:
        with _svc_lock:
            svc = _svc
    if svc is None:
        return "AI servis mavjud emas"
    seq = svc.add_camera(cam_id, reader)
    if not seq:
        return "AI servis to'xtatildi"
    return svc.wait_ready(seq)


def svc_unregister(cam_id: int, reader=None, svc: CameraService | None = None) -> None:
    """Worker to'xtaganda kamerani o'zi ro'yxatdan o'tgan servisdan olib tashlaydi
    (restart_all'dan keyin yaratilgan yangi servisga tegmaydi)."""
    if svc is None:
        with _svc_lock:
            svc = _svc
    if svc is not None:
        svc.remove_camera(cam_id, reader)


def svc_destroy() -> None:
    """Barcha grouplarni to'xtatadi (ilova yopilganda)."""
    global _svc
    with _svc_lock:
        svc, _svc = _svc, None
    if svc is not None:
        svc.stop()
