from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from storage import initialize_database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def query_hash(endpoint: str, parameters: dict[str, Any], select_fields: tuple[str, ...]) -> str:
    payload = canonical_json(
        {"endpoint": endpoint, "parameters": parameters, "select": select_fields}
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JobHandle:
    job_id: str
    batch_id: str
    status: str


class CollectionRepository:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        initialize_database(self.db_path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def ensure_job(
        self,
        *,
        job_type: str,
        logical_date: str,
        shard_key: str = "",
        max_attempts: int = 5,
        source: str = "OpenAlex",
        code_version: str | None = None,
    ) -> JobHandle:
        now = utc_now()
        with self.connection() as connection:
            existing = connection.execute(
                """
                SELECT job_id, batch_id, status FROM collection_jobs
                WHERE job_type=? AND logical_date=? AND shard_key=?
                """,
                (job_type, logical_date, shard_key),
            ).fetchone()
            if existing:
                return JobHandle(existing["job_id"], existing["batch_id"], existing["status"])
            batch_id = str(uuid.uuid4())
            job_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO snapshot_batches(
                    batch_id, batch_type, logical_date, status, source, code_version,
                    schema_version, started_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'collecting', ?, ?, 5, ?, ?, ?)
                """,
                (batch_id, job_type, logical_date, source, code_version, now, now, now),
            )
            connection.execute(
                """
                INSERT INTO collection_jobs(
                    job_id, job_type, logical_date, shard_key, status, max_attempts,
                    batch_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (job_id, job_type, logical_date, shard_key, max_attempts, batch_id, now, now),
            )
            return JobHandle(job_id, batch_id, "pending")

    def acquire_job(
        self, job_id: str, *, worker_id: str, lease_seconds: int = 900
    ) -> tuple[bool, int | None]:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_expires = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, lease_expires_at, attempt_count, max_attempts
                FROM collection_jobs WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise KeyError(f"Unknown collection job: {job_id}")
            status, current_expiry, attempt_count, max_attempts = row
            active_lease = (
                status in {"leased", "running", "validating"}
                and current_expiry
                and current_expiry > now
            )
            if status == "succeeded" or active_lease or attempt_count >= max_attempts:
                connection.execute("ROLLBACK")
                return False, None
            attempt_number = attempt_count + 1
            connection.execute(
                """
                UPDATE collection_jobs SET status='running', leased_by=?,
                    lease_expires_at=?, attempt_count=?, next_retry_at=NULL, updated_at=?
                WHERE job_id=?
                """,
                (worker_id, lease_expires, attempt_number, now, job_id),
            )
            connection.execute(
                """
                INSERT INTO collection_job_attempts(
                    job_id, attempt_number, status, started_at, created_at, updated_at
                ) VALUES (?, ?, 'running', ?, ?, ?)
                """,
                (job_id, attempt_number, now, now, now),
            )
            connection.execute("COMMIT")
            return True, attempt_number
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def checkpoint(self, job_id: str, key: str = "cursor") -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM collection_checkpoints WHERE job_id=? AND checkpoint_key=?",
                (job_id, key),
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["state"] = json.loads(result.pop("state_json") or "{}")
            return result

    def batch_status(self, batch_id: str) -> str:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT status FROM snapshot_batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown snapshot batch: {batch_id}")
            return str(row[0])

    def save_checkpoint(
        self,
        connection: sqlite3.Connection,
        *,
        job_id: str,
        cursor: str | None,
        page_number: int,
        records_processed: int,
        state: dict[str, Any],
        key: str = "cursor",
        lease_seconds: int = 900,
    ) -> None:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_expires = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        connection.execute(
            """
            INSERT INTO collection_checkpoints(
                job_id, checkpoint_key, cursor_value, page_number,
                records_processed, state_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, checkpoint_key) DO UPDATE SET
                cursor_value=excluded.cursor_value,
                page_number=excluded.page_number,
                records_processed=excluded.records_processed,
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            """,
            (job_id, key, cursor, page_number, records_processed, canonical_json(state), now),
        )
        connection.execute(
            """
            UPDATE collection_jobs SET lease_expires_at=?, updated_at=?
            WHERE job_id=? AND status IN ('leased', 'running', 'validating')
            """,
            (lease_expires, now, job_id),
        )

    def finish_attempt(
        self,
        *,
        job_id: str,
        attempt_number: int,
        success: bool,
        request_count: int,
        response_bytes: int,
        retry_count: int,
        error: Exception | None = None,
        interrupted: bool = False,
    ) -> None:
        now = utc_now()
        attempt_status = "interrupted" if interrupted else ("succeeded" if success else "failed")
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE collection_job_attempts SET status=?, completed_at=?,
                    request_count=?, response_bytes=?, retry_count=?, error_type=?,
                    error_message=?, updated_at=?
                WHERE job_id=? AND attempt_number=?
                """,
                (
                    attempt_status,
                    now,
                    request_count,
                    response_bytes,
                    retry_count,
                    type(error).__name__ if error else None,
                    str(error)[:1000] if error else None,
                    now,
                    job_id,
                    attempt_number,
                ),
            )
            if success:
                job_status = "succeeded"
            elif interrupted:
                job_status = "pending"
            else:
                row = connection.execute(
                    "SELECT attempt_count, max_attempts FROM collection_jobs WHERE job_id=?",
                    (job_id,),
                ).fetchone()
                job_status = "failed" if row and row[0] >= row[1] else "retry_wait"
            connection.execute(
                """
                UPDATE collection_jobs SET status=?, leased_by=NULL,
                    lease_expires_at=NULL, updated_at=? WHERE job_id=?
                """,
                (job_status, now, job_id),
            )
            if job_status == "failed":
                connection.execute(
                    """
                    UPDATE snapshot_batches SET status='failed', error=?,
                        completed_at=?, updated_at=?
                    WHERE batch_id=(SELECT batch_id FROM collection_jobs WHERE job_id=?)
                    """,
                    (str(error)[:1000] if error else "Task failed", now, now, job_id),
                )

    def add_quality_report(
        self,
        *,
        batch_id: str,
        check_name: str,
        severity: str,
        status: str,
        expected: Any,
        actual: Any,
        details: str = "",
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO data_quality_reports(
                    report_id, batch_id, check_name, severity, status,
                    expected_json, actual_json, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(batch_id, check_name) DO UPDATE SET
                    severity=excluded.severity, status=excluded.status,
                    expected_json=excluded.expected_json,
                    actual_json=excluded.actual_json, details=excluded.details,
                    created_at=excluded.created_at
                """,
                (
                    str(uuid.uuid4()), batch_id, check_name, severity, status,
                    canonical_json(expected), canonical_json(actual), details, utc_now(),
                ),
            )

    def record_query_audit(
        self,
        *,
        batch_id: str,
        job_id: str,
        endpoint: str,
        parameters: dict[str, Any],
        select_fields: tuple[str, ...],
        requested_at: str,
        completed_at: str,
        total_count: int | None,
        sampled_count: int,
        request_count: int,
        response_bytes: int,
        retry_count: int,
        rate_limit: int | None,
        rate_remaining: int | None,
        rate_reset_seconds: int | None,
        is_truncated: bool,
    ) -> None:
        coverage = (
            sampled_count / total_count if total_count and total_count > 0 else None
        )
        safe_parameters = {key: value for key, value in parameters.items() if key != "api_key"}
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO source_query_audit(
                    query_id, batch_id, job_id, endpoint, query_hash,
                    parameters_json, select_fields, requested_at, completed_at,
                    http_status, total_count, sampled_count, coverage_rate,
                    is_truncated, request_count, response_bytes, retry_count,
                    rate_limit, rate_remaining, rate_reset_seconds, source,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 200, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    'OpenAlex', ?, ?)
                """,
                (
                    str(uuid.uuid4()), batch_id, job_id, endpoint,
                    query_hash(endpoint, safe_parameters, select_fields),
                    canonical_json(safe_parameters), ",".join(select_fields),
                    requested_at, completed_at, total_count, sampled_count,
                    coverage, int(is_truncated), request_count, response_bytes,
                    retry_count, rate_limit, rate_remaining, rate_reset_seconds,
                    now, now,
                ),
            )

    def mark_batch_validated(self, batch_id: str, stats: dict[str, Any]) -> None:
        now = utc_now()
        with self.connection() as connection:
            failed = connection.execute(
                "SELECT COUNT(*) FROM data_quality_reports WHERE batch_id=? AND status='failed'",
                (batch_id,),
            ).fetchone()[0]
            if failed:
                raise RuntimeError("Batch has failed data-quality checks and cannot be validated.")
            connection.execute(
                """
                UPDATE snapshot_batches SET status='validated', stats_json=?,
                    completed_at=?, updated_at=? WHERE batch_id=? AND status!='failed'
                """,
                (canonical_json(stats), now, now, batch_id),
            )

    def publish_batch(self, *, batch_id: str, snapshot_type: str) -> None:
        now = utc_now()
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM snapshot_batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if row is None or row[0] != "validated":
                connection.execute("ROLLBACK")
                raise RuntimeError("Only a validated batch can be published.")
            connection.execute(
                """
                INSERT INTO published_snapshots(snapshot_type, batch_id, published_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_type) DO UPDATE SET
                    batch_id=excluded.batch_id,
                    published_at=excluded.published_at,
                    updated_at=excluded.updated_at
                """,
                (snapshot_type, batch_id, now, now),
            )
            connection.execute(
                """
                UPDATE snapshot_batches SET status='published', published_at=?, updated_at=?
                WHERE batch_id=?
                """,
                (now, now, batch_id),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def create_daily_run(
        self,
        *,
        run_id: str,
        run_date: str,
        timezone_name: str,
        trigger_kind: str,
        scheduled_for: str | None,
        request_budget: int,
        backup_path: str | None,
    ) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO daily_collection_runs(
                    run_id, run_date, timezone_name, trigger_kind, scheduled_for,
                    status, started_at, request_budget, backup_path,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                (
                    run_id, run_date, timezone_name, trigger_kind, scheduled_for,
                    now, request_budget, backup_path, now, now,
                ),
            )

    def finish_daily_run(
        self,
        *,
        run_id: str,
        status: str,
        window_count: int,
        completed_windows: int,
        failed_windows: int,
        request_count: int,
        response_bytes: int,
        retry_count: int,
        rate_remaining: int | None,
        report_path: str | None,
        error: str = "",
    ) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE daily_collection_runs SET status=?, completed_at=?,
                    window_count=?, completed_windows=?, failed_windows=?,
                    request_count=?, response_bytes=?, retry_count=?,
                    rate_remaining=?, report_path=?, error=?, updated_at=?
                WHERE run_id=?
                """,
                (
                    status, now, window_count, completed_windows, failed_windows,
                    request_count, response_bytes, retry_count, rate_remaining,
                    report_path, error[:1000], now, run_id,
                ),
            )

    def last_successful_daily_run_date(self) -> str | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT MAX(run_date) FROM daily_collection_runs
                WHERE status='succeeded'
                """
            ).fetchone()
            return str(row[0]) if row and row[0] else None

    def upsert_daily_window(
        self,
        *,
        run_id: str,
        publication_date: str,
        reasons: list[str],
        priority: int,
        preflight_meta_count: int | None = None,
        estimated_requests: int | None = None,
        status: str = "pending",
    ) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO daily_collection_windows(
                    run_id, publication_date, reasons_json, priority,
                    preflight_meta_count, estimated_requests, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, publication_date) DO UPDATE SET
                    reasons_json=excluded.reasons_json,
                    priority=excluded.priority,
                    preflight_meta_count=COALESCE(excluded.preflight_meta_count, daily_collection_windows.preflight_meta_count),
                    estimated_requests=COALESCE(excluded.estimated_requests, daily_collection_windows.estimated_requests),
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id, publication_date, canonical_json(reasons), priority,
                    preflight_meta_count, estimated_requests, status, now, now,
                ),
            )

    def update_daily_window(
        self,
        *,
        run_id: str,
        publication_date: str,
        status: str,
        job_id: str | None = None,
        batch_id: str | None = None,
        skip_reason: str = "",
        error: str = "",
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE daily_collection_windows SET status=?,
                    job_id=COALESCE(?, job_id), batch_id=COALESCE(?, batch_id),
                    skip_reason=?, error=?, updated_at=?
                WHERE run_id=? AND publication_date=?
                """,
                (
                    status, job_id, batch_id, skip_reason, error[:1000], utc_now(),
                    run_id, publication_date,
                ),
            )

    def mark_work_date_rechecking(self, publication_date: str, run_id: str | None) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO work_date_status(
                    publication_date, status, last_run_id, updated_at
                ) VALUES (?, 'rechecking', ?, ?)
                ON CONFLICT(publication_date) DO UPDATE SET
                    status='rechecking', last_run_id=excluded.last_run_id,
                    updated_at=excluded.updated_at
                """,
                (publication_date, run_id, now),
            )

    def mark_work_date_failed(self, publication_date: str, run_id: str | None) -> None:
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO work_date_status(
                    publication_date, status, last_run_id, updated_at
                ) VALUES (?, 'failed', ?, ?)
                ON CONFLICT(publication_date) DO UPDATE SET
                    status='failed', last_run_id=excluded.last_run_id,
                    updated_at=excluded.updated_at
                """,
                (publication_date, run_id, now),
            )

    @staticmethod
    def record_entity_change(
        connection: sqlite3.Connection,
        *,
        batch_id: str,
        entity_type: str,
        entity_key: str,
        change_type: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO collection_entity_changes(
                batch_id, entity_type, entity_key, change_type, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (batch_id, entity_type, entity_key, change_type, utc_now()),
        )

    def entity_change_counts(self, batch_id: str) -> dict[str, int]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT entity_type, change_type, COUNT(*)
                FROM collection_entity_changes WHERE batch_id=?
                GROUP BY entity_type, change_type
                """,
                (batch_id,),
            ).fetchall()
        return {f"{row[0]}_{row[1]}": int(row[2]) for row in rows}

    def work_type_statistics(self, publication_date: str) -> dict[str, Any] | None:
        """Return type counts from the latest published observation for a date."""
        with self.connection() as connection:
            observation = connection.execute(
                """
                SELECT observation.batch_id, observation.meta_count,
                       observation.sampled_count, observation.observed_at
                FROM work_date_observations observation
                WHERE observation.publication_date=? AND observation.published=1
                  AND observation.quality_status='passed'
                ORDER BY observation.observed_at DESC LIMIT 1
                """,
                (publication_date,),
            ).fetchone()
            if observation is None:
                return None
            rows = connection.execute(
                """
                SELECT raw_type, normalized_group, work_count
                FROM work_type_observations WHERE batch_id=?
                ORDER BY raw_type
                """,
                (observation["batch_id"],),
            ).fetchall()
        raw = {str(row[0]): int(row[2]) for row in rows}
        grouped: dict[str, int] = {}
        for row in rows:
            grouped[str(row[1])] = grouped.get(str(row[1]), 0) + int(row[2])
        return {
            "publication_date": publication_date,
            "batch_id": str(observation["batch_id"]),
            "observed_at": str(observation["observed_at"]),
            "total_count": int(observation["meta_count"]),
            "sampled_count": int(observation["sampled_count"]),
            "raw_types": raw,
            "normalized_groups": grouped,
        }

    def publish_works_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        publication_date: str,
        local_run_date: str,
        meta_count: int,
        sampled_count: int,
        is_truncated: bool,
        unchanged_works: int,
        request_count: int,
        response_bytes: int,
        retry_count: int,
        rate_remaining: int | None,
        type_counts: dict[str, int],
    ) -> dict[str, Any]:
        now = utc_now()
        changes = self.entity_change_counts(batch_id)
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            batch = connection.execute(
                "SELECT status FROM snapshot_batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if batch is None or batch["status"] != "validated":
                connection.execute("ROLLBACK")
                raise RuntimeError("Only a validated Works batch can be published.")
            existing = connection.execute(
                "SELECT * FROM work_date_observations WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if existing:
                connection.execute("ROLLBACK")
                return dict(existing)
            previous = connection.execute(
                """
                SELECT meta_count FROM work_date_observations
                WHERE publication_date=? AND published=1 AND quality_status='passed'
                ORDER BY observed_at DESC LIMIT 1
                """,
                (publication_date,),
            ).fetchone()
            status_row = connection.execute(
                "SELECT * FROM work_date_status WHERE publication_date=?",
                (publication_date,),
            ).fetchone()
            previous_count = int(previous[0]) if previous else None
            count_delta = meta_count - previous_count if previous_count is not None else None
            prior_successes = int(status_row["successful_observations"] or 0) if status_row else 0
            prior_unchanged = int(status_row["consecutive_unchanged"] or 0) if status_row else 0
            successful_observations = prior_successes + 1
            consecutive_unchanged = (
                prior_unchanged + 1
                if previous_count is not None and previous_count == meta_count
                else 0
            )
            age_days = (date.fromisoformat(local_run_date) - date.fromisoformat(publication_date)).days
            if successful_observations >= 3 and consecutive_unchanged >= 2 and age_days >= 3:
                stability_status = "stable"
            elif consecutive_unchanged >= 1:
                stability_status = "stabilizing"
            else:
                stability_status = "provisional"
            next_days = 7 if stability_status == "stable" else 1
            next_recheck = (date.fromisoformat(local_run_date) + timedelta(days=next_days)).isoformat()
            observation_id = str(uuid.uuid4())
            coverage = sampled_count / meta_count if meta_count > 0 else None
            inserted_works = changes.get("work_inserted", 0)
            updated_works = changes.get("work_updated", 0)
            authors_inserted = changes.get("author_inserted", 0)
            authors_updated = changes.get("author_updated", 0)
            institution_changes = sum(
                count for key, count in changes.items()
                if key.startswith("institution_relation_")
            )
            topic_changes = sum(
                count for key, count in changes.items()
                if key.startswith("topic_relation_")
            )
            connection.execute(
                """
                INSERT INTO work_date_observations(
                    observation_id, publication_date, batch_id, run_id, observed_at,
                    meta_count, previous_meta_count, count_delta, sampled_count,
                    coverage_rate, is_truncated, inserted_works, updated_works,
                    unchanged_works, authors_inserted, authors_updated,
                    institution_relationship_changes, topic_relationship_changes,
                    request_count, response_bytes, retry_count, rate_remaining,
                    quality_status, stability_status, published, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, 'passed', ?, 1, 'OpenAlex', ?)
                """,
                (
                    observation_id, publication_date, batch_id, run_id, now,
                    meta_count, previous_count, count_delta, sampled_count,
                    coverage, int(is_truncated), inserted_works, updated_works,
                    unchanged_works, authors_inserted, authors_updated,
                    institution_changes, topic_changes, request_count,
                    response_bytes, retry_count, rate_remaining, stability_status, now,
                ),
            )
            normalized_counts: dict[tuple[str, str], int] = {}
            for raw_type, count in type_counts.items():
                group = normalize_work_type(raw_type)
                normalized_counts[(raw_type, group)] = count
            for (raw_type, group), count in normalized_counts.items():
                connection.execute(
                    """
                    INSERT INTO work_type_observations(
                        batch_id, raw_type, normalized_group, work_count, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (batch_id, raw_type, group, count, now),
                )
            connection.execute(
                """
                INSERT INTO work_date_status(
                    publication_date, status, first_observed_at, last_observed_at,
                    last_meta_count, successful_observations, consecutive_unchanged,
                    last_batch_id, last_run_id, next_recheck_after, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(publication_date) DO UPDATE SET
                    status=excluded.status,
                    first_observed_at=COALESCE(work_date_status.first_observed_at, excluded.first_observed_at),
                    last_observed_at=excluded.last_observed_at,
                    last_meta_count=excluded.last_meta_count,
                    successful_observations=excluded.successful_observations,
                    consecutive_unchanged=excluded.consecutive_unchanged,
                    last_batch_id=excluded.last_batch_id,
                    last_run_id=excluded.last_run_id,
                    next_recheck_after=excluded.next_recheck_after,
                    updated_at=excluded.updated_at
                """,
                (
                    publication_date, stability_status, now, now, meta_count,
                    successful_observations, consecutive_unchanged, batch_id,
                    run_id, next_recheck, now,
                ),
            )
            snapshot_type = f"daily_ingest:{publication_date}"
            connection.execute(
                """
                INSERT INTO published_snapshots(snapshot_type, batch_id, published_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_type) DO UPDATE SET
                    batch_id=excluded.batch_id,
                    published_at=excluded.published_at,
                    updated_at=excluded.updated_at
                """,
                (snapshot_type, batch_id, now, now),
            )
            connection.execute(
                """
                UPDATE snapshot_batches SET status='published', published_at=?, updated_at=?
                WHERE batch_id=?
                """,
                (now, now, batch_id),
            )
            connection.execute("COMMIT")
            return {
                "observation_id": observation_id,
                "previous_meta_count": previous_count,
                "count_delta": count_delta,
                "stability_status": stability_status,
                "inserted_works": inserted_works,
                "updated_works": updated_works,
                "unchanged_works": unchanged_works,
                "authors_inserted": authors_inserted,
                "authors_updated": authors_updated,
                "institution_relationship_changes": institution_changes,
                "topic_relationship_changes": topic_changes,
            }
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


def normalize_work_type(raw_type: str | None) -> str:
    value = (raw_type or "other").strip().lower()
    if value in {"article", "review"}:
        return "article_review"
    if value == "conference-paper":
        return "conference_paper"
    if value == "preprint":
        return "preprint"
    if value in {"dataset", "software"}:
        return "dataset_software"
    if value == "report":
        return "report"
    if value == "book":
        return "book"
    if value == "dissertation":
        return "dissertation"
    return "other"

