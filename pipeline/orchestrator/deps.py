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
    # BXT/NXT/SXT:收费模块。**已不再是硬必需**——#4 三级路由(2026-08-11)给了免费兜底,
    #   缺了自动降级仍能出片(见 fallback 字段),故 need 从 core 降为 opt。装了质量更好。
    {"sym": "BlurXTerminator", "label": "BlurXTerminator (BXT)", "kind": "module", "paid": True,
     "need": "opt", "url": "https://www.rc-astro.com/software/bxt/",
     "fallback": "PI 自带 Deconvolution(RL 反卷积)自动顶上",
     "note": "反卷积/星点 PSF 校正(锐化+修圆星点)。缺了用免费兜底,但 BXT 质量明显更好。"},
    {"sym": "StarXTerminator", "label": "StarXTerminator (SXT)", "kind": "module", "paid": True,
     "need": "opt", "url": "https://www.rc-astro.com/software/sxt/",
     "fallback": "StarNet2(免费,见下)顶上;都没有则跳过去星",
     "note": "星点分离(星云/星点分开处理)。缺了走 StarNet2,或跳过(保留星点)。"},
    {"sym": "NoiseXTerminator", "label": "NoiseXTerminator (NXT)", "kind": "module", "paid": True,
     "need": "opt", "url": "https://www.rc-astro.com/software/nxt/",
     "fallback": "PI 自带 MultiscaleLinearTransform(小波降噪)自动顶上",
     "note": "降噪。缺了用免费兜底(MLT)。"},
    {"sym": "StarNet2", "label": "StarNet2(免费去星)", "kind": "module", "paid": False,
     "need": "opt", "url": "https://starnetastro.com/",
     "repo": "https://pixinsight.starnetastro.com/",
     "note": "星点分离的**免费**替代(没买 SXT 时用)。装后管线 starsep 自动走它。仓库方式装,PI 可自动更新。"},
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
        action = "购买并安装" if d["paid"] else "免费安装"
        if d["kind"] == "builtin":
            how = "PI 自带:请升级 PixInsight 到 1.8.9 或更新版本"
        elif d.get("repo"):
            # 现代仓库方式(StarNet2、以及新版 rc-astro 模块):加仓库 → 检查更新 → 重启。
            # 【关键】仓库只把 DLL 放进 bin/,**还需 Process → Modules → Install Modules 正式注册**
            #   (PJSR 无装模块 API,只能 GUI 点);否则 typeof 探不到、管线用不上(StarNet2 实测踩坑)。
            how = ("PI 里:①Resources → Updates → Manage Repositories → Add → 填仓库地址 "
                   + d["repo"] + " → Check for Updates → Apply → 重启 PI;"
                   "②若 Process 菜单里仍找不到,再走 Process → Modules → Install Modules → 搜索该模块 → 安装 → 再重启")
        else:
            how = ("下载后在 PI 里:Process → Modules → Install Modules → 选该文件夹 → 重启 PI"
                   "(新版也可用作者的仓库地址走 Manage Repositories 自动更新)")
        miss.append({**d, "action": action, "how": how})
    # 免费/可直接装的排前(用户能立刻行动的优先),其次按名字
    miss.sort(key=lambda x: (x["paid"], x["label"]))
    return miss


def format_text(miss: list[dict]) -> str:
    """给日志/对话框用的纯文本提示。"""
    if not miss:
        return "依赖体检:全部就绪。"
    lines = ["依赖体检:缺少以下项(缺了不再报错中断,按下方兜底自动降级)—"]
    for d in miss:
        tag = "【必需】" if d["need"] == "core" else "【可选】"
        pay = "(收费)" if d["paid"] else "(免费)"
        lines.append(f"  {tag}{d['label']}{pay}  {d['action']}")
        lines.append(f"      {d['note']}")
        if d.get("fallback"):
            lines.append(f"      缺失时兜底:{d['fallback']}")
        lines.append(f"      地址:{d['url']}")
        lines.append(f"      安装:{d['how']}")
    return "\n".join(lines)
