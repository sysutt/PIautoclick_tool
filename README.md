# PixInsight AnnotateImage 自动点击器

> 自动应对 PixInsight `AnnotateImage`（图像标注）脚本在长时间运行时反复弹出的
> **"Label placement optimization is taking a long time…"** 确认框，
> 让你无需守在电脑前手动点"是 / Yes"，并在标注完成、弹出保存对话框时**自动停止**。

一个带图形界面（PyQt5）的 Windows 小工具，用于把天文图像处理软件
[PixInsight](https://pixinsight.com/) 中 `AnnotateImage` 的重复性人工确认操作全自动化。

---

## 背景

PixInsight 的 `AnnotateImage` 在为深空图像添加标注（星表、网格、天体名称等）时，
标签布局优化（label placement optimization）可能非常耗时。每隔一段时间，
它就会弹出一个对话框询问是否继续：

> The label placement optimization task is taking a long time.
> Do you really want to continue?

对于需要长时间运行的大图或高密度标注，这个弹窗会反复出现，必须有人不断点击"是"，
非常影响批处理和无人值守的工作流。本工具在后台持续监视这些弹窗并自动点击确认，
直到标注结束、出现"另存为 / Save As"对话框时自动停下来。

## 功能特性

- **自动检测并确认**：后台监控目标弹窗，自动点击"是 / Yes / Continue / 确认 / 确定"。
- **中英文界面通吃**：同时匹配中文和英文的按钮与对话框文本。
- **双重检测引擎**：
  - Win32 `EnumWindows` / `EnumChildWindows` 遍历顶层与子窗口；
  - UI Automation（`uiautomation`）针对 Qt (`QPushButton` / `QDialog`) 控件精准定位，
    应对 PixInsight 这类 Qt 程序常见的非标准窗口结构。
- **智能自动停止**：检测到"另存为 / Save As / 保存"对话框时，判定任务完成并自动停止监控。
- **多种点击兜底**：按文本匹配按钮 → 按标准按钮 ID（IDOK/IDYES）→ 模拟回车键，层层兜底。
- **可调检测间隔**：100–5000 毫秒可调，在响应速度与 CPU 占用之间自由权衡。
- **实时日志 + 调试模式**：界面内滚动日志；调试模式可打印所有可见窗口及其子控件结构，
  方便排查匹配问题。
- **一键扫描**：手动触发一次窗口扫描，快速确认当前窗口是否被正确识别。

## 环境要求

- Windows（依赖 Win32 API 与 UI Automation）
- Python 3.11+（若使用打包好的 EXE 则无需 Python）
- 依赖库：

  ```bash
  pip install pywin32 PyQt5 uiautomation
  ```

## 使用方法

### 方式一：直接运行脚本

```bash
python pixinsight_auto_clicker.py
```

或双击 `run.bat`（会自动寻找系统中的 Python 解释器）。

### 方式二：使用打包好的 EXE（无需安装 Python）

自行构建（见下文）后，双击 `dist/PixInsightAutoClicker.exe` 即可。

### 操作步骤

1. 在 PixInsight 中启动 `AnnotateImage` 处理。
2. 打开本工具，按需设置"检测间隔"，点击 **▶ 启动监控**。
3. 工具会在后台自动点击每一次出现的"耗时过长"确认弹窗。
4. 标注完成、弹出保存对话框时，工具自动停止并提示任务完成，此时正常保存结果即可。

> 若弹窗没有被识别，可勾选 **🐛 调试模式** 后点击 **📡 立即扫描**，
> 在日志中查看当前窗口结构，据此调整匹配关键词。

## 打包为 EXE

需要先安装 PyInstaller：

```bash
pip install pyinstaller
```

然后任选其一：

- 双击 `build.bat`；
- 或运行：

  ```bash
  pyinstaller --onefile --windowed --name "PixInsightAutoClicker" pixinsight_auto_clicker.py
  ```

- 或使用现成的打包配置：

  ```bash
  pyinstaller PixInsightAutoClicker.spec
  ```

产物位于 `dist/PixInsightAutoClicker.exe`。

## 项目结构

| 文件 | 说明 |
| --- | --- |
| `pixinsight_auto_clicker.py` | 主程序：监控逻辑（`PixInsightMonitor`）+ 图形界面（`MainWindow`） |
| `uia_debug.py` | UI Automation 调试脚本，用于转储 `AnnotateImage` 对话框的实际控件树 |
| `run.bat` | 免命令行启动脚本，自动探测 Python 解释器 |
| `build.bat` | 一键打包为独立 EXE |
| `PixInsightAutoClicker.spec` | PyInstaller 打包配置 |

## 工作原理

监控线程（守护线程）以设定间隔循环执行：

1. **Win32 遍历**：枚举所有可见顶层窗口；对 PixInsight / Qt 相关窗口递归扫描子窗口，
   收集窗口文本并与目标关键词（如 `label placement optimization`、`taking a long time`）匹配。
2. **UI Automation 兜底**：每几个周期用 `uiautomation` 直接搜索 `Yes` / `QPushButton`
   或 `AnnotateImage` 对话框，命中即点击。
3. **确认点击**：找到目标弹窗后，依次尝试"按文本找按钮 → 按按钮 ID 找 → 模拟回车"。
4. **自动停止**：一旦检测到保存/另存为对话框，触发停止事件，结束监控。

## 免责声明

本工具通过窗口检测与模拟点击来自动化重复操作，仅用于辅助个人的 PixInsight 图像处理工作流。
使用者应自行确认自动点击行为符合预期，避免误点其他程序的对话框。
