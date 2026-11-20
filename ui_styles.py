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
            padding-top: .9rem;
            padding-bottom: 3rem;
        }}

        header[data-testid="stHeader"] {{
            display: none;
        }}
        .radar-brand-header {{
            align-items: center;
            background: #ffffff;
            border: 1px solid #e4edf6;
            border-radius: 8px;
            box-shadow: 0 5px 18px rgba(28, 73, 121, .07);
            display: grid;
            gap: 1.5rem;
            grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
            margin-bottom: 1rem;
            min-height: 82px;
            padding: .85rem 1.35rem;
        }}
        .radar-brand-lockup {{
            align-items: center;
            display: flex;
            gap: .9rem;
            min-width: 0;
        }}
        .radar-brand-mark {{
            align-items: center;
            background: #0b72e7;
            border-radius: 7px;
            box-shadow: 0 7px 16px rgba(11, 99, 206, .22);
            color: #ffffff;
            display: flex;
            flex: 0 0 46px;
            height: 46px;
            justify-content: center;
        }}
        .radar-brand-glyph {{
            font-size: 1.45rem;
            font-weight: 760;
            line-height: 1;
        }}
        .radar-brand-copy {{
            border-left: 1px solid #cbd9e8;
            min-width: 0;
            padding-left: .9rem;
        }}
        .radar-brand-name {{
            color: #0b2748;
            font-size: 1.05rem;
            font-weight: 760;
            line-height: 1.25;
            white-space: nowrap;
        }}
        .radar-brand-subtitle {{
            color: #6d829a;
            font-size: .66rem;
            font-weight: 700;
            letter-spacing: .06em !important;
            margin-top: .22rem;
        }}
        .radar-home-link {{
            align-items: center;
            background: #0b72e7;
            border-radius: 7px;
            box-shadow: 0 6px 16px rgba(11, 99, 206, .2);
            color: #ffffff !important;
            display: inline-flex;
            font-size: .95rem;
            font-weight: 700;
            gap: .42rem;
            justify-content: center;
            min-height: 42px;
            padding: 0 1.25rem;
            text-decoration: none !important;
        }}
        .radar-home-link:hover {{ background: #075fca; color: #ffffff !important; }}
        .radar-user-entry {{
            align-items: center;
            background: #f1f6fc;
            border: 1px solid #dce8f4;
            border-radius: 50%;
            color: #173f6c;
            cursor: default;
            display: flex;
            height: 42px;
            justify-content: center;
            justify-self: end;
            padding: 0;
            position: relative;
            width: 42px;
        }}
        .radar-user-entry span {{ font-size: 1rem; font-weight: 700; }}

        .st-key-research_hero {{
            background-image:
                linear-gradient(90deg, rgba(3, 27, 58, .98) 0%, rgba(3, 35, 76, .92) 43%, rgba(2, 42, 91, .28) 72%, rgba(0, 42, 91, .06) 100%),
                url("{hero_uri}");
            background-position: center, center right;
            background-size: cover;
            border: 1px solid rgba(66, 160, 224, .28);
            border-radius: 8px;
            box-shadow: 0 14px 34px rgba(7, 31, 59, .16);
            min-height: 260px;
            overflow: hidden;
            padding: 2.35rem 3rem 2.15rem;
        }}
        .radar-hero-copy {{ max-width: 64%; }}
        .radar-hero-kicker {{
            color: #7dd3fc;
            font-size: .76rem;
            font-weight: 700;
            letter-spacing: .04em !important;
            margin-bottom: 1.2rem;
            text-transform: uppercase;
        }}
        .radar-hero-copy h1 {{
            color: #ffffff;
            font-size: 2.45rem;
            font-weight: 760;
            line-height: 1.3;
            margin: 0 0 1rem;
            max-width: 1000px;
        }}
        .radar-hero-copy p {{
            color: #c6d9ed;
            font-size: 1rem;
            line-height: 1.65;
            margin: 0;
            max-width: 800px;
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
        [class*="st-key-kpi_v14_"] {{
            min-height: 155px;
            padding: .9rem 1rem .7rem;
        }}
        .radar-kpi-value {{
            color: var(--radar-ink);
            font-size: clamp(1.15rem, 1.45vw, 1.75rem);
            font-weight: 760;
            line-height: 1.2;
            margin: .45rem 0 .35rem;
            overflow-wrap: anywhere;
        }}
        .st-key-panel_v14_works,
        .st-key-panel_v14_growth,
        .st-key-panel_v14_ranking,
        .st-key-panel_v14_insights,
        .st-key-panel_v14_status {{
            background: #ffffff;
            border-color: var(--radar-border) !important;
            border-radius: 7px;
            box-shadow: 0 7px 20px rgba(37, 77, 121, .06);
        }}
        .st-key-panel_v14_status [data-testid="stMetric"] {{
            background: #f6faff;
            border: 1px solid #e0ebf7;
            border-radius: 6px;
            min-height: 88px;
            padding: .55rem .7rem;
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

        @media (max-width: 1280px) {{
            .radar-brand-name {{ font-size: .95rem; }}
            .radar-hero-copy {{ max-width: 70%; }}
            .radar-hero-copy h1 {{ font-size: 2rem; }}
        }}
        @media (max-width: 900px) {{
            [data-testid="stMainBlockContainer"] {{ padding: .8rem .8rem 2rem; }}
            .radar-brand-header {{
                gap: .75rem;
                grid-template-columns: minmax(0, 1fr) auto auto;
                min-height: 72px;
                padding: .7rem .8rem;
            }}
            .radar-brand-mark {{ flex-basis: 40px; height: 40px; }}
            .radar-brand-name {{ font-size: .82rem; white-space: normal; }}
            .radar-brand-subtitle {{ font-size: .58rem; }}
            .radar-home-link {{ min-height: 38px; padding: 0 .8rem; }}
            .radar-user-entry {{ height: 38px; width: 38px; }}
            .st-key-research_hero {{ min-height: 280px; padding: 2rem 1.35rem; }}
            .radar-hero-copy {{ max-width: 88%; }}
            .radar-hero-copy h1 {{ font-size: 1.75rem; }}
            .radar-hero-copy p {{ font-size: .9rem; max-width: 92%; }}
            [class*="st-key-kpi_"] {{ min-height: 155px; }}
        }}
        @media (max-width: 620px) {{
            .radar-brand-header {{ grid-template-columns: minmax(0, 1fr) auto; }}
            .radar-brand-subtitle {{ display: none; }}
            .radar-home-link {{ display: none; }}
            .radar-brand-mark {{ flex-basis: 38px; height: 38px; }}
            .st-key-research_hero {{
                background-position: center, 64% center;
                min-height: 310px;
            }}
            .radar-hero-copy {{ max-width: 100%; }}
            .radar-hero-copy h1 {{ font-size: 1.55rem; }}
        }}
        </style>
        """
    )
