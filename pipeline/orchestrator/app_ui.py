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

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QButtonGroup,
    QLabel, QLineEdit, QPushButton, QCheckBox, QDoubleSpinBox, QSpinBox,
    QPlainTextEdit, QFileDialog, QMessageBox, QFrame, QProgressBar,
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
QGroupBox {{ background:{p['surf1']}; border:1px solid {p['surf2']}; border-radius:10px; margin-top:14px; padding:10px 12px 12px 12px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:12px; padding:0 4px; color:{p['text2']}; font-weight:bold; }}
QLineEdit, QDoubleSpinBox, QSpinBox {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:6px; padding:5px 8px; color:{p['text']}; selection-background-color:{p['accent']}; selection-color:{p['bg']}; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border:1px solid {p['accent']}; }}
QPushButton {{ background:{p['surf2']}; border:1px solid {p['stroke']}; border-radius:7px; padding:7px 14px; color:{p['text']}; }}
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
QPlainTextEdit {{ background:{p['logbg']}; border:1px solid {p['surf2']}; border-radius:8px; color:{p['text2']}; font-family:Consolas,"Cascadia Mono",monospace; font-size:11px; }}
QProgressBar {{ background:{p['surf2']}; border:none; border-radius:5px; height:10px; text-align:center; color:transparent; }}
QProgressBar::chunk {{ background:{p['accent']}; border-radius:5px; }}
#preview {{ background:{p['prevbg']}; color:{p['muted']}; border:1px solid {p['surf2']}; border-radius:10px; }}
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
                if o["integrate_first"]:
                    inp = pipeline.run_integrate(inp, timeout=max(o["timeout"], 1800.0))
                if self.kind == "hoo":
                    res = pipeline.run_hoo(inp, timeout=o["timeout"])
                else:
                    res = pipeline.run_rgb(inp, timeout=o["timeout"], ghs_d=o["ghs_d"],
                                           neb_sat=o["neb_sat"], recombine_stars=o["stars"])
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
        left = QVBoxLayout(); body.addLayout(left, 3)

        # ① 流程
        gflow = QGroupBox("① 选择流程"); fl = QHBoxLayout(gflow)
        self.flow_group = QButtonGroup(self); self.flow_group.setExclusive(True)
        self.flow_btns = []
        for i, (_, label) in enumerate(self.FLOWS):
            b = QPushButton(label); b.setObjectName("seg"); b.setCheckable(True)
            b.clicked.connect(lambda _c, idx=i: self._select_flow(idx))
            self.flow_group.addButton(b, i); self.flow_btns.append(b); fl.addWidget(b)
        left.addWidget(gflow)

        # ② 输入
        gin = QGroupBox("② 选择输入"); vi = QVBoxLayout(gin)
        row = QHBoxLayout()
        self.ed_input = QLineEdit()
        self.btn_browse = QPushButton("浏览…"); self.btn_browse.clicked.connect(self._browse)
        row.addWidget(self.ed_input); row.addWidget(self.btn_browse); vi.addLayout(row)
        self.chk_integrate = QCheckBox("输入为 registered 目录,先自动叠加(RGB / HOO 用)")
        vi.addWidget(self.chk_integrate)
        left.addWidget(gin)

        # ③ 参数
        gp = QGroupBox("③ 参数"); vp = QVBoxLayout(gp)
        self.sp_ghs = self._param(vp, "ghs", "GHS 拉伸力度 D", QDoubleSpinBox, 0, 2.5, 0.1, 0.5)
        self.sp_sat = self._param(vp, "sat", "饱和度提升", QDoubleSpinBox, 0, 1.0, 0.05, 0.15)
        self.chk_stars = self._param(vp, "stars", "合回星点(默认 starless)", QCheckBox)
        self.sp_ha = self._param(vp, "ha", "Ha 小红花强度", QDoubleSpinBox, 0, 2.0, 0.1, 0.0)
        self.sp_ms = self._param(vp, "ms", "外环迭代拉伸次数", QSpinBox, 0, 6, 1, 2)
        self.sp_core = self._param(vp, "core", "核心保护阈值", QDoubleSpinBox, 0, 1.0, 0.05, 0.7)
        self.sp_crop = self._param(vp, "crop", "中央裁切比例", QDoubleSpinBox, 0, 0.4, 0.01, 0.13)
        self.sp_timeout = self._param(vp, "timeout", "单步超时(秒)", QSpinBox, 60, 7200, 30, 900)
        left.addWidget(gp)

        # 操作
        btns = QHBoxLayout()
        self.btn_pi = QPushButton("启动 PixInsight"); self.btn_pi.clicked.connect(self._start_pi)
        self.btn_cfg = QPushButton("配置…"); self.btn_cfg.clicked.connect(self._open_settings)
        self.btn_clean = QPushButton("清理中间文件"); self.btn_clean.clicked.connect(self._cleanup)
        self.btn_abort = QPushButton("■ 中止"); self.btn_abort.setObjectName("danger")
        self.btn_abort.clicked.connect(self._abort); self.btn_abort.setVisible(False)
        self.btn_run = QPushButton("▶ 开始处理"); self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self._run)
        for b in (self.btn_pi, self.btn_cfg, self.btn_clean):
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
        self.chk_integrate.setVisible(not lrgb)
        self.ed_input.setPlaceholderText(
            "registered 目录(含各通道子目录 …FILTER-Luminance/Red/…)" if lrgb
            else "单张主图 .xisf / .fits(或勾选先叠加则选 registered 目录)")

    def _browse(self):
        want_dir = self.FLOWS[self.flow_idx][0] == "lrgb" or self.chk_integrate.isChecked()
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

    def _start_pi(self):
        if self._refresh_runner():
            QMessageBox.information(self, "PixInsight", "job-runner 已在线。")
            return
        exe = config.pixinsight_exe()
        if not exe or not Path(exe).exists():
            QMessageBox.warning(self, "未找到 PixInsight", "请在『配置』里设置 PixInsight 路径。")
            return
        try:
            subprocess.Popen([exe, str(config.JOB_RUNNER_JS)])
            self._append(f"[启动] {exe}\n  加载 job-runner:{config.JOB_RUNNER_JS}")
            QMessageBox.information(self, "PixInsight", "已启动 PixInsight 并加载 job-runner。\n待『runner 在线』后再开始处理。")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", str(e))

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
                "integrate_first": self.chk_integrate.isChecked()}

    # ---------- 运行 / 进度 / 中止 ----------
    def _run(self):
        if self.thread is not None:
            return
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
        self.worker = Worker(kind, inp, self._collect_opts())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append)
        self.worker.progress.connect(self._on_progress)
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
        ext = Path(src).suffix
        dst, _ = QFileDialog.getSaveFileName(self, "导出成片", f"TTAstroPiLot_final{ext}",
                                             f"成片 (*{ext})")
        if dst:
            import shutil
            try:
                shutil.copy2(src, dst)
                # 顺带导出预览 png
                if self._final_png and self._final_png != src:
                    shutil.copy2(self._final_png, str(Path(dst).with_suffix(".png")))
                self._append(f"[导出] {dst}")
                QMessageBox.information(self, "导出完成", dst)
            except OSError as e:
                QMessageBox.critical(self, "导出失败", str(e))


def main() -> int:
    app = QApplication(sys.argv)
    w = AppWindow()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
