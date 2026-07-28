# 黑白相机 RGB(+Hα)完整流程(用户手把手,M8 验证)

黑白(mono)相机分通道拍 R/G/B(+可选 Hα)。核心原则:**校准与梯度必须逐通道、在合成之前做**;
Hα 作为独立高对比层在**非线性域**增强红信号(不是线性 hablend)。参数以 M8(2600MM,Antlia V 系滤镜)为例。

## 分步流程

1. **STF 拉伸逐通道看**:先用 STF 拉伸,逐通道观察梯度与星点情况(诊断,不烘焙)。
2. **逐通道 BXT**:对**每个通道 master** 各跑一次 BXT(反卷积 + 修星点)。**不要**在合成后对整图做——mono 每通道 PSF 不同,必须分通道。
3. **逐通道梯度**:**GraXpert → GC 二次**(用户的方法,治本除背景色梯度)。**逐通道、合成之前**做。
   - **GraXpert 调用方式(重要)**:PI 的 GraXpert **进程 headless 跑不通**(`new GraXpert` 设 appPath/replaceImage 仍空操作)→ 必须走 **CLI 子进程**:`orchestrator/graxpert.py` 的 `background_extraction(inp, out_noext)`,内部调
     `GraXpert.exe -cli -cmd background-extraction -correction Subtraction -smoothing 0.3 -gpu false -ai_version latest -output <out> <in>`(本地 AI 模型,读写 .xisf;-output 会自动加 .xisf,别带扩展名)。路径在 config 的 `graxpert_path`。
   - GraXpert 后再 `gradient` method=GradientCorrection(GC 二次)。M8 验证:逐通道 GraXpert→GC 后,合成图背景四角 greenFrac 0.31~0.34(中性),**绿彻底治住、零 SCNR**。
   - 若没配 GraXpert:退而用 GC→ABE(deg4~5),残留再 `polybg`。
4. **ChannelCombination** 合成 RGB(job-runner 的 `rgbcombine`,params.r/g/b)。
5. **ImageSolver** 解析(`solve`),供 SPCC。
6. **SPCC 色彩校准**:选对相机(2600MM)与滤镜(此例 **Antlia V 系**)。
   - **产品化**:滤镜让用户填;拿不准用默认,影响不大。
7. **拉伸(两选一,默认 b)**:先 STF 看效果(应已很好)。然后:
   - (a) 直接 `SXT` 分星 → 用"保持当前拉伸把星点图转非线性"(见 SKILL 流程骨架2)→ **星点更亮**;
   - **(b)【推荐】** 用 `HT` 拉到 **亮度范围占直方图 X 轴约 1/4、峰值在约 1/8** 处 → 跑一遍 `NXT` 降噪 → 再 `SXT` 分星 → **星点略暗但更自然**。
   - 两者都行,默认走 (b)。(htstretch 的 midtones/shadow 调到该直方图位置;可用 `lumprobe` 核对 p50/峰值位置。)
8. **Hα 层准备(独立处理)**:对 Hα 通道:`HT` 拉伸 → `SXT` 去星 → `NXT` 降噪 → **`CT`(curves)把背景压到最暗、同时保住亮部亮度**(得到高对比的 starless Hα 层,亮部结构清晰、背景近黑)。
9. **Hα 增强红信号**:用备好的 Hα 层,对 **starless RGB** 在**非线性域**增强 Hα(红)信号(相当于把 Hα 结构叠进 R/发射区,强化 Hα)。
   - 对应 op:`hablend`(把 Ha 相对自身背景的发射超出量加进 R)——注意此处 Ha 用的是**步骤8备好的高对比 starless Hα**、在非线性域,而非线性原图。
10. **starless 微调**:`CT` 调对比度 / 饱和度 / 亮度到位。
11. **合星出图**:提星点饱和 → `recombine` 合并 starless + 星点 → 导出。

## 关键纠正(相对"合成后整图处理"的错误做法)
- **校准/梯度逐通道 + 合成前**(步骤2/3):不是合成后对整图 BXT/ABE。
- **默认走步骤7的 (b)**:HT 到固定直方图位置(范围1/4、峰值1/8)+ NXT 再分星,而不是直接 STF 分星。
- **Hα 先做成"去星+背景压暗+保亮部"的高对比层**,再在非线性增强红;不要用线性原始 Hα 直接 hablend。

## 与 OSC 发射星云的关系
拉伸/降噪/调色/合星的后半段判据与 `emission-nebula.md` 一致(红脊 Hα、反射白蓝、背景中性);
mono 的特殊性在前半段:**分通道校准 + 独立 Hα 层 + 非线性红增强**。
