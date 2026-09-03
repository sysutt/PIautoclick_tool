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


def runner_busy() -> bool:
    """runner 是否正**忙于**执行任务(processing/ 里有在途作业文件)。

    job-runner 主循环只在轮询顶部写一次心跳,随后 processOne→runJob 是**阻塞长调用**
    (WBPP 整合几十上百帧 / BXT / 去卷积,可长达几十分钟),执行期间根本回不到循环写心跳
    → 心跳自然变旧 → 若只看 runner_alive() 会误判「未运行」,但其实活着在忙。
    只要 processing/ 里有作业,就说明 runner 领了活正在跑。真死(崩溃/挂起)由看门狗依
    「心跳旧 + CPU 平」判并重启;重启后新 runner 会立刻写新心跳 → runner_alive() 先命中
    「在线」,遗留在 processing/ 的孤儿文件不会被误读成「忙」(见 runner_status 的判序)。

    **关键(2026-09-03 修)**:必须**心跳文件存在**才可能「忙」。释放/重载会删掉心跳文件
    (config.HEARTBEAT.unlink),此时 processing/ 里若有作业,是上次崩溃/超时**遗留的孤儿**
    (runner 早已不在),绝不能误报「忙」→ 否则「开始处理」以为 runner 在跑、跳过冷启 PI,
    新任务丢进 inbox 永远没人处理(用户实测:筛帧超时后 processing 留孤儿 → 整合 job 干等)。
    长任务执行中心跳**时间戳**会旧,但心跳**文件仍在** → 仍判忙,不受影响。"""
    try:
        if not config.HEARTBEAT.exists():          # 无心跳文件 = runner 已释放/未启动 → processing 里的是孤儿
            return False
        d = config.PROCESSING
        return d.exists() and any(p.suffix == ".json" for p in d.iterdir())
    except OSError:
        return False


def runner_status(max_age: float = 10.0) -> str:
    """runner 三态:'online'(心跳新鲜)| 'busy'(心跳旧但有在途作业,长任务执行中)| 'offline'。
    **先判心跳**:心跳新一律「在线」(即便 processing/ 有崩溃遗留的孤儿文件也不误报忙)。"""
    if runner_alive(max_age):
        return "online"
    if runner_busy():
        return "busy"
    return "offline"


def runner_up(max_age: float = 10.0) -> bool:
    """runner 是否**在位**(在线 or 忙)——用于「该不该冷启动 PixInsight」判定:忙着的 runner
    也在位,新任务丢进 inbox/ 排队即可,别再拉起第二个 PI。区别于 runner_alive()(严格心跳,
    表示循环此刻可响应)。"""
    return runner_alive(max_age) or runner_busy()


def request_stop() -> None:
    """请求 runner 优雅停止(写 STOP 文件)。"""
    config.ensure_dirs()
    config.STOP_FILE.write_text("stop", encoding="utf-8")
