from pathlib import Path

import streamlit as st

from storage import initialize_database


APP_DIR = Path(__file__).parent

st.set_page_config(
    page_title="全球高校科研热点雷达",
    page_icon=":material/radar:",
    layout="wide",
)

initialize_database()

page = st.navigation(
    [
        st.Page(
            APP_DIR / "app_pages/global_dashboard.py",
            title="全球科研热点总览",
            icon=":material/public:",
            default=True,
        ),
        st.Page(
            APP_DIR / "app_pages/domain_scan.py",
            title="领域扫描",
            icon=":material/radar:",
        ),
        st.Page(
            APP_DIR / "app_pages/topic_analysis.py",
            title="主题深度分析",
            icon=":material/biotech:",
        ),
        st.Page(
            APP_DIR / "app_pages/history.py",
            title="历史扫描记录",
            icon=":material/history:",
        ),
        st.Page(
            APP_DIR / "app_pages/data_management.py",
            title="数据管理",
            icon=":material/database:",
        ),
    ],
    position="sidebar",
)

page.run()
