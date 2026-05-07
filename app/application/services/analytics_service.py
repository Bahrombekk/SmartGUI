from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta


class AnalyticsService:
    """Read-only analytics facade for UI pages."""

    def __init__(self, db, config_manager=None):
        self.db = db
        self.cfg = config_manager

    # ── summary ───────────────────────────────────────────────────────────────

    def summary_counts(self) -> dict:
        today = date.today()
        week_start  = today - timedelta(days=today.weekday())
        month_start = date(today.year, today.month, 1)
        def _ts(d: date, end: bool = False):
            t = datetime.max.time() if end else datetime.min.time()
            return int(datetime.combine(d, t).timestamp())
        return {
            "today": self.db.get_today_count(),
            "week":  self.db.get_count_between(_ts(week_start),  _ts(today, end=True)),
            "month": self.db.get_count_between(_ts(month_start), _ts(today, end=True)),
            "total": self.db.get_total_count(),
        }

    def summary_with_delta(self) -> dict:
        """Returns KPI counts + real % change vs the prior equivalent period."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=today.weekday())
        last_week_end = week_start - timedelta(days=1)
        last_week_start = week_start - timedelta(weeks=1)
        month_start = date(today.year, today.month, 1)
        last_month_end = month_start - timedelta(days=1)
        if month_start.month == 1:
            last_month_start = date(month_start.year - 1, 12, 1)
        else:
            last_month_start = date(month_start.year, month_start.month - 1, 1)

        def _count(d_from: date, d_to: date) -> int:
            return len(self.db.get_violations(date_from=d_from, date_to=d_to, limit=10000))

        def _pct(cur: int, prev: int) -> float | None:
            return None if prev == 0 else round((cur - prev) / prev * 100, 1)

        today_n = _count(today, today)
        yesterday_n = _count(yesterday, yesterday)
        week_n = _count(week_start, today)
        last_week_n = _count(last_week_start, last_week_end)
        month_n = _count(month_start, today)
        last_month_n = _count(last_month_start, last_month_end)

        return {
            "today":       today_n,
            "today_delta": _pct(today_n, yesterday_n),
            "week":        week_n,
            "week_delta":  _pct(week_n, last_week_n),
            "month":       month_n,
            "month_delta": _pct(month_n, last_month_n),
            "total":       self.db.get_total_count(),
        }

    # ── time-series ───────────────────────────────────────────────────────────

    def daily_counts(self, days: int = 30) -> list[dict]:
        return self.db.get_daily_counts(days=days)

    def weekly_counts(self, weeks: int = 8) -> list[dict]:
        return self.db.get_weekly_counts(weeks=weeks)

    def hourly_counts(self, target_date: date | None = None) -> list[dict]:
        return self.db.get_hourly_counts(target_date=target_date or date.today())

    # ── breakdowns ────────────────────────────────────────────────────────────

    def camera_ranking(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 6,
    ) -> list[dict]:
        rows = self.db.get_violations(date_from=date_from, date_to=date_to, limit=10000)
        counts = Counter(str(v.get("camera_name") or "Unknown") for v in rows)
        return [
            {"camera_name": name, "count": cnt}
            for name, cnt in counts.most_common(limit)
        ]

    def department_breakdown(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict]:
        rows = self.db.get_violations(date_from=date_from, date_to=date_to, limit=10000)
        camera_counts = Counter(str(v.get("camera_name") or "Unknown") for v in rows)
        departments = self.cfg.get_departments() if self.cfg else []
        cameras = self.cfg.get_cameras() if self.cfg else []
        dep_names = {dep.get("id"): dep.get("name", "Bo'lim") for dep in departments}
        camera_to_dep = {
            str(cam.get("name") or ""): dep_names.get(cam.get("department_id"), "Bo'limsiz")
            for cam in cameras
        }
        dep_counts: Counter = Counter()
        for cam_name, cnt in camera_counts.items():
            dep_counts[camera_to_dep.get(cam_name, "Bo'limsiz")] += cnt
        return [{"department": name, "count": cnt} for name, cnt in dep_counts.most_common()]

    def violation_type_breakdown(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict]:
        """Returns top-5 violation types with labels for the given date range."""
        rows = self.db.get_violations(date_from=date_from, date_to=date_to, limit=10000)
        counts = Counter(str(r.get("violation_type") or "no_helmet") for r in rows)
        _labels = {
            "no_helmet":      "No Helmet",
            "access_denied":  "Access Denied",
            "unknown_person": "Unknown Worker",
            "low_confidence": "Low Confidence",
        }
        result = [
            {
                "type":  k,
                "label": _labels.get(k, k.replace("_", " ").title()),
                "count": v,
            }
            for k, v in counts.most_common(5)
        ]
        return result or [{"type": "no_helmet", "label": "No Helmet", "count": 0}]

    def peak_insights(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """Returns peak hour, top camera, top department for the given range."""
        rows = self.db.get_violations(date_from=date_from, date_to=date_to, limit=10000)

        hour_counts: Counter = Counter()
        cam_counts:  Counter = Counter()
        for r in rows:
            ts = r.get("timestamp") or 0
            if ts:
                hour_counts[datetime.fromtimestamp(ts).hour] += 1
            cam_counts[str(r.get("camera_name") or "Unknown")] += 1

        # Bo'lim statistikasi — mavjud rows dan hisoblash (qayta query yo'q)
        departments = self.cfg.get_departments() if self.cfg else []
        cameras     = self.cfg.get_cameras()     if self.cfg else []
        dep_names   = {dep.get("id"): dep.get("name", "Bo'lim") for dep in departments}
        cam_to_dep  = {
            str(cam.get("name") or ""): dep_names.get(cam.get("department_id"), "Bo'limsiz")
            for cam in cameras
        }
        dep_counts: Counter = Counter()
        for cam_name, cnt in cam_counts.items():
            dep_counts[cam_to_dep.get(cam_name, "Bo'limsiz")] += cnt

        peak_h,   peak_h_cnt  = hour_counts.most_common(1)[0] if hour_counts else (14, 0)
        top_cam,  top_cam_cnt = cam_counts.most_common(1)[0]  if cam_counts  else ("—", 0)
        top_dept  = dep_counts.most_common(1)[0][0]           if dep_counts  else "—"

        return {
            "peak_hour":        peak_h,
            "peak_hour_count":  peak_h_cnt,
            "top_camera":       top_cam,
            "top_camera_count": top_cam_cnt,
            "top_dept":         top_dept,
            "total_in_range":   len(rows),
        }

    @staticmethod
    def format_range_status(count: int, date_from: date, date_to: date) -> str:
        return f"{count} ta buzilish ({date_from:%d.%m.%Y} - {date_to:%d.%m.%Y})"
