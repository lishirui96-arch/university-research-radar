# 全球科研热点趋势 V1.2：OpenAlex API 使用报告

生成日期：2026-11-18

## 执行前额度检查

回填前使用已配置的 `OPENALEX_API_KEY` 发送 1 次只读探测请求：

| 项目 | 结果 |
|---|---:|
| HTTP 状态 | 200 |
| `X-RateLimit-Limit` | 10,000 |
| `X-RateLimit-Remaining` | 9,829 |
| `X-RateLimit-Credits-Used` | 1 |
| `X-RateLimit-Cost-USD` | 0.0001 |
| 探测响应时间 | 1,506.8 ms |

剩余额度 9,829 高于预计 1,675 次基础请求，因此继续执行。探测请求没有写入趋势数据库。

## V1.2 回填用量

| 项目 | 结果 |
|---|---:|
| 逻辑查询 | 1,675 |
| 实际 HTTP 请求 | 1,675 |
| HTTP 200 | 1,675 |
| HTTP 429 | 0 |
| HTTP 5xx | 0 |
| 最终失败 | 0 |
| 重试 | 0 |
| 平均响应时间 | 892.2 ms |
| 最短响应时间 | 554.7 ms |
| 最长响应时间 | 10,411.4 ms |
| 最低观察到的剩余额度 | 8,154 |

额度从探测后的 9,829 降至最后日志观察到的 8,154，差值恰为 1,675，与实际回填请求数一致。

本轮外部请求总数为 1,676：1 次额度探测 + 1,675 次正式回填。完成后再次运行回填编排只进行了本地完整性计划检查，新增 OpenAlex 请求为 0。

## 历史累计日志说明

开发数据库当前共有 1,845 条成功查询日志：

- V1.1 初始 30 天回填：150；
- V1.1 历史复查：20；
- V1.2 缺失 335 天回填：1,675。

这 1,845 是数据库累计审计日志数量，不等于本轮新消耗。V1.2 新消耗严格为 1,675 个正式回填请求。

## 限流与错误处理

- 并发固定为 1。
- 请求间隔为 0.05 秒，并受实际响应时长限制。
- 429、5xx 和网络超时沿用指数退避，最多 4 次尝试。
- 可解析时尊重 `Retry-After`；退避等待设置上限。
- 最终失败写 `request_status='failed'` 且 `works_count=NULL`，不会写成 0。
- 任一批次不完整时不会发布该批快照。

本次没有触发限流或重试路径。相关分支继续由自动化测试覆盖。

## 请求口径

每次正式请求只读取 `meta.count`，参数包括：

```text
primary_location.source.is_core:true
from_publication_date:<snapshot_date-29>
to_publication_date:<snapshot_date>
primary_topic.id:<approved Topic OR list>
per-page=1
select=id
```

没有使用 `group_by=publication_date`，没有下载 Works 详细记录，Topic 映射和查询版本均保持 V1.1 口径。

