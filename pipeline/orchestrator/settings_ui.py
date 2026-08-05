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
        # 视觉沿用主窗口:样式表挂在 QApplication 上,这里只需复用同一批 objectName
        self.setWindowTitle("TTAstroPiLot · 配置")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        head = QVBoxLayout(); head.setSpacing(4)
        banner = QLabel("配置"); banner.setObjectName("banner")
        title = QLabel("保存在本机 _config/settings.json,不上传、不进版本库")
        title.setObjectName("sub"); title.setWordWrap(True)
        head.addWidget(banner); head.addWidget(title)
        layout.addLayout(head)
        hair = QFrame(); hair.setObjectName("hairline"); hair.setFixedHeight(2)
        layout.addWidget(hair)

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

        # ---- 按钮 ----
        btns = QHBoxLayout(); btns.setSpacing(9)
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
        layout.addLayout(btns)

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
        for fl in self.findChildren(QFormLayout):
            fl.setVerticalSpacing(12)
            fl.setHorizontalSpacing(12)
            fl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fl.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        # 官方接口说明:上下留白,别贴着下拉与下一组
        self.lbl_official.setContentsMargins(2, 6, 2, 8)

    def _on_source_changed(self, idx):
        """接口来源切换:官方→只显示说明;自己的API→显示供应商/模型/端点/key;不启用→都藏。"""
        src = _SOURCES[idx][0] if 0 <= idx < len(_SOURCES) else ""
        self.byo_box.setVisible(src == "byo")
        self.lbl_official.setVisible(src == "official")

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
        self.ed_base.setText(llm.get("base_url", ""))
        self.ed_llm_key.setText(llm.get("api_key", ""))
        self._on_source_changed(self.cb_source.currentIndex())
        ab = s.get("astrobin_ref", {})
        self.ed_ab_base.setText(ab.get("base_url", ""))
        self.ed_ab_key.setText(ab.get("api_key", ""))
        self.ed_pi.setText(s.get("pixinsight_exe", ""))

    def _save(self):
        s = config.load_settings()
        s["astrometry_api_key"] = self.ed_astro_key.text().strip()
        s["pixinsight_exe"] = self.ed_pi.text().strip()
        src = _SOURCES[self.cb_source.currentIndex()][0]
        if src == "official":
            # 官方接口:内部 provider=tickwhale;model/base/key 留空(base/key 用 AstroBin 后端,模型服务器定)
            s["llm"] = {"provider": "tickwhale", "model": "", "base_url": "", "api_key": ""}
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
