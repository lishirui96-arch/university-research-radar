from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Iterable

import pandas as pd


CALCULATION_VERSION = "distinct-citing-work-window-v1"
QUERY_VERSION = "openalex-referenced-works-v1"
REGIONS = ("GLOBAL", "CN", "US")


def aggregate_windowed_citations(
    citation_edges: pd.DataFrame,
    candidate_works: pd.DataFrame,
    *,
    window_end: date,
) -> pd.DataFrame:
    """Aggregate distinct citation edges for 90/360-day inclusive windows."""
    required_edges = {"citing_work_id", "cited_work_id", "citing_publication_date"}
    required_works = {
        "openalex_work_id", "topic_id", "field_id", "title", "publication_date",
    }
    if not required_edges.issubset(citation_edges.columns):
        raise ValueError("citation_edges is missing required columns")
    if not required_works.issubset(candidate_works.columns):
        raise ValueError("candidate_works is missing required columns")

    edges = citation_edges.copy()
    edges["citing_publication_date"] = pd.to_datetime(
        edges["citing_publication_date"], errors="coerce"
    ).dt.date
    edges = edges.dropna(subset=["citing_publication_date"])
    edges = edges.drop_duplicates(["citing_work_id", "cited_work_id"])
    end = window_end
    start_360 = end - timedelta(days=359)
    start_90 = end - timedelta(days=89)
    edges = edges[
        (edges["citing_publication_date"] >= start_360)
        & (edges["citing_publication_date"] <= end)
    ].copy()
    edges["cited_in_360d"] = 1
    edges["cited_in_90d"] = (
        edges["citing_publication_date"] >= start_90
    ).astype(int)
    counts = edges.groupby("cited_work_id", as_index=False).agg(
        cited_in_90d=("cited_in_90d", "sum"),
        cited_in_360d=("cited_in_360d", "sum"),
    )

    works = candidate_works.drop_duplicates("openalex_work_id").copy()
    result = works.merge(
        counts, left_on="openalex_work_id", right_on="cited_work_id", how="inner"
    ).drop(columns=["cited_work_id"])
    result["doi"] = result.get("doi", pd.Series(index=result.index, dtype="object"))
    result["venue"] = result.get("venue", pd.Series(index=result.index, dtype="object"))
    result["openalex_url"] = result.get(
        "openalex_url", result["openalex_work_id"].map(lambda value: f"https://openalex.org/{value}")
    )
    return result.reset_index(drop=True)


def publish_citation_snapshot(
    database: str | Path,
    *,
    batch_id: str,
    ranking_date: date,
    period_days: int,
    taxonomy_version: str,
    rows: pd.DataFrame,
    query_as_of: str,
    expected_scope_count: int,
    citing_work_count: int,
    citation_edge_count: int,
    api_request_count: int,
    completed_scopes: Iterable[tuple[str, str]],
    scope_diagnostics: dict[tuple[str, str], dict] | None = None,
) -> None:
    """Atomically publish a complete, prevalidated citation snapshot."""
    required = {
        "region_code", "topic_id", "field_id", "openalex_work_id", "title",
        "publication_date", "window_citation_count",
    }
    if not required.issubset(rows.columns):
        raise ValueError("citation snapshot rows are incomplete")
    if expected_scope_count <= 0:
        raise ValueError("expected_scope_count must be positive")
    if period_days not in {90, 360}:
        raise ValueError("period_days must be 90 or 360")
    now = datetime.now().astimezone().isoformat()
    window_start = ranking_date - timedelta(days=period_days - 1)
    records: list[tuple] = []
    for row in rows.itertuples(index=False):
        region = str(row.region_code).upper()
        if region not in REGIONS:
            raise ValueError(f"Unsupported region {region}")
        work_id = str(row.openalex_work_id).rsplit("/", 1)[-1]
        records.append((
            batch_id, region, str(row.topic_id), str(row.field_id), work_id,
            str(row.title), getattr(row, "doi", None),
            getattr(row, "openalex_url", None) or f"https://openalex.org/{work_id}",
            getattr(row, "venue", None), str(row.publication_date),
            int(row.window_citation_count), query_as_of, now, now,
        ))
    scopes = {(str(region).upper(), str(topic)) for region, topic in completed_scopes}
    if len(scopes) != expected_scope_count:
        raise ValueError(
            f"Cannot publish incomplete citation batch: {len(scopes)}/"
            f"{expected_scope_count} scopes"
        )
    invalid_regions = {region for region, _ in scopes} - set(REGIONS)
    if invalid_regions:
        raise ValueError(f"Unsupported regions: {sorted(invalid_regions)}")
    row_scope = set(zip(
        rows["region_code"].astype(str).str.upper(), rows["topic_id"].astype(str)
    ))
    if not row_scope.issubset(scopes):
        raise ValueError("Snapshot rows include an unvalidated scope")

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO citation_snapshot_batches(
                batch_id, ranking_date, period_days, window_start,
                window_end, taxonomy_version, query_version, calculation_version,
                status, query_as_of, expected_scope_count, completed_scope_count,
                citing_work_count, citation_edge_count, api_request_count,
                started_at, completed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id, ranking_date.isoformat(), period_days,
                window_start.isoformat(), ranking_date.isoformat(), taxonomy_version,
                QUERY_VERSION, CALCULATION_VERSION, query_as_of,
                expected_scope_count, len(scopes), citing_work_count,
                citation_edge_count, api_request_count, now, now, now, now,
            ),
        )
        matched_counts = rows.groupby(["region_code", "topic_id"]).size().to_dict()
        connection.executemany(
            """
            INSERT INTO citation_snapshot_scopes(
                batch_id, region_code, topic_id, status, matched_work_count,
                created_at, updated_at, candidate_count, candidates_scanned,
                tenth_citation_count, unchecked_cumulative_upper_bound,
                api_request_count
            ) VALUES (?, ?, ?, 'success', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    batch_id, region, topic,
                    int(matched_counts.get((region, topic), 0)), now, now,
                    *((scope_diagnostics or {}).get((region, topic), {}).get(key)
                      for key in (
                          "candidate_count", "candidates_scanned",
                          "tenth_citation_count", "stop_cumulative_upper_bound",
                          "api_request_count",
                      )),
                )
                for region, topic in sorted(scopes)
            ],
        )
        connection.executemany(
            """
            INSERT INTO citation_topic_work_snapshots(
                batch_id, region_code, topic_id, field_id, openalex_work_id,
                title, doi, openalex_url, venue, publication_date,
                window_citation_count, query_as_of, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        connection.commit()
