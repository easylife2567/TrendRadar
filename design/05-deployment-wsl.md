# 05 · WSL 工作站部署方案

> 上游文档：[02-architecture.md](02-architecture.md) · 配套：[06-security.md](06-security.md)
> 产出物：`deploy/wsl/` 目录（安装脚本、systemd 单元、cloudflared 配置模板、文档）

## 0. 前提与定位

- WSL 发行版：Ubuntu 22.04+（systemd 支持）
- Windows 11 22H2+（WSL 0.67+）或已验证 systemd 可用的版本
- 已有托管在 Cloudflare 的域名（项目官网 `sandev.cc` 同账号即可）
- **定位**：工作室级可用性（~99%），非产品级 SLA。迁移 VPS 的路径见 §8

## 1. WSL 基础配置

### 1.1 启用 systemd

`/etc/wsl.conf`：

```ini
[boot]
systemd=true

[automount]
options = "metadata"   # 让 Windows 挂载卷支持 Linux 权限位（可选）

# 不设 vmIdleTimeout 的情况下，常驻的 cloudflared 进程会让 VM 保持存活
```

改后 `wsl.exe --shutdown` 重启生效。

### 1.2 防止 WSL 空闲关机

cloudflared 常驻进程本身就阻止了 VM 空闲回收（微软的 idle 判定基于
无进程活动）。若仍观察到被回收，在 Windows 侧加开机任务
`wsl.exe -d <distro> --exec /bin/true`（见 §6）。

### 1.3 网络模式

**不需要改**。所有服务只绑 `127.0.0.1`，唯一出口是 cloudflared 的
出站 443。WSL2 默认 NAT 模式下 IP 漂移、端口转发等问题全部无关紧要--
这是选择隧道方案的最大红利。（若你想局域网直连访问，把 web 的
`host` 配置改 `0.0.0.0` 并用 mirrored 网络模式，见 `config.yaml` web 段，
但默认不这么做。）

## 2. 目录与环境

约定部署路径 `/opt/trendradar`（git clone 或 rsync）：

```bash
/opt/trendradar                # 仓库
├── .venv/                      # uv sync 产物
├── config/config.yaml          # 生产配置（不入库，单独备份）
└── output/                     # 数据（含历史 db，备份对象）
```

Python 环境：`uv sync`（项目已是 uv 管理，[uv.lock](../uv.lock) 锁定版本）。
Node 仅前端开发需要，部署侧不需要（dist 已入库，D4）。

## 3. systemd 单元（模板放 `deploy/wsl/`，安装脚本渲染）

### 3.1 `trendradar-web.service`

```ini
[Unit]
Description=TrendRadar Web Server
After=network.target

[Service]
Type=simple
User=%i                          # 或渲染为实际用户
WorkingDirectory=/opt/trendradar
ExecStart=/opt/trendradar/.venv/bin/python -m web_server --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5
Environment=TRENDRADAR_API_KEY=__SET_ME__
Environment=TRENDRADAR_ENV=prod

# 加固（06 §3 详述）
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/trendradar/output   # 仅情感结果表需要有限写入
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 3.2 `trendradar-scheduler.timer` + `.service`

```ini
# trendradar-scheduler.service
[Unit]
Description=TrendRadar pipeline run (one-shot)

[Service]
Type=oneshot
User=%i
WorkingDirectory=/opt/trendradar
ExecStart=/opt/trendradar/.venv/bin/python -m trendradar
# 管线自身的 schedule/already_executed 决定本次是否实际工作（D6）
```

```ini
# trendradar-scheduler.timer
[Unit]
Description=Trigger TrendRadar pipeline every 15 minutes

[Timer]
OnCalendar=*:0/15
RandomizedDelaySec=120           # 避开整点，对上游 newsnow 友好
Persistent=true                  # 错过的补跑一次

[Install]
WantedBy=timers.target
```

> 周期建议 15 分钟（粒度更细的 `rank_history`），保守可用 30 分钟
> （与 Docker 默认一致）。管线在非活跃时段空转退出，成本可忽略。

### 3.3 `cloudflared.service`

优先用官方包管理器安装（apt 源），配置放 `/etc/cloudflared/config.yml`
（内容见 02-D8），token 模式或 config 模式皆可：

```ini
# /etc/systemd/system/cloudflared.service
[Unit]
Description=cloudflared tunnel agent
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/bin/cloudflared --config /etc/cloudflared/config.yml tunnel run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3.4 手动管线触发（供 `/api/pipeline/run` 使用）

Web 服务用户有权限执行：

```bash
systemd-run --unit=trendradar-manual-$(date +%s) \
  --property=After=trendradar-web.service \
  /opt/trendradar/.venv/bin/python -m trendradar
```

transient unit 的好处：journal 里有完整日志、与 timer 语义一致、
Web 进程不用 fork 长命子进程。需要 Web 服务用户可访问 system bus
（把该用户加入 `systemd-journal` 组并配置 polkit 规则，安装脚本处理；
若环境受限，降级为 `subprocess.Popen` + nohup 日志文件方案）。

### 3.5 `trendradar-mcp.service`（可选）

```ini
ExecStart=/opt/trendradar/.venv/bin/python -m mcp_server.server \
          --transport http --host 127.0.0.1 --port 3333
```

注意：现有 [start-http.sh](../start-http.sh) 绑 `0.0.0.0`，
systemd 部署改为 `127.0.0.1`，对外统一走隧道（06 §2）。

## 4. 安装脚本 `deploy/wsl/install.sh`

```
用法: install.sh [--target /opt/trendradar] [--timer 15|30] [--with-mcp]
步骤:
 1. 前置检查    systemd 可用 / uv 存在 / 端口 8080、3333 空闲
 2. 环境搭建    uv sync（若 .venv 不存在）
 3. 单元渲染    模板 __PLACEHOLDER__ 替换 -> /etc/systemd/system/
 4. API Key     无则 openssl rand -hex 32 生成，写入
                /etc/trendradar/web.env (root:600)，unit 引用
                EnvironmentFile=
 5. cloudflared  检测未安装则提示（或 apt 安装）；校验 config.yml 存在
 6. 启用服务    daemon-reload; enable --now web scheduler.timer cloudflared
 7. 自检        curl 127.0.0.1:8080/api/system/status 应 200；
                systemctl is-active 三个单元；打印外网访问指引
升级: install.sh --upgrade  -> git pull && uv sync && restart web
```

另附 `deploy/wsl/uninstall.sh` 与 `deploy/wsl/README.md`（人肉步骤文档）。

## 5. Windows 侧配合

| 事项 | 做法 |
|---|---|
| 开机自启 WSL | 任务计划程序：登录时运行 `wsl.exe -d <distro> --exec /bin/sh -c "systemctl is-active cloudflared"`（拉起 VM 即触发 systemd 全家桶） |
| 禁止休眠 | 电源计划设置不休眠（工作站定位；或用 `powercfg`） |
| Windows 更新 | 保持「自动重启」开启亦可--systemd `Restart=always` + timer `Persistent=true` 保证重启后自愈 |
| 可选：休眠唤醒后网络自愈 | cloudflared 自带指数退避重连，通常无需干预 |

## 6. 备份与数据留存

- **备份对象**：`output/`（按日 db，唯一不可再生资产）+ `config/`
- **方案**（按需择一，脚本 `deploy/wsl/backup.sh` + systemd timer 每日）：
  1. rsync 到 NAS / 另一台机器
  2. rclone 到对象存储（项目已有 boto3 依赖与 remote storage 概念）
  3. 最简：tar 滚动副本到 Windows 盘（`/mnt/d/backups/`）
- **保留策略**：`StorageManager` 默认 0=无限制，保持；
  若配置了天数，为监测中心建议 ≥ 90 天
- db 文件小（单日几 MB），长期留存成本可忽略

## 7. 可用性预期（诚实声明）

| 事件 | 概率影响 | 恢复 |
|---|---|---|
| WSL/Windows 崩溃重启 | 数分钟不可用 | systemd 全家桶自启 |
| Windows 月度更新 | 最长约 20 分钟 | 同上 |
| 家庭断网/断电 | 直到恢复 | cloudflared 自动重连 |
| 计划外长停机 | 未知 | timer `Persistent` 补跑一次管线 |

**结论**：个人与小团队使用完全够；对外承诺 SLA 前请先迁移（§8）。

## 8. 迁移到 VPS 的路径（未来）

全部组件是标准 Linux 服务：`rsync /opt/trendradar` + 安装脚本在
任何 Ubuntu VPS 上原样跑通；cloudflared 配置原样可用（隧道指向改新机，
或直接 VPS 公网 + Caddy/Nginx TLS）。**本设计不为 WSL 引入任何
专有耦合**，这是把它当"工作站验证产品形态"的正确姿势。

## 9. 验收清单（Phase 0 完成定义）

- [ ] `wsl.conf` systemd 生效：`systemctl` 可用
- [ ] `uv sync` 成功，`python -m trendradar` 手动跑通一轮
- [ ] 三个单元 `systemctl is-active` 均 active
- [ ] `wsl.exe --shutdown` 后从 Windows 侧触发自启，服务全家恢复
- [ ] 公网域名 HTTPS 打开占位页；`/mcp` 路由到 MCP（若启用）
- [ ] 手机 4G 网络可访问（验证非局域网假象）
