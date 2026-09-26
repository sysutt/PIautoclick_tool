# TTAstroPiLot —— 深空天文照片自动后期系统

> 本项目的主体是**深空照片全自动后期处理系统**,位于 [`pipeline/`](pipeline/)。
> 仓库根目录里那个 `pixinsight_auto_clicker.py`(弹窗点击器)是**早期的小工具**,
> 现在只是 pipeline 的一个历史旁支,**不是项目主体** —— 见文末 §6。

---

## 1. 这个项目是什么

把深空拍摄的线性 master 图,自动处理成可交付的成片。两条并列的技术路线:

| 路线 | 做法 | 状态 |
|---|---|---|
| **PI 链** | 驱动常驻 PixInsight 的 PJSR 脚本,走 r00→r14 共 60+ 个落盘节点(BXT/NXT/SXT/SPCC/GHS…) | **主力**,用户定的优先级是"先把 PI 管线彻底走顺" |
| **零 PI 链** | 完全不用 PixInsight:Siril + StarNet2 + GraXpert/DeepSNR(`stack_engine` / `rgb_engine` / `hoo_engine` / `sho_engine` / `rgb_ha_engine`) | 可用,但 Siril 侧押后 |

两者之上有**质量闭环**:确定性指标(`quality.py`)→ LLM 评委(`critic.py`)→ 成片质量门
(只回退重跑,**不是改成片**)→ 轻量原位补救。

**产品目标是零起点可用**:即使没有用户的私有素材库与手工预设,也要达到用户手工后期水准。
(这条标准的具体含义与当前差距,见 `.claude/skills/deepsky-postprocess/SKILL.md`)

---

## 2. 真正的运行规范在这里(先读这三份,别只读 README)

| 文件 | 内容 |
|---|---|
| [`.claude/skills/deepsky-postprocess/SKILL.md`](.claude/skills/deepsky-postprocess/SKILL.md) | **23 条铁律** —— 改这个项目之前必须读 |
| [`.claude/skills/deepsky-postprocess/references/pipeline-ops.md`](.claude/skills/deepsky-postprocess/references/pipeline-ops.md) | 全部 job-runner `op` 与参数 |
| [`docs/自动后期处理-技术方案-v1.md`](docs/自动后期处理-技术方案-v1.md) | 设计文档 |

> 本 README 的职责是**指路**,不是复述细节。细节以那三份为准。

---

## 3. 快速上手

### 3.1 启动 GUI(日常唯一入口)

```powershell
pipeline\TTAstroPiLot.cmd          # = cd pipeline && python -m orchestrator.app_ui
```

> ⚠️ 该 `.cmd` **必须保持纯 ASCII** —— 含中文会被 cmd 按 GBK 拆行。

GUI 启动时会自动跑 `housekeep.startup_maintenance()`(清 `%TEMP%\_MEI*` 与 `_run` 顶层超期中间图)。

### 3.2 无素材自检(强烈建议接手第一件事)

```powershell
cd pipeline
python -m orchestrator.p0_demo --op probe        # 探测 PI 已装模块(BXT/SXT/NXT/StarNet/GraXpert…)
python -m orchestrator.p0_demo --op selftest     # 合成图跑通「统计+预览导出」,无需素材
python -m orchestrator.p0_demo --op inspect --input "M:/.../masterLight.xisf"
```

看到 `status: ok` + 逐通道统计 + `_run/preview_selftest.png` 才算链路通。

> ⚠️ **`probe` 要确认模块真的注册上了**,不能只看文件在不在 ——
> PI 升级后出现过 DLL 还在但 `typeof == "undefined"` 的静默失效。

### 3.3 命令行跑一整条(无需 GUI)

```powershell
cd pipeline
python -m orchestrator.pipeline --input "<线性 master.xisf>" --rgb
python -m orchestrator.pipeline --input "<线性 master.xisf>" --hoo
python -m orchestrator.pipeline --input "<registered 目录>" --lrgb
python -m orchestrator.pipeline --input "<x.xisf>"        # 不带动词 = 固定三步:裁黑边→梯度→拉伸
```

### 3.4 改动的生效边界(必须记住)

| 改了什么 | 需要做什么 |
|---|---|
| `pipeline.py` / UI | **重启 GUI** |
| `recombine.py`(Python worker) | 重启 App 即可 |
| **`job-runner.js`** | **必须冷启 PI**(`-r=` 只在启动时载入一次) |

冷启 PI runner:
```powershell
Get-Process PixInsight -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 3
Remove-Item pipeline\_run\runner.heartbeat -Force
& "<PixInsight.exe>" -n "-r=<仓库路径>\pipeline\job-runner.js"
```

GUI 底栏有「↻ 重载 runner」;`_ensure_runner` 见 runner 不在线会**自动冷启**。
⚠️ **zero-PI 流程绝不能拉 PI**(否则会冷启动 PI 空等)。

---

## 4. 目录结构

```
AutoClick/
├── pipeline/                       ← 主体
│   ├── job-runner.js               常驻 PixInsight 的作业派发脚本(PJSR)
│   ├── TTAstroPiLot.cmd            GUI 启动器
│   ├── solve.js                    本地天文解析(ImageSolver 库模式)
│   ├── orchestrator/               Python 编排器(40+ 模块)
│   │   ├── app_ui.py               PyQt5 GUI,唯一入口
│   │   ├── pipeline.py             管线编排(run_rgb / run_hoo / run_lrgb / run_sho /
│   │   │                           run_integrate / run_wbpp_stack / run_detrail / run_cull)
│   │   ├── quality.py              确定性指标
│   │   ├── critic.py               多模态 LLM 评委
│   │   ├── recombine.py            合成 / 色彩还原(基座剥离等)
│   │   ├── watchdog.py             看门狗(弹窗+卡死+崩溃自愈)
│   │   ├── housekeep.py            启动维护
│   │   ├── colorexp.py             调色经验库
│   │   └── *_engine.py             零 PI 引擎
│   ├── wbpp_custom/                WBPP 定制(叠加)
│   ├── pjsr/                       PJSR 资源
│   ├── _config/                    用户配置(gitignore:settings.json / color_presets.json /
│   │                               color_experience/ / house_colors/ / ref_colors/)
│   └── _run/                       运行时交换目录(gitignore;inbox/processing/done、runner.heartbeat)
├── .claude/skills/deepsky-postprocess/   ← 运行规范(见 §2)
├── docs/
├── design/
├── pixinsight_auto_clicker.py      ← 早期弹窗点击器(旁支,见 §6)
└── README.md
```

**关键路径**

| 用途 | 路径 |
|---|---|
| 成品 | `M:/Deepsky/<YYMMDD_CAM_TARGET>/` |
| 导出 | `M:/deepsky_output/...` |
| 交换目录 | `pipeline/_run/` |

---

## 5. 重要约定(改代码前必读)

1. **`status=ok` 不代表这一步做成了。** 本项目最高频故障是**静默失败** ——
   插件缺失时"优雅跳过"却返回 ok,整条链拿没处理的图继续跑。
   判活必须看**产物**,并挑一个"没做成时必然不同"的量。
2. **改完先问要不要上线。** "上线"在本项目的含义是:重启 GUI / 冷启 PI / commit&push。
3. **不要 `git add -A`** —— 树下有数 GB 中间产物。
4. **别把带进度条的 CLI 输出无过滤重定向到文件** —— 历史上单文件日志涨到 93GB 差点塞满 C 盘。
5. **零 PI 侧未提交的在途改动不要动**(`rgb_engine.py` 等,用户明确说过保持原样)。
6. **判据不许依赖用户的私有素材库**(`M:/deepsky_output`),否则它验证的只是这台机器。
7. **PI 退出时会用内存里的设置整个重写 `PixInsight.ini`** —— 开着改等于白改。

---

## 6. 早期小工具:`pixinsight_auto_clicker.py`(旁支)

> **它不是项目主体,与 pipeline 相互独立。** 保留在此仅因历史原因。

自动点掉 PixInsight `AnnotateImage` 反复弹出的
*"Label placement optimization is taking a long time…"* 确认框,
并在出现"另存为"对话框时自动停止。

```bash
pip install pywin32 PyQt5 uiautomation
python pixinsight_auto_clicker.py        # 或双击 run.bat
pyinstaller PixInsightAutoClicker.spec   # 打包 → dist/PixInsightAutoClicker.exe
```

相关文件:`pixinsight_auto_clicker.py`(主程序)、`uia_debug.py`(控件树调试)、
`run.bat`、`build.bat`、`PixInsightAutoClicker.spec`。

> 其思路已被 `pipeline/orchestrator/popup_guard.py` 与 `watchdog.py` 吸收 ——
> 新工作应改那两处,不要再扩这个独立脚本。

---

*最后核对:2026-09-27。本 README 由接手 agent 依据磁盘实测结构重写;
此前的版本仍在描述"弹窗点击器"并声称"当前进度 P0",已过期。*
