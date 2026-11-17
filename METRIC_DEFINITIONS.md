# 全球科研热点总览：指标定义

版本：规划稿 1.0
适用范围：全球科研热点总览及其下钻页面

## 1. 统一统计约定

### 1.1 时间

- `as_of_date`：最近一个成功、完整发布的快照日期；
- 近7/30/90天：含 `as_of_date` 的滚动自然日窗口；
- 上一周期：与当前窗口等长且紧邻、无重叠的窗口；
- 近12个月/3年：按自然月展示，末月可以是不完整月并标记；
- 作品时间默认使用 `publication_date`，不以采集时间替代；
- `first_seen_at` 用于衡量新入库或迟到回填，不能冒充发表日期；
- OpenAlex 回填会改变历史窗口，故每次计数同时保存 `observed_at` 和 `source_updated_at`（可用时）。

### 1.2 地域

- 全球：不按机构国家过滤；
- 中国：作品至少一个 authorship 关联的机构 `country_code='CN'`；
- 指定国家：同理按至少一个机构署名判定；
- 跨国合作作品可同时计入多个国家，但全球去重总量只计一次；
- 无机构信息的作品可进入全球论文计数，但不进入国家、高校或团队统计；
- “高校”要求机构主数据类型为教育机构，并保留 OpenAlex ID、ROR 和别名证据。

### 1.3 去重单位

优先统计单位为 `work_family_id`，将预印本、会议版、正式发表版等同一成果版本归并。若作品家族尚未实现：

- 可报告 `COUNT(DISTINCT openalex_work_id)`，名称必须为“OpenAlex 记录数”；
- DOI 仅作为归并证据之一，不能把 DOI 为空视为相同作品；
- 不得将原始记录数命名为“去重论文数量”；
- 原始 OpenAlex ID 必须全部保留在家族成员关系中。

### 1.4 数据范围

| `count_scope` | 含义 | 可用措辞 |
|---|---|---|
| `complete` | 对定义的总体完成计数 | “完整计数”“该口径总量” |
| `sample` | 仅采集代表样本 | “样本中”“观察到” |
| `verified` | 仅人工/多源核实实体 | “已核实” |
| `unavailable` | 无法可靠计算 | `--` 与原因 |

`total_count` 为 OpenAlex 对指定查询和窗口返回的完整命中计数；`sampled_count` 为本地实际持久化、通过去重和过滤的作品数；`coverage_rate = sampled_count / total_count`。分母为零时，覆盖率为缺失而不是 0%。

### 1.5 缺失与排名门槛

- 缺失值保存为 SQL `NULL`，不得填充 0 或中性分；
- 只要增长所需任一期缺失或口径不可比，增长率、指数、加速度均为缺失；
- `score_coverage` 表示可计算评分权重占计划总权重的比例；
- `data_confidence` 由覆盖、样本量、时间可比性、来源完整性和实体解析质量构成，公式必须版本化；
- 低于版本化最低 `score_coverage` 或 `data_confidence` 的对象不得进入正式榜单，只进入“证据不足”；
- 不允许对缺失分项重新归一后反向提高热度；
- 不同领域的热度分在完成领域校准前不可直接比较。全学科榜单优先使用领域内百分位，再使用明确版本的跨领域校准分。

## 2. 顶部核心指标

### 2.1 近30天新增论文

**展示名称**：近30天新增论文（按发表日期）

```text
current = COUNT(DISTINCT work_family_id)
          WHERE publication_date BETWEEN window_start AND window_end

previous = 同一地域、同一来源、同一去重版本下前30天计数

period_change = (current - previous) / previous
```

- `previous > 0` 才计算变化率；
- `previous = 0 AND current > 0` 显示“新出现”，变化率为缺失；
- 世界与中国使用同一窗口，但中国按机构署名过滤；
- 同时存储原始 OpenAlex 记录数、作品家族数和迟到回填数；
- 来源：OpenAlex Works 完整计数/本地作品实体；
- 当前没有作品家族时降级为“OpenAlex 记录数”或缺失。

### 2.2 活跃科研机构

```text
active_institutions = COUNT(DISTINCT institution_id)
WHERE exists(qualifying work authorship in window)

active_universities = 上述机构中 institution_type = education
active_cn_universities = 上述高校中 country_code = CN
```

- 必须展开全部 authorship-institution 关系，不得只取通讯作者或第一机构；
- 只有样本时指标名为“样本内活跃机构”；
- OpenAlex `group_by` 最多返回 200 组，不能仅凭它宣称全球活跃机构总数；
- 来源：`work_authorship_institutions`、`institutions` 和对应采集审计。

### 2.3 新兴研究主题数量

```text
emerging_topic_count = COUNT(DISTINCT topic_id)
WHERE category = 'emerging'
  AND eligible_for_ranking = 1
  AND snapshot_batch_id = selected_batch
```

默认候选规则（阈值作为算法配置保存，不硬编码在页面）：

- 至少两个可比较历史周期；
- 当前完整计数达到领域规模门槛；
- 历史基线为低但非“历史缺失”；
- 调整后增长、近期加速度或连续出现达到门槛；
- `data_confidence` 和 `score_coverage` 达标；
- 数据库覆盖变化未解释主要增长。

“中国重点新兴主题”使用中国计数独立判断，不从全球名单按高校名称筛选。

### 2.4 活跃研究团队与人员

```text
verified_active_groups = COUNT(DISTINCT group_id)
WHERE status='verified' AND has qualifying evidence/work in window

candidate_active_groups = COUNT(DISTINCT group_id)
WHERE status='candidate' AND has qualifying evidence/work in window

active_authors = COUNT(DISTINCT author_id)
WHERE has qualifying authorship in window
```

- 已验证和候选不得相加后统称“已识别团队”；
- OpenAlex 共著只能生成候选；
- 作者多机构署名完整保留；地域作者计数要求该作品署名中至少一个目标地区机构；
- 样本来源时显示“样本内活跃作者”。

## 3. 趋势指标

### 3.1 论文实际数量

每个时间桶保存：`total_count`、`sampled_count`、`coverage_rate`、`count_scope`。图表不得用 sampled_count 替代 total_count，也不得把两者相加。

### 3.2 期初为100的增长指数

```text
index_t = 100 * total_count_t / total_count_base
```

- 仅在 `total_count_base > 0` 且各期查询、分类和覆盖口径可比时计算；
- 使用样本时可计算“样本指数”，但必须单独命名且不与完整指数比较；
- 基期为零、缺失或算法版本跨越不可桥接时返回缺失。

### 3.3 增长率

```text
raw_growth = (current_count - baseline_count) / baseline_count

adjusted_growth = raw_growth * baseline_count / (baseline_count + shrinkage_prior)
```

- `baseline_count=0` 时 raw/adjusted growth 均缺失，并使用“新出现”判定；
- `shrinkage_prior` 按领域、窗口和算法版本保存；
- 小样本不得仅凭百分比进入 Fast Growing。

### 3.4 近期加速度

```text
recent_rate = (count_t - count_t-1) / duration
prior_rate  = (count_t-1 - count_t-2) / duration
acceleration = recent_rate - prior_rate
```

可选标准化版本使用领域内稳健尺度。任一期缺失、基线过小或覆盖不可比时为缺失。零基线不得通过极小伪分母直接获得满分。

### 3.5 历史趋势标签

- Emerging：低但充分观测的历史基线 + 当前达到最小规模 + 连续确认；
- Fast Growing：已有基线、调整后增长和加速度达标；
- Trending：至少三个可比周期持续位于领域内高分位；
- Cooling：持续负增长且数据可比；
- Evidence insufficient：历史、覆盖或置信度不足。

## 4. 主题榜单指标

### 4.1 近期论文数量

按主题映射版本，对窗口内作品家族去重计数。一个作品可属于多个主题，因此主题计数不可跨主题求和为全球总量。

### 4.2 主要高校

按主题窗口内完整的高校署名作品数排序。若只持久化代表样本，显示“样本内主要高校”。并列规则、分数计数/整数计数和国际合著口径写入算法版本。

### 4.3 代表性论文

代表样本与统计样本分离。候选池先保证时间、国家、高校和来源类型分层，再按相关度、质量和证据完整度排序。引用量只能作为特征之一，避免只保留高引用旧作。

### 4.4 Cross-disciplinary 指标

对每个作品家族取 OpenAlex Topic 的 Field/Domain 映射：

```text
cross_domain_share = 跨两个及以上 Field 的作品家族数 / 主题作品家族数
field_entropy = -SUM(p_field * ln(p_field)) / ln(number_of_eligible_fields)
cross_growth = current_cross_domain_share - baseline_cross_domain_share
```

只有主题映射覆盖达标且 Field 数至少为 2 时计算。分类版本变化必须触发不可比或桥接重算。

### 4.5 主题综合热度

热度由规模、调整后增长、加速度、机构扩散、作者/团队广度、质量等版本化分项构成：

```text
heat_score = SUM(weight_i * component_i) - missingness_penalty - coverage_penalty
```

- 缺失分项不重新归一为更高总分；
- 保存每个分项、权重、惩罚、`score_coverage` 和算法版本；
- 全学科比较使用领域内百分位或已验证的校准模型；
- 当前 V1.1 算法修复前，全球首页不得使用该分数正式排序。

## 5. 高校科研力量指标

### 5.1 近期论文数量

高校在窗口内所有署名作品家族的整数计数。一篇多校合作论文对每所参与高校各计 1，但全球总量只计 1。

### 5.2 研究主题数量

达到最小作品数或最小占比的不同 Topic 数。阈值、Topic 层级和分类版本随快照保存；不能把仅出现 1 篇的噪声主题默认计入。

### 5.3 活跃作者数量

窗口内以该高校署名的唯一 OpenAlex Author ID 数。作者在多个高校署名时可进入多个高校，但高校间不可简单求和为全球作者数。

### 5.4 历史增长趋势

使用高校在相同领域、相同地域口径下的完整作品计数；小样本收缩、覆盖可比性和缺失规则与主题增长一致。

### 5.5 研究方向分布

```text
topic_share_i = institution_topic_work_count_i /
                SUM(institution_topic_work_count across displayed topics)
```

因一篇作品可映射多个 Topic，默认采用主 Topic 或分数归一后的分数计数，二者不能混用。图例必须标明口径。

### 5.6 排名资格

- `complete_rank`：所有候选高校均在统一完整计数流程中评估；
- `complete_count_topk`：榜单内计数完整，但候选集合只保证 Top-K 截断覆盖；
- `sample_rank`：仅本地样本；
- `unavailable`：证据不足。

页面标题和导出文件必须包含 `ranking_scope`。

## 6. 科研动态与成果

- 发表时间：作品正式 `publication_date`；
- 技术突破摘要：来源原文摘要或机器归纳，必须保存 `summary_method`、模型/规则版本和证据链接；
- DOI：规范化后保存，仍保留原值；
- 证据状态：candidate、verified、rejected；
- 高校官网新闻与 OpenAlex 论文记录作为两个独立 evidence，不互相冒充。

## 7. 预警指标

所有预警保存：`alert_type`、对象、观察窗口、基线窗口、触发公式、阈值、观察值、置信度、算法版本、`snapshot_batch_id`、证据 ID、状态和失效时间。

### 7.1 快速升温

调整后增长、加速度和当前最小规模同时达标，并连续两个发布批次确认。覆盖变化异常时暂停触发。

### 7.2 多学科交叉增强

`cross_domain_share` 或 `field_entropy` 相对基线显著上升，且跨领域作品绝对数达到门槛。

### 7.3 高校集中布局

```text
top_n_share = SUM(top N institution work counts) / total topic work count
```

只有机构分布完整或覆盖可界定时计算。使用 HHI 时同步保存机构全集定义。

### 7.4 新高校进入

高校过去充分观察期内低于进入阈值，当前连续达到最小作品量。机构别名合并或 OpenAlex ID 变更不能触发“新进入”。

### 7.5 重要科研成果

论文相关度、来源质量和新颖性候选规则只能生成 candidate；使用“重大突破”等强表述必须有高校官网、出版商或人工核验等额外证据。

## 8. 数据置信度建议构成

```text
data_confidence =
    0.30 * coverage_component
  + 0.20 * sample_size_component
  + 0.20 * temporal_comparability_component
  + 0.15 * entity_resolution_component
  + 0.15 * source_evidence_component
```

各分项本身缺失时总置信度也应缺失，或按明确惩罚规则计算；不可重新归一掩盖缺项。权重只是实施起点，必须用边界测试和真实回测校准后版本化发布。
