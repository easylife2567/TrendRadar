#!/usr/bin/env bash
# TrendRadar 数据备份（design/07 Phase 4）：打包 output/（新闻库+报告）+ config/
# 恢复验证：解包后任选一个 .db 用只读连接打开查询一次（验收要求"实际恢复一次"）
#
# 建议用法（timer 化可选）：
#   bash backup.sh /path/to/backup_dir
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-$PROJECT_ROOT/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DEST"
ARCHIVE="$DEST/trendradar-backup-$STAMP.tar.gz"

tar -czf "$ARCHIVE" \
    -C "$PROJECT_ROOT" \
    output config \
    --exclude='output/pipeline_manual.log'

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
echo "备份完成: $ARCHIVE ($SIZE)"
echo ""
echo "恢复验证（强烈建议每次备份后跑一次）:"
echo "  tar -xzf $ARCHIVE -C /tmp/restore-test"
echo "  python -c \"import sqlite3; print(sqlite3.connect('file:/tmp/restore-test/output/news/$(ls $PROJECT_ROOT/output/news | sort | tail -1)', uri=True).execute('select count(*) from news_items').fetchone())\""
echo ""
echo "保留策略建议：find $DEST -name 'trendradar-backup-*.tar.gz' -mtime +14 -delete"
