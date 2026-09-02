"""
FastAPI 应用工厂（design/02 D2/D9）

create_app(mode) 是唯一的 app 构造入口：
- mode="local"  桌面本机形态（D9①）：/setup 首启向导挂载点保留（Track B 落地）
- mode="server" 工作站/Docker 形态：面向公网，/setup 路由不注册（非隐藏——根本不存在）

中间件栈（注册顺序敏感，Starlette 后注册者在外层先执行，一次写全勿回改）：
    AccessLogMiddleware  最外层：访问日志
    RateLimitMiddleware  限流（先于认证：认证失败也消耗额度，防暴力猜 key）
    AuthMiddleware       认证（内层）
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from . import __version__
from .auth import AuthMiddleware, load_api_key
from .cache import start_cache_cleanup, stop_cache_cleanup
from .errors import ApiError, register_error_handlers
from .logging_mw import AccessLogMiddleware
from .ratelimit import ANALYTICS_PER_MIN, DEFAULT_PER_MIN, RateLimitMiddleware
from .settings import WebSettings, load_web_settings

_PLACEHOLDER_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TrendRadar Web</title>
<style>
  body { font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0;
         background: #0f1115; color: #e8eaf0; }
  main { text-align: center; }
  h1 { font-size: 22px; margin: 0 0 8px; }
  p { color: #9aa3b5; margin: 4px 0; }
  code { color: #818cf8; }
</style>
</head>
<body>
<main>
  <h1>TrendRadar Web is alive</h1>
  <p>API 文档（仅非生产环境）：<code>/docs</code></p>
  <p>健康检查：<code>/api/system/status</code></p>
</main>
</body>
</html>"""


def create_app(mode: str = "server", settings: WebSettings | None = None) -> FastAPI:
    """构造 FastAPI 应用。mode 见模块 docstring（D9①）"""
    if mode not in ("local", "server"):
        raise ValueError(f"未知运行模式: {mode!r}（须为 local|server）")

    settings = settings or load_web_settings(mode=mode)
    is_prod = settings.env == "prod"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        start_cache_cleanup()
        yield
        stop_cache_cleanup()

    app = FastAPI(
        title="TrendRadar Web API",
        version=__version__,
        description="TrendRadar AI 舆情监测中心只读 API（业务逻辑全部复用 mcp_server 工具层）",
        # design/06 §5：prod 关闭 /docs 与 /redoc（仅本地调试可见）
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.project_root = settings.project_root
    # 手动管线启动器（POST /api/pipeline/run 用；app 级实例保证运行中判定的进程内一致性）
    from .pipeline import PipelineRunner

    app.state.pipeline_runner = PipelineRunner(settings.project_root)

    register_error_handlers(app)

    # ---- 路由（统一 /api 前缀，子路由在 web_server/api/ 汇总） ----
    from .api import api_router

    app.include_router(api_router, prefix="/api")

    # ---- 前端静态托管（P2，design/04 §7）：web_server/static/ 由 frontend 构建产出 ----
    # catch-all 必须在全部 /api 路由注册之后；内部先拒 api/docs 等前缀，
    # 否则未匹配的 API 路由会被 SPA fallback 吃掉返回 HTML 200（design/07 验收项）
    static_dir = Path(__file__).parent / "static"
    if (static_dir / "index.html").is_file():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        # SPA 前端路由白名单：fallback 只服务已知页面，不给任意路径回 200 HTML
        # （否则 /etc/passwd/html 这类穿越探测路径会被吞成 200，design/06 §8）
        _SPA_ROUTES = {
            "dashboard", "live", "topics", "search",
            "sentiment", "compare", "reports", "system",
        }

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            from fastapi.responses import FileResponse

            if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
                raise ApiError(404, "NOT_FOUND", "Not Found")
            if ".." in full_path.split("/") or full_path == "favicon.ico":
                raise ApiError(404, "NOT_FOUND", "Not Found")
            candidate = static_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            # SPA history 路由 fallback：白名单页面 + 根路径
            if not full_path or full_path.split("/", 1)[0] in _SPA_ROUTES:
                return FileResponse(static_dir / "index.html")
            raise ApiError(404, "NOT_FOUND", "Not Found")

    else:

        @app.get("/", include_in_schema=False)
        def index():
            from fastapi.responses import HTMLResponse

            return HTMLResponse(_PLACEHOLDER_HTML)

    # ---- 中间件栈：注册顺序即执行顺序的倒序，勿调整（见模块 docstring） ----
    app.add_middleware(
        AuthMiddleware,
        api_key=load_api_key(settings.project_root),
        require_read_key=settings.require_read_key,
        project_root=settings.project_root,
    )
    app.add_middleware(
        RateLimitMiddleware,
        host=settings.host,
        analytics_per_min=ANALYTICS_PER_MIN,
        default_per_min=DEFAULT_PER_MIN,
    )
    app.add_middleware(AccessLogMiddleware)

    # ---- D9③：首启向导挂载点（仅本机模式；工作站/Docker 模式下 /setup 路由不存在） ----
    if mode == "local":
        pass  # /setup 路由挂载点——Track B Phase 6 落地；届时在此 include setup router

    return app


def run():
    """`trendradar-web` script 入口（转调 __main__.main）"""
    from .__main__ import main

    main()


# 供 `uvicorn web_server.app:create_app` 工厂模式引用（默认 server 形态）
app: FastAPI | None = None
