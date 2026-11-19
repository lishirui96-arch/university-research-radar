# V1.3.4 全球 Topic TOP 10 阶段A只读审计报告

> as_of_date：2026-11-18；任务时区：Asia/Singapore；OpenAlex日期过滤使用明确ISO自然日边界。未修改首页、正式数据库、五领域映射或历史曲线。

## 1. 执行结论

- 官方目录完整性为 **4 Domains、26 Fields、252 Subfields、4,516 Topics**，Topic ID无重复。
- OpenAlex支持 `group_by=primary_topic.id` 和cursor分页；单页上限200。普通 `page=2` 不支持。
- 90天完整分页返回4,284个非零Topic，另外232个官方Topic在完整游标结束后确认为0。
- 360天完整分页返回4,376个非零Topic，另外140个官方Topic确认为0。
- 两个完整排名均包含4,516行，按Works降序、同量按Topic ID数字顺序排序。
- 两个TOP 10并集为12个Topic；360个日期全部成功，最后90天直接截取同一日序列。
- 12个入选Topic的每日合计与独立90/360天排名总量全部一致，差异为0。

## 2. 统计口径与窗口

| 项目 | 口径 |
|---|---|
| 实体 | OpenAlex Works |
| 地理 | 全球 |
| Corpus | `primary_location.source.is_core:true` |
| 日期 | `publication_date` |
| 分类 | `primary_topic.id` |
| 每篇Work归属 | 最多一个primary Topic |
| 90天 | 2026-08-21～2026-11-18，闭区间 |
| 360天 | 2025-11-24～2026-11-18，闭区间 |
| 排序 | `period_works_count DESC, numeric(topic_id) ASC` |
| 日值 | 当天新增唯一Works；不是累计值或30天滚动值 |

## 3. 现有架构兼容性检查

- 数据库：`migrations.py`采用增量版本迁移；当前趋势表保留修订号、current标志、查询日志和批次记录，可复用其事务与版本模式。
- 采集器：`collector/trend_analytics.py`已实现API Key、429/5xx/网络重试、指数退避、失败不写0、断点续跑，但当前只接受五个固定自定义类别和30天窗口，阶段B应新增独立Topic采集器而非改写V1逻辑。
- Repository：`dashboard_repository.get_global_research_trend()`只读取五领域30天滚动快照，不能复用为Topic日新增接口。
- 首页：`app_pages/global_dashboard.py`使用Altair、缓存和repository层，后续可以最小范围替换趋势模块的数据绑定，无需引入新图表库。
- 测试：现有迁移幂等、repository完整性、页面切换和缺失值不补0测试可扩展为Topic版本。

## 4. API分组分页验证

| 验证项 | 实测结果 |
|---|---|
| `group_by=primary_topic.id` | 支持 |
| 最大 `per-page` | 200；201返回HTTP 400 |
| cursor | 支持，`cursor=*`返回`next_cursor` |
| 普通page分页 | 不支持，`page=2`返回HTTP 400 |
| cursor顺序 | Topic ID顺序，不是Works数量顺序 |
| 本地排序 | 必须，两个完整结果均已重排 |
| 90天分页 | 22页：21×200＋84＝4,284个非零Topic |
| 360天分页 | 22页：21×200＋176＝4,376个非零Topic |
| 分页重复ID | 0 |
| 未知ID | 0 |
| 真实0确认 | 仅在cursor结束且与4,516官方目录做差集后填0 |

Cursor API的显示名称与层级CSV有51/52处差异，但Topic ID稳定。本审计统一采用用户指定层级CSV中的名称和层级，显示名漂移不影响计数。

## 5. 分类覆盖率

| 窗口 | 全部core Works | 有primary Topic | 未分类Works | 覆盖率 |
|---|---:|---:|---:|---:|
| 90天 | 953,790 | 935,792 | 17,998 | 98.11% |
| 360天 | 4,218,075 | 4,128,891 | 89,184 | 97.89% |

未分类Works没有可用primary Topic，不会被强制分配。已分类Works只进入一个Topic，因此Topic分组之间没有重复计数。

## 6. 最近90天 TOP 10

| Rank | Topic ID | 中文名 / Official Topic Name | Field / Subfield | 90天Works |
|---:|---|---|---|---:|
| 1 | `T11636` | 医疗与教育中的人工智能应用 / Artificial Intelligence in Healthcare and Education | Medicine / Health Informatics | 4,460 |
| 2 | `T10030` | 能源转换电催化剂 / Electrocatalysts for Energy Conversion | Energy / Renewable Energy, Sustainability and the Environment | 3,641 |
| 3 | `T10078` | 先进光催化技术 / Advanced Photocatalysis Techniques | Energy / Renewable Energy, Sustainability and the Environment | 3,578 |
| 4 | `T10158` | 癌症免疫治疗与生物标志物 / Cancer Immunotherapy and Biomarkers | Medicine / Oncology | 3,245 |
| 5 | `T10066` | 肠道微生物群与健康 / Gut microbiota and health | Biochemistry, Genetics and Molecular Biology / Molecular Biology | 2,615 |
| 6 | `T10009` | 痴呆与认知障碍研究 / Dementia and Cognitive Impairment Research | Medicine / Psychiatry and Mental health | 2,578 |
| 7 | `T10036` | 先进神经网络应用 / Advanced Neural Network Applications | Computer Science / Computer Vision and Pattern Recognition | 2,485 |
| 8 | `T10172` | 心脏瓣膜疾病与治疗 / Cardiac Valve Diseases and Treatments | Medicine / Cardiology and Cardiovascular Medicine | 2,458 |
| 9 | `T10018` | 电池材料进展 / Advancements in Battery Materials | Engineering / Electrical and Electronic Engineering | 2,288 |
| 10 | `T10211` | 计算药物发现方法 / Computational Drug Discovery Methods | Computer Science / Computational Theory and Mathematics | 2,266 |

## 7. 最近360天 TOP 10

| Rank | Topic ID | 中文名 / Official Topic Name | Field / Subfield | 360天Works |
|---:|---|---|---|---:|
| 1 | `T11636` | 医疗与教育中的人工智能应用 / Artificial Intelligence in Healthcare and Education | Medicine / Health Informatics | 17,217 |
| 2 | `T10030` | 能源转换电催化剂 / Electrocatalysts for Energy Conversion | Energy / Renewable Energy, Sustainability and the Environment | 15,263 |
| 3 | `T10078` | 先进光催化技术 / Advanced Photocatalysis Techniques | Energy / Renewable Energy, Sustainability and the Environment | 15,220 |
| 4 | `T10009` | 痴呆与认知障碍研究 / Dementia and Cognitive Impairment Research | Medicine / Psychiatry and Mental health | 14,913 |
| 5 | `T10158` | 癌症免疫治疗与生物标志物 / Cancer Immunotherapy and Biomarkers | Medicine / Oncology | 12,956 |
| 6 | `T10036` | 先进神经网络应用 / Advanced Neural Network Applications | Computer Science / Computer Vision and Pattern Recognition | 12,714 |
| 7 | `T10066` | 肠道微生物群与健康 / Gut microbiota and health | Biochemistry, Genetics and Molecular Biology / Molecular Biology | 11,440 |
| 8 | `T10134` | 炎症性肠病 / Inflammatory Bowel Disease | Biochemistry, Genetics and Molecular Biology / Genetics | 10,387 |
| 9 | `T10018` | 电池材料进展 / Advancements in Battery Materials | Engineering / Electrical and Electronic Engineering | 10,026 |
| 10 | `T10616` | 智慧农业与人工智能 / Smart Agriculture and AI | Agricultural and Biological Sciences / Plant Science | 9,856 |

## 8. 两榜单Topic ID并集

| Topic ID | 中文名 / Official Name | 90天排名 | 360天排名 |
|---|---|---:|---:|
| `T10009` | 痴呆与认知障碍研究 / Dementia and Cognitive Impairment Research | 6 | 4 |
| `T10018` | 电池材料进展 / Advancements in Battery Materials | 9 | 9 |
| `T10030` | 能源转换电催化剂 / Electrocatalysts for Energy Conversion | 2 | 2 |
| `T10036` | 先进神经网络应用 / Advanced Neural Network Applications | 7 | 6 |
| `T10066` | 肠道微生物群与健康 / Gut microbiota and health | 5 | 7 |
| `T10078` | 先进光催化技术 / Advanced Photocatalysis Techniques | 3 | 3 |
| `T10134` | 炎症性肠病 / Inflammatory Bowel Disease | 未入榜 | 8 |
| `T10158` | 癌症免疫治疗与生物标志物 / Cancer Immunotherapy and Biomarkers | 4 | 5 |
| `T10172` | 心脏瓣膜疾病与治疗 / Cardiac Valve Diseases and Treatments | 8 | 未入榜 |
| `T10211` | 计算药物发现方法 / Computational Drug Discovery Methods | 10 | 未入榜 |
| `T10616` | 智慧农业与人工智能 / Smart Agriculture and AI | 未入榜 | 10 |
| `T11636` | 医疗与教育中的人工智能应用 / Artificial Intelligence in Healthcare and Education | 1 | 1 |

## 9. 每日真实新增数据与一致性

- `TOPIC_TOP10_DAILY_90D.csv`：90×10＝900行。
- `TOPIC_TOP10_DAILY_360D.csv`：360×10＝3,600行。
- 两文件分别使用各自周期的TOP 10；不固定使用360天榜单。
- 360天原始查询对12个并集Topic一次分组，90天取最后90个自然日。
- 每个日期、Topic组合唯一；失败请求不会写0。
- 12个Topic的90天与360天日值合计均与完整排名中的独立周期总量一致。

2026-11-18的12个Topic当前全部为0，属于当日收录尚未稳定，不代表科研活动停止。阶段B必须展示“收录中”并执行D-2、D-3、D-7、D-14修订。

## 10. 数据库与历史保存建议（阶段B方案，不执行）

### `openalex_topics`

- `topic_id`主键、`topic_name`、`topic_name_zh`、`subfield_id/name`、`field_id/name`、`domain_id/name`、`taxonomy_version`、`updated_at`。

### `topic_daily_counts`

- `date`、`topic_id`、`daily_works_count`、`query_as_of`、`query_status`、`revision_no`、`is_current`、`supersedes_id`、`query_version`、`taxonomy_version`、时间戳。
- 唯一键 `(date, topic_id, revision_no)`；部分唯一索引 `(date, topic_id) WHERE is_current=1`。
- 失败只写查询日志，绝不写0。修订先保留旧版本，再切换current。

### `topic_ranking_snapshots`

- `ranking_date`、`period_days`、`topic_id`、`rank`、`period_works_count`、`window_start/end`、`query_as_of`、`calculation_version`。
- 保存90和360天全部4,516行，不只保存TOP 10。完整快照成功后再原子切换前端版本。

### 查询日志与批次

- 增加`topic_query_logs`和`topic_update_runs`，记录cursor、页数、返回Topic数、额度、重试、失败与完整性状态。
- 原五领域表和1,825条快照全部保留，Topic表独立新增。

## 11. `updated_date` / `created_date`增量评估

- `created_date`可发现新进入OpenAlex的Works，包括较早publication_date的迟到收录，但不能覆盖已有记录的Topic或日期修正。
- `updated_date`可发现记录变更，但若只保存聚合计数，无法知道旧Topic/旧日期需要减1以及新Topic/新日期需要加1。
- 因此，仅靠updated/created增量不能安全维护聚合表；若要使用，必须保存Work级旧状态并处理移动、删除和重复事件。
- V1建议采用D-2/D-3/D-7/D-14定点复查＋定期更宽历史重算；Work级增量缓存可作为后续优化，不应直接替代修订查询。

## 12. 阶段B接入边界

阶段B应新增独立Topic采集器、迁移和repository接口；首页继续使用Altair，只替换趋势区域的数据来源、90/360切换、图例与排名表。前端不得调用OpenAlex。只有当排名快照和入选Topic日序列均完整时才发布新版本，否则继续展示上一次完整快照。

## 13. 阶段A结论

全量Topic分页、两个独立排名、TOP 10并集和360天每日新增序列均已用真实OpenAlex数据验证。阶段A到此停止，等待人工确认TOP 10结果后再进入数据库和首页开发。
