from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


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


def load_daily_collection_data(path: str | Path, limit: int = 100) -> dict[str, Any]:
    """Load published V3.2 collection state without mutating the database."""
    empty = {
        "available": False,
        "latest_run": None,
        "runs": pd.DataFrame(),
        "windows": pd.DataFrame(),
        "observations": pd.DataFrame(),
        "date_status": pd.DataFrame(),
        "work_types": pd.DataFrame(),
        "quality": pd.DataFrame(),
    }
    db_path = Path(path)
    if not db_path.exists():
        return empty
    with closing(_connect_read_only(db_path)) as connection:
        tables = _table_names(connection)
        required = {"daily_collection_runs", "work_date_observations"}
        if not required.issubset(tables):
            return empty

        runs = _dataframe(
            connection.execute(
                """
                SELECT run_id, run_date, timezone_name, trigger_kind, status,
                       started_at, completed_at, window_count, completed_windows,
                       failed_windows, request_budget, request_count,
                       response_bytes, retry_count, rate_remaining, error
                FROM daily_collection_runs
                ORDER BY started_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )
        latest_run = None if runs.empty else runs.iloc[0].to_dict()
        windows = pd.DataFrame()
        if "daily_collection_windows" in tables:
            windows = _dataframe(
                connection.execute(
                    """
                    SELECT run_id, publication_date, reasons_json, priority,
                           preflight_meta_count, estimated_requests, status,
                           skip_reason, error, updated_at
                    FROM daily_collection_windows
                    ORDER BY updated_at DESC, priority LIMIT ?
                    """,
                    (limit * 10,),
                ).fetchall()
            )
        observations = _dataframe(
            connection.execute(
                """
                SELECT observation_id, publication_date, batch_id, run_id,
                       observed_at, meta_count, previous_meta_count, count_delta,
                       sampled_count, coverage_rate, is_truncated, inserted_works,
                       updated_works, unchanged_works, authors_inserted,
                       authors_updated, institution_relationship_changes,
                       topic_relationship_changes, request_count, response_bytes,
                       retry_count, rate_remaining, quality_status,
                       stability_status, published
                FROM work_date_observations
                ORDER BY observed_at DESC LIMIT ?
                """,
                (limit * 5,),
            ).fetchall()
        )
        date_status = pd.DataFrame()
        if "work_date_status" in tables:
            date_status = _dataframe(
                connection.execute(
                    """
                    SELECT publication_date, status, first_observed_at,
                           last_observed_at, last_meta_count,
                           successful_observations, consecutive_unchanged,
                           next_recheck_after, updated_at
                    FROM work_date_status
                    ORDER BY publication_date DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            )
        work_types = pd.DataFrame()
        if "work_type_observations" in tables:
            work_types = _dataframe(
                connection.execute(
                    """
                    SELECT types.batch_id, observations.publication_date,
                           observations.observed_at, types.raw_type,
                           types.normalized_group, types.work_count
                    FROM work_type_observations types
                    JOIN work_date_observations observations
                      ON observations.batch_id=types.batch_id
                    WHERE observations.published=1
                    ORDER BY observations.observed_at DESC, types.work_count DESC
                    """
                ).fetchall()
            )
        quality = pd.DataFrame()
        if "data_quality_reports" in tables:
            quality = _dataframe(
                connection.execute(
                    """
                    SELECT reports.batch_id, observations.publication_date,
                           reports.check_name, reports.severity, reports.status,
                           reports.details, reports.created_at
                    FROM data_quality_reports reports
                    LEFT JOIN work_date_observations observations
                      ON observations.batch_id=reports.batch_id
                    WHERE observations.batch_id IS NOT NULL
                    ORDER BY reports.created_at DESC LIMIT ?
                    """,
                    (limit * 5,),
                ).fetchall()
            )
    return {
        "available": True,
        "latest_run": latest_run,
        "runs": runs,
        "windows": windows,
        "observations": observations,
        "date_status": date_status,
        "work_types": work_types,
        "quality": quality,
    }


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
