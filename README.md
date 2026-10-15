# PixInsight Auto Clicker

自动点掉 PixInsight `AnnotateImage` 反复弹出的
*"Label placement optimization is taking a long time…"* 确认框,
并在出现"另存为"对话框时自动停止。

> 本仓库早期还包含深空照片自动后期系统(TTAstroPiLot,原 `pipeline/` 目录)。
> 2026-10-15 起它已独立为单独的项目,不再在本仓库维护。

## 使用

```bash
pip install pywin32 PyQt5 uiautomation
python pixinsight_auto_clicker.py        # 或双击 run.bat
pyinstaller PixInsightAutoClicker.spec   # 打包 → dist/PixInsightAutoClicker.exe
```

## 文件

| 文件 | 内容 |
|---|---|
| `pixinsight_auto_clicker.py` | 主程序 |
| `uia_debug.py` | 控件树调试 |
| `run.bat` | 启动 |
| `build.bat` / `PixInsightAutoClicker.spec` | 打包 |
