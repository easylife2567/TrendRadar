# 03 · Web API 设计（只读为主）

> 上游文档：[02-architecture.md](02-architecture.md) · 下游：[04-frontend-design.md](04-frontend-design.md)
> 实现位置：`web_server/api/` 各路由模块（框架 FastAPI，见 D3）

## 1. 设计约定

**响应信封**：沿用 tools 层既有返回形态，HTTP 状态码 + 统一结构：

```jsonc
// 成功：200/202
{ "success": true, "data": { ... }, "cached": false, "generated_at": "..." }
// 失败：4xx/5xx
{ "success": false, "error": { "code": "DATE_NOT_FOUND", "message": "..." } }
```

**参数约定**：
- 日期一律 `YYYY-MM-DD`；跨日范围 `start` + `end`（含端点）
- 支持自然语言日期的便利参数 `range=last7d|this_week|last_week|...`
  （服务端调 `DateParser.resolve_date_range_expression`，复用
  [mcp_server/utils/date_parser.py](../mcp_server/utils/date_parser.py)，
  与 MCP `resolve_date_range` 工具同一实现，保证语义一致）
- `platforms=zhihu,weibo` 逗号分隔
- 分页统一 `limit`（默认/上限见各端点）+ `offset`

**执行模型**：所有端点为同步 `def`（FastAPI 自动入线程池），
内部直调 tools 层同步方法--与 MCP server 的 `asyncio.to_thread` 等价。

**缓存**：GET 端点默认走 `CacheService`（进程内 TTL）。
缓存键含全部查询参数；TTL 按端点分级（下表）。
响应带 `cached: true/false` 便于前端展示数据新鲜度。

**认证**：见 [06-security.md](06-security.md)。
读端点默认公开（可配置强制）；写/触发端点**必须** `X-API-Key`。

## 2. 端点总表

### 2.1 系统 · `web_server/api/system.py`

| 端点 | 方法 | 映射的现有实现 | 缓存 | 认证 |
|---|---|---|---|---|
| `/api/system/status` | GET | `SystemManagementTools.get_system_status` | 10s | - |
| `/api/system/dates` | GET | `StorageSyncTools.list_available_dates(source="local")` | 60s | - |
| `/api/system/schedule` | GET | 读 `config.yaml` 的 `schedule` 段 + 最近 `crawl_records` 推算下次运行 | 30s | - |
| `/api/system/health/sources` | GET | 当日库 `crawl_source_status` 表（今日各源成功/失败） | 60s | - |
| `/api/crawl/trigger` | POST | `SystemManagementTools.trigger_crawl`（轻量抓取，可 `save_to_local`） | 无 | 🔑 |
| `/api/pipeline/run` | POST | `systemd-run --unit=trendradar-manual-<ts> python -m trendradar`（完整管线，异步） | 无 | 🔑 |

`/api/pipeline/run` 返回 202 + 系统页轮询 `/api/system/status` 观察进度。
**注意**：两者语义不同必须分开--`trigger_crawl` 只拉数据（
[mcp_server/tools/system.py:201](../mcp_server/tools/system.py#L201)），
`pipeline/run` 才含 AI 分析与推送。实现上后者的启动命令经
`subprocess` + systemd transient unit（见 05 §3.4），
避免与 timer 并发执行（管线自身有 `already_executed` 判重，双跑安全但浪费）。

### 2.2 热榜与历史 · `web_server/api/news.py`

| 端点 | 方法 | 映射 | 缓存 |
|---|---|---|---|
| `/api/news/latest` | GET | `DataQueryTools.get_latest_news(platforms, limit, include_url)` | 60s |
| `/api/news/date/{date}` | GET | `DataQueryTools.get_news_by_date(date, platforms, limit)` | 5m |
| `/api/news/search` | GET | `DataQueryTools.search_news_by_keyword(keyword, platforms, date_range, limit)` | 5m |
| `/api/topics/trending` | GET | `DataQueryTools.get_trending_topics(top_n, mode, extract_mode)` | 120s |
| `/api/news/item/{date}/{id}/rank-history` | GET | 当日库 `rank_history` 表直查（**例外**：此查询 tools 层没有，需下沉到 `DataQueryTools` 新方法，遵守 D1） | 5m |

### 2.3 高级分析 · `web_server/api/topics.py`

| 端点 | 方法 | 映射 | 缓存 |
|---|---|---|---|
| `/api/analytics/topic-trend` | GET | `AnalyticsTools.analyze_topic_trend_unified(topic, date_range, ...)` | 10m |
| `/api/analytics/insights` | GET | `AnalyticsTools.analyze_data_insights_unified(...)` | 10m |
| `/api/analytics/viral` | GET | `AnalyticsTools.detect_viral_topics(...)` | 10m |
| `/api/analytics/predict` | GET | `AnalyticsTools.predict_trending_topics(...)` | 30m |
| `/api/analytics/compare-periods` | GET | `AnalyticsTools.compare_periods(period_a, period_b)` | 30m |
| `/api/analytics/compare-platforms` | GET | `AnalyticsTools.compare_platforms(...)` | 10m |
| `/api/analytics/aggregate` | GET | `AnalyticsTools.aggregate_news(...)` | 10m |

> 慢端点（predict/compare 常在数秒级）：FastAPI 线程池默认 40 并发，
> 另加全局限流中间件（见 06 §4）防止前端并发触发雪崩。

### 2.4 情感分析（AI 执行）· `web_server/api/sentiment.py`

| 端点 | 方法 | 说明 | 认证 |
|---|---|---|---|
| `/api/analytics/sentiment/prompt` | GET | `AnalyticsTools.analyze_sentiment(...)` 生成提示词（**不执行**，供高级用户取用） | - |
| `/api/analytics/sentiment/run` | POST | 提示词 -> `ai_runner` -> litellm -> 落库 -> 返回结果 | 🔑 |
| `/api/analytics/sentiment/results` | GET | 查询历史情感分析结果（库表，按 topic/日期过滤） | - |

`run` 请求体：`{ topic?, platforms?, range?|start?+end?, limit? }`。
护栏（D7）：`Semaphore(1)` 串行；`(topic, range, prompt_hash)` 缓存 6h；
每日上限默认 50 次（`TRENDRADAR_SENTIMENT_DAILY_LIMIT`）。返回 429 附
`Retry-After`。执行耗时数秒到数十秒--前端按异步任务处理（提交后轮询
results 或 SSE，v1 用轮询即可）。

### 2.5 RSS · `web_server/api/rss.py`

| 端点 | 方法 | 映射 | 缓存 |
|---|---|---|---|
| `/api/rss/latest` | GET | `DataQueryTools.get_latest_rss(...)` | 60s |
| `/api/rss/search` | GET | `DataQueryTools.search_rss(...)` | 5m |
| `/api/rss/feeds-status` | GET | `DataQueryTools.get_rss_feeds_status()` | 120s |

### 2.6 报告归档 · `web_server/api/reports.py`

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/reports` | GET | 列出 `output/` 下已生成报告（日期、类型、大小） |
| `/api/reports/{date}/html` | GET | 返回当日 HTML 报告原文（`Content-Type: text/html`，iframe 嵌入用） |

**安全约束**：路径穿越防护（date 参数严格 `^\d{4}-\d{2}-\d{2}$`，
`Path.resolve()` 后必须仍在 `output/` 下）；只暴露白名单扩展名
（.html/.txt/.png）。**绝不**暴露 `config/`、`.env`、任意路径。

### 2.7 静态前端

`GET /` 与 `GET /assets/*` 由 FastAPI `StaticFiles` 挂载
`web_server/static/`（SPA history 模式，fallback 到 index.html）。

## 3. 认证与中间件链

```
请求 -> CORS(默认关闭，同源部署无需)
      -> 限流中间件（令牌桶：IP 级 60 req/min；/api/analytics/* 更严）
      -> API Key 中间件：
           🔑 端点：必须 X-API-Key，恒定时间比较
           读端点：TRENDRADAR_REQUIRE_READ_KEY=1 时才强制（默认关，见 06）
      -> 路由
```

API Key 来源：`web_server` 启动时读环境变量 `TRENDRADAR_API_KEY`
（不落 config.yaml，避免密钥进可编辑配置文件）。

## 4. 错误码约定

| code | HTTP | 场景 |
|---|---|---|
| `BAD_REQUEST` | 400 | 参数校验失败 |
| `UNAUTHORIZED` | 401 | 缺/错 API Key |
| `RATE_LIMITED` | 429 | 限流/每日上限 |
| `DATE_NOT_FOUND` | 404 | 查询日期无库文件 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `AI_EXECUTION_FAILED` | 502 | litellm 调用失败（透传原因摘要，不透 key） |
| `INTERNAL_ERROR` | 500 | 兜底 |

## 5. OpenAPI

FastAPI 自动生成 `/docs`（Swagger UI）。**对外发布时关闭**：
`TRENDRADAR_ENV=prod` 时 `docs_url=None`，仅本地调试可见（见 06 §5）。

## 6. 新增存储：`ai_sentiment_results` 表

情感分析结果需要可回看（US-5），在**当日 news 库**追加（不建独立库，
与按日分库一致；由 web 进程写入--这是 D5「Web 只读」的唯一例外，
表的写入路径收敛在 `ai_runner` 一处，其余端点仍严格只读）：

```sql
CREATE TABLE IF NOT EXISTS ai_sentiment_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL DEFAULT '',            -- 空串 = 全量话题
    date_start TEXT NOT NULL,
    date_end   TEXT NOT NULL,
    platforms  TEXT DEFAULT '',                -- 逗号分隔，空 = 全部
    prompt_hash TEXT NOT NULL,                 -- 提示词指纹，判重
    result_json TEXT NOT NULL,                 -- AI 输出（正/负/中比例+代表标题+摘要）
    model TEXT NOT NULL,                       -- 使用的模型标识
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic, date_start, date_end, platforms, prompt_hash)
);
```

写入用独立连接、`BEGIN IMMEDIATE`、失败即弃（缓存层仍会命中），
保证不阻塞管线主写入。

> **存储域归属标注（02-D5 修正案）**：本表是"工作台数据域"的过渡形态
> （Track A 阶段的唯一写例外）。Track B 落地 `workbench.db` 时，
> 此表**迁移**到独立库（web 层提供一次性迁移：读旧表 -> 写新库 ->
> 旧表停写）。接口语义不变，前端无感。

## 7. 配置：`config.yaml` 新增 `web` 段

```yaml
web:
  enabled: true
  host: 127.0.0.1          # 默认仅本机/隧道可达；显式 0.0.0.0 才对局域网开放
  port: 8080
  require_read_key: false  # true = 读端点也要 X-API-Key
  cache_ttl_overrides:     # 可选，覆盖默认 TTL（秒）
    "/api/topics/trending": 120
```

与现有配置风格一致（顶层小写段）。API Key **不**放这里（见 §3）。

## 8. Phase 1 需要的共享层增强（都符合 D1 下沉原则）

| 改动 | 位置 | 内容 |
|---|---|---|
| 只读连接 | `ParserService` | `sqlite3.connect("file:...?mode=ro", uri=True)` 开关 |
| 排名历史查询 | `DataQueryTools` | 新增 `get_rank_history(date, news_id)`（读 `rank_history` 表） |
| 下次运行推算 | `SystemManagementTools` | 新增 `get_next_schedule_run()`（读 schedule 配置 + 最近 crawl_records） |
| 情感结果读写 | `DataService` 或新 `SentimentStore` | §6 表的读写方法（供 web 与未来 MCP 共用） |

## 9. 工作台 API（Track B · 已声明未排期）

仅立契约占位，详见 [08-workbench-design.md](08-workbench-design.md) §6。
实现时新建 `web_server/api/workbench.py` 路由模块，业务逻辑全部位于
`workbench/` 引擎包（薄壳原则不变），存储走工作台数据域（D5）：

```
GET  /api/wb/tasks                          任务模板列表
GET  /api/wb/tasks/{id}/instances/{date}    某日实例（状态机当前态）
POST /api/wb/instances/{id}/select          提交勾选                🔑
POST /api/wb/instances/{id}/summarize       触发 AI 摘要（异步）     🔑
PUT  /api/wb/instances/{id}/draft           保存人工编辑            🔑
POST /api/wb/instances/{id}/generate        生成 docx/pdf + 入池     🔑
GET  /api/wb/instances/{id}/artifacts/{f}   下载产物（走 03 §2.6 同款路径防护）
GET  /api/wb/pool                           资源池查询
POST /api/wb/pool/export                    重生成 Excel 镜像        🔑
```

另：桌面本机模式的 `POST /api/setup/*` 首启向导路由**只在 local 模式
挂载**（09 §4），工作站/Docker 模式下不存在。
