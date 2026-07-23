/*
 * solve.js — 独立天文解析脚本(本地 ImageSolver,Tier 1)
 * ============================================================
 * 以"库模式"复用 PixInsight 自带 ImageSolver(USE_SOLVER_LIBRARY 抑制其 GUI)。
 * 读取 _run/solve_job.json {input, output},对 input 做本地天文解析,
 * 成功则把带解析的图存为 output,并写 _run/solve_result.json。
 *
 * 手动测试:PixInsight → SCRIPT ▸ Execute Script File ▸ 选本文件。
 * (先确保常驻 job-runner 已停,控制台空闲)
 */

#engine v8   // ImageSolver 及其 astrometry 依赖用 ES6 class,需 V8 引擎(旧引擎会报 "class is a reserved identifier")
#define USE_SOLVER_LIBRARY
#define SETTINGS_MODULE "ImageSolver"   // 库模式下 ImageSolver.js 不再定义它,需调用方补上
#include "C:/Program Files/PixInsight/src/scripts/ImageSolver/ImageSolver.js"

function _readText(p) { return File.readFile(p).toString(); }
function _writeText(p, t) { var f = new File; f.createForWriting(p); f.outText(t); f.close(); }

function solveMain() {
   var thisFile = #__FILE__;
   var base = File.extractDrive(thisFile) + File.extractDirectory(thisFile);
   var runDir = base + "/_run";
   var jobPath = runDir + "/solve_job.json";
   var resPath = runDir + "/solve_result.json";

   var res = { status: "error", error: null, hasSolution: false };
   try {
      var job = JSON.parse(_readText(jobPath));
      if (!job.input || !File.exists(job.input))
         throw new Error("input not found: " + job.input);

      var arr = ImageWindow.open(job.input);
      if (!arr || arr.length == 0)
         throw new Error("failed to open: " + job.input);
      var win = arr[0];
      try {
         win.show();               // 有些流程需要可见视图
         var engine = new ImageSolver;
         engine.initialize(win, false /*prioritizeSettings*/);  // 从图像头取焦距/像元/坐标
         engine.solveImage(win);

         res.hasSolution = win.hasAstrometricSolution;
         if (res.hasSolution) {
            var out = job.output || (runDir + "/solved_master.xisf");
            win.saveAs(out, false, false, false, false);
            res.output = out;
            res.status = "ok";
            try { res.summary = win.astrometricSolutionSummary().trim(); } catch (e) {}
         } else {
            res.error = "solveImage 未产生天文解析";
         }
      } finally {
         try { win.forceClose(); } catch (e) {}
      }
   } catch (e) {
      res.error = (e && e.message) ? e.message : String(e);
   }
   _writeText(resPath, JSON.stringify(res, null, 2));
   console.writeln("[solve] status=" + res.status + (res.error ? (" | " + res.error) : "") +
                   " | hasSolution=" + res.hasSolution);
}

solveMain();
