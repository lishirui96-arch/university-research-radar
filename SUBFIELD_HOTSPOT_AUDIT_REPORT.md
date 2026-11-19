# V1.3.3 TOP 7 Fields 下属 Subfield 科研热点只读审计报告

> 审计日期：2026-11-18。未修改首页、正式数据库、原五领域映射或既有曲线。

## 1. 执行结论

- 固定七个父级 Field 共包含 **127个官方 Subfields**，层级关系全部来自 `RESEARCH_OPENALEX_TOPIC_HIERARCHY.csv`。
- OpenAlex 实测支持 `group_by=primary_topic.subfield.id`，并支持按七个父级 Field 做 OR 过滤。
- 90天窗口为2026-08-21～2026-11-18；360天窗口为2025-11-24～2026-11-18，均为闭区间。
- 360个日期全部成功；90天序列直接取同一真实日序列最后90天，没有重复请求。
- 127个Subfield的每日计数之和与两个独立周期查询逐项一致，差异全部为0。
- 两个TOP 5成员相同，但Cardiology和Oncology的第4、5名顺序不同。

## 2. 固定统计口径

| 项目 | 口径 |
|---|---|
| 实体 | OpenAlex Works |
| 地理 | 全球 |
| Corpus | `primary_location.source.is_core:true` |
| 日期 | `publication_date` |
| 父级范围 | Field IDs 27、22、33、17、13、11、23 |
| 分类 | `primary_topic.subfield.id` |
| 分组 | `group_by=primary_topic.subfield.id` |
| 日值 | 单个自然日内新增的唯一Works；不是累计值或30天滚动值 |
| 排名 | 各自独立90天/360天唯一Works总量降序 |

## 3. 七个Field的Subfield数量

| Field ID | Field | 中文名 | Subfields |
|---:|---|---|---:|
| 27 | Medicine | 医学 | 42 |
| 22 | Engineering | 工程 | 16 |
| 33 | Social Sciences | 社会科学 | 22 |
| 17 | Computer Science | 计算机科学 | 11 |
| 13 | Biochemistry, Genetics and Molecular Biology | 生物化学、遗传学与分子生物学 | 14 |
| 11 | Agricultural and Biological Sciences | 农业与生物科学 | 11 |
| 23 | Environmental Science | 环境科学 | 11 |

## 4. 完整Subfield清单

下列名称以层级CSV为准。同名Subfield按ID和父级Field保留，不做人工合并。

### Medicine（Field 27）

| Subfield ID | Official Subfield Name | 所属Topics数 |
|---:|---|---:|
| 2702 | Anatomy | 1 |
| 2703 | Anesthesiology and Pain Medicine | 4 |
| 2704 | Biochemistry | 3 |
| 2705 | Cardiology and Cardiovascular Medicine | 29 |
| 2706 | Critical Care and Intensive Care Medicine | 5 |
| 2707 | Complementary and alternative medicine | 20 |
| 2708 | Dermatology | 13 |
| 2711 | Emergency Medicine | 11 |
| 2712 | Endocrinology, Diabetes and Metabolism | 18 |
| 2713 | Epidemiology | 42 |
| 2714 | Family Practice | 2 |
| 2715 | Gastroenterology | 5 |
| 2716 | Genetics | 9 |
| 2717 | Geriatrics and Gerontology | 3 |
| 2718 | Health Informatics | 1 |
| 2720 | Hematology | 12 |
| 2721 | Hepatology | 6 |
| 2723 | Immunology and Allergy | 3 |
| 2724 | Internal Medicine | 1 |
| 2725 | Infectious Diseases | 21 |
| 2726 | Microbiology | 1 |
| 2727 | Nephrology | 7 |
| 2728 | Neurology | 22 |
| 2729 | Obstetrics and Gynecology | 8 |
| 2730 | Oncology | 34 |
| 2731 | Ophthalmology | 12 |
| 2732 | Orthopedics and Sports Medicine | 7 |
| 2733 | Otorhinolaryngology | 3 |
| 2734 | Pathology and Forensic Medicine | 23 |
| 2735 | Pediatrics, Perinatology and Child Health | 20 |
| 2736 | Pharmacology | 22 |
| 2737 | Physiology | 30 |
| 2738 | Psychiatry and Mental health | 16 |
| 2739 | Public Health, Environmental and Occupational Health | 54 |
| 2740 | Pulmonary and Respiratory Medicine | 52 |
| 2741 | Radiology, Nuclear Medicine and Imaging | 30 |
| 2742 | Rehabilitation | 7 |
| 2743 | Reproductive Medicine | 8 |
| 2745 | Rheumatology | 24 |
| 2746 | Surgery | 96 |
| 2747 | Transplantation | 2 |
| 2748 | Urology | 5 |

### Engineering（Field 22）

| Subfield ID | Official Subfield Name | 所属Topics数 |
|---:|---|---:|
| 2200 | General Engineering | 1 |
| 2202 | Aerospace Engineering | 44 |
| 2203 | Automotive Engineering | 12 |
| 2204 | Biomedical Engineering | 72 |
| 2205 | Civil and Structural Engineering | 42 |
| 2206 | Computational Mechanics | 30 |
| 2207 | Control and Systems Engineering | 44 |
| 2208 | Electrical and Electronic Engineering | 117 |
| 2209 | Industrial and Manufacturing Engineering | 17 |
| 2210 | Mechanical Engineering | 79 |
| 2211 | Mechanics of Materials | 29 |
| 2212 | Ocean Engineering | 23 |
| 2213 | Safety, Risk, Reliability and Quality | 12 |
| 2214 | Media Technology | 12 |
| 2215 | Building and Construction | 22 |
| 2216 | Architecture | 4 |

### Social Sciences（Field 33）

| Subfield ID | Official Subfield Name | 所属Topics数 |
|---:|---|---:|
| 3300 | General Social Sciences | 16 |
| 3302 | Archeology | 2 |
| 3303 | Development | 8 |
| 3304 | Education | 137 |
| 3305 | Geography, Planning and Development | 15 |
| 3306 | Health | 14 |
| 3307 | Human Factors and Ergonomics | 3 |
| 3308 | Law | 40 |
| 3309 | Library and Information Sciences | 2 |
| 3310 | Linguistics and Language | 6 |
| 3311 | Safety Research | 19 |
| 3312 | Sociology and Political Science | 224 |
| 3313 | Transportation | 9 |
| 3314 | Anthropology | 25 |
| 3315 | Communication | 16 |
| 3316 | Cultural Studies | 38 |
| 3317 | Demography | 27 |
| 3318 | Gender Studies | 21 |
| 3319 | Life-span and Life-course Studies | 2 |
| 3320 | Political Science and International Relations | 118 |
| 3321 | Public Administration | 3 |
| 3322 | Urban Studies | 19 |

### Computer Science（Field 17）

| Subfield ID | Official Subfield Name | 所属Topics数 |
|---:|---|---:|
| 1702 | Artificial Intelligence | 77 |
| 1703 | Computational Theory and Mathematics | 24 |
| 1704 | Computer Graphics and Computer-Aided Design | 4 |
| 1705 | Computer Networks and Communications | 43 |
| 1706 | Computer Science Applications | 10 |
| 1707 | Computer Vision and Pattern Recognition | 35 |
| 1708 | Hardware and Architecture | 8 |
| 1709 | Human-Computer Interaction | 8 |
| 1710 | Information Systems | 78 |
| 1711 | Signal Processing | 10 |
| 1712 | Software | 5 |

### Biochemistry, Genetics and Molecular Biology（Field 13）

| Subfield ID | Official Subfield Name | 所属Topics数 |
|---:|---|---:|
| 1302 | Aging | 1 |
| 1303 | Biochemistry | 7 |
| 1304 | Biophysics | 6 |
| 1305 | Biotechnology | 8 |
| 1306 | Cancer Research | 13 |
| 1307 | Cell Biology | 17 |
| 1308 | Clinical Biochemistry | 4 |
| 1309 | Developmental Biology | 2 |
| 1310 | Endocrinology | 7 |
| 1311 | Genetics | 40 |
| 1312 | Molecular Biology | 135 |
| 1313 | Molecular Medicine | 3 |
| 1314 | Physiology | 4 |
| 1315 | Structural Biology | 1 |

### Agricultural and Biological Sciences（Field 11）

| Subfield ID | Official Subfield Name | 所属Topics数 |
|---:|---|---:|
| 1100 | General Agricultural and Biological Sciences | 20 |
| 1102 | Agronomy and Crop Science | 11 |
| 1103 | Animal Science and Zoology | 8 |
| 1104 | Aquatic Science | 7 |
| 1105 | Ecology, Evolution, Behavior and Systematics | 33 |
| 1106 | Food Science | 32 |
| 1107 | Forestry | 7 |
| 1108 | Horticulture | 1 |
| 1109 | Insect Science | 14 |
| 1110 | Plant Science | 90 |
| 1111 | Soil Science | 12 |

### Environmental Science（Field 23）

| Subfield ID | Official Subfield Name | 所属Topics数 |
|---:|---|---:|
| 2302 | Ecological Modeling | 3 |
| 2303 | Ecology | 33 |
| 2304 | Environmental Chemistry | 11 |
| 2305 | Environmental Engineering | 19 |
| 2306 | Global and Planetary Change | 30 |
| 2307 | Health, Toxicology and Mutagenesis | 16 |
| 2308 | Management, Monitoring, Policy and Law | 34 |
| 2309 | Nature and Landscape Conservation | 12 |
| 2310 | Pollution | 11 |
| 2311 | Waste Management and Disposal | 9 |
| 2312 | Water Science and Technology | 24 |

## 5. 最近90天TOP 5

| 排名 | Subfield ID | 中文名 / Official Name | Parent Field | 90天Works |
|---:|---:|---|---|---:|
| 1 | 2208 | 电气与电子工程 / Electrical and Electronic Engineering | Engineering | 28,231 |
| 2 | 1312 | 分子生物学 / Molecular Biology | Biochemistry, Genetics and Molecular Biology | 27,898 |
| 3 | 2746 | 外科学 / Surgery | Medicine | 25,803 |
| 4 | 2705 | 心脏病学与心血管医学 / Cardiology and Cardiovascular Medicine | Medicine | 23,422 |
| 5 | 2730 | 肿瘤学 / Oncology | Medicine | 21,667 |

## 6. 最近360天TOP 5

| 排名 | Subfield ID | 中文名 / Official Name | Parent Field | 360天Works |
|---:|---:|---|---|---:|
| 1 | 2208 | 电气与电子工程 / Electrical and Electronic Engineering | Engineering | 151,873 |
| 2 | 1312 | 分子生物学 / Molecular Biology | Biochemistry, Genetics and Molecular Biology | 119,763 |
| 3 | 2746 | 外科学 / Surgery | Medicine | 114,427 |
| 4 | 2730 | 肿瘤学 / Oncology | Medicine | 95,359 |
| 5 | 2705 | 心脏病学与心血管医学 / Cardiology and Cardiovascular Medicine | Medicine | 91,321 |

完整127项排名分别在 `SUBFIELD_RANKING_90D.csv` 和 `SUBFIELD_RANKING_360D.csv`。排名只使用Works数量，`topic_count`仅用于层级审计。

## 7. 每日真实新增数据

- `SUBFIELD_DAILY_90D.csv`：90天 × 5个Subfields = 450行。
- `SUBFIELD_DAILY_360D.csv`：360天 × 5个Subfields = 1,800行。
- `daily_works_count` 是当天新增Works，未累计、未平滑、未使用30天滚动窗口。
- CSV包含中英文图例标签、Parent Field、查询时点、映射版本和修订字段，可直接作为后续折线图数据输入。

## 8. 数据质量检查

| 检查项 | 结果 |
|---|---:|
| 固定Fields | 7/7 |
| 官方Subfields | 127/127 |
| 360天成功日期 | 360/360 |
| 90天成功日期 | 90/90 |
| 缺失日期 | 0 |
| 重复日期键 | 0 |
| 失败后错误写0 | 0 |
| 90天日值合计 vs 独立查询差异 | 127/127均为0 |
| 360天日值合计 vs 独立查询差异 | 127/127均为0 |
| Subfield分组总和 vs 筛选后meta.count | 两个窗口均为0差异 |
| 网络重试 | 10次重试尝试，最终全部成功 |

90天七Field合计为 **639,227** Works；360天合计为 **2,828,498** Works。分组总和与这些独立 `meta.count` 完全相等，因此同一Work没有跨Subfield重复计入。

### 8.1 API显示名漂移

Subfield ID保持一致，但API分组显示名与层级CSV有6处差异：

| Subfield ID | API显示名 | 层级CSV名称（本审计采用） |
|---:|---|---|
| 2704 | Biochemistry (medical) | Biochemistry |
| 2716 | Genetics (clinical) | Genetics |
| 2726 | Microbiology (medical) | Microbiology |
| 2728 | Clinical Neurology | Neurology |
| 2736 | Pharmacology (medical) | Pharmacology |
| 2737 | Physiology (medical) | Physiology |

### 8.2 收录延迟

2026-11-18的TOP方向多数仍为0或极低值，说明当日OpenAlex收录尚未稳定。查询成功和日期完整不等于最新文献已最终收齐。后续必须复查D-2、D-3、D-7、D-14，并保留修订版本；不能把最近几天低计数解释为科研活动下降。

## 9. API使用与后续成本

- 保留为正式审计数据的请求：**362次**（2个窗口＋360个日期）。
- 能力验证及名称漂移诊断：3次成功响应。
- 本阶段成功OpenAlex响应合计：365次；另有10次网络重试尝试，最终无失败日期。
- 结束时额度剩余：7364。
- 正式数据成本约0.0362美元等价额度；含诊断的成功响应约0.0365美元。
- 日常更新建议：D-0新增1次＋D-2/D-3/D-7/D-14复查4次，共5次/日，约1,825次/年；127个Subfield由每次分组请求同时更新。

## 10. 数据库结构建议

### `openalex_subfields`

- `subfield_id`、`subfield_name`、`subfield_name_zh`、`field_id`、`field_name`、`domain_id`、`taxonomy_version`、`updated_at`。

### `subfield_daily_counts`

- `date`、`field_id`、`subfield_id`、`daily_works_count`、`query_status`、`query_as_of`、`mapping_version`、`query_version`、`revision_no`、`is_current`、`supersedes_id`、`created_at`、`updated_at`。
- 唯一约束建议为 `(date, subfield_id, revision_no)`；当前版本另加部分唯一索引 `(date, subfield_id) WHERE is_current=1`。
- 失败请求只写日志，不写0计数。

### `subfield_ranking_snapshots` 与 `subfield_query_logs`

- 排名快照保存 `ranking_date`、`window_days`、`subfield_id`、`rank`、`works_count`、`query_as_of`。
- 查询日志保存日期窗口、HTTP状态、耗时、重试、错误和额度信息。
- TOP 5应从全部127个Subfield的当前日统计动态计算，不只存TOP 5，以便排名变化可追溯。

## 11. 后续图表接入建议（本轮不实施）

1. 两个Tab分别读取90天TOP 5和360天TOP 5；榜单独立计算。
2. 横轴使用完整日期，纵轴直接使用 `daily_works_count`。
3. 图例使用 `中文名 / Official Name (Parent Field)`。
4. Tooltip显示日期、Subfield、Parent Field和当日新增Works。
5. 最新日期显示“收录中”状态；数据不完整时不得把缺失填0。
6. 用户确认前继续保留原五条曲线，不修改首页。

## 12. 第一阶段结论

Subfield分组、两个独立排名周期和每日新增序列均已用真实OpenAlex数据验证。数据层面可以进入测试库迁移和接口开发，但本轮按要求停止，等待人工确认两个TOP 5结果。
