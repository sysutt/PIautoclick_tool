"""rc-astro CLI 集成(BXT 星点修复/反卷 · SXT 去星 · NXT 降噪)。

rc-astro 是 Russell Croman 的 BlurXTerminator/StarXTerminator/NoiseXTerminator 的**独立命令行版**:
一个 CLI 全包、跨平台、GPU 加速、读写 FITS+XISF,**持牌用户免费**。装法见 deps.py EXTERNAL(app 内有指引)。
用它补 Siril 无法做的**拉线星点修复**(BXT),以及专业反卷/去星/降噪。

**⚠️ CLI 参数需在真实安装上核对**:rc-astro CLI 较新、各版子命令/选项名可能有别。下方按官方文档
形态(`rc-astro bxt -i in -o out --sharpen-stars 0.5 ...`)实现;首次在用户机跑通后据实修正 _run()。
rcastro_path 来自 config(产品里让用户填,见 deps.py 安装指引)。
"""
from __future__ import annotations

import os
import subprocess

from . import config

_DEFAULTS = ["D:/rc-astro/rc-astro.exe", "C:/Program Files/rc-astro/rc-astro.exe",
             "D:/Program Files/rc-astro/rc-astro.exe",
             os.path.expanduser("~/rc-astro/rc-astro.exe")]


def rcastro_exe() -> str | None:
    """返回配置的 rc-astro CLI 路径(存在才返回);未配置则探测常见默认位置。"""
    try:
        p = config.load_settings().get("rcastro_path", "")
    except Exception:
        p = ""
    if p:
        return p if os.path.exists(p) else None
    for cand in _DEFAULTS:
        if os.path.exists(cand):
            return cand
    return None


def available() -> bool:
    return rcastro_exe() is not None


def _run(sub: str, args: list[str], *, timeout: float = 1800.0) -> str:
    """执行 `rc-astro <sub> <args...>`,返回合并输出(GBK 安全)。未装则抛异常。"""
    exe = rcastro_exe()
    if not exe:
        raise RuntimeError("rc-astro CLI 不可用:在『配置』填 rcastro_path(装法见插件体检/deps.py)")
    r = subprocess.run([exe, sub, *args], capture_output=True, timeout=timeout)
    return (r.stdout + r.stderr).decode("utf-8", errors="replace")


def bxt(input_path: str, output_path: str, *, sharpen_stars: float = 0.5,
        sharpen_nonstellar: float = 0.5, correct_only: bool = False,
        timeout: float = 1800.0, log=print) -> str:
    """**BXT 星点修复/反卷**(BlurXTerminator):修拉线星点 + 锐化非星结构。Siril 无等价,这是拉线星的正解。
    correct_only=True 只矫正星点形状(修拉线)不锐化非星。读写 FITS/XISF。返回 output_path。
    ⚠️ 选项名首次在用户机核对(--sharpen-stars/--sharpen-nonstellar/--correct-only 按官方文档)。"""
    args = ["-i", str(input_path).replace("\\", "/"), "-o", str(output_path).replace("\\", "/")]
    if correct_only:
        args += ["--correct-only"]
    else:
        args += ["--sharpen-stars", f"{sharpen_stars}", "--sharpen-nonstellar", f"{sharpen_nonstellar}"]
    out = _run("bxt", args, timeout=timeout)
    if not os.path.exists(output_path):
        raise RuntimeError(f"rc-astro bxt 未产出 {output_path}(核对 CLI 参数)\n{out[-500:]}")
    log(f"[rcastro] BXT 星点修复{'(仅矫正)' if correct_only else f'(锐星{sharpen_stars}/非星{sharpen_nonstellar})'} → {output_path}")
    return output_path


def sxt(input_path: str, starless_path: str, stars_path: str | None = None,
        *, timeout: float = 1800.0, log=print) -> str:
    """**SXT 去星**(StarXTerminator):分离星点。starless_path=无星图;stars_path 给了则另存星点层。
    ⚠️ 选项名首次核对(--starless/--stars 按官方文档)。返回 starless_path。"""
    args = ["-i", str(input_path).replace("\\", "/"), "-o", str(starless_path).replace("\\", "/")]
    if stars_path:
        args += ["--stars", str(stars_path).replace("\\", "/")]
    out = _run("sxt", args, timeout=timeout)
    if not os.path.exists(starless_path):
        raise RuntimeError(f"rc-astro sxt 未产出 {starless_path}(核对 CLI 参数)\n{out[-500:]}")
    log(f"[rcastro] SXT 去星 → {starless_path}")
    return starless_path


def nxt(input_path: str, output_path: str, *, denoise: float = 0.8, detail: float = 0.15,
        timeout: float = 1800.0, log=print) -> str:
    """**NXT 降噪**(NoiseXTerminator)。denoise=降噪量,detail=细节保留。读写 FITS/XISF。返回 output_path。
    ⚠️ 选项名首次核对(--denoise/--detail 按官方文档)。"""
    args = ["-i", str(input_path).replace("\\", "/"), "-o", str(output_path).replace("\\", "/"),
            "--denoise", f"{denoise}", "--detail", f"{detail}"]
    out = _run("nxt", args, timeout=timeout)
    if not os.path.exists(output_path):
        raise RuntimeError(f"rc-astro nxt 未产出 {output_path}(核对 CLI 参数)\n{out[-500:]}")
    log(f"[rcastro] NXT 降噪(denoise={denoise}) → {output_path}")
    return output_path
