"""
AI 执行通道（design/03 §2.4、02-D9④ 泛化预留）

通用 AI 步骤执行器，不写死情感专用（08 预留：Track B 工作台的 AI 步骤复用本通道）：
- run(prompt)                裸执行，返回文本
- run_json(prompt, contract) 执行 + 严格 JSON 解析（json.loads → json-repair 兜底）

键转换（决策表差异项）：AIClient 读扁平大写键（MODEL/API_KEY/…），config.yaml
是 `ai:` 小写嵌套——复用 trendradar.core.loader._load_ai_config 同一转换
（含 AI_MODEL/AI_API_KEY/AI_API_BASE/AI_TIMEOUT 环境变量覆盖），不在本层复制映射表。

护栏（D7）：每日执行上限（进程内计数，重启清零，v1 声明）；串行信号量由
调用方按业务持有（情感分析 asyncio.Semaphore(1)）。

模型输出要求严格 JSON 时，解析失败 → 502 AI_EXECUTION_FAILED（显式报错，
绝不冒充缓存结果——design/04 §7 可信度协议）。
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime
from pathlib import Path

from .errors import ApiError


class AiDailyLimitExceeded(Exception):
    """每日 AI 执行上限（D7 护栏）；retry_after 供 429 Retry-After 头"""

    def __init__(self, limit: int, retry_after: int):
        super().__init__(f"已达每日 AI 执行上限（{limit} 次/日）")
        self.limit = limit
        self.retry_after = retry_after


def prompt_hash(prompt: str) -> str:
    """提示词指纹（sha256 前 16 位，判重与缓存键组成部分）"""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _seconds_until_midnight() -> int:
    from datetime import timedelta

    now = datetime.now()
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return max(60, int((midnight - now).total_seconds()))


class AiRunner:
    """通用 AI 步骤执行器（惰性建客户端；每日上限进程内计数）"""

    def __init__(self, project_root: str | Path, max_daily: int = 50):
        self._project_root = Path(project_root)
        self._max_daily = max_daily
        self._client = None
        self._client_lock = threading.Lock()
        self._count_lock = threading.Lock()
        self._count_day: str = ""
        self._count: int = 0

    # ---------- 配置 ----------

    def _load_client(self):
        """惰性构造 AIClient（litellm 导入较重，不阻塞 web 启动）"""
        with self._client_lock:
            if self._client is not None:
                return self._client
            try:
                from trendradar.core.loader import _load_ai_config
                from mcp_server.services.parser_service import ParserService

                yaml_cfg = ParserService(str(self._project_root)).parse_yaml_config() or {}
            except Exception:
                yaml_cfg = {}  # 配置缺失 → 走环境变量/默认值，执行时显式报错
            from trendradar.ai.client import AIClient

            client = AIClient(_load_ai_config(yaml_cfg))
            valid, message = client.validate_config()
            if not valid:
                raise ApiError(
                    502, "AI_EXECUTION_FAILED",
                    f"AI 服务未配置：{message}",
                )
            self._client = client
            return client

    # ---------- 每日上限 ----------

    def _consume_quota(self) -> None:
        """检查并占用一次执行额度（跨日自动清零；进程内计数，重启清零属 v1 声明语义）"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._count_lock:
            if self._count_day != today:
                self._count_day = today
                self._count = 0
            if self._count >= self._max_daily:
                raise AiDailyLimitExceeded(self._max_daily, _seconds_until_midnight())
            self._count += 1

    def remaining_today(self) -> int:
        with self._count_lock:
            if self._count_day != datetime.now().strftime("%Y-%m-%d"):
                return self._max_daily
            return max(0, self._max_daily - self._count)

    def model_name(self) -> str:
        """当前模型标识（仅在 run 成功后调用——未配置时 _load_client 抛 502）"""
        client = self._load_client()
        return getattr(client, "model", "unknown")

    # ---------- 执行 ----------

    def run(self, prompt: str, system_prompt: str | None = None, *, count_quota: bool = True) -> str:
        """
        执行一次 AI 调用，返回原始文本。

        Raises:
            ApiError(502, AI_EXECUTION_FAILED)：未配置 / 调用失败（透传原因摘要，不透 key）
            AiDailyLimitExceeded：超出每日上限
        """
        if count_quota:
            self._consume_quota()
        client = self._load_client()
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            return client.chat(messages)
        except ApiError:
            raise
        except Exception as e:
            # 透传原因摘要（异常类型 + 首行），绝不透出 api_key
            reason = f"{type(e).__name__}: {str(e)[:200]}" if str(e) else type(e).__name__
            raise ApiError(502, "AI_EXECUTION_FAILED", f"AI 调用失败：{reason}") from e

    def run_json(
        self,
        prompt: str,
        json_contract: str,
        system_prompt: str | None = None,
        *,
        count_quota: bool = True,
    ) -> dict:
        """执行并解析严格 JSON 输出（json.loads → json-repair 兜底）"""
        full_prompt = (
            f"{prompt}\n\n{json_contract}\n\n"
            "只输出 JSON 本身，不要输出任何解释文字或 Markdown 代码块标记。"
        )
        return self._parse_output(self.run(full_prompt, system_prompt, count_quota=count_quota))

    def _parse_output(self, raw: str) -> dict:
        """json.loads 优先，json-repair 兜底（容忍模型输出尾随逗号/单引号等）"""
        text = (raw or "").strip()
        # 剥离常见的 ```json 包裹
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            import json

            return json.loads(text)
        except ValueError:
            pass
        try:
            import json_repair

            return json_repair.loads(text)
        except Exception as e:
            raise ApiError(502, "AI_EXECUTION_FAILED", f"AI 输出无法解析为 JSON：{type(e).__name__}") from e

    # ---------- 状态（系统页展示用） ----------

    def status(self) -> dict:
        return {"daily_limit": self._max_daily, "remaining_today": self.remaining_today(), "timestamp": time.time()}
