"""
CV2RTSPReader — RailSafeGUI OptimizedCamera yondashuvi asosida.

Asosiy yaxshilanishlar:
  1. stimeout;5000000 — FFmpeg socket-level timeout (5s)
  2. Thread-based open() — VideoCapture bloklanmaydi, 12s timeout
  3. 10 frame validation — buzilgan birinchi frameni o'tkazib yuborish
  4. Lock-free double buffer — get_frame() hech qachon bloklanmaydi
  5. CAP_PROP_BUFFERSIZE=1 — minimal latency
  6. Eksponentsial reconnect backoff
"""

import os
import time
import threading
import numpy as np
import cv2

import logging

_log = logging.getLogger(__name__)

os.environ["OPENCV_LOG_LEVEL"]       = "ERROR"
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "quiet"

# GPU (NVDEC) bilan dekodlash — CPU yukini sezilarli kamaytiradi
_RTSP_OPTIONS_GPU = (
    "rtsp_transport;tcp|"
    "stimeout;5000000|"
    "fflags;nobuffer|"
    "flags;low_delay|"
    "analyzeduration;1000000|"
    "probesize;500000|"
    "hwaccel;cuda|"
    "hwaccel_device;0"
)

# CPU fallback
_RTSP_OPTIONS = (
    "rtsp_transport;tcp|"
    "stimeout;5000000|"      # socket timeout: 5s (RailSafeGUI dan)
    "fflags;nobuffer|"
    "flags;low_delay|"
    "analyzeduration;1000000|"
    "probesize;500000"
)

def _cuda_ffmpeg_available() -> bool:
    """NVDEC (CUDA hwaccel) mavjudligini tekshiradi."""
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False

_USE_GPU_DECODE = _cuda_ffmpeg_available()


class _Snap:
    """snapshot() qaytaruvchi yengil obyekt — bir marta aniqlanadi."""
    __slots__ = ("frame", "timestamp", "fps", "status")


# ── Lock-free double buffer ───────────────────────────────────────────────────

class _FrameSlot:
    """Lock-free double buffer — get() hech qachon bloklanmaydi."""

    __slots__ = ("_bufs", "_idx", "_lock", "total", "_ts",
                 "_fps", "_fps_count", "_fps_ts")

    def __init__(self):
        self._bufs     = [None, None]
        self._idx      = 0
        self._lock     = threading.Lock()
        self.total     = 0
        self._ts       = 0.0
        self._fps      = 0.0
        self._fps_count = 0
        self._fps_ts   = time.perf_counter()

    def put(self, frame: np.ndarray):
        now = time.perf_counter()
        with self._lock:
            self._idx ^= 1
            self._bufs[self._idx] = frame
            self.total += 1
            self._ts = now
            self._fps_count += 1
            elapsed = now - self._fps_ts
            if elapsed >= 1.0:
                self._fps = self._fps_count / elapsed
                self._fps_count = 0
                self._fps_ts = now

    def get(self) -> np.ndarray | None:
        with self._lock:
            f = self._bufs[self._idx]
            return f.copy() if f is not None else None

    @property
    def fps(self) -> float:
        with self._lock:
            return self._fps

    @property
    def age_ms(self) -> float:
        return (time.perf_counter() - self._ts) * 1000 if self._ts else 9999.0


# ── CV2RTSPReader ─────────────────────────────────────────────────────────────

class CV2RTSPReader(threading.Thread):
    """
    RTSP/RTMP stream o'quvchi.

    Interfeys (detection_worker.py bilan mos):
        get_frame() -> (bool, ndarray|None)
        is_connected  -> bool
        stop()
    """

    FRAME_TIMEOUT  = 12.0   # Shu vaqt ichida frame kelmasa reconnect
    OPEN_TIMEOUT   = 12.0   # VideoCapture ochish uchun maksimal vaqt
    FIRST_FRAME_N  = 10     # Birinchi valid frameni topish uchun urinishlar

    # Eksponentsial backoff: 2→4→8→16→32→60s (keyin 60s da qoladi)
    _BACKOFF = [2, 4, 8, 16, 32, 60]

    def __init__(self, rtsp_url: str,
                 reconnect_delay: int = 3,
                 max_reconnects: int  = 10,
                 target_fps: int      = 12,
                 on_reconnect_attempt=None,
                 on_max_retries=None):
        super().__init__(daemon=True, name="RTSPReader")
        self.rtsp_url        = rtsp_url
        self.reconnect_delay = reconnect_delay
        self.max_reconnects  = max_reconnects
        self._target_fps     = max(1, target_fps)
        self._on_reconnect_attempt = on_reconnect_attempt  # (attempt: int, wait_sec: float) -> None
        self._on_max_retries       = on_max_retries        # () -> None

        self._slot       = _FrameSlot()
        self._running    = True
        self._connected  = False
        self._fail_count = 0

        # CameraService (DetectorGroup) tomonidan set qilinadi
        self.cam_id: int = 0

    @staticmethod
    def _release_cap_async(cap: cv2.VideoCapture | None) -> None:
        """
        Kamera uzilganda FFmpeg release/grab ichida osilib qolishi mumkin.
        Release alohida daemon threadda bajarilsa worker lifecycle qotmaydi.
        """
        if cap is None:
            return

        def _release():
            try:
                cap.release()
            except Exception:
                pass

        threading.Thread(target=_release, daemon=True, name="RTSPRelease").start()

    # ── VideoCapture ochish ───────────────────────────────────────────────

    def _try_open_cap(self, options: str = _RTSP_OPTIONS,
                       name: str = "RTSPOpen") -> cv2.VideoCapture | None:
        """
        VideoCapture ni thread ichida ochadi.
        RailSafeGUI yondashuvi: thread + join(timeout) — bloklanmaydi.
        """
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = options

        result = [None]

        def _worker():
            try:
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    self._release_cap_async(cap)
                    return

                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FPS, 25)

                for _ in range(self.FIRST_FRAME_N):
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        self._slot.put(frame)
                        result[0] = cap
                        return

                self._release_cap_async(cap)
            except Exception:
                pass

        t = threading.Thread(target=_worker, daemon=True, name=name)
        t.start()
        t.join(timeout=self.OPEN_TIMEOUT)

        return result[0]

    def _open(self) -> cv2.VideoCapture | None:
        """
        To'rt usul bilan urinib ko'rish:
          0. GPU NVDEC dekodlash (agar CUDA mavjud bo'lsa)
          1. TCP + stimeout (asosiy, CPU)
          2. UDP fallback
          3. CAP_ANY (oxirgi chora)
        """
        # 0-urinish: GPU NVDEC (CPU yukini drastik kamaytiradi)
        if _USE_GPU_DECODE:
            cap = self._try_open_cap(_RTSP_OPTIONS_GPU, "RTSPOpenGPU")
            if cap is not None:
                _log.info("GPU (NVDEC) dekodlash faollashdi")
                return cap
            _log.warning("GPU dekodlash ishlamadi, CPU ga o'tildi")

        # 1-urinish: TCP (asosiy, CPU)
        cap = self._try_open_cap()
        if cap is not None:
            return cap

        # 2-urinish: UDP
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;udp|stimeout;5000000|fflags;nobuffer|"
            "analyzeduration;1000000|probesize;500000"
        )
        result = [None]

        def _worker_udp():
            try:
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    self._release_cap_async(cap)
                    return
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                for _ in range(self.FIRST_FRAME_N):
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        self._slot.put(frame)
                        result[0] = cap
                        return
                self._release_cap_async(cap)
            except Exception:
                pass

        t = threading.Thread(target=_worker_udp, daemon=True, name="RTSPOpenUDP")
        t.start()
        t.join(timeout=self.OPEN_TIMEOUT)
        if result[0] is not None:
            return result[0]

        # 3-urinish: CAP_ANY
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|stimeout;8000000|fflags;nobuffer"
        )
        result2 = [None]

        def _worker_any():
            try:
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_ANY)
                if not cap.isOpened():
                    self._release_cap_async(cap)
                    return
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                for _ in range(self.FIRST_FRAME_N):
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        self._slot.put(frame)
                        result2[0] = cap
                        return
                self._release_cap_async(cap)
            except Exception:
                pass

        t = threading.Thread(target=_worker_any, daemon=True, name="RTSPOpenAny")
        t.start()
        t.join(timeout=self.OPEN_TIMEOUT)
        return result2[0]

    # ── Asosiy read loop ──────────────────────────────────────────────────

    def run(self):
        while self._running:
            cap = self._open()

            if cap is None or not cap.isOpened():
                self._connected = False
                self._fail_count += 1
                if 0 < self.max_reconnects < self._fail_count:
                    if callable(self._on_max_retries):
                        self._on_max_retries()
                    self._running = False
                    break
                wait = float(self._BACKOFF[min(self._fail_count - 1, len(self._BACKOFF) - 1)])
                if callable(self._on_reconnect_attempt):
                    self._on_reconnect_attempt(self._fail_count, wait)
                self._interruptible_sleep(wait)
                continue

            self._connected  = True
            self._fail_count = 0
            last_frame_t = time.time()
            stop_evt     = threading.Event()

            def _read_loop():
                nonlocal last_frame_t
                _interval = 1.0 / self._target_fps
                _last_retrieve = 0.0
                while not stop_evt.is_set():
                    try:
                        ok = cap.grab()
                    except Exception:
                        break
                    if not ok:
                        break

                    _now = time.perf_counter()
                    _elapsed = _now - _last_retrieve
                    if _elapsed < _interval:
                        _remaining = _interval - _elapsed
                        if _remaining > 0.010:
                            time.sleep(max(0.005, _remaining - 0.005))
                        else:
                            time.sleep(0.002)
                        continue
                    _last_retrieve = _now

                    try:
                        ok, frame = cap.retrieve()
                    except Exception:
                        break
                    if ok and frame is not None:
                        self._slot.put(frame)
                        last_frame_t = time.time()
                    else:
                        break

            rt = threading.Thread(target=_read_loop, daemon=True,
                                  name="RTSPReadLoop")
            rt.start()

            while self._running:
                time.sleep(0.3)
                if not rt.is_alive():
                    break
                if time.time() - last_frame_t > self.FRAME_TIMEOUT:
                    break

            stop_evt.set()
            self._connected = False
            self._release_cap_async(cap)

            if self._running:
                # Muvaffaqiyatli ulanish uzilib ketdi — darhol qayta urinish
                self._fail_count += 1
                if 0 < self.max_reconnects < self._fail_count:
                    if callable(self._on_max_retries):
                        self._on_max_retries()
                    self._running = False
                    break
                wait = float(self._BACKOFF[min(self._fail_count - 1, len(self._BACKOFF) - 1)])
                if callable(self._on_reconnect_attempt):
                    self._on_reconnect_attempt(self._fail_count, wait)
                self._interruptible_sleep(wait)

    def _interruptible_sleep(self, seconds: float):
        end = time.time() + seconds
        while self._running and time.time() < end:
            time.sleep(0.2)

    # ── Tashqi interfeys ──────────────────────────────────────────────────

    def get_frame(self) -> tuple[bool, np.ndarray | None]:
        frame = self._slot.get()
        if frame is None:
            return False, None
        if self._slot.age_ms > 15_000:
            return False, None
        return True, frame

    def snapshot(self):
        """
        CameraService / DetectorGroup bilan mos interfeys.
        .frame, .timestamp, .fps, .status atributlari bor obyekt qaytaradi.
        """
        ok, frame = self.get_frame()

        snap = _Snap()
        snap.frame     = frame if ok else None
        snap.timestamp = self._slot._ts
        snap.fps       = self._slot.fps
        snap.status    = "online" if self._connected else "connecting"
        return snap

    @property
    def fps(self) -> float:
        return self._slot.fps

    @property
    def frame_count(self) -> int:
        return self._slot.total

    @property
    def latency_ms(self) -> float:
        return self._slot.age_ms

    @property
    def is_connected(self) -> bool:
        return self._connected

    def reset_backoff(self):
        """Qayta ulanish tugmasidan chaqiriladi — backoff hisoblagichini nolga tushiradi."""
        self._fail_count = 0

    def request_stop(self):
        self._running = False
        self._connected = False

    def stop(self):
        self.request_stop()
        if threading.current_thread() is not self:
            self.join(timeout=2.0)
