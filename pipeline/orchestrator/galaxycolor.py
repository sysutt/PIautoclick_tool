# -*- coding: utf-8 -*-
"""星系盘色:自动选 BN/CC 参考框 + 径向 B/G 廓线度量 + 中性交叉点。

【为什么要有这个模块(2026-09-20,用户 M31 手工 BN+CC 链)】
  用户手工用 BN+CC 做出了"外围蓝 / 核心黄 / 尘带褐"的分离,管线用 SPCC 做不出来。
  同一把尺子量两边(相对半径分档、减四角背景、量 B/G):

  | ÷核心(形状) | 1% | 3% | 6% | 11% | 16% | 25% | 核→外 | B/G 穿过 1.0 处 |
  |---|---|---|---|---|---|---|---|---|
  | 线性母版(未校色) | 1.000 | 1.028 | 1.058 | 1.131 | 1.211 | 1.273 | 1.27 | 全程同侧 |
  | 用户成品(目标)   | 1.000 | 1.092 | 1.183 | 1.283 | 1.311 | 1.365 | 1.37 | **1.6%** |
  | 管线成品         | 1.000 | 0.969 | 0.986 | 1.004 | 1.114 | 1.255 | 1.26 | **16.5~18.1%** |

  **机理**:提饱和是绕中性点放大偏离 —— B/G<1 的更黄、>1 的更蓝。所以**校准决定廓线
  落在中性线的哪一侧,饱和只负责放大**。管线把中性点推到 16% 半径,内盘中盘全在 1.0 以下,
  提饱和只会更黄,**蓝臂结构性做不出来**;这不是饱和不够。

  **解法(用户给的通用规则)**:白参考框选在**星系本体的核心亮区** → 该区被定义成中性 →
  核心 B/G≈1.0(实测用户成品 0.977)→ 比核心蓝的盘自然全在 1.0 以上。
  背景参考框选在**非边缘、无明显星点**的矩形。两个框直接喂 PI 的 BN/CC 的 useROI,
  不必建预览。

  **形状本来就在数据里**(原始线性 1.27 vs 目标 1.37),不需要"造";用户的调色只扩了 6~13%。
  管线反而把它压掉了 6~11%(拉伸毁径向色温梯度)。所以优先级:
  **白平衡 ≫ 修复拉伸压形状 ≫ 提饱和**。

见 [[pi-neutral-crossover]]。
"""
from __future__ import annotations

import numpy as np

# 相对半径分档(除以图像短边),消掉分辨率差异 —— 度量必须是尺度不变量
FRACS = [(0.00, 0.02), (0.02, 0.045), (0.045, 0.08), (0.08, 0.13),
         (0.13, 0.20), (0.20, 0.30), (0.30, 0.45)]
MIDS = [0.5 * (a + b) for a, b in FRACS]

# 星系类盘色目标廓线(B/G,按相对半径)。来源:用户手工成品
#   M:/deepsky_output/D3 Messier/250726-260912_D3_M31/Image11.jpg(2026-09-20 实测)
# 用户 2026-09-20 拍板:**以他自己的成品为准**,拿不到才退回 AstroBin 共识。
HOUSE_BG_TARGET = [0.977, 1.067, 1.155, 1.253, 1.281, 1.333, 1.154]
HOUSE_RG_TARGET = [1.237, 1.333, 1.408, 1.380, 1.246, 1.167, 1.077]
# 中性交叉点(B/G=1)的目标相对半径:紧贴核心外沿
CROSS_TARGET = 0.016
CROSS_BAND = (0.008, 0.045)


def _gauss(a, s):
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(a, s)


def _locate_prep(lum, target_short: float = 512.0):
    """定位前的预处理:降采样 → **压点源**(中值) → **温和压高光**(sqrt)。返回 (小图, 缩放系数)。

    【为什么必须压点源(2026-09-23 M51/M81 事故)】原来只做「高通去梯度 + 取峰」。可是在**线性**
    数据上一颗亮星的峰值是 0.0736 = 全图中位的 **98 倍**,而星系核只有 0.0026 ——
    **星比星系核亮 28 倍**,取峰必然选中星。实测两个目标都中招:M51 选到距真核 **1522px**、
    M81 距 **1547px** 的位置,于是 BN+CC 的白参考框落在**空天区**上 → 本体白平衡整个失准。
    上一次(M33)的修法是「扣掉 S/5 的大尺度」,那治的是**残留梯度**,治不了亮星;
    而且置信度对错误答案给出 **76.8σ** —— **高置信度只说明它很确信,不说明它对**。

    【为什么先降采样】定位只需 ~10px 精度,而全分辨率上 σ≈410px 的高斯要 28s/次。
    降到短边 ~512 后整条链在小图上跑,快两个量级,量化误差 ≤ 缩放系数。
    """
    from scipy.ndimage import median_filter
    a = np.asarray(lum, dtype=np.float64)
    S0 = min(a.shape)
    f = int(max(1, round(float(S0) / float(target_short))))
    if f > 1:
        H2, W2 = (a.shape[0] // f) * f, (a.shape[1] // f) * f
        a = a[:H2, :W2].reshape(H2 // f, f, W2 // f, f).mean(axis=(1, 3))
    x = median_filter(a, size=5)                      # 点源整片削掉;星再亮也只是个点
    x = np.clip(x - float(np.median(x)), 0.0, None)
    hi = float(np.percentile(x, 99.99))
    if hi > 1e-12:
        # 【压高光用 sqrt,不要 MTF(2026-09-23 订正)】压高光是为了别让亮星在平滑后赢过天体,
        #   但**压过头会把天体自己相对周围的优势也压平** —— 于是大片中亮区反而能赢。
        #   实测 MTF m=0.02 在非线性图上把中心选到距真核 386px 处(真核平滑值 0.214、
        #   选中处只有 0.169 = 险胜翻车);而且 m 取 0.02/0.10/0.20 表现**非单调**,
        #   说明那条路本身不稳。五种输入(手动非线性/固定D非线性/线性去星/线性校色后/成片)扫下来:
        #     只中值        18 / 18 / **1195** / **1195** / 16 px
        #     **中值+sqrt   13 / 13 / 18 / 16 / 9 px** ← 唯一全过
        #     MTF m=0.20    13 / 13 / 22 / **1250** / 8
        #     MTF m=0.10     9 /  9 / **1262** / **1262** / **382**
        #     MTF m=0.02     0 / **386** / 16 / 8 / **385**
        x = np.sqrt(np.clip(x / hi, 0.0, 1.0))
    return x, f


def find_center(img, with_conf=False):
    """找星系本体中心。返回 (cx, cy);with_conf=True 时返回 (cx, cy, 置信度σ)。

    【必须先扣掉「远大于天体」的尺度(2026-09-22 M33 事故)】原来只做一次 S/35 平滑再 argmax。
    平滑挡得住热点和亮星,**挡不住残留梯度** —— M33 是低面亮度正向螺旋,线性图上
    峰/中位只有 **1.17**,于是梯度高的那一侧成了"最亮点":实测选中 x=3448,
    而拉伸图上的真中心在 x=1903,**差 1545 像素**。
    → 先减掉 S/5 尺度的背景(只留天体尺度的结构),再取峰;并给出**置信度**(峰高 / MAD 的 σ 数),
      置信度目前**只是个读数,没有任何调用方在用它做闸** —— 别照字面以为有保护。
      (先前这里写着「低于阈值时调用方不许用,见 auto_reference_rois 的 coreConf」,
       而 auto_reference_rois 根本没有这个闸;注释描述了一个不存在的保护,比没有注释更危险。)
    ⚠ 反过来**不成立**:2026-09-23 实测它对一颗亮星给出 76.8σ 的高置信度 ——
      置信度只说明峰有多突出,不说明峰是不是天体。点源必须在 `_locate_prep` 里先去掉。

    实测(M51,真核 (1929,971)):**线性去星 / 线性校色后 / 非线性调色前 / 非线性面板输出**
    四种输入误差都只有 3~5px;修前两种线性输入均偏 1522px。
    """
    lum = img.mean(-1) if img.ndim == 3 else img
    small, f = _locate_prep(np.asarray(lum, dtype=np.float64))
    S = min(small.shape)
    flat = _gauss(small, S / 35.0) - _gauss(small, S / 5.0)
    cy, cx = np.unravel_index(int(np.argmax(flat)), flat.shape)
    v = flat.ravel()
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med))) * 1.4826
    conf = (float(flat[cy, cx]) - med) / max(mad, 1e-12)
    cx, cy = int(cx * f + f // 2), int(cy * f + f // 2)
    if with_conf:
        return cx, cy, float(conf)
    return cx, cy




# ── 内盘暖红峰:用户两张手调成品的共同形态 ────────────────────────────────────
# 【为什么是这个量(2026-09-22,从用户手调的 M31/M33 反推)】
#   我先用「本体饱和度」当判据 —— 证伪:用户说"饱和不够"的那版量到 0.143,
#   比他自己手工那版(0.044)高三倍;两张手调成品之间也差 50%(0.204 vs 0.137)。
#   **那个量测不出他说的问题,也不是共性。**
#   按本体半径归一后再看,两张手调图的共同形态非常一致:
#     半径带          0.00-0.10  0.10-0.25  0.25-0.45  0.45-0.70  0.70-1.00
#     M31 手调 R/G      1.103      1.176      1.116      1.018      0.973
#     M33 手调 R/G      1.161      1.268      1.226      1.083      1.000
#   → **R/G 在 0.10~0.25 本体半径处有峰**(1.18~1.27),向外单调退回中性。
#   而自动版(M33 不推盘色)是 1.098/1.020/1.000/0.978 —— **红峰整个平掉了**,
#   同时 B/G 峰 1.194 比手调的 1.118 还高 = 用户说的"偏灰蓝、红色灰蒙蒙"。
#   **问题不在蓝太多,在红没起来。**
# ⚠ 这条带是 **n=2** 标定的,而且只在**星系**上验过。样本一多就该重标;
#   星云/星团不适用(它们的色彩结构完全不同)。
WARM_BINS = [(0.00, 0.10), (0.10, 0.25), (0.25, 0.45), (0.45, 0.70), (0.70, 1.00)]
WARM_PEAK_BAND = (1.15, 1.32)      # R/G 峰值该落的区间(手调实测 1.176 / 1.268)
WARM_PEAK_POS = (0.10, 0.45)       # 峰该出现在哪一段本体半径(手调两张都在 0.10~0.25)


def _sky_level(lum) -> float:
    """天光背景电平 = **直方图众数**(全管线统一口径,实现在 recombine._sky_mode)。

    【为什么不能用 p25(2026-09-23 M64)】`body_radius` 原来拿 `percentile(lum, 25)` 当背景。
    M64 调色前实测:p25 = **0.1240**,而真背景(远场中位)是 **0.1341**、众数 0.1345 ——
    **p25 落在真背景之下**,于是阈值 `bg + 0.10×(peak−bg) = 0.1331` 也在背景之下,
    "亮度降到阈值以下"的条件**永远不成立**,半径一路跑到 940px(真值 ~185px)。
    这不是个别现象:p25 是否等于背景,取决于天体占画面多少、有没有梯度、暗区多不多 ——
    **它是个会随内容漂的量**。众数不会(亮天体只是少数像素)。见 [[pi-background-level-estimator]]。

    效果:同一目标三个阶段(调色前/调色后/成片)量出的本体半径
    由 **940 / 210 / 205(离散 4.6×)** 变成 **185 / 180 / 190(离散 1.06×)**。
    这很关键 —— 暖峰判据的峰位是**按本体半径归一**的,分母自己漂 4.6 倍,
    闭环就是在追一个会动的靶。
    """
    try:
        from .recombine import _sky_mode
        return float(_sky_mode(np.asarray(lum).ravel()))
    except Exception:
        return float(np.percentile(np.asarray(lum), 25))


def body_radius(img, smooth_div: float = 30.0, drop: float = 0.10) -> float:
    """本体半径:大尺度平滑亮度降到 `背景 + drop×(峰−背景)` 的半径(像素)。

    归一化用它 —— 不归一就没法跨目标比(M31 本体 320px、M33 175px,同一个绝对半径
    在两张图上是完全不同的部位)。见 [[pi-ref-color-consensus]] 的尺度不变性教训。
    """
    a = np.asarray(img, dtype=np.float64)
    lum = a[..., :3].mean(-1) if a.ndim == 3 else a
    H, W = lum.shape
    S = min(H, W)
    sm = _gauss(lum, S / float(smooth_div))
    # 中心统一走 find_center:它先压点源再取峰。自己写 argmax 会被一颗亮星顶掉
    #   (2026-09-23 实测线性图上亮星比星系核亮 28 倍),半径一错整套归一化全废。
    cx, cy = find_center(a)
    yy, xx = np.ogrid[:H, :W]
    rr = np.hypot(yy - cy, xx - cx)
    bg = _sky_level(lum)
    pk = float(sm[cy, cx])
    thr = bg + float(drop) * (pk - bg)
    for r in range(5, int(S * 0.6), 5):
        m = (rr >= r - 4) & (rr < r + 4)
        if m.sum() and float(np.median(sm[m])) < thr:
            return float(r)
    return float(S * 0.5)


def warm_profile(img, r0=None) -> dict:
    """星系的径向色彩廓线(按本体半径归一)+ 内盘暖红峰。

    返回 {bins, rg, bg, sat, peak, peak_pos, radius}:
      peak     = R/G 在各带里的最大值
      peak_pos = 该带的中点(占本体半径的比例)
    """
    a = np.asarray(img, dtype=np.float64)
    if a.ndim != 3 or a.shape[2] < 3:
        return {}
    H, W = a.shape[:2]
    # r0 给了就用给的 —— 同一目标跨阶段比较时必须**锁同一把尺**,否则比的是两套坐标。
    #   (半径是天体的几何属性,调色不该改变它;但背景侧滑块会改亮度廓线,所以只有
    #    显式传同一个 r0 才严格可比。)
    R0 = float(r0) if r0 else body_radius(a)
    lum = a[..., :3].mean(-1)
    cx, cy = find_center(a)          # 同上:别自己 argmax
    yy, xx = np.ogrid[:H, :W]
    rr = np.hypot(yy - cy, xx - cx)
    mx = a[..., :3].max(-1)
    mn = a[..., :3].min(-1)
    satmap = (mx - mn) / np.maximum(mx, 1e-9)
    rg, bgv, sat = [], [], []
    for lo, hi in WARM_BINS:
        m = (rr >= lo * R0) & (rr < hi * R0)
        if m.sum() < 200:
            rg.append(None); bgv.append(None); sat.append(None); continue
        R, G, B = (float(np.median(a[..., i][m])) for i in range(3))
        rg.append(R / max(G, 1e-9))
        bgv.append(B / max(G, 1e-9))
        sat.append(float(np.median(satmap[m])))
    vals = [(v, i) for i, v in enumerate(rg) if v is not None]
    if not vals:
        return {}
    pk, pi = max(vals)
    lo, hi = WARM_BINS[pi]
    return {"bins": WARM_BINS, "rg": rg, "bg": bgv, "sat": sat, "radius": R0,
            "peak": round(pk, 4), "peak_pos": round((lo + hi) / 2.0, 3)}


def mask_leak(img, mask, thr: float = 0.5, r_mult: float = 3.0) -> dict:
    """蒙版漏进背景多少 —— **单一真源**,求解器/面板读数/验证一律调这个。

    【为什么必须单一真源(2026-09-23 自己踩的)】我在四个脚本里各写了一遍这个量,
    背景区定义、取哪个统计量、在哪个分辨率上算各不相同,于是同一件事量出
    0.2% / 1.6% / 10.3% / 2.8% 四个互相矛盾的数,排查时先怀疑的全是错的方向。
    **一个量有四份实现,就等于没有这个量。**(同类教训见 [[pi-quality-gate]] 的 s_star_band。)

    口径,三条都要紧:
      ① 背景区**按半径**圈(> r_mult × 本体半径),不按亮度 —— 按亮度会把蒙版真正漏出去的
         那些较亮斑块排除在外,那是「取样集合由被测量本身定义」(当天栽了四次);
      ② 统计量取**面积占比**(mask > thr),不取中位数 —— 背景蒙版可以"中位 0.000 却有
         10% 的面积超过 0.5",而造成可见发紫的正是那些斑块,中位数对它完全失明;
      ③ 结果**随分辨率变**(全分辨率噪声更大):实测预览是全分辨率的 1.0~2.1 倍,
         即预览**偏保守**。所以 `scale` 一并返回,调用方要知道自己量的是哪一档。
    """
    a = np.asarray(img, dtype=np.float64)
    m = np.asarray(mask, dtype=np.float64)
    if m.ndim == 3:
        m = m[..., 0]
    lum = a[..., :3].mean(-1) if a.ndim == 3 else a
    cx, cy = find_center(a)
    r0 = body_radius(a)
    yy, xx = np.ogrid[:lum.shape[0], :lum.shape[1]]
    rr = np.hypot(yy - cy, xx - cx)
    far = rr > float(r_mult) * r0
    if far.sum() < 2000:                     # 天体占满画面 → 放宽到 1.6 倍
        far = rr > 1.6 * r0
    if far.sum() < 500:
        return {"leak": 0.0, "n": 0, "r0": r0, "note": "背景区太小,量不了"}
    return {"leak": float((m[far] > float(thr)).mean()), "n": int(far.sum()),
            "r0": float(r0), "center": (int(cx), int(cy)),
            "scale": int(min(lum.shape))}


def mask_body_coverage(img, mask) -> dict:
    """本体上的蒙版覆盖情况 —— 面板要显示它,否则用户看不出蒙版圈没圈住天体。

    【为什么必须显示(用户 2026-09-22 M81_M82 事故)】蒙版收紧 0.85 从上一个目标(M33)继承过来,
    在 M81_M82 这种**双星系场**上圈不住本体:实测本体上蒙版中位只有 **0.446**
    (即星系 55% 的权重落在「背景侧」),于是用户设的背景压饱和 22%/压亮度 52%
    **直接削到了星系身上**(本体饱和 0.252→0.191)。而蒙版 >0.5 的区域只占画面 0.83%。
    同一组参数在 M33(单星系、亮度集中)上是能圈住的 —— **同一个数在不同画面上含义完全不同**,
    所以不能只显示滑块数值,必须显示它在**这张图上**的实际后果。
    返回 {body_med, body_frac_gt50, area_gt50}。
    """
    a = np.asarray(img, dtype=np.float64)
    m = np.asarray(mask, dtype=np.float64)
    if m.ndim == 3:
        m = m[..., 0]
    lum = a[..., :3].mean(-1) if a.ndim == 3 else a
    H, W = lum.shape
    S = min(H, W)
    sm = _gauss(lum, S / 30.0)
    # 背景走统一口径(直方图众数)。p25 会随天体占比/梯度/暗区漂,M64 实测比真背景还低
    #   → 「天体」判据的门槛整体下移、把背景也算成天体 → 覆盖率读数失真(见 _sky_level)。
    bg = _sky_level(lum)
    # 峰值取**本体中心**处,不取 sm.max():后者可能是残留亮星
    #   (线性图上亮星比星系核亮 28 倍,见 [[pi-white-roi-star-trap]])。
    _cx, _cy = find_center(a)
    pk = float(sm[_cy, _cx])
    body = sm > bg + 0.25 * (pk - bg)          # 取「明确属于天体」的那部分,别把暗外围算进来
    if body.sum() < 200:
        return {}
    return {"body_med": round(float(np.median(m[body])), 3),
            "body_frac_gt50": round(float((m[body] > 0.5).mean()), 3),
            "area_gt50": round(float((m > 0.5).mean()), 4)}

def corner_background(img, frac=0.08):
    """四角中位当背景基准(逐通道)。"""
    H, W = img.shape[:2]
    k = max(8, int(frac * min(H, W)))
    blocks = [img[:k, :k], img[:k, -k:], img[-k:, :k], img[-k:, -k:]]
    return np.median(np.concatenate([b.reshape(-1, img.shape[-1]) for b in blocks]), axis=0)


def disc_profile(img, center=None, bg=None):
    """径向 B/G、R/G 廓线(减背景后按相对半径分档取中位)。返回 dict。"""
    img = np.asarray(img, dtype=np.float64)
    H, W = img.shape[:2]
    S = min(H, W)
    if center is None:
        center = find_center(img)
    cx, cy = center
    if bg is None:
        bg = corner_background(img)
    yy, xx = np.ogrid[:H, :W]
    rr = np.hypot(yy - cy, xx - cx) / S
    bgp, rgp = [], []
    for lo, hi in FRACS:
        m = (rr >= lo) & (rr < hi)
        if m.sum() < 50:
            bgp.append(float("nan")); rgp.append(float("nan")); continue
        v = np.median(img[m], axis=0) - bg
        if v[1] <= 1e-6:
            bgp.append(float("nan")); rgp.append(float("nan")); continue
        bgp.append(float(v[2] / v[1])); rgp.append(float(v[0] / v[1]))
    return {"center": [cx, cy], "bg": [float(x) for x in bg],
            "fracs": MIDS, "bg_over_g": bgp, "r_over_g": rgp,
            "shape": [float(x / bgp[0]) if bgp[0] and bgp[0] == bgp[0] else float("nan")
                      for x in bgp],
            "crossing": crossing_radius(bgp)}


def crossing_radius(prof):
    """B/G 首次穿过 1.0 的相对半径(线性内插)。全程同侧返回 None。

    **三态**:穿过→数值;全程在 1.0 以下→None 且 side='below';以上→None 且 side='above'。
    调用方必须区分"没穿过"和"量不出来"(见 [[pi-silent-skip-plugins]] 的教训:
    优雅降级必须响亮)。这里全程同侧就是明确的 None,不是失败。
    """
    for i in range(1, len(prof)):
        a, b = prof[i - 1], prof[i]
        if not (a == a and b == b):
            continue
        if (a - 1.0) * (b - 1.0) < 0:
            t = (1.0 - a) / (b - a)
            return float(MIDS[i - 1] + t * (MIDS[i] - MIDS[i - 1]))
    return None


def auto_reference_rois(img, core_frac=0.035, bg_box_frac=0.10):
    """自动给出 (背景参考框, 白参考框),都是 [x0,y0,x1,y1] 像素整数。

    白参考 = 星系核心亮区(用户给的通用规则:大面积星系用盘的核心较亮区域当白)。
    背景参考 = 非边缘、星点最少、最暗、离本体最远的矩形。

    **背景框的打分必须同时看"暗"和"没星"**:只挑最暗会选到被暗云压住的区域,
    只挑星少会选到边角渐晕处。这里三项加权:低中位 + 低高频能量(星点少) + 远离本体。
    """
    img = np.asarray(img, dtype=np.float64)
    H, W = img.shape[:2]
    S = min(H, W)
    lum = img.mean(-1) if img.ndim == 3 else img
    cx, cy = find_center(img)

    # ── 白参考:核心亮区外接框 ────────────────────────────────────────────────
    half = max(6, int(core_frac * S))
    wx0, wy0 = max(0, cx - half), max(0, cy - half)
    wx1, wy1 = min(W - 1, cx + half), min(H - 1, cy + half)

    # ── 背景参考:网格搜矩形 ──────────────────────────────────────────────────
    bs = max(24, int(bg_box_frac * S))                 # 候选框边长
    margin = int(0.04 * S)                             # 离画面边缘至少这么远(躲黑边/渐晕)
    hp = np.abs(lum - _gauss(lum, 2.0))                # 高频能量 ≈ 星点密度
    best, bestscore = None, None
    ys = range(margin, max(margin + 1, H - margin - bs), max(8, bs // 3))
    xs = range(margin, max(margin + 1, W - margin - bs), max(8, bs // 3))
    for y0 in ys:
        for x0 in xs:
            y1, x1 = y0 + bs, x0 + bs
            if y1 >= H - margin or x1 >= W - margin:
                continue
            bx, by = x0 + bs / 2.0, y0 + bs / 2.0
            d = np.hypot(bx - cx, by - cy) / S
            if d < 0.30:                               # 离本体太近直接不要
                continue
            sub = lum[y0:y1, x0:x1]
            subhp = hp[y0:y1, x0:x1]
            med = float(np.median(sub))
            star = float(np.percentile(subhp, 99))     # 框内最亮星点的高频强度
            # 分数越小越好:暗 + 没星 + 远离本体(远的给负分奖励)
            sc = med / max(float(np.median(lum)), 1e-9) + 6.0 * star / max(med, 1e-9) - 0.5 * d
            if bestscore is None or sc < bestscore:
                bestscore, best = sc, [x0, y0, x1, y1]
    if best is None:                                   # 兜底:左上角安全框
        best = [margin, margin, margin + bs, margin + bs]
    # 【backgroundHigh 要从这块框里**量**出来,不能写常数(用户 2026-09-21 澄清)】
    #   用户原话:"BN 的 0.0016 是需要在图像框选区域中检测后才能照到的值,简单来说,就是测量预览
    #   区域内像素点的 RGB 数值,以最高的那个数值作为 BN 的值";并补充"CC 也同理"。
    #   即:阈值 = 这张图的"背景最亮能亮到哪",随图自适应。
    #   ★ 取 **p99.9 而不是绝对 max**:自动框难免混进一颗星或热点 —— 实测我们的框
    #     max/中位 = 4.93,而用户那块干净预览是 1.60;改 p99.9 得 1.47,与用户同量级。
    #     绝对 max 会被单个热点劫持,把阈值放大 3 倍 = 等于让 BN 拿整个星系当背景。
    #   ★ 绝对值**不能跨图搬**:直接把用户的 0.0016 用在我们图上(背景 0.001275)会选中 99.5%
    #     的像素,实测背景完全没被中和(B/G 到 2.1)。
    _bx = img[best[1]:best[3], best[0]:best[2], :3]
    _bhigh = float(np.percentile(_bx, 99.9))
    _btgt = float(np.median(_bx))
    return {"bgROI": [int(v) for v in best],
            "whiteROI": [int(wx0), int(wy0), int(wx1), int(wy1)],
            "center": [cx, cy], "score": bestscore,
            "bgHigh": _bhigh, "bgTarget": _btgt,
            "bgMedianRGB": [float(v) for v in np.median(_bx.reshape(-1, 3), axis=0)]}


def gain_for_crossing(prof_bg, target_cross=CROSS_TARGET):
    """求把中性交叉点挪到目标半径所需的 **全局 B/G 增益**。

    只解一个标量:k 使得 k*B/G 廓线在 target_cross 处等于 1.0。
    廓线在该半径处的值由分档中位线性内插得到。**这是电平校正,不改形状** ——
    形状该由校准+还原保住,不该让这一步去捏(见模块头:两件事别混在一个旋钮里)。
    """
    p = [x for x in prof_bg]
    xs, ys = [], []
    for m, v in zip(MIDS, p):
        if v == v:
            xs.append(m); ys.append(v)
    if len(xs) < 2:
        return None
    v_at = float(np.interp(target_cross, xs, ys))
    if v_at <= 1e-6:
        return None
    return float(1.0 / v_at)


def solve_channel_affine(a, b, sample=400000, seed=0):
    """求把图 a 变成图 b 的**逐通道仿射** (g, c):b ≈ g*a + c。

    用途:本体与星点用两套白点时,不必把整条预处理链跑两遍 —— 色彩校准本身就是逐通道
    线性变换,两次校准的产物之间必然存在精确的逐通道仿射关系,解出来直接搬到星点分支即可。

    **稳健性**:用随机子采样 + 最小二乘;并返回残差,调用方必须检查 —— 残差大说明两图
    之间不是逐通道线性关系(例如其中一次校准根本没跑成),这时**不能用**这个变换。
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 3 or a.shape[-1] < 3:
        return None
    n = a.shape[0] * a.shape[1]
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, size=int(min(sample, n)), replace=False)
    af = a.reshape(-1, a.shape[-1])[idx]
    bf = b.reshape(-1, b.shape[-1])[idx]
    gains, offs, res = [], [], []
    for c in range(3):
        x, y = af[:, c], bf[:, c]
        A = np.stack([x, np.ones_like(x)], 1)
        sol, *_ = np.linalg.lstsq(A, y, rcond=None)
        g, o = float(sol[0]), float(sol[1])
        pred = g * x + o
        den = float(np.std(y)) or 1e-12
        gains.append(g); offs.append(o)
        res.append(float(np.std(y - pred) / den))      # 相对残差
    return {"gains": gains, "offsets": offs, "resid": res}


def apply_channel_affine(img, gains, offsets):
    """逐通道 g*x+c;不截断负值(线性域电平是物理量,截断会毁暗端)。"""
    out = np.asarray(img, dtype=np.float64).copy()
    for c in range(3):
        out[..., c] = out[..., c] * float(gains[c]) + float(offsets[c])
    return out


def mask_anchor_health(img, bg, eps: float = 0.006, body_frac: float = 0.30) -> dict:
    """体检这个背景锚点:它会不会让主体蒙版塌掉、顺带让「蒙版收紧」滑块变成死的。

    【为什么需要(用户 2026-09-23 M64)】用户点的"背景"给出 bg=0.1752,而那张图的亮度分位是
    p50 0.1346 / p90 0.1546 / p99 0.1732 / **p99.8 0.1880** —— **点到了比全图 99% 都亮的地方**
    (四角实测背景只有 0.1392)。于是 `clip=bg+eps=0.1812`,clip 以上只剩 0.4% 的像素,
    `peak−clip=0.0068` **小于 `lum_sat_mask_array` 里 0.01 的下限** →
    `mid` 被 `max(clip+0.01, mid)` 夹死 → **body_frac 取任何值都给出同一张蒙版**。
    实测 0.85/0.60/0.45/0.30/0.15 五档逐位相同,>0.5 都只到 r=82px;
    而 r=110 处面亮度还有峰值的 40%(是盘不是背景),却被当背景、饱和乘 0.20。
    **那句 `max(clip+0.01, mid)` 把失败静默吞掉了** —— 同类教训见 [[pi-silent-skip-plugins]]:
    优雅降级必须响亮。

    返回 {ok, reason, clip, peak, span, above_frac, dead_below, suggest_bg}:
      span       = peak(p99.8) − clip,主体可用的亮度跨度
      dead_below = body_frac 低于这个值时 mid 会被夹死(=滑块在该区间无效);≥0.9 表示整条滑块都死
      suggest_bg = 四角实测背景,可作为替代锚点
    """
    a = np.asarray(img, dtype=np.float64)
    lum = a[..., :3].mean(-1) if a.ndim == 3 else a
    bgv = float(bg)
    clip = bgv + float(eps)
    peak = float(np.percentile(lum, 99.8))
    span = peak - clip
    above = float((lum > clip).mean())
    # 【跟着 lum_sat_mask_array 的下限走(2026-09-23 改成 0.05×跨度)】旧公式写死 0.01/跨度,
    #   下限改了不跟着改,报的就是**过期信息** —— 比不报更糟。
    #   现在 mid−clip ≥ 0.05×跨度 由 body_frac 自身的下限保证,所以只有 span 塌到 ~0
    #   (锚点点进天体)时才会真的夹死。
    dead = 0.05 if span > 2e-3 else 99.0
    try:
        sug = float(np.asarray(corner_background(a)).mean())
    except Exception:
        sug = float(np.percentile(lum, 25))
    # 【阈值分级(别对正确输入报警)】滑块上限是 0.85:
    #   dead ≥ 0.85 = **整条滑块都失效**(M64 实测 1.47)→ 错,必须提示;
    #   0.15 < dead < 0.85 = 只有低档失效 → 提醒一句即可(正确锚点在这张图上也会是 0.23,
    #   因为这是一张背景亮、主体跨度窄的非线性图,那不是错)。
    #   把「会误报」的阈值当错误报出去,比不报更糟(见 [[pi-quality-gate]]:
    #   指标标红先问这阈值是对着谁标定的)。
    SLIDER_MAX = 0.85
    if above < 0.02 or dead >= SLIDER_MAX:
        level = "bad"
        why = ("背景锚点偏亮:它之上只剩 %.1f%% 的像素、主体可用跨度只有 %.4f —— "
               "「蒙版收紧」滑块**整条都不起作用**,蒙版只会盖住最亮的核心。"
               "四角实测背景是 %.4f,多半该用它附近的点。"
               % (100 * above, span, sug))
    elif dead > 0.15:
        level = "warn"
        why = ("「蒙版收紧」低于 %.2f 的档位无效(主体亮度跨度只有 %.4f);"
               "这一段拖了不会有变化。" % (min(dead, SLIDER_MAX), span))
    else:
        level, why = "ok", ""
    return {"ok": level == "ok", "level": level, "reason": why, "clip": clip, "peak": peak,
            "span": span, "above_frac": above, "dead_below": min(dead, 99.0), "suggest_bg": sug}


def lum_sat_mask_array(img, bg=None, body_level=0.90, eps=0.006,
                       blur_sigma: float = 15.0, blur_times: int = 2,
                       body_frac: float = 0.30):
    """主体蒙版,按用户 2026-09-21 口述的四步做:
       ① 取 L 通道 ② **按标定的背景位置把背景压到最低**(黑点钉在那儿,以下全 0)
       ③ **大幅拉高星系主体亮度**(主体中位亮度处直接给到 body_level≈0.9)
       ④ 高斯模糊羽化 → 当蒙版用

    ★ `bg` 由**用户在预览上点选的那个点**给(面板里的"点选背景")。用户原话是
      "根据背景的位置" —— 用他指定的点,比我自己去测四角更可靠:大天体占满画面时
      四角量到的"背景"里一大半是天体自己的外晕(M31 实测 fill 1.95)。
      不给 bg 时才退回四角中位。
    ★★ 主体的抬升量按**本体自身的亮度尺度**取:`clip + body_frac×(峰值−clip)`,
      峰值用 p99.8(此时已去星,峰值就是星系核)。**不要用"背景以上像素的中位数"** ——
      用户 2026-09-21 指出"蒙版圈的范围有点大,星系盘外围的饱和度也被大幅拉起来了",
      实测 M31 占满画面时 **51.7% 的像素都在背景之上**,它们的中位只有 0.1885
      (核心 0.61、全图 p90 0.33)→ 蒙版曲线从 0 抬到 0.90 只用了 **0.043 的亮度跨度**,
      亮度一到 0.19 就满蒙版,>0.8 盖住 25.9% 的画面、r=0.45~0.60 的淡外围蒙版仍有 0.904。
      **取样集合被被测对象本身撑大 → 中位数不再代表"本体"**,同一个坑见
      [[pi-lumprobe-anchor-trap]] / [[pi-house-style-vector]] / [[pi-background-level-estimator]]。
      改锚之后(body_frac=0.30):>0.8 占 12.5%,r .45~.6 降到 0.439、r .6~.8 降到 0.195。
      body_frac 由面板的「蒙版收紧」滑块给,大 = 只盖更亮的盘面。

    返回 (mask, bg)。GUI 实时预览与最终应用**共用本函数**,只是分辨率不同;
    σ 按短边折算,所以两边羽化尺度一致、预览和结果对得上。
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter
    a = np.asarray(img, dtype=np.float64)
    if a.ndim == 2:
        a = np.stack([a] * 3, -1)
    lum = a[..., :3].mean(-1)
    H, W = lum.shape
    S = min(H, W)
    if bg is None:
        k = max(4, int(0.08 * S))
        bg = float(np.median(np.concatenate([
            lum[:k, :k].ravel(), lum[:k, -k:].ravel(),
            lum[-k:, :k].ravel(), lum[-k:, -k:].ravel()])))
    bg = float(bg)
    clip = bg + float(eps)                       # ② 背景压到最低:clip 以下全 0
    above = lum[lum > clip]
    if above.size < 200:                         # 几乎没有主体 → 退个保守的固定抬升
        mid = min(0.95, clip + 0.15)
    else:
        peak = float(np.percentile(lum, 99.8))   # ③ 本体峰值(已去星,就是星系核)
        _span = max(peak - clip, 0.01)
        mid = clip + float(max(0.05, min(0.9, body_frac))) * _span
        _want = mid
        # 【下限随本图跨度走,别用绝对 0.01(2026-09-23 M64)】那个绝对值是凭空来的:
        #   温和拉伸的底子上主体亮度跨度只有 0.0335,于是 body_frac 在 0.30 以下全被夹死,
        #   蒙版**覆盖本体封顶在 41%**,再松也没用 —— 剩下 59% 的星系被当背景处理。
        #   而 `mid = clip + max(0.05, body_frac)×跨度` 本来就保证 mid−clip ≥ 0.05×跨度,
        #   所以取 0.05×跨度当下限**等价于让它永不生效**,恰好就是"别让 mid 塌到 clip 上"的本意。
        #   实测(M64,跨度 0.039):下限 0.01→40% 覆盖;0.05×跨度→**60%**。
        #   担心的硬边没有出现:亮度斜率虽从 89 陡到 461,**径向过渡反而更宽**(62px→74px)——
        #   星系外围亮度随半径变化很缓,陡的亮度响应映射到空间上仍是一大片,
        #   小尺度还有 σ≈7px 的羽化兜着。**硬边是空间上的,不是亮度上的。**
        mid = float(min(0.95, max(clip + max(1e-4, 0.05 * _span), mid)))
        # 【被下限夹住 = body_frac 失效,必须让调用方知道(2026-09-23 M64)】
        #   原来这句 max() 会把"背景锚点点到天体上"这种错误**静默**吞掉:
        #   滑块从 0.85 拖到 0.15 蒙版一动不动,用户无从察觉。
        lum_sat_mask_array.last_clamped = bool(mid > _want + 1e-12)
    x = np.array([0.0, clip, mid, 1.0])
    y = np.array([0.0, 0.0, float(body_level), 1.0])
    sig = float(blur_sigma) * (S / 2065.0)       # ④ 羽化;按短边折算,换分辨率不跑掉
    # 【★先平滑亮度、再阈值(2026-09-23 M64「背景没压住还发紫」)】原来是**先对原始亮度硬阈值、
    #   再模糊蒙版** —— 每个噪声像素先跳到 body_level,羽化再把它们摊成**全图基座**。
    #   实测:M64 背景噪声 σ=0.0163 而主体全部亮度跨度只有 0.0472(σ 占 35%),
    #   于是 27% 的背景像素本就在 clip 之上 → 蒙版远到 8 倍本体半径仍有 **0.13**,
    #   整个背景吃到一部分提饱和 → 背景饱和 0.016→**0.030**、亮尾 0.111→**0.156**。
    #   蒙版是个**大尺度选择器,噪声压根不该进去**:先把亮度平滑到羽化尺度再阈值,
    #   背景蒙版中位由 0.138 归到 **0.000**,本体覆盖反而从 80% 升到 90%。
    #   (先平滑过了,后面只需一遍模糊;两遍是给硬阈值补偿用的。)
    m = np.interp(np.clip(gaussian_filter(lum, sig), 0.0, 1.0), x, y)
    for _ in range(max(1, int(blur_times) - 1)):
        m = gaussian_filter(m, sig)
    return np.clip(m, 0.0, 1.0), bg


def lum_sat_mask(img_path: str, out_path: str, bg=None, body_level: float = 0.90,
                 eps: float = 0.006, blur_sigma: float = 15.0, blur_times: int = 2,
                 body_frac: float = 0.30, log=None) -> dict:
    """把 lum_sat_mask_array 的结果写成 XISF,给 PI 的 op 当 params.mask 用。

    `bg` 传**用户点选的背景电平**(面板里的"点选背景");不传才退回四角中位。
    与实时预览共用 lum_sat_mask_array → 预览所见即所得。
    """
    import numpy as np
    from xisf import XISF
    xn = XISF(img_path)
    img = np.asarray(xn.read_image(0), dtype=np.float64)
    m, used_bg = lum_sat_mask_array(img, bg=bg, body_level=body_level, eps=eps,
                                    blur_sigma=blur_sigma, blur_times=blur_times,
                                    body_frac=body_frac)
    XISF.write(out_path, np.stack([m] * 3, -1).astype("float32"), None, None)
    info = {"path": out_path, "bg": used_bg, "clip": used_bg + eps,
            "coverage": float((m > 0.05).mean()), "peak": float(m.max())}
    if log:
        log("  [主体蒙版] 背景 %.4f 处压到 0(%s);主体抬到 %.2f;羽化 ×%d;覆盖 %.1f%% 画面"
            % (used_bg, "用户点选" if bg is not None else "四角中位",
               body_level, blur_times, 100.0 * info["coverage"]))
    return info


def lum_color_profile(img, nbins=9, margin=0.012):
    """「颜色 vs 亮度」廓线:[(亮度, R/G, B/G)]。

    自变量是**亮度** —— 因为 CT 的逐通道曲线就是亮度的函数,要设计它就必须在同一个
    自变量下对账。按半径分环是另一个自变量,两者能给出相反的结论(实测:半径口径说
    "外盘不够蓝",亮度口径说"暗端偏蓝且中调偏红")。

    只统计**本体内、且亮度高于背景+margin** 的像素:暗端被背景基座主导时,量到的是
    背景自己的通道比而不是星系的(实测用户成品暗端 R/G 1.000、B/G 0.957 恰好等于其
    背景 0.0863/0.0902/0.0902 的比值 —— 这不是星系的颜色)。
    """
    import numpy as np
    img = np.asarray(img, dtype=np.float64)
    H, W = img.shape[:2]
    S = min(H, W)
    lum = img[..., :3].mean(-1)
    sm = _gauss(lum, S / 60.0)
    bg = corner_background(img)
    sel = (sm > bg.mean() * 1.20) & (lum > bg.mean() + float(margin))
    if sel.sum() < 5000:
        return [], bg
    v = lum[sel]
    qs = np.linspace(2, 99, nbins + 1)
    out = []
    for i in range(nbins):
        lo, hi = np.percentile(v, qs[i]), np.percentile(v, qs[i + 1])
        m = sel & (lum >= lo) & (lum < hi)
        if m.sum() < 400:
            continue
        px = img[m]
        r, g, b = (float(np.median(px[:, 0])), float(np.median(px[:, 1])),
                   float(np.median(px[:, 2])))
        if g <= 1e-9:
            continue
        out.append((float(0.5 * (lo + hi)), r / g, b / g))
    return out, bg


def solve_lum_curves(cur, target, bg_level, strength=1.0, max_dev=0.25):
    """由「现状廓线」与「目标廓线」解出 R/B 通道的 CT 控制点。

    做法:在每个亮度档上求 R、B 需要的倍率(G 不动,因为 R/G 与 B/G 两个比值只约束两个自由度),
    把 (x, x*k) 当控制点。**背景电平处放一个「输出=输入」的锚点**把背景钉死 —— 否则曲线在
    x≈背景 附近的改动会直接给背景染色(用户手工时也是这么钉的)。

    strength<1 = 只走一部分(离线实测 1.0 会把暖/蓝比例从 51.8/32.0 推到 33.9/43.2,
    而目标是 39.6/41.9 —— 略微过校,故默认 0.85)。
    """
    import numpy as np
    if not cur or not target:
        return None
    tl = np.array([p[0] for p in target], dtype=float)
    tr = np.array([p[1] for p in target], dtype=float)
    tb = np.array([p[2] for p in target], dtype=float)
    lo, hi = 1.0 - float(max_dev), 1.0 + float(max_dev)
    pr, pb = [], []
    for L, rg, bgr in cur:
        kr = float(np.interp(L, tl, tr)) / max(rg, 1e-9)
        kb = float(np.interp(L, tl, tb)) / max(bgr, 1e-9)
        kr = 1.0 + (float(np.clip(kr, lo, hi)) - 1.0) * float(strength)
        kb = 1.0 + (float(np.clip(kb, lo, hi)) - 1.0) * float(strength)
        pr.append((L, L * kr))
        pb.append((L, L * kb))

    def mk(pts):
        c = [(0.0, 0.0), (round(float(bg_level), 5), round(float(bg_level), 5))]
        for x, y in pts:
            if x > bg_level + 0.005:
                c.append((round(float(x), 5), round(float(min(max(y, 0.0), 1.0)), 5)))
        c.append((1.0, 1.0))
        o = []
        for x, y in c:
            if not o or x > o[-1][0] + 1e-4:
                o.append([x, y])
        return o

    return {"pointsR": mk(pr), "pointsB": mk(pb)}


# ── 手动调色面板用的曲线构造(GUI 与实际应用共用同一套,免得预览和结果对不上)──────
#   用户 2026-09-21 定的交互:点画面标定背景 → RGB 三通道都以它为锚点(输出=输入),
#   第二个控制点用滑块控制。操作思路等同 PI 的 CurvesTransformation。

PRESETS = {
    "自然":     {"r": 1.00, "g": 1.00, "b": 1.00, "x2": 0.25, "sat": 1.00},
    "暖核蓝臂": {"r": 1.10, "g": 1.00, "b": 0.97, "x2": 0.22, "sat": 1.20},
    "尘带偏橙": {"r": 1.14, "g": 1.02, "b": 0.94, "x2": 0.18, "sat": 1.15},
    "整体偏冷": {"r": 0.96, "g": 1.00, "b": 1.08, "x2": 0.25, "sat": 1.10},
    "去品红":   {"r": 0.95, "g": 1.05, "b": 0.96, "x2": 0.22, "sat": 1.00},
}


def two_point_curve(bg, x2, gain):
    """两点曲线:背景处钉「输出=输入」,x2 处按 gain 抬/压,1.0 处钉死。

    背景锚点是**整件事的关键** —— 没有它,任何在低端的改动都会直接给背景染色。
    用户手工时也是这么钉的(其 L 蒙版黑点、CT 背景锚点都落在实测背景电平上)。
    """
    bg = float(max(0.0, min(0.95, bg)))
    x2 = float(max(bg + 0.02, min(0.95, x2)))
    y2 = float(max(0.0, min(1.0, x2 * float(gain))))
    pts = [[0.0, 0.0], [round(bg, 5), round(bg, 5)], [round(x2, 5), round(y2, 5)], [1.0, 1.0]]
    out = []
    for x, y in pts:                       # x 必须严格递增,否则样条会炸
        if not out or x > out[-1][0] + 1e-4:
            out.append([x, y])
    return out


def sat_curve(gain, knee=0.20):
    """饱和曲线:低饱和段按 gain 抬,高饱和段收敛回 1(免得把已经很浓的地方推爆)。

    【g < 1(降饱和)单独一支】原来的膝盖式公式在 g→0 时会给出 [0.2, 0.0] 后面又跟
      [0.52, 0.286] —— **先掉到 0 再抬回去**的怪形状。降饱和本来就该是"整体按比例缩",
      端点也不必钉在 (1,1),直接一条 y = g·x 最干净,g=0 就是彻底灰掉。
      (背景侧滑块 bgsat 会一路拉到 0,必须走这一支。)

    【g > 3 靠"横坐标压缩"再给力度(用户 2026-09-21 "饱和度的上限还不够")】
      纯把 g 调大没用:g=3 时曲线在 S=0.52 处已经到 0.988,输出被 1.0 封顶,
      再大的 g 只是把控制点顶到 1 然后**变平**,滑块从 3 往上是死的。
      高端唯一还有余量的方向是**把弱色也推上来** —— 所以 g>3 时保持 g=3 的输出形状,
      只把**横坐标整体压缩 3/g**:同样的浓度在更低的原始饱和上就达到。
      在 g=3 处与旧公式严丝合缝(s=1),所以用户已经找到的档位不会被这次改动挪走。
    """
    g = float(gain)
    if abs(g - 1.0) < 1e-4:
        return None
    if g < 1.0:
        return [[0.0, 0.0], [1.0, round(max(0.0, min(1.0, g)), 5)]]
    k = float(max(0.05, min(0.6, knee)))
    ge = min(g, 3.0)                 # 形状只按 ≤3 算
    sc = 1.0 if g <= 3.0 else 3.0 / g   # >3 的部分转成横坐标压缩
    x2 = min(0.95, k * 2.6)
    y1 = max(0.0, min(1.0, k * ge))
    y2 = max(0.0, min(1.0, x2 * (1.0 + (ge - 1.0) * 0.45)))
    X1, X2 = k * sc, x2 * sc
    # 【尾段必须补一个点,否则 Akima 会鼓包冲过 1.0】(X2,y2)→(1,1) 是一段又长又平的尾巴,
    #   样条在 X2 处接的是前面的陡斜率,会先冲高再回落 —— 实测旧的四点版 g=3 就已经
    #   冲到 **1.059**、g=6 冲到 1.196,超出部分被 clip 成一整条"全饱和"平台,
    #   这正是滑块推到头"再推也没变化"的手感来源。补一个尾段中点后全程单调、峰值正好 1.0。
    x3, y3 = X2 + (1.0 - X2) * 0.5, y2 + (1.0 - y2) * 0.5
    return [[0.0, 0.0], [round(X1, 5), round(y1, 5)], [round(X2, 5), round(y2, 5)],
            [round(x3, 5), round(y3, 5)], [1.0, 1.0]]


# ── 复刻 PI 的 CurvesTransformation:插值口径 + 饱和重建 ──────────────────────
# 【为什么要标定这两件事(2026-09-23,用户 M81:「手调预览是对的,跑完色彩就变了」)】
#   面板预览用 numpy、落盘用 PI,两边**必须是同一个变换**,否则用户是照着一张错的图在调。
#   实测这两处原来都错:
#     ① 插值器:代码一直传 `curveType:'akima'`,但 runner 设的属性名是错的(见 job-runner.js),
#        PI 实际跑的是**自然三次样条**。numpy 这边却真用了 Akima → 曲线形状从头到尾对不上。
#     ② 饱和重建:原来按"保通道均值"缩色差。PI 实测保的是 **Rec709 亮度**
#        (输出/输入比值:亮度 0.977±0.013、通道均值 1.169±0.100、最大通道 1.554±0.197),
#        色相保持(色度向量夹角 cos 0.994)。
#   M81 上这两项叠加的后果:盘上预览饱和 0.173 / PI 0.284,B/G 1.174 / 1.446。
#   用户把饱和推到 +598% 正是因为预览显得太淡 —— **他批准的是一张比成片淡得多的图**。
CURVE_AKIMA_MIN_PTS = 5      # PI 的 Akima 需要 ≥5 个控制点,4 点时它自己退回自然三次样条(实测)


def curve_interp(pts, curve_type: str = "cubic"):
    """按 PI 的实际口径造一条曲线。与 PI 输出逐位吻合(实测 max|Δ| 3e-8)。

    `curve_type` 必须与提交给 runner 的 `params.curveType` 一致 —— 这是"同一个变换"的前提。
    ⚠ akima 一档只在控制点够多时才真的生效,而且实测**个别形状的曲线 PI 仍按三次样条跑**
      (原因未查明)。所以需要预览与成片严格一致的地方(手动调色面板)一律用 cubic:
      那一档 PI 的行为没有歧义,已逐位验证。
    """
    import numpy as np
    from scipy.interpolate import Akima1DInterpolator, CubicSpline
    p = np.asarray(pts, dtype=float)
    if p.ndim != 2 or len(p) < 2:
        return None
    if str(curve_type).lower() == "linear":
        return lambda t: np.clip(np.interp(np.clip(t, 0, 1), p[:, 0], p[:, 1]), 0.0, 1.0)
    if str(curve_type).lower() == "akima" and len(p) >= CURVE_AKIMA_MIN_PTS:
        f = Akima1DInterpolator(p[:, 0], p[:, 1])
    else:
        f = CubicSpline(p[:, 0], p[:, 1], bc_type="natural")
    return lambda t: np.clip(np.nan_to_num(f(np.clip(t, 0.0, 1.0)), nan=0.0), 0.0, 1.0)


# PI 的 S 通道保的是这组亮度系数(Rec709);实测反解 [0.274, 0.631, 0.096],
#   与 Rec709 同一量级且 Rec709 的残差更小,取 Rec709。
LUMA_W = (0.2126, 0.7152, 0.0722)


def apply_curves_np(img, pts_r=None, pts_g=None, pts_b=None, pts_s=None,
                    curve_type: str = "cubic"):
    """在 numpy 上应用这几条曲线,复刻 PI 的 CurvesTransformation(给 GUI 做实时预览)。

    S 通道:**保 Rec709 亮度、保色相,只缩色度向量**,缩放系数 = 曲线在 HSV 饱和度上的增益
    `curve(S)/S`(S=(max−min)/max)。实测 RMSE 0.023,而原来的"保通道均值"是 0.060。

    ⚠ 剩下那 0.023 集中在**高饱和**处(S>0.2,残差 0.038、略偏低),低饱和区几乎为零
      (S=0.02 处 0.0008)—— 是色域边界上的截断差异。星系盘属于低饱和区,够用。
    """
    import numpy as np

    def _ap(ch, pts):
        f = curve_interp(pts, curve_type) if pts else None
        return ch if f is None else f(ch)

    out = np.asarray(img, dtype=np.float64).copy()
    out[..., 0] = _ap(out[..., 0], pts_r)
    out[..., 1] = _ap(out[..., 1], pts_g)
    out[..., 2] = _ap(out[..., 2], pts_b)
    if pts_s:
        fS = curve_interp(pts_s, curve_type)
        if fS is not None:
            mx = out[..., :3].max(-1, keepdims=True)
            mn = out[..., :3].min(-1, keepdims=True)
            s = np.where(mx > 1e-9, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
            g = np.where(s > 1e-6, fS(s) / np.maximum(s, 1e-9), 1.0)
            w = np.asarray(LUMA_W, dtype=np.float64)
            lum = (out[..., :3] * w).sum(-1, keepdims=True)
            out[..., :3] = np.clip(
                lum * (1.0 + (out[..., :3] / np.maximum(lum, 1e-9) - 1.0) * g), 0.0, 1.0)
    return out

def sample_background(img, x, y, radius=6):
    """取样一小块的逐通道中位当背景锚点(单像素会被噪声带偏)。"""
    import numpy as np
    a = np.asarray(img, dtype=np.float64)
    H, W = a.shape[:2]
    x, y, r = int(x), int(y), int(max(1, radius))
    x0, x1 = max(0, x - r), min(W, x + r + 1)
    y0, y1 = max(0, y - r), min(H, y + r + 1)
    blk = a[y0:y1, x0:x1, :3].reshape(-1, 3)
    med = np.median(blk, axis=0)
    return {"rgb": [float(v) for v in med], "lum": float(med.mean())}
