from __future__ import annotations

from datetime import date, datetime, timedelta
import os
from pathlib import Path
from uuid import uuid4

import altair as alt
import pandas as pd
import streamlit as st

from radar import (
    RadarAPIError,
    build_scan_radar,
    build_time_windows,
    compile_topic_query,
    count_openalex,
    fetch_openalex_region,
    format_growth,
    load_demo,
)
from skill_sync import default_skill_root, load_skill_bundle
from storage import initialize_database, save_run


APP_DIR = Path(__file__).parent.parent
DATA_DIR = APP_DIR / "data"
SKILL_SNAPSHOT_DIR = APP_DIR / "skill_snapshot"
REGIONS = ["中国内地", "美国", "欧洲"]


@st.cache_data(ttl="30m", max_entries=300, show_spinner=False)
def cached_fetch(
    query: str,
    from_date: date,
    to_date: date,
    region: str,
    max_records: int,
    _api_key: str | None,
):
    return fetch_openalex_region(
        query=query,
        from_date=from_date,
        to_date=to_date,
        region=region,
        max_records=max_records,
        api_key=_api_key,
    )


@st.cache_data(ttl="30m", max_entries=1200, show_spinner=False)
def cached_count(
    query: str,
    from_date: date,
    to_date: date,
    region: str,
    _api_key: str | None,
):
    return count_openalex(query, from_date, to_date, region, _api_key)


@st.cache_data
def demo_data():
    return load_demo(DATA_DIR)


@st.cache_data
def embodied_topics():
    return pd.read_csv(DATA_DIR / "embodied-topics.csv")


st.session_state.setdefault("radar_result", demo_data())
st.session_state.setdefault("last_query", "具身智能")
st.session_state.setdefault("notice", "当前展示已完成核验的具身智能示例；提交左侧条件可执行在线扫描。")
st.session_state.setdefault(
    "run_state",
    {
        "status": "demo",
        "run_id": "demo-2026-11-16",
        "attempted_query": "具身智能示例",
        "error": "",
        "completed_at": "2026-11-16 00:00",
    },
)

try:
    skill_bundle = load_skill_bundle(default_skill_root(), SKILL_SNAPSHOT_DIR)
except RuntimeError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

server_api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
radar_db_path = initialize_database()

with st.sidebar:
    with st.container(border=True):
        st.markdown("**配置同步**")
        sync_color = "red" if skill_bundle.workflow_review_required else "orange" if skill_bundle.source == "snapshot" else "green"
        st.badge(skill_bundle.status_label, color=sync_color, icon=":material/sync:")
        st.caption(
            f"版本 {skill_bundle.fingerprint} · "
            f"{skill_bundle.updated_at.astimezone().strftime('%Y-%m-%d %H:%M')}"
        )
        st.caption(f"已加载 {len(skill_bundle.files)} 个配置文件、{len(skill_bundle.material_options)} 个材料主题。")
        for warning in skill_bundle.warnings:
            st.warning(warning, icon=":material/warning:")

    st.markdown("### 扫描条件")
    st.caption("当前观察期与此前三个等长窗口分别计数，避免从同一相关性样本拆分趋势。")
    run_mode = st.segmented_control(
        "运行模式",
        ["领域扫描", "主题深挖"],
        default="领域扫描",
        key="run_mode_control",
    )
    profile = st.segmented_control(
        "领域配置",
        ["具身智能", "材料科学"],
        default="具身智能",
        key="domain_profile",
    )
    topic_catalog = skill_bundle.materials_topics if profile == "材料科学" else embodied_topics()
    topic_options = topic_catalog["label_zh"].dropna().astype(str).tolist()
    if run_mode == "领域扫描":
        selected_topics = st.multiselect(
            "纳入主题",
            topic_options,
            default=topic_options[:5],
            help="主题越多、对照地区越多，请求量越大。建议先扫描 5 个，再扩展。",
        )
    else:
        selected_topics = [st.selectbox("主题种子", topic_options)]

    with st.form("radar_search"):
        query = st.text_input(
            "自定义主题（可选）",
            placeholder="主题深挖时替换种子；领域扫描时作为新增主题",
        )
        extra_terms = st.text_input(
            "补充同义词（可选）",
            placeholder="用 | 分隔，例如 solid electrolyte | all-solid-state battery",
        )
        extra_excludes = st.text_input(
            "排除词（可选）",
            placeholder="用 | 分隔，例如 drink | beverage",
        )
        today = date.today()
        start_date = st.date_input("开始日期", value=today - timedelta(days=365))
        end_date = st.date_input("结束日期", value=today)
        regions = st.pills(
            "对照地区",
            REGIONS,
            default=REGIONS,
            selection_mode="multi",
        )
        max_records = st.selectbox(
            "每个主题/地区的成果样本",
            [50, 100, 200],
            index=1,
            help="趋势规模使用接口独立计数；这里的样本只用于高校、团队和质量结构。",
        )
        api_key = st.text_input(
            "OpenAlex API key（领域扫描建议填写）",
            type="password",
            disabled=bool(server_api_key),
            help=(
                "服务器已配置 OpenAlex API key，无需填写。"
                if server_api_key
                else "多主题、多地区扫描请求较多。免费 key 可避免共享匿名额度不足；只在当前会话中使用。"
            ),
        )
        submitted = st.form_submit_button(
            "开始扫描",
            type="primary",
            icon=":material/search:",
        )

    if st.button("使用示例数据", icon=":material/history:", width="stretch"):
        st.session_state.radar_result = demo_data()
        st.session_state.last_query = "具身智能"
        st.session_state.notice = "已恢复具身智能示例数据。"
        st.session_state.run_state = {
            "status": "demo",
            "run_id": "demo-2026-11-16",
            "attempted_query": "具身智能示例",
            "error": "",
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        st.rerun()

    st.caption("数据源：OpenAlex。课题组名称为候选归属，除非明确标注为已核验。")
    if server_api_key:
        st.caption("在线服务已配置检索额度。")

if submitted:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
    selected_regions = list(regions or ["中国内地"])
    if start_date > end_date or not selected_topics:
        st.session_state.run_state = {
            "status": "failed",
            "run_id": run_id,
            "run_mode": run_mode,
            "domain_profile": profile,
            "attempted_query": query.strip() or "受控主题扫描",
            "error": "开始日期不能晚于结束日期，且至少选择一个主题。",
            "started_at": datetime.now().astimezone().isoformat(),
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_run(st.session_state.run_state, path=radar_db_path)
        st.rerun()
    else:
        windows = build_time_windows(start_date, end_date)
        definitions = topic_catalog[topic_catalog["label_zh"].isin(selected_topics)].to_dict("records")
        if run_mode == "主题深挖" and query.strip():
            definitions = [
                {
                    **definitions[0],
                    "label_zh": query.strip(),
                    "label_en": query.strip(),
                    "include_terms": query.strip(),
                    "material_anchors": query.strip() if profile == "材料科学" else "",
                    "exclude_terms": "",
                }
            ]
        elif run_mode == "领域扫描" and query.strip():
            definitions.append(
                {
                    "topic_id": f"CUSTOM-{uuid4().hex[:8]}",
                    "label_zh": query.strip(),
                    "label_en": query.strip(),
                    "include_terms": query.strip(),
                    "exclude_terms": "",
                    "material_anchors": "",
                }
            )

        frames: list[pd.DataFrame] = []
        metadata: list[dict] = []
        aggregate_rows: list[dict] = []
        query_log: list[dict] = []
        st.session_state.run_state = {
            "status": "running",
            "run_id": run_id,
            "run_mode": run_mode,
            "domain_profile": profile,
            "attempted_query": query.strip() or "；".join(selected_topics),
            "error": "",
            "started_at": datetime.now().astimezone().isoformat(),
            "completed_at": "",
        }
        run_parameters = {
            "selected_topics": selected_topics,
            "regions": selected_regions,
            "start_date": start_date,
            "end_date": end_date,
            "max_records": max_records,
            "extra_terms": extra_terms,
            "extra_excludes": extra_excludes,
        }
        save_run(st.session_state.run_state, parameters=run_parameters, path=radar_db_path)
        try:
            total_pairs = len(definitions) * len(selected_regions)
            completed_pairs = 0
            with st.status("正在按主题和时间窗口独立计数…", expanded=True) as status:
                for definition in definitions:
                    is_custom_definition = str(definition.get("topic_id", "")).startswith("CUSTOM-")
                    controlled_query = compile_topic_query(
                        definition,
                        custom_query=query if run_mode == "主题深挖" and query.strip() else "",
                        extra_terms=extra_terms if run_mode == "主题深挖" or is_custom_definition else "",
                        extra_excludes=extra_excludes,
                    )
                    for region in selected_regions:
                        st.write(f"{definition['label_zh']} · {region}")
                        frame, meta = cached_fetch(
                            controlled_query,
                            start_date,
                            end_date,
                            region,
                            max_records,
                            server_api_key or api_key or None,
                        )
                        if not frame.empty:
                            frame["topic"] = definition["label_zh"]
                            frame["controlled_topic_id"] = definition.get("topic_id", "")
                            frame["query_string"] = controlled_query
                            frames.append(frame)
                        counts = {"current_count": int(meta["total_count"])}
                        for window_name in ["baseline_1", "baseline_2", "baseline_3", "recent", "previous"]:
                            window_start, window_end = windows[window_name]
                            counts[f"{window_name}_count"] = cached_count(
                                controlled_query,
                                window_start,
                                window_end,
                                region,
                                server_api_key or api_key or None,
                            )
                        aggregate_rows.append(
                            {
                                "topic_id": definition.get("topic_id", ""),
                                "topic": definition["label_zh"],
                                "region": region,
                                "query_string": controlled_query,
                                "coverage_comparable": True,
                                "database_coverage_change_detected": None,
                                **counts,
                            }
                        )
                        metadata.append({**meta, "topic": definition["label_zh"]})
                        query_log.append(
                            {
                                "source": "OpenAlex",
                                "topic": definition["label_zh"],
                                "region": region,
                                "query": controlled_query,
                                "current_start": start_date.isoformat(),
                                "current_end": end_date.isoformat(),
                                "result_count": int(meta["total_count"]),
                                "total_count": int(meta["total_count"]),
                                "sampled_count": int(meta["sampled_count"]),
                                "sample_count": int(meta["sampled_count"]),
                                "coverage_rate": float(meta["coverage_rate"]),
                                "sample_truncated": bool(meta["sample_truncated"]),
                                "sampling_strategy": meta["sampling_strategy"],
                                "sampling_segments": meta["sampling_segments"],
                                "filters": meta["filters"],
                            }
                        )
                        completed_pairs += 1
                        status.update(label=f"已完成 {completed_pairs}/{total_pairs} 个主题-地区组合")
                all_works = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
                result = build_scan_radar(
                    aggregate_rows,
                    all_works,
                    metadata,
                    start_date,
                    end_date,
                    run_mode,
                    profile,
                    query_log,
                )
                status.update(label="扫描完成", state="complete", expanded=False)
            st.session_state.radar_result = result
            st.session_state.last_query = query.strip() or "；".join(selected_topics)
            st.session_state.notice = f"{run_mode}：{st.session_state.last_query}"
            st.session_state.run_state = {
                "status": "success",
                "run_id": run_id,
                "run_mode": run_mode,
                "domain_profile": profile,
                "attempted_query": st.session_state.last_query,
                "error": "",
                "started_at": st.session_state.run_state["started_at"],
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            save_run(
                st.session_state.run_state,
                parameters=run_parameters,
                result=result,
                path=radar_db_path,
            )
            st.rerun()
        except RadarAPIError as exc:
            st.session_state.run_state = {
                "status": "failed",
                "run_id": run_id,
                "run_mode": run_mode,
                "domain_profile": profile,
                "attempted_query": query.strip() or "；".join(selected_topics),
                "error": str(exc),
                "started_at": st.session_state.run_state["started_at"],
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            save_run(st.session_state.run_state, parameters=run_parameters, path=radar_db_path)
            st.rerun()

result = st.session_state.radar_result
topics = result["topics"]
institutions = result["institutions"]
groups = result["groups"]
works = result["works"]
monthly = result["monthly"]

with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
    st.title("高校科研热点雷达")
    if result["mode"] == "demo":
        st.badge("示例数据", color="orange", icon=":material/science:")
    else:
        st.badge("在线结果", color="green", icon=":material/cloud_done:")

st.caption(st.session_state.notice)

run_state = st.session_state.run_state
if run_state["status"] == "failed":
    st.error(
        f"运行 {run_state['run_id']} 失败：{run_state['error']} 当前仍展示上一次成功结果。",
        icon=":material/cloud_off:",
    )
elif run_state["status"] == "success":
    st.caption(
        f"运行编号 {run_state['run_id']} · 完成时间 {run_state['completed_at']} · "
        f"检索范围 {run_state['attempted_query']}"
    )

sampled = sum(int(item.get("sample_count", 0)) for item in result.get("metadata", []))
total = sum(int(item.get("total_count", 0)) for item in result.get("metadata", []))
coverage = sampled / total if total else 1.0
top_topic = topics.iloc[0]["topic"] if not topics.empty else "暂无"
group_count = len(groups)
institution_count = works["institution"].nunique() if not works.empty and "institution" in works else 0

with st.container(horizontal=True):
    st.metric("检索样本", f"{sampled:,}", border=True)
    st.metric("主题命中合计", f"{total:,}", border=True)
    st.metric("论文采样覆盖", f"{coverage:.1%}", border=True)
    st.metric("当前首位主题", str(top_topic), border=True)
    st.metric("候选课题组", f"{group_count:,}", border=True)

if any(item.get("truncated") for item in result.get("metadata", [])):
    st.warning(
        "至少一个主题-地区组合超过成果样本上限。主题规模使用接口完整计数；高校、课题组和质量结构仅反映抽取样本。",
        icon=":material/warning:",
    )

if result["mode"] == "live" and groups.empty:
    st.info("当前条件没有返回可用结果。可扩大时间范围、换用英文检索词或降低主题粒度。")

overview_tab, institutions_tab, groups_tab, works_tab = st.tabs(
    [
        ":material/trending_up: 热点总览",
        ":material/account_balance: 高校分布",
        ":material/groups: 课题组雷达",
        ":material/article: 代表成果",
    ]
)

with overview_tab:
    if not topics.empty:
        region_options = [region for region in REGIONS if region in set(topics["region"])]
        focus_region = st.segmented_control(
            "查看地区",
            region_options,
            default=region_options[0],
            key="overview_region",
        )
        region_topics = topics[topics["region"] == focus_region].head(15).copy()
        region_topics["增长"] = region_topics["growth"].map(format_growth)
        region_topics["热点分"] = region_topics["score"].round(1)
        is_p0_result = "baseline_mean" in region_topics.columns
        is_deep_dive = result.get("run_mode") == "主题深挖"

        if is_p0_result and is_deep_dive:
            row = region_topics.iloc[0]
            with st.container(horizontal=True):
                st.metric("观察期成果", f"{int(row['current_count']):,}", border=True)
                st.metric("三年基线年均", f"{row['baseline_mean']:.1f}", border=True)
                st.metric("相对变化", format_growth(row["growth"]), border=True)
                st.metric("近期加速度", format_growth(row["acceleration"]), border=True)
            st.info(
                f"趋势判断：{row['trend_label']}。主题深挖不生成跨主题排名；热点分只在领域扫描中使用。",
                icon=":material/info:",
            )
        elif is_p0_result:
            left, right = st.columns([1.1, 1.4])
            with left.container(border=True):
                st.subheader("综合热度")
                chart = (
                    alt.Chart(region_topics)
                    .mark_bar(cornerRadiusEnd=3)
                    .encode(
                        x=alt.X("score:Q", title="综合热度", scale=alt.Scale(domain=[0, 100])),
                        y=alt.Y("topic:N", sort="-x", title=None),
                        color=alt.Color("trend_label:N", title="趋势类型"),
                        tooltip=[
                            alt.Tooltip("topic:N", title="主题"),
                            alt.Tooltip("current_count:Q", title="观察期"),
                            alt.Tooltip("baseline_mean:Q", title="三年基线年均", format=".1f"),
                            alt.Tooltip("growth:Q", title="相对变化", format="+.0%"),
                            alt.Tooltip("acceleration:Q", title="近期加速度", format="+.0%"),
                            alt.Tooltip("score:Q", title="热度", format=".1f"),
                        ],
                    )
                    .properties(height=420)
                )
                st.altair_chart(chart)
            with right.container(border=True):
                st.subheader("六项指标")
                component_columns = [
                    "topic", "trend_label", "current_count", "baseline_mean", "增长",
                    "momentum_score", "acceleration_score", "group_breadth_score",
                    "institution_diffusion_score", "quality_score", "industry_linkage_score",
                    "热点分", "score_coverage", "data_confidence",
                ]
                st.dataframe(
                    region_topics[component_columns],
                    hide_index=True,
                    height=420,
                    column_config={
                        "topic": st.column_config.TextColumn("主题", pinned=True),
                        "trend_label": st.column_config.TextColumn("类型"),
                        "current_count": st.column_config.NumberColumn("观察期"),
                        "baseline_mean": st.column_config.NumberColumn("基线年均", format="%.1f"),
                        "增长": st.column_config.TextColumn("变化"),
                        "momentum_score": st.column_config.ProgressColumn("动量", min_value=0, max_value=100),
                        "acceleration_score": st.column_config.ProgressColumn("加速度", min_value=0, max_value=100),
                        "group_breadth_score": st.column_config.ProgressColumn("课题组", min_value=0, max_value=100),
                        "institution_diffusion_score": st.column_config.ProgressColumn("机构扩散", min_value=0, max_value=100),
                        "quality_score": st.column_config.ProgressColumn("质量", min_value=0, max_value=100),
                        "industry_linkage_score": st.column_config.ProgressColumn("产业关联", min_value=0, max_value=100),
                        "热点分": st.column_config.ProgressColumn("热度", min_value=0, max_value=100),
                        "score_coverage": st.column_config.NumberColumn("计分覆盖", format="percent"),
                        "data_confidence": st.column_config.ProgressColumn("数据置信度", min_value=0, max_value=100),
                    },
                )
            st.caption("缺失分项显示为空，综合热度按已有分项重新归一；数据置信度不并入热度。")
        else:
            left, right = st.columns([1.35, 1])
            with left.container(border=True):
                st.subheader("示例主题规模")
                st.bar_chart(region_topics, x="topic", y="current_count", horizontal=True)
            with right.container(border=True):
                st.subheader("示例热点明细")
                st.dataframe(
                    region_topics[["topic", "current_count", "baseline_count", "增长", "热点分"]],
                    hide_index=True,
                )

        if not monthly.empty:
            with st.container(border=True):
                st.subheader("当前成果样本的月度分布")
                line = (
                    alt.Chart(monthly)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("month:T", title="月份"),
                        y=alt.Y("works:Q", title="成果样本数"),
                        color=alt.Color("region:N", title="地区"),
                        tooltip=["region:N", alt.Tooltip("month:T", format="%Y-%m"), "works:Q"],
                    )
                    .properties(height=280)
                )
                st.altair_chart(line)
        else:
            st.caption("示例数据按年度窗口汇总；执行在线扫描后可查看月度趋势。")

        export_topics = topics.drop(columns=[col for col in topics.columns if col.endswith("_rank")], errors="ignore")
        st.download_button(
            "下载热点数据",
            export_topics.to_csv(index=False).encode("utf-8-sig"),
            file_name="university_research_hotspots.csv",
            mime="text/csv",
            icon=":material/download:",
        )
        if result.get("query_log"):
            with st.expander("检索审计日志", icon=":material/manage_search:"):
                st.dataframe(pd.DataFrame(result["query_log"]), hide_index=True)
    else:
        st.info("暂无热点主题数据。")

with institutions_tab:
    if institutions.empty:
        st.info("示例扫描只保存了主题汇总；提交在线检索后可查看高校分布。")
    else:
        st.subheader("高校参与情况")
        st.caption(
            "国际合著可同时进入多个地区；这里是采集样本内观察到的高校参与数，"
            "样本截断时不代表主题的真实高校总数，也不是高校质量排名。"
        )
        institution_view = institutions.copy()
        st.dataframe(
            institution_view,
            hide_index=True,
            column_config={
                "region": st.column_config.TextColumn("地区"),
                "institution": st.column_config.TextColumn("高校", pinned=True),
                "works": st.column_config.NumberColumn("成果数"),
                "topics": st.column_config.TextColumn("主要主题", width="large"),
                "candidate_groups": st.column_config.NumberColumn("候选组数"),
                "representative_work": st.column_config.TextColumn("代表成果", width="large"),
                "representative_link": st.column_config.LinkColumn("来源"),
            },
        )

with groups_tab:
    if groups.empty:
        st.info("当前没有可展示的课题组数据。")
    else:
        st.subheader("谁在做什么")
        st.caption("低/中置信度条目是作者合作线索，不等同于高校官网确认的正式课题组。")
        group_labels = [
            f"{row.group_name}｜{row.institution}"
            for row in groups.itertuples(index=False)
        ]
        selected_label = st.selectbox("选择课题组或合作簇", group_labels)
        selected_index = group_labels.index(selected_label)
        selected = groups.iloc[selected_index]

        with st.container(border=True):
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                st.subheader(str(selected["group_name"]))
                confidence = str(selected.get("confidence", "待核验"))
                badge_color = "green" if confidence == "高" else "orange" if confidence in {"中高", "中"} else "gray"
                st.badge(f"归属置信度：{confidence}", color=badge_color)
            st.markdown(f"**高校/机构：** {selected['institution']}")
            st.markdown(f"**主要方向：** {selected['topics']}")
            st.markdown(f"**当前做了什么：** {selected['representative_work']}")
            st.markdown(f"**归属依据：** {selected.get('attribution_basis', '见原始报告或官方来源')}")
            if selected.get("representative_link"):
                st.link_button("查看代表成果", str(selected["representative_link"]), icon=":material/open_in_new:")

        related = pd.DataFrame()
        if not works.empty and "group_name" in works:
            related = works[
                (works["group_name"] == selected["group_name"])
                & (works["institution"] == selected["institution"])
            ]
        if not related.empty:
            st.markdown("**相关成果**")
            st.dataframe(
                related[["publication_date", "title", "topic", "venue", "link"]],
                hide_index=True,
                column_config={
                    "publication_date": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
                    "title": st.column_config.TextColumn("成果", width="large"),
                    "topic": st.column_config.TextColumn("主题"),
                    "venue": st.column_config.TextColumn("来源"),
                    "link": st.column_config.LinkColumn("链接"),
                },
            )

        st.markdown("**全部候选课题组**")
        st.dataframe(
            groups,
            hide_index=True,
            column_config={
                "region": st.column_config.TextColumn("地区"),
                "group_name": st.column_config.TextColumn("课题组/合作簇", pinned=True),
                "institution": st.column_config.TextColumn("高校/机构"),
                "leader": st.column_config.TextColumn("负责人线索"),
                "confidence": st.column_config.TextColumn("置信度"),
                "works": st.column_config.NumberColumn("成果数"),
                "topics": st.column_config.TextColumn("方向", width="large"),
                "representative_work": st.column_config.TextColumn("代表成果", width="large"),
                "representative_link": st.column_config.LinkColumn("来源"),
                "attribution_basis": st.column_config.TextColumn("归属依据", width="large"),
            },
        )

with works_tab:
    if works.empty:
        st.info("当前没有可展示的代表成果。")
    else:
        st.subheader("成果证据")
        work_view = works.copy()
        display_columns = [
            col
            for col in [
                "publication_date", "title", "region", "institution", "topic", "venue",
                "work_type", "citations", "is_open_access", "link",
            ]
            if col in work_view.columns
        ]
        st.dataframe(
            work_view[display_columns],
            hide_index=True,
            height=560,
            column_config={
                "publication_date": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
                "title": st.column_config.TextColumn("成果", pinned=True, width="large"),
                "region": st.column_config.TextColumn("地区"),
                "institution": st.column_config.TextColumn("高校/机构"),
                "topic": st.column_config.TextColumn("主题"),
                "venue": st.column_config.TextColumn("来源"),
                "work_type": st.column_config.TextColumn("类型"),
                "citations": st.column_config.NumberColumn("引用"),
                "is_open_access": st.column_config.CheckboxColumn("开放获取"),
                "link": st.column_config.LinkColumn("原始记录"),
            },
        )
        st.download_button(
            "下载成果数据",
            work_view.to_csv(index=False).encode("utf-8-sig"),
            file_name="university_research_works.csv",
            mime="text/csv",
            icon=":material/download:",
        )

with st.expander("口径与限制", icon=":material/info:"):
    st.markdown(
        """
- 在线检索使用 OpenAlex 题名、摘要与全文索引搜索，并限定高校类型机构。
- 观察期之前建立三个等长历史窗口；零基线与小样本不会显示夸张增长率，数据库历史回填仍作为替代解释保留。
- `total_count` 是 OpenAlex 完整命中计数，`sampled_count` 是实际采集论文数，`coverage_rate` 是两者比例；高校和作者统计来自采集样本。
- 在线课题组是基于通讯作者或末位作者与高校署名形成的候选归属，必须再用高校官网、实验室成员页或论文通讯信息核验。
- 主题之间可能重叠；国际合著可同时进入多个地区，因此地区数字不能相加成全球总量。
- 宽泛检索可能超过采样上限。正式报告应补充 Crossref、中文数据库、基金、专利和官方课题组页面。
- 领域配置、主题词表、质量量表和数据源配置从当前 Skill 实时读取；配置通过校验后会自动更新备用快照。
- `SKILL.md` 主流程变化需要人工检查网页计算逻辑，界面会在完成适配前持续提示，不会自动标记为兼容。
"""
    )
