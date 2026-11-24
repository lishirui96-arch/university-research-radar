from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import pandas as pd

from citation_rankings import aggregate_windowed_citations, publish_citation_snapshot
from collector.citation_v16 import (
    TopicCitationResult,
    collect_and_publish_view,
    collect_topic_citations,
)
from dashboard_repository import get_citation_ranking
from storage import initialize_database


class CitationAggregationTests(unittest.TestCase):
    def test_counts_distinct_edges_by_citing_publication_date(self) -> None:
        edges = pd.DataFrame([
            ("C1", "W-old", "2026-11-18"),
            ("C1", "W-old", "2026-11-18"),
            ("C2", "W-old", "2026-08-20"),
            ("C3", "W-old", "2025-11-24"),
            ("C4", "W-new", "2026-11-19"),
        ], columns=["citing_work_id", "cited_work_id", "citing_publication_date"])
        works = pd.DataFrame([
            ("W-old", "T1", "17", "Old paper", "2023-03-01"),
            ("W-new", "T1", "17", "Future citation", "2024-03-01"),
        ], columns=["openalex_work_id", "topic_id", "field_id", "title", "publication_date"])
        result = aggregate_windowed_citations(edges, works, window_end=date(2026, 11, 18))
        self.assertEqual(result["openalex_work_id"].tolist(), ["W-old"])
        self.assertEqual(int(result.iloc[0]["cited_in_90d"]), 1)
        self.assertEqual(int(result.iloc[0]["cited_in_360d"]), 3)
        self.assertEqual(result.iloc[0]["publication_date"], "2023-03-01")


class CitationPublishingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.temp.name) / "citations.db"
        initialize_database(self.db)
        with __import__("sqlite3").connect(self.db) as connection:
            connection.execute(
                """
                INSERT INTO taxonomy_versions(
                    taxonomy_version, effective_date, source, topic_count,
                    field_count, is_current, imported_at
                ) VALUES ('tax-v1', '2026-01-01', 'test', 2, 1, 1, '2026-01-01')
                """
            )
            for topic_id in ("T1", "T2"):
                connection.execute(
                    """
                    INSERT INTO openalex_topics(
                        topic_id, topic_name, topic_name_zh, subfield_id,
                        subfield_name, field_id, field_name, domain_id,
                        domain_name, taxonomy_version, updated_at
                    ) VALUES (?, ?, ?, 'S1', 'Subfield', '17', 'Computer Science',
                              'D1', 'Domain', 'tax-v1', '2026-01-01')
                    """,
                    (topic_id, topic_id, topic_id),
                )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_published_batch_is_aligned_sorted_and_distinguishes_empty_scope(self) -> None:
        rows = pd.DataFrame([
            {
                "region_code": "GLOBAL", "topic_id": "T1", "field_id": "17",
                "openalex_work_id": "W2", "title": "Second", "doi": None,
                "openalex_url": "https://openalex.org/W2", "venue": "Journal",
                "publication_date": "2024-01-01", "window_citation_count": 3,
            },
            {
                "region_code": "GLOBAL", "topic_id": "T1", "field_id": "17",
                "openalex_work_id": "W1", "title": "First", "doi": "https://doi.org/10/x",
                "openalex_url": "https://openalex.org/W1", "venue": "Journal",
                "publication_date": "2025-01-01", "window_citation_count": 3,
            },
        ])
        publish_citation_snapshot(
            self.db, batch_id="batch-1", ranking_date=date(2026, 11, 18), period_days=90,
            taxonomy_version="tax-v1", rows=rows,
            query_as_of="2026-11-18T12:00:00+00:00", expected_scope_count=2,
            citing_work_count=10, citation_edge_count=15, api_request_count=4,
            completed_scopes=[("GLOBAL", "T1"), ("GLOBAL", "T2")],
        )
        ranked = get_citation_ranking(
            self.db, region_code="GLOBAL", period_days=90, topic_id="T1",
            window_start="2026-08-21", window_end="2026-11-18",
        )
        self.assertEqual(ranked["status"], "available")
        self.assertEqual(ranked["works"]["openalex_work_id"].tolist(), ["W1", "W2"])
        empty = get_citation_ranking(
            self.db, region_code="GLOBAL", period_days=90, topic_id="T2",
            window_start="2026-08-21", window_end="2026-11-18",
        )
        self.assertEqual(empty["status"], "available")
        self.assertTrue(empty["works"].empty)
        unavailable = get_citation_ranking(
            self.db, region_code="CN", period_days=90, topic_id="T1",
            window_start="2026-08-21", window_end="2026-11-18",
        )
        self.assertEqual(unavailable["status"], "unavailable")

    def test_incomplete_scope_set_cannot_publish(self) -> None:
        empty_rows = pd.DataFrame(columns=[
            "region_code", "topic_id", "field_id", "openalex_work_id", "title",
            "publication_date", "window_citation_count",
        ])
        with self.assertRaisesRegex(ValueError, "incomplete citation batch"):
            publish_citation_snapshot(
                self.db, batch_id="partial", ranking_date=date(2026, 11, 18), period_days=90,
                taxonomy_version="tax-v1", rows=empty_rows, query_as_of="now",
                expected_scope_count=2, citing_work_count=0, citation_edge_count=0,
                api_request_count=0, completed_scopes=[("GLOBAL", "T1")],
            )


class CitationCollectionTests(unittest.TestCase):
    def test_stops_only_when_remaining_cumulative_bound_is_below_tenth(self) -> None:
        class FakeClient:
            request_count = 0

            def candidate_page(
                self, topic_id: str, cursor: str, region_code: str = "GLOBAL"
            ):
                self.request_count += 1
                results = []
                for index in range(12):
                    cumulative = 100 - index if index < 10 else 5
                    results.append({
                        "id": f"https://openalex.org/W{index:02d}",
                        "doi": None,
                        "display_name": f"Paper {index}",
                        "publication_date": f"202{index % 6}-01-01",
                        "type": "article",
                        "cited_by_count": cumulative,
                        "primary_location": {"source": {"display_name": "Journal"}},
                    })
                return {"meta": {"count": 12, "next_cursor": None}, "results": results}

            def grouped_window_counts(self, work_ids, window_start, window_end):
                self.request_count += 1
                return {
                    work_id: max(0, 20 - int(work_id[1:])) for work_id in work_ids
                }, 0

            def exact_window_count(self, work_id, window_start, window_end):
                raise AssertionError("all fake candidates have exact grouped counts")

        result = collect_topic_citations(
            FakeClient(), topic_id="T1", topic_name="Topic", field_id="17",
            window_start=date(2026, 8, 21), window_end=date(2026, 11, 18),
        )
        self.assertEqual(result.candidates_scanned, 12)
        self.assertEqual(result.tenth_citation_count, 11)
        self.assertEqual(result.stop_cumulative_upper_bound, 5)
        self.assertEqual(result.rows[0]["openalex_work_id"], "W00")

    def test_view_collection_caches_successes_before_reporting_peer_failure(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            database = Path(temp_dir) / "citations.db"
            initialize_database(database)
            dashboard = {
                "status": "available",
                "ranking": pd.DataFrame([
                    {
                        "topic_id": "T1", "topic_name": "One", "field_id": "17",
                        "window_start": "2026-08-21", "window_end": "2026-11-18",
                    },
                    {
                        "topic_id": "T2", "topic_name": "Two", "field_id": "17",
                        "window_start": "2026-08-21", "window_end": "2026-11-18",
                    },
                ]),
            }
            successful = TopicCitationResult(
                topic_id="T1", topic_name="One", candidate_count=10,
                candidates_scanned=10, api_request_count=2,
                stop_cumulative_upper_bound=0, tenth_citation_count=1,
                rows=[],
            )

            def collect(_client, *, topic_id, **_kwargs):
                if topic_id == "T2":
                    raise RuntimeError("quota exhausted")
                return successful

            with mock.patch(
                "collector.citation_v16.get_v14_hotspot_dashboard",
                return_value=dashboard,
            ), mock.patch(
                "collector.citation_v16.collect_topic_citations", side_effect=collect,
            ):
                with self.assertRaisesRegex(RuntimeError, "T2"):
                    collect_and_publish_view(
                        database, region_code="GLOBAL", period_days=90,
                        api_key="test-key",
                    )

            with __import__("sqlite3").connect(database) as connection:
                cached = connection.execute(
                    "SELECT topic_id FROM citation_topic_cache"
                ).fetchall()
            self.assertEqual(cached, [("T1",)])


if __name__ == "__main__":
    unittest.main()
