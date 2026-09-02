"""
访问日志中间件（design/06 §5：journal 只记 时间/路径/状态码/耗时/IP）

- 纯 ASGI 实现（不缓冲响应，兼容 P4 SSE）
- 只记 /api/* 请求（静态资源与 /docs 不进访问日志，保持 journal 干净）
- 不记 query string（搜索词等用户输入不落日志）；uvicorn 自带 access log 在
  __main__.py 里以 access_log=False 关闭，避免其记录完整 URL
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("trendradar.web.access")


class AccessLogMiddleware:
    """纯 ASGI 访问日志中间件（最外层：先执行）"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            client = scope.get("client")
            ip = client[0] if client else "unknown"
            logger.info(
                "%s %s %d %.0fms %s",
                scope.get("method", "?"),
                scope.get("path", "?"),
                status_holder["status"],
                duration_ms,
                ip,
            )
