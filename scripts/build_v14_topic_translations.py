from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import sqlite3
import time

import pandas as pd
import requests

from collector.v14_taxonomy import TAXONOMY_VERSION, VERIFIED_TOPIC_NAMES_ZH


FIELD_IDS = {"15", "16", "17", "21", "22", "25"}
CURATED_CANDIDATES = {
    "T10024": "二氧化钛光催化与太阳能电池", "T10028": "主题建模",
    "T10052": "医学图像分割技术", "T10079": "纳米颗粒合成与应用",
    "T10088": "生物质热化学转化过程", "T10096": "金属有机框架的合成与应用",
    "T10104": "纳米流体流动与传热", "T10117": "先进燃烧工程技术",
    "T10121": "建筑能源与舒适度优化", "T10161": "岩石力学与建模",
    "T10180": "分析化学方法开发", "T10212": "电化学传感器与生物传感器",
    "T10245": "超材料与超表面应用", "T10270": "区块链技术应用与安全",
    "T10274": "杂环化合物合成与生物活性", "T10275": "二维材料及其应用",
    "T10284": "厌氧消化与沼气生产", "T10343": "水凝胶合成、性质与应用",
    "T10400": "网络安全与入侵检测", "T10480": "离子液体性质与应用",
    "T10488": "食品包装用纳米复合薄膜", "T10491": "提高石油采收率技术",
    "T10495": "甲烷重整催化剂", "T10532": "分子传感器与离子检测",
    "T10578": "超分子化学与配合物", "T10640": "光谱与化学计量学分析",
    "T10663": "电池建模与管理", "T10680": "风能研究与开发",
    "T10682": "量子计算算法与架构", "T10689": "遥感图像分类",
    "T10701": "自由基光化学反应", "T10705": "增材制造材料与工艺",
    "T10719": "三维形状建模与分析", "T10764": "数据隐私保护技术",
    "T10775": "生成对抗网络与图像合成", "T10862": "人工智能癌症检测",
    "T10883": "人工智能伦理与社会影响", "T10967": "二氧化碳捕集与封存技术",
    "T11007": "混合可再生能源系统", "T11009": "生物质转化催化",
    "T11091": "萃取与分离过程", "T11208": "木质素与木材化学",
    "T11224": "电磁波吸收材料", "T11362": "膜分离与气体传输",
    "T11401": "矿物浮选与分离技术", "T11460": "药物分析方法",
    "T11690": "水系电池与液流电池", "T11714": "多模态机器学习应用",
    "T11784": "二氧化碳还原技术与催化剂", "T11948": "材料科学中的机器学习",
    "T12008": "太阳能驱动水净化方法", "T12074": "基于膜的离子分离技术",
    "T12112": "氨合成与氮还原",
}


def _translate(name: str) -> str:
    response = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": name},
        timeout=30,
    )
    response.raise_for_status()
    return "".join(segment[0] for segment in response.json()[0] if segment[0]).strip()


def _translate_with_retry(name: str) -> str:
    for attempt in range(4):
        try:
            translated = _translate(name)
            if translated:
                return translated
        except (requests.RequestException, ValueError, KeyError, TypeError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Unable to translate {name}")


def build_catalog(database: Path, output: Path, workers: int = 8) -> pd.DataFrame:
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        topics = pd.read_sql_query(
            """
            SELECT topic_id, topic_name, topic_name_zh, field_id
            FROM topic_taxonomy_versions
            WHERE taxonomy_version=?
            ORDER BY field_id, topic_id
            """,
            connection,
            params=(TAXONOMY_VERSION,),
            dtype={"topic_id": "string", "field_id": "string"},
        )
    if len(topics) != 1063 or set(topics["field_id"].astype(str)) != FIELD_IDS:
        raise ValueError("Expected the complete 1,063-Topic V1.4 taxonomy")

    existing: dict[str, str] = {}
    if output.exists():
        cached = pd.read_csv(output, dtype="string", encoding="utf-8-sig").fillna("")
        existing = dict(zip(cached["topic_id"].astype(str), cached["topic_name_zh"].astype(str)))
    pending = {
        str(row.topic_id): str(row.topic_name)
        for row in topics.itertuples()
        if str(row.topic_id) not in VERIFIED_TOPIC_NAMES_ZH
        and str(row.topic_id) not in CURATED_CANDIDATES
        and not existing.get(str(row.topic_id), "").strip()
    }
    translated: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_translate_with_retry, name): topic_id for topic_id, name in pending.items()}
        for future in as_completed(futures):
            translated[futures[future]] = future.result()

    records = []
    for row in topics.itertuples():
        topic_id = str(row.topic_id)
        if topic_id in VERIFIED_TOPIC_NAMES_ZH:
            name_zh = VERIFIED_TOPIC_NAMES_ZH[topic_id]
            status = "verified"
            source = "existing_manual_review"
            reviewed_at = "2026-11-18"
        elif topic_id in CURATED_CANDIDATES:
            name_zh = CURATED_CANDIDATES[topic_id]
            status = "candidate"
            source = "domain_terminology_candidate"
            reviewed_at = ""
        else:
            name_zh = translated.get(topic_id) or existing.get(topic_id, "")
            status = "candidate" if name_zh else "untranslated"
            source = "google_translate_candidate" if name_zh else ""
            reviewed_at = ""
        records.append(
            {
                "topic_id": topic_id,
                "topic_name": str(row.topic_name),
                "topic_name_zh": name_zh,
                "translation_status": status,
                "translation_source": source,
                "reviewed_at": reviewed_at,
                "taxonomy_version": TAXONOMY_VERSION,
                "field_id": str(row.field_id),
            }
        )
    result = pd.DataFrame(records)
    if result["topic_name_zh"].str.strip().eq("").any():
        raise ValueError("Translation catalog still contains untranslated Topics")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    result.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "v14_topic_names_zh.csv",
    )
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    result = build_catalog(args.database, args.output, args.workers)
    print(
        {
            "rows": len(result),
            "verified": int(result["translation_status"].eq("verified").sum()),
            "candidate": int(result["translation_status"].eq("candidate").sum()),
            "generated_at": date.today().isoformat(),
            "output": str(args.output),
        }
    )


if __name__ == "__main__":
    main()
