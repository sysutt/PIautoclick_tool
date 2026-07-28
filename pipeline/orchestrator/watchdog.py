"""看门狗(watchdog)—— 统一监测 PixInsight 自动化管线的运行状态并自愈。

一个进程同时做两件事:
 1) **弹窗自动处理**:复用 popup_guard 的扫描,自动点掉模态确认框
    (如几何变换"删除天文解析? Proceed"、裁切/旋转确认)。
 2) **真·卡死检测 + 自动重启**:区分"正在算长任务"与"真卡死"。
    job-runner 的心跳只在 poll 循环开头写(processOne 阻塞期间不更新),
    所以**长任务期间心跳本就会变旧**——单看心跳会误判。正确判据(全部满足才判卡死):
      - `_run/processing/` 里有在途任务(runner 正应在干活);
      - 心跳年龄 > HB_STALE;
      - PI 进程 CPU 在采样窗口内**几乎不涨**(<CPU_FLAT 秒);说明不是在算;
      - 当前没有待点的弹窗(弹窗交给上面那条处理);
      - 连续 CONFIRM 次复核仍成立(防抖)。
    判定卡死 → 杀 PI + 冷启 runner + 把 processing/*.json 移回 inbox 重新入队
    (等待中的 Python wait_result 会因 done/ 最终写出而正常返回)。

用法:
    python -m orchestrator.watchdog                 # 守卫(与 runner 并行)
    python -m orchestrator.watchdog --dry-run       # 只监测记录,不点/不重启
停止:在 _run 放 STOP_WATCHDOG 文件,或 Ctrl-C。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

import uiautomation as auto

from . import config
from . import popup_guard as pg

STOP_WD = config.RUN_DIR / "STOP_WATCHDOG"
LOG_FILE = config.RUN_DIR / "watchdog.log"

# 判据阈值
HB_STALE = 75.0        # 心跳年龄超过此秒数才考虑卡死(需 > 单步长任务的 poll 间隔富余)
CPU_FLAT = 1.5         # 采样窗口内 CPU 增量(秒)低于此值视为"没在算"
CHECK_INTERVAL = 20.0  # 卡死复核间隔(秒);同时也是 CPU 采样窗口
CONFIRM = 2            # 连续复核成立次数(防抖):2 → 约 40s 持续无活动才重启
DIALOG_POLL = 1.0      # 弹窗扫描间隔(秒)


def _log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _pi_cpu_seconds():
    """返回 PixInsight 进程累计 CPU 秒(所有实例求和);无进程返回 None。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$p=Get-Process PixInsight -ErrorAction SilentlyContinue;"
             "if($p){ ($p | Measure-Object -Property CPU -Sum).Sum } else { 'NONE' }"],
            capture_output=True, text=True, timeout=20).stdout.strip()
        if out == "NONE" or out == "":
            return None
        return float(out)
    except Exception:
        return None


def _heartbeat_age():
    hb = config.HEARTBEAT
    try:
        return time.time() - os.path.getmtime(hb)
    except OSError:
        return None  # 无心跳文件


def _processing_jobs():
    try:
        return [f for f in os.listdir(config.PROCESSING) if f.endswith(".json")]
    except OSError:
        return []


def _pixinsight_exe():
    exe = config.pixinsight_exe()
    return exe or r"C:\Program Files\PixInsight\bin\PixInsight.exe"


def restart_runner():
    """杀 PI + 把在途任务移回 inbox + 冷启 runner。popup_guard/本看门狗继续清理启动弹窗。"""
    _log("RESTART: killing PixInsight ...")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Process PixInsight -ErrorAction SilentlyContinue | Stop-Process -Force"],
                       capture_output=True, text=True, timeout=30)
    except Exception as e:
        _log(f"  kill error: {e}")
    time.sleep(3)
    # 心跳清掉
    try:
        if config.HEARTBEAT.exists():
            config.HEARTBEAT.unlink()
    except OSError:
        pass
    # 在途任务重新入队(processing → inbox)
    requeued = 0
    for f in _processing_jobs():
        try:
            shutil.move(str(config.PROCESSING / f), str(config.INBOX / f))
            requeued += 1
        except OSError:
            pass
    _log(f"  requeued {requeued} in-flight job(s)")
    # 冷启 runner
    exe = _pixinsight_exe()
    runner = str(config.JOB_RUNNER_JS)
    try:
        subprocess.Popen(f'"{exe}" -n "-r={runner}"', shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        _log(f"  relaunch error: {e}")
    # 等心跳恢复(最多 60s)
    for _ in range(60):
        age = _heartbeat_age()
        if age is not None and age < 10:
            _log("  runner back online.")
            return True
        time.sleep(1)
    _log("  WARNING: runner did not report heartbeat within 60s")
    return False


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description="PixInsight 管线看门狗")
    ap.add_argument("--dry-run", action="store_true", help="只监测记录,不点弹窗/不重启")
    args = ap.parse_args(argv)

    config.ensure_dirs()
    if STOP_WD.exists():
        STOP_WD.unlink()

    _log(f"watchdog starting (dry_run={args.dry_run}). HB_STALE={HB_STALE}s "
         f"CPU_FLAT={CPU_FLAT}s/{CHECK_INTERVAL}s CONFIRM={CONFIRM}; initializing UIA...")
    auto.InitializeUIAutomationInCurrentThread()
    root = auto.GetRootControl()
    pid = pg._pi_pid(root)
    _log("UIA ready; monitoring.")

    last_cpu = _pi_cpu_seconds()
    last_check = time.time()
    flat_hits = 0
    dialog_recent = 0.0

    while True:
        if STOP_WD.exists():
            try: STOP_WD.unlink()
            except OSError: pass
            _log("STOP_WATCHDOG detected, exiting.")
            break

        # 1) 弹窗扫描(高频)
        try:
            pid = pid or pg._pi_pid(root)
            clicked = pg._scan_once(root, pid, args.dry_run, _log)
            if clicked:
                dialog_recent = time.time()
        except Exception:
            pass

        # 2) 卡死复核(低频)
        now = time.time()
        if now - last_check >= CHECK_INTERVAL:
            cpu = _pi_cpu_seconds()
            age = _heartbeat_age()
            proc = _processing_jobs()
            cpu_delta = (cpu - last_cpu) if (cpu is not None and last_cpu is not None) else None
            no_recent_dialog = (now - dialog_recent) > CHECK_INTERVAL

            hung = (
                proc                                  # 有在途任务
                and (age is None or age > HB_STALE)   # 心跳旧/丢失
                and cpu is not None                   # PI 还在(否则是崩溃,单独处理)
                and cpu_delta is not None and cpu_delta < CPU_FLAT   # CPU 没涨=没在算
                and no_recent_dialog                  # 不是刚点过弹窗
            )
            if hung:
                flat_hits += 1
                _log(f"suspect hang: job={proc[:1]} hb_age={None if age is None else round(age)} "
                     f"cpuΔ={round(cpu_delta,2)}s/{int(CHECK_INTERVAL)}s hits={flat_hits}/{CONFIRM}")
                if flat_hits >= CONFIRM and not args.dry_run:
                    _log("HANG CONFIRMED -> restarting runner + requeue")
                    restart_runner()
                    flat_hits = 0
                    last_cpu = _pi_cpu_seconds()
                    last_check = time.time()
                    continue
            else:
                if flat_hits:
                    _log(f"activity resumed (cpuΔ={None if cpu_delta is None else round(cpu_delta,2)}), reset")
                flat_hits = 0
            # crash 检测:PI 不在但有在途任务 → 也重启
            if proc and cpu is None and not args.dry_run:
                _log("PixInsight not running but jobs in flight -> restart")
                restart_runner()
            last_cpu = cpu
            last_check = now

        time.sleep(DIALOG_POLL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
