"""无 PI HOO 双窄带引擎(zero-PixInsight OSC dual-narrowband HOO pipeline)。

从 OSC 双窄带 master(彩色相机/智能望远镜 + Ha+OIII 双窄带滤镜)到彩色成片,**全程不碰 PixInsight**。
照搬 PI run_hoo 的阶段序,复用 SHO 基建(StarNet2/DeepSNR)。IC1805+SH2-308 真机验证(2026-08-13)。
见 [[hoo-zeropi-engine]]。

管线(**阶段序照 PI 铁律**):
  ① **先裁黑边**(黑边污染梯度拟合)—— PI 铁律。
  ② **梯度校正在线性、拉伸前**(PI 最大铁律;我曾在拉伸后治全白费)—— GraXpert bge(AI 背景提取=ABE 等价)。
  ③ Siril `split` → **Ha=R, OIII=G**(OSC 双窄带)。
  ④ 各通道 autostretch → StarNet2 去星 → **Ha/OIII 分别揭示**(弱的揭示更狠)。
  ⑤ HOO 合成 R=Ha,G=OIII,B=OIII + gamma 提亮弱信号 + 饱和。**不做 linear_match**(会把强信号压到弱信号)。
  ⑥ DeepSNR 降噪彩色 + 星点(原图去星层去饱和,消双窄带绿/品红星)。
  ⑦ **背景抬中性灰**(通用铁律,绝不死黑)。

【铁律】
- **梯度必须线性阶段治**:线性 median 看着平,但 faint glow 被激进 reveal 放大成"梯度";拉伸后治治不干净。
- **GraXpert bge 喂 TIFF**(读不了 Siril 非标 FITS 头)+ **smoothing≥0.7**(0.3 会把扩散弱泡当背景吃掉)。
- **不做 linear_match**:OIII 主导目标(Ha 弱)把强 OIII 匹配到弱 Ha 会把泡压没。
- **背景绝不死黑**:成片最后各通道背景对齐抬到中性灰≈0.20(R=G=B)。
"""
from __future__ import annotations

import os
import subprocess

import numpy as np
try:
    import cv2
except Exception:
    cv2 = None
from PIL import Image

try:
    from scipy.ndimage import gaussian_filter
except Exception:                                   # 无 scipy → cv2 兜底(见 _chroma_denoise_bg)
    gaussian_filter = None

from . import config, siril, graxpert
from .sho_engine import _load_mono, _bg_sub, neutral_gray

# 预设:一组旋钮 = 一个 palette。reveal_ha/oiii_d = 各通道揭示强度(弱信号那个调大);
#   kg/kb = OIII→G/B 增益(kb 高出青);ha/oiii_gamma = 提亮弱信号;bg_sub_frac = 软减背景强度(小=保过渡带、消割裂);bg_gray = 背景中性灰目标。
PRESETS: dict[str, dict] = {
    # 经典青红双色(标准哈勃感,信号较均衡的目标如 IC1805)
    "classic": dict(reveal_ha_d=2.0, reveal_oiii_d=2.0, kg=1.10, kb=1.25,
                    ha_gamma=0.88, oiii_gamma=0.80, sat=0.45, bg_sub_frac=0.5, bg_gray=0.08),
    # OIII 主导(WR 泡如 SH2-308:Ha 弱→揭示狠、OIII 适度→不 blow 泡、提蓝出青泡)
    "oiii": dict(reveal_ha_d=2.2, reveal_oiii_d=1.8, kg=1.15, kb=1.35,
                 ha_gamma=0.85, oiii_gamma=0.70, sat=0.45, bg_sub_frac=0.45, bg_gray=0.08),
    # bg_gray:背景中性灰目标电平。0.20 会把背景抬成灰白发雾(玫瑰 v2"完全错误"主罪);0.08 暗干净。
}


def _reveal(d: float, sp: float = 0.26, hp: float = 0.84, lp: float = 0.14) -> str:
    return f"ght -D={d} -B=0 -LP={lp} -SP={sp} -HP={hp}"


def _chroma_denoise_bg(img: np.ndarray, *, strength: float = 0.85, sigma: float = 16.0,
                       log=print) -> np.ndarray:
    """**背景色度降噪**(专杀双窄带的红/青斑点)。双窄带 OSC 里 **Ha 只落 R 像素(拜耳 1/4 采样)**、
    OIII 落 G(1/2)+B → **R 通道噪声是 G/B 的 2 倍**,且 G/B 同源于 O(噪声相关→看着平滑)而 R 独立
    → 背景红斑点格外扎眼(NGC6992 实测降噪后 Rσ10.7 vs G5.6/B4.9)。
    做法:保**亮度**不动(结构/丝全保住)、只对**色度**(ch−L)做空间平滑,且**按主体蒙版**只在背景
    重度平滑(星云内轻,免抹掉真实红青分层)。色度噪声可以重压而几乎不损可见细节。"""
    L = img.mean(2, keepdims=True)
    chroma = img - L
    sm = np.stack([gaussian_filter(chroma[..., c], sigma) if gaussian_filter is not None
                   else cv2.GaussianBlur(chroma[..., c], (0, 0), sigma) for c in range(3)], -1)
    # 主体蒙版:大尺度亮度(星云/亮星区)→ 该处少平滑
    l2 = L[..., 0]
    big = gaussian_filter(l2, 12) if gaussian_filter is not None else cv2.GaussianBlur(l2, (0, 0), 12)
    big = (big - big.min()) / (big.max() - big.min() + 1e-6)
    w = (strength * (1.0 - _smooth01(big, 0.12, 0.45)))[..., None]      # 背景权重高、主体低
    out = np.clip(L + chroma * (1 - w) + sm * w, 0, 1)
    log(f"[hoo] 背景色度降噪(护亮度/护主体,专杀双窄带红斑):strength={strength} sigma={sigma}")
    return out


def _smooth01(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a if abs(b - a) > 1e-9 else 1e-9), 0, 1)   # 防 a==b 除零→NaN
    return np.nan_to_num(t * t * (3 - 2 * t), nan=0.0)


def _soft_knee(x: np.ndarray, knee: float = 0.80) -> np.ndarray:
    """**软膝压顶**(防拉伸削顶→平顶硬边→边缘锯齿):knee 以下原样,knee 以上用
    tanh 平滑压进 [knee,1](渐近不到 1)。替代 np.clip 的硬截断。
    NGC6992 实测:Ha 硬 clip 1.9% 面积 → 丝的顶部被削平成硬边,视觉上就是锯齿。"""
    k = float(knee)
    out = x.copy()
    hi = x > k
    if hi.any():
        out[hi] = k + (1.0 - k) * np.tanh((x[hi] - k) / max(1.0 - k, 1e-6))
    return np.clip(out, 0, 1)


def _softsub(a: np.ndarray, frac: float) -> np.ndarray:
    """软背景减:只减 frac× 角落背景(不减满)→ 保住星云外缘暗弱**过渡带**,消除星云"贴图"割裂感。
    全减(frac=1)+clip 会把"刚比背景亮一点"的外缘信号硬裁成 0 → 硬边贴在背景上(用户实测忌讳)。"""
    h, w = a.shape[:2]
    return np.clip(a - np.median(a[:int(h * 0.08), :int(w * 0.08)]) * frac, 0, 1)


def _neutralize_bg_color(img: np.ndarray, target: float = 0.20, log=print) -> np.ndarray:
    """**HOO 背景去 teal + 抬中性灰**(取代角落版 neutral_gray):双窄带里 OIII(→G/B)背景常高于
    Ha(→R)→ 整个背景发青。按**暗像素(背景,亮度下半)全局**稳健估各通道背景电平 → 逐通道对齐到
    最低通道(背景 R=G=B)→ 整体抬到中性灰 target(绝不死黑)。星云信号(高于背景)相对不动。
    **比 neutral_gray 只采两个角落稳**:角落常被星云丝/边缘块(如面纱右下红块)污染 → 反而把背景弄偏。"""
    L = img.mean(2)
    m = L < np.percentile(L, 55)
    if m.sum() < 1000:
        return neutral_gray(img, target=target)
    bg = np.array([float(np.median(img[..., c][m])) for c in range(3)])
    lo = float(bg.min())
    out = img.copy()
    for c in range(3):
        out[..., c] = out[..., c] - (bg[c] - lo)      # 逐通道对齐 → 背景中性
    out = np.clip(out - lo + target, 0, 1)             # 整体抬到中性灰 target
    log(f"[hoo] 背景去 teal + 抬灰:各通道背景 R{bg[0]*100:.1f} G{bg[1]*100:.1f} B{bg[2]*100:.1f} → 对齐中性 + 抬到 {target*100:.0f}")
    return out


# ── ② GraXpert 背景提取(喂 TIFF 避 FITS 头坑)──────────────────────────────────
def graxpert_bge_tiff(tif_path: str, out_noext: str, *, smoothing: float = 0.7,
                      timeout: float = 1800.0) -> str | None:
    """GraXpert AI 背景提取。**必须喂 TIFF**(GraXpert/astropy 读不了 Siril 非标 FITS 头卡片)。
    输出 .fits,返回可供 Siril `load` 的基名(无扩展);失败返回 None。smoothing 高保住扩散弱天体。"""
    exe = graxpert.graxpert_exe()
    if not exe:
        return None
    ver = graxpert.installed_bge_version() or "1.0.1"
    out = str(out_noext).replace("\\", "/")
    subprocess.run([exe, "-cli", "-cmd", "background-extraction", "-correction", "Subtraction",
                    "-smoothing", str(smoothing), "-gpu", "true", "-ai_version", ver,
                    "-output", out, str(tif_path).replace("\\", "/")],
                   capture_output=True, text=True, timeout=timeout)
    for e in (".fits", ".xisf", ".fit"):
        if os.path.exists(out + e):
            return os.path.basename(out)
    return None


def _masked_bge(m: str, mx: int, my: int, w: int, h: int, *, deg: int = 4,
                timeout: float = 1800.0, log=print) -> str:
    """**星云蒙版保护式去梯度**(治 moat 的正解,PI DBE 思路)。subsky 无论怎么调参都会把亮丝当背景
    拟合、挖暗环 moat(实测 subsky 各参数最好也只 −1.6)。正解:**拟合背景时把星云区完全排除**——
    ① StarNet 去星 → 星云蒙版(亮结构);② 只在**背景像素**上最小二乘拟合低阶多项式曲面(deg=4,
    含径向:x²/y² 项);③ 减去曲面,但**星云区按羽化蒙版少减/不减**(亮丝不进拟合也不被扣 → 无 moat)。
    返回去梯度后可供 Siril `load` 的基名。"""
    R = str(config.RUN_DIR)
    sn = siril.starnet_exe()
    # 裁黑边 → 存 32 位 fit 供 numpy;并 StarNet 去星拿星云(去星后剩星云/背景)
    siril.run_script([f"cd {R}", f'load "{m}"', f"crop {mx} {my} {w - 2 * mx} {h - 2 * my}",
                      "save _mb_crop"], timeout=timeout)
    img = _load_mono3(f"{R}/_mb_crop.fit")                       # (H,W,3) float [0,1]-ish
    hh, ww = img.shape[:2]
    starless = img
    if sn:
        siril.run_script([f"cd {R}", "load _mb_crop", "autostretch -2.8 0.10", "save _mb_st"], timeout=timeout)
        subprocess.run([sn, "-i", f"{R}/_mb_st.fit", "-o", f"{R}/_mb_sl.fit", "-s", "256"],
                       capture_output=True, text=True, timeout=timeout)
        if os.path.exists(f"{R}/_mb_sl.fit"):
            starless = _load_mono3(f"{R}/_mb_sl.fit")
    L = starless.mean(2)
    # 星云蒙版:大尺度亮度(去星后亮结构=星云)→ 归一 → 阈值 → 羽化。蒙版内=信号(不参与拟合/不扣)
    bl = gaussian_filter(L, 6) if gaussian_filter is not None else cv2.GaussianBlur(L, (0, 0), 6)
    bl = (bl - np.percentile(bl, 20)) / (np.percentile(bl, 99.5) - np.percentile(bl, 20) + 1e-6)
    neb = _smooth01(np.clip(bl, 0, 1), 0.18, 0.42)              # 星云=1,背景=0
    bgmask = (neb < 0.15) & np.isfinite(L)                       # 纯背景像素(拟合样本)
    # 逐通道:背景像素上最小二乘拟合多项式曲面(含 x²/y² 径向项)→ 全图求值 → 星云区按(1-neb)扣
    ys, xs = np.mgrid[0:hh, 0:ww].astype(np.float32)
    u = (xs - ww / 2) / (ww / 2); v = (ys - hh / 2) / (hh / 2)
    terms = [np.ones_like(u), u, v, u * u, v * v, u * v, u * u * u, v * v * v, u * u * v, u * v * v]
    Bfull = np.stack([t.ravel() for t in terms], 1)             # (H*W, T)
    sel = bgmask.ravel()
    out = np.empty_like(starless)
    for c in range(3):
        y = img[..., c].ravel()
        coef, *_ = np.linalg.lstsq(Bfull[sel], y[sel], rcond=None)
        surf = (Bfull @ coef).reshape(hh, ww)
        target = float(np.median(y[sel]))                       # 背景抬到其原中位(不压黑)
        corr = img[..., c] - (surf - target)
        out[..., c] = img[..., c] * neb + corr * (1 - neb)      # 星云区原样、背景区扣曲面
    out = np.clip(out, 0, 1)
    cv2.imwrite(f"{R}/_hoo_bge.tif", cv2.cvtColor((out * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))
    siril.run_script([f"cd {R}", "load _hoo_bge", "save _hoo_bge"], timeout=timeout)   # tif→fit 供下游
    log(f"[hoo] 星云蒙版保护去梯度(deg{deg}):背景像素 {int(sel.sum()/sel.size*100)}% 拟合,星云区不扣 → 无 moat")
    return "_hoo_bge"


def _load_mono3(path: str) -> np.ndarray:
    """读 Siril fit → (H,W,3) RGB float。彩色 fit 是 (3,H,W)。"""
    from astropy.io import fits
    d = fits.getdata(path).astype(np.float32)
    if d.ndim == 3:
        d = np.moveaxis(d, 0, -1) if d.shape[0] <= 4 else d
    else:
        d = np.stack([d] * 3, -1)
    mx = float(d.max())
    return d / mx if mx > 1.5 else d


# ── ①②③ 裁边 + 线性去梯度 + 提取 Ha/OIII ─────────────────────────────────────
def extract_haoiii(master: str, *, crop_margin: float = 0.03, bge: str = "subsky",
                   bge_smoothing: float = 0.85, bg_extract: str = "rbf",
                   bge_cmd: list | None = None, timeout: float = 1800.0, log=print) -> tuple[str, str, str]:
    """OSC 双窄带 master → 裁黑边 → 线性去梯度 → split。返回 (去梯度master基名, Ha=_cR, OIII=_cG)。
    bge:去梯度法——
      "subsky"(默认):轻 subsky。**平背景 + 有真实弥漫星云的目标**(如 SH2-308)安全、不造暗环。
      "graxpert":GraXpert AI 去梯度(=ABE)。**真有复杂梯度**(光污染/暗角)时用;但对平背景+弥漫目标
                 会把弥漫星云和亮物外缘当背景**过度扣除 → 泡周围暗环(moat)+ 抹真实信号**,慎用。"""
    R = str(config.RUN_DIR)
    m = str(master).replace("\\", "/")
    siril.run_script([f"cd {R}", f'load "{m}"', "savetif _hoo_full"], timeout=timeout)
    a = cv2.imread(f"{R}/_hoo_full.tif", cv2.IMREAD_UNCHANGED)
    h, w = a.shape[:2]
    mx, my = int(w * crop_margin), int(h * crop_margin)   # ① 裁黑边(黑边污染梯度拟合)
    if bge == "masked":
        src = _masked_bge(m, mx, my, w, h, timeout=timeout, log=log)
    elif bge == "graxpert":
        cv2.imwrite(f"{R}/_hoo_c.tif", a[my:h - my, mx:w - mx])
        src = graxpert_bge_tiff(f"{R}/_hoo_c.tif", f"{R}/_hoo_bge", smoothing=bge_smoothing, timeout=timeout)
        if src is None:
            log("[hoo] [!] GraXpert bge 失败/卡(GPU 争用?重启 GraXpert)→ 退 subsky")
            siril.run_script([f"cd {R}", "load _hoo_c", "subsky 1", "save _hoo_bge"], timeout=timeout)
            src = "_hoo_bge"
        else:
            log(f"[hoo] GraXpert bge 去梯度(smoothing={bge_smoothing})")
    else:   # subsky(默认,无 moat)
        # 【梯度】默认 **rbf 防-moat 档**:①`subsky 1` 一阶平面建不了径向渐晕(→"中间黑四周绿",
        #   实测中心 G-R−2.7→角落+1.6);②但普通 rbf(-samples=25 -smooth=0.4)会**贴着亮丝拟合、
        #   在丝周围挖暗环 moat**(NGC6992 用户圈出,实测丝旁 −3.9)。解法**不是换模型**,是让 rbf
        #   **别碰亮结构**:`-tolerance` sigma 拒绝把亮星云样本剔出拟合 + 高 `-smooth` 让曲面更钝、
        #   建得了径向大势却挖不出局部洞;`-dither` 抗量化。见 [[hoo-zeropi-engine]]。
        if bge_cmd is not None:
            cmds = list(bge_cmd)
        elif bg_extract == "rbf":
            cmds = ["subsky -rbf -samples=20 -tolerance=1.0 -smooth=0.9 -dither"]
        else:
            from .rgb_engine import _subsky_cmds
            cmds = _subsky_cmds(bg_extract)
        siril.run_script([f"cd {R}", f'load "{m}"', f"crop {mx} {my} {w - 2 * mx} {h - 2 * my}"]
                         + cmds + ["save _hoo_bge"], timeout=timeout)
        src = "_hoo_bge"
        log(f"[hoo] subsky 去梯度({' + '.join(cmds)};rbf 防-moat:tolerance 剔亮样本+高 smooth)")
    siril.run_script([f"cd {R}", f"load {src}", "split _cR _cG _cB"], timeout=timeout)   # ③ Ha=R, OIII=G
    return src, "_cR", "_cG"


def _rgb_star_layer(rgb_src: str, ref_fit: str, *, sn, sensor_hint: str | None = None,
                    timeout: float, log=print):
    """**RGB+HO 的真彩星点层**:IRCUT 宽带 master → 真 SPCC(真实星色)→ 配准到 HOO 场(ref_fit,
    因两滤镜/曝光尺寸构图可能微差)→ StarNet 取纯星层 → 返回 (H,W,3) RGB float,对齐 ref。失败返回 None。
    尺寸对齐:StarNet 星层若与 ref 尺寸不符,resize 到 ref(HOO 已裁边,以它为准)。
    sensor_hint:原始亮场目录(含设备名如 S30 Pro)——master 路径通用认不出传感器,用它 guess_sensor 保真 SPCC。"""
    R = str(config.RUN_DIR)
    try:
        from . import rgb_engine
        master = rgb_engine.resolve_master(rgb_src, "RGBstar", os.path.join(R, "_rgbstar_stack"),
                                           timeout=timeout, log=log)
        sensor, oscf = rgb_engine.guess_sensor(sensor_hint or rgb_src)
        # 真 SPCC(有星表+已知传感器)→ 真彩;拉伸给 StarNet 好输入
        cal, used = rgb_engine.calibrate(master, os.path.join(R, "_rgbstar_cal"), sensor=sensor,
                                         oscfilter=oscf, bg_extract="1", timeout=timeout, log=log)
        base = os.path.basename(cal).rsplit(".", 1)[0]
        # 配准到 HOO 参考帧:两帧堆一个序列 register(相位/星点),取配准后的 RGB 帧
        ref = os.path.basename(ref_fit).rsplit(".", 1)[0]
        siril.run_script([f"cd {R}", f"load {base}", "autostretch -linked -2.8 0.12", "save _rgbstar_st"],
                         timeout=timeout)
        from . import startools                              # 三级去星取真彩星层(SXT→darkstar→StarNet2)
        _rs = startools.load_rgb(f"{R}/_rgbstar_st.fit")
        if _rs is None:
            log("[hoo] [!] RGB 星点层读取失败 → 退回 HOO 自身星点")
            return None
        _, st = startools.remove_stars(_rs, tag="rgbstar", s_tile=256, timeout=timeout, log=log)
        # 对齐 ref 尺寸(HOO 裁边后的成片尺寸)
        rh, rw = _load_mono3(ref_fit).shape[:2]
        if st.shape[:2] != (rh, rw):
            st = cv2.resize(st, (rw, rh), interpolation=cv2.INTER_LINEAR)
            log(f"[hoo] RGB 星点层 resize 到 HOO 场 {rw}x{rh}(两滤镜尺寸微差)")
        return st
    except Exception as e:
        log(f"[hoo] [!] RGB 星点层异常({str(e)[:100]})→ 退回 HOO 自身星点")
        return None


# ── 主编排器 ─────────────────────────────────────────────────────────────────
def run_hoo(master: str, out_noext: str, *, palette: str = "oiii", bge: str = "subsky",
            crop_margin: float = 0.03, bge_smoothing: float = 0.85, stretch_bg: float = 0.16,
            bg_extract: str = "rbf", bge_cmd: list | None = None, knee: float = 0.80,
            chroma_dn: float = 0.85, star_floor: float = 2.0, rgb_star_src: str | None = None,
            rgb_star_hint: str | None = None, star_sat: float = 1.0, edge_crop: float = 0.22,
            snap_dir: str | None = None, glow_mode: str = "off", glow_neb_protect="auto",
            dn_struct_keep: float = 0.4,
            overrides: dict | None = None, timeout: float = 1800.0, log=print) -> str:
    """无 PI HOO 全流程。master=OSC 双窄带整合 master。palette: PRESETS 键
    ("oiii"=OIII 主导如 SH2-308 / "classic"=均衡青红如 IC1805)。
    bge: 去梯度法 "subsky"(默认,平背景+弥漫星云安全)/ "graxpert"(复杂梯度用)。返回成片 <out>.png。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python(cv2)")
    sn = siril.starnet_exe()
    if not sn:
        raise RuntimeError("StarNet2 CLI 不可用(配 starnet_path)")
    R = str(config.RUN_DIR)
    # 清理上一次运行的固定名中间产物:连续处理不同尺寸目标时,若某步(如 DeepSNR/reveal)未产出,
    #   os.path.exists 会误读到上一目标的残留 → 尺寸串档(SH2-308→Rosette 实测 neb 尺寸错乱崩溃)。
    import glob as _glob
    for _pat in ("_e_?.fit", "_sl_?.fit", "_r_?.fit", "_rv_?.*", "_hnb*", "_hrgb*", "_spm_*.*", "_e_?.png"):
        for _f in _glob.glob(os.path.join(R, _pat)):
            try:
                os.remove(_f)
            except OSError:
                pass
    p = {**PRESETS[palette], **(overrides or {})}
    log(f"[hoo] palette={palette} 旋钮={p}")

    # 逐步中间产物快照(诊断用):snap_dir 给了则每个操作后 dump 一张 PNG(编号_标签)。str=mono FITS,否则 ndarray。
    _snaps: list[str] = []
    def _snap(tag: str, obj) -> None:
        if not snap_dir:
            return
        os.makedirs(snap_dir, exist_ok=True)
        i = len(_snaps)
        try:
            a = _load_mono(obj, f"_snp{i}") if isinstance(obj, str) else np.asarray(obj, dtype=np.float32)
            a = np.clip(np.nan_to_num(a), 0, 1)
            if a.ndim == 2:
                a = np.stack([a, a, a], -1)
            Image.fromarray((a * 255).astype(np.uint8)).save(f"{snap_dir}/{i:02d}_{tag}.png")
            _snaps.append(tag)
            log(f"[hoo][snap] {i:02d} {tag}")
        except Exception as _se:
            log(f"[hoo][snap] {tag} 失败: {_se}")

    # ①②③ 裁边 + 线性去梯度 + 提取
    # 防-moat rbf 命令(tolerance 剔亮星云样本 + 高 smooth 钝曲面),extract 和逐通道共用
    if bge_cmd is not None:
        _bgc = list(bge_cmd)
    elif bg_extract == "rbf":
        _bgc = ["subsky -rbf -samples=20 -tolerance=1.0 -smooth=0.9 -dither"]
    else:
        from .rgb_engine import _subsky_cmds
        _bgc = _subsky_cmds(bg_extract)
    bgesrc, ha_ch, oiii_ch = extract_haoiii(master, crop_margin=crop_margin, bge=bge,
                                            bge_smoothing=bge_smoothing, bg_extract=bg_extract,
                                            bge_cmd=_bgc, timeout=timeout, log=log)

    # ④ 各通道:去梯度(**逐通道**:Ha/OIII 渐晕曲线不同 → 不逐通道治就留径向色偏;同用防-moat rbf)
    #    → autostretch → StarNet2 去星 → 分别揭示(弱信号揭示更狠)
    # 揭示 GHT 支点/护点(纯拉伸,不碰颜色):SP 必须落在星云信号电平附近才是"扩张"而非"压低"。
    #   **自动 SP**(reveal_sp 未给时):去星通道 p92 = 实测已知好 SP(背景在 p50、星云上探 p99),
    #   数据驱动 → 淡目标 SP 自动压低到信号电平、亮目标自动上移。给了 reveal_sp 则手动优先。
    _rsp_manual = p.get("reveal_sp", None); _rlp = p.get("reveal_lp", 0.14); _rhp = p.get("reveal_hp", 0.84)
    _chn = {"H": "Ha", "O": "OIII"}
    for ch, tag in ((ha_ch, "H"), (oiii_ch, "O")):
        d = p["reveal_ha_d"] if tag == "H" else p["reveal_oiii_d"]
        siril.run_script([f"cd {R}", f"load {ch}"] + _bgc
                         + [f"autostretch -2.8 {stretch_bg}", f"save _e_{tag}"], timeout=timeout)
        _snap(f"{_chn[tag]}_1去梯度+autostretch", f"{R}/_e_{tag}.fit")
        from . import startools
        # **前置 AI 降噪(揭示前!)**:噪声会被后面 GHT 揭示放大烙进去 → 先降(NXT→DeepSNR,FITS 原生保方向);
        #   去星/揭示都用降噪后的通道。RGB 引擎早有此前置降噪,HOO 补齐。
        _edn = startools.denoise_fit(f"{R}/_e_{tag}.fit", f"{R}/_e_{tag}_dn.fit", tag=f"pre{tag}", timeout=timeout, log=log)
        _snap(f"{_chn[tag]}_1b前置降噪", _edn)
        try:                                             # 三级去星(SXT→darkstar→StarNet2),Siril 转 FITS↔TIFF 保方向
            startools.remove_stars_fit(_edn, f"{R}/_sl_{tag}.fit", tag=f"ch{tag}",
                                       s_tile=256, timeout=timeout, log=log)
        except Exception as _se:
            log(f"[hoo] 通道{_chn[tag]}三级去星失败({repr(_se)[:60]})→ 退回 StarNet2")
            subprocess.run([sn, "-i", _edn, "-o", f"{R}/_sl_{tag}.fit", "-s", "256"],
                           capture_output=True, text=True, timeout=timeout)
        _snap(f"{_chn[tag]}_2去星", f"{R}/_sl_{tag}.fit")
        if _rsp_manual is not None:
            sp = float(_rsp_manual)
        else:
            _sla = _load_mono(f"{R}/_sl_{tag}.fit", f"_spm_{tag}")
            sp = float(np.clip(np.percentile(_sla, 92), 0.08, 0.35))
            log(f"[hoo] 自动SP[{_chn[tag]}] p92={sp:.3f}(背景p50={float(np.percentile(_sla, 50)):.3f})")
        # GHT 铁律:LP < SP < HP,否则非法命令 Siril 静默失败(淡目标自动 SP 可能低到 0.13,撞上默认
        #   LP=0.14 → 反案例)。LP 随 SP 联动下压,始终留足余量。
        lp_eff = min(_rlp, sp * 0.5)
        siril.run_script([f"cd {R}", f"load _sl_{tag}", _reveal(d, sp, _rhp, lp_eff), f"save _r_{tag}"], timeout=timeout)
        _snap(f"{_chn[tag]}_3揭示GHT_D{d}_SP{sp:.2f}", f"{R}/_r_{tag}.fit")

    # ⑤ HOO 合成(R=Ha, G=OIII, B=OIII)+ gamma 提亮弱信号 + 饱和。**不 linear_match**
    #   软减背景(bg_sub_frac)保住星云外缘过渡带,消除"贴图"割裂感(全减会硬裁成硬边)。
    Ha = _softsub(_load_mono(f"{R}/_r_H.fit", "_rv_H"), p["bg_sub_frac"]) ** p["ha_gamma"]
    O = _softsub(_load_mono(f"{R}/_r_O.fit", "_rv_O"), p["bg_sub_frac"]) ** p["oiii_gamma"]
    # **软膝压顶代替硬 clip**:硬 clip 会把丝的顶部削平成硬边 → 视觉锯齿(NGC6992 实测 Ha clip 1.9%)。
    Rc, Gc, Bc = _soft_knee(Ha, knee), _soft_knee(O * p["kg"], knee), _soft_knee(O * p["kb"], knee)
    lum = (Rc + Gc + Bc) / 3.0
    s = p["sat"]
    neb = _soft_knee(np.stack([lum + (1 + s) * (Rc - lum), lum + (1 + s) * (Gc - lum),
                               lum + (1 + s) * (Bc - lum)], -1).clip(0, None), knee)
    _snap("4合成HOO+gamma+饱和", neb)

    # ⑥ AI 降噪(**三级路由 NXT→cosmicclarity→DeepSNR**)。**保结构融合**:神经降噪把星云抹成塑料涂抹感
    #   (实测中心细节 −99.9%、高频 −95%)→ 背景全用降噪结果(干净),星云区按主体蒙版把**中频丝状结构
    #   (1.2–6px,排除最细像素噪)加回来**(dn_struct_keep 控强度,0=旧全抹行为)。低 SNR 短曝目标必开。
    #   合成图**已拉伸** → cosmicclarity/NXT 走 --no-temp-stretch;各后端读写标准 RGB(cv2 imwrite/imread 自洽,不串色)。
    neb_pre = neb.copy()
    cv2.imwrite(f"{R}/_hnb.tiff", cv2.cvtColor((neb * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))

    def _load_rgb01(path):
        im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if im is None:
            return None
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2RGB) if im.ndim == 2 else cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        mx = 65535.0 if im.dtype == np.uint16 else (255.0 if im.dtype == np.uint8 else 1.0)
        return np.clip(im.astype(np.float32) / mx, 0, 1)

    dn, _src = None, None
    try:                                                     # ① rc-astro NXT(收费,最优)
        from . import rcastro
        if rcastro.enabled():
            _o = rcastro.nxt(f"{R}/_hnb.tiff", f"{R}/_hnb_dn_nxt.tiff", denoise=0.8, timeout=timeout, log=log)
            dn, _src = _load_rgb01(_o), "rc-astro NXT"
    except Exception as e:
        log(f"[hoo] NXT 降噪失败({repr(e)[:70]})→ 退 cosmicclarity")
    if dn is None:                                           # ② 免费 cosmicclarity(GPU;已拉伸→temp_stretch=False)
        try:
            from . import setiastro
            if setiastro.available():
                _o = setiastro.denoise(f"{R}/_hnb.tiff", f"{R}/_hnb_dn_cc.tiff",
                                       luma=0.85, mode="full", temp_stretch=False, timeout=timeout, log=log)
                dn, _src = _load_rgb01(_o), "cosmicclarity"
        except Exception as e:
            log(f"[hoo] cosmicclarity 降噪失败({repr(e)[:70]})→ 退 DeepSNR")
    if dn is None and siril.deepsnr_exe():                   # ③ 免费兜底 DeepSNR
        try:
            subprocess.run([siril.deepsnr_exe(), "-i", f"{R}/_hnb.tiff", "-o", f"{R}/_hnb_dn.png",
                            "-m", "2", "-s", "480", "-q"], capture_output=True, text=True, timeout=timeout)
            if os.path.exists(f"{R}/_hnb_dn.png"):
                dn, _src = _load_rgb01(f"{R}/_hnb_dn.png"), "DeepSNR"
        except Exception as e:
            log(f"[hoo] DeepSNR 降噪失败({repr(e)[:70]})")

    if dn is not None:
        if dn.shape[:2] != neb_pre.shape[:2]:
            dn = cv2.resize(dn, (neb_pre.shape[1], neb_pre.shape[0]), interpolation=cv2.INTER_LINEAR)
        neb = dn
        if dn_struct_keep > 0:
            Lb = cv2.GaussianBlur(neb_pre.mean(2), (0, 0), 12)
            Lb = (Lb - Lb.min()) / (Lb.max() - Lb.min() + 1e-6)
            wneb = _smooth01(Lb, 0.12, 0.45)[..., None]          # 星云区高、背景低
            struct = cv2.GaussianBlur(neb_pre, (0, 0), 1.2) - cv2.GaussianBlur(neb_pre, (0, 0), 6)
            neb = np.clip(dn + wneb * dn_struct_keep * struct, 0, 1)
            log(f"[hoo] {_src} 保结构融合:星云区加回中频丝结构 keep={dn_struct_keep}(免塑料涂抹感)")
        else:
            log(f"[hoo] {_src} 降噪彩色合成图(全抹)")
    else:
        log("[hoo] [!] 无 NXT/cosmicclarity/DeepSNR → 跳过降噪(背景会偏噪;配 deepsnr_path 或装 SASpro)")
    _snap("5AI降噪", neb)
    # ⑥b 背景色度降噪:DeepSNR 后 **R(Ha)噪声仍是 G/B 两倍**(拜耳 1/4 采样,实测 Rσ10.7 vs G5.6/B4.9)
    #     → 背景红斑点扎眼。护亮度+护主体,只压背景色度。
    neb = _chroma_denoise_bg(neb, strength=chroma_dn, log=log)
    _snap("6背景色度降噪", neb)

    # 星点层:默认从 HOO 自身去梯度 master 出(双窄带星→去饱和成近中性);
    #   **rgb_star_src 给了 → RGB+HO**:从 IRCUT 宽带 master 出**真彩星点**(SPCC 真色),配准到 HOO 场后
    #   StarNet 取星层,**保留真实颜色**(不去饱和)→ HOO 星云 + RGB 星点。用户 NGC6992 要的正是这个。
    keep_star_color = False
    if rgb_star_src:
        st = _rgb_star_layer(rgb_star_src, ref_fit=f"{R}/{bgesrc}.fit", sn=sn,
                             sensor_hint=rgb_star_hint, timeout=timeout, log=log)
        keep_star_color = st is not None
    if not keep_star_color:                              # 无 RGB 源或失败 → 退回 HOO 自身星点
        siril.run_script([f"cd {R}", f"load {bgesrc}", "autostretch -2.8 0.16", "save _hrgb"], timeout=timeout)
        from . import startools                            # 三级去星(SXT→darkstar→StarNet2)取 HOO 自身星层
        _, st = startools.remove_stars(_load_mono3(f"{R}/_hrgb.fit"), tag="hoostar",
                                       s_tile=256, timeout=timeout, log=log)
    st = np.clip(st - np.median(st.reshape(-1, 3), 0), 0, 1)
    # **星点层去噪斑**:StarNet 的 stars 输出里混着大量噪点小斑,screen 回来会把降噪成果又抬回去
    #   (NGC6992 实测:降噪后 σ6.31 → 合星后 9.30)。按分位地板 + 软过渡只留真星点。
    if star_floor > 0:
        lst0 = st.mean(2)
        thr = float(np.percentile(lst0, 100.0 - star_floor))       # 只留最亮的 star_floor% 像素为星
        keep = _smooth01(lst0, thr * 0.6, thr)[..., None]
        st = st * keep
        log(f"[hoo] 星点层去噪斑(地板 p{100 - star_floor:.1f},软过渡):只留真星点,免把噪声 screen 回来")
    lst = st.mean(2, keepdims=True)
    if keep_star_color:
        st = np.clip(lst + star_sat * (st - lst), 0, 1)   # RGB 真彩星点:保色(star_sat 控饱和)
        log(f"[hoo] RGB 真彩星点(宽带 SPCC 色,饱和 {star_sat})→ screen 合到 HOO 星云上")
    else:
        st = np.clip(lst + 0.25 * (st - lst), 0, 1)       # 双窄带星点去饱和到近中性
    _snap("7星点层", st)
    fin = 1 - (1 - neb) * (1 - np.clip(st * 0.9, 0, 1))
    _snap("8合星点screen", fin)

    # ⑦ 先裁叠加抖动边缘带(线性只 +1%、拉伸后放大成亮/暗带,如底部带被搓成右下暗红 blob;HOO 边缘带
    #    较大 → max_frac 放宽 0.22)→ 再背景去 teal + 抬中性灰(在裁净的图上采样,边缘带不再污染 → 顺带改善发青)。
    from .rgb_engine import _autocrop_edges, remove_residual_glow
    fin = _autocrop_edges(fin, max_frac=edge_crop, log=log)
    _snap("9裁边", fin)
    # **径向背景收尾**:补线性 subsky 之漏的残留渐变/辉光。**默认 glow_mode="off"**——梯度本该在线性阶段
    #   subsky 治(PI铁律),这步 post-stretch 补漏实测弊大于利:干净背景上强开会造 moat/伪灰尘投影/红青麻点
    #   (SH2-308),占满画幅星云还会被当辉光减掉(IC1805/玫瑰);auto 又对付不了修不掉的红角(白跑还更噪)。
    #   真有 post-subsky 残留渐变(如个别 NGC6992)才显式开 "on"(+neb_protect 护占满画幅星云)。
    fin = remove_residual_glow(fin, mode=glow_mode, neb_protect=glow_neb_protect, log=log)
    _snap("10残留辉光+径向背景", fin)
    fin = _neutralize_bg_color(fin, target=p["bg_gray"], log=log)
    _snap("11背景去teal+抬灰(终)", fin)

    out = str(out_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    Image.fromarray((np.clip(fin, 0, 1) * 255).astype(np.uint8)).save(out + ".png", optimize=True)
    log(f"[hoo] 完成 → {out}.png(全程零 PixInsight)")
    return out + ".png"


# ── 从目录/文件一把梭(GUI 用)────────────────────────────────────────────────
def run_hoo_from_dir(src: str, out_noext: str, *, palette: str = "oiii",
                     timeout: float = 1800.0, log=print) -> str:
    """从 OSC 双窄带输入一把梭出 HOO 成片。src 可为单张整合 master 或 registered 子帧目录
    (目录则先 Siril 整合)。GUI 入口。"""
    import glob
    R = str(config.RUN_DIR)
    if os.path.isfile(src):
        master = src
    elif os.path.isdir(src):
        from .sho_engine import stack_registered
        import shutil
        subs = [x for x in glob.glob(os.path.join(src, "**", "*.xisf"), recursive=True)
                if not x.lower().endswith(".xdrz")] or glob.glob(os.path.join(src, "**", "*.fit*"), recursive=True)
        if not subs:
            raise RuntimeError(f"目录无可整合子帧:{src}")
        d = os.path.join(R, "_int_HOO")
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for x in subs:
            shutil.copy2(x, d)
        log(f"[hoo] 整合 {len(subs)} 帧双窄带子帧")
        master = stack_registered(d, os.path.join(R, "eng_HOO"), timeout=timeout)
    else:
        raise RuntimeError(f"输入不存在:{src}")
    return run_hoo(master, out_noext, palette=palette, timeout=timeout, log=log)
