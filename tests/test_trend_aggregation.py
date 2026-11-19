from __future__ import annotations

import unittest

import pandas as pd

from trend_aggregation import aggregate_topic_trends


def _daily_frame(start: str, end: str, count: int = 1) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "topic_id": "T1",
            "topic_name": "Test topic",
            "daily_works_count": count,
            "query_status": "success",
        }
    )


class TrendAggregationTests(unittest.TestCase):
    def test_90_day_window_uses_end_anchored_equal_length_periods(self) -> None:
        daily = _daily_frame("2026-08-15", "2026-11-18")
        result = aggregate_topic_trends(
            daily, 90, "2026-08-21", "2026-11-18"
        )

        self.assertEqual(len(result), 13)
        first = result.iloc[0]
        self.assertEqual(first["period_start"], pd.Timestamp("2026-08-21"))
        self.assertEqual(first["period_end"], pd.Timestamp("2026-08-26"))
        self.assertEqual(first["period_days"], 6)
        self.assertEqual(first["period_works_count"], 6)
        self.assertEqual(first["comparison_start"], pd.Timestamp("2026-08-15"))
        self.assertEqual(first["comparison_end"], pd.Timestamp("2026-08-20"))
        self.assertEqual(first["comparison_works_count"], 6)
        self.assertEqual(first["growth_rate"], 0.0)
        self.assertTrue((result.iloc[1:]["period_days"] == 7).all())
        self.assertTrue((result.iloc[1:]["period_works_count"] == 7).all())

    def test_weekly_missing_and_zero_baselines_remain_na(self) -> None:
        daily = _daily_frame("2026-08-15", "2026-11-18")
        daily.loc[daily["date"].between("2026-08-15", "2026-08-20"), "daily_works_count"] = 0
        daily.loc[daily["date"] == "2026-11-18", ["daily_works_count", "query_status"]] = [pd.NA, "missing"]
        result = aggregate_topic_trends(
            daily, 90, "2026-08-21", "2026-11-18"
        )

        self.assertTrue(pd.isna(result.iloc[0]["growth_rate"]))
        self.assertEqual(result.iloc[0]["growth_status"], "zero_baseline")
        self.assertTrue(pd.isna(result.iloc[-1]["period_works_count"]))
        self.assertTrue(pd.isna(result.iloc[-1]["growth_rate"]))
        self.assertEqual(result.iloc[-1]["query_status"], "missing")

    def test_360_day_window_uses_calendar_months_and_mtd_comparison(self) -> None:
        daily = _daily_frame("2025-10-24", "2026-11-18")
        result = aggregate_topic_trends(
            daily, 360, "2025-11-24", "2026-11-18"
        )

        self.assertEqual(len(result), 13)
        first = result.iloc[0]
        self.assertEqual(first["period_label"], "2025-11")
        self.assertEqual(first["period_days"], 7)
        self.assertEqual(first["period_works_count"], 7)
        self.assertEqual(first["comparison_start"], pd.Timestamp("2025-10-24"))
        self.assertEqual(first["comparison_end"], pd.Timestamp("2025-10-30"))
        self.assertEqual(first["growth_rate"], 0.0)

        december = result[result["period_label"] == "2025-12"].iloc[0]
        self.assertEqual(december["period_works_count"], 31)
        self.assertEqual(december["comparison_works_count"], 30)
        self.assertAlmostEqual(december["growth_rate"], 1 / 30)

        current_mtd = result.iloc[-1]
        self.assertEqual(current_mtd["period_label"], "2026-11")
        self.assertEqual(current_mtd["period_days"], 18)
        self.assertEqual(current_mtd["period_works_count"], 18)
        self.assertEqual(current_mtd["comparison_start"], pd.Timestamp("2026-10-01"))
        self.assertEqual(current_mtd["comparison_end"], pd.Timestamp("2026-10-18"))
        self.assertEqual(current_mtd["comparison_works_count"], 18)
        self.assertEqual(current_mtd["growth_rate"], 0.0)

    def test_monthly_missing_day_is_not_zero_filled(self) -> None:
        daily = _daily_frame("2025-10-24", "2026-11-18")
        daily = daily[daily["date"] != pd.Timestamp("2026-11-10")]
        result = aggregate_topic_trends(
            daily, 360, "2025-11-24", "2026-11-18"
        )

        current_mtd = result.iloc[-1]
        self.assertTrue(pd.isna(current_mtd["period_works_count"]))
        self.assertTrue(pd.isna(current_mtd["growth_rate"]))
        self.assertEqual(current_mtd["query_status"], "missing")


if __name__ == "__main__":
    unittest.main()
