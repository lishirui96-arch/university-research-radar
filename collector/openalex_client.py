from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import requests


class OpenAlexError(RuntimeError):
    """Base exception that never includes a URL containing credentials."""


class OpenAlexAuthenticationError(OpenAlexError):
    pass


class OpenAlexPermissionError(OpenAlexError):
    pass


class OpenAlexResponseError(OpenAlexError):
    pass


@dataclass(frozen=True)
class OpenAlexPage:
    results: list[dict[str, Any]]
    total_count: int | None
    next_cursor: str | None
    status_code: int
    response_bytes: int


@dataclass
class RequestStats:
    request_count: int = 0
    response_bytes: int = 0
    retry_count: int = 0
    rate_limit: int | None = None
    rate_remaining: int | None = None
    rate_reset_seconds: int | None = None


class OpenAlexClient:
    BASE_URL = "https://api.openalex.org"
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str | None = None,
        *,
        session: requests.Session | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 5,
        min_interval_seconds: float = 0.12,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("OPENALEX_API_KEY", "")
        self._api_key = key.strip()
        if not self._api_key:
            raise OpenAlexAuthenticationError(
                "OPENALEX_API_KEY is not available in the current process environment."
            )
        self._session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.min_interval_seconds = min_interval_seconds
        self._sleeper = sleeper
        self._last_request_at = 0.0
        self.stats = RequestStats()

    def reset_stats(self) -> None:
        self.stats = RequestStats()

    def get_page(
        self,
        endpoint: str,
        *,
        params: dict[str, Any],
        select_fields: tuple[str, ...],
    ) -> OpenAlexPage:
        if not select_fields:
            raise ValueError("OpenAlex requests must use an explicit select field list.")
        safe_endpoint = endpoint.strip("/")
        request_params = dict(params)
        request_params["select"] = ",".join(select_fields)
        request_params["api_key"] = self._api_key

        response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            self._respect_rate_limit()
            try:
                self.stats.request_count += 1
                response = self._session.get(
                    f"{self.BASE_URL}/{safe_endpoint}",
                    params=request_params,
                    headers={"Accept": "application/json"},
                    timeout=self.timeout_seconds,
                )
                self._last_request_at = time.monotonic()
                self.stats.response_bytes += len(response.content)
                self._capture_rate_headers(response)
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise OpenAlexResponseError("OpenAlex network request failed.") from exc
                self.stats.retry_count += 1
                self._sleeper(self._backoff_seconds(attempt, None))
                continue

            if response.status_code == 401:
                raise OpenAlexAuthenticationError("OpenAlex rejected the configured API key.")
            if response.status_code == 403:
                raise OpenAlexPermissionError(
                    f"OpenAlex denied access to endpoint {safe_endpoint!r}."
                )
            if response.status_code in self.RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    raise OpenAlexResponseError(
                        f"OpenAlex returned HTTP {response.status_code} after retries."
                    )
                self.stats.retry_count += 1
                retry_after = self._integer_header(response, "Retry-After")
                self._sleeper(self._backoff_seconds(attempt, retry_after))
                continue
            if not response.ok:
                raise OpenAlexResponseError(
                    f"OpenAlex returned HTTP {response.status_code} for endpoint "
                    f"{safe_endpoint!r}."
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise OpenAlexResponseError("OpenAlex returned invalid JSON.") from exc
            results = payload.get("results")
            if not isinstance(results, list):
                raise OpenAlexResponseError("OpenAlex response is missing a results list.")
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            count = meta.get("count")
            return OpenAlexPage(
                results=results,
                total_count=int(count) if isinstance(count, (int, float)) else None,
                next_cursor=(
                    str(meta["next_cursor"])
                    if isinstance(meta.get("next_cursor"), str) and meta["next_cursor"]
                    else None
                ),
                status_code=response.status_code,
                response_bytes=len(response.content),
            )

        raise OpenAlexResponseError("OpenAlex request did not produce a response.")

    def iter_cursor(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        select_fields: tuple[str, ...],
        cursor: str | None = None,
        per_page: int = 200,
        max_pages: int | None = None,
    ) -> Iterator[OpenAlexPage]:
        current_cursor = cursor or "*"
        pages = 0
        while current_cursor:
            page_params = dict(params or {})
            page_params["cursor"] = current_cursor
            page_params["per-page"] = per_page
            page = self.get_page(
                endpoint, params=page_params, select_fields=select_fields
            )
            yield page
            pages += 1
            if max_pages is not None and pages >= max_pages:
                break
            current_cursor = page.next_cursor

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_interval_seconds - elapsed
        if remaining > 0:
            self._sleeper(remaining)

    def _capture_rate_headers(self, response: requests.Response) -> None:
        self.stats.rate_limit = self._integer_header(response, "X-RateLimit-Limit")
        self.stats.rate_remaining = self._integer_header(
            response, "X-RateLimit-Remaining"
        )
        self.stats.rate_reset_seconds = self._integer_header(
            response, "X-RateLimit-Reset"
        )

    @staticmethod
    def _integer_header(response: requests.Response, name: str) -> int | None:
        value = response.headers.get(name)
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _backoff_seconds(attempt: int, retry_after: int | None) -> float:
        if retry_after is not None:
            return max(0.0, float(retry_after))
        return min(60.0, (2**attempt) + random.uniform(0.0, 0.5))

