"""配置界面(PyQt5)。

提前填入并持久保存敏感设置(astrometry.net API key、LLM 供应商/模型/key、
PixInsight 路径),存到本地 _config/settings.json(不进 git)。

运行:
    python -m orchestrator.settings_ui
"""

from __future__ import annotations

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFormLayout, QGroupBox, QLineEdit,
    QComboBox, QPushButton, QLabel, QHBoxLayout, QMessageBox, QCheckBox, QFrame,
    QDoubleSpinBox, QScrollArea,
)

from . import config

# 接口来源(顶层选择):内部值 → 显示文案。official 内部映射到 provider="tickwhale"(不暴露该词)。
_SOURCES = [("", "不启用评委"),
            ("official", "使用官方提供的接口"),
            ("byo", "使用自己的大模型 API")]
# 「自己的 API」下的供应商(不含官方接口)
_BYO_PROVIDERS = ["anthropic", "openai", "kimi", "deepseek", "openai_compatible"]


class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = config.load_settings()
        self._build()
        self._polish()
        self._load_into_fields()

    def _build(self):
        # 视觉沿用主窗口:样式表挂在 QApplication 上,这里只需复用同一批 objectName。
        # 【骨架(用户 2026-09-15「设置项没法滚动」)】内容比屏幕高 → 必须放进 QScrollArea。
        #   头部与「保存/关闭」留在滚动区**外**:滚到底才能点保存是很糟的交互,按钮要始终在。
        self.setWindowTitle("TTAstroPiLot · 配置")
        self.setMinimumWidth(640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head_w = QFrame(); head_w.setObjectName("headerbar")
        head = QVBoxLayout(head_w); head.setContentsMargins(24, 18, 24, 14); head.setSpacing(4)
        banner = QLabel("配置"); banner.setObjectName("banner")
        title = QLabel("保存在本机 _config/settings.json,不上传、不进版本库")
        title.setObjectName("sub"); title.setWordWrap(True)
        head.addWidget(banner); head.addWidget(title)
        outer.addWidget(head_w)
        hair = QFrame(); hair.setObjectName("hairline"); hair.setFixedHeight(2)
        outer.addWidget(hair)

        scroll = QScrollArea(); scroll.setObjectName("cfgscroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget(); body.setObjectName("cfgbody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 18, 24, 22)
        layout.setSpacing(16)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self._outer = outer
        # 滚动容器不该自带底色/边框 —— 让主窗口 QSS 的窗体底色透出来,视觉上就是一张连续的长页
        self.setStyleSheet("QScrollArea#cfgscroll{background:transparent;border:0;}"
                           "QWidget#cfgbody{background:transparent;}")

        # ---- astrometry.net ----
        g1 = QGroupBox("astrometry.net(在线天文解析兜底)")
        f1 = QFormLayout(g1)
        self.ed_astro_key = QLineEdit()
        self.ed_astro_key.setEchoMode(QLineEdit.Password)
        self.ed_astro_key.setPlaceholderText("在 nova.astrometry.net 账号页获取 API key")
        self.chk_show_astro = QCheckBox("显示")
        row = QHBoxLayout()
        row.addWidget(self.ed_astro_key)
        row.addWidget(self.chk_show_astro)
        self.chk_show_astro.toggled.connect(
            lambda on: self.ed_astro_key.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        f1.addRow("API key:", row)
        layout.addWidget(g1)

        # ---- LLM 评委 ----
        # 不复用主窗口的 gb_main(那是给"空标题+自定义头条"卡片用的 margin-top:0,带真标题会压边框);
        # 用默认 QGroupBox 样式,标题正常悬在上边框缺口处。
        g2 = QGroupBox("多模态 LLM 评委(用于图像质量评估,需视觉模型)")
        v2 = QVBoxLayout(g2)
        # 顶层:接口来源
        srcf = QFormLayout()
        self.cb_source = QComboBox()
        self.cb_source.addItems([label for _v, label in _SOURCES])
        self.cb_source.setToolTip("官方接口:由软件后端代调视觉模型,无需自填 key,复用下方 AstroBin 后端配置"
                                  "(模型在服务器端配置,后续计次收费·测试期免费);\n"
                                  "自己的 API:填你自己的大模型供应商/密钥直连")
        self.cb_source.currentIndexChanged.connect(self._on_source_changed)
        srcf.addRow("接口来源:", self.cb_source)
        v2.addLayout(srcf)

        # 官方接口说明(选官方时显示)
        self.lbl_official = QLabel(
            "✓ 由软件后端代为调用视觉模型评审,无需在此填 key —— 复用下方「AstroBin 参考图后端」的"
            "Base URL / Pipeline key。所用模型在服务器端配置(便于随时升级)。后续按次计费,测试期免费。")
        self.lbl_official.setWordWrap(True); self.lbl_official.setObjectName("hint")
        v2.addWidget(self.lbl_official)

        # 官方接口·可选视觉模型覆盖。**默认留空** —— 后端注释写明「客户端一般不传 model,
        #   仅在显式覆盖时才用 d.model」。
        # 【★占位符里不要放没验证过的值(用户 2026-09-15「视觉模型总是报错」)】
        #   此前这里写着「例:deepseek/deepseek-v4-flash-vision-exp」,用户照着填了,结果每次评审
        #   不是 400「unsupported image」就是超时。
        #   实测澄清:**这个模型确实是视觉模型、确实收图像**(七牛模型广场标注输入=文本/图像),
        #   问题在**它没资源**——同一张图 PNG/JPEG × 1024/512px(909KB~15KB)四种组合全部失败,
        #   其中一次返回 502「Model resources are currently busy. Please try again later.」;
        #   而留空走服务器默认(kimi-k3)同一通道同一张图 ✅ 一次成功。
        #   即:体积/格式/尺寸全部排除,是该 Exp 模型本身的可用性问题。
        #   教训:**占位符/示例会被用户当推荐值直接抄,没实测过的值绝不能写进去。**
        self.official_model_box = QWidget()
        _omf = QFormLayout(self.official_model_box); _omf.setContentsMargins(0, 4, 0, 0)
        self.ed_official_model = QLineEdit()
        self.ed_official_model.setPlaceholderText("留空即可 —— 由服务器选用已验证的视觉模型")
        self.ed_official_model.setToolTip(
            "留空即可。这一栏只在你明确知道要换哪个模型时才填(比如换到调用价更低的模型)。" + chr(10)
            + "填错不会让评审中断——首选调不动会自动切到下面的备用模型;" + chr(10)
            + "但每 15 分钟里第一次评审会先白等它一轮(约 75 秒)。不确定就清空。")
        self.ed_official_model_fb = QLineEdit()
        self.ed_official_model_fb.setPlaceholderText("留空 = 服务器默认模型(推荐)")
        self.ed_official_model_fb.setToolTip(
            "首选模型调不动(超时 / 报错 / 没资源)时自动改用它。留空就是服务器端已验证的模型," + chr(10)
            + "通常不用填。首选失败后会被挂起 15 分钟不再重试,免得同一次处理里反复白等。")
        _omf.addRow("首选视觉模型:", self.ed_official_model)
        _omf.addRow("备用视觉模型:", self.ed_official_model_fb)
        # 降级链说明(用户 2026-09-15:deepseek 便宜但当天起可用性劣化 → 要能自动切走)
        _hint_fb = QLabel("首选填便宜的模型、备用留空即可:首选超时或报错会自动切到备用,评审不会因此中断;"
                          "失败的模型会被挂起一段时间,不会每次都重新白等。")
        _hint_fb.setWordWrap(True); _hint_fb.setObjectName("hint")
        _hint_fb.setContentsMargins(2, 4, 2, 2)
        _omf.addRow(_hint_fb)
        v2.addWidget(self.official_model_box)

        # 自己的 API(选 byo 时显示)
        self.byo_box = QWidget()
        f2 = QFormLayout(self.byo_box); f2.setContentsMargins(0, 0, 0, 0)
        self.cb_provider = QComboBox(); self.cb_provider.addItems(_BYO_PROVIDERS)
        self.ed_model = QLineEdit()
        self.ed_model.setPlaceholderText("如 claude-opus-4-8 / gpt-4o / moonshot-v1-vision …")
        self.ed_base = QLineEdit()
        self.ed_base.setPlaceholderText("openai_compatible 时填自定义端点,否则留空")
        self.ed_llm_key = QLineEdit()
        self.ed_llm_key.setEchoMode(QLineEdit.Password)
        self.chk_show_llm = QCheckBox("显示")
        rowk = QHBoxLayout()
        rowk.addWidget(self.ed_llm_key)
        rowk.addWidget(self.chk_show_llm)
        self.chk_show_llm.toggled.connect(
            lambda on: self.ed_llm_key.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        f2.addRow("供应商:", self.cb_provider)
        f2.addRow("模型:", self.ed_model)
        f2.addRow("Base URL:", self.ed_base)
        f2.addRow("API key:", rowk)
        v2.addWidget(self.byo_box)
        layout.addWidget(g2)

        # ---- AstroBin 参考图后端 ----
        g4 = QGroupBox("AstroBin 参考图检索(经自有后端 /pipeline 代理)")
        f4 = QFormLayout(g4)
        self.ed_ab_base = QLineEdit()
        self.ed_ab_base.setPlaceholderText("后端根地址,如 https://app.tickwhale.com")
        self.ed_ab_key = QLineEdit()
        self.ed_ab_key.setEchoMode(QLineEdit.Password)
        self.ed_ab_key.setPlaceholderText("对应后端 .env 的 PIPELINE_API_KEY")
        self.chk_show_ab = QCheckBox("显示")
        rowab = QHBoxLayout()
        rowab.addWidget(self.ed_ab_key)
        rowab.addWidget(self.chk_show_ab)
        self.chk_show_ab.toggled.connect(
            lambda on: self.ed_ab_key.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        f4.addRow("Base URL:", self.ed_ab_base)
        f4.addRow("Pipeline key:", rowab)
        layout.addWidget(g4)

        # ---- PixInsight ----
        g3 = QGroupBox("PixInsight")
        f3 = QFormLayout(g3)
        self.ed_pi = QLineEdit()
        self.ed_pi.setPlaceholderText("留空则自动探测 PixInsight.exe")
        f3.addRow("可执行文件:", self.ed_pi)
        layout.addWidget(g3)

        # ---- 调色风格偏置 ----
        g6 = QGroupBox("调色风格")
        f6 = QFormLayout(g6)
        self.sp_bluebias = QDoubleSpinBox()
        self.sp_bluebias.setRange(-0.20, 0.20); self.sp_bluebias.setSingleStep(0.01)
        self.sp_bluebias.setDecimals(3)
        self.sp_bluebias.setToolTip(
            "盘面的蓝相对绿提多少。0 = 完全跟随 SPCC 标定色,不做任何审美调整。"
            + chr(10) + "每 0.01 约等于蓝通道相对绿差 1%。只作用在**信号**上,背景不动;亮核处淡出。")
        f6.addRow("盘面偏蓝:", self.sp_bluebias)
        self.sp_warmbias = QDoubleSpinBox()
        self.sp_warmbias.setRange(-0.20, 0.20); self.sp_warmbias.setSingleStep(0.01)
        self.sp_warmbias.setDecimals(3)
        self.sp_warmbias.setToolTip(
            "盘面的红相对绿提多少。与「盘面偏蓝」一起构成二维风格向量。"
            + chr(10) + "两个都往正调 = 压低绿、盘面更通透;只调其一 = 单方向偏色。"
            + chr(10) + "为什么需要两个:从标定色到个人风格常常是「红和蓝都要抬」(等价于压绿),"
            + chr(10) + "单一个偏蓝滑块会把红一起压下去,方向正好相反,怎么加都没用。")
        f6.addRow("盘面偏暖:", self.sp_warmbias)
        self.sp_galsat = QDoubleSpinBox()
        self.sp_galsat.setRange(0.08, 0.35); self.sp_galsat.setSingleStep(0.01)
        self.sp_galsat.setDecimals(3)
        self.sp_galsat.setToolTip(
            "星系本体要提到多饱和。程序会先量当前盘面饱和度,差多少提多少,够了就不提。"
            + chr(10) + "调高 = 星系颜色更浓;调低 = 更克制。亮核有独立上限跟随此值,不会被提爆。"
            + chr(10) + "只作用在星系本体蒙版内,背景与星点不受影响。")
        f6.addRow("星系饱和:", self.sp_galsat)
        hint6 = QLabel("偏蓝/偏暖两个一起构成风格向量,0/0 = 完全信 SPCC 标定色。"
                       "参考标定(对着你手动处理的 M63 反解):偏蓝 +0.160、偏暖 +0.074 时,"
                       "盘区信号色比落到 [R/G 1.156, B/G 0.934],你手动版是 [1.160, 0.950]。"
                       "注意:**色相调对之后饱和度自己就对了** —— 同一组参数下信号饱和度 0.192,"
                       "你手动版 0.194。你手工库 9 张星系片的本体饱和其实比程序低,"
                       "「看着更有色彩」来自色相不是饱和度,所以星系饱和别往高调。"
                       )
        hint6.setWordWrap(True); hint6.setObjectName("hint")
        f6.addRow(hint6)
        layout.addWidget(g6)

        # ---- AI 后端路由 ----
        g5 = QGroupBox("AI 后端(降噪 / 修星 / 去星 的三级路由)")
        v5 = QVBoxLayout(g5)
        self.chk_allow_paid = QCheckBox("允许收费 AI 后端(rc-astro BXT / SXT / NXT)")
        self.chk_allow_paid.setToolTip(
            "勾选:装了 rc-astro 就优先用(效果最好,收费 · 需授权额度)。\n"
            "取消:**强制免费路线**(SASpro cosmicclarity / StarNet2 / DeepSNR),即便装了 rc-astro 也不调用。\n"
            "免费管线始终保留。各后端是否已装 + 安装地址见主界面「插件体检」。")
        hint5 = QLabel("取消勾选=强制走免费路线(SASpro cosmicclarity(GPU AI)/ StarNet2 / DeepSNR)。"
                       "各后端安装状态与地址见主界面「插件体检」。")
        hint5.setWordWrap(True); hint5.setObjectName("hint")
        v5.addWidget(self.chk_allow_paid)
        v5.addWidget(hint5)
        layout.addWidget(g5)

        layout.addStretch(1)
        # ---- 吸底工具条(始终可见,不随内容滚动)----
        foot = QFrame(); foot.setObjectName("actionbar")
        btns = QHBoxLayout(foot); btns.setContentsMargins(24, 12, 24, 12); btns.setSpacing(9)
        self.lbl_status = QLabel(""); self.lbl_status.setObjectName("sub")
        self.lbl_status.setWordWrap(True)
        btn_save = QPushButton("保存"); btn_save.setObjectName("primary")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("关闭")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        btns.addWidget(self.lbl_status, 1)
        btns.addWidget(btn_close, 0)
        btns.addWidget(btn_save, 0)
        self._outer.addWidget(foot)
        # 打开时给一个既放得下又不超出屏幕的尺寸(内容仍可滚动)
        try:
            app = QApplication.instance()
            av = app.primaryScreen().availableGeometry() if app else None
            if av is not None:
                self.resize(min(760, av.width() - 80), min(900, av.height() - 80))
        except Exception:
            self.resize(760, 860)

    def _polish(self):
        """分组框内边距 + 表单行距(之前太挤):组框走布局 contentsMargins,
        所有 QFormLayout(含嵌套的 byo 表单)统一加大垂直/水平间距、标签右对齐。"""
        for gb in self.findChildren(QGroupBox):
            lay = gb.layout()
            if lay is None:
                continue
            m = lay.contentsMargins()
            # byo_box 那种内嵌 0 边距的表单不强加外距;其余组框给足内边距
            if (m.left() + m.top() + m.right() + m.bottom()) > 0 or isinstance(lay, QVBoxLayout):
                lay.setContentsMargins(16, 20, 16, 16)
            if lay.spacing() < 12:
                lay.setSpacing(12)
        # 【跨分组对齐(用户 2026-09-15「样式也很丑」)】每个 QFormLayout 各自按**本组**最长标签
        #   定列宽 → 各组的字段起始位置参差不齐,整页看上去是散的。给所有标签一个统一的最小列宽,
        #   字段就在同一条竖线上起始。
        for fl in self.findChildren(QFormLayout):
            fl.setVerticalSpacing(12)
            fl.setHorizontalSpacing(14)
            fl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fl.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
            for i in range(fl.rowCount()):
                it = fl.itemAt(i, QFormLayout.LabelRole)
                w = it.widget() if it is not None else None
                if w is not None:
                    w.setMinimumWidth(104)
        # 数值框给固定宽度:它们只放 3~5 个字符,让它跟着表单拉满会显得空且各组不齐
        for sp in self.findChildren(QDoubleSpinBox):
            sp.setFixedWidth(118)
            sp.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # 说明文字统一留白,别贴着控件
        for lb in self.findChildren(QLabel):
            if lb.objectName() == "hint":
                lb.setContentsMargins(2, 4, 2, 2)
        # 官方接口说明:上下留白,别贴着下拉与下一组
        self.lbl_official.setContentsMargins(2, 6, 2, 8)

    def _on_source_changed(self, idx):
        """接口来源切换:官方→只显示说明;自己的API→显示供应商/模型/端点/key;不启用→都藏。"""
        src = _SOURCES[idx][0] if 0 <= idx < len(_SOURCES) else ""
        self.byo_box.setVisible(src == "byo")
        self.lbl_official.setVisible(src == "official")
        self.official_model_box.setVisible(src == "official")

    def _load_into_fields(self):
        s = self.settings
        self.ed_astro_key.setText(s.get("astrometry_api_key", ""))
        llm = s.get("llm", {})
        prov = llm.get("provider", "")
        # provider → 接口来源:tickwhale=官方、空=不启用、其余=自己的 API
        src = "official" if prov == "tickwhale" else ("byo" if prov else "")
        self.cb_source.setCurrentIndex([v for v, _ in _SOURCES].index(src))
        if prov in _BYO_PROVIDERS:
            self.cb_provider.setCurrentIndex(_BYO_PROVIDERS.index(prov))
        self.ed_model.setText(llm.get("model", ""))
        self.ed_official_model.setText(llm.get("model", "") if prov == "tickwhale" else "")
        self.ed_official_model_fb.setText(llm.get("model_fallback", "") if prov == "tickwhale" else "")
        self.ed_base.setText(llm.get("base_url", ""))
        self.ed_llm_key.setText(llm.get("api_key", ""))
        self._on_source_changed(self.cb_source.currentIndex())
        ab = s.get("astrobin_ref", {})
        self.ed_ab_base.setText(ab.get("base_url", ""))
        self.ed_ab_key.setText(ab.get("api_key", ""))
        self.ed_pi.setText(s.get("pixinsight_exe", ""))
        self.chk_allow_paid.setChecked(bool(s.get("ai_backend", {}).get("allow_paid", True)))
        try:
            self.sp_bluebias.setValue(float(s.get("disc_blue_bias", 0.0)))
            self.sp_warmbias.setValue(float(s.get("disc_warm_bias", 0.0)))
            self.sp_galsat.setValue(float(s.get("galaxy_sat_target", 0.15)))
        except (TypeError, ValueError):
            self.sp_bluebias.setValue(0.0)
            self.sp_warmbias.setValue(0.0)
            self.sp_galsat.setValue(0.15)

    def _save(self):
        s = config.load_settings()
        s["astrometry_api_key"] = self.ed_astro_key.text().strip()
        s["pixinsight_exe"] = self.ed_pi.text().strip()
        src = _SOURCES[self.cb_source.currentIndex()][0]
        if src == "official":
            # 官方接口:内部 provider=tickwhale;base/key 用 AstroBin 后端;model **可选覆盖**服务器默认
            #   (留空=服务器定;填了传给后端换模型,如 deepseek 视觉。用户 2026-09-06)。
            #   model_fallback = 首选调不动时的备选,留空 = 服务器默认(见 critic._with_fallback)。
            s["llm"] = {"provider": "tickwhale", "model": self.ed_official_model.text().strip(),
                        "model_fallback": self.ed_official_model_fb.text().strip(),
                        "base_url": "", "api_key": ""}
        elif src == "byo":
            s["llm"] = {
                "provider": self.cb_provider.currentText().strip(),
                "model": self.ed_model.text().strip(),
                "base_url": self.ed_base.text().strip(),
                "api_key": self.ed_llm_key.text().strip(),
            }
        else:
            s["llm"] = {"provider": "", "model": "", "base_url": "", "api_key": ""}
        s["astrobin_ref"] = {
            "base_url": self.ed_ab_base.text().strip(),
            "api_key": self.ed_ab_key.text().strip(),
        }
        s["ai_backend"] = {"allow_paid": self.chk_allow_paid.isChecked()}
        s["disc_blue_bias"] = round(float(self.sp_bluebias.value()), 3)
        s["disc_warm_bias"] = round(float(self.sp_warmbias.value()), 3)
        s["galaxy_sat_target"] = round(float(self.sp_galsat.value()), 3)
        try:
            config.save_settings(s)
            self.lbl_status.setText(f"已保存 → {config.SETTINGS_FILE}")
        except OSError as e:
            QMessageBox.critical(self, "保存失败", str(e))


def main() -> int:
    app = QApplication(sys.argv)
    # 单独运行时也套上主窗口的深色样式(延迟导入,避免与 app_ui 形成循环导入)
    try:
        from .app_ui import DARK, qss
        app.setStyleSheet(qss(DARK))
    except Exception:
        pass
    w = SettingsWindow()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
