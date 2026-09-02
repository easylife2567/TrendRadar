"""
端点缓存（design/03：GET 默认走 CacheService，TTL 按端点分级，缓存键含全部查询参数）

底层复用 mcp_server/services/cache_service.py 的进程内 TTL 缓存（get_cache() 单例，
与 MCP 工具层共享——trigger_crawl 成功后 clear() 会连带清掉本层缓存，属预期行为）。

注意（cache_service 实现约束）：
- TTL 在读取时判定（get(key, ttl)），因此同一 namespace 的 key 只能被一个端点使用
- 缓存对象是进程内共享引用，路由层只读消费，不得原地改写
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from mcp_server.services.cache_service import get_cache, make_cache_key

from .settings import WebSettings

# 各端点默认 TTL（秒），键名与路由 namespace 一致
DEFAULT_TTLS: dict[str, int] = {
    # system（design/03 §2.1）
    "system.status": 10,
    "system.dates": 60,
    "system.schedule": 30,
    "system.health_sources": 60,
    # news / topics（§2.2）
    "news.latest": 60,
    "news.by_date": 300,
    "news.search": 300,
    "news.rank_history": 300,
    "topics.trending": 120,
    # analytics（§2.3，慢端点更长）
    "analytics.topic_trend": 600,
    "analytics.insights": 600,
    "analytics.viral": 600,
    "analytics.predict": 1800,
    "analytics.compare_periods": 1800,
    "analytics.compare_platforms": 600,
    "analytics.aggregate": 600,
    # rss（§2.5）
    "rss.latest": 60,
    "rss.search": 300,
    "rss.feeds_status": 120,
    # reports（§2.6）
    "reports.list": 300,
    # sentiment（§2.4）
    "sentiment.results": 300,
}

# 过期清理阈值：须 ≥ 本层使用的最大 TTL（P3 情感缓存 6h），否则会把仍有效条目清掉
_CLEANUP_TTL = 7 * 3600
_CLEANUP_INTERVAL = 600

_cleanup_stop = threading.Event()
_cleanup_thread: threading.Thread | None = None


def ttl_for(settings: WebSettings, endpoint: str) -> int:
    """取端点 TTL：config.yaml web.cache_ttl_overrides 覆盖 > DEFAULT_TTLS > 60s"""
    override = settings.cache_ttl_overrides.get(endpoint)
    if override is not None:
        return int(override)
    return DEFAULT_TTLS.get(endpoint, 60)


def cached_call(namespace: str, params: dict, ttl: int, producer: Callable[[], Any]) -> tuple[Any, bool]:
    """
    带缓存的工具层调用。

    Returns:
        (data, cached) —— data 为 producer() 的返回值，cached 指示是否命中缓存
    """
    cache = get_cache()
    key = make_cache_key(namespace, **params)
    hit = cache.get(key, ttl=ttl)
    if hit is not None:
        return hit, True
    value = producer()
    cache.set(key, value)
    return value, False


def start_cache_cleanup() -> None:
    """启动过期条目周期清理线程（仅内存卫生；正确性由读取时 TTL 判定保证）"""
    global _cleanup_thread
    if _cleanup_thread is not None and _cleanup_thread.is_alive():
        return

    def _loop():
        cache = get_cache()
        while not _cleanup_stop.wait(_CLEANUP_INTERVAL):
            try:
                cache.cleanup_expired(ttl=_CLEANUP_TTL)
            except Exception:  # 清理失败不影响服务
                pass

    _cleanup_stop.clear()
    _cleanup_thread = threading.Thread(target=_loop, name="web-cache-cleanup", daemon=True)
    _cleanup_thread.start()


def stop_cache_cleanup() -> None:
    _cleanup_stop.set()
