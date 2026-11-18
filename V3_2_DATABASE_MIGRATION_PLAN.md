# V3.2 数据库增量修改方案

日期：2026-11-17  
初始Schema：3  
目标Schema：5  
原则：只新增表和索引，不删除、重命名或重建V3表，不修改已有批次和历史记录。

实施说明：Schema 4 创建 V3.2 自动更新与历史回查表；Schema 5 单独回填
既有 V3 已发布 Works 批次的日期观察。拆分版本可让已先行创建 Schema 4
表的数据库继续以可审计、可重复的方式完成历史回填。

## 1. V3限制

V3 `collection_jobs` 的唯一约束为：

```text
(job_type, logical_date, shard_key)
```

旧Works任务使用 `logical_date=publication_date` 和固定 `shard_key=global_education`，因此同一发表日期成功后无法创建新Job。

V3.2不修改该约束。新任务改为：

- `logical_date=daily_run_id`：标识一次独立的每日运行。
- `shard_key=publication_date`：标识该运行中的日期分片。

不同运行ID可为同一发表日期创建独立批次；同一运行ID和日期重复执行仍命中同一Job并从检查点恢复。

## 2. 新增表

### `daily_collection_runs`

保存一次后台每日运行：

- `run_id` 主键。
- 本地运行日期、时区、触发方式和计划时间。
- 运行状态、开始/结束时间。
- 请求预算、实际请求、响应流量、重试和最低剩余额度。
- 备份路径、报告路径、错误摘要。

### `daily_collection_windows`

保存每日运行包含的每个发表日期窗口：

- `run_id + publication_date` 唯一。
- 窗口原因：D-1、D-2、D-3、D-7、D-14或missed-day。
- 优先级、预检 `meta.count`、预计分页请求。
- 对应Job和Batch、执行状态及跳过原因。

### `work_date_observations`

保存每次日期回查的不可变历史观测：

- 发表日期、批次、每日运行ID和观测时间。
- 当前 `meta.count`、上次计数、计数变化。
- 实际采集数、覆盖率、截断状态。
- 新增、更新、未变化Works数。
- 作者新增/更新数、机构关系变化数、Topic关系变化数。
- 请求数、流量、剩余额度、质量状态、稳定状态和发布状态。

每个Batch最多一条观测，不覆盖历史。

### `work_date_status`

保存每个发表日期的当前稳定状态：

- `provisional`
- `rechecking`
- `stabilizing`
- `stable`
- `failed`

记录首次/最近观测、最后计数、成功观测次数、连续无变化次数、最后成功批次和下次建议回查时间。

稳定规则初版：至少3次成功观测、至少2次连续计数无变化、发表日期至少达到D-3。后续D-7/D-14回查如果计数变化，状态重新进入 `provisional`。

### `work_type_observations`

按Batch保存OpenAlex原始Work type和规范统计组：

- 原始类型。
- 规范组：article/review、conference-paper、preprint、dataset/software、report、book、dissertation、other。
- 数量。

不把OpenAlex type解释为同行评审状态。

### `work_source_state`

保存每个Work最近一次OpenAlex源数据哈希：

- 源数据哈希。
- 源更新时间。
- 首次/最近看见批次。
- 最近发生变化批次。

哈希相同的Work计为未变化，不重复写入实体和关系表；哈希变化时执行upsert和关系同步。

### `collection_entity_changes`

按Batch保存去重后的实体和关系变更键：Work新增/更新、作者新增/更新、机构关系新增/删除、Topic关系新增/更新/删除。它用于断点恢复后的准确日报计数，不复制实体内容。

## 3. 兼容与回填

1. V3旧Job和Batch原样保留。
2. 2026-11-16旧批次可回填一条历史日期观测，但不修改其原始审计记录。
3. `works.work_type`继续保存OpenAlex原始type。
4. 新类型统计通过独立观测表提供，不改变旧Works实体结构。
5. 迁移和历史回填分开执行；迁移本身不请求OpenAlex。

## 4. 发布一致性

每个日期分片继续使用V3批次质量门禁。只有完整Cursor采集、`sampled_count=meta.count`、外键检查通过后，才更新：

```text
published_snapshots.snapshot_type = daily_ingest:<publication_date>
```

新批次发布只移动该日期的当前指针，旧批次和所有计数观测永久保留。失败批次不移动指针。

## 5. 迁移测试

- V3正式库副本依次升级到 Schema 4 和 Schema 5。
- 连续执行迁移两次结果一致。
- V3旧Job、Batch、发布指针和198条Works保持完整。
- 外键检查为0，integrity_check为ok。
- 失败可使用迁移前SQLite Backup API备份恢复。

