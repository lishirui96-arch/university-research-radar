# University Research Radar V1.1 交付说明

## 修改文件

- `radar.py`：分段代表性采样、覆盖口径、OpenAlex 实体关系、小样本和零基线算法。
- `migrations.py`：schema v2 增量表结构。
- `storage.py`：版本迁移、实体去重、作者多机构关系、候选课题组证据和快照入库。
- `streamlit_app.py`：覆盖率展示、检索审计字段和样本口径提示。
- `tests/test_v11.py`：V1.1 回归测试。
- `README.md`、`DEPLOYMENT_LAN.md`：版本、迁移和回滚说明。

## 新增表结构

| 表 | 用途 | 关键约束 |
|---|---|---|
| `schema_migrations` | 已执行迁移记录 | `version` 主键 |
| `works` | OpenAlex 论文主实体 | OpenAlex Work ID 主键，DOI 唯一 |
| `authors` | 作者主实体 | OpenAlex Author ID 主键 |
| `institutions` | 机构主实体 | OpenAlex Institution ID 主键 |
| `topics` | 受控主题与 OpenAlex 主题 | `topic_key` 主键，OpenAlex Topic ID 唯一 |
| `work_authorships` | 论文—作者关系 | 论文与作者唯一 |
| `work_authorship_institutions` | 单次署名的多机构关系 | 署名与机构联合主键 |
| `work_topics` | 论文—主题关系 | 论文与主题联合主键 |
| `research_groups` | 课题组或候选合作簇 | 状态限定为 candidate/verified/rejected |
| `research_group_evidence` | 课题组归属证据 | 证据主键，独立保存置信度与核验状态 |
| `topic_snapshots` | 主题日快照 | 运行、主题、地区唯一；保存算法版本 |
| `institution_snapshots` | 机构日快照 | 运行、机构唯一 |
| `author_snapshots` | 作者日快照 | 运行、作者唯一 |

所有科研实体和关系保留数据来源、首次创建时间与最近更新时间。OpenAlex 论文、作者、机构和主题均保存原始 ID。作者与机构通过署名关系的桥接表建模，不是一对一关系。

## 算法调整

- 算法版本：`1.1.0`。
- `group_breadth_score` 只使用高或中高置信度归属，并且只在样本完整时计分；OpenAlex 自动推断仍为候选，不冒充已验证课题组。
- 基线为零时不计算无限增长率，使用 `from_zero` 状态；达到最低样本量且历史口径完整时标记为 `genuine_new`。
- 小样本使用先验计数收缩后的增长值参与评分，原始增长仍单独保留。
- 历史窗口缺失时，增长、动量和加速度保持缺失，不用中性分替代。
- 保存 `score_coverage`、`data_confidence`、`growth_status`、`newness_status` 和覆盖可比性。
- 趋势解释明确为 OpenAlex 记录量变化；没有连续回填监测时，不把它断言为纯论文增长。

## 采集调整

- `total_count`：OpenAlex 完整命中计数。
- `sampled_count`：实际采集并去重的论文数。
- `coverage_rate`：`sampled_count / total_count`。
- 超过样本上限时，按最多四个时间段分层，并在各段选择高引用代表成果。
- 保存样本截断、分段范围、采样策略、检索式、过滤器和数据源。
- 高校、作者和课题组统计明确限定为采集样本；样本截断时高校数量不表示主题真实高校总数。

## 数据迁移

应用启动时读取 `schema_metadata.schema_version`：

1. v1 数据库仅新增 v2 表、索引和迁移记录；
2. `scan_runs`、`scan_topic_metrics`、`scan_query_log` 不删除、不改写；
3. 迁移在 `BEGIN IMMEDIATE` 事务内执行；
4. 重复初始化不重复迁移；
5. 数据库版本高于程序支持版本时停止启动，不自动降级。

生产升级必须先执行 `scripts/backup_database.py`。现有更新脚本已经在拉取代码前执行备份。

## 回滚方案

1. 停止网站容器。
2. 保留当前 v2 数据库和 `-wal`、`-shm` 文件的副本。
3. 恢复升级前由更新脚本生成的 v1 备份。
4. 将代码切回 V1.0 提交 `4b4c681`。
5. 重建并启动容器，检查健康状态和旧扫描记录。

不要直接在运行中的数据库上删除 V1.1 表或手工修改版本号。若 V1.1 已积累新实体和快照，回滚到 v1 备份会丢弃升级后的新增数据，应先完整保存 v2 数据库。

## 测试结果

- 10 项 `unittest`：全部通过。
- 原数据库副本 v1→v2：旧表行数保持一致。
- 迁移连续执行两次：结果一致。
- SQLite `PRAGMA integrity_check`：`ok`。
- V2 在线备份打开与完整性检查：`ok`。
- Streamlit AppTest：0 异常、0 错误、0 警告。
- Python 语法检查：通过。

## 下一阶段建议

1. 增加同一历史出版窗口的重复计数任务，用于量化 OpenAlex 回填变化。
2. 接入 Crossref 做 DOI、出版状态和版本关系核验。
3. 建立官方课题组页面人工核验工作台，只有官方证据通过后才将状态改为 `verified`。
4. 增加按周快照对比页面和算法版本切换审计。
5. 为 DOI 冲突和预印本—正式发表版本增加成果家族表。
