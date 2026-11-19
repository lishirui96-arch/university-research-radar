from __future__ import annotations

import json
import re
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.validate_trend_openalex import (
    CORE_CORPUS_FILTER,
    OpenAlexClient,
    OpenAlexValidationError,
    approved_topic_ids,
    build_filter,
    load_mapping,
)


class TrendTopicMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.mapping_path = cls.root / "config" / "trend_topic_mapping.json"
        cls.mapping = load_mapping(cls.mapping_path)

    def test_contains_exactly_the_five_v1_categories(self) -> None:
        self.assertEqual(
            set(self.mapping["categories"]),
            {
                "robotics_embodied",
                "ai_chip_packaging",
                "new_energy_storage",
                "advanced_materials",
                "bio_manufacturing",
            },
        )

    def test_candidates_have_required_audit_fields(self) -> None:
        valid_statuses = {"approved", "review", "rejected"}
        required = {
            "openalex_topic_id",
            "name",
            "description",
            "category_id",
            "category_name",
            "domain",
            "field",
            "subfield",
            "match_reason",
            "confidence",
            "status",
        }
        for category_id, category in self.mapping["categories"].items():
            self.assertTrue(category["topics"])
            self.assertTrue(approved_topic_ids(self.mapping, category_id))
            for topic in category["topics"]:
                self.assertTrue(required.issubset(topic))
                self.assertRegex(topic["openalex_topic_id"], r"^T\d+$")
                self.assertEqual(topic["category_id"], category_id)
                self.assertEqual(topic["category_name"], category["name"])
                self.assertTrue(topic["description"].strip())
                self.assertTrue(topic["match_reason"].strip())
                self.assertIn(topic["status"], valid_statuses)
                self.assertGreaterEqual(topic["confidence"], 0)
                self.assertLessEqual(topic["confidence"], 1)

    def test_approved_topics_are_unique_across_categories(self) -> None:
        approved = [
            topic["openalex_topic_id"]
            for category in self.mapping["categories"].values()
            for topic in category["topics"]
            if topic["status"] == "approved"
        ]
        self.assertEqual(len(approved), len(set(approved)))

    def test_only_approved_topics_enter_query_filter(self) -> None:
        topic_ids = approved_topic_ids(self.mapping, "robotics_embodied")
        self.assertEqual(topic_ids, ["T10879", "T10653", "T10462"])
        query_filter = build_filter(date(2026, 10, 20), date(2026, 11, 18), topic_ids)
        self.assertIn(CORE_CORPUS_FILTER, query_filter)
        self.assertIn("primary_topic.id:T10879|T10653|T10462", query_filter)
        self.assertNotIn("T10709", query_filter)
        self.assertTrue(
            re.search(
                r"from_publication_date:2026-10-20,to_publication_date:2026-11-18",
                query_filter,
            )
        )

    def test_json_is_strictly_parseable(self) -> None:
        with self.mapping_path.open(encoding="utf-8") as handle:
            reparsed = json.load(handle)
        self.assertEqual(reparsed["version"], "v1")


class OpenAlexClientErrorHandlingTests(unittest.TestCase):
    @staticmethod
    def response(status_code: int, payload: dict, headers: dict | None = None) -> Mock:
        response = Mock()
        response.status_code = status_code
        response.headers = headers or {}
        response.json.return_value = payload
        response.text = json.dumps(payload)
        return response

    @patch("scripts.validate_trend_openalex.time.sleep")
    def test_retries_429_and_returns_the_next_success(self, sleep: Mock) -> None:
        session = Mock()
        session.get.side_effect = [
            self.response(429, {"message": "rate limited"}, {"Retry-After": "1"}),
            self.response(200, {"meta": {"count": 7}, "results": []}),
        ]
        client = OpenAlexClient(session=session, max_attempts=2)

        result = client.get({"filter": "publication_date:2026-11-17"})

        self.assertEqual(result.payload["meta"]["count"], 7)
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_400_is_a_structured_non_retryable_error(self) -> None:
        session = Mock()
        session.get.return_value = self.response(400, {"message": "invalid filter"})
        client = OpenAlexClient(session=session, max_attempts=3)

        with self.assertRaises(OpenAlexValidationError) as raised:
            client.get({"filter": "invalid:true"})

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("invalid filter", str(raised.exception))
        self.assertEqual(session.get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
