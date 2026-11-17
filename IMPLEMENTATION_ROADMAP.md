# 全球科研热点总览：实施路线图

版本：规划稿 1.0
原则：增量升级、保留现有功能和历史数据、先修复可信度问题再发布全球榜单

## 1. 实施总原则

- 不重建现有 SQLite；所有变更通过可重复执行的 schema migration；
- 保留 `works`、`authors`、`institutions`、`topics` 及既有关系/快照表；
- 首页只读取预计算读模型，渲染时零 OpenAlex 请求；
- 采集、计算、发布三阶段分离，失败批次不覆盖上一成功批次；
- 完整计数、样本计数、已验证实体和缺失状态贯穿数据库、API 和页面；
- 单实例调度、幂等任务、WAL 和短事务保护多人访问下的 SQLite；
- 全球全量原始 Works 不作为 SQLite 的近期目标。

## 2. 阶段 0：关闭 V1.1 发布阻断项

在全球模块开发前完成：

1. 修复缺失分项重新归一导致低覆盖主题反向加分；
2. 对低 `score_coverage`、低 `data_confidence` 和口径不可比主题实施排名门控；
3. 处理同 DOI 多 OpenAlex ID，建立作品家族/别名关系并避免整次事务回滚；
4. 使用全部目标地区高校署名计算机构扩散度，并修正地域作者口径；
5. 实现真实覆盖变化检测；
6. 校准零基线加速度，禁止小样本直接饱和；
7. 将独立验收发现转为永久回归测试。

涉及现有文件：`radar.py`、`storage.py`、`migrations.py`、`tests/test_v11.py`。完成后重新执行 V1.1 发布验收；未通过不得启动全球正式排名。

## 3. 阶段 1：采集控制面与主数据索引

### 3.1 新增任务能力

- 单实例 scheduler/worker；
- 任务分片、请求预算、断点续跑、指数退避和失败重试；
- 任务级互斥锁，避免多个 Web 进程重复采集；
- OpenAlex 响应头、查询条件、计数和错误审计；
- 数据管理页显示任务状态，但网页进程不直接承担长时间采集。

建议新增代码：

- `collector/openalex_client.py`
- `collector/jobs.py`
- `collector/catalog_sync.py`
- `collector/worker.py`
- `repositories/collection_repository.py`
- `scripts/run_collection_worker.py`

### 3.2 新增表

| 表 | 主要字段 | 原因 |
|---|---|---|
| `collection_jobs` | job_id、job_type、scope_json、scheduled_for、status、lock_owner、attempt_count、started_at、completed_at、published_batch_id | 管理幂等采集和单实例发布 |
| `collection_job_attempts` | attempt_id、job_id、started_at、ended_at、status、error_class、error_message、retry_after | 保留重试和失败证据 |
| `source_query_audit` | query_id、job_id、source、endpoint、filters_json、query_hash、result_total、sampled_count、rate_limit、observed_at | 追溯每个计数和样本来源 |
| `institution_aliases` | institution_id、alias、alias_type、source、valid_from、valid_to | 防止名称变化制造“新高校” |
| `work_families` | work_family_id、canonical_work_id、method、confidence、created_at、updated_at | 版本级去重 |
| `work_family_members` | work_family_id、openalex_work_id、relation_type、evidence_json | 保留所有原始 OpenAlex ID |

目录同步先建立全量 Topics 和教育机构索引，不删除现有受控主题。

## 4. 阶段 2：全球聚合与历史快照

### 4.1 计算任务

- 全球、中国和配置国家的 7/30/90 天计数；
- 全球/中国 12个月和3年按月时间序列；
- 全量 Topic 分片计数和领域内基线；
- 高校 Top-K 与候选覆盖审计；
- 完整计数与代表样本独立运行；
- 最近 90-180 天重叠回算，识别迟到回填和覆盖变化。

### 4.2 新增读模型

| 表 | 关键字段 | 用途 |
|---|---|---|
| `global_metric_snapshots` | batch_id、scope_type、scope_id、period、window_start/end、metric_key、metric_value、count_scope、coverage_rate、confidence、source_query_id、algorithm_version | 顶部 KPI 和趋势总览 |
| `topic_period_metrics` | batch_id、topic_key、scope、period、total_count、sampled_count、coverage_rate、growth、acceleration、category、heat_score、score_coverage、confidence、eligibility、versions | 主题趋势和四类榜单 |
| `institution_period_metrics` | batch_id、institution_id、scope、topic_filter、period、work_count、topic_count、author_count、ranking_scope、confidence | 高校榜单与趋势 |
| `topic_institution_metrics` | batch_id、topic_key、institution_id、period、complete_count、sample_count、share、rank、ranking_scope | 主要高校和集中度 |
| `snapshot_batches` | batch_id、status、as_of_date、started_at、completed_at、published_at、source_versions、quality_report_json | 原子发布同一批次 |

现有 `topic_snapshots`、`institution_snapshots`、`author_snapshots` 继续保留，作为具体扫描运行的细粒度快照；新表服务全球统一周期和首页读性能，不重复建立实体。

### 4.3 迁移策略

- 在 `LATEST_SCHEMA_VERSION` 上逐版增加 V3、V4，不修改 V2 既有表内容；
- 每次 migration 在单事务内执行并写 `schema_migrations`；
- 所有新列允许旧数据为空，后台回填与 schema 迁移分开；
- 先备份、迁移副本、执行完整性/外键检查，再在维护窗口迁移生产库；
- 回滚使用升级前备份恢复，不尝试破坏性 down migration。

## 5. 阶段 3：首页读模型与多页面导航

建议代码结构：

```text
streamlit_app.py                 # set_page_config、导航和共享上下文
pages/global_dashboard.py        # 新首页
pages/domain_scan.py             # 保留现有领域扫描
pages/topic_analysis.py          # 主题深度分析
pages/history.py                 # 历史扫描记录
pages/data_management.py         # 数据状态、任务和备份
repositories/dashboard_repository.py
services/dashboard_service.py
components/coverage_badge.py
components/data_state.py
```

实施顺序：

1. 为现有单页增加 AppTest 行为基线；
2. 提取现有页面但不改变控件、默认值和扫描结果；
3. 建立 `st.navigation` 一级导航；
4. 新增只读 dashboard repository；
5. 先实现缺失/过期/失败状态，再接入真实快照；
6. 实现 KPI、趋势、主题榜单、高校榜单、动态和预警区域；
7. 确认页面渲染网络 mock 下不会调用 OpenAlex。

## 6. 阶段 4：全学科主题发现与分类

- 自动发现从完整 Topics 索引出发；
- group-by Top-200 只作为候选生成，不作为全量主题集合；
- 对全量 Topic 分片补齐计数；
- 建立 Emerging、Fast Growing、Trending、Cross-disciplinary 分类器；
- 保存每个分项、阈值、领域校准和算法版本；
- 分类变化保留历史，不覆盖旧结论。

可能新增：

| 表 | 用途 |
|---|---|
| `topic_catalog_history` | 保存 Topic 名称、层级、分类版本和有效期 |
| `topic_relations` | 保存 Topic 到 Subfield/Field/Domain 及跨学科关系 |
| `topic_classification_events` | 保存每批分类、理由、阈值和版本 |

代码建议：`services/topic_discovery.py`、`services/topic_classifier.py`、`services/cross_discipline.py`。

## 7. 阶段 5：高校、作者和团队情报

- 使用全部 authorship-institution 关系计算高校与作者指标；
- ROR、OpenAlex ID 和别名处理机构合并；
- 候选团队继续由共著/通讯作者证据生成；
- 新建人工/多源审核工作流后才允许状态变为 verified；
- 代表成果使用分层样本，不以高引用排序代替代表性。

建议新增 `work_source_evidence`：`evidence_id`、`work_id/work_family_id`、`source_type`、`source_url`、`observed_at`、`content_hash`、`claim_text`、`summary_method`、`verification_status`、`confidence`。本阶段只支持结构与人工导入，不开发高校官网爬虫。

## 8. 阶段 6：证据型预警

新增：

| 表 | 主要字段 |
|---|---|
| `research_alerts` | alert_id、type、subject_type/id、status、severity、triggered_at、window、baseline、observed_value、threshold、confidence、algorithm_version、batch_id |
| `alert_evidence` | alert_id、evidence_type、evidence_id/source_query_id、explanation、created_at |

预警流程：计算候选 → 质量门控 → 连续批次确认 → 保存证据 → 发布。覆盖变化或分类版本变化引起的信号进入复核，不自动发布。

## 9. 调度与运行建议

- 每日：目录差异、短窗口计数、失败重试、重点主题代表样本；
- 每周：全 Topic 分片、90天回填、高校榜单；
- 每月：12个月/3年重算、领域校准、索引维护；
- 单独 worker 容器/进程，Web 容器不执行 scheduler；
- 若仍为单容器，使用数据库租约锁并保证只有一个 scheduler 开关为真；
- 采集写入 staging batch，验证完成后以短事务更新 published batch 指针；
- SQLite 保持 WAL、busy timeout、外键开启；每个写事务小而幂等。

## 10. 测试计划

### 数据与迁移

- 从真实 V1/V2 副本迁移，多次执行结果一致；
- 旧表行数、哈希和扫描历史不变；
- 新表主键、外键、唯一约束、索引完整；
- DOI 冲突、无 DOI、同作品多版本正确归并；
- 机构别名不会产生“新高校”误报。

### 指标

- 0→N、1→5、100→120、1000→1100；
- 当前样本不足、历史缺失、覆盖率骤变；
- 多机构、多国家、多主题作品；
- 缺失值不变成 0，不因缺项升分；
- 领域内百分位与跨领域不可比门控；
- 完整计数和样本计数始终分开。

### 任务与快照

- 同一任务重复运行不重复插入；
- 两个 worker 抢同一任务只有一个成功获得租约；
- 429、超时和进程重启后可续跑；
- 失败批次不更改 published batch；
- 三个日期可比较，查询绑定同一算法/口径；
- API 配额耗尽后保留历史成功页面。

### 页面

- 原有页面 AppTest 无回归；
- 空库、部分库、过期、失败和完整数据状态；
- 页面渲染时 OpenAlex 客户端被禁用仍可正常打开；
- 手机与桌面布局无重叠；
- CSV 导出包含口径、版本和日期。

## 11. 发布与回滚

每阶段独立发布：代码 → 副本迁移 → 预生产采集 → 数据质量报告 → 人工批准 → 生产迁移/启用功能开关。全球首页默认关闭，直到首次快照通过验收。

回滚：关闭全球首页和 worker；恢复上一代码镜像；数据库保持向前兼容。若 migration 本身异常，停止写入并从迁移前 SQLite Backup API 备份恢复。不得删除已有实体或历史快照来回滚页面。

## 12. 建议里程碑

| 里程碑 | 可交付结果 | 发布门槛 |
|---|---|---|
| M0 | V1.1 阻断项关闭 | 独立复验通过 |
| M1 | Topics/Institutions 索引与任务控制面 | 幂等、限流、单实例测试通过 |
| M2 | 全球聚合快照 | 至少三个成功日期，覆盖报告可追溯 |
| M3 | 新一级首页 | 空态与真实数据态均通过页面验收 |
| M4 | 全学科自动发现 | 不依赖预设词表，领域校准通过 |
| M5 | 高校/团队情报 | 多机构正确，候选/已验证严格分离 |
| M6 | 科研预警 | 每条预警可回溯公式和证据 |
