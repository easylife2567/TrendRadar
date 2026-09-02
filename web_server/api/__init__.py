"""API 路由汇总（design/03 §2 端点树；子路由随 Phase 1 各 Step 逐个接入）"""

from fastapi import APIRouter

api_router = APIRouter()

from . import system  # noqa: E402,F401  isort: skip

api_router.include_router(system.router)
