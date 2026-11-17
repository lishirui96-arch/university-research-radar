from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


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


def initialize_database(path: Path | None = None) -> Path:
    db_path = path or database_path()
    path_key = db_path.resolve()
    with _INITIALIZATION_LOCK:
        if path_key in _INITIALIZED_PATHS:
            return db_path

        with _connect(db_path, initialize_journal=True) as connection:
            connection.executescript(
                """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO schema_metadata(key, value)
            VALUES ('schema_version', '1')
            ON CONFLICT(key) DO UPDATE SET value=excluded.value;

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
        _INITIALIZED_PATHS.add(path_key)
    return db_path


def _clean(value: Any) -> Any:
    if value is None:
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
    with _connect(db_path) as connection:
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


def database_summary(path: Path | None = None) -> dict[str, Any]:
    db_path = initialize_database(path)
    with _connect(db_path) as connection:
        runs = connection.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        successes = connection.execute(
            "SELECT COUNT(*) FROM scan_runs WHERE status='success'"
        ).fetchone()[0]
    return {"path": str(db_path), "runs": runs, "successful_runs": successes}
