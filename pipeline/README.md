# pipeline —— 深空自动后期处理系统(主体)

> 本目录是 TTAstroPiLot 的核心。**唯一日常入口是 PyQt5 GUI**,
> 由它把重活交给 Python 编排器,再由编排器驱动常驻 PixInsight 的 PJSR 脚本。
>
> 运行规范(23 条铁律)在 [`../.claude/skills/deepsky-postprocess/SKILL.md`](../.claude/skills/deepsky-postprocess/SKILL.md),
> `op` 全表在 [`../.claude/skills/deepsky-postprocess/references/pipeline-ops.md`](../.claude/skills/deepsky-postprocess/references/pipeline-ops.md)。
> 本文件只讲**结构、入口、验证方式**。

---

## 1. 三层结构

```
TTAstroPiLot.cmd → python -m orchestrator.app_ui          (PyQt5 GUI,唯一入口)
   │
   ├── orchestrator/pipeline.py      编排:run_rgb / run_hoo / run_lrgb / run_sho /
   │                                 run_integrate / run_wbpp_stack / run_detrail / run_cull
   │                                 + DECISION_POINTS(分步岔口)
   │
   ├── job-runner.js                 常驻 PixInsight 的 PJSR 脚本(for(;;)+msleep 阻塞轮询,
   │                                 占 PI 主线程;写 runner.heartbeat)
   │
   └── 零 PI 引擎:stack_engine / rgb_engine / hoo_engine / sho_engine / rgb_ha_engine
```

**GUI 自身不算数** —— 它只负责选流程/参数、进度、预览、评分卡、导出、调色面板、
岔口面板;所有重活都丢给 `Worker` 线程 → `pipeline.run_*` → `protocol.submit/wait_result`。

### PI 链的落盘节点(r00 → r14)

一轮 `run_rgb` 会落 60+ 个节点图。真实顺序(可对照 `_run/` 的 mtime):

```
_sess_masterLight → integrated_master
→ r00_crop → r00b_edgecrop → r01_gc(BXT) → r02_deconv → r02b_solve
→ r03s_starcal / r03b_nostarcc / r03_colorcal(SPCC) → r04a_galgx
→ r05_dn(NXT) → r06_str → r06c_starchroma → r07_stars / r07_sep(SXT)
→ r07b_galgc → r08_ghs → r08b_reghs → r09_dn2 → rG_hdr / rG_hdrblend
→ r10_depurple / r10_scnr → r11_neb → r11b_lhe → rG_usercolor(用户调色面板)
→ r11e_finalclean → r11g_starneutral → r12a/r12b/r12e/r12f → r12_stars
→ r13_recomb(合星) → r13b_galbg/galpin → r14_final → r14f_bgchroma
```

### 质量闭环在哪

`quality.py`(确定性指标)→ `critic.judge_field_extended`(LLM 判场)
→ `run_rgb` 末尾质量门(`_quality_retry`,**只回退一次,回退整条重跑,不是改成片**)
→ 轻量原位补救按钮「🔧 按评分优化」(`_apply_score_remedy`,纯 numpy,不需要 runner)。

---

## 2. 运行

### 2.1 启动 GUI(日常唯一入口)

```powershell
TTAstroPiLot.cmd                      # = cd pipeline && python -m orchestrator.app_ui
```

> ⚠️ **该 `.cmd` 必须保持纯 ASCII** —— 含中文会被 cmd 按 GBK 拆行。
> 启动时自动跑 `housekeep.startup_maintenance()`。

### 2.2 命令行跑一整条(无需 GUI)

```powershell
python -m orchestrator.pipeline --input "<线性 master.xisf>" --rgb   [--ghs-d 0.5 --neb-sat 0.15 --stars]
python -m orchestrator.pipeline --input "<线性 master.xisf>" --hoo
python -m orchestrator.pipeline --input "<registered 目录>" --lrgb [--ha 0.0 --ms-iters 2 --core-thr 0.7]
python -m orchestrator.pipeline --input "<x.xisf>"          # 不带动词 = 固定三步:裁黑边→梯度→拉伸
```

> 脚本首行务必 `sys.path.insert(0, r"<仓库路径>\pipeline")` —— 后台子 shell 不继承 cwd。

### 2.3 无素材自检

```powershell
python -m orchestrator.p0_demo --op probe        # 探测 PI 已装模块
python -m orchestrator.p0_demo --op selftest     # 合成图跑通「统计+预览导出」,无需素材
python -m orchestrator.p0_demo --op inspect --input "M:/.../masterLight.xisf"
python -m orchestrator.p0_demo --op selftest --launch   # 顺带自动拉起 PI+runner
```
预期:`status: ok` + 逐通道统计 + `_run/preview_selftest.png`。

### 2.4 跑单个阶段

```python
from orchestrator import protocol
job = protocol.new_job("lumprobe", input=".../r14_final.xisf",
                       params={"colorPct": 0.999}, outputs={"preview": ".../T.png"})
protocol.submit(job); r = protocol.wait_result(job["job_id"], timeout=180)   # r["status"]=="ok"
```
**op 名/参数/推荐值一律先查 `references/pipeline-ops.md`。**

### 2.5 看门狗(跑任何 PI 步骤前先起)

```powershell
python -m orchestrator.watchdog            # 常驻;--dry-run 只观察
```
停止:在 `_run` 放 `STOP_WATCHDOG`。
⚠️ 看门狗会**自动点掉 PI 弹窗** —— 你自己手动开 PI 干活时会被它干扰,记得先停。

### 2.6 冷启 / 重载 PI runner(改了 `job-runner.js` 之后必须)

```powershell
Get-Process PixInsight -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 3
Remove-Item _run\runner.heartbeat -Force
& "<PixInsight.exe>" -n "-r=<仓库路径>\pipeline\job-runner.js"      # ~18-22s 上线
```
GUI 底栏有「↻ 重载 runner」;`_ensure_runner` 见 runner 不在线会**自动冷启**。

> ⚠️ **zero-PI 流程绝不能拉 PI**(`_run` / `Worker.run` 两处旁路),
> 否则会冷启动 PI 空等 90s。

---

## 3. 改动后的生效边界

| 改了什么 | 需要做什么 |
|---|---|
| `pipeline.py` / UI | **重启 GUI** |
| `recombine.py`(Python worker) | 重启 App 即可 |
| **`job-runner.js`** | **必须冷启 PI**(`-r=` 只在启动时载入一次) |

> ⚠️ **PI 退出时会用内存里的设置整个重写 `PixInsight.ini`** —— 开着改等于白改。

---

## 4. 交换协议(文件级 IPC)

| 方向 | 位置 | 说明 |
|---|---|---|
| 下发 | `_run/inbox/<job_id>.json` | 编排器原子写入(先 `.tmp` 再 rename) |
| 处理中 | `_run/processing/<job_id>.json` | runner 领取后移入 |
| 回收 | `_run/done/<job_id>.json` | 执行结果(指标 / 预览 / 错误) |
| 判活 | `_run/runner.heartbeat` | runner 每轮写入毫秒时间戳 |
| 停止 | `_run/STOP` | 放入该文件令 runner 优雅退出 |
| 崩溃 | `_run/crash.log` | faulthandler 转储 |

---

## 5. ⚠️ 怎么验证(本项目**没有测试套件**)

**实测:全周 13 份会话记录里没有任何 `pytest`,也没有 `python -m orchestrator.<子命令>`
(除 `app_ui` / `watchdog`)。** 没有持久化测试套件。

实际可行的验证方式只有三种:

1. **真机跑一轮** + 用 `xisf`/PIL **逐节点量 `_run/<tag>.xisf`**(r00…r14f 全量 tag 见 §1)
2. **语法门**:`py_compile` / `ast.parse`
3. **离屏 `AppWindow` 冒烟**:`QT_QPA_PLATFORM=offscreen` + `WA_DontShowOnScreen`
   ⚠️ 注意:Worker 线程里弹 modal `QMessageBox` 会 **segfault exit 139**,那是离屏假象
4. 另有 `python -m orchestrator.ui_shot`(在仓库根下跑):离屏 3 尺寸 × 2 主题截图到 `_shots/`,
   用来核「没有控件被裁」

### 判断「这一步到底做没做」—— 唯一可信来源

| 手段 | 说明 |
|---|---|
| **`_run/done/<job_id>.json` 的 `applied` 字段** | **唯一可信来源**(`grep done/*.json`) |
| 逐节点 `max\|A−B\|` | BXT 0.163 = 做了 / SXT 0.00000000 = 没做(`applywcs` 的 0 是正常的) |
| starsep 另看 `starsFound` + **耗时** | 正常 12-16s,**2-3s 就是没跑** |
| solve | 看 `checksolve.hasSolution`,**别信 solve 自己的 ok** |

> **`status=ok` 只说明那段代码没抛异常,不说明它做成了事。**
> 本项目最高频故障就是这一族(SXT 缺插件时返回原图却报 ok,整链拿没去星的图继续跑)。

---

## 6. 目录约定

| 路径 | 内容 | 版本控制 |
|---|---|---|
| `orchestrator/` | Python 编排器(40+ 模块) | ✅ |
| `job-runner.js` | PJSR 常驻脚本 | ✅ |
| `wbpp_custom/` | WBPP 定制(叠加) | ✅ |
| `_config/` | 用户配置(settings.json / color_presets.json / color_experience/ / house_colors/ / ref_colors/) | ❌ gitignore |
| `_run/` | 运行时交换目录(inbox/processing/done、heartbeat、STOP、crash.log) | ❌ gitignore |
| `_t/` | 手工对照产物 | ❌ gitignore |
| `_projects/` `_style_cal/` | 工程文件 / 风格标定 | 视情况 |

**成品** → `M:/Deepsky/<YYMMDD_CAM_TARGET>/`;**导出** → `M:/deepsky_output/...`

⚠️ `_run` 可达 10GB+,且是**全局共享、跨目标复用、无 per-run 隔离** ——
跨轮复用中间结果**必须先核 mtime**、消费前**必须核几何**。

---

*最后核对:2026-09-27。本 README 由接手 agent 依据磁盘实测结构重写;
此前的版本写着「当前进度:P0」并只描述了最小链路,已过期。*
