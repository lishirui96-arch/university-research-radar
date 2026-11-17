from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_repository import load_topic_observations
from storage import database_path


@st.cache_data(ttl="5m", max_entries=8, show_spinner=False)
def _load(path: str, signature: tuple[int, int]) -> pd.DataFrame:
    del signature
    return load_topic_observations(path)


st.title("主题深度分析")
st.caption("基于已经成功保存的扫描结果进行回溯；新主题可从领域扫描发起在线深挖。")

db_path = Path(database_path())
signature = (db_path.stat().st_mtime_ns, db_path.stat().st_size) if db_path.exists() else (0, 0)
observations = _load(str(db_path), signature)

if observations.empty:
    st.info("当前数据库没有可分析的成功主题记录。", icon=":material/info:")
    if st.button("前往领域扫描", type="primary", icon=":material/search:"):
        st.session_state["run_mode_control"] = "主题深挖"
        st.switch_page("app_pages/domain_scan.py")
    st.stop()

with st.container(horizontal=True, vertical_alignment="bottom"):
    topic = st.selectbox(
        "研究主题",
        sorted(observations["topic"].dropna().unique().tolist()),
        key="analysis_topic",
    )
    regions = observations.loc[observations["topic"] == topic, "region"].dropna().unique().tolist()
    region = st.selectbox("地域", regions, key="analysis_region")
    if st.button("发起新的在线深挖", icon=":material/search:"):
        st.session_state["run_mode_control"] = "主题深挖"
        st.switch_page("app_pages/domain_scan.py")

view = observations[
    (observations["topic"] == topic) & (observations["region"] == region)
].sort_values("completed_at", ascending=False)
latest = view.iloc[0]

with st.container(horizontal=True):
    st.metric(
        "观察期成果",
        "--" if pd.isna(latest["current_count"]) else f"{int(latest['current_count']):,}",
        border=True,
    )
    st.metric(
        "采样量",
        "--" if pd.isna(latest["sampled_count"]) else f"{int(latest['sampled_count']):,}",
        border=True,
    )
    st.metric(
        "数据置信度",
        "--" if pd.isna(latest["data_confidence"]) else f"{latest['data_confidence']:.0f}/100",
        border=True,
    )
    st.metric(
        "评分覆盖",
        "--" if pd.isna(latest["score_coverage"]) else f"{latest['score_coverage']:.0%}",
        border=True,
    )

st.info(
    f"最新趋势判断：{latest['trend_label'] or '证据不足'}。"
    "综合热度仅用于同领域辅助观察，低覆盖结果不应进入正式排名。",
    icon=":material/analytics:",
)

with st.container(border=True):
    st.subheader("历史观察")
    display = view[
        [
            "completed_at",
            "current_count",
            "sampled_count",
            "coverage_rate",
            "growth",
            "acceleration",
            "trend_label",
            "heat_score",
            "score_coverage",
            "data_confidence",
        ]
    ]
    st.dataframe(
        display,
        hide_index=True,
        column_config={
            "completed_at": st.column_config.DatetimeColumn("扫描时间"),
            "current_count": st.column_config.NumberColumn("完整命中"),
            "sampled_count": st.column_config.NumberColumn("采样量"),
            "coverage_rate": st.column_config.ProgressColumn("采样覆盖", min_value=0, max_value=1),
            "growth": st.column_config.NumberColumn("调整后增长", format="%.1%%"),
            "acceleration": st.column_config.NumberColumn("近期加速度", format="%.1%%"),
            "trend_label": st.column_config.TextColumn("趋势"),
            "heat_score": st.column_config.NumberColumn("综合热度", format="%.1f"),
            "score_coverage": st.column_config.ProgressColumn("评分覆盖", min_value=0, max_value=1),
            "data_confidence": st.column_config.ProgressColumn("数据置信度", min_value=0, max_value=100),
        },
    )

with st.expander("检索证据", icon=":material/manage_search:"):
    st.code(str(latest["query_string"] or "未保存检索式"), language=None)
