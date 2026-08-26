# 02 · 总体架构与关键技术决策

> 上游文档：[01-goals.md](01-goals.md) · 下游：[03-api-design.md](03-api-design.md)、[04-frontend-design.md](04-frontend-design.md)、[05-deployment-wsl.md](05-deployment-wsl.md)

## 1. 架构总图

```
                         ┌─────────────────────────────┐
                         │        Cloudflare 边缘        │
                         │  DNS · TLS · WAF · 限流       │
                         │  （可选）Zero Trust Access    │
                         └──────────────┬──────────────┘
                                        │ 出站隧道（cloudflared 主动连接）
                 ┌──────────────────────┴──────────────────────┐
                 │            WSL 工作站（Ubuntu）               │
                 │                                              │
                 │  ┌────────────┐    ┌────────────────────┐   │
                 │  │ cloudflared │───▶│ trendradar-web     │   │
                 │  │  .service  │    │ 127.0.0.1:8080     │   │
                 │  └────────────┘    │  ASGI (FastAPI)    │   │
                 │         │          │  ├ /api/*  只读API  │   │
                 │         │          │  └ /      静态前端  │   │
                 │         │          └─────────┬──────────┘   │
                 │         │                    │ import       │
                 │         │          ┌─────────▼──────────┐   │
                 │         └─────────▶│ trendradar-mcp      │   │
                 │       /mcp 路径    │ 127.0.0.1:3333      │   │
                 │                    │ （现有 FastMCP）     │   │
                 │                    └────────────────────┘   │
                 │                                              │
                 │  ┌─────────────────────────────────────────┐ │
                 │  │ trendradar-scheduler.timer               │ │
                 │  │  每 15~30 分钟 oneshot:                  │ │
                 │  │  python -m trendradar（现有完整管线）      │ │
                 │  │  采集→AI分析→报告→推送→落库               │ │
                 │  └───────────────────────┬─────────────────┘ │
                 └──────────────────────────┼───────────────────┘
                                            │ 写入
                                            ▼
                              output/news/{date}.db  output/rss/{date}.db
                                            ▲
                                            │ 只读（mode=ro）
                              trendradar-web / mcp_server 共同消费
```

## 2. 八项关键技术决策

### D1 · Web 层是薄壳，业务逻辑全部复用 MCP 工具层 ⭐ 本设计的第一原则

**决策**：`web_server` 包**不实现**任何查询/分析逻辑，直接 import
`mcp_server/tools/` 下的类（`DataQueryTools`、`AnalyticsTools` 等）与
`mcp_server/services/`（`DataService`、`ParserService`、`CacheService`）。

**理由**（已核实的现状）：
- `AnalyticsTools`（[mcp_server/tools/analytics.py](../mcp_server/tools/analytics.py)，约 2600 行）已实现
  话题趋势、生命周期、爆火检测、趋势预测、平台对比、时期对比、关键词共现、聚合去重
- 工具方法返回 `Dict`（不是序列化字符串），天然可直接 JSON 化为 HTTP 响应
- MCP server 自己就是 `asyncio.to_thread(...)` 包同步工具（见
  [mcp_server/server.py:212](../mcp_server/server.py#L212)），Web 层照抄此模式即可

**推论（架构不变量）**：今后新功能一律先沉到 `mcp_server/tools|services` 层，
MCP 与 Web 作为两个消费者共享。**禁止**在 `web_server` 里出现直连 SQLite 的查询。
（唯一例外见 D7 的 AI 执行层，它本身就是新增的共享能力。）

**代价**：`mcp_server` 从"独立子系统"变为"共享业务层"，包名与位置名不副实。
接受暂不重命名（避免无谓 churn），在包 docstring 标注双重职责；
若未来第三方消费者出现再考虑抽出 `trendradar/services/`。

### D2 · 新建 `web_server` 顶层包，独立服务进程

```
web_server/
├── __init__.py
├── __main__.py        # CLI 入口：python -m web_server [--host --port]
├── app.py             # ASGI app 工厂 + 中间件（认证/日志/限流）
├── api/
│   ├── news.py        # 热榜/历史/搜索        → DataQueryTools
│   ├── topics.py      # 趋势/爆火/预测        → AnalyticsTools
│   ├── sentiment.py   # 情感分析（含AI执行）   → AnalyticsTools + trendradar.ai
│   ├── rss.py         # RSS 查询             → DataQueryTools
│   ├── system.py      # 状态/健康/手动触发     → SystemManagementTools
│   └── reports.py     # 历史报告文件服务
├── auth.py            # X-API-Key 校验（依赖注入）
├── ai_runner.py       # AI 执行通道（见 D7）
└── static/            # 前端构建产物（git 提交 dist，见 D4）
```

**决策**：与 `mcp_server` 平级的**独立进程**（`127.0.0.1:8080`），不合并进 MCP 进程。
`pyproject.toml` 增加 `[project.scripts] trendradar-web = "web_server.app:run"`，
与现有 `trendradar-mcp` 入口对称。

**理由**：生命周期不同（web 常驻高频、MCP 按需）；故障域隔离；
且现有 MCP 入口零改动。MCP 与 Web 在域名层由隧道统一（见 D8）。

### D3 · 框架：FastAPI

**决策**：采用 FastAPI（新增 1 个 pinned 依赖；starlette/uvicorn 反正已随
fastmcp 引入）。同步工具方法直接写成 `def` 端点，自动跑线程池，
与 MCP server 的 `asyncio.to_thread` 语义一致。

**理由**：自动 OpenAPI 文档（`/docs`）对产品化与前后端协作价值大；
pydantic 校验挡住脏参数；生态成熟。备选方案纯 Starlette（零新依赖）被否：
省一个依赖换来手写校验与文档，不值。

### D4 · 前端：Vue 3 + Vite + ECharts，构建产物入库

**决策**：源码放 `web_server/frontend/`（Vite 项目），构建产物输出到
`web_server/static/` **并提交 git**。

**理由**：
- "产品化"目标（04 文档的页面与图表复杂度）超出无构建模式的可维护范围
- ECharts 在中文生态/文档/时序图表现上最顺手；Vue 3 组合式 API 足够轻
- dist 入库使**部署侧可以完全不装 Node**（uv sync + systemd 即完事），
  保住"轻量部署"的项目立场；开发者改前端时本地 `npm run build`
- 沿用项目现有约定：**不用 TypeScript**（仓库现有 JS 均为 plain JS），
  样式用 design tokens 手写 CSS（延续 `docs/assets/style.css` 风格），
  i18n 复用 `docs/assets/i18n.js` 的字典模式重写为 Vue 版

### D5 · 数据访问铁律：存储域分离，新闻数据只读

**决策**：存储划分为两个域，规则不同：

| 存储域 | 内容 | 归属 | Web 进程权限 |
|---|---|---|---|
| **新闻数据域** | `output/news|rss/{date}.db` | 管线（scheduler 进程） | **严格只读**：一切连接 `file:...?mode=ro` |
| **工作台数据域** | `output/workbench/workbench.db`（Track B） | 工作台引擎 | 读写（经工作台服务层） |

**理由**：
- 根除 Web 层锁库导致管线写入失败的可能
- 读写分离让"Web 挂了不影响推送"成为结构保证
- **Track B 修正（2026-08-26）**：工作台（[08](08-workbench-design.md)）天然写密集
  （任务状态/勾选/产物索引）。若维持"Web 一律只读"的旧表述，届时必然
  被打破并污染新闻库。域分离让两个原则各自成立：
  新闻库的只读性永不妥协，工作台的写入有自己的家。
- 情感结果表 `ai_sentiment_results`（03 §6）按此修正归类为
  "工作台数据域的前身"，写在当日 news 库是过渡做法，Track B 落地时
  迁往独立库（迁移成本已在 03 标注）

**注意**：现有 `ParserService._read_from_sqlite` 用普通
`sqlite3.connect(path)` 打开--Phase 1 需给 `web_server` 侧加一个
只读连接开关（优先改 `ParserService` 增加 `readonly=True` 参数，
属于共享层小增强，符合 D1 的下沉原则）

### D6 · 调度：systemd timer 拉起现有管线，不写守护进程

**决策**：`trendradar-scheduler.timer` 定期（默认 `*:0/15`，可配）
oneshot 执行 `python -m trendradar`。

**理由**：调度器（[trendradar/core/scheduler.py](../trendradar/core/scheduler.py)）
本就是"每次运行解析当前时段 + `already_executed` 幂等判重"的被动触发设计；
Docker 部署也是同思路（supercronic 每 30 分钟跑一次，
见 [docker/entrypoint.sh](../docker/entrypoint.sh)）。timer 周期比 Docker 默认
更密（15 分钟），`rank_history` 粒度更细、趋势曲线更平滑，而管线在
非活跃时段自然空转，成本为零。**核心管线代码零改动。**

### D7 · 情感分析的 AI 执行通道（Web 层唯一新增的"业务"）

**现状**：`AnalyticsTools.analyze_sentiment()` 收集新闻并**生成结构化
AI 提示词**，但把执行留给调用方。MCP 场景下由 AI 客户端自己消化提示词。

**决策**：新增 `web_server/ai_runner.py`：
拿到 `analyze_sentiment()` 生成的提示词 -> 调 `trendradar/ai/client.py`
（litellm，读 `config.yaml` 的 `ai:` 段，与管线 AI 同一套配置与 key）->
结果 JSON（`json-repair` 兜底解析）-> 写入当日库新表 `ai_sentiment_results`
（表结构见 03 §6）-> 返回前端。

**护栏**：进程级 `asyncio.Semaphore(1)` 串行化；结果按
`(topic, date_range, prompt_hash)` 缓存（复用 `CacheService`，TTL 6h）+
落库去重；每日调用上限（默认 50 次，环境变量可调）。

**为什么放 web_server 而不下沉**：它是对 tools 层产物的"编排"而非新查询逻辑；
若未来 MCP 也要执行 AI 分析，再下沉为共享服务（D1 的例外条款）。

### D8 · 对外发布：Cloudflare Tunnel，一个域名两条路由

**决策**：`cloudflared` 以 systemd 服务常驻，配置路径路由：

```yaml
# /etc/cloudflared/config.yml（示意）
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/<tunnel-id>.json
ingress:
  - hostname: trendradar.<你的域名>
    path: ^/mcp.*$                    # MCP 端点保持原路径
    service: http://127.0.0.1:3333
  - hostname: trendradar.<你的域名>
    service: http://127.0.0.1:8080    # 其余全部 -> Web
  - service: http_status:404
```

**理由**：
- 家宽 CGNAT 下唯一现实解；零开端口、自动 TLS、免费
- 项目已在 CF 生态（Pages 静态站），域名复用同一账号
- WSL 的 NAT 网络/IP 漂移问题被彻底绕开（隧道从内向外发起）
- 绑定 `127.0.0.1`：服务不对局域网暴露，唯一入口是隧道（见 06）

**备选与否决**：frp（需自备公网 VPS，多养一台机器）；
Tailscale（优秀但只解决"自己访问"，不解决"对外发布"）；
公网 IP + 端口转发（家宽普遍不满足前提）。

### D9 · 一份产品三种形态：App 可单进程内嵌（Track B 声明，Track A 立即遵守）

**背景**：桌面 Release 版（[09-release-packaging.md](09-release-packaging.md)）
要求"下载即用"--一个进程同时干 Web 服务 + 管线调度 + 工作台引擎，
不能依赖 systemd/uvicorn 常驻假设。

**决策**（对 Phase 1 代码立即生效，成本≈0；将来返工成本高）：
1. App 以**工厂函数**构造：`create_app(mode: "local"|"server")`，
   模式决定是否挂载 setup 向导路由等信任相关的差异件
2. **调度器实现为线程组件**（可被本机模式拉起），systemd timer 只是
   工作站模式的"外部扳机"（D6 不变：管线本体仍是被动触发的
   `python -m trendradar`，单进程模式下由内部线程周期调用同一入口）
3. **数据根目录可配置**：`output/` 等路径解析集中到 config 层，
   桌面版落 OS 用户数据目录（09 §5），工作站版落 `/opt/trendradar`
4. **工作台预留**：`workbench/` 顶层包（Track B 排期时创建），
   遵守与 web_server 相同的薄壳原则：业务逻辑沉在 workbench 引擎层，
   Web 只是挂载其路由与页面

**理由**：Web 优先（SPA + API）的架构红利正在于此--桌面版 =
"本机跑一个只绑 127.0.0.1 的 Web 服务 + 一个壳"。壳可以是默认浏览器
（Jupyter 模式，最简）、pywebview 独立窗口，将来也可升级为 Electron 壳--
因为**壳只是"指向 localhost 的窗口 + 进程保姆"，打包后的 Python 单进程
（sidecar）才是本体，且三种壳通用**（详见 09 §2.1 壳策略阶梯）。
唯一要防的是 Phase 1~4 代码里长出 systemd/
路径硬编码的隐性耦合，故现在立此存照。

## 3. 请求流与数据流

**写路径（不变）**：
```
systemd timer → python -m trendradar → DataFetcher(热榜+RSS)
  → AI 分析/筛选/翻译 → 报告生成 → 通知推送 → StorageManager 写 output/{type}/{date}.db
```

**读路径（新增）**：
```
浏览器 → CF 边缘 → tunnel → trendradar-web
  → FastAPI 路由（def 端点，线程池）→ mcp_server/tools/*（Dict 返回）
  → ParserService（mode=ro 连接）→ output/{type}/{date}.db
  → JSON 响应（CacheService TTL 缓存热点查询）
```

**AI 路径（新增，唯一）**：
```
POST /api/analytics/sentiment/run
  → analyze_sentiment() 生成提示词 → ai_runner 调 trendradar/ai/client
  → json-repair 解析 → 落库 ai_sentiment_results → 响应
```

## 4. 失败与降级行为

| 组件故障 | 影响 | 行为 |
|---|---|---|
| scheduler 挂 | 数据停在旧时点 | web 照常服务旧数据；系统页红灯 + 下次采集时间超期提示 |
| web 挂 | 页面打不开 | 管线推送完全不受影响；systemd 自动拉起 |
| cloudflared 挂 | 外网不可达 | 本地 127.0.0.1 仍可用；CF 侧 5xx；systemd 拉起 |
| AI key 失效/欠费 | 情感分析失败 | 管线的 AI 推送同样失败（同配置）；web 情感端点返回明确错误码 |
| 某日库损坏/缺失 | 该日查询空 | tools 层现状即如此（返回空/None）；前端友好提示"该日无数据" |

## 5. 目录总览（改造后）

```
TrendRadar/
├── trendradar/          # 核心管线（不动）
├── mcp_server/          # MCP 服务 + 共享业务工具层（只增 readonly 参数类小改）
├── web_server/          # ★ 新增：Web API + 静态前端
│   ├── frontend/        #   Vue 3 + Vite 源码（开发时）
│   └── static/          #   构建产物（提交 git，部署侧免 Node）
├── workbench/           # ★ Track B 预留：工作台引擎（任务模型/文档生成/自有存储）
├── deploy/wsl/          # ★ 新增：安装脚本 + systemd 单元 + cloudflared 配置模板
├── config/              # 配置（不动；新增 web 段见 03 §7）
├── output/              # 数据（保留策略调为长期；Track B 追加 workbench/ 子域）
└── design/              # 本设计文档
```
