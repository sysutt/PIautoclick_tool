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


def find_center(img):
    """找星系本体中心:用**大尺度平滑后的峰**,别用 argmax(会被热点/亮星骗)。"""
    lum = img.mean(-1) if img.ndim == 3 else img
    S = min(lum.shape)
    sm = _gauss(lum.astype(np.float64), S / 35.0)
    cy, cx = np.unravel_index(int(np.argmax(sm)), sm.shape)
    return int(cx), int(cy)


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
        mid = clip + float(max(0.05, min(0.9, body_frac))) * max(peak - clip, 0.01)
        mid = float(min(0.95, max(clip + 0.01, mid)))
    x = np.array([0.0, clip, mid, 1.0])
    y = np.array([0.0, 0.0, float(body_level), 1.0])
    m = np.interp(np.clip(lum, 0.0, 1.0), x, y)
    sig = float(blur_sigma) * (S / 2065.0)       # ④ 羽化;按短边折算,换分辨率不跑掉
    for _ in range(max(1, int(blur_times))):
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


def apply_curves_np(img, pts_r=None, pts_g=None, pts_b=None, pts_s=None):
    """在 numpy 上应用这几条曲线 —— 给 GUI 做**实时预览**用(不占 PI)。

    与 PI 的 CurvesTransformation 用同一组控制点、同样的 Akima 插值;S 通道按 HSI 建模
    (PI 的 CT「S」经标定不是 HSV,保的是通道均值,见 [[pi-saturation-not-hsv]])。
    预览与最终结果**不会逐位相同**(PI 的样条端点行为略有差异),但方向和量级一致,
    足够用来判断"要不要这么调"。
    """
    import numpy as np
    from scipy.interpolate import Akima1DInterpolator

    def _ap(ch, pts):
        if not pts:
            return ch
        p = np.asarray(pts, dtype=float)
        f = Akima1DInterpolator(p[:, 0], p[:, 1])
        y = f(np.clip(ch, 0.0, 1.0))
        return np.clip(np.nan_to_num(y, nan=0.0), 0.0, 1.0)

    out = np.asarray(img, dtype=np.float64).copy()
    out[..., 0] = _ap(out[..., 0], pts_r)
    out[..., 1] = _ap(out[..., 1], pts_g)
    out[..., 2] = _ap(out[..., 2], pts_b)
    if pts_s:
        I = out.mean(-1, keepdims=True)
        mx, mn = out.max(-1, keepdims=True), out.min(-1, keepdims=True)
        s = np.where(mx > 1e-9, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
        s2 = _ap(s, pts_s)
        g = np.where(s > 1e-6, s2 / np.maximum(s, 1e-9), 1.0)
        out = np.clip(I + (out - I) * g, 0.0, 1.0)
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
