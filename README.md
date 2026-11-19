# 全球高校科研热点与产业创新情报平台 V1.4.2

`university-research-radar` 是基于 Streamlit、SQLite 和 OpenAlex 的科研热点监测平台。当前首页使用 OpenAlex 官方 Topic 层级，在六个 Physical Sciences Fields 内展示真实的90天与360天科研热点排名、周期新增 Works 和周/月环比增长率。

## V1.4.2 首页

- 分类版本：`openalex-taxonomy-2026-11-18-v1.4`。
- 学科范围：Chemical Engineering、Chemistry、Computer Science、Energy、Engineering、Materials Science。
- Topic 范围：1,063个，每篇 Work 仅按 `primary_topic.id` 归入一个 Topic。
- Corpus：`primary_location.source.is_core:true`。
- 日期口径：只使用 `publication_date`，不混用 Created Date 或 Updated Date。
- 观察窗口：近90天、近360天。
- 图表：近90天按连续7天聚合，近360天按自然月聚合；Works 与 Growth Rate 两张图共享相同时间分桶。
- 增长率：90天使用上一等长周期周环比；360天使用月环比，当前月使用 MTD 同期比较。
- 排名：基于完整日序列求和，支持六学科合并或单 Field 独立计算 TOP 5 / TOP 10。
- 增长率排序：使用最新周度或月度聚合增长率在当前 Field 内排名。
- 中文名称：1,063个 V1.4 Topic 全覆盖；已审核名称与待审核候选名称保留明确状态，英文原名保留在 Tooltip 和详情中。
- 缺失处理：查询失败和未完成回填保持缺失，不会自动补0；完整游标查询中未返回的 Topic 才记录为真实0。

首页数据通过 Repository 从本地 SQLite 读取，不会在页面请求中直接调用 OpenAlex。

## 其他功能

- 领域扫描：中国高校与全球高校同口径对照。
- 主题深挖：规模、历史基线、高校参与和候选课题组证据。
- 历史记录：保留成功与失败运行及实际检索式。
- 数据管理：数据库状态、覆盖范围和备份信息。
- 旧版五领域30天滚动快照继续保留，不与 V1.4 Topic 日新增口径混用。

## 数据库版本

当前 Schema 为 v6。V1.4 新增版本化分类表：

- `taxonomy_versions`
- `field_scope_versions`
- `topic_taxonomy_versions`

Topic 排名和日序列继续使用：

- `topic_ranking_snapshots`
- `topic_daily_counts`
- `topic_update_runs`

迁移是增量式的，不会重建数据库或删除旧趋势数据。

## 本地运行

```powershell
python -m pip install -r requirements.txt
$env:RADAR_DB_PATH = "C:\path\to\radar.db"
$env:OPENALEX_API_KEY = "your-key"
python -m streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8503
```

浏览器访问 `http://127.0.0.1:8503/`。同一局域网设备可访问 `http://主机局域网IP:8503/`，前提是主机防火墙允许该端口。

## 初始化与回填

导入 V1.3.4 的排名和 TOP 10 审计数据：

```powershell
python -m scripts.import_topic_hotspot_audit --database C:\path\to\radar.db
```

导入冻结的 V1.4 六学科 Topic 分类元数据（不下载 Works）：

```powershell
python -m scripts.import_v14_taxonomy --database C:\path\to\radar.db
```

回填1,063个 Topic 的360天每日新增 Works：

```powershell
python -m scripts.backfill_v14_daily `
  --database C:\path\to\radar.db `
  --end-date 2026-11-18 `
  --workers 6
```

回填器按日期使用 `group_by=primary_topic.id` 游标分页，支持断点续跑、429/5xx指数退避、修订历史和完成后发布。API Key 只从 `OPENALEX_API_KEY` 环境变量读取。

## 测试

```powershell
python -m unittest discover -s tests -v
```

当前自动化测试覆盖数据库迁移、Topic 映射、趋势查询、缺失值处理、90/360天切换和 Streamlit 页面加载。

V1.4.2 当前测试结果为40/40通过。真实开发数据库审计覆盖六个 Field、两种时间窗口、Works/增长率排序、TOP 5/TOP 10及自定义选择，共60组检查。详细结果见 [V1_4_2_FIELD_FILTER_AND_CHINESE_TOPIC_FIX_REPORT.md](V1_4_2_FIELD_FILTER_AND_CHINESE_TOPIC_FIX_REPORT.md)。

真实数据库审计：

```powershell
python -m scripts.audit_v142_dashboard `
  --database C:\path\to\radar.db `
  --output work\v142_dashboard_audit.json
```

浏览器验收使用独立测试实例和开发依赖：

```powershell
python -m pip install -r requirements-dev.txt
python -m scripts.browser_audit_v142 `
  --url http://127.0.0.1:8505 `
  --output-dir work\browser-v142 `
  --output work\v142_browser_audit.json
```

## 部署与安全

- `.env`、`.streamlit/secrets.toml`、SQLite 数据库、WAL/SHM、日志和备份均由 `.gitignore` 排除。
- 不要把 OpenAlex API Key 写入源码、报告或 Git 历史。
- 公司局域网部署、Windows/Linux 防火墙、备份恢复见 [DEPLOYMENT_LAN.md](DEPLOYMENT_LAN.md)。
- 生产主机更新流程见 [UPDATE_WORKFLOW.md](UPDATE_WORKFLOW.md)。

## 审计资料

仓库保留 V1.1 至 V1.4.2 的 Topic、Subfield、Field 审计 CSV、中文候选目录与报告，用于复核分类版本、统计口径、API成本和历史决策。生产数据库不提交到 GitHub。
