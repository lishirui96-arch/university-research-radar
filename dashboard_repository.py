from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from trend_aggregation import aggregate_topic_trends


ENTITY_TABLES = (
    "works",
    "authors",
    "institutions",
    "topics",
    "work_authorships",
    "work_authorship_institutions",
    "work_topics",
    "research_groups",
    "research_group_evidence",
    "topic_snapshots",
    "institution_snapshots",
    "author_snapshots",
)

TREND_CATEGORY_IDS = (
    "robotics_embodied",
    "ai_chip_packaging",
    "new_energy_storage",
    "advanced_materials",
    "bio_manufacturing",
)

V14_TAXONOMY_VERSION = "openalex-taxonomy-2026-11-18-v1.4"
V14_FIELD_IDS = ("15", "16", "17", "21", "22", "25")
V15_REGION_CODES = ("CN", "US")


def _connect_read_only(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path).resolve()
    connection = sqlite3.connect(
        f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=10
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _dataframe(rows: list[sqlite3.Row]) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows])


def load_dashboard_data(path: str | Path) -> dict[str, Any]:
    db_path = Path(path)
    empty = {
        "database_available": False,
        "coverage_status": "unavailable",
        "coverage_message": "本地数据库尚未建立。",
        "as_of_date": None,
        "last_success_at": None,
        "counts": {},
        "kpis": {},
        "trend": pd.DataFrame(),
        "topics": pd.DataFrame(),
        "global_institutions": pd.DataFrame(),
        "china_institutions": pd.DataFrame(),
        "works": pd.DataFrame(),
        "alerts": pd.DataFrame(),
        "countries": [],
    }
    if not db_path.exists():
        return empty

    with closing(_connect_read_only(db_path)) as connection:
        tables = _table_names(connection)
        counts = {
            table: _table_count(connection, table)
            for table in ENTITY_TABLES
            if table in tables
        }
        run = None
        if "scan_runs" in tables:
            run = connection.execute(
                """
                SELECT run_id, completed_at, updated_at
                FROM scan_runs
                WHERE status='success'
                ORDER BY COALESCE(completed_at, updated_at) DESC
                LIMIT 1
                """
            ).fetchone()

        latest_snapshot = None
        if "topic_snapshots" in tables:
            latest_snapshot = connection.execute(
                "SELECT MAX(snapshot_date) FROM topic_snapshots"
            ).fetchone()[0]

        countries: list[str] = []
        if "institutions" in tables:
            countries = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT DISTINCT country_code FROM institutions
                    WHERE country_code IS NOT NULL AND TRIM(country_code) <> ''
                    ORDER BY country_code
                    """
                ).fetchall()
            ]

        kpis = _load_kpis(connection, tables)
        trend = _load_global_trend(connection, tables)
        topics = _load_topic_ranking(connection, tables)
        global_institutions, china_institutions = _load_institution_rankings(
            connection, tables
        )
        works = _load_recent_works(connection, tables)
        alerts = _load_alerts(connection, tables)

    global_ready = "snapshot_batches" in tables and "global_metric_snapshots" in tables
    if global_ready and not trend.empty:
        coverage_status = "partial"
        coverage_message = "已读取全球聚合快照；每项指标仍以其计数口径为准。"
    else:
        coverage_status = "unavailable"
        coverage_message = (
            "尚未建立全球全学科采集批次。当前页面只展示本地已保存证据，"
            "缺失指标不会用示例数据补齐。"
        )

    return {
        "database_available": True,
        "coverage_status": coverage_status,
        "coverage_message": coverage_message,
        "as_of_date": latest_snapshot,
        "last_success_at": dict(run) if run else None,
        "counts": counts,
        "kpis": kpis,
        "trend": trend,
        "topics": topics,
        "global_institutions": global_institutions,
        "china_institutions": china_institutions,
        "works": works,
        "alerts": alerts,
        "countries": countries,
    }


def _load_kpis(
    connection: sqlite3.Connection, tables: set[str]
) -> dict[str, dict[str, Any]]:
    unavailable = {
        "value": None,
        "delta": None,
        "scope": "unavailable",
        "detail": "尚无可用于该指标的完整统计批次。",
    }
    result = {
        "works": dict(unavailable),
        "institutions": dict(unavailable),
        "topics": dict(unavailable),
        "groups": dict(unavailable),
    }
    cutoff = (date.today() - timedelta(days=29)).isoformat()

    if "works" in tables and _table_count(connection, "works"):
        recent = int(
            connection.execute(
                "SELECT COUNT(DISTINCT openalex_work_id) FROM works WHERE publication_date>=?",
                (cutoff,),
            ).fetchone()[0]
        )
        result["works"] = {
            "value": recent,
            "delta": None,
            "scope": "sample",
            "detail": "本地样本中的 OpenAlex 记录数；尚未建立作品家族去重。",
        }

    required = {"works", "work_authorships", "work_authorship_institutions"}
    if required.issubset(tables) and _table_count(connection, "works"):
        count = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT wai.institution_id)
                FROM works w
                JOIN work_authorships wa ON wa.work_id=w.openalex_work_id
                JOIN work_authorship_institutions wai ON wai.authorship_id=wa.authorship_id
                WHERE w.publication_date>=?
                """,
                (cutoff,),
            ).fetchone()[0]
        )
        result["institutions"] = {
            "value": count,
            "delta": None,
            "scope": "sample",
            "detail": "本地作品样本内观察到的唯一机构，不代表全球机构总数。",
        }

    if {"research_groups", "research_group_evidence"}.issubset(tables):
        verified, candidate, active_authors = connection.execute(
            """
            SELECT
                (SELECT COUNT(DISTINCT rg.group_id) FROM research_groups rg
                 JOIN research_group_evidence e ON e.group_id=rg.group_id
                 WHERE rg.status='verified' AND e.observed_at>=?),
                (SELECT COUNT(DISTINCT rg.group_id) FROM research_groups rg
                 JOIN research_group_evidence e ON e.group_id=rg.group_id
                 WHERE rg.status='candidate' AND e.observed_at>=?),
                (SELECT COUNT(DISTINCT author_id) FROM research_group_evidence
                 WHERE author_id IS NOT NULL AND observed_at>=?)
            """,
            (cutoff, cutoff, cutoff),
        ).fetchone()
        if verified or candidate or active_authors:
            result["groups"] = {
                "value": int(verified),
                "delta": None,
                "scope": "verified",
                "detail": (
                    f"已核实 {int(verified)} · 候选 {int(candidate)} · "
                    f"证据关联研究人员 {int(active_authors)}"
                ),
            }
    return result


def _load_global_trend(
    connection: sqlite3.Connection, tables: set[str]
) -> pd.DataFrame:
    if "global_metric_snapshots" not in tables:
        return pd.DataFrame()
    columns = {row[1] for row in connection.execute("PRAGMA table_info(global_metric_snapshots)")}
    required = {"window_end", "scope_id", "metric_key", "metric_value", "count_scope"}
    if not required.issubset(columns):
        return pd.DataFrame()
    return _dataframe(
        connection.execute(
            """
            SELECT window_end AS date, scope_id AS region, metric_value AS value,
                   count_scope
            FROM global_metric_snapshots
            WHERE metric_key='published_works'
            ORDER BY window_end, scope_id
            """
        ).fetchall()
    )


def get_global_research_trend(
    path: str | Path, days: int = 30
) -> dict[str, Any]:
    """Read current, successfully published 30-day trend snapshots."""
    if days not in {30, 90, 365}:
        raise ValueError("days must be one of 30, 90, or 365")

    columns = [
        "date",
        *TREND_CATEGORY_IDS,
        "data_status",
        "latest_updated_at",
        "complete_categories",
    ]
    unavailable = {
        "data": pd.DataFrame(columns=columns),
        "status": "unavailable",
        "latest_updated_at": None,
        "integrity": {
            "requested_days": days,
            "available_days": 0,
            "complete_days": 0,
            "missing_days": days,
            "expected_categories": list(TREND_CATEGORY_IDS),
            "mapping_versions": [],
            "query_versions": [],
            "calculation_versions": [],
        },
    }


    db_path = Path(path)
    if not db_path.exists():
        return unavailable

    with closing(_connect_read_only(db_path)) as connection:
        tables = _table_names(connection)
        required = {"trend_30d_snapshots", "trend_backfill_runs"}
        if not required.issubset(tables):
            return unavailable

        latest_date = connection.execute(
            """
            SELECT MAX(s.snapshot_date)
            FROM trend_30d_snapshots s
            JOIN trend_backfill_runs r ON r.run_id=s.run_id
            WHERE s.is_current=1 AND s.data_status='success' AND r.status='success'
            """
        ).fetchone()[0]
        if not latest_date:
            return unavailable

        end = date.fromisoformat(str(latest_date))
        start = end - timedelta(days=days - 1)
        rows = connection.execute(
            """
            SELECT s.snapshot_date, s.category_id, s.works_count,
                   s.updated_at, s.topic_mapping_version, s.query_version,
                   s.calculation_version
            FROM trend_30d_snapshots s
            JOIN trend_backfill_runs r ON r.run_id=s.run_id
            WHERE s.is_current=1
              AND s.data_status='success'
              AND r.status='success'
              AND s.snapshot_date BETWEEN ? AND ?
            ORDER BY s.snapshot_date, s.category_id
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    raw = _dataframe(rows)
    if raw.empty:
        return unavailable

    expected_index = pd.date_range(start=start, end=end, freq="D")
    pivot = raw.pivot(
        index="snapshot_date", columns="category_id", values="works_count"
    )
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.reindex(expected_index)
    for category_id in TREND_CATEGORY_IDS:
        if category_id not in pivot.columns:
            pivot[category_id] = pd.NA
    pivot = pivot[list(TREND_CATEGORY_IDS)]

    updated = raw.groupby("snapshot_date")["updated_at"].max()
    updated.index = pd.to_datetime(updated.index)
    complete_categories = pivot.notna().sum(axis=1)
    result = pivot.reset_index(names="date")
    result["complete_categories"] = complete_categories.to_numpy()
    result["data_status"] = result["complete_categories"].map(
        lambda count: "complete" if count == len(TREND_CATEGORY_IDS) else (
            "partial" if count > 0 else "missing"
        )
    )
    result["latest_updated_at"] = result["date"].map(updated)
    result = result[columns]

    available_days = int((result["complete_categories"] > 0).sum())
    complete_days = int((result["complete_categories"] == len(TREND_CATEGORY_IDS)).sum())
    status = "complete" if complete_days == days else "partial"
    return {
        "data": result,
        "status": status,
        "latest_updated_at": raw["updated_at"].max(),
        "integrity": {
            "requested_days": days,
            "available_days": available_days,
            "complete_days": complete_days,
            "missing_days": days - available_days,
            "expected_categories": list(TREND_CATEGORY_IDS),
            "mapping_versions": sorted(raw["topic_mapping_version"].unique().tolist()),
            "query_versions": sorted(raw["query_version"].unique().tolist()),
            "calculation_versions": sorted(raw["calculation_version"].unique().tolist()),
        },
    }


def get_topic_hotspot_ranking(
    path: str | Path, period_days: int = 90
) -> dict[str, Any]:
    """Return the current published TOP 10 for one ranking period."""
    if period_days not in {90, 360}:
        raise ValueError("period_days must be 90 or 360")
    columns = [
        "rank", "topic_id", "topic_name", "topic_name_zh", "subfield_id",
        "subfield_name", "field_id", "field_name", "domain_id", "domain_name",
        "period_works_count", "window_start", "window_end", "query_as_of",
        "taxonomy_version",
    ]
    unavailable = {
        "data": pd.DataFrame(columns=columns), "status": "unavailable",
        "period_days": period_days, "ranking_date": None,
        "latest_updated_at": None,
    }
    db_path = Path(path)
    if not db_path.exists():
        return unavailable
    with closing(_connect_read_only(db_path)) as connection:
        required = {"topic_ranking_snapshots", "openalex_topics", "topic_update_runs"}
        if not required.issubset(_table_names(connection)):
            return unavailable
        ranking_date = connection.execute(
            """
            SELECT MAX(r.ranking_date)
            FROM topic_ranking_snapshots r
            JOIN topic_update_runs u ON u.run_id=r.source_run_id
            WHERE r.period_days=? AND r.is_current=1 AND u.status='published'
            """,
            (period_days,),
        ).fetchone()[0]
        if not ranking_date:
            return unavailable
        rows = connection.execute(
            """
            SELECT r.rank, r.topic_id, t.topic_name, t.topic_name_zh,
                   t.subfield_id, t.subfield_name, t.field_id, t.field_name,
                   t.domain_id, t.domain_name, r.period_works_count,
                   r.window_start, r.window_end, r.query_as_of,
                   t.taxonomy_version, r.updated_at
            FROM topic_ranking_snapshots r
            JOIN openalex_topics t ON t.topic_id=r.topic_id
            JOIN topic_update_runs u ON u.run_id=r.source_run_id
            WHERE r.ranking_date=? AND r.period_days=? AND r.is_current=1
              AND u.status='published' AND r.rank<=10
            ORDER BY r.rank
            """,
            (ranking_date, period_days),
        ).fetchall()
    frame = _dataframe(rows)
    if frame.empty:
        return unavailable
    latest_updated = frame["updated_at"].max()
    return {
        "data": frame[columns],
        "status": "complete" if len(frame) == 10 else "partial",
        "period_days": period_days, "ranking_date": str(ranking_date),
        "latest_updated_at": latest_updated,
    }


def get_topic_daily_trends(
    path: str | Path, period_days: int = 90
) -> dict[str, Any]:
    """Return daily new Works for the selected period's own TOP 10 Topics."""
    ranking_result = get_topic_hotspot_ranking(path, period_days)
    empty = pd.DataFrame(columns=[
        "date", "rank", "topic_id", "topic_name", "topic_name_zh",
        "subfield_name", "field_name", "daily_works_count", "query_as_of",
    ])
    if ranking_result["status"] != "complete":
        return {
            **ranking_result, "data": empty,
            "integrity": {
                "expected_rows": period_days * 10, "available_rows": 0,
                "expected_dates": period_days, "available_dates": 0,
                "missing_rows": period_days * 10, "duplicate_rows": 0,
            },
        }
    ranking = ranking_result["data"]
    start, end = str(ranking.iloc[0]["window_start"]), str(ranking.iloc[0]["window_end"])
    topic_ids = ranking["topic_id"].astype(str).tolist()
    placeholders = ",".join("?" for _ in topic_ids)
    with closing(_connect_read_only(path)) as connection:
        rows = connection.execute(
            f"""
            SELECT d.date, r.rank, d.topic_id, t.topic_name, t.topic_name_zh,
                   t.subfield_name, t.field_name, d.daily_works_count,
                   d.query_as_of, d.updated_at
            FROM topic_daily_counts d
            JOIN openalex_topics t ON t.topic_id=d.topic_id
            JOIN topic_update_runs du ON du.run_id=d.source_run_id
            JOIN topic_ranking_snapshots r
              ON r.topic_id=d.topic_id AND r.ranking_date=?
             AND r.period_days=? AND r.is_current=1
            JOIN topic_update_runs u ON u.run_id=r.source_run_id
            WHERE d.is_current=1 AND d.query_status='success' AND du.status='published'
              AND u.status='published' AND d.date BETWEEN ? AND ?
              AND d.topic_id IN ({placeholders})
            ORDER BY d.date, r.rank
            """,
            (ranking_result["ranking_date"], period_days, start, end, *topic_ids),
        ).fetchall()
    frame = _dataframe(rows)
    expected_rows = period_days * 10
    available_rows = len(frame)
    available_dates = int(frame["date"].nunique()) if not frame.empty else 0
    duplicates = int(frame.duplicated(["date", "topic_id"]).sum()) if not frame.empty else 0
    topic_counts = frame.groupby("topic_id")["date"].nunique() if not frame.empty else pd.Series(dtype=int)
    complete = (
        available_rows == expected_rows and available_dates == period_days
        and len(topic_counts) == 10 and bool((topic_counts == period_days).all())
        and duplicates == 0
    )
    latest_updated = frame["updated_at"].max() if not frame.empty else None
    if not frame.empty:
        frame = frame.drop(columns=["updated_at"])
    return {
        "data": frame, "ranking": ranking,
        "status": "complete" if complete else ("partial" if available_rows else "unavailable"),
        "period_days": period_days, "ranking_date": ranking_result["ranking_date"],
        "latest_updated_at": latest_updated,
        "latest_date_ingesting": end == ranking_result["ranking_date"],
        "integrity": {
            "expected_rows": expected_rows, "available_rows": available_rows,
            "expected_dates": period_days, "available_dates": available_dates,
            "missing_rows": expected_rows - available_rows, "duplicate_rows": duplicates,
        },
    }


def get_v14_hotspot_dashboard(
    path: str | Path,
    *,
    period_days: int = 90,
    field_id: str | None = None,
    sort_by: str = "works",
) -> dict[str, Any]:
    """Return the V1.4 six-Field dashboard from published local snapshots.

    Counts use publication_date and primary_topic snapshots imported in V1.3.4.
    Missing daily rows remain NA. Period growth is unavailable until the matching
    previous 90/360-day snapshots have been collected.
    """
    if period_days not in {90, 360}:
        raise ValueError("period_days must be 90 or 360")
    if field_id is not None and str(field_id) not in V14_FIELD_IDS:
        raise ValueError("field_id must be one of the six V1.4 Fields")
    if sort_by not in {"works", "growth"}:
        raise ValueError("sort_by must be works or growth")

    empty = {
        "status": "unavailable",
        "taxonomy_version": V14_TAXONOMY_VERSION,
        "period_days": period_days,
        "field_id": field_id,
        "ranking_date": None,
        "ranking": pd.DataFrame(),
        "all_topics": pd.DataFrame(),
        "daily": pd.DataFrame(),
        "trend": pd.DataFrame(),
        "fields": pd.DataFrame(),
        "metrics": {},
        "integrity": {},
        "growth_sort_available": False,
    }
    db_path = Path(path)
    if not db_path.exists():
        return empty

    with closing(_connect_read_only(db_path)) as connection:
        required = {
            "taxonomy_versions", "field_scope_versions", "topic_taxonomy_versions",
            "topic_ranking_snapshots", "topic_daily_counts", "topic_update_runs",
        }
        if not required.issubset(_table_names(connection)):
            return empty
        version = connection.execute(
            """
            SELECT taxonomy_version, topic_count, field_count, imported_at
            FROM taxonomy_versions
            WHERE taxonomy_version=? AND is_current=1
            """,
            (V14_TAXONOMY_VERSION,),
        ).fetchone()
        if version is None:
            return empty
        fields = _dataframe(
            connection.execute(
                """
                SELECT field_id, field_name, field_name_zh, topic_count
                FROM field_scope_versions
                WHERE taxonomy_version=?
                ORDER BY CAST(field_id AS INTEGER)
                """,
                (V14_TAXONOMY_VERSION,),
            ).fetchall()
        )
        ranking_date = connection.execute(
            """
            SELECT MAX(r.ranking_date)
            FROM topic_ranking_snapshots r
            JOIN topic_update_runs u ON u.run_id=r.source_run_id
            WHERE r.period_days=? AND r.is_current=1 AND u.status='published'
            """,
            (period_days,),
        ).fetchone()[0]
        if not ranking_date:
            return {**empty, "fields": fields}

        parameters: list[Any] = [V14_TAXONOMY_VERSION, ranking_date, period_days]
        field_clause = ""
        if field_id is not None:
            field_clause = " AND t.field_id=?"
            parameters.append(str(field_id))
        ranking_rows = connection.execute(
            """
            SELECT r.topic_id, t.topic_name, t.topic_name_zh,
                   t.subfield_id, t.subfield_name, t.field_id, t.field_name,
                   f.field_name_zh, r.period_works_count, r.window_start,
                   r.window_end, r.query_as_of, r.updated_at
            FROM topic_ranking_snapshots r
            JOIN topic_taxonomy_versions t
              ON t.topic_id=r.topic_id AND t.taxonomy_version=?
            JOIN field_scope_versions f
              ON f.taxonomy_version=t.taxonomy_version AND f.field_id=t.field_id
            JOIN topic_update_runs u ON u.run_id=r.source_run_id
            WHERE r.ranking_date=? AND r.period_days=? AND r.is_current=1
              AND u.status='published'
            """ + field_clause + " ORDER BY r.period_works_count DESC, r.topic_id",
            parameters,
        ).fetchall()
        all_topics = _dataframe(ranking_rows)
        if all_topics.empty:
            return {**empty, "fields": fields, "ranking_date": str(ranking_date)}
        all_topics.insert(0, "rank", range(1, len(all_topics) + 1))
        all_topics["period_growth_rate"] = pd.NA
        all_topics["trend"] = "无可比基期"

        window_start = str(all_topics.iloc[0]["window_start"])
        window_end = str(all_topics.iloc[0]["window_end"])
        extra_start = (
            pd.Timestamp(window_start) - pd.DateOffset(months=1)
        ).date().isoformat()
        daily_parameters: list[Any] = [V14_TAXONOMY_VERSION, extra_start, window_end]
        daily_field_clause = ""
        if field_id is not None:
            daily_field_clause = " AND t.field_id=?"
            daily_parameters.append(str(field_id))
        daily_rows = connection.execute(
            """
            SELECT d.date, d.topic_id, t.topic_name, t.topic_name_zh,
                   t.subfield_id, t.subfield_name, t.field_id, t.field_name,
                   f.field_name_zh, d.daily_works_count, d.query_as_of,
                   d.updated_at
            FROM topic_daily_counts d
            JOIN topic_taxonomy_versions t
              ON t.topic_id=d.topic_id AND t.taxonomy_version=?
            JOIN field_scope_versions f
              ON f.taxonomy_version=t.taxonomy_version AND f.field_id=t.field_id
            JOIN topic_update_runs u ON u.run_id=d.source_run_id
            WHERE d.is_current=1 AND d.query_status='success'
              AND u.status='published' AND d.date BETWEEN ? AND ?
            """ + daily_field_clause + " ORDER BY d.topic_id, d.date",
            daily_parameters,
        ).fetchall()
        daily_raw = _dataframe(daily_rows)

        daily_parts: list[pd.DataFrame] = []
        if not daily_raw.empty:
            daily_raw["date"] = pd.to_datetime(daily_raw["date"])
            full_dates = pd.date_range(extra_start, window_end, freq="D")
            metadata_columns = [
                "topic_id", "topic_name", "topic_name_zh", "subfield_id",
                "subfield_name", "field_id", "field_name", "field_name_zh",
            ]
            for topic_id, topic_rows in daily_raw.groupby("topic_id", sort=False):
                metadata = topic_rows.iloc[0][metadata_columns].to_dict()
                indexed = topic_rows.set_index("date").reindex(full_dates)
                indexed.index.name = "date"
                for key, value in metadata.items():
                    indexed[key] = value
                indexed["query_status"] = indexed["daily_works_count"].map(
                    lambda value: "success" if pd.notna(value) else "missing"
                )
                daily_parts.append(indexed.reset_index())
        daily_with_baseline = (
            pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
        )
        trend = aggregate_topic_trends(
            daily_with_baseline, period_days, window_start, window_end
        )
        daily = daily_with_baseline
        if not daily_with_baseline.empty:
            daily = daily_with_baseline[
                (daily_with_baseline["date"] >= pd.Timestamp(window_start))
                & (daily_with_baseline["date"] <= pd.Timestamp(window_end))
            ].reset_index(drop=True)

        period_matrix_complete = (
            not daily.empty
            and len(daily) == len(all_topics) * period_days
            and not daily["daily_works_count"].isna().any()
            and int(daily["topic_id"].nunique()) == len(all_topics)
            and bool(
                (
                    daily.groupby("topic_id")["date"].nunique()
                    == period_days
                ).all()
            )
        )
        ranking_source = "period_snapshot"
        if period_matrix_complete:
            latest_totals = daily.groupby("topic_id")["daily_works_count"].sum()
            all_topics["period_works_count"] = (
                all_topics["topic_id"].map(latest_totals).astype(int)
            )
            all_topics = all_topics.sort_values(
                ["period_works_count", "topic_id"], ascending=[False, True]
            ).reset_index(drop=True)
            all_topics["rank"] = range(1, len(all_topics) + 1)
            ranking_source = "complete_daily_sum"

        latest_growth = pd.Series(dtype="float64")
        if not trend.empty:
            latest_period_end = trend["period_end"].max()
            latest_growth = (
                trend[trend["period_end"] == latest_period_end]
                .set_index("topic_id")["growth_rate"]
            )
        all_topics["period_growth_rate"] = pd.to_numeric(
            all_topics["topic_id"].map(latest_growth), errors="coerce"
        )
        all_topics["trend"] = all_topics["period_growth_rate"].map(
            lambda value: (
                "增长" if pd.notna(value) and value > 0
                else "下降" if pd.notna(value) and value < 0
                else "持平" if pd.notna(value)
                else "无可比基期"
            )
        )
        growth_ranking = all_topics[
            all_topics["period_growth_rate"].notna()
        ].sort_values(
            ["period_growth_rate", "period_works_count", "topic_id"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        growth_ranking["rank"] = range(1, len(growth_ranking) + 1)

        full_360 = connection.execute(
            """
            SELECT r.window_start, r.window_end, SUM(r.period_works_count)
            FROM topic_ranking_snapshots r
            JOIN topic_taxonomy_versions t
              ON t.topic_id=r.topic_id AND t.taxonomy_version=?
            JOIN topic_update_runs u ON u.run_id=r.source_run_id
            WHERE r.ranking_date=? AND r.period_days=360 AND r.is_current=1
              AND u.status='published'
            """,
            (V14_TAXONOMY_VERSION, ranking_date),
        ).fetchone()
        completeness_start = str(full_360[0]) if full_360 and full_360[0] else window_start
        completeness_end = str(full_360[1]) if full_360 and full_360[1] else window_end
        scope_topic_count = len(all_topics)
        available_360_rows = connection.execute(
            """
            SELECT COUNT(*)
            FROM topic_daily_counts d
            JOIN topic_taxonomy_versions t
              ON t.topic_id=d.topic_id AND t.taxonomy_version=?
            JOIN topic_update_runs u ON u.run_id=d.source_run_id
            WHERE d.is_current=1 AND d.query_status='success' AND u.status='published'
              AND d.date BETWEEN ? AND ?
            """ + (" AND t.field_id=?" if field_id is not None else ""),
            (
                V14_TAXONOMY_VERSION,
                completeness_start,
                completeness_end,
                *((str(field_id),) if field_id is not None else ()),
            ),
        ).fetchone()[0]
        works_rows = connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        failed_runs = connection.execute(
            "SELECT COUNT(*) FROM topic_update_runs WHERE status='failed'"
        ).fetchone()[0]
        latest_run = connection.execute(
            """
            SELECT status, query_as_of, completed_at
            FROM topic_update_runs ORDER BY COALESCE(completed_at, updated_at) DESC LIMIT 1
            """
        ).fetchone()

    expected_360_rows = scope_topic_count * 360
    completeness = (
        float(available_360_rows) / expected_360_rows if expected_360_rows else 0.0
    )
    growth_sort_available = not growth_ranking.empty
    ranking = (
        growth_ranking.head(10).copy()
        if sort_by == "growth" and growth_sort_available
        else all_topics.head(10).copy()
    )
    available_topic_ids = (
        set(daily.loc[daily["query_status"] == "success", "topic_id"].astype(str))
        if not daily.empty else set()
    )
    metrics = {
        "period_works_count": int(all_topics["period_works_count"].sum()),
        "covered_topics": scope_topic_count,
        "covered_fields": int(all_topics["field_id"].nunique()),
        "active_topics": int((all_topics["period_works_count"] > 0).sum()),
        "top_topic": all_topics.iloc[0].to_dict(),
        "daily_completeness_360": completeness,
        "available_daily_topics": len(available_topic_ids),
        "local_work_records": int(works_rows),
        "failed_update_runs": int(failed_runs),
        "latest_run_status": str(latest_run["status"]) if latest_run else None,
        "latest_success_at": (
            str(latest_run["query_as_of"] or latest_run["completed_at"])
            if latest_run else None
        ),
        "data_through": window_end,
        "ranking_source": ranking_source,
    }
    status = "complete" if completeness == 1.0 else "partial"
    return {
        "status": status,
        "taxonomy_version": V14_TAXONOMY_VERSION,
        "period_days": period_days,
        "field_id": field_id,
        "ranking_date": str(ranking_date),
        "ranking": ranking,
        "all_topics": all_topics,
        "daily": daily,
        "trend": trend,
        "fields": fields,
        "metrics": metrics,
        "integrity": {
            "expected_daily_rows_360": expected_360_rows,
            "available_daily_rows_360": int(available_360_rows),
            "missing_daily_rows_360": expected_360_rows - int(available_360_rows),
            "daily_completeness_360": completeness,
            "daily_topic_ids": sorted(available_topic_ids),
            "missing_is_zero_filled": False,
            "publication_date_only": True,
        },
        "growth_sort_available": growth_sort_available,
    }


def get_v15_regional_dashboard(
    path: str | Path,
    *,
    region_code: str,
    period_days: int = 90,
    field_id: str | None = None,
    sort_by: str = "works",
) -> dict[str, Any]:
    """Return one published CN/US regional snapshot without touching GLOBAL tables."""
    region = str(region_code).upper()
    if region not in V15_REGION_CODES:
        raise ValueError("region_code must be CN or US")
    if period_days not in {90, 360}:
        raise ValueError("period_days must be 90 or 360")
    if field_id is not None and str(field_id) not in V14_FIELD_IDS:
        raise ValueError("field_id must be one of the six V1.4 Fields")
    if sort_by not in {"works", "growth"}:
        raise ValueError("sort_by must be works or growth")

    empty = {
        "status": "unavailable",
        "region_code": region,
        "taxonomy_version": V14_TAXONOMY_VERSION,
        "period_days": period_days,
        "field_id": field_id,
        "ranking_date": None,
        "ranking": pd.DataFrame(),
        "all_topics": pd.DataFrame(),
        "daily": pd.DataFrame(),
        "trend": pd.DataFrame(),
        "fields": pd.DataFrame(),
        "metrics": {},
        "integrity": {},
        "growth_sort_available": False,
    }
    db_path = Path(path)
    if not db_path.exists():
        return empty

    with closing(_connect_read_only(db_path)) as connection:
        required = {
            "taxonomy_versions",
            "field_scope_versions",
            "topic_taxonomy_versions",
            "regional_snapshot_batches",
            "regional_topic_runs",
            "regional_topic_period_snapshots",
            "regional_topic_daily_counts",
        }
        if not required.issubset(_table_names(connection)):
            return empty
        fields = _dataframe(
            connection.execute(
                """
                SELECT field_id, field_name, field_name_zh, topic_count
                FROM field_scope_versions
                WHERE taxonomy_version=?
                ORDER BY CAST(field_id AS INTEGER)
                """,
                (V14_TAXONOMY_VERSION,),
            ).fetchall()
        )
        batch = connection.execute(
            """
            SELECT b.batch_id, b.ranking_date, b.daily_start, b.daily_end,
                   b.query_version, b.calculation_version, b.completed_at
            FROM regional_snapshot_batches b
            JOIN regional_topic_runs r ON r.batch_id=b.batch_id
            WHERE b.status='published' AND r.status='published'
              AND r.region_code=? AND b.taxonomy_version=?
            ORDER BY b.ranking_date DESC, b.completed_at DESC LIMIT 1
            """,
            (region, V14_TAXONOMY_VERSION),
        ).fetchone()
        if batch is None:
            return {**empty, "fields": fields}

        batch_id = str(batch["batch_id"])
        parameters: list[Any] = [V14_TAXONOMY_VERSION, batch_id, region, period_days]
        field_clause = ""
        if field_id is not None:
            field_clause = " AND s.field_id=?"
            parameters.append(str(field_id))
        rows = connection.execute(
            """
            SELECT s.topic_id, t.topic_name, t.topic_name_zh,
                   t.subfield_id, t.subfield_name, t.field_id, t.field_name,
                   f.field_name_zh, s.works_count AS period_works_count,
                   s.previous_works_count, s.growth_amount,
                   s.growth_rate AS period_growth_rate, s.growth_status,
                   s.window_start, s.window_end, s.query_as_of,
                   s.works_rank, s.growth_amount_rank, s.growth_rate_rank
            FROM regional_topic_period_snapshots s
            JOIN topic_taxonomy_versions t
              ON t.topic_id=s.topic_id AND t.taxonomy_version=?
            JOIN field_scope_versions f
              ON f.taxonomy_version=t.taxonomy_version AND f.field_id=t.field_id
            WHERE s.batch_id=? AND s.region_code=? AND s.period_days=?
              AND s.data_status='success'
            """ + field_clause,
            parameters,
        ).fetchall()
        all_topics = _dataframe(rows)
        if all_topics.empty:
            return {
                **empty,
                "fields": fields,
                "ranking_date": str(batch["ranking_date"]),
            }

        growth_available = bool(all_topics["period_growth_rate"].notna().any())
        if sort_by == "growth" and growth_available:
            all_topics = all_topics.sort_values(
                ["period_growth_rate", "period_works_count", "topic_id"],
                ascending=[False, False, True],
            ).reset_index(drop=True)
        else:
            all_topics = all_topics.sort_values(
                ["period_works_count", "topic_id"], ascending=[False, True]
            ).reset_index(drop=True)
        all_topics.insert(0, "rank", range(1, len(all_topics) + 1))
        all_topics["trend"] = all_topics["period_growth_rate"].map(
            lambda value: (
                "增长" if pd.notna(value) and value > 0
                else "下降" if pd.notna(value) and value < 0
                else "持平" if pd.notna(value)
                else "新出现"
            )
        )
        ranking = all_topics.head(10).copy()

        window_start = str(all_topics.iloc[0]["window_start"])
        window_end = str(all_topics.iloc[0]["window_end"])
        extra_start = (pd.Timestamp(window_start) - pd.DateOffset(months=1)).date().isoformat()
        daily_parameters: list[Any] = [
            V14_TAXONOMY_VERSION,
            batch_id,
            region,
            extra_start,
            window_end,
        ]
        daily_field_clause = ""
        if field_id is not None:
            daily_field_clause = " AND d.field_id=?"
            daily_parameters.append(str(field_id))
        daily_rows = connection.execute(
            """
            SELECT d.publication_date AS date, d.topic_id,
                   t.topic_name, t.topic_name_zh, t.subfield_id, t.subfield_name,
                   t.field_id, t.field_name, f.field_name_zh,
                   d.daily_works_count, d.query_as_of, d.updated_at
            FROM regional_topic_daily_counts d
            JOIN topic_taxonomy_versions t
              ON t.topic_id=d.topic_id AND t.taxonomy_version=?
            JOIN field_scope_versions f
              ON f.taxonomy_version=t.taxonomy_version AND f.field_id=t.field_id
            WHERE d.batch_id=? AND d.region_code=? AND d.data_status='success'
              AND d.publication_date BETWEEN ? AND ?
            """ + daily_field_clause + " ORDER BY d.topic_id, d.publication_date",
            daily_parameters,
        ).fetchall()
        daily_raw = _dataframe(daily_rows)
        if not daily_raw.empty:
            daily_raw["date"] = pd.to_datetime(daily_raw["date"])
            daily_raw["query_status"] = "success"
        trend = aggregate_topic_trends(
            daily_raw, period_days, window_start, window_end
        )
        daily = daily_raw[
            (daily_raw["date"] >= pd.Timestamp(window_start))
            & (daily_raw["date"] <= pd.Timestamp(window_end))
        ].reset_index(drop=True) if not daily_raw.empty else pd.DataFrame()

        expected_rows = len(all_topics) * period_days
        available_rows = len(daily)
        available_topics = int(daily["topic_id"].nunique()) if not daily.empty else 0
        period_matrix_complete = (
            available_rows == expected_rows
            and available_topics == len(all_topics)
            and not daily["daily_works_count"].isna().any()
        )
        start_360 = (pd.Timestamp(window_end) - pd.Timedelta(days=359)).date().isoformat()
        complete_360_rows = connection.execute(
            """
            SELECT COUNT(*)
            FROM regional_topic_daily_counts d
            WHERE d.batch_id=? AND d.region_code=? AND d.data_status='success'
              AND d.publication_date BETWEEN ? AND ?
            """ + (" AND d.field_id=?" if field_id is not None else ""),
            (
                batch_id,
                region,
                start_360,
                window_end,
                *((str(field_id),) if field_id is not None else ()),
            ),
        ).fetchone()[0]
        run = connection.execute(
            """
            SELECT status, query_as_of, api_request_count, retry_count
            FROM regional_topic_runs WHERE batch_id=? AND region_code=?
            """,
            (batch_id, region),
        ).fetchone()

    metrics = {
        "period_works_count": int(all_topics["period_works_count"].sum()),
        "covered_topics": len(all_topics),
        "covered_fields": int(all_topics["field_id"].nunique()),
        "active_topics": int((all_topics["period_works_count"] > 0).sum()),
        "top_topic": all_topics.iloc[0].to_dict(),
        "daily_completeness_360": (
            float(complete_360_rows / (len(all_topics) * 360))
            if len(all_topics) else 0.0
        ),
        "available_daily_topics": available_topics,
        "local_work_records": 0,
        "failed_update_runs": 0 if run and run["status"] == "published" else 1,
        "latest_run_status": str(run["status"]) if run else None,
        "latest_success_at": str(batch["completed_at"]),
        "data_through": window_end,
        "ranking_source": "regional_period_snapshot",
        "batch_id": batch_id,
        "query_version": str(batch["query_version"]),
        "calculation_version": str(batch["calculation_version"]),
    }
    return {
        "status": "complete" if period_matrix_complete else "partial",
        "region_code": region,
        "taxonomy_version": V14_TAXONOMY_VERSION,
        "period_days": period_days,
        "field_id": field_id,
        "ranking_date": str(batch["ranking_date"]),
        "ranking": ranking,
        "all_topics": all_topics,
        "daily": daily,
        "trend": trend,
        "fields": fields,
        "metrics": metrics,
        "integrity": {
            "expected_daily_rows_360": len(all_topics) * 360,
            "available_daily_rows_360": int(complete_360_rows),
            "missing_daily_rows_360": len(all_topics) * 360 - int(complete_360_rows),
            "daily_completeness_360": metrics["daily_completeness_360"],
            "daily_topic_ids": sorted(daily["topic_id"].astype(str).unique()),
            "missing_is_zero_filled": False,
            "publication_date_only": True,
            "region_batch_id": batch_id,
        },
        "growth_sort_available": growth_available,
    }


def _load_topic_ranking(
    connection: sqlite3.Connection, tables: set[str]
) -> pd.DataFrame:
    if "topic_period_metrics" not in tables:
        return pd.DataFrame()
    return _dataframe(
        connection.execute(
            """
            SELECT t.label AS topic, m.category, m.total_count, m.sampled_count,
                   m.growth, m.data_confidence, m.count_scope, m.topic_key
            FROM topic_period_metrics m
            JOIN topics t ON t.topic_key=m.topic_key
            WHERE m.eligible_for_ranking=1
              AND m.batch_id=(SELECT MAX(batch_id) FROM topic_period_metrics)
            ORDER BY m.heat_score DESC
            LIMIT 40
            """
        ).fetchall()
    )


def _load_institution_rankings(
    connection: sqlite3.Connection, tables: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "institution_period_metrics" in tables:
        rows = _dataframe(
            connection.execute(
                """
                SELECT i.display_name AS institution, i.country_code,
                       m.work_count, m.topic_count, m.author_count,
                       m.ranking_scope, m.data_confidence
                FROM institution_period_metrics m
                JOIN institutions i ON i.openalex_institution_id=m.institution_id
                WHERE m.batch_id=(SELECT MAX(batch_id) FROM institution_period_metrics)
                ORDER BY m.work_count DESC
                LIMIT 200
                """
            ).fetchall()
        )
    elif {"institution_snapshots", "institutions"}.issubset(tables):
        rows = _dataframe(
            connection.execute(
                """
                SELECT i.display_name AS institution, i.country_code,
                       s.sampled_work_count AS work_count, s.topic_count,
                       NULL AS author_count, 'sample_rank' AS ranking_scope,
                       s.data_confidence
                FROM institution_snapshots s
                JOIN institutions i ON i.openalex_institution_id=s.institution_id
                WHERE s.snapshot_date=(SELECT MAX(snapshot_date) FROM institution_snapshots)
                ORDER BY s.sampled_work_count DESC
                LIMIT 200
                """
            ).fetchall()
        )
    else:
        rows = pd.DataFrame()
    if rows.empty:
        return rows, rows.copy()
    return rows.head(20), rows[rows["country_code"] == "CN"].head(20)


def _load_recent_works(
    connection: sqlite3.Connection, tables: set[str]
) -> pd.DataFrame:
    if "works" not in tables or not _table_count(connection, "works"):
        return pd.DataFrame()
    institution_join = ""
    institution_column = "NULL AS institutions"
    if {"work_authorships", "work_authorship_institutions", "institutions"}.issubset(tables):
        institution_join = """
            LEFT JOIN work_authorships wa ON wa.work_id=w.openalex_work_id
            LEFT JOIN work_authorship_institutions wai ON wai.authorship_id=wa.authorship_id
            LEFT JOIN institutions i ON i.openalex_institution_id=wai.institution_id
        """
        institution_column = "GROUP_CONCAT(DISTINCT i.display_name) AS institutions"
    return _dataframe(
        connection.execute(
            f"""
            SELECT w.publication_date, w.title, w.doi, w.venue, w.work_type,
                   w.cited_by_count, w.openalex_work_id, {institution_column}
            FROM works w
            {institution_join}
            GROUP BY w.openalex_work_id
            ORDER BY w.publication_date DESC, w.cited_by_count DESC
            LIMIT 30
            """
        ).fetchall()
    )


def _load_alerts(
    connection: sqlite3.Connection, tables: set[str]
) -> pd.DataFrame:
    if "research_alerts" not in tables:
        return pd.DataFrame()
    return _dataframe(
        connection.execute(
            """
            SELECT alert_type, subject_type, subject_id, severity, status,
                   triggered_at, observed_value, threshold, confidence
            FROM research_alerts
            ORDER BY triggered_at DESC
            LIMIT 20
            """
        ).fetchall()
    )


def load_scan_history(path: str | Path, limit: int = 100) -> pd.DataFrame:
    db_path = Path(path)
    if not db_path.exists():
        return pd.DataFrame()
    with closing(_connect_read_only(db_path)) as connection:
        if "scan_runs" not in _table_names(connection):
            return pd.DataFrame()
        return _dataframe(
            connection.execute(
                """
                SELECT r.run_id, r.status, r.run_mode, r.domain_profile,
                       r.attempted_query, r.started_at, r.completed_at, r.error,
                       COUNT(DISTINCT m.row_number) AS topic_rows,
                       COUNT(DISTINCT q.row_number) AS query_rows
                FROM scan_runs r
                LEFT JOIN scan_topic_metrics m ON m.run_id=r.run_id
                LEFT JOIN scan_query_log q ON q.run_id=r.run_id
                GROUP BY r.run_id
                ORDER BY r.started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )


def load_run_queries(path: str | Path, run_id: str) -> pd.DataFrame:
    with closing(_connect_read_only(path)) as connection:
        return _dataframe(
            connection.execute(
                """
                SELECT source, topic, region, query_string, result_count, sample_count
                FROM scan_query_log WHERE run_id=? ORDER BY row_number
                """,
                (run_id,),
            ).fetchall()
        )


def load_topic_observations(path: str | Path) -> pd.DataFrame:
    db_path = Path(path)
    if not db_path.exists():
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    with closing(_connect_read_only(db_path)) as connection:
        if "scan_topic_metrics" not in _table_names(connection):
            return pd.DataFrame()
        rows = connection.execute(
            """
            SELECT m.run_id, m.topic_id, m.topic, m.region, m.metrics_json,
                   r.completed_at
            FROM scan_topic_metrics m
            JOIN scan_runs r ON r.run_id=m.run_id
            WHERE r.status='success'
            ORDER BY r.completed_at DESC, m.row_number
            """
        ).fetchall()
        for row in rows:
            metric = json.loads(row["metrics_json"])
            records.append(
                {
                    "run_id": row["run_id"],
                    "completed_at": row["completed_at"],
                    "topic_id": row["topic_id"],
                    "topic": row["topic"],
                    "region": row["region"],
                    "current_count": metric.get("current_count"),
                    "sampled_count": metric.get("sampled_count"),
                    "coverage_rate": metric.get("coverage_rate"),
                    "growth": metric.get("adjusted_growth", metric.get("growth")),
                    "acceleration": metric.get("adjusted_acceleration", metric.get("acceleration")),
                    "trend_label": metric.get("trend_label"),
                    "heat_score": metric.get("score"),
                    "score_coverage": metric.get("score_coverage"),
                    "data_confidence": metric.get("data_confidence"),
                    "query_string": metric.get("query_string"),
                }
            )
    return pd.DataFrame(records)


def load_database_status(path: str | Path) -> dict[str, Any]:
    db_path = Path(path)
    if not db_path.exists():
        return {"exists": False, "path": str(db_path), "tables": pd.DataFrame()}
    with closing(_connect_read_only(db_path)) as connection:
        tables = sorted(_table_names(connection) - {"sqlite_sequence"})
        table_rows = [
            {"table": table, "rows": _table_count(connection, table)}
            for table in tables
        ]
        schema_row = connection.execute(
            "SELECT value FROM schema_metadata WHERE key='schema_version'"
        ).fetchone()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    stat = db_path.stat()
    return {
        "exists": True,
        "path": str(db_path.resolve()),
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
        "schema_version": schema_row[0] if schema_row else None,
        "integrity": integrity,
        "foreign_key_violations": foreign_key_violations,
        "tables": pd.DataFrame(table_rows),
    }
