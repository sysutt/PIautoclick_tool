"""TTAstroPiLot · 深空自动后期 · 一键式桌面界面(PyQt5)。

选输入 → 选流程(RGB/HOO/LRGB)→ 一键跑完(自动启动 PixInsight + job-runner),
带分步进度、预计剩余、中止;完成后 LLM 评分卡 + 导出/在文件夹显示。深/亮双主题。
视觉见 E:/AutoClick/design 方案变体 A,唯一强调色薄荷绿 #68E098。
运行:  python -m orchestrator.app_ui
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QButtonGroup,
    QLabel, QLineEdit, QPushButton, QCheckBox, QDoubleSpinBox, QSpinBox,
    QPlainTextEdit, QFileDialog, QMessageBox, QFrame, QProgressBar,
    QScrollArea, QSizePolicy, QStackedWidget, QComboBox, QToolButton, QSlider,
)

from . import config, protocol, pipeline
from . import critic
from .settings_ui import SettingsWindow

# ---- 双主题调色板 ----
DARK = dict(bg="#0a131a", surf1="#1e2224", surf2="#2a333a", stroke="#405159",
            accent="#68E098", accent_hi="#7CEAA6", accent_press="#4CAF50",
            text="#EEF1F4", text2="#bbc2ca", muted="#8a9399",
            logbg="#0c1015", prevbg="#0c1015")
LIGHT = dict(bg="#faf9f5", surf1="#ffffff", surf2="#eef1f4", stroke="#d4dae0",
             accent="#2f9e5e", accent_hi="#39b06c", accent_press="#268050",
             text="#1e2224", text2="#405159", muted="#8a9399",
             logbg="#f2f4f6", prevbg="#eef1f4")

PHASES = ["叠加", "校准", "梯度", "拉伸", "成片"]
# op → 阶段索引(单调推进,取已见最大)
_OP_PHASE = {"integrate": 0, "rgbcombine": 0, "crop": 1, "solve": 1, "colorcal": 1,
             "deconv": 1, "gradient": 2, "dustremove": 2, "stretch": 3, "ghs": 3,
             "maskstretch": 3, "lrgb": 3, "hoo": 3, "starsep": 3,
             "scnr": 4, "curves": 4, "recombine": 4, "hablend": 4, "denoise": 4}
_EXPECTED = {"rgb": 14, "hoo": 14, "lrgb": 26}


def qss(p):
    return f"""
QWidget {{ background:{p['bg']}; color:{p['text']}; font-family:"Microsoft YaHei","Segoe UI",-apple-system,sans-serif; font-size:12px; }}
QLabel {{ background:transparent; }}
#banner {{ font-size:22px; font-weight:bold; color:{p['accent']}; }}
#sub {{ color:{p['muted']}; font-size:11px; }}
QGroupBox {{ background:{p['surf1']}; border:1px solid {p['surf2']}; border-radius:10px; margin-top:16px; padding:14px 14px 14px 14px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:2px 6px; color:{p['accent']}; font-weight:bold; font-size:12px; }}
QLineEdit, QDoubleSpinBox, QSpinBox {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px; padding:6px 9px; color:{p['text']}; min-height:22px; selection-background-color:{p['accent']}; selection-color:{p['bg']}; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border:1px solid {p['accent']}; }}
QDoubleSpinBox::up-button, QSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::down-button {{ width:16px; background:{p['surf1']}; border:none; }}
QPushButton {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:7px; padding:7px 14px; color:{p['text']}; min-height:20px; }}
QPushButton:hover {{ border:1px solid {p['accent']}; }}
QPushButton:pressed {{ background:{p['surf1']}; }}
QPushButton#seg {{ border-radius:7px; padding:8px 10px; color:{p['text2']}; }}
QPushButton#seg:checked {{ background:{p['surf2']}; border:1px solid {p['accent']}; color:{p['accent']}; font-weight:bold; }}
QPushButton#primary {{ background:{p['accent']}; color:{p['bg']}; border:none; font-weight:bold; padding:9px 20px; }}
QPushButton#primary:hover {{ background:{p['accent_hi']}; }}
QPushButton#primary:pressed {{ background:{p['accent_press']}; }}
QPushButton#primary:disabled {{ background:{p['surf2']}; color:{p['muted']}; }}
QPushButton#danger {{ border:1px solid #ff6b6b; color:#ff6b6b; }}
QCheckBox {{ background:transparent; color:{p['text2']}; }}
QCheckBox::indicator {{ width:15px; height:15px; border:1px solid {p['stroke']}; border-radius:4px; background:{p['surf2']}; }}
QCheckBox::indicator:checked {{ background:{p['accent']}; border:1px solid {p['accent']}; }}
QSlider::groove:horizontal {{ height:5px; background:{p['surf2']}; border-radius:3px; }}
QSlider::sub-page:horizontal {{ background:{p['accent']}; border-radius:3px; }}
QSlider::handle:horizontal {{ width:14px; margin:-5px 0; border-radius:7px; background:{p['accent']}; border:1px solid {p['accent_hi']}; }}
QSlider::handle:horizontal:hover {{ background:{p['accent_hi']}; }}
QSlider:disabled {{}}
QSlider::sub-page:horizontal:disabled {{ background:{p['stroke']}; }}
QSlider::handle:horizontal:disabled {{ background:{p['stroke']}; border:1px solid {p['stroke']}; }}
QPlainTextEdit {{ background:{p['logbg']}; border:1px solid {p['surf2']}; border-radius:8px; color:{p['text2']}; font-family:Consolas,"Cascadia Mono",monospace; font-size:11px; }}
QProgressBar {{ background:{p['surf2']}; border:none; border-radius:5px; height:10px; text-align:center; color:transparent; }}
QProgressBar::chunk {{ background:{p['accent']}; border-radius:5px; }}
#preview {{ background:{p['prevbg']}; color:{p['muted']}; border:1px dashed {p['stroke']}; border-radius:12px; font-size:13px; }}
QScrollArea#leftscroll {{ background:transparent; border:none; }}
QScrollArea#leftscroll > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{p['surf2']}; border-radius:5px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{p['stroke']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
QPushButton#seg {{ border-radius:8px; padding:11px 10px; color:{p['text2']}; font-size:12px; }}
QComboBox {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px; padding:6px 9px; color:{p['text']}; min-height:22px; }}
QComboBox:focus {{ border:1px solid {p['accent']}; }}
QComboBox QAbstractItemView {{ background:{p['surf1']}; border:1px solid {p['stroke']}; selection-background-color:{p['accent']}; selection-color:{p['bg']}; outline:none; }}
QToolButton {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px; padding:4px 8px; color:{p['text']}; }}
QToolButton:hover {{ border:1px solid {p['accent']}; }}
"""


class _EmitStream:
    def __init__(self, sig):
        self._sig = sig

    def write(self, s):
        if s:
            self._sig.emit(str(s))

    def flush(self):
        pass


class Worker(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(str)                 # op 名
    preview = pyqtSignal(str)                  # 阶段性预览 png 路径
    done = pyqtSignal(bool, str, str, dict)    # ok, preview_png, final_xisf, scores

    def __init__(self, kind, inp, opts):
        super().__init__()
        self.kind, self.inp, self.opts = kind, inp, opts

    def run(self):
        old = sys.stdout
        sys.stdout = _EmitStream(self.log)
        # 解析 stdout 里的 "[tag] op -> ok" 推进进度
        self.log.connect(self._sniff)
        png = xis = ""
        scores = {}
        try:
            o = self.opts
            if self.kind == "lrgb":
                res = pipeline.run_lrgb(self.inp, timeout=o["timeout"], crop_frac=o["crop_frac"],
                                        neb_sat=o["neb_sat"], maskstretch_iters=o["ms_iters"],
                                        ghs_d=o["ghs_d"], core_thr=o["core_thr"], ha_amount=o["ha"])
            else:
                inp = self.inp
                raw = o.get("raw")
                reg = None
                if raw:
                    self.log.emit("[叠加] 原始素材 → 自定义滤镜法 WBPP(校准+去马+对齐)…")
                    reg = pipeline.run_wbpp_stack(raw, timeout=max(o["timeout"], 3600.0))
                    self.log.emit(f"[叠加] WBPP 完成,对齐子帧目录:{reg}")
                elif o["integrate_first"]:
                    reg = inp                       # mode1:inp 即对齐子帧目录
                if reg is not None:
                    keep = None
                    if o.get("detrail"):
                        self.log.emit("[去线] 残差法检测卫星/飞机线…")
                        dt = pipeline.run_detrail(reg, timeout=max(o["timeout"], 1800.0))
                        if dt["dropped"]:
                            self.log.emit(f"[去线] 检出 {len(dt['trail_idx'])} 帧含轨迹 "
                                          f"{dt['trail_idx']},整帧剔除 {len(dt['dropped'])} 张后整合。")
                            keep = dt["keep"]
                        elif dt["skipped"]:
                            self.log.emit(f"[去线] 含轨迹帧过多({len(dt['trail_idx'])}/"
                                          f"{len(dt['all'])}),为保信噪未剔除,保留全部帧。")
                        else:
                            self.log.emit("[去线] 未检出轨迹,全部帧保留。")
                    inp = pipeline.run_integrate(reg, timeout=max(o["timeout"], 1800.0),
                                                 images=keep)
                if self.kind == "hoo":
                    res = pipeline.run_hoo(inp, timeout=o["timeout"])
                else:
                    res = pipeline.run_rgb(inp, timeout=o["timeout"], ghs_d=o["ghs_d"],
                                           neb_sat=o["neb_sat"], recombine_stars=o["stars"],
                                           stretch_judge=o["stretch_judge"], target=o["target"],
                                           reveal=o["reveal"], lhe=o["lhe"])
            for tag in reversed(list(res.keys())):
                p = res[tag].get("preview")
                if p and Path(p).exists():
                    png = str(p)
                    im = res[tag].get("image")
                    xis = str(im) if im and Path(str(im)).exists() else ""
                    break
            # 完成后可选 LLM 评分
            if png:
                prov = (config.get_setting("llm.provider") or "").strip()
                if prov:
                    self.log.emit("[评委] 正在评分…")
                    try:
                        s = critic.score(png, context=f"{self.kind} 成片")
                        if "error" not in s:
                            scores = s
                    except Exception as e:
                        self.log.emit(f"[评委] 评分失败:{e}")
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


class AppWindow(QWidget):
    FLOWS = [("rgb", "RGB 宽带真彩"), ("hoo", "HOO 双窄带"), ("lrgb", "LRGB(H) 多通道")]

    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        self.theme = DARK
        self._param_rows = {}
        self._start_t = 0.0
        self._max_phase = -1
        self._done_ops = 0
        self._final_png = self._final_xisf = ""
        self._build()
        self._apply_theme()
        self._select_input_mode(0)
        self._select_flow(0)
        self._refresh_runner()

    # ---------- 构建 ----------
    def _build(self):
        self.setWindowTitle("TTAstroPiLot · 深空自动后期")
        self.setMinimumSize(980, 680)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 14)

        top = QHBoxLayout()
        head = QVBoxLayout()
        banner = QLabel("TTAstroPiLot"); banner.setObjectName("banner")
        sub = QLabel("深空自动后期 · 一键处理(LLM 评审 · PixInsight 自动流程)"); sub.setObjectName("sub")
        head.addWidget(banner); head.addWidget(sub)
        top.addLayout(head); top.addStretch()
        self.btn_theme = QPushButton("🌓 主题"); self.btn_theme.clicked.connect(self._toggle_theme)
        self.lbl_runner = QLabel("● runner ?")
        top.addWidget(self.btn_theme, alignment=Qt.AlignTop)
        top.addWidget(self.lbl_runner, alignment=Qt.AlignTop)
        outer.addLayout(top)

        body = QHBoxLayout(); outer.addLayout(body, 1)
        # 左侧控件列放进可滚动容器:窗口变矮时出竖向滚动条,而非把输入控件压扁
        left_container = QWidget()
        left = QVBoxLayout(left_container); left.setSpacing(10); left.setContentsMargins(2, 2, 8, 2)
        self.left_scroll = QScrollArea(); self.left_scroll.setObjectName("leftscroll")
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setWidget(left_container)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setMinimumWidth(430)
        body.addWidget(self.left_scroll, 3)

        # ① 流程
        gflow = QGroupBox("① 选择流程"); fl = QHBoxLayout(gflow)
        self.flow_group = QButtonGroup(self); self.flow_group.setExclusive(True)
        self.flow_btns = []
        for i, (_, label) in enumerate(self.FLOWS):
            b = QPushButton(label); b.setObjectName("seg"); b.setCheckable(True)
            b.clicked.connect(lambda _c, idx=i: self._select_flow(idx))
            self.flow_group.addButton(b, i); self.flow_btns.append(b); fl.addWidget(b)
        left.addWidget(gflow)

        # ② 输入 / 数据源(三种模式)
        gin = QGroupBox("② 输入 / 数据源"); vi = QVBoxLayout(gin); vi.setSpacing(8)
        mode_row = QHBoxLayout(); mode_row.setSpacing(6)
        self.in_mode_group = QButtonGroup(self); self.in_mode_group.setExclusive(True)
        self.in_mode_btns = []
        for i, label in enumerate(["已叠加母版", "对齐子帧目录", "原始素材叠加"]):
            b = QPushButton(label); b.setObjectName("seg"); b.setCheckable(True)
            b.clicked.connect(lambda _c, idx=i: self._select_input_mode(idx))
            self.in_mode_group.addButton(b, i); self.in_mode_btns.append(b); mode_row.addWidget(b)
        vi.addLayout(mode_row)
        self._input_mode = 0
        # 页0:单路径(模式 0 母版文件 / 模式 1 registered 目录 共用)。用显隐切换而非
        # QStackedWidget → 隐藏页在布局里不占高度,组框高度自适应当前页(不再按最高页预留)。
        self.pg_single = QWidget(); ls = QVBoxLayout(self.pg_single); ls.setContentsMargins(0, 2, 0, 0); ls.setSpacing(6)
        rs = QHBoxLayout()
        self.ed_input = QLineEdit()
        self.btn_browse = QPushButton("浏览…"); self.btn_browse.clicked.connect(self._browse)
        rs.addWidget(self.ed_input); rs.addWidget(self.btn_browse); ls.addLayout(rs)
        self.lbl_input_hint = QLabel(""); self.lbl_input_hint.setObjectName("sub"); self.lbl_input_hint.setWordWrap(True)
        ls.addWidget(self.lbl_input_hint)
        vi.addWidget(self.pg_single)
        # 页1:原始素材叠加配置面板
        self.pg_raw = self._build_rawstack_panel(); self.pg_raw.setVisible(False)
        vi.addWidget(self.pg_raw)
        # 从子帧整合时可选:自动去卫星/飞机线(残差检测→整帧剔除)。母版模式(0)无子帧,隐藏。
        self.chk_detrail = QCheckBox("自动去除卫星 / 飞机线(残差检测 → 整帧剔除)")
        self.chk_detrail.setChecked(True)
        self.chk_detrail.setToolTip("整合前对对齐子帧做残差霍夫检测,检出含轨迹的帧整帧剔除后再整合;\n"
                                    "含线帧超过 25% 时为保信噪自动跳过。仅在从子帧整合(模式②/③)时生效。")
        vi.addWidget(self.chk_detrail)
        left.addWidget(gin)
        self.chk_integrate = QCheckBox(); self.chk_integrate.setVisible(False)  # 兼容:内部用

        # ③ 参数
        gp = QGroupBox("③ 参数"); vp = QVBoxLayout(gp)
        self.sp_ghs = self._param(vp, "ghs", "GHS 拉伸力度 D", QDoubleSpinBox, 0, 2.5, 0.1, 0.5)
        self.sp_sat = self._param(vp, "sat", "饱和度提升", QDoubleSpinBox, 0, 1.0, 0.05, 0.15)
        self.chk_stars = self._param(vp, "stars", "合回星点(取消勾选=仅输出去星 starless)", QCheckBox)
        self.chk_stars.setChecked(True)  # 默认合回星点出带星成品
        self.chk_stretch_judge = self._param(vp, "sjudge", "拉伸力度评委自检(GHS 偏暗自动加大 D)", QCheckBox)
        self.chk_stretch_judge.setChecked(True)
        self.chk_stretch_judge.setToolTip("GHS 拉伸后让 LLM 评委对照判断力度是否合适;\n"
                                          "报 too_dark/too_strong 且偏离当前值就按建议 D 重拉一次(仅一次)。需已配置 LLM。")
        self.chk_reveal = self._param(vp, "reveal", "暗弱星云揭示(护亮核+护背景,提外围淡云)", QCheckBox)
        self.chk_reveal.setChecked(True)
        self.chk_reveal.setToolTip("maskstretch(lum 蒙版+bgProtect):额外拉伸只作用在暗弱/中间调,\n"
                                   "把外围淡 Ha、弥漫云气抬起,亮核/暗湾/背景不动。低面亮度弥散星云尤其需要。")
        self.chk_lhe = self._param(vp, "lhe", "局部对比 LHE(暗尘细丝更立体)", QCheckBox)
        self.chk_lhe.setChecked(True)
        self.chk_lhe.setToolTip("LocalHistogramEqualization 只做在亮区(羽化蒙版),增强细丝/团块的立体层次,不动背景。")
        self.sp_ha = self._param(vp, "ha", "Ha 小红花强度", QDoubleSpinBox, 0, 2.0, 0.1, 0.0)
        self.sp_ms = self._param(vp, "ms", "外环迭代拉伸次数", QSpinBox, 0, 6, 1, 2)
        self.sp_core = self._param(vp, "core", "核心保护阈值", QDoubleSpinBox, 0, 1.0, 0.05, 0.7)
        self.sp_crop = self._param(vp, "crop", "中央裁切比例", QDoubleSpinBox, 0, 0.4, 0.01, 0.13)
        self.sp_timeout = self._param(vp, "timeout", "单步超时(秒)", QSpinBox, 60, 7200, 30, 900)
        left.addWidget(gp)

        # 操作
        btns = QHBoxLayout()
        self.btn_pi = QPushButton("启动 PixInsight"); self.btn_pi.clicked.connect(self._start_pi)
        self.btn_release = QPushButton("释放 PixInsight"); self.btn_release.clicked.connect(self._release_pi)
        self.btn_release.setToolTip("停止 job-runner/看门狗并结束 PixInsight,把 PI 交还给你手动使用")
        self.btn_cfg = QPushButton("配置…"); self.btn_cfg.clicked.connect(self._open_settings)
        self.btn_clean = QPushButton("清理中间文件"); self.btn_clean.clicked.connect(self._cleanup)
        self.btn_abort = QPushButton("■ 中止"); self.btn_abort.setObjectName("danger")
        self.btn_abort.clicked.connect(self._abort); self.btn_abort.setVisible(False)
        self.btn_run = QPushButton("▶ 开始处理"); self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self._run)
        for b in (self.btn_pi, self.btn_release, self.btn_cfg, self.btn_clean):
            btns.addWidget(b)
        btns.addStretch(); btns.addWidget(self.btn_abort); btns.addWidget(self.btn_run)
        left.addLayout(btns)

        # 进度(处理中显示)
        self.gprog = QGroupBox("处理进度")
        vpg = QVBoxLayout(self.gprog)
        self.phase_row = QHBoxLayout()
        self.phase_lbls = []
        for i, name in enumerate(PHASES):
            l = QLabel(f"{i+1}·{name}"); self.phase_lbls.append(l); self.phase_row.addWidget(l)
            if i < len(PHASES) - 1:
                arrow = QLabel("→"); self.phase_row.addWidget(arrow)
        self.phase_row.addStretch()
        vpg.addLayout(self.phase_row)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
        vpg.addWidget(self.bar)
        self.lbl_eta = QLabel("—"); self.lbl_eta.setObjectName("sub")
        vpg.addWidget(self.lbl_eta)
        self.gprog.setVisible(False)
        left.addWidget(self.gprog)

        left.addWidget(self._divider())
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(120)
        self.log.setPlaceholderText("就绪。选择流程与输入后点击「开始处理」。")
        left.addWidget(self.log, 1)

        # 右:预览 + 完成态卡片
        right = QVBoxLayout(); body.addLayout(right, 2)
        self.preview = QLabel("结果预览\n\n成片将在此显示"); self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumWidth(380)
        right.addWidget(self.preview, 1)

        self.gresult = QGroupBox("完成 · 评分与导出")
        vr = QVBoxLayout(self.gresult)
        self.lbl_scores = QLabel("—"); self.lbl_scores.setWordWrap(True)
        vr.addWidget(self.lbl_scores)
        # 导出格式多选 + JPG 质量
        fmt = QHBoxLayout(); fmt.setSpacing(8)
        self.chk_xisf = QCheckBox("XISF"); self.chk_xisf.setChecked(True)
        self.chk_png = QCheckBox("PNG"); self.chk_png.setChecked(True)
        self.chk_jpg = QCheckBox("JPG")
        self.sl_jpgq = QSlider(Qt.Horizontal); self.sl_jpgq.setRange(1, 100); self.sl_jpgq.setValue(95)
        self.sl_jpgq.setMinimumWidth(110); self.sl_jpgq.setMaximumWidth(160); self.sl_jpgq.setEnabled(False)
        self.sl_jpgq.setToolTip("JPG 导出质量(默认 95:画质与体积的甜点位)")
        self.lbl_jpgq = QLabel("95"); self.lbl_jpgq.setMinimumWidth(26); self.lbl_jpgq.setEnabled(False)
        self.sl_jpgq.valueChanged.connect(lambda v: self.lbl_jpgq.setText(str(v)))
        self.chk_jpg.toggled.connect(self.sl_jpgq.setEnabled)
        self.chk_jpg.toggled.connect(self.lbl_jpgq.setEnabled)
        fmt.addWidget(QLabel("格式:")); fmt.addWidget(self.chk_xisf); fmt.addWidget(self.chk_png)
        fmt.addWidget(self.chk_jpg); fmt.addWidget(QLabel("质量")); fmt.addWidget(self.sl_jpgq)
        fmt.addWidget(self.lbl_jpgq); fmt.addStretch()
        vr.addLayout(fmt)
        rb = QHBoxLayout()
        self.btn_show = QPushButton("在文件夹显示"); self.btn_show.clicked.connect(self._show_in_folder)
        self.btn_export = QPushButton("↓ 导出成片"); self.btn_export.setObjectName("primary")
        self.btn_export.clicked.connect(self._export)
        rb.addWidget(self.btn_show); rb.addStretch(); rb.addWidget(self.btn_export)
        vr.addLayout(rb)
        self.gresult.setVisible(False)
        right.addWidget(self.gresult)

    def _param(self, vbox, key, label, cls, *rng):
        roww = QWidget(); h = QHBoxLayout(roww); h.setContentsMargins(0, 2, 0, 2)
        if cls is QCheckBox:
            w = QCheckBox(label); h.addWidget(w)
        else:
            lab = QLabel(label + ":"); lab.setObjectName("sub")
            w = cls(); lo, hi, step, val = rng
            w.setRange(lo, hi); w.setSingleStep(step); w.setValue(val)
            if isinstance(w, QDoubleSpinBox):
                w.setDecimals(2)
            w.setMaximumWidth(120)
            h.addWidget(lab); h.addStretch(); h.addWidget(w)
        vbox.addWidget(roww); self._param_rows[key] = roww
        return w

    def _divider(self):
        f = QFrame(); f.setFrameShape(QFrame.HLine); f.setFixedHeight(1)
        f.setStyleSheet(f"color:{self.theme['surf2']};")
        return f

    # ---------- 输入模式 / 原始叠加配置 ----------
    def _build_rawstack_panel(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 2, 0, 0); v.setSpacing(8)
        hint = QLabel("每晚:光场+平场目录 + 标签(按晚匹配平场);暗场/偏置全项目共用。"
                      "用自定义滤镜法一次跑 WBPP(校准+去马+对齐)→ 整合去线 → 后期。")
        hint.setObjectName("sub"); hint.setWordWrap(True); v.addWidget(hint)
        self.night_rows = []
        self.nights_box = QVBoxLayout(); self.nights_box.setSpacing(6); v.addLayout(self.nights_box)
        addbtn = QPushButton("+ 添加一晚"); addbtn.clicked.connect(lambda: self._add_night_row())
        v.addWidget(addbtn, alignment=Qt.AlignLeft)
        self._add_night_row()
        self.ed_dark = self._dir_row(v, "暗场", "…/Dark/…(共用,不打标签)")
        self.ed_bias = self._dir_row(v, "偏置", "…/Bias/…(共用,不打标签)")
        outrow = QHBoxLayout()
        self.ed_stackout = QLineEdit(config.get_setting("stacking_output_base", "M:/Deepsky"))
        bo = QPushButton("浏览…"); bo.clicked.connect(lambda: self._pick_dir(self.ed_stackout))
        lo = QLabel("输出根:"); lo.setMinimumWidth(48)
        outrow.addWidget(lo); outrow.addWidget(self.ed_stackout, 1); outrow.addWidget(bo); v.addLayout(outrow)
        trow = QHBoxLayout()
        self.ed_target = QLineEdit(); self.ed_target.setPlaceholderText("项目名 如 260710-260724_2600mc_IC1396")
        lt = QLabel("项目名:"); lt.setMinimumWidth(48)
        trow.addWidget(lt); trow.addWidget(self.ed_target, 1); v.addLayout(trow)
        return w

    def _dir_row(self, vbox, label, ph):
        r = QHBoxLayout(); ed = QLineEdit(); ed.setPlaceholderText(ph)
        b = QPushButton("浏览…"); b.clicked.connect(lambda: self._pick_dir(ed))
        lab = QLabel(label + ":"); lab.setMinimumWidth(48)
        r.addWidget(lab); r.addWidget(ed, 1); r.addWidget(b); vbox.addLayout(r)
        return ed

    def _add_night_row(self):
        if len(self.night_rows) >= 6:
            return
        n = len(self.night_rows)
        roww = QWidget(); h = QHBoxLayout(roww); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
        tag = QComboBox(); tag.addItems([f"d{i}rgb" for i in range(1, 7)]); tag.setCurrentIndex(min(n, 5))
        tag.setMaximumWidth(84)
        ed_l = QLineEdit(); ed_l.setPlaceholderText(f"第{n+1}晚 光场目录")
        bl = QToolButton(); bl.setText("光…"); bl.clicked.connect(lambda: self._pick_dir(ed_l))
        ed_f = QLineEdit(); ed_f.setPlaceholderText("平场目录")
        bf = QToolButton(); bf.setText("平…"); bf.clicked.connect(lambda: self._pick_dir(ed_f))
        rm = QToolButton(); rm.setText("✕"); rm.clicked.connect(lambda: self._remove_night_row(roww))
        for wdg in (tag, ed_l, bl, ed_f, bf, rm):
            h.addWidget(wdg)
        h.setStretch(1, 2); h.setStretch(3, 2)
        self.night_rows.append({"w": roww, "tag": tag, "light": ed_l, "flat": ed_f})
        self.nights_box.addWidget(roww)

    def _remove_night_row(self, roww):
        if len(self.night_rows) <= 1:
            return
        self.night_rows = [r for r in self.night_rows if r["w"] is not roww]
        roww.setParent(None); roww.deleteLater()

    def _pick_dir(self, ed):
        p = QFileDialog.getExistingDirectory(self, "选择目录")
        if p:
            ed.setText(p.replace("\\", "/"))

    def _pick_file(self, ed):
        p, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "图像 (*.xisf *.fit *.fits)")
        if p:
            ed.setText(p.replace("\\", "/"))

    def _select_input_mode(self, idx):
        self._input_mode = idx
        self.in_mode_btns[idx].setChecked(True)
        self.pg_single.setVisible(idx < 2)
        self.pg_raw.setVisible(idx == 2)
        self.chk_detrail.setVisible(idx in (1, 2))   # 仅从子帧整合时可去线
        if idx == 0:
            self.ed_input.setPlaceholderText("已叠加母版 .xisf / .fit / .fits")
            self.lbl_input_hint.setText("直接后期一张已叠加好的主图。")
        elif idx == 1:
            self.ed_input.setPlaceholderText("registered 对齐子帧目录(将自动整合)")
            self.lbl_input_hint.setText("整合目录内全部对齐子帧后再后期(多通道 LRGB 也用此)。")

    def _raw_config(self):
        nights = []
        for r in self.night_rows:
            lt = r["light"].text().strip(); fl = r["flat"].text().strip()
            if lt or fl:
                nights.append({"light": lt, "flat": fl, "tag": r["tag"].currentText()})
        return {"nights": nights, "dark": self.ed_dark.text().strip(), "bias": self.ed_bias.text().strip(),
                "out_base": self.ed_stackout.text().strip(), "target": self.ed_target.text().strip()}

    # ---------- 主题 ----------
    def _apply_theme(self):
        QApplication.instance().setStyleSheet(qss(self.theme))
        self._refresh_runner()
        self._paint_phases()

    def _toggle_theme(self):
        self.theme = LIGHT if self.theme is DARK else DARK
        self._apply_theme()

    # ---------- 流程/参数 ----------
    def _select_flow(self, idx):
        self.flow_btns[idx].setChecked(True); self.flow_idx = idx
        kind = self.FLOWS[idx][0]
        lrgb, rgb = kind == "lrgb", kind == "rgb"
        vis = {"ghs": rgb or lrgb, "sat": rgb or lrgb, "stars": rgb,
               "ha": lrgb, "ms": lrgb, "core": lrgb, "crop": lrgb, "timeout": True}
        for k, r in self._param_rows.items():
            r.setVisible(vis.get(k, True))
        # 原始叠加模式仅适用于 OSC(RGB/HOO);LRGB 多通道需选"对齐子帧目录"
        self.in_mode_btns[2].setEnabled(not lrgb)
        if lrgb and self._input_mode != 1:
            self._select_input_mode(1)

    def _browse(self):
        # 模式 1(registered 目录)或 LRGB → 选目录;模式 0 → 选母版文件
        want_dir = self._input_mode == 1 or self.FLOWS[self.flow_idx][0] == "lrgb"
        if want_dir:
            p = QFileDialog.getExistingDirectory(self, "选择 registered 目录")
        else:
            p, _ = QFileDialog.getOpenFileName(self, "选择主图", "", "图像 (*.xisf *.fit *.fits)")
        if p:
            self.ed_input.setText(p.replace("\\", "/"))

    def _refresh_runner(self):
        alive = protocol.runner_alive()
        self.lbl_runner.setText("● runner 在线" if alive else "● runner 未运行")
        self.lbl_runner.setStyleSheet(
            f"color:{self.theme['accent']};font-weight:bold;" if alive
            else f"color:{self.theme['muted']};font-weight:bold;")
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

    def _start_pi(self):
        if self._refresh_runner():
            QMessageBox.information(self, "PixInsight", "job-runner 已在线。")
            return
        exe = config.pixinsight_exe()
        if not exe or not Path(exe).exists():
            QMessageBox.warning(self, "未找到 PixInsight", "请在『配置』里设置 PixInsight 路径。")
            return
        try:
            # 先杀掉可能残留的 PI 实例(单实例会吞掉 -r= 参数),再冷启动执行脚本
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/IM", "PixInsight.exe", "/F"], capture_output=True)
                time.sleep(2)
            subprocess.Popen([exe, "-n", "-r=" + str(config.JOB_RUNNER_JS)])
            self._append(f"[启动] {exe} -n -r={config.JOB_RUNNER_JS}")
            self._poll_runner()
            QMessageBox.information(self, "PixInsight", "正在冷启动 PixInsight 并执行 job-runner(约 15-30s)。\n待『runner 在线』后再开始处理。")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", str(e))

    def _release_pi(self):
        """停止 job-runner/看门狗并结束 PixInsight,把 PI 交还给用户手动使用。"""
        if self.thread is not None:
            QMessageBox.warning(self, "正在处理", "有处理任务进行中,请先『中止』再释放。")
            return
        ret = QMessageBox.question(
            self, "释放 PixInsight",
            "将停止 job-runner / 看门狗并结束所有 PixInsight 进程,之后你可手动使用 PI。\n确定?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            return
        try:
            # 1) 先发 STOP 信号(尤其 STOP_WATCHDOG:否则看门狗会把被杀的 PI 又拉起来)
            for name in ("STOP", "STOP_WATCHDOG", "STOP_GUARD"):
                try:
                    (config.RUN_DIR / name).write_text("stop", encoding="utf-8")
                except OSError:
                    pass
            time.sleep(1.5)  # 给看门狗/守卫一轮退出的时间
            # 2) 结束 PixInsight 进程
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/IM", "PixInsight.exe", "/F"], capture_output=True)
            else:
                subprocess.run(["pkill", "-f", "PixInsight"], capture_output=True)
            time.sleep(1)
            # 3) 清理 STOP 信号 + 心跳,便于下次启动
            for name in ("STOP", "STOP_WATCHDOG", "STOP_GUARD", "runner.heartbeat"):
                try:
                    f = config.RUN_DIR / name
                    if f.exists():
                        f.unlink()
                except OSError:
                    pass
            self._append("[释放] 已停止 runner/看门狗并结束 PixInsight。PI 现在可手动使用。")
            self._refresh_runner()
            QMessageBox.information(self, "已释放", "PixInsight 已释放,可手动使用。")
        except Exception as e:
            QMessageBox.critical(self, "释放失败", str(e))

    def _open_settings(self):
        self._settings = SettingsWindow(); self._settings.show()

    def _cleanup(self):
        xs = glob.glob(str(config.RUN_DIR / "*.xisf"))
        if not xs:
            QMessageBox.information(self, "清理", "没有中间 .xisf 可清理。")
            return
        total = sum(os.path.getsize(x) for x in xs if os.path.exists(x))
        if QMessageBox.question(self, "清理中间文件",
                                f"删除 {len(xs)} 个中间 .xisf,释放约 {total/1e9:.1f} GB。\n(PNG 与成片保留)确定?") != QMessageBox.Yes:
            return
        freed = n = 0
        for x in xs:
            try:
                sz = os.path.getsize(x); os.remove(x); freed += sz; n += 1
            except OSError:
                pass
        self._append(f"[清理] 删除 {n} 个,释放 {freed/1e9:.1f} GB")

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
            bad = [n for n in raw["nights"] if not (n["light"] and n["flat"])]
            if not raw["nights"] or bad:
                QMessageBox.warning(self, "配置不完整", "原始素材叠加:每晚都需填光场+平场目录。")
                return
            if not raw["dark"] or not raw["bias"] or not raw["target"]:
                QMessageBox.warning(self, "配置不完整", "需填暗场、偏置目录与项目名。")
                return
            inp = ""  # 原始叠加:输入路径在 WBPP 叠加+整合后得到
        else:
            inp = self.ed_input.text().strip()
            if not inp or not Path(inp).exists():
                QMessageBox.warning(self, "输入无效", "请选择有效的主图或目录。")
                return
        if not self._refresh_runner():
            if QMessageBox.question(self, "runner 未运行", "未检测到 job-runner。仍然开始?") != QMessageBox.Yes:
                return
        kind = self.FLOWS[self.flow_idx][0]
        self.log.clear(); self.gresult.setVisible(False)
        self._start_t = time.time(); self._max_phase = -1; self._done_ops = 0
        self._expected = _EXPECTED.get(kind, 16)
        self.bar.setValue(0); self.lbl_eta.setText("准备中…")
        self.gprog.setVisible(True); self._paint_phases()
        self.btn_run.setEnabled(False); self.btn_run.setText("处理中…"); self.btn_abort.setVisible(True)
        self.thread = QThread()
        self.worker = Worker(kind, inp, opts)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append)
        self.worker.progress.connect(self._on_progress)
        self.worker.preview.connect(self._show_stage_preview)
        self.worker.done.connect(self._finished)
        self.thread.start()

    def _abort(self):
        pipeline.request_cancel()
        self._append("[中止] 已请求中止,当前步骤后停止…")
        self.btn_abort.setEnabled(False)

    def _on_progress(self, op):
        self._done_ops += 1
        ph = _OP_PHASE.get(op)
        if ph is not None and ph > self._max_phase:
            self._max_phase = ph
            self._paint_phases()
        frac = min(0.99, self._done_ops / max(1, self._expected))
        self.bar.setValue(int(frac * 100))
        el = time.time() - self._start_t
        if frac > 0.05:
            rem = el * (1 - frac) / frac
            self.lbl_eta.setText(f"已用 {int(el//60):02d}:{int(el%60):02d} · 预计剩余 ~{int(rem//60):02d}:{int(rem%60):02d}"
                                 f"  ·  步骤 {min(self._max_phase+1, 5)}/5")

    def _paint_phases(self):
        for i, l in enumerate(getattr(self, "phase_lbls", [])):
            if i <= self._max_phase:
                l.setStyleSheet(f"color:{self.theme['accent']};font-weight:bold;")
            else:
                l.setStyleSheet(f"color:{self.theme['muted']};")

    def _append(self, s):
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(s if s.endswith("\n") else s + "\n")
        self.log.moveCursor(self.log.textCursor().End)

    def _show_stage_preview(self, path):
        # 处理过程中把每步的阶段效果图显示到右侧预览框(增强参与感)
        try:
            if not path or not Path(path).exists():
                return
            pm = QPixmap(path)
            if pm.isNull():
                return
            self.preview.setPixmap(pm.scaled(self.preview.width(), self.preview.height(),
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass

    def _finished(self, ok, png, xis, scores):
        self.thread.quit(); self.thread.wait()
        self.thread = None; self.worker = None
        self.btn_run.setEnabled(True); self.btn_run.setText("▶ 开始处理")
        self.btn_abort.setVisible(False); self.btn_abort.setEnabled(True)
        if ok:
            self.bar.setValue(100)
            el = time.time() - self._start_t
            self.lbl_eta.setText(f"完成 · 用时 {int(el//60):02d}:{int(el%60):02d}")
            self._final_png, self._final_xisf = png, xis
            if png and Path(png).exists():
                pm = QPixmap(png)
                if not pm.isNull():
                    self.preview.setPixmap(pm.scaled(self.preview.width(), self.preview.height(),
                                                     Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self._show_scores(scores)
            self.gresult.setVisible(True)
            self._append(f"[✓] 完成:{png}")
        else:
            self.lbl_eta.setText("已停止")
            self._append("[✗] 处理未完成,见日志。")

    def _show_scores(self, s):
        if s and "overall" in s:
            self.lbl_scores.setText(
                f"<b style='color:{self.theme['accent']};font-size:15px'>LLM 评分 {s['overall']:.1f}/10</b>"
                f"　背景 {s.get('background',0):.1f}　星色 {s.get('star_color',0):.1f}　核心 {s.get('core',0):.1f}"
                f"<br><span style='color:{self.theme['muted']}'>{s.get('comment','')}</span>")
        else:
            self.lbl_scores.setText(f"<span style='color:{self.theme['muted']}'>(未启用 LLM 评委或评分不可用)</span>")

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

    def _export(self):
        src = self._final_xisf or self._final_png
        if not src or not Path(src).exists():
            QMessageBox.information(self, "导出", "没有可导出的成片。")
            return
        fmts = [f for f, c in (("xisf", self.chk_xisf), ("png", self.chk_png), ("jpg", self.chk_jpg)) if c.isChecked()]
        if not fmts:
            QMessageBox.information(self, "导出", "请至少勾选一种导出格式。")
            return
        # PNG/JPG 需从 xisf 经 inspect op 全分辨率重导 → 需 runner 在线
        need_runner = ("png" in fmts or "jpg" in fmts)
        have_xisf = bool(self._final_xisf and Path(self._final_xisf).exists())
        if need_runner and not have_xisf:
            QMessageBox.warning(self, "无法导出", "缺少成片 XISF,无法生成 PNG/JPG。")
            return
        if need_runner and not protocol.runner_alive():
            QMessageBox.warning(self, "需要 runner", "导出 PNG/JPG 需 job-runner 在线(经 PixInsight 保存)。请先『启动 PixInsight』。")
            return
        dst, _ = QFileDialog.getSaveFileName(self, "导出成片(选择基名,自动加各格式后缀)",
                                             "TTAstroPiLot_final", "成片 (*.xisf *.png *.jpg)")
        if not dst:
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
            self._append("[导出] " + " / ".join(written))
            QMessageBox.information(self, "导出完成", "\n".join(written))
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
        finally:
            QApplication.restoreOverrideCursor()


def main() -> int:
    app = QApplication(sys.argv)
    w = AppWindow()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
