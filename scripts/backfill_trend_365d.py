from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.trend_analytics import (  # noqa: E402
    CALCULATION_VERSION,
    CATEGORY_ORDER,
    CORE_CORPUS_FILTER,
    MAPPING_VERSION,
    QUERY_VERSION,
    TrendOpenAlexClient,
    execute_backfill,
)
from storage import initialize_database  # noqa: E402


DEFAULT_START = date(2025, 11, 19)
DEFAULT_END = date(2026, 11, 18)
DATA_ORIGIN = "historical_backfill"


def date_range(start: date, end: date) -> list[date]:
    if start > end:
        raise ValueError("start date must not be after end date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def chunks(values: list[date], size: int) -> Iterable[list[date]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def complete_dates(db_path: Path) -> set[date]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT s.snapshot_date
            FROM trend_30d_snapshots s
            JOIN trend_backfill_runs r ON r.run_id=s.run_id
            WHERE s.is_current=1 AND s.data_status='success' AND r.status='success'
            GROUP BY s.snapshot_date
            HAVING COUNT(DISTINCT s.category_id)=?
               AND SUM(CASE WHEN s.category_id IN (?, ?, ?, ?, ?) THEN 1 ELSE 0 END)=?
            """,
            (len(CATEGORY_ORDER), *CATEGORY_ORDER, len(CATEGORY_ORDER)),
        ).fetchall()
    return {date.fromisoformat(str(row[0])) for row in rows}


def validate_batch(db_path: Path, run_id: str, batch_dates: list[date]) -> dict[str, Any]:
    expected = len(batch_dates) * len(CATEGORY_ORDER)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        run = connection.execute(
            "SELECT * FROM trend_backfill_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if not run or run["status"] != "success":
            raise RuntimeError(f"Batch {run_id} did not finish successfully")
        if run["data_origin"] != DATA_ORIGIN:
            raise RuntimeError(f"Batch {run_id} has the wrong data origin")

        placeholders = ",".join("?" for _ in batch_dates)
        values = [item.isoformat() for item in batch_dates]
        snapshot = connection.execute(
            f"""
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT snapshot_date) AS dates,
                   COUNT(DISTINCT category_id) AS categories,
                   SUM(CASE WHEN julianday(window_end)-julianday(window_start)=29
                            THEN 0 ELSE 1 END) AS bad_windows,
                   SUM(CASE WHEN data_origin=? THEN 0 ELSE 1 END) AS bad_origins
            FROM trend_30d_snapshots
            WHERE is_current=1 AND snapshot_date IN ({placeholders})
            """,
            (DATA_ORIGIN, *values),
        ).fetchone()
        if (
            snapshot["rows"] != expected
            or snapshot["dates"] != len(batch_dates)
            or snapshot["categories"] != len(CATEGORY_ORDER)
            or snapshot["bad_windows"] != 0
            or snapshot["bad_origins"] != 0
        ):
            raise RuntimeError(f"Batch {run_id} snapshot quality check failed")

        log = connection.execute(
            """
            SELECT COUNT(*) AS rows,
                   SUM(CASE WHEN request_status='success' THEN 0 ELSE 1 END) AS failures,
                   SUM(retry_count) AS retries,
                   SUM(retry_count + 1) AS http_requests,
                   SUM(CASE WHEN works_count IS NULL THEN 1 ELSE 0 END) AS null_counts,
                   SUM(CASE WHEN query_filter LIKE ? THEN 0 ELSE 1 END) AS bad_core,
                   SUM(CASE WHEN query_version=? THEN 0 ELSE 1 END) AS bad_versions,
                   SUM(CASE WHEN data_origin=? THEN 0 ELSE 1 END) AS bad_origins,
                   ROUND(AVG(duration_ms), 1) AS average_duration_ms,
                   ROUND(MAX(duration_ms), 1) AS maximum_duration_ms
            FROM trend_query_logs WHERE run_id=?
            """,
            (
                f"%{CORE_CORPUS_FILTER}%",
                QUERY_VERSION,
                DATA_ORIGIN,
                run_id,
            ),
        ).fetchone()
        if (
            log["rows"] != expected
            or log["failures"] != 0
            or log["null_counts"] != 0
            or log["bad_core"] != 0
            or log["bad_versions"] != 0
            or log["bad_origins"] != 0
        ):
            raise RuntimeError(f"Batch {run_id} query-log quality check failed")

        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        if integrity != "ok" or foreign_keys:
            raise RuntimeError(f"Batch {run_id} database integrity check failed")

    return {
        "run_id": run_id,
        "start_date": batch_dates[0].isoformat(),
        "end_date": batch_dates[-1].isoformat(),
        "snapshot_dates": len(batch_dates),
        "snapshots": expected,
        "http_requests": int(log["http_requests"]),
        "retries": int(log["retries"]),
        "average_duration_ms": log["average_duration_ms"],
        "maximum_duration_ms": log["maximum_duration_ms"],
        "integrity": integrity,
        "foreign_key_violations": foreign_keys,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing V1.2 trend dates in checked batches.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--batch-days", type=int, default=30)
    parser.add_argument("--request-delay", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()
    if args.batch_days < 1:
        parser.error("--batch-days must be positive")
    return args


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"ok": False, "error": "OPENALEX_API_KEY is not configured"}))
        return 2

    initialize_database(args.db)
    target = date_range(args.start_date, args.end_date)
    existing = complete_dates(args.db)
    missing = [item for item in target if item not in existing]
    print(
        json.dumps(
            {
                "event": "plan",
                "target_dates": len(target),
                "already_complete": len(target) - len(missing),
                "missing_dates": len(missing),
                "expected_new_queries": len(missing) * len(CATEGORY_ORDER),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if not missing:
        return 0

    client = TrendOpenAlexClient(
        api_key=api_key,
        timeout=args.timeout,
        max_attempts=args.max_attempts,
        request_delay=args.request_delay,
    )
    completed_batches: list[dict[str, Any]] = []
    for batch_number, target_batch in enumerate(chunks(target, args.batch_days), start=1):
        batch_dates = [item for item in target_batch if item not in existing]
        if not batch_dates:
            continue
        run_id = (
            f"trend-backfill-365d-b{batch_number:02d}-"
            f"{batch_dates[0].strftime('%Y%m%d')}-{batch_dates[-1].strftime('%Y%m%d')}-v12"
        )
        summary = execute_backfill(
            db_path=args.db,
            mapping_path=ROOT / "config" / "trend_topic_mapping.json",
            snapshot_dates=batch_dates,
            run_id=run_id,
            run_type="backfill",
            revision_reason=None,
            batch_size=None,
            client=client,
            data_origin=DATA_ORIGIN,
        )
        if summary["status"] != "success":
            print(json.dumps({"event": "batch_failed", **summary}, ensure_ascii=False), flush=True)
            return 2
        quality = validate_batch(args.db, run_id, batch_dates)
        completed_batches.append(quality)
        print(json.dumps({"event": "batch_complete", **quality}, ensure_ascii=False), flush=True)

    print(
        json.dumps(
            {
                "event": "complete",
                "batches": len(completed_batches),
                "dates": sum(item["snapshot_dates"] for item in completed_batches),
                "http_requests": sum(item["http_requests"] for item in completed_batches),
                "retries": sum(item["retries"] for item in completed_batches),
                "mapping_version": MAPPING_VERSION,
                "query_version": QUERY_VERSION,
                "calculation_version": CALCULATION_VERSION,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
