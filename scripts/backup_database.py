from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path


source = Path(os.environ.get("RADAR_DB_PATH", "persistent/data/radar.db"))
backup_dir = Path(os.environ.get("RADAR_BACKUP_DIR", "persistent/backups"))
retention = int(os.environ.get("RADAR_BACKUP_RETENTION", "30"))

if not source.is_file():
    raise SystemExit(f"Database does not exist: {source}")

backup_dir.mkdir(parents=True, exist_ok=True)
destination = backup_dir / f"radar-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"

with sqlite3.connect(source, timeout=30) as source_db:
    with sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)

backups = sorted(backup_dir.glob("radar-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
for old_backup in backups[retention:]:
    old_backup.unlink()

print(destination)
