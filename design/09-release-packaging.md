# 09 · Release 发行版设计（Track B · 已声明未排期）

> 状态：**愿景级设计**。上游文档：[08-workbench-design.md](08-workbench-design.md)
> 目标：实验室同学从 GitHub Releases **下载即用**，不装 Python、不碰命令行。

## 1. 目标与非目标

**目标用户**：实验室成员（Windows 为主，少量 macOS）。
**验收口径**：下载一个压缩包 -> 解压双击 -> 浏览器自动打开界面 ->
完成首次配置向导 -> 当天就能用上监测中心；后续用上工作台。

**非目标**：
- 应用商店分发、代码签名证书采购（成本问题，见 §7 已知问题）
- 自动更新（v1 只做"发现新版本"提示 + 跳转 Release 页）
- 移动端 App（响应式 Web 已覆盖）

## 2. 三种发行形态，一份产品

| 形态 | 受众 | 入口 | 说明 |
|---|---|---|---|
| **桌面发行版**（本档主角） | 实验室同学 | Releases 下载 zip，双击可执行 | PyInstaller 打包，本机模式 |
| Docker | 服务器用户 | `docker pull`（已有 [docker/](../docker/)） | 加 `RUN_MODE=server` 携带 web/mcp |
| 源码 + uv | 开发者 | git clone + `uv sync`（现有方式） | 不变 |

Web 优先架构（SPA + API）在这里兑现价值：**一份产品三种形态**，
桌面发行版 = "本机跑一个只监听 127.0.0.1 的 Web 服务 + 壳"。

### 2.1 壳策略：sidecar 是本体，壳可以换（关键决策）

**先摆一个容易被误解的技术事实**：整个后端（采集/AI/存储/工作台引擎）
是 Python，而 Electron 是 Node.js + Chromium 的壳，**跑不了 Python**。
所以选 Electron 并不消解"打包 Python 服务"的工作，而是：

```
Electron 版 = Electron 壳（Node 工具链打包）
            + PyInstaller sidecar（Python 工具链打包，与浏览器方案完全同一份）
            + 壳↔sidecar 的进程管理（spawn/回收/端口冲突/崩溃恢复）
```

即 **Electron 是叠加层，不是替代品**。风险大头（体积、杀软误报、
路径兼容、首启向导）全在 sidecar 侧，无论选哪个壳都得先做。

**壳方案对比**：

| 维度 | A · 默认浏览器 | A+ · pywebview 窗口 | B · Electron 壳 | C · Tauri 壳 |
|---|---|---|---|---|
| Python 打包 | PyInstaller（必做） | PyInstaller（必做） | PyInstaller sidecar（必做） | 同左 |
| 新增工具链 | 无 | 无（纯 Python 库） | Node + electron-builder | Rust + cargo |
| 观感 | 浏览器标签页（Jupyter/ComfyUI 式） | 独立应用窗口（系统 WebView：Win=WebView2，mac=WKWebView） | 完整桌面应用 | 完整桌面应用 |
| 托盘/原生菜单 | ✗ | 部分（配 pystray） | ✅ | ✅ |
| 自动更新 | ✗（提示+跳转 Release 页） | ✗ | ✅ electron-updater | ✅ |
| 体积增量 | 0 | ≈1MB | +100~150MB | +10MB 左右 |
| 进程管理 | 低（开完浏览器即走） | 中 | **高**（双进程生命周期/僵尸/端口占用） | 高 |
| CI | 单 matrix | 单 matrix | 双产物组装 | 双产物 + Rust 缓存 |
| 维护栈数 | 1 | 1 | 2 | 2（且 Rust 对本项目冷门） |
| 初始打包工作量 | ~1–2 天 | +0.5 天 | **+3–5 天** | +4–6 天 |

**结论（已定档，2026-08-26）**：

1. **v1 = pywebview 壳（B 类）**，不用浏览器方案也不上 Electron。
   理由：产品愿景是"双击 -> 独立窗口 -> 向导 -> 仪表盘"的桌面观感
   （浏览器标签页差一口气，Electron 双工具链不值）；pywebview 以
   约半天成本拿到该观感，且保持单 Python 栈。
   **两个兜底**：① webview 初始化失败（老机器缺 WebView2 运行时）->
   自动降级为开默认浏览器；② 端口已被占用（重复双击）-> 在已有实例
   上开新窗口。窗口关闭 = 应用退出（桌面语义），浏览器兜底模式下
   为"服务常驻、标签页可关"
2. **Electron = 触发式升级项（不做预防性建设）**，触发条件：
   ① 分发规模超出实验室（对外公开发布且装机量重要）；② 用户高频
   反馈要托盘常驻/原生体验；③ 自动更新成为支持负担。
   届时**复用同一份 sidecar**，只新增壳工程，前期工作零作废
3. 首启向导（填 API key 开跑）是网页，**三种壳下行为一致**，
   不是选任何特定壳的理由
4. **施工顺序按风险排**：先做 sidecar（PyInstaller/数据目录/本机模式/
   向导）并用浏览器形态验收--此时已是可用产品；再包 pywebview 窗口。
   pywebview 出任何平台问题都不影响交付

这个顺序的实质：先啃硬骨头（sidecar），壳作为化妆品后置。

## 3. 运行模式（与 02-D9 对应）

```
                ┌──────────┬──────────────┬──────────────┐
                │ 本机模式   │ 工作站模式     │ Docker 模式   │
├───────────────┼──────────┼──────────────┼──────────────┤
│ 进程拓扑        │ 单进程     │ systemd 多单元 │ 容器内常驻     │
│ 监听            │ 127.0.0.1 │ 127.0.0.1+隧道 │ 0.0.0.0:8080  │
│ 调度            │ 进程内线程  │ systemd timer │ supercronic   │
│ 配置首启向导     │ ✅ 允许    │ ❌ 禁用        │ ❌ 禁用        │
│ API Key        │ 首启生成   │ env 注入       │ env 注入       │
│ 信任假设        │ 用户=机主  │ 公网不可信      │ 取决于网络位置  │
└───────────────┴──────────┴──────────────┴──────────────┘
```

**本机模式识别**：`--mode local` CLI 参数（发行版快捷方式写死），
或检测到无 `TRENDRADAR_ENV=prod` 且绑定 127.0.0.1 时默认。
App 以 **工厂函数** 构造（`create_app(mode=...)`），调度器以**线程组件**
而非 systemd 前提实现--这是 02-D9 要求"单进程可内嵌"的具体含义。

## 4. 首次运行体验（本机模式专属）

```
双击 TrendRadar.exe
  -> 控制台/托盘提示 + 自动打开 http://127.0.0.1:8080
  -> 向导页（Web UI，仅 local 模式挂载）：
     ① 语言（中/英）
     ② AI 提供商与 Key（复用 config.ai 的多供应商支持）
     ③ 关注词（可跳过，用默认）
     ④ 通知渠道（可跳过）
     ⑤ 时区
  -> 写 config.yaml + 生成 API Key -> 进入仪表盘
  -> 首次抓取立即执行一次（后台）
```

**安全边界**：向导端点（`POST /api/setup/*`）**只在 local 模式注册路由**，
工作站/Docker 模式下这些路由根本不存在（不是隐藏，是不挂载）。
向导完成即自锁（config 存在后拒绝再写）。

## 5. 数据与配置落位（按 OS 惯例）

| 内容 | Windows | macOS | Linux |
|---|---|---|---|
| 配置/数据库/产物 | `%APPDATA%\TrendRadar\` | `~/Library/Application Support/TrendRadar/` | `~/.local/share/trendradar/` |
| 日志 | 同上 `logs/` | 同上 | 同上 |

单文件可执行的工作目录与此分离（程序文件不可写）。
升级 = 下载新版替换可执行文件，数据原地不动。
（`output/` 的相对路径逻辑需支持可配置的数据根目录--
管线现有 `data_dir` 概念已存在，排期时确认贯穿。）

## 6. 打包与发布流水线

```
GitHub Actions（新增 release.yml，tag 触发 v*）：
  matrix: [windows-latest, macos-latest(arm64), ubuntu-latest]
  steps:
    - uv sync（复用 uv.lock）
    - 前端 dist 已入库，无需 Node（D4）
    - pyinstaller trendradar_desktop.spec
      （含 Noto Sans SC 字体、默认模板、prompts）
    - zip -> 上传到 GitHub Release
```

体积预期：litellm/boto3/requests 全家桶约 120~200MB（压缩前）。
**优化预留**：boto3 仅远程存储（R2）需要，PyInstaller spec 里可做
条件排除；litellm 懒加载（仅配置了 AI 才 import）。

> 若升级 Electron 壳（§2.1 的 v2）：本流水线产物 sidecar 不变，
> 追加 electron-builder 作业把壳与 sidecar 组装为安装包，
> matrix 扩为三平台双产物；CI 复杂度翻倍是 v2 的主要代价之一。

## 7. 已知问题与对策（诚实清单）

| 问题 | 影响 | 对策 |
|---|---|---|
| PyInstaller 触发杀软误报 | 实验室同学被吓退 | v1：文档说明 + 白名单指引；中期：购买代码签名（EV 证书，年费数千，产品化后再说） |
| 包体积偏大 | 下载慢 | 条件排除依赖 + zip；实验室内网可镜像 |
| WeasyPrint 原生依赖 | Windows 打包复杂 | PDF 渲染器按 08 §4 备选 fpdf2 决断 |
| 无自动更新 | 用户停在旧版 | v1：启动时调现有版本检查（`version` 文件机制已有，MCP 的 check_version 已实现对比逻辑，抽出来复用）-> 界面横幅提示新版；v2 升级 Electron 壳后由 electron-updater 解决 |
| 家宽/内网穿透不在发行版范围 | 桌面版只能本机访问 | 这是有意的：对外发布走 05 的工作站方案，两种需求两种形态 |

## 8. 对现有设计的最小侵入点

| 侵入点 | 内容 | 时机 |
|---|---|---|
| `create_app(mode)` 工厂化 | 02-D9 已声明 | Phase 1 骨架就按此写（零额外成本） |
| 数据根目录可配置 | §5 落位需要 | Phase 1 顺带（路径解析集中在 config） |
| setup 向导路由 | 仅 local 模式挂载 | Track B 排期时实现 |
| release.yml CI | 打包流水线 | Track B 排期时实现 |
