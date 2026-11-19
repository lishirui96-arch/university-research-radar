# V1.3.2 OpenAlex 官方 Fields TOP 7 只读审计报告

> 审计日期：2026-11-18。第一阶段只读执行；未修改首页、正式映射、生产数据库、现有五条曲线或历史快照。

## 1. 执行结论

- OpenAlex 官方目录确认包含 **26 Fields、252 Subfields、4,516 Topics**。
- 本地开发库的 `topics`、`works`、`work_topics` 表均为空，因此不能从现有 SQLite 明细重算 Field；现有 1,825 条五领域滚动快照也不能转换为官方 Field 统计。
- OpenAlex Works API 实测支持 `group_by=primary_topic.field.id`。单次请求可在相同日期和 core corpus 口径下返回26个 Field 的唯一 Works 计数。
- 365个日期全部查询成功，26个 Field 的日计数求和与独立365天窗口查询逐项完全一致。
- TOP 7 完全由最近365天 Works 数量降序产生，没有按 Topic 数量、增长率或人工偏好筛选。

## 2. 固定统计口径

| 项目 | 口径 |
|---|---|
| 实体 | OpenAlex Works |
| 地理 | 全球 |
| Corpus | `primary_location.source.is_core:true` |
| 日期 | `publication_date` |
| 分类 | `primary_topic.field.id` |
| 计数 | 每个 Work 最多进入一个 Field；无 primary Topic/Field 的 Works 单列为未分类 |
| 365天窗口 | 2025-11-19 ～ 2026-11-18，闭区间 |
| 最近90天 | 2026-08-21 ～ 2026-11-18，闭区间 |
| 此前90天 | 2026-05-23 ～ 2026-08-20，闭区间 |
| 排名 | 最近365天唯一 Works 数量降序 |

中文名是本项目的显示译名；OpenAlex 官方 Field 名称仍以英文为准。

## 3. OpenAlex 官方26个 Fields

| Field ID | Official Field Name | 中文显示名 | Domain |
|---:|---|---|---|
| 11 | Agricultural and Biological Sciences | 农业与生物科学 | Life Sciences |
| 12 | Arts and Humanities | 艺术与人文 | Social Sciences |
| 13 | Biochemistry, Genetics and Molecular Biology | 生物化学、遗传学与分子生物学 | Life Sciences |
| 14 | Business, Management and Accounting | 商业、管理与会计 | Social Sciences |
| 15 | Chemical Engineering | 化学工程 | Physical Sciences |
| 16 | Chemistry | 化学 | Physical Sciences |
| 17 | Computer Science | 计算机科学 | Physical Sciences |
| 18 | Decision Sciences | 决策科学 | Social Sciences |
| 19 | Earth and Planetary Sciences | 地球与行星科学 | Physical Sciences |
| 20 | Economics, Econometrics and Finance | 经济学、计量经济学与金融 | Social Sciences |
| 21 | Energy | 能源 | Physical Sciences |
| 22 | Engineering | 工程 | Physical Sciences |
| 23 | Environmental Science | 环境科学 | Physical Sciences |
| 24 | Immunology and Microbiology | 免疫学与微生物学 | Life Sciences |
| 25 | Materials Science | 材料科学 | Physical Sciences |
| 26 | Mathematics | 数学 | Physical Sciences |
| 27 | Medicine | 医学 | Health Sciences |
| 28 | Neuroscience | 神经科学 | Life Sciences |
| 29 | Nursing | 护理学 | Health Sciences |
| 30 | Pharmacology, Toxicology and Pharmaceutics | 药理学、毒理学与药剂学 | Life Sciences |
| 31 | Physics and Astronomy | 物理学与天文学 | Physical Sciences |
| 32 | Psychology | 心理学 | Social Sciences |
| 33 | Social Sciences | 社会科学 | Social Sciences |
| 34 | Veterinary | 兽医学 | Health Sciences |
| 35 | Dentistry | 牙科学 | Health Sciences |
| 36 | Health Professions | 健康专业 | Health Sciences |

## 4. 最近365天完整排名

| 排名 | Field ID | Field | 中文名 | 365天 Works | 最近90天 | 此前90天 | 相邻90天增长率 |
|---:|---:|---|---|---:|---:|---:|---:|
| 1 | 27 | Medicine | 医学 | 1,143,912 | 269,223 | 278,135 | -3.20% |
| 2 | 22 | Engineering | 工程 | 555,718 | 113,793 | 131,050 | -13.17% |
| 3 | 33 | Social Sciences | 社会科学 | 274,458 | 61,179 | 67,751 | -9.70% |
| 4 | 17 | Computer Science | 计算机科学 | 256,170 | 50,231 | 61,818 | -18.74% |
| 5 | 13 | Biochemistry, Genetics and Molecular Biology | 生物化学、遗传学与分子生物学 | 221,724 | 50,599 | 52,800 | -4.17% |
| 6 | 11 | Agricultural and Biological Sciences | 农业与生物科学 | 214,202 | 48,814 | 51,398 | -5.03% |
| 7 | 23 | Environmental Science | 环境科学 | 199,679 | 45,388 | 48,411 | -6.24% |
| 8 | 25 | Materials Science | 材料科学 | 195,532 | 44,520 | 47,349 | -5.97% |
| 9 | 31 | Physics and Astronomy | 物理学与天文学 | 136,415 | 31,644 | 32,912 | -3.85% |
| 10 | 32 | Psychology | 心理学 | 102,501 | 22,901 | 25,431 | -9.95% |
| 11 | 16 | Chemistry | 化学 | 93,581 | 21,611 | 21,984 | -1.70% |
| 12 | 14 | Business, Management and Accounting | 商业、管理与会计 | 84,111 | 18,466 | 20,411 | -9.53% |
| 13 | 21 | Energy | 能源 | 82,878 | 18,285 | 20,053 | -8.82% |
| 14 | 19 | Earth and Planetary Sciences | 地球与行星科学 | 77,626 | 16,575 | 18,007 | -7.95% |
| 15 | 28 | Neuroscience | 神经科学 | 73,416 | 16,533 | 17,063 | -3.11% |
| 16 | 26 | Mathematics | 数学 | 68,129 | 13,711 | 15,753 | -12.96% |
| 17 | 20 | Economics, Econometrics and Finance | 经济学、计量经济学与金融 | 62,570 | 13,790 | 15,434 | -10.65% |
| 18 | 24 | Immunology and Microbiology | 免疫学与微生物学 | 60,073 | 13,950 | 15,016 | -7.10% |
| 19 | 36 | Health Professions | 健康专业 | 57,384 | 13,747 | 14,198 | -3.18% |
| 20 | 12 | Arts and Humanities | 艺术与人文 | 49,898 | 10,541 | 12,504 | -15.70% |
| 21 | 35 | Dentistry | 牙科学 | 37,434 | 8,983 | 8,857 | +1.42% |
| 22 | 18 | Decision Sciences | 决策科学 | 35,760 | 7,550 | 8,698 | -13.20% |
| 23 | 30 | Pharmacology, Toxicology and Pharmaceutics | 药理学、毒理学与药剂学 | 34,407 | 8,140 | 8,408 | -3.19% |
| 24 | 15 | Chemical Engineering | 化学工程 | 32,347 | 7,204 | 7,800 | -7.64% |
| 25 | 29 | Nursing | 护理学 | 27,908 | 6,522 | 7,224 | -9.72% |
| 26 | 34 | Veterinary | 兽医学 | 7,044 | 1,892 | 1,656 | +14.25% |

## 5. 最近90天完整排名

| 90天排名 | 365天排名 | Field ID | Field | 中文名 | 最近90天 Works |
|---:|---:|---:|---|---|---:|
| 1 | 1 | 27 | Medicine | 医学 | 269,223 |
| 2 | 2 | 22 | Engineering | 工程 | 113,793 |
| 3 | 3 | 33 | Social Sciences | 社会科学 | 61,179 |
| 4 | 5 | 13 | Biochemistry, Genetics and Molecular Biology | 生物化学、遗传学与分子生物学 | 50,599 |
| 5 | 4 | 17 | Computer Science | 计算机科学 | 50,231 |
| 6 | 6 | 11 | Agricultural and Biological Sciences | 农业与生物科学 | 48,814 |
| 7 | 7 | 23 | Environmental Science | 环境科学 | 45,388 |
| 8 | 8 | 25 | Materials Science | 材料科学 | 44,520 |
| 9 | 9 | 31 | Physics and Astronomy | 物理学与天文学 | 31,644 |
| 10 | 10 | 32 | Psychology | 心理学 | 22,901 |
| 11 | 11 | 16 | Chemistry | 化学 | 21,611 |
| 12 | 12 | 14 | Business, Management and Accounting | 商业、管理与会计 | 18,466 |
| 13 | 13 | 21 | Energy | 能源 | 18,285 |
| 14 | 14 | 19 | Earth and Planetary Sciences | 地球与行星科学 | 16,575 |
| 15 | 15 | 28 | Neuroscience | 神经科学 | 16,533 |
| 16 | 18 | 24 | Immunology and Microbiology | 免疫学与微生物学 | 13,950 |
| 17 | 17 | 20 | Economics, Econometrics and Finance | 经济学、计量经济学与金融 | 13,790 |
| 18 | 19 | 36 | Health Professions | 健康专业 | 13,747 |
| 19 | 16 | 26 | Mathematics | 数学 | 13,711 |
| 20 | 20 | 12 | Arts and Humanities | 艺术与人文 | 10,541 |
| 21 | 21 | 35 | Dentistry | 牙科学 | 8,983 |
| 22 | 23 | 30 | Pharmacology, Toxicology and Pharmaceutics | 药理学、毒理学与药剂学 | 8,140 |
| 23 | 22 | 18 | Decision Sciences | 决策科学 | 7,550 |
| 24 | 24 | 15 | Chemical Engineering | 化学工程 | 7,204 |
| 25 | 25 | 29 | Nursing | 护理学 | 6,522 |
| 26 | 26 | 34 | Veterinary | 兽医学 | 1,892 |

## 6. 最终 TOP 7

| 排名 | Field ID | 图例名称 | 365天 Works | 最近90天 | 此前90天 | 增长率 |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 27 | Medicine（医学） | 1,143,912 | 269,223 | 278,135 | -3.20% |
| 2 | 22 | Engineering（工程） | 555,718 | 113,793 | 131,050 | -13.17% |
| 3 | 33 | Social Sciences（社会科学） | 274,458 | 61,179 | 67,751 | -9.70% |
| 4 | 17 | Computer Science（计算机科学） | 256,170 | 50,231 | 61,818 | -18.74% |
| 5 | 13 | Biochemistry, Genetics and Molecular Biology（生物化学、遗传学与分子生物学） | 221,724 | 50,599 | 52,800 | -4.17% |
| 6 | 11 | Agricultural and Biological Sciences（农业与生物科学） | 214,202 | 48,814 | 51,398 | -5.03% |
| 7 | 23 | Environmental Science（环境科学） | 199,679 | 45,388 | 48,411 | -6.24% |

最近90天排名中 Biochemistry, Genetics and Molecular Biology 为第4，Computer Science 为第5；但 TOP 7 的成员集合与365天排名相同。首页成员应继续以365天排名为准。

## 7. 每日数据完整性

| 检查项 | 结果 |
|---|---:|
| 预期日期 | 365 |
| 成功日期 | 365 |
| 缺失日期 | 0 |
| 每日分组查询失败 | 0 |
| 每日查询重试 | 0 |
| 26个 Field 日计数之和 vs 365天窗口差异 | 全部为0 |
| 每个 Field 可用日数 | 365/365 |

`OPENALEX_FIELD_DAILY_365D_AUDIT.csv` 包含 365 × 26 = 9,490 行真实每日数据。成功的整日分组响应中未返回的 Field 被记录为真实的0，而不是请求失败；这些0仅出现在2026-11-17/18的少数字段。

### 7.1 分类覆盖率

| 窗口 | 全部 core Works | 有 Field 归属 | 未分类 Works | 覆盖率 |
|---|---:|---:|---:|---:|
| 最近365天 | 4,275,127 | 4,184,877 | 90,250 | 97.89% |
| 最近90天 | 953,790 | 935,792 | 17,998 | 98.11% |
| 此前90天 | 1,029,873 | 1,010,121 | 19,752 | 98.08% |

未分类 Works 没有可用的 `primary_topic.field.id`，因此不进入任何 Field。对已有 Field 归属的 Works，26组计数互斥，不存在跨 Field 重复。

### 7.2 收录延迟风险

2026-11-18 当日仍处于收录中：多个 Field 当前为0或极低值。这表示“API查询覆盖完整”，不等于“最新日期的文献收录已经最终稳定”。所有最近90天增长率都应标注查询时点，并通过 D-2、D-3、D-7、D-14 历史修订机制持续更新；不能把当前负增长直接解释为科研活动真实下降。

## 8. API请求量与成本

- 正式审计请求：**368 次**，包括3次周期查询和365次每日查询。
- 能力验证请求：1次。因此本阶段实际成功请求总数为369次。
- 失败/重试：0/0。结束时额度剩余：7729。
- OpenAlex 返回的单次成本标记为0.0001美元等价额度，368次正式请求约0.0368美元。
- 若采用逐 Field、逐日请求，需要9,490次；已通过官方 Field 分组将基础量降低到365次。

## 9. 建议的历史回填与每日更新方案

1. 新建独立 Field 维表，保存26个 Field、Domain 和 taxonomy version。
2. 新建 Field 日统计表，以 `(date, field_id, revision_no)` 唯一；保存 `daily_works_count`、`query_as_of`、`query_status`、`mapping_version`、`query_version`、`is_current`、`supersedes_id`。失败请求不得写0。
3. 周期累计量从成功的每日非重叠计数求和；页面选择30/90/365天时，从所选起点开始计算运行累计，不使用旧的30天滚动快照。
4. TOP 7 排名每天从 Field 日表滚动汇总最近365天后本地生成，不需要额外26次 API 查询。
5. 每日基础更新只需1次按日 Field 分组请求；建议额外复查 D-2、D-3、D-7、D-14，共最多5次/日。
6. 保存排名快照和查询日志，使 Field 进入/退出 TOP 7 可追溯。
7. 在测试库完成365天回填、修订和接口测试后，再由人工确认是否切换首页。

建议表：

- `openalex_fields(field_id, field_name, field_name_zh, domain_id, domain_name, taxonomy_version, updated_at)`
- `field_daily_counts(date, field_id, daily_works_count, query_as_of, query_status, mapping_version, query_version, revision_no, is_current, supersedes_id, created_at, updated_at)`
- `field_ranking_snapshots(ranking_date, field_id, rank_365d, works_365d, window_start, window_end, query_as_of, calculation_version)`
- `field_query_logs(date, request_status, http_status, duration_ms, retry_count, error_message, rate_limit_remaining, query_version)`

## 10. 与现有五领域口径的区别

| 项目 | 现有五领域 | 新 Field TOP 7 |
|---|---|---|
| 分类来源 | 人工审核的24个 approved Topics | OpenAlex 官方全部4,516 Topics→26 Fields |
| 一级类别 | 固定5个自定义技术集合 | 26个官方 Fields 中按365天数量动态选7个 |
| 时间点数值 | 截至该日的30天滚动累计 | 当日新增唯一 Works |
| 周期累计 | 不能累加重叠快照 | 可对非重叠每日计数求和 |
| 排名 | 固定顺序，无动态排名 | 最近365天唯一 Works 数降序 |
| 去重 | Topic OR 查询返回唯一 Works | 每个 Work 的单一 primary Topic 归入一个 Field |
| 历史数据 | 1,825条五类快照 | 需要独立的9,490条 Field 日统计 |
| 可复用性 | 不能转换为新口径 | 必须独立回填和版本化 |

## 11. 第一阶段验收结论

真实 TOP 7 已得到，API能力、请求成本和365天每日数据完整性均已验证。技术上可以进入第二阶段的测试库迁移、Field统计引擎和repository接口开发；在用户确认 TOP 7 前，不应修改首页或替换现有五条曲线。
