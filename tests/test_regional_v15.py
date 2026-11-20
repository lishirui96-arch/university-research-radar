from __future__ import annotations

from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import requests

from collector.regional_v15 import (
    RegionalOpenAlexClient,
    _sanitize_error,
    build_period_records,
    region_query_filter,
    validate_region,
)
from collector.v14_taxonomy import TAXONOMY_VERSION
from storage import initialize_database


class RegionalQueryContractTests(unittest.TestCase):
    def test_transport_error_is_retried_and_redacted_before_escape(self) -> None:
        client = RegionalOpenAlexClient("secret-value", max_attempts=1)
        error = requests.exceptions.SSLError(
            "request failed for https://api.openalex.org/works?api_key=secret-value"
        )
        with patch("collector.regional_v15.requests.get", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                client._get({"filter": "primary_topic.id:T1"})
        self.assertNotIn("secret-value", str(raised.exception))
        self.assertIn("api_key=[REDACTED]", str(raised.exception))

    def test_api_key_is_redacted_from_request_errors(self) -> None:
        message = _sanitize_error(
            "request failed: https://api.openalex.org/works?api_key=secret-value&x=1"
        )
        self.assertNotIn("secret-value", message)
        self.assertIn("api_key=[REDACTED]", message)

    def test_country_filter_matches_v14_contract_without_education_limit(self) -> None:
        query_filter = region_query_filter(
            date(2026, 8, 21), date(2026, 11, 18), "CN"
        )
        self.assertIn("primary_location.source.is_core:true", query_filter)
        self.assertIn("from_publication_date:2026-08-21", query_filter)
        self.assertIn("to_publication_date:2026-11-18", query_filter)
        self.assertIn("primary_topic.field.id:15|16|17|21|22|25", query_filter)
        self.assertIn("authorships.institutions.country_code:CN", query_filter)
        self.assertNotIn("institution_type", query_filter)
        self.assertNotIn("institutions.type", query_filter)

    def test_collection_rejects_global_region(self) -> None:
        with self.assertRaisesRegex(ValueError, "only accepts CN or US"):
            validate_region("GLOBAL")

    def test_period_metrics_and_independent_ranks(self) -> None:
        topics = {"T1": "15", "T2": "15", "T3": "16"}
        records = build_period_records(
            region_code="US",
            ranking_date=date(2026, 11, 18),
            current={
                90: {"T1": 20, "T2": 10, "T3": 4},
                360: {"T1": 100, "T2": 80, "T3": 5},
            },
            previous={
                90: {"T1": 10, "T2": 0, "T3": 8},
                360: {"T1": 50, "T2": 40, "T3": 10},
            },
            topics=topics,
        )
        self.assertEqual(len(records), 6)
        ninety = {
            record["topic_id"]: record
            for record in records
            if record["period_days"] == 90
        }
        self.assertEqual(ninety["T1"]["growth_amount"], 10)
        self.assertEqual(ninety["T1"]["growth_rate"], 1.0)
        self.assertEqual(ninety["T3"]["growth_amount"], -4)
        self.assertEqual(ninety["T3"]["growth_rate"], -0.5)
        self.assertIsNone(ninety["T2"]["growth_rate"])
        self.assertEqual(ninety["T2"]["growth_status"], "zero_baseline")
        self.assertIsNone(ninety["T2"]["growth_rate_rank"])
        self.assertEqual(ninety["T1"]["works_rank"], 1)
        self.assertEqual(ninety["T1"]["growth_amount_rank"], 1)
        self.assertEqual(ninety["T1"]["window_start"], "2026-08-21")
        self.assertEqual(ninety["T1"]["previous_window_start"], "2026-05-23")
        self.assertEqual(ninety["T1"]["previous_window_end"], "2026-08-20")


class RegionalSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "radar.db"
        initialize_database(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_schema_v7_keeps_region_tables_cn_us_only(self) -> None:
        now = "2026-11-20T00:00:00+08:00"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                """
                INSERT INTO taxonomy_versions(
                    taxonomy_version, effective_date, source, topic_count,
                    field_count, is_current, imported_at
                ) VALUES (?, '2026-11-18', 'test', 1063, 6, 1, ?)
                """,
                (TAXONOMY_VERSION, now),
            )
            connection.execute(
                """
                INSERT INTO regional_snapshot_batches(
                    batch_id, ranking_date, daily_start, daily_end,
                    taxonomy_version, query_version, calculation_version,
                    status, started_at, created_at, updated_at
                ) VALUES (
                    'batch', '2026-11-18', '2025-10-24', '2026-11-18',
                    ?, 'query-v1', 'calc-v1', 'running', ?, ?, ?
                )
                """,
                (TAXONOMY_VERSION, now, now, now),
            )
            for region in ("CN", "US"):
                connection.execute(
                    """
                    INSERT INTO regional_topic_runs(
                        run_id, batch_id, region_code, status,
                        started_at, created_at, updated_at
                    ) VALUES (?, 'batch', ?, 'running', ?, ?, ?)
                    """,
                    (f"run-{region}", region, now, now, now),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO regional_topic_runs(
                        run_id, batch_id, region_code, status,
                        started_at, created_at, updated_at
                    ) VALUES ('run-global', 'batch', 'GLOBAL', 'running', ?, ?, ?)
                    """,
                    (now, now, now),
                )
            connection.commit()
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM schema_metadata WHERE key='schema_version'"
                ).fetchone()[0],
                "7",
            )
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
