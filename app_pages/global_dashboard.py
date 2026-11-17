from __future__ import annotations

from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_repository import load_dashboard_data, load_topic_observations
from research_taxonomy import find_direction, find_domain, load_research_taxonomy
from storage import database_path


@st.cache_data(ttl="5m", max_entries=8, show_spinner=False)
def _load_dashboard(path: str, signature: tuple[int, int]) -> dict[str, Any]:
    del signature
    return load_dashboard_data(path)


@st.cache_data(ttl="5m", max_entries=8, show_spinner=False)
def _load_observations(path: str, signature: tuple[int, int]) -> pd.DataFrame:
    del signature
    return load_topic_observations(path)


@st.cache_data
def _load_taxonomy() -> dict[str, Any]:
    return load_research_taxonomy()


def _scope_label(scope: str) -> str:
    return {
        "complete": "完整计数",
        "sample": "样本观察",
        "verified": "已核实",
        "unavailable": "数据不足",
    }.get(scope, scope)


def _metric_value(metric: dict[str, Any]) -> str:
    value = metric.get("value")
    return "--" if value is None else f"{int(value):,}"


def _display_time(value: str | None) -> str:
    if not value:
        return "尚无全球快照"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _format_growth(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    return f"{float(value):+.1%}"


def _open_topic_analysis(topic: dict[str, Any]) -> None:
    st.session_state["analysis_requested_topic"] = topic
    st.switch_page("app_pages/topic_analysis.py")


def _find_observation(
    observations: pd.DataFrame, technology: dict[str, Any]
) -> pd.Series | None:
    if observations.empty or "topic" not in observations:
        return None
    candidates = [technology["label"], *technology.get("aliases", [])]
    normalized = observations["topic"].fillna("").astype(str).str.casefold()
    mask = pd.Series(False, index=observations.index)
    for candidate in candidates:
        term = str(candidate).casefold().strip()
        if term:
            mask |= normalized.eq(term)
    matches = observations[mask].sort_values("completed_at", ascending=False)
    return None if matches.empty else matches.iloc[0]


db_path = Path(database_path())
signature = (
    (db_path.stat().st_mtime_ns, db_path.stat().st_size)
    if db_path.exists()
    else (0, 0)
)
data = _load_dashboard(str(db_path), signature)
observations = _load_observations(str(db_path), signature)
taxonomy = _load_taxonomy()

with st.container(key="research_hero"):
    st.html(
        """
        <div class="radar-hero-copy">
          <div class="radar-hero-kicker">Global research intelligence</div>
          <h1>从全球高校科研动态，发现前沿技术与创新源头</h1>
          <p>基于全球论文、科研机构与高校公开信息，持续追踪科研热点、研究团队与技术突破。</p>
        </div>
        """
    )

last_success = data.get("last_success_at") or {}
last_updated = (
    data.get("as_of_date")
    or last_success.get("completed_at")
    or last_success.get("updated_at")
)

with st.container(horizontal=True, vertical_alignment="bottom"):
    period = st.segmented_control(
        "观察窗口",
        ["近30天", "近90天", "近365天"],
        default="近30天",
        key="home_period",
    )
    region_options = ["全球", "中国"] + [
        code for code in data.get("countries", []) if code != "CN"
    ]
    region = st.selectbox("地域", region_options, key="home_region")
    count_mode = st.segmented_control(
        "统计口径",
        ["完整计数", "样本计数"],
        default="完整计数",
        key="home_count_mode",
    )

if data["coverage_status"] == "unavailable":
    st.warning(data["coverage_message"], icon=":material/database_off:")
else:
    st.caption(data["coverage_message"])

st.html('<div class="radar-section-label">全球科研数据总览</div>')
kpis = data["kpis"]
kpi_specs = [
    ("works", "近30天新增论文", ":material/article:"),
    ("institutions", "活跃科研机构", ":material/account_balance:"),
    ("topics", "新兴研究主题", ":material/layers:"),
    ("groups", "活跃高校课题组", ":material/groups:"),
]
for column, (key, label, icon) in zip(st.columns(4, gap="medium"), kpi_specs):
    metric = kpis.get(key, {})
    with column:
        with st.container(key=f"kpi_{key}"):
            st.markdown(f"{icon} **{label}**")
            st.metric(
                label,
                _metric_value(metric),
                delta=metric.get("delta"),
                label_visibility="collapsed",
            )
            st.caption(_scope_label(metric.get("scope", "unavailable")))
            st.caption(f"更新：{_display_time(last_updated)}")

trend_column, hot_column = st.columns([1.65, 1], gap="medium")
with trend_column:
    with st.container(key="panel_trend", height=430):
        with st.container(horizontal=True, horizontal_alignment="distribute"):
            st.subheader(f"近期科研热点趋势（{region}）")
            st.badge(count_mode, color="blue" if count_mode == "完整计数" else "orange")
        trend = data["trend"].copy()
        if trend.empty:
            st.info(
                "尚无相同口径的全球历史快照。趋势图不会使用示例曲线补位。",
                icon=":material/timeline:",
            )
        else:
            trend["date"] = pd.to_datetime(trend["date"])
            selected_scope = "complete" if count_mode == "完整计数" else "sample"
            trend = trend[trend["count_scope"] == selected_scope]
            if region != "全球":
                trend = trend[trend["region"] == ("CN" if region == "中国" else region)]
            if trend.empty:
                st.info("当前筛选没有可比较的时间序列。")
            else:
                chart = (
                    alt.Chart(trend)
                    .mark_line(point=alt.OverlayMarkDef(size=55), strokeWidth=2.5)
                    .encode(
                        x=alt.X("date:T", title=None),
                        y=alt.Y("value:Q", title="论文数量"),
                        color=alt.Color(
                            "region:N",
                            title="地域",
                            scale=alt.Scale(
                                range=["#0B63CE", "#7C3AED", "#0E9F6E", "#F59E0B"]
                            ),
                        ),
                        tooltip=["date:T", "region:N", "value:Q", "count_scope:N"],
                    )
                    .properties(height=300)
                )
                st.altair_chart(chart)
        st.caption(f"窗口：{period} · 完整计数与样本计数不混用")

with hot_column:
    with st.container(key="panel_hotspots", height=430):
        st.subheader("近期热点速览")
        topics = data["topics"].copy()
        if topics.empty:
            st.info(
                "当前没有通过数据质量与排名门槛的新兴主题。",
                icon=":material/local_fire_department:",
            )
        else:
            for rank, row in enumerate(topics.head(6).to_dict("records"), start=1):
                rank_col, topic_col, growth_col = st.columns([0.45, 3.6, 1.2])
                rank_col.markdown(f'<span class="radar-hot-rank">{rank}</span>', unsafe_allow_html=True)
                if topic_col.button(
                    str(row["topic"]),
                    key=f"hot_topic_{row.get('topic_key', rank)}",
                    width="stretch",
                ):
                    _open_topic_analysis(
                        {"label": row["topic"], "id": row.get("topic_key"), "source": "ranking"}
                    )
                growth_col.markdown(f"**{_format_growth(row.get('growth'))}**")
                growth_col.caption(str(row.get("category") or "趋势观察"))
        st.caption("仅展示通过 score_coverage 与 data_confidence 门槛的真实结果")

taxonomy_column, technology_column = st.columns([1.12, 1], gap="medium")

domain_ids = [item["id"] for item in taxonomy["domains"]]
st.session_state.setdefault("home_domain_id", domain_ids[0])
if st.session_state.home_domain_id not in domain_ids:
    st.session_state.home_domain_id = domain_ids[0]
selected_domain = find_domain(taxonomy, st.session_state.home_domain_id)

direction_ids = [item["id"] for item in selected_domain["directions"]]
st.session_state.setdefault("home_direction_id", direction_ids[0])
if st.session_state.home_direction_id not in direction_ids:
    st.session_state.home_direction_id = direction_ids[0]
selected_direction = find_direction(selected_domain, st.session_state.home_direction_id)

technology_ids = [item["id"] for item in selected_direction["technologies"]]
st.session_state.setdefault("home_technology_id", technology_ids[0])
if st.session_state.home_technology_id not in technology_ids:
    st.session_state.home_technology_id = technology_ids[0]
selected_technology = next(
    item
    for item in selected_direction["technologies"]
    if item["id"] == st.session_state.home_technology_id
)

with taxonomy_column:
    with st.container(key="taxonomy_panel"):
        with st.container(horizontal=True, horizontal_alignment="distribute"):
            st.subheader("科研主题三级分类")
            st.badge("初始分类", color="gray", icon=":material/account_tree:")
        st.caption(taxonomy["notice"])
        level_one, level_two, level_three = st.columns([1, 1.05, 1.1], gap="small")
        with level_one:
            st.markdown("**一级领域**")
            for domain in taxonomy["domains"]:
                if st.button(
                    domain["label"],
                    icon=f":material/{domain['icon']}:",
                    type="primary" if domain["id"] == selected_domain["id"] else "secondary",
                    key=f"domain_{domain['id']}",
                    width="stretch",
                ):
                    st.session_state.home_domain_id = domain["id"]
                    st.session_state.home_direction_id = domain["directions"][0]["id"]
                    st.session_state.home_technology_id = domain["directions"][0]["technologies"][0]["id"]
                    st.rerun()
        with level_two:
            st.markdown("**二级研究方向**")
            for direction in selected_domain["directions"]:
                if st.button(
                    direction["label"],
                    type="primary" if direction["id"] == selected_direction["id"] else "secondary",
                    key=f"direction_{direction['id']}",
                    width="stretch",
                ):
                    st.session_state.home_direction_id = direction["id"]
                    st.session_state.home_technology_id = direction["technologies"][0]["id"]
                    st.rerun()
        with level_three:
            st.markdown("**三级细分技术**")
            for technology in selected_direction["technologies"]:
                if st.button(
                    technology["label"],
                    icon=":material/arrow_forward:",
                    type="primary" if technology["id"] == selected_technology["id"] else "secondary",
                    key=f"technology_{technology['id']}",
                    width="stretch",
                ):
                    st.session_state.home_technology_id = technology["id"]
                    _open_topic_analysis(
                        {
                            **technology,
                            "domain": selected_domain["label"],
                            "direction": selected_direction["label"],
                            "source": "taxonomy",
                        }
                    )

with technology_column:
    with st.container(key="technology_panel"):
        with st.container(horizontal=True, horizontal_alignment="distribute"):
            st.subheader(f"研究方向关键指标 — {selected_technology['label']}")
            st.badge("数据库实值", color="blue", icon=":material/verified:")
        observation = _find_observation(observations, selected_technology)
        paper_count = None if observation is None else observation.get("current_count")
        growth = None if observation is None else observation.get("growth")
        confidence = None if observation is None else observation.get("data_confidence")
        metrics = st.columns(4, gap="small")
        metrics[0].metric(
            "近一年论文数量",
            "--" if paper_count is None or pd.isna(paper_count) else f"{int(paper_count):,}",
        )
        metrics[1].metric("近一年增长率", _format_growth(growth))
        metrics[2].metric("新进入研究高校", "--")
        metrics[3].metric("跨学科研究程度", "--")

        technology_period = st.segmented_control(
            "论文趋势",
            ["近30天", "近90天", "近365天"],
            default="近365天",
            key="technology_period",
        )
        st.info(
            "当前数据库尚未形成该技术的标准化周期快照。缺失值保持为空，"
            "后续需要补充主题周期、高校进入和跨学科指标。",
            icon=":material/data_alert:",
        )
        with st.container(horizontal=True, horizontal_alignment="distribute"):
            st.caption(f"当前窗口：{technology_period}")
            st.caption(
                "数据置信度：--"
                if confidence is None or pd.isna(confidence)
                else f"数据置信度：{float(confidence):.0f}/100"
            )
        if st.button(
            "查看主题深度分析",
            type="primary",
            icon=":material/arrow_forward:",
            key="view_selected_technology",
        ):
            _open_topic_analysis(
                {
                    **selected_technology,
                    "domain": selected_domain["label"],
                    "direction": selected_direction["label"],
                    "source": "taxonomy",
                }
            )

with st.expander("数据口径与覆盖说明", icon=":material/info:"):
    st.markdown(
        """
- 首页只读取本地 SQLite 已保存结果，筛选和分类切换不会触发 OpenAlex 请求。
- 完整计数、样本观察、已核实实体和缺失状态分别展示；样本不会冒充全球总体。
- 三级分类是可扩展导航配置，不代表实时热点排名；热点速览只接受通过质量门槛的数据库结果。
- 中国按论文至少一个中国机构署名统计；跨国论文可进入多个国家，全球总量只去重一次。
"""
    )
