"""
TrendRadar Web 监测中心 — 只读 REST API + 前端薄壳

职责边界（design/02-architecture.md D1/D2）：
- 本包不实现任何查询/分析逻辑，业务全部复用 mcp_server/tools/ 与 services/
- 新闻数据域（output/{news,rss}/{date}.db）严格只读；唯一写例外见 P3 情感落库（D5/D7）
- 对外仅提供 REST API 与静态前端，部署形态见 design/05-deployment-wsl.md
"""

__version__ = "0.1.0"
