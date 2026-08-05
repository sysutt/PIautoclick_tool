# job-runner Op 参考

提交任何任务前先在此确认 op 名与参数。所有 op 通过 `protocol.new_job(op, input=, params=, outputs=)` 提交。
通用可选参数:`params.linear`(True/False,强制预览是否二次拉伸,见 SKILL 铁律 2)。
变换类 op 默认把结果落盘;显式给 `outputs.image`(扩展名决定格式:.xisf/.png/.tif)、`outputs.preview`(PNG)。

## 测量 / 分析类(早返回,不产出图)

| op | 关键 params | 返回 | 用途 |
|---|---|---|---|
| `lumprobe` | `samples`(默认 200000) | `probe`: anchors{background,faint,core}、ladder{p1..p999,max}、coreContrast{std,spread,thr,p10/50/90}、color{R,G,B,redFrac,greenFrac,blueFrac}(仅彩色) | **主力测量**:量化亮度分布、核心对比度、星云色彩占比。见 SKILL 判据表 |
| `starstats` | `thr`(亮像素阈值,默认自适应) | `starStats`: satMean/satMedian/satP90、starPixels | 星点 HSV 饱和度判据(0.25~0.40 自然有色) |
| `bgstats` | `grid`(默认 3) | `bgStats`: cells、min/max、spread、ratio | 分区背景中位数,量化梯度平坦度 |
| `probe` | — | `capabilities` | 探测已装的 PI 进程(BXT/SXT/NXT/SPCC 等)是否可用 |
| `inspect` | — | metrics/preview | 打开图查看;**给 `outputs.image` 时按扩展名落盘且不改图**(用于全分辨率导出) |
| `edgecheck` / `checksolve` | — | 边缘/解析信息 | 诊断 |

## 校准类(线性域)

| op | 关键 params | 说明 |
|---|---|---|
| `deconv` | `sharpenStars`(缩星力度,0=不缩星;反卷积力度内部默认) | BlurXTerminator。星点只校准不缩星→ `sharpenStars:0` |
| `gradient` | `method`("GradientCorrection" 默认 / "abe" / "refbg" / "dbe")、`polyDegree`(ABE 阶,默认 4)、`tolerance`(ABE 采样容差,放宽=纳入更多角落亮样本) | 梯度校准。GC 默认;**颜色梯度**用 abe(不够就 deg5+tolerance 3);refbg 大高斯会吃尘埃、慎用;dbe 有 samples bug |
| `polybg` | `degree`(1平面/2二次,默认2)、`nx`/`ny`(采样网格,默认24/16)、`reject`(亮区剔除σ,默认2.5) | **逐通道低阶多项式背景扣除**:只除平滑大尺度色彩梯度、**不动高频尘埃**。专治"亮源旁角落"残留色梯度(ABE/DBE 搞不定的);ν Sco 那种贴着亮源的残色可能含真实信号,别追到中性 |
| `colorcal` | `method`("bncc" 默认 / "bn" / "cc" / "spcc") | 色彩校准。智能望远镜/宽带用 **spcc**(传感器 Ideal QE + 滤镜 Sony Color Sensor R/G/B-UVIRcut) |
| `solve` | — | 天体解析(SPCC 前置) |
| `integrate` | 见源码 | 叠加(sigmaLow/High 等) |
| `rgbcombine` | R/G/B 单通道路径 | ChannelCombination 合成彩色 |

## 星点分离 / 合成

| op | 关键 params | 说明 |
|---|---|---|
| `starsep` | — ;`outputs.stars`=星点图落盘路径 | StarXTerminator 去星。**务必在完整拉伸后的非线性图上做**(见 SKILL 流程骨架 2) |
| `stretch` | `mode`("stars"=星点专用压黑提亮 / 缺省=autoStretch STF烘焙)、`targetBackground`(默认 0.25,STF 目标背景,星点提取用 ~0.18)、`shadowClip`(默认 -2.8)、`linked`、`stfFrom`(从参考图算 STF 套用) | STF→HT 拉伸。分星前用它把线性图烘焙成非线性 |
| `recombine` | `stars`(已调色星点图路径)、`starAmount`(0~1,压暗星点强度,默认 1) | screen 方式把星点合回 starless。**放在星云调色完成后的最后一步** |

## 拉伸类

| op | 关键 params | 说明 |
|---|---|---|
| `htstretch` | `midtones`(曲线形状,可跨图照搬)、`shadow`(给了用绝对;不给则自适应)、`shadowClip`(默认 -1.2) | 增量 HT。固定 midtones + 自适应黑场。**非线性阶段主力拉伸** |
| `maskstretch` | `stretchType`("ht"/"ghs")、`maskMode`("range"/"lum"/"core")、`smooth`(true=平滑连续蒙版 `1−exp(−k·亮度)`,**防分层**)、`strength`(lum 模式保护强度,越大保护越多→外围提得越少)、`midtones`、`feather`(蒙版高斯羽化 sigma)、`lowerLimit`(range 模式核心下限)、`shadowClip`、`maskContrast`、`bgProtect` | 蒙版保护拉伸:核心保护、外围拉伸。**优先 `maskMode:"lum"` + `smooth:true`**;range 硬阈值会分层 |
| `ghs` | `D`(强度)、`b`、`SP`(拉伸最陡处,对准弱星云亮度)、`LP`、`HP` | GeneralizedHyperbolicStretch。**仅用于极暗反射星云主体** |
| `softstretch` | `targetMedian`(默认0.20,越高越亮/越揭示暗部)、`expandLow`(低段展宽提暗部,默认0.05)、`shadowClip`(默认-1.5)、`linked` | **EZ Soft Stretch 等效**:一次 HT,目标中位偏高 + HT 低段负展宽提暗星云/暗 Hα。**适合 M8 这类中等动态**;**不适合** M42(核心过曝)和极暗反射(太暗,走 GHS)。expandLow 会连带抬核心/背景,M8 用 targetMedian 0.14~0.18 |
| `lhe` | `lowerLimit`(核心蒙版下限 ~0.30)、`feather`(~28)、`radius`(核半径 px ~110~150)、`slopeLimit`(对比上限 ~1.5~2.5)、`amount`(0~1,~0.6~0.8)、`bins` | LocalHistogramEqualization 只在核心蒙版区做,**恢复被压平的亮核内部结构**。会略提核心亮度 |
| `hdr` / `hdrblend` | hdrblend: `hdr`(HDR 图路径)、`coreThr`、`feather` | HDRMultiscaleTransform。全局 hdr 易在亮核周围压暗环 → 用 hdrblend 只在核心融合 |

## 降噪 / 调色

| op | 关键 params | 说明 |
|---|---|---|
| `denoise` | `denoise`(强度 0~1 ~0.7)、`detail`(细节保留 ~0.2)、`colorSep`(色度分离 true)、`denoiseColor`(~0.9)、`freqSep`(频率分离 true)、`denoiseLF`(低频 ~0.6)、`denoiseLFColor`(~0.9) | NoiseXTerminator。发射星云常用 colorSep+freqSep |
| `scnr` | `amount`(0~1,默认 0.75) | 去绿(Green,AverageNeutral 保护)。星云去绿要**轻**(~0.4~0.5),背景清绿可整图 |
| `curves` | `saturation`(S 曲线提饱和 ~0.1~0.4)、`contrast`(K 通道 S 曲线)、`blackpoint`、`highlight`(压高光)、`brightness`、`points`([[x,y],...] 显式亮度控制点)、**`pointsR`/`pointsG`/`pointsB`/`pointsL`/`pointsS`(逐通道显式控制点)** | CurvesTransformation。`points` 用于量化色调映射(测锚点→定目标→反算曲线)。**逐通道点是精细调色主力**:①背景归中性灰——每通道在**自己的**背景电平放点拉到共同目标 + 在 0.65 放"输出=输入"锚点钉住高光(不动星云亮部);②配 `params.mask` 只改某区域的色比。可与 `points`(K)、`saturation` 同时给,一次执行 |
| `redemph` | `ciel`(true=用 CIE L\* 当蒙版,复刻手动第15步)、`lo`(蒙版下限)、`width`(升区宽)、`amount`(红乘性提亮)、`gReduce`/`bReduce`(蒙版区压绿/蓝) | Hα 红强调:**降绿为主(gReduce)+ 提红为辅(amount),gReduce>amount**。只作用亮区、背景不动 |
| `lrgb` | L 图路径等 | 保色亮度替换(RGB×L/meanRGB),不用 LRGBCombination(会洗亮核色) |
| `colormask` | `mode`("green"/"cyan")、`width`(色度斜坡,~0.10~0.15,越小越挑纯色)、`sat`(蒙版区去饱和 0~1,~0.6~0.8)、`dim`(压暗 0~1,~0.04~0.08)、`blurSigma`(~21)、`blurTimes`(~2) | **局部去边角青绿**:建"绿/青过量"色度蒙版(与亮度无关)→ `gconv` 高斯模糊 blurTimes 次羽化 → 蒙版区去饱和+轻压暗。复刻用户"Cyan Color Mask + gconv×2 + CT"。**边角/局部色块用它**;整体均匀偏色用 `bgneutral`/GC;**星云主体偏色**用 `redemph ciel`(CIE L* 蒙版内降色);色彩已平衡时几乎不动=正确 |
| `huemask` | `hue`(blue/red/green/yellow/cyan/magenta)、`mode`("chrominance"=与亮度无关只挑色相 / "lightness"=再乘亮度)、`width`(色度斜坡,~0.10~0.12)、`floor`(先减掉的色度底)、`strength`(0~1)、`blurSigma`(~15)、`blurTimes`(~2) | **色相蒙版生成器**(输出蒙版文件,给别的 op 当 `params.mask`)。复刻手动 `ColorMask` 脚本(`E1=0` 色度 / `E1=1` 亮度、`E2`=强度)+ `gconv($T,15,1,0)` 羽化两次。用途:**只改一种颜色** —— 核心蓝区发黄→蓝蒙版内降 R 提 B;外围 Hα→红蒙版内加红降绿。全局 CT 做不到这种选择性。配 `lumprobe.hueStats.blueCore/redCore`(p98)定目标值 |
| `lmasklift` | `amount`(提亮量,~0.7~0.9)、`low`(蒙版下限≈背景,以下不提)、`high`(蒙版上限≈星云亮区,以上满提)、`ciel`(用 CIE L*) | **星云揭示/提亮的首选**:L 亮度蒙版 `clip((lum-low)/(high-low))` × **纯乘性提亮** `$T*(1+amount·mask)`。**不含黑场下压** → 暗部 mask≈0 几乎不动、**不会把中心空腔越压越黑**(maskstretch/HT 的黑场下压会造成"死黑洞");亮区按 mask 自然提亮。多次少量调用逐步提。**优先用它做揭示,别用带 shadowClip 的 htstretch/maskstretch 硬拉** |
| `bgneutral` | `target`(中性目标电平,留空=四角均值即不改平均亮度;或给低值如 0.03 更干净)、`measureOnly`(true=只测不改)、`frac`(角块比例,~0.08) | **数值法背景中性化**:采样四角背景逐通道中位 → 若 R/G/B 不等=偏色 → 逐通道加性偏移拉到共同 target。**返回实测 bgRGB**。**背景偏色一律"实测→数值校正",绝不用压暗/GC 压缩蒙混**(铁律级);每次拉伸/降噪后重测,漂了就再来一次 |

## 蒙版工作流(**任何 op 都能挂蒙版**)

所有 op 都支持 `params.mask`(蒙版图路径)+ `params.maskInverted`(true=只作用在蒙版**暗**处)。
执行前挂到窗口上、保存前摘掉。手动配方里那套"建蒙版 → 应用 → 翻转 → 跑处理 → 保持蒙版再降噪"
就是这么复刻的。**例外:`starsep`/`deconv`(SXT/BXT)不认视图蒙版**,要用 `maskblend` 手动混合。

| op | 关键 params | 说明 |
|---|---|---|
| `rangemask` | `lower`(下限,**按本图锚点换算 =(faint+core)/2**,别照搬别人的 0.35)、`upper`、`fuzziness`、`smoothness`(羽化,~60.5)、`lightness`(用 CIE L*)、`invert` | 亮度范围蒙版(= 手动 `RangeSelection`)。选出**主体**;翻转后就是**背景**。最常用两处:①背景重降噪 / 主体轻降噪(铁律 20);②翻转后 CT 只提亮主体之外的暗弱信号 |
| `starmask` | `boost`(~8)、`gamma`(~0.45)、`grow`(羽化 sigma ~1.5)、`floor`(先减底噪,~0.02)、`bin` | 从**星点图**取亮度大幅提亮成星点蒙版。用途:窄带里有**类星点的真实结构**(彗状结节)时限定去星位置 |
| `maskblend` | `top`(上层图路径)、`mask`、`maskInverted` | `out = mask*top + ~mask*$T`。**SXT/BXT 不认视图蒙版的唯一解法**:全图去星得 starless → `maskblend(view=原图, top=starless, mask=星点蒙版)` → 只有真恒星位置换成去星版 |
| `nbtint` | `nb`(窄带图)、`kR`/`kG`/`kB`(各通道注入系数)、`fit`(先 LinearFit)、`thr` | 把单通道窄带当**颜色特征层**注入彩色底图(`$T[i] + k_i*w`)。SII 染黄内圈可用它,也可以改用"SII 当 mask + CT 抬 R/G"(更可控,见 C63 配方 C2) |

## 其它

| op | 用途 |
|---|---|
| `dustremove` | 去尘/坏点(双向) |
| `flatpatch` | `x`/`y`/`r`(灰尘环中心与半径,像素)、`mode`("gain"乘性,默认 / "offset"加性)、`feather`、`maxCorr`、`measureOnly`:**人工平场**——羽化圆蒙版内量斑内/环外亮度差,按增益拉平圆形灰尘残影。**只改低频亮度、不动结构** → 斑压在星云上也安全(`dustremove` 填平只能用于空背景)。**乘性增益只在线性 master 上精确** → 必须在裁边+GC 后、拉伸前修,别等成片(成片是非线性合成,环除不净)。**自动检测(`dustspot`)不鲁棒**(对齐后各通道位置不同、拉伸预览星点星云干扰)→ 靠**用户点选环心**(`dustspot.fit_at` 拟合半径),桌面应用的"随时暂停介入"即此:运行中停在某步 → 点环心 → flatpatch 当前线性图 → 继续 |
| `maskline` | `params.lines`=[[x0,y0,x1,y1],...]、`width`:把线段带像素置 0(剔卫星/飞机轨迹,叠加前用)。**自动去线已弃用它**(定位精度不足挖不净),仅手工场景保留 |
| `residualset` | `params.images`、`outDir`、`zoom`(默认8):中位叠加出参考 → 每帧残差 `max($T−ref,0)`(按通道数自适应)→ autostretch+缩放存 `res_<i>.png`。全自动去线的检测输入,配 `orchestrator/detrail.py::detect_trail_frames`(cv2 霍夫)→ `pipeline.run_detrail` 整帧剔除带线帧 |
| `delinetrail` | 除轨迹 |
| `hablend` | 有独立 Hα 图时的"小红花"融合(OSC 无独立 Hα 时用 `redemph` 代替) |
| `chanmix` | 3×3 通道混合(`matrix=[[rr,rg,rb],...]` 或 `preset:"gold"/"teal"`):新RGB=矩阵·原RGB。窄带调色:把 Ha(G)折进红出金橙。**慎用**:硬折会盖掉 OIII 蓝体(见 sho-narrowband) |
| `dynpalette` | 动态窄带调色板(`s/h/o`=三通道路径,`sGain/hRed/gGain/oGain/sharp`):按 OIII 主导度门控→OIII处蓝、Ha/SII处金红。**当前实现有坑(易压没星云/糊紫),未调通** |

> 参数并非全部;新增或拿不准时读 `E:\AutoClick\pipeline\job-runner.js` 里对应
> `applyXxx` 函数的 `params.xxx` 读取处确认。
