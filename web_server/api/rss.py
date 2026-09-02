"""
RSS 端点（design/03 §2.5）

本地样例环境无 output/rss/ 时：latest/search 抛 404 DATE_NOT_FOUND
（前端渲染空态卡），feeds-status 读 config 恒 200。
days 钳制（1-30）在路由 ge/le + 工具层双重保障。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..cache import cached_call, ttl_for
from ..envelope import ok, unwrap_tool_result
from ..settings import WebSettings
from ..tools_registry import get_read_tools
from .deps import get_settings
from .news import _parse_platforms as _parse_feeds

router = APIRouter(tags=["rss"])


@router.get("/rss/latest", summary="最新 RSS 订阅条目（最近 N 天）")
def get_latest_rss(
    feeds: str | None = Query(None, description="逗号分隔 RSS 源 ID，如 hacker-news,36kr"),
    days: int = Query(1, ge=1, le=30),
    limit: int | None = Query(None, ge=1, le=1000, description="返回条数（工具层默认 50）"),
    include_summary: bool = Query(False),
    settings: WebSettings = Depends(get_settings),
):
    feed_list = _parse_feeds(feeds)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["data_query"].get_latest_rss(
                feeds=feed_list, days=days, limit=limit, include_summary=include_summary
            )
        )

    params = {"feeds": feed_list, "days": days, "limit": limit, "include_summary": include_summary}
    data, cached = cached_call(
        "rss.latest", params, ttl_for(settings, "rss.latest"), produce
    )
    return ok(data, cached=cached)


@router.get("/rss/search", summary="搜索 RSS 条目")
def search_rss(
    keyword: str = Query(..., min_length=1, max_length=200),
    feeds: str | None = Query(None, description="逗号分隔 RSS 源 ID"),
    days: int = Query(7, ge=1, le=30),
    limit: int | None = Query(None, ge=1, le=1000),
    include_summary: bool = Query(False),
    settings: WebSettings = Depends(get_settings),
):
    feed_list = _parse_feeds(feeds)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["data_query"].search_rss(
                keyword=keyword, feeds=feed_list, days=days,
                limit=limit, include_summary=include_summary,
            )
        )

    params = {
        "keyword": keyword, "feeds": feed_list, "days": days,
        "limit": limit, "include_summary": include_summary,
    }
    data, cached = cached_call(
        "rss.search", params, ttl_for(settings, "rss.search"), produce
    )
    return ok(data, cached=cached)


@router.get("/rss/feeds-status", summary="RSS 订阅源配置状态（读 config，恒 200）")
def get_feeds_status(settings: WebSettings = Depends(get_settings)):
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(tools["data_query"].get_rss_feeds_status())

    data, cached = cached_call(
        "rss.feeds_status", {}, ttl_for(settings, "rss.feeds_status"), produce
    )
    return ok(data, cached=cached)
