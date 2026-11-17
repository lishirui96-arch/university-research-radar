# 源代码与局域网网站更新流程

## 更新链路

```text
本地修改 -> 测试 -> GitHub 私有仓库 main 分支 -> 公司主机备份数据库 -> 拉取并重建网站
```

GitHub 只保存源码和配置模板。以下内容始终留在公司主机：

- `.env` 与 `OPENALEX_API_KEY`；
- `persistent/data/radar.db`；
- `persistent/backups/`；
- 虚拟环境、测试数据和本地缓存。

## 开发端发布源码

确认测试通过后执行：

```powershell
git status
git add -A
git commit -m "说明本次更新"
git push origin main
```

## Windows 公司主机更新网站

在项目目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_windows.ps1
```

## Linux 公司主机更新网站

首次赋予脚本执行权限，然后运行：

```bash
chmod +x scripts/update_linux.sh
./scripts/update_linux.sh
```

脚本按以下顺序执行：

1. 拒绝覆盖公司主机上未提交的源码改动；
2. 调用 SQLite Backup API 创建在线备份；
3. 仅接受 `main` 分支的快进更新，拒绝自动合并冲突；
4. 重新构建并创建容器；
5. 显示容器与健康状态。

更新失败时，数据库和 `.env` 不会被 Git 操作覆盖。恢复方法见 `DEPLOYMENT_LAN.md`。

## 自动更新说明

公司内网主机不开放公网入站端口，因此 GitHub 不能主动连接主机。若以后需要无人值守自动更新，可由公司 IT 使用 Windows 任务计划程序或 Linux systemd timer 定期运行上述脚本。启用前应先确定维护时间窗口，避免正在查询时重启网站。
