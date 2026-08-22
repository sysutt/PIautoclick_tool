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
]

# 外部 CLI 工具(非 PI 模块 → 路径探测,不靠 PJSR symbol):无 PI 引擎(#3)/免费兜底/引擎中立。
# cfg=config 设置键;defaults=常见默认安装位置(存在即视为已装);how=安装方法(下载 + 在『配置』填路径)。
EXTERNAL: list[dict] = [
    {"sym": "siril", "cfg": "siril_path", "label": "Siril(无 PI 引擎)", "paid": False, "need": "opt",
     "url": "https://siril.org/download/",
     "defaults": ["C:/Program Files/Siril/bin/siril-cli.exe", "C:/Program Files/SiriL/bin/siril-cli.exe"],
     "note": "引擎中立 CLI:无 PixInsight 时的背景提取/拉伸/合成/去星调度(#3 对等引擎)。",
     "how": "下载安装 Siril → 在『配置』填 siril_path 指向 bin/siril-cli.exe(装到默认位置可自动识别)"},
    {"sym": "starnet_cli", "cfg": "starnet_path", "label": "StarNet2 CLI(免费去星)", "paid": False, "need": "opt",
     "url": "https://starnetastro.com/cli-tools/", "defaults": [],
     "note": "免费去星:无 PI 时的星点分离 / SHO 星点转色。",
     "how": "下载 StarNet2 CLI(installer 或 zip,download.starnetastro.com)→ 装/解压 → 在『配置』填 starnet_path 指向可执行文件"},
    {"sym": "graxpert", "cfg": "graxpert_path", "label": "GraXpert(梯度校正/AI 降噪)", "paid": False, "need": "opt",
     "url": "https://github.com/Steffenhir/GraXpert/releases",
     "defaults": ["D:/GraXpert/GraXpert.exe", "C:/Program Files/GraXpert/GraXpert.exe"],
     "note": "外部 CLI:背景梯度校正 + AI 降噪(GPU,通道级)。无 PI SHO 引擎的通道降噪。降噪模型首次用会自动下(需联网)。",
     "how": "下载安装 GraXpert(3.x 含 denoise)→ 在『配置』填 graxpert_path 指向 GraXpert.exe(装默认位置可自动识别)"},
    {"sym": "deepsnr", "cfg": "deepsnr_path", "label": "DeepSNR(AI 降噪·免费最强)", "paid": False, "need": "opt",
     "url": "https://www.starnetastro.com/",
     "defaults": ["D:/Program Files/DeepSNR/bin/deepsnr.exe", "C:/Program Files/DeepSNR/bin/deepsnr.exe"],
     "note": "StarNet 作者的 AI 降噪(社区公认免费最强)。model 2 支持彩色 → **可直接降噪彩色合成图**(GraXpert 彩色会卡死);GPU ~0.4min。无 PI SHO 引擎的降噪主力。",
     "how": "下载 DeepSNR CLI(starnetastro.com,和 StarNet 同源)→ 装到 D:/Program Files/DeepSNR → 在『配置』填 deepsnr_path 指向 bin/deepsnr.exe(默认位置可自动识别)"},
    {"sym": "siril_gaia_astro", "cfg": "_siril_gaia_astro", "label": "Siril 本地 Gaia 解析星表(离线 platesolve)", "paid": False, "need": "opt",
     "url": "https://zenodo.org/records/14692304",
     "defaults": ["~/.local/share/siril/siril_cat_healpix8_astro.dat"],
     "note": "无 PI RGB/SHO 的离线天文解析(SPCC 前置)。全天单文件,解压 1.5GB,一次通用。",
     "how": "Siril → Scripts → Catalogue Installer → Astrometry「Install」(或 Zenodo 下 siril_cat_healpix8_astro.dat.bz2 → bz2 解压 → 放 ~/.local/share/siril/ → config 键 catalogue_gaia_astro 指向它)"},
    {"sym": "siril_gaia_photo", "cfg": "_siril_gaia_photo", "label": "Siril 本地 Gaia SPCC 光度星表(离线真·光度校准)", "paid": False, "need": "opt",
     "url": "https://zenodo.org/records/14738271",
     "defaults": ["~/.local/share/siril/siril_cat1_healpix8_xpsamp"],
     "note": "无 PI RGB 的真·光度色彩校准(spcc,与 PI SPCC 同源)。按天区分块(nside=2,48 块),只需下拍摄天区(如猎户座=块 20/22)。",
     "how": "Siril → Scripts → Catalogue Installer → SPCC → 选天区(如「Orion to Taurus」)/纬度「Install」(或 Zenodo 14738271 下对应块 → 解压进子目录 siril_cat1_healpix8_xpsamp/ → config 键 catalogue_gaia_photo 指向该目录)"},
    {"sym": "rcastro", "cfg": "rcastro_path", "label": "rc-astro CLI(BXT 星点修复 / SXT 去星 / NXT 降噪)", "paid": False, "need": "opt",
     "url": "https://www.rc-astro.com/software/",
     "defaults": ["D:/Program Files/RC-Astro/CLI/rc-astro.exe", "C:/Program Files/RC-Astro/CLI/rc-astro.exe",
                  "D:/rc-astro/rc-astro.exe", "C:/Program Files/rc-astro/rc-astro.exe", "~/rc-astro/rc-astro.exe"],
     "note": "Russell Croman 出品 BXT(BlurXTerminator 星点修复/反卷)/SXT(StarXTerminator 去星)/NXT(NoiseXTerminator 降噪)"
             "的**独立命令行版**,一个 CLI 全包、跨平台(Win/Mac/Linux)、GPU 加速、读写 FITS+XISF。**持牌用户免费**——"
             "本软件用它做拉线星点修复(Siril 无等价)、专业反卷/去星/降噪。",
     "how": "安装指引:①在 rc-astro.com 购买(或已购)BlurXTerminator/StarXTerminator/NoiseXTerminator——"
            "持有对应授权即可用 rc-astro 独立 CLI(每个产品各自授权,可只买需要的);②rc-astro.com/software 下 "
            "Windows 版 rc-astro CLI 安装包,装到默认 `C:/Program Files/RC-Astro/CLI/`(或自选目录);③在本软件"
            "『配置』填 rcastro_path 指向 rc-astro.exe(装默认位置可自动识别)。"
            "【激活授权(关键)】④命令行 `rc-astro license` 登录你的 RC-Astro 账户并看各产品状态、顺带自动下 AI 模型;"
            "⑤逐个激活本机:`rc-astro license --activate bxt`(sxt/nxt 同理;或 `--activate` 后按提示粘贴账户激活码)——"
            "**未激活的产品该功能不可用**(如 BXT 未激活则星点修复用不了)。命令形如 `rc-astro bxt image.fit -o out/ "
            "--sharpen-stars 0.5`。跨平台、GPU 加速、读写 FITS/XISF。**收费插件,可选升级**:装了则星点修复/降噪/去星"
            "用 rc-astro(更强),没装/未激活则自动回落免费管线(DeepSNR/StarNet2/Siril)。"},
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


def _resolve_ext(d: dict) -> str | None:
    """外部工具可执行路径:config 的 cfg 键优先,否则 defaults 里存在的第一个;都无则 None。"""
    import os
    try:
        from . import config
        p = config.load_settings().get(d["cfg"], "")
    except Exception:
        p = ""
    if p and os.path.exists(os.path.expanduser(p)):
        return p
    for c in d.get("defaults", []):
        if os.path.exists(os.path.expanduser(c)):
            return c
    return None


def probe_external() -> dict:
    """路径探测外部 CLI 工具(Siril/StarNet CLI/GraXpert/rc-astro),**不需 runner/PI**。返回 {sym: bool}。"""
    return {d["sym"]: (_resolve_ext(d) is not None) for d in EXTERNAL}


def report(avail: dict, avail_ext: dict | None = None) -> list[dict]:
    """把探测结果整理成缺失清单(附安装/购买提示)。avail=PJSR 探测(REGISTRY);
    avail_ext=外部工具路径探测(EXTERNAL,来自 probe_external);None 则不含外部。免费/可直接装的排前。"""
    miss = []
    for d in REGISTRY:
        if avail.get(d["sym"]):
            continue
        if d.get("kind") == "external":   # 兼容:REGISTRY 里若残留 external 项,交给 EXTERNAL 处理
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
    # 外部 CLI 工具(路径探测):缺则给下载地址 + 安装方法(下载 → 在『配置』填路径)
    if avail_ext is not None:
        for d in EXTERNAL:
            if avail_ext.get(d["sym"]):
                continue
            action = "购买并安装" if d["paid"] else "免费安装"
            miss.append({**d, "action": action,
                         "how": d.get("how", "下载后在『配置』里填该工具的可执行文件路径")})
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
