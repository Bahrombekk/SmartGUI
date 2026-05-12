from __future__ import annotations

from datetime import date, datetime, timedelta


class AnalyticsService:
    """Read-only analytics facade for UI pages."""

    def __init__(self, db, config_manager=None):
        self.db = db
        self.cfg = config_manager

    def summary_counts(
        self,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> dict:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = date(today.year, today.month, 1)

        def _ts(d: date, end: bool = False):
            t = datetime.max.time() if end else datetime.min.time()
            return int(datetime.combine(d, t).timestamp())

        kw = dict(camera_name=camera_name, department_id=department_id)
        return {
            "today": self.db.get_count_between(_ts(today), _ts(today, True), **kw),
            "week": self.db.get_count_between(_ts(week_start), _ts(today, True), **kw),
            "month": self.db.get_count_between(_ts(month_start), _ts(today, True), **kw),
            "total": self.db.get_violations_count(**kw),
        }

    def summary_with_delta(
        self,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> dict:
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=today.weekday())
        last_week_end = week_start - timedelta(days=1)
        last_week_start = week_start - timedelta(weeks=1)
        month_start = date(today.year, today.month, 1)
        last_month_end = month_start - timedelta(days=1)
        last_month_start = (
            date(month_start.year - 1, 12, 1)
            if month_start.month == 1
            else date(month_start.year, month_start.month - 1, 1)
        )

        def _ts(d: date, end: bool = False):
            t = datetime.max.time() if end else datetime.min.time()
            return int(datetime.combine(d, t).timestamp())

        kw = dict(camera_name=camera_name, department_id=department_id)

        def _cnt(d_from: date, d_to: date) -> int:
            return self.db.get_count_between(_ts(d_from), _ts(d_to, True), **kw)

        def _pct(cur: int, prev: int) -> float | None:
            return None if prev == 0 else round((cur - prev) / prev * 100, 1)

        today_n = _cnt(today, today)
        yesterday_n = _cnt(yesterday, yesterday)
        week_n = _cnt(week_start, today)
        last_week_n = _cnt(last_week_start, last_week_end)
        month_n = _cnt(month_start, today)
        last_month_n = _cnt(last_month_start, last_month_end)
        total_n = self.db.get_violations_count(**kw)

        return {
            "today": today_n,
            "today_delta": _pct(today_n, yesterday_n),
            "week": week_n,
            "week_delta": _pct(week_n, last_week_n),
            "month": month_n,
            "month_delta": _pct(month_n, last_month_n),
            "total": total_n,
        }

    def daily_counts(
        self,
        days: int = 30,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> list[dict]:
        return self.db.get_daily_counts(days=days, camera_name=camera_name, department_id=department_id)

    def weekly_counts(
        self,
        weeks: int = 8,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> list[dict]:
        return self.db.get_weekly_counts(weeks=weeks, camera_name=camera_name, department_id=department_id)

    def hourly_counts(
        self,
        target_date: date | None = None,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> list[dict]:
        if camera_name is None and department_id is None:
            return self.db.get_hourly_counts(target_date=target_date or date.today())
        return self.db.get_hourly_counts_filtered(
            target_date=target_date or date.today(),
            camera_name=camera_name,
            department_id=department_id,
        )

    def camera_ranking(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 6,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> list[dict]:
        rows = self.db.get_group_counts(
            "camera_name",
            date_from=date_from,
            date_to=date_to,
            camera_name=camera_name,
            department_id=department_id,
            limit=limit,
        )
        return [
            {"camera_name": str(row.get("key") or "Unknown"), "count": int(row.get("count", 0) or 0)}
            for row in rows
        ]

    def department_breakdown(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> list[dict]:
        rows = self.db.get_group_counts(
            "camera_name",
            date_from=date_from,
            date_to=date_to,
            camera_name=camera_name,
            department_id=department_id,
            limit=50,
        )
        departments = self.cfg.get_departments() if self.cfg else []
        cameras = self.cfg.get_cameras() if self.cfg else []
        dep_names = {dep.get("id"): dep.get("name", "Bo'lim") for dep in departments}
        camera_to_dep = {
            str(cam.get("name") or ""): dep_names.get(cam.get("department_id"), "Bo'limsiz")
            for cam in cameras
        }
        counts: dict[str, int] = {}
        for row in rows:
            name = camera_to_dep.get(str(row.get("key") or ""), "Bo'limsiz")
            counts[name] = counts.get(name, 0) + int(row.get("count", 0) or 0)
        return [
            {"department": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]

    def violation_type_breakdown(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> list[dict]:
        rows = self.db.get_group_counts(
            "violation_type",
            date_from=date_from,
            date_to=date_to,
            camera_name=camera_name,
            department_id=department_id,
            limit=5,
        )
        labels = {
            "no_helmet": "No Helmet",
            "access_denied": "Access Denied",
            "unknown_person": "Unknown Worker",
            "low_confidence": "Low Confidence",
        }
        result = []
        for row in rows:
            key = str(row.get("key") or "no_helmet")
            result.append({
                "type": key,
                "label": labels.get(key, key.replace("_", " ").title()),
                "count": int(row.get("count", 0) or 0),
            })
        return result or [{"type": "no_helmet", "label": "No Helmet", "count": 0}]

    def peak_insights(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        camera_name: str | None = None,
        department_id: int | None = None,
    ) -> dict:
        peak = self.db.get_peak_hour(
            date_from=date_from,
            date_to=date_to,
            camera_name=camera_name,
            department_id=department_id,
        )
        cam_rows = self.camera_ranking(
            date_from=date_from,
            date_to=date_to,
            limit=1,
            camera_name=camera_name,
            department_id=department_id,
        )
        dep_rows = self.department_breakdown(
            date_from=date_from,
            date_to=date_to,
            camera_name=camera_name,
            department_id=department_id,
        )
        total = self.db.get_violations_count(
            date_from=date_from,
            date_to=date_to,
            camera_name=camera_name,
            department_id=department_id,
        )
        return {
            "peak_hour": int(peak.get("hour", 14) or 14),
            "peak_hour_count": int(peak.get("count", 0) or 0),
            "top_camera": cam_rows[0]["camera_name"] if cam_rows else "-",
            "top_camera_count": cam_rows[0]["count"] if cam_rows else 0,
            "top_dept": dep_rows[0]["department"] if dep_rows else "-",
            "total_in_range": total,
        }

    @staticmethod
    def format_range_status(count: int, date_from: date, date_to: date) -> str:
        return f"{count} ta buzilish ({date_from:%d.%m.%Y} - {date_to:%d.%m.%Y})"
