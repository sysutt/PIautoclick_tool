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

#include <pjsr/UndoFlag.jsh>   // 定义 UndoFlag_NoSwapFile 等常量

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
// 裁切 → 返回一个装着裁切结果的【全新窗口】(无天文解析,故不弹"删除解析"确认框)。
// 不使用 Crop 进程(几何变换会对已解析图弹模态框卡住脚本),改用 Image.cropTo 纯像素裁切。
// 返回 { win: 新窗口|null, applied: 边距 }。win 为 null 表示无需裁切。
function cropToNewWindow(srcView, params) {
   var img = srcView.image;
   var m;
   if (params && params.margins) {
      m = params.margins;
   } else {
      var thr = Math.max(1e-6, img.median() * 0.02);
      m = detectBorders(img, thr, 0.15);
   }
   if (!(m.left || m.top || m.right || m.bottom)) {
      log("crop: 无需裁切");
      return { win: null, applied: m };
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
   log("crop: L" + m.left + " T" + m.top + " R" + m.right + " B" + m.bottom +
       " → " + (x1 - x0) + "x" + (y1 - y0));
   return { win: out, applied: m };
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
      var deg = (params && params.polyDegree != null) ? params.polyDegree : null;
      if (deg != null) { try { P.polyDegree = deg; } catch (e) {} }
      P.executeOn(view);
      return "ABE(deg=" + (deg != null ? deg : "default") + ")";
   }
   throw new Error("gradient method not implemented: " + method);
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
   P.executeOn(view);
   return "NoiseXTerminator";
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
   try {
      var P = new PixelMath;
      P.useSingleExpression = true;
      // screen 混合:~((~starless)*(~stars))
      P.expression = "~((~$T) * (~" + starsViewId + "))";
      P.createNewImage = false;
      P.rescale = false;
      P.truncate = true;
      P.executeOn(view);
   } finally {
      try { starsWin.forceClose(); } catch (e) {}
   }
   return { stars: starsPath, mode: "screen", starsView: starsViewId };
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
      else if (job.op == "inspect" || job.op == "crop" ||
               job.op == "gradient" || job.op == "deconv" ||
               job.op == "hoo" || job.op == "starsep" || job.op == "stretch" ||
               job.op == "denoise" || job.op == "scnr" || job.op == "recombine" ||
               job.op == "curves" || job.op == "colorcal") {
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
      var NONLINEAR_OPS = { stretch:1, scnr:1, denoise:1, recombine:1, curves:1 };
      var isNonlinear = !!NONLINEAR_OPS[job.op];
      if (job.params && job.params.linear != null)
         isNonlinear = !job.params.linear;
      res.metrics = computeStats(view.image);
      res.preview_diag = exportPreview(view, previewPath, !isNonlinear);
      res.preview = previewPath;

      // ---- 保存输出(变换类 op 默认落盘,便于管线串接)----
      var TRANSFORM_OPS = { crop:1, gradient:1, deconv:1, hoo:1, starsep:1,
                            stretch:1, denoise:1, scnr:1, recombine:1, curves:1,
                            colorcal:1 };
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
