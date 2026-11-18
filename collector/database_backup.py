from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path


def create_database_backup(
    source: Path | str,
    backup_dir: Path | str,
    *,
    now: datetime | None = None,
    daily_retention: int = 14,
    weekly_retention: int = 8,
) -> dict[str, str | None]:
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Database does not exist: {source_path}")
    timestamp = now or datetime.now().astimezone()
    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    daily = destination_dir / f"daily-{timestamp.strftime('%Y%m%d-%H%M%S')}.db"
    _backup(source_path, daily)
    _verify(daily)

    weekly: Path | None = None
    if timestamp.weekday() == 0:
        iso_year, iso_week, _ = timestamp.isocalendar()
        weekly = destination_dir / f"weekly-{iso_year}-W{iso_week:02d}.db"
        if not weekly.exists():
            _backup(source_path, weekly)
            _verify(weekly)

    _rotate(destination_dir, "daily-*.db", daily_retention)
    _rotate(destination_dir, "weekly-*.db", weekly_retention)
    return {"daily": str(daily), "weekly": str(weekly) if weekly else None}


def restore_database_backup(
    backup: Path | str,
    destination: Path | str,
    *,
    overwrite: bool = False,
) -> Path:
    source_path = Path(backup)
    destination_path = Path(destination)
    if not source_path.is_file():
        raise FileNotFoundError(f"Backup does not exist: {source_path}")
    _verify(source_path)
    if destination_path.exists() and not overwrite:
        raise FileExistsError(
            f"Restore destination already exists: {destination_path}. "
            "Choose a new path or explicitly allow overwrite."
        )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_path, timeout=30)) as source_db:
        with closing(sqlite3.connect(destination_path, timeout=30)) as destination_db:
            source_db.backup(destination_db)
    _verify(destination_path)
    return destination_path


def _backup(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(source, timeout=30)) as source_db:
        with closing(sqlite3.connect(destination, timeout=30)) as backup_db:
            source_db.backup(backup_db)


def _verify(path: Path) -> None:
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok" or foreign_keys:
        raise RuntimeError(
            f"Backup verification failed for {path}: integrity={integrity}, "
            f"foreign_key_violations={len(foreign_keys)}"
        )


def _rotate(directory: Path, pattern: str, retention: int) -> None:
    if retention < 1:
        return
    files = sorted(
        directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True
    )
    for path in files[retention:]:
        path.unlink()
