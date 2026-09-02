"""
错误模型与映射（design/03 §4）

契约错误码：BAD_REQUEST / UNAUTHORIZED / RATE_LIMITED / DATE_NOT_FOUND /
NOT_FOUND / AI_EXECUTION_FAILED / INTERNAL_ERROR

错误响应统一经全局 exception handler 输出信封：
{"success": false, "error": {"code", "message"[, "detail"]}}
错误响应不带堆栈（design/06 §5 信息暴露最小化）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mcp_server.utils.errors import MCPError

# Starlette HTTP 异常 → 契约错误码（未匹配路由的 404 等也走统一信封）
_HTTP_CODE_MAP: dict[int, str] = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}

logger = logging.getLogger("trendradar.web")


class ApiError(Exception):
    """Web 层业务错误（携带 HTTP 状态码与契约错误码；headers 供 429 Retry-After 等）"""

    def __init__(self, status_code: int, code: str, message: str, detail: Any = None, headers: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        self.headers = headers


# tools 层错误码 → (HTTP 状态码, 契约错误码)
MCP_ERROR_MAP: dict[str, tuple[int, str]] = {
    "DATA_NOT_FOUND": (404, "DATE_NOT_FOUND"),
    "INVALID_PARAMETER": (400, "BAD_REQUEST"),
    "PLATFORM_NOT_SUPPORTED": (400, "BAD_REQUEST"),
    "CONFIGURATION_ERROR": (500, "INTERNAL_ERROR"),
    "FILE_PARSE_ERROR": (500, "INTERNAL_ERROR"),
    "CRAWL_TASK_ERROR": (500, "INTERNAL_ERROR"),
}


def api_error_from_tool_error(err: dict) -> ApiError:
    """把 tools 层返回的 error dict（{"code","message","suggestion"?}）转为 ApiError"""
    raw_code = str(err.get("code") or "MCP_ERROR")
    status, code = MCP_ERROR_MAP.get(raw_code, (500, "INTERNAL_ERROR"))
    # detail 透传原始 code 与 suggestion，供排查（契约超集，前端忽略）
    detail = {"tool_code": raw_code}
    if err.get("suggestion"):
        detail["suggestion"] = err["suggestion"]
    return ApiError(status, code, str(err.get("message") or "未知错误"), detail=detail)


def _error_body(code: str, message: str, detail: Any = None) -> dict:
    error: dict = {"code": code, "message": message}
    if detail is not None:
        error["detail"] = detail
    return {"success": False, "error": error}


def register_error_handlers(app: FastAPI) -> None:
    """注册全局错误处理（信封化，绝不回堆栈）"""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.detail),
            headers=exc.headers,
        )

    @app.exception_handler(MCPError)
    async def handle_mcp_error(request: Request, exc: MCPError):
        """services 层直接抛出的 MCPError（tools 层已内部捕获大部分，此为兜底）"""
        status, code = MCP_ERROR_MAP.get(exc.code, (500, "INTERNAL_ERROR"))
        return JSONResponse(status_code=status, content=_error_body(code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content=_error_body("BAD_REQUEST", "请求参数不合法", detail=str(exc.errors()[:3])))

    @app.exception_handler(StarletteHTTPException)
    async def handle_starlette_http_error(request: Request, exc: StarletteHTTPException):
        """未匹配路由的 404、405 等框架级异常统一信封化（如 /api/nonexistent）"""
        code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_error_body(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception("未处理异常: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content=_error_body("INTERNAL_ERROR", "服务器内部错误"))
