# 全球高校科研数据采集系统架构

## 1. 设计目标

建立与 Streamlit 解耦、可恢复、可审计、可逐步扩展的 OpenAlex 数据流水线，覆盖全球高校并重点提供中国高校对照。系统支持全学科热点自动发现，同时保留现有预设分类作为解释和导航层，而不是把预设分类直接当作实时热点。

## 2. 总体架构

```text
OpenAlex API / OpenAlex Snapshot
              |
              v
     独立采集 Worker（单写者）
       | 任务租约、限流、重试
       | 分片、游标、检查点
       v
  V3 控制面 + V1.1 实体表 + 暂存批次
              |
        数据质量审计通过
              |
              v
       原子切换已发布批次
              |
              v
  指标快照 / 热点候选 / 告警读模型
              |
              v
     Streamlit 只读展示本地结果
```

核心原则：网站不发起全球采集；采集进程不直接替换最后一次成功结果；每个数字都能追溯到批次、查询条件和数据源。

## 3. 运行组件

建议新增但不替换现有文件：

```text
collector/
  openalex_client.py          # Key、限流、响应头、重试、select 白名单
  jobs.py                     # 任务定义和依赖
  worker.py                   # 租约、执行、状态机
  catalog_sync.py             # Topics、Institutions 索引同步
  works_ingest.py             # 日期分片、重叠回查、实体和关系写入
  checkpoints.py              # cursor、分片和恢复点
  metrics.py                  # 周期统计与覆盖率
  hotspot_detection.py        # 自动候选、分类匹配、待审核池
  quality.py                  # 完整性、去重、关系、覆盖变化检查
repositories/
  collection_repository.py   # V3 控制面和批次读写
scripts/
  run_collection_worker.py
  run_collection_task.py
  install_windows_tasks.ps1
  install_linux_cron.sh
```

现有 `storage.py` 继续负责 V1.1 实体持久化，可逐步抽出批量 upsert，但不一次性重写。`dashboard_repository.py` 只读取已发布批次。

## 4. 任务设计

| 任务 | 建议频率 | 输入 | 成功产物 |
|---|---|---|---|
| `daily_ingest` | 每日 | 发表日期窗口、国家/高校分层 | Works、作者、署名、主题关系、查询审计 |
| `sync_topics` | 每周；首次全量 | Topics cursor | Topic 索引及目录历史 |
| `sync_institutions` | 每周；首次全量 | education institutions cursor | 高校索引、别名、地区信息 |
| `calculate_metrics` | 每日采集后 | 已校验实体和完整计数 | 主题、高校、全局周期指标 |
| `detect_hotspots` | 每日或每周 | 多窗口主题指标 | 新兴主题候选、分类匹配结果 |
| `publish_snapshots` | 上游通过后 | 同一批次全部产物 | 已发布快照指针 |
| `audit_data` | 每日及发布前 | 批次实体、关系、指标 | 质量报告和发布门禁 |

### 4.1 任务状态机

`pending -> leased -> running -> validating -> succeeded -> published`

失败路径为 `running/validating -> retry_wait -> running`，超过上限后进入 `failed`。租约包含 `leased_by` 和 `lease_expires_at`，进程异常后可安全接管。相同任务、逻辑日期和分片必须有唯一键，避免重复触发。

### 4.2 重试策略

- 429、502、503、504：指数退避并加入随机抖动，尊重 `Retry-After`。
- 网络超时：可重试。
- 400、401、403：配置或权限错误，停止该分片并生成明确报告。
- 单条数据解析失败：隔离到错误记录，不应让已验证的其他分片丢失；发布门禁根据比例决定是否拒绝批次。
- 每次尝试记录请求数、响应字节数、限流响应头和错误摘要。

## 5. 采集策略

### 5.1 Topics 索引

首次以 200 条/页 cursor 全量同步，保存 OpenAlex ID、显示名、层级字段、描述、works/cited_by 计数、相关领域信息、源更新时间和采集时间。后续每周复扫目录；若服务等级支持更新时间过滤，再切换到增量。

### 5.2 Institutions 索引

使用 `type:education` 过滤，首次全量同步。保存 OpenAlex ID、规范名称、别名、国家代码、地区、ROR、主页、类型、层级关系及来源时间。别名进入独立历史表，不覆盖旧别名。

### 5.3 Works 采集

免费 API 建议按发表日期逐日分片，并对最近 7 至 30 日重叠回查。每个日期分片先获取 `total_count`，再根据预算决定完整分页或分层采样。

推荐两种数据层：

1. 近期完整窗口：在请求和存储预算允许时，对最近若干天完成教育机构关联 Works 的完整分页。
2. 长期代表样本：按日期、国家、机构和 Topic 分层保存代表论文，同时保留每层完整命中数。

每个 Work 至少保存 OpenAlex ID、标题、发表日期、DOI、作者署名、机构、国家、Topics、Primary Topic、被引数、来源期刊、开放获取、landing page、源更新时间和采集批次。

### 5.4 DOI 和版本冲突

- OpenAlex Work ID 始终作为来源身份，不因 DOI 相同而覆盖另一条来源记录。
- 规范化 DOI 后建立冲突队列；不能仅以 DOI 自动删除记录。
- `work_families` 表示预印本、会议版和正式发表版的候选归组。
- 自动归组需保存规则、置信度和证据，低置信度进入人工审核。
- 指标计算应明确按“OpenAlex Work”还是“作品族”去重，并保存算法版本。

## 6. 全学科热点发现

### 6.1 候选生成

不能每天对 4,516 个 Topic、多个地区和多个时间窗口逐一请求。推荐分层流程：

1. 同步全量 Topic 目录。
2. 使用 OpenAlex group-by 或批量计数能力生成全球和中国 Top 候选。
3. 对高活跃、新增、加速或跨学科候选执行 30/90/365 日及历史同期精确计数。
4. 将剩余 Topics 按优先级分片，在多日内轮转刷新。
5. 对高优先级主题采集高校参与和代表论文样本。
6. 计算增长、加速度、覆盖变化、新进入高校和跨学科程度。
7. 匹配 `research_taxonomy.json`；不能匹配的进入 `unmatched_topic_candidates`。

### 6.2 热点门禁

候选成为可展示热点前至少满足：

- 当前窗口和基线窗口均有可解释的数据覆盖；
- 小样本经过收缩或达到最小数量门槛；
- 采样覆盖变化不足以解释观察到的增长，或使用完整计数；
- 指标缺失时保留缺失，不补零或伪造分数；
- 保存 `score_coverage`、`data_confidence`、算法版本和计算批次；
- 预设分类只用于归类，不作为热点证据。

## 7. 增量 Schema 变更清单

建议以 Schema V3 增量迁移创建下列表，不删除、不重建 V2 表。字段命名在实现前可按现有风格微调。

### 7.1 采集控制面

#### `collection_jobs`

- 主键：`id`
- 关键字段：`job_type`、`logical_date`、`shard_key`、`status`、`priority`、`leased_by`、`lease_expires_at`、`attempt_count`、`max_attempts`、`next_retry_at`、`batch_id`、`created_at`、`updated_at`
- 唯一约束：`(job_type, logical_date, shard_key)`
- 索引：`(status, next_retry_at, priority)`、`lease_expires_at`、`batch_id`

#### `collection_job_attempts`

- 记录每次开始/结束、退出状态、请求数、响应字节数、429 数量、错误类型、日志位置。
- 唯一约束：`(job_id, attempt_no)`

#### `collection_checkpoints`

- 记录 `job_id`、`checkpoint_type`、cursor、页码、日期分片、最后 OpenAlex ID、已处理数量和校验和。
- 唯一约束：`(job_id, checkpoint_type, shard_key)`

#### `source_query_audit`

- 记录实体端点、规范化查询参数、过滤器、`select` 字段版本、请求时间、`total_count`、`sampled_count`、`coverage_rate`、`is_truncated`、HTTP 状态、配额响应头、批次和数据源。
- 索引：查询哈希、批次、实体类型、时间窗口。

#### `snapshot_batches`

- 记录批次范围、状态、开始/结束时间、代码版本、Schema 版本、算法版本、质量状态和统计摘要。

#### `published_snapshots`

- 每种快照类型保存当前已发布 `batch_id`，更新必须在单一事务中完成。
- 唯一约束：`snapshot_type`。

### 7.2 身份和历史

#### `institution_aliases`

- `institution_id` 外键、别名、语言、别名类型、有效时间、来源、首次/最近发现时间。
- 唯一约束：`(institution_id, normalized_alias, source)`。

#### `work_families` / `work_family_members`

- 保存作品族及其成员、关系类型、证据、归组方法、置信度和人工审核状态。
- 同一 Work 在同一算法版本下最多属于一个已确认作品族。

#### `topic_catalog_history`

- 保存 Topic 名称、层级、领域、描述等目录属性的有效期和源更新时间。

#### `topic_relations`

- 保存 Topic 间关系、关系类型、权重、来源及有效期。

#### `topic_classification_events`

- 保存 Topic 与本地三级分类的匹配、规则/模型版本、置信度、审核状态和证据。

### 7.3 指标和页面读模型

#### `global_metric_snapshots`

- 全局/国家范围、周期、完整计数、采样计数、覆盖率、指标值、批次、算法版本、置信度。

#### `topic_period_metrics`

- Topic、地区、周期起止、论文完整/样本数、同比基线、增长、加速度、作者/机构数、跨学科程度、覆盖率、置信度、批次、算法版本。
- 唯一约束：`(topic_id, region_scope, period_start, period_end, metric_version, batch_id)`。

#### `institution_period_metrics`

- Institution、周期、论文数、Topic 数、活跃作者数、增长、样本/完整口径、批次和置信度。

#### `topic_institution_metrics`

- Topic 与 Institution 在指定周期的论文数、首次进入时间、活跃作者数和覆盖信息。

#### `research_alerts` / `alert_evidence`

- 告警类型、严重度、触发规则、状态、批次；证据表保存指标、阈值、来源查询和代表 Work。

#### `unmatched_topic_candidates`

- 保存未匹配本地分类的 OpenAlex Topic、热度证据、推荐路径、审核状态。

#### `data_quality_reports`

- 保存批次级检查项、阈值、实际值、通过状态和问题样本。

### 7.4 对 V2 表的兼容处理

- 不删除或改名现有表和列。
- 不在迁移中重算历史扫描。
- 先创建 V3 新表，再以独立可恢复任务进行回填。
- `works.doi` 冲突需要先确定兼容策略；在确认前不修改现有唯一约束。
- 所有新增外键和索引通过重复迁移测试后再进入生产。

## 8. 发布与一致性

1. 采集批次创建为 `collecting`。
2. 所有分片完成后进入 `validating`。
3. `audit_data` 检查实体去重、关系完整、外键、数量偏差、覆盖率突变和错误比例。
4. `calculate_metrics` 与 `detect_hotspots` 只读取同一已校验批次。
5. `publish_snapshots` 在单一事务中更新 `published_snapshots`。
6. 网站查询始终带当前已发布批次条件。
7. 失败批次保留诊断信息，但不改变当前发布指针。

## 9. 调度和部署

### Windows

任务计划程序调用 `run_collection_task.py`，而不是启动 Streamlit 页面。每个任务设置“若任务已运行则不启动新实例”，应用内部租约仍作为第二道保护。API Key 读取主机环境变量或不入 Git 的 `.env`。

### Linux

cron 或 systemd timer 调用同一 CLI。生产 Docker Compose 可增加单独 `collector` 服务，但不能让 `web` 和 `collector` 同时运行调度器。SQLite 数据目录和日志目录使用持久化卷。

## 10. 存储演进

- 起步：SQLite 保存控制面、实体关系、近窗论文、快照和页面读模型，严格单写者。
- 扩展：将长期原始 Works 分区保存为 Parquet，SQLite 保存索引和聚合。
- 全量：若使用 OpenAlex Snapshot，应采用对象存储 + DuckDB/ClickHouse/PostgreSQL 等批处理或分析方案，不把完整 Snapshot 直接灌入单个 SQLite。

