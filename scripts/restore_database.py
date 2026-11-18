from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.database_backup import restore_database_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a verified radar database backup.")
    parser.add_argument("backup")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    destination = restore_database_backup(
        args.backup, args.destination, overwrite=args.overwrite
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
