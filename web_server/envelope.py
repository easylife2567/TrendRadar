"""
响应信封（design/03 设计约定）

成功信封只在路由层显式构造（不做响应中间件统一包裹）：
- reports 端点要返回 text/html 原文，中间件包裹会破坏
- P4 SSE 流式响应与「读完 body 再包裹」的中间件不兼容
- cached 标志是路由级信息，经 request.state 二次传递属隐式耦合

信封形态：
成功 {"success": true, "data": ..., "cached": false, "generated_at": "..."}
失败 {"success": false, "error": {"code", "message"}}
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import ApiError, api_error_from_tool_error


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ok(data: Any, *, cached: bool = False, extra: dict | None = None) -> dict:
    """构造成功信封。extra 用于携带 summary 等路由级附加字段"""
    body: dict = {"success": True, "data": data, "cached": cached, "generated_at": _now_iso()}
    if extra:
        body.update(extra)
    return body


def unwrap_tool_result(result: Any, *, data_key: str = "data") -> Any:
    """
    解包 tools 层返回值。

    tools 层约定（mcp_server/tools/*）：成功 {"success": True, ..., "data": [...]}，
    失败 {"success": False, "error": {"code","message","suggestion"?}}（业务异常已内部捕获）。

    - success=False → 抛 ApiError（按 MCP_ERROR_MAP 映射状态码）
    - 有 data_key 键 → 返回该键
    - 无 → 返回剔除 success/error 后的整体（适配键名不统一的工具）
    """
    if not isinstance(result, dict):
        raise ApiError(500, "INTERNAL_ERROR", "工具层返回了非预期结构")

    if result.get("success") is False:
        raise api_error_from_tool_error(result.get("error") or {})

    if data_key in result:
        return result[data_key]

    return {k: v for k, v in result.items() if k not in ("success", "error")}
