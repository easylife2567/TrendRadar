"""
报告归档端点（design/03 §2.6）

文件服务职责（契约明确归 web 层，不走 mcp_server 工具层）：
- /api/reports          列出 output/html/ 下已生成报告（日期、文件、大小）
- /api/reports/{date}/html  返回当日 HTML 报告原文（iframe 嵌入用）

三重防护（design/06 §8）+ 第 0 道缺失检查：
0. 目录/文件不存在 → 404（DATE_NOT_FOUND / NOT_FOUND），绝不 500
1. date 参数严格 ^\\d{4}-\\d{2}-\\d{2}$（或 latest）
2. Path.resolve() 后必须仍在 output/html resolve()之下
3. 白名单扩展名（.html）+ 常规文件检查

绝不暴露 config/、.env、任意路径。
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..envelope import ok
from ..errors import ApiError
from ..settings import WebSettings
from .deps import get_settings

router = APIRouter(tags=["reports"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_EXT = {".html"}
_LATEST_ALIAS = "latest"


def _resolve_report_dir(settings: WebSettings) -> Path:
    return (settings.output_root / "html").resolve()


def _safe_report_file(settings: WebSettings, date: str, filename: str | None) -> Path:
    """
    三重防护后返回目标文件路径。

    date="latest" 时取 output/html/latest/{mode}.html 中字典序最新的一个
    （报告生成器每次刷新 latest/{mode}.html，mode 可多个）。
    filename 为空时取 {date} 目录下字典序最新的 .html（HH-MM 短格式，字典序即时间序）。
    """
    html_dir = _resolve_report_dir(settings)

    if date == _LATEST_ALIAS:
        base = html_dir / _LATEST_ALIAS
    else:
        if not _DATE_RE.match(date):
            raise ApiError(400, "BAD_REQUEST", "date 须为 YYYY-MM-DD 或 latest")
        base = html_dir / date

    # 第 0 道缺失检查（404 非 500）
    if not base.is_dir():
        raise ApiError(404, "DATE_NOT_FOUND", f"该日期没有已生成的报告: {date}")

    if filename is None:
        # 第 2 道：resolve 后必须仍在 html_dir 之下（date 已正则，此处防御 future 改动）
        candidates = sorted(
            p for p in base.glob("*.html")
            if p.suffix.lower() in _ALLOWED_EXT and p.is_file()
            and _under(p.resolve(), html_dir)
        )
        if not candidates:
            raise ApiError(404, "NOT_FOUND", f"{date} 目录下没有 .html 报告")
        target = candidates[-1]
    else:
        # 第 1 道：文件名白名单字符
        if not re.match(r"^[A-Za-z0-9._-]+$", filename) or ".." in filename:
            raise ApiError(400, "BAD_REQUEST", "非法文件名")
        target = base / filename
        resolved = target.resolve()
        if not _under(resolved, html_dir):
            raise ApiError(400, "BAD_REQUEST", "非法路径")
        if not resolved.is_file():
            raise ApiError(404, "NOT_FOUND", "报告文件不存在")

    # 第 3 道：扩展名白名单 + 常规文件
    if target.suffix.lower() not in _ALLOWED_EXT or not target.is_file():
        raise ApiError(404, "NOT_FOUND", "报告文件不存在")

    return target


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@router.get("/reports", summary="已生成的报告列表（日期、文件、大小）")
def list_reports(settings: WebSettings = Depends(get_settings)):
    html_dir = _resolve_report_dir(settings)
    if not html_dir.is_dir():
        # 目录不存在 → 200 空数组（差异#3：本地无 output/html）
        return ok([])

    reports = []
    for date_dir in html_dir.iterdir():
        if not date_dir.is_dir():
            continue
        files = [
            {
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "modified_at": int(f.stat().st_mtime),
            }
            for f in sorted(date_dir.glob("*.html"))
            if f.suffix.lower() in _ALLOWED_EXT and f.is_file()
        ]
        if files:
            reports.append({"date": date_dir.name, "files": files})

    # 日期条目倒序（新日期在前）；latest 别名语义最新，置顶
    dated = [r for r in reports if r["date"] != _LATEST_ALIAS]
    dated.sort(key=lambda r: r["date"], reverse=True)
    latest = [r for r in reports if r["date"] == _LATEST_ALIAS]
    return ok(latest + dated)


@router.get("/reports/{date}/html", summary="当日 HTML 报告原文（iframe 嵌入用）")
def get_report_html(date: str, settings: WebSettings = Depends(get_settings)):
    target = _safe_report_file(settings, date, None)
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise ApiError(404, "NOT_FOUND", "报告文件不可读") from e
    return HTMLResponse(content=content)
