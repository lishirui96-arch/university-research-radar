from __future__ import annotations

import argparse
from pathlib import Path

from collector.v14_taxonomy import fetch_taxonomy, import_taxonomy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the frozen V1.4 OpenAlex Topic taxonomy (metadata only)."
    )
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    rows = fetch_taxonomy()
    result = import_taxonomy(args.database, rows)
    print(
        f"Imported {result['topic_count']:,} Topics as "
        f"{result['taxonomy_version']} into {args.database.resolve()}"
    )


if __name__ == "__main__":
    main()
