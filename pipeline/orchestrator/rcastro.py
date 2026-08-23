"""rc-astro CLI 集成(BXT 星点修复/反卷 · SXT 去星 · NXT 降噪)。

rc-astro = Russell Croman 的 BlurXTerminator/StarXTerminator/NoiseXTerminator **独立命令行版**:
一个 CLI 全包、跨平台、GPU 加速、读写 FITS+XISF+TIFF,持牌免费。装法/激活见 deps.py EXTERNAL(app 内指引)。
用它补 Siril 无法做的**拉线星点修复**(BXT),以及专业去星(SXT)/降噪(NXT)。

**真实 CLI(v2.6.x 实测,2026-08-20 核对)**:
  rc-astro [--no-banner] [--host <id>] <sub> <input...> -o <out> [--overwrite] [--depth 32F] [--device auto] [sub选项]
  - 输入是**位置参数**(不是 -i);-o/--output 给文件或目录;--overwrite 覆盖;--depth 32F 保线性 32 位精度。
  - 每个产品需激活:`rc-astro license --activate <bxt|sxt|nxt>`(账户操作,用户自行执行)。
rcastro_path 来自 config(产品里让用户填,见 deps.py 安装指引)。
"""
from __future__ import annotations

import os
import subprocess

from . import config

_DEFAULTS = ["D:/Program Files/RC-Astro/CLI/rc-astro.exe", "C:/Program Files/RC-Astro/CLI/rc-astro.exe",
             "D:/rc-astro/rc-astro.exe", "C:/Program Files/rc-astro/rc-astro.exe",
             os.path.expanduser("~/rc-astro/rc-astro.exe")]
_HOST = "TTAstroPiLot"


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


def enabled() -> bool:
    """**路由用**:已安装 且 未被『仅免费』开关禁用(config ai_backend.allow_paid=False 则强制免费路线)。
    deps 面板展示仍用 available()(反映是否真的装了),二者分开。"""
    if not available():
        return False
    try:
        return bool(config.load_settings().get("ai_backend", {}).get("allow_paid", True))
    except Exception:
        return True


def _run(sub: str, input_path: str, output_path: str, extra: list[str], *,
         depth: str = "32F", device: str = "auto", timeout: float = 1800.0) -> str:
    """执行 `rc-astro <sub> <input> -o <output> --overwrite --depth <depth> --device <device> <extra>`。
    返回合并输出(GBK 安全)。未装则抛异常。"""
    exe = rcastro_exe()
    if not exe:
        raise RuntimeError("rc-astro CLI 不可用:在『配置』填 rcastro_path(装法见插件体检/deps.py)")
    cmd = [exe, "--no-banner", "--host", _HOST, sub,
           str(input_path).replace("\\", "/"), "-o", str(output_path).replace("\\", "/"),
           "--overwrite", "--depth", depth, "--device", device] + list(extra)
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return (r.stdout + r.stderr).decode("utf-8", errors="replace")


def bxt(input_path: str, output_path: str, *, sharpen_stars: float = 0.5,
        sharpen_nonstellar: float = 0.5, correct_only: bool = False, adjust_star_halos: float = 0.0,
        extra: list[str] | None = None, depth: str = "32F", timeout: float = 1800.0, log=print) -> str:
    """**BXT 星点修复/反卷**(BlurXTerminator):修拉线/畸变星 + 锐化。Siril 无等价,拉线星的正解。
    **correct_only=True**:只矫正星形 PSF 像差(修拉线/畸变)不锐化——纯"星点修复"档,最安全。
    sharpen_stars[0,0.7]/sharpen_nonstellar[0,1];adjust_star_halos[-0.5,0.5]。需先激活 bxt。返回 output_path。
    实测线性 master:星点等效直径 −38%、亮星解析数翻倍。"""
    if correct_only:
        args = ["--correct-only"]
    else:
        args = ["--sharpen-stars", f"{sharpen_stars}", "--sharpen-nonstellar", f"{sharpen_nonstellar}"]
        if adjust_star_halos:
            args += ["--adjust-star-halos", f"{adjust_star_halos}"]
    args += (extra or [])
    out = _run("bxt", input_path, output_path, args, depth=depth, timeout=timeout)
    if not os.path.exists(output_path):
        raise RuntimeError(f"rc-astro bxt 未产出 {output_path}(未激活?license --activate bxt)\n{out[-500:]}")
    log(f"[rcastro] BXT {'仅矫正星形' if correct_only else f'星点修复(锐星{sharpen_stars}/非星{sharpen_nonstellar})'} → {output_path}")
    return output_path


def sxt(input_path: str, starless_path: str, *, depth: str = "32F",
        timeout: float = 1800.0, log=print) -> str:
    """**SXT 去星**(StarXTerminator):输出无星图(starless)。星点层建议调用方用 原图−starless 自算(确定性、
    文件名可控),不走 --difference。返回 starless_path。"""
    out = _run("sxt", input_path, starless_path, [], depth=depth, timeout=timeout)
    if not os.path.exists(starless_path):
        raise RuntimeError(f"rc-astro sxt 未产出 {starless_path}\n{out[-500:]}")
    log(f"[rcastro] SXT 去星 → {starless_path}")
    return starless_path


def nxt(input_path: str, output_path: str, *, denoise: float = 0.9, denoise_color: float | None = None,
        iterations: float | None = None, depth: str = "32F", timeout: float = 1800.0, log=print) -> str:
    """**NXT 降噪**(NoiseXTerminator):denoise=总降噪量[0,1];denoise_color 单独控色度;iterations 迭代数[1,5]。
    读写 FITS/XISF/TIFF。返回 output_path。"""
    args = ["--denoise", f"{denoise}"]
    if denoise_color is not None:
        args += ["--denoise-color", f"{denoise_color}"]
    if iterations is not None:
        args += ["--iterations", f"{iterations}"]
    out = _run("nxt", input_path, output_path, args, depth=depth, timeout=timeout)
    if not os.path.exists(output_path):
        raise RuntimeError(f"rc-astro nxt 未产出 {output_path}\n{out[-500:]}")
    log(f"[rcastro] NXT 降噪(denoise={denoise}) → {output_path}")
    return output_path
