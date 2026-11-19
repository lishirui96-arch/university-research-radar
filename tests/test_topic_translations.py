from __future__ import annotations

import unittest

from collector.v14_taxonomy import EXPECTED_FIELD_COUNTS, VERIFIED_TOPIC_NAMES_ZH
from topic_translations import load_topic_translation_catalog, topic_translation


class TopicTranslationTests(unittest.TestCase):
    def test_v14_catalog_covers_all_topics_with_auditable_status(self) -> None:
        catalog = load_topic_translation_catalog()
        self.assertEqual(len(catalog), sum(EXPECTED_FIELD_COUNTS.values()))
        statuses = [record["translation_status"] for record in catalog.values()]
        self.assertEqual(statuses.count("verified"), len(VERIFIED_TOPIC_NAMES_ZH))
        self.assertEqual(statuses.count("candidate"), 1063 - len(VERIFIED_TOPIC_NAMES_ZH))
        for topic_id, record in catalog.items():
            self.assertTrue(record["topic_name"])
            self.assertTrue(record["topic_name_zh"])
            self.assertTrue(record["translation_source"])
            self.assertIn(record["translation_status"], {"verified", "candidate"})
            self.assertEqual(record["topic_id"], topic_id)

    def test_verified_names_override_candidates(self) -> None:
        topic_id, expected = next(iter(VERIFIED_TOPIC_NAMES_ZH.items()))
        result = topic_translation(topic_id, "English", "Stored name")
        self.assertEqual(result["topic_name_zh"], expected)
        self.assertEqual(result["translation_status"], "verified")

    def test_candidate_status_is_explicit(self) -> None:
        result = topic_translation("T10104", "Nanofluid Flow and Heat Transfer")
        self.assertEqual(result["translation_status"], "candidate")
        self.assertIn("待审核", result["translation_status_label"])
        self.assertEqual(result["topic_name_zh"], "纳米流体流动与传热")


if __name__ == "__main__":
    unittest.main()
