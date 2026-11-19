# 全球科研热点趋势 V1.1 实施报告

生成日期：2026-11-18  
实现范围：首页“近期科研热点趋势（全球）”的数据统计引擎，不含 UI 改动。

## 结论

V1.1 数据引擎已经完成。它按“领域 + 快照日期”直接向 OpenAlex 查询 `[t-29, t]` 的 `meta.count`，只使用映射配置中 `approved` 的 `primary_topic`，并固定加入 `primary_location.source.is_core:true`。首轮 30 日测试回填为 150/150 成功，数据读取接口可向首页提供完整的 30 日数据。

本轮没有修改首页、其他页面、V3/V3.2 采集逻辑，也没有注册定时任务、提交 Git 或推送 GitHub。回填仅在测试数据库副本中执行。

## 实现内容

- `collector/trend_analytics.py`
  - 读取并校验 `config/trend_topic_mapping.json` 的统计契约。
  - 仅加载五个领域的 `approved` Topic，并拒绝空领域或跨领域重复 Topic。
  - 为每个快照日期计算含首尾两端的 30 个自然日窗口。
  - 组合 `primary_topic.id:T1|T2...` OR 过滤，不下载 Works 明细。
  - 从 `meta.count` 读取结果；429、5xx、网络超时采用最多 4 次尝试和指数退避。
  - 单并发执行，支持 `--batch-size` 暂停、相同 `--run-id` 恢复。
  - 失败结果写查询日志且 `works_count=NULL`；批次不完整时不发布快照。
- `migrations.py` / `storage.py`
  - Schema 升级至 v3，新增三个趋势表，迁移可重复执行且不重建数据库。
- `dashboard_repository.py`
  - 新增 `get_global_research_trend(path, days=30)`。
  - 支持 30、90、365 日读取，返回日期、五领域数值、逐日状态、最新更新时间和完整性信息。
  - 只读取成功批次中的当前有效快照。
- `tests/test_trend_analytics.py`
  - 覆盖迁移幂等、固定过滤口径、失败隔离、暂停恢复、重复运行、修订历史和读取完整性。

## 正式 Topic 集合

| 领域 | approved OpenAlex Topics |
|---|---|
| 人形机器人与具身智能 | T10879 Robotic Locomotion and Control；T10653 Robot Manipulation and Learning；T10462 Reinforcement Learning in Robotics |
| AI芯片与先进封装 | T11527 3D IC and TSV technologies；T10502 Advanced Memory and Neural Computing |
| 新能源与储能 | T10018 Advancements in Battery Materials；T10281 Advanced Battery Materials and Technologies；T11690 Aqueous and Flow Batteries；T10179 Supercapacitor Materials and Fabrication；T10811 Hydrogen Storage and Materials；T11007 Hybrid Renewable Energy Systems；T10247 Perovskite Materials and Applications |
| 新材料 | T11143 High Entropy Alloys Studies；T10275 2D Materials and Applications；T10245 Metamaterials and Metasurfaces Applications；T11948 Machine Learning in Materials Science；T10810 Polymer composites and self-healing；T10096 Metal-Organic Frameworks: Synthesis and Applications |
| 生物制造 | T10932 Microbial Metabolic Engineering and Bioproduction；T10404 Enzyme Catalysis and Immobilization；T11617 Enzyme Production and Characterization；T12856 Transgenic Plants and Applications；T11190 3D Printing in Biomedical Research；T14285 Biopolymer Synthesis and Applications |

`review` 和 `rejected` Topic 没有进入任何正式查询。

## 查询与发布语义

固定过滤器为：

```text
primary_location.source.is_core:true,
from_publication_date:<t-29>,
to_publication_date:<t>,
primary_topic.id:<approved-topic-1>|<approved-topic-2>|...
```

查询成功并不立即产生可读快照。只有一个批次的全部逻辑查询均成功后，才在事务中发布快照。相同值重查只保留新的查询日志；值发生变化时，旧快照转为 `is_current=0`，新快照递增 `revision_no` 并通过 `supersedes_id` 关联旧版本。

## 验证结果

- 自动化测试：27/27 通过。
- 首轮回填：150 个逻辑查询，150 次 HTTP 请求，0 失败，0 重试。
- 历史复查：20 个逻辑查询，20 次 HTTP 请求，0 失败，0 重试。
- 同 `run_id` 重跑：0 次新增 HTTP 请求，0 条新增查询日志，0 条新增快照。
- SQLite：`PRAGMA integrity_check=ok`，外键违规 0。
- API Key：仅从 `OPENALEX_API_KEY` 环境变量读取，不进入 URL 日志、数据库或报告。

## 是否可进入下一阶段

- 365 日回填：技术上可以。建议沿用单并发、分批和断点恢复，先估算并监控约 `5 × 365 = 1,825` 个基础逻辑查询；不要与 30 日测试库混作正式库。
- 首页接入：数据接口已具备接入条件，30 日返回 `complete`；90/365 日在尚未回填时会明确返回 `partial`，不会伪造缺失数据。本轮按要求未修改首页 UI。

