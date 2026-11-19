from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from collector.v14_daily_backfill import run_v14_full_backfill


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill all V1.4 Topic daily counts")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 11, 18))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    def show_progress(item: dict[str, object]) -> None:
        completed = int(item["completed_now"])
        total = int(item["target_dates"])
        if completed == 1 or completed % 10 == 0 or completed == total:
            print(json.dumps(item, ensure_ascii=False), flush=True)

    result = run_v14_full_backfill(
        args.database,
        end_date=args.end_date,
        workers=args.workers,
        progress=show_progress,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
