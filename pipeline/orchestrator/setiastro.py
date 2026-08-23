"""SetiAstroSuite Pro 的 `cosmicclarity` CLI 集成(**免费** AI:降噪/星点修复/锐化/去星)。

SASpro(Seti Astro,GPLv3 免费、在维护)通过 `pip install setiastrosuitepro` 装,自带命令行
`cosmicclarity`(内嵌 Cosmic Clarity + Syqon 引擎)。干净 -i/-o 文件参数、非交互、读写 FITS/XISF、GPU。
作为**免费档的 AI 后端**:rc-astro(收费)不可用时用它,再不行回落 DeepSNR/StarNet2。

**真实 CLI(v1.20.x 实测,2026-08-20 核对)**:`cosmicclarity <sub> -i <in> -o <out> [--gpu/--no-gpu]
[--temp-stretch] [--target-median 0.25] [子选项]`。子命令:denoise/correct/sharpen/both/darkstar/satellite/superres。
**线性数据必须 `--temp-stretch`**(AI 前临时拉伸、后还原;否则极低 ADU 上 AI 效果差)。
路径:config `cosmicclarity_path`;留空则 which / 用户 site Scripts 自动探测。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from . import config


def _cli_cmd() -> list[str] | None:
    """返回调用 cosmicclarity 的命令前缀。优先级:①config 配的 exe(存在)→ [exe];
    ②`cosmicclarity.exe` 控制台脚本(SASpro 常 `pip install --user`,exe 在 %APPDATA%\\Python\\Python3XX\\Scripts;
    遍历 3.12/3.13/3.14 及编排器自身 userbase/exe 目录,**不受编排器 python 版本影响**);③which;
    ④能 import 到 setiastro.saspro.cli 则用 [python, -m, setiastro.saspro.cli]。都无 → None。
    注:SASpro 的 AI 会经 runtime_torch.import_torch 自动桥接到 GPU 运行时 venv,cosmicclarity.exe 直接跑即吃 GPU。"""
    try:
        p = config.load_settings().get("cosmicclarity_path", "")
    except Exception:
        p = ""
    if p and os.path.exists(p):
        return [p]

    exe = "cosmicclarity.exe" if os.name == "nt" else "cosmicclarity"
    bases: list[str] = []
    try:
        import site
        if hasattr(site, "getuserbase"):
            bases.append(site.getuserbase())            # 编排器自身的 --user base
    except Exception:
        pass
    bases.append(os.path.dirname(sys.executable))
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            bases.append(os.path.join(appdata, "Python"))   # --user 安装的 exe 根
    vtags = [f"Python{sys.version_info.major}{sys.version_info.minor}", "Python314", "Python313", "Python312"]
    cands: list[str] = []
    for b in [d for d in bases if d]:
        cands += [os.path.join(b, "Scripts", exe), os.path.join(b, "bin", "cosmicclarity")]
        for vt in vtags:
            cands.append(os.path.join(b, vt, "Scripts", exe))   # …\Python\Python314\Scripts\cosmicclarity.exe
    if os.name == "nt":
        for vt in vtags:
            cands.append(os.path.join("C:\\", vt, "Scripts", exe))
    seen = set()
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            if os.path.exists(c):
                return [c]

    w = shutil.which("cosmicclarity")
    if w:
        return [w]
    try:
        import importlib.util
        if importlib.util.find_spec("setiastro.saspro.cli") is not None:
            return [sys.executable, "-m", "setiastro.saspro.cli"]
    except Exception:
        pass
    return None


def cosmicclarity_exe() -> str | None:
    """兼容旧名:返回命令前缀的可执行部分(exe 路径或 python)。"""
    c = _cli_cmd()
    return c[0] if c else None


def available() -> bool:
    return _cli_cmd() is not None


def _run(sub: str, input_path: str, output_path: str, extra: list[str], *,
         temp_stretch: bool = True, target_median: float = 0.25, gpu: bool = True,
         timeout: float = 1800.0) -> str:
    """执行 `cosmicclarity <sub> -i <in> -o <out> [--temp-stretch --target-median] [--gpu/--no-gpu] <extra>`。
    temp_stretch=True 用于**线性数据**(AI 前临时拉伸后还原)。返回合并输出(GBK 安全)。未装则抛异常。"""
    pre = _cli_cmd()
    if not pre:
        raise RuntimeError("cosmicclarity 不可用:pip install setiastrosuitepro,或在『配置』填 cosmicclarity_path")
    inp, outp = str(input_path).replace("\\", "/"), str(output_path).replace("\\", "/")

    def _once(use_gpu: bool) -> str:
        cmd = pre + [sub, "-i", inp, "-o", outp, "--gpu" if use_gpu else "--no-gpu"]
        if temp_stretch:
            cmd += ["--temp-stretch", "--target-median", f"{target_median}"]
        cmd += list(extra)
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return (r.stdout + r.stderr).decode("utf-8", errors="replace")

    def _resolve() -> None:
        """cosmicclarity 会规范化输出扩展名(实测 .tiff→.tif),把实际产物归位到请求的 outp,
        否则调用方 os.path.exists(output_path) 误判未产出、且 GPU 成功也会被当失败回落 CPU。"""
        if os.path.exists(outp):
            return
        stem = os.path.splitext(outp)[0]
        for ext in (".tif", ".tiff", ".fits", ".fit", ".png", ".xisf"):
            cand = stem + ext
            if os.path.exists(cand) and os.path.abspath(cand) != os.path.abspath(outp):
                try:
                    os.replace(cand, outp)                 # 同目录改名(RUN_DIR 无 rename 拦截)
                except Exception:
                    try:
                        shutil.copyfile(cand, outp)        # 兜底:纯写入,绕开任何 rename 拦截
                    except Exception:
                        pass
                return

    out = _once(gpu)
    _resolve()
    # **GPU 运行时未装 → 自动回落 CPU**(先归位扩展名再判断,避免把"扩展名不符"误当 GPU 失败)
    if gpu and not os.path.exists(outp) and "gpu acceleration runtime is not installed" in out.lower():
        out = _once(False)
        _resolve()
    return out


def denoise(input_path: str, output_path: str, *, luma: float = 0.85, color: float | None = None,
            mode: str = "full", temp_stretch: bool = True, timeout: float = 1800.0, log=print) -> str:
    """**降噪**(Cosmic Clarity 引擎)。luma/color=亮度/色度降噪强度[0,1];mode∈{full,luminance}。
    **temp_stretch**:线性数据 True(AI 前临时拉伸后还原);**已拉伸的合成图传 False**(避免二次拉伸位移黑点)。返回 output_path。"""
    extra = ["--denoise-luma", f"{luma}", "--denoise-mode", mode]
    if color is not None:
        extra += ["--denoise-color", f"{color}"]
    out = _run("denoise", input_path, output_path, extra, temp_stretch=temp_stretch, timeout=timeout)
    if not os.path.exists(output_path):
        raise RuntimeError(f"cosmicclarity denoise 未产出 {output_path}\n{out[-400:]}")
    log(f"[setiastro] cosmicclarity 降噪(luma={luma},{mode}) → {output_path}")
    return output_path


def correct(input_path: str, output_path: str, *, timeout: float = 1800.0, log=print) -> str:
    """**纯星点修复**(correct=仅像差矫正、不锐化,最安全)。免费的 BXT correct-only 等价。返回 output_path。"""
    out = _run("correct", input_path, output_path, [], timeout=timeout)
    if not os.path.exists(output_path):
        raise RuntimeError(f"cosmicclarity correct 未产出 {output_path}\n{out[-400:]}")
    log(f"[setiastro] cosmicclarity 星点修复(correct 仅矫正) → {output_path}")
    return output_path


def sharpen(input_path: str, output_path: str, *, mode: str = "Both", stellar_amount: float = 0.9,
            nonstellar_amount: float = 0.9, stellar_correct_mode: str = "correct_sharpen",
            timeout: float = 1800.0, log=print) -> str:
    """**锐化/反卷**。mode∈{Both,Stellar Only,Non-Stellar Only};stellar_correct_mode∈
    {sharpen_only,correct_only,correct_sharpen}(correct_sharpen=先矫正星形再锐化)。返回 output_path。"""
    extra = ["--sharpening-mode", mode, "--stellar-amount", f"{stellar_amount}",
             "--nonstellar-amount", f"{nonstellar_amount}", "--stellar-correct-mode", stellar_correct_mode]
    out = _run("sharpen", input_path, output_path, extra, timeout=timeout)
    if not os.path.exists(output_path):
        raise RuntimeError(f"cosmicclarity sharpen 未产出 {output_path}\n{out[-400:]}")
    log(f"[setiastro] cosmicclarity 锐化({mode}/{stellar_correct_mode}) → {output_path}")
    return output_path


def darkstar(input_path: str, starless_path: str, *, mode: str = "unscreen",
             path: str = "hybrid_luma_color", temp_stretch: bool = True,
             timeout: float = 1800.0, log=print) -> str:
    """**去星**(DarkStar)。mode∈{unscreen,additive};path∈{mono_per_channel,hybrid_luma_color,color_only}。
    **temp_stretch**:线性数据 True;**已拉伸图传 False**。输出 starless。返回 starless_path。"""
    extra = ["--star-removal-mode", mode, "--processing-path", path]
    out = _run("darkstar", input_path, starless_path, extra, temp_stretch=temp_stretch, timeout=timeout)
    if not os.path.exists(starless_path):
        raise RuntimeError(f"cosmicclarity darkstar 未产出 {starless_path}\n{out[-400:]}")
    log(f"[setiastro] cosmicclarity 去星(DarkStar {mode}) → {starless_path}")
    return starless_path
