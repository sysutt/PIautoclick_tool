"""无 PI OSC 叠加引擎(zero-PixInsight):原始亮场(+可选暗/平/偏)→ Siril 校准 → 去马赛克 →
星点配准 → 整合 → master。全程不碰 PixInsight,补齐"零 PI 完整链路"里叠加这块拼图。

与 rgb_engine / hoo_engine / sho_engine 并列(它们做后期,本模块做前端叠加)。见 [[siril-stacking]]。

**踩通的坑(固化自 M51 S30 Pro 161 帧真机验证,2026-08-15)**:
1. **Seestar `_sub` 混 .jpg 预览/缩略图**(161 fit + 322 jpg)→ Siril convert 会全叠进去 → **只挑 .fit 暂存**。
2. **Siril convert 序列名带尾下划线** `light_`(不是 `light`)→ 后续 register/stack 必须用 `light_`。
3. **register 复用 `cache/*.lst` 里的旧星表**(换目标/重试会用错) → 配准前**清 cache**。
4. **线性帧星点弱**,默认 findstar 只找到 2 颗星 → **`setfindstar -sigma=0.5`** 降阈值才够配准。
5. **Siril 在中文 Windows 输出 GBK**,按 utf-8 解码会乱码 + 假 OSError(stdout TextIOWrapper)→ 自动 utf-8/gbk 双解码。
6. **大帧数彩色栈慢**(161×3通道×32位≈16GB):默认 Siril 内存上限低 → **`setmem` 提上限**单遍内存整合。
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time

from . import config, siril

_LIGHT_EXTS = (".fit", ".fits", ".fts")


def _decode(b: bytes) -> str:
    """Siril 输出:先试 utf-8(非中文环境),失败退 gbk(中文 Windows 的 CP936)。"""
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def _tail(out: str, n: int = 12) -> str:
    return "\n".join(ln for ln in out.splitlines() if "EXIF" not in ln)[-1200:] if out else ""


def _run_siril(cmds: list[str], *, timeout: float, log, tag: str,
               mem_ratio: float | None = None, bit16: bool = False) -> str:
    """跑 Siril 脚本(自建,GBK 感知),返回解码后的输出。成败由调用方查产出文件(Siril 退出常打伪错误)。
    bit16=True 前置 `set16bits`(register 默认升 32 位浮点→帧翻倍/IO 翻倍;16 位减半、叠加质量无损)。"""
    exe = siril.siril_exe()
    if not exe:
        raise RuntimeError("Siril 不可用:未找到 siril-cli.exe(在配置里填 siril_path)")
    body = (["requires 1.2.0"]
            + (["set16bits"] if bit16 else [])
            + ([f"setmem {mem_ratio}"] if mem_ratio else [])
            + list(cmds))
    sp = os.path.join(str(config.RUN_DIR), f"_stkeng_{tag}.ssf").replace("\\", "/")
    with open(sp, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    r = subprocess.run([exe, "-s", sp], capture_output=True, timeout=timeout)
    return _decode(r.stdout) + "\n" + _decode(r.stderr)


def _stage_lights(light_dir: str, stage_dir: str, log) -> int:
    """只挑 .fit/.fits 光子帧(**排除 Seestar 的 .jpg 预览/缩略图、failed_ 废帧**)复制到干净暂存目录。"""
    subs: list[str] = []
    for e in _LIGHT_EXTS:
        subs += glob.glob(os.path.join(light_dir, "*" + e))
    subs = sorted(x for x in subs if not os.path.basename(x).lower().startswith("failed"))
    if not subs:
        raise RuntimeError(f"目录无 .fit 光子帧:{light_dir}")
    os.makedirs(stage_dir, exist_ok=True)
    for i, f in enumerate(subs):
        shutil.copy2(f, os.path.join(stage_dir, f"sub_{i:05d}.fit"))
    log(f"[stack] 暂存 {len(subs)} 帧光子帧(排除 .jpg 预览/failed_ 废帧)")
    return len(subs)


def make_master(frame_dir: str, out_noext: str, *, method: str = "med",
                mem_ratio: float = 0.9, timeout: float = 3600.0, log=print) -> str:
    """原始定标帧目录(暗/平/偏)→ master(convert + stack)。method: med(暗/偏)/ rej(平)。返回 <out>.fit。"""
    R = str(config.RUN_DIR)
    work = os.path.join(R, "_cal_" + os.path.basename(out_noext)).replace("\\", "/")
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    n = _stage_lights(frame_dir, f"{work}/stage", log)
    out = str(out_noext).replace("\\", "/").rsplit(".", 1)[0] if str(out_noext).lower().endswith((".fit", ".fits")) else str(out_noext).replace("\\", "/")
    stk = f"stack cal_ {method} -nonorm -out={out}" if method == "med" else f"stack cal_ rej 3 3 -nonorm -out={out}"
    out_log = _run_siril([f'cd "{work}/stage"', f"convert cal -out={work}",
                          f'cd "{work}"', stk], timeout=timeout, log=log, tag="cal", mem_ratio=mem_ratio)
    if not glob.glob(f"{out}.fit*"):
        raise RuntimeError(f"master 定标帧整合失败({n}帧):" + _tail(out_log))
    log(f"[stack] master 定标帧({method},{n}帧)→ {out}.fit")
    return out + ".fit"


def stack_osc(light_dir: str, out_noext: str, *, dark: str | None = None, flat: str | None = None,
              bias: str | None = None, debayer: bool = True, findstar_sigma: float = 0.5,
              sig_low: float = 3.0, sig_high: float = 3.0, norm: str = "addscale",
              bit16: bool = True, mem_ratio: float = 0.9, timeout: float = 7200.0, log=print) -> str:
    """**OSC 原始亮场 → master(零 PixInsight)**。
    light_dir=原始亮场目录(自动挑 .fit、排除 .jpg 预览);dark/flat/bias=master 定标帧文件(可选,
    Seestar 一体机无定标帧留空即可;Dwarf 传 master 暗场)。返回 <out>.fit。

    流程:挑 .fit 暂存 → convert(去马赛克)→ 可选 calibrate → 清 cache + setfindstar 配准 → setmem 整合。"""
    R = str(config.RUN_DIR)
    work = os.path.join(R, "_stack_osc").replace("\\", "/")
    stage, proc = f"{work}/stage", f"{work}/proc"
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(proc, exist_ok=True)
    t0 = time.time()
    n = _stage_lights(light_dir, stage, log)
    calibrated = bool(dark or flat or bias)
    out = str(out_noext).replace("\\", "/")
    if out.lower().endswith((".fit", ".fits")):
        out = out.rsplit(".", 1)[0]

    # ① convert(去马赛克;若后面 calibrate 则由 calibrate 去马赛克)
    conv = "convert light -out=" + proc + ("" if calibrated else (" -debayer" if debayer else ""))
    o = _run_siril([f'cd "{stage}"', conv], timeout=timeout, log=log, tag="conv", bit16=bit16)
    if not glob.glob(f"{proc}/light_*.fit"):
        raise RuntimeError("convert 失败(无输出帧):" + _tail(o))
    seq = "light_"
    log(f"[stack] convert 去马赛克完成 {len(glob.glob(f'{proc}/light_*.fit'))} 帧")

    # ②(可选)calibrate 校准 + 去马赛克
    if calibrated:
        # 【坑】-dark=/-flat=/-bias= **不能带引号**(同 -out=:Siril 会把引号当进路径→找不到+追加扩展名)。
        #   master 定标帧存在 _run(无空格),不加引号安全。
        cal = "calibrate light_"
        if dark:
            cal += f" -dark={dark}"
        if flat:
            cal += f" -flat={flat}"
        if bias:
            cal += f" -bias={bias}"
        cal += " -cfa -equalize_cfa" + (" -debayer" if debayer else "")
        o = _run_siril([f'cd "{proc}"', cal], timeout=timeout, log=log, tag="cal", bit16=bit16)
        pp = glob.glob(f"{proc}/pp_light_*.fit")
        if not pp:
            raise RuntimeError("校准失败(无 pp_ 帧):" + _tail(o))
        seq = "pp_light_"
        log(f"[stack] 校准+去马赛克完成 {len(pp)} 帧")

    # ③ 配准:**清 cache(旧星表)+ 降星点阈值(线性帧星弱)**
    if os.path.exists(f"{proc}/cache"):
        shutil.rmtree(f"{proc}/cache", ignore_errors=True)
    for f in glob.glob(f"{proc}/*.lst"):
        os.remove(f)
    o = _run_siril([f'cd "{proc}"', f"setfindstar -sigma={findstar_sigma} -roundness=0.4",
                    f"register {seq}"], timeout=timeout, log=log, tag="reg", bit16=bit16)
    rseq = "r_" + seq
    if not glob.glob(f"{proc}/{rseq}.seq"):
        raise RuntimeError("配准失败(星点不足?可再降 findstar_sigma):" + _tail(o))
    log(f"[stack] 配准完成(setfindstar sigma={findstar_sigma})")

    # ④ 整合:**setmem 提内存上限**(大帧数彩色栈,单遍内存整合免反复读盘)
    o = _run_siril([f'cd "{proc}"',
                    f"stack {rseq} rej {sig_low} {sig_high} -norm={norm} -output_norm -out={out}"],
                   timeout=timeout, log=log, tag="stk", mem_ratio=mem_ratio, bit16=bit16)
    if not glob.glob(f"{out}.fit*"):
        raise RuntimeError("整合失败:" + _tail(o))
    log(f"[stack] 整合完成 {n} 帧 → {out}.fit(全程零 PixInsight,用时 {int(time.time()-t0)}s)")
    return out + ".fit"
