# 07 · 实施计划

> 上游文档：全部前置。原则：每阶段结束都是一个**可独立验收的可用状态**，
> 随时可停在某阶段而不留半成品。

## 总览

| 阶段 | 主题 | 规模 | 依赖 |
|---|---|---|---|
| Phase 0 | WSL 地基与隧道 | 0.5~1 天 | 无（可与 P1 并行） |
| Phase 1 | 只读 API 薄壳 | 1~2 天 | 无 |
| Phase 2 | MVP 前端 | 3~5 天 | P1 |
| Phase 3 | 监测中心能力 | 3~5 天 | P2（情感依赖 P1 的 ai_runner） |
| Phase 4 | 产品化打磨 | 持续 | 按需 |
| Phase 5 🅱 | 工作台 MVP（国际日报） | **未排期** | P2 + 用户拍板 08 §8 |
| Phase 6 🅱 | Release 桌面发行版 | **未排期** | P5（向导要有工作台可导向） |

规模按"熟悉本仓库的一个人 + AI 辅助"估算，含自测不含正式测试套件。

---

## Phase 0 · WSL 地基（05 文档为施工图）

**目标**：公网域名 HTTPS 打得开一个占位页；隧道通；自愈通。

任务：
1. WSL：`/etc/wsl.conf` 启用 systemd，重启验证 `systemctl` 可用
2. `git clone` 仓库到 `/opt/trendradar`，`uv sync`，手动
   `python -m trendradar` 跑通一轮（配置从现网复制）
3. `deploy/wsl/` 脚手架：`trendradar-scheduler.{service,timer}` 模板
   + `install.sh` 雏形（渲染/enable/自检）
4. cloudflared 安装 + 域名 DNS + tunnel config（02-D8 的 ingress）
5. `trendradar-mcp.service`（127.0.0.1:3333）enable（可选但建议，
   验证路径路由）
6. 占位页：最简 `web_server`（见 P1 任务 1 提前做骨架）返回
   "TrendRadar Web is alive" + `/api/system/status` 透传
7. Windows 侧：任务计划自启 + 电源设置（05 §5）
8. 破坏性验证：`wsl.exe --shutdown` -> 重启 -> 全家自愈

**验收** = 05 §9 清单全绿。

---

## Phase 1 · 只读 API 薄壳（03 文档为契约）

**目标**：核心查询端点全部可用、带认证与缓存；`/docs` 本地可调试。

任务：
1. `web_server` 包骨架：`app.py`（**`create_app(mode)` 工厂**，02-D9--
   本机/服务两模式从第一天就分叉）、`__main__.py`
   CLI、信封/错误码中间件、`pyproject.toml` 加 `fastapi` pinned
   版本与 `trendradar-web` script 入口。
   **随路两件小事（D9 预留，成本≈0）**：路径解析集中到 config 层
   （数据根目录可配置）；`/setup` 路由挂载点预留（local 模式才注册）
2. `auth.py`：X-API-Key 恒定时间校验 + `web.env` 加载 +
   `require_read_key` 开关（读 config.yaml web 段）
3. 共享层增强（03 §8，全走 D1 下沉）：
   - `ParserService` 只读连接参数（`mode=ro`）
   - `DataQueryTools.get_rank_history()`
   - `SystemManagementTools.get_next_schedule_run()`
4. 路由模块：`system.py` / `news.py` / `topics.py` / `rss.py`
   （03 §2.1–2.3、2.5 全端点），`CacheService` 接线（TTL 分级）
5. `reports.py` 文件服务（路径穿越三重防护，06 §8 验证）
6. 限流中间件 + `/api/pipeline/run`（systemd-run transient unit，
   降级路径 Popen）+ `/api/crawl/trigger`
7. 生产开关：`TRENDRADAR_ENV=prod` 关 `/docs`
8. 手测脚本 `deploy/wsl/smoke_api.sh`：逐端点 curl 断言（信封/缓存
   标志/401/404/429）

**验收**：
- [ ] smoke 脚本全绿（本地 + 经域名两遍）
  ——本机 `--fixture` 24/24 全绿（2026-09-02，tag `web-v0.1`）；实机/经域名两遍在 Phase 0 完成后补跑
- [ ] `python -m web_server --port 8080` 与 systemd 两种方式行为一致（systemd 侧待 Phase 0 实机）
- [x] 抓包确认无任何响应包含 config 路径/key 类字段
  ——本机侧由 smoke 断言覆盖（status 响应白名单投影 + 无路径泄露检查）
- [ ] 管线照常运行不受 web 并发读影响（连续 trigger 后库无锁错误；待实机）

### Phase 1 实际偏差回填（2026-09-02）

1. **409 并发去重复用 `RATE_LIMITED` 码**（HTTP 409）：03 §4 信封无 409 专属码，
   pipeline/crawl 运行中再触发返回 `RATE_LIMITED` + `Retry-After: 60` + 运行详情。
2. **RSS 缺库返回 200 空列表而非 404**：工具层内部吞 `DataNotFoundError`（MCP 语义），
   前端以空态卡等效处理。
3. **`/api/news/search` 用 `SearchTools.search_news_unified`**：03 所写
   `search_news_by_keyword` 方法不存在，unified 为其超集。
4. **`system/dates` 走 `DataQueryTools.get_available_dates`**：
   `StorageSyncTools.list_available_dates` 无 data_root 支持，D9② 数据根隔离
   （fixture 模式依赖）只能走 ParserService 路径。
5. **range 表达式集合为「最近7天 / 近7天 / 上周 / last 7 days」式**
   （DateParser `RANGE_EXPRESSIONS`）；03 示例中的 `last7d` 连写形式不支持。
6. **认证 fail-closed 语义补全**（06 §2 未定义）：服务端未配置 key 时，
   POST 写端点返回 **503 `SERVER_MISCONFIGURED`**（区分配置问题与鉴权失败）；
   smoke fixture 须注入已知 key 才能测出 401。
7. **Popen 降级解释器修复**：`sys.executable` 不可 `Path.resolve()`
   （venv python 是指向基础解释器的符号链接，resolve 后脱离 venv
   site-packages，管线启动即 `ModuleNotFoundError`）。05 部署文档同理适用。

---

## Phase 2 · MVP 前端（04 文档 §3.1/3.2/3.4/3.7）

**目标**：日常看热点的入口从 IM 切到 Web（US-1/2/3 达成）。

任务：
1. `web_server/frontend/` Vite + Vue3 脚手架：router、
   `api/client.js`（信封解包/key 注入/toast）、tokens.css 亮暗双主题、
   `useI18n` + zh-CN/en 字典、`usePolling`
   **侧导航按「监测中心/工作台」双分组容器搭建**（04 §2 预留，
   工作台组显示"即将上线"，日后挂 `/wb` 不动导航骨架）
2. 布局壳：侧导航 + 顶栏（全局搜索/范围选择/主题/语言）
3. 仪表盘页：四指标卡、关注词曲线（TrendChart）、TOP 话题、
   源健康灯板、（预警条/预测卡占位，P3 填充）
4. 热榜页：平台 tab、NewsItem（排名箭头/高亮/NEW）、
   RankHistoryDrawer（排名折线 + title_changes 时间线）
5. 检索页：过滤器 + 结果列表 + 日期/平台聚合侧栏
6. 报告归档页：日期网格 + iframe 嵌入 + 下载
7. `npm run build` -> `static/` 入库；ASGI StaticFiles 挂载 + SPA fallback；
   vite dev 代理配置
8. 移动端断点适配（仪表盘/热榜优先）

**验收**：
- [ ] 手机 4G 打开仪表盘 < 3s 出首屏（CF 缓存后）
- [ ] 首屏 gzip JS < 200KB
- [ ] 能完成三个真实任务：看今日热点 / 翻上周三榜单 / 搜一个历史关键词
- [ ] 亮暗/中英切换全页面无漏译、无样式破碎

---

## Phase 3 · 监测中心能力（04 §3.3/3.5/3.6）

**目标**：US-4~8 全部可用，"舆情监测"名副其实。

任务：
1. 话题追踪页：热度面积图 + 生命周期标注 + 平台环形图 +
   相关新闻（`analyze_topic_trend_unified` 全量映射）；
   「加为关注词」v1 只提示复制到 frequency_words（在线编辑属 P4/非目标）
2. `ai_runner.py` + `sentiment.py` API（03 §2.4）：
   litellm 执行、json-repair 解析、`ai_sentiment_results` 落库、
   Semaphore/每日上限/缓存三护栏
3. 情感分析页：表单 -> 轮询 -> 结果可视化（环形+堆叠+代表标题+AI 摘要）
   + 历史回看
4. 对比页：时期对比（迁移表/活跃度/环比）+ 平台对比视图
5. 仪表盘补齐：爆火预警条（viral）+ 趋势预测卡（predict，AI 徽标）
6. 系统页：下次运行倒计时、手动抓取/管线按钮（🔑 + 二次确认）

**验收**：
- [ ] "特斯拉近 30 天热度怎么变的"一屏可答（曲线+阶段+分布）
- [ ] 情感分析：同参数二次调用秒回（缓存命中）；并发点击只跑一次；
      第 51 次/日 429
- [ ] 爆火话题在仪表盘预警条出现，且可点进话题页
- [ ] 周环比页面数字与手查两天榜单交叉验证一致

---

## Phase 4 · 产品化（持续，按需插空）

候选任务（按价值排序，做之前逐项再评估）：
1. **Cloudflare Access 接入**（06 §3.1 推荐路径）+ 部署文档对外发布
2. **备份自动化**：`backup.sh` + timer（05 §6），验证可恢复
3. **i18n 收尾 + README 部署章节**：WSL 形态进主 README/官网文档
4. **通知订阅管理**：Web 上管理推送渠道与关注词（**注意**：触碰
   config 写路径，需先过 06 的安全评审，v1 明确不做）
5. **SSE 实时刷新**替代轮询（管线落库后推送事件）
6. **多 API key / 操作审计日志**（journal 之外的结构化记录）
7. **dist 一致性 CI**（04 §7）+ 冒烟测试进 GitHub Actions

---

## Track B · Phase 5 / 6（🅱 已声明未排期）

> 详细设计见 [08-workbench-design.md](08-workbench-design.md) 与
> [09-release-packaging.md](09-release-packaging.md)。此处只立排期骨架，
> 开工前需完成 08 §8 的五项用户拍板（Excel 资源池语义、协作模型、
> Word 模板、国际源清单、PDF 渲染器选型）。

### Phase 5 · 工作台 MVP（目标：国际日报零手工搜集）

1. `workbench/` 引擎包：任务模板/实例模型 + 状态机 + `workbench.db` 迁移
   （含 `ai_sentiment_results` 从当日 news 库迁出，03 §6 标注项）
2. 文档生成栈：python-docx + openpyxl + PDF 渲染器（按打包验证定
   WeasyPrint/fpdf2）+ Noto Sans SC 内嵌
3. 国际日报模板与 prompt；候选池组装（RSS international 分组 +
   aggregate_news 去重 + calculate_news_weight 初排）
4. `/api/wb/*` 路由（03 §9 契约）+ 四步向导 UI（08 §7）
5. Excel 资源池（按拍板结果 A/B 方案实现）
6. （可选）交付推送复用现有通知渠道

验收：连续 5 个工作日，国际日报的实际人耗 < 15 分钟且全部花在筛选与把关；
产物 Word/PDF 符合实验室版式；资源池可检索、Excel 镜像可下载。

### Phase 6 · Release 桌面发行版（目标：实验室同学下载即用）

0. 壳策略已定档（[09 §2.1](09-release-packaging.md)，2026-08-26）：
   **v1 = pywebview 独立窗口 + 浏览器自动兜底**；Electron 不做，
   留三个触发条件明确的升级信号。施工顺序按风险排：
   先 sidecar（PyInstaller/数据目录/本机模式/向导）用浏览器形态验收，
   再包 pywebview 窗口
1. 本机模式落地：单进程（web + 调度线程 + 工作台）、127.0.0.1、
   自动开浏览器
2. 首启向导（local 模式路由 + 自锁逻辑，06 §3.0 红线）
3. `pyinstaller` spec（条件排除 boto3 等）+ GitHub Actions
   `release.yml` 三平台 matrix（09 §6）
4. 版本更新提示（复用现有 version 文件机制）

验收：一台无 Python 的 Windows 实验室电脑，从下载到出第一份日报
≤ 10 分钟；杀软误报有文档指引。

---

## 里程碑与「可停点」

- **P0+P1 后**：已是可用的自托管只读 API（对开发者有价值）
- **P2 后**：自用价值完整兑现（看热点不依赖推送）
- **P3 后**：产品故事完整（可对外宣传"AI 舆情监测中心"）
- **P5 后（Track B）**：实验室例行任务价值兑现（国际日报零手工搜集）
- 每个阶段结束 commit + tag（`web-v0.x`），设计文档回填
  「实际偏差」小节

## 风险与回退

| 风险 | 触发点 | 回退方案 |
|---|---|---|
| WSL 不稳定超预期 | P0 验收不过 | 整套设计迁 Docker（项目已有 docker/ 基础）或提前上 VPS；设计不变 |
| tools 层复用阻力（接口不匹配） | P1 中 | 允许在 web_server 写薄适配器，但**逻辑**仍须下沉；严禁复制 SQL |
| 前端工作量失控 | P2 超 1 周 | 砍页面保三件套：仪表盘/热榜/搜索；追踪与对比推 P3+ |
| AI 端点被滥用 | 上线后 | 一键 `require_read_key=1` + CF 限流收紧；最坏关 AI 端点 |
| newsnow 上游限制 | 任意时刻 | 管线已有处理；调度周期调回 30min |

## 与现有部署的关系（收尾确认）

| 现有形态 | 处置 |
|---|---|
| GitHub Actions 定时跑 | 可停（被 WSL timer 取代）或保留做灾备（双写无害，`already_executed` 判重按库走，注意远端同步开关） |
| Docker 部署 | 不动，继续作为主流轻量形态；未来可把 web_server 编进镜像（RUN_MODE=server） |
| Cloudflare Pages 静态报告/官网 | 不动 |
| MCP Docker/本地 | 不动；systemd 版为新增选项 |
