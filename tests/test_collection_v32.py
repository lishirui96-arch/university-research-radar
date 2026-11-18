from __future__ import annotations

import sqlite3
import json
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from collector.daily_collection import WorkerLock, build_collection_windows, run_daily_collection
from collector.database_backup import create_database_backup, restore_database_backup
from collector.openalex_client import OpenAlexPage, RequestStats
from collector.works_ingest import ingest_works_for_date
from storage import initialize_database
from repositories.collection_repository import CollectionRepository


class FakeClient:
    def __init__(self, records: list[dict[str, Any]], total_count: int | None = None) -> None:
        self.records = records
        self.total_count = len(records) if total_count is None else total_count
        self.stats = RequestStats()

    def reset_stats(self) -> None:
        self.stats = RequestStats()

    def iter_cursor(self, endpoint: str, **kwargs: Any) -> Iterator[OpenAlexPage]:
        self.stats.request_count += 1
        self.stats.response_bytes += 100
        self.stats.rate_limit = 10_000
        self.stats.rate_remaining = 9_999
        yield OpenAlexPage(self.records, self.total_count, None, 200, 100)


class DailyFakeClient:
    def __init__(self) -> None:
        self.stats = RequestStats()

    def reset_stats(self) -> None:
        self.stats = RequestStats()

    def _date(self, params: dict[str, Any]) -> str:
        value = str(params.get("filter") or "")
        return value.split("from_publication_date:", 1)[1].split(",", 1)[0]

    def get_page(self, endpoint: str, *, params: dict[str, Any], select_fields: tuple[str, ...]):
        publication_date = self._date(params)
        self.stats.request_count += 1
        self.stats.response_bytes += 10
        self.stats.rate_limit = 10_000
        self.stats.rate_remaining = 9_900
        return OpenAlexPage(
            [{"id": f"https://openalex.org/W{publication_date.replace('-', '')}"}],
            1, None, 200, 10,
        )

    def iter_cursor(self, endpoint: str, *, params: dict[str, Any], **kwargs: Any):
        publication_date = self._date(params)
        self.stats.request_count += 1
        self.stats.response_bytes += 100
        self.stats.rate_limit = 10_000
        self.stats.rate_remaining = 9_899
        record = work(f"W{publication_date.replace('-', '')}")
        record["publication_date"] = publication_date
        yield OpenAlexPage([record], 1, None, 200, 100)


def work(
    work_id: str,
    *,
    title: str = "Work",
    institution_id: str = "https://openalex.org/I1",
    topic_id: str = "https://openalex.org/T1",
    work_type: str = "article",
) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{work_id}",
        "title": title,
        "publication_date": "2026-11-10",
        "type": work_type,
        "updated_date": "2026-11-17T00:00:00Z",
        "authorships": [{
            "author": {"id": "https://openalex.org/A1", "display_name": "Author One"},
            "author_position": "first",
            "institutions": [{
                "id": institution_id,
                "display_name": institution_id.rsplit("/", 1)[-1],
                "country_code": "CN",
            }],
        }],
        "topics": [{"id": topic_id, "display_name": "Topic", "score": 0.9}],
        "primary_topic": {"id": topic_id},
    }


class CollectionV32Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "radar.db"
        initialize_database(self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def ingest(self, records: list[dict[str, Any]], run_id: str, total: int | None = None):
        return ingest_works_for_date(
            self.db,
            publication_date="2026-11-10",
            local_run_date="2026-11-20",
            collection_run_id=run_id,
            client=FakeClient(records, total),
        )

    def test_second_batch_same_date_discovers_new_work(self) -> None:
        first = self.ingest([work("W1")], "run-one")
        second = self.ingest([work("W1"), work("W2", work_type="preprint")], "run-two")
        self.assertNotEqual(first.batch_id, second.batch_id)
        self.assertEqual(second.inserted_works, 1)
        self.assertEqual(second.unchanged_works, 1)
        self.assertEqual(second.count_delta, 1)
        self.assertEqual(second.type_counts, {"article": 1, "preprint": 1})
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM work_date_observations").fetchone()[0], 2)

    def test_same_batch_rerun_is_idempotent(self) -> None:
        first = self.ingest([work("W1")], "same-run")
        second = self.ingest([work("W1")], "same-run")
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual(second.request_count, 0)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM snapshot_batches").fetchone()[0], 1)

    def test_changed_work_updates_and_synchronizes_relationships(self) -> None:
        self.ingest([work("W1")], "run-one")
        changed = work(
            "W1", title="Changed", institution_id="https://openalex.org/I2",
            topic_id="https://openalex.org/T2",
        )
        changed["updated_date"] = "2026-11-18T00:00:00Z"
        result = self.ingest([changed], "run-two")
        self.assertEqual(result.updated_works, 1)
        self.assertEqual(result.institution_relationship_changes, 2)
        self.assertEqual(result.topic_relationship_changes, 2)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT title FROM works").fetchone()[0], "Changed")
            self.assertEqual(
                connection.execute("SELECT institution_id FROM work_authorship_institutions").fetchone()[0],
                "https://openalex.org/I2",
            )
            self.assertEqual(
                connection.execute("SELECT topic_key FROM work_topics").fetchone()[0],
                "openalex:T2",
            )

    def test_unchanged_records_are_not_rewritten(self) -> None:
        self.ingest([work("W1")], "run-one")
        with closing(sqlite3.connect(self.db)) as connection:
            before = connection.execute("SELECT last_updated_at FROM works").fetchone()[0]
        result = self.ingest([work("W1")], "run-two")
        with closing(sqlite3.connect(self.db)) as connection:
            after = connection.execute("SELECT last_updated_at FROM works").fetchone()[0]
        self.assertEqual(result.unchanged_works, 1)
        self.assertEqual(result.updated_works, 0)
        self.assertEqual(before, after)

    def test_three_equal_observations_mark_date_stable(self) -> None:
        self.ingest([work("W1")], "run-one")
        self.ingest([work("W1")], "run-two")
        third = self.ingest([work("W1")], "run-three")
        self.assertEqual(third.stability_status, "stable")

    def test_count_decrease_is_recorded_without_deleting_history(self) -> None:
        self.ingest([work("W1"), work("W2")], "run-one")
        second = self.ingest([work("W1")], "run-two")
        self.assertEqual(second.count_delta, -1)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0], 2)

    def test_monday_and_missed_run_add_catchup_dates(self) -> None:
        windows = build_collection_windows(
            date(2026, 11, 23), last_successful_run_date=date(2026, 11, 20)
        )
        by_date = {item.publication_date: item for item in windows}
        self.assertIn("catch-up", by_date["2026-11-21"].reasons)
        self.assertIn("catch-up", by_date["2026-11-22"].reasons)
        self.assertEqual(by_date["2026-11-22"].priority, 10)
        self.assertLessEqual(len(windows), 7)

    def test_daily_orchestrator_runs_all_standard_windows_and_writes_report(self) -> None:
        report_dir = Path(self.temp.name) / "reports"
        backup_dir = Path(self.temp.name) / "backups"
        result = run_daily_collection(
            self.db,
            run_date=date(2026, 11, 17),
            trigger_kind="test",
            report_dir=report_dir,
            backup_dir=backup_dir,
            client_factory=DailyFakeClient,
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.windows), 5)
        self.assertEqual({item["publication_date"] for item in result.windows}, {
            "2026-11-16", "2026-11-15", "2026-11-14", "2026-11-10", "2026-11-03",
        })
        self.assertTrue(Path(result.report_json).is_file())
        self.assertTrue(Path(result.report_markdown).is_file())
        report_payload = json.loads(Path(result.report_json).read_text(encoding="utf-8"))
        self.assertTrue(report_payload["started_at"])
        self.assertTrue(report_payload["completed_at"])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM daily_collection_windows WHERE status='succeeded'"
            ).fetchone()[0], 5)

    def test_budget_limit_skips_ingest_and_marks_run_partial(self) -> None:
        result = run_daily_collection(
            self.db,
            run_date=date(2026, 11, 17),
            trigger_kind="test",
            request_budget=0,
            report_dir=Path(self.temp.name) / "reports",
            backup_dir=Path(self.temp.name) / "backups",
            client_factory=DailyFakeClient,
        )
        self.assertEqual(result.status, "partial")
        self.assertTrue(all(item["status"] == "skipped" for item in result.windows))
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM works").fetchone()[0], 0)

    def test_failed_second_batch_does_not_replace_published_snapshot(self) -> None:
        first = self.ingest([work("W1")], "run-one")
        with self.assertRaises(RuntimeError):
            self.ingest([work("W1")], "run-two", total=2)
        with closing(sqlite3.connect(self.db)) as connection:
            published_batch = connection.execute(
                "SELECT batch_id FROM published_snapshots WHERE snapshot_type='daily_ingest:2026-11-10'"
            ).fetchone()[0]
        self.assertEqual(published_batch, first.batch_id)

    def test_backup_and_safe_restore(self) -> None:
        backup_dir = Path(self.temp.name) / "backups"
        result = create_database_backup(self.db, backup_dir)
        restored = Path(self.temp.name) / "restored.db"
        restore_database_backup(str(result["daily"]), restored)
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with self.assertRaises(FileExistsError):
            restore_database_backup(str(result["daily"]), restored)

    def test_worker_lock_rejects_concurrent_start(self) -> None:
        lock_path = Path(self.temp.name) / "worker.lock"
        with WorkerLock(lock_path):
            with self.assertRaises(RuntimeError):
                with WorkerLock(lock_path):
                    pass

    def test_work_type_statistics_exposes_raw_and_grouped_counts(self) -> None:
        self.ingest(
            [work("W1", work_type="article"), work("W2", work_type="review"),
             work("W3", work_type="conference-paper")],
            "type-run",
        )
        stats = CollectionRepository(self.db).work_type_statistics("2026-11-10")
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats["raw_types"]["article"], 1)
        self.assertEqual(stats["raw_types"]["review"], 1)
        self.assertEqual(stats["normalized_groups"]["article_review"], 2)
        self.assertEqual(stats["normalized_groups"]["conference_paper"], 1)


if __name__ == "__main__":
    unittest.main()
