# 全球科研热点趋势 V1.1：数据库迁移报告

生成日期：2026-11-18  
目标 Schema 版本：3

## 迁移方案

实施前采用以下方案：

1. 先读取现有 `schema_metadata` 和迁移入口，不重建 SQLite 文件。
2. 以 additive migration 新增趋势专用表，不修改或删除 V3/V3.2 业务表和数据。
3. 所有 DDL 使用 `IF NOT EXISTS`，由现有 `initialize_database()` 在事务中执行并更新 Schema 版本。
4. 将运行状态、逐请求审计日志和可读取快照分表保存。
5. 查询日志只追加；快照采用版本号、当前标志和前序引用保留历史。
6. 用部分唯一索引保证每个“领域 + 快照日期”最多一个当前版本。
7. 先在测试数据库副本迁移和回填，正式数据库本轮不迁移、不覆盖。

## 新增表

### `trend_backfill_runs`

保存一个回填或修订批次的范围、预期/完成/成功/失败数量、状态、三个版本号、修订原因和运行时间。状态支持 `running`、`paused`、`partial`、`success`、`failed`。

### `trend_query_logs`

逐请求追加保存：

- 领域、快照日期、窗口起止日期和 Topic ID 列表；
- 完整查询过滤器、请求状态、HTTP 状态和 `works_count`；
- `query_as_of`、耗时、重试次数、错误信息和查询版本；
- 可获得的限流响应头。

`works_count` 可为 NULL，用于明确表示失败；约束禁止负数。

### `trend_30d_snapshots`

保存可供读取的成功快照，包括领域、日期窗口、成果数、查询时点、数据状态、映射/查询/计算版本，以及：

- `revision_no`：同领域同快照日期的版本号；
- `is_current`：当前有效版本；
- `supersedes_id`：指向被替代版本；
- `revision_reason`：修订原因。

只有 `data_status='success'` 的非负计数可以进入此表。

## 索引与约束

- `trend_backfill_runs(status, start_snapshot_date, end_snapshot_date)`：批次状态与日期查询。
- `trend_query_logs(run_id, request_status, category_id, snapshot_date)`：恢复和批次核验。
- `trend_query_logs(category_id, snapshot_date, created_at)`：历史请求审计。
- `UNIQUE(category_id, snapshot_date, revision_no)`：版本号唯一。
- 部分唯一索引 `(category_id, snapshot_date) WHERE is_current=1`：保证单一当前版本。
- `trend_30d_snapshots(snapshot_date, category_id, is_current)`：趋势读取。
- 查询日志到批次使用外键；快照到批次和前序快照使用限制删除的外键，避免历史被级联破坏。

## 事务与发布

- 单条查询日志及运行进度在事务中写入。
- 完整批次发布使用立即写事务：先核验成功逻辑键数量等于预期数量，再写入或修订全部快照并将批次标为成功。
- 发布前任何失败或暂停都只留下审计日志，不产生可读取快照。
- 同值重查不新增快照版本；变更值重查保留旧行并插入新版本。

## 实施与验证结果

- 测试副本已从现有结构迁移到 Schema v3。
- 迁移连续执行两次无错误，证明幂等。
- 原有表和数据未删除，数据库未重建。
- 30 日回填后：2 个运行批次、170 条查询日志、150 条当前快照。
- 当前没有多版本快照，因为真实历史复查结果未变化；变更值修订链由自动化测试验证。
- `PRAGMA integrity_check` 返回 `ok`；`PRAGMA foreign_key_check` 返回 0 条违规。
- 项目内正式/开发数据库没有执行本次真实回填；真实请求仅写入明确指定的测试副本。

## 回滚与正式迁移建议

本迁移是增加式的，运行时无需删除旧表。正式迁移前应创建可恢复备份，迁移后先核验 Schema 版本、三张表、索引、完整性和外键，再启动小批回填。若应用层需要暂时停用趋势功能，可停止回填并让读取接口返回 unavailable/partial；不应删除趋势表或改写历史日志。

