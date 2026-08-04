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

// 软拉伸(复刻 EZ Soft Stretch):一次 HT,目标中位数偏高(默认 0.20,比常规拉伸亮、揭示暗部),
// 并把 HT 行的 lowRange(第4位)设为 -expandLow 展宽低段 → 把暗星云/暗 Hα 提出来。
// 适合 M8 这类中等动态目标;**不适合** M42(核心会过曝)和极暗反射(太暗,应走 GHS)。
// params: targetMedian(默认0.20)、expandLow(低段展宽,默认0.05,越大暗部提得越多)、
//         shadowClip(默认-1.5)、linked(默认true)。
function applySoftStretch(view, params) {
   var tm = (params && params.targetMedian != null) ? params.targetMedian : 0.20;
   var expandLow = (params && params.expandLow != null) ? Math.abs(params.expandLow) : 0.05;
   var sc = (params && params.shadowClip != null) ? params.shadowClip : -1.5;
   var linked = (params && params.linked != null) ? params.linked : true;
   var img = view.image;
   var H = computeStretchH(img, tm, sc, linked);
   var lo = -expandLow;
   if (linked || img.numberOfChannels < 3) { H[3][3] = lo; }
   else { H[0][3] = lo; H[1][3] = lo; H[2][3] = lo; }
   applyHMatrix(view, H);
   return { targetMedian: tm, expandLow: expandLow, shadowClip: sc, linked: linked };
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
// 残差集:中位叠加出参考帧,逐帧算残差(帧−参考,取正)→ 拉伸+缩小存缩略图 PNG。
// 供全自动去线用:静态的星云/星点在残差里抵消,只剩逐帧瞬时结构(卫星/飞机线、宇宙线),
// Python 端用 cv2 Hough 在残差缩略图上检出长直线(=卫星线),再回来 maskline 挖除。
// 残差用 createNewImage 新图(无天文解析)→ IntegerResample 不弹"删除解析"框。
function applyResidualSet(params) {
   var imgs = params.images;
   if (!imgs || imgs.length < 3) throw new Error("residualset 需要 ≥3 张");
   var outDir = params.outDir;
   var zoom = Math.abs((params.zoom != null) ? params.zoom : 8);
   var II = new ImageIntegration;
   var rows = []; for (var i = 0; i < imgs.length; ++i) rows.push([true, imgs[i], "", ""]);
   II.images = rows;
   // 常量在 job-runner 上下文可能 undefined → try 原型、失败用数值(Median=1/NoRejection=0/NoNorm=0)
   try { II.combination = ImageIntegration.prototype.Median; } catch (e) { try { II.combination = 1; } catch (e2) {} }
   try { II.rejection = ImageIntegration.prototype.NoRejection; } catch (e) { try { II.rejection = 0; } catch (e2) {} }
   try { II.normalization = ImageIntegration.prototype.NoNormalization; } catch (e) { try { II.normalization = 0; } catch (e2) {} }
   try { II.weightMode = ImageIntegration.prototype.DontCare; } catch (e) { try { II.weightMode = 0; } catch (e2) {} }
   try { II.generateRejectionMaps = false; } catch (e) {}
   II.executeGlobal();
   var refId = II.integrationImageId;
   var refWin = ImageWindow.windowById(refId);
   var refImg = refWin.mainView.image;
   var fullW = refImg.width, fullH = refImg.height;
   var nch = refImg.numberOfChannels;   // 残差表达式按通道数自适应(黑白=1,OSC/RGB=3)
   var resExpr;
   if (nch >= 3)
      resExpr = "max( ( ($T[0]-" + refId + "[0])+($T[1]-" + refId + "[1])+($T[2]-" + refId + "[2]) )/3, 0 )";
   else
      resExpr = "max( $T[0]-" + refId + "[0], 0 )";
   var thumbs = [];
   for (var i = 0; i < imgs.length; ++i) {
      if (!File.exists(imgs[i])) continue;
      var wa = ImageWindow.open(imgs[i]); if (!wa || wa.length == 0) continue;
      var w = wa[0]; if (w.isNull) continue;
      var v = w.mainView;
      var rid = "restmp_" + i;
      var old = ImageWindow.windowById(rid); if (old && !old.isNull) { try { old.forceClose(); } catch (e) {} }
      var PM = new PixelMath;
      PM.expression = resExpr;
      PM.useSingleExpression = true; PM.createNewImage = true; PM.newImageId = rid;
      PM.rescale = false; PM.truncate = true;
      PM.executeOn(v, false);
      var rw = ImageWindow.windowById(rid); var rv = rw.mainView;
      autoStretch(rv, 0.30, -2.8, true);
      var IR = new IntegerResample; IR.zoomFactor = -zoom; IR.executeOn(rv, false);
      var tp = outDir + "/res_" + i + ".png";
      rw.saveAs(tp, false, false, false, false);
      rw.forceClose(); w.forceClose();
      thumbs.push({ idx: i, path: imgs[i], thumb: tp });
   }
   try { refWin.forceClose(); } catch (e) {}
   return { count: thumbs.length, fullW: fullW, fullH: fullH, zoom: zoom, thumbs: thumbs };
}

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

// 逐通道多项式背景扣除:对每通道拟合 deg 阶 2D 多项式背景(网格采样 + 亮度剔除亮区),
// 用 PixelMath 归一化坐标 X()/Y() 构造模型表达式,逐通道扣除(减模型+加回均值)。
// 只除平滑大尺度色彩梯度(deg1=平面 / deg2=二次可抓角落弯曲),不动高频尘埃/星云结构。
// 专治"亮源旁角落"这类 ABE 欠拟合的残留色彩梯度(如 IC4592 ν Sco 旁的对角红)。
function solveLinearSystem(A, b, n) {
   // 高斯消元(带部分主元),解 A x = b,A 为 n×n,就地修改
   for (var col = 0; col < n; ++col) {
      var piv = col;
      for (var r = col + 1; r < n; ++r) if (Math.abs(A[r][col]) > Math.abs(A[piv][col])) piv = r;
      if (piv != col) { var t = A[piv]; A[piv] = A[col]; A[col] = t; var tb = b[piv]; b[piv] = b[col]; b[col] = tb; }
      var d = A[col][col];
      if (Math.abs(d) < 1e-20) continue;
      for (var r2 = 0; r2 < n; ++r2) {
         if (r2 == col) continue;
         var f = A[r2][col] / d;
         if (f == 0) continue;
         for (var k = col; k < n; ++k) A[r2][k] -= f * A[col][k];
         b[r2] -= f * b[col];
      }
   }
   var x = new Array(n);
   for (var i = 0; i < n; ++i) x[i] = (Math.abs(A[i][i]) < 1e-20) ? 0 : b[i] / A[i][i];
   return x;
}
function applyPolyBg(view, params) {
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   var W = img.width, H = img.height, nc = img.numberOfChannels;
   var deg  = (params && params.degree != null) ? params.degree : 2;
   var nx   = (params && params.nx != null) ? params.nx : 24;
   var ny   = (params && params.ny != null) ? params.ny : 16;
   var krej = (params && params.reject != null) ? params.reject : 2.5;
   var cw = Math.floor(W / nx), ch = Math.floor(H / ny);
   var half = Math.max(4, Math.floor(Math.min(cw, ch) * 0.30));
   // 1. 网格采样:每格取各通道中位数 + 亮度
   var samples = [], lums = [];
   for (var gy = 0; gy < ny; ++gy) for (var gx = 0; gx < nx; ++gx) {
      var cx = Math.floor((gx + 0.5) * cw), cy = Math.floor((gy + 0.5) * ch);
      var x0 = Math.max(0, cx - half), y0 = Math.max(0, cy - half);
      var x1 = Math.min(W, cx + half), y1 = Math.min(H, cy + half);
      var v = [], ok = true, lum = 0;
      for (var c = 0; c < nc; ++c) {
         try {
            img.selectedRect = new Rect(x0, y0, x1, y1);
            img.firstSelectedChannel = c; img.lastSelectedChannel = c;
            var m = img.median(); v.push(m); lum += m;
         } catch (e) { ok = false; }
      }
      try { img.resetSelections(); } catch (e) {}
      if (ok) { lum /= nc; samples.push({ X: cx / W, Y: cy / H, v: v, lum: lum }); lums.push(lum); }
   }
   // 2. 亮度阈值剔除亮区(星云/亮源),只留背景格
   lums.sort(function (a, b) { return a - b; });
   var midL = lums.length ? lums[Math.floor(lums.length / 2)] : 0;
   var madA = []; for (var i = 0; i < lums.length; ++i) madA.push(Math.abs(lums[i] - midL));
   madA.sort(function (a, b) { return a - b; });
   var madL = madA.length ? madA[Math.floor(madA.length / 2)] * 1.4826 : midL * 0.1 + 1e-9;
   var thr = midL + krej * madL;
   var acc = samples.filter(function (s) { return s.lum <= thr; });
   // 3. 多项式项 (i,j) with i+j<=deg
   var terms = [];
   for (var d = 0; d <= deg; ++d) for (var j = 0; j <= d; ++j) terms.push([d - j, j]);
   var nt = terms.length;
   function basisStr(i, j) {
      var parts = [];
      for (var a = 0; a < i; ++a) parts.push("X()");
      for (var b = 0; b < j; ++b) parts.push("Y()");
      return parts.length ? parts.join("*") : "1";
   }
   // 4. 逐通道最小二乘拟合 + 构造扣除表达式
   var exprs = [], info = { degree: deg, samples: acc.length, rejected: samples.length - acc.length, thr: Number(thr.toFixed(5)), terms: nt };
   for (var c2 = 0; c2 < nc; ++c2) {
      var AtA = [], Atb = [];
      for (var a2 = 0; a2 < nt; ++a2) { var row = []; for (var b2 = 0; b2 < nt; ++b2) row.push(0); AtA.push(row); Atb.push(0); }
      for (var s = 0; s < acc.length; ++s) {
         var basis = [];
         for (var t = 0; t < nt; ++t) basis.push(Math.pow(acc[s].X, terms[t][0]) * Math.pow(acc[s].Y, terms[t][1]));
         var val = acc[s].v[c2];
         for (var a3 = 0; a3 < nt; ++a3) { Atb[a3] += basis[a3] * val; for (var b3 = 0; b3 < nt; ++b3) AtA[a3][b3] += basis[a3] * basis[b3]; }
      }
      var coef = solveLinearSystem(AtA, Atb, nt);
      var mmean = 0;
      for (var s2 = 0; s2 < acc.length; ++s2) { var mv = 0; for (var t2 = 0; t2 < nt; ++t2) mv += coef[t2] * Math.pow(acc[s2].X, terms[t2][0]) * Math.pow(acc[s2].Y, terms[t2][1]); mmean += mv; }
      mmean = acc.length ? mmean / acc.length : 0;
      // model 表达式
      var modelTerms = [];
      for (var t3 = 0; t3 < nt; ++t3) modelTerms.push("(" + coef[t3].toFixed(10) + ")*" + basisStr(terms[t3][0], terms[t3][1]));
      var model = modelTerms.join("+");
      // 通道自身:useSingleExpression=false 时 $T 指当前通道 → new = $T - (model - mmean)
      exprs.push("$T - (" + model + ") + (" + mmean.toFixed(10) + ")");
   }
   var P = new PixelMath;
   P.useSingleExpression = false;
   P.expression  = exprs[0];
   if (nc > 1) P.expression1 = exprs[1];
   if (nc > 2) P.expression2 = exprs[2];
   P.createNewImage = false; P.rescale = false; P.truncate = true;
   P.executeOn(view);
   return info;
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
      // 关键:必须 replaceImage=true 就地替换,否则 GraXpert 只新建一张校正图、不动原图(表现为"空操作")
      gset("replaceImage", (params && params.replaceImage != null) ? params.replaceImage : true);
      gset("createBackground", (params && params.createBackground != null) ? params.createBackground : false);
      if (params && params.correction != null) gset("correction", params.correction);
      if (params && params.appPath) gset("appPath", params.appPath);   // 需要外部程序时用户配置
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

// 星点饱和度量化:采样亮像素(星点),算 HSV 饱和度 S=(max-min)/max 的均值/中位/P90。
// 用于确认星点色彩是否到位(经验:satMean 0.25~0.4 为自然有色;<0.15 偏灰)。
function computeStarStats(img, params) {
   try { img.resetSelections(); } catch (e) {}
   if (img.numberOfChannels < 3) return { error: "需要彩色图" };
   var W = img.width, H = img.height;
   var med = img.median();
   var thr = (params && params.thr != null) ? params.thr : Math.min(0.5, med * 3 + 0.06);
   var target = 120000;
   var step = Math.max(1, Math.round(Math.sqrt(W * H / target)));
   var sats = [], n = 0;
   for (var y = 0; y < H; y += step) {
      for (var x = 0; x < W; x += step) {
         var r = img.sample(x, y, 0), g = img.sample(x, y, 1), b = img.sample(x, y, 2);
         var mx = Math.max(r, g, b), mn = Math.min(r, g, b);
         if (mx > thr) { sats.push(mx > 0 ? (mx - mn) / mx : 0); ++n; }
      }
   }
   sats.sort(function (a, b) { return a - b; });
   function pct(p) { return sats.length ? sats[Math.min(sats.length - 1, Math.floor(p * sats.length))] : 0; }
   var mean = 0; for (var i = 0; i < sats.length; ++i) mean += sats[i];
   mean = sats.length ? mean / sats.length : 0;
   return { starPixels: n, thr: Number(thr.toFixed(4)), satMean: Number(mean.toFixed(3)),
            satMedian: Number(pct(0.5).toFixed(3)), satP90: Number(pct(0.9).toFixed(3)) };
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

// 亮度分布探针:采样全图亮度 L=(R+G+B)/3(灰度图=单通道),排序出分位数阶梯。
// 用于量化拉伸力度 —— 各段有明确物理含义:
//   background(p20~p40)= 天空背景亮度;faint(p90~p97)= 淡云/外围星云;core(p999/max)= 亮核。
// 目标(非线性成片经验值,0..1):bg≈0.08~0.12、faint≈0.45~0.55、core≤0.85~0.90(不死白)。
function computeProbe(img, params) {
   try { img.resetSelections(); } catch (e) {}
   var W = img.width, H = img.height, nc = img.numberOfChannels;
   var target = (params && params.samples) ? params.samples : 200000;
   var step = Math.max(1, Math.round(Math.sqrt(W * H / target)));
   var L = [], Lraw = [], Rr = [], Gg = [], Bb = [];
   for (var y = 0; y < H; y += step) {
      for (var x = 0; x < W; x += step) {
         var v;
         if (nc >= 3) {
            var rr = img.sample(x, y, 0), gg = img.sample(x, y, 1), bb = img.sample(x, y, 2);
            v = (rr + gg + bb) / 3;
            Rr.push(rr); Gg.push(gg); Bb.push(bb);
         } else v = img.sample(x, y, 0);
         L.push(v); Lraw.push(v);
      }
   }
   L.sort(function (a, b) { return a - b; });
   var N = L.length;
   function pct(p) { return N ? L[Math.min(N - 1, Math.max(0, Math.floor(p * N)))] : 0; }
   function band(lo, hi) {  // 均值 of [lo,hi] 分位区间
      var a = Math.floor(lo * N), b = Math.floor(hi * N), s = 0, c = 0;
      for (var i = a; i < b && i < N; ++i) { s += L[i]; ++c; }
      return c ? s / c : 0;
   }
   function r4(v) { return Number(v.toFixed(4)); }
   var ladder = { p1: r4(pct(0.01)), p5: r4(pct(0.05)), p10: r4(pct(0.10)),
                  p25: r4(pct(0.25)), p50: r4(pct(0.50)), p75: r4(pct(0.75)),
                  p90: r4(pct(0.90)), p95: r4(pct(0.95)), p97: r4(pct(0.97)),
                  p99: r4(pct(0.99)), p995: r4(pct(0.995)), p999: r4(pct(0.999)),
                  max: r4(N ? L[N - 1] : 0) };
   // 三段锚点(区间均值,比单点稳)
   var anchors = { background: r4(band(0.20, 0.40)),
                   faint:      r4(band(0.90, 0.97)),
                   core:       r4(band(0.999, 1.0)) };
   // 核心内部对比度:取最亮 top 段(默认亮度 >= p97)像素,报其内部亮度分布的展宽。
   // spread(=内部 p90-p10)越大=核心越有立体感;越小=越"平"。用于量化核心对比度。
   var coreThr = pct(0.97);
   var cv = [];
   for (var i = 0; i < N; ++i) if (L[i] >= coreThr) cv.push(L[i]);
   var coreContrast = null;
   if (cv.length > 20) {
      var M = cv.length;
      function cpct(p) { return cv[Math.min(M - 1, Math.max(0, Math.floor(p * M)))]; }
      var cmean = 0; for (var j = 0; j < M; ++j) cmean += cv[j]; cmean /= M;
      var cvar = 0; for (var k = 0; k < M; ++k) cvar += (cv[k] - cmean) * (cv[k] - cmean);
      coreContrast = { thr: r4(coreThr), pixels: M,
                       p10: r4(cpct(0.10)), p50: r4(cpct(0.50)), p90: r4(cpct(0.90)),
                       spread: r4(cpct(0.90) - cpct(0.10)),   // 内部展宽:越大越立体
                       std: r4(Math.sqrt(cvar / M)) };
   }
   // 核心/星云主体色彩平衡:对亮度 >= faint 段阈值(默认 p90)的星云像素,报均值 R/G/B
   // 及红占比 redFrac=R/(R+G+B)。量化"红味够不够":中性白≈0.333;偏红>0.36;发射星云通常 0.38~0.45。
   var color = null;
   if (nc >= 3) {
      var cthr = pct(0.90);
      var sr = 0, sg = 0, sb = 0, cc2 = 0;
      for (var m = 0; m < Lraw.length; ++m) {
         if (Lraw[m] >= cthr) { sr += Rr[m]; sg += Gg[m]; sb += Bb[m]; ++cc2; }
      }
      if (cc2 > 0) {
         var mr = sr / cc2, mg = sg / cc2, mb = sb / cc2, tot = mr + mg + mb;
         color = { thr: r4(cthr), pixels: cc2, R: r4(mr), G: r4(mg), B: r4(mb),
                   redFrac: r4(tot > 0 ? mr / tot : 0),
                   greenFrac: r4(tot > 0 ? mg / tot : 0),
                   blueFrac: r4(tot > 0 ? mb / tot : 0) };
      }
   }
   return { samples: N, step: step, ladder: ladder, anchors: anchors,
            coreContrast: coreContrast, color: color };
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

// HT 拉伸:复用 computeStretchH 的 STF 自适应数学(m=mtf(targetBG, med-c0)),真拉伸。
// targetBG=拉伸目标背景(小=温和);shadowClip=黑场(越接近0背景越暗;比 STF 默认 -2.8 更狠)。
function applyHTStretch(view, params) {
   if (typeof HistogramTransformation == "undefined")
      throw new Error("HistogramTransformation 不可用");
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   // 模式一:指定 midtones(曲线形状,与刻度无关,可照搬 PI 面板值)。
   // shadow(黑场)是绝对值、依赖本图刻度,不能照搬 → 未给时按本图 median 自适应算。
   if (params && params.midtones != null) {
      var shadow;
      if (params.shadow != null) {
         shadow = params.shadow;
      } else {
         var med = img.median();
         var mad = img.MAD() * 1.4826;
         var sc = (params.shadowClip != null) ? params.shadowClip : -1.2;
         shadow = (mad > 0) ? Math.max(0, med + sc * mad) : Math.max(0, med * 0.5);
      }
      var comb = [shadow, params.midtones, 1.0, 0, 1];
      var Hf = [[0,0.5,1,0,1],[0,0.5,1,0,1],[0,0.5,1,0,1], comb, [0,0.5,1,0,1]];
      applyHMatrix(view, Hf);
      return { mode: "fixed", shadow: Number(shadow.toFixed(6)), midtones: params.midtones };
   }
   // 模式二:自适应 targetBG(仅用于线性图的首次拉伸)
   var targetBG   = (params && params.targetBG   != null) ? params.targetBG   : 0.15;
   var shadowClip = (params && params.shadowClip != null) ? params.shadowClip : -1.5;
   var H = computeStretchH(img, targetBG, shadowClip, true);
   applyHMatrix(view, H);
   return { mode: "adaptive", targetBG: targetBG, shadowClip: shadowClip };
}

// HDR 压缩:HDRMultiscaleTransform,压缩大尺度亮结构的动态范围,救回过曝亮核细节
// (M42 等亮核+暗弱外围的高动态目标必备)。作用于已拉伸(非线性)图。
function applyHDR(view, params) {
   if (typeof HDRMultiscaleTransform == "undefined")
      throw new Error("HDRMultiscaleTransform 不可用");
   var P = new HDRMultiscaleTransform;
   var info = { set: [] };
   try {
      info.props = Object.getOwnPropertyNames(P).filter(function (k) {
         return k.charAt(0) !== "_" && typeof P[k] !== "function";
      });
   } catch (e) {}
   function hset(n, v) { try { if (typeof P[n] != "undefined") { P[n] = v; info.set.push(n + "=" + v); } } catch (e) {} }
   hset("numberOfLayers", (params && params.layers != null) ? params.layers : 6);
   hset("medianTransform", true);
   hset("toLightness", (params && params.toLightness != null) ? params.toLightness : true);
   hset("preserveHue", (params && params.preserveHue != null) ? params.preserveHue : false);
   if (params && params.overdrive != null) hset("overdrive", params.overdrive);
   if (params && params.iterations != null) hset("numberOfIterations", params.iterations);
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
   // 1. 拉伸副本(GHS 或 HT)。HT 模式黑场压背景,只抬中间调 → 背景保持全黑不放大噪声。
   var sw = clone("ms_stretch");
   if (params && params.stretchType == "ht") {
      // 非线性增量 HT:固定 midtones(曲线形状) + **自适应黑场**(每步压住当前背景,防翻噪)
      applyHTStretch(sw.mainView, { midtones: (params.midtones != null) ? params.midtones : 0.25,
                                    shadowClip: (params.shadowClip != null) ? params.shadowClip : -1.2 });
   } else {
      applyGHS(sw.mainView, { D: D, HP: (params && params.HP != null) ? params.HP : 0.9 });
   }
   var sid = sw.mainView.id;
   // 2. 保护蒙版。core=硬阈值(旧);lum=**连续亮度蒙版**(自身亮度→保护量,平滑无断层)
   var maskMode = (params && params.maskMode) ? params.maskMode : "core";
   var strength = (params && params.strength != null) ? params.strength : 1.5;
   var mw = clone("ms_mask");
   var Pm = new PixelMath;
   Pm.useSingleExpression = true;
   if (maskMode == "lum") {
      var lum = isColor ? "(($T[0]+$T[1]+$T[2])/3)" : "$T";
      // 核心保护:两种形状——
      //  min 形(默认,旧):min(1,strength*lum),在 lum=1/strength 处有拐点(等亮度线→可能分层);
      //  smooth 形(smooth:true):1-exp(-strength*lum),处处光滑无拐点、渐近到 1,消除等亮度分层。
      var coreM;
      if (params && params.smooth)
         coreM = "(1-exp(-" + strength + "*" + lum + "))";
      else
         coreM = "min(1," + strength + "*" + lum + ")";
      if (params && params.bgProtect) {
         // 背景保护:亮度低于 bgLevel 时→高(保护暗背景不被拉伸放大噪声)
         var bgL = (params && params.bgLevel != null) ? params.bgLevel : (med * 2.5);
         var bgM = "max(0,1-" + lum + "/" + bgL + ")";
         // 合成:核心 或 背景 都保护,只拉伸中间调(外围星云)→ 背景不被放大
         Pm.expression = "max(" + coreM + "," + bgM + ")";
      } else {
         Pm.expression = coreM;
      }
   } else if (maskMode == "range") {
      // RangeSelection 式亮度范围蒙版:选亮度 >= lowerLimit 的核心区(=1 保护),
      // 下方羽化过渡,smoothness(=feather 高斯)提供平滑。复刻用户手法(截图3/5)。
      var lumr = isColor ? "(($T[0]+$T[1]+$T[2])/3)" : "$T";
      var lower = (params && params.lowerLimit != null) ? params.lowerLimit : 0.31;
      Pm.expression = "iif(" + lumr + ">=" + lower + ",1,0)";
   } else {
      Pm.expression = "iif($T>" + coreThr + ",1,0)";
   }
   Pm.createNewImage = false; Pm.rescale = false; Pm.truncate = true;
   Pm.executeOn(mw.mainView);
   var C = new Convolution;
   try { C.mode = 0; C.sigma = feather; C.shape = 2.0; } catch (e) {}
   C.executeOn(mw.mainView);
   // 2b. 蒙版对比拉伸:绕 0.5 加对比,核心(高)更接近1、外围(低)更接近0 → 核心抑制更强、外围拉更多
   var mc = (params && params.maskContrast != null) ? params.maskContrast : 1.0;
   if (mc != 1.0) {
      var Pc = new PixelMath;
      Pc.useSingleExpression = true;
      Pc.expression = "max(0,min(1,0.5+($T-0.5)*" + mc + "))";
      Pc.createNewImage = false; Pc.rescale = false; Pc.truncate = true;
      Pc.executeOn(mw.mainView);
   }
   var mid = mw.mainView.id;
   // 3. 混合:蒙版(核心)保留原样,其余用拉伸版
   var Pb = new PixelMath;
   Pb.useSingleExpression = true;
   Pb.expression = mid + "*$T + (1-" + mid + ")*" + sid;
   Pb.createNewImage = false; Pb.rescale = false; Pb.truncate = true;
   Pb.executeOn(view);
   try { sw.forceClose(); } catch (e) {}
   try { mw.forceClose(); } catch (e) {}
   return { D: D, maskMode: maskMode, strength: strength, feather: feather, maskContrast: mc };
}

// HDR 核心融合:以正常拉伸(view,外围舒服/核心过曝)为底,只在亮核区用 HDR 图替换。
// 避免 HDRMultiscaleTransform 全局做在亮星云周围压出暗环。params.hdr=HDR 图路径。
function applyHdrBlend(view, params) {
   var hp = params && params.hdr;
   if (!hp || !File.exists(hp)) throw new Error("hdrblend 需要 params.hdr: " + hp);
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   var med = img.median();
   var coreThr = (params && params.coreThr != null) ? params.coreThr : Math.min(0.85, med * 2 + 0.35);
   var feather = (params && params.feather != null) ? params.feather : 25;
   var hw = ImageWindow.open(hp)[0];
   try {
      var hid = hw.mainView.id;
      var nCh = img.numberOfChannels, isColor = nCh >= 3;
      // 核心蒙版:view 亮处=1(用 HDR),羽化
      var mw = new ImageWindow(img.width, img.height, nCh, 32, true, isColor, "hdr_mask");
      mw.mainView.beginProcess(UndoFlag_NoSwapFile);
      mw.mainView.image.assign(img); mw.mainView.endProcess();
      var Pm = new PixelMath;
      Pm.useSingleExpression = true;
      Pm.expression = "iif($T>" + coreThr + ",1,0)";
      Pm.createNewImage = false; Pm.rescale = false; Pm.truncate = true;
      Pm.executeOn(mw.mainView);
      var C = new Convolution;
      try { C.mode = 0; C.sigma = feather; C.shape = 2.0; } catch (e) {}
      C.executeOn(mw.mainView);
      var mid = mw.mainView.id;
      // 混合:核心用 HDR,其余用底图
      var Pb = new PixelMath;
      Pb.useSingleExpression = true;
      Pb.expression = "(1-" + mid + ")*$T + " + mid + "*" + hid;
      Pb.createNewImage = false; Pb.rescale = false; Pb.truncate = true;
      Pb.executeOn(view);
      try { mw.forceClose(); } catch (e) {}
      return { coreThr: Number(coreThr.toFixed(4)), feather: feather };
   } finally { try { hw.forceClose(); } catch (e) {} }
}

// 核心局部对比度:LocalHistogramEqualization 只做在核心区(range 蒙版羽化),
// 恢复被全局压缩压平的亮核内部结构(旋涡/尘带/明暗团),不动外围与背景。
// 全局曲线无法兼顾"控亮度+留对比";LHE 是空间局部处理,专治"核心发平"。
// params: lowerLimit(核心蒙版下限,默认0.35)、feather(羽化sigma,默认28)、
//         radius(LHE 核半径 px,默认110,越大越大尺度)、slopeLimit(对比上限,默认1.5)、
//         amount(0..1 强度,默认0.5)、bins(0=8/1=10/2=12bit,默认1)。
function applyLHE(view, params) {
   if (typeof LocalHistogramEqualization == "undefined")
      throw new Error("LocalHistogramEqualization 不可用");
   var img = view.image;
   try { img.resetSelections(); } catch (e) {}
   var nCh = img.numberOfChannels, isColor = nCh >= 3;
   var lower   = (params && params.lowerLimit != null) ? params.lowerLimit : 0.35;
   var feather = (params && params.feather != null) ? params.feather : 28;
   var radius  = (params && params.radius != null) ? params.radius : 110;
   var slope   = (params && params.slopeLimit != null) ? params.slopeLimit : 1.5;
   var amount  = (params && params.amount != null) ? params.amount : 0.5;
   var bins    = (params && params.bins != null) ? params.bins : 1;
   function clone(name) {
      var w = new ImageWindow(img.width, img.height, nCh, 32, true, isColor, name);
      w.mainView.beginProcess(UndoFlag_NoSwapFile);
      w.mainView.image.assign(img);
      w.mainView.endProcess();
      return w;
   }
   // 1. LHE 副本
   var lw = clone("lhe_tmp");
   var P = new LocalHistogramEqualization;
   var set = [];
   function sp(n, v) { try { if (typeof P[n] != "undefined") { P[n] = v; set.push(n); } } catch (e) {} }
   sp("radius", radius);
   sp("histogramBins", bins);
   sp("slopeLimit", slope);
   sp("amount", amount);
   try { sp("circularKernel", true); } catch (e) {}
   P.executeOn(lw.mainView);
   var lid = lw.mainView.id;
   // 2. 核心蒙版(range,羽化)
   var mw = clone("lhe_mask");
   var lumr = isColor ? "(($T[0]+$T[1]+$T[2])/3)" : "$T";
   var Pm = new PixelMath;
   Pm.useSingleExpression = true;
   Pm.expression = "iif(" + lumr + ">=" + lower + ",1,0)";
   Pm.createNewImage = false; Pm.rescale = false; Pm.truncate = true;
   Pm.executeOn(mw.mainView);
   var C = new Convolution;
   try { C.mode = 0; C.sigma = feather; C.shape = 2.0; } catch (e) {}
   C.executeOn(mw.mainView);
   var mid = mw.mainView.id;
   // 3. 混合:核心用 LHE 版,其余保持原图
   var Pb = new PixelMath;
   Pb.useSingleExpression = true;
   Pb.expression = mid + "*" + lid + " + (1-" + mid + ")*$T";
   Pb.createNewImage = false; Pb.rescale = false; Pb.truncate = true;
   Pb.executeOn(view);
   try { lw.forceClose(); } catch (e) {}
   try { mw.forceClose(); } catch (e) {}
   return { lowerLimit: lower, feather: feather, radius: radius,
            slopeLimit: slope, amount: amount, set: set };
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
// 动态 HOO 调色板(用户提供的 PixelMath 配方,Bill Blanshan 式):
//   R = hGain*H
//   G = m*H + ~m*O,   m = (O*H)^~(O*H)        —— 按 O·H 乘积动态在 H/O 间取舍
//   B = ~((~O)*(~(~H*O)))                      —— O 与"H 暗处的 O"做 screen
// (~x = 1-x,^ = 幂)。效果:Hα 呈**橙红**、OIII 呈蓝青,过渡自然。
// **S 通道增强(解决"加黄污染全局")**:用**相对 S 蒙版**门控——只在 S 真正强于 H 的地方加黄:
//   sm = clip((S-H)/(S+H+eps), 0, 1) ^ sMaskPow ;  R += sYellow*sm*S ; G += 0.8*sYellow*sm*S
// 输入 h/o/s 为**已各自拉伸并背景对齐**的单通道路径(线性域用此公式会失真)。
function applyDynHoo(params) {
   function op(p, need) {
      if (!p || !File.exists(p)) {
         if (need) throw new Error("dynhoo 缺通道: " + p);
         return null;
      }
      var a = ImageWindow.open(p);
      if (!a || a.length == 0) { if (need) throw new Error("打开失败: " + p); return null; }
      return a[0];
   }
   var hw = op(params.h, true), ow = op(params.o, true), sw = op(params.s, false);
   try {
      var H = hw.mainView.id, O = ow.mainView.id, S = sw ? sw.mainView.id : null;
      var hG = (params.hGain != null) ? params.hGain : 0.8;
      var sY = (params.sYellow != null) ? params.sYellow : 0.0;
      var sP = (params.sMaskPow != null) ? params.sMaskPow : 2.0;
      var W = hw.mainView.image.width, Ht = hw.mainView.image.height;
      var out = null;
      // 【坑】此 PI 的 PixelMath **不支持 pow() 函数**(用了就静默失败、不建图);
      // 幂用原生 **^** 运算符,反相用 **~**(用户给的公式原文就是这两个,别自己翻成 pow)。
      var OH = "(" + O + "*" + H + ")";
      var m  = "(" + OH + "^~" + OH + ")";                        // (O*H)^~(O*H)
      var rE = hG + "*" + H;
      var gE = m + "*" + H + "+~" + m + "*" + O;                  // m*H + ~m*O
      var bE = "~((~" + O + ")*(~(~" + H + "*" + O + ")))";       // ~((~O)*(~(~H*O)))
      if (S && sY > 0) {                                          // 相对 S 蒙版:只在 S 强于 H 处加黄
         var sm = "((max(0,min(1,(" + S + "-" + H + ")/(" + S + "+" + H + "+1e-4))))^" + sP + ")";
         rE = "(" + rE + ")+" + sY + "*" + sm + "*" + S;
         gE = "(" + gE + ")+" + (0.8 * sY) + "*" + sm + "*" + S;
      }
      // 【坑1】空白新窗口上执行 PixelMath 引用外部 id → 全 0;
      // 【坑2】createNewImage 出来的是**灰度**图(newImageColorSpace 在此上下文不生效)。
      // 正解:三个表达式各生成一张灰度图,再用 ChannelCombination 合成 RGB。
      function mk(expr, id) {
         var od = ImageWindow.windowById(id);
         if (od && !od.isNull) { try { od.forceClose(); } catch (e) {} }
         var Pm = new PixelMath;
         Pm.expression = expr; Pm.useSingleExpression = true;
         Pm.createNewImage = true; Pm.newImageId = id;
         Pm.rescale = false; Pm.truncate = true;
         Pm.executeOn(hw.mainView, false);
         var w2 = ImageWindow.windowById(id);
         if (!w2 || w2.isNull) throw new Error("dynhoo 分量生成失败: " + id + " expr=" + expr);
         return w2;
      }
      var sfx = "_" + Math.floor(Date.now() % 100000);
      var wr = mk(rE, "dh_r" + sfx), wg = mk(gE, "dh_g" + sfx), wb = mk(bE, "dh_b" + sfx);
      var W2 = hw.mainView.image.width, H2 = hw.mainView.image.height;
      out = new ImageWindow(W2, H2, 3, 32, true, true, "dynhoo" + sfx);
      var CC = new ChannelCombination;
      CC.colorSpace = 0;   // RGB
      CC.channels = [[true, wr.mainView.id], [true, wg.mainView.id], [true, wb.mainView.id]];
      out.mainView.beginProcess(UndoFlag_NoSwapFile);
      CC.executeOn(out.mainView);
      out.mainView.endProcess();
      try { wr.forceClose(); wg.forceClose(); wb.forceClose(); } catch (e) {}
      try { if (hw.keywords) out.keywords = hw.keywords; } catch (e) {}
      try { log("dynhoo out median=" + out.mainView.image.median() + " ch=" + out.mainView.image.numberOfChannels); } catch (e) {}
      log("dynhoo: hGain=" + hG + " sYellow=" + sY + " sMaskPow=" + sP + (S ? " (S 相对蒙版)" : ""));
      return out;
   } finally {
      try { hw.forceClose(); } catch (e) {}
      try { ow.forceClose(); } catch (e) {}
      if (sw) { try { sw.forceClose(); } catch (e) {} }
   }
}

// 宽窄带混合(业界标准做法:逐通道按波长注入,不是两张彩图整体 blend)。
// view = 线性 RGB 彩色底图;把窄带按波长注入对应通道:
//   Hα(656nm)+SII(672nm) → R;OIII(500nm) → G 和 B(波长介于绿蓝之间)。
// 注入前对每个窄带做 **LinearFit**(以对应宽带通道为参考)统一量级,否则窄带压倒宽带。
// 公式用"像素替换+乘数"(最灵活,业界常用):
//   R = iif(NB > R, R + k*(NB - med(NB)), R)   —— 减窄带自身天光中位再按 k 倍注入,
//   只在窄带更亮处生效(发射区),连续谱区域保持宽带原样 → 自然色底 + 窄带发射结构。
// params: ha / oiii / sii(单通道 master 路径,线性)、kHa / kOiii / kSii(强度,默认 1.0/0.8/0.5)、
//         fit(默认 true:先 LinearFit 到对应宽带通道)。
function applyNBInject(view, params) {
   var img = view.image;
   if (img.numberOfChannels < 3) throw new Error("nbinject 需要彩色底图(线性 RGB)");
   var kHa = (params.kHa != null) ? params.kHa : 1.0;
   var kO  = (params.kOiii != null) ? params.kOiii : 0.8;
   var kS  = (params.kSii != null) ? params.kSii : 0.5;
   var doFit = (params.fit != null) ? params.fit : true;
   var opened = [], info = { fit: doFit, kHa: kHa, kOiii: kO, kSii: kS, injected: [] };

   // 把底图的某个通道抽成独立灰度图,作为 LinearFit 的参考(PixelMath 建新图,单通道)
   function chanRef(idx, name) {
      var old = ImageWindow.windowById(name);
      if (old && !old.isNull) { try { old.forceClose(); } catch (e) {} }
      var P = new PixelMath;
      P.expression = "$T[" + idx + "]";
      P.useSingleExpression = true;
      P.createNewImage = true; P.newImageId = name;
      P.newImageColorSpace = 1;            // 1 = Gray(单通道)
      P.rescale = false; P.truncate = true;
      try { P.executeOn(view, false); }
      catch (e) {                          // 某些版本 newImageColorSpace 常量不同 → 退化为默认
         var P2 = new PixelMath;
         P2.expression = "$T[" + idx + "]";
         P2.useSingleExpression = true; P2.createNewImage = true; P2.newImageId = name;
         P2.rescale = false; P2.truncate = true;
         P2.executeOn(view, false);
      }
      var w = ImageWindow.windowById(name);
      if (w && !w.isNull) opened.push(w);
      return w;
   }

   function prep(path, refIdx, tagName) {
      if (!path || !File.exists(path)) return null;
      var a = ImageWindow.open(path);
      if (!a || a.length == 0) return null;
      var w = a[0]; opened.push(w);
      if (doFit) {
         var ref = chanRef(refIdx, tagName + "_ref");
         try {
            var LF = new LinearFit;
            LF.referenceViewId = ref.mainView.id;
            LF.executeOn(w.mainView, false);
            info.injected.push(tagName + ":fit");
         } catch (e) {
            info.injected.push(tagName + ":fitFail(" + e + ")");
         }
      }
      return w.mainView.id;
   }

   var ha = prep(params.ha, 0, "ha");
   var o3 = prep(params.oiii, 1, "o3");     // 以 G 为参考拟合(再同样注入 B)
   var s2 = prep(params.sii, 0, "s2");

   function inj(chExpr, nbId, k) {
      if (!nbId || k <= 0) return chExpr;
      return "iif(" + nbId + " > " + chExpr + ", " + chExpr + " + " + k +
             "*(" + nbId + " - med(" + nbId + ")), " + chExpr + ")";
   }
   var rExpr = "$T[0]", gExpr = "$T[1]", bExpr = "$T[2]";
   rExpr = inj(rExpr, ha, kHa);
   rExpr = inj(rExpr, s2, kS);              // SII 也进 R
   gExpr = inj(gExpr, o3, kO);
   bExpr = inj(bExpr, o3, kO);              // OIII 进 G 和 B

   var PM = new PixelMath;
   PM.useSingleExpression = false;
   PM.expression = rExpr; PM.expression1 = gExpr; PM.expression2 = bExpr;
   PM.createNewImage = false; PM.rescale = false; PM.truncate = true;
   PM.executeOn(view);
   for (var i = 0; i < opened.length; ++i) { try { opened[i].forceClose(); } catch (e) {} }
   log("nbinject: Ha/SII→R, OIII→G+B  k=" + kHa + "/" + kO + "/" + kS + " fit=" + doFit);
   return info;
}

// 两张彩色图融合(RGB ⊕ SHO 用):view=底图,params.top=叠加图路径,params.mode=模式,
// params.amount=强度 0..1(0=纯底图,1=纯模式结果),params.lum(可选)=用哪张的亮度。
//   "screen"   : 1-(1-a)(1-b)   两者的发光都保留(不会变暗),适合叠加窄带发射
//   "lighten"  : max(a,b)       各处取更亮者,保各自最强特征
//   "average"  : (a+b)/2        均衡混色
//   "weighted" : (1-w)a + w·b   按 amount 线性混合
//   "colorlum" : 取底图色比 × 叠加图亮度(保 RGB 色相、用 SHO 亮度结构)
//   "lumcolor" : 取叠加图色比 × 底图亮度(保 SHO 色相、用 RGB 亮度)
// 融合前两图应已各自拉伸到相近背景电平(否则一方压倒另一方)。
function applyImgBlend(view, params) {
   var tp = params && params.top;
   if (!tp || !File.exists(tp)) throw new Error("imgblend 需要 params.top: " + tp);
   var mode = (params && params.mode) ? params.mode : "screen";
   var amt = (params && params.amount != null) ? params.amount : 0.5;
   var tw = ImageWindow.open(tp)[0];
   try {
      var b = tw.mainView.id;                        // 叠加图(top)
      var P = new PixelMath;
      P.useSingleExpression = true;
      var expr;
      if (mode == "screen")        expr = "1-(1-$T)*(1-" + b + ")";
      else if (mode == "lighten")  expr = "max($T," + b + ")";
      else if (mode == "average")  expr = "($T+" + b + ")/2";
      else if (mode == "weighted") expr = "(1-" + amt + ")*$T+" + amt + "*" + b;
      else if (mode == "colorlum") {   // 底图色相 × 叠加图亮度
         var lb = "((" + b + "[0]+" + b + "[1]+" + b + "[2])/3)";
         expr = "$T * " + lb + " / max(1e-5,(($T[0]+$T[1]+$T[2])/3))";
      } else if (mode == "lumcolor") { // 叠加图色相 × 底图亮度
         var lt = "(($T[0]+$T[1]+$T[2])/3)";
         expr = b + " * " + lt + " / max(1e-5,((" + b + "[0]+" + b + "[1]+" + b + "[2])/3))";
      } else if (mode == "keepneutral") {
         // **保留底图(RGB)里近白/灰的云气,其余交给叠加图(窄带)**:
         // 中性度 n = 1 - 饱和度 = 1 - (max-min)/max(白/灰→1、彩色→0),再乘亮度门控
         // (背景不参与,免得暗处也用 RGB),幂次 keepPow 控制过渡陡缓。
         var mx = "max(max($T[0],$T[1]),$T[2])", mn = "min(min($T[0],$T[1]),$T[2])";
         var neu = "(1-(" + mx + "-" + mn + ")/max(1e-4," + mx + "))";
         var lo = (params.keepLow != null) ? params.keepLow : 0.12;   // 亮度下限(背景不算云气)
         var pw = (params.keepPow != null) ? params.keepPow : 2.0;
         var lum = "(($T[0]+$T[1]+$T[2])/3)";
         var bright = "max(0,min(1,(" + lum + "-" + lo + ")/0.25))";
         var k = "((" + neu + "*" + bright + ")^" + pw + ")";         // k=1 → 保 RGB;k=0 → 用窄带(^ 非 pow)
         expr = k + "*$T + (1-" + k + ")*" + b;
      } else throw new Error("未知 imgblend mode: " + mode);
      // 非 weighted 模式:再按 amount 与底图线性混合(amount=1 即纯模式结果)
      if (mode != "weighted" && amt < 0.999)
         expr = "(1-" + amt + ")*$T + " + amt + "*(" + expr + ")";
      P.expression = expr;
      P.createNewImage = false; P.rescale = false; P.truncate = true;
      P.executeOn(view);
      log("imgblend: mode=" + mode + " amount=" + amt);
      return { mode: mode, amount: amt, top: tp };
   } finally { try { tw.forceClose(); } catch (e) {} }
}

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

// Hα 红强调(OSC 自含,无需单独 Hα):只在星云亮区按亮度蒙版提红通道,背景不动。
// 用于把偏灰白的亮核/星云主体拉回浓郁鲑红(复刻 recipe 第 15 步的红强调)。
// 蒙版:亮度在 [lo, lo+width] 线性升到 1(lo 以下=背景=0,不泛红)。
// params: lo(蒙版下限,默认0.12)、width(升区宽,默认0.30)、amount(红乘性提亮,默认0.2)、
//         gReduce/bReduce(可选,在蒙版区轻压绿/蓝以增红,默认0)、
//         ciel(true=用 CIE L* 分量当蒙版,复刻 recipe 第15步;否则用平均亮度)。
function applyRedEmph(view, params) {
   var img = view.image;
   if (img.numberOfChannels < 3) throw new Error("redemph 需要彩色图");
   var lo     = (params && params.lo != null) ? params.lo : 0.12;
   var width  = (params && params.width != null) ? params.width : 0.30;
   var amount = (params && params.amount != null) ? params.amount : 0.2;
   var gRed   = (params && params.gReduce != null) ? params.gReduce : 0.0;
   var bRed   = (params && params.bReduce != null) ? params.bReduce : 0.0;
   // 蒙版量:CIE L*(第15步手法)或平均亮度
   var lum = (params && params.ciel) ? "CIEL($T)" : "(($T[0]+$T[1]+$T[2])/3)";
   var mask = "max(0,min(1,(" + lum + "-" + lo + ")/" + width + "))";
   var P = new PixelMath;
   P.useSingleExpression = false;
   P.expression  = "$T[0]*(1+" + amount + "*" + mask + ")";   // R:亮区按蒙版提亮
   P.expression1 = "$T[1]*(1-" + gRed + "*" + mask + ")";     // G:可选轻压
   P.expression2 = "$T[2]*(1-" + bRed + "*" + mask + ")";     // B:可选轻压
   P.createNewImage = false; P.rescale = false; P.truncate = true;
   P.executeOn(view);
   return { lo: lo, width: width, amount: amount, gReduce: gRed, bReduce: bRed };
}

// 色度蒙版局部去色(复刻用户手动"Cyan Color Mask + gconv×2 + CT"):
// 建一张与亮度无关的"绿/青过量"色度蒙版 → 高斯模糊(羽化)times 次 →
// 只在蒙版区去饱和(拉向亮度)+ 轻压暗,让局部偏色并入周围背景。
// 专治提亮/提饱和后某块背景泛青绿,而全局 SCNR/GC 会伤星云的情况(SKILL emission 阶段 E')。
function applyColorMask(view, params) {
   var img = view.image;
   if (img.numberOfChannels < 3) throw new Error("colormask 需要彩色图");
   var mode  = (params && params.mode) ? params.mode : "green";   // green / cyan
   var width = (params && params.width != null) ? params.width : 0.15;  // 色度斜坡宽(越小越挑纯绿)
   var sat   = (params && params.sat != null) ? params.sat : 0.8;       // 蒙版区去饱和强度 0~1
   var dim   = (params && params.dim != null) ? params.dim : 0.08;      // 蒙版区压暗强度 0~1
   var sigma = (params && params.blurSigma != null) ? params.blurSigma : 21; // 模糊 sigma
   var times = (params && params.blurTimes != null) ? params.blurTimes : 2;  // 模糊次数
   // 色度过量(与亮度无关):green=G 超出 R/B 均值;cyan=(G+B)/2 超出 R
   var chroma = (mode == "cyan") ? "((($T[1]+$T[2])/2)-$T[0])" : "($T[1]-($T[0]+$T[2])/2)";
   var maskId = "ttap_colormask";
   var mo = ImageWindow.windowById(maskId); if (mo && !mo.isNull) { try { mo.forceClose(); } catch (e) {} }
   var PM = new PixelMath;
   PM.expression = "max(0,min(1,(" + chroma + ")/" + width + "))";
   PM.useSingleExpression = true; PM.createNewImage = true; PM.newImageId = maskId;
   PM.rescale = false; PM.truncate = true;   // 默认与目标同色彩空间(RGB),三通道相同,作蒙版无碍
   PM.executeOn(view, false);
   var mw = ImageWindow.windowById(maskId);
   // 用 PixelMath 的 gconv 高斯卷积模糊蒙版 times 次(复刻用户手动 gconv($T,sigma,1,0)),
   // 避免 Convolution.mode 常量坑。
   var PB = new PixelMath;
   PB.expression = "gconv($T," + sigma + ",1,0)";
   PB.useSingleExpression = true; PB.createNewImage = false; PB.rescale = false; PB.truncate = true;
   for (var i = 0; i < times; ++i)
      PB.executeOn(mw.mainView, false);
   var lum = "(($T[0]+$T[1]+$T[2])/3)";
   function ex(c) { return "(" + lum + "+($T[" + c + "]-" + lum + ")*(1-" + sat + "*" + maskId + "))*(1-" + dim + "*" + maskId + ")"; }
   var P = new PixelMath;
   P.useSingleExpression = false;
   P.expression = ex(0); P.expression1 = ex(1); P.expression2 = ex(2);
   P.createNewImage = false; P.rescale = false; P.truncate = true;
   P.executeOn(view);
   try { mw.forceClose(); } catch (e) {}
   return { mode: mode, width: width, sat: sat, dim: dim, sigma: sigma, times: times };
}

// L 亮度蒙版提亮(用户手法):从自身亮度(或 CIE L*)建蒙版 mask=clip((lum-low)/(high-low)),
// 再对全通道做**纯乘性提亮** out=$T*(1+amount*mask)。**不含黑场下压** → 暗部 mask≈0 几乎不动、
// 不会把中心空腔越压越黑;亮区(星云)按 mask 提亮 → 自然。可多次少量调用逐步提亮。
function applyLMaskLift(view, params) {
   var img = view.image;
   if (img.numberOfChannels < 3) throw new Error("lmasklift 需要彩色图");
   var amount = (params && params.amount != null) ? params.amount : 0.7;
   var low    = (params && params.low != null) ? params.low : 0.05;   // 蒙版下限(≈背景,以下不提)
   var high   = (params && params.high != null) ? params.high : 0.30;  // 蒙版上限(≈星云亮区,以上满提)
   var span   = Math.max(1e-4, high - low);
   var lum = (params && params.ciel) ? "CIEL($T)" : "(($T[0]+$T[1]+$T[2])/3)";
   var mask = "max(0,min(1,(" + lum + "-" + low + ")/" + span + "))";
   var P = new PixelMath;
   P.useSingleExpression = false;
   P.expression  = "$T[0]*(1+" + amount + "*" + mask + ")";
   P.expression1 = "$T[1]*(1+" + amount + "*" + mask + ")";
   P.expression2 = "$T[2]*(1+" + amount + "*" + mask + ")";
   P.createNewImage = false; P.rescale = false; P.truncate = true;
   P.executeOn(view);
   return { amount: amount, low: low, high: high, ciel: !!(params && params.ciel) };
}

// 通道混合(3x3 矩阵):新 R/G/B = 矩阵 · 原 RGB。窄带调色板核心工具——
// SHO(R=SII,G=Ha,B=OIII)默认合成偏青绿;把 Ha(绿)按比例折进红→金橙,OIII 留作青蓝点缀,
// 即可从"青金"转"暖金红"(向 AstroBin 2/4/5 那类)。也可做用户可选配色预设。
// params.matrix = [[rr,rg,rb],[gr,gg,gb],[br,bg,bb]](缺省单位阵);或 params.preset:
//   "gold"(暖金红,Ha折入红+降绿) / "teal"(经典青金,近单位) / "sho"(单位阵)。
// params.protectStars 无关(应在 starless 上做)。truncate 到 [0,1]。
function applyChanMix(view, params) {
   var img = view.image;
   if (img.numberOfChannels < 3) throw new Error("chanmix 需要彩色图");
   var PRESETS = {
      // 暖金红:Ha(G)大幅折进红→金;绿保留少量(金=红+绿);OIII(B)略降、掺一点绿成青
      "gold": [[1.0, 0.85, 0.0], [0.0, 0.5, 0.12], [0.0, 0.0, 0.9]],
      "teal": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
      "sho":  [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
   };
   var M = (params && params.matrix) ? params.matrix
           : (PRESETS[(params && params.preset) || "sho"] || PRESETS["sho"]);
   function row(i) { return "(" + M[i][0] + "*$T[0]+" + M[i][1] + "*$T[1]+" + M[i][2] + "*$T[2])"; }
   var P = new PixelMath;
   P.useSingleExpression = false;
   P.expression  = row(0);
   P.expression1 = row(1);
   P.expression2 = row(2);
   P.createNewImage = false; P.rescale = false; P.truncate = true;
   P.executeOn(view);
   log("chanmix: preset=" + ((params && params.preset) || (params && params.matrix ? "custom" : "sho")));
   return { matrix: M, preset: (params && params.preset) || null };
}

// 背景中性化(数值法,不靠压暗):采样四角背景区逐通道中位 → 若 R/G/B 不相等=偏色 →
// 按差值做逐通道加性偏移,把背景拉到共同目标(三通道均值,保持平均亮度不压暗)。
// 返回实测背景 RGB + 偏移,便于核对"是否中性灰"。
function applyBgNeutral(view, params) {
   var img = view.image;
   if (img.numberOfChannels < 3) throw new Error("bgneutral 需要彩色图");
   var W = img.width, H = img.height;
   var fw = Math.max(1, Math.floor(W * ((params && params.frac != null) ? params.frac : 0.08)));
   var fh = Math.max(1, Math.floor(H * ((params && params.frac != null) ? params.frac : 0.08)));
   var rects = [ new Rect(0, 0, fw, fh), new Rect(W - fw, 0, W, fh),
                 new Rect(0, H - fh, fw, H), new Rect(W - fw, H - fh, W, H) ];
   function chBg(c) {
      var v = [];
      for (var i = 0; i < rects.length; ++i) {
         try { v.push(img.median(rects[i], c, c)); } catch (e) {}
      }
      v.sort(function (a, b) { return a - b; });
      // 取四角里较暗的两个的均值(避开某角含星云的偏高值)
      return v.length >= 2 ? (v[0] + v[1]) / 2 : (v[0] || 0);
   }
   var bR = chBg(0), bG = chBg(1), bB = chBg(2);
   var target = (params && params.target != null) ? params.target : (bR + bG + bB) / 3;
   var oR = bR - target, oG = bG - target, oB = bB - target;
   if (!(params && params.measureOnly)) {
      var P = new PixelMath;
      P.useSingleExpression = false;
      P.expression  = "$T[0]-(" + oR + ")";
      P.expression1 = "$T[1]-(" + oG + ")";
      P.expression2 = "$T[2]-(" + oB + ")";
      P.createNewImage = false; P.rescale = false; P.truncate = true;
      P.executeOn(view);
   }
   log("bgneutral: bgRGB=[" + bR.toFixed(5) + "," + bG.toFixed(5) + "," + bB.toFixed(5) +
       "] target=" + target.toFixed(5) + " off=[" + oR.toFixed(5) + "," + oG.toFixed(5) + "," + oB.toFixed(5) + "]");
   return { bgR: bR, bgG: bG, bgB: bB, target: target, offR: oR, offG: oG, offB: oB,
            measureOnly: !!(params && params.measureOnly) };
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

// 动态窄带调色板:按"OIII 主导度"分配颜色 —— OIII 强处→蓝(星云主体空腔),Ha/SII 强处→
// 金红(边缘壳)。解决线性 chanmix/直接合成在 OIII+Ha 混合区糊成紫褐、盖掉 OIII 蓝的问题;
// 复刻 AstroBin SHO"蓝体金边"观感(SH2-132 狮子星云主体就是蓝 OIII)。
// 权重 w=O/(O+H+eps)=OIII 主导度;nw=1-w=Ha 主导度。
//   R = sGain*S + hRed*H*nw   (SII 红 + Ha 在非OIII区→红)
//   G = gGain*H*nw            (Ha 在非OIII区→绿,配红成金)
//   B = oGain*O               (OIII→蓝)
// params: s,h,o=三单通道 master 路径(已拉伸对齐);sGain(默1.0)hRed(默0.9)gGain(默0.6)oGain(默1.0)。
function applyDynPalette(params) {
   function op(p) {
      if (!p || !File.exists(p)) throw new Error("dynpalette 缺通道: " + p);
      var a = ImageWindow.open(p);
      if (!a || a.length == 0) throw new Error("打开失败: " + p);
      return a[0];
   }
   var sw = op(params.s), hw = op(params.h), ow = op(params.o);
   try {
      var s = sw.mainView.id, h = hw.mainView.id, o = ow.mainView.id;
      var sG = (params.sGain != null) ? params.sGain : 1.0;
      var hR = (params.hRed  != null) ? params.hRed  : 0.9;
      var gG = (params.gGain != null) ? params.gGain : 0.6;
      var oG = (params.oGain != null) ? params.oGain : 1.0;
      var sh = (params.sharp != null) ? params.sharp : 2.0;   // 主导度锐化指数(越大蓝/金越干脆)
      var W = sw.mainView.image.width, H = sw.mainView.image.height;
      var out = new ImageWindow(W, H, 3, 32, true, true, "dynpal");
      // OIII 主导度 w=O^sh/(O^sh+H^sh);nw=1-w=Ha/SII 主导度。R、G 全按 nw 门控 →
      // OIII 主导处 R=G=0=纯蓝(星云主体空腔);SII/Ha 主导处才出金红(边缘壳)。
      // 同 dynhoo:PixelMath 不支持 pow(),用原生 ^(这正是 dynpalette 之前输出全黑的真因)
      var op_ = "(" + o + "^" + sh + ")", hp_ = "(" + h + "^" + sh + ")";
      var w  = "(" + op_ + "/(" + op_ + "+" + hp_ + "+1e-6))";
      var nw = "(1-" + w + ")";
      var P = new PixelMath;
      P.useSingleExpression = false;
      P.expression  = nw + "*(" + sG + "*" + s + "+" + hR + "*" + h + ")";
      P.expression1 = nw + "*" + gG + "*" + h;
      P.expression2 = oG + "*" + o;
      P.createNewImage = false; P.rescale = false; P.truncate = true;
      out.mainView.beginProcess(UndoFlag_NoSwapFile);
      P.executeOn(out.mainView);
      out.mainView.endProcess();
      try { if (sw.keywords) out.keywords = sw.keywords; } catch (e) {}
      log("dynpalette: B=OIII(蓝体), R/G=SII/Ha 在非OIII区(金边)");
      return out;
   } finally {
      try { sw.forceClose(); } catch (e) {}
      try { hw.forceClose(); } catch (e) {}
      try { ow.forceClose(); } catch (e) {}
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
   // 显式控制点模式:params.points = [[x,y],...](作用于 K/亮度通道),用于量化调色。
   // 会自动补 (0,0)/(1,1) 端点(若未给),并按 x 排序。points 优先于其它预设。
   if (params && params.points && params.points.length) {
      var pts = params.points.slice();
      var hasZero = false, hasOne = false;
      for (var pi = 0; pi < pts.length; ++pi) {
         if (pts[pi][0] <= 0.0001) hasZero = true;
         if (pts[pi][0] >= 0.9999) hasOne = true;
      }
      if (!hasZero) pts.push([0.0, 0.0]);
      if (!hasOne)  pts.push([1.0, 1.0]);
      pts.sort(function (a, b) { return a[0] - b[0]; });
      P.K = pts;
      did.points = pts;
      P.executeOn(view);
      return did;
   }
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
      else if (job.op == "probedeps") {
         // 依赖体检:typeof 探测各 PJSR 全局符号是否可用(PI 模块/自带进程/脚本)
         var names = (job.params && job.params.names) || [];
         var deps = {};
         for (var di = 0; di < names.length; ++di) {
            var nm = String(names[di]);
            var okd = false;
            try { okd = (eval("typeof " + nm) != "undefined"); } catch (e) { okd = false; }
            deps[nm] = okd;
         }
         res.deps = deps;
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
      else if (job.op == "starstats") {
         if (!job.input || !File.exists(job.input))
            throw new Error("input not found: " + job.input);
         var sw = ImageWindow.open(job.input)[0];
         try { res.starStats = computeStarStats(sw.mainView.image, job.params); }
         finally { try { sw.forceClose(); } catch (e) {} }
         return res;
      }
      else if (job.op == "lumprobe") {
         if (!job.input || !File.exists(job.input))
            throw new Error("input not found: " + job.input);
         var pw = ImageWindow.open(job.input)[0];
         try { res.probe = computeProbe(pw.mainView.image, job.params); }
         finally { try { pw.forceClose(); } catch (e) {} }
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
      else if (job.op == "residualset") {
         res.residual = applyResidualSet(job.params);
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
      else if (job.op == "dynhoo") {
         win = applyDynHoo(job.params);
         created = true;
         res.applied = { dynhoo: true };
      }
      else if (job.op == "dynpalette") {
         win = applyDynPalette(job.params);
         created = true;
         res.applied = { dynpalette: true };
      }
      else if (job.op == "inspect" || job.op == "crop" ||
               job.op == "gradient" || job.op == "deconv" ||
               job.op == "hoo" || job.op == "starsep" || job.op == "stretch" ||
               job.op == "denoise" || job.op == "scnr" || job.op == "recombine" ||
               job.op == "curves" || job.op == "colorcal" || job.op == "solve" ||
               job.op == "ghs" || job.op == "dustremove" || job.op == "lrgb" ||
               job.op == "delinetrail" || job.op == "maskline" ||
               job.op == "maskstretch" || job.op == "hablend" || job.op == "hdr" ||
               job.op == "hdrblend" || job.op == "htstretch" || job.op == "lhe" ||
               job.op == "redemph" || job.op == "polybg" || job.op == "softstretch" ||
               job.op == "colormask" || job.op == "bgneutral" || job.op == "lmasklift" ||
               job.op == "chanmix" || job.op == "imgblend" || job.op == "nbinject") {
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
      else if (job.op == "hdr") {
         res.applied = applyHDR(view, job.params);
      }
      else if (job.op == "hdrblend") {
         res.applied = applyHdrBlend(view, job.params);
      }
      else if (job.op == "htstretch") {
         res.applied = applyHTStretch(view, job.params);
      }
      else if (job.op == "lhe") {
         res.applied = applyLHE(view, job.params);
      }
      else if (job.op == "redemph") {
         res.applied = applyRedEmph(view, job.params);
      }
      else if (job.op == "colormask") {
         res.applied = applyColorMask(view, job.params);
      }
      else if (job.op == "bgneutral") {
         res.applied = applyBgNeutral(view, job.params);
      }
      else if (job.op == "lmasklift") {
         res.applied = applyLMaskLift(view, job.params);
      }
      else if (job.op == "chanmix") {
         res.applied = applyChanMix(view, job.params);
      }
      else if (job.op == "imgblend") {
         res.applied = applyImgBlend(view, job.params);
      }
      else if (job.op == "nbinject") {
         res.applied = applyNBInject(view, job.params);
      }
      else if (job.op == "polybg") {
         res.applied = applyPolyBg(view, job.params);
      }
      else if (job.op == "softstretch") {
         res.applied = applySoftStretch(view, job.params);
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
      var NONLINEAR_OPS = { stretch:1, scnr:1, denoise:1, recombine:1, curves:1, ghs:1,
                            maskstretch:1, hdrblend:1, htstretch:1, lhe:1, redemph:1, polybg:1,
                            softstretch:1 };
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
                            colorcal:1, solve:1, ghs:1,
                            maskstretch:1, hdrblend:1, htstretch:1, lhe:1, redemph:1, polybg:1,
                            softstretch:1 };
      var imageOut = outputs.image;
      if (!imageOut && TRANSFORM_OPS[job.op])
         imageOut = RUN_DIR + "/" + job.job_id + ".xisf";
      if (imageOut) {
         // 【易用性】保存前把**视图 ID 设成输出文件名**:否则各 op 建的新窗口都叫
         // "cropped"/"rgb" 之类,用户在 PI 里打开多个通道 master 时全同名、分不清
         // (用户 2026-08-04 反馈)。ID 只允许字母数字下划线、不能以数字开头。
         // View.id 是只读的 → 改名无效(实测仍写出 "cropped")。可靠做法:**新建一个以目标名
         // 命名的窗口、把像素拷进去,再保存它**(PixInsight 用窗口/视图 id 作为 XISF 里的图像名)。
         var renamedWin = null;
         try {
            var vbase = File.extractName(imageOut);
            var vid = String(vbase).replace(/[^A-Za-z0-9_]/g, "_");
            if (/^[0-9]/.test(vid)) vid = "_" + vid;
            if (vid.length > 0 && win.mainView.id != vid) {
               var oldw = ImageWindow.windowById(vid);
               if (oldw && !oldw.isNull) { try { oldw.forceClose(); } catch (e9) {} }
               var im0 = win.mainView.image;
               renamedWin = new ImageWindow(im0.width, im0.height, im0.numberOfChannels,
                                            im0.bitsPerSample, im0.isReal,
                                            im0.numberOfChannels >= 3, vid);
               renamedWin.mainView.beginProcess(UndoFlag_NoSwapFile);
               renamedWin.mainView.image.assign(im0);
               renamedWin.mainView.endProcess();
               try { if (win.keywords) renamedWin.keywords = win.keywords; } catch (e8) {}
               try { if (win.astrometricSolution) renamedWin.copyAstrometricSolution(win); } catch (e7) {}
            }
         } catch (e0) { renamedWin = null; }
         // JPG 导出可传质量(params.quality 0~100),经 saveAs 的 outputHints;其它格式无视
         var hints = "";
         if (/\.jpe?g$/i.test(imageOut) && job.params && job.params.quality != null)
            hints = "quality " + Math.max(0, Math.min(100, Math.round(job.params.quality)));
         if (renamedWin && !renamedWin.isNull) {
            renamedWin.saveAs(imageOut, false, false, false, false, hints);
            try { renamedWin.forceClose(); } catch (e6) {}
         } else {
            win.saveAs(imageOut, false, false, false, false, hints);
         }
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
