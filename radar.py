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
ALGORITHM_VERSION = "1.1.0"
MIN_GROWTH_SAMPLE = 5
GROWTH_PRIOR_COUNT = 5.0
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
    count_payload = _request_json(
        {"search": query, "filter": filters, "per-page": 1, "select": "id"}, api_key
    )
    total_count = int(count_payload.get("meta", {}).get("count", 0))
    records: list[dict[str, Any]] = []
    segments = [(from_date, to_date, min(max_records, total_count))]
    sampling_strategy = "complete_cursor" if total_count <= max_records else "time_stratified_representative"
    if total_count > max_records:
        date_segments = _date_segments(from_date, to_date, min(4, max_records))
        base, remainder = divmod(max_records, len(date_segments))
        segments = [
            (start, end, base + (1 if index < remainder else 0))
            for index, (start, end) in enumerate(date_segments)
        ]

    for segment_start, segment_end, budget in segments:
        if budget <= 0:
            continue
        segment_filters = ",".join(
            [
                f"from_publication_date:{segment_start.isoformat()}",
                f"to_publication_date:{segment_end.isoformat()}",
                f"authorships.institutions.country_code:{country_filter}",
                "authorships.institutions.type:education",
            ]
        )
        cursor = "*"
        segment_records = 0
        while segment_records < budget and cursor:
            page_size = min(200, budget - segment_records)
            params = {
                "search": query,
                "filter": segment_filters,
                "per-page": page_size,
                "cursor": cursor,
                "select": (
                    "id,doi,display_name,publication_date,type,cited_by_count,"
                    "primary_topic,topics,keywords,authorships,primary_location,open_access"
                ),
            }
            if sampling_strategy == "time_stratified_representative":
                params["sort"] = "cited_by_count:desc"
            payload = _request_json(params, api_key)
            batch = payload.get("results", [])
            if not batch:
                break
            records.extend(_parse_work(work, region, set(codes)) for work in batch)
            segment_records += len(batch)
            cursor = payload.get("meta", {}).get("next_cursor")

    deduplicated = {record["openalex_work_id"]: record for record in records}
    records = list(deduplicated.values())

    frame = pd.DataFrame(records)
    if not frame.empty:
        frame["publication_date"] = pd.to_datetime(frame["publication_date"], errors="coerce")
    meta = {
        "region": region,
        "total_count": total_count,
        "sampled_count": len(frame),
        "sample_count": len(frame),
        "coverage_rate": min(1.0, len(frame) / total_count) if total_count else 1.0,
        "truncated": total_count > len(frame),
        "sample_truncated": total_count > len(frame),
        "sampling_strategy": sampling_strategy,
        "sampling_segments": [
            {"from": start.isoformat(), "to": end.isoformat(), "budget": budget}
            for start, end, budget in segments
        ],
        "sampled_institution_count": (
            int(frame["institution_id"].replace("", pd.NA).nunique()) if not frame.empty else 0
        ),
        "institution_coverage_complete": total_count <= len(frame),
        "institution_coverage_rate": 1.0 if total_count <= len(frame) else math.nan,
        "source": "OpenAlex",
        "query": query,
        "filters": filters,
    }
    return frame, meta


def _date_segments(from_date: date, to_date: date, count: int) -> list[tuple[date, date]]:
    """Split an inclusive date window into non-overlapping, near-equal segments."""
    total_days = (to_date - from_date).days + 1
    count = max(1, min(count, total_days))
    base, remainder = divmod(total_days, count)
    segments: list[tuple[date, date]] = []
    cursor = from_date
    for index in range(count):
        days = base + (1 if index < remainder else 0)
        end = cursor + timedelta(days=days - 1)
        segments.append((cursor, end))
        cursor = end + timedelta(days=1)
    return segments


def _parse_work(work: dict[str, Any], region: str, country_codes: set[str]) -> dict[str, Any]:
    target_authors: list[dict[str, Any]] = []
    author_names: list[str] = []
    institutions: list[str] = []
    institution_ids: list[str] = []
    authorships_data: list[dict[str, Any]] = []

    for authorship_order, authorship in enumerate(work.get("authorships") or []):
        author = authorship.get("author") or {}
        author_name = author.get("display_name", "")
        if author_name:
            author_names.append(author_name)
        all_institutions = [
            {
                "openalex_institution_id": inst.get("id") or "",
                "display_name": inst.get("display_name") or "",
                "country_code": inst.get("country_code") or "",
                "institution_type": inst.get("type") or "",
                "ror": inst.get("ror") or "",
            }
            for inst in authorship.get("institutions") or []
            if inst.get("id")
        ]
        authorships_data.append(
            {
                "openalex_author_id": author.get("id") or "",
                "display_name": author_name,
                "orcid": author.get("orcid") or "",
                "author_position": authorship.get("author_position") or "",
                "is_corresponding": bool(authorship.get("is_corresponding")),
                "authorship_order": authorship_order,
                "institutions": all_institutions,
            }
        )
        target_institutions = [
            inst
            for inst in authorship.get("institutions") or []
            if inst.get("country_code") in country_codes and inst.get("type") == "education"
        ]
        if target_institutions:
            target_authors.append(
                {
                    "openalex_author_id": author.get("id") or "",
                    "name": author_name,
                    "is_corresponding": bool(authorship.get("is_corresponding")),
                    "institutions": target_institutions,
                }
            )
            institutions.extend(
                inst.get("display_name", "") for inst in target_institutions if inst.get("display_name")
            )
            institution_ids.extend(inst.get("id", "") for inst in target_institutions if inst.get("id"))

    corresponding = [item for item in target_authors if item["is_corresponding"]]
    leader_record = corresponding[0] if corresponding else (target_authors[-1] if target_authors else None)
    leader = leader_record["name"] if leader_record else "待核验"
    leader_id = leader_record.get("openalex_author_id", "") if leader_record else ""
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

    topics_data = []
    for topic_record in work.get("topics") or []:
        if not topic_record.get("id"):
            continue
        topics_data.append(
            {
                "openalex_topic_id": topic_record.get("id") or "",
                "display_name": topic_record.get("display_name") or "",
                "score": topic_record.get("score"),
                "is_primary": topic_record.get("id") == topic.get("id"),
            }
        )

    return {
        "work_id": work_id.rsplit("/", 1)[-1],
        "openalex_work_id": work_id,
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
        "institution_id": (
            leader_record["institutions"][0].get("id", "")
            if leader_record
            else (institution_ids[0] if institution_ids else "")
        ),
        "institutions": "；".join(dict.fromkeys(institutions)),
        "institution_ids": list(dict.fromkeys(institution_ids)),
        "authors": "；".join(author_names),
        "authorships_data": authorships_data,
        "openalex_topics": topics_data,
        "openalex_primary_topic_id": topic.get("id") or "",
        "leader": leader,
        "leader_id": leader_id,
        "group_name": f"{leader} 候选课题组" if leader != "待核验" else "待核验合作簇",
        "group_confidence": confidence,
        "group_status": "candidate",
        "attribution_basis": attribution,
    }


def _bounded_growth_score(growth: float, scale: float = 1.0) -> float:
    if pd.isna(growth):
        return math.nan
    return float(max(0.0, min(100.0, 50.0 + 50.0 * math.tanh(growth / scale))))


def _momentum_score(current_count: int, growth: float) -> float:
    if pd.isna(growth):
        return math.nan
    scale_score = min(100.0, 25.0 * math.log10(current_count + 1))
    growth_score = _bounded_growth_score(growth)
    return 0.45 * scale_score + 0.55 * growth_score


def _breadth_score(count: int, reference_count: int, available: bool) -> float:
    if not available:
        return math.nan
    return min(100.0, count / max(reference_count, 1) * 100)


def _trend_label(
    current_count: int,
    baseline_mean: float,
    growth: float,
    acceleration: float,
    institution_count: int,
    newness_status: str,
) -> str:
    if current_count < 5:
        return "证据不足"
    if newness_status == "insufficient_history":
        return "证据不足"
    if newness_status == "genuine_new":
        return "新兴方向"
    if not pd.isna(growth) and growth >= 0.20 and not pd.isna(acceleration) and acceleration >= 0 and institution_count >= 3:
        return "上升热点"
    if (not pd.isna(growth) and growth <= -0.20) or (
        not pd.isna(acceleration) and acceleration <= -0.25
    ):
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
    metadata_by_topic_region = {
        (item.get("topic"), item.get("region")): item for item in metadata
    }
    weights = MATERIAL_HEAT_WEIGHTS if domain_profile == "材料科学" else GENERIC_HEAT_WEIGHTS
    for row in topics.to_dict("records"):
        raw_baseline_values = [row.get(f"baseline_{index}_count") for index in range(1, 4)]
        history_complete = all(value is not None and not pd.isna(value) for value in raw_baseline_values)
        baseline_values = [float(value) for value in raw_baseline_values] if history_complete else []
        baseline_mean = sum(baseline_values) / 3 if history_complete else math.nan
        current_count = int(row.get("current_count", 0))
        coverage_comparable = bool(row.get("coverage_comparable", True))
        baseline_zero = history_complete and baseline_mean == 0
        growth = (
            (current_count - baseline_mean) / baseline_mean
            if history_complete and baseline_mean > 0
            else math.nan
        )
        adjusted_growth = (
            (current_count - baseline_mean) / (baseline_mean + GROWTH_PRIOR_COUNT)
            if history_complete
            else math.nan
        )
        small_growth_sample = history_complete and current_count + baseline_mean < 2 * MIN_GROWTH_SAMPLE
        growth_for_scoring = adjusted_growth if small_growth_sample or baseline_zero else growth

        recent_count = row.get("recent_count")
        previous_count = row.get("previous_count")
        acceleration_history_complete = all(
            value is not None and not pd.isna(value) for value in [recent_count, previous_count]
        )
        recent_rate = float(recent_count) / max(recent_days, 1) if acceleration_history_complete else math.nan
        previous_rate = float(previous_count) / max(previous_days, 1) if acceleration_history_complete else math.nan
        if acceleration_history_complete and previous_rate > 0:
            acceleration = (recent_rate - previous_rate) / previous_rate
        elif acceleration_history_complete and recent_rate == 0:
            acceleration = 0.0
        else:
            acceleration = math.nan
        acceleration_sample = (
            int(recent_count) + int(previous_count) if acceleration_history_complete else 0
        )
        adjusted_acceleration = (
            (recent_rate - previous_rate) / (previous_rate + 1 / max(current_days, 1))
            if acceleration_history_complete and acceleration_sample >= MIN_GROWTH_SAMPLE
            else math.nan
        )
        acceleration_for_scoring = (
            acceleration
            if acceleration_sample >= 2 * MIN_GROWTH_SAMPLE and not pd.isna(acceleration)
            else adjusted_acceleration
        )

        if not history_complete or not coverage_comparable:
            newness_status = "insufficient_history"
        elif baseline_zero and current_count >= MIN_GROWTH_SAMPLE:
            newness_status = "genuine_new"
        elif baseline_zero:
            newness_status = "small_sample_from_zero"
        else:
            newness_status = "established"

        topic_works = pd.DataFrame()
        if not works.empty:
            topic_works = works[
                (works["region"] == row["region"]) & (works["topic"] == row["topic"])
            ]
        institution_key = "institution_id" if "institution_id" in topic_works else "institution"
        institution_count = (
            int(topic_works[institution_key].replace("", pd.NA).dropna().nunique())
            if not topic_works.empty
            else 0
        )
        author_ids = {
            author.get("openalex_author_id")
            for authorships in topic_works.get("authorships_data", pd.Series(dtype=object))
            if isinstance(authorships, list)
            for author in authorships
            if author.get("openalex_author_id")
        }
        author_count = len(author_ids)
        peer_share = (
            float(topic_works["source_type"].isin(["journal", "conference"]).mean())
            if not topic_works.empty
            else math.nan
        )
        eligible_groups = pd.DataFrame()
        if not topic_works.empty:
            eligible_groups = topic_works[topic_works["group_confidence"].isin(["高", "中高"])]
        group_count = int(eligible_groups["group_name"].nunique()) if not eligible_groups.empty else 0

        meta = metadata_by_topic_region.get((row.get("topic"), row.get("region")), {})
        sampled_count = int(meta.get("sampled_count", meta.get("sample_count", len(topic_works))))
        coverage_rate = float(
            meta.get(
                "coverage_rate",
                min(1.0, sampled_count / current_count) if current_count else 1.0,
            )
        )
        sample_truncated = bool(meta.get("sample_truncated", meta.get("truncated", False)))
        institution_coverage_complete = bool(
            meta.get("institution_coverage_complete", not sample_truncated)
        )

        components: dict[str, float] = {
            "momentum_score": _momentum_score(current_count, growth_for_scoring),
            "acceleration_score": _bounded_growth_score(acceleration_for_scoring),
            "group_breadth_score": _breadth_score(
                group_count, 10, group_count > 0 and institution_coverage_complete
            ),
            "institution_diffusion_score": _breadth_score(
                institution_count, 20, institution_coverage_complete
            ),
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
        confidence_score = 100 * (
            0.40 * coverage_rate
            + 0.25 * (1.0 if row.get("query_string") else 0.0)
            + 0.15 * (1.0 if not pd.isna(peer_share) else 0.0)
            + 0.10 * (1.0 if institution_coverage_complete else 0.0)
            + 0.10 * (1.0 if group_count else 0.0)
        )
        enriched_rows.append(
            {
                **row,
                "baseline_mean": baseline_mean,
                "growth": growth,
                "adjusted_growth": adjusted_growth,
                "growth_status": (
                    "insufficient_history"
                    if not history_complete
                    else "from_zero"
                    if baseline_zero and current_count > 0
                    else "stable_zero"
                    if baseline_zero
                    else "comparable"
                ),
                "acceleration": acceleration,
                "adjusted_acceleration": adjusted_acceleration,
                "acceleration_status": (
                    "insufficient_history"
                    if not acceleration_history_complete
                    else "from_zero"
                    if previous_rate == 0 and recent_rate > 0
                    else "comparable"
                ),
                "institution_breadth": institution_count,
                "institution_count_is_complete": institution_coverage_complete,
                "author_breadth": author_count,
                "group_breadth": group_count,
                "peer_reviewed_share": peer_share,
                **components,
                "score": score,
                "score_coverage": available_weight,
                "data_confidence": min(100.0, confidence_score),
                "total_count": current_count,
                "sampled_count": sampled_count,
                "coverage_rate": coverage_rate,
                "sample_truncated": sample_truncated,
                "newness_status": newness_status,
                "coverage_comparability": (
                    "same_source_same_query" if coverage_comparable else "not_comparable"
                ),
                "database_coverage_change_detected": row.get("database_coverage_change_detected"),
                "growth_interpretation": (
                    "OpenAlex记录数量变化；尚不能排除数据库历史回填"
                    if coverage_comparable
                    else "数据覆盖口径变化，不解释为论文增长"
                ),
                "algorithm_version": ALGORITHM_VERSION,
                "trend_label": _trend_label(
                    current_count,
                    baseline_mean,
                    growth_for_scoring,
                    acceleration_for_scoring,
                    institution_count,
                    newness_status,
                ),
                "small_sample_warning": current_count < MIN_GROWTH_SAMPLE or small_growth_sample,
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
        "algorithm_version": ALGORITHM_VERSION,
    }


def _top_values(series: pd.Series, limit: int = 3) -> str:
    values = [str(value) for value in series if pd.notna(value) and value]
    return "；".join(value for value, _ in Counter(values).most_common(limit))


def _build_institutions(current: pd.DataFrame) -> pd.DataFrame:
    if current.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    group_columns = ["region", "institution"]
    if "institution_id" in current:
        group_columns.insert(1, "institution_id")
    for keys, group in current.groupby(group_columns, dropna=False):
        if len(group_columns) == 3:
            region, institution_id, institution = keys
        else:
            region, institution = keys
            institution_id = ""
        representative = group.sort_values("citations", ascending=False).iloc[0]
        rows.append(
            {
                "region": region,
                "institution_id": institution_id,
                "institution": institution,
                "works": group["work_id"].nunique(),
                "topics": _top_values(group["topic"]),
                "candidate_groups": group["group_name"].nunique(),
                "representative_work": representative["title"],
                "representative_link": representative["link"],
                "count_scope": "采集样本",
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
                "status": "candidate",
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
        "query_log": [],
        "algorithm_version": ALGORITHM_VERSION,
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
            {"region": "中国内地", "total_count": int(raw[raw.region == "中国内地"].current_count.sum()), "sampled_count": len(raw), "sample_count": len(raw), "coverage_rate": math.nan, "truncated": False},
            {"region": "美国", "total_count": int(raw[raw.region == "美国"].current_count.sum()), "sampled_count": len(raw), "sample_count": len(raw), "coverage_rate": math.nan, "truncated": False},
            {"region": "欧洲", "total_count": int(raw[raw.region == "欧洲"].current_count.sum()), "sampled_count": len(raw), "sample_count": len(raw), "coverage_rate": math.nan, "truncated": False},
        ],
        "current_start": date(2025, 11, 16),
        "current_end": date(2026, 11, 16),
        "algorithm_version": "demo-v1",
    }


def format_growth(value: float) -> str:
    if pd.isna(value):
        return "—"
    if math.isinf(value):
        return "新增"
    return f"{value:+.0%}"
