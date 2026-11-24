from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable
from uuid import uuid4

import pandas as pd
import requests

from citation_rankings import publish_citation_snapshot
from dashboard_repository import (
    V14_TAXONOMY_VERSION,
    get_v14_hotspot_dashboard,
    get_v15_regional_dashboard,
)
from storage import initialize_database


OPENALEX_URL = "https://api.openalex.org/works"
CORE_CANDIDATE_FILTER = "primary_location.source.is_core:true"
SELECT_CANDIDATES = (
    "id,doi,display_name,publication_date,type,cited_by_count,"
    "primary_topic,primary_location"
)


@dataclass(frozen=True)
class TopicCitationResult:
    topic_id: str
    topic_name: str
    candidate_count: int
    candidates_scanned: int
    api_request_count: int
    stop_cumulative_upper_bound: int
    tenth_citation_count: int
    rows: list[dict[str, Any]]


class OpenAlexCitationClient:
    def __init__(self, api_key: str, *, max_attempts: int = 4) -> None:
        if not api_key:
            raise ValueError("OPENALEX_API_KEY is required")
        self.api_key = api_key
        self.max_attempts = max_attempts
        self.request_count = 0

    def get(self, parameters: dict[str, Any]) -> dict[str, Any]:
        safe_parameters = {**parameters, "api_key": self.api_key}
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            self.request_count += 1
            try:
                response = requests.get(
                    OPENALEX_URL,
                    params=safe_parameters,
                    timeout=90,
                    headers={"User-Agent": "UniversityResearchRadar/1.6 (windowed citations)"},
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"OpenAlex HTTP {response.status_code}")
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as error:
                last_error = error
                if attempt + 1 == self.max_attempts:
                    break
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"OpenAlex request failed after retries: {last_error}")

    def candidate_page(
        self, topic_id: str, cursor: str, region_code: str = "GLOBAL"
    ) -> dict[str, Any]:
        region_filter = ""
        if region_code in {"CN", "US"}:
            region_filter = f",authorships.institutions.country_code:{region_code}"
        return self.get({
            "filter": (
                f"primary_topic.id:{topic_id},{CORE_CANDIDATE_FILTER}{region_filter}"
            ),
            "sort": "cited_by_count:desc",
            "per-page": 200,
            "cursor": cursor,
            "select": SELECT_CANDIDATES,
        })

    def grouped_window_counts(
        self, work_ids: list[str], window_start: date, window_end: date
    ) -> tuple[dict[str, int], int]:
        if not work_ids:
            return {}, 0
        query_filter = (
            f"cites:{'|'.join(work_ids)},"
            f"from_publication_date:{window_start.isoformat()},"
            f"to_publication_date:{window_end.isoformat()}"
        )
        payload = self.get({
            "filter": query_filter,
            "group_by": "cites",
            "per-page": 200,
        })
        groups = payload.get("group_by") or []
        counts = {
            str(group.get("key") or "").rsplit("/", 1)[-1]: int(group["count"])
            for group in groups
        }
        missing_upper_bound = int(groups[-1]["count"]) if len(groups) == 200 else 0
        return {work_id: counts[work_id] for work_id in work_ids if work_id in counts}, missing_upper_bound

    def exact_window_count(
        self, work_id: str, window_start: date, window_end: date
    ) -> int:
        payload = self.get({
            "filter": (
                f"cites:{work_id},from_publication_date:{window_start.isoformat()},"
                f"to_publication_date:{window_end.isoformat()}"
            ),
            "per-page": 1,
            "select": "id",
        })
        return int(payload["meta"]["count"])


def _work_id(value: Any) -> str:
    return str(value or "").rsplit("/", 1)[-1]


def _candidate_record(work: dict[str, Any], topic_id: str) -> dict[str, Any]:
    source = ((work.get("primary_location") or {}).get("source") or {})
    return {
        "openalex_work_id": _work_id(work.get("id")),
        "topic_id": topic_id,
        "title": str(work.get("display_name") or "Untitled work"),
        "doi": work.get("doi"),
        "openalex_url": str(work.get("id") or ""),
        "venue": source.get("display_name"),
        "publication_date": work.get("publication_date"),
        "work_type": work.get("type"),
        "cumulative_citations": int(work.get("cited_by_count") or 0),
    }


def collect_topic_citations(
    client: OpenAlexCitationClient,
    *,
    topic_id: str,
    topic_name: str,
    field_id: str,
    region_code: str = "GLOBAL",
    window_start: date,
    window_end: date,
    max_candidate_pages: int | None = None,
) -> TopicCitationResult:
    request_start = client.request_count
    cursor = "*"
    page_number = 0
    candidate_count = 0
    scanned: dict[str, dict[str, Any]] = {}
    exact_counts: dict[str, int] = {}
    unresolved_bounds: dict[str, int] = {}
    stop_upper_bound = 0

    while cursor:
        page_number += 1
        payload = client.candidate_page(topic_id, cursor, region_code)
        candidate_count = int(payload["meta"]["count"])
        candidates = [_candidate_record(item, topic_id) for item in payload.get("results", [])]
        if not candidates:
            break
        for candidate in candidates:
            scanned[candidate["openalex_work_id"]] = candidate

        for offset in range(0, len(candidates), 100):
            work_ids = [
                item["openalex_work_id"] for item in candidates[offset:offset + 100]
            ]
            grouped, missing_upper = client.grouped_window_counts(
                work_ids, window_start, window_end
            )
            exact_counts.update(grouped)
            for work_id in work_ids:
                if work_id not in grouped:
                    unresolved_bounds[work_id] = missing_upper

        positive = sorted((count for count in exact_counts.values() if count > 0), reverse=True)
        if len(positive) >= 10:
            tenth = positive[9]
            needs_exact = [
                work_id for work_id, bound in unresolved_bounds.items()
                if bound >= tenth
            ]
            for work_id in needs_exact:
                exact_counts[work_id] = client.exact_window_count(
                    work_id, window_start, window_end
                )
                unresolved_bounds.pop(work_id, None)
            positive = sorted((count for count in exact_counts.values() if count > 0), reverse=True)
            tenth = positive[9] if len(positive) >= 10 else 0
        else:
            tenth = 0

        stop_upper_bound = int(candidates[-1]["cumulative_citations"])
        unresolved_max = max(unresolved_bounds.values(), default=0)
        if tenth > 0 and stop_upper_bound < tenth and unresolved_max < tenth:
            break
        if max_candidate_pages is not None and page_number >= max_candidate_pages:
            raise RuntimeError(
                f"Topic {topic_id} did not reach a proven TOP 10 after "
                f"{len(scanned)} candidates; remaining cumulative upper bound "
                f"is {stop_upper_bound}, current tenth is {tenth}."
            )
        cursor = str(payload.get("meta", {}).get("next_cursor") or "")

    ranked = [
        {**scanned[work_id], "window_citation_count": count, "field_id": field_id}
        for work_id, count in exact_counts.items() if count > 0
    ]
    ranked.sort(key=lambda row: (
        -int(row["window_citation_count"]),
        -(date.fromisoformat(row["publication_date"]).toordinal() if row["publication_date"] else 0),
        row["openalex_work_id"],
    ))
    if len(ranked) < 10:
        raise RuntimeError(f"Topic {topic_id} has fewer than 10 proven cited works")
    tenth = int(ranked[9]["window_citation_count"])
    if stop_upper_bound >= tenth or max(unresolved_bounds.values(), default=0) >= tenth:
        raise RuntimeError(f"Topic {topic_id} TOP 10 is not proven complete")
    return TopicCitationResult(
        topic_id=topic_id,
        topic_name=topic_name,
        candidate_count=candidate_count,
        candidates_scanned=len(scanned),
        api_request_count=client.request_count - request_start,
        stop_cumulative_upper_bound=stop_upper_bound,
        tenth_citation_count=tenth,
        rows=ranked[:10],
    )


def _result_payload(result: TopicCitationResult) -> dict[str, Any]:
    return {
        "topic_id": result.topic_id,
        "topic_name": result.topic_name,
        "candidate_count": result.candidate_count,
        "candidates_scanned": result.candidates_scanned,
        "api_request_count": result.api_request_count,
        "stop_cumulative_upper_bound": result.stop_cumulative_upper_bound,
        "tenth_citation_count": result.tenth_citation_count,
        "rows": result.rows,
    }


def _result_from_payload(payload: dict[str, Any]) -> TopicCitationResult:
    return TopicCitationResult(**payload)


def _load_cached_result(
    database: str | Path, *, region_code: str, period_days: int,
    window_start: date, window_end: date, topic_id: str,
) -> TopicCitationResult | None:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT result_json FROM citation_topic_cache
            WHERE region_code=? AND period_days=? AND window_start=? AND window_end=?
              AND topic_id=? AND query_version=?
            """,
            (
                region_code, period_days, window_start.isoformat(),
                window_end.isoformat(), topic_id, "openalex-referenced-works-v1",
            ),
        ).fetchone()
        if row:
            result = _result_from_payload(json.loads(row["result_json"]))
            return TopicCitationResult(**{**_result_payload(result), "api_request_count": 0})

        scope = connection.execute(
            """
            SELECT s.*, b.batch_id
            FROM citation_snapshot_batches b
            JOIN citation_snapshot_scopes s ON s.batch_id=b.batch_id
            WHERE b.status='published' AND b.period_days=?
              AND b.window_start=? AND b.window_end=?
              AND s.region_code=? AND s.topic_id=? AND s.status='success'
              AND s.candidate_count IS NOT NULL
            ORDER BY b.completed_at DESC LIMIT 1
            """,
            (
                period_days, window_start.isoformat(), window_end.isoformat(),
                region_code, topic_id,
            ),
        ).fetchone()
        if scope is None:
            return None
        works = [
            dict(item) for item in connection.execute(
                """
                SELECT openalex_work_id, topic_id, title, doi, openalex_url,
                       venue, publication_date, window_citation_count, field_id
                FROM citation_topic_work_snapshots
                WHERE batch_id=? AND region_code=? AND topic_id=?
                ORDER BY window_citation_count DESC, publication_date DESC,
                         openalex_work_id ASC LIMIT 10
                """,
                (scope["batch_id"], region_code, topic_id),
            )
        ]
        return TopicCitationResult(
            topic_id=topic_id,
            topic_name=topic_id,
            candidate_count=int(scope["candidate_count"]),
            candidates_scanned=int(scope["candidates_scanned"]),
            api_request_count=0,
            stop_cumulative_upper_bound=int(scope["unchecked_cumulative_upper_bound"]),
            tenth_citation_count=int(scope["tenth_citation_count"]),
            rows=works,
        )


def _save_cached_result(
    database: str | Path, *, region_code: str, period_days: int,
    window_start: date, window_end: date, field_id: str,
    result: TopicCitationResult,
) -> None:
    now = datetime.now().astimezone().isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO citation_topic_cache(
                region_code, period_days, window_start, window_end, topic_id,
                field_id, result_json, candidate_count, candidates_scanned,
                tenth_citation_count, unchecked_cumulative_upper_bound,
                api_request_count, query_version, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                region_code, period_days, window_start, window_end, topic_id,
                query_version
            ) DO UPDATE SET
                result_json=excluded.result_json,
                field_id=excluded.field_id,
                candidate_count=excluded.candidate_count,
                candidates_scanned=excluded.candidates_scanned,
                tenth_citation_count=excluded.tenth_citation_count,
                unchecked_cumulative_upper_bound=excluded.unchecked_cumulative_upper_bound,
                api_request_count=excluded.api_request_count,
                completed_at=excluded.completed_at
            """,
            (
                region_code, period_days, window_start.isoformat(),
                window_end.isoformat(), result.topic_id, field_id,
                json.dumps(_result_payload(result), ensure_ascii=False),
                result.candidate_count, result.candidates_scanned,
                result.tenth_citation_count, result.stop_cumulative_upper_bound,
                result.api_request_count, "openalex-referenced-works-v1", now,
            ),
        )
        connection.commit()


def collect_and_publish_view(
    database: str | Path,
    *,
    region_code: str,
    period_days: int,
    field_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    region = str(region_code).upper()
    if region not in {"GLOBAL", "CN", "US"}:
        raise ValueError("region_code must be GLOBAL, CN, or US")
    if period_days not in {90, 360}:
        raise ValueError("period_days must be 90 or 360")
    initialize_database(Path(database))
    dashboard = (
        get_v14_hotspot_dashboard(
            database, period_days=period_days, field_id=field_id, sort_by="works"
        )
        if region == "GLOBAL"
        else get_v15_regional_dashboard(
            database, region_code=region, period_days=period_days,
            field_id=field_id, sort_by="works",
        )
    )
    if dashboard["status"] == "unavailable":
        raise RuntimeError(f"{region} dashboard data is unavailable")
    topics = dashboard["ranking"].head(10).copy()
    window_end = date.fromisoformat(str(topics.iloc[0]["window_end"]))
    window_start = date.fromisoformat(str(topics.iloc[0]["window_start"]))
    resolved_key = api_key or os.environ.get("OPENALEX_API_KEY", "")
    topic_rows = list(topics.itertuples(index=False))
    results_by_id: dict[str, TopicCitationResult] = {}
    pending_rows = []
    for row in topic_rows:
        cached = _load_cached_result(
            database, region_code=region, period_days=period_days,
            window_start=window_start, window_end=window_end,
            topic_id=str(row.topic_id),
        )
        if cached is None:
            pending_rows.append(row)
        else:
            results_by_id[str(row.topic_id)] = cached
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                collect_topic_citations,
                OpenAlexCitationClient(resolved_key),
                topic_id=str(row.topic_id),
                topic_name=str(row.topic_name),
                field_id=str(row.field_id),
                region_code=region,
                window_start=window_start,
                window_end=window_end,
            ): str(row.topic_id)
            for row in pending_rows
        }
        failures: list[tuple[str, Exception]] = []
        for future in as_completed(futures):
            topic_id = futures[future]
            try:
                result = future.result()
            except Exception as error:
                failures.append((topic_id, error))
                continue
            results_by_id[topic_id] = result
            matching = next(row for row in pending_rows if str(row.topic_id) == topic_id)
            _save_cached_result(
                database, region_code=region, period_days=period_days,
                window_start=window_start, window_end=window_end,
                field_id=str(matching.field_id), result=result,
            )
        if failures:
            failed_topics = ", ".join(topic_id for topic_id, _ in failures)
            raise RuntimeError(
                f"Citation collection failed for Topics: {failed_topics}"
            ) from failures[0][1]
    results = [results_by_id[str(row.topic_id)] for row in topic_rows]
    total_requests = sum(result.api_request_count for result in results)

    records = []
    for result in results:
        for row in result.rows:
            records.append({**row, "region_code": region})
    frame = pd.DataFrame(records)
    batch_id = (
        f"citation-v16-{region.lower()}-{field_id or 'all'}-"
        f"{period_days}d-{window_end.isoformat()}-"
        f"{uuid4().hex[:8]}"
    )
    query_as_of = datetime.now().astimezone().isoformat()
    diagnostics = {
        (region, result.topic_id): {
            "candidate_count": result.candidate_count,
            "candidates_scanned": result.candidates_scanned,
            "tenth_citation_count": result.tenth_citation_count,
            "stop_cumulative_upper_bound": result.stop_cumulative_upper_bound,
            "api_request_count": result.api_request_count,
        }
        for result in results
    }
    publish_citation_snapshot(
        database,
        batch_id=batch_id,
        ranking_date=window_end,
        period_days=period_days,
        taxonomy_version=V14_TAXONOMY_VERSION,
        rows=frame,
        query_as_of=query_as_of,
        expected_scope_count=len(results),
        citing_work_count=0,
        citation_edge_count=int(frame["window_citation_count"].sum()),
        api_request_count=total_requests,
        completed_scopes=[(region, result.topic_id) for result in results],
        scope_diagnostics=diagnostics,
    )
    return {
        "batch_id": batch_id,
        "period_days": period_days,
        "region_code": region,
        "field_id": field_id,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "topic_count": len(results),
        "work_count": len(frame),
        "api_request_count": total_requests,
        "query_as_of": query_as_of,
        "topics": [
            {
                "topic_id": result.topic_id,
                "topic_name": result.topic_name,
                "candidate_count": result.candidate_count,
                "candidates_scanned": result.candidates_scanned,
                "api_request_count": result.api_request_count,
                "tenth_citation_count": result.tenth_citation_count,
                "stop_cumulative_upper_bound": result.stop_cumulative_upper_bound,
                "top_work_id": result.rows[0]["openalex_work_id"],
                "top_work_citations": result.rows[0]["window_citation_count"],
            }
            for result in results
        ],
    }


def collect_and_publish_global_view(
    database: str | Path, *, period_days: int, api_key: str | None = None,
) -> dict[str, Any]:
    return collect_and_publish_view(
        database, region_code="GLOBAL", period_days=period_days,
        field_id=None, api_key=api_key,
    )
