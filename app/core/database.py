"""
SQLite ma'lumotlar bazasi — buzilishlar jurnali.
"""

import sqlite3
import threading
from datetime import datetime, date, timedelta
from pathlib import Path


DB_FILE = "smartgui.db"


class ViolationsDB:
    """Buzilishlar (violations) jurnalini SQLite da boshqarish."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ── Ishga tushirish ────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        """Jadvallarni yaratish (mavjud bo'lmasa)."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS violations (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp       INTEGER NOT NULL,
                        track_id        INTEGER NOT NULL,
                        crop_path       TEXT    DEFAULT '',
                        full_path       TEXT    DEFAULT '',
                        camera_name     TEXT    DEFAULT '',
                        confidence      REAL    DEFAULT 0.0,
                        created_at      TEXT    NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_violations_timestamp
                    ON violations (timestamp)
                """)
                conn.commit()
            finally:
                conn.close()

    # ── Yozish ────────────────────────────────────────────────────────────

    def add_violation(
        self,
        track_id: int,
        crop_path: str = "",
        full_path: str = "",
        camera_name: str = "",
        confidence: float = 0.0,
        timestamp: int = 0,
    ) -> int:
        """Yangi buzilish yozuvi qo'shish. Yangi record ID qaytaradi."""
        if not timestamp:
            timestamp = int(datetime.now().timestamp())
        created_at = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("""
                    INSERT INTO violations
                        (timestamp, track_id, crop_path, full_path,
                         camera_name, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (timestamp, track_id, crop_path, full_path,
                      camera_name, confidence, created_at))
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    # ── O'qish ────────────────────────────────────────────────────────────

    def get_violations(
        self,
        date_from: date = None,
        date_to: date = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """
        Buzilishlarni filtrlangan holda olish.
        date_from / date_to: Python date obyekti (None = cheksiz).
        """
        conditions = []
        params = []

        if date_from:
            ts_from = int(datetime.combine(date_from, datetime.min.time()).timestamp())
            conditions.append("timestamp >= ?")
            params.append(ts_from)

        if date_to:
            ts_to = int(datetime.combine(date_to, datetime.max.time()).timestamp())
            conditions.append("timestamp <= ?")
            params.append(ts_to)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params += [limit, offset]

        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(f"""
                    SELECT * FROM violations
                    {where}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_today_count(self) -> int:
        """Bugungi buzilishlar soni."""
        today = date.today()
        ts_from = int(datetime.combine(today, datetime.min.time()).timestamp())
        ts_to   = int(datetime.combine(today, datetime.max.time()).timestamp())

        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM violations WHERE timestamp BETWEEN ? AND ?",
                    (ts_from, ts_to)
                ).fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def get_total_count(self) -> int:
        """Jami buzilishlar soni."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT COUNT(*) as cnt FROM violations").fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def get_daily_counts(self, days: int = 30) -> list[dict]:
        """
        Oxirgi N kun uchun kunlik buzilishlar soni.
        Returns: [{'date': '2024-01-15', 'count': 12}, ...]
        """
        result = []
        today = date.today()

        with self._lock:
            conn = self._get_conn()
            try:
                for i in range(days - 1, -1, -1):
                    d = today - timedelta(days=i)
                    ts_from = int(datetime.combine(d, datetime.min.time()).timestamp())
                    ts_to   = int(datetime.combine(d, datetime.max.time()).timestamp())
                    row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM violations WHERE timestamp BETWEEN ? AND ?",
                        (ts_from, ts_to)
                    ).fetchone()
                    result.append({
                        "date":  d.strftime("%m/%d"),
                        "count": row["cnt"] if row else 0
                    })
            finally:
                conn.close()

        return result

    def get_hourly_counts(self, target_date: date = None) -> list[dict]:
        """
        Berilgan kun uchun soatlik taqsimot.
        Returns: [{'hour': 8, 'count': 5}, ...]
        """
        if target_date is None:
            target_date = date.today()

        ts_from = int(datetime.combine(target_date, datetime.min.time()).timestamp())
        ts_to   = int(datetime.combine(target_date, datetime.max.time()).timestamp())

        result = []
        with self._lock:
            conn = self._get_conn()
            try:
                for hour in range(24):
                    h_from = ts_from + hour * 3600
                    h_to   = h_from  + 3599
                    h_to   = min(h_to, ts_to)
                    row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM violations WHERE timestamp BETWEEN ? AND ?",
                        (h_from, h_to)
                    ).fetchone()
                    result.append({"hour": hour, "count": row["cnt"] if row else 0})
            finally:
                conn.close()

        return result

    def get_weekly_counts(self, weeks: int = 8) -> list[dict]:
        """
        Oxirgi N hafta uchun haftalik buzilishlar soni.
        Returns: [{'week': 'W15', 'count': 47}, ...]
        """
        result = []
        today = date.today()

        with self._lock:
            conn = self._get_conn()
            try:
                for i in range(weeks - 1, -1, -1):
                    week_end   = today - timedelta(weeks=i)
                    week_start = week_end - timedelta(days=6)
                    ts_from = int(datetime.combine(week_start, datetime.min.time()).timestamp())
                    ts_to   = int(datetime.combine(week_end,   datetime.max.time()).timestamp())
                    row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM violations WHERE timestamp BETWEEN ? AND ?",
                        (ts_from, ts_to)
                    ).fetchone()
                    result.append({
                        "week":  f"W{week_end.isocalendar()[1]}",
                        "count": row["cnt"] if row else 0
                    })
            finally:
                conn.close()

        return result

    def cleanup_old(self, keep_days: int = 7):
        """keep_days kundan eski yozuvlarni o'chirish."""
        cutoff = int((datetime.now() - timedelta(days=keep_days)).timestamp())
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM violations WHERE timestamp < ?", (cutoff,))
                conn.commit()
            finally:
                conn.close()
