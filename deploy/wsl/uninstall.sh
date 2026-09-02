#!/usr/bin/env bash
# TrendRadar WSL 卸载：停用并移除 systemd 单元与 /etc/trendradar
# 数据安全：不动 output/（新闻库与报告），不动仓库本体；web.env 默认保留（含 key）
set -uo pipefail

KEEP_ENV=1
[[ "${1:-}" == "--purge-env" ]] && KEEP_ENV=0

echo "停止并禁用服务..."
systemctl disable --now trendradar-web.service 2>/dev/null || true
systemctl disable --now trendradar-scheduler.timer 2>/dev/null || true
systemctl disable --now trendradar-mcp.service 2>/dev/null || true

echo "移除单元文件..."
rm -f /etc/systemd/system/trendradar-web.service \
      /etc/systemd/system/trendradar-scheduler.service \
      /etc/systemd/system/trendradar-scheduler.timer \
      /etc/systemd/system/trendradar-mcp.service
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

if [[ $KEEP_ENV -eq 1 ]]; then
    echo "保留 /etc/trendradar/web.env（--purge-env 一并删除）"
else
    rm -rf /etc/trendradar
    echo "已删除 /etc/trendradar"
fi
echo "卸载完成。output/ 数据未动；重装运行 install.sh 即可。"
