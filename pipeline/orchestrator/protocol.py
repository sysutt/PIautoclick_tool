"""job / result 交换协议(文件级 IPC)。

- 提交 job:原子写入 INBOX/<job_id>.json(先写 .tmp 再 rename,避免半包读取)。
- 回收 result:轮询 DONE/<job_id>.json。
- 判活:runner 每轮写 HEARTBEAT(毫秒时间戳)。

对应技术方案 §8 的数据契约。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from . import config


def new_job(
    op: str,
    *,
    input: str | None = None,
    params: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造一个 job 字典。op ∈ {probe, selftest, inspect, ...}。"""
    job_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    job: dict[str, Any] = {"job_id": job_id, "op": op}
    if input is not None:
        # PixInsight 端在 Windows 上也接受正斜杠,统一用正斜杠避免转义问题
        job["input"] = str(input).replace("\\", "/")
    if params:
        job["params"] = params
    if outputs:
        job["outputs"] = {
            k: (str(v).replace("\\", "/") if isinstance(v, (str, Path)) else v)
            for k, v in outputs.items()
        }
    return job


def submit(job: dict[str, Any]) -> Path:
    """原子提交 job 到 inbox,返回最终文件路径。"""
    config.ensure_dirs()
    job_id = job["job_id"]
    tmp = config.INBOX / f".{job_id}.json.tmp"
    final = config.INBOX / f"{job_id}.json"
    tmp.write_text(json.dumps(job, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(final)  # 原子 rename
    return final


def wait_result(
    job_id: str, timeout: float = 120.0, poll: float = 0.4
) -> dict[str, Any]:
    """等待并返回 result;超时抛 TimeoutError。"""
    target = config.DONE / f"{job_id}.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if target.exists():
            # 结果文件可能正在写入,短暂重试解析
            for _ in range(6):
                try:
                    return json.loads(target.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.1)
        time.sleep(poll)
    raise TimeoutError(
        f"等待 job {job_id} 结果超时({timeout}s)。"
        f" 请确认 PixInsight 中的 job-runner.js 正在运行。"
    )


def runner_alive(max_age: float = 10.0) -> bool:
    """依据心跳判断 runner 是否在线(max_age 秒内有心跳)。"""
    hb = config.HEARTBEAT
    if not hb.exists():
        return False
    try:
        ts_ms = int(hb.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    now_ms = time.time() * 1000.0
    return (now_ms - ts_ms) < max_age * 1000.0


def request_stop() -> None:
    """请求 runner 优雅停止(写 STOP 文件)。"""
    config.ensure_dirs()
    config.STOP_FILE.write_text("stop", encoding="utf-8")
