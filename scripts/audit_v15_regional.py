from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from typing import Any

from collector.regional_v15 import (
    DAILY_BASELINE_DAYS,
    EXPECTED_TOPIC_COUNT,
    GLOBAL_TABLES,
    REGION_CODES,
    global_table_fingerprints,
)


def audit_regional_database(database: Path, global_source: Path | None = None) -> dict[str, Any]:
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = int(connection.execute("PRAGMA foreign_key_check").fetchone() is not None)
        batch = connection.execute(
            """
            SELECT * FROM regional_snapshot_batches
            WHERE status='published'
            ORDER BY ranking_date DESC, completed_at DESC LIMIT 1
            """
        ).fetchone()
        if batch is None:
            raise ValueError("No published V1.5 regional batch")
        batch_id = str(batch["batch_id"])
        published_runs = connection.execute(
            """
            SELECT COUNT(*) AS rows, COUNT(DISTINCT region_code) AS regions,
                   COUNT(DISTINCT query_as_of) AS query_as_of_values
            FROM regional_topic_runs
            WHERE batch_id=? AND status='published'
            """,
            (batch_id,),
        ).fetchone()
        regions: dict[str, Any] = {}
        for region in REGION_CODES:
            daily = connection.execute(
                """
                SELECT COUNT(*) rows, COUNT(DISTINCT publication_date) dates,
                       COUNT(DISTINCT topic_id) topics,
                       MIN(publication_date) start_date, MAX(publication_date) end_date,
                       COUNT(DISTINCT query_version) query_versions,
                       COUNT(DISTINCT taxonomy_version) taxonomy_versions,
                       COUNT(DISTINCT source_run_id) source_runs
                FROM regional_topic_daily_counts
                WHERE batch_id=? AND region_code=? AND data_status='success'
                """,
                (batch_id, region),
            ).fetchone()
            periods: dict[str, Any] = {}
            for period_days in (90, 360):
                snapshot = connection.execute(
                    """
                    SELECT COUNT(*) rows, COUNT(DISTINCT topic_id) topics,
                           COUNT(DISTINCT works_rank) works_ranks,
                           COUNT(DISTINCT growth_amount_rank) amount_ranks,
                           COUNT(DISTINCT growth_rate_rank) rate_ranks,
                           SUM(CASE WHEN growth_rate IS NOT NULL THEN 1 ELSE 0 END)
                               nonnull_rates,
                           SUM(CASE WHEN previous_works_count=0 AND growth_rate IS NOT NULL
                                    THEN 1 ELSE 0 END) invalid_zero_rates
                           ,SUM(CASE WHEN previous_works_count=0
                                          AND growth_status<>'zero_baseline'
                                     THEN 1 ELSE 0 END) invalid_zero_statuses
                           ,SUM(CASE WHEN previous_works_count>0
                                          AND (growth_rate IS NULL OR growth_status<>'success')
                                     THEN 1 ELSE 0 END) invalid_positive_baselines
                    FROM regional_topic_period_snapshots
                    WHERE batch_id=? AND region_code=? AND period_days=?
                      AND data_status='success'
                    """,
                    (batch_id, region, period_days),
                ).fetchone()
                mismatches = connection.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT s.topic_id, s.works_count,
                               COALESCE(SUM(d.daily_works_count), 0) daily_sum
                        FROM regional_topic_period_snapshots s
                        LEFT JOIN regional_topic_daily_counts d
                          ON d.batch_id=s.batch_id AND d.region_code=s.region_code
                         AND d.topic_id=s.topic_id
                         AND d.publication_date BETWEEN s.window_start AND s.window_end
                        WHERE s.batch_id=? AND s.region_code=? AND s.period_days=?
                        GROUP BY s.topic_id, s.works_count
                        HAVING s.works_count<>daily_sum
                    )
                    """,
                    (batch_id, region, period_days),
                ).fetchone()[0]
                periods[str(period_days)] = {
                    **dict(snapshot),
                    "daily_sum_mismatches": int(mismatches),
                }
            filters = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT query_filter FROM regional_query_logs
                    WHERE batch_id=? AND region_code=?
                    """,
                    (batch_id, region),
                ).fetchall()
            ]
            query_status = connection.execute(
                """
                SELECT request_status, COUNT(*) rows,
                       COALESCE(SUM(page_count), 0) pages,
                       COALESCE(SUM(retry_count), 0) retries
                FROM regional_query_logs
                WHERE batch_id=? AND region_code=?
                GROUP BY request_status
                """,
                (batch_id, region),
            ).fetchall()
            regions[region] = {
                "daily": dict(daily),
                "periods": periods,
                "query_status": {str(row[0]): dict(row) for row in query_status},
                "all_filters_have_region": bool(filters) and all(
                    f"authorships.institutions.country_code:{region}" in value
                    for value in filters
                ),
                "all_filters_match_v14_contract": bool(filters) and all(
                    "primary_location.source.is_core:true" in value
                    and "primary_topic.field.id:15|16|17|21|22|25" in value
                    and "from_publication_date:" in value
                    and "to_publication_date:" in value
                    for value in filters
                ),
                "any_education_filter": any("institutions.type" in value for value in filters),
            }
        global_unchanged = None
        if global_source is not None:
            global_unchanged = (
                global_table_fingerprints(global_source)
                == global_table_fingerprints(database)
            )
        expected_daily_rows = DAILY_BASELINE_DAYS * EXPECTED_TOPIC_COUNT
        complete = (
            integrity == "ok"
            and foreign_keys == 0
            and batch["completed_region_count"] == len(REGION_CODES)
            and published_runs["rows"] == len(REGION_CODES)
            and published_runs["regions"] == len(REGION_CODES)
            and all(
                item["daily"]["rows"] == expected_daily_rows
                and item["daily"]["dates"] == DAILY_BASELINE_DAYS
                and item["daily"]["topics"] == EXPECTED_TOPIC_COUNT
                and item["daily"]["start_date"] == batch["daily_start"]
                and item["daily"]["end_date"] == batch["daily_end"]
                and item["daily"]["query_versions"] == 1
                and item["daily"]["taxonomy_versions"] == 1
                and item["daily"]["source_runs"] == 1
                and item["periods"]["90"]["rows"] == EXPECTED_TOPIC_COUNT
                and item["periods"]["360"]["rows"] == EXPECTED_TOPIC_COUNT
                and item["periods"]["90"]["works_ranks"] == EXPECTED_TOPIC_COUNT
                and item["periods"]["360"]["works_ranks"] == EXPECTED_TOPIC_COUNT
                and item["periods"]["90"]["amount_ranks"] == EXPECTED_TOPIC_COUNT
                and item["periods"]["360"]["amount_ranks"] == EXPECTED_TOPIC_COUNT
                and item["periods"]["90"]["rate_ranks"]
                    == item["periods"]["90"]["nonnull_rates"]
                and item["periods"]["360"]["rate_ranks"]
                    == item["periods"]["360"]["nonnull_rates"]
                and item["periods"]["90"]["daily_sum_mismatches"] == 0
                and item["periods"]["360"]["daily_sum_mismatches"] == 0
                and item["periods"]["90"]["invalid_zero_rates"] == 0
                and item["periods"]["360"]["invalid_zero_rates"] == 0
                and item["periods"]["90"]["invalid_zero_statuses"] == 0
                and item["periods"]["360"]["invalid_zero_statuses"] == 0
                and item["periods"]["90"]["invalid_positive_baselines"] == 0
                and item["periods"]["360"]["invalid_positive_baselines"] == 0
                and item["all_filters_have_region"]
                and item["all_filters_match_v14_contract"]
                and not item["any_education_filter"]
                for item in regions.values()
            )
            and global_unchanged is not False
        )
        return {
            "database": str(database.resolve()),
            "batch": dict(batch),
            "published_runs": dict(published_runs),
            "integrity_check": integrity,
            "foreign_key_violations": foreign_keys,
            "global_tables_checked": list(GLOBAL_TABLES),
            "global_tables_unchanged": global_unchanged,
            "regions": regions,
            "complete": complete,
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a published V1.5 CN/US batch.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--global-source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_regional_database(args.database, args.global_source)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    if not result["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
