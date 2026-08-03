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
from typing import Any, Callable

from . import config, protocol

# 中止标志:GUI 中止按钮置 True;各流程 step() 在提交每步前检查,置位则抛出中止。
CANCEL = False


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

    args = ["automationMode=true"]
    exp_lights = 0
    for n in raw["nights"]:
        args.append("dir=%s|%s" % (n["light"].replace("\\", "/"), n["tag"]))
        args.append("dir=%s|%s" % (n["flat"].replace("\\", "/"), n["tag"]))
        exp_lights += _fits(n["light"])
    args.append("dir=" + raw["dark"].replace("\\", "/"))
    args.append("dir=" + raw["bias"].replace("\\", "/"))
    args.append("outputDirectory=" + out)
    args += ["integrate=false", "platesolve=false", "debayerOutputMethod=0"]
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
    print("== 自定义滤镜法 WBPP:%d 晚, 预计 %d 张光场 → %s ==" % (len(raw["nights"]), exp_lights, out))
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


def run_hoo(input_path: str, timeout: float = 600.0) -> dict[str, Any]:
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
    r = step("crop",     input_path,   tag="h00_crop")
    r = step("gradient", r["image"],   tag="h01_grad")
    r = step("deconv",   r["image"],   params={"sharpenStars": 0}, tag="h02_deconv")  # 不缩星
    r = step("hoo",      r["image"],   tag="h03_hoo")
    hoo_linear = r["image"]            # 全图线性 HOO,用于策略2的 STF 参考
    sep = step("starsep", hoo_linear,  tag="h04_starsep", stars_out=True)
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
                max_drop_frac: float = 0.25, zoom: int = 8,
                min_frac: float = 0.30) -> dict:
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
    if frac > max_drop_frac:
        print(f"  ⚠ 超过丢帧护栏 {max_drop_frac:.0%},为保信噪不自动剔除,保留全部帧。")
        return {"all": subs, "trail_idx": trail_idx, "keep": subs, "dropped": [],
                "audit": audit, "skipped": True}
    print(f"  → 整帧剔除 {len(dropped)} 张,保留 {len(keep)} 张整合。")
    return {"all": subs, "trail_idx": trail_idx, "keep": keep, "dropped": dropped,
            "audit": audit, "skipped": False}


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
            lhe: bool = True, cluster: bool | None = None) -> dict[str, Any]:
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

    # 角落敏感裁切参数(暗边+叠加亮边都裁,分段抓角落)
    CROP = {"segments": 6, "brightFrac": 2.5, "extraMargin": 8}

    print("== 宽带 RGB 管线(顺滑配方)==")
    # ---- 线性阶段 ----
    r = step("crop",     input_path,  params=CROP, tag="r00_crop")   # 先裁,免边缘污染统计
    r = step("gradient", r["image"],  params={"method": "GradientCorrection"}, tag="r01_gc")
    r = step("deconv",   r["image"],  params={"sharpenStars": 0}, tag="r02_deconv")  # BXT 不缩星
    # 颜色校准自适应:优先 SPCC(需解析)→ 本地 ImageSolver → 回退 BN+CC。
    solved = bool(query("checksolve", r["image"]).get("solveInfo", {}).get("hasSolution"))
    if not solved:
        print("  无天文解析,尝试本地 ImageSolver…")
        try:
            r = step("solve", r["image"], tag="r02b_solve")
            solved = bool(query("checksolve", r["image"]).get("solveInfo", {}).get("hasSolution"))
        except RuntimeError as e:
            print(f"  本地解析失败:{e}(TODO: astrometry.net 兜底)")
    method = "spcc" if solved else "bncc"
    print(f"  颜色校准: {method}(天文解析={solved})")
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
    r = step("colorcal", r["image"],  params={"method": method}, tag="r03_colorcal")
    r = step("gradient", r["image"],  params={"method": "abe", "polyDegree": 4}, tag="r04_abe")  # 压平梯度
    # 线性强降噪(压亮度噪声,GHS 前)
    r = step("denoise",  r["image"],  params={"denoise": 0.90, "detail": 0.10}, tag="r05_dn")
    # ---- 目标分类第二级:星团候选 → LLM 看画面有无"较大面积暗云/星云"值得保留 ----
    # 类型是星团 ≠ 画面一定空(如 M45 裹反射星云、银河球团压暗云带)→ 有大面积暗云/星云则退回正常。
    cluster_mode = cluster if cluster is not None else False
    if cluster is None and cluster_candidate:
        cluster_mode = True   # 默认克制,除非场判发现有延展结构
        try:
            from . import critic
            if all(critic._llm_config()[:3]):
                pv = step("inspect", r["image"], params={"linear": True},
                          tag="r05p_field").get("preview")
                fe = critic.judge_field_extended(pv, target=cluster_name,
                                                 context="星团背景钉黑门控:有大面积暗云/星云则不钉黑")
                if fe.get("error"):
                    print(f"  [场判] 不可用:{fe['error']}(按类型走克制)")
                else:
                    print(f"  [场判] has_extended={fe.get('has_extended')} "
                          f"kind={fe.get('kind')} :: {fe.get('reason')}")
                    if fe.get("has_extended"):
                        cluster_mode = False
                        print("  → 画面有较大面积暗云/星云,退回正常处理(保背景、照常揭示)")
            else:
                print("  [场判] 未配置 LLM,按类型走克制。")
        except Exception as e:
            print(f"  [场判] 跳过(异常):{e}")
    if cluster_mode:
        reveal = lhe = stretch_judge = False
        print("  → 星团克制模式:不揭示背景 / GHS 不自动加大 / 背景钉深黑")
    # ---- 拉伸 → 分离星点 ----
    tb = 0.06 if cluster_mode else 0.12   # 星团:背景目标压低,别把空背景拉亮
    r = step("stretch",  r["image"],  params={"linked": True, "targetBackground": tb}, tag="r06_str")
    sep = step("starsep", r["image"], tag="r07_sep", extra={"stars": R / "r07_stars.xisf"})
    # ---- 星云(starless)后期 ----
    neb = step("ghs",    sep["image"], params={"D": ghs_d, "HP": 0.9}, tag="r08_ghs")
    # 【拉伸力度自检闭环】GHS 后让评委(judge_ghs)对照判 D:偏离当前且非 stop 就按建议
    # 重拉一次(仅一次,防振荡)。对低面亮度弥散星云(如 NGC7000),固定 ghs_d 常偏保守 →
    # 评委报 too_dark、给更大 D。可选喂 AstroBin 同视场参考(stretch_refs)让判断更准。
    if stretch_judge:
        try:
            from . import critic
            if all(critic._llm_config()[:3]):     # provider/model/key 齐备才判
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
    # GHS 后二次降噪:带色度+低频,专抹斑驳/紫斑(先清杂色,后面提饱和才不返噪)
    neb = step("denoise", neb["image"], params={
        "denoise": 0.75, "detail": 0.15, "colorSep": True, "denoiseColor": 0.95,
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
    r = neb

    # 可选:极轻合回星点(默认 starless 定稿形态)
    if recombine_stars:
        stw = step("curves", sep.get("stars"), params={"saturation": 0.3}, tag="r12_stars")
        r = step("recombine", neb["image"], params={"stars": stw["image"]}, tag="r13_recomb")

    # 星团:把背景钉到深黑 + 中性(数值法,不糊细节),彻底消除"奶雾"背景
    if cluster_mode:
        r = step("bgneutral", r["image"], params={"target": 0.06, "frac": 0.08},
                 tag="r13b_bgpin")

    # 末尾角落裁切(去掉拉伸后显现的亮边)
    r = step("crop", r["image"], params=CROP, tag="r14_final")

    print(f"\n最终成片: {r.get('image')}")
    print(f"最终预览: {r.get('preview')}")
    return results


def run_lrgb(registered_dir: str, timeout: float = 1800.0,
             crop_frac: float = 0.13, neb_sat: float = 0.55,
             maskstretch_iters: int = 2, ghs_d: float = 1.0, core_thr: float = 0.7,
             ha_amount: float = 0.0) -> dict[str, Any]:
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

    # 2. 首轮 superL 作背景参考 → 每通道 refbg
    ref = step("integrate", params={"images": [masters[k] for k in lum_keys]}, tag="lr_superLref")["image"]
    for k in [k for k in ("L", "R", "G", "B") if k in masters]:
        r = step("gradient", masters[k], params={"method": "refbg", "ref": str(ref), "sigma": 120}, tag=f"lr_{k}_rb")
        masters[k] = str(r["image"])

    # 3. RGB 合成 + superL
    rgb = step("rgbcombine", params={"r": masters["R"], "g": masters["G"], "b": masters["B"]}, tag="lr_rgb")["image"]
    superl = step("integrate", params={"images": [masters[k] for k in lum_keys]}, tag="lr_superL")["image"]

    # 4. 中央裁切(去旋转黑边;同 margins 保对齐)。用首张通道尺寸算边距。
    dims = query("inspect", masters["R"]).get("metrics", {})
    W, H = int(dims.get("width", 0)), int(dims.get("height", 0))
    margins = {"left": int(W * crop_frac), "right": int(W * crop_frac),
               "top": int(H * crop_frac), "bottom": int(H * crop_frac)} if W and H else None
    if margins:
        rgb = step("crop", rgb, params={"margins": margins, "linear": True}, tag="lr_rgbc")["image"]
        superl = step("crop", superl, params={"margins": margins, "linear": True}, tag="lr_superLc")["image"]
        if "Ha" in masters:
            masters["Ha"] = step("crop", masters["Ha"], params={"margins": margins, "linear": True}, tag="lr_Hac")["image"]

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

    # 6. 拉伸彩色 + 提饱和
    rgb = step("stretch", rgb, params={"linked": True, "targetBackground": 0.15}, tag="lr_rgbstr")["image"]
    rgb = step("curves", rgb, params={"saturation": neb_sat}, tag="lr_rgbsat")["image"]

    # 7. 亮度:拉伸 superL,可选核心保护迭代拉伸(揭示外环/暗晕)
    lum = step("stretch", superl, params={"linked": True, "targetBackground": 0.12}, tag="lr_lumstr")["image"]
    for i in range(maskstretch_iters):
        lum = step("maskstretch", lum, params={"D": ghs_d, "HP": 1.0, "coreThr": core_thr, "feather": 12},
                   tag=f"lr_ms{i + 1}")["image"]
    lum = step("denoise", lum, params={"denoise": 0.85, "detail": 0.2}, tag="lr_lumdn")["image"]

    # 8. 保色 LRGB → 色度降噪 → 去绿
    out = step("lrgb", rgb, params={"l": str(lum)}, tag="lr_lrgb")["image"]
    out = step("denoise", out, params={"denoise": 0.5, "detail": 0.25, "colorSep": True, "denoiseColor": 0.98,
                                       "freqSep": True, "denoiseLF": 0.7, "denoiseLFColor": 0.95}, tag="lr_cdn")["image"]
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


def run_sho(registered_dir: str, channels: dict | None = None, palette: str = "warm",
            timeout: float = 2400.0, per_chan_denoise: float = 0.5, reveal_d: float = 1.1,
            lmask_amount: float = 0.5, saturation: float = 0.5, crop_frac: float = 0.06,
            detrail_min_frac: float = 0.10, out_base: str | None = None) -> dict[str, Any]:
    """SHO 窄带(星云去星)+ RGB(星点,SPCC真色)合成全流程。固化自 SH2-132 v17 定稿。
    见 skill references/sho-narrowband.md、记忆 pi-sho-narrowband。

    channels: {"S":[subs],"H":[..],"O":[..],"R":[..],"G":[..],"B":[..]};None=按目录 FILTER 标签自动分类。
    palette:  "warm"(暖金红:去绿+redemph 保 OIII 蓝体) / "teal"(经典青金:轻去绿+饱和)。

    要点(逐条踩坑固化):①各通道先 BXT+线性NXT(≤0.5,别过=塑料)+拉伸到同一 tb 对齐再合成;
    ②去星后揭示 maskstretch(护核)+lmasklift+hdr 压核(core≤~0.85 别爆);③末尾只轻降噪、不 LHE
    (防搓衣板颗粒);④RGB 合成后 BXT(sharpenStars0.3)修圆星点再分星;⑤detrail min_frac 降到 0.15 抓短线。
    """
    import glob as _glob
    from . import detrail as _dt
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
            print(f"[preview] {_pv}")
        if st != "ok":
            raise RuntimeError(f"step {tag}({op}) failed: {r.get('error')}")
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
        channels = _sho_classify_dirs(registered_dir)
    print("== SHO 通道分类 ==")
    for k in ("S", "H", "O", "R", "G", "B"):
        print(f"    {k}: {len(channels.get(k, []))} 张")
    for need in ("S", "H", "O"):
        if not channels.get(need):
            raise RuntimeError(f"缺少 {need} 通道,无法合成 SHO")

    # 1) SHO 各通道:detrail整合 → GC → BXT(不缩星) → 线性 NXT(≤0.5) → 拉伸到同一 tb 对齐
    m = {}
    for k in ("S", "H", "O"):
        x = detrail_integrate(channels[k], k)
        x = step("gradient", x, params={"method": "GradientCorrection", "linear": True}, tag=f"sho_{k}_gc")["image"]
        x = step("deconv", x, params={"sharpenStars": 0, "linear": True}, tag=f"sho_{k}_bxt")["image"]
        x = step("denoise", x, params={"denoise": per_chan_denoise, "detail": 0.2, "linear": True}, tag=f"sho_{k}_nxt")["image"]
        x = step("stretch", x, params={"linked": True, "targetBackground": 0.10}, tag=f"sho_{k}_str")["image"]
        m[k] = x

    # 2) 合成 SHO(非线性通道)→ 裁 → 去星
    sho = step("rgbcombine", params={"r": m["S"], "g": m["H"], "b": m["O"]}, tag="sho_combine")["image"]
    d = query("inspect", sho, params={"linear": False}).get("metrics", {})
    W, H = int(d.get("width", 0)), int(d.get("height", 0))
    marg = {"left": int(W*crop_frac), "right": int(W*crop_frac),
            "top": int(H*crop_frac), "bottom": int(H*crop_frac)} if W and H else None
    if marg:
        sho = step("crop", sho, params={"margins": marg, "linear": False}, tag="sho_crop")["image"]
    sep = step("starsep", sho, tag="sho_sep", extra={"stars": R / "sho_shostars.xisf"})
    neb = sep["image"]

    # 3) 揭示(护核)+ hdr 压核防爆 → 末尾轻降噪、不 LHE(防颗粒/涂抹)
    # 【自适应,防亮目标过曝】先测去星核心:亮目标(core 起点已高,如 M17)自动调轻揭示,
    # 否则暗目标(如 SH2-132 core0.33)才用足力度。否则固定参数会把亮核冲爆(M17 教训)。
    c0 = (query("lumprobe", neb, {"linear": False}).get("probe", {}).get("anchors", {})).get("core") or 0.3
    lmh = 0.45
    use_hdr = True
    if c0 >= 0.55:                     # 亮目标(M17):调轻揭示 + hdr 压核防爆
        rd, la = reveal_d * 0.3, min(lmask_amount, 0.12)
    elif c0 >= 0.38:                   # 中等
        rd, la = reveal_d * 0.55, min(lmask_amount, 0.3)
    else:                              # 暗目标(SH2-132):更激进揭示 + 跳过 hdr(hdr 只会压暗)
        rd, la, lmh, use_hdr = reveal_d * 1.3, min(lmask_amount * 1.4, 0.7), 0.35, False
    print(f"  <去星核心 core={c0:.3f} → 自适应揭示 D={rd:.2f} lmask={la:.2f} hdr={use_hdr}>")
    if rd > 0.05:
        neb = step("maskstretch", neb, params={"D": rd, "maskMode": "lum", "smooth": True,
                   "bgProtect": True, "strength": 1.6, "feather": 15, "linear": False}, tag="sho_reveal")["image"]
    if la > 0.02:
        neb = step("lmasklift", neb, params={"amount": la, "low": 0.06, "high": lmh}, tag="sho_lift")["image"]
    if use_hdr:
        neb = step("hdr", neb, params={"layers": 6}, tag="sho_hdr")["image"]
    v = query("lumprobe", neb, {"linear": False}).get("probe", {}).get("anchors", {})
    print(f"  <揭示后 core={v.get('core')} faint={v.get('faint')} bg={v.get('background')}>")
    neb = step("denoise", neb, params={"denoise": 0.35, "detail": 0.25, "colorSep": True, "denoiseColor": 0.85,
               "freqSep": True, "denoiseLF": 0.35, "denoiseLFColor": 0.8}, tag="sho_dn")["image"]

    # 4) 调色:背景中性 + 配色预设
    neb = step("bgneutral", neb, params={"target": 0.10}, tag="sho_bg")["image"]
    if palette == "teal":
        neb = step("scnr", neb, params={"amount": 0.5}, tag="sho_scnr")["image"]
        neb = step("curves", neb, params={"saturation": saturation}, tag="sho_sat")["image"]
    else:   # warm(暖金红,保 OIII 蓝体);Ha 强目标(M17)需更强去绿,0.85 才不留绿铸
        neb = step("scnr", neb, params={"amount": 0.85}, tag="sho_scnr")["image"]
        neb = step("redemph", neb, params={"amount": 0.5, "ciel": True}, tag="sho_red")["image"]
        neb = step("curves", neb, params={"saturation": saturation}, tag="sho_sat")["image"]
    neb = step("bgneutral", neb, params={"target": 0.10}, tag="sho_bg2")["image"]

    # 5) RGB 星点:合成 → BXT 修圆星点 → 降噪 → 解析+SPCC → 拉伸 → 分星
    stars = None
    if channels.get("R") and channels.get("G") and channels.get("B"):
        rm = {}
        for k in ("R", "G", "B"):
            x = detrail_integrate(channels[k], k)
            rm[k] = step("gradient", x, params={"method": "GradientCorrection", "linear": True}, tag=f"sho_{k}_gc")["image"]
        rgb = step("rgbcombine", params={"r": rm["R"], "g": rm["G"], "b": rm["B"]}, tag="sho_rgb")["image"]
        rgb = step("deconv", rgb, params={"sharpenStars": 0.3, "linear": True}, tag="sho_rgb_bxt")["image"]
        rgb = step("denoise", rgb, params={"denoise": 0.6, "detail": 0.15, "linear": True}, tag="sho_rgb_nxt")["image"]
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
        print("  无完整 RGB 通道,跳过星点合成(输出 starless)")

    # 6) 合成星云 + 星点
    if stars:
        out = step("recombine", neb, params={"stars": str(stars)}, tag="sho_final")
    else:
        out = results.get("sho_bg2")

    # 7) AI 评委:对成片做质量评估。SHO 配色是主观档(铁律8)→ 报告为主、不自动改;
    #    评委抓 background_washout/color_cast/noise/曝光等,给用户参考是否要调 palette/参数。
    try:
        from . import critic
        if all(critic._llm_config()[:3]):
            fin_png = out.get("preview")
            if fin_png:
                v = critic.critique(fin_png, context=f"SHO 窄带成片(palette={palette})")
                if v.get("error"):
                    print(f"  [AI评委] 不可用:{v['error']}")
                else:
                    print(f"  [AI评委] verdict={v.get('verdict')} issues={v.get('issues')}")
                    print(f"  [AI评委] {v.get('reason')}")
                    acts = v.get("actions") or []
                    if acts:
                        print("  [AI评委] 建议:" + "; ".join(
                            f"{a.get('target')} {a.get('direction')} {a.get('magnitude')}" for a in acts[:5]))
                    results["_critic"] = v
    except Exception as e:
        print(f"  [AI评委] 跳过(异常):{e}")

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
