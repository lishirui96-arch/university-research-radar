from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
from uuid import uuid4

import requests

from storage import initialize_database


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
CORE_FILTER = "primary_location.source.is_core:true"
QUERY_VERSION = "openalex-primary-topic-groupby-v1"
CALCULATION_VERSION = "topic-ranking-daily-v1"
USER_AGENT = "UniversityResearchRadar/1.3.5 (topic-hotspot-updater)"


@dataclass
class GroupResult:
    counts: dict[str, int]
    requests: int
    retries: int
    query_as_of: str


class TopicOpenAlexClient:
    def __init__(self, api_key: str, timeout: float = 45, max_attempts: int = 5) -> None:
        if not api_key:
            raise ValueError("OPENALEX_API_KEY is required")
        self.api_key = api_key
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.session = requests.Session()

    def _get(self, params: dict[str, Any]) -> tuple[dict[str, Any], int]:
        for attempt in range(self.max_attempts):
            try:
                response = self.session.get(
                    OPENALEX_WORKS_URL,
                    params={**params, "api_key": self.api_key},
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                )
            except requests.RequestException:
                if attempt + 1 == self.max_attempts:
                    raise
                time.sleep(min(2**attempt, 16))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 == self.max_attempts:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2**attempt
                except ValueError:
                    delay = 2**attempt
                time.sleep(min(max(delay, 0), 30))
                continue
            response.raise_for_status()
            return response.json(), attempt
        raise RuntimeError("OpenAlex retry loop ended unexpectedly")

    def grouped_topics(
        self, start: date, end: date, topic_ids: list[str] | None = None
    ) -> GroupResult:
        filters = [
            CORE_FILTER,
            f"from_publication_date:{start.isoformat()}",
            f"to_publication_date:{end.isoformat()}",
        ]
        if topic_ids:
            filters.append(f"primary_topic.id:{'|'.join(topic_ids)}")
        cursor: str | None = "*"
        counts: dict[str, int] = {}
        requests_count = retries = 0
        while cursor:
            payload, request_retries = self._get(
                {
                    "filter": ",".join(filters), "group_by": "primary_topic.id",
                    "per-page": 200, "cursor": cursor,
                }
            )
            requests_count += 1
            retries += request_retries
            for group in payload.get("group_by", []):
                topic_id = str(group.get("key", "")).rsplit("/", 1)[-1]
                count = group.get("count")
                if topic_id.startswith("T") and isinstance(count, int) and count >= 0:
                    counts[topic_id] = count
            cursor = payload.get("meta", {}).get("next_cursor")
        return GroupResult(
            counts=counts, requests=requests_count, retries=retries,
            query_as_of=datetime.now(timezone.utc).isoformat(),
        )


def _rank(counts: dict[str, int], all_topic_ids: set[str]) -> list[tuple[str, int]]:
    complete = {topic_id: counts.get(topic_id, 0) for topic_id in all_topic_ids}
    return sorted(complete.items(), key=lambda item: (-item[1], item[0]))


def run_daily_update(database: Path, ranking_date: date) -> dict[str, Any]:
    initialize_database(database)
    client = TopicOpenAlexClient(os.environ.get("OPENALEX_API_KEY", "").strip())
    with sqlite3.connect(database) as connection:
        all_topic_ids = {
            row[0] for row in connection.execute("SELECT topic_id FROM openalex_topics")
        }
    if len(all_topic_ids) != 4516:
        raise ValueError("Expected the audited 4,516 Topic taxonomy before updating")

    rankings: dict[int, list[tuple[str, int]]] = {}
    request_count = retry_count = 0
    query_as_of = ""
    for period in (90, 360):
        start = ranking_date - timedelta(days=period - 1)
        result = client.grouped_topics(start, ranking_date)
        rankings[period] = _rank(result.counts, all_topic_ids)
        request_count += result.requests
        retry_count += result.retries
        query_as_of = max(query_as_of, result.query_as_of)

    selected = sorted(
        {topic for period in (90, 360) for topic, _ in rankings[period][:10]}
    )
    window_start = ranking_date - timedelta(days=359)
    with sqlite3.connect(database) as connection:
        existing = {
            (row[0], row[1])
            for row in connection.execute(
                """
                SELECT date, topic_id FROM topic_daily_counts
                WHERE is_current=1 AND query_status='success'
                  AND date BETWEEN ? AND ?
                """,
                (window_start.isoformat(), ranking_date.isoformat()),
            )
        }
    revision_dates = {
        ranking_date - timedelta(days=offset) for offset in (0, 2, 3, 7, 14)
    }
    query_dates = sorted(
        revision_dates
        | {
            window_start + timedelta(days=offset)
            for offset in range(360)
            if any(
                ((window_start + timedelta(days=offset)).isoformat(), topic_id) not in existing
                for topic_id in selected
            )
        }
    )
    daily_updates: dict[tuple[str, str], tuple[int, str]] = {}
    for publication_date in query_dates:
        result = client.grouped_topics(publication_date, publication_date, selected)
        request_count += result.requests
        retry_count += result.retries
        query_as_of = max(query_as_of, result.query_as_of)
        for topic_id in selected:
            daily_updates[(publication_date.isoformat(), topic_id)] = (
                result.counts.get(topic_id, 0), result.query_as_of
            )

    with sqlite3.connect(database) as connection:
        current_counts = {
            (row[0], row[1]): int(row[2])
            for row in connection.execute(
                """
                SELECT date, topic_id, daily_works_count FROM topic_daily_counts
                WHERE is_current=1 AND query_status='success'
                  AND date BETWEEN ? AND ?
                """,
                (window_start.isoformat(), ranking_date.isoformat()),
            )
        }
    projected = {**current_counts}
    projected.update({key: value[0] for key, value in daily_updates.items()})
    for period in (90, 360):
        start = ranking_date - timedelta(days=period - 1)
        for topic_id, total in rankings[period][:10]:
            values = [
                projected.get(((start + timedelta(days=offset)).isoformat(), topic_id))
                for offset in range(period)
            ]
            if any(value is None for value in values) or sum(values) != total:
                raise ValueError(
                    f"Daily series validation failed for {period}d {topic_id}; "
                    "the previous published snapshot remains active"
                )

    now = datetime.now().astimezone().isoformat()
    run_id = f"topic-daily-{ranking_date.isoformat()}-{uuid4().hex[:8]}"
    calculation_version = f"{CALCULATION_VERSION}:{run_id}"
    connection = sqlite3.connect(database, timeout=30)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO topic_update_runs(
                    run_id, ranking_date, source_type, status, query_as_of,
                    calculation_version, started_at, completed_at, created_at, updated_at
                ) VALUES (?, ?, 'daily_update', 'validated', ?, ?, ?, NULL, ?, ?)
                """,
                (run_id, ranking_date.isoformat(), query_as_of, calculation_version, now, now, now),
            )
            for (day, topic_id), (count, counted_at) in daily_updates.items():
                current = connection.execute(
                    """
                    SELECT id, daily_works_count, revision_no FROM topic_daily_counts
                    WHERE date=? AND topic_id=? AND is_current=1
                    """,
                    (day, topic_id),
                ).fetchone()
                if current and int(current[1]) == count:
                    continue
                revision = int(current[2]) + 1 if current else 1
                if current:
                    connection.execute(
                        "UPDATE topic_daily_counts SET is_current=0, updated_at=? WHERE id=?",
                        (now, current[0]),
                    )
                connection.execute(
                    """
                    INSERT INTO topic_daily_counts(
                        date, topic_id, daily_works_count, query_as_of, query_status,
                        revision_no, is_current, query_version, taxonomy_version,
                        source_run_id, revision_reason, created_at, updated_at
                    ) SELECT ?, ?, ?, ?, 'success', ?, 1, ?, taxonomy_version,
                             ?, 'scheduled D-0/D-2/D-3/D-7/D-14 revision', ?, ?
                      FROM openalex_topics WHERE topic_id=?
                    """,
                    (day, topic_id, count, counted_at, revision, QUERY_VERSION,
                     run_id, now, now, topic_id),
                )
            for period in (90, 360):
                start = ranking_date - timedelta(days=period - 1)
                connection.execute(
                    """
                    UPDATE topic_ranking_snapshots SET is_current=0, updated_at=?
                    WHERE ranking_date=? AND period_days=? AND is_current=1
                    """,
                    (now, ranking_date.isoformat(), period),
                )
                connection.executemany(
                    """
                    INSERT INTO topic_ranking_snapshots(
                        ranking_date, period_days, topic_id, rank, period_works_count,
                        window_start, window_end, query_as_of, calculation_version,
                        source_run_id, is_current, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    [
                        (ranking_date.isoformat(), period, topic_id, rank, count,
                         start.isoformat(), ranking_date.isoformat(), query_as_of,
                         calculation_version, run_id, now, now)
                        for rank, (topic_id, count) in enumerate(rankings[period], start=1)
                    ],
                )
            connection.execute(
                """
                UPDATE topic_update_runs SET status='published', completed_at=?, updated_at=?
                WHERE run_id=?
                """,
                (now, now, run_id),
            )
    finally:
        connection.close()
    return {
        "run_id": run_id, "ranking_date": ranking_date.isoformat(),
        "selected_topic_count": len(selected), "daily_dates_queried": len(query_dates),
        "successful_requests": request_count, "retry_attempts": retry_count,
        "status": "published",
    }
