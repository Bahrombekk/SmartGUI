from __future__ import annotations

import os
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class CleanupWorker(QThread):
    finished_cleanup = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, db, cfg, keep_days: int = 7, cleanup_files: bool = False, parent=None):
        super().__init__(parent)
        self.db = db
        self.cfg = cfg
        self.keep_days = max(1, int(keep_days or 7))
        self.cleanup_files = bool(cleanup_files)

    def run(self):
        deleted_files = 0
        try:
            self.db.cleanup_old(self.keep_days)
            if self.cleanup_files:
                deleted_files = self._cleanup_files()
            self.finished_cleanup.emit({"keep_days": self.keep_days, "deleted_files": deleted_files})
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def _cleanup_files(self) -> int:
        root = Path(getattr(self.cfg, "violations_dir", Path("violations")))
        if not root.exists():
            return 0
        cutoff = time.time() - self.keep_days * 86400
        deleted = 0
        for path in root.rglob("*.jpg"):
            try:
                if path.stat().st_mtime < cutoff:
                    os.remove(path)
                    deleted += 1
            except OSError:
                continue
        return deleted
