from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from collector.regional_v15 import run_regional_backfill


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill CN and US V1.5 Topic rankings and daily series."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--ranking-date", required=True, type=date.fromisoformat)
    parser.add_argument("--batch-id")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    def progress(record: dict[str, object]) -> None:
        print(json.dumps(record, ensure_ascii=False), flush=True)

    result = run_regional_backfill(
        args.database,
        ranking_date=args.ranking_date,
        batch_id=args.batch_id,
        workers=args.workers,
        progress=progress,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
