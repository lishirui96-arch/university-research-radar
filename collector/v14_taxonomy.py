from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from storage import initialize_database


TAXONOMY_VERSION = "openalex-taxonomy-2026-11-18-v1.4"
EFFECTIVE_DATE = "2026-11-18"
DOMAIN_ID = "3"
FIELD_NAMES_ZH = {
    "15": "化学工程",
    "16": "化学",
    "17": "计算机科学",
    "21": "能源",
    "22": "工程学",
    "25": "材料科学",
}
EXPECTED_FIELD_COUNTS = {
    "15": 24,
    "16": 119,
    "17": 265,
    "21": 44,
    "22": 467,
    "25": 144,
}
EXPECTED_TOPIC_COUNT = sum(EXPECTED_FIELD_COUNTS.values())
VERIFIED_TOPIC_NAMES_ZH = {
    "T10018": "电池材料研究进展",
    "T10030": "能源转换电催化剂",
    "T10033": "混凝土与水泥材料研究",
    "T10036": "先进神经网络应用",
    "T10063": "纳米颗粒药物递送",
    "T10078": "先进光催化技术",
    "T10179": "超级电容器材料与制备",
    "T10220": "机械故障诊断技术",
    "T10247": "钙钛矿材料及其应用",
    "T10281": "先进电池材料与技术",
    "T10338": "先进传感与能量采集材料",
}


def _identifier(value: Any) -> str:
    return str(value or "").rstrip("/").rsplit("/", 1)[-1]


def fetch_taxonomy(*, timeout: float = 30.0) -> list[dict[str, str]]:
    """Fetch Topic metadata only; this never queries or downloads Works."""
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    rows: list[dict[str, str]] = []
    for field_id in EXPECTED_FIELD_COUNTS:
        cursor = "*"
        while cursor:
            params = {
                "filter": f"field.id:{field_id}",
                "per-page": "200",
                "cursor": cursor,
            }
            if api_key:
                params["api_key"] = api_key
            request = Request(
                "https://api.openalex.org/topics?" + urlencode(params),
                headers={"User-Agent": "university-research-radar/1.4"},
            )
            with urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            for topic in payload.get("results") or []:
                subfield = topic.get("subfield") or {}
                field = topic.get("field") or {}
                domain = topic.get("domain") or {}
                rows.append(
                    {
                        "topic_id": _identifier(topic.get("id")),
                        "topic_name": str(topic.get("display_name") or "").strip(),
                        "subfield_id": _identifier(subfield.get("id")),
                        "subfield_name": str(subfield.get("display_name") or "").strip(),
                        "field_id": _identifier(field.get("id")),
                        "field_name": str(field.get("display_name") or "").strip(),
                        "domain_id": _identifier(domain.get("id")),
                        "domain_name": str(domain.get("display_name") or "").strip(),
                    }
                )
            cursor = str((payload.get("meta") or {}).get("next_cursor") or "")
    validate_taxonomy(rows)
    return rows


def validate_taxonomy(rows: list[dict[str, str]]) -> None:
    topic_ids = [row["topic_id"] for row in rows]
    if len(rows) != EXPECTED_TOPIC_COUNT or len(set(topic_ids)) != EXPECTED_TOPIC_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_TOPIC_COUNT} unique Topics, received {len(rows)} rows "
            f"and {len(set(topic_ids))} unique IDs"
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["field_id"]] = counts.get(row["field_id"], 0) + 1
        if row["domain_id"] != DOMAIN_ID:
            raise ValueError(f"Topic {row['topic_id']} is outside Physical Sciences")
        if not all(row.get(key) for key in (
            "topic_id", "topic_name", "subfield_id", "subfield_name",
            "field_id", "field_name", "domain_id", "domain_name",
        )):
            raise ValueError(f"Topic {row.get('topic_id')} has incomplete hierarchy data")
    if counts != EXPECTED_FIELD_COUNTS:
        raise ValueError(f"Unexpected Field counts: {counts}")


def import_taxonomy(database: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    validate_taxonomy(rows)
    initialize_database(database)
    now = datetime.now().astimezone().isoformat()
    connection = sqlite3.connect(database, timeout=30)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            connection.execute("UPDATE taxonomy_versions SET is_current=0")
            connection.execute(
                """
                INSERT INTO taxonomy_versions(
                    taxonomy_version, effective_date, source, topic_count,
                    field_count, is_current, imported_at
                ) VALUES (?, ?, 'OpenAlex Topics API', ?, ?, 1, ?)
                ON CONFLICT(taxonomy_version) DO UPDATE SET
                    topic_count=excluded.topic_count,
                    field_count=excluded.field_count,
                    is_current=1,
                    imported_at=excluded.imported_at
                """,
                (
                    TAXONOMY_VERSION,
                    EFFECTIVE_DATE,
                    EXPECTED_TOPIC_COUNT,
                    len(EXPECTED_FIELD_COUNTS),
                    now,
                ),
            )
            for field_id, count in EXPECTED_FIELD_COUNTS.items():
                field_name = next(
                    row["field_name"] for row in rows if row["field_id"] == field_id
                )
                connection.execute(
                    """
                    INSERT INTO field_scope_versions(
                        taxonomy_version, field_id, field_name, field_name_zh, topic_count
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(taxonomy_version, field_id) DO UPDATE SET
                        field_name=excluded.field_name,
                        field_name_zh=excluded.field_name_zh,
                        topic_count=excluded.topic_count
                    """,
                    (TAXONOMY_VERSION, field_id, field_name, FIELD_NAMES_ZH[field_id], count),
                )
            existing_names = {
                topic_id: topic_name_zh
                for topic_id, topic_name_zh in connection.execute(
                    "SELECT topic_id, topic_name_zh FROM openalex_topics "
                    "WHERE topic_name_zh IS NOT NULL AND TRIM(topic_name_zh)<>''"
                ).fetchall()
            }
            connection.execute(
                "DELETE FROM topic_taxonomy_versions WHERE taxonomy_version=?",
                (TAXONOMY_VERSION,),
            )
            connection.executemany(
                """
                INSERT INTO topic_taxonomy_versions(
                    taxonomy_version, topic_id, topic_name, topic_name_zh,
                    subfield_id, subfield_name, field_id, field_name,
                    domain_id, domain_name, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        TAXONOMY_VERSION,
                        row["topic_id"],
                        row["topic_name"],
                        VERIFIED_TOPIC_NAMES_ZH.get(
                            row["topic_id"], existing_names.get(row["topic_id"])
                        ),
                        row["subfield_id"],
                        row["subfield_name"],
                        row["field_id"],
                        row["field_name"],
                        row["domain_id"],
                        row["domain_name"],
                        now,
                    )
                    for row in rows
                ],
            )
    finally:
        connection.close()
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "topic_count": len(rows),
        "field_counts": EXPECTED_FIELD_COUNTS.copy(),
        "imported_at": now,
    }


def apply_verified_topic_translations(database: Path) -> int:
    """Apply reviewed Chinese display names without changing taxonomy or counts."""
    initialize_database(database)
    connection = sqlite3.connect(database, timeout=30)
    try:
        with connection:
            updated = 0
            for topic_id, topic_name_zh in VERIFIED_TOPIC_NAMES_ZH.items():
                cursor = connection.execute(
                    """
                    UPDATE topic_taxonomy_versions
                    SET topic_name_zh=?
                    WHERE taxonomy_version=? AND topic_id=?
                    """,
                    (topic_name_zh, TAXONOMY_VERSION, topic_id),
                )
                updated += cursor.rowcount
            return updated
    finally:
        connection.close()
