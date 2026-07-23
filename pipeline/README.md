# 深空自动后期处理系统 · pipeline

本目录是「脚本执行 + AI 评估 + 闭环决策」自动后期系统的实现,与仓库根部的
`AutoClick`(弹窗守卫)相互独立。设计详见 [`docs/自动后期处理-技术方案-v1.md`](../docs/自动后期处理-技术方案-v1.md)。

> **当前进度:P0** — 打通最小执行链路:
> Python 编排器下发 job → PixInsight 常驻脚本执行 → 回收指标 JSON + 预览 PNG。

## 目录结构

```
pipeline/
├── job-runner.js          # 常驻 PixInsight 的作业派发脚本 (PJSR)
├── orchestrator/          # Python 编排器
│   ├── config.py          #   路径 / PixInsight 定位
│   ├── protocol.py        #   job/result 文件交换协议
│   └── p0_demo.py         #   P0 端到端演示入口
└── _run/                  # 运行时交换目录(自动创建,不纳入版本控制)
    ├── inbox/  processing/  done/
    └── runner.heartbeat
```

## 交换协议(文件级 IPC)

| 方向 | 位置 | 说明 |
|---|---|---|
| 下发 | `_run/inbox/<job_id>.json` | 编排器原子写入(先 `.tmp` 再 rename) |
| 处理中 | `_run/processing/<job_id>.json` | runner 领取后移入 |
| 回收 | `_run/done/<job_id>.json` | 执行结果(指标 / 预览 / 错误) |
| 判活 | `_run/runner.heartbeat` | runner 每轮写入毫秒时间戳 |
| 停止 | `_run/STOP` | 放入该文件令 runner 优雅退出 |

P0 支持的 `op`:
- `probe` — 探测已安装的处理模块(BXT/SXT/NXT/StarNet/GraXpert 等)。
- `selftest` — 内部生成合成图,验证「统计 + 预览导出」全链路,**无需任何素材**。
- `inspect` — 打开指定图像,输出统计指标 + 自动拉伸预览 PNG。

## 运行步骤

### 1. 启动常驻 runner(在 PixInsight 内)
打开 PixInsight → **SCRIPT ▸ Execute Script File...** → 选择 `pipeline/job-runner.js`。
控制台出现 `[job-runner] started. watching ...` 即为就绪,保持该脚本运行。

> 命令行等效:`PixInsight.exe -r="<仓库路径>/pipeline/job-runner.js"`

### 2. 提交 job(在终端,pipeline/ 目录下)
```bash
# 最小自测,无需素材
python -m orchestrator.p0_demo --op selftest

# 探测本机已装模块
python -m orchestrator.p0_demo --op probe

# 检查一张真实主图
python -m orchestrator.p0_demo --op inspect --input "D:/astro/master.xisf"
```

`--launch` 可尝试自动启动 PixInsight 并加载 runner(需能定位 `PixInsight.exe`,
或设置环境变量 `PIXINSIGHT_EXE`)。

### 3. 停止 runner
在终端:`python -c "from orchestrator import protocol; protocol.request_stop()"`,
或直接在 PixInsight 控制台点击 **Abort**。

## 预期输出(selftest)
`p0_demo` 打印 job 状态、逐通道统计(median/mean/stdDev/min/max),并给出
预览 PNG 路径(`_run/preview_selftest.png`)。看到 `status: ok` + 合理统计值 +
可打开的预览图,即代表 P0 链路打通。

## 说明
- 预览用经典 STF AutoStretch(阴影裁剪 −2.8σ、目标背景 0.25)生成,仅供观看,
  不改动数据(在副本上拉伸)。对应技术方案 §3.4「预览渲染标准化」。
- 本阶段无任何决策逻辑;闭环评估与调参在后续 P2/P3 阶段实现。
