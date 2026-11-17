# 高校科研热点雷达网站 V1.1

这是 `university-research-radar` 的交互式查询界面。它支持：

- 自定义研究主题和观察时间；
- 中国高校与美国、欧洲高校同口径对照；
- 热点主题、等长历史基线和月度趋势；
- 高校参与分布；
- 候选课题组及其代表成果；
- CSV 下载和数据覆盖提示。
- Skill 配置实时同步、结构校验和备用快照回退。

## 运行模式

- 领域扫描：一次比较多个受控主题，分别计算中国、美国和欧洲的热点指标。
- 主题深挖：检索一个具体主题及自定义同义词、排除词，展示规模、趋势、高校和候选课题组；不生成没有比较基础的跨主题排名。

每次在线运行都会保存运行编号、实际检索式、地区、时间和返回量。失败运行不会覆盖上一次成功结果，页面会持续显示失败状态和旧结果提示。

## 热点口径

- 当前观察期与此前三个等长窗口分别向 OpenAlex 请求计数，不再从一个相关性样本拆分历史趋势。
- 近期加速度比较观察期最后四分之一与此前四分之三的日均产出。
- 综合热度展示动量、加速度、课题组广度、机构扩散、成果质量和产业关联六项分值，并单列计分覆盖率和数据置信度。
- 当前 OpenAlex 自动归属只能形成中/低置信度候选组，因此课题组广度和产业关联暂不自动赋分；缺失项留空，并按已有分项重新归一。
- 高校、课题组和质量结构来自受限成果样本；主题规模和历史变化来自独立窗口的接口完整命中数。

## 双层同步

网站默认读取：

`%USERPROFILE%\.agents\skills\university-research-radar`

也可以通过环境变量 `UNIVERSITY_RADAR_SKILL_ROOT` 指向其他位置。

- 配置层：`domain-profiles`、`taxonomies`、`quality-rubrics` 和 `source-profiles` 中的改动通过校验后自动热加载，并同步到 `skill_snapshot`。
- 逻辑层：`SKILL.md` 主流程发生变化时，网站显示“主流程待适配”，不会自动覆盖兼容基准。网页逻辑完成适配后运行 `python sync_skill_snapshot.py` 更新基准快照。
- 回退层：实时 Skill 缺失或校验失败时，网站使用 `skill_snapshot` 中最后一次有效配置。

## 运行

```powershell
.\.runtime-venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

浏览器打开 `http://localhost:8501`。

## 公司局域网部署

项目包含 `Dockerfile`、`docker-compose.yml`、SQLite 持久化和在线备份脚本。公司主机部署后，同一获准办公网段的同事可通过 `http://主机局域网IP:8501` 访问；不需要域名、云服务器、公网隧道或路由器端口映射。

完整的 Windows/Linux 部署、防火墙、备份恢复、代码更新和故障排查步骤见 [DEPLOYMENT_LAN.md](DEPLOYMENT_LAN.md)。生产环境将 `OPENALEX_API_KEY` 写入主机 `.env`，不要写入源代码或发送给其他人。

后续源码发布与公司主机一键更新见 [UPDATE_WORKFLOW.md](UPDATE_WORKFLOW.md)。更新脚本会先备份数据库，再拉取 GitHub 的 `main` 分支并重建网站。

历史运行数据保存在主机的 `persistent/data/radar.db`，备份保存在 `persistent/backups/`。重建容器不会删除这些目录；不要手工删除 `persistent/`。

V1.1 的科研实体库、热点算法、schema v2 迁移、测试与回滚说明见 [V1_1_RELEASE_NOTES.md](V1_1_RELEASE_NOTES.md)。

在线检索使用 OpenAlex。匿名访问被限流时，可在界面中填写免费的 OpenAlex API key。课题组归属默认是候选线索，正式报告仍需用高校官网或实验室成员页核验。
