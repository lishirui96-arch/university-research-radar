from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from collector.trend_analytics import (
    CALCULATION_VERSION,
    CORE_CORPUS_FILTER,
    QUERY_VERSION,
    QueryOutcome,
    QueryTask,
    build_query_filter,
    execute_backfill,
    load_categories,
    rolling_window,
)
from dashboard_repository import get_global_research_trend
from storage import initialize_database


class FakeClient:
    def __init__(self, *, failed_category: str | None = None, revision: bool = False) -> None:
        self.failed_category = failed_category
        self.revision = revision
        self.calls = 0

    def query_count(self, task):
        self.calls += 1
        query_filter = build_query_filter(task)
        if task.category.category_id == self.failed_category:
            return QueryOutcome(
                "failed", 503, None, "2026-11-18T00:00:00+00:00", 10.0, 2,
                "service unavailable", 1000, 997, "1", query_filter,
            )
        base = 100 + list(load_category_ids()).index(task.category.category_id) * 10
        if self.revision and task.category.category_id == "robotics_embodied":
            base += 1
        return QueryOutcome(
            "success", 200, base, "2026-11-18T00:00:00+00:00", 5.0, 0,
            None, 1000, 999, "1", query_filter,
        )


def load_category_ids() -> tuple[str, ...]:
    return (
        "robotics_embodied",
        "ai_chip_packaging",
        "new_energy_storage",
        "advanced_materials",
        "bio_manufacturing",
    )


class TrendAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "radar.db"
        self.root = Path(__file__).resolve().parents[1]
        self.mapping_path = self.root / "config" / "trend_topic_mapping.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_latest_migration_is_idempotent_and_additive(self) -> None:
        initialize_database(self.db_path)
        initialize_database(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM schema_metadata WHERE key='schema_version'"
                ).fetchone()[0],
                "9",
            )
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertTrue(
                {
                    "trend_backfill_runs",
                    "trend_query_logs",
                    "trend_30d_snapshots",
                    "openalex_topics",
                    "topic_daily_counts",
                    "topic_ranking_snapshots",
                }.issubset(tables)
            )
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            for table in (
                "trend_backfill_runs",
                "trend_query_logs",
                "trend_30d_snapshots",
            ):
                columns = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                self.assertIn("data_origin", columns)

    def test_mapping_and_window_enforce_the_fixed_contract(self) -> None:
        categories = load_categories(self.mapping_path)
        self.assertEqual(len(categories), 5)
        self.assertTrue(all(category.topic_ids for category in categories))
        start, end = rolling_window(date(2026, 11, 18))
        self.assertEqual(start, date(2026, 10, 20))
        self.assertEqual(end, date(2026, 11, 18))
        task_filter = build_query_filter(
            QueryTask(categories[0], date(2026, 11, 18), start, end)
        )
        self.assertIn(CORE_CORPUS_FILTER, task_filter)
        self.assertNotIn(",is_core:true", task_filter)
        self.assertIn("primary_topic.id:T10879|T10653|T10462", task_filter)

    def test_incomplete_run_logs_failure_but_publishes_no_snapshots(self) -> None:
        client = FakeClient(failed_category="ai_chip_packaging")
        summary = execute_backfill(
            db_path=self.db_path,
            mapping_path=self.mapping_path,
            snapshot_dates=[date(2026, 11, 18)],
            run_id="failed-run",
            run_type="backfill",
            revision_reason=None,
            batch_size=None,
            client=client,
        )
        self.assertEqual(summary["status"], "partial")
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trend_30d_snapshots").fetchone()[0], 0)
            failed = connection.execute(
                "SELECT works_count, error_message, data_origin FROM trend_query_logs WHERE request_status='failed'"
            ).fetchone()
            self.assertIsNone(failed[0])
            self.assertIn("unavailable", failed[1])
            self.assertEqual(failed[2], "historical_backfill")

    def test_batch_resume_skips_successful_queries_and_publishes_atomically(self) -> None:
        client = FakeClient()
        first = execute_backfill(
            db_path=self.db_path,
            mapping_path=self.mapping_path,
            snapshot_dates=[date(2026, 11, 18)],
            run_id="resume-run",
            run_type="backfill",
            revision_reason=None,
            batch_size=2,
            client=client,
        )
        self.assertEqual(first["status"], "paused")
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trend_30d_snapshots").fetchone()[0], 0)

        second = execute_backfill(
            db_path=self.db_path,
            mapping_path=self.mapping_path,
            snapshot_dates=[date(2026, 11, 18)],
            run_id="resume-run",
            run_type="backfill",
            revision_reason=None,
            batch_size=None,
            client=client,
        )
        self.assertEqual(second["status"], "success")
        self.assertEqual(client.calls, 5)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trend_query_logs").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trend_30d_snapshots").fetchone()[0], 5)

            completed_at = connection.execute(
                "SELECT completed_at FROM trend_backfill_runs WHERE run_id='resume-run'"
            ).fetchone()[0]

        execute_backfill(
            db_path=self.db_path,
            mapping_path=self.mapping_path,
            snapshot_dates=[date(2026, 11, 18)],
            run_id="resume-run",
            run_type="backfill",
            revision_reason=None,
            batch_size=None,
            client=client,
        )
        self.assertEqual(client.calls, 5)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT completed_at FROM trend_backfill_runs WHERE run_id='resume-run'"
                ).fetchone()[0],
                completed_at,
            )

    def test_idempotence_and_revision_history(self) -> None:
        common = {
            "db_path": self.db_path,
            "mapping_path": self.mapping_path,
            "snapshot_dates": [date(2026, 11, 18)],
            "batch_size": None,
        }
        execute_backfill(
            **common, run_id="initial", run_type="backfill",
            revision_reason=None, client=FakeClient()
        )
        execute_backfill(
            **common, run_id="same", run_type="revision",
            revision_reason="idempotence check", client=FakeClient()
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trend_30d_snapshots").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trend_query_logs").fetchone()[0], 10)

        execute_backfill(
            **common, run_id="changed", run_type="revision",
            revision_reason="OpenAlex backfill", client=FakeClient(revision=True)
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                """
                SELECT works_count, revision_no, is_current, revision_reason
                FROM trend_30d_snapshots
                WHERE category_id='robotics_embodied'
                ORDER BY revision_no
                """
            ).fetchall()
            self.assertEqual(rows, [(100, 1, 0, None), (101, 2, 1, "OpenAlex backfill")])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trend_30d_snapshots").fetchone()[0], 6)
            self.assertEqual(rows[-1][3], "OpenAlex backfill")

            origins = connection.execute(
                "SELECT DISTINCT data_origin FROM trend_query_logs WHERE run_id='changed'"
            ).fetchall()
            self.assertEqual(origins, [("historical_revision",)])

    def test_30_day_reader_reports_complete_integrity(self) -> None:
        end = date(2026, 11, 18)
        dates = [end - timedelta(days=offset) for offset in range(29, -1, -1)]
        execute_backfill(
            db_path=self.db_path,
            mapping_path=self.mapping_path,
            snapshot_dates=dates,
            run_id="thirty-days",
            run_type="backfill",
            revision_reason=None,
            batch_size=None,
            client=FakeClient(),
        )
        result = get_global_research_trend(self.db_path, days=30)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["data"]), 30)
        self.assertEqual(result["integrity"]["complete_days"], 30)
        self.assertEqual(result["integrity"]["missing_days"], 0)
        self.assertEqual(result["integrity"]["query_versions"], [QUERY_VERSION])
        self.assertEqual(
            result["integrity"]["calculation_versions"], [CALCULATION_VERSION]
        )
        self.assertTrue((result["data"]["data_status"] == "complete").all())


if __name__ == "__main__":
    unittest.main()
