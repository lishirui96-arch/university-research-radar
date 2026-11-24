from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard_repository import (
    get_citation_ranking,
    get_v14_hotspot_dashboard,
    get_v15_regional_dashboard,
)
from storage import database_path
from topic_translations import topic_display_name, topic_translation
from trend_aggregation import diagnose_topic_trends


FIELD_LABEL_ALL = "六大学科（全部）"
COLORS = [
    "#0B63CE", "#16A4D8", "#0E9F6E", "#7C3AED", "#F59E0B",
    "#E83E8C", "#65A30D", "#DC2626", "#475569", "#14B8A6",
]


_PLOTLY_RIGHT_BOUNDARY_GUARD = st.components.v2.component(
    "plotly_right_boundary_guard",
    js=r"""
export default function(component) {
  const { data } = component;
  const latestDate = new Date(`${data.latestDate}T00:00:00`).getTime();
  const attached = new Map();
  let stopped = false;

  const plotlyDate = (timestamp) => {
    const value = new Date(timestamp);
    const pad = (part) => String(part).padStart(2, "0");
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
      + `T${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`;
  };

  const attach = () => {
    if (stopped) return;
    for (const selector of data.chartSelectors) {
      const chart = document.querySelector(`${selector} .js-plotly-plot`);
      if (!chart || attached.has(chart) || typeof chart.on !== "function") continue;

      let correcting = false;
      let animationFrame = null;
      const selectedTraces = new Set();
      const constrainRightEdge = () => {
        animationFrame = null;
        if (correcting) return;
        const range = chart._fullLayout?.xaxis?.range;
        if (!Array.isArray(range) || range.length !== 2) return;

        const currentStart = new Date(range[0]).getTime();
        const currentEnd = new Date(range[1]).getTime();
        if (!Number.isFinite(currentStart) || !Number.isFinite(currentEnd)) return;
        if (currentEnd <= latestDate + 1) return;

        const visibleSpan = currentEnd - currentStart;
        const correctedStart = plotlyDate(latestDate - visibleSpan);
        const correctedEnd = `${data.latestDate}T00:00:00`;
        const plotly = globalThis.Plotly;
        if (!plotly?.relayout) return;

        correcting = true;
        Promise.resolve(plotly.relayout(chart, {
          "xaxis.range[0]": correctedStart,
          "xaxis.range[1]": correctedEnd,
          "xaxis.autorange": false,
        })).finally(() => {
          correcting = false;
        });
      };
      const onRelayout = () => {
        if (correcting || animationFrame !== null) return;
        animationFrame = requestAnimationFrame(constrainRightEdge);
      };
      const onLegendClick = (event) => {
        const plotly = globalThis.Plotly;
        if (!plotly?.restyle) return false;
        if (selectedTraces.has(event.curveNumber)) {
          selectedTraces.delete(event.curveNumber);
        } else {
          selectedTraces.add(event.curveNumber);
        }
        const traceIndices = chart.data.map((_, index) => index);
        const visibility = traceIndices.map(
          (index) => selectedTraces.has(index) ? true : "legendonly"
        );
        plotly.restyle(chart, { visible: visibility }, traceIndices);
        return false;
      };
      const onLegendDoubleClick = () => false;

      chart.on("plotly_relayout", onRelayout);
      chart.on("plotly_legendclick", onLegendClick);
      chart.on("plotly_legenddoubleclick", onLegendDoubleClick);
      attached.set(chart, { onRelayout, onLegendClick, onLegendDoubleClick });
      constrainRightEdge();
    }
  };

  const observer = new MutationObserver(attach);
  observer.observe(document.body, { childList: true, subtree: true });
  const retryTimer = window.setInterval(attach, 100);
  attach();

  return () => {
    stopped = true;
    observer.disconnect();
    window.clearInterval(retryTimer);
    for (const [chart, listeners] of attached) {
      if (typeof chart.removeListener === "function") {
        chart.removeListener("plotly_relayout", listeners.onRelayout);
        chart.removeListener("plotly_legendclick", listeners.onLegendClick);
        chart.removeListener("plotly_legenddoubleclick", listeners.onLegendDoubleClick);
      }
    }
    attached.clear();
  };
}
""",
)


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


@st.cache_data(ttl="5m", max_entries=48, show_spinner=False)
def _load_v15_region(
    path: str,
    signature: tuple[int, int],
    region_code: str,
    period_days: int,
    field_id: str | None,
    sort_by: str,
) -> dict[str, Any]:
    del signature
    return get_v15_regional_dashboard(
        path,
        region_code=region_code,
        period_days=period_days,
        field_id=field_id,
        sort_by=sort_by,
    )


def _load_dashboard(
    path: str,
    signature: tuple[int, int],
    region_code: str,
    period_days: int,
    field_id: str | None,
    sort_by: str,
) -> dict[str, Any]:
    if region_code == "GLOBAL":
        return _load_v14(path, signature, period_days, field_id, sort_by)
    return _load_v15_region(
        path, signature, region_code, period_days, field_id, sort_by
    )


@st.cache_data(ttl="5m", max_entries=96, show_spinner=False)
def _load_citations(
    path: str,
    signature: tuple[int, int],
    region_code: str,
    period_days: int,
    topic_id: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    del signature
    return get_citation_ranking(
        path,
        region_code=region_code,
        period_days=period_days,
        topic_id=topic_id,
        window_start=window_start,
        window_end=window_end,
    )


def _on_topic_select() -> None:
    event = st.session_state.get("v16_topic_table_event")
    topic_ids = st.session_state.get("v16_topic_table_ids", [])
    rows = event.selection.rows if event is not None else []
    if rows and 0 <= rows[0] < len(topic_ids):
        st.session_state["v16_selected_topic_id"] = topic_ids[rows[0]]


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


def _citation_table_html(papers: pd.DataFrame, period_days: int) -> str:
    rows: list[str] = []
    for rank, row in enumerate(papers.itertuples(index=False), start=1):
        doi = str(row.doi).strip() if pd.notna(row.doi) else ""
        fallback = str(row.openalex_url).strip()
        link = doi or fallback
        if urlparse(link).scheme != "https":
            link = fallback if urlparse(fallback).scheme == "https" else "https://openalex.org"
        venue = str(row.venue).strip() if pd.notna(row.venue) else "未知来源"
        published = pd.to_datetime(row.publication_date, errors="coerce")
        published_label = published.strftime("%Y-%m-%d") if pd.notna(published) else "日期未知"
        rows.append(
            "<tr>"
            f'<td class="citation-rank">{rank:02d}</td>'
            '<td class="citation-paper">'
            f'<a href="{escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">'
            f'{escape(str(row.title))}</a>'
            f'<span>{escape(venue)} · {published_label}</span>'
            "</td>"
            f'<td class="citation-count">{int(row.window_citation_count):,}</td>'
            "</tr>"
        )
    return f"""
    <style>
      .citation-table-wrap {{
        border: 1px solid #DCE6F2;
        border-radius: 6px;
        overflow: hidden;
        background: #FFFFFF;
      }}
      .citation-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
      .citation-table th {{
        padding: 9px 10px;
        background: #EAF1FA;
        color: #334E68;
        font-size: 13px;
        font-weight: 650;
        text-align: left;
      }}
      .citation-table td {{
        padding: 8px 10px;
        border-top: 1px solid #DFE7F1;
        color: #102A43;
        font-size: 13px;
        vertical-align: top;
      }}
      .citation-table .citation-rank {{ width: 42px; font-weight: 650; }}
      .citation-table .citation-count {{
        width: 94px;
        text-align: right;
        font-weight: 700;
        white-space: nowrap;
      }}
      .citation-paper a {{
        display: block;
        color: #0B4F9C;
        font-weight: 650;
        line-height: 1.3;
        text-decoration: none;
        overflow-wrap: anywhere;
      }}
      .citation-paper a:hover {{ text-decoration: underline; }}
      .citation-paper span {{
        display: block;
        margin-top: 2px;
        color: #6B7C93;
        font-size: 11px;
        line-height: 1.25;
        overflow-wrap: anywhere;
      }}
      @media (max-width: 640px) {{
        .citation-table th, .citation-table td {{ padding: 7px 8px; }}
        .citation-table .citation-rank {{ width: 34px; }}
        .citation-table .citation-count {{ width: 76px; }}
      }}
    </style>
    <div class="citation-table-wrap">
      <table class="citation-table">
        <thead><tr><th class="citation-rank">排名</th><th>论文</th>
        <th class="citation-count">近{period_days}天被引</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


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
        margin={"l": 60, "r": 42, "t": 8, "b": 92},
        hovermode="closest",
        dragmode="pan",
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
        tickmode="array",
        tickvals=tick_values,
        ticktext=tick_text,
        tickangle=0,
        automargin=True,
        ticklabeloverflow="allow",
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
                customdata=customdata, connectgaps=False, cliponaxis=False,
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
                customdata=customdata, connectgaps=False, cliponaxis=False,
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

control_columns = st.columns([1.0, 1.15, 1.5, 1.1, 1.15], gap="small")
with control_columns[0]:
    region_code = st.segmented_control(
        "地区范围", ["GLOBAL", "CN", "US"], default="GLOBAL", key="v15_region"
    )
    if region_code not in {"GLOBAL", "CN", "US"}:
        region_code = "GLOBAL"
with control_columns[1]:
    period_label = st.segmented_control(
        "观察窗口", ["近90天", "近360天"], default="近90天", key="v14_period"
    )
with control_columns[2]:
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
with control_columns[3]:
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
    result = _load_dashboard(
        str(db_path), signature, str(region_code), period_days,
        field_ids[field_label], sort_by,
    )
with control_columns[4]:
    st.text_input(
        "更新时间", value=_display_time(result.get("metrics", {}).get("latest_success_at")),
        disabled=True, key="v14_updated_at",
    )

if result["status"] == "unavailable":
    st.error(
        (
            "V1.4 分类版本尚未导入当前数据库，首页不会回退到旧版分类。"
            if region_code == "GLOBAL"
            else f"{region_code} 区域数据尚未完成同批采集和发布。"
        ),
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
        with st.container(key=f"kpi_v14_{key}", height="stretch"):
            st.markdown(f"**{label}**")
            st.markdown(f'<div class="radar-kpi-value">{value}</div>', unsafe_allow_html=True)
            st.caption(caption)

region_names = {"GLOBAL": "全球", "CN": "中国", "US": "美国"}
st.html(
    f'<div class="radar-section-label">{region_names[str(region_code)]}科研热点监测</div>'
)
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

if not chart_data.empty:
    _PLOTLY_RIGHT_BOUNDARY_GUARD(
        key=(
            f"v14_plotly_boundary_{region_code}_{period_days}_"
            f"{field_ids[field_label] or 'all'}"
        ),
        data={
            "latestDate": pd.Timestamp(metrics["data_through"]).strftime("%Y-%m-%d"),
            "chartSelectors": [
                ".st-key-v14_works_chart",
                ".st-key-v14_growth_chart",
            ],
        },
    )

st.caption(
    f"地区：{region_names[str(region_code)]} · 数据截止：{metrics['data_through']} · "
    "来源：OpenAlex · 口径：core corpus、primary_topic.id、publication_date"
    + (
        "、作者署名机构国家。"
        if region_code in {"CN", "US"}
        else "。"
    )
    + "最新日期可能仍在收录中。"
)

ranking_top10 = display_ranking.head(10).reset_index(drop=True)
topic_ids = ranking_top10["topic_id"].astype(str).tolist()
selected_topic_id = str(st.session_state.get("v16_selected_topic_id", ""))
if selected_topic_id not in topic_ids and topic_ids:
    selected_topic_id = topic_ids[0]
    st.session_state["v16_selected_topic_id"] = selected_topic_id
st.session_state["v16_topic_table_ids"] = topic_ids

ranking_columns = st.columns(2, gap="medium")
with ranking_columns[0]:
    with st.container(key="panel_v16_topic_ranking", border=True, height="stretch"):
        st.subheader(":material/emoji_events: 科研热点 TOP 10")
        ranking_scope = (
            "六学科范围" if result["field_id"] is None else str(field_label).split(" · ")[0]
        )
        ranking_basis = "最新周期增长率" if sort_by == "growth" else f"近{period_days}天 Works"
        st.caption(f"{ranking_scope}内按{ranking_basis}排名；点击行查看引用榜")
        table = ranking_top10.copy()
        table["Topic"] = table.apply(_topic_label, axis=1)
        table["所属学科"] = table["field_name_zh"].fillna(table["field_name"])
        table[f"近{period_days}天发文"] = table["period_works_count"]
        table["增长率"] = pd.to_numeric(
            table["period_growth_rate"], errors="coerce"
        ).mul(100)
        table = table.rename(columns={"rank": "排名"})[
            ["排名", "Topic", "所属学科", f"近{period_days}天发文", "增长率"]
        ]
        selected_mask = ranking_top10["topic_id"].astype(str).eq(selected_topic_id)
        styled_table = table.style.apply(
            lambda row: [
                "background-color: #E7F1FF; color: #102A43;"
                if selected_mask.iloc[row.name] else ""
            ] * len(row),
            axis=1,
        )
        st.dataframe(
            styled_table,
            hide_index=True,
            on_select=_on_topic_select,
            selection_mode="single-row",
            key="v16_topic_table_event",
            height=448,
            column_config={
                "排名": st.column_config.NumberColumn(width="small", format="%02d"),
                "Topic": st.column_config.TextColumn(width="medium"),
                "所属学科": st.column_config.TextColumn(
                    width="small", help="学科中文名称"
                ),
                f"近{period_days}天发文": st.column_config.NumberColumn(
                    width="small", format="compact"
                ),
                "增长率": st.column_config.NumberColumn(width="small", format="%.1f%%"),
            },
        )

detail = (
    ranking_top10.loc[ranking_top10["topic_id"].astype(str).eq(selected_topic_id)].iloc[0]
    if topic_ids else None
)
with ranking_columns[1]:
    with st.container(key="panel_v16_citation_ranking", border=True, height="stretch"):
        if detail is None:
            st.subheader(":material/article: 高被引论文 TOP 10")
            st.info("当前筛选范围没有 Topic。", icon=":material/info:")
        else:
            detail_name = _topic_label(detail)
            st.subheader(f":material/article: {detail_name} · 高被引论文 TOP 10")
            st.caption(
                f"Topic ID：{selected_topic_id} · 按引用方作品发表日期统计窗口内新增引用；"
                "引用方范围为全球"
            )
            citation_result = _load_citations(
                str(db_path), signature, str(region_code), period_days,
                selected_topic_id, str(detail["window_start"]), str(detail["window_end"]),
            )
            if citation_result["status"] != "available":
                st.info(
                    "引用数据暂不可用。现有发文榜可正常浏览；引用批次完整发布后将自动显示。",
                    icon=":material/database_off:",
                )
            elif citation_result["works"].empty:
                st.info("当前窗口内无符合条件且至少被引一次的论文。", icon=":material/search_off:")
            else:
                papers = citation_result["works"].copy()
                st.html(_citation_table_html(papers, period_days))
            st.caption(
                f"统计区间：{detail['window_start']} 至 {detail['window_end']}（含起止日） · "
                f"数据来源：OpenAlex · 引用数据更新时间："
                f"{_display_time(citation_result.get('query_as_of'))}"
            )
