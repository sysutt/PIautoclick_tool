/*
 * TTAstroPiLot —— 处理历史导出(独立脚本,单次运行,不驻留)
 * ================================================================
 * 用途:把 PixInsight 里**当前活动图像**的完整处理历史(每一步进程 + 全部
 *      精确参数)导出成一个文本文件,用来给自动化管线做量化参考。
 *
 * 用法(在你自己平时用的 PixInsight 里,全程手动、无需本工具的 runner):
 *   ① 正常打开 PI,打开并手动处理你的图(拉伸/调色各步,爱怎么调怎么调);
 *   ② 确保处理完的那张图是**当前活动窗口**(点一下它的标题栏);
 *   ③ 菜单 Script > Execute Script File... > 选中本文件 > 运行(或按 F9);
 *   ④ 它会把历史写到下面 OUT 指定的文件,并在 Process Console 打印路径。
 *      把那个 txt 文件发给我即可。
 *
 * 说明:每一块是该步进程的 toSource(),这是 PixInsight 官方序列化,包含该进程
 *      在那一刻的**全部参数取值**(HistogramTransformation 的黑/中/白点、
 *      GeneralizedHyperbolicStretch 的 D/b/SP、CurvesTransformation 的控制点……)。
 */

function main()
{
   // 输出路径:被本工具的「导出历史」按钮自动替换为具体路径;
   // 若你直接从仓库运行(占位符未被替换),则退回系统临时目录。
   var OUT = "__OUT_PATH__";
   if (OUT.indexOf("__OUT") == 0) {
      try { OUT = File.systemTempDirectory + "/tt_process_history.txt"; }
      catch (e) { OUT = "tt_process_history.txt"; }
   }

   var win = ImageWindow.activeWindow;
   if (win.isNull) {
      console.criticalln("<end><cbr>[导出历史] 没有活动图像窗口。请先点选你处理完的那张图的标题栏,再运行。");
      return;
   }
   var view = win.mainView;
   var proc = view.processing;              // 历史栈(有 .length / .at(i))
   var n = proc ? proc.length : 0;
   var hi = view.historyIndex;              // 当前所在位置

   function typeOf(src) {                    // 从 toSource 取进程类型名:new XXX
      try { var m = /new\s+([A-Za-z_]\w*)/.exec(src); return m ? m[1] : "?"; }
      catch (e) { return "?"; }
   }

   var L = [];
   L.push("# TTAstroPiLot —— 处理历史导出");
   L.push("# 视图(view id): " + view.id);
   try { L.push("# 文件: " + (win.filePath || "(未保存)")); } catch (e) {}
   L.push("# 步数(history length): " + n);
   L.push("# 当前位置(historyIndex): " + hi);
   try { L.push("# 导出时间: " + (new Date()).toISOString()); } catch (e) {}
   L.push("# 说明: 每块是该步进程的 toSource(),含全部精确参数;* 标记当前位置(historyIndex-1)。");
   L.push("");

   var okCount = 0;
   for (var i = 0; i < n; ++i) {
      var src = "";
      try { src = proc.at(i).toSource(); }
      catch (e) { src = "// (无法序列化此步: " + e + ")"; }
      var mark = (i == hi - 1) ? " *当前" : "";
      L.push("// ========== [" + i + "] " + typeOf(src) + mark + " ==========");
      L.push(src);
      L.push("");
      if (src.indexOf("//") != 0) ++okCount;
   }
   if (n == 0)
      L.push("// (该视图历史为空 —— 确认你选的是处理过的那张图,而不是刚打开的原图。)");

   var text = L.join("\n") + "\n";
   try {
      var f = new File;
      f.createForWriting(OUT);
      f.outText(text);
      f.close();
   } catch (e) {
      console.criticalln("<end><cbr>[导出历史] 写文件失败: " + e + "  (路径: " + OUT + ")");
      return;
   }

   console.noteln("<end><cbr>[导出历史] 视图『" + view.id + "』共 " + n + " 步(可序列化 " + okCount + "),已写到:");
   console.noteln("  " + OUT);
   console.noteln("把这个文件发给我即可。");
}

main();
