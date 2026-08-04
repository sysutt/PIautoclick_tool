"""第三方插件/模块依赖体检。

PixInsight 的**模块**(bin/*-pxm.dll,如 BXT/SXT/NXT)只能由用户经 GUI
「Process → Modules → Install Modules」安装(注册信息在 PI 私有配置里,PJSR 无安装 API),
所以程序能做的是:**提前探测缺什么 → 给出下载/购买地址与安装步骤**,而不是等流程跑到一半才失败。

免费的提示"去下载安装",收费的才提示"购买"。
"""
from __future__ import annotations

# name: PJSR 全局符号名(用 typeof 探测);其余为展示信息
#   kind:  module(PI 模块,需 GUI 安装) / builtin(PI 自带,缺=版本太旧) / external(外部程序)
#   paid:  True=收费(提示购买) / False=免费(提示下载安装)
#   need:  core=核心流程必需 / opt=可选增强(缺了会退化但能跑)
REGISTRY: list[dict] = [
    {"sym": "BlurXTerminator", "label": "BlurXTerminator (BXT)", "kind": "module", "paid": True,
     "need": "core", "url": "https://www.rc-astro.com/software/bxt/",
     "note": "反卷积/星点 PSF 校正。管线用它锐化与修圆星点。"},
    {"sym": "StarXTerminator", "label": "StarXTerminator (SXT)", "kind": "module", "paid": True,
     "need": "core", "url": "https://www.rc-astro.com/software/sxt/",
     "note": "星点分离(星云/星点分开处理的前提)。"},
    {"sym": "NoiseXTerminator", "label": "NoiseXTerminator (NXT)", "kind": "module", "paid": True,
     "need": "core", "url": "https://www.rc-astro.com/software/nxt/",
     "note": "降噪。管线在多处按不同强度调用。"},
    {"sym": "SpectrophotometricColorCalibration", "label": "SPCC(光谱色彩校准)", "kind": "builtin",
     "paid": False, "need": "opt", "url": "https://pixinsight.com/",
     "note": "PI 1.8.9+ 自带;缺失会退化为 BN+CC。"},
    {"sym": "GeneralizedHyperbolicStretch", "label": "GHS(广义双曲拉伸)", "kind": "builtin",
     "paid": False, "need": "opt", "url": "https://www.ghsastro.co.uk/",
     "note": "PI 1.8.9+ 自带;旧版可装 GHS 脚本/模块。暗弱星云揭示用。"},
    {"sym": "ImageSolver", "label": "ImageSolver(天文解析脚本)", "kind": "builtin", "paid": False,
     "need": "opt", "url": "https://pixinsight.com/",
     "note": "PI 自带脚本;SPCC 需要解析结果,缺失则退化为 BN+CC。"},
    {"sym": "LocalHistogramEqualization", "label": "LHE(局部直方图均衡)", "kind": "builtin",
     "paid": False, "need": "opt", "url": "https://pixinsight.com/", "note": "PI 自带;局部对比用。"},
    {"sym": "HDRMultiscaleTransform", "label": "HDRMT(多尺度 HDR)", "kind": "builtin", "paid": False,
     "need": "opt", "url": "https://pixinsight.com/", "note": "PI 自带;压亮核保结构用。"},
    {"sym": "MorphologicalTransformation", "label": "形态学变换", "kind": "builtin", "paid": False,
     "need": "opt", "url": "https://pixinsight.com/", "note": "PI 自带;缩星用。"},
    {"sym": "GraXpert", "label": "GraXpert(外部梯度校正)", "kind": "external", "paid": False,
     "need": "opt", "url": "https://github.com/Steffenhir/GraXpert/releases",
     "note": "可选:更强的背景梯度校正。装好后在『配置』里填 GraXpert.exe 路径;不装则用 PI 自带 GC/ABE。"},
]


def probe(timeout: float = 120.0) -> dict:
    """让 job-runner 在 PI 里 typeof 探测各依赖,返回 {sym: bool}。runner 未运行时抛异常。"""
    from . import protocol
    if not protocol.runner_alive():
        raise RuntimeError("job-runner 未运行,无法探测依赖(请先启动 PixInsight)")
    syms = [d["sym"] for d in REGISTRY]
    job = protocol.new_job("probedeps", params={"names": syms})
    protocol.submit(job)
    r = protocol.wait_result(job["job_id"], timeout=timeout)
    if r.get("status") != "ok":
        raise RuntimeError(f"依赖探测失败:{r.get('error')}")
    return r.get("deps") or {}


def report(avail: dict) -> list[dict]:
    """把探测结果整理成缺失清单(附安装/购买提示)。返回缺失项列表(need=core 排前)。"""
    miss = []
    for d in REGISTRY:
        if avail.get(d["sym"]):
            continue
        if d["kind"] == "external":       # 外部程序由配置项判断,不靠 PJSR 符号
            continue
        action = "购买并安装" if d["paid"] else "下载安装"
        if d["kind"] == "builtin":
            how = "PI 自带:请升级 PixInsight 到 1.8.9 或更新版本"
        else:
            how = "下载后在 PI 里:Process → Modules → Install Modules → 选该文件夹 → 重启 PI"
        miss.append({**d, "action": action, "how": how})
    miss.sort(key=lambda x: (x["need"] != "core", not x["paid"]))
    return miss


def format_text(miss: list[dict]) -> str:
    """给日志/对话框用的纯文本提示。"""
    if not miss:
        return "依赖体检:全部就绪。"
    lines = ["依赖体检:缺少以下项 —"]
    for d in miss:
        tag = "【必需】" if d["need"] == "core" else "【可选】"
        pay = "(收费)" if d["paid"] else "(免费)"
        lines.append(f"  {tag}{d['label']}{pay}  {d['action']}")
        lines.append(f"      {d['note']}")
        lines.append(f"      地址:{d['url']}")
        lines.append(f"      安装:{d['how']}")
    return "\n".join(lines)
