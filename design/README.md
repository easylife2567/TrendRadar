# TrendRadar Web 舆情监测中心 — 设计文档

> 状态：**设计已定稿（2026-08-26 用户确认），待实施** · 创建日期：2026-08-26
> 目标：把 TrendRadar 从「推送工具」升级为「AI 舆情监测中心」产品，
> 以 WSL 工作站作为常驻服务节点，通过 Cloudflare Tunnel 对外发布。
>
> **双轨扩展（2026-08-26 追加声明）**：Track B 实验室工作台（人机协作
> 任务引擎，参考场景"国际日报"）+ Release 发行版（下载即用）。
> 已声明未排期，但三处架构级修正已回灌 Track A 设计（见 02 的 D5 修正
> 与新增 D9）。

## 一页纸总览

**现状**：后端能力已经齐备——多平台热榜 + RSS 采集、AI 分析/翻译/筛选、
10+ 推送渠道、按日 SQLite 历史库（含排名变化、标题改动、源健康度），
且 `mcp_server/` 里已经沉淀了一整套查询与分析工具层。
**缺口**：没有任何 Web 层消费这些数据；调度是被动触发式，无常驻服务。

**核心结论**：Web 层应当是**薄壳**——新建 `web_server` 包对外提供只读
REST API + 前端页面，业务逻辑**全部复用** `mcp_server/tools/` 与
`mcp_server/services/`，不在 Web 层重写任何查询/分析逻辑。

**部署形态**：

```
互联网用户
   │ HTTPS
   ▼
Cloudflare 边缘（域名 / WAF / 限流 / 可选 Access 认证）
   │ Cloudflare Tunnel（出站隧道，零开端口，穿 CGNAT）
   ▼
WSL 工作站（Ubuntu + systemd）
   ├── cloudflared.service        隧道客户端
   ├── trendradar-web.service     Web API + 前端（127.0.0.1:8080）
   ├── trendradar-mcp.service     MCP Server（127.0.0.1:3333，可选）
   └── trendradar-scheduler.timer 定期拉起 python -m trendradar 完整管线
```

## 文档索引

| 文档 | 内容 | 关心什么读它 |
|---|---|---|
| [01-goals.md](01-goals.md) | 产品定位、用户故事、非目标、路线图 | 想知道"做什么、不做什么" |
| [02-architecture.md](02-architecture.md) | 总体架构、八项关键技术决策、数据流 | 想知道"系统怎么搭、为什么这么搭" |
| [03-api-design.md](03-api-design.md) | REST API 契约、与现有工具层的映射 | 想写后端 / 对接前端 |
| [04-frontend-design.md](04-frontend-design.md) | 信息架构、八个页面、图表与组件设计 | 想写前端 |
| [05-deployment-wsl.md](05-deployment-wsl.md) | WSL 工作站部署：systemd、cloudflared、安装脚本 | 想把服务跑起来 |
| [06-security.md](06-security.md) | 信任边界、认证、只读原则、威胁清单 | 关心对外暴露的安全 |
| [07-implementation-plan.md](07-implementation-plan.md) | Phase 0–4 任务分解与验收标准 | 想开工排期 |
| [08-workbench-design.md](08-workbench-design.md) | 🅱 实验室工作台：任务引擎、国际日报参考场景、文档生成栈 | 想了解 Track B 愿景 |
| [09-release-packaging.md](09-release-packaging.md) | 🅱 Release 发行版：运行模式、壳策略阶梯（浏览器/pywebview/Electron）、首启向导、打包流水线 | 关心"下载即用"形态 |
| [10-ui-style-guide.md](10-ui-style-guide.md) | UI 风格规范：情报终端设计语言、色彩/字体/间距 tokens、组件与图表规范、AI 可信度视觉协议 | 写前端时随手查 |

## 路线图摘要

| 阶段 | 内容 | 验收标志 |
|---|---|---|
| Phase 0 | WSL 地基：systemd、uv 环境、隧道、占位页 | 公网域名能打开页面 |
| Phase 1 | 只读 API 薄壳（复用 tools 层） | 核心查询端点可用，带 API key |
| Phase 2 | MVP 前端：仪表盘/热榜/搜索/历史 | 日常看热点不再依赖推送 |
| Phase 3 | 监测中心能力：话题追踪/情感/对比/预测 | "舆情监测"名副其实 |
| Phase 4 | 产品化：认证完善、告警订阅、i18n、备份 | 可以给外人用 |
| Phase 5 🅱 | 工作台 MVP：国际日报跑通全流程 | 实验室日报零手工搜集 |
| Phase 6 🅱 | Release 发行版：桌面打包 + 首启向导 | 实验室同学下载即用 |

> 🅱 Phase 5/6 属 Track B：**已声明、未排期**。Track A（Phase 0–4）
> 范围不受影响，但架构上已为 Track B 预留（02-D5 修正、02-D9）。

## 本设计依据的代码事实（已核实）

- `mcp_server/tools/` 有 8 个工具类，其中 `AnalyticsTools`（约 2600 行）已实现
  话题趋势、生命周期、爆火检测、趋势预测、平台对比、时期对比、关键词共现、跨平台聚合去重
- `mcp_server/tools/analytics.py` 的 `analyze_sentiment()` 只**生成 AI 提示词**，
  不执行 AI 调用——Web 层需补上「AI 执行」这一步（复用 `trendradar/ai/client.py`）
- `mcp_server/tools/system.py` 的 `trigger_crawl()` 是轻量抓取（DataFetcher 直取），
  不走 AI 分析/推送的完整管线——两者在 API 里要分开提供
- `mcp_server/services/` 已有 `DataService`、`ParserService`、`CacheService`（TTL 缓存）
- 数据存储为按日分库：`output/news/{YYYY-MM-DD}.db`、`output/rss/{YYYY-MM-DD}.db`，
  schema 含 `news_items / rank_history / title_changes / crawl_source_status / push_records`
- `pyproject.toml` 已依赖 `fastmcp==2.12.5`（底层 Starlette + uvicorn，ASGI 栈现成）
- 调度器（`trendradar/core/scheduler.py`）为**被动触发式**：每次运行解析当前时段并幂等执行，
  `already_executed` 判重——天然适配 systemd timer 定期拉起，无需改造成守护进程
- 数据保留默认 0 = 无限制（`StorageManager` 的 `local_retention_days`）
- Docker 部署里的 "webserver" 只是 `python -m http.server` 托管静态报告，无 API
