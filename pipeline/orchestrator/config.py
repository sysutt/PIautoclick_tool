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
    "graxpert_path": "",               # GraXpert.exe 路径(梯度校正,留空则不用 GraXpert 用 ABE);
                                       #   如 D:/GraXpert/GraXpert.exe。PI 进程 headless 跑不通,
                                       #   走 CLI:GraXpert.exe -cli -cmd background-extraction ...
    "stacking_output_base": "M:/Deepsky",  # WBPP 叠加产物根目录;项目夹命名 YYMMDD_CAM_TARGET,
                                       #   多日为 begindate-enddate_CAM_TARGET
    "llm": {                           # 多模态评委(P3)预留
        "provider": "",                #   anthropic / openai / kimi / deepseek / openai_compatible
        "model": "",
        "base_url": "",
        "api_key": "",
    },
    "astrobin_ref": {                  # AstroBin 同视场参考图检索(经自有后端代理)
        "base_url": "",                #   如 https://app.tickwhale.com
        "api_key": "",                 #   对应后端 .env 的 PIPELINE_API_KEY
    },
    "ai_backend": {                    # AI 后端路由偏好(降噪/修星/去星的三级路由)
        "allow_paid": True,            #   True=装了 rc-astro(收费 BXT/SXT/NXT)则优先用;
                                       #   False=**强制免费路线**(cosmicclarity/StarNet2/DeepSNR),
                                       #   即便装了 rc-astro 也不调(省授权额度/共享机)。免费管线始终保留。
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


def client_id() -> str:
    """本机安装的稳定匿名 id(uuid4 十六进制),给服务端 token 流水归组统计用。
    纯本地随机、无个人信息;首次生成即落盘,以后复用。"""
    cid = get_setting("pipeline.client_id", "")
    if isinstance(cid, str) and cid:
        return cid
    import uuid
    cid = uuid.uuid4().hex
    s = load_settings()
    if not isinstance(s.get("pipeline"), dict):
        s["pipeline"] = {}
    s["pipeline"]["client_id"] = cid
    save_settings(s)
    return cid


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


def pixinsight_dir() -> str | None:
    """PixInsight 安装根目录(由 <root>/bin/PixInsight.exe 反推 <root>)。找不到返回 None。"""
    exe = pixinsight_exe()
    if not exe:
        return None
    return str(Path(exe).resolve().parent.parent)


def pixinsight_library_dir() -> str | None:
    """PixInsight 的 library 目录(<root>/library)——NXT/SXT 等 AI 模型 .pb 放这里。找不到返回 None。"""
    root = pixinsight_dir()
    return str(Path(root) / "library") if root else None
