from pathlib import Path

from skill_sync import default_skill_root, refresh_snapshot


app_dir = Path(__file__).parent
manifest = refresh_snapshot(default_skill_root(), app_dir / "skill_snapshot")
print(f"Snapshot updated: {manifest['fingerprint']}")
