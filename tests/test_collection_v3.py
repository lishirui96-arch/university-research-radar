from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Iterator

from collector.catalog_sync import sync_institutions, sync_topics
from collector.openalex_client import (
    OpenAlexClient,
    OpenAlexPage,
    OpenAlexPermissionError,
    RequestStats,
)
from collector.works_ingest import ingest_works_for_date
from repositories.collection_repository import CollectionRepository
from storage import initialize_database


class FakeClient:
    def __init__(self, pages_by_cursor: dict[str, OpenAlexPage]) -> None:
        self.pages_by_cursor = pages_by_cursor
        self.stats = RequestStats()

    def reset_stats(self) -> None:
        self.stats = RequestStats()

    def iter_cursor(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None,
        select_fields: tuple[str, ...],
        cursor: str | None,
        per_page: int = 200,
        max_pages: int | None = None,
    ) -> Iterator[OpenAlexPage]:
        current = cursor or "*"
        pages = 0
        while current:
            page = self.pages_by_cursor[current]
            self.stats.request_count += 1
            self.stats.response_bytes += page.response_bytes
            self.stats.rate_limit = 10_000
            self.stats.rate_remaining = 9_000 - self.stats.request_count
            yield page
            pages += 1
            if max_pages is not None and pages >= max_pages:
                break
            current = page.next_cursor


class FakeResponse:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status_code = status
        self._payload = payload
        self.content = b"{}"
        self.headers = {
            "X-RateLimit-Limit": "10000",
            "X-RateLimit-Remaining": "9999",
            "X-RateLimit-Reset": "100",
        }

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


class CollectionV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "radar.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_v3_migration_is_idempotent(self) -> None:
        initialize_database(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM schema_metadata WHERE key='schema_version'"
                ).fetchone()[0],
                "5",
            )
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(
                {
                    "collection_jobs",
                    "collection_job_attempts",
                    "collection_checkpoints",
                    "source_query_audit",
                    "snapshot_batches",
                    "published_snapshots",
                    "data_quality_reports",
                }.issubset(tables)
            )
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_job_lease_is_mutually_exclusive_and_failed_batch_does_not_publish(self) -> None:
        repository = CollectionRepository(self.db_path)
        handle = repository.ensure_job(
            job_type="test_job", logical_date="2026-11-17", max_attempts=1
        )
        acquired, attempt = repository.acquire_job(handle.job_id, worker_id="worker-a")
        self.assertTrue(acquired)
        acquired_again, _ = repository.acquire_job(handle.job_id, worker_id="worker-b")
        self.assertFalse(acquired_again)
        repository.finish_attempt(
            job_id=handle.job_id,
            attempt_number=int(attempt or 0),
            success=False,
            request_count=1,
            response_bytes=10,
            retry_count=0,
            error=RuntimeError("expected failure"),
        )
        with self.assertRaises(RuntimeError):
            repository.publish_batch(batch_id=handle.batch_id, snapshot_type="test")
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM published_snapshots").fetchone()[0],
                0,
            )

    def test_topics_resume_and_idempotent_rerun(self) -> None:
        pages = {
            "*": OpenAlexPage(
                [{"id": "https://openalex.org/T1", "display_name": "One"}],
                2,
                "next",
                200,
                100,
            ),
            "next": OpenAlexPage(
                [{"id": "https://openalex.org/T2", "display_name": "Two"}],
                2,
                None,
                200,
                100,
            ),
        }
        first = sync_topics(
            self.db_path,
            client=FakeClient(pages),
            logical_date="2026-11-17",
            max_pages=1,
        )
        self.assertEqual(first.status, "pending")
        second = sync_topics(
            self.db_path,
            client=FakeClient(pages),
            logical_date="2026-11-17",
        )
        self.assertEqual(second.status, "succeeded")
        self.assertEqual(second.resumed_from_page, 1)
        third = sync_topics(
            self.db_path,
            client=FakeClient(pages),
            logical_date="2026-11-17",
        )
        self.assertEqual(third.request_count, 0)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM topics").fetchone()[0], 2)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM topic_catalog_metadata").fetchone()[0],
                2,
            )

    def test_institutions_rerun_does_not_duplicate(self) -> None:
        records = [
            {
                "id": "https://openalex.org/I1",
                "display_name": "University One",
                "display_name_acronyms": ["U1"],
                "display_name_alternatives": ["Uni One"],
                "country_code": "CN",
                "type": "education",
                "lineage": ["https://openalex.org/I1"],
            }
        ]
        pages = {"*": OpenAlexPage(records, 1, None, 200, 100)}
        sync_institutions(
            self.db_path, client=FakeClient(pages), logical_date="2026-11-17"
        )
        sync_institutions(
            self.db_path, client=FakeClient(pages), logical_date="2026-11-18"
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM institutions").fetchone()[0], 1
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM institution_aliases").fetchone()[0], 3
            )

    def test_works_preserve_multiple_affiliations_and_isolate_doi_conflict(self) -> None:
        authorship = {
            "author": {"id": "https://openalex.org/A1", "display_name": "Author"},
            "author_position": "first",
            "institutions": [
                {"id": "https://openalex.org/I1", "display_name": "One", "country_code": "CN"},
                {"id": "https://openalex.org/I2", "display_name": "Two", "country_code": "US"},
            ],
        }
        works = [
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1/example",
                "title": "First",
                "publication_date": "2026-11-16",
                "authorships": [authorship],
                "topics": [{"id": "https://openalex.org/T1", "display_name": "Topic", "score": 0.9}],
                "primary_topic": {"id": "https://openalex.org/T1"},
            },
            {
                "id": "https://openalex.org/W2",
                "doi": "https://doi.org/10.1/example",
                "title": "Second",
                "publication_date": "2026-11-16",
                "authorships": [],
                "topics": [],
            },
        ]
        result = ingest_works_for_date(
            self.db_path,
            publication_date="2026-11-16",
            client=FakeClient({"*": OpenAlexPage(works, 2, None, 200, 500)}),
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.doi_conflicts, 1)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0], 2)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM work_authorship_institutions").fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM doi_conflicts").fetchone()[0], 1
            )

    def test_validated_no_publish_batch_can_be_published_on_rerun(self) -> None:
        works = [{
            "id": "https://openalex.org/W1",
            "title": "First",
            "publication_date": "2026-11-15",
            "authorships": [],
            "topics": [],
        }]
        pages = {"*": OpenAlexPage(works, 1, None, 200, 100)}
        first = ingest_works_for_date(
            self.db_path,
            publication_date="2026-11-15",
            client=FakeClient(pages),
            publish=False,
            collection_run_id="same-batch",
        )
        self.assertFalse(first.published)
        second = ingest_works_for_date(
            self.db_path,
            publication_date="2026-11-15",
            client=FakeClient(pages),
            publish=True,
            collection_run_id="same-batch",
        )
        self.assertTrue(second.published)
        self.assertEqual(second.request_count, 0)


class OpenAlexClientTests(unittest.TestCase):
    def test_retries_429_and_tracks_quota_without_exposing_key(self) -> None:
        session = FakeSession(
            [
                FakeResponse(429, {"error": "rate limited"}),
                FakeResponse(
                    200,
                    {"results": [{"id": "T1"}], "meta": {"count": 1, "next_cursor": None}},
                ),
            ]
        )
        client = OpenAlexClient(
            "top-secret", session=session, max_retries=1,
            min_interval_seconds=0, sleeper=lambda _: None,
        )
        page = client.get_page("topics", params={}, select_fields=("id",))
        self.assertEqual(len(page.results), 1)
        self.assertEqual(client.stats.request_count, 2)
        self.assertEqual(client.stats.retry_count, 1)
        self.assertEqual(client.stats.rate_limit, 10_000)

    def test_403_raises_permission_error_without_key(self) -> None:
        client = OpenAlexClient(
            "top-secret",
            session=FakeSession([FakeResponse(403, {"error": "upgrade"})]),
            min_interval_seconds=0,
        )
        with self.assertRaises(OpenAlexPermissionError) as context:
            client.get_page("works", params={}, select_fields=("id",))
        self.assertNotIn("top-secret", str(context.exception))


if __name__ == "__main__":
    unittest.main()

