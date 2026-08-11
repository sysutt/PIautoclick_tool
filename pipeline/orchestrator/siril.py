"""Siril 命令行集成(引擎中立后端 / 无 PixInsight 后期)。

#3 对等引擎的基石:Siril 有完整的脚本 CLI(siril-cli.exe -s script.ssf),原生读写 XISF/FITS,
把纯像素运算(背景提取/拉伸/合成/裁切/降噪…)映射到 Siril 命令 → 让管线**不依赖 PixInsight** 也能跑
(PI 本身收费,这是给买不起 PI 的用户的)。模板同 graxpert.py:resolve 路径 → 拼脚本 → subprocess → 校验产出。

已验证(2026-08-11,Siril 1.4.0-beta2):
- 原生读 XISF(load 直接吃 .xisf);save=FITS(.fit)、savepng/savejpg/savetif 出对应格式。
- subsky(背景提取,degree 多项式 或 -rbf)、autostretch(自动拉伸)可用。
- **denoise(NL-Bayes)在 1.4.0-beta2 有 bug**:处理到收尾必报 "no suitable data in src fits"(与图无关)
  → 降噪暂走 GraXpert CLI(graxpert.py,也不碰 PI);待 Siril 稳定版修复或换 denoise 命令。
"""
from __future__ import annotations

import os
import subprocess

from . import config


def siril_exe() -> str | None:
    """返回 siril-cli.exe 路径(config 的 siril_path 优先,否则常见安装位置)。"""
    try:
        p = config.load_settings().get("siril_path", "")
    except Exception:
        p = ""
    if p and os.path.exists(p):
        return p
    for c in [r"C:/Program Files/Siril/bin/siril-cli.exe",
              r"C:/Program Files/SiriL/bin/siril-cli.exe",
              r"C:/Program Files (x86)/Siril/bin/siril-cli.exe"]:
        if os.path.exists(c):
            return c
    return None


def available() -> bool:
    return siril_exe() is not None


def version() -> str | None:
    exe = siril_exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return (r.stdout or "").strip().splitlines()[0] if r.stdout else None
    except Exception:
        return None


def run_script(commands: list[str], *, requires: str = "1.2.0",
               timeout: float = 900.0) -> tuple[bool, str]:
    """把命令列表写成 .ssf → 跑 `siril-cli -s` → 返回 (ok, 合并输出)。
    ok 判据:输出含成功标记且无失败/error 标记(Siril 中文本地化会打"脚本执行成功完成"/"脚本执行失败")。"""
    exe = siril_exe()
    if not exe:
        raise RuntimeError("Siril 不可用:未找到 siril-cli.exe(在配置里填 siril_path)")
    script = "requires " + requires + "\n" + "\n".join(commands) + "\n"
    sd = str(config.RUN_DIR)
    os.makedirs(sd, exist_ok=True)
    sp = os.path.join(sd, "_siril_job.ssf").replace("\\", "/")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    r = subprocess.run([exe, "-s", sp], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    # 注:Siril 1.4-beta 退出时常打一条**伪错误** "error: no suitable data in src fits"(在脚本成功之后),
    #   不能当失败标志;只认显式的"脚本执行失败"/"Script execution failed"。真正成败由调用方查产出文件。
    fail = ("脚本执行失败" in out) or ("Script execution failed" in out)
    return (not fail), out


def process_poc(input_path: str, output_noext: str, *, bg: str = "1",
                denoise: str = "none", timeout: float = 1200.0) -> str:
    """【无 PI 整流程 POC】Siril:load → subsky 背景提取 → [denoise] → autostretch → savepng。
    全程不碰 PixInsight。返回 <output_noext>.png。

    bg: subsky 参数——数字=多项式阶数;或 "-rbf -samples=20 -smooth=0.5"。
    denoise: "none"(默认)/ "fmedian"(Siril 中值,基础降噪)。
      注:AI 级降噪目前 PI-free 都受阻——Siril 1.4-beta NL-Bayes 有 bug(收尾报 "no suitable data")、
      GraXpert denoise 模型未装且下载源不通;待 Siril 稳定版或手动装 GraXpert denoise 模型后再接。
    """
    inp = str(input_path).replace("\\", "/")
    out = str(output_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    cmds = [f"load {inp}", "subsky " + bg]
    if denoise == "fmedian":
        cmds.append("fmedian 3 1")   # 3x3 中值,1 次迭代(基础降噪,非 AI)
    cmds += ["autostretch", f"savepng {out}"]
    ok, log = run_script(cmds, timeout=timeout)
    final = out + ".png"
    # 成败以产出文件为准(Siril beta 退出伪错误不可信)
    if not os.path.exists(final):
        raise RuntimeError("Siril POC 失败(无产出 PNG)\n" + log[-1500:])
    return final
