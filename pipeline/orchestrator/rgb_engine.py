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
import re
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


def _emission_mask(proc: np.ndarray, log=print, *, protect_stars: bool = True) -> np.ndarray:
    """**红色发射蒙版**:提 R 显著超过 G/B 的**连贯**区域(发射星云红丝,如马头 IC434 脊)。
    按亮度的 nebmask 看不见这种"和背景一样暗但偏红"的faint发射 → 用它补上。
    ① 地板去背景红噪(只留真发射,robust 百分位)。② **护星**(星点+色晕膨胀后排除,否则
    带星揭示会在每颗星揭示出环状伪影/暗环)——**去星后的图传 protect_stars=False**(无星、且
    护星反而在原星位挖暗盘)。返回 [0,1] 权重图。"""
    R, G, B = proc[..., 0], proc[..., 1], proc[..., 2]
    L = _lum(proc)
    em = np.clip(R - np.maximum(G, B), 0, 1)
    em = gaussian_filter(em, 4) if gaussian_filter is not None else cv2.GaussianBlur(em, (0, 0), 4)
    floor = float(np.percentile(em, 90))                         # 地板:切掉背景红噪(下 90%),只留真发射
    em = np.clip(em - floor, 0, None)
    em = np.clip(em / (np.percentile(em, 99.5) + 1e-6), 0, 1)
    if protect_stars:
        star = (L > 0.42).astype(np.float32)                     # 护星:亮紧致特征(星+色晕)膨胀排除
        star = cv2.dilate(star, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
        star = gaussian_filter(star, 6) if gaussian_filter is not None else cv2.GaussianBlur(star, (0, 0), 6)
        em = em * (1.0 - np.clip(star, 0, 1))
    return em


def _starless_reveal(proc: np.ndarray, reveal: float, emission: float, *,
                     timeout: float = 1800.0, log=print) -> np.ndarray:
    """**去星揭示**(消除星点暗环的正解):StarNet2 去星 → 在**无星星云**上做揭示/发射揭示
    (无需护星 → 星位不再挖暗盘、星晕不再留暗环)→ **screen 合回星点层**(screen 只提亮不压暗)。
    比带星揭示干净:星云被自由提亮、星点原样叠回。StarNet2 不可用则调用方退回带星揭示。"""
    R = str(config.RUN_DIR)
    sn = siril.starnet_exe()
    if not sn:
        raise RuntimeError("StarNet2 CLI 不可用")
    # 存全图 16bit TIFF → StarNet2 出 starless + stars
    cv2.imwrite(f"{R}/_rgb_full.tif",
                cv2.cvtColor((np.clip(proc, 0, 1) * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))
    subprocess.run([sn, "-i", f"{R}/_rgb_full.tif", "-o", f"{R}/_rgb_starless.tif",
                    "-n", f"{R}/_rgb_stars.tif", "-s", "256"],
                   capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(f"{R}/_rgb_starless.tif"):
        raise RuntimeError("StarNet2 去星失败(无 starless 输出)")
    starless = _rd(f"{R}/_rgb_starless.tif")
    # 星点层:优先 StarNet 的 -n 输出;没有则 full-starless(残星更多,兜底)
    if os.path.exists(f"{R}/_rgb_stars.tif"):
        stars = _rd(f"{R}/_rgb_stars.tif")
    else:
        stars = np.clip(proc - starless, 0, 1)
    log(f"[rgb] 去星揭示:StarNet2 去星 → 无星星云揭示(reveal={reveal},emission={emission})→ screen 合回星点")
    # 在无星图上揭示(护星关闭:已无星)
    nebmask = _nebmask(starless)
    emmask = _emission_mask(starless, log=log, protect_stars=False) if emission and emission > 0 else None
    rev = _reveal_nebula(starless, nebmask, reveal, emmask=emmask, emission=emission)
    # screen 合回星点(只提亮不压暗 → 不产生暗环)
    return np.clip(1.0 - (1.0 - rev) * (1.0 - np.clip(stars, 0, 1)), 0, 1)


def _reveal_nebula(proc: np.ndarray, nebmask: np.ndarray, amount: float,
                   *, emmask: np.ndarray | None = None, emission: float = 0.0) -> np.ndarray:
    """**星云区揭示**:对 nebmask 加权做 asinh 中低调提升(揭示星云暗弱结构/外围弱云),
    **保背景**(mask~0 不动,不抬噪)+ **保高光**(亮核/亮星 L>0.9 不揭示,防 blow 白核)。
    amount 越大揭示越狠。给暗弱/需要更亮星云的目标强化拉伸,又不动背景和核心。
    **emmask/emission**:额外把**红色发射蒙版**(faint 红丝,亮度 nebmask 抓不到的)也纳入揭示权重,
    emission 控其力度(马头 IC434 脊这类靠它)。两路权重相加后统一过 hi_protect + clip。"""
    lum_on = bool(amount and amount > 0)
    em_on = emmask is not None and emission and emission > 0
    if not lum_on and not em_on:
        return proc
    L = _lum(proc)
    a = 3.0
    lifted = np.arcsinh(np.clip(L, 0, 1) * a) / np.arcsinh(a)    # asinh:提暗中、压高光
    ratio = np.where(L > 1e-4, lifted / np.maximum(L, 1e-4), 1.0)
    hi_protect = 1.0 - _smooth(L, 0.55, 0.9)                     # 亮核/亮星不揭示
    wsum = nebmask * (amount or 0.0)
    if em_on:
        wsum = wsum + emmask * emission
    w = np.clip(wsum * hi_protect, 0, 1)[..., None]
    return np.clip(proc * (1.0 + (ratio[..., None] - 1.0) * w), 0, 1)


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


def _astro_available() -> bool:
    """全天解析星表(platesolve 用)是否装好——SPCC 的一次性前置;photo 区块由 spcc_catalog 按天区自动补。"""
    cfg = _siril_config_path()
    if not cfg or not os.path.exists(cfg):
        return False
    astro = None
    try:
        for line in open(cfg, encoding="utf-8", errors="ignore"):
            if line.startswith("catalogue_gaia_astro="):
                astro = os.path.expanduser(line.split("=", 1)[1].strip())
    except Exception:
        return False
    return bool(astro) and os.path.exists(astro) and os.path.getsize(astro) > 1e8


# 常见 OSC 相机型号 → Siril SPCC 的 Sony 传感器名(型号写进路径/文件名,如 "2600mc")。
# 键带 "m"(MC/MM 尾)减少误命中日期等数字串。ASI2600MC=IMX571(已验证 SPCC 可用)。
_CAM2SENSOR = [
    ("2600m", "Sony IMX571"), ("6200m", "Sony IMX455"), ("2400m", "Sony IMX410"),
    ("533m", "Sony IMX533"), ("294m", "Sony IMX294"), ("183m", "Sony IMX183"),
    ("178m", "Sony IMX178"), ("071m", "Sony IMX071"), ("585m", "Sony IMX585"),
    ("482m", "Sony IMX482"), ("455m", "Sony IMX455"), ("410m", "Sony IMX410"),
]


def guess_sensor(path: str) -> tuple[str | None, str | None]:
    """从路径/文件名猜 SPCC 传感器+滤镜。Seestar 自带配置;常见 ZWO/QHY OSC 按型号映射 Sony 传感器。
    返回 (oscsensor, oscfilter) 或 (None, None)。滤镜:双窄带→LP/Dualband,否则→UV/IR Block。"""
    n = str(path).lower()
    dual = ("_lp" in n or "filter-lp" in n or "dualband" in n or "_ho" in n or "duo" in n
            or "l-enhance" in n or "lextreme" in n or "l-ultimate" in n)
    if "s50" in n or "seestar_s50" in n:
        return "ZWO Seestar S50", ("ZWO Seestar LP" if dual else "UV/IR Block")
    if "s30" in n or "seestar" in n:
        return "ZWO Seestar S30", ("ZWO Seestar LP" if dual else "UV/IR Block")
    for key, sensor in _CAM2SENSOR:                       # 常见 OSC 相机型号
        if key in n:
            # 双窄带滤镜的谱线不适合 SPCC 连续谱校色 → 只在广谱下给滤镜;双窄带留给 HO 引擎另处
            return sensor, ("UV/IR Block" if not dual else None)
    return None, None


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


def _subsky_cmds(bg_extract: str) -> list[str]:
    """背景梯度提取命令(可两遍,`+` 连接)。单项:"1"~"4"=多项式阶数(越高拟合越复杂梯度,太高吃弥漫星云);
    "rbf"=径向基(对**不对称/复杂梯度**更稳,Siril 推荐);degree1 只去线性倾斜。
    **两遍**如 "4+rbf"=d4 压主梯度 + rbf 清残留(低空银河/光污染这类**顶部残留**单遍拟合不掉时用)。"""
    def _one(s: str) -> str:
        return "subsky -rbf -samples=25 -smooth=0.4" if s == "rbf" else f"subsky {s}"
    return [_one(s) for s in bg_extract.split("+")]


def calibrate(master: str, out_noext: str, *, sensor: str | None = None,
              oscfilter: str | None = None, crop: str | None = None, bg_extract: str = "1",
              do_spcc: bool = True, timeout: float = 1800.0, log=print) -> tuple[str, bool]:
    """线性色彩校准 → 保存校准图。返回 (路径, 是否用了真SPCC)。
    SPCC(装了本地星表 + 已知传感器):load→subsky→platesolve→spcc→存 .fit(32位,精度最好)。
    兜底:load→subsky→存 tif→numpy 部分星场白平衡→存 .tif。bg_extract 见 _subsky_cmd。"""
    R = str(config.RUN_DIR)
    m = str(master).replace("\\", "/")
    out = str(out_noext).replace("\\", "/")
    for e in (".fit", ".fits", ".tif", ".xisf", ".png"):
        if out.lower().endswith(e):
            out = out[:-len(e)]
    # 【坑】清同名旧中间文件:Siril `load <basename>`(不带扩展)默认优先 .fit,
    #   跨会话残留的旧 _cal.fit 会盖过本次新存的 _cal.tif(WB 兜底存 tif)→ 读到旧图(实测 M31 中招)。
    import glob as _glob
    for _f in _glob.glob(f"{R}/{os.path.basename(out)}_cal.*") + _glob.glob(f"{R}/{os.path.basename(out)}_lin.*"):
        try:
            os.remove(_f)
        except OSError:
            pass
    if sensor is None:
        sensor, oscfilter = guess_sensor(master)
    pre = [f"cd {R}", f'load "{m}"'] + (["crop " + crop] if crop else []) + _subsky_cmds(bg_extract)

    # 【桌面固化】SPCC:装了全天解析星表 + 已知传感器 → 按目标天区**自动补装** photo 区块再跑 spcc
    _do_spcc = bool(do_spcc and sensor and _astro_available())
    if _do_spcc:
        try:
            from . import spcc_catalog
            rd = spcc_catalog.read_radec(master, siril)
            if rd:
                need, _ok = spcc_catalog.ensure_for_field(rd[0], rd[1], log=log, timeout=timeout)
                _do_spcc = bool(need) and all(c in spcc_catalog.installed_chunks() for c in need)
            else:
                _do_spcc = spcc_available()          # 读不到坐标 → 退回旧判断
        except Exception as e:
            log(f"[rgb] SPCC 区块补装异常:{str(e)[:80]}")
            _do_spcc = spcc_available()

    if _do_spcc:
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


def align_rgb_channels(img: np.ndarray, log=print) -> np.ndarray:
    """**校正 RGB 三通道错位**(横向色差 LCA + 大气色散):以 G 为基准,网格相位相关测 R/B 相对
    G 的位移场、拟合二次形变、把 R/B warp 到 G → 离轴星点从"绿核+红蓝边"恢复成白色圆点。
    这类错位是**光学(横向色差,径向)+ 大气色散(方向性)**在拍摄数据里就有的,任何软件直接
    合成都会有,须单独校正。stretched/linear 图皆可(星点未饱和处相位相关够准)。"""
    if cv2 is None or img.ndim != 3:
        return img
    h, w = img.shape[:2]

    def hp(x):
        return (x - cv2.GaussianBlur(x, (0, 0), 3)).astype(np.float64)   # 高通突出星点(星点无关缩放)

    nx, ny = 7, 5
    tile = int(min(h, w) * 0.14)
    half = tile // 2
    # 【坑】网格 tile **不能贴边**(边缘反射污染 phaseCorrelate→拟合斜率偏、只修一半);中心内插到
    #   [half, 尺寸-half]。且 G/R/B **同法逐 tile 高通**(全图高通再切,tile 边界与逐 tile 不一致)。
    centers = [(int(half + (w - 2 * half) * (ix / (nx - 1))),
                int(half + (h - 2 * half) * (iy / (ny - 1)))) for iy in range(ny) for ix in range(nx)]
    U, Vv, DxR, DyR, DxB, DyB = [], [], [], [], [], []
    for cx, cy in centers:
        gt = hp(img[cy - half:cy + half, cx - half:cx + half, 1])
        if gt.std() < 1e-5:
            continue
        rt = hp(img[cy - half:cy + half, cx - half:cx + half, 0])
        bt = hp(img[cy - half:cy + half, cx - half:cx + half, 2])
        (dxr, dyr), rr = cv2.phaseCorrelate(gt, rt)
        (dxb, dyb), rb = cv2.phaseCorrelate(gt, bt)
        if min(rr, rb) < 0.4 or max(abs(dxr), abs(dyr), abs(dxb), abs(dyb)) > 5:
            continue
        U.append((cx - w / 2) / (w / 2))
        Vv.append((cy - h / 2) / (h / 2))
        DxR.append(dxr); DyR.append(dyr); DxB.append(dxb); DyB.append(dyb)
    if len(U) < 8:
        log("[rgb] 通道对齐:有效网格点不足,跳过")
        return img
    peak = float(np.max(np.abs(np.array(DxR + DyR + DxB + DyB))))
    if peak < 0.25:
        log(f"[rgb] 通道对齐:通道位移已很小(peak {peak:.2f}px),跳过")
        return img
    U = np.array(U); Vv = np.array(Vv)
    # **线性基 [1,u,v]**:LCA=径向缩放(线性位移)+ 色散=均匀平移,本就是仿射;线性场在边角
    # 按线性外推、不过冲(二次基会在角上发散)。3 参/分量,稳拟合。
    Bm = np.stack([np.ones_like(U), U, Vv], 1)
    cs = {k: np.linalg.lstsq(Bm, np.array(v), rcond=None)[0]
          for k, v in [("xr", DxR), ("yr", DyR), ("xb", DxB), ("yb", DyB)]}
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    Un = (X - w / 2) / (w / 2)
    Vn = (Y - h / 2) / (h / 2)
    Bf = np.stack([np.ones_like(Un), Un, Vn], -1)

    def fld(c):
        return (Bf @ c).astype(np.float32)

    def _grid_resid(Rarr):
        """在同一内插网格上重测 R vs G 的残余位移均值(定号/自检用,与拟合网格一致最可靠)。"""
        tot, n = 0.0, 0
        for cx, cy in centers:
            g = hp(img[cy - half:cy + half, cx - half:cx + half, 1])
            r = hp(Rarr[cy - half:cy + half, cx - half:cx + half])
            (dx, dy), cf = cv2.phaseCorrelate(g, r)
            if cf < 0.4:
                continue
            tot += abs(dx) + abs(dy); n += 1
        return tot / max(n, 1)

    # 自动定号(采样位置 = X ± 形变场):选让网格残余更小的号,免踩 phaseCorrelate 方向约定坑。
    warps = {s: cv2.remap(img[..., 0], X + s * fld(cs["xr"]), Y + s * fld(cs["yr"]),
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT) for s in (1.0, -1.0)}
    resid = {s: _grid_resid(warps[s]) for s in (1.0, -1.0)}
    best_s = 1.0 if resid[1.0] <= resid[-1.0] else -1.0
    out = img.copy()
    out[..., 0] = warps[best_s]
    out[..., 2] = cv2.remap(img[..., 2], X + best_s * fld(cs["xb"]), Y + best_s * fld(cs["yb"]),
                            cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    log(f"[rgb] 通道对齐(横向色差/大气色散校正):{len(U)} 网格点,线性形变 warp R/B→G"
        f"(sign={best_s:+.0f},peak {peak:.2f}px→网格残余 {resid[best_s]:.2f}px)")
    return np.clip(out, 0, 1)


# ── 主编排器 ─────────────────────────────────────────────────────────────────
def remove_residual_glow(rgb: np.ndarray, *, mode: str = "auto", detect_thr: float = 0.012,
                         log=print) -> np.ndarray:
    """成片后**残留辉光/梯度清除**(ABE 式,补线性 subsky 之漏)。网格取每格**最暗分位**中位作
    背景样点(darkest-quantile,天然护星/护云)→ 平滑背景面 → 逐通道减到全图目标电平
    (亮度辉光 + 随之的色偏一起治,如角落 amp glow/光污染的品红角)。
    mode: "auto"(检测:大尺度背景落差/色偏低于阈值=图已干净则**原样返回**,尊重
      [[pi-gradient-findings]]/朝银心真实天光别压平的铁律)/ "on"(强制)/ "off"(跳过)。"""
    if cv2 is None or mode == "off":
        return rgb
    h, w = rgb.shape[:2]
    GY = 42
    GX = max(1, int(round(GY * w / h)))
    th, tw = max(1, h // GY), max(1, w // GX)
    grid = np.zeros((GY, GX, 3), np.float32)
    for iy in range(GY):
        for ix in range(GX):
            blk = rgb[iy * th:(iy + 1) * th, ix * tw:(ix + 1) * tw].reshape(-1, 3)
            if blk.size == 0:
                grid[iy, ix] = grid[iy, max(0, ix - 1)]
                continue
            Lb = blk.mean(1)
            sel = Lb <= np.quantile(Lb, 0.4)                  # 该格最暗 40%(排除星/亮云)
            grid[iy, ix] = np.median(blk[sel], 0)
    target = np.median(grid.reshape(-1, 3), 0)
    bg = cv2.resize(grid, (w, h), interpolation=cv2.INTER_CUBIC)
    bg = cv2.GaussianBlur(bg, (0, 0), max(th, tw) * 0.9)       # 只保低频大尺度,不动高频星/云结构
    # 【辉光幅度检测(粗区块,抗星云)】4×4 大区块、每区最暗分位中位作背景(大区块里星云/星点占比小
    #   → 不被污染;辉光"比背景亮比星云暗"用亮度掩膜会两头落空,故按大区块统计)。辉光=最亮区比区块
    #   中位高多少;色偏=各区相对中位的最大色度偏移。都低于阈值 → 图已均匀,auto 跳过(尊重真实天光)。
    CR = 4
    rh, rw = max(1, h // CR), max(1, w // CR)
    reg = np.zeros((CR, CR, 3), np.float32)
    for iy in range(CR):
        for ix in range(CR):
            blk = rgb[iy * rh:(iy + 1) * rh, ix * rw:(ix + 1) * rw].reshape(-1, 3)
            Lb = blk.mean(1)
            reg[iy, ix] = np.median(blk[Lb <= np.quantile(Lb, 0.4)], 0)
    regL = reg.mean(2).ravel()
    glow = float(regL.max() - np.median(regL))                 # 最亮区比典型区高多少
    regC = reg - reg.mean(2, keepdims=True)                     # 各区色度
    chroma = float(np.abs(regC - np.median(regC.reshape(-1, 3), 0)).max())
    if mode == "auto" and glow < detect_thr and chroma < detect_thr:
        log(f"[rgb] 残留辉光清除:背景已均匀(辉光{glow * 100:.1f}/色偏{chroma * 100:.1f}"
            f"<{detect_thr * 100:.1f}×100),跳过不动(尊重真实天光别压平)")
        return rgb
    corr = np.clip(rgb - (bg - target.reshape(1, 1, 3)), 0, 1)
    log(f"[rgb] 残留辉光清除(ABE式,护星护云):背景辉光 {glow * 100:.1f}→平、色偏 {chroma * 100:.1f} 中和(×100)")
    return corr


def _autocrop_edges(img: np.ndarray, *, thr: float = 0.30, max_frac: float = 0.06, log=print) -> np.ndarray:
    """裁掉**叠加抖动边缘的异常带**(整行/整列中位显著偏离内部 → 拉伸后放大成亮/暗带,如底部亮条)。
    从四边向内扫连续异常的行/列(相对内部中位偏离 > thr),各边最多裁 max_frac。**在拉伸后调**
    (线性 master 里边缘带只 +3% 抓不住,拉伸后 +60% 才明显)。整行/整列判据 → 不误伤边缘的真星云。"""
    if img.ndim != 3:
        return img
    h, w = img.shape[:2]
    L = img.mean(2)
    inner = float(np.median(L[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)])) + 1e-6
    rm = np.median(L, axis=1)
    cm = np.median(L, axis=0)

    def scan(arr, n):
        lo = 0
        for i in range(int(n * max_frac)):
            if abs(arr[i] - inner) / inner > thr:
                lo = i + 1
            else:
                break
        hi = n
        for i in range(int(n * max_frac)):
            if abs(arr[n - 1 - i] - inner) / inner > thr:
                hi = n - 1 - i
            else:
                break
        return lo, hi
    y0, y1 = scan(rm, h)
    x0, x1 = scan(cm, w)
    if (y0, y1, x0, x1) != (0, h, 0, w):
        log(f"[rgb] 边缘裁切(叠加抖动异常带):上{y0} 下{h - y1} 左{x0} 右{w - x1} 行/列"
            f"(FOV 保留 {(y1 - y0) * (x1 - x0) / (h * w) * 100:.1f}%)")
        return np.ascontiguousarray(img[y0:y1, x0:x1])
    return img


def run_rgb(master: str, out_noext: str, *, palette: str = "natural",
            hdr: str | None = None, sat: float | None = None, green: float | None = None,
            sensor: str | None = None, oscfilter: str | None = None,
            crop: str | None = None, stretch_bg: float | None = None, bg_extract: str = "1",
            reveal: float | None = None, emission: float = 0.0, glow_clean: str = "auto",
            timeout: float = 1800.0, log=print) -> str:
    """无 PI 纯 RGB 全流程。master=OSC 单张整合 master。palette=PRESETS 键。返回成片 <out>.png。
    hdr: "ght"(GHS 压核)/"off"(纯 autostretch);sat/green/stretch_bg 覆盖预设;
    bg_extract: 背景梯度提取("1"~"4" 多项式 / "rbf" 径向基,复杂梯度用 rbf,见 _subsky_cmds);
    reveal: 星云区揭示强度(0=关;暗弱/需更亮星云的目标调高,保背景/高光,见 _reveal_nebula)。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python(cv2)")
    R = str(config.RUN_DIR)
    p = {**PRESETS[palette]}
    hdr = hdr if hdr is not None else p["hdr"]
    sat = sat if sat is not None else p["sat"]
    green = green if green is not None else p["green"]
    stretch_bg = stretch_bg if stretch_bg is not None else p["stretch_bg"]
    reveal = reveal if reveal is not None else p.get("reveal", 0.0)
    log(f"[rgb] palette={palette} hdr={hdr} sat={sat} green={green} reveal={reveal}")

    # ① 色彩校准(SPCC 或兜底)
    cal, used_spcc = calibrate(master, os.path.join(R, "_rgbcal"), sensor=sensor,
                               oscfilter=oscfilter, crop=crop, bg_extract=bg_extract,
                               timeout=timeout, log=log)

    # ② 拉伸:autostretch -linked(+ 可选 GHS 压核)
    st_cmds = [f"cd {R}", f"load {os.path.basename(cal).rsplit('.', 1)[0]}",
               f"autostretch -linked -2.8 {stretch_bg}"]
    if hdr == "ght":
        st_cmds.append(_GHT)
    st_cmds.append("savepng _rgb_st")
    siril.run_script(st_cmds, timeout=timeout)
    proc = _rd(f"{R}/_rgb_st.png")

    # ②a 边缘裁切:裁掉叠加抖动边缘的异常带(拉伸后放大成亮/暗条,如底部亮带)。放在最前 →
    #    异常带不污染后续通道对齐/背景/辉光/nebmask 统计。
    proc = _autocrop_edges(proc, log=log)

    # ②b 通道对齐:校正 RGB 三通道错位(横向色差 + 大气色散),星点从"绿核红蓝边"归为白圆点
    proc = align_rgb_channels(proc, log=log)

    # ③ 背景中性化 + 压黑
    proc = _bg_neutralize(proc)

    # ③a 残留辉光清除(ABE 式,补线性 subsky 漏掉的局部残留辉光+色偏;auto 检测,图已均匀则跳过)。
    #    放在揭示/nebmask 前 → 辉光不污染 nebmask、也不被揭示放大。
    proc = remove_residual_glow(proc, mode=glow_clean, log=log)

    # ③b 星云区揭示。**去星揭示优先**(StarNet2 可用时):去星 → 在无星星云上揭示 → screen 合回星点,
    #    消除"带星揭示"的**星点暗环**(护高光/护星逻辑在星位/星晕挖暗盘所致)。不可用则退回带星蒙版揭示。
    _rv = reveal or 0.0
    if _rv > 0 or (emission and emission > 0):
        try:
            proc = _starless_reveal(proc, _rv, emission, timeout=timeout, log=log)
        except Exception as _se:
            log(f"[rgb] 去星揭示不可用({_se})→ 退回带星蒙版揭示(星点可能有暗环)")
            nb0 = _nebmask(proc)
            emmask = _emission_mask(proc, log=log) if emission and emission > 0 else None
            proc = _reveal_nebula(proc, nb0, _rv, emmask=emmask, emission=emission)
    # 降噪用的主体蒙版(在揭示/合星后的图上重算)
    nebmask = _nebmask(proc)

    # 可选轻去绿(SPCC 已校色默认 0;残留背景绿再开)
    if green and green > 0:
        l2 = _lum(proc)
        gr = proc.copy()
        gr[..., 1] = np.minimum(proc[..., 1], (proc[..., 0] + proc[..., 2]) / 2)
        cm = _smooth(l2, 0.5, 0.82)[..., None]
        g = cm + (1 - cm) * (1 - green)
        proc = proc * g + gr * (1 - g)

    # ④ 带主体蒙版降噪(复用 ③b 的 nebmask)
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
# 定标 master(暗场/平场/偏置/暗平场)——不是光子帧,叠加时必须排除
_CAL_MASTER_RE = re.compile(r"master[_\- ]?(dark|flat|bias|darkflat)", re.I)


def select_master_in_dir(src: str, log=print) -> str | None:
    """目录里认出**整合 master**:优先 `masterLight*`(取最大的=整合主图),没有则返回 None。
    这样用户指向 `.../master` 目录(内含 masterLight + masterDark/Flat + 参考帧)时,直接用
    整合好的 masterLight,**不会把定标 master 也当子帧叠进去**(否则出错图)。"""
    cand = [x for x in glob.glob(os.path.join(src, "**", "*.xisf"), recursive=True)
            + glob.glob(os.path.join(src, "**", "*.fit*"), recursive=True)
            if not x.lower().endswith(".xdrz")]
    lights = [x for x in cand if "masterlight" in os.path.basename(x).lower()]
    if lights:
        m = max(lights, key=lambda p: os.path.getsize(p))
        log(f"[master] 目录内认出整合 master:{os.path.basename(m)}")
        return m.replace("\\", "/")
    return None


def subframes_in_dir(src: str) -> list[str]:
    """目录里可叠加的**光子帧**(排除 masterDark/Flat/Bias 定标 master)。"""
    subs = [x for x in glob.glob(os.path.join(src, "**", "*.xisf"), recursive=True)
            if not x.lower().endswith(".xdrz")] or \
           glob.glob(os.path.join(src, "**", "*.fit*"), recursive=True)
    return [x for x in subs if not _CAL_MASTER_RE.search(os.path.basename(x))]


def resolve_master(src: str, tag: str, out_stack_noext: str, *, timeout: float = 1800.0, log=print) -> str:
    """GUI 输入(文件或目录)→ 单张整合 master 路径。文件直接用;目录:优先 masterLight*,
    否则排除定标 master 后——单帧直接用、多帧才 Siril 整合。所有 from_dir 入口共用,统一"选主图"逻辑。"""
    if os.path.isfile(src):
        return str(src).replace("\\", "/")
    if not os.path.isdir(src):
        raise RuntimeError(f"输入不存在:{src}")
    m = select_master_in_dir(src, log)
    if m:
        return m
    subs = subframes_in_dir(src)
    if not subs:
        raise RuntimeError(f"{tag} 目录无可用子帧/整合 master:{src}")
    if len(subs) == 1:
        log(f"[master] {tag} 目录内单帧直接用:{os.path.basename(subs[0])}")
        return subs[0].replace("\\", "/")
    import shutil
    d = os.path.join(str(config.RUN_DIR), f"_int_{tag}")
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for x in subs:
        shutil.copy2(x, d)
    log(f"[{tag}] 整合 {len(subs)} 帧 OSC 子帧")
    return stack_registered(d, out_stack_noext, timeout=timeout)


def run_rgb_from_dir(src: str, out_noext: str, *, palette: str = "natural",
                     sensor: str | None = None, oscfilter: str | None = None,
                     crop: str | None = None, bg_extract: str = "1", reveal: float | None = None,
                     emission: float = 0.0, glow_clean: str = "auto",
                     timeout: float = 1800.0, log=print) -> str:
    """从 OSC 输入一把梭出无 PI 纯 RGB 成片。src 可为:
      - 单张整合 master(.xisf/.fit/.fits/.tif)→ 直接 run_rgb;
      - `.../master` 目录(masterLight + 定标 master)→ 认出 masterLight 直接用;
      - registered/subs 目录(含 OSC 子帧)→ 先 Siril 整合再 run_rgb。GUI 入口。"""
    R = str(config.RUN_DIR)
    master = resolve_master(src, "RGB", os.path.join(R, "eng_RGB"), timeout=timeout, log=log)
    if sensor is None:
        sensor, oscfilter = guess_sensor(src)
    return run_rgb(master, out_noext, palette=palette, sensor=sensor, oscfilter=oscfilter,
                   crop=crop, bg_extract=bg_extract, reveal=reveal, emission=emission, glow_clean=glow_clean,
                   timeout=timeout, log=log)
