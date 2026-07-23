"""路径与环境配置。

约定:交换目录 `_run/` 位于 pipeline/ 根下,PixInsight 端(job-runner.js)
和 Python 端在此目录约定一致,通过文件交换 job / result。
"""

from __future__ import annotations

import os
from pathlib import Path

# pipeline/ 根目录(本文件位于 pipeline/orchestrator/config.py)
PIPELINE_DIR = Path(__file__).resolve().parent.parent

# 交换目录(与 job-runner.js 中的 _run 对应)
RUN_DIR = PIPELINE_DIR / "_run"
INBOX = RUN_DIR / "inbox"
PROCESSING = RUN_DIR / "processing"
DONE = RUN_DIR / "done"
HEARTBEAT = RUN_DIR / "runner.heartbeat"
STOP_FILE = RUN_DIR / "STOP"

# 常驻脚本路径
JOB_RUNNER_JS = PIPELINE_DIR / "job-runner.js"

# PixInsight 可执行文件的常见安装位置(可用环境变量 PIXINSIGHT_EXE 覆盖)
_PI_CANDIDATES = [
    r"C:\Program Files\PixInsight\bin\PixInsight.exe",
    r"D:\Program Files\PixInsight\bin\PixInsight.exe",
    r"C:\Program Files (x86)\PixInsight\bin\PixInsight.exe",
]


def ensure_dirs() -> None:
    """创建交换目录(幂等)。"""
    for d in (RUN_DIR, INBOX, PROCESSING, DONE):
        d.mkdir(parents=True, exist_ok=True)


def pixinsight_exe() -> str | None:
    """定位 PixInsight 可执行文件;找不到返回 None。"""
    env = os.environ.get("PIXINSIGHT_EXE")
    if env and Path(env).exists():
        return env
    for c in _PI_CANDIDATES:
        if Path(c).exists():
            return c
    return None
