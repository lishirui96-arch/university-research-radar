from __future__ import annotations

import hashlib
import logging
import socket
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from collector.openalex_client import OpenAlexClient
from repositories.collection_repository import CollectionRepository, canonical_json, utc_now


LOGGER = logging.getLogger(__name__)

WORK_SELECT = (
    "id",
    "doi",
    "title",
    "publication_date",
    "type",
    "language",
    "cited_by_count",
    "open_access",
    "primary_location",
    "best_oa_location",
    "authorships",
    "topics",
    "primary_topic",
    "updated_date",
    "created_date",
)


@dataclass(frozen=True)
class WorksIngestResult:
    job_id: str
    batch_id: str
    collection_run_id: str
    status: str
    publication_date: str
    total_count: int | None
    sampled_count: int
    coverage_rate: float | None
    request_count: int
    response_bytes: int
    retry_count: int
    rate_limit: int | None
    rate_remaining: int | None
    rate_reset_seconds: int | None
    resumed_from_page: int
    doi_conflicts: int
    inserted_works: int
    updated_works: int
    unchanged_works: int
    authors_inserted: int
    authors_updated: int
    institution_relationship_changes: int
    topic_relationship_changes: int
    count_delta: int | None
    stability_status: str | None
    type_counts: dict[str, int]
    published: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ingest_works_for_date(
    db_path: Path | str,
    *,
    publication_date: str,
    client: OpenAlexClient | None = None,
    max_pages: int | None = None,
    publish: bool = True,
    worker_id: str | None = None,
    collection_run_id: str | None = None,
    daily_run_id: str | None = None,
    local_run_date: str | None = None,
) -> WorksIngestResult:
    """Collect one publication date.

    ``collection_run_id`` identifies one resumable attempt. Reusing it is
    idempotent; a different value creates a new batch for the same date.
    """
    date.fromisoformat(publication_date)
    local_run_date = local_run_date or date.today().isoformat()
    date.fromisoformat(local_run_date)
    collection_run_id = collection_run_id or _new_collection_run_id()
    repository = CollectionRepository(db_path)
    handle = repository.ensure_job(
        job_type="daily_ingest",
        logical_date=collection_run_id,
        shard_key=publication_date,
    )
    checkpoint = repository.checkpoint(handle.job_id) or {}
    resumed_page = int(checkpoint.get("page_number") or 0)
    sampled_count = int(checkpoint.get("records_processed") or 0)
    state = checkpoint.get("state") or {}
    total_count = state.get("total_count")
    cursor = checkpoint.get("cursor_value") or "*"
    doi_conflicts = int(state.get("doi_conflicts") or 0)
    unchanged_works = int(state.get("unchanged_works") or 0)
    type_counts = Counter({str(k): int(v) for k, v in (state.get("type_counts") or {}).items()})

    if handle.status == "succeeded":
        batch_status = repository.batch_status(handle.batch_id)
        observation: dict[str, Any] = {}
        if publish and batch_status == "validated":
            observation = repository.publish_works_batch(
                batch_id=handle.batch_id,
                run_id=daily_run_id,
                publication_date=publication_date,
                local_run_date=local_run_date,
                meta_count=int(total_count or 0),
                sampled_count=sampled_count,
                is_truncated=False,
                unchanged_works=unchanged_works,
                request_count=0,
                response_bytes=0,
                retry_count=0,
                rate_remaining=None,
                type_counts=dict(type_counts),
            )
            batch_status = "published"
        return _build_result(
            repository, handle.job_id, handle.batch_id, collection_run_id,
            "succeeded", publication_date, total_count, sampled_count,
            0, 0, 0, None, None, None, resumed_page, doi_conflicts,
            unchanged_works, dict(type_counts), batch_status == "published", observation,
        )

    acquired, attempt_number = repository.acquire_job(
        handle.job_id,
        worker_id=worker_id or f"{socket.gethostname()}:daily_ingest",
        lease_seconds=1800,
    )
    if not acquired or attempt_number is None:
        raise RuntimeError(f"Collection job {handle.job_id} is already leased or complete.")

    openalex = client or OpenAlexClient()
    openalex.reset_stats()
    parameters = {
        "filter": (
            f"from_publication_date:{publication_date},"
            f"to_publication_date:{publication_date},institutions.type:education"
        )
    }
    requested_at = utc_now()
    page_number = resumed_page
    complete = False
    repository.mark_work_date_rechecking(publication_date, daily_run_id)
    try:
        for page in openalex.iter_cursor(
            "works",
            params=parameters,
            select_fields=WORK_SELECT,
            cursor=cursor,
            max_pages=max_pages,
        ):
            page_number += 1
            if total_count is None:
                total_count = page.total_count
            now = utc_now()
            with repository.connection() as connection:
                page_result = _write_works(
                    connection, page.results, handle.batch_id, now, repository
                )
                doi_conflicts += page_result["doi_conflicts"]
                unchanged_works += page_result["unchanged_works"]
                type_counts.update(page_result["type_counts"])
                sampled_count += len(page.results)
                repository.save_checkpoint(
                    connection,
                    job_id=handle.job_id,
                    cursor=page.next_cursor,
                    page_number=page_number,
                    records_processed=sampled_count,
                    state={
                        "total_count": total_count,
                        "doi_conflicts": doi_conflicts,
                        "unchanged_works": unchanged_works,
                        "type_counts": dict(type_counts),
                        "complete": page.next_cursor is None,
                    },
                    lease_seconds=1800,
                )
            LOGGER.info(
                "daily_ingest date=%s batch=%s page=%s records=%s total=%s",
                publication_date, handle.batch_id, page_number, sampled_count, total_count,
            )
            if page.next_cursor is None:
                complete = True
                break

        repository.record_query_audit(
            batch_id=handle.batch_id,
            job_id=handle.job_id,
            endpoint="works",
            parameters=parameters,
            select_fields=WORK_SELECT,
            requested_at=requested_at,
            completed_at=utc_now(),
            total_count=total_count,
            sampled_count=sampled_count,
            request_count=openalex.stats.request_count,
            response_bytes=openalex.stats.response_bytes,
            retry_count=openalex.stats.retry_count,
            rate_limit=openalex.stats.rate_limit,
            rate_remaining=openalex.stats.rate_remaining,
            rate_reset_seconds=openalex.stats.rate_reset_seconds,
            is_truncated=not complete,
        )
        if not complete:
            repository.finish_attempt(
                job_id=handle.job_id,
                attempt_number=attempt_number,
                success=False,
                interrupted=True,
                request_count=openalex.stats.request_count,
                response_bytes=openalex.stats.response_bytes,
                retry_count=openalex.stats.retry_count,
            )
            return _build_result(
                repository, handle.job_id, handle.batch_id, collection_run_id,
                "pending", publication_date, total_count, sampled_count,
                openalex.stats.request_count, openalex.stats.response_bytes,
                openalex.stats.retry_count, openalex.stats.rate_limit,
                openalex.stats.rate_remaining, openalex.stats.rate_reset_seconds,
                resumed_page, doi_conflicts, unchanged_works, dict(type_counts), False, {},
            )

        counts_match = total_count is not None and sampled_count == total_count
        repository.add_quality_report(
            batch_id=handle.batch_id,
            check_name="daily_ingest_sample_matches_meta",
            severity="error",
            status="passed" if counts_match else "failed",
            expected={"meta_count": total_count},
            actual={"sampled_count": sampled_count},
            details="A full one-day ingest must process every OpenAlex result page.",
        )
        with repository.connection() as connection:
            foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        repository.add_quality_report(
            batch_id=handle.batch_id,
            check_name="daily_ingest_foreign_keys",
            severity="error",
            status="passed" if foreign_key_violations == 0 else "failed",
            expected={"violations": 0},
            actual={"violations": foreign_key_violations},
        )
        if not counts_match or foreign_key_violations:
            raise RuntimeError("Works ingest failed data-quality checks.")
        repository.mark_batch_validated(
            handle.batch_id,
            {
                "publication_date": publication_date,
                "total_count": total_count,
                "sampled_count": sampled_count,
                "coverage_rate": 1.0,
                "doi_conflicts": doi_conflicts,
                "unchanged_works": unchanged_works,
                "type_counts": dict(type_counts),
                "request_count": openalex.stats.request_count,
                "response_bytes": openalex.stats.response_bytes,
            },
        )
        observation: dict[str, Any] = {}
        if publish:
            observation = repository.publish_works_batch(
                batch_id=handle.batch_id,
                run_id=daily_run_id,
                publication_date=publication_date,
                local_run_date=local_run_date,
                meta_count=int(total_count or 0),
                sampled_count=sampled_count,
                is_truncated=False,
                unchanged_works=unchanged_works,
                request_count=openalex.stats.request_count,
                response_bytes=openalex.stats.response_bytes,
                retry_count=openalex.stats.retry_count,
                rate_remaining=openalex.stats.rate_remaining,
                type_counts=dict(type_counts),
            )
        repository.finish_attempt(
            job_id=handle.job_id,
            attempt_number=attempt_number,
            success=True,
            request_count=openalex.stats.request_count,
            response_bytes=openalex.stats.response_bytes,
            retry_count=openalex.stats.retry_count,
        )
        return _build_result(
            repository, handle.job_id, handle.batch_id, collection_run_id,
            "succeeded", publication_date, total_count, sampled_count,
            openalex.stats.request_count, openalex.stats.response_bytes,
            openalex.stats.retry_count, openalex.stats.rate_limit,
            openalex.stats.rate_remaining, openalex.stats.rate_reset_seconds,
            resumed_page, doi_conflicts, unchanged_works, dict(type_counts), publish, observation,
        )
    except Exception as exc:
        repository.mark_work_date_failed(publication_date, daily_run_id)
        repository.finish_attempt(
            job_id=handle.job_id,
            attempt_number=attempt_number,
            success=False,
            request_count=openalex.stats.request_count,
            response_bytes=openalex.stats.response_bytes,
            retry_count=openalex.stats.retry_count,
            error=exc,
        )
        raise


def _new_collection_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"manual-{stamp}-{uuid.uuid4().hex[:8]}"


def _build_result(
    repository: CollectionRepository,
    job_id: str,
    batch_id: str,
    collection_run_id: str,
    status: str,
    publication_date: str,
    total_count: int | None,
    sampled_count: int,
    request_count: int,
    response_bytes: int,
    retry_count: int,
    rate_limit: int | None,
    rate_remaining: int | None,
    rate_reset_seconds: int | None,
    resumed_from_page: int,
    doi_conflicts: int,
    unchanged_works: int,
    type_counts: dict[str, int],
    published: bool,
    observation: dict[str, Any],
) -> WorksIngestResult:
    changes = repository.entity_change_counts(batch_id)
    coverage = sampled_count / total_count if total_count and total_count > 0 else (1.0 if total_count == 0 else None)
    return WorksIngestResult(
        job_id=job_id,
        batch_id=batch_id,
        collection_run_id=collection_run_id,
        status=status,
        publication_date=publication_date,
        total_count=total_count,
        sampled_count=sampled_count,
        coverage_rate=coverage,
        request_count=request_count,
        response_bytes=response_bytes,
        retry_count=retry_count,
        rate_limit=rate_limit,
        rate_remaining=rate_remaining,
        rate_reset_seconds=rate_reset_seconds,
        resumed_from_page=resumed_from_page,
        doi_conflicts=doi_conflicts,
        inserted_works=changes.get("work_inserted", 0),
        updated_works=changes.get("work_updated", 0),
        unchanged_works=unchanged_works,
        authors_inserted=changes.get("author_inserted", 0),
        authors_updated=changes.get("author_updated", 0),
        institution_relationship_changes=sum(v for k, v in changes.items() if k.startswith("institution_relation_")),
        topic_relationship_changes=sum(v for k, v in changes.items() if k.startswith("topic_relation_")),
        count_delta=observation.get("count_delta"),
        stability_status=observation.get("stability_status"),
        type_counts=type_counts,
        published=published,
    )


def _write_works(
    connection: Any,
    records: list[dict[str, Any]],
    batch_id: str,
    now: str,
    repository: CollectionRepository,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "doi_conflicts": 0,
        "unchanged_works": 0,
        "type_counts": Counter(),
    }
    for record in records:
        work_id = str(record.get("id") or "").strip()
        if not work_id:
            continue
        raw_type = str(record.get("type") or "other")
        result["type_counts"][raw_type] += 1
        source_hash = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
        source_state = connection.execute(
            "SELECT source_hash FROM work_source_state WHERE work_id=?", (work_id,)
        ).fetchone()
        if source_state and source_state[0] == source_hash:
            connection.execute(
                "UPDATE work_source_state SET last_seen_batch_id=?, last_seen_at=? WHERE work_id=?",
                (batch_id, now, work_id),
            )
            connection.execute(
                "UPDATE work_collection_metadata SET last_batch_id=?, last_collected_at=? WHERE work_id=?",
                (batch_id, now, work_id),
            )
            result["unchanged_works"] += 1
            continue

        existed = connection.execute(
            "SELECT 1 FROM works WHERE openalex_work_id=?", (work_id,)
        ).fetchone() is not None
        repository.record_entity_change(
            connection, batch_id=batch_id, entity_type="work",
            entity_key=work_id, change_type="updated" if existed else "inserted",
        )
        result["doi_conflicts"] += _upsert_work(connection, record, batch_id, now)
        _sync_authorships(connection, record, batch_id, now, repository)
        _sync_topics(connection, record, batch_id, now, repository)
        _upsert_collection_metadata(connection, record, batch_id, now)
        connection.execute(
            """
            INSERT INTO work_source_state(
                work_id, source_hash, source_updated_date, first_seen_batch_id,
                last_seen_batch_id, last_changed_batch_id, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(work_id) DO UPDATE SET
                source_hash=excluded.source_hash,
                source_updated_date=excluded.source_updated_date,
                last_seen_batch_id=excluded.last_seen_batch_id,
                last_changed_batch_id=excluded.last_changed_batch_id,
                last_seen_at=excluded.last_seen_at
            """,
            (
                work_id, source_hash, record.get("updated_date"), batch_id,
                batch_id, batch_id, now, now,
            ),
        )
    return result


def _upsert_work(connection: Any, record: dict[str, Any], batch_id: str, now: str) -> int:
    work_id = str(record["id"]).strip()
    doi = _normalize_doi(record.get("doi"))
    stored_doi = doi
    conflict_count = 0
    if doi:
        conflict = connection.execute(
            "SELECT openalex_work_id FROM works WHERE doi=? AND openalex_work_id!=?",
            (doi, work_id),
        ).fetchone()
        if conflict:
            existing_work_id = str(conflict[0])
            conflict_id = hashlib.sha256(f"{doi}|{existing_work_id}|{work_id}".encode()).hexdigest()
            connection.execute(
                """
                INSERT INTO doi_conflicts(
                    conflict_id, normalized_doi, existing_work_id, incoming_work_id,
                    batch_id, evidence_json, first_detected_at, last_detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_doi, existing_work_id, incoming_work_id)
                DO UPDATE SET batch_id=excluded.batch_id,
                    evidence_json=excluded.evidence_json,
                    last_detected_at=excluded.last_detected_at
                """,
                (
                    conflict_id, doi, existing_work_id, work_id, batch_id,
                    canonical_json({"incoming_title": record.get("title")}), now, now,
                ),
            )
            stored_doi = None
            conflict_count = 1
    primary_location = record.get("primary_location") or {}
    source = primary_location.get("source") or {}
    open_access = record.get("open_access") or {}
    connection.execute(
        """
        INSERT INTO works(
            openalex_work_id, doi, title, publication_date, work_type,
            source_type, venue, cited_by_count, is_open_access, source,
            first_created_at, last_updated_at, last_seen_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OpenAlex', ?, ?, NULL)
        ON CONFLICT(openalex_work_id) DO UPDATE SET
            doi=excluded.doi, title=excluded.title,
            publication_date=excluded.publication_date,
            work_type=excluded.work_type, source_type=excluded.source_type,
            venue=excluded.venue, cited_by_count=excluded.cited_by_count,
            is_open_access=excluded.is_open_access,
            last_updated_at=excluded.last_updated_at
        """,
        (
            work_id, stored_doi, record.get("title") or "Untitled work",
            record.get("publication_date"), record.get("type"), source.get("type"),
            source.get("display_name"), int(record.get("cited_by_count") or 0),
            int(bool(open_access.get("is_oa"))), now, now,
        ),
    )
    return conflict_count


def _sync_authorships(
    connection: Any,
    record: dict[str, Any],
    batch_id: str,
    now: str,
    repository: CollectionRepository,
) -> None:
    work_id = str(record["id"]).strip()
    expected_authors: set[str] = set()
    expected_institutions: dict[str, set[str]] = {}
    for order, authorship in enumerate(record.get("authorships") or []):
        author = authorship.get("author") or {}
        author_id = str(author.get("id") or "").strip()
        if not author_id:
            continue
        expected_authors.add(author_id)
        author_row = connection.execute(
            "SELECT display_name, orcid FROM authors WHERE openalex_author_id=?", (author_id,)
        ).fetchone()
        new_values = (author.get("display_name") or author_id, author.get("orcid"))
        author_change = None
        if author_row is None:
            author_change = "inserted"
        elif tuple(author_row) != new_values:
            author_change = "updated"
        connection.execute(
            """
            INSERT INTO authors(openalex_author_id, display_name, orcid, source,
                first_created_at, last_updated_at)
            VALUES (?, ?, ?, 'OpenAlex', ?, ?)
            ON CONFLICT(openalex_author_id) DO UPDATE SET
                display_name=excluded.display_name, orcid=excluded.orcid,
                last_updated_at=excluded.last_updated_at
            """,
            (author_id, new_values[0], new_values[1], now, now),
        )
        if author_change:
            repository.record_entity_change(
                connection, batch_id=batch_id, entity_type="author",
                entity_key=author_id, change_type=author_change,
            )
        connection.execute(
            """
            INSERT INTO work_authorships(
                work_id, author_id, author_position, is_corresponding,
                authorship_order, source, first_created_at, last_updated_at
            ) VALUES (?, ?, ?, ?, ?, 'OpenAlex', ?, ?)
            ON CONFLICT(work_id, author_id) DO UPDATE SET
                author_position=excluded.author_position,
                is_corresponding=excluded.is_corresponding,
                authorship_order=excluded.authorship_order,
                last_updated_at=excluded.last_updated_at
            """,
            (
                work_id, author_id, authorship.get("author_position"),
                int(bool(authorship.get("is_corresponding"))), order, now, now,
            ),
        )
        authorship_id = connection.execute(
            "SELECT authorship_id FROM work_authorships WHERE work_id=? AND author_id=?",
            (work_id, author_id),
        ).fetchone()[0]
        expected_institutions[author_id] = set()
        existing_institutions = {
            str(row[0]) for row in connection.execute(
                "SELECT institution_id FROM work_authorship_institutions WHERE authorship_id=?",
                (authorship_id,),
            )
        }
        for institution in authorship.get("institutions") or []:
            institution_id = str(institution.get("id") or "").strip()
            if not institution_id:
                continue
            expected_institutions[author_id].add(institution_id)
            connection.execute(
                """
                INSERT INTO institutions(
                    openalex_institution_id, display_name, country_code,
                    institution_type, ror, source, first_created_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, 'OpenAlex', ?, ?)
                ON CONFLICT(openalex_institution_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    country_code=COALESCE(excluded.country_code, institutions.country_code),
                    institution_type=COALESCE(excluded.institution_type, institutions.institution_type),
                    ror=COALESCE(excluded.ror, institutions.ror),
                    last_updated_at=excluded.last_updated_at
                """,
                (
                    institution_id, institution.get("display_name") or institution_id,
                    institution.get("country_code"), institution.get("type"),
                    institution.get("ror"), now, now,
                ),
            )
            connection.execute(
                """
                INSERT INTO work_authorship_institutions(
                    authorship_id, institution_id, source, first_created_at, last_updated_at
                ) VALUES (?, ?, 'OpenAlex', ?, ?)
                ON CONFLICT(authorship_id, institution_id) DO UPDATE SET
                    last_updated_at=excluded.last_updated_at
                """,
                (authorship_id, institution_id, now, now),
            )
            if institution_id not in existing_institutions:
                repository.record_entity_change(
                    connection, batch_id=batch_id, entity_type="institution_relation",
                    entity_key=f"{work_id}|{author_id}|{institution_id}", change_type="inserted",
                )
        for institution_id in existing_institutions - expected_institutions[author_id]:
            connection.execute(
                "DELETE FROM work_authorship_institutions WHERE authorship_id=? AND institution_id=?",
                (authorship_id, institution_id),
            )
            repository.record_entity_change(
                connection, batch_id=batch_id, entity_type="institution_relation",
                entity_key=f"{work_id}|{author_id}|{institution_id}", change_type="deleted",
            )
    existing_authors = {
        str(row[0]) for row in connection.execute(
            "SELECT author_id FROM work_authorships WHERE work_id=?", (work_id,)
        )
    }
    for author_id in existing_authors - expected_authors:
        row = connection.execute(
            "SELECT authorship_id FROM work_authorships WHERE work_id=? AND author_id=?",
            (work_id, author_id),
        ).fetchone()
        if row:
            for institution_row in connection.execute(
                "SELECT institution_id FROM work_authorship_institutions WHERE authorship_id=?",
                (row[0],),
            ):
                repository.record_entity_change(
                    connection, batch_id=batch_id, entity_type="institution_relation",
                    entity_key=f"{work_id}|{author_id}|{institution_row[0]}", change_type="deleted",
                )
        connection.execute(
            "DELETE FROM work_authorships WHERE work_id=? AND author_id=?", (work_id, author_id)
        )


def _sync_topics(
    connection: Any,
    record: dict[str, Any],
    batch_id: str,
    now: str,
    repository: CollectionRepository,
) -> None:
    work_id = str(record["id"]).strip()
    primary_topic_id = str((record.get("primary_topic") or {}).get("id") or "").strip() or None
    expected: set[str] = set()
    existing = {
        str(row[0]) for row in connection.execute(
            "SELECT topic_key FROM work_topics WHERE work_id=?", (work_id,)
        )
    }
    for topic in record.get("topics") or []:
        topic_id = str(topic.get("id") or "").strip()
        if not topic_id:
            continue
        topic_key = f"openalex:{topic_id.rsplit('/', 1)[-1]}"
        expected.add(topic_key)
        connection.execute(
            """
            INSERT INTO topics(
                topic_key, openalex_topic_id, label, topic_kind, description,
                source, first_created_at, last_updated_at
            ) VALUES (?, ?, ?, 'openalex', NULL, 'OpenAlex', ?, ?)
            ON CONFLICT(topic_key) DO UPDATE SET
                label=excluded.label, last_updated_at=excluded.last_updated_at
            """,
            (topic_key, topic_id, topic.get("display_name") or topic_id, now, now),
        )
        connection.execute(
            """
            INSERT INTO work_topics(
                work_id, topic_key, score, is_primary, source,
                first_created_at, last_updated_at
            ) VALUES (?, ?, ?, ?, 'OpenAlex', ?, ?)
            ON CONFLICT(work_id, topic_key) DO UPDATE SET
                score=excluded.score, is_primary=excluded.is_primary,
                last_updated_at=excluded.last_updated_at
            """,
            (work_id, topic_key, topic.get("score"), int(topic_id == primary_topic_id), now, now),
        )
        if topic_key not in existing:
            repository.record_entity_change(
                connection, batch_id=batch_id, entity_type="topic_relation",
                entity_key=f"{work_id}|{topic_key}", change_type="inserted",
            )
    for topic_key in existing - expected:
        connection.execute(
            "DELETE FROM work_topics WHERE work_id=? AND topic_key=?", (work_id, topic_key)
        )
        repository.record_entity_change(
            connection, batch_id=batch_id, entity_type="topic_relation",
            entity_key=f"{work_id}|{topic_key}", change_type="deleted",
        )


def _upsert_collection_metadata(
    connection: Any, record: dict[str, Any], batch_id: str, now: str
) -> None:
    work_id = str(record["id"]).strip()
    primary_location = record.get("primary_location") or {}
    source = primary_location.get("source") or {}
    landing_page = primary_location.get("landing_page_url") or (
        record.get("best_oa_location") or {}
    ).get("landing_page_url")
    countries = sorted({
        str(institution.get("country_code"))
        for authorship in record.get("authorships") or []
        for institution in authorship.get("institutions") or []
        if institution.get("country_code")
    })
    primary_topic_id = str((record.get("primary_topic") or {}).get("id") or "").strip() or None
    connection.execute(
        """
        INSERT INTO work_collection_metadata(
            work_id, language, journal_name, landing_page_url,
            openalex_updated_date, openalex_created_date, primary_topic_id,
            countries_json, last_batch_id, source, first_collected_at, last_collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OpenAlex', ?, ?)
        ON CONFLICT(work_id) DO UPDATE SET
            language=excluded.language, journal_name=excluded.journal_name,
            landing_page_url=excluded.landing_page_url,
            openalex_updated_date=excluded.openalex_updated_date,
            openalex_created_date=excluded.openalex_created_date,
            primary_topic_id=excluded.primary_topic_id,
            countries_json=excluded.countries_json,
            last_batch_id=excluded.last_batch_id,
            last_collected_at=excluded.last_collected_at
        """,
        (
            work_id, record.get("language"), source.get("display_name"), landing_page,
            record.get("updated_date"), record.get("created_date"), primary_topic_id,
            canonical_json(countries), batch_id, now, now,
        ),
    )


def _normalize_doi(value: Any) -> str | None:
    if not value:
        return None
    doi = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi or None
