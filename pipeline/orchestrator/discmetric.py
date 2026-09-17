"""星系盘色彩的**尺度归一**度量(用户 2026-09-17 M74)。

为什么要专门写一个:要拿 AstroBin 参考当调色目标,就得把"别人的图"和"我们的图"放在
同一把尺子上量。旧的 disc_signal_color / disc_color_profile 做不到 ——

  · **不是尺度不变量**:同一张我们的成片,3779px 量出 B/G 0.745、620px 0.897、400px 1.080。
    参考图过去只下 620px 缩略图,拿它跟我们的全分辨率比,差距被夸大了一倍。
    (同一类错误在 star_saturation 上栽过一次,见 [[pi-quality-gate]]。)
  · **不同设备的本体大小差 3~9 倍**:参考图 0.31~0.93 角秒/px,Dwarf3 是 2.75。
    固定像素半径、固定模糊半径的量法,量的根本不是同一块地方。

做法:**先把本体缩放到统一半径,再按本体自身半径的比例分环**。
  ① 定心 + 量 r_obj(方位角平均廓线落到峰值 10% 处);模糊尺度按画幅取,不写死像素
  ② 整幅缩放使 r_obj = CANON_R,之后所有模糊/分环都在归一后的尺度上做
  ③ 逐环取**逐通道中位 − 逐通道背景**,给出 R/G、B/G 和显示饱和度

实测(M74):同一张图缩到 3779/2267/1322/680px,内三环的 B/G 基本不动(旧度量漂 45%);
12 张不同设备的参考各自量出的本体半径换算成角分是 4.83′±0.48′(星表 ~5′)——
**12 台设备独立量到同一个物理尺寸**,说明 r_obj 判据站得住。

分环用**半径**而不是信号占峰值比例:比例带在跨图比较时会被各人拉伸力度不同带偏,
半径带只依赖几何。代价是高倾角星系的环里混了尘带(见 [[pi-galaxy-disc-color-target]]),
所以**这是"跨图比对"的尺子**;要把目标落到曲线上时,再把环映射成各自图上的亮度(见
recombine.disc_push_curves)。
"""
from __future__ import annotations

import numpy as np

CANON_R = 200.0                      # 归一后本体半径(像素)
BANDS = ((0.0, 0.15), (0.15, 0.35), (0.35, 0.70), (0.70, 1.10))
BAND_NAMES = ("核", "内盘", "盘", "外盘")


def _blur(x, sigma):
    import cv2
    return cv2.GaussianBlur(x, (0, 0), float(sigma))


def _bg_per_channel(a, sm):
    """逐通道背景电平:用**平滑亮度**选背景区(选择与通道值无关 → 不会按噪声选样),再取各通道中位。
    见 [[pi-dark-pixel-selection-bias]]:按像素挑最暗会优先挑中噪声向下涨落的,噪声大的通道被拉更低。"""
    b = float(np.median(sm))
    mad = float(np.median(np.abs(sm - b))) * 1.4826
    m = sm < b + 1.0 * max(mad, 1e-6)
    if int(m.sum()) < 2000:
        m = sm < np.percentile(sm, 40)
    return np.array([float(np.median(a[..., i][m])) for i in range(3)], dtype=np.float64)


def locate(a, win: float = 0.34):
    """定位本体中心 + 估 r_obj。返回 (cx, cy, r_obj, peak, bg_lum)。

    中心用**中央窗口内的平滑亮度极大值**:别用全图 argmax(前景亮星比星系亮,见
    [[pi-galaxy-halo-vignette-degeneracy]]);窗口取画幅中央 ±34%,参考图基本都把目标放中间。
    """
    h, w = a.shape[:2]
    lum = a.mean(-1)
    sm = _blur(lum, max(4.0, min(h, w) / 260.0))     # 模糊尺度按画幅,不写死像素
    cy0, cx0 = h // 2, w // 2
    dy, dx = int(h * win), int(w * win)
    sub = sm[cy0 - dy:cy0 + dy, cx0 - dx:cx0 + dx]
    yy, xx = np.unravel_index(int(np.argmax(sub)), sub.shape)
    cy, cx = cy0 - dy + yy, cx0 - dx + xx
    Y, X = np.mgrid[0:h, 0:w]
    rr = np.hypot(Y - cy, X - cx)
    bgl = float(np.median(sm))
    peak = float(sm[max(0, cy - 3):cy + 4, max(0, cx - 3):cx + 4].mean()) - bgl
    rmax = int(min(h, w) * 0.45)
    step = max(2, rmax // 120)
    r_obj = None
    for r in range(step, rmax, step):
        m = (rr >= r) & (rr < r + step)
        if not m.any():
            continue
        if peak > 0 and (float(np.mean(sm[m])) - bgl) < 0.10 * peak:
            r_obj = float(r)
            break
    # 【没落到 10% 就不能用这个估计(用户 2026-09-17 M31)】天体溢出画幅时廓线根本降不到
    #   峰值的 10%,回退值 rmax*0.5 是**纯粹由取景决定的数**。M31 实测 12/12 参考全部
    #   落在回退上,r_obj 从 249 到 810px 乱跳 → 各自量的根本不是同一块地方
    #   (各环 R/G 的 σ 高达 0.96,而 M74 只有 0.04~0.14)。调用方拿到 fit=False 就该换锘
    #   (按星表尺寸 + 图的角分辨率算 r_obj),别拿这个数去比。
    return cx, cy, float(r_obj if r_obj else rmax * 0.5), peak, bgl, bool(r_obj)


def position_angle(sm, cx, cy, r_px, q: float = 1.0) -> float:
    """估星系长轴方向(弧度)。**用“括进椭圆里的信号最多”搜一遍,不用二阶矩。**

    二阶矩版在这里失效了两次:① 天体占满画面时窗口被画幅剪成矩形,量到的是
    **画幅的形状**(M31 算出 −17°,真值约 38°);② 权重用 sm−median(sm),而大天体的
    中位落在天体里(这条坐过多次,见 [[pi-background-level-estimator]])。
    改成直接搜:轴比用星表的,每个角度算一遍椭圆内的信号量,取最大。
    直接优化的就是我们要的东西(蒙版包不包得住星系),且对背景估计不敏感。"""
    import numpy as np
    import cv2
    if q >= 0.95:
        return 0.0
    h, w = sm.shape
    k = 600.0 / max(h, w)
    if k < 1.0:
        small = cv2.resize(sm, (max(16, int(w * k)), max(16, int(h * k))), interpolation=cv2.INTER_AREA)
        cx2, cy2, r2 = cx * k, cy * k, r_px * k
    else:
        small, cx2, cy2, r2 = sm, cx, cy, r_px
    v = small.astype(np.float64)
    hist, edges = np.histogram(v, bins=512)
    bg = float(edges[int(np.argmax(hist))])          # 直方图众数 = 天光,不是中位
    sig = np.clip(v - bg, 0.0, None)
    H, W = small.shape
    Y, X = np.mgrid[0:H, 0:W]
    dx = X - cx2; dy = Y - cy2
    # 【两道防番完全是为了"天体比画幅大"这种情况】
    #   ① 半径截到**任何角度都能完整放进画幅**(≤ 半短边),否则横着的椭圆因为
    #      没被剪而"装得多",搜出来的总是横的(M31 实测 −15°,真值约 38°)。
    #   ② 比的是**平均信号**不是总和 —— 总和会奖励"圈得多",平均才奖励"圈得准"。
    r2 = float(min(r2, 0.5 * min(H, W)))
    best, best_pa = -1.0, 0.0
    for deg in range(0, 180, 3):
        pa = np.radians(deg)
        c, s2 = np.cos(pa), np.sin(pa)
        u = dx * c + dy * s2
        vv = (-dx * s2 + dy * c) / max(q, 1e-3)
        m = (u * u + vv * vv) <= (r2 * r2)
        n = int(m.sum())
        if n < 100:
            continue
        val = float(sig[m].mean())
        if val > best:
            best, best_pa = val, pa
    return float(best_pa)


def measure(a, canon_r: float | None = CANON_R, bands=BANDS,
            r_obj_px: float | None = None, q: float = 1.0, center=None) -> dict:
    """量一张图的盘色廓线。a = float RGB 0..1(H,W,3)。

    canon_r=None → **不缩放**,环半径直接用该图自己的 r_obj。
    跨图比较要缩放(才有可比性);只是要在**自己这张图**上取控制点时不该缩 ——
    曲线的控制点是像素**值**,要和原图的值同源。

    返回 {"rings": [{rg, bg, S, snr, lum, xr, xb, vg} | None], "r_obj": px, "scale": 缩放比,
    "center": (x,y), "bg": [R,G,B 背景电平]}。
    rg/bg = 扣背景后的 R/G、B/G;S = **显示饱和度**(含基座的像素 HSV S,和肉眼看到的一致);
    lum = 该环的中位亮度;xr/xb = 该环 R/B 的中位**值**;vg = 该环的 G 信号(G − 背景G)。
    """
    import cv2
    cx, cy, r_obj, _peak, _bgl, _fit = locate(a)
    if center is not None:
        cx, cy = int(center[0]), int(center[1])
        _fit = True
    if r_obj_px:                      # 外部给了物理锚(星表尺寸 × 角分辨率)→ 以它为准
        r_obj = float(r_obj_px)
        _fit = True
    h, w = a.shape[:2]
    if canon_r is None:
        k = 1.0
        canon_r = r_obj
        b = a
        nh, nw = h, w
    else:
        k = float(canon_r) / max(r_obj, 1.0)
        nw, nh = max(32, int(round(w * k))), max(32, int(round(h * k)))
        b = cv2.resize(a, (nw, nh), interpolation=(cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC))
    cx2, cy2 = cx * k, cy * k
    sm = _blur(b.mean(-1), 3.0)
    bgv = _bg_per_channel(b, sm)
    bs = np.stack([_blur(b[..., i], 3.0) for i in range(3)], -1)
    # 【环要跟着星系的形状走(用户 2026-09-17 M31)】圆环只对面朝星系成立。
    #   M31 是 189′×62′ 的3:1 椭圆,圆环半径一大就有大半扫到星系外的空天上 →
    #   环内信号被背景稀释成噪声 → 比值发散、整环被 σ 闸废掉(而蓝色恒星形成环恰好就在那里)。
    #   轴比 q 用星表的 size_minor/size_major,长轴方向从图像二阶矩估 —— 不需额外数据。
    #   面朝星系 q≈1,退化成圆环,安全。
    _q = float(min(1.0, max(0.15, q or 1.0)))
    Y, X = np.mgrid[0:nh, 0:nw]
    _dx = X - cx2; _dy = Y - cy2
    if _q < 0.95:
        _pa = position_angle(sm, cx2, cy2, canon_r * 1.2, q=_q)
        _c, _s = np.cos(_pa), np.sin(_pa)
        _u = _dx * _c + _dy * _s
        _v = -_dx * _s + _dy * _c
        rr = np.sqrt(_u * _u + (_v / _q) ** 2)
    else:
        _pa = 0.0
        rr = np.hypot(_dy, _dx)
    out = []
    for lo, hi in bands:
        m = (rr >= lo * canon_r) & (rr < hi * canon_r)
        # 【环要么基本在画幅内,要么不算】只剩一角落在图里的环,量到的是偏向画幅中心
        #   那一侧的像素,跟别的图不可比。覆盖度 = 实际像素数 / 完整圆环面积。
        _full = np.pi * ((hi * canon_r) ** 2 - (lo * canon_r) ** 2) * _q
        if int(m.sum()) < 200 or (_full > 0 and float(m.sum()) / _full < 0.5):
            out.append(None)
            continue
        v = np.array([float(np.median(bs[..., i][m])) for i in range(3)])
        sig = v - bgv
        # 【信号太弱就不要报色比(用户 2026-09-17 M31)】高倡角星系的外环有大半落在星系外的
        #   天空上,G 信号接近 0 → R/G 算出 5.28、-0.14、甚至 -2.5e7 这种数。这不是颜色,
        #   是除以零。这种环宁可不给值 —— 上游的 σ 闸会因为它们直接把整个目标废掉。
        if sig[1] <= 0 or float(sig.mean() / max(bgv.mean(), 1e-9)) < 0.02:
            out.append(None)
            continue
        out.append({
            "rg": float(sig[0] / max(sig[1], 1e-9)),
            "bg": float(sig[2] / max(sig[1], 1e-9)),
            "S": float((v.max() - v.min()) / max(v.max(), 1e-9)),
            "snr": float(sig.mean() / max(bgv.mean(), 1e-9)),
            "lum": float(np.median(sm[m])),
            "xr": float(v[0]), "xb": float(v[2]), "vg": float(sig[1]),
        })
    return {"rings": out, "r_obj": r_obj, "scale": k, "center": (int(cx), int(cy)),
            "fit": bool(_fit), "q": _q, "pa_deg": round(float(np.degrees(_pa)), 1),
            "bg": [float(x) for x in bgv]}


def load_any(p) -> np.ndarray:
    """读 .xisf / 常见位图 → float RGB 0..1。"""
    import cv2
    s = str(p)
    if s.lower().endswith(".xisf"):
        from xisf import XISF
        from . import recombine as _R
        return np.clip(_R._norm01(XISF(s).read_image(0))[..., :3], 0, 1).astype(np.float32)
    im = cv2.imread(s, cv2.IMREAD_COLOR)
    if im is None:
        raise OSError("读不出图像:%s" % s)
    return np.clip(cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0, 0, 1)


def arcsec_per_px(path) -> float | None:
    """从 xisf/fits 头的 FOCALLEN + XPIXSZ 算角分辨率(″/px);没头返回 None。
    XPIXSZ 的注释已声明"including binning",不要再乘 XBINNING。"""
    try:
        from xisf import XISF
        fk = (XISF(str(path)).get_images_metadata()[0].get("FITSKeywords") or {})

        def _v(k):
            e = fk.get(k)
            return float(e[0]["value"]) if e else None

        f, px = _v("FOCALLEN"), _v("XPIXSZ")
        if f and px and f > 1e-6:
            return 206.265 * px / f
    except Exception:
        pass
    return None


def r_obj_from_catalog(target: str, arcsec_px: float) -> float | None:
    """按**星表尺寸**算本体半径(px)。天体溢出画幅时廓线法失效,只能用物理锚。
    交叉验证:M74 廓线法量出 4.83′,星表 size_major/2 = 5.25′ —— 差 8%,两者一致。"""
    try:
        from . import dso
        info = dso.lookup(target or "") or {}
        maj = float(info.get("size_major") or 0.0)
        if maj > 0 and arcsec_px and arcsec_px > 1e-9:
            return (maj / 2.0) * 60.0 / float(arcsec_px)
    except Exception:
        pass
    return None


def axis_ratio_from_catalog(target: str) -> float:
    """星表轴比 size_minor/size_major(≤1);查不到返回 1.0(当圆处理)。"""
    try:
        from . import dso
        info = dso.lookup(target or "") or {}
        maj = float(info.get("size_major") or 0.0)
        mnr = float(info.get("size_minor") or 0.0)
        if maj > 0 and mnr > 0:
            return float(min(1.0, mnr / maj))
    except Exception:
        pass
    return 1.0


def frame_fill(img_path, target: str) -> float:
    """天体本体半径 / 画幅半短边。>1 = 天体比画幅还大;拿不到尺寸/尺度返回 0。

    【用处：背景展平类操作的前提是"画里有干净的天空可拟合"】
    M31 实测本体半径 2040px、画幅半短边 1068px → fill 1.91,根本没有纯天空。
    这时背景模型分不清天光梯度和星系本体,两者各扣一点、谁也没治好:
    实测二次 GC 把外盘信噪削掉 31%、polybg 再削 36%,而 nonflat 只分别降了 7% / 6%,
    两步跑完依旧 uneven=True。**花掉两个三分之一的外盘,换来一个没解决的问题。**
    同理 bg_uniformity 在这种图上本身就不可信(量到的"背景"大片是星系),
    它报的 uneven=True 正是把这两步放进来的原因。"""
    try:
        asp = arcsec_per_px(img_path)
        if not asp:
            return 0.0
        r = r_obj_from_catalog(target, asp)
        if not r:
            return 0.0
        from xisf import XISF
        import numpy as _np
        sh = _np.asarray(XISF(str(img_path)).read_image(0)).shape
        half = min(int(sh[0]), int(sh[1])) / 2.0
        return float(r / max(half, 1.0))
    except Exception:
        return 0.0


def object_mask(img_path, target: str, out_path: str | None = None,
                r_scale: float = 1.15, feather: float = 0.15, log=None):
    """按**星表尺寸 + 长轴方向**画一个软边椭圆蒙版,只圈住这个天体本身。

    【用户 2026-09-17】「发绿的检测只对星系有效 —— 例如 M33 旁边有个小的行星状星云,
    星云本身就是有点绿的,这种情况不应该作为去绿的先决条件。」
    亮度蒙版(rangemask)圈的是"所有亮东西",包括那个星云;拿它去量绿,
    星云的**真绿**会把闸门顶开,然后连星云一起被削 —— 两头都错。
    椭圆蒙版把范围钉在星系自己身上:测的是它、改的也只是它。

    拿不到星表尺寸/角分辨率 → 返回 None(调用方退回原来的亮度蒙版)。
    """
    import numpy as np
    try:
        asp = arcsec_per_px(img_path)
        r = r_obj_from_catalog(target, asp) if asp else None
        if not r:
            if log:
                log("    椭圆蒙版:拿不到星表尺寸或角分辨率 → 退回亮度蒙版")
            return None
        a = load_any(img_path)
        h, w = a.shape[:2]
        cx, cy, _r0, _pk, _bg, _fit = locate(a)
        # 【这里用**圆**不用椭圆(2026-09-17 实测后改回)】椭圆得知道长轴方向,
        #   而天体比画幅大时长轴方向**从图里测不准**:二阶矩/最大总量/最大均值
        #   三种写法在 M31 上分别给 −17° / −15° / 90°(真值约 38°)—— 都被画幅形状带跑了,
        #   套错方向的椭圆只包住 40% 的星系光,比不用蒙版还糟。
        #   改用**星表长轴半径的圆**:不需要方向,一定包得住星系;多圈进来的空天由亮度
        #   蒙版卡掉。目的就是"别把旁边那个星云算进来",圆已经够。
        #   (分环量颜色仍用椭圆 —— 那里要的是环与环可比,实测 7 张参考的 σ 只有 0.01~0.02。)
        Y, X = np.mgrid[0:h, 0:w]
        rr = np.hypot(Y - cy, X - cx) / max(r * float(r_scale), 1.0)
        # 软边:rr<1-feather 全开,>1 全关,中间 smoothstep(硬边会在曲线里碾出接缝)
        t = np.clip((1.0 - rr) / max(float(feather), 1e-3), 0.0, 1.0)
        m = (t * t * (3.0 - 2.0 * t)).astype(np.float32)
        if log:
            log("    天体范围蒙版:中心(%d,%d) 星表半径 %.0fpx ×%.2f → 覆盖 %.1f%% 画面"
                % (cx, cy, r, r_scale, 100.0 * float((m > 0.5).mean())))
        if out_path:
            from xisf import XISF
            XISF.write(str(out_path), np.stack([m] * 3, -1))
            return str(out_path)
        return m
    except Exception as e:
        if log:
            log(f"    椭圆蒙版失败({e}) → 退回亮度蒙版")
        return None


def restrict_to_object(mask_path: str, img_path: str, target: str, out_path: str,
                       r_scale: float = 1.15, log=None):
    """把亮度本体蒙版 ∩ 天体星表范围,写成新蒙版;做不成返回原蒙版路径。

    【用户 2026-09-17】「发绿的检测只对星系有效。例如 M33 旁边有个小的行星状星云,
    星云本身就是有点绿的,这种情况就不应该作为去绿的先决条件。」
    亮度蒙版圈的是画里所有亮东西;拿它测绿,星云的**真绿**会把闸门顶开,
    接着连星云一起被削 —— 测错了、改错了,两头都错。
    """
    import numpy as np
    try:
        from xisf import XISF
        om = object_mask(img_path, target, r_scale=r_scale, log=log)
        if om is None:
            return mask_path
        mk = np.asarray(XISF(str(mask_path)).read_image(0)).astype(np.float32)
        if mk.ndim == 3:
            mk = mk[..., 0]
        if mk.shape != om.shape:
            return mask_path
        out = np.clip(mk * om, 0.0, 1.0).astype(np.float32)
        if float((out > 0.5).sum()) < 2000:
            if log:
                log("    限到天体范围后本体像素不足 → 维持原蒙版")
            return mask_path
        XISF.write(str(out_path), np.stack([out] * 3, -1))
        if log:
            log("    本体蒙版 ∩ 天体范围:%d → %d px(只在星系自己身上查绿/去绿)"
                % (int((mk > 0.5).sum()), int((out > 0.5).sum())))
        return str(out_path)
    except Exception as e:
        if log:
            log(f"    限定天体范围失败({e}) → 用原蒙版")
        return mask_path


def find_object(a, r_obj_px: float, expect_off_px: float | None = None,
                tol_px: float | None = None, log=None):
    """在图里找出**目标天体**的中心。返回 (cx, cy, ok)。

    【为什么不能只按亮度找(用户 2026-09-18 M77)】M77 只有 7.1′、又在亮星多的天区,
    旧的"中央窗口取平滑亮度最大值"实测 12 张参考里有 3 张落在**带星芒的亮星**上、
    4 张落在旁边的 **NGC 1055**(只隔 0.5°,同视场检索会把以它为中心的作品一起返回)。
    于是"M77 共识"量的大半是星点和别的星系的颜色(核 R/G 1.217=偏黄),
    推色就把星系往星点的黄推 —— 用户看到的"主体很黄"就是这么来的。

    两道修正:
      ① **按天体自身尺度平滑**(σ=0.3·r_obj)再找峰:星点在这个尺度下塌掉,展源留得住。
      ② **用天测挑**:参考条目带图像中心的 RA/Dec 和视场 → 算得出"目标应该离图心多远"。
         **这个距离与旋转、翻转都无关**,所以不需要知道 rotate 的约定。
         在候选峰里挑距离最吻合的;差太多 = 这张图里根本没有目标 → ok=False,整张剔掉。
         M77 实测:8 张匹配到 1~4px,4 张期望离心 2611~4251px(画幅才 2560px 宽)= 目标不在画里。
    """
    import numpy as np
    import cv2
    try:
        from scipy.ndimage import maximum_filter
    except Exception:
        cx, cy, _r, _p, _b, _fit = locate(a)
        return cx, cy, True
    h, w = a.shape[:2]
    sm = cv2.GaussianBlur(a.mean(-1), (0, 0), max(3.0, 0.30 * float(r_obj_px)))
    mx = maximum_filter(sm, size=int(max(9, r_obj_px * 0.8)) | 1)
    peak = (sm >= mx - 1e-9)
    b = float(np.median(sm))
    mad = float(np.median(np.abs(sm - b))) * 1.4826
    peak &= sm > b + 4.0 * max(mad, 1e-6)
    ys, xs = np.nonzero(peak)
    if len(xs) == 0:
        cx, cy, _r, _p, _b, _fit = locate(a)
        return cx, cy, True
    v = sm[ys, xs]
    idx = np.argsort(-v)[:8]
    cand = [(int(xs[i]), int(ys[i])) for i in idx]
    if expect_off_px is None:
        # 没有天测信息:取离画幅中心最近的候选(参考图都以目标取景)
        best = min(cand, key=lambda c: np.hypot(c[0] - w / 2.0, c[1] - h / 2.0))
        return best[0], best[1], True
    tol = float(tol_px if tol_px else max(0.5 * float(r_obj_px), 30.0))
    best = min(cand, key=lambda c: abs(np.hypot(c[0] - w / 2.0, c[1] - h / 2.0) - float(expect_off_px)))
    err = abs(np.hypot(best[0] - w / 2.0, best[1] - h / 2.0) - float(expect_off_px))
    if err > tol:
        if log:
            log("      天测对不上:期望离心 %.0fpx,最接近的候选差 %.0fpx(容差 %.0f) → 这张里没有目标"
                % (float(expect_off_px), err, tol))
        return best[0], best[1], False
    return best[0], best[1], True


def expected_offset_px(item: dict, target_ra: float, target_dec: float,
                       arcsec_px: float) -> float | None:
    """目标在这张参考里**应该离图心多远**(像素)。拿不到坐标返回 None。"""
    import numpy as np
    try:
        cra, cdec = item.get("ra_deg"), item.get("dec_deg")
        if cra is None or cdec is None or not arcsec_px:
            return None
        xi = (float(target_ra) - float(cra)) * np.cos(np.radians(float(target_dec)))
        eta = float(target_dec) - float(cdec)
        return float(np.hypot(xi, eta) * 3600.0 / float(arcsec_px))
    except Exception:
        return None
