"""
UI Automation 调试工具
用于检测 PixInsight AnnotateImage 对话框的实际 UIA 结构

用法：
    1. 在 PixInsight 中运行 AnnotateImage
    2. 等到弹窗出现（不要点击）
    3. 运行: python uia_debug.py
"""

import uiautomation as auto
import time


def dump_control_tree(control, indent=0, max_depth=5, max_children=20):
    """递归输出控件树"""
    if indent == 0:
        print(f"\n{'='*60}")
        print(f"UIA Tree Dump - Depth {max_depth}")
        print(f"{'='*60}")
    
    if max_depth <= 0:
        return
    
    try:
        name = control.Name or ""
        ctype = control.ControlTypeName or "?"
        cls = control.ClassName or ""
        rect = control.BoundingRectangle
        auto_id = control.AutomationId or ""
        
        prefix = "  " * indent
        info = f"{prefix}[{ctype}]"
        if name:
            info += f" \"{name[:60]}\""
        if cls:
            info += f" class:{cls}"
        if auto_id:
            info += f" id:{auto_id}"
        if rect:
            info += f" ({rect.left},{rect.top},{rect.right},{rect.bottom})"
        
        print(info)
        
        children = control.GetChildren()
        count = 0
        for child in children:
            if count >= max_children:
                print(f"{prefix}  ... ({len(children) - max_children} more children)")
                break
            dump_control_tree(child, indent + 1, max_depth - 1, max_children)
            count += 1
    except Exception as e:
        print(f"  {'  ' * indent}[Error: {e}]")


def find_annotate_window():
    """查找 AnnotateImage 或 PixInsight 窗口"""
    root = auto.GetRootControl()
    for child in root.GetChildren():
        name = (child.Name or "").lower()
        if "annotate" in name or "pixinsight" in name:
            return child
    return None


def find_text_controls(control, texts, max_depth=8, current_depth=0):
    """查找包含指定文本的控件"""
    results = []
    if current_depth > max_depth:
        return results
    
    try:
        name = (control.Name or "").lower()
        for text in texts:
            if text.lower() in name:
                results.append((control, text, current_depth))
                break
    except:
        pass
    
    try:
        for child in control.GetChildren():
            results.extend(find_text_controls(child, texts, max_depth, current_depth + 1))
    except:
        pass
    
    return results


def main():
    print("=" * 60)
    print("UI Automation Debug Tool for PixInsight")
    print("=" * 60)
    
    # 1. 查找 PixInsight/AnnotateImage 窗口
    pi_window = find_annotate_window()
    if pi_window:
        print(f"\n[1] Found PixInsight/Annotate window:")
        print(f"    Name: {pi_window.Name}")
        print(f"    Type: {pi_window.ControlTypeName}")
        print(f"    Class: {pi_window.ClassName}")
        
        # 2. 转储整个窗口的控件树
        print(f"\n[2] Dumping control tree (depth=4, max 15 children)...")
        dump_control_tree(pi_window, max_depth=4, max_children=15)
    else:
        print("\n[1] No PixInsight/Annotate window found!")
        print("    Searching all top-level windows...")
        root = auto.GetRootControl()
        for child in root.GetChildren():
            try:
                print(f"    [{child.ControlTypeName}] \"{child.Name[:50]}\"")
            except:
                pass
    
    # 3. 在整个 UIA 树中搜索目标文本
    print(f"\n[3] Searching for target texts in entire UIA tree...")
    target_texts = [
        "label placement optimization",
        "taking a long time",
        "do you really want to continue",
        "you may prefer adjusting",
        "more reasonable image annotation",
    ]
    
    root = auto.GetRootControl()
    found = find_text_controls(root, target_texts, max_depth=6)
    
    if found:
        print(f"    Found {len(found)} matching controls:")
        for ctrl, text, depth in found:
            try:
                print(f"    - Depth {depth}: [{ctrl.ControlTypeName}] \"{ctrl.Name[:80]}\"")
                # 显示父控件
                parent = ctrl
                for i in range(3):
                    parent = parent.GetParentControl()
                    if parent:
                        print(f"      Parent {i+1}: [{parent.ControlTypeName}] \"{parent.Name[:60]}\"")
            except:
                pass
    else:
        print(f"    No matching controls found!")
        
        # 4. 如果没找到，搜索常见的按钮文本
        print(f"\n[4] Searching for Yes/Continue buttons...")
        btn_texts = ["是", "Yes", "Continue", "确定", "确认", "OK"]
        for text in btn_texts:
            results = find_text_controls(root, [text], max_depth=6)
            if results:
                for ctrl, t, d in results:
                    try:
                        ctype = str(ctrl.ControlTypeName).lower()
                        print(f"    Found \"{text}\": [{ctrl.ControlTypeName}] \"{ctrl.Name}\"")
                        if "button" in ctype:
                            print(f"    -> This IS a button! Can click!")
                    except:
                        pass


if __name__ == "__main__":
    main()
    print(f"\n{'='*60}")
    print("Debug complete. Share this output for analysis.")
    print(f"{'='*60}")
    input("\nPress Enter to exit...")
