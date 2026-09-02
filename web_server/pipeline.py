"""
完整管线启动器（design/03 §2.1 POST /api/pipeline/run）

两级启动策略：
1. systemd-run transient unit（工作站/WSL 形态，design/05）：journal 有完整日志、
   与 timer 语义一致、Web 进程不 fork 长命子进程
2. Popen 降级（本机开发/无 systemd 环境）：直接 fork `python -m trendradar`

重复触发判定（进程内存，v1 单进程声明）：
- systemd-run：unit 启动后命令立即返回，min_interval 窗口内用
  `systemctl is-active` 探测 unit 存活
- Popen：pid 存活探测（kill 0）

运行中再触发抛 PipelineAlreadyRunning → 路由层转 409。
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


class PipelineAlreadyRunning(Exception):
    def __init__(self, launch: "PipelineLaunch"):
        self.launch = launch
        super().__init__(f"管线已在运行中（{launch.describe()}）")


class LauncherUnavailable(Exception):
    """两级启动器均不可用"""


@dataclass
class PipelineLaunch:
    mode: str  # "systemd-run" | "popen"
    unit: str | None = None
    pid: int | None = None

    def describe(self) -> str:
        if self.mode == "systemd-run":
            return f"unit={self.unit}"
        return f"pid={self.pid}"


def _pid_alive(pid: int) -> bool:
    try:
        import os

        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 存在但属其他用户


class PipelineRunner:
    """进程内单例语义：一个 Web 进程同一时刻只允许一条手动管线"""

    def __init__(self, project_root: Path, min_interval: int = 60, python: str | None = None):
        self.project_root = Path(project_root)
        self.min_interval = min_interval
        self._python = python or str(Path(sys.executable).resolve())
        self._lock = threading.Lock()
        self._last_launch: tuple[float, PipelineLaunch] | None = None

    # ---- 探测（无锁内部版） ----

    def _systemd_available(self) -> bool:
        return Path("/run/systemd/system").exists()

    def _is_running_locked(self) -> tuple[bool, PipelineLaunch | None]:
        rec = self._last_launch
        if rec is None:
            return False, None
        started_at, launch = rec
        if time.monotonic() - started_at >= self.min_interval:
            return False, launch
        if launch.mode == "systemd-run" and launch.unit:
            try:
                r = subprocess.run(
                    ["systemctl", "is-active", "--quiet", launch.unit],
                    capture_output=True, timeout=5,
                )
                return r.returncode == 0, launch
            except Exception:
                return False, launch
        if launch.mode == "popen" and launch.pid:
            return _pid_alive(launch.pid), launch
        return False, launch

    # ---- 对外 ----

    def is_running(self) -> tuple[bool, PipelineLaunch | None]:
        with self._lock:
            return self._is_running_locked()

    def launch(self) -> PipelineLaunch:
        """启动完整管线。运行中抛 PipelineAlreadyRunning"""
        with self._lock:
            running, prev = self._is_running_locked()
            if running:
                raise PipelineAlreadyRunning(prev)

            if self._systemd_available():
                launch = self._launch_systemd_run()
            else:
                launch = self._launch_popen()

            self._last_launch = (time.monotonic(), launch)
            return launch

    def _launch_systemd_run(self) -> PipelineLaunch:
        unit = f"trendradar-manual-{int(time.time())}"
        cmd = [
            "systemd-run", "--unit", unit,
            "--property", "After=trendradar-web.service",
            "--description", "TrendRadar manual pipeline (web trigger)",
            self._python, "-m", "trendradar",
        ]
        try:
            subprocess.run(
                cmd, cwd=str(self.project_root), check=True,
                capture_output=True, timeout=15,
            )
        except FileNotFoundError as e:
            raise LauncherUnavailable(f"systemd-run 不可用: {e}") from e
        except subprocess.CalledProcessError as e:
            # systemd 存在但命令失败（如权限）——降级 Popen 可能同样无意义，直接暴露
            raise LauncherUnavailable(
                f"systemd-run 启动失败（exit {e.returncode}）: "
                f"{(e.stderr or b'').decode(errors='replace')[:200]}"
            ) from e
        return PipelineLaunch("systemd-run", unit=unit)

    def _launch_popen(self) -> PipelineLaunch:
        log_path = self.project_root / "output" / "pipeline_manual.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as log_file:
            proc = subprocess.Popen(
                [self._python, "-m", "trendradar"],
                cwd=str(self.project_root),
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        return PipelineLaunch("popen", pid=proc.pid)
