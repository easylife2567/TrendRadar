# TrendRadar · WSL 工作站部署包

把 TrendRadar 变成 7×24 常驻服务：systemd 三个单元 + cloudflared 公网发布。
设计依据：design/05（部署）、design/06（安全）、design/07（阶段验收）。

> **与 Docker 部署互斥**：docker compose 的 `WEBSERVER_PORT` 同样占 8080，
> 同一台机器请二选一（本包自检会拒绝占用端口）。

## 文件清单

| 文件 | 用途 |
|---|---|
| `install.sh` | 一键安装（7 步：前置检查 → uv sync → 渲染单元 → 生成 key → cloudflared 检测 → 启动 → 自检） |
| `uninstall.sh` | 卸载（保留 output/ 数据；`--purge-env` 连 key 一起删） |
| `backup.sh` | 打包 output/ + config/（验收要求：每次备份后实际恢复验证一次） |
| `smoke_api.sh` | API 冒烟测试（`--fixture` 本地自测 / 实机模式） |
| `trendradar-*.service(.timer)` | systemd 单元模板（install.sh 渲染 `@VAR@`） |
| `cloudflared-config.example.yml` | 隧道 ingress 参考（`/mcp`→3333，其余→8080） |

## 三单元拓扑

```
cloudflared ──> trendradar-web.service (127.0.0.1:8080, FastAPI, 单进程)
     │
     ├── trendradar-scheduler.timer ──> trendradar-scheduler.service (one-shot 管线, 每 15 分钟)
     └── (可选) trendradar-mcp.service (127.0.0.1:3333, MCP HTTP)
```

- **单进程声明（v1）**：限流与 AI 护栏在进程内存，web.service 不加 workers
- 管线在非活跃时段空转退出（D6），15 分钟周期成本可忽略
- timer `Persistent=true`：Windows 更新重启后错过的补跑一次

## 安装（WSL 工作站）

```bash
# 0. WSL 启用 systemd（一次性）：/etc/wsl.conf
#    [boot]
#    systemd=true
#    然后 Windows 侧 wsl.exe --shutdown 重开

# 1. 克隆 + 安装
sudo mkdir -p /opt && sudo git clone <repo-url> /opt/trendradar
cd /opt/trendradar
sudo bash deploy/wsl/install.sh                 # 加 --with-mcp 装 MCP 单元

# 2. 公网发布（cloudflared）
#    参考 cloudflared-config.example.yml：apt 装 cloudflared →
#    tunnel create → 写 /etc/cloudflared/config.yml → enable --now cloudflared
```

安装脚本会自动生成 API key 到 `/etc/trendradar/web.env`（root:600），
查看：`sudo cat /etc/trendradar/web.env`。前端调 POST 端点时带
`X-API-Key` 头。

## 冒烟测试

```bash
# 本地夹具模式（样例库映射为今天，隔离目录，跑完检查不误建库）
bash deploy/wsl/smoke_api.sh --fixture

# 实机模式（当天已跑过管线后）
bash deploy/wsl/smoke_api.sh http://127.0.0.1:8080

# 经域名（P0 验收要求）+ prod docs 检查
SMOKE_CHECK_PROD=1 bash deploy/wsl/smoke_api.sh https://你的域名
```

## 自愈验证（P0 验收项）

Windows 侧执行 `wsl.exe --shutdown`，等 30 秒后重开 WSL：
`systemctl is-active trendradar-web trendradar-scheduler.timer` 应全部
active，公网域名应恢复可访问。

## 与设计文档的偏差回填（design/07）

- 409（运行中再触发）契约码复用 `RATE_LIMITED`（03 §4 无 409 专属码）
- RSS 缺库返回 200 空列表而非 404（工具层 MCP 语义，前端空态卡等效）
- `/api/news/search` 用 `SearchTools.search_news_unified`（03 所写
  `search_news_by_keyword` 不存在，unified 为超集）
