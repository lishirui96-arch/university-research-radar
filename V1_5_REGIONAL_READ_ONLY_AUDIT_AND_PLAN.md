# V1.5 全球、中国、美国区域科研热点监测：只读审计与实施计划

审计日期：2026-11-20（Asia/Singapore）  
项目：`university-research-radar`  
代码基线：`0dbfb18d6df790ac687b33bac7f879e25ec9047e`  
审计性质：只读；未调用 OpenAlex，未修改任何 SQLite 数据或现有业务代码

## 1. 审计范围与数据源说明

本次检查了以下数据位置：

- 仓库默认数据库：`persistent/data/radar.db`，356,352 bytes，Schema v5，当前为空壳数据库。
- V1.4 完整开发数据库：`trend-v1-1-test-20261118.db`，155,037,696 bytes，Schema v6。
- 当前 8508 页面使用的测试副本：`radar-ui-v11.db`，与完整开发库的 V1.4 数据一致。

因此，V1.5 开发不能把仓库默认空库误认为现有 GLOBAL 数据源。正式实施前必须明确部署数据库路径，并继续使用复制库开发和验收，不能直接修改现有完整开发库。

本机已确认可从 Process/User 环境变量读取 `OPENALEX_API_KEY`。本报告没有读取、显示或记录 Key 内容；`.env` 和 `.streamlit/secrets.toml` 均受 `.gitignore` 保护。

## 2. V1.4 分类与 GLOBAL 数据审计

### 2.1 六个 Field 与 1,063 Topic

当前分类版本为 `openalex-taxonomy-2026-11-18-v1.4`，数据库声明值与实际值一致：

| Field ID | 学科 | 声明 Topic | 实际 Topic |
|---:|---|---:|---:|
| 15 | 化学工程 | 24 | 24 |
| 16 | 化学 | 119 | 119 |
| 17 | 计算机科学 | 265 | 265 |
| 21 | 能源 | 44 | 44 |
| 22 | 工程学 | 467 | 467 |
| 25 | 材料科学 | 144 | 144 |
| 合计 |  | 1,063 | 1,063 |

结论：Field、Topic ID 和归属完整，无重复或缺失，不需要重建分类体系。

### 2.2 GLOBAL 排名快照

现有原始排名快照包含 OpenAlex 全部 4,516 Topic；首页通过 V1.4 分类表联接后只使用目标六个 Field 的 1,063 Topic。

| 周期 | 排名日期 | V1.4 Topic | 窗口 | 快照 Works 合计 |
|---|---|---:|---|---:|
| 90天 | 2026-11-18 | 1,063 | 2026-08-21 至 2026-11-18 | 255,644 |
| 360天 | 2026-11-18 | 1,063 | 2025-11-24 至 2026-11-18 | 1,197,657 |

两个周期各来自一个已发布批次，`query_as_of` 在周期内部一致。OpenAlex 后续历史修订后，完整日序列求和分别为 259,645 和 1,202,103；当前首页在日矩阵完整时使用日序列重算排名，因此与旧审计快照存在可解释的版本差异，旧快照仍被保留。

### 2.3 GLOBAL 日序列

- 覆盖日期：2025-11-24 至 2026-11-18，共360天。
- 按 V1.4 Topic ID 联接后：382,680行，即 `1,063 x 360`，每个日期均有1,063个 Topic。
- 缺失日期：0；重复 current 日期/Topic：0。
- `PRAGMA integrity_check`：`ok`。
- 本地 `works`、`institutions`、`work_authorships` 表在该开发库中均为0行；现有首页依靠聚合快照而非原始 Works 运行。

发现一个版本一致性风险：T10018、T10030、T10036、T10078 的部分 current 日记录沿用了旧 V1.3 查询版本，其余记录使用 V1.4 查询版本。两者统计口径均为 core corpus、`publication_date`、`primary_topic.id`，页面数据矩阵完整，但数据库层面存在2个 `query_version`、2个 `taxonomy_version` 和2个 `source_run_id`。V1.5 新表不得继续这种跨版本联接方式。

## 3. 当前增长量与增长率逻辑

当前 V1.4.2 图表逻辑位于 `trend_aggregation.py`：

- 90天图：按连续7天聚合，首段不足7天时与前一等长周期比较；增长率为周环比。
- 360天图：按自然月聚合；完整月为月环比，首尾不完整月按上月相同日期范围比较。
- 缺日、失败查询或基期为0时保持 NA，不补0。
- 当前首页“增长率榜单”使用最新一个周度/月度桶的增长率排序。

V1.5 要求的榜单口径不同：

- 90天：当前90天与此前90天比较。
- 360天：当前360天与此前360天比较。
- `growth_amount = current_works - previous_works`。
- `growth_rate = growth_amount / previous_works`；基期为0或缺失时为 NA/新出现。

实施时应保留现有图表周/月聚合，不改图表含义；只为区域榜单新增完整90/360天相邻窗口指标，避免把最新周/月环比冒充完整窗口增长率。

## 4. 历史基期完整性

以排名日 2026-11-18 为例：

| 指标 | 当前窗口 | 前置等长窗口 | 现有 GLOBAL 覆盖 |
|---|---|---|---|
| 90天 | 2026-08-21 至 2026-11-18 | 2026-05-23 至 2026-08-20 | 完整，可从现有360天日序列计算 |
| 360天 | 2025-11-24 至 2026-11-18 | 2024-11-29 至 2025-11-23 | 不完整，缺少整个前置360天 |

CN、US 当前没有任何区域 Topic 排名或日序列，因此90天和360天当前窗口及基期都需要独立采集。不能用 GLOBAL TOP 10 过滤替代国家排名。

## 5. 国家字段与可复用代码

### 5.1 已有能力

- Schema 已有 `institutions.country_code`、作者署名、作者-机构关联表，可表达一篇 Work 同时属于 CN 和 US。
- `radar.py` 已有 `REGION_CODES`、`count_openalex`、`fetch_openalex_region`，包含 CN/US 国家过滤及请求重试的早期实现。
- `collector/v14_daily_backfill.py` 已具备按日、按 `primary_topic.id` 分组、cursor 分页、限速、重试、断点续跑和整批发布能力。
- `collector/topic_hotspot_updater.py` 已具备全 Topic 聚合排名及修订历史模式。
- 页面只读取 SQLite，不在渲染期间调用 OpenAlex。

### 5.2 不可直接复用的部分

`radar.py` 的地区函数同时强制 `authorships.institutions.type:education`，且没有 V1.5 所需的 core corpus和六 Field 固定过滤，因此不能直接用于 V1.5 正式统计。其请求/重试框架可参考，查询合同必须重写。

V1.5 正式过滤合同应为：

```text
GLOBAL:
  primary_location.source.is_core:true
  publication_date in [window_start, window_end]
  primary_topic.field.id:15|16|17|21|22|25

CN/US 额外增加：
  authorships.institutions.country_code:CN 或 US
```

第一阶段不增加 `institution_type=education`。国际合作论文分别命中 CN 和 US 是预期行为。

## 6. 缺失能力

1. 现有排名表和日表没有 `region_code`，同一 Topic 的 GLOBAL/CN/US 会发生键冲突。
2. 没有 CN、US 的全量90/360天排名、日序列或历史基期。
3. 没有完整窗口的 `previous_works_count`、`growth_amount`、`growth_rate` 和三种独立排名。
4. 当前开发库没有原始 Works/作者机构数据，不能从本地 SQL 推导 CN/US，只能离线调用 OpenAlex 聚合接口。
5. 现有 GLOBAL 360天基期不足720天。
6. 现有发布模型不能保证 CN、US 来自同一个区域采集批次。
7. 仅回填 TOP 10 并集无法立即支持“当前 Field 全部 Topic 中任意选择最多10个”的自定义功能；页面又禁止实时调用 API，因此两项要求不能同时依靠按需 TOP 10 数据满足。

## 7. 推荐数据库设计

不 ALTER、不覆盖现有 V1.4 表，新增 Schema v7 独立表。GLOBAL 继续由原有 V1.4 Repository 和数据表提供；新表只允许 CN、US：

### `regional_snapshot_batches`

保存 `batch_id`、`ranking_date`、`taxonomy_version`、`query_version`、`calculation_version`、`status`、开始/完成时间、API请求数和错误摘要。只有 CN、US 同时通过质量门槛后，区域批次才可发布。GLOBAL 不属于该批次。

### `regional_topic_runs`

每个 `batch_id + region_code` 一行，保存 `source_run_id`、`region_code`、`query_as_of`、状态、窗口、请求和重试统计。Schema v7 的 `region_code` CHECK 仅允许 `CN/US`，从数据库约束层阻止采集器写入 GLOBAL。

### `regional_topic_period_snapshots`

核心字段：

```text
batch_id, region_code, ranking_date, period_days,
topic_id, field_id, window_start, window_end,
works_count, previous_window_start, previous_window_end,
previous_works_count, growth_amount, growth_rate,
works_rank, growth_amount_rank, growth_rate_rank,
taxonomy_version, query_version, calculation_version,
source_run_id, query_as_of, data_status,
revision_no, is_current, created_at, updated_at
```

建议唯一约束：

```text
UNIQUE(batch_id, region_code, period_days, topic_id)
UNIQUE(region_code, ranking_date, period_days, topic_id,
       taxonomy_version, calculation_version, revision_no)
```

并为三种非空 rank 分别建立区域/周期内的部分唯一索引。

### `regional_topic_daily_counts`

核心字段：

```text
batch_id, region_code, publication_date, topic_id, field_id,
daily_works_count, taxonomy_version, query_version,
source_run_id, query_as_of, data_status,
revision_no, is_current, created_at, updated_at
```

建议唯一约束：

```text
UNIQUE(region_code, publication_date, topic_id,
       taxonomy_version, query_version, revision_no)
```

API整日所有 cursor 页均成功后，OpenAlex 未返回的 Topic 才能写入经过确认的真实0；失败或缺页时整日保持失败/缺失状态，不写0。

### `regional_query_logs`

保存可复现的过滤器、窗口、region、cursor、HTTP状态、重试、查询哈希、响应计数和错误摘要。API Key 永不入库。

## 8. API 请求量估算

OpenAlex `group_by=primary_topic.id` 每页最多200组。六 Field 共1,063 Topic，保守按每个窗口最多6页估算。

### 8.1 全量区域排名与完整窗口增长

CN、US 分别查询当前90、此前90、当前360、此前360：

```text
2 regions x 4 windows x up to 6 pages = up to 48 successful requests
```

国家非零 Topic 通常少于全球，实际请求数预计低于72。

### 8.2 只回填榜单 TOP 10 并集

为周/月图表保留首段比较基期，需要约391个发布日期（2025-10-24 至 2026-11-18）。榜单并集不超过200 Topic时，每地区每天约1次请求：

```text
48 ranking + 2 x 391 daily = about 830 successful requests
```

该方案成本最低，但不能立即支持任意1,063 Topic的自定义曲线，因此不满足完整 UI 要求。

### 8.3 推荐：CN、US 全1,063 Topic日序列

保守上限：

```text
48 ranking + 2 x 391 x 6 pages = up to 4,740 successful requests
```

参考 V1.4 GLOBAL 实际360天全量回填为1,341次成功请求，约3.7页/天；CN、US 的非零 Topic 数通常更少，实际值预计明显低于4,740。按历史报告的0.0001美元等价额度/成功响应计算，保守上限约0.474美元等价额度，不含重试。应读取实时 `X-RateLimit-*` 响应头并支持跨日断点续跑。

不需要回填 CN、US 全部720天日序列：完整窗口增长可由四个全量聚合排名窗口获得；日序列只需覆盖当前360天及图表比较所需的前置月份。这样仍可核对当前90/360排名与日序列求和，同时避免额外约一倍请求。GLOBAL 日序列完全复用 V1.4，不产生请求。

## 9. 推荐历史回填与发布流程

1. 在完整数据库的副本上执行 Schema v7 迁移并验证幂等性。
2. 创建一个共同 `batch_id`，冻结排名日、分类版本、查询版本和计算版本。
3. 仅对 CN、US 各自查询四个相邻窗口，生成全量1,063 Topic指标和三种独立排名。
4. 仅对 CN、US 回填约391天的全 Topic 日序列，整日全部cursor成功后才提交该日期。
5. 校验当前90/360 `daily SUM == period works_count`；任何不一致阻止发布。
6. 校验国家 Topic 均属于当前 Field；校验 CN/US 国际合作样本可同时进入两地。
7. 对 GLOBAL 表执行采集前后哈希、行数和关键指标对账，必须完全一致；任何变化立即阻止发布。
8. 只有 CN、US 同批完成、`integrity_check=ok`、外键检查无错误后，原子发布区域批次。
9. 首页 GLOBAL 始终读取 V1.4 表；CN、US 读取最后一个完整区域批次；地区切换绝不触发 OpenAlex。

## 10. 数据完整性风险

- OpenAlex 会修订历史记录，同一窗口在不同 `query_as_of` 可能不同。
- 作者机构缺少 `country_code` 时，Work 会进入 GLOBAL 但不进入 CN/US；不能推断补齐。
- 国际合作导致 `CN + US` 与 GLOBAL 不可加总，这是正确统计结果。
- 最后发布日期可能仍在收录中，需要延续 D-0/D-2/D-3/D-7/D-14 修订策略。
- country filter 必须使用作者署名机构，不能使用期刊国家或作者国籍。
- cursor 任一页失败时不能把未返回 Topic 写成0。
- 旧 GLOBAL 日表存在四个 Topic 跨查询版本混用，但本次明确冻结并保留现状；V1.5 不修复、不重写、不迁移这些记录，只在验收报告中披露。
- 仓库默认数据库为空，部署时若未设置 `RADAR_DB_PATH`，会显示无数据。
- 全 Topic 区域日表预计新增约124.7万行；应在副本上先评估文件增长、查询索引和备份时间。

## 11. 分阶段实施计划

### 阶段A：Schema与采集合同

- 新增 Schema v7 迁移、区域批次/周期/日序列/日志表。
- 实现严格的 CN/US 查询构造器，移除教育机构限制；采集代码不接受 GLOBAL。
- 增加唯一约束、版本一致性和失败不发布测试。
- 不触碰旧 GLOBAL 表。

### 阶段B：区域采集与副本回填

- 使用环境变量中的 OpenAlex API Key。
- 先跑小窗口、小样本只读验证，再在数据库副本执行完整回填。
- 输出实际请求量、覆盖率、重试、失败日期和对账差异。

### 阶段C：Repository与首页 UI

- Repository 增加 `region_code` 参数，只读已发布本地批次。
- 顶部顺序改为：地区范围、观察窗口、学科范围、榜单口径、更新时间。
- 默认 GLOBAL 且继续调用原 V1.4 Repository；切换地区保留周期、Field和榜单选择。
- KPI、榜单、TOP 5/TOP 10、自定义、两张图、详情、速览全部使用同一地区和批次。

### 阶段D：自动化与浏览器验收

- 覆盖3地区 x 2周期 x 6 Fields x TOP 5/TOP 10、自定义和两种榜单口径。
- 验证国际合作、零基期、缺失基期、API失败、缓存切换和数据库完整性。
- 使用独立 Streamlit 实例，不停止现有服务，不覆盖现有数据库。

## 12. 本阶段结果与停止点

- 修改文件：仅新增本审计报告。
- 数据库变更：无。
- OpenAlex请求：0。
- API Key：确认本机可安全读取，未显示、未记录、未上传。
- 已有分类：1,063/1,063 Topic完整。
- 当前 GLOBAL 日序列：1,063 x 360完整，但有4个 Topic 跨两个历史查询版本。
- CN/US历史数据：不存在，需要独立采集。
- 360天历史基期：不存在，需要按前一360天聚合窗口补采。

修订结论已确认：GLOBAL 冻结并继续读取 V1.4；Schema v7 只存 CN/US；CN、US 同批采集并回填全1,063 Topic日序列。后续开发不得产生 GLOBAL OpenAlex 请求，也不得写入原有 GLOBAL 表。
