# 08 · 实验室工作台设计（Track B · 已声明未排期）

> 状态：**愿景级设计**（用户已声明需求，未排期实现）。
> 上游文档：[01-goals.md](01-goals.md) · [02-architecture.md](02-architecture.md)
> 原则：本档只定架构骨架与关键技术选型，细则在排期时另出实施设计。

## 1. 定位

工作台 = **人机协作的实验室日常任务引擎**，跑在监测中心同一套
Web 产品里。监测中心负责"看懂舆情"，工作台负责"把机械劳动交还给系统"。

与批处理自动化的本质区别：国际日报的关键步骤（**选出 6 条**）是人的判断。
工作台的价值不是"全自动"，而是：

1. 候选池自动备好（数据来自监测中心的新闻资源池，不用手动搜集）
2. AI 先干粗活（预筛建议、摘要初稿）
3. 人只做两件事：**筛选**与**把关**
4. 文件生成（Word/PDF/Excel）与归档零手工

## 2. 参考场景：国际日报（end-to-end）

```
每天 08:00（调度）
   │
   ▼
① 候选池就绪     拉取昨日 08:00 ~ 今晨 08:00 的国际新闻
   │             （RSS 国际源 + 热榜国际平台，现有采集能力）
   │             跨平台去重（aggregate_news 已有）+ 权重初排
   │             （calculate_news_weight 已有）+ AI 预筛建议（可选）
   ▼
② 人工筛选       工作台 UI：候选列表（按权重排序，AI 建议高亮）
   │             → 勾选 6 条 → 调整顺序                 ← 人的判断
   ▼
③ AI 摘要        每条新闻生成简报摘要（复用 trendradar/ai
   │             + 可定制的日报 prompt 模板）
   ▼
④ 人工把关       预览简报（HTML），可编辑摘要文字        ← 人的判断
   ▼
⑤ 生成归档       一键产出：
   │             · 国际日报-2026-08-26.docx（Word 模板填充）
   │             · 国际日报-2026-08-26.pdf（同源渲染）
   │             · 资源池入库（新闻+摘要落 workbench.db，
   │               并更新 Excel 资源池文件）
   ▼
⑥（可选）交付     简报推送到实验室群（复用现有通知渠道，
                 飞书/企微/邮件——现成的，白捡的能力）
```

**任务状态机**（每步落库，随时中断随时续）：

```
instantiated ──select──▶ selected ──summarize──▶ summarized
   (候选池就绪)           (已勾选6条)              (AI初稿完成)
                                                   │ edit
                                                   ▼
                          archived ◀──generate── reviewed
                          (产物+入库)               (人工把关完成)
```

## 3. 任务模型

一个"实验室任务"= 模板 + 每日实例。国际日报只是第一个模板，
同类任务（周报汇总、竞品动态、特定话题简报）复用同一模型：

```yaml
# wb_task_templates（示意）
id: intl_daily
name: 国际日报
schedule: "0 8 * * *"                 # 实例化时刻
candidate_source:                     # 候选池从哪来
  platforms: [reuters, bbc]           #   热榜平台（config.platforms 子集）
  rss_groups: [international]         #   RSS 源分组（config.rss 打标签）
  window: {from: "yesterday 08:00", to: "today 08:00"}
selection:
  count: 6                            # 勾选数量
  ai_suggest: true                    # 是否给 AI 预筛建议
ai_steps:
  - id: summarize
    prompt_template: prompts/intl_daily_summary.txt   # 可定制
outputs:
  docx: {template: templates/intl_daily.dotx}         # Word 模板
  pdf:  {from: briefing_html}                         # 与预览同源
  pool: {target: intl_news_pool}                      # 资源池目标表
delivery:                             # 可选
  channels: [feishu]
```

实例数据（`wb_task_instances` 等）存工作台自有库，见 §5。

## 4. 文档生成技术栈

| 产物 | 选型 | 理由 |
|---|---|---|
| Word (.docx) | **python-docx** | 事实标准；支持从 .dotx 模板填充（实验室若有固定版式，给模板即可换皮） |
| Excel (.xlsx) | **openpyxl** | 纯 Python 零原生依赖；追加/生成皆可 |
| PDF | **WeasyPrint**（HTML/CSS → PDF） | 与项目现有 HTML 报告技能同源：简报预览 HTML 直接转 PDF，所见即所得；**备选 fpdf2**（纯 Python 零原生依赖，桌面发行版打包更省心，但排版能力弱、需内嵌 CJK 字体） |
| 字体 | Noto Sans SC（OFL 协议） | 可再分发，随发行版打包，解决中文字形问题 |

**单一事实源**：简报内容建模为结构化 JSON（标题/6 条新闻/各摘要/日期），
`HTML 预览 / DOCX / PDF` 都是它的渲染器。改样式只动模板，不动数据。

**PDF 选型的待决点**：WeasyPrint 依赖 Pango 等系统库（Windows 打包要带
GTK 运行时，体积+复杂度）；fpdf2 无原生依赖但手排中文版式费劲。
排期时按 [09-release-packaging.md](09-release-packaging.md) 的打包验证结果
二选一，接口层先抽象成 `render_pdf(briefing) -> bytes` 不赌方向。

## 5. 存储设计（存储域分离，02-D5 修正案的落地）

```
新闻数据域（不动）：output/news|rss/{date}.db
  · 管线写、Web 只读 —— 现有原则原样保留

工作台数据域（新增）：output/workbench/workbench.db
  · 工作台引擎读写，Web 经工作台服务层访问
  · 表：wb_task_templates / wb_task_instances / wb_selections /
        wb_artifacts / wb_resource_pool(各池按 target 分表或单表+列)

产物文件（新增）：output/workbench/{task_id}/{date}/
  · 国际日报-YYYY-MM-DD.docx / .pdf
  · 资源池-国际新闻.xlsx
  · 产物路径与校验和登记在 wb_artifacts
```

**关键细节——引用与拷贝**：工作台对新闻条目的**运行时引用**
（哪天哪个平台的哪条）可以指向当日 news 库；但**资源池必须拷贝内容**
（标题/URL/日期/AI 摘要落 `wb_resource_pool`）。原因：news 库按日轮转/
清理，资源池是要长期积累的实验室资产，不能跟着过期数据一起消失。

**Excel 资源池的坑（必须现在说清）**：用户需求是"汇集到一个 Excel 历史池"，
但 .xlsx 被人在 Office 里打开时会**文件锁死**，程序追加会失败；且 Excel
当数据库用容易损坏。两个方案：

| 方案 | 行为 | 取舍 |
|---|---|---|
| A（推荐） | SQLite 为真相，Excel 是**导出产物**：一键"更新资源池.xlsx"全量重生成 | 永不锁死、可查询、可重建；代价是"那个 Excel"变成生成物而非手改的原件 |
| B（字面满足） | 直接向共享 .xlsx 追加行，锁冲突时提示"文件被占用" | 字面符合直觉；代价是锁/损坏风险，且 Excel 里手改的内容会被下次导出覆盖（或不敢覆盖） |

**建议 A**，把"资源池"的产品语义定义为"系统里的历史库 + 随时可取的
Excel 镜像"。此点需用户确认（见 §8 开放问题）。

## 6. API 草案（v2，仅声明）

```
GET  /api/wb/tasks                          任务模板列表
GET  /api/wb/tasks/{id}/instances/{date}    某日实例（含状态机当前态）
POST /api/wb/instances/{id}/select          提交勾选（6条+顺序）      🔑
POST /api/wb/instances/{id}/summarize       触发 AI 摘要（异步）      🔑
PUT  /api/wb/instances/{id}/draft           保存人工编辑              🔑
POST /api/wb/instances/{id}/generate        生成 docx/pdf + 入池      🔑
GET  /api/wb/instances/{id}/artifacts/{f}   下载产物
GET  /api/wb/pool?target=intl_news_pool     资源池查询（分页/搜索）
POST /api/wb/pool/export                    重生成 Excel 镜像         🔑
```

全部写操作走 `X-API-Key`；AI 步骤复用 03 §2.4 的护栏模式
（Semaphore / 每日上限 / 缓存）。

## 7. 前端信息架构（并入 04 的导航分组）

```
监测中心（Track A，04 文档的八个页面）
工作台（Track B）
  /wb                 任务卡片墙：今日待办（状态徽标：待筛选/AI中/待把关/已归档）
  /wb/intl-daily      任务详情 = 四步向导：筛选 → 摘要 → 把关 → 生成
                      （筛选步：候选列表 + AI 建议星标 + 勾选计数器；
                        把关步：简报预览 + 行内编辑；
                        生成步：产物下载卡 + 交付渠道开关）
  /wb/pool            资源池浏览器（表格 + 搜索 + 导出按钮）
```

## 8. 开放问题（排期前需用户拍板）

1. **Excel 资源池语义**：§5 方案 A/B 二选一（推荐 A）
2. **协作模型**：实验室谁都能筛，还是轮值？v1 按"单操作员"实现，
   但表结构预留 `operated_by` 审计字段，多人/轮值是 v2 话题
3. **Word 版式**：实验室有没有固定的日报模板？有就给 .dotx，没有就用默认版式
4. **国际新闻源清单**：现有 RSS 配置里加 `international` 分组标签即可，
   但具体订阅哪些源（BBC/Reuters/AP/…）需要实验室提供清单
5. **PDF 渲染器**：按打包验证结果定 WeasyPrint / fpdf2（§4）

## 9. 对 Track A 的反向依赖（很小，且都是便宜动作）

| 依赖 | 落点 | 状态 |
|---|---|---|
| 存储域分离原则 | 02-D5 修正 | ✅ 本轮已改 |
| 运行模式三分法（桌面/工作站/Docker） | 02-D9 新增 | ✅ 本轮已改 |
| 前端导航顶层分组 | 04 §2 | ✅ 本轮已改 |
| AI 执行通道复用 | 03 §2.4 的 ai_runner 泛化为通用 AI 步骤执行器 | 排期时小重构 |
| 配置首启向导（本机模式） | 09 §4 | Track B 实现时做 |
