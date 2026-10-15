"""CleanupWorker — eski buzilish yozuvlari va rasm fayllarini tozalash.

Ikki alohida retention:
- `keep_db_days` (standart 365) — bazadagi yozuvlar (grafiklar 30 kun / 8 hafta
  ko'rsatadi, shuning uchun bu fayllardan ancha uzun bo'lishi kerak). Backend'ga
  hali yuborilmagan (queued/local/failed) yozuvlar hech qachon o'chirilmaydi.
- `keep_files_days` — diskdagi rasmlar; faqat `cleanup_files` yoqilgan bo'lsa.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


class CleanupWorker(QThread):
    finished_cleanup = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, db, cfg, keep_days: int = 7, cleanup_files: bool = False,
                 keep_db_days: int = 365, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg
        # keep_days — fayllar (keep_files_days) uchun; nomi eski chaqiruvlar uchun saqlangan
        self.keep_days = max(1, int(keep_days or 7))
        self.keep_db_days = max(1, int(keep_db_days or 365))
        self.cleanup_files = bool(cleanup_files)

    def run(self):
        deleted_files = 0
        deleted_rows = 0
        try:
            # Backend o'chiq bo'lsa `local` yozuvlar hech qachon yuborilmaydi —
            # ular ham muddati o'tgach o'chadi (aks holda cheksiz to'planardi).
            keep_local = bool(getattr(self.cfg, "backend_enabled", False))
            deleted_rows = int(self.db.cleanup_old(self.keep_db_days, keep_local=keep_local) or 0)
            # Yuborilgan/abadiy-xato notification joblarni ham tozalaymiz
            # (pending joblar tegilmaydi).
            try:
                self.db.cleanup_notification_jobs(self.keep_days)
            except Exception:
                pass
            if self.cleanup_files:
                deleted_files = self._cleanup_files()
            self.finished_cleanup.emit({
                "keep_days": self.keep_days,
                "keep_db_days": self.keep_db_days,
                "deleted_rows": deleted_rows,
                "deleted_files": deleted_files,
            })
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def _protected_paths(self) -> set[str]:
        """Backend yoqilgan bo'lsa — hali yuborilmagan buzilishlar rasmlari saqlanadi."""
        if not getattr(self.cfg, "backend_enabled", False):
            return set()
        try:
            return {_norm(p) for p in self.db.get_unsynced_image_paths()}
        except Exception:
            return set()

    def _cleanup_files(self) -> int:
        root = Path(getattr(self.cfg, "violations_dir", Path("violations")))
        if not root.exists():
            return 0
        cutoff = time.time() - self.keep_days * 86400
        protected = self._protected_paths()
        deleted = 0
        for path in root.rglob("*.jpg"):
            try:
                if path.stat().st_mtime < cutoff and _norm(path) not in protected:
                    os.remove(path)
                    deleted += 1
            except OSError:
                continue
        return deleted
