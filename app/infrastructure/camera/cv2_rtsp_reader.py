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
from collections import deque
import numpy as np
import cv2

import logging

from app.infrastructure.camera.rtsp_probe import blocking_reason, diagnose
from app.shared.utils.rate_gate import RateGate

_log = logging.getLogger(__name__)

os.environ["OPENCV_LOG_LEVEL"]       = "ERROR"
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "quiet"

# GPU (NVDEC) bilan dekodlash — CPU yukini sezilarli kamaytiradi
# threads;1 — pthread_frame.c async_lock assertion crash ni to'xtatadi
_RTSP_OPTIONS_GPU = (
    "rtsp_transport;tcp|"
    "stimeout;5000000|"
    "fflags;nobuffer|"
    "flags;low_delay|"
    "analyzeduration;1000000|"
    "probesize;500000|"
    "threads;1|"
    "hwaccel;cuda|"
    "hwaccel_device;0"
)

# CPU fallback — threads;1 HEVC ko'p-threadli decoder crash ni oldini oladi
_RTSP_OPTIONS = (
    "rtsp_transport;tcp|"
    "stimeout;5000000|"
    "fflags;nobuffer|"
    "flags;low_delay|"
    "analyzeduration;1000000|"
    "probesize;500000|"
    "threads;1"
)

def _cuda_ffmpeg_available() -> bool:
    """NVDEC (CUDA hwaccel) mavjudligini tekshiradi."""
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False

_USE_GPU_DECODE = _cuda_ffmpeg_available()

_RTSP_OPTIONS_UDP = (
    "rtsp_transport;udp|stimeout;5000000|fflags;nobuffer|"
    "analyzeduration;1000000|probesize;500000|threads;1"
)
_RTSP_OPTIONS_ANY = "rtsp_transport;tcp|stimeout;8000000|fflags;nobuffer|threads;1"


class _CaptureOptionsGate:
    """OPENCV_FFMPEG_CAPTURE_OPTIONS — jarayon bo'yicha umumiy env o'zgaruvchi.

    Bir nechta reader thread uni parallel o'rnatsa, bitta kamera boshqasining
    (masalan UDP) sozlamasi bilan ochilib qolardi. Env set + VideoCapture ochish
    shu gate ichida bajariladi: BIR XIL sozlamali ochishlar parallel ketadi
    (oddiy holat — barcha kamera TCP), boshqacha sozlama esa ular tugashini
    kutadi. Osilib qolgan ochish butun tizimni to'xtatmasligi uchun kutish
    `timeout` bilan cheklangan."""

    def __init__(self):
        self._cond = threading.Condition()
        self._current: str | None = None
        self._active = 0

    def acquire(self, options: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._active and self._current != options:
                left = deadline - time.monotonic()
                if left <= 0:
                    break  # kutish tugadi — baribir davom etamiz (avvalgi xatti-harakat)
                self._cond.wait(left)
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = options
            self._current = options
            self._active += 1
            return True

    def release(self) -> None:
        with self._cond:
            self._active = max(0, self._active - 1)
            if self._active == 0:
                self._current = None
            self._cond.notify_all()


_OPTIONS_GATE = _CaptureOptionsGate()


class _Snap:
    """snapshot() qaytaruvchi yengil obyekt — bir marta aniqlanadi."""
    __slots__ = ("frame", "timestamp", "fps", "status", "corrupt")


class FramePacket:
    """Tartibli kadr navbatidagi yozuv: kadr + uning kamera vaqti.

    `frame` consumerlar o'rtasida UMUMIY — o'zgartirmang (chizishdan oldin copy())."""
    __slots__ = ("seq", "ts", "arrival", "frame", "corrupt", "fps", "timestamp")

    def __init__(self, seq: int, ts: float, arrival: float, frame: np.ndarray, corrupt: bool):
        self.seq, self.ts, self.arrival, self.frame, self.corrupt = seq, ts, arrival, frame, corrupt
        self.fps, self.timestamp = 0.0, ts


class _MediaClock:
    """Kamera PTS'ini (ms) perf_counter vaqtiga o'giradi.

    Tarmoq kadrlarni notekis yetkazadi: 1.2 s uzilishdan keyin 30 kadr 10 ms
    oralig'ida keladi, PTS esa ularni to'g'ri 40 ms oralig'ida ko'rsatadi
    (o'lchangan). Kelish vaqti bo'yicha ishlansa bu kadrlar tashlanadi va
    tracker tezlikni noto'g'ri hisoblaydi. offset = min(kelish − PTS) so'nggi
    ~10 s bo'yicha — minimal tarmoq kechikishi; soat siljishiga moslashadi.
    PTS yo'q / orqaga ketsa / >5 s sakrasa — qayta sinxronlanadi."""

    def __init__(self):
        self._offs: deque = deque(maxlen=250)
        self._last_pts: float | None = None

    def reset(self):
        self._offs.clear()
        self._last_pts = None

    def map(self, pts_ms: float, arrival: float) -> float:
        if not pts_ms or pts_ms <= 0:
            return arrival
        if self._last_pts is not None and not (0 < pts_ms - self._last_pts <= 5000):
            self._offs.clear()
        self._last_pts = pts_ms
        pts = pts_ms / 1000.0
        self._offs.append(arrival - pts)
        return min(pts + min(self._offs), arrival)


def is_corrupt_frame(frame: np.ndarray) -> bool:
    """HEVC/H.264 dekoder havola kadrni yo'qotganda (PPS / "Could not find ref")
    kadrning katta qismi aynan o'rta kulrang (128,128,128) bo'lib chiqadi —
    bunday kadrda model odamlarni topa olmaydi va tracker ularni yo'qotadi.
    Haqiqiy sahnada uchala kanal ±2 aniqlikda 128 bo'lgan 20% maydon deyarli
    bo'lmaydi (asfalt ham emas)."""
    s = frame[::16, ::16]
    flat = (np.abs(s.astype(np.int16) - 128) <= 2).all(axis=2)
    return float(flat.mean()) > 0.20


# ── Lock-free double buffer ───────────────────────────────────────────────────

class _FrameSlot:
    """Lock-free double buffer — get() hech qachon bloklanmaydi."""

    __slots__ = ("_bufs", "_idx", "_lock", "_cond", "total", "_ts",
                 "_fps", "_fps_count", "_fps_ts", "_meta", "_queues", "_arrival")

    def __init__(self):
        self._bufs     = [None, None]
        self._meta     = [(0.0, False), (0.0, False)]   # (media ts, corrupt) har buferga
        self._queues: dict[str, deque] = {}             # tartibli consumer navbatlari
        self._arrival  = 0.0
        self._idx      = 0
        self._lock     = threading.Lock()
        self._cond     = threading.Condition(self._lock)
        self.total     = 0
        self._ts       = 0.0
        self._fps      = 0.0
        self._fps_count = 0
        self._fps_ts   = time.perf_counter()

    def subscribe(self, name: str, maxlen: int = 30) -> None:
        """Tartibli navbat ochadi: put() har kadrni unga ham qo'shadi (pop() bilan olinadi).
        maxlen — consumer sekinlashsa eng eskilari tushadi (xotira chegarasi)."""
        with self._lock:
            self._queues.setdefault(name, deque(maxlen=maxlen))

    def pop(self, name: str) -> list:
        with self._lock:
            q = self._queues.get(name)
            if not q:
                return []
            out = list(q)
            q.clear()
            return out

    def put(self, frame: np.ndarray, ts: float | None = None, corrupt: bool = False):
        if frame is None or frame.size == 0:
            return
        if len(frame.shape) < 3 or frame.shape[2] != 3:
            return  # grayscale yoki buzilgan frame — o'tkazib yubor
        if frame.shape[0] < 8 or frame.shape[1] < 8:
            return  # juda kichik frame — buzilgan
        now = time.perf_counter()
        ts = now if ts is None else ts
        with self._lock:
            self._idx ^= 1
            self._bufs[self._idx] = frame
            self._meta[self._idx] = (ts, corrupt)
            self.total += 1
            self._ts = ts
            self._arrival = now
            if self._queues:
                pkt = FramePacket(self.total, ts, now, frame, corrupt)
                for q in self._queues.values():
                    q.append(pkt)
            self._fps_count += 1
            elapsed = now - self._fps_ts
            if elapsed >= 1.0:
                self._fps = self._fps_count / elapsed
                self._fps_count = 0
                self._fps_ts = now
            self._cond.notify_all()

    def wait_newer(self, last_total: int, timeout: float) -> bool:
        """`last_total` dan keyingi kadr kelguncha kutadi (polling'siz)."""
        with self._cond:
            if self.total != last_total:
                return True
            self._cond.wait(timeout)
            return self.total != last_total

    def get(self) -> np.ndarray | None:
        with self._lock:
            f = self._bufs[self._idx]
            return f.copy() if f is not None else None

    def get_with_meta(self) -> tuple[np.ndarray | None, float, bool]:
        """Kadr va AYNAN shu kadrning vaqti/buzilganligi (alohida o'qilsa
        kadr bitta put()dan, vaqt keyingisidan kelishi mumkin edi)."""
        with self._lock:
            f = self._bufs[self._idx]
            ts, corrupt = self._meta[self._idx]
            return (f.copy() if f is not None else None), ts, corrupt

    @property
    def fps(self) -> float:
        with self._lock:
            return self._fps

    @property
    def age_ms(self) -> float:
        return (time.perf_counter() - self._arrival) * 1000 if self._arrival else 9999.0


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
    # max_reconnects dan keyin ham to'xtamaymiz — shu oraliqda abadiy qayta urinamiz
    MAX_BACKOFF = 60.0

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
        self._on_reconnect_attempt = on_reconnect_attempt  # (attempt, wait_sec, reason) -> None
        self._on_max_retries       = on_max_retries        # () -> None

        self._slot       = _FrameSlot()
        self._running    = True
        self._connected  = False
        self._fail_count = 0
        self.last_error  = ""   # oxirgi ulanish xatosining tushunarli sababi
        self._limit_notified = False   # on_max_retries shu uzilish davrida chaqirildimi
        self._wake = threading.Event() # reset_backoff/stop kutishni darhol uzadi

        # CameraService (DetectorGroup) tomonidan set qilinadi
        self.cam_id: int = 0
        self.corrupt_frames = 0   # dekoder buzgan kadrlar soni (diagnostika)

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
                       name: str = "RTSPOpen",
                       api: int = cv2.CAP_FFMPEG) -> cv2.VideoCapture | None:
        """
        VideoCapture ni thread ichida ochadi.
        RailSafeGUI yondashuvi: thread + join(timeout) — bloklanmaydi.

        Barcha ochish usullari (GPU/TCP/UDP/CAP_ANY) shu yerdan o'tadi:
        OPEN_TIMEOUT dan keyin kech ochilgan cap `abandoned` belgisi tufayli
        worker thread'ning o'zida yopiladi — RTSP sessiya oqib ketmaydi
        (kameralar sessiya sonini cheklaydi → 453/503).
        """
        result = [None]
        lock = threading.Lock()
        abandoned = [False]
        url = self.rtsp_url
        first_n = self.FIRST_FRAME_N
        slot = self._slot
        gate_timeout = self.OPEN_TIMEOUT

        def _worker():
            cap = None
            try:
                _OPTIONS_GATE.acquire(options, gate_timeout)
                try:
                    cap = cv2.VideoCapture(url, api)
                finally:
                    _OPTIONS_GATE.release()
                if not cap.isOpened():
                    cap.release()
                    return

                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FPS, 25)

                for _ in range(first_n):
                    with lock:
                        if abandoned[0]:
                            break  # kutish vaqti o'tib ketgan — hech kim olmaydi
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        with lock:
                            if not abandoned[0]:
                                slot.put(frame)
                                result[0] = cap
                                return
                        break  # kutish vaqti o'tib ketgan — hech kim olmaydi
                cap.release()  # shu threadda — parallel foydalanish yo'q
            except Exception:
                if cap is not None and result[0] is not cap:
                    try:
                        cap.release()
                    except Exception:
                        pass

        t = threading.Thread(target=_worker, daemon=True, name=name)
        t.start()
        t.join(timeout=self.OPEN_TIMEOUT)

        with lock:
            if result[0] is None:
                abandoned[0] = True  # kech ochilsa worker o'zi yopadi (leak yo'q)
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
        if cap is not None or not self._running:
            return cap

        # 2-urinish: UDP
        cap = self._try_open_cap(_RTSP_OPTIONS_UDP, "RTSPOpenUDP")
        if cap is not None or not self._running:
            return cap

        # 3-urinish: CAP_ANY
        return self._try_open_cap(_RTSP_OPTIONS_ANY, "RTSPOpenAny", api=cv2.CAP_ANY)

    # ── Asosiy read loop ──────────────────────────────────────────────────

    def run(self):
        while self._running:
            # Tezkor tekshiruv (~3 s): kamera aniq ishlamasa sabab darhol ko'rinadi,
            # 4 usulli FFmpeg urinishlari (~50 s) kutilmaydi
            quick = None
            if self.rtsp_url.lower().startswith(("rtsp://", "rtsps://")):
                try:
                    quick = blocking_reason(self.rtsp_url)
                except Exception:
                    quick = None
            cap = None if quick else self._open()

            if cap is None or not cap.isOpened():
                self._connected = False
                self._fail_count += 1
                if quick:
                    self.last_error = quick
                # Sabab: birinchi urinishda va keyin har 3-urinishda (kamera ortiqcha bezovta qilinmasin)
                elif self._fail_count == 1 or self._fail_count % 3 == 0 or not self.last_error:
                    try:
                        self.last_error = diagnose(self.rtsp_url) or "Video oqim ochilmadi"
                    except Exception:
                        self.last_error = "Video oqim ochilmadi"
                self._after_failure()
                continue

            self._connected  = True
            self._fail_count = 0
            self._limit_notified = False
            self.last_error  = ""
            last_frame_t = time.time()
            stop_evt     = threading.Event()

            def _read_loop():
                # cap faqat shu threadda yopiladi: grab()/retrieve() davom
                # etayotganda boshqa threaddan release() qilish FFmpeg'da
                # "pthread_frame.c async_lock" assertion bilan butun jarayonni
                # yiqitadi (kamera restart/o'chirishda).
                try:
                    _grab_loop()
                finally:
                    try:
                        cap.release()
                    except Exception:
                        pass

            def _grab_loop():
                nonlocal last_frame_t
                # Token-bucket: O'RTACHA tezlik target_fps bilan cheklanadi, lekin
                # tarmoqdan to'p-to'p kelgan kadrlar tashlanmaydi. Avvalgi "oxirgi
                # retrieve'dan beri 1/fps o'tdimi" tekshiruvi 20 FPS kamerada
                # kadrlarning ~36% ini tashlardi (20 → 12.8 FPS). grab() o'zi keyingi
                # kadrgacha bloklanadi — sleep kerak emas (sleep faqat kechikish qo'shadi).
                gate = RateGate(self._target_fps, burst=2.0)
                clock = _MediaClock()
                while not stop_evt.is_set():
                    try:
                        ok = cap.grab()
                    except Exception:
                        break
                    if not ok:
                        break
                    arrival = time.perf_counter()
                    try:
                        pts_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                    except Exception:
                        pts_ms = 0.0
                    ts = clock.map(pts_ms, arrival)

                    # Limit kamera vaqti bo'yicha: tarmoq to'p qilib yetkazgan
                    # kadrlar (PTS bo'yicha tekis) tashlanmaydi
                    if not gate.try_take(ts):
                        last_frame_t = time.time()   # oqim tirik — faqat limit tufayli o'tkazildi
                        continue

                    try:
                        ok, frame = cap.retrieve()
                    except Exception:
                        break
                    if ok and frame is not None:
                        corrupt = is_corrupt_frame(frame)
                        if corrupt:
                            self.corrupt_frames += 1
                        self._slot.put(frame, ts, corrupt)
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
            # release() ni _read_loop o'zi bajaradi (grab tugagach) — bu yerda
            # parallel release qilinmaydi.

            if self._running:
                # Muvaffaqiyatli ulanish uzilib ketdi — darhol qayta urinish
                self._fail_count += 1
                self.last_error = "Oqim uzilib qoldi — qayta ulanmoqda"
                self._after_failure()

    def _backoff_wait(self) -> float:
        idx = min(max(0, self._fail_count - 1), len(self._BACKOFF) - 1)
        return min(float(self._BACKOFF[idx]), self.MAX_BACKOFF)

    def _after_failure(self) -> None:
        """Muvaffaqiyatsiz ulanishdan keyin: xabar berish va backoff bilan kutish.

        max_reconnects ga yetganda reader TO'XTAMAYDI: on_max_retries faqat bir
        marta chaqiriladi (UI ga ogohlantirish), keyin MAX_BACKOFF (60 s) oralig'ida
        jimgina qayta urinishda davom etadi — tungi uzilishdan keyin kamera o'zi
        tiklanadi."""
        wait = self._backoff_wait()
        over_limit = 0 < self.max_reconnects < self._fail_count
        if over_limit:
            wait = self.MAX_BACKOFF
            if not self._limit_notified:
                self._limit_notified = True
                if callable(self._on_max_retries):
                    try:
                        self._on_max_retries()
                    except Exception as exc:
                        _log.debug("on_max_retries xatosi: %s", exc)
            else:
                _log.debug("Kamera hali ham ulanmadi (%s urinish): %s",
                           self._fail_count, self.last_error)
        elif callable(self._on_reconnect_attempt):
            self._on_reconnect_attempt(self._fail_count, wait, self.last_error)
        self._interruptible_sleep(wait)

    def _interruptible_sleep(self, seconds: float):
        end = time.time() + seconds
        while self._running and time.time() < end:
            if self._wake.wait(min(0.2, max(0.0, end - time.time()))):
                self._wake.clear()
                break

    # ── Tashqi interfeys ──────────────────────────────────────────────────

    def wait_new_frame(self, last_id: int, timeout: float = 0.25) -> bool:
        """`last_id` (frame_count) dan yangi kadr kelguncha kutadi."""
        return self._slot.wait_newer(last_id, timeout)

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
        frame, ts, corrupt = self._slot.get_with_meta()
        ok = frame is not None and self._slot.age_ms <= 15_000

        snap = _Snap()
        snap.frame     = frame if ok else None
        snap.timestamp = ts
        snap.fps       = self._slot.fps
        snap.status    = "online" if self._connected else "connecting"
        snap.corrupt   = corrupt
        return snap

    def subscribe(self, name: str, maxlen: int = 30) -> None:
        """Tartibli kadr navbati (worker/AI): to'p kelgan kadrlar ham yo'qolmaydi."""
        self._slot.subscribe(name, maxlen)

    def pop_frames(self, name: str) -> list:
        """`subscribe(name)` dan beri kelgan kadrlar (FramePacket), vaqt tartibida."""
        return self._slot.pop(name)

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
        """Qayta ulanish tugmasidan chaqiriladi — backoff hisoblagichini nolga tushiradi
        va kutayotgan bo'lsa darhol qayta urinadi."""
        self._fail_count = 0
        self._limit_notified = False
        self._wake.set()

    def request_stop(self):
        self._running = False
        self._connected = False
        self._wake.set()

    def stop(self):
        self.request_stop()
        if threading.current_thread() is not self:
            self.join(timeout=2.0)
