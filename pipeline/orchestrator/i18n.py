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
}
