"""
路由公共依赖与参数解析（design/03：日期表达式经服务端 DateParser 解析，
与 MCP resolve_date_range 工具同实现，保证语义一致）
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import Request

from mcp_server.utils.date_parser import DateParser
from mcp_server.utils.errors import InvalidParameterError

from ..errors import ApiError
from ..settings import WebSettings

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_settings(request: Request) -> WebSettings:
    return request.app.state.settings


def get_project_root(request: Request) -> Path:
    return request.app.state.settings.project_root


def get_pipeline_runner(request: Request):
    """手动管线启动器（app 级单例，create_app 时创建）"""
    return request.app.state.pipeline_runner


def validate_date_string(value: str, field: str) -> str:
    r"""日期字符串早拒（design/06 §3：日期一律 ^\d{4}-\d{2}-\d{2}$）"""
    if not DATE_RE.match(value or ""):
        raise ApiError(400, "BAD_REQUEST", f"参数 {field} 须为 YYYY-MM-DD 格式的日期")
    return value


def resolve_range(
    range_expr: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict | None:
    """
    解析日期范围参数（Query 参数 → tools 层 date_range dict）。

    - start+end 同时给出：校验格式后直接构造
    - range 表达式（"last7d"/"本周"/"最近30天"...）：经 DateParser.resolve_date_range_expression
    - 都未给：返回 None（由工具层按默认语义处理，多为「今天」）

    Raises:
        ApiError(400, BAD_REQUEST)：格式错误或表达式无法解析
    """
    if start or end:
        if not (start and end):
            raise ApiError(400, "BAD_REQUEST", "start 与 end 必须同时提供")
        return {"start": validate_date_string(start, "start"), "end": validate_date_string(end, "end")}

    if range_expr:
        try:
            result = DateParser.resolve_date_range_expression(range_expr)
        except InvalidParameterError as e:
            raise ApiError(400, "BAD_REQUEST", f"无法解析日期范围表达式: {e.message}", detail=e.to_dict())
        return result.get("date_range")

    return None
