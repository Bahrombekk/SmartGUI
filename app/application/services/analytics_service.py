from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta


class AnalyticsService:
    """Read-only analytics facade for UI pages."""

    def __init__(self, db, config_manager=None):
        self.db = db
        self.cfg = config_manager

    def summary_counts(self) -> dict:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = date(today.year, today.month, 1)
        return {
            "today": len(self.db.get_violations(date_from=today, date_to=today, limit=10000)),
            "week": len(self.db.get_violations(date_from=week_start, date_to=today, limit=10000)),
            "month": len(self.db.get_violations(date_from=month_start, date_to=today, limit=10000)),
            "total": self.db.get_total_count(),
        }

    def daily_counts(self, days: int = 30) -> list[dict]:
        return self.db.get_daily_counts(days=days)

    def weekly_counts(self, weeks: int = 8) -> list[dict]:
        return self.db.get_weekly_counts(weeks=weeks)

    def hourly_counts(self, target_date: date | None = None) -> list[dict]:
        return self.db.get_hourly_counts(target_date=target_date or date.today())

    def camera_ranking(self, date_from: date | None = None, date_to: date | None = None, limit: int = 6) -> list[dict]:
        rows = self.db.get_violations(date_from=date_from, date_to=date_to, limit=10000)
        counts = Counter(str(v.get("camera_name") or "Unknown") for v in rows)
        return [{"camera_name": name, "count": count} for name, count in counts.most_common(limit)]

    def department_breakdown(self, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
        rows = self.db.get_violations(date_from=date_from, date_to=date_to, limit=10000)
        camera_counts = Counter(str(v.get("camera_name") or "Unknown") for v in rows)
        departments = self.cfg.get_departments() if self.cfg else []
        cameras = self.cfg.get_cameras() if self.cfg else []
        dep_names = {dep.get("id"): dep.get("name", "Bo'lim") for dep in departments}
        camera_to_dep = {
            str(cam.get("name") or ""): dep_names.get(cam.get("department_id"), "Bo'limsiz")
            for cam in cameras
        }
        dep_counts = Counter()
        for camera_name, count in camera_counts.items():
            dep_counts[camera_to_dep.get(camera_name, "Bo'limsiz")] += count
        return [{"department": name, "count": count} for name, count in dep_counts.most_common()]

    @staticmethod
    def format_range_status(count: int, date_from: date, date_to: date) -> str:
        return f"{count} ta buzilish ({date_from:%d.%m.%Y} - {date_to:%d.%m.%Y})"
