# 10 · UI 设计风格规范

> 独立成档（应用户要求，不混入架构文档）。
> 服务对象：[04-frontend-design.md](04-frontend-design.md)（信息架构与页面）
> 及所有前端实现的视觉决策。本档只管"长什么样"，不管"有什么页"。
> 实现落点：`web_server/frontend/src/styles/tokens.css` 等（04 §4）。

## 1. 设计语言：「情报终端」

一句话基调：**冷静、致密、数据优先的暗色情报终端**，不是营销官网。

参照系：Grafana / Linear / Vercel Dashboard 一脉的工具审美--
大面积低饱和底色、克制的品牌色点缀、高信息密度的表格与图表、
几乎无装饰性插画与动效。

**三条铁律**：
1. 数据是主角：任何视觉元素若不能帮助读数，就去掉
2. 异常要扎眼，正常要安静：爆火预警是页面上唯一允许"喊"的元素
3. 情绪语义有专属色，别的元素不许抢（见 §2.2）

**与现有资产的连续性**：延续推送报告页（[index.html](../index.html)）的
品牌靛紫渐变与 `hot/warm`、`top/high` 热度分级语义，保证用户从
IM 推送报告切换到 Web 端时视觉同源、无需重新学习。

## 2. 色彩系统

### 2.1 中性与品牌（CSS Custom Properties，双主题）

| token | dark（默认） | light | 用途 |
|---|---|---|---|
| `--bg-base` | `#0f1115` | `#f7f8fa` | 页面底 |
| `--bg-surface` | `#161a22` | `#ffffff` | 卡片/表格容器 |
| `--bg-raised` | `#1d222c` | `#ffffff` | 抽屉/弹层/悬浮 |
| `--border-subtle` | `#262c38` | `#e5e8ee` | 常规描边 |
| `--border-strong` | `#3a4252` | `#cbd3de` | 强调描边/表格头下边 |
| `--text-primary` | `#e8eaf0` | `#1a202c` | 正文 |
| `--text-secondary` | `#9aa3b5` | `#4a5568` | 次要文字/轴标签 |
| `--text-muted` | `#5c6678` | `#a0aab8` | 仅装饰性/禁用（勿用于必读信息） |
| `--accent` | `#6366f1` | `#4f46e5` | 主操作/选中/链接 |
| `--accent-hover` | `#818cf8` | `#6366f1` | 悬停态 |
| `--gradient-brand` | `linear-gradient(135deg,#4f46e5,#7c3aed)` | 同 | 品牌标识位（logo 条/空态插画/主卡头） |

暗色模式层级策略：**以边框和底色微差分层，不用重阴影**；
阴影只留给真正的悬浮层（§5）。

### 2.2 语义色（全局唯一，禁止挪用）

| token | 色值 | 语义 | 出现场景 |
|---|---|---|---|
| `--sem-pos` | `#34d399` | 正面 | 情感分析的正向 |
| `--sem-neg` | `#f87171` | 负面 | 情感的负向、故障、失败源 |
| `--sem-neu` | `#94a3b8` | 中性 | 情感的中立 |
| `--sem-warn` | `#fbbf24` | 预警 | 爆火预警、降级提示、每日配额将尽 |
| `--sem-crit` | `#fb7185` | 严重 | 服务不可用、源连续失败 |
| `--sem-info` | `#60a5fa` | 新信息 | NEW 徽标、进行中状态 |

**排名升降的用色决策**：上升 `--sem-crit` 系（红=热，延续中文热搜语境），
下降 `--text-muted`（灰=降温）。**刻意不用绿**--绿已被"正面情感"独占，
混用会造成"排名下跌=好消息"的误读。

**冲突规则**：一个页面同时出现情感语义与排名语义时（如话题追踪页），
情感用色块/环形图承载，排名用箭头字符 ▲▼ 承载，形状差异兜底色盲可达性。

### 2.3 图表色板（ECharts，按需注册）

```
分类色板（8 色，暗底校准，明度梯度区分）：
#818cf8 #22d3ee #34d399 #fbbf24 #fb7185 #c084fc #60a5fa #94a3b8

强制约定：
- 情感堆叠图只用 --sem-pos/--sem-neg/--sem-neu 三色
- 单序列趋势线默认 #818cf8，对比双序列用 #818cf8 + #94a3b8
- 轴线/网格线用 --border-subtle，轴标签 --text-secondary
- 主题切换时 ECharts 实例随 tokens 重建（不手维护两套色值）
```

## 3. 字体排印

```css
/* 字体栈（延续项目现有栈 + CJK 回退） */
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui,
             "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
--font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono", Consolas,
             "Noto Sans Mono CJK SC", monospace;
```

| 级别 | 尺寸/行高 | 用途 |
|---|---|---|
| `--text-xs` | 12 / 1.4 | 表格辅助列、时间戳、徽标 |
| `--text-sm` | 13 / 1.5 | 表格正文、次级按钮 |
| `--text-base` | 14 / 1.6 | **正文基准**（密度型工具 UI） |
| `--text-lg` | 16 / 1.5 | 卡片标题 |
| `--text-xl` | 20 / 1.4 | 页面标题 |
| `--text-2xl` | 28 / 1.2 | KPI 大数字 |

**数字规则**（监测工具的命门）：
- 一切对齐敏感的数字（排名、计数、百分比）用 `font-variant-numeric: tabular-nums`
- 排名值、时间戳、ID 用 `--font-mono`
- 中文正文行高不低于 1.6；表格内可压到 1.4

**中英混排**：Latin 标签（如 `API`、`RSS`）两侧留出视觉间距
（CJK 与 Latin 间 `margin: 0 .25em` 或依赖字体默认空隙）；
英文全大写微标签（导航分组名、表头）加 `letter-spacing: .08em`，
中文**永远不加**字距。

## 4. 间距与布局

**4px 基准网格**，常用档位：`4 / 8 / 12 / 16 / 24 / 32 / 48`。

| 场景 | 值 |
|---|---|
| 卡片内边距 | 16（紧凑卡片 12） |
| 页面水槽（desktop / mobile） | 24 / 16 |
| 卡片间距 | 16 |
| 表单控件纵向间距 | 16 |
| 表格行高（默认 / 密档 dense 模式） | 40 / 32 |

**密度原则**：表格页与热榜页允许开"密档"（用户偏好，存 localStorage）；
仪表盘 KPI 卡默认四列 ≥1200px，双列 ≥768px，单列 <768px。
内容最大宽度：表格/列表页 1440px 居中，仪表盘全宽流式。

## 5. 圆角、描边与高度

| token | 值 | 用途 |
|---|---|---|
| `--radius-card` | 12px | 卡片（呼应报告页容器的 12px） |
| `--radius-ctrl` | 8px | 按钮/输入框/下拉 |
| `--radius-pill` | 999px | 徽标/状态点 |
| `--shadow-overlay` | dark: `0 8px 24px rgba(0,0,0,.45)`; light: `0 8px 24px rgba(16,24,40,.12)` | 仅弹层/抽屉/下拉浮层 |

暗色卡片 = `--bg-surface` + `1px --border-subtle`，**不加常驻阴影**。

## 6. 组件视觉规范

**侧导航**：宽 220px（折叠 64px 图标态）；分组标题用
`--text-xs` + `letter-spacing` 的全大写微标签风格（「监测中心」「工作台」）；
当前项 = 左缘 3px `--accent` 竖条 + `--bg-raised` 底。

**徽标体系**（全部 pill 形，`--text-xs`）：

| 徽标 | 样式 | 语义 |
|---|---|---|
| `AI` | `--sem-info` 描边空心 + 图标 | AI 生成内容（见 §9） |
| `NEW` | `--sem-info` 实心浅底 | 今日新上榜 |
| `HOT` | `--sem-warn` 实心 | 热度分级 top（沿用报告页语义） |
| 状态灯 | 8px 圆点 + `--sem-pos/neg/warn` | 源健康/服务状态 |

**按钮**：主按钮 `--accent` 实心白字；次按钮描边；危险操作
（跑完整管线/删除）`--sem-neg` 描边 + 二次确认弹窗。
高度 32（sm）/ 36（默认），点击热区不小于 32×32。

**表格**：表头 `--bg-raised` + `--text-secondary` 微标签风；斑马纹不用
（密度靠行高与分隔线 `--border-subtle`）；排序列表头带方向箭头。

**抽屉（RankHistoryDrawer 等）**：右滑入，宽 min(480px, 90vw)，
`--bg-raised` + `--shadow-overlay`，遮罩 `rgba(0,0,0,.5)`。

**Toast**：右上角堆叠，成功/失败/加载三种，3s 自动消失，失败态常驻。

**空态**：品牌渐变绘制的简洁插画位 + 一句话 + 主操作按钮
（如"该日无数据 · 去看最新热榜"）。

## 7. 动效

| 场景 | 时长/曲线 |
|---|---|
| 悬停、按压反馈 | 150ms · ease-out |
| 抽屉、下拉、toast | 200ms · `cubic-bezier(.16,1,.3,1)` |
| 页面切换 | ≤300ms，仅淡入位移 8px |
| 图表动画 | 首载 400ms，数据更新不重播 |

`prefers-reduced-motion: reduce` 时全部时长归零。
**禁用**：视差、循环脉冲（状态灯的呼吸效果除外，2s 周期，
仅 `--sem-warn/crit` 态使用）。

## 8. 可访问性

- 正文对比度 ≥ 4.5:1（本档暗色组合已验证：`--text-secondary` on
  `--bg-surface` ≈ 7:1；`--text-muted` 仅用于可忽略信息）
- `:focus-visible` 全局可见：2px `--accent` 外环 + 2px 偏移
- 移动端点击热区 ≥ 44×44
- 色彩不作为唯一信息载体（§2.2 的冲突规则、图表 always 配图例/标签）
- 图表交互（hover tooltip）在触屏上有 tap 等价物

## 9. 「AI 生成」的可信度视觉协议

产品叫"AI 舆情监测中心"，人机信任边界必须可视：

1. 凡 AI 产出（情感结论、趋势预测、AI 预筛建议、工作台摘要初稿）：
   容器左缘 2px `--sem-info` 竖线 + `AI` 徽标 + 生成时间戳（相对时间，
   hover 显绝对时间）+ 所用模型名（`--text-xs`）
2. 凡抓取事实（榜单、排名、来源）：**永不**出现 AI 徽标
3. AI 文本支持一键复制原文 prompt（高级用户验证用，衔接 MCP 生态）
4. AI 出错时：明确失败态文案（"AI 调用失败：余额不足"），**不用**
   缓存旧数据冒充新结果

## 10. 文件组织

```
web_server/frontend/src/styles/
├── tokens.css      # §2–§5 全部变量，:root[data-theme="dark|light"] 双套
├── base.css        # reset + 元素默认 + 工具类（.mono-num 等少量）
└── charts.js       # §2.3 图表色板与主题注册（ECharts 按需引入处）
```

组件内**禁止硬编码色值**，一律引用 token；新语义色先入本档再入代码。
