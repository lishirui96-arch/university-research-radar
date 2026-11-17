from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


CONFIG_DIRECTORIES = (
    "references/domain-profiles",
    "references/taxonomies",
    "references/quality-rubrics",
    "references/source-profiles",
)
REQUIRED_MATERIAL_FILES = (
    "references/domain-profiles/materials.md",
    "references/taxonomies/materials-topics.csv",
    "references/quality-rubrics/materials-evidence.md",
    "references/source-profiles/materials-sources.md",
)
MATERIAL_COLUMNS = {
    "topic_id",
    "domain",
    "label_zh",
    "label_en",
    "include_terms",
    "material_anchors",
    "process_terms",
    "property_terms",
    "application_terms",
    "exclude_terms",
    "classification_hints",
    "notes",
}


@dataclass
class SkillBundle:
    source: str
    root: Path
    fingerprint: str
    workflow_hash: str
    config_hash: str
    updated_at: datetime
    materials_topics: pd.DataFrame = field(default_factory=pd.DataFrame)
    files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    workflow_review_required: bool = False
    snapshot_updated: bool = False

    @property
    def status_label(self) -> str:
        if self.source == "snapshot":
            return "使用备用快照"
        if self.workflow_review_required:
            return "主流程待适配"
        if self.snapshot_updated:
            return "配置已自动同步"
        return "已同步"

    @property
    def material_options(self) -> list[str]:
        if self.materials_topics.empty:
            return []
        return self.materials_topics["label_zh"].dropna().astype(str).tolist()

    def material_query(self, label_zh: str) -> str:
        if self.materials_topics.empty:
            return label_zh
        selected = self.materials_topics[self.materials_topics["label_zh"] == label_zh]
        if selected.empty:
            return label_zh
        row = selected.iloc[0]
        return str(row.get("label_en") or row.get("label_zh") or label_zh)


def default_skill_root() -> Path:
    configured = os.environ.get("UNIVERSITY_RADAR_SKILL_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".agents" / "skills" / "university-research-radar"


def _tracked_files(root: Path) -> list[Path]:
    files: list[Path] = []
    skill_file = root / "SKILL.md"
    if skill_file.is_file():
        files.append(skill_file)
    for relative_dir in CONFIG_DIRECTORIES:
        directory = root / relative_dir
        if directory.is_dir():
            files.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _hash_files(root: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _single_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _validate(root: Path) -> tuple[bool, list[str], pd.DataFrame]:
    warnings: list[str] = []
    if not (root / "SKILL.md").is_file():
        warnings.append("缺少 SKILL.md")
    for relative in REQUIRED_MATERIAL_FILES:
        if not (root / relative).is_file():
            warnings.append(f"缺少 {relative}")

    topics_path = root / "references/taxonomies/materials-topics.csv"
    topics = pd.DataFrame()
    if topics_path.is_file():
        try:
            topics = pd.read_csv(topics_path)
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            warnings.append(f"材料词表无法读取：{exc}")
        else:
            missing = sorted(MATERIAL_COLUMNS - set(topics.columns))
            if missing:
                warnings.append(f"材料词表缺少字段：{', '.join(missing)}")
            if "topic_id" in topics and (
                topics["topic_id"].isna().any() or topics["topic_id"].duplicated().any()
            ):
                warnings.append("材料词表 topic_id 存在空值或重复")
            if "label_zh" in topics and topics["label_zh"].dropna().duplicated().any():
                warnings.append("材料词表 label_zh 存在重复")

    return not warnings, warnings, topics


def _build_bundle(root: Path, source: str) -> SkillBundle:
    valid, warnings, topics = _validate(root)
    if not valid:
        raise ValueError("；".join(warnings))
    files = _tracked_files(root)
    workflow_file = root / "SKILL.md"
    config_files = [path for path in files if path != workflow_file]
    timestamp = max(path.stat().st_mtime for path in files)
    return SkillBundle(
        source=source,
        root=root,
        fingerprint=_hash_files(root, files)[:12],
        workflow_hash=_single_hash(workflow_file),
        config_hash=_hash_files(root, config_files),
        updated_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
        materials_topics=topics,
        files=[path.relative_to(root).as_posix() for path in files],
    )


def _read_manifest(snapshot_root: Path) -> dict:
    manifest_path = snapshot_root / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def refresh_snapshot(skill_root: Path, snapshot_root: Path) -> dict:
    bundle = _build_bundle(skill_root, "live")
    snapshot_root.mkdir(parents=True, exist_ok=True)

    tracked_relatives = set(bundle.files)
    for path in _tracked_files(snapshot_root):
        relative = path.relative_to(snapshot_root).as_posix()
        if relative not in tracked_relatives:
            path.unlink()

    for relative in bundle.files:
        source = skill_root / relative
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "source_root": str(skill_root),
        "fingerprint": bundle.fingerprint,
        "workflow_hash": bundle.workflow_hash,
        "config_hash": bundle.config_hash,
        "files": bundle.files,
    }
    (snapshot_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_skill_bundle(skill_root: Path, snapshot_root: Path) -> SkillBundle:
    live_error = ""
    try:
        live = _build_bundle(skill_root, "live")
    except (OSError, ValueError) as exc:
        live = None
        live_error = str(exc)

    manifest = _read_manifest(snapshot_root)
    if live is not None:
        snapshot_workflow_hash = str(manifest.get("workflow_hash", ""))
        snapshot_config_hash = str(manifest.get("config_hash", ""))
        if not manifest:
            try:
                refresh_snapshot(skill_root, snapshot_root)
                live.snapshot_updated = True
            except OSError as exc:
                live.warnings.append(f"无法创建备用快照：{exc}")
        elif snapshot_workflow_hash != live.workflow_hash:
            live.workflow_review_required = True
            live.warnings.append("SKILL.md 主流程已变化，需要检查网页计算逻辑后再更新基准快照。")
        elif snapshot_config_hash != live.config_hash:
            try:
                refresh_snapshot(skill_root, snapshot_root)
                live.snapshot_updated = True
            except OSError as exc:
                live.warnings.append(f"配置已热加载，但备用快照更新失败：{exc}")
        return live

    try:
        snapshot = _build_bundle(snapshot_root, "snapshot")
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"实时 Skill 和备用快照均不可用。实时错误：{live_error}；快照错误：{exc}") from exc
    snapshot.warnings.append(f"实时 Skill 不可用，已回退到快照：{live_error}")
    return snapshot
