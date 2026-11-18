from __future__ import annotations

import hashlib
import json
import logging
import socket
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from collector.openalex_client import OpenAlexClient
from repositories.collection_repository import (
    CollectionRepository,
    canonical_json,
    utc_now,
)


LOGGER = logging.getLogger(__name__)

TOPIC_SELECT = (
    "id",
    "display_name",
    "description",
    "works_count",
    "cited_by_count",
    "updated_date",
    "subfield",
    "field",
    "domain",
)

INSTITUTION_SELECT = (
    "id",
    "display_name",
    "display_name_acronyms",
    "display_name_alternatives",
    "ror",
    "country_code",
    "type",
    "homepage_url",
    "image_url",
    "works_count",
    "cited_by_count",
    "ids",
    "geo",
    "lineage",
    "updated_date",
)


@dataclass(frozen=True)
class SyncResult:
    job_id: str
    batch_id: str
    status: str
    total_count: int | None
    records_processed: int
    catalog_count: int
    request_count: int
    response_bytes: int
    retry_count: int
    rate_limit: int | None
    rate_remaining: int | None
    rate_reset_seconds: int | None
    resumed_from_page: int
    published: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sync_topics(
    db_path: Path | str,
    *,
    client: OpenAlexClient | None = None,
    logical_date: str | None = None,
    max_pages: int | None = None,
    publish: bool = True,
    worker_id: str | None = None,
) -> SyncResult:
    return _sync_catalog(
        db_path,
        job_type="sync_topics",
        endpoint="topics",
        parameters={},
        select_fields=TOPIC_SELECT,
        page_writer=_write_topics,
        catalog_counter=lambda connection: connection.execute(
            "SELECT COUNT(*) FROM topic_catalog_metadata"
        ).fetchone()[0],
        client=client,
        logical_date=logical_date,
        max_pages=max_pages,
        publish=publish,
        worker_id=worker_id,
    )


def sync_institutions(
    db_path: Path | str,
    *,
    client: OpenAlexClient | None = None,
    logical_date: str | None = None,
    max_pages: int | None = None,
    publish: bool = True,
    worker_id: str | None = None,
) -> SyncResult:
    return _sync_catalog(
        db_path,
        job_type="sync_institutions",
        endpoint="institutions",
        parameters={"filter": "type:education"},
        select_fields=INSTITUTION_SELECT,
        page_writer=_write_institutions,
        catalog_counter=lambda connection: connection.execute(
            "SELECT COUNT(*) FROM institution_catalog_metadata"
        ).fetchone()[0],
        client=client,
        logical_date=logical_date,
        max_pages=max_pages,
        publish=publish,
        worker_id=worker_id,
    )


def _sync_catalog(
    db_path: Path | str,
    *,
    job_type: str,
    endpoint: str,
    parameters: dict[str, Any],
    select_fields: tuple[str, ...],
    page_writer: Callable[[Any, list[dict[str, Any]], str, str], None],
    catalog_counter: Callable[[Any], int],
    client: OpenAlexClient | None,
    logical_date: str | None,
    max_pages: int | None,
    publish: bool,
    worker_id: str | None,
) -> SyncResult:
    repository = CollectionRepository(db_path)
    run_date = logical_date or date.today().isoformat()
    handle = repository.ensure_job(job_type=job_type, logical_date=run_date)
    checkpoint = repository.checkpoint(handle.job_id) or {}
    resumed_page = int(checkpoint.get("page_number") or 0)
    records_processed = int(checkpoint.get("records_processed") or 0)
    state = checkpoint.get("state") or {}
    total_count = state.get("total_count")
    cursor = checkpoint.get("cursor_value") or "*"

    if handle.status == "succeeded":
        batch_status = repository.batch_status(handle.batch_id)
        if publish and batch_status == "validated":
            repository.publish_batch(batch_id=handle.batch_id, snapshot_type=job_type)
            batch_status = "published"
        with repository.connection() as connection:
            catalog_count = int(catalog_counter(connection))
        return SyncResult(
            handle.job_id, handle.batch_id, "succeeded", total_count,
            records_processed, catalog_count, 0, 0, 0, None, None, None,
            resumed_page, batch_status == "published",
        )

    acquired, attempt_number = repository.acquire_job(
        handle.job_id, worker_id=worker_id or f"{socket.gethostname()}:{job_type}"
    )
    if not acquired or attempt_number is None:
        raise RuntimeError(f"Collection job {handle.job_id} is already leased or complete.")

    openalex = client or OpenAlexClient()
    openalex.reset_stats()
    requested_at = utc_now()
    page_number = resumed_page
    last_cursor = cursor
    complete = False
    try:
        for page in openalex.iter_cursor(
            endpoint,
            params=parameters,
            select_fields=select_fields,
            cursor=cursor,
            max_pages=max_pages,
        ):
            page_number += 1
            if total_count is None:
                total_count = page.total_count
            now = utc_now()
            with repository.connection() as connection:
                page_writer(connection, page.results, handle.batch_id, now)
                records_processed += len(page.results)
                last_cursor = page.next_cursor
                repository.save_checkpoint(
                    connection,
                    job_id=handle.job_id,
                    cursor=last_cursor,
                    page_number=page_number,
                    records_processed=records_processed,
                    state={"total_count": total_count, "complete": last_cursor is None},
                )
            LOGGER.info(
                "%s page=%s records=%s total=%s",
                job_type,
                page_number,
                records_processed,
                total_count,
            )
            if last_cursor is None:
                complete = True
                break

        with repository.connection() as connection:
            catalog_count = int(catalog_counter(connection))
        repository.record_query_audit(
            batch_id=handle.batch_id,
            job_id=handle.job_id,
            endpoint=endpoint,
            parameters=parameters,
            select_fields=select_fields,
            requested_at=requested_at,
            completed_at=utc_now(),
            total_count=total_count,
            sampled_count=records_processed,
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
            return SyncResult(
                handle.job_id, handle.batch_id, "pending", total_count,
                records_processed, catalog_count, openalex.stats.request_count,
                openalex.stats.response_bytes, openalex.stats.retry_count,
                openalex.stats.rate_limit, openalex.stats.rate_remaining,
                openalex.stats.rate_reset_seconds, resumed_page, False,
            )

        counts_match = total_count is not None and catalog_count == total_count
        repository.add_quality_report(
            batch_id=handle.batch_id,
            check_name=f"{job_type}_count_matches_meta",
            severity="error",
            status="passed" if counts_match else "failed",
            expected={"meta_count": total_count},
            actual={"catalog_count": catalog_count},
            details="Catalog row count must equal the OpenAlex meta.count for this scope.",
        )
        if not counts_match:
            raise RuntimeError(
                f"{job_type} count mismatch: catalog={catalog_count}, meta={total_count}."
            )
        repository.mark_batch_validated(
            handle.batch_id,
            {
                "total_count": total_count,
                "catalog_count": catalog_count,
                "request_count": openalex.stats.request_count,
                "response_bytes": openalex.stats.response_bytes,
            },
        )
        if publish:
            repository.publish_batch(batch_id=handle.batch_id, snapshot_type=job_type)
        repository.finish_attempt(
            job_id=handle.job_id,
            attempt_number=attempt_number,
            success=True,
            request_count=openalex.stats.request_count,
            response_bytes=openalex.stats.response_bytes,
            retry_count=openalex.stats.retry_count,
        )
        return SyncResult(
            handle.job_id, handle.batch_id, "succeeded", total_count,
            records_processed, catalog_count, openalex.stats.request_count,
            openalex.stats.response_bytes, openalex.stats.retry_count,
            openalex.stats.rate_limit, openalex.stats.rate_remaining,
            openalex.stats.rate_reset_seconds, resumed_page, publish,
        )
    except Exception as exc:
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


def _write_topics(connection: Any, records: list[dict[str, Any]], batch_id: str, now: str) -> None:
    for record in records:
        openalex_id = str(record.get("id") or "").strip()
        if not openalex_id:
            continue
        topic_key = f"openalex:{openalex_id.rsplit('/', 1)[-1]}"
        label = str(record.get("display_name") or openalex_id)
        connection.execute(
            """
            INSERT INTO topics(
                topic_key, openalex_topic_id, label, topic_kind, description,
                source, first_created_at, last_updated_at
            ) VALUES (?, ?, ?, 'openalex', ?, 'OpenAlex', ?, ?)
            ON CONFLICT(topic_key) DO UPDATE SET
                openalex_topic_id=excluded.openalex_topic_id,
                label=excluded.label, description=excluded.description,
                last_updated_at=excluded.last_updated_at
            """,
            (topic_key, openalex_id, label, record.get("description"), now, now),
        )
        metadata = {
            "subfield": record.get("subfield"),
            "field": record.get("field"),
            "domain": record.get("domain"),
            "works_count": record.get("works_count"),
            "cited_by_count": record.get("cited_by_count"),
            "updated_date": record.get("updated_date"),
        }
        metadata_json = canonical_json(metadata)
        metadata_hash = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
        subfield = record.get("subfield") or {}
        field = record.get("field") or {}
        domain = record.get("domain") or {}
        connection.execute(
            """
            INSERT INTO topic_catalog_metadata(
                topic_key, subfield_id, subfield_name, field_id, field_name,
                domain_id, domain_name, works_count, cited_by_count,
                openalex_updated_date, metadata_hash, source,
                first_collected_at, last_collected_at, last_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OpenAlex', ?, ?, ?)
            ON CONFLICT(topic_key) DO UPDATE SET
                subfield_id=excluded.subfield_id, subfield_name=excluded.subfield_name,
                field_id=excluded.field_id, field_name=excluded.field_name,
                domain_id=excluded.domain_id, domain_name=excluded.domain_name,
                works_count=excluded.works_count, cited_by_count=excluded.cited_by_count,
                openalex_updated_date=excluded.openalex_updated_date,
                metadata_hash=excluded.metadata_hash,
                last_collected_at=excluded.last_collected_at,
                last_batch_id=excluded.last_batch_id
            """,
            (
                topic_key, subfield.get("id"), subfield.get("display_name"),
                field.get("id"), field.get("display_name"), domain.get("id"),
                domain.get("display_name"), record.get("works_count"),
                record.get("cited_by_count"), record.get("updated_date"),
                metadata_hash, now, now, batch_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO topic_catalog_history(
                topic_key, metadata_hash, metadata_json, valid_from,
                last_seen_at, source, batch_id
            ) VALUES (?, ?, ?, ?, ?, 'OpenAlex', ?)
            ON CONFLICT(topic_key, metadata_hash) DO UPDATE SET
                last_seen_at=excluded.last_seen_at, batch_id=excluded.batch_id
            """,
            (topic_key, metadata_hash, metadata_json, now, now, batch_id),
        )


def _write_institutions(
    connection: Any, records: list[dict[str, Any]], batch_id: str, now: str
) -> None:
    for record in records:
        institution_id = str(record.get("id") or "").strip()
        if not institution_id:
            continue
        display_name = str(record.get("display_name") or institution_id)
        connection.execute(
            """
            INSERT INTO institutions(
                openalex_institution_id, display_name, country_code,
                institution_type, ror, source, first_created_at, last_updated_at
            ) VALUES (?, ?, ?, ?, ?, 'OpenAlex', ?, ?)
            ON CONFLICT(openalex_institution_id) DO UPDATE SET
                display_name=excluded.display_name,
                country_code=excluded.country_code,
                institution_type=excluded.institution_type,
                ror=excluded.ror, last_updated_at=excluded.last_updated_at
            """,
            (
                institution_id, display_name, record.get("country_code"),
                record.get("type"), record.get("ror"), now, now,
            ),
        )
        metadata = {
            "homepage_url": record.get("homepage_url"),
            "image_url": record.get("image_url"),
            "works_count": record.get("works_count"),
            "cited_by_count": record.get("cited_by_count"),
            "updated_date": record.get("updated_date"),
            "ids": record.get("ids") or {},
            "geo": record.get("geo") or {},
        }
        metadata_hash = hashlib.sha256(canonical_json(metadata).encode("utf-8")).hexdigest()
        connection.execute(
            """
            INSERT INTO institution_catalog_metadata(
                institution_id, homepage_url, image_url, works_count,
                cited_by_count, openalex_updated_date, geo_json, ids_json,
                metadata_hash, source, first_collected_at, last_collected_at,
                last_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OpenAlex', ?, ?, ?)
            ON CONFLICT(institution_id) DO UPDATE SET
                homepage_url=excluded.homepage_url, image_url=excluded.image_url,
                works_count=excluded.works_count, cited_by_count=excluded.cited_by_count,
                openalex_updated_date=excluded.openalex_updated_date,
                geo_json=excluded.geo_json, ids_json=excluded.ids_json,
                metadata_hash=excluded.metadata_hash,
                last_collected_at=excluded.last_collected_at,
                last_batch_id=excluded.last_batch_id
            """,
            (
                institution_id, record.get("homepage_url"), record.get("image_url"),
                record.get("works_count"), record.get("cited_by_count"),
                record.get("updated_date"), canonical_json(record.get("geo") or {}),
                canonical_json(record.get("ids") or {}), metadata_hash, now, now,
                batch_id,
            ),
        )
        aliases = [(display_name, "display_name")]
        aliases.extend((str(value), "acronym") for value in record.get("display_name_acronyms") or [])
        aliases.extend((str(value), "alternative") for value in record.get("display_name_alternatives") or [])
        for alias, alias_type in aliases:
            normalized = " ".join(alias.casefold().split())
            if not normalized:
                continue
            connection.execute(
                """
                INSERT INTO institution_aliases(
                    institution_id, alias, normalized_alias, alias_type, source,
                    first_collected_at, last_collected_at, last_batch_id
                ) VALUES (?, ?, ?, ?, 'OpenAlex', ?, ?, ?)
                ON CONFLICT(institution_id, normalized_alias, source) DO UPDATE SET
                    alias=excluded.alias, alias_type=excluded.alias_type,
                    last_collected_at=excluded.last_collected_at,
                    last_batch_id=excluded.last_batch_id
                """,
                (institution_id, alias, normalized, alias_type, now, now, batch_id),
            )
        for order, ancestor in enumerate(record.get("lineage") or []):
            ancestor_id = str(ancestor or "").strip()
            if not ancestor_id:
                continue
            connection.execute(
                """
                INSERT INTO institution_lineage(
                    institution_id, ancestor_institution_id, lineage_order, source,
                    first_collected_at, last_collected_at, last_batch_id
                ) VALUES (?, ?, ?, 'OpenAlex', ?, ?, ?)
                ON CONFLICT(institution_id, ancestor_institution_id) DO UPDATE SET
                    lineage_order=excluded.lineage_order,
                    last_collected_at=excluded.last_collected_at,
                    last_batch_id=excluded.last_batch_id
                """,
                (institution_id, ancestor_id, order, now, now, batch_id),
            )

