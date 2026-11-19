# 全球科研热点趋势 V1：Topic 映射报告

报告日期：2026-11-18（Asia/Singapore）  
配置版本：`v1`  
数据源：OpenAlex Topics API 当前目录  
配置文件：`config/trend_topic_mapping.json`

## 1. 结论

V1 共审核 43 个候选 Topic：24 个 `approved`、12 个 `review`、7 个 `rejected`。只有 `approved` Topic 进入趋势计数；`review` 和 `rejected` 只保留为可审计记录。

| 一级领域 | approved | review | rejected | V1 实际统计 Topic |
|---|---:|---:|---:|---|
| 人形机器人与具身智能 | 3 | 1 | 2 | T10879、T10653、T10462 |
| AI芯片与先进封装 | 2 | 3 | 1 | T11527、T10502 |
| 新能源与储能 | 7 | 2 | 1 | T10018、T10281、T11690、T10179、T10811、T11007、T10247 |
| 新材料 | 6 | 3 | 1 | T11143、T10275、T10245、T11948、T10810、T10096 |
| 生物制造 | 6 | 3 | 2 | T10932、T10404、T11617、T12856、T11190、T14285 |

所有候选的 OpenAlex 原始英文 Description、Domain、Field、Subfield、匹配理由、confidence 和 status 均已逐条保存在配置文件中。本报告列出审核结论与边界；配置文件是机器可读的完整审计记录。

## 2. 统一映射口径

- 统计实体：OpenAlex `Works`。
- 地域：全球，不增加国家、机构或高校过滤。
- corpus：主发表来源属于 OpenAlex/CWTS core sources，即 `primary_location.source.is_core:true`。
- 主题：只使用 `primary_topic.id`，不混用 `topics`、Concepts、Keywords 或检索词命中。
- 日期：`publication_date`，通过 `from_publication_date` 和 `to_publication_date` 过滤。
- 窗口：`t-29` 至 `t`，首尾均包含，共 30 个自然日。
- 状态：只有 `approved` 进入 API 查询。
- 去重：同一 Work 只有一个 primary Topic；同一一级领域内用 Topic OR 查询一次，不把各 Topic 的结果集拼接。

仓库没有既定的 core corpus 过滤器。实测证明 Works 级 `is_core:true` 无效；V1 因此明确采用可用且更严格的 `primary_location.source.is_core:true`，而不是静默忽略 corpus 条件。

## 3. 人形机器人与具身智能

### Approved

| Topic ID | Topic Name | Description 要点 | confidence | 匹配理由 |
|---|---|---|---:|---|
| T10879 | Robotic Locomotion and Control | 双足/多足运动、生物力学、动态行走与人形机器人控制 | 0.98 | 直接覆盖人形本体运动控制 |
| T10653 | Robot Manipulation and Learning | 抓取、示教学习、姿态估计、阻抗控制与安全交互 | 0.95 | 直接覆盖具身操作和感知学习 |
| T10462 | Reinforcement Learning in Robotics | 机器人强化学习、模型学习、策略梯度、探索与 sim-to-real | 0.86 | 覆盖具身智能的学习控制，且不是泛 AI Topic |

这三个 Topic 组合仍不是“整个机器人学”：教育机器人、社交心理、通用机电、移动机器人路径规划等没有被自动纳入。

### Review / Rejected

| Topic ID | Topic Name | status | confidence | 判断 |
|---|---|---|---:|---|
| T10709 | Social Robot Interaction and HRI | review | 0.55 | 与人形交互有关，但大量内容属于社会心理、辅助机器人和 uncanny valley |
| T11883 | Embodied and Extended Cognition | rejected | 0.08 | “embodied” 指认知神经科学与心智理论，不是具身 AI |
| T14335 | Educational Robotics and Engineering | rejected | 0.02 | 研究机器人课程与教育效果，不是人形/具身技术 |

## 4. AI芯片与先进封装

### Approved

| Topic ID | Topic Name | Description 要点 | confidence | 匹配理由 |
|---|---|---|---:|---|
| T11527 | 3D IC and TSV technologies | 3D IC、TSV、晶圆键合、热管理、异构集成与芯片堆叠 | 0.98 | 先进封装的直接 Topic |
| T10502 | Advanced Memory and Neural Computing | 忆阻器、阻变存储、脉冲神经元、神经形态计算与非易失存储 | 0.93 | AI 芯片的器件与存算路线 |

### Review / Rejected

| Topic ID | Topic Name | status | confidence | 判断 |
|---|---|---|---:|---|
| T12611 | Neural Networks and Reservoir Computing | review | 0.72 | 包含光子神经计算，但也包含算法与非芯片动力学研究 |
| T10460 | Electronic Packaging and Soldering Technologies | review | 0.64 | 与封装可靠性相关，但主体偏传统焊料、界面和导电胶 |
| T10363 | Low-power high-performance VLSI design | review | 0.58 | 可支撑 AI 芯片，但未限定 AI 加速器 |
| T11522 | VLSI and FPGA Design Techniques | rejected | 0.18 | 泛 FPGA/ASIC Topic，无法从 primary Topic 判断是否为 AI 芯片 |

OpenAlex 当前目录未找到边界足够清楚、可直接批准的“AI accelerator/TPU/NPU”独立 Topic。因此 V1 不用泛 VLSI Topic 补齐数量，避免把整个芯片设计领域纳入。

## 5. 新能源与储能

### Approved

| Topic ID | Topic Name | Description 要点 | confidence | 匹配理由 |
|---|---|---|---:|---|
| T10018 | Advancements in Battery Materials | 锂离子电池、电极材料、电化学性能与可充电储能 | 0.95 | 直接电化学储能 |
| T10281 | Advanced Battery Materials and Technologies | 锂硫、固态电解质、锂金属、高能量密度与稳定性 | 0.98 | 直接先进电池路线 |
| T11690 | Aqueous and Flow Batteries | 水系锌离子、液流电池、电解质与电网储能 | 0.96 | 直接长时/水系储能路线 |
| T10179 | Supercapacitor Materials and Fabrication | 超级电容材料、赝电容与柔性储能器件 | 0.94 | 直接电化学储能器件 |
| T10811 | Hydrogen Storage and Materials | 金属氢化物、化学储氢、容量、动力学与稳定性 | 0.91 | 直接氢储存 |
| T11007 | Hybrid Renewable Energy Systems | 氢能、电解、Power-to-Gas、燃料电池与可再生能源集成 | 0.88 | 新能源系统与储能直接相关 |
| T10247 | Perovskite Materials and Applications | 钙钛矿光伏效率、稳定性、载流子输运与器件 | 0.90 | 直接新能源发电路线 |

### Review / Rejected

| Topic ID | Topic Name | status | confidence | 判断 |
|---|---|---|---:|---|
| T10938 | Phase Change Materials Research | review | 0.74 | 明确涉及热储能，但应用集中于建筑和热管理 |
| T10905 | Solar Thermal and Photovoltaic Systems | review | 0.70 | 新能源相关，但系统工程范围较宽 |
| T10223 | Microgrid Control and Optimization | rejected | 0.20 | 储能仅是应用场景，纳入会扩张为整个电力控制 |

## 6. 新材料

### Approved

| Topic ID | Topic Name | Description 要点 | confidence | 匹配理由 |
|---|---|---|---:|---|
| T11143 | High Entropy Alloys Studies | 多主元合金、相稳定、微结构、力学性能与难熔合金 | 0.98 | 材料族、工艺/结构和性能边界清楚 |
| T10275 | 2D Materials and Applications | 二维半导体、范德华异质结构、激子与光电子器件 | 0.97 | 材料与器件锚点明确 |
| T10245 | Metamaterials and Metasurfaces Applications | 负折射、超表面、变换光学、太赫兹与纳光应用 | 0.96 | 结构、性能和应用明确 |
| T11948 | Machine Learning in Materials Science | 材料信息学、高通量、性能预测、晶体结构与分子动力学 | 0.95 | 明确以材料发现为对象，不是泛 AI |
| T10810 | Polymer composites and self-healing | 自修复聚合物、动态共价键、vitrimer 与复合材料性能 | 0.95 | 材料族与功能性能明确 |
| T10096 | Metal-Organic Frameworks: Synthesis and Applications | MOF 合成、结构、吸附、催化、分离与传感 | 0.95 | 多孔材料族和应用边界明确 |

### Review / Rejected

| Topic ID | Topic Name | status | confidence | 判断 |
|---|---|---|---:|---|
| T12038 | Covalent Organic Framework Applications | review | 0.76 | COF 边界清楚，但与新能源储能存在跨一级领域归属问题 |
| T11277 | Thermal properties of materials | review | 0.73 | 有热管理材料，也含大量基础热输运 |
| T11782 | Magnetic Properties of Alloys | review | 0.71 | 含稀土永磁，但范围扩展到较宽的磁性合金和器件 |
| T11737 | Advanced Materials and Mechanics | rejected | 0.28 | 混合 4D 打印、软体机器人、水凝胶等多路线，边界不稳定 |

V1 没有纳入“所有 Materials Science Topic”。每个 approved Topic 都有具体材料族，并至少有结构/制备、性能或应用锚点。

## 7. 生物制造

### Approved

| Topic ID | Topic Name | Description 要点 | confidence | 匹配理由 |
|---|---|---|---:|---|
| T10932 | Microbial Metabolic Engineering and Bioproduction | 代谢工程、合成生物学、细胞工厂、生物炼制与代谢流 | 0.99 | 生物制造核心 Topic |
| T10404 | Enzyme Catalysis and Immobilization | 酶固定化、定向进化、生物催化与工业应用 | 0.92 | 直接酶工程制造路线 |
| T11617 | Enzyme Production and Characterization | 微生物工业酶、耐热酶与极端微生物 | 0.88 | 直接工业酶生产 |
| T12856 | Transgenic Plants and Applications | 重组蛋白、糖基化工程、植物生物反应器与分子农场 | 0.91 | 直接植物生物制造 |
| T11190 | 3D Printing in Biomedical Research | 生物打印、生物墨水、组织工程、类器官芯片与支架 | 0.86 | 直接组织/生物材料制造 |
| T14285 | Biopolymer Synthesis and Applications | 微生物发酵生产聚谷氨酸等生物聚合物 | 0.90 | 直接生物合成材料 |

### Review / Rejected

| Topic ID | Topic Name | status | confidence | 判断 |
|---|---|---|---:|---|
| T10171 | Biofuel production and bioconversion | review | 0.72 | 属于生物转化制造，但也可归入新能源，需确定唯一归属 |
| T10864 | Fluid Dynamics and Mixing | review | 0.68 | 直接涉及生物反应器放大，但 Topic 名称和部分内容属于通用流体工程 |
| T10621 | Gene Regulatory Network Analysis | review | 0.58 | 含合成生物学/基因回路，但大量内容是基础网络分析 |
| T10521 | RNA and protein synthesis mechanisms | rejected | 0.12 | 主体是核糖体和翻译机制，制造只是潜在应用 |
| T10750 | Fermentation and Sensory Analysis | rejected | 0.20 | 主体是葡萄酒风味与感官分析，不是平台型生物制造 |

## 8. 人工审核清单

下一轮如需扩大映射，应优先审核 12 个 `review` Topic，而不是重新以关键词自动批准：

- 人形机器人：T10709。
- AI芯片与封装：T12611、T10460、T10363。
- 新能源与储能：T10938、T10905。
- 新材料：T12038、T11277、T11782。
- 生物制造：T10171、T10864、T10621。

审核建议采用每个 Topic 至少 3 篇近期代表 Work 的标题/摘要边界抽查，并记录“纳入、排除、拆分或跨类唯一归属”的决定。当前 V1 未执行论文级人工抽样，因此 review Topic 不进入统计。

## 9. 局限与决策日志

- OpenAlex Topic 是模型聚类，不是平台自定义本体；其名称、描述和 Work 归类可能回填或更新。
- `primary_topic` 保证单一主 Topic，但会牺牲跨学科覆盖；这是本轮为保持统一统计口径而接受的取舍。
- 同一个研究方向可能被 OpenAlex 拆到多个 Topic，也可能被一个 Topic 混合；confidence 表示映射把握，不表示论文质量。
- 本报告不声称五个领域是全球“升温”方向。30 天数量只能表示当前窗口规模，趋势判断仍需历史基线。
- 2026-11-18 决定：review/rejected 不进入 V1 计数。
- 2026-11-18 决定：approved Topic 在五个一级领域之间保持唯一归属，避免跨类别重复。
- 2026-11-18 决定：使用 `primary_location.source.is_core:true` 定义 core corpus。
