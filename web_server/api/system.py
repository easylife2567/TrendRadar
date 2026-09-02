"""
系统状态端点（design/03 §2.1）

Step 1 占位：仅 /api/system/status，Step 4 接入 dates/schedule/health/sources 与缓存。
status 做字段白名单投影：tools 层原样返回 project_root 绝对路径（MCP 语义保留），
Web 契约禁止向公网暴露本机路径（design/06 §5、验收「响应不含 config 路径」）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..envelope import ok, unwrap_tool_result
from ..settings import WebSettings
from .deps import get_settings

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
