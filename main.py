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

# ── Venv Python ni majburan ishlatish ────────────────────────────────────
# Agar boshqa Python bilan ishga tushirilsa, venv Python'iga o'tadi
_BASE = Path(__file__).parent.resolve()
_VENV_PYTHON = _BASE / "venv" / "Scripts" / "python.exe"
if _VENV_PYTHON.exists() and Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

# ── SmartGUI papkasini sys.path ga qo'shish ──────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── torch va ultralytics AVVAL import — PyQt6 dan oldin ──────────────────
# Windows da Qt DLL'lari CUDA DLL yuklashiga to'sqinlik qiladi.
# Shuning uchun torch PyQt6 dan OLDIN import qilinishi shart.
def _ai_model_enabled() -> bool:
    try:
        settings_path = BASE_DIR / "settings.json"
        if not settings_path.exists():
            return False
        with open(settings_path, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("ai_model_enabled", False))
    except Exception:
        return False


def _ui_theme() -> str:
    try:
        settings_path = BASE_DIR / "settings.json"
        if not settings_path.exists():
            return "dark"
        with open(settings_path, "r", encoding="utf-8") as f:
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
    from PyQt6.QtGui import QPixmap, QFont, QColor
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


# ── Splash Screen ─────────────────────────────────────────────────────────

def _make_splash(app: QApplication) -> QSplashScreen:
    """Ishga tushirish vaqtida splash screen."""
    from PyQt6.QtGui import QPainter, QPen, QBrush, QLinearGradient
    from PyQt6.QtCore import QRect

    W, H = 480, 260
    px = QPixmap(W, H)
    px.fill(QColor("#0d1117"))

    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Chegarali to'rtburchak
    painter.setPen(QPen(QColor("#f97316"), 2))
    painter.setBrush(QBrush(QColor("#161b22")))
    painter.drawRoundedRect(16, 16, W - 32, H - 32, 12, 12)

    # Sarlavha
    font_big = QFont("Segoe UI", 26, QFont.Weight.Bold)
    painter.setFont(font_big)
    painter.setPen(QColor("#f97316"))
    painter.drawText(QRect(0, 50, W, 60), Qt.AlignmentFlag.AlignCenter, "SafeZone")

    # Kichik matn
    font_sm = QFont("Segoe UI", 11)
    painter.setFont(font_sm)
    painter.setPen(QColor("#8b949e"))
    painter.drawText(QRect(0, 115, W, 30), Qt.AlignmentFlag.AlignCenter,
                     "Xavfsizlik kuzatuv tizimi")

    # Yuklash matni
    font_xs = QFont("Segoe UI", 9)
    painter.setFont(font_xs)
    painter.setPen(QColor("#6b7280"))
    painter.drawText(QRect(0, H - 44, W, 24), Qt.AlignmentFlag.AlignCenter,
                     "Yuklanmoqda...")

    painter.end()

    splash = QSplashScreen(px, Qt.WindowType.WindowStaysOnTopHint)
    splash.setFont(QFont("Segoe UI", 10))
    return splash


# ── Asosiy funksiya ───────────────────────────────────────────────────────

def main():
    # High DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("SafeZone")
    app.setOrganizationName("SafeZone")
    app.setApplicationVersion("1.0.0")

    # Font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # QSS stil
    try:
        set_theme(_ui_theme())
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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
