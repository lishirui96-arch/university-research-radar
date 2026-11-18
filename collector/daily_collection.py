from __future__ import annotations

import json
import math
import os
import socket
import uuid
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from collector.database_backup import create_database_backup
from collector.openalex_client import OpenAlexClient
from collector.works_ingest import WORK_SELECT, ingest_works_for_date
from repositories.collection_repository import CollectionRepository


WINDOW_OFFSETS = ((1, 10, "D-1"), (2, 20, "D-2"), (3, 30, "D-3"), (7, 70, "D-7"), (14, 140, "D-14"))
PREFLIGHT_SELECT = ("id",)


@dataclass(frozen=True)
class CollectionWindow:
    publication_date: str
    reasons: tuple[str, ...]
    priority: int


@dataclass(frozen=True)
class DailyCollectionResult:
    run_id: str
    run_date: str
    status: str
    backup_path: str
    windows: list[dict[str, Any]]
    request_count: int
    response_bytes: int
    retry_count: int
    rate_remaining: int | None
    report_json: str
    report_markdown: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_collection_windows(
    run_date: date,
    *,
    last_successful_run_date: date | None,
    catchup_limit_days: int = 30,
) -> list[CollectionWindow]:
    entries: dict[date, dict[str, Any]] = {}
    for offset, priority, reason in WINDOW_OFFSETS:
        target = run_date - timedelta(days=offset)
        entries[target] = {"reasons": [reason], "priority": priority}

    if last_successful_run_date and last_successful_run_date < run_date - timedelta(days=1):
        catchup_start = max(
            last_successful_run_date + timedelta(days=1),
            run_date - timedelta(days=catchup_limit_days),
        )
        cursor = catchup_start
        while cursor < run_date:
            item = entries.setdefault(cursor, {"reasons": [], "priority": 40})
            if "catch-up" not in item["reasons"]:
                item["reasons"].append("catch-up")
            item["priority"] = min(item["priority"], 40)
            cursor += timedelta(days=1)

    return [
        CollectionWindow(day.isoformat(), tuple(value["reasons"]), int(value["priority"]))
        for day, value in sorted(entries.items(), key=lambda pair: (pair[1]["priority"], pair[0]))
    ]


def run_daily_collection(
    db_path: Path | str,
    *,
    run_date: date | None = None,
    trigger_kind: str = "manual",
    request_budget: int = 9_000,
    quota_reserve: int = 100,
    catchup_limit_days: int = 30,
    report_dir: Path | str = "logs/daily-collection",
    backup_dir: Path | str = "persistent/backups",
    client_factory: Any = OpenAlexClient,
) -> DailyCollectionResult:
    local_now = datetime.now().astimezone()
    started_at = local_now.isoformat()
    local_date = run_date or local_now.date()
    run_id = f"daily-{local_date.isoformat()}-{uuid.uuid4().hex[:12]}"
    repository = CollectionRepository(db_path)
    lock_path = Path(db_path).parent / ".daily_collection.lock"
    with WorkerLock(lock_path):
        backups = create_database_backup(db_path, backup_dir, now=local_now)
        backup_path = str(backups["daily"])
        repository.create_daily_run(
            run_id=run_id,
            run_date=local_date.isoformat(),
            timezone_name=str(local_now.tzinfo),
            trigger_kind=trigger_kind,
            scheduled_for=f"{local_date.isoformat()}T09:00:00",
            request_budget=request_budget,
            backup_path=backup_path,
        )
        last_value = repository.last_successful_daily_run_date()
        last_success = date.fromisoformat(last_value) if last_value else None
        windows = build_collection_windows(
            local_date,
            last_successful_run_date=last_success,
            catchup_limit_days=catchup_limit_days,
        )
        outcomes: list[dict[str, Any]] = []
        total_requests = 0
        total_bytes = 0
        total_retries = 0
        rate_remaining: int | None = None
        completed = 0
        failed = 0
        skipped = 0
        error_text = ""
        for window in windows:
            repository.upsert_daily_window(
                run_id=run_id,
                publication_date=window.publication_date,
                reasons=list(window.reasons),
                priority=window.priority,
            )
        for index, window in enumerate(windows):
            outcome: dict[str, Any] = {
                "publication_date": window.publication_date,
                "reasons": list(window.reasons),
                "priority": window.priority,
            }
            try:
                preflight_client = client_factory()
                preflight_client.reset_stats()
                meta_count = _preflight_count(preflight_client, window.publication_date)
                preflight_requests = preflight_client.stats.request_count
                estimated_ingest = max(1, math.ceil(meta_count / 200))
                estimated_total = preflight_requests + estimated_ingest
                total_requests += preflight_requests
                total_bytes += preflight_client.stats.response_bytes
                total_retries += preflight_client.stats.retry_count
                rate_remaining = preflight_client.stats.rate_remaining
                repository.upsert_daily_window(
                    run_id=run_id,
                    publication_date=window.publication_date,
                    reasons=list(window.reasons),
                    priority=window.priority,
                    preflight_meta_count=meta_count,
                    estimated_requests=estimated_total,
                    status="pending",
                )
                available_budget = request_budget - total_requests
                quota_available = (
                    rate_remaining - quota_reserve
                    if rate_remaining is not None
                    else available_budget
                )
                if estimated_ingest > available_budget or estimated_ingest > quota_available:
                    reason = (
                        f"Skipped before ingest: estimated {estimated_ingest} requests, "
                        f"budget available {available_budget}, quota available {quota_available}."
                    )
                    repository.update_daily_window(
                        run_id=run_id,
                        publication_date=window.publication_date,
                        status="skipped",
                        skip_reason=reason,
                    )
                    outcome.update({
                        "status": "skipped",
                        "meta_count": meta_count,
                        "estimated_requests": estimated_total,
                        "skip_reason": reason,
                    })
                    outcomes.append(outcome)
                    skipped += 1
                    continue
                repository.update_daily_window(
                    run_id=run_id,
                    publication_date=window.publication_date,
                    status="running",
                )
                result = ingest_works_for_date(
                    db_path,
                    publication_date=window.publication_date,
                    client=client_factory(),
                    publish=True,
                    collection_run_id=f"{run_id}:{window.publication_date}",
                    daily_run_id=run_id,
                    local_run_date=local_date.isoformat(),
                    worker_id=f"{socket.gethostname()}:{run_id}",
                )
                total_requests += result.request_count
                total_bytes += result.response_bytes
                total_retries += result.retry_count
                rate_remaining = result.rate_remaining
                repository.update_daily_window(
                    run_id=run_id,
                    publication_date=window.publication_date,
                    status="succeeded",
                    job_id=result.job_id,
                    batch_id=result.batch_id,
                )
                outcome.update(result.to_dict())
                outcome["status"] = "succeeded"
                outcome["quality_status"] = "passed"
                outcome["preflight_request_count"] = preflight_requests
                completed += 1
            except Exception as exc:
                failed += 1
                error_text = str(exc)[:1000]
                repository.update_daily_window(
                    run_id=run_id,
                    publication_date=window.publication_date,
                    status="failed",
                    error=error_text,
                )
                outcome.update({
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": error_text,
                })
            outcomes.append(outcome)

        if completed == len(windows):
            status = "succeeded"
        elif completed or skipped:
            status = "partial"
        else:
            status = "failed"
        report_paths = _write_reports(
            Path(report_dir), run_id, local_date, started_at,
            datetime.now().astimezone().isoformat(), status, backup_path, outcomes,
            total_requests, total_bytes, total_retries, rate_remaining,
        )
        repository.finish_daily_run(
            run_id=run_id,
            status=status,
            window_count=len(windows),
            completed_windows=completed,
            failed_windows=failed,
            request_count=total_requests,
            response_bytes=total_bytes,
            retry_count=total_retries,
            rate_remaining=rate_remaining,
            report_path=str(report_paths["json"]),
            error=error_text,
        )
        return DailyCollectionResult(
            run_id=run_id,
            run_date=local_date.isoformat(),
            status=status,
            backup_path=backup_path,
            windows=outcomes,
            request_count=total_requests,
            response_bytes=total_bytes,
            retry_count=total_retries,
            rate_remaining=rate_remaining,
            report_json=str(report_paths["json"]),
            report_markdown=str(report_paths["markdown"]),
        )


def _preflight_count(client: OpenAlexClient, publication_date: str) -> int:
    parameters = {
        "filter": (
            f"from_publication_date:{publication_date},"
            f"to_publication_date:{publication_date},institutions.type:education"
        ),
        "per-page": 1,
    }
    page = client.get_page("works", params=parameters, select_fields=PREFLIGHT_SELECT)
    if page.total_count is None:
        raise RuntimeError("OpenAlex preflight response did not include meta.count.")
    return page.total_count


class WorkerLock(AbstractContextManager["WorkerLock"]):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "WorkerLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.handle.write(b"0")
            self.handle.flush()
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self.handle.close()
            raise RuntimeError("Another daily collection worker is already running.") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def _write_reports(
    directory: Path,
    run_id: str,
    run_date: date,
    started_at: str,
    completed_at: str,
    status: str,
    backup_path: str,
    windows: list[dict[str, Any]],
    request_count: int,
    response_bytes: int,
    retry_count: int,
    rate_remaining: int | None,
) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "run_date": run_date.isoformat(),
        "started_at": started_at,
        "completed_at": completed_at,
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": status,
        "backup_path": backup_path,
        "request_count": request_count,
        "response_bytes": response_bytes,
        "retry_count": retry_count,
        "rate_remaining": rate_remaining,
        "windows": windows,
    }
    json_path = directory / f"{run_id}.json"
    markdown_path = directory / f"{run_id}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        f"# Daily Collection Report {run_date.isoformat()}",
        "",
        f"- Run ID: `{run_id}`",
        f"- Status: `{status}`",
        f"- Started: `{started_at}`",
        f"- Completed: `{completed_at}`",
        f"- API requests: {request_count}",
        f"- Response bytes: {response_bytes}",
        f"- Retries: {retry_count}",
        f"- Remaining quota: {rate_remaining if rate_remaining is not None else '--'}",
        f"- Pre-run backup: `{backup_path}`",
        "",
        "| Publication date | Reason | Status | meta.count | Inserted | Updated | Unchanged | Stability | Published |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for item in windows:
        lines.append(
            "| {date} | {reason} | {status} | {meta} | {inserted} | {updated} | "
            "{unchanged} | {stability} | {published} |".format(
                date=item.get("publication_date", "--"),
                reason=", ".join(item.get("reasons") or []),
                status=item.get("status", "--"),
                meta=item.get("total_count", item.get("meta_count", "--")),
                inserted=item.get("inserted_works", 0),
                updated=item.get("updated_works", 0),
                unchanged=item.get("unchanged_works", 0),
                stability=item.get("stability_status", "--"),
                published=item.get("published", False),
            )
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
