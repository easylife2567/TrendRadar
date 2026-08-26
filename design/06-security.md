# 06 · 安全设计

> 上游文档：[02-architecture.md](02-architecture.md) · [05-deployment-wsl.md](05-deployment-wsl.md)
> 背景：把一台家用 WSL 工作站的服务发布到公网。默认姿态：**不信任公网**。

## 1. 信任边界

```
[不可信] 公网用户
   │
   ▼
[半可信] Cloudflare 边缘：TLS 终止 · WAF · 限流 ·（可选）Access 认证
   │  仅隧道流量（出站 443），无任何入站端口
   ▼
[可信] WSL 内部：所有服务仅监听 127.0.0.1
   │
   ├── trendradar-web  :8080   ← 唯一面向公网的应用
   ├── trendradar-mcp  :3333   ← 仅 /mcp 路径经隧道可达
   └── scheduler               ← 不触网
[敏感] config/（AI key、推送 token）、output/（数据）、web.env（API key）
```

关键结构保证：**攻击面收敛为 web 进程一个**；MCP 只暴露标准 /mcp 端点
（FastMCP 自身协议层）；scheduler 与配置完全不触网。

## 2. 网络层

1. **零入站端口**：WSL/Windows 不开任何端口转发；唯一通道是
   cloudflared 出站连接。Windows 防火墙保持默认（拒绝入站）
2. **服务绑定 127.0.0.1**：web/mcp 均如此（05 §3 已把 MCP 从
   `start-http.sh` 的 `0.0.0.0` 收紧）。局域网直连是显式 opt-in
   （config `web.host: 0.0.0.0`），文档注明风险
3. **Cloudflare 侧**：
   - DNS 记录开代理（橙云），源站 IP 永不暴露（本来就无公网 IP）
   - WAF 托管规则默认集 + 速率限制规则（见 §4）
   - Bot Fight Mode 开启

## 3. 应用层

### 3.0 运行模式的信任差异（Track B 声明，边界现在立好）

本档默认姿态（不信任公网）适用于**工作站 / Docker 模式**。
桌面本机模式（[09-release-packaging.md](09-release-packaging.md)）信任假设
不同，边界如下：

| | 本机模式（桌面发行版） | 工作站 / Docker 模式 |
|---|---|---|
| 监听 | 仅 127.0.0.1 | 127.0.0.1 + 隧道 / 容器网络 |
| 用户假设 | 用户 = 机主 | 公网访客不可信 |
| 首启向导（写配置） | ✅ 允许，完成即自锁 | ❌ 路由**不挂载**（非隐藏） |
| API Key | 首启自动生成 | env 注入（05 §4.4） |
| `/docs` | 可开（本机调试友好） | prod 模式关闭（§5） |

**红线（两种模式一致）**：配置内容与密钥永不通过 API 回显；
路径穿越防护、参数校验、限流护栏不因模式放宽。

### 3.1 认证

| 层 | 机制 | 说明 |
|---|---|---|
| 推荐（个人） | **Cloudflare Access** | 在边缘做邮箱 OTP / GitHub 登录，应用零开发即获得认证；云函数免费额度 50 用户内免费 |
| 应用层（必备兜底） | `X-API-Key` | 🔑 写/触发/AI 端点强制；读端点 `require_read_key` 可开 |
| 两者叠加 | Access + Key | 公开只读给访客、Key 给自己的写操作 |

API Key 管理：
- 生成：`openssl rand -hex 32`，存放 `/etc/trendradar/web.env`（root:600），
  systemd `EnvironmentFile=` 注入，**不进** config.yaml / git
- 校验：恒定时间比较（`hmac.compare_digest`）
- 轮换：改 env 重启即可；设计上允许多 key（v2 再做）

### 3.2 授权矩阵

| 端点类别 | API Key | 说明 |
|---|---|---|
| 只读查询（news/topics/rss/reports） | 默认免 | 可全局收紧 |
| 系统状态/健康 | 免 | 只暴露运行状态，无敏感配置 |
| 手动抓取 / 完整管线 / 情感 AI | **必须** | 花钱或改变状态的操作必须挡 |
| 工作台写操作（Track B：select/draft/generate/export） | **必须** | 改变任务状态、产出对外交付物，必须挡；本机模式亦不豁免（防浏览器内恶意页面借 localhost 发写请求） |
| 配置内容 | **永不在 API 暴露** | `ConfigManagementTools` 的能力**不**映射到任何 Web 端点（01 非目标 #1；local 模式首启向导是唯一且一次性的例外，见 §3.0） |

### 3.3 输入防护

- FastAPI/pydantic 类型校验；日期正则 `^\d{4}-\d{2}-\d{2}$`；
  `limit` 上限钳制；platforms 白名单校验（复用
  [mcp_server/utils/validators.py](../mcp_server/utils/validators.py)）
- 报告文件服务：§2.6 的路径穿越防护 + 扩展名白名单 + `resolve()` 归一化
- SQL：全部经由 tools 层参数化查询（现状即如此），Web 层禁止拼 SQL

### 3.4 进程加固（systemd，05 §3.1 已含）

`NoNewPrivileges` / `ProtectSystem=strict` /
`ReadWritePaths=output`（仅情感结果表）/ `PrivateTmp`。
运行用户非 root，无 sudo。

## 4. 限流与滥用防护

| 位置 | 规则 |
|---|---|
| CF 边缘 | 单 IP 60 req/min（可再按路径细分）；`/api/analytics/*` 10 req/min |
| 应用令牌桶 | 与 CF 冗余的进程内限流（防直接打源站的可能路径） |
| AI 端点 | `Semaphore(1)` 串行 + 每日 50 次上限 + 结果缓存 6h（03 §2.4） |
| 管线触发 | 并发去重：运行中再触发返回 409 + 当前 unit 名 |

## 5. 信息暴露最小化

- `TRENDRADAR_ENV=prod` 时关闭 `/docs`、`/redoc`、debug 日志
- 错误响应不带堆栈；`AI_EXECUTION_FAILED` 只透传原因摘要，
  绝不含 API key 片段
- `/api/system/status` 输出经字段白名单（不含路径、版本号可选隐藏、
  不含任何配置值）
- 日志（journal）只记：时间、路径、状态码、耗时、IP；不记查询参数
  中的敏感内容（本系统参数无敏感内容，搜索词属于低敏）

## 6. 威胁清单（STRIDE 简化版）

| 威胁 | 场景 | 缓解 |
|---|---|---|
| 爬虫/滥用 | 公网脚本狂刷 AI 端点烧 token | 认证 + 限流 + 每日上限 + 缓存（§4） |
| 路径穿越 | `/api/reports/../../config/config.yaml` | 03 §2.6 三重防护 |
| 注入 | 搜索词/日期参数注入 | 参数化查询 + pydantic 校验 |
| 凭据泄露 | API key 进 git/配置 | env 文件 + gitignore + 生成脚本 |
| DoS（应用层） | 慢端点并发雪崩 | 线程池上限 + 限流 + Semaphore |
| 供应链 | 依赖投毒 | 版本全 pinned（现状）+ uv.lock；升级走 PR |
| WSL 提权逃逸 | 理论面 | 非本文档范围，但服务进程最小权限降低了爆炸半径 |
| 隧道凭据失窃 | cloudflared cert 被复制 | 文件权限 root:600；失窃只需 CF 面板删隧道，数据不直接暴露 |

## 7. 事件响应

- **怀疑 key 泄露**：`/etc/trendradar/web.env` 换 key + `systemctl restart trendradar-web`，一分钟内生效
- **怀疑隧道泄露**：CF Zero Trust 面板删除 tunnel + 轮换 cert，服务即断
- **应急下线**：CF DNS 切灰云/删除记录，或 `systemctl stop cloudflared`，
  本地服务不受影响

## 8. 验收清单

- [ ] 无 Key 调 `/api/pipeline/run` 返回 401；带 Key 202
- [ ] `curl https://域名/api/reports/..%2f..%2fconfig%2fconfig.yaml` 类变体均 404/400
- [ ] `https://域名/docs` 返回 404（prod 模式）
- [ ] AI 端点第 51 次/日调用返回 429 + Retry-After
- [ ] 从外网扫描：8080/3333 端口不可达（nmap 家宽 IP）
- [ ]（若启用 Access）未登录浏览器访问域名跳转 CF 登录页
