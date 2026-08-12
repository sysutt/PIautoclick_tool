"""GraXpert 命令行集成(梯度校正 / 降噪)。

PI 的 GraXpert 进程在 headless PJSR 下接不通(new GraXpert + appPath 仍空操作),
所以走 GraXpert 的 CLI 子进程直接处理文件(读写 .xisf,本地 AI 模型)。
GraXpert.exe 路径来自 config 的 graxpert_path(产品里让用户填)。

用法:
    from orchestrator import graxpert
    out = graxpert.background_extraction("in.xisf", "out")   # 生成 out.xisf(GraXpert 会自动加 .xisf)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import config


def graxpert_exe() -> str | None:
    """返回配置的 GraXpert.exe 路径(存在才返回)。"""
    try:
        p = config.load_settings().get("graxpert_path", "")
    except Exception:
        p = ""
    if not p:
        # 常见默认位置兜底
        for cand in [r"D:/GraXpert/GraXpert.exe", r"C:/Program Files/GraXpert/GraXpert.exe"]:
            if os.path.exists(cand):
                return cand
        return None
    return p if os.path.exists(p) else None


def available() -> bool:
    return graxpert_exe() is not None


def installed_model_version(kind: str = "bge"):
    """探测本地已装 AI 模型的最高版本号(n.n.n);无则 None。
    kind: "bge"=背景提取(bge-ai-models) / "denoise"=降噪(denoise-ai-models)。
    模型目录:%LOCALAPPDATA%/GraXpert/GraXpert/<kind>-ai-models/<version>/。"""
    import os
    import re
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "GraXpert", "GraXpert", f"{kind}-ai-models")
    try:
        vers = [d for d in os.listdir(base)
                if re.match(r"^\d+\.\d+\.\d+$", d)
                and os.path.isdir(os.path.join(base, d))]
    except OSError:
        return None
    if not vers:
        return None
    return sorted(vers, key=lambda v: [int(x) for x in v.split(".")])[-1]


def installed_bge_version():
    return installed_model_version("bge")


def denoise(
    input_path: str,
    output_noext: str,
    *,
    strength: float = 0.5,   # 0..1 降噪强度
    gpu: bool = False,
    ai_version: str = "latest",
    timeout: float = 1800.0,
) -> str:
    """GraXpert AI 降噪(本地 denoise-ai-models 模型),输出 <output_noext>.xisf,返回该路径。
    零 PI 的 AI 级降噪(cv2/NLM 压不干净暗弱天文噪时用)。读写 XISF/FITS。
    ai_version="latest" → 本地探测 denoise 模型版本(避免联网下载,SSL 不通也能跑)。"""
    exe = graxpert_exe()
    if not exe:
        raise RuntimeError("GraXpert 不可用:在 config 的 graxpert_path 填 GraXpert.exe 路径")
    inp = str(input_path).replace("\\", "/")
    out = str(output_noext).replace("\\", "/")
    for ext in (".xisf", ".fits", ".fit"):
        if out.lower().endswith(ext):
            out = out[:-len(ext)]
    resolved = ai_version
    if not ai_version or ai_version.lower() == "latest":
        resolved = installed_model_version("denoise")
    cmd = [exe, "-cli", "-cmd", "denoising",
           "-strength", str(strength),
           "-gpu", "true" if gpu else "false"]
    if resolved:
        cmd += ["-ai_version", resolved]
    cmd += ["-output", out, inp]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    # GraXpert 的输出格式**跟随输入**(输入 .fit→输出 .fits、.xisf→.xisf),故不能只认 .xisf。
    for ext in (".xisf", ".fits", ".fit"):
        if os.path.exists(out + ext):
            return out + ext
    raise RuntimeError(
        f"GraXpert 降噪未产出(找过 .xisf/.fits/.fit)\ncmd={' '.join(cmd)}\n"
        f"stderr={r.stderr[-800:]}\nstdout={r.stdout[-800:]}"
    )


def background_extraction(
    input_path: str,
    output_noext: str,
    *,
    correction: str = "Subtraction",   # Subtraction / Division
    smoothing: float = 0.3,            # 0..1
    gpu: bool = False,
    ai_version: str = "latest",
    timeout: float = 900.0,
) -> str:
    """对 input_path 跑 GraXpert 背景提取,输出 <output_noext>.xisf,返回该路径。

    注意:GraXpert 的 -output 会自动追加 .xisf,所以 output_noext 不要带扩展名。
    """
    exe = graxpert_exe()
    if not exe:
        raise RuntimeError("GraXpert 不可用:请在 config 的 graxpert_path 填 GraXpert.exe 路径")
    inp = str(input_path).replace("\\", "/")
    out = str(output_noext).replace("\\", "/")
    if out.lower().endswith(".xisf"):
        out = out[:-5]
    # GraXpert 的 -ai_version 只接受 n.n.n,不接受 "latest"。若传 "latest" 则本地探测
    # 已装的 background-extraction 模型版本(bge-ai-models/<n.n.n>);探测不到就干脆
    # 不传 -ai_version,让 GraXpert 用它自己的默认。
    resolved = ai_version
    if not ai_version or ai_version.lower() == "latest":
        resolved = installed_bge_version()
    cmd = [
        exe, "-cli", "-cmd", "background-extraction",
        "-correction", correction,
        "-smoothing", str(smoothing),
        "-gpu", "true" if gpu else "false",
    ]
    if resolved:
        cmd += ["-ai_version", resolved]
    cmd += ["-output", out, inp]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    final = out + ".xisf"
    if not os.path.exists(final):
        raise RuntimeError(
            f"GraXpert 未产出 {final}\ncmd={' '.join(cmd)}\nstderr={r.stderr[-800:]}\nstdout={r.stdout[-800:]}"
        )
    return final
