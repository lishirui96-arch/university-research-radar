from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class TrendPeriod:
    start: pd.Timestamp
    end: pd.Timestamp
    comparison_start: pd.Timestamp | None
    comparison_end: pd.Timestamp | None
    label: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _weekly_periods(window_start: pd.Timestamp, window_end: pd.Timestamp) -> list[TrendPeriod]:
    periods: list[TrendPeriod] = []
    period_end = window_end
    while period_end >= window_start:
        period_start = max(window_start, period_end - pd.Timedelta(days=6))
        days = (period_end - period_start).days + 1
        comparison_end = period_start - pd.Timedelta(days=1)
        comparison_start = comparison_end - pd.Timedelta(days=days - 1)
        periods.append(
            TrendPeriod(
                period_start,
                period_end,
                comparison_start,
                comparison_end,
                f"{period_start:%Y-%m-%d} 至 {period_end:%Y-%m-%d}",
            )
        )
        period_end = period_start - pd.Timedelta(days=1)
    return list(reversed(periods))


def _same_day_previous_month(value: pd.Timestamp) -> pd.Timestamp | None:
    previous_month = value - pd.DateOffset(months=1)
    last_day = calendar.monthrange(previous_month.year, previous_month.month)[1]
    if value.day > last_day:
        return None
    return pd.Timestamp(previous_month.year, previous_month.month, value.day)


def _monthly_periods(window_start: pd.Timestamp, window_end: pd.Timestamp) -> list[TrendPeriod]:
    periods: list[TrendPeriod] = []
    for month_start in pd.date_range(
        window_start.to_period("M").start_time,
        window_end.to_period("M").start_time,
        freq="MS",
    ):
        month_end = month_start + pd.offsets.MonthEnd(0)
        period_start = max(window_start, month_start)
        period_end = min(window_end, month_end)
        is_complete_month = period_start == month_start and period_end == month_end
        if is_complete_month:
            comparison_end = month_start - pd.Timedelta(days=1)
            comparison_start = comparison_end.to_period("M").start_time
        else:
            comparison_start = _same_day_previous_month(period_start)
            comparison_end = _same_day_previous_month(period_end)
            if (
                comparison_start is None
                or comparison_end is None
                or (comparison_end - comparison_start).days
                != (period_end - period_start).days
            ):
                comparison_start = None
                comparison_end = None
        periods.append(
            TrendPeriod(
                period_start,
                period_end,
                comparison_start,
                comparison_end,
                f"{month_start:%Y-%m}",
            )
        )
    return periods


def _range_total(
    indexed: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> tuple[int | None, str]:
    if start is None or end is None:
        return None, "unavailable"
    expected_dates = pd.date_range(start, end, freq="D")
    rows = indexed.reindex(expected_dates)
    counts = pd.to_numeric(rows["daily_works_count"], errors="coerce")
    valid = counts.notna()
    if "query_status" in rows:
        valid &= rows["query_status"].eq("success")
    if not bool(valid.all()):
        return None, "missing"
    return int(counts.sum()), "success"


def aggregate_topic_trends(
    daily: pd.DataFrame,
    period_days: int,
    window_start: str | pd.Timestamp,
    window_end: str | pd.Timestamp,
) -> pd.DataFrame:
    """Aggregate published daily Topic counts for the dashboard trend charts."""
    if period_days not in {90, 360}:
        raise ValueError("period_days must be 90 or 360")
    if daily.empty:
        return pd.DataFrame()

    start = pd.Timestamp(window_start).normalize()
    end = pd.Timestamp(window_end).normalize()
    if start > end:
        raise ValueError("window_start must not be after window_end")
    periods = _weekly_periods(start, end) if period_days == 90 else _monthly_periods(start, end)

    source = daily.copy()
    source["date"] = pd.to_datetime(source["date"]).dt.normalize()
    metadata_columns = [
        column
        for column in (
            "topic_id", "topic_name", "topic_name_zh", "subfield_id",
            "subfield_name", "field_id", "field_name", "field_name_zh",
        )
        if column in source.columns
    ]
    records: list[dict[str, Any]] = []
    for topic_id, topic_rows in source.groupby("topic_id", sort=False):
        metadata = topic_rows.iloc[0][metadata_columns].to_dict()
        indexed = topic_rows.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        for period in periods:
            works, query_status = _range_total(indexed, period.start, period.end)
            previous_works, comparison_status = _range_total(
                indexed, period.comparison_start, period.comparison_end
            )
            growth_rate: float | None = None
            growth_status = comparison_status
            if query_status != "success":
                growth_status = "missing_current"
            elif previous_works == 0:
                growth_status = "zero_baseline"
            elif previous_works is not None:
                growth_rate = (works - previous_works) / previous_works
                growth_status = "success"
            records.append(
                {
                    **metadata,
                    "date": period.end,
                    "period_label": period.label,
                    "period_start": period.start,
                    "period_end": period.end,
                    "period_days": period.days,
                    "period_works_count": works,
                    "query_status": query_status,
                    "comparison_start": period.comparison_start,
                    "comparison_end": period.comparison_end,
                    "comparison_works_count": previous_works,
                    "growth_rate": growth_rate,
                    "growth_status": growth_status,
                }
            )

    result = pd.DataFrame.from_records(records)
    for column in ("period_works_count", "comparison_works_count"):
        result[column] = pd.array(result[column], dtype="Int64")
    result["growth_rate"] = pd.array(result["growth_rate"], dtype="Float64")
    return result


def diagnose_topic_trends(
    daily: pd.DataFrame,
    trend: pd.DataFrame,
    selected_ids: list[str],
    field_id: str | None,
    field_topic_count: int,
) -> dict[str, Any]:
    selected = {str(topic_id) for topic_id in selected_ids}
    trend_ids = (
        set(trend["topic_id"].astype(str)) if not trend.empty else set()
    )
    matched = selected & trend_ids
    selected_daily = (
        daily[daily["topic_id"].astype(str).isin(selected)]
        if not daily.empty else pd.DataFrame()
    )
    selected_trend = (
        trend[trend["topic_id"].astype(str).isin(selected)]
        if not trend.empty else pd.DataFrame()
    )
    points = (
        selected_trend.groupby("topic_id")["date"].nunique().astype(int).to_dict()
        if not selected_trend.empty else {}
    )
    return {
        "field_id": field_id,
        "field_topic_count": int(field_topic_count),
        "selected_topic_ids": list(selected_ids),
        "daily_record_count": len(selected_daily),
        "aggregated_record_count": len(selected_trend),
        "non_null_works_count": (
            int(selected_trend["period_works_count"].notna().sum())
            if not selected_trend.empty else 0
        ),
        "non_null_growth_count": (
            int(selected_trend["growth_rate"].notna().sum())
            if not selected_trend.empty else 0
        ),
        "matched_topic_count": len(matched),
        "unmatched_topic_ids": sorted(selected - matched),
        "points_per_topic": {str(key): value for key, value in points.items()},
    }
