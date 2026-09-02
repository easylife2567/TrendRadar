"""
Web 层配置装载（design/03 §7、02-D9②）

唯一的配置入口：读 config.yaml `web:` 段，环境变量覆盖。
API Key 不进本模块——认证凭据统一由 web_server/auth.py 从环境变量解析。

运行模式（D9①）：
- "local"  桌面本机形态：仅 127.0.0.1，用户即机主，/setup 首启向导可用
- "server" 工作站/Docker 形态：面向公网访客，/setup 路由不注册，prod 下关 /docs
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from mcp_server.services.parser_service import ParserService


@dataclass
class WebSettings:
    """web_server 运行配置（config.yaml `web:` 段 + 环境变量覆盖）"""

    project_root: Path
    mode: str = "server"                 # "local" | "server"（D9①）
    env: str = "dev"                     # "dev" | "prod"（TRENDRADAR_ENV；prod 关 /docs）
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8080
    require_read_key: bool = False
    cache_ttl_overrides: dict = field(default_factory=dict)
    data_root: Path | None = None        # 数据根目录（含 output/ 的目录），None = project_root

    @property
    def output_root(self) -> Path:
        """output/ 目录：所有按日分库与报告的根（D9② 路径解析集中于此）"""
        return (self.data_root or self.project_root) / "output"


def load_web_settings(project_root: Path | str | None = None, mode: str = "server") -> WebSettings:
    """
    装载 Web 配置。

    优先级：环境变量 > config.yaml `web:` 段 > 默认值。
    配置读取走 ParserService.parse_yaml_config（原始小写嵌套 YAML，与 MCP 工具层同一来源）。
    """
    root = Path(project_root) if project_root else Path(__file__).parent.parent

    web_cfg: dict = {}
    try:
        yaml_cfg = ParserService(str(root)).parse_yaml_config() or {}
        web_cfg = yaml_cfg.get("web") or {}
    except Exception as e:  # 配置缺失/损坏不阻断启动，按默认值运行
        print(f"Warning: 读取 config.yaml web 段失败，使用默认配置: {e}")

    def _env_bool(name: str, default: bool) -> bool:
        v = os.environ.get(name)
        if v is None:
            return default
        return v.strip().lower() in ("1", "true", "yes", "on")

    data_root_cfg = str(web_cfg.get("data_root") or "").strip() or None
    data_root_env = os.environ.get("TRENDRADAR_DATA_ROOT", "").strip() or None

    return WebSettings(
        project_root=root,
        mode=mode,
        env=os.environ.get("TRENDRADAR_ENV", "dev").strip().lower() or "dev",
        enabled=_env_bool("TRENDRADAR_WEB_ENABLED", bool(web_cfg.get("enabled", True))),
        host=os.environ.get("TRENDRADAR_WEB_HOST", "").strip() or str(web_cfg.get("host", "127.0.0.1")),
        port=int(os.environ.get("TRENDRADAR_WEB_PORT", "").strip() or web_cfg.get("port", 8080)),
        require_read_key=_env_bool("TRENDRADAR_REQUIRE_READ_KEY", bool(web_cfg.get("require_read_key", False))),
        cache_ttl_overrides=dict(web_cfg.get("cache_ttl_overrides") or {}),
        data_root=Path(data_root_env or data_root_cfg) if (data_root_env or data_root_cfg) else None,
    )


def resolve_data_root(settings: WebSettings) -> Path:
    """
    解析数据根目录（D9②）。

    优先级：TRENDRADAR_DATA_ROOT > web.data_root > 项目根。
    返回包含 output/ 的目录本身。
    """
    return settings.data_root or settings.project_root
