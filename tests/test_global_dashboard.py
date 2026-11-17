from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard_repository import load_dashboard_data, load_database_status
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
        self.assertEqual(str(status["schema_version"]), "2")


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
