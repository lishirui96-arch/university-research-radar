from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st


@lru_cache(maxsize=2)
def _asset_data_uri(path: str) -> str:
    asset = Path(path)
    encoded = base64.b64encode(asset.read_bytes()).decode("ascii")
    return f"data:image/{asset.suffix.lstrip('.')};base64,{encoded}"


def apply_global_styles(app_dir: Path) -> None:
    hero_uri = _asset_data_uri(str(app_dir / "assets" / "research-network-hero.png"))
    st.html(
        f"""
        <style>
        :root {{
            --radar-navy: #071f3b;
            --radar-blue: #0b63ce;
            --radar-cyan: #16a4d8;
            --radar-ink: #14263b;
            --radar-muted: #60758e;
            --radar-surface: #ffffff;
            --radar-border: #dbe7f3;
            --radar-canvas: #f3f7fc;
        }}

        html, body, [class*="css"] {{ letter-spacing: 0 !important; }}
        .stApp {{ background: var(--radar-canvas); }}
        [data-testid="stAppViewContainer"] {{ background: var(--radar-canvas); }}
        [data-testid="stMainBlockContainer"] {{
            max-width: 1760px;
            padding-top: 1.1rem;
            padding-bottom: 3rem;
        }}

        header[data-testid="stHeader"] {{
            background: var(--radar-navy);
            border-bottom: 1px solid rgba(255,255,255,.12);
            min-height: 3.5rem;
        }}
        header[data-testid="stHeader"]::before {{
            content: "全球高校科研热点与产业创新情报平台";
            color: #ffffff;
            font-size: 1.02rem;
            font-weight: 700;
            position: absolute;
            left: 1.25rem;
            top: 1rem;
            white-space: nowrap;
        }}
        header[data-testid="stHeader"] nav {{ padding-left: 24rem; }}
        header[data-testid="stHeader"] a,
        header[data-testid="stHeader"] button,
        header[data-testid="stHeader"] span {{ color: #eef6ff !important; }}

        .st-key-research_hero {{
            background-image: url("{hero_uri}");
            background-position: center;
            background-size: cover;
            border: 1px solid rgba(66, 160, 224, .28);
            border-radius: 6px;
            box-shadow: 0 14px 34px rgba(7, 31, 59, .16);
            min-height: 245px;
            overflow: hidden;
            padding: 3.25rem 3rem 2.5rem;
        }}
        .radar-hero-copy {{ max-width: 760px; }}
        .radar-hero-kicker {{
            color: #7dd3fc;
            font-size: .78rem;
            font-weight: 700;
            margin-bottom: .8rem;
            text-transform: uppercase;
        }}
        .radar-hero-copy h1 {{
            color: #ffffff;
            font-size: 2.25rem;
            line-height: 1.24;
            margin: 0 0 .85rem;
            max-width: 700px;
        }}
        .radar-hero-copy p {{
            color: #c6d9ed;
            font-size: 1rem;
            line-height: 1.7;
            margin: 0;
            max-width: 680px;
        }}

        [class*="st-key-kpi_"] {{
            background: #ffffff;
            border: 1px solid var(--radar-border);
            border-radius: 7px;
            box-shadow: 0 7px 20px rgba(37, 77, 121, .07);
            min-height: 178px;
            padding: 1rem 1.1rem .8rem;
        }}
        [class*="st-key-kpi_"] [data-testid="stMetricValue"] {{
            color: var(--radar-ink);
            font-size: 2rem;
            font-weight: 750;
        }}
        [class*="st-key-kpi_"] [data-testid="stMetricLabel"] {{
            color: #2d4764;
            font-size: .88rem;
            font-weight: 650;
        }}

        [class*="st-key-panel_"], .st-key-taxonomy_panel, .st-key-technology_panel {{
            background: #ffffff;
            border: 1px solid var(--radar-border);
            border-radius: 7px;
            box-shadow: 0 7px 20px rgba(37, 77, 121, .06);
            padding: 1rem 1.1rem 1.1rem;
        }}
        [class*="st-key-panel_"] h3,
        .st-key-taxonomy_panel h3,
        .st-key-technology_panel h3 {{
            color: var(--radar-ink);
            font-size: 1.08rem;
        }}
        .radar-section-label {{
            color: #1b3857;
            font-size: 1.1rem;
            font-weight: 750;
            margin: .2rem 0 .4rem;
        }}
        .radar-data-note {{
            color: var(--radar-muted);
            font-size: .75rem;
            line-height: 1.45;
        }}
        .radar-hot-rank {{
            background: #eaf3ff;
            border-radius: 999px;
            color: #0b63ce;
            display: inline-block;
            font-weight: 750;
            min-width: 1.75rem;
            padding: .16rem .45rem;
            text-align: center;
        }}
        .st-key-taxonomy_panel button {{
            height: auto;
            border-radius: 5px;
            justify-content: flex-start;
            min-height: 2.45rem;
            text-align: left;
            width: 100%;
        }}
        .st-key-taxonomy_panel button p {{
            line-height: 1.25;
            overflow: visible;
            text-overflow: clip;
            white-space: normal;
            word-break: break-word;
        }}
        .st-key-taxonomy_panel .stMarkdownEllipsis {{
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: normal !important;
        }}
        .st-key-technology_panel [data-testid="stMetric"] {{
            background: #f6faff;
            border: 1px solid #e0ebf7;
            border-radius: 6px;
            padding: .65rem .8rem;
        }}

        @media (max-width: 900px) {{
            header[data-testid="stHeader"]::before {{ display: none; }}
            header[data-testid="stHeader"] nav {{ padding-left: 0; }}
            [data-testid="stMainBlockContainer"] {{ padding: .8rem .8rem 2rem; }}
            .st-key-research_hero {{ min-height: 310px; padding: 2rem 1.35rem; }}
            .radar-hero-copy h1 {{ font-size: 1.75rem; }}
            .radar-hero-copy p {{ font-size: .9rem; max-width: 92%; }}
            [class*="st-key-kpi_"] {{ min-height: 155px; }}
        }}
        </style>
        """
    )
