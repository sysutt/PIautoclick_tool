"""磁盘维护:清理本工具自己留下的临时/中间产物。

两类垃圾,都在**启动最早期**做一次(失败绝不能影响启动):
  ① PyInstaller 的 `_MEI*` 解压残留 —— 打包版(onefile)启动时解压到 %TEMP%,正常退出自删;
     被强杀(看门狗 taskkill / 崩溃)时清理没机会跑,于是累积。
     注:**TTAstroPiLot 本体是源码运行**(`python -m orchestrator.app_ui`),不产生 _MEI;
     这一步是给同目录下的打包版(dist/PixInsightAutoClicker.exe)和将来可能的打包版兜底。
  ② `_run` 里的中间图像 —— 逐步处理的每一步都落一张 .xisf/.png,跑完没人清,持续累积
     (实测 211 个 .xisf / 21.4 GB)。成品在 M:/Deepsky,这些只是过程产物。

**安全边界(宁可保守):**
  · `_run` 只扫**顶层文件**,绝不递归 —— 子目录 `_cal__*`(校准母版)、`done`/`inbox`/
    `processing`(任务队列)、`handoff_*`、`astrobin_*`(参考图)全部天然免疫;
  · 只删图像类扩展名,日志/状态/脚本类一律不动;
  · 只删超过保留期的 —— 正在跑的任务其文件是新的,天然免疫;
  · `_config` / `_projects` / `_style_cal` / `M:/Deepsky` **从不出现在扫描范围里**。
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path

from . import config

_MEI_RE = re.compile(r"^_MEI\d+$")          # 按需求:_MEI 后跟数字,避免误伤别的同前缀目录
# 中间图像的扩展名;.log/.json/.ssf/.js/.txt/.heartbeat 等状态类一律不动
_IMG_EXT = {".xisf", ".png", ".fit", ".fits", ".tif", ".tiff"}


def _fmt(n: int) -> str:
    return "%.2f GB" % (n / 1e9) if n >= 1e8 else "%.1f MB" % (n / 1e6)


def _dir_size(p: Path) -> int:
    t = 0
    try:
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    t += f.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return t


def clean_mei(age_h: float | None = None, dry_run: bool = False, log=print) -> dict:
    """删 %TEMP% 下超龄的 PyInstaller `_MEI<数字>` 残留目录。返回 {n, bytes}。"""
    res = {"n": 0, "bytes": 0, "skipped": 0}
    try:
        age_h = float(config.MEI_CLEAN_AGE_H if age_h is None else age_h)
        tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "")
        if not tmp.is_dir():
            return res
        # 当前实例自己的解压目录(仅打包版有)绝不能删
        self_dir = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else None
        now = time.time()
        cand = []
        for d in tmp.iterdir():
            try:
                if not d.is_dir() or not _MEI_RE.match(d.name):
                    continue
                if self_dir and d.resolve() == self_dir.resolve():
                    continue
                if (now - d.stat().st_mtime) < age_h * 3600.0:
                    continue
                cand.append((d, _dir_size(d)))
            except OSError:
                continue
        if not cand:
            return res
        total = sum(s for _, s in cand)
        log("  [维护] %%TEMP%% 里有 %d 个超过 %.0f 小时的 _MEI 残留,合计 %s%s"
            % (len(cand), age_h, _fmt(total), "(试运行,不删)" if dry_run else ""))
        for d, s in cand:
            if dry_run:
                res["n"] += 1; res["bytes"] += s
                continue
            try:
                shutil.rmtree(d)                       # 删不掉 = 有别的实例在用,跳过即可
                res["n"] += 1; res["bytes"] += s
            except (PermissionError, OSError):
                res["skipped"] += 1
        if res["n"] or res["skipped"]:
            log("  [维护] _MEI 清理:删除 %d 个(释放 %s)%s"
                % (res["n"], _fmt(res["bytes"]),
                   ",%d 个占用中已跳过" % res["skipped"] if res["skipped"] else ""))
    except Exception as e:                             # 维护失败绝不影响启动
        try: log("  [维护] _MEI 清理跳过(异常):%s" % e)
        except Exception: pass
    return res


def clean_run_intermediates(keep_days: float | None = None, dry_run: bool = False,
                            log=print) -> dict:
    """删 `_run` **顶层**超过保留期的中间图像。返回 {n, bytes}。"""
    res = {"n": 0, "bytes": 0, "skipped": 0}
    try:
        keep = float(config.RUN_KEEP_DAYS if keep_days is None else keep_days)
        run = Path(config.RUN_DIR)
        if not run.is_dir():
            return res
        now = time.time()
        cand = []
        for f in run.iterdir():                        # **不递归**:子目录全部免疫
            try:
                if not f.is_file() or f.suffix.lower() not in _IMG_EXT:
                    continue
                st = f.stat()
                if (now - st.st_mtime) < keep * 86400.0:
                    continue                           # 新文件(含正在跑的任务)一律保留
                cand.append((f, st.st_size))
            except OSError:
                continue
        if not cand:
            return res
        total = sum(s for _, s in cand)
        log("  [维护] _run 顶层有 %d 个超过 %.1f 天的中间图像,合计 %s%s"
            % (len(cand), keep, _fmt(total), "(试运行,不删)" if dry_run else ""))
        for f, s in cand:
            if dry_run:
                res["n"] += 1; res["bytes"] += s
                continue
            try:
                f.unlink()
                res["n"] += 1; res["bytes"] += s
            except (PermissionError, OSError):
                res["skipped"] += 1                    # 被占用 = 有任务在用,跳过
        if res["n"] or res["skipped"]:
            log("  [维护] 中间产物清理:删除 %d 个(释放 %s)%s"
                % (res["n"], _fmt(res["bytes"]),
                   ",%d 个占用中已跳过" % res["skipped"] if res["skipped"] else ""))
    except Exception as e:
        try: log("  [维护] 中间产物清理跳过(异常):%s" % e)
        except Exception: pass
    return res


def startup_maintenance(log=print, dry_run: bool = False) -> dict:
    """启动时的一揽子维护。整体 try/except:**任何失败都不能挡住启动**。"""
    out = {}
    try:
        out["mei"] = clean_mei(dry_run=dry_run, log=log)
        out["run"] = clean_run_intermediates(dry_run=dry_run, log=log)
        freed = out["mei"]["bytes"] + out["run"]["bytes"]
        if freed:
            log("  [维护] 本次共释放 %s" % _fmt(freed))
    except Exception as e:
        try: log("  [维护] 启动维护整体跳过(异常):%s" % e)
        except Exception: pass
    return out
