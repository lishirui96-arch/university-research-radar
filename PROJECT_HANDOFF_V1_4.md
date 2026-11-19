# University Research Radar 项目交接说明（更新至 V1.4.2）

交接日期：2026-11-19（Asia/Singapore）
项目：`university-research-radar`
GitHub：<https://github.com/lishirui96-arch/university-research-radar>

> 说明：第1至14节记录 V1.4 基线及其历史状态；V1.4.2 的最新实现与验收结果以第15节为准。

## 1. 当前 Git 状态

- 当前分支：`main`
- 已推送提交：`3177a934ac3c9cf318ad64b75d29f3680d45e976`
- 提交说明：`feat: add audited Topic analytics and V1.4 dashboard`
- 推送完成时，本地 `HEAD`、`origin/main` 和 GitHub `main` 一致。
- 上述提交包含51个文件，自动化测试为32/32通过。
- 本交接文件是在推送之后新建的，因此尚未包含在上述 GitHub 提交中。

## 2. 本地项目与数据库

项目路径：

```text
C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\university-research-radar
```

当前 V1.4 非正式开发数据库：

```text
C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\trend-v1-1-test-20261118.db
```

重要说明：

- SQLite 数据库、API Key、`.env`、WAL/SHM、日志和备份均未上传 GitHub。
- 数据库位于仓库目录之外，并由 `.gitignore` 排除。
- 不要删除、重建或覆盖该数据库。
- 正式数据库 `persistent/data/radar.db` 没有被本轮 V1.4 数据回填覆盖。

备份文件：

```text
C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\trend-v1-1-test-20261118-pre-v14-20261119.db
C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\trend-v1-1-test-20261118-pre-v14-full-daily-20261119.db
```

第二个备份是执行1,063 Topic全量360天日序列回填前的完整备份，`PRAGMA integrity_check=ok`。

## 3. 已完成版本

### V1.1

- 建立五个自定义研究领域的30天滚动成果统计引擎。
- 统一使用 OpenAlex Works、`publication_date`、`primary_topic.id` 和 core corpus。
- core corpus 过滤条件为：

```text
primary_location.source.is_core:true
```

- 失败请求不会写成0。
- 支持修订历史、幂等运行、查询日志和断点恢复。

### V1.2

- 完成旧五领域365天历史快照回填。
- 365天 × 5领域，共1,825条有效快照。
- 旧五领域数据和表仍保留，未被 V1.4 删除或覆盖。

### V1.3 / V1.3.5

- 将真实趋势数据接入 Streamlit 首页。
- 完成4,516个 OpenAlex Topics 的90天和360天全量排名审计。
- 导入两个周期的完整排名以及原 TOP 10 日序列。
- 建立：
  - `openalex_topics`
  - `topic_daily_counts`
  - `topic_ranking_snapshots`
  - `topic_update_runs`

### V1.4

- 首页调整为六个 Physical Sciences Fields 内的 Topic 热点监测。
- 页面整体按照深蓝科技风格重构。
- 新增每日新增 Works 图和7日滚动增长率图。
- 支持近90天、近360天、Field筛选、TOP 5、TOP 10和自定义 Topic。
- 增加真实 KPI、TOP 10表格、Topic详情、热点速览和采集状态。
- 所有可见 TOP Topic 已补充中文名称。
- 完成1,063个 Topic的360天全量日序列回填。

## 4. V1.4 固定统计口径

仅使用以下六个 OpenAlex Fields：

| Field ID | Field | 中文名 | Topic 数 |
|---:|---|---|---:|
| 15 | Chemical Engineering | 化学工程 | 24 |
| 16 | Chemistry | 化学 | 119 |
| 17 | Computer Science | 计算机科学 | 265 |
| 21 | Energy | 能源 | 44 |
| 22 | Engineering | 工程学 | 467 |
| 25 | Materials Science | 材料科学 | 144 |
|  | 合计 |  | 1,063 |

分类版本：

```text
openalex-taxonomy-2026-11-18-v1.4
```

统计规则：

- 全球 Works。
- core corpus：`primary_location.source.is_core:true`。
- 日期：只使用 `publication_date`。
- 分类：只使用 `primary_topic.id`。
- 每篇 Work 最多归入一个 Topic。
- 不使用 Created Date、Updated Date、Concepts、关键词或多 Topic 关联进行正式统计。
- OpenAlex API 使用 `group_by=primary_topic.id` 和 cursor 分页。
- 页面不直接调用 OpenAlex，只读取本地 SQLite。

## 5. V1.4 当前真实数据

历史范围：

```text
2025-11-24 至 2026-11-18，共360个自然日
```

全量回填结果：

- Topic：1,063
- 日期：360
- current 日序列记录：382,680
- 完整率：100%
- 重复 current 日期/Topic：0
- 缺失日期：0
- 数据库完整性：`ok`
- 外键错误：0
- 回填运行 ID：`topic-v14-full-daily-20261118-v1`
- 成功 API 请求：1,341
- 自动重试：24
- 失败日期：0

OpenAlex 在旧审计后发生了正常历史修订，因此首页在日序列完整时以最新完整日序列求和生成排名，旧排名快照仍保留，不静默覆盖历史审计证据。

当前总量：

- 近90天六学科 Works：259,645
- 近360天六学科 Works：1,202,103

当前近90天 TOP 10：

| 排名 | Topic ID | 中文名 | Works |
|---:|---|---|---:|
| 1 | T10030 | 能源转换电催化剂 | 3,671 |
| 2 | T10078 | 先进光催化技术 | 3,626 |
| 3 | T10036 | 先进神经网络应用 | 2,535 |
| 4 | T10018 | 电池材料研究进展 | 2,323 |
| 5 | T10247 | 钙钛矿材料及其应用 | 2,193 |
| 6 | T10281 | 先进电池材料与技术 | 2,187 |
| 7 | T10033 | 混凝土与水泥材料研究 | 2,068 |
| 8 | T10338 | 先进传感与能量采集材料 | 1,740 |
| 9 | T10063 | 纳米颗粒药物递送 | 1,685 |
| 10 | T10179 | 超级电容器材料与制备 | 1,658 |

当前近360天 TOP 10：

| 排名 | Topic ID | 中文名 | Works |
|---:|---|---|---:|
| 1 | T10030 | 能源转换电催化剂 | 15,296 |
| 2 | T10078 | 先进光催化技术 | 15,270 |
| 3 | T10036 | 先进神经网络应用 | 12,777 |
| 4 | T10018 | 电池材料研究进展 | 10,061 |
| 5 | T10247 | 钙钛矿材料及其应用 | 9,579 |
| 6 | T10281 | 先进电池材料与技术 | 8,973 |
| 7 | T10033 | 混凝土与水泥材料研究 | 8,325 |
| 8 | T10220 | 机械故障诊断技术 | 7,589 |
| 9 | T10179 | 超级电容器材料与制备 | 7,171 |
| 10 | T10338 | 先进传感与能量采集材料 | 7,131 |

## 6. 增长率口径与限制

折线图增长率已经实现：

```text
Growth Rate(t) = (近7日新增 Works / 前7日新增 Works - 1) × 100%
```

- 上一7日为0或数据不足时显示 NA。
- 近90天和近360天折线均已使用完整日序列。
- 360天窗口最早部分若缺少展示窗口前14天，会保持 NA，不会补造。

尚未完成的部分：

- 排行榜的90天同比前90天增长率尚未采集。
- 排行榜的360天同比前360天增长率尚未采集。
- 因此“按增长率排序”会显示数据不足提示，不能把7日滚动增长率冒充完整窗口增长率。
- 若下一阶段要完成增长率榜单，需要额外回填前一等长窗口，而不是修改现有日序列定义。

## 7. Schema 与关键数据表

当前 Schema 版本：v6。

V1.4 新增版本化分类表：

- `taxonomy_versions`
- `field_scope_versions`
- `topic_taxonomy_versions`

Topic统计表：

- `openalex_topics`
- `topic_daily_counts`
- `topic_ranking_snapshots`
- `topic_update_runs`

旧五领域表继续保留：

- `trend_30d_snapshots`
- `trend_query_logs`
- `trend_backfill_runs`

数据库迁移入口：

- `migrations.py`
- `storage.py`

## 8. 关键代码文件

首页：

```text
app_pages/global_dashboard.py
ui_styles.py
streamlit_app.py
```

Repository：

```text
dashboard_repository.py
```

V1.4 分类：

```text
collector/v14_taxonomy.py
scripts/import_v14_taxonomy.py
```

V1.4 全量日序列回填：

```text
collector/v14_daily_backfill.py
scripts/backfill_v14_daily.py
```

Topic排名与日常更新：

```text
collector/topic_hotspots.py
collector/topic_hotspot_updater.py
scripts/import_topic_hotspot_audit.py
scripts/update_topic_hotspots.py
```

旧五领域统计：

```text
collector/trend_analytics.py
scripts/backfill_trend_365d.py
scripts/validate_trend_openalex.py
config/trend_topic_mapping.json
```

测试：

```text
tests/test_global_dashboard.py
tests/test_trend_analytics.py
tests/test_trend_topic_mapping.py
tests/test_v11.py
```

## 9. 页面运行方式

当前页面使用开发数据库启动：

```powershell
cd C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\university-research-radar
$env:RADAR_DB_PATH='C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\trend-v1-1-test-20261118.db'
python -m streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8503
```

访问地址：

- 本机：<http://127.0.0.1:8503/>
- 同一公司 WiFi：<http://192.168.0.52:8503/>

如果地址无法访问，先检查8503端口是否仍在监听，以及 Windows 防火墙是否允许公司网段访问。

## 10. 重新导入与回填命令

不要在已有完整数据库上无意义重复执行。仅在新数据库初始化、恢复或明确需要修订时运行。

导入 V1.3.4 审计排名：

```powershell
python -m scripts.import_topic_hotspot_audit --database C:\path\to\radar.db
```

导入 V1.4 分类元数据：

```powershell
python -m scripts.import_v14_taxonomy --database C:\path\to\radar.db
```

完整日序列回填：

```powershell
python -m scripts.backfill_v14_daily `
  --database C:\path\to\radar.db `
  --end-date 2026-11-18 `
  --workers 6
```

回填器特性：

- 按日期查询六学科范围。
- `group_by=primary_topic.id` cursor分页。
- 429、5xx和网络超时指数退避。
- 受控并发。
- 每个日期达到1,063条后才事务提交。
- 支持断点续跑。
- 保留 revision/current 历史。
- 全部360天完整后才将批次标记为 `published`。

API Key 只从环境变量读取：

```powershell
$env:OPENALEX_API_KEY='...'
```

不要把真实 Key 写入源码、Markdown、Git、日志或聊天记录。

## 11. 测试与验收

全套测试：

```powershell
python -m unittest discover -s tests -v
```

最近一次结果：

```text
32 tests passed
```

已验证：

- Schema迁移幂等。
- 旧数据不被删除。
- V1.4六学科范围为1,063 Topic。
- 90/360天页面切换无报错。
- TOP 5和TOP 10曲线完整。
- 近90天 TOP 10：900个点、90日期、10 Topic、0缺失。
- 近360天 TOP 10：3,600个点、360日期、10 Topic、0缺失。
- 失败或未完成数据不会自动填0。
- 中文 Topic 图例正常。

## 12. GitHub 发布情况

已推送内容包括：

- V1.4首页和样式。
- Schema v6和Repository。
- Topic采集、导入、更新和完整回填代码。
- V1.1至V1.4审计报告与CSV。
- 中文 Topic 显示名称。
- 测试和更新后的README。

未推送内容：

- SQLite开发数据库。
- 数据库备份。
- OpenAlex API Key。
- `.env`和Streamlit secrets。
- 运行日志与缓存。

## 13. 下一对话开始时建议检查

依次执行：

```powershell
cd C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\university-research-radar
git status --short
git log -1 --oneline --decorate
Get-NetTCPConnection -State Listen -LocalPort 8503 -ErrorAction SilentlyContinue
python -m unittest discover -s tests -v
```

下一位开发者应先完整阅读本文件，再阅读：

- `README.md`
- `dashboard_repository.py`
- `app_pages/global_dashboard.py`
- `collector/v14_daily_backfill.py`
- `collector/v14_taxonomy.py`

## 14. 后续工作边界

除非用户明确要求，不要：

- 删除或重建数据库。
- 覆盖旧五领域1,825条历史快照。
- 把旧分类数据冒充 V1.4 分类数据。
- 把缺失数据写成0。
- 混用 Created Date、Updated Date 与 Publication Date。
- 修改 V3/V3.2 原始采集逻辑。
- 自动注册 Windows 正式定时任务。
- 上传数据库或 API Key 到 GitHub。

最明确的下一阶段候选工作是：采集前一90天和前一360天的等长基线，以完成排行榜增长率和“按增长率排序”。在执行前应先估算请求量、检查API额度，并设计与现有日序列相同的修订与发布机制。

## 15. V1.4.2 增量更新（2026-11-19）

V1.4.2 已在不请求 OpenAlex、不修改 SQLite Schema、不覆盖历史数据的前提下完成：

- 近90天图表由每日点调整为13个周度点：首段6天，其余12段各7天。
- 近360天图表调整为13个自然月点；完整月按月环比，当前月按 MTD 同期比较。
- Works 与 Growth Rate 两张图共享相同时间分桶、日期范围和 Topic 选择。
- 六个 Field 的 TOP 5 / TOP 10 均在当前 Field 内独立计算，不混入其他学科。
- “按增长率排序”使用最新周度/月度聚合增长率，不再返回空榜单。
- 新增 `config/v14_topic_names_zh.csv`，覆盖全部1,063 Topic：11个 `verified`，1,052个 `candidate`。
- 中文候选不会冒充已审核名称；英文原名、翻译状态和来源继续保留。
- 页面送入 Altair 前统一转换数值类型，并显式固定两张图共同的13个横轴刻度。

验收结果：

- 自动化测试：40/40通过。
- 真实 SQLite 数据链路审计：60/60组通过。
- 独立 Chrome 浏览器验收：36/36个页面状态通过。
- 独立测试实例使用8505；原8503和8504服务未停止。

详细报告：

```text
V1_4_2_FIELD_FILTER_AND_CHINESE_TOPIC_FIX_REPORT.md
```

V1.4 第6节关于“榜单增长率不可计算”的描述仅适用于完整90/360天前置窗口同比。V1.4.2 新增的是基于已完成周度/月度聚合的最新周期增长率排序，两者不是同一统计口径。
