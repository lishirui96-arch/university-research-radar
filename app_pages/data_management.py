from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from dashboard_repository import load_database_status
from storage import database_path


@st.cache_data(ttl="2m", max_entries=8, show_spinner=False)
def _load_status(path: str, signature: tuple[int, int]) -> dict:
    del signature
    return load_database_status(path)


st.title("数据管理")
st.caption("查看本地数据库、长期数据表和完整性状态。")

db_path = Path(database_path())
signature = (db_path.stat().st_mtime_ns, db_path.stat().st_size) if db_path.exists() else (0, 0)
status = _load_status(str(db_path), signature)

if not status["exists"]:
    st.error(f"数据库不存在：{status['path']}", icon=":material/database_off:")
    st.stop()

with st.container(horizontal=True):
    st.metric("Schema 版本", str(status["schema_version"] or "--"), border=True)
    st.metric("数据库大小", f"{status['size_bytes'] / 1024:.1f} KB", border=True)
    st.metric("完整性检查", str(status["integrity"]), border=True)
    st.metric("外键违规", f"{status['foreign_key_violations']:,}", border=True)

if status["integrity"] == "ok" and status["foreign_key_violations"] == 0:
    st.success("数据库完整性检查通过。", icon=":material/check_circle:")
else:
    st.error("数据库完整性检查未通过，请停止采集并先执行备份和诊断。")

with st.container(border=True):
    st.subheader("数据库位置")
    st.code(status["path"], language=None)
    st.caption(
        "最后修改："
        + datetime.fromtimestamp(status["modified_at"]).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    )

with st.container(border=True):
    st.subheader("数据表覆盖")
    tables = status["tables"].copy()
    st.dataframe(
        tables,
        hide_index=True,
        column_config={
            "table": st.column_config.TextColumn("数据表", pinned=True),
            "rows": st.column_config.NumberColumn("记录数", format="%d"),
        },
    )

if st.button("刷新数据库状态", icon=":material/refresh:"):
    _load_status.clear()
    st.rerun()

st.info(
    "全球总览需要预计算的全学科聚合快照。当前实体表为空时，首页会显示数据不足，"
    "不会把示例数据或单次领域扫描当作全球统计。",
    icon=":material/info:",
)
