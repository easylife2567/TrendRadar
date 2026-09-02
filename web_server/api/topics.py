"""
高级分析端点（design/03 §2.3）

全部走 AnalyticsTools（只读实例）。数值钳制（top_n/similarity_threshold 等）
按校验分层原则交给 tools 层 validators；路由层只做枚举白名单早拒。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query

from ..cache import cached_call, ttl_for
from ..envelope import ok, unwrap_tool_result
from ..errors import ApiError
from ..settings import WebSettings
from ..tools_registry import get_read_tools
from .deps import get_settings, resolve_range
from .news import _parse_platforms

router = APIRouter(tags=["analytics"])

_INSIGHT_TYPES = ("platform_compare", "platform_activity", "keyword_cooccur")
_COMPARE_TYPES = ("overview", "topic_shift", "platform_activity")

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_period(period: str) -> str | dict:
    """
    时期参数适配：单日 "YYYY-MM-DD" → {"start","end"} 字典。

    tools 层 compare_periods 的字符串分支只认预设值（today/last_week 等），
    不认单日日期；dict 分支接受任意范围。web 契约允许前端传单日字符串，
    在此转为等价单日范围（参数适配，非业务逻辑）。
    """
    if _DATE_ONLY_RE.match(period):
        return {"start": period, "end": period}
    return period


@router.get("/analytics/topic-trend", summary="话题热度趋势 / 生命周期 / 爆火 / 预测")
def topic_trend(
    topic: str = Query(..., min_length=1, max_length=100),
    analysis_type: str = Query("trend", description="trend|lifecycle|viral|predict"),
    range: str | None = Query(None, alias="range", description="日期范围表达式"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    granularity: str = Query("day", description="day|hour"),
    settings: WebSettings = Depends(get_settings),
):
    if analysis_type not in ("trend", "lifecycle", "viral", "predict"):
        raise ApiError(400, "BAD_REQUEST", "analysis_type 仅支持 trend|lifecycle|viral|predict")
    date_range = resolve_range(range, start, end)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["analytics"].analyze_topic_trend_unified(
                topic=topic, analysis_type=analysis_type, date_range=date_range,
                granularity=granularity,
            )
        )

    params = {
        "topic": topic, "analysis_type": analysis_type,
        "date_range": date_range, "granularity": granularity,
    }
    data, cached = cached_call(
        "analytics.topic_trend", params, ttl_for(settings, "analytics.topic_trend"), produce
    )
    return ok(data, cached=cached)


@router.get("/analytics/insights", summary="数据洞察（平台对比/活跃度/关键词共现）")
def insights(
    insight_type: str = Query("platform_compare"),
    topic: str | None = Query(None, max_length=100),
    range: str | None = Query(None, alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    min_frequency: int = Query(3, ge=1),
    top_n: int = Query(20, ge=1, le=100),
    settings: WebSettings = Depends(get_settings),
):
    if insight_type not in _INSIGHT_TYPES:
        raise ApiError(400, "BAD_REQUEST", f"insight_type 仅支持 {'|'.join(_INSIGHT_TYPES)}")
    date_range = resolve_range(range, start, end)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["analytics"].analyze_data_insights_unified(
                insight_type=insight_type, topic=topic, date_range=date_range,
                min_frequency=min_frequency, top_n=top_n,
            )
        )

    params = {
        "insight_type": insight_type, "topic": topic, "date_range": date_range,
        "min_frequency": min_frequency, "top_n": top_n,
    }
    data, cached = cached_call(
        "analytics.insights", params, ttl_for(settings, "analytics.insights"), produce
    )
    return ok(data, cached=cached)


@router.get("/analytics/viral", summary="爆火话题检测（异常热度预警）")
def viral(
    threshold: float = Query(3.0, ge=1.0, le=100.0, description="热度突增倍数阈值"),
    time_window: int = Query(24, ge=1, le=168, description="检测时间窗口（小时）"),
    settings: WebSettings = Depends(get_settings),
):
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["analytics"].detect_viral_topics(threshold=threshold, time_window=time_window)
        )

    params = {"threshold": threshold, "time_window": time_window}
    data, cached = cached_call(
        "analytics.viral", params, ttl_for(settings, "analytics.viral"), produce
    )
    return ok(data, cached=cached)


@router.get("/analytics/predict", summary="热点预测（未来 N 小时潜力话题）")
def predict(
    lookahead_hours: int = Query(6, ge=1, le=72),
    confidence_threshold: float = Query(0.7, ge=0.0, le=1.0),
    settings: WebSettings = Depends(get_settings),
):
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["analytics"].predict_trending_topics(
                lookahead_hours=lookahead_hours, confidence_threshold=confidence_threshold
            )
        )

    params = {"lookahead_hours": lookahead_hours, "confidence_threshold": confidence_threshold}
    data, cached = cached_call(
        "analytics.predict", params, ttl_for(settings, "analytics.predict"), produce
    )
    return ok(data, cached=cached)


@router.get("/analytics/compare-periods", summary="时期对比（环比/话题变化/平台活跃度）")
def compare_periods(
    period_a: str = Query(..., description='预设（today/last_week）或单日 "YYYY-MM-DD"'),
    period_b: str = Query(..., description="同 period_a"),
    topic: str | None = Query(None, max_length=100),
    compare_type: str = Query("overview"),
    platforms: str | None = Query(None, description="逗号分隔平台 ID"),
    top_n: int = Query(10, ge=1, le=100),
    settings: WebSettings = Depends(get_settings),
):
    if compare_type not in _COMPARE_TYPES:
        raise ApiError(400, "BAD_REQUEST", f"compare_type 仅支持 {'|'.join(_COMPARE_TYPES)}")
    platform_list = _parse_platforms(platforms)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["analytics"].compare_periods(
                period1=_normalize_period(period_a), period2=_normalize_period(period_b),
                topic=topic, compare_type=compare_type, platforms=platform_list, top_n=top_n,
            )
        )

    params = {
        "period_a": period_a, "period_b": period_b, "topic": topic,
        "compare_type": compare_type, "platforms": platform_list, "top_n": top_n,
    }
    data, cached = cached_call(
        "analytics.compare_periods", params, ttl_for(settings, "analytics.compare_periods"), produce
    )
    return ok(data, cached=cached)


@router.get("/analytics/compare-platforms", summary="平台对比（各平台对话题的关注度）")
def compare_platforms(
    topic: str | None = Query(None, max_length=100),
    range: str | None = Query(None, alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    settings: WebSettings = Depends(get_settings),
):
    date_range = resolve_range(range, start, end)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["analytics"].compare_platforms(topic=topic, date_range=date_range)
        )

    params = {"topic": topic, "date_range": date_range}
    data, cached = cached_call(
        "analytics.compare_platforms", params, ttl_for(settings, "analytics.compare_platforms"), produce
    )
    return ok(data, cached=cached)


@router.get("/analytics/aggregate", summary="跨平台新闻聚合（相似事件去重合并）")
def aggregate(
    range: str | None = Query(None, alias="range"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    platforms: str | None = Query(None, description="逗号分隔平台 ID"),
    similarity_threshold: float = Query(0.7, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    include_url: bool = Query(False),
    settings: WebSettings = Depends(get_settings),
):
    date_range = resolve_range(range, start, end)
    platform_list = _parse_platforms(platforms)
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(
            tools["analytics"].aggregate_news(
                date_range=date_range, platforms=platform_list,
                similarity_threshold=similarity_threshold, limit=limit,
                include_url=include_url,
            )
        )

    params = {
        "date_range": date_range, "platforms": platform_list,
        "similarity_threshold": similarity_threshold, "limit": limit,
        "include_url": include_url,
    }
    data, cached = cached_call(
        "analytics.aggregate", params, ttl_for(settings, "analytics.aggregate"), produce
    )
    return ok(data, cached=cached)
