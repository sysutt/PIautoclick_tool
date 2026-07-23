"""路径与环境配置。

约定:交换目录 `_run/` 位于 pipeline/ 根下,PixInsight 端(job-runner.js)
和 Python 端在此目录约定一致,通过文件交换 job / result。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# pipeline/ 根目录(本文件位于 pipeline/orchestrator/config.py)
PIPELINE_DIR = Path(__file__).resolve().parent.parent

# 用户配置目录/文件(存 API key 等敏感设置,不进 git)
CONFIG_DIR = PIPELINE_DIR / "_config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

# 默认配置结构(新字段在此登记,load 时与文件合并)
_DEFAULT_SETTINGS: dict[str, Any] = {
    "astrometry_api_key": "",          # nova.astrometry.net API key(在线解析用)
    "pixinsight_exe": "",              # 覆盖 PixInsight.exe 路径(留空自动探测)
    "llm": {                           # 多模态评委(P3)预留
        "provider": "",                #   anthropic / openai / kimi / deepseek / openai_compatible
        "model": "",
        "base_url": "",
        "api_key": "",
    },
}

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


def _merge(base: dict, over: dict) -> dict:
    """递归合并(over 覆盖 base),用于把已存设置并到默认结构上。"""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings() -> dict[str, Any]:
    """读取用户配置(与默认结构合并);文件不存在则返回默认。"""
    import copy
    settings = copy.deepcopy(_DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            settings = _merge(settings, json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    """写入用户配置到本地文件(不进 git)。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)


def get_setting(path: str, default: Any = None) -> Any:
    """按点路径读取设置,如 get_setting('llm.api_key')。"""
    cur: Any = load_settings()
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def pixinsight_exe() -> str | None:
    """定位 PixInsight 可执行文件;找不到返回 None。优先级:配置 > 环境变量 > 常见位置。"""
    cfg = get_setting("pixinsight_exe", "")
    if cfg and Path(cfg).exists():
        return cfg
    env = os.environ.get("PIXINSIGHT_EXE")
    if env and Path(env).exists():
        return env
    for c in _PI_CANDIDATES:
        if Path(c).exists():
            return c
    return None
