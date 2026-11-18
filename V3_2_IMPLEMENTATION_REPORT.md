# University Research Radar V3.2 实施与验收报告

验收日期：2026-11-17  
分支：`feature/collection-worker-v3`  
Windows 时区：`Singapore Standard Time`（UTC+08:00，无夏令时）

## 1. 实施结论

V3.2 自动更新系统已完成开发，并在正式数据库副本上通过真实 OpenAlex
五窗口验收。Windows 计划任务安装脚本已通过语法与配置校验，但依据任务
要求尚未注册；正式数据库未启动 V3.2 Works 采集。

正式数据库已在备份后完成增量 Schema 4→5 回填：Works 仍为 198 条，
旧批次与旧查询审计均保留，新增一条 `2026-11-16 / 198` 历史日期观察。
完整性检查为 `ok`，外键违规为 0。

## 2. 数据库变更

Schema 4 新增：

- `daily_collection_runs`
- `daily_collection_windows`
- `work_date_observations`
- `work_date_status`
- `work_type_observations`
- `work_source_state`
- `collection_entity_changes`

Schema 5 只执行旧 V3 发布批次回填。它不会重建实体表，也不会删除 Works、
批次、查询审计或历史扫描记录。

同一发表日期的新任务键为：

- `logical_date = daily_run_id / collection_run_id`
- `shard_key = publication_date`

因此，同一运行批次可幂等恢复，不同运行可以对同一发表日期建立独立批次。

## 3. 采集与回查逻辑

- 固定窗口：D-1、D-2、D-3、D-7、D-14。
- 漏跑补录：从上次成功日的下一天补到昨天，上限 30 天。
- 周一补录：自动覆盖周六、周日未处理发表日期。
- 每个窗口先查询实时 `meta.count`，再执行完整 Cursor 分页。
- 新 Work 插入；源哈希变化的 Work 更新；未变化记录不重写实体和关系。
- 作者、多机构署名和 Topic 关系按当前源记录同步，支持新增与删除。
- `meta.count` 下降只记录审计，不删除历史 Works。
- 批次只有在完整计数与外键检查通过后才能原子发布。

稳定状态规则：至少 3 次成功观察、至少 2 次连续计数不变、发表日期至少达到
D-3，才标记 `stable`。一次计数不变只进入 `stabilizing`；后续仍可回查。

## 4. Work 类型口径

每批保留 OpenAlex 原始 `type`，并提供原始类型和标准组两种统计：

- `article`、`review` 原始计数分别保留；标准组为 `article_review`
- `conference-paper` → `conference_paper`
- `preprint` → `preprint`
- `dataset`、`software` → `dataset_software`
- `report`、`book`、`dissertation` 分组保留
- 其他原始类型进入 `other`

该分类不代表同行评审状态，所有 Works 不会统一称为同行评审论文。

## 5. 真实 API 预算与运行结果

运行前实时预算：

| 窗口 | meta.count | 预计 Cursor 页 |
|---|---:|---:|
| D-1 / 2026-11-16 | 12,034 | 61 |
| D-2 / 2026-11-15 | 5,016 | 26 |
| D-3 / 2026-11-14 | 7,176 | 36 |
| D-7 / 2026-11-10 | 16,794 | 84 |
| D-14 / 2026-11-03 | 19,152 | 96 |

合计 60,172 条，预计 303 个 Cursor 请求，加 5 次预检约 308 请求。
实际执行 322 请求，差额来自 14 次受控重试；实际响应流量 505,633,603
字节，运行后 API 剩余额度 9,248。

预算策略按 D-1 最高优先级执行。每个低优先级窗口开始前都会结合当前剩余额度、
100 请求保留量和日预算重新判断；不足时跳过低优先级窗口，不无限重试。

## 6. 延迟收录实证

D-1 初次预检曾返回 496；几分钟后的正式 Cursor 首页已返回 12,034。
系统以正式批次 `meta.count` 为准并完成全部分页：

- 历史观察：198
- 新观察：12,034
- 计数变化：+11,836
- 实际新增 Work：11,837
- 更新旧 Work：197
- 一条旧 Work 未出现在当前源结果中，但被保留而非删除

随后同日期再次创建独立批次，12,034 条全部识别为未变化，新增 0、更新 0、
未变化 12,034，证明重复回查不会重复写入。

## 7. 验收结果

- 单元与回归测试：35/35 通过。
- Python 语法检查：通过。
- 五个日期窗口真实副本采集：全部成功并发布。
- 测试副本 Works：60,172 条。
- 测试副本数据质量报告：16 项全部 `passed`。
- 测试副本采集任务：9 个全部 `succeeded`。
- SQLite 完整性：`ok`。
- SQLite 外键违规：0。
- 失败批次不替换成功快照：通过。
- 同批次重复执行幂等：通过。
- 不同批次同日期重新请求：通过。
- 源数据变化和关系增删：通过。
- 计数下降保留历史：通过。
- Worker 并发互斥：通过。
- 周一/漏跑补录日期计算：通过。
- 备份、恢复及默认拒绝覆盖：通过。

## 8. Windows 自动任务

计划任务配置已验证：

- 名称：`UniversityResearchRadar-DailyCollection`
- 时间：周一至周五 09:00，本地 Windows 时区
- 解释器：项目 `.venv\Scripts\python.exe`
- 工作目录：项目根目录
- `StartWhenAvailable = True`
- `MultipleInstances = IgnoreNew`
- 当前 Windows 用户、有限权限
- 独立于 Streamlit 运行

当前查询结果为任务不存在，符合“确认后再注册”的要求。注册命令为：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_collection_tasks_windows.ps1 -Register
```

## 9. 备份与恢复

每日任务开始前使用 SQLite Backup API 创建 `daily-*.db`；周一额外保留
`weekly-YYYY-Www.db`。默认保留 14 个每日备份、8 个周备份。轮转只处理
新命名备份，不删除既有 `radar-v3-*` 文件。

正式 Schema 5 迁移前备份：

`persistent/backups/daily-20261117-235236.db`

恢复脚本默认要求新目标路径，除非显式指定覆盖：

```powershell
.\.venv\Scripts\python.exe scripts\restore_database.py BACKUP --destination RESTORED_DB
```

## 10. 安全检查

- `.env`、`persistent/`、`logs/`、`*.db` 均被 Git 忽略。
- API Key 只从进程或用户环境变量读取。
- 查询审计主动剔除 `api_key` 参数。
- 报告与日志未记录密钥值。
- 未提交、未推送、未修改网站 UI、未注册计划任务。
