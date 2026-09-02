#!/usr/bin/env bash
# TrendRadar Web API smoke 测试（design/07 P1 验收；两级模式）
#
# 用法：
#   实机模式：bash smoke_api.sh [BASE_URL]           # 默认 http://127.0.0.1:8080
#             （要求当天已跑过管线；经域名验证直接传 https://域名）
#   夹具模式：bash smoke_api.sh --fixture            # 本地自测：样例库映射为今天，
#             TRENDRADAR_DATA_ROOT 隔离 + 临时 uvicorn，不污染真实 output/
#
# 断言：信封字段 / cached 标志 / 401 / 404 / 路径穿越 / prod 关 docs /
#       JSON 404 / 限流 429（放最后，避免污染令牌桶）/ output 文件集不变

set -uo pipefail

MODE="live"
BASE_URL="http://127.0.0.1:8080"
if [[ "${1:-}" == "--fixture" ]]; then
    MODE="fixture"
elif [[ -n "${1:-}" ]]; then
    BASE_URL="$1"
fi

PASS=0; FAIL=0; FAILED_CASES=()
say()  { printf '%s\n' "$*"; }
ok()   { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); FAILED_CASES+=("$1"); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }

# 断言助手：expect <名称> <期望状态码> <curl 参数...>
expect() {
    local name="$1" want="$2"; shift 2
    local got
    got="$(curl -s -o /tmp/smoke_body.$$ -w '%{http_code}' "$@")"
    if [[ "$got" == "$want" ]]; then ok "$name ($got)"; else bad "${name}（期望 $want 实得 ${got}：$(head -c 120 /tmp/smoke_body.$$)）"; fi
    rm -f /tmp/smoke_body.$$
}
# JSON 字段断言：expect_json <名称> <期望状态码> <python 表达式（body 变量）> <curl 参数...>
expect_json() {
    local name="$1" want="$2" expr="$3"; shift 3
    local got
    got="$(curl -s -o /tmp/smoke_body.$$ -w '%{http_code}' "$@")"
    if [[ "$got" != "$want" ]]; then
        bad "${name}（期望 $want 实得 ${got}）"; rm -f /tmp/smoke_body.$$; return
    fi
    if python3 -c "
import json,sys
body = json.load(open('/tmp/smoke_body.$$'))
sys.exit(0 if ($expr) else 1)
" 2>/dev/null; then ok "$name"; else bad "${name}（字段断言失败：$(head -c 120 /tmp/smoke_body.$$)）"; fi
    rm -f /tmp/smoke_body.$$
}

TODAY="$(date +%F)"
YESTERDAY="$(date -d yesterday +%F 2>/dev/null || date -v-1d +%F)"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# 缺库日期：>365 天的日期会被日期校验 400 拒绝，缺库 404 断言必须用近端日期
# fixture：数据根只有今天一个库 → 固定 3 天前必缺
# live：从昨天向前找第一个仓库 output/news 里没有的日期（10 天全有则跳过该断言）
MISSING_DATE="$(date -d '3 days ago' +%F 2>/dev/null || date -v-3d +%F)"
if [[ "$MODE" == "live" ]]; then
    for i in 1 2 3 4 5 6 7 8 9 10; do
        CAND="$(date -d "$i days ago" +%F 2>/dev/null || date -v-${i}d +%F)"
        if [[ ! -f "$REPO_ROOT/output/news/${CAND}.db" ]]; then MISSING_DATE="$CAND"; break; fi
    done
fi

# ════════════════════════════════════════════
# 夹具模式准备
# ════════════════════════════════════════════
if [[ "$MODE" == "fixture" ]]; then
    say "── 夹具模式：样例库 → TRENDRADAR_DATA_ROOT(<today>.db) ──"
    cd "$REPO_ROOT"

    LATEST_DB="$(ls output/news/*.db 2>/dev/null | sort | tail -1)"
    [[ -n "$LATEST_DB" ]] || { echo "output/news 无样例库，无法跑夹具模式"; exit 1; }

    FIXTURE_DIR="$(mktemp -d)"
    mkdir -p "$FIXTURE_DIR/output/news"
    cp "$LATEST_DB" "$FIXTURE_DIR/output/news/${TODAY}.db"
    BEFORE_SNAPSHOT="$(ls output/news | sort | md5)"

    PORT=8899
    if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
        echo "端口 $PORT 已被占用（疑似上次运行的残留 web_server），请先清理：lsof -ti :$PORT | xargs kill"; exit 1
    fi
    # 注入已知 key：POST 401 断言需要服务端已配置 key（未配置时写端点是 503 fail-closed 而非 401）
    TRENDRADAR_DATA_ROOT="$FIXTURE_DIR" TRENDRADAR_API_KEY="smoke-fixture-key" \
        .venv/bin/python -m web_server --host 127.0.0.1 --port $PORT >/tmp/smoke_web.log 2>&1 &
    WEB_PID=$!
    BASE_URL="http://127.0.0.1:$PORT"
    for _ in $(seq 1 30); do
        curl -sf "$BASE_URL/api/system/status" >/dev/null 2>&1 && break
        sleep 0.5
    done
    say "  临时服务已起（pid $WEB_PID, ${BASE_URL}）"
fi

# ════════════════════════════════════════════
# 断言
# ════════════════════════════════════════════
say "── $MODE 模式断言（${BASE_URL}）──"

# 1. 信封契约
expect_json "system/status 信封"        200 "body['success'] is True and 'data' in body and 'cached' in body and 'generated_at' in body" "$BASE_URL/api/system/status"
expect_json "status 无路径泄露"          200 "not any(k in json.dumps(body) for k in ('project_root','/opt/','/Users/'))" "$BASE_URL/api/system/status"
expect_json "system/dates"              200 "body['success'] is True" "$BASE_URL/api/system/dates"
expect_json "system/schedule 三态"       200 "body['success'] is True and 'enabled' in body['data']" "$BASE_URL/api/system/schedule"
expect_json "system/health/sources"     200 "body['success'] is True" "$BASE_URL/api/system/health/sources"

# 2. 缓存标志（第二击命中）
curl -s "$BASE_URL/api/system/dates" >/dev/null
expect_json "缓存第二击 cached=true"      200 "body['cached'] is True" "$BASE_URL/api/system/dates"

# 3. news
expect_json "news/latest"               200 "body['success'] is True" "$BASE_URL/api/news/latest?limit=5"
expect_json "news/date 今天"             200 "body['success'] is True" "$BASE_URL/api/news/date/$TODAY?limit=5"
expect_json "坏日期 400"                 400 "body['error']['code'] == 'BAD_REQUEST'" "$BASE_URL/api/news/date/2025-13-99"
if [[ -n "$MISSING_DATE" ]]; then
    expect_json "缺库日期 404 DATE_NOT_FOUND" 404 "body['error']['code'] == 'DATE_NOT_FOUND'" "$BASE_URL/api/news/date/$MISSING_DATE"
else
    say "  （跳过缺库 404：近 10 天每日都有库）"
fi
expect_json "news/search range 表达式"   200 "body['success'] is True" "$BASE_URL/api/news/search?query=%E4%B8%AD%E5%9B%BD&range=%E6%9C%80%E8%BF%917%E5%A4%A9&limit=10"
expect_json "topics/trending"           200 "body['success'] is True" "$BASE_URL/api/topics/trending?top_n=5"

# 4. analytics（慢端点各一次）
expect_json "analytics/viral"           200 "body['success'] is True" "$BASE_URL/api/analytics/viral"
expect_json "analytics/topic-trend"     200 "body['success'] is True" "$BASE_URL/api/analytics/topic-trend?topic=%E4%B8%AD%E5%9B%BD&range=%E6%9C%80%E8%BF%917%E5%A4%A9"

# 5. rss / reports
expect_json "rss/feeds-status"          200 "body['success'] is True" "$BASE_URL/api/rss/feeds-status"
expect_json "reports 列表（缺失=空数组）" 200 "body['success'] is True" "$BASE_URL/api/reports"

# 6. 认证
expect_json "POST 无 key 401"           401 "body['error']['code'] == 'UNAUTHORIZED'" -X POST "$BASE_URL/api/pipeline/run"
expect_json "POST 错 key 401"           401 "body['error']['code'] == 'UNAUTHORIZED'" -X POST -H "X-API-Key: wrong-key" "$BASE_URL/api/pipeline/run"

# 7. 路径穿越变体（design/06 §8）
expect "穿越 ..%2f config"              404 "$BASE_URL/api/reports/..%2f..%2f..%2fconfig%2fconfig.yaml/html"
expect "穿越 ../../../../etc"           404 "$BASE_URL/api/reports/../../../../etc/passwd/html"
expect "穿越 .... 变体"                 400 "$BASE_URL/api/reports/..../html"

# 8. JSON 404（未匹配路由回 JSON 信封，非 HTML）
expect_json "不存在的 API 路由 JSON 404"  404 "body['error']['code'] == 'NOT_FOUND'" "$BASE_URL/api/nonexistent"

# 9. prod 关 docs（仅 prod 环境断言：服务端 TRENDRADAR_ENV=prod）
if [[ "${SMOKE_CHECK_PROD:-0}" == "1" ]]; then
    expect "prod /docs 404"             404 "$BASE_URL/docs"
    expect "prod /redoc 404"            404 "$BASE_URL/redoc"
else
    say "  （跳过 prod docs 检查——SMOKE_CHECK_PROD=1 时启用）"
fi

# 10. 限流 429（放最后：analytics 10/min 桶会被打穿）
say "  （限流测试：连打 analytics 12 次）"
LAST=""
for _ in $(seq 1 12); do
    LAST="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/analytics/predict")"
done
if [[ "$LAST" == "429" ]]; then ok "限流 429 生效"; else bad "限流 429（最后状态 ${LAST}）"; fi

# 11. 夹具模式收尾：主仓库 output/news 文件集不变
if [[ "$MODE" == "fixture" ]]; then
    kill "$WEB_PID" 2>/dev/null; wait "$WEB_PID" 2>/dev/null
    AFTER_SNAPSHOT="$(ls output/news | sort | md5)"
    if [[ "$BEFORE_SNAPSHOT" == "$AFTER_SNAPSHOT" ]]; then
        ok "output/news 文件集不变（只读连接未误建库）"
    else
        bad "output/news 文件集变化！before=$BEFORE_SNAPSHOT after=$AFTER_SNAPSHOT"
    fi
    rm -rf "$FIXTURE_DIR"
fi

# ════════════════════════════════════════════
say ""
say "结果：$PASS 通过 / $FAIL 失败"
if [[ $FAIL -gt 0 ]]; then
    printf '  失败项：\n'; printf '   - %s\n' "${FAILED_CASES[@]}"
    exit 1
fi
say "smoke 全绿 ✓"
