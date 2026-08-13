"""无 PI 纯 RGB 引擎(zero-PixInsight broadband RGB pipeline)。

从 OSC 单张 master(智能望远镜/彩色相机)到彩色成片,**全程不碰 PixInsight**,
用 Siril + DeepSNR + numpy。Seestar S30 M42 真机验证(2026-08-13)。见 [[rgb-zeropi-engine]]。

管线(每步都有踩坑固化):
  ① 色彩校准:**真 SPCC**(装了 Siril 本地 Gaia 星表则 platesolve+spcc,与 PI 同源、色彩权威;
     见 [[siril-offline-spcc]]);无星表则退**部分星场白平衡**近似。校准在**线性、拉伸前**。
  ② 拉伸:`autostretch -linked`(保通道平衡不产生色偏)+ 可选 **GHS(ght)压亮核**(HDR)。
  ③ 背景中性化(拉伸后微调)+ 压黑。
  ④ **带主体蒙版降噪**(DeepSNR 全图 → 按星云蒙版混:背景强/星云轻,保尘埃结构)。
  ⑤ 温和饱和。

【铁律】
- **别用 Durand TM + CLAHE 做 HDR**:实测过度处理、核心发假发硬(用户否掉)。用 Siril 原生 GHS(ght)在拉伸阶段压核,干净。
- **autostretch 必须 -linked**:各通道同一 MTF → 保 SPCC 通道平衡;unlinked 会让背景发偏色。
- 全图降噪会把星云内部结构抹成死板色块 → 必挂主体蒙版(见 [[pi-denoise-background-mask]])。
- 星场白平衡兜底:发射星云区满天弥漫 Ha 污染星样本 → 白平衡只做部分(WBS≈0.5)否则把 Ha 红压成土褐。
- SPCC 传感器名/滤镜名的引号要**包整个** `-arg=value`(Siril 坑)。
"""
from __future__ import annotations

import glob
import os
import subprocess

import numpy as np
try:
    import cv2
except Exception:
    cv2 = None
try:
    from scipy.ndimage import gaussian_filter
except Exception:
    gaussian_filter = None
from PIL import Image

from . import config, siril
from .sho_engine import stack_registered, detect_crop, neutral_gray   # 复用整合/裁边/中性灰

# 预设:一组旋钮 = 一个 palette。RGB 调色比 SHO 简单(SPCC 给物理正确色,只调 HDR/饱和)。
PRESETS: dict[str, dict] = {
    # 自然:SPCC 权威色 + 温和 GHS 压核 + 温和饱和。多数宽带目标(星系/发射反射星云)默认。
    "natural": dict(hdr="ght", sat=1.15, green=0.0, stretch_bg=0.16),
    # 浓郁:饱和更足(展示用)。
    "vivid":   dict(hdr="ght", sat=1.30, green=0.0, stretch_bg=0.16),
    # 平拉:关 HDR(纯 autostretch),亮核会稍爆但最干净;暗弱目标(核心不爆)用。
    "flat":    dict(hdr="off", sat=1.15, green=0.0, stretch_bg=0.14),
}

# GHS 压亮核参数(温和;别过度否则发假)。在 autostretch 之后施加,压 SP 附近的亮核区。
_GHT = "ght -D=0.9 -b=6 -SP=0.55 -HP=0.75"


# ── 工具 ─────────────────────────────────────────────────────────────────────
def _lum(x: np.ndarray) -> np.ndarray:
    return 0.30 * x[..., 0] + 0.59 * x[..., 1] + 0.11 * x[..., 2]


def _smooth(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _rd(p: str) -> np.ndarray:
    a = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    return cv2.cvtColor(a, cv2.COLOR_BGR2RGB).astype(np.float32) / (65535.0 if a.dtype == np.uint16 else 255.0)


def _nebmask(proc: np.ndarray) -> np.ndarray:
    """主体(星云/星系)蒙版:大尺度亮度平滑 → 归一 → 平滑阶跃。用于带蒙版降噪。"""
    bl = _lum(proc)
    if gaussian_filter is not None:
        nb = gaussian_filter(bl, 20)
    else:
        nb = cv2.GaussianBlur(bl, (0, 0), 20)
    nb = (nb - nb.min()) / (nb.max() - nb.min() + 1e-6)
    return _smooth(nb, 0.10, 0.45)


def _bg_neutralize(proc: np.ndarray) -> np.ndarray:
    """背景色偏对齐(四角背景三通道对齐到最低,消色偏)。**不压黑点**——留给 neutral_gray 抬中性灰
    (深空铁律:背景绝不死黑)。"""
    h, w, _ = proc.shape
    bg = np.median(np.concatenate([proc[:int(h * .10), :int(w * .12)].reshape(-1, 3),
                                   proc[-int(h * .10):, -int(w * .12):].reshape(-1, 3)], 0), 0)
    out = proc.copy()
    for c in range(3):
        out[..., c] = np.clip(out[..., c] - (bg[c] - bg.min()), 0, 1)
    return out


# ── ① 色彩校准:SPCC 可用性 + 传感器识别 ──────────────────────────────────────
def _siril_config_path() -> str | None:
    d = os.path.join(os.environ.get("LOCALAPPDATA", ""), "siril")
    cfgs = sorted(glob.glob(os.path.join(d, "config.*.ini")))
    return cfgs[-1] if cfgs else None


def spcc_available() -> bool:
    """Siril 本地 Gaia 星表是否装好(config 两键指向存在的解析文件 + 含块的 SPCC 目录)。
    装法见 [[siril-offline-spcc]] / deps.py。"""
    cfg = _siril_config_path()
    if not cfg or not os.path.exists(cfg):
        return False
    astro = photo = None
    try:
        for line in open(cfg, encoding="utf-8", errors="ignore"):
            if line.startswith("catalogue_gaia_astro="):
                astro = os.path.expanduser(line.split("=", 1)[1].strip())
            elif line.startswith("catalogue_gaia_photo="):
                photo = os.path.expanduser(line.split("=", 1)[1].strip())
    except Exception:
        return False
    ok_a = bool(astro) and os.path.exists(astro) and os.path.getsize(astro) > 1e8   # 真星表 >100MB
    ok_p = bool(photo) and os.path.isdir(photo) and any(f.endswith(".dat") for f in os.listdir(photo))
    return bool(ok_a and ok_p)


def guess_sensor(path: str) -> tuple[str | None, str | None]:
    """从路径/文件名猜 SPCC 传感器+滤镜。Seestar 自带配置;其它 OSC 需调用方指定。
    返回 (oscsensor, oscfilter) 或 (None, None)。滤镜:IRCUT→UV/IR Block,LP→ZWO Seestar LP。"""
    n = str(path).lower()
    sensor = None
    if "s50" in n or "seestar_s50" in n:
        sensor = "ZWO Seestar S50"
    elif "s30" in n or "seestar" in n:
        sensor = "ZWO Seestar S30"
    if sensor is None:
        return None, None
    flt = "ZWO Seestar LP" if ("_lp" in n or "filter-lp" in n or "dualband" in n) else "UV/IR Block"
    return sensor, flt


def _star_wb(lin: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """兜底:部分星场白平衡(无 SPCC 时)。取最亮非星云像素(恒星)平均色 → 部分校成中性。
    只做部分(strength≈0.5)否则发射星云区的弥漫 Ha 污染星样本、把红压成土褐。"""
    L = _lum(lin)
    if gaussian_filter is not None:
        nb = gaussian_filter(L, 25)
    else:
        nb = cv2.GaussianBlur(L, (0, 0), 25)
    nb = (nb - nb.min()) / (nb.max() - nb.min() + 1e-6)
    cand = L.copy()
    cand[nb > 0.18] = 0                                  # 排除大尺度亮延展(星云)
    pos = cand[cand > 0]
    if pos.size < 500:
        return lin
    star = cand >= np.percentile(pos, 99.7)
    ref = lin[star].mean(0)
    scale = 1 + strength * (ref.mean() / (ref + 1e-6) - 1)
    return np.clip(lin * scale, 0, None)


def calibrate(master: str, out_noext: str, *, sensor: str | None = None,
              oscfilter: str | None = None, crop: str | None = None,
              do_spcc: bool = True, timeout: float = 1800.0, log=print) -> tuple[str, bool]:
    """线性色彩校准 → 保存校准图。返回 (路径, 是否用了真SPCC)。
    SPCC(装了本地星表 + 已知传感器):load→subsky→platesolve→spcc→存 .fit(32位,精度最好)。
    兜底:load→subsky→存 tif→numpy 部分星场白平衡→存 .tif。"""
    R = str(config.RUN_DIR)
    m = str(master).replace("\\", "/")
    out = str(out_noext).replace("\\", "/")
    for e in (".fit", ".fits", ".tif", ".xisf", ".png"):
        if out.lower().endswith(e):
            out = out[:-len(e)]
    if sensor is None:
        sensor, oscfilter = guess_sensor(master)
    pre = [f"cd {R}", f'load "{m}"'] + (["crop " + crop] if crop else []) + ["subsky 1"]

    if do_spcc and sensor and spcc_available():
        arg_s = f'"-oscsensor={sensor}"'
        arg_f = f'"-oscfilter={oscfilter or "UV/IR Block"}"'
        ok, logtxt = siril.run_script(pre + ["platesolve", f"spcc {arg_s} {arg_f}", f"save {os.path.basename(out)}_cal"],
                                      timeout=timeout)
        cal = f"{R}/{os.path.basename(out)}_cal.fit"
        if os.path.exists(cal) and "spcc" not in logtxt.lower().split("error")[0][-200:]:
            # 粗判成功:文件存在(spcc 失败 Siril 会中断不出文件)
            log(f"[rgb] [OK] 真 SPCC 校准(sensor={sensor} filter={oscfilter or 'UV/IR Block'})")
            return cal, True
        log(f"[rgb] SPCC 未成功,退回星场白平衡兜底")

    # 兜底:subsky + 部分星场白平衡
    siril.run_script(pre + [f"savetif {os.path.basename(out)}_lin"], timeout=timeout)
    lin = _rd(f"{R}/{os.path.basename(out)}_lin.tif")
    lin = _star_wb(lin, strength=0.5)
    cal = f"{R}/{os.path.basename(out)}_cal.tif"
    cv2.imwrite(cal, cv2.cvtColor((np.clip(lin / (lin.max() + 1e-6), 0, 1) * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))
    log(f"[rgb] [WB] 星场白平衡兜底(未用 SPCC:{'无本地星表' if not spcc_available() else '传感器未知'})")
    return cal, False


# ── ④ 带蒙版降噪 ─────────────────────────────────────────────────────────────
def masked_denoise(proc: np.ndarray, nebmask: np.ndarray, timeout: float = 1800.0) -> np.ndarray:
    """DeepSNR 全图降噪 → 按主体蒙版混(背景权重 0.9 / 星云 0.3),保星云结构。无 DeepSNR 则原样返回。"""
    if not siril.deepsnr_exe():
        return proc
    R = str(config.RUN_DIR)
    cv2.imwrite(f"{R}/_rgb_proc.tiff", cv2.cvtColor((proc * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))
    subprocess.run([siril.deepsnr_exe(), "-i", f"{R}/_rgb_proc.tiff", "-o", f"{R}/_rgb_proc_dn.png",
                    "-m", "2", "-s", "480", "-q"], capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(f"{R}/_rgb_proc_dn.png"):
        return proc
    dn = _rd(f"{R}/_rgb_proc_dn.png")
    w = (0.9 - 0.6 * nebmask)[..., None]
    return np.clip(dn * w + proc * (1 - w), 0, 1)


# ── 主编排器 ─────────────────────────────────────────────────────────────────
def run_rgb(master: str, out_noext: str, *, palette: str = "natural",
            hdr: str | None = None, sat: float | None = None, green: float | None = None,
            sensor: str | None = None, oscfilter: str | None = None,
            crop: str | None = None, stretch_bg: float | None = None,
            timeout: float = 1800.0, log=print) -> str:
    """无 PI 纯 RGB 全流程。master=OSC 单张整合 master。palette=PRESETS 键。返回成片 <out>.png。
    hdr: "ght"(GHS 压核)/"off"(纯 autostretch);sat/green/stretch_bg 覆盖预设。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python(cv2)")
    R = str(config.RUN_DIR)
    p = {**PRESETS[palette]}
    hdr = hdr if hdr is not None else p["hdr"]
    sat = sat if sat is not None else p["sat"]
    green = green if green is not None else p["green"]
    stretch_bg = stretch_bg if stretch_bg is not None else p["stretch_bg"]
    log(f"[rgb] palette={palette} hdr={hdr} sat={sat} green={green}")

    # ① 色彩校准(SPCC 或兜底)
    cal, used_spcc = calibrate(master, os.path.join(R, "_rgbcal"), sensor=sensor,
                               oscfilter=oscfilter, crop=crop, timeout=timeout, log=log)

    # ② 拉伸:autostretch -linked(+ 可选 GHS 压核)
    st_cmds = [f"cd {R}", f"load {os.path.basename(cal).rsplit('.', 1)[0]}",
               f"autostretch -linked -2.8 {stretch_bg}"]
    if hdr == "ght":
        st_cmds.append(_GHT)
    st_cmds.append("savepng _rgb_st")
    siril.run_script(st_cmds, timeout=timeout)
    proc = _rd(f"{R}/_rgb_st.png")

    # ③ 背景中性化 + 压黑
    proc = _bg_neutralize(proc)

    # 可选轻去绿(SPCC 已校色默认 0;残留背景绿再开)
    if green and green > 0:
        l2 = _lum(proc)
        gr = proc.copy()
        gr[..., 1] = np.minimum(proc[..., 1], (proc[..., 0] + proc[..., 2]) / 2)
        cm = _smooth(l2, 0.5, 0.82)[..., None]
        g = cm + (1 - cm) * (1 - green)
        proc = proc * g + gr * (1 - g)

    # ④ 带主体蒙版降噪
    nebmask = _nebmask(proc)
    proc = masked_denoise(proc, nebmask, timeout=timeout)

    # ⑤ 温和饱和
    L = _lum(proc)[..., None]
    proc = np.clip(L + sat * (proc - L), 0, 1)

    # ⑥ 背景抬中性灰(绝不死黑)
    proc = neutral_gray(proc)

    out = str(out_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    Image.fromarray((np.clip(proc, 0, 1) * 255).astype(np.uint8)).save(out + ".png", optimize=True)
    log(f"[rgb] 完成 → {out}.png ({'真SPCC' if used_spcc else '星场白平衡兜底'})")
    return out + ".png"


# ── 从目录一把梭(GUI 用)────────────────────────────────────────────────────
def run_rgb_from_dir(src: str, out_noext: str, *, palette: str = "natural",
                     sensor: str | None = None, oscfilter: str | None = None,
                     crop: str | None = None, timeout: float = 1800.0, log=print) -> str:
    """从 OSC 输入一把梭出无 PI 纯 RGB 成片。src 可为:
      - 单张整合 master(.xisf/.fit/.fits/.tif)→ 直接 run_rgb;
      - registered/subs 目录(含 OSC 子帧)→ 先 Siril 整合再 run_rgb。GUI 入口。"""
    R = str(config.RUN_DIR)
    if os.path.isfile(src):
        master = src
    elif os.path.isdir(src):
        subs = [x for x in glob.glob(os.path.join(src, "**", "*.xisf"), recursive=True)
                if not x.lower().endswith(".xdrz")] or \
               glob.glob(os.path.join(src, "**", "*.fit*"), recursive=True)
        if not subs:
            raise RuntimeError(f"目录无可整合子帧:{src}")
        import shutil
        d = os.path.join(R, "_int_RGB")
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for x in subs:
            shutil.copy2(x, d)
        log(f"[rgb] 整合 {len(subs)} 帧 OSC 子帧")
        master = stack_registered(d, os.path.join(R, "eng_RGB"), timeout=timeout)
    else:
        raise RuntimeError(f"输入不存在:{src}")
    if sensor is None:
        sensor, oscfilter = guess_sensor(src)
    return run_rgb(master, out_noext, palette=palette, sensor=sensor, oscfilter=oscfilter,
                   crop=crop, timeout=timeout, log=log)
