"""
系统状态端点（design/03 §2.1）

status 做字段白名单投影：tools 层原样返回 project_root 绝对路径（MCP 语义保留），
Web 契约禁止向公网暴露本机路径（design/06 §5、验收「响应不含 config 路径」）。

dates 走 DataQueryTools.get_available_dates（ParserService 支持数据根目录覆盖 D9②），
schedule 走 SystemManagementTools.get_next_schedule_run（三态降级，永不 500），
health/sources 走 DataQueryTools.get_source_health（当日无库 → 404 DATE_NOT_FOUND）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..cache import cached_call, ttl_for
from ..envelope import ok, unwrap_tool_result
from ..settings import WebSettings
from ..tools_registry import get_action_tools, get_read_tools
from .deps import get_settings, validate_date_string

router = APIRouter(tags=["system"])

# 白名单：契约暴露的字段（tools 层 get_system_status 返回 system/data/cache/health 四段）
# tools 层内嵌的 "data"（存储概况）在契约里改名为 storage，避免 data.data 歧义
_STATUS_WHITELIST = ("cache", "health")


@router.get("/system/status", summary="系统运行状态（版本 / 存储概况 / 缓存统计）")
def get_system_status(settings: WebSettings = Depends(get_settings)):
    from mcp_server.tools.system import SystemManagementTools

    result = SystemManagementTools(str(settings.project_root)).get_system_status()
    payload = unwrap_tool_result(result)

    projected = {key: payload.get(key) for key in _STATUS_WHITELIST if key in payload}
    if payload.get("data") is not None:
        projected["storage"] = payload["data"]
    if isinstance(payload.get("system"), dict):
        projected["version"] = payload["system"].get("version")
    return ok(projected)


@router.get("/system/dates", summary="可用的数据日期列表")
def get_available_dates(
    db_type: str = Query("news", pattern="^(news|rss)$"),
    settings: WebSettings = Depends(get_settings),
):
    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(tools["data_query"].get_available_dates(db_type))

    data, cached = cached_call(
        "system.dates", {"db_type": db_type}, ttl_for(settings, "system.dates"), produce
    )
    return ok(data, cached=cached)


@router.get("/system/schedule", summary="调度状态与下一次执行推算（三态降级）")
def get_schedule(settings: WebSettings = Depends(get_settings)):
    tools = get_action_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(tools["system"].get_next_schedule_run())

    data, cached = cached_call(
        "system.schedule", {}, ttl_for(settings, "system.schedule"), produce
    )
    return ok(data, cached=cached)


@router.get("/system/health/sources", summary="当日各采集源成功/失败状况")
def get_source_health(
    date: str | None = Query(None, description="YYYY-MM-DD，缺省为今天"),
    settings: WebSettings = Depends(get_settings),
):
    if date is not None:
        validate_date_string(date, "date")

    tools = get_read_tools(str(settings.project_root), settings.data_root)

    def produce():
        return unwrap_tool_result(tools["data_query"].get_source_health(date))

    params = {"date": date or "today"}
    data, cached = cached_call(
        "system.health_sources", params, ttl_for(settings, "system.health_sources"), produce
    )
    return ok(data, cached=cached)
