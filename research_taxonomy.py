from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_TAXONOMY_PATH = Path(__file__).parent / "config" / "research_taxonomy.json"


def load_research_taxonomy(path: Path | None = None) -> dict[str, Any]:
    source = path or DEFAULT_TAXONOMY_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    domains = payload.get("domains")
    if not isinstance(domains, list) or not domains:
        raise ValueError("Research taxonomy must contain at least one domain.")

    seen: set[str] = set()
    for domain in domains:
        _require_unique_id(domain, seen, "domain")
        directions = domain.get("directions")
        if not isinstance(directions, list) or not directions:
            raise ValueError(f"Domain {domain['id']} has no research directions.")
        for direction in directions:
            _require_unique_id(direction, seen, "direction")
            technologies = direction.get("technologies")
            if not isinstance(technologies, list) or not technologies:
                raise ValueError(f"Direction {direction['id']} has no technologies.")
            for technology in technologies:
                _require_unique_id(technology, seen, "technology")
                technology.setdefault("aliases", [])
    return payload


def _require_unique_id(item: dict[str, Any], seen: set[str], kind: str) -> None:
    item_id = str(item.get("id") or "").strip()
    label = str(item.get("label") or "").strip()
    if not item_id or not label:
        raise ValueError(f"Every {kind} requires a non-empty id and label.")
    if item_id in seen:
        raise ValueError(f"Duplicate taxonomy id: {item_id}")
    seen.add(item_id)


def find_domain(taxonomy: dict[str, Any], domain_id: str) -> dict[str, Any]:
    return next(item for item in taxonomy["domains"] if item["id"] == domain_id)


def find_direction(domain: dict[str, Any], direction_id: str) -> dict[str, Any]:
    return next(item for item in domain["directions"] if item["id"] == direction_id)
