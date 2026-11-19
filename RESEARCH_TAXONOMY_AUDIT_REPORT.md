# 全球科研热点领域分类体系审计报告

> 审计日期：2026-11-18。性质：只读数据审计；未修改 UI、数据库、Topic 状态或正式映射。

## 1. 结论摘要

1. 官方目录已还原为 **4 Domains → 26 Fields → 252 Subfields → 4,516 Topics**。这四层是隶属关系，不代表相邻节点具有相同论文规模。
2. 现有映射共有 **43** 个候选：approved 24、review 12、rejected 7；状态原样保留。
3. 24 个 approved Topic 在五个一级领域之间 **没有 Topic ID 重复分配**，所以现有五条线不存在由同一 primary_topic ID 同时计入两个领域导致的机械重复。
4. 五类不是同一粒度：approved Topic 数为 2–7，跨 1–3 个 Fields、1–5 个 Subfields；“新材料”和“新能源与储能”是多技术集合，而“AI芯片与先进封装”仅有 2 个 Topic。
5. 官方 v2 目录与映射文件记录的层级元数据有 **8** 处变化；Topic ID 均仍存在。这是层级元数据漂移，不等于审核状态失效。
6. 30 天快照库完整：365 日 × 5 类 = 1,825 条当前快照，无重复，窗口均为 30 个自然日；但这 1,825 条只能代表 mapping v1。

## 2. 数据来源与口径

- 官方目录：OpenAlex 官方仓库 `ourresearch/openalex-topic-classification`，本地审计提交 `98df3b96c36128819075dd86949c9f18411fab40`，README 标注 v2 为 2026-10 current，目录文件 `v2/data/topics/topics.json`。
- 映射：`C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\university-research-radar\config\trend_topic_mapping.json`，版本 `v1`，as-of `2026-11-18`。
- 自定义导航 taxonomy：`C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\university-research-radar\config\research_taxonomy.json`，版本 `1.0.0`。它是产品导航层，不是 OpenAlex 官方层级。
- 趋势数据库：`C:\Users\LSR\Documents\Codex\2026-11-18\ji\work\trend-v1-1-test-20261118.db`，只读打开。
- 独立规模查询：OpenAlex Works `meta.count`，统一使用 `primary_location.source.is_core:true`、`primary_topic.id`、`publication_date`。
- 时间窗口：最近90天 2026-08-21～2026-11-18；此前90天 2026-05-23～2026-08-20；最近365天 2025-11-19～2026-11-18，均为闭区间。
- 本轮正式分析请求 15 次（5 类 × 3 窗口），另有 2 次成功的元数据/连接探测；所有正式计数请求成功、无重试。
- 重要限制：90/365 天规模均为独立唯一 Works 计数，**没有**累加重叠的 30 天滚动快照。

## 3. 数据库只读检查

| 检查项 | 结果 |
|---|---:|
| 当前快照 | 1,825 |
| 日期范围 | 2025-11-19 ～ 2026-11-18 |
| 独立日期 / 类别 | 365 / 5 |
| 当前快照重复键 | 0 |
| 非 30 日窗口 | 0 |
| 成功日志中 core 条件偏离 | 0 |
| topics 表 | 0（官方目录未落入该开发库） |

完整 4,516 Topic 的 ID、名称、描述及四级隶属关系另存于 `RESEARCH_OPENALEX_TOPIC_HIERARCHY.csv`，避免在 Markdown 中复制 4,516 行而降低可审阅性。

## 4. OpenAlex 官方四级结构

### 4.1 Domain → Field

| Domain | Fields | Topic 数 |
|---|---:|---:|
| Health Sciences | 5 | 844 |
| Life Sciences | 5 | 614 |
| Physical Sciences | 10 | 1,571 |
| Social Sciences | 6 | 1,487 |

### 4.2 Field → Subfield

| Domain | Field | Subfields | Topics |
|---|---|---:|---:|
| Health Sciences | Dentistry | 4 | 13 |
| Health Sciences | Health Professions | 11 | 107 |
| Health Sciences | Medicine | 42 | 692 |
| Health Sciences | Nursing | 4 | 21 |
| Health Sciences | Veterinary | 2 | 11 |
| Life Sciences | Agricultural and Biological Sciences | 11 | 235 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | 14 | 248 |
| Life Sciences | Immunology and Microbiology | 5 | 44 |
| Life Sciences | Neuroscience | 8 | 62 |
| Life Sciences | Pharmacology, Toxicology and Pharmaceutics | 4 | 25 |
| Physical Sciences | Chemical Engineering | 6 | 13 |
| Physical Sciences | Chemistry | 6 | 101 |
| Physical Sciences | Computer Science | 11 | 302 |
| Physical Sciences | Earth and Planetary Sciences | 8 | 57 |
| Physical Sciences | Energy | 5 | 27 |
| Physical Sciences | Engineering | 16 | 560 |
| Physical Sciences | Environmental Science | 11 | 202 |
| Physical Sciences | Materials Science | 8 | 123 |
| Physical Sciences | Mathematics | 10 | 82 |
| Physical Sciences | Physics and Astronomy | 8 | 104 |
| Social Sciences | Arts and Humanities | 13 | 266 |
| Social Sciences | Business, Management and Accounting | 9 | 146 |
| Social Sciences | Decision Sciences | 4 | 60 |
| Social Sciences | Economics, Econometrics and Finance | 3 | 107 |
| Social Sciences | Psychology | 7 | 144 |
| Social Sciences | Social Sciences | 22 | 764 |

### 4.3 Subfield → Topic

| Domain | Field | Subfield | Topics |
|---|---|---|---:|
| Health Sciences | Dentistry | General Dentistry | 1 |
| Health Sciences | Dentistry | Oral Surgery | 5 |
| Health Sciences | Dentistry | Orthodontics | 3 |
| Health Sciences | Dentistry | Periodontics | 4 |
| Health Sciences | Health Professions | Complementary and Manual Therapy | 2 |
| Health Sciences | Health Professions | Emergency Medical Services | 7 |
| Health Sciences | Health Professions | General Health Professions | 50 |
| Health Sciences | Health Professions | Health Information Management | 12 |
| Health Sciences | Health Professions | Medical Laboratory Technology | 2 |
| Health Sciences | Health Professions | Medical Terminology | 1 |
| Health Sciences | Health Professions | Occupational Therapy | 8 |
| Health Sciences | Health Professions | Pharmacy | 5 |
| Health Sciences | Health Professions | Physical Therapy, Sports Therapy and Rehabilitation | 7 |
| Health Sciences | Health Professions | Radiological and Ultrasound Technology | 3 |
| Health Sciences | Health Professions | Speech and Hearing | 10 |
| Health Sciences | Medicine | Anatomy | 1 |
| Health Sciences | Medicine | Anesthesiology and Pain Medicine | 4 |
| Health Sciences | Medicine | Cardiology and Cardiovascular Medicine | 29 |
| Health Sciences | Medicine | Complementary and alternative medicine | 20 |
| Health Sciences | Medicine | Critical Care and Intensive Care Medicine | 5 |
| Health Sciences | Medicine | Dermatology | 13 |
| Health Sciences | Medicine | Emergency Medicine | 11 |
| Health Sciences | Medicine | Endocrinology, Diabetes and Metabolism | 18 |
| Health Sciences | Medicine | Epidemiology | 42 |
| Health Sciences | Medicine | Family Practice | 2 |
| Health Sciences | Medicine | Gastroenterology | 5 |
| Health Sciences | Medicine | Geriatrics and Gerontology | 3 |
| Health Sciences | Medicine | Health Informatics | 1 |
| Health Sciences | Medicine | Hematology | 12 |
| Health Sciences | Medicine | Hepatology | 6 |
| Health Sciences | Medicine | Immunology and Allergy | 3 |
| Health Sciences | Medicine | Infectious Diseases | 21 |
| Health Sciences | Medicine | Internal Medicine | 1 |
| Health Sciences | Medicine | Nephrology | 7 |
| Health Sciences | Medicine | Neurology | 32 |
| Health Sciences | Medicine | Obstetrics and Gynecology | 8 |
| Health Sciences | Medicine | Oncology | 34 |
| Health Sciences | Medicine | Ophthalmology | 12 |
| Health Sciences | Medicine | Orthopedics and Sports Medicine | 7 |
| Health Sciences | Medicine | Otorhinolaryngology | 3 |
| Health Sciences | Medicine | Pathology and Forensic Medicine | 23 |
| Health Sciences | Medicine | Pediatrics, Perinatology and Child Health | 20 |
| Health Sciences | Medicine | Psychiatry and Mental health | 16 |
| Health Sciences | Medicine | Public Health, Environmental and Occupational Health | 54 |
| Health Sciences | Medicine | Pulmonary and Respiratory Medicine | 52 |
| Health Sciences | Medicine | Radiology, Nuclear Medicine and Imaging | 30 |
| Health Sciences | Medicine | Rehabilitation | 7 |
| Health Sciences | Medicine | Reproductive Medicine | 8 |
| Health Sciences | Medicine | Rheumatology | 24 |
| Health Sciences | Medicine | Surgery | 96 |
| Health Sciences | Medicine | Transplantation | 2 |
| Health Sciences | Medicine | Urology | 5 |
| Health Sciences | Nursing | Issues, ethics and legal aspects | 2 |
| Health Sciences | Nursing | Leadership and Management | 1 |
| Health Sciences | Nursing | Nutrition and Dietetics | 17 |
| Health Sciences | Nursing | Research and Theory | 1 |
| Health Sciences | Veterinary | Equine | 1 |
| Health Sciences | Veterinary | Small Animals | 10 |
| Life Sciences | Agricultural and Biological Sciences | Agronomy and Crop Science | 11 |
| Life Sciences | Agricultural and Biological Sciences | Animal Science and Zoology | 8 |
| Life Sciences | Agricultural and Biological Sciences | Aquatic Science | 7 |
| Life Sciences | Agricultural and Biological Sciences | Ecology, Evolution, Behavior and Systematics | 33 |
| Life Sciences | Agricultural and Biological Sciences | Food Science | 32 |
| Life Sciences | Agricultural and Biological Sciences | Forestry | 7 |
| Life Sciences | Agricultural and Biological Sciences | General Agricultural and Biological Sciences | 20 |
| Life Sciences | Agricultural and Biological Sciences | Horticulture | 1 |
| Life Sciences | Agricultural and Biological Sciences | Insect Science | 14 |
| Life Sciences | Agricultural and Biological Sciences | Plant Science | 90 |
| Life Sciences | Agricultural and Biological Sciences | Soil Science | 12 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Aging | 1 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Biochemistry | 10 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Biophysics | 6 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Biotechnology | 8 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Cancer Research | 13 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Cell Biology | 17 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Clinical Biochemistry | 4 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Developmental Biology | 2 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Endocrinology | 7 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Genetics | 49 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Molecular Biology | 135 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Molecular Medicine | 3 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Physiology | 34 |
| Life Sciences | Biochemistry, Genetics and Molecular Biology | Structural Biology | 1 |
| Life Sciences | Immunology and Microbiology | Applied Microbiology and Biotechnology | 2 |
| Life Sciences | Immunology and Microbiology | Immunology | 26 |
| Life Sciences | Immunology and Microbiology | Microbiology | 7 |
| Life Sciences | Immunology and Microbiology | Parasitology | 7 |
| Life Sciences | Immunology and Microbiology | Virology | 3 |
| Life Sciences | Neuroscience | Behavioral Neuroscience | 1 |
| Life Sciences | Neuroscience | Biological Psychiatry | 1 |
| Life Sciences | Neuroscience | Cellular and Molecular Neuroscience | 13 |
| Life Sciences | Neuroscience | Cognitive Neuroscience | 28 |
| Life Sciences | Neuroscience | Developmental Neuroscience | 3 |
| Life Sciences | Neuroscience | Endocrine and Autonomic Systems | 3 |
| Life Sciences | Neuroscience | Sensory Systems | 3 |
| Life Sciences | Pharmacology, Toxicology and Pharmaceutics | Drug Discovery | 1 |
| Life Sciences | Pharmacology, Toxicology and Pharmaceutics | Pharmaceutical Science | 5 |
| Life Sciences | Pharmacology, Toxicology and Pharmaceutics | Pharmacology | 37 |
| Life Sciences | Pharmacology, Toxicology and Pharmaceutics | Toxicology | 4 |
| Physical Sciences | Chemical Engineering | Bioengineering | 1 |
| Physical Sciences | Chemical Engineering | Catalysis | 4 |
| Physical Sciences | Chemical Engineering | Chemical Health and Safety | 1 |
| Physical Sciences | Chemical Engineering | Filtration and Separation | 1 |
| Physical Sciences | Chemical Engineering | Fluid Flow and Transfer Processes | 4 |
| Physical Sciences | Chemical Engineering | Process Chemistry and Technology | 2 |
| Physical Sciences | Chemistry | Analytical Chemistry | 7 |
| Physical Sciences | Chemistry | Electrochemistry | 1 |
| Physical Sciences | Chemistry | Inorganic Chemistry | 12 |
| Physical Sciences | Chemistry | Organic Chemistry | 61 |
| Physical Sciences | Chemistry | Physical and Theoretical Chemistry | 8 |
| Physical Sciences | Chemistry | Spectroscopy | 12 |
| Physical Sciences | Computer Science | Artificial Intelligence | 77 |
| Physical Sciences | Computer Science | Computational Theory and Mathematics | 24 |
| Physical Sciences | Computer Science | Computer Graphics and Computer-Aided Design | 4 |
| Physical Sciences | Computer Science | Computer Networks and Communications | 43 |
| Physical Sciences | Computer Science | Computer Science Applications | 10 |
| Physical Sciences | Computer Science | Computer Vision and Pattern Recognition | 35 |
| Physical Sciences | Computer Science | Hardware and Architecture | 8 |
| Physical Sciences | Computer Science | Human-Computer Interaction | 8 |
| Physical Sciences | Computer Science | Information Systems | 78 |
| Physical Sciences | Computer Science | Signal Processing | 10 |
| Physical Sciences | Computer Science | Software | 5 |
| Physical Sciences | Earth and Planetary Sciences | Atmospheric Science | 13 |
| Physical Sciences | Earth and Planetary Sciences | Earth-Surface Processes | 6 |
| Physical Sciences | Earth and Planetary Sciences | Geochemistry and Petrology | 6 |
| Physical Sciences | Earth and Planetary Sciences | Geology | 5 |
| Physical Sciences | Earth and Planetary Sciences | Geophysics | 10 |
| Physical Sciences | Earth and Planetary Sciences | Oceanography | 9 |
| Physical Sciences | Earth and Planetary Sciences | Paleontology | 7 |
| Physical Sciences | Earth and Planetary Sciences | Space and Planetary Science | 1 |
| Physical Sciences | Energy | Energy Engineering and Power Technology | 2 |
| Physical Sciences | Energy | Fuel Technology | 1 |
| Physical Sciences | Energy | General Energy | 1 |
| Physical Sciences | Energy | Nuclear Energy and Engineering | 1 |
| Physical Sciences | Energy | Renewable Energy, Sustainability and the Environment | 22 |
| Physical Sciences | Engineering | Aerospace Engineering | 44 |
| Physical Sciences | Engineering | Architecture | 4 |
| Physical Sciences | Engineering | Automotive Engineering | 12 |
| Physical Sciences | Engineering | Biomedical Engineering | 72 |
| Physical Sciences | Engineering | Building and Construction | 22 |
| Physical Sciences | Engineering | Civil and Structural Engineering | 42 |
| Physical Sciences | Engineering | Computational Mechanics | 30 |
| Physical Sciences | Engineering | Control and Systems Engineering | 44 |
| Physical Sciences | Engineering | Electrical and Electronic Engineering | 117 |
| Physical Sciences | Engineering | General Engineering | 1 |
| Physical Sciences | Engineering | Industrial and Manufacturing Engineering | 17 |
| Physical Sciences | Engineering | Mechanical Engineering | 79 |
| Physical Sciences | Engineering | Mechanics of Materials | 29 |
| Physical Sciences | Engineering | Media Technology | 12 |
| Physical Sciences | Engineering | Ocean Engineering | 23 |
| Physical Sciences | Engineering | Safety, Risk, Reliability and Quality | 12 |
| Physical Sciences | Environmental Science | Ecological Modeling | 3 |
| Physical Sciences | Environmental Science | Ecology | 33 |
| Physical Sciences | Environmental Science | Environmental Chemistry | 11 |
| Physical Sciences | Environmental Science | Environmental Engineering | 19 |
| Physical Sciences | Environmental Science | Global and Planetary Change | 30 |
| Physical Sciences | Environmental Science | Health, Toxicology and Mutagenesis | 16 |
| Physical Sciences | Environmental Science | Management, Monitoring, Policy and Law | 34 |
| Physical Sciences | Environmental Science | Nature and Landscape Conservation | 12 |
| Physical Sciences | Environmental Science | Pollution | 11 |
| Physical Sciences | Environmental Science | Waste Management and Disposal | 9 |
| Physical Sciences | Environmental Science | Water Science and Technology | 24 |
| Physical Sciences | Materials Science | Biomaterials | 13 |
| Physical Sciences | Materials Science | Ceramics and Composites | 2 |
| Physical Sciences | Materials Science | Electronic, Optical and Magnetic Materials | 17 |
| Physical Sciences | Materials Science | General Materials Science | 3 |
| Physical Sciences | Materials Science | Materials Chemistry | 69 |
| Physical Sciences | Materials Science | Metals and Alloys | 1 |
| Physical Sciences | Materials Science | Polymers and Plastics | 14 |
| Physical Sciences | Materials Science | Surfaces, Coatings and Films | 4 |
| Physical Sciences | Mathematics | Algebra and Number Theory | 5 |
| Physical Sciences | Mathematics | Applied Mathematics | 17 |
| Physical Sciences | Mathematics | Computational Mathematics | 1 |
| Physical Sciences | Mathematics | Discrete Mathematics and Combinatorics | 4 |
| Physical Sciences | Mathematics | Geometry and Topology | 11 |
| Physical Sciences | Mathematics | Mathematical Physics | 12 |
| Physical Sciences | Mathematics | Modeling and Simulation | 6 |
| Physical Sciences | Mathematics | Numerical Analysis | 5 |
| Physical Sciences | Mathematics | Statistics and Probability | 20 |
| Physical Sciences | Mathematics | Theoretical Computer Science | 1 |
| Physical Sciences | Physics and Astronomy | Acoustics and Ultrasonics | 1 |
| Physical Sciences | Physics and Astronomy | Astronomy and Astrophysics | 21 |
| Physical Sciences | Physics and Astronomy | Atomic and Molecular Physics, and Optics | 37 |
| Physical Sciences | Physics and Astronomy | Condensed Matter Physics | 8 |
| Physical Sciences | Physics and Astronomy | Instrumentation | 2 |
| Physical Sciences | Physics and Astronomy | Nuclear and High Energy Physics | 13 |
| Physical Sciences | Physics and Astronomy | Radiation | 6 |
| Physical Sciences | Physics and Astronomy | Statistical and Nonlinear Physics | 16 |
| Social Sciences | Arts and Humanities | Archeology | 22 |
| Social Sciences | Arts and Humanities | Classics | 5 |
| Social Sciences | Arts and Humanities | Conservation | 6 |
| Social Sciences | Arts and Humanities | General Arts and Humanities | 4 |
| Social Sciences | Arts and Humanities | History | 44 |
| Social Sciences | Arts and Humanities | History and Philosophy of Science | 19 |
| Social Sciences | Arts and Humanities | Language and Linguistics | 20 |
| Social Sciences | Arts and Humanities | Literature and Literary Theory | 53 |
| Social Sciences | Arts and Humanities | Museology | 9 |
| Social Sciences | Arts and Humanities | Music | 5 |
| Social Sciences | Arts and Humanities | Philosophy | 49 |
| Social Sciences | Arts and Humanities | Religious studies | 15 |
| Social Sciences | Arts and Humanities | Visual Arts and Performing Arts | 17 |
| Social Sciences | Business, Management and Accounting | Accounting | 22 |
| Social Sciences | Business, Management and Accounting | Business and International Management | 2 |
| Social Sciences | Business, Management and Accounting | Industrial relations | 1 |
| Social Sciences | Business, Management and Accounting | Management Information Systems | 16 |
| Social Sciences | Business, Management and Accounting | Management of Technology and Innovation | 16 |
| Social Sciences | Business, Management and Accounting | Marketing | 15 |
| Social Sciences | Business, Management and Accounting | Organizational Behavior and Human Resource Management | 30 |
| Social Sciences | Business, Management and Accounting | Strategy and Management | 42 |
| Social Sciences | Business, Management and Accounting | Tourism, Leisure and Hospitality Management | 2 |
| Social Sciences | Decision Sciences | General Decision Sciences | 2 |
| Social Sciences | Decision Sciences | Information Systems and Management | 15 |
| Social Sciences | Decision Sciences | Management Science and Operations Research | 34 |
| Social Sciences | Decision Sciences | Statistics, Probability and Uncertainty | 9 |
| Social Sciences | Economics, Econometrics and Finance | Economics and Econometrics | 79 |
| Social Sciences | Economics, Econometrics and Finance | Finance | 16 |
| Social Sciences | Economics, Econometrics and Finance | General Economics, Econometrics and Finance | 12 |
| Social Sciences | Psychology | Applied Psychology | 7 |
| Social Sciences | Psychology | Clinical Psychology | 38 |
| Social Sciences | Psychology | Developmental and Educational Psychology | 20 |
| Social Sciences | Psychology | Experimental and Cognitive Psychology | 24 |
| Social Sciences | Psychology | General Psychology | 1 |
| Social Sciences | Psychology | Neuropsychology and Physiological Psychology | 2 |
| Social Sciences | Psychology | Social Psychology | 52 |
| Social Sciences | Social Sciences | Anthropology | 25 |
| Social Sciences | Social Sciences | Communication | 16 |
| Social Sciences | Social Sciences | Cultural Studies | 38 |
| Social Sciences | Social Sciences | Demography | 27 |
| Social Sciences | Social Sciences | Development | 8 |
| Social Sciences | Social Sciences | Education | 137 |
| Social Sciences | Social Sciences | Gender Studies | 21 |
| Social Sciences | Social Sciences | General Social Sciences | 16 |
| Social Sciences | Social Sciences | Geography, Planning and Development | 15 |
| Social Sciences | Social Sciences | Health | 14 |
| Social Sciences | Social Sciences | Human Factors and Ergonomics | 3 |
| Social Sciences | Social Sciences | Law | 40 |
| Social Sciences | Social Sciences | Library and Information Sciences | 2 |
| Social Sciences | Social Sciences | Life-span and Life-course Studies | 2 |
| Social Sciences | Social Sciences | Linguistics and Language | 6 |
| Social Sciences | Social Sciences | Political Science and International Relations | 118 |
| Social Sciences | Social Sciences | Public Administration | 3 |
| Social Sciences | Social Sciences | Safety Research | 19 |
| Social Sciences | Social Sciences | Sociology and Political Science | 224 |
| Social Sciences | Social Sciences | Transportation | 9 |
| Social Sciences | Social Sciences | Urban Studies | 19 |

## 5. 现有 43 个候选 Topic

下表使用官方 v2 的当前层级；`status` 与 `confidence` 来自现有映射，未作修改。

| 一级领域 | Topic ID | Topic Name | Domain | Field | Subfield | confidence | status | 原审核依据 |
|---|---|---|---|---|---|---:|---|---|
| 人形机器人与具身智能 | T10879 | Robotic Locomotion and Control | Physical Sciences | Engineering | Biomedical Engineering | 0.98 | approved | 直接覆盖双足、人形机器人运动控制，是人形本体能力的核心 Topic。 |
| 人形机器人与具身智能 | T10653 | Robot Manipulation and Learning | Physical Sciences | Engineering | Control and Systems Engineering | 0.95 | approved | 直接覆盖具身操作、抓取、示教学习、感知和安全交互。 |
| 人形机器人与具身智能 | T10462 | Reinforcement Learning in Robotics | Physical Sciences | Computer Science | Artificial Intelligence | 0.86 | approved | 以机器人强化学习、模型学习和 sim-to-real 为主，能够覆盖具身智能的学习控制部分；不等同于整个机器人学。 |
| 人形机器人与具身智能 | T10709 | Social Robot Interaction and HRI | Social Sciences | Psychology | Social Psychology | 0.55 | review | 与人形机器人的人机交互相关，但大量成果属于社会心理与辅助机器人，是否计入具身智能需人工决定。 |
| 人形机器人与具身智能 | T11883 | Embodied and Extended Cognition | Life Sciences | Neuroscience | Cognitive Neuroscience | 0.08 | rejected | 名称含 embodied，但主体是认知神经科学与心智哲学，不是具身 AI 或机器人。 |
| 人形机器人与具身智能 | T14335 | Educational Robotics and Engineering | Physical Sciences | Computer Science | Artificial Intelligence | 0.02 | rejected | 研究对象是机器人教育和课程，不是人形机器人或具身智能技术。 |
| AI芯片与先进封装 | T11527 | 3D IC and TSV technologies | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.98 | approved | 直接覆盖 3D IC、TSV、晶圆键合、异构集成与芯片堆叠，是先进封装核心 Topic。 |
| AI芯片与先进封装 | T10502 | Advanced Memory and Neural Computing | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.93 | approved | 直接覆盖忆阻器、非易失存储与神经形态计算器件，属于 AI 芯片的器件路线。 |
| AI芯片与先进封装 | T12611 | Neural Networks and Reservoir Computing | Physical Sciences | Computer Science | Artificial Intelligence | 0.72 | review | 覆盖光子神经计算和半导体激光器，但同时包含算法与动力学，需确认是否按 AI 芯片硬件纳入。 |
| AI芯片与先进封装 | T10460 | Electronic Packaging and Soldering Technologies | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.64 | review | 与封装可靠性有关，但主体偏传统焊料和互连材料，不宜自动等同先进封装。 |
| AI芯片与先进封装 | T10363 | Low-power high-performance VLSI design | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.58 | review | 低功耗 VLSI 可支撑 AI 芯片，但 Topic 未限定 AI 加速器，需人工审核边界。 |
| AI芯片与先进封装 | T11522 | VLSI and FPGA Design Techniques | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.18 | rejected | 泛 FPGA/ASIC 设计范围过宽，无法从 primary Topic 判断是否属于 AI 芯片。 |
| 新能源与储能 | T10018 | Advancements in Battery Materials | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.95 | approved | 直接覆盖锂离子电池、电极材料和电化学储能。 |
| 新能源与储能 | T10281 | Advanced Battery Materials and Technologies | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.98 | approved | 直接覆盖固态电解质、锂硫、锂金属和高能量密度电池。 |
| 新能源与储能 | T11690 | Aqueous and Flow Batteries | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.96 | approved | 直接覆盖水系锌离子、液流电池和电网储能。 |
| 新能源与储能 | T10179 | Supercapacitor Materials and Fabrication | Physical Sciences | Materials Science | Electronic, Optical and Magnetic Materials | 0.94 | approved | 直接覆盖超级电容器材料、制造与柔性储能器件。 |
| 新能源与储能 | T10811 | Hydrogen Storage and Materials | Physical Sciences | Materials Science | Materials Chemistry | 0.91 | approved | 直接覆盖氢储存材料、容量、动力学和稳定性。 |
| 新能源与储能 | T11007 | Hybrid Renewable Energy Systems | Physical Sciences | Energy | Energy Engineering and Power Technology | 0.88 | approved | 覆盖氢能、电解、Power-to-Gas、燃料电池及可再生能源储能集成。 |
| 新能源与储能 | T10247 | Perovskite Materials and Applications | Physical Sciences | Engineering | Electrical and Electronic Engineering | 0.90 | approved | 主体是钙钛矿光伏材料和器件，属于新能源发电路线。 |
| 新能源与储能 | T10938 | Phase Change Materials Research | Physical Sciences | Engineering | Mechanical Engineering | 0.74 | review | 明确覆盖热储能，但主要应用偏建筑与热管理，是否纳入首页新能源口径需审核。 |
| 新能源与储能 | T10905 | Solar Thermal and Photovoltaic Systems | Physical Sciences | Energy | Renewable Energy, Sustainability and the Environment | 0.70 | review | 覆盖太阳能与光伏系统，但系统工程范围较宽，需确认与材料/器件口径的边界。 |
| 新能源与储能 | T10223 | Microgrid Control and Optimization | Physical Sciences | Engineering | Control and Systems Engineering | 0.20 | rejected | 储能只是微电网控制场景之一，纳入会把领域扩张为整个电力控制。 |
| 新材料 | T11143 | High Entropy Alloys Studies | Physical Sciences | Engineering | Mechanical Engineering | 0.98 | approved | 材料族、组织/相稳定和性能问题均明确，属于高熵合金前沿材料。 |
| 新材料 | T10275 | 2D Materials and Applications | Physical Sciences | Materials Science | Materials Chemistry | 0.97 | approved | 明确覆盖二维半导体材料、异质结构、性能与光电子器件。 |
| 新材料 | T10245 | Metamaterials and Metasurfaces Applications | Physical Sciences | Materials Science | Electronic, Optical and Magnetic Materials | 0.96 | approved | 明确覆盖超材料/超表面结构、波前性能和太赫兹/纳光应用。 |
| 新材料 | T11948 | Machine Learning in Materials Science | Physical Sciences | Materials Science | Materials Chemistry | 0.95 | approved | 材料对象与高通量/机器学习发现路线明确，不是泛 AI。 |
| 新材料 | T10810 | Polymer composites and self-healing | Physical Sciences | Materials Science | Polymers and Plastics | 0.95 | approved | 明确覆盖自修复聚合物、动态键和复合材料性能。 |
| 新材料 | T10096 | Metal-Organic Frameworks: Synthesis and Applications | Physical Sciences | Chemistry | Inorganic Chemistry | 0.95 | approved | 材料族、合成、结构与吸附/催化/分离应用均明确。 |
| 新材料 | T12038 | Covalent Organic Framework Applications | Physical Sciences | Materials Science | Materials Chemistry | 0.76 | review | COF 材料边界明确，但与新能源储能存在跨一级领域归属问题，需人工确认唯一归类。 |
| 新材料 | T11277 | Thermal properties of materials | Physical Sciences | Materials Science | Materials Chemistry | 0.73 | review | 覆盖热管理材料，但也含较多基础热输运，需确认首页是否纳入。 |
| 新材料 | T11782 | Magnetic Properties of Alloys | Physical Sciences | Materials Science | Electronic, Optical and Magnetic Materials | 0.71 | review | 稀土永磁与高性能磁性合金相关，但 Topic 同时覆盖较宽的磁性材料与器件。 |
| 新材料 | T11737 | Advanced Materials and Mechanics | Physical Sciences | Engineering | Mechanical Engineering | 0.28 | rejected | Topic 名称宽泛且混合 4D 打印、软体机器人、水凝胶等多路线，无法作为稳定的新材料统计边界。 |
| 生物制造 | T10932 | Microbial Metabolic Engineering and Bioproduction | Life Sciences | Biochemistry, Genetics and Molecular Biology | Molecular Biology | 0.99 | approved | 直接覆盖微生物代谢工程、合成生物学、细胞工厂和生物生产。 |
| 生物制造 | T10404 | Enzyme Catalysis and Immobilization | Life Sciences | Biochemistry, Genetics and Molecular Biology | Molecular Biology | 0.92 | approved | 直接覆盖酶工程、固定化、生物催化与工业应用。 |
| 生物制造 | T11617 | Enzyme Production and Characterization | Life Sciences | Biochemistry, Genetics and Molecular Biology | Biotechnology | 0.88 | approved | 直接覆盖微生物酶生产、工业酶和极端微生物资源。 |
| 生物制造 | T12856 | Transgenic Plants and Applications | Life Sciences | Biochemistry, Genetics and Molecular Biology | Biotechnology | 0.91 | approved | 直接覆盖植物分子农场、重组蛋白和植物生物反应器。 |
| 生物制造 | T11190 | 3D Printing in Biomedical Research | Physical Sciences | Engineering | Biomedical Engineering | 0.86 | approved | 直接覆盖生物 3D 打印、生物墨水和组织制造。 |
| 生物制造 | T14285 | Biopolymer Synthesis and Applications | Life Sciences | Biochemistry, Genetics and Molecular Biology | Molecular Biology | 0.90 | approved | 明确覆盖微生物发酵合成生物聚合物及其应用。 |
| 生物制造 | T10171 | Biofuel production and bioconversion | Physical Sciences | Engineering | Biomedical Engineering | 0.72 | review | 覆盖生物转化与发酵制造，但也可归入新能源；需确定跨一级领域唯一归属。 |
| 生物制造 | T10864 | Fluid Dynamics and Mixing | Physical Sciences | Engineering | Biomedical Engineering | 0.68 | review | 与生物反应器放大、供氧和混合直接相关，但 Topic 名称和部分内容属于通用流体工程。 |
| 生物制造 | T10621 | Gene Regulatory Network Analysis | Life Sciences | Biochemistry, Genetics and Molecular Biology | Molecular Biology | 0.58 | review | 包含合成生物学与基因回路，但大量内容是基础网络分析，是否能代表制造需人工审核。 |
| 生物制造 | T10521 | RNA and protein synthesis mechanisms | Life Sciences | Biochemistry, Genetics and Molecular Biology | Molecular Biology | 0.12 | rejected | 主体是翻译与核糖体基础机制，合成生物学只是潜在应用，不能作为生物制造 Topic。 |
| 生物制造 | T10750 | Fermentation and Sensory Analysis | Life Sciences | Agricultural and Biological Sciences | Food Science | 0.20 | rejected | 虽含 fermentation，但主体是葡萄酒风味与感官分析，不代表平台型生物制造。 |

## 6. 官方层级元数据漂移

| Topic ID | 层级 | 映射文件记录 | 官方 v2 当前值 |
|---|---|---|---|
| `T10879` | subfield | Control and Systems Engineering | Biomedical Engineering |
| `T14335` | domain | Social Sciences | Physical Sciences |
| `T14335` | field | Social Sciences | Computer Science |
| `T14335` | subfield | Education | Artificial Intelligence |
| `T14285` | field | Immunology and Microbiology | Biochemistry, Genetics and Molecular Biology |
| `T14285` | subfield | Applied Microbiology and Biotechnology | Molecular Biology |
| `T10864` | field | Chemical Engineering | Engineering |
| `T10864` | subfield | Fluid Flow and Transfer Processes | Biomedical Engineering |

建议后续把 Topic 审核决定与层级元数据分开版本化：审核状态不因层级标签变化自动改变，但统计报告应记录所使用的 taxonomy release。

## 7. 覆盖与重复审计

- Topic ID 多重分配：**0**。
- 父级 Subfield 重合不等于重复计数，因为统计过滤使用互斥的 `primary_topic.id`。
- 内容交叉仍然存在，例如钙钛矿同时属于能源材料和光电材料语境；这是语义关联，不是同一 Work 在 primary_topic 口径下被同一 Topic ID 重复分配。
- 一个 Work 只有一个 `primary_topic` 用于本口径，因此多 Topic OR 查询的结果集合按 Work 去重；但分类器把跨学科 Work 归到哪个 primary Topic 仍会影响覆盖。

### 7.1 approved Topic 对官方 Subfield 的覆盖率

| 一级领域 | Subfield | 已纳入 / 官方 Topic | 覆盖率 |
|---|---|---:|---:|
| 人形机器人与具身智能 | Biomedical Engineering | 1/72 | 1.4% |
| 人形机器人与具身智能 | Control and Systems Engineering | 1/44 | 2.3% |
| 人形机器人与具身智能 | Artificial Intelligence | 1/77 | 1.3% |
| AI芯片与先进封装 | Electrical and Electronic Engineering | 2/117 | 1.7% |
| 新能源与储能 | Electrical and Electronic Engineering | 4/117 | 3.4% |
| 新能源与储能 | Electronic, Optical and Magnetic Materials | 1/17 | 5.9% |
| 新能源与储能 | Materials Chemistry | 1/69 | 1.4% |
| 新能源与储能 | Energy Engineering and Power Technology | 1/2 | 50.0% |
| 新材料 | Mechanical Engineering | 1/79 | 1.3% |
| 新材料 | Materials Chemistry | 2/69 | 2.9% |
| 新材料 | Electronic, Optical and Magnetic Materials | 1/17 | 5.9% |
| 新材料 | Polymers and Plastics | 1/14 | 7.1% |
| 新材料 | Inorganic Chemistry | 1/12 | 8.3% |
| 生物制造 | Molecular Biology | 3/135 | 2.2% |
| 生物制造 | Biotechnology | 2/8 | 25.0% |
| 生物制造 | Biomedical Engineering | 1/72 | 1.4% |

覆盖率显示：这些一级领域不是完整官方 Field/Subfield，而是跨官方节点抽取的自定义技术集合。规模差异有真实研究活跃度因素，也有 Topic 数量和覆盖范围差异，不能只看绝对值解释热度。

## 8. 数据限制

1. OpenAlex Topic 是对 Works 的分类，不是产业技术树；某些细粒度技术（Chiplet、VLA、灵巧手等）没有独立 Topic，只能被较宽 Topic 吸收，关键词关联不能直接替代稳定统计口径。
2. 官方 v2 分类器在 2026-10 更新；历史 Works 的 Topic 归类与 API 当前查询结果可能随 OpenAlex 修订而变化。
3. 本轮独立窗口查询反映 2026-11-18 查询时 OpenAlex 对历史发表窗口的当前收录，不是历史日期当时的收录快照。
4. `research_taxonomy.json` 适合产品导航，但其技术节点不与 OpenAlex Topic 一一对应，不能直接用于计数。
5. 现有 1,825 条快照仅适用于 mapping v1；任何 Topic 变更都需要新 mapping version 和完整 365 天重算。
