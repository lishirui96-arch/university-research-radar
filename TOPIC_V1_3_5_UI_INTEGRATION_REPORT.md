# V1.3.5 Topic TOP 10 首页接入实施报告

## 1. 实施结论

V1.3.4 已核验数据已正式接入指定的非生产开发数据库：

`C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\trend-v1-1-test-20261118.db`

首页“全球科研热点 TOP 10”模块默认显示近90天，可切换近360天。两种模式分别使用自己的 TOP 10 排名和每日新增 Works 序列，不使用模拟值、不复用旧五领域滚动快照，也不把周期总量画成日数据。

## 2. 修改文件

| 文件 | 修改内容 |
|---|---|
| `migrations.py` | schema v5；新增 Topic 维表、日计数、排名快照、更新批次；提供 v5 回滚 SQL |
| `storage.py` | 接入 additive schema v5 迁移 |
| `collector/topic_hotspots.py` | 审计 CSV 全量校验、去重、事务化及幂等导入 |
| `collector/topic_hotspot_updater.py` | 双周期全量排名、榜单并集补数、历史修订、重试、校验和原子发布 |
| `scripts/import_topic_hotspot_audit.py` | V1.3.4 文件导入命令 |
| `scripts/update_topic_hotspots.py` | 可调度的每日更新命令 |
| `dashboard_repository.py` | 新增 `get_topic_hotspot_ranking()` 和 `get_topic_daily_trends()` |
| `app_pages/global_dashboard.py` | 仅替换首页左侧全球趋势模块，继续使用 Altair |
| `tests/test_global_dashboard.py` | 导入、接口、90/360切换、缺失不补0测试 |
| `tests/test_trend_analytics.py` | schema v5 additive 迁移断言 |
| `tests/test_v11.py` | 最新 schema 版本断言 |

未修改 V3/V3.2 采集逻辑、旧五领域映射和旧趋势快照。

## 3. 新增数据库表

- `openalex_topics`
- `topic_daily_counts`
- `topic_ranking_snapshots`
- `topic_update_runs`

关键约束：

- Topic ID 为分类唯一标识。
- `topic_daily_counts` 同一日期、同一 Topic 只允许一条 current 记录。
- 修订以 `revision_no` 保留旧版本。
- 排名以 `ranking_date + period_days` 区分90天和360天。
- Repository 只读取 `published` 批次；不完整批次不能进入首页。

## 4. 导入与一致性

| 项目 | 结果 |
|---|---:|
| OpenAlex Topics | 4,516 |
| 90天完整排名 | 4,516 |
| 360天完整排名 | 4,516 |
| 排名快照合计 | 9,032 |
| 90天展示源数据 | 900 |
| 360天展示源数据 | 3,600 |
| 两榜单 Topic 并集 | 12 |
| 去重后的底层日计数 | 3,780 |
| current 重复日期/Topic | 0 |
| SQLite integrity_check | ok |
| 外键错误 | 0 |
| 原五领域快照 | 1,825，保持不变 |

导入命令重复执行后表行数不增加，幂等性通过。两个周期每个 Topic 的逐日合计均与各自排名 CSV 的 `period_works_count` 完全一致。

2026-11-18 的12个 Topic 均为成功查询得到的0，页面明确标注“收录中”，不解释为科研活动停止。失败请求不会写0。

## 5. 首页实现

- 标题：全球科研热点 TOP 10
- 副标题：GLOBAL RESEARCH HOTSPOTS
- 模块内周期：近90天 / 近360天，默认近90天
- 图表：现有 Altair
- 纵轴：每日新增 Works
- 交互：Tooltip、图例选择/高亮、日期缩放
- 排名表：与当前曲线使用同一个周期榜单
- Topic 信息：中文名、OpenAlex 英文名、Topic ID、Field、Subfield
- 缺失处理：任何一条缺失都会使批次状态变为 partial，首页不画不完整曲线

首页顶部原有“观察窗口”仍服务其他首页内容；Topic 模块不再提供或读取30天模式，只使用自己的90/360天选择器。

## 6. 自动更新

已提供可调度命令：

`python scripts/update_topic_hotspots.py --database <数据库路径> --date YYYY-MM-DD`

流程包括：

1. 90天和360天全部4,516 Topic 的 cursor 分页排名。
2. 分别选取两个周期自己的 TOP 10。
3. 对榜单 Topic 并集补齐缺失的360天历史。
4. 复查 D-0、D-2、D-3、D-7、D-14。
5. 校验日计数之和与周期独立总量。
6. 通过后在单一事务中发布；失败则继续展示上一完整版本。
7. 429、5xx和网络错误指数退避。

正常日预计约49次成功请求：排名约44次，日计数/修订5次，约0.0049美元等价额度/日。新 Topic 入榜时最多增加360次批量日查询。

未注册 Windows 定时任务。代码已具备每日运行能力，但操作系统级调度需要单独确认后启用。

## 7. 测试结果

`python -m unittest discover -s tests -v`

结果：31/31 通过。

覆盖：

- schema 迁移与幂等
- 4,516 Topic 和9,032排名行
- 3,780条去重日序列
- 90天900条、360天3,600条
- 两个周期使用不同 TOP 10
- 每日合计与排名独立计数一致
- 缺失数据不补0
- 首页90 → 360 → 90切换
- 旧趋势引擎回归测试

## 8. 浏览器验收

验收地址：`http://127.0.0.1:8504/`

8503 已被一个既有 Streamlit 进程占用，因此未停止它，另启8504并明确绑定本轮开发数据库。

结果：

- 首页正常加载，无 Streamlit 页面异常。
- 模块位置保持在原左侧趋势区域。
- 90天与360天均渲染10条曲线和排名表。
- 切换后日期范围、图例和榜单同步变化。
- 最新日期收录提示显示正常。
- 页面没有可见错误。

截图：

- `topic-hotspots-90d.png`
- `topic-hotspots-360d.png`

## 9. Git与回滚

本轮未提交、未 push。开始时工作树已经包含 V1.1-V1.3 的未提交修改及报告文件，为避免把既有工作混入新提交，没有自动新建分支或提交。

数据库迁移为纯新增表；`ROLLBACK_MIGRATION_5_SQL` 可删除本轮新增表。正式环境应用前仍应先做数据库备份。本轮只迁移并写入指定开发数据库。

## 10. 未解决事项

- Windows 正式定时任务尚未注册，需要人工确认运行时间和目标数据库。
- 8503 的既有进程未被接管；本轮可验证实例运行在8504。
- 正式数据库尚未迁移或导入，这是按任务要求保留的安全边界。

