from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.topic_hotspot_updater import run_daily_update
from storage import database_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Update and atomically publish Topic hotspots")
    parser.add_argument("--database", type=Path, default=database_path())
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    print(json.dumps(run_daily_update(args.database, args.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
