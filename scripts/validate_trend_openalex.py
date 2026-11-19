from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
CORE_CORPUS_FILTER = "primary_location.source.is_core:true"
USER_AGENT = "UniversityResearchRadar/0.1 (trend-api-validation)"


class OpenAlexValidationError(RuntimeError):
    def __init__(self, status_code: int | None, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class RequestResult:
    status_code: int
    elapsed_ms: float
    payload: dict[str, Any]
    rate_limit: dict[str, str | None]


class OpenAlexClient:
    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 35.0,
        max_attempts: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.session = session or requests.Session()

    def get(self, params: dict[str, Any]) -> RequestResult:
        request_params = dict(params)
        if self.api_key:
            request_params["api_key"] = self.api_key

        last_error = "OpenAlex request failed"
        for attempt in range(self.max_attempts):
            started = time.perf_counter()
            try:
                response = self.session.get(
                    OPENALEX_WORKS_URL,
                    params=request_params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt + 1 < self.max_attempts:
                    time.sleep(min(2**attempt, 4))
                    continue
                raise OpenAlexValidationError(None, last_error) from exc

            elapsed_ms = (time.perf_counter() - started) * 1000
            rate_limit = {
                "limit": response.headers.get("X-RateLimit-Limit"),
                "remaining": response.headers.get("X-RateLimit-Remaining"),
                "reset": response.headers.get("X-RateLimit-Reset"),
                "retry_after": response.headers.get("Retry-After"),
            }

            if response.status_code == 429 or response.status_code >= 500:
                last_error = _error_message(response)
                if attempt + 1 < self.max_attempts:
                    retry_after = _bounded_retry_after(response.headers.get("Retry-After"))
                    time.sleep(retry_after if retry_after is not None else min(2**attempt, 4))
                    continue
                raise OpenAlexValidationError(response.status_code, last_error)

            if response.status_code >= 400:
                raise OpenAlexValidationError(response.status_code, _error_message(response))

            try:
                payload = response.json()
            except ValueError as exc:
                raise OpenAlexValidationError(
                    response.status_code, "OpenAlex returned non-JSON content"
                ) from exc
            return RequestResult(response.status_code, elapsed_ms, payload, rate_limit)

        raise OpenAlexValidationError(None, last_error)


def _bounded_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 10.0))
    except ValueError:
        return None


def _error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500].replace("\n", " ")
    return str(payload.get("message") or payload.get("error") or payload)[:1000]


def load_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        mapping = json.load(handle)
    if mapping.get("version") != "v1":
        raise ValueError("Expected trend topic mapping version v1")
    return mapping


def approved_topic_ids(mapping: dict[str, Any], category_id: str) -> list[str]:
    try:
        topics = mapping["categories"][category_id]["topics"]
    except KeyError as exc:
        raise ValueError(f"Unknown category: {category_id}") from exc
    return [topic["openalex_topic_id"] for topic in topics if topic["status"] == "approved"]


def build_filter(start: date, end: date, topic_ids: list[str] | None = None) -> str:
    if start > end:
        raise ValueError("start must not be after end")
    filters = [
        CORE_CORPUS_FILTER,
        f"from_publication_date:{start.isoformat()}",
        f"to_publication_date:{end.isoformat()}",
    ]
    if topic_ids:
        filters.append(f"primary_topic.id:{'|'.join(topic_ids)}")
    return ",".join(filters)


def count_query(
    client: OpenAlexClient, start: date, end: date, topic_ids: list[str] | None = None
) -> RequestResult:
    return client.get(
        {
            "filter": build_filter(start, end, topic_ids),
            "per-page": 1,
            "select": "id,publication_date,primary_topic",
        }
    )


def meta_count(result: RequestResult) -> int:
    count = result.payload.get("meta", {}).get("count")
    if not isinstance(count, int):
        raise ValueError("OpenAlex response does not contain integer meta.count")
    return count


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def run_validation(
    mapping_path: Path,
    category_id: str,
    as_of: date,
    api_key: str | None,
) -> dict[str, Any]:
    mapping = load_mapping(mapping_path)
    topic_ids = approved_topic_ids(mapping, category_id)
    if len(topic_ids) < 2:
        raise ValueError("Validation category must contain at least two approved topics")

    client = OpenAlexClient(api_key=api_key)
    requests_made: list[RequestResult] = []
    window_start = as_of - timedelta(days=29)
    one_day = as_of - timedelta(days=1)

    date_result = count_query(client, one_day, one_day)
    requests_made.append(date_result)
    sample = date_result.payload.get("results", [])
    sample_date = sample[0].get("publication_date") if sample else None

    single_results: dict[str, RequestResult] = {}
    for topic_id in topic_ids[:2]:
        result = count_query(client, window_start, as_of, [topic_id])
        requests_made.append(result)
        single_results[topic_id] = result

    multi_result = count_query(client, window_start, as_of, topic_ids[:2])
    requests_made.append(multi_result)
    single_sum = sum(meta_count(item) for item in single_results.values())
    multi_count = meta_count(multi_result)

    group_by_error: dict[str, Any]
    try:
        group_result = client.get(
            {
                "filter": build_filter(window_start, as_of, topic_ids[:2]),
                "group_by": "publication_date",
                "per-page": 200,
            }
        )
        requests_made.append(group_result)
        group_by_error = {
            "supported": True,
            "status_code": group_result.status_code,
            "groups": group_result.payload.get("group_by", []),
        }
    except OpenAlexValidationError as exc:
        group_by_error = {
            "supported": False,
            "status_code": exc.status_code,
            "error": str(exc),
        }

    handled_error: dict[str, Any]
    try:
        client.get({"filter": "this_filter_does_not_exist:true", "per-page": 1})
        handled_error = {"handled": False, "error": "Invalid request unexpectedly succeeded"}
    except OpenAlexValidationError as exc:
        handled_error = {
            "handled": True,
            "status_code": exc.status_code,
            "error": str(exc),
        }

    latencies = [item.elapsed_ms for item in requests_made]
    rate_limit_samples = [item.rate_limit for item in requests_made]
    meta_notice = date_result.payload.get("meta", {}).get("notice")
    observed_429 = any(item.status_code == 429 for item in requests_made)

    return {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of.isoformat(),
        "window": {
            "start": window_start.isoformat(),
            "end": as_of.isoformat(),
            "inclusive_days": 30,
        },
        "mapping_version": mapping["version"],
        "category_id": category_id,
        "query_contract": {
            "entity": "works",
            "geography": "global (no institution/country filter)",
            "corpus_filter": CORE_CORPUS_FILTER,
            "topic_filter": "primary_topic.id",
            "date_filter": "publication_date via from/to_publication_date",
        },
        "tests": {
            "publication_date_filter": {
                "passed": date_result.status_code == 200 and sample_date == one_day.isoformat(),
                "date": one_day.isoformat(),
                "meta_count": meta_count(date_result),
                "sample_publication_date": sample_date,
            },
            "primary_topic_filter": {
                "passed": all(item.status_code == 200 for item in single_results.values()),
                "counts": {key: meta_count(value) for key, value in single_results.items()},
            },
            "multiple_topics": {
                "passed": multi_result.status_code == 200,
                "topic_ids": topic_ids[:2],
                "meta_count": multi_count,
            },
            "meta_count": {
                "passed": isinstance(multi_count, int),
                "value": multi_count,
            },
            "group_by_publication_date": group_by_error,
            "duplicate_count_risk": {
                "passed": multi_count == single_sum,
                "single_topic_sum": single_sum,
                "multi_topic_count": multi_count,
                "difference": multi_count - single_sum,
                "interpretation": (
                    "No overlap for primary_topic.id because each work has one primary topic."
                    if multi_count == single_sum
                    else "Observed a count mismatch; investigate before using OR counts."
                ),
            },
            "response_time_ms": {
                "samples": len(latencies),
                "min": round(min(latencies), 1),
                "median": round(statistics.median(latencies), 1),
                "p95": round(percentile(latencies, 0.95) or 0.0, 1),
                "max": round(max(latencies), 1),
            },
            "rate_limit": {
                "observed_429": observed_429,
                "headers": rate_limit_samples,
                "notice": meta_notice,
            },
            "error_handling": handled_error,
        },
        "recommended_daily_query": {
            "endpoint": OPENALEX_WORKS_URL,
            "params": {
                "filter": build_filter(one_day, one_day, topic_ids),
                "per-page": 1,
                "select": "id",
            },
            "count_from": "meta.count",
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Read-only validation of OpenAlex queries for the global trend module."
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=root / "config" / "trend_topic_mapping.json",
    )
    parser.add_argument("--category", default="robotics_embodied")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = run_validation(args.mapping, args.category, args.as_of, args.api_key)
    except (OSError, ValueError, OpenAlexValidationError, requests.RequestException) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
