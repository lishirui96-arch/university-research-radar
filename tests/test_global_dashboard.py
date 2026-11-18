from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from dashboard_repository import (
    load_daily_collection_data,
    load_dashboard_data,
    load_database_status,
)
from repositories.collection_repository import CollectionRepository
from research_taxonomy import load_research_taxonomy
from storage import initialize_database


class DashboardRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "radar.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_empty_database_keeps_global_metrics_unavailable(self) -> None:
        result = load_dashboard_data(self.db_path)
        self.assertTrue(result["database_available"])
        self.assertEqual(result["coverage_status"], "unavailable")
        self.assertTrue(result["trend"].empty)
        self.assertTrue(result["topics"].empty)
        self.assertTrue(result["global_institutions"].empty)
        self.assertTrue(result["works"].empty)
        for metric in result["kpis"].values():
            self.assertIsNone(metric["value"])
            self.assertEqual(metric["scope"], "unavailable")

    def test_database_status_is_read_only_and_reports_integrity(self) -> None:
        before = self.db_path.stat().st_mtime_ns
        status = load_database_status(self.db_path)
        after = self.db_path.stat().st_mtime_ns
        self.assertEqual(before, after)
        self.assertEqual(status["integrity"], "ok")
        self.assertEqual(status["foreign_key_violations"], 0)
        self.assertEqual(str(status["schema_version"]), "5")

    def test_daily_collection_status_reads_latest_run(self) -> None:
        repository = CollectionRepository(self.db_path)
        repository.create_daily_run(
            run_id="daily-test",
            run_date="2026-11-18",
            timezone_name="Singapore Standard Time",
            trigger_kind="test",
            scheduled_for="2026-11-18T09:00:00",
            request_budget=9000,
            backup_path="ignored-test-backup.db",
        )
        repository.finish_daily_run(
            run_id="daily-test",
            status="succeeded",
            window_count=5,
            completed_windows=5,
            failed_windows=0,
            request_count=12,
            response_bytes=1024,
            retry_count=1,
            rate_remaining=9988,
            report_path="ignored-test-report.json",
        )
        result = load_daily_collection_data(self.db_path)
        self.assertTrue(result["available"])
        self.assertEqual(result["latest_run"]["run_id"], "daily-test")
        self.assertEqual(result["latest_run"]["request_count"], 12)
        self.assertTrue(result["observations"].empty)


class DashboardPageTests(unittest.TestCase):
    def test_default_navigation_page_renders_without_remote_data(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(root / "streamlit_app.py", default_timeout=15)
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertGreaterEqual(len(app.metric), 4)
        self.assertTrue(any(metric.value == "--" for metric in app.metric))
        self.assertGreaterEqual(len(app.button), 3)
        hero_html = "\n".join(element.value for element in app.get("html"))
        self.assertIn("radar-hero-copy", hero_html)

    def test_daily_updates_page_renders_without_collection_runs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "radar.db"
            initialize_database(db_path)
            with patch.dict(os.environ, {"RADAR_DB_PATH": str(db_path)}):
                app = AppTest.from_file(
                    root / "app_pages" / "daily_updates.py", default_timeout=15
                )
                app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertGreaterEqual(len(app.metric), 5)
        self.assertTrue(any("尚未运行" in str(metric.value) for metric in app.metric))


class ResearchTaxonomyTests(unittest.TestCase):
    def test_taxonomy_has_three_complete_levels_and_unique_ids(self) -> None:
        taxonomy = load_research_taxonomy()
        self.assertGreaterEqual(len(taxonomy["domains"]), 6)
        ids: list[str] = []
        for domain in taxonomy["domains"]:
            ids.append(domain["id"])
            self.assertTrue(domain["directions"])
            for direction in domain["directions"]:
                ids.append(direction["id"])
                self.assertTrue(direction["technologies"])
                ids.extend(item["id"] for item in direction["technologies"])
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
