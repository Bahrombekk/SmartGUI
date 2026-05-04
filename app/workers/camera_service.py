"""
CameraService — ai_camera_service dan ko'chirildi, SmartGUI ga moslashtirildi.

CV2RTSPReader.snapshot() orqali ishlaydi (CameraReader o'rniga).
DetectorGroup: bir guruh kameralar uchun batch YOLO inference.
CameraService: global singleton, barcha kameralarni boshqaradi.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO


BOX_COLORS = [
    (0, 255, 0), (0, 255, 255), (255, 0, 0),
    (255, 0, 255), (0, 128, 255), (255, 255, 0),
]


@dataclass
class DetectionResult:
    camera_id: int
    timestamp: float | None = None
    fps: float = 0.0
    frame_width: int = 0
    frame_height: int = 0
    detections: list[dict] = field(default_factory=list)
    raw_frame: object | None = None  # detection bajarilgan original frame


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
                 ai_fps_limit: int = 10, process_every_n: int = 1):
        super().__init__(daemon=True, name=f"DetectorGroup-{group_id}")
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
            except Exception:
                pass

        # Cache
        self._results: dict[int, DetectionResult] = {
            r.cam_id: DetectionResult(camera_id=r.cam_id) for r in readers
        }
        self._last_snaps: list = [None] * len(readers)
        self._processed_ts: list = [None] * len(readers)  # takroriy inference oldini olish
        self._last_infer_time: list[float] = [0.0] * len(readers)
        self._seen_counts: list[int] = [0] * len(readers)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

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
                kwargs["half"] = self.device != "cpu"
            self.model.predict([dummy], **kwargs)
            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            print(f"[DetectorGroup-{self.group_id}] Warmup tayyor ({self.device})")
        except Exception as exc:
            print(f"[DetectorGroup-{self.group_id}] Warmup xato: {exc}")

    def run(self):
        # CUDA warmup — birinchi real frameni kutmasdan oldin bajar
        self._warmup()

        while not self._stop_event.is_set():
            # Har bir readerdan snapshot olish
            for i, reader in enumerate(self.readers):
                snap = reader.snapshot()
                if snap.frame is not None:
                    self._last_snaps[i] = snap

            # Faqat YANGI timestamp li framlarni olish (takroriy inference oldini olish)
            ready = [
                (i, snap) for i, snap in enumerate(self._last_snaps)
                if snap is not None
                and snap.timestamp != self._processed_ts[i]
                and (time.time() - self._last_infer_time[i]) >= self.ai_interval
            ]
            if not ready:
                time.sleep(0.005)  # yangi frame kutish
                continue

            filtered = []
            for idx, snap in ready:
                self._seen_counts[idx] += 1
                self._processed_ts[idx] = snap.timestamp
                if self._seen_counts[idx] % self.process_every_n == 0:
                    self._last_infer_time[idx] = time.time()
                    filtered.append((idx, snap))
            ready = filtered
            if not ready:
                continue

            processed = 0
            for start in range(0, len(ready), self.batch_size):
                chunk = ready[start:start + self.batch_size]
                frames = [snap.frame for _, snap in chunk]

                kwargs: dict = {
                    "conf": self.confidence,
                    "imgsz": self.imgsz,
                    "verbose": False,
                    "max_det": 50,
                }
                if not self._is_engine:
                    kwargs["device"] = self.device
                    kwargs["half"] = self.device != "cpu"

                try:
                    predictions = self.model.predict(frames, **kwargs)
                except Exception as exc:
                    print(f"[DetectorGroup-{self.group_id}] inference xato: {exc}")
                    time.sleep(1)
                    continue

                with self._lock:
                    for (idx, snap), frame, pred in zip(chunk, frames, predictions):
                        reader = self.readers[idx]
                        dets = parse_detections(pred, self.model.names)
                        h, w = frame.shape[:2]
                        self._results[reader.cam_id] = DetectionResult(
                            camera_id=reader.cam_id,
                            timestamp=snap.timestamp,
                            fps=snap.fps,
                            frame_width=w,
                            frame_height=h,
                            detections=dets,
                            raw_frame=frame,  # snap.frame allaqachon copy, qayta nusxa olish shart emas
                        )
                        processed += 1

            now = time.time()
            self._count += processed
            elapsed = now - self._fps_time
            if elapsed >= 1.0:
                self.fps = self._count / elapsed
                self._count = 0
                self._fps_time = now

    def get_result(self, cam_id: int) -> DetectionResult | None:
        with self._lock:
            return self._results.get(cam_id)

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
                 ai_fps_limit: int = 10, process_every_n: int = 1):
        self.model_path = model_path
        self.imgsz = imgsz
        self.confidence = confidence
        self.cameras_per_model = cameras_per_model
        self.batch_size = batch_size
        self.ai_fps_limit = ai_fps_limit
        self.process_every_n = process_every_n
        self.device = self._resolve_device(device)

        if self.device != "cpu":
            torch.backends.cudnn.benchmark = True
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

    @staticmethod
    def _resolve_device(cfg: str) -> str:
        if cfg != "auto":
            return cfg
        return "cuda" if torch.cuda.is_available() else "cpu"

    # ── Kamera boshqaruvi ──────────────────────────────────────────────────

    def add_camera(self, cam_id: int, reader) -> None:
        with self._lock:
            if cam_id in self._readers:
                return
            self._readers[cam_id] = reader
        self._schedule_restart()

    def remove_camera(self, cam_id: int) -> bool:
        with self._lock:
            reader = self._readers.pop(cam_id, None)
        if reader is None:
            return False
        self._schedule_restart()
        return True

    def _schedule_restart(self, delay: float = 0.6):
        """
        Debounce: 600ms ichida boshqa kamera qo'shilmasa restart qiladi.
        Shu tufayli 5 ta kamera bir vaqtda qo'shilsa — faqat 1 ta model load.
        """
        with self._timer_lock:
            if self._restart_timer is not None:
                self._restart_timer.cancel()
            t = threading.Timer(delay, self._restart_groups)
            t.daemon = True
            self._restart_timer = t
            t.start()

    def _restart_groups(self):
        # Yangi grouplar uchun readerlarni lock tashqarisida olish
        with self._lock:
            old_groups = list(self._groups)
            readers = list(self._readers.values())

        # Model yuklash (sekin) — lock tashqarisida
        new_groups: list[DetectorGroup] = []
        for i in range(0, len(readers), self.cameras_per_model):
            chunk = readers[i:i + self.cameras_per_model]
            g = DetectorGroup(
                group_id=len(new_groups) + 1,
                readers=chunk,
                model_path=self.model_path,
                device=self.device,
                imgsz=self.imgsz,
                confidence=self.confidence,
                batch_size=self.batch_size,
                ai_fps_limit=self.ai_fps_limit,
                process_every_n=self.process_every_n,
            )
            new_groups.append(g)

        # Yangi grouplarni registratsiya qil
        with self._lock:
            self._groups = new_groups

        # Eski grouplarni to'xtatish
        for g in old_groups:
            g.stop()
        for g in old_groups:
            g.join(timeout=2)

        # Yangi grouplarni boshlash
        for g in new_groups:
            g.start()

    # ── Natijalar ──────────────────────────────────────────────────────────

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
            groups = list(self._groups)
            self._groups = []
            self._readers = {}
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
    p = Path(model_path)
    if not p.is_absolute():
        p = Path(__file__).parent.parent.parent / p
    if not p.exists():
        print(f"[CameraService] Model topilmadi: {p}")
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
            )
        return _svc


def svc_register(cam_id: int, reader) -> None:
    """Reader ni global servicega qo'shadi va DetectorGroup'larni yangilaydi."""
    global _svc
    with _svc_lock:
        svc = _svc
    if svc is not None:
        svc.add_camera(cam_id, reader)


def svc_unregister(cam_id: int) -> None:
    """Worker to'xtaganda camera ni serviceden olib tashlaydi."""
    global _svc
    with _svc_lock:
        svc = _svc
    if svc is not None:
        svc.remove_camera(cam_id)


def svc_destroy() -> None:
    """Barcha grouplarni to'xtatadi (ilova yopilganda)."""
    global _svc
    with _svc_lock:
        svc, _svc = _svc, None
    if svc is not None:
        svc.stop()
