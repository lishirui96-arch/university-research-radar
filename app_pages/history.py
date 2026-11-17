from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_repository import load_run_queries, load_scan_history
from storage import database_path


@st.cache_data(ttl="2m", max_entries=8, show_spinner=False)
def _load_history(path: str, signature: tuple[int, int]) -> pd.DataFrame:
    del signature
    return load_scan_history(path)


st.title("历史扫描记录")
st.caption("成功与失败运行分别保留；失败运行不会覆盖上一次成功结果。")

db_path = Path(database_path())
signature = (db_path.stat().st_mtime_ns, db_path.stat().st_size) if db_path.exists() else (0, 0)
history = _load_history(str(db_path), signature)

if history.empty:
    st.info("当前没有历史扫描记录。", icon=":material/history:")
    st.stop()

successes = int((history["status"] == "success").sum())
failures = int((history["status"] == "failed").sum())
with st.container(horizontal=True):
    st.metric("扫描运行", f"{len(history):,}", border=True)
    st.metric("成功", f"{successes:,}", border=True)
    st.metric("失败", f"{failures:,}", border=True)
    st.metric("主题指标记录", f"{int(history['topic_rows'].sum()):,}", border=True)

st.dataframe(
    history,
    hide_index=True,
    column_config={
        "run_id": st.column_config.TextColumn("运行编号", pinned=True),
        "status": st.column_config.TextColumn("状态"),
        "run_mode": st.column_config.TextColumn("模式"),
        "domain_profile": st.column_config.TextColumn("领域"),
        "attempted_query": st.column_config.TextColumn("检索范围", width="large"),
        "started_at": st.column_config.DatetimeColumn("开始时间"),
        "completed_at": st.column_config.DatetimeColumn("完成时间"),
        "error": st.column_config.TextColumn("错误", width="large"),
        "topic_rows": st.column_config.NumberColumn("主题记录"),
        "query_rows": st.column_config.NumberColumn("查询记录"),
    },
)

selected_run = st.selectbox(
    "查看运行证据",
    history["run_id"].tolist(),
    format_func=lambda run_id: f"{run_id} · {history.loc[history['run_id'] == run_id, 'attempted_query'].iloc[0]}",
)
queries = load_run_queries(str(db_path), selected_run)
with st.container(border=True):
    st.subheader("来源与检索条件")
    if queries.empty:
        st.info("该运行没有保存查询明细。")
    else:
        st.dataframe(
            queries,
            hide_index=True,
            column_config={
                "source": st.column_config.TextColumn("来源"),
                "topic": st.column_config.TextColumn("主题"),
                "region": st.column_config.TextColumn("地区"),
                "query_string": st.column_config.TextColumn("检索式", width="large"),
                "result_count": st.column_config.NumberColumn("完整命中"),
                "sample_count": st.column_config.NumberColumn("实际采样"),
            },
        )
