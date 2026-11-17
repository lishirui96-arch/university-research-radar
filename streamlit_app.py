from pathlib import Path

import streamlit as st

from storage import initialize_database
from ui_styles import apply_global_styles


APP_DIR = Path(__file__).parent

st.set_page_config(
    page_title="全球高校科研热点雷达",
    page_icon=":material/radar:",
    layout="wide",
)

initialize_database()
apply_global_styles(APP_DIR)

page = st.navigation(
    [
        st.Page(
            APP_DIR / "app_pages/global_dashboard.py",
            title="首页",
            icon=":material/home:",
            default=True,
        ),
        st.Page(
            APP_DIR / "app_pages/domain_scan.py",
            title="科研热点发现",
            icon=":material/radar:",
        ),
        st.Page(
            APP_DIR / "app_pages/topic_analysis.py",
            title="科研成果追踪",
            icon=":material/biotech:",
        ),
        st.Page(
            APP_DIR / "app_pages/history.py",
            title="历史记录",
            icon=":material/history:",
        ),
        st.Page(
            APP_DIR / "app_pages/data_management.py",
            title="数据管理",
            icon=":material/database:",
        ),
    ],
    position="top",
)

page.run()
