from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Callable, Iterable

import requests

from collector.topic_hotspot_updater import CORE_FILTER, OPENALEX_WORKS_URL
from collector.v14_taxonomy import EXPECTED_TOPIC_COUNT, TAXONOMY_VERSION
from storage import initialize_database


REGION_CODES = ("CN", "US")
FIELD_IDS = ("15", "16", "17", "21", "22", "25")
QUERY_VERSION = "openalex-v15-country-primary-topic-groupby-v1"
CALCULATION_VERSION = "v15-adjacent-window-growth-v1"
USER_AGENT = "UniversityResearchRadar/1.5 (CN-US regional backfill)"
DAILY_BASELINE_DAYS = 391
GLOBAL_TABLES = (
    "topic_update_runs",
    "topic_ranking_snapshots",
    "topic_daily_counts",
)


@dataclass(frozen=True)
class GroupResult:
    counts: dict[str, int]
    page_count: int
    retry_count: int
    query_as_of: str
    query_filter: str


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


def validate_region(region_code: str) -> str:
    region = str(region_code).upper()
    if region not in REGION_CODES:
        raise ValueError("V1.5 regional collection only accepts CN or US")
    return region


def region_query_filter(start: date, end: date, region_code: str) -> str:
    region = validate_region(region_code)
    return ",".join(
        (
            CORE_FILTER,
            f"from_publication_date:{start.isoformat()}",
            f"to_publication_date:{end.isoformat()}",
            f"primary_topic.field.id:{'|'.join(FIELD_IDS)}",
            f"authorships.institutions.country_code:{region}",
        )
    )


class RegionalOpenAlexClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 45.0,
        max_attempts: int = 6,
        requests_per_second: float = 8.0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENALEX_API_KEY is required")
        self.api_key = api_key
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.rate_limiter = _RateLimiter(requests_per_second)

    def _get(self, params: dict[str, Any]) -> tuple[dict[str, Any], int]:
        for attempt in range(self.max_attempts):
            self.rate_limiter.wait()
            try:
                response = requests.get(
                    OPENALEX_WORKS_URL,
                    params={**params, "api_key": self.api_key},
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt + 1 == self.max_attempts:
                    raise RuntimeError(_sanitize_error(exc)) from None
                time.sleep(min(2**attempt, 30))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 == self.max_attempts:
                    try:
                        response.raise_for_status()
                    except requests.HTTPError as exc:
                        raise RuntimeError(_sanitize_error(exc)) from None
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                time.sleep(min(max(delay, 0.0), 60.0))
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(_sanitize_error(exc)) from None
            return response.json(), attempt
        raise RuntimeError("OpenAlex retry loop ended unexpectedly")

    def grouped_topics(self, start: date, end: date, region_code: str) -> GroupResult:
        query_filter = region_query_filter(start, end, region_code)
        cursor: str | None = "*"
        counts: dict[str, int] = {}
        page_count = retry_count = 0
        while cursor:
            payload, retries = self._get(
                {
                    "filter": query_filter,
                    "group_by": "primary_topic.id",
                    "per-page": 200,
                    "cursor": cursor,
                }
            )
            page_count += 1
            retry_count += retries
            for group in payload.get("group_by") or []:
                topic_id = str(group.get("key") or "").rsplit("/", 1)[-1]
                count = group.get("count")
                if topic_id.startswith("T") and isinstance(count, int) and count >= 0:
                    if topic_id in counts:
                        raise ValueError(f"Duplicate OpenAlex group for {topic_id}")
                    counts[topic_id] = count
            cursor = (payload.get("meta") or {}).get("next_cursor")
        return GroupResult(
            counts=counts,
            page_count=page_count,
            retry_count=retry_count,
            query_as_of=datetime.now(timezone.utc).isoformat(),
            query_filter=query_filter,
        )


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database, timeout=60)
    connection.execute("PRAGMA busy_timeout=60000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _sanitize_error(error: Exception | str) -> str:
    message = str(error)
    message = re.sub(
        r"(?i)(api_key(?:=|%3D))[^&\s]+",
        r"\1[REDACTED]",
        message,
    )
    return message[:1000]


def _taxonomy(database: Path) -> dict[str, str]:
    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT topic_id, field_id
            FROM topic_taxonomy_versions
            WHERE taxonomy_version=?
            """,
            (TAXONOMY_VERSION,),
        ).fetchall()
    topics = {str(topic_id): str(field_id) for topic_id, field_id in rows}
    if len(topics) != EXPECTED_TOPIC_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_TOPIC_COUNT} V1.4 Topics, found {len(topics)}"
        )
    return topics


def _table_digest(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    columns = [
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
    ]
    digest = hashlib.sha256()
    row_count = 0
    cursor = connection.execute(
        f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid"
    )
    while True:
        batch = cursor.fetchmany(2000)
        if not batch:
            break
        for row in batch:
            digest.update(
                json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
                .encode("utf-8")
            )
            digest.update(b"\n")
        row_count += len(batch)
    return {"rows": row_count, "sha256": digest.hexdigest()}


def global_table_fingerprints(database: Path) -> dict[str, dict[str, Any]]:
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        return {table: _table_digest(connection, table) for table in GLOBAL_TABLES}
    finally:
        connection.close()


def _ensure_batch(
    database: Path,
    batch_id: str,
    ranking_date: date,
    daily_start: date,
) -> None:
    now = datetime.now().astimezone().isoformat()
    with _connect(database) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO regional_snapshot_batches(
                    batch_id, ranking_date, daily_start, daily_end,
                    taxonomy_version, query_version, calculation_version,
                    status, started_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET
                    status=CASE
                        WHEN regional_snapshot_batches.status='published'
                        THEN 'published' ELSE 'running' END,
                    error_message=NULL, updated_at=excluded.updated_at
                """,
                (
                    batch_id,
                    ranking_date.isoformat(),
                    daily_start.isoformat(),
                    ranking_date.isoformat(),
                    TAXONOMY_VERSION,
                    QUERY_VERSION,
                    CALCULATION_VERSION,
                    now,
                    now,
                    now,
                ),
            )
            for region in REGION_CODES:
                run_id = f"{batch_id}-{region.lower()}"
                connection.execute(
                    """
                    INSERT INTO regional_topic_runs(
                        run_id, batch_id, region_code, status,
                        started_at, created_at, updated_at
                    ) VALUES (?, ?, ?, 'running', ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        status=CASE WHEN regional_topic_runs.status='published'
                            THEN 'published' ELSE 'running' END,
                        error_message=NULL, updated_at=excluded.updated_at
                    """,
                    (run_id, batch_id, region, now, now, now),
                )


def _complete_daily_dates(
    database: Path, batch_id: str, region_code: str
) -> set[str]:
    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT publication_date
            FROM regional_topic_daily_counts
            WHERE batch_id=? AND region_code=? AND data_status='success'
            GROUP BY publication_date HAVING COUNT(*)=?
            """,
            (batch_id, region_code, EXPECTED_TOPIC_COUNT),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _log_query(
    database: Path,
    *,
    batch_id: str,
    region_code: str,
    query_kind: str,
    start: date,
    end: date,
    result: GroupResult | None,
    error: Exception | None = None,
    period_days: int | None = None,
    window_role: str | None = None,
) -> None:
    now = datetime.now().astimezone().isoformat()
    query_filter = (
        result.query_filter
        if result is not None
        else region_query_filter(start, end, region_code)
    )
    with _connect(database) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO regional_query_logs(
                    batch_id, source_run_id, region_code, query_kind,
                    period_days, window_role, window_start, window_end,
                    query_filter, request_status, response_group_count,
                    page_count, retry_count, query_as_of, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    f"{batch_id}-{region_code.lower()}",
                    region_code,
                    query_kind,
                    period_days,
                    window_role,
                    start.isoformat(),
                    end.isoformat(),
                    query_filter,
                    "success" if error is None else "failed",
                    len(result.counts) if result is not None else None,
                    result.page_count if result is not None else 0,
                    result.retry_count if result is not None else 0,
                    result.query_as_of if result is not None else datetime.now(timezone.utc).isoformat(),
                    _sanitize_error(error) if error is not None else None,
                    now,
                ),
            )


def _save_daily_result(
    database: Path,
    *,
    batch_id: str,
    region_code: str,
    publication_date: date,
    result: GroupResult,
    topics: dict[str, str],
) -> None:
    unknown = set(result.counts) - set(topics)
    if unknown:
        raise ValueError(
            f"OpenAlex returned Topics outside frozen V1.4 scope: {sorted(unknown)[:5]}"
        )
    now = datetime.now().astimezone().isoformat()
    rows = [
        (
            batch_id,
            region_code,
            publication_date.isoformat(),
            topic_id,
            topics[topic_id],
            int(result.counts.get(topic_id, 0)),
            result.query_as_of,
            TAXONOMY_VERSION,
            QUERY_VERSION,
            f"{batch_id}-{region_code.lower()}",
            now,
            now,
        )
        for topic_id in sorted(topics)
    ]
    with _connect(database) as connection:
        with connection:
            connection.executemany(
                """
                INSERT INTO regional_topic_daily_counts(
                    batch_id, region_code, publication_date, topic_id, field_id,
                    daily_works_count, query_as_of, taxonomy_version,
                    query_version, source_run_id, data_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'success', ?, ?)
                ON CONFLICT(batch_id, region_code, publication_date, topic_id)
                DO UPDATE SET
                    daily_works_count=excluded.daily_works_count,
                    query_as_of=excluded.query_as_of,
                    updated_at=excluded.updated_at
                """,
                rows,
            )
            stored = connection.execute(
                """
                SELECT COUNT(*) FROM regional_topic_daily_counts
                WHERE batch_id=? AND region_code=? AND publication_date=?
                  AND data_status='success'
                """,
                (batch_id, region_code, publication_date.isoformat()),
            ).fetchone()[0]
            if stored != EXPECTED_TOPIC_COUNT:
                raise ValueError(
                    f"{region_code} {publication_date} stored {stored}/{EXPECTED_TOPIC_COUNT} Topics"
                )
            connection.execute(
                """
                UPDATE regional_topic_runs
                SET query_as_of=?, completed_daily_dates=(
                    SELECT COUNT(DISTINCT publication_date)
                    FROM regional_topic_daily_counts
                    WHERE batch_id=? AND region_code=? AND data_status='success'
                ), updated_at=? WHERE run_id=?
                """,
                (
                    result.query_as_of,
                    batch_id,
                    region_code,
                    now,
                    f"{batch_id}-{region_code.lower()}",
                ),
            )


def _rank_values(values: dict[str, float | int]) -> dict[str, int]:
    ordered = sorted(values, key=lambda topic_id: (-values[topic_id], topic_id))
    return {topic_id: rank for rank, topic_id in enumerate(ordered, start=1)}


def build_period_records(
    *,
    region_code: str,
    ranking_date: date,
    current: dict[int, dict[str, int]],
    previous: dict[int, dict[str, int]],
    topics: dict[str, str],
) -> list[dict[str, Any]]:
    region = validate_region(region_code)
    records: list[dict[str, Any]] = []
    for period_days in (90, 360):
        current_counts = {
            topic_id: int(current[period_days].get(topic_id, 0)) for topic_id in topics
        }
        previous_counts = {
            topic_id: int(previous[period_days].get(topic_id, 0)) for topic_id in topics
        }
        growth_amounts = {
            topic_id: current_counts[topic_id] - previous_counts[topic_id]
            for topic_id in topics
        }
        growth_rates = {
            topic_id: growth_amounts[topic_id] / previous_counts[topic_id]
            for topic_id in topics
            if previous_counts[topic_id] > 0
        }
        works_ranks = _rank_values(current_counts)
        amount_ranks = _rank_values(growth_amounts)
        rate_ranks = _rank_values(growth_rates)
        window_start = ranking_date - timedelta(days=period_days - 1)
        previous_end = window_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        for topic_id in sorted(topics):
            baseline = previous_counts[topic_id]
            records.append(
                {
                    "region_code": region,
                    "period_days": period_days,
                    "topic_id": topic_id,
                    "field_id": topics[topic_id],
                    "window_start": window_start.isoformat(),
                    "window_end": ranking_date.isoformat(),
                    "works_count": current_counts[topic_id],
                    "previous_window_start": previous_start.isoformat(),
                    "previous_window_end": previous_end.isoformat(),
                    "previous_works_count": baseline,
                    "growth_amount": growth_amounts[topic_id],
                    "growth_rate": growth_rates.get(topic_id),
                    "growth_status": "success" if baseline > 0 else "zero_baseline",
                    "works_rank": works_ranks[topic_id],
                    "growth_amount_rank": amount_ranks[topic_id],
                    "growth_rate_rank": rate_ranks.get(topic_id),
                }
            )
    return records


def _daily_totals(
    database: Path,
    batch_id: str,
    region_code: str,
    start: date,
    end: date,
) -> dict[str, int]:
    with _connect(database) as connection:
        rows = connection.execute(
            """
            SELECT topic_id, SUM(daily_works_count)
            FROM regional_topic_daily_counts
            WHERE batch_id=? AND region_code=? AND data_status='success'
              AND publication_date BETWEEN ? AND ?
            GROUP BY topic_id
            """,
            (batch_id, region_code, start.isoformat(), end.isoformat()),
        ).fetchall()
    return {str(topic_id): int(total) for topic_id, total in rows}


def _save_period_records(
    database: Path,
    *,
    batch_id: str,
    ranking_date: date,
    region_code: str,
    records: Iterable[dict[str, Any]],
    query_as_of: str,
) -> None:
    now = datetime.now().astimezone().isoformat()
    values = [
        (
            batch_id,
            record["region_code"],
            ranking_date.isoformat(),
            record["period_days"],
            record["topic_id"],
            record["field_id"],
            record["window_start"],
            record["window_end"],
            record["works_count"],
            record["previous_window_start"],
            record["previous_window_end"],
            record["previous_works_count"],
            record["growth_amount"],
            record["growth_rate"],
            record["growth_status"],
            record["works_rank"],
            record["growth_amount_rank"],
            record["growth_rate_rank"],
            query_as_of,
            TAXONOMY_VERSION,
            QUERY_VERSION,
            CALCULATION_VERSION,
            f"{batch_id}-{region_code.lower()}",
            now,
            now,
        )
        for record in records
    ]
    with _connect(database) as connection:
        with connection:
            connection.execute(
                "DELETE FROM regional_topic_period_snapshots WHERE batch_id=? AND region_code=?",
                (batch_id, region_code),
            )
            connection.executemany(
                """
                INSERT INTO regional_topic_period_snapshots(
                    batch_id, region_code, ranking_date, period_days,
                    topic_id, field_id, window_start, window_end, works_count,
                    previous_window_start, previous_window_end, previous_works_count,
                    growth_amount, growth_rate, growth_status,
                    works_rank, growth_amount_rank, growth_rate_rank,
                    query_as_of, taxonomy_version, query_version,
                    calculation_version, source_run_id, data_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, 'success', ?, ?)
                """,
                values,
            )


def _logged_request_totals(
    database: Path, batch_id: str, region_code: str
) -> tuple[int, int]:
    with _connect(database) as connection:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(page_count), 0), COALESCE(SUM(retry_count), 0)
            FROM regional_query_logs
            WHERE batch_id=? AND region_code=? AND request_status='success'
            """,
            (batch_id, region_code),
        ).fetchone()
    return int(row[0]), int(row[1])


def _collect_periods(
    database: Path,
    client: RegionalOpenAlexClient,
    batch_id: str,
    region_code: str,
    ranking_date: date,
    topics: dict[str, str],
) -> tuple[list[dict[str, Any]], int, int, str]:
    current: dict[int, dict[str, int]] = {}
    previous: dict[int, dict[str, int]] = {}
    requests_count = retry_count = 0
    query_as_of = ""
    topic_ids = set(topics)
    for period_days in (90, 360):
        current_start = ranking_date - timedelta(days=period_days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        for role, start, end, destination in (
            ("current", current_start, ranking_date, current),
            ("previous", previous_start, previous_end, previous),
        ):
            result: GroupResult | None = None
            try:
                result = client.grouped_topics(start, end, region_code)
                unknown = set(result.counts) - topic_ids
                if unknown:
                    raise ValueError(
                        f"OpenAlex returned Topics outside frozen V1.4 scope: {sorted(unknown)[:5]}"
                    )
                destination[period_days] = result.counts
                requests_count += result.page_count
                retry_count += result.retry_count
                query_as_of = max(query_as_of, result.query_as_of)
                _log_query(
                    database,
                    batch_id=batch_id,
                    region_code=region_code,
                    query_kind="period",
                    start=start,
                    end=end,
                    result=result,
                    period_days=period_days,
                    window_role=role,
                )
            except Exception as exc:
                _log_query(
                    database,
                    batch_id=batch_id,
                    region_code=region_code,
                    query_kind="period",
                    start=start,
                    end=end,
                    result=result,
                    error=exc,
                    period_days=period_days,
                    window_role=role,
                )
                raise
    records = build_period_records(
        region_code=region_code,
        ranking_date=ranking_date,
        current=current,
        previous=previous,
        topics=topics,
    )
    for period_days in (90, 360):
        start = ranking_date - timedelta(days=period_days - 1)
        daily = _daily_totals(database, batch_id, region_code, start, ranking_date)
        expected = {topic_id: int(current[period_days].get(topic_id, 0)) for topic_id in topics}
        if daily != expected:
            mismatched = [
                topic_id
                for topic_id in topics
                if daily.get(topic_id) != expected.get(topic_id)
            ]
            raise ValueError(
                f"{region_code} {period_days}-day daily/ranking mismatch for "
                f"{len(mismatched)} Topics: {mismatched[:5]}"
            )
    return records, requests_count, retry_count, query_as_of


def _mark_failed(database: Path, batch_id: str, error: Exception) -> None:
    now = datetime.now().astimezone().isoformat()
    with _connect(database) as connection:
        with connection:
            connection.execute(
                """
                UPDATE regional_snapshot_batches
                SET status='failed', error_message=?, updated_at=? WHERE batch_id=?
                """,
                (_sanitize_error(error), now, batch_id),
            )
            connection.execute(
                """
                UPDATE regional_topic_runs
                SET status=CASE WHEN status='published' THEN status ELSE 'failed' END,
                    error_message=?, updated_at=? WHERE batch_id=?
                """,
                (_sanitize_error(error), now, batch_id),
            )


def _publish(database: Path, batch_id: str, ranking_date: date) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat()
    with _connect(database) as connection:
        with connection:
            for region in REGION_CODES:
                daily_rows = connection.execute(
                    """
                    SELECT COUNT(*) FROM regional_topic_daily_counts
                    WHERE batch_id=? AND region_code=? AND data_status='success'
                    """,
                    (batch_id, region),
                ).fetchone()[0]
                period_rows = connection.execute(
                    """
                    SELECT COUNT(*) FROM regional_topic_period_snapshots
                    WHERE batch_id=? AND region_code=? AND data_status='success'
                    """,
                    (batch_id, region),
                ).fetchone()[0]
                expected_daily = DAILY_BASELINE_DAYS * EXPECTED_TOPIC_COUNT
                expected_period = 2 * EXPECTED_TOPIC_COUNT
                if daily_rows != expected_daily or period_rows != expected_period:
                    raise ValueError(
                        f"{region} incomplete: daily {daily_rows}/{expected_daily}, "
                        f"period {period_rows}/{expected_period}"
                    )
                connection.execute(
                    """
                    UPDATE regional_topic_runs
                    SET status='published', completed_at=?, updated_at=?
                    WHERE batch_id=? AND region_code=?
                    """,
                    (now, now, batch_id, region),
                )
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(api_request_count), 0), COALESCE(SUM(retry_count), 0)
                FROM regional_topic_runs WHERE batch_id=?
                """,
                (batch_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE regional_snapshot_batches
                SET status='published', completed_region_count=2,
                    api_request_count=?, retry_count=?, completed_at=?, updated_at=?
                WHERE batch_id=?
                """,
                (int(totals[0]), int(totals[1]), now, now, batch_id),
            )
    return {
        "batch_id": batch_id,
        "ranking_date": ranking_date.isoformat(),
        "regions": list(REGION_CODES),
        "status": "published",
    }


def run_regional_backfill(
    database: Path,
    *,
    ranking_date: date,
    batch_id: str | None = None,
    workers: int = 6,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    initialize_database(database)
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    client = RegionalOpenAlexClient(api_key)
    topics = _taxonomy(database)
    daily_start = ranking_date - timedelta(days=DAILY_BASELINE_DAYS - 1)
    batch = batch_id or f"regional-v15-{ranking_date.isoformat()}-v1"
    global_before = global_table_fingerprints(database)
    _ensure_batch(database, batch, ranking_date, daily_start)

    tasks: list[tuple[str, date]] = []
    for region in REGION_CODES:
        complete = _complete_daily_dates(database, batch, region)
        tasks.extend(
            (region, daily_start + timedelta(days=offset))
            for offset in range(DAILY_BASELINE_DAYS)
            if (daily_start + timedelta(days=offset)).isoformat() not in complete
        )
    request_totals = {region: 0 for region in REGION_CODES}
    retry_totals = {region: 0 for region in REGION_CODES}
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
            futures = {
                executor.submit(client.grouped_topics, day, day, region): (region, day)
                for region, day in tasks
            }
            for future in as_completed(futures):
                region, day = futures[future]
                result: GroupResult | None = None
                try:
                    result = future.result()
                    _save_daily_result(
                        database,
                        batch_id=batch,
                        region_code=region,
                        publication_date=day,
                        result=result,
                        topics=topics,
                    )
                    _log_query(
                        database,
                        batch_id=batch,
                        region_code=region,
                        query_kind="daily",
                        start=day,
                        end=day,
                        result=result,
                    )
                    request_totals[region] += result.page_count
                    retry_totals[region] += result.retry_count
                    completed += 1
                    if progress and (completed % 10 == 0 or completed == len(tasks)):
                        progress(
                            {
                                "completed_dates": completed,
                                "target_dates": len(tasks),
                                "region": region,
                                "date": day.isoformat(),
                                "requests": sum(request_totals.values()),
                                "retries": sum(retry_totals.values()),
                            }
                        )
                except Exception as exc:
                    _log_query(
                        database,
                        batch_id=batch,
                        region_code=region,
                        query_kind="daily",
                        start=day,
                        end=day,
                        result=result,
                        error=exc,
                    )
                    for pending in futures:
                        pending.cancel()
                    executor.shutdown(wait=True, cancel_futures=True)
                    raise

        for region in REGION_CODES:
            records, requests_count, retries, query_as_of = _collect_periods(
                database, client, batch, region, ranking_date, topics
            )
            request_totals[region] += requests_count
            retry_totals[region] += retries
            _save_period_records(
                database,
                batch_id=batch,
                ranking_date=ranking_date,
                region_code=region,
                records=records,
                query_as_of=query_as_of,
            )
            request_totals[region], retry_totals[region] = _logged_request_totals(
                database, batch, region
            )
            now = datetime.now().astimezone().isoformat()
            with _connect(database) as connection:
                with connection:
                    connection.execute(
                        """
                        UPDATE regional_topic_runs
                        SET status='validated', query_as_of=?, api_request_count=?,
                            retry_count=?, updated_at=? WHERE batch_id=? AND region_code=?
                        """,
                        (
                            query_as_of,
                            request_totals[region],
                            retry_totals[region],
                            now,
                            batch,
                            region,
                        ),
                    )
        published = _publish(database, batch, ranking_date)
        global_after = global_table_fingerprints(database)
        if global_before != global_after:
            raise RuntimeError("GLOBAL V1.4 tables changed during regional collection")
        return {
            **published,
            "daily_start": daily_start.isoformat(),
            "daily_end": ranking_date.isoformat(),
            "daily_dates_queried": completed,
            "api_request_count": sum(request_totals.values()),
            "retry_count": sum(retry_totals.values()),
            "global_tables_unchanged": True,
        }
    except Exception as exc:
        _mark_failed(database, batch, exc)
        raise
