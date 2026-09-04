"""TTAstroPiLot · 深空自动后期 · 一键式桌面界面(PyQt5)。

选输入 → 选流程(RGB/HOO/LRGB)→ 一键跑完(自动启动 PixInsight + job-runner),
带分步进度、预计剩余、中止;完成后 LLM 评分卡 + 导出/在文件夹显示。深/亮双主题。
视觉重构 2026-09:近黑冷中性地色 + 唯一信号绿 #55DDA0(IBM Plex Mono 数据字 + 全局 ~4.6s 呼吸)。
运行:  python -m orchestrator.app_ui
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from PyQt5.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt,
                          QThread, QTimer, pyqtProperty, pyqtSignal)
from PyQt5.QtGui import (QBrush, QColor, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QRadialGradient, QTextCursor)
from PyQt5.QtWidgets import (
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
from .i18n import t, set_lang as _i18n_set_lang
from .settings_ui import SettingsWindow

# ---- 视觉重构 2026-09:近黑冷中性地色 + 唯一信号绿 #55DDA0(去青蓝第二强调色/彩虹徽章)----
# 两套调色板键名必须完全一致:QSS 只认 qss(p) 里的键,别处不要写死色值。
# accent* = 信号绿,唯一强调(进行中 / 主路径 / 主按钮 / 数值 / 已完成);
# sec*    = 历史"第二强调色",现全部指向同一信号绿(双强调已收敛为单色;键名保留,免改散落各处引用);
# line/line2 = 白色极低透明度发丝线(仅在 QSS 边框里用,不可传给 QColor);
# warn=琥珀(交棒/不可选) · danger=珊瑚红 · ai=克制的信息蓝(LLM 评委标记)。
# 注意:凡会被 QColor(...) 读的键(stroke/accent/sec/*非 soft/line/ghost)必须是 #hex;
#       *_soft/*_line/*_ghost/line/line2 是 rgba() 字串,只能出现在 QSS 文本里。
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

DARK = dict(bg="#0B0E13", surf1="#11151C", surf2="#161B23", surf3="#1D232D", surf4="#242C38",
            stroke="#2A313B",
            line="rgba(255,255,255,16)", line2="rgba(255,255,255,26)",
            accent="#55DDA0", accent_hi="#6BE6AF", accent_press="#3FA87C", accent_hover="#7CEAA6",
            accent_dim="#3FA87C",
            accent_soft="rgba(85,221,160,28)", accent_line="rgba(85,221,160,71)",
            accent_ghost="rgba(85,221,160,18)",
            sec="#55DDA0", sec_hi="#6BE6AF",
            sec_soft="rgba(85,221,160,28)", sec_line="rgba(85,221,160,71)",
            text="#E7EBF1", text2="#98A3B2", muted="#5C6675",
            info="#69AFD6", info_soft="rgba(105,175,214,26)", info_line="rgba(105,175,214,77)",
            warn="#E2AC61", warn_soft="rgba(226,172,97,30)", danger="#E8706E", ai="#69AFD6",
            logbg="#0A0D12", prevbg="#05070A")
LIGHT = dict(bg="#EEF1F5", surf1="#FFFFFF", surf2="#F2F5F8", surf3="#E9EEF3", surf4="#DFE6EC",
             stroke="#C4CDD6",
             line="rgba(15,23,32,18)", line2="rgba(15,23,32,30)",
             accent="#1FA36B", accent_hi="#25B478", accent_press="#178055", accent_hover="#4CC091",
             accent_dim="#178055",
             accent_soft="rgba(31,163,107,28)", accent_line="rgba(31,163,107,77)",
             accent_ghost="rgba(31,163,107,16)",
             sec="#1FA36B", sec_hi="#25B478",
             sec_soft="rgba(31,163,107,28)", sec_line="rgba(31,163,107,77)",
             text="#141A20", text2="#41505C", muted="#77848F",
             info="#2C7DA8", info_soft="rgba(44,125,168,26)", info_line="rgba(44,125,168,77)",
             warn="#9A6414", warn_soft="rgba(154,100,20,28)", danger="#C6403E", ai="#2C7DA8",
             logbg="#F1F4F7", prevbg="#E6EBF0")

# SHO 配色档(顺序必须与 cb_palette 下拉项一致;NGC1499 定稿,旧 warm/teal/pink 已废弃)
PALETTES = ["hss", "natural", "natural_blue", "sho"]
PAL_LABELS = {"hss": "Ha红+SII青", "natural": "自然色", "natural_blue": "洋红加蓝", "sho": "经典哈勃"}
# 评委"退回哪一步"用的阶段中文名(与 stop_after 词表对应)
STAGE_CN = {"integrate": "整合", "crop_gc": "裁边+梯度", "crop": "裁边", "gradient": "梯度校正",
            "bxt": "BXT", "denoise": "降噪", "stretch": "拉伸", "combine": "合成",
            "starless": "去星/星点", "color": "调色", "colorcal": "色彩校准", "final": "成片"}

PHASES = ["叠加", "校准", "梯度", "拉伸", "成片"]
# op → 阶段索引(单调推进,取已见最大)
_OP_PHASE = {"integrate": 0, "rgbcombine": 0, "crop": 1, "solve": 1, "colorcal": 1,
             "deconv": 1, "gradient": 2, "dustremove": 2, "stretch": 3, "ghs": 3,
             "maskstretch": 3, "lrgb": 3, "hoo": 3, "starsep": 3,
             "scnr": 4, "curves": 4, "recombine": 4, "hablend": 4, "denoise": 4}
_EXPECTED = {"rgb": 14, "hoo": 14, "lrgb": 26}

# 各流程 5 个阶段的一句话说明(右侧路线图用;不参与进度计算)
PHASE_DESC = {
    "rgb": ["整合对齐子帧 → 线性 master", "裁黑边 · 色彩校准 SPCC/BNCC", "梯度校正 · 背景中和",
            "GHS 拉伸 · 暗弱星云揭示", "去星调色 · 合回星点 · 降噪"],
    "hoo": ["整合各通道 → 线性 master", "裁黑边 · BXT", "梯度校正",
            "HOO 合成 · 拉伸", "去星 · 输出成片"],
    "lrgb": ["整合 L/R/G/B(/Ha) 各通道", "统一裁边 · 背景匹配", "RGB 合成 · superL",
             "拉伸 · 外环迭代", "保色亮度替换 · 成片"],
    "sho": ["整合 S/H/O 各通道", "统一裁边 · 梯度校正 · BXT", "线性降噪 · 拉伸对齐",
            "SHO 合成 · 去星", "调色 · 合回星点 · 成片"],
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
    "原始素材叠加:普通相机(亮/平/暗/偏)或智能望远镜(Seestar 仅亮场 / Dwarf 需温度匹配暗场)→ WBPP 后整合(OSC 流程)",
]

# 原始叠加·设备预设:每个预设声明各校准场的策略(亮场恒为必填,不列)。
#   req=必填 · opt=可选 · reqtemp=必填且需与亮场温度匹配(否则热噪) · skip=该设备无此项(不适用)
STACK_DEVICES = [
    ("osc", "普通相机 (OSC)", {"flat": "req", "dark": "req", "bias": "req"},
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
# 帧特征识别(设备/类型/温度)统一在 devices 模块;温度读取见 devices.frame_temp / dir_temp


def qss(p):
    _plus = icons.png_path(icons.PLUS, "plus", p['sec'])      # 数值步进 加/减 图标(随主题 sec 上色)
    _minus = icons.png_path(icons.MINUS, "minus", p['sec'])
    _plusm = icons.png_path(icons.PLUS, "plusm", p['muted'])  # 禁用态(灰)
    _minusm = icons.png_path(icons.MINUS, "minusm", p['muted'])
    _check = icons.png_path(icons.CHECK, "check", p['bg'], 12)   # 勾选态对勾(深色,压在绿底上)
    return f"""
QWidget {{ background:{p['bg']}; color:{p['text']}; font-family:{SANS_STACK}; font-size:12px; }}
QLabel {{ background:transparent; }}
/* 布局用的空容器(参数行/分段条/子页)不能吃全局 QWidget 的窗口底色,否则在卡片里显示成
   一条条比底色更深的横带。_polish_groups() 给所有未命名的纯容器统一打上 #rowbg。 */
QWidget#rowbg {{ background:transparent; }}
QToolTip {{ background:{p['surf1']}; color:{p['text']}; border:1px solid {p['stroke']}; padding:6px 8px; }}

/* ---- 窗口骨架 ---- */
QFrame#headerbar {{ background:{p['surf1']}; }}
QFrame#hairline {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {p['accent']}, stop:0.42 {p['accent_dim']}, stop:0.9 {p['surf1']}); }}
QFrame#ribbon {{ background:{p['surf1']}; border-bottom:1px solid {p['line']}; }}
QFrame#actionbar {{ background:{p['surf1']}; border-top:1px solid {p['line']}; }}
QFrame#card {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:12px; }}
QFrame#cardhead {{ background:transparent; border:none; border-bottom:1px solid {p['line']}; }}

/* ---- 字号层级 ---- */
#banner {{ font-size:20px; font-weight:bold; color:{p['accent']}; }}
#sub {{ color:{p['muted']}; font-size:11px; }}
#cardtitle {{ font-size:13px; font-weight:bold; color:{p['text2']}; }}
#primlabel {{ font-size:12px; font-weight:bold; color:{p['text']}; }}
#plabel {{ font-size:12px; color:{p['text2']}; }}
#seclabel {{ font-size:11px; font-weight:bold; color:{p['sec']}; font-family:{MONO_STACK}; }}
QLabel#mono {{ font-family:{MONO_STACK}; color:{p['text2']}; font-size:11px; }}
QFrame#statuspill {{ border-radius:14px; }}
QFrame#roadpanel {{ background:{p['prevbg']}; border:1px dashed {p['stroke']}; border-radius:10px; }}
QLabel#warnnote {{ background:{p['warn_soft']}; border:1px solid {p['warn']}; border-radius:6px;
                   padding:7px 9px; color:{p['warn']}; font-size:11px; }}

/* ---- 分组框 ----
   内边距**不用** QSS 的 QGroupBox padding —— 它在 QGroupBox 上左右不对称(右侧控件会贴边
   甚至溢出边框)。统一由 _polish_groups() 设布局 contentsMargins。 */
QGroupBox {{ background:{p['surf1']}; border:1px solid {p['line']}; border-radius:12px; margin-top:14px; padding:0; }}
/* 标题带**组框底色背景**遮住身后的边框线,横跨上边框呈"缺口"效果,不再压在线上显乱 */
QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top left; left:14px; padding:1px 8px;
                    background:{p['surf1']}; color:{p['muted']}; font-weight:bold; font-size:12px; }}
QGroupBox#gb_main {{ border:1px solid {p['accent_line']}; margin-top:0; }}
QGroupBox#gb_quiet {{ margin-top:0; }}
/* 卡片头条:渐变底 + 分隔线 + 圆角跟卡片对齐 */
QFrame#stripaccent {{ border:none; border-bottom:1px solid {p['line']};
    border-top-left-radius:11px; border-top-right-radius:11px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {p['accent_soft']}, stop:0.55 {p['accent_ghost']}, stop:1 transparent); }}
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
QGroupBox#gb_result {{ border:1px solid {p['accent_line']}; margin-top:0; }}
QGroupBox#gb_prog {{ border:1px solid {p['accent_line']}; border-radius:8px; margin-top:0; }}
QGroupBox#gb_prog::title {{ padding:0; }}

/* ---- 行容器 ---- */
QWidget#paramrow {{ background:{p['surf3']}; border:1px solid {p['line']}; border-radius:7px; }}
QWidget#primrow {{ background:{p['accent_soft']}; border:1px solid {p['accent_line']}; border-radius:8px; }}
QWidget#roadrow {{ background:{p['surf3']}; border:1px solid {p['line']}; border-radius:8px; }}
QWidget#roadrow:hover {{ border:1px solid {p['sec_line']}; }}
QWidget#roadrow_on {{ background:{p['accent_soft']}; border:1px solid {p['accent_line']}; border-radius:8px; }}
QWidget#nightrow {{ background:{p['surf3']}; border:1px solid {p['line']}; border-radius:7px; }}

/* ---- 输入控件 ---- */
QLineEdit, QComboBox {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px;
                        padding:6px 10px; color:{p['text']}; min-height:22px;
                        selection-background-color:{p['accent']}; selection-color:{p['bg']}; }}
QDoubleSpinBox, QSpinBox {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px;
                            padding:4px 8px; color:{p['accent']}; font-family:{MONO_STACK}; font-weight:600; min-height:20px;
                            selection-background-color:{p['accent']}; selection-color:{p['bg']}; }}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border:1px solid {p['sec_line']}; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border:1px solid {p['sec']}; }}
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
                               selection-background-color:{p['accent']}; selection-color:{p['bg']}; outline:none; }}

/* ---- 按钮 ---- */
/* 去描边:边框改透明(保持尺寸不跳),质感靠 _apply_button_shadows 的浅投影 + hover 换底色 */
QPushButton {{ background:{p['surf2']}; border:1px solid transparent; border-radius:6px;
               padding:7px 12px; color:{p['text2']}; min-height:20px; }}
QPushButton:hover {{ background:{p['surf4']}; color:{p['text']}; }}
QPushButton:pressed {{ background:{p['surf1']}; }}
QPushButton:disabled {{ background:transparent; border:1px solid transparent; color:{p['muted']}; }}
QPushButton#ghost {{ border-radius:14px; padding:5px 13px; }}
QPushButton#tab {{ background:transparent; border:none; border-bottom:3px solid transparent;
                   border-radius:0; padding:10px 20px 8px 20px; color:{p['text2']}; font-size:13px; }}
QPushButton#tab:hover {{ background:{p['accent_ghost']}; color:{p['text']}; }}
QPushButton#tab:checked {{ background:{p['accent_ghost']}; border-bottom:3px solid {p['accent']};
                           color:{p['accent']}; font-weight:bold; }}
QPushButton#seg {{ background:{p['surf2']}; border:1px solid transparent; border-radius:6px;
                   padding:9px 12px; color:{p['text2']}; }}
QPushButton#seg:hover {{ background:{p['surf3']}; }}
/* 选中态的底由 SlideIndicator(会滑动的药丸)画成实心 accent+内阴影,按钮让位透明;文字改深色(bg)压在绿药丸上 */
QPushButton#seg:checked {{ background:transparent; border:1px solid transparent;
                           color:{p['bg']}; font-weight:bold; }}
QPushButton#seg:disabled {{ background:transparent; border:1px solid transparent; color:{p['muted']}; }}
/* segaccent:需要被一眼看到的**次级绿动作**(如校准库『自动匹配』)——实心 accent 底 + 深色字,比 seg 醒目、比 primary 克制 */
QPushButton#segaccent {{ background:{p['accent']}; border:1px solid transparent; border-radius:6px;
                         padding:9px 12px; color:{p['bg']}; font-weight:bold; }}
QPushButton#segaccent:hover {{ background:{p['accent_hover']}; }}
QPushButton#segaccent:pressed {{ background:{p['accent_press']}; }}
QPushButton#segaccent:disabled {{ background:{p['surf2']}; border:1px solid transparent; color:{p['muted']}; }}
/* segdev:设备行等**无 SlideIndicator** 的段按钮 —— 选中态**自带实心 accent 背景 + 深色字**(否则 #seg 的
   透明底+深字在无绿药丸时看不见)。底/悬停同 #seg。 */
QPushButton#segdev {{ background:{p['surf2']}; border:1px solid transparent; border-radius:6px;
                      padding:9px 12px; color:{p['text2']}; }}
QPushButton#segdev:hover {{ background:{p['surf3']}; }}
QPushButton#segdev:checked {{ background:{p['accent']}; border:1px solid transparent;
                              color:{p['bg']}; font-weight:bold; }}
QPushButton#segdev:disabled {{ background:{p['surf2']}; border:1px solid transparent; color:{p['muted']}; }}
QPushButton#sectoggle {{ background:{p['surf2']}; border:1px solid transparent; border-radius:6px;
                         padding:7px 11px; color:{p['text2']}; text-align:left; }}
QPushButton#sectoggle:hover {{ background:{p['surf3']}; color:{p['text']}; }}
QPushButton#sectoggle:checked {{ background:{p['surf3']}; }}
QPushButton#primary {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {p['accent_hi']}, stop:1 {p['accent']});
                       color:{p['bg']}; border:none; border-radius:6px; font-weight:bold; font-size:13px;
                       padding:10px 22px; min-height:20px; }}
QPushButton#primary:hover {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                       stop:0 {p['accent_hover']}, stop:1 {p['accent']}); }}
QPushButton#primary:pressed {{ background:{p['accent_press']}; }}
/* disabled/处理中:清晰的实心底(surf3)+ 描边 + 可读文字 —— 否则 surf2 太贴近面板底、
   叠上处理态绿微光扫过后基底看不见,像个「镂空缺背景」的按钮(用户 2026-09-04 反馈) */
QPushButton#primary:disabled {{ background:{p['surf3']}; color:{p['text2']}; border:1px solid {p['stroke']}; }}
QPushButton#danger {{ background:transparent; border:1px solid {p['danger']}; color:{p['danger']}; }}
QPushButton#danger:hover {{ background:{p['surf2']}; border:1px solid {p['danger']}; color:{p['danger']}; }}
QToolButton {{ background:{p['surf2']}; border:1px solid transparent; border-radius:6px;
               padding:5px 9px; color:{p['text2']}; min-height:20px; }}
QToolButton:hover {{ background:{p['surf4']}; color:{p['text']}; }}

/* ---- 勾选 / 滑块 / 进度 ---- */
QCheckBox {{ background:transparent; color:{p['text2']}; padding:2px 0; spacing:9px; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1.5px solid {p['stroke']}; border-radius:5px; background:{p['surf2']}; }}
QCheckBox::indicator:hover {{ border:1.5px solid {p['accent']}; background:{p['sec_soft']}; }}
QCheckBox::indicator:checked {{ background:{p['accent']}; border:1.5px solid {p['accent']}; image:url("{_check}"); }}
QCheckBox::indicator:checked:hover {{ background:{p['accent_hi']}; border:1.5px solid {p['accent_hi']}; }}
QCheckBox::indicator:disabled {{ border:1.5px solid {p['surf2']}; background:{p['surf1']}; }}
QCheckBox:disabled {{ color:{p['muted']}; }}
QSlider::groove:horizontal {{ height:5px; background:{p['surf2']}; border-radius:3px; }}
QSlider::sub-page:horizontal {{ background:{p['accent']}; border-radius:3px; }}
QSlider::handle:horizontal {{ width:14px; margin:-5px 0; border-radius:7px; background:{p['accent']}; border:1px solid {p['accent_hi']}; }}
QSlider::handle:horizontal:hover {{ background:{p['accent_hi']}; }}
QSlider::sub-page:horizontal:disabled {{ background:{p['stroke']}; }}
QSlider::handle:horizontal:disabled {{ background:{p['stroke']}; border:1px solid {p['stroke']}; }}
QProgressBar {{ background:{p['surf2']}; border:none; border-radius:4px; height:8px; text-align:center; color:transparent; }}
QProgressBar::chunk {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {p['accent_dim']}, stop:1 {p['accent']}); border-radius:4px; }}

/* ---- 日志 / 预览 ---- */
QPlainTextEdit {{ background:{p['logbg']}; border:1px solid {p['line']}; border-radius:8px; padding:8px 10px;
                  color:{p['text2']}; font-family:{MONO_STACK}; font-size:11px; }}
#preview {{ background:{p['prevbg']}; color:{p['muted']}; border:1px solid {p['stroke']}; border-radius:10px; font-size:12px; }}

/* ---- 滚动 ---- */
QScrollArea#leftscroll {{ background:transparent; border:none; }}
QScrollArea#leftscroll > QWidget > QWidget {{ background:transparent; }}
QScrollArea#rightscroll {{ background:transparent; border:none; }}
QScrollArea#rightscroll > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{p['surf2']}; border-radius:5px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{p['stroke']}; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:{p['surf2']}; border-radius:5px; min-width:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}

/* ---- 多页 IA:顶栏件 / 阶段导航 / 屏 / 流程卡 / 项目卡 / 页脚 ---- */
QLabel#eyebrow {{ font-family:{MONO_STACK}; font-size:10px; font-weight:600; color:{p['muted']}; }}
QLabel#h2 {{ font-size:17px; font-weight:bold; color:{p['text']}; }}
QLabel#lead {{ color:{p['text2']}; font-size:12px; }}
QLabel#ver {{ font-family:{MONO_STACK}; font-size:10px; color:{p['muted']};
             border:1px solid {p['line']}; border-radius:5px; padding:1px 6px; }}
QFrame#projchip {{ background:{p['surf2']}; border:1px solid {p['line']}; border-radius:7px; }}
QLineEdit#projname {{ background:transparent; border:none; color:{p['text']}; font-weight:500;
                      padding:0 2px; min-height:16px; }}
QLabel#savedtag {{ font-family:{MONO_STACK}; font-size:10px; color:{p['accent']}; }}
QLabel#savedtag[dirty="true"] {{ color:{p['warn']}; }}
QFrame#langbox {{ background:transparent; border:1px solid {p['line']}; border-radius:7px; }}
QPushButton#langseg {{ background:transparent; border:none; border-radius:6px; padding:4px 10px;
                       color:{p['muted']}; font-family:{MONO_STACK}; font-size:11px; }}
QPushButton#langseg:hover {{ color:{p['text2']}; }}
QPushButton#langseg:checked {{ background:{p['surf3']}; color:{p['text']}; }}
QToolButton#gear {{ background:{p['surf2']}; border:1px solid {p['line']}; border-radius:7px;
                    padding:4px 7px; color:{p['text2']}; }}
QToolButton#gear:hover {{ background:{p['surf3']}; color:{p['text']}; }}
/* 阶段导航 */
QFrame#navbar {{ background:{p['surf1']}; border-bottom:1px solid {p['line']}; }}
QPushButton#nav {{ background:transparent; border:none; border-radius:0; padding:11px 14px;
                   color:{p['muted']}; font-size:12.5px; }}
QPushButton#nav:hover {{ color:{p['text2']}; }}
/* 选中态只变亮不加粗:加粗会让文字变宽、被 FlowBar 量好的按钮宽裁掉(与 mockup 一致:仅提亮 + 下划线) */
QPushButton#nav:checked {{ color:{p['text']}; }}
QWidget#screen {{ background:transparent; }}
QWidget#screenscroll {{ background:transparent; }}
QScrollArea#screenscroll {{ background:transparent; border:none; }}
/* 流程卡 */
QFrame#flowcard {{ background:{p['surf2']}; border:1px solid {p['line']}; border-radius:11px; }}
QFrame#flowcard:hover {{ border:1px solid {p['line2']}; }}
QFrame#flowcard[sel="true"] {{ border:1px solid {p['accent_line']};
                               background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {p['accent_ghost']}, stop:1 {p['surf2']}); }}
QLabel#flowname {{ font-size:13.5px; font-weight:600; color:{p['text']}; }}
QLabel#flowdesc {{ font-size:11px; color:{p['muted']}; }}
QLabel#flowtick {{ color:{p['accent']}; font-family:{MONO_STACK}; font-size:12px; }}
/* 项目卡 */
QFrame#projcard {{ background:{p['surf2']}; border:1px solid {p['line']}; border-radius:11px; }}
QFrame#projcard:hover {{ border:1px solid {p['line2']}; }}
QFrame#projcard_new {{ background:{p['surf1']}; border:1px dashed {p['stroke']}; border-radius:11px; }}
QFrame#projcard_new:hover {{ background:{p['surf2']}; border:1px dashed {p['accent_line']}; }}
QLabel#exportprev {{ background:#05070A; border:1px solid {p['line']}; border-radius:8px; color:{p['muted']}; font-family:{MONO_STACK}; font-size:11px; }}
QLabel#projname_c {{ font-size:13.5px; font-weight:600; color:{p['text']}; }}
QLabel#projmeta {{ font-family:{MONO_STACK}; font-size:10px; color:{p['muted']}; }}
/* 页脚(维护工具) */
QFrame#footerbar {{ background:{p['surf1']}; border-top:1px solid {p['line']}; }}
/* 取景器叠层标题 */
QLabel#viewtitle {{ font-size:14px; font-weight:bold; color:{p['text']}; }}
QLabel#viewsub {{ font-family:{MONO_STACK}; font-size:10px; color:{p['text2']}; }}
/* 审阅双面板:评审(评分条 green→blue) + 实测指标(数值蓝) */
QFrame#panel {{ background:{p['surf2']}; border:1px solid {p['line']}; border-radius:12px; }}
QLabel#paneltitle {{ font-size:12px; color:{p['text2']}; }}
QLabel#panelvia {{ font-family:{MONO_STACK}; font-size:9px; color:{p['muted']}; }}
QLabel#bigscore {{ font-family:{MONO_STACK}; font-weight:600; font-size:30px; color:{p['text']}; }}
QLabel#barlabel {{ font-size:11px; color:{p['text2']}; }}
QLabel#barval {{ font-family:{MONO_STACK}; font-size:11px; color:{p['text']}; }}
QProgressBar#scoreprog {{ background:{p['surf4']}; border:none; border-radius:2px; }}
QProgressBar#scoreprog::chunk {{ border-radius:2px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {p['accent']}, stop:1 {p['info']}); }}
QLabel#metrickey {{ font-size:12px; color:{p['text2']}; }}
QLabel#metricval {{ font-family:{MONO_STACK}; font-size:12px; color:{p['info']}; font-weight:500; }}
QLabel#metrictag {{ font-family:{MONO_STACK}; font-size:9px; color:{p['muted']};
                    border:1px solid {p['line']}; border-radius:4px; padding:1px 5px; }}
"""


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

    def set_colors(self, fill, border=None, fill2=None, inner=False):
        self._fill = QColor(fill)
        self._fill2 = QColor(fill2) if fill2 else None
        self._border = QColor(border) if border else QColor(0, 0, 0, 0)
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


class _ScoreThread(QThread):
    """后台跑 LLM 主观评分,不阻塞"完成"(kimi-k3 是推理模型、带图评审慢,曾把 UI 卡在"正在评分")。"""
    result = pyqtSignal(object)                     # scores dict 或 None(失败/不可用)

    def __init__(self, png, ctx, parent=None):
        super().__init__(parent)
        self._png = png
        self._ctx = ctx

    def run(self):
        try:
            from . import critic
            import glob as _glob
            # 同视场 AstroBin 参考图(管线解析后下载到 <_run>/astrobin_refs/ref_*.jpg)→ 多图对比评分,
            #   以真实范例为锚,纠偏抽象"背景中性"标准对暖调星场的误判(用户 2026-09-04)。无则普通评分。
            _refs = sorted(_glob.glob(str(Path(self._png).parent / "astrobin_refs" / "ref_*.jpg"))) if self._png else []
            s = critic.score(self._png, context=self._ctx, ref_paths=_refs or None)
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


class Worker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(str)                 # op 名
    preview = pyqtSignal(str)                  # 阶段性预览 png 路径
    done = pyqtSignal(bool, str, str, dict)    # ok, preview_png, final_xisf, scores
    paused = pyqtSignal(str, str, str, str)    # 进入暂停:tag, image_xisf, preview_png, targets_json
    pause_preview = pyqtSignal(str)            # 暂停中矫正后刷新预览 png
    pause_chat = pyqtSignal(str, str)          # 与 AI 对话:role("ai"/"sys"), 文本
    deps = pyqtSignal(list)                     # 首启插件体检:缺失清单(回主线程弹引导框)

    def __init__(self, kind, inp, opts):
        super().__init__()
        self.kind, self.inp, self.opts = kind, inp, opts
        import queue as _q
        self._pause_req = False          # UI 置位 → 下一步边界暂停
        self._pause_cmd = _q.Queue()     # UI → pause_gate 的命令队列(线程安全)

    # —— 供 UI 线程调用 ——
    def request_pause(self):
        self._pause_req = True

    def send_pause_cmd(self, cmd: dict):
        self._pause_cmd.put(cmd)

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
            """在 active 上执行一个 op:通道模式就地覆盖(存撤销快照),步骤模式写新文件。返回 ok。"""
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
            job = protocol.new_job(op, input=str(active), params=params, outputs=outs)
            protocol.submit(job)
            rr = protocol.wait_result(job["job_id"], timeout=600)
            if rr.get("status") != "ok":
                self.log.emit(f"[暂停] {op} 失败:{rr.get('error')}")
                return False
            if not in_place:
                cur_img = rr.get("image") or outs["image"]
                cur_prev = rr.get("preview") or outs["preview"]
                active = cur_img; changed_step = True
            self.pause_preview.emit(outs["preview"])
            self.log.emit(f"[暂停] {op} 完成,已刷新预览。")
            return True

        def _norm(op, params):
            """把 op/params 归一到 runner 可执行形式(并注入 linear);未知/缺参返回 (None,原因)。"""
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
                    if _u.get("total"):
                        _r = _u.get("reasoning")
                        self.pause_chat.emit("sys", f"本次 {_u['total']} tokens" +
                                             (f"(含推理 {_r})" if _r else ""))
                    continue
            except Exception as e:
                self.log.emit(f"[暂停] 出错:{e}")
                self.pause_chat.emit("sys", f"出错:{e}")

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
                        _miss = _deps.report(_deps.probe(), {d["sym"]: True for d in _deps.EXTERNAL})
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
                    self.log.emit(f"[无 PI RGB+H/HO] Siril 引擎(RGB 预设 {_pal} + 窄带 {_hp})…"
                                  "RGB底→星点配准HO→线性连续谱扣除→黑点拒噪HII→screen融合→中性灰")
                    self.log.emit(f"[无 PI RGB+H/HO] 窄带 Ha/OIII 目录:{_ha_dir}")
                    _out = str(config.RUN_DIR / "zeropi_rgbha")
                    png = rgb_ha_engine.run_rgb_ha_from_dirs(self.inp, _ha_dir, _out, palette=_pal, preset=_hp,
                                                             sensor=_sensor, oscfilter=_oscf,
                                                             timeout=max(o["timeout"], 2400.0), log=self.log.emit)
                    self.log.emit(f"[无 PI RGB+H/HO] 成片(全程零 PixInsight):{png}。"
                                  "如有残留灰尘投影,点『🩹 灰尘修复』圈选自动中和色度。")
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
                # SHO 窄带(星云)+ RGB(星点):self.inp = registered 目录(含各滤镜子目录)
                res = pipeline.run_sho(self.inp, palettes=o["palettes"], timeout=max(o["timeout"], 2400.0),
                                       saturation=o["neb_sat"] + 0.35, dust_reveal=o["dust_reveal"],
                                       grade_curve=o.get("grade_curve"), darkstruct=o.get("darkstruct", "auto"),
                                       stop_after=o["stop_after"], pause_gate=self._pause_gate)
            else:
                inp = self.inp
                raw = o.get("raw")
                reg = None
                if raw:
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
                elif o["integrate_first"]:
                    reg = inp                       # mode1:inp 即对齐子帧目录
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
                        self.log.emit(f"[整合] 存输出目录失败({_ie})→ 退回临时目录")
                        inp = pipeline.run_integrate(reg, timeout=max(o["timeout"], 1800.0), images=keep)
                # 无暗场校准(纯亮场,如 Seestar 或 Dwarf 未给暗场)→ 干净背景 profile,避免揭示放大残留热噪
                lights_only = bool(raw) and not (raw.get("dark") or "").strip()
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
                    res = pipeline.run_rgb(inp, timeout=o["timeout"], ghs_d=o["ghs_d"],
                                           neb_sat=o["neb_sat"], recombine_stars=o["stars"],
                                           stretch_judge=o["stretch_judge"], target=o["target"],
                                           reveal=o["reveal"], lhe=o["lhe"], lights_only=lights_only,
                                           star_scnr=_star_scnr, star_blue=_star_blue, stop_after=o["stop_after"],
                                           pause_gate=self._pause_gate)
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
                    _qual = quality.measure(png)
                    if _qual.get("error"):
                        _qual = None
                except Exception:
                    _qual = None
            if _qual:
                scores["_quality"] = _qual
            # LLM 主观评分**不在此阻塞**:成片 + 确定性指标先出(下面 done 立即"完成"),
            #   主观分由主线程 _finished 后台异步补(kimi-k3 推理慢,曾把"完成"卡住 1~3 分钟;
            #   确定性指标已够看,LLM 分作补充)。SHO 走 run_sho 已带 _critic/overall,不再异步。
            self.done.emit(True, png, xis, scores)
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
            if "->" in line and "]" in line and "[" in line:
                seg = line.split("]", 1)[1].strip()
                op = seg.split("->")[0].strip().split()[0] if "->" in seg else ""
                if op:
                    self.progress.emit(op)


# 流程签名色(流程卡图标底 + 项目卡标签):RGB=银 / SHO=金 / HOO=青 / LRGB=冷银(设计定稿)
FLOW_SIG = {"rgb": "#C6D0DC", "sho": "#E2AC61", "hoo": "#5FD0C4", "lrgb": "#9DB4CC"}
# 流程卡:签名徽章字、卡名、一句话(配置屏 4 张卡)
FLOW_CARD = {
    "rgb":  ("RGB", "宽带 RGB", "彩色相机宽带,自然真彩"),
    "sho":  ("SHO", "窄带 SHO", "SII/Ha/OIII 哈勃调色"),
    "hoo":  ("HOO", "双窄 HOO", "Ha/OIII 双窄,红青"),
    "lrgb": ("L",   "黑白 LRGB", "单色相机,亮度+彩色"),
}


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
    FLOWS = [("rgb", "RGB 宽带真彩"), ("sho", "SHO 窄带"), ("hoo", "HOO 双窄带"),
             ("lrgb", "LRGB(H) 多通道")]        # 卡片顺序对齐定稿:宽带→窄带→双窄→黑白

    def __init__(self):
        super().__init__()
        _load_bundled_fonts()       # 注册打包的 IBM Plex Mono(QApplication 此时已在);QSS 随后即可命中
        self.thread = None
        self.worker = None
        self.theme = DARK
        self._param_rows = {}
        self._param_sliders = {}
        self._start_t = 0.0
        self._max_phase = -1
        self._done_ops = 0
        self._final_png = self._final_xisf = ""
        self._proj_path = ""        # 当前 .ttproj 落盘路径(空=还没选过位置,首次保存弹「另存为」)
        self._anims = []            # 持有动画对象,避免被 GC
        self._sections = []         # 折叠小节 (开关, 容器)
        self._has_preview = False   # 右侧是否已有图(决定空态路线图 / 横向阶段带)
        self._pm_raw = None
        self._end_state = "idle"    # idle / run / done / handoff / fail
        self._finals = {}           # {配色: 成片 xisf}
        self._cur_pal = None
        self._scored_pal = None     # 评委实际评过的那档
        self._last_scores = {}
        self._pal_scores = {}       # 按需评分缓存 {配色: score dict}
        self._dust_mode = False
        self._dust_circle = None    # 灰尘可编辑圆 {cx,cy,r}(label 坐标)
        self._dust_act = None       # 拖拽状态 new/resize/move
        self._pm_display = None     # 当前显示的缩放图(画圈叠加基于它)
        self._remedy_rows = []      # 动态"需你决定"行,便于清理
        self._i18n_widgets = []     # (widget, 中文源串, setter) —— 语言切换时重刷
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
        rp = QHBoxLayout(self.runner_pill); rp.setContentsMargins(9, 4, 13, 4); rp.setSpacing(4)
        self.runner_dot = PulseDot(8)
        self.lbl_runner = QLabel("runner ?")
        self.lbl_runner.setToolTip(t("job-runner(PixInsight 内的作业执行器)在线状态"))
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
        self.pg_single = QWidget()
        ls = QVBoxLayout(self.pg_single); ls.setContentsMargins(0, 0, 0, 0); ls.setSpacing(6)
        rs = QHBoxLayout(); rs.setSpacing(8)
        self.ed_input = QLineEdit()
        self.btn_browse = QPushButton(t("浏览…")); self.btn_browse.clicked.connect(self._browse)
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        rs.addWidget(self.ed_input, 1); rs.addWidget(self.btn_browse, 0); ls.addLayout(rs)
        self.lbl_input_hint = QLabel(""); self.lbl_input_hint.setObjectName("sub")
        self.lbl_input_hint.setWordWrap(True)
        ls.addWidget(self.lbl_input_hint)
        vi.addWidget(self.pg_single)
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

        # SHO 配色预设(仅 SHO 流程显示)
        _prow = QWidget(); _prow.setObjectName("paramrow")
        _ph = QHBoxLayout(_prow); _ph.setContentsMargins(11, 5, 10, 5); _ph.setSpacing(9)
        _plab = QLabel(t("SHO 配色")); _plab.setObjectName("plabel")
        self.cb_palette = QComboBox()
        self.cb_palette.addItems([t("全部四种 (推荐)"), t("Ha红+SII青 (hss)"), t("自然色 (natural)"),
                                  t("洋红加蓝 (natural_blue)"), t("经典哈勃 (sho)")])
        self.cb_palette.setMinimumWidth(130); self.cb_palette.setMaximumWidth(190)
        self.cb_palette.setToolTip(t("配色是主观档 → 默认四种都生成供你挑(NGC1499 定稿):\n"
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
        self.cb_zpreset.addItems([t("金蓝 goldblue (OIII 有料,如巫师)"), t("暖橙 warm (Ha 主导,如狮子)")])
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
        self.cb_rgbpreset.addItems([t("自然 natural (SPCC真彩+GHS压核)"), t("浓郁 vivid (饱和更足)"), t("平拉 flat (关HDR最干净)")])
        self.cb_rgbpreset.setMinimumWidth(150); self.cb_rgbpreset.setMaximumWidth(230)
        self.cb_rgbpreset.setToolTip(t("无 PI RGB 引擎预设:\n"
                                     "natural=SPCC 权威色 + 温和 GHS 压核 + 温和饱和(多数目标);\n"
                                     "vivid=饱和更足;flat=关 HDR 纯 autostretch(亮核稍爆但最干净,暗弱目标用)"))
        _zrh.addWidget(self.chk_zeropi_rgb, 0); _zrh.addWidget(self.cb_rgbpreset, 1)
        vp.addWidget(_zrrow); self._param_rows["zeropi_rgb"] = _zrrow

        # 无 PI RGB 可加窄带 Ha/OIII(给星系旋臂加 HII 红结):填了此目录 → 走 rgb_ha_engine(RGB 底 + Ha/OIII 增强)
        _zrnrow = QWidget(); _zrnrow.setObjectName("paramrow")
        _zrn = QHBoxLayout(_zrnrow); _zrn.setContentsMargins(11, 5, 10, 5); _zrn.setSpacing(9)
        self.ed_ha_dir = QLineEdit(); self.ed_ha_dir.setClearButtonEnabled(True)
        self.ed_ha_dir.setPlaceholderText(t("(可选)+ 双窄带 Ha/OIII master 或子帧目录 → 给 RGB 加 Ha/OIII 红结"))
        self.ed_ha_dir.setToolTip(t("填双窄带(Ha/OIII)OSC master 或子帧目录 → 无 PI RGB 底上叠加 Ha/OIII 发射信号\n"
                                  "(星系旋臂 HII 红结、发射区)。留空 = 只做纯 RGB。\n"
                                  "配准以 RGB 为参考对齐窄带;成片后可用『🩹 灰尘修复』圈选中和残留灰尘投影。"))
        self.btn_ha_dir = QPushButton(t("浏览…")); self.btn_ha_dir.setObjectName("seg")
        self.btn_ha_dir.setCursor(Qt.PointingHandCursor); self.btn_ha_dir.clicked.connect(self._pick_ha_dir)
        self.cb_hapreset = QComboBox()
        self.cb_hapreset.addItems([t("星系 galaxy (M31式,克制)"), t("浓郁 vivid (HII更跳)")])
        self.cb_hapreset.setMinimumWidth(140); self.cb_hapreset.setMaximumWidth(190)
        self.cb_hapreset.setToolTip(t("RGB+窄带融合预设:galaxy=克制(Ha力度1.6、去饱和0.3);vivid=HII更跳(2.0)"))
        _lbl_ha = QLabel(t("+窄带")); _lbl_ha.setObjectName("dim")
        _zrn.addWidget(_lbl_ha, 0); _zrn.addWidget(self.ed_ha_dir, 1)
        _zrn.addWidget(self.btn_ha_dir, 0); _zrn.addWidget(self.cb_hapreset, 0)
        vp.addWidget(_zrnrow); self._param_rows["zeropi_rgb_ha"] = _zrnrow

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
        self.cb_hoopreset.addItems([t("OIII主导 oiii (WR泡如SH2-308)"), t("均衡青红 classic (如IC1805心脏)")])
        self.cb_hoopreset.setMinimumWidth(150); self.cb_hoopreset.setMaximumWidth(230)
        self.cb_hoopreset.setToolTip(t("无 PI HOO 引擎预设:\n"
                                     "oiii=OIII 主导目标(Ha弱→揭示狠、提蓝出青泡);classic=均衡青红双色"))
        _zhh.addWidget(self.chk_zeropi_hoo, 0); _zhh.addWidget(self.cb_hoopreset, 1)
        vp.addWidget(_zhrow); self._param_rows["zeropi_hoo"] = _zhrow

        # 暗尘层次揭示(仅 SHO):自动=评委判画面有无显著暗星云再定强度
        _drow = QWidget(); _drow.setObjectName("paramrow")
        _dh = QHBoxLayout(_drow); _dh.setContentsMargins(11, 5, 10, 5); _dh.setSpacing(9)
        _dlab = QLabel(t("暗尘层次揭示")); _dlab.setObjectName("plabel")
        self.cb_dust = QComboBox(); self.cb_dust.addItems([t("自动检测"), t("强制开启"), t("关闭 (推荐·暗 moody)")])
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
        self.btn_adv, adv_body, adv_v = self._make_section(t("高级参数"), t("装好一次即可,共 6 项"))
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
        self.sp_ha = self._param(lrgb_v, "ha", "Ha 小红花强度", QDoubleSpinBox, 0, 2.0, 0.1, 0.0)
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
        self.caret = BlinkBlock(self.log.viewport(), self.theme['sec'])
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

        pcard = QFrame(); pcard.setObjectName("card"); self._pcard = pcard
        pv = QVBoxLayout(pcard); pv.setContentsMargins(0, 0, 0, 0); pv.setSpacing(0)
        phead = QFrame(); phead.setObjectName("cardhead")
        ph2 = QHBoxLayout(phead); ph2.setContentsMargins(14, 9, 12, 9); ph2.setSpacing(8)
        ptitle = QLabel(); ptitle.setObjectName("cardtitle"); self._tr(ptitle, "成片预览")
        self.lbl_prevtag = QLabel(); self._tr(self.lbl_prevtag, "等待素材")
        ph2.addWidget(ptitle, 0); ph2.addStretch(1); ph2.addWidget(self.lbl_prevtag, 0)
        pv.addWidget(phead)

        pbody = QWidget(); pbody.setObjectName("rowbg")
        pb = QVBoxLayout(pbody); pb.setContentsMargins(12, 12, 12, 12); pb.setSpacing(10)
        # 成片预览:放进滚动区,按**视口宽度**缩放 → 图像完整呈现,过高就出竖向滚动条(不裁切)。
        self.preview = QLabel(""); self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
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

        # 空态 = 当前流程的阶段清单(运行时逐段点亮)
        self.road_v = QWidget(); self.road_v.setObjectName("rowbg")
        rv = QVBoxLayout(self.road_v); rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(6)
        self.lbl_road_title = QLabel(""); self.lbl_road_title.setObjectName("cardtitle")
        self.lbl_road_sub = QLabel(""); self.lbl_road_sub.setObjectName("sub")
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
        self.phase_row = FlowBar(hspace=8, vspace=6); self.phase_row.setObjectName("rowbg")
        self.phase_lbls = []
        for i, name in enumerate(PHASES):
            l = QLabel(f"{i + 1}·{name}")
            l.setToolTip(name)
            self.phase_lbls.append(l); self.phase_row.add(l)
        self.phase_row.setVisible(False)
        pb.addWidget(self.phase_row, 0)
        self.scanline = ScanBand(self.road_panel, self.theme['sec'])
        self._scan_anim = QPropertyAnimation(self.scanline, b"pos", self)
        self._scan_anim.setDuration(6200); self._scan_anim.setLoopCount(-1)
        self._scan_anim.setEasingCurve(QEasingCurve.Linear)
        pv.addWidget(pbody, 1)
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
        # -- 审阅操作(留在 gresult →「审阅」页):灰尘修复 · 按评分优化 · 对比 · 撤销 · 重新评分 --
        rbtn = FlowBar(hspace=8, vspace=7); rbtn.setObjectName("rowbg")
        self.btn_dust = QPushButton(t("🩹 灰尘修复")); self.btn_dust.setCheckable(True)
        self.btn_dust.setCursor(Qt.PointingHandCursor)
        self.btn_dust.setToolTip(t("点亮后,在预览上按住拖出一个圆框住灰尘 → 出现『应用修复』按钮(所有配色档一起修)"))
        self.btn_dust.clicked.connect(self._toggle_dust_mode)
        self.btn_dust_apply = QPushButton(t("✓ 应用修复")); self.btn_dust_apply.setObjectName("primary")
        self.btn_dust_apply.setCursor(Qt.PointingHandCursor)
        self.btn_dust_apply.setToolTip(t("对画好的圆做人工平场(也可直接在圆上双击)"))
        self.btn_dust_apply.clicked.connect(self._apply_dust_circle)
        self.btn_dust_apply.setVisible(False)
        self.btn_scorefix = QPushButton(t("🔧 按评分优化")); self.btn_scorefix.setObjectName("seg")
        self.btn_scorefix.setCursor(Qt.PointingHandCursor)
        self.btn_scorefix.setToolTip(t("按确定性质量指标一键补救(纯 numpy,秒出):背景偏色→中和;星点发闷→星蒙版提饱和。\n"
                                     "只动该动的、不重跑管线,存为新成片并刷新指标。"))
        self.btn_scorefix.clicked.connect(self._apply_score_remedy)
        self.btn_scorefix.setVisible(False)          # 有可修的确定性问题时才显示(_show_scores 控制)
        self.btn_rescore = QPushButton(t("🔄 重新评分")); self.btn_rescore.setObjectName("seg")
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
        self.btn_dse_file = QPushButton(t("🌑 加暗结构")); self.btn_dse_file.setCursor(Qt.PointingHandCursor)
        self.btn_dse_file.setToolTip(t("对任意已完成成片(含旧图)补做 DSE 暗结构强化:加深暗尘/暗带、提升立体感。\n"
                                     "选图 → 自动用 PI 处理(runner 不在线会自动拉起)→ 存为 <名>_DSE.png,不必重跑管线。"))
        self.btn_dse_file.clicked.connect(self._dse_a_file)
        self.btn_export = QPushButton(t("↓ 导出成片")); self.btn_export.setObjectName("primary")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._export)
        ebtn.add(self.btn_dse_file); ebtn.add(self.btn_show); ebtn.add(self.btn_export)
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
        self.btn_pause = QPushButton(t("⏸ 暂停介入")); self.btn_pause.setObjectName("seg")
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
        # 顺序 = 「▶ 开始处理 / 处理中…」在左、「⏸ 暂停介入」「■ 中止」在右;未处理时后两者隐藏不占位。
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

        top = self._make_topbar()
        self._header.setParent(None)
        nav = self._make_nav()

        # ---- 配置屏:标题 + 流程卡 + 给素材卡(gin) + 下一步 ----
        setup = QWidget(); setup.setObjectName("screen")
        sv = QVBoxLayout(setup); sv.setContentsMargins(16, 0, 16, 2); sv.setSpacing(10)
        _h2s = self._trl("配置", "h2"); sv.addWidget(_h2s)
        _lds = self._trl("选择处理流程,再指定素材与设备。这一步决定整条管线。", "lead")
        _lds.setWordWrap(True); sv.addWidget(_lds)
        _eb1 = self._trl("选择流程", "eyebrow"); sv.addSpacing(4); sv.addWidget(_eb1)
        sv.addWidget(self._build_flow_cards())
        _eb2 = self._trl("素材 · 设备 · 输出", "eyebrow"); sv.addSpacing(4); sv.addWidget(_eb2)
        sv.addWidget(self._gin)
        _nr = QHBoxLayout(); _nr.addStretch(1)
        _nextb = QPushButton(); _nextb.setObjectName("primary"); _nextb.setCursor(Qt.PointingHandCursor)
        self._tr(_nextb, "下一步:处理 →")
        _nextb.clicked.connect(lambda: self._go_stage(2)); _nr.addWidget(_nextb, 0)
        sv.addSpacing(4); sv.addLayout(_nr); sv.addStretch(1)

        # ---- 处理屏:split(左 参数gp + run/pause/abort + 进度 + 日志 | 右 取景器 slot) ----
        process = QWidget(); process.setObjectName("screen")
        prg = QHBoxLayout(process); prg.setContentsMargins(16, 0, 16, 2); prg.setSpacing(16)
        pleft = QWidget(); pleft.setObjectName("rowbg")
        plv = QVBoxLayout(pleft); plv.setContentsMargins(0, 0, 0, 0); plv.setSpacing(10)
        _ebp = self._trl("参数", "eyebrow"); plv.addWidget(_ebp)
        plv.addWidget(self._gp)                          # 调参数卡 → 处理屏左侧
        _runrow = FlowBar(hspace=8, vspace=8); _runrow.setObjectName("rowbg")
        for b in (self.btn_run, self.btn_pause, self.btn_abort):
            _runrow.add(b)
        plv.addWidget(_runrow, 0)
        plv.addWidget(self.gprog, 0)
        plv.addWidget(self.log, 0)                       # 运行日志
        plv.addStretch(1)
        _pleft_scroll = self._screen_scroll(pleft)
        _pleft_scroll.setMinimumWidth(380); _pleft_scroll.setMaximumWidth(560)
        self._proc_view = QWidget(); self._proc_view.setObjectName("rowbg")
        self._proc_view_l = QVBoxLayout(self._proc_view); self._proc_view_l.setContentsMargins(0, 0, 0, 0)
        prg.addWidget(_pleft_scroll, 0)
        prg.addWidget(self._proc_view, 1)

        # ---- 审阅屏:取景器 slot(上) + gresult(下) ----
        review = QWidget(); review.setObjectName("screen")
        rvv = QVBoxLayout(review); rvv.setContentsMargins(16, 0, 16, 2); rvv.setSpacing(11)
        self._rev_view = QWidget(); self._rev_view.setObjectName("rowbg")
        self._rev_view_l = QVBoxLayout(self._rev_view); self._rev_view_l.setContentsMargins(0, 0, 0, 0)
        rvv.addWidget(self._rev_view, 0)
        rvv.addWidget(self._build_score_panels(), 0)   # 评审 + 实测指标 双面板
        self.lbl_review_empty = self._trl("还没有成片。到「处理」跑完流程后,评审与实测指标会出现在这里。", "lead")
        self.lbl_review_empty.setWordWrap(True)
        rvv.addWidget(self.lbl_review_empty)
        rvv.addWidget(self.gresult, 0)
        rvv.addStretch(1)

        # ---- 导出屏:左 成片预览 + 右 格式/附件/导出(用户 2026-09-04:导出屏内容少,补图像预览)----
        export = QWidget(); export.setObjectName("screen")
        exv = QVBoxLayout(export); exv.setContentsMargins(16, 0, 16, 2); exv.setSpacing(10)
        _h2e = self._trl("导出", "h2"); exv.addWidget(_h2e)
        _lde = self._trl("选择格式与附件,导出到项目输出目录。", "lead"); _lde.setWordWrap(True)
        exv.addWidget(_lde)
        _exp_split = QHBoxLayout(); _exp_split.setSpacing(16)
        # 左:成片预览(独立轻量取景器,不占用处理/审阅复用的 _pcard;进导出屏时刷新)
        _exp_prev_card = QFrame(); _exp_prev_card.setObjectName("card")
        _epc = QVBoxLayout(_exp_prev_card); _epc.setContentsMargins(12, 12, 12, 12); _epc.setSpacing(8)
        _epc.addWidget(self._trl("成片预览", "eyebrow"))
        self.export_preview = QLabel(); self.export_preview.setObjectName("exportprev")
        self.export_preview.setAlignment(Qt.AlignCenter); self.export_preview.setMinimumSize(320, 320)
        self._tr(self.export_preview, "成片就绪后在此预览")
        _epc.addWidget(self.export_preview, 1)
        _exp_split.addWidget(_exp_prev_card, 1)
        # 右:格式/附件/导出
        _exp_ctrl = QWidget(); _exp_ctrl.setObjectName("rowbg"); _exp_ctrl.setMaximumWidth(430)
        _ecv = QVBoxLayout(_exp_ctrl); _ecv.setContentsMargins(0, 0, 0, 0); _ecv.setSpacing(10)
        self.lbl_export_empty = self._trl("成片就绪后,在此选择格式并导出(先到「处理」跑完流程)。", "lead")
        self.lbl_export_empty.setWordWrap(True)
        _ecv.addWidget(self.lbl_export_empty)
        _ecv.addWidget(self.export_panel, 0)
        _ecv.addStretch(1)
        _exp_split.addWidget(_exp_ctrl, 0)
        exv.addLayout(_exp_split, 1)

        home = self._build_home()

        # ---- 屏栈 ----
        self.screen_stack = QStackedWidget()
        self._screens = [home, self._screen_scroll(setup), process,
                         self._screen_scroll(review), self._screen_scroll(export)]
        for pg in self._screens:
            self.screen_stack.addWidget(pg)

        # 预览初始挂到处理屏取景器;把 pcard 从旧右列取出,旧空容器弃用
        self._mount_preview(self._proc_view_l)
        self._rightw.setParent(None); self._leftw.setParent(None)
        self._progw.setParent(None); self._bodyw.setParent(None); self._actionbar.setParent(None)

        footer = self._make_footer()

        # ---- 顶层装配:顶栏 + 发丝线 + 阶段导航 + 屏栈 + 页脚 ----
        outer.addWidget(top, 0)
        _hair2 = QFrame(); _hair2.setObjectName("hairline"); _hair2.setFixedHeight(2)
        outer.addWidget(_hair2, 0)
        outer.addWidget(nav, 0)
        outer.addWidget(self.screen_stack, 1)
        outer.addWidget(footer, 0)

        # 登记 _build 创建的关键 CTA / 格式项做 i18n(chrome-first;深层参数行/tooltip 暂留中文)
        for _b, _zh in [(self.btn_run, "▶ 开始处理"), (self.btn_pause, "⏸ 暂停介入"),
                        (self.btn_abort, "■ 中止"), (self.btn_export, "↓ 导出成片"),
                        (self.btn_show, "在文件夹显示"), (self.btn_dse_file, "🌑 加暗结构"),
                        (self.btn_release, "释放 PixInsight"), (self.btn_cfg, "配置…"),
                        (self.btn_deps, "插件体检"), (self.btn_reload, "↻ 重载 runner"),
                        (self.btn_dumphist, "导出历史"), (self.chk_starless, "去星星云·JPG"),
                        (self.chk_export_stars, "纯星点·PNG"), (self.chk_annotate, "标注 TXT"),
                        (self.btn_to_export, "下一步:导出 →")]:
            if _b is not None:
                self._tr(_b, _zh)

        self._stage_idx = -1
        self._go_stage(0)           # 落在项目库

    def _make_topbar(self):
        """顶栏:呼吸标记 + 品牌字 + 版本 + 项目名chip/已保存 + 语言 + 状态 + 主题 + 设置。
        复用已建的 banner / runner_pill / btn_theme(reparent 进来)。"""
        top = QFrame(); top.setObjectName("headerbar")
        th = QHBoxLayout(top); th.setContentsMargins(16, 9, 13, 9); th.setSpacing(10)
        self.mark = BreathMark(22); self._anims.append(self.mark._anim)
        th.addWidget(self.mark, 0, Qt.AlignVCenter)
        th.addWidget(self.banner, 0, Qt.AlignVCenter)              # 品牌字(GradientLabel)
        _ver = QLabel("v0.9"); _ver.setObjectName("ver")
        th.addWidget(_ver, 0, Qt.AlignVCenter)
        # 项目名 chip(名 + 已保存指示 + 保存键)
        chip = QFrame(); chip.setObjectName("projchip")
        ch = QHBoxLayout(chip); ch.setContentsMargins(9, 3, 7, 3); ch.setSpacing(7)
        self.ed_project = QLineEdit(); self.ed_project.setObjectName("projname")
        self.ed_project.setMaximumWidth(150)
        self._tr(self.ed_project, "未命名项目", "setPlaceholderText")
        self.ed_project.setToolTip(t("项目名(导出文件名 / .ttproj 工程名)"))
        self.ed_project.textEdited.connect(lambda _t: self._mark_dirty())
        self.lbl_saved = QLabel(t("未保存")); self.lbl_saved.setObjectName("savedtag")
        self.lbl_saved.setProperty("dirty", True)
        self.btn_save = QToolButton(); self.btn_save.setText("💾"); self.btn_save.setObjectName("gear")
        self.btn_save.setToolTip(t("保存 .ttproj 工程(配置 + 成片 + 调色态)"))
        self.btn_save.setCursor(Qt.PointingHandCursor); self.btn_save.clicked.connect(self._save_project)
        ch.addWidget(self.ed_project, 0); ch.addWidget(self.lbl_saved, 0); ch.addWidget(self.btn_save, 0)
        th.addWidget(chip, 0, Qt.AlignVCenter)
        th.addStretch(1)
        # 语言切换 中/EN
        langbox = QFrame(); langbox.setObjectName("langbox")
        lb = QHBoxLayout(langbox); lb.setContentsMargins(0, 0, 0, 0); lb.setSpacing(0)
        self.lang_group = QButtonGroup(self); self.lang_group.setExclusive(True)
        self.lang_btns = {}
        for code, label in (("zh", "中"), ("en", "EN")):
            b = QPushButton(label); b.setObjectName("langseg"); b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, c=code: self._set_lang(c))
            self.lang_group.addButton(b); self.lang_btns[code] = b; lb.addWidget(b)
        _cur = config.get_setting("ui.lang", config.get_setting("lang", "zh")) or "zh"
        self.lang_btns.get(_cur, self.lang_btns["zh"]).setChecked(True)
        th.addWidget(langbox, 0, Qt.AlignVCenter)
        self.runner_pill.setParent(None)
        th.addWidget(self.runner_pill, 0, Qt.AlignVCenter)
        self.btn_theme.setParent(None); self.btn_theme.setText("◑")
        th.addWidget(self.btn_theme, 0, Qt.AlignVCenter)
        gear = QToolButton(); gear.setText("⚙"); gear.setObjectName("gear")
        gear.setCursor(Qt.PointingHandCursor); gear.setToolTip(t("设置(PixInsight 路径 / LLM 评委 / 后端…)"))
        gear.clicked.connect(self._open_settings)
        th.addWidget(gear, 0, Qt.AlignVCenter)
        return top

    def _make_nav(self):
        """阶段导航:项目库 · 配置 · 处理 · 审阅 · 导出;激活态 green→blue 下划线(SlideIndicator)。"""
        navbar = QFrame(); navbar.setObjectName("navbar")
        nb = QHBoxLayout(navbar); nb.setContentsMargins(16, 0, 16, 0); nb.setSpacing(1)
        holder = FlowBar(hspace=1, vspace=0); holder.setObjectName("rowbg")
        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        self.nav_btns = []
        for i, (ix, name) in enumerate([("◈", "项目库"), ("1", "配置"), ("2", "处理"),
                                        ("3", "审阅"), ("4", "导出")]):
            b = QPushButton(f"{ix} · {t(name)}"); b.setObjectName("nav"); b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, idx=i: self._go_stage(idx))
            self.nav_group.addButton(b, i); self.nav_btns.append(b); holder.add(b)
            self._nav_meta.append((b, ix, name))   # 组合串「ix · 名」i18n 重建用
        self.stage_ind = SlideIndicator(holder, 2); self.stage_ind.hide()
        nb.addWidget(holder, 0, Qt.AlignVCenter); nb.addStretch(1)
        return navbar

    def _make_footer(self):
        """精简页脚:维护工具(复用已建的 _bar_sec:释放/配置/清理/体检/重载/历史)。"""
        footer = QFrame(); footer.setObjectName("footerbar")
        fl = QHBoxLayout(footer); fl.setContentsMargins(16, 7, 16, 8); fl.setSpacing(8)
        self._bar_sec.setParent(None)
        fl.addWidget(self._bar_sec, 1)
        return footer

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
            cl = QVBoxLayout(card); cl.setContentsMargins(14, 13, 13, 13); cl.setSpacing(3)
            fi = QLabel(badge); fi.setFixedSize(30, 30); fi.setAlignment(Qt.AlignCenter)
            fi.setStyleSheet(f"background:rgba({r},{gg},{bb},30); color:{sig}; border-radius:8px; "
                             f"font-family:{MONO_STACK}; font-weight:600; font-size:12px;")
            tick = QLabel("✓"); tick.setObjectName("flowtick"); tick.setVisible(False)
            trow = QHBoxLayout(); trow.setContentsMargins(0, 0, 0, 0)
            trow.addWidget(fi, 0); trow.addStretch(1); trow.addWidget(tick, 0, Qt.AlignTop)
            nm = self._trl(name, "flowname")
            ds = self._trl(desc, "flowdesc"); ds.setWordWrap(True)
            cl.addLayout(trow); cl.addWidget(nm); cl.addWidget(ds)
            card.clicked.connect(lambda idx=i: self._pick_flow(idx))
            g.addWidget(card, 0, i); g.setColumnStretch(i, 1)
            self.flow_cards.append((i, card, tick))
        return wrap

    def _build_score_panels(self):
        """审阅屏双面板:成片评审(LLM 大分 + 3 条 green→blue 评分条)+ 实测指标(numpy,数值蓝)。"""
        wrap = QWidget(); wrap.setObjectName("rowbg")
        g = QGridLayout(wrap); g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12); g.setVerticalSpacing(12)
        # 评审 panel
        pv = QFrame(); pv.setObjectName("panel")
        pvl = QVBoxLayout(pv); pvl.setContentsMargins(15, 14, 15, 15); pvl.setSpacing(11)
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
        g.addWidget(pv, 0, 0)
        # 实测指标 panel
        pm = QFrame(); pm.setObjectName("panel")
        pml = QVBoxLayout(pm); pml.setContentsMargins(15, 14, 15, 15); pml.setSpacing(11)
        h2 = QHBoxLayout(); t2 = self._trl("实测指标", "paneltitle")
        v2 = self._trl("确定性 · numpy", "panelvia")
        h2.addWidget(t2, 0); h2.addStretch(1); h2.addWidget(v2, 0); pml.addLayout(h2)
        self.metric_rows = {}
        for key, label in (("s_star", "星点饱和度"), ("bg_s", "背景中性"), ("bg_level", "背景亮度")):
            row = QHBoxLayout(); row.setSpacing(9)
            dot = QLabel(); dot.setFixedSize(8, 8)
            klab = self._trl(label, "metrickey")
            val = QLabel("—"); val.setObjectName("metricval")
            tag = QLabel(""); tag.setObjectName("metrictag")
            row.addWidget(dot, 0); row.addWidget(klab, 1); row.addWidget(val, 0); row.addWidget(tag, 0)
            pml.addLayout(row); self.metric_rows[key] = (dot, val, tag)
        pml.addStretch(1)
        g.addWidget(pm, 0, 1)
        g.setColumnStretch(0, 11); g.setColumnStretch(1, 10)
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
        for b, ix, name in getattr(self, "_nav_meta", []):
            try:
                b.setText(f"{ix} · {t(name)}")
            except Exception:
                pass
        if hasattr(self, "lbl_saved"):     # 动态存档标(未/已保存)按当前状态重译
            self.lbl_saved.setText(t("已保存" if not getattr(self, "_proj_dirty", True) else "未保存"))
        if hasattr(self, "_home_grid"):    # 项目库卡片(含「新建项目」)随语言重建
            self._refresh_home()
        if hasattr(self, "road_rows"):     # 流程路线卡(处理/审阅空态)随语言重绘
            try: self._paint_roadmap()
            except Exception: pass
        QTimer.singleShot(0, self._sync_indicators)

    def _mark_dirty(self):
        self._proj_dirty = True
        if hasattr(self, "lbl_saved"):
            self.lbl_saved.setText(t("未保存")); self.lbl_saved.setProperty("dirty", True)
            self.lbl_saved.style().unpolish(self.lbl_saved); self.lbl_saved.style().polish(self.lbl_saved)

    def _mark_saved(self):
        self._proj_dirty = False
        if hasattr(self, "lbl_saved"):
            self.lbl_saved.setText(t("已保存")); self.lbl_saved.setProperty("dirty", False)
            self.lbl_saved.style().unpolish(self.lbl_saved); self.lbl_saved.style().polish(self.lbl_saved)

    def _projects_dir(self):
        return config.PIPELINE_DIR / "_projects"

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
        """项目库屏:标题 + 打开/新建 + 最近工程卡片网格(缩略图 + 流程签名色标签)。"""
        page = QWidget(); page.setObjectName("screen")
        v = QVBoxLayout(page); v.setContentsMargins(16, 0, 16, 2); v.setSpacing(12)
        head = QHBoxLayout()
        col = QVBoxLayout(); col.setSpacing(2)
        h2 = self._trl("项目", "h2")
        lead = self._trl("继续最近的工程,或新建 / 打开一个 .ttproj 工程文件", "lead")
        col.addWidget(h2); col.addWidget(lead)
        head.addLayout(col, 1)
        openb = QPushButton(); openb.setCursor(Qt.PointingHandCursor); self._tr(openb, "打开工程")
        openb.clicked.connect(self._open_project_dialog)
        newb = QPushButton(); newb.setObjectName("primary"); newb.setCursor(Qt.PointingHandCursor)
        self._tr(newb, "＋ 新建项目")
        newb.clicked.connect(self._new_project)
        head.addWidget(openb, 0, Qt.AlignVCenter); head.addWidget(newb, 0, Qt.AlignVCenter)
        v.addLayout(head)
        gridwrap = QWidget(); gridwrap.setObjectName("rowbg")
        self._home_grid = QGridLayout(gridwrap); self._home_grid.setContentsMargins(0, 0, 0, 0)
        self._home_grid.setHorizontalSpacing(13); self._home_grid.setVerticalSpacing(13)
        v.addWidget(self._screen_scroll(gridwrap), 1)
        self._refresh_home()
        return page

    def _refresh_home(self):
        """重建项目库卡片网格(3 列;末尾一张虚线『新建』卡)。"""
        if not hasattr(self, "_home_grid"):
            return
        while self._home_grid.count():
            it = self._home_grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
        import json as _json
        import time as _t
        cells = []
        for p in self._list_projects():
            meta = {}
            try:
                meta = _json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
            cells.append(("proj", p, meta))
        cells.append(("new", None, None))
        cols = 3
        for idx, (kind, p, meta) in enumerate(cells):
            r, c = divmod(idx, cols)
            if kind == "new":
                card = ClickFrame(); card.setObjectName("projcard_new")
                cl = QVBoxLayout(card); cl.setContentsMargins(14, 22, 14, 22); cl.setSpacing(6)
                cl.setAlignment(Qt.AlignCenter)
                plus = QLabel("＋"); plus.setAlignment(Qt.AlignCenter)
                plus.setStyleSheet("font-size:26px; color:palette(mid);")
                lab = QLabel(t("新建项目")); lab.setObjectName("lead"); lab.setAlignment(Qt.AlignCenter)
                cl.addWidget(plus); cl.addWidget(lab)
                card.clicked.connect(self._new_project)
                self._home_grid.addWidget(card, r, c)
                continue
            flow = (meta.get("flow") or "rgb"); sig = FLOW_SIG.get(flow, "#C6D0DC")
            card = ClickFrame(); card.setObjectName("projcard")
            cl = QVBoxLayout(card); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
            thumb = QLabel(); thumb.setFixedHeight(94); thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet("background:#05070A; border-top-left-radius:11px; border-top-right-radius:11px;")
            tp = meta.get("thumb") or ""
            if tp and Path(tp).exists():
                pm = QPixmap(tp)
                if not pm.isNull():
                    thumb.setPixmap(pm.scaledToHeight(94, Qt.SmoothTransformation))
            metaw = QWidget(); metaw.setObjectName("rowbg")
            mv = QVBoxLayout(metaw); mv.setContentsMargins(12, 10, 12, 11); mv.setSpacing(5)
            nm = QLabel(meta.get("name") or p.stem); nm.setObjectName("projname_c")
            row = QHBoxLayout(); row.setSpacing(8)
            dt = QLabel(_t.strftime("%Y-%m-%d", _t.localtime(p.stat().st_mtime))); dt.setObjectName("projmeta")
            tag = QLabel(flow.upper())
            tag.setStyleSheet(f"color:{sig}; border:1px solid {sig}; border-radius:20px; padding:0 7px; "
                              f"font-family:{MONO_STACK}; font-size:10px;")
            tt = meta.get("target_type") or ""
            row.addWidget(dt, 0); row.addWidget(tag, 0)
            if tt:
                tl = QLabel(tt); tl.setObjectName("projmeta"); row.addWidget(tl, 0)
            row.addStretch(1)
            mv.addWidget(nm); mv.addLayout(row)
            cl.addWidget(thumb); cl.addWidget(metaw)
            card.clicked.connect(lambda path=str(p): self._open_project(path))
            self._home_grid.addWidget(card, r, c)
        for c in range(cols):
            self._home_grid.setColumnStretch(c, 1)
        self._home_grid.setRowStretch((len(cells) + cols - 1) // cols, 1)

    def _go_stage(self, idx):
        """切到某屏(0项目库/1配置/2处理/3审阅/4导出);处理·审阅挂载唯一预览取景器。"""
        if not hasattr(self, "screen_stack"):
            return
        self._stage_idx = idx
        for i, b in enumerate(self.nav_btns):
            b.setChecked(i == idx)
        if idx == 2:
            self._mount_preview(self._proc_view_l)
        elif idx == 3:
            self._mount_preview(self._rev_view_l)
        elif idx == 4:
            QTimer.singleShot(0, self._refresh_export_preview)   # 布局落定后再缩放填图
        self.screen_stack.setCurrentIndex(idx)
        self._fade_screen(self._screens[idx])
        QTimer.singleShot(0, self._sync_indicators)   # 重新对位 stage_ind(green→blue 下划线)

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
        self.export_preview.setPixmap(pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _open_project_dialog(self):
        fn, _ = QFileDialog.getOpenFileName(self, t("打开工程"), str(self._projects_dir()),
                                            t("TTAstroPiLot 工程 (*.ttproj)"))
        if fn:
            self._open_project(fn)

    def _new_project(self):
        """新建:清项目名,进入「配置」屏(参数保持当前默认;真正的重置/从工程恢复留待 .ttproj 阶段)。"""
        self.ed_project.setText(""); self._proj_path = ""   # 新项目还没有落盘路径 → 首次保存会问位置
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
        try:
            self._apply_project_state(data.get("state") or data)   # 兼容旧最小工程(顶层字段)
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
    _PROJ_LINES = ("ed_input", "ed_exportdir", "ed_ha_dir")
    _PROJ_SPINS = ("sp_ghs", "sp_sat", "sp_ha", "sp_core", "sp_crop", "sp_ms", "sp_timeout")
    _PROJ_COMBOS = ("cb_palette", "cb_zpreset", "cb_rgbpreset", "cb_bgextract", "cb_rgbreveal",
                    "cb_glow", "cb_hapreset", "cb_hoopreset", "cb_dust", "cb_grade", "cb_dse")
    _PROJ_CHECKS = ("chk_stars", "chk_detrail", "chk_stretch_judge", "chk_reveal", "chk_lhe",
                    "chk_zeropi", "chk_zeropi_rgb", "chk_zeropi_hoo", "chk_release",
                    "chk_xisf", "chk_png", "chk_jpg", "chk_starless", "chk_export_stars", "chk_annotate")

    def _collect_project_state(self):
        """把当前 config(全控件)+ 成片结果 + 调色态收进一个可 JSON 化的 dict。"""
        st = {
            "flow": self.FLOWS[getattr(self, "flow_idx", 0)][0],
            "input_mode": self._input_mode,
            "stop_key": self.STOPS[self.cb_stop.currentIndex()][0] if hasattr(self, "cb_stop") else "final",
            "jpgq": self.sl_jpgq.value() if hasattr(self, "sl_jpgq") else 95,
            "target": self.ed_target.text().strip() if hasattr(self, "ed_target") else "",
            "lines": {k: getattr(self, k).text() for k in self._PROJ_LINES if hasattr(self, k)},
            "spins": {k: getattr(self, k).value() for k in self._PROJ_SPINS if hasattr(self, k)},
            "combos": {k: getattr(self, k).currentIndex() for k in self._PROJ_COMBOS if hasattr(self, k)},
            "checks": {k: getattr(self, k).isChecked() for k in self._PROJ_CHECKS if hasattr(self, k)},
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

    def _apply_project_state(self, st):
        """把 _collect_project_state 的 dict 恢复到控件/预览(尽力而为,缺控件跳过)。"""
        flow = st.get("flow", "rgb")
        for i, (k, _lbl) in enumerate(self.FLOWS):
            if k == flow:
                self._select_flow(i); self._sync_flow_cards(); break
        try:
            self._select_input_mode(int(st.get("input_mode", 0)))
        except Exception:
            pass
        for k, v in (st.get("lines") or {}).items():
            if hasattr(self, k):
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

    def _save_project(self, save_as=False):
        """保存 .ttproj:完整 config + 成片结果 + 调色态(可从项目库载入直接续处理,不重跑)。
        首次保存(或『另存为』)弹**选择保存位置**对话框,记住路径;之后直接覆盖同一文件。"""
        import json
        name = (self.ed_project.text() or "").strip() or (self._guess_target() or "未命名项目")
        self.ed_project.setText(name)
        safe = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "未命名项目"
        # 决定落盘路径:已有记住的路径且非『另存为』→ 直接覆盖;否则弹「选择保存位置」
        target = self._proj_path
        if save_as or not target:
            self._projects_dir().mkdir(parents=True, exist_ok=True)   # 默认目录先备好
            default = str((Path(self._proj_path).parent if self._proj_path else self._projects_dir()) / f"{safe}.ttproj")
            fn, _ = QFileDialog.getSaveFileName(self, t("保存工程 · 选择位置"), default,
                                                t("TTAstroPiLot 工程 (*.ttproj)"))
            if not fn:
                return                                               # 用户取消 → 不保存
            if not fn.lower().endswith(".ttproj"):
                fn += ".ttproj"
            target = fn
        try:
            data = {
                "schema": "ttproj/0.2",
                "name": name,
                "flow": self.FLOWS[getattr(self, "flow_idx", 0)][0],   # 顶层留一份给项目库卡片标签
                "thumb": self._final_png or "",
                "target_type": self._guess_target() or "",
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "state": self._collect_project_state(),
            }
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            self._proj_path = str(Path(target).resolve())
            self._add_recent(self._proj_path)
            self._append(f"[项目] 已保存 → {self._proj_path}(完整配置 + 成片 + 调色态)")
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
            btn.setText(("▾  %s · %s" if on else "▸  %s · %s") % (title, note))

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
            # 选中态药丸:**纯色 accent 平填充**,无描边、无内阴影渐变(用户嫌渐变+文字投影不好看 → 扁平化)
            self.mode_ind.set_colors(p['accent'], None, None, inner=False)
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
                self.scanline.set_color(p['sec'])
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

    def _set_preview_pixmap(self, pm):
        """收下原图,按预览视口**等比缩放到最大**(完整呈现 + 尽量填满,绝不裁切)。"""
        self._pm_raw = pm
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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._rescale_preview)
        QTimer.singleShot(0, self._sync_indicators)
        QTimer.singleShot(0, self._sync_caret)

    def _sync_param_sections(self):
        """流程切换后的视觉同步:LRGB 专用整块显隐、折叠高度重算、路线图重绘。"""
        kind = self.FLOWS[getattr(self, "flow_idx", 0)][0]
        if hasattr(self, "lrgb_wrap"):
            self.lrgb_wrap.setVisible(kind == "lrgb")
        if hasattr(self, "lbl_param_count"):
            shown = sum(1 for k, r in self._param_rows.items() if r.isVisible())
            self.lbl_param_count.setText(t("{} 项 · 已按流程过滤").format(shown))
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
        # 设备类型:决定校准场是必填还是可选(智能望远镜常缺校准场)。见 STACK_DEVICES。
        devrow = FlowBar(hspace=6, vspace=6); devrow.setObjectName("rowbg")
        dlab = QLabel(t("设备")); dlab.setObjectName("plabel"); dlab.setMinimumWidth(48)
        devrow.add(dlab)
        self.dev_btns = {}
        self._stack_device = "osc"
        for k, label, _pol, _hint in STACK_DEVICES:
            # segdev:与 #seg 同底,但**选中态自带实心绿背景**(设备行无 SlideIndicator 垫绿药丸,
            #   若用 #seg 会是"透明底+深色字"=看不见,用户 2026-09-03 反馈)。不需滑动动画。
            b = QPushButton(label); b.setObjectName("segdev"); b.setCheckable(True)
            b.setChecked(k == "osc"); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, key=k: self._select_stack_device(key))
            self.dev_btns[k] = b; devrow.add(b)
        v.addWidget(devrow)
        self.lbl_stack_dev_hint = QLabel(STACK_DEV_MAP["osc"][2])
        self.lbl_stack_dev_hint.setObjectName("sub"); self.lbl_stack_dev_hint.setWordWrap(True)
        v.addWidget(self.lbl_stack_dev_hint)
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
        self.ed_target = QLineEdit(); self.ed_target.setPlaceholderText(t("项目名 如 260710-260724_2600mc_IC1396"))
        lt = QLabel(t("项目名")); lt.setObjectName("plabel"); lt.setMinimumWidth(48)
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
        ed_f = QLineEdit(); ed_f.setPlaceholderText("通道平场目录" if mono else "平场目录")
        bf = QToolButton(); bf.setText(t("平场…")); bf.clicked.connect(lambda: self._pick_dir(ed_f))
        rm = QToolButton(); rm.setText("✕"); rm.setToolTip(t("删除这一晚"))
        rm.clicked.connect(lambda: self._remove_night_row(roww))
        for wdg in (idx_lab, ed_l, bl, ed_f, bf, rm):
            h.addWidget(wdg)
        h.setStretch(1, 2); h.setStretch(3, 2)
        self.night_rows.append({"w": roww, "idx": idx_lab, "light": ed_l, "flat": ed_f})
        self.nights_box.addWidget(roww)
        self._renumber_nights()

    def _remove_night_row(self, roww):
        if len(self.night_rows) <= 1:
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

    def _pick_dir(self, ed):
        p = QFileDialog.getExistingDirectory(self, t("选择目录"))
        if p:
            ed.setText(p.replace("\\", "/"))

    def _pick_file(self, ed):
        p, _ = QFileDialog.getOpenFileName(self, t("选择文件"), "", t("图像 (*.xisf *.fit *.fits)"))
        if p:
            ed.setText(p.replace("\\", "/"))

    def _select_input_mode(self, idx):
        self._input_mode = idx
        self.in_mode_btns[idx].setChecked(True)
        self.pg_single.setVisible(idx < 2)
        self.pg_raw.setVisible(idx == 2)
        self.chk_detrail.setVisible(idx in (1, 2))   # 仅从子帧整合时可去线
        if idx == 0:
            self.ed_input.setPlaceholderText(t("已叠加母版 .xisf / .fit / .fits"))
            self.lbl_input_hint.setText(t("直接后期一张已叠加好的主图。"))
        elif idx == 1:
            self.ed_input.setPlaceholderText(t("registered 对齐子帧目录(将自动整合)"))
            self.lbl_input_hint.setText(t("整合目录内全部对齐子帧后再后期(多通道 LRGB 也用此)。"))
        if hasattr(self, "detrail_row"):
            self.detrail_row.setVisible(idx in (1, 2))
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
        d = QFileDialog.getExistingDirectory(self, t("选择素材文件夹(自动识别亮/暗场·机内成片)"))
        if not d:
            return
        d = d.replace("\\", "/")
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
                dd = QFileDialog.getExistingDirectory(self, t("选择暗场文件夹"))
                if dd:
                    self.ed_dark.setText(dd.replace("\\", "/"))
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
                # tag = WBPP 自定义滤镜标签,只要"每晚唯一且亮场/平场一致"即可 → 按填了内容的
                # 行序自动生成,不暴露给用户(空行不占号)。
                nights.append({"light": lt, "flat": fl, "tag": f"d{len(nights) + 1}"})
        dark = "" if pol.get("dark") == "skip" else self.ed_dark.text().strip()
        bias = "" if pol.get("bias") == "skip" else self.ed_bias.text().strip()
        return {"nights": nights, "dark": dark, "bias": bias,
                "out_base": self.ed_stackout.text().strip(), "target": self.ed_target.text().strip(),
                "device": dev, "calib_library": self.ed_caliblib.text().strip().replace("\\", "/")}

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
            self.banner.set_colors(self.theme['accent'], self.theme['accent_hi'])  # 品牌字单色信号绿(去青蓝)
        self._sync_indicators()
        self._sync_caret()
        self._apply_button_shadows()       # 按钮浅投影(替代描边)——随主题明暗重设强度
        if hasattr(self, "_glow_fx"):       # 主 CTA 呼吸辉光随主题重设颜色
            for _eff in self._glow_fx:
                _eff.setColor(QColor(self.theme['accent']))

    def _apply_button_shadows(self):
        """给按钮加**浅投影**代替描边(Qt QSS 不支持 box-shadow → 逐控件 QGraphicsDropShadowEffect)。
        平标签 #tab 不加(它本就是无框下划线式);深色主题投影稍重、浅色主题更淡。每次切主题重设,
        setGraphicsEffect 会自动删掉旧 effect(不泄漏)。动态新建的按钮(配色条等)在其构建后另调。"""
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QToolButton
        from PyQt5.QtGui import QColor
        dark = (self.theme is DARK)
        btns = self.findChildren(QPushButton) + self.findChildren(QToolButton)
        cta = (getattr(self, "btn_run", None), getattr(self, "btn_export", None))
        for b in btns:
            if b.objectName() in ("tab", "seg", "segdev"):   # 平标签 + 段控件不加投影(段选中态透明→投影会落到文字上,难看)
                continue
            if b in cta:      # 主 CTA 用会呼吸的信号绿辉光(_init_primary_glow),别被黑投影覆盖
                continue
            eff = QGraphicsDropShadowEffect(b)
            eff.setBlurRadius(15 if dark else 13)
            eff.setOffset(0, 2)
            eff.setColor(QColor(0, 0, 0, 120 if dark else 48))
            b.setGraphicsEffect(eff)

    def _init_primary_glow(self):
        """主 CTA(开始处理 / 导出成片)常驻一层随应用心跳呼吸的信号绿辉光。
        QPropertyAnimation 驱动 QGraphicsDropShadowEffect 的 blurRadius,与状态点/品牌标记同 ~4.6s 拍。"""
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        self._glow_fx = []
        for btn in (getattr(self, "btn_run", None), getattr(self, "btn_export", None)):
            if btn is None:
                continue
            eff = QGraphicsDropShadowEffect(btn)
            eff.setOffset(0, 0)
            eff.setColor(QColor(self.theme['accent']))
            eff.setBlurRadius(16)
            btn.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"blurRadius", self)
            a.setDuration(4600); a.setLoopCount(-1)
            a.setStartValue(12); a.setKeyValueAt(0.5, 30); a.setEndValue(12)
            a.setEasingCurve(QEasingCurve.InOutSine)
            a.start()
            self._glow_fx.append(eff)
            self._anims.append(a)

    def _toggle_theme(self):
        self.theme = LIGHT if self.theme is DARK else DARK
        self._apply_theme()

    # ---------- 流程/参数 ----------
    def _select_flow(self, idx):
        self.flow_btns[idx].setChecked(True); self.flow_idx = idx
        kind = self.FLOWS[idx][0]
        lrgb, rgb, sho, hoo = kind == "lrgb", kind == "rgb", kind == "sho", kind == "hoo"
        multichan = lrgb or sho                     # 多通道:输入=registered 目录
        vis = {"ghs": rgb or lrgb, "sat": rgb or lrgb or sho, "stars": rgb,
               "ha": lrgb, "ms": lrgb, "core": lrgb, "crop": lrgb,
               "palette": sho, "dust": sho, "grade": sho, "dse": sho, "zeropi": sho,
               "zeropi_rgb": rgb, "zeropi_rgb_ha": rgb, "zeropi_rgb_adv": rgb, "zeropi_hoo": hoo,
               "stop": True, "timeout": True}
        for k, r in self._param_rows.items():
            r.setVisible(vis.get(k, True))
        # 交棒点下拉按流程切换(各流程阶段不同)
        if hasattr(self, "cb_stop"):
            self.STOPS = self.STOPS_BY_FLOW.get(kind, self.STOPS_BY_FLOW["rgb"])
            self.cb_stop.blockSignals(True)
            self.cb_stop.clear(); self.cb_stop.addItems([t for _, t in self.STOPS])
            self.cb_stop.setCurrentIndex(0)
            self.cb_stop.blockSignals(False)
        # 原始素材叠加:OSC(RGB/HOO)单主叠加;多通道(LRGB/SHO)= 黑白 per-filter 叠加(设备锁「黑白相机」)。
        self.in_mode_btns[2].setEnabled(True)
        if multichan:
            if self._input_mode == 0:                 # 母版文件模式对多通道无意义 → 切到子帧目录
                self._select_input_mode(1)
            if hasattr(self, "dev_btns"):
                self._select_stack_device("mono")     # 多通道原始叠加固定走黑白 per-filter
        elif hasattr(self, "dev_btns") and getattr(self, "_stack_device", "osc") == "mono":
            self._select_stack_device("osc")          # 回到 OSC 流程 → 设备复位
        self._sync_param_sections()
        self._sync_flow_cards()                       # 配置屏流程卡选中态跟随
        self._mark_dirty()

    def _browse(self):
        # 模式 1(registered 目录)或 LRGB → 选目录;模式 0 → 选母版文件
        want_dir = self._input_mode == 1 or self.FLOWS[self.flow_idx][0] in ("lrgb", "sho")
        if want_dir:
            p = QFileDialog.getExistingDirectory(self, t("选择 registered 目录"))
        else:
            p, _ = QFileDialog.getOpenFileName(self, t("选择主图"), "", t("图像 (*.xisf *.fit *.fits)"))
        if p:
            self.ed_input.setText(p.replace("\\", "/"))

    def _pick_ha_dir(self):
        """选无 PI RGB 的窄带 Ha/OIII master 或子帧目录(可选;填了就 RGB+H/HO)。"""
        start = self.ed_ha_dir.text() or self.ed_input.text() or ""
        p = QFileDialog.getExistingDirectory(self, t("选择双窄带 Ha/OIII master 或子帧目录"), start)
        if p:
            self.ed_ha_dir.setText(p.replace("\\", "/"))

    def _refresh_runner(self):
        # 三态:在线(心跳新)/ 忙·处理中(心跳旧但有在途作业,长任务执行中)/ 未运行。
        #   长任务(WBPP/整合/BXT)执行期 runner 阻塞、心跳变旧,但它活着在忙 → 显示绿色「处理中」
        #   而非灰色「未运行」,别吓唬用户(用户反馈:PI 明明在跑却提示 runner 未运行)。
        st = protocol.runner_status()
        alive = st != "offline"                     # 忙也算「在位」:控制『释放』按钮显隐、冷启动判定
        p = self.theme
        self.lbl_runner.setText({"online": t("runner 在线"), "busy": t("runner 忙·处理中"),
                                 "offline": t("runner 未运行")}[st])
        col = p['accent'] if alive else p['muted']
        self.lbl_runner.setStyleSheet(f"color:{col};font-weight:bold;background:transparent;")
        self.runner_pill.setStyleSheet(
            f"QFrame#statuspill {{ background:{p['accent_soft'] if alive else 'transparent'};"
            f"border:1px solid {p['accent_line'] if alive else p['stroke']};border-radius:14px; }}")
        self.runner_dot.set_state(col, alive)
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
        self.btn_clean.setText(t("清理中间文件(统计中…)"))
        th = _RunScan(self)
        th.result.connect(self._on_run_scan)
        th.finished.connect(th.deleteLater)
        self._scan_thread = th
        th.start()

    def _on_run_scan(self, entries, total):
        self._scan_thread = None          # 结果已到、线程即将 deleteLater → 丢陈旧引用(Qt 父对象仍保活到删除)
        self._run_entries = entries
        self._run_size_total = total
        self.btn_clean.setText(t("清理中间文件") + f"({self._fmt_size(total)})" if total
                               else t("清理中间文件"))
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
        miss = _deps.report(avail, avail_ext)
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
                "reveal": self.chk_reveal.isChecked(),
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
                "ha_dir": self.ed_ha_dir.text().strip(),
                "hapreset": ("galaxy", "vivid")[self.cb_hapreset.currentIndex()],
                "zeropi_hoo": self.chk_zeropi_hoo.isChecked(),
                "hoopreset": ("oiii", "classic")[self.cb_hoopreset.currentIndex()],
                "grade_curve": ("henry_sho" if self.cb_grade.currentIndex() == 1 else None),
                "darkstruct": ("auto", {"amount": 0.5}, {"amount": 0.2}, None)[self.cb_dse.currentIndex()],
                "target": self._guess_target(),
                "raw": self._raw_config() if self._input_mode == 2 else None}

    def _guess_target(self):
        """尽力从输入路径/原始配置猜目标名(喂评委;猜不到留空,评委无参考也能判)。"""
        import re as _re
        if self._input_mode == 2:
            t = self.ed_target.text().strip()
            if t:
                return t
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
        else:
            inp = self.ed_input.text().strip()
            if not inp or not Path(inp).exists():
                QMessageBox.warning(self, t("输入无效"), t("请选择有效的主图或目录。"))
                return
        # 无 PI · Siril 引擎流程:全程零 PixInsight → 不需要 job-runner,跳过 PI 冷启动
        _kind0 = self.FLOWS[self.flow_idx][0]
        _zeropi0 = ((_kind0 == "rgb" and self.chk_zeropi_rgb.isChecked())
                    or (_kind0 == "hoo" and self.chk_zeropi_hoo.isChecked())
                    or (_kind0 == "sho" and self.chk_zeropi.isChecked()))
        # runner 未在线 → 自动冷启动 PI(zero-PI 流程除外);Worker 会先等 runner 就绪再跑。
        if not _zeropi0 and not self._refresh_runner():
            if not config.pixinsight_exe():
                QMessageBox.warning(self, t("未找到 PixInsight"), t("请在『配置』里设置 PixInsight 路径后再开始。"))
                return
            self._append("[准备] runner 未在线 → 自动启动 PixInsight,就绪后开始处理…")
            if not self._launch_pi():
                return
        kind = self.FLOWS[self.flow_idx][0]
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
        self._start_t = time.time(); self._max_phase = -1; self._done_ops = 0
        self._expected = _EXPECTED.get(kind, 16)
        self.bar.setValue(0); self.lbl_eta.setText(t("准备中…"))
        self._end_state = "run"
        self._reveal(self.gprog); self._paint_phases()
        self._pulse.start()
        self.lbl_prog_stage.setText(t("准备中"))
        self.bar_shim.start(); self.run_shim.start()
        self.btn_run.setEnabled(False); self.btn_run.setText(t("处理中…")); self.btn_abort.setVisible(True)
        # 支持随时暂停介入的流程 → 显示暂停按钮(SHO 逐通道 + RGB 逐步;pipeline 层已埋 pause_gate)
        self.btn_pause.setVisible(kind in ("sho", "rgb")); self.btn_pause.setEnabled(True)
        self.btn_pause.setText(t("⏸ 暂停介入"))
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
        self.worker.pause_preview.connect(self._on_pause_preview)
        self.worker.pause_chat.connect(self._on_pause_chat)
        self.worker.deps.connect(self._on_deps_missing)
        self.thread.start()

    def _on_deps_missing(self, miss):
        """首启体检回主线程:缺插件时弹一次引导框(不阻断处理——#4 已自动兜底,后台继续跑)。"""
        try:
            self._show_deps_dialog(list(miss), proactive=True)
        except Exception:
            pass

    def _abort(self):
        pipeline.request_cancel()
        self._append("[中止] 已请求中止,当前步骤后停止…")
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
        self.lbl_pause.setText(t("已暂停 · 当前【{}】。{},或点继续。").format(tag, hint))
        self.btn_p_dust.setChecked(False); self._dust_mode = False
        self._dust_circle = None; self._sync_dust_apply()
        self._stop_pause_think(); self.pause_chat_log.clear()
        self.pause_panel.setVisible(True)
        self.lbl_prevtag.setText(t("已暂停 · {}").format(tag))

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
            pm = QPixmap(preview)
            if not pm.isNull():
                self._set_preview_pixmap(pm)

    def _pause_do_gradient(self):
        if self.worker:
            self._pause_seq = getattr(self, "_pause_seq", 0) + 1
            self.worker.send_pause_cmd({"op": "gradient", "seq": self._pause_seq})

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
        self.btn_pause.setEnabled(True); self.btn_pause.setText(t("⏸ 暂停介入"))
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
            self.lbl_eta.setText(t("已用 {:02d}:{:02d} · 预计剩余 ~{:02d}:{:02d}  ·  步骤 {}/5").format(
                int(el//60), int(el%60), int(rem//60), int(rem%60), min(self._max_phase+1, 5)))

    def _paint_phases(self):
        """阶段着色:已完成=青蓝,进行中=薄荷绿,未开始=灰。横向阶段带与右侧路线图共用。"""
        p = self.theme
        cur = self._max_phase
        for i, l in enumerate(getattr(self, "phase_lbls", [])):
            if i < cur:
                l.setStyleSheet(f"color:{p['sec']};font-weight:bold;"
                                f"border-top:2px solid {p['sec']};padding:6px 4px 0 0;")
            elif i == cur:
                l.setStyleSheet(f"color:{p['accent']};font-weight:bold;"
                                f"border-top:2px solid {p['accent']};padding:6px 4px 0 0;")
            else:
                l.setStyleSheet(f"color:{p['muted']};"
                                f"border-top:2px solid {p['surf2']};padding:6px 4px 0 0;")
        if hasattr(self, "prog_dot"):
            self.prog_dot.set_state(p['accent'], self._end_state == "run")
        self._paint_roadmap()

    def _paint_roadmap(self):
        """右侧空态的流程路线图:按当前流程写阶段说明,按进度点亮。"""
        if not hasattr(self, "road_rows"):
            return
        p = self.theme
        idx = getattr(self, "flow_idx", 0)
        kind, label = self.FLOWS[idx]
        desc = PHASE_DESC.get(kind, PHASE_DESC["rgb"])
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
        self.caret.set_color(self.theme['sec'])
        self.caret.show(); self.caret.raise_()

    def _show_stage_preview(self, path):
        # 处理过程中把每步的阶段效果图显示到右侧预览框(增强参与感)
        try:
            if not path or not Path(path).exists():
                return
            pm = QPixmap(path)
            if pm.isNull():
                return
            self._set_preview_pixmap(pm)
        except Exception:
            pass

    def _finished(self, ok, png, xis, scores):
        self.thread.quit(); self.thread.wait()
        self.thread = None; self.worker = None
        try:
            self._refresh_run_size()           # 本次处理产生的新中间产物 → 重扫,刷新按钮体积
        except Exception:
            pass                               # 体积统计**绝不能**阻断"完成"(曾因陈旧线程引用崩溃卡住 UI)
        self.btn_run.setEnabled(True); self.btn_run.setText(t("▶ 开始处理"))
        self.btn_abort.setVisible(False); self.btn_abort.setEnabled(True)
        self.btn_pause.setVisible(False); self.pause_panel.setVisible(False)
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
                #   评分按钮:有评委+有图就露出「🔄 重新评分」,随时可手动重评(超时/想再评)。
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
        for pal in [p for p in PALETTES if p in self._finals] or list(self._finals):
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

    def _dse_a_file(self):
        """对用户选定的任意成片(含旧图)一键补做 DSE 暗结构强化,不必重跑管线。
        强度取自「暗结构强化 DSE」下拉(默认/更强/更轻);存为 <名>_DSE.png。"""
        start = ""
        try:
            start = str(config.RUN_DIR)
        except Exception:
            pass
        fp, _ = QFileDialog.getOpenFileName(self, t("选择要加暗结构的成片"), start,
                                            t("图像 (*.png *.jpg *.jpeg *.tif *.tiff *.xisf)"))
        if not fp:
            return
        if not self._ensure_runner("暗结构强化"):
            return
        amt = {0: 0.35, 1: 0.5, 2: 0.2, 3: 0.35}.get(self.cb_dse.currentIndex(), 0.35)
        fp = fp.replace("\\", "/")
        p = Path(fp)
        outp = str(p.with_name(p.stem + "_DSE.png")).replace("\\", "/")
        r = {}
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._append(f"[暗结构强化] {p.name} (amount={amt}) 处理中…")
            job = protocol.new_job("darkstruct", input=fp,
                                   params={"layers": 8, "amount": amt, "iterations": 1, "linear": False},
                                   outputs={"image": outp, "preview": outp})
            protocol.submit(job)
            r = protocol.wait_result(job["job_id"], timeout=600)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, t("暗结构强化"), t("失败:{}").format(e)); return
        finally:
            QApplication.restoreOverrideCursor()
        if r.get("status") != "ok":
            QMessageBox.critical(self, t("暗结构强化"), t("失败:{}").format(r.get('error'))); return
        outimg = r.get("image") or outp
        self._append(f"[暗结构强化] 完成 → {outimg}")
        if Path(outimg).exists():
            pm = QPixmap(outimg)
            if not pm.isNull():
                self._set_preview_pixmap(pm)
        QMessageBox.information(self, t("暗结构强化"), t("完成,已保存:\n{}").format(outimg))

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
        自动完成后 & 手动『🔄 重新评分』共用。retries=失败后自动重试次数(自动评分传 2,手动=0):
        自动评分紧接处理结束,系统/服务端还在收尾易瞬态报错,手动重评则秒回 → 用重试抹平。"""
        png = png or self._final_png
        self._score_retries = int(retries)          # 供 _on_llm_score 失败时决定是否自动重试
        self._score_png_cur = str(png) if png else ""
        if not (png and Path(str(png)).exists()):
            self._append("[评委] 没有可评分的成片。"); return
        if not (config.get_setting("llm.provider") or "").strip():
            self._append("[评委] 未配置 LLM(在『配置』里设),无法评分。"); return
        th = getattr(self, "_score_thread", None)
        if th is not None:
            try:
                if th.isRunning():
                    self._append("[评委] 评分进行中,请稍候…"); return
            except RuntimeError:
                self._score_thread = None
        _q = (self._last_scores or {}).get("_quality") or {}
        _ctx = f"{self.FLOWS[self.flow_idx][0]} 成片"
        if _q:
            _ctx += (f";确定性指标 S_star={_q.get('s_star')}(甜区0.30~0.55)"
                     f" 背景中性S={_q.get('bg_s')}(应<0.12) 背景失衡={_q.get('bg_imbalance')}"
                     f" 背景亮度={_q.get('bg_level')} 偏色={_q.get('bg_cast')}")
        self._append("[评委] 后台评分中(不阻塞;评完自动补上)…")
        th = _ScoreThread(str(png), _ctx, self)
        th.result.connect(self._on_llm_score)
        th.finished.connect(th.deleteLater)
        self._score_thread = th
        th.start()

    def _rescore(self):
        """🔄 重新评分:手动再唤起一次 AI 评分(超时/想再评时用)。"""
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
                         f"(已有实测指标,不影响成片;可点『🔄 重新评分』重试)")
            if getattr(self, "btn_rescore", None) is not None:
                self.btn_rescore.setVisible(True)
            return
        merged = {**(self._last_scores or {}), **s}
        self._last_scores = merged
        self._show_scores(merged)
        if getattr(self, "btn_rescore", None) is not None:
            self.btn_rescore.setVisible(True)
        try:
            self._append(f"[评委] AI 评分 {float(s.get('overall', 0)):.1f}/10")
        except (TypeError, ValueError):
            pass

    def _set_metric(self, key, val, tag, dot_color):
        """写一条实测指标(数值蓝 #info,点色按状态 绿/红/蓝)。"""
        if not hasattr(self, "metric_rows") or key not in self.metric_rows:
            return
        dot, vlab, tlab = self.metric_rows[key]
        dot.setStyleSheet(f"background:{dot_color}; border-radius:4px;")
        vlab.setText(val); tlab.setText(tag)

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
            if has_panels:
                self._set_metric("s_star", f"{ss:.2f}", f"甜区≥{_q.S_STAR_LO}",
                                 p['accent'] if ss >= _q.S_STAR_LO else p['danger'])
                self._set_metric("bg_s", f"{bgs:.2f}",
                                 "真实底色" if (bgs > _q.BG_S_MAX and not _bg_flat) else f"应<{_q.BG_S_MAX}",
                                 p['danger'] if _bg_defect else p['accent'])
                self._set_metric("bg_level", f"{bgl:.3f}", "near black", p['info'])
            if getattr(self, "btn_scorefix", None) is not None:
                self.btn_scorefix.setVisible(ss < _q.S_STAR_LO or _bg_defect)
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
        """🔧 按评分优化:按确定性指标一键补救(纯 numpy,不需 runner、秒出)——背景偏色→中和;
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
        if op == "saturation_down":
            return "curves", {"saturation": -abs(float(p.get("amount", 0.15))), "linear": False}
        if op == "flatpatch":
            if not all(k in p for k in ("x", "y", "r")):
                return None, "需先用『🩹 灰尘修复』点选圆圈(缺坐标)"
            p.setdefault("mode", "gain"); return "flatpatch", p
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
        self.ed_ai_edit.clear()
        self._append(f"[你 → AI] {msg}")
        self._append("[AI 修改] 思考中(不阻塞界面)…")
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

    def _on_ai_edit(self, res):
        """agent_edit 返回 → 显示回复;有 op 则(存快照后)在成片上执行、刷新指标 + 撤销/对比。"""
        self._aiedit_thread = None
        if not isinstance(res, dict) or res.get("error"):
            self._append(f"[AI 修改] 出错:{(res or {}).get('error', '未知')}"); return
        reply = res.get("reply") or ""
        if reply:
            self._append(f"[AI] {reply}")
        hist = getattr(self, "_aiedit_history", [])
        hist.append(("用户", getattr(self, "_aiedit_pending", ""))); hist.append(("助手", reply))
        self._aiedit_history = hist[-16:]
        op, params = res.get("op"), res.get("params") or {}
        _u = res.get("usage") or {}
        if _u.get("total"):
            self._append(f"[AI 修改] 本次 {_u['total']} tokens" + (f"(含推理 {_u['reasoning']})" if _u.get("reasoning") else ""))
        if not op:
            return                                  # 纯文字回复 / 追问,不改图
        nop, nparams = self._norm_agent_op(op, params)
        if not nop:
            self._append(f"[AI 修改] 未执行:{nparams}"); return
        # 存优化前快照(撤销/对比复用)→ 在成片上执行(PI op,经 runner;不在线会自动拉起 PI)
        self._pre_remedy = {"xisf": self._final_xisf, "png": self._final_png,
                            "scores": dict(self._last_scores or {})}
        if self._run_op_on_final(nop, nparams, tag=f"aiedit_{op}", label=f"AI·{op}"):
            try:
                from . import quality
                m2 = quality.measure(str(self._final_xisf))
                self._last_scores = {**(self._last_scores or {}), "_quality": m2}
                self._show_scores(self._last_scores)
            except Exception:
                pass
            self.btn_remedy_undo.setVisible(True)
            self.btn_remedy_cmp.setChecked(False); self.btn_remedy_cmp.setText(t("⇄ 对比原图"))
            self.btn_remedy_cmp.setVisible(True)
            self._append(f"[AI 修改] ✓ 已执行 {op} → 满意可『导出成片』,不满意点『↩ 撤销』")

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
        # **优先用项目名**(ed_target,如原始叠加填的 260712_D3_M28 最可靠)——原始素材叠加模式下
        #   ed_input 为空,只看它会退回固定名 TTAstroPiLot_final(用户 2026-09-03 反馈的命名 bug)。
        folder = ""
        try:
            folder = (self.ed_target.text() or "").strip()
        except Exception:
            folder = ""
        if not folder:                                   # 无项目名 → 从输入路径推(母版/registered 模式)
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

    def _save_export_dir(self):
        """持久化「导出目录」字段到 settings(下次启动仍在)。"""
        d = (self.ed_exportdir.text() or "").strip().replace("\\", "/")
        try:
            _s = config.load_settings(); _s["export_dir"] = d; config.save_settings(_s)
        except Exception:
            pass

    def _export(self):
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
        if _expdir and os.path.isdir(_expdir):
            dst = "%s/%s" % (_expdir.rstrip("/"), self._suggest_export_name())
            self._append("[导出] → 导出目录 %s(文件名 %s)" % (_expdir, self._suggest_export_name()))
        else:
            dst, _ = QFileDialog.getSaveFileName(self, t("导出成片(选择基名,自动加各格式后缀)"),
                                                 self._suggest_export_name(), t("成片 (*.xisf *.png *.jpg)"))
            if not dst:
                return
            self.ed_exportdir.setText(str(Path(dst).parent).replace("\\", "/"))   # 回填并记住,下次免选
            self._save_export_dir()
        # PNG/JPG 要经 PixInsight 全分辨率重导 → runner 不在线就**自动冷启动 PI**并等就绪,不再让用户手动启动
        if need_runner and not self._ensure_runner("导出成片"):
            return
        base = str(Path(dst).with_suffix("")).replace("\\", "/")
        written = []
        import shutil
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            for f in fmts:
                outp = f"{base}.{f}"
                if f == "xisf":
                    shutil.copy2(self._final_xisf, outp)
                else:
                    params = {"quality": self.sl_jpgq.value()} if f == "jpg" else {}
                    job = protocol.new_job("inspect", input=self._final_xisf, params=params,
                                           outputs={"image": outp})
                    protocol.submit(job)
                    r = protocol.wait_result(job["job_id"], timeout=300)
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
                r = protocol.wait_result(job["job_id"], timeout=1800)
                if r.get("status") != "ok":
                    raise RuntimeError(f"星点分离失败:{r.get('error')}")
                _sl = r.get("image") or _sl
                _st = r.get("stars") or _st
                if self.chk_starless.isChecked():          # 去星星云 → JPG(3D 星云底)
                    o = f"{base}_starless.jpg"
                    jr = protocol.new_job("inspect", input=_sl, params={"quality": self.sl_jpgq.value()},
                                          outputs={"image": o})
                    protocol.submit(jr)
                    if protocol.wait_result(jr["job_id"], timeout=300).get("status") == "ok":
                        written.append(o)
                if self.chk_export_stars.isChecked():      # 纯星点 → PNG(3D 星点层)
                    o = f"{base}_stars.png"
                    jr = protocol.new_job("inspect", input=_st, outputs={"image": o})
                    protocol.submit(jr)
                    if protocol.wait_result(jr["job_id"], timeout=300).get("status") == "ok":
                        written.append(o)
            if self.chk_annotate.isChecked():              # 天体标注 → TXT(3D 建模按坐标放置天体)
                self._append("[导出] 天体标注(AnnotateImage:Messier/NGC/IC/SH2 + HIP/TYC/GAIA)中…")
                o = f"{base}_annotations.txt"
                job = protocol.new_job("annotate", input=self._final_xisf, outputs={"text": o})
                protocol.submit(job)
                r = protocol.wait_result(job["job_id"], timeout=900)
                if r.get("status") == "ok":
                    _cnt = r.get("count", 0)
                    written.append(o)                      # TXT 已写(即使 0 天体也含表头),照常报告
                    self._append(f"[导出] 已标注 {_cnt} 个天体 → {Path(o).name}"
                                 + ("" if _cnt else "(0 个:解析范围内无已知目录天体)"))
                else:
                    self._append(f"[导出] 标注失败:{r.get('error') or '成片天文解析失败'}")
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
            _msg = "\n".join(written)
            if _released:
                _msg += "\n\n" + t("PixInsight 已释放,可手动使用。")
            QMessageBox.information(self, t("导出完成"), _msg)
        except Exception as e:
            QMessageBox.critical(self, t("导出失败"), str(e))
        finally:
            QApplication.restoreOverrideCursor()


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
