---
name: deepsky-postprocess
description: >-
  驱动 TTAstroPiLot / PixInsight 自动化管线(常驻 PJSR job-runner + 文件 IPC 编排器)
  对深空天体图像做后期处理:拉伸、降噪、星点分离/合成、色彩校准与调色。凡是用户要
  "处理/调整/后期一张天文图像"(发射星云如 M42、反射星云、星系、OSC 彩色或黑白窄带
  数据),或提到 job-runner / PixInsight 自动化 / 拉伸不动 / 核心过曝 / 星点太细 /
  背景偏色 / 分层 等后期问题,都应使用本 skill。它把整条流程和**量化判据**统一成
  一套 LLM 无关的规范,任何对接本工具的模型都照此执行,以保证一致的处理结果。
---

# 深空天体自动后期(TTAstroPiLot / PixInsight 管线)

本 skill 是驱动本管线的**统一操作规范**。目标不是"凭手感调图",而是**用测量数据驱动每一步、
用明确判据判断对错**。任何 LLM 照此执行都应得到一致、可复现的结果。

## 架构:管线怎么跑

- **job-runner.js**(`E:\AutoClick\pipeline\job-runner.js`):常驻 PixInsight 里的 PJSR 脚本,
  轮询 `_run/inbox/*.json`,执行一个 op(操作),把结果写到 `_run/done/`,并周期写
  `_run/runner.heartbeat` 判活。
- **编排器**(`E:\AutoClick\pipeline\orchestrator\`):Python 侧。`protocol.py` 提供
  `new_job(op, input=, params=, outputs=)` / `submit(job)` / `wait_result(job_id)` /
  `runner_alive()`。所有路径用正斜杠。
- **一次 job** = 一个 op + 输入图 + 参数 + 输出路径。变换类 op 把结果落盘为 `.xisf`,
  并生成忠实预览 PNG(见"忠实预览"铁律)。

### 提交任务(Python)
```python
from orchestrator import protocol
job = protocol.new_job("htstretch", input="E:/AutoClick/pipeline/_run/x.xisf",
                       params={"midtones":0.12,"linear":False},
                       outputs={"image":".../y.xisf","preview":".../T_y.png"})
protocol.submit(job)
r = protocol.wait_result(job["job_id"], timeout=180)   # r["status"]=="ok" 才算成功
```
在 `E:\AutoClick\pipeline` 目录下运行 Python(否则 `import orchestrator` 失败)。

### 启动 / 重载 job-runner(改了 job-runner.js 必须重载)
`-r=` 只在**冷启动**的新实例生效;已有实例会吞掉它。**先杀干净所有实例,再冷启一个**:
```bash
powershell -NoProfile -Command "Get-Process PixInsight -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 3"
rm -f E:/AutoClick/pipeline/_run/runner.heartbeat
("<PixInsight.exe 路径>" -n "-r=E:\AutoClick\pipeline\job-runner.js" >/dev/null 2>&1 &)
# 约 18~22s 上线;用 protocol.runner_alive() 轮询确认
```
若出现 PixInsight 弹窗(如 "Risky Temporary Folders")挡住,用 UI Automation 点掉;
`popup_guard.py` 只处理"同时有肯定+否定按钮"的确认框,单 OK 框需另行点。

## 铁律(先读——这是认知对齐的核心)

1. **测量优先,不靠肉眼猜。** 每个关键步骤后用 `lumprobe` / `starstats` / `bgstats`
   测数值,对照判据表判断,再决定下一步。预览 PNG 只用来看结构/颜色定性,亮度一律看数值。
2. **忠实预览。** 预览会按中位数判断线性/非线性(<0.03 视为线性→自动拉伸显示)。判断真实
   亮度时,给 op 传 `params.linear=False` 强制不二次拉伸,否则会被"暗背景亮星云"的假象骗到。
3. **绝对 shadow 不能跨图照搬,曲线形状(midtones)可以。** shadow 依赖本图刻度;拉伸用
   **固定 midtones(曲线形状) + 自适应黑场**(`shadow=median+shadowClip*MAD*1.4826`,
   shadowClip≈-1.1~-1.2),每步压住当前背景防翻噪。
4. **一旦第一次 HT 把图变非线性,就别再用 STF。** 只用 HT 增量推进,否则会叠加多余拉伸。
5. **维持自然亮度层级:核心>内层>外围>背景,绝不倒挂。** 蒙版压核心是为了防死白过曝,
   但绝不能把内部压得比外围暗——那违反物理常识。逐步小幅拉伸就是为了始终守住这个梯度。
6. **全局曲线不能同时"压核心亮度"和"留核心对比度"**——在 [0,1] 内两者互斥。亮度用色调解决,
   核心内部对比度(发平)必须用**空间局部处理**(`lhe`),不要用全局压缩硬压(会压平)。
7. **蒙版分层的根治**:亮度阈值硬蒙版 `iif(亮度≥阈值,1,0)` 的过渡带压在等亮度轮廓线上→"分层"。
   用**平滑连续蒙版**(`maskstretch` 的 `smooth:true`,`1−exp(−k·亮度)`,处处无拐点)。
8. **客观流程能量化做好,主观色彩美学的"最舒服那一档"要留给人。** 白平衡、饱和是否达标可量化,
   但"再淡一点/再浓一点"这类审美档位,给用户看图确认,别自作主张反复微调。
9. **SCNR 去绿是"万不得已"的补救,不该常规用在星云上。** 它把绿往红蓝挪,对发射星云会把 Hα
   红染成黄褐。**背景偏色治本在前期校准**(梯度/色彩做对),让绿压根不出现,而非事后 SCNR 盖。
10. **拉伸力度看积分深度/信噪,不只看目标亮不亮。** 深数据(数小时)要**"揭示"**——钉住背景、
    把星云整体抬起,让外围暗云气/淡反射浮现;浅数据(如 30s 单张)才"克制"——压背景+强降噪防噪。
    **`run_rgb` 已内建 GHS 拉伸自检闭环**(`stretch_judge=True`):GHS 后自动 `judge_ghs` 判力度,报
    `too_dark`/`too_strong` 且偏离当前值就按建议 D 重拉一次(仅一次防振荡)。**固定 `ghs_d=0.5` 对低面亮度
    弥散星云偏保守**(NGC7000 实测:评委纠到 D≈1.1–1.2 才够,主体/发射脊/暗尘层次才出);闭环让它自纠,
    可选喂 AstroBin 参考(`stretch_refs`)更准。见 [[pi-aesthetic-prefs]]。
11. **残留色彩梯度治本用 `polybg`(逐通道低阶多项式)或更强 ABE(deg5+放宽 tol),不是 SCNR。**
    自动 GC/单次 ABE deg4 常压不掉"亮源旁角落"这类色梯度;`polybg` deg2 只除平滑梯度、不动尘埃。
12. **亮核高动态目标(温和拉伸也把核心冲到 0.9+)用 `hdr`(HDRMultiscaleTransform)** 压核心+
    多尺度保结构,别用全局曲线硬压(会压平,见铁律 6)。**暗尘细丝/团块的立体层次**用 `lhe`
    (LocalHistogramEqualization,只做亮区羽化蒙版、不动背景);**`run_rgb` 已内建**(`lhe=True`,`r11b_lhe`,
    提饱和后,`lowerLimit=0.30,amount=0.5,radius=110`)。
13. **定稿前必查 AstroBin 同视场参考对照亮度/色调。** 量化判据只保证"不过曝/不倒挂/不偏绿",
    但"整体该多亮、什么色调"必须对照**真实优秀作品**(`orchestrator/astrobin_ref.fetch_similar(ra,dec)`,
    返回字段 `list`;优先宽带 RGB/OSC,窄带 SHO 是假彩只能比亮度/结构)。**深数据尤其容易凭感觉压太暗**
    (IC1396 实测:v1 background 0.06/faint 0.28 自以为达标,对照参考发现该到 background 0.12/faint 0.37 才对)。
    不查参考就定稿=容易交出偏暗偏闷的图。见铁律 10 + [[pi-astrobin-reference]]。
14. **星云揭示/提亮别用带黑场下压(shadowClip)的 HT。** shadowClip 会把中心空腔/暗云**越压越黑成"死黑洞"**、过渡生硬。两条安全的揭示路子,都**不压黑场**:
    - **`lmasklift`**(L 亮度蒙版乘性提亮 `$T*(1+amount·mask)`):暗部 mask≈0 几乎不动,亮区按亮度提亮 → 适合"把已可见星云提得更亮";蒙版单调随亮度增,偏袒亮区。多次少量。(IC1396 实测:全局 curves/HT 硬拉→黑洞;换 lmasklift→全解决。)
    - **`maskstretch`(`maskMode=lum`+`smooth`+`bgProtect`,GHS 模式)**:混合 `mask*原图+(1-mask)*拉伸版`,lum 蒙版在亮核=1**护住亮核**、bgProtect 护暗背景,额外拉伸**只作用在暗弱/中间调** → 适合"把全局 GHS 提不动的外围淡 Ha/弥漫云抬起"。**`run_rgb` 已内建此步**(`reveal=True`,`r09b_reveal`,`reveal_d=0.7`;NGC7000 实测比纯 GHS 信息量大、护核护背景)。用 GHS 模式(非 HT),不碰 shadowClip 所以无黑洞。
15. **背景偏色一律"实测 RGB → 数值校正",绝不靠压暗/GC 压缩蒙混。** 用 `bgneutral` 采四角背景逐通道中位,看是否 R=G=B(中性灰);不等就逐通道加性偏移拉到共同电平(不改平均亮度)。**每次拉伸/降噪后重测**(会漂),漂了再校。**两种色问题两种工具**:边角/局部色块→`colormask`(色度蒙版);**星云主体偏色**→`redemph ciel`(CIE L* 亮度蒙版内降色,方法A)。
16. **主观拉伸/调色可"每步出截图给用户确认再进下一步"。** 拉伸/色彩是主观档位(铁律 8),逐步确认比一把跑完再返工高效——用户明确要这种节奏时照做,每步 `inspect` 出预览、量化(锚点+背景RGB)一起给。
17. **跑任何 PI 自动化步骤(含独立 -r= 脚本)前先起看门狗** `python -m orchestrator.watchdog`
    (弹窗自动点 + 真卡死自动重启;卡住多半是没开它)。判卡死必须"心跳旧 **且 CPU 平**"——
    心跳单独会被长任务(BXT/SXT 数分钟)误判。见 [[pi-watchdog]]。
18. **梯度校正必须在裁掉黑边之后做——所有目标、所有流程的固定顺序。** 对齐/叠加后的图常带
    **黑边或部分覆盖的暗边**;若先 GC/ABE/refbg,黑边会污染梯度拟合 → **靠近边缘出现亮度异常**
    (用户 2026-08-04 查过程文件发现;修正后 AI 评委不再报 `residual_gradient`/`edge_artifact`)。
    正确顺序:**整合 → 裁黑边 → 梯度校正 → 其余**。多通道(SHO/LRGB)还须**裁同一边距**才保持对齐:
    各通道 `crop`(不传 margins → `detectBordersCoverage` 自动检黑边)取**并集(最大值)**+ 安全边,
    统一裁完再逐通道 GC。`run_rgb`/`run_sho`/`run_lrgb` 均已按此顺序。
19. **拉伸策略按天体类型分流——星团别拉背景。** 星团(球状/疏散)背景是空的(无星云/星系),
    拉伸只会把天光+噪声抬成**发白"奶雾"**(M22 实测背景中位 51/255=反面教材)。**先判该不该动背景**:
    - **判类型**:解析只给 `OBJECT` 名+坐标、无类型 → 用名字查自有后端 DSO 目录
      (`orchestrator/dso.classify(name)` → `POST /weather {a:dso_search,d:{catalog_id}}`;type 编码
      `GCL`/`OCL`=星团、`Nb`/`Gxy`/`PN`=有延展信号;`dso_search` 按名查不吃坐标,用 FITS `OBJECT`)。
    - **两级门控(类型≠画面空,别只看类型)**:类型=星团只是**候选**;M45 裹反射星云、银河球团压暗云带,
      即使是星团画面里也有真信号。**第二级:LLM 看拉伸预览判"除了星点,有没有较大面积、值得保留的暗云或星云"**
      (`critic.judge_field_extended`)→ 有则退回正常(保背景、照常揭示),没有(空旷星场)才钉黑。
    - **星团克制模式**(候选 + 场判无延展 → 触发):**不揭示(reveal off)**、**GHS 评委不自动加大 D**
      (深黑背景是对的、**不是 too_dark**)、拉伸 `targetBackground 0.06`、末尾 `bgneutral(target≈0.06)` 钉深黑中性。
      重点交给星点(颜色/不糊/核心不过曝)。
    - 星云/星系/行星状 → 正常走揭示(铁律 10/14)。查不到类型 / LLM 不可用 → 退化(前者按"有信号"不误伤星云;后者仅按类型)。见 [[pi-target-classify]]。
20. **降噪一律挂"背景蒙版",绝不全图降噪。** 用户抱怨"背景偏亮、噪点多"时,顺手把 NXT 开大跑全图
    = 把**星云内部真实结构**一起抹平(C63 实测:OIII 0.7+0.65 全图 → 空腔的丝状/斑驳糊成一块,
    合成后核心变成**死板纯色圆盘**;SII 0.75+0.7+0.5 同样毁了内圈纹理)。正解三步:
    `rangemask`(lower=(faint+core)/2)选主体 → **翻转蒙版**背景重降噪(0.8~0.9,detail 0.15)→
    **保持蒙版**主体轻降噪(0.25~0.35,detail 0.3~0.35);被糊掉的残存层次用 `lhe` 找回
    (C63 OIII:radius 128 / slopeLimit 1.6 / amount 0.45 / lowerLimit=主体阈值)。
    自检:降噪前后各切一块**主体 1:1 特写**对比,只看背景数值会以为"干净了=好了"。
21. **"照搬 midtones"的前提是前面的拉伸量相同,否则就是双重拉伸。** 铁律 3 说形状可照搬,但
    在**已经自适应 `stretch` 到 bg≈0.10** 的图上再套一次别人的 `htstretch(midtones)` = 拉两次。
    **量化自检:`core − faint` = 主体动态范围,< 0.15 就是拉爆了**(C63 Ha 实测 0.742/0.859
    = 0.117 → 环带死白无层次,而且 Ha 一强就把合成里 OIII 的蓝色层次一起压没)。健康 ≈0.17~0.25。
    修法:**只做一次** `stretch`;电平不够时用**保斜率抬升曲线**
    (`points=[[0,0],[bg,bg],[faint,目标faint],[core,目标core],[1,1]]`,保证段内斜率 ≥0.85),
    不要再叠 HT。
22. **窄带合成不只要对齐背景,还要对齐"通道相对强度"。** 改了任一通道电平后,合成公式的增益
    必须跟着重定:C63 实测 Ha faint 由 0.742 降到 0.627 后,`dynhoo hGain=0.8` 让 **R 反而成了
    最弱通道**(主体 R .60 / G .72 / B .71)→ 环带发紫;`hGain=1.0` 才回暖色环带,`1.15` 偏粉。
    **判据:主体亮区处 R ≥ G,环带才是暖色**;`hGain ≈ O_faint / H_faint` 是好起点。

## 测量优先:量化工具与判据

用 `lumprobe`(采样全图亮度分位)。返回 `anchors`(三段)、`ladder`(分位阶梯)、
`coreContrast`(核心内部展宽)、`color`(星云亮区 R/G/B 与占比;**`params.colorPct` 指定取样分位,
星点图必须传 0.999** —— 星点图 90% 像素≈0,默认 p90 量出来的"颜色"全是噪声,会误判偏绿)、
`bgColor`(**背景逐通道 R/G/B**,= 手动在背景处读三个值的自动化版,用于"归中性灰")、
`hueStats`(`blue`/`red`/`green` 按色度过量 p90 = 整个色相区,`blueCore`/`redCore`/`greenCore` = **p98 色相核心**;
移植手动读数必须用 **Core** 档,用 p90 会把整片淡晕当核心一起推)、
`at`(`params.at=[[x,y],…]` **指定坐标读点**,直接核对用户截图里的 R/G/B 读数)。
判据(非线性成片经验值):

| 量 | 工具/字段 | 目标 | 含义 |
|---|---|---|---|
| 背景 | lumprobe anchors.background | ≈0.05(暗但不死黑) | 天空背景亮度 |
| 外围淡云 | anchors.faint | ≈0.30~0.35 | 外围星云可见、不空 |
| 核心 | anchors.core | ≈0.78~0.87(≠1.0) | 亮核不死白 |
| 层级 | core>faint>background | 不倒挂 | 见铁律 5 |
| 核心对比度 | coreContrast.std | 越大越立体(参考 ≥0.15) | 发平=std 低,用 lhe 救 |
| **主体动态范围** | anchors.core − anchors.faint | **≥0.17**(0.17~0.25 健康) | **<0.15=拉爆了**,见铁律 21 |
| 背景中性灰 | bgColor.R/G/B | 三值互差 <0.01 | 逐通道曲线归位,见"背景归中性灰" |
| 星云红味 | color.redFrac | 发射区 0.38~0.40 | =R/(R+G+B),中性=0.333 |
| 背景中性 | 各区 redFrac≈grnFrac≈bluFrac | ≈0.333 | 偏绿要补去绿(SCNR) |
| 星点饱和 | `starstats` satMean | 0.25~0.40 | <0.15 偏灰;提饱和到位 |
| 白平衡判据(反射) | 反射星云亮区 | 近纯白→淡蓝(bluFrac 最高) | 反射区偏红/黄=错 |
| 极暗反射(蓝) | color.blueFrac | 蓝反射 0.38~0.40(最高) | 如 IC4592;不提红、暖棕尘保留 |
| 星系核球 | color.redFrac 略高、去绿 | 核球黄白、旋臂偏蓝、尘带暗 | **绝不提红**;发射星云那套判据不适用 |
| 梯度平坦 | `bgstats` spread/ratio;四角 redFrac/blueFrac | 越小越平;四角≈0.333 | 四角某色占比偏高=残留色梯度→polybg |

## 处理路径选择(先分类目标类型 → 决定判据与工具)

- **明亮发射星云**(M42/M8/IC434…):蒙版+HT(+亮核高动态则 HDRMT)。判据=红脊 Hα、反射区白蓝。
  详见 `references/emission-nebula.md`。
- **星系**(M31…):不用 GHS;**绝不提红**,核球黄白、旋臂蓝、尘带暗。详见 `references/galaxy.md`。
- **极暗反射星云**(蓝马头 IC4592 这类主体极弱):用 **GHS**(SP 对准微弱星云亮度选择性提亮),
  判据=蓝反射 blueFrac 最高、暖棕尘、暗 moody。详见 `references/reflection-ghs.md`。
- **黑白相机 RGB(+Hα)**:**逐通道 BXT+梯度 → 合成 → SPCC → 拉伸(HT到范围1/4峰1/8+NXT+SXT)
  → Hα 独立做成高对比 starless 层 → 非线性红增强 → 微调 → 合星**。详见 `references/mono-rgbh.md`。
- 判断依据可结合 LLM + AstroBin 同视场参考图分类(见管线的 astrobin_ref)。**不同类型判据不通用**
  ——把发射星云的"提红/红脊"套到星系或反射星云上就是错的。

## 通用流程骨架(顺序很重要)

1. **校准(线性域)**:BXT(反卷积 0.5,不缩星)→ GC 梯度 → SPCC 色彩校准(智能望远镜:
   传感器 Ideal QE + 滤镜 Sony Color Sensor R/G/B-UVIRcut)。
2. **星点分离(正确姿势)**:先把 SPCC 后的线性图 **STF 拉伸 + HT 烘焙成非线性**,
   **再在这张非线性图上 SXT 分星**——这样得到的星点图亮度和 PSF 光晕天然合理。
   **切勿**在欠拉伸图上分星后再单独硬拉/裁剪星点(会又细又硬)。
3. **星云拉伸(starless)**:全局 HT 起步(无蒙版无分层)→ **平滑连续蒙版**逐步提外围、护核心
   → 用 `lhe` 恢复核心内部结构。全程对照判据表。
4. **降噪(贯穿拉伸,不是末尾单独一步)**:**早降、勤降、轻降**——**第一次 HT 拉伸(把线性变非线性)后立刻 NXT 一次**(中等 ~0.65),之后**每加一档拉伸就补一次轻 NXT**(~0.35~0.4)。原理:噪声随拉伸逐级放大,边拉边压不让它累积;只在末尾重降一次要对付已被反复放大的噪声、还磨细节。IC1396 实测:交错 3 次(1 中等+2 轻)比末尾单次明显干净、细节不糊。所以下面阶段 C 的多步拉伸里要**穿插** NXT,别攒到最后。
5. **星云调色**:轻去绿(SCNR,清背景绿)+ 提饱和;可选 Hα 红强调(见下)。
6. **星点调色**:去绿 + 提饱和到 satMean 0.25~0.40。
7. **最后合成**:星云调色**全部完成后**,才把已调色星点 screen 合回。
8. **导出**:`inspect` op + `outputs.image`(扩展名决定格式,不改图),导全分辨率 PNG/TIFF。

**Hα 红强调(可选,发射星云)**:不是单纯提红,而是**先略降绿(为主)再略提红(为辅)**,
都小幅;用 **CIE L\* 分量当蒙版**(`redemph` 的 `ciel:true`,只作用星云亮区、背景不动)。
判据:调完后反射星云亮区仍是**近纯白→淡蓝**;若反射区被染红,说明红提过头。

## 常见坑(都踩过,别再犯)

- HT 不动:用了死 midtones + 高光卡 1.0,而数据 max 很低 → 拉伸区间几乎空。用自适应
  midtones 或确认数据范围。
- 被忠实预览假象骗:见铁律 2。
- 核心发平:全局压缩曲线把核心塞进窄输出带 → 用 lhe 空间局部处理,别加大全局压缩。
- 分层:硬阈值蒙版 → 换平滑连续蒙版(铁律 7)。
- 星点又细又硬:在欠拉伸图上分星 + 单独硬裁 → 用正确星点流程(流程骨架 2)。
- 背景/角落偏色:**治本**——`polybg`(逐通道低阶多项式,deg2)或更强 ABE(deg5+放宽 tol),
  **不是常规 SCNR**(铁律 9/11)。"亮源旁角落"色梯度尤其要 polybg,ABE 会欠拟合。
- 成片背景**均匀偏色**(如整体偏蓝,非局部梯度):**再跑一次 `gradient` method=GradientCorrection**
  即可校成中性(用户常规做法,IC1396 验证有效;副作用是外围略偏暖)。**BN(colorcal method=bn)
  在星云填满画面时几乎无效**(采不到干净背景)→ 优先 GC。**判偏色看预览/逐通道颜色,别看
  `bgstats`——它只给亮度网格,GC 前后亮度几乎不变会让你误判"没效果"**(其实颜色已校)。
- 深数据外围被压黑(暗云气/淡反射不见):套了浅数据的"压背景"思路 → 改"揭示"(铁律 10)。
- 改了 job-runner.js 没重载:必须"杀干净+冷启"(见上)。后台跑 python 记得先 `cd` 到 pipeline 目录。
- 大图(26MP)每步慢:BXT/solve/SPCC/SXT/LHE/denoise 都用后台跑。
- 后台 Python 脚本 `import orchestrator` 失败:后台子 shell 不继承 cwd → 脚本首行写死
  `sys.path.insert(0, r"E:\AutoClick\pipeline")`,别只靠 cd。
- GraXpert CLI 报 `-ai_version invalid version`:不接受 "latest",要 n.n.n。`graxpert.py` 现已
  自动探测本地 bge 模型版本(`bge-ai-models/<n.n.n>`);手调时传实际版本如 `1.0.1`。
- 弥散大视场发射星云(IC1396):无紧凑亮核,`coreContrast.std` 天然偏低(非缺陷,别硬提);
  用 curves `points` 做"揭示"色调映射,深数据把 faint 提到 ~0.37、background ~0.12(对照参考,铁律 13)。
- 折射镜(如智能望远镜)无衍射星芒,星点去绿 OK;牛反有绿色星芒时别对星点重度去绿。
- **判星点偏绿用了默认 p90 分位** → 星点图 90% 像素≈0,量的全是噪声(实测同一张图 p90 给
  greenFrac 0.409"该去绿"、p999 给 0.357"不该去")。星点图一律 `lumprobe params.colorPct=0.999`。
- **"用户说背景噪点多"就开大全图降噪** → 星云内部结构一起被抹平,成片核心变死板色块(铁律 20)。
- **在已自适应拉伸过的图上再套别人的 midtones** → 双重拉伸,主体动态范围 <0.15(铁律 21)。
- **`starsep` 传 `params.mask` 没用**:SXT/BXT 不认 PixInsight 视图蒙版 → 用 `maskblend` 手动混合。
- **`bgneutral` 只吃彩色图**(它按通道采四角):单通道要做背景平移,用 `curves points`
  `[[0,0],[当前背景,目标背景],[1,1]]`。

## 参考文件指引

- **`references/pipeline-ops.md`** —— job-runner 全部 op 的名称、参数、用途、推荐值。
  要提交任何任务前先查这里确认 op 名和参数。
- **`references/emission-nebula.md`** —— M42 型明亮发射星云**完整分步配方**(确切参数、正确星点
  工作流、亮核 HDRMT、调色判据、mono RGBH+Hα 增强)。
- **`references/galaxy.md`** —— 星系(M31 型):不提红、黄核蓝臂、自然色的流程与判据。
- **`references/reflection-ghs.md`** —— 极暗反射星云(IC4592 蓝马头):GHS 揭示 + 尘埃 GHS 增强
  + polybg 治角落色梯度 + 蓝反射判据。
- **`references/mono-rgbh.md`** —— 黑白相机 RGB(+Hα)完整流程(逐通道校准、独立 Hα 层非线性红增强)。
- **`references/helix-c63-recipe.md`** —— **C63 螺旋星云(行星状星云)完整配方:19 步通道处理 + 合成后 5 步精细调色**(用户手把手,含实测参数):RGB 只出星点;**星点蒙版保护彗状结节**(窄带里的类星点真实结构别被 SXT 抹掉,且 `starsep` 的 mask 无效→用 `maskblend`);逐通道手工分级;动态 HOO 合成。调色部分是**通用手法**:**逐通道曲线把背景归中性灰(每通道在自己的背景电平放点 + 0.65 锚点钉高光)**、SII 当蒙版染黄内圈、**`huemask` 色相蒙版**只改核心蓝/外围红、**跨图移植色彩目标要移植"目标色占比+亮度变化率"而非逐通道增益**、取样用 p98 色相核心。同时记录了三个上游错误(全图降噪毁结构 / 双重拉伸 / 改了电平没改合成增益)。
- **`references/sho-narrowband.md`** —— SHO 窄带(星云)+ RGB(星点)合成:**合成前各通道先拉伸对齐背景**(最关键)、去星揭示别拉没、哈勃调色(redemph 暖化/保 OIII 蓝体)、chanmix/dynpalette 新 op、短轨迹漏检诊断、RGB 星点 SPCC。SH2-132 验证。
- **`references/wbpp-stacking.md`** —— **后期的前置步骤**:多晚 WBPP 叠加(自定义滤镜标签法一次跑=按晚平场+统一对齐,含改副本三处 + 最大的坑)+ 整合去线/去带(卫星/飞机线、电线投影宽带的剔除法配方与"按线形态分流"判断)。

已验证 7 类目标(M42 暗核/亮核、IC434 马头、M20 三叶、M31 星系、M8 mono RGBH、IC4592 反射);
后续扩展(SHO / OSC 双窄带 / 多日窄带)在 references/ 下逐条新增。
