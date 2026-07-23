"""弹窗守卫(泛化 AutoClick)—— 任务 #3。

与常驻 job-runner 并行运行的独立进程:监测 PixInsight 的**模态确认框**并自动点掉,
避免自动化流程被意外弹窗卡住(如几何变换"删除天文解析? Proceed"、旋转/裁切确认等)。

PixInsight 是 Qt 程序,按钮非原生 win32 控件 → 用 UI Automation 定位与点击。

安全策略:
- 只处理**同时含肯定按钮(Yes/OK/Continue/Proceed/是/确定/继续)与否定按钮
  (No/Cancel/否/取消)的窗口**——据此判定为"确认框",避免误点主窗口/其它对话框。
- 点肯定按钮让流程继续;**每次点击都记日志**(_run/popup_guard.log + stdout)。
- 仅作用于 PixInsight 进程的窗口。
- --dry-run 只探测记录、不点击(用于观察)。

用法:
    python -m orchestrator.popup_guard            # 守卫(与 runner 并行)
    python -m orchestrator.popup_guard --dry-run  # 只观察
停止:在 _run 放 STOP_GUARD 文件,或 Ctrl-C。
"""

from __future__ import annotations

import argparse
import sys
import time

import uiautomation as auto

try:
    import win32con
    import win32gui
except ImportError:
    win32gui = None
    win32con = None

from . import config

AFFIRM = {"yes", "ok", "continue", "proceed", "是", "确定", "确认", "继续", "接受"}
NEGATIVE = {"no", "cancel", "否", "取消", "关闭"}

STOP_GUARD = config.RUN_DIR / "STOP_GUARD"
LOG_FILE = config.RUN_DIR / "popup_guard.log"


def _clean(name: str) -> str:
    return (name or "").replace("&", "").strip().lower()


def _pi_pid(root) -> int | None:
    """定位 PixInsight 主进程 PID(通过标题含 PixInsight 的顶层窗口)。"""
    for w in root.GetChildren():
        try:
            if "pixinsight" in (w.Name or "").lower():
                return w.ProcessId
        except Exception:
            pass
    return None


def _activate_window(w):
    """短暂把对话框前置(仅 Invoke 失败时的兜底)。不置顶,避免持续抢占焦点挡住其它程序。"""
    try:
        hwnd = w.NativeWindowHandle
    except Exception:
        hwnd = 0
    if hwnd and win32gui is not None:
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass


def _click_button(btn, w) -> str:
    """优先 Invoke(程序化点击,不抢焦点/不置顶,不依赖窗口在前台);
    仅当 Invoke 不可用时才短暂前置窗口 + 物理点击兜底。"""
    try:
        pat = btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            return "invoke"
    except Exception:
        pass
    _activate_window(w)   # 兜底:Invoke 不行才前置
    try:
        btn.Click(simulateMove=False)
        return "click(activated)"
    except Exception as e:
        return f"failed:{e}"


def _collect_buttons(ctrl, depth: int = 6, acc=None):
    if acc is None:
        acc = []
    if depth <= 0:
        return acc
    try:
        for c in ctrl.GetChildren():
            try:
                if "button" in (c.ControlTypeName or "").lower():
                    acc.append(c)
            except Exception:
                pass
            _collect_buttons(c, depth - 1, acc)
    except Exception:
        pass
    return acc


def _collect_texts(ctrl, depth: int = 4, acc=None):
    if acc is None:
        acc = []
    if depth <= 0:
        return acc
    try:
        for c in ctrl.GetChildren():
            try:
                if (c.Name or "").strip():
                    acc.append(c.Name.strip())
            except Exception:
                pass
            _collect_texts(c, depth - 1, acc)
    except Exception:
        pass
    return acc


def _scan_once(root, pid: int, dry_run: bool, log) -> bool:
    """扫描一次;发现确认框则点肯定按钮。返回是否点击。"""
    for w in root.GetChildren():
        try:
            if pid is not None and w.ProcessId != pid:
                continue
            buttons = _collect_buttons(w, depth=6)
            if not buttons:
                continue
            affirm_btn = None
            has_negative = False
            for b in buttons:
                nm = _clean(b.Name)
                if nm in AFFIRM and affirm_btn is None:
                    affirm_btn = b
                if nm in NEGATIVE:
                    has_negative = True
            # 需同时具备肯定+否定按钮 → 判定为确认框(避免误点主窗口)
            if affirm_btn is None or not has_negative:
                continue
            ctx = " | ".join(_collect_texts(w, depth=4)[:6])[:200]
            wname = w.Name or ""
            if dry_run:
                log(f"[dry-run] 发现确认框 '{wname}' 肯定按钮='{affirm_btn.Name}' :: {ctx}")
            else:
                how = _click_button(affirm_btn, w)   # Invoke 优先(不抢焦点),兜底才前置
                log(f"点击 '{affirm_btn.Name}'({how})于确认框 '{wname}' :: {ctx}")
            return True
        except Exception:
            pass
    return False


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    p = argparse.ArgumentParser(description="PixInsight 弹窗守卫")
    p.add_argument("--interval", type=float, default=0.7, help="轮询间隔(秒)")
    p.add_argument("--dry-run", action="store_true", help="只探测记录,不点击")
    args = p.parse_args(argv)

    config.ensure_dirs()
    if STOP_GUARD.exists():
        STOP_GUARD.unlink()

    auto.InitializeUIAutomationInCurrentThread()
    root = auto.GetRootControl()

    def log(msg: str):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    log(f"弹窗守卫启动{'(dry-run)' if args.dry_run else ''}。停止:创建 {STOP_GUARD}")
    pid = _pi_pid(root)
    log(f"PixInsight PID = {pid}" + ("" if pid else "(未找到 PixInsight,将持续重试)"))

    try:
        while not STOP_GUARD.exists():
            if pid is None:
                pid = _pi_pid(root)
            try:
                _scan_once(root, pid, args.dry_run, log)
            except Exception as e:
                log(f"扫描异常: {e}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            auto.UninitializeUIAutomationInCurrentThread()
        except Exception:
            pass
        if STOP_GUARD.exists():
            STOP_GUARD.unlink()
    log("弹窗守卫已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
