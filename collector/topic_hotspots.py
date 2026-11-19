from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from storage import initialize_database


AUDIT_DATE = "2026-11-18"
PERIODS = (90, 360)
EXPECTED_DAILY_ROWS = {90: 900, 360: 3600}
EXPECTED_RANKING_ROWS = 4516
IMPORT_RUN_ID = "topic-audit-import-20261118-v1"
CALCULATION_VERSION = "topic-ranking-audit-20261118-v1"


@dataclass(frozen=True)
class AuditFiles:
    ranking_90: Path
    ranking_360: Path
    daily_90: Path
    daily_360: Path

    @classmethod
    def from_root(cls, root: Path) -> "AuditFiles":
        return cls(
            root / "TOPIC_RANKING_90D.csv",
            root / "TOPIC_RANKING_360D.csv",
            root / "TOPIC_TOP10_DAILY_90D.csv",
            root / "TOPIC_TOP10_DAILY_360D.csv",
        )


def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype={"topic_id": "string"})
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
    return frame


def validate_audit_files(root: Path) -> dict[str, Any]:
    files = AuditFiles.from_root(root)
    ranking_required = {
        "rank", "window_days", "window_start", "window_end", "topic_id",
        "topic_name", "topic_name_zh", "subfield_id", "subfield_name",
        "field_id", "field_name", "domain_id", "domain_name",
        "period_works_count", "query_status", "query_as_of", "query_version",
        "taxonomy_version",
    }
    daily_required = {
        "date", "period_days", "period_rank", "topic_id", "topic_name",
        "topic_name_zh", "subfield_id", "subfield_name", "field_id",
        "field_name", "domain_id", "domain_name", "daily_works_count",
        "query_status", "query_as_of", "query_version", "taxonomy_version",
        "revision_no", "is_current",
    }
    rankings = {
        90: _read_csv(files.ranking_90, ranking_required),
        360: _read_csv(files.ranking_360, ranking_required),
    }
    daily = {
        90: _read_csv(files.daily_90, daily_required),
        360: _read_csv(files.daily_360, daily_required),
    }

    for period in PERIODS:
        ranking = rankings[period]
        series = daily[period]
        if len(ranking) != EXPECTED_RANKING_ROWS or ranking["topic_id"].nunique() != EXPECTED_RANKING_ROWS:
            raise ValueError(f"{period}-day ranking must contain 4,516 unique Topics")
        if set(ranking["window_days"].astype(int)) != {period}:
            raise ValueError(f"{period}-day ranking has a mismatched window_days")
        if set(ranking["query_status"]) != {"success"}:
            raise ValueError(f"{period}-day ranking contains failed queries")
        if sorted(ranking["rank"].astype(int)) != list(range(1, EXPECTED_RANKING_ROWS + 1)):
            raise ValueError(f"{period}-day ranking is not a complete rank sequence")
        if len(series) != EXPECTED_DAILY_ROWS[period]:
            raise ValueError(f"{period}-day daily file has {len(series)} rows")
        series["date"] = pd.to_datetime(series["date"], errors="raise").dt.date.astype(str)
        if series["date"].nunique() != period or series["topic_id"].nunique() != 10:
            raise ValueError(f"{period}-day daily coverage must be {period} dates x 10 Topics")
        if series.duplicated(["date", "topic_id"]).any():
            raise ValueError(f"{period}-day daily file contains duplicate date/Topic rows")
        if (pd.to_numeric(series["daily_works_count"], errors="raise") < 0).any():
            raise ValueError(f"{period}-day daily file contains a negative count")
        if set(series["query_status"]) != {"success"}:
            raise ValueError(f"{period}-day daily file contains failed queries")
        top = ranking.nsmallest(10, "rank").set_index("topic_id")
        sums = series.groupby("topic_id")["daily_works_count"].sum()
        expected = top["period_works_count"].astype(int)
        if not sums.sort_index().equals(expected.sort_index()):
            raise ValueError(f"{period}-day daily sums do not match the ranking snapshot")

    hierarchy_columns = [
        "topic_name", "subfield_id", "subfield_name", "field_id", "field_name",
        "domain_id", "domain_name", "taxonomy_version",
    ]
    left = rankings[90].set_index("topic_id")[hierarchy_columns].sort_index().astype(str)
    right = rankings[360].set_index("topic_id")[hierarchy_columns].sort_index().astype(str)
    if not left.equals(right):
        raise ValueError("90-day and 360-day ranking files use different Topic hierarchies")

    overlap = daily[90].merge(
        daily[360], on=["date", "topic_id"], suffixes=("_90", "_360")
    )
    if not (
        overlap["daily_works_count_90"].astype(int)
        == overlap["daily_works_count_360"].astype(int)
    ).all():
        raise ValueError("overlapping 90/360-day daily counts disagree")

    return {
        "rankings": rankings,
        "daily": daily,
        "ranking_rows": {period: len(rankings[period]) for period in PERIODS},
        "daily_source_rows": {period: len(daily[period]) for period in PERIODS},
        "top_topic_union": len(set(daily[90]["topic_id"]) | set(daily[360]["topic_id"])),
    }


def import_audit_files(root: Path, database: Path) -> dict[str, Any]:
    validated = validate_audit_files(root)
    rankings: dict[int, pd.DataFrame] = validated["rankings"]
    daily: dict[int, pd.DataFrame] = validated["daily"]
    initialize_database(database)
    now = datetime.now().astimezone().isoformat()
    query_as_of = max(
        str(frame["query_as_of"].max()) for frame in [*rankings.values(), *daily.values()]
    )

    topics = rankings[90].copy()
    daily_union = pd.concat([daily[360], daily[90]], ignore_index=True)
    daily_union = daily_union.sort_values(["date", "topic_id", "period_days"], ascending=[True, True, False])
    daily_union = daily_union.drop_duplicates(["date", "topic_id"], keep="first")

    connection = sqlite3.connect(database, timeout=30)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO topic_update_runs(
                    run_id, ranking_date, source_type, status, query_as_of,
                    calculation_version, started_at, completed_at, created_at, updated_at
                ) VALUES (?, ?, 'audit_import', 'running', ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status='running', error_message=NULL, updated_at=excluded.updated_at
                """,
                (IMPORT_RUN_ID, AUDIT_DATE, query_as_of, CALCULATION_VERSION, now, now, now),
            )
            connection.executemany(
                """
                INSERT INTO openalex_topics(
                    topic_id, topic_name, topic_name_zh, subfield_id, subfield_name,
                    field_id, field_name, domain_id, domain_name, taxonomy_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_id) DO UPDATE SET
                    topic_name=excluded.topic_name,
                    topic_name_zh=COALESCE(excluded.topic_name_zh, openalex_topics.topic_name_zh),
                    subfield_id=excluded.subfield_id, subfield_name=excluded.subfield_name,
                    field_id=excluded.field_id, field_name=excluded.field_name,
                    domain_id=excluded.domain_id, domain_name=excluded.domain_name,
                    taxonomy_version=excluded.taxonomy_version, updated_at=excluded.updated_at
                """,
                [
                    (
                        str(row.topic_id), str(row.topic_name),
                        None if pd.isna(row.topic_name_zh) else str(row.topic_name_zh),
                        str(row.subfield_id), str(row.subfield_name), str(row.field_id),
                        str(row.field_name), str(row.domain_id), str(row.domain_name),
                        str(row.taxonomy_version), now,
                    )
                    for row in topics.itertuples(index=False)
                ],
            )
            for period, frame in rankings.items():
                connection.executemany(
                    """
                    INSERT INTO topic_ranking_snapshots(
                        ranking_date, period_days, topic_id, rank, period_works_count,
                        window_start, window_end, query_as_of, calculation_version,
                        source_run_id, is_current, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(ranking_date, period_days, topic_id, calculation_version)
                    DO UPDATE SET rank=excluded.rank,
                        period_works_count=excluded.period_works_count,
                        query_as_of=excluded.query_as_of, updated_at=excluded.updated_at
                    """,
                    [
                        (
                            AUDIT_DATE, period, str(row.topic_id), int(row.rank),
                            int(row.period_works_count), str(row.window_start),
                            str(row.window_end), str(row.query_as_of), CALCULATION_VERSION,
                            IMPORT_RUN_ID, now, now,
                        )
                        for row in frame.itertuples(index=False)
                    ],
                )
            connection.executemany(
                """
                INSERT INTO topic_daily_counts(
                    date, topic_id, daily_works_count, query_as_of, query_status,
                    revision_no, is_current, query_version, taxonomy_version,
                    source_run_id, revision_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'success', ?, 1, ?, ?, ?, 'V1.3.4 audit import', ?, ?)
                ON CONFLICT(date, topic_id, revision_no) DO UPDATE SET
                    daily_works_count=excluded.daily_works_count,
                    query_as_of=excluded.query_as_of, updated_at=excluded.updated_at
                """,
                [
                    (
                        str(row.date), str(row.topic_id), int(row.daily_works_count),
                        str(row.query_as_of), int(row.revision_no), str(row.query_version),
                        str(row.taxonomy_version), IMPORT_RUN_ID, now, now,
                    )
                    for row in daily_union.itertuples(index=False)
                ],
            )
            connection.execute(
                """
                UPDATE topic_update_runs
                SET status='published', completed_at=?, updated_at=? WHERE run_id=?
                """,
                (now, now, IMPORT_RUN_ID),
            )
    finally:
        connection.close()

    return {
        **{key: value for key, value in validated.items() if not isinstance(value, dict)},
        "topics": len(topics),
        "ranking_rows": sum(len(frame) for frame in rankings.values()),
        "daily_rows": len(daily_union),
        "database": str(database.resolve()),
        "run_id": IMPORT_RUN_ID,
    }
