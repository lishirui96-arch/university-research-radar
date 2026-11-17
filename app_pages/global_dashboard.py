from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_repository import load_dashboard_data
from storage import database_path


@st.cache_data(ttl="5m", max_entries=8, show_spinner=False)
def _load_dashboard(path: str, signature: tuple[int, int]) -> dict:
    del signature
    return load_dashboard_data(path)


def _scope_label(scope: str) -> str:
    return {
        "complete": "完整计数",
        "sample": "样本观察",
        "verified": "已核实",
        "unavailable": "数据不足",
    }.get(scope, scope)


def _metric_value(metric: dict) -> str:
    value = metric.get("value")
    return "--" if value is None else f"{int(value):,}"


db_path = Path(database_path())
signature = (db_path.stat().st_mtime_ns, db_path.stat().st_size) if db_path.exists() else (0, 0)
data = _load_dashboard(str(db_path), signature)

with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
    st.title("全球高校科研热点总览")
    if data["coverage_status"] == "unavailable":
        st.badge("全球数据未就绪", color="orange", icon=":material/database_off:")
    else:
        st.badge("本地快照", color="green", icon=":material/database:")

st.caption("Global University Research & Innovation Intelligence Radar")

last_success = data.get("last_success_at")
status_text = data["coverage_message"]
if last_success:
    status_text += f" 最近一次成功扫描：{last_success.get('completed_at') or last_success.get('updated_at')}。"
st.info(status_text, icon=":material/info:")

country_options = ["全球", "中国"] + [
    code for code in data.get("countries", []) if code != "CN"
]
with st.container(horizontal=True, vertical_alignment="bottom"):
    time_range = st.segmented_control(
        "时间范围",
        ["近7天", "近30天", "近90天", "近12个月", "近3年"],
        default="近30天",
        key="global_time_range",
    )
    region = st.selectbox(
        "地域",
        country_options,
        key="global_region",
    )
    statistic_mode = st.segmented_control(
        "统计模式",
        ["论文实际数量", "期初为100的增长指数"],
        default="论文实际数量",
        key="global_statistic_mode",
    )
    discovery_mode = st.segmented_control(
        "发现模式",
        ["自动发现", "预设领域"],
        default="自动发现",
        key="global_discovery_mode",
    )

st.caption(
    f"当前筛选：{time_range} · {region} · {statistic_mode} · {discovery_mode} · "
    f"统计日期 {data.get('as_of_date') or '尚无全球快照'}"
)

st.subheader("全球科研数据总览")
kpis = data["kpis"]
with st.container(horizontal=True):
    for key, label, icon in [
        ("works", "近30天新增论文", ":material/article:"),
        ("institutions", "活跃科研机构", ":material/account_balance:"),
        ("topics", "新兴研究主题", ":material/trending_up:"),
        ("groups", "活跃研究团队", ":material/groups:"),
    ]:
        metric = kpis.get(key, {})
        st.metric(
            label,
            _metric_value(metric),
            delta=metric.get("delta"),
            border=True,
            help=f"{_scope_label(metric.get('scope', 'unavailable'))}。{metric.get('detail', '')}",
        )

with st.container(border=True):
    st.subheader("近期科研热点趋势")
    trend = data["trend"].copy()
    if trend.empty:
        st.info(
            "尚无可比较的全球历史快照。形成至少两个相同口径的成功批次后才计算趋势。",
            icon=":material/timeline:",
        )
    else:
        trend["date"] = pd.to_datetime(trend["date"])
        if statistic_mode == "期初为100的增长指数":
            parts = []
            for name, part in trend.groupby("region"):
                part = part.sort_values("date").copy()
                base = part["value"].iloc[0]
                if pd.notna(base) and base > 0:
                    part["display_value"] = part["value"] / base * 100
                    parts.append(part)
            trend = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
            y_title = "增长指数（期初=100）"
        else:
            trend["display_value"] = trend["value"]
            y_title = "论文数量"
        if trend.empty:
            st.warning("期初为零、缺失或统计口径不可比，无法计算增长指数。")
        else:
            chart = (
                alt.Chart(trend)
                .mark_line(point=True)
                .encode(
                    x=alt.X("date:T", title="日期"),
                    y=alt.Y("display_value:Q", title=y_title),
                    color=alt.Color("region:N", title="地域"),
                    strokeDash=alt.StrokeDash("count_scope:N", title="计数口径"),
                    tooltip=["date:T", "region:N", "display_value:Q", "count_scope:N"],
                )
            )
            st.altair_chart(chart)

with st.container(border=True):
    st.subheader("全球新兴研究主题 TOP 10")
    topics = data["topics"].copy()
    if topics.empty:
        st.info(
            "自动发现需要全量 Topics 索引、历史计数及质量门控。当前没有满足条件的真实主题榜单。",
            icon=":material/search_insights:",
        )
    else:
        labels = {
            "emerging": "Emerging",
            "fast_growing": "Fast Growing",
            "trending": "Trending",
            "cross_disciplinary": "Cross-disciplinary",
        }
        tabs = st.tabs(list(labels.values()))
        for tab, (category, _) in zip(tabs, labels.items()):
            with tab:
                view = topics[topics["category"] == category].head(10)
                if view.empty:
                    st.caption("当前批次没有通过质量门槛的主题。")
                else:
                    st.dataframe(
                        view,
                        hide_index=True,
                        column_config={
                            "topic": st.column_config.TextColumn("主题", pinned=True),
                            "total_count": st.column_config.NumberColumn("完整计数", format="%d"),
                            "sampled_count": st.column_config.NumberColumn("采样量", format="%d"),
                            "growth": st.column_config.NumberColumn("增长率", format="%.1%%"),
                            "data_confidence": st.column_config.ProgressColumn(
                                "数据置信度", min_value=0, max_value=100
                            ),
                            "topic_key": None,
                            "category": None,
                        },
                    )

st.subheader("全球高校科研力量")
left, right = st.columns(2)
for column, title, frame in [
    (left, "全球高校 TOP 20", data["global_institutions"]),
    (right, "中国高校 TOP 20", data["china_institutions"]),
]:
    with column:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            if frame.empty:
                st.info("尚无可发布的高校排名。")
            else:
                ranking_scope = str(frame.iloc[0].get("ranking_scope", "sample_rank"))
                st.badge(
                    "样本论文排名" if ranking_scope == "sample_rank" else "完整数据排名",
                    color="orange" if ranking_scope == "sample_rank" else "green",
                )
                st.dataframe(
                    frame,
                    hide_index=True,
                    column_config={
                        "institution": st.column_config.TextColumn("高校", pinned=True),
                        "country_code": st.column_config.TextColumn("国家/地区"),
                        "work_count": st.column_config.NumberColumn("近期论文"),
                        "topic_count": st.column_config.NumberColumn("主题"),
                        "author_count": st.column_config.NumberColumn("活跃作者"),
                        "data_confidence": st.column_config.ProgressColumn(
                            "置信度", min_value=0, max_value=100
                        ),
                        "ranking_scope": None,
                    },
                )

with st.container(border=True):
    st.subheader("高校科研动态与代表性成果")
    works = data["works"]
    if works.empty:
        st.info("本地数据库尚无可展示的真实成果记录。")
    else:
        st.badge("OpenAlex 论文样本", color="orange", icon=":material/source:")
        st.dataframe(
            works,
            hide_index=True,
            column_config={
                "publication_date": st.column_config.DateColumn("发表日期", format="YYYY-MM-DD"),
                "title": st.column_config.TextColumn("论文标题", pinned=True, width="large"),
                "institutions": st.column_config.TextColumn("高校及机构", width="large"),
                "doi": st.column_config.LinkColumn("DOI"),
                "openalex_work_id": st.column_config.LinkColumn("OpenAlex"),
                "venue": st.column_config.TextColumn("来源"),
                "work_type": st.column_config.TextColumn("类型"),
                "cited_by_count": st.column_config.NumberColumn("引用"),
            },
        )

with st.container(border=True):
    st.subheader("科研热点预警")
    alerts = data["alerts"]
    if alerts.empty:
        st.info(
            "尚无通过连续周期、覆盖率和证据门槛的预警。失败或低置信度批次不会触发正式预警。",
            icon=":material/notifications_none:",
        )
    else:
        st.dataframe(alerts, hide_index=True)

with st.expander("数据口径", icon=":material/info:"):
    st.markdown(
        """
- 完整计数、样本观察、已核实实体和缺失状态分别展示，不相互替代。
- 中国按论文至少一个中国机构署名统计；跨国论文可进入多个国家，但全球总量只去重一次。
- 当前未建立作品版本家族时，只能显示 OpenAlex 记录数，不能称为去重论文数量。
- 自动发现不受具身智能或材料科学预设词表限制，但必须先建立全量 Topics 历史计数。
"""
    )
