from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from collector.v14_taxonomy import VERIFIED_TOPIC_NAMES_ZH


CATALOG_PATH = Path(__file__).resolve().parent / "config" / "v14_topic_names_zh.csv"
STATUS_LABELS = {
    "verified": "已审核",
    "candidate": "中文候选（待审核）",
    "untranslated": "未翻译",
}


@lru_cache(maxsize=1)
def load_topic_translation_catalog() -> dict[str, dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return {}
    frame = pd.read_csv(CATALOG_PATH, dtype="string", encoding="utf-8-sig").fillna("")
    return {
        str(row["topic_id"]): row
        for row in frame.to_dict("records")
    }


def topic_translation(
    topic_id: Any,
    topic_name: Any,
    stored_name_zh: Any = None,
) -> dict[str, str]:
    key = str(topic_id)
    verified = VERIFIED_TOPIC_NAMES_ZH.get(key)
    if verified:
        return {
            "topic_name_zh": verified,
            "translation_status": "verified",
            "translation_status_label": STATUS_LABELS["verified"],
            "translation_source": "existing_manual_review",
            "reviewed_at": "2026-11-18",
        }
    catalog = load_topic_translation_catalog().get(key)
    if catalog and str(catalog.get("topic_name_zh", "")).strip():
        status = str(catalog.get("translation_status") or "candidate")
        return {
            "topic_name_zh": str(catalog["topic_name_zh"]),
            "translation_status": status,
            "translation_status_label": STATUS_LABELS.get(status, status),
            "translation_source": str(catalog.get("translation_source", "")),
            "reviewed_at": str(catalog.get("reviewed_at", "")),
        }
    if pd.notna(stored_name_zh) and str(stored_name_zh).strip():
        return {
            "topic_name_zh": str(stored_name_zh),
            "translation_status": "verified",
            "translation_status_label": STATUS_LABELS["verified"],
            "translation_source": "database_manual_review",
            "reviewed_at": "",
        }
    return {
        "topic_name_zh": str(topic_name),
        "translation_status": "untranslated",
        "translation_status_label": STATUS_LABELS["untranslated"],
        "translation_source": "",
        "reviewed_at": "",
    }


def topic_display_name(row: pd.Series | dict[str, Any]) -> str:
    topic_id = row.get("topic_id")
    if topic_id is None and isinstance(row, pd.Series):
        topic_id = row.name
    return topic_translation(
        topic_id,
        row.get("topic_name", ""),
        row.get("topic_name_zh"),
    )["topic_name_zh"]
