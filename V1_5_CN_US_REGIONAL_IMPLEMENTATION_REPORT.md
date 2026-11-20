# V1.5 CN/US 区域科研热点实施报告

实施日期：2026-11-20（Asia/Singapore）  
代码基线：`0dbfb18d6df790ac687b33bac7f879e25ec9047e`  
区域批次：`regional-v15-20261118-v1`  
排名日期：2026-11-18

## 1. 实施结论

V1.5 已按修订方案完成：GLOBAL 完全保留 V1.4 读取路径和原始数据；仅新增 CN、US 两套区域数据。CN 与 US 使用同一个新区域批次，页面切换地区只读取本地 SQLite，不会实时请求 OpenAlex。

原始 V1.4 数据库 `trend-v1-1-test-20261118.db` 始终只读。Schema v7 迁移和区域回填只发生在开发副本 `work/v15-regional/radar-v15.db`，该数据库及日志受 `.gitignore` 保护，不提交 GitHub。

## 2. 统计合同

- Corpus：`primary_location.source.is_core:true`
- 日期：`publication_date`
- 分类：`primary_topic.id`
- Field：15、16、17、21、22、25
- Topic：冻结 V1.4 分类的1,063个 Topic
- CN：`authorships.institutions.country_code:CN`
- US：`authorships.institutions.country_code:US`
- 不使用 `institution_type=education`
- OpenAlex `group_by=primary_topic.id` 按 Work 聚合，同一 Work 在一个国家查询内只计一次

90天和360天榜单均比较相邻、等长、不重叠窗口：

```text
growth_amount = current_works - previous_works
growth_rate = growth_amount / previous_works
```

前置窗口为0时，`growth_rate` 保持 NULL，状态为 `zero_baseline`，不生成无穷增长率。

## 3. GLOBAL 保护结果

- 未发送任何 GLOBAL OpenAlex 请求。
- 未重新生成 GLOBAL 排名或日序列。
- 未向 Schema v7 区域表写入 GLOBAL；数据库 CHECK 约束只允许 CN/US。
- 首页选择 GLOBAL 时继续调用 `get_v14_hotspot_dashboard`。
- 采集前后核对 `topic_update_runs`、`topic_ranking_snapshots`、`topic_daily_counts` 的行级 SHA-256 指纹。
- V1.5 副本与原始 V1.4 数据库的 GLOBAL 指纹完全一致。

## 4. Schema v7

新增表：

- `regional_snapshot_batches`：CN/US 共用批次和原子发布状态。
- `regional_topic_runs`：每个区域的运行、请求、重试和版本信息。
- `regional_topic_period_snapshots`：90/360天当前窗口、前置窗口、增长量、增长率及三种独立排名。
- `regional_topic_daily_counts`：全部1,063 Topic 的391天日序列。
- `regional_query_logs`：过滤器、窗口、页数、重试和脱敏错误摘要。

所有表均保留 `region_code`、分类/查询/计算版本、`source_run_id`、`query_as_of` 和数据状态；联合唯一约束阻止地区、周期和排名相互覆盖。

## 5. 数据覆盖与请求量

日序列范围：2025-10-24 至 2026-11-18，共391天。

| 地区 | 日序列行数 | Topic | 90天 Works | 前置90天 Works | 360天 Works | 前置360天 Works |
|---|---:|---:|---:|---:|---:|---:|
| CN | 415,633 | 1,063 | 117,697 | 130,733 | 540,916 | 506,607 |
| US | 415,633 | 1,063 | 21,365 | 25,666 | 100,660 | 106,665 |

- 成功 API 请求：1,634
- 自动重试：8
- CN/US 成功日查询：各391
- CN/US 90天排名：各1,063
- CN/US 360天排名：各1,063
- 失败连接只写入失败日志，不写日数据；断点续跑后对应日期全部成功完成。

## 6. 数据质量审计

`scripts/audit_v15_regional.py` 的最终结果为 `complete: true`：

- SQLite `integrity_check=ok`
- 外键违规：0
- 两个区域均为同一已发布批次
- 每区391个日期、1,063个 Topic、415,633行日数据
- 90/360天日序列求和与周期排名不一致数：0
- Works rank 和 Growth Amount rank：每区每周期1,063个唯一排名
- Growth Rate rank 与非空增长率数量完全一致
- 前置基数为0但生成增长率的记录：0
- 查询过滤器全部含正确国家、Core Sources、六 Field 和日期范围
- 教育机构类型过滤：0
- GLOBAL 指纹变化：0

国际合作抽样验证：OpenAlex Work `W4416296080` 的署名机构国家包含 CN、SG、US；使用 CN 和 US 国家过滤分别查询时均返回该 Work，两个查询中各返回一次。

## 7. 页面与浏览器验收

首页新增 `GLOBAL | CN | US` 地区选择，位置为“地区范围 → 观察窗口 → 学科范围 → 榜单口径 → 更新时间”。

路由规则：

- GLOBAL：原 V1.4 Repository。
- CN/US：最后一个同时发布的 Schema v7 区域批次。

浏览器使用独立 `http://127.0.0.1:8509` 实例验收，未停止8506、8507、8508：

- 3地区 × 2周期 × 6学科：36/36通过。
- 每个场景的 Works 与 Growth Rate 图均显示5条真实曲线。
- 90天和360天每条曲线均为13个周期点，最后日期均为2026-11-18。
- GLOBAL/CN/US 的 TOP 10：两张图均为10条曲线。
- GLOBAL/CN/US 的自定义模式：默认5个 Topic 正常显示，可继续选择最多10个。
- GLOBAL/CN/US 的增长率排序：排名、图例和两张图同步刷新。
- 切换学科后的 Topic 数分别为24、119、265、44、467、144，无跨学科残留。
- 修复了再次点击已选地区导致地区值暂时为空的交互边界，空值安全回退 GLOBAL。

最终截图保存在忽略目录 `work/v15-regional/browser/`，不提交数据库或运行产物。

## 8. 自动化测试

命令：

```text
python -m unittest discover -s tests -v
```

结果：47/47通过。

新增覆盖包括：

- Schema v7 只接受 CN/US。
- GLOBAL 采集请求被拒绝。
- 国家过滤合同且无教育机构限制。
- 90/360窗口、零基期和三类独立排名。
- API Key 日志及异常脱敏。
- TLS/网络异常安全退出。
- CN 已发布批次 Repository 读取。
- 地区控件空选择安全回退。

## 9. 修改文件

- `migrations.py`
- `storage.py`
- `collector/regional_v15.py`
- `scripts/backfill_regional_v15.py`
- `scripts/audit_v15_regional.py`
- `dashboard_repository.py`
- `app_pages/global_dashboard.py`
- `tests/test_regional_v15.py`
- `tests/test_global_dashboard.py`
- `tests/test_trend_analytics.py`
- `tests/test_v11.py`
- `README.md`
- `V1_5_REGIONAL_READ_ONLY_AUDIT_AND_PLAN.md`
- `V1_5_CN_US_REGIONAL_IMPLEMENTATION_REPORT.md`

## 10. 未解决问题

无阻断性问题。运行期间本机 HTTPS 代理曾导致 OpenAlex TLS 握手失败；失败日期没有写入虚假0，使用同一批次断点续跑后全部完成。正式部署仍需把已验收的 V1.5 数据库副本放入受备份保护的部署路径，并通过 `RADAR_DB_PATH` 指向该文件；数据库本身不进入 GitHub。
