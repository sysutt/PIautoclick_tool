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
    r = step("deconv",   r["image"],   tag="h02_deconv")
    r = step("hoo",      r["image"],   tag="h03_hoo")
    hoo_linear = r["image"]            # 全图线性 HOO,用于策略2的 STF 参考
    sep = step("starsep", hoo_linear,  tag="h04_starsep", stars_out=True)
    starless_lin, stars_lin = sep["image"], sep.get("stars")
    if not stars_lin:
        raise RuntimeError("星点分离未产出星点图")

    # 星云:更激进的逐通道拉伸(暗目标),再降噪、去绿
    sl = step("stretch", starless_lin,
              params={"linked": False, "targetBackground": 0.18}, tag="h05_starless_str")
    sl = step("denoise", sl["image"], params={"linear": False}, tag="h06_starless_dn")
    sl = step("scnr",    sl["image"], params={"amount": 0.75}, tag="h07_starless_scnr")
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
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)

    config.ensure_dirs()

    if protocol.runner_alive():
        print("[✓] runner 在线。")
    else:
        print("[!] 未检测到 runner 心跳,请先在 PixInsight 运行 job-runner.js。")

    if args.hoo:
        try:
            run_hoo(args.input.replace("\\", "/"), timeout=args.timeout)
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
