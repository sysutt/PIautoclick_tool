# SHO 窄带(星云)+ RGB(星点)合成

黑白相机(ASI2600MM 等)SHO 假彩 + RGB 真色星点。**SHO 出星云主体(去星)+ RGB 出星点(SPCC真色)→ recombine**。首验 SH2-132 狮子星云(2026-08-03)。见记忆 [[pi-sho-narrowband]]。

## 素材与整合
- 命名常见"每晚+通道"标签 `FILTER-<dN通道>_mono`(如 d2s=第2晚SII、d1h=第1晚Ha、d3r=第3晚R)。
- **按发射线跨晚分组整合**:S=所有SII子帧、H=Ha、O=OIII、R/G/B=宽带。多晚同线一起 `integrate`(已对齐)。
- SHO 映射 **S→R,H→G,O→B**。

## 【最关键姿势】合成前:各通道先 BXT+降噪、拉伸对齐,再合成
Ha 强、OIII/SII 弱。**线性合成→再拉伸**会让强 Ha 压倒弱通道、混成灰糊(踩过 4 版)。正解:
1. 每通道 detrail→整合→GC→**BXT(deconv,不缩星)→ 线性 NXT 降噪(denoise 0.85,窄带噪声最该在这一步压)**
   → **`stretch` 各自拉到同一 `targetBackground`(如 0.10)** → 每通道非线性、背景对齐(实测 S/H/O 背景落 0.083)。
2. `rgbcombine(r=S,g=H,b=O)` → 颜色干净平衡、青金调直接出。
- **【坑,v12 补】各通道线性降噪别漏**:只在合成/揭示后降噪不够,窄带(尤其 OIII/SII 弱通道)噪声大,必须**逐通道线性 NXT** + 揭示中穿插 + 合成后再一道带色度/低频降噪(见铁律4"早降勤降轻降")。

## 星云揭示(别把星云拉没了)
- **坑**:GHS(D大)把背景连星云一起抬(bg 0.24→0.45),再 `bgneutral(加性平移)` 把 bg 切回 → 整体减 0.38、**星云也被减没**。
- **正解**:背景全程保持低。`stretch` 低 tb 起步 → `starsep` → 去星图上 **`maskstretch`(lum+bgProtect,D≈1.3)×2 + `lmasklift`** 提亮(乘性,不抬背景)+ 穿插轻 NXT → `lhe` 出细节。测到 faint≈0.30~0.35、core≈0.6、bg≈0.07。

## 调色(哈勃 SHO)
- **背景中性** `bgneutral` + **去绿** `scnr`(0.5~0.6)+ **强饱和** `curves(saturation 0.5~0.6)`。
- **暖调(金红,向 AstroBin 常见观感)**:`redemph(amount 0.35~0.4, ciel)` 暖化亮区(Ha→金红),**保住 OIII 蓝体**(SH2-132 狮子主体就是蓝 OIII——别硬压 OIII,否则蓝体丢失)。这套 v11 定稿:蓝体 + 金橙边。
- **两个新调色 op(2026-08-03 加)**:
  - **`chanmix`**(3×3 通道混合,`preset:"gold"` 或 `matrix`):把 Ha(G)按比例折进红出金橙。**注意**:硬折会把 OIII+Ha 混合区搞成红/紫、盖掉蓝体(v9 教训);做暖调用小量、或只用于边缘。
  - **`dynpalette`**(动态调色板,输入 S/H/O 路径,按 OIII 主导度 `w=O^sharp/(O^sharp+H^sharp)` 门控:R/G=nw·(SII/Ha)、B=O → 想做"OIII处纯蓝、Ha处金红")。**当前实现有坑**(门控+锐化易把星云压没或糊成紫),SH2-132 上未调通;要用需先在小图 debug 表达式(`pow`/科学计数法/门控强度)。**首选还是 v11 的 redemph 暖化路子**。

## RGB 星点
- `rgbcombine(r,g,b)` → **BXT(deconv,`sharpenStars≈0.3` 校正+轻收紧,修圆星点)** → 线性 NXT 降噪 → crop → solve+**SPCC**(真实星色)→ `stretch` → `starsep` 取**星点**(丢 starless)→ 提饱和 → 最后 `recombine(星云, stars=星点)`。
- **【坑,v12 补】RGB 合成后必须先 BXT 再分星**:直接 starsep 出的星点**不圆**(PSF 未校正)。BXT 只要跑就校正星点 PSF→变圆(`sharpenStars` 只是额外收紧量)。诊断:放大星场看星点胖软=漏了 BXT。

## 去线(短轨迹易漏)
- **detrail 默认 `min_frac=0.30` 会漏短轨迹**。SH2-132 的 R 通道有 1 帧带**约 10% 图宽**的短线,0.30 检不出、混进星点图成红线(只在 R→合成后红色)。**诊断法**:分别渲染各通道 master + 星点图 + SHO 图,看线在哪张(在 R master=R 有拉线帧)。**修**:对该通道降 `min_frac` 到 ~0.10 重检 → 定位帧 → 整帧剔除重整合。→ detrail 该做成 `min_frac` 可配 / 分档扫短线。

## 定稿要点
- **必查 AstroBin 同视场参考**(`astrobin_ref.fetch_similar(ra,dec)` + `download_thumbs`):SH2-132 好作品是**蓝体(OIII)+ 金红边(Ha/SII)、星云填满**;不查就容易交出偏暗偏淡的图(v5 太暗、v6 偏冷都是对照才发现)。**配色是主观档,应做成用户可选**(经典青金 / 暖金红),给参考让用户挑方向(铁律 8)。
- 保持完整宽场或裁到主体由用户定;SH2-132 本数据视场偏宽、星云偏小。
