"""P0 端到端演示:提交一个 job → 等待 PixInsight 执行 → 打印结果。

用法(在 pipeline/ 目录下运行):
    python -m orchestrator.p0_demo --op selftest
    python -m orchestrator.p0_demo --op probe
    python -m orchestrator.p0_demo --op inspect --input "D:/path/to/master.xisf"

前置:PixInsight 中已运行 job-runner.js(见 pipeline/README.md)。
可加 --launch 让脚本尝试自动启动 PixInsight 并加载 runner。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from . import config, protocol


def launch_runner() -> bool:
    """尝试用命令行启动 PixInsight 并加载 job-runner.js。"""
    exe = config.pixinsight_exe()
    if not exe:
        print("[!] 未找到 PixInsight.exe。请设置环境变量 PIXINSIGHT_EXE 指向它,"
              "或手动启动 PixInsight 后运行 job-runner.js。")
        return False
    runner = str(config.JOB_RUNNER_JS).replace("\\", "/")
    print(f"[*] 启动 PixInsight: {exe}")
    print(f"    -r={runner}")
    subprocess.Popen([exe, f"-r={runner}"], close_fds=False)
    return True


def summarize(result: dict) -> None:
    """精简打印 result 关键信息。"""
    print("\n===== RESULT =====")
    print(f"job_id : {result.get('job_id')}")
    print(f"op     : {result.get('op')}")
    print(f"status : {result.get('status')}")
    if result.get("error"):
        print(f"error  : {result['error']}")

    if "capabilities" in result:
        caps = result["capabilities"]
        print("capabilities:")
        for k in sorted(caps):
            v = caps[k]
            if isinstance(v, bool):
                print(f"   {'✓' if v else '✗'} {k}")
            else:
                print(f"     {k}: {v}")

    metrics = result.get("metrics")
    if metrics:
        print(f"image  : {metrics.get('width')}x{metrics.get('height')} "
              f"ch={metrics.get('channels')} bits={metrics.get('bits')} "
              f"color={metrics.get('isColor')}")
        for pc in metrics.get("perChannel", []):
            if "error" in pc:
                print(f"   ch{pc['channel']}: <err> {pc['error']}")
            else:
                print(f"   ch{pc['channel']}: median={pc['median']:.5f} "
                      f"mean={pc['mean']:.5f} stdDev={pc['stdDev']:.5f} "
                      f"min={pc['min']:.5f} max={pc['max']:.5f}")
    if result.get("preview"):
        print(f"preview: {result['preview']}")
    if result.get("image"):
        print(f"saved  : {result['image']}")
    print("==================\n")


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK,无法编码 ✓/✗ 等字符 → 统一切到 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="P0 端到端演示")
    parser.add_argument("--op", default="selftest",
                        choices=["selftest", "probe", "inspect"],
                        help="要执行的操作(默认 selftest,无需素材)")
    parser.add_argument("--input", default=None,
                        help="inspect 操作的输入图像路径")
    parser.add_argument("--launch", action="store_true",
                        help="尝试自动启动 PixInsight 并加载 runner")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="等待结果的超时秒数")
    args = parser.parse_args(argv)

    config.ensure_dirs()

    if args.op == "inspect" and not args.input:
        parser.error("--op inspect 需要 --input <图像路径>")

    if args.launch and not protocol.runner_alive():
        launch_runner()
        print("[*] 等待 runner 心跳(最多 90s)...")
        for _ in range(180):
            if protocol.runner_alive():
                break
            time.sleep(0.5)

    if protocol.runner_alive():
        print("[✓] runner 在线。")
    else:
        print("[!] 未检测到 runner 心跳。仍将提交 job —— 请确保稍后在 "
              "PixInsight 中运行 job-runner.js,否则会等待超时。")

    outputs = {"preview": config.RUN_DIR / f"preview_{args.op}.png"}
    job = protocol.new_job(args.op, input=args.input, outputs=outputs)
    protocol.submit(job)
    print(f"[*] 已提交 job {job['job_id']} (op={args.op}),等待结果...")

    try:
        result = protocol.wait_result(job["job_id"], timeout=args.timeout)
    except TimeoutError as e:
        print(f"[✗] {e}")
        return 1

    summarize(result)
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
