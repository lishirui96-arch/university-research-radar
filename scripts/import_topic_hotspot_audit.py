from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.topic_hotspots import import_audit_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the verified V1.3.4 Topic audit")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT)
    args = parser.parse_args()
    result = import_audit_files(args.source, args.database)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
