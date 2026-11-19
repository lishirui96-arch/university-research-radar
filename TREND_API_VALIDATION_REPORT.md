# 全球科研热点趋势 V1：OpenAlex API 验证报告

验证日期：2026-11-18（Asia/Singapore）  
验证脚本：`scripts/validate_trend_openalex.py`  
映射版本：`config/trend_topic_mapping.json` / `v1`  
验证方式：OpenAlex 官方 API，只读请求；未连接或修改 SQLite

## 1. 结论

OpenAlex 能支持当前设计所需的“一级领域 + 某一天 + 全球 + core corpus + Works 数量”，但不能使用 `group_by=publication_date` 一次返回逐日序列。

推荐做法是对每个一级领域、每个目标日期发出一个 Works count 请求：

```text
GET https://api.openalex.org/works
filter=primary_location.source.is_core:true,
       from_publication_date:YYYY-MM-DD,
       to_publication_date:YYYY-MM-DD,
       primary_topic.id:T1|T2|T3
per-page=1
select=id
```

数量读取 `meta.count`。全球口径不增加国家、机构或高校过滤。

对于图上某个日期 `t` 的 30 天滚动值，也可直接查询：

```text
from_publication_date:t-29
to_publication_date:t
```

这正好对应 `Trend(category, t)`，不是当日增量、历史累计或日均值。

## 2. 实测环境与固定口径

| 项目 | 值 |
|---|---|
| API | `https://api.openalex.org/works` |
| 实测窗口 | 2026-10-20 至 2026-11-18（含首尾，30 天） |
| 单日样本 | 2026-11-17 |
| 地域 | 全球，无地域过滤 |
| corpus | `primary_location.source.is_core:true` |
| Topic 字段 | `primary_topic.id` |
| 日期字段 | `publication_date` |
| 测试 Topic | T10879、T10653（人形机器人与具身智能 approved 子集） |
| API key | 未使用；匿名共享额度 |

仓库没有已有 core corpus 过滤实现。API 实测表明 `is_core:true` 返回 400，因为 `is_core` 不是 Works 的合法顶层过滤字段；合法的相关字段包括 `primary_location.source.is_core` 和 `locations.source.is_core`。V1 选择前者，以“主发表来源属于 OpenAlex/CWTS core sources”定义 corpus，边界更稳定且避免“任一位置是 core”扩大集合。

## 3. 九项验证结果

| 验证项 | 结果 | 实测证据 |
|---|---|---|
| 1. `publication_date` 日期过滤 | 通过 | `from_publication_date=to_publication_date=2026-11-17` 返回 200；`meta.count=344`；样本 Work 的 `publication_date=2026-11-17` |
| 2. `primary_topic.id` 过滤 | 通过 | 30 天窗口内 T10879 返回 50，T10653 返回 157 |
| 3. 多 Topic 查询 | 通过 | `primary_topic.id:T10879|T10653` 返回 200，`meta.count=207` |
| 4. `meta.count` | 通过 | 返回整数，可在 `per-page=1` 时读取完整命中数 |
| 5. `group_by=publication_date` | 不支持 | 返回 400：`Cannot group by date, number, or search fields.` |
| 6. 多 Topic 重复计数 | 当前口径无重复 | 50 + 157 = 207，与 OR 查询的 207 完全一致 |
| 7. API 响应时间 | 可用但需异步采集 | 4 个成功计数请求：min 286.3 ms，median 331.1 ms，p95/max 1241.8 ms |
| 8. API 限流 | 未触发 429；需按响应头治理 | 实测头 `X-RateLimit-Limit=1000`，remaining 从 999 降至 996；匿名请求共享 IP 的免费日预算 |
| 9. API 失败处理 | 通过 | 无效过滤器返回 400，被脚本转换为结构化 `OpenAlexValidationError`；429/5xx 有有界重试和 `Retry-After` 支持 |

验证脚本退出码为 0，所有预期成功项通过；`group_by=publication_date` 的 400 被记录为能力限制而不是脚本失败。

## 4. 能否得到“领域 + 某一天 + 全球 + 成果数量”

可以。以人形机器人与具身智能 V1 为例：

```text
filter=
  primary_location.source.is_core:true,
  from_publication_date:2026-11-17,
  to_publication_date:2026-11-17,
  primary_topic.id:T10879|T10653|T10462
```

不设置 institutions/country 条件即为全球。响应中的 `meta.count` 是该查询口径下的 OpenAlex Work 记录数。

需要注意：当前项目尚未实现 `work_family_id`。因此结果必须称为“OpenAlex 记录数”或“该查询完整命中数”，不能称为“作品家族去重论文数”。这与现有 `METRIC_DEFINITIONS.md` 一致。

## 5. 为什么不使用 group_by publication_date

实际请求：

```text
group_by=publication_date
```

OpenAlex 返回 HTTP 400 和明确错误：

```text
Cannot group by date, number, or search fields.
```

因此不能假设服务端支持按发表日聚合。`group_by=primary_topic.id` 可以成功，但它解决的是 Topic 分组，不是逐日序列，而且 group-by 仍有分组页数/数量限制，不适合替代日级计数。

## 6. 多 Topic 重复风险

### 同一类别内

当前过滤字段是 `primary_topic.id`。每个 Work 只有一个 primary Topic，所以一个 Work 不可能同时命中同一 OR 列表中的两个 primary Topic。

实测：

```text
T10879 = 50
T10653 = 157
OR      = 207
差值    = 0
```

推荐直接使用一个 OR 请求读取 `meta.count`，不要抓取各 Topic 结果后手工合并。

### 类别之间

V1 配置强制 approved Topic 在五个一级领域之间唯一归属，测试也检查这一约束。因此当前类别间不会因同一 primary Topic 重复。

如果未来允许一个 Topic 映射多个一级领域，各领域折线仍可分别正确计数，但不得把五条线相加为“全球总成果”。配置审核和数据库约束应明确这一点。

### 仍然存在的实体重复问题

OpenAlex 的不同 Work ID 可能是预印本、会议版和正式发表版等同一成果家族。`primary_topic` 只能消除 Topic 交叉计数，不能完成作品家族去重。V1 在家族表实现前应持续标注“OpenAlex 记录数”。

## 7. 响应时间与限流

成功计数请求的实测时间为 0.29-1.24 秒。这个延迟适合离线采集，不适合首页渲染时同步调用。首页继续遵守现有设计：只读取已发布的本地快照。

匿名响应返回：

- `X-RateLimit-Limit: 1000`；
- `X-RateLimit-Remaining` 每次请求递减；
- OpenAlex notice 明确说明匿名请求与同一公网 IP 共享免费日预算；
- 本次没有观察到 429，不能据此假设永不触发限流。

下一阶段采集器应：

1. 使用环境变量提供 OpenAlex API key，不写入配置、数据库或日志；
2. 每次读取 `X-RateLimit-*` 和 `Retry-After`；
3. 遇到 429、5xx 或网络错误做有界重试与指数退避；
4. 失败时保留上一成功快照，不写 0 覆盖真实值；
5. 记录请求时间、状态、错误摘要和 query hash。

## 8. 推荐的数据表结构

本轮不执行迁移。下一阶段建议在现有 schema 之上新增以下离线统计表，而不是修改已有 V3 数据：

### `trend_refresh_runs`

| 字段 | 用途 |
|---|---|
| `run_id` | 批次主键 |
| `started_at` / `finished_at` | 批次时间 |
| `as_of_date` | 本批次目标自然日 |
| `mapping_version` / `query_version` | 口径版本 |
| `status` | running/succeeded/failed |
| `api_request_count` | 请求数 |
| `rate_limit_remaining` | 完成时额度 |
| `error_summary` | 失败原因；成功时 NULL |

### `trend_category_topics`

| 字段 | 用途 |
|---|---|
| `mapping_version` | 映射版本 |
| `category_id` / `category_name` | 一级领域 |
| `openalex_topic_id` | Topic ID |
| `status` / `confidence` | 审核结果 |
| `description` / `match_reason` | 审计证据 |
| `effective_from` / `effective_to` | 生效区间 |

建议主键：`(mapping_version, category_id, openalex_topic_id)`；只有 approved 行参与查询。

### `trend_category_window_counts`

| 字段 | 用途 |
|---|---|
| `run_id` | 采集批次 |
| `mapping_version` / `query_version` | 口径版本 |
| `category_id` | 一级领域 |
| `as_of_date` | 折线点日期 `t` |
| `window_start` / `window_end` | `t-29` / `t` |
| `openalex_record_count` | `meta.count` |
| `work_family_count` | 尚未实现时 NULL |
| `count_scope` | `complete`（对定义查询的完整计数） |
| `corpus_filter` / `topic_filter` | 实际查询口径 |
| `query_hash` | 查询审计与幂等 |
| `observed_at` | 实际观察时间 |
| `source_updated_at` | 可获得时保存 |
| `latency_ms` | API 延迟 |
| `source` | `OpenAlex API` |

建议唯一键：`(run_id, category_id, as_of_date)`。发布视图只选择整批成功的 `run_id`，防止五个类别来自不同批次。

不建议现在复用 `topic_snapshots` 冒充一级领域滚动值：它以单 Topic 为粒度，且缺少映射版本与类别窗口的明确合同。

## 9. 下一阶段 30 天滚动统计方案

### 日常增量

每天成功完成数据准备后，对五个类别各发一个请求：

```text
for category in five_categories:
    topics = approved topics for mapping_version
    count = OpenAlex meta.count where
        primary_location.source.is_core = true
        publication_date between t-29 and t
        primary_topic.id in topics
    save one category/window row
publish only when all five rows pass validation
```

每天只需 5 个主计数请求；可另加健康检查和重试。直接查询 30 天窗口比把 30 个历史日计数相加更稳妥，因为它与产品定义完全一致，也避免缺日时错误求和。

### 首次历史回填

由于 `group_by=publication_date` 不支持，历史折线必须对每个 `t` 单独查询。例如回填 90 天需要 `90 × 5 = 450` 个主请求。应在有独立 API key、限流感知和可恢复断点的离线任务中执行，不能在页面请求中执行。

### 回填修订

OpenAlex 会回填 Topic 和 publication metadata。建议每天除最新 `t` 外，重查最近 7-30 个折线点，并保留 `observed_at` 与批次版本；不要原地覆盖而失去修订证据。更长历史可按周重查。

### 质量门槛

- 五个类别必须使用同一 `as_of_date`、mapping version、query version 和 corpus filter；
- 任一类别失败则整批不发布；
- `meta.count` 缺失、非整数或负数时失败；
- review/rejected Topic 不得进入过滤器；
- 与上一批次的异常跳变只触发告警，不自动解释为科研升温；
- 首页始终读取最后一个完整成功批次。

## 10. 本轮停止点

本轮已完成 Topic 映射、API 验证、查询建议和表结构设计。未执行数据库迁移、历史回填、自动更新、定时任务或首页 UI 修改；这些内容等待下一步指令。
