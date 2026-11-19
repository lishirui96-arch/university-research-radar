from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable

import requests

from collector.topic_hotspot_updater import CORE_FILTER, OPENALEX_WORKS_URL
from collector.v14_taxonomy import EXPECTED_FIELD_COUNTS, TAXONOMY_VERSION
from storage import initialize_database


RUN_ID = "topic-v14-full-daily-20261118-v1"
QUERY_VERSION = "openalex-v14-field-topic-groupby-daily-v1"
CALCULATION_VERSION = "v14-publication-date-daily-full-v1"
USER_AGENT = "UniversityResearchRadar/1.4 (full-daily-backfill)"
FIELD_IDS = tuple(EXPECTED_FIELD_COUNTS)


@dataclass(frozen=True)
class DailyResult:
    publication_date: date
    counts: dict[str, int]
    requests: int
    retries: int
    query_as_of: str
    rate_remaining: int | None


class _RateLimiter:
    def __init__(self, requests_per_second: float = 8.0) -> None:
        self.interval = 1.0 / requests_per_second
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)


class V14DailyClient:
    def __init__(self, api_key: str, *, timeout: float = 45.0, max_attempts: int = 6) -> None:
        if not api_key:
            raise ValueError("OPENALEX_API_KEY is required")
        self.api_key = api_key
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.rate_limiter = _RateLimiter()

    def _get(self, params: dict[str, Any]) -> tuple[dict[str, Any], int, int | None]:
        for attempt in range(self.max_attempts):
            self.rate_limiter.wait()
            try:
                response = requests.get(
                    OPENALEX_WORKS_URL,
                    params={**params, "api_key": self.api_key},
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                )
            except requests.RequestException:
                if attempt + 1 == self.max_attempts:
                    raise
                time.sleep(min(2**attempt, 30))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 == self.max_attempts:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                time.sleep(min(max(delay, 0.0), 60.0))
                continue
            response.raise_for_status()
            remaining = response.headers.get("X-RateLimit-Remaining")
            try:
                rate_remaining = int(remaining) if remaining is not None else None
            except ValueError:
                rate_remaining = None
            return response.json(), attempt, rate_remaining
        raise RuntimeError("OpenAlex retry loop ended unexpectedly")

    def query_date(self, publication_date: date) -> DailyResult:
        filters = [
            CORE_FILTER,
            f"from_publication_date:{publication_date.isoformat()}",
            f"to_publication_date:{publication_date.isoformat()}",
            f"primary_topic.field.id:{'|'.join(FIELD_IDS)}",
        ]
        cursor: str | None = "*"
        counts: dict[str, int] = {}
        request_count = retry_count = 0
        rate_remaining: int | None = None
        while cursor:
            payload, retries, remaining = self._get(
                {
                    "filter": ",".join(filters),
                    "group_by": "primary_topic.id",
                    "per-page": 200,
                    "cursor": cursor,
                }
            )
            request_count += 1
            retry_count += retries
            rate_remaining = remaining if remaining is not None else rate_remaining
            for group in payload.get("group_by") or []:
                topic_id = str(group.get("key") or "").rsplit("/", 1)[-1]
                count = group.get("count")
                if topic_id.startswith("T") and isinstance(count, int) and count >= 0:
                    if topic_id in counts:
                        raise ValueError(f"Duplicate group for {topic_id} on {publication_date}")
                    counts[topic_id] = count
            cursor = (payload.get("meta") or {}).get("next_cursor")
        return DailyResult(
            publication_date=publication_date,
            counts=counts,
            requests=request_count,
            retries=retry_count,
            query_as_of=datetime.now(timezone.utc).isoformat(),
            rate_remaining=rate_remaining,
        )


def _topic_ids(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT topic_id FROM topic_taxonomy_versions
            WHERE taxonomy_version=?
            """,
            (TAXONOMY_VERSION,),
        ).fetchall()
    topic_ids = {str(row[0]) for row in rows}
    if len(topic_ids) != 1063:
        raise ValueError(f"Expected 1,063 V1.4 Topics, found {len(topic_ids)}")
    return topic_ids


def _complete_dates(database: Path, start: date, end: date) -> set[str]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT d.date, COUNT(*)
            FROM topic_daily_counts d
            JOIN topic_taxonomy_versions t
              ON t.topic_id=d.topic_id AND t.taxonomy_version=?
            WHERE d.is_current=1 AND d.query_status='success'
              AND d.date BETWEEN ? AND ?
            GROUP BY d.date HAVING COUNT(*)=1063
            """,
            (TAXONOMY_VERSION, start.isoformat(), end.isoformat()),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _ensure_run(database: Path, start: date, end: date) -> None:
    now = datetime.now().astimezone().isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO topic_update_runs(
                run_id, ranking_date, source_type, status, query_as_of,
                calculation_version, error_message, started_at, completed_at,
                created_at, updated_at
            ) VALUES (?, ?, 'daily_update', 'running', ?, ?, NULL, ?, NULL, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=CASE WHEN topic_update_runs.status='published'
                            THEN 'published' ELSE 'running' END,
                error_message=NULL, updated_at=excluded.updated_at
            """,
            (
                RUN_ID, end.isoformat(), now, CALCULATION_VERSION,
                now, now, now,
            ),
        )


def _save_date(database: Path, result: DailyResult, topic_ids: set[str]) -> None:
    unknown = set(result.counts) - topic_ids
    if unknown:
        raise ValueError(
            f"OpenAlex returned {len(unknown)} Topics outside frozen V1.4 scope: "
            f"{sorted(unknown)[:5]}"
        )
    day = result.publication_date.isoformat()
    now = datetime.now().astimezone().isoformat()
    connection = sqlite3.connect(database, timeout=60)
    connection.execute("PRAGMA busy_timeout=60000")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            current = {
                str(row[0]): (int(row[1]), int(row[2]), int(row[3]))
                for row in connection.execute(
                    """
                    SELECT d.topic_id, d.daily_works_count, d.revision_no, d.id
                    FROM topic_daily_counts d
                    JOIN topic_taxonomy_versions t
                      ON t.topic_id=d.topic_id AND t.taxonomy_version=?
                    WHERE d.date=? AND d.is_current=1 AND d.query_status='success'
                    """,
                    (TAXONOMY_VERSION, day),
                ).fetchall()
            }
            inserts: list[tuple[Any, ...]] = []
            for topic_id in sorted(topic_ids):
                count = int(result.counts.get(topic_id, 0))
                existing = current.get(topic_id)
                if existing and existing[0] == count:
                    continue
                revision_no = existing[1] + 1 if existing else 1
                if existing:
                    connection.execute(
                        "UPDATE topic_daily_counts SET is_current=0, updated_at=? WHERE id=?",
                        (now, existing[2]),
                    )
                inserts.append(
                    (
                        day, topic_id, count, result.query_as_of, revision_no,
                        QUERY_VERSION, TAXONOMY_VERSION, RUN_ID, now, now,
                    )
                )
            connection.executemany(
                """
                INSERT INTO topic_daily_counts(
                    date, topic_id, daily_works_count, query_as_of, query_status,
                    revision_no, is_current, query_version, taxonomy_version,
                    source_run_id, revision_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'success', ?, 1, ?, ?, ?,
                          'V1.4 full six-Field historical backfill', ?, ?)
                """,
                inserts,
            )
            count = connection.execute(
                """
                SELECT COUNT(*) FROM topic_daily_counts d
                JOIN topic_taxonomy_versions t
                  ON t.topic_id=d.topic_id AND t.taxonomy_version=?
                WHERE d.date=? AND d.is_current=1 AND d.query_status='success'
                """,
                (TAXONOMY_VERSION, day),
            ).fetchone()[0]
            if count != 1063:
                raise ValueError(f"Date {day} has {count}/1063 current rows after save")
            connection.execute(
                "UPDATE topic_update_runs SET query_as_of=?, updated_at=? WHERE run_id=?",
                (result.query_as_of, now, RUN_ID),
            )
    finally:
        connection.close()


def _publish(database: Path, start: date, end: date) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        total_rows = connection.execute(
            """
            SELECT COUNT(*) FROM topic_daily_counts d
            JOIN topic_taxonomy_versions t
              ON t.topic_id=d.topic_id AND t.taxonomy_version=?
            WHERE d.is_current=1 AND d.query_status='success'
              AND d.date BETWEEN ? AND ?
            """,
            (TAXONOMY_VERSION, start.isoformat(), end.isoformat()),
        ).fetchone()[0]
        complete_dates = connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT d.date FROM topic_daily_counts d
                JOIN topic_taxonomy_versions t
                  ON t.topic_id=d.topic_id AND t.taxonomy_version=?
                WHERE d.is_current=1 AND d.query_status='success'
                  AND d.date BETWEEN ? AND ?
                GROUP BY d.date HAVING COUNT(*)=1063
            )
            """,
            (TAXONOMY_VERSION, start.isoformat(), end.isoformat()),
        ).fetchone()[0]
        expected_rows = 360 * 1063
        if total_rows != expected_rows or complete_dates != 360:
            raise ValueError(
                f"Backfill incomplete: {total_rows}/{expected_rows} rows, "
                f"{complete_dates}/360 dates"
            )
        now = datetime.now().astimezone().isoformat()
        connection.execute(
            """
            UPDATE topic_update_runs
            SET status='published', completed_at=?, updated_at=? WHERE run_id=?
            """,
            (now, now, RUN_ID),
        )
        connection.commit()
    return {
        "status": "published",
        "run_id": RUN_ID,
        "rows": total_rows,
        "dates": complete_dates,
        "topics": 1063,
    }


def run_v14_full_backfill(
    database: Path,
    *,
    end_date: date = date(2026, 11, 18),
    workers: int = 4,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    initialize_database(database)
    topic_ids = _topic_ids(database)
    start_date = end_date - timedelta(days=359)
    _ensure_run(database, start_date, end_date)
    complete = _complete_dates(database, start_date, end_date)
    targets = [
        start_date + timedelta(days=offset)
        for offset in range(360)
        if (start_date + timedelta(days=offset)).isoformat() not in complete
    ]
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    client = V14DailyClient(api_key)
    requests_count = retry_count = 0
    completed_now = 0
    try:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as executor:
            futures = {executor.submit(client.query_date, day): day for day in targets}
            for future in as_completed(futures):
                result = future.result()
                _save_date(database, result, topic_ids)
                completed_now += 1
                requests_count += result.requests
                retry_count += result.retries
                if progress:
                    progress(
                        {
                            "date": result.publication_date.isoformat(),
                            "completed_now": completed_now,
                            "target_dates": len(targets),
                            "requests": requests_count,
                            "retries": retry_count,
                            "rate_remaining": result.rate_remaining,
                        }
                    )
    except Exception as exc:
        now = datetime.now().astimezone().isoformat()
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE topic_update_runs
                SET status='failed', error_message=?, updated_at=? WHERE run_id=?
                """,
                (str(exc), now, RUN_ID),
            )
            connection.commit()
        raise
    published = _publish(database, start_date, end_date)
    return {
        **published,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "dates_already_complete": len(complete),
        "dates_queried": completed_now,
        "successful_requests": requests_count,
        "retry_attempts": retry_count,
    }
