from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_repository import load_daily_collection_data
from storage import database_path


STATUS_LABELS = {
    "pending": "等待运行",
    "running": "运行中",
    "succeeded": "成功",
    "partial": "部分完成",
    "failed": "失败",
    "skipped": "已跳过",
    "provisional": "初步收录",
    "rechecking": "历史回查",
    "stabilizing": "趋于稳定",
    "stable": "稳定",
}


@st.cache_data(ttl="2m", max_entries=8, show_spinner=False)
def _load_daily(path: str, signature: tuple[int, int]) -> dict[str, Any]:
    del signature
    return load_daily_collection_data(path)


def _display_time(value: Any) -> str:
    if value is None or pd.isna(value):
        return "--"
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return str(value)
    return parsed.tz_convert("Asia/Singapore").strftime("%Y-%m-%d %H:%M")


def _status(value: Any) -> str:
    return STATUS_LABELS.get(str(value), str(value) if value else "--")


def _reasons(value: Any) -> str:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(value or "--")
    return "、".join(str(item) for item in parsed) or "--"


db_path = Path(database_path())
signature = (
    (db_path.stat().st_mtime_ns, db_path.stat().st_size)
    if db_path.exists()
    else (0, 0)
)
data = _load_daily(str(db_path), signature)

st.title("每日自动更新")
st.caption("查看工作日自动采集、历史回查、数据质量和 OpenAlex 请求预算。页面只读本地数据库。")

with st.container(border=True):
    schedule_col, window_col, safety_col = st.columns(3, gap="medium")
    schedule_col.markdown(":material/schedule: **运行计划**")
    schedule_col.caption("周一至周五 09:00 · Windows 本地时区")
    window_col.markdown(":material/calendar_view_week: **回查窗口**")
    window_col.caption("D-1 · D-2 · D-3 · D-7 · D-14")
    safety_col.markdown(":material/verified_user: **发布门禁**")
    safety_col.caption("完整分页、质量检查和外键检查通过后发布")

latest_run = data["latest_run"]
observations = data["observations"].copy()
latest_observation = None if observations.empty else observations.iloc[0]

with st.container(horizontal=True):
    st.metric(
        "最近任务",
        "尚未运行" if latest_run is None else _status(latest_run.get("status")),
        border=True,
    )
    st.metric(
        "最近发表日期",
        "--" if latest_observation is None else str(latest_observation["publication_date"]),
        border=True,
    )
    st.metric(
        "完整命中",
        "--" if latest_observation is None else f"{int(latest_observation['meta_count']):,}",
        delta=(None if latest_observation is None or pd.isna(latest_observation["count_delta"])
               else int(latest_observation["count_delta"])),
        border=True,
    )
    st.metric(
        "API 请求",
        "--" if latest_run is None else f"{int(latest_run.get('request_count') or 0):,}",
        border=True,
    )
    st.metric(
        "剩余额度",
        "--" if latest_run is None or pd.isna(latest_run.get("rate_remaining"))
        else f"{int(latest_run['rate_remaining']):,}",
        border=True,
    )

if latest_run is None:
    st.warning(
        "正式数据库尚未产生每日自动采集运行。当前仅显示已迁移的历史日期观察；"
        "测试副本数据不会进入正式统计。",
        icon=":material/pending_actions:",
    )
else:
    completed = int(latest_run.get("completed_windows") or 0)
    total = int(latest_run.get("window_count") or 0)
    st.success(
        f"最近任务于 {_display_time(latest_run.get('completed_at'))} 完成，"
        f"日期窗口 {completed}/{total}，重试 {int(latest_run.get('retry_count') or 0)} 次，"
        f"响应流量 {float(latest_run.get('response_bytes') or 0) / 1024 / 1024:.1f} MB。",
        icon=":material/check_circle:",
    )

st.subheader("发表日期观察")
if observations.empty:
    st.info("尚无可展示的日期观察。", icon=":material/event_busy:")
else:
    observations["observed_at"] = pd.to_datetime(
        observations["observed_at"], errors="coerce", utc=True
    )
    observations["coverage_percent"] = observations["coverage_rate"] * 100
    if len(observations) > 1:
        trend = (
            alt.Chart(observations.sort_values("observed_at"))
            .mark_line(point=True, strokeWidth=2.5)
            .encode(
                x=alt.X("observed_at:T", title="观察时间"),
                y=alt.Y("meta_count:Q", title="OpenAlex 完整命中"),
                color=alt.Color("publication_date:N", title="发表日期"),
                tooltip=[
                    alt.Tooltip("publication_date:N", title="发表日期"),
                    alt.Tooltip("observed_at:T", title="观察时间"),
                    alt.Tooltip("meta_count:Q", title="完整命中", format=","),
                    alt.Tooltip("count_delta:Q", title="计数变化", format="+,.0f"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(trend, alt="不同发表日期的 OpenAlex 完整命中变化")

    observation_view = observations[
        [
            "publication_date", "observed_at", "meta_count", "previous_meta_count",
            "count_delta", "sampled_count", "coverage_percent", "inserted_works",
            "updated_works", "unchanged_works", "request_count", "retry_count",
            "quality_status", "stability_status", "published",
        ]
    ].copy()
    observation_view["stability_status"] = observation_view["stability_status"].map(_status)
    st.dataframe(
        observation_view,
        hide_index=True,
        alt="每日采集的发表日期观察与质量状态",
        column_config={
            "publication_date": st.column_config.DateColumn("发表日期", pinned=True),
            "observed_at": st.column_config.DatetimeColumn("观察时间"),
            "meta_count": st.column_config.NumberColumn("完整命中", format="%d"),
            "previous_meta_count": st.column_config.NumberColumn("上次命中", format="%d"),
            "count_delta": st.column_config.NumberColumn("计数变化", format="%+d"),
            "sampled_count": st.column_config.NumberColumn("实际采集", format="%d"),
            "coverage_percent": st.column_config.NumberColumn("覆盖率", format="%.1f%%"),
            "inserted_works": st.column_config.NumberColumn("新增 Works", format="%d"),
            "updated_works": st.column_config.NumberColumn("更新 Works", format="%d"),
            "unchanged_works": st.column_config.NumberColumn("未变化", format="%d"),
            "request_count": st.column_config.NumberColumn("API 请求", format="%d"),
            "retry_count": st.column_config.NumberColumn("重试", format="%d"),
            "quality_status": st.column_config.TextColumn("质量"),
            "stability_status": st.column_config.TextColumn("稳定状态"),
            "published": st.column_config.CheckboxColumn("已发布"),
        },
    )

runs = data["runs"].copy()
st.subheader("任务运行与日期窗口")
if runs.empty:
    st.info("尚无正式每日任务运行记录。", icon=":material/history_toggle_off:")
else:
    run_ids = runs["run_id"].astype(str).tolist()
    selected_run = st.selectbox(
        "选择任务",
        run_ids,
        format_func=lambda run_id: (
            f"{runs.loc[runs['run_id'] == run_id, 'run_date'].iloc[0]} · "
            f"{_status(runs.loc[runs['run_id'] == run_id, 'status'].iloc[0])} · {run_id}"
        ),
        key="daily_selected_run",
    )
    run_view = runs.copy()
    run_view["status"] = run_view["status"].map(_status)
    st.dataframe(
        run_view,
        hide_index=True,
        alt="每日自动采集任务运行历史",
        column_config={
            "run_id": st.column_config.TextColumn("任务编号", pinned=True),
            "run_date": st.column_config.DateColumn("运行日期"),
            "status": st.column_config.TextColumn("状态"),
            "started_at": st.column_config.DatetimeColumn("开始时间"),
            "completed_at": st.column_config.DatetimeColumn("结束时间"),
            "request_count": st.column_config.NumberColumn("API 请求", format="%d"),
            "response_bytes": st.column_config.NumberColumn("响应字节", format="%d"),
            "retry_count": st.column_config.NumberColumn("重试", format="%d"),
            "rate_remaining": st.column_config.NumberColumn("剩余额度", format="%d"),
        },
    )
    windows = data["windows"]
    selected_windows = windows[windows["run_id"].astype(str) == selected_run].copy()
    if not selected_windows.empty:
        selected_windows["reasons"] = selected_windows["reasons_json"].map(_reasons)
        selected_windows["status"] = selected_windows["status"].map(_status)
        st.dataframe(
            selected_windows[
                [
                    "publication_date", "reasons", "priority", "preflight_meta_count",
                    "estimated_requests", "status", "skip_reason", "error",
                ]
            ],
            hide_index=True,
            alt="所选每日任务的日期回查窗口",
            column_config={
                "publication_date": st.column_config.DateColumn("发表日期", pinned=True),
                "reasons": st.column_config.TextColumn("窗口原因"),
                "priority": st.column_config.NumberColumn("优先级"),
                "preflight_meta_count": st.column_config.NumberColumn("预检命中", format="%d"),
                "estimated_requests": st.column_config.NumberColumn("预计请求", format="%d"),
                "status": st.column_config.TextColumn("状态"),
                "skip_reason": st.column_config.TextColumn("跳过原因", width="large"),
                "error": st.column_config.TextColumn("错误", width="large"),
            },
        )

type_data = data["work_types"].copy()
st.subheader("Work 类型分布")
if type_data.empty:
    st.info(
        "当前已发布历史批次尚未保存 Work 类型快照。首次正式每日采集后将自动出现。",
        icon=":material/category:",
    )
else:
    latest_batch = str(type_data.iloc[0]["batch_id"])
    latest_types = type_data[type_data["batch_id"].astype(str) == latest_batch].copy()
    chart = (
        alt.Chart(latest_types.head(15))
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("work_count:Q", title="Works"),
            y=alt.Y("raw_type:N", title=None, sort="-x"),
            color=alt.Color("normalized_group:N", title="标准分组"),
            tooltip=["raw_type:N", "normalized_group:N", "work_count:Q"],
        )
        .properties(height=360)
    )
    st.altair_chart(chart, alt="最近发布批次的 OpenAlex Work 原始类型分布")
    st.caption("原始类型按 OpenAlex 保存；类型分组不代表同行评审状态。")

quality = data["quality"]
with st.expander("数据质量检查", icon=":material/fact_check:"):
    if quality.empty:
        st.info("尚无每日采集质量检查记录。")
    else:
        st.dataframe(
            quality,
            hide_index=True,
            alt="每日采集批次的数据质量检查结果",
            column_config={
                "publication_date": st.column_config.DateColumn("发表日期"),
                "check_name": st.column_config.TextColumn("检查项", pinned=True),
                "severity": st.column_config.TextColumn("级别"),
                "status": st.column_config.TextColumn("结果"),
                "details": st.column_config.TextColumn("说明", width="large"),
                "created_at": st.column_config.DatetimeColumn("检查时间"),
            },
        )

if st.button("刷新每日更新状态", icon=":material/refresh:"):
    _load_daily.clear()
    st.rerun()
