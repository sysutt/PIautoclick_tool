"""配置界面(PyQt5)。

提前填入并持久保存敏感设置(astrometry.net API key、LLM 供应商/模型/key、
PixInsight 路径),存到本地 _config/settings.json(不进 git)。

运行:
    python -m orchestrator.settings_ui
"""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QFormLayout, QGroupBox, QLineEdit,
    QComboBox, QPushButton, QLabel, QHBoxLayout, QMessageBox, QCheckBox,
)

from . import config

_PROVIDERS = ["", "anthropic", "openai", "kimi", "deepseek", "openai_compatible"]


class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = config.load_settings()
        self._build()
        self._load_into_fields()

    def _build(self):
        self.setWindowTitle("深空自动后期 · 配置")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        title = QLabel("配置(保存在本机 _config/settings.json,不上传、不进版本库)")
        title.setWordWrap(True)
        layout.addWidget(title)

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
        g2 = QGroupBox("多模态 LLM 评委(用于图像质量评估,需视觉模型)")
        f2 = QFormLayout(g2)
        self.cb_provider = QComboBox()
        self.cb_provider.addItems(_PROVIDERS)
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
        layout.addWidget(g2)

        # ---- PixInsight ----
        g3 = QGroupBox("PixInsight")
        f3 = QFormLayout(g3)
        self.ed_pi = QLineEdit()
        self.ed_pi.setPlaceholderText("留空则自动探测 PixInsight.exe")
        f3.addRow("可执行文件:", self.ed_pi)
        layout.addWidget(g3)

        # ---- 按钮 ----
        btns = QHBoxLayout()
        self.lbl_status = QLabel("")
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        btns.addWidget(self.lbl_status)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _load_into_fields(self):
        s = self.settings
        self.ed_astro_key.setText(s.get("astrometry_api_key", ""))
        llm = s.get("llm", {})
        prov = llm.get("provider", "")
        self.cb_provider.setCurrentIndex(_PROVIDERS.index(prov) if prov in _PROVIDERS else 0)
        self.ed_model.setText(llm.get("model", ""))
        self.ed_base.setText(llm.get("base_url", ""))
        self.ed_llm_key.setText(llm.get("api_key", ""))
        self.ed_pi.setText(s.get("pixinsight_exe", ""))

    def _save(self):
        s = config.load_settings()
        s["astrometry_api_key"] = self.ed_astro_key.text().strip()
        s["pixinsight_exe"] = self.ed_pi.text().strip()
        s["llm"] = {
            "provider": self.cb_provider.currentText().strip(),
            "model": self.ed_model.text().strip(),
            "base_url": self.ed_base.text().strip(),
            "api_key": self.ed_llm_key.text().strip(),
        }
        try:
            config.save_settings(s)
            self.lbl_status.setText(f"已保存 → {config.SETTINGS_FILE}")
        except OSError as e:
            QMessageBox.critical(self, "保存失败", str(e))


def main() -> int:
    app = QApplication(sys.argv)
    w = SettingsWindow()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
