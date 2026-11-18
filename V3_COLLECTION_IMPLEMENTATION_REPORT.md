# V3 数据采集基础设施实施报告

实施日期：2026-11-17  
开发分支：`feature/collection-worker-v3`  
范围：V3 控制面、OpenAlex 客户端、Topics/Institutions 全量索引、单日 Works 采集  
不在本轮范围：网站 UI 改造、复杂热点算法、30/365 日 Works 回填

## 1. Python 环境

- Windows 未检测到可直接使用的系统 Python 安装。
- 原 `.venv` 指向已不存在的 Python 3.12.9。
- 原环境已保留为 `.venv-broken-20261117`，并加入 Git 忽略。
- 新 `.venv` 使用 Python 3.12.14 创建。
- SQLite：3.53.1
- Streamlit：1.67.0
- Requests：2.34.2
- Pandas：3.1.1
- Altair：6.3.0
- 现有网站真实启动验证：健康状态 `ok`、应用状态 `ready`、5 个页面、0 个异常。

## 2. 数据安全

迁移前备份：

`persistent/backups/radar-v3-pre-migration-20261117-161333.db`

采集后备份：

`persistent/backups/radar-v3-post-sync-20261117-165118.db`

两个备份均由 SQLite Backup API 创建。采集后备份验证结果：

- Schema：3
- 完整性：`ok`
- 外键违规：0
- Works：198
- 大小：83,865,600 bytes

迁移前数据库中的 1 条历史扫描和 3 条主题指标均保留。

密钥安全检查：

- `OPENALEX_API_KEY` 只从进程环境变量读取。
- `.env` 继续由 `.gitignore` 排除。
- 扫描 64 个受 Git 管理或待加入文件，实际 Key 内容命中 0。
- 日志不记录请求 URL、查询参数中的 Key 或 Key 内容。

## 3. Schema V3

新增控制面表：

- `collection_jobs`
- `collection_job_attempts`
- `collection_checkpoints`
- `source_query_audit`
- `snapshot_batches`
- `published_snapshots`
- `data_quality_reports`

新增目录和采集元数据表：

- `topic_catalog_metadata`
- `topic_catalog_history`
- `institution_catalog_metadata`
- `institution_aliases`
- `institution_lineage`
- `work_collection_metadata`
- `doi_conflicts`

迁移采用 V2 -> V3 增量方式，不删除或重建现有实体表。迁移在数据库副本上连续执行两次后，再应用到正式库。

副本迁移结果：Schema 3、迁移记录 3、完整性 `ok`、外键违规 0。

## 4. OpenAlex 客户端

已实现：

- 从 `OPENALEX_API_KEY` 读取认证信息。
- Cursor 分页。
- 强制显式 `select` 字段。
- 默认最小请求间隔 0.12 秒。
- 429、500、502、503、504 指数退避重试。
- `Retry-After` 支持。
- 401 认证错误和 403 权限错误分类。
- 请求数、响应字节数、重试数和配额响应头统计。
- 异常信息不包含认证 URL 或 Key。

正式增量流程未使用 `from_created_date` 或 `from_updated_date`。Works 采用发表日期分片，后续调度默认采集前一个自然日。

## 5. 正式库同步结果

| 任务 | 完整计数 | 实际采集 | 覆盖率 | 请求 | 响应数据 | 重试 | 最低剩余额度 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Topics | 4,516 | 4,516 | 100% | 23 | 3,909,975 bytes | 0 | 9,795 |
| Education Institutions | 30,711 | 30,711 | 100% | 154 | 29,888,584 bytes | 0 | 9,641 |
| 2026-11-16 Works | 198 | 198 | 100% | 1 | 1,376,154 bytes | 0 | 9,640 |
| 合计 |  |  |  | 178 | 35,174,713 bytes | 0 |  |

正式库关系数据：

- 机构别名：87,887
- Works：198
- Authors：723
- Authorships：759
- Authorship-Institution 关系：819
- Work-Topic 关系：576
- DOI 冲突：0

2026-11-16 的 198 篇是 OpenAlex 在本次查询时对该发表日期和教育机构过滤条件返回的完整命中数。近期日期存在索引延迟，不能将该数字解释为稳定的全球日均产出。

## 6. 断点、幂等与失败安全

真实断点测试：

1. Topics 首次只采集 1 页、200 条后停止。
2. 再次运行从第 2 页继续，最终达到 4,516/4,516。
3. Institutions 首次只采集 1 页、200 条后停止。
4. 再次运行从第 2 页继续，最终达到 30,711/30,711。

重复执行测试：

- Topics 同一逻辑日期重跑：0 请求、0 bytes。
- Institutions 同一逻辑日期重跑：0 请求、0 bytes。
- Works 同一日期重跑：0 请求、0 bytes。
- 实体和关系未重复插入。

失败发布测试：

- 未通过质量检查或状态为 `failed` 的批次无法写入 `published_snapshots`。
- `--no-publish` 完成的已验证批次可在后续运行中以 0 个 API 请求完成发布。
- 发布指针和批次状态在同一 SQLite 事务内更新。

## 7. 测试结果

- 自动化测试：22 项全部通过。
- Python 编译检查：通过。
- PowerShell 脚本语法检查：通过。
- SQLite 完整性：`ok`。
- SQLite 外键违规：0。
- 正式批次：3 个任务全部 `succeeded`、3 个已发布快照。
- 失败质量检查：0。
- Streamlit AppTest：通过。
- Streamlit 真实运行：通过，首页读取到 198 篇论文和 353 个近期活跃机构；缺失指标继续显示 `--`。

## 8. 运行方式

单次运行：

```powershell
.\scripts\run_collection_task.ps1 -Task sync_topics
.\scripts\run_collection_task.ps1 -Task sync_institutions
.\scripts\run_collection_task.ps1 -Task daily_ingest
```

指定 Works 日期：

```powershell
.\scripts\run_collection_task.ps1 -Task daily_ingest -PublicationDate 2026-11-16
```

安装 Windows 定时任务：

```powershell
.\scripts\install_collection_tasks_windows.ps1
```

默认计划：每日 02:00 采集前一日 Works；每周日 03:00 同步 Topics；每周日 04:00 同步 Institutions。Windows 安装脚本只注册任务，不写入或复制 API Key。

运行日志位于 `logs/collection.log`，每次命令的 JSON 更新报告位于 `logs/collection-reports/`。两个目录均由 Git 忽略。

## 9. 修改文件

修改：

- `.gitignore`
- `migrations.py`
- `storage.py`
- `tests/test_global_dashboard.py`
- `tests/test_v11.py`

新增：

- `collector/__init__.py`
- `collector/openalex_client.py`
- `collector/catalog_sync.py`
- `collector/works_ingest.py`
- `collector/logging_config.py`
- `repositories/__init__.py`
- `repositories/collection_repository.py`
- `scripts/run_collection_task.py`
- `scripts/run_collection_task.ps1`
- `scripts/install_collection_tasks_windows.ps1`
- `tests/test_collection_v3.py`
- `V3_COLLECTION_IMPLEMENTATION_REPORT.md`

## 10. 当前边界

- 当前套餐不支持 Daily Sync，因此不能保证捕获所有旧论文的后续元数据修改。
- 本轮只采集一个自然日的 Works，没有回填 30 天或 365 天。
- `calculate_metrics`、`detect_hotspots` 和复杂热点算法不在本轮范围。
- Windows 定时任务安装脚本已经提供，但未自动修改本机任务计划程序。
- 本轮没有修改网站 UI，也没有提交或推送 GitHub。

## 11. 回滚

如需审核旧版本，不应直接覆盖当前正式数据库。推荐将迁移前备份复制到新的测试路径，并临时设置 `RADAR_DB_PATH` 指向该副本。确认旧代码和副本可正常启动后，再决定是否执行正式回滚。这样可以保留当前 V3 数据和采集历史。

