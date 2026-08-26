# 04 · 前端设计

> 上游文档：[03-api-design.md](03-api-design.md)
> 技术栈（决策 D4）：Vue 3（组合式 API，`<script setup>`，无 TS）
> + Vite + ECharts + 手写 CSS design tokens；i18n 字典模式沿用
> [docs/assets/i18n.js](../docs/assets/i18n.js) 的既有做法
>
> **视觉与风格规范已独立成档：[10-ui-style-guide.md](10-ui-style-guide.md)**
> （色彩/字体/间距/组件/图表/动效/可访问性）。
> 本档只管信息架构、页面、组件结构与数据流。

## 1. 设计原则

1. **信息密度优先**：监测中心是工具不是官网，一屏要能看清状态与异常
2. **移动可用**：CF Tunnel 出门在外手机查看是真实场景（US-1），
   仪表盘与热榜做响应式；复杂分析页桌面优先
3. **AI 结果显式标注**：情感分析/预测结果一律带「AI 生成」徽标与时间戳，
   与抓取数据视觉区分（可信度沟通，视觉协议见 10 §9）
4. **暗色为默认**，亮色可切（主题机制见 §5，色彩规范见 10 §2）

## 2. 信息架构与路由

```
/                     重定向 -> /dashboard
/dashboard            仪表盘（默认页）
/live                 实时热榜
/topics               话题追踪（含搜索框，/:keyword 展开详情）
/search               全历史检索
/sentiment            情感分析
/compare              对比分析（时期 / 平台）
/reports              报告归档
/system               系统与健康
```

布局：左侧窄导航栏（图标+文字，移动端折叠为底部 tab），
顶栏放全局搜索框、日期/范围选择器、语言与主题切换。

> **导航顶层分组（Track B 预留）**：侧导航从第一天就按两个分组组织--
> 「监测中心」（上表八页）与「工作台」（Track B 排期时挂
> `/wb` 系列，见 [08](08-workbench-design.md) §7）。分组容器现在就建
> （工作台组先隐藏或显示"即将上线"），避免日后导航结构大改。
> 桌面发行版（[09](09-release-packaging.md)）同用此壳。

> **首启向导页（Track B 预留）**：`/setup` 路由仅 local 模式可用，
> 独立于主布局（无侧导航），完成后跳转仪表盘。

## 3. 页面设计

### 3.1 仪表盘 `/dashboard`（US-1）

```
┌──────────────────────────────────────────────────────┐
│ ⚠ 爆火预警条（detect_viral_topics 命中时才出现，置顶红条）│
├────────────┬────────────┬────────────┬───────────────┤
│ 今日热榜数   │ 关注词命中   │ 覆盖平台     │ 数据新鲜度     │
│ 1,247 ↑12%  │ 23 条       │ 8/9 在线     │ 6 分钟前       │
├────────────┴────────────┴──────┬─────┴───────────────┤
│ 关注词今日热度曲线（ECharts 折线，多系列）                   │
│ [frequency_words 中各词组过去 24h 命中量随时间]              │
├───────────────────────────────┼──────────────────────┤
│ TOP 话题榜（trending keywords） │ 源健康灯板             │
│ 1. 关键词A  ▲ 3 平台           │ ● weibo  ● zhihu     │
│ 2. 关键词B  ▼ 1 平台           │ ● rss:tech ○ rss:x   │
│ （点击 -> /topics/:keyword）    │ （失败源置灰可点看详情）  │
├───────────────────────────────┼──────────────────────┤
│ 近 7 日趋势预测候选（AI 徽标）   │ 最近推送记录           │
└───────────────────────────────┴──────────────────────┘
```

数据：`/api/system/status`、`/api/topics/trending`、`/api/analytics/viral`、
`/api/analytics/predict`、`/api/system/health/sources`。
刷新策略：进入拉取 + 每 60s 自动轮询（页面可见时）。

### 3.2 实时热榜 `/live`（US-1/2）

- 平台 tab（全部/微博/知乎/…，含 RSS 源）+ 平铺分组两种视图
- 每条：排名（与上次变化箭头 `rank_history` 首末对比）、标题、
  关键词高亮（关注词命中加底色）、NEW 徽标（今日新出现）、停留时长
- 视觉延续现有报告页的热度分级（hot/warm、top/high 的 class 语义照搬
  [index.html](../index.html) 的成熟分级）
- 点击条目 -> 抽屉：该条新闻的排名历史折线 + 标题改动记录
  （`title_changes`，舆情信号）+ 原文链接

### 3.3 话题追踪 `/topics/:keyword`（US-4，核心页）

```
┌──────────────────────────────────────────────────────┐
│ 「特斯拉」  [加为关注词]   范围: [近30天 ▾]              │
├──────────────────────────────────────────────────────┤
│ 热度曲线（ECharts 面积图：每日命中量/加权热度）             │
│ 生命周期阶段标注（analyze_topic_lifecycle：发酵/爆发/衰退）  │
├───────────────────────┬──────────────────────────────┤
│ 平台分布（环形图）      │ 相关新闻列表（find_related_news）  │
└───────────────────────┴──────────────────────────────┘
```

数据：`/api/analytics/topic-trend`。命中曲线需要跨日聚合--
`analyze_topic_trend_unified` 已含热度序列，直接映射。

### 3.4 全历史检索 `/search`（US-3）

- 单输入框 + 过滤器（平台、日期范围、来源类型 热榜/RSS）
- 结果列表：标题（关键词高亮）、平台、日期、当时排名
- 侧栏聚合：命中量的日期分布柱状图、平台分布

### 3.5 情感分析 `/sentiment`（US-5）

- 表单：话题（可空=全量）、范围、平台 -> 「运行 AI 分析」（🔑 需登录态输入 API Key，存 localStorage 仅本地）
- 结果区：正/负/中比例环形图 + 分平台堆叠条形图 + 代表性标题列表（按情感着色）+ AI 摘要段落（AI 徽标）
- 历史区：已跑过的分析（`/api/analytics/sentiment/results`），一键回看
- 运行中状态：提交后轮询，进度提示；达到每日上限时明确提示剩余额度

### 3.6 对比分析 `/compare`（US-7）

- 两个下拉：本周 vs 上周 / 本月 vs 上月 / 自定义两段
- 输出：话题迁移表（新上榜/消失/持续，带变化箭头）、
  平台活跃度对比条形图、总量环比卡

### 3.7 报告归档 `/reports`（低成本高价值）

- 日期网格（有数据的日期可点）
- 选中日期 -> iframe 嵌入当日 HTML 报告（`/api/reports/{date}/html`），
  顶部快捷键：下载 HTML / 查看当日热榜数据视图

### 3.8 系统 `/system`（US-9/10）

- 服务状态卡：web/scheduler 上次运行、下次运行倒计时、连续在线时长
- 采集源健康表：今日各源成功/失败次数、最近失败原因
- 手动操作（🔑）：立即抓取（轻量）/ 跑完整管线（含 AI+推送），
  二次确认弹窗写明区别
- 存储概览：库文件数、总大小、最早/最晚日期

## 4. 组件与状态

```
web_server/frontend/src/
├── main.js
├── App.vue
├── router/index.js
├── api/client.js          # fetch 封装：信封解包、错误 toast、X-API-Key 注入
├── composables/
│   ├── usePolling.js      # 可见性感知的轮询
│   ├── useDateRange.js    # range 快捷词 <-> start/end
│   └── useI18n.js         # zh-CN / en 字典
├── components/
│   ├── TrendChart.vue     # ECharts 封装（折线/面积/环形/堆叠，props 驱动）
│   ├── NewsItem.vue       # 热榜条目（排名箭头/高亮/NEW）
│   ├── PlatformTabs.vue
│   ├── SourceHealthGrid.vue
│   ├── AiBadge.vue        # 「AI 生成」徽标
│   └── RankHistoryDrawer.vue
├── views/                 # §3 的八个页面
├── styles/tokens.css      # 色彩/间距/字号 design tokens（亮暗双套）
└── locales/{zh-CN,en}.json
```

- **无 Pinia**：状态就两块（主题/语言入 localStorage，API key 入
  localStorage），组合式函数足够；等出现真实跨页状态再加
- **ECharts 按需引入**（tree-shake），主题跟 tokens 走

## 5. i18n 与主题

- 字典 JSON + `useI18n()`，默认 zh-CN，en 完整对照（文案与
  `docs/` 编辑器的 i18n 术语保持一致，比如「热榜/热点/关注词」翻译统一）
- 主题机制：`<html data-theme="dark|light">` 切换 10 §2 定义的 tokens
  变量集；默认 dark，首访跟随系统偏好，选择持久化 localStorage
  （中英混排、字距等排版规则见 10 §3）

## 6. 性能预算

| 项 | 预算 |
|---|---|
| 首屏 JS（gzip） | < 200KB（Vue runtime ~34KB + ECharts 按需 + 业务代码） |
| 首屏接口 | ≤ 5 个并行 |
| 图表数据点 | 单序列 > 500 点时降采样（前端 LTTB） |
| 弱网 | 接口 8s 超时，可重试；图表骨架屏 |

## 7. 构建与产物

- `web_server/frontend/` 内 `npm run build` -> 输出 `web_server/static/`
- **dist 提交 git**（D4）：部署侧免 Node；CI（GitHub Actions）
  可加一致性校验（源码有变而 dist 未更新时 fail，防漂移）
- 开发时 `vite dev` 代理 `/api` 到 `127.0.0.1:8080`
