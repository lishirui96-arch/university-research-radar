# 现有研究领域比较与候选领域清单

> 本报告比较“范围”和“规模”，不把论文数量接近当作分类目标。

## 1. 现有五领域完整对比

| 一级领域 | approved Topics | Fields / Subfields | 2026-11-18 滚动30天 | 最近90天独立 Works | 此前90天独立 Works | 相邻90天增长 | 最近365天独立 Works | 365个快照范围 | 粒度判断 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| 人形机器人与具身智能 | 3 | 2 / 3 | 418 | 1,506 | 2,172 | -30.7% | 7,495 | 405–1,421 | 窄而聚焦：3 个 Topic 跨工程与 AI；名称包含“人形”，但 T10462 也覆盖一般机器人强化学习。 |
| AI芯片与先进封装 | 2 | 1 / 1 | 361 | 1,133 | 1,297 | -12.6% | 5,372 | 315–875 | 最窄：仅 2 个电子工程 Topic；同时混合 3D 封装与神经形态存储，不能代表完整 AI 芯片产业链。 |
| 新能源与储能 | 7 | 3 / 4 | 3,455 | 11,255 | 11,842 | -5.0% | 48,941 | 3,308–6,543 | 最宽之一：7 个 Topic 跨工程、材料、能源，混合储能材料、光伏材料与能源系统。 |
| 新材料 | 6 | 3 / 5 | 1,983 | 6,363 | 6,512 | -2.3% | 26,969 | 1,773–3,270 | 宽且异质：6 个 Topic 横跨合金、二维/超材料、材料信息学、聚合物和框架化学。 |
| 生物制造 | 6 | 2 / 3 | 710 | 2,174 | 2,320 | -6.3% | 9,484 | 644–1,087 | 中等宽度：6 个 Topic 混合代谢工程、酶、转基因植物、生物打印和生物聚合物。 |

增长率公式为 `(最近90天 - 此前90天) / 此前90天`。两个 90 天窗口不重叠；365 天值也是单次独立 Works 集合计数。

## 2. Field 与 Subfield 分布

### 人形机器人与具身智能

- Fields：Engineering (2)；Computer Science (1)。
- Subfields：Biomedical Engineering (1)；Control and Systems Engineering (1)；Artificial Intelligence (1)。
- Approved Topic IDs：`T10879`, `T10653`, `T10462`。

### AI芯片与先进封装

- Fields：Engineering (2)。
- Subfields：Electrical and Electronic Engineering (2)。
- Approved Topic IDs：`T11527`, `T10502`。

### 新能源与储能

- Fields：Engineering (4)；Materials Science (2)；Energy (1)。
- Subfields：Electrical and Electronic Engineering (4)；Electronic, Optical and Magnetic Materials (1)；Materials Chemistry (1)；Energy Engineering and Power Technology (1)。
- Approved Topic IDs：`T10018`, `T10281`, `T11690`, `T10179`, `T10811`, `T11007`, `T10247`。

### 新材料

- Fields：Engineering (1)；Materials Science (4)；Chemistry (1)。
- Subfields：Mechanical Engineering (1)；Materials Chemistry (2)；Electronic, Optical and Magnetic Materials (1)；Polymers and Plastics (1)；Inorganic Chemistry (1)。
- Approved Topic IDs：`T11143`, `T10275`, `T10245`, `T11948`, `T10810`, `T10096`。

### 生物制造

- Fields：Biochemistry, Genetics and Molecular Biology (5)；Engineering (1)。
- Subfields：Molecular Biology (3)；Biotechnology (2)；Biomedical Engineering (1)。
- Approved Topic IDs：`T10932`, `T10404`, `T11617`, `T12856`, `T11190`, `T14285`。

## 3. 交叉与重复

### 3.1 Topic ID 重复矩阵

所有非对角值均为 0。

| 类别 | 机器人 | AI芯片 | 新能源 | 新材料 | 生物制造 |
|---|---:|---:|---:|---:|---:|
| 机器人 | 3 | 0 | 0 | 0 | 0 |
| AI芯片 | 0 | 2 | 0 | 0 | 0 |
| 新能源 | 0 | 0 | 7 | 0 | 0 |
| 新材料 | 0 | 0 | 0 | 6 | 0 |
| 生物制造 | 0 | 0 | 0 | 0 | 6 |

### 3.2 官方父级与内容交叉

| 领域对 | 共享官方父级 | 解释 |
|---|---|---|
| 人形机器人与具身智能 ↔ AI芯片与先进封装 | Field: Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| 人形机器人与具身智能 ↔ 新能源与储能 | Field: Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| 人形机器人与具身智能 ↔ 新材料 | Field: Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| 人形机器人与具身智能 ↔ 生物制造 | Field: Engineering；Subfield: Biomedical Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| AI芯片与先进封装 ↔ 新能源与储能 | Field: Engineering；Subfield: Electrical and Electronic Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| AI芯片与先进封装 ↔ 新材料 | Field: Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| AI芯片与先进封装 ↔ 生物制造 | Field: Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| 新能源与储能 ↔ 新材料 | Field: Engineering, Materials Science；Subfield: Electronic, Optical and Magnetic Materials, Materials Chemistry | Topic ID 不重合，属于父级或语义交叉。 |
| 新能源与储能 ↔ 生物制造 | Field: Engineering | Topic ID 不重合，属于父级或语义交叉。 |
| 新材料 ↔ 生物制造 | Field: Engineering | Topic ID 不重合，属于父级或语义交叉。 |

### 3.3 覆盖范围导致的规模差异

- 新能源与储能的 7 个 Topic 覆盖电池、超级电容、氢储能、光伏材料和能源系统，最近365天 48,941 Works；其高值不能单纯解释为比所有其他前沿方向“更热”。
- AI芯片与先进封装只有 2 个 Topic，最近365天 5,372 Works；其低值部分来自覆盖链条不完整。
- 人形机器人与具身智能只有 3 个 Topic，且官方 Topic 无法细分 VLA、灵巧手、执行器等产品技术，存在 Topic 粒度不足导致的漏计。
- 新材料的 Topic 数不算最多，但材料 Topic 本身往往覆盖大型文献群，绝对规模仍高。

## 4. 全面候选领域清单

| 候选一级领域 | 代表 Topic IDs | 结构判断 | 建议位置 |
|---|---|---|---|
| 机器人与具身智能 | `T10879`, `T10653`, `T10462` | 保留为自定义技术集合；官方没有对应单一 Subfield。 | 主图候选 |
| 人工智能与机器学习 | `T12072`, `T10181`, `T11714`, `T11689`, `T12026`, `T10775` | 核心方法可形成独立集合，应用 AI 不宜全部纳入。 | 主图候选 |
| 半导体与集成电路 | `T11527`, `T10502`, `T10363`, `T10460`, `T10361`, `T10099` | 器件、电路、封装链条清晰；比“AI 芯片”可解释。 | 主图候选 |
| 先进计算与量子技术 | `T10682`, `T10020` | 官方 Topic 很少且同时包含计算、信息、密码学；暂偏窄。 | 二级/观察 |
| 清洁能源转换与储能 | `T10018`, `T10281`, `T11690`, `T10179`, `T10811`, `T11007`, `T10247`, `T10905` | 可分电化学储能、氢能、光伏、能源系统四个二级方向。 | 主图候选 |
| 前沿功能与结构材料 | `T11143`, `T10275`, `T10245`, `T11948`, `T10810`, `T10096`, `T12038` | 必须明确为精选前沿材料集合，不能称整个“新材料”。 | 主图候选 |
| 先进制造 | `T10705`, `T10783`, `T10763`, `T11814`, `T13027` | 工艺与制造系统可独立成类；与材料交叉但不重复 Topic。 | 主图候选 |
| 生物技术与生物制造 | `T10932`, `T10404`, `T11617`, `T12856`, `T11190`, `T14285`, `T10878` | CRISPR 属平台技术但不必自动计入制造；建议二级展示。 | 主图候选 |
| 航空航天 | `T12449`, `T12513`, `T11619`, `T11701`, `T11082` | 主题清晰，但与当前五类无连续口径；适合扩展板块。 | 二级/扩展 |
| 光电技术与传感器 | `T10299`, `T10767`, `T11429`, `T10205`, `T12153` | 跨电子工程、物理仪器与材料，需先划定器件/通信/传感边界。 | 二级/观察 |

## 5. 关键词无法充分覆盖的方向

以下产品技术在 OpenAlex 目录中没有稳定的一一对应 Topic：VLA、Chiplet、灵巧手、六维力传感器、行星滚柱丝杠、玻璃基板等。它们可以作为二级情报标签或检索词，但不应在未验证 precision/recall 前直接并入 `primary_topic.id` 的正式趋势口径。

## 6. 解释建议

首页绝对量应明确标注为“按固定 Topic 集合计数的近30天滚动 Works”，并同时提供相对指标（例如相邻独立90天增长率，或以起点=100的指数）。绝对量回答规模，相对量回答变化，二者不可互相替代。
