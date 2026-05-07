"""
SQLite ma'lumotlar bazasi — buzilishlar jurnali.

Thread-local ulanishlar: har thread o'z connection'iga ega.
WAL mode: bir vaqtda ko'p o'qish + 1 yozish (Python lock kutilmaydi).
"""

import sqlite3
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
import json


DB_FILE = "smartgui.db"


class ViolationsDB:
    """Buzilishlar (violations) jurnalini SQLite da boshqarish."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._write_lock = threading.Lock()   # Faqat yozish uchun
        self._local = threading.local()        # Thread-local ulanishlar
        self._init_db()

    # ── Ulanish ────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        """
        Thread-local persistent connection.
        Har thread o'z ulanishini bir marta yaratadi va qayta ishlatadi.
        WAL mode: o'qish operatsiyalari lock kutmaydi.
        """
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=4000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA busy_timeout=3000")  # 3s kutib turadi, error emas
            self._local.conn = conn
        return conn

    def close_current_thread(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def _init_db(self):
        """Jadvallarni yaratish (mavjud bo'lmasa)."""
        with self._write_lock:
            conn = self._conn()
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
            self._ensure_column(conn, "violations", "violation_type", "TEXT DEFAULT 'no_helmet'")
            self._ensure_column(conn, "violations", "camera_id", "INTEGER")
            self._ensure_column(conn, "violations", "department_id", "INTEGER")
            self._ensure_column(conn, "violations", "employee_id", "TEXT")
            self._ensure_column(conn, "violations", "employee_name", "TEXT DEFAULT ''")
            self._ensure_column(conn, "violations", "identity_confidence", "REAL DEFAULT 0.0")
            self._ensure_column(conn, "violations", "sync_status", "TEXT DEFAULT 'queued'")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_violations_timestamp
                ON violations (timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_violations_camera_time
                ON violations (camera_name, timestamp)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id     TEXT NOT NULL UNIQUE,
                    first_name      TEXT DEFAULT '',
                    last_name       TEXT DEFAULT '',
                    department_id   INTEGER,
                    photo_path      TEXT DEFAULT '',
                    active          INTEGER DEFAULT 1,
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS face_embeddings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id     TEXT NOT NULL,
                    model_version   TEXT NOT NULL,
                    embedding       BLOB NOT NULL,
                    created_at      INTEGER NOT NULL,
                    UNIQUE(employee_id, model_version)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cameras (
                    id              INTEGER PRIMARY KEY,
                    name            TEXT NOT NULL,
                    rtsp_url        TEXT DEFAULT '',
                    company_id      TEXT DEFAULT '',
                    department_id   INTEGER,
                    enabled         INTEGER DEFAULT 1,
                    access_mode     TEXT DEFAULT 'department',
                    allowed_department_ids TEXT DEFAULT '[]',
                    allowed_employee_ids   TEXT DEFAULT '[]',
                    polygon_points  TEXT DEFAULT '[]',
                    updated_at      INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_jobs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel         TEXT NOT NULL,
                    payload         TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    retry_count     INTEGER NOT NULL DEFAULT 0,
                    last_error      TEXT DEFAULT '',
                    created_at      INTEGER NOT NULL,
                    updated_at      INTEGER NOT NULL,
                    sent_at         INTEGER
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_jobs_status
                ON notification_jobs (status, created_at)
            """)
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str):
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # ── Yozish (write lock kerak) ──────────────────────────────────────────

    def add_violation(
        self,
        track_id: int,
        crop_path: str = "",
        full_path: str = "",
        camera_name: str = "",
        confidence: float = 0.0,
        timestamp: int = 0,
        violation_type: str = "no_helmet",
        camera_id: int | None = None,
        department_id: int | None = None,
        employee_id: str | None = None,
        employee_name: str = "",
        identity_confidence: float = 0.0,
        sync_status: str = "queued",
    ) -> int:
        """Yangi buzilish yozuvi qo'shish. Yangi record ID qaytaradi."""
        if not timestamp:
            timestamp = int(datetime.now().timestamp())
        created_at = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        with self._write_lock:
            conn = self._conn()
            cur = conn.execute("""
                INSERT INTO violations
                    (timestamp, track_id, crop_path, full_path,
                     camera_name, confidence, created_at, violation_type,
                     camera_id, department_id, employee_id, employee_name,
                     identity_confidence, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, track_id, crop_path, full_path,
                  camera_name, confidence, created_at, violation_type,
                  camera_id, department_id, employee_id, employee_name,
                  identity_confidence, sync_status))
            conn.commit()
            return cur.lastrowid

    def add_notification_job(self, channel: str, payload: dict) -> int:
        now = int(datetime.now().timestamp())
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute("""
                INSERT INTO notification_jobs
                    (channel, payload, status, retry_count, last_error, created_at, updated_at)
                VALUES (?, ?, 'pending', 0, '', ?, ?)
            """, (channel, json.dumps(payload, ensure_ascii=False), now, now))
            conn.commit()
            return cur.lastrowid

    def update_notification_job(self, job_id: int, **kwargs) -> None:
        allowed = {"status", "last_error", "sent_at"}
        data = {k: v for k, v in kwargs.items() if k in allowed}
        if not data:
            return
        data["updated_at"] = int(datetime.now().timestamp())
        assignments = ", ".join(f"{key}=?" for key in data)
        with self._write_lock:
            conn = self._conn()
            conn.execute(
                f"UPDATE notification_jobs SET {assignments} WHERE id=?",
                [*data.values(), job_id],
            )
            conn.commit()

    def increment_notification_retry(self, job_id: int, last_error: str) -> None:
        now = int(datetime.now().timestamp())
        with self._write_lock:
            conn = self._conn()
            conn.execute("""
                UPDATE notification_jobs
                SET status='pending',
                    retry_count=retry_count + 1,
                    last_error=?,
                    updated_at=?
                WHERE id=?
            """, (last_error, now, job_id))
            conn.commit()

    def get_pending_notification_jobs(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("""
            SELECT * FROM notification_jobs
            WHERE status='pending'
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def upsert_employee(
        self,
        *,
        employee_id: str,
        first_name: str = "",
        last_name: str = "",
        photo_path: str = "",
        department_id: int | None = None,
        active: bool = True,
    ) -> None:
        now = int(datetime.now().timestamp())
        with self._write_lock:
            conn = self._conn()
            conn.execute("""
                INSERT INTO employees
                    (employee_id, first_name, last_name, department_id, photo_path,
                     active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employee_id) DO UPDATE SET
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    department_id=excluded.department_id,
                    photo_path=excluded.photo_path,
                    active=excluded.active,
                    updated_at=excluded.updated_at
            """, (employee_id, first_name, last_name, department_id, photo_path,
                  1 if active else 0, now, now))
            conn.commit()

    def get_employee_by_employee_id(self, employee_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM employees WHERE employee_id=?",
            (employee_id,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_face_embedding(
        self,
        *,
        employee_id: str,
        model_version: str,
        embedding: bytes,
        created_at: int,
    ) -> None:
        with self._write_lock:
            conn = self._conn()
            conn.execute("""
                INSERT INTO face_embeddings (employee_id, model_version, embedding, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(employee_id, model_version) DO UPDATE SET
                    embedding=excluded.embedding,
                    created_at=excluded.created_at
            """, (employee_id, model_version, embedding, created_at))
            conn.commit()

    def get_face_embedding(self, employee_id: str, model_version: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("""
            SELECT * FROM face_embeddings
            WHERE employee_id=? AND model_version=?
        """, (employee_id, model_version)).fetchone()
        return dict(row) if row else None

    def get_face_embeddings(self, model_version: str) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("""
            SELECT * FROM face_embeddings
            WHERE model_version=?
        """, (model_version,)).fetchall()
        return [dict(r) for r in rows]

    def upsert_camera(self, camera: dict) -> None:
        now = int(datetime.now().timestamp())
        with self._write_lock:
            conn = self._conn()
            conn.execute("""
                INSERT INTO cameras
                    (id, name, rtsp_url, company_id, department_id, enabled, access_mode,
                     allowed_department_ids, allowed_employee_ids, polygon_points, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    rtsp_url=excluded.rtsp_url,
                    company_id=excluded.company_id,
                    department_id=excluded.department_id,
                    enabled=excluded.enabled,
                    access_mode=excluded.access_mode,
                    allowed_department_ids=excluded.allowed_department_ids,
                    allowed_employee_ids=excluded.allowed_employee_ids,
                    polygon_points=excluded.polygon_points,
                    updated_at=excluded.updated_at
            """, (
                camera.get("id"),
                camera.get("name", "Camera"),
                camera.get("rtsp_url", ""),
                camera.get("company_id", ""),
                camera.get("department_id"),
                1 if camera.get("enabled", True) else 0,
                camera.get("access_mode", "department"),
                json.dumps(camera.get("allowed_department_ids", []), ensure_ascii=False),
                json.dumps(camera.get("allowed_employee_ids", []), ensure_ascii=False),
                json.dumps(camera.get("polygon_points", []), ensure_ascii=False),
                now,
            ))
            conn.commit()

    def cleanup_old(self, keep_days: int = 7):
        """keep_days kundan eski yozuvlarni o'chirish."""
        cutoff = int((datetime.now() - timedelta(days=keep_days)).timestamp())
        with self._write_lock:
            conn = self._conn()
            conn.execute("DELETE FROM violations WHERE timestamp < ?", (cutoff,))
            conn.commit()

    # ── O'qish (lock shart emas — WAL mode) ───────────────────────────────

    def get_violations(
        self,
        date_from: date = None,
        date_to: date = None,
        limit: int = 500,
        offset: int = 0,
        camera_name: str | None = None,
        violation_type: str | None = None,
    ) -> list[dict]:
        """
        Buzilishlarni filtrlangan holda olish.
        Lock kutilmaydi — WAL mode bir vaqtda ko'p o'qishga ruxsat beradi.
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

        if camera_name:
            conditions.append("camera_name = ?")
            params.append(camera_name)

        if violation_type:
            conditions.append("violation_type = ?")
            params.append(violation_type)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params += [limit, offset]

        conn = self._conn()
        rows = conn.execute(f"""
            SELECT * FROM violations
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, params).fetchall()
        return [dict(r) for r in rows]

    def get_today_count(self) -> int:
        """Bugungi buzilishlar soni. Lock kutilmaydi."""
        today = date.today()
        ts_from = int(datetime.combine(today, datetime.min.time()).timestamp())
        ts_to   = int(datetime.combine(today, datetime.max.time()).timestamp())
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM violations WHERE timestamp BETWEEN ? AND ?",
            (ts_from, ts_to)
        ).fetchone()
        return row["cnt"] if row else 0

    def get_total_count(self) -> int:
        """Jami buzilishlar soni."""
        conn = self._conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM violations").fetchone()
        return row["cnt"] if row else 0

    def get_count_between(self, ts_from: int, ts_to: int) -> int:
        """Berilgan timestamp oralig'idagi buzilishlar soni."""
        conn = self._conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM violations WHERE timestamp BETWEEN ? AND ?",
            (ts_from, ts_to)
        ).fetchone()
        return row["cnt"] if row else 0

    def get_daily_counts(self, days: int = 30) -> list[dict]:
        """Oxirgi N kun uchun kunlik buzilishlar soni. 1 ta GROUP BY query."""
        today = date.today()
        cutoff = today - timedelta(days=days - 1)
        ts_from = int(datetime.combine(cutoff, datetime.min.time()).timestamp())
        ts_to   = int(datetime.combine(today, datetime.max.time()).timestamp())
        conn = self._conn()
        rows = conn.execute("""
            SELECT date(timestamp, 'unixepoch', 'localtime') AS day, COUNT(*) AS cnt
            FROM violations
            WHERE timestamp BETWEEN ? AND ?
            GROUP BY day
        """, (ts_from, ts_to)).fetchall()
        raw = {row["day"]: row["cnt"] for row in rows}
        return [
            {"date": (today - timedelta(days=i)).strftime("%m/%d"),
             "count": raw.get((today - timedelta(days=i)).strftime("%Y-%m-%d"), 0)}
            for i in range(days - 1, -1, -1)
        ]

    def get_hourly_counts(self, target_date: date = None) -> list[dict]:
        """Berilgan kun uchun soatlik taqsimot. 1 ta GROUP BY query."""
        if target_date is None:
            target_date = date.today()
        ts_from = int(datetime.combine(target_date, datetime.min.time()).timestamp())
        ts_to   = int(datetime.combine(target_date, datetime.max.time()).timestamp())
        conn = self._conn()
        rows = conn.execute("""
            SELECT CAST(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS INTEGER) AS hour,
                   COUNT(*) AS cnt
            FROM violations
            WHERE timestamp BETWEEN ? AND ?
            GROUP BY hour
        """, (ts_from, ts_to)).fetchall()
        raw = {row["hour"]: row["cnt"] for row in rows}
        return [{"hour": h, "count": raw.get(h, 0)} for h in range(24)]

    def get_weekly_counts(self, weeks: int = 8) -> list[dict]:
        """Oxirgi N hafta uchun haftalik buzilishlar soni."""
        today = date.today()
        result = []
        for i in range(weeks - 1, -1, -1):
            week_end   = today - timedelta(weeks=i)
            week_start = week_end - timedelta(days=6)
            ts_from = int(datetime.combine(week_start, datetime.min.time()).timestamp())
            ts_to   = int(datetime.combine(week_end,   datetime.max.time()).timestamp())
            result.append({
                "week":  f"W{week_end.isocalendar()[1]}",
                "count": self.get_count_between(ts_from, ts_to),
            })
        return result
