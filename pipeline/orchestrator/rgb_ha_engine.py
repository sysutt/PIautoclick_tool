"""无 PI RGB+H/HO 引擎(zero-PixInsight 宽带 RGB + 窄带 Ha/OIII 增强)。

给宽带 RGB 底加窄带 Ha/OIII(星系 HII 红结、发射区)。M31(2600mc RGB + HO)验证,2026-08-14。
见 [[rgb-narrowband-blend]]。与 rgb_engine / hoo_engine / sho_engine 并列。

管线:
  ① RGB 底:rgb_engine.run_rgb(真 SPCC 自然色 + 拉伸 + 蒙版降噪 + 中性灰)。
  ② **配准 HO→RGB**:同框独立叠加仍有位移;**相位相关会被平滑星系带偏 → 必须 Siril 星点配准**
     (RGB 设为参考不动,匹配已处理的底)。split 出对齐的 Ha=R / OIII=G。
  ③ **连续谱扣除必须在线性**:`Ha_em = clip(Ha_lin − k·R_lin, 0)`,k 按中亮像素连续谱匹配。
  ④ HII 提取:降噪 + **黑点拒噪拉伸**(否则拉伸把噪声放大满屏);黑点越低范围越大。
  ⑤ 可选**灰尘投影蒙版消除**(按蓝紫 B−G 自动检测弥漫斑、protect 排除伴星系、中和色度)。
  ⑥ 融合:Ha screen 进 R(+微 B 出粉)、OIII 进 G/B(青)+ 红花区去饱和(降艳)。中性灰收尾。
"""
from __future__ import annotations

import os
import shutil
import subprocess  # noqa: F401  (预留)

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

from . import config, siril, rgb_engine
from .sho_engine import neutral_gray

PRESETS: dict[str, dict] = {
    # 星系(如 M31):Ha 力度/去饱和/黑点(范围)/OIII 力度
    "galaxy": dict(ha_strength=1.6, ha_desat=0.3, ha_black_sigma=1.3, oiii_strength=0.4),
    # HII 更跳(暗弱发射星系)
    "vivid":  dict(ha_strength=2.0, ha_desat=0.2, ha_black_sigma=1.2, oiii_strength=0.5),
}


def _lum(x: np.ndarray) -> np.ndarray:
    return 0.30 * x[..., 0] + 0.59 * x[..., 1] + 0.11 * x[..., 2]


def _smooth(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _rd(p: str) -> np.ndarray:
    a = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    if a.ndim == 3 and a.shape[2] == 3:
        return cv2.cvtColor(a, cv2.COLOR_BGR2RGB).astype(np.float32) / (65535.0 if a.dtype == np.uint16 else 255.0)
    return a.astype(np.float32) / (65535.0 if a.dtype == np.uint16 else 255.0)


def _rd_mono(p: str) -> np.ndarray:
    a = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    return (a[..., 0] if a.ndim == 3 else a).astype(np.float32) / (65535.0 if a.dtype == np.uint16 else 255.0)


# ── ② 配准 HO→RGB + 提取 Ha/OIII ─────────────────────────────────────────────
def _register_ho(rgb_master: str, ho_master: str, timeout: float, log) -> tuple[np.ndarray, np.ndarray]:
    """Siril 星点配准 HO→RGB(RGB=参考,不动),split 出对齐的 Ha(R)/OIII(G)线性 numpy。
    【坑】相位相关(cv2.phaseCorrelate)会被平滑星系主导 → 位移错、星点分离;必须星点配准。"""
    R = str(config.RUN_DIR)
    rd = os.path.join(R, "_rgbha_reg")
    if os.path.exists(rd):
        shutil.rmtree(rd)
    os.makedirs(rd)
    rgbm = str(rgb_master).replace("\\", "/")
    hom = str(ho_master).replace("\\", "/")
    siril.run_script([f"cd {rd}", f'load "{rgbm}"', "save a_rgb"], timeout=timeout)      # a_ 排前 = 参考
    siril.run_script([f"cd {rd}", f'load "{hom}"', "save b_ho"], timeout=timeout)
    siril.run_script([f"cd {rd}", "convert rgbhaseq -out=.", "setref rgbhaseq 1", "register rgbhaseq"], timeout=timeout)
    regho = next((f"r_rgbhaseq_{n}" for n in ("00002", "00001") if os.path.exists(f"{rd}/r_rgbhaseq_{n}.fit")), None)
    if not regho:
        raise RuntimeError("HO 星点配准失败(无 registered 帧)")
    siril.run_script([f"cd {R}", f'load "{rd}/{regho}"', "subsky 1",
                      "split _rgbha_haR _rgbha_oiG _rgbha_xB",
                      "load _rgbha_haR", "savetif _rgbha_ha16",
                      "load _rgbha_oiG", "savetif _rgbha_oi16"], timeout=timeout)
    return _rd_mono(f"{R}/_rgbha_ha16.tif"), _rd_mono(f"{R}/_rgbha_oi16.tif")


# ── ③④ 连续谱扣除 + HII 提取 ─────────────────────────────────────────────────
def _extract_emission(nb: np.ndarray, cont: np.ndarray, black_sigma: float, smooth_sig: float = 2.6) -> np.ndarray:
    """连续谱扣除(线性 nb−k·cont,k 按中亮连续谱匹配)+ 降噪 + **黑点拒噪拉伸** → 发射(HII)层 [0,1]。
    black_sigma 越小 → 黑点越低 → HII 范围越大(但太低会起噪)。"""
    h, w = nb.shape

    def bgs(a):
        return a - np.median(a[:int(h * .06), :int(w * .06)])
    nb, cont = bgs(nb), bgs(cont)
    m = (cont > np.percentile(cont, 82)) & (cont < np.percentile(cont, 99))
    k = float(np.median(nb[m] / (cont[m] + 1e-5)))
    em = np.clip(nb - k * cont, 0, 1)
    em = gaussian_filter(em, smooth_sig) if gaussian_filter is not None else cv2.GaussianBlur(em, (0, 0), smooth_sig)
    bg = em[:int(h * .10), :int(w * .10)]
    nf = np.median(bg) + black_sigma * bg.std()
    return np.clip((em - nf) / (np.percentile(em, 99.95) - nf + 1e-6), 0, 1) ** 0.55


# ── ⑤ 灰尘投影蒙版消除(可选)─────────────────────────────────────────────────
def remove_dust_blob(rgb: np.ndarray, box: tuple, protect: list | None = None, log=print) -> np.ndarray:
    """蒙版消灰尘投影(平场没除净的蓝紫弥漫残影)。box=(x0,x1,y0,y1) 相对坐标,限定检测范围避开亮区;
    protect=[(cx,cy,rx,ry)…] 相对坐标椭圆(排除伴星系等真天体)。按蓝紫(B−G)自动检测弥漫斑、
    **中和色度**(减平滑色度,保星点/亮度)。灰尘蒙版消除的通法(和暖色伴星系按颜色区分)。"""
    h, w, _ = rgb.shape
    x0, x1, y0, y1 = int(box[0] * w), int(box[1] * w), int(box[2] * h), int(box[3] * h)
    bp = cv2.GaussianBlur(rgb[..., 2] - rgb[..., 1], (0, 0), 18)
    boxm = np.zeros((h, w), np.float32)
    boxm[y0:y1, x0:x1] = 1
    thr = np.percentile(bp[boxm > 0], 60)
    blob = _smooth(bp, thr * 0.4, thr) * boxm
    if protect:
        Y, X = np.ogrid[:h, :w]
        for (cx, cy, rx, ry) in protect:
            blob[((X - cx * w) / (rx * w)) ** 2 + ((Y - cy * h) / (ry * h)) ** 2 < 1] = 0
    blob = cv2.GaussianBlur(blob, (0, 0), 30)
    blob = blob / max(blob.max(), 1e-6) * 0.95
    lum = _lum(rgb)
    out = rgb.copy()
    for c in range(3):
        out[..., c] = np.clip(rgb[..., c] - cv2.GaussianBlur(rgb[..., c] - lum, (0, 0), 18) * blob, 0, 1)
    log("[rgbha] 灰尘投影蒙版消除")
    return out


# ── ⑥ 融合 ───────────────────────────────────────────────────────────────────
def _blend(base: np.ndarray, hae: np.ndarray, oie: np.ndarray,
           ha_strength: float, ha_desat: float, oiii_strength: float) -> np.ndarray:
    """screen 融合:Ha→R(+微 B 出粉红)、OIII→G/B(青)+ 红花区往亮度去饱和(降艳)。"""
    o = base.copy()
    o[..., 0] = 1 - (1 - o[..., 0]) * (1 - np.clip(hae * ha_strength, 0, 1))
    o[..., 2] = 1 - (1 - o[..., 2]) * (1 - np.clip(hae * ha_strength * 0.28, 0, 1))
    o[..., 1] = 1 - (1 - o[..., 1]) * (1 - np.clip(oie * oiii_strength, 0, 1))
    o[..., 2] = 1 - (1 - o[..., 2]) * (1 - np.clip(oie * oiii_strength, 0, 1))
    m = np.clip(hae * ha_strength, 0, 1)[..., None]
    L = _lum(o)[..., None]
    return np.clip(o * (1 - ha_desat * m) + L * (ha_desat * m), 0, 1)


# ── 主编排器 ─────────────────────────────────────────────────────────────────
def run_rgb_ha(rgb_master: str, ho_master: str, out_noext: str, *, palette: str = "natural",
               preset: str = "galaxy", sensor: str | None = None, oscfilter: str | None = None,
               dust_box: tuple | None = None, dust_protect: list | None = None,
               overrides: dict | None = None, timeout: float = 1800.0, log=print) -> str:
    """无 PI RGB+H/HO 全流程。rgb_master=宽带 OSC master,ho_master=双窄带 OSC master。
    palette=RGB 底预设(rgb_engine);preset=融合旋钮(PRESETS);sensor/oscfilter=SPCC 传感器/滤镜。
    dust_box/dust_protect=可选灰尘蒙版消除。返回成片 <out>.png。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python(cv2)")
    R = str(config.RUN_DIR)
    p = {**PRESETS[preset], **(overrides or {})}
    log(f"[rgbha] preset={preset} palette={palette} 旋钮={p}")

    # ① RGB 底(SPCC + 拉伸 + 降噪 + 中性灰)
    base_png = rgb_engine.run_rgb(rgb_master, os.path.join(R, "_rgbha_base"), palette=palette,
                                  sensor=sensor, oscfilter=oscfilter, timeout=timeout, log=log)
    base = _rd(base_png)

    # 校准后线性 RGB(rgb_engine.calibrate 存的 _rgbcal_cal;做连续谱扣除的 R/G)
    calf = next((f"_rgbcal_cal" for e in (".fit", ".fits", ".tif") if os.path.exists(f"{R}/_rgbcal_cal{e}")), None)
    if not calf:
        raise RuntimeError("找不到校准线性图 _rgbcal_cal")
    siril.run_script([f"cd {R}", "load _rgbcal_cal", "savetif _rgbha_lin"], timeout=timeout)
    lin = _rd(f"{R}/_rgbha_lin.tif")
    Rl, Gl = lin[..., 0], lin[..., 1]

    # ② 配准 HO→RGB + split 对齐 Ha/OIII
    log("[rgbha] 配准 HO→RGB(Siril 星点配准)…")
    ha_lin, oi_lin = _register_ho(rgb_master, ho_master, timeout, log)

    # ③④ 连续谱扣除 + HII 提取
    hae = _extract_emission(ha_lin, Rl, p["ha_black_sigma"])
    oie = _extract_emission(oi_lin, Gl, p["ha_black_sigma"])

    # ⑤ 灰尘投影蒙版消除(可选)
    if dust_box:
        base = remove_dust_blob(base, dust_box, dust_protect, log=log)

    # ⑥ 融合 + 中性灰
    out = _blend(base, hae, oie, p["ha_strength"], p["ha_desat"], p["oiii_strength"])
    out = neutral_gray(out)

    o = str(out_noext).replace("\\", "/")
    if o.lower().endswith(".png"):
        o = o[:-4]
    Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(o + ".png", optimize=True)
    log(f"[rgbha] 完成 → {o}.png(RGB 底 + Ha/OIII 增强,全程零 PixInsight)")
    return o + ".png"


def run_rgb_ha_from_dirs(rgb_src: str, ho_src: str, out_noext: str, *, palette: str = "natural",
                         preset: str = "galaxy", sensor: str | None = None, oscfilter: str | None = None,
                         dust_box: tuple | None = None, dust_protect: list | None = None,
                         timeout: float = 1800.0, log=print) -> str:
    """GUI 入口:RGB 与 HO 各为单张 master 或子帧目录(目录先 Siril 整合)。"""
    import glob
    from .sho_engine import stack_registered

    def _to_master(src, tag):
        if os.path.isfile(src):
            return src
        subs = [x for x in glob.glob(os.path.join(src, "**", "*.xisf"), recursive=True)
                if not x.lower().endswith(".xdrz")] or glob.glob(os.path.join(src, "**", "*.fit*"), recursive=True)
        if not subs:
            raise RuntimeError(f"{tag} 目录无子帧:{src}")
        d = os.path.join(str(config.RUN_DIR), f"_int_{tag}")
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for x in subs:
            shutil.copy2(x, d)
        log(f"[rgbha] 整合 {tag} {len(subs)} 帧")
        return stack_registered(d, os.path.join(str(config.RUN_DIR), f"eng_{tag}"), timeout=timeout)

    rgb_m = _to_master(rgb_src, "RGB")
    ho_m = _to_master(ho_src, "HO")
    if sensor is None:
        sensor, oscfilter = rgb_engine.guess_sensor(rgb_src)
    return run_rgb_ha(rgb_m, ho_m, out_noext, palette=palette, preset=preset, sensor=sensor,
                      oscfilter=oscfilter, dust_box=dust_box, dust_protect=dust_protect,
                      timeout=timeout, log=log)
