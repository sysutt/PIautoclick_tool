"""圆形灰尘残影(平场校正没除净的"甜甜圈")检测。

背景:平场没做好时,校准后的图上会留下**圆形斑点**——灰尘在传感器前投下的影子/亮环。
它在整幅图里是**低频、圆对称**的亮度偏差,和真实星云结构(有丝状纹理、不圆对称)可以区分。

检测思路(纯 cv2,不占 PixInsight):
  1. 缩图 → 大尺度中值/高斯模型 → 取比值残差 `img / blur(img)`,把星云的大尺度亮度抹掉,
     只留下"局部相对偏亮/偏暗"的成分;
  2. 霍夫圆找圆形候选;
  3. **逐个复核**:量斑内 vs 环外的亮度比,再看这个偏差是否**圆对称**
     (沿环取样的离散度要远小于偏差本身)—— 这一步把"星云里恰好有个亮团"排除掉;
  4. 报告每个斑点是否**压在星云上**(`on_signal`):环外亮度显著高于全图背景即认为在星云上。

用途上的关键区别(用户经验):
  - 斑点在**空背景** → 可以直接抹掉(`dustremove` 用背景模型填平),也可以走人工平场;
  - 斑点**压在星云结构上** → **绝不能填平**(会抹掉结构),只能走**人工平场**
    (`flatpatch` op:羽化圆蒙版 + 乘性增益校正,只改低频亮度、不动结构)。
"""
from __future__ import annotations

import math
from typing import List

try:
    import cv2
    import numpy as np
except Exception:                                    # pragma: no cover
    cv2 = None
    np = None


def _odd(v: int) -> int:
    v = int(max(3, v))
    return v if v % 2 else v + 1


def detect_spots(png_path: str, full_w: int = 0, full_h: int = 0,
                 min_frac: float = 0.010, max_frac: float = 0.075,
                 min_dev: float = 0.012, max_spots: int = 6,
                 audit_path: str | None = None) -> List[dict]:
    """在(拉伸后的)预览图上找圆形灰尘斑。

    png_path : 预览 PNG(runner 的 outputs.preview 即可)
    full_w/h : 原图尺寸;给了就把坐标换算回原图像素(flatpatch 需要原图坐标)
    min_frac/max_frac : 斑点半径占图像短边的比例范围(甜甜圈通常 1%~7%)
    min_dev  : 斑内/环外相对偏差阈值(0.012 = 1.2%),低于此不值得改
    返回 [{x,y,r,gain,dev,symmetry,on_signal}]  —— 坐标/半径为**原图像素**
    """
    if cv2 is None:
        return []
    img = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []
    h, w = img.shape[:2]
    short = min(h, w)
    # 缩到短边 ~900:霍夫在这个尺度上稳,且够快
    scale = min(1.0, 900.0 / short)
    sm = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) \
        if scale < 1.0 else img.copy()
    sh, sw = sm.shape[:2]
    f = sm.astype(np.float32) + 1.0

    # 1) 比值残差:除掉大尺度亮度(星云本体),只留局部相对偏差。
    #    先重度中值滤波压掉星点与细结构 —— 灰尘斑是**平滑低频**的,星云细丝不是。
    base = cv2.medianBlur(sm, _odd(int(min(sh, sw) * 0.012))).astype(np.float32) + 1.0
    big = cv2.GaussianBlur(base, (0, 0), sigmaX=min(sh, sw) * 0.11)
    ratio = base / np.maximum(big, 1.0)
    # 【坑】别用固定的 ±6% 归一化:拉伸后的图上星云本身就摆动远超 6%,会把残差图打成
    # 近二值的"星云蒙版",霍夫就在星云边缘上乱找圆。改用**鲁棒尺度(MAD)**自适应。
    dev = ratio - 1.0
    mad = float(np.median(np.abs(dev - np.median(dev)))) * 1.4826
    nscale = max(0.004, mad * 3.0)          # 注意别和上面的缩图 scale 撞名
    disp = np.clip(dev / nscale * 127 + 128, 0, 255).astype(np.uint8)
    disp = cv2.GaussianBlur(disp, (0, 0), sigmaX=2.0)

    rmin = max(6, int(min(sh, sw) * min_frac))
    rmax = max(rmin + 4, int(min(sh, sw) * max_frac))
    circles = cv2.HoughCircles(disp, cv2.HOUGH_GRADIENT, dp=1.5,
                               minDist=rmin * 2, param1=60, param2=22,
                               minRadius=rmin, maxRadius=rmax)
    if circles is None:
        return []

    # 2) 逐个复核:偏差幅度 + 圆对称性
    med = cv2.medianBlur(sm, _odd(int(min(sh, sw) * 0.01)))       # 去星后的低频图,用于量亮度
    medf = med.astype(np.float32) / 255.0
    gmed = float(np.median(medf))                                  # 全图背景(中位)
    out: List[dict] = []
    for cx, cy, r in circles[0]:
        cx, cy, r = float(cx), float(cy), float(r)

        def ring(radius: float, npt: int) -> list:
            vals = []
            for i in range(npt):
                a = 2 * math.pi * i / npt
                x = int(round(cx + radius * math.cos(a)))
                y = int(round(cy + radius * math.sin(a)))
                if 0 <= x < sw and 0 <= y < sh:
                    vals.append(float(medf[y, x]))
            return vals

        v_in = ring(r * 0.45, 24)
        v_out = ring(r * 1.6, 48)
        if len(v_in) < 12 or len(v_out) < 24:
            continue
        a_in, a_out = float(np.median(v_in)), float(np.median(v_out))
        if a_out <= 1e-4:
            continue
        d_rel = (a_in - a_out) / a_out                             # 相对偏差,正=亮斑
        if abs(d_rel) < min_dev:
            continue
        # 判据 A:**环外**要齐(圆对称)。真灰尘斑周围亮度一致;星云边缘上环外一半亮一半暗。
        spread_out = float(np.percentile(v_out, 84) - np.percentile(v_out, 16))
        sym = spread_out / max(1e-4, abs(a_in - a_out))
        if sym > 0.8:
            continue
        # 判据 B:**斑内**也要齐。灰尘斑内部是平滑的一片;星云暗团/亮结内部起伏大。
        spread_in = float(np.percentile(v_in, 84) - np.percentile(v_in, 16))
        if spread_in > 0.9 * abs(a_in - a_out):
            continue
        # 判据 C:**径向要一致**。沿 0.3r / 0.6r / 0.9r 三个半径都应与环外同号偏离,
        # 且幅度单调不反号 —— 星云结构常在某个半径上就翻号了。
        radial = [float(np.median(ring(r * k, 20)) or 0) - a_out for k in (0.3, 0.6, 0.9)]
        if any((v > 0) != (d_rel > 0) for v in radial if abs(v) > 1e-4):
            continue
        # 判据 D:幅度别太大。平场残差通常几个百分点;>35% 的"圆斑"基本是真结构。
        if abs(d_rel) > 0.35:
            continue
        k = 1.0 / scale if scale < 1.0 else 1.0
        sx, sy = (full_w / w if full_w else 1.0), (full_h / h if full_h else 1.0)
        out.append({
            "x": round(cx * k * sx, 1), "y": round(cy * k * sy, 1),
            "r": round(r * k * max(sx, sy), 1),
            "gain": round(a_in / a_out, 4), "dev": round(d_rel, 4),
            "symmetry": round(sym, 3),
            # 环外亮度明显高于全图背景 → 斑点压在星云/信号上 → 只能人工平场,不能填平
            "on_signal": bool(a_out > gmed * 1.25 + 0.01),
        })
    out.sort(key=lambda d: -abs(d["dev"]))
    out = out[:max_spots]
    if audit_path:
        vis = cv2.cvtColor(disp, cv2.COLOR_GRAY2BGR)
        for s in out:
            x = int(s["x"] / (full_w / w) / (1 / scale)) if full_w else int(s["x"] * scale)
            y = int(s["y"] / (full_h / h) / (1 / scale)) if full_h else int(s["y"] * scale)
            rr = int(s["r"] * scale / (max(full_w / w, full_h / h) if full_w else 1))
            cv2.circle(vis, (x, y), max(3, rr), (0, 0, 255), 2)
        cv2.imwrite(audit_path, vis)
    return out


def fit_at(png_path: str, cx: float, cy: float, rmax_frac: float = 0.12) -> dict:
    """用户点中心 → 在该点自动拟合灰尘环的半径与增益(比盲检可靠:已知在哪找)。

    cx/cy : 在**该 png 像素坐标系**里的点击位置。
    返回 {r, gain, dev}(r 为 png 像素;gain=斑内/环外亮度比;dev=相对偏差)或 {}。
    做法:以点击点为心,扫多个半径,取"斑内(0.45r)与环外(1.6r)亮度差随 r 变化最显著"的 r。
    """
    if cv2 is None:
        return {}
    img = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {}
    h, w = img.shape[:2]
    med = cv2.medianBlur(img, _odd(int(min(h, w) * 0.008))).astype(np.float32) / 255.0
    cx, cy = float(cx), float(cy)

    def ring(radius, npt):
        v = []
        for i in range(npt):
            a = 2 * math.pi * i / npt
            x = int(round(cx + radius * math.cos(a)))
            y = int(round(cy + radius * math.sin(a)))
            if 0 <= x < w and 0 <= y < h:
                v.append(float(med[y, x]))
        return v

    rmax = max(10, int(min(h, w) * rmax_frac))
    best = {}
    for r in range(8, rmax, 3):
        vin = ring(r * 0.45, 24)
        vout = ring(r * 1.6, 48)
        if len(vin) < 12 or len(vout) < 24:
            continue
        a_in = float(np.median(vin)); a_out = float(np.median(vout))
        if a_out <= 1e-4:
            continue
        dev = (a_in - a_out) / a_out
        if not best or abs(dev) > abs(best["dev"]):
            best = {"r": float(r), "gain": round(a_in / a_out, 4), "dev": round(dev, 4)}
    return best


def describe(spots: List[dict]) -> str:
    if not spots:
        return "未检出圆形灰尘残影"
    parts = []
    for s in spots:
        parts.append("(%.0f,%.0f) r=%.0f 偏差%+.1f%% %s"
                     % (s["x"], s["y"], s["r"], s["dev"] * 100,
                        "压在星云上→只做人工平场" if s["on_signal"] else "空背景"))
    return "检出 %d 处:" % len(spots) + ";".join(parts)
