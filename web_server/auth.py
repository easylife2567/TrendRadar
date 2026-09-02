"""
认证中间件（design/06 §2：X-API-Key 应用层认证，Cloudflare Access 为边缘层可选叠加）

规则：
- 仅作用于 /api/* 路径
- 任何 POST 一律要求 X-API-Key（fail-closed：P1 的 crawl/pipeline 与 P3 的 sentiment/run、
  未来工作台写端点自动覆盖；本机模式亦不豁免——防浏览器内恶意页面借 localhost 发写请求）
- GET 等读方法仅当 require_read_key 开启时要求（默认公开只读，可一键收紧）
- 恒定时间比较（hmac.compare_digest），防时序侧信道

Key 来源（优先级）：
1. 环境变量 TRENDRADAR_API_KEY（systemd 部署经 EnvironmentFile=/etc/trendradar/web.env 注入）
2. /etc/trendradar/web.env（裸进程运行的兜底读取）
3. 项目根 .env（本地开发便利）

Key 不进 config.yaml（避免密钥进可编辑配置文件，design/06 §2）。
"""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

_ENV_FILE_SERVER = Path("/etc/trendradar/web.env")
_KEY_ENV_NAME = "TRENDRADAR_API_KEY"


def _parse_env_file(path: Path) -> dict[str, str]:
    """极简 KEY=VALUE 解析（够 web.env 用即可，不追求 dotenv 全语义）"""
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    except OSError:
        pass
    return values


def load_api_key(project_root: Path | None = None) -> str | None:
    """解析生效的 API Key；未配置返回 None（此时写端点 fail-closed）"""
    key = os.environ.get(_KEY_ENV_NAME, "").strip()
    if key:
        return key
    for path in (_ENV_FILE_SERVER, (project_root or Path(__file__).parent.parent) / ".env"):
        key = _parse_env_file(path).get(_KEY_ENV_NAME, "").strip()
        if key:
            return key
    return None


def _constant_time_equals(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


class AuthMiddleware:
    """纯 ASGI 认证中间件（内层：限流之后、路由之前执行）"""

    def __init__(self, app, api_key: str | None, require_read_key: bool = False, project_root: Path | None = None):
        self.app = app
        self.require_read_key = require_read_key
        self.project_root = project_root
        self._api_key = api_key

    def _resolve_key(self) -> str | None:
        # 环境变量可能在进程生命周期内被更新（少见），每次决议取最新
        key = os.environ.get(_KEY_ENV_NAME, "").strip()
        return key or self._api_key

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        needs_key = method == "POST" or self.require_read_key

        if needs_key:
            expected = self._resolve_key()
            provided = ""
            for name, value in scope.get("headers") or []:
                if name.lower() == b"x-api-key":
                    provided = value.decode("latin-1", errors="replace").strip()
                    break

            if not expected:
                # Key 未配置：写操作 fail-closed（服务端配置问题，503）
                await self._reject(send, 503, "SERVER_MISCONFIGURED", "API Key 未配置，写操作不可用")
                return
            if not provided or not _constant_time_equals(provided, expected):
                await self._reject(send, 401, "UNAUTHORIZED", "缺少或错误的 X-API-Key")
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, status: int, code: str, message: str):
        body = json.dumps(
            {"success": False, "error": {"code": code, "message": message}},
            ensure_ascii=False,
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json; charset=utf-8")],
        })
        await send({"type": "http.response.body", "body": body})


# ==================== FastAPI 依赖（双保险） ====================

async def require_api_key(request) -> None:
    """
    🔑 端点路由级依赖（与 AuthMiddleware 双保险：即使中间件被误摘，端点仍有门槛）。
    中间件已放行的请求此处必然通过——重复校验是恒定时间比较，成本可忽略。
    抛 ApiError 走全局错误 handler，保证信封格式一致。
    """
    from .errors import ApiError

    key = os.environ.get(_KEY_ENV_NAME, "").strip() or load_api_key(
        getattr(request.app.state, "project_root", None)
    )
    provided = request.headers.get("x-api-key", "").strip()
    if not key:
        raise ApiError(503, "SERVER_MISCONFIGURED", "API Key 未配置，写操作不可用")
    if not provided or not _constant_time_equals(provided, key):
        raise ApiError(401, "UNAUTHORIZED", "缺少或错误的 X-API-Key")
