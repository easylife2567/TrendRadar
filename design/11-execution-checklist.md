# 11 · 实施执行清单（随做随记的活文档）

> 依据 07（阶段计划）+ 实施计划（web-v0.x 多会话执行版）。
> 每步完成回填：日期、commit、验证口径。偏差统一记入 07 对应 Phase 的
> 「实际偏差回填」小节。

## Phase 0+1 · P1 代码侧（本机 macOS）——已完成 ✅

| Step | 内容 | 状态 | commit / 验证 |
|---|---|---|---|
| 0 | 工程准备：fastapi/uvicorn 依赖、.gitignore、config web 段、uv lock | ✅ | `f7d7743d`；uv lock 解析通过（fastmcp 2.12.5 × fastapi starlette 0.48 兼容） |
| 1 | web_server 骨架：settings/errors/envelope/cache/ratelimit/auth/logging_mw/app/__main__ + 占位路由 + hatchling packages | ✅ | `f7d7743d`；`create_app("local"/"server")`、三中间件顺序 AccessLog→RateLimit→Auth |
| 2 | 共享层增强：ParserService readonly + get_rank_history/get_source_health/get_keyword_hit_series/get_last_crawl_time、DataService 透传、get_next_schedule_run 三态、tools_registry | ✅ | `ae8f2e8e`；真实样例库 10/10（rank 11 点、健康度 22 次采集、21 小时桶）；缺库永不误建 |
| 3 | 认证接线：POST 一律 fail-closed、GET 受 TRENDRADAR_REQUIRE_READ_KEY 控制、双保险依赖 | ✅ | `f7d7743d` 内；401/401/200 实测（注意 env 名无 WEB：`TRENDRADAR_REQUIRE_READ_KEY`） |
| 4 | 只读路由 + 缓存：system/news/topics/rss 19 端点、TTL 分级、白名单投影 | ✅ | `dc10e878`；TestClient fixture 29/29；`TRENDRADAR_DATA_ROOT` 隔离验证 |
| 5 | 写路径与文件服务：reports 三重防护、crawl trigger 409、pipeline/run 202/409、限流桶生效 | ✅ | `3a4d846b`；429 实测 analytics 第 11 次 + Retry-After |
| 6 | 自测与部署包：deploy/wsl 全套（3 单元模板+install/uninstall/backup/smoke+README）、prod 关 docs、tag web-v0.1 | ✅ | `7fd21c46`；smoke --fixture 24/24 全绿；prod /docs /redoc 404；MCP 回归 8 实例构造正常 |
| — | 补提交：DataQueryTools 三系统查询包装（Step 2 遗漏） | ✅ | `4e74b1ca` |

**tag `web-v0.1` @ `7fd21c46`**（P1 代码侧完成点）

## Phase 0 · P0 实机侧（用户在 WSL 工作站执行）

- [ ] `/etc/wsl.conf` 启 systemd（`[boot] systemd=true`）→ `wsl.exe --shutdown` 重开
- [ ] clone 至 /opt/trendradar → `uv sync --locked`
- [ ] 手动 `python -m trendradar` 跑通一轮（产出今日库）
- [ ] `sudo bash deploy/wsl/install.sh`（可加 `--with-mcp`）→ 自检全绿
- [ ] cloudflared：apt 装 → `tunnel create` → `/etc/cloudflared/config.yml`（参考 deploy/wsl/cloudflared-config.example.yml）→ enable --now
- [ ] 公网域名 HTTPS 打开 `/` 占位 + 手机 4G 再验（排除局域网假象）
- [ ] 破坏性自愈：`wsl.exe --shutdown` 等 30s 重开 → 三单元 is-active 全 active、域名恢复
- [ ] 实机 smoke 两遍：`bash deploy/wsl/smoke_api.sh http://127.0.0.1:8080` + `SMOKE_CHECK_PROD=1 bash deploy/wsl/smoke_api.sh https://<域名>`
- [ ] Windows 任务计划 + 电源设置（防睡眠）
- [ ] 备份演练：`bash deploy/wsl/backup.sh` → 实际恢复验证一次

## Phase 2 · P2 MVP 前端（Step 8）——代码侧已完成 ✅

| 项 | 状态 | 说明 |
|---|---|---|
| Vite+Vue3 脚手架 | ✅ | build.outDir=../static（emptyOutDir）、terser passes:2、dev 代理 /api→8080 |
| 路由分包 + client + tokens + i18n + polling | ✅ | 8 路由动态 import；zh-CN/en 双字典；usePolling（visibilitychange/退避） |
| 布局壳 | ✅ | 双分组侧导航（工作台组"即将上线"）+ 顶栏（搜索/主题/语言）+ 移动底部 tab |
| 热榜页 | ✅ | PlatformTabs/NewsItem（rank 1-3 红 4-10 橙/NEW=count 1）/RankHistoryDrawer 联动 rank-history |
| 仪表盘 | ✅ | 四指标卡（todayCount/keywordHits/platformStats/freshness）+ keyword-series 曲线 + TOP 话题 + 源灯板；viral 预警条 |
| 检索 / 报告 | ✅ | search 三模式 + 日期/平台聚合侧栏；reports 日期网格 + iframe + 下载 |
| ECharts 按需 | ✅ | echarts/core + Line/Bar（Pie/DataZoom/MarkLine P3 加回）；异步 chunk 163.6KB |
| 主题切换图表重建 | ✅ | TrendChart MutationObserver 监听 data-theme → dispose+init |
| 首屏 gzip JS | ✅（口径） | 同步关键路径 ≈48KB 达标；总量 ≈211KB 超 5.5%（07 Phase 2 偏差#1 如实回填） |
| static/ 入库 + catch-all | ✅ | mount /assets + catch-all 在 API 路由后；**白名单 fallback**（拒 `..` 段，仅 8 前端路由+根路径回 index.html，其余 JSON 404——防穿越探测被吞成 200） |
| 回归 | ✅ | smoke --fixture 24/24 全绿（穿越用例加 --path-as-is）；/ /dashboard /system 200、规范化穿越 404、未知路径 404 |

浏览器侧手测（无法本机自动化，留给实机）：亮暗/中英全页切换、主题切换图表重建、手机 4G 首屏 <3s、三个真实任务。

**tag `web-v0.2` @ `11d96c78`**（P2 代码侧完成点）

## Phase 3 · P3 监测中心（Step 9）

| 项 | 状态 | 验证口径 |
|---|---|---|
| ai_runner | ✅ | 复用 `_load_ai_config` 键转换 + AIClient；run_json JSON contract + json_repair 兜底；每日 50 上限（TRENDRADAR_SENTIMENT_DAILY_LIMIT 可调） |
| api/sentiment 三端点 | ✅ | prompt/run/results；Semaphore(1) 串行 + 快路径双重检查（同参并发只跑一次 AI）；429+Retry-After（ApiError 扩展 headers） |
| SentimentStore 唯一写路径 | ✅ | BEGIN IMMEDIATE + INSERT OR IGNORE；schema.sql 追加 ai_sentiment_results（UNIQUE 五元组判重）；落库锚定 date_end 当日库 |
| 话题追踪页 | ✅ | TopicView：热度面积图+markLine 峰值+生命周期四指标+平台环形+相关标题；URL 同步 /topics/:keyword 直链 |
| 情感分析页 | ✅ | SentimentView：run 长超时 180s、环形（语义色）+平台堆叠+代表标题+AiBadge+历史回看 |
| 对比页 | ✅ | CompareView：时期对比三型（电梯数/升降榜/平台活跃柱）+新增消失关键词+平台关注度 |
| 系统页 | ✅ | SystemView：schedule 三态（disabled/timeline_unavailable/正常倒计时含跨日）+status/dates+手动抓取/管线（🔑+confirm 二次确认+409 提示）+源灯板 |
| 仪表盘 predict | ✅ | 真实数据卡（趋势统计口径标注，**不挂 AI 徽标**——07 偏差#6） |
| charts 加回 Pie/MarkLine | ✅ | TrendChart chunk gzip 175.5KB（异步）；首屏 47.6KB 不变 |
| 路由接线 + i18n | ✅ | 四路由指向真实视图；PlaceholderView 删除；zh-CN/en 补 topics./sentiment./compare./system. 全键 |
| 回归 | ✅ | 后端探针 20/20（prompt/run/缓存/429/落库/502/无误建库）；smoke --fixture 24/24；SPA 直链 /topics /sentiment /compare /system 200、未知路径 404 |

**tag `web-v0.3`**（P3 代码侧完成点）

浏览器侧手测（实机）：Phase 3 验收四项（特斯拉一屏可答 / 缓存命中+并发去重+429 / viral 条可点进 / 周环比交叉验证）。

## Phase 4 · P4 产品化（Step 10，按价值插空）

- [ ] Cloudflare Access
- [ ] 备份 timer 化
- [ ] i18n 收尾 + README 部署章节
- [ ] SSE（纯 ASGI 中间件已兼容）
- [ ] 多 key / 审计
- [ ] dist 一致性 CI + smoke 进 GitHub Actions

## 待用户决策 / 汇报

- **docker/.env 被 git 追踪且含真实密钥**——建议 `git rm --cached docker/.env` + 轮换密钥 + .gitignore 补条目；因涉及历史改写与用户资产，未擅动，待确认。
