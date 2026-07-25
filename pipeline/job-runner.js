/*
 * job-runner.js — 常驻 PixInsight 的作业派发脚本 (PJSR)
 * ============================================================
 * 深空自动后期处理系统 · P0 骨架
 *
 * 职责:在 PixInsight 内常驻运行,轮询 _run/inbox 目录中的 job(JSON),
 *       执行对应操作,导出指标 JSON + 预览 PNG 到 _run/done。
 *       无决策逻辑——决策由外部 Python 编排器负责。
 *
 * 用法:
 *   1) 打开 PixInsight;
 *   2) SCRIPT > Execute Script File... 选择本文件,或用命令行:
 *        PixInsight.exe -r="<...>/pipeline/job-runner.js"
 *   3) 脚本会在 Process Console 打印心跳,保持运行;
 *   4) 在 _run 目录放入名为 STOP 的文件即可优雅停止(或在控制台点 Abort)。
 *
 * 交换协议见 pipeline/README.md 与技术方案 §8。
 */

#engine v8   // 需 V8 引擎以便 include ImageSolver(其 astrometry 依赖用 ES6 class)
#include <pjsr/UndoFlag.jsh>   // 定义 UndoFlag_NoSwapFile 等常量

// 以"库模式"引入 PixInsight 内置 ImageSolver(用于本地天文解析 solve op)
#define USE_SOLVER_LIBRARY
#define SETTINGS_MODULE "ImageSolver"
#include "C:/Program Files/PixInsight/src/scripts/ImageSolver/ImageSolver.js"

// ---- 目录解析(以本脚本所在目录为基准,_run 为同级)----
// 注意:PixInsight 的 File.extractDirectory() 只返回目录部分,不含盘符,
//       需拼回 File.extractDrive() 得到完整绝对路径(否则会退化成盘符相对路径)。
var THIS_FILE  = #__FILE__;
var _dir       = File.extractDirectory(THIS_FILE);
var _drv       = File.extractDrive(THIS_FILE);
var BASE_DIR   = (_drv && _drv.length ? _drv : "") + _dir;
var RUN_DIR    = BASE_DIR + "/_run";
var INBOX      = RUN_DIR + "/inbox";
var PROCESSING = RUN_DIR + "/processing";
var DONE       = RUN_DIR + "/done";
var HEARTBEAT  = RUN_DIR + "/runner.heartbeat";
var STOP_FILE  = RUN_DIR + "/STOP";

var POLL_MS          = 300;    // 轮询间隔
var PREVIEW_MAX_SIDE = 1600;   // 预览长边像素上限

// ============================================================
// 基础工具
// ============================================================
function log(msg)  { console.writeln("[job-runner] " + msg); }
function warn(msg) { console.warningln("[job-runner] " + msg); }

function ensureDir(dir) {
   if (!File.directoryExists(dir))
      File.createDirectory(dir, true);
}

function ensureDirs() {
   ensureDir(RUN_DIR);
   ensureDir(INBOX);
   ensureDir(PROCESSING);
   ensureDir(DONE);
}

function readAllText(path) {
   var bytes = File.readFile(path);   // ByteArray
   return bytes.toString();
}

function writeAllText(path, text) {
   var f = new File;
   f.createForWriting(path);
   f.outText(text);
   f.close();
}

function nowMs() {
   return (new Date).getTime();
}

// 列出 inbox 中的 *.json(排序保证 FIFO)
function listJobFiles() {
   var names = [];
   var ff = new FileFind;
   if (ff.begin(INBOX + "/*.json")) {
      do {
         if (ff.isFile && ff.name != "." && ff.name != "..")
            names.push(ff.name);
      } while (ff.next());
   }
   return names.sort();
}

// ============================================================
// 图像统计与预览
// ============================================================
function computeStats(img) {
   var s = {
      width: img.width,
      height: img.height,
      channels: img.numberOfChannels,
      bits: img.bitsPerSample,
      isColor: img.isColor,
      perChannel: []
   };
   for (var c = 0; c < img.numberOfChannels; ++c) {
      try {
         img.firstSelectedChannel = c;
         img.lastSelectedChannel  = c;
         s.perChannel.push({
            channel: c,
            median: img.median(),
            mean:   img.mean(),
            stdDev: img.stdDev(),
            mad:    img.MAD(),
            min:    img.minimum(),
            max:    img.maximum()
         });
      } catch (e) {
         s.perChannel.push({ channel: c, error: String(e) });
      }
   }
   // 关键:恢复完整通道范围与选区,否则后续 assign() 会只复制被选中的通道子集 → 灰度化
   try { img.resetSelections(); } catch (e) {}
   return s;
}

// 中值转移函数
function mtf(m, x) {
   if (x <= 0) return 0;
   if (x >= 1) return 1;
   if (x == m) return 0.5;
   return ((m - 1) * x) / ((2 * m - 1) * x - m);
}

// 经典 STF AutoStretch。targetBG 越小/shadowClip 越负 → 拉得越狠(暗目标可调)
// linked=true:所有通道同一曲线(保留色比,宽带用);
// linked=false:逐通道独立拉伸,均衡各通道背景(HOO 等窄带用,出红蓝配色)
function computeStretchH(img, targetBG, shadowClip, linked) {
   if (targetBG === undefined) targetBG = 0.25;
   if (shadowClip === undefined) shadowClip = -2.80;
   if (linked === undefined) linked = true;
   try { img.resetSelections(); } catch (e) {}
   var nCh = img.numberOfChannels;

   // 计算某通道(channel<0 表示组合)的 HT 曲线行 [c0, m, 1, 0, 1]
   function curveFor(channel) {
      if (channel >= 0) {
         img.lastSelectedChannel  = channel;   // 先设 last 再设 first,避免 first>last
         img.firstSelectedChannel = channel;
      }
      var med  = img.median();
      var madN = img.MAD() * 1.4826;
      var c0 = (madN > 0) ? Math.max(0, Math.min(1, med + shadowClip * madN)) : 0.0;
      var m  = mtf(targetBG, med - c0);
      return [c0, m, 1.0, 0, 1];
   }

   var H;
   if (linked || nCh < 3) {
      var comb = curveFor(-1);
      H = [[0,0.5,1,0,1],[0,0.5,1,0,1],[0,0.5,1,0,1], comb, [0,0.5,1,0,1]];
   } else {
      var r = curveFor(0), g = curveFor(1), b = curveFor(2);
      H = [r, g, b, [0,0.5,1,0,1], [0,0.5,1,0,1]];
   }
   try { img.resetSelections(); } catch (e) {}
   return H;
}

// 应用 HT 曲线(H 矩阵)到视图
function applyHMatrix(view, H) {
   var P = new HistogramTransformation;
   P.H = H;
   P.executeOn(view);
   try { view.image.resetSelections(); } catch (e) {}
}

function autoStretch(view, targetBG, shadowClip, linked) {
   applyHMatrix(view, computeStretchH(view.image, targetBG, shadowClip, linked));
}

// 星点专用拉伸:黑场压到背景噪声之上(背景归零,不抬升),仅提亮星点。
// 避免对"近黑背景+星点"的星点图做背景归一化拉伸而炸开噪声/棋盘纹。
function applyStarStretch(view, params) {
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   var clipK  = (params && params.clipSigma != null) ? params.clipSigma : 3.0;  // 背景之上多少σ压黑
   var mid    = (params && params.midtones  != null) ? params.midtones  : 0.20; // 中值提亮星点
   var linked = (params && params.linked     != null) ? params.linked   : false;

   function rowFor(c) {
      if (c >= 0) { img.lastSelectedChannel = c; img.firstSelectedChannel = c; }
      var med = img.median(), madN = img.MAD() * 1.4826;
      var c0 = Math.max(0, Math.min(0.98, med + clipK * madN));
      return [c0, mid, 1.0, 0, 1];
   }
   var H;
   if (linked) {
      var comb = rowFor(-1);
      H = [[0,0.5,1,0,1],[0,0.5,1,0,1],[0,0.5,1,0,1], comb, [0,0.5,1,0,1]];
   } else {
      var r = rowFor(0), g = rowFor(1), b = rowFor(2);
      H = [r, g, b, [0,0.5,1,0,1], [0,0.5,1,0,1]];
   }
   try { img.resetSelections(); } catch (e) {}
   var P = new HistogramTransformation;
   P.H = H;
   P.executeOn(view);
   try { view.image.resetSelections(); } catch (e) {}
}

// 为预览缩小尺寸(整数倍降采样,API 简单稳)
function downsampleForPreview(view, maxLongSide) {
   try {
      var img = view.image;
      var longSide = Math.max(img.width, img.height);
      if (longSide <= maxLongSide) return;
      var k = Math.ceil(longSide / maxLongSide);
      if (k < 2) return;
      var IR = new IntegerResample;
      IR.zoomFactor = -k;   // 负值 = 降采样
      IR.executeOn(view);
   } catch (e) {
      // 缩放失败则保留全尺寸,不影响主流程
      warn("downsample skipped: " + e);
   }
}

// 复制一份视图 → (线性图才自动拉伸)→ 降采样 → 存 PNG(不改动原图数据)
// applyStretch: 线性数据传 true(需拉伸才可见);已是非线性的图传 false(原样显示)
function exportPreview(srcView, pngPath, applyStretch) {
   if (applyStretch === undefined) applyStretch = true;
   var img = srcView.image;
   try { img.resetSelections(); } catch (e) {}   // 防御:清除可能残留的通道/矩形选区
   var nCh = img.numberOfChannels;
   var isColorImg = (nCh >= 3);
   var diag = { srcIsColor: img.isColor, srcNCh: nCh };

   // 用 createWindow 从源视图克隆(保留颜色空间),比空窗口+assign 更可靠
   var tmp = new ImageWindow(img.width, img.height, nCh, 32, true, isColorImg,
                             "p0_preview_tmp");
   diag.afterCreate = { nCh: tmp.mainView.image.numberOfChannels,
                        isColor: tmp.mainView.image.isColor,
                        cs: tmp.mainView.image.colorSpace };
   try {
      tmp.mainView.beginProcess(UndoFlag_NoSwapFile);
      tmp.mainView.image.assign(img);
      tmp.mainView.endProcess();
      diag.afterAssign = { nCh: tmp.mainView.image.numberOfChannels,
                           isColor: tmp.mainView.image.isColor,
                           cs: tmp.mainView.image.colorSpace };

      if (applyStretch)
         autoStretch(tmp.mainView);   // 仅线性图需要,避免对非线性图二次拉伸
      downsampleForPreview(tmp.mainView, PREVIEW_MAX_SIDE);

      var ti = tmp.mainView.image;
      diag.finalNCh = ti.numberOfChannels;
      diag.finalIsColor = ti.isColor;
      if (ti.numberOfChannels >= 3) {
         var cx = Math.floor(ti.width / 2), cy = Math.floor(ti.height / 2);
         diag.centerRGB = [ti.sample(cx, cy, 0), ti.sample(cx, cy, 1), ti.sample(cx, cy, 2)];
      }

      tmp.saveAs(pngPath, false, false, false, false);
   } finally {
      try { tmp.forceClose(); } catch (e) {}
   }
   return diag;
}

// ============================================================
// 能力探测(有/无三件套等)
// ============================================================
function probeCapabilities() {
   // 已注册的 Process 会成为全局构造器;typeof 对未定义标识符返回 "undefined" 而不抛错
   var checks = [
      "BlurXTerminator", "StarXTerminator", "NoiseXTerminator",
      "StarNet2", "StarNet",
      "GradientCorrection", "DynamicBackgroundExtraction",
      "SpectrophotometricColorCalibration", "BackgroundNeutralization",
      "ColorCalibration", "HistogramTransformation",
      "GeneralizedHyperbolicStretch", "MultiscaleLinearTransform",
      "PixelMath", "IntegerResample", "GraXpert"
   ];
   var caps = {};
   for (var i = 0; i < checks.length; ++i) {
      var name = checks[i];
      var available = false;
      try {
         available = (eval("typeof " + name) == "function");
      } catch (e) {
         available = false;
      }
      caps[name] = available;
   }
   caps.pixinsightVersion =
      (typeof coreVersionBuild != "undefined") ? String(coreVersionBuild) : "unknown";
   return caps;
}

// ============================================================
// 合成自测图(无需任何外部素材,证明整条链路可用)
// ============================================================
function makeSyntheticWindow() {
   var w = new ImageWindow(600, 400, 3, 32, true, true, "p0_selftest");
   var P = new PixelMath;
   P.useSingleExpression = true;
   P.expression = "0.10 + 0.40*X()*Y()";   // 平滑梯度,统计量非平凡
   P.createNewImage = false;
   P.executeOn(w.mainView);
   return w;
}

// 叠加:ImageIntegration 把一批已配准单张(registered)合成一个新 master。
// params.images = [路径,...]。返回积分结果窗口。
function applyIntegration(params) {
   if (typeof ImageIntegration == "undefined")
      throw new Error("ImageIntegration 不可用");
   var imgs = (params && params.images) || [];
   if (imgs.length < 3)
      throw new Error("integrate 需要至少 3 张,收到 " + imgs.length);
   var P = new ImageIntegration;
   var rows = [];
   for (var i = 0; i < imgs.length; ++i) rows.push([true, imgs[i], "", ""]);
   P.images = rows;
   try { P.combination = ImageIntegration.prototype.Average; } catch (e) {}
   try { P.rejection = ImageIntegration.prototype.WinsorizedSigmaClipping; } catch (e) {}
   try { P.normalization = ImageIntegration.prototype.AdditiveWithScaling; } catch (e) {}
   try { P.rejectionNormalization = ImageIntegration.prototype.Scale; } catch (e) {}
   try { P.weightMode = ImageIntegration.prototype.NoiseEvaluation; } catch (e) {}
   try { P.generateRejectionMaps = false; } catch (e) {}
   // 可调裁剪 sigma(默认 4.0/3.0)。压低 sigmaHigh 可剔除亮离群
   if (params && params.sigmaLow  != null) { try { P.sigmaLow  = params.sigmaLow;  } catch (e) {} }
   if (params && params.sigmaHigh != null) { try { P.sigmaHigh = params.sigmaHigh; } catch (e) {} }
   // 大尺度高段抑制:专治卫星/飞机轨迹等线状延展亮结构(普通 sigma 裁剪对其不敏感)
   if (params && params.trailReject) {
      try { P.largeScaleClipHigh = true; } catch (e) {}
      try { P.largeScaleClipHighProtectedLayers = (params.trailProtect != null) ? params.trailProtect : 2; } catch (e) {}
      try { P.largeScaleClipHighGrowth = (params.trailGrowth != null) ? params.trailGrowth : 2; } catch (e) {}
   }
   var diag = {};
   try {
      diag.props = Object.getOwnPropertyNames(P).filter(function (k) {
         return (k.toLowerCase().indexOf("scale") >= 0 || k.toLowerCase().indexOf("sigma") >= 0
                 || k.toLowerCase().indexOf("clip") >= 0 || k.toLowerCase().indexOf("reject") >= 0)
                && typeof P[k] !== "function";
      });
      diag.sigmaLow = P.sigmaLow; diag.sigmaHigh = P.sigmaHigh;
   } catch (e) {}
   if (!P.executeGlobal())
      throw new Error("ImageIntegration executeGlobal 失败 | diag=" + JSON.stringify(diag));
   var id = P.integrationImageId;
   var win = ImageWindow.windowById(id);
   if (!win || win.isNull)
      throw new Error("找不到积分结果窗口: " + id);
   // 关掉可能生成的抑制/斜率图窗口
   var maps = ["lowRejectionMapImageId", "highRejectionMapImageId", "slopeMapImageId"];
   for (var j = 0; j < maps.length; ++j) {
      try {
         var w2 = ImageWindow.windowById(P[maps[j]]);
         if (w2 && !w2.isNull) w2.forceClose();
      } catch (e) {}
   }
   log("integrate: " + imgs.length + " 张 → " + id);
   return { win: win, count: imgs.length, diag: diag };
}

// ============================================================
// 处理步骤(P1 管线)
// ============================================================

// 判断某一行/列是否"空"(所有采样点都低于阈值)
function lineEmpty(img, orient, idx, thr, samples) {
   var n = (orient == "row") ? img.width : img.height;
   var step = Math.max(1, Math.floor(n / samples));
   var nCh = img.numberOfChannels;
   for (var p = 0; p < n; p += step) {
      for (var c = 0; c < nCh; ++c) {
         var v = (orient == "row") ? img.sample(p, idx, c) : img.sample(idx, p, c);
         if (v > thr) return false;
      }
   }
   return true;
}

// 探测四周黑边厚度(像素);maxFrac 限制最多扫描的比例,避免误吃内容
function detectBorders(img, thr, maxFrac) {
   var W = img.width, H = img.height;
   var maxX = Math.floor(W * maxFrac), maxY = Math.floor(H * maxFrac);
   var left = 0;   while (left   < maxX && lineEmpty(img, "col", left,        thr, 40)) ++left;
   var right = 0;  while (right  < maxX && lineEmpty(img, "col", W - 1 - right, thr, 40)) ++right;
   var top = 0;    while (top    < maxY && lineEmpty(img, "row", top,         thr, 40)) ++top;
   var bottom = 0; while (bottom < maxY && lineEmpty(img, "row", H - 1 - bottom, thr, 40)) ++bottom;
   return { left: left, top: top, right: right, bottom: bottom };
}

// 边缘明暗不均检测:网格化算每格稳健背景(中位数,抗星点),以全体格子中位数为天空基准,
// 量化四条边缘偏离天空的程度(MAD 单位),并给出建议裁切像素数。只提案,不修改图像。
function edgeCheck(img, params) {
   var gx = 16, gy = 9;
   var W = img.width, H = img.height;
   var tw = Math.floor(W / gx), th = Math.floor(H / gy);
   var thr = (params && params.threshold != null) ? params.threshold : 4.0;  // MAD 阈值

   try { img.resetSelections(); } catch (e) {}
   var med = [];
   for (var r = 0; r < gy; ++r) {
      med[r] = [];
      for (var c = 0; c < gx; ++c) {
         var x0 = c * tw, y0 = r * th;
         var x1 = (c == gx - 1) ? W : x0 + tw, y1 = (r == gy - 1) ? H : y0 + th;
         img.selectedRect = new Rect(x0, y0, x1, y1);
         med[r][c] = img.median();
      }
   }
   try { img.resetSelections(); } catch (e) {}

   // 天空基准 = 所有格子中位数的中位数;离散度用 MAD
   var flat = [];
   for (r = 0; r < gy; ++r) for (c = 0; c < gx; ++c) flat.push(med[r][c]);
   flat.sort(function (a, b) { return a - b; });
   var sky = flat[Math.floor(flat.length / 2)];
   var ad = [];
   for (var i = 0; i < flat.length; ++i) ad.push(Math.abs(flat[i] - sky));
   ad.sort(function (a, b) { return a - b; });
   var mad = ad[Math.floor(ad.length / 2)] * 1.4826;
   if (!(mad > 0)) mad = 1e-6;

   function lineDev(cells) {
      var s = 0;
      for (var i = 0; i < cells.length; ++i) s += (cells[i] - sky);
      return (s / cells.length) / mad;    // 带符号,MAD 单位
   }
   function row(k) { return med[k].slice(); }
   function col(k) { var a = []; for (var r = 0; r < gy; ++r) a.push(med[r][k]); return a; }

   var dev = {
      top:    lineDev(row(0)),      bottom: lineDev(row(gy - 1)),
      left:   lineDev(col(0)),      right:  lineDev(col(gx - 1))
   };

   // 从每条边往里推,直到该边格子线偏离 <= 阈值,得出建议裁切的格子数
   function propose(getLine, maxLines) {
      var n = 0;
      for (var k = 0; k < maxLines; ++k) {
         if (Math.abs(lineDev(getLine(k))) <= thr) break;
         ++n;
      }
      return n;
   }
   var maxR = Math.floor(gy * 0.3), maxC = Math.floor(gx * 0.3);
   var ct = {
      top:    propose(function (k) { return row(k); }, maxR),
      bottom: propose(function (k) { return row(gy - 1 - k); }, maxR),
      left:   propose(function (k) { return col(k); }, maxC),
      right:  propose(function (k) { return col(gx - 1 - k); }, maxC)
   };
   var needCrop = (ct.top || ct.bottom || ct.left || ct.right) ? true : false;
   return {
      sky: sky, mad: mad, thresholdMad: thr,
      edgeDeviationMad: dev,
      needCrop: needCrop,
      cropProposalPx: { left: ct.left * tw, right: ct.right * tw, top: ct.top * th, bottom: ct.bottom * th }
   };
}

// 裁黑边:params.margins 显式指定,否则自动探测
// 覆盖度感知裁边:多日叠加的"部分覆盖边"暗但非零,纯黑检测抓不到。
// 以中心区域中位数为参照,从每条边逐带(step px)测中位数,低于 frac*内部背景则视为边界,
// 一直裁到带亮度回到正常。返回各边像素数 + 诊断。
function detectBordersCoverage(img, params) {
   var W = img.width, H = img.height;
   var frac = (params && params.coverageThreshold != null) ? params.coverageThreshold : 0.6;
   var maxFrac = (params && params.maxFrac != null) ? params.maxFrac : 0.15;
   var step = (params && params.step != null) ? params.step : 16;

   var segs = (params && params.segments != null) ? params.segments : 6;  // 边沿分段数(角落敏感)
   var extra = (params && params.extraMargin != null) ? params.extraMargin : 0; // 检测后再多刮的像素

   function med(x0, y0, x1, y1) {
      img.selectedRect = new Rect(x0, y0, x1, y1);
      var m = img.median();
      return m;
   }
   // 一条水平带分 segs 段,返回 {lo:最暗段, hi:最亮段} 中位数
   function hBand(y0, y1) {
      var lo = Infinity, hi = -Infinity;
      for (var s = 0; s < segs; ++s) {
         var xa = Math.floor(s * W / segs), xb = Math.floor((s + 1) * W / segs);
         var v = med(xa, y0, xb, y1);
         if (v < lo) lo = v; if (v > hi) hi = v;
      }
      return { lo: lo, hi: hi };
   }
   function vBand(x0, x1) {
      var lo = Infinity, hi = -Infinity;
      for (var s = 0; s < segs; ++s) {
         var ya = Math.floor(s * H / segs), yb = Math.floor((s + 1) * H / segs);
         var v = med(x0, ya, x1, yb);
         if (v < lo) lo = v; if (v > hi) hi = v;
      }
      return { lo: lo, hi: hi };
   }
   var ib = med(Math.floor(W * 0.30), Math.floor(H * 0.30),
                Math.floor(W * 0.70), Math.floor(H * 0.70));
   var thr = frac * ib;                                   // 暗边阈值
   var brightFrac = (params && params.brightFrac != null) ? params.brightFrac : 3.0;
   var bthr = brightFrac * ib;                            // 亮边阈值(叠加边缘发亮)
   // 边界带 = 最暗段偏暗(<thr,欠覆盖) 或 最亮段偏亮(>bthr,叠加亮边)
   function isEdge(b) { return (b.lo < thr) || (b.hi > bthr); }
   var maxX = Math.floor(W * maxFrac), maxY = Math.floor(H * maxFrac);
   var prof = { top: [], bottom: [], left: [], right: [] };

   var top = 0;
   while (top + step <= maxY) {
      var bt = hBand(top, top + step);
      if (prof.top.length < 10) prof.top.push([Number(bt.lo.toFixed(6)), Number(bt.hi.toFixed(6))]);
      if (isEdge(bt)) top += step; else break;
   }
   var bottom = 0;
   while (bottom + step <= maxY) {
      var bb = hBand(H - bottom - step, H - bottom);
      if (prof.bottom.length < 10) prof.bottom.push([Number(bb.lo.toFixed(6)), Number(bb.hi.toFixed(6))]);
      if (isEdge(bb)) bottom += step; else break;
   }
   var left = 0;
   while (left + step <= maxX) {
      var bl = vBand(left, left + step);
      if (prof.left.length < 10) prof.left.push([Number(bl.lo.toFixed(6)), Number(bl.hi.toFixed(6))]);
      if (isEdge(bl)) left += step; else break;
   }
   var right = 0;
   while (right + step <= maxX) {
      var br = vBand(W - right - step, W - right);
      if (prof.right.length < 10) prof.right.push([Number(br.lo.toFixed(6)), Number(br.hi.toFixed(6))]);
      if (isEdge(br)) right += step; else break;
   }
   try { img.resetSelections(); } catch (e) {}
   if (extra > 0) {
      if (top) top += extra;  if (bottom) bottom += extra;
      if (left) left += extra; if (right) right += extra;
   }
   return { left: left, top: top, right: right, bottom: bottom, segments: segs, extraMargin: extra,
            interiorBg: Number(ib.toFixed(6)), thr: Number(thr.toFixed(6)), brightThr: Number(bthr.toFixed(6)),
            profile: prof };
}

// 裁切 → 返回一个装着裁切结果的【全新窗口】(无天文解析,故不弹"删除解析"确认框)。
// 不使用 Crop 进程(几何变换会对已解析图弹模态框卡住脚本),改用 Image.cropTo 纯像素裁切。
// 返回 { win: 新窗口|null, applied: 边距 }。win 为 null 表示无需裁切。
function cropToNewWindow(srcView, params) {
   var img = srcView.image;
   var m, diag = null;
   if (params && params.margins) {
      m = params.margins;                        // 显式裁切
   } else {
      var cov = detectBordersCoverage(img, params);  // 覆盖度感知(含黑边与部分覆盖暗边)
      m = { left: cov.left, top: cov.top, right: cov.right, bottom: cov.bottom };
      diag = { interiorBg: cov.interiorBg, thr: cov.thr, profile: cov.profile };
   }
   if (!(m.left || m.top || m.right || m.bottom)) {
      log("crop: 无需裁切");
      return { win: null, applied: m, diag: diag };
   }
   var nCh = img.numberOfChannels;
   var x0 = m.left, y0 = m.top;
   var x1 = img.width - m.right, y1 = img.height - m.bottom;
   var out = new ImageWindow(img.width, img.height, nCh, 32, true, nCh >= 3, "cropped");
   out.mainView.beginProcess(UndoFlag_NoSwapFile);
   try { img.resetSelections(); } catch (e) {}
   out.mainView.image.assign(img);            // 全通道拷贝
   out.mainView.image.cropTo(x0, y0, x1, y1); // 纯像素裁切,无几何进程 → 不弹框
   out.mainView.endProcess();
   // 拷贝源窗口的 FITS 头关键字(坐标/焦距/观测时间等),否则裁后无法再天文解析
   try {
      var srcWin = srcView.window;
      if (srcWin && srcWin.keywords) out.keywords = srcWin.keywords;
   } catch (e) {}
   log("crop: L" + m.left + " T" + m.top + " R" + m.right + " B" + m.bottom +
       " → " + (x1 - x0) + "x" + (y1 - y0));
   return { win: out, applied: m, diag: diag };
}

// 梯度校正:P1 默认用原生 GradientCorrection(参数默认,作者认可)
// 后续 P2 再接入 GraXpert / DBE 的降级阶梯与能力自适应
function applyGradientCorrection(view, params) {
   var method = (params && params.method) ? params.method : "GradientCorrection";
   if (method == "GradientCorrection") {
      new GradientCorrection().executeOn(view);
      return "GradientCorrection";
   }
   if (method == "abe") {
      if (typeof AutomaticBackgroundExtractor == "undefined")
         throw new Error("AutomaticBackgroundExtractor 不可用");
      var P = new AutomaticBackgroundExtractor;
      var info = { method: "abe", set: [] };
      try {
         info.props = Object.getOwnPropertyNames(P).filter(function (k) {
            return k.charAt(0) !== "_" && typeof P[k] !== "function";
         });
      } catch (e) {}
      function aset(name, val) {
         try { if (typeof P[name] != "undefined") { P[name] = val; info.set.push(name + "=" + val); } } catch (e) {}
      }
      var deg = (params && params.polyDegree != null) ? params.polyDegree : 4;
      aset("polyDegree", deg);
      aset("targetCorrection", 1);      // 1=Subtract(真正把模型减掉,否则只生成模型窗口=空操作)
      aset("replaceTarget", true);      // 就地替换目标视图
      aset("discardModel", true);
      aset("normalize", false);
      if (params && params.tolerance != null) aset("tolerance", params.tolerance);
      if (params && params.deviation != null) aset("deviation", params.deviation);
      P.executeOn(view);
      return info;
   }
   if (method == "graxpert") {
      if (typeof GraXpert == "undefined")
         throw new Error("GraXpert 不可用");
      var P = new GraXpert;
      var info = { method: "graxpert", set: [] };
      // 诊断:枚举属性名(首次运行用于确认操作参数名)
      try {
         info.props = Object.getOwnPropertyNames(P).filter(function (k) {
            return k.charAt(0) !== "_" && typeof P[k] !== "function";
         });
      } catch (e) {}
      function gset(name, val) {
         try { if (typeof P[name] != "undefined") { P[name] = val; info.set.push(name + "=" + val); } } catch (e) {}
      }
      // 只做背景提取,关掉降噪/反卷积
      gset("backgroundExtraction", true);
      gset("denoising", false);
      gset("deconvolution", false);
      if (params && params.smoothing != null) gset("smoothing", params.smoothing);
      if (params && params.strength != null) gset("strength", params.strength);
      P.executeOn(view);
      return info;
   }
   if (method == "refbg") {
      // 参考引导背景扣除(≈用 SuperL 判背景的手动 DBE):
      // 以 ref(SuperL)建对象掩模,只在背景区建平滑模型,从当前通道扣除梯度。
      if (params == null || !params.ref || !File.exists(params.ref))
         throw new Error("refbg 需要 ref(背景参考,如 SuperL 路径): " + (params && params.ref));
      var refW = ImageWindow.open(params.ref)[0];
      try {
         var img = view.image; try { img.resetSelections(); } catch (e) {}
         var gMed = img.median();
         var refImg = refW.mainView.image; try { refImg.resetSelections(); } catch (e) {}
         var refMed = refImg.median();
         var refSpread;
         try { refSpread = refImg.MAD() * 1.4826; } catch (e) { refSpread = refMed * 0.1; }
         if (!(refSpread > 0)) refSpread = refMed * 0.1 + 1e-6;
         var objK = (params.objK != null) ? params.objK : 2.5;
         var refThr = refMed + objK * refSpread;   // ref 高于此 = 对象(星系/星点)→ 排除
         var sigma = (params.sigma != null) ? params.sigma : 120;
         var refId = refW.mainView.id;
         var info = { method: "refbg", gMed: Number(gMed.toFixed(5)),
                      refThr: Number(refThr.toFixed(5)), sigma: sigma };

         // 1. 掩掉对象:对象处用 G 全局中位替代(不污染背景模型)
         var mw = new ImageWindow(img.width, img.height, img.numberOfChannels, 32, true,
                                  img.numberOfChannels >= 3, "refbg_model");
         mw.mainView.beginProcess(UndoFlag_NoSwapFile);
         mw.mainView.image.assign(img);
         mw.mainView.endProcess();
         var Pm = new PixelMath;
         Pm.useSingleExpression = true;
         Pm.expression = "iif(" + refId + " > " + refThr + ", " + gMed + ", $T)";
         Pm.createNewImage = false; Pm.rescale = false; Pm.truncate = true;
         Pm.executeOn(mw.mainView);
         // 2. 大高斯模糊 → 平滑背景模型
         var C = new Convolution;
         try { C.mode = 0; } catch (e) {}
         try { C.sigma = sigma; } catch (e) {}
         try { C.shape = 2.0; } catch (e) {}
         C.executeOn(mw.mainView);
         var modelId = mw.mainView.id;
         var modelMed = mw.mainView.image.median();
         info.modelMed = Number(modelMed.toFixed(5));
         // 3. 扣模型 + 加回基准(加性梯度去除)
         var Ps = new PixelMath;
         Ps.useSingleExpression = true;
         Ps.expression = "$T - " + modelId + " + " + modelMed;
         Ps.createNewImage = false; Ps.rescale = false; Ps.truncate = true;
         Ps.executeOn(view);
         try { mw.forceClose(); } catch (e) {}
         return info;
      } finally { try { refW.forceClose(); } catch (e) {} }
   }
   if (method == "dbe") {
      if (typeof DynamicBackgroundExtraction == "undefined")
         throw new Error("DynamicBackgroundExtraction 不可用");
      var img = view.image;
      try { img.resetSelections(); } catch (e) {}
      var W = img.width, Hgt = img.height;
      var nx = (params && params.nx) ? params.nx : 12;
      var ny = (params && params.ny) ? params.ny : 8;
      // 每格取局部中位数,用于剔除落在星云/亮星上的点
      var cells = [], meds = [];
      var cw = Math.floor(W / nx), ch = Math.floor(Hgt / ny);
      var half = Math.floor(Math.min(cw, ch) * 0.18);   // 采样小窗半径(避开点内部亮结构)
      if (half < 4) half = 4;
      for (var gy = 0; gy < ny; ++gy) {
         for (var gx = 0; gx < nx; ++gx) {
            var cx = Math.floor((gx + 0.5) * cw);
            var cy = Math.floor((gy + 0.5) * ch);
            var x0 = Math.max(0, cx - half), y0 = Math.max(0, cy - half);
            var x1 = Math.min(W, cx + half), y1 = Math.min(Hgt, cy + half);
            var m;
            try {
               img.selectedRect = new Rect(x0, y0, x1, y1);
               m = img.median();
            } catch (e) { m = null; }
            try { img.resetSelections(); } catch (e) {}
            cells.push({ cx: cx, cy: cy, m: m });
            if (m != null) meds.push(m);
         }
      }
      // 阈值:格中位数的分布下部为背景;高于 (中位 + k*MAD) 视为星云/亮区 → 剔除
      meds.sort(function (a, b) { return a - b; });
      var midMed = meds.length ? meds[Math.floor(meds.length / 2)] : 0;
      var mad = [];
      for (var i = 0; i < meds.length; ++i) mad.push(Math.abs(meds[i] - midMed));
      mad.sort(function (a, b) { return a - b; });
      var madv = mad.length ? mad[Math.floor(mad.length / 2)] : 0;
      var krej = (params && params.reject != null) ? params.reject : 2.5;
      var thr = midMed + krej * (madv > 0 ? madv * 1.4826 : midMed * 0.1 + 1e-6);
      var pts = [], placed = 0, rejected = 0;
      for (var c = 0; c < cells.length; ++c) {
         var cc = cells[c];
         if (cc.m == null) { rejected++; continue; }
         if (cc.m > thr)   { rejected++; continue; }   // 落在星云/亮区 → 弃
         pts.push([cc.cx / W, cc.cy / Hgt]);           // 归一化坐标 [0,1]
         placed++;
      }
      var P = new DynamicBackgroundExtraction;
      var info = { method: "dbe", nx: nx, ny: ny, placed: placed, rejected: rejected,
                   midMed: Number(midMed.toFixed(5)), thr: Number(thr.toFixed(5)), set: [] };
      try {
         info.props = Object.getOwnPropertyNames(P).filter(function (k) {
            return k.charAt(0) !== "_" && typeof P[k] !== "function";
         });
      } catch (e) {}
      function dset(name, val) {
         try { if (typeof P[name] != "undefined") { P[name] = val; info.set.push(name + "=" + val); } } catch (e) {}
      }
      // 正确属性名是 samples(不是 samplePoints)。行格式不透明 → 用 samplesPerRow 让 DBE 自动布点。
      dset("samplesPerRow", (params && params.samplesPerRow != null) ? params.samplesPerRow : nx);
      dset("defaultSampleRadius", (params && params.sampleRadius != null) ? params.sampleRadius : 15);
      dset("tolerance", (params && params.tolerance != null) ? params.tolerance : 1.0);
      dset("minSampleFraction", (params && params.minSampleFraction != null) ? params.minSampleFraction : 0.05);
      if (params && params.smoothing != null) dset("smoothing", params.smoothing);
      if (params && params.downsample != null) dset("downsample", params.downsample);
      dset("targetCorrection", 0);          // 0=Subtract(常用于加性梯度)
      dset("normalize", false);
      dset("discardModel", true);
      info.autoGrid = true;
      try { P.executeOn(view); info.executed = true; }
      catch (e) { info.execErr = String(e); throw new Error("DBE executeOn failed: " + e + " | diag=" + JSON.stringify(info)); }
      return info;
   }
   throw new Error("gradient method not implemented: " + method);
}

// 分区背景统计:把线性图分 3x3 网格,报各区中位数(避开亮区用低分位),量化梯度平坦度。
function bgStats(img, grid) {
   try { img.resetSelections(); } catch (e) {}
   var n = grid || 3;
   var W = img.width, Hgt = img.height;
   var cells = [];
   var vals = [];
   for (var gy = 0; gy < n; ++gy) {
      var row = [];
      for (var gx = 0; gx < n; ++gx) {
         var x0 = Math.floor(gx * W / n), x1 = Math.floor((gx + 1) * W / n);
         var y0 = Math.floor(gy * Hgt / n), y1 = Math.floor((gy + 1) * Hgt / n);
         var m;
         try { img.selectedRect = new Rect(x0, y0, x1, y1); m = img.median(); }
         catch (e) { m = null; }
         try { img.resetSelections(); } catch (e) {}
         var v = (m == null) ? null : Number(m.toFixed(6));
         row.push(v);
         if (v != null) vals.push(v);
      }
      cells.push(row);
   }
   var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
   return { grid: n, cells: cells, min: Number(mn.toFixed(6)), max: Number(mx.toFixed(6)),
            spread: Number((mx - mn).toFixed(6)),
            ratio: Number((mx / (mn > 0 ? mn : 1e-9)).toFixed(3)) };
}

// GHS(GeneralizedHyperbolicStretch):把拉伸最陡处对准 SP(星云亮度)以选择性提亮暗弱星云。
// SP 默认设在背景中位数略上方;D=强度。属性名随版本 → 逐个 try 并报回实际设置。
function applyGHS(view, params) {
   if (typeof GeneralizedHyperbolicStretch == "undefined")
      throw new Error("GeneralizedHyperbolicStretch 不可用");
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   var bg = img.median();
   var D  = (params && params.D  != null) ? params.D  : 2.0;
   var b  = (params && params.b  != null) ? params.b  : 0.0;
   var SP = (params && params.SP != null) ? params.SP : Math.min(0.9, bg + 0.02);
   var LP = (params && params.LP != null) ? params.LP : Math.max(0, bg * 0.5);
   var HP = (params && params.HP != null) ? params.HP : 1.0;

   var P = new GeneralizedHyperbolicStretch;
   var info = { bg: Number(bg.toFixed(4)), SP: Number(SP.toFixed(4)), D: D, set: [] };
   function setp(name, val) {
      try {
         if (typeof P[name] != "undefined") { P[name] = val; info.set.push(name); }
      } catch (e) {}
   }
   setp("stretchType", 0);            // GHS
   setp("stretchFactor", D);          // 强度 D
   setp("localIntensity", b);         // 局部强度 b
   setp("symmetryPoint", SP);         // 对称点(对准星云亮度)
   setp("shadowProtection", LP);      // 阴影保护
   setp("highlightProtection", HP);   // 高光保护
   setp("blackPoint", 0.0);
   setp("useRGBWorkingSpace", true);  // 组合 RGB/K,彩色三通道一致
   setp("inverse", false);
   P.executeOn(view);
   return info;
}

// 本地天文解析(Tier 1):复用内置 ImageSolver 库,把解析写回窗口(供 SPCC 使用)
function applySolve(win) {
   if (typeof ImageSolver == "undefined")
      throw new Error("ImageSolver 库未加载");
   var engine = new ImageSolver;
   engine.initialize(win, false /*prioritizeSettings:从图像头取焦距/像元/坐标*/);
   engine.solveImage(win);
   if (!win.hasAstrometricSolution)
      throw new Error("solveImage 未产生天文解析");
   return "solved";
}

// 颜色校准(线性阶段)。
//   bn   = BackgroundNeutralization(背景中和)
//   cc   = ColorCalibration(白平衡)
//   bncc = BN + CC(宽带常用替代方案,无需解析/数据库)
//   spcc = SpectrophotometricColorCalibration(需 plate-solve + Gaia,待实现)
function applyColorCalibration(view, params) {
   var method = (params && params.method) ? params.method : "bncc";
   function doBN() {
      if (typeof BackgroundNeutralization == "undefined")
         throw new Error("BackgroundNeutralization 不可用");
      new BackgroundNeutralization().executeOn(view);
   }
   function doCC() {
      if (typeof ColorCalibration == "undefined")
         throw new Error("ColorCalibration 不可用");
      new ColorCalibration().executeOn(view);
   }
   if (method == "bn")   { doBN(); return "BackgroundNeutralization"; }
   if (method == "cc")   { doCC(); return "ColorCalibration"; }
   if (method == "bncc") { doBN(); doCC(); return "BN+CC"; }
   if (method == "spcc") {
      if (typeof SpectrophotometricColorCalibration == "undefined")
         throw new Error("SpectrophotometricColorCalibration 不可用");
      var P = new SpectrophotometricColorCalibration;
      // 关掉校准后弹出的图表/报告/星图窗口(会挡住看图)。属性名随版本不同 → 逐个探测并关闭
      var offProps = ["generateGraphs", "generateTextReports", "generateStarMaps",
                      "generatePNGs", "generateGraphImages"];
      var disabled = [];
      for (var i = 0; i < offProps.length; ++i) {
         var name = offProps[i];
         if (typeof P[name] != "undefined") {
            P[name] = false;
            disabled.push(name);
         }
      }
      // 依赖图像已完成天文解析;默认设置面向宽带 OSC(Sony 传感器为默认)
      P.executeOn(view);
      return { method: "SPCC", disabledOutputs: disabled };
   }
   throw new Error("colorcal method not implemented: " + method);
}

// 反卷积:BlurXTerminator。params.sharpenStars 控制缩星力度(0=不缩星,作者常用 0~0.2)
function applyDeconvolution(view, params) {
   if (typeof BlurXTerminator == "undefined")
      throw new Error("BlurXTerminator 未安装");
   var P = new BlurXTerminator;
   var info = {};
   // 探测并报告 BXT 的缩星属性名与默认值(不同版本属性名可能不同)
   var cands = ["sharpen_stars", "sharpenStars", "star_sharpening"];
   var prop = null;
   for (var i = 0; i < cands.length; ++i) {
      if (typeof P[cands[i]] != "undefined") { prop = cands[i]; break; }
   }
   if (prop) {
      info.starProp = prop;
      info.starDefault = P[prop];
      if (params && params.sharpenStars != null) {
         P[prop] = params.sharpenStars;
         info.starSet = params.sharpenStars;
      }
   } else {
      info.starProp = "(未找到缩星属性,已用默认)";
   }
   P.executeOn(view);
   return info;
}

// HOO 合成(OSC 双窄带):R=Hα($T[0]),G=B=OIII(默认 $T[1]+$T[2])
// 就地把 OSC 的 RGB 主图变换为 HOO 排布,仍为线性
function applyHOOCombine(view, params) {
   var ha   = (params && params.ha)   ? params.ha   : "$T[0]";
   var oiii = (params && params.oiii) ? params.oiii : "$T[1] + $T[2]";
   var P = new PixelMath;
   P.useSingleExpression = false;
   P.expression  = ha;      // R 通道
   P.expression1 = oiii;    // G 通道
   P.expression2 = oiii;    // B 通道
   P.createNewImage = false;
   P.rescale = false;
   P.truncate = true;       // 截断到 [0,1]
   P.executeOn(view);
   return { ha: ha, oiii: oiii };
}

// 核心保护迭代拉伸:GHS 拉伸一份副本 → 用当前亮度建核心保护蒙版 →
// 混合(核心保留原样、外环用拉伸版)。反复调用可把外环/暗云逐步提亮而亮核不过曝。
// 适用于双环星系(如 M94)、亮核+暗晕目标。默认作用于 mono 亮度图(superL)。
function applyMaskStretch(view, params) {
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   var med = img.median();
   var D       = (params && params.D != null) ? params.D : 1.0;
   var coreThr = (params && params.coreThr != null) ? params.coreThr : med * 3.0;  // 高于此=核心→保护
   var feather = (params && params.feather != null) ? params.feather : 15;          // 蒙版羽化(高斯sigma)
   var nCh = img.numberOfChannels, isColor = nCh >= 3;
   function clone(name) {
      var w = new ImageWindow(img.width, img.height, nCh, 32, true, isColor, name);
      w.mainView.beginProcess(UndoFlag_NoSwapFile);
      w.mainView.image.assign(img);
      w.mainView.endProcess();
      return w;
   }
   // 1. 拉伸副本(GHS)
   var sw = clone("ms_stretch");
   applyGHS(sw.mainView, { D: D, HP: (params && params.HP != null) ? params.HP : 0.9 });
   var sid = sw.mainView.id;
   // 2. 核心保护蒙版:核心=1(保护),其余=0;羽化
   var mw = clone("ms_mask");
   var Pm = new PixelMath;
   Pm.useSingleExpression = true;
   Pm.expression = "iif($T>" + coreThr + ",1,0)";
   Pm.createNewImage = false; Pm.rescale = false; Pm.truncate = true;
   Pm.executeOn(mw.mainView);
   var C = new Convolution;
   try { C.mode = 0; C.sigma = feather; C.shape = 2.0; } catch (e) {}
   C.executeOn(mw.mainView);
   var mid = mw.mainView.id;
   // 3. 混合:核心保留原样($T),外环用拉伸版
   var Pb = new PixelMath;
   Pb.useSingleExpression = true;
   Pb.expression = mid + "*$T + (1-" + mid + ")*" + sid;
   Pb.createNewImage = false; Pb.rescale = false; Pb.truncate = true;
   Pb.executeOn(view);
   try { sw.forceClose(); } catch (e) {}
   try { mw.forceClose(); } catch (e) {}
   return { D: D, coreThr: Number(coreThr.toFixed(5)), feather: feather };
}

// 挖线:把若干条线段所在的对角带像素置 0(供叠加前剔除卫星/飞机线)。
// params.lines = [[x0,y0,x1,y1],...] 全分辨率像素坐标;params.width = 带半宽(像素,默认 30)。
// 用 PixelMath 按点到直线距离判定。置 0 后整合用 sigmaLow 把这些像素当低离群丢弃。
function applyMaskLine(view, params) {
   var lines = (params && params.lines) || [];
   if (lines.length === 0) throw new Error("maskline 需要 params.lines");
   var w = (params && params.width != null) ? params.width : 30;
   var W = view.image.width, H = view.image.height;
   // 点到直线距离(像素坐标):|A*px+B*py+C|/sqrt(A^2+B^2)
   // px=X()*W, py=Y()*H
   var conds = [];
   for (var i = 0; i < lines.length; ++i) {
      var L = lines[i];
      var A = (L[3] - L[1]), B = -(L[2] - L[0]), C = (L[2] - L[0]) * L[1] - (L[3] - L[1]) * L[0];
      var norm = Math.sqrt(A * A + B * B) || 1;
      var d = "abs((" + A + ")*X()*" + W + "+(" + B + ")*Y()*" + H + "+(" + C + "))/" + norm;
      conds.push("(" + d + ")<" + w);
   }
   var cond = conds.join("||");
   var P = new PixelMath;
   P.useSingleExpression = true;
   P.expression = "iif(" + cond + ",0,$T)";
   P.createNewImage = false; P.rescale = false; P.truncate = true;
   P.executeOn(view);
   return { lines: lines.length, width: w };
}

// 去线状轨迹:对(星点)图做形态学开运算 —— 细线(窄于结构元)被抹掉,圆形星点保留。
function applyDelineTrail(view, params) {
   if (typeof MorphologicalTransformation == "undefined")
      throw new Error("MorphologicalTransformation 不可用");
   var P = new MorphologicalTransformation;
   var info = { set: [] };
   try {
      info.props = Object.getOwnPropertyNames(P).filter(function (k) {
         return k.charAt(0) !== "_" && typeof P[k] !== "function";
      });
   } catch (e) {}
   function mset(n, v) { try { if (typeof P[n] != "undefined") { P[n] = v; info.set.push(n + "=" + v); } } catch (e) {} }
   mset("operator", (params && params.operator != null) ? params.operator : 2);  // 2 = Opening
   if (params && params.iterations != null) mset("numberOfIterations", params.iterations);
   if (params && params.amount != null) mset("amount", params.amount);
   P.executeOn(view);
   return info;
}

// Ha 融合"小红花":把 Ha 相对 R 的发射超出量加进 R 通道(HII 区变红,连续谱不变)。
// view = 彩色图;params.ha = 已拉伸到相近尺度的 Ha 路径;params.amount = 强度(默认 0.5)。
function applyHaBlend(view, params) {
   var hp = params && params.ha;
   if (!hp || !File.exists(hp)) throw new Error("hablend 需要 params.ha(已拉伸的 Ha): " + hp);
   var amt = (params && params.amount != null) ? params.amount : 0.5;
   var hw = ImageWindow.open(hp)[0];
   try {
      var hid = hw.mainView.id;
      var P = new PixelMath;
      P.useSingleExpression = false;   // 分通道
      P.expression  = "$T[0] + " + amt + "*max(0," + hid + "-med(" + hid + "))";  // R:加 Ha 高于自身背景的发射量
      P.expression1 = "$T[1]";                                          // G 不变
      P.expression2 = "$T[2]";                                          // B 不变
      P.createNewImage = false; P.rescale = false; P.truncate = true;
      P.executeOn(view);
      return { ha: hp, amount: amt };
   } finally { try { hw.forceClose(); } catch (e) {} }
}

// RGB 合成:把三个单通道 master(R/G/B 路径)用 ChannelCombination 合成一张彩色图。
// 返回新窗口(拷贝 R 的 FITS 头,便于后续解析/SPCC)。
function applyRGBCombine(params) {
   if (typeof ChannelCombination == "undefined")
      throw new Error("ChannelCombination 不可用");
   function op(p) {
      if (!p || !File.exists(p)) throw new Error("通道文件不存在: " + p);
      var a = ImageWindow.open(p);
      if (!a || a.length == 0) throw new Error("打开失败: " + p);
      return a[0];
   }
   var rw = op(params.r), gw = op(params.g), bw = op(params.b);
   try {
      var W = rw.mainView.image.width, H = rw.mainView.image.height;
      var out = new ImageWindow(W, H, 3, 32, true, true, "rgb");
      var P = new ChannelCombination;
      P.colorSpace = 0;   // 0 = RGB
      P.channels = [[true, rw.mainView.id], [true, gw.mainView.id], [true, bw.mainView.id]];
      out.mainView.beginProcess(UndoFlag_NoSwapFile);
      P.executeOn(out.mainView);
      out.mainView.endProcess();
      try { if (rw.keywords) out.keywords = rw.keywords; } catch (e) {}
      log("rgbcombine: R+G+B → " + W + "x" + H);
      return { win: out };
   } finally {
      try { rw.forceClose(); } catch (e) {}
      try { gw.forceClose(); } catch (e) {}
      try { bw.forceClose(); } catch (e) {}
   }
}

// LRGB:把亮度通道 L(superL,路径)套到当前彩色 view 上。
// 默认用**保色亮度替换**(每通道 × L/meanRGB):严格保持色比(色相/饱和不变),
// 只把亮度换成 L —— 避免 LRGBCombination 在 Lab 空间对亮区(星系核)造成的色偏。
function applyLRGB(view, params) {
   var lp = params && params.l;
   if (!lp || !File.exists(lp)) throw new Error("L 通道文件不存在: " + lp);
   var lw = ImageWindow.open(lp)[0];
   try {
      var lid = lw.mainView.id;
      if (params && params.method == "lrgbcombination" && typeof LRGBCombination != "undefined") {
         var P = new LRGBCombination;
         P.channels = [[true, lid, 1.0], [false, "", 1.0], [false, "", 1.0], [false, "", 1.0]];
         P.executeOn(view);
         return { l: lp, method: "lrgbcombination" };
      }
      // 保色亮度替换(默认)
      var Pm = new PixelMath;
      Pm.useSingleExpression = true;
      Pm.expression = "$T * " + lid + " / max(1e-5,($T[0]+$T[1]+$T[2])/3)";
      Pm.createNewImage = false; Pm.rescale = false; Pm.truncate = true;
      Pm.executeOn(view);
      return { l: lp, method: "ratio" };
   } finally {
      try { lw.forceClose(); } catch (e) {}
   }
}

// 星点分离:StarXTerminator。view 变为去星图,并生成独立星点图窗口
// 返回星点窗口(可能为 null);unscreen 便于后续 screen 合成
function applyStarSeparation(view, params) {
   if (typeof StarXTerminator == "undefined")
      throw new Error("StarXTerminator 未安装");
   var P = new StarXTerminator;
   try { P.stars    = true; } catch (e) {}   // 生成星点图
   try { P.unscreen = true; } catch (e) {}   // 反屏幕,利于重新合成
   P.executeOn(view);
   var starsId = view.id + "_stars";
   var starsWin = null;
   try {
      var w = ImageWindow.windowById(starsId);
      if (w && !w.isNull) starsWin = w;
   } catch (e) {}
   return { starsId: starsId, starsWin: starsWin };
}

// 降噪:NoiseXTerminator(默认参数)
function applyDenoise(view, params) {
   if (typeof NoiseXTerminator == "undefined")
      throw new Error("NoiseXTerminator 未安装");
   var P = new NoiseXTerminator;
   var info = { set: [] };
   try {
      info.props = Object.getOwnPropertyNames(P).filter(function (k) {
         return k.charAt(0) !== "_" && typeof P[k] !== "function";
      });
   } catch (e) {}
   function nset(name, val) {
      try { if (typeof P[name] != "undefined") { P[name] = val; info.set.push(name + "=" + val); } } catch (e) {}
   }
   if (params && params.denoise != null) nset("denoise", params.denoise);   // 降噪强度 0~1
   if (params && params.detail  != null) nset("detail",  params.detail);    // 细节保留 0~1
   if (params && params.iterations != null) nset("iterations", params.iterations);
   if (params && params.colorSep != null) nset("enable_color_separation", !!params.colorSep);
   if (params && params.denoiseColor != null) nset("denoise_color", params.denoiseColor);       // 色度降噪
   if (params && params.freqSep != null) nset("enable_frequency_separation", !!params.freqSep);
   if (params && params.denoiseLF != null) nset("denoise_lf", params.denoiseLF);                 // 低频(大尺度斑驳)
   if (params && params.denoiseLFColor != null) nset("denoise_lf_color", params.denoiseLFColor); // 低频色度
   P.executeOn(view);
   return info;
}

// 去绿:SCNR。默认 amount=0.75(不全量去绿,更自然),去绿(Green)
function applySCNR(view, params) {
   var amount = (params && params.amount != null) ? params.amount : 0.75;
   var P = new SCNR;
   P.amount = amount;
   try { P.colorToRemove = SCNR.prototype.Green; } catch (e) {}
   try { P.protectionMethod = SCNR.prototype.AverageNeutral; } catch (e) {}
   P.executeOn(view);
   return { amount: amount };
}

// 曲线:CurvesTransformation。contrast=K 通道 S 曲线(加对比);saturation=S 通道提饱和
function applyCurves(view, params) {
   var P = new CurvesTransformation;
   var did = {};
   if (params && params.contrast != null && params.contrast != 0) {
      var c = params.contrast;   // 建议 0.05~0.20
      P.K = [[0.0, 0.0],
             [0.25, Math.max(0, 0.25 - c)],
             [0.75, Math.min(1, 0.75 + c)],
             [1.0, 1.0]];
      did.contrast = c;
   }
   if (params && params.saturation != null && params.saturation != 0) {
      var s = params.saturation; // 建议 0.05~0.25
      P.S = [[0.0, 0.0], [0.5, Math.min(1, 0.5 + s)], [1.0, 1.0]];
      did.saturation = s;
   }
   if (params && params.blackpoint != null && params.blackpoint > 0) {
      // 黑场拉伸:把输入 bp 映射到 0、1 保持 1(两点线性),压暗背景且不抬高光
      var bp = Math.max(0, Math.min(0.95, params.blackpoint));
      P.K = [[0.0, 0.0], [bp, 0.0], [1.0, 1.0]];   // 0..bp 压到黑,bp..1 线性,不抬高光
      did.blackpoint = bp;
   }
   if (params && params.highlight != null && params.highlight > 0) {
      // 高光压缩:把白场 1.0 拉到 1-h,收住过亮核心/星点,不动暗部
      var h = Math.max(0, Math.min(0.6, params.highlight));
      P.K = [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0 - h]];
      did.highlight = h;
   }
   if (params && params.brightness != null && params.brightness != 0) {
      var b = params.brightness; // 中值提亮
      P.K = [[0.0, 0.0], [0.5, Math.min(1, 0.5 + b)], [1.0, 1.0]];
      did.brightness = b;
   }
   P.executeOn(view);
   return did;
}

// 星点合成:把 stars 图以 screen 方式叠回 starless(view=starless)
// params.stars: 已(拉伸好的)星点图路径
function applyRecombine(view, params) {
   var starsPath = params ? params.stars : null;
   if (!starsPath || !File.exists(starsPath))
      throw new Error("recombine: stars image not found: " + starsPath);
   var arr = ImageWindow.open(starsPath);
   if (!arr || arr.length == 0)
      throw new Error("recombine: failed to open stars: " + starsPath);
   var starsWin = arr[0];
   var starsViewId = starsWin.mainView.id;
   // 星点强度系数:<1 时把星点整体压暗(避免过亮/喧宾夺主)
   var amt = (params && params.starAmount != null) ? Math.max(0, Math.min(1, params.starAmount)) : 1.0;
   var starTerm = (amt >= 0.999) ? starsViewId : ("(" + starsViewId + "*" + amt + ")");
   try {
      var P = new PixelMath;
      P.useSingleExpression = true;
      // screen 混合:~((~starless)*(~(stars*amt)))
      P.expression = "~((~$T) * (~" + starTerm + "))";
      P.createNewImage = false;
      P.rescale = false;
      P.truncate = true;
      P.executeOn(view);
   } finally {
      try { starsWin.forceClose(); } catch (e) {}
   }
   return { stars: starsPath, mode: "screen", starsView: starsViewId, starAmount: amt };
}

// 自动去灰尘暗影(平场残留):在(去星)图上用大尺度高斯模型填补背景中明显暗于模型的暗斑。
// 仅作用于背景区(模型 < bgCeil)且像素明显暗于模型(< model-thr)→ 用模型值填充;
// 星云主体(模型亮)及其内部真实暗尘埃带不受影响。相当于自动化的"背景 CloneStamp"。
function applyDustRemove(view, params) {
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   var med = img.median();
   var sigma  = (params && params.sigma  != null) ? params.sigma  : 40;   // 模型平滑尺度(需 > 灰尘斑尺寸)
   var thr    = (params && params.thr    != null) ? params.thr    : Math.max(0.006, med * 0.08); // 暗影阈值
   var thrHi  = (params && params.thrBright != null) ? params.thrBright : Math.max(0.04, med * 0.4); // 亮斑阈值(远高于噪声,只抓强亮斑)
   var bgCeil = (params && params.bgCeil != null) ? params.bgCeil : med * 1.8;
   var info = { median: Number(med.toFixed(5)), sigma: sigma, thr: Number(thr.toFixed(5)),
                thrBright: Number(thrHi.toFixed(5)), bgCeil: Number(bgCeil.toFixed(5)) };

   // 1. 背景模型:克隆 + 大高斯卷积
   var mw = new ImageWindow(img.width, img.height, img.numberOfChannels, 32, true,
                            img.numberOfChannels >= 3, "dust_model");
   mw.mainView.beginProcess(UndoFlag_NoSwapFile);
   mw.mainView.image.assign(img);
   mw.mainView.endProcess();
   var C = new Convolution;
   info.convProps = [];
   try {
      info.convProps = Object.getOwnPropertyNames(C).filter(function (k) {
         return k.charAt(0) !== "_" && typeof C[k] !== "function";
      });
   } catch (e) {}
   function cset(n, v) { try { if (typeof C[n] != "undefined") { C[n] = v; info["set_" + n] = v; } } catch (e) {} }
   cset("mode", 0);          // 0 = Parametric(参数化高斯)
   cset("sigma", sigma);
   cset("shape", 2.0);       // 2 = 高斯
   C.executeOn(mw.mainView);
   var mid = mw.mainView.id;

   // 2. 只填"背景区 & 明显暗于模型"的像素
   try {
      var P = new PixelMath;
      P.useSingleExpression = true;
      // 背景区(model<bgCeil)内:过暗(<model-thr,暗影)或过亮(>model+thrHi,亮斑/星残留)→ 用模型填平
      P.expression = "iif(" + mid + " < " + bgCeil + " && ($T < " + mid + " - " + thr +
                     " || $T > " + mid + " + " + thrHi + "), " + mid + ", $T)";
      P.createNewImage = false;
      P.rescale = false;
      P.truncate = true;
      P.executeOn(view);
   } finally {
      try { mw.forceClose(); } catch (e) {}
   }
   return info;
}

// ============================================================
// 执行单个 job
// ============================================================
function runJob(job) {
   var res = {
      job_id: job.job_id,
      op: job.op,
      status: "ok",
      error: null,
      metrics: null,
      image: null,
      preview: null
   };
   var outputs = job.outputs || {};
   var previewPath = outputs.preview || (RUN_DIR + "/" + job.job_id + "_preview.png");
   var win = null, created = false;

   try {
      if (job.op == "probe") {
         res.capabilities = probeCapabilities();
         return res;
      }
      else if (job.op == "checksolve") {
         if (!job.input || !File.exists(job.input))
            throw new Error("input not found: " + job.input);
         var cw = ImageWindow.open(job.input)[0];
         var info = {};
         try { info.hasSolution = cw.hasAstrometricSolution; }
         catch (e) { info.solErr = String(e); }
         var want = ["RA","DEC","OBJCTRA","OBJCTDEC","OBJECT","FOCALLEN","FOCALLENGTH",
                     "XPIXSZ","YPIXSZ","PIXSIZE","INSTRUME","TELESCOP",
                     "CTYPE1","CRVAL1","CRVAL2","CD1_1"];
         var got = {};
         try {
            var kw = cw.keywords || [];
            for (var i = 0; i < kw.length; ++i)
               if (want.indexOf(kw[i].name) >= 0) got[kw[i].name] = kw[i].value;
         } catch (e) { info.kwErr = String(e); }
         info.keywords = got;
         try { cw.forceClose(); } catch (e) {}
         res.solveInfo = info;
         return res;
      }
      else if (job.op == "bgstats") {
         if (!job.input || !File.exists(job.input))
            throw new Error("input not found: " + job.input);
         var bw = ImageWindow.open(job.input)[0];
         try { res.bgStats = bgStats(bw.mainView.image, job.params ? job.params.grid : 3); }
         finally { try { bw.forceClose(); } catch (e) {} }
         return res;
      }
      else if (job.op == "edgecheck") {
         if (!job.input || !File.exists(job.input))
            throw new Error("input not found: " + job.input);
         var ew = ImageWindow.open(job.input)[0];
         try { res.edgeAnalysis = edgeCheck(ew.mainView.image, job.params); }
         finally { try { ew.forceClose(); } catch (e) {} }
         return res;
      }
      else if (job.op == "selftest") {
         win = makeSyntheticWindow();
         created = true;
      }
      else if (job.op == "integrate") {
         var ir = applyIntegration(job.params);
         win = ir.win;
         created = true;
         res.applied = { integrated: ir.count, diag: ir.diag };
      }
      else if (job.op == "rgbcombine") {
         var rc = applyRGBCombine(job.params);
         win = rc.win;
         created = true;
         res.applied = { rgbcombine: true };
      }
      else if (job.op == "inspect" || job.op == "crop" ||
               job.op == "gradient" || job.op == "deconv" ||
               job.op == "hoo" || job.op == "starsep" || job.op == "stretch" ||
               job.op == "denoise" || job.op == "scnr" || job.op == "recombine" ||
               job.op == "curves" || job.op == "colorcal" || job.op == "solve" ||
               job.op == "ghs" || job.op == "dustremove" || job.op == "lrgb" ||
               job.op == "delinetrail" || job.op == "maskline" ||
               job.op == "maskstretch" || job.op == "hablend") {
         if (!job.input || !File.exists(job.input))
            throw new Error("input not found: " + job.input);
         var arr = ImageWindow.open(job.input);
         if (!arr || arr.length == 0)
            throw new Error("failed to open: " + job.input);
         win = arr[0];
         created = true;
      }
      else {
         throw new Error("unknown op: " + job.op);
      }

      var view = win.mainView;

      // ---- op 特有的处理 ----
      if (job.op == "crop") {
         var cropRes = cropToNewWindow(view, job.params);
         res.applied = cropRes.applied;
         res.cropDiag = cropRes.diag;
         if (cropRes.win) {
            // 用裁切后的新窗口替换原窗口(新窗口无天文解析,后续保存不弹框)
            try { win.forceClose(); } catch (e) {}
            win = cropRes.win;
            view = win.mainView;
         }
      }
      else if (job.op == "gradient") {
         res.applied = applyGradientCorrection(view, job.params);
      }
      else if (job.op == "colorcal") {
         res.applied = applyColorCalibration(view, job.params);
      }
      else if (job.op == "solve") {
         res.applied = applySolve(win);   // 本地解析,写回窗口;保存后带解析
      }
      else if (job.op == "ghs") {
         res.applied = applyGHS(view, job.params);
      }
      else if (job.op == "dustremove") {
         res.applied = applyDustRemove(view, job.params);
      }
      else if (job.op == "lrgb") {
         res.applied = applyLRGB(view, job.params);
      }
      else if (job.op == "delinetrail") {
         res.applied = applyDelineTrail(view, job.params);
      }
      else if (job.op == "maskline") {
         res.applied = applyMaskLine(view, job.params);
      }
      else if (job.op == "maskstretch") {
         res.applied = applyMaskStretch(view, job.params);
      }
      else if (job.op == "hablend") {
         res.applied = applyHaBlend(view, job.params);
      }
      else if (job.op == "deconv") {
         res.applied = applyDeconvolution(view, job.params);
      }
      else if (job.op == "hoo") {
         res.applied = applyHOOCombine(view, job.params);
      }
      else if (job.op == "starsep") {
         var sep = applyStarSeparation(view, job.params);
         res.applied = { starsId: sep.starsId, starsFound: !!sep.starsWin };
         var starsOut = outputs.stars || (RUN_DIR + "/" + job.job_id + "_stars.xisf");
         if (sep.starsWin) {
            sep.starsWin.saveAs(starsOut, false, false, false, false);
            res.stars = starsOut;
            try { sep.starsWin.forceClose(); } catch (e) {}
         }
      }
      else if (job.op == "stretch") {
         var p = job.params || {};
         var tbg = (p.targetBackground != null) ? p.targetBackground : 0.25;
         var sc  = (p.shadowClip != null) ? p.shadowClip : -2.80;
         var linked = (p.linked != null) ? p.linked : true;
         if (p.stfFrom) {
            // 策略2:从参考图(全图)算 STF,套到当前图(如星点图 线性→非线性)
            if (!File.exists(p.stfFrom))
               throw new Error("stfFrom not found: " + p.stfFrom);
            var refArr = ImageWindow.open(p.stfFrom);
            var H;
            try { H = computeStretchH(refArr[0].mainView.image, tbg, sc, linked); }
            finally { try { refArr[0].forceClose(); } catch (e) {} }
            applyHMatrix(view, H);
            res.applied = { stfFrom: p.stfFrom, linked: linked };
         } else if (p.mode == "stars") {
            applyStarStretch(view, p);          // 星点专用:压黑背景,提亮星点
         } else {
            autoStretch(view, tbg, sc, linked); // 就地拉伸,烘焙为非线性
         }
      }
      else if (job.op == "denoise") {
         res.applied = applyDenoise(view, job.params);
      }
      else if (job.op == "scnr") {
         res.applied = applySCNR(view, job.params);
      }
      else if (job.op == "recombine") {
         res.applied = applyRecombine(view, job.params);
      }
      else if (job.op == "curves") {
         res.applied = applyCurves(view, job.params);
      }

      // ---- 统计 + 预览 ----
      // 非线性域的 op(拉伸及其之后)预览不再二次拉伸;线性数据需拉伸才可见。
      // 可由 params.linear 显式覆盖(如对线性图做降噪)。
      // 预览是否需要拉伸:用**数据中位数**判断线性/非线性(最可靠)。
      // 线性天体数据背景中位数极低(~1e-3);任何拉伸后会跳到 ~0.05+。
      // 这样 crop/starsep 等"状态随输入而定"的 op 也能忠实预览,不会二次拉伸。
      var NONLINEAR_OPS = { stretch:1, scnr:1, denoise:1, recombine:1, curves:1, ghs:1 };
      var med = 0;
      try { view.image.resetSelections(); med = view.image.median(); } catch (e) {}
      var isNonlinear = (med > 0.03) || !!NONLINEAR_OPS[job.op];
      if (job.params && job.params.linear != null)   // 显式覆盖仍优先
         isNonlinear = !job.params.linear;
      res.metrics = computeStats(view.image);
      res.preview_diag = exportPreview(view, previewPath, !isNonlinear);
      res.preview_diag.median = Number(med.toFixed(5));
      res.preview_diag.previewStretched = !isNonlinear;
      res.preview = previewPath;

      // ---- 保存输出(变换类 op 默认落盘,便于管线串接)----
      var TRANSFORM_OPS = { integrate:1, crop:1, gradient:1, deconv:1, hoo:1, starsep:1,
                            stretch:1, denoise:1, scnr:1, recombine:1, curves:1,
                            colorcal:1, solve:1, ghs:1 };
      var imageOut = outputs.image;
      if (!imageOut && TRANSFORM_OPS[job.op])
         imageOut = RUN_DIR + "/" + job.job_id + ".xisf";
      if (imageOut) {
         win.saveAs(imageOut, false, false, false, false);
         res.image = imageOut;
      }
   } catch (e) {
      res.status = "error";
      res.error = (e && e.message) ? e.message : String(e);
      warn("job " + job.job_id + " failed: " + res.error);
   } finally {
      if (created && win) {
         try { win.forceClose(); } catch (e) {}
      }
   }
   return res;
}

// 处理一个 job 文件:inbox → processing → 执行 → done
function processOne(name) {
   var src  = INBOX + "/" + name;
   var proc = PROCESSING + "/" + name;

   try {
      if (File.exists(proc)) File.remove(proc);
      File.move(src, proc);
   } catch (e) {
      // 抢占失败/文件被占用,下一轮再试
      return;
   }

   var job = null;
   try {
      job = JSON.parse(readAllText(proc));
   } catch (e) {
      warn("bad job json (" + name + "): " + e);
      try { File.remove(proc); } catch (e2) {}
      return;
   }

   log("run job " + job.job_id + " op=" + job.op);
   var res = runJob(job);
   try {
      writeAllText(DONE + "/" + job.job_id + ".json", JSON.stringify(res, null, 2));
      log("done " + job.job_id + " status=" + res.status);
   } catch (e) {
      warn("failed writing result for " + job.job_id + ": " + e);
   }
   try { File.remove(proc); } catch (e) {}

   // 大图连续处理易累积内存/交换文件 → 每个 job 后强制回收,缓解 PI 变卡/无响应
   try { gc(); } catch (e) {}
}

// ============================================================
// 主循环
// ============================================================
function main() {
   ensureDirs();
   console.abortEnabled = true;
   // 清理残留 STOP 文件:避免"上次停止时写的 STOP 没人消费"导致新 runner 一启动就退出
   try { if (File.exists(STOP_FILE)) File.remove(STOP_FILE); } catch (e) {}
   log("started. watching " + INBOX);
   log("stop by creating file: " + STOP_FILE + "  (or click Abort)");

   for (;;) {
      processEvents();

      if (console.abortRequested) { log("aborted by console."); break; }
      if (File.exists(STOP_FILE)) {
         try { File.remove(STOP_FILE); } catch (e) {}
         log("STOP file detected, exiting.");
         break;
      }

      try { writeAllText(HEARTBEAT, String(nowMs())); } catch (e) {}

      var names = listJobFiles();
      for (var i = 0; i < names.length; ++i) {
         if (console.abortRequested || File.exists(STOP_FILE)) break;
         processOne(names[i]);
      }

      msleep(POLL_MS);
   }
   log("runner stopped.");
}

main();
