#!/usr/bin/env python3
"""
SmartHelmet GUI — Entry point.
Zavod hududidagi xavfsizlik shlemini kiymaganlarni real vaqtda aniqlash
va ko'rsatuvchi desktop ilova.

Ishga tushirish:
    python main.py
    yoki
    run.bat (ikki marta bosib)
"""

import sys
import os
import json
from pathlib import Path

_FROZEN = bool(getattr(sys, "frozen", False))

# ── Venv Python ni majburan ishlatish ────────────────────────────────────
# Agar boshqa Python bilan ishga tushirilsa, venv Python'iga o'tadi (exe'da emas)
if not _FROZEN:
    _BASE = Path(__file__).parent.resolve()
    _VENV_PYTHON = _BASE / "venv" / "Scripts" / "python.exe"
    if _VENV_PYTHON.exists() and Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

    # ── SmartGUI papkasini sys.path ga qo'shish ──────────────────────────
    _src_dir = str(Path(__file__).parent.resolve())
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)

# ── --windowed exe'da stdout/stderr None bo'ladi — print/tqdm yiqilmasin ──
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from app import __version__
from app.shared.paths import DATA_DIR, resource_path

# Barcha nisbiy yo'llar (settings.json, smartgui.db, violations) DATA_DIR ga
# bog'lanadi — yorliq yoki service qaysi papkadan ishga tushirsa ham.
BASE_DIR = DATA_DIR
os.chdir(BASE_DIR)

# ── torch va ultralytics AVVAL import — PyQt6 dan oldin ──────────────────
# Windows da Qt DLL'lari CUDA DLL yuklashiga to'sqinlik qiladi.
# Shuning uchun torch PyQt6 dan OLDIN import qilinishi shart.
def _ai_model_enabled() -> bool:
    try:
        settings_path = BASE_DIR / "settings.json"
        if not settings_path.exists():
            return False
        with open(settings_path, "r", encoding="utf-8-sig") as f:
            return bool(json.load(f).get("ai_model_enabled", False))
    except Exception:
        return False


def _ui_theme() -> str:
    try:
        settings_path = BASE_DIR / "settings.json"
        if not settings_path.exists():
            return "dark"
        with open(settings_path, "r", encoding="utf-8-sig") as f:
            return str(json.load(f).get("theme", "dark")).lower()
    except Exception:
        return "dark"


if _ai_model_enabled():
    try:
        import torch
        try:
            import ultralytics  # noqa: F401
        except Exception:
            pass
    except Exception as _torch_err:
        print(f"[main] torch yuklanmadi: {_torch_err}", file=sys.stderr)

# ── PyQt6 import ─────────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QPixmap, QFont, QColor, QIcon
except ImportError:
    print("PyQt6 o'rnatilmagan. Quyidagi buyruqni bajaring:\n  pip install PyQt6",
          file=sys.stderr)
    sys.exit(1)

import logging
import logging.handlers

from app.ui.styles import build_main_stylesheet as get_main_stylesheet, set_theme

# ── Logging sozlash ───────────────────────────────────────────────────────
_log_dir = BASE_DIR / "logs"
_log_dir.mkdir(exist_ok=True)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S")
_root = logging.getLogger()
_root.setLevel(logging.INFO)
_ch = logging.StreamHandler()
_ch.setFormatter(_fmt)
_fh = logging.handlers.RotatingFileHandler(
    _log_dir / "smartgui.log", maxBytes=5*1024*1024, backupCount=7, encoding="utf-8"
)
_fh.setFormatter(_fmt)
_root.addHandler(_ch)
_root.addHandler(_fh)
_log = logging.getLogger("main")


def _excepthook(exc_type, exc, tb):
    """Qt slot ichidagi ushlanmagan xato PyQt6'da butun dasturni yopadi (qFatal).
    O'rniga log'ga yozamiz — konsolsiz exe'da ham logs/ da ko'rinadi."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    _log.critical("Ushlanmagan xato", exc_info=(exc_type, exc, tb))


sys.excepthook = _excepthook


# ── Splash Screen ─────────────────────────────────────────────────────────

def _make_splash(app: QApplication) -> QSplashScreen:
    """Ishga tushirish vaqtida splash screen — Figma dizayni (navy karta, cyan aksent)."""
    from PyQt6.QtGui import QPainter, QPen, QLinearGradient, QBrush, QPainterPath
    from PyQt6.QtCore import QRectF

    try:
        from app.ui import fz
        sans = lambda px, w=400: fz.qfont(px, w)
        mono = lambda px, w=400: fz.qfont(px, w, mono=True)
        logo = lambda size: fz.svg_pixmap("logo", size, size, fz.ACCENT)
    except Exception:
        sans = lambda px, w=400: QFont("Segoe UI", max(1, int(px * 0.75)), w)
        mono = sans
        logo = None

    CARD, BORDER = "#0b1426", "#1a2842"
    TEXT, TEXT2, MUTED, DIM, ACCENT = "#e8f0fb", "#b4c0d3", "#7e8ea8", "#4a5872", "#1fb6ff"

    SH = 18                                   # soya uchun shaffof hoshiya
    W, H = 460, 248
    dpr = app.primaryScreen().devicePixelRatio() if app.primaryScreen() else 1.0
    px = QPixmap(int((W + 2 * SH) * dpr), int((H + 2 * SH) * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # Yumshoq soya
    for i in range(SH, 0, -2):
        c = QColor(0, 0, 0, int(70 * (1 - i / SH) ** 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(SH - i, SH - i + 4, W + 2 * i, H + 2 * i), 14 + i, 14 + i)

    card = QRectF(SH + 0.5, SH + 0.5, W - 1, H - 1)
    path = QPainterPath()
    path.addRoundedRect(card, 14, 14)
    p.fillPath(path, QColor(CARD))
    # Yuqoridan cyan nur (juda xira)
    glow = QLinearGradient(0, SH, 0, SH + 120)
    glow.setColorAt(0, QColor(31, 182, 255, 26))
    glow.setColorAt(1, QColor(31, 182, 255, 0))
    p.fillPath(path, QBrush(glow))
    p.setPen(QPen(QColor(BORDER), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    x0, y0 = SH, SH
    # Logo qutisi
    box = QRectF(x0 + (W - 56) / 2, y0 + 38, 56, 56)
    p.setPen(QPen(QColor(31, 182, 255, 90), 1))
    p.setBrush(QColor("#0e2a45"))
    p.drawRoundedRect(box, 14, 14)
    if logo is not None:
        p.drawPixmap(int(box.x() + 14), int(box.y() + 14), logo(28))

    p.setFont(sans(26, 700))
    p.setPen(QColor(TEXT))
    p.drawText(QRectF(x0, y0 + 106, W, 36), Qt.AlignmentFlag.AlignCenter, "SafeZone")
    p.setFont(sans(13, 400))
    p.setPen(QColor(TEXT2))
    p.drawText(QRectF(x0, y0 + 142, W, 20), Qt.AlignmentFlag.AlignCenter,
               "Shlem nazorati · xavfsizlik kuzatuv tizimi")

    # Yuklanish chizig'i
    bw = 160
    track = QRectF(x0 + (W - bw) / 2, y0 + 186, bw, 3)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(BORDER))
    p.drawRoundedRect(track, 1.5, 1.5)
    g = QLinearGradient(track.x(), 0, track.x() + bw * 0.45, 0)
    g.setColorAt(0, QColor(31, 182, 255, 40))
    g.setColorAt(1, QColor(ACCENT))
    p.setBrush(QBrush(g))
    p.drawRoundedRect(QRectF(track.x(), track.y(), bw * 0.45, 3), 1.5, 1.5)

    p.setFont(sans(12, 400))
    p.setPen(QColor(MUTED))
    p.drawText(QRectF(x0, y0 + 198, W, 18), Qt.AlignmentFlag.AlignCenter, "Yuklanmoqda…")
    p.setFont(mono(10.5, 400))
    p.setPen(QColor(DIM))
    p.drawText(QRectF(x0, y0 + H - 26, W - 16, 16),
               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"v{__version__}")
    p.end()

    splash = QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return splash


# ── Asosiy funksiya ───────────────────────────────────────────────────────

def main():
    # High DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Windows taskbar python.exe ikonkasini emas, ilova ikonkasini ko'rsatsin
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SafeZone.SmartGUI")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("SafeZone")
    app.setOrganizationName("SafeZone")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(resource_path("images", "app.ico"))))

    # Yagona nusxa: ikkinchi nusxa bildirishnoma va buzilishlarni dublikat qiladi.
    # QLockFile jarayon yiqilsa ham eskirgan lockni o'zi aniqlaydi.
    from PyQt6.QtCore import QLockFile
    from app.shared.paths import data_path

    instance_lock = QLockFile(str(data_path("smartgui.lock")))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(100):
        _log.warning("Ikkinchi nusxa ishga tushirildi — chiqilmoqda")
        QMessageBox.information(None, "SafeZone", "SafeZone allaqachon ishlayapti")
        sys.exit(0)

    # Font — Figma dizayni: Inter + JetBrains Mono (fonts/ papkasidan)
    try:
        from app.ui import fz
        fz.init_fonts()
        font = QFont(fz.SANS)
        font.setPointSizeF(fz.pt(13))
    except Exception as e:
        _log.warning("Shriftlar yuklanmadi: %s", e)
        font = QFont("Segoe UI", 10)
    app.setFont(font)

    # QSS stil
    try:
        set_theme("dark")      # Figma dizayni: faqat qorong'i mavzu
        app.setStyleSheet(get_main_stylesheet())
    except Exception as e:
        _log.warning("Stil yuklanmadi: %s", e)

    # Splash
    splash = _make_splash(app)
    splash.show()
    app.processEvents()

    # Asosiy oyna (0.8 soniyadan keyin ochiladi)
    window = None

    def _open_main():
        nonlocal window
        try:
            from app.ui.pages.main_window import MainWindow

            window = MainWindow()
            window.show()
            splash.finish(window)
        except Exception as e:
            splash.close()
            import traceback, datetime
            tb = traceback.format_exc()
            log_path = BASE_DIR / "logs" / f"crash_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            log_path.parent.mkdir(exist_ok=True)
            log_path.write_text(
                f"Python: {sys.executable}\n"
                f"sys.path:\n" + "\n".join(sys.path) + f"\n\nError:\n{tb}",
                encoding="utf-8"
            )
            QMessageBox.critical(
                None, "Xatolik",
                f"Dastur ochilmadi:\n{e}\n\n"
                f"Batafsil: {log_path}\n\n"
                "Sozlamalarni tekshiring va qayta urinib ko'ring."
            )
            sys.exit(1)

    QTimer.singleShot(800, _open_main)

    code = app.exec()
    instance_lock.unlock()
    _exit_safely(code)


def _exit_safely(code: int) -> None:
    """Vaqtida to'xtamagan QThread qolsa — Python finalizatsiyasini o'tkazib
    yuboramiz: aks holda u QThread'ni o'chirib "Destroyed while thread is still
    running" bilan dastur abort bo'ladi."""
    try:
        from app.ui.controllers.camera_runtime_controller import running_orphan_threads
        orphans = running_orphan_threads()
    except Exception:
        orphans = []
    if orphans:
        _log.warning("%s ta thread hali ishlayapti — majburiy chiqish", len(orphans))
        logging.shutdown()
        os._exit(code)
    sys.exit(code)


if __name__ == "__main__":
    # Windows multiprocessing (subprocess kamera reader) uchun zarur
    import multiprocessing
    multiprocessing.freeze_support()
    main()
