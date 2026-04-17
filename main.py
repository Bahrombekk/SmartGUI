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
try:
    import torch
    try:
        import ultralytics  # noqa: F401
    except Exception:
        pass
except Exception as _torch_err:
    print(f"[main] torch yuklanmadi: {_torch_err}")

# ── PyQt6 import ─────────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QPixmap, QFont, QColor
except ImportError:
    print("PyQt6 o'rnatilmagan. Quyidagi buyruqni bajaring:")
    print("  pip install PyQt6")
    sys.exit(1)

from app.ui.theme import get_main_stylesheet
from app.ui.pages.main_window import MainWindow


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
    painter.drawText(QRect(0, 50, W, 60), Qt.AlignmentFlag.AlignCenter, "⛑ SmartHelmet")

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
    app.setApplicationName("SmartHelmet GUI")
    app.setOrganizationName("SmartHelmet")
    app.setApplicationVersion("1.0.0")

    # Font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # QSS stil
    try:
        app.setStyleSheet(get_main_stylesheet())
    except Exception as e:
        print(f"[main] Stil yuklanmadi: {e}")

    # Splash
    splash = _make_splash(app)
    splash.show()
    app.processEvents()

    # Asosiy oyna (0.8 soniyadan keyin ochiladi)
    window = None

    def _open_main():
        nonlocal window
        try:
            window = MainWindow()
            window.show()
        except Exception as e:
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
        finally:
            splash.finish(window)

    QTimer.singleShot(800, _open_main)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
