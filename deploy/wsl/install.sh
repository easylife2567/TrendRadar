#!/usr/bin/env bash
# TrendRadar WSL 工作站一键安装（design/05 §4 七步）
#
# 用法：
#   sudo bash install.sh [--project-root /opt/trendradar] [--run-user <user>] [--with-mcp]
#
# 步骤：前置检查 → uv sync → 渲染 systemd 单元 → 生成 API key →
#       cloudflared 检测 → enable --now → 自检
#
# 注意：须以 root 运行（写 /etc/trendradar 与 /etc/systemd/system）。
# 与 Docker 部署互斥：docker compose 的 WEBSERVER_PORT 也占 8080，
# 同机请二选一（design/07 差异#7）。

set -euo pipefail

PROJECT_ROOT="/opt/trendradar"
RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
WITH_MCP=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-root) PROJECT_ROOT="$2"; shift 2 ;;
        --run-user)     RUN_USER="$2"; shift 2 ;;
        --with-mcp)     WITH_MCP=1; shift ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

cd "$PROJECT_ROOT"
TEMPLATE_DIR="$(dirname "$0")"

say()  { printf '\n\033[1;36m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { printf '\033[1;31m[失败]\033[0m %s\n' "$*" >&2; exit 1; }

# ────────────────────────────────────────────
# 1. 前置检查：systemd / uv / 端口 / 目录
# ────────────────────────────────────────────
say "1/7 前置检查"

[[ -d /run/systemd/system ]] || fail "systemd 未运行。WSL 需先启用：/etc/wsl.conf 加 [boot]\nsystemd=true 后 wsl.exe --shutdown 重启"
command -v uv >/dev/null 2>&1 || fail "uv 未安装：curl -LsSf https://astral.sh/uv/install.sh | sh"
[[ -f pyproject.toml ]] || fail "请在仓库根运行（当前目录无 pyproject.toml）"

# 端口读 config.yaml 的 web 段（非硬编码）
read_web_port() {
    uv run python - <<'EOF'
import yaml
cfg = yaml.safe_load(open("config/config.yaml", encoding="utf-8")) or {}
print((cfg.get("web") or {}).get("port", 8080))
EOF
}
WEB_PORT="$(read_web_port)" || fail "无法读取 config.yaml 的 web.port"
MCP_PORT=3333

for p in "$WEB_PORT" "$MCP_PORT"; do
    if ss -ltn 2>/dev/null | grep -q ":${p} "; then
        fail "端口 $p 已被占用（若装过 docker compose 版 TrendRadar，两者互斥，先停 docker）"
    fi
done
[[ -d output/news ]] || echo "  提示：output/news 不存在——首次管线运行后才有数据，Web 先显示空态属正常"
say "  systemd OK / uv OK / 端口 $WEB_PORT+$MCP_PORT 空闲 / 用户 $RUN_USER"

# ────────────────────────────────────────────
# 2. uv sync（锁定依赖）
# ────────────────────────────────────────────
say "2/7 uv sync --locked"
uv sync --locked || fail "uv sync 失败"

# ────────────────────────────────────────────
# 3. 渲染 systemd 单元
# ────────────────────────────────────────────
say "3/7 渲染 systemd 单元（web / scheduler.timer$( [[ $WITH_MCP -eq 1 ]] && echo ' / mcp' )）"
render() {
    sed -e "s|@PROJECT_ROOT@|$PROJECT_ROOT|g" \
        -e "s|@RUN_USER@|$RUN_USER|g" \
        -e "s|@WEB_PORT@|$WEB_PORT|g" \
        -e "s|@MCP_PORT@|$MCP_PORT|g" \
        "$1" > "/etc/systemd/system/$2"
    echo "  /etc/systemd/system/$2"
}
render "$TEMPLATE_DIR/trendradar-web.service.template"        "trendradar-web.service"
render "$TEMPLATE_DIR/trendradar-scheduler.service.template"  "trendradar-scheduler.service"
cp  "$TEMPLATE_DIR/trendradar-scheduler.timer" /etc/systemd/system/trendradar-scheduler.timer
echo "  /etc/systemd/system/trendradar-scheduler.timer"
if [[ $WITH_MCP -eq 1 ]]; then
    render "$TEMPLATE_DIR/trendradar-mcp.service.template" "trendradar-mcp.service"
fi

# ────────────────────────────────────────────
# 4. API key：无则生成（root:600）
# ────────────────────────────────────────────
say "4/7 API key（/etc/trendradar/web.env）"
mkdir -p /etc/trendradar
chmod 700 /etc/trendradar
if [[ -s /etc/trendradar/web.env ]] && grep -q "^TRENDRADAR_API_KEY=" /etc/trendradar/web.env; then
    echo "  已存在，保留（key 不回显）"
else
    KEY="$(openssl rand -hex 32)"
    {
        echo "TRENDRADAR_API_KEY=$KEY"
        echo "TRENDRADAR_ENV=prod"
    } > /etc/trendradar/web.env
    chmod 600 /etc/trendradar/web.env
    echo "  已生成新 key（root:600）。查看：sudo cat /etc/trendradar/web.env"
fi

# ────────────────────────────────────────────
# 5. cloudflared 检测（可选组件，不强装）
# ────────────────────────────────────────────
say "5/7 cloudflared 检测"
if command -v cloudflared >/dev/null 2>&1; then
    echo "  已安装。隧道配置参考：deploy/wsl/cloudflared-config.example.yml"
    systemctl list-unit-files 2>/dev/null | grep -q cloudflared \
        || echo "  提示：cloudflared.service 未安装——公网发布前需完成（design/05 §3.3）"
else
    echo "  未安装（跳过）。公网发布需：官方 apt 源安装 + tunnel create + /etc/cloudflared/config.yml"
fi

# ────────────────────────────────────────────
# 6. 启动
# ────────────────────────────────────────────
say "6/7 daemon-reload + enable --now"
systemctl daemon-reload
systemctl enable --now trendradar-web.service
systemctl enable --now trendradar-scheduler.timer
[[ $WITH_MCP -eq 1 ]] && systemctl enable --now trendradar-mcp.service

# ────────────────────────────────────────────
# 7. 自检
# ────────────────────────────────────────────
say "7/7 自检"
sleep 3
for unit in trendradar-web.service trendradar-scheduler.timer; do
    state="$(systemctl is-active "$unit" || true)"
    [[ "$state" == "active" ]] || { journalctl -u "$unit" -n 20 --no-pager; fail "$unit 未 active"; }
    echo "  $unit: active"
done
[[ $WITH_MCP -eq 1 ]] && echo "  trendradar-mcp.service: $(systemctl is-active trendradar-mcp.service || true)"

if curl -sf "http://127.0.0.1:${WEB_PORT}/api/system/status" | grep -q '"success":true'; then
    echo "  /api/system/status: OK"
else
    journalctl -u trendradar-web.service -n 20 --no-pager
    fail "API 自检失败"
fi

say "安装完成"
cat <<TIP

  下一步：
  1. 公网发布：cloudflared 隧道（参考 deploy/wsl/cloudflared-config.example.yml）
  2. 前端验证：浏览器打开 https://<你的域名>/（手机 4G 再验一次，排除局域网假象）
  3. 破坏性自愈测试：Windows 侧 wsl.exe --shutdown 后等 30s 重开，三单元应自愈
  4. 实机 smoke：bash deploy/wsl/smoke_api.sh http://127.0.0.1:${WEB_PORT}
TIP
