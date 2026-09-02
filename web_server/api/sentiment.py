"""
情感分析端点（design/03 §2.4，P3）

- GET  /analytics/sentiment/prompt   生成提示词（不执行，供高级用户取用）
- POST /analytics/sentiment/run      提示词 → AiRunner → 落库 → 返回结果（🔑）
- GET  /analytics/sentiment/results  历史结果查询（跨日库扫描）

run 三护栏（D7）：
- asyncio.Semaphore(1) 串行执行；排队后双重检查缓存/库，同参并发只跑一次 AI
- (topic, 范围, platforms, prompt_hash) 进程缓存 6h + 库内 UNIQUE 判重，二次调用秒回
- 每日执行上限（TRENDRADAR_SENTIMENT_DAILY_LIMIT，默认 50）→ 429 + Retry-After
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from mcp_server.services.cache_service import get_cache, make_cache_key

from ..ai_runner import AiDailyLimitExceeded, AiRunner, prompt_hash
from ..cache import cached_call, ttl_for
from ..envelope import ok
from ..errors import ApiError, api_error_from_tool_error
from ..sentiment_store import SentimentStore
from ..settings import WebSettings
from ..tools_registry import get_read_tools
from .deps import get_settings, resolve_range
from .news import _parse_platforms

router = APIRouter(tags=["sentiment"])

# run 结果进程缓存 TTL（design/03 §2.4：6h）
_RUN_TTL = 6 * 3600
# 每日执行上限（env 可覆盖；进程内计数，重启清零属 v1 声明语义）
_DEFAULT_DAILY_LIMIT = 50
# results 历史窗口钳制（天），防全库扫描
_MAX_WINDOW_DAYS = 90

_JSON_CONTRACT = """请严格按以下 JSON 结构输出分析结果：
{
  "distribution": {"positive": <正面新闻条数>, "negative": <负面新闻条数>, "neutral": <中性新闻条数>},
  "platform_breakdown": [
    {"platform": "<平台名>", "positive": <n>, "negative": <n>, "neutral": <n>}
  ],
  "summary": "<整体情感趋势总结，1-3 句>",
  "positive_samples": ["<正面代表标题>", "..."],
  "negative_samples": ["<负面代表标题>", "..."]
}"""

# 模块级单例：AiRunner（每日额度跨请求累计）与串行信号量
_runner: AiRunner | None = None
_run_semaphore = asyncio.Semaphore(1)


def _get_runner(settings: WebSettings) -> AiRunner:
    global _runner
    if _runner is None:
        import os

        try:
            max_daily = int(os.environ.get("TRENDRADAR_SENTIMENT_DAILY_LIMIT", "").strip() or _DEFAULT_DAILY_LIMIT)
        except ValueError:
            max_daily = _DEFAULT_DAILY_LIMIT
        _runner = AiRunner(str(settings.project_root), max_daily=max_daily)
    return _runner


def _unwrap_full(result) -> dict:
    """analyze_sentiment 返回多键结构（ai_prompt/summary/data），不能按单一 data_key 解包"""
    if not isinstance(result, dict) or result.get("success") is False:
        raise api_error_from_tool_error((result or {}).get("error") or {})
    return result


def _resolve_dates(range_expr: str | None, start: str | None, end: str | None) -> tuple[str, str]:
    """日期范围 → 具体起止字符串（未指定 = 今天，与 tools 层默认语义一致）"""
    date_range = resolve_range(range_expr, start, end)
    if date_range is None:
        today = datetime.now().strftime("%Y-%m-%d")
        return today, today
    return date_range["start"], date_range["end"]


# ============================================
# GET /prompt —— 生成提示词（不执行）
# ============================================


@router.get("/analytics/sentiment/prompt", summary="情感分析提示词生成（不执行 AI）")
def sentiment_prompt(
    topic: str | None = Query(None, max_length=100),
    platforms: str | None = Query(None, description="逗号分隔平台 ID"),
    range: str | None = Query(None, alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    settings: WebSettings = Depends(get_settings),
):
    date_start, date_end = _resolve_dates(range, start, end)
    date_range = resolve_range(range, start, end)  # None → tools 层按今天处理
    platform_list = _parse_platforms(platforms)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        result = _unwrap_full(tools["analytics"].analyze_sentiment(
            topic=topic or None, platforms=platform_list or None,
            date_range=date_range, limit=limit,
        ))
        return {
            "summary": result.get("summary", {}),
            "ai_prompt": result.get("ai_prompt", ""),
            "news": result.get("data", []),
            "usage_note": result.get("usage_note", ""),
        }

    params = {
        "topic": topic or "", "platforms": platform_list,
        "date_start": date_start, "date_end": date_end, "limit": limit,
    }
    data, cached = cached_call(
        "sentiment.prompt", params, ttl_for(settings, "sentiment.prompt"), produce
    )
    return ok(data, cached=cached)


# ============================================
# POST /run —— 执行 AI 情感分析（🔑；AuthMiddleware 对 POST 一律强制）
# ============================================


class _RunBody(BaseModel):
    topic: str | None = Field(None, max_length=100)
    platforms: list[str] | None = None
    range: str | None = Field(None, max_length=50)
    start: str | None = None
    end: str | None = None
    limit: int = Field(50, ge=1, le=100)


@router.post("/analytics/sentiment/run", summary="执行 AI 情感分析（串行 + 6h 缓存 + 每日上限）")
async def sentiment_run(
    body: _RunBody | None = None,
    settings: WebSettings = Depends(get_settings),
):
    payload = body or _RunBody()
    date_start, date_end = _resolve_dates(payload.range, payload.start, payload.end)
    date_range = resolve_range(payload.range, payload.start, payload.end)
    platform_list = payload.platforms or None
    platforms_str = ",".join(sorted(payload.platforms)) if payload.platforms else ""
    topic = payload.topic or ""

    # 1. 生成提示词（数据收集；缺数据 → 404 DATE_NOT_FOUND 语义透传）
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce_prompt():
        return _unwrap_full(tools["analytics"].analyze_sentiment(
            topic=topic or None, platforms=platform_list,
            date_range=date_range, limit=payload.limit,
        ))

    analysis = await asyncio.to_thread(produce_prompt)
    prompt = analysis.get("ai_prompt", "")
    ph = prompt_hash(prompt)
    summary = analysis.get("summary", {})

    # 2. 缓存键（含 prompt_hash：底层数据变了即视为新请求）
    cache_params = {
        "topic": topic, "date_start": date_start, "date_end": date_end,
        "platforms": platforms_str, "prompt_hash": ph,
    }
    cache = get_cache()
    cache_key = make_cache_key("sentiment.run", **cache_params)

    def build_data(result: dict, model: str, created_at: str) -> dict:
        return {
            "topic": topic, "date_start": date_start, "date_end": date_end,
            "platforms": platforms_str, "prompt_hash": ph, "model": model,
            "created_at": created_at, "result": result, "summary": summary,
        }

    def db_find():
        store = SentimentStore(settings.output_root)
        return store.find(
            date_end=date.fromisoformat(date_end), topic=topic,
            date_start=date_start, date_end_str=date_end,
            platforms=platforms_str, prompt_hash=ph,
        )

    # 3. 快路径：进程缓存 → 库内历史（排队前检查，命中不占串行队列）
    hit = cache.get(cache_key, ttl=_RUN_TTL)
    if hit is not None:
        return ok(hit, cached=True)
    stored = await asyncio.to_thread(db_find)
    if stored:
        data = build_data(stored["result"], stored["model"], stored["created_at"])
        cache.set(cache_key, data)
        return ok(data, cached=True)

    # 4. AI 执行段：串行 + 排队后双重检查（同参并发只跑一次 AI）
    runner = _get_runner(settings)
    async with _run_semaphore:
        hit = cache.get(cache_key, ttl=_RUN_TTL)
        if hit is not None:
            return ok(hit, cached=True)
        stored = await asyncio.to_thread(db_find)
        if stored:
            data = build_data(stored["result"], stored["model"], stored["created_at"])
            cache.set(cache_key, data)
            return ok(data, cached=True)
        try:
            parsed = await asyncio.to_thread(
                runner.run_json, prompt, _JSON_CONTRACT, None
            )
        except AiDailyLimitExceeded as e:
            raise ApiError(
                429, "RATE_LIMITED", str(e),
                detail={"daily_limit": e.limit, "remaining_today": 0},
                headers={"Retry-After": str(e.retry_after)},
            ) from e
        model = runner.model_name()

    data = build_data(parsed, model, datetime.now().isoformat(timespec="seconds"))

    # 5. 落库（失败即弃，不影响响应）+ 进程缓存
    def db_save():
        SentimentStore(settings.output_root).save(
            date_end=date.fromisoformat(date_end), topic=topic,
            date_start=date_start, date_end_str=date_end,
            platforms=platforms_str, prompt_hash=ph,
            result=parsed, model=model,
        )

    await asyncio.to_thread(db_save)
    cache.set(cache_key, data)
    return ok(data, cached=False)


# ============================================
# GET /results —— 历史结果回看
# ============================================


@router.get("/analytics/sentiment/results", summary="情感分析历史结果（跨日库扫描）")
def sentiment_results(
    topic: str | None = Query(None, max_length=100),
    range: str | None = Query(None, alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    settings: WebSettings = Depends(get_settings),
):
    if range:
        date_start, date_end = _resolve_dates(range, start, end)
    elif start or end:
        date_start, date_end = _resolve_dates(range, start, end)
    else:
        # 默认近 7 天窗口
        today = datetime.now().date()
        date_start = (today - timedelta(days=6)).isoformat()
        date_end = today.isoformat()

    # 窗口钳制（无 tools 层可托管的数值边界，路由层静默收敛）
    d_start = date.fromisoformat(date_start)
    d_end = date.fromisoformat(date_end)
    if (d_end - d_start).days > _MAX_WINDOW_DAYS:
        d_start = d_end - timedelta(days=_MAX_WINDOW_DAYS)
        date_start = d_start.isoformat()

    def produce():
        rows = SentimentStore(settings.output_root).query(
            topic=topic or None, date_start=date_start, date_end=date_end, limit=limit,
        )
        return {"results": rows, "count": len(rows)}

    params = {"topic": topic or "", "date_start": date_start, "date_end": date_end, "limit": limit}
    data, cached = cached_call(
        "sentiment.results", params, ttl_for(settings, "sentiment.results"), produce
    )
    return ok(data, cached=cached)
