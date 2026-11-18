from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.database_backup import create_database_backup


source = Path(os.environ.get("RADAR_DB_PATH", "persistent/data/radar.db"))
backup_dir = Path(os.environ.get("RADAR_BACKUP_DIR", "persistent/backups"))
retention = int(os.environ.get("RADAR_BACKUP_RETENTION", "14"))

if not source.is_file():
    raise SystemExit(f"Database does not exist: {source}")

result = create_database_backup(source, backup_dir, daily_retention=retention)
print(result["daily"])
