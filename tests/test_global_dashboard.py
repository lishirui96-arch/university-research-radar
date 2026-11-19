from __future__ import annotations

import gc
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pyarrow.ipc as pa_ipc
import pandas as pd
from streamlit.testing.v1 import AppTest

from collector.topic_hotspots import import_audit_files
from collector.v14_taxonomy import (
    EXPECTED_FIELD_COUNTS,
    VERIFIED_TOPIC_NAMES_ZH,
    import_taxonomy,
)
from dashboard_repository import (
    get_v14_hotspot_dashboard,
    get_topic_daily_trends,
    get_topic_hotspot_ranking,
    load_dashboard_data,
    load_database_status,
)
from research_taxonomy import load_research_taxonomy
from storage import initialize_database
from topic_translations import load_topic_translation_catalog


TREND_CATEGORIES = (
    "robotics_embodied",
    "ai_chip_packaging",
    "new_energy_storage",
    "advanced_materials",
    "bio_manufacturing",
)
TREND_LABELS = (
    "人形机器人与具身智能",
    "AI芯片与先进封装",
    "新能源与储能",
    "新材料",
    "生物制造",
)
TREND_LATEST_VALUES = (418, 361, 3455, 1983, 710)

FIELD_CHART_TOPIC_IDS = {
    "15": {
        "T10104", "T10967", "T10495", "T10117", "T12112", "T11009",
        "T11401", "T11362", "T11208", "T12074",
    },
    "16": {
        "T10212", "T10096", "T10640", "T10701", "T10532", "T10180",
        "T10274", "T11460", "T10480", "T10578",
    },
    "17": {
        "T10036", "T10883", "T10052", "T10862", "T11714", "T10400",
        "T10764", "T10028", "T10775", "T10719", "T10689", "T10270",
        "T10682",
    },
    "21": {
        "T10030", "T10078", "T10088", "T11784", "T11007", "T10284",
        "T10024", "T12008", "T10491", "T10680",
    },
    "22": {
        "T10018", "T10247", "T10281", "T10033", "T10338", "T11690",
        "T10220", "T10663", "T10705", "T10161", "T10121",
    },
    "25": {
        "T10063", "T10179", "T10275", "T11948", "T10079", "T10343",
        "T11091", "T10488", "T10245", "T11224",
    },
}


def _seed_complete_trend(db_path: Path) -> None:
    end = date(2026, 11, 18)
    start = end - timedelta(days=364)
    dates = [start + timedelta(days=offset) for offset in range(365)]
    now = "2026-11-18T05:03:53+00:00"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO trend_backfill_runs(
                run_id, run_type, start_snapshot_date, end_snapshot_date,
                snapshot_dates, expected_query_count, completed_query_count,
                successful_query_count, failed_query_count, status,
                topic_mapping_version, query_version, calculation_version,
                revision_reason, started_at, completed_at, updated_at, data_origin
            ) VALUES (?, 'backfill', ?, ?, ?, 1825, 1825, 1825, 0, 'success',
                      'v1', 'trend-openalex-primary-topic-core-v1',
                      'rolling-30d-direct-count-v1', NULL, ?, ?, ?,
                      'historical_backfill')
            """,
            (
                "ui-test-trend",
                start.isoformat(),
                end.isoformat(),
                json.dumps([item.isoformat() for item in dates]),
                now,
                now,
                now,
            ),
        )
        rows = []
        for snapshot_date in dates:
            day_offset = (end - snapshot_date).days
            for category_id, latest_value in zip(
                TREND_CATEGORIES, TREND_LATEST_VALUES
            ):
                rows.append(
                    (
                        "ui-test-trend",
                        category_id,
                        snapshot_date.isoformat(),
                        (snapshot_date - timedelta(days=29)).isoformat(),
                        snapshot_date.isoformat(),
                        latest_value + day_offset,
                        now,
                        now,
                        now,
                    )
                )
        connection.executemany(
            """
            INSERT INTO trend_30d_snapshots(
                run_id, category_id, snapshot_date, window_start, window_end,
                works_count, query_as_of, data_status, topic_mapping_version,
                query_version, calculation_version, revision_no, is_current,
                supersedes_id, revision_reason, created_at, updated_at, data_origin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'success', 'v1',
                      'trend-openalex-primary-topic-core-v1',
                      'rolling-30d-direct-count-v1', 1, 1, NULL, NULL, ?, ?,
                      'historical_backfill')
            """,
            rows,
        )


def _chart_dataframe(app: AppTest):
    chart = app.get("vega_lite_chart")[0]
    arrow_bytes = chart.proto.datasets[0].data.data
    return pa_ipc.open_stream(io.BytesIO(arrow_bytes)).read_pandas()


def _seed_v14_taxonomy(root: Path, db_path: Path) -> None:
    ranking = pd.read_csv(root / "TOPIC_RANKING_90D.csv", dtype={"topic_id": "string"})
    by_id = ranking.set_index("topic_id")
    priority = {
        "15": [],
        "16": [],
        "17": ["T10036"],
        "21": ["T10030", "T10078"],
        "22": ["T10018", "T10247", "T10281", "T10033", "T10338"],
        "25": ["T10063", "T10179"],
    }
    used = {topic_id for values in priority.values() for topic_id in values}
    candidates = [
        topic_id for topic_id in ranking.sort_values("rank", ascending=False)["topic_id"]
        if topic_id not in used
    ]
    rows = []
    cursor = 0
    field_names = {
        "15": "Chemical Engineering", "16": "Chemistry",
        "17": "Computer Science", "21": "Energy",
        "22": "Engineering", "25": "Materials Science",
    }
    for field_id, expected_count in EXPECTED_FIELD_COUNTS.items():
        topic_ids = list(priority[field_id])
        needed = expected_count - len(topic_ids)
        topic_ids.extend(candidates[cursor:cursor + needed])
        cursor += needed
        for topic_id in topic_ids:
            source = by_id.loc[topic_id]
            rows.append(
                {
                    "topic_id": str(topic_id),
                    "topic_name": str(source["topic_name"]),
                    "subfield_id": f"{field_id}01",
                    "subfield_name": f"Test {field_names[field_id]} Subfield",
                    "field_id": field_id,
                    "field_name": field_names[field_id],
                    "domain_id": "3",
                    "domain_name": "Physical Sciences",
                }
            )
    import_taxonomy(db_path, rows)


class DashboardRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
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

    def test_field_chart_topics_have_chinese_names_with_review_status(self) -> None:
        expected = set().union(*FIELD_CHART_TOPIC_IDS.values())
        catalog = load_topic_translation_catalog()
        self.assertTrue(expected.issubset(catalog))
        for topic_id in expected:
            record = catalog[topic_id]
            label = record["topic_name_zh"]
            self.assertTrue(label.strip())
            self.assertTrue(any("\u4e00" <= char <= "\u9fff" for char in label))
            self.assertIn(record["translation_status"], {"verified", "candidate"})

    def test_database_status_is_read_only_and_reports_integrity(self) -> None:
        before = self.db_path.stat().st_mtime_ns
        status = load_database_status(self.db_path)
        after = self.db_path.stat().st_mtime_ns
        self.assertEqual(before, after)
        self.assertEqual(status["integrity"], "ok")
        self.assertEqual(status["foreign_key_violations"], 0)
        self.assertEqual(str(status["schema_version"]), "6")

    def test_topic_audit_import_is_complete_and_idempotent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        first = import_audit_files(root, self.db_path)
        second = import_audit_files(root, self.db_path)
        self.assertEqual(first["topics"], 4516)
        self.assertEqual(first["ranking_rows"], 9032)
        self.assertEqual(first["daily_rows"], 3780)
        self.assertEqual(second["daily_rows"], 3780)
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM openalex_topics").fetchone()[0], 4516)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM topic_ranking_snapshots").fetchone()[0], 9032)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM topic_daily_counts").fetchone()[0], 3780)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_topic_repository_uses_each_periods_own_top_ten(self) -> None:
        root = Path(__file__).resolve().parents[1]
        import_audit_files(root, self.db_path)
        expected = {90: (900, "T10172"), 360: (3600, "T10134")}
        for period, (rows, period_specific_topic) in expected.items():
            ranking = get_topic_hotspot_ranking(self.db_path, period)
            daily = get_topic_daily_trends(self.db_path, period)
            self.assertEqual(ranking["status"], "complete")
            self.assertEqual(daily["status"], "complete")
            self.assertEqual(len(ranking["data"]), 10)
            self.assertEqual(len(daily["data"]), rows)
            self.assertIn(period_specific_topic, set(ranking["data"]["topic_id"]))
            sums = daily["data"].groupby("topic_id")["daily_works_count"].sum()
            totals = ranking["data"].set_index("topic_id")["period_works_count"]
            self.assertEqual(sums.sort_index().to_dict(), totals.sort_index().to_dict())

    def test_v14_repository_filters_scope_and_preserves_missing_daily_values(self) -> None:
        root = Path(__file__).resolve().parents[1]
        import_audit_files(root, self.db_path)
        _seed_v14_taxonomy(root, self.db_path)
        result = get_v14_hotspot_dashboard(self.db_path, period_days=90)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["all_topics"]), 1063)
        self.assertEqual(result["metrics"]["covered_fields"], 6)
        self.assertEqual(result["ranking"].iloc[0]["topic_id"], "T10030")
        self.assertEqual(result["ranking"].iloc[0]["period_works_count"], 3641)
        self.assertTrue(result["ranking"]["topic_name_zh"].notna().all())
        self.assertTrue(
            set(result["ranking"]["topic_id"]).issubset(VERIFIED_TOPIC_NAMES_ZH)
        )
        self.assertEqual(result["integrity"]["available_daily_rows_360"], 1440)
        self.assertFalse(result["integrity"]["missing_is_zero_filled"])
        self.assertEqual(result["trend"]["date"].nunique(), 13)
        self.assertTrue(result["trend"]["growth_rate"].notna().any())

        growth = get_v14_hotspot_dashboard(
            self.db_path, period_days=90, sort_by="growth"
        )
        self.assertTrue(growth["growth_sort_available"])
        self.assertFalse(growth["ranking"].empty)
        rates = growth["ranking"]["period_growth_rate"].tolist()
        self.assertEqual(rates, sorted(rates, reverse=True))


class DashboardPageTests(unittest.TestCase):
    def test_default_navigation_page_renders_without_remote_data(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "dashboard-test.db"
            with patch.dict("os.environ", {"RADAR_DB_PATH": str(db_path)}):
                app = AppTest.from_file(root / "streamlit_app.py", default_timeout=15)
                app.run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(app.get("vega_lite_chart")), 0)
                self.assertTrue(any("V1.4" in item.value for item in app.error))
                hero_html = "\n".join(element.proto.body for element in app.get("html"))
                self.assertIn("radar-hero-copy", hero_html)

    def test_topic_hotspot_switches_90_and_360_days(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "trend-ui-test.db"
            initialize_database(db_path)
            import_audit_files(root, db_path)
            _seed_v14_taxonomy(root, db_path)
            with patch.dict("os.environ", {"RADAR_DB_PATH": str(db_path)}):
                app = AppTest.from_file(root / "streamlit_app.py", default_timeout=30)
                app.run()
                self.assertEqual(len(app.exception), 0)
                ninety = _chart_dataframe(app)
                self.assertEqual(len(ninety), 52)
                self.assertEqual(ninety["date"].nunique(), 13)
                self.assertEqual(ninety["topic_id"].nunique(), 4)
                self.assertEqual(sorted(ninety["period_days"].unique()), [6, 7])
                self.assertTrue(
                    ninety["topic_label"].map(
                        lambda label: any("\u4e00" <= char <= "\u9fff" for char in label)
                    ).all()
                )

                app.segmented_control(key="v14_period").set_value("近360天").run()
                self.assertEqual(len(app.exception), 0)
                year = _chart_dataframe(app)
                self.assertEqual(len(year), 52)
                self.assertEqual(year["date"].nunique(), 13)
                self.assertEqual(year["topic_id"].nunique(), 4)
                self.assertEqual(year.iloc[-1]["period_days"], 18)

                app.segmented_control(key="v14_period").set_value("近90天").run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(len(_chart_dataframe(app)), 52)
                del app
                gc.collect()

    def test_incomplete_trend_does_not_render_missing_values_as_zero(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            db_path = Path(temp) / "trend-ui-partial.db"
            initialize_database(db_path)
            import_audit_files(root, db_path)
            _seed_v14_taxonomy(root, db_path)
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    DELETE FROM topic_daily_counts
                    WHERE topic_id='T10030' AND date='2026-11-18'
                    """
                )
            with patch.dict("os.environ", {"RADAR_DB_PATH": str(db_path)}):
                app = AppTest.from_file(root / "streamlit_app.py", default_timeout=30)
                app.run()
                self.assertEqual(len(app.exception), 0)
                chart = _chart_dataframe(app)
                missing = chart[(chart["topic_id"] == "T10030") & (chart["period_end"] == pd.Timestamp("2026-11-18"))]
                self.assertEqual(len(missing), 1)
                self.assertTrue(missing["period_works_count"].isna().all())
                self.assertEqual(missing.iloc[0]["query_status"], "missing")
                del app
                gc.collect()


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
