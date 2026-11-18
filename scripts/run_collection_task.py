from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.catalog_sync import sync_institutions, sync_topics
from collector.daily_collection import run_daily_collection
from collector.logging_config import configure_collection_logging
from collector.works_ingest import ingest_works_for_date


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one research-radar collection task.")
    parser.add_argument(
        "task", choices=("sync_topics", "sync_institutions", "daily_ingest", "daily_collection")
    )
    parser.add_argument("--db", default="persistent/data/radar.db")
    parser.add_argument("--logical-date")
    parser.add_argument("--publication-date")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--run-date")
    parser.add_argument("--trigger-kind", default="manual")
    parser.add_argument("--request-budget", type=int, default=9000)
    parser.add_argument("--backup-dir", default=str(ROOT / "persistent" / "backups"))
    parser.add_argument("--report-dir", default=str(ROOT / "logs" / "daily-collection"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    configure_collection_logging()
    db_path = Path(args.db)
    common = {
        "db_path": db_path,
        "max_pages": args.max_pages,
        "publish": not args.no_publish,
    }
    try:
        if args.task == "sync_topics":
            result = sync_topics(logical_date=args.logical_date, **common)
        elif args.task == "sync_institutions":
            result = sync_institutions(logical_date=args.logical_date, **common)
        elif args.task == "daily_ingest":
            publication_date = args.publication_date or (
                date.today() - timedelta(days=1)
            ).isoformat()
            result = ingest_works_for_date(
                publication_date=publication_date,
                db_path=db_path,
                max_pages=args.max_pages,
                publish=not args.no_publish,
            )
        else:
            result = run_daily_collection(
                db_path,
                run_date=date.fromisoformat(args.run_date) if args.run_date else None,
                trigger_kind=args.trigger_kind,
                request_budget=args.request_budget,
                report_dir=Path(args.report_dir),
                backup_dir=Path(args.backup_dir),
            )
    except Exception as exc:
        _write_report(
            args.task,
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
            },
        )
        raise
    payload = result.to_dict()
    _write_report(args.task, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _write_report(task: str, payload: dict[str, object]) -> Path:
    generated_at = datetime.now(timezone.utc)
    report = {
        "task": task,
        "generated_at": generated_at.isoformat(),
        "result": payload,
    }
    report_dir = ROOT / "logs" / "collection-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    destination = report_dir / f"{task}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination


if __name__ == "__main__":
    raise SystemExit(main())

