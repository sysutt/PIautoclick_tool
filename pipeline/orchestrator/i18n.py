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
    "成片就绪后在此预览": "Preview appears here once ready",
    "就绪。选择流程与输入后点击「开始处理」。": "Ready. Pick a workflow and input, then click “Start”.",
    "还没有成片。到「处理」跑完流程后,评审与实测指标会出现在这里。":
        "No result yet. Run the pipeline in “Process” — the review and metrics will appear here.",
    "处理进行中…评审与实测指标会在完成后出现在这里。":
        "Processing… the review and metrics will appear here when it finishes.",
    # 主要按钮 / 操作
    "▶ 开始处理": "▶ Start", "▶ 继续": "▶ Resume", "■ 中止": "■ Abort", "⏸ 暂停介入": "⏸ Pause",
    "⏸ 将在当前步骤后暂停…": "⏸ Will pause after the current step…",
    "下一步:处理 →": "Next: Process →", "下一步:导出 →": "Next: Export →", "↓ 导出成片": "↓ Export", "在文件夹显示": "Show in folder",
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
    # ── tokenize 深包:下拉项 + 多行 tooltip(2026-09-04),技术代码保留 ──
    "全部四种 (推荐)": "All four (recommended)", "自然色 (natural)": "Natural color (natural)",
    "Ha红+SII青 (hss)": "Ha-red + SII-cyan (hss)", "洋红加蓝 (natural_blue)": "Magenta + blue (natural_blue)",
    "经典哈勃 (sho)": "Classic Hubble (sho)", "发射·中 (红丝)": "Emission · med (red filaments)",
    "发射·强 (红丝)": "Emission · strong (red filaments)",
    "金蓝 goldblue (OIII 有料,如巫师)": "Gold-blue goldblue (rich OIII, e.g. Wizard)",
    "暖橙 warm (Ha 主导,如狮子)": "Warm amber (Ha-dominant, e.g. Leo)",
    "自然 natural (SPCC真彩+GHS压核)": "Natural (SPCC true color + GHS core)",
    "浓郁 vivid (饱和更足)": "Vivid (more saturation)", "平拉 flat (关HDR最干净)": "Flat (HDR off, cleanest)",
    "星系 galaxy (M31式,克制)": "Galaxy (M31-style, restrained)", "浓郁 vivid (HII更跳)": "Vivid (punchier HII)",
    "跟随预设": "Follow preset", "平背景 d1": "Flat background d1", "多项式 d4": "Polynomial d4",
    "径向基 rbf": "Radial basis rbf", "两遍 4+rbf (梯度重)": "Two-pass 4+rbf (heavy gradient)",
    "关 0": "Off 0", "适度 0.5": "Moderate 0.5", "强 0.9": "Strong 0.9",
    "自动": "Auto", "强制清除": "Force clear", "关": "Off",
    "OIII主导 oiii (WR泡如SH2-308)": "OIII-dominant oiii (WR bubbles, e.g. SH2-308)",
    "均衡青红 classic (如IC1805心脏)": "Balanced teal-red classic (e.g. IC1805 Heart)",
    "自动检测": "Auto-detect", "强制开启": "Force on", "关闭 (推荐·暗 moody)": "Off (recommended · dark moody)",
    "自适应 (默认)": "Adaptive (default)", "Henry 忠实曲线": "Henry faithful curve",
    "自动 (推荐)": "Auto (recommended)", "更强": "Stronger", "更轻": "Lighter", "关闭": "Off",
    "DarkStructureEnhance 原生复刻:蒙版内压暗,加深暗尘/暗带、提升立体感。\n自动=有暗结构时施加 amount0.35(默认);更强=0.5;更轻=0.2;关闭=不做。\n(也可对任意已完成成片一键补做,见导出区旁的按钮。)":
        "Native DarkStructureEnhance: darkens within a mask, deepening dark dust/lanes and adding depth.\nAuto = apply amount 0.35 when dark structure is present (default); Stronger = 0.5; Lighter = 0.2; Off = skip.\n(Can also be applied to any finished image — see the button beside the export area.)",
    "GHS 拉伸后让 LLM 评委对照判断力度是否合适;\n报 too_dark/too_strong 且偏离当前值就按建议 D 重拉一次(仅一次)。需已配置 LLM。":
        "After the GHS stretch, let the LLM reviewer judge whether the strength is right;\nif it reports too_dark/too_strong and diverges from the current value, re-stretch once at the suggested D (once only). Requires a configured LLM.",
    "maskstretch(lum 蒙版+bgProtect):额外拉伸只作用在暗弱/中间调,\n把外围淡 Ha、弥漫云气抬起,亮核/暗湾/背景不动。低面亮度弥散星云尤其需要。":
        "maskstretch (luminance mask + bgProtect): the extra stretch acts only on faint/midtones,\nlifting outer faint Ha and diffuse gas while leaving bright core/dark bays/background. Especially for low-surface-brightness diffuse nebulae.",
    "勾选:HOO 双窄带全程零 PixInsight(Siril 提取 Ha/OIII + 线性 GraXpert 去梯度 +\nStarNet2 去星 + 分通道揭示 + DeepSNR + 背景中性灰)。输入选 OSC 双窄带 master 或子帧目录。":
        "Checked: HOO dual-narrowband entirely without PixInsight (Siril extracts Ha/OIII + linear GraXpert gradient removal +\nStarNet2 star removal + per-channel reveal + DeepSNR + neutral-gray background). Input: an OSC dual-narrowband master or subframe folder.",
    "勾选:SHO 全程零 PixInsight(Siril 整合 + StarNet2 去星 + GraXpert/DeepSNR AI 降噪\n+ GHS 揭示 + 比例控制器调色 + RGB 彩色星点)。输入请选 registered 目录(含各滤镜子目录)。":
        "Checked: SHO entirely without PixInsight (Siril integration + StarNet2 star removal + GraXpert/DeepSNR AI denoise\n+ GHS reveal + ratio-controller grading + RGB color stars). Input: a registered folder (with per-filter subfolders).",
    "勾选:纯 RGB 全程零 PixInsight(Siril 真 SPCC 光度校色 + GHS 压亮核 +\n带主体蒙版 DeepSNR 降噪)。输入选 OSC 单张 master 或子帧目录。\n真 SPCC 需装 Siril 本地 Gaia 星表(见依赖体检);未装则星场白平衡兜底。":
        "Checked: pure RGB entirely without PixInsight (Siril true SPCC photometric color calibration + GHS core compression +\nsubject-masked DeepSNR denoise). Input: an OSC single master or subframe folder.\nTrue SPCC needs Siril's local Gaia catalog (see dependency check); without it, star-field white balance is the fallback.",
    "只跑到选定步骤,产物导出到输出目录,后续你在 PixInsight 手工接管。\n例:选③ 就得到六通道 整合+裁边+梯度校正+BXT 的线性 master。":
        "Run only up to the chosen step, export the products to the output folder, then take over manually in PixInsight.\nE.g. choosing ③ yields a six-channel linear master (integration + crop + gradient correction + BXT).",
    "填双窄带(Ha/OIII)OSC master 或子帧目录 → 无 PI RGB 底上叠加 Ha/OIII 发射信号\n(星系旋臂 HII 红结、发射区)。留空 = 只做纯 RGB。\n配准以 RGB 为参考对齐窄带;成片后可用『🩹 灰尘修复』圈选中和残留灰尘投影。":
        "Fill in a dual-narrowband (Ha/OIII) OSC master or subframe folder → blend Ha/OIII emission onto the PI-free RGB base\n(HII red knots in galaxy arms, emission regions). Empty = pure RGB only.\nNarrowband is aligned to the RGB reference; after processing, use “🩹 Dust fix” to circle and neutralize leftover dust shadows.",
    "处理结束后自动停 runner/看门狗并结束 PI,把 PixInsight 交还给你。\n选了中间交棒点时尤其需要——否则你无法在 PI 里手工接着做。":
        "After processing, automatically stop the runner/watchdog and close PI, handing PixInsight back to you.\nEspecially needed when a mid-pipeline handoff point is chosen — otherwise you can't continue manually in PI.",
    "对任意已完成成片(含旧图)补做 DSE 暗结构强化:加深暗尘/暗带、提升立体感。\n选图 → 自动用 PI 处理(runner 不在线会自动拉起)→ 存为 <名>_DSE.png,不必重跑管线。":
        "Apply DSE dark-structure enhancement to any finished image (including old ones): deepen dark dust/lanes, add depth.\nPick an image → processed automatically in PI (runner auto-started if offline) → saved as <name>_DSE.png, no pipeline re-run.",
    "成片导出到这个目录,文件名自动用项目名(如 M54_260712_D3);点『导出成片』直接存、不弹窗。\n留空则导出时弹窗选文件夹(选完自动回填这里、下次免选)。":
        "The result is exported here, named automatically after the project (e.g. M54_260712_D3); “Export result” saves directly, no dialog.\nLeave empty and a folder picker appears on export (your choice is filled back here for next time).",
    "指向你的校准场库根目录(内含按次整理的暗场/偏置/平场各组文件夹)。\n点『🔎 自动匹配』→ 按统一原则为每晚配齐并回填上面各字段:\n  • 暗/偏:温度最接近 → 温度相同再取拍摄时间最接近\n  • 平场:时间最接近 → 时间相同再比温度(随灰尘/对焦变,时效优先)\n硬性条件先过滤:暗=曝光+增益、偏=增益、平=滤镜,尺寸须一致。免去手动一个个选文件夹。":
        "Point to your calibration-library root (with dark/bias/flat sets organized per session).\nClick “🔎 Auto-match” → fill every field above for each night by uniform rules:\n  • Darks/bias: closest temperature → if equal, closest capture time\n  • Flats: closest time → if equal, closest temperature (they drift with dust/focus, so recency wins)\nHard filters first: darks = exposure + gain, bias = gain, flats = filter; dimensions must match. No more picking folders one by one.",
    "按确定性质量指标一键补救(纯 numpy,秒出):背景偏色→中和;星点发闷→星蒙版提饱和。\n只动该动的、不重跑管线,存为新成片并刷新指标。":
        "One-click remediation by deterministic quality metrics (pure numpy, instant): color-cast background → neutralize; dull stars → star-masked saturation boost.\nTouches only what's needed, no pipeline re-run; saves a new result and refreshes the metrics.",
    "整合前对对齐子帧做两道质量筛选:\n① 残差霍夫检测卫星/飞机线,整帧剔除;\n② 逐帧背景鲁棒离群检测有云/低透明度帧(背景异常偏高),整帧剔除。\n各自超护栏比例时为保信噪自动跳过。仅在从子帧整合(模式②/③)时生效。\n【默认关】显著增加耗时;卫星线通常整合 rejection 就能排掉,有明显残留或云帧时再勾。":
        "Two quality passes on aligned subframes before integration:\n① Residual Hough detection of satellite/aircraft trails, rejecting whole frames;\n② Per-frame robust outlier detection of cloudy/low-transparency frames (abnormally high background), rejecting whole frames.\nEach auto-skips past its guardrail ratio to protect SNR. Active only when integrating from subframes (mode ②/③).\n[Off by default] adds significant time; satellite trails are usually removed by integration rejection anyway — enable it when there's obvious residue or cloudy frames.",
    "无 PI HOO 引擎预设:\noiii=OIII 主导目标(Ha弱→揭示狠、提蓝出青泡);classic=均衡青红双色":
        "PI-free HOO engine presets:\noiii = OIII-dominant targets (weak Ha → aggressive reveal, boost blue for teal bubbles); classic = balanced teal-red duotone",
    "无 PI RGB 引擎预设:\nnatural=SPCC 权威色 + 温和 GHS 压核 + 温和饱和(多数目标);\nvivid=饱和更足;flat=关 HDR 纯 autostretch(亮核稍爆但最干净,暗弱目标用)":
        "PI-free RGB engine presets:\nnatural = authoritative SPCC color + gentle GHS core + gentle saturation (most targets);\nvivid = more saturation; flat = HDR off, pure autostretch (core slightly blown but cleanest, for faint targets)",
    "无 PI 引擎调色预设(比例控制器旋钮组):\ngoldblue=金橙 + 蓝 OIII 核心;warm=暖 salmon + 蓝(Ha 极强的目标)":
        "PI-free engine grading presets (ratio-controller knobs):\ngoldblue = gold-amber + blue OIII core; warm = warm salmon + blue (targets with very strong Ha)",
    "星云区揭示强度(无 PI RGB):护亮核+护背景,只提暗弱/中间调星云。\n适度 0.5(M8 验证);强 0.9(暗弱外围淡云);关=不揭示;跟随预设=预设默认。\n『发射·中/强』:额外用**红色发射蒙版**专提faint红丝(马头 IC434 脊这类\n亮度蒙版抓不到的暗红发射;护星防环状伪影)。faint 红发射目标+足够积分时用。":
        "Nebula reveal strength (PI-free RGB): protects bright core + background, lifts only faint/midtone nebula.\nModerate 0.5 (verified on M8); Strong 0.9 (faint outer wisps); Off = no reveal; Follow preset = preset default.\n“Emission · med/strong”: additionally uses a red emission mask to lift faint red filaments (the Horsehead IC434 ridge and similar\ndim red emission a luminance mask misses; star-protected against ring artifacts). Use on faint-red-emission targets with enough integration.",
    "暗星云(象鼻/尘柱/暗带)内部层次常被压成死黑 → 提亮中间调揭示。\n默认关闭(暗 moody 克制调,外围不刻意提亮);自动检测=让评委按显著度定强度\n(每跑可能变,曾致淡区断层);强制开启=显式要揭示时用。":
        "Dark-nebula (elephant trunks/dust pillars/dark lanes) inner detail is often crushed to dead black → lift midtones to reveal.\nOff by default (dark moody restraint, no forced brightening of the outskirts); Auto-detect = let the reviewer set strength by prominence\n(may vary per run, has caused banding in faint areas); Force on = when you explicitly want the reveal.",
    "有天文解析时,用 AnnotateImage 标注 Messier/NGC/IC/SH2 + HIP/TYC/GAIA 恒星,\n导出天体列表(名称/类型/像素坐标/星等)TXT —— 供结合纯星点图做 3D 建模":
        "When an astrometric solution exists, use AnnotateImage to label Messier/NGC/IC/SH2 + HIP/TYC/GAIA stars,\nand export an object list (name/type/pixel coords/magnitude) TXT — for 3D modeling together with the stars-only image.",
    "残留辉光清除(成片后 ABE 式,补线性去梯度漏掉的局部残留辉光+色偏,如角落 amp glow/光污染的品红角)。\n自动=检测到大尺度背景落差/色偏才清(图已均匀则不动,IC434 验证);强制清除=总是清;\n关=不清。护星护云(最暗分位采样)。朝银心/银河的真实弥漫别强清 → 那种情形选『关』。":
        "Residual-glow removal (post-processing, ABE-style; cleans up local residual glow + color cast the linear gradient removal missed, e.g. corner amp glow / magenta light-pollution corners).\nAuto = clean only when a large-scale background offset/cast is detected (leaves already-even images alone, verified on IC434); Force clear = always clean;\nOff = don't clean. Protects stars and gas (samples the darkest quantile). Don't force-clean genuine diffuse toward the galactic center/Milky Way → choose “Off” there.",
    "生成一个独立小脚本,让你在**自己平时的 PixInsight** 里手动处理完后运行一次,\n把每一步进程的**全部精确参数**(HT黑/中/白点、GHS的D/b/SP、曲线控制点…)导出成文本。\n不走本工具的 runner:runner 占着 PI、手动交互处理会卡。用它给自动流程做量化参考。":
        "Generate a small standalone script to run once in your own everyday PixInsight after you finish processing manually,\nexporting every exact parameter of each process step (HT black/mid/white points, GHS D/b/SP, curve control points…) as text.\nIt doesn't use this tool's runner — the runner holds PI and would stall interactive work. Use it as a quantitative reference for the automated pipeline.",
    "结束 PixInsight 并冷启动,加载**最新的 job-runner.js**(改了 runner 脚本后点它生效;\n也可用来恢复卡死/异常的 runner)。PI 的 -r 脚本只在启动时加载一次,故需冷启。":
        "Close PixInsight and cold-start it, loading the latest job-runner.js (click after editing the runner script to apply it;\nalso recovers a hung/misbehaving runner). PI's -r script loads only once at startup, so a cold start is required.",
    "背景梯度提取(无 PI RGB,线性阶段 subsky):\n平背景 d1=一阶(轻倾斜);d4=四阶多项式(四角梯度);rbf=径向基(不对称/复杂);\n4+rbf=两遍(d4 压主梯度 + rbf 清残留,低空/光污染重梯度,M8 验证)。\n朝银心/银河方向的残留亮度是真实天光,别过度压平。跟随预设=引擎默认(d1)。":
        "Background gradient extraction (PI-free RGB, linear-stage subsky):\nFlat d1 = first order (slight tilt); d4 = fourth-order polynomial (four-corner gradient); rbf = radial basis (asymmetric/complex);\n4+rbf = two-pass (d4 knocks down the main gradient + rbf clears residue; low-altitude / heavy light-pollution gradients, verified on M8).\nResidual brightness toward the galactic center/Milky Way is real skyglow — don't over-flatten. Follow preset = engine default (d1).",
    "自适应=去绿 + 黄区加红 + 提饱和,偏自然暖调(默认,推荐)。\nHenry 忠实曲线=按播主 .xpsm 转录的 8 通道曲线,鲜艳粉紫;\n适合 OIII 充足的均衡目标,Ha 主导目标会压成单色红,慎用。":
        "Adaptive = remove green + add red in the yellows + boost saturation, a natural warm tone (default, recommended).\nHenry faithful curve = the 8-channel curve transcribed from the streamer's .xpsm, vivid pink-purple;\nsuits OIII-rich balanced targets; Ha-dominant targets get crushed into monochrome red — use with care.",
    "选一个文件夹,按 FITS 头+文件名自动识别亮场/暗场/机内成片等 → 回填下面字段;识别到机内成片时可选择重新叠加或直接优化成片":
        "Pick a folder; lights/darks/in-camera stacks etc. are auto-detected from FITS headers + filenames → fields below are filled in; when an in-camera stack is found, choose to re-stack or optimize it directly.",
    "配色是主观档 → 默认四种都生成供你挑(NGC1499 定稿):\nhss=Ha 红 + SII 青(层次最好);natural=Ha红/OIII蓝/SII橙(最真);\nnatural_blue=洋红加蓝;sho=经典哈勃(自动去绿成金青调 + 黄区加红)":
        "Palette is a subjective choice → all four are generated by default for you to pick (finalized on NGC1499):\nhss = Ha-red + SII-cyan (best depth); natural = Ha-red/OIII-blue/SII-orange (most true);\nnatural_blue = magenta + blue; sho = classic Hubble (auto green-removal to gold-teal + red in the yellows)",
    # ── QMessageBox 标题 / QFileDialog 标题+过滤器(2026-09-04)──
    "TTAstroPiLot 工程 (*.ttproj)": "TTAstroPiLot project (*.ttproj)",
    "启动失败": "Launch failed", "导出失败": "Export failed", "导出完成": "Export complete",
    "释放失败": "Release failed", "确认删除": "Confirm deletion", "确认导出目录": "Confirm export folder",
    "自动识别": "Auto-detect", "暗结构强化": "Dark-structure enhance",
    "图像 (*.png *.jpg *.jpeg *.tif *.tiff *.xisf)": "Images (*.png *.jpg *.jpeg *.tif *.tiff *.xisf)",
    "图像 (*.xisf *.fit *.fits)": "Images (*.xisf *.fit *.fits)", "成片 (*.xisf *.png *.jpg)": "Result (*.xisf *.png *.jpg)",
    "导出成片(选择基名,自动加各格式后缀)": "Export result (pick a base name; format suffixes are added automatically)",
    "选择 registered 目录": "Pick the registered folder", "选择主图": "Pick the master image",
    "选择双窄带 Ha/OIII master 或子帧目录": "Pick a dual-narrowband Ha/OIII master or subframe folder",
    "选择文件": "Pick a file", "选择暗场文件夹": "Pick the darks folder", "选择目录": "Pick a folder",
    "保存工程 · 选择位置": "Save project · choose location",
    "选择素材文件夹(自动识别亮/暗场·机内成片)": "Pick a material folder (auto-detect lights/darks · in-camera stacks)",
    "选择要加暗结构的成片": "Pick the image to add dark structure to",
    "将停止 job-runner / 看门狗并结束所有 PixInsight 进程,之后你可手动使用 PI。\n确定?":
        "This will stop the job-runner / watchdog and end all PixInsight processes, after which you can use PI manually.\nProceed?",
    "未匹配到符合硬性条件(曝光/增益/滤镜/尺寸)的校准场。\n请检查库里是否有与本次亮场同曝光/增益/滤镜/尺寸的校准场组。":
        "No calibration frames matched the hard conditions (exposure/gain/filter/dimensions).\nCheck whether the library has a calibration set with the same exposure/gain/filter/dimensions as these lights.",
    # ── 运行时模板 .format() / 按钮 / 裸 PAL 标签(2026-09-04)──
    '(未配置 LLM 评委)': '(no LLM reviewer configured)',
    '{} 需要暗场,但此文件夹里没识别到(暗场通常在单独的 DWARF_DARK 文件夹)。\n现在去选暗场文件夹吗?': '{} needs darks, but none were detected in this folder (darks are usually in a separate DWARF_DARK folder).\nPick a darks folder now?',
    '{} 项 · 已按流程过滤': '{} shown · filtered by workflow',
    '{}:必须提供与亮场温度匹配的暗场,否则热噪严重。': "{}: darks matching the lights' temperature are required, or thermal noise will be severe.",
    '{}:每晚都需填平场目录。': '{}: every night needs a flats folder.',
    '{}失败:{}': '{} failed: {}',
    '优化机内成片': 'Optimize in-camera stack',
    '依赖缺失:{}': 'Missing dependency: {}',
    '再定位脚本': 'Locate script again',
    '叠加的中间产物(逐帧校准/去马赛克/对齐子帧)体量巨大,将全部写入:\n\n    {}\n\n请确认该磁盘剩余空间充足。是否开始叠加?': 'Stacking intermediates (per-frame calibration / debayer / aligned subframes) are very large and will all be written to:\n\n    {}\n\nPlease confirm this disk has enough free space. Start stacking?',
    '可在『选通道图』里挑前面生成的任一通道图,再做 梯度矫正 / 灰尘修复 / 跟 AI 说想法': 'In “Pick channel” you can choose any earlier-generated channel, then do gradient fix / dust fix / talk to the AI',
    '可对当前图做 梯度矫正 / 灰尘修复 / 跟 AI 说想法': 'You can run gradient fix / dust fix / talk to the AI on the current image',
    '失败:{}': 'Failed: {}',
    '完成 · 用时 {:02d}:{:02d}': 'Done · {:02d}:{:02d}',
    '完成,已保存:\n{}': 'Done, saved:\n{}',
    '将删除 {} 项,释放约 {}。\n此操作不可恢复,确定?': 'Will delete {} item(s), freeing about {}.\nThis cannot be undone. Proceed?',
    '已停在【{}】· 交棒': 'Stopped at 【{}】 · handoff',
    '已出成片 · {}': 'Result ready · {}',
    '已暂停 · {}': 'Paused · {}',
    '已暂停 · 当前【{}】。{},或点继续。': 'Paused · now 【{}】. {}, or click Resume.',
    '已用 {:02d}:{:02d} · 预计剩余 ~{:02d}:{:02d}  ·  步骤 {}/5': 'Elapsed {:02d}:{:02d} · ETA ~{:02d}:{:02d}  ·  step {}/5',
    '当前档【{}】尚未评分。': "This palette 【{}】 hasn't been scored yet.",
    '当前档【{}】未单独评分 —— 评委只评了主版【{}】。四档同基底,差异只在配色。': "This palette 【{}】 wasn't scored separately — the reviewer only scored the main version 【{}】. All four share one base; only the palette differs.",
    '探测失败:{}': 'Probe failed: {}',
    '未识别到可叠加的亮场子帧。\n{}': 'No stackable light subframes detected.\n{}',
    '查看结果': 'View result',
    '生成导出脚本失败:{}\n模板:{}': 'Failed to generate the export script: {}\nTemplate: {}',
    '用时 {:02d}:{:02d}': 'Took {:02d}:{:02d}',
    '第 {} 晚': 'Night {}',
    '第 {} 组': 'Group {}',
    '记录每一步精确参数,用你**自己平时的 PixInsight**、全程手动——不用本工具的 runner\n(runner 在跑轮询循环、占着 PI,那个实例里做交互式处理会卡、会和它抢视图)。\n\n步骤:\n① 正常打开你的 PI,打开并手动处理你的图(拉伸/调色随你怎么调);\n② 菜单 Script ▸ Execute Script File… ▸ 选中这个(已帮你在资源管理器里定位):\n      {}\n    运行(或按 F9);\n③ 它会 dump **所有打开窗口**的历史(不用你手动选窗口;历史常分在\n    masterLight / 主图 等多个视图里,一次全抓)到:\n      {}\n    然后回来点『查看结果』,或直接把该文件发我。\n\n⚠ 关键:PixInsight **不把历史存进磁盘**。必须**同一次会话**里处理完就跑脚本、\n   别关 PI —— 存盘后重开的图历史是空的(0 步)。标注/预览这类新渲染视图也没历史。': "Records every exact parameter — done entirely by hand in your own everyday PixInsight, not this tool's runner\n(the runner is polling and holding PI; interactive work in that instance would stall and fight it for views).\n\nSteps:\n① Open your PI normally, open and process your image by hand (stretch/grade however you like);\n② Menu Script ▸ Execute Script File… ▸ select this one (already located for you in Explorer):\n      {}\n    run it (or press F9);\n③ It dumps the history of all open windows (no need to pick windows; history is often split across\n    masterLight / the main view etc. — all captured at once) to:\n      {}\n    then come back and click “View result”, or just send me that file.\n\n⚠ Key: PixInsight does not save history to disk. You must run the script in the same session right after processing,\n   and don't close PI — a reopened saved image has empty history (0 steps). Freshly rendered views like annotate/preview have no history either.",
    '评分不可用:{}': 'Scoring unavailable: {}',
    '评分失败:{}': 'Scoring failed: {}',
    '评这一档 · {}': 'Score this one · {}',
    '识别到 {} 张子帧亮场 + {} 张机内成片。\n重新叠加子帧(质量更好、更慢),还是直接优化机内成片(快)?': 'Detected {} light subframes + {} in-camera stacks.\nRe-stack the subframes (better quality, slower), or optimize the in-camera stack directly (fast)?',
    '读不了成片:{}': "Can't read the result: {}",
    '运行目录 _run 可清理中间产物合计 <b>{}</b>。成片已在你的输出根(如 M:/Deepsky),这里都是可重建的中间文件。勾选要删除的项(预览图默认不选):': 'Reclaimable intermediates in the _run directory total <b>{}</b>. Your results are already in your output root (e.g. M:/Deepsky); everything here is rebuildable intermediate files. Check the items to delete (previews unchecked by default):',
    '还没找到结果文件:\n{}\n\n请先在你的 PixInsight 里运行导出脚本(Script ▸ Execute Script File),再回来点『查看结果』。': 'Result file not found yet:\n{}\n\nRun the export script in your PixInsight first (Script ▸ Execute Script File), then come back and click “View result”.',
    '通道组需「亮场+平场」成对:现有亮场 {} 个、平场 {} 个。': 'Channel groups need lights+flats in pairs: {} lights, {} flats present.',
    '重新叠加子帧': 'Re-stack subframes',
    '阶段 {}/{} · {}': 'Phase {}/{} · {}',
    '需填暗场目录。': 'A darks folder is required.',
    'Ha红+SII青': 'Ha-red + SII-cyan',
    '自然色': 'Natural color',
    '洋红加蓝': 'Magenta + blue',
    '经典哈勃': 'Classic Hubble',
}
