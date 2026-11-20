from __future__ import annotations

import math
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

from radar import _date_segments, _parse_work, build_scan_radar
from storage import database_summary, initialize_database, save_run


def parsed_work() -> dict:
    return _parse_work(
        {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1000/example",
            "display_name": "Representative work",
            "publication_date": "2026-10-01",
            "type": "article",
            "cited_by_count": 7,
            "primary_topic": {"id": "https://openalex.org/T1", "display_name": "Robotics"},
            "topics": [
                {
                    "id": "https://openalex.org/T1",
                    "display_name": "Robotics",
                    "score": 0.91,
                }
            ],
            "authorships": [
                {
                    "author_position": "last",
                    "is_corresponding": True,
                    "author": {
                        "id": "https://openalex.org/A1",
                        "display_name": "Researcher One",
                        "orcid": "https://orcid.org/0000-0000-0000-0001",
                    },
                    "institutions": [
                        {
                            "id": "https://openalex.org/I1",
                            "display_name": "University One",
                            "country_code": "CN",
                            "type": "education",
                            "ror": "https://ror.org/01",
                        },
                        {
                            "id": "https://openalex.org/I2",
                            "display_name": "University Two",
                            "country_code": "CN",
                            "type": "education",
                            "ror": "https://ror.org/02",
                        },
                    ],
                }
            ],
            "primary_location": {"source": {"display_name": "Journal", "type": "journal"}},
            "open_access": {"is_oa": True},
        },
        "中国内地",
        {"CN"},
    )


def live_result(work: dict | None = None) -> dict:
    work = dict(work or parsed_work())
    work.update(
        {
            "topic": "具身智能",
            "controlled_topic_id": "EMB-01",
            "query_string": "embodied intelligence",
        }
    )
    works = pd.DataFrame([work])
    aggregate = [
        {
            "topic_id": "EMB-01",
            "topic": "具身智能",
            "region": "中国内地",
            "query_string": "embodied intelligence",
            "coverage_comparable": True,
            "current_count": 1,
            "baseline_1_count": 1,
            "baseline_2_count": 1,
            "baseline_3_count": 1,
            "recent_count": 1,
            "previous_count": 0,
        }
    ]
    metadata = [
        {
            "topic": "具身智能",
            "region": "中国内地",
            "total_count": 1,
            "sampled_count": 1,
            "coverage_rate": 1.0,
            "sample_truncated": False,
            "institution_coverage_complete": True,
        }
    ]
    return build_scan_radar(
        aggregate,
        works,
        metadata,
        date(2025, 11, 18),
        date(2026, 11, 17),
        "领域扫描",
        "具身智能",
        [{"source": "OpenAlex", "query": "embodied intelligence"}],
    )


class RadarAlgorithmTests(unittest.TestCase):
    def test_date_segments_are_complete_and_non_overlapping(self) -> None:
        segments = _date_segments(date(2026, 1, 1), date(2026, 1, 10), 4)
        flattened = [
            start.fromordinal(day)
            for start, end in segments
            for day in range(start.toordinal(), end.toordinal() + 1)
        ]
        self.assertEqual(flattened, [date(2026, 1, day) for day in range(1, 11)])

    def test_zero_baseline_is_new_not_infinite_growth(self) -> None:
        row = {
            "topic_id": "NEW",
            "topic": "新主题",
            "region": "中国内地",
            "query_string": "new topic",
            "current_count": 6,
            "baseline_1_count": 0,
            "baseline_2_count": 0,
            "baseline_3_count": 0,
            "recent_count": 6,
            "previous_count": 0,
        }
        result = build_scan_radar(
            [row], pd.DataFrame(), [], date(2026, 1, 1), date(2026, 12, 31),
            "领域扫描", "具身智能", [],
        )["topics"].iloc[0]
        self.assertTrue(math.isnan(result["growth"]))
        self.assertEqual(result["growth_status"], "from_zero")
        self.assertTrue(math.isnan(result["acceleration"]))
        self.assertEqual(result["acceleration_status"], "from_zero")
        self.assertFalse(math.isnan(result["adjusted_acceleration"]))
        self.assertEqual(result["newness_status"], "genuine_new")
        self.assertEqual(result["trend_label"], "新兴方向")

    def test_small_sample_growth_is_shrunk_for_scoring(self) -> None:
        row = {
            "topic_id": "SMALL", "topic": "小样本", "region": "中国内地",
            "query_string": "small", "current_count": 2,
            "baseline_1_count": 1, "baseline_2_count": 1, "baseline_3_count": 1,
            "recent_count": 1, "previous_count": 1,
        }
        topic = build_scan_radar(
            [row], pd.DataFrame(), [], date(2026, 1, 1), date(2026, 12, 31),
            "领域扫描", "具身智能", [],
        )["topics"].iloc[0]
        self.assertEqual(topic["growth"], 1.0)
        self.assertLess(topic["adjusted_growth"], topic["growth"])
        self.assertTrue(topic["small_sample_warning"])

    def test_coverage_change_is_not_labeled_as_research_growth(self) -> None:
        row = {
            "topic_id": "COVERAGE", "topic": "覆盖变化", "region": "中国内地",
            "query_string": "coverage", "coverage_comparable": False,
            "current_count": 30, "baseline_1_count": 10,
            "baseline_2_count": 10, "baseline_3_count": 10,
            "recent_count": 15, "previous_count": 15,
        }
        topic = build_scan_radar(
            [row], pd.DataFrame(), [], date(2026, 1, 1), date(2026, 12, 31),
            "领域扫描", "具身智能", [],
        )["topics"].iloc[0]
        self.assertEqual(topic["newness_status"], "insufficient_history")
        self.assertEqual(topic["trend_label"], "证据不足")
        self.assertIn("不解释为论文增长", topic["growth_interpretation"])

    def test_missing_history_keeps_scores_missing(self) -> None:
        row = {
            "topic_id": "MISS", "topic": "缺失", "region": "中国内地",
            "query_string": "missing", "current_count": 20,
            "baseline_1_count": None, "baseline_2_count": 4, "baseline_3_count": 5,
            "recent_count": None, "previous_count": 10,
        }
        topic = build_scan_radar(
            [row], pd.DataFrame(), [], date(2026, 1, 1), date(2026, 12, 31),
            "领域扫描", "具身智能", [],
        )["topics"].iloc[0]
        self.assertTrue(math.isnan(topic["growth"]))
        self.assertTrue(math.isnan(topic["momentum_score"]))
        self.assertTrue(math.isnan(topic["acceleration_score"]))
        self.assertLess(topic["score_coverage"], 0.5)
        self.assertEqual(topic["trend_label"], "证据不足")

    def test_group_breadth_scores_only_verified_evidence(self) -> None:
        work = parsed_work()
        work.update(
            {
                "topic": "主题", "controlled_topic_id": "T", "query_string": "topic",
                "group_name": "Verified lab", "group_confidence": "高",
            }
        )
        row = {
            "topic_id": "T", "topic": "主题", "region": "中国内地",
            "query_string": "topic", "current_count": 20,
            "baseline_1_count": 10, "baseline_2_count": 10, "baseline_3_count": 10,
            "recent_count": 8, "previous_count": 12,
        }
        metadata = [{
            "topic": "主题", "region": "中国内地", "sampled_count": 20,
            "coverage_rate": 1.0, "sample_truncated": False,
            "institution_coverage_complete": True,
        }]
        topic = build_scan_radar(
            [row], pd.DataFrame([work]), metadata,
            date(2026, 1, 1), date(2026, 12, 31), "领域扫描", "具身智能", [],
        )["topics"].iloc[0]
        self.assertEqual(topic["group_breadth"], 1)
        self.assertEqual(topic["group_breadth_score"], 10.0)


class StorageMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "radar.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_v1_database(self) -> None:
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(
                """
                CREATE TABLE schema_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO schema_metadata VALUES ('schema_version', '1');
                CREATE TABLE scan_runs(
                    run_id TEXT PRIMARY KEY, status TEXT NOT NULL, run_mode TEXT,
                    domain_profile TEXT, attempted_query TEXT, parameters_json TEXT NOT NULL,
                    error TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE scan_topic_metrics(
                    run_id TEXT NOT NULL, row_number INTEGER NOT NULL, topic_id TEXT,
                    topic TEXT, region TEXT, metrics_json TEXT NOT NULL,
                    PRIMARY KEY(run_id,row_number)
                );
                CREATE TABLE scan_query_log(
                    run_id TEXT NOT NULL, row_number INTEGER NOT NULL, source TEXT,
                    topic TEXT, region TEXT, query_string TEXT, result_count INTEGER,
                    sample_count INTEGER, record_json TEXT NOT NULL,
                    PRIMARY KEY(run_id,row_number)
                );
                INSERT INTO scan_runs VALUES(
                    'historic','success',NULL,NULL,'old','{}','','2026-01-01',
                    '2026-01-02','2026-01-02'
                );
                """
            )

    def test_v1_migration_is_idempotent_and_preserves_history(self) -> None:
        self._create_v1_database()
        initialize_database(self.path)
        initialize_database(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT value FROM schema_metadata").fetchone()[0], "7")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 7)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_deduplicates_works_and_preserves_multiple_affiliations(self) -> None:
        result = live_result()
        run = {
            "run_id": "run-1", "status": "success", "run_mode": "领域扫描",
            "domain_profile": "具身智能", "attempted_query": "具身智能",
            "started_at": "2026-11-17T10:00:00+08:00",
            "completed_at": "2026-11-17T10:01:00+08:00",
        }
        save_run(run, parameters={}, result=result, path=self.path)
        save_run(run, parameters={}, result=result, path=self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM works").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM authors").fetchone()[0], 1)
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM work_authorship_institutions").fetchone()[0], 2
            )
            group = db.execute(
                "SELECT status, confidence FROM research_groups"
            ).fetchone()
            self.assertEqual(group, ("candidate", "medium"))
            self.assertEqual(
                db.execute("SELECT verification_status FROM research_group_evidence").fetchone()[0],
                "candidate",
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM topic_snapshots").fetchone()[0], 1)
        self.assertEqual(database_summary(self.path)["schema_version"], 7)

    def test_failed_run_does_not_remove_last_success(self) -> None:
        success = {
            "run_id": "success", "status": "success", "started_at": "2026-01-01",
            "completed_at": "2026-01-02",
        }
        save_run(success, result=live_result(), path=self.path)
        failed = {
            "run_id": "failed", "status": "failed", "error": "network",
            "started_at": "2026-01-03", "completed_at": "2026-01-03",
        }
        save_run(failed, path=self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM scan_topic_metrics WHERE run_id='success'"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute("SELECT status FROM scan_runs WHERE run_id='failed'").fetchone()[0],
                "failed",
            )


class DeploymentScriptTests(unittest.TestCase):
    def test_update_scripts_backup_before_pull(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for script in [root / "scripts/update_windows.ps1", root / "scripts/update_linux.sh"]:
            text = script.read_text(encoding="utf-8")
            self.assertLess(text.index("backup_database.py"), text.index("git fetch"))
            self.assertNotIn("down -v", text)


if __name__ == "__main__":
    unittest.main()
