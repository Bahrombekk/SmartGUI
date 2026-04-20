
import os
import time
import threading
import subprocess
import json
import numpy as np
import cv2

# HEVC/H.265 codec ogohlantirish xabarlarini bosish
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")


# ══════════════════════════════════════════════════════════════════════════════
#  CV2RTSPReader — OpenCV prebuilt FFmpeg orqali RTSP (subprocess talab qilmaydi)
# ══════════════════════════════════════════════════════════════════════════════

class CV2RTSPReader(threading.Thread):
    """
    cv2.VideoCapture asosida RTSP/RTMP stream o'quvchi.
    System ffmpeg binary talab qilinmaydi — OpenCV ichki FFmpeg ishlatiladi.

    Arxitektura:
      - Asosiy thread: ulanish + watchdog (frame_timeout ni nazorat qiladi)
      - Sub-thread (_read_loop): cap.read() ni bloklanmagan holda ishlatadi
      - cap.release() chaqirilsa cap.read() interrupt bo'ladi
    """

    FRAME_TIMEOUT = 8.0   # 8s frame kelmasa reconnect

    def __init__(self, rtsp_url: str, reconnect_delay: int = 3,
                 max_reconnects: int = 50):
        super().__init__(daemon=True)
        self.rtsp_url         = rtsp_url
        self.reconnect_delay  = reconnect_delay
        self.max_reconnects   = max_reconnects

        self._frame           = None
        self._lock            = threading.Lock()
        self._running         = True
        self._connected       = False
        self._reconnect_count = 0

    def run(self):
        while self._running:
            cap = None
            try:
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10_000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10_000)

                if not cap.isOpened():
                    raise RuntimeError("VideoCapture ochilmadi")

                self._connected = True
                self._reconnect_count = 0

                # last_frame_t — sub-thread va watchdog o'rtasida ulashiladi
                last_frame_t = [time.time()]
                stop_evt = threading.Event()

                def _read_loop():
                    while not stop_evt.is_set():
                        ok, frame = cap.read()
                        if ok and frame is not None:
                            with self._lock:
                                self._frame = frame
                            last_frame_t[0] = time.time()
                        else:
                            break  # stream uzildi

                rt = threading.Thread(target=_read_loop, daemon=True)
                rt.start()

                # Watchdog: frame_timeout dan uzoq kelmasa yoki sub-thread o'lsa
                while self._running:
                    time.sleep(0.4)
                    if not rt.is_alive():
                        break
                    if time.time() - last_frame_t[0] > self.FRAME_TIMEOUT:
                        break  # muzlab qolgan — majburan reconnect

                stop_evt.set()

            except Exception:
                pass
            finally:
                self._connected = False
                if cap is not None:
                    try:
                        # cap.release() — blokda turgan cap.read() ni to'xtatadi
                        cap.release()
                    except Exception:
                        pass

            if self._running:
                self._reconnect_count += 1
                time.sleep(min(self.reconnect_delay * (1 + self._reconnect_count // 10), 30))

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    @property
    def is_connected(self) -> bool:
        return self._connected

    def stop(self):
        self._running = False
        self.join(timeout=6.0)


# ══════════════════════════════════════════════════════════════════════════════
#  _FFmpegReader — subprocess orqali (system ffmpeg kerak, HW akselerasiya bilan)
# ══════════════════════════════════════════════════════════════════════════════

class _FFmpegReader(threading.Thread):
    """
    Subprocess-based FFmpeg RTSP reader.
    Faqat system 'ffmpeg' binary mavjud bo'lganda ishlaydi.
    HW akselerasiya qo'llab-quvvatlaydi (Intel QSV, D3D11VA).
    """

    def __init__(self, rtsp_url: str, reconnect_delay: int = 3,
                 max_reconnects: int = 20):
        super().__init__(daemon=True)
        self.rtsp_url        = rtsp_url
        self.reconnect_delay = reconnect_delay
        self.max_reconnects  = max_reconnects

        self._frame          = None
        self._lock           = threading.Lock()
        self._running        = True
        self._connected      = False
        self._reconnect_count = 0
        self._proc           = None
        self._hw_mode        = "unknown"

        self.out_width  = 1280
        self.out_height = 720
        self.fps        = 25.0

    def _probe(self):
        try:
            cmd = [
                "ffprobe", "-v", "error", "-rtsp_transport", "tcp",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json", self.rtsp_url,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            d = json.loads(r.stdout).get("streams", [])
            if d:
                s = d[0]
                w = int(s.get("width", 1280))
                h = int(s.get("height", 720))
                num, den = s.get("r_frame_rate", "25/1").split("/")
                fps = float(num) / max(float(den), 1.0)
                return w, h, fps
        except Exception:
            pass
        return 1280, 720, 25.0

    @staticmethod
    def _scale(w, h, max_w=1280):
        if w <= max_w:
            return (w // 2) * 2, (h // 2) * 2
        scale = max_w / w
        return max_w, (int(h * scale) // 2) * 2

    def _try_first_frame(self, proc, frame_size, timeout=5.0):
        result = {"data": None}

        def _r():
            try:
                result["data"] = proc.stdout.read(frame_size)
            except Exception:
                pass

        t = threading.Thread(target=_r, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            try:
                proc.kill()
            except Exception:
                pass
            return None
        return result["data"]

    def _open_ffmpeg(self, w, h):
        ow, oh = self._scale(w, h)
        fsize  = ow * oh * 3
        pre  = [
            "ffmpeg", "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer+discardcorrupt",
            "-flags", "low_delay",
            "-strict", "experimental",
        ]
        post = [
            "-i", self.rtsp_url, "-an",
            "-vf", f"scale={ow}:{oh}",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
        ]
        for name, opts in [
            ("Intel QSV", ["-hwaccel", "qsv", "-c:v", "h264_qsv"]),
            ("D3D11VA",   ["-hwaccel", "d3d11va"]),
            ("Software",  []),
        ]:
            try:
                proc = subprocess.Popen(
                    pre + opts + post,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=fsize * 2,
                )
                raw = self._try_first_frame(proc, fsize, timeout=5.0)
                if raw and len(raw) == fsize:
                    frame = np.frombuffer(raw, np.uint8).reshape((oh, ow, 3))
                    with self._lock:
                        self._frame = frame
                    self._hw_mode   = name
                    self.out_width  = ow
                    self.out_height = oh
                    return proc, fsize
                else:
                    try:
                        proc.kill(); proc.wait(timeout=2)
                    except Exception:
                        pass
            except Exception:
                pass
        return None, fsize

    def run(self):
        while self._running:
            if self._reconnect_count > self.max_reconnects:
                break
            proc = None
            try:
                w, h, self.fps = self._probe()
                proc, fsize = self._open_ffmpeg(w, h)
                if proc is None:
                    raise RuntimeError("FFmpeg ochilmadi")
                self._proc = proc
                self._connected = True
                self._reconnect_count = 0

                while self._running:
                    raw = proc.stdout.read(fsize)
                    if len(raw) < fsize:
                        break
                    frame = np.frombuffer(raw, np.uint8).reshape(
                        (self.out_height, self.out_width, 3)
                    )
                    with self._lock:
                        self._frame = frame
            except Exception:
                pass
            finally:
                self._connected = False
                self._proc = None
                if proc:
                    try:
                        proc.kill(); proc.wait(timeout=3)
                    except Exception:
                        pass

            if self._running:
                self._reconnect_count += 1
                time.sleep(self.reconnect_delay)

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    @property
    def is_connected(self):
        return self._connected

    def stop(self):
        self._running = False
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass
        self.join(timeout=5.0)
