"""
限流中间件（design/06 §2：应用层令牌桶，与 Cloudflare 边缘限流冗余，防直接打源站）

实现为纯 ASGI 中间件（不用 BaseHTTPMiddleware）：不缓冲响应体，兼容 P4 SSE 流式响应。

策略（design/03 §3）：
- /api/analytics/*  10 req/min（慢端点，防雪崩）
- 其余 /api/*       60 req/min
- 非 /api/* 路径（静态资源、/docs）不限流

客户端标识：仅当服务绑定 127.0.0.1（唯一入口是 Cloudflare Tunnel）时信任
CF-Connecting-IP 头；显式绑定 0.0.0.0 时回落 socket 对端地址（该头可被伪造）。

护栏均为进程内存实现——v1 明确单进程部署（systemd unit 不加 workers）。
"""

from __future__ import annotations

import json
import time
from threading import Lock

ANALYTICS_PER_MIN = 10
DEFAULT_PER_MIN = 60
_BUCKET_STALE_SECONDS = 600  # 桶空闲超时回收，防长期运行下 dict 无界增长


class TokenBucket:
    """令牌桶（线程安全）"""

    def __init__(self, per_minute: int):
        self.capacity = float(per_minute)
        self.tokens = float(per_minute)
        self.refill_rate = per_minute / 60.0
        self.updated = time.monotonic()
        self.lock = Lock()

    def acquire(self) -> bool:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_rate)
            self.updated = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


def _client_ip(scope: dict, trust_cf_header: bool) -> str:
    if trust_cf_header:
        for name, value in scope.get("headers") or []:
            if name.lower() == b"cf-connecting-ip":
                return value.decode("latin-1", errors="replace")
    client = scope.get("client")
    return client[0] if client else "unknown"


def _bucket_class(path: str) -> str:
    return "analytics" if path.startswith("/api/analytics") else "default"


class RateLimitMiddleware:
    """纯 ASGI 限流中间件（外层先于认证执行：认证失败也消耗额度，防暴力猜 key）"""

    def __init__(self, app, host: str = "127.0.0.1",
                 analytics_per_min: int = ANALYTICS_PER_MIN,
                 default_per_min: int = DEFAULT_PER_MIN):
        self.app = app
        # 仅隧道形态（绑回环、唯一公网入口是 CF）信任 CF-Connecting-IP
        self.trust_cf_header = host in ("127.0.0.1", "localhost")
        self.analytics_per_min = analytics_per_min
        self.default_per_min = default_per_min
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._lock = Lock()
        self._last_seen: dict[tuple[str, str], float] = {}

    def _get_bucket(self, ip: str, bucket_class: str) -> TokenBucket:
        key = (ip, bucket_class)
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > 10000:  # 周期回收空闲桶
                stale = [k for k, t in self._last_seen.items() if now - t > _BUCKET_STALE_SECONDS]
                for k in stale:
                    self._buckets.pop(k, None)
                    self._last_seen.pop(k, None)
            bucket = self._buckets.get(key)
            if bucket is None:
                per_min = self.analytics_per_min if bucket_class == "analytics" else self.default_per_min
                bucket = TokenBucket(per_min)
                self._buckets[key] = bucket
            self._last_seen[key] = now
            return bucket

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        ip = _client_ip(scope, self.trust_cf_header)
        bucket = self._get_bucket(ip, _bucket_class(scope["path"]))

        if not bucket.acquire():
            body = json.dumps(
                {"success": False, "error": {"code": "RATE_LIMITED", "message": "请求过于频繁，请稍后重试"}},
                ensure_ascii=False,
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"retry-after", b"60"),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
