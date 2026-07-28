# 明亮发射星云后期(M42 型,OSC)

适用:主体明亮的发射星云(M42、M8、M17…),智能望远镜或普通 OSC 彩色数据。
核心技法:**STF 判定 + 蒙版保护 + HT 拉伸 + 空间局部对比度**,不用 GHS(GHS 只留给极暗反射主体)。
全程按 SKILL 判据表测量驱动。以下参数是 M42(15s 智能望远镜 OSC master,峰值仅 ~0.06 未饱和)走通的值,
新目标按判据微调,不要盲目照搬绝对 shadow(见铁律 3)。

## 阶段 A — 校准(线性域)
1. `deconv`(BXT):反卷积 + 星点校准,`sharpenStars:0`(只校准不缩星)。
2. `gradient`(GC):梯度校准;**梯度轻就只用 GC**(先观察原图梯度大小再决定,别反射性上 GraXpert;多做一步无害但非必需)。顽固梯度再 `gradient` method=abe polyDegree=4。
3. `solve` → `colorcal` method=`spcc`。**SPCC 传感器按相机选**:**ASI2600MC = Sony IMX411/455/461/571**(不是泛化的 "Sony Color Sensor");智能望远镜用 Ideal QE + Sony Color Sensor + R/G/B-UVIRcut。
   校准后可 STF 勾 Link 看色彩与残余梯度。
   - **【robustness 2026-07-28】SPCC 会偶发失灵(没真校准、留绿)**:SPCC 后**测一下 `lumprobe` 的 color**——OSC 平衡后 greenFrac 应 ≈0.33;**若 greenFrac 明显偏高(>~0.38)= SPCC 没生效,重跑一次 SPCC 即平衡**(IC1396 实测:首次 gF 0.42→重跑 0.325)。别急着往下走,否则整条链一路偏绿。
   - **铁律 3 提醒**:后面拉伸/揭示的**曲线绝对点不能跨图照搬**(照搬别的图的点会发白/过暗)→ 每次**测锚点自适应建曲线**。
4. **裁剪**去旋转/覆盖黑边(可提前到线性阶段做;**裁后要重跑一次 `solve` 天文解析**,否则 WCS 失效)。

## 阶段 B — 星点分离(正确姿势,关键)
**先把 SPCC 后的线性图完整拉伸成非线性,再分星**,得到的星点亮度/PSF 光晕天然合理:
1. `stretch`(缺省 mode=autoStretch,STF→HT 烘焙):`targetBackground≈0.18, shadowClip≈-2.8, linked:True, linear:True`。
2. `starsep`(SXT):`outputs.stars` 落盘星点图,`outputs.image` 落盘 starless。
   - 走通判据:星点图 `lumprobe` 应有 p99≈0.20、p999≈0.84、峰值≈1.0(从暗到亮自然铺开)。
3. 星云拉伸用另一条链(下面阶段 C),星点先放着,阶段 F 才调色+合成。
> **反例(别做)**:在只做了轻微初拉伸的图上分星 → 星点欠拉伸;再单独 `stretch mode=stars`
> 用大 `clipSigma` 硬裁 → 光晕被裁掉 → 星点"又细又硬"。这是踩过的坑。

## 阶段 C0 — 亮核高动态判定(先做)
若核心动态范围很大(线性 max 高、或任何温和全局拉伸都把核心冲到 ~0.95+),链式 STF 会爆核。
此时先接受全局拉伸把核心冲高,再用 **`hdr`(HDRMultiscaleTransform,layers≈6)**把核心压回
(实测 0.95→0.65)且**多尺度保住内部结构**(core-std 不塌,优于全局曲线)。之后再进阶段 C 提外围。
判断:温和 `stretch`(tb≈0.06)后 `lumprobe` 的 core 已 ≥0.9 → 走 HDRMT;否则直接阶段 C。

## 阶段 C — 星云拉伸(在 starless 上,平滑蒙版,守住亮度层级)
从干净的 starless(可来自阶段 B 的 starless,或独立初拉伸+SXT 的 starless)出发:
1. **全局 HT 起步**(无蒙版→无分层):`htstretch midtones≈0.05`(把核心提到 ~0.6,背景仍近黑)。
2. **平滑连续蒙版逐步提外围、护核心**:`maskstretch maskMode="lum" smooth=true`,
   分 1~2 步推进。示例:`strength≈1.5, midtones≈0.11, feather≈40`(strength 越大保护越强、
   外围提得越少——别搞反)。目标把 `anchors.faint` 提到 ≈0.30~0.35、`core` 落 ≈0.78,层级不倒挂。
3. **`lhe` 恢复核心内部结构**:`lowerLimit≈0.30, feather≈30, radius≈120~150, slopeLimit≈2.0~2.5, amount≈0.7~0.8`。
   核心 `coreContrast.std` 应回升(全局曲线做不到这一点——见铁律 6)。amount 会略提核心亮度,可当"核心略提亮"。

每步后 `lumprobe` 对照:核心不死白(core≤~0.87、非 1.0 死白团)、外围不空(faint≈0.3)、
背景暗净(background≈0.05)、层级 core>faint>background 不倒挂、无等亮度分层(放大中下段确认)。

## 阶段 D — 降噪(贯穿阶段 C 的拉伸,不是最后单独一步)
**早降、勤降、轻降**(IC1396 实测,比末尾单次重降明显干净、细节不糊):
- **第一次拉伸(STF→HT 烘焙成非线性)后立刻 NXT 一次**,中等力度 `denoise≈0.65, detail≈0.15`。
- 之后**阶段 C 每加一档拉伸(每步 curves/HT/maskstretch)就补一次轻 NXT** `denoise≈0.35~0.40`。
- 完整参数:`colorSep=true, denoiseColor≈0.85~0.9, freqSep=true, denoiseLF≈0.55~0.6, denoiseLFColor≈0.85~0.9`。
- 原理:噪声随拉伸逐级放大,边拉边压不让它累积;末尾才重降要对付已放大的噪声、还磨细节。
背景提得越高越要这样交错降。**注意**:仍遵铁律 10/噪声优化——力度过猛就先降拉伸,别靠猛降噪硬盖。

## 阶段 C' — L 亮度蒙版**纯乘性提亮**揭示(2026-07-28 定稿手法,IC1396 逐步打磨)
**这是揭示的首选,取代带黑场下压的 htstretch/maskstretch**(后者把中心空腔越压越黑=死黑洞、过渡生硬)。
1. SXT 后在 starless 上,先按需 `bgneutral` 把背景**数值校成中性**(见下阶段 E')。
2. **`lmasklift`**(= Extract CIE L\* 当蒙版 + 纯乘性提亮 `$T*(1+amount·mask)`,`mask=clip((lum-low)/(high-low))`):
   `low`≈背景(以下不提)、`high`≈星云亮区(以上满提)、`amount`~0.8~0.9、可 `ciel:true`。**不含黑场下压 → 暗部 mask≈0 几乎不动、不压黑洞**;亮区自然提亮。**多次少量**调用逐步提(faint 每步 +0.05~0.10)。
3. **每步后**:重测背景 RGB(`bgneutral measureOnly`)确认仍中性、看颗粒感必要时轻 NXT(铁律 14/15/D)。
> 反例(踩过):全局 `curves`/`htstretch` 硬拉整个色调范围 → 抬背景噪点+放大背景偏色+亮暗过渡生硬+中心死黑洞。换 lmasklift 全解决。

## 阶段 E — 星云调色
1. **轻去绿**:`scnr amount≈0.45`(AverageNeutral 保护,不伤饱和红星云;清背景绿)。
2. **提饱和**:`curves saturation≈0.10~0.20`(用户要"淡一点"就取低端)。
3. **可选 Hα 红强调**(第15步):`redemph ciel=true`,**降绿为主+提红为辅**:
   `lo≈0.30, width≈0.40, gReduce≈0.12, amount≈0.08`(gReduce>amount)。CIE L\* 蒙版只作用星云亮区。
   - **白平衡硬判据**:调完后**反射星云亮区仍是近纯白→淡蓝**(bluFrac 最高)。若反射区被染红=红提过头,回退。
   - 发射区目标 `color.redFrac≈0.38~0.40`。背景各占比≈0.333;若某侧仍偏绿(grnFrac 高),整图补一次轻 `scnr`。
   - **注意**:这一步的"浓/淡"档位是主观审美,量化到判据即可,最终"最舒服那档"给用户看图确认(铁律 8)。

## 阶段 E' — 局部背景偏色(青/绿)→ 色度蒙版 + CT(优于全局 SCNR/GC)
提亮/提饱和后若**某一块背景**泛青绿(常见右下角),而星云颜色已满意 → **别用全局 SCNR/GC(会伤星云或整体偏色)**,用**色度蒙版只动那块**:
1. 建色度蒙版(PixelMath,"Simple Cyan Color Mask"):`E1=0`(=色度蒙版;1 为亮度蒙版)、`E2=1.0`(强度 0~1)。
2. 对蒙版 **`gconv` 模糊两次**(羽化,免硬边):`gconv($T, 15 /*sigma,越大越糊*/, 1 /*aspectRatio*/, 0 /*rotationAngle*/)`。
3. 蒙版套到 starless → `CurvesTransformation` **降一点亮度+饱和**,直到那块青绿并入周围背景。
这是"SCNR 万不得已、偏色治本/局部治"的最佳落地:只中和目标色区、完整保留发射星云红与蓝反射。(均匀整体偏色仍优先 GC,见 SKILL 常见坑;局部色块用本法。)

## 阶段 F — 星点调色 + 最后合成
1. 星点调色:`scnr amount≈0.6~0.7`(去绿)→ `curves saturation`。
   - **【克制去绿保星色 2026-07-28】若画面有亮星,SCNR 力度要小(~0.4)**:强去绿会把亮星从**亮黄**染成**红褐**(IC1396 右下亮星实测)。宁可留一点绿也别毁掉亮星的黄色;星色比彻底去绿重要。
   - **【重要 2026-07-27,IC1396】screen 合成会把星色冲淡,星云越亮冲得越狠**:recombine 用 screen,
     叠到**明亮**星云上时星点颜色被洗白。所以**标准 satMean 0.25~0.40 是指最终合成图上的星点**,
     而**独立星点图要拉得更足**才能扛过冲淡——亮星云背景下独立星点图 saturation 用 ~0.45、
     `starstats` satMean 到 ~0.6 才合适(暗背景/星系类目标才用 0.35/满足 0.3~0.4)。看合成后成品判断,
     星色不足就回头把独立星点 saturation 再加、scnr 再降一点(scnr 越猛越掉色)。
2. **最后合成**:`recombine input=<调色后的星云> params.stars=<调色后的星点>`(screen)。顺序必须是先星云后星点。

## 阶段 G — 导出
`inspect input=<最终 xisf> outputs.image=<...>.png` 与 `.tif` 各一次,导全分辨率
(不改图,扩展名决定格式)。PNG 供查看/分享,TIFF(32bit)作母版。

## M42 走通的量化落点(参考,非硬指标)
- 星云:background≈0.05,faint≈0.30~0.35,core≈0.78~0.87,coreContrast.std 回升;
- 颜色:发射区 redFrac≈0.38~0.40,反射区(跑步者 NGC1977)bluFrac 最高(近白→淡蓝);
- 星点:satMean≈0.30~0.42,亮度分布 p99≈0.20/p999≈0.84/峰值≈1.0。

## 噪声优化(重要)
成片噪声偏大时,**优先降低拉伸力度,而不是多做一次降噪**——多降噪会磨掉细节;噪声本质是把
暗部/faint 提太狠时被放大。做法:阶段 C 的提升 **HT midtones 调大**(记牢:midtones 越小拉伸
越强、越大越弱),把 `faint` 目标从 ~0.35 降到 ~0.30 左右,从源头少放大噪声、细节保留。
提升致背景被抬高时,用 `curves points:[[bg,目标],[faint,~保持]]` 只压背景(别用 blackpoint,会连 faint 砸)。

## 决策速查
- 核心死白 → 不是数据饱和(检查 max),多半过拉伸;蒙版护核 + 别全局硬压。
- 亮核高动态(温和拉伸也爆核)→ 全局拉伸后用 `hdr`(HDRMT)压核心保结构(阶段 C0)。
- 噪声大 → 降拉伸力度(midtones 调大、faint 目标 ~0.30),别只靠多降噪。
- 核心发平 → `lhe`,不要加大全局压缩。
- 分层 → `maskstretch smooth=true`(平滑连续蒙版)。
- 外围太暗/暗环 → 降低蒙版 strength、提 midtones,把 faint 提到 ~0.3。
- 星点细硬 → 回阶段 B 正确星点流程重做。
- 背景偏绿 → 轻 `scnr`;反射区被染红 → 降 `redemph` 力度或提高 `lo`。
