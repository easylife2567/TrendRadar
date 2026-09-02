"""
工具层实例注册表（design/02 D1：web_server 只组装，不实现业务逻辑）

仿 mcp_server/server.py 的惰性单例模式，按 (project_root, data_root) 维度缓存实例。

两套组装：
- get_read_tools()   查询/分析/检索三件套，readonly=True（D5：新闻库严格只读，
                     只读 URI 打开，永不误建空库/写库）
- get_action_tools() SystemManagementTools 保持非只读（trigger_crawl 需写库）

缓存清理线程与 CacheService 为进程级单例，不随实例维度区分。
"""

from __future__ import annotations

import threading
from typing import Dict

from mcp_server.tools.analytics import AnalyticsTools
from mcp_server.tools.data_query import DataQueryTools
from mcp_server.tools.search_tools import SearchTools
from mcp_server.tools.system import SystemManagementTools

_REGISTRY_LOCK = threading.Lock()
_read_tools: Dict[str, Dict] = {}
_action_tools: Dict[str, SystemManagementTools] = {}


def _instance_key(project_root: str, data_root: str | None) -> str:
    return f"{project_root}|{data_root or ''}"


def get_read_tools(project_root: str, data_root: str | None = None) -> Dict:
    """
    获取只读工具集（查询/分析/检索），进程内惰性单例

    Args:
        project_root: 项目根目录
        data_root: 数据根目录覆盖（D9②）

    Returns:
        {"data_query": DataQueryTools, "analytics": AnalyticsTools, "search": SearchTools}
    """
    key = _instance_key(project_root, data_root)
    with _REGISTRY_LOCK:
        if key not in _read_tools:
            _read_tools[key] = {
                "data_query": DataQueryTools(project_root, readonly=True, data_root=data_root),
                "analytics": AnalyticsTools(project_root, readonly=True, data_root=data_root),
                "search": SearchTools(project_root, readonly=True, data_root=data_root),
            }
        return _read_tools[key]


def get_action_tools(project_root: str, data_root: str | None = None) -> Dict:
    """
    获取动作工具集（系统管理），进程内惰性单例

    注意：SystemManagementTools 非 readonly（trigger_crawl 需写库），
    仅应在需要写路径的端点（POST）中使用。

    Args:
        project_root: 项目根目录
        data_root: 数据根目录覆盖（D9②）

    Returns:
        {"system": SystemManagementTools}
    """
    key = _instance_key(project_root, data_root)
    with _REGISTRY_LOCK:
        if key not in _action_tools:
            _action_tools[key] = SystemManagementTools(project_root, data_root=data_root)
        return _action_tools[key]
