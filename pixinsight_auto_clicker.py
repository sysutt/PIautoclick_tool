"""
PixInsight AnnotateImage 自动点击工具
=======================================
自动检测 AnnotateImage 的长时间优化弹窗并点击"是/Yes"，
当检测到保存对话框时自动停止。

用法：
    双击「启动自动点击器.bat」
    或运行：python pixinsight_auto_clicker.py

打包为exe：
    双击「build_exe.bat」
    或运行：pyinstaller --onefile --windowed --name "PixInsight自动点击器" pixinsight_auto_clicker.py
"""

import sys
import time
import threading
import win32gui
import win32api
import win32con
import uiautomation as auto
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QGroupBox, QCheckBox, QSpinBox,
    QFormLayout, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QTextCursor, QIcon


class QtMaster:
    """Qt 窗口检测工具"""
    @staticmethod
    def is_qt_window(class_name):
        """判断一个窗口类名是否属于 Qt 窗口"""
        if not class_name:
            return False
        lower = class_name.lower()
        # Qt 窗口类名特征: Qt5..., Qt6..., QWindow, QWidget, QDialog 等
        return (
            lower.startswith("qt")
            or lower.startswith("qwindow")
            or lower.startswith("qwidget")
            or lower.startswith("qdialog")
            or "qwindow" in lower
        )


# ============================================================
# 窗口检测逻辑 (在独立线程中运行，避免阻塞 GUI)
# ============================================================

class PixInsightMonitor(QObject):
    """PixInsight 弹窗监视器，运行在后台线程中"""

    # 信号: 向 GUI 发送日志消息
    log_signal = pyqtSignal(str)
    # 信号: 状态更新
    status_signal = pyqtSignal(str)
    # 信号: 检测到保存对话框时发出
    save_dialog_detected = pyqtSignal()
    # 信号: 点击了确认按钮
    confirmed_signal = pyqtSignal()

    # 匹配的目标对话框文本（包含即匹配，不区分大小写）
    TARGET_TEXTS = [
        "the label placement optimization task is taking a long time",
        "label placement optimization",
        "taking a long time",
        "do you really want to continue",
        "you may prefer adjusting some layer parameters",
        "achieve a more reasonable image annotation",
    ]

    # 匹配的保存对话框标题文本
    SAVE_DIALOG_TEXTS = [
        "另存为",          # 中文
        "save as",         # 英文
        "save annotated",  # 英文
        "annotated image", # 英文
        "保存",            # 中文保存
        "save file",       # 英文
    ]

    # 需要点击的按钮文本（匹配子窗口文本，忽略 & 快捷键符号）
    YES_BUTTON_TEXTS = [
        "是(&Y)", "是(&y)", "是",   # 中文
        "Yes", "&Yes", "yes",       # 英文
        "Continue", "continue",     # 英文继续
        "确认", "确定", "确定(&O)",  # 中文确认
    ]

    def __init__(self, poll_interval=0.5, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread = None
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._debug = False

    def start(self):
        """启动后台监控线程"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self.log_signal.emit("🟢 监控已启动...")

    def stop(self):
        """停止后台监控线程"""
        self._running = False
        self._stop_event.set()
        self.log_signal.emit("🔴 监控已停止")

    def is_running(self):
        return self._running

    def set_poll_interval(self, interval):
        self._poll_interval = interval

    # --------------------------------------------------
    # 核心：枚举所有顶级窗口
    # --------------------------------------------------
    def _monitor_loop(self):
        """监控循环：混合使用 win32 和 UI Automation 检测弹窗"""
        # 重要：在后台线程中初始化 COM（UI Automation 需要）
        auto.InitializeUIAutomationInCurrentThread()
        skip_count = 0
        while not self._stop_event.is_set():
            try:
                self._check_windows(show_all=False)
                skip_count += 1

                # ---- UI Automation 检测（主方案）----
                if skip_count % 3 == 0:
                    found = self._uia_search_dialog()
                    if not found and skip_count % 12 == 0:
                        found = self._uia_search_yes_button()
                    if found and self._debug:
                        self.log_signal.emit("✅ UIA 检测到弹窗并已处理")

                if self._debug and skip_count % 30 == 0:
                    self.log_signal.emit("🔍 监控运行中...")

            except Exception as e:
                self.log_signal.emit(f"⚠️ 检测异常: {e}")
            self._stop_event.wait(self._poll_interval)

    # --------------------------------------------------
    # UI Automation 检测方法
    # --------------------------------------------------
    def _uia_search_dialog(self):
        """主方案：使用 uiautomation 控件类直接搜索"""
        try:
            # 方法1：直接在 PixInsight 窗口中搜索 Yes 按钮（最快最准）
            btn = auto.ButtonControl(
                searchDepth=5,
                Name="Yes",
                ClassName="QPushButton"
            )
            if btn.Exists(maxSearchSeconds=0.5):
                self.log_signal.emit(f"✅ UIA 找到 Yes 按钮 (QPushButton)!")
                btn.Click()
                return True

            # 方法2：找 AnnotateImage 对话框，在其中找 Yes 按钮
            dlg = auto.WindowControl(
                searchDepth=5,
                Name="AnnotateImage",
                ClassName="QDialog"
            )
            if dlg.Exists(maxSearchSeconds=0.5):
                self.log_signal.emit(f"✅ UIA 找到 AnnotateImage 对话框")
                btn = auto.ButtonControl(
                    searchFromControl=dlg,
                    searchDepth=2,
                    Name="Yes"
                )
                if btn.Exists(maxSearchSeconds=0.3):
                    self.log_signal.emit(f"✅ UIA 在对话框中点击 Yes!")
                    btn.Click()
                    return True

            # 方法3：全树搜索 Yes 按钮
            btn = auto.ButtonControl(searchDepth=6, Name="Yes")
            if btn.Exists(maxSearchSeconds=0.5):
                self.log_signal.emit(f"✅ UIA 全局找到 Yes!")
                btn.Click()
                return True

        except Exception as e:
            if self._debug:
                self.log_signal.emit(f"UIA err: {e}")
        return False

    def _uia_search_yes_button(self):
        """兜底：直接搜索确认按钮"""
        for t in ["是(&Y)", "是", "Yes", "Continue", "确认", "确定"]:
            btn = self._uia_recursive_find_button(t, 5)
            if btn:
                self.log_signal.emit(f"✅ UIA 兜底: \"{btn.Name}\"")
                btn.Click()
                return True
        return False

    def _uia_recursive_find(self, text, depth):
        """递归搜索包含指定文本的控件（优先在 PixInsight 窗口中搜索）"""
        try:
            root = auto.GetRootControl()
            # 先找 PixInsight / AnnotateImage 窗口，缩小搜索范围
            pi_window = None
            for child in root.GetChildren():
                try:
                    name = (child.Name or "").lower()
                    if "pixinsight" in name or "annotate" in name:
                        pi_window = child
                        break
                except:
                    pass
            # 如果找到了 PixInsight 窗口，优先在其中搜索
            if pi_window:
                found = self._uia_recursive_search(pi_window, text.lower(), depth)
                if found:
                    return found
            # 没找到则全树搜索
            return self._uia_recursive_search(root, text.lower(), depth)
        except:
            return None

    def _uia_recursive_search(self, parent, text_lower, depth):
        if depth <= 0 or self._stop_event.is_set():
            return None
        try:
            for child in parent.GetChildren():
                try:
                    if text_lower in (child.Name or "").lower():
                        return child
                except:
                    pass
                found = self._uia_recursive_search(child, text_lower, depth - 1)
                if found:
                    return found
        except:
            pass
        return None

    def _uia_recursive_find_button(self, text, depth):
        """递归搜索指定文本的按钮"""
        try:
            root = auto.GetRootControl()
            return self._uia_recursive_button_search(root, text.lower().replace("&", ""), depth)
        except:
            return None

    def _uia_recursive_button_search(self, parent, text_lower, depth):
        if depth <= 0 or self._stop_event.is_set():
            return None
        try:
            for child in parent.GetChildren():
                try:
                    name = (child.Name or "").lower().replace("&", "")
                    ctype = str(child.ControlTypeName).lower()
                    if "button" in ctype:
                        if text_lower in name or name == text_lower:
                            return child
                except:
                    pass
                found = self._uia_recursive_button_search(child, text_lower, depth - 1)
                if found:
                    return found
        except:
            pass
        return None

    def _uia_find_yes_button(self, parent):
        """在父控件中找确认按钮"""
        for text in ["是(&Y)", "是", "Yes", "Continue", "确认", "确定", "OK"]:
            try:
                for child in parent.GetChildren():
                    try:
                        name = (child.Name or "").lower().replace("&", "")
                        ctype = str(child.ControlTypeName).lower()
                        if "button" in ctype:
                            t = text.lower().replace("&", "")
                            if t in name or name == t:
                                return child
                    except:
                        pass
            except:
                pass
        return None

    def set_debug(self, enabled):
        """开启/关闭调试日志"""
        self._debug = enabled
        if enabled:
            self.log_signal.emit("🐛 调试模式已开启，将显示所有检测到的窗口")

    def _check_windows(self, show_all=False):
        """遍历所有窗口，查找匹配的对话框
        show_all: 为 True 时在调试模式下显示所有窗口（手动扫描用）
        """
        all_visible = [] if (self._debug and show_all) else None

        def enum_callback(hwnd, _):
            if self._stop_event.is_set():
                return False

            if not win32gui.IsWindowVisible(hwnd):
                return True

            title = self._get_window_text(hwnd)
            cls = self._get_window_class(hwnd)
            title_lower = title.lower()

            # 记录信息用于调试
            if all_visible is not None and title:
                all_visible.append((hwnd, title, cls, 'TOP'))

            # --- 检查1: 保存对话框（顶层窗口）---
            if self._is_save_dialog(hwnd):
                self._on_save_dialog_found(hwnd, cls, title)
                return False

            # --- 检查2: 目标弹窗（顶层窗口）---
            if self._is_target_dialog(hwnd):
                self._on_target_found(hwnd, cls, title)
                return True

            # --- 检查3: 对 PixInsight 相关窗口，扫描其子窗口 ---
            # Qt 程序的弹窗可能以子窗口形式存在
            is_pi_related = (
                "pixinsight" in title_lower
                or "annotate" in title_lower
            )
            if is_pi_related or QtMaster.is_qt_window(cls):
                self._scan_child_windows(hwnd, cls, title)

            return True

        win32gui.EnumWindows(enum_callback, None)

        # 调试输出
        if all_visible is not None and all_visible:
            seen = set()
            unique_windows = []
            for hwnd, t, c, level in all_visible:
                key = (c, t)
                if key not in seen:
                    seen.add(key)
                    unique_windows.append((hwnd, t, c))

            if unique_windows:
                self.log_signal.emit(f"📋 当前可见窗口 ({len(unique_windows)} 个):")
                for hwnd, t, c in unique_windows:
                    self.log_signal.emit(f"  [{c}] \"{t}\"")
                    children = self._get_child_texts(hwnd)
                    if children:
                        for ct in children[:5]:
                            self.log_signal.emit(f"    ├─ \"{ct[:70]}\"")
                    # 对 AnnotateImage/PixInsight 窗口递归扫描子窗口
                    tl = t.lower()
                    if "annotate" in tl or "pixinsight" in tl:
                        self._debug_scan_children(hwnd, "    ")

    def _debug_scan_children(self, hwnd, indent="  "):
        """递归打印子窗口结构（调试用）"""
        import itertools
        def enum_all(h, _):
            if self._stop_event.is_set():
                return False
            if not win32gui.IsWindowVisible(h):
                return True
            ct = self._get_window_text(h)
            cc = self._get_window_class(h)
            if ct or cc.startswith("Qt"):
                self.log_signal.emit(f"{indent}├─ [{cc}] \"{ct}\"")
                # 继续递归
                def deeper(h2, _2):
                    if self._stop_event.is_set():
                        return False
                    if not win32gui.IsWindowVisible(h2):
                        return True
                    ct2 = self._get_window_text(h2)
                    cc2 = self._get_window_class(h2)
                    if ct2 or cc2.startswith("Qt"):
                        self.log_signal.emit(f"{indent}│  ├─ [{cc2}] \"{ct2}\"")
                    return True
                win32gui.EnumChildWindows(h, deeper, None)
            return True
        win32gui.EnumChildWindows(hwnd, enum_all, None)

    def _scan_child_windows(self, hwnd_parent, parent_cls, parent_title):
        """检查一个父窗口的所有子窗口中是否有目标弹窗"""
        def enum_child(child_hwnd, _):
            if self._stop_event.is_set():
                return False

            if not win32gui.IsWindowVisible(child_hwnd):
                return True

            child_title = self._get_window_text(child_hwnd)
            child_cls = self._get_window_class(child_hwnd)

            # 检查子窗口本身
            if self._is_target_dialog(child_hwnd):
                self.log_signal.emit(f"✅ 在子窗口中发现目标: [{child_cls}] \"{child_title}\"")
                self.log_signal.emit(f"   父窗口: [{parent_cls}] \"{parent_title}\"")
                self._on_target_found(child_hwnd, child_cls, child_title)
                return False

            # 检查子窗口的文本内容是否匹配（子窗口可能是一个没有标题的 QDialog）
            child_text = self._get_dialog_text(child_hwnd).lower()
            if any(kw in child_text for kw in self.TARGET_TEXTS):
                self.log_signal.emit(f"✅ 子窗口内容匹配: [{child_cls}] \"{child_title}\"")
                self.log_signal.emit(f"   父窗口: [{parent_cls}] \"{parent_title}\"")
                # 显示匹配到的内容片段
                for kw in self.TARGET_TEXTS:
                    if kw in child_text:
                        idx = child_text.find(kw)
                        snippet = child_text[max(0,idx-10):idx+len(kw)+30]
                        self.log_signal.emit(f"   匹配文本: \"{snippet}\"")
                        break
                self._on_target_found(child_hwnd, child_cls, child_title)
                return False

            return True

        win32gui.EnumChildWindows(hwnd_parent, enum_child, None)

    def _on_target_found(self, hwnd, cls, title):
        """找到目标弹窗后的处理"""
        self.status_signal.emit("✅ 检测到目标弹窗，正在点击确认...")
        self.log_signal.emit(f"✅ 找到目标对话框: [{cls}] \"{title}\"")
        children = self._get_child_texts(hwnd)
        for ct in children[:8]:
            self.log_signal.emit(f"   ├─ \"{ct[:80]}\"")
        self.log_signal.emit("✅ 正在点击确认按钮...")
        if self._click_yes_button(hwnd):
            self.confirmed_signal.emit()
            self.log_signal.emit("👍 已点击确认按钮")
        else:
            self.log_signal.emit("⚠️ 未找到确认按钮，尝试模拟回车...")
            self._press_enter(hwnd)
            self.log_signal.emit("⌨️ 已模拟回车键")

    def _on_save_dialog_found(self, hwnd, cls, title):
        """找到保存对话框后的处理"""
        self.status_signal.emit("📂 检测到保存对话框，自动停止")
        self.log_signal.emit("📂 检测到保存对话框，自动停止监控")
        self.save_dialog_detected.emit()
        self._stop_event.set()

    def _get_child_texts(self, hwnd, max_items=10):
        """获取窗口的所有子文本"""
        texts = []
        def enum_child(h, _):
            ct = self._get_window_text(h)
            if ct and len(texts) < max_items:
                texts.append(ct)
            return True
        win32gui.EnumChildWindows(hwnd, enum_child, None)
        return texts

    # --------------------------------------------------
    # 对话框识别
    # --------------------------------------------------
    def _get_window_text(self, hwnd):
        """安全获取窗口文本"""
        try:
            length = win32gui.GetWindowTextLength(hwnd)
            if length > 0:
                return win32gui.GetWindowText(hwnd)
        except:
            pass
        return ""

    def _get_window_class(self, hwnd):
        """安全获取窗口类名"""
        try:
            return win32gui.GetClassName(hwnd)
        except:
            return ""

    def _is_target_dialog(self, hwnd):
        """判断是否是目标警告对话框（多策略，宽松匹配）"""
        cls = self._get_window_class(hwnd)
        title = self._get_window_text(hwnd)
        title_lower = title.lower()

        # 获取窗口内所有子窗口文本
        dialog_text = self._get_dialog_text(hwnd).lower()

        # 检查内容是否包含目标关键词
        text_match = any(kw in dialog_text for kw in self.TARGET_TEXTS)

        if not text_match:
            return False

        # 只要内容匹配了，进一步放宽窗口类型的判断
        # PixInsight 的 Qt 对话框类名可能是 QDialog、#32770、Qt5QDialog 等
        # 也可能没有标准对话框类名，但只要有文本匹配就应该处理
        cls_lower = cls.lower()
        is_likely_dialog = (
            "dialog" in cls_lower
            or "#32770" in cls
            or "qt" in cls_lower
            or "qwidget" in cls_lower
            or title_lower.startswith("annotate")  # 标题以 Annotate 开头
            or "pixinsight" in title_lower
        )

        # 如果是内容匹配了但不是标准对话框，日志记录下来
        if not is_likely_dialog:
            if self._debug:
                self.log_signal.emit(f"🔍 内容匹配但窗口类型非标准 (class={cls}): \"{title}\"")
            # 仍然尝试处理——只要有内容匹配就尝试点击
            return True

        return True

    def _is_save_dialog(self, hwnd):
        """判断是否是保存文件对话框"""
        title = self._get_window_text(hwnd).lower()
        cls = self._get_window_class(hwnd)

        is_dialog = (
            "dialog" in cls.lower()
            or cls == "#32770"
            or cls == "#32771"
        )

        title_match = any(kw in title for kw in self.SAVE_DIALOG_TEXTS)

        return is_dialog and title_match

    def _get_dialog_text(self, hwnd):
        """递归收集对话框中所有子窗口文本"""
        texts = []

        def enum_child(hwnd_child, _):
            t = self._get_window_text(hwnd_child)
            if t:
                texts.append(t)
            return True

        win32gui.EnumChildWindows(hwnd, enum_child, None)
        return " ".join(texts)

    # --------------------------------------------------
    # 按钮点击
    # --------------------------------------------------
    def _find_button_by_text(self, hwnd_dialog):
        """在对话框中查找匹配文本的按钮"""
        found_buttons = []

        def enum_child(hwnd_child, _):
            cls = self._get_window_class(hwnd_child)
            if "button" in cls.lower():
                text = self._get_window_text(hwnd_child)
                if text:
                    clean_text = text.replace("&", "").strip()
                    for yes_text in self.YES_BUTTON_TEXTS:
                        yes_clean = yes_text.replace("&", "").strip()
                        if clean_text.lower() == yes_clean.lower():
                            found_buttons.append(hwnd_child)
                            break
            return True

        win32gui.EnumChildWindows(hwnd_dialog, enum_child, None)

        if found_buttons:
            return found_buttons[0]
        return None

    def _find_button_by_id(self, hwnd_dialog):
        """通过标准按钮 ID 查找确认按钮（IDOK = 1, IDYES = 6）"""
        for btn_id in [1, 6]:
            try:
                hwnd_btn = win32gui.GetDlgItem(hwnd_dialog, btn_id)
                if hwnd_btn and win32gui.IsWindowVisible(hwnd_btn):
                    return hwnd_btn
            except:
                pass
        return None

    def _press_enter(self, hwnd_dialog):
        """模拟按回车键（兜底方案）"""
        try:
            win32gui.SetForegroundWindow(hwnd_dialog)
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            time.sleep(0.02)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            self.log_signal.emit(f"❌ 模拟回车失败: {e}")
            return False

    def _click_yes_button(self, hwnd_dialog):
        """点击确认按钮（多种方法）"""
        hwnd_btn = self._find_button_by_text(hwnd_dialog)

        if hwnd_btn is None:
            hwnd_btn = self._find_button_by_id(hwnd_dialog)

        if hwnd_btn:
            try:
                win32api.SendMessage(hwnd_btn, win32con.BM_CLICK, 0, 0)
                return True
            except Exception as e:
                self.log_signal.emit(f"❌ 点击按钮失败: {e}")
                return False

        return False



# ============================================================
# 主窗口 GUI
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.monitor = PixInsightMonitor()
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        self.setWindowTitle("PixInsight AnnotateImage 自动点击器")
        self.setFixedSize(540, 480)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # ---- 标题 ----
        title = QLabel("🎯 PixInsight 标注弹窗自动点击器")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ---- 说明 ----
        desc = QLabel(
            "自动检测 AnnotateImage 的「标签布局优化耗时过长」弹窗并点击确认。\n"
            "当检测到「保存/另存为」对话框时自动停止。"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ---- 控制区域 ----
        ctrl_group = QGroupBox("控制")
        ctrl_layout = QVBoxLayout(ctrl_group)

        # 按钮行
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 启动监控")
        self.btn_start.setMinimumHeight(40)
        self.btn_stop = QPushButton("⏹ 停止监控")
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.setEnabled(False)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        ctrl_layout.addLayout(btn_layout)

        # 按钮行2: 扫描和调试
        btn_layout2 = QHBoxLayout()
        self.btn_scan = QPushButton("📡 立即扫描")
        self.btn_scan.setMinimumHeight(36)
        self.chk_debug = QCheckBox("🐛 调试模式")
        self.chk_debug.setToolTip("开启后显示所有检测到的窗口信息")
        btn_layout2.addWidget(self.btn_scan)
        btn_layout2.addWidget(self.chk_debug)
        btn_layout2.addStretch()
        ctrl_layout.addLayout(btn_layout2)

        # 参数行
        param_layout = QFormLayout()
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(100, 5000)
        self.spin_interval.setValue(500)
        self.spin_interval.setSuffix(" 毫秒")
        self.spin_interval.setSingleStep(100)
        self.spin_interval.setToolTip("检测间隔越短响应越快，但 CPU 占用略高")
        param_layout.addRow("检测间隔:", self.spin_interval)

        self.chk_auto_stop = QCheckBox("检测到保存对话框时自动停止 ✓")
        self.chk_auto_stop.setChecked(True)
        param_layout.addRow("", self.chk_auto_stop)

        ctrl_layout.addLayout(param_layout)
        layout.addWidget(ctrl_group)

        # ---- 状态显示 ----
        self.label_status = QLabel("⏸ 就绪，点击「启动监控」开始")
        self.label_status.setAlignment(Qt.AlignCenter)
        status_font = QFont()
        status_font.setPointSize(11)
        status_font.setBold(True)
        self.label_status.setFont(status_font)
        layout.addWidget(self.label_status)

        # ---- 日志 ----
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(200)
        self.log_view.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_group, stretch=1)

        self._append_log("🟢 程序已启动，等待操作...")

    def _connect_signals(self):
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_scan.clicked.connect(self._on_scan)
        self.chk_debug.stateChanged.connect(self._on_debug_changed)
        self.spin_interval.valueChanged.connect(self._on_interval_changed)

        self.monitor.log_signal.connect(self._append_log)
        self.monitor.status_signal.connect(self._update_status)
        self.monitor.save_dialog_detected.connect(self._on_save_dialog)
        self.monitor.confirmed_signal.connect(self._on_confirmed)

    def _on_start(self):
        self.monitor.set_poll_interval(self.spin_interval.value() / 1000.0)
        self.monitor.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.spin_interval.setEnabled(False)
        self._update_status("🟢 监控运行中...")

    def _on_stop(self):
        self.monitor.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.spin_interval.setEnabled(True)
        self._update_status("⏸ 已手动停止")

    def _on_interval_changed(self, val):
        if self.monitor.is_running():
            self.monitor.set_poll_interval(val / 1000.0)

    def _on_save_dialog(self):
        """检测到保存对话框，自动停止"""
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.spin_interval.setEnabled(True)
        self._update_status("📂 任务完成 - 保存对话框已弹出")
        QMessageBox.information(
            self,
            "🎉 任务完成",
            "检测到保存对话框，自动停止监控。\n\n"
            "您现在可以正常保存标注结果了。\n"
            "如需继续标注新图像，请点击「启动监控」。"
        )

    def _on_scan(self):
        """立即手动扫描一次窗口"""
        self._append_log("📡 手动扫描启动...")
        self.monitor._check_windows(show_all=True)
        self._append_log("📡 扫描完成")

    def _on_debug_changed(self, state):
        """调试模式切换"""
        enabled = state == Qt.Checked
        self.monitor.set_debug(enabled)
        if enabled:
            self._append_log("🐛 调试模式已开启")
        else:
            self._append_log("🐛 调试模式已关闭")

    def _on_confirmed(self):
        pass

    def _update_status(self, text):
        self.label_status.setText(text)

    def _append_log(self, msg):
        from PyQt5.QtCore import QDateTime
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        self.log_view.append(f"[{ts}] {msg}")
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)

    def closeEvent(self, event):
        self.monitor.stop()
        event.accept()


# ============================================================
# 入口
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationName("PixInsight自动点击器")
    app.setApplicationDisplayName("PixInsight自动点击器")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

