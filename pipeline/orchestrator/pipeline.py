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


def run_integrate(registered_dir: str, out_path: str | None = None,
                  timeout: float = 1800.0) -> str:
    """把 registered 目录(含按夜分的子目录)下所有 .xisf 单张叠加成一个新 master。

    对应作者多日拍摄工作流:不直接用 WBPP 的分夜 masterLight,而是把所有已配准
    单张一起 ImageIntegration。返回新 master 的路径。
    """
    from pathlib import Path
    root = Path(registered_dir)
    subs = sorted(str(p).replace("\\", "/") for p in root.rglob("*.xisf"))
    if len(subs) < 3:
        raise RuntimeError(f"registered 目录下 .xisf 太少({len(subs)}):{registered_dir}")
    if out_path is None:
        out_path = str(config.RUN_DIR / "integrated_master.xisf")
    out_path = str(out_path).replace("\\", "/")
    print(f"== ImageIntegration:{len(subs)} 张 → {out_path} ==")
    job = protocol.new_job("integrate", params={"images": subs},
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
            recombine_stars: bool = False) -> dict[str, Any]:
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
    r = step("colorcal", r["image"],  params={"method": method}, tag="r03_colorcal")
    r = step("gradient", r["image"],  params={"method": "abe", "polyDegree": 4}, tag="r04_abe")  # 压平梯度
    # 线性强降噪(压亮度噪声,GHS 前)
    r = step("denoise",  r["image"],  params={"denoise": 0.90, "detail": 0.10}, tag="r05_dn")
    # ---- 拉伸 → 分离星点 ----
    r = step("stretch",  r["image"],  params={"linked": True, "targetBackground": 0.12}, tag="r06_str")
    sep = step("starsep", r["image"], tag="r07_sep", extra={"stars": R / "r07_stars.xisf"})
    # ---- 星云(starless)后期 ----
    neb = step("ghs",    sep["image"], params={"D": ghs_d, "HP": 0.9}, tag="r08_ghs")
    # GHS 后二次降噪:带色度+低频,专抹斑驳/紫斑(先清杂色,后面提饱和才不返噪)
    neb = step("denoise", neb["image"], params={
        "denoise": 0.75, "detail": 0.15, "colorSep": True, "denoiseColor": 0.95,
        "freqSep": True, "denoiseLF": 0.6, "denoiseLFColor": 0.9}, tag="r09_dn2")
    neb = step("scnr",   neb["image"], params={"amount": 0.85}, tag="r10_scnr")
    neb = step("curves", neb["image"], params={"saturation": neb_sat}, tag="r11_neb")  # 仅提星云饱和
    r = neb

    # 可选:极轻合回星点(默认 starless 定稿形态)
    if recombine_stars:
        stw = step("curves", sep.get("stars"), params={"saturation": 0.3}, tag="r12_stars")
        r = step("recombine", neb["image"], params={"stars": stw["image"]}, tag="r13_recomb")

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
            r = step("integrate", params={"images": subs}, tag=f"lr_{key}")
            masters[key] = str(r["image"])
            print(f"    {key}: {len(subs)} 张")
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
