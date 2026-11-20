from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard_repository import get_v14_hotspot_dashboard
from storage import database_path
from topic_translations import topic_display_name, topic_translation
from trend_aggregation import diagnose_topic_trends


FIELD_LABEL_ALL = "六大学科（全部）"
COLORS = [
    "#0B63CE", "#16A4D8", "#0E9F6E", "#7C3AED", "#F59E0B",
    "#E83E8C", "#65A30D", "#DC2626", "#475569", "#14B8A6",
]


@st.cache_data(ttl="5m", max_entries=24, show_spinner=False)
def _load_v14(
    path: str,
    signature: tuple[int, int],
    period_days: int,
    field_id: str | None,
    sort_by: str,
) -> dict[str, Any]:
    del signature
    return get_v14_hotspot_dashboard(
        path, period_days=period_days, field_id=field_id, sort_by=sort_by
    )


def _display_time(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "暂无"
    return parsed.strftime("%Y-%m-%d %H:%M")


def _topic_label(row: pd.Series | dict[str, Any]) -> str:
    return topic_display_name(row)


def _topic_options(frame: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    labels: list[str] = []
    label_to_id: dict[str, str] = {}
    for row in frame.to_dict("records"):
        label = f"{_topic_label(row)} · {row['topic_id']}"
        labels.append(label)
        label_to_id[label] = str(row["topic_id"])
    return labels, label_to_id


def _prepare_chart_data(trend: pd.DataFrame, selected_ids: list[str]) -> pd.DataFrame:
    if trend.empty or not selected_ids:
        return pd.DataFrame()
    chart_data = trend[trend["topic_id"].astype(str).isin(selected_ids)].copy()
    if chart_data.empty:
        return chart_data
    chart_data["topic_label"] = chart_data.apply(_topic_label, axis=1)
    translations = chart_data.apply(
        lambda row: topic_translation(
            row["topic_id"], row["topic_name"], row.get("topic_name_zh")
        ),
        axis=1,
    )
    chart_data["translation_status_label"] = translations.map(
        lambda item: item["translation_status_label"]
    )
    for column in ("period_works_count", "comparison_works_count", "growth_rate"):
        chart_data[column] = pd.to_numeric(
            chart_data[column], errors="coerce"
        ).astype("float64")
    chart_data["date"] = pd.to_datetime(chart_data["date"])
    return chart_data


def _date_bounds(frame: pd.DataFrame, data_through: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    starts = pd.to_datetime(frame.get("period_start"), errors="coerce").dropna()
    last_valid_date = pd.to_datetime(data_through, errors="coerce")
    if starts.empty or pd.isna(last_valid_date):
        raise ValueError("Chart date boundaries require valid period dates")
    return starts.min().normalize(), last_valid_date.normalize()


def _display_count(value: Any) -> str:
    return "NA" if pd.isna(value) else f"{int(value):,}"


def _display_rate(value: Any) -> str:
    return "NA" if pd.isna(value) else f"{float(value):+.1%}"


def _plotly_config() -> dict[str, Any]:
    return {
        "displayModeBar": True,
        "displaylogo": False,
        "scrollZoom": True,
        "doubleClick": "reset+autosize",
        "modeBarButtonsToAdd": ["pan2d", "select2d"],
        "responsive": True,
    }


def _base_figure(
    frame: pd.DataFrame, period_days: int, data_through: Any, y_title: str
) -> go.Figure:
    earliest, latest = _date_bounds(frame, data_through)
    tick_values = sorted(pd.to_datetime(frame["date"].dropna().unique()))
    tick_text = [
        pd.Timestamp(value).strftime("%m-%d" if period_days == 90 else "%Y-%m")
        for value in tick_values
    ]
    figure = go.Figure()
    figure.update_layout(
        template="plotly_white",
        height=330,
        margin={"l": 60, "r": 18, "t": 8, "b": 92},
        hovermode="closest",
        dragmode="zoom",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#F8FAFD",
        font={"color": "#14263B", "size": 12},
        legend={
            "orientation": "h", "yanchor": "top", "y": -0.2,
            "xanchor": "left", "x": 0,
        },
    )
    figure.update_xaxes(
        title=None,
        type="date",
        range=[earliest.isoformat(), latest.isoformat()],
        autorange=False,
        fixedrange=False,
        minallowed=earliest.isoformat(),
        maxallowed=latest.isoformat(),
        tickmode="array",
        tickvals=tick_values,
        ticktext=tick_text,
        showgrid=False,
        zeroline=False,
    )
    figure.update_yaxes(
        title=y_title,
        fixedrange=False,
        gridcolor="#E3EBF4",
        zeroline=False,
    )
    return figure


def _works_chart(
    frame: pd.DataFrame, topic_order: list[str], period_days: int,
    data_through: Any,
) -> go.Figure:
    y_title = "7天新增 Works" if period_days == 90 else "月度新增 Works"
    figure = _base_figure(frame, period_days, data_through, y_title)
    color_by_topic = dict(zip(topic_order, COLORS, strict=False))
    for topic_label in topic_order:
        rows = frame[frame["topic_label"] == topic_label].sort_values("date")
        if rows.empty:
            continue
        customdata = [
            [
                escape(str(row.period_label)), row.period_start.strftime("%Y-%m-%d"),
                row.period_end.strftime("%Y-%m-%d"), int(row.period_days),
                escape(str(row.topic_label)), escape(str(row.topic_name)),
                escape(str(row.translation_status_label)), escape(str(row.topic_id)),
                _display_count(row.period_works_count), _display_rate(row.growth_rate),
                escape(str(row.query_status)),
            ]
            for row in rows.itertuples()
        ]
        figure.add_trace(
            go.Scatter(
                x=rows["date"], y=rows["period_works_count"],
                mode="lines+markers", name=topic_label,
                line={"color": color_by_topic[topic_label], "width": 2},
                marker={"color": color_by_topic[topic_label], "size": 6},
                customdata=customdata, connectgaps=False,
                hovertemplate=(
                    "统计周期：%{customdata[0]}<br>开始日期：%{customdata[1]}<br>"
                    "结束日期：%{customdata[2]}<br>统计天数：%{customdata[3]}<br>"
                    "Topic：%{customdata[4]}<br>OpenAlex 英文名称：%{customdata[5]}<br>"
                    "中文名称状态：%{customdata[6]}<br>Topic ID：%{customdata[7]}<br>"
                    "新增 Works：%{customdata[8]}<br>环比：%{customdata[9]}<br>"
                    "数据状态：%{customdata[10]}<extra></extra>"
                ),
            )
        )
    return figure


def _growth_chart(
    frame: pd.DataFrame, topic_order: list[str], period_days: int,
    data_through: Any,
) -> go.Figure:
    y_title = "周环比增长率" if period_days == 90 else "月环比增长率"
    figure = _base_figure(frame, period_days, data_through, y_title)
    figure.update_yaxes(tickformat="+.0%", zeroline=True, zerolinecolor="#64748B")
    color_by_topic = dict(zip(topic_order, COLORS, strict=False))
    for topic_label in topic_order:
        rows = frame[frame["topic_label"] == topic_label].sort_values("date")
        if rows.empty:
            continue
        customdata = [
            [
                escape(str(row.period_label)), row.period_start.strftime("%Y-%m-%d"),
                row.period_end.strftime("%Y-%m-%d"), int(row.period_days),
                escape(str(row.topic_label)), escape(str(row.topic_name)),
                escape(str(row.translation_status_label)), escape(str(row.topic_id)),
                _display_count(row.period_works_count),
                _display_count(row.comparison_works_count),
                _display_rate(row.growth_rate), escape(str(row.growth_status)),
            ]
            for row in rows.itertuples()
        ]
        figure.add_trace(
            go.Scatter(
                x=rows["date"], y=rows["growth_rate"],
                mode="lines+markers", name=topic_label,
                line={"color": color_by_topic[topic_label], "width": 2},
                marker={"color": color_by_topic[topic_label], "size": 6},
                customdata=customdata, connectgaps=False,
                hovertemplate=(
                    "统计周期：%{customdata[0]}<br>开始日期：%{customdata[1]}<br>"
                    "结束日期：%{customdata[2]}<br>统计天数：%{customdata[3]}<br>"
                    "Topic：%{customdata[4]}<br>OpenAlex 英文名称：%{customdata[5]}<br>"
                    "中文名称状态：%{customdata[6]}<br>Topic ID：%{customdata[7]}<br>"
                    "本期 Works：%{customdata[8]}<br>对比期 Works：%{customdata[9]}<br>"
                    f"{y_title}：%{{customdata[10]}}<br>"
                    "增长率状态：%{customdata[11]}<extra></extra>"
                ),
            )
        )
    return figure


db_path = Path(database_path())
signature = (
    (db_path.stat().st_mtime_ns, db_path.stat().st_size)
    if db_path.exists() else (0, 0)
)

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

control_columns = st.columns([1.05, 1.45, 1.05, 1.15], gap="small")
with control_columns[0]:
    period_label = st.segmented_control(
        "观察窗口", ["近90天", "近360天"], default="近90天", key="v14_period"
    )
with control_columns[1]:
    field_label = st.selectbox(
        "学科范围",
        [
            FIELD_LABEL_ALL,
            "化学工程 · Chemical Engineering", "化学 · Chemistry",
            "计算机科学 · Computer Science", "能源 · Energy",
            "工程学 · Engineering", "材料科学 · Materials Science",
        ],
        key="v14_field",
    )
with control_columns[2]:
    sort_label = st.segmented_control(
        "榜单口径", ["增长量", "增长率"], default="增长量", key="v14_sort"
    )
field_ids = {
    FIELD_LABEL_ALL: None,
    "化学工程 · Chemical Engineering": "15", "化学 · Chemistry": "16",
    "计算机科学 · Computer Science": "17", "能源 · Energy": "21",
    "工程学 · Engineering": "22", "材料科学 · Materials Science": "25",
}
period_days = 360 if period_label == "近360天" else 90
sort_by = "growth" if sort_label == "增长率" else "works"
with st.spinner("正在读取本地科研热点数据..."):
    result = _load_v14(
        str(db_path), signature, period_days, field_ids[field_label], sort_by
    )
with control_columns[3]:
    st.text_input(
        "更新时间", value=_display_time(result.get("metrics", {}).get("latest_success_at")),
        disabled=True, key="v14_updated_at",
    )

if result["status"] == "unavailable":
    st.error(
        "V1.4 分类版本尚未导入当前数据库，首页不会回退到旧版 1,126 Topic 分类。",
        icon=":material/database_off:",
    )
    st.stop()
if sort_by == "growth" and not result["growth_sort_available"]:
    st.warning(
        "当前筛选范围没有可用于增长率排名的完整周度或月度基期，已保留 Works 排名。",
        icon=":material/info:",
    )

metrics = result["metrics"]
top_topic = metrics["top_topic"]
completeness = metrics["daily_completeness_360"]
field_names = "化学工程、化学、计算机科学、能源、工程学、材料科学"
kpi_specs = [
    ("period_works", f"近{period_days}天新增论文", f"{metrics['period_works_count']:,}", "Publication Date"),
    ("topic_coverage", "覆盖 Topic 数量", f"{metrics['covered_topics']:,}", result["taxonomy_version"]),
    ("field_coverage", "覆盖学科", f"{metrics['covered_fields']}", field_names if metrics["covered_fields"] == 6 else str(field_label)),
    ("active_topics", "活跃 Topic 数量", f"{metrics['active_topics']:,}", f"近{period_days}天 Works > 0"),
    ("top_topic", "热门研究主题", _topic_label(top_topic), f"{int(top_topic['period_works_count']):,} Works"),
    ("completeness", "数据完整性", f"{completeness:.1%}", "360天日序列" if completeness == 1 else "回填中"),
]
for column, (key, label, value, caption) in zip(st.columns(6, gap="small"), kpi_specs):
    with column:
        with st.container(key=f"kpi_v14_{key}"):
            st.markdown(f"**{label}**")
            st.markdown(f'<div class="radar-kpi-value">{value}</div>', unsafe_allow_html=True)
            st.caption(caption)

st.html('<div class="radar-section-label">全球科研热点监测</div>')
works_ranking = result["all_topics"].head(10).copy()
display_ranking = result["ranking"].copy()
if display_ranking.empty:
    display_ranking = works_ranking

selection_mode = st.segmented_control(
    "Topic 对比范围", ["TOP 5", "TOP 10", "自定义"],
    default="TOP 5", key="v14_topic_mode",
)
all_labels, label_to_id = _topic_options(result["all_topics"])
if selection_mode == "TOP 10":
    selected_ids = display_ranking.head(10)["topic_id"].astype(str).tolist()
elif selection_mode == "自定义":
    defaults = set(display_ranking.head(5)["topic_id"].astype(str))
    selected_labels = st.multiselect(
        "选择要比较的 Topic", all_labels,
        default=[label for label in all_labels if label_to_id[label] in defaults],
        max_selections=10, key="v14_custom_topics",
    )
    selected_ids = [label_to_id[label] for label in selected_labels]
else:
    selected_ids = display_ranking.head(5)["topic_id"].astype(str).tolist()

chart_data = _prepare_chart_data(result["trend"], selected_ids)
available_ids = (
    set(chart_data.loc[chart_data["query_status"] == "success", "topic_id"].astype(str))
    if not chart_data.empty else set()
)
pending_ids = [topic_id for topic_id in selected_ids if topic_id not in available_ids]
indexed_topics = result["all_topics"].set_index("topic_id")
selected_rows = indexed_topics.loc[
    [topic_id for topic_id in selected_ids if topic_id in indexed_topics.index]
] if selected_ids else pd.DataFrame()
topic_order = [
    _topic_label(row) for row in selected_rows.reset_index().to_dict("records")
]
diagnostics = diagnose_topic_trends(
    result["daily"], result["trend"], selected_ids,
    result["field_id"], len(result["all_topics"]),
)
if pending_ids:
    pending_names = [_topic_label(indexed_topics.loc[topic_id]) for topic_id in pending_ids]
    st.info(
        "以下 Topic 的日序列尚在回填，图表不会将缺失值补成 0：" + "、".join(pending_names),
        icon=":material/pending:",
    )
if diagnostics["unmatched_topic_ids"]:
    st.error(
        "图表数据未匹配到以下 Topic ID："
        + "、".join(diagnostics["unmatched_topic_ids"]),
        icon=":material/error:",
    )

chart_columns = st.columns(2, gap="medium")
with chart_columns[0]:
    with st.container(key="panel_v14_works", border=True, height=505):
        st.subheader(":material/query_stats: 热点增长量趋势（Works）")
        st.caption(
            "选定 Topic 的7天新增论文合计 · Publication Date"
            if period_days == 90 else
            "选定 Topic 的自然月新增论文合计 · Publication Date"
        )
        if chart_data.empty or chart_data["period_works_count"].notna().sum() == 0:
            st.info("所选 Topic 暂无已完成回填的日序列。", icon=":material/timeline:")
        else:
            st.plotly_chart(
                _works_chart(
                    chart_data, topic_order, period_days, metrics["data_through"]
                ),
                key="v14_works_chart",
                config=_plotly_config(),
            )
with chart_columns[1]:
    with st.container(key="panel_v14_growth", border=True, height=505):
        st.subheader(":material/trending_up: 热点增长率趋势（Growth Rate）")
        st.caption(
            "当前7天周期相对上一等长周期；无可比基期显示 NA"
            if period_days == 90 else
            "完整月按月环比，未结束月份按 MTD 同期比较；无可比基期显示 NA"
        )
        if chart_data.empty or chart_data["growth_rate"].notna().sum() == 0:
            st.info("当前日序列不足以计算周期增长率。", icon=":material/timeline:")
        else:
            st.plotly_chart(
                _growth_chart(
                    chart_data, topic_order, period_days, metrics["data_through"]
                ),
                key="v14_growth_chart",
                config=_plotly_config(),
            )

st.caption(
    f"数据截止：{metrics['data_through']} · 来源：OpenAlex · "
    "口径：core corpus、primary_topic.id、publication_date。最新日期可能仍在收录中。"
)

bottom_columns = st.columns([1.5, 1], gap="medium")
with bottom_columns[0]:
    with st.container(key="panel_v14_ranking", border=True):
        st.subheader(":material/emoji_events: 科研热点 TOP 10")
        ranking_scope = "六学科范围" if result["field_id"] is None else str(field_label).split(" · ")[0]
        ranking_basis = "最新周期增长率" if sort_by == "growth" else f"近{period_days}天 Works"
        st.caption(f"{ranking_scope}内按{ranking_basis}排名；点击行查看 Topic 详情")
        table = display_ranking.head(10).copy()
        table["Topic"] = table.apply(_topic_label, axis=1)
        table["所属学科"] = table["field_name_zh"] + " · " + table["field_name"]
        table[f"{period_days}天 Works"] = table["period_works_count"]
        table["增长率"] = pd.to_numeric(
            table["period_growth_rate"], errors="coerce"
        ).mul(100)
        table["趋势"] = table["trend"]
        table = table.rename(columns={"rank": "排名"})[
            ["排名", "Topic", "所属学科", f"{period_days}天 Works", "增长率", "趋势"]
        ]
        event = st.dataframe(
            table, hide_index=True, on_select="rerun", selection_mode="single-row",
            key="v14_ranking_table",
            column_config={
                f"{period_days}天 Works": st.column_config.NumberColumn(format="localized"),
                "增长率": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
        selected_index = event.selection.rows[0] if event.selection.rows else 0
        detail = display_ranking.head(10).iloc[selected_index]
        st.markdown(f"**Topic 详情：{_topic_label(detail)}**")
        detail_columns = st.columns(4)
        detail_columns[0].metric("Topic ID", str(detail["topic_id"]))
        detail_columns[1].metric(f"{period_days}天 Works", f"{int(detail['period_works_count']):,}")
        detail_columns[2].metric("Field", str(detail["field_name"]))
        detail_growth = pd.to_numeric(detail["period_growth_rate"], errors="coerce")
        detail_columns[3].metric(
            "增长率", f"{detail_growth:+.1%}" if pd.notna(detail_growth) else "NA"
        )
        detail_translation = topic_translation(
            detail["topic_id"], detail["topic_name"], detail.get("topic_name_zh")
        )
        st.caption(
            f"OpenAlex：{detail['topic_name']} · Subfield：{detail['subfield_name']} · "
            f"中文名称状态：{detail_translation['translation_status_label']}。"
        )

with bottom_columns[1]:
    with st.container(key="panel_v14_insights", border=True):
        st.subheader(":material/insights: 近期热点速览")
        first = result["all_topics"].iloc[0]
        st.markdown(
            f"- **{_topic_label(first)}** 位列当前范围第一，近{period_days}天 "
            f"Works 为 **{int(first['period_works_count']):,}**。"
        )
        other_period = 360 if period_days == 90 else 90
        other = _load_v14(str(db_path), signature, other_period, field_ids[field_label], "works")
        if not other["all_topics"].empty:
            current_top = set(result["all_topics"].head(10)["topic_id"].astype(str))
            other_top = set(other["all_topics"].head(10)["topic_id"].astype(str))
            st.markdown(
                f"- 当前 TOP 10 中有 **{len(current_top & other_top)}** 个 Topic "
                f"同时进入近{other_period}天 TOP 10。"
            )
        st.markdown(
            f"- 当前筛选覆盖 **{metrics['covered_topics']:,}** 个 Topic，其中 "
            f"**{metrics['active_topics']:,}** 个在窗口内有成果。"
        )
        st.caption("增长加速/放缓结论需前一等长窗口；数据不足时不生成推断。")

    with st.container(key="panel_v14_status", border=True):
        st.subheader(":material/database: 数据采集状态")
        status_columns = st.columns(2)
        status_columns[0].metric("上次成功更新", _display_time(metrics["latest_success_at"]))
        status_columns[1].metric("数据截止日期", metrics["data_through"])
        status_columns[0].metric("已覆盖 Topic", f"{metrics['covered_topics']:,}")
        status_columns[1].metric("360天完整率", f"{completeness:.1%}")
        status_columns[0].metric("本地 Works 明细", f"{metrics['local_work_records']:,}")
        status_columns[1].metric("失败更新任务", f"{metrics['failed_update_runs']:,}")
        st.badge(
            "完整" if result["status"] == "complete" else "回填中",
            color="green" if result["status"] == "complete" else "orange",
            icon=":material/sync:",
        )
        st.caption(
            "当前库保存 OpenAlex 汇总计数而非 Works 明细；所有趋势均基于 Publication Date。"
        )
