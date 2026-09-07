# -*- coding: utf-8 -*-
"""原始子帧的快速解拜耳 + 自动拉伸预览(筛帧用)。

用途:原始素材叠加前,让用户目视快速筛掉有问题的单帧(云/梯度/拖线/对焦跑焦),
WBPP 的加权剔除对这类整帧劣化常无能为力(尤见 M20:混入的坏帧把背景拉出梯度)。

设计取舍:
- **超像素解拜耳**(2×2 拜耳块 → 1 个 RGB 像素:R、(G1+G2)/2、B)。零插值、纯 numpy、极快,
  半分辨率对"看清是不是坏帧"完全够用(坏帧的云/梯度/拖线是大尺度特征)。
- **STF 自动拉伸**(PixInsight 同款 MTF:中值+MAD 定黑点、把中值抬到 ~0.25)。三通道共用同一条
  传递函数(而非逐通道各自拉伸)→ 保留真实色差,云/月光造成的偏色、亮背景一眼可辨。
- 背景中值(拉伸前、归一化后)作为**客观坏帧线索**:云/月光/梯度会显著抬高背景 → 供"自动标记异常"。

纯计算、无 Qt 依赖;QImage 转换在 app_ui 侧做。FITS 走 astropy,XISF 走 xisf 库。
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

_FITS_EXT = (".fit", ".fits", ".fts")

# 设备 → 默认拜耳阵列(头里有 BAYERPAT 时以头为准,这里只作兜底)
DEVICE_BAYER = {"dwarf": "RGGB", "seestar": "GRBG"}


def _read_array(path: str):
    """读单帧原始数据 → (ndarray, header_dict)。FITS 用 astropy,XISF 用 xisf 库。
    返回的 ndarray 可能是 2D(拜耳)或 3D(已彩色);header_dict 至少可能含 'BAYERPAT'。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in _FITS_EXT:
        from astropy.io import fits
        with fits.open(path, memmap=False) as hdul:
            hdu = None
            for h in hdul:                      # 取第一个带图像数据的 HDU(通常是主 HDU)
                if getattr(h, "data", None) is not None and np.ndim(h.data) >= 2:
                    hdu = h
                    break
            if hdu is None:
                raise ValueError("FITS 无图像数据")
            data = np.asarray(hdu.data)
            hdr = {k.upper(): hdu.header[k] for k in hdu.header.keys() if k}
        return data, hdr
    if ext == ".xisf":
        from xisf import XISF
        x = XISF(path)
        data = np.asarray(x.read_image(0))
        hdr = {}
        try:                                    # XISF 的 BAYERPAT 在 image 属性 ColorFilterArray 里
            meta = x.get_images_metadata()[0]
            cfa = (meta.get("ColorFilterArray") or {}).get("pattern") if isinstance(meta, dict) else None
            if cfa:
                hdr["BAYERPAT"] = cfa
        except Exception:
            pass
        return data, hdr
    raise ValueError(f"不支持的格式:{ext}")


def _to_float01(a: np.ndarray) -> np.ndarray:
    """任意位深 → float32 的 0..1(整数按位深满量程归一;浮点按范围自适应)。"""
    a = np.asarray(a)
    if np.issubdtype(a.dtype, np.integer):
        info = np.iinfo(a.dtype)
        lo = 0.0 if info.min >= 0 else float(info.min)
        rng = float(info.max) - lo
        return (a.astype(np.float32) - lo) / (rng if rng > 0 else 1.0)
    a = a.astype(np.float32)
    mx = float(np.nanmax(a)) if a.size else 1.0
    if mx <= 1.5:                               # 已是 0..1 显示域
        return np.clip(np.nan_to_num(a), 0.0, 1.0)
    if mx <= 255.0:
        return np.clip(np.nan_to_num(a) / 255.0, 0.0, 1.0)
    if mx <= 65535.0:                           # astropy 对 BZERO=32768 的 int16 会还原成 0..65535 浮点
        return np.clip(np.nan_to_num(a) / 65535.0, 0.0, 1.0)
    return np.clip(np.nan_to_num(a) / mx, 0.0, 1.0)


def _superpixel(bayer: np.ndarray, pat: str) -> np.ndarray:
    """2×2 拜耳块 → 半分辨率 RGB(超像素法,零插值)。pat 为左上起 4 格的 CFA 排列。"""
    h, w = bayer.shape[:2]
    h -= h % 2
    w -= w % 2
    b = bayer[:h, :w]
    cells = {"00": b[0::2, 0::2], "01": b[0::2, 1::2],
             "10": b[1::2, 0::2], "11": b[1::2, 1::2]}
    order = ("00", "01", "10", "11")
    pat = (pat or "RGGB").upper()
    if len(pat) != 4 or any(c not in "RGB" for c in pat):
        pat = "RGGB"
    greens, red, blue = [], None, None
    for ch, key in zip(pat, order):
        if ch == "G":
            greens.append(cells[key])
        elif ch == "R":
            red = cells[key]
        else:
            blue = cells[key]
    if red is None or blue is None or not greens:   # 阵列异常 → 退化成灰度三连
        g = b[0::2, 0::2]
        return np.stack([g, g, g], axis=-1)
    green = greens[0] if len(greens) == 1 else (greens[0] + greens[1]) * 0.5
    return np.stack([red, green, blue], axis=-1)


def read_debayer_float(path: str, pat_hint: Optional[str] = None, reduce: bool = True):
    """读一帧 → (rgb float32 HxWx3 0..1, meta)。2D 拜耳按超像素解;3D 直接当彩色。
    meta = {pat, bg(拉伸前背景中值), w, h, mono}。"""
    data, hdr = _read_array(path)
    pat = (str(hdr.get("BAYERPAT") or pat_hint or "")).strip() or None
    mono = False
    if data.ndim == 2:
        f = _to_float01(data)
        if pat:                                 # 有拜耳阵列(头 BAYERPAT 或设备提示)→ 超像素解拜耳
            rgb = _superpixel(f, pat) if reduce else np.stack([f, f, f], axis=-1)
        else:                                   # 无阵列 = 黑白相机原始帧 → 灰度(不造假色),大图降采样加速
            g = f[::2, ::2] if (reduce and max(f.shape) > 2200) else f
            rgb = np.stack([g, g, g], axis=-1)
            mono = True
    else:
        if data.shape[0] in (1, 3, 4) and data.shape[0] < data.shape[-1]:
            data = np.moveaxis(data, 0, -1)     # (C,H,W) → (H,W,C)
        f = _to_float01(data)
        rgb = f[:, :, :3] if f.shape[2] >= 3 else np.repeat(f[:, :, :1], 3, axis=2)
        if reduce and max(rgb.shape[:2]) > 2200:
            rgb = rgb[::2, ::2, :]              # 已彩色的大图也降半采样加速
    bg = float(np.median(rgb)) if rgb.size else 0.0
    return rgb.astype(np.float32), {"pat": pat or ("mono" if mono else "RGGB"),
                                    "bg": bg, "h": int(rgb.shape[0]), "w": int(rgb.shape[1]),
                                    "mono": mono}


def _stf_midtone(v: float, target: float = 0.25) -> float:
    """求 MTF 的中调参数 m,使 mtf(v)=target(v=黑点裁剪后的归一化中值)。闭式解。"""
    v = float(np.clip(v, 1e-6, 1.0 - 1e-6))
    denom = (2.0 * target * v - target - v)
    if abs(denom) < 1e-9:
        return 0.5
    return float(np.clip(v * (target - 1.0) / denom, 1e-4, 1.0 - 1e-4))


def _mtf(x: np.ndarray, m: float) -> np.ndarray:
    """PixInsight 中调传递函数,m∈(0,1) 单调把 [0,1]→[0,1]。"""
    x = np.clip(x, 0.0, 1.0)
    num = (m - 1.0) * x
    den = (2.0 * m - 1.0) * x - m
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den
    return np.clip(np.nan_to_num(out), 0.0, 1.0)


def fast_stretch(rgb: np.ndarray, target: float = 0.25, shadow_sigma: float = 2.8) -> np.ndarray:
    """STF 自动拉伸:按亮度中值+MAD 定黑点、把中值抬到 target。三通道共用一条曲线保色。"""
    lum = rgb.mean(axis=2)
    med = float(np.median(lum))
    mad = float(np.median(np.abs(lum - med)))
    mad = mad if mad > 1e-6 else 1e-6
    c0 = float(np.clip(med - shadow_sigma * 1.4826 * mad, 0.0, 1.0))
    denom = max(1.0 - c0, 1e-6)
    v = (med - c0) / denom
    m = _stf_midtone(v, target)
    x = np.clip((rgb - c0) / denom, 0.0, 1.0)
    return _mtf(x, m)


def _neutralize(rgb: np.ndarray) -> np.ndarray:
    """按逐通道中值对齐 → 背景中性灰(OSC 原始绿像素×2 天然偏绿;中性后星点更突出、
    坏帧的橙色/云/梯度反差更明显,更利于目视筛帧)。灰度图三通道相等 → 无操作。"""
    flat = rgb.reshape(-1, 3)
    med = np.median(flat, axis=0)
    if float(med.max() - med.min()) < 1e-5:      # 已中性(或灰度)
        return rgb
    ref = float(np.median(med))
    out = rgb.copy()
    for c in range(3):
        if med[c] > 1e-6:
            out[..., c] = np.clip(rgb[..., c] * (ref / med[c]), 0.0, 1.0)
    return out


def _resize_max(u8: np.ndarray, max_px: int) -> np.ndarray:
    """长边缩到 max_px(用 cv2 area,回退 numpy 步采样)。"""
    h, w = u8.shape[:2]
    long_side = max(h, w)
    if max_px <= 0 or long_side <= max_px:
        return u8
    s = max_px / float(long_side)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    try:
        import cv2
        return cv2.resize(u8, (nw, nh), interpolation=cv2.INTER_AREA)
    except Exception:
        step = max(1, long_side // max_px)
        return u8[::step, ::step, :]


def render_rgb8(path: str, pat_hint: Optional[str] = None, max_px: Optional[int] = None,
                reduce: bool = True, neutralize: bool = True):
    """完整管线:读→解拜耳→(中性化)→STF 拉伸→(可选)缩放 → (uint8 HxWx3 连续内存, stats)。
    stats = {bg, w, h, pat}。bg 为拉伸前背景中值(越高越可能有云/月光/梯度)。"""
    rgb, meta = read_debayer_float(path, pat_hint=pat_hint, reduce=reduce)
    if neutralize:
        rgb = _neutralize(rgb)
    st = fast_stretch(rgb)
    u8 = (np.clip(st, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    if max_px:
        u8 = _resize_max(u8, int(max_px))
    u8 = np.ascontiguousarray(u8)
    return u8, {"bg": meta["bg"], "w": meta["w"], "h": meta["h"], "pat": meta["pat"]}
