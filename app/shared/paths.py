"""
Ilova yo'llari — oddiy ishga tushirish va PyInstaller exe uchun yagona joy.

RESOURCE_DIR — faqat o'qiladigan resurslar (images, qss, app/models).
               Exe'da: sys._MEIPASS (`_internal/`), oddiy rejimda: loyiha ildizi.
DATA_DIR     — yoziladigan ma'lumotlar (settings.json, smartgui.db, logs,
               violations). Oddiy rejimda: loyiha ildizi. Exe'da:
               - SAFEZONE_DATA_DIR muhit o'zgaruvchisi bo'lsa — o'sha;
               - Program Files'ga o'rnatilgan bo'lsa — %PROGRAMDATA%\\SafeZone
                 (Program Files'ga oddiy foydalanuvchi yoza olmaydi);
               - aks holda (portable) — exe turgan papka.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))


def _is_under(path: Path, parent: str | None) -> bool:
    if not parent:
        return False
    try:
        path.relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def _frozen_data_dir(exe_dir: Path) -> Path:
    override = os.environ.get("SAFEZONE_DATA_DIR", "").strip()
    if override:
        return Path(override)
    program_files = (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.environ.get("ProgramW6432"))
    if any(_is_under(exe_dir, pf) for pf in program_files):
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SafeZone"
    return exe_dir


if FROZEN:
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    DATA_DIR = _frozen_data_dir(Path(sys.executable).parent.resolve())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
else:
    RESOURCE_DIR = Path(__file__).resolve().parents[2]
    DATA_DIR = RESOURCE_DIR


def resource_path(*parts: str) -> Path:
    """Bundle ichidagi resurs yo'li (images, qss, models)."""
    return RESOURCE_DIR.joinpath(*parts)


def data_path(*parts: str) -> Path:
    """Yoziladigan ma'lumot yo'li (settings, db, logs)."""
    return DATA_DIR.joinpath(*parts)


def resolve_model_path(model_path: str | Path) -> Path:
    """
    Nisbiy model yo'lini topadi: avval DATA_DIR (foydalanuvchi o'z modelini
    exe yoniga qo'yishi mumkin), keyin RESOURCE_DIR (bundle ichidagi model).
    """
    p = Path(str(model_path or ""))
    if not str(model_path or "").strip() or p.is_absolute():
        return p
    user_p = DATA_DIR / p
    if user_p.exists():
        return user_p
    return RESOURCE_DIR / p
