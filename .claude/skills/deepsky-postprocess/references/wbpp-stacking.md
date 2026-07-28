# 多晚叠加(WBPP)+ 整合去线/去带

后期的**前置步骤**:把多晚原始子帧叠成 master。本流程覆盖 ASIAIR OSC 多晚素材,验证于 IC1396(2600MC,三晚)。

## 用户的多晚习惯(规格)
- WBPP **只走到"星点对齐(registration)"** —— **不整合、不天文解析**(多晚先出对齐子帧)。
- **每晚打自定义滤镜标签**(GUI 的 **Add Custom / Filter name**,只打**亮场+平场**):d1rgb / d2rgb / d3rgb…
  用于**按晚匹配平场**(每晚平场只校当晚亮场);配准时所有 filter 一起对到**同一参考帧**(同 LRGB 共配准)。
- **暗场/偏置全项目共用**,不打标签;暗场曝光匹配亮场。
- **整合是独立步骤**(WBPP 之后):从 registered 取全部子帧 → 去线/去带 → 整合。
- 输出根 `M:/Deepsky`(config `stacking_output_base`),项目夹 `YYMMDD_CAM_TARGET`,多日 `begin-end_CAM_TARGET`。

## 两种多晚模式
- **全新从头多晚 → 自定义滤镜标签一次跑**(首选,下节)。
- **增量追加**(已对齐过的老素材 + 后拍新素材)→ 新素材直接拿**任意一张老 registered 单帧当 `referenceImage`** 对齐即可,不必重跑老素材。

## 自定义滤镜法的自动化实现(命令行无法直接打标签,须改副本)
命令行 `dir=`/`file=` 走无 filter 的 `addFile(path)`,复刻不了 Add Custom。系统脚本目录通常不可写(需管理员)→ **复制 `BatchPreprocessing` 到工作区 `wbpp_custom`,只改三处**:
1. **`BPP-Automation.js` 的 `parseFileParameters`**:支持 `dir=<路径>|<滤镜>` 语法 →
   `engine.addFile(path, ImageType.Unknown, filter, 0, 0)`(**Unknown 仍自动分光/平/暗/偏,filter 强制覆盖**;
   按最后一个 `|` 切路径与滤镜);且只扫 `*.fit/*.fits/*.xisf`(**排除 ASIAIR `_thn.jpg` 缩略图**)。
2. **`BPP-Solver.js`**:`#include "../ImageSolver/ImageSolver.js"` 换成**空壳 stub**
   (`function ImageSolver(){}` 等;platesolve=false 永不真调,ImageSolver 仅函数内引用、顶层无)。
3. **`WBPP.js`**:去掉 `#feature-*` 指令(-r= 不需 GUI 注册),**保留 `#engine v8`**。

**运行**(先杀 runner/PI、起 popup_guard):
```
PixInsight.exe -n "-r=<wbpp_custom>\WBPP.js,automationMode=true,\
  dir=<光1>|d1rgb,dir=<平1>|d1rgb,dir=<光2>|d2rgb,dir=<平2>|d2rgb,dir=<光3>|d3rgb,dir=<平3>|d3rgb,\
  dir=<暗>,dir=<偏>,outputDirectory=<OUT>,integrate=false,platesolve=false,debayerOutputMethod=0"
```
校验日志:平场按 d1/d2/d3rgb **分组各30**、暗偏 NoFilter 共用、光按晚、**registered 按 filter 分子目录但全对齐到同一参考帧**。

### 最大的坑(改副本时)
失败根因**不是 include**,而是改坏 WBPP.js:(a) `#feature-id` 是**多行续行指令**(行尾 `\`),只删首行会留下裸续行文本=语法错;(b) 插的标记里 `"\n"` 被写成**真换行**→ 字符串未闭合。**整树任一语法错 → `-r=` 脚本一句不跑、PI 只开 GUI**(不是弹框)。诊断:`BPPmain()` 前后写标记文件区分"解析错 vs include期抛错";**探针脚本必带 `#engine v8`**(BPP 用 ES 新语法),否则测试无效。

## 整合去线/去带(独立步骤,剔除法 > 手挖)
从 registered 汇总**全部**子帧,`ImageIntegration`:
- `combination=Average`、`normalization=AdditiveWithScaling`、`weightMode=NoiseEvaluation`;
- `rejection=WinsorizedSigmaClip`(**注意常量名不是 ...Clipping**)、`rejectionNormalization=Scale`、
  `sigmaLow=4.0, sigmaHigh=2.8, clipLow/clipHigh=true`;
- **大尺度高段剔除**:`largeScaleClipHigh=true, largeScaleClipHighProtectedLayers=2, largeScaleClipHighGrowth=2`
  (常量名不是 ...Layers);
- `generateRejectionMaps=true` → 看 `highRejectionMapImageId` **验证线/带被扫进剔除图、master 干净**。
- 常量名写错→setter 抛"unsigned integer value expected"、脚本早退、PI 空转(CPU 不涨)。标准 -r= 脚本无日志→ **try/catch 写 status.txt** 抓错。

**去线方法按线形态分流**(重要判断,实测定论):
- **宽而偏亮、逐帧漂移的色带**(电线投影,~20帧)→ **整合高段/大尺度高段 rejection** 扫掉(`trail_reject=True`):带逐帧漂移=瞬时结构、几十帧覆盖每像素 → 被当高段离群彻底扫进剔除图。**不要手挖**(直线成不了带、残差幅度蒙版与天光梯度纠缠都失败)。
- **细淡卫星/飞机线**(单帧每像素 <~2σ,如 NGC7000)→ **统计 rejection 无论多激进都除不掉**(sigmaHigh 2.8/2.0 三版对比线几乎无差别),大尺度高段只针对宽结构 → **必须走残差检测 + 整帧剔除**(见下 `run_detrail`)。
- **maskline 手挖已弃用于自动化**:残差霍夫在 zoom-8 缩略图上定位有 ±几十像素误差,挖偏(红线与真 streak 平行偏移),master 仍残留。整帧剔除不依赖定位,轨迹必净。

## 全自动去线:残差检测 + 整帧剔除(`run_detrail`,首选)
整合前对 registered 全部子帧:
1. **`residualset` op** 中位叠加出参考 → 每帧 PixelMath 残差 `max($T−ref,0)`(静态星云/星点抵消,只剩逐帧瞬时线;表达式按通道数自适应:黑白 `$T[0]`、RGB 三通道均值)→ autostretch + IntegerResample 存 zoom-8 残差缩略图 `res_<i>.png`。
2. **`detrail.detect_trail_frames`**(cv2):高通 `GaussianBlur − medianBlur(31)` → 阈 `mean+3.5σ` 二值 → `HoughLinesP(threshold=60, minLineLen=0.30*w, maxGap=25)` 检长直线;`edge_hug` 滤掉贴顶/底/左/右边缘的对齐伪影线;取最长内部线 ≥0.30*w 判为**带线帧**。生成审计图(检出帧画红线)供人核。
3. **整帧剔除**这些帧,`run_integrate(images=keep)` 整合剩余。剔 6/52=噪声仅 +6%,可忽略。
- **护栏**:含线帧 >25%(`max_drop_frac`)→ 丢帧损信噪太大,**不自动剔、保留全部并告警**(少帧 LRGB 防误伤)。
- **验证决定性**:NGC7000 52 帧全整合(卫星线明显)vs 剔检出 6 帧整合 46 张(线彻底消失)。检测稳定命中,整帧剔除必净。
- GUI:②对齐子帧 / ③原始素材 模式下复选框"自动去除卫星/飞机线"(默认开);①母版模式无子帧,隐藏。

> 详尽踩坑与实测参数见记忆 pi-wbpp-stacking。
