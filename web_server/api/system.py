"""
系统状态端点（design/03 §2.1）

status 做字段白名单投影：tools 层原样返回 project_root 绝对路径（MCP 语义保留），
Web 契约禁止向公网暴露本机路径（design/06 §5、验收「响应不含 config 路径」）。

dates 走 DataQueryTools.get_available_dates（ParserService 支持数据根目录覆盖 D9②），
schedule 走 SystemManagementTools.get_next_schedule_run（三态降级，永不 500），
health/sources 走 DataQueryTools.get_source_health（当日无库 → 404 DATE_NOT_FOUND）。
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..cache import cached_call, ttl_for
from ..envelope import ok, unwrap_tool_result
from ..errors import ApiError
from ..settings import WebSettings
from ..tools_registry import get_action_tools, get_read_tools
from .deps import get_pipeline_runner, get_settings, validate_date_string

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


# ============================================
# 写路径（design/03 §2.1 🔑 端点；POST 一律要求 X-API-Key，AuthMiddleware 强制）
# ============================================

_crawl_lock = threading.Lock()


class _CrawlBody(BaseModel):
    platforms: list[str] | None = None
    save_to_local: bool = False
    include_url: bool = False


@router.post("/crawl/trigger", summary="触发轻量抓取（写库；成功后分析缓存将被清空）")
def trigger_crawl(
    body: _CrawlBody | None = None,
    settings: WebSettings = Depends(get_settings),
):
    """
    轻量抓取（SystemManagementTools.trigger_crawl）。

    并发保护：web 层 threading.Lock 占锁（tools 层无并发保护，差异#5 计划项），
    占锁失败返回 409。成功后工具内部清空进程缓存（含长 TTL 分析缓存，差异#13）。
    """
    payload = body or _CrawlBody()
    if not _crawl_lock.acquire(blocking=False):
        raise ApiError(409, "RATE_LIMITED", "已有一次抓取在执行中，请稍候")
    try:
        tools = get_action_tools(str(settings.project_root), settings.data_root)
        result = tools["system"].trigger_crawl(
            platforms=payload.platforms or None,
            save_to_local=payload.save_to_local,
            include_url=payload.include_url,
        )
        data = unwrap_tool_result(result)
        return ok(data)
    finally:
        _crawl_lock.release()


@router.post("/pipeline/run", summary="触发完整管线（systemd-run transient unit 或 Popen 降级）", status_code=202)
def run_pipeline(
    runner=Depends(get_pipeline_runner),
):
    """
    完整管线（python -m trendradar，异步执行）。

    - 工作站（有 systemd）：systemd-run transient unit，journal 可查日志
    - 本机开发：Popen 降级，输出追加到 output/pipeline_manual.log
    - 运行中再触发 → 409（附当前 unit/pid）
    """
    from ..pipeline import LauncherUnavailable, PipelineAlreadyRunning

    try:
        running, launch = runner.is_running()
        if running:
            raise ApiError(
                409, "RATE_LIMITED",
                f"管线已在运行中（{launch.describe()}），请等待完成",
                detail={"launch": launch.describe()},
            )
        started = runner.launch()
    except PipelineAlreadyRunning as e:
        raise ApiError(
            409, "RATE_LIMITED",
            f"管线已在运行中（{e.launch.describe()}）",
            detail={"launch": e.launch.describe()},
        ) from e
    except LauncherUnavailable as e:
        raise ApiError(500, "INTERNAL_ERROR", str(e)) from e

    return ok(
        {
            "started": True,
            "mode": started.mode,
            "unit": started.unit,
            "pid": started.pid,
            "description": "管线已异步启动；进度看 output/ 数据变化或 journalctl（systemd 模式）",
        }
    )
