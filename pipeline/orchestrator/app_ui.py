"""TTAstroPiLot · 深空自动后期 · 一键式桌面界面(PyQt5)。

选输入 → 选流程(RGB/HOO/LRGB)→ 一键跑完(自动启动 PixInsight + job-runner),
带分步进度、预计剩余、中止;完成后 LLM 评分卡 + 导出/在文件夹显示。深/亮双主题。
视觉重构 2026-09:近黑冷中性地色 + 唯一信号绿 #55DDA0(IBM Plex Mono 数据字 + 全局 ~4.6s 呼吸)。
运行:  python -m orchestrator.app_ui
"""
from __future__ import annotations


import os
import shutil       # 清理中间文件 / 分组挪帧用;原来只在个别函数里局部导入,这两处漏了 → NameError 被全局钩子吞掉,按钮像没反应
import subprocess
import sys
import time
import traceback
from pathlib import Path

from PyQt5.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt,
                          QThread, QTimer, pyqtProperty, pyqtSignal)
from PyQt5.QtGui import (QBrush, QColor, QFontDatabase, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                         QPixmap, QRadialGradient, QTextCursor)
from PyQt5.QtWidgets import (
    QMenu,
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QButtonGroup,
    QLabel, QLayout, QLineEdit, QPushButton, QCheckBox, QDoubleSpinBox, QSpinBox,
    QPlainTextEdit, QFileDialog, QMessageBox, QFrame, QProgressBar,
    QScrollArea, QSizePolicy, QStackedWidget, QComboBox, QToolButton, QSlider,
    QGraphicsOpacityEffect, QDialog,
)

from . import config, protocol, pipeline
from . import critic
from . import devices
from . import icons
from .i18n import t, set_lang as _i18n_set_lang, to_zh as _to_zh
from .settings_ui import SettingsWindow

# ---- 视觉重构 2026-09:近黑冷中性地色 + 唯一信号绿 #55DDA0(去青蓝第二强调色/彩虹徽章)----
# 两套调色板键名必须完全一致:QSS 只认 qss(p) 里的键,别处不要写死色值。
# accent* = 信号绿,唯一强调(进行中 / 主路径 / 主按钮 / 数值 / 已完成);
# sec*    = 历史"第二强调色",现全部指向同一信号绿(双强调已收敛为单色;键名保留,免改散落各处引用);
# line/line2 = 白色极低透明度发丝线(仅在 QSS 边框里用,不可传给 QColor);
# warn=琥珀(交棒/不可选) · danger=珊瑚红 · ai=克制的信息蓝(LLM 评委标记)。
# 注意:凡会被 QColor(...) 读的键(stroke/accent/sec/*非 soft/line/ghost)必须是 #hex;
#       *_soft/*_line/*_ghost/line/line2 是 rgba() 字串,只能出现在 QSS 文本里。
# logtext/logmark(2026-09-06 新增):日志/预览/路线图是**数据面,两套主题下都保持深底**(设计原则
#   "深底只给数据面",浅色主题=春野绿设计稿定稿)——深底上的文字/光标/扫线不能用会随主题变深的
#   text2/sec,必须走这两个专用键(dark=沿用原值;light=暗底可读的浅鼠尾草)。
MONO_STACK = '"IBM Plex Mono","Cascadia Mono",Consolas,ui-monospace,monospace'   # 数据/数字/拉丁标签
SANS_STACK = '"Noto Sans SC","Microsoft YaHei","Segoe UI",-apple-system,sans-serif'  # 中文 UI

# 随程序打包的 IBM Plex Mono(OFL-1.1,orchestrator/assets/fonts/)——定稿科技数据字,
# 不依赖系统是否装。Qt 用排版族名把 4 权重并进单一 "IBM Plex Mono"(QSS font-weight 500/600/bold 正确映射)。
# 没装/加载失败也无妨:MONO_STACK 会回落 Cascadia Mono→Consolas,不影响功能。
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONTS_LOADED = False


def _load_bundled_fonts() -> None:
    """把 assets/fonts 下的 .ttf 注册进 QFontDatabase。需已有 QApplication(故在窗口 __init__ 里调,
    不在 import 期);只跑一次(多开窗/离屏渲染都幂等)。任何异常静默吞掉——字体是装饰,绝不该让 UI 崩。"""
    global _FONTS_LOADED
    if _FONTS_LOADED:
        return
    try:
        from PyQt5.QtWidgets import QApplication
        if QApplication.instance() is None:      # 没有 app 实例时 addApplicationFont 无效
            return
        if FONT_DIR.is_dir():
            for ttf in sorted(FONT_DIR.glob("*.ttf")):
                QFontDatabase.addApplicationFont(str(ttf))
        _FONTS_LOADED = True
    except Exception:
        pass

# 【精修(用户 2026-10-10「像半成品」,设计稿 artifact 7f1qvMWZK7BE1FpQ5ATsjK「设计规范」板)】
#   地色 / 面板 / 卡片 / 控件 / 选中 五级表面拉开但都带一点冷蓝;发丝线 #1E2530 取代白色半透明线;
#   次要文字 #98A3B2→#A9B2C0、说明文字 #5C6675→#7C8696(原来在近黑底上对比度只有 ~3:1,读不清)。
#   panel = 顶栏/导航/页脚/侧栏(比卡片更深一档);danger_line = 危险按钮的暗红描边。
DARK = dict(bg="#0A0D12", surf1="#10141B", surf2="#161B24", surf3="#1A212C", surf4="#232B37",
            stroke="#262E3B", panel="#0D1117",
            accent_bg="#12261E", accent_edge="#2A5A45", on_accent="#06140D",
            ontext="#E6EAF0", onmuted="#7C8696",
            line="#1E2530", line2="#2E3746",
            accent="#55DDA0", accent_hi="#6BE6AF", accent_press="#3FA87C", accent_hover="#7CEAA6",
            accent_dim="#3FA87C",
            accent_soft="rgba(85,221,160,28)", accent_line="rgba(85,221,160,71)",
            accent_ghost="rgba(85,221,160,18)",
            sec="#55DDA0", sec_hi="#6BE6AF",
            sec_soft="rgba(85,221,160,28)", sec_line="rgba(85,221,160,71)",
            text="#E6EAF0", text2="#A9B2C0", muted="#7C8696",
            info="#69AFD6", info_soft="rgba(105,175,214,26)", info_line="rgba(105,175,214,77)",
            warn="#E2AC61", warn_soft="rgba(226,172,97,30)", danger="#E8706E", danger_line="#5B2F31",
            ai="#69AFD6",
            logbg="#0A0D12", prevbg="#05070A",
            logtext="#98A3B2", logmark="#55DDA0")
# 浅色主题 = 春野绿(用户 2026-09-06 定稿,参照三星 Galaxy 视觉;设计稿 artifact ff915bb3):
#   暖白地 #F3F3F0 · 森林绿行动 #3A4A40(=accent,兼数值文字,深色在浅底可读)· 鼠尾草选中软填充 ·
#   数据蓝收敛为钢青 #4A6FA5(info)· 进度条 accent_dim→accent = 鼠尾草→森林的丝带扫过 ·
#   日志/预览/路线图仍深底(见 logtext/logmark 注)。柔薰紫方向被用户判"AI 软件俗套"弃选。
LIGHT = dict(bg="#F3F3F0", surf1="#FFFFFF", surf2="#F4F6F1", surf3="#E9EDE6", surf4="#DCE2D8",
             stroke="#BFC9BC", panel="#FFFFFF",
             accent_bg="#E2EAE3", accent_edge="#9FB5A6", on_accent="#FFFFFF",
             ontext="#E4E8E2", onmuted="#8A938C",
             line="rgba(23,28,24,34)", line2="rgba(23,28,24,56)",
             accent="#3A4A40", accent_hi="#46584C", accent_press="#2C382F", accent_hover="#52655A",
             accent_dim="#8FB49B",
             accent_soft="rgba(90,124,98,56)", accent_line="rgba(58,74,64,115)",
             accent_ghost="rgba(90,124,98,26)",
             sec="#3A4A40", sec_hi="#46584C",
             sec_soft="rgba(90,124,98,56)", sec_line="rgba(58,74,64,115)",
             text="#171C18", text2="#4E5852", muted="#869088",
             info="#4A6FA5", info_soft="rgba(74,111,165,28)", info_line="rgba(74,111,165,100)",
             warn="#A9690F", warn_soft="rgba(190,130,40,34)", danger="#BE4B41",
             danger_line="rgba(190,75,65,110)", ai="#4A6FA5",
             logbg="#10140F", prevbg="#0F1411",
             logtext="#9CC7A6", logmark="#8FB49B")

# SHO 配色档(顺序必须与 cb_palette 下拉项一致;NGC1499 定稿,旧 warm/teal/pink 已废弃)
PALETTES = ["hss", "natural", "natural_blue", "sho"]
PAL_LABELS = {"hss": "Ha红+SII青", "natural": "自然色", "natural_blue": "洋红加蓝", "sho": "经典哈勃",
              "hoo": "HOO 双色"}
# 评委"退回哪一步"用的阶段中文名(与 stop_after 词表对应)
STAGE_CN = {"integrate": "整合", "crop_gc": "裁边+梯度", "crop": "裁边", "gradient": "梯度校正",
            "bxt": "BXT", "denoise": "降噪", "stretch": "拉伸", "combine": "合成",
            "starless": "去星/星点", "color": "调色", "colorcal": "色彩校准", "final": "成片"}

PHASES = ["叠加", "梯度", "校准", "拉伸", "成片"]
# op → 阶段索引(单调推进,取已见最大)。**顺序必须与 run_rgb 实际执行序一致**:
#   整合 → 裁边/梯度校正/BXT(线性几何) → 板解/SPCC 色彩校准 → 拉伸/揭示/分星 → 去绿调色/合星/输出。
#   两个此前的错映射已修:①梯度(GC r01)在色彩校准(SPCC r03)**之前**,故 gradient=1、colorcal=2;
#   ②线性降噪(r05,拉伸前)归"校准"段(denoise=2),别再 denoise=4 让进度条早早跳到"成片"。
_OP_PHASE = {"integrate": 0, "rgbcombine": 0,
             "crop": 1, "gradient": 1, "deconv": 1, "dustremove": 1, "polybg": 1,
             "solve": 2, "applywcs": 2, "colorcal": 2, "denoise": 2,
             "stretch": 3, "ghs": 3, "maskstretch": 3, "lrgb": 3, "hoo": 3,
             "starsep": 3, "hdr": 3, "hdrblend": 3,
             "scnr": 4, "redemph": 4, "curves": 4, "lhe": 4, "darkstruct": 4,
             "rangemask": 4, "recombine": 4, "hablend": 4}
# 各流程预估 op 数(驱动进度条 + ETA)。**必须≈实际 step 数**,否则进度条提前跑满、ETA 归零(用户 2026-09-06:
#   加了边缘预裁/局部检测/去绿/星点饱和闭环等步骤后,run_rgb 典型 ~24-26 个 step;旧值 14 太低)。宁可略高
#   (末尾从 ~90% 跳 100%)也别太低(99% 卡半天)。星系/窄带路径更多、略超 99% 无妨。
_EXPECTED = {"rgb": 26, "hoo": 22, "lrgb": 34}

# 各流程 5 个阶段(叠加·梯度·校准·拉伸·成片)的一句话说明(右侧路线图用;不参与进度计算)。
# 与 PHASES/_OP_PHASE 的顺序对齐:梯度(裁边/梯度/BXT)在色彩校准(SPCC)之前。
PHASE_DESC = {
    "rgb": ["整合对齐子帧 → 线性 master", "裁黑边 · 梯度校正 GC/ABE · BXT 锐化",
            "板解 · 色彩校准 SPCC/BNCC · 线性降噪", "GHS 拉伸 · 暗弱星云揭示 · 分离星点",
            "去绿 · 饱和调色 · 局部对比 · 合回星点"],
    "hoo": ["整合各通道 → 线性 master", "裁黑边 · 梯度校正 · BXT",
            "背景中和 · 线性对齐", "各通道拉伸 · HOO 合成",
            "去绿调色 · 去星/合星 · 输出成片"],
    "lrgb": ["整合 L/R/G/B(/Ha) 各通道", "统一裁边 · 梯度校正 · BXT",
             "背景匹配 · RGB 合成 · superL", "拉伸 · 外环迭代",
             "保色亮度替换 · 调色 · 成片"],
    "sho": ["整合 S/H/O 各通道", "统一裁边 · 梯度校正 · BXT",
            "线性降噪 · 背景对齐", "拉伸对齐 · SHO 合成",
            "调色 · 去星/合星 · 成片"],
}
FLOW_TIPS = {
    "rgb": "OSC 彩色相机宽带:裁边 → 梯度 → BXT → SPCC → 拉伸 → 去星调色 → 合星",
    "hoo": "Ha/OIII 双窄带映射 HOO:裁边 → 梯度 → BXT → HOO 合成 → 去星",
    "lrgb": "L+R+G+B(+Ha) 分通道:整合 → 背景匹配 → RGB 合成/superL → 色彩校准 → 保色亮度替换",
    "sho": "SII/Ha/OIII 三窄带:整合 → 裁边梯度 → BXT → 降噪 → 拉伸对齐 → SHO 合成 → 去星 → 调色",
}
MODE_NAMES = ["已叠加母版", "对齐子帧目录", "原始素材叠加"]
MODE_TIPS = [
    "已经叠加好的一张主图,直接进后期",
    "registered 对齐子帧目录,先整合再后期;多通道 LRGB / SHO 也走这里",
    "原始素材叠加:彩色相机(亮/平/暗/偏)或智能望远镜(Seestar 仅亮场 / Dwarf 需温度匹配暗场)→ WBPP 后整合(OSC 流程)",
]

# 原始叠加·设备预设:每个预设声明各校准场的策略(亮场恒为必填,不列)。
#   req=必填 · opt=可选 · reqtemp=必填且需与亮场温度匹配(否则热噪) · skip=该设备无此项(不适用)
STACK_DEVICES = [
    ("osc", "彩色相机 (OSC)", {"flat": "req", "dark": "req", "bias": "req"},
     "常规彩色/单反相机:每晚亮场+平场配对,暗场/偏置全项目共用(四项齐全)。"),
    ("mono", "黑白相机 (per-filter)", {"flat": "req", "dark": "reqtemp", "bias": "req"},
     "黑白相机(冷冻):**每通道一组=该通道亮场+该通道平场**(下面每行填一个通道的亮/平)。"
     "程序不打标签、读真实 FILTER 头 → WBPP 自动按滤镜分组;平场按 FILTER 配光、暗场按曝光配光、偏置全局。"
     "暗场填父目录(含各曝光子夹)即可,程序按曝光自动配。"),
    ("seestar", "Seestar", {"flat": "opt", "dark": "opt", "bias": "opt"},
     "Seestar:一般只需亮场(设备内已做基础校准)。平场/暗场/偏置可选填,没有也能叠加。"),
    ("dwarf", "Dwarf", {"flat": "skip", "dark": "reqtemp", "bias": "skip"},
     "Dwarf:只用亮场+暗场(暗场需与亮场温度匹配)。平场/偏置实测帮助不大且易引入问题,留空即可。开始前会校验暗场温度。"),
]
STACK_DEV_MAP = {k: (label, pol, hint) for k, label, pol, hint in STACK_DEVICES}
# OSC 亮场的滤镜标签(用户 2026-09-04:窄带就是普通亮场、只是滤镜不同 → 按滤镜分组叠加)。
#   宽带=IR-UVcut → RGB 底;双窄带(Hα/OIII、SII/OIII、Hβ/SII)→ 各成一组 master 供融合。
#   key 用于分组/路由;第一项为默认(宽带)。
OSC_FILTERS = [("uvir", "IR-UVcut (宽带)"), ("hoo", "Hα/OIII"), ("soo", "SII/OIII"), ("hbo", "Hβ/SII")]
OSC_FILTER_KEYS = [k for k, _ in OSC_FILTERS]
# 黑白相机:一个滤镜一张母版(用户 2026-09-28:「宽带图像合并窄带信号不需要区分彩色还是黑白相机」)。
#   宽带 R/G/B 先合成一张 RGB 当底(L 暂不参与),窄带 Hα/OIII 各是一层;之后与彩色相机走同一套融合。
#   SII 能识别,但现有几种融合方式只用 Hα/OIII,选了会在日志里说明不参与。
MONO_FILTERS = [("R", "R"), ("G", "G"), ("B", "B"), ("L", "L"), ("Ha", "Hα"), ("OIII", "OIII"), ("SII", "SII")]
BB_FILTER_KEYS = {"uvir", "L", "R", "G", "B"}          # 宽带(当 RGB 底);其余都是窄带


def _is_bb(fk) -> bool:
    """这个滤镜键是不是宽带(彩色相机的 IR-UVcut,或黑白的 L/R/G/B)。"""
    return (fk or "uvir") in BB_FILTER_KEYS


def _reg_project_dir(d: str) -> str:
    """对齐子帧目录 → 它所属的**项目目录**(完整路径)。WBPP 的结构是 `<项目>/registered/<各晚子夹>`,
    往上跳出 registered;不在 registered 结构里的散目录取它的上一级 —— 母版别存进子帧目录本身。"""
    p0 = Path(str(d or "").replace("\\", "/"))
    p = p0
    for _ in range(3):
        if p.name.lower() in ("registered", "master", "calibrated", "debayered", "lights", "light"):
            p = p.parent
        elif p.parent.name.lower() == "registered":
            p = p.parent.parent
        else:
            break
    if p == p0:
        p = p0.parent
    return str(p).replace("\\", "/")
# 帧特征识别(设备/类型/温度)统一在 devices 模块;温度读取见 devices.frame_temp / dir_temp


def qss(p):
    _plus = icons.png_path(icons.PLUS, "plus", p['sec'])      # 数值步进 加/减 图标(随主题 sec 上色)
    _minus = icons.png_path(icons.MINUS, "minus", p['sec'])
    _plusm = icons.png_path(icons.PLUS, "plusm", p['muted'])  # 禁用态(灰)
    _minusm = icons.png_path(icons.MINUS, "minusm", p['muted'])
    _check = icons.png_path(icons.CHECK, "check", p['bg'], 12)   # 勾选态对勾(深色,压在绿底上)
    return f"""
QWidget {{ background:{p['bg']}; color:{p['text']}; font-family:{SANS_STACK}; font-size:13px; }}
QLabel {{ background:transparent; }}
/* 布局用的空容器(参数行/分段条/子页)不能吃全局 QWidget 的窗口底色,否则在卡片里显示成
   一条条比底色更深的横带。_polish_groups() 给所有未命名的纯容器统一打上 #rowbg。 */
QWidget#rowbg {{ background:transparent; }}
QToolTip {{ background:{p['surf1']}; color:{p['text']}; border:1px solid {p['stroke']}; padding:6px 8px; }}

/* ---- 窗口骨架 ---- */
QFrame#headerbar {{ background:{p['panel']}; border-bottom:1px solid {p['line']}; }}
QFrame#hairline {{ background:{p['line']}; }}
QFrame#ribbon {{ background:{p['panel']}; border-bottom:1px solid {p['line']}; }}
QFrame#actionbar {{ background:{p['panel']}; border-top:1px solid {p['line']}; }}
QFrame#card {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:10px; }}
QFrame#cardhead {{ background:transparent; border:none; border-bottom:1px solid {p['line']}; }}

/* ---- 字号层级 ---- */
#banner {{ font-size:15px; font-weight:600; color:{p['text']}; }}
#sub {{ color:{p['muted']}; font-size:12px; }}
#cardtitle {{ font-size:13px; font-weight:bold; color:{p['text2']}; }}
#primlabel {{ font-size:13px; font-weight:600; color:{p['text']}; }}
#plabel {{ font-size:13px; color:{p['text2']}; }}
#seclabel {{ font-size:11px; font-weight:bold; color:{p['sec']}; font-family:{MONO_STACK}; }}
QLabel#mono {{ font-family:{MONO_STACK}; color:{p['text2']}; font-size:11px; }}
QFrame#statuspill {{ border-radius:14px; }}
QFrame#roadpanel {{ background:{p['prevbg']}; border:1px dashed {p['stroke']}; border-radius:10px; }}
QLabel#warnnote {{ background:{p['warn_soft']}; border:1px solid {p['warn']}; border-radius:6px;
                   padding:7px 9px; color:{p['warn']}; font-size:11px; }}

/* ---- 分组框 ----
   内边距**不用** QSS 的 QGroupBox padding —— 它在 QGroupBox 上左右不对称(右侧控件会贴边
   甚至溢出边框)。统一由 _polish_groups() 设布局 contentsMargins。 */
QGroupBox {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:10px; margin-top:14px; padding:0; }}
/* 标题带**组框底色背景**遮住身后的边框线,横跨上边框呈"缺口"效果,不再压在线上显乱 */
QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:14px; padding:1px 8px;
                    background:{p['surf1']}; color:{p['muted']}; font-weight:600; font-size:11px; }}
QGroupBox#gb_main {{ border:1px solid {p['accent_line']}; margin-top:0; }}
QGroupBox#gb_quiet {{ margin-top:0; }}
/* 卡片头条:平底 + 分隔线(精修 2026-10-10:去掉绿渐变;「当前步」由卡片的绿描边 + 实心序号表达) */
QFrame#stripaccent {{ border:none; border-bottom:1px solid {p['line']};
    border-top-left-radius:9px; border-top-right-radius:9px; background:transparent; }}
QFrame#stripquiet {{ background:transparent; border:none; border-bottom:1px solid {p['line']}; }}
QLabel#badgeon {{ background:{p['accent']}; color:{p['bg']}; border-radius:10px;
                  font-size:11px; font-weight:bold; }}
QLabel#badgeoff {{ background:transparent; color:{p['muted']}; border:1px solid {p['stroke']};
                   border-radius:10px; font-size:11px; font-weight:bold; }}
QLabel#striptitle {{ font-size:13px; font-weight:bold; color:{p['text']}; }}
QFrame#scorebar {{ border:none; border-radius:3px;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {p['accent']}, stop:1 {p['info']}); }}
QLabel#progstage {{ font-size:11.5px; font-weight:bold; color:{p['accent']}; }}
QLabel#striptitle2 {{ font-size:12.5px; font-weight:bold; color:{p['text2']}; }}
QGroupBox#gb_result {{ border:1px solid {p['line']}; margin-top:0; }}
QGroupBox#gb_prog {{ border:1px solid {p['accent_line']}; border-radius:8px; margin-top:0; }}
QGroupBox#gb_prog::title {{ padding:0; }}

/* ---- 行容器 ---- */
QWidget#paramrow {{ background:transparent; border:none; border-bottom:1px solid {p['line']}; border-radius:0; }}
QWidget#primrow {{ background:transparent; border:none; border-bottom:1px solid {p['line']}; border-radius:0; }}
QWidget#roadrow {{ background:{p['surf3']}; border:1px solid {p['line']}; border-radius:8px; }}
QWidget#roadrow:hover {{ border:1px solid {p['sec_line']}; }}
QWidget#roadrow_on {{ background:{p['accent_soft']}; border:1px solid {p['accent_line']}; border-radius:8px; }}
QWidget#nightrow {{ background:{p['surf3']}; border:1px solid {p['line']}; border-radius:7px; }}

/* ---- 输入控件 ---- */
QLineEdit, QComboBox {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px;
                        padding:5px 10px; color:{p['text']}; min-height:20px;
                        selection-background-color:{p['accent']}; selection-color:{p['bg']}; }}
QDoubleSpinBox, QSpinBox {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px;
                            padding:4px 8px; color:{p['text']}; font-family:{MONO_STACK}; font-weight:500; min-height:20px;
                            selection-background-color:{p['accent']}; selection-color:{p['bg']}; }}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border:1px solid {p['line2']}; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border:1px solid {p['accent']}; }}
/* 数值框上下箭头:一旦给 up-button/down-button 上样式,原生箭头就不画了,
   必须用 QSS 的三角形写法(width/height 归零 + 三边 border)把箭头补回来。 */
QDoubleSpinBox::up-button, QSpinBox::up-button {{
    subcontrol-origin:border; subcontrol-position:top right;
    width:16px; height:11px; background:{p['surf1']};
    border-left:1px solid {p['stroke']}; border-bottom:1px solid {p['stroke']};
    border-top-right-radius:5px; }}
QDoubleSpinBox::down-button, QSpinBox::down-button {{
    subcontrol-origin:border; subcontrol-position:bottom right;
    width:16px; height:11px; background:{p['surf1']};
    border-left:1px solid {p['stroke']}; border-bottom-right-radius:5px; }}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{ background:{p['surf2']}; }}
/* 加/减(±)图标:up=加、down=减(SVG 渲染的 PNG,随主题上色);替代原来的小三角 */
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{ width:11px; height:11px; image:url("{_plus}"); }}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{ width:11px; height:11px; image:url("{_minus}"); }}
QDoubleSpinBox::up-arrow:disabled, QSpinBox::up-arrow:disabled {{ image:url("{_plusm}"); }}
QDoubleSpinBox::down-arrow:disabled, QSpinBox::down-arrow:disabled {{ image:url("{_minusm}"); }}
QComboBox::drop-down {{ width:20px; border:none; }}
QComboBox QAbstractItemView {{ background:{p['surf1']}; border:1px solid {p['stroke']}; padding:4px;
                               selection-background-color:{p['surf4']}; selection-color:{p['text']}; outline:none; }}

/* ---- 按钮 ---- */
/* 去描边:边框改透明(保持尺寸不跳),质感靠 _apply_button_shadows 的浅投影 + hover 换底色 */
/* outline:none 去掉点击后的默认焦点框(Qt 用调色板高亮=accent 绿画,浅色下尤其扎眼;用户 2026-09-06 保存键绿边) */
QPushButton, QToolButton {{ outline:none; }}
QPushButton {{ background:{p['surf3']}; border:1px solid {p['line2']}; border-radius:6px;
               padding:5px 12px; color:{p['text2']}; min-height:20px; }}
QPushButton:hover {{ background:{p['surf4']}; color:{p['text']}; }}
QPushButton:pressed {{ background:{p['surf2']}; }}
QPushButton:disabled {{ background:transparent; border:1px solid {p['line']}; color:{p['muted']}; }}
QPushButton#ghost {{ border-radius:14px; padding:5px 13px; }}
QPushButton#tab {{ background:transparent; border:none; border-bottom:3px solid transparent;
                   border-radius:0; padding:10px 20px 8px 20px; color:{p['text2']}; font-size:13px; }}
QPushButton#tab:hover {{ background:{p['accent_ghost']}; color:{p['text']}; }}
QPushButton#tab:checked {{ background:{p['accent_ghost']}; border-bottom:3px solid {p['accent']};
                           color:{p['accent']}; font-weight:bold; }}
QPushButton#seg {{ background:{p['surf2']}; border:1px solid transparent; border-radius:6px;
                   padding:6px 12px; color:{p['muted']}; }}
QPushButton#seg:hover {{ background:{p['surf3']}; color:{p['text2']}; }}
/* 选中态的底由 SlideIndicator(会滑动的药丸)画成中性灰蓝(surf4),按钮让位透明、文字提亮 */
QPushButton#seg:checked {{ background:transparent; border:1px solid transparent;
                           color:{p['text']}; font-weight:600; }}
QPushButton#seg:disabled {{ background:transparent; border:1px solid transparent; color:{p['muted']}; }}
/* segaccent:需要被一眼看到的**建议动作**(如校准库『自动匹配』)——绿底绿字的软填充,比主按钮克制 */
QPushButton#segaccent {{ background:{p['accent_soft']}; border:1px solid {p['accent_line']}; border-radius:6px;
                         padding:6px 12px; color:{p['accent']}; font-weight:600; }}
QPushButton#segaccent:hover {{ background:{p['accent_line']}; }}
QPushButton#segaccent:pressed {{ background:{p['accent_soft']}; }}
QPushButton#segaccent:disabled {{ background:{p['surf2']}; border:1px solid transparent; color:{p['muted']}; }}
/* segdev:设备行等**无 SlideIndicator** 的段按钮 —— 选中态**自带实心 accent 背景 + 深色字**(否则 #seg 的
   透明底+深字在无绿药丸时看不见)。底/悬停同 #seg。 */
QPushButton#segdev {{ background:{p['surf2']}; border:1px solid transparent; border-radius:6px;
                      padding:6px 12px; color:{p['muted']}; }}
QPushButton#segdev:hover {{ background:{p['surf3']}; color:{p['text2']}; }}
QPushButton#segdev:checked {{ background:{p['surf4']}; border:1px solid {p['line2']};
                              color:{p['text']}; font-weight:600; }}
QPushButton#segdev:disabled {{ background:{p['surf2']}; border:1px solid transparent; color:{p['muted']}; }}
QPushButton#sectoggle {{ background:transparent; border:1px dashed {p['stroke']}; border-radius:6px;
                         padding:6px 11px; color:{p['text2']}; text-align:left; }}
QPushButton#sectoggle:hover {{ background:{p['surf3']}; color:{p['text']}; }}
QPushButton#sectoggle:checked {{ background:{p['surf3']}; }}
QPushButton#primary {{ background:{p['accent']};
                       color:{p['bg']}; border:none; border-radius:6px; font-weight:600; font-size:13px;
                       padding:9px 18px; min-height:20px; }}
QPushButton#primary:hover {{ background:{p['accent_hi']}; }}
QPushButton#primary:pressed {{ background:{p['accent_press']}; }}
/* disabled/处理中:清晰的实心底(surf3)+ 描边 + 可读文字 —— 否则 surf2 太贴近面板底、
   叠上处理态绿微光扫过后基底看不见,像个「镂空缺背景」的按钮(用户 2026-09-04 反馈) */
QPushButton#primary:disabled {{ background:{p['surf3']}; color:{p['text2']}; border:1px solid {p['stroke']}; }}
QPushButton#danger {{ background:transparent; border:1px solid {p['danger_line']}; color:{p['danger']}; }}
QPushButton#danger:hover {{ background:{p['surf2']}; border:1px solid {p['danger']}; color:{p['danger']}; }}
QToolButton {{ background:{p['surf3']}; border:1px solid {p['line2']}; border-radius:6px;
               padding:5px 9px; color:{p['text2']}; min-height:20px; }}
QToolButton:hover {{ background:{p['surf4']}; color:{p['text']}; }}

/* ---- 勾选 / 滑块 / 进度 ---- */
QCheckBox {{ background:transparent; color:{p['text2']}; padding:2px 0; spacing:9px; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {p['line2']}; border-radius:4px; background:{p['surf2']}; }}
QCheckBox::indicator:hover {{ border:1.5px solid {p['accent']}; background:{p['sec_soft']}; }}
QCheckBox::indicator:checked {{ background:{p['accent']}; border:1.5px solid {p['accent']}; image:url("{_check}"); }}
QCheckBox::indicator:checked:hover {{ background:{p['accent_hi']}; border:1.5px solid {p['accent_hi']}; }}
QCheckBox::indicator:disabled {{ border:1.5px solid {p['surf2']}; background:{p['surf1']}; }}
QCheckBox:disabled {{ color:{p['muted']}; }}
QSlider::groove:horizontal {{ height:4px; background:{p['line']}; border-radius:2px; }}
QSlider::sub-page:horizontal {{ background:{p['accent']}; border-radius:2px; }}
/* 浅色滑钮 + 半透明行动绿外圈(设计稿:白钮 + 绿光圈);外圈用 border 画,margin 让钮压在轨道正中 */
QSlider::handle:horizontal {{ width:10px; height:10px; margin:-6px 0; border-radius:8px;
                              background:{p['text']}; border:3px solid {p['accent_line']}; }}
QSlider::handle:horizontal:hover {{ border:3px solid {p['accent']}; }}
QSlider::sub-page:horizontal:disabled {{ background:{p['stroke']}; }}
QSlider::handle:horizontal:disabled {{ background:{p['stroke']}; border:1px solid {p['stroke']}; }}
QProgressBar {{ background:{p['line']}; border:none; border-radius:3px; height:6px; text-align:center; color:transparent; }}
QProgressBar::chunk {{ background:{p['accent']}; border-radius:3px; }}

/* ---- 日志 / 预览 ---- */
QPlainTextEdit {{ background:{p['logbg']}; border:1px solid {p['line']}; border-radius:8px; padding:8px 10px;
                  color:{p['logtext']}; font-family:{MONO_STACK}; font-size:11px; }}
#preview {{ background:{p['prevbg']}; color:{p['logtext']}; border:1px solid {p['stroke']}; border-radius:10px; font-size:12px; }}

/* ---- 滚动 ---- */
QScrollArea#leftscroll {{ background:transparent; border:none; }}
QScrollArea#leftscroll > QWidget > QWidget {{ background:transparent; }}
QScrollArea#rightscroll {{ background:transparent; border:none; }}
QScrollArea#rightscroll > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{p['surf3']}; border-radius:5px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{p['stroke']}; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:{p['surf3']}; border-radius:5px; min-width:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}

/* ---- 多页 IA:顶栏件 / 阶段导航 / 屏 / 流程卡 / 项目卡 / 页脚 ---- */
QLabel#eyebrow {{ font-size:11px; font-weight:600; color:{p['muted']}; }}
QLabel#h2 {{ font-size:20px; font-weight:600; color:{p['text']}; }}
QLabel#lead {{ color:{p['text2']}; font-size:13px; }}
QLabel#ver {{ font-family:{MONO_STACK}; font-size:11px; color:{p['muted']}; }}
/* 顶栏(精修 2026-10-10):标记方块 / 竖分隔 / 项目名 / 图标按钮 / 工具菜单 */
QLabel#logotile {{ background:{p['accent_bg']}; border:1px solid {p['accent_edge']}; border-radius:8px; }}
QFrame#vdiv {{ background:{p['line']}; border:none; }}
QFrame#projchip {{ background:transparent; border:none; }}
QLineEdit#projname {{ background:transparent; border:1px solid transparent; border-radius:6px; color:{p['text']};
                      font-size:14px; font-weight:600; padding:3px 6px; min-height:18px; }}
QLineEdit#projname:hover {{ border:1px solid {p['line']}; }}
QLineEdit#projname:focus {{ border:1px solid {p['accent']}; background:{p['surf2']}; }}
QLabel#saveddot {{ background:{p['accent']}; border-radius:3px; }}
QLabel#saveddot[dirty="true"] {{ background:{p['warn']}; }}
QLabel#savedtag {{ font-size:12px; color:{p['muted']}; }}
QLabel#savedtag[dirty="true"] {{ color:{p['warn']}; }}
/* 尺寸必须写在 QSS 里:通用 QPushButton 规则的 min-height 会盖掉代码里 setFixedSize 的下限 */
QToolButton#chipbtn {{ background:transparent; border:1px solid transparent; border-radius:6px; padding:0;
                       min-width:24px; max-width:24px; min-height:24px; max-height:24px; }}
QToolButton#chipbtn:hover {{ background:{p['surf3']}; border:1px solid {p['line2']}; }}
QPushButton#iconbtn, QToolButton#iconbtn {{ background:transparent; border:1px solid {p['line']};
                       border-radius:6px; padding:0; min-width:30px; max-width:30px; min-height:30px; max-height:30px; }}
QPushButton#iconbtn:hover, QToolButton#iconbtn:hover {{ background:{p['surf3']}; border:1px solid {p['line2']}; }}
QToolButton#toolsbtn {{ background:transparent; border:1px solid {p['line']}; border-radius:6px;
                       padding:0 10px; color:{p['text2']}; min-height:30px; max-height:30px; }}
QToolButton#toolsbtn:hover, QToolButton#toolsbtn:pressed {{ background:{p['surf3']}; border:1px solid {p['line2']};
                       color:{p['text']}; }}
QToolButton#toolsbtn::menu-indicator {{ image:none; width:0px; }}
QMenu {{ background:{p['surf1']}; border:1px solid {p['line2']}; border-radius:8px; padding:4px; }}
QMenu::item {{ background:transparent; color:{p['text']}; padding:7px 24px 7px 12px; border-radius:5px; }}
QMenu::item:selected {{ background:{p['surf4']}; }}
QMenu::item:disabled {{ color:{p['muted']}; }}
QMenu::separator {{ height:1px; background:{p['line']}; margin:4px 6px; }}
/* 步骤导航:圆形序号由 _step_badge 画成图标;当前步 = 浅绿底药丸,已完成 = 绿圈对勾 + 绿连线 */
QPushButton#step {{ background:transparent; border:none; border-radius:6px; padding:0 10px;
                    color:{p['muted']}; min-height:32px; max-height:32px; }}
QPushButton#step[done="true"] {{ color:{p['text2']}; }}
QPushButton#step:hover {{ background:{p['surf2']}; color:{p['text2']}; }}
QPushButton#step:checked {{ background:{p['accent_bg']}; color:{p['text']}; font-weight:600; }}
QFrame#stepline {{ background:{p['line2']}; border:none; }}
QFrame#stepline[done="true"] {{ background:{p['accent_edge']}; }}
/* 底部状态栏 */
QLabel#statustext {{ font-size:12px; color:{p['muted']}; }}
QLabel#statusmono {{ font-family:{MONO_STACK}; font-size:12px; color:{p['muted']}; }}
QPushButton#linkbtn {{ background:transparent; border:none; padding:0; min-height:0; color:{p['info']}; font-size:12px; }}
QPushButton#linkbtn:hover {{ color:{p['text']}; }}
QFrame#langbox {{ background:transparent; border:1px solid {p['line']}; border-radius:6px; }}
QPushButton#langseg {{ background:transparent; border:none; border-radius:5px; padding:0 10px;
                       min-height:26px; max-height:26px;
                       color:{p['muted']}; font-family:{MONO_STACK}; font-size:11px; }}
QPushButton#langseg:hover {{ color:{p['text2']}; }}
/* 语言开关的"当前语言"必须一眼可辨(用户 2026-09-11:界面已是英文,却以为开关显示中文)。
   langseg 与 segdev 同类:**无 SlideIndicator 绿药丸**,选中态若用 surf3(它同时是 #seg/#segdev 的悬停色
   和普通行底色)在近黑地色上几乎看不出来 → 用户分不清当前是中还是 EN。照 #segdev:checked 的成例用实心
   强调绿 + 深字 + 加粗。*/
QPushButton#langseg:checked {{ background:{p['accent']}; color:{p['bg']}; font-weight:bold; }}
QToolButton#gear {{ background:{p['surf2']}; border:1px solid {p['line']}; border-radius:7px;
                    padding:4px 7px; color:{p['text2']}; }}
QToolButton#gear:hover {{ background:{p['surf3']}; color:{p['text']}; }}
/* 阶段导航 */
QFrame#navbar {{ background:{p['panel']}; border-bottom:1px solid {p['line']}; }}
QPushButton#nav {{ background:transparent; border:none; border-radius:0; padding:11px 14px;
                   color:{p['muted']}; font-size:12.5px; }}
QPushButton#nav:hover {{ color:{p['text2']}; }}
/* 选中态只变亮不加粗:加粗会让文字变宽、被 FlowBar 量好的按钮宽裁掉(与 mockup 一致:仅提亮 + 下划线) */
QPushButton#nav:checked {{ color:{p['text']}; }}
QWidget#screen {{ background:transparent; }}
QWidget#screenscroll {{ background:transparent; }}
QScrollArea#screenscroll {{ background:transparent; border:none; }}
/* 流程卡 */
QFrame#flowcard {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:10px; }}
QFrame#flowcard:hover {{ border:1px solid {p['line2']}; }}
QFrame#flowcard[sel="true"] {{ border:1px solid {p['accent']}; background:{p['surf1']}; }}
QLabel#flowname {{ font-size:15px; font-weight:600; color:{p['text']}; }}
QLabel#flowdesc {{ font-size:12px; color:{p['text2']}; }}
QLabel#seltag {{ font-size:11px; color:{p['accent']}; background:{p['accent_bg']}; border-radius:10px; padding:2px 8px; }}
/* 配置屏(第四步):大纲 / 分段控件 / 素材卡 / 底栏 */
QFrame#outline {{ background:{p['panel']}; border:none; border-right:1px solid {p['line']}; }}
QFrame#outrow {{ background:transparent; border:none; border-radius:8px; }}
QFrame#outrow:hover {{ background:{p['surf1']}; }}
QFrame#outrow[cur="true"] {{ background:{p['surf2']}; }}
QLabel#outtitle {{ font-weight:600; color:{p['text']}; }}
QLabel#outsub {{ font-size:12px; color:{p['muted']}; }}
QFrame#segbox QPushButton#seg, QFrame#segbox QPushButton#segdev {{ background:transparent; border:none; border-radius:4px;
    padding:0 12px; min-height:30px; max-height:30px; color:{p['muted']}; font-weight:normal; }}
QFrame#segbox QPushButton#seg:hover, QFrame#segbox QPushButton#segdev:hover {{ color:{p['text2']}; }}
QFrame#segbox QPushButton#seg:checked {{ background:transparent; color:{p['text']}; }}
QFrame#segbox QPushButton#segdev:checked {{ background:{p['surf4']}; color:{p['text']}; border:none; }}
QFrame#segbox QPushButton:disabled {{ color:{p['stroke']}; }}
QWidget#srccard {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:10px; }}
QFrame#setupbar {{ background:{p['panel']}; border:none; border-top:1px solid {p['line']}; }}
/* 导出屏 */
QFrame#exportframe {{ background:{p['prevbg']}; border:1px solid {p['line']}; border-radius:12px; }}
QGroupBox#exportbox {{ background:transparent; border:none; margin-top:0; padding:0; }}
QFrame#optcard {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:8px; }}
QFrame#optcard:hover {{ border:1px solid {p['line2']}; }}
QFrame#optcard[on="true"] {{ border:1px solid {p['accent_edge']}; }}
QLabel#opttitle {{ font-weight:600; color:{p['text']}; }}
QLabel#optsize {{ font-family:{MONO_STACK}; font-size:12px; color:{p['text2']}; }}
QLabel#histname {{ font-family:{MONO_STACK}; font-size:12px; color:{p['text']}; }}
QLabel#flowtick {{ color:{p['accent']}; font-family:{MONO_STACK}; font-size:12px; }}
/* 项目卡 */
QFrame#projcard {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:10px; }}
/* 项目库(第四步):大标题 / 分段筛选 / 搜索框 / 继续上次大卡 / 卡片字 */
QLabel#h1 {{ font-size:24px; font-weight:600; color:{p['text']}; }}
QFrame#segbox {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:6px; }}
QFrame#segbox QPushButton#segin {{ background:transparent; border:none; border-radius:4px; padding:0 10px;
                                   min-height:26px; max-height:26px; color:{p['muted']}; font-size:12px; }}
QFrame#segbox QPushButton#segin:hover {{ color:{p['text2']}; }}
QFrame#segbox QPushButton#segin:checked {{ background:{p['surf4']}; color:{p['text']}; }}
QLineEdit#searchbox {{ background:{p['surf1']}; border:1px solid {p['line']}; padding:5px 8px; }}
QFrame#herocard {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:12px; }}
QFrame#herocard:hover {{ border:1px solid {p['line2']}; }}
QLabel#heroname {{ font-size:22px; font-weight:600; color:{p['text']}; }}
QLabel#herometa {{ font-size:13px; color:{p['text2']}; }}
QLabel#cardname {{ font-size:14px; font-weight:600; color:{p['text']}; }}
QLabel#carddate {{ font-family:{MONO_STACK}; font-size:11px; color:{p['muted']}; }}
QLabel#cardflow {{ font-size:12px; color:{p['text2']}; }}
QLabel#cardcam {{ font-size:12px; color:{p['muted']}; }}
QFrame#projcard:hover {{ border:1px solid {p['line2']}; }}
QFrame#projcard_new {{ background:{p['surf1']}; border:1px dashed {p['stroke']}; border-radius:11px; }}
QFrame#projcard_new:hover {{ background:{p['surf2']}; border:1px dashed {p['accent_line']}; }}
QLabel#exportprev {{ background:transparent; border:none; color:{p['onmuted']}; font-size:12px; }}
QLabel#projname_c {{ font-size:13.5px; font-weight:600; color:{p['text']}; }}
QLabel#projmeta {{ font-family:{MONO_STACK}; font-size:10px; color:{p['muted']}; }}
/* 页脚(维护工具) */
QFrame#footerbar {{ background:{p['panel']}; border-top:1px solid {p['line']}; }}
/* ---- 第三步:处理屏检查器 / 取景器 / 时间线 / 日志抽屉 / 审阅侧栏 ---- */
QFrame#inspector {{ background:{p['panel']}; border:none; border-right:1px solid {p['line']}; }}
QFrame#reviewaside {{ background:{p['panel']}; border:none; border-left:1px solid {p['line']}; }}
QFrame#inspector QScrollArea, QFrame#reviewaside QScrollArea {{ background:transparent; border:none; }}
QFrame#inspector QScrollArea > QWidget > QWidget, QFrame#reviewaside QScrollArea > QWidget > QWidget {{ background:transparent; }}
QLabel#insptitle {{ font-size:16px; font-weight:600; color:{p['text']}; }}
QLabel#inspchip {{ font-size:12px; color:{p['text2']}; background:{p['surf3']}; border-radius:10px; padding:3px 8px; }}
QLabel#secthead {{ font-size:11px; font-weight:600; color:{p['muted']}; }}
QWidget#insprow {{ background:transparent; border:none; }}
QWidget#insprow QLabel#primlabel, QWidget#insprow QLabel#plabel, QWidget#insprow QLabel#dim {{
    font-weight:normal; color:{p['text2']}; }}
QFrame#runcard {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:10px; }}
QGroupBox#runprog {{ background:transparent; border:none; margin-top:0; padding:0; }}
QFrame#asidefoot {{ background:transparent; border:none; border-top:1px solid {p['line']}; }}
/* 取景器:工具条在地色上,看图区一律深底(两个主题都是 —— 深底只给图像) */
QFrame#viewer {{ background:transparent; border:none; border-radius:0; }}
QFrame#viewer QFrame#cardhead {{ background:{p['bg']}; border:none; border-bottom:1px solid {p['line']}; }}
QFrame#viewer QLabel#cardtitle {{ font-size:13px; font-weight:600; color:{p['text']}; }}
QScrollArea#panescroll {{ background:{p['prevbg']}; border:none; }}
QScrollArea#panescroll > QWidget > QWidget {{ background:{p['prevbg']}; }}
QScrollArea#previewscroll {{ background:transparent; border:none; }}
QScrollArea#previewscroll > QWidget > QWidget {{ background:transparent; }}
QFrame#viewer #preview {{ border:none; border-radius:0; }}
QLabel#roadtitle {{ font-size:13px; font-weight:600; color:{p['ontext']}; background:transparent; }}
QLabel#roadsub {{ font-size:12px; color:{p['onmuted']}; background:transparent; }}
QFrame#timeline {{ background:{p['panel']}; border:none; border-top:1px solid {p['line']}; }}
QFrame#logdrawer {{ background:{p['panel']}; border:none; border-top:1px solid {p['line']}; }}
QLabel#drawertitle {{ font-size:12px; font-weight:600; color:{p['text']}; }}
QPlainTextEdit#drawerlog {{ border:none; border-radius:0; border-top:1px solid {p['line']}; }}
QFrame#statuspill {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:14px; }}
QLabel#statuspilltext {{ font-size:12px; color:{p['text2']}; background:transparent; }}
/* 取景器叠层标题 */
QLabel#viewtitle {{ font-size:14px; font-weight:bold; color:{p['text']}; }}
QLabel#viewsub {{ font-family:{MONO_STACK}; font-size:10px; color:{p['text2']}; }}
/* 审阅双面板:评审(评分条 green→blue) + 实测指标(数值蓝) */
QFrame#panel {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:10px; }}
QLabel#paneltitle {{ font-size:12px; color:{p['text2']}; }}
QLabel#panelvia {{ font-family:{MONO_STACK}; font-size:9px; color:{p['muted']}; }}
QLabel#bigscore {{ font-family:{MONO_STACK}; font-weight:500; font-size:40px; color:{p['text']}; }}
QLabel#barlabel {{ font-size:11px; color:{p['text2']}; }}
QLabel#barval {{ font-family:{MONO_STACK}; font-size:11px; color:{p['text']}; }}
QProgressBar#scoreprog {{ background:{p['surf4']}; border:none; border-radius:2px; }}
QProgressBar#scoreprog::chunk {{ border-radius:2px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {p['accent']}, stop:1 {p['info']}); }}
QLabel#metrickey {{ font-size:13px; color:{p['text']}; }}
QLabel#metricref {{ font-size:12px; color:{p['muted']}; }}
QLabel#metricval {{ font-family:{MONO_STACK}; font-size:14px; color:{p['info']}; font-weight:500; }}
QLabel#pillok {{ background:{p['accent_bg']}; color:{p['accent']}; border-radius:9px; padding:2px 8px; font-size:11px; }}
QLabel#pillbad {{ background:{p['warn_soft']}; color:{p['warn']}; border-radius:9px; padding:2px 8px; font-size:11px; }}
QFrame#metricsep {{ background:{p['line']}; border:none; }}
QLabel#metrictag {{ font-family:{MONO_STACK}; font-size:9px; color:{p['muted']};
                    border:1px solid {p['line']}; border-radius:4px; padding:1px 5px; }}
"""



def _sexa_deg(txt: str, is_ra: bool):
    """'13 30 05.278' / '+47 10 03.90' → 度。认不出返回 None。"""
    try:
        parts = str(txt).replace(":", " ").split()
        if not parts:
            return None
        sign = -1.0 if parts[0].lstrip().startswith("-") else 1.0
        vals = [abs(float(x)) for x in parts[:3]]
        while len(vals) < 3:
            vals.append(0.0)
        deg = sign * (vals[0] + vals[1] / 60.0 + vals[2] / 3600.0)
        return deg * 15.0 if is_ra else deg
    except (TypeError, ValueError):
        return None


def _designation(text: str) -> str:
    """认星表编号 —— 实现在 colorprefs,这里只是转发(存和取必须用同一套规则)。"""
    try:
        from . import colorprefs as _cp
        return _cp.designation(text)
    except Exception:
        return ""

class FlowLayout(QLayout):
    """按可用宽度自动**换行**的布局。

    用途:窗口变窄时,分段按钮 / 操作按钮 / 阶段标签**折行**而不是被裁掉看不见
    (QHBoxLayout 的最小宽度=所有子项之和,窗口一窄就把右边的按钮挤出可视区)。
    `stretch=True` 时同一行内的子项等分剩余宽度 → 分段控件在宽窗口下仍铺满一行。
    """

    def __init__(self, parent=None, margin=0, hspace=8, vspace=8, stretch=False):
        super().__init__(parent)
        self._items = []
        self._hs, self._vs, self._stretch = hspace, vspace, stretch
        self.setContentsMargins(margin, margin, margin, margin)

    # --- QLayout 必须实现的接口 ---
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Horizontal)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._layout(QRect(0, 0, w, 0), test_only=True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._layout(r, test_only=False)

    def sizeHint(self):
        # **首选**尺寸=全部排在一行的宽度。不能返回 minimumSize:上层若用 Maximum/Fixed
        # 尺寸策略,会把容器宽度锁在"单个按钮"上,于是两个按钮永远被迫折成两行。
        return self.singleLineSize()

    def singleLineSize(self):
        w = h = 0
        n = 0
        for it in self._items:
            if it.isEmpty():        # 隐藏的控件不占位(如未处理时的「中止」)
                continue
            hint = it.sizeHint()
            w += hint.width() + (self._hs if n else 0)
            h = max(h, hint.height())
            n += 1
        m = self.contentsMargins()
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):
        # 最小宽度只按**单个最宽子项**算 → 容器可以一直收窄,收窄就折行
        s = QSize()
        for it in self._items:
            if it.isEmpty():
                continue
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    # --- 排版 ---
    def _layout(self, rect, test_only):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        # 先按 sizeHint 断行
        lines, cur, cur_w = [], [], 0
        for it in self._items:
            if it.isEmpty():        # 隐藏控件不参与排版,也不留空隙
                continue
            w = it.sizeHint().width()
            add = w if not cur else w + self._hs
            if cur and cur_w + add > eff.width():
                lines.append((cur, cur_w)); cur, cur_w = [it], w
            else:
                cur.append(it); cur_w += add
        if cur:
            lines.append((cur, cur_w))
        # 再逐行摆放(stretch 时等分剩余宽度)
        y = eff.y()
        for items, used in lines:
            extra = max(0, eff.width() - used) // len(items) if self._stretch else 0
            x, line_h = eff.x(), 0
            for it in items:
                hint = it.sizeHint()
                w = hint.width() + extra
                if not test_only:
                    it.setGeometry(QRect(QPoint(x, y), QSize(w, hint.height())))
                x += w + self._hs
                line_h = max(line_h, hint.height())
            y += line_h + self._vs
        return y - self._vs - rect.y() + m.bottom() if lines else 0


# 【禁用滚轮改值(用户 2026-09-04)】QSlider/QSpinBox 默认鼠标悬停+滚轮就改值 → 用户正常滚页面时极易**误改**
#   参数。wheelEvent 改为 ignore():不改值、且把滚轮事件冒泡给外层滚动区(页面照常滚)。+/- 按钮/直接输入照常。
class _NoWheelSlider(QSlider):
    def wheelEvent(self, e):
        e.ignore()


class _FineSlider(QSlider):
    """滚轮**一格 = 一个单位**(调色滑块的单位就是 1%)。

    Qt 默认是 `singleStep × wheelScrollLines`(通常 1×3 = **3 个单位**),对饱和这种
    要精调的量太粗(用户 2026-09-23:"跳转幅度有点太大")。
    高分辨率滚轮一次物理格会发多个小 delta,所以**累加到 120 才走一步**,
    不能见一个事件就走一格 —— 那样反而更快。
    """
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._wheel_acc = 0

    def wheelEvent(self, e):
        self._wheel_acc += e.angleDelta().y()
        moved = 0
        while self._wheel_acc >= 120:
            self._wheel_acc -= 120
            moved += 1
        while self._wheel_acc <= -120:
            self._wheel_acc += 120
            moved -= 1
        if moved:
            self.setValue(self.value() + moved)
        e.accept()


class _NoWheelSpin(QDoubleSpinBox):
    def wheelEvent(self, e):
        e.ignore()


class _NoWheelIntSpin(QSpinBox):
    def wheelEvent(self, e):
        e.ignore()


class FlowBar(QWidget):
    """承载 FlowLayout 的容器:把 heightForWidth 透传出去,折行后容器会自己变高。"""

    def __init__(self, hspace=8, vspace=8, stretch=False, parent=None):
        super().__init__(parent)
        self._fl = FlowLayout(self, 0, hspace, vspace, stretch)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def add(self, w):
        self._fl.addWidget(w)
        return w

    def clear(self):
        """移除并销毁所有子控件(重填前用)。"""
        while self._fl.count():
            it = self._fl.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.setParent(None); w.deleteLater()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._fl.heightForWidth(w)

    def sizeHint(self):
        one = self._fl.singleLineSize()
        return QSize(one.width(), self.heightForWidth(self.width() or one.width()))

    def minimumSizeHint(self):
        return self._fl.minimumSize()

    def refresh(self):
        """子控件显隐变化后重算尺寸(隐藏项不占位 → sizeHint 会变)。"""
        self._fl.invalidate()
        self.updateGeometry()
        self.adjustSize()


class PulseDot(QWidget):
    """会呼吸的状态圆点。自己 paintEvent + QPropertyAnimation,不反复 setStyleSheet
    (那会触发全局重新 polish,是 Qt 里做动画最贵的做法)。"""

    def __init__(self, d=9, parent=None):
        super().__init__(parent)
        self._d = d
        self._t = 1.0
        self._color = QColor("#888888")
        self.setFixedSize(d + 14, d + 14)          # 留足空间给柔光晕(否则光晕被裁)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        a = QPropertyAnimation(self, b"pulse", self)
        a.setDuration(4600)                        # 共享呼吸周期 ~4.6s(视觉重构·应用心跳,全局同拍)
        a.setStartValue(1.0); a.setKeyValueAt(0.5, 0.55); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.InOutSine); a.setLoopCount(-1)
        self._anim = a

    def getPulse(self):
        return self._t

    def setPulse(self, v):
        self._t = float(v); self.update()

    pulse = pyqtProperty(float, fget=getPulse, fset=setPulse)

    def set_state(self, color, breathing):
        self._color = QColor(color)
        if breathing:
            if self._anim.state() != QPropertyAnimation.Running:
                self._anim.start()
        else:
            self._anim.stop(); self._t = 1.0
        self.update()

    # 兼容 self._pulse.start()/stop() 的调用方式
    def start(self):
        self.set_state(self._color, True)

    def stop(self):
        self.set_state(self._color, False)

    def paintEvent(self, _e):
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)
        q.setPen(Qt.NoPen)
        ctr = self.rect().center()
        # 柔光晕:径向渐变(中心亮 → 外缘透明),半径随呼吸脉动 —— 比原来的实心 halo 更像"发光"
        glowR = self._d / 2.0 + 3.0 + 3.0 * self._t
        grad = QRadialGradient(float(ctr.x()), float(ctr.y()), float(glowR))
        c0 = QColor(self._color); c0.setAlphaF(0.45 * self._t)
        c1 = QColor(self._color); c1.setAlphaF(0.14 * self._t)
        c2 = QColor(self._color); c2.setAlphaF(0.0)
        grad.setColorAt(0.0, c0); grad.setColorAt(0.55, c1); grad.setColorAt(1.0, c2)
        q.setBrush(QBrush(grad))
        q.drawEllipse(ctr, int(glowR), int(glowR))
        # 核心亮点(实心,呼吸时也微微亮暗)
        core = QColor(self._color); core.setAlphaF(0.6 + 0.4 * self._t)
        q.setBrush(core)
        q.drawEllipse(ctr, self._d // 2, self._d // 2)


class BlinkBlock(QWidget):
    """日志末尾的方块光标。QPlainTextEdit 只读时不画 caret,而且只在拿到焦点后才闪,
    所以自己画一个:位置跟着 cursorRect(),闪烁用自己的 QTimer。"""

    def __init__(self, parent=None, color="#4FC3F7"):
        super().__init__(parent)
        self._color = QColor(color)
        self._on = True
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        t = QTimer(self); t.setInterval(540)
        t.timeout.connect(self._flip); t.start()
        self._timer = t

    def _flip(self):
        self._on = not self._on
        self.update()

    def set_color(self, c):
        self._color = QColor(c); self.update()

    def paintEvent(self, _e):
        if not self._on:
            return
        q = QPainter(self)
        c = QColor(self._color); c.setAlpha(215)
        q.fillRect(self.rect(), c)


class GradientLabel(QLabel):
    """双色渐变文字(品牌字)。QSS 不支持文字渐变,只能自己 QPen(QBrush(渐变)) 画。"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._a = QColor("#55DDA0")
        self._b = QColor("#6BE6AF")

    def set_colors(self, a, b):
        self._a, self._b = QColor(a), QColor(b)
        self.update()

    def paintEvent(self, _e):
        q = QPainter(self)
        q.setRenderHint(QPainter.TextAntialiasing)
        g = QLinearGradient(0.0, 0.0, float(self.width()), 0.0)
        g.setColorAt(0.0, self._a); g.setColorAt(0.34, self._a); g.setColorAt(1.0, self._b)
        q.setFont(self.font())
        q.setPen(QPen(QBrush(g), 1))
        q.drawText(self.rect(), int(self.alignment()), self.text())


def _thumb_focus(pm):
    """缩略图里天体的位置(0~1):灰度 → 16px 块平均 → 3×3 中值去孤立亮点(星)→ 亮区加权质心。
    找不到明显主体就返回画面中心。用来让「覆盖裁切」别把居中偏一点的天体切掉。"""
    try:
        import numpy as np
        img = pm.toImage().convertToFormat(QImage.Format_Grayscale8)
        w, h = img.width(), img.height()
        if w < 32 or h < 32:
            return 0.5, 0.5
        ptr = img.constBits(); ptr.setsize(img.bytesPerLine() * h)
        arr = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine())[:, :w].astype(np.float32)
        b = 16; H2, W2 = h // b, w // b
        if H2 < 3 or W2 < 3:
            return 0.5, 0.5
        a = arr[:H2 * b, :W2 * b].reshape(H2, b, W2, b).mean(axis=(1, 3))
        pad = np.pad(a, 1, mode="edge")
        stack = [pad[1 + dy:1 + dy + H2, 1 + dx:1 + dx + W2] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
        a = np.median(np.stack(stack), axis=0)
        a = a - np.percentile(a, 50); a[a < 0] = 0
        if a.max() <= 0:
            return 0.5, 0.5
        m = a >= np.percentile(a, 90)
        ys, xs = np.nonzero(m); wt = a[m]
        if wt.sum() <= 0:
            return 0.5, 0.5
        return float(((xs + 0.5) * wt).sum() / wt.sum() / W2), float(((ys + 0.5) * wt).sum() / wt.sum() / H2)
    except Exception:
        return 0.5, 0.5


def _cover_crop(pm, W, H, focus=(0.5, 0.5), radius=0, corners="all"):
    """等比放大铺满 W×H,按 focus 定裁切窗口(夹在图内),再把圆角裁进像素里(QLabel 不会被父框圆角裁)。"""
    dpr = 2.0
    sc = pm.scaled(int(W * dpr), int(H * dpr), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = int(round(focus[0] * sc.width() - W * dpr / 2)); y = int(round(focus[1] * sc.height() - H * dpr / 2))
    x = max(0, min(sc.width() - int(W * dpr), x)); y = max(0, min(sc.height() - int(H * dpr), y))
    cut = sc.copy(x, y, int(W * dpr), int(H * dpr))
    out = QPixmap(int(W * dpr), int(H * dpr)); out.fill(Qt.transparent)
    q = QPainter(out); q.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath(); r = radius * dpr; rw, rh = float(W * dpr), float(H * dpr)
    if r <= 0:
        path.addRect(QRectF(0, 0, rw, rh))
    else:
        tl = r if corners in ("all", "top", "left") else 0.0
        tr = r if corners in ("all", "top") else 0.0
        bl = r if corners in ("all", "left") else 0.0
        path.moveTo(tl, 0); path.lineTo(rw - tr, 0)
        path.quadTo(rw, 0, rw, tr) if tr else path.lineTo(rw, 0)
        path.lineTo(rw, rh); path.lineTo(bl, rh)
        path.quadTo(0, rh, 0, rh - bl) if bl else path.lineTo(0, rh)
        path.lineTo(0, tl)
        path.quadTo(0, 0, tl, 0) if tl else path.lineTo(0, 0)
    q.setClipPath(path); q.drawPixmap(0, 0, cut); q.end()
    out.setDevicePixelRatio(dpr)
    return out


class _ResizeWatch(QObject):
    """被监视控件尺寸变化时回调(项目库网格按可用宽度重算列数)。"""

    def __init__(self, cb, parent=None):
        super().__init__(parent)
        self._cb = cb

    def eventFilter(self, o, e):
        if e.type() == QEvent.Resize:
            QTimer.singleShot(0, self._cb)
        return False


class _VisWatch(QObject):
    """被监视控件自身 setVisible 变化时回调(ShowToParent/HideToParent:祖先显隐不触发)。
    用来让外层容器跟着内层面板显隐(检查器换成交互面板、时间线跟阶段带、审阅底栏跟结果卡)。"""

    def __init__(self, cb, parent=None):
        super().__init__(parent)
        self._cb = cb

    def eventFilter(self, o, e):
        if e.type() in (QEvent.ShowToParent, QEvent.HideToParent):
            QTimer.singleShot(0, self._cb)
        return False


def _qcol(s):
    """色板值 → QColor(兼容 QSS 写法 rgba(r,g,b,a),a 为 0~255)。"""
    if isinstance(s, str) and s.startswith("rgba("):
        r, g, b, al = (int(float(v)) for v in s[5:-1].split(","))
        return QColor(r, g, b, al)
    return QColor(s)


STEP_GAP = 7      # 序号圈与文字的间距:画进图标右侧(QPushButton 的图标与文字之间没有间距可调)


def _icon_padded(tpl, size, color, pad=STEP_GAP):
    """线性图标右侧补透明边,当作图标与文字的间距。"""
    from PyQt5.QtGui import QIcon
    dpr = 2.0
    src = icons.pixmap(tpl, size, color, dpr=dpr)
    px = QPixmap(int((size + pad) * dpr), int(size * dpr)); px.setDevicePixelRatio(dpr); px.fill(Qt.transparent)
    q = QPainter(px); q.drawPixmap(0, 0, src); q.end()
    return QIcon(px)


def _step_badge(state, num, p, d=20, dpr=2.0):
    """步骤导航的圆形序号:cur=实心绿 + 深字 / done=绿圈 + 对勾 / todo=灰圈 + 灰字。返回 QIcon。"""
    from PyQt5.QtGui import QFont, QIcon
    px = QPixmap(int((d + STEP_GAP) * dpr), int(d * dpr)); px.setDevicePixelRatio(dpr); px.fill(Qt.transparent)
    q = QPainter(px); q.setRenderHint(QPainter.Antialiasing)
    r = QRectF(0.75, 0.75, d - 1.5, d - 1.5)
    if state == "cur":
        q.setPen(Qt.NoPen); q.setBrush(_qcol(p['accent'])); q.drawEllipse(r)
        fg = _qcol(p['on_accent'])
    elif state == "done":
        q.setPen(QPen(_qcol(p['accent_edge']), 1.0)); q.setBrush(Qt.NoBrush); q.drawEllipse(r)
        pen = QPen(_qcol(p['accent']), 1.6); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        q.setPen(pen)
        path = QPainterPath(); path.moveTo(d * 0.31, d * 0.52); path.lineTo(d * 0.44, d * 0.65)
        path.lineTo(d * 0.70, d * 0.37); q.drawPath(path)
        q.end()
        return QIcon(px)
    else:
        q.setPen(QPen(_qcol(p['line2']), 1.0)); q.setBrush(Qt.NoBrush); q.drawEllipse(r)
        fg = _qcol(p['muted'])
    f = QFont("IBM Plex Mono"); f.setPixelSize(11); f.setWeight(QFont.DemiBold if state == "cur" else QFont.Normal)
    q.setFont(f); q.setPen(fg)
    q.drawText(QRectF(0, 0, d, d), int(Qt.AlignCenter), str(num))
    q.end()
    return QIcon(px)


class DotPanel(QFrame):
    """空态底板。底色与虚线边仍由 QSS(#roadpanel)画,paintEvent 再补一层点阵 ——
    QSS 里没有 radial-gradient / background-repeat,点阵只能自己画。"""

    def __init__(self, parent=None, step=22):
        super().__init__(parent)
        self._dot = QColor("#4b5e68")
        self._step = step

    def set_dot(self, c):
        if QColor(c) != self._dot:
            self._dot = QColor(c); self.update()

    def paintEvent(self, e):
        super().paintEvent(e)                     # 先让 QSS 画底 + 虚线边
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._dot); c.setAlpha(110)
        q.setPen(Qt.NoPen); q.setBrush(c)
        st = self._step
        for y in range(st // 2, self.height() - 2, st):
            for x in range(st // 2, self.width() - 2, st):
                q.drawEllipse(x, y, 2, 2)


class ScanBand(QWidget):
    """预览空态里缓慢扫过的光带。

    QSS 的 qlineargradient 只能纵向渐变,两侧会留硬边,看着像个色块。这里改成带 alpha 的
    QPixmap 预渲染(纵向渐变 + 横向羽化),每帧只搬一次位图,不重算渐变。
    """

    def __init__(self, parent, color="#4FC3F7"):
        super().__init__(parent)
        self._color = QColor(color)
        self._cache = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_color(self, c):
        if QColor(c) != self._color:
            self._color = QColor(c); self._cache = None; self.update()

    def _render(self):
        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        g = QLinearGradient(0.0, 0.0, 0.0, float(h))
        for pos, alpha in ((0.0, 0), (0.42, 8), (0.74, 26), (0.92, 52),
                           (0.975, 112), (1.0, 0)):
            c = QColor(self._color); c.setAlpha(alpha); g.setColorAt(pos, c)
        q.fillRect(0, 0, w, h, g)
        # 两侧羽化:否则光带贴着面板边缘会出现两道竖直硬边
        m = QLinearGradient(0.0, 0.0, float(w), 0.0)
        m.setColorAt(0.0, QColor(0, 0, 0, 0)); m.setColorAt(0.16, QColor(0, 0, 0, 255))
        m.setColorAt(0.84, QColor(0, 0, 0, 255)); m.setColorAt(1.0, QColor(0, 0, 0, 0))
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        q.fillRect(0, 0, w, h, m)
        q.end()
        self._cache = pm

    def paintEvent(self, _e):
        if self._cache is None or self._cache.size() != self.size():
            self._render()
        QPainter(self).drawPixmap(0, 0, self._cache)


class Shimmer(QWidget):
    """在进度条 / 主按钮上横向扫过的流光。宿主尺寸变了调 resync() 重新量一次。"""

    def __init__(self, host, alpha=80, frac=0.30, ms=1700, radius=4):
        super().__init__(host)
        self._host = host
        self._alpha, self._frac, self._radius = alpha, frac, radius
        self._cache = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()
        a = QPropertyAnimation(self, b"pos", self)
        a.setDuration(ms); a.setLoopCount(-1)
        a.setEasingCurve(QEasingCurve.InOutSine)
        self._anim = a

    def _measure(self):
        h = max(4, self._host.height())
        w = max(10, int(self._host.width() * self._frac))
        if self.size() != QSize(w, h):
            self.setFixedSize(w, h); self._cache = None
        self._anim.setStartValue(QPoint(-w, 0))
        self._anim.setEndValue(QPoint(self._host.width(), 0))

    def start(self):
        self._measure()
        self.show(); self.raise_()
        self._anim.stop(); self._anim.start()

    def stop(self):
        self._anim.stop(); self.hide()

    def resync(self):
        if self.isVisible():
            self.start()

    def _render(self):
        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(w, h); pm.fill(Qt.transparent)
        q = QPainter(pm); q.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0.0, 0.0, float(w), 0.0)
        for pos, a in ((0.0, 0), (0.5, self._alpha), (1.0, 0)):
            c = QColor(255, 255, 255, a); g.setColorAt(pos, c)
        q.setPen(Qt.NoPen); q.setBrush(QBrush(g))
        q.drawRoundedRect(0, 0, w, h, self._radius, self._radius)
        q.end()
        self._cache = pm

    def paintEvent(self, _e):
        if self._cache is None or self._cache.size() != self.size():
            self._render()
        QPainter(self).drawPixmap(0, 0, self._cache)


class SlideIndicator(QWidget):
    """跟着选中项滑动的指示器:流程标签下的横条 / 输入模式后面的药丸。

    位置用 geometry 动画,所以窗口折行、缩放后重新对位即可(见 _sync_indicators)。
    """

    def __init__(self, parent, radius=0):
        super().__init__(parent)
        self._radius = radius
        self._fill = QColor("#68E098")
        self._fill2 = None
        self._border = QColor(0, 0, 0, 0)
        self._inner = False                 # 内阴影(嵌入感,替代描边)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        a = QPropertyAnimation(self, b"geometry", self)
        a.setDuration(320); a.setEasingCurve(QEasingCurve.OutCubic)
        self._anim = a

    @staticmethod
    def _qc(s):
        """色板里有 QSS 写法的 "rgba(r,g,b,a)"(a 为 0~255),QColor 不认 → 手动解析。"""
        if isinstance(s, str) and s.startswith("rgba("):
            r, g, b, a = (int(float(v)) for v in s[5:-1].split(","))
            return QColor(r, g, b, a)
        return QColor(s)

    def set_colors(self, fill, border=None, fill2=None, inner=False):
        self._fill = self._qc(fill)
        self._fill2 = self._qc(fill2) if fill2 else None
        self._border = self._qc(border) if border else QColor(0, 0, 0, 0)
        self._inner = bool(inner)
        self.update()

    def move_to(self, rect):
        if not self.isVisible() or self.geometry().width() == 0:
            self.setGeometry(rect); self.show(); return
        if self.geometry() == rect:
            return
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(rect)
        self._anim.start()

    def paintEvent(self, _e):
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect().adjusted(0, 0, -1, -1))
        path = QPainterPath()
        path.addRoundedRect(r, float(self._radius), float(self._radius))
        # 填充:纯色 / 横向渐变
        if self._fill2 is not None:
            g = QLinearGradient(0.0, 0.0, float(self.width()), 0.0)
            g.setColorAt(0.0, self._fill); g.setColorAt(1.0, self._fill2)
            q.fillPath(path, QBrush(g))
        else:
            q.fillPath(path, self._fill)
        # 内阴影:顶部内缘深色→透明(嵌入/现代感,替代描边);底部一道极淡高光增强立体
        if self._inner:
            q.save(); q.setClipPath(path)
            h = float(self.height())
            top = QLinearGradient(0.0, 0.0, 0.0, max(1.0, h * 0.55))
            top.setColorAt(0.0, QColor(0, 0, 0, 70)); top.setColorAt(1.0, QColor(0, 0, 0, 0))
            q.fillRect(self.rect(), QBrush(top))
            bot = QLinearGradient(0.0, h * 0.55, 0.0, h)
            bot.setColorAt(0.0, QColor(255, 255, 255, 0)); bot.setColorAt(1.0, QColor(255, 255, 255, 30))
            q.fillRect(self.rect(), QBrush(bot))
            q.restore()
        # 边框(mode_ind 已改无边框;flow_ind 等仍可用)
        if self._border.alpha():
            q.setPen(self._border); q.setBrush(Qt.NoBrush)
            q.drawPath(path)


class _EmitStream:
    def __init__(self, sig):
        self._sig = sig

    def write(self, s):
        if s:
            self._sig.emit(str(s))

    def flush(self):
        pass


# ---------- 运行目录 _run 体积扫描 / 清理 ----------
_RUN_PROTECT_DIRS = {"inbox", "processing", "done"}                 # 运行时作业队列,永不清
_RUN_PROTECT_FILES = {"runner.heartbeat", "popup_guard.log", "watchdog.log"}
_RUN_INTER_EXTS = (".xisf", ".fit", ".fits", ".fts", ".tiff", ".tif")   # 顶层散落中间产物


def _dir_size(path: str) -> int:
    tot = 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            try:
                tot += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return tot


def _scan_run_entries():
    """扫 _run 顶层 → (可清理条目[按体积降序], 合计)。每个子目录=一行(一个目标/运行的中间工作区);
    顶层散落文件按 中间产物 / 预览图 两类聚合成行。运行时队列(inbox/processing/done)与心跳/日志受保护,不列。
    entry = {label, kind('dir'/'files'), paths:[...], size, preserve}。preserve=True 的(预览图)默认不勾选。"""
    root = str(config.RUN_DIR)
    entries = []
    inter_files, inter_sz = [], 0
    png_files, png_sz = [], 0
    try:
        its = list(os.scandir(root))
    except OSError:
        return [], 0
    for e in its:
        try:
            if e.is_dir(follow_symlinks=False):
                if e.name in _RUN_PROTECT_DIRS:
                    continue
                sz = _dir_size(e.path)
                entries.append({"label": e.name, "kind": "dir", "paths": [e.path],
                                "size": sz, "preserve": False})
            else:
                if e.name in _RUN_PROTECT_FILES:
                    continue
                low = e.name.lower()
                sz = e.stat().st_size
                if low.endswith(".png"):
                    png_files.append(e.path); png_sz += sz
                elif low.endswith(_RUN_INTER_EXTS):
                    inter_files.append(e.path); inter_sz += sz
                # 其它零碎(.ssf/.lst/.log 等)体量可略,忽略
        except OSError:
            pass
    if inter_files:
        entries.append({"label": f"顶层中间文件 .xisf/.fit/.tiff ×{len(inter_files)}",
                        "kind": "files", "paths": inter_files, "size": inter_sz, "preserve": False})
    if png_files:
        entries.append({"label": f"顶层预览图 .png ×{len(png_files)}",
                        "kind": "files", "paths": png_files, "size": png_sz, "preserve": True})
    entries.sort(key=lambda d: d["size"], reverse=True)
    return entries, sum(d["size"] for d in entries)


class _RunScan(QThread):
    """后台统计 _run 体积(全量遍历可能 >1 分钟,不能卡界面)。size 用 object 传,避免 32 位 int 溢出。"""
    result = pyqtSignal(object, object)            # entries(list), total(int)

    def run(self):
        try:
            entries, total = _scan_run_entries()
        except Exception:
            entries, total = [], 0
        self.result.emit(entries, total)


COL_DRAFT_DIV = 2              # 拖动中出草图:底图每边缩到 1/2(像素 1/4),松手出全尺寸
COL_LUT = 65536                # 面板预览曲线查表点数(见 galaxycolor._apply_curves_lut)


def _col_preview_compute(req: dict, cache: dict) -> dict:
    """手动调色面板的预览重算 —— 纯 numpy,在后台线程里跑(见 _ColPreviewWorker)。

    【为什么挪出界面线程(用户 2026-10-10「处理中滑块就拖不动,像卡死」)】原来每次重算都在界面线程上,
    1000px 预览上实测约 6 秒:蒙版漏出 3.0s + 覆盖率 1.5s(两者每次都重找中心、重量半径)、
    曲线 0.75s + 背景侧 0.4s;松手(sliderReleased)那一下还同步算一遍 → 每次停手/松手都冻住几秒。
    现在:几何量按底图只算一次、蒙版读数按蒙版缓存、曲线查表;算本身放后台,界面只收结果贴图。
    变换走 colorexp.apply_panel —— 与放大镜、经验库同一份实现(原来这里另写了一遍、靠注释提醒同步)。

    req:base / base_key / draft / pts / bpts / use_mask / need_mask / mask_frac / bg / ct / show_mask。
    cache 归后台线程独占:换底图(base_key 变)时清空。
    """
    import numpy as np
    from . import galaxycolor as gc, colorexp as cx
    if cache.get("base_key") != req["base_key"]:
        cache.clear()
        cache["base_key"] = req["base_key"]
    base = req["base"]
    draft = bool(req.get("draft"))
    tag = "draft" if draft else "full"
    if draft:
        work = cache.get("draft_base")
        if work is None:
            d = COL_DRAFT_DIV
            h, w = base.shape[0] // d * d, base.shape[1] // d * d
            work = base[:h, :w, :3].reshape(h // d, d, w // d, d, 3).mean(axis=(1, 3)).astype(np.float32)
            cache["draft_base"] = work
    else:
        work = base
    mk = None
    if req.get("need_mask"):
        mkey = (req.get("bg"), round(float(req.get("mask_frac", 0.30)), 4))
        if cache.get(("mk_key", tag)) != mkey:
            m, _ = gc.lum_sat_mask_array(work, bg=req.get("bg"), body_frac=req.get("mask_frac", 0.30))
            cache[("mk", tag)] = m
            cache[("mk_key", tag)] = mkey
            cache.pop(("mstat", tag), None)
        mk = cache[("mk", tag)]
    prm = {"pts": req.get("pts") or {}, "bpts": req.get("bpts") or {}, "use_mask": bool(req.get("use_mask")),
           "mask": mk, "ct": req.get("ct"), "lut": COL_LUT}
    img = np.asarray(cx.apply_panel(work, prm), dtype=np.float32)
    info = {"draft": draft, "base_key": req["base_key"]}
    if not draft:
        # 读数(覆盖/漏出/背景电平)**不在这里算**:首次要量几何 ~2.7s,放这儿会让刚打开面板那几秒
        #   拖动出不了图(离屏实测拖 40 步一张草图都没出)。→ 交给 _ColStatsWorker,图先出、读数随后补上。
        info["img_f"] = img            # 叠蒙版显示之前的图,背景读数在它上面量
        info["mask"] = mk
        info["mask_key"] = cache.get(("mk_key", tag)) if mk is not None else None
    if req.get("show_mask"):
        if mk is None:
            info["no_mask"] = True
        else:
            _veil = (1.0 - np.clip(mk, 0, 1))[..., None]
            _tint = np.array([0.16, 0.40, 0.95], np.float32)       # 冷蓝 = 背景侧
            img = img * (1.0 - 0.42 * _veil) + _tint * (0.42 * _veil)
            try:
                from scipy.ndimage import binary_erosion, binary_dilation
                _b = mk > 0.5
                _e = binary_dilation(_b ^ binary_erosion(_b), iterations=1)
                img[_e] = np.array([1.0, 0.95, 0.30], np.float32)   # 分界线
            except Exception:
                pass
    info["u8"] = np.ascontiguousarray((np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8))
    return info


def _col_stats_compute(req: dict, cache: dict) -> dict:
    """调色面板的读数(后台):蒙版盖住天体多少、漏进背景多少、背景电平/饱和。几何按底图只量一次,
    覆盖/漏出按蒙版缓存 —— 口径全走 galaxycolor 的单一真源(mask_body_coverage / mask_leak / mask_geometry)。"""
    import numpy as np
    from . import galaxycolor as gc, recombine as rc
    if cache.get("base_key") != req["base_key"]:
        cache.clear()
        cache["base_key"] = req["base_key"]
    base = req["base"]
    g = cache.get("geom")
    if g is None:
        g = gc.mask_geometry(base)
        cache["geom"] = g
    out = {"base_key": req["base_key"]}
    mk = req.get("mask")
    if mk is not None:
        k = ("mstat", req.get("mask_key"))
        st = cache.get(k)
        if st is None:
            st = {"cover": gc.mask_body_coverage(base, mk, geom=g),
                  "leak": float(gc.mask_leak(base, mk, geom=g).get("leak") or 0.0)}
            cache[k] = st
        out.update(st)
    try:
        far = g["far"]
        bl = req["img"][..., :3]
        out["bg_level"] = float(rc._sky_mode(bl.mean(-1)[far]))
        mx = bl.max(-1)
        out["bg_sat"] = float(np.median(((mx - bl.min(-1)) / np.maximum(mx, 1e-9))[far]))
    except Exception:
        pass
    return out


class _ColStatsWorker(QObject):
    """调色读数的后台算手(与出图分开一条线程:读数慢不拖住出图)。"""
    done = pyqtSignal(int, object)

    def __init__(self):
        super().__init__()
        self._cache = {}

    def run(self, req):
        try:
            res = _col_stats_compute(req, self._cache)
        except Exception as e:
            res = {"error": str(e)[:160], "base_key": req.get("base_key")}
        self.done.emit(int(req.get("id", 0)), res)


class _ColPreviewWorker(QObject):
    """调色预览的后台算手:住在自己的 QThread 里,一次只算一张;界面那边「最新的请求为准」排队。"""
    done = pyqtSignal(int, object)                 # (请求序号, 结果 dict)

    def __init__(self):
        super().__init__()
        self._cache = {}

    def render(self, req):
        try:
            res = _col_preview_compute(req, self._cache)
        except Exception as e:                       # 算挂了也要回信,否则界面那边一直等「在算」
            res = {"error": str(e)[:160], "base_key": req.get("base_key")}
        self.done.emit(int(req.get("id", 0)), res)


class _ColSolveThread(QThread):
    """调色面板「自动定其余」的后台求解(colorprefs.auto_solve),结果经 result 回界面线程。"""
    result = pyqtSignal(object)                     # auto_solve 的输出 dict,或 {"error": ...}

    def __init__(self, base, bg, vals, parent=None):
        super().__init__(parent)
        self._base, self._bg, self._vals = base, bg, dict(vals)

    def run(self):
        try:
            from . import colorprefs as _cpa
            out = _cpa.auto_solve(self._base, self._bg, vals=self._vals)
        except Exception as e:
            out = {"error": str(e)}
        self.result.emit(out)


class _ScoreThread(QThread):
    """后台跑 LLM 主观评分,不阻塞"完成"(kimi-k3 是推理模型、带图评审慢,曾把 UI 卡在"正在评分")。
    带 target/band → 没本地 AstroBin 参考就**按目标名拉同视场作品**(不依赖天文解析,filter 同波段匹配);
    带 prev_overall/prev_image → 连续评分锚定上一版(防尺度漂移)。"""
    result = pyqtSignal(object)                     # scores dict 或 None(失败/不可用)

    def __init__(self, png, ctx, parent=None, target="", band="", prev_overall=None, prev_image=None):
        super().__init__(parent)
        self._png = png
        self._ctx = ctx
        self._target = target or ""
        self._band = band or ""
        self._prev_overall = prev_overall
        self._prev_image = prev_image or None

    def run(self):
        try:
            from . import critic
            import glob as _glob
            # 同视场 AstroBin 参考图(以真实范例为锚,纠偏抽象"背景中性"标准对暖调星场的误判,用户 2026-09-04)。
            _refdir = Path(self._png).parent / "astrobin_refs"
            _refs = sorted(_glob.glob(str(_refdir / "ref_*.jpg"))) if self._png else []
            # 【关键修复(用户 2026-09-08:M1~M38 从没拉过)】没有本地参考 → **按目标名查坐标拉**(不再依赖天文
            #   解析成功;filter 按流程波段匹配:宽带 RGB 只比宽带/LRGB 作品、不比纯窄带)。
            if not _refs and self._target:
                try:
                    from . import astrobin_ref
                    _saved = astrobin_ref.fetch_for_target(self._target, band=self._band or None,
                                                           out_dir=_refdir, limit=3)
                    _refs = [s["local_path"] for s in _saved if s.get("local_path")]
                except Exception:
                    _refs = []
            s = critic.score(self._png, context=self._ctx, ref_paths=_refs or None,
                             prev_overall=self._prev_overall, prev_image=self._prev_image,
                             target=self._target)
            if isinstance(s, dict) and not s.get("error"):
                s["_astrobin_refs"] = len(_refs)     # 供 UI 显示"对比了 N 张 AstroBin 作品"
            self.result.emit(s if isinstance(s, dict) else {"error": "评分返回非预期"})
        except Exception as e:
            self.result.emit({"error": str(e)})     # 保留真实错误(超时/HTTP/后端 memo)供诊断


class _AgentEditThread(QThread):
    """后台跑 critic.agent_edit(自然语言→{reply,op,params}),不阻塞界面(LLM 调用慢)。"""
    result = pyqtSignal(object)                     # dict(agent_edit 返回)或 {error}

    def __init__(self, png, metrics, history, msg, parent=None):
        super().__init__(parent)
        self._png = png
        self._m = metrics
        self._h = history
        self._msg = msg

    def run(self):
        try:
            from . import critic
            self.result.emit(critic.agent_edit(self._png, self._m, self._h, self._msg))
        except Exception as e:
            self.result.emit({"error": str(e)})


# 【窄带融合 → 无 PI 引擎的档位(2026-09-28)】界面「窄带融合」四档是按 PI 管线定的(pipeline.run_rgb 四档都认);
#   无 PI 的 rgb_ha_engine.PRESETS 只有 galaxy / vivid 两档,都是「窄带只叠在画面里最亮的主体上」的星系式叠加
#   (_galaxy_mask 门控 + screen 提亮)。09-10 下拉改成 emission/emission_vivid/galaxy 时无 PI 分支没跟着改,
#   界面值原样传进引擎 → 除 galaxy 外全部 KeyError(默认档必崩,日志只有一行「[✗] 'emission'」)。
#   对不上的档换成最接近的,但**必须响亮**(开跑先说、成片旁再提一句),不静默替换:
#   · emission → galaxy:没有整片增强;强度取默认档(也是 09-10 之前无 PI 默认档的实际行为)
#   · emission_vivid → vivid:同上,强度对上「更浓」
#   · compact → galaxy:没有按比例上色、也锁不住主体亮度(screen 必然提亮主体)→ 取叠得最轻的一档
#   值 =(引擎档, 提示);提示空 = 引擎原样支持。以后下拉再加档,没登记的走 _ZEROPI_HAPRESET_OTHER。
_ZEROPI_HAPRESET = {
    "galaxy": ("galaxy", ""),
    "emission": ("galaxy",
                 "无 PI 引擎没有「整片星云增强」,这次改用「只增强星系的窄带信号」的叠法:"
                 "窄带只叠在画面里最亮的主体上,外围暗弱的云气不会增强。"
                 "目标是一整片发射星云、想整片增强时,请取消勾选「无 PI · Siril 引擎」,改走 PixInsight 流程。"),
    "emission_vivid": ("vivid",
                       "无 PI 引擎没有「整片星云增强·更浓」,这次改用「只增强星系的窄带信号」的叠法、叠得更浓:"
                       "窄带只叠在画面里最亮的主体上,外围暗弱的云气不会增强。"
                       "想整片增强时,请取消勾选「无 PI · Siril 引擎」,改走 PixInsight 流程。"),
    "compact": ("galaxy",
                "无 PI 引擎没有「保留主体明暗」,这次改用「只增强星系的窄带信号」的叠法:"
                "窄带会把主体提亮,主体的明暗层次不会保持宽带原样。"
                "想保留主体明暗时,请取消勾选「无 PI · Siril 引擎」,改走 PixInsight 流程。"),
}
_ZEROPI_HAPRESET_OTHER = ("galaxy",
                          "无 PI 引擎不支持这次选的窄带融合方式,改用「只增强星系的窄带信号」的叠法:"
                          "窄带只叠在画面里最亮的主体上。"
                          "想用原来选的方式,请取消勾选「无 PI · Siril 引擎」,改走 PixInsight 流程。")


class Worker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(str)                 # op 名
    preview = pyqtSignal(str)                  # 阶段性预览 png 路径
    done = pyqtSignal(bool, str, str, dict)    # ok, preview_png, final_xisf, scores
    paused = pyqtSignal(str, str, str, str)    # 进入暂停:tag, image_xisf, preview_png, targets_json
    pause_preview = pyqtSignal(str)            # 暂停中矫正后刷新预览 png
    pause_chat = pyqtSignal(str, str)          # 与 AI 对话:role("ai"/"sys"), 文本
    pause_busy = pyqtSignal(bool, str)         # 暂停中某个操作开跑/跑完:busy, 说明文字(UI 据此禁按钮+提示)
    decision = pyqtSignal(str, str, str)       # 分步询问:岔口 JSON, 当前图, 预览图
    decide_reply = pyqtSignal(str, str)        # 岔口里 AI 的回话:文本, 解析出的 set(JSON)
    deps = pyqtSignal(list)                     # 首启插件体检:缺失清单(回主线程弹引导框)
    color_ask = pyqtSignal(str, str)           # 手动调色:停在去星后的本体层,等用户调(当前图, 预览图)

    def __init__(self, kind, inp, opts):
        super().__init__()
        self.kind, self.inp, self.opts = kind, inp, opts
        import queue as _q
        self._pause_req = False          # UI 置位 → 下一步边界暂停
        self._pause_cmd = _q.Queue()     # UI → pause_gate 的命令队列(线程安全)
        self._dec_cmd = _q.Queue()       # UI → _decide_gate 的命令队列(分步询问模式)
        self._col_cmd = _q.Queue()       # UI → _color_gate 的命令队列(手动调色面板)

    # —— 供 UI 线程调用 ——
    def request_pause(self):
        self._pause_req = True

    def send_pause_cmd(self, cmd: dict):
        self._pause_cmd.put(cmd)

    # —— 分步询问模式(用户 2026-09-15)——
    def send_decide_cmd(self, cmd: dict):
        self._dec_cmd.put(cmd)

    # —— 手动调色面板(用户 2026-09-21)——
    def send_color_cmd(self, cmd: dict):
        self._col_cmd.put(cmd)

    def _color_gate(self, image, preview):
        """停在**去星后的星系本体层**,把调色交给用户。返回 (新图, 新预览) 或 None。

        用户 2026-09-21 定的交互:点画面标定背景 → RGB 三通道都以它为锚点(输出=输入),
        第二个控制点用滑块控制,操作思路跟 CT 一样;另配一条饱和度曲线。
        **明确不做**挂蒙版提星系饱和 —— 用户:"那样整个交互就过于复杂了,我还是希望以简洁明了为主"。

        实际应用走 runner 的 `curves` op(与 PI 的 CurvesTransformation 同一个东西);
        GUI 那边的实时预览用 numpy 算同一组控制点,只为看方向,不保证逐位相同。
        """
        from . import protocol as _pr
        self.color_ask.emit(str(image or ""), str(preview or ""))
        self.log.emit("[调色] 停在去星后的本体层,等你调色。")
        while True:
            cmd = self._col_cmd.get() or {}
            op = cmd.get("op")
            if op in ("skip", "cancel", None):
                self.log.emit("[调色] 不调,继续。")
                return None
            if op != "apply":
                continue
            pts = cmd.get("points") or {}
            bpts = cmd.get("bgPoints") or {}
            if not any(pts.values()) and not any(bpts.values()):
                self.log.emit("[调色] 没有实际改动,继续。")
                return None
            base = str(config.RUN_DIR / "rG_usercolor").replace("\\", "/")
            params = {k: v for k, v in pts.items() if v}
            from . import colorprefs as _cpj
            params.update({"linear": False, "curveType": _cpj.curve_type()})
            # 挂主体蒙版:在**全分辨率**上重算一份(与预览同一个函数,σ 按短边折算 → 羽化一致)。
            #   曲线本身有背景锚点,但**饱和曲线没有** —— 它作用在饱和度上,背景彩噪会被一起抬。
            _mpath = None
            if cmd.get("mask") or any(bpts.values()):
                # 背景侧那两条**必须**有蒙版才谈得上"背景":没有蒙版就没有补集。
                try:
                    from . import galaxycolor as _gcm
                    _mp = str(config.RUN_DIR / "rG_usermask.xisf").replace("\\", "/")
                    _mi = _gcm.lum_sat_mask(str(image), _mp, bg=cmd.get("bg"),
                                            body_frac=float(cmd.get("maskFrac") or 0.30),
                                            log=self.log.emit)
                    _mpath = _mi["path"]
                except Exception as _me:
                    self.log.emit("[调色] 蒙版构建失败,改为整图作用:%s" % str(_me)[:120])
            if _mpath and cmd.get("mask"):
                params["mask"] = _mpath
            _cur, _prev = str(image), str(preview or "")
            # (蒙版建不出来时背景侧会被整条跳过 → _prev 必须先有值,否则下面返回时 NameError)
            for _i, (_pp, _inv, _tag) in enumerate(
                    ((params if any(pts.values()) else None, False, "主体"),
                     ({**bpts, "linear": False, "curveType": _cpj.curve_type()}
                      if (any(bpts.values()) and _mpath) else None, True, "背景侧"))):
                if not _pp:
                    continue
                _pr2 = dict(_pp)
                if _inv:
                    _pr2["mask"] = _mpath
                    _pr2["maskInverted"] = True
                _out = base + ("" if _i == 0 else "_bg")
                job = _pr.new_job("curves", input=_cur, params=_pr2,
                                  outputs={"image": _out + ".xisf", "preview": _out + ".png"})
                _pr.submit(job)
                r = _pr.wait_result(job["job_id"], timeout=600)
                if r.get("status") != "ok":
                    self.log.emit("[调色] %s应用失败:%s" % (_tag, str(r.get("error"))[:200]))
                    self.color_ask.emit(str(image or ""), str(preview or ""))   # 退回面板重来
                    _cur = None
                    break
                _cur = r.get("image") or (_out + ".xisf")
                _prev = r.get("preview") or (_out + ".png")
            if _cur is None:
                continue
            self.log.emit("[调色] 已应用你的曲线。")
            # 【必须打 [preview](用户 2026-09-23:「确认调色后进入后续环节,放大镜又变回原始图像」)】
            #   放大镜的全分辨率取样源是 `_final_xisf or _stage_xisf`,而 `_stage_xisf` 只在
            #   GUI 收到 `[preview] <png>` 时更新(取同名 .xisf)。手动调色这两步是本函数**直接走
            #   protocol 跑的、不经过 step()**,所以从来不打这行 —— 于是主预览显示的是调色后
            #   (面板自己画的),放大镜却还指着调色前的 r11b_lhe,两者对不上。
            #   stdout 在 Worker 里已重定向并经 _sniff 解析,print 出去即可。
            if _prev:
                print('[preview] %s' % _prev)
            return (_cur, _prev)

    def _decide_gate(self, point, image, preview, cur):
        """岔口回调:把这一岔口交给用户,阻塞等他定,返回 {"option":..,"set":{..},"said":..}。

        两条入口**归到同一套旋钮**:固定按钮直接取表里的 set;自然语言经 critic.decide_direction
        翻成同一批旋钮名,再由 pipeline._mk_decider 统一夹范围。人话那条**先给解释再等确认**——
        模型理解错时用户还能改口,而不是等成片出来才发现跑偏。"""
        import json as _json
        self.decision.emit(_json.dumps(point, ensure_ascii=False), str(image or ""), str(preview or ""))
        self.log.emit(f"[分步] 停在岔口【{point.get('title')}】,等你定方向。")
        pending = None          # 自然语言解析出来、还没采用的那一套
        while True:
            cmd = self._dec_cmd.get() or {}
            op = cmd.get("op")
            if op == "choose":
                key = cmd.get("key")
                for o in point.get("options") or []:
                    if o.get("key") == key:
                        self.log.emit(f"[分步] 你选了:{o.get('label')}")
                        return {"option": key, "set": dict(o.get("set") or {})}
                self.decide_reply.emit(f"没有这个选项:{key}", "")
                continue
            if op in ("keep", "cancel"):
                self.log.emit("[分步] 保持默认,继续。")
                return {}
            if op == "apply":
                if not pending:
                    self.decide_reply.emit("还没有可采用的方案,先说一句你想怎么改。", "")
                    continue
                self.log.emit(f"[分步] 采用:{pending.get('set')}")
                return pending
            if op == "say":
                txt = (cmd.get("text") or "").strip()
                if not txt:
                    continue
                src = preview if (preview and Path(str(preview)).exists()) else image
                if not (src and Path(str(src)).exists()):
                    self.decide_reply.emit("这一步没有可看的预览图,先用上面的按钮选。", "")
                    continue
                from . import critic as _cr
                if not _cr.is_configured():
                    self.decide_reply.emit("没配 AI 接口,自然语言用不了;用上面的按钮选。", "")
                    continue
                try:
                    res = _cr.decide_direction(str(src), point, txt)
                except Exception as e:
                    self.decide_reply.emit(f"没问成:{e}", "")
                    continue
                if res.get("error"):
                    self.decide_reply.emit(f"没问成:{res['error']}", "")
                    continue
                if res.get("model_note"):
                    self.decide_reply.emit(res["model_note"], "")
                pending = {"option": res.get("option") or "custom",
                           "set": dict(res.get("set") or {}), "said": txt}
                _s = pending["set"]
                self.decide_reply.emit(
                    (res.get("reply") or "(没给说明)")
                    + ("" if _s else "  —— 理解成「保持默认」"),
                    _json.dumps(_s, ensure_ascii=False))
                continue

    # —— 在 Worker 线程里执行(run_sho 每步边界回调)——
    def _pause_gate(self, tag, image, preview, linmode, targets=None):
        """暂停介入。targets={显示名:通道master路径}——**可回到任一通道**修(不止当前步),
        因为合成前各通道独立、就地覆盖能传播到下游。返回 (新image,新preview) 或 None。

        两种模式:
        - 通道模式(targets 非空,合成前):对**选中的通道** master 就地覆盖 → run_sho 的
          raw[k] 路径不变、内容已改 → 下游读到修正版。始终返回 None(靠就地传播)。
        - 步骤模式(targets 空,如合成后):对当前步图写新文件并返回,让 step() 替换 r。
        """
        if not self._pause_req:
            return None
        import json as _json
        targets = targets or {}
        lin = (linmode == "linear")
        cur_img, cur_prev = image, preview
        changed_step = False
        # 活动目标:通道模式默认=当前步对应的那个通道(image 命中 targets)否则第一个;步骤模式=当前图
        active = image
        if targets and image not in targets.values():
            active = next(iter(targets.values()))
        self.paused.emit(tag, image or "", preview or "", _json.dumps(targets, ensure_ascii=False))
        self.log.emit(f"[暂停] 停在【{tag}】。" +
                      ("可选通道后做 梯度矫正/灰尘修复;" if targets else "可对当前图做 梯度矫正/灰尘修复;") +
                      "或点继续。")

        import shutil as _sh
        from . import critic as _cr
        history = []          # 与 AI 的对话历史 [(role, text)]
        undo_stack = []       # 就地模式撤销:[(active路径, 快照xisf, 快照png)]

        def _preview_of(path):
            p = str(path)
            return p[:-5] + ".png" if p.endswith(".xisf") else ""

        def _apply_op(op, params):
            """在 active 上执行一个 op:通道模式就地覆盖(存撤销快照),步骤模式写新文件。返回 ok。

            多数 op 交给 runner;graxpert_bge 是例外——它走 GraXpert 的 Python CLI,runner 里
            **根本没有这个 op**(用户 2026-09-16:AI 说要用 GraXpert,直接转发 runner → "unknown op")。
            """
            nonlocal cur_img, cur_prev, changed_step, active
            in_place = bool(targets)
            if in_place:
                try:
                    snx = str(config.RUN_DIR / f"undo_{len(undo_stack)}_{Path(str(active)).stem}.xisf").replace("\\", "/")
                    _sh.copy2(str(active), snx)
                    pv0 = _preview_of(active); snp = snx[:-5] + ".png"
                    if pv0 and Path(pv0).exists():
                        _sh.copy2(pv0, snp)
                    else:
                        snp = ""
                    undo_stack.append((str(active), snx, snp))
                except Exception:
                    pass
                outs = {"image": str(active), "preview": _preview_of(active)}
            else:
                base = str(config.RUN_DIR / f"edit_{tag}_{len(undo_stack)}").replace("\\", "/")
                outs = {"image": base + ".xisf", "preview": base + ".png"}
                undo_stack.append((str(active), cur_img, cur_prev))
            if op == "graxpert_bge":
                if not _graxpert_bge(params, outs):
                    return False
            else:
                job = protocol.new_job(op, input=str(active), params=params, outputs=outs)
                protocol.submit(job)
                rr = protocol.wait_result(job["job_id"], timeout=1800)
                if rr.get("status") != "ok":
                    self.log.emit(f"[暂停] {op} 失败:{rr.get('error')}")
                    return False
                outs["image"] = rr.get("image") or outs["image"]
                outs["preview"] = rr.get("preview") or outs["preview"]
            if not in_place:
                cur_img = outs["image"]
                cur_prev = outs["preview"]
                active = cur_img; changed_step = True
            self.pause_preview.emit(outs["preview"])
            self.log.emit(f"[暂停] {op} 完成,已刷新预览。")
            return True

        def _graxpert_bge(params, outs):
            """GraXpert AI 背景提取(子进程,1~2 分钟)→ 落到 outs["image"],再借 runner 的 inspect
            出预览(拉伸口径与其他步骤一致:线性图才拉伸)。返回是否成功。"""
            from . import graxpert as _gx
            try:
                _sm = max(0.0, min(1.0, float(params.get("smoothing", 0.2))))
            except (TypeError, ValueError):
                _sm = 0.2
            self.log.emit(f"[暂停] GraXpert AI 背景提取中(smoothing={_sm},约 1~2 分钟,请等它跑完)…")
            _noext = outs["image"][:-5] if outs["image"].lower().endswith(".xisf") else outs["image"]
            try:
                _gout = _gx.background_extraction(str(active), _noext + "_gx",
                                                  smoothing=_sm, gpu=False, timeout=900)
            except Exception as e:
                self.log.emit(f"[暂停] GraXpert 失败:{e}")
                return False
            try:
                if str(_gout).replace("\\", "/") != outs["image"]:
                    _sh.copy2(_gout, outs["image"])
            except OSError as e:
                self.log.emit(f"[暂停] GraXpert 结果写入失败:{e}")
                return False
            j = protocol.new_job("inspect", input=outs["image"], params={"linear": lin},
                                 outputs={"preview": outs["preview"]})
            protocol.submit(j)
            rr = protocol.wait_result(j["job_id"], timeout=600)
            if rr.get("status") != "ok":
                self.log.emit(f"[暂停] GraXpert 已完成,但预览生成失败:{rr.get('error')}")
            return True

        def _norm(op, params):
            """把 op/params 归一到**可执行**形式(并注入 linear);未知/缺参返回 (None,原因)。

            AGENT_OPS 是给 LLM 看的目录,**不等于 runner 的 op 表**——照单转发会撞
            "unknown op"(用户 2026-09-16 的 graxpert_bge)。这里按名字逐个落到真实执行路径,
            处理中做不了的(要重跑全流程 / 要多步分离星点)直接说清楚,别让它到 runner 才炸。
            """
            p = dict(params or {}); p["linear"] = lin
            if op == "gradient":
                return "gradient", {"method": "GradientCorrection", "linear": lin}
            if op == "saturation_down":
                return "curves", {"saturation": -abs(float(p.get("amount", 0.15))), "linear": lin}
            if op == "flatpatch":
                if not all(k in p for k in ("x", "y", "r")):
                    return None, "需先点选灰尘环(缺坐标)"
                p.setdefault("mode", "gain")
                return "flatpatch", p
            if op == "graxpert_bge":
                from . import graxpert as _gx
                if not _gx.available():
                    return None, "未检测到 GraXpert(在『配置』里把 graxpert_path 指向 GraXpert.exe)"
                try:
                    _sm = float(p.get("smoothing", 0.2))
                except (TypeError, ValueError):
                    _sm = 0.2
                return "graxpert_bge", {"smoothing": max(0.0, min(1.0, _sm))}
            if op == "polybg":
                try:
                    _dg = int(round(float(p.get("degree", 2))))
                except (TypeError, ValueError):
                    _dg = 2
                return "polybg", {"degree": max(1, min(3, _dg)), "linear": lin}
            if op == "crop":
                # AI 给的是逐边比例(0~0.3),runner 要的是 marginsFrac;不转换等于白跑
                _mf = {}
                for _e in ("left", "right", "top", "bottom"):
                    try:
                        _v = float(p.get(_e, 0) or 0)
                    except (TypeError, ValueError):
                        _v = 0.0
                    if _v > 0:
                        _mf[_e] = max(0.0, min(0.3, _v))
                if not _mf:
                    return None, "裁切需指定至少一边的比例(left/right/top/bottom,0~0.3)"
                return "crop", {"marginsFrac": _mf, "linear": lin}
            if op == "restretch":
                return None, "『退回改拉伸力度』要重跑整条流程,处理中做不了 —— 先点继续跑完,再在『审阅』页说一次"
            if op == "depurple":
                return None, "去星点紫要先分离星点再合回(多步),处理中做不了 —— 跑完在『审阅』页说一次"
            if op in _cr.AGENT_OPS:
                return op, p
            return None, f"不支持的操作 {op}"

        while True:
            cmd = self._pause_cmd.get()
            op = cmd.get("op")
            if op == "continue":
                self._pause_req = False
                self.log.emit("[暂停] 继续。")
                return (cur_img, cur_prev) if changed_step else None
            if op == "select_target":
                active = cmd.get("path") or active
                pv = _preview_of(active)
                if pv and Path(pv).exists():
                    self.pause_preview.emit(pv)
                self.log.emit(f"[暂停] 目标切到:{Path(str(active)).name}")
                continue
            if op == "undo":
                if not undo_stack:
                    self.pause_chat.emit("sys", "没有可撤销的步骤。")
                    continue
                ap, sx, sp = undo_stack.pop()
                try:
                    if bool(targets):     # 就地模式:快照复原回 active 文件
                        _sh.copy2(sx, ap)
                        if sp and Path(sp).exists():
                            _sh.copy2(sp, _preview_of(ap))
                        active = ap
                    else:                  # 步骤模式:指针回退
                        active = sx; cur_img = sx; cur_prev = sp
                    self.pause_preview.emit(_preview_of(active) if bool(targets) else cur_prev)
                    self.pause_chat.emit("sys", "已撤销上一步。")
                except Exception as e:
                    self.pause_chat.emit("sys", f"撤销失败:{e}")
                continue
            # 【连点保护(用户 2026-09-16)】点了没立刻反应 → 用户连点 8 次 → 8 遍 GradientCorrection
            #   叠在同一张图上。这里把队列里堆着的同名命令并成一次(UI 侧同时会禁按钮)。
            import queue as _qmod
            _dup = 0
            while op in ("gradient",):
                try:
                    _nx = self._pause_cmd.get_nowait()
                except _qmod.Empty:
                    break
                if _nx.get("op") == op:
                    _dup += 1
                    continue
                self._pause_cmd.put(_nx)
                break
            if _dup:
                self.log.emit(f"[暂停] 同一操作点了 {_dup + 1} 次 → 只执行一次(别叠着跑)。")
            self.pause_busy.emit(True, {"gradient": "梯度矫正中…", "flatpatch": "灰尘修复中…",
                                        "llm_edit": "AI 处理中…"}.get(op, "处理中…"))
            try:
                if op == "gradient":
                    _apply_op("gradient", {"method": "GradientCorrection", "linear": lin})
                    continue
                if op == "flatpatch":
                    # UI 传 png 坐标 → 用 active 全分辨率换算
                    j0 = protocol.new_job("inspect", input=str(active), params={"linear": lin})
                    protocol.submit(j0)
                    met = (protocol.wait_result(j0["job_id"], timeout=300).get("metrics") or {})
                    fw = int(met.get("width") or cmd["png_w"])
                    k = fw / float(cmd["png_w"])
                    x, y, r = cmd["cx_png"] * k, cmd["cy_png"] * k, cmd["r_png"] * k
                    _apply_op("flatpatch", {"x": round(x, 1), "y": round(y, 1), "r": round(r, 1),
                                            "mode": "gain", "linear": lin})
                    continue
                if op == "llm_edit":
                    user_msg = cmd.get("text", "")
                    # 量当前 active 指标喂给 AI
                    prm = {}
                    try:
                        jj = protocol.new_job("lumprobe", input=str(active), params={"linear": False})
                        protocol.submit(jj)
                        pr = protocol.wait_result(jj["job_id"], timeout=120).get("probe") or {}
                        prm = {"anchors": pr.get("anchors"), "color": pr.get("color"),
                               "bgColor": pr.get("bgColor")}
                    except Exception:
                        pass
                    pv = _preview_of(active)
                    if not (pv and Path(pv).exists()):
                        pv = cur_prev
                    res = _cr.agent_edit(pv, prm, history, user_msg)
                    if res.get("error"):
                        self.pause_chat.emit("ai", f"(出错:{res['error']})")
                        continue
                    reply = res.get("reply") or ""
                    history.append(("用户", user_msg)); history.append(("助手", reply))
                    aop, aparams = res.get("op"), res.get("params") or {}
                    if aop:
                        nop, nparams = _norm(aop, aparams)
                        if nop:
                            ok = _apply_op(nop, nparams)
                            self.pause_chat.emit("ai", reply + (f"\n✓ 已执行 {aop}" if ok else f"\n✗ {aop} 执行失败"))
                        else:
                            self.pause_chat.emit("ai", reply + f"\n(未执行:{nparams})")
                    else:
                        self.pause_chat.emit("ai", reply)
                    _u = res.get("usage") or {}      # 本次 token 用量(官方接口),给用户可见反馈
                    if res.get("model_note"):        # 首选模型没调动、自动换了备用
                        self.pause_chat.emit("sys", res["model_note"])
                    if _u.get("total"):
                        _r = _u.get("reasoning")
                        self.pause_chat.emit("sys", f"本次 {_u['total']} tokens" +
                                             (f"(含推理 {_r})" if _r else ""))
                    continue
            except Exception as e:
                self.log.emit(f"[暂停] 出错:{e}")
                self.pause_chat.emit("sys", f"出错:{e}")
            finally:
                self.pause_busy.emit(False, "")

    _NB_KEY = {"Ha": "H", "OIII": "O", "SII": "S", "R": "R", "G": "G", "B": "B"}

    def _nb_inputs(self, o: dict):
        """窄带引擎(run_sho)的输入 → (各通道子帧表, 各通道母版, 跳过的行)。
        对齐子帧目录:**按每行右边选的滤镜**归通道(同一滤镜多行 = 多晚,合并整合);
        已叠加母版:每个通道取第一张。L 和彩色相机的双窄带标签不进这条路(run_sho 不用 L)。"""
        chans, mst, skipped = {}, {}, []
        if o.get("integrate_first"):
            for g in (o.get("reg") or []):
                k = self._NB_KEY.get(g.get("filter"))
                if not k:
                    skipped.append(f"{Path(g['dir']).name}({g.get('filter')})")
                    continue
                chans.setdefault(k, []).extend(pipeline._reg_xisf(g["dir"]))
        elif o.get("input_mode") == 0:
            for m_ in (o.get("master") or []):
                k = self._NB_KEY.get(m_.get("filter"))
                if not k:
                    skipped.append(f"{Path(m_['file']).name}({m_.get('filter')})")
                elif k not in mst:
                    mst[k] = m_["file"]
        return {k: v for k, v in chans.items() if v}, mst, skipped

    def _integrate_reg_group(self, dirs: list, out_path: str, o: dict) -> str:
        """把若干**对齐子帧目录**(同一滤镜组)里的子帧直接整合成一个 master(无 WBPP,已对齐)。
        用于对齐子帧目录模式按滤镜分组出 RGB 底 / NB master。返回 master 路径。

        【取帧走 _reg_xisf】以前这里自己 rglob,不跳过 `_ttlot_culled/`(筛帧挪进去的坏帧)和 PI 标记的
        `failed_` 配准失败帧 → 这个模式下「筛」按钮筛掉的帧照样进了母版。
        【复用(用户 2026-10-06)】同样的帧、同一版整合算法、母版叠完没被动过 → 直接用盘上的母版,
        不再每次点处理都重叠一遍(见 pipeline.reuse_stacked_master)。"""
        subs = []
        for d in dirs:
            subs += pipeline._reg_xisf(d)
        if not subs:
            raise RuntimeError("对齐子帧目录里没有可用的 .xisf:%s" % dirs)
        _hit = pipeline.reuse_stacked_master(subs, out_path, log=self.log.emit)
        if _hit:
            self.log.emit(f"[对齐子帧] 复用已叠好的母版 {_hit}(这 {len(subs)} 帧上次已经叠过,"
                          "一帧没变 → 不再重叠;要强制重叠就删掉它旁边的 .stack.json)")
            return _hit
        pipeline.set_aside_foreign_master(out_path, log=self.log.emit)
        try:
            pipeline._stack_record_path(out_path).unlink()
        except OSError:
            pass
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        m = pipeline.run_integrate(dirs[0], out_path=out_path, images=subs,
                                   timeout=max(o["timeout"], 1800.0))
        try:
            pipeline.write_stack_record(subs, out_path, m)
        except Exception as e:
            self.log.emit(f"[对齐子帧] 叠加记录没写成({e})→ 下次还会重新叠加")
        return m

    def _stack_filter_group(self, raw_subset: dict, o: dict, label: str) -> str:
        """把某一滤镜组的原始亮场叠成单张 master(PI WBPP 校准+去马+对齐 → 整合)。
        用于双窄带滤镜组单独出 NB master(供 run_rgb 的 ha_dir 融合)。复用主流程判定
        (多晚+校准库 → 逐晚 WBPP 各配各温度暗场)。NB 帧通常少,不做 detrail。返回 master 路径。"""
        _vn = [n for n in (raw_subset.get("nights") or []) if n.get("light")]
        _lib = (raw_subset.get("calib_library") or "").strip()
        if len(_vn) > 1 and _lib and os.path.isdir(_lib):
            self.log.emit(f"[叠加·{label}] 多晚({len(_vn)})+ 校准库 → 逐晚 WBPP…")
            reg = pipeline.run_wbpp_stack_pernight(raw_subset, timeout=max(o["timeout"], 3600.0))
        else:
            self.log.emit(f"[叠加·{label}] WBPP(校准+去马+对齐)…")
            reg = pipeline.run_wbpp_stack(raw_subset, timeout=max(o["timeout"], 3600.0))
        # NB master 存**项目目录**(与 RGB masterLight 并列,可见+『已叠加母版』复用);整合先于 RGB 叠加完成,
        #   两者 masterLight_HO.xisf / masterLight.xisf 文件名不撞(中间 registered 会被 RGB 覆盖但 master 已落盘)。
        _projdir = str(Path(reg).parent).replace("\\", "/")
        _out = f"{_projdir}/masterLight_HO.xisf"
        return pipeline.run_integrate(reg, out_path=_out, timeout=max(o["timeout"], 1800.0))

    def _zeropi_stack_raw(self, raw: dict, o: dict) -> str:
        """无 PI 原始素材叠加:OSC 亮场(多晚合并)+ 可选定标帧 → Siril stack_engine 出 master(零 PixInsight)。
        定标帧(暗/偏/平原始目录,可由校准场库自动匹配回填)先 make_master 再喂 stack_osc。返回 master .fit。"""
        from . import stack_engine
        nights = raw.get("nights") or []
        lights = [n["light"].replace("\\", "/") for n in nights if n.get("light")]
        if not lights:
            raise RuntimeError("无 PI 原始叠加:未填亮场目录")
        # 叠出的 master 路径不含设备名 → 后续 guess_sensor 认不出;stash 首个原始亮场目录供传感器识别(保真 SPCC)
        self._raw_ref_light = lights[0]
        flats = [n["flat"].replace("\\", "/") for n in nights if n.get("flat")]
        dark_dir = (raw.get("dark") or "").strip().replace("\\", "/")
        bias_dir = (raw.get("bias") or "").strip().replace("\\", "/")
        out_base = (raw.get("out_base") or str(config.RUN_DIR)).rstrip("/").replace("\\", "/")
        target = (raw.get("target") or "zeropi").strip()
        proj = f"{out_base}/{target}"
        os.makedirs(proj, exist_ok=True)
        tmo = max(o["timeout"], 7200.0)
        # 定标 master(有原始定标帧才建;暗/偏 median、平 rej)
        m_dark = m_flat = m_bias = None
        if dark_dir:
            self.log.emit(f"[叠加] 暗场 master(median):{dark_dir}")
            m_dark = stack_engine.make_master(dark_dir, f"{proj}/_m_dark", method="med", timeout=tmo, log=self.log.emit)
        if bias_dir:
            self.log.emit(f"[叠加] 偏置 master(median):{bias_dir}")
            m_bias = stack_engine.make_master(bias_dir, f"{proj}/_m_bias", method="med", timeout=tmo, log=self.log.emit)
        if flats:
            if len(set(flats)) > 1:
                self.log.emit(f"[叠加] 检测到 {len(flats)} 组平场;zero-PI 单 master 校准路径用第一组:{flats[0]}")
            self.log.emit(f"[叠加] 平场 master(rej):{flats[0]}")
            m_flat = stack_engine.make_master(flats[0], f"{proj}/_m_flat", method="rej", timeout=tmo, log=self.log.emit)
        # **多晚 + 校准库 → 逐晚按温度配暗场**(Dwarf 等非制冷各晚温度不同 → 单暗场会错配其它晚,残留暗电流/辉光)
        #   + 逐晚平场,走 stack_osc_pernight(每晚各自 calibrate 再汇合整合)。单晚/无库退回单 master stack_osc。
        lib = (raw.get("calib_library") or "").strip().replace("\\", "/")
        vnights = [n for n in nights if n.get("light")]
        if len(vnights) > 1 and lib and os.path.isdir(lib):
            from . import calib_match
            self.log.emit(f"[叠加] 多晚({len(vnights)}晚)+ 校准库 → 逐晚按温度配暗场(避免单暗场温度错配)")
            pn = calib_match.auto_calib_pernight(lib, [n["light"].replace("\\", "/") for n in vnights],
                                                 kinds=("dark",), log=self.log.emit)
            ncfg = []
            for i, n in enumerate(vnights):
                nd = pn[i]["dark"]["dir"] if (i < len(pn) and pn[i].get("dark")) else None
                nf = (n.get("flat") or "").strip().replace("\\", "/") or None
                ncfg.append({"lights": n["light"].replace("\\", "/"), "dark": nd, "flat": nf})
            self._raw_ref_light = vnights[0]["light"].replace("\\", "/")
            return stack_engine.stack_osc_pernight(ncfg, f"{proj}/{target}_master",
                                                   bias=m_bias, timeout=tmo, log=self.log.emit)
        _cal = [t for t, v in (("暗", m_dark), ("平", m_flat), ("偏", m_bias)) if v] or ["无校准(纯亮场)"]
        self.log.emit(f"[叠加] OSC 亮场 → master(零 PixInsight):{len(lights)} 组亮场目录,校准={'/'.join(_cal)}")
        return stack_engine.stack_osc(lights if len(lights) > 1 else lights[0], f"{proj}/{target}_master",
                                      dark=m_dark, flat=m_flat, bias=m_bias,
                                      timeout=tmo, log=self.log.emit)

    def run(self):
        old = sys.stdout
        sys.stdout = _EmitStream(self.log)
        # 解析 stdout 里的 "[tag] op -> ok" 推进进度
        self.log.connect(self._sniff)
        png = xis = ""
        scores = {}
        # 无 PI · Siril 引擎流程全程零 PixInsight → 不需要 job-runner,跳过就绪等待(否则 90s 空等后放弃)
        _o0 = self.opts or {}
        _zeropi = ((self.kind == "rgb" and _o0.get("zeropi_rgb"))
                   or (self.kind == "hoo" and _o0.get("zeropi_hoo"))
                   or (self.kind == "sho" and _o0.get("zeropi")))
        # runner 未就绪(如刚自动冷启动 PI)→ 在此等待,最多 90s,别冻 UI(UI 线程照常刷新)
        if not _zeropi and not protocol.runner_up():
            self.log.emit("[准备] 等待 PixInsight / job-runner 就绪…")
            for _ in range(180):
                if protocol.runner_up():          # 忙(在跑别的任务)也算就位 → 本任务丢 inbox 排队即可
                    break
                time.sleep(0.5)
            if not protocol.runner_up():
                self.log.emit("[✗] PixInsight/job-runner 未能在 90s 内就绪,已放弃。请检查 PI 路径或手动启动。")
                self.done.emit(False, "", "", {})
                sys.stdout = old
                return
            self.log.emit("[准备] runner 已就绪,开始处理。")
        try:
            o = self.opts
            # 【首启插件引导】本会话首次处理、runner 已确保就绪 → 主动体检一次:缺插件不再报错(#4 有兜底),
            #   但把"缺什么 / 兜底是什么 / 想更好怎么装"引导给用户(deps 信号回主线程弹框,每会话一次)。
            if o.get("check_deps"):
                try:
                    from . import deps as _deps
                    if _zeropi:
                        # 无 PI 流程:只体检外部 CLI(Siril/StarNet/GraXpert,零 PI 全靠它们),
                        # 跳过 PI 插件探测(需 runner、且与本流程无关)——PI 插件全标"有"以略过
                        _miss = _deps.report({d["sym"]: True for d in _deps.REGISTRY}, _deps.probe_external())
                    else:
                        # PI 流程:只体检 PI 模块(BXT/SXT/NXT/StarNet2/SPCC…),**跳过外部 CLI 探测**——
                        # 外部 CLI(cosmicclarity/Siril/rc-astro/DeepSNR…)是零 PI 后端,PI 模式用 PI 自带插件、
                        # 与其无关,不该提示装 SASpro 等(外部全标"有"以略过)。
                        # PI 脚本(PCS 等)一并带上:它们不注册 PJSR 符号,probe() 看不见,只能按文件探
                        _miss = _deps.report(_deps.probe(), {d["sym"]: True for d in _deps.EXTERNAL},
                                             _deps.probe_scripts())
                    if _miss:
                        self.log.emit("\n" + _deps.format_text(_miss))
                        self.deps.emit(_miss)
                except Exception as _de:
                    self.log.emit(f"[插件体检] 跳过(探测失败:{_de})")
            # 【无 PI 原始素材叠加】zero-PI OSC 单主流程(RGB/HOO)+ 原始素材(mode2)→ 先 Siril stack_engine
            #   叠加出 master(零 PI),再喂后期引擎(修复此前"zero-PI + 原始素材"把空输入喂给引擎的坏组合)。
            #   校准场可由校准场库自动匹配回填。SHO(per-filter 多通道)不走此路 → 明确提示用 registered 目录。
            if _zeropi and o.get("raw"):
                if self.kind not in ("rgb", "hoo"):
                    self.log.emit("[✗] 无 PI SHO 暂不支持从原始素材直接叠加(per-filter 需按滤镜分组)。"
                                  "请改用『对齐子帧目录』(registered,含各滤镜子目录)作为输入。")
                    self.done.emit(False, "", "", {})
                    sys.stdout = old
                    return
                self.log.emit("[叠加] 无 PI 原始素材 → Siril stack_engine 叠加(零 PixInsight,不走 PI WBPP)…")
                try:
                    self.inp = self._zeropi_stack_raw(o["raw"], o)
                except Exception as _se:
                    self.log.emit(f"[✗] 无 PI 叠加失败:{_se}")
                    self.done.emit(False, "", "", {})
                    sys.stdout = old
                    return
                self.log.emit(f"[叠加] 无 PI master(全程零 PixInsight):{self.inp}")
            # 【无 PI · Siril 引擎】SHO 勾选「无 PI」→ 走 sho_engine(Siril 整合+去星+AI降噪+比例控制器,零 PixInsight)。
            #   self.inp = registered 目录(含各滤镜子目录);run_sho_from_dir 自做分类/整合/后期,返回单 PNG。
            if self.kind == "sho" and o.get("zeropi"):
                from . import sho_engine
                _pal = o.get("zpreset", "goldblue")
                self.log.emit(f"[无 PI SHO] Siril 引擎(预设 {_pal})…这会跑整合→去星→AI降噪→揭示→比例控制器→DeepSNR→彩色星点")
                _out = str(config.RUN_DIR / "zeropi_sho")
                png = sho_engine.run_sho_from_dir(self.inp, _out, palette=_pal,
                                                  timeout=max(o["timeout"], 3600.0), log=self.log.emit)
                self.log.emit(f"[无 PI SHO] 成片(全程零 PixInsight):{png}")
                self.preview.emit(png)
                self.done.emit(True, png, "", {})
                return
            # 【无 PI · Siril 引擎】RGB 勾选「无 PI」→ 走 rgb_engine(真 SPCC 校色 + GHS 压核 + 带蒙版降噪,零 PixInsight)。
            #   self.inp = OSC 单张 master(母版模式)或子帧目录;run_rgb_from_dir 自做整合/校色/后期,返回单 PNG。
            if self.kind == "rgb" and o.get("zeropi_rgb"):
                from . import rgb_engine
                _pal = o.get("rgbpreset", "natural")
                _ha_dir = (o.get("ha_dir") or "").strip()
                # 从原始素材叠加来的 master 路径不含设备名 → 传感器认不出;用原始亮场目录名识别并显式传入(保真 SPCC)。
                # 非原始叠加(母版/子帧模式):sensor 留 None,由引擎从输入路径自识别(路径本就含设备名)。
                _sensor = _oscf = None
                _refl = getattr(self, "_raw_ref_light", "")
                if o.get("raw") and _refl:
                    _sensor, _oscf = rgb_engine.guess_sensor(_refl)
                    self.log.emit(f"[无 PI RGB] 传感器识别(自原始亮场目录 {os.path.basename(_refl)}):"
                                  f"{_sensor or '未知 → 星场白平衡兜底'}")
                # 填了窄带目录 → RGB+H/HO(rgb_ha_engine):RGB 底 + 星点配准窄带 + 线性连续谱扣除 + HII 融合
                if _ha_dir:
                    from . import rgb_ha_engine
                    _hp = o.get("hapreset", "galaxy")
                    # 界面档 → 引擎档(见 _ZEROPI_HAPRESET):原样传会 KeyError;对不上的档开跑前就响亮说明
                    _zp, _zwarn = _ZEROPI_HAPRESET.get(_hp, _ZEROPI_HAPRESET_OTHER)
                    if _zwarn:
                        self.log.emit(f"[无 PI RGB+H/HO] ★ {_zwarn}")
                    _hpnote = "" if _zp == _hp else f"(界面选 {_hp})"
                    self.log.emit(f"[无 PI RGB+H/HO] Siril 引擎(RGB 预设 {_pal} + 窄带 {_zp}{_hpnote})…"
                                  "RGB底→星点配准HO→线性连续谱扣除→黑点拒噪HII→screen融合→中性灰")
                    self.log.emit(f"[无 PI RGB+H/HO] 窄带 Ha/OIII 目录:{_ha_dir}")
                    _out = str(config.RUN_DIR / "zeropi_rgbha")
                    png = rgb_ha_engine.run_rgb_ha_from_dirs(self.inp, _ha_dir, _out, palette=_pal, preset=_zp,
                                                             sensor=_sensor, oscfilter=_oscf,
                                                             timeout=max(o["timeout"], 2400.0), log=self.log.emit)
                    self.log.emit(f"[无 PI RGB+H/HO] 成片(全程零 PixInsight):{png}。"
                                  "如有残留灰尘投影,点『灰尘修复』圈选自动中和色度。")
                    if _zwarn:   # 跑了几十分钟,开头那条早滚走了 → 成片旁再提一句
                        self.log.emit("[无 PI RGB+H/HO] ★ 提醒:这张成片的窄带是按「只增强星系的窄带信号」叠的,"
                                      "不是界面上选的那种(无 PI 引擎没有);原因和改法见开跑时的说明。")
                    self.preview.emit(png)
                    self.done.emit(True, png, "", {})
                    return
                _bg = o.get("bg_extract") or "1"           # None(跟随预设)→ 引擎默认 d1
                _rv = o.get("rgb_reveal")                   # None=跟随预设;0/0.5/0.9=显式档
                _em = o.get("rgb_emission", 0.0)            # 发射感知揭示(红丝);0=关
                _gc = o.get("glow_clean", "auto")           # 残留辉光清除:auto/on/off
                self.log.emit(f"[无 PI RGB] Siril 引擎(预设 {_pal},梯度 {_bg},揭示 {'预设' if _rv is None else _rv}"
                              f"{f',发射{_em}' if _em else ''},辉光 {_gc})…"
                              "真 SPCC 校色→GHS 压核→残留辉光清除→带主体蒙版 DeepSNR 降噪→温和饱和")
                _out = str(config.RUN_DIR / "zeropi_rgb")
                png = rgb_engine.run_rgb_from_dir(self.inp, _out, palette=_pal, sensor=_sensor, oscfilter=_oscf,
                                                  bg_extract=_bg, reveal=_rv, emission=_em, glow_clean=_gc,
                                                  timeout=max(o["timeout"], 1800.0), log=self.log.emit)
                self.log.emit(f"[无 PI RGB] 成片(全程零 PixInsight):{png}")
                self.preview.emit(png)
                self.done.emit(True, png, "", {})
                return
            # 【无 PI · Siril 引擎】HOO 勾选「无 PI」→ 走 hoo_engine(OSC 双窄带提取 Ha/OIII + 线性去梯度 + 分通道揭示 + 中性灰,零 PixInsight)。
            if self.kind == "hoo" and o.get("zeropi_hoo"):
                from . import hoo_engine
                _pal = o.get("hoopreset", "oiii")
                self.log.emit(f"[无 PI HOO] Siril 引擎(预设 {_pal})…提取Ha/OIII→线性GraXpert去梯度→去星→分通道揭示→DeepSNR→中性灰")
                _out = str(config.RUN_DIR / "zeropi_hoo")
                png = hoo_engine.run_hoo_from_dir(self.inp, _out, palette=_pal,
                                                  timeout=max(o["timeout"], 1800.0), log=self.log.emit)
                self.log.emit(f"[无 PI HOO] 成片(全程零 PixInsight):{png}")
                self.preview.emit(png)
                self.done.emit(True, png, "", {})
                return
            # 【#1 黑白 per-filter】多通道流程(LRGB/SHO)+ 原始素材 → 先 WBPP 按滤镜叠加,
            #   得到含各滤镜子目录的 registered,直接喂 run_lrgb/run_sho(它们自做逐通道整合)。
            if self.kind in ("lrgb", "sho") and o.get("raw"):
                self.log.emit("[叠加] 黑白 per-filter 原始素材 → WBPP(读真实 FILTER 按滤镜分组校准对齐)…")
                self.inp = pipeline.run_wbpp_stack(o["raw"], timeout=max(o["timeout"], 5400.0))
                self.log.emit(f"[叠加] WBPP 完成,registered:{self.inp}")
            if self.kind == "lrgb":
                res = pipeline.run_lrgb(self.inp, timeout=o["timeout"], crop_frac=o["crop_frac"],
                                        neb_sat=o["neb_sat"], maskstretch_iters=o["ms_iters"],
                                        ghs_d=o["ghs_d"], core_thr=o["core_thr"], ha_amount=o["ha"],
                                        stop_after=o["stop_after"])
            elif self.kind == "sho":
                # SHO / HOO 窄带(星云)+ RGB(星点)。输入三种来源:
                #   原始素材 → 上面 WBPP 出的 registered 目录(按目录名/FILTER 自动分通道);
                #   对齐子帧目录 → **按每行选的滤镜**分通道(以前这里直接把空的 self.inp 传进去,
                #     「源:registered:.」→ 各通道 0 张,用户 2026-10-06 SH2-224);
                #   已叠加母版 → 每个通道一张母版,跳过整合。
                _ch, _ms, _sk = self._nb_inputs(o)
                if _sk:
                    self.log.emit("[窄带] 这些行的滤镜不参与窄带合成,跳过:" + "、".join(_sk))
                if _ch or _ms:
                    self.log.emit("[窄带] " + ";".join(
                        f"{_k}:{('母版 ' + Path(_ms[_k]).name) if _k in _ms else str(len(_ch.get(_k, []))) + ' 张'}"
                        for _k in ("H", "O", "S", "R", "G", "B") if _k in _ch or _k in _ms))
                res = pipeline.run_sho(self.inp if not (_ch or _ms) else "",
                                       channels=(_ch if (_ch or _ms) else None), masters=_ms or None,
                                       nb_mode=o.get("nb_mode") or "auto",
                                       palettes=o["palettes"], timeout=max(o["timeout"], 2400.0),
                                       saturation=o["neb_sat"] + 0.35, dust_reveal=o["dust_reveal"],
                                       grade_curve=o.get("grade_curve"), darkstruct=o.get("darkstruct", "auto"),
                                       stop_after=o["stop_after"], pause_gate=self._pause_gate)
            else:
                inp = self.inp
                raw = o.get("raw")
                reg = None
                _ha_from_stack = ""      # 原始叠加里双窄带滤镜组 → 叠出的 NB master(供 run_rgb 融合)
                # 【黑白相机·宽带 + 窄带(用户 2026-09-28)】「在 RGB 图像的部分,本质上都是处理一张宽带图像,
                #   只是窄带素材多了一步通道合成」→ 先得到每个滤镜一张母版,R/G/B 合成一张彩色底,
                #   Hα/OIII 交给 run_rgb 逐通道处理;之后的融合与彩色相机完全同一套。
                _nb_mono = None
                _mono_done = False
                if self.kind == "rgb" and o.get("camera") == "mono":
                    _mm = dict(o.get("mono_masters") or {})
                    if raw:
                        self.log.emit("[叠加] 黑白相机 → WBPP 按真实 FILTER 头分滤镜校准对齐…")
                        _reg = pipeline.run_wbpp_stack(raw, timeout=max(o["timeout"], 5400.0))
                        self.log.emit(f"[叠加] WBPP 完成,对齐子帧目录:{_reg} → 每个滤镜整合一张母版")
                        _mm = pipeline.integrate_mono_filters(_reg, timeout=max(o["timeout"], 1800.0),
                                                              log=self.log.emit)
                    elif o["integrate_first"]:
                        for _k in ("R", "G", "B", "L", "Ha", "OIII", "SII"):
                            _dirs = [g["dir"] for g in (o.get("reg") or []) if g.get("filter") == _k]
                            if _dirs:
                                _home = o.get("stack_home") or _reg_project_dir(_dirs[0])
                                _out = f"{_home}/masterLight_{_k}.xisf"
                                self.log.emit(f"[对齐子帧] 黑白 {_k}:{len(_dirs)} 个目录 → 整合 {_out}")
                                _mm[_k] = self._integrate_reg_group(_dirs, _out, o)
                    self.log.emit("[母版] 黑白:" + "、".join(f"{_k} {Path(str(_v)).name}" for _k, _v in _mm.items()))
                    inp = pipeline.mono_rgb_master(_mm, timeout=max(o["timeout"], 900.0), log=self.log.emit)
                    _nb_mono = {_k: _mm[_k] for _k in ("Ha", "OIII", "SII") if _mm.get(_k)} or None
                    if _nb_mono and o.get("mode") != "rgb_fuse":
                        _nb_mono = None
                    _mono_done = True
                if raw and not _mono_done:
                    # 【按滤镜分组(用户 2026-09-04:窄带=普通亮场只是滤镜不同)】拆出双窄带组单独叠 NB master,
                    #   宽带(IR-UVcut)组走主流程出 RGB 底;NB master 当 ha_dir 传给 run_rgb 融合(宽带+小红花)。
                    _all_nights = raw.get("nights") or []
                    _nb_nights = [n for n in _all_nights if n.get("light") and n.get("filter", "uvir") != "uvir"]
                    _bb_nights = [n for n in _all_nights if n.get("filter", "uvir") == "uvir"]
                    if _nb_nights and o.get("mode") == "rgb_fuse":
                        self.log.emit(f"[叠加] 检出双窄带亮场 {len(_nb_nights)} 组 → 单独按滤镜叠加出窄带母版(用于增强气体信号)…")
                        try:
                            # 【关键:独立项目目录(用户 2026-09-04 发现的撞车 bug)】NB 与 RGB 若同 target →
                            #   同一个 registered 目录,宽带 WBPP 轮询会抓到窄带残留的 registered、把窄带当宽带整合
                            #   (609 张宽带只出 238 张窄带 master)。→ NB 用 target_HO 独立目录,彻底隔离。
                            _nb_target = (raw.get("target") or "stack").rstrip("/") + "_HO"
                            _nb_raw = dict(raw, nights=_nb_nights, target=_nb_target)
                            _ha_from_stack = self._stack_filter_group(_nb_raw, o, "双窄带")
                            self.log.emit(f"[叠加] 双窄带 master:{_ha_from_stack}(将作为 ha_dir 融合进宽带底)")
                        except Exception as _nbe:
                            import traceback as _tb; _tb.print_exc()
                            self.log.emit(f"[叠加] 双窄带叠加失败 → 跳过融合,只出纯 RGB:{_nbe}")
                            _ha_from_stack = ""
                        raw = dict(raw, nights=_bb_nights)   # 主流程只叠宽带(IR-UVcut)
                    # 多晚 + 校准库 → **逐晚跑 WBPP**(各晚各自温度暗场;WBPP 读不到 Dwarf 的 DET-TEMP、
                    #   单次只出一个 dark master → 单次会把第1晚暗场套给所有晚、温度错配)。单晚/无库自动退回单次。
                    _vn = [n for n in (raw.get("nights") or []) if n.get("light")]
                    _lib = (raw.get("calib_library") or "").strip()
                    if len(_vn) > 1 and _lib and os.path.isdir(_lib):
                        self.log.emit(f"[叠加] 多晚({len(_vn)}晚)+ 校准库 → 自定义滤镜法 WBPP **逐晚跑**"
                                      "(各晚各自温度暗场,再汇总整合;避免 WBPP 单暗场温度错配)…")
                        reg = pipeline.run_wbpp_stack_pernight(raw, timeout=max(o["timeout"], 3600.0))
                    else:
                        self.log.emit("[叠加] 原始素材 → 自定义滤镜法 WBPP(校准+去马+对齐)…")
                        reg = pipeline.run_wbpp_stack(raw, timeout=max(o["timeout"], 3600.0))
                    self.log.emit(f"[叠加] WBPP 完成,对齐子帧目录:{reg}")
                elif o["integrate_first"] and not _mono_done:
                    # mode1 对齐子帧:**按滤镜分组各自直接整合**(无 WBPP,已对齐)。IR-UVcut→RGB 底,
                    #   双窄带→NB master 用于增强气体信号。与原始叠加一致的模型(用户 2026-09-04)。
                    _rg = o.get("reg") or []
                    if _rg:
                        _bb = [g["dir"] for g in _rg if g.get("filter", "uvir") == "uvir"]
                        _nbg = [g["dir"] for g in _rg if g.get("filter", "uvir") != "uvir"]
                        if not _bb:
                            raise RuntimeError("对齐子帧:缺 IR-UVcut 宽带目录(RGB 底必需)")
                        # 母版存**项目目录**(_stack_home 定的;旧版存第一个子帧目录的上一级 = registered/ 里,
                        #   多段合并时还落进第一段的 registered —— 用户 2026-10-06 找不到、只能重叠)
                        _home = o.get("stack_home") or _reg_project_dir(_bb[0])
                        if _nbg and o.get("mode") == "rgb_fuse":
                            self.log.emit(f"[对齐子帧] 双窄带 {len(_nbg)} 个目录 → 整合成窄带母版(用于增强气体信号)…")
                            try:
                                _nbout = f"{_home}/masterLight_HO.xisf"
                                _ha_from_stack = self._integrate_reg_group(_nbg, _nbout, o)
                                self.log.emit(f"[对齐子帧] 双窄带 master:{_ha_from_stack}")
                            except Exception as _nbe:
                                self.log.emit(f"[对齐子帧] 双窄带整合失败 → 跳过融合:{_nbe}")
                        self.log.emit(f"[对齐子帧] IR-UVcut 宽带 {len(_bb)} 个目录 → 整合 RGB 底…")
                        _bbout = f"{_home}/masterLight.xisf"
                        inp = self._integrate_reg_group(_bb, _bbout, o)
                        self.log.emit(f"[整合] 宽带 masterLight 在项目目录:{inp}"
                                      "(下次同样的子帧直接复用;也可以拿它进 PI 手动处理)")
                        reg = None                  # 已整合完,跳过下面的通用整合块
                    else:
                        reg = inp                   # 兜底:旧单目录(ed_input)
                if reg is not None:
                    keep = None
                    if o.get("detrail"):   # 「叠加前智能筛帧」:去卫星/飞机线 + 去云/低透明度帧
                        dropped = set(); all_subs = None
                        self.log.emit("[筛帧] 残差法检测卫星/飞机线…")
                        dt = pipeline.run_detrail(reg, timeout=max(o["timeout"], 1800.0))
                        all_subs = dt.get("all")
                        if dt.get("dropped"):
                            self.log.emit(f"[筛帧] 检出含轨迹 {len(dt['dropped'])} 帧,剔除。")
                            dropped |= set(dt["dropped"])
                        elif dt.get("skipped"):
                            self.log.emit("[筛帧] 含轨迹帧过多,为保信噪未剔。")
                        else:
                            self.log.emit("[筛帧] 未检出轨迹。")
                        self.log.emit("[筛帧] 逐帧背景检测有云/低透明度帧…")
                        try:
                            cl = pipeline.run_cull(reg, timeout=max(o["timeout"], 1800.0))
                            all_subs = all_subs or cl.get("all")
                            if cl.get("dropped"):
                                self.log.emit(f"[筛帧] 检出有云/背景异常 {len(cl['dropped'])} 帧,剔除。")
                                dropped |= set(cl["dropped"])
                            elif cl.get("skipped"):
                                self.log.emit("[筛帧] 无离散云帧(或比例过高未剔,可能整晚透明度差)。")
                            else:
                                self.log.emit("[筛帧] 未检出云帧。")
                        except Exception as ce:
                            self.log.emit(f"[筛帧] 去云跳过(异常):{ce}")
                        if dropped and all_subs:
                            keep = [s for s in all_subs if s not in dropped]
                            self.log.emit(f"[筛帧] 共剔除 {len(dropped)} 张,保留 {len(keep)} 张整合。")
                    # OSC:整合出的 masterLight **存到输出目录**(registered 的上级项目目录),方便用户自己后期
                    #   (「已叠加母版」直接加载)+ 我们调试复用(改调色只重跑后期、免重整合)。用户 2026-09-03。
                    _projdir = str(Path(reg).parent).replace("\\", "/")
                    _master_out = "%s/masterLight.xisf" % _projdir
                    try:
                        inp = pipeline.run_integrate(reg, out_path=_master_out,
                                                     timeout=max(o["timeout"], 1800.0), images=keep)
                        self.log.emit(f"[整合] masterLight 已存输出目录:{_master_out}"
                                      "(下次可用『已叠加母版』直接加载它调色,免重整合)")
                    except Exception as _ie:
                        # 【2026-09-18 M78 教训】这个兜底本来是给"输出目录写不进"准备的,但它把**超时**
                        #   也一并接了下来:PI 还在算第一趟的时候,又丢了一趟同样的 830 帧整合进去,两趟
                        #   互抢资源各超时一次,白烧 2.6 小时——而事后查 done/ 两趟其实**都成功了**。
                        #   ① 超时绝不重整合(重来只会更慢),直接往上抛,让用户看到真错误;
                        #   ② 其余错误先看盘上有没有成品(整合可能早写完、炸在事后步骤),有就直接用。
                        if isinstance(_ie, TimeoutError):
                            raise
                        if Path(_master_out).exists():
                            self.log.emit(f"[整合] 出错({_ie})但 masterLight 已在盘上 → 直接使用:{_master_out}")
                            inp = _master_out
                        else:
                            self.log.emit(f"[整合] 存输出目录失败({_ie})→ 退回临时目录")
                            inp = pipeline.run_integrate(reg, timeout=max(o["timeout"], 1800.0), images=keep)
                # 无暗场校准(纯亮场,如 Seestar 或 Dwarf 未给暗场)→ 干净背景 profile,避免揭示放大残留热噪
                # 黑白原始素材的暗场是目录列表 darks(彩色/智能望远镜是单个 dark),两种都算「给了暗场」
                lights_only = bool(raw) and not ((raw.get("dark") or "").strip() or raw.get("darks"))
                if self.kind == "hoo":
                    res = pipeline.run_hoo(inp, timeout=o["timeout"], stop_after=o["stop_after"])
                else:
                    if lights_only:
                        self.log.emit("[后期] 无暗场 → 干净背景模式(不揭示/压背景)")
                    # 智能望远镜(dwarf/seestar)管线:星点残留绿铸明显 → 加强星点去绿(其他管线不动)
                    _smart = bool(raw) and (raw.get("device") in ("dwarf", "seestar"))
                    _star_scnr = 0.8 if _smart else 0.0
                    # 蓝星点补偿:量化证实对 Dwarf3 弱蓝星点无效(色相蒙版选不中准中性蓝星,blueFrac 纹丝不动),
                    #   且硬造会牺牲 SPCC 真彩 → 用户定"保持 SPCC 真彩"→ 关闭(star_blue 参数保留=0 备用)。
                    _star_blue = 0.0
                    if _smart:
                        self.log.emit("[后期] 智能望远镜 → 星点加强去绿(SCNR 0.8);蓝弱保持 SPCC 真彩不硬补")
                    # 宽带 + 双窄带融合(用户文章法「给星系加小红花」):PI 底出片后在去星星系上叠加 Ha/OIII
                    #   (配准→去星→拉伸→chansplit→nbinject)。窄带 master 来源:原始叠加/对齐子帧=按滤镜标签叠出的
                    #   NB master(_ha_from_stack);已叠加母版模式=母版行里标了窄带滤镜的第一路(o["ha_dir"])。
                    #   多路窄带(HO+Hβ/SII)在 o["nb_masters"],留待后续多窄带引擎。galaxy 克制/vivid 更跳。
                    _ha_dir = _ha_from_stack or (o.get("ha_dir") or "").strip()
                    _hp = o.get("hapreset", "emission")
                    _ha_amt = 1.2 if _hp == "emission_vivid" else 0.8
                    # 融合方法:发射星云(整层Ha/OIII)/ 星系小红花(离散HII)/ 保留主体明暗(比值上色,小而亮的星云)
                    _ha_preset = _hp if _hp in ("galaxy", "compact") else "emission"
                    if _ha_dir or _nb_mono:
                        self.log.emit(f"[窄带融合] PI 底 + "
                                      f"{ {'galaxy': '只增强星系的窄带信号', 'compact': '保留主体明暗'}.get(_ha_preset, '整片星云增强') }"
                                      f"(kHa={_ha_amt}):"
                                      + ("黑白 " + "、".join(_nb_mono) if _nb_mono else _ha_dir))
                    res = pipeline.run_rgb(inp, timeout=o["timeout"], ghs_d=o["ghs_d"],
                                           neb_sat=o["neb_sat"], recombine_stars=o["stars"],
                                           stretch_judge=o["stretch_judge"], target=o["target"],
                                           reveal=o["reveal"], lhe=o["lhe"], lights_only=lights_only,
                                           star_scnr=_star_scnr, star_blue=_star_blue, stop_after=o["stop_after"],
                                           pause_gate=self._pause_gate,
                                           # 分步询问模式才挂岔口回调;全自动传 None = 严格空操作
                                           decide_gate=(self._decide_gate if o.get("stepwise") else None),
                                           # 手动调色:只有勾了才挂;不挂时管线里那段严格空操作
                                           color_gate=(self._color_gate if o.get("mancolor") else None),
                                           ha_dir=(_ha_dir or None), ha_amount=_ha_amt, ha_preset=_ha_preset,
                                           nb_mono=_nb_mono, mono_rgb=_mono_done)
            # 结果预览:优先用 run_sho 记录的**主版成片**(_finals[主配色]),否则回退到最后一个预览
            finals_map = (res or {}).get("_finals") or {}
            main_xis = ""
            if finals_map:
                # 主配色 = pal_list[0];dict 保序,取第一个
                main_xis = next((v for v in finals_map.values() if v and Path(str(v)).exists()), "")
            if main_xis:
                xis = str(main_xis)
                pp = Path(str(main_xis)).with_suffix(".png")
                png = str(pp) if pp.exists() else ""
            # 【真·成片优先(用户 2026-09-10 M52「graxpert 后预览又变回处理前」)】run_rgb 显式登记的
            #   _final = r14 尾部(终梯度 GraXpert/星点饱和/背景克制)全跑完的成片。旧「取最后一个带 preview
            #   的 results 条目」会落到 r14_final(尾部之前)→ 成片丢了梯度修复/饱和/背景克制。显式优先 _final。
            if not png:
                _fin = res.get("_final") if isinstance(res, dict) else None
                if isinstance(_fin, dict) and _fin.get("preview") and Path(str(_fin["preview"])).exists():
                    png = str(_fin["preview"])
                    _im = _fin.get("image")
                    xis = str(_im) if _im and Path(str(_im)).exists() else ""
            if not png:
                for tag in reversed(list(res.keys())):
                    if not isinstance(res.get(tag), dict):
                        continue
                    p = res[tag].get("preview")
                    if p and Path(p).exists():
                        png = str(p)
                        im = res[tag].get("image")
                        xis = str(im) if im and Path(str(im)).exists() else ""
                        break
            # 交棒:若流程按设置停在中间步骤,把信息带出去(GUI 据此提示 + 自动释放 PI)
            ho = (res or {}).get("_handoff")
            if ho:
                scores["_handoff"] = ho
            # 多配色:把每档的成片 xisf 都带出去(GUI 做配色切换 + 导出你选的那档)
            if finals_map and not ho:
                scores["_finals"] = {k: str(v) for k, v in finals_map.items()
                                     if v and Path(str(v)).exists()}
            # 评委结论:run_sho 已评过(含打分 + "退回哪一步")→ 直接透传,不再另调评委。
            _critic = (res or {}).get("_critic")
            if _critic and not ho:
                scores["_critic"] = _critic
                scr = _critic.get("score") or {}
                if scr.get("overall") is not None:
                    scores.update({k: scr.get(k, 0) for k in
                                   ("overall", "background", "star_color", "core", "comment")})
            # 确定性质量指标(不依赖 LLM):有 run_rgb 的 _quality 就用,否则在成片上补测。
            #   → 既展示给用户(硬数据),又喂给 LLM 评委的 context 让主观打分有据(此前评委拿不到指标)。
            _qm = (res or {}).get("_quality")
            _qual = _qm.get("metrics") if isinstance(_qm, dict) and "metrics" in _qm else None
            if not _qual and png and not ho:
                try:
                    from . import quality
                    # 优先测全分辨率成片 xisf(非降采样预览 png,否则星点被缩糊、饱和虚低;用户 2026-09-06 M5)
                    _qsrc = (str(self._final_xisf) if getattr(self, "_final_xisf", None)
                             and Path(str(self._final_xisf)).exists() else png)
                    _qual = quality.measure(_qsrc)
                    if _qual.get("error"):
                        _qual = None
                except Exception:
                    _qual = None
            if _qual:
                scores["_quality"] = _qual
            # 同视场参考导出的**因目标而异**目标一并带上:星点饱和的甜区要按这个天体定
            #   (固定 0.22 对 M31 这类宽视场目标不适用),见 quality.s_star_band
            if isinstance(_qm, dict) and _qm.get("ref_targets"):
                scores["_ref_targets"] = _qm["ref_targets"]
            # LLM 主观评分**不在此阻塞**:成片 + 确定性指标先出(下面 done 立即"完成"),
            #   主观分由主线程 _finished 后台异步补(kimi-k3 推理慢,曾把"完成"卡住 1~3 分钟;
            #   确定性指标已够看,LLM 分作补充)。SHO 走 run_sho 已带 _critic/overall,不再异步。
            self.done.emit(True, png, xis, scores)
        except protocol.CancelledError:
            # 中止不是故障:不打堆栈。它继承 BaseException(好穿过管线里 144 处兜底),
            #   所以必须在这里**显式**接住,否则线程会带着未捕获异常退出、界面卡在「处理中」。
            self.log.emit(t(chr(10) + '[中止] 已停止。'))
            self.done.emit(False, '', '', {})
        except Exception as e:
            self.log.emit("\n[✗] %s" % e)
            if str(e) != "已中止":
                self.log.emit(traceback.format_exc())
            self.done.emit(False, "", "", {})
        finally:
            sys.stdout = old

    def _sniff(self, s):
        for line in s.splitlines():
            ls = line.strip()
            if ls.startswith("[preview]"):
                pv = ls[len("[preview]"):].strip()
                if pv:
                    self.preview.emit(pv)
                continue
            if "[旁路]" in line:
                # 旁路步骤(如喂在线天文解析的 r02c_solveimg):是真任务、会花时间,但**不属于成片链路**。
                # 它的 op 名可能与正式步骤撞车(solveimg 也是 stretch),不排除就会把阶段指示器
                # 提前推到「拉伸」——而阶段是单调取最大的,推过去就回不来了。见 pipeline.step(side=True)。
                continue
            if "->" in line and "]" in line and "[" in line:
                seg = line.split("]", 1)[1].strip()
                op = seg.split("->")[0].strip().split()[0] if "->" in seg else ""
                if op:
                    self.progress.emit(op)


# 【混合模式(用户 2026-09-04 重构:流程=成片混合方式,相机/滤镜是正交的输入维度)】
#   纯RGB / RGB星点+窄带天体 / 纯窄带 / 全量RGB+窄带。签名色沿用原设计(银/金/青/冷银)。
FLOW_SIG = {"pure_rgb": "#C6D0DC", "rgb_nb": "#E2AC61", "pure_nb": "#5FD0C4", "rgb_fuse": "#9DB4CC"}
# 旧 flow key → 新混合模式 key(兼容老 .ttproj 工程加载)
FLOW_MIGRATE = {"rgb": "pure_rgb", "sho": "rgb_nb", "hoo": "pure_nb", "lrgb": "pure_rgb"}
# 流程卡:签名徽章字、卡名、一句话(配置屏 4 张卡)
FLOW_CARD = {
    "pure_rgb": ("RGB",  "纯 RGB",          "只用宽带 R/G/B,最自然的真彩。"),
    "rgb_nb":   ("R+N",  "RGB 星点 + 窄带天体", "天体用窄带合成配色,星点保留宽带的真实颜色。"),
    "pure_nb":  ("NB",   "纯窄带",           "画面全部来自 Hα / OIII / SII,星点也是窄带的。"),
    "rgb_fuse": ("R⊕N",  "全量 RGB + 窄带",   "宽带真彩做底,窄带只把红色气体和 OIII 发射区加强。"),
}
# 流程卡上的三色圆点(精修 2026-10-10):用颜色说明这个流程的成片大致是什么色,替代内部代号徽章
FLOW_DOTS = {"pure_rgb": ("#D86A62", "#7FA98A", "#5B8FD6"), "rgb_nb": ("#E2AC61", "#5FD0C4", "#C6D0DC"),
             "pure_nb": ("#C85A5A", "#5FD0C4", "#E2AC61"), "rgb_fuse": ("#C6D0DC", "#D86A62", "#5FD0C4")}


class Loupe(QWidget):
    """AstroBin 式放大镜:按住成片预览时,在光标处画一个圆形放大镜,
    显示**全分辨率**原图的该区域(素材大时约 1:1;小图上仍保证放大)。作 preview 的子控件,
    WA_TransparentForMouseEvents=事件仍落到 preview(由 eventFilter 驱动移动/裁剪)。"""

    def __init__(self, parent=None, dia=260, ring="#55DDA0"):
        super().__init__(parent)
        self._dia = dia
        self._ring = ring
        self._crop = None
        self.setFixedSize(dia, dia)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def set_crop(self, pm):
        self._crop = pm
        self.update()

    def paintEvent(self, e):
        if self._crop is None or self._crop.isNull():
            return
        d = self._dia
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        path = QPainterPath()
        path.addEllipse(1.0, 1.0, d - 2.0, d - 2.0)
        p.setClipPath(path)
        # 裁片按短边铺满圆(已在外部缩放到 dia)
        p.drawPixmap(0, 0, self._crop)
        p.setClipping(False)
        # 深色描边打底 + accent 环(在任何亮度的天体图上都清晰)
        p.setPen(QPen(QColor(0, 0, 0, 150), 3))
        p.drawEllipse(2, 2, d - 4, d - 4)
        p.setPen(QPen(QColor(self._ring), 2))
        p.drawEllipse(2, 2, d - 4, d - 4)
        p.end()


class _FlowLayout(QLayout):
    """经典流式布局:子控件按宽度自动换行(缩略图网格随对话框宽度重排,不用手动重排 N 个控件)。"""

    def __init__(self, parent=None, margin=0, spacing=10):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        s += QSize(m.left() + m.right(), m.top() + m.bottom())
        return s

    def _do(self, rect, test):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_h = 0
        sp = self.spacing()
        for it in self._items:
            sz = it.sizeHint()
            w, h = sz.width(), sz.height()
            if x + w > right and line_h > 0:
                x = rect.x() + m.left()
                y += line_h + sp
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x += w + sp
            line_h = max(line_h, h)
        return y + line_h + m.bottom() - rect.y()


class _CullThumbWorker(QThread):
    """后台流式生成缩略图:逐帧 解拜耳+STF 拉伸+缩放 → 发 QImage 给对话框(边生成边可筛)。"""
    ready = pyqtSignal(int, object, float, str)   # idx, QImage(或None), 背景中值bg, 错误串
    progressed = pyqtSignal(int, int)             # done, total

    def __init__(self, frames, pat_hint, px=190, parent=None):
        super().__init__(parent)
        self._frames = frames                     # [路径]
        self._pat = pat_hint
        self._px = px
        self._abort = False

    def stop(self):
        self._abort = True

    def run(self):
        from PyQt5.QtGui import QImage
        from . import frame_preview as _fp
        total = len(self._frames)
        for i, path in enumerate(self._frames):
            if self._abort:
                break
            qi, bg, err = None, -1.0, ""
            try:
                u8, st = _fp.render_rgb8(path, pat_hint=self._pat, max_px=self._px)
                h, w = int(u8.shape[0]), int(u8.shape[1])
                qi = QImage(u8.data, w, h, 3 * w, QImage.Format_RGB888).copy()
                bg = float(st.get("bg", -1.0))
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            if self._abort:
                break
            self.ready.emit(i, qi, bg, err)
            self.progressed.emit(i + 1, total)


class _CullTile(QFrame):
    """一帧的卡片:缩略图 + 文件名 + 背景值;点卡片切换保留/剔除,右上🔍看大图。"""
    toggled = pyqtSignal(int)
    zoom = pyqtSignal(int)
    TW, TH = 190, 150                              # 缩略图区
    _KEEP_BORDER = "#2B3440"
    _CULL_BORDER = "#E86A5C"

    def __init__(self, idx, name, badge="", parent=None):
        super().__init__(parent)
        self.idx = idx
        self.culled = False
        self._name = name
        self.setFixedSize(self.TW + 12, self.TH + 58)
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 5)
        v.setSpacing(3)
        self.thumb = QLabel(t("载入中…"))
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedSize(self.TW, self.TH)
        self.thumb.setStyleSheet("background:#0C0F14; color:#5A6470; border-radius:3px;")
        v.addWidget(self.thumb, alignment=Qt.AlignHCenter)
        # 剔除遮罩(红叉,盖在缩略图上)
        self.overlay = QLabel("✕", self.thumb)
        self.overlay.setAlignment(Qt.AlignCenter)
        self.overlay.setGeometry(0, 0, self.TW, self.TH)
        self.overlay.setStyleSheet(
            "background:rgba(190,50,44,0.42); color:#FFE8E4; font-size:34px; font-weight:bold; border-radius:3px;")
        self.overlay.hide()
        # 右上🔍放大按钮
        self.btn_zoom = QToolButton(self.thumb)
        self.btn_zoom.setText("🔍")
        self.btn_zoom.setCursor(Qt.PointingHandCursor)
        self.btn_zoom.setToolTip(t("看大图(细看云/梯度/拖线)"))
        self.btn_zoom.setStyleSheet(
            "QToolButton{background:rgba(10,14,20,0.70); color:#DCE3EA; border:none; border-radius:11px;"
            "font-size:12px; padding:0;} QToolButton:hover{background:rgba(85,221,160,0.85); color:#0C0F14;}")
        self.btn_zoom.setFixedSize(22, 22)
        self.btn_zoom.move(self.TW - 26, 4)
        self.btn_zoom.clicked.connect(lambda: self.zoom.emit(self.idx))
        # 徽章(机内叠加)
        if badge:
            bd = QLabel(badge, self.thumb)
            bd.setStyleSheet("background:rgba(210,150,40,0.85); color:#12160C; font-size:10px;"
                             "padding:1px 4px; border-radius:3px;")
            bd.move(4, 4); bd.adjustSize()
        from PyQt5.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        el = fm.elidedText(name, Qt.ElideMiddle, self.TW - 2)
        self.lab = QLabel(el)
        self.lab.setToolTip(name)
        self.lab.setStyleSheet("color:#AEB7C2; font-size:11px;")
        v.addWidget(self.lab)
        self.bg_lab = QLabel(t("背景 —"))
        self.bg_lab.setStyleSheet("color:#6B7480; font-size:10px;")
        v.addWidget(self.bg_lab)
        self._restyle()

    def set_image(self, qimg, bg):
        if qimg is not None and not qimg.isNull():
            pm = QPixmap.fromImage(qimg).scaled(self.TW, self.TH, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb.setPixmap(pm)
        else:
            self.thumb.setText(t("读取失败"))
        if bg is not None and bg >= 0:
            self.bg_lab.setText(t("背景 {:.3f}").format(bg))

    def mark_bg_outlier(self):
        self.bg_lab.setStyleSheet("color:#E8A24A; font-size:10px; font-weight:bold;")

    def set_culled(self, on):
        self.culled = bool(on)
        self.overlay.setVisible(self.culled)
        self._restyle()

    def _restyle(self):
        col = self._CULL_BORDER if self.culled else self._KEEP_BORDER
        bw = 2 if self.culled else 1
        self.setStyleSheet(
            f"#culltile{{}} QFrame{{background:#161B22; border:{bw}px solid {col}; border-radius:6px;}}")
        self.setObjectName("culltile")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.toggled.emit(self.idx)
        super().mousePressEvent(e)


class _CullPreviewDialog(QDialog):
    """单帧大图:解拜耳+STF 拉伸后按屏缩放显示,供细看是否有云/梯度/拖线。底部可直接标剔除/保留。"""

    def __init__(self, path, pat_hint, culled, log, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # 去掉标题栏多余的"?"
        self.result_culled = culled
        self._log = log
        self.setWindowTitle(os.path.basename(path))
        self.setStyleSheet("QDialog{background:#0C0F14;} QLabel{color:#C6CED6;}"
                           "QPushButton{background:#1B222B; color:#DCE3EA; border:1px solid #2B3440;"
                           "border-radius:5px; padding:6px 14px;} QPushButton:hover{border-color:#55DDA0;}")
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)
        scr = QApplication.primaryScreen().availableGeometry()
        maxpx = int(min(1500, scr.width() * 0.82, scr.height() * 0.78))
        img = QLabel(t("载入中…"))
        img.setAlignment(Qt.AlignCenter)
        img.setMinimumSize(600, 400)
        v.addWidget(img, 1)
        info = QLabel("")
        info.setStyleSheet("color:#8A94A0; font-size:11px;")
        v.addWidget(info)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            from . import frame_preview as _fp
            from PyQt5.QtGui import QImage
            u8, st = _fp.render_rgb8(path, pat_hint=pat_hint, max_px=maxpx)
            h, w = int(u8.shape[0]), int(u8.shape[1])
            qi = QImage(u8.data, w, h, 3 * w, QImage.Format_RGB888).copy()
            img.setPixmap(QPixmap.fromImage(qi))
            info.setText(t("背景中值 {:.4f} · 解拜耳 {} · 显示 {}×{}").format(st.get("bg", 0), st.get("pat", "?"), w, h))
        except Exception as e:
            img.setText(t("预览失败:{}").format(e))
        finally:
            QApplication.restoreOverrideCursor()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_state = QPushButton("")
        self.btn_state.clicked.connect(self._flip)
        bc = QPushButton(t("关闭"))
        bc.clicked.connect(self.accept)
        row.addWidget(self.btn_state)
        row.addStretch(1)
        row.addWidget(bc)
        v.addLayout(row)
        self._sync_btn()

    def _flip(self):
        self.result_culled = not self.result_culled
        self._sync_btn()

    def _sync_btn(self):
        if self.result_culled:
            self.btn_state.setText(t("↩ 恢复保留此帧"))
            self.btn_state.setStyleSheet("background:#2A1A18; color:#F0C9C3; border:1px solid #E86A5C;"
                                         "border-radius:5px; padding:6px 14px;")
        else:
            self.btn_state.setText(t("✕ 剔除此帧"))
            self.btn_state.setStyleSheet("background:#12241C; color:#BFEBD6; border:1px solid #55DDA0;"
                                         "border-radius:5px; padding:6px 14px;")


class FrameCullDialog(QDialog):
    """手动筛帧对话框:缩略图网格(后台流式解拜耳+快速拉伸),点击切换剔除,🔍看大图,
    『自动标记背景异常』按背景中值离群一键预标(云/月光/梯度帧背景显著偏高)。
    确定后把剔除帧挪进各自帧目录的 _ttlot_culled/(WBPP 扫不到,可逆)。"""

    def __init__(self, frames, pat_hint, log, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # 去掉标题栏多余的"?"
        self._frames = frames                      # [{path,name,parent,culled,stacked}]
        self._pat = pat_hint
        self._log = log
        self._tiles = []
        self._state = [bool(f.get("culled")) for f in frames]   # 目标剔除态
        self._orig = list(self._state)                          # 打开时的物理态(culled=已在子夹)
        self._bg = [None] * len(frames)
        self.setWindowTitle(t("筛帧 · 剔除坏帧(云/梯度/拖线/跑焦)"))
        self.setStyleSheet(
            "QDialog{background:#0C0F14;}"
            "QLabel{color:#C6CED6;}"
            "QPushButton{background:#1B222B; color:#DCE3EA; border:1px solid #2B3440; border-radius:5px; padding:6px 12px;}"
            "QPushButton:hover{border-color:#55DDA0;}"
            "QPushButton#accent{background:#12241C; color:#BFEBD6; border-color:#55DDA0;}"
            "QScrollArea{border:1px solid #1E2530; border-radius:6px; background:#0A0D12;}"
            "QScrollBar:vertical{background:#0A0D12; width:12px;}"
            "QScrollBar::handle:vertical{background:#2B3440; border-radius:6px; min-height:30px;}")
        V = QVBoxLayout(self)
        V.setContentsMargins(12, 12, 12, 12)
        V.setSpacing(9)
        # 顶栏:统计 + 批量操作
        top = QHBoxLayout()
        top.setSpacing(8)
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color:#AEB7C2; font-size:12px;")
        top.addWidget(self.lbl_info)
        top.addStretch(1)
        b_auto = QPushButton(t("⚑ 自动标记背景异常"))
        b_auto.setToolTip(t("按背景中值离群(云/月光/梯度会显著抬高背景)自动预标剔除,供你复核。"))
        b_auto.clicked.connect(self._auto_mark)
        b_none = QPushButton(t("全部保留"))
        b_none.clicked.connect(lambda: self._set_all(False))
        b_inv = QPushButton(t("反选"))
        b_inv.clicked.connect(self._invert)
        for b in (b_auto, b_none, b_inv):
            top.addWidget(b)
        V.addLayout(top)
        # 缩略图网格(流式布局 + 滚动区)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        host = QWidget()
        host.setStyleSheet("background:#0A0D12;")
        self.flow = _FlowLayout(host, margin=10, spacing=10)
        for i, f in enumerate(frames):
            badge = t("机内叠加") if f.get("stacked") else ""
            tile = _CullTile(i, f["name"], badge=badge)
            tile.toggled.connect(self._toggle)
            tile.zoom.connect(self._open_preview)
            tile.set_culled(self._state[i])
            self.flow.addWidget(tile)
            self._tiles.append(tile)
        self.scroll.setWidget(host)
        V.addWidget(self.scroll, 1)
        # 底栏:进度 + 取消/确定
        bot = QHBoxLayout()
        bot.setSpacing(8)
        self.lbl_prog = QLabel("")
        self.lbl_prog.setStyleSheet("color:#6B7480; font-size:11px;")
        bot.addWidget(self.lbl_prog)
        bot.addStretch(1)
        b_cancel = QPushButton(t("取消"))
        b_cancel.clicked.connect(self.reject)
        self.b_ok = QPushButton("")
        self.b_ok.setObjectName("accent")
        self.b_ok.clicked.connect(self._commit)
        bot.addWidget(b_cancel)
        bot.addWidget(self.b_ok)
        V.addLayout(bot)
        # 尺寸:铺满父窗大半
        if parent is not None:
            pg = parent.geometry()
            self.resize(int(min(1200, pg.width() * 0.92)), int(min(780, pg.height() * 0.9)))
        else:
            self.resize(1160, 760)
        self._refresh_counts()
        # 起后台缩略图线程
        paths = [f["path"] for f in frames]
        self._worker = _CullThumbWorker(paths, pat_hint, px=_CullTile.TW)
        self._worker.ready.connect(self._on_thumb)
        self._worker.progressed.connect(self._on_prog)
        self._worker.start()

    # ---- 缩略图回填 ----
    def _on_thumb(self, i, qimg, bg, err):
        if 0 <= i < len(self._tiles):
            self._tiles[i].set_image(qimg, bg)
            self._bg[i] = bg if (bg is not None and bg >= 0) else None
            if err:
                self._log and self._log(f"[筛帧] {self._frames[i]['name']} 缩略图失败:{err}")

    def _on_prog(self, done, total):
        if done >= total:
            self.lbl_prog.setText(t("缩略图已全部载入({} 帧)").format(total))
        else:
            self.lbl_prog.setText(t("正在解拜耳预览… {}/{}").format(done, total))

    # ---- 交互 ----
    def _toggle(self, i):
        self._state[i] = not self._state[i]
        self._tiles[i].set_culled(self._state[i])
        self._refresh_counts()

    def _set_all(self, on):
        for i in range(len(self._state)):
            self._state[i] = on
            self._tiles[i].set_culled(on)
        self._refresh_counts()

    def _invert(self):
        for i in range(len(self._state)):
            self._state[i] = not self._state[i]
            self._tiles[i].set_culled(self._state[i])
        self._refresh_counts()

    def _auto_mark(self):
        import numpy as _np
        vals = [(i, b) for i, b in enumerate(self._bg) if b is not None]
        if len(vals) < 5:
            QMessageBox.information(self, t("筛帧"),
                                    t("缩略图还没载入够(需要背景数据)。请等进度条走完再点。"))
            return
        arr = _np.array([b for _, b in vals], dtype=float)
        med = float(_np.median(arr))
        mad = float(_np.median(_np.abs(arr - med))) or 1e-6
        thr = med + 3.5 * 1.4826 * mad
        thr = max(thr, med * 1.4)                  # 背景整体很平时不乱标
        n = 0
        for i, b in vals:
            if b > thr:
                if not self._state[i]:
                    self._state[i] = True
                    self._tiles[i].set_culled(True)
                self._tiles[i].mark_bg_outlier()
                n += 1
        self._refresh_counts()
        self._log and self._log(
            f"[筛帧] 自动标记:背景中值 {med:.3f},阈值 {thr:.3f} → 预标 {n} 帧为异常(请复核)。")
        QMessageBox.information(self, t("筛帧"),
                                t("已按背景离群预标 {} 帧(阈值 {:.3f})。\n请逐一复核后再确定——自动标记只是线索。")
                                .format(n, thr))

    def _open_preview(self, i):
        f = self._frames[i]
        dlg = _CullPreviewDialog(f["path"], self._pat, self._state[i], self._log, self)
        dlg.exec_()
        if dlg.result_culled != self._state[i]:
            self._state[i] = dlg.result_culled
            self._tiles[i].set_culled(self._state[i])
            self._refresh_counts()

    def _refresh_counts(self):
        total = len(self._state)
        n_cull = sum(1 for s in self._state if s)
        self.lbl_info.setText(t("共 {} 帧 · 保留 {} · 剔除 {}").format(total, total - n_cull, n_cull))
        # 相对打开时的净变化
        add = sum(1 for i in range(total) if self._state[i] and not self._orig[i])
        rem = sum(1 for i in range(total) if not self._state[i] and self._orig[i])
        if add or rem:
            self.b_ok.setText(t("确定(新剔除 {} · 恢复 {})").format(add, rem))
        else:
            self.b_ok.setText(t("确定"))

    def _commit(self):
        to_cull, to_restore = [], []
        for i, f in enumerate(self._frames):
            if self._state[i] and not self._orig[i]:
                to_cull.append((f["path"], f["parent"]))
            elif not self._state[i] and self._orig[i]:
                to_restore.append(f["path"])
        if not to_cull and not to_restore:
            self.accept()
            return
        try:
            nc, nr = pipeline.apply_cull(to_cull, to_restore)
        except Exception as e:
            QMessageBox.warning(self, t("筛帧"), t("执行失败:{}").format(e))
            return
        self._log and self._log(f"[筛帧] 已剔除 {nc} 帧(挪进 _ttlot_culled,不进 WBPP)、恢复 {nr} 帧。")
        self.accept()

    def _cleanup(self):
        w = getattr(self, "worker", None)
        if w is not None:
            try:
                w.stop()
                w.wait(2500)
            except Exception:
                pass

    def reject(self):
        self._cleanup()
        super().reject()

    def accept(self):
        self._cleanup()
        super().accept()

    def closeEvent(self, e):
        self._cleanup()
        super().closeEvent(e)


class ClickFrame(QFrame):
    """可点击卡片(流程卡 / 项目卡)。QFrame 不发 clicked,自己在 mousePress 里发。"""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class BreathMark(QWidget):
    """品牌标记:圆角方块,径向绿核 + 蓝色涟漪环 + 心跳呼吸(设计签名元素)。
    颜色随主题:core=accent(绿),ring=info(蓝)。"""

    def __init__(self, d=22, parent=None):
        super().__init__(parent)
        self._d = d
        self._core = QColor("#55DDA0")
        self._ring = QColor("#69AFD6")
        self._t = 1.0
        self.setFixedSize(d + 8, d + 8)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        a = QPropertyAnimation(self, b"pulse", self)
        a.setDuration(4600)
        a.setStartValue(1.0); a.setKeyValueAt(0.5, 0.55); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.InOutSine); a.setLoopCount(-1)
        self._anim = a; a.start()

    def getPulse(self):
        return self._t

    def setPulse(self, v):
        self._t = float(v); self.update()

    pulse = pyqtProperty(float, fget=getPulse, fset=setPulse)

    def set_colors(self, core, ring):
        self._core = QColor(core); self._ring = QColor(ring); self.update()

    def paintEvent(self, _e):
        q = QPainter(self); q.setRenderHint(QPainter.Antialiasing)
        r = self.rect(); cx, cy = r.center().x(), r.center().y()
        d = self._d
        # 涟漪蓝环(呼吸放大淡出)
        ring = QColor(self._ring); ring.setAlphaF(0.42 * self._t)
        pen = QPen(ring); pen.setWidthF(1.3); q.setPen(pen); q.setBrush(Qt.NoBrush)
        gr = d / 2.0 + 2.0 + 3.0 * (1.0 - self._t)
        q.drawRoundedRect(QRectF(cx - gr, cy - gr, gr * 2, gr * 2), 5, 5)
        # 圆角方块 + 径向绿渐变
        sq = QRectF(cx - d / 2.0, cy - d / 2.0, d, d)
        grad = QRadialGradient(float(cx), float(cy - d * 0.05), float(d * 0.62))
        c0 = QColor(self._core)
        c1 = QColor(self._core).darker(140)
        grad.setColorAt(0.0, c0); grad.setColorAt(1.0, c1)
        path = QPainterPath(); path.addRoundedRect(sq, 6, 6)
        q.fillPath(path, QBrush(grad))
        # 中心暗点(镜头感)
        q.setBrush(QColor("#06140D")); q.setPen(Qt.NoPen)
        q.drawEllipse(QRectF(cx - 2.0, cy - d * 0.05 - 2.0, 4.0, 4.0))


class AppWindow(QWidget):
    # 【混合模式】流程 = 成片混合方式(相机/滤镜是正交输入);内部引擎 kind 由 _derive_kind(模式,相机,通道)派生。
    FLOWS = [("pure_rgb", "纯 RGB"), ("rgb_nb", "RGB 星点 + 窄带天体"),
             ("pure_nb", "纯窄带"), ("rgb_fuse", "全量 RGB + 窄带")]
    _col_req_sig = pyqtSignal(object)        # 调色预览请求 → 后台算手(_ColPreviewWorker.render)
    _col_stat_sig = pyqtSignal(object)       # 调色读数请求 → 读数算手(_ColStatsWorker.run)

    def __init__(self):
        super().__init__()
        _load_bundled_fonts()       # 注册打包的 IBM Plex Mono(QApplication 此时已在);QSS 随后即可命中
        self.thread = None
        self.worker = None
        # 主题持久化(2026-09-06):跟随上次选择;浅色=春野绿。原来写死 DARK,切过浅色重启就回深色。
        self.theme = LIGHT if config.get_setting("theme", "dark") == "light" else DARK
        self._param_rows = {}
        self._param_sliders = {}
        self._start_t = 0.0
        self._max_phase = -1
        self._done_ops = 0
        self._final_png = self._final_xisf = ""; self._stage_xisf = ""
        self._proj_path = ""        # 当前 .ttproj 落盘路径(空=还没选过位置,首次保存弹「另存为」)
        self._anims = []            # 持有动画对象,避免被 GC
        self._sections = []         # 折叠小节 (开关, 容器)
        self._has_preview = False   # 右侧是否已有图(决定空态路线图 / 横向阶段带)
        self._pm_raw = None
        self._end_state = "idle"    # idle / run / done / handoff / fail
        self._finals = {}           # {配色: 成片 xisf}
        self._cur_pal = None
        self._scored_pal = None     # 评委实际评过的那档
        self._last_scores = {}; self._last_scored_png = ""
        self._pal_scores = {}       # 按需评分缓存 {配色: score dict}
        self._dust_mode = False
        self._col_pick_mode = False   # 手动调色:是否正在等用户点选背景
        self._col_bg = None           # 用户点选的背景电平(None=还没点,曲线用 0.09 兜底)
        self._col_pt = None           # 取样点归一化坐标(在预览上画标记)
        self._col_base = None         # 实时预览的底图(numpy),_on_color_ask 时载入
        self._col_busy = False        # (旧)界面线程重算中;预览已挪后台,见 _col_request
        self._col_worker = None       # 预览后台算手(_ColPreviewWorker)及其线程,首次打开面板时建
        self._col_wthread = None
        self._col_inflight = False    # 后台正在算一张
        self._col_pending = None      # 算的时候又来的请求:只留最新一个
        self._col_seq = 0             # 请求序号
        self._col_base_ver = 0        # 底图版本(换底图 → 后台缓存作废)
        self._col_dragging = False    # 有滑块正被按住拖动 → 出草图
        self._col_preset_btns = []
        self._dust_circle = None    # 灰尘可编辑圆 {cx,cy,r}(label 坐标)
        self._dust_act = None       # 拖拽状态 new/resize/move
        self._pm_display = None     # 当前显示的缩放图(画圈叠加基于它)
        self._remedy_rows = []      # 动态"需你决定"行,便于清理
        self._i18n_widgets = []     # (widget, 中文源串, setter) —— 语言切换时重刷
        self._i18n_callbacks = []   # 语言切换时调用的重刷回调(格式化拼接文案等,遍历反查修不到的)
        self._nav_meta = []         # (nav按钮, ix, 名) —— 组合串「ix · 名」单独重建
        self._build()
        self._install_ia()                      # 单页布局 → 5 屏 IA(顶栏/导航/屏栈/页脚)
        self.preview.installEventFilter(self)   # 灰尘修复:捕获预览点击
        self._polish_groups()
        self._apply_theme()
        self._select_input_mode(0)
        self._select_flow(0)
        self._sync_flow_cards()                 # 流程卡选中态跟随初始 flow
        self._refresh_runner()
        # 常驻状态轮询:PI 起来/挂掉时,状态灯与『释放』按钮跟着同步(每 4s,runner_alive 只查心跳文件)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_runner)
        self._status_timer.start(4000)
        # 工程自动保存(用户 2026-09-07:常忘手动保存)。每 120s 检查一次,有改动就静默存;
        #   处理完成也会即时存一次(见 _finished)。从未存过的工程一旦出成片,自动挑路径存、不再丢进度。
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(120000)

    # ---------- 构建 ----------
    def _build(self):
        self.setWindowTitle(t("TTAstroPiLot · 深空自动后期"))
        self.setWindowIcon(icons.icon(icons.APP, 64, DARK['accent']))   # 任务栏/标题栏 App 图标(品牌绿)
        self.setMinimumSize(1024, 700)      # 抬高最小尺寸:缩小后元素仍能容纳(兼容 1366×768 小屏)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ===== 顶栏:品牌 + 主题 + runner 状态灯 =====
        header = QFrame(); header.setObjectName("headerbar"); self._header = header
        th = QHBoxLayout(header); th.setContentsMargins(20, 12, 20, 10); th.setSpacing(14)
        # 品牌标记已由窗口/标题栏图标(setWindowIcon)承担 → banner 左侧不再重复放 logo(用户 2026-08-27)
        head = QVBoxLayout(); head.setSpacing(2)
        self.banner = GradientLabel("TTAstroPiLot"); self.banner.setObjectName("banner")
        banner = self.banner
        sub = QLabel(t("深空自动后期 · 一键处理(PixInsight 自动流程 · LLM 评审)"))
        sub.setObjectName("sub")
        head.addWidget(banner); head.addWidget(sub)
        th.addLayout(head); th.addStretch(1)
        self.btn_theme = QPushButton(t("◑ 主题")); self.btn_theme.setObjectName("ghost")
        self.btn_theme.setToolTip(t("在深色 / 亮色主题之间切换"))
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.clicked.connect(self._toggle_theme)
        self.runner_pill = QFrame(); self.runner_pill.setObjectName("statuspill")
        rp = QHBoxLayout(self.runner_pill); rp.setContentsMargins(6, 0, 12, 0); rp.setSpacing(2)
        self.runner_pill.setFixedHeight(28)
        self.runner_dot = PulseDot(8)
        self.lbl_runner = QLabel("PixInsight"); self.lbl_runner.setObjectName("statuspilltext")
        self._tr(self.lbl_runner, "本工具在 PixInsight 里运行的处理脚本是否在线。开始处理时会自动启动 PixInsight。",
                 "setToolTip")
        self.runner_pill.setToolTip(self.lbl_runner.toolTip())
        rp.addWidget(self.runner_dot, 0); rp.addWidget(self.lbl_runner, 0)
        th.addWidget(self.btn_theme, 0, Qt.AlignVCenter)
        th.addWidget(self.runner_pill, 0, Qt.AlignVCenter)
        outer.addWidget(header)
        hair = QFrame(); hair.setObjectName("hairline"); hair.setFixedHeight(2)
        outer.addWidget(hair)

        # ===== 流程:提到顶部做成标签条(主路径第一步)——_install_ia() 会把它移进「配置」页顶部 =====
        ribbon = QFrame(); ribbon.setObjectName("ribbon"); self.ribbon = ribbon
        rb = QHBoxLayout(ribbon); rb.setContentsMargins(20, 0, 20, 0); rb.setSpacing(10)
        rlab = QLabel(t("流程")); rlab.setObjectName("sub")
        rb.addWidget(rlab, 0, Qt.AlignVCenter)
        flow_bar = FlowBar(hspace=2, vspace=0); flow_bar.setObjectName("rowbg")
        self.flow_group = QButtonGroup(self); self.flow_group.setExclusive(True)
        self.flow_btns = []
        for i, (kind, label) in enumerate(self.FLOWS):
            b = QPushButton(label); b.setObjectName("tab"); b.setCheckable(True)
            b.setToolTip(FLOW_TIPS.get(kind, ""))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, idx=i: self._select_flow(idx))
            self.flow_group.addButton(b, i); self.flow_btns.append(b); flow_bar.add(b)
        self.flow_ind = SlideIndicator(flow_bar, 2); self.flow_ind.hide()
        self._flow_bar = flow_bar
        rb.addWidget(flow_bar, 1, Qt.AlignVCenter)
        outer.addWidget(ribbon)

        # ===== 主体:左(填写)/ 右(预览) —— _install_ia() 会把左列换成分页 stage_stack,右列预览常驻 =====
        bodyw = QWidget(); bodyw.setObjectName("rowbg"); self._bodyw = bodyw
        body = QHBoxLayout(bodyw); body.setContentsMargins(20, 12, 20, 0); body.setSpacing(14)
        self._body = body
        outer.addWidget(bodyw, 1)

        leftw = QWidget(); leftw.setObjectName("rowbg"); self._leftw = leftw
        leftcol = QVBoxLayout(leftw); leftcol.setContentsMargins(0, 0, 0, 0); leftcol.setSpacing(10)
        body.addWidget(leftw, 5)

        # 左侧控件列放进可滚动容器:窗口变矮时出竖向滚动条,而非把输入控件压扁
        left_container = QWidget()
        left = QVBoxLayout(left_container); left.setSpacing(9); left.setContentsMargins(1, 1, 8, 4)
        self._left_layout = left   # _install_ia() 在其顶部插入流程选择行
        self.left_scroll = QScrollArea(); self.left_scroll.setObjectName("leftscroll")
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setWidget(left_container)
        # 横向滚动条按需出现:极窄时(连折行也放不下)仍能滚到被遮住的控件,而不是被静默裁掉
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setMinimumWidth(330)
        leftcol.addWidget(self.left_scroll, 1)

        # ---- ① 给素材(主路径,高亮卡) ----
        gin = QGroupBox(""); gin.setObjectName("gb_main"); self._gin = gin
        gin_v = QVBoxLayout(gin); gin_v.setContentsMargins(0, 0, 0, 0); gin_v.setSpacing(0)
        strip1, self.lbl_mode_name = self._card_strip("1", "给素材", True)
        gin_v.addWidget(strip1)
        gin_body = QWidget(); gin_body.setObjectName("rowbg"); gin_v.addWidget(gin_body)
        vi = QVBoxLayout(gin_body); vi.setContentsMargins(14, 12, 14, 14); vi.setSpacing(8)
        # 【相机/设备(用户 2026-09-04:相机是第一维输入,提到「给素材」顶部、所有模式可见)】决定处理分流
        #   (OSC→RGB / 黑白→LRGB per-filter)+ 原始叠加的校准策略。从原始叠加面板上移到这。
        devrow = FlowBar(hspace=6, vspace=6); devrow.setObjectName("rowbg")
        _dlab = QLabel(); _dlab.setObjectName("plabel"); _dlab.setMinimumWidth(48); self._tr(_dlab, "相机")
        devrow.add(_dlab)
        self.dev_btns = {}
        self._stack_device = "osc"
        for _k, _label, _pol, _hint in STACK_DEVICES:
            _b = QPushButton(_label); _b.setObjectName("segdev"); _b.setCheckable(True)
            _b.setChecked(_k == "osc"); _b.setCursor(Qt.PointingHandCursor)
            _b.clicked.connect(lambda _c=False, key=_k: self._select_stack_device(key))
            self.dev_btns[_k] = _b; devrow.add(_b)
        vi.addWidget(devrow)
        self.lbl_stack_dev_hint = QLabel(STACK_DEV_MAP["osc"][2])
        self.lbl_stack_dev_hint.setObjectName("sub"); self.lbl_stack_dev_hint.setWordWrap(True)
        vi.addWidget(self.lbl_stack_dev_hint)
        mode_bar = FlowBar(hspace=6, vspace=6, stretch=True); mode_bar.setObjectName("rowbg")
        self.in_mode_group = QButtonGroup(self); self.in_mode_group.setExclusive(True)
        self.in_mode_btns = []
        for i, label in enumerate(["已叠加母版", "对齐子帧目录", "原始素材叠加"]):
            b = QPushButton(); self._tr(b, label); b.setObjectName("seg"); b.setCheckable(True)
            b.setToolTip(MODE_TIPS[i]); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, idx=i: self._select_input_mode(idx))
            self.in_mode_group.addButton(b, i); self.in_mode_btns.append(b); mode_bar.add(b)
        self.mode_ind = SlideIndicator(mode_bar, 6); self.mode_ind.hide()   # 半径与 #seg 按钮 6px 一致
        self.mode_ind.lower()
        vi.addWidget(mode_bar)
        # 多通道流程下第三种输入被 setEnabled(False):用一条琥珀提示说明"为什么不可选"
        self.lbl_mode_note = QLabel(""); self.lbl_mode_note.setObjectName("warnnote")
        self.lbl_mode_note.setWordWrap(True); self.lbl_mode_note.setVisible(False)
        vi.addWidget(self.lbl_mode_note)
        self._input_mode = 0
        # 页0:单路径(模式 0 母版文件 / 模式 1 registered 目录 共用)。用显隐切换而非
        # QStackedWidget → 隐藏页在布局里不占高度,组框高度自适应当前页(不再按最高页预留)。
        # 页0:已叠加母版(**多行 + 滤镜标签**,与对齐子帧/原始素材一致:IR-UVcut→RGB 底,
        #   Hα/OIII·SII/OIII·Hβ/SII 各窄带母版→给 RGB 叠发射信号;不再单列窄带输入框)。用户 2026-09-07。
        self.pg_master = QWidget()
        lm = QVBoxLayout(self.pg_master); lm.setContentsMargins(0, 0, 0, 0); lm.setSpacing(6)
        self.master_rows = []
        self.master_box = QVBoxLayout(); self.master_box.setSpacing(6); lm.addLayout(self.master_box)
        self.btn_add_master = QPushButton(t("+ 添加已叠加母版")); self.btn_add_master.setCursor(Qt.PointingHandCursor)
        self.btn_add_master.clicked.connect(lambda: self._add_master_row())
        lm.addWidget(self.btn_add_master, alignment=Qt.AlignLeft)
        self.lbl_input_hint = QLabel(t("每行 = 一个已叠加母版 + 滤镜标签。IR-UVcut→RGB 底;"
                                       "Hα/OIII·SII/OIII·Hβ/SII 窄带母版→给 RGB 叠发射信号(只留一个宽带即纯 RGB)。"))
        self.lbl_input_hint.setObjectName("sub"); self.lbl_input_hint.setWordWrap(True)
        lm.addWidget(self.lbl_input_hint)
        vi.addWidget(self.pg_master)
        self._add_master_row()             # 建首行(其输入框兼任 self.ed_input:宽带底/自动识别/导出命名沿用)
        # 页1b:对齐子帧目录(**多目录 + 滤镜标签**,与原始叠加一致:窄带=某滤镜的对齐子帧,不单独摘出来;
        #   各滤镜组直接整合出各自 master)。用户 2026-09-04。
        self.pg_reg = QWidget()
        lr = QVBoxLayout(self.pg_reg); lr.setContentsMargins(0, 0, 0, 0); lr.setSpacing(6)
        self.reg_rows = []
        self.reg_box = QVBoxLayout(); self.reg_box.setSpacing(6); lr.addLayout(self.reg_box)
        self.btn_add_reg = QPushButton(t("+ 添加对齐子帧目录")); self.btn_add_reg.setCursor(Qt.PointingHandCursor)
        self.btn_add_reg.clicked.connect(lambda: self._add_reg_row())
        lr.addWidget(self.btn_add_reg, alignment=Qt.AlignLeft)
        _rhint = QLabel(t("每个目录 = 某滤镜的对齐子帧;同滤镜整合到一起。IR-UVcut→RGB 底,双窄带→窄带信号融合。"))
        _rhint.setObjectName("sub"); _rhint.setWordWrap(True); lr.addWidget(_rhint)
        self.pg_reg.setVisible(False); vi.addWidget(self.pg_reg)
        self._add_reg_row()
        # 页1:原始素材叠加配置面板
        self.pg_raw = self._build_rawstack_panel(); self.pg_raw.setVisible(False)
        vi.addWidget(self.pg_raw)
        # 从子帧整合时可选:叠加前智能筛帧(去卫星/飞机线 + 去云/低透明度帧)。母版模式(0)无子帧,隐藏。
        self.detrail_row = QWidget(); self.detrail_row.setObjectName("paramrow")
        dh = QHBoxLayout(self.detrail_row); dh.setContentsMargins(11, 6, 10, 6); dh.setSpacing(8)
        dcol = QVBoxLayout(); dcol.setSpacing(1)
        self.chk_detrail = QCheckBox(t("叠加前智能筛帧(去卫星线 + 去云帧)"))
        self.chk_detrail.setChecked(False)   # 默认关(用户 2026-09-03):开启会显著增加耗时(残差检测逐帧跑),
                                             #   而卫星线大多数情况整合的 rejection 就能排掉,不必逐帧筛。需要时再勾。
        self.chk_detrail.setToolTip(t("整合前对对齐子帧做两道质量筛选:\n"
                                    "① 残差霍夫检测卫星/飞机线,整帧剔除;\n"
                                    "② 逐帧背景鲁棒离群检测有云/低透明度帧(背景异常偏高),整帧剔除。\n"
                                    "各自超护栏比例时为保信噪自动跳过。仅在从子帧整合(模式②/③)时生效。\n"
                                    "【默认关】显著增加耗时;卫星线通常整合 rejection 就能排掉,有明显残留或云帧时再勾。"))
        dcap = QLabel(t("残差去线 + 逐帧背景去云;【默认关】耗时大、卫星线整合 rejection 通常能排掉,需要时再勾"))
        dcap.setObjectName("sub"); dcap.setWordWrap(True)
        dcol.addWidget(self.chk_detrail); dcol.addWidget(dcap)
        dh.addLayout(dcol, 1)
        vi.addWidget(self.detrail_row)
        # 窄带融合预设 —— 宽带 RGB + 双窄带融合的**强度**选择。窄带母版本身现在走上方「素材」里的
        #   **滤镜标签**(母版行标 Hα/OIII 等 / 对齐子帧目录 / 原始亮场滤镜),不再单列输入框(用户 2026-09-07)。
        #   仅 RGB 融合流程显示(_sync_narrowband_vis 控制),三种输入模式都适用。
        self.narrowband_row = QWidget(); self.narrowband_row.setObjectName("paramrow")
        _nbv = QVBoxLayout(self.narrowband_row); _nbv.setContentsMargins(11, 7, 10, 7); _nbv.setSpacing(4)
        _nbtop = QHBoxLayout(); _nbtop.setSpacing(8)
        _lbl_ha = QLabel(); _lbl_ha.setObjectName("plabel"); self._tr(_lbl_ha, "窄带融合"); _lbl_ha.setMinimumWidth(56)
        self.cb_hapreset = QComboBox()
        self.cb_hapreset.addItems([t("整片星云增强(默认)"), t("整片星云增强·更浓"), t("只增强星系的窄带信号"),
                                   t("保留主体明暗(小而亮的星云)")])
        self.cb_hapreset.setMinimumWidth(140); self.cb_hapreset.setMaximumWidth(220)
        # 【文案说人话(用户 2026-09-11)】旧文案用具体天体名(气泡)+内部黑话(小红花/离散HII/更跳),
        #   用户无法据此判断该选哪个 → 改成"什么时候用 + 会得到什么",不出现天体名和术语缩写。
        self.cb_hapreset.setToolTip(t(
            "窄带信号怎么叠到宽带真彩上。\n"
            "· 整片星云增强:目标是一整片发射星云时用。把窄带的红和青蓝整体叠上去,让星云颜色更鲜明。默认。\n"
            "· 更浓:同上,叠得更强、颜色更浓,可能偏艳。\n"
            "· 只增强星系的窄带信号:目标是星系时用。只挑出星系里零散的恒星形成区叠加,星系本体不动。\n"
            "· 保留主体明暗:目标小而亮时用(如行星状星云)。主体的明暗层次保持宽带原样,只按窄带里红与青蓝的比例上色;"
            "主体外面宽带拍不到的暗弱云气用窄带提亮。识别为行星状星云时会自动使用。"))
        _nbtop.addWidget(_lbl_ha, 0); _nbtop.addWidget(self.cb_hapreset, 0); _nbtop.addStretch(1)
        _nbv.addLayout(_nbtop)
        _nbcap = QLabel(t("窄带母版在上方「素材」里加一行、滤镜标 Hα/OIII 等即可融合;此处只调融合强度。无窄带行 = 纯 RGB"))
        _nbcap.setObjectName("sub"); _nbcap.setWordWrap(True)
        _nbv.addWidget(_nbcap)
        vi.addWidget(self.narrowband_row)
        self.narrowband_row.setVisible(False)     # 由 _select_flow 按 RGB 流程显示
        # 成片导出目录(常显·所有模式,用户 2026-09-03):填一次记住;点「导出成片」直接存这、文件名用项目名,
        #   免每次弹窗选。留空=导出时弹窗选(选完自动回填这里)。放输入区、处理前就能设。
        self.exportdir_row = QWidget(); self.exportdir_row.setObjectName("paramrow")
        _eh = QHBoxLayout(self.exportdir_row); _eh.setContentsMargins(11, 6, 10, 6); _eh.setSpacing(8)
        _lexp = QLabel(); _lexp.setObjectName("plabel"); self._tr(_lexp, "导出目录"); _lexp.setMinimumWidth(56)
        self.ed_exportdir = QLineEdit(config.get_setting("export_dir", ""))
        self.ed_exportdir.setPlaceholderText(t("(留空=导出时弹窗选)成片导出到这、文件名用项目名"))
        self.ed_exportdir.setToolTip(t("成片导出到这个目录,文件名自动用项目名(如 M54_260712_D3);点『导出成片』直接存、不弹窗。\n"
                                     "留空则导出时弹窗选文件夹(选完自动回填这里、下次免选)。"))
        self.ed_exportdir.editingFinished.connect(self._save_export_dir)
        _bexp = QPushButton(t("浏览…")); _bexp.setObjectName("seg"); _bexp.setCursor(Qt.PointingHandCursor)
        _bexp.clicked.connect(lambda: (self._pick_dir(self.ed_exportdir), self._save_export_dir()))
        _eh.addWidget(_lexp); _eh.addWidget(self.ed_exportdir, 1); _eh.addWidget(_bexp)
        vi.addWidget(self.exportdir_row)
        left.addWidget(gin)
        self.chk_integrate = QCheckBox(); self.chk_integrate.setVisible(False)  # 兼容:内部用

        # ---- ② 调参数(收敛卡:主区常驻 + 高级折叠) ----
        gp = QGroupBox(""); gp.setObjectName("gb_quiet"); self._gp = gp
        gp_v = QVBoxLayout(gp); gp_v.setContentsMargins(0, 0, 0, 0); gp_v.setSpacing(0)
        strip2, self.lbl_param_count = self._card_strip("2", "调参数", False)
        gp_v.addWidget(strip2)
        gp_body = QWidget(); gp_body.setObjectName("rowbg"); gp_v.addWidget(gp_body)
        vp = QVBoxLayout(gp_body); vp.setContentsMargins(14, 12, 14, 14); vp.setSpacing(6)

        # 处理到哪一步(最常动的一项 → 强调行,放最前)
        _srow = QWidget(); _srow.setObjectName("primrow")
        _sh2 = QHBoxLayout(_srow); _sh2.setContentsMargins(11, 8, 10, 8); _sh2.setSpacing(9)
        _slab = QLabel(); _slab.setObjectName("primlabel"); self._tr(_slab, "处理到")
        _shint = QLabel(); _shint.setObjectName("sub"); self._tr(_shint, "交棒点")
        self.cb_stop = QComboBox()
        # 各流程的交棒点(第一项固定=跑完全流程)
        self.STOPS_BY_FLOW = {
            "sho": [("final", "跑完全流程(出成片)"), ("integrate", "① 只整合各通道"),
                    ("crop_gc", "② +统一裁黑边+梯度校正"), ("bxt", "③ +BXT(常用交棒点)"),
                    ("denoise", "④ +线性降噪"), ("stretch", "⑤ +拉伸对齐"),
                    ("combine", "⑥ +合成 SHO"), ("starless", "⑦ +去星(星云/星点)"),
                    ("color", "⑧ +调色(合星前)")],
            "rgb": [("final", "跑完全流程(出成片)"), ("crop", "① 只裁黑边"),
                    ("gradient", "② +梯度校正"), ("bxt", "③ +BXT"),
                    ("colorcal", "④ +色彩校准(SPCC/BNCC)"), ("denoise", "⑤ +线性降噪"),
                    ("stretch", "⑥ +拉伸"), ("starless", "⑦ +去星(星云/星点)"),
                    ("color", "⑧ +调色(合星前)")],
            "hoo": [("final", "跑完全流程(出成片)"), ("crop", "① 只裁黑边"),
                    ("gradient", "② +梯度校正"), ("bxt", "③ +BXT"),
                    ("combine", "④ +HOO 合成"), ("starless", "⑤ +去星(星云/星点)")],
            "lrgb": [("final", "跑完全流程(出成片)"), ("integrate", "① 只整合各通道"),
                     ("crop_gc", "② +统一裁黑边+背景匹配"), ("combine", "③ +RGB合成/superL"),
                     ("colorcal", "④ +色彩校准"), ("stretch", "⑤ +拉伸"),
                     ("lrgb", "⑥ +保色亮度替换")],
        }
        self.STOPS = self.STOPS_BY_FLOW["rgb"]
        self.cb_stop.addItems([t for _, t in self.STOPS])
        self.cb_stop.setMinimumWidth(160); self.cb_stop.setMaximumWidth(250)
        self.cb_stop.setToolTip(t("只跑到选定步骤,产物导出到输出目录,后续你在 PixInsight 手工接管。\n"
                                "例:选③ 就得到六通道 整合+裁边+梯度校正+BXT 的线性 master。"))
        _sh2.addWidget(_slab, 0); _sh2.addWidget(_shint, 0); _sh2.addStretch(1)
        _sh2.addWidget(self.cb_stop, 0)
        vp.addWidget(_srow); self._param_rows["stop"] = _srow

        # 处理方式:全自动 vs 分步询问方向(用户 2026-09-15)
        _mrow = QWidget(); _mrow.setObjectName("primrow")
        _mh = QHBoxLayout(_mrow); _mh.setContentsMargins(11, 8, 10, 8); _mh.setSpacing(9)
        _mlab = QLabel(); _mlab.setObjectName("primlabel"); self._tr(_mlab, "处理方式")
        self.cb_stepwise = QComboBox()
        self.cb_stepwise.addItems([t("全自动跑完"), t("分步问我方向")])
        self.cb_stepwise.setMinimumWidth(160); self.cb_stepwise.setMaximumWidth(250)
        self.cb_stepwise.setToolTip(
            t("全自动跑完:程序在每个岔口按自己的判断选,中途不打断。") + chr(10)
            + t("分步问我方向:跑到几个真正有分歧的地方(整体明暗 / 暗弱结构 / 色彩方向 /") + chr(10)
            + t("星点 / 背景电平)停下来问你,可以点选项,也可以直接用自己的话说。") + chr(10)
            + t("两种模式出的图在没做选择时完全一样。"))
        _mh.addWidget(_mlab, 0); _mh.addStretch(1); _mh.addWidget(self.cb_stepwise, 0)
        vp.addWidget(_mrow); self._param_rows["stepwise"] = _mrow

        # 手动调色(用户 2026-09-21):与「分步问我方向」正交 —— 那个是问方向,这个是**自己动手拉曲线**,
        #   所以单独一行,不塞进同一个下拉。
        _crow = QWidget(); _crow.setObjectName("rowbg")
        _ch2 = QHBoxLayout(_crow); _ch2.setContentsMargins(11, 8, 10, 8); _ch2.setSpacing(9)
        _clab = QLabel(); _clab.setObjectName("primlabel"); self._tr(_clab, "颜色")
        self.cb_mancolor = QComboBox()
        self.cb_mancolor.addItems([t("程序自动调"), t("去星后我自己调")])
        self.cb_mancolor.setMinimumWidth(160); self.cb_mancolor.setMaximumWidth(250)
        self.cb_mancolor.setToolTip(
            t("程序自动调:按你以往成片的色彩走,中途不打断。") + chr(10)
            + t("去星后我自己调:拉伸和去星做完后停下来,在预览上点一下标定背景,") + chr(10)
            + t("再用滑块拉 R/G/B 三条曲线和饱和度,看着预览实时变。也可以直接套预设。"))
        _ch2.addWidget(_clab, 0); _ch2.addStretch(1); _ch2.addWidget(self.cb_mancolor, 0)
        vp.addWidget(_crow); self._param_rows["mancolor"] = _crow

        # 常驻数值(按流程显隐)
        self.sp_ghs = self._param(vp, "ghs", "GHS 拉伸力度 D", QDoubleSpinBox,
                                  0, 2.5, 0.1, 0.5, slider=True)
        self.sp_ghs.setToolTip(t("GHS 拉伸强度 D(0~2.5)。偏暗加大、过曝减小;开启评委自检时会自动微调。"))
        self.sp_sat = self._param(vp, "sat", "饱和度提升", QDoubleSpinBox,
                                  0, 1.0, 0.05, 0.15, slider=True)
        self.sp_sat.setToolTip(t("星云饱和度提升量(0~1.0)。SHO 流程内部会再叠加 0.35。"))
        for _k in ("ghs", "sat"):                 # 滑块与整行共用数值框的说明
            _tip = {"ghs": self.sp_ghs, "sat": self.sp_sat}[_k].toolTip()
            self._param_rows[_k].setToolTip(_tip)
            self._param_sliders[_k].setToolTip(_tip)

        # 窄带调色(显式选合成方式,覆盖相机默认;用户 2026-09-04:OSC 也能 SHO、黑白也能 HOO)。
        #   仅窄带模式(RGB星点+窄带天体 / 纯窄带)显示。自动=按相机(OSC 双窄带→HOO、黑白多通道→SHO)。
        _nbprow = QWidget(); _nbprow.setObjectName("paramrow")
        _nbph = QHBoxLayout(_nbprow); _nbph.setContentsMargins(11, 5, 10, 5); _nbph.setSpacing(9)
        _nbplab = QLabel(); _nbplab.setObjectName("plabel"); self._tr(_nbplab, "窄带调色")
        self.cb_nbpalette = QComboBox()
        self.cb_nbpalette.addItems([t("自动 (按相机/通道)"), t("SHO 哈勃 (SII→R Ha→G OIII→B)"),
                                    t("HOO 双色 (Ha→R OIII→G/B)")])
        self.cb_nbpalette.setMinimumWidth(150); self.cb_nbpalette.setMaximumWidth(230)
        self.cb_nbpalette.setToolTip(t("窄带合成方式(覆盖相机默认):SHO=三通道哈勃(需 SII+Ha+OIII);"
                                     "HOO=双色(Ha 红 + OIII 青);自动=OSC 双窄带→HOO、黑白多通道→SHO。"
                                     "具体色相档在下面『SHO 配色』里再选(走 SHO 时)。"))
        self.cb_nbpalette.currentIndexChanged.connect(lambda _i: (self._apply_kind_vis(), self._sync_param_sections()))
        _nbph.addWidget(_nbplab, 1); _nbph.addWidget(self.cb_nbpalette, 0)
        vp.addWidget(_nbprow); self._param_rows["nbpalette"] = _nbprow

        # SHO 配色预设(仅 SHO 流程显示)
        _prow = QWidget(); _prow.setObjectName("paramrow")
        _ph = QHBoxLayout(_prow); _ph.setContentsMargins(11, 5, 10, 5); _ph.setSpacing(9)
        _plab = QLabel(t("SHO 配色")); _plab.setObjectName("plabel")
        self.cb_palette = QComboBox()
        self.cb_palette.addItems([t("全部四种 (推荐)"), t("Ha红+SII青 (hss)"), t("自然色 (natural)"),
                                  t("洋红加蓝 (natural_blue)"), t("经典哈勃 (sho)")])
        self.cb_palette.setMinimumWidth(130); self.cb_palette.setMaximumWidth(190)
        self.cb_palette.setToolTip(t("配色是主观档 → 默认四种都生成供你挑:\n"
                                   "hss=Ha 红 + SII 青(层次最好);natural=Ha红/OIII蓝/SII橙(最真);\n"
                                   "natural_blue=洋红加蓝;sho=经典哈勃(自动去绿成金青调 + 黄区加红)"))
        _ph.addWidget(_plab, 1); _ph.addWidget(self.cb_palette, 0)
        vp.addWidget(_prow); self._param_rows["palette"] = _prow

        # 无 PI · Siril 引擎(仅 SHO):勾选后走 sho_engine(零 PixInsight),配 warm/goldblue 预设
        _zrow = QWidget(); _zrow.setObjectName("paramrow")
        _zh = QHBoxLayout(_zrow); _zh.setContentsMargins(11, 5, 10, 5); _zh.setSpacing(9)
        self.chk_zeropi = QCheckBox(t("无 PI · Siril 引擎"))
        self.chk_zeropi.setToolTip(t("勾选:SHO 全程零 PixInsight(Siril 整合 + StarNet2 去星 + GraXpert/DeepSNR AI 降噪\n"
                                   "+ GHS 揭示 + 比例控制器调色 + RGB 彩色星点)。输入请选 registered 目录(含各滤镜子目录)。"))
        self.cb_zpreset = QComboBox()
        self.cb_zpreset.addItems([t("金蓝调(青蓝更突出)"), t("暖橙调(红色更突出)")])
        self.cb_zpreset.setMinimumWidth(150); self.cb_zpreset.setMaximumWidth(230)
        self.cb_zpreset.setToolTip(t("无 PI 引擎调色预设(比例控制器旋钮组):\n"
                                   "goldblue=金橙 + 蓝 OIII 核心;warm=暖 salmon + 蓝(Ha 极强的目标)"))
        _zh.addWidget(self.chk_zeropi, 0); _zh.addWidget(self.cb_zpreset, 1)
        vp.addWidget(_zrow); self._param_rows["zeropi"] = _zrow

        # 无 PI · Siril 引擎(仅 RGB):OSC 单张 master/子帧 → rgb_engine(零 PixInsight),真 SPCC 校色 + GHS 压核
        _zrrow = QWidget(); _zrrow.setObjectName("paramrow")
        _zrh = QHBoxLayout(_zrrow); _zrh.setContentsMargins(11, 5, 10, 5); _zrh.setSpacing(9)
        self.chk_zeropi_rgb = QCheckBox(t("无 PI · Siril 引擎"))
        self.chk_zeropi_rgb.setToolTip(t("勾选:纯 RGB 全程零 PixInsight(Siril 真 SPCC 光度校色 + GHS 压亮核 +\n"
                                       "带主体蒙版 DeepSNR 降噪)。输入选 OSC 单张 master 或子帧目录。\n"
                                       "真 SPCC 需装 Siril 本地 Gaia 星表(见依赖体检);未装则星场白平衡兜底。"))
        self.cb_rgbpreset = QComboBox()
        self.cb_rgbpreset.addItems([t("自然真彩(默认)"), t("浓郁(颜色更饱满)"), t("平淡(最干净,不压亮核)")])
        self.cb_rgbpreset.setMinimumWidth(150); self.cb_rgbpreset.setMaximumWidth(230)
        self.cb_rgbpreset.setToolTip(t("无 PI RGB 引擎预设:\n"
                                     "natural=SPCC 权威色 + 温和 GHS 压核 + 温和饱和(多数目标);\n"
                                     "vivid=饱和更足;flat=关 HDR 纯 autostretch(亮核稍爆但最干净,暗弱目标用)"))
        _zrh.addWidget(self.chk_zeropi_rgb, 0); _zrh.addWidget(self.cb_rgbpreset, 1)
        vp.addWidget(_zrrow); self._param_rows["zeropi_rgb"] = _zrrow

        # 窄带素材(Ha/OIII)入口已移到「给素材」区(配置屏),更贴近"这是素材"的心智 —— 见 _gin 里的 narrowband_row。

        # 无 PI RGB 高级旋钮(M8 调好的两档暴露给用户):背景梯度提取档 + 星云揭示档。均"跟随预设"= 引擎默认。
        _zradvrow = QWidget(); _zradvrow.setObjectName("paramrow")
        _zra = QHBoxLayout(_zradvrow); _zra.setContentsMargins(11, 5, 10, 5); _zra.setSpacing(9)
        _lbl_bg = QLabel(); _lbl_bg.setObjectName("dim"); self._tr(_lbl_bg, "背景梯度")
        self.cb_bgextract = QComboBox()
        self.cb_bgextract.addItems([t("跟随预设"), t("平背景 d1"), t("多项式 d4"), t("径向基 rbf"), t("两遍 4+rbf (梯度重)")])
        self.cb_bgextract.setMinimumWidth(120); self.cb_bgextract.setMaximumWidth(185)
        self.cb_bgextract.setToolTip(t("背景梯度提取(无 PI RGB,线性阶段 subsky):\n"
                                     "平背景 d1=一阶(轻倾斜);d4=四阶多项式(四角梯度);rbf=径向基(不对称/复杂);\n"
                                     "4+rbf=两遍(d4 压主梯度 + rbf 清残留,低空/光污染重梯度,M8 验证)。\n"
                                     "朝银心/银河方向的残留亮度是真实天光,别过度压平。跟随预设=引擎默认(d1)。"))
        _lbl_rv = QLabel(); _lbl_rv.setObjectName("dim"); self._tr(_lbl_rv, "星云揭示")
        self.cb_rgbreveal = QComboBox()
        self.cb_rgbreveal.addItems([t("跟随预设"), t("关 0"), t("适度 0.5"), t("强 0.9"),
                                    t("发射·中 (红丝)"), t("发射·强 (红丝)")])
        self.cb_rgbreveal.setMinimumWidth(120); self.cb_rgbreveal.setMaximumWidth(175)
        self.cb_rgbreveal.setToolTip(t("星云区揭示强度(无 PI RGB):护亮核+护背景,只提暗弱/中间调星云。\n"
                                     "适度 0.5(M8 验证);强 0.9(暗弱外围淡云);关=不揭示;跟随预设=预设默认。\n"
                                     "『发射·中/强』:额外用**红色发射蒙版**专提faint红丝(马头 IC434 脊这类\n"
                                     "亮度蒙版抓不到的暗红发射;护星防环状伪影)。faint 红发射目标+足够积分时用。"))
        _lbl_gl = QLabel(t("残留辉光")); _lbl_gl.setObjectName("dim")
        self.cb_glow = QComboBox()
        self.cb_glow.addItems([t("自动"), t("强制清除"), t("关")])
        self.cb_glow.setMinimumWidth(90); self.cb_glow.setMaximumWidth(130)
        self.cb_glow.setToolTip(t("残留辉光清除(成片后 ABE 式,补线性去梯度漏掉的局部残留辉光+色偏,如角落 amp glow/光污染的品红角)。\n"
                                "自动=检测到大尺度背景落差/色偏才清(图已均匀则不动,IC434 验证);强制清除=总是清;\n"
                                "关=不清。护星护云(最暗分位采样)。朝银心/银河的真实弥漫别强清 → 那种情形选『关』。"))
        # 三对 label+下拉用 FlowBar **成对换行**:窄栏时自动折行,避免 QHBoxLayout 三连超宽(~600)
        # 撑大整列内容宽 → 横向滚动条把所有行右侧裁掉(用户 2026-09-04 反馈)。每对独立小容器,整体不散。
        _zra_flow = FlowBar(hspace=18, vspace=7); _zra_flow.setObjectName("rowbg")
        for _la, _cb in ((_lbl_bg, self.cb_bgextract), (_lbl_rv, self.cb_rgbreveal), (_lbl_gl, self.cb_glow)):
            _pc = QWidget(); _phl = QHBoxLayout(_pc); _phl.setContentsMargins(0, 0, 0, 0); _phl.setSpacing(7)
            _phl.addWidget(_la, 0); _phl.addWidget(_cb, 0)
            _zra_flow.add(_pc)
        _zra.addWidget(_zra_flow, 1)
        vp.addWidget(_zradvrow); self._param_rows["zeropi_rgb_adv"] = _zradvrow

        # 无 PI · Siril 引擎(仅 HOO):OSC 双窄带 master/子帧 → hoo_engine(零 PixInsight),线性去梯度+提取Ha/OIII+中性灰
        _zhrow = QWidget(); _zhrow.setObjectName("paramrow")
        _zhh = QHBoxLayout(_zhrow); _zhh.setContentsMargins(11, 5, 10, 5); _zhh.setSpacing(9)
        self.chk_zeropi_hoo = QCheckBox(t("无 PI · Siril 引擎"))
        self.chk_zeropi_hoo.setToolTip(t("勾选:HOO 双窄带全程零 PixInsight(Siril 提取 Ha/OIII + 线性 GraXpert 去梯度 +\n"
                                       "StarNet2 去星 + 分通道揭示 + DeepSNR + 背景中性灰)。输入选 OSC 双窄带 master 或子帧目录。"))
        self.cb_hoopreset = QComboBox()
        self.cb_hoopreset.addItems([t("偏青蓝(OIII 更突出)"), t("青红均衡(经典)")])
        self.cb_hoopreset.setMinimumWidth(150); self.cb_hoopreset.setMaximumWidth(230)
        self.cb_hoopreset.setToolTip(t("无 PI HOO 引擎预设:\n"
                                     "oiii=OIII 主导目标(Ha弱→揭示狠、提蓝出青泡);classic=均衡青红双色"))
        _zhh.addWidget(self.chk_zeropi_hoo, 0); _zhh.addWidget(self.cb_hoopreset, 1)
        vp.addWidget(_zhrow); self._param_rows["zeropi_hoo"] = _zhrow

        # 暗尘层次揭示(仅 SHO):自动=评委判画面有无显著暗星云再定强度
        _drow = QWidget(); _drow.setObjectName("paramrow")
        _dh = QHBoxLayout(_drow); _dh.setContentsMargins(11, 5, 10, 5); _dh.setSpacing(9)
        _dlab = QLabel(t("暗尘层次揭示")); _dlab.setObjectName("plabel")
        self.cb_dust = QComboBox(); self.cb_dust.addItems([t("自动检测"), t("强制开启"), t("关闭(推荐:保留暗部氛围)")])
        self.cb_dust.setCurrentIndex(2)   # 默认关闭:外围留暗、避免主体/背景割裂断层(用户 NGC7380 定稿)
        self.cb_dust.setMinimumWidth(130); self.cb_dust.setMaximumWidth(180)
        self.cb_dust.setToolTip(t("暗星云(象鼻/尘柱/暗带)内部层次常被压成死黑 → 提亮中间调揭示。\n"
                                "默认关闭(暗 moody 克制调,外围不刻意提亮);自动检测=让评委按显著度定强度\n"
                                "(每跑可能变,曾致淡区断层);强制开启=显式要揭示时用。"))
        _dh.addWidget(_dlab, 1); _dh.addWidget(self.cb_dust, 0)
        vp.addWidget(_drow); self._param_rows["dust"] = _drow

        # 调色方式(仅 SHO):自适应(默认,自然暖)vs Henry 忠实曲线(鲜艳品红,均衡目标可选)
        _grow = QWidget(); _grow.setObjectName("paramrow")
        _gh = QHBoxLayout(_grow); _gh.setContentsMargins(11, 5, 10, 5); _gh.setSpacing(9)
        _glab = QLabel(t("调色方式")); _glab.setObjectName("plabel")
        self.cb_grade = QComboBox(); self.cb_grade.addItems([t("自适应 (默认)"), t("Henry 忠实曲线")])
        self.cb_grade.setMinimumWidth(130); self.cb_grade.setMaximumWidth(180)
        self.cb_grade.setToolTip(t("自适应=去绿 + 黄区加红 + 提饱和,偏自然暖调(默认,推荐)。\n"
                                 "Henry 忠实曲线=按播主 .xpsm 转录的 8 通道曲线,鲜艳粉紫;\n"
                                 "适合 OIII 充足的均衡目标,Ha 主导目标会压成单色红,慎用。"))
        _gh.addWidget(_glab, 1); _gh.addWidget(self.cb_grade, 0)
        vp.addWidget(_grow); self._param_rows["grade"] = _grow

        # 暗结构强化 DSE(仅 SHO):加深暗尘/暗带、提升立体感(2026-08 定稿默认开)
        _erow = QWidget(); _erow.setObjectName("paramrow")
        _eh = QHBoxLayout(_erow); _eh.setContentsMargins(11, 5, 10, 5); _eh.setSpacing(9)
        _elab = QLabel(t("暗结构强化 DSE")); _elab.setObjectName("plabel")
        self.cb_dse = QComboBox(); self.cb_dse.addItems([t("自动 (推荐)"), t("更强"), t("更轻"), t("关闭")])
        self.cb_dse.setMinimumWidth(130); self.cb_dse.setMaximumWidth(180)
        self.cb_dse.setToolTip(t("DarkStructureEnhance 原生复刻:蒙版内压暗,加深暗尘/暗带、提升立体感。\n"
                               "自动=有暗结构时施加 amount0.35(默认);更强=0.5;更轻=0.2;关闭=不做。\n"
                               "(也可对任意已完成成片一键补做,见导出区旁的按钮。)"))
        _eh.addWidget(_elab, 1); _eh.addWidget(self.cb_dse, 0)
        vp.addWidget(_erow); self._param_rows["dse"] = _erow

        # ---- 高级参数(默认折叠;折叠只作用在外层容器,不接管每行的 visible) ----
        self.btn_adv, adv_body, adv_v = self._make_section("高级参数", "装好一次即可,共 6 项")
        vp.addWidget(self.btn_adv); vp.addWidget(adv_body)
        self.chk_release = self._param(adv_v, "release", "完成后自动释放 PixInsight(交棒时必开)", QCheckBox)
        self.chk_release.setChecked(True)
        self.chk_release.setToolTip(t("处理结束后自动停 runner/看门狗并结束 PI,把 PixInsight 交还给你。\n"
                                    "选了中间交棒点时尤其需要——否则你无法在 PI 里手工接着做。"))
        self.chk_stars = self._param(adv_v, "stars", "合回星点(取消勾选=仅输出去星 starless)", QCheckBox)
        self.chk_stars.setChecked(True)  # 默认合回星点出带星成品
        self.chk_stretch_judge = self._param(adv_v, "sjudge", "拉伸力度评委自检(GHS 偏暗自动加大 D)", QCheckBox)
        self.chk_stretch_judge.setChecked(True)
        self.chk_stretch_judge.setToolTip(t("GHS 拉伸后让 LLM 评委对照判断力度是否合适;\n"
                                          "报 too_dark/too_strong 且偏离当前值就按建议 D 重拉一次(仅一次)。需已配置 LLM。"))
        self.chk_reveal = self._param(adv_v, "reveal", "暗弱星云揭示(护亮核+护背景,提外围淡云)", QCheckBox)
        self.chk_reveal.setChecked(True)
        self.chk_reveal.setToolTip(t("maskstretch(lum 蒙版+bgProtect):额外拉伸只作用在暗弱/中间调,\n"
                                   "把外围淡 Ha、弥漫云气抬起,亮核/暗湾/背景不动。低面亮度弥散星云尤其需要。"))
        self.chk_lhe = self._param(adv_v, "lhe", "局部对比 LHE(暗尘细丝更立体)", QCheckBox)
        self.chk_lhe.setChecked(True)
        self.chk_lhe.setToolTip(t("LocalHistogramEqualization 只做在亮区(羽化蒙版),增强细丝/团块的立体层次,不动背景。"))
        self.sp_timeout = self._param(adv_v, "timeout", "单步超时(秒)", QSpinBox, 60, 7200, 30, 900)
        self.sp_timeout.setToolTip(t("单步作业的最长等待时间,超时视为失败并中止。"))

        # ---- LRGB(H) 专用参数(整块只在该流程显示,默认折叠) ----
        self.lrgb_wrap = QWidget(); self.lrgb_wrap.setObjectName("rowbg")
        lw = QVBoxLayout(self.lrgb_wrap); lw.setContentsMargins(0, 0, 0, 0); lw.setSpacing(7)
        self.btn_lrgb, lrgb_body, lrgb_v = self._make_section("LRGB(H) 专用参数", "仅本流程,共 4 项")
        lw.addWidget(self.btn_lrgb); lw.addWidget(lrgb_body)
        self.sp_ha = self._param(lrgb_v, "ha", "Hα 叠加强度", QDoubleSpinBox, 0, 2.0, 0.1, 0.0)
        self.sp_ha.setToolTip(t("Ha 通道叠加进 R 的强度(0~2.0),0=不叠。"))
        self.sp_ms = self._param(lrgb_v, "ms", "外环迭代拉伸次数", QSpinBox, 0, 6, 1, 2)
        self.sp_ms.setToolTip(t("maskstretch 迭代次数(0~6),越多外围越亮。"))
        self.sp_core = self._param(lrgb_v, "core", "核心保护阈值", QDoubleSpinBox, 0, 1.0, 0.05, 0.7)
        self.sp_core.setToolTip(t("高于该亮度的核心区不再被额外拉伸(0~1.0)。"))
        self.sp_crop = self._param(lrgb_v, "crop", "中央裁切比例", QDoubleSpinBox, 0, 0.4, 0.01, 0.13)
        self.sp_crop.setToolTip(t("统一裁掉四周对齐黑边的比例(0~0.4)。"))
        vp.addWidget(self.lrgb_wrap)

        left.addWidget(gp)
        left.addStretch(1)

        # ---- 日志(固定在左列底部,不随滚动条走) ----
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        # 日志区加高(74→170,更协调;上方输入区可滚动,加高不挤输入)。用户 2026-09-03 反馈原来太矮。
        self.log.setMinimumHeight(170); self.log.setMaximumHeight(230)
        self.log.setPlaceholderText(t("就绪。选择流程与输入后点击「开始处理」。"))
        self.log.setPlainText(t("就绪。选择流程与输入后点击「开始处理」。"))
        self.caret = BlinkBlock(self.log.viewport(), self.theme['logmark'])
        self.caret.setFixedSize(6, 13)
        leftcol.addWidget(self.log, 0)

        # ===== 右列:预览卡(空态=流程路线图)+ 评分导出卡 =====
        rightw = QWidget(); rightw.setObjectName("rowbg"); self._rightw = rightw
        rightcol = QVBoxLayout(rightw); rightcol.setContentsMargins(0, 0, 0, 0); rightcol.setSpacing(10)
        body.addWidget(rightw, 4)

        # 右列(预览卡 + 评分导出卡)放进可滚动容器:AI 点评/「需你决定」内容变多、或窗口变矮时,
        # 整列上下滚动,而不是把上面的预览框压扁(预览有最小高度守着,见 preview_scroll.setMinimumSize)。
        right_container = QWidget()
        right = QVBoxLayout(right_container); right.setContentsMargins(0, 0, 0, 0); right.setSpacing(10)
        self.right_scroll = QScrollArea(); self.right_scroll.setObjectName("rightscroll")
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setWidget(right_container)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.right_scroll.setFrameShape(QFrame.NoFrame)
        rightcol.addWidget(self.right_scroll, 1)

        pcard = QFrame(); pcard.setObjectName("viewer"); self._pcard = pcard
        pv = QVBoxLayout(pcard); pv.setContentsMargins(0, 0, 0, 0); pv.setSpacing(0)
        phead = QFrame(); phead.setObjectName("cardhead"); phead.setFixedHeight(48)
        ph2 = QHBoxLayout(phead); ph2.setContentsMargins(16, 0, 16, 0); ph2.setSpacing(10)
        ptitle = QLabel(); ptitle.setObjectName("cardtitle"); self._tr(ptitle, "成片预览")
        self.lbl_prevtag = QLabel(); self._tr(self.lbl_prevtag, "等待素材")
        self.lbl_view_hint = QLabel(); self.lbl_view_hint.setObjectName("sub")
        self._tr(self.lbl_view_hint, "按住图片看全分辨率细节")
        ph2.addWidget(ptitle, 0); ph2.addWidget(self.lbl_view_hint, 0); ph2.addStretch(1)
        ph2.addWidget(self.lbl_prevtag, 0, Qt.AlignVCenter)
        pv.addWidget(phead)

        pbody = QWidget(); pbody.setObjectName("rowbg")
        pb = QVBoxLayout(pbody); pb.setContentsMargins(20, 20, 20, 16); pb.setSpacing(10)
        # 成片预览:放进滚动区,按**视口宽度**缩放 → 图像完整呈现,过高就出竖向滚动条(不裁切)。
        self.preview = QLabel(""); self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setToolTip(t("按住鼠标放大查看(全分辨率),拖动平移,松开还原"))
        self._loupe = Loupe(self.preview)            # AstroBin 式放大镜(按住预览触发,见 eventFilter)
        self._loupe_on = False
        self._pm_hires = None; self._pm_hires_key = ""   # 放大镜全分辨率缓存(直接读成片 XISF)
        self.preview_scroll = QScrollArea(); self.preview_scroll.setObjectName("previewscroll")
        self.preview_scroll.setWidget(self.preview)
        self.preview_scroll.setWidgetResizable(False)   # 由 _rescale_preview 定 label 尺寸=缩放后图
        self.preview_scroll.setAlignment(Qt.AlignCenter)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.preview_scroll.setFrameShape(QFrame.NoFrame)
        # 最小高度给足:右列滚到最小态时(下方点评内容多),预览也守住 ~400px 不被压扁
        self.preview_scroll.setMinimumSize(180, 400)
        self.preview_scroll.setVisible(False)   # 有成片/阶段图才出现,空态让位给路线图
        pb.addWidget(self.preview_scroll, 3)

        # 多配色切换条:SHO 出多档时,每档一个按钮,点了切预览 + 决定导出哪档(窄窗口折行不裁)
        self.pal_bar = FlowBar(hspace=6, vspace=6); self.pal_bar.setObjectName("rowbg")
        self.pal_bar.setVisible(False)
        self.pal_btns = {}
        self._finals = {}                       # {配色: xisf 路径}
        self._cur_pal = None
        pb.addWidget(self.pal_bar, 0)

        # 暂停介入面板:运行中点「暂停介入」后出现 —— 对当前图做 梯度矫正/灰尘修复,再继续
        self.pause_panel = QWidget(); self.pause_panel.setObjectName("rowbg")
        ppv = QVBoxLayout(self.pause_panel); ppv.setContentsMargins(0, 4, 0, 0); ppv.setSpacing(6)
        self.lbl_pause = QLabel(t("已暂停 · 可对当前图做矫正"))
        self.lbl_pause.setObjectName("sub"); self.lbl_pause.setWordWrap(True)
        ppv.addWidget(self.lbl_pause)
        # 目标选择:合成前可回到任一通道去修(解决"暂停晚了一步、够不到想修的通道")
        trow = QWidget(); trow.setObjectName("rowbg"); th = QHBoxLayout(trow)
        th.setContentsMargins(0, 0, 0, 0); th.setSpacing(8)
        tlab = QLabel(t("选通道图:")); tlab.setObjectName("sub")
        self.cb_pause_target = QComboBox(); self.cb_pause_target.setMinimumWidth(160)
        self.cb_pause_target.setToolTip(t("选择前面已生成的某个通道图(Ha/OIII/SII…)来做矫正 —— 合成前可回到任一通道"))
        self.cb_pause_target.currentIndexChanged.connect(self._pause_target_changed)
        th.addWidget(tlab, 0); th.addWidget(self.cb_pause_target, 0); th.addStretch(1)
        ppv.addWidget(trow)
        self._pause_target_row = trow
        pbar = FlowBar(hspace=6, vspace=6); pbar.setObjectName("rowbg")
        self.btn_p_gc = QPushButton(t("梯度矫正")); self.btn_p_gc.setObjectName("seg")
        self.btn_p_gc.setToolTip(t("对当前图再跑一次 GradientCorrection"))
        self.btn_p_gc.clicked.connect(self._pause_do_gradient)
        # segdev:checkable 无 SlideIndicator → 点亮(checked)态用 segdev 的实心绿底,别用 #seg:checked(透明底深字隐形)
        self.btn_p_dust = QPushButton(t("灰尘修复")); self.btn_p_dust.setObjectName("segdev"); self.btn_p_dust.setCheckable(True)
        self.btn_p_dust.setToolTip(t("点亮后在预览上按住拖出一个圆框住灰尘 → 出现『应用修复』按钮"))
        self.btn_p_dust.clicked.connect(self._pause_toggle_dust)
        # 画好圈才出现的显式应用按钮(不再只靠双击 —— 用户容易找不到)
        self.btn_p_dust_apply = QPushButton(t("✓ 应用修复")); self.btn_p_dust_apply.setObjectName("primary")
        self.btn_p_dust_apply.setToolTip(t("对画好的圆做人工平场(也可直接在圆上双击)"))
        self.btn_p_dust_apply.clicked.connect(self._apply_dust_circle)
        self.btn_p_dust_apply.setVisible(False)
        self.btn_p_go = QPushButton(t("▶ 继续")); self.btn_p_go.setObjectName("primary")
        self.btn_p_go.clicked.connect(self._pause_continue)
        for b in (self.btn_p_gc, self.btn_p_dust, self.btn_p_dust_apply, self.btn_p_go):
            b.setCursor(Qt.PointingHandCursor); pbar.add(b)
        ppv.addWidget(pbar)
        # 与 AI 对话改图:说想法 → AI 给参数并执行工具(需已配 LLM 评委)
        self.pause_chat_log = QPlainTextEdit(); self.pause_chat_log.setReadOnly(True)
        self.pause_chat_log.setObjectName("chatlog"); self.pause_chat_log.setMaximumHeight(150)
        self.pause_chat_log.setPlaceholderText(t("与 AI 对话改当前图:例如「核心蓝色不够,增强一点核心的蓝,别动背景」"))
        ppv.addWidget(self.pause_chat_log)
        crow = QWidget(); crow.setObjectName("rowbg"); ch2 = QHBoxLayout(crow)
        ch2.setContentsMargins(0, 0, 0, 0); ch2.setSpacing(6)
        self.ed_pause_chat = QLineEdit(); self.ed_pause_chat.setPlaceholderText(t("告诉 AI 你想怎么改,回车发送…"))
        self.ed_pause_chat.returnPressed.connect(self._pause_send_chat)
        self.btn_p_send = QPushButton(t("发送")); self.btn_p_send.setObjectName("seg")
        self.btn_p_send.clicked.connect(self._pause_send_chat)
        self.btn_p_undo = QPushButton(t("撤销")); self.btn_p_undo.setObjectName("seg")
        self.btn_p_undo.setToolTip(t("撤销上一步矫正/AI 操作"))
        self.btn_p_undo.clicked.connect(lambda: self.worker and self.worker.send_pause_cmd({"op": "undo"}))
        for b in (self.btn_p_send, self.btn_p_undo):
            b.setCursor(Qt.PointingHandCursor)
        ch2.addWidget(self.ed_pause_chat, 1); ch2.addWidget(self.btn_p_send, 0); ch2.addWidget(self.btn_p_undo, 0)
        ppv.addWidget(crow)
        self.pause_panel.setVisible(False)
        pb.addWidget(self.pause_panel, 0)

        # 分步询问面板(用户 2026-09-15):流程跑到"有方向分歧"的岔口时弹出。
        #   与上面的「暂停介入」分工不同:暂停是**用户主动**在任意一步插手改图;
        #   这里是**程序主动**在少数几个真岔口上问方向,选完继续跑,不改已出的图。
        self.decide_panel = QWidget(); self.decide_panel.setObjectName("rowbg")
        dpv = QVBoxLayout(self.decide_panel); dpv.setContentsMargins(0, 4, 0, 0); dpv.setSpacing(6)
        self.lbl_dec_title = QLabel(""); self.lbl_dec_title.setObjectName("primlabel")
        self.lbl_dec_title.setWordWrap(True)
        self.lbl_dec_why = QLabel(""); self.lbl_dec_why.setObjectName("sub")
        self.lbl_dec_why.setWordWrap(True)
        dpv.addWidget(self.lbl_dec_title); dpv.addWidget(self.lbl_dec_why)
        self.dec_btnbar = FlowBar(hspace=6, vspace=6); self.dec_btnbar.setObjectName("rowbg")
        dpv.addWidget(self.dec_btnbar)
        self._dec_buttons = []
        self.dec_chat_log = QPlainTextEdit(); self.dec_chat_log.setReadOnly(True)
        self.dec_chat_log.setObjectName("chatlog"); self.dec_chat_log.setMaximumHeight(110)
        self.dec_chat_log.setPlaceholderText(
            t("按钮里没有你想要的,就直接说 —— 例如「盘面再蓝一点点,核心别动」"))
        dpv.addWidget(self.dec_chat_log)
        drow = QWidget(); drow.setObjectName("rowbg"); dh = QHBoxLayout(drow)
        dh.setContentsMargins(0, 0, 0, 0); dh.setSpacing(6)
        self.ed_dec_say = QLineEdit()
        self.ed_dec_say.setPlaceholderText(t("用自己的话说想往哪个方向走,回车发送…"))
        self.ed_dec_say.returnPressed.connect(self._dec_say)
        self.btn_dec_send = QPushButton(t("发送")); self.btn_dec_send.setObjectName("seg")
        self.btn_dec_send.clicked.connect(self._dec_say)
        self.btn_dec_apply = QPushButton(t("✓ 就按这个走")); self.btn_dec_apply.setObjectName("primary")
        self.btn_dec_apply.setToolTip(t("采用上面 AI 理解出来的方向,继续跑"))
        self.btn_dec_apply.setVisible(False)
        self.btn_dec_apply.clicked.connect(self._dec_apply)
        for b in (self.btn_dec_send, self.btn_dec_apply):
            b.setCursor(Qt.PointingHandCursor)
        dh.addWidget(self.ed_dec_say, 1); dh.addWidget(self.btn_dec_send, 0); dh.addWidget(self.btn_dec_apply, 0)
        dpv.addWidget(drow)
        self.decide_panel.setVisible(False)
        pb.addWidget(self.decide_panel, 0)
        # ── 手动调色面板(用户 2026-09-21)──────────────────────────────────────────
        # 用户原话:"用户点击画面中的某个位置标定背景,RGB 三个通道都以它为锚点,第二个控制点位
        #   则可以通过滑块或者曲线来控制,操作思路跟 CT 差不多……同时还提供一个饱和度曲线。
        #   但是这个部分不涉及加入蒙版后提升星系饱和度,那样整个交互就过于复杂了。"
        # 背景锚点是关键:没有它,任何低端改动都会直接给背景染色(用户手工时也是这么钉的)。
        self.color_panel = QWidget(); self.color_panel.setObjectName("rowbg")
        _cpv = QVBoxLayout(self.color_panel); _cpv.setContentsMargins(0, 4, 0, 0); _cpv.setSpacing(6)
        self.lbl_col_title = QLabel(); self.lbl_col_title.setObjectName("primlabel")
        self._tr(self.lbl_col_title, "调整颜色")
        self.lbl_col_hint = QLabel(); self.lbl_col_hint.setObjectName("sub")
        self.lbl_col_hint.setWordWrap(True)
        self._tr(self.lbl_col_hint,
                 "先在预览上点一下没有天体的地方,把那里定为背景 —— 三条曲线都会钉住这个点,"
                 "之后怎么拉都不会给背景染色。再用滑块调,预览会跟着变。")
        _cpv.addWidget(self.lbl_col_title); _cpv.addWidget(self.lbl_col_hint)

        self.btn_col_pick = QPushButton(t("在预览上点选背景"))
        self.btn_col_pick.setObjectName("segdev"); self.btn_col_pick.setCheckable(True)
        self.btn_col_pick.setCursor(Qt.PointingHandCursor)
        self.lbl_col_bg = QLabel(); self.lbl_col_bg.setObjectName("sub")
        _prow = QWidget(); _prow.setObjectName("rowbg"); _ph = QHBoxLayout(_prow)
        _ph.setContentsMargins(0, 0, 0, 0); _ph.setSpacing(8)
        # 【只改星系主体(用户 2026-09-21 追加)】用户原话:"现在如果直接拉饱和度,还是会影响到
        #   背景的色彩"。原因:**RGB 三条曲线有背景锚点保护,但饱和曲线没有** —— 它作用在"饱和度"
        #   这个量上、不是像素值,背景那点彩噪的低饱和正好落在它抬得最狠的段上,被一起放大。
        #   挂上 L 蒙版(黑点钉在背景,见 galaxycolor.lum_sat_mask_array)就只作用在天体上。
        #   默认**开**:用户是踩到这个坑才提的。
        self.btn_col_mask = QPushButton(t("只改星系,不动背景"))
        self.btn_col_mask.setObjectName("segdev"); self.btn_col_mask.setCheckable(True)
        self.btn_col_mask.setChecked(True); self.btn_col_mask.setCursor(Qt.PointingHandCursor)
        self.btn_col_mask.setToolTip(
            t("挂一张按亮度做的蒙版:背景处为 0,越亮的地方作用越强。") + chr(10)
            + t("关掉的话饱和度会把背景的彩噪一起拉出来。"))
        _ph.addWidget(self.btn_col_pick, 0); _ph.addWidget(self.btn_col_mask, 0)
        _ph.addWidget(self.lbl_col_bg, 1)
        _cpv.addWidget(_prow)

        self.col_presetbar = FlowBar(hspace=6, vspace=6); self.col_presetbar.setObjectName("rowbg")
        _cpv.addWidget(self.col_presetbar)
        self._col_preset_btns = []

        self._col_sliders = {}

        def _mkslider(key, label, lo, hi, init, tip):
            row = QWidget(); row.setObjectName("rowbg")
            h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
            lb = QLabel(label); lb.setMinimumWidth(96)
            sl = _FineSlider(Qt.Horizontal); sl.setRange(lo, hi); sl.setValue(init)
            sl.setToolTip(tip)
            val = QLabel(""); val.setObjectName("sub"); val.setMinimumWidth(58)
            h.addWidget(lb, 0); h.addWidget(sl, 1); h.addWidget(val, 0)
            _cpv.addWidget(row)
            self._col_sliders[key] = (sl, val)
            # 【必须吞掉参数】`valueChanged(int)` 会把**滑块当前值**传给槽 →
            #   直接连 `_col_changed` 的话 `immediate=滑块值`,非零即 True,防抖当场失效。
            sl.valueChanged.connect(lambda _v=0: self._col_changed())
            # 按住拖动期间出**草图**(半尺寸,几十毫秒),松手出全尺寸;都在后台算,界面不停。
            sl.sliderPressed.connect(lambda: setattr(self, "_col_dragging", True))
            sl.sliderReleased.connect(self._col_slider_released)
            return sl

        # 【范围放宽(用户 2026-09-21 实测)】原来 R/G/B ±30%、饱和 −30%~+60%,
        #   用户把**饱和顶到 +60% 的尽头**、R +20% / B +23% 才"稍微接近可用" —— 不够用。
        #   放宽到 R/G/B −40%~+100%、饱和 −30%~+200%。滑块步进仍是 1%,精调不受影响。
        _mkslider("r", t("红 R"), 60, 200, 100, t("往右 = 这个亮度上红更多。尘埃带偏橙靠它。"))
        _mkslider("g", t("绿 G"), 60, 200, 100, t("往右 = 绿更多。整体发品红/发紫时往右一点。"))
        _mkslider("b", t("蓝 B"), 60, 200, 100, t("往右 = 蓝更多。外围盘面偏蓝靠它。"))
        # 【蒙版收紧(用户 2026-09-21「蒙版圈的范围有点大」)】见 galaxycolor.lum_sat_mask_array:
        #   蒙版抬满的位置按「本体峰值的百分之多少」定,这个滑块就是那个百分比。
        _mkslider("mask", t("蒙版收紧"), 10, 85, 30,
                  t("往右 = 蒙版只盖住更亮的盘面,星系外围的淡云不再跟着提饱和;往左 = 盖得更宽。"))
        # 【蒙版覆盖率读数(用户 2026-09-22 M81_M82 事故)】同一个「收紧」数值在不同画面上
        #   含义完全不同 —— 0.85 在 M33(单星系)圈得住,在 M81_M82(双星系场)本体上只剩 0.446,
        #   于是背景侧的压饱和削到了星系身上。**光显示滑块数值不够,要显示它在这张图上的后果。**
        self.lbl_col_cover = QLabel(); self.lbl_col_cover.setObjectName("sub")
        self.lbl_col_cover.setWordWrap(True)
        _cpv.addWidget(self.lbl_col_cover)
        self.lbl_col_bgstat = QLabel(); self.lbl_col_bgstat.setObjectName("sub")
        self.lbl_col_bgstat.setWordWrap(True)
        self.lbl_col_bgstat.setToolTip(t(
            "背景区按**半径**圈(>3 倍本体半径)—— 按亮度圈会把蒙版真正漏出去的亮斑块排除在外,"
            "量出来是假的。 "
            "读数在预览分辨率上算,与成片略有出入:实测漏出预览 1.6% / 成片 0.8%,"
            "**预览偏保守**(宁可高估),所以预览看着干净就基本不会翻车。"))
        _cpv.addWidget(self.lbl_col_bgstat)
        _mkslider("x2", t("作用亮度"), 12, 70, 25,
                  t("三条曲线的第二个控制点放在多亮的地方。往左 = 只改暗的部分(外围盘面),"
                    "往右 = 连中等亮度也改(尘埃带、内盘)。最亮的核心始终不动。"))
        # 用户 2026-09-21 第二次反馈:+200% 还是顶到尽头 → 再抬到 +500%。
        _mkslider("sat", t("饱和度"), 70, 1000, 100,
                  t("往右 = 颜色更浓。高饱和的地方会自动收着点,不会推爆。"))
        # 【背景侧(蒙版反选)】用户原话:"蒙版可以加一个反选的功能,我可以降低图像暗部的
        #   饱和度和亮度,以突出主体,现在背景的饱和度可以再降一点"。
        #   做成**两个独立滑块**而不是一个反选开关:这样主体和背景能同时调,不必来回切模式;
        #   它们作用在蒙版的**补集**上(1−mask),与上面几个滑块互不干扰。
        _bglab = QLabel(); _bglab.setObjectName("sub")
        self._tr(_bglab, "背景侧(蒙版之外)—— 压下去能让主体更突出")
        _cpv.addWidget(_bglab)
        _mkslider("bgsat", t("背景饱和"), 0, 100, 100,
                  t("往左 = 背景颜色更淡。彩噪压在这里最有效,而且不碰主体。"))
        _mkslider("bglum", t("背景亮度"), 40, 100, 100,
                  t("往左 = 背景更暗。主体和背景拉开,画面更立体。"))

        _cbar = QWidget(); _cbar.setObjectName("rowbg"); _cbh = QHBoxLayout(_cbar)
        _cbh.setContentsMargins(0, 0, 0, 0); _cbh.setSpacing(8)
        self.btn_col_showmask = QPushButton(t("看蒙版"))
        # 【可切换按钮别用 seg(用户 2026-09-23:"点了以后没有取消的按钮")】
        #   `#seg:checked` 的底是**透明**、文字用 bg 深色 —— 那是给带滑动药丸(SlideIndicator)
        #   的标签栏设计的,药丸在后面画实心底。这排按钮没有药丸,于是一选中就变成
        #   **深底上的深字 + 透明背景 = 整个消失**,用户找不到它再点一次。
        #   `#segdev:checked` 是实心 accent 底 + 深字,同面板另两个切换按钮用的就是它。
        self.btn_col_showmask.setObjectName("segdev")
        self.btn_col_showmask.setCheckable(True)
        self.btn_col_showmask.setToolTip(t(
            "在预览上盖一层蓝纱,标出**会被当背景处理**的区域(饱和×背景饱和、亮度×背景亮度),"
            "亮线是两者的分界。用来确认暗云气、星系外晕有没有被误当成背景压掉。"))
        self.btn_col_auto = QPushButton(t("自动定其余"))
        self.btn_col_auto.setObjectName("seg")
        self.btn_col_auto.setToolTip(t(
            "蒙版、背景两项、饱和按可测目标解出来,你只管盘色。"
            "蒙版解「盖住天体最多、又不漏进背景」;饱和解到内盘饱和 0.20;背景两项取你已存各组的中位。"))
        self.btn_col_reset = QPushButton(t("复位")); self.btn_col_reset.setObjectName("seg")
        self.btn_col_skip = QPushButton(t("不调,继续")); self.btn_col_skip.setObjectName("seg")
        self.btn_col_apply = QPushButton(t("就这样")); self.btn_col_apply.setObjectName("primary")
        for _b in (self.btn_col_showmask, self.btn_col_auto, self.btn_col_reset,
                   self.btn_col_skip, self.btn_col_apply):
            _b.setCursor(Qt.PointingHandCursor)
        _cbh.addStretch(1)
        _cbh.addWidget(self.btn_col_showmask, 0)
        _cbh.addWidget(self.btn_col_auto, 0)
        _cbh.addWidget(self.btn_col_reset, 0); _cbh.addWidget(self.btn_col_skip, 0)
        _cbh.addWidget(self.btn_col_apply, 0)
        # 【为什么这么调(用户 2026-09-25)】一句话就够,存进预设和调色经验库(colorexp)。
        #   滑块值换一张底图就不成立,能迁移给自动调色的是原因:同样把背景压暗,是因为有竖条纹、
        #   蒙版漏光还是纯口味,下一次该不该照做完全不同。
        self.ed_col_reason = QLineEdit()
        self.ed_col_reason.setPlaceholderText(t("为什么这么调?(可选,一句话)—— 会存进调色经验库,给以后的自动调色参考"))
        self.ed_col_reason.setToolTip(t("写原因比写数值有用:比如背景里有什么问题、你想要什么效果。留空也能正常保存。"))
        _cpv.addWidget(self.ed_col_reason)
        _cpv.addWidget(_cbar)
        self.btn_col_pick.clicked.connect(self._col_toggle_pick)
        self.btn_col_mask.clicked.connect(self._col_changed)
        self.btn_col_auto.clicked.connect(self._col_autosolve)
        self.btn_col_showmask.toggled.connect(self._col_showmask_toggled)
        self.btn_col_reset.clicked.connect(self._col_reset)
        self.btn_col_skip.clicked.connect(lambda: self._col_finish(False))
        self.btn_col_apply.clicked.connect(lambda: self._col_finish(True))
        self.color_panel.setVisible(False)

        pb.addWidget(self.color_panel, 0)          # 手动调色面板(默认隐藏)

        # 空态 = 当前流程的阶段清单(运行时逐段点亮)
        self.road_v = QWidget(); self.road_v.setObjectName("rowbg")
        rv = QVBoxLayout(self.road_v); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(6)
        self.lbl_road_title = QLabel(""); self.lbl_road_title.setObjectName("roadtitle")
        self.lbl_road_sub = QLabel(""); self.lbl_road_sub.setObjectName("roadsub")
        self.lbl_road_sub.setWordWrap(True)
        rv.addWidget(self.lbl_road_title); rv.addWidget(self.lbl_road_sub); rv.addSpacing(2)
        self.road_rows = []
        for i, name in enumerate(PHASES):
            roww = QWidget(); roww.setObjectName("roadrow")
            rh = QHBoxLayout(roww); rh.setContentsMargins(10, 7, 11, 7); rh.setSpacing(10)
            dot = QLabel(str(i + 1)); dot.setFixedSize(20, 20); dot.setAlignment(Qt.AlignCenter)
            tcol = QVBoxLayout(); tcol.setSpacing(1)
            nm = QLabel(f"{i + 1} · {name}")
            ds = QLabel(""); ds.setObjectName("sub"); ds.setWordWrap(True)
            tcol.addWidget(nm); tcol.addWidget(ds)
            tag = QLabel("")
            rh.addWidget(dot, 0); rh.addLayout(tcol, 1); rh.addWidget(tag, 0)
            rv.addWidget(roww)
            self.road_rows.append({"w": roww, "dot": dot, "name": nm, "desc": ds, "tag": tag})
        rv.addStretch(1)
        self.road_panel = DotPanel(); self.road_panel.setObjectName("roadpanel")
        rp2 = QVBoxLayout(self.road_panel); rp2.setContentsMargins(14, 13, 14, 11)
        rp2.addWidget(self.road_v)
        pb.addWidget(self.road_panel, 2)

        # 运行/完成后:路线图压成一条横向阶段带(FlowBar → 窄窗口折行不裁)
        self.phase_row = FlowBar(hspace=28, vspace=6); self.phase_row.setObjectName("rowbg")
        self.phase_lbls = []
        for i, name in enumerate(PHASES):
            l = QLabel(f"{i + 1}·{name}")
            l.setToolTip(name)
            self.phase_lbls.append(l); self.phase_row.add(l)
        self.phase_row.setVisible(False)
        pb.addWidget(self.phase_row, 0)
        self.scanline = ScanBand(self.road_panel, self.theme['logmark'])
        self._scan_anim = QPropertyAnimation(self.scanline, b"pos", self)
        self._scan_anim.setDuration(6200); self._scan_anim.setLoopCount(-1)
        self._scan_anim.setEasingCurve(QEasingCurve.Linear)
        # 【右栏整体滚动(用户 2026-09-21「预览选背景那一栏被遮住了一部分,底栏按钮也被遮了一半」)】
        #   pbody 里塞着 预览(min 400)+ 配色条 + 暂停面板 + 岔口面板 + 调色面板 + 路线图 + 阶段带,
        #   调色面板加到 8 个滑块之后,**各子控件的最小高度之和超过了窗口高度** —— Qt 压不下去就
        #   互相裁切(看起来像"被遮住")。修法不是再去抠某个面板的高度(下次加一行又坏),
        #   而是给整栏一个滚动视口:装得下时和以前一模一样(widgetResizable 会把 pbody 撑满视口、
        #   内部 stretch 照旧),装不下才出滚动条。
        self.pane_scroll = QScrollArea(); self.pane_scroll.setObjectName("panescroll")
        self.pane_scroll.setWidget(pbody)
        self.pane_scroll.setWidgetResizable(True)
        self.pane_scroll.setFrameShape(QFrame.NoFrame)
        self.pane_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pane_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 【必须给最低高度(2026-09-22 回归)】QScrollArea 的 minimumSizeHint **不包含内容的最小高度**
        #   —— 那正是滚动区的意义。但也因此,pcard 从"至少装得下 400px 的预览"变成了"能压到几乎没有":
        #   审阅屏里它拿的是 stretch 0,于是整张预览卡塌成一条(用户 2026-09-22「要确保预览框的高度」)。
        #   加滚动区时**必须同时补一个下限**,否则就是把"挤不下会裁切"换成了"挤不下会塌掉"。
        self.pane_scroll.setMinimumHeight(420)
        pv.addWidget(self.pane_scroll, 1)
        right.addWidget(pcard, 1)

        # ---- 完成 · 评分与导出 ----
        self.gresult = QGroupBox(""); self.gresult.setObjectName("gb_result")
        gr_v = QVBoxLayout(self.gresult); gr_v.setContentsMargins(0, 0, 0, 0); gr_v.setSpacing(0)
        strip3, self.lbl_result_hint = self._card_strip("✓", "完成 · 评分与导出", True)
        gr_v.addWidget(strip3)
        gr_body = QWidget(); gr_body.setObjectName("rowbg"); gr_v.addWidget(gr_body)
        vr = QVBoxLayout(gr_body); vr.setContentsMargins(14, 12, 14, 14); vr.setSpacing(9)
        self.lbl_scores = QLabel("—"); self.lbl_scores.setWordWrap(True)
        srow = QWidget(); srow.setObjectName("rowbg")
        s_h = QHBoxLayout(srow); s_h.setContentsMargins(0, 0, 0, 0); s_h.setSpacing(9)
        self.score_bar = QFrame(); self.score_bar.setObjectName("scorebar")
        self.score_bar.setFixedSize(5, 34)
        s_h.addWidget(self.score_bar, 0, Qt.AlignTop); s_h.addWidget(self.lbl_scores, 1)
        vr.addWidget(srow)
        # 「评这一档」:切到未评分的配色档时出现,点了让评委单独评这一档(按需,省调用)
        self.btn_scorepal = QPushButton(t("评这一档")); self.btn_scorepal.setObjectName("seg")
        self.btn_scorepal.setCursor(Qt.PointingHandCursor); self.btn_scorepal.setVisible(False)
        self.btn_scorepal.clicked.connect(self._score_current_pal)
        vr.addWidget(self.btn_scorepal, 0, Qt.AlignLeft)
        # 「需你决定」可操作项:每条一行(说明 + 可选「应用」按钮),动态填充
        self.remedy_box = QVBoxLayout(); self.remedy_box.setSpacing(6)
        vr.addLayout(self.remedy_box)
        # 向 AI 提需求驱动修改:用户用自然语言说想怎么改 → agent_edit 解释 → 执行 → 复用 撤销/对比
        aiedit = QHBoxLayout(); aiedit.setSpacing(6)
        self.ed_ai_edit = QLineEdit()
        self.ed_ai_edit.setPlaceholderText(t("跟 AI 说想怎么改,例如「星点饱和度还不够」「背景再压暗点」「核心蓝一点」,回车发送…"))
        self.ed_ai_edit.returnPressed.connect(self._ai_edit_send)
        self.btn_ai_edit = QPushButton(t("发送")); self.btn_ai_edit.setObjectName("seg")
        self.btn_ai_edit.setCursor(Qt.PointingHandCursor)
        self.btn_ai_edit.clicked.connect(self._ai_edit_send)
        aiedit.addWidget(self.ed_ai_edit, 1); aiedit.addWidget(self.btn_ai_edit, 0)
        vr.addLayout(aiedit)
        # AI 回复就地显示(修 UX:原先只写「处理」面板日志,用户在审阅提意见看不到回复;这里同区显示思考中/回复)
        self.lbl_ai_reply = QLabel(); self.lbl_ai_reply.setObjectName("dim")
        self.lbl_ai_reply.setWordWrap(True); self.lbl_ai_reply.setVisible(False)
        vr.addWidget(self.lbl_ai_reply)

        # -- 审阅操作(留在 gresult →「审阅」页):灰尘修复 · 按评分优化 · 对比 · 撤销 · 重新评分 --
        rbtn = FlowBar(hspace=8, vspace=7); rbtn.setObjectName("rowbg")
        self.btn_dust = QPushButton(t("灰尘修复")); self.btn_dust.setCheckable(True)
        self.btn_dust.setCursor(Qt.PointingHandCursor)
        self.btn_dust.setToolTip(t("点亮后,在预览上按住拖出一个圆框住灰尘 → 出现『应用修复』按钮(所有配色档一起修)"))
        self.btn_dust.clicked.connect(self._toggle_dust_mode)
        self.btn_dust_apply = QPushButton(t("✓ 应用修复")); self.btn_dust_apply.setObjectName("primary")
        self.btn_dust_apply.setCursor(Qt.PointingHandCursor)
        self.btn_dust_apply.setToolTip(t("对画好的圆做人工平场(也可直接在圆上双击)"))
        self.btn_dust_apply.clicked.connect(self._apply_dust_circle)
        self.btn_dust_apply.setVisible(False)
        self.btn_scorefix = QPushButton(t("按评分优化")); self.btn_scorefix.setObjectName("seg")
        self.btn_scorefix.setCursor(Qt.PointingHandCursor)
        self.btn_scorefix.setToolTip(t("按确定性质量指标一键补救(纯 numpy,秒出):背景偏色→中和;星点发闷→星蒙版提饱和。\n"
                                     "只动该动的、不重跑管线,存为新成片并刷新指标。"))
        self.btn_scorefix.clicked.connect(self._apply_score_remedy)
        self.btn_scorefix.setVisible(False)          # 有可修的确定性问题时才显示(_show_scores 控制)
        self.btn_rescore = QPushButton(t("重新评分")); self.btn_rescore.setObjectName("seg")
        self.btn_rescore.setCursor(Qt.PointingHandCursor)
        self.btn_rescore.setToolTip(t("再唤起一次 AI 评分(评分超时/失败,或想让评委再看一次时用;后台跑不阻塞)"))
        self.btn_rescore.clicked.connect(self._rescore)
        self.btn_rescore.setVisible(False)           # 完成且配了评委才显示(_finished 控制)
        # segdev(非 seg):此按钮 checkable 但**背后无 SlideIndicator 绿药丸** → #seg:checked 的"透明底+深字"
        #   会让选中态(显示"看优化后"时)文字在深色面板上几乎隐形(用户 2026-09-04 反馈)。segdev 选中态自带实心绿底。
        self.btn_remedy_cmp = QPushButton(t("⇄ 对比原图")); self.btn_remedy_cmp.setObjectName("segdev")
        self.btn_remedy_cmp.setCheckable(True); self.btn_remedy_cmp.setCursor(Qt.PointingHandCursor)
        self.btn_remedy_cmp.setToolTip(t("在 优化前 / 优化后 之间切换预览对比"))
        self.btn_remedy_cmp.clicked.connect(self._toggle_remedy_compare)
        self.btn_remedy_cmp.setVisible(False)
        self.btn_remedy_undo = QPushButton(t("↩ 撤销优化")); self.btn_remedy_undo.setObjectName("seg")
        self.btn_remedy_undo.setCursor(Qt.PointingHandCursor)
        self.btn_remedy_undo.setToolTip(t("撤销「按评分优化」,恢复优化前的成片"))
        self.btn_remedy_undo.clicked.connect(self._undo_remedy)
        self.btn_remedy_undo.setVisible(False)
        rbtn.add(self.btn_dust); rbtn.add(self.btn_dust_apply); rbtn.add(self.btn_scorefix)
        rbtn.add(self.btn_remedy_cmp); rbtn.add(self.btn_remedy_undo); rbtn.add(self.btn_rescore)
        vr.addWidget(rbtn)
        # 进入导出:醒目主按钮(用户 2026-09-04:审阅完要有明确出口去导出,别只靠顶部进度条跳转)
        _exprow = QHBoxLayout(); _exprow.addStretch(1)
        self.btn_to_export = QPushButton(t("下一步:导出 →")); self.btn_to_export.setObjectName("primary")
        self.btn_to_export.setCursor(Qt.PointingHandCursor)
        self.btn_to_export.clicked.connect(lambda: self._go_stage(4))
        _exprow.addWidget(self.btn_to_export, 0)
        vr.addLayout(_exprow)
        self.gresult.setVisible(False)
        right.addWidget(self.gresult, 0)     # 临时;_install_ia() 会把它移到「审阅」页

        # ---- 导出面板(独立卡:格式 + 导出动作)——_install_ia() 放到「导出」页 ----
        self.export_panel = QGroupBox(""); self.export_panel.setObjectName("gb_result")
        _exv = QVBoxLayout(self.export_panel); _exv.setContentsMargins(0, 0, 0, 0); _exv.setSpacing(0)
        _strip_ex, self.lbl_export_hint = self._card_strip("↓", "导出成片", True)
        _exv.addWidget(_strip_ex)
        _exb = QWidget(); _exb.setObjectName("rowbg"); _exv.addWidget(_exb)
        vex = QVBoxLayout(_exb); vex.setContentsMargins(14, 12, 14, 14); vex.setSpacing(9)
        # 导出格式多选 + JPG 质量(FlowBar:窄窗口折行,不挤出可视区)
        fmt = FlowBar(hspace=8, vspace=7); fmt.setObjectName("rowbg")
        flab = QLabel(t("格式")); flab.setObjectName("plabel")
        self.chk_xisf = QCheckBox("XISF"); self.chk_xisf.setChecked(True)
        self.chk_xisf.setToolTip(t("直接复制成片 XISF(原始位深,无损)"))
        self.chk_png = QCheckBox("PNG")                     # 默认不勾
        self.chk_png.setToolTip(t("经 PixInsight 全分辨率重导 PNG(需 runner 在线)"))
        self.chk_jpg = QCheckBox("JPG"); self.chk_jpg.setChecked(True)   # 默认勾:成片默认导 XISF+JPG
        self.chk_jpg.setToolTip(t("经 PixInsight 全分辨率重导 JPG(需 runner 在线)"))
        qlab = QLabel(t("质量")); qlab.setObjectName("sub")
        self.sl_jpgq = QSlider(Qt.Horizontal); self.sl_jpgq.setRange(1, 100); self.sl_jpgq.setValue(95)
        self.sl_jpgq.setMinimumWidth(90); self.sl_jpgq.setMaximumWidth(140)
        self.sl_jpgq.setToolTip(t("JPG 导出质量(默认 95:画质与体积的甜点位)"))
        self.lbl_jpgq = QLabel("95"); self.lbl_jpgq.setObjectName("seclabel"); self.lbl_jpgq.setMinimumWidth(24)
        self.sl_jpgq.valueChanged.connect(lambda v: self.lbl_jpgq.setText(str(v)))
        self.chk_jpg.toggled.connect(self.sl_jpgq.setEnabled)
        self.chk_jpg.toggled.connect(self.lbl_jpgq.setEnabled)
        self.chk_jpg.toggled.connect(qlab.setEnabled)      # JPG 默认开 → 质量控件默认可用(下同)
        # 3D 建模备料:去星星云(JPG)+ 纯星点(PNG)+ 天体标注(TXT)。见记忆 star3d-* / pi-astrobin-reference。
        self.chk_starless = QCheckBox(t("去星星云·JPG"))
        self.chk_starless.setToolTip(t("导出去星后的纯星云图(JPG)——星空 3D 视频的星云底"))
        self.chk_export_stars = QCheckBox(t("纯星点·PNG"))     # 注意:别叫 chk_stars,那是「合回星点」(recombine)!
        self.chk_export_stars.setToolTip(t("导出纯星点图(PNG)——星空 3D 视频的星点层"))
        self.chk_annotate = QCheckBox(t("标注 TXT"))
        self.chk_annotate.setToolTip(t("有天文解析时,用 AnnotateImage 标注 Messier/NGC/IC/SH2 + HIP/TYC/GAIA 恒星,\n"
                                     "导出天体列表(名称/类型/像素坐标/星等)TXT —— 供结合纯星点图做 3D 建模"))
        for w in (flab, self.chk_xisf, self.chk_png, self.chk_jpg, qlab, self.sl_jpgq, self.lbl_jpgq,
                  self.chk_starless, self.chk_export_stars, self.chk_annotate):
            fmt.add(w)
        vex.addWidget(fmt)
        ebtn = FlowBar(hspace=8, vspace=7); ebtn.setObjectName("rowbg")
        self.btn_show = QPushButton(t("在文件夹显示")); self.btn_show.clicked.connect(self._show_in_folder)
        self.btn_show.setCursor(Qt.PointingHandCursor)
        self.btn_export = QPushButton(t("↓ 导出成片")); self.btn_export.setObjectName("primary")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._export)
        ebtn.add(self.btn_show); ebtn.add(self.btn_export)
        vex.addWidget(ebtn)
        self.export_panel.setVisible(False)
        right.addWidget(self.export_panel, 0)   # 临时;_install_ia() 会把它移到「导出」页

        # ===== 处理进度:常驻一行,运行时用高度动画展开(不再整块跳动) =====
        progw = QWidget(); progw.setObjectName("rowbg"); self._progw = progw
        pgo = QHBoxLayout(progw); pgo.setContentsMargins(20, 10, 20, 12); pgo.setSpacing(0)  # 底边距 12:进度条不贴操作栏
        self.gprog = QGroupBox(""); self.gprog.setObjectName("gb_prog")
        vpg = QHBoxLayout(self.gprog); vpg.setSpacing(10)
        self.prog_dot = PulseDot(8)
        self.lbl_prog_stage = QLabel(t("处理中")); self.lbl_prog_stage.setObjectName("progstage")
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
        self.bar.setTextVisible(False); self.bar.setMinimumWidth(80)
        self.bar.setFixedHeight(8)
        self.lbl_eta = QLabel("—"); self.lbl_eta.setObjectName("sub")
        vpg.addWidget(self.prog_dot, 0); vpg.addWidget(self.lbl_prog_stage, 0)
        vpg.addWidget(self.bar, 1); vpg.addWidget(self.lbl_eta, 0)
        pgo.addWidget(self.gprog, 1)
        self.gprog.setVisible(False)
        outer.addWidget(progw)

        # ===== 操作条:吸底全宽,次要按钮左、主按钮右(各自 FlowBar 内折行) =====
        act = QFrame(); act.setObjectName("actionbar"); self._actionbar = act
        ah = QHBoxLayout(act); ah.setContentsMargins(20, 11, 20, 12); ah.setSpacing(10)
        # 没有『启动 PixInsight』按钮:开始处理时自动冷启动。
        # 『释放 PixInsight』只在 PI/runner 起来后才出现(_refresh_runner 里按状态显隐)。
        self.btn_release = QPushButton(t("释放 PixInsight")); self.btn_release.clicked.connect(self._release_pi)
        self.btn_release.setToolTip(t("停止 job-runner/看门狗并结束 PixInsight,把 PI 交还给你手动使用"))
        self.btn_release.setVisible(False)
        self.btn_cfg = QPushButton(t("配置…")); self.btn_cfg.clicked.connect(self._open_settings)
        self.btn_cfg.setToolTip(t("PixInsight 路径、LLM 评委、AstroBin 后端等设置"))
        self.btn_clean = QPushButton(t("清理中间文件")); self.btn_clean.clicked.connect(self._cleanup)
        self.btn_clean.setToolTip(t("分目标列出运行目录 _run 的中间产物,勾选清理;按钮上常显可清理体积"))
        self._run_entries = None; self._run_size_total = None
        self._scan_thread = None; self._clean_dlg = None
        QTimer.singleShot(1500, self._refresh_run_size)     # 启动后后台统计一次 _run 体积 → 标到按钮上
        self.btn_deps = QPushButton(t("插件体检")); self.btn_deps.clicked.connect(self._check_deps)
        self.btn_deps.setToolTip(t("探测 BXT/SXT/NXT 等第三方模块与 PI 自带进程是否可用;缺失的给出下载/购买地址与安装步骤"))
        self.btn_reload = QPushButton(t("↻ 重载 runner")); self.btn_reload.clicked.connect(self._reload_runner)
        self.btn_reload.setToolTip(t("结束 PixInsight 并冷启动,加载**最新的 job-runner.js**(改了 runner 脚本后点它生效;\n"
                                   "也可用来恢复卡死/异常的 runner)。PI 的 -r 脚本只在启动时加载一次,故需冷启。"))
        self.btn_dumphist = QPushButton(t("导出历史")); self.btn_dumphist.clicked.connect(self._dump_history)
        self.btn_dumphist.setToolTip(t("生成一个独立小脚本,让你在**自己平时的 PixInsight** 里手动处理完后运行一次,\n"
                                     "把每一步进程的**全部精确参数**(HT黑/中/白点、GHS的D/b/SP、曲线控制点…)导出成文本。\n"
                                     "不走本工具的 runner:runner 占着 PI、手动交互处理会卡。用它给自动流程做量化参考。"))
        self.btn_pause = QPushButton(t("暂停介入")); self.btn_pause.setObjectName("seg")
        self.btn_pause.setToolTip(t("随时点它 → 程序在当前步骤后停住,你可对当前图做 梯度矫正/灰尘修复,再继续"))
        self.btn_pause.clicked.connect(self._request_pause); self.btn_pause.setVisible(False)
        self.btn_abort = QPushButton(t("■ 中止")); self.btn_abort.setObjectName("danger")
        self.btn_abort.clicked.connect(self._abort); self.btn_abort.setVisible(False)
        self.btn_run = QPushButton(t("▶ 开始处理")); self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self._run)
        bar_sec = FlowBar(hspace=7, vspace=7); bar_sec.setObjectName("rowbg")
        for b in (self.btn_release, self.btn_cfg, self.btn_clean, self.btn_deps, self.btn_reload, self.btn_dumphist):
            b.setCursor(Qt.PointingHandCursor)
            bar_sec.add(b)
        self._bar_sec = bar_sec
        # 顺序 = 「▶ 开始处理 / 处理中…」在左、「暂停介入」「■ 中止」在右;未处理时后两者隐藏不占位。
        # 同一行 —— FlowBar.sizeHint() 返回"排成一行"的宽度(不是单个按钮宽),否则 Maximum 策略
        # 会把容器宽度锁死在一个按钮上,挤成两行。
        self.bar_main = FlowBar(hspace=8, vspace=8); self.bar_main.setObjectName("rowbg")
        self.bar_main.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        for b in (self.btn_run, self.btn_pause, self.btn_abort):
            b.setCursor(Qt.PointingHandCursor)
            self.bar_main.add(b)
        ah.addWidget(bar_sec, 1); ah.addWidget(self.bar_main, 0, Qt.AlignBottom)
        outer.addWidget(act)

        self.bar_shim = Shimmer(self.bar, alpha=95, frac=0.26, ms=1500, radius=4)
        self.run_shim = Shimmer(self.btn_run, alpha=62, frac=0.34, ms=1900, radius=8)
        self._init_pulse()
        self._init_primary_glow()          # 主 CTA 呼吸辉光(须在首次 _apply_theme 前建好,免被黑投影覆盖)
        self._entrance((gin, gp))   # pcard 交由屏切换淡入(_fade_screen),不再单独入场

    def _card_strip(self, num, title, accent):
        """卡片头条:序号徽章 + 标题 + 右侧提示。返回 (头条, 右侧提示 QLabel)。"""
        f = QFrame(); f.setObjectName("stripaccent" if accent else "stripquiet")
        h = QHBoxLayout(f); h.setContentsMargins(14, 10, 13, 10); h.setSpacing(9)
        badge = QLabel(num); badge.setObjectName("badgeon" if accent else "badgeoff")
        badge.setFixedSize(20, 20); badge.setAlignment(Qt.AlignCenter)
        lab = QLabel(); lab.setObjectName("striptitle" if accent else "striptitle2")
        self._tr(lab, title)   # 卡片头条标题 i18n(给素材/调参数/完成·评分与导出/导出成片)
        hint = QLabel(""); hint.setObjectName("sub")
        h.addWidget(badge, 0); h.addWidget(lab, 0); h.addStretch(1); h.addWidget(hint, 0)
        return f, hint

    # ---------- 多页 IA(项目库 + 配置/处理/审阅/导出;A 方案:右侧预览常驻,顶部步骤导航翻左侧) ----------
    def _install_ia(self):
        """把 _build 造好的控件重组为 5 屏 IA(项目库/配置/处理/审阅/导出),按 app.html 定稿:
        顶栏 + 阶段导航常驻,屏幕切换;每屏各自取景器(单个 pcard 在处理/审阅间 reparent 复用)。
        worker/pipeline 接线完全不动。仅在 __init__ 里 _build() 之后调用一次。"""
        outer = self.layout()
        for w in (self._header, self.ribbon, self._bodyw, self._progw, self._actionbar):
            outer.removeWidget(w)
        self.ribbon.hide()          # 流程标签条弃用(改流程卡);flow_btns 仍作隐藏状态源

        top = self._make_topbar()                 # 含步骤导航(原单独一行的阶段导航并进顶栏)
        self._header.setParent(None)

        # ---- 配置屏(精修 2026-10-10,设计稿 Setup 板):左 = 三件事大纲;右 = 处理流程 / 素材 / 输出 + 底栏 ----
        setup = QWidget(); setup.setObjectName("screen")
        suh = QHBoxLayout(setup); suh.setContentsMargins(0, 0, 0, 0); suh.setSpacing(0)
        suh.addWidget(self._build_setup_outline(), 0)
        smain = QWidget(); smain.setObjectName("rowbg")
        smv = QVBoxLayout(smain); smv.setContentsMargins(0, 0, 0, 0); smv.setSpacing(0)
        swrap = QWidget(); swrap.setObjectName("rowbg")
        swh = QHBoxLayout(swrap); swh.setContentsMargins(0, 0, 0, 0); swh.setSpacing(0)
        sbody = QWidget(); sbody.setObjectName("rowbg"); sbody.setMaximumWidth(1100)
        sbv = QVBoxLayout(sbody); sbv.setContentsMargins(40, 28, 40, 28); sbv.setSpacing(32)
        sec_flow = self._setup_section("处理流程", "按你拍了哪些滤镜来选;选错了后面也能改")
        sec_flow.layout().addWidget(self._build_flow_cards())
        sec_src = self._setup_section("素材", "相机和素材状态决定怎么叠加、怎么校准")
        sec_src.layout().addWidget(self._restyle_source())
        sec_out = self._setup_section("输出", "")
        sec_out.layout().addWidget(self._trl("成片保存到", "sub"))
        self.exportdir_row.setObjectName("insprow")
        self.exportdir_row.layout().setContentsMargins(0, 0, 0, 0)
        self.exportdir_row.layout().itemAt(0).widget().hide()      # 行内「导出目录」标签由上面一行代替
        self.exportdir_row.layout().itemAt(2).widget().setObjectName("")   # 「浏览…」用普通按钮样式(seg 看着像禁用)
        sec_out.layout().addWidget(self.exportdir_row)
        for _s in (sec_flow, sec_src, sec_out):
            sbv.addWidget(_s)
        sbv.addStretch(1)
        swh.addWidget(sbody, 1); swh.addStretch(0)
        self._setup_secs = [sec_flow, sec_src, sec_out]
        self._setup_scroll = self._screen_scroll(swrap)
        self._setup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._setup_scroll.verticalScrollBar().valueChanged.connect(lambda _v: self._sync_setup_outline())
        smv.addWidget(self._setup_scroll, 1)
        sbar = QFrame(); sbar.setObjectName("setupbar"); sbar.setFixedHeight(64)
        sbh = QHBoxLayout(sbar); sbh.setContentsMargins(40, 0, 40, 0); sbh.setSpacing(12)
        self.lbl_setup_summary = QLabel(""); self.lbl_setup_summary.setObjectName("sub")
        _nextb = QPushButton(); _nextb.setObjectName("primary"); _nextb.setCursor(Qt.PointingHandCursor)
        self._tr(_nextb, "下一步:处理 →")
        _nextb.clicked.connect(lambda: self._go_stage(2))
        sbh.addWidget(self.lbl_setup_summary, 1); sbh.addWidget(_nextb, 0)
        smv.addWidget(sbar, 0)
        suh.addWidget(smain, 1)
        # 大纲完成态:素材 / 输出随手改,1.2s 轮询一次(只在配置屏时做,只查几个文件在不在)
        self._setup_timer = QTimer(self)
        self._setup_timer.timeout.connect(lambda: self._stage_idx == 1 and self._sync_setup_outline())
        self._setup_timer.start(1200)

        # ---- 处理屏(精修 2026-10-10,设计稿 Main / ColorPanel 板)----
        #   左 = 参数检查器(按「运行 / 拉伸与色彩 / 背景 / 引擎」分组;暂停·岔口·调色面板出现时整栏换成面板)
        #        + 吸底运行卡(进度 + 开始 / 暂停 / 中止);
        #   右 = 取景器(唯一 pcard 挂在 _proc_view)+ 阶段时间线 + 可收起的运行日志。
        process = QWidget(); process.setObjectName("screen")
        prg = QHBoxLayout(process); prg.setContentsMargins(0, 0, 0, 0); prg.setSpacing(0)
        prg.addWidget(self._build_inspector(), 0)
        pright = QWidget(); pright.setObjectName("rowbg")
        prv = QVBoxLayout(pright); prv.setContentsMargins(0, 0, 0, 0); prv.setSpacing(0)
        self._proc_view = QWidget(); self._proc_view.setObjectName("rowbg")
        self._proc_view_l = QVBoxLayout(self._proc_view); self._proc_view_l.setContentsMargins(0, 0, 0, 0)
        prv.addWidget(self._proc_view, 1)
        # 阶段时间线:原来压在预览卡里的阶段带搬出来,跟着它显隐(出第一张阶段图才出现)
        self._timeline = QFrame(); self._timeline.setObjectName("timeline")
        _tl = QHBoxLayout(self._timeline); _tl.setContentsMargins(20, 10, 20, 10)
        self.phase_row.setParent(None); _tl.addWidget(self.phase_row, 1)
        self._timeline.setVisible(not self.phase_row.isHidden())
        self._vw_tl = _VisWatch(lambda: self._timeline.setVisible(not self.phase_row.isHidden()), self)
        self.phase_row.installEventFilter(self._vw_tl)
        prv.addWidget(self._timeline, 0)
        prv.addWidget(self._build_log_drawer(), 0)
        prg.addWidget(pright, 1)

        # ---- 审阅屏(设计稿 Review 板):左 = 取景器;右 = 评审 / 实测指标 / 继续调整 + 底栏 ----
        review = QWidget(); review.setObjectName("screen")
        rvh = QHBoxLayout(review); rvh.setContentsMargins(0, 0, 0, 0); rvh.setSpacing(0)
        self._rev_view = QWidget(); self._rev_view.setObjectName("rowbg")
        self._rev_view_l = QVBoxLayout(self._rev_view); self._rev_view_l.setContentsMargins(0, 0, 0, 0)
        rvh.addWidget(self._rev_view, 1)
        rvh.addWidget(self._build_review_aside(), 0)
        # ---- 导出屏(精修 2026-10-10,设计稿 Export 板):左 = 标题 + 大图;右 = 格式 / 附件 / 保存到 / 之前导出过 + 导出按钮 ----
        export = QWidget(); export.setObjectName("screen")
        exh = QHBoxLayout(export); exh.setContentsMargins(0, 0, 0, 0); exh.setSpacing(0)
        emain = QWidget(); emain.setObjectName("rowbg")
        emv = QVBoxLayout(emain); emv.setContentsMargins(28, 24, 28, 24); emv.setSpacing(16)
        ehd = QHBoxLayout(); ehd.setSpacing(16)
        ecol = QVBoxLayout(); ecol.setSpacing(4)
        self.lbl_export_title = QLabel(""); self.lbl_export_title.setObjectName("h1")
        self.lbl_export_sub = QLabel(""); self.lbl_export_sub.setObjectName("sub")
        ecol.addWidget(self.lbl_export_title); ecol.addWidget(self.lbl_export_sub)
        self.lbl_export_dims = QLabel(""); self.lbl_export_dims.setObjectName("statusmono")
        ehd.addLayout(ecol, 1); ehd.addWidget(self.lbl_export_dims, 0, Qt.AlignBottom)
        emv.addLayout(ehd)
        _exp_prev_card = QFrame(); _exp_prev_card.setObjectName("exportframe")
        _epc = QVBoxLayout(_exp_prev_card); _epc.setContentsMargins(20, 20, 20, 20)
        self.export_preview = QLabel(); self.export_preview.setObjectName("exportprev")
        self.export_preview.setAlignment(Qt.AlignCenter); self.export_preview.setMinimumSize(320, 320)
        self._tr(self.export_preview, "成片就绪后在此预览")
        _epc.addWidget(self.export_preview, 1)
        # 导出屏预览也配 AstroBin 式放大镜(复用全分辨率成片 _pm_hires;用户 2026-09-07)
        self._export_loupe = Loupe(self.export_preview)
        self._export_loupe_on = False
        self._export_pm_display = None
        self.export_preview.setToolTip(t("按住鼠标放大查看(全分辨率),拖动平移,松开还原"))
        self.export_preview.installEventFilter(self)
        emv.addWidget(_exp_prev_card, 1)
        exh.addWidget(emain, 1)
        exh.addWidget(self._build_export_aside(), 0)

        home = self._build_home()

        # ---- 屏栈 ----
        self.screen_stack = QStackedWidget()
        self._screens = [home, setup, process, review, export]
        for pg in self._screens:
            self.screen_stack.addWidget(pg)

        # 预览初始挂到处理屏取景器;把 pcard 从旧右列取出,旧空容器弃用
        self._mount_preview(self._proc_view_l)
        self._rightw.setParent(None); self._leftw.setParent(None)
        self._progw.setParent(None); self._bodyw.setParent(None); self._actionbar.setParent(None)

        footer = self._make_footer()

        # ---- 顶层装配:顶栏(含步骤导航)+ 屏栈 + 状态栏 ----
        outer.addWidget(top, 0)
        outer.addWidget(self.screen_stack, 1)
        outer.addWidget(footer, 0)

        # 登记 _build 创建的关键 CTA / 格式项做 i18n(chrome-first;深层参数行/tooltip 暂留中文)
        for _b, _zh in [(self.btn_run, "▶ 开始处理"), (self.btn_pause, "暂停介入"),
                        (self.btn_abort, "■ 中止"),
                        (self.btn_show, "在文件夹显示"),
                        (self.btn_release, "释放 PixInsight"), (self.btn_cfg, "配置…"),
                        (self.btn_deps, "插件体检"), (self.btn_reload, "↻ 重载 runner"),
                        (self.btn_dumphist, "导出历史"),
                        (self.btn_to_export, "下一步:导出 →")]:
            if _b is not None:
                self._tr(_b, _zh)

        self._stage_idx = -1
        self._go_stage(0)           # 落在项目库

    def _themed_icon(self, w, tpl, size, key="text2", pad=0):
        """登记一个随主题重着色的线性图标(切主题时 _repaint_icons 重渲)。pad=图标右侧留白(当文字间距)。"""
        self._icon_reg.append((w, tpl, size, key, pad))
        col = self.theme[key] if hasattr(self, "theme") else DARK[key]
        w.setIcon(_icon_padded(tpl, size, col, pad) if pad else icons.icon(tpl, size, col))
        w.setIconSize(QSize(size + pad, size))
        return w

    def _repaint_icons(self):
        p = self.theme
        for w, tpl, size, key, pad in getattr(self, "_icon_reg", []):
            try:
                w.setIcon(_icon_padded(tpl, size, p[key], pad) if pad else icons.icon(tpl, size, p[key]))
            except Exception:
                pass
        if hasattr(self, "logo_tile"):
            self.logo_tile.setPixmap(icons.pixmap(icons.LOGO, 16, p['accent']))

    def _make_topbar(self):
        """顶栏(精修 2026-10-10,设计稿 Main 板):
        标记方块 + 品牌字 + 版本 | 项目名(可直接改)+ 保存状态 + 保存/新建 ‖ 步骤导航(居中)‖
        PixInsight 状态 · 中/EN · 主题 · 工具菜单 · 设置。原来单独一行的阶段导航并进来,省一整行高度。
        复用已建的 banner / runner_pill / btn_theme(reparent 进来)。"""
        self._icon_reg = []
        top = QFrame(); top.setObjectName("headerbar"); top.setFixedHeight(56); self._topbar = top
        self._hdr_level = 0
        th = QHBoxLayout(top); th.setContentsMargins(16, 0, 16, 0); th.setSpacing(10)
        self.logo_tile = QLabel(); self.logo_tile.setObjectName("logotile")
        self.logo_tile.setFixedSize(28, 28); self.logo_tile.setAlignment(Qt.AlignCenter)
        th.addWidget(self.logo_tile, 0, Qt.AlignVCenter)
        th.addWidget(self.banner, 0, Qt.AlignVCenter)              # 品牌字(GradientLabel,改单色正文色)
        self.lbl_ver = QLabel("0.9"); self.lbl_ver.setObjectName("ver")
        th.addWidget(self.lbl_ver, 0, Qt.AlignVCenter)
        _vd = QFrame(); _vd.setObjectName("vdiv"); _vd.setFixedSize(1, 24)
        th.addSpacing(4); th.addWidget(_vd, 0, Qt.AlignVCenter); th.addSpacing(2)
        # 项目名(直接点名字改)+ 保存状态(圆点 + 字)+ 保存 / 新建
        chip = QFrame(); chip.setObjectName("projchip")
        ch = QHBoxLayout(chip); ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(6)
        self.ed_project = QLineEdit(); self.ed_project.setObjectName("projname")
        self._tr(self.ed_project, "未命名项目", "setPlaceholderText")
        self.ed_project.setToolTip(t("项目名(导出文件名 / .ttproj 工程名)"))
        self.ed_project.textEdited.connect(lambda _t: self._mark_dirty())
        self.ed_project.textChanged.connect(lambda _t: self._fit_projname())
        self.lbl_saved_dot = QLabel(); self.lbl_saved_dot.setObjectName("saveddot")
        self.lbl_saved_dot.setFixedSize(6, 6); self.lbl_saved_dot.setProperty("dirty", True)
        self.lbl_saved = QLabel(t("未保存")); self.lbl_saved.setObjectName("savedtag")
        self.lbl_saved.setProperty("dirty", True)
        self.btn_save = QToolButton(); self.btn_save.setObjectName("chipbtn"); self.btn_save.setFixedSize(26, 26)
        self._themed_icon(self.btn_save, icons.SAVE, 14)
        self.btn_save.setToolTip(t("保存 .ttproj 工程(配置 + 成片 + 调色态)"))
        self.btn_save.setCursor(Qt.PointingHandCursor); self.btn_save.clicked.connect(self._save_project)
        # 新建项目(保存键右侧;用户 2026-09-07)。先自动保存当前工程再新建,别丢进度。
        self.btn_new = QToolButton(); self.btn_new.setObjectName("chipbtn"); self.btn_new.setFixedSize(26, 26)
        self._themed_icon(self.btn_new, icons.PLUS, 12)
        self.btn_new.setToolTip(t("新建项目(会先自动保存当前工程)"))
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.clicked.connect(lambda: (self._autosave(), self._new_project()))
        ch.addWidget(self.ed_project, 0); ch.addSpacing(2)
        ch.addWidget(self.lbl_saved_dot, 0, Qt.AlignVCenter); ch.addWidget(self.lbl_saved, 0)
        ch.addSpacing(4); ch.addWidget(self.btn_save, 0); ch.addWidget(self.btn_new, 0)
        self._fit_projname()
        th.addWidget(chip, 0, Qt.AlignVCenter)
        th.addStretch(1)
        th.addWidget(self._make_stepper(), 0, Qt.AlignVCenter)     # 步骤导航居中(两侧弹簧)
        th.addStretch(1)
        self.runner_pill.setParent(None)
        th.addWidget(self.runner_pill, 0, Qt.AlignVCenter)
        # 语言切换 中/EN(当前语言保持实心绿:用户 2026-09-11 要一眼看出当前是哪种语言)
        langbox = QFrame(); langbox.setObjectName("langbox"); langbox.setFixedHeight(28)
        lb = QHBoxLayout(langbox); lb.setContentsMargins(1, 1, 1, 1); lb.setSpacing(0)
        self.lang_group = QButtonGroup(self); self.lang_group.setExclusive(True)
        self.lang_btns = {}
        for code, label in (("zh", "中"), ("en", "EN")):
            b = QPushButton(label); b.setObjectName("langseg"); b.setCheckable(True)
            b.setFixedHeight(26); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, c=code: self._set_lang(c))
            self.lang_group.addButton(b); self.lang_btns[code] = b; lb.addWidget(b)
        _cur = config.get_setting("ui.lang", config.get_setting("lang", "zh")) or "zh"
        self.lang_btns.get(_cur, self.lang_btns["zh"]).setChecked(True)
        th.addWidget(langbox, 0, Qt.AlignVCenter)
        self.btn_theme.setParent(None); self.btn_theme.setText(""); self.btn_theme.setObjectName("iconbtn")
        self.btn_theme.setFixedSize(32, 32); self._themed_icon(self.btn_theme, icons.THEME, 15)
        self.btn_theme.setToolTip(t("主题:深色 / 浅色"))
        th.addWidget(self.btn_theme, 0, Qt.AlignVCenter)
        th.addWidget(self._make_tools_button(), 0, Qt.AlignVCenter)
        gear = QToolButton(); gear.setObjectName("iconbtn"); gear.setFixedSize(32, 32)
        self._themed_icon(gear, icons.GEAR, 15)
        gear.setCursor(Qt.PointingHandCursor); gear.setToolTip(t("设置(PixInsight 路径 / LLM 评委 / 后端…)"))
        gear.clicked.connect(self._open_settings)
        th.addWidget(gear, 0, Qt.AlignVCenter)
        return top

    def _fit_projname(self):
        """项目名框宽度跟着名字走(空时按占位符),夹在 80~220px。"""
        e = getattr(self, "ed_project", None)
        if e is None:
            return
        txt = e.text() or e.placeholderText()
        from PyQt5.QtGui import QFont, QFontMetrics
        f = QFont(e.font()); f.setPixelSize(14); f.setWeight(QFont.DemiBold)
        w = QFontMetrics(f).horizontalAdvance(txt) + 18
        e.setFixedWidth(max(80, min(220, w)))

    def _fit_header(self):
        """窄窗口时顶栏分级收起(最小窗宽 1024 时放不下全部):
        1 级 = 品牌字 / 版本 / PixInsight 状态字 / 工具二字 / 「未保存」字收起(都留图标或圆点 + 悬停提示);
        2 级 = 步骤导航只留当前步的名字,其余只剩序号圈。每次从 0 级试起,放得下就停。"""
        hb = getattr(self, "_topbar", None)
        if hb is None or not hasattr(self, "nav_btns"):
            return
        names = ["项目库", "配置", "处理", "审阅", "导出"]
        cur = getattr(self, "_stage_idx", 0)
        W = hb.width() if hb.width() > 0 else self.width()
        for lvl in (0, 1, 2):
            full = lvl == 0
            for w in (self.banner, self.lbl_ver, self.lbl_runner, self.lbl_saved):
                w.setVisible(full)
            self.tools_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if full else Qt.ToolButtonIconOnly)
            self.runner_pill.layout().setContentsMargins(6, 0, 12 if full else 6, 0)
            for i, b in enumerate(self.nav_btns):
                show = lvl < 2 or i == cur
                b.setText(t(names[i]) if show else "")
                b.setToolTip("" if show else t(names[i]))
            hb.layout().invalidate()
            if hb.layout().sizeHint().width() <= W or lvl == 2:
                break
        self._hdr_level = lvl

    def _make_stepper(self):
        """步骤导航:项目库 — ①配置 — ②处理 — ③审阅 — ④导出。
        当前步 = 浅绿底药丸 + 实心绿序号;做完的步 = 绿圈对勾 + 绿连线(_sync_steps 判定);
        仍可随意点任何一步(导航不设门槛,完成态只是告诉你走到哪了)。"""
        holder = QWidget(); holder.setObjectName("rowbg")
        hl = QHBoxLayout(holder); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(4)
        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        self.nav_btns = []; self._step_lines = []
        for i, name in enumerate(["项目库", "配置", "处理", "审阅", "导出"]):
            if i > 0:
                ln = QFrame(); ln.setObjectName("stepline"); ln.setFixedSize(18, 1)
                hl.addWidget(ln, 0, Qt.AlignVCenter); self._step_lines.append(ln)
            b = QPushButton(); b.setObjectName("step"); b.setCheckable(True); b.setFixedHeight(32)
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(20 + STEP_GAP, 20) if i else QSize(14 + STEP_GAP, 14))
            self._tr(b, name)
            b.clicked.connect(lambda _c, idx=i: self._go_stage(idx))
            self.nav_group.addButton(b, i); self.nav_btns.append(b); hl.addWidget(b, 0)
        self._themed_icon(self.nav_btns[0], icons.GRID, 14, pad=STEP_GAP)
        return holder

    def _make_tools_button(self):
        """工具菜单:原来页脚一排维护按钮(清理 / 体检 / 重启 / 导出参数 / 释放)收进这里。
        菜单项直接调原来的槽函数;旧按钮对象保留(不显示),免得别处引用断掉。"""
        btn = QToolButton(); btn.setObjectName("toolsbtn"); btn.setFixedHeight(32)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); btn.setPopupMode(QToolButton.InstantPopup)
        btn.setCursor(Qt.PointingHandCursor)
        self._tr(btn, "工具"); self._themed_icon(btn, icons.TOOLS, 14)
        menu = QMenu(btn); menu.setToolTipsVisible(True)
        # 圆角菜单:不开透明底的话 Windows 会在四角露出方形黑底
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WA_TranslucentBackground)
        self.act_clean = menu.addAction(t("清理中间文件…")); self.act_clean.triggered.connect(self._cleanup)
        self.act_clean.setToolTip(self.btn_clean.toolTip())
        self.act_deps = menu.addAction(""); self._tr(self.act_deps, "检查 PixInsight 插件")
        self.act_deps.setToolTip(self.btn_deps.toolTip()); self.act_deps.triggered.connect(self._check_deps)
        self.act_hist = menu.addAction(""); self._tr(self.act_hist, "导出 PixInsight 手动处理参数…")
        self.act_hist.setToolTip(self.btn_dumphist.toolTip()); self.act_hist.triggered.connect(self._dump_history)
        menu.addSeparator()
        self.act_reload = menu.addAction(""); self._tr(self.act_reload, "重启 PixInsight")
        self._tr(self.act_reload, "结束 PixInsight 并重新启动,加载最新的处理脚本。处理卡住、或更新了本工具后用它。",
                 "setToolTip")
        self.act_reload.triggered.connect(self._reload_runner)
        self.act_release = menu.addAction(""); self._tr(self.act_release, "释放 PixInsight(交给你手动用)")
        self.act_release.setToolTip(self.btn_release.toolTip()); self.act_release.triggered.connect(self._release_pi)
        self.act_release.setVisible(False)                 # 跟『释放』按钮一样:PI 起来后才出现
        btn.setMenu(menu)
        self.tools_btn = btn
        return btn

    def _make_footer(self):
        """底部状态栏(28px):中间文件体积 + 清理 | 版本。原来那排维护按钮挪进了顶栏「工具」菜单。"""
        footer = QFrame(); footer.setObjectName("footerbar"); footer.setFixedHeight(28)
        fl = QHBoxLayout(footer); fl.setContentsMargins(16, 0, 16, 0); fl.setSpacing(6)
        self._bar_sec.setParent(footer); self._bar_sec.hide()      # 旧按钮条:对象保留、不再显示
        self.lbl_runfiles = QLabel(); self.lbl_runfiles.setObjectName("statustext")
        self._tr(self.lbl_runfiles, "中间文件")
        self.lbl_runsize = QLabel("—"); self.lbl_runsize.setObjectName("statusmono")
        _sep = QLabel("·"); _sep.setObjectName("statustext")
        self.btn_clean_link = QPushButton(); self.btn_clean_link.setObjectName("linkbtn")
        self._tr(self.btn_clean_link, "清理"); self.btn_clean_link.setCursor(Qt.PointingHandCursor)
        self.btn_clean_link.clicked.connect(self._cleanup)
        for w in (self.lbl_runfiles, self.lbl_runsize, _sep, self.btn_clean_link):
            fl.addWidget(w, 0, Qt.AlignVCenter)
        fl.addStretch(1)
        _v = QLabel("v0.9"); _v.setObjectName("statusmono"); fl.addWidget(_v, 0, Qt.AlignVCenter)
        return footer

    def _set_clean_size(self, total=None, scanning=False):
        """中间文件体积 → 工具菜单项 + 状态栏 + (隐藏的)旧按钮,一处更新。"""
        sz = t("统计中…") if scanning else (self._fmt_size(total) if total else "")
        if hasattr(self, "btn_clean"):
            self.btn_clean.setText(t("清理中间文件") + (f"({sz})" if sz else ""))
        if hasattr(self, "act_clean"):
            self.act_clean.setText(t("清理中间文件…") + (f"  {sz}" if sz else ""))
        if hasattr(self, "lbl_runsize"):
            self.lbl_runsize.setText(sz or "0 MB")

    def _setup_ready(self):
        """「配置」这一步算不算填好了:素材行至少一行、文件/目录都在。只用来画导航上的对勾。"""
        try:
            mode = getattr(self, "_input_mode", 0)
            if mode == 0:
                mc = self._master_config()
                return bool(mc) and all(Path(x["file"]).exists() for x in mc)
            if mode == 1:
                rg = self._reg_config()
                return bool(rg) and all(Path(g["dir"]).exists() for g in rg)
            raw = self._raw_config()
            lights = raw.get("lights") if raw.get("device") == "mono" else [n["light"] for n in raw.get("nights", [])]
            return bool(lights) and all(lights)
        except Exception:
            return False

    def _sync_steps(self):
        """步骤导航的完成态 + 序号图标(随主题)。配置=素材齐;处理=有成片;审阅=看过这张成片;导出=导出过这张成片。"""
        if not hasattr(self, "_step_lines"):
            return
        p = self.theme
        fin = self._final_png if (getattr(self, "_final_png", "") and Path(self._final_png).exists()) else ""
        done = {1: self._setup_ready(), 2: bool(fin),
                3: bool(fin) and getattr(self, "_reviewed_png", "") == fin,
                4: bool(fin) and getattr(self, "_exported_png", "") == fin}
        cur = getattr(self, "_stage_idx", 0)
        for i, b in enumerate(self.nav_btns):
            if i == 0:
                continue
            st = "cur" if i == cur else ("done" if done.get(i) else "todo")
            b.setIcon(_step_badge(st, i, p))
            if b.property("done") != (st == "done"):
                b.setProperty("done", st == "done"); b.style().unpolish(b); b.style().polish(b)
        if getattr(self, "_hdr_level", 0) == 2:            # 窄窗口只显示当前步的名字 → 换步要重排
            self._fit_header()
        for k, ln in enumerate(self._step_lines):        # 第 k 条线连着 k 和 k+1 两步;前一步做完就变绿
            on = bool(done.get(k)) if k else False
            if ln.property("done") != on:
                ln.setProperty("done", on); ln.style().unpolish(ln); ln.style().polish(ln)

    def _screen_scroll(self, content):
        sa = QScrollArea(); sa.setObjectName("screenscroll"); sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame); sa.setWidget(content)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        return sa

    def _build_flow_cards(self):
        """配置屏 4 张流程卡(签名色徽章 + 名 + 一句话;选中态绿边+✓)。点卡=选流程。"""
        wrap = QWidget(); wrap.setObjectName("rowbg")
        g = QGridLayout(wrap); g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(11); g.setVerticalSpacing(11)
        self.flow_cards = []
        for i, (kind, _full) in enumerate(self.FLOWS):
            badge, name, desc = FLOW_CARD[kind]; sig = FLOW_SIG[kind]
            r, gg, bb = int(sig[1:3], 16), int(sig[3:5], 16), int(sig[5:7], 16)
            card = ClickFrame(); card.setObjectName("flowcard")
            cl = QVBoxLayout(card); cl.setContentsMargins(16, 16, 16, 16); cl.setSpacing(10)
            trow = QHBoxLayout(); trow.setContentsMargins(0, 0, 0, 0); trow.setSpacing(4)
            for _c in FLOW_DOTS.get(kind, ("#C6D0DC",) * 3):
                _d = QLabel(); _d.setFixedSize(10, 10); _d.setStyleSheet(f"background:{_c}; border-radius:5px;")
                trow.addWidget(_d, 0, Qt.AlignVCenter)
            tick = self._trl("已选", "seltag"); tick.setVisible(False)
            _sp = tick.sizePolicy(); _sp.setRetainSizeWhenHidden(True); tick.setSizePolicy(_sp)   # 隐藏也占位:四张卡标题对齐
            trow.addStretch(1); trow.addWidget(tick, 0, Qt.AlignVCenter)
            nm = self._trl(name, "flowname")
            ds = self._trl(desc, "flowdesc"); ds.setWordWrap(True)
            cl.addLayout(trow); cl.addWidget(nm); cl.addWidget(ds); cl.addStretch(1)   # 内容顶齐(同排卡等高时不被拉开)
            card.clicked.connect(lambda idx=i: self._pick_flow(idx))
            g.addWidget(card, 0, i); g.setColumnStretch(i, 1)
            self.flow_cards.append((i, card, tick))
        return wrap

    # ---------- 配置屏 ----------
    def _setup_section(self, title, sub):
        """配置屏的一节:20px 标题 + 一句说明;内容由调用方往返回控件的布局里加。"""
        sec = QWidget(); sec.setObjectName("rowbg")
        v = QVBoxLayout(sec); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(14)
        hd = QVBoxLayout(); hd.setSpacing(4)
        hd.addWidget(self._trl(title, "h2"))
        if sub:
            hd.addWidget(self._trl(sub, "sub"))
        v.addLayout(hd)
        return sec

    def _build_setup_outline(self):
        """配置屏左侧大纲:处理流程 / 素材 / 输出;点一项滚到那节,完成的打勾,看到哪节高亮哪节。"""
        ol = QFrame(); ol.setObjectName("outline"); ol.setFixedWidth(260)
        v = QVBoxLayout(ol); v.setContentsMargins(20, 28, 20, 20); v.setSpacing(4)
        _cap = self._trl("三件事,决定整条处理流程", "sub"); _cap.setWordWrap(True)
        v.addWidget(_cap); v.addSpacing(12)
        self._outline_rows = []
        for i, title in enumerate(["处理流程", "素材", "输出"]):
            row = ClickFrame(); row.setObjectName("outrow")
            h = QHBoxLayout(row); h.setContentsMargins(12, 10, 12, 10); h.setSpacing(12)
            badge = QLabel(); badge.setFixedSize(22 + STEP_GAP, 22)
            col = QVBoxLayout(); col.setSpacing(2)
            col.addWidget(self._trl(title, "outtitle"))
            sub = QLabel(""); sub.setObjectName("outsub"); sub.setWordWrap(True)
            col.addWidget(sub)
            h.addWidget(badge, 0, Qt.AlignTop); h.addLayout(col, 1)
            row.clicked.connect(lambda idx=i: self._setup_goto(idx))
            v.addWidget(row); self._outline_rows.append((row, badge, sub))
        v.addStretch(1)
        return ol

    def _setup_goto(self, i):
        secs = getattr(self, "_setup_secs", [])
        if i < len(secs):
            self._setup_scroll.verticalScrollBar().setValue(max(0, secs[i].y() - 8))

    def _material_summary(self):
        """素材一句话摘要:几个母版 / 几个子帧目录 / 几组原始素材;没有就说还没添加。"""
        try:
            mode = getattr(self, "_input_mode", 0)
            if mode == 0:
                n, key = len(self._master_config()), "{n} 个母版"
            elif mode == 1:
                n, key = len(self._reg_config()), "{n} 个子帧目录"
            else:
                raw = self._raw_config()
                n = len(raw.get("lights") or []) if raw.get("device") == "mono" else len(raw.get("nights") or [])
                key = "{n} 组原始素材"
            return t(key).format(n=n) if n else t("还没添加素材")
        except Exception:
            return t("还没添加素材")

    def _sync_setup_outline(self):
        """大纲完成态 + 当前节高亮 + 底栏摘要。"""
        if not hasattr(self, "_outline_rows"):
            return
        p = self.theme
        sb = self._setup_scroll.verticalScrollBar(); y = sb.value()
        cur = 0
        for i, s in enumerate(self._setup_secs):
            if s.y() <= y + 80:
                cur = i
        if sb.maximum() > 0 and y >= sb.maximum() - 4:
            cur = len(self._setup_secs) - 1
        flow_label = t(self.FLOWS[getattr(self, "flow_idx", 0)][1])
        mat = self._material_summary()
        outd = (self.ed_exportdir.text() or "").strip().replace("\\", "/")
        done = [True, self._setup_ready(), bool(outd)]
        _fm = self._outline_rows[2][2].fontMetrics()
        subs = [flow_label, mat, _fm.elidedText(outd, Qt.ElideMiddle, 150) if outd else t("导出时再选")]
        self._outline_rows[2][2].setWordWrap(False)        # 路径只占一行(中间省略),别在斜杠处折行
        for i, (row, badge, sub) in enumerate(self._outline_rows):
            st = "done" if done[i] else ("cur" if i == cur else "todo")
            badge.setPixmap(_step_badge(st, i + 1, p, d=22).pixmap(QSize(22 + STEP_GAP, 22)))
            sub.setText(subs[i])
            on = (i == cur)
            if row.property("cur") != on:
                row.setProperty("cur", on); row.style().unpolish(row); row.style().polish(row)
        dev = {"osc": "彩色相机", "mono": "黑白相机", "seestar": "Seestar", "dwarf": "DWARF"}.get(
            getattr(self, "_stack_device", "osc"), "")
        self.lbl_setup_summary.setText(" · ".join(x for x in (mat, t(dev), flow_label) if x))

    def _restyle_source(self):
        """「素材」节:原给素材卡的内容搬出来;相机 / 素材状态改成并排的两组分段控件,素材行放进卡片。"""
        gin_body = self._gin.layout().itemAt(1).widget()
        gin_body.setParent(None)
        vi = gin_body.layout(); vi.setContentsMargins(0, 0, 0, 0); vi.setSpacing(12)
        devrow = self.dev_btns["osc"].parentWidget()
        mode_bar = self.in_mode_btns[0].parentWidget()
        top = QWidget(); top.setObjectName("rowbg")
        th = QHBoxLayout(top); th.setContentsMargins(0, 0, 0, 0); th.setSpacing(24)
        for title, btns, is_mode in (("相机", list(self.dev_btns.values()), False),
                                     ("素材状态", list(self.in_mode_btns), True)):
            col = QVBoxLayout(); col.setSpacing(8)
            col.addWidget(self._trl(title, "sub"))
            box = QFrame(); box.setObjectName("segbox")
            bh = QHBoxLayout(box); bh.setContentsMargins(2, 2, 2, 2); bh.setSpacing(2)
            for b in btns:
                bh.addWidget(b)
            if is_mode:                            # 滑动药丸跟着按钮搬进分段框(坐标系随父控件)
                self.mode_ind.setParent(box); self.mode_ind._radius = 4; self.mode_ind.lower()
            col.addWidget(box, 0, Qt.AlignLeft)
            th.addLayout(col)
        th.addStretch(1)
        vi.insertWidget(vi.indexOf(devrow), top)
        devrow.hide(); mode_bar.hide()
        self.exportdir_row.setParent(None)         # 挪到「输出」节
        for pg in (self.pg_master, self.pg_reg, self.pg_raw):
            pg.setObjectName("srccard"); pg.setAttribute(Qt.WA_StyledBackground, True)
            pg.layout().setContentsMargins(14, 12, 14, 12)
        return gin_body

    # ---------- 导出屏 ----------
    def _export_option(self, chk, title, use, extra=None):
        """导出选项卡:勾选框 + 名称 / 用途 +(可选)右侧实测大小;点整张卡切换勾选。"""
        card = ClickFrame(); card.setObjectName("optcard")
        h = QHBoxLayout(card); h.setContentsMargins(12, 12, 12, 12); h.setSpacing(12)
        chk.setText(""); h.addWidget(chk, 0, Qt.AlignTop)
        col = QVBoxLayout(); col.setSpacing(2)
        col.addWidget(self._trl(title, "opttitle")); col.addWidget(self._trl(use, "sub"))
        if extra is not None:
            col.addWidget(extra)
        h.addLayout(col, 1)
        size = QLabel(""); size.setObjectName("optsize"); h.addWidget(size, 0, Qt.AlignTop)

        def _sync(_on=None, c=card, k=chk):
            on = k.isChecked()
            if c.property("on") != on:
                c.setProperty("on", on); c.style().unpolish(c); c.style().polish(c)
            self._update_export_btn()
        chk.toggled.connect(_sync)
        card.clicked.connect(lambda k=chk: k.setChecked(not k.isChecked()))
        QTimer.singleShot(0, _sync)
        return card, size

    def _build_export_aside(self):
        """导出屏右栏。原导出面板(export_panel)改作容器:显隐逻辑不变(有成片才出现)。"""
        aside = QFrame(); aside.setObjectName("reviewaside"); aside.setFixedWidth(420)
        av = QVBoxLayout(aside); av.setContentsMargins(0, 0, 0, 0); av.setSpacing(0)
        body = QWidget(); body.setObjectName("rowbg")
        bv = QVBoxLayout(body); bv.setContentsMargins(20, 24, 20, 24); bv.setSpacing(22)
        self.lbl_export_empty = self._trl("成片就绪后,在此选择格式并导出(先到「处理」跑完流程)。", "lead")
        self.lbl_export_empty.setWordWrap(True)
        bv.addWidget(self.lbl_export_empty)
        # 旧面板:摘空旧布局(控件保留),换成分节布局
        ep = self.export_panel
        _ol = ep.layout(); _old = []
        while _ol.count():
            it = _ol.takeAt(0)
            if it.widget() is not None:
                _old.append(it.widget())
        QWidget().setLayout(_ol)
        ep.setObjectName("exportbox")
        ev = QVBoxLayout(ep); ev.setContentsMargins(0, 0, 0, 0); ev.setSpacing(22)

        def _sec(title):
            w = QWidget(); w.setObjectName("rowbg")
            v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(10)
            v.addWidget(self._trl(title, "secthead"))
            ev.addWidget(w)
            return v
        s1 = _sec("成片格式")
        c_x, self.lbl_xisf_size = self._export_option(self.chk_xisf, "XISF", "原始位深,以后还能在 PixInsight 里接着调")
        jq = QWidget(); jq.setObjectName("rowbg")
        jqh = QHBoxLayout(jq); jqh.setContentsMargins(0, 6, 0, 0); jqh.setSpacing(8)
        for _w in (self.sl_jpgq, self.lbl_jpgq):
            _w.setParent(None)
        jqh.addWidget(self._trl("质量", "sub")); jqh.addWidget(self.sl_jpgq, 1); jqh.addWidget(self.lbl_jpgq)
        self.sl_jpgq.setMaximumWidth(16777215)
        self.chk_jpg.toggled.connect(jq.setEnabled); jq.setEnabled(self.chk_jpg.isChecked())
        c_j, _ = self._export_option(self.chk_jpg, "JPG", "分享和发图用", extra=jq)
        c_p, _ = self._export_option(self.chk_png, "PNG", "无损,交给其他软件继续修")
        for c in (c_x, c_j, c_p):
            s1.addWidget(c)
        s2 = _sec("附件")
        for chk, title, use in ((self.chk_starless, "去星图", "JPG · 做海报或三维建模的星云层"),
                                (self.chk_export_stars, "星点层", "PNG · 单独叠回星点"),
                                (self.chk_annotate, "天体标注", "TXT · 画面里每个天体的名字和位置")):
            s2.addWidget(self._export_option(chk, title, use)[0])
        s3 = _sec("保存到")
        dr = QHBoxLayout(); dr.setSpacing(8)
        self.ed_export_dir2 = QLineEdit(self.ed_exportdir.text())
        self.ed_export_dir2.setPlaceholderText(self.ed_exportdir.placeholderText())
        _sync_lock = {"on": False}

        def _mirror(src, dst):
            if _sync_lock["on"]:
                return
            _sync_lock["on"] = True; dst.setText(src.text()); _sync_lock["on"] = False
        self.ed_exportdir.textChanged.connect(lambda _t: _mirror(self.ed_exportdir, self.ed_export_dir2))
        self.ed_export_dir2.textChanged.connect(lambda _t: _mirror(self.ed_export_dir2, self.ed_exportdir))
        self.ed_export_dir2.editingFinished.connect(lambda: (self._save_export_dir(), self._refresh_export_meta()))
        pick = QPushButton(); pick.setCursor(Qt.PointingHandCursor); self._tr(pick, "浏览…")
        pick.clicked.connect(lambda: (self._pick_dir(self.ed_exportdir), self._save_export_dir(),
                                      self._refresh_export_meta()))
        dr.addWidget(self.ed_export_dir2, 1); dr.addWidget(pick, 0)
        s3.addLayout(dr)
        self.lbl_export_fname = QLabel(""); self.lbl_export_fname.setObjectName("sub"); self.lbl_export_fname.setWordWrap(True)
        s3.addWidget(self.lbl_export_fname)
        _od = QPushButton(); _od.setObjectName("linkbtn"); _od.setCursor(Qt.PointingHandCursor)
        self._tr(_od, "打开导出文件夹"); _od.clicked.connect(self._open_export_dir)
        s3.addWidget(_od, 0, Qt.AlignLeft)
        s4 = _sec("之前导出过")
        self._export_hist = QVBoxLayout(); self._export_hist.setSpacing(0)
        s4.addLayout(self._export_hist)
        for w in _old:                              # 旧头条 / 旧按钮排:不再显示
            w.hide()
        self.btn_show.hide()
        bv.addWidget(ep)
        bv.addStretch(1)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); sc.setWidget(body)
        av.addWidget(sc, 1)
        foot = QFrame(); foot.setObjectName("asidefoot")
        fv = QVBoxLayout(foot); fv.setContentsMargins(20, 14, 20, 14); fv.setSpacing(8)
        self.btn_export.setParent(None); self.btn_export.setMinimumHeight(42)
        fv.addWidget(self.btn_export)
        _note = self._trl("导完会自动释放 PixInsight 占用的内存", "sub"); _note.setAlignment(Qt.AlignCenter)
        fv.addWidget(_note)
        av.addWidget(foot, 0)
        foot.setVisible(not ep.isHidden())
        self._vw_exp = _VisWatch(lambda: foot.setVisible(not self.export_panel.isHidden()), self)
        ep.installEventFilter(self._vw_exp)
        self._update_export_btn()
        return aside

    def _update_export_btn(self):
        """导出按钮文案 = 这次会写出几个文件(格式 + 附件)。"""
        if not hasattr(self, "btn_export"):
            return
        n = sum(1 for c in (self.chk_xisf, self.chk_jpg, self.chk_png, self.chk_starless,
                            self.chk_export_stars, self.chk_annotate) if c.isChecked())
        self.btn_export.setText(t("导出 {n} 个文件").format(n=n))
        self.btn_export.setEnabled(n > 0 and not getattr(self, "_exporting", False))

    def _open_export_dir(self):
        d = (self.ed_exportdir.text() or "").strip()
        if d and os.path.isdir(d):
            if sys.platform == "win32":
                os.startfile(d)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])

    def _refresh_export_meta(self):
        """导出屏的实测信息:标题 / 流程与评分 / 成片像素 / XISF 大小 / 文件名预览 / 之前导出过(按导出目录里真实文件)。"""
        if not hasattr(self, "lbl_export_title"):
            return
        import re as _re
        import time as _t
        from datetime import datetime as _dt
        has_fin = bool(self._final_png and Path(self._final_png).exists())
        name = (self.ed_project.text() or "").strip() or (self._suggest_export_name() if has_fin else "")
        self.lbl_export_title.setText(name or t("导出"))
        bits = [t(self.FLOWS[getattr(self, "flow_idx", 0)][1])]
        sc = (getattr(self, "_last_scores", None) or {}).get("overall")
        if sc is not None:
            try:
                bits.append(t("AI 评分 {s}").format(s=f"{float(sc):.1f}"))
            except Exception:
                pass
        self.lbl_export_sub.setText(" · ".join(bits))
        dims = ""
        if self._final_png and Path(self._final_png).exists():
            from PyQt5.QtGui import QImageReader
            _sz = QImageReader(self._final_png).size()
            if _sz.isValid():
                dims = f"{_sz.width()} × {_sz.height()}"
        self.lbl_export_dims.setText(dims)
        xs = ""
        if self._final_xisf and Path(self._final_xisf).exists():
            xs = self._fmt_size(Path(self._final_xisf).stat().st_size)
        self.lbl_xisf_size.setText(xs)
        base = self._suggest_export_name()
        stamp = ("_" + _dt.now().strftime("%m%d-%H%M")) if config.get_setting("export_timestamp", True) else ""
        self.lbl_export_fname.setText(t("文件名 {name} · 目标 + 导出时间,不会覆盖旧的").format(name=base + stamp))
        # 之前导出过:导出目录里 <基名>_<月日-时分>.* 按时间戳成组
        hl = self._export_hist
        while hl.count():
            it = hl.takeAt(0)
            if it.widget() is not None:
                it.widget().setParent(None)
        d = (self.ed_exportdir.text() or "").strip()
        groups = {}
        if d and os.path.isdir(d):
            pat = _re.compile(r"^" + _re.escape(base) + r"_(\d{4}-\d{4})")
            try:
                for fn in os.listdir(d):
                    m = pat.match(fn)
                    if m:
                        fp = os.path.join(d, fn)
                        g = groups.setdefault(m.group(0), [])
                        g.append((fp, os.path.getmtime(fp)))
            except OSError:
                pass
        if not groups:
            hl.addWidget(self._trl("还没有导出过", "sub"))
        now = _t.localtime()
        for gname, files in sorted(groups.items(), key=lambda kv: -max(m for _f, m in kv[1]))[:3]:
            mt = max(m for _f, m in files); lt = _t.localtime(mt)
            day = t("今天") if lt[:3] == now[:3] else _t.strftime("%m-%d", lt)
            row = QWidget(); row.setObjectName("rowbg")
            rh = QHBoxLayout(row); rh.setContentsMargins(0, 8, 0, 8); rh.setSpacing(8)
            col = QVBoxLayout(); col.setSpacing(1)
            nm = QLabel(gname); nm.setObjectName("histname")
            wh = QLabel(f"{day} {_t.strftime('%H:%M', lt)} · " + t("{n} 个文件").format(n=len(files)))
            wh.setObjectName("sub")
            col.addWidget(nm); col.addWidget(wh)
            first = sorted(files)[0][0]
            lk = QPushButton(); lk.setObjectName("linkbtn"); lk.setCursor(Qt.PointingHandCursor)
            self._tr(lk, "在文件夹中显示")
            lk.clicked.connect(lambda _c=False, fp=first: subprocess.Popen(["explorer", "/select,", str(Path(fp))])
                               if sys.platform == "win32" else None)
            rh.addLayout(col, 1); rh.addWidget(lk, 0, Qt.AlignVCenter)
            sep = QFrame(); sep.setObjectName("metricsep"); sep.setFixedHeight(1)
            hl.addWidget(sep); hl.addWidget(row)

    def _build_inspector(self):
        """处理屏左侧检查器:标题 + 流程签 | 分组参数(滚动)/ 交互面板 | 吸底运行卡。"""
        insp = QFrame(); insp.setObjectName("inspector"); insp.setFixedWidth(384)
        iv = QVBoxLayout(insp); iv.setContentsMargins(0, 0, 0, 0); iv.setSpacing(0)
        head = QWidget(); head.setObjectName("rowbg")
        hv = QVBoxLayout(head); hv.setContentsMargins(20, 18, 20, 10); hv.setSpacing(4)
        hr = QHBoxLayout(); hr.setSpacing(8)
        self.lbl_insp_title = self._trl("处理参数", "insptitle")
        self.lbl_insp_chip = QLabel(""); self.lbl_insp_chip.setObjectName("inspchip")
        hr.addWidget(self.lbl_insp_title, 0); hr.addStretch(1); hr.addWidget(self.lbl_insp_chip, 0)
        hv.addLayout(hr)
        self.lbl_param_count.setParent(None); self.lbl_param_count.setObjectName("sub")
        hv.addWidget(self.lbl_param_count)
        iv.addWidget(head, 0)
        # 滚动区:参数分组 + 交互面板(二选一显示)
        body = QWidget(); body.setObjectName("rowbg")
        bv = QVBoxLayout(body); bv.setContentsMargins(20, 4, 20, 16); bv.setSpacing(0)
        self._insp_params = QWidget(); self._insp_params.setObjectName("rowbg")
        pv = QVBoxLayout(self._insp_params); pv.setContentsMargins(0, 0, 0, 0); pv.setSpacing(18)
        gp_body = self._gp.layout().itemAt(1).widget()
        items = []
        lay = gp_body.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget() is not None:
                items.append(it.widget())
        key_of = {id(w): k for k, w in self._param_rows.items()}
        SECTIONS = [("运行", ["stop", "stepwise"]),
                    ("拉伸与色彩", ["ghs", "sat", "mancolor", "nbpalette", "palette", "grade", "dust", "dse"]),
                    ("背景", ["zeropi_rgb_adv"]),
                    ("引擎", ["zeropi", "zeropi_rgb", "zeropi_hoo"])]
        placed = set()
        self._insp_sections = []
        for title, keys in SECTIONS:
            sec = QWidget(); sec.setObjectName("rowbg")
            sv = QVBoxLayout(sec); sv.setContentsMargins(0, 0, 0, 0); sv.setSpacing(6)
            sv.addWidget(self._trl(title, "secthead"))
            rows = []
            for k in keys:
                w = self._param_rows.get(k)
                if w is None or id(w) not in {id(x) for x in items}:
                    continue
                sv.addWidget(w); rows.append(w); placed.add(id(w))
            if rows:
                pv.addWidget(sec); self._insp_sections.append((sec, rows))
        rest = QWidget(); rest.setObjectName("rowbg")              # 高级参数 / LRGB 专用(自带折叠头)
        rv = QVBoxLayout(rest); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(7)
        for w in items:
            if id(w) not in placed:
                rv.addWidget(w)
        pv.addWidget(rest)
        # 检查器里的参数行:去掉行底框、左右贴齐分组标题
        for k, w in self._param_rows.items():
            if gp_body.isAncestorOf(w) or self._insp_params.isAncestorOf(w):
                w.setObjectName("insprow")
                if w.layout() is not None:
                    w.layout().setContentsMargins(0, 3, 0, 3)
        for _cb in (self.cb_stop, self.cb_stepwise, self.cb_mancolor, self.cb_nbpalette, self.cb_palette,
                    self.cb_dust, self.cb_grade, self.cb_dse, self.cb_rgbpreset, self.cb_zpreset, self.cb_hoopreset):
            _cb.setMinimumWidth(196); _cb.setMaximumWidth(196)
        for _cb in (self.cb_bgextract, self.cb_rgbreveal, self.cb_glow):
            _cb.setMinimumWidth(196); _cb.setMaximumWidth(196)
            _pc = _cb.parentWidget(); _pc.setMinimumWidth(340)
            _pc.layout().insertStretch(1, 1)
        bv.addWidget(self._insp_params)
        # 交互面板(暂停介入 / 岔口 / 手动调色):从预览卡搬进来,出现时整栏换成它
        self._insp_panels = QWidget(); self._insp_panels.setObjectName("rowbg")
        qv = QVBoxLayout(self._insp_panels); qv.setContentsMargins(0, 0, 0, 0); qv.setSpacing(12)
        self.lbl_col_title.setVisible(False)                       # 检查器标题已写「手动调色」
        for w in (self.pause_panel, self.decide_panel, self.color_panel):
            w.setParent(None); qv.addWidget(w)
        self._regrid_color_panel()
        self._insp_panels.setVisible(False)
        bv.addWidget(self._insp_panels)
        bv.addStretch(1)
        self._insp_scroll = QScrollArea(); self._insp_scroll.setWidgetResizable(True)
        self._insp_scroll.setFrameShape(QFrame.NoFrame)
        self._insp_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._insp_scroll.setWidget(body)
        iv.addWidget(self._insp_scroll, 1)
        self._vw_insp = _VisWatch(self._sync_inspector, self)
        for w in (self.pause_panel, self.decide_panel, self.color_panel):
            w.installEventFilter(self._vw_insp)
        iv.addWidget(self._build_run_card(), 0)
        return insp

    def _regrid_color_panel(self):
        """手动调色面板放进窄栏:底部五个按钮改两行网格;背景读数挪到按钮下面单独一行。"""
        cpv = self.color_panel.layout()
        old = self.btn_col_apply.parentWidget()
        grid = QWidget(); grid.setObjectName("rowbg")
        g = QGridLayout(grid); g.setContentsMargins(0, 4, 0, 0); g.setHorizontalSpacing(8); g.setVerticalSpacing(8)
        g.addWidget(self.btn_col_showmask, 0, 0); g.addWidget(self.btn_col_auto, 0, 1)
        g.addWidget(self.btn_col_reset, 0, 2)
        g.addWidget(self.btn_col_skip, 1, 0); g.addWidget(self.btn_col_apply, 1, 1, 1, 2)
        cpv.insertWidget(cpv.indexOf(old), grid); old.hide()
        prow = self.btn_col_pick.parentWidget()
        self.lbl_col_bg.setParent(None); self.lbl_col_bg.setWordWrap(True)
        cpv.insertWidget(cpv.indexOf(prow) + 1, self.lbl_col_bg)

    def _build_run_card(self):
        """检查器底部的运行卡:进度(阶段 · 预计剩余 · 进度条)+ 开始 / 暂停介入 / 中止。"""
        wrap = QWidget(); wrap.setObjectName("rowbg")
        wv = QVBoxLayout(wrap); wv.setContentsMargins(12, 0, 12, 12)
        card = QFrame(); card.setObjectName("runcard")
        cv = QVBoxLayout(card); cv.setContentsMargins(14, 12, 14, 12); cv.setSpacing(10)
        # 进度块:原 gprog(一行横排)改成「阶段 … 剩余」+ 下面一条进度
        _ol = self.gprog.layout()                          # 卸掉旧横排布局:先把控件摘出来(不删控件),
        while _ol.count():                                 #   再把空布局挪到临时控件上随它销毁
            _ol.takeAt(0)
        QWidget().setLayout(_ol)
        self.gprog.setObjectName("runprog")
        gv = QVBoxLayout(self.gprog); gv.setContentsMargins(0, 0, 0, 0); gv.setSpacing(8)
        top = QHBoxLayout(); top.setSpacing(6)
        top.addWidget(self.prog_dot, 0); top.addWidget(self.lbl_prog_stage, 0); top.addStretch(1)
        top.addWidget(self.lbl_eta, 0)
        gv.addLayout(top); self.bar.setFixedHeight(6); gv.addWidget(self.bar)
        self.gprog.setParent(None); cv.addWidget(self.gprog)
        br = QHBoxLayout(); br.setSpacing(8)
        for b, st in ((self.btn_run, 1), (self.btn_pause, 1), (self.btn_abort, 0)):
            b.setParent(None); b.setCursor(Qt.PointingHandCursor); br.addWidget(b, st)
        cv.addLayout(br)
        wv.addWidget(card)
        return wrap

    def _build_log_drawer(self):
        """处理屏右下的运行日志抽屉:标题 + 收起/展开;日志本体在深底上。"""
        dr = QFrame(); dr.setObjectName("logdrawer")
        dv = QVBoxLayout(dr); dv.setContentsMargins(0, 0, 0, 0); dv.setSpacing(0)
        hd = QWidget(); hd.setObjectName("rowbg"); hd.setFixedHeight(36)
        hh = QHBoxLayout(hd); hh.setContentsMargins(16, 0, 16, 0); hh.setSpacing(8)
        hh.addWidget(self._trl("运行日志", "drawertitle"), 0); hh.addStretch(1)
        self.btn_log_toggle = QPushButton(); self.btn_log_toggle.setObjectName("linkbtn")
        self.btn_log_toggle.setCursor(Qt.PointingHandCursor)
        self._tr(self.btn_log_toggle, "收起")
        hh.addWidget(self.btn_log_toggle, 0)
        dv.addWidget(hd)
        self.log.setParent(None); self.log.setObjectName("drawerlog")
        self.log.setMinimumHeight(150); self.log.setMaximumHeight(150)
        dv.addWidget(self.log)

        def _toggle():
            on = self.log.isHidden()
            self.log.setVisible(on)
            self._tr_set(self.btn_log_toggle, "收起" if on else "展开")
            if on:
                QTimer.singleShot(0, self._sync_caret)
        self.btn_log_toggle.clicked.connect(_toggle)
        return dr

    def _build_review_aside(self):
        """审阅屏右侧栏:空态说明 / 评审卡 / 实测指标 / 继续调整(滚动)+ 底栏「重新评分 / 下一步:导出」。"""
        aside = QFrame(); aside.setObjectName("reviewaside"); aside.setFixedWidth(420)
        av = QVBoxLayout(aside); av.setContentsMargins(0, 0, 0, 0); av.setSpacing(0)
        body = QWidget(); body.setObjectName("rowbg")
        bv = QVBoxLayout(body); bv.setContentsMargins(16, 16, 16, 16); bv.setSpacing(12)
        self.lbl_review_empty = self._trl("还没有成片。到「处理」跑完流程后,评审与实测指标会出现在这里。", "lead")
        self.lbl_review_empty.setWordWrap(True)
        bv.addWidget(self.lbl_review_empty)
        bv.addWidget(self._build_score_panels(), 0)
        # 结果卡(评分细节 / 需你决定 / 跟 AI 说 / 修复工具)→ 改名「继续调整」;导出与重评挪到底栏
        self._tr_set(self.gresult.findChild(QLabel, "striptitle"), "继续调整")
        self.btn_to_export.setParent(None); self.btn_rescore.setParent(None)
        bv.addWidget(self.gresult, 0)
        bv.addStretch(1)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); sc.setWidget(body)
        av.addWidget(sc, 1)
        foot = QFrame(); foot.setObjectName("asidefoot")
        fh = QHBoxLayout(foot); fh.setContentsMargins(16, 12, 16, 12); fh.setSpacing(8)
        fh.addWidget(self.btn_rescore, 0); fh.addWidget(self.btn_to_export, 1)
        av.addWidget(foot, 0)
        foot.setVisible(not self.gresult.isHidden())
        self._vw_rev = _VisWatch(lambda: foot.setVisible(not self.gresult.isHidden()), self)
        self.gresult.installEventFilter(self._vw_rev)
        return aside

    def _tr_set(self, w, zh, setter="setText"):
        """改一个已登记 i18n 控件的源串(没登记就登记),免得切语言时被旧源串改回去、登记表也不重复增长。"""
        for i, (ww, _z, st) in enumerate(self._i18n_widgets):
            if ww is w and st == setter:
                self._i18n_widgets[i] = (w, zh, setter)
                break
        else:
            self._i18n_widgets.append((w, zh, setter))
        getattr(w, setter)(t(zh))

    def _sync_inspector(self):
        """暂停 / 岔口 / 调色面板任一出现 → 检查器整栏换成面板(处理中参数已不起作用);都收起 → 换回参数。"""
        if not hasattr(self, "_insp_params"):
            return
        col, pau, dec = (not self.color_panel.isHidden(), not self.pause_panel.isHidden(),
                         not self.decide_panel.isHidden())
        busy = col or pau or dec
        self._insp_params.setVisible(not busy)
        self._insp_panels.setVisible(busy)
        self.lbl_insp_chip.setVisible(not busy); self.lbl_param_count.setVisible(not busy)
        self._tr_set(self.lbl_insp_title, "手动调色" if col else "已暂停" if pau else "选方向" if dec else "处理参数")
        if busy:
            self._insp_scroll.verticalScrollBar().setValue(0)

    def _build_score_panels(self):
        """审阅屏双面板:成片评审(LLM 大分 + 3 条 green→blue 评分条)+ 实测指标(numpy,数值蓝)。"""
        wrap = QWidget(); wrap.setObjectName("rowbg")
        g = QVBoxLayout(wrap); g.setContentsMargins(0, 0, 0, 0); g.setSpacing(12)
        # 评审 panel
        pv = QFrame(); pv.setObjectName("panel")
        pvl = QVBoxLayout(pv); pvl.setContentsMargins(16, 16, 16, 16); pvl.setSpacing(14)
        h1 = QHBoxLayout(); t1 = self._trl("成片评审", "paneltitle")
        v1 = self._trl("LLM · 同视场对照", "panelvia")
        h1.addWidget(t1, 0); h1.addStretch(1); h1.addWidget(v1, 0); pvl.addLayout(h1)
        sw = QHBoxLayout(); sw.setSpacing(16)
        self.lbl_bigscore = QLabel("—"); self.lbl_bigscore.setObjectName("bigscore")
        sw.addWidget(self.lbl_bigscore, 0, Qt.AlignVCenter)
        bars = QVBoxLayout(); bars.setSpacing(8)
        self.score_bars = {}
        for key, label in (("background", "背景"), ("star_color", "星点色"), ("core", "核心")):
            row = QHBoxLayout(); row.setSpacing(9)
            lab = self._trl(label, "barlabel"); lab.setFixedWidth(72)  # 72:容得下英文 Background/Star color 不截断
            pb = QProgressBar(); pb.setObjectName("scoreprog"); pb.setRange(0, 100); pb.setValue(0)
            pb.setTextVisible(False); pb.setFixedHeight(4)
            val = QLabel("—"); val.setObjectName("barval"); val.setFixedWidth(28)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(lab, 0); row.addWidget(pb, 1); row.addWidget(val, 0)
            bars.addLayout(row); self.score_bars[key] = (pb, val)
        sw.addLayout(bars, 1); pvl.addLayout(sw)
        self.lbl_verdict_comment = QLabel(""); self.lbl_verdict_comment.setObjectName("lead")
        self.lbl_verdict_comment.setWordWrap(True); self.lbl_verdict_comment.setVisible(False)
        pvl.addWidget(self.lbl_verdict_comment)
        g.addWidget(pv)
        # 实测指标 panel
        pm = QFrame(); pm.setObjectName("panel")
        pml = QVBoxLayout(pm); pml.setContentsMargins(16, 14, 16, 8); pml.setSpacing(0)
        h2 = QHBoxLayout(); t2 = self._trl("实测指标", "paneltitle")
        v2 = self._trl("确定性 · numpy", "panelvia")
        h2.addWidget(t2, 0); h2.addStretch(1); h2.addWidget(v2, 0); pml.addLayout(h2); pml.addSpacing(8)
        self.metric_rows = {}
        for key, label in (("s_star", "星点饱和度"), ("bg_s", "背景中性"), ("bg_level", "背景亮度"),
                           ("bg_nonflat", "背景平整")):
            sep = QFrame(); sep.setObjectName("metricsep"); sep.setFixedHeight(1); pml.addWidget(sep)
            roww = QWidget(); roww.setObjectName("rowbg")
            row = QHBoxLayout(roww); row.setContentsMargins(0, 9, 0, 9); row.setSpacing(10)
            col = QVBoxLayout(); col.setSpacing(2)
            klab = self._trl(label, "metrickey")
            ref = QLabel(""); ref.setObjectName("metricref"); ref.setWordWrap(True)   # 参考说明(原来的小标签)
            col.addWidget(klab); col.addWidget(ref)
            val = QLabel("—"); val.setObjectName("metricval"); val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pill = QLabel(""); pill.setObjectName("pillok"); pill.setVisible(False)
            row.addLayout(col, 1); row.addWidget(val, 0, Qt.AlignVCenter); row.addWidget(pill, 0, Qt.AlignVCenter)
            pml.addWidget(roww); self.metric_rows[key] = (pill, val, ref)
        g.addWidget(pm)
        self.score_panels = wrap
        wrap.setVisible(False)      # 有评分/指标才显示(_show_scores 控制)
        if hasattr(self, "score_bar"):
            self.score_bar.setVisible(False)   # 竖向评分条已被双面板取代
        return wrap

    def _pick_flow(self, idx):
        self._select_flow(idx)          # 复用原逻辑(设 flow_idx + 参数显隐 + 交棒点等)
        self._sync_flow_cards()

    def _sync_flow_cards(self):
        if not hasattr(self, "flow_cards"):
            return
        cur = getattr(self, "flow_idx", 0)
        for i, card, tick in self.flow_cards:
            sel = (i == cur)
            card.setProperty("sel", "true" if sel else "false")
            card.style().unpolish(card); card.style().polish(card)
            tick.setVisible(sel)

    def _mount_preview(self, target_layout):
        """把唯一的预览卡 pcard 移进目标取景器 slot(处理/审阅共用一个 pcard)。"""
        if self._pcard.parentWidget() is not None:
            self._pcard.setParent(None)
        target_layout.addWidget(self._pcard)
        self._pcard.show()

    def _fade_screen(self, w):
        """屏切换淡入(平滑无过冲)。"""
        try:
            eff = QGraphicsOpacityEffect(w); eff.setOpacity(0.0); w.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", self); a.setDuration(300)
            a.setStartValue(0.0); a.setEndValue(1.0); a.setEasingCurve(QEasingCurve.OutCubic)
            a.finished.connect(lambda: w.setGraphicsEffect(None))
            self._anims.append(a); a.start()
        except Exception:
            pass

    def _set_lang(self, code):
        """界面语言开关 → 落配置 ui.lang(评委 critic + UI 文案一起跟随)并即时重刷界面。"""
        _i18n_set_lang(code)                    # 写 config ui.lang(load→改→save,不冲其它配置)
        b = self.lang_btns.get(code)
        if b:
            b.setChecked(True)
        self._retranslate()

    def _tr(self, w, zh, setter="setText"):
        """登记一个可翻译控件并即时置文案(源串即键;英文查 i18n.ZH_EN,未收录回落中文)。"""
        self._i18n_widgets.append((w, zh, setter))
        try:
            getattr(w, setter)(t(zh))
        except Exception:
            pass
        return w

    def _trl(self, zh, obj=None, cls=None):
        """便捷:造一个已登记的可翻译 QLabel(可选 objectName)。"""
        w = (cls or QLabel)()
        if obj:
            w.setObjectName(obj)
        return self._tr(w, zh)

    def _retranslate(self):
        """语言切换后重刷所有已登记控件 + 组合串 nav;宽度变了重排指示器。"""
        for w, zh, setter in getattr(self, "_i18n_widgets", []):
            try:
                getattr(w, setter)(t(zh))
            except Exception:
                pass
        for _cb0 in getattr(self, "_i18n_callbacks", []):   # 格式化拼接文案(如折叠小节标题)重刷
            try: _cb0()
            except Exception: pass
        for b, ix, name in getattr(self, "_nav_meta", []):
            try:
                b.setText(f"{ix} · {t(name)}")
            except Exception:
                pass
        if hasattr(self, "lbl_saved"):     # 动态存档标(未/已保存)按当前状态重译
            self.lbl_saved.setText(t("已保存" if not getattr(self, "_proj_dirty", True) else "未保存"))
        if hasattr(self, "_home_grid"):    # 项目库卡片(含「新建项目」)随语言重建
            self._refresh_home()
        if hasattr(self, "road_rows"):     # 流程路线卡 + 阶段时间线随语言重绘(_paint_phases 末尾会画路线卡)
            try: self._paint_phases()
            except Exception: pass
        # 【通用兜底重译(修没经 _tr 注册的普通 t() 控件/下拉项)】遍历所有子控件:把文案反查回中文源(_to_zh)
        #   再按当前语言重译(t)。已注册的会被重复设一次(无害);动态拼接文案(含数字/路径/纯数据)反查不中→原样不动。
        #   放在 nav/saved 等专项之后,避免覆盖它们的格式化文案。
        for _cls in (QLabel, QCheckBox, QPushButton, QToolButton):
            for _w in self.findChildren(_cls):
                try:
                    _s = _w.text()
                    if _s:
                        _w.setText(t(_to_zh(_s)))
                except Exception:
                    pass
        for _cb in self.findChildren(QComboBox):
            try:
                _ix = _cb.currentIndex(); _cb.blockSignals(True)
                for _i in range(_cb.count()):
                    _cb.setItemText(_i, t(_to_zh(_cb.itemText(_i))))
                _cb.setCurrentIndex(_ix); _cb.blockSignals(False)
            except Exception:
                pass
        for _le in self.findChildren(QLineEdit):       # 输入框占位符(setPlaceholderText,遍历 setText 不含)
            try:
                _ph = _le.placeholderText()
                if _ph:
                    _le.setPlaceholderText(t(_to_zh(_ph)))
            except Exception:
                pass
        try:                               # 窗口标题(启动设一次,切换时重刷)
            self.setWindowTitle(t("TTAstroPiLot · 深空自动后期"))
        except Exception:
            pass
        if hasattr(self, "btn_clean"):            # 动态拼接文案("清理中间文件(N GB)")单独重渲(遍历反查不中)
            try:
                self._set_clean_size(getattr(self, "_run_size_total", 0))
            except Exception:
                pass
        if hasattr(self, "log"):                  # 日志占位符重刷;若正文仍是初始「就绪」提示(未跑过)则一并重译
            try:
                self.log.setPlaceholderText(t("就绪。选择流程与输入后点击「开始处理」。"))
                _cur = self.log.toPlainText().strip()
                if _to_zh(_cur) == "就绪。选择流程与输入后点击「开始处理」。":
                    self.log.setPlainText(t("就绪。选择流程与输入后点击「开始处理」。"))
            except Exception:
                pass
        self._fit_projname()                      # 占位符换了语言 → 项目名框重定宽
        self._refresh_runner()                    # PixInsight 状态字(动态文案,遍历反查不一定中)
        for _fn in ("_sync_setup_outline", "_refresh_export_meta", "_update_export_btn"):   # 配置大纲 / 导出信息(拼接文案)
            try:
                getattr(self, _fn)()
            except Exception:
                pass
        QTimer.singleShot(0, self._fit_header)    # 英文更长 → 顶栏可能要收起一级
        QTimer.singleShot(0, self._sync_indicators)

    def _mark_dirty(self):
        self._proj_dirty = True
        if hasattr(self, "lbl_saved"):
            self.lbl_saved.setText(t("未保存"))
            for _w in (self.lbl_saved, getattr(self, "lbl_saved_dot", None)):
                if _w is not None:
                    _w.setProperty("dirty", True); _w.style().unpolish(_w); _w.style().polish(_w)

    def _mark_saved(self):
        self._proj_dirty = False
        if hasattr(self, "lbl_saved"):
            self.lbl_saved.setText(t("已保存"))
            for _w in (self.lbl_saved, getattr(self, "lbl_saved_dot", None)):
                if _w is not None:
                    _w.setProperty("dirty", False); _w.style().unpolish(_w); _w.style().polish(_w)

    def _autosave(self):
        """定时 / 关键节点**静默自动保存**(用户 2026-09-07:常忘手动保存)。
        只在有改动时存;处理进行中不存(避免与运行态争用,完成后 _finished 会存);
        空白新工程(没成片也没存过)不建文件;从未存过但已出成片 → 自动挑路径(上次保存目录/默认库)。"""
        if not getattr(self, "_proj_dirty", False):
            return
        if getattr(self, "thread", None) is not None:
            return
        has_result = bool(self._final_png and Path(str(self._final_png)).exists())
        if not self._proj_path and not has_result:
            return
        try:
            if not self._proj_path:
                name = (self.ed_project.text() or "").strip() or (self._guess_target() or "未命名项目")
                safe = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "未命名项目"
                # 先放项目自己的目录(_project_home);以前直接放「上次保存的目录」= 上一个目标的文件夹
                _home = self._project_home()
                _dir = _home if (_home and os.path.isdir(_home)) else self._last_project_dir()
                _cand = str(Path(_dir) / f"{safe}.ttproj")
                if os.path.exists(_cand):              # 同名已存在 → 加时间戳,别覆盖别的工程
                    _cand = str(Path(_dir) / f"{safe}_{time.strftime('%m%d_%H%M')}.ttproj")
                self._proj_path = _cand
            self._save_project(autosave=True)          # 有 _proj_path → 静默覆盖,不弹窗
        except Exception as e:
            self._append(f"[项目] 自动保存失败(忽略):{e}")

    def closeEvent(self, event):
        """关窗前自动保存(用户 2026-09-07:常忘手动存,别在关闭时丢进度)。失败也不拦关闭。"""
        try:
            self._autosave()
        except Exception:
            pass
        try:
            super().closeEvent(event)
        except Exception:
            event.accept()

    def _projects_dir(self):
        return config.PIPELINE_DIR / "_projects"

    def _last_project_dir(self):
        """上次保存工程所在的目录(用户 2026-09-07:新建保存默认停这、别落软件安装目录)。
        取不到 → 最近一个工程的目录 → 再兜底软件默认库目录。"""
        try:
            d = (config.get_setting("projects.last_dir") or "").strip()
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
        for p in self._recent_paths():          # 没存过 last_dir → 用最近工程的目录
            try:
                pd = os.path.dirname(p)
                if pd and os.path.isdir(pd):
                    return pd
            except Exception:
                pass
        return str(self._projects_dir())

    def _recent_paths(self):
        """config 里记录的最近工程路径(可落在任意磁盘位置)。"""
        try:
            v = config.get_setting("projects.recent") or []
            return [str(x) for x in v] if isinstance(v, list) else []
        except Exception:
            return []

    def _add_recent(self, path):
        """把一个 .ttproj 路径置顶进最近列表(去重、限 12 条)。config.save_settings 整体覆盖 → load→改→save。"""
        try:
            path = str(Path(path).resolve())
            s = config.load_settings()
            if not isinstance(s.get("projects"), dict):
                s["projects"] = {}
            rec = [str(x) for x in (s["projects"].get("recent") or []) if str(x) != path]
            s["projects"]["recent"] = [path] + rec[:11]
            config.save_settings(s)
        except Exception:
            pass

    def _list_projects(self):
        """项目库卡片来源:最近列表(任意位置)∪ 旧 _projects 目录,存在的去重,按修改时间倒序。"""
        seen = {}
        for sp in self._recent_paths():
            p = Path(sp)
            if p.suffix == ".ttproj" and p.exists():
                seen[str(p.resolve())] = p
        d = self._projects_dir()
        if d.exists():
            try:
                for p in d.glob("*.ttproj"):
                    seen.setdefault(str(p.resolve()), p)
            except OSError:
                pass
        try:
            return sorted(seen.values(), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return list(seen.values())

    def _build_home(self):
        """项目库屏(精修 2026-10-10,设计稿 Library 板):
        标题 + 数量/最近 | 搜索 · 流程筛选 · 打开工程文件 · 新建项目;「继续上次」大卡;自适应列数的卡片网格。"""
        page = QWidget(); page.setObjectName("screen")
        v = QVBoxLayout(page); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        body = QWidget(); body.setObjectName("rowbg")
        bv = QVBoxLayout(body); bv.setContentsMargins(32, 28, 32, 28); bv.setSpacing(24)
        head = QHBoxLayout(); head.setSpacing(8)
        col = QVBoxLayout(); col.setSpacing(4)
        col.addWidget(self._trl("项目", "h1"))
        self.lbl_home_sub = QLabel(""); self.lbl_home_sub.setObjectName("sub")
        col.addWidget(self.lbl_home_sub)
        head.addLayout(col, 1)
        self.ed_home_search = QLineEdit(); self.ed_home_search.setObjectName("searchbox")
        self.ed_home_search.setFixedWidth(200)
        self._tr(self.ed_home_search, "搜索目标名", "setPlaceholderText")
        self.ed_home_search.setClearButtonEnabled(True)
        self.ed_home_search.textChanged.connect(lambda _t: self._refresh_home())
        segbox = QFrame(); segbox.setObjectName("segbox")
        sh = QHBoxLayout(segbox); sh.setContentsMargins(2, 2, 2, 2); sh.setSpacing(2)
        self._home_filter = "all"; self._home_filter_grp = QButtonGroup(self)
        for key, lab in (("all", "全部"), ("rgb", "纯 RGB"), ("nb", "含窄带")):
            b = QPushButton(); b.setObjectName("segin"); b.setCheckable(True); b.setChecked(key == "all")
            b.setCursor(Qt.PointingHandCursor); self._tr(b, lab)
            b.clicked.connect(lambda _c=False, k=key: (setattr(self, "_home_filter", k), self._refresh_home()))
            self._home_filter_grp.addButton(b); sh.addWidget(b)
        openb = QPushButton(); openb.setCursor(Qt.PointingHandCursor); self._tr(openb, "打开工程文件")
        openb.clicked.connect(self._open_project_dialog)
        newb = QPushButton(); newb.setObjectName("primary"); newb.setCursor(Qt.PointingHandCursor)
        self._tr(newb, "＋ 新建项目")
        newb.clicked.connect(self._new_project)
        for w in (self.ed_home_search, segbox, openb, newb):
            head.addWidget(w, 0, Qt.AlignBottom)
        bv.addLayout(head)
        self._home_hero = QWidget(); self._home_hero.setObjectName("rowbg")
        QVBoxLayout(self._home_hero).setContentsMargins(0, 0, 0, 0)
        bv.addWidget(self._home_hero)
        self._home_gridw = QWidget(); self._home_gridw.setObjectName("rowbg")
        self._home_grid = QGridLayout(self._home_gridw)
        self._home_grid.setContentsMargins(0, 0, 0, 0); self._home_grid.setSpacing(16)
        bv.addWidget(self._home_gridw)
        self.lbl_home_empty = self._trl("没有符合条件的项目", "lead"); self.lbl_home_empty.setVisible(False)
        bv.addWidget(self.lbl_home_empty)
        bv.addStretch(1)
        sc = self._screen_scroll(body); sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.addWidget(sc, 1)
        self._home_cols = 0; self._home_thumb_cache = {}
        self._rw_home = _ResizeWatch(self._relayout_home, self)
        sc.viewport().installEventFilter(self._rw_home)
        self._home_scroll = sc
        self._refresh_home()
        return page

    def _home_entries(self):
        """读工程文件 → [(路径, 元数据, 摘要)];摘要只取文件里真有的字段(名字 / 流程 / 相机 / 保存时间 / 有没有成片)。"""
        import json as _json
        import time as _t
        flow_name = dict(self.FLOWS)
        dev_name = {"osc": "彩色相机", "mono": "黑白相机", "seestar": "Seestar", "dwarf": "DWARF"}
        out = []
        for p in self._list_projects():
            try:
                meta = _json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
            st = meta.get("state") or {}
            flow = meta.get("flow") or st.get("flow") or "pure_rgb"; flow = FLOW_MIGRATE.get(flow, flow)
            res = st.get("result") or {}
            fin = (res.get("final_png") or "") if isinstance(res, dict) else ""
            try:
                mt = p.stat().st_mtime
            except OSError:
                mt = 0
            out.append((p, meta, {
                "name": meta.get("name") or p.stem, "flow": flow, "flow_label": flow_name.get(flow, flow),
                "dev": dev_name.get(st.get("device") or "", ""), "mtime": mt,
                "date": _t.strftime("%m-%d", _t.localtime(mt)) if mt else "",
                "has_final": bool(fin) and Path(fin).exists(), "had_final": bool(fin), "search": (meta.get("name") or p.stem) + " "
                + (meta.get("target_type") or "")}))
        return out

    def _home_thumb(self, p, meta):
        """工程缩略图(原图 + 天体位置),按路径 + 修改时间缓存。来源次序沿用:内嵌 base64 → 工程旁 png;不用共享 _run 路径。"""
        try:
            key = (str(p), p.stat().st_mtime)
        except OSError:
            key = (str(p), 0)
        if key in self._home_thumb_cache:
            return self._home_thumb_cache[key]
        pm = QPixmap()
        _b64 = meta.get("thumb_b64") or ""
        if _b64:
            try:
                from PyQt5.QtCore import QByteArray
                pm.loadFromData(QByteArray.fromBase64(_b64.encode("ascii")))
            except Exception:
                pm = QPixmap()
        if pm.isNull():
            tp = (meta.get("thumb") or "").replace("\\", "/")
            if tp and "/_run/" not in tp and Path(tp).exists():   # 跳过共享 _run 路径(老工程串图根源)
                pm = QPixmap(tp)
        val = (pm, _thumb_focus(pm)) if not pm.isNull() else (None, (0.5, 0.5))
        self._home_thumb_cache[key] = val
        return val

    def _refresh_home(self):
        """按搜索 / 筛选重建「继续上次」大卡和卡片网格(列数按可用宽度,见 _relayout_home)。"""
        if not hasattr(self, "_home_grid"):
            return
        import time as _t
        entries = self._home_entries()
        q = (self.ed_home_search.text() or "").strip().lower()
        flt = getattr(self, "_home_filter", "all")
        # 小标题:数量 + 最近处理的是谁、什么时候
        if entries:
            _p0, _m0, s0 = entries[0]
            d0 = _t.localtime(s0["mtime"]); now = _t.localtime()
            days = (_t.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1))
                    - _t.mktime((d0.tm_year, d0.tm_mon, d0.tm_mday, 0, 0, 0, 0, 0, -1))) / 86400
            when = t("今天") if days < 0.5 else t("昨天") if days < 1.5 else s0["date"]
            self.lbl_home_sub.setText(t("{n} 个项目").format(n=len(entries)) + " · "
                                      + t("最近处理 {name}({when})").format(name=s0["name"], when=when))
        else:
            self.lbl_home_sub.setText(t("继续最近的工程,或新建 / 打开一个 .ttproj 工程文件"))
        show = [e for e in entries
                if (not q or q in e[2]["search"].lower())
                and (flt == "all" or (flt == "rgb") == (e[2]["flow"] == "pure_rgb"))]
        hero = show[0] if (show and not q and flt == "all") else None
        # 「继续上次」大卡
        hl = self._home_hero.layout()
        while hl.count():
            it = hl.takeAt(0)
            if it.widget() is not None:
                it.widget().setParent(None)
        self._home_hero.setVisible(hero is not None)
        if hero is not None:
            hl.addWidget(self._make_hero_card(*hero))
        self._home_cards_src = [e for e in show if e is not hero]
        self.lbl_home_empty.setVisible(not show)
        self._home_cols = 0                       # 强制按当前宽度重排
        self._relayout_home()

    def _relayout_home(self):
        """列数 = 可用宽度能放下几张 ≥240px 的卡;卡宽平分整行(不在右边留一块空)。"""
        if not hasattr(self, "_home_scroll"):
            return
        avail = self._home_scroll.viewport().width() - 64
        gap = 16
        cols = max(1, (avail + gap) // (240 + gap))
        cw = int((avail - gap * (cols - 1)) / cols)
        if cols == self._home_cols and abs(cw - getattr(self, "_home_cw", 0)) < 2:
            return
        self._home_cols, self._home_cw = cols, cw
        g = self._home_grid
        while g.count():
            it = g.takeAt(0)
            if it.widget() is not None:
                it.widget().setParent(None)
        for i, e in enumerate(getattr(self, "_home_cards_src", [])):
            g.addWidget(self._make_proj_card(*e, cw), i // cols, i % cols, Qt.AlignTop | Qt.AlignLeft)
        for c in range(cols):
            g.setColumnStretch(c, 1)

    def _make_proj_card(self, p, meta, s, cw):
        th = int(round(cw * 2 / 3))                        # 3:2 缩略图
        card = ClickFrame(); card.setObjectName("projcard"); card.setFixedWidth(cw)
        cl = QVBoxLayout(card); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        thumb = QLabel(); thumb.setFixedSize(cw, th); thumb.setAlignment(Qt.AlignCenter)
        pm, focus = self._home_thumb(p, meta)
        if pm is not None:
            thumb.setPixmap(_cover_crop(pm, cw - 2, th, focus, radius=9, corners="top"))
        else:
            thumb.setObjectName("thumbph"); thumb.setWordWrap(True)
            # 记过成片(文件可能已被清理)≠ 没出过图
            thumb.setText(t("没有缩略图") if s["had_final"] else t("尚未出图 · 点开继续配置"))
            thumb.setStyleSheet(f"background:{self.theme['prevbg']}; color:{self.theme['onmuted']}; "
                                "font-size:12px; border-top-left-radius:9px; border-top-right-radius:9px;")
        cl.addWidget(thumb)
        info = QWidget(); info.setObjectName("rowbg")
        iv = QVBoxLayout(info); iv.setContentsMargins(14, 12, 14, 14); iv.setSpacing(6)
        r1 = QHBoxLayout(); r1.setSpacing(8)
        nm = QLabel(s["name"]); nm.setObjectName("cardname")
        dt = QLabel(s["date"]); dt.setObjectName("carddate")
        r1.addWidget(nm, 1); r1.addWidget(dt, 0)
        iv.addLayout(r1)
        sig = FLOW_SIG.get(s["flow"], "#C6D0DC")
        fl = QLabel(f"<span style='color:{sig}'>●</span>&nbsp;{t(s['flow_label'])}"); fl.setObjectName("cardflow")
        iv.addWidget(fl)
        cm = QLabel(t(s["dev"]) if s["dev"] else ""); cm.setObjectName("cardcam")   # 空也占一行:同排卡片等高
        cm.setMinimumHeight(cm.fontMetrics().height()); iv.addWidget(cm)
        cl.addWidget(info)
        card.clicked.connect(lambda path=str(p): self._open_project(path))
        return card

    def _make_hero_card(self, p, meta, s):
        """「继续上次」大卡:左图右文;进度只按工程里有没有成片判断(有 → 下一步审阅,没有 → 回到配置)。"""
        card = ClickFrame(); card.setObjectName("herocard"); card.setFixedHeight(200)
        hl = QHBoxLayout(card); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        img = QLabel(); img.setFixedSize(360, 198)
        pm, focus = self._home_thumb(p, meta)
        if pm is not None:
            img.setPixmap(_cover_crop(pm, 360, 198, focus, radius=11, corners="left"))
        else:
            img.setStyleSheet(f"background:{self.theme['prevbg']}; border-top-left-radius:11px; "
                              "border-bottom-left-radius:11px;")
        hl.addWidget(img, 0)
        right = QWidget(); right.setObjectName("rowbg")
        rv = QVBoxLayout(right); rv.setContentsMargins(24, 22, 24, 22); rv.setSpacing(6)
        rv.addWidget(self._trl("继续上次", "sub"))
        nm = QLabel(s["name"]); nm.setObjectName("heroname"); rv.addWidget(nm)
        sig = FLOW_SIG.get(s["flow"], "#C6D0DC")
        bits = [t(s["flow_label"])] + ([t(s["dev"])] if s["dev"] else []) + ([s["date"]] if s["date"] else [])
        mt = QLabel(f"<span style='color:{sig}'>●</span>&nbsp;&nbsp;" + " · ".join(bits)); mt.setObjectName("herometa")
        rv.addWidget(mt)
        rv.addStretch(1)
        br = QHBoxLayout(); br.setSpacing(6)
        p_ = self.theme
        done = s["has_final"]
        steps = [("配置", "done" if done else "cur"), ("处理", "done" if done else "todo"),
                 ("审阅", "cur" if done else "todo"), ("导出", "todo")]
        for i, (nm_, st_) in enumerate(steps):
            if i:
                ln = QFrame(); ln.setFixedSize(16, 1)
                ln.setStyleSheet(f"background:{p_['accent_edge'] if steps[i - 1][1] == 'done' else p_['line2']};")
                br.addWidget(ln, 0, Qt.AlignVCenter)
            lab = QLabel(t(nm_) + (" ✓" if st_ == "done" else ""))
            lab.setStyleSheet("font-size:12px; " + (f"color:{p_['accent']};" if st_ == "done" else
                              f"color:{p_['text']}; font-weight:600;" if st_ == "cur" else f"color:{p_['muted']};"))
            br.addWidget(lab, 0)
        br.addStretch(1)
        go = QPushButton(); go.setObjectName("primary"); go.setCursor(Qt.PointingHandCursor)
        self._tr(go, "继续审阅" if done else "继续配置")
        go.clicked.connect(lambda _c=False, path=str(p): self._open_project(path))
        br.addWidget(go, 0)
        rv.addLayout(br)
        hl.addWidget(right, 1)
        card.clicked.connect(lambda path=str(p): self._open_project(path))
        return card

    def _go_stage(self, idx):
        """切到某屏(0项目库/1配置/2处理/3审阅/4导出);处理·审阅挂载唯一预览取景器。"""
        if not hasattr(self, "screen_stack"):
            return
        self._stage_idx = idx
        for i, b in enumerate(self.nav_btns):
            b.setChecked(i == idx)
        if idx == 2:
            # 【进处理屏先核对预览是不是这个目标的(用户 2026-09-14)】换目标后进来,右侧还挂着
            #   上一个目标的成片图,用户会困惑。预览带着"属主"标识,对不上就清回空态。
            self._drop_stale_preview()
            self._mount_preview(self._proc_view_l)
            # 挂载后预览卡被 reparent 到新布局、视口尺寸变了 → 布局落定后重缩放,否则沿用**上个视口**(常是项目重开时
            #   算的错尺寸)的图=偏移/留白(用户 2026-09-09:重开程序进"处理"预览偏到右边)。0ms+80ms 两跳等布局稳。
            QTimer.singleShot(0, self._rescale_preview)
            QTimer.singleShot(80, self._rescale_preview)
        elif idx == 3:
            if getattr(self, "_final_png", ""):
                self._reviewed_png = self._final_png          # 步骤导航:「审阅」打勾
            self._mount_preview(self._rev_view_l)
            QTimer.singleShot(0, self._rescale_preview)
            QTimer.singleShot(80, self._rescale_preview)
        elif idx == 4:
            QTimer.singleShot(0, self._refresh_export_preview)   # 布局落定后再缩放填图
            self._refresh_export_meta()
        if idx == 1:
            self._sync_setup_outline()
        self.screen_stack.setCurrentIndex(idx)
        self._fade_screen(self._screens[idx])
        self._sync_steps()
        QTimer.singleShot(0, self._sync_indicators)

    def _drop_stale_preview(self):
        """右侧预览若属于**上一个目标**,清回「等待素材」空态。同目标(含重跑)保留,方便对照。"""
        try:
            if not getattr(self, "_has_preview", False):
                return
            own = getattr(self, "_pm_owner", None)
            if own is None or own == self._preview_owner():
                return
            self._reset_result_preview()
            self._append(t("<已换目标:右侧预览已清空,等本次处理出图>"))
        except Exception:
            pass

    def _refresh_export_preview(self):
        """导出屏预览:把当前成片 PNG 等比缩放填入 export_preview;无成片则显示占位文案。"""
        if not hasattr(self, "export_preview"):
            return
        src = self._final_png if (self._final_png and Path(self._final_png).exists()) else ""
        if not src:
            self.export_preview.setPixmap(QPixmap()); self.export_preview.setText(t("成片就绪后在此预览"))
            return
        pm = QPixmap(src)
        if pm.isNull():
            return
        self._export_src_pm = pm
        area = self.export_preview.size()
        w = max(220, area.width() - 4); h = max(220, area.height() - 4)
        self.export_preview.setText("")
        _scaled = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.export_preview.setPixmap(_scaled)
        self._export_pm_display = _scaled            # 放大镜坐标映射用(导出屏自己的显示图)
        if getattr(self, "_export_loupe_on", False):  # 重刷/重排时收起放大镜(映射已变)
            if hasattr(self, "_export_loupe"):
                self._export_loupe.hide()
            self._export_loupe_on = False

    def _open_project_dialog(self):
        fn, _ = QFileDialog.getOpenFileName(self, t("打开工程"), str(self._projects_dir()),
                                            t("TTAstroPiLot 工程 (*.ttproj)"))
        if fn:
            self._open_project(fn)

    def _reset_result_preview(self):
        """把成片结果 + 右侧预览彻底还原到「等待素材」空态(新建项目用)。
        用户 2026-09-07:新建项目进「处理」屏,预览还挂着上个项目的成片图 → 必须清干净。"""
        # 成片 / 调色态
        self._final_png = self._final_xisf = ""; self._stage_xisf = ""
        self._pm_hires = None; self._pm_hires_key = ""
        self._finals = {}; self._cur_pal = None; self._scored_pal = None
        self._last_scores = {}; self._pal_scores = {}; self._last_scored_png = ""
        # 清掉上个目标的 AstroBin 同视场参考(_run 共享,防新目标误用旧参考评分)
        try:
            import shutil as _sh
            _sh.rmtree(str(config.RUN_DIR / "astrobin_refs"), ignore_errors=True)
        except Exception:
            pass
        # 预览像素 + 空态版式(镜像 __init__ / _set_preview_pixmap 的反向)
        self._pm_raw = None; self._pm_display = None
        self._has_preview = False
        self._max_phase = -1; self._done_ops = 0; self._end_state = "idle"
        if hasattr(self, "preview"):
            self.preview.clear()
        for _n, _vis in (("preview_scroll", False), ("phase_row", False),
                         ("road_v", True), ("road_panel", True),
                         ("gresult", False), ("export_panel", False)):
            if hasattr(self, _n):
                getattr(self, _n).setVisible(_vis)
        if hasattr(self, "pal_bar"):
            self.pal_bar.setVisible(False); self.pal_bar.clear()
        if hasattr(self, "lbl_review_empty"):
            self.lbl_review_empty.setText(t("还没有成片。到「处理」跑完流程后,评审与实测指标会出现在这里。"))
            self.lbl_review_empty.setVisible(True)
        if hasattr(self, "lbl_export_empty"):
            self.lbl_export_empty.setVisible(True)
        for _m in ("_paint_phases", "_paint_roadmap", "_sync_indicators"):
            if hasattr(self, _m):
                try:
                    getattr(self, _m)()
                except Exception:
                    pass

    def _new_project(self):
        """新建:清项目名 + 清上个项目的成片/预览,进入「配置」屏(参数保持当前默认)。"""
        self.ed_project.setText(""); self._proj_path = ""   # 新项目还没有落盘路径 → 首次保存会问位置
        self._reset_result_preview()                        # 清掉上个项目残留的成片图/评分/预览态
        self._mark_dirty()
        self._go_stage(1)

    def _open_project(self, path):
        """打开 .ttproj:恢复 config(全控件)+ 成片结果 + 调色态;有成片跳「审阅」,否则「配置」。"""
        import json
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            self._append(f"[项目] 打开失败:{e}")
            return
        self.ed_project.setText(data.get("name") or Path(path).stem)
        self._reset_result_preview()   # 先清上个项目的成片/预览;有成片的工程会在 _apply_project_state 里重填
        try:
            self._apply_project_state(data.get("state") or data, meta=data)   # 兼容旧最小工程(顶层字段)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._append(f"[项目] 恢复部分失败:{e}")
        self._proj_path = str(Path(path).resolve())   # 记住来源 → 后续「保存」直接覆盖它
        self._add_recent(self._proj_path)
        self._mark_saved()
        has_final = bool((data.get("state") or {}).get("result", {}).get("final_png")
                         and Path(((data.get("state") or {}).get("result") or {}).get("final_png", "")).exists())
        self._go_stage(3 if has_final else 1)

    # ---- .ttproj 持久化的控件清单(键名即 JSON 键;缺失控件用 hasattr 兜底) ----
    _PROJ_LINES = ("ed_exportdir",)   # ed_input/ed_ha_dir 已并入母版多行 → 走 masters 单独存(见下)
    _PROJ_SPINS = ("sp_ghs", "sp_sat", "sp_ha", "sp_core", "sp_crop", "sp_ms", "sp_timeout")
    _PROJ_COMBOS = ("cb_nbpalette", "cb_palette", "cb_zpreset", "cb_rgbpreset", "cb_bgextract", "cb_rgbreveal",
                    "cb_glow", "cb_hapreset", "cb_hoopreset", "cb_dust", "cb_grade", "cb_dse")
    _PROJ_CHECKS = ("chk_stars", "chk_detrail", "chk_stretch_judge", "chk_reveal", "chk_lhe",
                    "chk_zeropi", "chk_zeropi_rgb", "chk_zeropi_hoo", "chk_release",
                    "chk_xisf", "chk_png", "chk_jpg", "chk_starless", "chk_export_stars", "chk_annotate")

    def _collect_project_state(self):
        """把当前 config(全控件)+ 成片结果 + 调色态收进一个可 JSON 化的 dict。"""
        st = {
            "flow": self.FLOWS[getattr(self, "flow_idx", 0)][0],
            "input_mode": self._input_mode,
            "device": getattr(self, "_stack_device", "osc"),   # 相机设备(OSC/mono/seestar/dwarf,用户 2026-09-06)
            "stop_key": self.STOPS[self.cb_stop.currentIndex()][0] if hasattr(self, "cb_stop") else "final",
            "jpgq": self.sl_jpgq.value() if hasattr(self, "sl_jpgq") else 95,
            "target": self.ed_target.text().strip() if hasattr(self, "ed_target") else "",
            "lines": {k: getattr(self, k).text() for k in self._PROJ_LINES if hasattr(self, k)},
            "spins": {k: getattr(self, k).value() for k in self._PROJ_SPINS if hasattr(self, k)},
            "combos": {k: getattr(self, k).currentIndex() for k in self._PROJ_COMBOS if hasattr(self, k)},
            "checks": {k: getattr(self, k).isChecked() for k in self._PROJ_CHECKS if hasattr(self, k)},
            "masters": self._master_config() if hasattr(self, "master_rows") else None,   # 已叠加母版多行(文件+滤镜)
            "regs": self._reg_config() if hasattr(self, "reg_rows") else None,            # 对齐子帧目录多行
            "raw": self._raw_config() if self._input_mode == 2 else None,   # 原始叠加配置(恢复见下·部分)
            "result": {
                "final_png": self._final_png or "",
                "final_xisf": self._final_xisf or "",
                "finals": dict(self._finals or {}),
                "cur_pal": self._cur_pal,
                "scored_pal": self._scored_pal,
                "scores": self._last_scores or {},
            },
        }
        return st

    def _find_recent_export(self, name: str):
        """这个项目**最近一次导出**的全分辨率成片。返回 (显示用图, 全分辨率 xisf) 或 (None, None)。

        【为什么要找它(用户 2026-09-23)】工程里存的成片路径在共享 `_run` 下,会被后面跑的
        目标覆盖(13 个工程里 12 个如此)。上一版我退回工程自带的内嵌缩略图 —— 那是给项目库
        **卡片**用的 280×158,铺到预览框里糊得没法看。用户原话:"拿不到清晰的图像,不如干脆
        不显示,或者读取最近导出的原图"。导出名以项目名开头(`M74_0923-1530.png`),按前缀找即可。
        ⚠ **必须按项目名前缀匹配**:导出目录里躺着别的目标的成片,拿最新那张会串图 ——
          那正是今天反复踩的同一类坑。
        """
        from pathlib import Path as _P
        nm = (name or "").strip()
        if not nm:
            return None, None
        dirs = []
        try:
            d = (self.ed_exportdir.text() or "").strip()
            if d:
                dirs.append(d)
        except Exception:
            pass
        try:
            d2 = (config.get_setting("export_dir") or "").strip()
            if d2 and d2 not in dirs:
                dirs.append(d2)
        except Exception:
            pass
        # 【必须精确匹配,不能只看前缀(2026-09-23 实测)】同一次导出还会写出
        #   `<名>_<戳>_stars.png`(星点层)、`_starless.jpg`(去星层)、`_annotations.txt`,
        #   而且它们**比成片本身更新** —— 只按前缀找会挑中星点层当预览。
        #   只认 `<名>` 或 `<名>_月日-时分`(导出戳)这两种,把附属产物排除干净。
        import re as _re
        _pat = _re.compile(r"^" + _re.escape(nm.lower()) + r"(_\d{4}-\d{4})?$")
        best_img = best_xis = None
        bt = bx = -1.0
        for d in dirs:
            try:
                p = _P(d)
                if not p.is_dir():
                    continue
                for f in p.iterdir():
                    if not f.is_file() or not _pat.match(f.stem.lower()):
                        continue
                    ext = f.suffix.lower()
                    try:
                        mt = f.stat().st_mtime
                    except OSError:
                        continue
                    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff") and mt > bt:
                        bt, best_img = mt, f
                    elif ext == ".xisf" and mt > bx:
                        bx, best_xis = mt, f
            except OSError:
                continue
        return (str(best_img) if best_img else None), (str(best_xis) if best_xis else None)

    def _apply_project_state(self, st, meta=None):
        """把 _collect_project_state 的 dict 恢复到控件/预览(尽力而为,缺控件跳过)。"""
        flow = st.get("flow", "pure_rgb")
        flow = FLOW_MIGRATE.get(flow, flow)      # 老工程的 rgb/sho/hoo/lrgb → 新混合模式 key
        for i, (k, _lbl) in enumerate(self.FLOWS):
            if k == flow:
                self._select_flow(i); self._sync_flow_cards(); break
        try:
            self._select_input_mode(int(st.get("input_mode", 0)))
        except Exception:
            pass
        try:      # 相机设备(用户 2026-09-06:保存后没保留,选了 Dwarf 重开变回 OSC)
            if hasattr(self, "_select_stack_device"):
                self._select_stack_device(st.get("device", "osc") or "osc")
        except Exception:
            pass
        if st.get("target") and hasattr(self, "ed_target"):   # 项目目录(用户 2026-09-07:重开工程名字丢了)
            self.ed_target.setText(st["target"])
        try:      # 原始叠加素材:逐晚亮/平/滤镜、校准库、暗/偏、输出根(用户 2026-09-07:重开全丢)
            if st.get("raw"):
                self._apply_raw_config(st["raw"])
        except Exception:
            pass
        try:      # 已叠加母版多行 / 对齐子帧目录多行(用户 2026-09-07)
            _ms = st.get("masters")
            if _ms is None and (st.get("lines") or {}).get("ed_input"):     # 旧工程只存了单 ed_input → 当宽带底
                _ms = [{"file": st["lines"]["ed_input"], "filter": "uvir"}]
                if (st.get("lines") or {}).get("ed_ha_dir"):               # 旧工程的窄带框 → 补一行 Ha/OIII
                    _ms.append({"file": st["lines"]["ed_ha_dir"], "filter": "hoo"})
            if _ms:
                self._apply_master_config(_ms)
            if st.get("regs"):
                self._apply_reg_config(st["regs"])
        except Exception:
            pass
        for k, v in (st.get("lines") or {}).items():
            if hasattr(self, k):
                # 【导出目录别被工程空值清掉(用户 2026-09-06)】export_dir 是全局偏好(settings 持久化);
                #   旧工程 .ttproj 里存过空 ed_exportdir,恢复时 setText("") 会把设好的全局目录清空 →
                #   点「导出成片」又弹窗(且第三参是裸文件名,对话框落在 CWD)。工程值**非空才覆盖**,
                #   空则保留当前值(启动时已从 settings 填入)。
                if k == "ed_exportdir" and not (v or "").strip():
                    continue
                getattr(self, k).setText(v or "")
        for k, v in (st.get("spins") or {}).items():
            if hasattr(self, k):
                try:
                    getattr(self, k).setValue(v)
                except Exception:
                    pass
        for k, v in (st.get("combos") or {}).items():
            if hasattr(self, k):
                cb = getattr(self, k)
                if isinstance(v, int) and 0 <= v < cb.count():
                    cb.setCurrentIndex(v)
        for k, v in (st.get("checks") or {}).items():
            if hasattr(self, k):
                getattr(self, k).setChecked(bool(v))
        sk = st.get("stop_key")
        if sk and hasattr(self, "cb_stop"):
            for i, (key, _t) in enumerate(self.STOPS):
                if key == sk:
                    self.cb_stop.setCurrentIndex(i); break
        if "jpgq" in st and hasattr(self, "sl_jpgq"):
            try:
                self.sl_jpgq.setValue(int(st["jpgq"]))
            except Exception:
                pass
        # 结果 / 调色态
        res = st.get("result") or {}
        self._final_png = res.get("final_png", "") or ""
        self._final_xisf = res.get("final_xisf", "") or ""
        self._finals = dict(res.get("finals") or {})
        self._cur_pal = res.get("cur_pal")
        self._scored_pal = res.get("scored_pal")
        self._last_scores = res.get("scores") or {}
        png = self._final_png
        # 【★工程里存的成片路径若在 _run 下,一律不认(用户 2026-09-23:「打开新项目总是显示
        #   前一个项目的预览」)】`_run` 是**跨目标复用**的临时区,`r14_final.png` 这种名字
        #   每跑一个目标就被覆盖一次 —— 于是打开工程 A 时,那个路径下装的是最近跑过的 B 的成片,
        #   预览、放大镜、评分图全串到 B 去。项目库缩略图早就防了这一手
        #   (「绝不用 /_run/ 下的共享路径」),**但恢复预览这条路一直没防**。
        #   宁可显示"没有成片"也不能显示别人的图:错图比空态危险得多(见 [[pi-gui-stale-target-state]])。
        #   有内嵌缩略图就退回它(分辨率低但**确实是本工程的**),并说明要重跑才能拿回全分辨率。
        _stale = bool(png) and "/_run/" in str(png).replace("\\", "/")
        if _stale:
            self._final_png = self._final_xisf = ""      # 一并清掉,免得放大镜去采样那张串图
            png = ""
            _ei, _ex = self._find_recent_export((self.ed_project.text() or "").strip())
            if _ei:
                png = _ei
                self._final_png = _ei
                self._final_xisf = _ex or ""
                self._append(t("[项目] 工程里记的成片在共享临时区、已被后来的目标覆盖 → "
                               "改用这个项目**最近一次导出**的全分辨率图:{}").format(_ei))
            else:
                # 【宁可不显示,也不显示糊图或别人的图(用户 2026-09-23)】
                self._append(t("[项目] 工程里记的成片在共享临时区、已被后来的目标覆盖,"
                               "导出目录里也没有这个项目的成品 → **不显示预览**(重跑或导出一次即可)。"))
        if png and Path(png).exists():
            pm = QPixmap(png)
            if not pm.isNull():
                self._set_preview_pixmap(pm)
            if self._finals:
                try:
                    self._build_palette_bar(self._finals)
                except Exception:
                    pass
            if self._last_scores:
                try:
                    self._show_scores(self._last_scores)
                except Exception:
                    pass
            self.gresult.setVisible(True)
            if hasattr(self, "export_panel"):
                self.export_panel.setVisible(True)
            if hasattr(self, "lbl_review_empty"):
                self.lbl_review_empty.setVisible(False)
            if hasattr(self, "lbl_export_empty"):
                self.lbl_export_empty.setVisible(False)
            self._end_state = "done"

    def _save_project(self, save_as=False, autosave=False):
        """保存 .ttproj:完整 config + 成片结果 + 调色态(可从项目库载入直接续处理,不重跑)。
        autosave=True:定时器触发的静默保存(日志措辞不同;不弹任何窗)。
        首次保存(或『另存为』)弹**选择保存位置**对话框,记住路径;之后直接覆盖同一文件。"""
        import json
        name = (self.ed_project.text() or "").strip() or (self._guess_target() or "未命名项目")
        self.ed_project.setText(name)
        safe = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "未命名项目"
        # 决定落盘路径:已有记住的路径且非『另存为』→ 直接覆盖;否则弹「选择保存位置」
        target = self._proj_path
        if save_as or not target:
            # 起始目录:另存已有工程→其所在目录;新建→**上次保存工程的目录**(用户 2026-09-07:别再默认落软件目录)
            _home = self._project_home()             # 默认停在项目自己的目录,别停在上一个目标的文件夹
            _startdir = _home if (_home and os.path.isdir(_home)) else self._last_project_dir()
            try:
                Path(_startdir).mkdir(parents=True, exist_ok=True)
            except Exception:
                _startdir = str(self._projects_dir()); self._projects_dir().mkdir(parents=True, exist_ok=True)
            _base = Path(self._proj_path).parent if self._proj_path else Path(_startdir)
            default = str(_base / f"{safe}.ttproj")
            fn, _ = QFileDialog.getSaveFileName(self, t("保存工程 · 选择位置"), default,
                                                t("TTAstroPiLot 工程 (*.ttproj)"))
            if not fn:
                return                                               # 用户取消 → 不保存
            if not fn.lower().endswith(".ttproj"):
                fn += ".ttproj"
            target = fn
        # 【缩略图**内嵌 base64**(用户 2026-09-06 bug:工程缩略图全串成最新那张 / 或黑图)】self._final_png 是
        #   _run 里的**共享预览**,每跑新项目就被覆盖 → 存路径的话所有工程都指向同一被覆盖/被清理的文件。
        #   **改成把小缩略图(280×158 JPEG)base64 直接写进 .ttproj**——自包含、永不串、清理中间文件也不受影响。
        #   仍存一份 thumb 路径当老工程兼容/回退。用 QPixmap 生成(不依赖 PIL)。
        _thumb = self._final_png or ""
        _thumb_b64 = ""
        try:
            if self._final_png and Path(str(self._final_png)).exists():
                from PyQt5.QtCore import QByteArray, QBuffer, QIODevice
                _pm0 = QPixmap(str(self._final_png))
                if not _pm0.isNull():
                    _sc0 = _pm0.scaled(280, 158, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    _cx = max(0, (_sc0.width() - 280) // 2); _cy = max(0, (_sc0.height() - 158) // 2)
                    _sc0 = _sc0.copy(_cx, _cy, 280, 158)
                    _ba0 = QByteArray(); _bf0 = QBuffer(_ba0); _bf0.open(QIODevice.WriteOnly)
                    _sc0.save(_bf0, "JPEG", 62); _bf0.close()
                    _thumb_b64 = bytes(_ba0.toBase64().data()).decode("ascii")
                # 顺带存一份工程旁 png(老工程/外部查看兼容)
                import shutil
                _tp = Path(target).parent / (Path(target).stem + "_thumb.png")
                shutil.copy2(str(self._final_png), str(_tp))
                _thumb = str(_tp).replace("\\", "/")
        except Exception:
            _thumb = self._final_png or ""
        # 【保留旧缩略图(用户 2026-09-09 bug:定时/关窗/配置期自动保存时 _final_png 为空 → 把已存的成片缩略图
        #   覆盖成空,项目库缩略图消失/不更新)】没生成新缩略图(还没出成片或图已被清)→ 沿用被覆盖文件里的旧
        #   thumb_b64/thumb,**绝不用空值抹掉已有缩略图**。有新成片时 _thumb_b64 非空 → 跳过本段、正常更新。
        if not _thumb_b64 and target and os.path.exists(target):
            try:
                _old = json.loads(Path(target).read_text(encoding="utf-8"))
                _thumb_b64 = _old.get("thumb_b64") or ""
                if not _thumb:
                    _thumb = _old.get("thumb") or ""
            except Exception:
                pass
        try:
            data = {
                "schema": "ttproj/0.2",
                "name": name,
                "flow": self.FLOWS[getattr(self, "flow_idx", 0)][0],   # 顶层留一份给项目库卡片标签
                "thumb": _thumb,
                "thumb_b64": _thumb_b64,
                "target_type": self._guess_target() or "",
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "state": self._collect_project_state(),
            }
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            self._proj_path = str(Path(target).resolve())
            self._add_recent(self._proj_path)
            try:      # 记住这次保存的目录 → 下次新建默认停这(用户 2026-09-07)。嵌套存(与 projects.recent 一致)
                _s = config.load_settings()
                if not isinstance(_s.get("projects"), dict):
                    _s["projects"] = {}
                _s["projects"]["last_dir"] = str(Path(target).resolve().parent).replace("\\", "/")
                config.save_settings(_s)
            except Exception:
                pass
            self._append((f"[项目] 已自动保存 → {self._proj_path}" if autosave
                          else f"[项目] 已保存 → {self._proj_path}(完整配置 + 成片 + 调色态)"))
            self._mark_saved()
            self._refresh_home()
        except OSError as e:
            self._append(f"[项目] 保存失败:{e}")

    # ---------- 视觉:折叠区 / 入场动画 ----------
    def _make_section(self, title, note):
        """可折叠小节。返回 (开关按钮, 折叠容器, 容器布局)。

        折叠**只**改外层容器的 maximumHeight —— 每一行的 visible 仍由 _select_flow 控制,
        两者互不干扰(否则切流程会错乱)。
        """
        btn = QPushButton(); btn.setObjectName("sectoggle"); btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        body = QWidget(); body.setObjectName("rowbg")
        v = QVBoxLayout(body); v.setContentsMargins(0, 5, 0, 1); v.setSpacing(5)
        body.setMaximumHeight(0)
        anim = QPropertyAnimation(body, b"maximumHeight", self)
        anim.setDuration(240); anim.setEasingCurve(QEasingCurve.OutCubic)

        def _relabel(on):
            # title/note 传的是**中文源**,这里 t() 动态译 → 语言切换时经回调重刷可跟随。
            btn.setText(("▾  %s · %s" if on else "▸  %s · %s") % (t(title), t(note)))
        self._i18n_callbacks.append(lambda: _relabel(btn.isChecked()))

        def _toggle(on):
            _relabel(on)
            anim.stop()
            anim.setStartValue(body.maximumHeight())
            anim.setEndValue(body.sizeHint().height() if on else 0)
            anim.start()
            if on:                                  # 高度展开的同时内容淡入
                eff = QGraphicsOpacityEffect(body); eff.setOpacity(0.0)
                body.setGraphicsEffect(eff)
                fade = QPropertyAnimation(eff, b"opacity", self)
                fade.setDuration(300); fade.setStartValue(0.0); fade.setEndValue(1.0)
                fade.setEasingCurve(QEasingCurve.OutCubic)
                fade.finished.connect(lambda: body.setGraphicsEffect(None))
                self._anims.append(fade); fade.start()

        def _settle():
            if btn.isChecked():
                body.setMaximumHeight(16777215)      # 展开完成后放开上限,内容变化能自适应

        anim.finished.connect(_settle)
        btn.toggled.connect(_toggle)
        _relabel(False)
        self._anims.append(anim)
        self._sections.append((btn, body))
        return btn, body, v

    def _init_pulse(self):
        """进度条左侧的呼吸圆点(仅处理中呼吸)。_pulse 保留 start()/stop() 调用方式。"""
        self.prog_dot.set_state(self.theme['accent'], False)
        self._pulse = self.prog_dot

    def _entrance(self, widgets):
        """启动时卡片错峰淡入,避免一次性糊在脸上。"""
        for i, w in enumerate(widgets):
            eff = QGraphicsOpacityEffect(w); eff.setOpacity(0.0)
            w.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", self)
            a.setDuration(340); a.setStartValue(0.0); a.setEndValue(1.0)
            a.setEasingCurve(QEasingCurve.OutCubic)
            a.finished.connect(lambda w=w: w.setGraphicsEffect(None))
            self._anims.append(a)
            QTimer.singleShot(80 * i, a.start)

    def _sync_indicators(self):
        """把滑动指示器对到当前选中项,并按主题上色;扫描线按预览区尺寸重排。

        折行 / 缩放后子控件几何会变,所以 showEvent、resizeEvent、切流程、切输入模式
        都要来这里重新对位(带动画)。
        """
        p = self.theme
        if hasattr(self, "flow_ind"):
            self.flow_ind.set_colors(p['accent'], None, p['sec'])
            for i, b in enumerate(self.flow_btns):
                if b.isChecked() and b.width() > 1:
                    g = b.geometry()
                    self.flow_ind.move_to(QRect(g.x(), g.bottom() - 2, g.width(), 3))
                    self.flow_ind.raise_()
                    break
        if hasattr(self, "stage_ind") and hasattr(self, "nav_btns"):
            self.stage_ind.set_colors(p['accent'], None, p['info'])   # 阶段导航下划线 green→blue
            for i, b in enumerate(self.nav_btns):
                if b.isChecked() and b.width() > 1:
                    g = b.geometry()
                    self.stage_ind.move_to(QRect(g.x() + 6, g.bottom() - 2, max(6, g.width() - 12), 2))
                    self.stage_ind.raise_()
                    break
        if hasattr(self, "mode_ind"):
            # 选中态药丸:中性灰蓝平填充(设计稿:绿色只给行动,选中态不用绿 —— 原来整块实心绿像主按钮)
            self.mode_ind.set_colors(p['surf4'], None, None, inner=False)
            for i, b in enumerate(self.in_mode_btns):
                if b.isChecked() and b.width() > 1:
                    self.mode_ind.move_to(b.geometry())
                    self.mode_ind.lower()
                    break
        for _sh in ("bar_shim", "run_shim"):
            if hasattr(self, _sh):
                getattr(self, _sh).resync()
        if hasattr(self, "scanline"):
            par = self.road_panel
            if self._has_preview or not par.isVisible() or par.height() < 40:
                self._scan_anim.stop(); self.scanline.hide()
            else:
                self.scanline.set_color(p['logmark'])
                self.road_panel.set_dot(p['stroke'])
                self.scanline.setFixedSize(max(10, par.width() - 2), 128)
                self.scanline.show(); self.scanline.raise_()
                self._scan_anim.stop()
                self._scan_anim.setStartValue(QPoint(1, -136))
                self._scan_anim.setEndValue(QPoint(1, par.height() + 8))
                self._scan_anim.start()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._sync_indicators)
        QTimer.singleShot(0, self._sync_caret)

    def _reveal(self, w):
        """淡入出现(用于进度条、评分卡、成片预览),避免元素凭空跳出来。"""
        w.setVisible(True)
        eff = QGraphicsOpacityEffect(w); eff.setOpacity(0.0)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(260); a.setStartValue(0.0); a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: w.setGraphicsEffect(None))
        self._anims.append(a)
        a.start()

    def _preview_owner(self):
        """当前配置指向的目标标识(项目名 + 输入路径)。预览图带着它,换目标时就能认出预览是旧的。"""
        try:
            _p = ""
            if getattr(self, "_input_mode", 0) == 1:
                _rg = self._reg_config()
                _p = (_rg[0].get("dir", "") if _rg else "")
            else:
                _p = self.ed_input.text().strip()
            return ((self.ed_project.text() or "").strip(),
                    str(_p).replace(chr(92), "/").rstrip("/"),
                    str(self._guess_target() or ""))
        except Exception:
            return ((self.ed_project.text() or "").strip(), "", "")

    def _set_preview_pixmap(self, pm):
        """收下原图,按预览视口**等比缩放到最大**(完整呈现 + 尽量填满,绝不裁切)。"""
        self._pm_raw = pm
        self._pm_owner = self._preview_owner()          # 这张图属于哪个目标(换目标时据此清掉)
        if not self._has_preview:
            self._has_preview = True
            self.road_v.setVisible(False)
            self.road_panel.setVisible(False)
            self.phase_row.setVisible(True)
            self._reveal(self.preview_scroll)
            self._paint_phases()
            self._sync_indicators()
        self._rescale_preview()
        # 视口尺寸在布局稳定后才准 → 延迟再算一次,避免首帧算小/留空
        QTimer.singleShot(0, self._rescale_preview)
        QTimer.singleShot(80, self._rescale_preview)

    def _rescale_preview(self):
        pm = getattr(self, "_pm_raw", None)
        if pm is None or pm.isNull() or not self.preview_scroll.isVisible():
            return
        vp = self.preview_scroll.viewport().size()
        w, h = max(160, vp.width() - 2), max(120, vp.height() - 2)
        # KeepAspectRatio 到视口:整幅完整、按较紧的一边铺满(横图在横向预览区里几乎填满)
        scaled = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._pm_display = scaled          # 缓存当前显示图(灰尘画圈叠加基于它重绘)
        self.preview.setPixmap(scaled)
        # label 填满视口、图居中(AlignCenter)→ 不留白顶边、点选坐标映射也对称
        self.preview.resize(max(scaled.width(), w), max(scaled.height(), h))
        if getattr(self, "_loupe_on", False):        # 重排/重缩放时收起放大镜(映射已变)
            self._loupe.hide(); self._loupe_on = False

    def _hires_src(self):
        """放大镜的全分辨率取样源:**已出成片就用成片**,处理过程中用**当前阶段**的全分辨率图
        (用户 2026-09-14:处理 M64 时想看细节,放大却是上一个目标 M63)。
        运行中 _final_xisf 只可能是面板(暂停/调色/岔口)临时设的"这一步",下一张阶段预览
        一到就作废(见 _show_stage_preview),否则它会一直压着 _stage_xisf。
        ⚠ 调色阶段这张是**调色前**的 —— 放大镜那边会再套一道面板的曲线+蒙版
        (见 `_col_adjust_crop`),否则看到的和预览对不上。"""
        return (self._final_xisf or "") or getattr(self, "_stage_xisf", "") or ""

    def _hires_key(self):
        """放大镜全分辨率缓存键:路径 + mtime(就地覆盖也能识别为新图、触发重载)。"""
        src = self._hires_src()
        if not src or not src.lower().endswith(".xisf") or not Path(src).exists():
            return ""
        try:
            return f"{src}|{int(os.path.getmtime(src))}"
        except OSError:
            return src

    def _loupe_source(self):
        """放大镜取样源:优先**全分辨率成片**(直接读 XISF,像素级细看星点/噪点);
        没有则回退当前显示预览的原图(~1200px 界面预览图)。"""
        hi = getattr(self, "_pm_hires", None)
        if hi is not None and not hi.isNull() and getattr(self, "_pm_hires_key", "") == self._hires_key() and self._hires_key():
            return hi
        return getattr(self, "_pm_raw", None)

    def _col_live(self) -> bool:
        """调色面板正开着、且已有底图 —— 此时放大镜必须显示**调色后**的样子。"""
        try:
            return bool(self.color_panel.isVisible()
                        and getattr(self, "_col_base", None) is not None)
        except AttributeError:
            return False

    def _col_adjust_params(self) -> dict:
        """面板当前这一组变换的**快照**(控件只能在界面线程读)。交给纯 numpy 的
        colorexp.apply_panel,后台线程也能算同一个变换 —— 经验采集要读 90MB 的全分辨率图,不能卡界面。"""
        from . import colorprefs as _cpt
        return {"pts": self._col_points() or {}, "bpts": self._col_bg_points() or {},
                "use_mask": bool(self.btn_col_mask.isChecked()),
                "mask": getattr(self, "_col_maskarr", None), "ct": _cpt.curve_type()}

    def _col_adjust_crop(self, pm_crop, x0, y0, crop, src_w, src_h):
        """把面板当前的曲线+蒙版施加到放大镜裁出来的这一小块上(全分辨率)。

        【为什么要这一步(用户 2026-09-23)】放大镜的取样源是 `_hires_src()` =
        `_final_xisf or _stage_xisf`,调色阶段那就是 `r11b_lhe` —— **调色前**的图;
        而面板预览那张(已调色)只是 `_pm_raw`,优先级更低。于是"想看调色后的细节"
        看到的却是调色前。**放大镜和预览必须显示同一个东西**,否则又是一处
        "程序跟你看到的不一样"(同类见 [[pi-gui-final-preview-bug]])。
        裁图只有两百来像素,在它上面算曲线开销可忽略,所以不必缓存整张调色后的全分辨率图。
        蒙版按预览分辨率那张**双线性取样**到裁图坐标:蒙版本身是高斯羽化的平滑场
        (σ 按短边折算),放大后误差远小于一个像素级的可见量。
        实测(M51):本法 vs「整图调好再裁」RMSE **0.0019**、max 0.0138
        (≈3.5 个 8bit 色阶 = 中间那道 8 位量化本身,蒙版取样误差为 0);
        而不做这一步(即修复前)差 RMSE **0.0554**、max 0.151 —— 那就是用户看到的"还是调色前"。
        """
        import numpy as _np
        from . import colorexp as _cx
        qi = pm_crop.toImage().convertToFormat(QImage.Format_RGB888)
        w, h = qi.width(), qi.height()
        ptr = qi.constBits()
        ptr.setsize(qi.byteCount())
        a = (_np.frombuffer(ptr, _np.uint8).reshape(h, qi.bytesPerLine())[:, :w * 3]
             .reshape(h, w, 3).astype(_np.float64) / 255.0)
        prm = self._col_adjust_params()
        if not prm["pts"] and not prm["bpts"]:
            return pm_crop
        # 变换本体在 colorexp.apply_panel(纯 numpy):经验库存的「调后」也走它,两边永远一致
        out = _cx.apply_panel(a, prm, x0, y0, src_w, src_h)
        u8 = (_np.clip(out, 0, 1) * 255.0 + 0.5).astype("uint8")
        q2 = QImage(u8.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
        return QPixmap.fromImage(q2.copy())

    def _loupe_move(self, px, py, widget=None, disp=None, loupe=None, raw_fallback=None):
        """光标(px,py = widget 坐标)按显示占比映射到取样源,裁一块放进放大镜并移到光标处。
        全分辨率源:约 1:1 native(相对 fit 是好几倍的像素级放大);预览源:≥3×fit 也是真放大。
        默认作用于主预览 self.preview;传 widget/disp/loupe/raw_fallback 可复用于导出屏 export_preview。"""
        widget = widget or self.preview
        loupe = loupe or self._loupe
        if disp is None:
            disp = getattr(self, "_pm_display", None)
        # 取样源:优先**全分辨率成片**(_pm_hires,跨屏共享);否则回退各屏自己的原图
        hi = getattr(self, "_pm_hires", None)
        if (hi is not None and not hi.isNull()
                and getattr(self, "_pm_hires_key", "") == self._hires_key() and self._hires_key()):
            src = hi
        else:
            src = raw_fallback if raw_fallback is not None else getattr(self, "_pm_raw", None)
        if src is None or src.isNull() or disp is None or disp.isNull():
            loupe.hide(); return
        Lw, Lh = widget.width(), widget.height()
        Dw, Dh = disp.width(), disp.height()
        ox, oy = (Lw - Dw) / 2.0, (Lh - Dh) / 2.0        # 图在 label 内居中偏移
        ix, iy = px - ox, py - oy
        if ix < 0 or iy < 0 or ix > Dw or iy > Dh:        # 光标不在图上 → 收起
            loupe.hide(); return
        fx, fy = ix / float(Dw), iy / float(Dh)           # 显示图内的归一化位置(与源分辨率无关)
        rx, ry = fx * src.width(), fy * src.height()       # 映射到取样源坐标
        s_src = Dw / float(src.width())                    # 源相对显示的比例
        dia = loupe._dia
        lscale = max(1.0, 3.0 * s_src)                     # 全分辨率源 s 很小→1.0(1:1 native);预览源→≥3×fit
        crop = max(24, int(round(dia / lscale)))           # 需裁的源区域边长
        x0 = max(0, min(int(rx - crop / 2), max(0, src.width() - crop)))
        y0 = max(0, min(int(ry - crop / 2), max(0, src.height() - crop)))
        c = src.copy(x0, y0, crop, crop)
        # 调色面板开着、且这块是从**调色前**的全分辨率图上裁的 → 当场施加面板的曲线+蒙版。
        #   (src 是 _pm_raw 时它本来就是面板预览、已经调过色,不能再调一次。)
        try:                                   # 换了取样源就报一次,方便核对"放大镜在看哪张图"
            _tag = ("调色面板实时" if (src is hi and self._col_live())
                    else (self._hires_src() if src is hi else "界面预览图(非全分辨率)"))
            if getattr(self, "_loupe_src_tag", None) != _tag:
                self._loupe_src_tag = _tag
                self._append(t("[放大镜] 取样自:{}").format(_tag))
        except Exception:
            pass
        if src is hi and self._col_live():
            try:
                c = self._col_adjust_crop(c, x0, y0, crop, src.width(), src.height())
            except Exception as _le:
                self._append("[放大镜] 调色后预览算不出来,显示调色前:%s" % str(_le)[:80])
        if c.width() != dia or c.height() != dia:
            c = c.scaled(dia, dia, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        loupe.set_crop(c)
        loupe.move(int(px - dia / 2), int(py - dia / 2))
        loupe.show(); loupe.raise_()

    def _ensure_hires_loupe(self):
        """把成片**全分辨率**图直接从 XISF 读进内存(不经 runner)供放大镜像素级查看。按源路径缓存;
        位深自适应归一到 0..1 显示域(与预览一致,不额外拉伸)。失败静默回退预览图。"""
        src = self._hires_src()
        key = self._hires_key()
        if not key:
            return
        if getattr(self, "_pm_hires_key", "") == key:
            return            # 这个源已处理过(成功=有图;不适用=None,别反复重载几十 MB)
        try:
            import numpy as np
            from xisf import XISF
            from PyQt5.QtGui import QImage
            arr = np.asarray(XISF(src).read_image(0))
            if arr.dtype == np.uint8:
                a = arr.astype(np.float32) / 255.0
            elif arr.dtype == np.uint16:
                a = arr.astype(np.float32) / 65535.0
            elif np.issubdtype(arr.dtype, np.integer):
                a = arr.astype(np.float32) / float(np.iinfo(arr.dtype).max)
            else:
                a = np.clip(arr.astype(np.float32), 0.0, 1.0)   # 处理后成片:float 已在 0..1 显示域
            if a.ndim == 2:
                a = np.stack([a, a, a], axis=-1)
            if a.shape[2] > 3:
                a = a[:, :, :3]
            # 【线性阶段图不能直接拿来显示(会是全黑)】阶段预览 png 是 runner 拉伸过的,xisf 没有。
            #   中位数极低=线性 → 标记这个源不适用,放大镜回退到那张已拉伸的预览图。
            if float(np.median(a)) < 0.02:
                self._pm_hires = None; self._pm_hires_key = key
                return
            u8 = np.ascontiguousarray((np.clip(a, 0, 1) * 255.0 + 0.5).astype(np.uint8))
            h, wd = int(u8.shape[0]), int(u8.shape[1])
            qi = QImage(u8.data, wd, h, 3 * wd, QImage.Format_RGB888)
            self._pm_hires = QPixmap.fromImage(qi.copy())   # copy 脱离 numpy 缓冲
            self._pm_hires_key = key
            _wh = "成片" if (self._final_xisf or "") else "当前步骤"
            self._append(f"[放大镜] 已载入{_wh}全分辨率图 {wd}×{h}(可像素级查看)。")
        except Exception as e:
            self._pm_hires = None; self._pm_hires_key = ""
            self._append(f"[放大镜] 全分辨率载入失败,回退预览图:{e}")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._fit_header)
        QTimer.singleShot(0, self._rescale_preview)
        QTimer.singleShot(0, self._sync_indicators)
        QTimer.singleShot(0, self._sync_caret)
        QTimer.singleShot(0, self._refresh_export_preview)   # 导出屏预览随窗口重排(放大镜坐标映射依赖显示图)

    def _sync_param_sections(self):
        """流程切换后的视觉同步:LRGB 专用整块显隐、折叠高度重算、路线图重绘。"""
        kind = self._derive_kind()               # 派生引擎 kind(LRGB 专块按它显隐)
        if hasattr(self, "lrgb_wrap"):
            self.lrgb_wrap.setVisible(kind == "lrgb")
        if hasattr(self, "lbl_param_count"):
            shown = sum(1 for k, r in self._param_rows.items() if not r.isHidden())
            self.lbl_param_count.setText(t("{} 项 · 已按流程过滤").format(shown))
        for _sec, _rows in getattr(self, "_insp_sections", []):   # 整组都被流程隐藏 → 标题也藏
            _sec.setVisible(any(not r.isHidden() for r in _rows))
        if hasattr(self, "lbl_insp_chip"):
            self.lbl_insp_chip.setText(t(self.FLOWS[getattr(self, "flow_idx", 0)][1]))
        for btn, bd in getattr(self, "_sections", []):
            bd.setMaximumHeight(16777215 if btn.isChecked() else 0)
        if hasattr(self, "lbl_mode_note"):
            multi = kind in ("lrgb", "sho")
            self.lbl_mode_note.setText(
                "多通道(LRGB/SHO):可选「对齐子帧目录」直接后期,或选「原始素材叠加」走黑白相机"
                " per-filter 叠加(每组=一个通道的亮场+平场,按真实 FILTER 头分组校准对齐)。" if multi else "")
            self.lbl_mode_note.setVisible(multi)
        self._paint_phases()
        self._sync_indicators()

    def _polish_groups(self):
        """统一给分组框加内边距,并把纯布局容器透明化。

        不用 QSS 的 QGroupBox padding —— 它在 QGroupBox 上左右不对称,右侧控件会贴着边框
        甚至溢出。改用布局 contentsMargins,插入量确定且对称;新加的分组框自动生效。
        """
        for gb in self.findChildren(QGroupBox):
            lay = gb.layout()
            if lay is None:
                continue
            if gb.objectName() in ("runprog", "exportbox"):   # 运行卡进度块 / 导出容器:边距自己管
                continue
            if gb.objectName() == "gb_prog":            # 进度条是一行,要更薄
                lay.setContentsMargins(12, 8, 12, 8)
                continue
            if gb.objectName() in ("gb_main", "gb_quiet", "gb_result"):  # 自带头条,边距在内层 body
                continue
            lay.setContentsMargins(14, 16, 14, 14)
            if lay.spacing() < 8:
                lay.setSpacing(8)
        # 纯布局容器透明化(见 QSS #rowbg 注释);已命名的(paramrow/roadrow…)保持自己的样式
        for ch in self.findChildren(QWidget):
            if ch.objectName():
                continue
            if type(ch) is QWidget or isinstance(ch, FlowBar):
                ch.setObjectName("rowbg")

    def _param(self, vbox, key, label, cls, *rng, slider=False):
        """一行参数(标签 + 控件)。行本体打 #paramrow 拿到卡片底色,并注册进 _param_rows,
        供 _select_flow 按流程 setVisible()。"""
        roww = QWidget(); roww.setObjectName("paramrow")
        h = QHBoxLayout(roww); h.setContentsMargins(11, 3, 10, 3); h.setSpacing(10)
        if cls is QCheckBox:
            w = QCheckBox(); self._tr(w, label)      # 登记 i18n:切英文时复选框文案跟随
            h.addWidget(w, 1)
        else:
            lab = QLabel(); lab.setObjectName("plabel"); self._tr(lab, label)  # 登记 i18n:参数行标签跟随
            cls = {QDoubleSpinBox: _NoWheelSpin, QSpinBox: _NoWheelIntSpin}.get(cls, cls)  # 禁滚轮改值版
            w = cls(); lo, hi, step, val = rng
            w.setRange(lo, hi); w.setSingleStep(step); w.setValue(val)
            if isinstance(w, QDoubleSpinBox):
                w.setDecimals(2)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            w.setMinimumWidth(88); w.setMaximumWidth(108)
            if slider:
                lab.setMinimumWidth(94)
                sl = _NoWheelSlider(Qt.Horizontal); sl.setMinimumWidth(54)   # 禁滚轮改值(防误操作)
                n = max(1, int(round((hi - lo) / step)))
                sl.setRange(0, n); sl.setValue(int(round((val - lo) / step)))
                guard = {"busy": False}

                def _from_slider(i, _w=w, _lo=lo, _st=step, _g=guard):
                    if _g["busy"]:
                        return
                    _g["busy"] = True; _w.setValue(_lo + i * _st); _g["busy"] = False

                def _from_spin(v, _sl=sl, _lo=lo, _st=step, _g=guard):
                    if _g["busy"]:
                        return
                    _g["busy"] = True
                    _sl.setValue(int(round((v - _lo) / _st))); _g["busy"] = False

                sl.valueChanged.connect(_from_slider)
                w.valueChanged.connect(_from_spin)
                self._param_sliders[key] = sl
                h.addWidget(lab, 0); h.addWidget(sl, 1); h.addWidget(w, 0)
            else:
                h.addWidget(lab, 1); h.addWidget(w, 0)
        vbox.addWidget(roww); self._param_rows[key] = roww
        return w

    def _divider(self):
        f = QFrame(); f.setFrameShape(QFrame.HLine); f.setFixedHeight(1)
        f.setStyleSheet(f"color:{self.theme['surf2']};")
        return f

    # ---------- 输入模式 / 原始叠加配置 ----------
    def _build_rawstack_panel(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 2, 0, 0); v.setSpacing(8)
        # 设备/相机选择器已上移到「给素材」顶部(所有模式可见,见 _build 材料区);此处只留原始叠加专有配置。
        detect = QPushButton(t("📁 自动识别文件夹")); detect.setObjectName("seg")
        detect.setCursor(Qt.PointingHandCursor)
        detect.setToolTip(t("选一个文件夹,按 FITS 头+文件名自动识别亮场/暗场/机内成片等 → 回填下面字段;"
                          "识别到机内成片时可选择重新叠加或直接优化成片"))
        detect.clicked.connect(self._autodetect_folder)
        v.addWidget(detect, alignment=Qt.AlignLeft)
        self.night_rows = []
        self.nights_box = QVBoxLayout(); self.nights_box.setSpacing(6); v.addLayout(self.nights_box)
        self.btn_add_night = QPushButton(t("+ 添加一晚")); self.btn_add_night.clicked.connect(lambda: self._add_night_row())
        v.addWidget(self.btn_add_night, alignment=Qt.AlignLeft)
        self._add_night_row()
        # 校准场库自动匹配:用户有一套按次整理的暗/偏/平库 → 指到库根,一键按亮场
        #   曝光/增益/温度/滤镜/时间自动配齐各晚校准场(统一原则,免手动一个个选)。见 calib_match。
        #   **放在暗场/偏置之前**(用户 2026-09-03):先指库 → 点自动匹配 → 回填下面的暗/偏,顺序更合逻辑。
        clr = QHBoxLayout(); clr.setSpacing(8)
        self.ed_caliblib = QLineEdit(config.get_setting("calib_library", ""))
        self.ed_caliblib.setPlaceholderText(t("(可选)校准场库根目录 → 按亮场自动匹配暗/偏/平各组"))
        self.ed_caliblib.setToolTip(
            t("指向你的校准场库根目录(内含按次整理的暗场/偏置/平场各组文件夹)。\n"
            "点『🔎 自动匹配』→ 按统一原则为每晚配齐并回填上面各字段:\n"
            "  • 暗/偏:温度最接近 → 温度相同再取拍摄时间最接近\n"
            "  • 平场:时间最接近 → 时间相同再比温度(随灰尘/对焦变,时效优先)\n"
            "硬性条件先过滤:暗=曝光+增益、偏=增益、平=滤镜,尺寸须一致。免去手动一个个选文件夹。"))
        bcl = QPushButton(t("浏览…")); bcl.clicked.connect(lambda: self._pick_dir(self.ed_caliblib))
        bmatch = QPushButton(t("🔎 自动匹配")); bmatch.setObjectName("segaccent")
        bmatch.setCursor(Qt.PointingHandCursor); bmatch.setToolTip(t("扫描校准场库,按上述原则为每晚自动配齐暗/偏/平并回填。"))
        bmatch.clicked.connect(self._autofill_calib_library)
        lcl = QLabel(t("校准库")); lcl.setObjectName("plabel"); lcl.setMinimumWidth(48)
        clr.addWidget(lcl); clr.addWidget(self.ed_caliblib, 1); clr.addWidget(bcl); clr.addWidget(bmatch)
        self.calib_lib_row = QWidget(); self.calib_lib_row.setLayout(clr)
        v.addWidget(self.calib_lib_row)
        # 暗场/偏置(放校准库之后:自动匹配会回填这两个字段)
        self.ed_dark = self._dir_row(v, "暗场", "…/Dark/…(共用,不打标签)")
        self.ed_bias = self._dir_row(v, "偏置", "…/Bias/…(共用,不打标签)")
        outrow = QHBoxLayout(); outrow.setSpacing(8)
        self.ed_stackout = QLineEdit(config.get_setting("stacking_output_base", "M:/Deepsky"))
        bo = QPushButton(t("浏览…")); bo.clicked.connect(lambda: self._pick_dir(self.ed_stackout))
        lo = QLabel(t("输出根")); lo.setObjectName("plabel"); lo.setMinimumWidth(48)
        outrow.addWidget(lo); outrow.addWidget(self.ed_stackout, 1); outrow.addWidget(bo); v.addLayout(outrow)
        trow = QHBoxLayout(); trow.setSpacing(8)
        self.ed_target = QLineEdit(); self.ed_target.setPlaceholderText(t("项目目录 如 260710-260724_2600mc_IC1396"))
        lt = QLabel(t("项目目录")); lt.setObjectName("plabel"); lt.setMinimumWidth(48)
        trow.addWidget(lt); trow.addWidget(self.ed_target, 1); v.addLayout(trow)
        return w

    def _dir_row(self, vbox, label, ph):
        r = QHBoxLayout(); r.setSpacing(8)
        ed = QLineEdit(); ed.setPlaceholderText(ph)
        b = QPushButton(t("浏览…")); b.clicked.connect(lambda: self._pick_dir(ed))
        lab = QLabel(label); lab.setObjectName("plabel"); lab.setMinimumWidth(48)
        r.addWidget(lab); r.addWidget(ed, 1); r.addWidget(b); vbox.addLayout(r)
        return ed

    MAX_NIGHTS = 24   # OSC 按晚,黑白 per-filter 按「通道组」(滤镜×晚),后者更易多,故放宽上限

    def _add_night_row(self):
        # 每晚只需"亮场 + 平场"两个目录。WBPP 的自定义滤镜标签(按晚配平场用)不再让用户选——
        # 它只是个每晚唯一的内部分组键,程序按行序自动生成 d1/d2/…(见 _raw_config)。
        if len(self.night_rows) >= self.MAX_NIGHTS:
            return
        roww = QWidget(); roww.setObjectName("nightrow")
        h = QHBoxLayout(roww); h.setContentsMargins(9, 5, 9, 5); h.setSpacing(7)
        mono = getattr(self, "_stack_device", "osc") == "mono"
        idx_lab = QLabel(""); idx_lab.setObjectName("seclabel"); idx_lab.setMinimumWidth(34)
        ed_l = QLineEdit(); ed_l.setPlaceholderText("通道亮场目录" if mono else "亮场目录")
        bl = QToolButton(); bl.setText(t("亮场…")); bl.clicked.connect(lambda: self._pick_dir(ed_l))
        bc = QToolButton(); bc.setText(t("🔍筛"))
        bc.setToolTip(t("筛帧:解拜耳+快速拉伸预览这组亮场,手动剔除有问题的帧(云/梯度/拖线/跑焦)。\n"
                        "被剔除的帧挪进子夹、不进 WBPP;可再次打开恢复。"))
        bc.clicked.connect(lambda: self._open_cull(ed_l))
        # 滤镜标签(OSC:窄带=普通亮场只是滤镜不同 → 标一下,叠加时按滤镜分组;mono 读真实 FILTER 头不需要)
        cb_filt = QComboBox()
        cb_filt.addItems([lab for _, lab in OSC_FILTERS])
        cb_filt.setToolTip(t("这组亮场用的滤镜。IR-UVcut=宽带(→RGB 底);Hα/OIII 等双窄带 →各成一组叠加、用于增强气体信号。\n"
                            "同滤镜的多晚会叠在一起;平场按此滤镜匹配、暗场按曝光匹配(与滤镜无关)。"))
        cb_filt.setMinimumWidth(118); cb_filt.setMaximumWidth(150)
        cb_filt.setVisible(not mono)
        ed_f = QLineEdit(); ed_f.setPlaceholderText("通道平场目录" if mono else "平场目录")
        bf = QToolButton(); bf.setText(t("平场…")); bf.clicked.connect(lambda: self._pick_dir(ed_f))
        rm = QToolButton(); rm.setText("✕"); rm.setToolTip(t("删除这一晚"))
        rm.clicked.connect(lambda: self._remove_night_row(roww))
        for wdg in (idx_lab, ed_l, bl, bc, cb_filt, ed_f, bf, rm):
            h.addWidget(wdg)
        h.setStretch(1, 2); h.setStretch(5, 2)   # ed_l / ed_f 拉伸(bc 插在 bl 后,ed_f 移到 idx5)
        self.night_rows.append({"w": roww, "idx": idx_lab, "light": ed_l, "flat": ed_f, "filt": cb_filt})
        self.nights_box.addWidget(roww)
        self._renumber_nights()

    def _remove_night_row(self, roww):
        if len(self.night_rows) <= 1:
            for r in self.night_rows:           # 只剩一行:× = 清空该行内容(亮/平场 + 滤镜复位),不删行
                if r["w"] is roww:
                    r["light"].clear(); r["flat"].clear()
                    if r.get("filt") is not None:
                        r["filt"].setCurrentIndex(0)
            return
        self.night_rows = [r for r in self.night_rows if r["w"] is not roww]
        roww.setParent(None); roww.deleteLater()
        self._renumber_nights()

    def _renumber_nights(self):
        """行序即晚序:删掉中间一行后重编号,标签也跟着重排(避免出现空号)。
        黑白 per-filter 下每行是「一个通道组」而非「一晚」,单位随设备切换。"""
        mono = getattr(self, "_stack_device", "osc") == "mono"
        for i, r in enumerate(self.night_rows):
            r["idx"].setText((t("第 {} 组") if mono else t("第 {} 晚")).format(i + 1))
            if r.get("filt") is not None:            # mono 读真实 FILTER 头分组 → 隐藏滤镜下拉;OSC 显示
                r["filt"].setVisible(not mono)

    def _add_reg_row(self):
        """对齐子帧目录行:目录 + 滤镜标签(与 nights 一致的分组模型,但已对齐子帧无需平场/校准)。"""
        roww = QWidget(); roww.setObjectName("nightrow")
        h = QHBoxLayout(roww); h.setContentsMargins(9, 5, 9, 5); h.setSpacing(7)
        ed = QLineEdit(); ed.setPlaceholderText(t("registered 对齐子帧目录"))
        bb = QToolButton(); bb.setText(t("浏览…")); bb.clicked.connect(lambda: self._pick_dir(ed))
        bc = QToolButton(); bc.setText(t("🔍筛"))
        bc.setToolTip(t("筛帧:快速拉伸预览这组对齐子帧,剔除有云层/景物遮挡/拖线的帧。\n"
                        "剔除的帧挪进子夹、不进整合;可再次打开恢复。"))
        bc.clicked.connect(lambda: self._open_cull(ed, is_registered=True))
        cb = QComboBox(); self._fill_filter_combo(cb, kind="reg")
        cb.setMinimumWidth(118); cb.setMaximumWidth(150)
        rm = QToolButton(); rm.setText("✕"); rm.setToolTip(t("删除"))
        rm.clicked.connect(lambda: self._remove_reg_row(roww))
        for w in (ed, bb, bc, cb, rm):
            h.addWidget(w)
        h.setStretch(0, 1)
        row = {"w": roww, "dir": ed, "filt": cb}
        self.reg_rows.append(row)
        ed.textChanged.connect(lambda txt, _r=row: self._auto_filter_row(_r, txt))
        self.reg_box.addWidget(roww)

    def _remove_reg_row(self, roww):
        if len(self.reg_rows) <= 1:
            for r in self.reg_rows:             # 只剩一行:× = 清空该行内容(目录 + 滤镜复位),不删行
                if r["w"] is roww:
                    r["dir"].clear()
                    if r.get("filt") is not None:
                        r["filt"].setCurrentIndex(0)
            return
        self.reg_rows = [r for r in self.reg_rows if r["w"] is not roww]
        roww.setParent(None); roww.deleteLater()

    def _filter_table(self):
        """母版行 / 对齐子帧行的滤镜下拉内容随相机变:彩色相机 = 宽带 + 三种双窄带;黑白 = 单个滤镜。"""
        return MONO_FILTERS if getattr(self, "_stack_device", "osc") == "mono" else OSC_FILTERS

    def _fill_filter_combo(self, cb, key=None, kind="master"):
        """按当前相机重填滤镜下拉(显示名 + 键存在 itemData 里),尽量保留 key,不在新表里就回到第一项。"""
        mono = getattr(self, "_stack_device", "osc") == "mono"
        cb.blockSignals(True)
        cb.clear()
        for k, lab in self._filter_table():
            cb.addItem(lab, k)
        i = cb.findData(key) if key else -1
        cb.setCurrentIndex(max(0, i))
        cb.blockSignals(False)
        if kind == "reg":
            tip = (t("这组对齐子帧的滤镜。R/G/B 是宽带,三组合成一张彩色图当底(L 暂不参与);"
                     "Hα/OIII 是窄带,给彩色底叠发射信号。填了目录会按目录名或文件头里的滤镜自动选好。") if mono
                   else t("这组对齐子帧的滤镜。IR-UVcut=宽带(→RGB 底);Hα/OIII 等双窄带 →整合成窄带母版,用于增强气体信号。"))
        else:
            tip = (t("这个母版的滤镜。R/G/B 是宽带,三张合成一张彩色图当底(L 暂不参与);"
                     "Hα/OIII 是窄带,给彩色底叠发射信号。选了文件会按文件头里的滤镜自动选好。") if mono
                   else t("这个母版的滤镜。IR-UVcut=宽带(→RGB 底);Hα/OIII·SII/OIII·Hβ/SII 双窄带 →给 RGB 叠发射信号。"))
        cb.setToolTip(tip)

    def _auto_filter_row(self, r, path):
        """黑白相机:填了母版文件 / 子帧目录 → 按文件头(或文件名)里的滤镜自动选下拉。认不出就不动。
        彩色相机不自动选(双窄带母版的 FILTER 头各家写法不一,IR-UVcut 与双窄带靠用户标)。"""
        if getattr(self, "_stack_device", "osc") != "mono" or r.get("filt") is None:
            return
        import re as _re
        p = (path or "").strip()
        k = ""
        try:
            if p and os.path.isdir(p):
                m = _re.search(r"FILTER-([^_/\\]+)", os.path.basename(p.rstrip("/\\")), _re.I)
                k = devices.mono_filter_key(m.group(1)) if m else ""
                if not k:
                    fs = sorted(str(q) for q in Path(p).glob("*.xis*")) + sorted(str(q) for q in Path(p).glob("*.fit*"))
                    k = devices.mono_filter_of(fs[0]) if fs else ""
            elif p and os.path.isfile(p):
                k = devices.mono_filter_of(p)
        except Exception:
            k = ""
        if k:
            i = r["filt"].findData(k)
            if i >= 0:
                r["filt"].setCurrentIndex(i)

    def _mono_master_map(self):
        """黑白相机·已叠加母版:{滤镜键: 文件}。同一滤镜填了多行只取第一行(返回的第二项列出被忽略的)。"""
        out, dup = {}, []
        for m in self._master_config():
            k = m.get("filter")
            if k in out:
                dup.append(m["file"])
            else:
                out[k] = m["file"]
        return out, dup

    def _reg_config(self):
        """对齐子帧目录模式:按滤镜分组的目录列表 [{dir, filter}](供 worker 各滤镜组直接整合)。"""
        out = []
        for r in self.reg_rows:
            d = r["dir"].text().strip()
            if d:
                fk = (r["filt"].currentData() or "uvir") if r.get("filt") is not None else "uvir"
                out.append({"dir": d.replace("\\", "/"), "filter": fk})
        return out

    def _add_master_row(self, filt_idx=0):
        """已叠加母版行:母版**文件** + 滤镜标签(与对齐子帧一致的分组模型,但已是 master 无需整合)。
        **首行**的输入框兼任 self.ed_input(宽带底;自动识别/机内成片载入/导出命名沿用它)。"""
        roww = QWidget(); roww.setObjectName("nightrow")
        h = QHBoxLayout(roww); h.setContentsMargins(9, 5, 9, 5); h.setSpacing(7)
        ed = QLineEdit(); ed.setPlaceholderText(t("已叠加母版 .xisf / .fit / .fits"))
        bb = QToolButton(); bb.setText(t("浏览…")); bb.clicked.connect(lambda: self._pick_file(ed))
        cb = QComboBox(); self._fill_filter_combo(cb, kind="master")
        cb.setMinimumWidth(118); cb.setMaximumWidth(150)
        if filt_idx:
            cb.setCurrentIndex(filt_idx)
        rm = QToolButton(); rm.setText("✕"); rm.setToolTip(t("删除"))
        rm.clicked.connect(lambda: self._remove_master_row(roww))
        for w in (ed, bb, cb, rm):
            h.addWidget(w)
        h.setStretch(0, 1)
        if not self.master_rows:            # 首行 = 宽带底,兼任 ed_input
            self.ed_input = ed
        row = {"w": roww, "file": ed, "filt": cb}
        self.master_rows.append(row)
        ed.textChanged.connect(lambda txt, _r=row: self._auto_filter_row(_r, txt))
        self.master_box.addWidget(roww)
        return self.master_rows[-1]

    def _remove_master_row(self, roww):
        if len(self.master_rows) <= 1:
            for r in self.master_rows:          # 只剩一行:× = 清空该行内容(文件框 + 滤镜复位宽带),不删行
                if r["w"] is roww:
                    r["file"].clear()
                    if r.get("filt") is not None:
                        r["filt"].setCurrentIndex(0)
            return
        self.master_rows = [r for r in self.master_rows if r["w"] is not roww]
        roww.setParent(None); roww.deleteLater()
        self.ed_input = self.master_rows[0]["file"]   # 首行可能被删 → ed_input 重指向新首行

    def _master_config(self):
        """已叠加母版模式:[{file, filter}]。宽带(uvir)=RGB 底;窄带=给 RGB 叠发射信号(直接用 master,无需整合)。"""
        out = []
        for r in self.master_rows:
            f = r["file"].text().strip()
            if f:
                fk = (r["filt"].currentData() or "uvir") if r.get("filt") is not None else "uvir"
                out.append({"file": f.replace("\\", "/"), "filter": fk})
        return out

    def _mode0_nb_master(self):
        """已叠加母版模式的**第一路**窄带 master(供现融合引擎的单窄带路径 ha_dir);
        其它模式返回 ''(窄带走滤镜标签 → worker 里 _ha_from_stack)。多路窄带(HO+Hβ/SII)留待后续引擎。"""
        if getattr(self, "_input_mode", 0) != 0 or getattr(self, "_stack_device", "osc") == "mono":
            return ""                       # 黑白的窄带母版走 mono_masters(逐通道),不走彩色的双窄带入口
        for m in self._master_config():
            if not _is_bb(m.get("filter")):
                return m["file"]
        return ""

    def _apply_master_config(self, masters):
        """恢复已叠加母版多行(文件+滤镜):行数多退少补,逐行填(用户 2026-09-07 工程持久化)。"""
        if not masters or not hasattr(self, "master_rows"):
            return
        need = max(1, len(masters))
        while len(self.master_rows) > need:
            self._remove_master_row(self.master_rows[-1]["w"])
        while len(self.master_rows) < need:
            self._add_master_row()
        for i, m in enumerate(masters):
            if i >= len(self.master_rows):
                break
            r = self.master_rows[i]
            r["file"].setText(m.get("file", "") or "")
            if r.get("filt") is not None:
                _i = r["filt"].findData(m.get("filter", "uvir"))
                if _i >= 0:
                    r["filt"].setCurrentIndex(_i)

    def _apply_reg_config(self, regs):
        """恢复对齐子帧目录多行(目录+滤镜)。"""
        if not regs or not hasattr(self, "reg_rows"):
            return
        need = max(1, len(regs))
        while len(self.reg_rows) > need:
            self._remove_reg_row(self.reg_rows[-1]["w"])
        while len(self.reg_rows) < need:
            self._add_reg_row()
        for i, g in enumerate(regs):
            if i >= len(self.reg_rows):
                break
            r = self.reg_rows[i]
            r["dir"].setText(g.get("dir", "") or "")
            if r.get("filt") is not None:
                _i = r["filt"].findData(g.get("filter", "uvir"))
                if _i >= 0:
                    r["filt"].setCurrentIndex(_i)

    def _dialog_start(self, ed, is_file=False):
        """目录/文件对话框的起始路径(用户 2026-09-06:浏览应打开已填地址,别落进程 CWD)。
        目录框→已填目录本身;文件框→已填文件的父目录;路径不存在则逐级退到存在的上级,再退主目录。"""
        t0 = ""
        try:
            t0 = (ed.text() or "").strip().replace("\\", "/") if ed is not None else ""
        except Exception:
            t0 = ""
        if t0:
            if is_file or os.path.isfile(t0):
                t0 = os.path.dirname(t0) or t0
            p = t0
            for _ in range(5):                     # 逐级退到存在的目录
                if p and os.path.isdir(p):
                    return p
                _np = os.path.dirname(p)
                if not _np or _np == p:
                    break
                p = _np
        # 字段为空:优先落到"上次浏览过的目录"(仅第一次、还没浏览过时才落主目录)
        lb = (getattr(self, "_last_browse_dir", "")
              or config.get_setting("browse.last_dir") or "").strip().replace("\\", "/")
        if lb and os.path.isdir(lb):
            return lb
        return str(Path.home()).replace("\\", "/")

    def _remember_browse(self, path):
        """记住这次浏览到的目录(选的是文件→取其父目录),供下次字段为空时作起始目录;持久化到设置。"""
        try:
            d = (path or "").replace("\\", "/")
            if d and os.path.isfile(d):
                d = os.path.dirname(d)
            if not d or not os.path.isdir(d):
                return
            self._last_browse_dir = d
            _s = config.load_settings()
            _s.setdefault("browse", {})["last_dir"] = d
            config.save_settings(_s)
        except Exception:
            pass

    def _pick_dir(self, ed):
        p = QFileDialog.getExistingDirectory(self, t("选择目录"), self._dialog_start(ed))
        if p:
            ed.setText(p.replace("\\", "/")); self._remember_browse(p)

    def _pick_file(self, ed):
        p, _ = QFileDialog.getOpenFileName(self, t("选择文件"), self._dialog_start(ed, is_file=True),
                                           t("图像 (*.xisf *.fit *.fits)"))
        if p:
            ed.setText(p.replace("\\", "/")); self._remember_browse(p)

    def _open_cull(self, ed_light, is_registered=False):
        """筛帧:枚举目录里的帧(递归含 Dwarf 时间戳子夹)→ 缩略图对话框手动剔除坏帧(云/景物遮挡/拖线)。
        剔除的帧挪进各帧目录的 _ttlot_culled/(WBPP 与整合都跳过该子夹),不进 registered/master;可逆。
        is_registered=对齐子帧模式:帧已解拜耳(RGB 或抽出的窄带单通道)→ 绝不再按拜耳解(pat=None)。"""
        d = (ed_light.text() or "").strip().replace("\\", "/")
        if not d or not os.path.isdir(d):
            QMessageBox.warning(self, t("筛帧"),
                                t("请先填/选这组的对齐子帧目录。") if is_registered
                                else t("请先填/选这组的亮场目录(含原始单帧)。"))
            return
        if is_registered:
            pat = None            # 对齐子帧已解拜耳,绝不再按拜耳解(2D 窄带单通道会被误当拜耳)
        else:
            dev = getattr(self, "_stack_device", "osc")
            pat = {"seestar": "GRBG", "dwarf": "RGGB"}.get(dev)   # 头里有 BAYERPAT 以头为准;mono→None 走灰度
        self._append(f"[筛帧] 扫描 {d} …(解拜耳+快速拉伸预览,可能需数秒)")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            frames = pipeline.list_cullable_frames(d)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, t("筛帧"), t("扫描失败:{}").format(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not frames:
            QMessageBox.information(self, t("筛帧"),
                                   t("该目录下没找到原始单帧(校准场已排除;若是母版/对齐子帧请用对应模式)。"))
            return
        n_cull0 = sum(1 for f in frames if f.get("culled"))
        self._append(f"[筛帧] 找到 {len(frames)} 帧" + (f"(其中 {n_cull0} 帧上次已剔除)" if n_cull0 else "") + "。")
        dlg = FrameCullDialog(frames, pat, self._append, self)
        dlg.exec_()

    def _select_input_mode(self, idx):
        self._input_mode = idx
        self.in_mode_btns[idx].setChecked(True)
        if hasattr(self, "pg_master"):
            self.pg_master.setVisible(idx == 0)      # 已叠加母版(多行+滤镜)
        if hasattr(self, "pg_reg"):
            self.pg_reg.setVisible(idx == 1)         # 对齐子帧目录(多目录+滤镜)
        self.pg_raw.setVisible(idx == 2)             # 原始素材叠加
        self.chk_detrail.setVisible(idx == 2)        # 去线在 WBPP 前;对齐子帧已定稿不再去线
        self._sync_narrowband_vis()                  # 窄带融合预设:仅 RGB 融合流程显示(三模式都走滤镜标签)
        if hasattr(self, "detrail_row"):
            self.detrail_row.setVisible(idx == 2)     # 去线在 WBPP 前(原始叠加);对齐子帧/母版不去线
        if hasattr(self, "lbl_mode_name"):
            self.lbl_mode_name.setText(t(MODE_NAMES[idx]))
        self._sync_indicators()

    def _select_stack_device(self, key):
        """切换原始叠加的设备类型 → 更新校验策略提示;智能望远镜可缺校准场。
        黑白 per-filter:每行是「通道组」,联动按钮/占位符/行号的措辞。"""
        self._stack_device = key
        for k, b in self.dev_btns.items():
            b.setChecked(k == key)
        self.lbl_stack_dev_hint.setText(STACK_DEV_MAP.get(key, STACK_DEV_MAP["osc"])[2])
        # Seestar 机内已校准、无需校准场库匹配 → 隐藏校准库行;其余(OSC/黑白/Dwarf)显示
        if hasattr(self, "calib_lib_row"):
            self.calib_lib_row.setVisible(key != "seestar")
        mono = key == "mono"
        if hasattr(self, "btn_add_night"):
            self.btn_add_night.setText("+ 添加一组通道" if mono else "+ 添加一晚")
        for r in getattr(self, "night_rows", []):
            r["light"].setPlaceholderText("通道亮场目录" if mono else "亮场目录")
            r["flat"].setPlaceholderText("通道平场目录" if mono else "平场目录")
        if getattr(self, "night_rows", None):
            self._renumber_nights()
        # 母版行 / 对齐子帧行的滤镜下拉随相机换表(黑白 = R/G/B/L/Hα/OIII/SII)
        for _kind, _rows, _fld in (("master", getattr(self, "master_rows", []), "file"),
                                   ("reg", getattr(self, "reg_rows", []), "dir")):
            for r in _rows:
                if r.get("filt") is not None:
                    _old = r["filt"].currentData()
                    self._fill_filter_combo(r["filt"], _old, kind=_kind)
                    if r["filt"].currentData() != _old:        # 原来的滤镜新表里没有 → 按文件重新识别
                        self._auto_filter_row(r, r[_fld].text())
        # 相机(OSC/黑白)变 → 派生 kind 变(如 纯RGB:OSC→rgb / 黑白→lrgb)→ 刷新参数可见性 + LRGB 专块
        if hasattr(self, "_param_rows"):
            self._apply_kind_vis(); self._sync_param_sections()

    def _check_dark_temp_match(self, light_dir, dark_dir):
        """记录亮/暗场温差(仅提示,不拦截)。按用户 2026-08 定稿的策略:直接用温差最近的暗场、
        不设温差阈值,故这里只报数不弹窗。温度读取见 devices.dir_temp(头 DET-TEMP/CCD-TEMP + 文件名兜底)。"""
        lt = devices.dir_temp(light_dir)
        dt = devices.dir_temp(dark_dir)
        if lt is not None and dt is not None:
            self._append(f"[温度] 亮场 {lt:.1f}℃ / 暗场 {dt:.1f}℃,温差 {abs(lt - dt):.1f}℃(已用温差最近的暗场)。")
        return True

    def _autofill_calib_library(self):
        """校准场库自动匹配:指到库根 → 按统一原则(暗/偏 温度→时间;平 时间→温度)为每晚配齐
        暗/偏/平并回填字段,免手动一个个选。硬性条件先过滤(暗=曝光+增益、偏=增益、平=滤镜、尺寸一致)。
        全局字段(暗/偏)用第一晚亮场作参考(同目标各晚曝光/增益通常一致);平场逐晚匹配(时效性优先)。"""
        lib = self.ed_caliblib.text().strip()
        if not lib or not Path(lib).exists():
            QMessageBox.warning(self, t("校准场库"), t("请先选择有效的校准场库根目录。"))
            return
        dev = getattr(self, "_stack_device", "osc")
        _label, pol, _hint = STACK_DEV_MAP.get(dev, STACK_DEV_MAP["osc"])
        night_lights = [r["light"].text().strip() for r in self.night_rows if r["light"].text().strip()]
        if not night_lights:
            QMessageBox.warning(self, t("校准场库"), t("请先填至少一晚(或一个通道)的亮场目录——自动匹配需读亮场特征。"))
            return
        # 持久化库路径(下次自动带出)
        try:
            _s = config.load_settings(); _s["calib_library"] = lib.replace("\\", "/"); config.save_settings(_s)
        except Exception:
            pass
        from . import calib_match
        QApplication.setOverrideCursor(Qt.WaitCursor)
        filled = []
        try:
            groups = calib_match.scan_library(lib, log=self._append)
            if not groups:
                QApplication.restoreOverrideCursor()
                QMessageBox.information(self, t("校准场库"), t("库里没扫描到暗/偏/平校准场组(检查库根目录是否含 FITS)。"))
                return
            ref_meta = calib_match.group_meta(night_lights[0]) or {}
            # 暗/偏:全局字段(设备策略非 skip 才配)
            if pol.get("dark") != "skip":
                g = calib_match.match(ref_meta, groups, "dark", log=self._append)
                if g:
                    self.ed_dark.setText(g["dir"])              # 字段显第1晚参考(叠加时逐晚各配各的)
                if len(night_lights) > 1:                       # **多晚:暗场逐晚按各晚温度配**(叠加时每晚各跑一次)
                    self._append("[校准库] 多晚:暗场**逐晚按各晚温度**匹配(叠加时每晚各用各自暗场、不共用;下为各晚):")
                    _pn = []
                    for i, ld in enumerate(night_lights):
                        lm = calib_match.group_meta(ld) or {}
                        gd = calib_match.match(lm, groups, "dark", log=lambda _m: None)
                        _t = lm.get("temp")
                        _nm = Path(gd['dir']).name if gd else '无匹配'
                        _pn.append(_nm)
                        self._append(f"    第{i+1}晚(曝光{lm.get('exp')}s 温度{'?' if _t is None else f'{_t:.0f}°'}) → {_nm}")
                    filled.append("暗场:逐晚匹配 %d 晚(%s)" %
                                  (len(night_lights), " / ".join(f"第{i+1}晚 {n}" for i, n in enumerate(_pn))))
                elif g:
                    filled.append(f"暗场 → {Path(g['dir']).name}")
            if pol.get("bias") != "skip":
                g = calib_match.match(ref_meta, groups, "bias", log=self._append)
                if g:
                    self.ed_bias.setText(g["dir"]); filled.append(f"偏置 → {Path(g['dir']).name}")
            # 平场:逐晚/逐通道(平场随时段/灰尘变,按各自亮场的时间/滤镜配)
            if pol.get("flat") != "skip":
                for i, r in enumerate(self.night_rows):
                    ld = r["light"].text().strip()
                    if not ld:
                        continue
                    lm = calib_match.group_meta(ld) or {}
                    g = calib_match.match(lm, groups, "flat", log=self._append)
                    if g:
                        r["flat"].setText(g["dir"]); filled.append(f"第{i + 1}组平场 → {Path(g['dir']).name}")
        finally:
            QApplication.restoreOverrideCursor()
        if filled:
            self._append("[校准库] 自动匹配完成:" + "; ".join(filled) + "。请核对后开始处理。")
            QMessageBox.information(self, t("校准场库"), "已按统一原则自动匹配并回填:\n\n  " + "\n  ".join(filled)
                                   + "\n\n(暗/偏:温度→时间;平:时间→温度。请核对后开始。)")
        else:
            QMessageBox.information(self, t("校准场库"),
                                   t("未匹配到符合硬性条件(曝光/增益/滤镜/尺寸)的校准场。\n"
                                   "请检查库里是否有与本次亮场同曝光/增益/滤镜/尺寸的校准场组。"))

    def _autodetect_folder(self):
        """选一个文件夹 → devices.scan 按文件特征分类 → 回填叠加面板;识别到机内成片时让用户选路径。"""
        d = QFileDialog.getExistingDirectory(self, t("选择素材文件夹(自动识别亮/暗场·机内成片)"), self._dialog_start(self.ed_input))
        if not d:
            return
        d = d.replace("\\", "/")
        self._remember_browse(d)
        self._append(f"[识别] 扫描 {d} …")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            sr = devices.scan(d)
            plan = devices.stacking_plan(sr)
        finally:
            QApplication.restoreOverrideCursor()
        summ = "  ".join(f"{t}×{a['count']}" for t, a in sr["summary"].items()) or "(未识别到 FITS)"
        self._append(f"[识别] 设备={sr['device']} | {summ}")
        n_sub = len(sr["groups"].get("light", []))
        n_stk = len(plan["stacked_files"])
        # 【混合 Seestar 目录】同目标堆多会话/多滤镜(见 group_frames)→ 检测到就弹分组选择,
        #   让用户挑会话/滤镜、按 RGB/HO 路由,避免盲叠混不同夜/滤镜致配准错乱。仅当有子帧时。
        if n_sub:
            try:
                from . import stack_engine
                groups = stack_engine.group_frames(d, log=self._append)
            except Exception as _ge:
                groups = []
                self._append(f"[识别] 分组探测跳过({_ge})")
            sess = {g["session"] for g in groups}
            filt = {g["filter"] for g in groups}
            if groups and (len(sess) > 1 or len(filt) > 1):     # 真·混合(多会话 或 多滤镜)
                if self._pick_groups_and_fill(d, groups):
                    return                                       # 已按用户选择回填,结束
                # 用户取消分组 → 落到原逻辑(整目录)
        if n_sub and n_stk:                     # 子帧 + 机内成片并存 → 让用户选(用户 2026-08 定)
            box = QMessageBox(self); box.setWindowTitle(t("发现子帧和机内成片"))
            box.setIcon(QMessageBox.Question)
            box.setText(t("识别到 {} 张子帧亮场 + {} 张机内成片。\n重新叠加子帧(质量更好、更慢),还是直接优化机内成片(快)?").format(n_sub, n_stk))
            b_re = box.addButton(t("重新叠加子帧"), QMessageBox.AcceptRole)
            b_opt = box.addButton(t("优化机内成片"), QMessageBox.ActionRole)
            box.addButton(t("取消"), QMessageBox.RejectRole)
            box.exec_()
            c = box.clickedButton()
            if c is b_opt:
                return self._use_stacked_master(plan)
            if c is not b_re:
                return
        elif n_stk and not n_sub:               # 只有机内成片
            return self._use_stacked_master(plan)
        elif not n_sub:
            QMessageBox.information(self, t("自动识别"), t("未识别到可叠加的亮场子帧。\n{}").format(summ))
            return
        self._fill_rawstack_from_plan(d, sr, plan)

    def _pick_groups_and_fill(self, folder, groups):
        """混合 Seestar 目录 → 弹分组选择框(会话×滤镜,标 RGB/HO 路由)→ 用户勾选后按组硬链接分拣、
        回填面板。返回 True=已处理(回填完),False=用户取消。宽带(rgb)组回填为亮场行;窄带(narrowband)
        组同样回填亮场行(zero-PI HOO/RGB+HO 从亮场目录叠),用户按需在参数区选无 PI RGB(填窄带目录=HO)。"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QLabel, QDialogButtonBox, QScrollArea, QWidget
        dlg = QDialog(self); dlg.setWindowTitle(t("混合目录 · 选择要叠加的组"))
        dlg.setMinimumWidth(560)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(f"此目录混了 {len({g['session'] for g in groups})} 个拍摄夜 / "
                           f"{len({g['filter'] for g in groups})} 种滤镜。勾选要叠加的组"
                           "(宽带→RGB,窄带→HO/HOO;不同夜/滤镜请分别处理):"))
        scr = QScrollArea(); scr.setWidgetResizable(True); box = QWidget(); bv = QVBoxLayout(box)
        _KIND = {"rgb": "宽带·RGB", "narrowband": "窄带·HO", "unknown": "未知"}
        checks = []
        biggest = max(groups, key=lambda g: g["count"])         # 默认勾最大的一组
        for g in groups:
            t0 = g["t0"]; ts = f"{t0[:4]}-{t0[4:6]}-{t0[6:8]} {t0[8:10]}:{t0[10:12]}" if len(t0) >= 12 else g["date"]
            cb = QCheckBox(f"会话{g['session']}  {ts}   FILTER={g['filter']}  EXP={g['exp']}s   "
                           f"{g['count']}帧   [{_KIND.get(g['kind'], g['kind'])}]")
            cb.setChecked(g is biggest)
            bv.addWidget(cb); checks.append((cb, g))
        bv.addStretch(1); scr.setWidget(box); v.addWidget(scr, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); v.addWidget(bb)
        if dlg.exec_() != QDialog.Accepted:
            return False
        chosen = [g for cb, g in checks if cb.isChecked()]
        if not chosen:
            QMessageBox.information(self, t("分组"), t("未勾选任何组。")); return False
        # 按组硬链接分拣到 _ttgroups/<session>_<filter>_<exp>/
        import os as _os
        base = folder.rstrip("/") + "/_ttgroups"
        self._select_stack_device("seestar")                    # 混合 Seestar → 智能望远镜策略(lights-only)
        light_dirs = []
        for g in chosen:
            gd = f"{base}/s{g['session']}_{g['filter']}_{g['exp']}s".replace(" ", "")
            if _os.path.exists(gd):
                shutil.rmtree(gd, ignore_errors=True)
            _os.makedirs(gd, exist_ok=True)
            for i, f in enumerate(g["frames"]):
                dst = f"{gd}/L_{i:05d}.fit"
                try:
                    _os.link(f, dst)                            # 硬链接(同盘秒建、不占空间)
                except OSError:
                    shutil.copy2(f, dst)                        # 跨盘退回复制
            light_dirs.append(gd.replace("\\", "/"))
            self._append(f"[分组] 会话{g['session']} {g['filter']} {g['exp']}s {g['count']}帧 → {gd}")
        self._set_nights(light_dirs, [], True)                  # 每组一个亮场行,无平场
        self.ed_dark.setText(""); self.ed_bias.setText("")
        if not self.ed_target.text().strip():
            self.ed_target.setText(_os.path.basename(folder.rstrip("/")).replace("_sub", "").strip())
        kinds = {g["kind"] for g in chosen}
        hint = ""
        if kinds == {"narrowband"}:
            hint = " 全是窄带 → 参数区勾『无 PI RGB』当 HO/HOO 处理(或后续做 RGB+HO)。"
        elif "rgb" in kinds and "narrowband" in kinds:
            hint = " 含宽带+窄带 → 宽带组出 RGB、窄带组出 HO,可做 RGB+HO 融合。"
        self._append(f"[分组] 已回填 {len(chosen)} 组亮场({sum(g['count'] for g in chosen)} 帧)。{hint}核对后开始。")
        return True

    def _use_stacked_master(self, plan):
        """用机内成片直接进后期:切到「已叠加母版」模式并载入最大的那张成片(通常叠得最多)。"""
        files = [f for f in plan["stacked_files"] if Path(f).exists()]
        if not files:
            QMessageBox.information(self, t("优化成片"), t("没有找到机内成片文件。"))
            return
        best = max(files, key=lambda p: Path(p).stat().st_size).replace("\\", "/")
        self._select_input_mode(0)
        self.ed_input.setText(best)
        self._append(f"[识别] 已切到「已叠加母版」,载入机内成片:{Path(best).name}")

    def _set_nights(self, light_dirs, flat_dirs, skip_flat):
        """把 night 行数调成 = len(light_dirs)(至少 1),并回填每晚亮场/平场目录。"""
        want = max(1, len(light_dirs))
        while len(self.night_rows) > want:
            self._remove_night_row(self.night_rows[-1]["w"])
        while len(self.night_rows) < want:
            self._add_night_row()
        for i, r in enumerate(self.night_rows):
            r["light"].setText(light_dirs[i] if i < len(light_dirs) else "")
            r["flat"].setText("" if skip_flat else (flat_dirs[i] if i < len(flat_dirs) else ""))

    def _fill_rawstack_from_plan(self, folder, sr, plan):
        """把识别结果回填到叠加面板(设备/亮场/暗场等)。同一目录混放多类型时先硬链接分拣。"""
        dev = plan["device"] if plan["device"] in STACK_DEV_MAP else "osc"
        self._select_stack_device(dev)
        _label, pol, _hint = STACK_DEV_MAP[dev]
        skip_flat = pol.get("flat") == "skip"
        light_dirs, dark_dirs = plan["light_dirs"], plan["dark_dirs"]
        flat_dirs, bias_dirs = plan["flat_dirs"], plan["bias_dirs"]
        if plan["mixed"]:
            types = ["light"] + [t for t in ("dark", "flat", "bias") if pol.get(t) != "skip"]
            stage = devices.stage_frames(sr, folder.rstrip("/") + "/_ttstage", types=types)
            light_dirs = [stage["light"]] if "light" in stage else []
            dark_dirs = [stage["dark"]] if "dark" in stage else []
            flat_dirs = [stage["flat"]] if "flat" in stage else []
            bias_dirs = [stage["bias"]] if "bias" in stage else []
            self._append(f"[识别] 同一文件夹混放多类型 → 已按类型硬链接分拣到 {folder}/_ttstage/")
        self._set_nights(light_dirs, flat_dirs, skip_flat)
        self.ed_dark.setText("" if pol.get("dark") == "skip" else (dark_dirs[0] if dark_dirs else ""))
        self.ed_bias.setText("" if pol.get("bias") == "skip" else (bias_dirs[0] if bias_dirs else ""))
        if not self.ed_target.text().strip():
            import os as _os
            self.ed_target.setText(_os.path.basename(folder.rstrip("/")).replace("_sub", "").strip())
        tail = ",暗场 1 个" if (dark_dirs and pol.get("dark") != "skip") else ""
        self._append(f"[识别] 已回填:{len(light_dirs)} 个亮场目录{tail}。核对后点『开始处理』。")
        # Dwarf 暗场常在单独的 DWARF_DARK 文件夹,此文件夹没扫到暗场 → 引导再选一个
        if pol.get("dark") == "reqtemp" and not self.ed_dark.text().strip():
            r = QMessageBox.question(
                self, t("选择暗场文件夹"),
                t("{} 需要暗场,但此文件夹里没识别到(暗场通常在单独的 DWARF_DARK 文件夹)。\n现在去选暗场文件夹吗?").format(_label),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                dd = QFileDialog.getExistingDirectory(self, t("选择暗场文件夹"), self._dialog_start(self.ed_dark))
                if dd:
                    self.ed_dark.setText(dd.replace("\\", "/"))
                    self._remember_browse(dd)
                    self._append(f"[识别] 暗场目录:{dd}")

    def _raw_config(self):
        dev = getattr(self, "_stack_device", "osc")
        _label, pol, _hint = STACK_DEV_MAP.get(dev, STACK_DEV_MAP["osc"])
        if dev == "mono":
            # 黑白 per-filter:每行=一个通道(亮场+平场),**不打标签**(WBPP 读真实 FILTER 头分组);
            #   平场按 FILTER 配光、暗场按曝光配光、偏置全局。暗场填父目录 → 展开各曝光子夹。
            lights = [r["light"].text().strip() for r in self.night_rows if r["light"].text().strip()]
            flats = [r["flat"].text().strip() for r in self.night_rows if r["flat"].text().strip()]
            darks = []
            darkp = self.ed_dark.text().strip()
            if darkp:
                import glob as _g
                import os as _o
                subs = sorted(d.replace("\\", "/") for d in _g.glob(darkp + "/*") if _o.path.isdir(d))
                darks = subs if subs else [darkp.replace("\\", "/")]
            return {"device": "mono", "lights": lights, "flats": flats, "darks": darks,
                    "bias": self.ed_bias.text().strip(),
                    "out_base": self.ed_stackout.text().strip(), "target": self.ed_target.text().strip()}
        skip_flat = pol.get("flat") == "skip"      # Dwarf:平场/偏置不用,即便填了也丢弃
        nights = []
        for r in self.night_rows:
            lt = r["light"].text().strip()
            fl = "" if skip_flat else r["flat"].text().strip()
            if lt or fl:
                # filter = 该行滤镜(IR-UVcut 宽带 / Hα-OIII 等双窄带)。同滤镜多晚叠一起 → 各出一个 master。
                #   tag 仍每行唯一(供 WBPP 逐行配平场:平场按晚/按次不同);分组/路由靠 filter。
                _fk = OSC_FILTER_KEYS[r["filt"].currentIndex()] if r.get("filt") else "uvir"
                nights.append({"light": lt, "flat": fl, "tag": f"d{len(nights) + 1}", "filter": _fk})
        dark = "" if pol.get("dark") == "skip" else self.ed_dark.text().strip()
        bias = "" if pol.get("bias") == "skip" else self.ed_bias.text().strip()
        return {"nights": nights, "dark": dark, "bias": bias,
                "out_base": self.ed_stackout.text().strip(), "target": self.ed_target.text().strip(),
                "device": dev, "calib_library": self.ed_caliblib.text().strip().replace("\\", "/")}

    def _apply_raw_config(self, raw):
        """把 .ttproj 里存的原始叠加配置(_raw_config 的产物)恢复回控件:逐晚/组行(亮/平/滤镜)、
        校准库、暗/偏、输出根。支持 OSC/Dwarf/Seestar(nights)与黑白(lights/flats/darks 列表)两形态。
        尽力而为——缺字段/控件一律跳过,不打断载入(设备已在此之前恢复,行的 mono/OSC 版式已正确)。"""
        if not raw or not hasattr(self, "night_rows"):
            return
        import os as _o
        # 1) 组装「行」列表:(亮场, 平场, 滤镜key)。黑白按 lights/flats 索引配对(无滤镜);其余读 nights。
        if raw.get("device") == "mono" or ("nights" not in raw and "lights" in raw):
            lights = raw.get("lights") or []
            flats = raw.get("flats") or []
            rows = [(lights[i] if i < len(lights) else "",
                     flats[i] if i < len(flats) else "", "uvir")
                    for i in range(max(len(lights), len(flats)))]
            darks = raw.get("darks") or []      # _raw_config 把父目录展开成各曝光子夹 → dirname 还原父目录
            if darks and hasattr(self, "ed_dark"):
                self.ed_dark.setText(_o.path.dirname(darks[0]) if len(darks) > 1 else darks[0])
        else:
            rows = [(n.get("light", ""), n.get("flat", ""), n.get("filter", "uvir"))
                    for n in (raw.get("nights") or [])]
            if hasattr(self, "ed_dark"):
                self.ed_dark.setText(raw.get("dark", "") or "")
            if hasattr(self, "ed_caliblib") and raw.get("calib_library"):
                self.ed_caliblib.setText(raw.get("calib_library", ""))
        # 2) 行数对齐:多退少补(至少留 1 行,不超过 MAX_NIGHTS 上限——否则 _add_night_row 静默拒绝会死循环)
        need = max(1, min(len(rows), self.MAX_NIGHTS))
        while len(self.night_rows) > need:
            self._remove_night_row(self.night_rows[-1]["w"])
        while len(self.night_rows) < need:
            self._add_night_row()
        # 3) 逐行填值
        for i, (lt, fl, fk) in enumerate(rows):
            if i >= len(self.night_rows):
                break
            r = self.night_rows[i]
            r["light"].setText(lt or "")
            r["flat"].setText(fl or "")
            if r.get("filt") is not None:
                try:
                    r["filt"].setCurrentIndex(OSC_FILTER_KEYS.index(fk))
                except ValueError:
                    pass
        # 4) 其余公共字段
        if hasattr(self, "ed_bias"):
            self.ed_bias.setText(raw.get("bias", "") or "")
        if hasattr(self, "ed_stackout") and raw.get("out_base"):
            self.ed_stackout.setText(raw.get("out_base", ""))
        self._renumber_nights()

    # ---------- 主题 ----------
    def _apply_titlebar_theme(self):
        """把 Windows 原生标题栏染成与当前主题一致的明/暗(DWM API),不做无边框自定义标题栏。
        非 Windows / 老系统 / 失败一律静默跳过。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            val = ctypes.c_int(1 if self.theme is DARK else 0)
            dwm = ctypes.windll.dwmapi
            for attr in (20, 19):     # 20=Win10 2004+/Win11;19=较老版本的属性号
                if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                    break
        except Exception:
            pass

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(qss(self.theme))
        self._apply_titlebar_theme()       # 标题栏跟随主题明/暗
        self._refresh_runner()
        self._paint_phases()
        if hasattr(self, "banner"):
            self.banner.set_colors(self.theme['text'], self.theme['text'])   # 品牌字用正文色(绿只留给行动)
        self._repaint_icons()
        self._sync_steps()
        self._sync_indicators()
        self._sync_caret()
        self._apply_button_shadows()       # 摘掉旧版按钮投影(扁平 + 发丝描边)
        if hasattr(self, "_glow_fx"):       # 主 CTA 柔光圈随主题重设颜色(保持半透明)
            for _eff in self._glow_fx:
                _gc = QColor(self.theme['accent']); _gc.setAlpha(90)
                _eff.setColor(_gc)

    def _apply_button_shadows(self):
        """【精修 2026-10-10:按钮不再加黑投影】设计稿是扁平 + 发丝描边(质感交给 QSS 的 1px 边框),
        投影让每个按钮都浮起来、层级反而乱。这里只负责把旧版加过的投影摘掉(切主题/动态建按钮后照常调用)。
        主 CTA 的绿光圈在 _init_primary_glow,不受影响。"""
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QToolButton
        btns = self.findChildren(QPushButton) + self.findChildren(QToolButton)
        cta = (getattr(self, "btn_run", None), getattr(self, "btn_export", None))
        for b in btns:
            if b in cta:
                continue
            if isinstance(b.graphicsEffect(), QGraphicsDropShadowEffect):
                b.setGraphicsEffect(None)

    def _init_primary_glow(self):
        """主 CTA(开始处理 / 导出成片)常驻一层随应用心跳呼吸的信号绿辉光。
        QPropertyAnimation 驱动 QGraphicsDropShadowEffect 的 blurRadius,与状态点/品牌标记同 ~4.6s 拍。"""
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        self._glow_fx = []
        self._run_glow = None                       # btn_run 的辉光:处理中(disabled)时关掉,免"暗按钮+绿光晕"
        for btn in (getattr(self, "btn_run", None), getattr(self, "btn_export", None)):
            if btn is None:
                continue
            # 【精修 2026-10-10】静态柔光圈,不再呼吸:规范里呼吸只给「正在进行」的状态点,
            #   主按钮常驻呼吸会和状态点抢注意力
            eff = QGraphicsDropShadowEffect(btn)
            eff.setOffset(0, 0)
            _gc = QColor(self.theme['accent']); _gc.setAlpha(90)
            eff.setColor(_gc)
            eff.setBlurRadius(14)
            btn.setGraphicsEffect(eff)
            self._glow_fx.append(eff)
            if btn is getattr(self, "btn_run", None):
                self._run_glow = eff

    def _set_run_glow(self, on: bool):
        """处理中(btn_run disabled 变暗)关掉绿辉光,免得只剩一圈绿光晕;处理完/空闲再开回。"""
        if getattr(self, "_run_glow", None) is not None:
            self._run_glow.setEnabled(bool(on))

    def _toggle_theme(self):
        self.theme = LIGHT if self.theme is DARK else DARK
        try:      # 记住选择(下次启动仍生效);settings 写失败不影响本次切换
            _s = config.load_settings()
            _s["theme"] = "light" if self.theme is LIGHT else "dark"
            config.save_settings(_s)
        except Exception:
            pass
        self._apply_theme()

    def _sync_narrowband_vis(self):
        """窄带融合**预设**行只在 RGB 融合流程(rgb_fuse)显示——三种输入模式都通用
        (窄带母版本身走「素材」里的滤镜标签,不再单列输入框)。"""
        if not hasattr(self, "narrowband_row"):
            return
        try:
            _fuse = (self.FLOWS[getattr(self, "flow_idx", 0)][0] == "rgb_fuse")
        except Exception:
            _fuse = False
        self.narrowband_row.setVisible(_fuse)

    # ---------- 流程/参数 ----------
    def _derive_kind(self):
        """混合模式 + 相机 → 内部引擎 kind(rgb/lrgb/sho/hoo);worker 路由不变。
        窄带具体调色(SHO/HOO/SOO…)进窄带处理步再按通道细选,这里只给引擎大类。"""
        mode = self.FLOWS[getattr(self, "flow_idx", 0)][0]
        mono = (getattr(self, "_stack_device", "osc") == "mono")
        if mode == "pure_rgb":
            return "lrgb" if mono else "rgb"          # 宽带真彩:黑白→LRGB,OSC→RGB
        if mode == "rgb_fuse":
            return "rgb"                              # 宽带底 + 窄带融合(ha_dir);走 run_rgb
        if mode == "rgb_nb":
            return "sho"                              # 窄带天体 + RGB 星点:必须走 run_sho(唯一保留 RGB 星点的引擎)
        if mode == "pure_nb":
            # 窄带调色显式覆盖相机默认(用户 2026-09-04:OSC 也能 SHO、黑白也能 HOO)
            nbp = self.cb_nbpalette.currentIndex() if hasattr(self, "cb_nbpalette") else 0
            if nbp == 1:
                return "sho"                          # 显式 SHO 哈勃(需 SII+Ha+OIII)
            if nbp == 2:
                # 显式 HOO 双色:彩色相机走 OSC 双窄带引擎;**黑白**的 Hα / OIII 是分开的两组素材,
                #   那个引擎吃不了 → 走 run_sho 的 HOO 模式(nb_mode="hoo",用户 2026-10-06 SH2-224)
                return "sho" if mono else "hoo"
            return "sho" if mono else "hoo"           # 自动:黑白多通道→SHO、OSC 双窄带→HOO
        return "rgb"

    def _select_flow(self, idx):
        self.flow_btns[idx].setChecked(True); self.flow_idx = idx
        self._apply_kind_vis()
        self._sync_narrowband_vis()
        self._sync_param_sections()
        self._sync_flow_cards()                       # 配置屏流程卡选中态跟随
        self._mark_dirty()

    def _apply_kind_vis(self):
        """按**派生引擎 kind**设参数行可见性 + 交棒点。混合模式变、或相机变(kind 会随之变)都调。"""
        mode = self.FLOWS[getattr(self, "flow_idx", 0)][0]
        kind = self._derive_kind()
        lrgb, rgb, sho, hoo = kind == "lrgb", kind == "rgb", kind == "sho", kind == "hoo"
        vis = {"ghs": rgb or lrgb, "sat": rgb or lrgb or sho, "stars": rgb,
               "ha": lrgb, "ms": lrgb, "core": lrgb, "crop": lrgb,
               "nbpalette": mode == "pure_nb",        # 纯窄带才显式选 SHO/HOO(rgb_nb 固定保留 RGB 星点走 sho)
               "palette": sho, "dust": sho, "grade": sho, "dse": sho, "zeropi": sho,
               "zeropi_rgb": rgb, "zeropi_rgb_adv": rgb, "zeropi_hoo": hoo,
               # 岔口只埋在 run_rgb 里 → 其它引擎不显示这一行,别给一个按了不算数的开关
               "stepwise": rgb,
               "mancolor": rgb,
               "stop": True, "timeout": True}
        for k, r in self._param_rows.items():
            r.setVisible(vis.get(k, True))
        if hasattr(self, "cb_stop"):
            self.STOPS = self.STOPS_BY_FLOW.get(kind, self.STOPS_BY_FLOW["rgb"])
            self.cb_stop.blockSignals(True)
            self.cb_stop.clear(); self.cb_stop.addItems([t for _, t in self.STOPS])
            self.cb_stop.setCurrentIndex(0)
            self.cb_stop.blockSignals(False)

    def _browse(self):
        # 模式 1(registered 目录)或 LRGB → 选目录;模式 0 → 选母版文件。起始路径=已填地址(用户 2026-09-06)
        want_dir = self._input_mode == 1 or self._derive_kind() in ("lrgb", "sho")
        if want_dir:
            p = QFileDialog.getExistingDirectory(self, t("选择 registered 目录"),
                                                 self._dialog_start(self.ed_input))
        else:
            p, _ = QFileDialog.getOpenFileName(self, t("选择主图"),
                                               self._dialog_start(self.ed_input, is_file=True),
                                               t("图像 (*.xisf *.fit *.fits)"))
        if p:
            self.ed_input.setText(p.replace("\\", "/")); self._remember_browse(p)

    def _refresh_runner(self):
        # 三态:在线(心跳新)/ 忙·处理中(心跳旧但有在途作业,长任务执行中)/ 未运行。
        #   长任务(WBPP/整合/BXT)执行期 runner 阻塞、心跳变旧,但它活着在忙 → 显示绿色「处理中」
        #   而非灰色「未运行」,别吓唬用户(用户反馈:PI 明明在跑却提示 runner 未运行)。
        st = protocol.runner_status()
        alive = st != "offline"                     # 忙也算「在位」:控制『释放』按钮显隐、冷启动判定
        p = self.theme
        # 【精修 2026-10-10】文案改人话(用户不需要知道 runner);胶囊底色固定,状态只靠圆点:
        #   绿点 = PI 在线,绿点呼吸 = 正在处理,灰点 = 没启动。呼吸只给「正在进行」。
        self.lbl_runner.setText({"online": t("PixInsight 已就绪"), "busy": t("PixInsight · 正在处理"),
                                 "offline": t("PixInsight 未启动")}[st])
        col = p['accent'] if alive else p['muted']
        _busy = st == "busy" or getattr(self, "thread", None) is not None
        self.runner_dot.set_state(col, alive and _busy)
        if getattr(self, "act_release", None) is not None:
            self.act_release.setVisible(alive)
        # 『释放 PixInsight』只在 PI/runner 起来后才出现
        if getattr(self, "btn_release", None) is not None and self.btn_release.isVisible() != alive:
            self.btn_release.setVisible(alive)
            if getattr(self, "_bar_sec", None):
                self._bar_sec.refresh()
        return alive

    def _poll_runner(self, times=12):
        """启动 PI 后每 3s 刷新一次 runner 状态,共约 36s。"""
        self._poll_left = times
        if not hasattr(self, "_poll_timer"):
            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self._poll_tick)
        self._poll_timer.start(3000)

    def _poll_tick(self):
        self._poll_left -= 1
        if self._refresh_runner() or self._poll_left <= 0:
            self._poll_timer.stop()

    def _launch_pi(self) -> bool:
        """冷启动 PixInsight 并加载 job-runner(不等待)。返回是否成功发起。
        没有『启动』按钮了 —— 开始处理时若 runner 未在线,自动调用它。"""
        exe = config.pixinsight_exe()
        if not exe or not Path(exe).exists():
            QMessageBox.warning(self, t("未找到 PixInsight"), t("请在『配置』里设置 PixInsight 路径。"))
            return False
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/IM", "PixInsight.exe", "/F"], capture_output=True)
                time.sleep(2)
            # 冷启前清残留:上次崩溃/超时遗留在 inbox/processing 的**孤儿 job** + 旧心跳/STOP。
            #   否则孤儿 processing 文件会让 runner_busy 误报「忙」→ 下次开始处理跳过冷启;孤儿 inbox 文件会被
            #   新 runner 重复处理。(用户 2026-09-03:筛帧超时遗留孤儿 → 整合 job 干等无人处理。)
            for _d in (config.INBOX, config.PROCESSING):
                try:
                    for _f in _d.glob("*.json"):
                        _f.unlink()
                except Exception:
                    pass
            for _f in (config.HEARTBEAT, config.STOP_FILE):
                try:
                    if _f.exists():
                        _f.unlink()
                except Exception:
                    pass
            subprocess.Popen([exe, "-n", "-r=" + str(config.JOB_RUNNER_JS)])
            self._append(f"[启动] 自动冷启动 PixInsight:{exe} -n -r={config.JOB_RUNNER_JS}")
            self._poll_runner()
            return True
        except Exception as e:
            QMessageBox.critical(self, t("启动失败"), str(e))
            return False

    def _do_release(self, quiet=False):
        """真正的释放动作(可静默调用):停 runner/看门狗/守卫 → 结束 PI → 清信号。

        **按进程名杀辅助进程**,不只发 STOP 文件——只靠信号不可靠(看门狗可能来不及读取
        就被清理,导致进程累积、还会把被杀的 PI 又拉起来)。
        """
        # 1) 先发 STOP(让它们有机会优雅退出)
        for name in ("STOP", "STOP_WATCHDOG", "STOP_GUARD"):
            try:
                (config.RUN_DIR / name).write_text("stop", encoding="utf-8")
            except OSError:
                pass
        time.sleep(1.0)
        # 2) 按进程名结束看门狗/弹窗守卫(关键:确保不残留、不重启 PI)
        if sys.platform == "win32":
            ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                  "Where-Object { $_.CommandLine -match 'watchdog|popup_guard' } | "
                  "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "orchestrator.watchdog"], capture_output=True)
            subprocess.run(["pkill", "-f", "orchestrator.popup_guard"], capture_output=True)
        # 3) 结束 PixInsight
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/IM", "PixInsight.exe", "/F"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "PixInsight"], capture_output=True)
        time.sleep(1.0)
        # 4) 清信号+心跳,便于下次启动
        for name in ("STOP", "STOP_WATCHDOG", "STOP_GUARD", "runner.heartbeat"):
            try:
                p = config.RUN_DIR / name
                if p.exists():
                    p.unlink()
            except OSError:
                pass
        if not quiet:
            self._append("[释放] 已停止 runner/看门狗/守卫并结束 PixInsight。PI 现在可手动使用。")
        self._refresh_runner()

    def _release_pi(self):
        """停止 job-runner/看门狗并结束 PixInsight,把 PI 交还给用户手动使用。"""
        if self.thread is not None:
            QMessageBox.warning(self, t("正在处理"), t("有处理任务进行中,请先『中止』再释放。"))
            return
        ret = QMessageBox.question(
            self, t("释放 PixInsight"),
            t("将停止 job-runner / 看门狗并结束所有 PixInsight 进程,之后你可手动使用 PI。\n确定?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            return
        try:
            self._do_release()
            QMessageBox.information(self, t("已释放"), t("PixInsight 已释放,可手动使用。"))
        except Exception as e:
            QMessageBox.critical(self, t("释放失败"), str(e))

    def _refit_run_btn(self):
        """按当前文字重算「开始处理 / 处理中…」按钮的宽度并让父布局重排。
        FlowBar 是自定义流式布局,不会因子控件文字变化自动重算 —— 不刷新就会出现末字被裁。"""
        try:
            b = self.btn_run
            b.setMinimumWidth(0)
            w = b.fontMetrics().boundingRect(b.text()).width() + 48   # 48 ≈ 左右各 22px padding + 余量
            b.setMinimumWidth(w)
            b.updateGeometry()
            if hasattr(self, "bar_main"):
                self.bar_main.updateGeometry()
                lay = self.bar_main.layout()
                if lay is not None:
                    lay.invalidate()
                    lay.activate()
        except Exception:
            pass

    def _reload_runner(self):
        """重载 runner:结束 PI + 冷启 → 加载最新 job-runner.js(PI 的 -r 脚本只在启动时载入一次,改了得冷启)。"""
        if self.thread is not None:
            QMessageBox.warning(self, t("正在处理"), t("有处理任务进行中,请先『中止』再重载。"))
            return
        self._append("[重载] 结束 PixInsight + 冷启动以加载最新 job-runner.js…")
        try:
            self._do_release(quiet=True)           # 停 runner/看门狗/守卫 + 杀 PI(确保 runner 下线)
        except Exception as e:
            self._append(f"[重载] 释放异常(忽略,继续冷启):{e}")
        if self._ensure_runner("重载"):            # runner 已下线 → 冷启 + 等就绪(载入新代码)
            self._append("[重载] 完成:已加载最新 job-runner.js,runner 就绪。")
            QMessageBox.information(self, t("重载完成"), t("已用最新 job-runner.js 冷启 PixInsight,runner 就绪。"))

    def _dump_history(self):
        """导出处理历史 —— 给你**自己平时用的 PixInsight** 用的独立脚本。
        为什么不走本工具的 runner:runner 是个 for(;;) 轮询循环、占着 PI 主线程,那个 PI 里
        做交互式手动处理会卡顿、且和 runner 抢视图不可靠。所以正确姿势是:你用自己的 PI
        全程手动处理,处理完运行这个独立脚本一次,把每步精确参数写成文本发我。"""
        tpl = config.PIPELINE_DIR / "pjsr" / "dump_history.js"
        script = config.RUN_DIR / "dump_history.js"
        result = config.RUN_DIR / "manual_history.txt"
        try:
            config.RUN_DIR.mkdir(parents=True, exist_ok=True)
            src = tpl.read_text(encoding="utf-8")
            # 把输出路径烘进脚本,保证脚本写的位置 = 本按钮读的位置
            script.write_text(src.replace("__OUT_PATH__", str(result).replace("\\", "/")),
                              encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, t("导出历史"), t("生成导出脚本失败:{}\n模板:{}").format(e, tpl))
            return
        try:                                          # 资源管理器里定位脚本,方便去 PI 里选它
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(script)])
        except Exception:
            pass
        self._append(f"[历史] 已生成独立导出脚本 → {script}(在你自己的 PI 里 Script ▸ Execute Script File 运行它)")

        box = QMessageBox(self)
        box.setWindowTitle(t("导出处理历史(在你自己的 PixInsight 里跑)"))
        box.setIcon(QMessageBox.Information)
        box.setText(t(
            "记录每一步精确参数,用你**自己平时的 PixInsight**、全程手动——不用本工具的 runner\n"
            "(runner 在跑轮询循环、占着 PI,那个实例里做交互式处理会卡、会和它抢视图)。\n\n"
            "步骤:\n"
            "① 正常打开你的 PI,打开并手动处理你的图(拉伸/调色随你怎么调);\n"
            "② 菜单 Script ▸ Execute Script File… ▸ 选中这个(已帮你在资源管理器里定位):\n"
            "      {}\n"
            "    运行(或按 F9);\n"
            "③ 它会 dump **所有打开窗口**的历史(不用你手动选窗口;历史常分在\n"
            "    masterLight / 主图 等多个视图里,一次全抓)到:\n"
            "      {}\n"
            "    然后回来点『查看结果』,或直接把该文件发我。\n\n"
            "⚠ 关键:PixInsight **不把历史存进磁盘**。必须**同一次会话**里处理完就跑脚本、\n"
            "   别关 PI —— 存盘后重开的图历史是空的(0 步)。标注/预览这类新渲染视图也没历史。").format(script, result))
        b_reveal = box.addButton(t("再定位脚本"), QMessageBox.ActionRole)
        box.addButton(t("查看结果"), QMessageBox.AcceptRole)
        box.addButton(t("关闭"), QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is b_reveal:
            try:
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", "/select,", str(script)])
            except Exception:
                pass
        elif box.buttonRole(clicked) == QMessageBox.AcceptRole:
            self._open_history_result(result)

    def _open_history_result(self, result):
        """打开手动导出的历史结果(独立脚本写的 manual_history.txt)。"""
        if not Path(result).exists():
            QMessageBox.information(
                self, t("导出历史"),
                t("还没找到结果文件:\n{}\n\n请先在你的 PixInsight 里运行导出脚本(Script ▸ Execute Script File),再回来点『查看结果』。").format(result))
            return
        self._append(f"[历史] 结果已就绪 → {result}")
        try:
            if sys.platform == "win32":
                os.startfile(str(result))             # 默认程序打开 txt
        except Exception:
            try:
                subprocess.Popen(["explorer", "/select,", str(result)])
            except Exception:
                pass

    def _open_settings(self):
        self._settings = SettingsWindow(); self._settings.show()

    @staticmethod
    def _fmt_size(n):
        return f"{n/1e9:.1f} GB" if n >= 1e9 else f"{n/1e6:.0f} MB" if n >= 1e6 else f"{n/1e3:.0f} KB"

    def _refresh_run_size(self):
        """后台重扫 _run 体积 → 更新按钮标签 + 缓存条目(供清理弹窗用)。"""
        th = getattr(self, "_scan_thread", None)
        if th is not None:
            try:
                if th.isRunning():
                    return
            except RuntimeError:          # 上个线程 C++ 对象已 deleteLater 删除 → 视为已结束,清引用
                self._scan_thread = None
        self._set_clean_size(scanning=True)
        th = _RunScan(self)
        th.result.connect(self._on_run_scan)
        th.finished.connect(th.deleteLater)
        self._scan_thread = th
        th.start()

    def _on_run_scan(self, entries, total):
        self._scan_thread = None          # 结果已到、线程即将 deleteLater → 丢陈旧引用(Qt 父对象仍保活到删除)
        self._run_entries = entries
        self._run_size_total = total
        self._set_clean_size(total)
        dlg = getattr(self, "_clean_dlg", None)
        if dlg is not None and dlg.isVisible():
            self._fill_cleanup_dialog()

    def _cleanup(self):
        """分目标/运行列出 _run 中间产物,勾选清理。成片已导出到输出根,这里都是可重建的中间文件。"""
        if self.thread is not None:
            QMessageBox.information(self, t("清理中间文件"), t("正在处理中,请等本次处理结束再清理(避免删到正在使用的中间文件)。"))
            return
        dlg = QDialog(self); self._clean_dlg = dlg
        dlg.setWindowTitle(t("清理中间文件"))
        dlg.setMinimumWidth(560)
        lay = QVBoxLayout(dlg)
        self._clean_head = QLabel(); self._clean_head.setWordWrap(True)
        lay.addWidget(self._clean_head)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumHeight(320)
        self._clean_host = QWidget(); self._clean_vbox = QVBoxLayout(self._clean_host)
        self._clean_vbox.setAlignment(Qt.AlignTop); self._clean_vbox.setSpacing(2)
        scroll.setWidget(self._clean_host); lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        b_all = QPushButton(t("全选")); b_none = QPushButton(t("全不选")); b_rescan = QPushButton(t("重新扫描"))
        b_del = QPushButton(t("删除选中")); b_del.setObjectName("danger")
        b_cancel = QPushButton(t("取消"))
        b_all.clicked.connect(lambda: self._clean_check_all(True))
        b_none.clicked.connect(lambda: self._clean_check_all(False))
        b_rescan.clicked.connect(self._refresh_run_size)
        b_del.clicked.connect(self._do_cleanup_selected)
        b_cancel.clicked.connect(dlg.reject)
        for b in (b_all, b_none, b_rescan):
            b.setCursor(Qt.PointingHandCursor); row.addWidget(b)
        row.addStretch(1)
        for b in (b_del, b_cancel):
            b.setCursor(Qt.PointingHandCursor); row.addWidget(b)
        lay.addLayout(row)
        self._clean_rows = []
        self._fill_cleanup_dialog()
        if self._run_entries is None:                 # 还没扫过 → 触发一次
            self._refresh_run_size()
        dlg.finished.connect(lambda _=0: setattr(self, "_clean_dlg", None))
        dlg.exec_()

    def _fill_cleanup_dialog(self):
        while self._clean_vbox.count():                # 清空旧行
            it = self._clean_vbox.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        self._clean_rows = []
        entries = self._run_entries
        if entries is None:
            self._clean_head.setText(t("正在统计运行目录体积,请稍候…"))
            return
        if not entries:
            self._clean_head.setText(t("运行目录 _run 里没有可清理的中间产物。"))
            return
        total = self._run_size_total or 0
        self._clean_head.setText(
            t("运行目录 _run 可清理中间产物合计 <b>{}</b>。成片已在你的输出根(如 M:/Deepsky),这里都是可重建的中间文件。勾选要删除的项(预览图默认不选):").format(self._fmt_size(total)))
        for ent in entries:
            roww = QWidget(); h = QHBoxLayout(roww); h.setContentsMargins(2, 1, 2, 1)
            cb = QCheckBox(ent["label"]); cb.setChecked(not ent["preserve"])
            szl = QLabel(self._fmt_size(ent["size"]))
            szl.setStyleSheet(f"color:{self.theme['muted']};font-weight:bold;")
            h.addWidget(cb, 1); h.addWidget(szl, 0)
            self._clean_vbox.addWidget(roww)
            self._clean_rows.append((cb, ent))

    def _clean_check_all(self, on):
        for cb, _ent in self._clean_rows:
            cb.setChecked(on)

    def _do_cleanup_selected(self):
        sel = [ent for cb, ent in self._clean_rows if cb.isChecked()]
        if not sel:
            QMessageBox.information(self, t("清理"), t("没有勾选任何项。"))
            return
        tot = sum(e["size"] for e in sel)
        if QMessageBox.question(self, t("确认删除"),
                                t("将删除 {} 项,释放约 {}。\n此操作不可恢复,确定?").format(len(sel), self._fmt_size(tot)),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        freed = 0; nfail = 0
        try:
            for ent in sel:
                ok = True
                for p in ent["paths"]:
                    try:
                        if os.path.isdir(p):
                            shutil.rmtree(p, ignore_errors=True)
                            if os.path.exists(p):
                                ok = False
                        else:
                            os.remove(p)
                    except OSError:
                        ok = False
                if ok:
                    freed += ent["size"]
                else:
                    nfail += 1
        finally:
            QApplication.restoreOverrideCursor()
        self._append(f"[清理] 删除 {len(sel) - nfail}/{len(sel)} 项,释放约 {self._fmt_size(freed)}"
                     + (f";{nfail} 项部分文件被占用未删净" if nfail else ""))
        dlg = getattr(self, "_clean_dlg", None)
        if dlg is not None:
            dlg.accept()
        self._refresh_run_size()

    def _check_deps(self):
        """插件体检:探测缺哪些第三方模块 → 弹窗给出下载/购买地址与安装步骤。"""
        from . import deps as _deps
        # runner 不在线就**自动冷启动 PixInsight**再体检,不再让用户手动启动
        if not self._ensure_runner("插件体检"):
            return
        try:
            avail = _deps.probe()
        except Exception as e:
            QMessageBox.critical(self, t("插件体检"), t("探测失败:{}").format(e))
            return
        avail_ext = _deps.probe_external()   # 外部 CLI 工具(Siril/StarNet CLI/GraXpert/rc-astro),路径探测不需 runner
        avail_scr = _deps.probe_scripts()    # PI 脚本(PCS 等):不注册 PJSR 符号,只能按文件探测
        miss = _deps.report(avail, avail_ext, avail_scr)
        self._append("\n" + _deps.format_text(miss))
        # 内置 AI 模型(如 NXT 旧版 .2.pb):缺失自动装回 PI library,并把情况报给用户
        models = _deps.ensure_bundled_models(log=self._append)
        mtxt = _deps.format_models_text(models)
        if mtxt:
            self._append(mtxt)
        if not miss:
            QMessageBox.information(self, t("插件体检"), "全部依赖就绪。\n\n" + mtxt)
            return
        self._show_deps_dialog(miss)

    def _show_deps_dialog(self, miss, proactive=False):
        """渲染缺失插件的引导弹窗(下载/仓库地址 + 安装步骤 + #4 免费兜底说明)。
        proactive=True 时是本会话首启的主动引导(措辞强调"不会报错、已自动兜底")。"""
        head = ("<b>插件体检</b>:检测到以下项缺失。<br>缺了<b>不会报错中断</b>——已自动用免费兜底降级;"
                "想要更好效果按下面的地址/步骤装即可。<br><br>" if proactive
                else "<b>缺少以下依赖:</b><br>")
        html = [head]
        for d in miss:
            tag = ("<span style='color:#e06c6c'>【必需】</span>" if d["need"] == "core"
                   else "<span style='color:#8a8f98'>【可选】</span>")
            pay = "<b>收费</b>,需购买" if d["paid"] else "<span style='color:#5fb96a'>免费</span>"
            fb = (f"缺失时兜底:<i>{d['fallback']}</i><br>" if d.get("fallback") else "")
            # 链接显式给亮蓝+下划线:QMessageBox 默认链接色在深色主题下是暗蓝,和背景过近看不清(用户反馈)
            html.append(f"<p>{tag} <b>{d['label']}</b>({pay})<br>{d['note']}<br>{fb}"
                        f"地址:<a href='{d['url']}' style='color:#5aa9ff;text-decoration:underline'>{d['url']}</a>"
                        f"<br><i>{d['how']}</i></p>")
        box = QMessageBox(self)
        box.setWindowTitle(t("插件体检"))
        box.setTextFormat(Qt.RichText)
        box.setText("".join(html))
        box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        box.exec_()

    def _collect_opts(self):
        return {"timeout": float(self.sp_timeout.value()), "ghs_d": self.sp_ghs.value(),
                "neb_sat": self.sp_sat.value(), "stars": self.chk_stars.isChecked(),
                "ha": self.sp_ha.value(), "ms_iters": self.sp_ms.value(),
                "core_thr": self.sp_core.value(), "crop_frac": self.sp_crop.value(),
                "integrate_first": self._input_mode == 1,
                "input_mode": self._input_mode,
                "detrail": self.chk_detrail.isChecked(),
                "stretch_judge": self.chk_stretch_judge.isChecked(),
                "stepwise": self.cb_stepwise.currentIndex() == 1,   # 分步询问方向
                "mancolor": self.cb_mancolor.currentIndex() == 1,   # 去星后手动调色面板
                # PI 管线 reveal:高级 chk_reveal 与主区「星云揭示」下拉**任一为关都关**(用户 2026-09-09:
                #   主区下拉设"关 0"却只喂了 Siril 引擎、没到 PI 管线 → reveal 照跑把背景过度拉伸)。下拉 idx1="关 0"。
                "reveal": self.chk_reveal.isChecked() and self.cb_rgbreveal.currentIndex() != 1,
                "lhe": self.chk_lhe.isChecked(),
                "dust_reveal": (None, True, False)[self.cb_dust.currentIndex()],
                "stop_after": self.STOPS[self.cb_stop.currentIndex()][0],
                "palettes": (PALETTES if self.cb_palette.currentIndex() == 0
                             else [PALETTES[self.cb_palette.currentIndex() - 1]]),
                "zeropi": self.chk_zeropi.isChecked(),
                "zpreset": ("goldblue", "warm")[self.cb_zpreset.currentIndex()],
                "zeropi_rgb": self.chk_zeropi_rgb.isChecked(),
                "rgbpreset": ("natural", "vivid", "flat")[self.cb_rgbpreset.currentIndex()],
                "bg_extract": (None, "1", "4", "rbf", "4+rbf")[self.cb_bgextract.currentIndex()],
                # 揭示下拉:前4档只 reveal(亮度);后2档「发射」额外加 emission(红色发射蒙版提红丝)
                "rgb_reveal": (None, 0.0, 0.5, 0.9, 0.9, 0.9)[self.cb_rgbreveal.currentIndex()],
                "rgb_emission": (0.0, 0.0, 0.0, 0.0, 0.6, 1.0)[self.cb_rgbreveal.currentIndex()],
                "glow_clean": ("auto", "on", "off")[self.cb_glow.currentIndex()],
                "ha_dir": self._mode0_nb_master(),   # 母版模式第一路窄带 master(现融合引擎单窄带路径);其它模式走滤镜标签
                "hapreset": ("emission", "emission_vivid", "galaxy", "compact")[max(0, min(3, self.cb_hapreset.currentIndex()))],
                "zeropi_hoo": self.chk_zeropi_hoo.isChecked(),
                "hoopreset": ("oiii", "classic")[self.cb_hoopreset.currentIndex()],
                "grade_curve": ("henry_sho" if self.cb_grade.currentIndex() == 1 else None),
                "darkstruct": ("auto", {"amount": 0.5}, {"amount": 0.2}, None)[self.cb_dse.currentIndex()],
                "target": self._guess_target(),
                "mode": self.FLOWS[self.flow_idx][0],   # 混合模式(严格门控融合:仅 rgb_fuse 才叠窄带)
                "master": self._master_config() if self._input_mode == 0 else None,  # 已叠加母版:滤镜分组文件
                "nb_masters": [m["file"] for m in (self._master_config() if self._input_mode == 0 else [])
                               if not _is_bb(m.get("filter"))],   # 全部窄带母版(供后续多窄带引擎 HO+Hβ/SII)
                # 相机 + 黑白已叠加母版 {滤镜键: 文件}(黑白宽带+窄带融合:R/G/B 合成底、Hα/OIII 逐通道)
                "camera": getattr(self, "_stack_device", "osc"),
                "mono_masters": (self._mono_master_map()[0]
                                 if self._input_mode == 0 and getattr(self, "_stack_device", "osc") == "mono"
                                 else None),
                "reg": self._reg_config() if self._input_mode == 1 else None,   # 对齐子帧:滤镜分组目录
                "stack_home": self._stack_home() if self._input_mode == 1 else "",   # 对齐子帧:母版存哪
                # 窄带合成方式:纯窄带下拉选了 SHO / HOO 就照办;其余(含「RGB 星点 + 窄带」)自动 = 有 SII 走 SHO、没有走 HOO
                "nb_mode": (("auto", "sho", "hoo")[max(0, min(2, self.cb_nbpalette.currentIndex()))]
                            if (self.FLOWS[self.flow_idx][0] == "pure_nb" and hasattr(self, "cb_nbpalette"))
                            else "auto"),
                "raw": self._raw_config() if self._input_mode == 2 else None}

    def _stack_home(self) -> str:
        """对齐子帧模式叠出的母版存哪 = **项目目录**(用户 2026-10-06:「叠加生成的 masterLight 不保存在
        项目目录下,这样我需要编辑时还要重新叠加一次」)。旧版存第一个子帧目录的上一级 = `<项目>/registered/`,
        多段合并时还落进**第一段**的 registered 里。
        ① 子帧目录都在同一个项目目录下(`<项目>/registered/<各晚>`)→ `<项目>/`,与原始素材叠加的母版同处;
        ② 跨了几个项目目录(多段合并,如 IC4592 的 260313-260425 + 260710-260808)→ 存**导出目录**
           (那是给合并后的项目起的目录);导出目录没填、或夹名里的天体编号对不上当前目标 → 第一个项目目录。"""
        homes = []
        for g in (self._reg_config() or []):
            h = _reg_project_dir(g["dir"])
            if h and h not in homes:
                homes.append(h)
        if not homes:
            return ""
        if len(homes) == 1:
            return homes[0]
        exp = (self.ed_exportdir.text() or "").strip().replace("\\", "/").rstrip("/")
        if exp:
            want = self._desig_of(self._guess_target())
            have = self._desig_of(Path(exp).name)
            if not (want and have and want != have):
                return exp
        return homes[0]

    def _project_home(self) -> str:
        """当前项目自己的目录(.ttproj 默认存这):对齐子帧=母版所在的项目目录;原始叠加=叠加输出目录/项目名;
        已叠加母版=母版所在目录(WBPP 的 master/ 子夹取上一级)。推不出来返回 ""。
        【为什么要有(2026-10-06)】从没存过的新项目,自动保存原先落在「上次保存工程的目录」=
        上一个目标的文件夹 —— IC4592.ttproj 就这样被存进了 M109 的文件夹。"""
        try:
            if self._input_mode == 1:
                return self._stack_home()
            if self._input_mode == 2:
                raw = self._raw_config() or {}
                ob = (raw.get("out_base") or "").strip().replace("\\", "/").rstrip("/")
                tg = (raw.get("target") or "").strip()
                return f"{ob}/{tg}" if (ob and tg) else ""
            ms = [m["file"] for m in (self._master_config() or []) if m.get("file")]
            if ms:
                d = Path(ms[0]).parent
                if d.name.lower() in ("master", "masters") and d.parent.name:
                    d = d.parent
                return str(d).replace("\\", "/")
        except Exception:
            pass
        return ""

    def _guess_target(self):
        """尽力从输入路径/原始配置猜目标名(喂评委;猜不到留空,评委无参考也能判)。"""
        import re as _re
        if self._input_mode == 2:
            t = self.ed_target.text().strip()
            if t:
                return t
        # 输入路径:mode1 用第一个对齐子帧目录(宽带优先),其余用单目录 ed_input
        if self._input_mode == 1:
            _rg = self._reg_config()
            _bb = [g["dir"] for g in _rg if _is_bb(g.get("filter"))] or [g["dir"] for g in _rg]
            p = (_bb[0] if _bb else "").replace("\\", "/")
        else:
            p = self.ed_input.text().strip().replace("\\", "/")
        for part in reversed([x for x in p.split("/") if x]):
            # 项目夹命名 YYMMDD_CAM_TARGET / begin-end_CAM_TARGET → 取末段
            m = _re.match(r"^[\d\-]+_[^_]+_(.+)$", part)
            if m:
                return m.group(1)
        return ""

    # ---------- 运行 / 进度 / 中止 ----------
    def _run(self):
        if self.thread is not None:
            return
        opts = self._collect_opts()
        if self._input_mode == 2:
            raw = opts["raw"]
            dev = raw.get("device", "osc")
            dev_label, pol, _hint = STACK_DEV_MAP.get(dev, STACK_DEV_MAP["osc"])
            if dev == "mono":
                # 黑白 per-filter:每组=通道亮场+通道平场(一一对应);暗场按曝光/偏置全局必填
                lts = raw.get("lights") or []; fls = raw.get("flats") or []
                if not lts or any(not x for x in lts):
                    QMessageBox.warning(self, t("配置不完整"), t("黑白 per-filter:每个通道组都需填「通道亮场」目录。"))
                    return
                if len(fls) != len(lts) or any(not x for x in fls):
                    QMessageBox.warning(self, t("配置不完整"),
                                        t("通道组需「亮场+平场」成对:现有亮场 {} 个、平场 {} 个。").format(len(lts), len([x for x in fls if x])))
                    return
                if not raw.get("darks"):
                    QMessageBox.warning(self, t("配置不完整"), t("黑白相机:需填暗场父目录(内含各曝光时长子夹,程序按曝光自动配光)。"))
                    return
                if not (raw.get("bias") or "").strip():
                    QMessageBox.warning(self, t("配置不完整"), t("黑白相机:需填偏置目录(全局共用)。"))
                    return
            else:
                # 亮场恒为必填;平场/暗场/偏置是否必填按设备策略(智能望远镜可缺)
                if not raw["nights"] or any(not n["light"] for n in raw["nights"]):
                    QMessageBox.warning(self, t("配置不完整"), t("原始素材叠加:每晚都需填亮场目录。"))
                    return
                if pol.get("flat") == "req" and any(not n["flat"] for n in raw["nights"]):
                    QMessageBox.warning(self, t("配置不完整"), t("{}:每晚都需填平场目录。").format(t(dev_label)))
                    return
                if pol.get("dark") in ("req", "reqtemp") and not raw["dark"]:
                    m = (t("{}:必须提供与亮场温度匹配的暗场,否则热噪严重。").format(t(dev_label))
                         if pol["dark"] == "reqtemp" else t("需填暗场目录。"))
                    QMessageBox.warning(self, t("配置不完整"), m)
                    return
                if pol.get("bias") == "req" and not raw["bias"]:
                    QMessageBox.warning(self, t("配置不完整"), t("需填偏置目录。"))
                    return
                # Dwarf:开始前校验暗场温度与亮场是否匹配(读 FITS CCD-TEMP);不匹配弹窗让用户确认
                if pol.get("dark") == "reqtemp" and raw["dark"]:
                    if not self._check_dark_temp_match(raw["nights"][0]["light"], raw["dark"]):
                        return
            if not (raw.get("target") or "").strip():
                QMessageBox.warning(self, t("配置不完整"), t("请填项目名。"))
                return
            # 叠加中间产物(校准/去马/对齐子帧)体量巨大 → 启动前确认导出目录(用户 2026-08 强调)
            _outb = (raw.get("out_base") or "").strip()
            if not _outb:
                QMessageBox.warning(self, t("配置不完整"), t("请填「导出目录」——叠加中间产物体量巨大,请选一个空间充足的磁盘。"))
                return
            _proj = _outb.rstrip("/") + "/" + raw["target"].strip()
            if QMessageBox.question(
                    self, t("确认导出目录"),
                    t("叠加的中间产物(逐帧校准/去马赛克/对齐子帧)体量巨大,将全部写入:\n\n    {}\n\n请确认该磁盘剩余空间充足。是否开始叠加?").format(_proj),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
                return
            inp = ""  # 原始叠加:输入路径在 WBPP 叠加+整合后得到
        elif self._input_mode == 1:
            # 对齐子帧目录:校验滤镜分组目录(不再用单目录 ed_input)
            _rg = self._reg_config()
            _mono_fuse = (getattr(self, "_stack_device", "osc") == "mono" and self._derive_kind() == "rgb")
            if not _rg:
                QMessageBox.warning(self, t("输入无效"), t("请至少填一个对齐子帧目录。"))
                return
            _bad = next((g["dir"] for g in _rg if not Path(g["dir"]).exists()), "")
            if _bad:
                QMessageBox.warning(self, t("输入无效"), t("对齐子帧目录不存在:{}").format(_bad))
                return
            if self._derive_kind() == "sho":
                # 窄带合成:要的是 Hα + OIII(SII 可选,没有就走 HOO);R/G/B 只给星点用,可以没有
                _have = {g.get("filter") for g in _rg}
                _miss = [lab for k, lab in (("Ha", "Hα"), ("OIII", "OIII")) if k not in _have]
                if _miss:
                    QMessageBox.warning(self, t("配置不完整"),
                                        t("窄带合成至少要 Hα 和 OIII 两组子帧,还缺:{}。每行右边的下拉选这组子帧的滤镜。")
                                        .format("、".join(_miss)))
                    return
            elif not any(_is_bb(g.get("filter")) for g in _rg):
                QMessageBox.warning(self, t("配置不完整"), t("对齐子帧:至少需要一个 IR-UVcut 宽带目录(作 RGB 底)。"))
                return
            if _mono_fuse:
                _miss = [k for k in ("R", "G", "B") if not any(g.get("filter") == k for g in _rg)]
                if _miss:
                    QMessageBox.warning(self, t("配置不完整"),
                                        t("黑白相机做宽带 + 窄带融合,彩色底要 R、G、B 三组子帧,还缺:{}").format(
                                            "、".join(_miss)))
                    return
            inp = ""  # mode1:整合在 worker 里按滤镜分组做
        else:
            # mode0 已叠加母版(多行·文件+滤镜):宽带(IR-UVcut)母版=RGB 底 → inp;窄带母版走 ha_dir/nb_masters 融合
            _mc = self._master_config()
            _mono_fuse = (getattr(self, "_stack_device", "osc") == "mono" and self._derive_kind() == "rgb")
            if not _mc:
                QMessageBox.warning(self, t("输入无效"), t("请至少填一个已叠加母版文件。"))
                return
            _bad = next((m["file"] for m in _mc if not Path(m["file"]).exists()), "")
            if _bad:
                QMessageBox.warning(self, t("输入无效"), t("母版文件不存在:{}").format(_bad))
                return
            if self._derive_kind() == "sho":
                _have0 = {m.get("filter") for m in _mc}
                _miss0 = [lab for k, lab in (("Ha", "Hα"), ("OIII", "OIII")) if k not in _have0]
                if _miss0:
                    QMessageBox.warning(self, t("配置不完整"),
                                        t("窄带合成至少要 Hα 和 OIII 两张母版,还缺:{}。每行右边的下拉选这张母版的滤镜。")
                                        .format("、".join(_miss0)))
                    return
            _bbm = [m["file"] for m in _mc if _is_bb(m.get("filter"))] or [_mc[0]["file"]]
            inp = _bbm[0]      # 宽带底(未标 IR-UVcut 时退回第一行,兼容单母版)
            if _mono_fuse:
                # 黑白:宽带底是 R/G/B 三张合成的一张彩色图(在 worker 里合成),这里只校验齐不齐
                _mm, _dup = self._mono_master_map()
                _miss = [k for k in ("R", "G", "B") if k not in _mm]
                if _miss:
                    QMessageBox.warning(self, t("配置不完整"),
                                        t("黑白相机做宽带 + 窄带融合,彩色底要 R、G、B 三张母版,还缺:{}。\n"
                                          "每行右边的下拉选这张母版的滤镜(选了文件会按文件头自动选)。").format(
                                            "、".join(_miss)))
                    return
                if _dup:
                    self._append("[母版] 同一滤镜填了多行,只用第一行,忽略:" + "、".join(_dup))
                opts["mono_masters"] = _mm
                inp = _mm["R"]
        # 无 PI · Siril 引擎流程:全程零 PixInsight → 不需要 job-runner,跳过 PI 冷启动
        _kind0 = self._derive_kind()             # 派生引擎 kind
        _zeropi0 = ((_kind0 == "rgb" and self.chk_zeropi_rgb.isChecked())
                    or (_kind0 == "hoo" and self.chk_zeropi_hoo.isChecked())
                    or (_kind0 == "sho" and self.chk_zeropi.isChecked()))
        if _zeropi0 and _kind0 == "rgb" and getattr(self, "_stack_device", "osc") == "mono":
            # 无 PI 的 RGB 引擎只认一张彩色母版;黑白的 R/G/B 合成与逐通道窄带处理目前只在 PI 流程里
            self._append("[准备] 黑白相机的 R/G/B 合成和逐通道窄带处理目前只有 PI 版本 → 这次按 PI 流程处理")
            _zeropi0 = False
            opts["zeropi_rgb"] = False
        # runner 未在线 → 自动冷启动 PI(zero-PI 流程除外);Worker 会先等 runner 就绪再跑。
        if not _zeropi0 and not self._refresh_runner():
            if not config.pixinsight_exe():
                QMessageBox.warning(self, t("未找到 PixInsight"), t("请在『配置』里设置 PixInsight 路径后再开始。"))
                return
            self._append("[准备] runner 未在线 → 自动启动 PixInsight,就绪后开始处理…")
            if not self._launch_pi():
                return
        kind = self._derive_kind()               # 混合模式+相机 → 内部引擎 kind 喂 Worker
        self.log.clear(); self.gresult.setVisible(False)
        if hasattr(self, "export_panel"):
            self.export_panel.setVisible(False)
        if hasattr(self, "lbl_review_empty"):
            self.lbl_review_empty.setText(t("处理进行中…评审与实测指标会在完成后出现在这里。"))
            self.lbl_review_empty.setVisible(True)
        if hasattr(self, "lbl_export_empty"):
            self.lbl_export_empty.setVisible(True)
        if hasattr(self, "_go_stage"):
            self._go_stage(2)                    # 开跑 → 切到「处理」屏看进度
        self.pal_bar.setVisible(False); self.pal_bar.clear(); self._finals = {}
        self._pal_scores = {}; self._scored_pal = None; self._cur_pal = None
        self._dust_mode = False; self.btn_dust.setChecked(False); self.preview.setCursor(Qt.ArrowCursor)
        self.btn_scorepal.setVisible(False); self.btn_scorefix.setVisible(False); self._clear_remedy_rows()
        self._pre_remedy = None
        self.btn_remedy_undo.setVisible(False)
        self.btn_remedy_cmp.setVisible(False); self.btn_remedy_cmp.setChecked(False)
        self.btn_rescore.setVisible(False)
        self.pause_panel.setVisible(False); self.btn_p_dust.setChecked(False)
        self.decide_panel.setVisible(False)
        # 【开跑先清掉上一轮的成片引用(用户 2026-09-14:处理 M64 时用放大镜看到的是 M63)】
        #   _final_xisf/_final_png 原本只在「新建项目」和「跑完」时更新 → 换目标直接重跑时,
        #   从开跑到出成片这段时间它还指着**上一个目标**的成片文件(而且 _run/ 是跨目标复用的,
        #   文件还在、mtime 也没变,放大镜的「路径+mtime」缓存键照样命中)→ 放大后看到上一张图。
        #   清空后 _hires_key() 返回空,放大镜自动回退到当前实时预览图。
        self._final_png = self._final_xisf = ""; self._stage_xisf = ""
        self._pm_hires = None; self._pm_hires_key = ""
        self._start_t = time.time(); self._max_phase = -1; self._done_ops = 0
        self._expected = _EXPECTED.get(kind, 16)
        self.bar.setValue(0); self.lbl_eta.setText(t("准备中…"))
        self._end_state = "run"
        self._reveal(self.gprog); self._paint_phases()
        self._pulse.start()
        self.lbl_prog_stage.setText(t("准备中"))
        self.bar_shim.start(); self.run_shim.start()
        self.btn_run.setEnabled(False); self.btn_run.setText(t("处理中…")); self.btn_abort.setVisible(True)
        self._refit_run_btn()
        self._set_run_glow(False)      # 处理中关绿辉光,免暗按钮外一圈绿光晕(用户 2026-09-04)
        # 支持随时暂停介入的流程 → 显示暂停按钮(SHO 逐通道 + RGB 逐步;pipeline 层已埋 pause_gate)
        self.btn_pause.setVisible(kind in ("sho", "rgb")); self.btn_pause.setEnabled(True)
        self.btn_pause.setText(t("暂停介入"))
        self.bar_main.refresh()   # 中止/暂停按钮出现 → 容器要重算宽度
        self.thread = QThread()
        opts["check_deps"] = not getattr(self, "_deps_checked", False)   # 本会话首次处理 → 主动插件体检一次
        self._deps_checked = True
        self.worker = Worker(kind, inp, opts)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append)
        self.worker.progress.connect(self._on_progress)
        self.worker.preview.connect(self._show_stage_preview)
        self.worker.done.connect(self._finished)
        self.worker.paused.connect(self._on_paused)
        self.worker.decision.connect(self._on_decision)
        self.worker.decide_reply.connect(self._on_decide_reply)
        self.worker.pause_preview.connect(self._on_pause_preview)
        self.worker.pause_chat.connect(self._on_pause_chat)
        self.worker.pause_busy.connect(self._on_pause_busy)
        self.worker.deps.connect(self._on_deps_missing)
        self.worker.color_ask.connect(self._on_color_ask)      # 手动调色面板
        self.thread.start()

    def _on_deps_missing(self, miss):
        """首启体检回主线程:缺插件时弹一次引导框(不阻断处理——#4 已自动兜底,后台继续跑)。"""
        try:
            self._show_deps_dialog(list(miss), proactive=True)
        except Exception:
            pass

    def _abort(self):
        self._append(t("[中止] 正在立刻停止(会终止 PixInsight 里正在跑的那一步 —— "
                       "PJSR 的操作无法中途打断;下次运行自动冷启动)…"))
        pipeline.request_cancel(kill_runner=True, log=self._append)
        self.btn_abort.setEnabled(False)

    # ---------- 随时暂停介入 ----------
    def _request_pause(self):
        if self.worker:
            self.worker.request_pause()
            self.btn_pause.setEnabled(False); self.btn_pause.setText(t("⏸ 将在当前步骤后暂停…"))
            self._append("[暂停] 已请求,将在当前步骤完成后停住。")

    def _on_paused(self, tag, image, preview, targets_json):
        """Worker 线程在某步边界停住 → 显示暂停面板 + 通道目标选择,让用户对选定图做矫正。"""
        import json as _json
        self._pause_tag = tag; self._pause_seq = 0
        try:
            targets = _json.loads(targets_json) if targets_json else {}
        except Exception:
            targets = {}
        self._final_xisf = image
        self._final_png = preview if preview and Path(preview).exists() else self._final_png
        if self._final_png and Path(self._final_png).exists():
            pm = QPixmap(self._final_png)
            if not pm.isNull():
                self.preview_scroll.setVisible(True); self._set_preview_pixmap(pm)
        # 目标下拉:合成前列出各通道(可回到任一通道修);合成后无通道则隐藏该行,只修当前图
        self.cb_pause_target.blockSignals(True)
        self.cb_pause_target.clear()
        self._pause_targets = targets
        if targets:
            cur_key = None
            for label, path in targets.items():
                self.cb_pause_target.addItem(label, path)
                if path == image:
                    cur_key = label
            if cur_key:
                self.cb_pause_target.setCurrentText(cur_key)
            self._pause_target_row.setVisible(True)
        else:
            self._pause_target_row.setVisible(False)
        self.cb_pause_target.blockSignals(False)
        hint = t("可在『选通道图』里挑前面生成的任一通道图,再做 梯度矫正 / 灰尘修复 / 跟 AI 说想法") if targets else t("可对当前图做 梯度矫正 / 灰尘修复 / 跟 AI 说想法")
        self._pause_busy = False; self._pause_status = ""   # 新的暂停点:面板一律回到可操作态
        self._on_pause_busy(False, "")
        self.lbl_pause.setText(t("已暂停 · 当前【{}】。{},或点继续。").format(tag, hint))
        self.btn_p_dust.setChecked(False); self._dust_mode = False
        self._dust_circle = None; self._sync_dust_apply()
        self._stop_pause_think(); self.pause_chat_log.clear()
        self.pause_panel.setVisible(True)
        self.lbl_prevtag.setText(t("已暂停 · {}").format(tag))

    # ── 手动调色面板(用户 2026-09-21)────────────────────────────────────────
    def _on_color_ask(self, image, preview):
        """管线停在去星后的本体层 → 显示调色面板,载入预览做实时预算。"""
        import numpy as _np
        self._col_img = image
        self._col_prev = preview
        self._col_bg = None
        self._col_pt = None
        self._col_maskarr = None
        self._col_busy = False
        # 实时预览的底:用**界面预览图**(约 1200px)在 numpy 上算,不占 PI。
        self._col_base = None
        try:
            if preview and Path(preview).exists():
                from PIL import Image as _PI
                _a = _np.asarray(_PI.open(preview).convert("RGB")).astype(_np.float32) / 255.0
                # 太大就先缩,保证拖滑块跟手(1000px 以内单次重算约几十毫秒)
                if max(_a.shape[:2]) > 1000:
                    _sc = 1000.0 / max(_a.shape[:2])
                    _im2 = _PI.open(preview).convert("RGB").resize(
                        (max(1, int(_a.shape[1] * _sc)), max(1, int(_a.shape[0] * _sc))), _PI.LANCZOS)
                    _a = _np.asarray(_im2).astype(_np.float32) / 255.0
                self._col_base = _a
        except Exception as _e:
            self._append("[调色] 预览载入失败,只能盲调:%s" % str(_e)[:80])
        self._col_base_ver = getattr(self, "_col_base_ver", 0) + 1     # 后台缓存(蒙版/几何)按它作废
        self._col_pending = None
        if preview and Path(preview).exists():
            pm = QPixmap(preview)
            if not pm.isNull():
                self.preview_scroll.setVisible(True); self._set_preview_pixmap(pm)
        if image:
            self._final_xisf = image
        # 预设按钮每次重建
        for b in getattr(self, "_col_preset_btns", []):
            b.setParent(None); b.deleteLater()
        self._col_preset_btns = []
        try:
            from . import galaxycolor as _gcp
            _ps = _gcp.PRESETS
        except Exception:
            _ps = {}
        for _name, _v in _ps.items():
            b = QPushButton(_name); b.setObjectName("seg"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, vv=dict(_v): self._col_preset(vv))
            self.col_presetbar.add(b); self._col_preset_btns.append(b)
        self._col_reset()
        self._col_load_preset()          # 上次调定的那组 → 直接填回滑块
        self.color_panel.setVisible(True)
        self.lbl_prevtag.setText(t("等你调色"))
        self._scroll_into_view(self.color_panel)

    def _scroll_into_view(self, w):
        """把刚出现的面板滚进视野。延一拍再滚 —— 这一帧布局还没重算,现在滚是滚到旧位置。"""
        try:
            sc = getattr(self, "pane_scroll", None)
            _isc = getattr(self, "_insp_scroll", None)
            if _isc is not None and w is not None and _isc.widget().isAncestorOf(w):
                sc = _isc                          # 暂停 / 岔口 / 调色面板在左侧检查器里
            if sc is None or w is None:
                return
            QTimer.singleShot(0, lambda: sc.ensureWidgetVisible(w, 0, 24))
        except Exception:
            pass

    def _col_toggle_pick(self):
        """点选背景模式:与灰尘圈选互斥(两者都要抢预览的鼠标事件)。"""
        on = self.btn_col_pick.isChecked()
        if on:
            self._dust_mode = False
            if hasattr(self, "btn_dust"):
                self.btn_dust.setChecked(False)
            if hasattr(self, "btn_p_dust"):
                self.btn_p_dust.setChecked(False)
        self._col_pick_mode = on
        self.preview.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    def _col_pick_at(self, px, py):
        """预览控件坐标 → 原图坐标 → 取一小块中位当背景锚点。"""
        disp = getattr(self, "_pm_display", None)
        base = getattr(self, "_col_base", None)
        if disp is None or disp.isNull() or base is None:
            return
        Lw, Lh = self.preview.width(), self.preview.height()
        Dw, Dh = disp.width(), disp.height()
        ox, oy = (Lw - Dw) / 2.0, (Lh - Dh) / 2.0        # 预览在控件里居中
        u, v = (px - ox) / max(Dw, 1), (py - oy) / max(Dh, 1)
        if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
            return
        H, W = base.shape[:2]
        try:
            from . import galaxycolor as _gcp
            info = _gcp.sample_background(base, u * W, v * H, radius=max(3, int(0.006 * min(H, W))))
        except Exception:
            return
        self._col_bg = float(info["lum"])
        self._col_pt = (float(u), float(v))     # 归一化坐标,给预览上画标记用
        r, g, b = info["rgb"]
        self.lbl_col_bg.setText(
            t("背景已定在 {:.4f}(R {:.3f} / G {:.3f} / B {:.3f})——三条曲线都钉住这里")
            .format(self._col_bg, r, g, b))
        # 【当场体检(用户 2026-09-23 M64)】点到天体上 → clip 抬过头 → 主体亮度跨度被压没
        #   → 蒙版只剩最亮的核心,而且**「蒙版收紧」滑块整条失效**(拖了不动)。
        #   这个失败原本是**静默**的:滑块从 0.85 拖到 0.15 蒙版逐位相同,用户无从察觉。
        try:
            _h = _gcp.mask_anchor_health(base, self._col_bg)
            if _h.get("reason"):
                self._append(("[调色] ★" if _h.get("level") == "bad" else "[调色] ") + _h["reason"])
                if _h.get("level") == "bad":
                    self.lbl_col_bg.setText(
                        self.lbl_col_bg.text() + t("  ⚠ 这个点偏亮,蒙版会只剩核心"))
        except Exception:
            pass
        self.btn_col_pick.setChecked(False); self._col_pick_mode = False
        self.preview.setCursor(Qt.ArrowCursor)
        self._col_maskarr = self._col_maskkey = None    # 黑点变了 → 蒙版重算
        self._col_changed(immediate=True)

    def _col_vals(self):
        d = {}
        for k, (sl, _lb) in getattr(self, "_col_sliders", {}).items():
            d[k] = sl.value() / 100.0
        return d

    # 【滑块→曲线的换算不写在这里】统一在 orchestrator/colorprefs.py。
    #   理由:同一套数要给三个地方用 —— GUI 实时预览、GUI 最终应用、**全自动管线**。
    #   以前只有 GUI 有这套换算、自动路是另一套机制(AstroBin 盘色 + 自有基准),
    #   两条路的颜色本来就对不上,用户 2026-09-21「自动调色跑出来的颜色相当糟糕」说的就是它。
    def _col_points(self):
        """当前滑块 → 主体侧曲线控制点(没定背景则 colorprefs 里用 0.09 兜底)。"""
        try:
            from . import colorprefs as _cpf
        except Exception:
            return {}
        return _cpf.curves_for(self._col_vals(), getattr(self, "_col_bg", None))

    def _col_bg_points(self):
        """当前滑块 → 背景侧(蒙版补集)曲线:压饱和 + 压亮度。"""
        try:
            from . import colorprefs as _cpf
        except Exception:
            return {}
        return _cpf.bg_curves_for(self._col_vals(), getattr(self, "_col_bg", None))

    def _col_identity(self) -> dict:
        """当前正在调色的**这张图是谁**:天体名 + 天区坐标 + 来源。

        【为什么不能只读面板那张图(用户 2026-09-23 M51 事故)】面板停在 `r11b_lhe`,
        而 **OBJECT 关键字在中途某一步被丢掉了** —— 上游的 `r02b_solve` 明明写着
        `OBJECT='M 51'`。读不到就退回界面上那个"项目目录"输入框,而它**换目标时不更新**,
        于是 M51 的参数被当成 M81 存了进去、**把真正的 M81 那条覆盖掉**。
        (我先前加的"从目录名抠星表编号"反而让这个错更隐蔽:原来存成一长串目录名一眼能看出不对,
         抠完变成干干净净的 `M81`,静默覆盖。**让错误更好看 = 让它更危险**。)

        → 面板图上没有就**沿本轮的上游产物往回找**。只认**时间窗内**的文件:
          `_run` 是跨目标复用的,不卡时间窗会捡到上一个目标的残留(这个坑栽过两次,
          见 [[pi-gui-stale-target-state]] / [[pi-galaxy-disc-color-target]])。
        """
        from pathlib import Path as _P
        out = {"name": "", "ra": None, "dec": None, "src": ""}

        def _kw(path):
            try:
                from xisf import XISF as _XT
                return _XT(str(path)).get_images_metadata()[0].get("FITSKeywords", {}) or {}
            except Exception:
                return {}

        def _get(kw, k):
            v = kw.get(k)
            if isinstance(v, list) and v:
                v = v[0].get("value") if isinstance(v[0], dict) else v[0]
            return str(v or "").strip().strip("'\"") if v is not None else ""

        cur = getattr(self, "_col_img", None)
        cands = []
        if cur and _P(str(cur)).exists():
            cands.append(_P(str(cur)))
            try:
                t0 = _P(str(cur)).stat().st_mtime
                run = _P(str(cur)).parent
                # 本轮上游:比面板那张**更早**但在 2 小时内(一轮跑满也就 45 分钟),由近及远
                up = [p for p in run.glob("*.xisf")
                      if t0 - 7200 <= p.stat().st_mtime <= t0 + 1]
                cands += sorted(up, key=lambda p: p.stat().st_mtime, reverse=True)
            except OSError:
                pass
        from . import colorprefs as _cpi
        for p in cands:
            kw = _kw(p)
            if not out["name"]:
                nm = _get(kw, "OBJECT")
                # 'Unknown' 这类占位值不是天体名(DWARF3 按坐标拍就写它)→ 当没有,接着往下找
                if nm and _cpi.is_placeholder_name(nm):
                    out.setdefault("placeholder", nm)
                    nm = ""
                if nm:
                    out["name"], out["src"] = nm, p.name
            if out["ra"] is None:
                ra, dec = _get(kw, "OBJCTRA"), _get(kw, "OBJCTDEC")
                if ra and dec:
                    out["ra"], out["dec"] = _sexa_deg(ra, True), _sexa_deg(dec, False)
            # 相机:预设的 R/G/B 是在修**这台相机**的偏色,存/取都要带上(见 colorprefs.LEGACY_CAMERA)
            if not out.get("camera"):
                cam = _get(kw, "INSTRUME")
                if cam:
                    out["camera"] = cam
            if out["name"] and out["ra"] is not None and out.get("camera"):
                break
        return out

    def _col_target(self):
        """当前**天体名**(存/取预设的键)。

        取值序:本轮任一产物的 FITS `OBJECT` → 项目目录里的星表编号 → 项目目录原文。
        后两档都只是**猜**,所以存盘那一步还有一道「天区坐标对不上就拒绝覆盖」的闸
        (见 colorprefs.save)—— 名字猜错最多是多存一条,不会再把别人的那条抹掉。
        """
        ident = self._col_identity()
        if ident.get("name"):
            if ident.get("src") and not str(ident["src"]).startswith("r11b"):
                self._append(t("[调色] 这张图上没有 OBJECT 关键字,从本轮上游的 {} 读到天体名「{}」")
                             .format(ident["src"], ident["name"]))
            return ident["name"]
        try:
            fb = (self.ed_target.text() or "").strip()
        except Exception:
            fb = ""
        des = _designation(fb)
        if ident.get("placeholder"):
            self._append(t("[调色] 这张图的 OBJECT 是占位值「{}」(相机没记目标名),不当天体名用")
                         .format(ident["placeholder"]))
        if des:
            self._append(t("[调色] 本轮产物里都没有 OBJECT → 只能从项目目录「{}」猜成「{}」;"
                           "**这个输入框换目标时不会自动更新**,如果不对请先改它").format(fb, des))
            return des
        if fb:
            self._append(t("[调色] 本轮产物里都没有 OBJECT、目录名「{}」里也认不出星表编号 → "
                           "预设按整段目录名存").format(fb))
        return fb

    def _col_load_preset(self):
        """面板打开时把**上次调定的那组**填回滑块(本目标专用优先,否则借最近一次)。

        只填滑块,**不填背景锚点** —— 背景电平是这张图的实测值,换了目标/换了拉伸就变了,
        照搬会把三条曲线钉在错误的位置上。用户照旧点一下背景即可。
        """
        try:
            from . import colorprefs as _cpf
        except Exception:
            return
        # 【只填**这个目标自己**的,不借上一个(用户 2026-09-22 M81_M82 事故)】
        #   原来用 get() 的默认 fallback_last=True → M81 没有自己的预设就借了 M33 的整组值,
        #   其中**蒙版收紧 0.85** 在双星系场上圈不住本体(本体上蒙版只有 0.446),
        #   用户没察觉它已经不是默认值,背景侧的压饱和就削到了星系上。
        #   「省事」的预填跨目标就变成了污染 —— 换目标就该回默认。
        _cam = self._col_identity().get("camera") or ""
        rec = _cpf.get(self._col_target(), fallback_last=False, camera=_cam)
        try:                                    # 原因只带**这个目标自己**的(同上:别跨目标借)
            self.ed_col_reason.setText(((rec or {}).get("note") or "")
                                       if (rec or {}).get("source") in ("target", "pos") else "")
        except AttributeError:
            pass
        if not rec:
            self._append(t("[调色] 这个目标还没有存过预设 → 滑块用默认值(不借用别的目标)"))
            return
        vals = _cpf.clean(rec.get("vals"))
        if rec.get("camera_match") is not True:
            # 别的相机调的那组:R/G/B 是在修那台相机的偏色,不预填(用户 2026-10-09 M33)
            vals.update({"r": 1.0, "g": 1.0, "b": 1.0})
            self._append(t("[调色] 这个目标的预设是在「{}」上调的,这份素材是「{}」→ R/G/B 不预填(那是在修那台相机的偏色)")
                         .format(_cpf.preset_camera(rec) or "?", _cam or t("读不到相机")))
        for k, (sl, _lb) in getattr(self, "_col_sliders", {}).items():
            if k in vals:
                sl.blockSignals(True)
                sl.setValue(int(round(max(sl.minimum(), min(sl.maximum(), vals[k] * 100.0)))))
                sl.blockSignals(False)
        self._col_changed()
        _src = ("这个目标上次调的" if rec.get("source") == "target"
                else "最近一次调的(%s)" % (rec.get("target") or "别的目标"))
        self._append(t("[调色] 滑块已预填为{}:{}").format(_src, _cpf.describe(vals)))

    def _col_changed(self, immediate: bool = False):
        """滑块动了 → **读数立刻更新**,预览交给后台算(见 _col_request)。

        【演变】09-24 加了 140ms 防抖:拖动期间不算、停手才算 —— 可那一算仍在**界面线程**上,
        实测 1000px 预览一次约 6 秒(蒙版漏出/覆盖率每次重找中心、曲线逐像素样条),停手、松手都冻住,
        用户 2026-10-10:「程序处理中滑块就拖不动,看起来是卡死的」。现在:
          · 重算全挪后台线程(_ColPreviewWorker),界面线程只读滑块、收结果贴图 → 滑块永远跟手;
          · 一次只算一张,算的时候又来的请求只留**最新的**,不排长队;
          · 按住拖动时出**草图**(底图半尺寸,几十毫秒),松手出全尺寸并刷新读数;
          · 几何量按底图只算一次、蒙版读数按蒙版缓存、曲线查表(与逐点版差 <1e-4)。
        `immediate` 保留给按钮路径(自动定其余/复位/预设/点背景):直接要全尺寸。
        """
        v = self._col_vals()
        for k, (sl, lb) in getattr(self, "_col_sliders", {}).items():
            if k in ("x2", "mask"):
                lb.setText("%.2f" % v[k])
            elif k in ("bgsat", "bglum"):
                lb.setText("%.0f%%" % (v[k] * 100.0))      # 背景侧显示绝对比例,100%=不动
            else:
                lb.setText("%+.0f%%" % ((v[k] - 1.0) * 100.0))
        self._col_request(draft=(not immediate) and bool(getattr(self, "_col_dragging", False)))

    def _col_slider_released(self):
        self._col_dragging = False
        self._col_changed(immediate=True)

    def _col_render(self):
        """(兼容旧调用点)要一张全尺寸预览。"""
        self._col_request(draft=False)

    def _col_ensure_worker(self):
        if getattr(self, "_col_worker", None) is not None:
            return self._col_worker
        th = QThread(self)
        wk = _ColPreviewWorker()
        wk.moveToThread(th)
        self._col_req_sig.connect(wk.render)              # 跨线程 → 排队连接,在后台线程里执行
        wk.done.connect(self._on_col_done)                # 回到界面线程
        th.start()
        th2 = QThread(self)
        sw = _ColStatsWorker()
        sw.moveToThread(th2)
        self._col_stat_sig.connect(sw.run)
        sw.done.connect(self._on_col_stats)
        th2.start()
        try:
            QApplication.instance().aboutToQuit.connect(
                lambda: [(x.quit(), x.wait(2000)) for x in (th, th2)])
        except Exception:
            pass
        self._col_worker, self._col_wthread = wk, th
        self._col_sworker, self._col_sthread = sw, th2
        self._col_stat_busy, self._col_stat_pending = False, None
        return wk

    def _col_request(self, draft: bool = False):
        """按当前控件状态拍一份**快照**交后台(控件只能在界面线程读)。在算就只留最新一份。"""
        base = getattr(self, "_col_base", None)
        if base is None:
            return
        try:
            if not self.color_panel.isVisible():
                return
        except AttributeError:
            pass
        from . import colorprefs as _cpt
        v = self._col_vals()
        pts = self._col_points() or {}
        bpts = self._col_bg_points() or {}
        use_mask = bool(self.btn_col_mask.isChecked())
        self._col_seq = getattr(self, "_col_seq", 0) + 1
        req = {"id": self._col_seq, "base": base, "base_key": getattr(self, "_col_base_ver", 0),
               "draft": bool(draft), "pts": pts, "bpts": bpts, "use_mask": use_mask,
               "need_mask": bool((pts and use_mask) or bpts), "mask_frac": v.get("mask", 0.30),
               "bg": getattr(self, "_col_bg", None), "ct": _cpt.curve_type(),
               "show_mask": bool(self.btn_col_showmask.isChecked())}
        self._col_ensure_worker()
        if getattr(self, "_col_inflight", False):
            # 全尺寸请求不能被后来的草图顶掉(松手那张必须出);草图之间只留最新
            pend = getattr(self, "_col_pending", None)
            if pend is not None and not pend["draft"] and req["draft"]:
                return
            self._col_pending = req
            return
        self._col_inflight = True
        self._col_req_sig.emit(req)

    def _on_col_done(self, req_id, res):
        """后台算完(界面线程):贴图、刷读数;有排着的就接着算。"""
        self._col_inflight = False
        pend, self._col_pending = getattr(self, "_col_pending", None), None
        try:
            visible = self.color_panel.isVisible()
        except AttributeError:
            visible = False
        # 面板关了、或底图已经换了(换目标/重进面板)→ 这张作废
        if visible and res.get("base_key") == getattr(self, "_col_base_ver", 0):
            if res.get("error"):
                self._append("[调色] 预览重算失败:%s" % res["error"][:80])
            if res.get("no_mask"):
                self._append(t("[调色] 现在没有启用蒙版(勾「只改星系,不动背景」或调背景滑块才有)"))
            if "mask" in res:
                self._col_maskarr = res["mask"]         # 放大镜 / 经验库用同一张(预览分辨率)蒙版
            u8 = res.get("u8")
            if u8 is not None:
                self._col_show_u8(u8)
            if res.get("img_f") is not None:            # 全尺寸那张 → 读数交读数线程(只留最新一份)
                self._col_stat_request({"base": getattr(self, "_col_base", None), "base_key": res["base_key"],
                                        "img": res["img_f"], "mask": res.get("mask"),
                                        "mask_key": res.get("mask_key")})
        if pend is not None and visible:
            self._col_inflight = True
            self._col_req_sig.emit(pend)

    def _col_stat_request(self, req):
        if req.get("base") is None:
            return
        if getattr(self, "_col_stat_busy", False):
            self._col_stat_pending = req
            return
        self._col_stat_busy = True
        self._col_stat_sig.emit(req)

    def _on_col_stats(self, _rid, res):
        self._col_stat_busy = False
        pend, self._col_stat_pending = getattr(self, "_col_stat_pending", None), None
        try:
            visible = self.color_panel.isVisible()
        except AttributeError:
            visible = False
        if visible and res.get("base_key") == getattr(self, "_col_base_ver", 0) and not res.get("error"):
            if res.get("cover"):
                _cv = res["cover"]
                self.lbl_col_cover.setText(
                    t("蒙版盖住天体的 {:.0f}%(占画面 {:.1f}%)—— 剩下的 {:.0f}% 算「背景侧」,"
                      "下面两个背景滑块会按这个比例作用到天体上")
                    .format(_cv["body_med"] * 100, _cv["area_gt50"] * 100, (1 - _cv["body_med"]) * 100))
            if "bg_level" in res:
                self.lbl_col_bgstat.setText(
                    t("背景(本体半径 3 倍以外):电平 {:.3f} · 饱和 {:.3f} · 蒙版漏出 {:.1f}%"
                      " —— 漏出越大,背景的噪声斑块越会跟着提饱和(发紫多半来自这里)")
                    .format(res["bg_level"], res.get("bg_sat", 0.0), 100.0 * float(res.get("leak") or 0.0)))
        if pend is not None and visible:
            self._col_stat_busy = True
            self._col_stat_sig.emit(pend)

    def _col_show_u8(self, u8):
        h, w, _ = u8.shape
        qi = QImage(u8.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
        pm = QPixmap.fromImage(qi.copy())
        # 画出取样点:不画的话用户不知道自己点中了哪(用户 2026-09-21 直接反馈)。
        # 画一个空心十字环:中间留空,免得把被取样的那几个像素本身盖住。
        _pt = getattr(self, "_col_pt", None)
        if _pt and not pm.isNull():
            _px, _py = int(_pt[0] * w), int(_pt[1] * h)
            _pa = QPainter(pm)
            _pa.setRenderHint(QPainter.Antialiasing, True)
            for _c, _wd in ((QColor(0, 0, 0, 170), 3.0), (QColor(255, 255, 255, 230), 1.4)):
                _pa.setPen(QPen(_c, _wd))
                _pa.drawEllipse(_px - 9, _py - 9, 18, 18)
                _pa.drawLine(_px - 15, _py, _px - 11, _py)
                _pa.drawLine(_px + 11, _py, _px + 15, _py)
                _pa.drawLine(_px, _py - 15, _px, _py - 11)
                _pa.drawLine(_px, _py + 11, _px, _py + 15)
            _pa.end()
        if not pm.isNull():
            self._set_preview_pixmap(pm)

    def _col_showmask_toggled(self, on):
        """切换蒙版叠加。**按钮文字跟着变** —— 只靠样式表示开关状态不可靠:
        同一个按钮曾因为用了 `#seg` 的选中态(透明底+深字)在选中后整个看不见,
        用户找不到地方关掉。文字是最后一道保证。"""
        self.btn_col_showmask.setText(t("关掉蒙版显示") if on else t("看蒙版"))
        self._col_changed(immediate=True)

    def _col_autosolve(self):
        """把「除盘色以外」的滑块解出来。盘色(R/G/B)不动 —— 那是唯一留给人的决定。

        【为什么必须解而不是存(用户 2026-09-23 M64 实测)】滑块值**连同一个目标的不同轮次
        都不可移植**:两点曲线绕背景锚点转,而锚点随拉伸走;GHS 评委是 LLM、非确定,
        两轮 D 取 0.275 与 1.0,锚点就从 0.1752 变成 0.1954 —— 照搬同一组预设,
        盘饱和从 0.131 冲到 **0.328**(2.5 倍)、核 R/G 冲到 1.706。
        同一底子上自动求解给出饱和 1.36(而非 6.74),盘饱和 **0.190**(目标 0.20)、蒙版覆盖 60%。
        **增益不可移植,目标可以。**
        """
        base = getattr(self, "_col_base", None)
        if base is None:
            self._append(t("[调色] 还没载入底图,先等预览出来"))
            return
        bg = getattr(self, "_col_bg", None)
        if bg is None:
            from . import galaxycolor as _gca
            import numpy as _np
            bg = float(_np.asarray(_gca.corner_background(_np.asarray(base, float))).mean())
            self._append(t("[调色] 还没点背景 → 先用四角实测 {:.4f} 代替(点选后可再按一次)").format(bg))
        # 【挪后台(用户 2026-10-10「一处理就卡死」)】求解要扫十几档蒙版、再二分饱和,1000px 上约 11s
        #   (几何缓存前 80s+),放在界面线程上整窗冻住。→ 后台算,按钮显示「求解中…」,算完回界面线程填滑块。
        if getattr(self, "_col_solve_th", None) is not None:
            return                                      # 上一次还没算完,别叠
        th = _ColSolveThread(base, bg, self._col_vals(), self)
        th.result.connect(self._col_autosolve_done)
        th.finished.connect(th.deleteLater)
        self._col_solve_th = th
        self.btn_col_auto.setEnabled(False)
        self.btn_col_auto.setText(t("求解中…"))
        th.start()

    def _col_autosolve_done(self, out):
        self._col_solve_th = None
        self.btn_col_auto.setEnabled(True)
        self.btn_col_auto.setText(t("自动定其余"))
        if not isinstance(out, dict) or out.get("error"):
            self._append(t("[调色] 自动求解失败:{}").format(str((out or {}).get("error"))[:120]))
            return
        try:
            if not self.color_panel.isVisible():
                return                                  # 算完时面板已经关了 → 不改滑块
        except AttributeError:
            pass
        v = out["vals"]
        for k, (sl, _lb) in getattr(self, "_col_sliders", {}).items():
            if k in ("r", "g", "b"):        # 盘色不动
                continue
            if k in v:
                sl.blockSignals(True)
                sl.setValue(int(round(float(v[k]) * 100)))
                sl.blockSignals(False)
        self._append(t("[调色] 自动定其余(盘色不动):"))
        for line in out["report"]:
            self._append("        · " + line)
        self._col_maskarr = self._col_maskkey = None      # 蒙版参数变了 → 重算
        self._col_changed(immediate=True)

    def _col_preset(self, vals):
        for k, (sl, _lb) in getattr(self, "_col_sliders", {}).items():
            if k in vals:
                sl.blockSignals(True)
                sl.setValue(int(round(float(vals[k]) * 100)))
                sl.blockSignals(False)
        self._col_changed(immediate=True)

    def _col_reset(self):
        for k, (sl, _lb) in getattr(self, "_col_sliders", {}).items():
            sl.blockSignals(True)
            sl.setValue(25 if k == "x2" else 100)
            sl.blockSignals(False)
        self._col_changed(immediate=True)

    def _col_finish(self, apply_it):
        """收尾:应用走 runner 的 curves op(与预览同一组控制点),或直接跳过。"""
        # 排着的预览请求作废;后台正在算的那张回来时面板已隐藏,_on_col_done 会丢弃它(免得面板关了还重画)
        self._col_pending = None
        self._col_dragging = False
        self.color_panel.setVisible(False)
        self.btn_col_pick.setChecked(False); self._col_pick_mode = False
        self.preview.setCursor(Qt.ArrowCursor)
        w = getattr(self, "worker", None)
        if w is None:
            return
        if not apply_it:
            w.send_color_cmd({"op": "skip"})
            return
        pts = self._col_points()
        bpts = self._col_bg_points()
        if not pts and not bpts:
            self._append(t("[调色] 滑块都在原位,等于没改 → 直接继续。"))
            w.send_color_cmd({"op": "skip"})
            return
        # 【记下这一组当预设】用户 2026-09-21:"在我完成手动参数的处理后,你可以记录下这个
        #   参数,作为预设值。另外现在自动调色的管线也可以参照我调整的数值来修改。"
        #   → 存两份:本目标专用 + `last`(跨目标默认)。全自动路会读它,见 pipeline 的 r11g。
        _rc = None
        try:
            _reason = (self.ed_col_reason.text() or "").strip()
        except AttributeError:
            _reason = ""
        try:
            from . import colorprefs as _cpf
            _v = self._col_vals()
            _id = self._col_identity()
            _rc = _cpf.save(self._col_target(), _v, getattr(self, "_col_bg", None), note=_reason,
                            pos=((_id.get("ra"), _id.get("dec"))
                                 if _id.get("ra") is not None else None),
                            camera=_id.get("camera") or "")
            if _rc.get("conflict"):
                self._append(t("[调色] ★{}").format(_rc["conflict"]))
            else:
                self._append(t("[调色] 这组参数已存为「{}」").format(_rc.get("key") or "?"))
            self._append(t("[调色] 已记下这组参数作为预设:{}").format(_cpf.describe(_v)))
        except Exception as _se:
            self._append(t("[调色] 预设没存上:{}").format(str(_se)[:120]))
        try:
            self._col_capture_experience(_rc, _reason)
        except Exception as _ce:
            self._append(t("[调色] 这次的调色经验没存上:{}").format(str(_ce)[:120]))
        self.lbl_prevtag.setText(t("正在应用你的调色…"))
        w.send_color_cmd({"op": "apply", "points": pts, "bgPoints": bpts,
                          "mask": bool(self.btn_col_mask.isChecked()),
                          "maskFrac": self._col_vals().get("mask", 0.30),
                          "bg": getattr(self, "_col_bg", None)})

    def _col_capture_experience(self, rec, reason):
        """存一份调色经验(见 colorexp):调前/调后全幅 + 全分辨率主体放大 + 测量 + 原因。
        界面线程只做**快照**,读图、裁图、测量都丢后台 —— 点「就这样」必须立刻有反应。"""
        import threading
        from . import colorexp as _cx
        base = getattr(self, "_col_base", None)
        if base is None or not rec or not rec.get("key"):
            return
        prm = self._col_adjust_params()
        if prm.get("mask") is not None:
            prm["mask"] = prm["mask"].copy()
        snap = {"prm": prm, "base": base.copy(), "full": str(getattr(self, "_col_img", "") or ""),
                "rec": dict(rec), "reason": reason, "vals": self._col_vals(),
                "bg": getattr(self, "_col_bg", None)}
        self._exp_res = None

        def _run():
            try:
                self._exp_res = _cx.capture(config.CONFIG_DIR / "color_experience", **snap)
            except Exception as e:
                self._exp_res = {"error": str(e)}
        threading.Thread(target=_run, daemon=True).start()
        self._exp_timer = QTimer(self)
        self._exp_timer.timeout.connect(self._col_exp_poll)
        self._exp_timer.start(400)

    def _col_exp_poll(self):
        r = getattr(self, "_exp_res", None)
        if r is None:
            return
        self._exp_timer.stop()
        if r.get("error"):
            self._append(t("[调色] 这次的调色经验没存上:{}").format(str(r["error"])[:120]))
        else:
            self._append(t("[调色] 已存入调色经验库(调前/调后全幅 + 主体放大 + 测量):{}")
                         .format(r.get("dir")))

    # ── 分步询问模式:岔口面板 ──────────────────────────────────────────────
    def _on_decision(self, point_json, image, preview):
        """流程停在一个岔口 → 显示这一岔口的问题 + 选项按钮 + 自然语言输入。"""
        import json as _json
        try:
            pt = _json.loads(point_json) if point_json else {}
        except Exception:
            pt = {}
        self._dec_point = pt
        if preview and Path(preview).exists():          # 让用户看着**这一步的结果**做决定
            self._final_png = preview
            pm = QPixmap(preview)
            if not pm.isNull():
                self.preview_scroll.setVisible(True); self._set_preview_pixmap(pm)
        if image:
            self._final_xisf = image
        self.lbl_dec_title.setText(pt.get("title") or t("往哪个方向走"))
        self.lbl_dec_why.setText(pt.get("why") or "")
        for b in self._dec_buttons:                     # 选项按钮每次重建(各岔口不同)
            b.setParent(None); b.deleteLater()
        self._dec_buttons = []
        for o in pt.get("options") or []:
            b = QPushButton(o.get("label") or o.get("key") or "?")
            b.setObjectName("primary" if o.get("key") == "keep" else "seg")
            if o.get("hint"):
                b.setToolTip(o["hint"])
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=o.get("key"): self._dec_choose(k))
            self.dec_btnbar.add(b); self._dec_buttons.append(b)
        self.dec_chat_log.clear(); self.btn_dec_apply.setVisible(False)
        self._dec_pending = None
        self.decide_panel.setVisible(True)
        self.lbl_prevtag.setText(t("等你定方向 · {}").format(pt.get("title") or ""))

    def _dec_log(self, text):
        self.dec_chat_log.appendPlainText(text)
        sb = self.dec_chat_log.verticalScrollBar(); sb.setValue(sb.maximum())

    def _on_decide_reply(self, text, set_json):
        """岔口里 AI 的回话。set_json 非空 = 它给出了一套可采用的方向。"""
        self._dec_log("AI: " + text)
        if set_json:
            self._dec_pending = set_json
            self.btn_dec_apply.setVisible(True)
            self._dec_log(t("(按「就按这个走」采用,或者再说一次)"))

    def _dec_choose(self, key):
        if not self.worker:
            return
        self.decide_panel.setVisible(False)
        self.worker.send_decide_cmd({"op": "choose", "key": key})

    def _dec_say(self):
        txt = self.ed_dec_say.text().strip()
        if not txt or not self.worker:
            return
        self._dec_log("你: " + txt)
        self.ed_dec_say.clear()
        QApplication.processEvents()       # 同上:先上屏再排队
        self.worker.send_decide_cmd({"op": "say", "text": txt})

    def _dec_apply(self):
        if not self.worker:
            return
        self.decide_panel.setVisible(False)
        self.worker.send_decide_cmd({"op": "apply"})

    def _pause_target_changed(self, idx):
        """切换要修的通道 → 通知 Worker 切换活动目标(它会回传该通道预览)。"""
        if idx < 0 or not self.worker:
            return
        path = self.cb_pause_target.itemData(idx)
        if path:
            self.worker.send_pause_cmd({"op": "select_target", "path": path})

    def _on_pause_preview(self, preview):
        """暂停中一次矫正完成 → 刷新预览。"""
        if preview and Path(preview).exists():
            self._final_png = preview
            # 放大镜取样源一起换到这次的结果(同名 xisf),否则预览是矫正后、放大镜还是矫正前
            try:
                _sx = Path(preview).with_suffix(".xisf")
                if _sx.exists():
                    self._final_xisf = str(_sx)
            except Exception:
                pass
            pm = QPixmap(preview)
            if not pm.isNull():
                self._set_preview_pixmap(pm)

    def _pause_do_gradient(self):
        if not self.worker:
            return
        self._pause_seq = getattr(self, "_pause_seq", 0) + 1
        # 【立刻给反馈(用户 2026-09-16)】GradientCorrection 要跑十几秒,以前点下去界面毫无动静,
        #   用户以为没反应就连点 → 同一张图被叠着矫正了 8 遍。点一下就禁按钮 + 写日志。
        self._on_pause_busy(True, t("梯度矫正中…"))
        self._append("[暂停] 梯度矫正(GradientCorrection)中,约十几秒…")
        self.worker.send_pause_cmd({"op": "gradient", "seq": self._pause_seq})

    def _on_pause_busy(self, busy, text):
        """暂停面板忙/闲:忙时禁掉全部动作(含继续),并把状态写在标题行 —— 否则用户看不出在跑。"""
        _was = getattr(self, "_pause_busy", False)
        self._pause_busy = bool(busy)
        for _w in ("btn_p_gc", "btn_p_dust", "btn_p_dust_apply", "btn_p_go",
                   "btn_p_send", "btn_p_undo", "ed_pause_chat", "cb_pause_target"):
            _o = getattr(self, _w, None)
            if _o is not None:
                _o.setEnabled(not busy)
        if busy:
            if not _was:        # UI 点下时先置忙、Worker 取到命令又置一次 —— 别把"处理中"当原文存起来
                self._pause_status = self.lbl_pause.text()
            self.lbl_pause.setText("⏳ " + (t(text) if text else t("处理中…")))
        else:
            _old = getattr(self, "_pause_status", "")
            if _old:
                self.lbl_pause.setText(_old)
            self._pause_status = ""
        try:
            self.preview.setCursor(Qt.WaitCursor if busy else
                                   (Qt.CrossCursor if getattr(self, "_dust_mode", False) else Qt.ArrowCursor))
        except Exception:
            pass

    def _pause_send_chat(self):
        """把用户这句话发给 AI(Worker 线程里调 agent → 给参数并执行工具)。"""
        txt = self.ed_pause_chat.text().strip()
        if not txt or not self.worker:
            return
        if not (config.get_setting("llm.provider") or "").strip():
            self._on_pause_chat("sys", "未配置 LLM 评委,无法用 AI 改图(见配置)。")
            return
        self.pause_chat_log.appendPlainText(f"你: {txt}")
        self._start_pause_think()          # 追加「AI: 思考中…（0s）」并起秒表(推理模型慢,给实时反馈)
        self.ed_pause_chat.clear()
        QApplication.processEvents()       # 先把这一帧画出去,再去排队(交互要跟手)
        self.worker.send_pause_cmd({"op": "llm_edit", "text": txt})

    def _on_pause_chat(self, role, text):
        """AI/系统 回复 → 追加到对话框(去掉占位的"思考中…（Ns）")。"""
        self._stop_pause_think()
        # 占位行现在带秒数,按前缀整行剔除(不再靠精确 endswith)
        lines = self.pause_chat_log.toPlainText().split("\n")
        if lines and lines[-1].startswith("AI: 思考中…"):
            lines = lines[:-1]
            self.pause_chat_log.setPlainText("\n".join(lines).rstrip("\n"))
        prefix = {"ai": "AI", "sys": "·"}.get(role, role)
        self.pause_chat_log.appendPlainText(f"{prefix}: {text}")
        sb = self.pause_chat_log.verticalScrollBar(); sb.setValue(sb.maximum())

    def _start_pause_think(self):
        """起「思考中…（Ns）」秒表:每秒原地刷新最后一行,让慢的推理模型不像卡死。"""
        import time
        self._pause_think_t0 = time.time()
        self.pause_chat_log.appendPlainText("AI: 思考中…（0s）")
        t = getattr(self, "_pause_think_timer", None)
        if t is None:
            t = QTimer(self); t.setInterval(1000); t.timeout.connect(self._tick_pause_think)
            self._pause_think_timer = t
        t.start()

    def _tick_pause_think(self):
        import time
        # 最后一行不再是占位(已被回复替换/对话被清空)→ 自动停表,别乱改
        if not self.pause_chat_log.toPlainText().split("\n")[-1].startswith("AI: 思考中…"):
            self._stop_pause_think(); return
        el = int(time.time() - getattr(self, "_pause_think_t0", time.time()))
        cur = self.pause_chat_log.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)   # 选中最后一行
        cur.removeSelectedText(); cur.insertText(f"AI: 思考中…（{el}s）")
        sb = self.pause_chat_log.verticalScrollBar(); sb.setValue(sb.maximum())

    def _stop_pause_think(self):
        t = getattr(self, "_pause_think_timer", None)
        if t is not None:
            t.stop()

    def _pause_toggle_dust(self):
        self._dust_mode = self.btn_p_dust.isChecked()
        self._dust_circle = None; self._dust_act = None
        self.preview.setCursor(Qt.CrossCursor if self._dust_mode else Qt.ArrowCursor)
        if self._dust_mode:
            self._append("[暂停·灰尘] 按住拖出一个圆框住灰尘;拖边缘缩放、拖中心移动;调准后点『✓ 应用修复』(或在圆上双击)。")
        else:
            self._rescale_preview()
        self._sync_dust_apply()

    def _pause_continue(self):
        self._stop_pause_think()
        self.pause_panel.setVisible(False)
        self.cb_pause_target.blockSignals(True); self.cb_pause_target.clear()
        self.cb_pause_target.blockSignals(False)
        self._dust_mode = False; self.btn_p_dust.setChecked(False)
        self.preview.setCursor(Qt.ArrowCursor)
        self.btn_pause.setEnabled(True); self.btn_pause.setText(t("暂停介入"))
        self.lbl_prevtag.setText(t("处理中…"))
        if self.worker:
            self.worker.send_pause_cmd({"op": "continue"})

    def _on_progress(self, op):
        self._done_ops += 1
        ph = _OP_PHASE.get(op)
        if ph is not None and ph > self._max_phase:
            self._max_phase = ph
            self._paint_phases()
        if self._max_phase >= 0:
            self.lbl_prog_stage.setText(
                t("阶段 {}/{} · {}").format(
                    min(self._max_phase + 1, len(PHASES)), len(PHASES),
                    t(PHASES[min(self._max_phase, len(PHASES) - 1)])))
        frac = min(0.99, self._done_ops / max(1, self._expected))
        self.bar.setValue(int(frac * 100))
        el = time.time() - self._start_t
        if frac > 0.05:
            rem = el * (1 - frac) / frac
            # 尾部标"步 N/~M"(真实 op 计数,~=估计;M 取 max 免出现 27/26)——不再显示会误导的"步骤=阶段5/5"
            _tot = max(self._expected, self._done_ops)
            self.lbl_eta.setText(t("已用 {:02d}:{:02d} · 预计剩余 ~{:02d}:{:02d}  ·  步 {}/~{}").format(
                int(el//60), int(el%60), int(rem//60), int(rem%60), self._done_ops, _tot))

    def _paint_phases(self):
        """阶段着色:已完成=青蓝,进行中=薄荷绿,未开始=灰。横向阶段带与右侧路线图共用。"""
        p = self.theme
        cur = self._max_phase
        for i, l in enumerate(getattr(self, "phase_lbls", [])):
            nm = t(PHASES[i]) if i < len(PHASES) else ""
            if i < cur:
                l.setText(f"<span style='color:{p['accent']}'>✓</span>&nbsp;&nbsp;{nm}")
                l.setStyleSheet(f"color:{p['text2']};")
            elif i == cur:
                l.setText(f"<span style='color:{p['accent']}'>●</span>&nbsp;&nbsp;{nm}")
                l.setStyleSheet(f"color:{p['text']};font-weight:600;")
            else:
                l.setText(f"<span style='font-family:\"IBM Plex Mono\"'>{i + 1}</span>&nbsp;&nbsp;{nm}")
                l.setStyleSheet(f"color:{p['muted']};")
        if hasattr(self, "prog_dot"):
            self.prog_dot.set_state(p['accent'], self._end_state == "run")
        self._paint_roadmap()

    def _paint_roadmap(self):
        """右侧空态的流程路线图:按当前流程写阶段说明,按进度点亮。"""
        if not hasattr(self, "road_rows"):
            return
        p = self.theme
        idx = getattr(self, "flow_idx", 0)
        _mode, label = self.FLOWS[idx]
        desc = PHASE_DESC.get(self._derive_kind(), PHASE_DESC["rgb"])   # 阶段说明按派生引擎 kind
        cur = self._max_phase
        self.lbl_road_title.setText(f"{t(label)} · {t('流程路线')}")
        self.lbl_road_sub.setText(t("共 {n} 个阶段 · 开始处理后逐段点亮;").format(n=len(PHASES))
                                  + t("选定交棒点会停在对应阶段。"))
        for i, r in enumerate(self.road_rows):
            r["name"].setText(t(PHASES[i]) if i < len(PHASES) else "")   # 阶段名随语言
            r["desc"].setText(t(desc[i]) if i < len(desc) else "")
            done, now = i < cur, i == cur
            if done:
                r["w"].setObjectName("roadrow")
                r["dot"].setText("✓"); r["tag"].setText(t("完成"))
                r["dot"].setStyleSheet(f"background:{p['sec']};color:{p['bg']};"
                                       "border-radius:10px;font-size:11px;font-weight:bold;")
                r["name"].setStyleSheet(f"color:{p['text']};font-weight:bold;")
                r["tag"].setStyleSheet(f"color:{p['muted']};font-size:11px;")
            elif now:
                r["w"].setObjectName("roadrow_on")
                r["dot"].setText("●")
                r["tag"].setText(t("交棒") if self._end_state == "handoff" else t("进行中"))
                r["dot"].setStyleSheet(f"background:{p['accent_soft']};color:{p['accent']};"
                                       f"border:1px solid {p['accent']};"
                                       "border-radius:10px;font-size:11px;font-weight:bold;")
                r["name"].setStyleSheet(f"color:{p['accent']};font-weight:bold;")
                r["tag"].setStyleSheet(f"color:{p['accent']};font-size:11px;font-weight:bold;")
            else:
                r["w"].setObjectName("roadrow")
                r["dot"].setText(str(i + 1)); r["tag"].setText("")
                r["dot"].setStyleSheet(f"background:transparent;color:{p['muted']};"
                                       f"border:1px solid {p['stroke']};"
                                       "border-radius:10px;font-size:11px;")
                r["name"].setStyleSheet(f"color:{p['muted']};")
                r["tag"].setStyleSheet("")
            r["w"].style().unpolish(r["w"]); r["w"].style().polish(r["w"])
        # 预览卡右上角的状态徽章
        if hasattr(self, "lbl_prevtag"):
            st = self._end_state
            if st == "handoff":
                txt, fg, bg = "已交棒", p['warn'], p['warn_soft']
            elif st == "fail":
                txt, fg, bg = "已停止", p['danger'], p['surf2']
            elif st == "done":
                txt, fg, bg = "已出成片", p['accent'], p['accent_soft']
            elif cur >= 0:
                txt = f"阶段 {min(cur + 1, len(PHASES))}/{len(PHASES)}"
                fg, bg = p['accent'], p['accent_soft']
            else:
                txt, fg, bg = t("等待素材"), p['muted'], p['surf2']
            self.lbl_prevtag.setText(txt)
            self.lbl_prevtag.setStyleSheet(f"background:{bg};color:{fg};border-radius:10px;"
                                           "padding:3px 9px;font-size:11px;font-weight:bold;")

    def _append(self, s):
        # 每条非空日志行前加系统时间戳 [HH:MM:SS](空行=分段留白,保持原样不加)
        ts = time.strftime("%H:%M:%S")
        if s:
            s = "\n".join((f"[{ts}] {ln}" if ln.strip() else ln) for ln in s.split("\n"))
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(s if s.endswith("\n") else s + "\n")
        self.log.moveCursor(self.log.textCursor().End)
        self._sync_caret()

    def _sync_caret(self):
        """把方块光标摆到日志最后一个字符之后。"""
        if not hasattr(self, "caret"):
            return
        self.log.moveCursor(self.log.textCursor().End)
        r = self.log.cursorRect()
        self.caret.setFixedSize(6, max(11, r.height() - 1))
        self.caret.move(r.left() + 1, r.top())
        self.caret.set_color(self.theme['logmark'])
        self.caret.show(); self.caret.raise_()

    def _show_stage_preview(self, path):
        # 处理过程中把每步的阶段效果图显示到右侧预览框(增强参与感)
        try:
            if not path or not Path(path).exists():
                return
            pm = QPixmap(path)
            if pm.isNull():
                return
            # 【面板设的"这一步"在流程往下走时就过期(用户 2026-09-25 M95_M96_M105:「放大镜里还是前一步」)】
            #   暂停介入 / 调色 / 岔口三个面板进入时都把 _final_xisf、_final_png 指向当时那张图,好让放大镜
            #   看"这一步"。可放大镜取样源是 `_final_xisf or _stage_xisf` —— 前者一旦被面板设上,整轮剩下的
            #   时间都压着后者:调完色流程一路走到成片,放大镜还钉在调色面板那张**去星、调色前**的底图上。
            #   (2026-09-23 那次只让 _stage_xisf 跟上了,没看出它被 _final_xisf 压着,所以没修好。)
            #   运行中本不存在真正的成片(开跑即清空,跑完 _finished 才设),新阶段预览一到就一并作废。
            #   跑完之后的预览(AI 编辑等)不受影响:那时 _end_state 已不是 run。
            if getattr(self, "_end_state", "") == "run":
                self._final_xisf = ""
                self._final_png = ""
            # 【处理过程中也能像素级放大(用户 2026-09-14)】阶段预览 png 旁边就是同名的全分辨率 xisf,
            #   记下来给放大镜用;没有就留空,放大镜自动回退到这张预览图。
            try:
                _sx = Path(path).with_suffix(".xisf")
                self._stage_xisf = str(_sx) if _sx.exists() else ""
            except Exception:
                self._stage_xisf = ""
            self._set_preview_pixmap(pm)
        except Exception:
            pass

    def _finished(self, ok, png, xis, scores):
        self.thread.quit(); self.thread.wait()
        self.thread = None; self.worker = None
        QTimer.singleShot(0, self._sync_steps)     # 有成片了 →「处理」打勾(等 _final_png 落定)
        try:
            self._refresh_run_size()           # 本次处理产生的新中间产物 → 重扫,刷新按钮体积
        except Exception:
            pass                               # 体积统计**绝不能**阻断"完成"(曾因陈旧线程引用崩溃卡住 UI)
        self.btn_run.setEnabled(True); self.btn_run.setText(t("▶ 开始处理"))
        # 【按钮文字被裁(用户 2026-09-14:「开始处理那个按钮,理字被裁掉了」)】处理中文字变成更短的
        #   「处理中…」,FlowBar 用的是自定义流式布局、不会因子控件文字变化自动重算宽度 → 切回长文案时
        #   还占着短文案的宽度,末字被裁。切文字后显式让按钮重算尺寸提示、并触发父布局重排。
        self._refit_run_btn()
        self._set_run_glow(True)       # 处理结束/空闲:恢复绿辉光
        self.btn_abort.setVisible(False); self.btn_abort.setEnabled(True)
        self.btn_pause.setVisible(False); self.pause_panel.setVisible(False)
        self.decide_panel.setVisible(False)
        self._dust_mode = False; self.preview.setCursor(Qt.ArrowCursor)
        self.bar_main.refresh()
        self._pulse.stop()
        self.bar_shim.stop(); self.run_shim.stop()
        if ok:
            self.bar.setValue(100)
            el = time.time() - self._start_t
            self.lbl_eta.setText(t("完成 · 用时 {:02d}:{:02d}").format(int(el//60), int(el%60)))
            self.lbl_prog_stage.setText(t("已完成"))
            self.lbl_result_hint.setText(t("用时 {:02d}:{:02d}").format(int(el//60), int(el%60)))
            self._final_png, self._final_xisf = png, xis
            if png and Path(png).exists():
                pm = QPixmap(png)
                if not pm.isNull():
                    self._set_preview_pixmap(pm)
            self._build_palette_bar((scores or {}).get("_finals"))
            ho = (scores or {}).get("_handoff")
            if ho:
                # 交棒:提示产物位置,并强调 PI 已/将释放给用户接管
                d = ho.get("dir"); stg = ho.get("stage")
                self._end_state = "handoff"
                self.lbl_eta.setText(t("已停在【{}】· 交棒").format(t(stg)))
                self._append(f"[交棒] 停在【{stg}】,产物已导出:{d}")
                self.gresult.setVisible(False)
            else:
                self._last_scores = scores or {}
                self._scored_pal = ((scores or {}).get("_critic") or {}).get("palette_evaluated")
                self._show_scores(scores)
                self._reveal(self.gresult)
                # 多页 IA:成片就绪 → 露出审阅/导出内容,收起空态,自动切到「审阅」屏
                if hasattr(self, "lbl_review_empty"):
                    self.lbl_review_empty.setVisible(False)
                if hasattr(self, "export_panel"):
                    self.export_panel.setVisible(True)
                if hasattr(self, "lbl_export_empty"):
                    self.lbl_export_empty.setVisible(False)
                if hasattr(self, "_go_stage"):
                    self._go_stage(3)            # 完成 → 切到「审阅」屏看评分
                self._end_state = "done"
                self._append(f"[✓] 完成:{png}")
                # LLM 主观评分:后台异步补,**不阻塞"完成"**(kimi-k3 推理慢)。
                #   SHO 已带 overall / 交棒 / 无评委 / 无图 则跳过。评完 _on_llm_score 合并刷新评分行。
                #   评分按钮:有评委+有图就露出「重新评分」,随时可手动重评(超时/想再评)。
                if png and Path(png).exists() and (config.get_setting("llm.provider") or "").strip():
                    self.btn_rescore.setVisible(True)
                    if "overall" not in (scores or {}):
                        # 延迟 2.5s 再发(让 PI 释放/体积扫描/服务端都收尾),失败自动重试 2 次 —— 抹平瞬态接口错误
                        QTimer.singleShot(2500, lambda pg=png: self._kick_llm_score(pg, retries=2))
        else:
            self._end_state = "fail"
            self.lbl_eta.setText(t("已停止"))
            self._append("[✗] 处理未完成,见日志。")

        # 处理结束 → 按设置自动释放 PixInsight(交棒时必须放开,否则用户无法手工接着做)
        try:
            ho2 = (scores or {}).get("_handoff")
            if getattr(self, "chk_release", None) and (self.chk_release.isChecked() or ho2):
                self._do_release(quiet=True)
                self._append("[释放] 已把 PixInsight 交还给你(runner/看门狗已停)。")
        except Exception as e:
            self._append(f"[释放] 自动释放失败:{e}")
        self._paint_phases()
        if ok:                          # 出了新成片 → 即时自动保存,别让处理进度因忘存而丢(用户 2026-09-07)
            self._mark_dirty()
            self._autosave()

    def _build_palette_bar(self, finals):
        """多配色成片 → 每档一个切换按钮;点了切预览 + 把导出目标指向该档。"""
        self._finals = dict(finals or {})
        self.pal_bar.clear(); self.pal_btns = {}
        if len(self._finals) <= 1:
            self.pal_bar.setVisible(False); self._cur_pal = None
            return
        # 主版 = _final_xisf 对应的那档(worker 已把主版放第一个)
        main = None
        for k, v in self._finals.items():
            if self._final_xisf and Path(str(v)) == Path(str(self._final_xisf)):
                main = k; break
        main = main or next(iter(self._finals))
        _order = ["hoo"] + PALETTES          # HOO 的主版 hoo 不在 PALETTES 里,别被过滤掉
        for pal in ([p for p in _order if p in self._finals]
                    + [p for p in self._finals if p not in _order]):
            lab = f"{PAL_LABELS.get(pal, pal)}"
            # segdev:pal_bar 是 FlowBar 无 SlideIndicator → 选中态用 segdev 实心绿底(#seg:checked 透明底深字会隐形)
            b = QPushButton(lab); b.setObjectName("segdev"); b.setCheckable(True)
            b.setChecked(pal == main); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, pk=pal: self._switch_palette(pk))
            self.pal_btns[pal] = self.pal_bar.add(b)
        self.pal_bar.setVisible(True); self.pal_bar.refresh()
        self._cur_pal = main

    def _switch_palette(self, pal):
        """切换预览到某配色档,并把导出目标(_final_xisf/_final_png)指向它。"""
        xis = self._finals.get(pal)
        if not xis or not Path(str(xis)).exists():
            return
        self._cur_pal = pal
        for k, b in self.pal_btns.items():
            b.setChecked(k == pal)
        self._final_xisf = str(xis)
        pp = Path(str(xis)).with_suffix(".png")
        self._final_png = str(pp) if pp.exists() else self._final_png
        if self._final_png and Path(self._final_png).exists():
            pm = QPixmap(self._final_png)
            if not pm.isNull():
                self._set_preview_pixmap(pm)
        self.lbl_prevtag.setText(t("已出成片 · {}").format(t(PAL_LABELS.get(pal, pal))))
        # 评分只针对被评的那档(评委只评主版)。切到别档:有按需评分缓存就显示,否则诚实标注 +
        # 给「评这一档」按钮(功能C)。
        scored = getattr(self, "_scored_pal", None)
        llm_on = bool((config.get_setting("llm.provider") or "").strip())
        self._clear_remedy_rows()
        if pal in self._pal_scores:
            # 这一档已按需评过 → 显示它自己的分,不给按钮
            self._show_scores(self._pal_scores[pal])
            self.btn_scorepal.setVisible(False)
        elif pal == scored and self._last_scores:
            # 主版(评委评过的那档)→ 显示主版分,不给按钮
            self._show_scores(self._last_scores)
            self.btn_scorepal.setVisible(False)
        else:
            # 该档**没有自己的评分** → 诚实标注 + 给「评这一档」按钮(只要配了 LLM 就给)。
            # 涵盖:切到未评的别档;以及评委整体没跑(scored 为空)时的任意档。
            pcol = self.theme
            if scored:
                note = t("当前档【{}】未单独评分 —— 评委只评了主版【{}】。四档同基底,差异只在配色。").format(
                    t(PAL_LABELS.get(pal, pal)), t(PAL_LABELS.get(scored, scored)))
            else:
                note = t("当前档【{}】尚未评分。").format(t(PAL_LABELS.get(pal, pal)))
            self.lbl_scores.setText(
                f"<span style='color:{pcol['muted']};font-size:11px'>{note}"
                + ("" if llm_on else t("(未配置 LLM 评委)")) + "</span>")
            self.btn_scorepal.setText(t("评这一档 · {}").format(t(PAL_LABELS.get(pal, pal))))
            self.btn_scorepal.setVisible(llm_on)

    def eventFilter(self, obj, ev):
        # 放大镜(AstroBin 式):非灰尘模式下按住成片预览 → 光标处圆形放大镜看全分辨率,拖动平移,松开还原。
        # 手动调色·点选背景:**必须排在放大镜分支之前**。放大镜那段在 MouseButtonPress 上
        #   `return True` 把事件吃掉了 —— 取点分支原本放在它后面,于是**一次都没触发过**
        #   (用户 2026-09-21:"点选背景时会触发放大镜,但我不知道自己点的是哪里" —— 实际是没取到点)。
        #   这里取完点**不拦截**,继续往下走让放大镜照常弹(用户说不介意,而且按住能看清像素、更好瞄)。
        if (obj is getattr(self, "preview", None) and getattr(self, "_col_pick_mode", False)
                and ev.type() == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton):
            try:
                self._col_pick_at(ev.pos().x(), ev.pos().y())
            except Exception as _cpe:
                self._append("[调色] 取背景失败:%s" % str(_cpe)[:80])
        # Qt 在 MouseButtonPress 后隐式抓取鼠标 → 拖出预览、在外面松开的 Release 仍回到本 eventFilter。
        if (obj is getattr(self, "preview", None) and not getattr(self, "_dust_mode", False)
                and getattr(self, "_pm_raw", None) is not None):
            tt = ev.type()
            if tt == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                self._loupe_on = True
                if self._hires_key() and self._pm_hires_key != self._hires_key():
                    QApplication.setOverrideCursor(Qt.WaitCursor)   # 首次载入全分辨率成片(缓存后即时)
                    try:
                        self._ensure_hires_loupe()
                    finally:
                        QApplication.restoreOverrideCursor()
                self.preview.setCursor(Qt.BlankCursor)      # 光标让位:镜心即光标点
                self._loupe_move(ev.pos().x(), ev.pos().y())
                return True
            if tt == QEvent.MouseMove and getattr(self, "_loupe_on", False):
                self._loupe_move(ev.pos().x(), ev.pos().y())
                return True
            if tt == QEvent.MouseButtonRelease and getattr(self, "_loupe_on", False):
                self._loupe_on = False
                self._loupe.hide()
                self.preview.setCursor(Qt.ArrowCursor)
                return True
        # 导出屏预览的放大镜(与主预览同款,复用全分辨率成片 _pm_hires;用户 2026-09-07)
        if (obj is getattr(self, "export_preview", None)
                and getattr(self, "_export_pm_display", None) is not None):
            tt = ev.type()

            def _emove(_ev):
                self._loupe_move(_ev.pos().x(), _ev.pos().y(), widget=self.export_preview,
                                 disp=self._export_pm_display, loupe=self._export_loupe,
                                 raw_fallback=getattr(self, "_export_src_pm", None))
            if tt == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                self._export_loupe_on = True
                if self._hires_key() and self._pm_hires_key != self._hires_key():
                    QApplication.setOverrideCursor(Qt.WaitCursor)   # 首次载入全分辨率成片(缓存后即时)
                    try:
                        self._ensure_hires_loupe()
                    finally:
                        QApplication.restoreOverrideCursor()
                self.export_preview.setCursor(Qt.BlankCursor)
                _emove(ev)
                return True
            if tt == QEvent.MouseMove and getattr(self, "_export_loupe_on", False):
                _emove(ev)
                return True
            if tt == QEvent.MouseButtonRelease and getattr(self, "_export_loupe_on", False):
                self._export_loupe_on = False
                self._export_loupe.hide()
                self.export_preview.setCursor(Qt.ArrowCursor)
                return True
        # 灰尘修复:画一个可编辑的圆(拖边缘缩放、拖中心移动,像 PS 图层),**双击应用**。
        if obj is getattr(self, "preview", None) and getattr(self, "_dust_mode", False):
            import math
            t = ev.type()
            px, py = (ev.pos().x(), ev.pos().y()) if hasattr(ev, "pos") else (0, 0)
            c = getattr(self, "_dust_circle", None)
            if t == QEvent.MouseButtonDblClick:
                if c and c["r"] >= 6:
                    self._apply_dust_circle()
                return True
            if t == QEvent.MouseButtonPress:
                if c:
                    d = math.hypot(px - c["cx"], py - c["cy"])
                    if abs(d - c["r"]) <= max(9, c["r"] * 0.18):
                        self._dust_act = {"m": "resize"}                     # 拖边缘缩放
                    elif d < c["r"]:
                        self._dust_act = {"m": "move", "dx": px - c["cx"], "dy": py - c["cy"]}  # 拖中心移动
                    else:
                        self._dust_circle = {"cx": px, "cy": py, "r": 0.0}; self._dust_act = {"m": "new"}
                else:
                    self._dust_circle = {"cx": px, "cy": py, "r": 0.0}; self._dust_act = {"m": "new"}
                self._redraw_dust(); return True
            if t == QEvent.MouseMove and getattr(self, "_dust_act", None) and self._dust_circle:
                cc, a = self._dust_circle, self._dust_act
                if a["m"] in ("new", "resize"):
                    cc["r"] = math.hypot(px - cc["cx"], py - cc["cy"])
                elif a["m"] == "move":
                    cc["cx"], cc["cy"] = px - a["dx"], py - a["dy"]
                self._redraw_dust(); return True
            if t == QEvent.MouseButtonRelease and getattr(self, "_dust_act", None):
                self._dust_act = None
                if self._dust_circle and self._dust_circle["r"] < 6:
                    self._dust_circle = None; self._rescale_preview(); self._sync_dust_apply()
                else:
                    self._redraw_dust()
                return True
        return super().eventFilter(obj, ev)

    def _redraw_dust(self):
        """把当前可编辑圆画在预览上(基于缓存显示图重绘,不动原图)。"""
        base = getattr(self, "_pm_display", None); c = getattr(self, "_dust_circle", None)
        if base is None or base.isNull():
            return
        canvas = QPixmap(base)
        if c:
            ox = max(0, (self.preview.width() - base.width()) / 2.0)
            oy = max(0, (self.preview.height() - base.height()) / 2.0)
            cx, cy, r = c["cx"] - ox, c["cy"] - oy, c["r"]
            p = QPainter(canvas); p.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(120, 230, 160)); pen.setWidth(2); p.setPen(pen)
            p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
            # 边缘四个小手柄 + 中心点,提示可拖动
            p.setBrush(QColor(120, 230, 160))
            for hx, hy in ((cx + r, cy), (cx - r, cy), (cx, cy + r), (cx, cy - r)):
                p.drawEllipse(int(hx - 3), int(hy - 3), 6, 6)
            p.drawEllipse(int(cx - 2), int(cy - 2), 4, 4)
            p.end()
        self.preview.setPixmap(canvas)
        self._sync_dust_apply()

    def _sync_dust_apply(self):
        """画出有效圆(r≥6)才显示『应用修复』按钮 —— 引导用户点按钮,不必靠不直观的双击。"""
        c = getattr(self, "_dust_circle", None)
        ready = bool(getattr(self, "_dust_mode", False) and c and c.get("r", 0) >= 6)
        for name in ("btn_p_dust_apply", "btn_dust_apply"):
            b = getattr(self, name, None)
            if b is not None:
                b.setVisible(ready)

    # ---------- 成片后交互:共用骨架(runner 跑单 op → 重渲染当前档)----------
    def _ensure_models(self):
        """把内置 AI 模型(如 NXT 旧版 NoiseXTerminator.2.pb)装回 PixInsight library。
        本会话成功装齐一次后不再重复(no_pi/失败则下次再试)。缺 PI 路径时静默跳过。"""
        if getattr(self, "_models_ok", False):
            return
        if not config.pixinsight_exe():             # PI 路径未设 → 等设好后 _ensure_runner 会再次尝试
            return
        try:
            from . import deps as _deps
            res = _deps.ensure_bundled_models(log=self._append)
            if res and all(r.get("status") in ("present", "restored") for r in res):
                self._models_ok = True              # 全部到位才封存,避免每次操作重复检查
        except Exception as e:
            self._append(f"[模型] 装回检查异常(忽略):{e}")

    def _ensure_runner(self, label="操作") -> bool:
        """确保 job-runner 在线:不在线就**自动冷启动 PixInsight**并等就绪(最多 ~90s,
        wait 光标 + processEvents 保持响应)。返回是否就绪。给成片后交互(降饱和/降噪/灰尘)复用。"""
        self._ensure_models()                       # 确保内置 AI 模型(NXT 旧版等)已装回 PI(本会话仅实做一次)
        if protocol.runner_up():                    # 在线 or 忙(在跑别的任务)都算就位,别拉起第二个 PI
            return True
        if not config.pixinsight_exe():
            QMessageBox.warning(self, t("未找到 PixInsight"), t("请在『配置』里设置 PixInsight 路径后再操作。"))
            return False
        self._append(f"[{label}] runner 未在线 → 自动启动 PixInsight,就绪后执行…")
        if not self._launch_pi():
            return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        ready = False
        try:
            for _ in range(180):
                if protocol.runner_alive():
                    ready = True; break
                QApplication.processEvents(); time.sleep(0.5)
        finally:
            QApplication.restoreOverrideCursor()
        if not ready:
            QMessageBox.warning(self, t("启动超时"), t("PixInsight/job-runner 未能在 90s 内就绪,请稍后重试。"))
        return ready

    def _run_op_on_final(self, op, params, tag, label, apply_all=False):
        """在成片上跑一个 op(经 runner),更新当前档 + 重渲染。apply_all=同样套到所有配色档
        (灰尘环各档位置相同,一起修才一致)。需 runner 在线。返回是否成功。"""
        if not (self._final_xisf and Path(self._final_xisf).exists()):
            QMessageBox.information(self, label, t("没有可处理的成片。")); return False
        if op == "graxpert_bge":                     # GraXpert 走 Python CLI,不经 runner(单独分支)
            return self._run_graxpert_on_final(params, tag, label, apply_all)
        if op == "depurple_stars":                   # 去星点紫·严谨版:分离星点→星点层去紫→合回(多步 runner)
            return self._run_depurple_stars_on_final(params, tag, label)
        # runner 未在线(常见:处理完自动释放了 PI)→ **自动拉起 PixInsight**,不再让用户手动启动
        if not self._ensure_runner(label):
            return False
        targets = ([(k, v) for k, v in self._finals.items()] if apply_all and self._finals
                   else [(self._cur_pal or "main", self._final_xisf)])
        ok = False
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._append(f"[{label}] 处理中…")
            for pal, xis in targets:
                if not xis or not Path(str(xis)).exists():
                    continue
                base = f"edit_{tag}_{pal}"
                outp = str(config.RUN_DIR / f"{base}.xisf").replace("\\", "/")
                outpng = str(config.RUN_DIR / f"{base}.png").replace("\\", "/")
                job = protocol.new_job(op, input=str(xis), params=params,
                                       outputs={"image": outp, "preview": outpng})
                protocol.submit(job)
                r = protocol.wait_result(job["job_id"], timeout=600)
                if r.get("status") != "ok":
                    raise RuntimeError(r.get("error") or "op 失败")
                if pal in self._finals:
                    self._finals[pal] = r.get("image") or outp
                if (pal == (self._cur_pal or "main")) or not apply_all:
                    self._final_xisf = r.get("image") or outp
                    self._final_png = r.get("preview") or outpng
            ok = True
        except Exception as e:
            QMessageBox.critical(self, t(label), t("{}失败:{}").format(t(label), e))
        finally:
            QApplication.restoreOverrideCursor()
        if ok and self._final_png and Path(self._final_png).exists():
            pm = QPixmap(self._final_png)
            if not pm.isNull():
                self._set_preview_pixmap(pm)
            self._append(f"[{label}] 完成 → {self._final_xisf}")
        return ok

    def _run_graxpert_on_final(self, params, tag, label, apply_all=False):
        """GraXpert AI 背景提取(治**斑块状/不规则云残留**;polybg/gradient 那类平滑多项式压不掉)。
        走 GraXpert 的 Python CLI 子进程(不经 runner),边跑边泵事件防"未响应";完成后更新档 + 重渲染。"""
        from . import graxpert
        if not graxpert.available():
            QMessageBox.information(self, t(label),
                                    t("未检测到 GraXpert。请在『配置』里把 graxpert_path 指向 GraXpert.exe(装默认位置可自动识别)。"))
            return False
        try:
            _sm = float(params.get("smoothing", 0.2))
        except (TypeError, ValueError):
            _sm = 0.2
        _sm = max(0.0, min(1.0, _sm))
        targets = ([(k, v) for k, v in self._finals.items()] if apply_all and self._finals
                   else [(self._cur_pal or "main", self._final_xisf)])
        ok = False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for pal, xis in targets:
                if not xis or not Path(str(xis)).exists():
                    continue
                base = f"edit_{tag}_{pal}"
                outnoext = str(config.RUN_DIR / base).replace("\\", "/")
                self._append(f"[{label}] GraXpert AI 背景提取中(smoothing={_sm},约 1-2 分钟,不阻塞界面)…")
                QApplication.processEvents()
                outx = graxpert.background_extraction(str(xis), outnoext, smoothing=_sm, gpu=False,
                                                      timeout=600, on_poll=QApplication.processEvents)
                outpng = self._save_display_png(outx, outnoext + ".png")
                if pal in self._finals:
                    self._finals[pal] = outx
                if pal == (self._cur_pal or "main") or not apply_all:
                    self._final_xisf = outx
                    self._final_png = outpng
            ok = True
        except Exception as e:
            QMessageBox.critical(self, t(label), t("{}失败:{}").format(t(label), e))
        finally:
            QApplication.restoreOverrideCursor()
        if ok and self._final_png and Path(self._final_png).exists():
            pm = QPixmap(self._final_png)
            if not pm.isNull():
                self._set_preview_pixmap(pm)
            self._append(f"[{label}] 完成 → {self._final_xisf}")
        return ok

    def _save_display_png(self, xisf_path, png_path, max_px=1600):
        """把**显示域**成片 xisf(已非线性 0..1,不再拉伸)渲染为预览 PNG;位深自适应归一,长边缩到 max_px。"""
        import numpy as np
        from xisf import XISF
        arr = np.asarray(XISF(str(xisf_path)).read_image(0))
        if arr.dtype == np.uint8:
            a = arr.astype(np.float32) / 255.0
        elif arr.dtype == np.uint16:
            a = arr.astype(np.float32) / 65535.0
        elif np.issubdtype(arr.dtype, np.integer):
            a = arr.astype(np.float32) / float(np.iinfo(arr.dtype).max)
        else:
            a = np.clip(arr.astype(np.float32), 0.0, 1.0)
        if a.ndim == 2:
            a = np.stack([a, a, a], axis=-1)
        a = a[:, :, :3]
        u8 = np.ascontiguousarray((np.clip(a, 0, 1) * 255.0 + 0.5).astype(np.uint8))
        try:
            import cv2
            h, w = u8.shape[:2]
            if max(h, w) > max_px:
                s = max_px / float(max(h, w))
                u8 = cv2.resize(u8, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(png_path), cv2.cvtColor(u8, cv2.COLOR_RGB2BGR))
        except Exception:
            from PyQt5.QtGui import QImage
            h, w = u8.shape[:2]
            QImage(u8.tobytes(), w, h, 3 * w, QImage.Format_RGB888).save(str(png_path))
        return str(png_path)

    def _run_depurple_stars_on_final(self, params, tag, label):
        """去星点紫·**严谨版**(用户 2026-09-09:有星云/星系时全局去紫影响极大):对成片 SXT 重新分离星点 →
        **只对星点层去紫**(反相→SCNR→反相)→ screen 合回星点。去星底图(星云/星系)完全不被碰。
        SXT/合星失败 → 回退整图去紫(自限,中性背景不动)。三步都经 runner,边跑边泵事件防"未响应"。"""
        if not self._ensure_runner(label):
            return False
        try:
            _am = float((params or {}).get("amount", 0.7))
        except (TypeError, ValueError):
            _am = 0.7
        _am = max(0.0, min(1.0, _am))
        xis = str(self._final_xisf)
        R = config.RUN_DIR
        _starless = str((R / f"edit_{tag}_starless.xisf")).replace("\\", "/")
        _stars = str((R / f"edit_{tag}_stars.xisf")).replace("\\", "/")
        _dpstars = str((R / f"edit_{tag}_stars_dp.xisf")).replace("\\", "/")
        _out = str((R / f"edit_{tag}_final.xisf")).replace("\\", "/")
        _outpng = str((R / f"edit_{tag}_final.png")).replace("\\", "/")
        _pump = QApplication.processEvents
        ok = False

        def _job(op, inp, prm, outs, to=600):
            j = protocol.new_job(op, input=str(inp), params=prm, outputs=outs)
            protocol.submit(j)
            r = protocol.wait_result(j["job_id"], timeout=to, on_poll=_pump)
            if r.get("status") != "ok":
                raise RuntimeError(r.get("error") or f"{op} 失败")
            return r

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._append("[去星点紫] SXT 分离星点(把星点从星云/星系里抠出来单独处理)…")
            _pump()
            r1 = _job("starsep", xis, {"linear": False}, {"image": _starless, "stars": _stars})
            _starless_p = r1.get("image") or _starless
            _stars_p = r1.get("stars") or _stars
            self._append(f"[去星点紫] 只对星点层去紫:反相→SCNR 去绿→反相(amount={_am})…")
            _pump()
            r2 = _job("scnr", _stars_p, {"amount": _am, "depurple": True, "linear": False},
                      {"image": _dpstars}, to=300)
            _dp_p = r2.get("image") or _dpstars
            self._append("[去星点紫] screen 合回星点(星云/星系底图未被碰)…")
            _pump()
            r3 = _job("recombine", _starless_p, {"stars": _dp_p, "linear": False},
                      {"image": _out, "preview": _outpng}, to=300)
            self._final_xisf = r3.get("image") or _out
            self._final_png = r3.get("preview") or _outpng
            ok = True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            # 【回退】SXT 不可用/分离失败 → 整图去紫(自限:只削偏紫像素,中性背景不动)
            self._append(f"[去星点紫] 分离/合回失败({e})→ 回退整图去紫(自限)…")
            return self._run_op_on_final("scnr", {"amount": _am, "depurple": True, "linear": False},
                                         tag=tag + "_whole", label=label)
        finally:
            if ok:
                QApplication.restoreOverrideCursor()
        if ok and self._final_png and Path(self._final_png).exists():
            pm = QPixmap(self._final_png)
            if not pm.isNull():
                self._set_preview_pixmap(pm)
            self._append(f"[去星点紫] 完成(星点层去紫·星云/星系未动)→ {self._final_xisf}")
        return ok

    # ---------- 功能A:点选灰尘修复 ----------
    def _toggle_dust_mode(self):
        on = self.btn_dust.isChecked()
        if on and not (self._final_png and Path(self._final_png).exists()):
            self.btn_dust.setChecked(False); return
        self._dust_mode = on
        self._dust_circle = None; self._dust_act = None
        if on:
            self.preview.setCursor(Qt.CrossCursor)
            self.lbl_prevtag.setText(t("拖拽画圆框住灰尘,可拖边缘缩放/拖中心移动,点『应用修复』"))
            self._append("[灰尘修复] 在预览上按住拖出一个圆框住灰尘;可拖边缘缩放、拖中心移动;调准后点『✓ 应用修复』(或在圆上双击)。")
        else:
            self.preview.setCursor(Qt.ArrowCursor)
            self._rescale_preview()
            self.lbl_prevtag.setText(t("已出成片 · {}").format(t(PAL_LABELS.get(self._cur_pal, self._cur_pal or ''))))
        self._sync_dust_apply()

    def _preview_click_to_image(self, ev):
        """把预览 QLabel 上的点击坐标映射到成片 png 的像素坐标(考虑等比缩放留白)。"""
        pm = self.preview.pixmap()
        if pm is None or pm.isNull():
            return None
        lw, lh = self.preview.width(), self.preview.height()
        pw, ph = pm.width(), pm.height()
        # 居中留白偏移
        ox, oy = (lw - pw) / 2.0, (lh - ph) / 2.0
        x, y = ev.pos().x() - ox, ev.pos().y() - oy
        if x < 0 or y < 0 or x >= pw or y >= ph:
            return None
        # pixmap 是从成片 png 缩放来的 → 换算回 png 像素
        src = QPixmap(self._final_png)
        if src.isNull():
            return None
        sx, sy = src.width() / pw, src.height() / ph
        return x * sx, y * sy, src.width(), src.height()

    def _circle_to_png(self):
        """把当前可编辑圆(label 坐标)映射到成片 png 像素:返回 (cx_png, cy_png, r_png, png_w, png_h)。"""
        c = getattr(self, "_dust_circle", None)
        pm = self.preview.pixmap()
        if not c or pm is None or pm.isNull():
            return None
        # label 里 pixmap 居中,但 _pm_display 是真实显示图(pixmap 可能被叠加过圈)→ 用它的尺寸
        base = getattr(self, "_pm_display", None) or pm
        pw, ph = base.width(), base.height()
        ox, oy = (self.preview.width() - pw) / 2.0, (self.preview.height() - ph) / 2.0
        x, y, r = c["cx"] - ox, c["cy"] - oy, c["r"]
        src = QPixmap(self._final_png)
        if src.isNull():
            return None
        s = src.width() / pw
        return x * s, y * s, r * s, src.width(), src.height()

    def _apply_dust_circle(self):
        """按用户画好的圆做人工平场(不再自动猜半径;圆即用户指定的修复区)。"""
        m = self._circle_to_png()
        if not m:
            return
        cx_png, cy_png, r_png, png_w, png_h = m
        self._dust_circle = None; self._dust_act = None; self._sync_dust_apply()
        # 暂停中:runner 由 Worker 线程驱动 → 交 png 坐标给它换算+flatpatch
        if self.pause_panel.isVisible() and self.worker:
            self._dust_mode = False; self.btn_p_dust.setChecked(False); self.preview.setCursor(Qt.ArrowCursor)
            self._append(f"[暂停·灰尘] 圆心≈({cx_png:.0f},{cy_png:.0f}) 半径≈{r_png:.0f}px → 交程序修")
            self.worker.send_pause_cmd({"op": "flatpatch", "cx_png": cx_png, "cy_png": cy_png,
                                        "r_png": r_png, "png_w": png_w, "png_h": png_h})
            return
        # 无 PI 成片(zero-PI 引擎输出,_final_xisf 为空 → 无 runner)→ 纯 cv2 圈内中和蓝紫灰尘投影,不拉 PI
        if not self._final_xisf:
            self._dust_mode = False; self.btn_dust.setChecked(False); self.preview.setCursor(Qt.ArrowCursor)
            if not (self._final_png and Path(self._final_png).exists()):
                return
            self._append(f"[灰尘修复·无 PI] 圈心≈({cx_png:.0f},{cy_png:.0f}) 半径≈{r_png:.0f}px → 圈内自动中和蓝紫灰尘投影(纯 cv2,不用 PI)")
            try:
                from . import rgb_ha_engine
                rgb_ha_engine.neutralize_dust_circle(self._final_png, self._final_png,
                                                     cx_png, cy_png, r_png, log=self._append)
            except Exception as e:
                self._append(f"[灰尘修复·无 PI] 失败:{e}")
                return
            pm = QPixmap(self._final_png)
            if not pm.isNull():
                self._set_preview_pixmap(pm)
            return
        # 成片后工具:需 runner(inspect+flatpatch);不在线自动拉起 PI
        if not self._ensure_runner("灰尘修复"):
            self._dust_mode = False; self.btn_dust.setChecked(False); self.preview.setCursor(Qt.ArrowCursor)
            return
        dd = protocol.new_job("inspect", input=self._final_xisf, params={"linear": False})
        protocol.submit(dd)
        met = (protocol.wait_result(dd["job_id"], timeout=300).get("metrics") or {})
        fw = int(met.get("width") or png_w)
        k = fw / png_w
        x, y, r = cx_png * k, cy_png * k, r_png * k
        self._dust_mode = False; self.btn_dust.setChecked(False); self.preview.setCursor(Qt.ArrowCursor)
        self._append(f"[灰尘修复] 圆心≈({x:.0f},{y:.0f}) 半径≈{r:.0f} → 人工平场(所有配色档)")
        self._run_op_on_final("flatpatch",
                              {"x": round(x, 1), "y": round(y, 1), "r": round(r, 1),
                               "mode": "gain", "linear": False},
                              tag="dust", label="灰尘修复", apply_all=True)

    def _score_current_pal(self):
        """功能C:让评委单独给当前配色档打分(按需,LLM 调用)。"""
        pal = self._cur_pal or "main"
        png = self._final_png
        if not (png and Path(png).exists()):
            return
        if not (config.get_setting("llm.provider") or "").strip():
            QMessageBox.information(self, t("评分"), t("未配置 LLM 评委,无法评分。")); return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._append(f"[评分] 正在评 {PAL_LABELS.get(pal, pal)} 档…")
            s = critic.score(png, context=f"SHO 成片(palette={pal})")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, t("评分"), t("评分失败:{}").format(e)); return
        finally:
            QApplication.restoreOverrideCursor()
        if s.get("error"):
            QMessageBox.information(self, t("评分"), t("评分不可用:{}").format(s['error'])); return
        self._pal_scores[pal] = s
        self.btn_scorepal.setVisible(False)
        self._show_scores({**s, "_pal_note": PAL_LABELS.get(pal, pal)})

    def _kick_llm_score(self, png=None, retries=0):
        """后台异步 LLM 主观评分(不阻塞;评完 _on_llm_score 合并)。png 缺省用当前成片。
        自动完成后 & 手动『重新评分』共用。retries=失败后自动重试次数(自动评分传 2,手动=0):
        自动评分紧接处理结束,系统/服务端还在收尾易瞬态报错,手动重评则秒回 → 用重试抹平。"""
        png = png or self._final_png
        self._score_retries = int(retries)          # 供 _on_llm_score 失败时决定是否自动重试
        self._score_png_cur = str(png) if png else ""
        if not (png and Path(str(png)).exists()):
            self._append("[评委] 没有可评分的成片。"); return
        if not (config.get_setting("llm.provider") or "").strip():
            self._append("[评委] 未配置 LLM(在『配置』里设),无法评分。"); return
        # 【卡住也要能救回来(用户 2026-09-22「评分出不来,点重新评分也没反应」)】
        #   原来只要线程还在跑就直接 return —— 一旦它卡住(拉参考图/后端慢/异常没冒出来),
        #   「重新评分」就**永远点不动**,界面停在"评分中…"没有任何逃生口。
        #   实测后端本身是好的(直调 17.9s 返回完整评分),所以卡的是线程这一侧。
        #   改成:超过死线就**弃掉旧线程另起一个**,并把已等多久说清楚(不是静默 return)。
        _SCORE_DEADLINE = 240.0
        th = getattr(self, "_score_thread", None)
        if th is not None:
            try:
                if th.isRunning():
                    _t0 = float(getattr(self, "_score_started", 0.0) or 0.0)
                    _el = (time.time() - _t0) if _t0 else 0.0
                    if _t0 and _el > _SCORE_DEADLINE:
                        self._append(f"[评委] 上一次评分已卡住 {_el:.0f}s(超过 {_SCORE_DEADLINE:.0f}s 死线)"
                                     f" → **弃掉它重新发起**(旧线程会自己结束,结果丢弃)")
                        try:
                            th.result.disconnect()       # 断开,免得它later返回把新结果覆盖
                        except Exception:
                            pass
                        self._score_thread = None
                    else:
                        self._append(f"[评委] 评分进行中(已等 {_el:.0f}s,{_SCORE_DEADLINE:.0f}s 后可强制重发),请稍候…")
                        return
            except RuntimeError:
                self._score_thread = None
        _q = (self._last_scores or {}).get("_quality") or {}
        from . import quality as _ql
        _ctx = f"{self.FLOWS[self.flow_idx][0]} 成片"
        # 评委上下文里的甜区也必须走同一真源(别复制常量 —— 复制的迟早变废值还继续误导评委)
        _rtc = (self._last_scores or {}).get("_ref_targets") or {}
        _clo, _chi, _cfrom = _ql.s_star_band(_rtc, verbose=True)
        if _q:
            _ctx += (f";确定性指标 S_star={_q.get('s_star')}(甜区{_clo}~{_chi},由{_cfrom};"
                     f"**在甜区内即星点饱和达标,总评别说饱和不足**)"
                     f" 背景中性S={_q.get('bg_s')}(应<0.12) 背景失衡={_q.get('bg_imbalance')}"
                     f" 背景亮度={_q.get('bg_level')} 偏色={_q.get('bg_cast')}")
            # 梯度校正量化判据(用户 2026-09-09):背景不匀度 → 评委据此判"梯度校平没有"(星云旁暗带/四角暗=残留梯度)
            if _q.get("bg_nonflat") is not None and _q.get("bg_flat_na"):
                _ctx += (" 天体铺满画面:背景平整度读到的是天体本身,不适用;背景已按最暗处去过,"
                         "**不要据此判残留梯度、也别建议更强的背景提取**(那会把主体当背景减掉)")
            elif _q.get("bg_nonflat") is not None and _q.get("bg_flat_src") == "sky":
                # 天体占了画面大头 → 全画面格子量的是天体本身(M33:格子 0.855,天空 0.031),已换成只量天空(quality.sky_flatness)
                _ctx += (f" 背景平整度(只量天体以外的真天空;天体铺满画面,全画面格子口径量到的是天体本身、已弃用)"
                         f"nonflat={_q.get('bg_nonflat')}(应<0.18)。**星系/星云外晕向外渐暗是天体本身的亮度廓线,不是残留梯度**"
                         + ("【★天空本身不匀:四角/边缘有残留梯度,请点出】" if _q.get("bg_uneven")
                            else ";天空已平,**别据此判梯度暗晕、也别建议 GraXpert/更强背景提取**(会把外晕当背景减掉)"))
            elif _q.get("bg_nonflat") is not None:
                _ctx += (f" 背景平整度nonflat={_q.get('bg_nonflat')}(应<0.18,越大越有残留梯度)"
                         + ("【★背景不匀:梯度校正未到位,星云周围一圈暗/四角暗,请在 core/background 评分与总评里点出】"
                            if _q.get("bg_uneven") else ""))
        # 目标名(拉 AstroBin 同视场参考用,dso.lookup 会自动剥项目名前缀)+ 波段(宽/窄带 filter 匹配)
        _tname = (self.ed_project.text() or "").strip() or (self._guess_target() or "")
        _kind = self._derive_kind() if hasattr(self, "_derive_kind") else "rgb"
        _band = "narrow" if _kind in ("hoo", "sho") else "broad"   # 宽带 RGB/LRGB 只比宽带作品、不比纯窄带
        # 连续评分锚点:上一版综合分 + 上一版图(仅换了图=编辑后重评时带图对比;同图重评只带分锚,防漂移)
        _prev_o = (self._last_scores or {}).get("overall")
        _prev_img = getattr(self, "_last_scored_png", None)
        if _prev_img and str(_prev_img) == str(png):
            _prev_img = None
        self._append("[评委] 后台评分中(不阻塞;评完自动补上)…")
        th = _ScoreThread(str(png), _ctx, self, target=_tname, band=_band,
                          prev_overall=_prev_o, prev_image=_prev_img)
        th.result.connect(self._on_llm_score)
        th.finished.connect(th.deleteLater)
        self._score_thread = th
        self._score_started = time.time()             # 死线用:卡住时据此判断能否弃旧起新
        th.start()
        # 到点还没回 → 把界面从"评分中…"里放出来,并说清楚能干什么(否则看着像死了)
        def _score_deadline_hit(_th=th):
            if getattr(self, "_score_thread", None) is not _th:
                return                                # 已经返回或已被弃掉
            self._append(f"[评委] 评分等了 {_SCORE_DEADLINE:.0f}s 还没回。"
                         f"成片和实测指标都不受影响;点『重新评分』可重发。")
            try:
                self.lbl_bigscore.setText(
                    f"<span style=\"font-size:13px;color:{self.theme['muted']}\">"
                    f"{t('评分超时,可重评')}</span>")
            except Exception:
                pass
            self._set_rescore_busy(False)             # 关键:放开按钮,别让用户点不动
        QTimer.singleShot(int(_SCORE_DEADLINE * 1000) + 500, _score_deadline_hit)
        self._set_rescore_busy(True)                 # 评分开始 → 按钮变「⏳ 正在评分…」禁用,给交互反馈

    def _set_rescore_busy(self, busy):
        """『重新评分』按钮忙碌态:评分中 → 变「⏳ 正在评分…」+ 禁用(防重复点),评完/失败 → 复原可点。
        用户 2026-09-10:点了没反馈 → 加状态变化。"""
        b = getattr(self, "btn_rescore", None)
        if b is None:
            return
        try:
            if busy:
                b.setEnabled(False); b.setText(t("⏳ 正在评分…"))
            else:
                b.setEnabled(True); b.setText(t("重新评分"))
        except RuntimeError:                         # 控件已析构(切页/关窗)→ 忽略
            pass

    def _rescore(self):
        """重新评分:手动再唤起一次 AI 评分(超时/想再评时用)。"""
        self._kick_llm_score()

    def _on_llm_score(self, s):
        """后台 LLM 评分返回 → 有分则合并刷新;失败则显示**真实原因**(超时/HTTP/后端 memo)+ 可重评。"""
        self._score_thread = None
        if not isinstance(s, dict) or s.get("error"):
            _err = s.get("error") if isinstance(s, dict) else None
            _left = int(getattr(self, "_score_retries", 0) or 0)
            if _left > 0:                            # 瞬态接口错误 → 自动重试(自动评分才有重试预算,手动=0)
                self._score_retries = _left - 1
                self._append(f"[评委] 评分接口错误({_err}),4s 后自动重试(剩 {_left} 次)…")
                _pg = getattr(self, "_score_png_cur", "") or self._final_png
                QTimer.singleShot(4000, lambda: self._kick_llm_score(_pg, retries=self._score_retries))
                if getattr(self, "btn_rescore", None) is not None:
                    self.btn_rescore.setVisible(True)
                return
            self._append(f"[评委] AI 评分未完成:{_err or '不可用'}"
                         f"(已有实测指标,不影响成片;可点『重新评分』重试)")
            if getattr(self, "btn_rescore", None) is not None:
                self.btn_rescore.setVisible(True)
            self._set_rescore_busy(False)            # 终态失败(无重试预算)→ 按钮复原可再点
            return
        merged = {**(self._last_scores or {}), **s}
        self._last_scores = merged
        self._last_scored_png = getattr(self, "_score_png_cur", "") or self._final_png   # 记本次评分的图 → 下次编辑后重评锚定它
        self._show_scores(merged)
        if getattr(self, "btn_rescore", None) is not None:
            self.btn_rescore.setVisible(True)
        self._set_rescore_busy(False)                # 评分成功返回 → 按钮复原「重新评分」可再点
        try:
            _n = int(s.get("_astrobin_refs") or 0)
            _ab = f"(对比了 AstroBin 同视场作品 {_n} 张)" if _n else "(无同视场参考 → 按固定标准评)"
            self._append(f"[评委] AI 评分 {float(s.get('overall', 0)):.1f}/10 {_ab}")
        except (TypeError, ValueError):
            pass

    def _sky_ref_cached(self):
        """AstroBin 同目标天空亮度中位 —— 只读本地缓存(ref_colors.sky_target 跑流程时写的),
        界面线程里绝不联网;没有缓存就返回 None。"""
        try:
            import json, re
            from . import ref_colors as _rc
            tgt = (self._guess_target() or self.ed_project.text() or "").strip()
            slug = re.sub(r"[^0-9A-Za-z_\-]+", "_", tgt)[:48]
            cp = _rc.CACHE_DIR / f"{slug}_sky.json"
            if slug and cp.exists():
                return float(json.loads(cp.read_text(encoding="utf-8"))["median"])
        except Exception:
            pass
        return None

    def _set_metric(self, key, val, tag, dot_color):
        """写一条实测指标:数值(测量蓝)+ 参考说明 + 状态签。
        状态按调用方给的颜色定:行动绿 = 达标、红 = 需处理、信息蓝 = 只供参考(不挂签)。"""
        if not hasattr(self, "metric_rows") or key not in self.metric_rows:
            return
        pill, vlab, rlab = self.metric_rows[key]
        vlab.setText(val); rlab.setText(tag); rlab.setVisible(bool(tag))
        p = self.theme
        if dot_color == p['accent']:
            pill.setText(t("达标")); pill.setObjectName("pillok"); pill.setVisible(True)
        elif dot_color in (p['danger'], p['warn']):
            pill.setText(t("需处理")); pill.setObjectName("pillbad"); pill.setVisible(True)
        else:
            pill.setVisible(False)
        pill.style().unpolish(pill); pill.style().polish(pill)

    def _show_scores(self, s):
        p = self.theme
        s = s or {}
        has_panels = hasattr(self, "score_panels")
        # ---- 成片评审 panel:LLM 大分 + 背景/星点色/核心 三条 green→blue 评分条 ----
        if has_panels:
            if "overall" in s:
                self.lbl_bigscore.setText(
                    f"{float(s['overall']):.1f}"
                    f"<span style=\"font-size:14px;color:{p['muted']}\">/10</span>")
                for key in ("background", "star_color", "core"):
                    pb, val = self.score_bars[key]
                    v = float(s.get(key, 0) or 0)
                    pb.setValue(max(0, min(100, int(round(v * 10))))); val.setText(f"{v:.1f}")
            else:
                self.lbl_bigscore.setText(f"<span style=\"font-size:15px;color:{p['muted']}\">{t('评分中…')}</span>")
                for key in ("background", "star_color", "core"):
                    pb, val = self.score_bars[key]; pb.setValue(0); val.setText("—")
            cm = s.get("comment")
            self.lbl_verdict_comment.setText(cm or ""); self.lbl_verdict_comment.setVisible(bool(cm))
        # ---- 实测指标 panel:确定性 numpy(星点饱和 / 背景中性 / 背景亮度)----
        q = s.get("_quality") or {}
        has_q = bool(q and not q.get("error"))
        if has_q:
            from . import quality as _q
            ss = float(q.get("s_star", 0)); bgs = float(q.get("bg_s", 0)); bgl = float(q.get("bg_level", 0))
            # 【真实底色不算偏色(用户 2026-09-04,M71)】背景中性度只适用于**平坦中性场**;真实暖调/带尘是讨喜底色不标红。
            _bg_flat = True
            if bgs > _q.BG_S_MAX and getattr(self, "_final_xisf", None):
                try:
                    from . import recombine as _rcb
                    _bg_flat = bool(_rcb.classify_bg(str(self._final_xisf)).get("flat_neutral"))
                except Exception:
                    _bg_flat = True
            _bg_defect = bgs > _q.BG_S_MAX and _bg_flat
            # 星点饱和的甜区**按目标取**:有同视场参考就用这个天体的,没有才用固定值。
            #   单一真源 = quality.s_star_band,别在这儿复制阈值([[pi-critic-scoring-bias]])。
            _rt = s.get("_ref_targets") or {}
            _slo, _shi, _sfrom = _q.s_star_band(_rt, verbose=True)
            if has_panels:
                self._set_metric("s_star", f"{ss:.2f}", f"{_sfrom}≥{_slo}",
                                 p['accent'] if ss >= _slo else p['danger'])
                self._set_metric("bg_s", f"{bgs:.2f}",
                                 "真实底色" if (bgs > _q.BG_S_MAX and not _bg_flat) else f"应<{_q.BG_S_MAX}",
                                 p['danger'] if _bg_defect else p['accent'])
                _skr = self._sky_ref_cached()
                self._set_metric("bg_level", f"{bgl:.3f}",
                                 t("AstroBin 同目标中位 {:.3f}").format(_skr) if _skr else t("仅供参考"),
                                 p['info'])
                # 背景平整度(梯度校正判据,用户 2026-09-09 M45):nonflat 越大越有残留梯度(星云旁暗带/四角暗)
                _nf = q.get("bg_nonflat")
                if _nf is not None and q.get("bg_flat_na"):
                    # 天体铺满画面:量到的「不平」是天体本身,不是残留梯度(管线已按最暗处去背景)
                    self._set_metric("bg_nonflat", f"{float(_nf):.2f}", t("铺满画面·不适用"), p['info'])
                elif _nf is not None and q.get("bg_flat_src") == "sky":
                    # 天体占了画面大头:只量天体以外的天空(quality.sky_flatness)
                    _uneven = bool(q.get("bg_uneven"))
                    self._set_metric("bg_nonflat", f"{float(_nf):.2f}",
                                     t("只量天空·有残留梯度") if _uneven else t("只量天空·平整 <0.18"),
                                     p['danger'] if _uneven else p['accent'])
                elif _nf is not None:
                    _uneven = bool(q.get("bg_uneven"))
                    self._set_metric("bg_nonflat", f"{float(_nf):.2f}",
                                     "有残留梯度" if _uneven else "平整 <0.18",
                                     p['danger'] if _uneven else p['accent'])
            if getattr(self, "btn_scorefix", None) is not None:
                self.btn_scorefix.setVisible(ss < _slo or _bg_defect)
        elif getattr(self, "btn_scorefix", None) is not None:
            self.btn_scorefix.setVisible(False)
        if has_panels:
            self.score_panels.setVisible(("overall" in s) or has_q)
        # ---- 结构化点评:已自动修正(chips)+ 需你决定(退回哪一步)----
        cr = s.get("_critic") or {}
        af = cr.get("auto_fixed") or []
        na = cr.get("needs_attention") or []
        parts = []
        if af:
            chips = "　".join(f"<span style='color:{p['accent']}'>✓ {a['issue']}</span>" for a in af)
            parts.append(f"<span style='color:{p['muted']};font-size:11px'>已自动修正:</span> "
                         f"<span style='font-size:11px'>{chips}</span>")
        if not (("overall" in s) or has_q or af):
            parts.append(f"<span style='color:{p['muted']}'>(未启用 LLM 评委或评分不可用)</span>")
        self.lbl_scores.setText("<br>".join(parts)); self.lbl_scores.setVisible(bool(parts))
        # 「需你决定」逐条渲染成可操作行(功能B:成片能无损修的加「应用」按钮)
        self._clear_remedy_rows()
        if na:
            hdr = QLabel(t("需你决定:")); hdr.setObjectName("sub")
            self.remedy_box.addWidget(hdr); self._remedy_rows.append(hdr)
            for d in na:
                self._add_remedy_row(d)

    # 问题 → 成片可无损修的 op(功能B「应用」按钮用;仅 in_place 项才有)
    _REMEDY_OP = {
        "over_saturation": ("curves", {"saturation": -0.15, "linear": False}, "降饱和"),
        "noise":           ("denoise", {"denoise": 0.4, "detail": 0.2, "linear": False}, "降噪"),
    }

    def _clear_remedy_rows(self):
        for w in getattr(self, "_remedy_rows", []):
            w.setParent(None); w.deleteLater()
        self._remedy_rows = []

    def _add_remedy_row(self, d):
        p = self.theme
        row = QWidget(); row.setObjectName("rowbg")
        h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
        where = "成片可修" if d["in_place"] else f"退回【{STAGE_CN.get(d['stage'], d['stage'])}】"
        knob = f"(调 {d['knob']})" if d.get("knob") else ""
        lab = QLabel(f"<span style='color:{p['sec']}'>{d['issue']}</span> → "
                     f"<span style='color:{'#8fd39f' if d['in_place'] else '#ff9d5c'}'>{where}</span> "
                     f"<span style='color:{p['muted']};font-size:11px'>{d['how']}{knob}</span>")
        lab.setWordWrap(True)
        h.addWidget(lab, 1)
        op = self._REMEDY_OP.get(d["issue"])
        if d["in_place"] and op:
            btn = QPushButton(f"应用·{op[2]}"); btn.setObjectName("seg")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c, dd=d, o=op: self._apply_remedy(dd, o))
            h.addWidget(btn, 0)
        elif d["issue"] == "color_cast" and len(self._finals) > 1:
            btn = QPushButton(t("换配色")); btn.setObjectName("seg")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(t("偏色多是配色取向问题 → 用预览下方的配色切换条挑别的档"))
            btn.clicked.connect(lambda: self._append("[提示] 用预览下方的配色切换条对比 自然色 / 洋红加蓝 / 经典哈勃"))
            h.addWidget(btn, 0)
        self.remedy_box.addWidget(row); self._remedy_rows.append(row)

    def _apply_remedy(self, d, op):
        """功能B:对当前成片应用一个无损补救 op(降饱和/降噪),重渲染。"""
        opname, params, label = op
        if self._run_op_on_final(opname, params, tag=f"rem_{d['issue']}", label=f"应用·{label}"):
            self._append(f"[补救] {d['issue']} → 已在成片上{label}(其余档未动;如要一致请逐档切换后再应用)")

    def _apply_score_remedy(self):
        """按评分优化:按确定性指标一键补救(纯 numpy,不需 runner、秒出)——背景偏色→中和;
        星点发闷→星蒙版提饱和。只动该动的、不重跑管线,存为新成片、重测指标刷新显示。"""
        xis = self._final_xisf
        if not (xis and Path(str(xis)).exists()):
            QMessageBox.information(self, t("按评分优化"), t("没有可处理的成片。")); return
        try:
            from . import quality, recombine as _recomb
        except Exception as e:
            QMessageBox.critical(self, t("按评分优化"), t("依赖缺失:{}").format(e)); return
        m = quality.measure(str(xis))
        if m.get("error"):
            QMessageBox.information(self, t("按评分优化"), t("读不了成片:{}").format(m['error'])); return
        do_bg = m.get("bg_s", 0) > quality.BG_S_MAX
        do_star = 0 < m.get("s_star", 0) < quality.S_STAR_LO
        # 【真实底色不中和(用户 2026-09-04,M71)】"背景应中性"这条标准**只适用于平坦中性场**(如 M54);
        #   M71 暖金密集星场、M28 带尘场的高 bg_s 是**真实讨喜底色**,不是偏色 → 中和会把暖调减掉变冷(用户
        #   更喜欢管线原图)。用 classify_bg:非 flat_neutral(有结构/真色)→ 跳过背景中和,只保留星点补救。
        if do_bg:
            try:
                if not _recomb.classify_bg(str(xis)).get("flat_neutral"):
                    do_bg = False
                    self._append("[按评分优化] 背景为真实底色(有结构/暖调,非平坦中性场)→ 跳过背景中和,保留讨喜色调")
            except Exception:
                pass
        if not (do_bg or do_star):
            QMessageBox.information(self, t("按评分优化"), t("确定性指标已达标(或背景为真实底色不宜中和),无需优化。"))
            self.btn_scorefix.setVisible(False); return
        # 存优化前快照(供 撤销 / 前后对比)
        self._pre_remedy = {"xisf": str(xis), "png": self._final_png,
                            "scores": dict(self._last_scores or {})}
        QApplication.setOverrideCursor(Qt.WaitCursor)
        applied = []
        try:
            base = str(config.RUN_DIR / "scorefix").replace("\\", "/")
            cur = str(xis)
            if do_bg:
                o = base + "_bg.xisf"
                _recomb.neutralize_background(cur, o, preview_path=base + "_bg.png")
                cur = o; applied.append("背景中和")
            if do_star:
                o = base + "_star.xisf"
                _recomb.boost_star_saturation(cur, o, amount=1.5, preview_path=base + "_star.png")
                cur = o; applied.append("提星饱和")
            self._final_xisf = cur
            _png = cur.rsplit(".", 1)[0] + ".png"
            if Path(_png).exists():
                self._final_png = _png
            m2 = quality.measure(cur)
            if ((self._last_scores or {}).get("_quality") or {}).get("bg_flat_na"):
                m2["bg_flat_na"] = self._last_scores["_quality"]["bg_flat_na"]   # 铺满画面的判定随图走,重测不丢
            self._last_scores = {**(self._last_scores or {}), "_quality": m2}
            self._show_scores(self._last_scores)     # 刷新指标 + 按钮显隐(达标则自动隐去)
            if self._final_png and Path(self._final_png).exists():
                pm = QPixmap(self._final_png)
                if not pm.isNull():
                    self._set_preview_pixmap(pm)
            self._append(f"[按评分优化] 已应用:{'、'.join(applied)} → {cur};"
                         f"重测 s_star={m2.get('s_star')} 背景中性={m2.get('bg_s')}(满意后可再『导出成片』)")
            # 亮出 撤销 / 前后对比
            self.btn_remedy_undo.setVisible(True)
            self.btn_remedy_cmp.setChecked(False); self.btn_remedy_cmp.setText(t("⇄ 对比原图"))
            self.btn_remedy_cmp.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, t("按评分优化"), t("失败:{}").format(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _undo_remedy(self):
        """↩ 撤销「按评分优化」,恢复优化前的成片 + 指标 + 预览。"""
        pr = getattr(self, "_pre_remedy", None)
        if not pr:
            return
        self._final_xisf = pr["xisf"]
        self._final_png = pr["png"]
        self._last_scores = pr.get("scores") or self._last_scores
        self._pre_remedy = None
        self.btn_remedy_undo.setVisible(False)
        self.btn_remedy_cmp.setVisible(False); self.btn_remedy_cmp.setChecked(False)
        self._show_scores(self._last_scores)          # 恢复指标(会按原指标重新决定 btn_scorefix 显隐)
        if self._final_png and Path(str(self._final_png)).exists():
            pm = QPixmap(str(self._final_png))
            if not pm.isNull():
                self._set_preview_pixmap(pm)
        self._append("[撤销优化] 已恢复优化前的成片")

    def _toggle_remedy_compare(self):
        """⇄ 在 优化前 / 优化后 之间切换预览。"""
        pr = getattr(self, "_pre_remedy", None)
        if not pr:
            self.btn_remedy_cmp.setChecked(False); return
        show_before = self.btn_remedy_cmp.isChecked()
        png = pr["png"] if show_before else self._final_png
        self.btn_remedy_cmp.setText("⇄ 看优化后" if show_before else "⇄ 对比原图")
        if png and Path(str(png)).exists():
            pm = QPixmap(str(png))
            if not pm.isNull():
                self._set_preview_pixmap(pm)
        self._append(f"[对比] 预览:{'优化前' if show_before else '优化后'}")

    # ---------- 向 AI 提需求驱动修改(自然语言 → agent_edit → 执行) ----------
    def _norm_agent_op(self, op, params):
        """把 agent 返回的 op/params 归一到 runner 可执行形式(成片是非线性 → linear=False),
        并按 AGENT_OPS 白名单校验。未知/缺参返回 (None, 原因)。复刻 Worker 内 _norm 的成片版。"""
        from . import critic
        p = dict(params or {}); p["linear"] = False
        if op == "gradient":
            return "gradient", {"method": "GradientCorrection", "linear": False}
        if op == "restretch":                        # 退回·改拉伸力度从头重跑(不经 _run_op_on_final,单独处理)
            _o = {}
            _d = str(p.get("direction", "") or "").lower()
            if any(k in _d for k in ("weak", "弱", "小", "轻", "down")):
                _o["direction"] = "weaker"
            elif any(k in _d for k in ("strong", "强", "大", "up")):
                _o["direction"] = "stronger"
            if p.get("ghs_d") is not None:
                try:
                    _o["ghs_d"] = max(0.0, min(2.5, float(p["ghs_d"])))
                except (TypeError, ValueError):
                    pass
            return "restretch", _o
        if op == "depurple":
            # 去星点紫/品红·**严谨版**:对成片 SXT 重新分离星点 → 只对星点层去紫(反相→SCNR→反相)→ screen 合回,
            # 星云/星系(去星底图)完全不被碰(用户 2026-09-09:有星云/星系时全局去紫影响极大)。走专门分支执行。
            try:
                _am = float(p.get("amount", 0.7))
            except (TypeError, ValueError):
                _am = 0.7
            return "depurple_stars", {"amount": max(0.0, min(1.0, _am))}
        if op == "polybg":
            try:
                _dg = int(round(float(p.get("degree", 2))))
            except (TypeError, ValueError):
                _dg = 2
            return "polybg", {"degree": max(1, min(3, _dg)), "linear": False}
        if op == "graxpert_bge":
            from . import graxpert
            if not graxpert.available():
                return None, "未检测到 GraXpert(在『配置』里填 graxpert_path 指向 GraXpert.exe)"
            try:
                _sm = float(p.get("smoothing", 0.2))
            except (TypeError, ValueError):
                _sm = 0.2
            return "graxpert_bge", {"smoothing": max(0.0, min(1.0, _sm))}
        if op == "saturation_down":
            return "curves", {"saturation": -abs(float(p.get("amount", 0.15))), "linear": False}
        if op == "flatpatch":
            if not all(k in p for k in ("x", "y", "r")):
                return None, "需先用『灰尘修复』点选圆圈(缺坐标)"
            p.setdefault("mode", "gain"); return "flatpatch", p
        if op == "crop":
            # AI 给逐边裁切比例(0~0.3)→ runner 的 marginsFrac(按比例转像素,见 job-runner cropToNewWindow)
            _mf = {}
            for _e in ("left", "right", "top", "bottom"):
                try:
                    _v = float(p.get(_e, 0) or 0)
                except (TypeError, ValueError):
                    _v = 0.0
                if _v > 0:
                    _mf[_e] = max(0.0, min(0.3, _v))
            if not _mf:
                return None, "裁切需指定至少一边的比例(left/right/top/bottom,0~0.3)"
            return "crop", {"marginsFrac": _mf, "linear": False}
        if op in critic.AGENT_OPS:
            return op, p
        return None, f"不支持的操作 {op}"

    def _ai_edit_send(self):
        """用户用自然语言说想怎么改 → 后台 agent_edit 解释 → _on_ai_edit 执行。"""
        msg = self.ed_ai_edit.text().strip()
        if not msg:
            return
        if not (self._final_xisf and Path(str(self._final_xisf)).exists()):
            QMessageBox.information(self, t("AI 修改"), t("还没有成片可改。")); return
        if not (config.get_setting("llm.provider") or "").strip():
            QMessageBox.information(self, t("AI 修改"), t("未配置 LLM(在『配置』里设),无法用自然语言驱动修改。")); return
        th = getattr(self, "_aiedit_thread", None)
        if th is not None:
            try:
                if th.isRunning():
                    self._append("[AI 修改] 上一条还在处理,请稍候…"); return
            except RuntimeError:
                self._aiedit_thread = None
        # 【回车后立刻上屏(用户 2026-09-24:"响应必须及时,哪怕真实的数据交互发生在操作之后")】
        #   清框和回显本来就写在最前面,但紧接着**同步**跑了 quality.measure(全分辨率成片) ——
        #   那要几秒,Qt 在这期间根本没机会重绘,用户看到的就是"字还在框里、什么都没发生"。
        #   → 回显走 _set_ai_reply(它末尾有 processEvents 立即重绘),把这一帧先画出去,再做阻塞的事。
        self.ed_ai_edit.clear()
        self._append(f"[你 → AI] {msg}")
        self._append("[AI 修改] 思考中(不阻塞界面)…")
        self._set_ai_reply(t("你") + f": {msg}　·　" + t("AI 思考中…"), "busy")
        try:
            from . import quality
            m = quality.measure(str(self._final_xisf))
        except Exception:
            m = None
        self._aiedit_pending = msg
        th = _AgentEditThread(str(self._final_png or self._final_xisf), m,
                              getattr(self, "_aiedit_history", []), msg, self)
        th.result.connect(self._on_ai_edit)
        th.finished.connect(th.deleteLater)
        self._aiedit_thread = th
        th.start()

    def _set_ai_reply(self, text, state="normal"):
        """审阅面板 AI 回复条:就地显示 + 按状态上色(用户 2026-09-06:改完要有明确反馈)。
        state: normal(灰)/ busy(进行中,accent)/ done(完成,accent 加粗)/ error(danger)。
        done/error 额外**闪烁任务栏**(QApplication.alert)——用户可能切走了别的窗口,给个提醒。"""
        if not hasattr(self, "lbl_ai_reply"):
            return
        p = self.theme
        _col = {"busy": p['accent'], "done": p['accent'], "error": p['danger']}.get(state, p['text2'])
        _wt = "bold" if state in ("done", "error") else "normal"
        self.lbl_ai_reply.setStyleSheet(f"color:{_col}; font-weight:{_wt};")
        self.lbl_ai_reply.setText(text)
        self.lbl_ai_reply.setVisible(True)
        if state in ("done", "error"):
            try:
                QApplication.alert(self)          # 任务栏闪烁(切走了也能看到"改完了")
            except Exception:
                pass
        QApplication.processEvents()              # 立即重绘(尤其 busy→阻塞执行前先让文字露出来)

    def _do_restretch(self, params, reply):
        """退回·改拉伸力度从头重跑(用户 2026-09-09:成片拉伸不满意、要退回拉伸阶段重来,而成片上 curves 硬压救不回)。
        按 direction/ghs_d 调 GHS 拉伸力度 sp_ghs → 触发 _run() 用**整条流程**重跑(复用 run_rgb 全部正确逻辑;
        母版输入约几分钟,原始素材更久)。比起交互 op,这是唯一能真正"重新拉伸"的路子(线性数据在 _run 里重取)。"""
        if getattr(self, "thread", None) is not None:
            self._set_ai_reply(t("AI: 正在处理中,请等这次跑完再重新拉伸。"), state="busy"); return
        try:
            cur = float(self.sp_ghs.value())
        except Exception:
            cur = 0.5
        if params.get("ghs_d") is not None:
            newd = float(params["ghs_d"])
        elif params.get("direction") == "weaker":
            newd = max(0.05, round(cur * 0.55, 3))     # 背景太亮/太花 → 减弱
        elif params.get("direction") == "stronger":
            newd = min(2.5, round(cur * 1.5, 3))       # 太暗 → 加强
        else:
            newd = cur
        newd = round(max(0.0, min(2.5, newd)), 3)
        self.sp_ghs.setValue(newd)
        _m = f"GHS 拉伸力度 {cur} → {newd}"
        self._append(f"[重新拉伸] {_m},用新力度从头重跑整条流程(不是在成片上硬改;母版约几分钟)…")
        self._set_ai_reply("AI: " + (reply or "") + f"　·　已把{_m},正在用新拉伸力度重新处理…", state="busy")
        QApplication.processEvents()
        self._run()

    def _on_ai_edit(self, res):
        """agent_edit 返回 → 显示回复;有 op 则(存快照后)在成片上执行、刷新指标 + 撤销/对比。"""
        self._aiedit_thread = None
        if not isinstance(res, dict) or res.get("error"):
            _err = (res or {}).get('error', '未知')
            self._append(f"[AI 修改] 出错:{_err}")
            self._set_ai_reply(t("AI 修改出错:") + str(_err), state="error")
            return
        reply = res.get("reply") or ""
        if reply:
            self._append(f"[AI] {reply}")
        hist = getattr(self, "_aiedit_history", [])
        hist.append(("用户", getattr(self, "_aiedit_pending", ""))); hist.append(("助手", reply))
        self._aiedit_history = hist[-16:]
        op, params = res.get("op"), res.get("params") or {}
        _u = res.get("usage") or {}
        if res.get("model_note"):                    # 首选模型没调动、自动换了备用
            self._append("[AI 修改] " + res["model_note"])
        if _u.get("total"):
            self._append(f"[AI 修改] 本次 {_u['total']} tokens" + (f"(含推理 {_u['reasoning']})" if _u.get("reasoning") else ""))
        if not op:
            self._set_ai_reply("AI: " + (reply or t("(收到,无需改图)")), state="done")
            return                                  # 纯文字回复 / 追问,不改图
        nop, nparams = self._norm_agent_op(op, params)
        if not nop:
            self._append(f"[AI 修改] 未执行:{nparams}")
            self._set_ai_reply("AI: " + (reply or "") + f"　✗ {nparams}", state="error"); return
        if nop == "restretch":                       # 退回·改拉伸力度从头重跑(不是成片上的单步 op)
            self._do_restretch(nparams, reply)
            return
        # 执行前先亮"正在应用…"(_run_op_on_final 同步阻塞 GUI,先把这句刷出来,用户知道在跑)
        self._set_ai_reply("AI: " + (reply or t("(已按需求调整成片)")) + "　·　" + t("正在应用调整…"),
                           state="busy")
        # 存优化前快照(撤销/对比复用)→ 在成片上执行(PI op,经 runner;不在线会自动拉起 PI)
        self._pre_remedy = {"xisf": self._final_xisf, "png": self._final_png,
                            "scores": dict(self._last_scores or {})}
        if self._run_op_on_final(nop, nparams, tag=f"aiedit_{op}", label=f"AI·{op}"):
            try:
                from . import quality
                m2 = quality.measure(str(self._final_xisf))
                if ((self._last_scores or {}).get("_quality") or {}).get("bg_flat_na"):
                    m2["bg_flat_na"] = self._last_scores["_quality"]["bg_flat_na"]   # 铺满画面的判定随图走
                self._last_scores = {**(self._last_scores or {}), "_quality": m2}
                self._show_scores(self._last_scores)
            except Exception:
                pass
            self.btn_remedy_undo.setVisible(True)
            self.btn_remedy_cmp.setChecked(False); self.btn_remedy_cmp.setText(t("⇄ 对比原图"))
            self.btn_remedy_cmp.setVisible(True)
            self._append(f"[AI 修改] ✓ 已执行 {op} → 满意可『导出成片』,不满意点『↩ 撤销』")
            self._set_ai_reply("AI: " + (reply or t("(已按需求调整成片)"))
                               + "　✓ " + t("已调整完成 · 可『对比原图』/『撤销』/『导出成片』"), state="done")
        else:
            self._set_ai_reply("AI: " + (reply or "") + "　✗ " + t("调整未执行(见日志)"), state="error")

    def _show_in_folder(self):
        p = self._final_xisf or self._final_png
        if not p or not Path(p).exists():
            return
        p = str(Path(p))
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", p])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", p])
        else:
            subprocess.Popen(["xdg-open", str(Path(p).parent)])

    def _suggest_export_name(self):
        """从输入项目文件夹名推导导出基名:天体_日期_设备(重排 + 清洗 + 限长),
        便于保存多张时区分。用户约定夹名如 `260712_D3_M23`(日期_设备_天体)→ `M23_260712_D3`。
        识别不出就退回夹名本身;再不行退回固定名。只做默认建议,用户仍可在对话框改。"""
        import re
        # **最优先:顶栏项目名 ed_project**(用户明确设的名字,如 M11)——用户 2026-09-07:导出文件名必须跟当前
        #   项目名一致,不能再从输入母版路径推(母版是别的目标叠出来的,如 M8 的 master 会推成 M8,与项目 M11 不符)。
        #   其次 ed_target(原始叠加的项目目录,如 260712_D3_M28),再退回从 ed_input 路径推。
        folder = ""
        for _src in ("ed_project", "ed_target"):
            try:
                folder = (getattr(self, _src).text() or "").strip()
            except Exception:
                folder = ""
            if folder and folder not in ("未命名项目", "TTAstroPiLot_final"):
                break
            folder = ""
        if not folder:                                   # 都没填 → 从输入路径推(母版/registered 模式)
            inp = (self.ed_input.text() or "").replace("\\", "/").strip()
            if inp:
                parts = [x for x in inp.split("/") if x and ":" not in x]
                skip = {"master", "registered", "lights", "light", "flat", "flats", "dark", "darks",
                        "bias", "output", "out", "deepsky", "astro", "data"}
                cand = [x for x in parts[:-1] if x.lower() not in skip]   # 排除文件名 + 通用子夹
                folder = cand[-1] if cand else (parts[-2] if len(parts) >= 2 else "")
        if not folder:
            return "TTAstroPiLot_final"
        # 先从整个夹名抓**日期**(ISO 2026-07-12 优先,其次紧凑 8/6 位)再摘掉 —— 否则 ISO 的 '-' 会被当分隔符拆坏
        date = ""
        m = re.search(r"(\d{4}-\d{1,2}-\d{1,2}|\d{8}|\d{6})", folder)
        if m:
            date = m.group(1)
            folder = folder.replace(date, " ")
        # 剩下的 token 里认 天体(目录编号)+ 设备(剩下第一个)
        _OBJ = r"^(?:M|NGC|IC|SH2|Sh2|B|Barnard|LDN|LBN|vdB|C|Cr|Mel|Tr|Stock|Abell|Pal|UGC|PGC|Arp|Ced|Gum|Sadr)\d"
        obj = dev = ""
        rest = []
        for t in re.split(r"[_\-\s]+", folder):
            if not t:
                continue
            if not obj and re.match(_OBJ, t, re.I):
                obj = t
            else:
                rest.append(t)
        dev = rest[0] if rest else ""
        ordered = [p for p in (obj, date, dev) if p]
        name = "_".join(ordered) if ordered else folder
        name = re.sub(r"[^0-9A-Za-z_\.\-]", "", name)[:48].strip("_-.")
        return name or "TTAstroPiLot_final"

    _OBJ_DESIG = (r"(?:M|NGC|IC|SH2|Sh2|B|Barnard|LDN|LBN|vdB|C|Cr|Mel|Tr|Stock|Abell|Pal|UGC|PGC|Arp|Ced|Gum|Sadr)"
                  r"\s?\d{1,4}[A-Za-z]?")

    def _desig_of(self, text):
        """从一段文本(夹名/项目名)里摘出天体编号,如 M78 / NGC2071;摘不出返回 ""。"""
        import re
        m = re.search(self._OBJ_DESIG, str(text or ""), re.I)
        return re.sub(r"\s+", "", m.group(0)).upper() if m else ""

    def _cur_project_dir(self):
        """当前目标的**项目目录名**(权威来源=输入路径,不是可能陈旧的 ed_target)。
        母版模式取母版文件所在目录名、对齐子帧模式取 registered 的上级目录名、原始模式取 ed_target。"""
        from pathlib import Path as _P
        try:
            if self._input_mode == 0:
                ms = [m["file"] for m in (self._master_config() or []) if _is_bb(m.get("filter"))]                      or [m["file"] for m in (self._master_config() or [])]
                if ms:
                    d = _P(ms[0]).parent
                    # WBPP 把母版放在 <项目>/master/ 下 → 项目名取上一级(否则项目名成了 "master")
                    if d.name.lower() in ("master", "masters") and d.parent.name:
                        d = d.parent
                    return d.name
            elif self._input_mode == 1:
                rs = [r["dir"] for r in (self._reg_config() or [])]
                if rs:
                    d = _P(rs[0])
                    # registered/<按晚分的子夹> 或 registered 本身 → 往上找到项目目录
                    for _ in range(3):
                        if d.name.lower() in ("registered", "master", "calibrated", "debayered", "lights", "light"):
                            d = d.parent
                        elif d.parent.name.lower() == "registered":
                            d = d.parent.parent
                        else:
                            break
                    return d.name
        except Exception:
            pass
        return (self.ed_target.text() or "").strip()

    def _export_dir_checked(self, expdir):
        """【导出目录属于另一个目标就纠正(2026-09-18 M78)】`ed_exportdir` 既是全局设置、又被逐项目
        保存进 .ttproj → **新建项目会继承上一个目标的专属文件夹**,而 `_export` 是直接拿它存、不弹窗的
        (用户 2026-09-03 要的)。实测 M78 工程里这个字段还指着 `.../250827-250914_D3_M74`,
        成品会静默落进 M74 的文件夹。属于 [[pi-gui-stale-target-state]] 那条铁律的同一类。

        判法:比对**导出目录夹名里的天体编号**与**当前项目**的编号;不一致才动手,一致/摘不出就原样放过
        (别打扰正常用法)。纠正优先用输入路径里的项目目录名(权威),同级建出对应文件夹;
        推不出来就清空 → 落回原有的弹窗选择,绝不闷着存错地方。"""
        from pathlib import Path as _P
        d = (expdir or "").strip().replace("\\", "/")
        if not d:
            return d
        want = self._desig_of(self._guess_target()) or self._desig_of(self._cur_project_dir())
        have = self._desig_of(_P(d).name)
        if not (want and have) or want == have:
            return d                                  # 摘不出或本来就对 → 不动
        proj = self._cur_project_dir()
        if proj and self._desig_of(proj) == want:
            nd = str(_P(d).parent / proj).replace("\\", "/")
            self._append(f"[导出] 目录 {_P(d).name} 属于 {have},当前项目是 {want} → 改存 {nd}")
            self.ed_exportdir.setText(nd); self._save_export_dir()
            return nd
        self._append(f"[导出] 目录 {_P(d).name} 属于 {have},当前项目是 {want} → 不确定该存哪,改为弹窗选择")
        return ""

    def _save_export_dir(self):
        """持久化「导出目录」字段到 settings(下次启动仍在)。"""
        d = (self.ed_exportdir.text() or "").strip().replace("\\", "/")
        try:
            _s = config.load_settings(); _s["export_dir"] = d; config.save_settings(_s)
        except Exception:
            pass

    def _export(self):
        if getattr(self, "_exporting", False):     # 防重入:导出中会泵事件循环,别让用户又点一次导出
            return
        src = self._final_xisf or self._final_png
        if not src or not Path(src).exists():
            QMessageBox.information(self, t("导出"), t("没有可导出的成片。"))
            return
        fmts = [f for f, c in (("xisf", self.chk_xisf), ("png", self.chk_png), ("jpg", self.chk_jpg)) if c.isChecked()]
        if not fmts:
            QMessageBox.information(self, t("导出"), t("请至少勾选一种导出格式。"))
            return
        # PNG/JPG/星云/星点/标注 都需经 PixInsight → 需 runner 在线 + 成片 XISF
        _extra = (self.chk_starless.isChecked() or self.chk_export_stars.isChecked() or self.chk_annotate.isChecked())
        need_runner = ("png" in fmts or "jpg" in fmts or _extra)
        have_xisf = bool(self._final_xisf and Path(self._final_xisf).exists())
        if need_runner and not have_xisf:
            QMessageBox.warning(self, t("无法导出"), t("缺少成片 XISF,无法生成 PNG/JPG/星云星点/标注。"))
            return
        # 导出目录已填 → **直接存那**(文件名用项目名),不弹窗;否则弹窗选、选完回填记住(用户 2026-09-03)
        _expdir = (self.ed_exportdir.text() or "").strip().replace("\\", "/")
        # 【兜底(用户 2026-09-06)】字段可能被旧工程恢复清空(见 _apply_project_state)→ 回读全局 settings
        #   的 export_dir 再试,拿到就回填字段,保证"设过一次就不再弹窗"。
        if not _expdir:
            _expdir = (config.get_setting("export_dir", "") or "").strip().replace("\\", "/")
            if _expdir:
                self.ed_exportdir.setText(_expdir)
        # 【导出目录归属校验(2026-09-18 M78)】这个字段既是全局设置、又被逐项目存进 .ttproj,
        #   新建项目会继承上一个目标的专属文件夹 → 而这里是**直接存、不弹窗**的,
        #   成片会静默落进别的目标的文件夹(实测 M78 工程里它还指着 .../250827-250914_D3_M74)。
        _expdir = self._export_dir_checked(_expdir)
        # 【目录不存在就建(用户 2026-09-16)】导出目录多是按目标新拟的路径(如 .../260710_D3_M68),
        #   跑到最后一步才发现没建好、被迫重选一次很麻烦。建不出来(盘不在/没权限)才退回弹窗。
        if _expdir and not os.path.isdir(_expdir):
            try:
                os.makedirs(_expdir, exist_ok=True)
                self._append("[导出] 导出目录不存在,已新建:%s" % _expdir)
            except OSError as e:
                self._append("[导出] 导出目录建不出来(%s),改为弹窗选:%s" % (e, _expdir))
        if _expdir and os.path.isdir(_expdir):
            dst = "%s/%s" % (_expdir.rstrip("/"), self._suggest_export_name())
            self._append("[导出] → 导出目录 %s(文件名 %s)" % (_expdir, self._suggest_export_name()))
        else:
            # 弹窗时把默认路径**锚定到已知目录**(settings 里最近一次导出目录,失效则用户主目录),
            #   别传裸文件名——那会让对话框落在进程 CWD(如 E:/AutoClick/pipeline,用户 2026-09-06 截图)。
            _anchor = _expdir if (_expdir and os.path.isdir(_expdir)) else str(Path.home()).replace("\\", "/")
            dst, _ = QFileDialog.getSaveFileName(self, t("导出成片(选择基名,自动加各格式后缀)"),
                                                 "%s/%s" % (_anchor.rstrip("/"), self._suggest_export_name()),
                                                 t("成片 (*.xisf *.png *.jpg)"))
            if not dst:
                return
            self.ed_exportdir.setText(str(Path(dst).parent).replace("\\", "/"))   # 回填并记住,下次免选
            self._save_export_dir()
        # PNG/JPG 要经 PixInsight 全分辨率重导 → runner 不在线就**自动冷启动 PI**并等就绪,不再让用户手动启动
        if need_runner and not self._ensure_runner("导出成片"):
            return
        # 【导出加时间戳,不再覆盖上一次(用户 2026-09-22)】同一次导出的所有产物
        #   (xisf/jpg/png、去星层、星点层、标注 txt)**共用同一个戳** —— 它们是一组,
        #   分开打戳会让同一次的产物对不上。格式 月日-时分,既短又能按名字排序。
        #   不想要就把 export_timestamp 设成 false。
        base = str(Path(dst).with_suffix("")).replace("\\", "/")
        if config.get_setting("export_timestamp", True):
            from datetime import datetime as _dt
            base = "%s_%s" % (base, _dt.now().strftime("%m%d-%H%M"))
        written = []
        import shutil
        _pump = QApplication.processEvents          # 每轮轮询泵一次事件循环,避免长任务把窗口卡成"未响应"
        self._exporting = True
        try:
            self.btn_export.setEnabled(False)
        except Exception:
            pass
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            for f in fmts:
                outp = f"{base}.{f}"
                if f == "xisf":
                    shutil.copy2(self._final_xisf, outp)
                elif f == "jpg":
                    # 【JPG 必须自己编码,不能交给 PI(2026-09-19)】PI 的 JPEG 写出固定 4:2:0,
                    #   色度按 2×2 块平均 → 星点才几像素宽,整颗星的色度被摊掉。四张成品实测
                    #   s_star 掉 27~41%(M80 -40.6%),而星系/星云大结构几乎无损 ——
                    #   正是「大结构没问题偏偏星点脏」的来源。见 recombine.write_jpeg 的实测记录。
                    from . import recombine as _rcj
                    _rcj.write_jpeg(self._final_xisf, outp, quality=self.sl_jpgq.value())
                    written.append(outp)
                    continue
                else:
                    job = protocol.new_job("inspect", input=self._final_xisf, params={},
                                           outputs={"image": outp})
                    protocol.submit(job)
                    r = protocol.wait_result(job["job_id"], timeout=300, on_poll=_pump)
                    if r.get("status") != "ok":
                        raise RuntimeError(f"{f.upper()} 导出失败:{r.get('error')}")
                written.append(outp)
            # ── 3D 建模备料:去星星云(JPG)/ 纯星点(PNG)/ 天体标注(TXT)──
            if self.chk_starless.isChecked() or self.chk_export_stars.isChecked():
                self._append("[导出] 星点分离(StarXTerminator)中…")
                _sl = str(config.RUN_DIR / "export_starless.xisf").replace("\\", "/")
                _st = str(config.RUN_DIR / "export_stars.xisf").replace("\\", "/")
                job = protocol.new_job("starsep", input=self._final_xisf,
                                       outputs={"image": _sl, "preview": _sl[:-5] + ".png", "stars": _st})
                protocol.submit(job)
                r = protocol.wait_result(job["job_id"], timeout=1800, on_poll=_pump)
                if r.get("status") != "ok":
                    raise RuntimeError(f"星点分离失败:{r.get('error')}")
                _sl = r.get("image") or _sl
                _st = r.get("stars") or _st
                if self.chk_starless.isChecked():          # 去星星云 → JPG(3D 星云底)
                    o = f"{base}_starless.jpg"
                    from . import recombine as _rcj2      # 同样走 4:4:4,别退回 PI 的 4:2:0
                    _rcj2.write_jpeg(_sl, o, quality=self.sl_jpgq.value())
                    written.append(o)
                if self.chk_export_stars.isChecked():      # 纯星点 → PNG(3D 星点层)
                    o = f"{base}_stars.png"
                    jr = protocol.new_job("inspect", input=_st, outputs={"image": o})
                    protocol.submit(jr)
                    if protocol.wait_result(jr["job_id"], timeout=300, on_poll=_pump).get("status") == "ok":
                        written.append(o)
            if self.chk_annotate.isChecked():              # 天体标注 → TXT(3D 建模按坐标放置天体)
                self._append("[导出] 天体标注(AnnotateImage:Messier/NGC/IC/SH2 + HIP/TYC/GAIA)中…")
                o = f"{base}_annotations.txt"
                job = protocol.new_job("annotate", input=self._final_xisf, outputs={"text": o})
                protocol.submit(job)
                r = protocol.wait_result(job["job_id"], timeout=900, on_poll=_pump)
                if r.get("status") != "ok":
                    # 【本地天文解析失败 → nova.astrometry.net 在线兜底(用户 2026-09-07)】常见于智能望远镜头
                    #   缺焦距/尺度、PI 盲解不出的目标。需在设置里配 astrometry_api_key;解出后用带解副本重试标注。
                    self._append(f"[导出] 本地天文解析失败({r.get('error') or '无解'})→ 尝试 nova.astrometry.net 在线兜底…")
                    QApplication.processEvents()           # 让「尝试兜底」先显出来(在线解析会阻塞较久)
                    _wcs = pipeline.nova_solve_wcs(self._final_xisf, self._final_png,
                                                   log=self._append, on_poll=_pump)
                    if _wcs:
                        # nova 的 WCS 直接交给 annotate,在成片窗口就地建线性解再标注(免 applywcs 存盘重开)
                        job = protocol.new_job("annotate", input=self._final_xisf,
                                               params={"wcs": _wcs}, outputs={"text": o})
                        protocol.submit(job)
                        r = protocol.wait_result(job["job_id"], timeout=900, on_poll=_pump)
                if r.get("status") == "ok":
                    _cnt = r.get("count", 0)
                    written.append(o)                      # TXT 已写(即使 0 天体也含表头),照常报告
                    self._append(f"[导出] 已标注 {_cnt} 个天体 → {Path(o).name}"
                                 + ("" if _cnt else "(0 个:解析范围内无已知目录天体)"))
                else:
                    self._append(f"[导出] 标注失败:{r.get('error') or '成片天文解析失败(本地 + nova 在线均未解出)'}")
            self._append("[导出] " + " / ".join(written))
            # 导出是流程终点 → 自动释放 PI 交还用户(用户 2026-09-04)。仅在 runner 在跑时释放;
            # 之后若再导出,_ensure_runner 会自动冷启 PI,不会卡死。
            _released = False
            try:
                if protocol.runner_up():
                    QApplication.restoreOverrideCursor()      # 释放可能耗时,先收回等待光标
                    self._do_release(quiet=True)
                    _released = True
                    self._append("[导出] 已释放 PixInsight,交还你手动使用。")
            except Exception as _re:
                self._append(f"[导出] 释放 PI 异常(忽略):{_re}")
            self._exported_png = self._final_png; self._sync_steps()   # 步骤导航:「导出」打勾
            self._refresh_export_meta()
            _msg = "\n".join(written)
            if _released:
                _msg += "\n\n" + t("PixInsight 已释放,可手动使用。")
            QMessageBox.information(self, t("导出完成"), _msg)
        except Exception as e:
            QMessageBox.critical(self, t("导出失败"), str(e))
        finally:
            QApplication.restoreOverrideCursor()
            self._exporting = False
            try:
                self.btn_export.setEnabled(True)
            except Exception:
                pass


def main() -> int:
    # 崩溃可观测:faulthandler 抓 C 层段错误(cv2/numpy/PI-COM 等 try/except 拦不住的硬崩),
    # excepthook 抓 Python 未捕获异常;都写到 _run/crash.log(带时间),便于闪退后复盘。
    try:
        import faulthandler
        _cl = open(str(config.RUN_DIR / "crash.log"), "a", encoding="utf-8", buffering=1)
        faulthandler.enable(_cl)
        _orig_hook = sys.excepthook

        def _hook(et, ev, tb):
            try:
                import traceback as _tb, time as _t
                _cl.write(f"\n===== 未捕获异常 {_t.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
                _tb.print_exception(et, ev, tb, file=_cl)
                _cl.flush()
            except Exception:
                pass
            _orig_hook(et, ev, tb)
        sys.excepthook = _hook
    except Exception:
        pass
    # 【启动维护:清掉本工具自己留下的垃圾(2026-09-20)】放在崩溃日志之后、建 GUI 之前 ——
    #   这样维护本身若出问题也会被 crash.log 记到,而又不拖慢窗口出现(实测毫秒级)。
    #   ① %TEMP% 的 PyInstaller `_MEI<数字>` 残留(打包版被 taskkill 时自清跑不到);
    #   ② `_run` 顶层超期的中间图像(每步处理都落一张,实测累积 211 个 .xisf / 21.4 GB)。
    #   housekeep 内部全程 try/except,任何失败都不会挡住启动。
    try:
        from . import housekeep as _hk
        _hk.startup_maintenance(log=lambda m: print(m))
    except Exception:
        pass
    app = QApplication(sys.argv)
    w = AppWindow()
    w._apply_titlebar_theme()          # show 前先把标题栏染深(避免开窗时亮条闪一下)
    # 初始**最大化**呈现(元素完整不挤);同时给一个合理的窗口化尺寸(取消最大化后也不至于太小)。
    try:
        _scr = app.primaryScreen().availableGeometry()
        w.resize(int(_scr.width() * 0.82), int(_scr.height() * 0.86))
        w.move(_scr.left() + (_scr.width() - w.width()) // 2,
               _scr.top() + (_scr.height() - w.height()) // 2)
    except Exception:
        w.resize(1280, 860)
    w.showMaximized()
    w._apply_titlebar_theme()          # show 后再补一次(部分系统需窗口已显示才生效)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
