from __future__ import annotations

import json
import hashlib
import math
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from migrations import (
    LATEST_SCHEMA_VERSION,
    MIGRATION_2_SQL,
    MIGRATION_3_SQL,
    MIGRATION_4_SQL,
    MIGRATION_5_SQL,
    MIGRATION_6_SQL,
    MIGRATION_7_SQL,
    MIGRATION_8_SQL,
    MIGRATION_9_SQL,
)


DEFAULT_DB_PATH = Path("persistent/data/radar.db")
_INITIALIZATION_LOCK = threading.Lock()
_INITIALIZED_PATHS: set[Path] = set()


def database_path() -> Path:
    configured = os.environ.get("RADAR_DB_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_DB_PATH


def _connect(
    path: Path | None = None, *, initialize_journal: bool = False
) -> sqlite3.Connection:
    db_path = path or database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.execute("PRAGMA busy_timeout=30000")
    if initialize_journal:
        connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def _connection(
    path: Path | None = None, *, initialize_journal: bool = False
):
    connection = _connect(path, initialize_journal=initialize_journal)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(path: Path | None = None) -> Path:
    db_path = path or database_path()
    path_key = db_path.resolve()
    with _INITIALIZATION_LOCK:
        if path_key in _INITIALIZED_PATHS:
            return db_path

        with _connection(db_path, initialize_journal=True) as connection:
            connection.executescript(
                """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO schema_metadata(key, value)
            VALUES ('schema_version', '1')
            ON CONFLICT(key) DO NOTHING;

            CREATE TABLE IF NOT EXISTS scan_runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('running', 'success', 'failed')),
                run_mode TEXT,
                domain_profile TEXT,
                attempted_query TEXT,
                parameters_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scan_topic_metrics (
                run_id TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                topic_id TEXT,
                topic TEXT,
                region TEXT,
                metrics_json TEXT NOT NULL,
                PRIMARY KEY(run_id, row_number),
                FOREIGN KEY(run_id) REFERENCES scan_runs(run_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scan_query_log (
                run_id TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                source TEXT,
                topic TEXT,
                region TEXT,
                query_string TEXT,
                result_count INTEGER,
                sample_count INTEGER,
                record_json TEXT NOT NULL,
                PRIMARY KEY(run_id, row_number),
                FOREIGN KEY(run_id) REFERENCES scan_runs(run_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_scan_runs_status_updated
                ON scan_runs(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_topic_metrics_topic_region
                ON scan_topic_metrics(topic, region);
                """
            )
            version_row = connection.execute(
                "SELECT value FROM schema_metadata WHERE key='schema_version'"
            ).fetchone()
            version = int(version_row[0]) if version_row else 1
            if version > LATEST_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema {version} is newer than supported version "
                    f"{LATEST_SCHEMA_VERSION}."
                )
            if version < 2:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_2_SQL
                    + "\nINSERT OR IGNORE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (1, 'legacy scan storage', '{now}');\n"
                    + "INSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (2, 'research intelligence foundation', '{now}');\n"
                    + "UPDATE schema_metadata SET value='2' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 2
            if version < 3:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_3_SQL
                    + "\nINSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (3, 'global 30-day trend analytics', '{now}');\n"
                    + "UPDATE schema_metadata SET value='3' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 3
            if version < 4:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_4_SQL
                    + "\nINSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (4, 'trend data origin audit fields', '{now}');\n"
                    + "UPDATE schema_metadata SET value='4' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 4
            if version < 5:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_5_SQL
                    + "\nINSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (5, 'OpenAlex Topic hotspot analytics', '{now}');\n"
                    + "UPDATE schema_metadata SET value='5' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 5
            if version < 6:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_6_SQL
                    + "\nINSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (6, 'versioned OpenAlex taxonomy scope', '{now}');\n"
                    + "UPDATE schema_metadata SET value='6' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 6
            if version < 7:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_7_SQL
                    + "\nINSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (7, 'CN and US regional Topic analytics', '{now}');\n"
                    + "UPDATE schema_metadata SET value='7' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 7
            if version < 8:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_8_SQL
                    + "\nINSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (8, 'windowed citation rankings', '{now}');\n"
                    + "UPDATE schema_metadata SET value='8' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 8
            if version < 9:
                now = datetime.now().astimezone().isoformat()
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATION_9_SQL
                    + "\nINSERT OR REPLACE INTO schema_migrations(version, name, applied_at) "
                    + f"VALUES (9, 'citation scope audits and resumable cache', '{now}');\n"
                    + "UPDATE schema_metadata SET value='9' WHERE key='schema_version';\n"
                    + "COMMIT;"
                )
                version = 9
        _INITIALIZED_PATHS.add(path_key)
    return db_path


def _clean(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(_clean(value), ensure_ascii=False, sort_keys=True)


def _nullable(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


def _controlled_topic_key(topic_id: Any) -> str:
    return f"controlled:{str(topic_id).strip()}"


def _openalex_topic_key(topic_id: str) -> str:
    return f"openalex:{topic_id.rsplit('/', 1)[-1]}"


def _upsert_intelligence_entities(
    connection: sqlite3.Connection,
    run_id: str,
    result: dict[str, Any],
    now: str,
) -> None:
    topics = result.get("topics")
    if isinstance(topics, pd.DataFrame):
        for row in topics.to_dict("records"):
            topic_id = str(row.get("topic_id") or "").strip()
            if not topic_id:
                continue
            connection.execute(
                """
                INSERT INTO topics(
                    topic_key, openalex_topic_id, label, topic_kind, description,
                    source, first_created_at, last_updated_at
                ) VALUES (?, NULL, ?, 'controlled', NULL, 'radar_controlled_query', ?, ?)
                ON CONFLICT(topic_key) DO UPDATE SET
                    label=excluded.label, last_updated_at=excluded.last_updated_at
                """,
                (_controlled_topic_key(topic_id), row.get("topic") or topic_id, now, now),
            )

    works = result.get("works")
    if not isinstance(works, pd.DataFrame) or works.empty:
        return

    seen_works: set[str] = set()
    author_snapshot_data: dict[str, dict[str, set[str]]] = {}
    for row in works.to_dict("records"):
        work_id = str(row.get("openalex_work_id") or "").strip()
        if not work_id:
            continue
        if work_id not in seen_works:
            connection.execute(
                """
                INSERT INTO works(
                    openalex_work_id, doi, title, publication_date, work_type,
                    source_type, venue, cited_by_count, is_open_access, source,
                    first_created_at, last_updated_at, last_seen_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OpenAlex', ?, ?, ?)
                ON CONFLICT(openalex_work_id) DO UPDATE SET
                    doi=excluded.doi, title=excluded.title,
                    publication_date=excluded.publication_date,
                    work_type=excluded.work_type, source_type=excluded.source_type,
                    venue=excluded.venue, cited_by_count=excluded.cited_by_count,
                    is_open_access=excluded.is_open_access,
                    last_updated_at=excluded.last_updated_at,
                    last_seen_run_id=excluded.last_seen_run_id
                """,
                (
                    work_id,
                    _nullable(row.get("doi")) or None,
                    row.get("title") or "Untitled work",
                    _nullable(row.get("publication_date")),
                    row.get("work_type"),
                    row.get("source_type"),
                    row.get("venue"),
                    int(row.get("citations") or 0),
                    int(bool(row.get("is_open_access"))),
                    now,
                    now,
                    run_id,
                ),
            )
            seen_works.add(work_id)

        controlled_topic_id = str(row.get("controlled_topic_id") or "").strip()
        if controlled_topic_id:
            topic_key = _controlled_topic_key(controlled_topic_id)
            connection.execute(
                """
                INSERT INTO work_topics(
                    work_id, topic_key, score, is_primary, source,
                    first_created_at, last_updated_at
                ) VALUES (?, ?, NULL, 1, 'radar_controlled_query', ?, ?)
                ON CONFLICT(work_id, topic_key) DO UPDATE SET
                    last_updated_at=excluded.last_updated_at
                """,
                (work_id, topic_key, now, now),
            )

        for topic in row.get("openalex_topics") or []:
            topic_id = str(topic.get("openalex_topic_id") or "").strip()
            if not topic_id:
                continue
            topic_key = _openalex_topic_key(topic_id)
            connection.execute(
                """
                INSERT INTO topics(
                    topic_key, openalex_topic_id, label, topic_kind, description,
                    source, first_created_at, last_updated_at
                ) VALUES (?, ?, ?, 'openalex', NULL, 'OpenAlex', ?, ?)
                ON CONFLICT(topic_key) DO UPDATE SET
                    label=excluded.label, last_updated_at=excluded.last_updated_at
                """,
                (topic_key, topic_id, topic.get("display_name") or topic_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO work_topics(
                    work_id, topic_key, score, is_primary, source,
                    first_created_at, last_updated_at
                ) VALUES (?, ?, ?, ?, 'OpenAlex', ?, ?)
                ON CONFLICT(work_id, topic_key) DO UPDATE SET
                    score=excluded.score, is_primary=excluded.is_primary,
                    last_updated_at=excluded.last_updated_at
                """,
                (
                    work_id,
                    topic_key,
                    _nullable(topic.get("score")),
                    int(bool(topic.get("is_primary"))),
                    now,
                    now,
                ),
            )

        for authorship in row.get("authorships_data") or []:
            author_id = str(authorship.get("openalex_author_id") or "").strip()
            if not author_id:
                continue
            connection.execute(
                """
                INSERT INTO authors(
                    openalex_author_id, display_name, orcid, source,
                    first_created_at, last_updated_at
                ) VALUES (?, ?, ?, 'OpenAlex', ?, ?)
                ON CONFLICT(openalex_author_id) DO UPDATE SET
                    display_name=excluded.display_name, orcid=excluded.orcid,
                    last_updated_at=excluded.last_updated_at
                """,
                (
                    author_id,
                    authorship.get("display_name") or author_id,
                    authorship.get("orcid") or None,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO work_authorships(
                    work_id, author_id, author_position, is_corresponding,
                    authorship_order, source, first_created_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, 'OpenAlex', ?, ?)
                ON CONFLICT(work_id, author_id) DO UPDATE SET
                    author_position=excluded.author_position,
                    is_corresponding=excluded.is_corresponding,
                    authorship_order=excluded.authorship_order,
                    last_updated_at=excluded.last_updated_at
                """,
                (
                    work_id,
                    author_id,
                    authorship.get("author_position"),
                    int(bool(authorship.get("is_corresponding"))),
                    authorship.get("authorship_order"),
                    now,
                    now,
                ),
            )
            authorship_id = connection.execute(
                "SELECT authorship_id FROM work_authorships WHERE work_id=? AND author_id=?",
                (work_id, author_id),
            ).fetchone()[0]
            for institution in authorship.get("institutions") or []:
                institution_id = str(institution.get("openalex_institution_id") or "").strip()
                if not institution_id:
                    continue
                connection.execute(
                    """
                    INSERT INTO institutions(
                        openalex_institution_id, display_name, country_code,
                        institution_type, ror, source, first_created_at, last_updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'OpenAlex', ?, ?)
                    ON CONFLICT(openalex_institution_id) DO UPDATE SET
                        display_name=excluded.display_name,
                        country_code=excluded.country_code,
                        institution_type=excluded.institution_type,
                        ror=excluded.ror,
                        last_updated_at=excluded.last_updated_at
                    """,
                    (
                        institution_id,
                        institution.get("display_name") or institution_id,
                        institution.get("country_code"),
                        institution.get("institution_type"),
                        institution.get("ror") or None,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO work_authorship_institutions(
                        authorship_id, institution_id, source,
                        first_created_at, last_updated_at
                    ) VALUES (?, ?, 'OpenAlex', ?, ?)
                    ON CONFLICT(authorship_id, institution_id) DO UPDATE SET
                        last_updated_at=excluded.last_updated_at
                    """,
                    (authorship_id, institution_id, now, now),
                )
            author_data = author_snapshot_data.setdefault(
                author_id, {"works": set(), "topics": set()}
            )
            author_data["works"].add(work_id)
            if controlled_topic_id:
                author_data["topics"].add(controlled_topic_id)

        _upsert_candidate_group(connection, run_id, row, work_id, now)

    _save_snapshots(connection, run_id, result, author_snapshot_data, now)


def _upsert_candidate_group(
    connection: sqlite3.Connection,
    run_id: str,
    row: dict[str, Any],
    work_id: str,
    now: str,
) -> None:
    group_name = str(row.get("group_name") or "").strip()
    if not group_name:
        return
    institution_id = str(row.get("institution_id") or "").strip() or None
    leader_id = str(row.get("leader_id") or "").strip() or None
    confidence = "medium" if row.get("group_confidence") in {"中", "中高"} else "low"
    identity = "|".join([group_name, institution_id or "", leader_id or ""])
    group_id = "candidate:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    connection.execute(
        """
        INSERT INTO research_groups(
            group_id, canonical_name, institution_id, status, confidence,
            source, first_created_at, last_updated_at
        ) VALUES (?, ?, ?, 'candidate', ?, 'OpenAlex inference', ?, ?)
        ON CONFLICT(group_id) DO UPDATE SET
            canonical_name=excluded.canonical_name,
            institution_id=excluded.institution_id,
            confidence=excluded.confidence,
            last_updated_at=excluded.last_updated_at
        """,
        (group_id, group_name, institution_id, confidence, now, now),
    )
    evidence_identity = f"{group_id}|{work_id}|{leader_id or ''}|{run_id}"
    evidence_id = hashlib.sha256(evidence_identity.encode("utf-8")).hexdigest()
    connection.execute(
        """
        INSERT INTO research_group_evidence(
            evidence_id, group_id, work_id, author_id, evidence_type,
            evidence_url, evidence_text, confidence, verification_status,
            observed_at, valid_from, valid_to, source,
            first_created_at, last_updated_at
        ) VALUES (?, ?, ?, ?, 'openalex_authorship_candidate', ?, ?, ?,
                  'candidate', ?, ?, NULL, 'OpenAlex', ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
            evidence_text=excluded.evidence_text,
            confidence=excluded.confidence,
            last_updated_at=excluded.last_updated_at
        """,
        (
            evidence_id,
            group_id,
            work_id,
            leader_id,
            row.get("link"),
            row.get("attribution_basis") or "OpenAlex authorship candidate",
            confidence,
            now,
            _nullable(row.get("publication_date")),
            now,
            now,
        ),
    )


def _save_snapshots(
    connection: sqlite3.Connection,
    run_id: str,
    result: dict[str, Any],
    author_snapshot_data: dict[str, dict[str, set[str]]],
    now: str,
) -> None:
    snapshot_date = now[:10]
    algorithm_version = str(result.get("algorithm_version") or "unknown")
    topics = result.get("topics")
    if isinstance(topics, pd.DataFrame):
        for row in topics.to_dict("records"):
            topic_id = str(row.get("topic_id") or "").strip()
            region = str(row.get("region") or "").strip()
            if not topic_id or not region:
                continue
            connection.execute(
                """
                INSERT INTO topic_snapshots(
                    run_id, topic_key, region, snapshot_date, window_start, window_end,
                    total_count, sampled_count, coverage_rate, sample_truncated,
                    growth_rate, adjusted_growth_rate, acceleration,
                    institution_count, institution_count_is_complete, author_count,
                    data_confidence, heat_score, score_coverage, algorithm_version,
                    query_string, coverage_comparability, source,
                    first_created_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'OpenAlex', ?, ?)
                ON CONFLICT(run_id, topic_key, region) DO UPDATE SET
                    total_count=excluded.total_count,
                    sampled_count=excluded.sampled_count,
                    coverage_rate=excluded.coverage_rate,
                    sample_truncated=excluded.sample_truncated,
                    growth_rate=excluded.growth_rate,
                    adjusted_growth_rate=excluded.adjusted_growth_rate,
                    acceleration=excluded.acceleration,
                    institution_count=excluded.institution_count,
                    institution_count_is_complete=excluded.institution_count_is_complete,
                    author_count=excluded.author_count,
                    data_confidence=excluded.data_confidence,
                    heat_score=excluded.heat_score,
                    score_coverage=excluded.score_coverage,
                    algorithm_version=excluded.algorithm_version,
                    query_string=excluded.query_string,
                    coverage_comparability=excluded.coverage_comparability,
                    last_updated_at=excluded.last_updated_at
                """,
                (
                    run_id,
                    _controlled_topic_key(topic_id),
                    region,
                    snapshot_date,
                    str(_nullable(result.get("current_start")) or ""),
                    str(_nullable(result.get("current_end")) or ""),
                    _nullable(row.get("total_count", row.get("current_count"))),
                    _nullable(row.get("sampled_count")),
                    _nullable(row.get("coverage_rate")),
                    int(bool(row.get("sample_truncated"))),
                    _nullable(row.get("growth")),
                    _nullable(row.get("adjusted_growth")),
                    _nullable(row.get("acceleration")),
                    _nullable(row.get("institution_breadth")),
                    int(bool(row.get("institution_count_is_complete"))),
                    _nullable(row.get("author_breadth")),
                    _nullable(row.get("data_confidence")),
                    _nullable(row.get("score")),
                    _nullable(row.get("score_coverage")),
                    str(row.get("algorithm_version") or algorithm_version),
                    row.get("query_string"),
                    row.get("coverage_comparability"),
                    now,
                    now,
                ),
            )

    institutions = result.get("institutions")
    if isinstance(institutions, pd.DataFrame):
        for row in institutions.to_dict("records"):
            institution_id = str(row.get("institution_id") or "").strip()
            if not institution_id:
                continue
            connection.execute(
                """
                INSERT INTO institution_snapshots(
                    run_id, institution_id, snapshot_date, sampled_work_count,
                    topic_count, count_scope, data_confidence, source,
                    first_created_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, 'sample', NULL, 'OpenAlex', ?, ?)
                ON CONFLICT(run_id, institution_id) DO UPDATE SET
                    sampled_work_count=excluded.sampled_work_count,
                    topic_count=excluded.topic_count,
                    last_updated_at=excluded.last_updated_at
                """,
                (
                    run_id,
                    institution_id,
                    snapshot_date,
                    int(row.get("works") or 0),
                    len([item for item in str(row.get("topics") or "").split("；") if item]),
                    now,
                    now,
                ),
            )

    for author_id, values in author_snapshot_data.items():
        connection.execute(
            """
            INSERT INTO author_snapshots(
                run_id, author_id, snapshot_date, sampled_work_count,
                topic_count, count_scope, data_confidence, source,
                first_created_at, last_updated_at
            ) VALUES (?, ?, ?, ?, ?, 'sample', NULL, 'OpenAlex', ?, ?)
            ON CONFLICT(run_id, author_id) DO UPDATE SET
                sampled_work_count=excluded.sampled_work_count,
                topic_count=excluded.topic_count,
                last_updated_at=excluded.last_updated_at
            """,
            (
                run_id,
                author_id,
                snapshot_date,
                len(values["works"]),
                len(values["topics"]),
                now,
                now,
            ),
        )


def save_run(
    run_state: dict[str, Any],
    *,
    parameters: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    path: Path | None = None,
) -> None:
    db_path = initialize_database(path)
    now = datetime.now().astimezone().isoformat()
    status = str(run_state.get("status", "failed"))
    if status not in {"running", "success", "failed"}:
        return

    completed_at = run_state.get("completed_at") or (now if status != "running" else None)
    with _connection(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO scan_runs(
                run_id, status, run_mode, domain_profile, attempted_query,
                parameters_json, error, started_at, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                run_mode=excluded.run_mode,
                domain_profile=excluded.domain_profile,
                attempted_query=excluded.attempted_query,
                parameters_json=excluded.parameters_json,
                error=excluded.error,
                completed_at=excluded.completed_at,
                updated_at=excluded.updated_at
            """,
            (
                run_state["run_id"],
                status,
                run_state.get("run_mode"),
                run_state.get("domain_profile"),
                run_state.get("attempted_query", ""),
                _json(parameters or {}),
                run_state.get("error", ""),
                run_state.get("started_at") or now,
                completed_at,
                now,
            ),
        )

        if result is not None and status == "success":
            connection.execute("DELETE FROM scan_topic_metrics WHERE run_id=?", (run_state["run_id"],))
            connection.execute("DELETE FROM scan_query_log WHERE run_id=?", (run_state["run_id"],))

            topics = result.get("topics")
            if isinstance(topics, pd.DataFrame):
                for index, row in enumerate(topics.to_dict("records")):
                    connection.execute(
                        """
                        INSERT INTO scan_topic_metrics(
                            run_id, row_number, topic_id, topic, region, metrics_json
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_state["run_id"],
                            index,
                            row.get("topic_id"),
                            row.get("topic"),
                            row.get("region"),
                            _json(row),
                        ),
                    )

            for index, record in enumerate(result.get("query_log") or []):
                connection.execute(
                    """
                    INSERT INTO scan_query_log(
                        run_id, row_number, source, topic, region, query_string,
                        result_count, sample_count, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_state["run_id"],
                        index,
                        record.get("source"),
                        record.get("topic"),
                        record.get("region"),
                        record.get("query"),
                        record.get("result_count"),
                        record.get("sample_count"),
                        _json(record),
                    ),
                )

            _upsert_intelligence_entities(
                connection, str(run_state["run_id"]), result, now
            )


def database_summary(path: Path | None = None) -> dict[str, Any]:
    db_path = initialize_database(path)
    with _connection(db_path) as connection:
        version = int(
            connection.execute(
                "SELECT value FROM schema_metadata WHERE key='schema_version'"
            ).fetchone()[0]
        )
        runs = connection.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        successes = connection.execute(
            "SELECT COUNT(*) FROM scan_runs WHERE status='success'"
        ).fetchone()[0]
        works = connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        snapshots = connection.execute("SELECT COUNT(*) FROM topic_snapshots").fetchone()[0]
    return {
        "path": str(db_path),
        "schema_version": version,
        "runs": runs,
        "successful_runs": successes,
        "works": works,
        "topic_snapshots": snapshots,
    }
