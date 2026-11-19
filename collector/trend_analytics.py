from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import requests

from storage import initialize_database


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
CORE_CORPUS_FILTER = "primary_location.source.is_core:true"
CATEGORY_ORDER = (
    "robotics_embodied",
    "ai_chip_packaging",
    "new_energy_storage",
    "advanced_materials",
    "bio_manufacturing",
)
MAPPING_VERSION = "v1"
QUERY_VERSION = "trend-openalex-primary-topic-core-v1"
CALCULATION_VERSION = "rolling-30d-direct-count-v1"
USER_AGENT = "UniversityResearchRadar/1.1 (global-trend-collector)"
DATA_ORIGINS = (
    "historical_backfill",
    "daily_live",
    "historical_revision",
)


@dataclass(frozen=True)
class TrendCategory:
    category_id: str
    name: str
    topic_ids: tuple[str, ...]


@dataclass(frozen=True)
class QueryTask:
    category: TrendCategory
    snapshot_date: date
    window_start: date
    window_end: date


@dataclass
class QueryOutcome:
    request_status: str
    http_status: int | None
    works_count: int | None
    query_as_of: str
    duration_ms: float
    retry_count: int
    error_message: str | None
    rate_limit_limit: int | None
    rate_limit_remaining: int | None
    rate_limit_reset: str | None
    query_filter: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_categories(mapping_path: Path) -> list[TrendCategory]:
    with mapping_path.open(encoding="utf-8") as handle:
        mapping = json.load(handle)

    if mapping.get("version") != MAPPING_VERSION:
        raise ValueError(f"Expected topic mapping {MAPPING_VERSION}")
    contract = mapping.get("counting_contract", {})
    expected_contract = {
        "entity": "works",
        "geography": "global",
        "corpus_filter": CORE_CORPUS_FILTER,
        "topic_filter": "primary_topic.id",
        "date_filter": "publication_date",
        "window_days": 30,
        "included_status": "approved",
    }
    mismatches = {
        key: (contract.get(key), value)
        for key, value in expected_contract.items()
        if contract.get(key) != value
    }
    if mismatches:
        raise ValueError(f"Topic mapping counting contract mismatch: {mismatches}")

    configured = mapping.get("categories", {})
    if set(configured) != set(CATEGORY_ORDER):
        raise ValueError("Topic mapping must contain exactly the five V1 categories")

    categories: list[TrendCategory] = []
    approved_seen: set[str] = set()
    for category_id in CATEGORY_ORDER:
        category = configured[category_id]
        topic_ids = tuple(
            item["openalex_topic_id"]
            for item in category.get("topics", [])
            if item.get("status") == "approved"
        )
        if not topic_ids:
            raise ValueError(f"Category {category_id} has no approved topics")
        duplicates = approved_seen.intersection(topic_ids)
        if duplicates:
            raise ValueError(f"Approved topics are assigned to multiple categories: {duplicates}")
        approved_seen.update(topic_ids)
        categories.append(TrendCategory(category_id, category["name"], topic_ids))
    return categories


def rolling_window(snapshot_date: date) -> tuple[date, date]:
    return snapshot_date - timedelta(days=29), snapshot_date


def build_query_filter(task: QueryTask) -> str:
    return ",".join(
        [
            CORE_CORPUS_FILTER,
            f"from_publication_date:{task.window_start.isoformat()}",
            f"to_publication_date:{task.window_end.isoformat()}",
            f"primary_topic.id:{'|'.join(task.category.topic_ids)}",
        ]
    )


def build_tasks(
    categories: Iterable[TrendCategory], snapshot_dates: Iterable[date]
) -> list[QueryTask]:
    tasks: list[QueryTask] = []
    for snapshot_date in sorted(set(snapshot_dates)):
        start, end = rolling_window(snapshot_date)
        tasks.extend(QueryTask(category, snapshot_date, start, end) for category in categories)
    return tasks


def _header_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _response_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:1000].replace("\n", " ")
    return str(payload.get("message") or payload.get("error") or payload)[:1000]


class TrendOpenAlexClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 35.0,
        max_attempts: int = 4,
        request_delay: float = 0.05,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.request_delay = max(0.0, request_delay)
        self.session = session or requests.Session()

    def query_count(self, task: QueryTask) -> QueryOutcome:
        query_filter = build_query_filter(task)
        params: dict[str, Any] = {
            "filter": query_filter,
            "per-page": 1,
            "select": "id",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        started = time.perf_counter()
        last_http_status: int | None = None
        last_error = "OpenAlex request failed"
        last_headers: dict[str, str] = {}
        attempts = 0

        for attempt in range(self.max_attempts):
            attempts = attempt + 1
            if self.request_delay:
                time.sleep(self.request_delay)
            try:
                response = self.session.get(
                    OPENALEX_WORKS_URL,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempts < self.max_attempts:
                    time.sleep(min(2**attempt, 8))
                    continue
                break

            last_http_status = response.status_code
            last_headers = dict(response.headers)
            if response.status_code == 429 or response.status_code >= 500:
                last_error = _response_error(response)
                if attempts < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(max(float(retry_after), 0.0), 15.0)
                    except (TypeError, ValueError):
                        delay = min(2**attempt, 8)
                    time.sleep(delay)
                    continue
                break

            if response.status_code >= 400:
                last_error = _response_error(response)
                break

            try:
                payload = response.json()
            except ValueError:
                last_error = "OpenAlex returned non-JSON content"
                break
            count = payload.get("meta", {}).get("count")
            if not isinstance(count, int) or count < 0:
                last_error = "OpenAlex response has no non-negative integer meta.count"
                break

            return QueryOutcome(
                request_status="success",
                http_status=response.status_code,
                works_count=count,
                query_as_of=utc_now(),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                retry_count=attempts - 1,
                error_message=None,
                rate_limit_limit=_header_int(response.headers.get("X-RateLimit-Limit")),
                rate_limit_remaining=_header_int(
                    response.headers.get("X-RateLimit-Remaining")
                ),
                rate_limit_reset=response.headers.get("X-RateLimit-Reset"),
                query_filter=query_filter,
            )

        return QueryOutcome(
            request_status="failed",
            http_status=last_http_status,
            works_count=None,
            query_as_of=utc_now(),
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            retry_count=max(0, attempts - 1),
            error_message=last_error[:1000],
            rate_limit_limit=_header_int(last_headers.get("X-RateLimit-Limit")),
            rate_limit_remaining=_header_int(last_headers.get("X-RateLimit-Remaining")),
            rate_limit_reset=last_headers.get("X-RateLimit-Reset"),
            query_filter=query_filter,
        )


def _connect(db_path: Path) -> sqlite3.Connection:
    initialize_database(db_path)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def _database(db_path: Path):
    connection = _connect(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _date_json(snapshot_dates: Iterable[date]) -> str:
    return json.dumps([item.isoformat() for item in sorted(set(snapshot_dates))])


def create_or_resume_run(
    db_path: Path,
    *,
    run_id: str,
    run_type: str,
    snapshot_dates: list[date],
    expected_query_count: int,
    revision_reason: str | None,
    data_origin: str,
) -> None:
    now = utc_now()
    serialized_dates = _date_json(snapshot_dates)
    with _database(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM trend_backfill_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row:
            expected = {
                "run_type": run_type,
                "start_snapshot_date": min(snapshot_dates).isoformat(),
                "end_snapshot_date": max(snapshot_dates).isoformat(),
                "snapshot_dates": serialized_dates,
                "expected_query_count": expected_query_count,
                "topic_mapping_version": MAPPING_VERSION,
                "query_version": QUERY_VERSION,
                "calculation_version": CALCULATION_VERSION,
                "data_origin": data_origin,
            }
            mismatches = {
                key: (row[key], value) for key, value in expected.items() if row[key] != value
            }
            if mismatches:
                raise ValueError(f"Resume run parameters do not match: {mismatches}")
            return
        connection.execute(
            """
            INSERT INTO trend_backfill_runs(
                run_id, run_type, start_snapshot_date, end_snapshot_date,
                snapshot_dates, expected_query_count, status,
                topic_mapping_version, query_version, calculation_version,
                revision_reason, started_at, updated_at, data_origin
            ) VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                run_type,
                min(snapshot_dates).isoformat(),
                max(snapshot_dates).isoformat(),
                serialized_dates,
                expected_query_count,
                MAPPING_VERSION,
                QUERY_VERSION,
                CALCULATION_VERSION,
                revision_reason,
                now,
                now,
                data_origin,
            ),
        )


def _successful_keys(connection: sqlite3.Connection, run_id: str) -> set[tuple[str, str]]:
    return {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            """
            SELECT DISTINCT category_id, snapshot_date
            FROM trend_query_logs
            WHERE run_id=? AND request_status='success'
            """,
            (run_id,),
        ).fetchall()
    }


def successful_keys(db_path: Path, run_id: str) -> set[tuple[str, str]]:
    with _database(db_path) as connection:
        return _successful_keys(connection, run_id)


def log_query(
    db_path: Path,
    run_id: str,
    task: QueryTask,
    outcome: QueryOutcome,
    data_origin: str,
) -> None:
    now = utc_now()
    with _database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO trend_query_logs(
                run_id, category_id, snapshot_date, window_start, window_end,
                topic_ids, query_filter, request_status, http_status, works_count,
                query_as_of, duration_ms, retry_count, error_message, query_version,
                rate_limit_limit, rate_limit_remaining, rate_limit_reset, created_at,
                data_origin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task.category.category_id,
                task.snapshot_date.isoformat(),
                task.window_start.isoformat(),
                task.window_end.isoformat(),
                json.dumps(task.category.topic_ids),
                outcome.query_filter,
                outcome.request_status,
                outcome.http_status,
                outcome.works_count,
                outcome.query_as_of,
                outcome.duration_ms,
                outcome.retry_count,
                outcome.error_message,
                QUERY_VERSION,
                outcome.rate_limit_limit,
                outcome.rate_limit_remaining,
                outcome.rate_limit_reset,
                now,
                data_origin,
            ),
        )
        _update_run_progress(connection, run_id, now)


def _update_run_progress(
    connection: sqlite3.Connection, run_id: str, now: str, status: str | None = None
) -> None:
    success = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT category_id, snapshot_date FROM trend_query_logs
                WHERE run_id=? AND request_status='success'
                GROUP BY category_id, snapshot_date
            )
            """,
            (run_id,),
        ).fetchone()[0]
    )
    failed = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT category_id, snapshot_date FROM trend_query_logs f
                WHERE f.run_id=? AND f.request_status='failed'
                  AND NOT EXISTS (
                    SELECT 1 FROM trend_query_logs s
                    WHERE s.run_id=f.run_id
                      AND s.category_id=f.category_id
                      AND s.snapshot_date=f.snapshot_date
                      AND s.request_status='success'
                  )
                GROUP BY category_id, snapshot_date
            )
            """,
            (run_id,),
        ).fetchone()[0]
    )
    current = connection.execute(
        "SELECT expected_query_count, status FROM trend_backfill_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    completed = success + failed
    next_status = status or str(current["status"])
    if status is None:
        next_status = "success" if success == int(current["expected_query_count"]) else "running"
    connection.execute(
        """
        UPDATE trend_backfill_runs
        SET completed_query_count=?, successful_query_count=?, failed_query_count=?,
            status=?, updated_at=?
        WHERE run_id=?
        """,
        (completed, success, failed, next_status, now, run_id),
    )


def set_run_status(db_path: Path, run_id: str, status: str) -> None:
    now = utc_now()
    with _database(db_path) as connection:
        _update_run_progress(connection, run_id, now, status=status)


def publish_complete_run(db_path: Path, run_id: str) -> dict[str, int]:
    now = utc_now()
    inserted = 0
    revised = 0
    unchanged = 0
    with _database(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        run = connection.execute(
            "SELECT * FROM trend_backfill_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not run:
            raise ValueError(f"Unknown run: {run_id}")
        success_keys = _successful_keys(connection, run_id)
        if len(success_keys) != int(run["expected_query_count"]):
            raise ValueError(
                f"Run is incomplete: {len(success_keys)}/{run['expected_query_count']} successful"
            )

        logs = connection.execute(
            """
            SELECT q.* FROM trend_query_logs q
            JOIN (
                SELECT category_id, snapshot_date, MAX(id) AS max_id
                FROM trend_query_logs
                WHERE run_id=? AND request_status='success'
                GROUP BY category_id, snapshot_date
            ) latest ON latest.max_id=q.id
            ORDER BY q.snapshot_date, q.category_id
            """,
            (run_id,),
        ).fetchall()

        for log in logs:
            current = connection.execute(
                """
                SELECT * FROM trend_30d_snapshots
                WHERE category_id=? AND snapshot_date=? AND is_current=1
                """,
                (log["category_id"], log["snapshot_date"]),
            ).fetchone()
            same = current and all(
                [
                    current["window_start"] == log["window_start"],
                    current["window_end"] == log["window_end"],
                    current["works_count"] == log["works_count"],
                    current["topic_mapping_version"] == run["topic_mapping_version"],
                    current["query_version"] == run["query_version"],
                    current["calculation_version"] == run["calculation_version"],
                ]
            )
            if same:
                unchanged += 1
                continue

            supersedes_id = None
            revision_no = 1
            if current:
                supersedes_id = int(current["id"])
                revision_no = int(current["revision_no"]) + 1
                connection.execute(
                    "UPDATE trend_30d_snapshots SET is_current=0, updated_at=? WHERE id=?",
                    (now, supersedes_id),
                )
                revised += 1
            else:
                inserted += 1

            connection.execute(
                """
                INSERT INTO trend_30d_snapshots(
                    run_id, category_id, snapshot_date, window_start, window_end,
                    works_count, query_as_of, data_status, topic_mapping_version,
                    query_version, calculation_version, revision_no, is_current,
                    supersedes_id, revision_reason, created_at, updated_at
                    , data_origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'success', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    log["category_id"],
                    log["snapshot_date"],
                    log["window_start"],
                    log["window_end"],
                    log["works_count"],
                    log["query_as_of"],
                    run["topic_mapping_version"],
                    run["query_version"],
                    run["calculation_version"],
                    revision_no,
                    supersedes_id,
                    run["revision_reason"],
                    now,
                    now,
                    run["data_origin"],
                ),
            )

        connection.execute(
            """
            UPDATE trend_backfill_runs
            SET completed_query_count=expected_query_count,
                successful_query_count=expected_query_count,
                failed_query_count=0, status='success',
                completed_at=COALESCE(completed_at, ?), updated_at=?
            WHERE run_id=?
            """,
            (now, now, run_id),
        )
    return {"inserted": inserted, "revised": revised, "unchanged": unchanged}


def run_summary(db_path: Path, run_id: str) -> dict[str, Any]:
    with _database(db_path) as connection:
        run = connection.execute(
            "SELECT * FROM trend_backfill_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not run:
            raise ValueError(f"Unknown run: {run_id}")
        actual_http_requests = int(
            connection.execute(
                """
                SELECT COALESCE(SUM(retry_count + 1), 0)
                FROM trend_query_logs WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()[0]
        )
        return {**dict(run), "actual_http_requests": actual_http_requests}


def execute_backfill(
    *,
    db_path: Path,
    mapping_path: Path,
    snapshot_dates: list[date],
    run_id: str,
    run_type: str,
    revision_reason: str | None,
    batch_size: int | None,
    client: TrendOpenAlexClient,
    data_origin: str | None = None,
) -> dict[str, Any]:
    resolved_origin = data_origin or (
        "historical_revision" if run_type == "revision" else "historical_backfill"
    )
    if resolved_origin not in DATA_ORIGINS:
        raise ValueError(f"Unsupported data_origin: {resolved_origin}")
    categories = load_categories(mapping_path)
    tasks = build_tasks(categories, snapshot_dates)
    create_or_resume_run(
        db_path,
        run_id=run_id,
        run_type=run_type,
        snapshot_dates=snapshot_dates,
        expected_query_count=len(tasks),
        revision_reason=revision_reason,
        data_origin=resolved_origin,
    )

    completed = successful_keys(db_path, run_id)
    pending = [
        task
        for task in tasks
        if (task.category.category_id, task.snapshot_date.isoformat()) not in completed
    ]
    if batch_size is not None:
        pending = pending[:batch_size]

    try:
        for task in pending:
            outcome = client.query_count(task)
            log_query(db_path, run_id, task, outcome, resolved_origin)
    except KeyboardInterrupt:
        set_run_status(db_path, run_id, "paused")
        raise

    summary = run_summary(db_path, run_id)
    if summary["successful_query_count"] == summary["expected_query_count"]:
        summary["publication"] = publish_complete_run(db_path, run_id)
    elif summary["failed_query_count"]:
        set_run_status(db_path, run_id, "partial")
    else:
        set_run_status(db_path, run_id, "paused")
    return run_summary(db_path, run_id) | {
        "publication": summary.get("publication"),
        "concurrency": 1,
    }


def parse_snapshot_dates(args: argparse.Namespace) -> tuple[list[date], str]:
    if args.snapshot_dates:
        values = [date.fromisoformat(item.strip()) for item in args.snapshot_dates.split(",")]
        if not values:
            raise ValueError("--snapshot-dates must contain at least one date")
        return sorted(set(values)), "revision"
    if args.start_date and args.end_date:
        if args.start_date > args.end_date:
            raise ValueError("--start-date must not be after --end-date")
        span = (args.end_date - args.start_date).days
        return [args.start_date + timedelta(days=offset) for offset in range(span + 1)], "backfill"
    start = args.as_of - timedelta(days=args.days - 1)
    return [start + timedelta(days=offset) for offset in range(args.days)], "backfill"


def parse_args(argv: list[str]) -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Backfill direct OpenAlex 30-day rolling counts into an explicit database."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--mapping", type=Path, default=root / "config" / "trend_topic_mapping.json"
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument(
        "--snapshot-dates",
        help="Comma-separated historical snapshot dates for a revision run.",
    )
    parser.add_argument("--revision-reason")
    parser.add_argument("--data-origin", choices=DATA_ORIGINS)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Maximum new logical queries in this invocation; rerun with the same run ID to resume.",
    )
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--request-delay", type=float, default=0.05)
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be positive")
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if args.snapshot_dates and not args.revision_reason:
        parser.error("--revision-reason is required with --snapshot-dates")
    if bool(args.start_date) != bool(args.end_date):
        parser.error("--start-date and --end-date must be provided together")
    if args.snapshot_dates and args.start_date:
        parser.error("--snapshot-dates cannot be combined with a date range")
    if args.snapshot_dates and args.data_origin not in {None, "historical_revision"}:
        parser.error("revision dates require data_origin=historical_revision")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    snapshot_dates, run_type = parse_snapshot_dates(args)
    run_id = args.run_id or (
        f"trend-{run_type}-{min(snapshot_dates).isoformat()}-"
        f"{max(snapshot_dates).isoformat()}-{uuid4().hex[:8]}"
    )
    client = TrendOpenAlexClient(
        api_key=os.environ.get("OPENALEX_API_KEY", "").strip() or None,
        timeout=args.timeout,
        max_attempts=args.max_attempts,
        request_delay=args.request_delay,
    )
    try:
        summary = execute_backfill(
            db_path=args.db,
            mapping_path=args.mapping,
            snapshot_dates=snapshot_dates,
            run_id=run_id,
            run_type=run_type,
            revision_reason=args.revision_reason,
            batch_size=args.batch_size,
            client=client,
            data_origin=args.data_origin,
        )
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "run_id": run_id, "status": "paused"}, indent=2))
        return 130
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "run_id": run_id, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
