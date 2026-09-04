# -*- coding: utf-8 -*-
"""界面多语言(用户 2026-09-04:中/英双语)。

**源串为键**的最低摩擦方案:界面里把可见文案包一层 `t("处理到")` 即可;英文时查 ZH_EN,
未收录的串**回落中文**(不会崩、不会显空)。语言从 config `ui.lang`(回退 `lang`)读,值 'en'/'zh',
默认中文;也可显式传 `t(s, "en")`。与 critic.py 的 `_ui_lang` 同一配置键,界面切语言→写 config→
UI 文案 + LLM 输出一起跟随。

移植端(app_ui.py)接线:`from .i18n import t`;把 QLabel/QPushButton/... 的中文字面量包成 `t("…")`;
语言开关调 `set_lang('en'|'zh')`(写 config)后,重刷各控件 `setText(t(原串))` 即可即时切换。
LLM 侧无需改(critic 自读同键)。表以外(动态拼接串)按需在调用点用 t() 或补进 ZH_EN。
"""
from __future__ import annotations

from . import config

_LANG_CACHE: dict = {}


def ui_lang(lang: str | None = None) -> str:
    """当前语言:显式('zh'/'en')优先,否则读 config ui.lang→lang,默认 zh。与 critic._ui_lang 同键。"""
    if lang in ("zh", "en"):
        return lang
    try:
        v = config.get_setting("ui.lang") or config.get_setting("lang") or "zh"
    except Exception:
        v = "zh"
    return "en" if str(v).lower().startswith("en") else "zh"


def set_lang(lang: str) -> None:
    """把语言写进 config 的**嵌套** ui.lang,critic 的 LLM 输出与 UI 同步跟随。
    注意:config.save_settings 是**整体覆盖**→ 必须 load_settings→改→save,别只写 {'ui.lang':..} 冲掉其它配置。
    get_setting('ui.lang') 走点路径读嵌套 settings['ui']['lang']。"""
    lang = "en" if str(lang).lower().startswith("en") else "zh"
    try:
        s = config.load_settings()
        if not isinstance(s.get("ui"), dict):
            s["ui"] = {}
        s["ui"]["lang"] = lang
        config.save_settings(s)
    except Exception:
        pass


def t(s: str, lang: str | None = None) -> str:
    """翻译一个 UI 串。英文查表,未收录回落原(中文)串。中文原样返回。"""
    if ui_lang(lang) != "en":
        return s
    return ZH_EN.get(s, s)


# ── 源串(中文)→ 英文。键必须与 app_ui.py 里的字面量**完全一致**(含标点/emoji/空格)。 ──
ZH_EN: dict[str, str] = {
    # 顶栏 / 阶段 / 品牌
    "深空自动后期 · 一键处理(PixInsight 自动流程 · LLM 评审)":
        "Deep-sky auto post-processing · one click (PixInsight pipeline · LLM review)",
    "项目": "Projects", "配置": "Setup", "流程": "Workflow", "参数": "Parameters",
    "格式": "Format", "质量": "Quality", "设备": "Device", "校准库": "Calib library",
    "◑ 主题": "◑ Theme", "已保存": "Saved", "未保存": "Unsaved", "未命名项目": "Untitled project",
    "项目名": "Project name", "项目名 如 260710-260724_2600mc_IC1396": "Project name, e.g. 260710-260724_2600mc_IC1396",
    # 阶段导航 / 页面标题与引导
    "选择流程": "Choose workflow", "调色方式": "Palette", "SHO 配色": "SHO palette",
    "选择处理流程,再指定素材与设备。这一步决定整条管线。":
        "Pick a workflow, then point to your data and device — this defines the whole pipeline.",
    "素材 · 设备 · 输出": "Data · Device · Output",
    "继续最近的工程,或新建 / 打开一个 .ttproj 工程文件":
        "Resume a recent project, or create / open a .ttproj file",
    "选择格式与附件,导出到项目输出目录。": "Choose formats and extras, export to the project folder.",
    "成片就绪后,在此选择格式并导出(先到「处理」跑完流程)。":
        "Once the image is ready, choose formats and export here (run the pipeline in “Process” first).",
    "就绪。选择流程与输入后点击「开始处理」。": "Ready. Pick a workflow and input, then click “Start”.",
    "还没有成片。到「处理」跑完流程后,评审与实测指标会出现在这里。":
        "No result yet. Run the pipeline in “Process” — the review and metrics will appear here.",
    "处理进行中…评审与实测指标会在完成后出现在这里。":
        "Processing… the review and metrics will appear here when it finishes.",
    # 主要按钮 / 操作
    "▶ 开始处理": "▶ Start", "▶ 继续": "▶ Resume", "■ 中止": "■ Abort", "⏸ 暂停介入": "⏸ Pause",
    "⏸ 将在当前步骤后暂停…": "⏸ Will pause after the current step…",
    "下一步:处理 →": "Next: Process →", "↓ 导出成片": "↓ Export", "在文件夹显示": "Show in folder",
    "导出目录": "Export folder", "导出历史": "Export history", "输出根": "Output root",
    "浏览…": "Browse…", "配置…": "Configure…", "打开工程": "Open project",
    "新建项目": "New project", "＋ 新建项目": "＋ New project",
    "释放 PixInsight": "Release PixInsight", "↻ 重载 runner": "↻ Reload runner",
    "插件体检": "Plugin check", "重新扫描": "Rescan",
    "清理中间文件": "Clean temp files", "清理中间文件(统计中…)": "Clean temp files (measuring…)",
    "运行目录 _run 里没有可清理的中间产物。": "Nothing to clean in the _run working directory.",
    "正在统计运行目录体积,请稍候…": "Measuring working-directory size, please wait…",
    "📁 自动识别文件夹": "📁 Auto-detect folder", "🔎 自动匹配": "🔎 Auto-match",
    "导出成片": "Export",
    # 审阅 / 评分 / 优化
    "成片预览": "Preview", "成片评审": "Verdict", "实测指标": "Measured",
    "LLM · 同视场对照": "LLM · vs. same field", "确定性 · numpy": "Deterministic · numpy",
    "⇄ 对比原图": "⇄ Compare original", "⇄ 看优化后": "⇄ Show optimized", "↩ 撤销优化": "↩ Undo",
    "🔧 按评分优化": "🔧 Optimize by score", "🔄 重新评分": "🔄 Re-score", "评这一档": "Score this",
    "换配色": "Change palette", "需你决定:": "Needs your call:",
    "🩹 灰尘修复": "🩹 Dust fix", "灰尘修复": "Dust fix", "✓ 应用修复": "✓ Apply fix",
    "🌑 加暗结构": "🌑 Add dark structure",
    "拖拽画圆框住灰尘,可拖边缘缩放/拖中心移动,点『应用修复』":
        "Drag a circle over the dust; drag the edge to resize / center to move, then “Apply fix”.",
    # 与 AI 对话
    "发送": "Send", "取消": "Cancel", "撤销": "Undo",
    "告诉 AI 你想怎么改,回车发送…": "Tell the AI what to change, press Enter…",
    "跟 AI 说想怎么改,例如「星点饱和度还不够」「背景再压暗点」「核心蓝一点」,回车发送…":
        "Tell the AI what to change, e.g. “stars need more saturation”, “darken the background”, "
        "“a bit more blue in the core” — press Enter…",
    "与 AI 对话改当前图:例如「核心蓝色不够,增强一点核心的蓝,别动背景」":
        "Refine this image by chat, e.g. “the core lacks blue — boost it a little, leave the background”.",
    # 处理选项 / 参数
    "处理到": "Run to", "交棒": "Handoff", "交棒点": "Handoff point",
    "星云揭示": "Nebula reveal", "暗尘层次揭示": "Faint-dust reveal", "暗结构强化 DSE": "Dark-structure (DSE)",
    "残留辉光": "Residual glow", "背景梯度": "Background gradient", "梯度矫正": "Gradient correction",
    "残差去线 + 逐帧背景去云;【默认关】耗时大、卫星线整合 rejection 通常能排掉,需要时再勾":
        "Residual line removal + per-frame cloud rejection; OFF by default — slow, and satellite trails "
        "are usually rejected during integration anyway; enable when needed.",
    # 输入 / 叠加
    "已叠加母版 .xisf / .fit / .fits": "Stacked master .xisf / .fit / .fits",
    "直接后期一张已叠加好的主图。": "Post-process a single already-stacked master.",
    "整合目录内全部对齐子帧后再后期(多通道 LRGB 也用此)。":
        "Integrate all registered subframes in a folder, then process (also for multi-channel LRGB).",
    "registered 对齐子帧目录(将自动整合)": "Registered-subframe folder (will be integrated)",
    "混合目录 · 选择要叠加的组": "Mixed folder · pick the set to stack",
    "(可选)校准场库根目录 → 按亮场自动匹配暗/偏/平各组":
        "(optional) Calibration-library root → auto-match darks/bias/flats to lights",
    "(可选)+ 双窄带 Ha/OIII master 或子帧目录 → 给 RGB 加 Ha/OIII 红结":
        "(optional) + dual-narrowband Ha/OIII master or subframe folder → add Ha/OIII to RGB",
    "(留空=导出时弹窗选)成片导出到这、文件名用项目名":
        "(blank = ask on export) export here, filename = project name",
    "+ 添加一晚": "＋ Add a night", "+ 添加一组通道": "＋ Add channels", "+窄带": "+narrowband",
    "亮场…": "Lights…", "平场…": "Flats…", "通道亮场目录": "Channel lights folder",
    "通道平场目录": "Channel flats folder", "选通道图:": "Pick channel:",
    "全选": "Select all", "全不选": "Clear", "删除选中": "Remove selected",
    # 状态
    "准备中": "Preparing", "准备中…": "Preparing…", "等待素材": "Waiting for data",
    "处理中": "Processing", "处理中…": "Processing…", "完成": "Done", "已完成": "Done",
    "已停止": "Stopped", "已暂停 · 可对当前图做矫正": "Paused · you can fix the current image",
    # 交棒点(「处理到」下拉,各流程)
    "跑完全流程(出成片)": "Full pipeline (final image)",
    "① 只整合各通道": "① Integrate channels only", "① 只裁黑边": "① Crop edges only",
    "② +梯度校正": "② + Gradient correction", "② +统一裁黑边+梯度校正": "② + Crop + gradient correction",
    "② +统一裁黑边+背景匹配": "② + Crop + background match",
    "③ +BXT": "③ + BXT", "③ +BXT(常用交棒点)": "③ + BXT (common handoff)",
    "③ +RGB合成/superL": "③ + RGB combine / superL",
    "④ +HOO 合成": "④ + HOO combine", "④ +线性降噪": "④ + Linear denoise",
    "④ +色彩校准": "④ + Color calibration", "④ +色彩校准(SPCC/BNCC)": "④ + Color calibration (SPCC/BNCC)",
    "⑤ +去星(星云/星点)": "⑤ + Star removal (nebula / stars)", "⑤ +拉伸": "⑤ + Stretch",
    "⑤ +拉伸对齐": "⑤ + Stretch & align", "⑤ +线性降噪": "⑤ + Linear denoise",
    "⑥ +保色亮度替换": "⑥ + Color-preserving luminance", "⑥ +合成 SHO": "⑥ + SHO combine",
    "⑥ +拉伸": "⑥ + Stretch", "⑦ +去星(星云/星点)": "⑦ + Star removal (nebula / stars)",
    "⑧ +调色(合星前)": "⑧ + Color grading (before recombine)",
    "…/Dark/…(共用,不打标签)": "…/Dark/… (shared, no label)",
    "…/Bias/…(共用,不打标签)": "…/Bias/… (shared, no label)",
    # ── 5 屏 IA 重构新增(app_ui.py 移植期补,2026-09-04)──
    # 阶段导航名(nav 用 f"{ix} · {t(name)}" 组合)
    "项目库": "Projects", "处理": "Process", "审阅": "Review", "导出": "Export",
    # 流程卡:名 + 一句话
    "宽带 RGB": "Broadband RGB", "窄带 SHO": "Narrowband SHO",
    "双窄 HOO": "Dual HOO", "黑白 LRGB": "Mono LRGB",
    "彩色相机宽带,自然真彩": "Color camera, natural true color",
    "SII/Ha/OIII 哈勃调色": "SII/Ha/OIII Hubble palette",
    "Ha/OIII 双窄,红青": "Ha/OIII dual-narrowband, red–teal",
    "单色相机,亮度+彩色": "Mono camera, luminance + color",
    # 卡片头条 / 面板标题
    "给素材": "Data", "调参数": "Parameters", "完成 · 评分与导出": "Done · review & export",
    # 审阅评分条 / 实测指标行标
    "背景": "Background", "星点色": "Star color", "核心": "Core",
    "星点饱和度": "Star saturation", "背景中性": "Bg neutrality", "背景亮度": "Bg level",
    "评分中…": "Scoring…", "真实底色": "true tint",
    # 导出格式附件
    "去星星云·JPG": "Starless · JPG", "纯星点·PNG": "Stars only · PNG", "标注 TXT": "Annotations TXT",
    # ── 验收补(2026-09-04):参数行标签 / 输入模式 / 流程路线 ──
    "GHS 拉伸力度 D": "GHS stretch D", "饱和度提升": "Saturation boost",
    "单步超时(秒)": "Step timeout (s)", "Ha 小红花强度": "Ha bloom strength",
    "外环迭代拉伸次数": "Outer-halo iterations", "核心保护阈值": "Core-protect threshold",
    "中央裁切比例": "Center crop ratio",
    "合回星点(取消勾选=仅输出去星 starless)": "Recombine stars (uncheck = starless only)",
    "完成后自动释放 PixInsight(交棒时必开)": "Release PixInsight when done (required for handoff)",
    "局部对比 LHE(暗尘细丝更立体)": "Local contrast (LHE) — depth for dust filaments",
    "拉伸力度评委自检(GHS 偏暗自动加大 D)": "Stretch self-check by reviewer (raise D if too dim)",
    "暗弱星云揭示(护亮核+护背景,提外围淡云)": "Reveal faint nebula (protect core & bg, lift outer haze)",
    "已叠加母版": "Stacked master", "对齐子帧目录": "Registered subframes", "原始素材叠加": "Stack from raw",
    "流程路线": "Pipeline route", "叠加": "Stack", "校准": "Calibrate", "梯度": "Gradient",
    "拉伸": "Stretch", "成片": "Final",
    "RGB 宽带真彩": "RGB broadband true color", "HOO 双窄带": "HOO dual-narrowband",
    "LRGB(H) 多通道": "LRGB(H) multi-channel", "SHO 窄带": "SHO narrowband",
    "共 {n} 个阶段 · 开始处理后逐段点亮;": "{n} stages · light up as processing runs;",
    "选定交棒点会停在对应阶段。": "the chosen handoff point stops at its stage.",
    "进行中": "In progress",
    # 流程路线逐步说明(PHASE_DESC)
    "整合对齐子帧 → 线性 master": "Integrate registered subframes → linear master",
    "裁黑边 · 色彩校准 SPCC/BNCC": "Crop edges · color calibration (SPCC/BNCC)",
    "梯度校正 · 背景中和": "Gradient correction · background neutralize",
    "GHS 拉伸 · 暗弱星云揭示": "GHS stretch · reveal faint nebula",
    "去星调色 · 合回星点 · 降噪": "Starless grading · recombine stars · denoise",
    "整合各通道 → 线性 master": "Integrate channels → linear master",
    "裁黑边 · BXT": "Crop edges · BXT", "梯度校正": "Gradient correction",
    "HOO 合成 · 拉伸": "HOO combine · stretch", "去星 · 输出成片": "Star removal · final image",
    "整合 L/R/G/B(/Ha) 各通道": "Integrate L/R/G/B(/Ha) channels",
    "统一裁边 · 背景匹配": "Uniform crop · background match",
    "RGB 合成 · superL": "RGB combine · superL", "拉伸 · 外环迭代": "Stretch · outer-halo iterations",
    "保色亮度替换 · 成片": "Color-preserving luminance · final",
    "整合 S/H/O 各通道": "Integrate S/H/O channels",
    "统一裁边 · 梯度校正 · BXT": "Uniform crop · gradient · BXT",
    "线性降噪 · 拉伸对齐": "Linear denoise · stretch & align",
    "SHO 合成 · 去星": "SHO combine · star removal",
    "调色 · 合回星点 · 成片": "Grading · recombine stars · final",
    "高级参数": "Advanced", "装好一次即可,共 6 项": "set once · 6 items",
    "背景梯度": "Background gradient", "星云揭示": "Nebula reveal",
    "无 PI · Siril 引擎": "No PI · Siril engine",
    "runner 在线": "runner online", "runner 忙·处理中": "runner busy · working", "runner 未运行": "runner offline",
    # ── 验收收尾补(2026-09-04):tooltip / 对话框 / 状态,批量包 t() 后补齐翻译 ──
    "AI 修改": "AI edit", "优化成片": "Optimize image", "分组": "Group", "删除这一晚": "Remove this night",
    "发现子帧和机内成片": "Found subframes and in-camera stacks", "启动超时": "Launch timed out",
    "在深色 / 亮色主题之间切换": "Toggle dark / light theme", "已释放": "Released",
    "按评分优化": "Optimize by score", "撤销上一步矫正/AI 操作": "Undo the last fix / AI action",
    "无法导出": "Cannot export", "未勾选任何组。": "No group selected.", "未找到 PixInsight": "PixInsight not found",
    "未配置 LLM 评委,无法评分。": "No LLM reviewer configured — cannot score.", "校准场库": "Calibration library",
    "正在处理": "Processing", "没有勾选任何项。": "Nothing selected.", "没有可处理的成片。": "No image to process.",
    "没有可导出的成片。": "No image to export.", "没有找到机内成片文件。": "No in-camera stack files found.",
    "清理": "Clean", "评分": "Score", "请填项目名。": "Please enter a project name.",
    "请先选择有效的校准场库根目录。": "Pick a valid calibration-library root folder first.",
    "请至少勾选一种导出格式。": "Select at least one export format.", "请选择有效的主图或目录。": "Pick a valid master image or folder.",
    "输入无效": "Invalid input", "还没有成片可改。": "No image to edit yet.", "配置不完整": "Incomplete setup",
    "重载完成": "Reload done", "需填偏置目录。": "A bias folder is required.",
    "GHS 拉伸强度 D(0~2.5)。偏暗加大、过曝减小;开启评委自检时会自动微调。":
        "GHS stretch strength D (0–2.5). Higher for dim, lower if over-exposed; auto-tuned when reviewer self-check is on.",
    "Ha 通道叠加进 R 的强度(0~2.0),0=不叠。": "Strength of blending Ha into R (0–2.0); 0 = off.",
    "JPG 导出质量(默认 95:画质与体积的甜点位)": "JPG quality (default 95 — the sweet spot of quality vs. size)",
    "LocalHistogramEqualization 只做在亮区(羽化蒙版),增强细丝/团块的立体层次,不动背景。":
        "LocalHistogramEqualization on bright areas only (feathered mask) — adds depth to filaments/clumps, leaves the background.",
    "PixInsight 已释放,可手动使用。": "PixInsight released — you can use it manually.",
    "PixInsight 路径、LLM 评委、AstroBin 后端等设置": "PixInsight path, LLM reviewer, AstroBin backend and other settings",
    "PixInsight/job-runner 未能在 90s 内就绪,请稍后重试。": "PixInsight/job-runner did not become ready within 90 s — please retry.",
    "RGB+窄带融合预设:galaxy=克制(Ha力度1.6、去饱和0.3);vivid=HII更跳(2.0)":
        "RGB+narrowband blend preset: galaxy = restrained (Ha 1.6, desat 0.3); vivid = punchier HII (2.0)",
    "TTAstroPiLot · 深空自动后期": "TTAstroPiLot · Deep-sky auto post-processing",
    "job-runner(PixInsight 内的作业执行器)在线状态": "job-runner (the executor inside PixInsight) online status",
    "maskstretch 迭代次数(0~6),越多外围越亮。": "maskstretch iterations (0–6); more brightens the outer regions.",
    "保存 .ttproj 工程(配置 + 成片 + 调色态)": "Save the .ttproj project (setup + result + color-grading state)",
    "偏色多是配色取向问题 → 用预览下方的配色切换条挑别的档":
        "A color cast is usually a palette choice — use the palette switcher below the preview to try another",
    "停止 job-runner/看门狗并结束 PixInsight,把 PI 交还给你手动使用":
        "Stop the job-runner/watchdog and close PixInsight, handing PI back to you",
    "再唤起一次 AI 评分(评分超时/失败,或想让评委再看一次时用;后台跑不阻塞)":
        "Run an AI score again (if it timed out/failed, or for a second look; runs in the background, non-blocking)",
    "分目标列出运行目录 _run 的中间产物,勾选清理;按钮上常显可清理体积":
        "List intermediate products in the _run directory per target to clean; the button shows the reclaimable size",
    "单步作业的最长等待时间,超时视为失败并中止。": "Max wait per step; a timeout counts as failure and aborts.",
    "原始素材叠加:每晚都需填亮场目录。": "Stack from raw: every night needs a lights folder.",
    "叠加前智能筛帧(去卫星线 + 去云帧)": "Smart frame culling before stacking (satellite trails + cloudy frames)",
    "在 优化前 / 优化后 之间切换预览对比": "Toggle preview between before / after optimization",
    "对当前图再跑一次 GradientCorrection": "Run GradientCorrection again on the current image",
    "对画好的圆做人工平场(也可直接在圆上双击)": "Apply a manual flat over the drawn circle (or double-click the circle)",
    "导出去星后的纯星云图(JPG)——星空 3D 视频的星云底":
        "Export the starless nebula (JPG) — nebula base for 3D star-field videos",
    "导出处理历史(在你自己的 PixInsight 里跑)": "Export the processing history (run in your own PixInsight)",
    "导出纯星点图(PNG)——星空 3D 视频的星点层":
        "Export the stars-only layer (PNG) — star layer for 3D star-field videos",
    "已用最新 job-runner.js 冷启 PixInsight,runner 就绪。": "Cold-started PixInsight with the latest job-runner.js — runner ready.",
    "库里没扫描到暗/偏/平校准场组(检查库根目录是否含 FITS)。":
        "No dark/bias/flat calibration sets found in the library (check the root folder contains FITS).",
    "扫描校准场库,按上述原则为每晚自动配齐暗/偏/平并回填。":
        "Scan the calibration library and auto-fill darks/bias/flats per night by the rules above.",
    "探测 BXT/SXT/NXT 等第三方模块与 PI 自带进程是否可用;缺失的给出下载/购买地址与安装步骤":
        "Check whether BXT/SXT/NXT and PI's built-in processes are available; for missing ones, show download/purchase links and install steps",
    "撤销「按评分优化」,恢复优化前的成片": "Undo “Optimize by score”, restore the pre-optimization image",
    "星云饱和度提升量(0~1.0)。SHO 流程内部会再叠加 0.35。": "Nebula saturation boost (0–1.0). SHO adds another 0.35 internally.",
    "有处理任务进行中,请先『中止』再释放。": "A processing task is running — “Abort” it before releasing.",
    "有处理任务进行中,请先『中止』再重载。": "A processing task is running — “Abort” it before reloading.",
    "未配置 LLM 评委,无法评分。": "No LLM reviewer configured — cannot score.",
    "未配置 LLM(在『配置』里设),无法用自然语言驱动修改。":
        "No LLM configured (set it in Settings) — natural-language edits unavailable.",
    "正在处理中,请等本次处理结束再清理(避免删到正在使用的中间文件)。":
        "Processing is running — wait until it finishes before cleaning (to avoid deleting in-use files).",
    "点亮后,在预览上按住拖出一个圆框住灰尘 → 出现『应用修复』按钮(所有配色档一起修)":
        "When active, drag a circle over the dust → “Apply fix” appears (fixes all palettes together)",
    "点亮后在预览上按住拖出一个圆框住灰尘 → 出现『应用修复』按钮":
        "When active, drag a circle over the dust → the “Apply fix” button appears",
    "直接复制成片 XISF(原始位深,无损)": "Copy the master XISF directly (original bit depth, lossless)",
    "确定性指标已达标(或背景为真实底色不宜中和),无需优化。":
        "Deterministic metrics already pass (or the background is a real tint not to be neutralized) — no optimization needed.",
    "经 PixInsight 全分辨率重导 JPG(需 runner 在线)": "Re-export full-resolution JPG via PixInsight (runner must be online)",
    "经 PixInsight 全分辨率重导 PNG(需 runner 在线)": "Re-export full-resolution PNG via PixInsight (runner must be online)",
    "统一裁掉四周对齐黑边的比例(0~0.4)。": "Fraction cropped from all edges to remove alignment borders (0–0.4).",
    "缺少成片 XISF,无法生成 PNG/JPG/星云星点/标注。": "No master XISF — cannot generate PNG/JPG/starless-stars/annotations.",
    "设置(PixInsight 路径 / LLM 评委 / 后端…)": "Settings (PixInsight path / LLM reviewer / backend…)",
    "请先填至少一晚(或一个通道)的亮场目录——自动匹配需读亮场特征。":
        "Fill in at least one night's (or channel's) lights folder first — auto-match reads the lights.",
    "请在『配置』里设置 PixInsight 路径。": "Set the PixInsight path in Settings.",
    "请在『配置』里设置 PixInsight 路径后再开始。": "Set the PixInsight path in Settings before starting.",
    "请在『配置』里设置 PixInsight 路径后再操作。": "Set the PixInsight path in Settings before continuing.",
    "请填「导出目录」——叠加中间产物体量巨大,请选一个空间充足的磁盘。":
        "Fill in the export folder — stacking intermediates are large, pick a disk with plenty of space.",
    "选择前面已生成的某个通道图(Ha/OIII/SII…)来做矫正 —— 合成前可回到任一通道":
        "Pick a previously generated channel (Ha/OIII/SII…) to fix — you can revisit any channel before combining",
    "随时点它 → 程序在当前步骤后停住,你可对当前图做 梯度矫正/灰尘修复,再继续":
        "Click any time → the pipeline pauses after the current step so you can run gradient / dust fixes, then resume",
    "项目名(导出文件名 / .ttproj 工程名)": "Project name (export filename / .ttproj name)",
    "高于该亮度的核心区不再被额外拉伸(0~1.0)。": "Core regions above this brightness get no extra stretch (0–1.0).",
    "黑白 per-filter:每个通道组都需填「通道亮场」目录。": "Mono per-filter: each channel group needs a channel-lights folder.",
    "黑白相机:需填偏置目录(全局共用)。": "Mono camera: a bias folder is required (shared globally).",
    "黑白相机:需填暗场父目录(内含各曝光时长子夹,程序按曝光自动配光)。":
        "Mono camera: a darks parent folder is required (with per-exposure subfolders; matched to lights by exposure).",
}
