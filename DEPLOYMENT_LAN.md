# 高校科研热点雷达：公司局域网部署手册

## A. 当前项目检查报告

| 检查项 | 实际情况 |
|---|---|
| 应用入口 | `streamlit_app.py`。Dockerfile 通过 `python -m streamlit run streamlit_app.py` 启动。 |
| 依赖管理 | `requirements.txt`，包含 Streamlit、Pandas、Altair 和 Requests。 |
| Dockerfile | 已存在并设置 `0.0.0.0:8501`、健康检查和无界面运行。 |
| Docker Compose | 本次新增 `docker-compose.yml`，单 Web 容器、`restart: unless-stopped`。 |
| 数据库 | 原项目没有数据库，结果只存在浏览器会话。本次新增 SQLite：`persistent/data/radar.db`。 |
| OpenAlex 调用 | `radar.py` 使用 Requests 调用 `https://api.openalex.org/works`，包含重试和限流提示。 |
| 采集调度 | 没有定时器、cron、APScheduler 或后台采集进程。采集仅由用户提交页面表单触发。 |
| 数据库并发 | 新增 `storage.py`；每次操作使用独立连接、WAL、外键、30 秒 busy timeout 和短事务。 |
| API Key | `streamlit_app.py` 从 `OPENALEX_API_KEY` 环境变量读取；不会写入前端、数据库或日志。 |
| 缓存 | `st.cache_data` 是可丢弃的运行缓存；不作为历史数据来源。历史运行、指标和检索日志写入 SQLite。 |
| 静态数据 | `data/` 与 `skill_snapshot/` 随镜像发布；数据库和备份不写入镜像。 |

数据库表包括：

- `scan_runs`：运行状态、范围和错误；
- `scan_topic_metrics`：每次成功运行的主题指标；
- `scan_query_log`：实际 OpenAlex 检索式、地区、返回量和样本量；
- `schema_metadata`：数据库结构版本。

当前没有定时采集任务，因此不存在多容器重复执行调度器的问题。不要使用 `docker compose up --scale radar=...`；本方案固定运行一个 Web 容器。

## B. Docker 与 Compose

完整文件已经保存在项目根目录：

- `Dockerfile`
- `docker-compose.yml`

`Dockerfile` 完整内容：

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["python", "-m", "streamlit", "run", "streamlit_app.py"]
```

`docker-compose.yml` 完整内容：

```yaml
name: university-research-radar

services:
  radar:
    build:
      context: .
      dockerfile: Dockerfile
    image: university-research-radar:local
    container_name: university-research-radar
    restart: unless-stopped
    init: true
    env_file:
      - .env
    environment:
      RADAR_DB_PATH: /app/persistent/data/radar.db
      RADAR_BACKUP_DIR: /app/persistent/backups
      RADAR_BACKUP_RETENTION: ${RADAR_BACKUP_RETENTION:-30}
      TZ: ${TZ:-Asia/Singapore}
      STREAMLIT_SERVER_ADDRESS: 0.0.0.0
      STREAMLIT_SERVER_PORT: 8501
      STREAMLIT_SERVER_HEADLESS: "true"
      STREAMLIT_SERVER_RUN_ON_SAVE: "false"
      STREAMLIT_BROWSER_GATHER_USAGE_STATS: "false"
      HOME: /tmp
    ports:
      - "${RADAR_BIND_ADDRESS:-0.0.0.0}:8501:8501"
    volumes:
      - type: bind
        source: ./persistent/data
        target: /app/persistent/data
      - type: bind
        source: ./persistent/backups
        target: /app/persistent/backups
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)
      interval: 30s
      timeout: 5s
      start_period: 30s
      retries: 3
    stop_grace_period: 30s
    read_only: true
    tmpfs:
      - /tmp:size=256m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
```

Compose 将以下主机目录映射进容器：

```text
./persistent/data     -> /app/persistent/data
./persistent/backups  -> /app/persistent/backups
```

重新创建、升级或删除容器不会删除这些主机目录。不要运行 `docker compose down -v`，也不要手工删除 `persistent/`。

## C. 环境变量

在主机项目目录执行：

```powershell
Copy-Item .env.example .env
notepad .env
```

填入真实密钥：

```dotenv
OPENALEX_API_KEY=你的真实密钥
RADAR_BIND_ADDRESS=0.0.0.0
RADAR_BACKUP_RETENTION=30
TZ=Asia/Singapore
```

`.env` 已加入 `.gitignore` 和 `.dockerignore`。不要截图、上传或发送该文件。

## D. Windows 主机部署

### 前提

1. 安装 Docker Desktop，并启用 WSL 2 后端。
2. 确认公司对 Docker Desktop 的商业许可政策。
3. 将本项目完整复制到长期运行主机的固定目录，例如 `C:\CompanyApps\university-research-radar`。
4. 在 Docker Desktop 设置中启用“登录时启动 Docker Desktop”。

### 首次启动

以 PowerShell 进入项目目录：

```powershell
Copy-Item .env.example .env
notepad .env
New-Item -ItemType Directory -Force persistent\data, persistent\backups
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail 100 radar
```

健康状态应最终变为 `healthy`。主机本机访问：

```text
http://localhost:8501
```

### Windows 防火墙仅允许局域网

先确定公司局域网网段，例如 `192.168.10.0/24`，然后以管理员 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\configure_windows_firewall.ps1 -LanSubnet 192.168.10.0/24
```

脚本拒绝明显的非私有网段。确认 Windows 当前网络配置文件为 `Private`：

```powershell
Get-NetConnectionProfile
```

不要在公司路由器上配置端口映射、UPnP 或 DMZ。

Windows 防火墙通常默认阻止未获准的入站连接。请同时检查没有其他规则向任意来源开放 8501：

```powershell
Get-NetFirewallRule -Enabled True -Direction Inbound |
  Get-NetFirewallPortFilter |
  Where-Object {$_.LocalPort -eq '8501'}
```

## Linux 主机部署

安装 Docker Engine 和 Compose 插件后：

```bash
cd /opt/university-research-radar
cp .env.example .env
chmod 600 .env
mkdir -p persistent/data persistent/backups
sudo chown -R "$USER":"$USER" persistent
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail 100 radar
```

只允许局域网网段访问，例如：

```bash
sudo sh scripts/configure_ufw.sh 192.168.10.0/24
```

如果 UFW 尚未启用，先审查现有 SSH 和管理端口规则；不要在远程会话中直接启用默认拒绝策略，以免锁死主机。

确认 UFW 的入站默认策略为拒绝，并且 8501 只有指定私有网段的允许规则：

```bash
sudo ufw status verbose
```

## E. 查询主机局域网 IP

Windows：

```powershell
Get-NetIPConfiguration |
  Where-Object {$_.IPv4DefaultGateway} |
  Select-Object InterfaceAlias,@{Name='IPv4';Expression={$_.IPv4Address.IPAddress}}
```

也可运行 `ipconfig`，查看当前办公网络适配器的 IPv4 地址。忽略 `127.0.0.1`、Docker、WSL、VPN 和虚拟网卡地址。

Linux：

```bash
ip -4 route get 1.1.1.1
hostname -I
```

建议在公司 DHCP 或路由器中为主机设置地址保留，避免 IP 变化。

## F. 同事访问方式

假设主机局域网 IP 是 `192.168.10.25`，同一局域网的电脑和手机访问：

```text
http://192.168.10.25:8501
```

访问条件：

- 设备连接公司同一局域网或公司允许互访的办公 VLAN；
- 无线网络未启用客户端隔离；
- 防火墙规则包含访问设备所在网段；
- 容器状态为 `healthy`。

## G. 主机不休眠与 Docker 自动启动

Windows 管理员 PowerShell，仅修改接通电源状态：

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

Docker Desktop 启用登录时启动。普通 Windows 工作站重启后通常仍需要用户登录，Docker Desktop 才会完全启动；若要求无人值守重启恢复，优先使用 Linux 主机，或由公司 IT 配置专用服务账号和合规的启动任务。

Linux：

```bash
sudo systemctl enable --now docker
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Compose 的 `restart: unless-stopped` 会在 Docker 服务恢复后自动启动容器。

## H. 数据库备份与恢复

### 在线备份

备份脚本使用 SQLite 官方 Backup API，可在网站运行时安全执行：

```powershell
docker compose exec -T radar python scripts/backup_database.py
```

备份写入 `persistent/backups/radar-YYYYMMDD-HHMMSS.db`，默认保留最近 30 份。可以用 Windows 任务计划程序或 Linux cron 每日执行该命令。备份目录应另外复制到公司受控文件服务器或备份介质；只留在同一硬盘不算完整备份。

Windows 可在“任务计划程序”中新建每日任务：使用部署主机的专用运行账号，程序设为 `docker`，参数设为 `compose exec -T radar python scripts/backup_database.py`，“起始于”设为项目绝对路径。启用“无论用户是否登录都运行”，并先手工运行一次确认结果出现在 `persistent\backups`。

Linux 可执行 `crontab -e`，每天 02:15 备份（替换为实际项目路径）：

```cron
15 2 * * * cd /opt/university-research-radar && /usr/bin/docker compose exec -T radar python scripts/backup_database.py >> persistent/backups/backup.log 2>&1
```

只在主机层配置一个备份任务，不要在多个容器中各自配置调度器。

### 恢复

恢复前先停止应用并保留当前数据库：

Windows PowerShell：

```powershell
docker compose stop radar
Copy-Item persistent\data\radar.db persistent\backups\radar-before-restore.db
Copy-Item -Force persistent\backups\radar-20261117-020000.db persistent\data\radar.db
Remove-Item -ErrorAction SilentlyContinue persistent\data\radar.db-wal, persistent\data\radar.db-shm
docker compose up -d
```

Linux：

```bash
docker compose stop radar
cp persistent/data/radar.db persistent/backups/radar-before-restore.db
cp persistent/backups/radar-20261117-020000.db persistent/data/radar.db
rm -f persistent/data/radar.db-wal persistent/data/radar.db-shm
docker compose up -d
```

将示例备份文件名替换为实际文件。不要在容器仍运行时直接覆盖数据库。

## I. 更新代码且不丢失数据库

更新前先备份：

```powershell
docker compose exec -T radar python scripts/backup_database.py
```

替换代码后：

```powershell
docker compose build --pull
docker compose up -d --force-recreate
docker compose ps
docker compose logs --tail 100 radar
```

数据库和备份位于主机 `persistent/`，不会被镜像构建或容器重建覆盖。不要把旧项目目录整体删除后重新解压；至少先独立保存 `.env` 和 `persistent/`。

## J. 多人访问测试与故障排查

### 多人测试

1. 主机浏览器打开 `http://localhost:8501`。
2. 两台电脑和一部手机同时打开局域网地址。
3. 分别执行不同主题查询。
4. 检查页面没有数据库锁错误。
5. 运行：

```powershell
docker compose exec -T radar python -c "from storage import database_summary; print(database_summary())"
```

6. 重启容器后复查数据库统计仍存在：

```powershell
docker compose restart radar
docker compose exec -T radar python -c "from storage import database_summary; print(database_summary())"
```

### 常用排查

```powershell
docker compose ps
docker compose logs --tail 200 radar
docker inspect --format '{{json .State.Health}}' university-research-radar
Test-NetConnection localhost -Port 8501
Test-NetConnection 192.168.10.25 -Port 8501
```

常见问题：

- 主机可访问、同事不可访问：检查 Windows/UFW、防火墙网段、无线客户端隔离和 VLAN 策略。
- 容器反复重启：查看日志，确认 `.env` 格式和持久化目录可写。
- OpenAlex 限流：确认 `.env` 中设置了有效 API Key；不要在网页、日志或聊天中粘贴密钥。
- 数据库锁：确认只有一个 `radar` 容器；不要把 SQLite 放到 SMB/NFS 网络共享盘。
- 主机重启后未恢复：检查 Docker 是否自动启动，Windows 是否需要登录。

## 网络安全边界

- Compose 监听主机端口是为了局域网访问；真正的来源限制由主机防火墙按私有网段执行。
- 不设置路由器端口映射、UPnP、DMZ、反向代理公网地址或公网隧道。
- 若公司存在访客 Wi-Fi、跨 VLAN 路由或零信任代理，由公司 IT 确认访问控制策略。
- 当前应用没有用户登录功能；同一获准网段内的设备均可访问。若公司要求按员工身份认证，需要另行增加内网反向代理与 SSO。
