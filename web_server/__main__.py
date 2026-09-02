"""
`python -m web_server` CLI（design/05 §3：systemd unit 以本入口启动）

端口优先级：CLI --port > 环境变量 TRENDRADAR_WEB_PORT > config.yaml web.port > 8080
v1 单进程部署（限流桶与 AI 每日计数器为进程内存实现，勿加 --workers）。
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from .app import create_app
from .settings import load_web_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m web_server",
        description="TrendRadar Web 监测中心（只读 REST API + 前端薄壳）",
    )
    parser.add_argument("--host", default=None, help="监听地址（默认取 config web.host，即 127.0.0.1）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认取 TRENDRADAR_WEB_PORT 或 config web.port）")
    parser.add_argument("--mode", choices=("local", "server"), default="server",
                        help="运行模式（D9①：local=桌面本机形态，server=工作站/Docker 形态）")
    parser.add_argument("--project-root", default=None, help="项目根目录（默认自动定位）")
    args = parser.parse_args(argv)

    settings = load_web_settings(args.project_root, mode=args.mode)
    if not settings.enabled:
        print("Web 服务已在 config.yaml 中禁用（web.enabled: false），退出。")
        return 0

    host = args.host or settings.host
    port = args.port or settings.port

    app = create_app(mode=args.mode, settings=settings)
    uvicorn.run(app, host=host, port=port, access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
