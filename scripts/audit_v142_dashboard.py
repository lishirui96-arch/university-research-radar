from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from collector.v14_taxonomy import EXPECTED_FIELD_COUNTS
from dashboard_repository import get_v14_hotspot_dashboard
from topic_translations import load_topic_translation_catalog
from trend_aggregation import diagnose_topic_trends


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def audit_dashboard(database: Path) -> dict[str, Any]:
    catalog = load_topic_translation_catalog()
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for field_id, expected_topic_count in EXPECTED_FIELD_COUNTS.items():
        for period_days in (90, 360):
            by_sort = {
                sort_by: get_v14_hotspot_dashboard(
                    database,
                    period_days=period_days,
                    field_id=field_id,
                    sort_by=sort_by,
                )
                for sort_by in ("works", "growth")
            }
            for sort_by, dashboard in by_sort.items():
                if len(dashboard["all_topics"]) != expected_topic_count:
                    failures.append(
                        f"Field {field_id}/{period_days}/{sort_by}: unexpected Topic count"
                    )
                if set(dashboard["all_topics"]["field_id"].astype(str)) != {field_id}:
                    failures.append(
                        f"Field {field_id}/{period_days}/{sort_by}: cross-Field Topic leakage"
                    )
                if sort_by == "growth" and dashboard["ranking"].empty:
                    failures.append(
                        f"Field {field_id}/{period_days}: growth ranking is empty"
                    )
                for top_n in (5, 10):
                    selected_ids = (
                        dashboard["ranking"].head(top_n)["topic_id"].astype(str).tolist()
                    )
                    diagnostics = diagnose_topic_trends(
                        dashboard["daily"],
                        dashboard["trend"],
                        selected_ids,
                        field_id,
                        len(dashboard["all_topics"]),
                    )
                    expected_points = 13
                    if len(selected_ids) != top_n:
                        failures.append(
                            f"Field {field_id}/{period_days}/{sort_by}/TOP {top_n}: short ranking"
                        )
                    if diagnostics["unmatched_topic_ids"]:
                        failures.append(
                            f"Field {field_id}/{period_days}/{sort_by}/TOP {top_n}: unmatched IDs"
                        )
                    if set(diagnostics["points_per_topic"].values()) != {expected_points}:
                        failures.append(
                            f"Field {field_id}/{period_days}/{sort_by}/TOP {top_n}: point count mismatch"
                        )
                    if diagnostics["non_null_works_count"] != top_n * expected_points:
                        failures.append(
                            f"Field {field_id}/{period_days}/{sort_by}/TOP {top_n}: missing Works"
                        )
                    selected_trend = dashboard["trend"][
                        dashboard["trend"]["topic_id"].astype(str).isin(selected_ids)
                    ]
                    bucket_sets = selected_trend.groupby("topic_id")["period_end"].apply(
                        lambda values: tuple(pd.to_datetime(values).sort_values())
                    )
                    if bucket_sets.nunique() != 1:
                        failures.append(
                            f"Field {field_id}/{period_days}/{sort_by}/TOP {top_n}: inconsistent buckets"
                        )
                    missing_translations = [
                        topic_id for topic_id in selected_ids
                        if topic_id not in catalog or not catalog[topic_id]["topic_name_zh"]
                    ]
                    if missing_translations:
                        failures.append(
                            f"Field {field_id}/{period_days}/{sort_by}/TOP {top_n}: missing Chinese names"
                        )
                    results.append(
                        {
                            "field_id": field_id,
                            "period_days": period_days,
                            "sort_by": sort_by,
                            "selection_mode": f"TOP {top_n}",
                            **diagnostics,
                            "bucket_dates": [
                                value.isoformat()
                                for value in (
                                    bucket_sets.iloc[0] if not bucket_sets.empty else ()
                                )
                            ],
                            "translation_statuses": {
                                topic_id: catalog[topic_id]["translation_status"]
                                for topic_id in selected_ids
                            },
                        }
                    )

            custom_ids = [
                str(by_sort["works"]["all_topics"].iloc[index]["topic_id"])
                for index in (0, 1, 2, -2, -1)
            ]
            custom = diagnose_topic_trends(
                by_sort["works"]["daily"], by_sort["works"]["trend"], custom_ids,
                field_id, expected_topic_count,
            )
            if custom["unmatched_topic_ids"] or set(custom["points_per_topic"].values()) != {13}:
                failures.append(f"Field {field_id}/{period_days}: custom selection mismatch")
            results.append(
                {
                    "field_id": field_id,
                    "period_days": period_days,
                    "sort_by": "works",
                    "selection_mode": "custom",
                    **custom,
                }
            )

    return {
        "database": str(database),
        "generated_at": datetime.now().astimezone().isoformat(),
        "checks": len(results),
        "failures": failures,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit = audit_dashboard(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(_json_value(audit), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"checks": audit["checks"], "failures": audit["failures"]}, ensure_ascii=False))
    if audit["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
