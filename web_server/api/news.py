"""
热榜与历史端点（design/03 §2.2）

search 经 resolve_range 支持 range 表达式/ start+end（DateParser 同 MCP 语义）；
date/{date} 严格单日（差异#10：tools 层 dict 入参只取 start，故传单日字符串）；
rank-history 为 Step 2 下沉的 get_news_rank_history。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..cache import cached_call, ttl_for
from ..envelope import ok, unwrap_tool_result
from ..errors import ApiError
from ..settings import WebSettings
from ..tools_registry import get_read_tools
from .deps import get_settings, resolve_range, validate_date_string

router = APIRouter(tags=["news"])

_SEARCH_MODES = ("keyword", "fuzzy", "entity")
_TRENDING_MODES = ("daily", "current")
_EXTRACT_MODES = ("keywords", "auto_extract")


def _parse_platforms(platforms: str | None) -> list[str] | None:
    """,/空格分隔的平台 ID 列表 → list；空串返回 None（全部平台）"""
    if not platforms:
        return None
    items = [p.strip() for p in platforms.replace("，", ",").split(",") if p.strip()]
    return items or None


@router.get("/news/latest", summary="最新一批爬取的热榜新闻")
def get_latest_news(
    platforms: str | None = Query(None, description="逗号分隔平台 ID，如 zhihu,weibo"),
    limit: int | None = Query(None, ge=1, le=1000, description="返回条数（工具层默认 20）"),
    include_url: bool = Query(False),
    settings: WebSettings = Depends(get_settings),
):
    platform_list = _parse_platforms(platforms)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["data_query"].get_latest_news(
                platforms=platform_list, limit=limit, include_url=include_url
            )
        )

    params = {"platforms": platform_list, "limit": limit, "include_url": include_url}
    data, cached = cached_call(
        "news.latest", params, ttl_for(settings, "news.latest"), produce
    )
    return ok(data, cached=cached)


@router.get("/news/date/{date}", summary="按日期查询热榜新闻（单日）")
def get_news_by_date(
    date: str,
    platforms: str | None = Query(None, description="逗号分隔平台 ID"),
    limit: int | None = Query(None, ge=1, le=1000, description="返回条数（工具层默认 50）"),
    include_url: bool = Query(False),
    settings: WebSettings = Depends(get_settings),
):
    validate_date_string(date, "date")
    platform_list = _parse_platforms(platforms)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["data_query"].get_news_by_date(
                date_range=date, platforms=platform_list, limit=limit, include_url=include_url
            )
        )

    params = {"date": date, "platforms": platform_list, "limit": limit, "include_url": include_url}
    data, cached = cached_call(
        "news.by_date", params, ttl_for(settings, "news.by_date"), produce
    )
    return ok(data, cached=cached)


@router.get("/news/search", summary="跨日全文检索（关键词/模糊/实体三种模式）")
def search_news(
    query: str = Query(..., min_length=1, max_length=200),
    search_mode: str = Query("keyword", description="keyword|fuzzy|entity"),
    range: str | None = Query(None, alias="range", description="日期范围表达式，如 last7d/本周"),
    start: str | None = Query(None, description="范围起（与 end 成对）"),
    end: str | None = Query(None, description="范围止（与 start 成对）"),
    platforms: str | None = Query(None, description="逗号分隔平台 ID"),
    limit: int = Query(50, ge=1, le=1000),
    include_rss: bool = Query(False, description="是否同时检索 RSS"),
    settings: WebSettings = Depends(get_settings),
):
    if search_mode not in _SEARCH_MODES:
        raise ApiError(400, "BAD_REQUEST", f"search_mode 仅支持 {'|'.join(_SEARCH_MODES)}")
    date_range = resolve_range(range, start, end)
    platform_list = _parse_platforms(platforms)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["search"].search_news_unified(
                query=query,
                search_mode=search_mode,
                date_range=date_range,
                platforms=platform_list,
                limit=limit,
                include_rss=include_rss,
            )
        )

    params = {
        "query": query, "search_mode": search_mode, "date_range": date_range,
        "platforms": platform_list, "limit": limit, "include_rss": include_rss,
    }
    data, cached = cached_call(
        "news.search", params, ttl_for(settings, "news.search"), produce
    )
    return ok(data, cached=cached)


@router.get("/topics/trending", summary="热点话题统计（关注词或自动提取）")
def get_trending_topics(
    top_n: int | None = Query(None, ge=1, le=100),
    mode: str | None = Query(None, description="daily|current，缺省 current"),
    extract_mode: str | None = Query(None, description="keywords|auto_extract"),
    settings: WebSettings = Depends(get_settings),
):
    if mode is not None and mode not in _TRENDING_MODES:
        raise ApiError(400, "BAD_REQUEST", f"mode 仅支持 {'|'.join(_TRENDING_MODES)}")
    if extract_mode is not None and extract_mode not in _EXTRACT_MODES:
        raise ApiError(400, "BAD_REQUEST", f"extract_mode 仅支持 {'|'.join(_EXTRACT_MODES)}")
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["data_query"].get_trending_topics(
                top_n=top_n, mode=mode, extract_mode=extract_mode
            )
        )

    params = {"top_n": top_n, "mode": mode, "extract_mode": extract_mode}
    data, cached = cached_call(
        "topics.trending", params, ttl_for(settings, "topics.trending"), produce
    )
    return ok(data, cached=cached)


@router.get("/news/item/{date}/{news_id}/rank-history", summary="单条新闻的排名轨迹与标题变更")
def get_rank_history(
    date: str,
    news_id: int,
    include_title_changes: bool = Query(True),
    settings: WebSettings = Depends(get_settings),
):
    validate_date_string(date, "date")
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["data_query"].get_news_rank_history(
                date=date, news_id=news_id, include_title_changes=include_title_changes
            )
        )

    params = {"date": date, "news_id": news_id, "include_title_changes": include_title_changes}
    data, cached = cached_call(
        "news.rank_history", params, ttl_for(settings, "news.rank_history"), produce
    )
    return ok(data, cached=cached)
