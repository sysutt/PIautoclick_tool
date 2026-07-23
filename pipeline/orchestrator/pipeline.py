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
            crop_margins: dict | None = None,
            use_critic: bool = True, auto_crop: bool = True) -> dict[str, Any]:
    """宽带 RGB 真实色全流程(M45 验证配方)。

    线性: crop → gradient(GC) → deconv(不缩星) → colorcal(SPCC自适应/BN+CC)
          → ABE(修边角渐晕) → stretch(linked, 激进)
    非线性: denoise → 分离星点
            ├ 星云: 轻度去绿(SCNR 0.4) → 曲线(对比+饱和)
            └ 星点: 两遍强饱和
          → 合成 → edgecheck(边缘不均粗筛,只提案不自动裁)
    crop_margins: 若给出 {left,top,right,bottom} 则最后执行边缘裁切(人工确认后传入)。
    """
    R = config.RUN_DIR
    results: dict[str, dict] = {}

    def step(op, inp, params=None, tag="", extra=None):
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

    print("== 宽带 RGB 管线 ==")
    r = step("crop",     input_path,  tag="r00_crop")
    r = step("gradient", r["image"],  tag="r01_grad")
    r = step("deconv",   r["image"],  params={"sharpenStars": 0}, tag="r02_deconv")
    # 颜色校准自适应:优先 SPCC(需天文解析)。无解析 → 本地 ImageSolver 解一次;
    # 仍失败 → 回退 BN+CC(Tier 2 astrometry.net 在线解析待接入)。
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
    r = step("gradient", r["image"],  params={"method": "abe", "polyDegree": 5}, tag="r04_abe")  # 修边角渐晕
    r = step("stretch",  r["image"],  params={"linked": True, "targetBackground": 0.30}, tag="r05_stretch")
    r = step("denoise",  r["image"],  params={"linear": False}, tag="r06_denoise")
    sep = step("starsep", r["image"], tag="r07_starsep", extra={"stars": R / "r07_stars.xisf"})

    # 星云:轻度去绿 → 曲线(对比 + 适中饱和)
    neb = step("scnr",   sep["image"], params={"amount": 0.4}, tag="r08_neb_scnr")
    neb = step("curves", neb["image"], params={"contrast": 0.08, "saturation": 0.22}, tag="r09_neb")
    # 星点:两遍强饱和
    st = step("curves",  sep.get("stars"), params={"saturation": 0.5}, tag="r10_st1")
    st = step("curves",  st["image"], params={"saturation": 0.4}, tag="r11_st2")
    # 合成
    r = step("recombine", neb["image"], params={"stars": st["image"]}, tag="r12_final")

    # 边缘不均粗筛(只提案,不自动裁 —— 破坏性 + 需感知判断)
    ea = query("edgecheck", r["image"]).get("edgeAnalysis", {})
    print(f"\n[edgecheck] 边缘偏离(MAD): {ea.get('edgeDeviationMad')}")
    print(f"[edgecheck] 建议裁切(像素): {ea.get('cropProposalPx')}  needCrop={ea.get('needCrop')}")
    print("  * 裁切为破坏性操作,不自动执行;确认后用 crop_margins 传入或单独跑 crop。")

    if crop_margins:
        r = step("crop", r["image"], params={"margins": crop_margins, "linear": False}, tag="r13_cropped")
        print("  已按 crop_margins 裁切。")

    # ---- LLM 评委:A) 质量报告  B) 边缘伪影 → 评委给裁切比例并落实 ----
    if use_critic and not crop_margins:
        r = _critic_finish(step, r, ctx="宽带 RGB 真实色成片", timeout=timeout, auto=auto_crop)

    print(f"\n最终成片: {r.get('image')}")
    print(f"最终预览: {r.get('preview')}")
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
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)

    config.ensure_dirs()

    if protocol.runner_alive():
        print("[✓] runner 在线。")
    else:
        print("[!] 未检测到 runner 心跳,请先在 PixInsight 运行 job-runner.js。")

    if args.hoo or args.rgb:
        try:
            fn = run_hoo if args.hoo else run_rgb
            fn(args.input.replace("\\", "/"), timeout=args.timeout)
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
