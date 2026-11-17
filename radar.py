from __future__ import annotations

import math
import re
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests


OPENALEX_URL = "https://api.openalex.org/works"
EUROPE_CODES = (
    "GB", "DE", "FR", "IT", "ES", "NL", "CH", "SE", "NO", "DK", "FI",
    "BE", "AT", "PT", "IE", "PL", "CZ", "GR", "RO", "HU", "SI", "SK",
    "HR", "EE", "LV", "LT", "BG", "LU", "IS",
)
REGION_CODES = {
    "中国内地": ("CN",),
    "美国": ("US",),
    "欧洲": EUROPE_CODES,
}

GENERIC_HEAT_WEIGHTS = {
    "momentum_score": 0.25,
    "acceleration_score": 0.15,
    "group_breadth_score": 0.20,
    "institution_diffusion_score": 0.15,
    "quality_score": 0.10,
    "industry_linkage_score": 0.15,
}
MATERIAL_HEAT_WEIGHTS = {
    "momentum_score": 0.25,
    "acceleration_score": 0.15,
    "group_breadth_score": 0.10,
    "institution_diffusion_score": 0.10,
    "quality_score": 0.25,
    "industry_linkage_score": 0.15,
}


class RadarAPIError(RuntimeError):
    pass


def split_terms(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [term.strip() for term in re.split(r"[|;；\n]+", str(value)) if term.strip()]


def _quote_term(term: str) -> str:
    escaped = term.replace('"', "")
    return f'"{escaped}"' if " " in escaped or "-" in escaped else escaped


def compile_topic_query(
    topic: dict[str, Any],
    custom_query: str = "",
    extra_terms: str = "",
    extra_excludes: str = "",
) -> str:
    """Build a reproducible Boolean query from a controlled topic definition."""
    if custom_query.strip():
        include = [custom_query.strip(), *split_terms(extra_terms)]
    else:
        include = [*split_terms(topic.get("include_terms")), *split_terms(extra_terms)]
        if not include:
            include = [str(topic.get("label_en") or topic.get("label_zh") or "").strip()]

    include = list(dict.fromkeys(term for term in include if term))[:12]
    include_clause = " OR ".join(_quote_term(term) for term in include)
    if len(include) > 1:
        include_clause = f"({include_clause})"

    material_anchors = split_terms(topic.get("material_anchors"))[:10]
    if material_anchors:
        anchor_clause = " OR ".join(_quote_term(term) for term in material_anchors)
        include_clause = f"{include_clause} AND ({anchor_clause})"

    excludes = list(
        dict.fromkeys(
            [*split_terms(topic.get("exclude_terms")), *split_terms(extra_excludes)]
        )
    )[:10]
    if excludes:
        include_clause += " NOT (" + " OR ".join(_quote_term(term) for term in excludes) + ")"
    return include_clause


def build_time_windows(current_start: date, current_end: date) -> dict[str, tuple[date, date]]:
    if current_start > current_end:
        raise ValueError("Current window start must not be after end.")
    window_days = (current_end - current_start).days + 1
    windows: dict[str, tuple[date, date]] = {"current": (current_start, current_end)}
    cursor_end = current_start - timedelta(days=1)
    for index in range(1, 4):
        cursor_start = cursor_end - timedelta(days=window_days - 1)
        windows[f"baseline_{index}"] = (cursor_start, cursor_end)
        cursor_end = cursor_start - timedelta(days=1)

    recent_days = max(1, round(window_days * 0.25))
    recent_start = current_end - timedelta(days=recent_days - 1)
    windows["recent"] = (recent_start, current_end)
    if recent_start > current_start:
        windows["previous"] = (current_start, recent_start - timedelta(days=1))
    else:
        windows["previous"] = (current_start, current_end)
    return windows


def count_openalex(
    query: str,
    from_date: date,
    to_date: date,
    region: str,
    api_key: str | None = None,
) -> int:
    codes = REGION_CODES[region]
    filters = ",".join(
        [
            f"from_publication_date:{from_date.isoformat()}",
            f"to_publication_date:{to_date.isoformat()}",
            f"authorships.institutions.country_code:{'|'.join(codes)}",
            "authorships.institutions.type:education",
        ]
    )
    payload = _request_json(
        {"search": query, "filter": filters, "per-page": 1, "select": "id"},
        api_key,
    )
    return int(payload.get("meta", {}).get("count", 0))


def _request_json(params: dict[str, Any], api_key: str | None) -> dict[str, Any]:
    request_params = dict(params)
    if api_key:
        request_params["api_key"] = api_key

    headers = {"User-Agent": "UniversityResearchRadar/0.1 (research dashboard)"}
    last_error = ""
    for attempt in range(2):
        try:
            response = requests.get(
                OPENALEX_URL,
                params=request_params,
                headers=headers,
                timeout=35,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt == 0:
                time.sleep(1.5)
                continue
            raise RadarAPIError(f"连接 OpenAlex 失败：{exc}") from exc

        if response.status_code == 429:
            retry_after = min(int(response.headers.get("Retry-After", "3")), 10)
            last_error = "OpenAlex 当前触发访问频率限制"
            if attempt == 0:
                time.sleep(retry_after)
                continue
            raise RadarAPIError(
                "OpenAlex 当前限制匿名检索。稍后重试，或在左侧填入免费的 OpenAlex API key。"
            )
        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise RadarAPIError(f"OpenAlex 返回 {response.status_code}：{detail}")
        return response.json()

    raise RadarAPIError(last_error or "OpenAlex 请求失败")


def fetch_openalex_region(
    query: str,
    from_date: date,
    to_date: date,
    region: str,
    max_records: int,
    api_key: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    codes = REGION_CODES[region]
    country_filter = "|".join(codes)
    filters = ",".join(
        [
            f"from_publication_date:{from_date.isoformat()}",
            f"to_publication_date:{to_date.isoformat()}",
            f"authorships.institutions.country_code:{country_filter}",
            "authorships.institutions.type:education",
        ]
    )
    cursor = "*"
    records: list[dict[str, Any]] = []
    total_count = 0

    while len(records) < max_records and cursor:
        page_size = min(200, max_records - len(records))
        payload = _request_json(
            {
                "search": query,
                "filter": filters,
                "per-page": page_size,
                "cursor": cursor,
                "select": (
                    "id,doi,display_name,publication_date,type,cited_by_count,"
                    "primary_topic,topics,keywords,authorships,primary_location,open_access"
                ),
            },
            api_key,
        )
        total_count = int(payload.get("meta", {}).get("count", 0))
        batch = payload.get("results", [])
        if not batch:
            break
        records.extend(_parse_work(work, region, set(codes)) for work in batch)
        cursor = payload.get("meta", {}).get("next_cursor")

    frame = pd.DataFrame(records)
    if not frame.empty:
        frame["publication_date"] = pd.to_datetime(frame["publication_date"], errors="coerce")
    meta = {
        "region": region,
        "total_count": total_count,
        "sample_count": len(frame),
        "truncated": total_count > len(frame),
    }
    return frame, meta


def _parse_work(work: dict[str, Any], region: str, country_codes: set[str]) -> dict[str, Any]:
    target_authors: list[dict[str, Any]] = []
    author_names: list[str] = []
    institutions: list[str] = []

    for authorship in work.get("authorships") or []:
        author_name = (authorship.get("author") or {}).get("display_name", "")
        if author_name:
            author_names.append(author_name)
        target_institutions = [
            inst
            for inst in authorship.get("institutions") or []
            if inst.get("country_code") in country_codes and inst.get("type") == "education"
        ]
        if target_institutions:
            target_authors.append(
                {
                    "name": author_name,
                    "is_corresponding": bool(authorship.get("is_corresponding")),
                    "institutions": target_institutions,
                }
            )
            institutions.extend(
                inst.get("display_name", "") for inst in target_institutions if inst.get("display_name")
            )

    corresponding = [item for item in target_authors if item["is_corresponding"]]
    leader_record = corresponding[0] if corresponding else (target_authors[-1] if target_authors else None)
    leader = leader_record["name"] if leader_record else "待核验"
    institution = (
        leader_record["institutions"][0].get("display_name", "待核验")
        if leader_record
        else (institutions[0] if institutions else "待核验")
    )
    confidence = "中" if corresponding else "低"
    attribution = "通讯作者与高校署名共同指向" if corresponding else "末位署名作者线索，尚未用官网核验"

    topic = work.get("primary_topic") or {}
    if not topic and work.get("topics"):
        topic = work["topics"][0]
    source = ((work.get("primary_location") or {}).get("source") or {})
    work_id = work.get("id", "")
    doi = work.get("doi") or ""
    link = doi or work_id

    return {
        "work_id": work_id.rsplit("/", 1)[-1],
        "title": work.get("display_name") or "未命名成果",
        "publication_date": work.get("publication_date"),
        "work_type": work.get("type") or "unknown",
        "source_type": source.get("type") or "unknown",
        "venue": source.get("display_name") or "",
        "citations": int(work.get("cited_by_count") or 0),
        "doi": doi,
        "link": link,
        "is_open_access": bool((work.get("open_access") or {}).get("is_oa")),
        "topic": topic.get("display_name") or "待分类",
        "subfield": (topic.get("subfield") or {}).get("display_name") or "",
        "field": (topic.get("field") or {}).get("display_name") or "",
        "region": region,
        "institution": institution,
        "institutions": "；".join(dict.fromkeys(institutions)),
        "authors": "；".join(author_names),
        "leader": leader,
        "group_name": f"{leader} 候选课题组" if leader != "待核验" else "待核验合作簇",
        "group_confidence": confidence,
        "attribution_basis": attribution,
    }


def _bounded_growth_score(growth: float, scale: float = 1.0) -> float:
    if pd.isna(growth):
        return 50.0
    return float(max(0.0, min(100.0, 50.0 + 50.0 * math.tanh(growth / scale))))


def _momentum_score(current_count: int, growth: float) -> float:
    scale_score = min(100.0, 25.0 * math.log10(current_count + 1))
    growth_score = _bounded_growth_score(growth)
    return 0.45 * scale_score + 0.55 * growth_score


def _trend_label(
    current_count: int,
    baseline_mean: float,
    growth: float,
    acceleration: float,
    institution_count: int,
) -> str:
    if current_count < 5:
        return "证据不足"
    if baseline_mean < 2 and current_count >= 5:
        return "新兴方向"
    if growth >= 0.20 and acceleration >= 0 and institution_count >= 3:
        return "上升热点"
    if growth <= -0.20 or acceleration <= -0.25:
        return "降温方向"
    if institution_count <= 2:
        return "集中型热点"
    return "存量热门"


def build_scan_radar(
    aggregate_rows: list[dict[str, Any]],
    works: pd.DataFrame,
    metadata: list[dict[str, Any]],
    current_start: date,
    current_end: date,
    run_mode: str,
    domain_profile: str,
    query_log: list[dict[str, Any]],
) -> dict[str, Any]:
    topics = pd.DataFrame(aggregate_rows)
    if topics.empty:
        result = empty_radar(metadata)
        result.update(
            {
                "run_mode": run_mode,
                "domain_profile": domain_profile,
                "query_log": query_log,
                "current_start": current_start,
                "current_end": current_end,
            }
        )
        return result

    works = works.copy()
    if not works.empty:
        works["publication_date"] = pd.to_datetime(works["publication_date"], errors="coerce")

    windows = build_time_windows(current_start, current_end)
    current_days = (current_end - current_start).days + 1
    recent_days = (windows["recent"][1] - windows["recent"][0]).days + 1
    previous_days = (windows["previous"][1] - windows["previous"][0]).days + 1

    enriched_rows: list[dict[str, Any]] = []
    weights = MATERIAL_HEAT_WEIGHTS if domain_profile == "材料科学" else GENERIC_HEAT_WEIGHTS
    for row in topics.to_dict("records"):
        baseline_values = [float(row.get(f"baseline_{index}_count", 0)) for index in range(1, 4)]
        baseline_mean = sum(baseline_values) / 3
        current_count = int(row.get("current_count", 0))
        growth = (current_count - baseline_mean) / baseline_mean if baseline_mean else math.nan
        recent_rate = float(row.get("recent_count", 0)) / max(recent_days, 1)
        previous_rate = float(row.get("previous_count", 0)) / max(previous_days, 1)
        acceleration = (recent_rate - previous_rate) / previous_rate if previous_rate else math.nan

        topic_works = pd.DataFrame()
        if not works.empty:
            topic_works = works[
                (works["region"] == row["region"]) & (works["topic"] == row["topic"])
            ]
        institution_count = int(topic_works["institution"].nunique()) if not topic_works.empty else 0
        peer_share = (
            float(topic_works["source_type"].isin(["journal", "conference"]).mean())
            if not topic_works.empty
            else math.nan
        )
        eligible_groups = pd.DataFrame()
        if not topic_works.empty:
            eligible_groups = topic_works[topic_works["group_confidence"].isin(["高", "中高"])]
        group_count = int(eligible_groups["group_name"].nunique()) if not eligible_groups.empty else 0

        components: dict[str, float] = {
            "momentum_score": _momentum_score(current_count, growth),
            "acceleration_score": _bounded_growth_score(acceleration),
            "group_breadth_score": math.nan,
            "institution_diffusion_score": min(100.0, institution_count / 20 * 100),
            "quality_score": peer_share * 100 if not pd.isna(peer_share) else math.nan,
            "industry_linkage_score": math.nan,
        }
        available_weight = sum(
            weight for component, weight in weights.items() if not pd.isna(components[component])
        )
        score = (
            sum(
                components[component] * weight
                for component, weight in weights.items()
                if not pd.isna(components[component])
            )
            / available_weight
            if available_weight
            else math.nan
        )
        sample_count = len(topic_works)
        sample_coverage = min(1.0, sample_count / current_count) if current_count else 0.0
        confidence_score = 100 * (
            0.45 * sample_coverage
            + 0.25 * (1.0 if row.get("query_string") else 0.0)
            + 0.20 * (1.0 if not pd.isna(peer_share) else 0.0)
            + 0.10 * (1.0 if group_count else 0.0)
        )
        enriched_rows.append(
            {
                **row,
                "baseline_mean": baseline_mean,
                "growth": growth,
                "acceleration": acceleration,
                "institution_breadth": institution_count,
                "group_breadth": group_count,
                "peer_reviewed_share": peer_share,
                **components,
                "score": score,
                "score_coverage": available_weight,
                "data_confidence": min(100.0, confidence_score),
                "trend_label": _trend_label(
                    current_count, baseline_mean, growth, acceleration, institution_count
                ),
                "small_sample_warning": current_count < 5,
            }
        )

    topics = pd.DataFrame(enriched_rows).sort_values(
        ["region", "score"], ascending=[True, False], na_position="last"
    )
    institutions = _build_institutions(works) if not works.empty else pd.DataFrame()
    groups = _build_groups(works) if not works.empty else pd.DataFrame()
    monthly = pd.DataFrame()
    if not works.empty:
        monthly = (
            works.dropna(subset=["publication_date"])
            .assign(month=lambda frame: frame["publication_date"].dt.to_period("M").dt.to_timestamp())
            .groupby(["month", "region"], as_index=False)
            .agg(works=("work_id", "nunique"))
        )
        works = works.sort_values(["publication_date", "citations"], ascending=[False, False])

    return {
        "mode": "live",
        "run_mode": run_mode,
        "domain_profile": domain_profile,
        "topics": topics,
        "institutions": institutions,
        "groups": groups,
        "works": works,
        "monthly": monthly,
        "metadata": metadata,
        "query_log": query_log,
        "current_start": current_start,
        "current_end": current_end,
    }


def _top_values(series: pd.Series, limit: int = 3) -> str:
    values = [str(value) for value in series if pd.notna(value) and value]
    return "；".join(value for value, _ in Counter(values).most_common(limit))


def _build_institutions(current: pd.DataFrame) -> pd.DataFrame:
    if current.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (region, institution), group in current.groupby(["region", "institution"]):
        representative = group.sort_values("citations", ascending=False).iloc[0]
        rows.append(
            {
                "region": region,
                "institution": institution,
                "works": group["work_id"].nunique(),
                "topics": _top_values(group["topic"]),
                "candidate_groups": group["group_name"].nunique(),
                "representative_work": representative["title"],
                "representative_link": representative["link"],
            }
        )
    return pd.DataFrame(rows).sort_values(["region", "works"], ascending=[True, False])


def _build_groups(current: pd.DataFrame) -> pd.DataFrame:
    if current.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for keys, group in current.groupby(
        ["region", "institution", "group_name", "leader", "group_confidence", "attribution_basis"]
    ):
        representative = group.sort_values("citations", ascending=False).iloc[0]
        rows.append(
            {
                "region": keys[0],
                "institution": keys[1],
                "group_name": keys[2],
                "leader": keys[3],
                "confidence": keys[4],
                "attribution_basis": keys[5],
                "works": group["work_id"].nunique(),
                "topics": _top_values(group["topic"]),
                "latest_date": group["publication_date"].max(),
                "representative_work": representative["title"],
                "representative_link": representative["link"],
            }
        )
    return pd.DataFrame(rows).sort_values(["region", "works"], ascending=[True, False])


def empty_radar(metadata: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "mode": "live",
        "topics": pd.DataFrame(),
        "institutions": pd.DataFrame(),
        "groups": pd.DataFrame(),
        "works": pd.DataFrame(),
        "monthly": pd.DataFrame(),
        "metadata": metadata or [],
    }


def load_demo(data_dir: Path) -> dict[str, Any]:
    raw = pd.read_csv(data_dir / "demo_topic_counts.csv")
    raw = raw.rename(
        columns={
            "主题": "topic",
            "地区": "region",
            "当前窗口": "current_count",
            "基线1_2024-11-16至2025-11-15": "baseline_count",
            "最近3月": "recent_three_months",
            "此前9月": "previous_nine_months",
            "预印本": "preprint_count",
        }
    )
    raw["growth"] = (raw["current_count"] - raw["baseline_count"]) / raw["baseline_count"].clip(lower=1)
    raw["institution_breadth"] = pd.NA
    raw["peer_reviewed_share"] = (
        (raw.get("期刊", 0) + raw.get("会议", 0)) / raw["current_count"].clip(lower=1)
    ).clip(upper=1)
    raw["score"] = 100 * (
        0.6 * raw.groupby("region")["current_count"].rank(pct=True)
        + 0.4 * raw.groupby("region")["growth"].rank(pct=True)
    )
    groups = pd.read_csv(data_dir / "demo_groups.csv")
    works = pd.read_csv(data_dir / "demo_works.csv", parse_dates=["publication_date"])
    return {
        "mode": "demo",
        "topics": raw,
        "institutions": pd.DataFrame(),
        "groups": groups,
        "works": works,
        "monthly": pd.DataFrame(),
        "metadata": [
            {"region": "中国内地", "total_count": int(raw[raw.region == "中国内地"].current_count.sum()), "sample_count": len(raw), "truncated": False},
            {"region": "美国", "total_count": int(raw[raw.region == "美国"].current_count.sum()), "sample_count": len(raw), "truncated": False},
            {"region": "欧洲", "total_count": int(raw[raw.region == "欧洲"].current_count.sum()), "sample_count": len(raw), "truncated": False},
        ],
        "current_start": date(2025, 11, 16),
        "current_end": date(2026, 11, 16),
    }


def format_growth(value: float) -> str:
    if pd.isna(value):
        return "—"
    if math.isinf(value):
        return "新增"
    return f"{value:+.0%}"
