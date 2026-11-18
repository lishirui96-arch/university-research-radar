# V3.1 Works 真实数据质量复核

复核日期：2026-11-17  
复核方式：正式数据库只读查询 + OpenAlex API 只读重查  
数据库：`persistent/data/radar.db`  
复核范围：2026-11-16 Works 批次及相邻日期  

## 1. 结论

2026-11-16 批次没有漏页：OpenAlex 在原始采集时返回 `meta.count=198`，实际入库 198，`sampled_count=198`、`coverage_rate=100%`、`is_truncated=0`。该查询只有一页，页面包含198条记录，`next_cursor` 为 `null`。

使用完全相同的过滤条件和字段列表重新请求，OpenAlex 仍返回198，证明数据库与当前API结果一致。此前近7日72,532篇的评估也能用同一过滤口径复现。

异常来自OpenAlex近期发表日期的收录延迟：2026-11-15为3,050，2026-11-16为198，2026-11-17为28。198是“截至采集时OpenAlex已经收录的完整命中数”，不是该日期最终稳定的全球成果总数。

当前采集程序可以每日运行，但尚不满足“最终完整的每日自动采集”条件。成功日期再次执行会直接返回0请求，无法在OpenAlex后续补录后自动回查同一日期。上线前必须增加可重复发布的重叠回查策略。

## 2. 原始查询条件

端点：`/works`

过滤条件：

```text
from_publication_date:2026-11-16,
to_publication_date:2026-11-16,
institutions.type:education
```

分页条件：

- `cursor=*`
- `per-page=200`

显式字段：

```text
id,doi,title,publication_date,type,language,cited_by_count,
open_access,primary_location,best_oa_location,authorships,
topics,primary_topic,updated_date,created_date
```

统计边界：Work只要至少一个署名机构的OpenAlex类型为 `education` 即纳入。没有国家限制、主题限制、语言限制或预设领域限制。

该查询按 `publication_date` 过滤，不是按OpenAlex收录时间或更新时间过滤。当前账户不能使用 `from_created_date` 和 `from_updated_date`。

## 3. 数据库采集记录

| 项目 | 数据库记录 |
|---|---:|
| OpenAlex `total_count` | 198 |
| `sampled_count` | 198 |
| 实际保存Works | 198 |
| `coverage_rate` | 1.0 |
| `is_truncated` | 0 |
| API请求 | 1 |
| 响应流量 | 1,376,154 bytes |
| Cursor页数 | 1 |
| 最终Cursor | `null` |
| 检查点状态 | `complete=true` |
| Job状态 | `succeeded` |
| Batch状态 | `published` |

因此，本批次完成了OpenAlex当时返回结果的全部Cursor页面。

## 4. API重新核对

三个日期均使用与正式任务相同的机构类型过滤、Cursor起点、每页200条及显式字段列表。

| 发表日期 | 重新请求 `meta.count` | 首页面数量 | 是否存在下一页 |
|---|---:|---:|---|
| 2026-11-15 | 3,050 | 200 | 是 |
| 2026-11-16 | 198 | 198 | 否 |
| 2026-11-17 | 28 | 28 | 否 |

近7日验证：

```text
from_publication_date:2026-11-10,
to_publication_date:2026-11-16,
institutions.type:education
```

重新请求结果为72,532，与此前数据规模评估完全一致。

### 判断

1. 日期过滤没有写错，开始和结束日期均为2026-11-16。
2. `institutions.type:education` 是唯一额外实体过滤条件。
3. 2026-11-16的198条在查询时确实是完整API命中，不是客户端截断。
4. 近日期从3,050降至198再降至28，不符合稳定科研产出的自然波动，属于明显的源数据收录延迟。
5. 不能用D-1一次采集结果作为该日最终全球统计。

## 5. 353个机构的统计口径

353来自以下本地查询口径：

- 只读取本地已经保存的Works；
- 统计近30日窗口中作者署名关联的唯一机构ID；
- 当前近30日本地Works只有本批次2026-11-16的198条；
- 因此353就是这198条Works涉及的唯一机构数。

它不是全球近30日教育机构完整数量，也不是30,711所教育机构中近期有成果的完整数量。

页面当前已正确设置：

- Repository返回 `scope="sample"`；
- 首页显示“样本观察”；
- 代码说明为“本地作品样本内观察到的唯一机构，不代表全球机构总数”。

所以当前页面没有把353标成完整全球统计，但“活跃科研机构”主标签必须始终和“样本观察”口径同时展示。

## 6. Works类型与字段缺失

198条OpenAlex Works的类型分布：

| 类型 | 数量 |
|---|---:|
| article | 98 |
| preprint | 24 |
| dataset | 24 |
| conference-paper | 13 |
| software | 10 |
| other | 10 |
| peer-review | 7 |
| report | 4 |
| supplementary-materials | 2 |
| review | 2 |
| standard | 1 |
| dissertation | 1 |
| data-paper | 1 |
| book | 1 |

来源类型：journal 88、repository 87、缺失16、other 7。

字段缺失：

- DOI缺失：5条。
- 作者署名缺失：0条。
- 机构关联缺失：0条。
- Topics缺失：6条。
- Primary Topic缺失：6条。
- DOI冲突：0条。

这些缺失与当前OpenAlex原始记录一致。需要注意：198是Works数量，不应直接称为198篇同行评审论文。若页面展示“论文数量”，后续指标层必须明确纳入的Work类型。

## 7. 30篇随机抽查

抽样方法：从198条正式库记录中使用固定种子 `20261117` 随机抽取30条，再逐条请求OpenAlex Work详情。核对标题、规范化DOI、作者顺序、作者—机构ID映射、Topic ID与score、Primary Topic及主Topic标志。

总体结果：

| 检查项 | 通过 |
|---|---:|
| API详情请求 | 30/30 |
| 标题 | 30/30 |
| DOI | 30/30 |
| 作者及顺序 | 30/30 |
| 多机构署名映射 | 30/30 |
| Topics及score | 30/30 |
| Primary Topic | 30/30 |
| 全字段同时通过 | 30/30 |

样本中OpenAlex作者ID缺失记录：0。详情请求响应总量：436,119 bytes。

| # | OpenAlex ID | 标题 | DOI | 作者 | 机构关系 | Topics | 结果 |
|---:|---|---|---|---:|---:|---:|---|
| 1 | W7233542418 | Kompass: An Agentic Retrieval-Augmented Generation System for Personalized German University Admissions | 10.5281/zenodo.24265011 | 1 | 1 | 3 | 全部一致 |
| 2 | W7134889574 | Methodological Evaluation and Time-Series Forecasting for Process-Control System Adoption in Tanzania | 10.5281/zenodo.18966513 | 4 | 4 | 3 | 全部一致 |
| 3 | W7233556365 | Ambivalent Post-colonial Experiences in Mochtar Lubis' Jalan Tak Ada Ujung | 10.24071/lsc.vi.790 | 1 | 1 | 3 | 全部一致 |
| 4 | W7233552543 | Hippocampal Glial Signatures of Cognitive Resilience in SuperAgers with Primary Age-Related Tauopathy | 10.21203/rs.3.rs-11578733/v1 | 18 | 18 | 3 | 全部一致 |
| 5 | W7233553530 | La monnaie electronique au sein de la CEMAC a-t-elle ameliore l'inclusion financiere des femmes? | 10.5281/zenodo.24264835 | 1 | 1 | 3 | 全部一致 |
| 6 | W7233566357 | Personalized AI-Supported Sport and Physical Activity for Children with Autism Spectrum Disorder | 10.68700/ijsshp.v1i2.6 | 1 | 1 | 3 | 全部一致 |
| 7 | W7233563129 | Comment on egusphere-2026-4864 | 10.5194/egusphere-2026-4864-ac1 | 1 | 1 | 0 | 全部一致 |
| 8 | W7233619603 | Blade orientation and contact formulation in distal shoe guidance: source code and numerical data | 10.5281/zenodo.24261985 | 1 | 1 | 3 | 全部一致 |
| 9 | W7233566479 | Gouvernance collaborative et transformations societales durables a l'ere de l'Intelligence Artificielle | 10.5281/zenodo.24265457 | 2 | 2 | 3 | 全部一致 |
| 10 | W7233582848 | Foggy days are becoming more common across southern Australia: new study | 10.64628/aa.ey7jd9kqa | 2 | 2 | 3 | 全部一致 |
| 11 | W7203604471 | Suitable organic fertilizer substitution improves grain yield and water use efficiency of rainfed maize | 10.1016/j.agwat.2026.110937 | 8 | 8 | 3 | 全部一致 |
| 12 | W4411103444 | Encapsulating an iron complex within a heme and anthraquinone codecorated capsule | 10.1038/s41467-026-79524-3 | 7 | 7 | 3 | 全部一致 |
| 13 | W7233566592 | High normal arterial pressure in young adults (Russian title) | 10.5281/zenodo.24260427 | 1 | 1 | 3 | 全部一致 |
| 14 | W7233562548 | Diabetes distress, social participation and social inclusion in Type 1 diabetes | 10.1108/mhsi-10-2026-0419 | 3 | 3 | 3 | 全部一致 |
| 15 | W7233561603 | Did more fatal infections or changing death certification drive the rise in sepsis mortality in Korea? | 10.5281/zenodo.24266126 | 1 | 1 | 3 | 全部一致 |
| 16 | W7233584360 | TIPE2 suppresses adipogenesis via METTL14-mediated m6A methylation | 10.21203/rs.3.rs-11199357/v1 | 11 | 11 | 3 | 全部一致 |
| 17 | W7233612233 | Theoretical, practical and normative dimensions of value concepts and valuation methods in B2B marketing | 10.1108/jbim-07-2025-0725 | 1 | 1 | 3 | 全部一致 |
| 18 | W7233540003 | Transformation des pratiques et metiers a l'ere de l'IA | 10.5281/zenodo.24265086 | 1 | 1 | 3 | 全部一致 |
| 19 | W7233587913 | Late Ottoman Gaza: An Eastern Mediterranean Hub in Transformation | 10.1163/15700607-20263029 | 1 | 1 | 3 | 全部一致 |
| 20 | W7233573046 | Can Indonesian researchers ever win a Nobel? | 10.64628/aan.g4t4er4d4 | 1 | 1 | 3 | 全部一致 |
| 21 | W7233583367 | Acceptability and early outcomes of an automated telemonitored smartphone rehabilitation programme | 10.47102/annals-acadmedsg.2026492 | 7 | 7 | 3 | 全部一致 |
| 22 | W7233548042 | Canon Dynamics in the Princeton Prosody Archive, 1559-1929 | 10.22148/jca.1429 | 3 | 4 | 3 | 全部一致 |
| 23 | W7233540688 | Electronic Evidence, Authentication Challenges, and the Qarinah Doctrine | 10.32332/a2esyq87 | 3 | 3 | 3 | 全部一致 |
| 24 | W7233563824 | Operacionalizacion metodologica del impacto de la produccion cientifica | 10.5281/zenodo.24264571 | 4 | 4 | 3 | 全部一致 |
| 25 | W7233607033 | Physical Fidelity of Learned Nonlinear Vehicle Dynamics | 10.21203/rs.3.rs-11443334/v1 | 2 | 2 | 3 | 全部一致 |
| 26 | W7233608476 | Saber Docente no combate as Fake News | 10.5212/olharprofr.v.29.26310.051 | 3 | 3 | 3 | 全部一致 |
| 27 | W7233591250 | Determinants and Barriers to Hepatitis B Vaccination Uptake | 10.21203/rs.3.rs-11268912/v1 | 4 | 5 | 3 | 全部一致 |
| 28 | W7233596542 | Structural Complementarity, Bottlenecks, and Total Factor Productivity in Mexico | 10.21203/rs.3.rs-11706417/v1 | 2 | 2 | 3 | 全部一致 |
| 29 | W7233591320 | Capstone Sponsor Onboarding Ontology, version 0.2.1 | 10.5281/zenodo.24264613 | 1 | 1 | 3 | 全部一致 |
| 30 | W7233541214 | Recognizing and Responding to Medical Neglect: Clinical Report | 10.1542/peds.2026-079368 | 3 | 6 | 3 | 全部一致 |

## 8. 数据缺失与错误判断

### 未发现的采集错误

- 未发现Cursor漏页。
- 未发现数据库记录数与API `meta.count` 不一致。
- 未发现抽样记录标题、DOI、作者、机构或Topic关系写错。
- 未发现多机构署名丢失。
- 未发现DOI唯一约束冲突。

### 已确认的数据限制

1. OpenAlex近期发表日期有明显收录延迟。
2. 当前198条中包含数据集、软件、预印本、报告等，不全是传统论文。
3. 5条无DOI，6条无Topics和Primary Topic；与源数据一致。
4. 353仅是当前本地Works样本中的机构数。
5. 固定30篇抽样用于验证写入正确性，不能证明其余168篇绝对无误。

## 9. 每日自动采集条件

当前判断：**采集器技术链路通过，但尚不满足最终完整的生产级每日采集条件。**

已满足：

- API认证、Cursor分页、显式字段、请求审计正常。
- 数据写入、作者多机构关系和Topic关系正确。
- 任务互斥、检查点、重试和失败不发布机制可用。
- 同一批次重复执行不会重复写入。

必须补齐：

1. 每日D-1采集后，自动回查D-2、D-3、D-7、D-14或滚动窗口。
2. 同一发表日期必须允许创建新的采集批次，而不是成功后永久返回0请求。
3. 每次回查重新记录 `total_count`，对比上次计数并upsert新增或更新的Works。
4. 日期计数连续多个回查周期稳定后，才能标记为“稳定完整”；此前只能标记“OpenAlex当前完整计数/仍可能补录”。
5. 页面论文指标需要定义纳入的Work类型，至少将article、conference-paper、preprint、dataset和software分开。
6. 353机构继续保留“样本观察”标签，直到覆盖相应完整时间窗口。

在这些条件完成前，Windows每日任务可以作为试运行采集，但不能把D-1结果发布为最终全球日统计。

