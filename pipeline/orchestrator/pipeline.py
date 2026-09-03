"""P1:固定参数管线串接。

把若干处理步骤(op)串成一条流水线,每步的输出图作为下一步的输入,
逐步回收指标 + 预览。P1 不含闭环反馈(参数固定),只验证端到端出片。

用法(pipeline/ 目录下):
    python -m orchestrator.pipeline --input "D:/astro/master.xisf"
    python -m orchestrator.pipeline --input "..." --no-crop
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path          # 模块级:run_rgb 等处用 Path 却没导入过 → NameError 被 except 吞掉(干净星点轨曾因此静默失效)
from typing import Any, Callable

from . import config, protocol

# 中止标志:GUI 中止按钮置 True;各流程 step() 在提交每步前检查,置位则抛出中止。
CANCEL = False

# ── HT 拉伸背景峰值标准位(量化标准,用户 2026-08 定,替代旧 1/8)────────────────────
# autoStretch(computeStretchH)把背景中位数钉到 targetBackground = 直方图"亮度峰值"落点。
# 旧策略峰值在 1/8(0.125);实战教程对比后,更合理的位置是 **3/16(0.1875)**——1/8 与 1/4(PI 默认 STF 0.25)之间。
# 各主拉伸统一用 PEAK_BG;干净背景模式(星团/纯亮场)按比例更暗(见 run_rgb)。改这一个数即可全局调峰值位。
PEAK_BG = 0.1875   # 3/16

# 播主 Henry 的 SHO 窄带调色曲线(从其 .xpsm 忠实拆出,8 条通道一次成型;AkimaSubsplines=curves 默认插值)。
# R 抬红(暖金)/ G 压绿(去铸)/ B 抬蓝(OIII 青)/ K 提亮提对比 / CIE a* 压极端红品红 /
# CIE b* S形拉开蓝-黄 / H 轻旋色相 / S 中饱和区提饱和。作用于**非线性**(拉伸后)图,配色相蒙版更佳。
# 端点 (0,0)/(1,1) 由 job-runner 的 curves op 自动补齐。用 grade_curve="henry_sho" 启用。
HENRY_SHO_CURVE = {
    "pointsR":  [[0.07368, 0.07632], [0.41842, 0.50263], [0.75263, 0.85526]],
    "pointsG":  [[0.07895, 0.07895], [0.31316, 0.26316], [0.53158, 0.48421]],
    "pointsB":  [[0.07105, 0.07368], [0.50000, 0.59474]],
    "pointsK":  [[0.23947, 0.22368], [0.47632, 0.53421], [0.72632, 0.79211]],
    "pointsLa": [[0.22105, 0.21053], [0.50263, 0.50263], [0.79211, 0.68421]],
    "pointsLb": [[0.29211, 0.23421], [0.50263, 0.50263], [0.71316, 0.80000]],
    "pointsH":  [[0.48421, 0.46579], [0.76579, 0.73421]],
    "pointsS":  [[0.11579, 0.10526], [0.49211, 0.58421]],
}


def _scale_wcs_for(wcs_path: str, W: int, H: int) -> dict:
    """把 nova wcs.fits(它内部把图降采样后解,IMAGEW/H 是降采版尺寸)线性缩放到全分辨率
    母版网格(W×H),返回 applywcs op 用的 WCS 关键字字典(仅线性 TAN,丢 SIP;后续 ImageSolver
    以此为初值精修出带畸变的原生解)。"""
    import re
    with open(wcs_path, "rb") as f:
        txt = f.read().decode("latin1")
    cards = [txt[i:i + 80] for i in range(0, len(txt), 80)]
    d = {}
    for c in cards:
        if c.startswith("END"):
            break
        m = re.match(r"^([A-Z0-9_]+)\s*=\s*('?[^/']*'?)", c)
        if m:
            d[m.group(1)] = m.group(2).strip().strip("'").strip()
    imw, imh = float(d["IMAGEW"]), float(d["IMAGEH"])
    sx, sy = W / imw, H / imh

    def fn(k):
        return float(d[k])
    return {
        "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN", "CUNIT1": "deg", "CUNIT2": "deg",
        "RADESYS": "ICRS", "EQUINOX": 2000.0,
        "CRVAL1": fn("CRVAL1"), "CRVAL2": fn("CRVAL2"),
        "CRPIX1": round(fn("CRPIX1") * sx, 4), "CRPIX2": round(fn("CRPIX2") * sy, 4),
        "CD1_1": fn("CD1_1") / sx, "CD1_2": fn("CD1_2") / sy,
        "CD2_1": fn("CD2_1") / sx, "CD2_2": fn("CD2_2") / sy,
        "XPIXSZ": 2.0, "YPIXSZ": 2.0,
    }


def request_cancel():
    global CANCEL
    CANCEL = True


def _ckc():
    if CANCEL:
        raise RuntimeError("已中止")


def run_wbpp_stack(raw: dict, timeout: float = 3600.0) -> str:
    """原始素材 → 自定义滤镜法 WBPP(每晚 dNrgb 标签打在光+平上,校准+去马+对齐,
    停在 registration)。独占实例运行 wbpp_custom/WBPP.js,轮询 registered 完成后重启
    job-runner,返回 registered 目录路径(供 run_integrate 递归整合)。

    raw = {"nights":[{"light","flat","tag"}], "dark","bias","out_base","target"}
    """
    import os
    import glob as _glob
    import subprocess
    import time as _time
    from pathlib import Path

    exe = config.pixinsight_exe()
    if not exe:
        raise RuntimeError("未找到 PixInsight,请在配置里设置路径")
    wbpp = config.PIPELINE_DIR / "wbpp_custom" / "WBPP.js"
    if not wbpp.exists():
        raise RuntimeError("缺少 wbpp_custom/WBPP.js(自定义滤镜法 WBPP 副本)")
    out = (raw["out_base"].rstrip("/") + "/" + raw["target"]).replace("\\", "/")
    os.makedirs(out, exist_ok=True)

    def _fits(d):  # 目录内 .fit/.fits 数量(不含缩略图,自定义 WBPP 只扫 fit-like)
        d = d.replace("\\", "/")
        return len(_glob.glob(d + "/*.fit")) + len(_glob.glob(d + "/*.fits")) + len(_glob.glob(d + "/*.xisf"))

    # 智能望远镜常缺校准场(Seestar 只有亮场;Dwarf 只有亮+暗)→ 空目录一律不追加,
    # 避免出现畸形的 "dir=" 参数;WBPP 缺哪类主帧就跳过对应校准步骤。
    args = ["automationMode=true"]
    exp_lights = 0
    if raw.get("lights"):
        # 【#1 黑白 per-filter 模式】亮场/平场 **不打 dN 标签** → WBPP 读真实 FILTER 头天然按滤镜分组;
        #   平场↔亮场按 FILTER 配、暗场↔亮场按曝光配、偏置全局。lights/flats/darks 均为目录列表。
        for ld in raw["lights"]:
            args.append("dir=" + ld.replace("\\", "/"))
            exp_lights += _fits(ld)
        for fd in (raw.get("flats") or []):
            args.append("dir=" + fd.replace("\\", "/"))
        for dd in (raw.get("darks") or []):
            args.append("dir=" + dd.replace("\\", "/"))
        if raw.get("bias"):
            args.append("dir=" + raw["bias"].replace("\\", "/"))
    else:
        # 原 nights 模式(OSC/智能望远镜):dN 自定义滤镜标签(每晚一组,覆盖 FILTER)
        for n in raw["nights"]:
            args.append("dir=%s|%s" % (n["light"].replace("\\", "/"), n["tag"]))
            if n.get("flat"):
                args.append("dir=%s|%s" % (n["flat"].replace("\\", "/"), n["tag"]))
            exp_lights += _fits(n["light"])
        if raw.get("dark"):
            args.append("dir=" + raw["dark"].replace("\\", "/"))
        if raw.get("bias"):
            args.append("dir=" + raw["bias"].replace("\\", "/"))
    args.append("outputDirectory=" + out)
    # autoIntegrationMode=false:关掉 WBPP「POST 组 ≥150 帧自动切快速整合」。该模式下每组只测前 5 帧
    # (日志出现 "SubframeSelector: 5 succeeded"),且 Pipeline 不给快速整合组排 StarAlignment →
    # registered/ 全空,大帧数栈(如两晚 252 张)必然轮询超时。强制所有组走常规注册路径,任意帧数都出 *_r.xisf。
    args += ["integrate=false", "platesolve=false", "debayerOutputMethod=0",
             "autoIntegrationMode=false"]
    argstr = ",".join(args)

    # WBPP 需独占实例:停 job-runner + 杀 PI
    _ckc()
    try:
        config.STOP_FILE.write_text("stop", encoding="utf-8")
    except OSError:
        pass
    _time.sleep(1.5)
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/IM", "PixInsight.exe", "/F"], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", "PixInsight"], capture_output=True)
    _time.sleep(3)
    try:
        if config.HEARTBEAT.exists():
            config.HEARTBEAT.unlink()
    except OSError:
        pass

    # 起弹窗守卫(WBPP 可能弹框),再启动自定义 WBPP
    try:
        subprocess.Popen([sys.executable, "-m", "orchestrator.popup_guard"],
                         cwd=str(config.PIPELINE_DIR),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    _mono = bool(raw.get("lights"))
    _has_dark = bool(raw.get("darks")) if _mono else bool(raw.get("dark"))
    _has_flat = bool(raw.get("flats")) if _mono else any(n.get("flat") for n in raw["nights"])
    _cal = [t for t, ok in (("暗场", _has_dark), ("偏置", raw.get("bias")), ("平场", _has_flat)) if ok] or ["无校准场"]
    _ngrp = len(raw["lights"]) if _mono else len(raw["nights"])
    print("== 自定义滤镜法 WBPP[%s]:%s %d 组, 预计 %d 张亮场, 校准=%s → %s ==" %
          (raw.get("device", "osc"), "per-filter" if _mono else "分晚", _ngrp, exp_lights, "/".join(_cal), out))
    subprocess.Popen('"%s" -n "-r=%s,%s"' % (exe, str(wbpp), argstr), shell=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 轮询 registered:达到预计张数,或计数稳定多轮=完成
    regdir = out + "/registered"
    deadline = _time.time() + timeout
    last, stable = -1, 0
    while _time.time() < deadline:
        _ckc()
        cnt = len(_glob.glob(regdir + "/**/*_r.xisf", recursive=True))
        if exp_lights and cnt >= exp_lights:
            print("  registered 完成:%d/%d" % (cnt, exp_lights))
            break
        stable = stable + 1 if (cnt == last and cnt > 0) else 0
        last = cnt
        if stable >= 5 and cnt > 0:   # 连续多轮不变=完成
            print("  registered 稳定:%d 张" % cnt)
            break
        _time.sleep(20)
    else:
        raise RuntimeError("WBPP 叠加超时(%.0fs);registered=%d" % (timeout, last))

    # 杀 WBPP 的 PI,停守卫,重启 job-runner 供后续整合/后期
    try:
        (config.RUN_DIR / "STOP_GUARD").write_text("stop", encoding="utf-8")
    except OSError:
        pass
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/IM", "PixInsight.exe", "/F"], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", "PixInsight"], capture_output=True)
    _time.sleep(3)
    for f in ("STOP", "STOP_GUARD", "runner.heartbeat"):
        try:
            p = config.RUN_DIR / f
            if p.exists():
                p.unlink()
        except OSError:
            pass
    subprocess.Popen([exe, "-n", "-r=" + str(config.JOB_RUNNER_JS)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):   # 等 runner 上线(冷启约 18-22s)
        if protocol.runner_alive():
            break
        _time.sleep(2)
    return regdir


def run_wbpp_stack_pernight(raw: dict, timeout: float = 3600.0) -> str:
    """智能望远镜(Dwarf 等非制冷)**多晚**原始素材:**逐晚**用各自温度匹配的暗场分别跑 WBPP,再把各晚
    registered 帧汇总到一个目录供统一整合;返回该汇总目录(与 run_wbpp_stack 一样是 registered 目录)。

    为什么逐晚跑:WBPP 暗场匹配按 exposure/binning/CCD-TEMP(BPP-StackEngine.findGroup),而 **Dwarf 温度存在
    `DET-TEMP`、WBPP 读不到** → 一次任务对同曝光暗场只合成**一个 master dark**、套给所有晚(温度错配、残留
    暗电流/辉光)。故对每晚单独跑 WBPP、显式喂该晚正确暗场,不依赖 WBPP 自身匹配。= WBPP 侧对齐无 PI 的
    stack_osc_pernight(用户 2026-09-03 选此方案)。需 raw['calib_library'] + 多晚;单晚/无库自动退回单次。
    """
    import os
    import glob as _glob
    import shutil
    nights = [n for n in (raw.get("nights") or []) if n.get("light")]
    lib = (raw.get("calib_library") or "").strip().replace("\\", "/")
    if len(nights) <= 1 or not lib or not os.path.isdir(lib):
        return run_wbpp_stack(raw, timeout)          # 单晚/无库 → 单次 WBPP 即可

    from . import calib_match
    pn = calib_match.auto_calib_pernight(
        lib, [n["light"].replace("\\", "/") for n in nights], kinds=("dark",), log=print)

    out_base = raw["out_base"].rstrip("/").replace("\\", "/")
    target = raw["target"]
    combined = "%s/%s/registered" % (out_base, target)
    os.makedirs(combined, exist_ok=True)
    for _old in _glob.glob(combined + "/*.xisf"):   # 清掉上次残留,防旧帧混入本次整合
        try: os.remove(_old)
        except OSError: pass
    print("== 逐晚 WBPP(%d 晚):各晚各自温度暗场分别跑,再汇总整合(WBPP 读不到 Dwarf 的 DET-TEMP,单次只出一个 dark master)==" % len(nights))
    total = 0
    for i, n in enumerate(nights):
        nd = (pn[i]["dark"]["dir"] if (i < len(pn) and pn[i].get("dark")) else None) \
            or ((raw.get("dark") or "").strip().replace("\\", "/") or None)
        sub = {"device": raw.get("device", "osc"),
               "out_base": out_base, "target": "%s__n%d" % (target, i + 1),
               "nights": [{"light": n["light"].replace("\\", "/"),
                           "flat": ((n.get("flat") or "").strip().replace("\\", "/") or None),
                           "tag": n.get("tag") or ("d%d" % (i + 1))}],
               "dark": nd, "bias": ((raw.get("bias") or "").strip().replace("\\", "/") or None)}
        print("== 逐晚 WBPP:第 %d/%d 晚 → 暗场=%s ==" %
              (i + 1, len(nights), os.path.basename(nd) if nd else "(无·退回无暗场校准)"))
        reg = run_wbpp_stack(sub, timeout)
        moved = 0
        for f in _glob.glob(reg + "/**/*_r.xisf", recursive=True):
            dst = "%s/n%d_%s" % (combined, i + 1, os.path.basename(f))   # 前缀 nN 防跨晚重名
            try:
                os.replace(f, dst)                   # 同盘瞬时移动(registered 与汇总同在 out_base)
            except OSError:
                shutil.copy2(f, dst)                 # 跨盘退回复制
            moved += 1
        total += moved
        print("   第 %d 晚 registered %d 帧 → 汇总目录" % (i + 1, moved))
    if total == 0:
        raise RuntimeError("逐晚 WBPP:各晚均无 registered 帧产出(检查亮场/暗场/超时)")
    print("== 逐晚 WBPP 完成:%d 晚共 %d 帧 → %s(交统一整合)==" % (len(nights), total, combined))
    return combined


def run_step(
    op: str,
    input_path: str,
    params: dict[str, Any] | None = None,
    tag: str = "step",
    timeout: float = 300.0,
) -> dict[str, Any]:
    """执行单个步骤,返回 result。输出图/预览按 tag 命名到 _run/。"""
    outputs = {
        "image": config.RUN_DIR / f"{tag}.xisf",
        "preview": config.RUN_DIR / f"{tag}.png",
    }
    job = protocol.new_job(op, input=input_path, params=params, outputs=outputs)
    protocol.submit(job)
    return protocol.wait_result(job["job_id"], timeout=timeout)


def run_pipeline(
    input_path: str,
    steps: list[tuple[str, dict[str, Any]]],
    timeout: float = 300.0,
    on_step: Callable[[int, str, dict], None] | None = None,
) -> list[dict[str, Any]]:
    """依次执行 steps=[(op, params), ...],output→input 串接。

    某步失败即终止(返回已完成的结果),便于定位问题。
    """
    results: list[dict[str, Any]] = []
    current = input_path
    for i, (op, params) in enumerate(steps):
        tag = f"p1_{i:02d}_{op}"
        res = run_step(op, current, params, tag=tag, timeout=timeout)
        results.append(res)
        if on_step:
            on_step(i, op, res)
        if res.get("status") != "ok":
            break
        if res.get("image"):
            current = res["image"]
    return results


def _summarize(step_idx: int, op: str, res: dict) -> None:
    """打印单步关键信息。"""
    print(f"\n----- step {step_idx}: {op} -> {res.get('status')} -----")
    if res.get("error"):
        print(f"  error: {res['error']}")
    if res.get("applied"):
        print(f"  applied: {res['applied']}")
    m = res.get("metrics")
    if m:
        print(f"  image: {m.get('width')}x{m.get('height')} ch={m.get('channels')}")
        for pc in m.get("perChannel", []):
            if "error" not in pc:
                print(f"    ch{pc['channel']}: median={pc['median']:.5f} "
                      f"stdDev={pc['stdDev']:.5f} min={pc['min']:.5f} max={pc['max']:.5f}")
    if res.get("preview"):
        print(f"  preview: {res['preview']}")
    if res.get("image"):
        print(f"  saved  : {res['image']}")


def measure(path: str, label: str = "", samples: int = 60000, timeout: float = 900.0) -> dict:
    """量一张图:返回 lumprobe 的 probe(anchors/ladder/clip/bgColor/hueStats)。"""
    job = protocol.new_job("lumprobe", input=str(path).replace("\\", "/"),
                           params={"linear": False, "samples": samples})
    protocol.submit(job)
    pr = protocol.wait_result(job["job_id"], timeout=timeout).get("probe") or {}
    if label:
        a, c = pr.get("anchors") or {}, pr.get("clip") or {}
        f, co = float(a.get("faint") or 0), float(a.get("core") or 0)
        print(f"  <{label}> bg={a.get('background')} faint={a.get('faint')} core={a.get('core')}"
              f" 动态={co - f:.3f} hi={(c.get('hiFrac') or 0) * 100:.2f}%"
              f" sat={(c.get('satFrac') or 0) * 100:.3f}% white={(c.get('whiteFrac') or 0) * 100:.2f}%")
    return pr


def check_overexposed(pr: dict, faint_ceil: float = 0.62, min_span: float = 0.15,
                      sat_ceil: float = 0.0015, white_ceil: float = 0.0008) -> dict:
    """**数值判过曝**。返回 {"over":bool, "why":[...], 各项实测值}。

    判据(四条,任一触发即过曝),阈值来自 NGC1499 实测反面教材:
      1. `faint > faint_ceil` —— faint 是 p90~p97 段均值 = **星云主体**的亮度。主体本该
         落在 0.30~0.50;实测那次 Ha 被拉到 **0.875** → 整条脊发白。这是最灵敏的一条。
      2. `core - faint < min_span` —— 主体动态范围(铁律 21)。实测 0.099 → 亮部被压平、
         结构全无。注意**只在 faint 偏高时才算过曝**,信号本来就弱(如 OIII faint 0.26)
         导致的小动态不是过曝,不该误判。
      3. `satFrac > sat_ceil` —— 接近饱和(≥0.995)的像素占比。
      4. `whiteFrac > white_ceil` —— 三通道齐平(视觉纯白)的占比。

    **必须在去星图上测**:带星图里星核本来就饱和,3/4 两条会被顶爆。
    """
    a, c = pr.get("anchors") or {}, pr.get("clip") or {}
    bg = float(a.get("background") or 0)
    faint = float(a.get("faint") or 0)
    core = float(a.get("core") or 0)
    span = core - faint
    sat = float(c.get("satFrac") or 0)
    white = float(c.get("whiteFrac") or 0)
    why = []
    if faint > faint_ceil:
        why.append(f"主体亮度 faint={faint:.3f} > {faint_ceil}(主体该在 0.30~0.50)")
    if faint > 0.55 and span < min_span:
        why.append(f"主体动态 core-faint={span:.3f} < {min_span}(亮部被压平)")
    if sat > sat_ceil:
        why.append(f"近饱和像素 {sat * 100:.3f}% > {sat_ceil * 100:.2f}%")
    if white > white_ceil:
        why.append(f"纯白像素 {white * 100:.3f}% > {white_ceil * 100:.2f}%")
    return {"over": bool(why), "why": why, "bg": bg, "faint": faint, "core": core,
            "span": span, "satFrac": sat, "whiteFrac": white}


def destretch_curve(bg: float, faint: float, core: float,
                    target_faint: float = 0.45, target_core: float = 0.78) -> list:
    """过曝**补救曲线**:把主体压回目标亮度,同时**展开**被压平的亮部动态。

    控制点 = [[0,0],[bg,bg],[faint,target_faint],[core,target_core],[1,1]]
    背景钉住不动;faint→core 这一段的斜率变成 (tc-tf)/(core-faint),原本被压成 0.1 的
    动态会被拉开(实测 0.099 → 0.33,斜率 3.3×)→ 脊上的结构重新出来。
    """
    bg = round(max(0.0, min(0.5, bg)), 4)
    faint = round(faint, 4)
    core = round(core, 4)
    tf = round(min(target_faint, faint), 4)
    tc = round(min(target_core, max(tf + 0.18, core)), 4)
    pts = [[0.0, 0.0], [bg, bg]]
    if faint > bg + 0.02:
        pts.append([faint, tf])
    if core > faint + 0.01:
        pts.append([core, tc])
    pts.append([1.0, 1.0])
    return pts


def guard_overexposure(path: str, tag: str, label: str = "",
                       target_faint: float = 0.45, target_core: float = 0.78,
                       timeout: float = 900.0, **thr) -> tuple[str, dict]:
    """测 → 判 → 若过曝就用补救曲线压回来 → 再测。返回 (可能已修正的路径, 诊断)。

    放在**拉伸之后、合成/调色之前**(用户:"这应该可以在前期通过数值检测解决")。
    单通道窄带各自过一遍比在合成图上补救更有效——合成后再压会连带改变颜色。
    """
    pr = measure(path, label or tag, timeout=timeout)
    d = check_overexposed(pr, **thr)
    if not d["over"]:
        print(f"  过曝自检:通过(faint={d['faint']:.3f} 动态={d['span']:.3f})")
        return path, d
    print(f"  [!] 过曝自检:{'; '.join(d['why'])}")
    pts = destretch_curve(d["bg"], d["faint"], d["core"], target_faint, target_core)
    print(f"  → 补救曲线 {pts}")
    job = protocol.new_job("curves", input=str(path).replace("\\", "/"),
                           params={"points": pts, "linear": False},
                           outputs={"image": str(config.RUN_DIR / f"{tag}.xisf").replace("\\", "/"),
                                    "preview": str(config.RUN_DIR / f"{tag}.png").replace("\\", "/")})
    protocol.submit(job)
    r = protocol.wait_result(job["job_id"], timeout=timeout)
    if r.get("status") != "ok":
        print(f"  [!] 补救失败({r.get('error')}),沿用原图")
        return path, d
    out = r["image"]
    pr2 = measure(out, (label or tag) + " 补救后", timeout=timeout)
    d2 = check_overexposed(pr2, **thr)
    d["after"] = d2
    d["curve"] = pts
    d["fixed"] = out
    if d2["over"]:
        print(f"  [!] 补救后仍报:{'; '.join(d2['why'])}(可能上游拉伸过头,建议减小 GHS D)")
    return out, d


def degreen_adaptive(path: str, tag: str, target: float = 0.39, probe_a: float = 0.5,
                     tol: float = 0.015, lo: float = 0.05, hi: float = 0.95,
                     timeout: float = 900.0) -> tuple[str, dict]:
    """SHO 假彩**自适应去绿**:按实测绿占比反解 SCNR 力度,不写死常数。

    为什么 SHO 该去绿:SHO 是假彩,绿是**分配**给 Ha 的通道,不是真实颜色 → 压绿得到
    主流的"金橙主体 + 青蓝翼"哈勃调。这与铁律 9(别对真实发射星云常规 SCNR)不冲突。

    判据 = `lumprobe.color.greenFrac`(星云亮区 ≥p90 像素的绿占比)。
    NGC1499 标定:a=0 → 0.500(太绿);**a=0.60 → 0.390(用户认可)**;a=0.90 → 0.345(去过头,
    连青也没了)。→ 目标默认 0.39。绿本来不过量的图(greenFrac ≤ target+tol)直接跳过。

    力度用**两点反解**:测 a=0 与 a=probe_a 两点,线性插到目标 a;再校验一次,偏差大就用
    最近两点重解。**每次都从原图重做** —— SCNR 不能在上次结果上叠加。
    """
    src = str(path).replace("\\", "/")

    def _gf(p):
        pr = measure(p, timeout=timeout)
        return float(((pr.get("color") or {}).get("greenFrac") or 1.0 / 3))

    def _scnr(a, sub):
        out = str(config.RUN_DIR / f"{tag}_{sub}.xisf").replace("\\", "/")
        job = protocol.new_job("scnr", input=src, params={"amount": round(a, 4)},
                               outputs={"image": out,
                                        "preview": out.replace(".xisf", ".png")})
        protocol.submit(job)
        r = protocol.wait_result(job["job_id"], timeout=timeout)
        if r.get("status") != "ok":
            raise RuntimeError(f"scnr 失败:{r.get('error')}")
        return r["image"]

    g0 = _gf(src)
    info = {"greenFrac0": round(g0, 4), "target": target}
    if g0 <= target + tol:
        print(f"  去绿:绿占比 {g0:.3f} ≤ 目标 {target}+{tol} → 跳过")
        info["amount"] = 0.0
        return src, info
    p1 = _scnr(probe_a, "probe")
    g1 = _gf(p1)
    print(f"  去绿标定:a=0 → {g0:.3f};a={probe_a} → {g1:.3f}")
    if g1 >= g0 - 1e-4:                     # 压不动(不该发生)→ 用探测值收场
        info.update({"amount": probe_a, "greenFrac": round(g1, 4), "note": "标定无响应"})
        return p1, info
    a = probe_a * (g0 - target) / (g0 - g1)
    a = max(lo, min(hi, a))
    if abs(a - probe_a) < 0.02:             # 探测值已经够准,省一次
        info.update({"amount": round(probe_a, 3), "greenFrac": round(g1, 4)})
        return p1, info
    p2 = _scnr(a, "fit")
    g2 = _gf(p2)
    print(f"  去绿反解:a={a:.3f} → 绿占比 {g2:.3f}(目标 {target})")
    if abs(g2 - target) > tol * 2:           # 还差得多 → 用最近两点再解一次
        if abs(g2 - g1) > 1e-4:
            a3 = a + (a - probe_a) * (target - g2) / (g2 - g1)
            a3 = max(lo, min(hi, a3))
            if abs(a3 - a) > 0.02:
                p3 = _scnr(a3, "fit2")
                g3 = _gf(p3)
                print(f"  去绿二次修正:a={a3:.3f} → 绿占比 {g3:.3f}")
                info.update({"amount": round(a3, 3), "greenFrac": round(g3, 4), "iters": 3})
                return p3, info
    info.update({"amount": round(a, 3), "greenFrac": round(g2, 4), "iters": 2})
    return p2, info


def _make_stopper(stages: list[str], stop_after: str, export_dir, results: dict):
    """给各流程共用的**交棒机制**:用户可只跑到某阶段,产物导出供其手工接管。

    返回 (reached, handoff):reached(stage)->bool 判断是否该停;handoff(stage, {名:路径})
    导出并返回 results(调用方 `return handoff(...)` 即可)。
    """
    import os as _os
    import shutil as _sh
    if stop_after not in stages:
        raise RuntimeError(f"stop_after 需为 {stages} 之一,收到 {stop_after!r}")
    idx = stages.index(stop_after)

    def reached(stage: str) -> bool:
        return stages.index(stage) >= idx

    def handoff(stage: str, files: dict):
        d = export_dir or str(config.RUN_DIR / f"handoff_{stage}")
        d = str(d).replace("\\", "/")
        _os.makedirs(d, exist_ok=True)
        out = {}
        for nm, p in files.items():
            if not p or not _os.path.exists(str(p)):
                continue
            ext = _os.path.splitext(str(p))[1] or ".xisf"
            dst = f"{d}/{nm}{ext}"
            try:
                _sh.copy2(str(p), dst); out[nm] = dst
            except OSError as e:
                print(f"    导出失败 {nm}: {e}")
        print(f"\n== 已按设置停在【{stage}】,产物导出到:{d} ==")
        for nm, p in out.items():
            print(f"    {nm}: {p}")
        print("   (后续步骤由你在 PixInsight 手工接管)")
        results["_handoff"] = {"stage": stage, "dir": d, "files": out}
        return results

    return reached, handoff


def run_hoo(input_path: str, timeout: float = 600.0,
            stop_after: str = "final", export_dir: str | None = None) -> dict[str, Any]:
    """OSC 双窄带 HOO 全流程(暗目标:星点/星云分开拉伸)。

    crop → gradient → deconv → hoo →
    starsep ┬ starless: stretch(unlinked,狠) → denoise → scnr(0.75)
            └ stars   : stretch(unlinked)
    → recombine(screen)
    返回各步 result 的字典。
    """
    R = config.RUN_DIR
    results: dict[str, dict] = {}

    def step(op, inp, params=None, tag="", stars_out=False):
        outs = {"image": R / f"{tag}.xisf", "preview": R / f"{tag}.png"}
        if stars_out:
            outs["stars"] = R / f"{tag}_stars.xisf"
        job = protocol.new_job(op, input=inp, params=params, outputs=outs)
        protocol.submit(job)
        r = protocol.wait_result(job["job_id"], timeout=timeout)
        results[tag] = r
        st = r.get("status")
        print(f"  [{tag}] {op} -> {st}" + (f" | {r.get('error')}" if r.get("error") else ""))
        _pv = r.get("preview")
        if _pv:
            print(f"[preview] {_pv}")   # GUI 嗅探此标记 → 右侧显示阶段效果图
        if st != "ok":
            raise RuntimeError(f"step {tag}({op}) failed: {r.get('error')}")
        return r

    print("== HOO 管线 ==")
    _HOO_STAGES = ["crop", "gradient", "bxt", "combine", "starless", "final"]
    _reached, _handoff = _make_stopper(_HOO_STAGES, stop_after, export_dir, results)
    r = step("crop",     input_path,   tag="h00_crop")
    if _reached("crop"):
        return _handoff("crop", {"cropped": r["image"]})
    r = step("gradient", r["image"],   tag="h01_grad")
    if _reached("gradient"):
        return _handoff("gradient", {"crop_gc": r["image"]})
    r = step("deconv",   r["image"],   params={"sharpenStars": 0}, tag="h02_deconv")  # 不缩星
    if _reached("bxt"):
        return _handoff("bxt", {"crop_gc_bxt": r["image"]})
    r = step("hoo",      r["image"],   tag="h03_hoo")
    if _reached("combine"):
        return _handoff("combine", {"hoo_combined": r["image"]})
    hoo_linear = r["image"]            # 全图线性 HOO,用于策略2的 STF 参考
    sep = step("starsep", hoo_linear,  tag="h04_starsep", stars_out=True)
    if _reached("starless"):
        return _handoff("starless", {"starless": sep["image"], "stars": sep.get("stars")})
    starless_lin, stars_lin = sep["image"], sep.get("stars")
    if not stars_lin:
        raise RuntimeError("星点分离未产出星点图")

    # 星云:逐通道拉伸(暗目标提亮)→ 降噪 → 去绿 → 曲线(对比+微饱和)
    sl = step("stretch", starless_lin,
              params={"linked": False, "targetBackground": 0.24}, tag="h05_starless_str")
    sl = step("denoise", sl["image"], params={"linear": False}, tag="h06_starless_dn")
    sl = step("scnr",    sl["image"], params={"amount": 0.75}, tag="h07_starless_scnr")
    sl = step("curves",  sl["image"], params={"contrast": 0.12, "saturation": 0.12}, tag="h07b_starless_curves")
    starless_final = sl["image"]

    # 星点(策略2):套用全图 STF,线性→非线性。星点图背景近 0 会落在曲线黑场之下自动压黑,
    # 星点则以"以真实背景为基准"的合理曲线提亮,不会炸开噪声/棋盘纹
    st = step("stretch", stars_lin,
              params={"stfFrom": hoo_linear, "linked": False}, tag="h08_stars_str")
    stars_final = st["image"]

    # 合成
    fin = step("recombine", starless_final,
               params={"stars": stars_final}, tag="h09_final")
    print(f"\n最终成片: {fin.get('image')}")
    print(f"最终预览: {fin.get('preview')}")
    return results


def run_detrail(registered_dir: str, timeout: float = 1800.0,
                max_drop_frac: float = 0.40, zoom: int = 8,
                min_frac: float = 0.30, min_keep: int = 12) -> dict:
    """全自动卫星/飞机线去除(整帧剔除法)。

    对 registered 目录下所有已配准单张:
      1) residualset op 生成"帧 − 中位参考"的残差缩略图(静态星云/星点抵消,只剩逐帧
         瞬时线状结构);
      2) cv2 概率霍夫在残差图上检出长直线 = 含轨迹的帧(detrail.detect_trail_frames);
      3) 把这些帧整帧剔除,返回保留帧列表 keep(供 run_integrate(images=keep))。

    **为何整帧剔除而非挖线**:实测检测帧准确,整帧剔除轨迹必净;而精确 maskline 受缩略图
    定位精度限制(zoom-8 上 ±几像素 ×8 = 全分辨率几十像素)挖不净(见 pi-wbpp-stacking)。
    **护栏**:若含线帧超过 max_drop_frac(默认 25%),丢帧会显著损失信噪 → 不自动剔除,
    保留全部并告警(交叠列表让上层决定)。

    返回 {"all":[...], "trail_idx":[...], "keep":[...], "dropped":[...],
          "audit":png路径, "skipped":bool(是否因超护栏未剔)}。
    """
    import os
    from pathlib import Path
    from . import detrail as _detrail

    root = Path(registered_dir)
    subs = sorted(str(p).replace("\\", "/") for p in root.rglob("*.xisf"))
    if len(subs) < 3:
        raise RuntimeError(f"registered 目录下 .xisf 太少({len(subs)}):{registered_dir}")

    thumb_dir = str((config.RUN_DIR / "detrail_res")).replace("\\", "/")
    os.makedirs(thumb_dir, exist_ok=True)
    print(f"== 去线检测:{len(subs)} 张 → 残差缩略图({thumb_dir}) ==")
    job = protocol.new_job("residualset",
                           params={"images": subs, "outDir": thumb_dir, "zoom": zoom})
    protocol.submit(job)
    r = protocol.wait_result(job["job_id"], timeout=timeout)
    # residualset 收尾可能报 error,但缩略图已落盘 → 以磁盘上的 res_*.png 为准
    import glob as _glob
    n_thumb = len(_glob.glob(thumb_dir + "/res_*.png"))
    if n_thumb < 3:
        raise RuntimeError(f"残差缩略图生成失败(仅 {n_thumb} 张):{r.get('error')}")

    audit = str((config.RUN_DIR / "detrail_audit.png")).replace("\\", "/")
    det = _detrail.detect_trail_frames(thumb_dir, min_frac=min_frac, audit_path=audit)
    trail_idx = sorted(det.keys())
    keep = [subs[i] for i in range(len(subs)) if i not in det]
    dropped = [subs[i] for i in trail_idx if i < len(subs)]
    frac = len(trail_idx) / max(1, len(subs))

    print(f"[preview] {audit}")
    if not trail_idx:
        print("  未检出卫星/飞机线,全部帧保留。")
        return {"all": subs, "trail_idx": [], "keep": subs, "dropped": [],
                "audit": audit, "skipped": False}
    print(f"  检出含轨迹帧 {len(trail_idx)}/{len(subs)}({frac:.0%}):{trail_idx}")
    # 护栏改成"比例 + 绝对保留数"两条一起看。
    # 【NGC1499 教训】原来只看 25% 比例:G 通道遇到**卫星编队**(一串卫星沿同一轨道 → 配准后
    # 多帧的线几乎叠在同一位置),检出帧比例一超 25% 就整体放弃剔除 → 线**直接进了成片**,
    # 而且这种"多帧同位置"的线连 sigma 剔除也除不掉(它在那条线上不再是离群值)。
    # 现实里 31 帧丢 10 帧只损失 ~18% 信噪,远比留一条线划算 → 放宽到 40%,再加绝对下限。
    snr_cost = (1 - (len(keep) / len(subs)) ** 0.5) if keep else 1.0
    if frac > max_drop_frac or len(keep) < min_keep:
        why = (f"检出比例 {frac:.0%} > 护栏 {max_drop_frac:.0%}" if frac > max_drop_frac
               else f"剔除后仅剩 {len(keep)} 张 < 下限 {min_keep} 张")
        print(f"  [!] {why} → 不自动剔除,保留全部帧。")
        print(f"      注意:轨迹会残留进 master。若是**卫星编队**(多帧线叠在同一位置),"
              f"sigma 剔除也除不掉,需手工挑帧或接受。审计图:{audit}")
        return {"all": subs, "trail_idx": trail_idx, "keep": subs, "dropped": [],
                "audit": audit, "skipped": True, "snrCost": round(snr_cost, 3)}
    print(f"  → 整帧剔除 {len(dropped)} 张,保留 {len(keep)} 张整合"
          f"(信噪代价 ≈{snr_cost:.0%})。")
    return {"all": subs, "trail_idx": trail_idx, "keep": keep, "dropped": dropped,
            "audit": audit, "skipped": False}


def run_cull(registered_dir: str, timeout: float = 1800.0, mad_k: float = 3.0, ratio: float = 1.6,
             max_drop_frac: float = 0.40, min_keep: int = 12, use_stars: bool = False,
             subs: list[str] | None = None) -> dict:
    """智能筛片(叠加前):按**逐帧背景亮度**剔除有云/透明度差的帧。

    云/薄云经过时该帧被散射光抬高背景、且不均 → 叠进栈里就是明暗带/条纹(sigma 剔除去不掉,因为
    整帧偏亮不是像素级离群)。做法:对每张已配准单张测 lumprobe 背景锚点,用**鲁棒离群**(中位 + MAD)
    只标记"背景异常偏高"的高端离群帧(不动正常/偏暗帧),整帧剔除,keep 交给 run_integrate。
    可选 use_stars:同时看星点像素(透明度差→星点少)辅证,默认关(背景单指标已足够稳)。

    护栏:剔除比例 > max_drop_frac 或剩余 < min_keep → 不自动剔(可能整晚天气差,全剔无意义),只报告。
    返回 {all, keep, dropped, bg:{idx:值}, stars:{idx:值}, med, mad, skipped}。
    """
    import statistics
    from pathlib import Path
    if subs is None:
        root = Path(registered_dir)
        subs = sorted(str(p).replace("\\", "/") for p in root.rglob("*.xisf"))
    n = len(subs)
    if n < 5:
        return {"all": subs, "keep": subs, "dropped": [], "skipped": True, "reason": f"帧太少({n})"}

    def query(op, inp, params=None):
        job = protocol.new_job(op, input=inp, params=params)
        protocol.submit(job)
        return protocol.wait_result(job["job_id"], timeout=timeout)

    print(f"== 智能筛片:测 {n} 张逐帧背景{'+星点' if use_stars else ''} ==")
    bgs: list = [None] * n
    stars: list = [None] * n
    for i, p in enumerate(subs):
        _ckc()
        pr = (query("lumprobe", p, {"linear": True}).get("probe") or {})
        bgs[i] = (pr.get("anchors") or {}).get("background")
        if use_stars:
            try:
                stars[i] = (query("starstats", p).get("starStats") or {}).get("starPixels")
            except Exception:
                pass
    valid = [b for b in bgs if b is not None]
    if len(valid) < 5:
        return {"all": subs, "keep": subs, "dropped": [], "skipped": True, "reason": "背景测量失败"}
    med = statistics.median(valid)
    mad = statistics.median([abs(b - med) for b in valid]) * 1.4826 or 1e-9
    thr = max(med + mad_k * mad, med * ratio)   # 高端离群阈值:MAD 与比例取更松的一个,避免误杀
    reject = [i for i, b in enumerate(bgs) if b is not None and b > thr]
    print(f"  背景 中位={med:.5f} MAD={mad:.5f} → 云帧阈值 bg>{thr:.5f}"
          f"(即 z>{mad_k} 或 >{ratio:.2f}×中位)")
    for i in reject:
        z = (bgs[i] - med) / mad
        print(f"    云帧 #{i}: bg={bgs[i]:.5f}(z={z:.1f})"
              + (f" stars={stars[i]}" if use_stars else "") + f"  {Path(subs[i]).name}")
    keep = [subs[i] for i in range(n) if i not in reject]
    frac = len(reject) / n
    out = {"all": subs, "bg": {i: bgs[i] for i in range(n)},
           "stars": {i: stars[i] for i in range(n)}, "med": med, "mad": mad}
    if frac > max_drop_frac or len(keep) < min_keep:
        print(f"  [!] 云帧比例 {frac:.0%}(>{max_drop_frac:.0%})或剩余 {len(keep)}(<{min_keep})→ 不自动筛,保留全部。")
        out.update(keep=subs, dropped=[], skipped=True)
        return out
    print(f"  → 筛掉 {len(reject)} 张云/低透明度帧,保留 {len(keep)} 张。")
    out.update(keep=keep, dropped=[subs[i] for i in reject], skipped=False)
    return out


def run_integrate(registered_dir: str, out_path: str | None = None,
                  timeout: float = 1800.0, trail_reject: bool = True,
                  sigma_low: float = 4.0, sigma_high: float = 2.8,
                  images: list[str] | None = None) -> str:
    """把 registered 目录(含按夜分的子目录)下所有 .xisf 单张叠加成一个新 master。

    对应作者多日拍摄工作流:不直接用 WBPP 的分夜 masterLight,而是把所有已配准
    单张一起 ImageIntegration。返回新 master 的路径。

    **默认开启去线**(`trail_reject=True`):Winsorized sigma(sigma_low/high 4.0/2.8)
    + **大尺度高段剔除**,把卫星线/飞机线/电线投影宽带等线状延展亮结构扫进高段剔除、
    不进 master(实测配方,见 pi-wbpp-stacking)。普通 sigma 裁剪对宽/软的线不敏感,
    必须靠 largeScaleClipHigh。数据帧数很少(<8)时可关(trail_reject=False)以免误剔真信号。
    """
    from pathlib import Path
    if images is not None:
        subs = [str(p).replace("\\", "/") for p in images]
    else:
        root = Path(registered_dir)
        subs = sorted(str(p).replace("\\", "/") for p in root.rglob("*.xisf"))
    if len(subs) < 3:
        raise RuntimeError(f"registered 目录下 .xisf 太少({len(subs)}):{registered_dir}")
    if out_path is None:
        out_path = str(config.RUN_DIR / "integrated_master.xisf")
    out_path = str(out_path).replace("\\", "/")
    ip = {"images": subs, "sigmaLow": sigma_low, "sigmaHigh": sigma_high}
    if trail_reject:
        ip.update({"trailReject": True, "trailProtect": 2, "trailGrowth": 2})
    print(f"== ImageIntegration:{len(subs)} 张 → {out_path} "
          f"(去线={'开' if trail_reject else '关'} sigma={sigma_low}/{sigma_high}) ==")
    job = protocol.new_job("integrate", params=ip,
                           outputs={"image": out_path,
                                    "preview": str(config.RUN_DIR / "integrated_master.png")})
    protocol.submit(job)
    r = protocol.wait_result(job["job_id"], timeout=timeout)
    if r.get("status") != "ok":
        raise RuntimeError(f"integrate 失败:{r.get('error')}")
    m = r.get("metrics", {})
    print(f"  完成:{m.get('width')}x{m.get('height')}  applied={r.get('applied')}")
    print(f"  master: {r.get('image')}")
    print(f"  preview: {r.get('preview')}")
    return r.get("image")


# 评委问题 → 可自动补救的动作(其余问题如过锐化/过降噪/星点膨胀无法事后撤销,只报告)
_ISSUE_ACTION = {
    "edge_artifact": "crop",
    "residual_gradient": "gradient",
    "color_cast": "scnr",
    "background_washout": "contrast",
    "over_saturation": "desaturate",
    "noise": "denoise",
}


def _print_verdict(v, it=None):
    tag = f"[第{it + 1}轮] " if it is not None else ""
    print(f"  {tag}verdict={v.get('verdict')} confidence={v.get('confidence')} issues={v.get('issues')}")
    print(f"  reason: {v.get('reason')}")


def _do_action(step, r, action, ref_preview, ctx, tag):
    """执行一个补救动作,返回新的 result(失败/无操作返回 None)。"""
    from . import critic
    if action == "crop":
        sc = critic.suggest_crop(ref_preview, context=ctx)
        m = r.get("metrics") or {}
        W, H = m.get("width"), m.get("height")
        if sc.get("error") or not (W and H):
            return None
        margins = {"left": int(sc["left"] / 100 * W), "right": int(sc["right"] / 100 * W),
                   "top": int(sc["top"] / 100 * H), "bottom": int(sc["bottom"] / 100 * H)}
        if not any(margins.values()):
            return None
        return step("crop", r["image"], params={"margins": margins, "linear": False}, tag=tag)
    if action == "gradient":
        return step("gradient", r["image"],
                    params={"method": "GradientCorrection", "linear": False}, tag=tag)
    if action == "scnr":
        return step("scnr", r["image"], params={"amount": 0.6, "linear": False}, tag=tag)
    if action == "contrast":
        return step("curves", r["image"], params={"contrast": 0.10, "linear": False}, tag=tag)
    if action == "desaturate":
        return step("curves", r["image"], params={"saturation": -0.15, "linear": False}, tag=tag)
    if action == "denoise":
        return step("denoise", r["image"], params={"linear": False}, tag=tag)
    return None


def _critic_finish(step, r, ctx: str, timeout: float = 600.0,
                   auto: bool = True, max_iters: int = 3):
    """LLM 评委迭代闭环:诊断 → 补救 → 复评,直到评委满意 / 无新动作 / 达上限。

    每种补救动作全程最多执行一次(防过度处理)。auto=False 时只报告不补救。
    """
    from . import critic
    print("\n== LLM 评委(迭代闭环)==")
    applied_ever = set()
    for it in range(max_iters):
        v = critic.critique(r.get("preview"), context=ctx)
        if v.get("error"):
            print(f"  评委不可用:{v['error']}")
            break
        _print_verdict(v, it)
        if not auto:
            break
        if v.get("verdict") == "ok" or v.get("stop"):
            print("  评委满意,停止迭代。")
            break
        issues = v.get("issues") or []
        todo = []
        for iss in issues:
            act = _ISSUE_ACTION.get(iss)
            if act and act not in applied_ever and act not in todo:
                todo.append(act)
        if not todo:
            print("  剩余问题无新的可自动补救动作,停止。")
            break
        ref_preview = r.get("preview")
        for act in todo:
            nr = _do_action(step, r, act, ref_preview, ctx, tag=f"ci{it}_{act}")
            applied_ever.add(act)
            if nr:
                r = nr
                print(f"    · 已补救:{act}")
            else:
                print(f"    · 跳过:{act}(无有效操作)")
    print(f"  闭环结束,累计补救:{sorted(applied_ever) or '无'}")
    return r


def run_rgb(input_path: str, timeout: float = 600.0,
            ghs_d: float = 0.5, neb_sat: float = 0.15,
            recombine_stars: bool = False,
            stretch_judge: bool = True, target: str = "",
            stretch_refs: list[str] | None = None,
            reveal: bool = True, reveal_d: float = 0.7,
            lhe: bool = True, cluster: bool | None = None,
            lights_only: bool = False, darkstruct: dict | None = None,
            colorcal: str | None = None, star_scnr: float = 0.0, star_blue: float = 0.0,
            star_boost: float = 0.80,
            stop_after: str = "final", export_dir: str | None = None,
            _quality_retry: bool = False) -> dict[str, Any]:
    """宽带 RGB 真实色全流程(IC4592 蓝马头定稿"顺滑"配方)。

    设计要点(见记忆 pi-gradient-findings):
    - 梯度:GC → ABE(subtract, deg4) 两级压平(ratio≈1.02),必须在**线性、GHS 之前**做;
      GHS 之后再做梯度会把亮星云当背景,产生"眼环"。
    - 拉伸顺滑优先(低 SNR 素材别硬凸显):温和拉伸(tb=0.12)+ 温和 GHS(D=0.5)+
      **两道降噪**(线性一道压亮度噪声;GHS 后一道带色度/低频专门抹斑驳紫斑)。
    - 不用黑场硬压、不加大饱和/对比(会过冲发硬);星云饱和仅 +0.15。
    - 成片默认 **starless**(定稿形态);recombine_stars=True 时才极轻合回星点。

    ghs_d / neb_sat:换目标验证时可微调(星云提亮量 / 星云饱和)。
    """
    global CANCEL
    CANCEL = False
    R = config.RUN_DIR
    results: dict[str, dict] = {}

    # 终清(r11e)用 NXT 旧版模型 NoiseXTerminator.2.pb 规避絮状 → 开跑前确保它在 PI library 里(缺则从内置装回)
    try:
        from . import deps as _deps
        for _m in _deps.ensure_bundled_models(log=lambda s: print(f"  {s}")):
            if _m.get("status") not in ("present", "restored"):
                print(f"  [模型] {_m.get('label')}: {_m.get('detail', _m.get('status'))}")
    except Exception as _e:
        print(f"  [模型] 装回检查异常(忽略):{_e}")

    def step(op, inp, params=None, tag="", extra=None):
        _ckc()
        outs = {"image": R / f"{tag}.xisf", "preview": R / f"{tag}.png"}
        if extra:
            outs.update(extra)
        job = protocol.new_job(op, input=inp, params=params, outputs=outs)
        protocol.submit(job)
        r = protocol.wait_result(job["job_id"], timeout=timeout)
        results[tag] = r
        st = r.get("status")
        print(f"  [{tag}] {op} -> {st}" + (f" | {r.get('error')}" if r.get("error") else ""))
        _pv = r.get("preview")
        if _pv:
            print(f"[preview] {_pv}")   # GUI 嗅探此标记 → 右侧显示阶段效果图
        if st != "ok":
            raise RuntimeError(f"step {tag}({op}) failed: {r.get('error')}")
        return r

    def query(op, inp, params=None):
        job = protocol.new_job(op, input=inp, params=params)
        protocol.submit(job)
        return protocol.wait_result(job["job_id"], timeout=timeout)

    # 角落敏感裁切参数(分段抓角落)。coverageThreshold=0.20:**只裁近黑硬边(<20%内部背景)+ 亮缝**,
    #   渐变式变暗的欠覆盖边**保留**、交给梯度校正(GC/ABE)去补,保住 FOV(用户 2026-08-27 定)。
    #   实测 M23 右边最暗段 0.28×ib(渐变、非硬黑)→ 旧默认 0.6 误裁 296px,新阈值下保留。硬黑边(0 覆盖)仍裁。
    CROP = {"segments": 6, "brightFrac": 2.5, "extraMargin": 8, "coverageThreshold": 0.20}

    print("== 宽带 RGB 管线(顺滑配方)==")
    # ---- 线性阶段 ----
    _RGB_STAGES = ["crop", "gradient", "bxt", "colorcal", "denoise", "stretch",
                   "starless", "color", "final"]
    _reached, _handoff = _make_stopper(_RGB_STAGES, stop_after, export_dir, results)
    r = step("crop",     input_path,  params=CROP, tag="r00_crop")   # 先裁,免边缘污染统计
    if _reached("crop"):
        return _handoff("crop", {"cropped": r["image"]})
    r = step("gradient", r["image"],  params={"method": "GradientCorrection"}, tag="r01_gc")
    if _reached("gradient"):
        return _handoff("gradient", {"crop_gc": r["image"]})
    # BXT:不缩星(sharpenStars=0,原星点不肥只需修圆)+ Sharpen Nonstellar=0.5(温和,别用 BXT 默认 ~0.9
    #   过锐化会放大背景噪声/结构)。用户 M23 手动配方实测(见记忆 pi-quality-gate)。
    r = step("deconv",   r["image"],  params={"sharpenStars": 0, "sharpen": 0.5}, tag="r02_deconv")
    if _reached("bxt"):
        return _handoff("bxt", {"crop_gc_bxt": r["image"]})
    # 颜色校准:colorcal=None 自适应(优先 SPCC 需解析,回退 BN+CC);"bncc"/"spcc" 强制。
    #   SPCC 依赖 Gaia SP 库,无界面自动实例可能用不上(见 pi-online-solve-spcc)→ SPCC 零校正、
    #   OSC 绿铸不除;强制 colorcal="bncc"(BN+CC 白平衡)不靠 Gaia 也能压绿。
    _force = colorcal if colorcal in ("bncc", "spcc") else None
    if _force == "bncc":
        solved = False
    else:
        solved = bool(query("checksolve", r["image"]).get("solveInfo", {}).get("hasSolution"))
    if (_force != "bncc") and (not solved):
        print("  无天文解析,尝试本地 ImageSolver…")
        try:
            r = step("solve", r["image"], tag="r02b_solve")
            solved = bool(query("checksolve", r["image"]).get("solveInfo", {}).get("hasSolution"))
        except RuntimeError as e:
            print(f"  本地解析失败:{e}")
    if (_force != "bncc") and (not solved):
        # Tier2:nova.astrometry.net 在线盲解兜底(需在设置里配 astrometry_api_key)。
        #   本地盲解常因智能望远镜头缺焦距/尺度而失败;nova 不依赖头。解在**裁剪之后**应用,
        #   不会被 r00_crop 剥掉。关键:不限像素尺度(否则会把 nova 降采版尺度排除→失败)。
        try:
            _key = (config.get_setting("astrometry_api_key") or "").strip()
            if not _key:
                print("  未配置 astrometry_api_key → 跳过在线兜底(将用 bncc)")
            else:
                from . import astrometry_online as _ao
                print("  → nova.astrometry.net 在线兜底(不限尺度盲解)…")
                _sr = step("stretch", r["image"], params={"linked": True, "targetBackground": 0.25},
                           tag="r02c_solveimg")
                _png = _sr.get("preview") or ""
                _m = _sr.get("metrics") or {}
                _W = int(_m.get("width") or 0); _H = int(_m.get("height") or 0)
                _wcsf = str(R / "nova_wcs.fits").replace("\\", "/")
                _nr = _ao.solve_online(_png, _key, wcs_out=_wcsf, timeout=900,
                                       log=lambda m: print("   " + str(m)))
                if _nr.get("ok") and _W and _H:
                    _scaled = _scale_wcs_for(_wcsf, _W, _H)
                    _ar = step("applywcs", r["image"], params={"wcs": _scaled}, tag="r02d_applywcs")
                    solved = bool((_ar.get("applied") or {}).get("solved"))
                    if solved:
                        r = _ar
                        print("  nova 在线解析 + applywcs 精修成功 → SPCC 可用")
                    else:
                        print("  nova 解出但 applywcs 精修未成解 → 用 bncc")
                else:
                    print(f"  nova 在线解析失败:{_nr.get('error')} → 用 bncc")
        except Exception as _e:
            print(f"  nova 在线兜底异常:{_e} → 用 bncc")
    method = _force or ("spcc" if solved else "bncc")
    print(f"  颜色校准: {method}(天文解析={solved}{',强制' if _force else ''})")
    # ---- 目标分类第一级:DSO 类型(星团=候选克制)----
    # 星团(球状/疏散)背景常没星云星系,拉伸只会把天光噪声抬成奶雾 → 候选走克制。
    # 靠解析出的 OBJECT 名查 DSO 目录(dso_search)得类型;GCL/OCL=星团。
    cluster_candidate = False
    cluster_name = target
    if cluster is None:
        try:
            from . import dso
            if not cluster_name:
                si = query("checksolve", r["image"]).get("solveInfo", {})
                cluster_name = (si.get("keywords") or {}).get("OBJECT", "")
            cl = dso.classify(cluster_name) if cluster_name else {"cluster": False, "type": None}
            cluster_candidate = bool(cl.get("cluster"))
            print(f"  目标分类: name={cluster_name!r} type={cl.get('type')} → "
                  f"{'星团候选' if cluster_candidate else '有延展信号(正常揭示)'}")
        except Exception as e:
            print(f"  目标分类跳过(异常):{e}")
    # ── AstroBin 同视场参考(**解析后**拉,当处理中的"审美目标"喂 judge_ghs 等;此刻 WCS 还在,
    #    colorcal/gradient 之后会被剥,所以必须现在抓坐标)。有解析才拉;拉不到/无参考/未配置一律
    #    优雅跳过(退回固定标准)。用户显式传的 stretch_refs 优先,不覆盖。见记忆 pi-astrobin-reference。
    _ref_tg = None                        # AstroBin 参考导出的"因目标而异"经验目标(ref_targets)
    if solved and not stretch_refs:
        try:
            from . import astrobin_ref, quality
            _si2 = query("checksolve", r["image"]).get("solveInfo", {})
            _ra, _dec = _si2.get("CRVAL1"), _si2.get("CRVAL2")
            if _ra is not None and _dec is not None:
                _sim = astrobin_ref.fetch_similar(float(_ra), float(_dec), radius=2.0, pagesize=8)
                _items = _sim.get("list") or []
                if _items:
                    _saved = astrobin_ref.download_thumbs(_items, R / "astrobin_refs", limit=6)
                    stretch_refs = [s["local_path"] for s in _saved if s.get("local_path")]
                    _ref_tg = quality.ref_targets(stretch_refs)      # 测参考图 → 该天体经验目标
                    print(f"  [AstroBin] 解析后拉到 {len(stretch_refs)} 张同视场参考"
                          f"(RA {float(_ra):.2f} Dec {float(_dec):.2f});经验目标={_ref_tg}")
                else:
                    print(f"  [AstroBin] 该视场暂无同视场参考"
                          f"(RA {float(_ra):.2f} Dec {float(_dec):.2f})→ 用固定标准")
        except Exception as _abe:
            print(f"  [AstroBin] 参考拉取跳过:{_abe}")
    r = step("colorcal", r["image"],  params={"method": method}, tag="r03_colorcal")
    if _reached("colorcal"):
        return _handoff("colorcal", {"color_calibrated": r["image"]})
    r = step("gradient", r["image"],  params={"method": "abe", "polyDegree": 4}, tag="r04_abe")  # 压平梯度
    # 线性强降噪(压亮度噪声,GHS 前)
    # 第一次降噪:NXT iterations=2(线性态强压亮度噪声)。**只有第一次用 2**——NXT AI v3 多次 iterations=2
    #   叠加会把噪声搓成"絮状"伪结构(用户 M23 放大实见),后续降噪一律 iterations=1 且降强度。
    r = step("denoise",  r["image"],  params={"denoise": 0.90, "detail": 0.10, "iterations": 2}, tag="r05_dn")
    if _reached("denoise"):
        return _handoff("denoise", {"linear_denoised": r["image"]})
    # ---- 目标分类第二级:星团候选 → LLM 看画面有无"较大面积暗云/星云"值得保留 ----
    # 类型是星团 ≠ 画面一定空(如 M45 裹反射星云、银河球团压暗云带)→ 有大面积暗云/星云则退回正常。
    cluster_mode = cluster if cluster is not None else False
    if cluster is None and cluster_candidate:
        cluster_mode = True   # 默认克制,除非发现有延展结构
        # **优先用 AstroBin 参考的填充度(signal_frac)确定性判断**:星团 ≠ 画面一定空——M45 裹反射星云、
        #   银河球团压暗云带,其优秀作品被星云/尘埃填满(signal_frac 高)→ 该正常揭示不钉黑;真空旷星团
        #   (signal_frac 低)→ 钉黑。有参考就不劳 LLM(kimi 顽固把密集星场误判);无参考再退回 judge_field_extended
        #   + 置信度闸。见 [[pi-astrobin-reference]] [[pi-quality-gate]]。
        if _ref_tg and _ref_tg.get("n"):
            _sf = float(_ref_tg.get("signal_frac") or 0.0)
            if _sf > 0.30:
                cluster_mode = False
                print(f"  → [参考] signal_frac={_sf} 高=画面被星云/尘埃填满 → 正常揭示(不克制)")
            else:
                print(f"  → [参考] signal_frac={_sf} 低=空旷星团场 → 克制钉黑")
        else:
            try:
                from . import critic
                if critic.is_configured():
                    pv = step("inspect", r["image"], params={"linear": True},
                              tag="r05p_field").get("preview")
                    fe = critic.judge_field_extended(pv, target=cluster_name,
                                                     context="星团背景钉黑门控:有大面积暗云/星云则不钉黑")
                    if fe.get("error"):
                        print(f"  [场判] 不可用:{fe['error']}(按类型走克制)")
                    else:
                        _conf = float(fe.get("confidence") or 0.0)
                        print(f"  [场判] has_extended={fe.get('has_extended')} conf={_conf} "
                              f"kind={fe.get('kind')} :: {fe.get('reason')}")
                        # 置信度闸 + **类型闸**:kimi 常把密集星场/银河误判成延展结构 → 需高置信(≥0.6)。
                        #   且**只有成片亮星云(nebula/both)才退回揭示**;`darkcloud`(暗云带/尘)本身就暗,
                        #   "揭示"会把暗云连同背景 carpet 一起抬亮发脏(用户 M23 反馈)——暗云该靠**受控拉伸**
                        #   在干净背景上自然显出,而非抬亮。故暗云保持克制。见 [[pi-clean-stars-dualstretch]]。
                        _kind = str(fe.get("kind") or "")
                        if fe.get("has_extended") and _conf >= 0.6 and _kind in ("nebula", "both"):
                            cluster_mode = False
                            print(f"  → 画面有成片亮星云(kind={_kind}),退回正常处理(揭示亮星云)")
                        elif fe.get("has_extended") and _conf >= 0.6:
                            print(f"  → 有暗云带(kind={_kind})但仍是星团 → 保持克制:暗云靠受控拉伸显出,不抬亮发脏")
                        elif fe.get("has_extended"):
                            print(f"  → 场判置信度低({_conf}<0.6),保持星团克制(防星场误判)")
                else:
                    print("  [场判] 未配置 LLM(且无参考),按类型走克制。")
            except Exception as e:
                print(f"  [场判] 跳过(异常):{e}")
    # 纯亮场(无暗场校准,如 Seestar)背景残留热噪/辉光/热梯度,reveal 会把它放大成褐麻点 →
    # 与星团候选一样走"干净背景"路线:不揭示、压背景(clean_bg)。见记忆 pi-stacking-engine-roadmap。
    clean_bg = cluster_mode or lights_only
    if clean_bg:
        reveal = lhe = stretch_judge = False
        # 【克制拉伸对齐用户参考】GHS 是双曲拉伸、专抬暗部 faint 信号(=尘+密集暗星 carpet 整层被抬亮发脏)。
        #   用户"多次 HT 收敛到受控波形"的暗部落点低得多 → 克制模式把 GHS 力度**按比例大幅压低**(默认 0.5→0.125),
        #   只当"轻拉深"用;背景饱和也压低(实测 LLM 反馈"背景明显偏蓝")。见 [[pi-clean-stars-dualstretch]] [[pi-aesthetic-prefs]]。
        ghs_d = round(ghs_d * 0.25, 3)        # 0.5→0.125:GHS 只轻拉,不猛抬暗部
        neb_sat = round(neb_sat * 0.40, 3)    # 0.15→0.06:压低背景饱和,避免偏蓝/均衡超标
        print(f"  → 干净背景模式({'星团克制' if cluster_mode else '纯亮场无暗场'}):"
              f"GHS 轻拉 D={ghs_d} / 饱和 {neb_sat} / 不揭示 / 背景压暗")
    # ---- 拉伸 → 分离星点 ----
    _lin_for_stars = r["image"]   # 存**线性图**:干净星点走"软拉伸轨"(见下 recombine_stars),需退回线性单独提星
    _clean_stars = None           # 软拉伸轨提到的干净星点(供合星 + 质量门星蒙版);None=退回传统轨
    # 背景峰值统一钉到标准位 PEAK_BG(3/16);干净背景模式按比例更暗:星团 0.42×(更暗,配合克制)、纯亮场 0.75×。
    tb = (0.42 if cluster_mode else 0.75 if lights_only else 1.0) * PEAK_BG
    r = step("stretch",  r["image"],  params={"linked": True, "targetBackground": tb}, tag="r06_str")
    if _reached("stretch"):
        return _handoff("stretch", {"stretched": r["image"]})
    sep = step("starsep", r["image"], tag="r07_sep", extra={"stars": R / "r07_stars.xisf"})
    if _reached("starless"):
        return _handoff("starless", {"starless": sep["image"], "stars": sep.get("stars")})
    # ---- 星云(starless)后期 ----
    # 【干净背景/带尘场:跳过二次揭示】实测(M23):r06_str 拉伸阶段(GC+BXT+降噪后)已把暗尘揭示到位、
    #   星点+暗尘+干净背景俱佳;再对无星星云做 GHS 会把暗尘抬成棕浆、引红移。故 clean_bg 直接用 r06_str
    #   的星云层,不二次 GHS。见记忆 pi-reference-recipe-m23(r06_str 好、后处理做坏了)。
    if clean_bg:
        neb = {"image": sep["image"], "preview": sep.get("preview")}
        print("  → 干净背景:跳过 r08_ghs 二次揭示(暗尘已在拉伸阶段显现,避免棕浆/红移)")
    else:
        neb = step("ghs",    sep["image"], params={"D": ghs_d, "HP": 0.9}, tag="r08_ghs")
    # 【拉伸力度自检闭环】GHS 后让评委(judge_ghs)对照判 D:偏离当前且非 stop 就按建议
    # 重拉一次(仅一次,防振荡)。对低面亮度弥散星云(如 NGC7000),固定 ghs_d 常偏保守 →
    # 评委报 too_dark、给更大 D。可选喂 AstroBin 同视场参考(stretch_refs)让判断更准。
    if stretch_judge:
        try:
            from . import critic
            if critic.is_configured():     # provider/model/key 齐备才判
                jv = critic.judge_ghs(neb.get("preview"), ref_paths=stretch_refs or [],
                                      target=target or "", context="自动管线 GHS 拉伸自检",
                                      cur_d=ghs_d)
                if jv.get("error"):
                    print(f"  [GHS评委] 不可用:{jv['error']}")
                else:
                    sd = float(jv.get("suggested_D", ghs_d))
                    print(f"  [GHS评委] issues={jv.get('issues')} suggested_D={sd} "
                          f"(当前 {ghs_d}) stop={jv.get('stop')} :: {jv.get('reason')}")
                    if not jv.get("stop") and abs(sd - ghs_d) >= 0.2:
                        ghs_d = max(0.0, min(2.5, sd))
                        print(f"  → 按评委重拉 GHS D={ghs_d}")
                        neb = step("ghs", sep["image"],
                                   params={"D": ghs_d, "HP": 0.9}, tag="r08b_reghs")
                    else:
                        print("  → 评委认为当前拉伸合适,不重拉。")
        except Exception as e:
            print(f"  [GHS评委] 跳过(异常):{e}")
    # 星云主降噪(对齐用户配方 step7):NXT 0.7 + iterations=2 + 色度/频率分离(彩机常开)。
    #   絮状不靠这里压(那样会欠降噪)——真正规避絮状靠后面 r11e 的**旧模型 detail=0 终清**(step9)。
    neb = step("denoise", neb["image"], params={
        "denoise": 0.7, "detail": 0.15, "iterations": 2, "colorSep": True, "denoiseColor": 0.95,
        "freqSep": True, "denoiseLF": 0.6, "denoiseLFColor": 0.9}, tag="r09_dn2")
    # 【暗弱星云揭示】maskstretch:lum 蒙版护亮核 + bgProtect 护暗背景,额外拉伸只作用在
    # 暗弱/中间调 → 把外围淡 Ha、弥漫云气抬起(全局 GHS 提不动的那部分),亮核/暗湾/背景不动。
    # 放在去噪后(不放大原始噪声)、SCNR 前(SCNR 顺带清掉揭示带出的绿)。见铁律 10。
    if reveal:
        neb = step("maskstretch", neb["image"],
                   params={"D": reveal_d, "maskMode": "lum", "smooth": True,
                           "bgProtect": True, "strength": 2.5, "feather": 15,
                           "linear": False}, tag="r09b_reveal")
    neb = step("scnr",   neb["image"], params={"amount": 0.85}, tag="r10_scnr")
    neb = step("curves", neb["image"], params={"saturation": neb_sat}, tag="r11_neb")  # 仅提星云饱和
    # 【局部对比】LHE 只做在亮区(range 蒙版羽化):暗尘细丝/团块更立体,不动背景。见铁律 12 邻域。
    if lhe:
        neb = step("lhe", neb["image"],
                   params={"lowerLimit": 0.30, "amount": 0.5, "radius": 110,
                           "feather": 28, "linear": False}, tag="r11b_lhe")
    # DSE 暗结构强化(可选):深化暗尘/暗带(宽带暗星云、星系尘带受益)。默认关。
    if darkstruct:
        _ds = {"layers": 8, "amount": 0.4, "iterations": 1}
        if isinstance(darkstruct, dict):
            _ds.update(darkstruct)
        neb = step("darkstruct", neb["image"], params={**_ds, "linear": False}, tag="r11c_dse")
        print(f"  <DSE 暗结构强化 {_ds}>")
    # 【调色对齐参考】把星云色调**温和有界**地往 AstroBin 同视场参考配色靠(每通道 ±15%、保总亮度);
    #   只动星云,星点单独走 SPCC 真彩不受影响。有参考(rgb_balance)才做;SPCC 已给绝对色,这里只审美微调。
    #   见 recombine.color_nudge / 记忆 pi-astrobin-reference 第二步。
    if _ref_tg and _ref_tg.get("rgb_balance"):
        try:
            from . import recombine as _recomb
            _cg = R / "r11d_colorgrade.xisf"
            _cgp = R / "r11d_colorgrade.png"
            _recomb.color_nudge(str(neb["image"]), _ref_tg["rgb_balance"], str(_cg),
                                strength=0.5, max_dev=0.15, preview_path=str(_cgp), log=print)
            neb = {"image": _cg, "preview": _cgp}
            print(f"[preview] {_cgp}")
        except Exception as _cge:
            print(f"  [调色] 跳过(异常):{_cge}")
    # 【星云终清·对齐用户配方 step9】NXT **detail=0** 做一道最终降噪 —— 规避 NXT AI v3 的**絮状纹理**
    #   (低信噪素材尤显)。用**旧模型 NoiseXTerminator.2.pb**(v3 絮状真正的解)。实测 NXT 暴露脚本属性
    #   `ai_file`、设定成功(aiFileSet=true)。传**绝对路径**:NXT 的 Select AI 存的是文件路径,裸名未必被
    #   解析到 library;由 PI 安装目录反推(与自动装回同一份文件),取不到/不存在则退回裸名(runner 端仍试)。
    #   detail=0 只平滑平坦区、保边缘,过降噪风险小。见记忆 pi-quality-gate / 用户 M23 手动配方。
    _nxt_old = "NoiseXTerminator.2.pb"
    try:
        import os as _os
        _libdir = config.pixinsight_library_dir()
        if _libdir:
            _full = (_libdir.rstrip("/\\") + "/" + _nxt_old).replace("\\", "/")
            if _os.path.exists(_full):
                _nxt_old = _full
    except Exception:
        pass
    neb = step("denoise", neb["image"],
               params={"denoise": 0.7, "detail": 0.0, "aiFile": _nxt_old,
                       "linear": False}, tag="r11e_finalclean")
    r = neb

    if _reached("color"):
        return _handoff("color", {"nebula_colored": neb["image"]})
    # 可选:极轻合回星点(默认 starless 定稿形态)
    if recombine_stars:
        # 【干净星点·双轨(用户 2026-08-27 定)】传统拉伸(STF shadowClip=-2.8σ)保留大量背景底噪 →
        #   被 SXT 卷进星点层(星点层带絮状脏背景)。改用 **EZ Soft Stretch 式软拉伸**(直方图回归定黑点,
        #   精确卡背景峰脚)对**线性图**单独提星 → 背景干净的星点层。星云仍走传统轨(软拉伸对星云层次不理想,
        #   故只借它提星)。= 退回线性、双 SXT:软拉伸轨出干净星点,传统轨出星云。失败则退回传统轨星点。
        if _lin_for_stars:
            try:
                _softw = step("stretch", _lin_for_stars, params={"mode": "soft"}, tag="r06s_softstr")
                _ssep = step("starsep", _softw["image"], tag="r07s_starsep",
                             extra={"stars": R / "r07s_stars.xisf"})
                _cs = _ssep.get("stars")
                if _cs and Path(str(_cs)).exists():
                    _clean_stars = _cs
                    print("  <干净星点:软拉伸轨 SXT 提星(背景更净,替代传统轨脏星点)>")
            except Exception as _se:
                print(f"  [干净星点] 软拉伸提星失败({_se})→ 退回传统轨星点")
        _stars_in = _clean_stars or sep.get("stars")
        # 【星点增亮(用户 2026-08-27)】软拉伸(medianTarget=0.2)温和 → 星点放星云背景下显单薄。
        #   做法(用户定):**锚点钉住背景 + 曲线提亮星点**——不压低暗部,只在背景/星点分界处打锚点(输出=输入)
        #   钉住背景杂质不被带上去,锚点以上按 star_boost 比例提亮。锚点位置由**数据实测**定:干净 SXT 星点层
        #   经 unscreen 后背景在近黑处(实测 92% 像素<0.02、p95≈0.029)→ 分界取 **0.03**。pointsK(RGB 主曲线)保 SPCC 色。
        #   仅软拉伸干净轨做(它偏暗);脏回退轨本就亮,跳过。star_boost=0.50=提亮50%(离线实测过曝仅 0.02%)。见 [[pi-clean-stars-dualstretch]]。
        if _clean_stars:
            _b = float(star_boost)
            _sk = [[0.0, 0.0], [0.03, 0.03],
                   [0.15, round(0.15 * (1 + _b), 3)],
                   [0.6, round(min(0.98, 0.6 * (1 + _b)), 3)], [1.0, 1.0]]
            _stars_in = step("curves", _stars_in, params={"pointsK": _sk, "linear": False},
                             tag="r11f_starboost")["image"]
            print(f"  <星点增亮:锚点 0.03 钉背景 + 提亮 {int(_b*100)}%(pointsK 保色,不带背景杂质)>")
        # 【星点减补色·净化(用户 2026-09-03)】星点整体偏暖发灰——R+G 过量把真彩 washout 成灰。按"提亮浑浊色
        #   =减其补色饱和"的思路,**轻减 R、G(=相对增蓝)**:黄/蓝各归位、色彩更干净。对齐用户手动配方 Curves[0]
        #   (R 0.137→0.127≈×0.93、G 0.119→0.103≈×0.87,G 减得比 R 多)。低-中调各打一个下拉点,量小("一点点");
        #   高光星核(→1.0)不动,不整体偏色。放在星点处理最前(用户也是第一步做),后续去边纹/提饱和再跟上。
        _rp, _gp = 0.93, 0.87                  # R 保 93% / G 保 87%(用户比例);想更蓝再降,想收手往 1.0 靠
        _stars_in = step("curves", _stars_in, params={
            "pointsR": [[0.0, 0.0], [0.15, round(0.15 * _rp, 4)], [1.0, 1.0]],
            "pointsG": [[0.0, 0.0], [0.15, round(0.15 * _gp, 4)], [1.0, 1.0]],
            "linear": False}, tag="r11g_starneutral")["image"]
        print(f"  <星点减补色净化:低-中调 R×{_rp} / G×{_gp}(相对增蓝、去灰暖底),对齐用户配方>")
        # 【星点色彩矫正·通用(对齐用户 M23 配方)——放在提饱和之前】星点层普遍带**绿边 + 洋红边**
        #   (横向色差、SXT 残留)→ 先清:SCNR 去绿 + depurple 去洋红(= Invert→SCNR→Invert)。**用户对 RGB
        #   也做**,不只智能望远镜。**关键顺序**:SCNR 会削饱和 → 必须**先清边纹、再提饱和**(实测提饱和后再
        #   SCNR 会把 s_star 从 0.286 削到 0.267)。amount:star_scnr>0(智能望远镜)用其值,否则默认 0.8(用户值)。
        _deg = round(float(star_scnr), 3) if (star_scnr and star_scnr > 0) else 0.8
        _stars_in = step("scnr", _stars_in, params={"amount": _deg, "linear": False},
                         tag="r12a_stardegreen")["image"]
        _stars_in = step("scnr", _stars_in, params={"amount": 1.0, "depurple": True, "linear": False},
                         tag="r12b_stardepurple")["image"]
        print(f"  <星点色彩矫正(通用):去绿 SCNR {_deg} + 去洋红 depurple(饱和前,对齐用户配方)>")
        # 星点饱和**自适应判断**(satMean → 目标区)——作为星点处理**最后一步**,保住饱和不被 SCNR 削,
        #   直接进合星。测星点(已清边纹)当前 satMean,不足目标才补;测不到退回 0.3;boost 后复测报实际值。
        #   目标 0.55(用户 2026-09-03 选鲜艳路线 + 要求再拉饱和;W_KNEE=0.015 合星保得住,不易 washout)。
        _star_target = 0.55
        try:
            _sm0 = float(((query("starstats", _stars_in).get("starStats")) or {}).get("satMean") or 0.0)
        except Exception:
            _sm0 = 0.0
        if _sm0 <= 0:
            _sboost = 0.30
        elif _sm0 >= _star_target:
            _sboost = 0.0
        else:
            _sboost = max(0.1, min(0.7, round((_star_target - _sm0) * 2.0 + 0.15, 3)))
        if _sboost > 0.02:
            stw = step("curves", _stars_in, params={"saturation": _sboost}, tag="r12_stars")
            _stars_out = stw["image"]
            try:
                _sm1 = float(((query("starstats", _stars_out).get("starStats")) or {}).get("satMean") or 0.0)
            except Exception:
                _sm1 = _sm0
            print(f"  <星点饱和自适应 satMean {_sm0}→{_sm1}(目标{_star_target},提{_sboost})>")
        else:
            _stars_out = _stars_in
            print(f"  <星点饱和 satMean={_sm0} 已达标(≥{_star_target}),不提>")
        # 蓝色星点补偿(仅 star_blue>0):Dwarf3(IMX678)蓝弱 → 蓝星点"蓝占比"低(实测仅 ~0.355,
        #   中性 0.333)。**量化证实提饱和无效**(饱和不改 B 相对量)→ 改成**提 B 通道拉高蓝占比**,
        #   **按 blueStarBlueFrac 目标自适应**(测→提到目标)。色相蒙版选蓝,只动蓝星点。
        if star_blue and star_blue > 0:
            _blue_target = 0.42
            try:
                _bf0 = float(((query("starstats", _stars_out).get("starStats")) or {}).get("blueStarBlueFrac") or 0.0)
            except Exception:
                _bf0 = 0.0
            _bm = step("huemask", _stars_out, params={"hue": "blue", "mode": "chrominance",
                       "width": 0.18, "blurSigma": 6, "blurTimes": 2}, tag="r12c_bluemask")["image"]
            # B 提升系数:缺口越大提越多(star_blue 作上限缩放);pointsB 抬 B 中调
            _gap = max(0.0, _blue_target - _bf0)
            _blift = min(float(star_blue), round(_gap * 4.0 + 0.15, 3)) if _bf0 > 0 else float(star_blue)
            _bmid = round(min(0.95, 0.5 * (1 + _blift)), 4)
            _stars_out = step("curves", _stars_out, params={
                "pointsB": [[0.0, 0.0], [0.5, _bmid], [1.0, 1.0]],
                "mask": _bm, "linear": False}, tag="r12d_bluesat")["image"]
            try:
                _bf1 = float(((query("starstats", _stars_out).get("starStats")) or {}).get("blueStarBlueFrac") or 0.0)
            except Exception:
                _bf1 = _bf0
            print(f"  <蓝星点增蓝 blueFrac {_bf0}→{_bf1}(目标{_blue_target},提 B 中调→{_bmid};补 Dwarf3 蓝弱)>")
        # 色度保持合星(纯 numpy):亮背景上也保住星点色——screen `1-(1-neb)(1-star)` 会给星点每通道
        #   加一层背景、把星色洗白(M23 实测星蒙版 S 0.53→0.14);缩放法把星原色缩放到 screen 亮度、
        #   保通道比例=保饱和(实测拉回 0.53),背景不动。见 recombine.py / 记忆 pi-quality-gate。
        #   失败(numpy/xisf 异常)优雅退回 PI screen 合星。
        try:
            from . import recombine as _recomb
            _r13 = R / "r13_recomb.xisf"
            _r13p = R / "r13_recomb.png"
            _recomb.chroma_recombine(str(neb["image"]), str(_stars_out), str(_r13),
                                     preview_path=str(_r13p))
            print("  [r13_recomb] recombine(色度保持,保星点色) -> ok")
            print(f"[preview] {_r13p}")            # GUI 嗅探 → 显示阶段图
            r = {"image": _r13, "preview": _r13p, "status": "ok"}
            results["r13_recomb"] = r
        except Exception as _re:
            print(f"  [r13_recomb] 色度保持合星失败({_re})→ 退回 PI screen 合星")
            r = step("recombine", neb["image"], params={"stars": _stars_out}, tag="r13_recomb")

    # 干净背景模式:把背景钉到深黑 + 中性(数值法,不糊细节),消除"奶雾"/残留热梯度
    # (星团钉 0.06 更狠;纯亮场钉 0.09,压住残留但保留一点弥漫过渡)
    if clean_bg:
        # 【别钉死暗尘】星团旧值 0.06 把带尘场的暗尘也压平了(M23 实测棕浆)。抬到 0.09:仍做背景**中性化**
        #   (修 bg_cast 红移)但保留暗尘过渡。frac 保持 0.08 只轻融合。
        r = step("bgneutral", r["image"], params={"target": 0.09, "frac": 0.08},
                 tag="r13b_bgpin")

    # 末尾角落裁切(去掉拉伸后显现的亮边)
    r = step("crop", r["image"], params=CROP, tag="r14_final")

    print(f"\n最终成片: {r.get('image')}")
    print(f"最终预览: {r.get('preview')}")

    # ── 成片质量门(确定性指标 → 回退重跑,仅一次,防振荡)──────────────────────────
    # 评分要能驱动改动、且回退到前序步骤(用户 2026-08-25)。这里在成片上直接测 S_star / 背景中性度,
    # 超出目标带且根因是"该走星团克制却揭示了背景"(cluster 候选 + 背景脏/抬亮/星点被冲淡 + 本轮没克制)
    # → **强制星团克制 cluster=True 回退重跑**(背景钉暗中性 → 背景干净 + 星点合到暗背景保色,
    # M23 实测 S_star 0.165→0.431)。已克制仍不达标则不空转,记录待评委/人工。
    if stop_after == "final" and not _quality_retry:
        try:
            from . import quality
            _sref = _clean_stars or (sep.get("stars") if isinstance(sep, dict) else None)  # 干净星层优先当星蒙版
            q = quality.measure(str(r.get("preview") or r.get("image")),
                                stars=str(_sref) if _sref else None)       # 尺寸不符(裁剪)自动退回检测
            bad = quality.diagnose(q, cluster_target=cluster_candidate, targets=_ref_tg)  # 参考→因目标而异的目标
            results["_quality"] = {"metrics": q, "issues": [b["issue"] for b in bad], "ref_targets": _ref_tg}
            if bad:
                print("[质量门] 指标 " + str(q))
                for b in bad:
                    print(f"  ✗ {b['issue']}({b['metric']}):{b['how']}")
            else:
                print(f"[质量门] 指标达标 {q}")
            _restraint_issues = {"dirty_background", "background_lifted", "dull_stars"}
            if (cluster_candidate and not (cluster_mode or lights_only)
                    and any(b["issue"] in _restraint_issues for b in bad)):
                print("[质量门] → 该走星团克制却揭示了背景 → 强制克制,从头重跑一次(回退前序步骤,非改成片)")
                return run_rgb(input_path, timeout=timeout, ghs_d=ghs_d, neb_sat=neb_sat,
                               recombine_stars=recombine_stars, stretch_judge=stretch_judge,
                               target=target, stretch_refs=stretch_refs, reveal=reveal,
                               reveal_d=reveal_d, lhe=lhe, cluster=True, lights_only=lights_only,
                               darkstruct=darkstruct, colorcal=colorcal, star_scnr=star_scnr,
                               star_blue=star_blue, stop_after=stop_after, export_dir=export_dir,
                               _quality_retry=True)
        except Exception as e:
            print(f"[质量门] 跳过(异常):{e}")
    return results


def run_lrgb(registered_dir: str, timeout: float = 1800.0,
             crop_frac: float = 0.13, neb_sat: float = 0.55,
             maskstretch_iters: int = 2, ghs_d: float = 1.0, core_thr: float = 0.7,
             ha_amount: float = 0.0,
             stop_after: str = "final", export_dir: str | None = None) -> dict[str, Any]:
    """黑白相机 LRGB(H) 全流程(M94 验证配方)。见记忆 pi-mono-lrgb。

    registered_dir: 含各通道子目录(…FILTER-<Luminance/Red/Green/Blue/Ha>_mono/*_c_r.xisf)。
    流程: 各通道 integrate → 每通道 refbg(以 superL 判背景) → rgbcombine + superL
          → 中央裁切 → solve+SPCC(线性) → 拉伸+提饱和 → superL maskstretch(核心保护,揭示外环)
          → 保色 LRGB → 色度降噪 → 可选 Ha 小红花。
    参数: crop_frac 每边裁切比例; neb_sat 星云/星点饱和; maskstretch_iters 外环拉伸迭代数(0=跳过);
          ghs_d/core_thr maskstretch 力度/核心保护阈值; ha_amount>0 时融合 Ha 小红花。
    注意: 卫星轨迹去除(maskline)需人工定位带线单张,本入口不自动做;有轨迹请先手动处理该通道。
    """
    import glob
    from pathlib import Path
    global CANCEL
    CANCEL = False
    R = config.RUN_DIR
    results: dict[str, dict] = {}

    def step(op, inp=None, params=None, tag="", extra=None):
        _ckc()
        outs = {"image": R / f"{tag}.xisf", "preview": R / f"{tag}.png"}
        if extra:
            outs.update(extra)
        job = protocol.new_job(op, input=inp, params=params, outputs=outs)
        protocol.submit(job)
        r = protocol.wait_result(job["job_id"], timeout=timeout)
        results[tag] = r
        st = r.get("status")
        print(f"  [{tag}] {op} -> {st}" + (f" | {r.get('error')}" if r.get("error") else ""))
        _pv = r.get("preview")
        if _pv:
            print(f"[preview] {_pv}")   # GUI 嗅探此标记 → 右侧显示阶段效果图
        if st != "ok":
            raise RuntimeError(f"step {tag}({op}) failed: {r.get('error')}")
        return r

    def query(op, inp, params=None):
        job = protocol.new_job(op, input=inp, params=params)
        protocol.submit(job)
        return protocol.wait_result(job["job_id"], timeout=timeout)

    def chan_subs(filt):
        dirs = glob.glob(str(Path(registered_dir) / f"*FILTER-{filt}*"))
        if not dirs:
            return []
        return sorted(str(p).replace("\\", "/") for p in glob.glob(str(Path(dirs[0]) / "*_c_r.xisf")))

    print("== 黑白 LRGB(H) 管线 ==")
    # 1. 各通道叠加
    masters = {}
    for key, filt in [("L", "Luminance"), ("R", "Red"), ("G", "Green"), ("B", "Blue"), ("Ha", "Ha")]:
        subs = chan_subs(filt)
        if len(subs) >= 3:
            # 逐通道整合原始子帧:默认开去线(卫星/飞机线),≥8 张才开(少帧防误剔)
            ip = {"images": subs, "sigmaLow": 4.0, "sigmaHigh": 2.8}
            if len(subs) >= 8:
                ip.update({"trailReject": True, "trailProtect": 2, "trailGrowth": 2})
            r = step("integrate", params=ip, tag=f"lr_{key}")
            masters[key] = str(r["image"])
            print(f"    {key}: {len(subs)} 张 (去线={'开' if len(subs)>=8 else '关'})")
    for need in ("R", "G", "B"):
        if need not in masters:
            raise RuntimeError(f"缺少 {need} 通道,无法合成 RGB")
    lum_keys = [k for k in ("L", "R", "G", "B") if k in masters]

    _LR_STAGES = ["integrate", "crop_gc", "combine", "colorcal", "stretch", "lrgb", "final"]
    _reached, _handoff = _make_stopper(_LR_STAGES, stop_after, export_dir, results)
    if _reached("integrate"):
        return _handoff("integrate", {f"master_{k}_integrated": masters[k] for k in masters})

    # 2. **先统一裁黑边,再做梯度校正**(铁律:GC/refbg 必须在裁黑边之后——黑边会污染梯度
    #    拟合,导致靠近边缘亮度异常)。多通道须裁同一边距保对齐 → 各通道自动检出取并集+安全边。
    all_keys = [k for k in ("L", "R", "G", "B", "Ha") if k in masters]
    uni = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    for k in all_keys:
        try:
            ap = step("crop", masters[k], params={"linear": True}, tag=f"lr_{k}_edge").get("applied") or {}
            for sd in uni:
                uni[sd] = max(uni[sd], int(ap.get(sd, 0) or 0))
        except RuntimeError as e:
            print(f"    {k} 黑边检测跳过:{e}")
    dims = query("inspect", masters["R"]).get("metrics", {})
    W, H = int(dims.get("width", 0)), int(dims.get("height", 0))
    if W and H:
        uni = {"left": max(uni["left"], int(W*crop_frac)), "right": max(uni["right"], int(W*crop_frac)),
               "top": max(uni["top"], int(H*crop_frac)), "bottom": max(uni["bottom"], int(H*crop_frac))}
    print(f"  == 统一裁黑边(并集+安全边):{uni} ==")
    for k in all_keys:
        masters[k] = step("crop", masters[k], params={"margins": uni, "linear": True},
                          tag=f"lr_{k}_crop")["image"]

    # 3. 裁完才做 refbg 背景匹配(首轮 superL 作参考)
    ref = step("integrate", params={"images": [masters[k] for k in lum_keys]}, tag="lr_superLref")["image"]
    for k in [k for k in ("L", "R", "G", "B") if k in masters]:
        r = step("gradient", masters[k], params={"method": "refbg", "ref": str(ref), "sigma": 120}, tag=f"lr_{k}_rb")
        masters[k] = str(r["image"])

    if _reached("crop_gc"):
        return _handoff("crop_gc", {f"master_{k}": masters[k] for k in masters})

    # 4. RGB 合成 + superL(已裁边,合成后不再裁)
    rgb = step("rgbcombine", params={"r": masters["R"], "g": masters["G"], "b": masters["B"]}, tag="lr_rgb")["image"]
    superl = step("integrate", params={"images": [masters[k] for k in lum_keys]}, tag="lr_superL")["image"]
    margins = None

    if _reached("combine"):
        return _handoff("combine", {"rgb_combined": rgb, "superL": superl})

    # 5. solve + SPCC(线性,合成 superL 前)
    solved = bool(query("checksolve", rgb).get("solveInfo", {}).get("hasSolution"))
    if not solved:
        try:
            rgb = step("solve", rgb, tag="lr_rgb_solve")["image"]
            solved = bool(query("checksolve", rgb).get("solveInfo", {}).get("hasSolution"))
        except RuntimeError as e:
            print(f"  本地解析失败:{e}")
    method = "spcc" if solved else "bncc"
    print(f"  颜色校准: {method}")
    rgb = step("colorcal", rgb, params={"method": method}, tag="lr_cc")["image"]

    if _reached("colorcal"):
        return _handoff("colorcal", {"rgb_calibrated": rgb, "superL": superl})

    # 6. 拉伸彩色 + 提饱和
    rgb = step("stretch", rgb, params={"linked": True, "targetBackground": 0.15}, tag="lr_rgbstr")["image"]
    rgb = step("curves", rgb, params={"saturation": neb_sat}, tag="lr_rgbsat")["image"]

    # 7. 亮度:拉伸 superL,可选核心保护迭代拉伸(揭示外环/暗晕)
    lum = step("stretch", superl, params={"linked": True, "targetBackground": PEAK_BG}, tag="lr_lumstr")["image"]
    for i in range(maskstretch_iters):
        lum = step("maskstretch", lum, params={"D": ghs_d, "HP": 1.0, "coreThr": core_thr, "feather": 12},
                   tag=f"lr_ms{i + 1}")["image"]
    lum = step("denoise", lum, params={"denoise": 0.85, "detail": 0.2, "iterations": 2}, tag="lr_lumdn")["image"]  # 亮度第一次降噪=2

    if _reached("stretch"):
        return _handoff("stretch", {"rgb_stretched": rgb, "lum_stretched": lum})

    # 8. 保色 LRGB → 色度降噪 → 去绿
    out = step("lrgb", rgb, params={"l": str(lum)}, tag="lr_lrgb")["image"]
    out = step("denoise", out, params={"denoise": 0.5, "detail": 0.25, "iterations": 1, "colorSep": True,
                                       "denoiseColor": 0.98, "freqSep": True, "denoiseLF": 0.55,
                                       "denoiseLFColor": 0.95}, tag="lr_cdn")["image"]  # 第二次降噪 iterations=1 + 低频降到 0.55
    if _reached("lrgb"):
        return _handoff("lrgb", {"lrgb_combined": out})
    out = step("scnr", out, params={"amount": 0.7}, tag="lr_scnr")["image"]

    # 9. 可选 Ha 小红花
    if ha_amount > 0 and "Ha" in masters:
        ha_str = step("stretch", masters["Ha"], params={"linked": True, "targetBackground": 0.15}, tag="lr_Hastr")["image"]
        out = step("hablend", out, params={"ha": str(ha_str), "amount": ha_amount}, tag="lr_ha")["image"]

    print(f"\n最终成片: {out}")
    print(f"最终预览: {str(out).replace('.xisf', '.png')}")
    return results


def _sho_classify_dirs(registered_dir):
    """自动把 registered 子目录按 FILTER 标签分到 S/H/O/R/G/B。
    支持:每晚短标签 dNx(末位 h/s/o/r/g/b)或标准名(Ha/SII/S2/OIII/O3/Red/Green/Blue)。
    返回 {chan: [subs...]}(跨晚/多目录合并)。"""
    import re
    from pathlib import Path
    chans = {k: [] for k in ("S", "H", "O", "R", "G", "B")}
    for d in sorted(Path(registered_dir).glob("*")):
        if not d.is_dir():
            continue
        m = re.search(r"FILTER-([^_/\\]+)", d.name, re.I)
        tag = (m.group(1) if m else d.name).lower()
        # 标准名优先
        if "sii" in tag or "s2" in tag: ch = "S"
        elif "oiii" in tag or "o3" in tag: ch = "O"
        elif tag.startswith("ha") or "halpha" in tag: ch = "H"
        elif "red" in tag: ch = "R"
        elif "green" in tag: ch = "G"
        elif "blue" in tag: ch = "B"
        else:
            # 短标签 dNx:取末位字母
            last = re.sub(r"[^a-z]", "", tag)[-1:] if re.sub(r"[^a-z]", "", tag) else ""
            ch = {"s": "S", "h": "H", "o": "O", "r": "R", "g": "G", "b": "B"}.get(last)
        if ch:
            subs = sorted(str(p).replace("\\", "/") for p in d.glob("*.xisf"))
            chans[ch] += subs
    return {k: v for k, v in chans.items() if v}


# 通道目录名 → 通道键。支持:单字母(aligned/ 的 H/O/S/R/G/B)、标准名、每晚短标签 dNx。
_CH_ALIAS = {"h": "H", "ha": "H", "halpha": "H", "o": "O", "oiii": "O", "o3": "O",
             "s": "S", "sii": "S", "s2": "S", "r": "R", "red": "R",
             "g": "G", "green": "G", "b": "B", "blue": "B"}


def _sho_resolve_input(paths) -> dict:
    """把用户给的路径解析成 {chan: [子帧...]}。**固化"找对齐素材"的判断**:

    1. **优先 `aligned/`**:若路径下(或其父目录下)有 `aligned/` 且含通道子目录,用它——
       那是把**多个拍摄目录/多晚统一对齐到同一参考帧**的产物,跨目录整合的正确输入。
    2. 否则用 `registered/`(或路径本身)按 FILTER 标签分类(`_sho_classify_dirs`)。
    3. 传多个目录 → 各自解析后按通道合并,并**告警**:不同目录的 registered 若没共用参考帧
       就没有互相对齐,直接合并会错位(此时应先做跨目录对齐、或改用 aligned/)。
    4. 传项目根目录也行(自动往下找 aligned/ 或 registered/)。
    """
    from pathlib import Path
    if isinstance(paths, (str, Path)):
        paths = [paths]
    paths = [Path(str(p)) for p in paths]

    def scan_chan_dirs(root: Path):
        """root 下若子目录名可映射到通道键,返回 {chan:[xisf...]}。"""
        out = {}
        for d in sorted(root.glob("*")):
            if not d.is_dir():
                continue
            key = _CH_ALIAS.get(d.name.strip().lower())
            if key:
                fs = sorted(str(x).replace("\\", "/") for x in d.glob("*.xisf"))
                if fs:
                    out.setdefault(key, []).extend(fs)
        return out

    def find_aligned(p: Path):
        for cand in (p / "aligned", p.parent / "aligned"):
            if cand.is_dir():
                got = scan_chan_dirs(cand)
                if got:
                    return cand, got
        return None, None

    # 先扫一遍:任一路径能找到 aligned/ 就**只用它**(aligned/ 已含全部已对齐素材,
    # 再合并别的 registered 会重复计入同一批帧)。
    merged, srcs, used_aligned = {}, [], False
    for p in paths:
        al, got = find_aligned(p)
        if got:
            merged, srcs, used_aligned = {}, [f"aligned:{al}"], True
            for k, v in got.items():
                merged.setdefault(k, []).extend(v)
            break
    if used_aligned:
        for k in merged:
            merged[k] = sorted(set(merged[k]))
        print("== 素材解析 ==")
        print(f"    源:{srcs[0]}")
        print("    [OK] 使用 aligned/(跨目录/跨夜统一对齐的产物,已含全部素材,忽略其他路径)")
        return {k: v for k, v in merged.items() if v}

    for p in paths:
        al, got = find_aligned(p)
        if got:
            used_aligned = True
            srcs.append(f"aligned:{al}")
        else:
            reg = p if (p / "..").exists() and any(p.glob("*")) else p
            if (p / "registered").is_dir():
                reg = p / "registered"
            got = scan_chan_dirs(reg) or _sho_classify_dirs(str(reg))
            srcs.append(f"registered:{reg}")
        for k, v in (got or {}).items():
            merged.setdefault(k, []).extend(v)
    for k in merged:
        merged[k] = sorted(set(merged[k]))

    print("== 素材解析 ==")
    for sname in srcs:
        print(f"    源:{sname}")
    if used_aligned:
        print("    [OK] 使用 aligned/(跨目录/跨夜统一对齐的产物)")
    elif len(paths) > 1:
        print("    [WARN] 多个 registered 目录直接合并:仅在它们共用同一参考帧对齐时才正确;"
              "否则请先跨目录对齐(或提供 aligned/)")
    return {k: v for k, v in merged.items() if v}


def _sho_critic(step, query, finals: dict, pal_list: list, results: dict, timeout: float = 600.0):
    """SHO 成片评委:评主版一次 → 客观项自动补救(套用全配色）→ 打分 → 结构化结论。

    返回 {verdict, reason, issues, score:{overall,background,star_color,core,comment},
          auto_fixed:[{issue,how}], needs_attention:[{issue,stage,in_place,knob,how}],
          palette_evaluated} 或 None(评委不可用)。GUI 直接据此展示 + 给"退回哪一步"。
    """
    from . import critic
    if not critic.is_configured():
        print("  [AI评委] 未配置 LLM,跳过评估(不影响成片)")
        return None
    pal0 = pal_list[0]
    out = finals.get(pal0) or {}
    fin_png = out.get("preview")
    if not fin_png:
        return None
    v = critic.critique(fin_png, context=f"SHO 窄带成片(palette={pal0})")
    if v.get("error"):
        print(f"  [AI评委] 不可用:{v['error']}")
        return None
    issues = v.get("issues") or []
    print(f"  [AI评委] verdict={v.get('verdict')} issues={issues}")
    print(f"  [AI评委] {v.get('reason')}")

    # 客观、可无损修的项 → 自动补救。**只做真正安全的**:加裁边缘。
    # 【重要教训 NGC1499】residual_gradient **不再**在成片上自动 GC:成片是彩色非线性、星云铺满
    #   画面,GradientCorrection 会误把星云当背景 → 实测把轻微右下偏红放大成右上发紫/右下发红的
    #   大裂口(铁律11)。残余梯度只能**退回上游逐通道线性重做 GC**,故归入"需你决定"。
    need_crop = "edge_artifact" in issues
    done = set()
    if need_crop:
        print(f"  [评委补救] edge_artifact→加裁边缘(套用到 {len(pal_list)} 个配色版本)")
        for pal in pal_list:
            cur = finals.get(pal)
            if not cur or not cur.get("image"):
                continue
            dd = query("inspect", cur["image"], {"linear": False}).get("metrics", {})
            W2, H2 = int(dd.get("width", 0)), int(dd.get("height", 0))
            if W2 and H2:
                cf = 0.04
                mg = {"left": int(W2 * cf), "right": int(W2 * cf),
                      "top": int(H2 * cf), "bottom": int(H2 * cf)}
                cur = step("crop", cur["image"], params={"margins": mg, "linear": False},
                           tag=f"sho_fix_crop_{pal}")
            finals[pal] = cur
        done.add("edge_artifact")
        results["_finals"] = {k: (x or {}).get("image") for k, x in finals.items()}
        v2 = critic.critique(finals[pal0].get("preview"),
                             context=f"SHO 成片补救后(palette={pal0})")
        if not v2.get("error"):
            print(f"  [AI评委·复评] verdict={v2.get('verdict')} issues={v2.get('issues')}")
            v = v2
            issues = v.get("issues") or []

    # 打分(数值)—— 在(可能已补救的)主版上打,和上面的 issues 同源
    sc = {}
    try:
        sc = critic.score(finals[pal0].get("preview"), context="SHO 窄带成片")
        if sc.get("error"):
            print(f"  [AI评分] 不可用:{sc['error']}"); sc = {}
        else:
            print(f"  [AI评分] {sc.get('overall')}/10 · {sc.get('comment', '')}")
    except Exception as e:
        print(f"  [AI评分] 跳过:{e}")

    plan = critic.remedy_plan(issues, in_place_done=done)
    if plan["auto_fixed"]:
        print("  [已自动修正] " + "; ".join(a["issue"] for a in plan["auto_fixed"]))
    if plan["needs_attention"]:
        print("  [需你决定] " + "; ".join(
            f"{d['issue']}→{'成片可修' if d['in_place'] else '退回「' + d['stage'] + '」'}"
            for d in plan["needs_attention"]))
    return {"verdict": v.get("verdict"), "reason": v.get("reason"), "issues": issues,
            "score": {k: sc.get(k) for k in ("overall", "background", "star_color", "core", "comment")}
                     if sc else {},
            "auto_fixed": plan["auto_fixed"], "needs_attention": plan["needs_attention"],
            "palette_evaluated": pal0}


def run_sho(registered_dir: str, channels: dict | None = None, palette: str = "hss",
            palettes: list[str] | None = None,
            timeout: float = 2400.0, per_chan_denoise: float = 0.5, reveal_d: float = 1.1,   # reveal_d/lmask_amount 已弃用(留作向后兼容)
            tone_faint: float = 0.20, tone_core: float = 0.68, lhe_amount: float = 0.30,
            degreen_target: float = 0.34, dust_patch: bool = False, pause_gate=None,
            lmask_amount: float = 0.5, saturation: float = 0.25, crop_frac: float = 0.06,
            detrail_min_frac: float = 0.10, out_base: str | None = None,
            dust_reveal: bool | None = False, dust_d: float | None = None,
            grade_curve: str | None = None, darkstruct="auto",
            grad_boost: dict | None = None, reuse_integrated: bool = False,
            stop_after: str = "final", export_dir: str | None = None) -> dict[str, Any]:
    """SHO 窄带(星云去星)+ RGB(星点,SPCC真色)合成全流程。固化自 SH2-132 v17 定稿。
    见 skill references/sho-narrowband.md、记忆 pi-sho-narrowband。

    channels: {"S":[subs],"H":[..],"O":[..],"R":[..],"G":[..],"B":[..]};None=按目录 FILTER 标签自动分类。
    palette:  单一配色;palettes: 一次出多版供用户挑(推荐 ["hss","natural","natural_blue","sho"])。
      配色档(NGC1499 定稿,旧的 warm/teal/pink 已废弃):
        "hss"=Ha红 + SII青(层次最好,默认) / "natural"=Ha红 OIII蓝 SII橙(最"真")
        "natural_blue"=洋红加蓝 / "sho"=经典哈勃(自适应去绿 → 金青调 + 黄区加红)
    色调三参数(取代旧的 reveal+lift 叠加):tone_faint/tone_core = 共用扩张曲线的目标锚点;
      lhe_amount = 亮部局部对比。**降亮度请调小 tone_faint,别指望事后压曲线**。
    degreen_target: SHO 档的目标绿占比(星云亮区 greenFrac),力度按实测反解。

    要点(逐条踩坑固化):①各通道先 BXT+线性NXT(≤0.5,别过=塑料)+拉伸到同一 tb 对齐再合成;
    ②去星后揭示 maskstretch(护核)+lmasklift+hdr 压核(core≤~0.85 别爆);③末尾只轻降噪、不 LHE
    (防搓衣板颗粒);④RGB 合成后 BXT(sharpenStars0.3)修圆星点再分星;⑤detrail min_frac 降到 0.15 抓短线。

    grad_boost: {通道:ABE阶数} 给 GC 后仍有残梯度的**指定**通道再压一级 ABE(如 {"S":1});不自动
      全通道(强信号通道边缘星云会被误判为梯度)。reuse_integrated: 复用上轮缓存的整合 master 跳过
      重整合(仅调 grad_boost/调色等下游参数迭代时用,省 ~30min)。

    【默认=暗 moody 克制调(用户 NGC7380 2026-08 定稿,见 [[pi-aesthetic-prefs]])】
      dust_reveal=False(不揭示,外围留暗)、tone_faint=0.20(扩张曲线不抬 faint,外围保持诚实拉伸位、
      不刻意提亮致主体/背景割裂断层)、lhe_amount=0.30(局部对比收着)、degreen_target=0.34(强去绿→金
      Ha+蓝 OIII,不发绿)。要更"揭示"的暗弱结构再显式传 dust_reveal=True/dust_d;要更亮外围调大 tone_faint。
    """
    import glob as _glob
    import shutil as _sh
    from . import detrail as _dt
    global CANCEL
    CANCEL = False
    R = config.RUN_DIR
    results: dict[str, dict] = {}
    # 暂停介入可编辑的目标:各通道**当前** master 路径 {显示名: 路径}。step() 自动维护
    # (合成前各通道独立、就地改能传播到下游);合成后清空(改通道无意义)。
    pause_targets: dict[str, str] = {}

    # 【处理到某一步就交棒】用户可选只跑到某阶段,产物导出到 export_dir 供其手工接管。
    STAGES = ["integrate", "crop_gc", "bxt", "denoise", "stretch", "combine",
              "starless", "color", "final"]
    if stop_after not in STAGES:
        raise RuntimeError(f"stop_after 需为 {STAGES} 之一,收到 {stop_after!r}")
    _stop_idx = STAGES.index(stop_after)

    def _reached(stage: str) -> bool:
        """当前阶段是否已达到用户设定的停止点。"""
        return STAGES.index(stage) >= _stop_idx

    def _handoff(stage: str, files: dict):
        """导出该阶段产物到 export_dir 并打印交棒说明。files={名称: 路径}"""
        import os as _os
        d = export_dir or str(config.RUN_DIR / f"handoff_{stage}")
        d = str(d).replace("\\", "/")
        _os.makedirs(d, exist_ok=True)
        out = {}
        for nm, p in files.items():
            if not p or not _os.path.exists(str(p)):
                continue
            ext = _os.path.splitext(str(p))[1] or ".xisf"
            dst = f"{d}/{nm}{ext}"
            try:
                _sh.copy2(str(p), dst); out[nm] = dst
            except OSError as e:
                print(f"    导出失败 {nm}: {e}")
        print(f"\n== 已按设置停在【{stage}】,产物导出到:{d} ==")
        for nm, p in out.items():
            print(f"    {nm}: {p}")
        print("   (后续步骤由你在 PixInsight 手工接管)")
        results["_handoff"] = {"stage": stage, "dir": d, "files": out}
        return results

    def step(op, inp=None, params=None, tag="", extra=None):
        _ckc()
        outs = {"image": R / f"{tag}.xisf", "preview": R / f"{tag}.png"}
        if extra:
            outs.update(extra)
        job = protocol.new_job(op, input=inp, params=params, outputs=outs)
        protocol.submit(job)
        r = protocol.wait_result(job["job_id"], timeout=timeout)
        results[tag] = r
        st = r.get("status")
        print(f"  [{tag}] {op} -> {st}" + (f" | {r.get('error')}" if r.get("error") else ""))
        _pv = r.get("preview")
        if _pv:
            print(f"[preview] {_pv}")
        if st != "ok":
            raise RuntimeError(f"step {tag}({op}) failed: {r.get('error')}")
        # 【随时暂停介入】每步边界给用户一个介入口:若用户点了暂停,pause_gate 会阻塞,
        # 让其在**当前这张图**上做梯度矫正/灰尘修复(就地覆盖),弄完再放行。无暂停时立即返回。
        # 自动维护"可编辑通道 master"表:tag 形如 sho_S_nxt → 记 {SII: 该通道当前 master}。
        # 这样暂停时能**回到任一通道**修灰尘/梯度(不止当前步),就地改经 combine 前传播。
        # 匹配通道 master:裸整合标签 sho_O(len 5)**和**处理步 sho_O_gc(第 6 位是 _)都登记,
        # 这样整合一完成就能在暂停里选到该通道(不必等到裁剪步)。排除 sho_O_edge —— 那是丢弃用的
        # 黑边检测图,不赋回 raw[k],登记它会导致"选中改了却不向下游传播"。tag[4] 只认大写通道字母,
        # 天然避开 sho_bg / sho_rgb / sho_combine / sho_final 等(它们第 5 位是小写)。
        if (tag[:4] == "sho_" and len(tag) >= 5 and tag[4] in "HOSRGB"
                and (len(tag) == 5 or tag[5] == "_") and not tag.endswith("_edge")):
            try:
                pause_targets[_NM[tag[4]]] = str(r.get("image"))
            except Exception:
                pass
        if tag == "sho_combine":
            pause_targets.clear()          # 合成后改通道无意义
        if pause_gate is not None and r.get("image"):
            try:
                fixed = pause_gate(tag, str(r.get("image")), str(r.get("preview") or ""),
                                   "linear" if any(s in tag for s in
                                                   ("crop", "gc", "bxt", "nxt", "_str")) else "nonlinear",
                                   dict(pause_targets))
                if fixed and fixed[0]:
                    r["image"], r["preview"] = fixed[0], fixed[1]
                    results[tag] = r
            except Exception as _pe:
                print(f"  [暂停介入] 跳过(异常):{_pe}")
        return r

    def query(op, inp, params=None):
        job = protocol.new_job(op, input=inp, params=params)
        protocol.submit(job)
        return protocol.wait_result(job["job_id"], timeout=timeout)

    def detrail_integrate(subs, key):
        """残差检测去短轨迹 → 整帧剔除 → 整合。"""
        import os as _os
        thumb = str(R / f"sho_dt_{key}").replace("\\", "/")
        _os.makedirs(thumb, exist_ok=True)
        job = protocol.new_job("residualset", params={"images": subs, "outDir": thumb, "zoom": 8})
        protocol.submit(job)
        protocol.wait_result(job["job_id"], timeout=timeout)
        det = _dt.detect_trail_frames(thumb, min_frac=detrail_min_frac,
                                      audit_path=str(R / f"sho_dt_{key}_audit.png").replace("\\", "/"))
        keep = [subs[i] for i in range(len(subs)) if i not in det]
        if len(det) / max(1, len(subs)) > 0.25:   # 护栏:带线帧过多不剔
            keep = subs
        print(f"  == {key}: {len(subs)} 张,检出带线 {sorted(det.keys())} → 整合 {len(keep)}")
        ip = {"images": keep, "sigmaLow": 4.0, "sigmaHigh": 2.8}
        if len(keep) >= 8:
            ip.update({"trailReject": True, "trailProtect": 2, "trailGrowth": 2})
        return step("integrate", params=ip, tag=f"sho_{key}")["image"]

    if channels is None:
        channels = _sho_resolve_input(registered_dir)
    print("== SHO 通道分类 ==")
    for k in ("S", "H", "O", "R", "G", "B"):
        print(f"    {k}: {len(channels.get(k, []))} 张")
    for need in ("S", "H", "O"):
        if not channels.get(need):
            raise RuntimeError(f"缺少 {need} 通道,无法合成 SHO")

    # 1) 先把**所有**通道整合出来(含 RGB),再统一裁黑边,**最后**才 GC。
    # 【关键顺序,别再犯】GC(梯度校正)必须在**裁掉黑边之后**做:各通道对齐后常带黑边/暗边,
    # 若先 GC,黑边会污染梯度拟合 → 靠近边缘出现亮度异常(用户 2026-08-04 查过程文件发现)。
    # 且多通道必须**裁同一边距**才保持对齐 → 取各通道自动检出边距的**并集(最大值)**。
    # _NM 提到整合循环之前:step() 闭包在整合步(裸标签 sho_O)就要用它登记暂停目标,
    # 而整合就发生在下面这个循环里(早于原先 _NM 的定义位置),否则登记会 NameError 被吞掉。
    _NM = {"H": "Ha", "O": "OIII", "S": "SII", "R": "Red", "G": "Green", "B": "Blue"}
    raw = {}
    chan_all = [k for k in ("S", "H", "O", "R", "G", "B") if channels.get(k)]
    for k in chan_all:
        # 迭代提速:整合是最慢环节(逐帧残差检测+ImageIntegration,~30min/全栈)。reuse_integrated
        # 时若上一轮的整合 master(sho_<k>.xisf)已在 RUN_DIR,直接复用,只重跑下游(GC/合成/调色)。
        _cached = R / f"sho_{k}.xisf"
        if reuse_integrated and _cached.exists():
            raw[k] = str(_cached).replace("\\", "/")
            print(f"  == {k}: 复用已缓存整合 master {_cached.name} ==")
        else:
            raw[k] = detrail_integrate(channels[k], k)

    # 各通道自动检黑边(crop 不传 margins → detectBordersCoverage 自动测),取并集
    uni = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    for k in chan_all:
        try:
            ap = step("crop", raw[k], params={"linear": True}, tag=f"sho_{k}_edge").get("applied") or {}
            for s in uni:
                uni[s] = max(uni[s], int(ap.get(s, 0) or 0))
        except RuntimeError as e:
            print(f"  {k} 黑边检测跳过:{e}")
    d0 = query("inspect", raw[chan_all[0]], params={"linear": True}).get("metrics", {})
    W0, H0 = int(d0.get("width", 0)), int(d0.get("height", 0))
    # 叠加固定安全边(crop_frac)兜底旋转黑角,并与自动检出取大
    if W0 and H0:
        uni = {"left": max(uni["left"], int(W0*crop_frac)), "right": max(uni["right"], int(W0*crop_frac)),
               "top": max(uni["top"], int(H0*crop_frac)), "bottom": max(uni["bottom"], int(H0*crop_frac))}
    # 交棒点 integrate:只要各通道整合结果(未裁未校)
    if _reached("integrate"):
        return _handoff("integrate", {f"master_{_NM[k]}_integrated": raw[k] for k in chan_all})

    print(f"  == 统一裁黑边(各通道并集+安全边):{uni} ==")
    for k in chan_all:
        raw[k] = step("crop", raw[k], params={"margins": uni, "linear": True}, tag=f"sho_{k}_crop")["image"]
    # 裁完才 GC(此时无黑边污染)—— 六通道都做,便于交棒时全部可用
    for k in chan_all:
        raw[k] = step("gradient", raw[k], params={"method": "GradientCorrection", "linear": True},
                      tag=f"sho_{k}_gc")["image"]
    # 【残余梯度·定向二级压平】grad_boost={"S":1,...}:给指定通道再加一级 ABE(低阶多项式)。
    # 为何**不做自动全通道**:GradientCorrection 偶尔欠校单晚/弱信号通道(实测 NGC7380 的 S 单晚
    # 底部残梯度 → sho 合成里 S→红 → 画面底部发红,用户一眼揪出)。但强信号通道(H)的星云常
    # 铺到画面边缘,任何"边缘背景"自动判据都把边缘星云误当梯度 → 自动 ABE 会误伤(实测 deg1 使
    # H faint −56%)。故只在**评委/用户定位到具体通道**后定向施加;degree 用 1(平面)最稳,
    # 弱信号通道的"faint"本就是被抬起的梯度,压掉正好(实测 S 底-顶差 +0.0078→0,四边收敛)。
    if grad_boost:
        for k, deg in grad_boost.items():
            if k in raw and deg:
                raw[k] = step("gradient", raw[k],
                              params={"method": "abe", "polyDegree": int(deg), "linear": True},
                              tag=f"sho_{k}_gb")["image"]
                print(f"  <{_NM.get(k, k)} 定向梯度压平 ABE deg{deg}>")
    # 【圆形灰尘残影】平场没除净会留下圆斑/甜甜圈,人工平场(flatpatch:羽化圆蒙版+乘性增益)
    # 在**线性态**修最准。但**自动检测默认关闭**(dust_patch=False):灰尘是传感器固定的,对齐后
    # 在各通道位置不同,拉伸预览里星点/星云又有大量"圆形"干扰 → 自动霍夫**误报(误伤星云)+漏检
    # 真环**(NGC1499 实测漏了右侧的环)。可靠做法是 GUI 里**用户点一下那个环**,按点选坐标
    # 对成片做 flatpatch(flatpatch op 给定 x/y/r 即可)。此处的自动分支仅在显式开启时用。
    if dust_patch:
        from . import dustspot as _ds
        for k in chan_all:
            pv = (results.get(f"sho_{k}_gc") or {}).get("preview")
            if not pv:
                continue
            pr0 = (query("lumprobe", raw[k], {"linear": True}).get("probe") or {})
            W0, H0 = pr0.get("width") or 0, pr0.get("height") or 0
            spots = _ds.detect_spots(pv, full_w=W0, full_h=H0)
            if not spots:
                continue
            print(f"  <{_NM[k]} 灰尘残影> {_ds.describe(spots)}")
            for si, sp in enumerate(spots[:3]):
                cur = raw[k]
                for it in range(3):
                    fr = step("flatpatch", cur,
                              params={"x": sp["x"], "y": sp["y"], "r": sp["r"] * 1.15,
                                      "mode": "gain", "linear": True},
                              tag=f"sho_{k}_fp{si}_{it}")
                    cur = fr["image"]
                    g = float((fr.get("applied") or {}).get("gain") or 1.0)
                    if abs(g - 1.0) < 0.03:          # 已经平了
                        break
                raw[k] = cur
    # 交棒点 crop_gc:整合+统一裁边+梯度校正
    if _reached("crop_gc"):
        return _handoff("crop_gc", {f"master_{_NM[k]}": raw[k] for k in chan_all})

    # BXT(六通道都做:窄带校正 PSF、宽带同时修圆星点)
    bxt = {}
    for k in chan_all:
        ss = 0.3 if k in ("R", "G", "B") else 0     # 宽带轻收紧星点,窄带只校正
        bxt[k] = step("deconv", raw[k], params={"sharpenStars": ss, "linear": True},
                      tag=f"sho_{k}_bxt")["image"]
    # 交棒点 bxt:整合+裁边+GC+BXT(= 交给用户手工接管的常用起点)
    if _reached("bxt"):
        return _handoff("bxt", {f"master_{_NM[k]}": bxt[k] for k in chan_all})

    # 线性 NXT(≤0.5)
    dn = {}
    for k in chan_all:
        dn[k] = step("denoise", bxt[k], params={"denoise": per_chan_denoise, "detail": 0.2,
                     "iterations": 2, "linear": True}, tag=f"sho_{k}_nxt")["image"]  # 逐通道首次降噪=2
    if _reached("denoise"):
        return _handoff("denoise", {f"master_{_NM[k]}": dn[k] for k in chan_all})

    # 拉伸到同一 tb 对齐(SHO 三通道)
    m = {}
    for k in ("S", "H", "O"):
        m[k] = step("stretch", dn[k], params={"linked": True, "targetBackground": 0.10},
                    tag=f"sho_{k}_str")["image"]
    if _reached("stretch"):
        return _handoff("stretch", {f"stretched_{_NM[k]}": m[k] for k in ("S", "H", "O")})

    # 2) 合成 SHO(非线性通道,已裁边)→ 去星
    sho = step("rgbcombine", params={"r": m["S"], "g": m["H"], "b": m["O"]}, tag="sho_combine")["image"]
    marg = None      # 已在通道级裁过,合成后不再裁
    if _reached("combine"):
        return _handoff("combine", {"SHO_combined": sho})
    sep = step("starsep", sho, tag="sho_sep", extra={"stars": R / "sho_shostars.xisf"})
    neb = sep["image"]
    if _reached("starless"):
        return _handoff("starless", {"SHO_starless": neb, "SHO_stars": sep.get("stars")})

    # 3) 色调:**一条共用扩张曲线** + 背景蒙版降噪 + lhe 局部对比
    # 【NGC1499 定稿,取代旧的 maskstretch reveal + lmasklift 叠加】
    #  旧路子把中间调整体**抬升**:实测去星合成 faint 0.220 → reveal 0.380 → lift 0.645,
    #  主体动态只剩 0.17 → 亮部一片发平(用户:"亮部被压得完全没有梯度")。
    #  新路子是**扩张**:把 [bg, faint, core] 映射到 [0.10, tf, tc],段内斜率都 >1
    #  (实测 1.76 / 2.32)→ 梯度是被拉开而不是压平,外围淡云同样浮起来。
    #  【铁律】锚点重映射只能往扩张方向用;目标若低于现值就**不做**(压缩会压平中间调,
    #  样条还会在陡段前形成硬边平板),该回上游减小拉伸力度。
    a0 = (query("lumprobe", neb, {"linear": False}).get("probe") or {}).get("anchors") or {}
    _bg0 = float(a0.get("background") or 0.09)
    _f0 = float(a0.get("faint") or 0.22)
    _c0 = float(a0.get("core") or 0.37)
    _tf, _tc = max(tone_faint, _f0), max(tone_core, _c0)
    if _tf <= _f0 + 1e-3 and _tc <= _c0 + 1e-3:
        print(f"  <色调:faint={_f0:.3f} core={_c0:.3f} 已达/超目标 → 不做扩张"
              f"(要降亮度请减小上游 tb/ghs,别在这里压)>")
    else:
        _pts = [[0.0, 0.0], [round(_bg0, 4), 0.10], [round(_f0, 4), round(_tf, 4)],
                [round(_c0, 4), round(_tc, 4)], [1.0, 1.0]]
        _s1 = (_tf - 0.10) / max(1e-4, _f0 - _bg0)
        _s2 = (_tc - _tf) / max(1e-4, _c0 - _f0)
        print(f"  <扩张曲线 {_pts} 斜率 {_s1:.2f}/{_s2:.2f}>")
        neb = step("curves", neb, params={"points": _pts, "linear": False}, tag="sho_expand")["image"]
    # 扩张同时放大了背景噪声 → 只在背景降噪,主体不动(铁律 20)
    a1 = (query("lumprobe", neb, {"linear": False}).get("probe") or {}).get("anchors") or {}
    _lo = round((float(a1.get("faint") or 0.33) + float(a1.get("core") or 0.68)) / 2.0, 3)
    _nm = step("rangemask", neb, params={"lower": _lo, "upper": 1.0, "fuzziness": 0.0,
               "smoothness": 60.5, "lightness": True}, tag="sho_nmask")["image"]
    neb = step("denoise", neb, params={"denoise": 0.6, "detail": 0.15, "iterations": 1, "linear": False,
               "mask": _nm, "maskInverted": True}, tag="sho_dnbg")["image"]  # 后续背景降噪 iterations=1 + 降强度
    # 亮部"有数值梯度但看不出来"是观感问题 → 空间局部处理(铁律 6/12),别再动全局曲线
    if lhe_amount > 0.02:
        neb = step("lhe", neb, params={"radius": 110, "slopeLimit": 1.7, "amount": lhe_amount,
                   "lowerLimit": round(float(a1.get("faint") or 0.33) * 0.85, 3), "feather": 28,
                   "linear": False}, tag="sho_lhe")["image"]
    _v = (query("lumprobe", neb, {"linear": False}).get("probe") or {})
    _va = _v.get("anchors") or {}
    _oe = check_overexposed(_v)
    print(f"  <色调完成 bg={_va.get('background')} faint={_va.get('faint')} core={_va.get('core')}"
          f" 动态={float(_va.get('core') or 0) - float(_va.get('faint') or 0):.3f}"
          f" 过曝={'是 ' + '; '.join(_oe['why']) if _oe['over'] else '否'}>")
    if _oe["over"]:
        print("  [!] 色调后仍判过曝 → 建议减小 tone_faint/tone_core 或上游拉伸力度")

    # 4) 配色:NGC1499 定稿四档。全部基于**同一份色调基底**,只换颜色映射 → 可公平比较。
    #    hss / natural / natural_blue 走 nbcolor(按发射线上色);sho = 经典哈勃 + **自适应去绿**。
    neb_base = step("bgneutral", neb, params={"target": 0.10}, tag="sho_bg")["image"]


    # 【暗尘揭示自动判定】暗尘揭示**不是通用流程**:只有画面里真有显著暗星云(象鼻/尘柱/暗带)
    # 才需要提亮中间调揭层次;没有暗尘的目标做这步就是多余提亮。
    # dust_reveal=None → 让评委看去星星云预览判(has_dust + prominence),按显著度定强度;
    # LLM 不可用则保守跳过并提示用户可手动开。True/False = 用户强制。
    _dust_on, _dust_d = dust_reveal, dust_d
    if _dust_on is None:
        _dust_on = False
        try:
            from . import critic as _cr
            if _cr.is_configured():
                pv = results.get("sho_bg", {}).get("preview")
                dj = _cr.judge_dust(pv, target="", context="SHO 去星星云,判是否需要暗尘层次揭示")
                if dj.get("error"):
                    print(f"  [暗尘判定] 不可用:{dj['error']}(跳过;可传 dust_reveal=True 强制)")
                else:
                    pm = dj.get("prominence")
                    print(f"  [暗尘判定] has_dust={dj.get('has_dust')} prominence={pm} :: {dj.get('reason')}")
                    if dj.get("has_dust") and pm in ("high", "medium", "low"):
                        _dust_on = True
                        if _dust_d is None:
                            _dust_d = {"high": 0.9, "medium": 0.7, "low": 0.45}[pm]
                        print(f"    → 启用暗尘层次揭示(D={_dust_d})")
                    else:
                        print("    → 无显著暗尘,跳过(如需强化可手动开启 dust_reveal=True)")
            else:
                print("  [暗尘判定] 未配置 LLM → 跳过暗尘揭示(可传 dust_reveal=True 强制)")
        except Exception as e:
            print(f"  [暗尘判定] 跳过(异常):{e}")
    if _dust_d is None:
        _dust_d = 0.8

    # 拆回单通道供 nbcolor 上色(SHO 合成是 R=S / G=H / B=O)
    step("chansplit", neb_base, tag="sho_split",
         extra={"r": str(R / "sho_ch_S.xisf").replace("\\", "/"),
                "g": str(R / "sho_ch_H.xisf").replace("\\", "/"),
                "b": str(R / "sho_ch_O.xisf").replace("\\", "/")})
    _CH = {k: str(R / f"sho_ch_{k}.xisf").replace("\\", "/") for k in ("H", "O", "S")}

    def _sig(pth):
        aa = (query("lumprobe", pth, {"linear": False}).get("probe") or {}).get("anchors") or {}
        return max(1e-4, float(aa.get("core") or 0) - float(aa.get("background") or 0))
    _sH, _sO, _sS = _sig(_CH["H"]), _sig(_CH["O"]), _sig(_CH["S"])
    # 弱通道归一到强通道量级时要**限幅**:NGC1499 的 OIII 比 Ha 弱 4 倍,直接归一会把它的噪声
    # 一起放大 → 外围紫雾/绿雾。上限 1.5。
    _nO, _nS = min(1.5, _sH / _sO), min(1.6, _sH / _sS)
    print(f"  <通道信号动态 H={_sH:.3f} O={_sO:.3f} S={_sS:.3f} → 归一增益 O={_nO:.2f} S={_nS:.2f}>")

    # 每档 = (颜色映射, 增益)。颜色是"这条发射线渲染成什么色";增益是它的相对权重。
    PAL_DEF = {
        # Ha=RGB 里那种绯红、OIII=蓝、SII=橙(最"真",适合默认)
        "natural":      ({"h": [1.00, 0.15, 0.25], "o": [0.12, 0.32, 1.00], "s": [1.00, 0.55, 0.12]},
                         {"h": 1.0, "o": _nO * 0.55, "s": _nS * 0.45}),
        # 同上但蓝更多(用户要的"pink 加蓝"),洋红调
        "natural_blue": ({"h": [1.00, 0.14, 0.46], "o": [0.10, 0.28, 1.00], "s": [1.00, 0.52, 0.14]},
                         {"h": 1.0, "o": _nO * 0.75, "s": _nS * 0.45}),
        # HSS:Ha→红、SII→青。SII 增益别高(0.35),否则 Ha 与 SII 同强处 R≈G≈B → 脊发白
        # (数值不过曝但观感像过曝,NGC1499 实测 0.55 就白了)
        "hss":          ({"h": [1.00, 0.00, 0.00], "o": [0, 0, 0], "s": [0.00, 1.00, 1.00]},
                         {"h": 1.0, "o": 0.0, "s": 0.35}),
        # 经典哈勃 SHO:R=SII G=Ha B=OIII,三通道归一;后面走自适应去绿 + 黄区加红
        "sho":          ({"s": [1.00, 0.00, 0.00], "h": [0.00, 1.00, 0.00], "o": [0.00, 0.00, 1.00]},
                         {"h": 1.0, "o": _nO, "s": _nS}),
    }

    def colorize(pal):
        p = f"sho_{pal}"
        key = pal if pal in PAL_DEF else "natural"
        if pal not in PAL_DEF:
            print(f"    [!] 未知配色 {pal!r} → 回退 natural")
        colors, gains = PAL_DEF[key]
        g = {k: round(min(3.0, v), 4) for k, v in gains.items()}
        x = step("nbcolor", params={"h": _CH["H"], "o": _CH["O"], "s": _CH["S"],
                 "colors": colors, "gains": g, "bgOut": 0.10}, tag=f"{p}_mix")["image"]
        # 亮度归一到同一 faint:合成对增益是线性的(减掉基座后)→ **等比缩增益**重算,
        # 不用事后压曲线(压缩会压平中间调)。这样各档亮度一致、可公平比较。
        aa = (query("lumprobe", x, {"linear": False}).get("probe") or {}).get("anchors") or {}
        f_now = float(aa.get("faint") or tone_faint)
        if abs(f_now - tone_faint) > 0.015 and f_now > 0.105:
            sc = (tone_faint - 0.10) / (f_now - 0.10)
            g2 = {k: round(v * sc, 4) for k, v in g.items()}
            print(f"    <{pal} 亮度归一 faint {f_now:.3f}→{tone_faint} 增益×{sc:.3f}>")
            x = step("nbcolor", params={"h": _CH["H"], "o": _CH["O"], "s": _CH["S"],
                     "colors": colors, "gains": g2, "bgOut": 0.10}, tag=f"{p}_mix2")["image"]
        # 【SHO 新思路·idea1(用户 2026-08)】合成上色后**先用 BackgroundNeutralization 做背景色彩校准,
        #   再调星云主体**(去绿/加红/提饱和)。BN=限值法:自动采背景区取 RGB min/max 当 lower/upper 中性化。
        #   x 由去星通道合成(即去星后)→ 契合"去星后校准更准"。背景先中性 → 后续调色不被背景色偏带偏。
        x = step("bn", x, tag=f"{p}_bn")["image"]
        # 【调色分支】grade_curve="henry_sho" → 忠实转录播主 8 通道 SHO 曲线(自带去绿/加红/提饱和),
        #   取代下面的自适应去绿+黄区加红+末尾提饱和(干净 A/B 对比,后续评委微调)。
        _use_henry = (grade_curve == "henry_sho")
        if _use_henry:
            x = step("curves", x, params={**HENRY_SHO_CURVE, "linear": False}, tag=f"{p}_henry")["image"]
            print(f"    <{pal} 调色:Henry SHO 8 通道曲线(忠实转录 .xpsm)>")
        if (not _use_henry) and key == "sho":
            # SHO 是假彩,绿是**分配**给 Ha 的通道而非真实颜色 → 压绿得到主流金青调
            # (与铁律 9"别对真实发射星云常规 SCNR"不冲突)。力度**按实测绿占比反解**,
            # 不写死:NGC1499 标定 a=0→0.500、a=0.60→0.390(认可)、a=0.90→0.345(过头)。
            x, dgi = degreen_adaptive(x, tag=f"{p}_dg", target=degreen_target, timeout=timeout)
            print(f"    <{pal} 自适应去绿 {dgi}>")
            # 黄区加一点红(用户要求):黄色色度蒙版限定,只动黄的部分,背景处曲线恒等
            ab = (query("lumprobe", x, {"linear": False}).get("probe") or {}).get("anchors") or {}
            _b, _m = round(float(ab.get("background") or 0.10), 4), round(float(ab.get("faint") or 0.33), 4)
            ym = step("huemask", x, params={"hue": "yellow", "mode": "chrominance", "width": 0.12,
                      "blurSigma": 15, "blurTimes": 2}, tag=f"{p}_ym")["image"]
            x = step("curves", x, params={
                "pointsR": [[0.0, 0.0], [_b, _b], [_m, round(min(0.98, _m * 1.12), 4)], [1.0, 1.0]],
                "pointsG": [[0.0, 0.0], [_b, _b], [_m, round(_m * 0.96, 4)], [1.0, 1.0]],
                "mask": ym, "linear": False}, tag=f"{p}_red")["image"]
        # 末尾提饱和:**量化标准,不硬套固定值**(用户反馈:natural/HSS 本就够艳,固定 +0.5 反而变差)。
        # 先测星云亮区当前饱和度 S(HSV),只把"不够目标"的部分补上;已达标就不提。saturation(UI)只作上限。
        SAT_TARGET = 0.52          # 鲜明但不溢出的目标饱和(HSV S)
        try:
            _c = (query("lumprobe", x, {"linear": False}).get("probe") or {}).get("color") or {}
            _mx = max(_c.get("R", 0), _c.get("G", 0), _c.get("B", 0))
            _mn = min(_c.get("R", 0), _c.get("G", 0), _c.get("B", 0))
            s_now = (_mx - _mn) / _mx if _mx > 1e-4 else 0.0
        except Exception:
            s_now = 0.0
        if _use_henry or s_now >= SAT_TARGET - 0.03:
            if not _use_henry:
                print(f"    <{pal} 饱和 S={s_now:.2f} ≥ 目标 {SAT_TARGET} → 不提(避免过饱和)>")
        else:
            boost = min(saturation, round((SAT_TARGET - s_now) * 1.1, 3))
            if boost > 0.02:
                print(f"    <{pal} 饱和 S={s_now:.2f} → 目标 {SAT_TARGET},提 {boost}(上限={saturation})>")
                x = step("curves", x, params={"saturation": boost}, tag=f"{p}_sat")["image"]
        # 【暗尘层次揭示】只有画面真有显著暗星云(象鼻/尘柱/暗带)才做,不是通用流程
        if _dust_on:
            x = step("maskstretch", x, params={"D": _dust_d, "maskMode": "lum", "smooth": True,
                     "bgProtect": True, "strength": 2.2, "feather": 15, "linear": False},
                     tag=f"{p}_dust")["image"]
        # DSE 暗结构强化【已确立为默认工作流,2026-08-09 SH2-132 认可;2026-08-10 NGC7380 定稿】:
        #   深化暗尘/暗带、提升立体感。darkstruct="auto"(默认)= **无条件**施加温和 amount0.35
        #   (原先只在 _dust_on 时施加;但揭示默认已关 _dust_on=False,会漏掉 DSE → 改为总施加,
        #   DSE 压暗结构反而助"暗 moody"且对无暗尘目标基本无害);传 dict = 覆盖 amount 等;None/False = 关。
        _ds = None
        if darkstruct == "auto":
            _ds = {"layers": 8, "amount": 0.35, "iterations": 1}
        elif isinstance(darkstruct, dict):
            _ds = {"layers": 8, "amount": 0.35, "iterations": 1}
            _ds.update(darkstruct)
        if _ds:
            x = step("darkstruct", x, params={**_ds, "linear": False}, tag=f"{p}_dse")["image"]
            print(f"    <{pal} DSE 暗结构强化 {_ds}>")
        return step("bgneutral", x, params={"target": 0.10}, tag=f"{p}_final")["image"]

    pal_list = palettes if palettes else [palette]
    neb_by_pal = {}
    for pal in pal_list:
        print(f"  == 配色 {pal} ==")
        neb_by_pal[pal] = colorize(pal)
    neb = neb_by_pal[pal_list[0]]   # 主版(用于评委/后续)
    if _reached("color"):
        return _handoff("color", {f"nebula_{p}": neb_by_pal[p] for p in pal_list})

    # 5) RGB 星点:合成 → BXT 修圆星点 → 降噪 → 解析+SPCC → 拉伸 → 分星
    stars = None
    if channels.get("R") and channels.get("G") and channels.get("B"):
        # 复用上面已整合+统一裁边+GC+BXT 的宽带通道(顺序:裁→GC→BXT,已在前面统一做过)
        rm = {k: bxt[k] for k in ("R", "G", "B")}
        rgb = step("rgbcombine", params={"r": rm["R"], "g": rm["G"], "b": rm["B"]}, tag="sho_rgb")["image"]
        rgb = step("denoise", rgb, params={"denoise": 0.6, "detail": 0.15, "iterations": 1, "linear": True}, tag="sho_rgb_nxt")["image"]
        if marg:
            rgb = step("crop", rgb, params={"margins": marg, "linear": True}, tag="sho_rgb_crop")["image"]
        solved = bool(query("checksolve", rgb).get("solveInfo", {}).get("hasSolution"))
        if not solved:
            try:
                rgb = step("solve", rgb, tag="sho_rgb_solve")["image"]
                solved = bool(query("checksolve", rgb).get("solveInfo", {}).get("hasSolution"))
            except RuntimeError as e:
                print(f"  RGB 解析失败:{e}")
        meth = "spcc" if solved else "bncc"
        print(f"  RGB 颜色校准:{meth}")
        rgb = step("colorcal", rgb, params={"method": meth}, tag="sho_rgb_cc")["image"]
        rgb = step("stretch", rgb, params={"linked": True, "targetBackground": 0.12}, tag="sho_rgb_str")["image"]
        rsep = step("starsep", rgb, tag="sho_rgb_sep", extra={"stars": R / "sho_rgbstars.xisf"})
        stars = step("curves", rsep.get("stars"), params={"saturation": 0.3}, tag="sho_stars")["image"]
    else:
        # 【SHO 新思路·idea2(用户 2026-08)】无 RGB 通道 → 不再输出 starless,用 SHO 星点**转色**
        #   近似还原 RGB 星色:R=H, G=0.5H+0.5O, B=O。SHO 星点图通道为 R:S / G:H / B:O
        #   (合成时 r=S,g=H,b=O)→ chanmix 映射矩阵:Rout=G(H)、Gout=0.5G+0.5B(½H+½O)、Bout=B(O)。
        shostars = sep.get("stars")
        if shostars:
            _sc = step("chanmix", str(shostars),
                       params={"matrix": [[0, 1, 0], [0, 0.5, 0.5], [0, 0, 1]]},
                       tag="sho_starcolor")["image"]
            stars = step("curves", _sc, params={"saturation": 0.3}, tag="sho_stars")["image"]
            print("  无 RGB 通道 → 用 H/O 转色合成星点色(R=H, G=½H+½O, B=O)")
        else:
            print("  无 RGB 通道且无 SHO 星点 → 输出 starless")

    # 6) 合成星云 + 星点:每个配色各出一版成片(sho_final_<pal>),主版=第一个
    # 【合星过曝防护】星云核心区星点极密,screen 合星会把星点亮度叠上去 → 核心视觉过曝
    #   (SH2-132 实测:星云 core 0.64 → 合星后 0.98;星点图自身 core 0.98 已近饱和)。
    #   故合星前按需**压星点亮度**(curves 线性缩放),不动星云。
    if stars:
        sc_core = ((query("lumprobe", str(stars), {"linear": False}).get("probe") or {})
                   .get("anchors", {}) or {}).get("core") or 0.0
        nb_core = ((query("lumprobe", neb_by_pal[pal_list[0]], {"linear": False}).get("probe") or {})
                   .get("anchors", {}) or {}).get("core") or 0.0
        # 星点亮 + 星云已亮 → 压得多;都不亮则不压
        k_star = 1.0
        if sc_core > 0.85 and nb_core > 0.55:
            k_star = 0.6
        elif sc_core > 0.85 or nb_core > 0.70:
            k_star = 0.75
        print(f"  <合星防护 星点core={sc_core:.3f} 星云core={nb_core:.3f} → 星点×{k_star}>")
        if k_star < 0.99:
            stars = step("curves", str(stars), params={"points": [[0.0, 0.0], [1.0, k_star]],
                         "linear": False}, tag="sho_stars_dim")["image"]
    finals = {}
    for pal in pal_list:
        if stars:
            finals[pal] = step("recombine", neb_by_pal[pal], params={"stars": str(stars)},
                               tag=f"sho_final_{pal}")
        else:
            finals[pal] = results.get(f"sho_{pal}_final")
    results["_finals"] = {k: (v or {}).get("image") for k, v in finals.items()}
    out = finals[pal_list[0]]
    if len(pal_list) > 1:
        print("  == 多配色成片 ==")
        for k, v in finals.items():
            print(f"    {k}: {(v or {}).get('image')}")

    # 7) AI 评委:对**主版成片**做一次评估 + 打分,并把结论结构化(含"该退回哪一步")。
    #    只评主版一次(多配色瑕疵同源);客观项自动补救并**套用到所有配色版本**,主观/不可逆项
    #    只报告并给出回退阶段(铁律 8)。结构化结果存 res["_critic"],由 GUI 直接展示——
    #    不再让 Worker 另调一次 score(),避免"两个评委各说各话"(用户反馈的困惑点)。
    _c = _sho_critic(step, query, finals, pal_list, results, timeout=timeout)
    if _c:
        results["_critic"] = _c
    out = finals[pal_list[0]]           # 补救可能替换了主版 → 重取

    print(f"\n最终成片: {out.get('image')}")
    return results


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="P1 固定管线")
    parser.add_argument("--input", required=True, help="线性主图路径 (XISF/FITS)")
    parser.add_argument("--no-crop", action="store_true", help="跳过裁黑边")
    parser.add_argument("--hoo", action="store_true", help="运行 OSC 双窄带 HOO 全流程")
    parser.add_argument("--rgb", action="store_true", help="运行宽带 RGB 真实色全流程")
    parser.add_argument("--lrgb", action="store_true",
                        help="运行黑白 LRGB(H) 全流程(--input 传 registered 目录)")
    parser.add_argument("--ha", type=float, default=0.0, help="LRGB: Ha 小红花强度(>0 启用)")
    parser.add_argument("--ms-iters", type=int, default=2, help="LRGB: superL 核心保护迭代拉伸次数")
    parser.add_argument("--core-thr", type=float, default=0.7, help="LRGB: maskstretch 核心保护阈值")
    parser.add_argument("--crop-frac", type=float, default=0.13, help="LRGB: 每边中央裁切比例")
    parser.add_argument("--ghs-d", type=float, default=0.5,
                        help="RGB: GHS 星云提亮力度 D(默认 0.5;发射星云/高SNR可调大 0.8~1.2)")
    parser.add_argument("--neb-sat", type=float, default=0.15,
                        help="RGB: 星云饱和提升(默认 0.15)")
    parser.add_argument("--stars", action="store_true",
                        help="RGB: 极轻合回星点(默认 starless)")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)

    config.ensure_dirs()

    if protocol.runner_alive():
        print("[✓] runner 在线。")
    else:
        print("[!] 未检测到 runner 心跳,请先在 PixInsight 运行 job-runner.js。")

    if args.hoo or args.rgb or args.lrgb:
        try:
            inp = args.input.replace("\\", "/")
            if args.hoo:
                run_hoo(inp, timeout=args.timeout)
            elif args.lrgb:
                run_lrgb(inp, timeout=max(args.timeout, 1800.0), crop_frac=args.crop_frac,
                         neb_sat=args.neb_sat, maskstretch_iters=args.ms_iters,
                         ghs_d=args.ghs_d, core_thr=args.core_thr, ha_amount=args.ha)
            else:
                run_rgb(inp, timeout=args.timeout, ghs_d=args.ghs_d,
                        neb_sat=args.neb_sat, recombine_stars=args.stars)
            return 0
        except RuntimeError as e:
            print(f"\n[✗] {e}")
            return 2

    # 基线:先看一眼原始输入
    print("\n===== 基线(原始输入)=====")
    base = run_step("inspect", args.input.replace("\\", "/"),
                    tag="p1_00_input", timeout=args.timeout)
    _summarize(-1, "inspect(input)", base)
    if base.get("status") != "ok":
        print("\n[✗] 无法读取输入,终止。")
        return 1

    # 固定管线:裁黑边 → 梯度校正 → 拉伸
    steps: list[tuple[str, dict]] = []
    if not args.no_crop:
        steps.append(("crop", {}))
    steps += [("gradient", {}), ("stretch", {})]

    print("\n===== 运行管线 =====")
    results = run_pipeline(args.input.replace("\\", "/"), steps,
                           timeout=args.timeout, on_step=_summarize)

    ok = all(r.get("status") == "ok" for r in results) and bool(results)
    print("\n" + ("[✓] 管线完成。" if ok else "[✗] 管线中断,见上面的 error。"))
    if ok and results:
        final = results[-1]
        print(f"最终成片(非线性): {final.get('image')}")
        print(f"最终预览: {final.get('preview')}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
