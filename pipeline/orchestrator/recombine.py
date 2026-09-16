"""色度保持星点合成(chrominance-preserving recombine)——纯 numpy。

**为什么不用 screen**:screen `out = 1-(1-neb)(1-star) = star + neb·(1-star)`,那个 `+neb·(1-star)`
给星点每通道**加了一层背景**;背景亮又中性时每通道被抬相近的量 → 通道差异压缩 → 饱和度掉。
M23 实测:分离层星点 S=0.53,screen 合到亮背景后只剩 0.14(星蒙版测)。**"加法"毁饱和。**

**改法(缩放而非相加)**:星点区域把星点**原色缩放到 screen 后的亮度**,保住通道比例=保住色相+饱和;
亮度仍按 screen(星点照样发光、不变暗);背景(无星处)原样不动。实测把星蒙版内 S 从 0.135 拉回 0.531
(=分离层原值),背景亮度不变。见记忆 [[pi-quality-gate]]。

    Ln=mean(neb), Ls=mean(star·amt)      # 逐像素亮度
    Lo=1-(1-Ln)(1-Ls)                    # screen 亮度
    w =clip(Ls/W_KNEE,0,1)               # 星点权重(星图黑底,有信号处→1)
    out=Lo·[(1-w)·neb/Ln + w·star/Ls]    # 缩放星色到 Lo,而非加背景

用纯 numpy(不碰 cv2:cv2 在 PyQt Worker 子线程有崩溃风险,见 pi-quality-gate 教训)。
"""
from __future__ import annotations

W_KNEE = 0.015           # 星点权重拐点:star 亮度 >W_KNEE 即视为纯星点。**用户 2026-09-03 选"鲜艳丰富"路线**:
                         #   0.015 让中暗星拿满星权重、不混星云棕色度 → 星区饱和 0.500→0.552、星色更跳、暗尘更浓
                         #   (recomb_test.py 实证;纯 screen 才 0.292)。代价:背景更"忙"(更多带色暗星)、质量门会
                         #   报 dirty_background/dull_stars——但那是**审美预期非缺陷**;门在星团模式仅信息性标记、不触发
                         #   重跑,无害。旧值 0.04=干净克制路线(用户可切回)。
_EPS = 1e-5


def _norm01(a):
    import numpy as np
    a = a.astype(np.float32)
    mx = float(a.max()) if a.size else 1.0
    if mx > 1.5:
        a = a / (65535.0 if mx > 255 else 255.0)
    return a


def chroma_recombine(neb_path: str, stars_path: str, out_path: str,
                     star_amount: float = 1.0, preview_path: str | None = None,
                     mode: str = "auto", star_chroma_blur: float = 0.0,
                     star_knee: float | None = None) -> str:
    """把 stars_path(拉伸好的星点图,黑底)以**色度保持**方式合回 neb_path(去星星云),写 out_path。
    保留 neb 的 xisf 头(色彩空间/WCS/FITS 关键字)。可选出降采样预览 PNG。返回 out_path。

    mode(星点亮度如何叠加,解决"亮星云吞掉重合星点"):
      - "screen":Lo=1-(1-neb)(1-star)(PI 官方 ~(~$T*(~stars)))。亮星云上 Lo→1 与星点无关→**吞星点**。
      - "add"   :Lo=min(1,neb+star)(=用户的 $T+stars)。星点亮度**叠加穿透**亮星云,暗处与 screen 近似等价。
      - "auto"(默认):**暗/中处 screen、亮星云处渐变转相加**(按 neb 亮度加权)——自动化用户"平时 screen、亮云改相加"的手法。
    三种都保色度(星点色相/饱和不被背景稀释)。"""
    import numpy as np
    from xisf import XISF

    xn = XISF(neb_path)
    neb = _norm01(xn.read_image(0))
    star = _norm01(XISF(stars_path).read_image(0)) * float(star_amount)
    if neb.ndim == 2:
        neb = np.stack([neb] * 3, -1)
    if star.ndim == 2:
        star = np.stack([star] * 3, -1)
    neb = np.clip(neb[..., :3], 0, 1)
    star = np.clip(star[..., :3], 0, 1)

    Ln = neb.mean(-1, keepdims=True)
    Ls = star.mean(-1, keepdims=True)
    Lo_screen = 1.0 - (1.0 - Ln) * (1.0 - Ls)                # screen 亮度(亮星云会吞星点)
    Lo_add = np.minimum(1.0, Ln + Ls)                        # 相加亮度(星点穿透亮星云,=$T+stars)
    _m = (mode or "auto").lower()
    if _m == "screen":
        Lo = Lo_screen
    elif _m == "add":
        Lo = Lo_add
    else:                                                    # auto:按 neb 亮度在 screen↔add 间过渡
        T0 = 0.5                                             # neb 亮度超过 0.5 起渐转相加(bright→星点叠加穿透)
        bright = np.clip((Ln - T0) / (1.0 - T0), 0.0, 1.0)
        Lo = (1.0 - bright) * Lo_screen + bright * Lo_add
    # 星点权重拐点:W_KNEE 太小(0.015)会给**噪声级暗弱星翼**满权重(w=1)→ 其 Cs=star/Ls 把翼色按 Lo/Ls≈几倍
    #   放大 → 合成后**彩色光晕环 + 绿点**(星点层本身没有,是合成放大出来的;用户 2026-09-05 M31 查出)。
    #   调大拐点(星系传 star_knee≈0.10)让暗弱翼混向星系色(Cn)、不放大自身噪声色 → 根治光晕环/绿,无需事后 SCNR。
    _knee = float(star_knee) if star_knee else W_KNEE
    w = np.clip(Ls / _knee, 0.0, 1.0)                         # 星点权重(拐点 _knee)
    Cn = neb / (Ln + _EPS)                                    # 各自色度(去亮度)
    Cs = star / (Ls + _EPS)
    # 【星点色度外扩(用户 2026-09-05 M31:彩核灰晕脱节"严重")】源星图光晕(低信噪)近灰、色彩只集中在核心 →
    #   合成后是"彩色核 + 灰白晕"脱节。对星点色度 Cs 做**亮度加权高斯模糊**:亮核色相按 Ls 权重蔓延到邻近光晕、
    #   统一整颗星色相(灰晕吃到核心色);非星区 w≈0 不用 Cs、不受影响。降饱和只减核晕反差,这步才根治。
    if star_chroma_blur and star_chroma_blur > 0:
        try:
            from scipy.ndimage import gaussian_filter
            _sig = float(star_chroma_blur)
            _num = gaussian_filter(Cs * Ls, sigma=(_sig, _sig, 0))   # 亮度加权:亮核主导邻域色相
            _den = gaussian_filter(Ls, sigma=(_sig, _sig, 0)) + _EPS
            Cs = _num / _den
        except Exception as _cbe:
            print(f"  [chroma_recombine] 色度外扩跳过(异常):{_cbe}")
    out = np.clip(Lo * ((1.0 - w) * Cn + w * Cs), 0.0, 1.0).astype(np.float32)

    # 保留 neb 的头(下游 bgneutral/crop 需要正确色彩空间;有解析时保 WCS)
    img_meta = None
    file_meta = None
    try:
        img_meta = xn.get_images_metadata()[0]
    except Exception:
        img_meta = None
    try:
        file_meta = xn.get_file_metadata()
    except Exception:
        file_meta = None
    XISF.write(out_path, out, image_metadata=img_meta, xisf_metadata=file_meta)

    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def _sky_mode(v, bins: int = 4000, hi_pct: float = 90.0, smooth: int = 5) -> float:
    """单通道**天光背景电平 = 直方图众数**(天文里的标准背景估计)。对亮天体占比不敏感(它们是少数像素),
    更关键的是**对噪声无偏**——不像"挑最暗的 N% 像素取中位"那样会把噪声大的通道多往下拉(见 neutralize_bg_offset)。"""
    import numpy as np
    v = np.asarray(v).ravel()
    v = v[(v > 0) & (v < np.percentile(v, hi_pct))]
    if v.size < 1000:
        return float(np.median(v)) if v.size else 0.0
    h, e = np.histogram(v, bins=int(bins))
    if smooth > 1:
        h = np.convolve(h.astype(np.float64), np.ones(smooth) / smooth, "same")
    k = int(h.argmax())
    return float(0.5 * (e[k] + e[k + 1]))


def bg_mottle_chroma(img_path: str, lo_sigma: float = 25.0, hi_sigma: float = 200.0) -> dict:
    """**背景斑块本身的色度**(不是全图彩噪均值)。取背景里带通(约 100~800px 尺度)最亮的 10% 斑块,
    量它们的 R-G / B-G 偏离亮度多少。返回 {"chroma","rg","bg"}(均为亮度的比例)。

    为什么不能用 bg_chroma_level 的全图均值判:结构性色度会被均值摊平。M63 实测全图 bg_chroma 只有
    0.0165(远低于 0.06 的常用闸),可云斑亮处 R-G +2.65% / B-G +1.29%(两者同高 = 洋红)清晰可见——
    因为**色度是跟着斑块结构走的**(逐通道背景模型在空间上不一致的典型特征)。用户 2026-09-13 M63。"""
    import numpy as np
    from xisf import XISF
    try:
        from scipy.ndimage import gaussian_filter, median_filter
    except Exception:
        return {"chroma": 0.0, "rg": 0.0, "bg": 0.0}
    try:
        a = _norm01(XISF(img_path).read_image(0))
        if a.ndim == 2:
            return {"chroma": 0.0, "rg": 0.0, "bg": 0.0}
        a = np.clip(a[..., :3], 0, 1).astype(np.float32)
        L = median_filter(a.mean(-1), 3)
        band = gaussian_filter(L, lo_sigma) - gaussian_filter(L, hi_sigma)
        # 背景 = 亮度低于 p70 的区域(排除星系/星云本体与亮星)
        dark = L < float(np.percentile(L, 70))
        if int(dark.sum()) < 5000:
            return {"chroma": 0.0, "rg": 0.0, "bg": 0.0}
        sel = dark & (band > float(np.percentile(band[dark], 90)))
        if int(sel.sum()) < 500:
            return {"chroma": 0.0, "rg": 0.0, "bg": 0.0}
        R, G, B = (float(np.median(a[..., c][sel])) for c in range(3))
        lum = max((R + G + B) / 3.0, 1e-6)
        rg, bg = (R - G) / lum, (B - G) / lum
        return {"chroma": round(float(max(abs(rg), abs(bg))), 4),
                "rg": round(rg, 4), "bg": round(bg, 4)}
    except Exception:
        return {"chroma": 0.0, "rg": 0.0, "bg": 0.0}


def galactic_latitude(img_path: str):
    """从图像 FITS 头的 RA/DEC 算**银纬 b**(度);取不到返回 None。

    用途:判断"背景里的暗云斑块**有没有可能是真的前景尘埃**"。银纬是这个问题唯一靠谱的先验——
    |b| 小(银道面里)暗云遍地;|b| 大(银极方向)几乎没有前景尘埃,同样的斑驳外观多半是被拉伸
    放大的噪声/背景模型残差。实测对照:M52 b=-0.4 度(暗云是真的,见 [[pi-shallow-dense-field]]
    四证伪);M63 b=+74.3 度(用户 2026-09-13 判"画面中的暗云应该大部分都是伪细节",
    幅度也只有白噪预测的 1.4~1.6 倍)。**同一个外观,在两个天区含义相反 —— 不能只靠图像统计判。**"""
    import numpy as np
    try:
        from xisf import XISF
        fk = (XISF(img_path).get_images_metadata()[0] or {}).get("FITSKeywords", {}) or {}

        def _val(k):
            v = fk.get(k)
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, dict):
                v = v.get("value")
            return v

        def _deg(v, is_ra):
            if v is None:
                return None
            v = str(v).strip()
            try:
                return float(v)
            except ValueError:
                pass
            parts = [float(t) for t in v.replace(":", " ").split()]
            if not parts:
                return None
            sign = -1.0 if v.lstrip().startswith("-") else 1.0
            a = abs(parts[0]) + (parts[1] if len(parts) > 1 else 0) / 60.0 + (parts[2] if len(parts) > 2 else 0) / 3600.0
            return sign * a * (15.0 if is_ra else 1.0)

        ra = _deg(_val("RA"), True)
        if ra is None:
            ra = _deg(_val("OBJCTRA"), True)
        dec = _deg(_val("DEC"), False)
        if dec is None:
            dec = _deg(_val("OBJCTDEC"), False)
        if ra is None or dec is None:
            return None
        r = np.pi / 180.0
        a, d = ra * r, dec * r
        ngp_ra, ngp_dec = 192.85948 * r, 27.12825 * r      # J2000 北银极
        b = np.arcsin(np.sin(d) * np.sin(ngp_dec) + np.cos(d) * np.cos(ngp_dec) * np.cos(a - ngp_ra))
        return round(float(b / r), 1)
    except Exception:
        return None


def _bg_stat(sm):
    """平滑亮度图 → (背景电平, 噪声σ)。**别用中位数**(用户 2026-09-15 M31)。

    中位数当背景,只在「天体占画面一小块」时才成立。M31 这种占满画面的目标,中位数落进天体里,
    更要命的是 **MAD 被天体自身撑大 2~3 倍**(实测 σ 0.0047 → 0.0114),于是所有
    `b + kσ` 的判据一起失效:
      · `body = sm > b+12σ` 选出的本体从 19% 缩到 10%,在参考缩略图上直接**一个像素都不剩**
        → 12 张同视场参考 10 张量不出来 → 盘色目标退回平均值 → 把本来对的颜色推歪;
      · `green_cast_curve` 的 body 选不出来 → 判定「绿没过量」→ **整个去绿步骤被跳过**
        → 背景的绿一路留到成片(用户看到的「星系外围偏绿」)。
    这解释了为什么「几个星系都正常,只有 M31 出问题」—— 小天体上中位数≈背景,坑不触发。

    改用**直方图众数**(=天空峰)+ 只在背景一侧算 MAD。实测:
      小天体(M51/M63)b 变化 <0.3%、body 0.92%→1.08%,**几乎不变**(不会回归);
      M31 b 由 +2.0%/+4.4% 修正到 −1.1%/−3.2%,σ 由被撑大的 0.0114/0.0131 回到 0.0047/0.0040。
    """
    import numpy as _np
    h, e = _np.histogram(sm, bins=512)
    b = float((e[int(_np.argmax(h))] + e[int(_np.argmax(h)) + 1]) / 2)
    lo = sm <= b
    sg = float(_np.median(_np.abs(sm[lo] - b)) * 1.4826) if int(lo.sum()) > 100 else 0.0
    if sg <= 1e-9:
        sg = float(_np.median(_np.abs(sm - b)) * 1.4826) or 1e-6
    return b, sg


def body_sat_amount(img_path: str, target: float = 0.15, cap: float = 0.40,
                    core_ceiling: float = 0.20) -> float:
    """星系本体该提多少饱和 —— **按实测收敛到 target,而不是固定值**。返回 curves 的 saturation 量(0..cap)。

    【为什么(用户 2026-09-14 狮子座三重星系,对照他手动处理的 Image07)】原来是写死的 +0.40
    (2026-09-05 给 M31 **深数据**定的,见 [[pi-galaxy-deepdata]]),对浅数据小星系过量一倍多:
      阶段                三个星系「盘」饱和度        用户手动版
      r09_dn2             0.115 / 0.117 / 0.112
      r11_neb(全局+0.15)  0.151 / 0.155 / 0.148      0.093 / 0.083 / 0.106
      **rG_bodysat(+0.40)  0.313 / 0.320 / 0.299**   <- 是手动版的 3~4 倍
    也就是**提饱和之前就已经高过用户的水平了**,再 +0.40 纯属过量;而过量的饱和把盘上本来就偏黄的色相
    放大得更刺眼(B-G 由 -13% 变 -28%),正是用户说的"提升饱和度后星系开始偏色、呈现黄褐色"。
    用户审美一贯是**颜色克制**(见 [[pi-aesthetic-prefs]])。

    做法:量本体"盘"区(亮度 30~65 分位,避开过曝核心与外围噪声)的 HSV 饱和中位 s0,
    需要的增益 = target/s0 - 1,夹在 [0, cap]。已经够饱和(s0 >= target)就**返回 0 = 不提**。
    深数据星系盘本来偏灰(s0 小)时仍会正常提上去,不影响 M31 那类。"""
    import numpy as np
    from xisf import XISF
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:
        return float(cap)
    try:
        a = np.clip(_norm01(XISF(img_path).read_image(0))[..., :3], 0, 1).astype(np.float32)
        L = a.mean(-1)
        sm = gaussian_filter(L, max(6.0, min(L.shape) / 170.0))
        b, sg = _bg_stat(sm)
        body = sm > b + 12.0 * sg
        if int(body.sum()) < 2000:
            return float(cap)                              # 测不出本体 → 维持原行为
        reg = L[body]
        lo, hi = (float(v) for v in np.percentile(reg, [30, 65]))
        sel = body & (L >= lo) & (L <= hi)
        if int(sel.sum()) < 500:
            return float(cap)
        mx = a.max(-1); mn = a.min(-1)
        S = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
        s0 = float(np.median(S[sel]))
        if s0 <= 1e-4:
            return float(cap)
        amt = min(max(float(target) / s0 - 1.0, 0.0), float(cap))
        # 【核心上限(2026-09-14 M65/M66)】提饱和量由**盘**算出,但曲线是整个蒙版全局生效 ——
        #   核心本来就比盘饱和得多,同一条曲线会把它轰爆:实测核心饱和 0.229 → 0.560,
        #   而用户手动版核心只有 0.131(和本体中位 0.135 几乎相同)。这是「用一个标量控制一个
        #   有空间结构的属性」的老毛病,同 [[pi-mtf-crushes-highlight-chroma]]。
        #   → 同时量核心的饱和,按同样的公式取**更小**的那个量。核心区用 **p90(本体亮度)**:
        #     p99.5 只取到星系最中心那一小撮,而 MTF 恰恰把最亮处压得最中性,量出来的饱和反而偏低
        #     (实测 p99.5 给 0.137,而真正的核区是 0.284)。p90 与「半径<12px」实测吻合到 0.001。
        try:
            _ct = float(np.percentile(L[body], 90))
            _cm = body & (L >= _ct)
            if int(_cm.sum()) >= 200:
                sc = float(np.median(S[_cm]))
                if sc > 1e-4:
                    amt = min(amt, max(float(core_ceiling) / sc - 1.0, 0.0))
        except Exception:
            pass
        return round(float(amt), 3)
    except Exception:
        return float(cap)


def boost_body_saturation(img_path: str, out_path: str, mask_path: str | None = None,
                          target: float = 0.15, v_lo: float = 0.55, v_hi: float = 0.85,
                          preview_path: str | None = None, log=None) -> str:
    """星系本体提饱和 —— **真正的 HSV 提饱和**:V(最大通道)一动不动、只压低最小通道,
    色相严格保持。按构造**不可能削顶**。返回 out_path;测不到本体就原样拷。

    【为什么不能交给 PI 的 CurvesTransformation(用户 2026-09-14「星系核心过曝了」)】
    用户指出「提饱和跟通道的亮度没有关系」—— 按 HSV 定义这是对的。但 **PI 的「S」通道不是 HSV**:
    实测标定残差 HSI 0.0143 / HSL 0.0146 / **HSV 0.0312**,它保的是接近通道均值的亮度,
    于是提饱和时**最大通道往上顶**:实测 +0.318 在星系核心 V 中位 +0.0625、99.8% 的像素在涨,
    **V 触顶 1.0 的像素 0.24%→33.76%**,核心被不可逆地削平。
    改用 pointsS 分段曲线(低 S 抬、高 S 钉住)也失败:控制点斜率从 2.89 骤降到 0.18,
    插值器在急弯处冲过头再栽下去 —— 实测传递函数非单调(输入 0.075→0.123 是峰,0.21→0.079),
    高饱和区反而被压垮。**斜率骤变的分段曲线交给样条插值是不可靠的。**

    → 在 Python 里显式做:V 与色相保持不变,只改 S。
      S' = S · g(S),g 在**低饱和(盘)**给足、随 S 升高线性退到 1(**核心完全不动**)。
      重建:min' = V(1−S'),mid' = min' + h·(V−min'),其中 h=(mid−min)/(V−min) 即色相位置。"""
    import numpy as np
    from xisf import XISF
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:
        gaussian_filter = None
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1).astype(np.float32)

    def _bail(msg):
        XISF.write(out_path, img, *_read_meta(xn))
        if preview_path:
            _save_preview(img, preview_path)
        if log:
            log("  <星系提饱和跳过:" + msg + ">")
        return out_path

    if gaussian_filter is None:
        return _bail("缺 scipy")
    L = img.mean(-1)
    sm = gaussian_filter(L, max(6.0, min(L.shape) / 170.0))
    b, sg = _bg_stat(sm)
    body = sm > b + 12.0 * sg
    if int(body.sum()) < 2000 or sg <= 1e-9:
        return _bail("找不到天体本体")
    # 【★必须按「信号」口径量饱和度(用户 2026-09-15 M63)】盘区像素 = 背景基座 + 信号。
    #   基座会把 HSV 饱和度稀释:M63 盘区信号口径 S=0.243,含基座只量到 **0.076** —— 按后者去够
    #   目标 0.26 需要 **×3.44** 的增益,把信号的色相极度夸张、B(最小通道)被狠狠压下去,
    #   正是「星系发黄、偏蓝旋钮怎么加都没用」的来源。与 [[pi-mtf-crushes-highlight-chroma]] 里
    #   色比还原踩的是同一个坑:**跨背景比颜色/量色度之前必须先扣背景**。
    #   用户手工库实测(9 张星系片)信号口径盘区 S 中位 **0.277**(范围 0.08~0.42,按星系类型真实变化)。
    _bgsel = sm < b + 1.0 * sg
    BGc = (np.median(img[_bgsel].reshape(-1, 3), 0).astype(np.float32)
           if int(_bgsel.sum()) > 5000 else np.zeros(3, np.float32))
    sig = img - BGc[None, None, :]
    V = sig.max(-1); mn = sig.min(-1)
    S = np.where(V > 1e-5, (V - mn) / np.maximum(V, 1e-5), 0.0).astype(np.float32)
    Vpix = img.max(-1)                                   # 削顶保护仍看**像素**亮度
    # 【量 s_disc 必须用**平滑后**的信号(2026-09-15)】S=(V−min)/V 在低信噪区会被噪声灌满:
    #   同一张 M63,逐像素量到 0.133、平滑后只有 0.240 —— 而且噪声水平不同的两张图之间完全不可比
    #   (见 [[pi-noise-artifact-in-color-measurement]])。增益仍逐像素施加,只有**测量**要平滑。
    _ssc = min(L.shape) / 2051.0
    _blm = np.stack([gaussian_filter(sig[..., c], max(1.0, 4.0 * _ssc)) for c in range(3)], -1)
    _Vm = _blm.max(-1); _mnm = _blm.min(-1)
    Smeas = np.where(_Vm > 1e-5, (_Vm - _mnm) / np.maximum(_Vm, 1e-5), 0.0).astype(np.float32)
    reg = L[body]
    lo, hi = (float(v) for v in np.percentile(reg, [30, 65]))
    disc = body & (L >= lo) & (L <= hi)
    core = body & (L >= float(np.percentile(reg, 90)))
    if int(disc.sum()) < 500:
        return _bail("盘区样本不足")
    s_disc = float(np.median(Smeas[disc]))
    s_core = float(np.median(Smeas[core])) if int(core.sum()) >= 200 else s_disc * 2.0
    if s_disc <= 1e-4 or s_disc >= float(target):
        return _bail(f"盘区实测 {round(s_disc,3)} 已达目标 {target}")
    k = float(target) / s_disc                                  # 盘需要的倍数
    # 【淡出必须按 V(亮度)而不是 S(用户 2026-09-14「星系核心的颜色不对」)】
    #   第一版按 S 淡出(核心饱和高就不提)——**搞反了**:接近白色的亮核 S 恰恰很低。
    #   实测 M66 最核心 V=0.987 而 **S 只有 0.111**,比星系盘的 0.089~0.102 高不了多少,
    #   于是拿了满增益;HSV 提饱和保 V 不变、压低 G 和 B,核心 R/G 就从 1.084 冲到 1.189
    #   (R 一点没涨,是 G 被压下去了)→ 成片上是一团粉红,而用户手动版那里是近中性的。
    #   V 能把两者分得很干净:盘 0.27~0.44,核 0.74~0.99 → 按 V 淡出。
    #   S 的淡出保留为辅助(已经很有色的地方别再叠),两者取乘积。
    s_hi = max(s_core, s_disc * 1.5)
    tS = np.clip((s_hi - S) / max(1e-6, s_hi - s_disc), 0.0, 1.0)
    tS = np.where(S <= s_disc, 1.0, tS)
    tV = np.clip((float(v_hi) - Vpix) / max(1e-6, float(v_hi) - float(v_lo)), 0.0, 1.0)
    g = (1.0 + (k - 1.0) * tS * tV).astype(np.float32)
    # 本体权重:盘处爬满、背景为 0(蒙版文件优先,没有就按亮度算)
    if mask_path:
        try:
            w = np.clip(_norm01(XISF(mask_path).read_image(0)), 0, 1).astype(np.float32)
            w = w[..., 0] if w.ndim == 3 else w
        except Exception:
            w = None
    else:
        w = None
    if w is None or w.shape != L.shape:
        w = np.clip((sm - (b + 3.0 * sg)) / (5.0 * sg), 0.0, 1.0).astype(np.float32)
    S2 = np.clip(S * (1.0 + (g - 1.0) * w), 0.0, 0.995).astype(np.float32)
    # 重建:V 与色相(中间通道的相对位置)不变
    rng = np.maximum(V - mn, 1e-6)
    mid = sig.sum(-1) - V - mn
    h = np.clip((mid - mn) / rng, 0.0, 1.0)
    mn2 = V * (1.0 - S2)
    mid2 = mn2 + h * (V - mn2)
    out = np.empty_like(sig)
    imx = sig.argmax(-1); imn = sig.argmin(-1)
    for c in range(3):
        out[..., c] = np.where(imx == c, V, np.where(imn == c, mn2, mid2))
    out = out + BGc[None, None, :]                        # 背景基座原样加回,背景严格不动
    # 信号太弱(噪声)或三通道相等时 argmax/argmin 会撞车 → 直接回填原值
    flat = ((V - mn) < 1e-5) | (V <= 1e-5)
    if flat.any():
        out[flat] = img[flat]
    out = np.clip(out, 0, 1).astype(np.float32)
    XISF.write(out_path, out, *_read_meta(xn))
    if preview_path:
        _save_preview(out, preview_path)
    if log:
        nV = out.max(-1)
        log(f"  → 星系本体提饱和(**信号口径** HSV,V 不动):盘信号 S {round(s_disc,3)}→{target}(×{round(k,2)});"
            f"核处增益按 V 退到 1.0(V {v_lo}→{v_hi} 之间淡出,完全不提);"
            f"最大通道变化 {float(np.median((nV - V)[body])):+.5f}(应为 0),"
            f"V≥0.99 占比 {round(float(np.mean(nV[body] >= 0.99)) * 100, 2)}%(提饱和前 "
            f"{round(float(np.mean(V[body] >= 0.99)) * 100, 2)}%)")
    return out_path


def hii_significance(flowers_path: str, ref_path: str, thr: float = 0.3) -> dict:
    """量提取出的 HII(小红花)信号**在天体本体内**的富余程度。返回
    {"in_frac","bg_frac","ratio","body_frac"};测不出返回全 0。

    【为什么不能用"占整幅画面的比例"当闸门(用户 2026-09-14 狮子座三重星系「双窄带的 Hα 没加进成片」)】
    原闸门是 `占画面比例 < 0.3% 就跳过`,那是在 M31/M52 这类**填满画面**的目标上定的。狮子座三重星系
    三个星系加起来才占画面 **0.662%** —— 要让 HII 占到画面的 0.3%,得覆盖星系面积的 45%,不可能。
    实测该目标:HII 占画面 0.084%(被判"太弱"跳过),但**占星系本体 1.6%**,
    而本体内密度是背景密度的 **22 倍** —— 信号是真的,只是小。
    (同一类坑见 [[pi-lumprobe-anchor-trap]]:小天体大视场下全画面分位没有意义。)

    同时给出 `ratio`(本体内密度 / 背景密度)——提取结果里有 87% 落在背景(噪声),
    只看 in_frac 会把纯噪声的提取也放行,必须再看这个比值。"""
    import numpy as np
    from xisf import XISF
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:
        return {"in_frac": 0.0, "bg_frac": 0.0, "ratio": 0.0, "body_frac": 0.0}
    try:
        fl = _norm01(XISF(flowers_path).read_image(0))
        if fl.ndim == 3:
            fl = fl[..., :3].mean(-1)
        rf = _norm01(XISF(ref_path).read_image(0))
        L = (rf[..., :3].mean(-1) if rf.ndim == 3 else rf).astype(np.float32)
        if fl.shape != L.shape:
            return {"in_frac": 0.0, "bg_frac": 0.0, "ratio": 0.0, "body_frac": 0.0}
        sm = gaussian_filter(L, max(6.0, min(L.shape) / 170.0))
        b, sg = _bg_stat(sm)
        if sg <= 1e-9:
            return {"in_frac": 0.0, "bg_frac": 0.0, "ratio": 0.0, "body_frac": 0.0}
        body = sm > b + 12.0 * sg
        nb = int(body.sum())
        if nb < 1000:
            return {"in_frac": 0.0, "bg_frac": 0.0, "ratio": 0.0, "body_frac": 0.0}
        hit = fl > float(thr)
        inf = float((hit & body).sum()) / nb
        bgf = float((hit & ~body).sum()) / max(int((~body).sum()), 1)
        # 【连续谱判据:真 Hα 只该出现在 R,不该出现在 G(用户 2026-09-14 「Hα 加到汉堡星系两侧去了」)】
        #   把同样的高通用在**宽带**上,量提取命中处相对随机位置的富余;
        #   真发射线 → R 的富余明显高于 G(rg_excess > 1);
        #   若 G 同样高甚至更高 = 那是**连续谱结构/高通伪影**,不是发射线。
        #   实测该目标:R 富余 8.9x、**G 富余 12.0x** → rg_excess 0.74 —— 提取出来的"Hα"其实是
        #   高通在细长星系两端产生的振铃(最亮的脊被"排除超亮区"清零,只剩两端),必须拒。
        rg = 0.0
        try:
            if rf.ndim == 3 and int(hit.sum()) >= 100:
                rng = np.random.default_rng(0)
                idx = rng.choice(L.size, int(hit.sum()), replace=False)
                exc = []
                for c in (0, 1):
                    ch = rf[..., c].astype(np.float32)
                    hp = np.clip(ch - gaussian_filter(ch, 22.0), 0, None)
                    e = float(np.median(hp[hit])) / max(float(np.median(hp.ravel()[idx])), 1e-12)
                    exc.append(e)
                rg = round(exc[0] / max(exc[1], 1e-9), 2)
        except Exception:
            rg = 0.0
        return {"in_frac": round(inf, 5), "bg_frac": round(bgf, 5),
                "ratio": round(inf / max(bgf, 1e-9), 1), "body_frac": round(float(body.mean()), 5),
                "rg_excess": rg}
    except Exception:
        return {"in_frac": 0.0, "bg_frac": 0.0, "ratio": 0.0, "body_frac": 0.0}


def body_protect_mask(img_path: str, out_path: str, bg_w: float = 0.85,
                      body_w: float = 0.30) -> str | None:
    """给**降噪**用的主体保护蒙版:背景处权重 bg_w、天体本体处降到 body_w,中间平滑过渡。
    返回 out_path;测不出本体返回 None(调用方就不挂蒙版)。

    【为什么(用户 2026-09-14 狮子座三重星系「星系的蓝出不来」)】铁律早已定过
    「"背景噪点多"≠全图降噪,必挂主体蒙版」(见 [[pi-denoise-background-mask]]),但**线性强降噪
    r05_dn 一直是全图无蒙版的 denoise 0.90 × 2 轮**。星系盘的蓝信噪最低、被抹得最狠:
      降噪前(SPCC 后)三个星系盘 B-G  -14.0% / -9.7% / **+1.8%**
      无蒙版降噪后                    -21.2% / -21.7% / -13.8%   <- 蓝被吃掉
      **挂本蒙版后**                  -18.1% / -14.9% / **-3.8%**  <- 挽回六到七成
    而背景降噪几乎不受影响:背景像素噪声降到降噪前的 44.0%(无蒙版)vs **51.0%**(带蒙版)。
    权重 0.85/0.30 沿用记忆里既定的配方。

    本体判定用**平滑后的显著性**(sm > 背景 + 4σ 起,到 +12σ 满),线性图上同样适用。"""
    import numpy as np
    from xisf import XISF
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:
        return None
    try:
        a = _norm01(XISF(img_path).read_image(0))
        L = (a[..., :3].mean(-1) if a.ndim == 3 else a).astype(np.float32)
        sm = gaussian_filter(L, max(6.0, min(L.shape) / 170.0))
        b, sg = _bg_stat(sm)
        if sg <= 1e-9:
            return None
        w = np.clip((sm - (b + 4.0 * sg)) / (8.0 * sg), 0.0, 1.0)
        if float(w.mean()) < 1e-5:
            return None                                   # 没有可辨认的本体 → 不必挂
        m = (float(bg_w) - (float(bg_w) - float(body_w)) * w).astype(np.float32)
        XISF.write(out_path, np.stack([m] * 3, -1), None, None)
        return out_path
    except Exception:
        return None


def green_cast_curve(img_path: str, k: float = 1.3, dom_floor: float = 0.38) -> list | None:
    """量出天体本体的**真绿超出量**,返回一条给 CurvesTransformation 用的 **G 通道曲线点**;
    绿本来就不过量(绿占优 ≤ dom_floor)→ 返回 None(不必动)。

    【为什么不用 SCNR(用户 2026-09-14 定的原则)】「处理星系/星云时确实要避免主体发绿,但**用 SCNR 去绿
    不可取**,会导致星系整体偏黄、蓝色难以体现。星系校色主要靠 BN-CC 或 SPCC,在此基础上如果还发现发绿,
    再通过 CT 曲线微调。」
    机理:SCNR 的 average-neutral 是「凡 G>(R+B)/2 就按比例削」——对 R>G>B 的黄色天体**越黄削得越多**
    (见 [[pi-scnr-yellows-to-orange]]),而且它会连背景一起改。曲线是按**实测的绝对超出量**在对应 G 值上
    减掉一点,背景处设锚点(输出=输入)不动、高光钉 (1,1) 保住核心。

    判据用**绿占优**(G 同时高于 R 和 B)的占比:中性噪声下期望是 1/3。狮子座三重星系实测对照——
      去绿前 89.3%(核心 R-G -1.2%)
      现行 SCNR 0.5 → 27.7%(**低于中性=过校正**),核心 R-G 被推到 +2.5%
      **G 曲线 k=1.3 → 32.6%(正落在中性),核心 R-G 仅 +1.3%**,且背景 R-G/B-G 一点没变
    即:用一半的偏色代价做到更干净的去绿。k 就是"减掉几倍的实测中位超出量"。"""
    import numpy as np
    from xisf import XISF
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:
        return None
    try:
        a = np.clip(_norm01(XISF(img_path).read_image(0))[..., :3], 0, 1).astype(np.float32)
        R, G, B = a[..., 0], a[..., 1], a[..., 2]
        L = a.mean(-1)
        sm = gaussian_filter(L, max(6.0, min(L.shape) / 170.0))
        b0, s0 = _bg_stat(sm)
        body = sm > b0 + 12.0 * s0
        if int(body.sum()) < 2000 or s0 <= 1e-6:
            return None
        dom = (G > R) & (G > B)
        if float(dom[body].mean()) <= float(dom_floor):
            return None                                  # 绿没过量 → 不动
        exc = np.where(dom, G - np.maximum(R, B), 0.0)
        gs = G[body]
        pts = []
        for lo, hi in ((10, 30), (30, 50), (50, 70), (70, 90), (90, 99)):
            t0, t1 = (float(v) for v in np.percentile(gs, [lo, hi]))
            band = body & (G >= t0) & (G <= t1)
            sel = band & dom
            if int(sel.sum()) < 200:
                continue
            gm = float(np.median(G[band])); e = float(np.median(exc[sel])) * float(k)
            if e > 1e-4:
                pts.append((round(gm, 4), round(max(0.0, gm - e), 4)))
        if not pts:
            return None
        bg_g = round(float(np.median(G[~body])), 4)       # 背景锚点:输出=输入,背景一点不动
        out = {0.0: 0.0, bg_g: bg_g, 1.0: 1.0}
        for x, y in pts:
            if x > bg_g:
                out[x] = y
        return [[x, out[x]] for x in sorted(out)]
    except Exception:
        return None


def green_protect_level(img_path: str, dom_tol: float = 0.15) -> dict:
    """找出「绿真的占优」的**亮度上界**:亮过它的地方绿早就不占优了,再去绿只会削掉真实的黄。
    返回 {"level", "dom_bright", "dom_faint"};level=None 表示整幅亮区都有绿、不必护。

    【为什么(用户 2026-09-14 狮子座三重星系「最后的成片星系发黄」)】SCNR 的 average-neutral 判据是
    「G > (R+B)/2 就算有绿」。可**只要是 R>G>B 的黄色渐变,G 就必然高于两端平均** —— 那是算术,不是绿偏色。
    实测 NGC3628 核心 R=1.078G、B=0.701G → (R+B)/2=0.889G,于是被判「有绿」而削掉 11% 的 G,
    黄核被削成橙核(R-G 由 +7.8% 变 +15.5%)。整个星系本体 99.55% 的像素都被该判据判成「有绿」。
    **真正的绿偏色应该是 G 同时高于 R 和 B。** 按这个判据分层实测:
      最亮 10%(核)绿占优 5.1% | 次亮 9.4% | 中段 29.0% | 最暗 40%(外盘)40.8%
    —— 绿全在**暗的外盘**(低信噪噪声),核心几乎没有。所以去绿要挂亮度蒙版护住亮核,
    别无差别作用(同 [[pi-denoise-background-mask]] 的道理:"背景噪点多"不等于全图降噪)。"""
    import numpy as np
    from xisf import XISF
    try:
        a = np.clip(_norm01(XISF(img_path).read_image(0))[..., :3], 0, 1).astype(np.float32)
        R, G, B = a[..., 0], a[..., 1], a[..., 2]
        L = a.mean(-1)
        dom = (G > R) & (G > B)                       # 真绿占优
        # 【必须只在天体本体里找,别拿全图分位】天体常只占画面千分之几,全图 p75 还是背景 —— 在背景里
        #   量绿占优会得到一个远低于本体的界(实测 0.177,而本体的界在 0.45 附近)。
        #   先用平滑亮度圈出显著延展源(星点被抹平),再在它内部按亮度分层找绿退场的位置。
        try:
            from scipy.ndimage import gaussian_filter as _gf
        except Exception:
            return {"level": None, "dom_bright": 0.0, "dom_faint": 0.0}
        sm = _gf(L, max(6.0, min(L.shape) / 170.0))
        b0, sg = _bg_stat(sm)
        body = sm > b0 + 12.0 * sg
        if int(body.sum()) < 2000:
            return {"level": None, "dom_bright": 0.0, "dom_faint": 0.0}
        reg = L[body]
        lo, hi = (float(v) for v in np.percentile(reg, [10, 99]))
        if not (hi > lo):
            return {"level": None, "dom_bright": 0.0, "dom_faint": 0.0}
        edges = np.linspace(lo, hi, 9)
        lvl = None
        for i in range(len(edges) - 1):
            m = body & (L >= edges[i]) & (L < edges[i + 1])
            if int(m.sum()) < 300:
                continue
            if float(dom[m].mean()) < float(dom_tol):
                lvl = round(float(edges[i]), 3)
                break
        if lvl is None:
            return {"level": None, "dom_bright": 0.0, "dom_faint": round(float(dom[body].mean()), 3)}
        return {"level": lvl,
                "dom_bright": round(float(dom[body & (L >= lvl)].mean()), 3),
                "dom_faint": round(float(dom[body & (L < lvl)].mean()), 3)}
    except Exception:
        return {"level": None, "dom_bright": 0.0, "dom_faint": 0.0}


def background_floor(img_path: str, k: float = 1.5) -> dict:
    """**背景电平 + 噪声宽度**(非线性图;通道均值 (R+G+B)/3 标度,与 job-runner lumprobe / rangemask
    lightness:False 同尺)。返回 {"level","width","floor"},floor = level + k*width。

    用途:给"只选天体本体"的 range 蒙版定下限。**下限必须由背景自身的噪声宽度决定**,不能只靠
    lumprobe 的亮度锚点——锚点的 `faint` 是全图 **p90~p97** 均值,对"小天体 + 大视场"这种画面
    (M63 星系只占不到 1% 面积)**那一段仍然是背景的亮尾**:实测 faint 0.1768 = 背景中位 + 2.0σ,
    于是 (background+faint)/2 只有 bg+0.79σ,一半背景被选进蒙版(用户 2026-09-13 实见:提饱和把
    背景也提了、成为背景偏色的来源)。

    估计方式用**低侧分位**:亮天体只往高侧加,故 p50 近似背景电平、(p50−p16) 近似噪声 σ。
    M63 实测 p50=0.1472 / 宽度 0.0181,对比真值(远景)中位 0.1436 / σ 0.0169 —— 误差 <0.004。"""
    import numpy as np
    from xisf import XISF
    try:
        a = _norm01(XISF(img_path).read_image(0))
        L = (a[..., :3].mean(-1) if a.ndim == 3 else a).astype(np.float32)
        p16, p50 = (float(v) for v in np.percentile(L, [16, 50]))
        w = max(1e-4, p50 - p16)
        return {"level": round(p50, 4), "width": round(w, 4), "floor": round(p50 + float(k) * w, 4)}
    except Exception:
        return {"level": 0.0, "width": 0.0, "floor": 0.0}


def neutralize_bg_offset(in_path: str, out_path: str, dark_pct: float = 30.0,
                         preview_path: str | None = None):
    """**线性图背景逐通道偏移中和**(白平衡背景;用户 2026-09-09 M45 洋红铸)。各通道测天光电平,减去偏移使三通道
    背景相等 → 之后 **linked 拉伸不再把微小通道差(如 GraXpert 后 G/B 差 ~1e-5)放大成偏色**。**只减均匀偏移
    (=色铸/白平衡),不动色彩空间结构**——真实尘色是空间结构不是均匀偏移,不受影响。
    返回 out_path;单通道/异常返回 None(调用方保留原图)。

    【2026-09-13 M63 重做估计方式:旧版把外围云气染成紫色】旧版取**最暗 dark_pct% 像素**(按 max 通道选)的
    各通道中位当背景电平。这个选择器**对噪声有偏**:挑"最暗"的像素会优先挑中噪声向下涨落的像素,**通道噪声
    越大被拉得越低**。M63 实测 B 的 sigma 0.000195 ≈ G(0.000110)的 1.8 倍 → 暗区里蓝显得比绿低 8.3e-5,
    可全图中位其实是蓝比绿**高** 1.0e-5。于是这步从 R/G 各减掉 8.3e-5 去对齐那个假的低蓝 = **等于给蓝全局
    加了 8.3e-5**;linked 拉伸放大约 7 倍后 B−G 达亮度的 +44%、R−G +17% → 外围云气整片发紫(用户实见)。
    → 改用**直方图众数**(对噪声无偏、对亮天体不敏感)。M63 实测 ring/far 的 B−G 由 +6.77%/+6.70%
    回到 −0.12%/−0.24%(线性未做梯度处理的 r03_colorcal 基准是 +0.39%/−0.08%)。
    `dark_pct` 保留只为兼容旧调用签名,不再使用。见 [[pi-galaxy-halo-vignette-degeneracy]]。"""
    import numpy as np
    from xisf import XISF
    try:
        xn = XISF(in_path)
        a = _norm01(xn.read_image(0))
        if a.ndim == 2 or a.shape[-1] < 3:
            return None                                  # 单通道无偏色可言
        out = np.clip(a[..., :3], 0.0, 1.0).astype(np.float32)
        # 多个 bin 数取平均,削掉单一直方图分箱带来的抖动(实测各档差 ~6e-6,远小于待修偏移)
        lev = np.array([np.mean([_sky_mode(out[..., c], bins=b) for b in (2000, 4000, 8000)])
                        for c in range(3)], dtype=np.float32)
        off = (lev - lev.min()).astype(np.float32)        # 减到都等于最低通道 → 只去偏移、不抬亮
        if float(off.max()) >= 1e-7:
            out = np.clip(out - off[None, None, :], 0.0, 1.0).astype(np.float32)
        img_meta = None
        file_meta = None
        try: img_meta = xn.get_images_metadata()[0]
        except Exception: pass
        try: file_meta = xn.get_file_metadata()
        except Exception: pass
        XISF.write(out_path, out, image_metadata=img_meta, xisf_metadata=file_meta)
        if preview_path:
            try: _save_preview(out, preview_path)
            except Exception: pass
        return out_path
    except Exception:
        return None


def screen_recombine(neb_path: str, stars_path: str, out_path: str,
                     star_amount: float = 1.0, preview_path: str | None = None) -> str:
    """官方星点合成 `~(~T*~stars)` = **逐通道 screen(滤色)** `1-(1-neb)(1-star)`(用户 2026-09-06 指出)。

    **为什么用它取代 chroma_recombine**:
    - 与 SXT `unscreen=true` **互逆成对** → 数学自洽、**自然融合**(星点不硬贴)。chroma 法把色度硬替换
      (有星处直接 Cs=star/Ls 顶掉星云色)= 硬贴观感 + Cs 除以 Ls 放大暗弱翼 = 光晕/绿 bug 的根。screen 都没有。
    - **暗背景**(M1 星场、多数星云外围)star 色照常保留(neb≈0 时 out≈star);**亮星云内**星点被前景辉光
      自然稀释(物理正确)。chroma 当初是为治 M23"亮背景洗白星色"过度设计,暗背景根本不需要。
    保 neb 的 xisf 头(色彩空间/WCS);可选出预览。返回 out_path。"""
    import numpy as np
    from xisf import XISF
    xn = XISF(neb_path)
    neb = _norm01(xn.read_image(0))
    star = _norm01(XISF(stars_path).read_image(0)) * float(star_amount)
    if neb.ndim == 2:
        neb = np.stack([neb] * 3, -1)
    if star.ndim == 2:
        star = np.stack([star] * 3, -1)
    neb = np.clip(neb[..., :3], 0, 1)
    star = np.clip(star[..., :3], 0, 1)
    out = np.clip(1.0 - (1.0 - neb) * (1.0 - star), 0.0, 1.0).astype(np.float32)
    im, fm = _read_meta(xn)
    XISF.write(out_path, out, image_metadata=im, xisf_metadata=fm)
    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def _save_preview(out, preview_path, long_side=1600):
    import numpy as np
    try:
        from PIL import Image
        h, wd = out.shape[:2]
        s = min(1.0, float(long_side) / max(h, wd))
        pim = Image.fromarray((np.clip(out, 0, 1) * 255.0 + 0.5).astype(np.uint8), "RGB")
        if s < 1.0:
            pim = pim.resize((max(1, int(wd * s)), max(1, int(h * s))), Image.LANCZOS)
        pim.save(preview_path)
    except Exception:
        pass


def _read_meta(xn):
    im = fm = None
    try:
        im = xn.get_images_metadata()[0]
    except Exception:
        im = None
    try:
        fm = xn.get_file_metadata()
    except Exception:
        fm = None
    return im, fm


def classify_bg(img_path: str, grid=(16, 28),
                color_thr: float = 0.05, lum_thr: float = 0.09) -> dict:
    """【r06 背景判据·策略分流(用户 2026-09-03)】用拉伸后(r06)背景决定后续策略,而非天体类型。

    背景『平坦中性』(如 M54 人马座密集星场)→ 干净星场路线(克制:不揭示/不上星链/温和全局饱和);
    背景『有色彩或结构』(如 M28,r06 就见背景色彩变化)→ 星云/揭示路线。判据两条:
      · color_spatial: 把图切网格,每格取暗部(自适应 p50)算**归一化色比**(去亮度),取各格色比的空间 std。
        真星云/尘=各处颜色不同→大;平坦场=只剩噪声→小。**对全局均匀绿铸不敏感**(SCNR 前的绿是均匀的,
        空间 std 仍小)——正是要的:均匀色铸不算"有结构"。
      · lum_spatial: 各格暗部亮度均值的**相对**空间 std。有梯度/亮星云→大;平坦→小。
    两者都低于阈值 → flat_neutral。阈值以 M54 实测(color 0.033 / lum 0.054)为平坦锚点、留余量。
    """
    import numpy as np
    _pl = str(img_path).lower()
    if _pl.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):   # 评委/成片评判拿到的是 png → 直接读
        from PIL import Image
        img = np.asarray(Image.open(img_path).convert("RGB")).astype(np.float32) / 255.0
    else:
        from xisf import XISF
        img = _norm01(XISF(img_path).read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    H, W = img.shape[:2]
    V = img.max(-1)
    bg = V < np.percentile(V, 40)
    mR, mG, mB = (float(img[..., c][bg].mean()) for c in range(3))
    mavg = (mR + mG + mB) / 3.0
    neutrality = (max(mR, mG, mB) - min(mR, mG, mB)) / max(1e-5, mavg)
    gy, gx = grid
    col_ratio, lum_cell = [], []
    for j in range(gy):
        for i in range(gx):
            sub = img[j * H // gy:(j + 1) * H // gy, i * W // gx:(i + 1) * W // gx]
            sv = sub.max(-1)
            m = sv < np.percentile(sv, 50)
            if int(m.sum()) < 20:
                continue
            cm = sub.reshape(-1, 3)[m.reshape(-1)].mean(0)
            s = float(cm.mean())
            lum_cell.append(s)
            if s > 1e-5:
                col_ratio.append(cm / s)
    color_spatial = float(np.array(col_ratio).std(0).mean()) if col_ratio else 0.0
    lum_spatial = (float(np.std(lum_cell) / max(1e-5, np.mean(lum_cell)))
                   if lum_cell else 0.0)
    flat_neutral = (color_spatial < color_thr) and (lum_spatial < lum_thr)
    return {"flat_neutral": bool(flat_neutral),
            "color_spatial": round(color_spatial, 4),
            "lum_spatial": round(lum_spatial, 4),
            "neutrality": round(neutrality, 3),
            "bg_means": [round(mR, 5), round(mG, 5), round(mB, 5)]}


def signal_coverage(img_path: str, contrast_thr: float = 0.30,
                    cov_thr: float = 0.06) -> dict:
    """【局部星云判据(用户 2026-09-06 M1)】判"是不是 M1 型:中心一小块**亮**星云 + 周围密集星场/暗背景",
    以便**关揭示、别强行抬背景**。要与「M42:亮而满屏」「NGC7000:暗而满屏(真需揭示)」区分开。

    **在去星图(starless)上测**(点星已除,只剩延展信号 + 天光背景)。全分辨率、天光相对(不做盒平均——
    盒平均会把小星云稀释、把密集星场星光糊成假背景,M1 实测因此失效)。三步:
      · sky = 全图 p10(星点间真天光暗电平);
      · pk  = 最亮 0.05% 像素均值(真亮天体峰值,避开单点热点);contrast = pk − sky;
      · 只在 **contrast > contrast_thr(有确实很亮的天体,≈0.30)** 时才可能判局部——暗弥散星云 contrast 低、
        永远不触发(安全:该揭示的照常揭示);此时 bright_thr = sky + 0.45·contrast(明显"天体"非"天光尾"),
        bright_cov = 高于 bright_thr 的画面比例;**bright_cov < cov_thr(≈6%)= 亮天体很小 = 局部星云**。
    M1 实测:sky0.143 / pk0.704 / contrast0.561 / bright_cov0.0014 → localized。M42/NGC7000 分别因 cov 大 / contrast 小而不触发。
    """
    import numpy as np
    _pl = str(img_path).lower()
    if _pl.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        from PIL import Image
        img = np.asarray(Image.open(img_path).convert("RGB")).astype(np.float32) / 255.0
    else:
        from xisf import XISF
        img = _norm01(XISF(img_path).read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    V = np.clip(img[..., :3].max(-1), 0, 1).ravel()   # 亮度(通道最大,对彩色星云敏感)
    sky = float(np.percentile(V, 10))
    Vs = np.sort(V)
    ntop = max(50, V.size // 2000)                     # 最亮 0.05%
    pk = float(Vs[-ntop:].mean())
    contrast = pk - sky
    if contrast > contrast_thr:
        bright_thr = sky + 0.45 * contrast
        bright_cov = float((V > bright_thr).mean())
        localized = bool(bright_cov < cov_thr)
    else:
        bright_thr = float("nan"); bright_cov = float("nan"); localized = False
    # 【极小天体补充判据(用户 2026-09-11 M57 行星状星云)】取峰窗口 0.05%(8MP≈4000px)对**很小的天体**
    #   会被背景稀释:M57 环仅约 700 亮像素,pk 被 3200+ 背景拉低到 0.396 → contrast 0.241<0.30 漏判,
    #   于是按"弥散星云"开了揭示+强拉 → 空场背景被抬到 0.295、噪声放大成斑驳,星点也在亮背景上被冲淡
    #   (成片 s_star 仅 0.11)。→ 再用**小窗口(0.01%)**量一次峰值;但**不放宽尺寸门**,反而收严到
    #   bright_cov < 0.005(主判据是 0.06):只有"确实很亮 + 只占画面千分之五以内"才认小天体,
    #   NGC7000 那类"暗而满屏、真需揭示"的弥散星云占比远大于此,不会被误关揭示。M57 实测:
    #   小窗 pk 0.694 / contrast 0.540 / bright_cov 0.00009 → localized。见 [[pi-stretch-dynamic-range]]。
    tiny = False
    if not localized:
        ntop2 = max(50, V.size // 10000)               # 最亮 0.01%
        pk2 = float(Vs[-ntop2:].mean())
        contrast2 = pk2 - sky
        if contrast2 > contrast_thr:
            bt2 = sky + 0.45 * contrast2
            cov2 = float((V > bt2).mean())
            if cov2 < 0.005:
                tiny = True; localized = True
                pk = pk2; contrast = contrast2; bright_thr = bt2; bright_cov = cov2
    return {"localized": localized, "tiny": tiny,
            "bright_cov": (round(bright_cov, 4) if bright_cov == bright_cov else None),
            "contrast": round(contrast, 4), "sky": round(sky, 4), "pk": round(pk, 4),
            "bright_thr": (round(bright_thr, 4) if bright_thr == bright_thr else None)}


def edge_lowsnr_margins(img_path: str, noise_ratio: float = 1.35,
                        step_frac: float = 0.02, max_frac: float = 0.14) -> dict:
    """【低信噪边预裁判据(用户 2026-09-06 M4)】离轴/跟踪漂移致某些边**欠覆盖**——读噪比中心高,但
    **亮度未必低**(所以按亮度的边缘裁切 detectBordersCoverage 抓不到)。这种噪声边会把后面**梯度矫正**的
    背景拟合带歪:M4 实测离轴致右/下低信噪 → 梯度后**右黑边** + **左暗云被当背景多扣变淡**(reveal 追不回)。

    判据用**相邻像素差分的 MAD**(高通:只留读噪,去掉暗云/星云的低频真结构)→ 暗云边(低频结构)读噪=
    中心水平不会被误裁,欠覆盖边(高频读噪)才被抓。逐带(step_frac)向内扫,差分读噪比中心 >noise_ratio
    就继续裁、回落即停(裁到刚好去掉欠覆盖带),单边上限 max_frac。返回 {margins:{left,right,top,bottom}像素,
    diag, center_noise}。**在线性母版上测**(读噪最纯)。梯度矫正**前**用。"""
    import numpy as np
    _pl = str(img_path).lower()
    if _pl.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        from PIL import Image
        img = np.asarray(Image.open(img_path).convert("RGB")).astype(np.float32) / 255.0
    else:
        from xisf import XISF
        img = _norm01(XISF(img_path).read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    V = np.clip(img[..., :3], 0, 1).mean(-1)
    H, W = V.shape

    def ndn(a):                                   # 相邻像素差分 MAD(高通读噪)
        d = (np.diff(a, axis=1) if a.shape[1] > 1 else np.diff(a, axis=0)).ravel()
        if d.size == 0:
            return 0.0
        return float(np.median(np.abs(d - np.median(d))) * 1.4826)

    cn = ndn(V[int(H * 0.35):int(H * 0.65), int(W * 0.35):int(W * 0.65)]) or 1e-9
    sx = max(1, int(W * step_frac)); sy = max(1, int(H * step_frac))
    mx = int(W * max_frac); my = int(H * max_frac)

    def scan(get, n, s, cap):
        depth = 0; ratios = []
        for k in range(max(1, n)):
            r = ndn(get(k)) / cn
            ratios.append(round(r, 2))
            if r > noise_ratio:
                depth = (k + 1) * s
            else:
                break
        return min(depth, cap), ratios

    _l, _dl = scan(lambda k: V[:, k * sx:(k + 1) * sx], mx // sx, sx, mx)
    _r, _dr = scan(lambda k: V[:, W - (k + 1) * sx:W - k * sx], mx // sx, sx, mx)
    _t, _dt = scan(lambda k: V[k * sy:(k + 1) * sy, :], my // sy, sy, my)
    _b, _db = scan(lambda k: V[H - (k + 1) * sy:H - k * sy, :], my // sy, sy, my)
    return {"margins": {"left": int(_l), "right": int(_r), "top": int(_t), "bottom": int(_b)},
            "diag": {"left": _dl, "right": _dr, "top": _dt, "bottom": _db},
            "center_noise": round(cn, 6)}


def boost_star_sat(img_path: str, out_path: str, gain: float = 1.0,
                   lum_gate: float = 0.02, star_only: bool = False,
                   preview_path: str | None = None) -> dict:
    """【星点饱和·numpy HSV 乘法(用户 2026-09-06 M4/M7)】按**显式增益 gain** 缩放饱和度:逐像素
    `out=mx−(mx−img)·gain`(明度 max/色相不变,只把各通道从 max 拉开或收拢)。gain>1 提饱和、<1 降饱和。
    **不自己测**(旧版内部用"最亮1%像素 HSV 均值"测,M7 富星场里最亮1%是过曝发白团核 HSV饱和极低→误判要狂提×4
    →过爆;见 [[pi-galaxy-deepdata]])——增益由调用方按 `quality.star_saturation`(与UI同标度)闭环算,升降都行。
    **亮度门 lum_gate**:只作用亮度>gate 的像素(星点),背景近黑(mx−img≈0)不动、不放大背景色噪。
    **star_only(用户 2026-09-10 M52「graxpert 后星云更红了」)**:纯亮度门分不清亮星云和恒星 → 会把气泡等
    **亮星云本体一起提饱和**(实测气泡 sat 0.305→0.457、发红过冲,与用户「星云饱和要克制」冲突)。置 True 时
    再乘一层**点状星蒙版**(高通 `V−gauss(V,3)`:点状恒星≈1、延展星云≈0)→ 这步「**星点**饱和校正」名副
    其实只作用真恒星,星云本体保持自然饱和。见 [[pi-shallow-dense-field]]/铁律 8。保 xisf 头。"""
    import numpy as np
    from xisf import XISF
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1).astype(np.float32)
    mx = img.max(-1, keepdims=True)
    V = mx[..., 0]
    g = float(max(0.05, gain))
    w = np.clip((V - lum_gate) / 0.04, 0.0, 1.0)               # 亮度门:背景不动、星点全作用
    if star_only:                                              # 只作用点状恒星、护延展星云本体不被误提饱和
        from scipy.ndimage import gaussian_filter
        _hp = V - gaussian_filter(V, 3.0)                      # 高通:点状星≈1、平滑星云≈0
        # 【再跳过已高饱和像素(用户 2026-09-10 M52「星云放大有色彩断层」)】只有高通会把**细的 Ha 红丝**
        #   当"点状"一起提饱和 → 红丝过饱和(s≈0.43)压在粉色连续谱(s≈0.19)上=硬色彩断层。已高饱和的红丝
        #   本不需要提饱和(要提的是发白恒星),故再按当前饱和**反向加权**:低饱和(白星)全提、高饱和(红丝)
        #   跳过。实测断层 gap 0.297→0.228(回到无 star-sat 的 0.236 以下),恒星照常上色(s_star 保持)。
        _s = (V - img.min(-1)) / np.maximum(V, 1e-5)
        w = w * np.clip(_hp / 0.04, 0.0, 1.0) * np.clip((0.40 - _s) / 0.20, 0.0, 1.0)
    w = w[..., None]
    geff = 1.0 + (g - 1.0) * w
    out = np.clip(mx - (mx - img) * geff, 0.0, 1.0).astype(np.float32)
    im_m, fm_m = _read_meta(xn)
    XISF.write(out_path, out, image_metadata=im_m, xisf_metadata=fm_m)
    if preview_path:
        _save_preview(out, preview_path)
    return {"gain": round(g, 3)}


def nebula_sat(img_path: str, bright_pct: float = 97.0) -> float:
    """星云本体实测饱和度(用户 2026-09-06 M1:艳星点贴闷星云不协调)。取最亮 (100−bright_pct)% 像素
    (=星云信号)的 **HSV S 均值**(S=(max−min)/max,与 runner `starstats.satMean` 同标度),用来把星点
    饱和目标钉到与星云协调。在**去星星云图**上测(亮区=星云,非星点)。M1 蟹云低饱和→星点也该低。"""
    import numpy as np
    _pl = str(img_path).lower()
    if _pl.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        from PIL import Image
        img = np.asarray(Image.open(img_path).convert("RGB")).astype(np.float32) / 255.0
    else:
        from xisf import XISF
        img = _norm01(XISF(img_path).read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    V = img.max(-1)
    m = V >= np.percentile(V, bright_pct)
    if int(m.sum()) < 50:
        m = V >= np.percentile(V, 90)
    px = img[m]
    mx = px.max(-1); mn = px.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-5)
    return float(sat.mean())


def bg_chroma_level(img_path: str) -> dict:
    """暗背景彩噪水平(OSC"七彩油污",用户 2026-09-06)。返回:
      · chroma = 暗背景带(亮度 p20~p65,排除最暗 clip 与亮星/星云)的 **HSV S 均值** —— 干净背景 ≈0.03~0.05,
        油污 ≈0.07+;用来判要不要挂蒙版给背景降饱和。
      · bg_lum = 背景亮度(p30),用来把 suppress_bg_chroma 的 lum_knee 定在"背景之上、星云之下"(护住星云)。
    彩机(OSC)低信噪背景常见,黑白/窄带少见 → 故按图判、不无脑做。"""
    import numpy as np
    _pl = str(img_path).lower()
    if _pl.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        from PIL import Image
        img = np.asarray(Image.open(img_path).convert("RGB")).astype(np.float32) / 255.0
    else:
        from xisf import XISF
        img = _norm01(XISF(img_path).read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    V = img.max(-1)
    mx = img.max(-1); mn = img.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-5)
    lo, hi = np.percentile(V, 20), np.percentile(V, 65)
    m = (V >= lo) & (V <= hi)
    chroma = float(sat[m].mean()) if bool(m.any()) else 0.0
    return {"chroma": round(chroma, 4), "bg_lum": round(float(np.percentile(V, 30)), 4)}


def chroma_floor_for(img_path: str, target: float = 0.04,
                     lo: float = 0.15, hi: float = 0.45) -> float:
    """给 suppress_bg_chroma 反解 `floor`:**压到背景彩噪可接受就停,别一压到底**。
    floor = target / 实测背景彩噪,夹在 [lo, hi]。

    【为什么不能用固定的 floor=0.08(用户 2026-09-13 M64「星系边缘断层」)】那一档把色度压到 8%,
    对**低面亮度星系盘**是灾难:M64 的盘只有 0.10~0.12 亮度、背景 0.09,整个盘都在亮度门(knee 0.152)
    下面 → 盘的饱和度被从 0.226 铲到 0.036,而核心(在门上面)还留着 0.254 → **核心到盘之间 50 倍的
    饱和度断崖**,就是用户看到的"星系边缘断层"。同一个故障此前在 M45 反射星云上出现过(faint 蓝被压成
    8% 灰),当时的处理是"反射星云整个跳过"——其实是判据本身错了,亮度门分不出"暗背景"和"暗的真信号"。
    对照用户手动处理的 M64(M:/deepsky_output/D3 Messier/260307_D3_M64/Image08.jpg):他是**均匀降到
    压制前的约 30%**(各半径带实测 0.31/0.27/0.31),不是按亮度铲 —— 曲线平滑、没有断层。
    本函数按实测反解:M64 背景彩噪 0.1452 → floor 0.28(与实测最优档吻合);
    背景本来就干净的图反解出高 floor = 几乎不动。见 [[pi-chroma-suppression-cliff]]。"""
    try:
        c = float(bg_chroma_level(img_path).get("chroma", 0.0))
    except Exception:
        return float(lo)
    if c <= 1e-6:
        return float(hi)
    return round(min(float(hi), max(float(lo), float(target) / c)), 3)


def suppress_bg_chroma(img_path: str, out_path: str, lum_knee: float = 0.20,
                       floor: float = 0.12, softness: float = 0.10,
                       preview_path: str | None = None) -> str:
    """【暗部去色度(用户 2026-09-04,星场干净背景)】全局饱和会把背景微色噪染成褐/花斑块。对**暗像素**
    把色度(色−亮度)压到 floor 比例 → 背景回近中性灰;**亮像素(星点)不动**保住星色。平滑过渡:亮度
    v<lum_knee-softness 压到 floor、v>lum_knee+softness 全保、中间 smoothstep。分步拉伸保留了更多真实色
    (星点更鲜艳),背景那点被饱和放大的色噪用这步清掉——兼得富星色 + 干净背景(对齐 Dwarf stacked)。保 xisf 头。"""
    import numpy as np
    from xisf import XISF
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    lum = img.mean(-1, keepdims=True)                       # 等权亮度(近似)
    v = lum[..., 0]
    lo = lum_knee - softness
    w = np.clip((v - lo) / max(1e-4, 2.0 * softness), 0.0, 1.0)
    w = floor + (1.0 - floor) * (w * w * (3.0 - 2.0 * w))    # smoothstep,底 floor
    # 【护暗星点(用户 2026-09-13 M63)】亮度门只护得住**亮**星点:低于 lum_knee 的暗星会连同背景一起去色
    #   (M63 实测成片 s_star 0.229→0.204,跌出 0.22 甜区)。补一道高通门:**局部尖峰(星点)一律保色**,
    #   与背景的大尺度色斑尺度不重叠,不影响去彩噪效果。
    try:
        from scipy.ndimage import gaussian_filter as _gfz
        _hp = v - _gfz(v.astype(np.float32), 3.0)
        w = np.maximum(w, np.clip(_hp / 0.02, 0.0, 1.0))
        # 【护住低面亮度星系盘(用户 2026-09-14 M65/M66「盘偏灰」)】上面的高通门只护得住**局部尖峰**
        #   (星点);低面亮度的**星系盘是平滑的**,3px 高通量不到它 → 整个盘落在亮度过渡带里被一起去色:
        #   实测 lum_knee 0.151 + softness 0.10 的过渡带覆盖 v=0.051~0.251,而星系盘 v=0.176,
        #   只保住 83% 色度(盘带饱和 0.100→0.087、本体中位 0.115→0.091)。这是
        #   [[pi-chroma-suppression-cliff]] 的残余:**亮度门天生分不开「暗背景」和「暗天体」**。
        #   → 补一道**空间相干性**门(与 calm_bg_mottle 同一手法):大尺度(σ=60)平滑后显著高于背景的
        #   连片区域=真天体,一律保色。背景色斑在该尺度上被抹平不会误判;大天体填满画面时中位数落在
        #   天体内部 → _obj≈0 → 退化为原行为,安全。
        #   【门槛必须定高(2026-09-14 实测,第一版 1.5→4.5 bs 太松、把「外围云系发紫」带回来了)】
        #   1.5→4.5 bs 会把**噪声主导的暗弱弥散区**也一起保住:实测那些团 R/G 1.21、B/G **1.40**
        #   (强烈品红,正是 [[pi-dark-pixel-selection-bias]] 里 B 通道噪声更大的老毛病),而用户手动版
        #   同位置是 1.03/1.01 基本中性。显著度分得很开:**星系盘 20.6 / 27.6 bs**,发紫的暗弱团只有
        #   6.2 / 9.1 / 10.1 bs。→ 取 8→18 bs:星系盘仍满保护(1.00),紫团落到 0.00/0.11/0.21,
        #   星系外晕(5.8~6.6 bs)也回到原来的亮度门行为 —— 那里的色度本就是噪声,不该保。
        _smb = _gfz(v.astype(np.float32), 60.0)
        _b0 = float(np.median(_smb))
        _bs = float(np.median(np.abs(_smb - _b0)) * 1.4826)
        if _bs > 1e-6:
            _obj = np.clip((_smb - (_b0 + 8.0 * _bs)) / (10.0 * _bs), 0.0, 1.0)
            w = np.maximum(w, _obj.astype(np.float32))
    except Exception:
        pass
    out = lum + (img - lum) * w[..., None]                   # 暗:色度→floor;亮:全保
    out = np.clip(out, 0, 1).astype(np.float32)
    im_m, fm_m = _read_meta(xn)
    XISF.write(out_path, out, image_metadata=im_m, xisf_metadata=fm_m)
    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def bg_mottle_level(img_path: str) -> float:
    """浅数据背景「暗云」起伏量:排除亮星/星云后,暗背景 中尺度(≈0.006W~0.04W px)亮度 std。
    深数据干净背景 ≲0.010;15s 浅数据密集星场+真实尘埃 ≳0.02(暗云被拉伸揭示)。用于门控 calm_bg_mottle。"""
    import numpy as np
    from scipy.ndimage import uniform_filter
    _pl = str(img_path).lower()
    if _pl.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        from PIL import Image
        img = np.asarray(Image.open(img_path).convert("RGB")).astype(np.float32) / 255.0
    else:
        from xisf import XISF
        img = _norm01(XISF(img_path).read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    lum = img.mean(-1); W = img.shape[1]
    s1 = max(8, int(0.006 * W)); s2 = max(48, int(0.04 * W))
    band = uniform_filter(lum, s1) - uniform_filter(lum, s2)
    m = lum < 0.22                                          # 仅暗背景(排除亮星云/亮星)
    return float(band[m].std()) if bool(m.any()) else 0.0


def pin_bg_level(img_path: str, out_path: str, target: float = 0.085,
                 frac: float = 0.08, preview_path: str | None = None) -> str:
    """**用曲线(MTF)把背景电平压到 target,而不是减一个常数偏移。**

    【为什么(用户 2026-09-14 M63「背景过度拉伸把传感器固有的网格纹路凸显出来」)】原来走 bgneutral 的
    `target` 参数,那是**逐通道减常数**:背景结构的**绝对幅度一点没变**,分母却被砍掉一半 → 相对可见度
    必然翻倍。M63 实测 r13_recomb 背景 0.1665、中尺度结构绝对幅度 0.01288(相对 7.73%),减完偏移
    背景 0.0873、绝对幅度还是 0.01288 → **相对 14.75%**;背景里本来就有的传感器读出条纹(轴向功率是
    各向同性期望的 4~5 倍)就这样被翻倍放大出来。

    MTF 曲线在背景处的斜率 <1,把结构跟着一起压。同一张图实测对照(目标=用户手动的 Image29):
                        背景    中尺度绝对  相对    核心   盘(80-200px)
      现行 减偏移        0.0873   0.01288  14.75%  0.494  0.122
      **MTF 曲线**      0.0874   0.00805   9.22%  0.393  0.108
      纯等比缩放         0.0874   0.00676   7.73%  0.301  0.106
      用户手动 Image29   0.0863   0.00402   4.66%  0.369  0.102   <- 目标
    MTF 档三个指标同时最接近手动基准(纯等比把核心压太暗)。

    背景电平的测法与 job-runner 的 applyBgNeutral 一致:取四角 frac 见方的区块,按各通道中位排序后
    取**较暗的两个**的均值(避开某角含星云/星系的偏高值)。色偏中和仍由 bgneutral 负责(那是加性天光,
    减常数才对);本函数只管**电平**。见 [[pi-background-pin-curve]]。"""
    import numpy as np
    from xisf import XISF
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1).astype(np.float32)
    H, W = img.shape[:2]
    fh, fw = max(1, int(H * frac)), max(1, int(W * frac))
    lum = img.mean(-1)
    corners = [lum[:fh, :fw], lum[:fh, -fw:], lum[-fh:, :fw], lum[-fh:, -fw:]]
    vals = sorted(float(np.median(c)) for c in corners)
    B = float(np.mean(vals[:2])) if len(vals) >= 2 else (vals[0] if vals else 0.0)
    T = float(target)
    if not (0.0 < T < B < 1.0):
        # 背景已经不比 target 亮(或测不出)→ 不动,交给调用方保留原图
        XISF.write(out_path, img, *_read_meta(xn))
        if preview_path:
            _save_preview(img, preview_path)
        return out_path

    def _mtf(x, m):
        return np.where(x <= 0, 0.0, np.where(x >= 1, 1.0, ((m - 1) * x) / ((2 * m - 1) * x - m)))

    lo, hi = 0.5, 0.9999                                  # m>0.5 = 压暗
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if float(_mtf(np.array([B], dtype=np.float64), mid)[0]) > T:
            lo = mid
        else:
            hi = mid
    m = 0.5 * (lo + hi)
    # 【曲线只作用在**亮度**上、三通道按同一倍率缩放 → 严格保色比(2026-09-14)】
    #   逐通道套 MTF 会改变通道比:这条曲线为了把背景压下去、又要回到 (1,1),**高光段斜率必然 >1**,
    #   于是把亮区的通道差一起展开 —— 实测 M66 核心 R/G 被这一步从 1.189 推到 **1.308**(+10%),
    #   是「核心发粉」的第二个来源。本函数只该管**电平**,颜色交给 bgneutral/色比还原。
    #   注意这不是文档里试过的「纯等比缩放」(那是全图乘同一个常数、把核心压太暗 0.301);
    #   这里每个像素的倍率仍来自 MTF,亮度分布与逐通道版几乎一致,只是不再改色比。
    l2 = _mtf(lum.astype(np.float64), m)
    kk = np.where(lum > 1e-6, l2 / np.maximum(lum.astype(np.float64), 1e-6), 1.0)
    out = np.clip(img.astype(np.float64) * kk[..., None], 0, 1).astype(np.float32)
    XISF.write(out_path, out, *_read_meta(xn))
    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def calm_bg_mottle(img_path: str, out_path: str, strength: float = 0.6,
                   cloud_hi: float = 0.22, neb_lo: float = 0.34, sigma_frac: float = 0.08,
                   preview_path: str | None = None) -> str:
    """【浅数据·背景克制(用户 2026-09-10 M52「拉出来的暗云是伪细节」)】浅数据(15s)低银纬密集星场,
    真实尘埃+暗弱恒星被拉伸揭示成「暗云」斑驳,肉眼判伪细节。它不是噪声(每像素 σ≈0.003)、不是颜色、不是
    reveal——是拉伸把 faint 背景的**局部对比**放大出来的(证伪:降噪 -0%、reveal=off 无变化、去色 无变化)。
    做法(=reveal 的逆):把亮度对「云尺度局部背景(σ=sigma_frac·W)」的偏差压到 strength 比例(0.6=-40%,
    用户选)→ 暗云隐退、背景干净。**蒙版关键(用户 2026-09-10 M52 二次:旧 knee/幂律蒙版在 0.20 处淡出,
    恰好把暗云(亮度 0.12-0.22)一起护住 → 只 -5% 无效)**:改 smoothstep,**贯穿暗云亮度(<cloud_hi)全压、
    只在亮星云(>neb_lo)淡出** → 暗云真被压(实测 -21%),气泡/亮星(>neb_lo,被门排除)一根不动。
    保色(增益等比乘 RGB)。深数据/干净背景 band 小、改动自然小。见 [[pi-gradient-findings]]。保 xisf 头。"""
    import numpy as np
    from xisf import XISF
    from scipy.ndimage import gaussian_filter
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    lum = img.mean(-1); W = img.shape[1]
    sig = max(24.0, float(sigma_frac) * W)
    t = np.clip((neb_lo - lum) / max(1e-4, neb_lo - cloud_hi), 0, 1)   # 1 贯穿暗云(<cloud_hi)、0 护亮星云(>neb_lo)
    w = (t * t * (3.0 - 2.0 * t)).astype(np.float32)                   # smoothstep 软过渡(护主体)
    w = gaussian_filter(w, 3.0)
    # 【护星点(用户 2026-09-13 M63:安全网测出这步在压星点)】亮度门 t 对星点是 0(不压),但紧接着的
    #   `gaussian_filter(w, 3.0)` **把这份保护糊掉了**:小星点只有 2~3px,3px 模糊会把周围 w=1 的背景卷进来
    #   → 星点被当成"局部对比"一起压暗(实测 nebula_preserved 核心比 strength=0.6 时 0.772、0.45 时 0.687,
    #   而它的日志一直写着"恒星和星云本体不动")。→ 在**模糊之后**再乘一道高通星点保护,保护本身不被糊掉。
    #   星点是 2~5px 的局部尖峰,暗云是 100~800px 的大尺度起伏,两者尺度不重叠,压暗云的效果不受影响。
    _hp = lum - gaussian_filter(lum.astype(np.float32), 3.0)
    w = (w * (1.0 - np.clip(_hp / 0.02, 0.0, 1.0))).astype(np.float32)
    # 【护天体本体的外晕(用户 2026-09-14 M63「星系外围的暗云就不见了」)】亮度门(cloud_hi 0.22)对
    #   **低面亮度的星系外晕**是拦不住的:M63 外晕亮度才 0.13 左右,全在门里 → 被当背景斑块一起压掉
    #   (实测 r=40-80px 的外晕超出量 +0.0795 → +0.0455,掉了 43%,而用户手动基准是 +0.0693)。
    #   判据不能用亮度,要用**空间相干性**:天体外晕是一片连贯的、显著高出背景的隆起;背景斑块是随机起伏。
    #   重模糊(sigma=60)把随机噪声压掉约一个量级后按稳健 sigma 判显著性 → 只保护真正隆起的区域。
    #   压制的是"局部对比"(纹理)不是电平,且保护是宽羽化的渐变,不会像硬蒙版那样在边界留环。
    _sm = gaussian_filter(lum.astype(np.float32), 60.0)
    _b0 = float(np.median(_sm)); _bs = float(np.median(np.abs(_sm - _b0)) * 1.4826)
    if _bs > 1e-6:
        _obj = np.clip((_sm - (_b0 + 1.5 * _bs)) / (3.0 * _bs), 0.0, 1.0).astype(np.float32)
        w = (w * (1.0 - _obj)).astype(np.float32)
    low = gaussian_filter(lum.astype(np.float32), sig)                 # 云尺度局部背景
    newl = low + (lum - low) * float(strength)                         # 压局部对比(暗云隐退)
    fac = np.where(lum > 1e-4, np.clip(newl, 0, None) / np.maximum(lum, 1e-4), 1.0)
    fac = 1.0 * (1.0 - w) + fac * w
    out = np.clip(img * fac[..., None], 0, 1).astype(np.float32)
    im_m, fm_m = _read_meta(xn)
    XISF.write(out_path, out, image_metadata=im_m, xisf_metadata=fm_m)
    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def clean_starfield_bg(img_path: str, out_path: str, star_lo: float = 0.11,
                       star_hi: float = 0.24, bg_chroma: float = 0.0,
                       bg_blur: float = 2.0, star_sat: float = 1.0,
                       preview_path: str | None = None) -> str:
    """【星场背景净化(用户 2026-09-04)】平坦星场成片的残余噪声**几乎全是假彩噪**(chroma speckle)——
    背景本就该中性无色。做法:挂**星点亮度蒙版**(亮=星点保护、暗=背景净化,smoothstep 软过渡),对**背景**
    ①饱和度压到 bg_chroma(0=纯灰,去彩噪)②高斯模糊 bg_blur(去亮度噪);**星点保持原样锐利有色**。
    模糊用 **masked blur**(gaussian(lum·mask)/gaussian(mask))**排除星点**→ 不把亮星晕开成光斑。
    **仅背景干净的星场用**(有色星云/带尘背景是真信号,绝不可用;由 run_rgb 的 _starfield 判据门控)。保 xisf 头。"""
    import numpy as np
    from xisf import XISF
    from scipy.ndimage import gaussian_filter
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    lum = img.mean(-1)
    w = np.clip((lum - star_lo) / max(1e-4, star_hi - star_lo), 0.0, 1.0)
    m = w * w * (3.0 - 2.0 * w)                              # 1=星点, 0=背景(2D)
    mask_bg = 1.0 - m
    if bg_blur and bg_blur > 0:                              # 星点排除的平滑背景亮度(防星点晕开)
        num = gaussian_filter((lum * mask_bg).astype(np.float32), bg_blur)
        den = gaussian_filter(mask_bg.astype(np.float32), bg_blur)
        bg_lum = num / np.maximum(den, 1e-4)
    else:
        bg_lum = lum
    graybg = np.repeat(bg_lum[..., None], 3, axis=2)          # 背景=平滑灰
    bg = graybg + (img - lum[..., None]) * float(bg_chroma)   # + 可选残留 chroma(0→纯灰)
    m3 = m[..., None]
    # 星区提饱和(用户 2026-09-04:背景既已蒙版保护,星色可放开):只在星点蒙版内把色度(色−亮度)放大
    #   (1+star_sat)倍 → 亮/暗星一起更鲜活,背景纯灰不受影响(不像全局 neb_sat 会连累背景又跟净化打架)。
    lum3 = lum[..., None]
    star_col = np.clip(lum3 + (img - lum3) * (1.0 + float(star_sat)), 0, 1) if star_sat else img
    out = np.clip(m3 * star_col + (1.0 - m3) * bg, 0, 1).astype(np.float32)
    im_m, fm_m = _read_meta(xn)
    XISF.write(out_path, out, image_metadata=im_m, xisf_metadata=fm_m)
    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def neutralize_background(img_path: str, out_path: str, v_bg: float = 0.22,
                          preview_path: str | None = None) -> str:
    """按评分补救·背景中和:把暗背景各通道均值对齐到最低通道(减去 per-channel 偏移)→ 去残留色铸。
    偏移是**加性天光**,全局减最正确;量很小(暗背景),不伤主体色。保 xisf 头。

    【为什么这里保留"按 max 通道选暗像素"(2026-09-13 实测过,别再改)】这个选择器对噪声有偏——挑暗像素会把
    噪声大的通道多往下拉(详见 neutralize_bg_offset 的教训:线性图上 B 的 sigma 是 G 的 1.8 倍,害得外围云气发紫)。
    但**本函数只作用在拉伸后的成片上**,那里三通道噪声已基本相等(M63 成片实测 R .01264 / G .01228 / B .01249),
    两种估计给出的偏移几乎一致(实测 ring 色度 +0.51%/−0.36% vs 天光众数 +0.38%/+0.09%)→ 无需改动。"""
    import numpy as np
    from xisf import XISF
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    V = img.max(-1)
    bg = V < v_bg
    if int(bg.sum()) < 200:
        bg = V < np.percentile(V, 20)
    means = np.array([float(img[..., c][bg].mean()) for c in range(3)])
    off = (means - means.min()).reshape(1, 1, 3)
    out = np.clip(img - off, 0, 1).astype(np.float32)
    im_m, fm_m = _read_meta(xn)
    XISF.write(out_path, out, image_metadata=im_m, xisf_metadata=fm_m)
    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def boost_star_saturation(img_path: str, out_path: str, amount: float = 1.5,
                          preview_path: str | None = None) -> str:
    """按评分补救·提星饱和:星蒙版内把 (色度=色-亮度) 放大 amount 倍 → 星点更有色;不动星云/背景。
    实测 M23 星蒙版 s_star 0.32→0.52。保 xisf 头。"""
    import numpy as np
    from xisf import XISF
    from . import quality
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1)
    _S, V = quality._hsv_sv(img)
    sm = quality._star_mask_auto(V)
    luma = img.mean(-1, keepdims=True)
    boosted = np.clip(luma + float(amount) * (img - luma), 0, 1)
    out = np.where(sm[..., None], boosted, img).astype(np.float32)
    im_m, fm_m = _read_meta(xn)
    XISF.write(out_path, out, image_metadata=im_m, xisf_metadata=fm_m)
    if preview_path:
        _save_preview(out, preview_path)
    return out_path


def disc_signal_color(img, blur: float = 4.0):
    """星系盘的**信号**色比 (R/G, B/G, S) —— 扣掉各自背景、先平滑再量。测不到返回 None。

    【口径是三次踩坑换来的,不能省(2026-09-15)】
      · **必须扣背景**:两张图的背景电平可能差 100 倍,低信号处量到的是背景色偏不是信号颜色
        (M63 最外环非线性 R/G=1.126 其实是背景红偏,被当锚点后整体凭空加了 11% 的 R)。
      · **必须先平滑**:S=(V−min)/V 在低信噪区被噪声灌满,同一张 M63 逐像素量到 0.133、
        平滑后 0.240,噪声水平不同的两图完全不可比。见 [[pi-noise-artifact-in-color-measurement]]。
      · 盘 = 本体内亮度 30~65 分位那一圈(避开过曝核心与外围噪声)。

    这是「家族审美」的度量基准。**旧口径量出的 R/G 1.18 / B/G 0.87 已作废**(取样一半落在星场,
    见下)。新口径实测用户手工库:M51 [1.01, 1.16] / M63 [1.20, 1.02] / M64 [1.23, 0.99] /
    M65_M66 [1.12, 0.97] / M31 [1.31, 0.87],中位 **[1.20, 0.99]**。
    注意 B/G 从 0.87(M31 尘埃暖调)到 1.16(M51 蓝旋臂)是**真实的类型差异**,
    不是噪声 —— 单一全局目标服务不了两端。见 [[pi-house-style-vector]]。"""
    import numpy as np
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:
        return None
    # 入参可以是数组,也可以是 xisf 路径
    try:
        if isinstance(img, str):
            from xisf import XISF as _X
            rgb = _norm01(_X(img).read_image(0))
        else:
            rgb = np.asarray(img)
        if rgb.ndim == 2:
            rgb = np.stack([rgb] * 3, -1)
        rgb = np.clip(rgb[..., :3], 0, 1).astype(np.float32)
    except Exception:
        return None
    try:
        L = rgb.mean(-1)
        H, W = L.shape
        sm = gaussian_filter(L, max(6.0, min(H, W) / 170.0))
        # 背景电平统一走 _bg_stat(直方图众数,别用中位数 —— 原因见那个函数的注释)。
        #   M31 的 12 张同视场参考在旧口径下 10 张量不出来,修完 12/12 都能量,
        #   中位 [1.335, 0.917] ↔ 用户手调 M31 真盘 [1.316, 0.873],对上了。
        b, sg = _bg_stat(sm)
        bgm = sm <= b + 1.0 * sg
        if int(bgm.sum()) < 200:
            return None
        BG = np.median(rgb[bgm].reshape(-1, 3), 0)
        # 【★取样集合修正(用户 2026-09-15 M51「调色完全没生效」)】旧口径 = 全图亮度分位:
        #   `body = sm > b+12σ` 会把**星点**一并算进来,再在 body 里取 30~65 亮度分位当"盘"。
        #   小天体大视场下这就完全跑偏 —— M51 实测:取样 **53% 落在 r≥400px(纯星场)、
        #   落在星系核心 r<50px 的占 0%**。量出来的根本不是星系的颜色。
        #   后果不是"数偏一点",而是**整条闭环朝错误方向收敛**:用户手工库被它读成 B/G 0.87,
        #   真盘其实是 0.99(M51 更是 1.16)→ 家族目标把蓝压低了 12~25% → 成片永远发灰。
        #   这是同类错误第五次(见 [[pi-mtf-crushes-highlight-chroma]] 的"简并指标"、
        #   [[pi-lumprobe-anchor-trap]]、[[pi-noise-artifact-in-color-measurement]])。
        # 新口径:**先定位本体、再按本体自身尺度取盘环**,与视场大小/天体大小都无关 ——
        #   ① 大 σ 平滑压掉星点后取峰 = 本体中心;
        #   ② 方位平均的径向廓线落到峰值 10% 处 = 本体半径 r_obj(自适应,M51 得 112px、M31 得 428px);
        #   ③ 盘环 = 0.15~0.70 r_obj:避开过曝核,也避开外围噪声。
        _k = max(1.0, min(H, W) / 2051.0)
        _big = gaussian_filter(L, 12.0 * _k)
        _cy, _cx = np.unravel_index(int(np.argmax(_big)), _big.shape)
        _yy, _xx = np.mgrid[0:H, 0:W]
        _rr = np.hypot(_yy - _cy, _xx - _cx)
        _rmax = int(min(H, W) / 2)
        _stp = max(2, int(4 * _k))
        _rad = np.arange(0, _rmax, _stp)
        _prof = np.array([np.median(_big[(_rr >= a) & (_rr < a + _stp)]) - b for a in _rad])
        _pk = float(_prof[0]) if _prof[0] > 0 else float(_prof.max())
        if _pk <= 0:
            return None
        _idx = np.nonzero(_prof < 0.10 * _pk)[0]
        _robj = float(_rad[_idx[0]]) if len(_idx) else float(_rmax)
        _robj = max(20.0 * _k, min(float(_rmax), _robj))
        sc = min(H, W) / 2051.0
        bl = np.stack([gaussian_filter(rgb[..., c], max(1.0, blur * sc)) for c in range(3)], -1)
        sig = bl - BG
        disc = (_rr >= 0.15 * _robj) & (_rr < 0.70 * _robj)
        if int(disc.sum()) < 500:
            return None
        v = np.median(sig[disc], 0)
        # 信噪闸:环内信号必须显著高于背景噪声。低于它量到的是噪声/残留梯度的颜色
        #   —— 实测这种情况 R/G 能炸到 7,混进参考中位就把整个目标带跑。
        if v[1] <= max(3.0 * sg, 1e-6):
            return None
        V = sig.max(-1); mn = sig.min(-1)
        S = np.where(V > 1e-5, (V - mn) / np.maximum(V, 1e-5), 0.0)
        return float(v[0] / v[1]), float(v[2] / v[1]), float(np.median(S[disc]))
    except Exception:
        return None


# 盘色廓线的分档口径:**按信号占峰值的比例**,不按亮度分位、也不按半径。
#   · 亮度分位依赖 body 蒙版 —— 实测我们的 body 占画面 32%、用户手工版占 20%,
#     **同一个百分位落在完全不同的物理区域**,两张图的"第 30 层"根本不是一回事;
#   · 半径带对 M31 这种高倾角星系会把尘带和盘平均掉,用户肉眼看见的洋红在半径带里量不出来。
#   信号占峰值的比例是**物理锚定**的:与视场大小、蒙版、天体在画面里占多大都无关,
#   缩略图参考和全分辨率成片可以直接比。
SIG_LAYERS = ((0.50, 1.01), (0.20, 0.50), (0.08, 0.20), (0.03, 0.08), (0.01, 0.03))
SIG_LAYER_NAMES = ("核", "亮盘", "盘", "外盘", "最外")


def disc_color_profile(img, blur: float = 3.0):
    """盘色**廓线**:按 SIG_LAYERS 分档,每档返回该档的色比和曲线所需的输入坐标。

    返回 [{lo,hi,n,rg,bg,xr,xb,vg} ...](测不到的档返回 None 占位),测不出整张图返回 None。
    xr/xb = 该档 R/B 通道的**像素中位数**(含背景基座)—— 就是 CT 曲线上那个点的 x 坐标。
    """
    import numpy as np
    try:
        from scipy.ndimage import gaussian_filter
    except Exception:
        return None
    try:
        if isinstance(img, str):
            from xisf import XISF as _X
            rgb = _norm01(_X(img).read_image(0))
        else:
            rgb = np.asarray(img)
        if rgb.ndim == 2:
            rgb = np.stack([rgb] * 3, -1)
        rgb = np.clip(rgb[..., :3], 0, 1).astype(np.float32)
    except Exception:
        return None
    try:
        L = rgb.mean(-1)
        H, W = L.shape
        k = max(1.0, min(H, W) / 2051.0)
        sm = gaussian_filter(L, max(6.0, min(H, W) / 170.0))
        b, sg = _bg_stat(sm)
        bgm = sm <= b + 1.0 * sg
        if int(bgm.sum()) < 200:
            return None
        BG = np.median(rgb[bgm].reshape(-1, 3), 0).astype(np.float64)
        s = sm - b
        pk = float(np.percentile(s, 99.99))
        if pk <= max(3.0 * sg, 1e-6):
            return None
        bl = np.stack([gaussian_filter(rgb[..., c], max(1.0, blur * k)) for c in range(3)], -1)
        out = []
        for lo, hi in SIG_LAYERS:
            sel = (s >= lo * pk) & (s < hi * pk)
            n = int(sel.sum())
            if n < 500:
                out.append(None)
                continue
            px = np.median(bl[sel].reshape(-1, 3), 0).astype(np.float64)   # 含基座的像素中位
            v = px - BG                                                    # 该档的**信号**
            if v[1] <= max(2.0 * sg, 1e-6):        # G 信号弱于噪声 → 这一档的色比不可信
                out.append(None)
                continue
            out.append({"lo": lo, "hi": hi, "n": n,
                        "rg": float(v[0] / v[1]), "bg": float(v[2] / v[1]),
                        "xr": float(px[0]), "xb": float(px[2]),
                        "vg": float(v[1]), "BGr": float(BG[0]), "BGb": float(BG[2])})
        return out if any(o for o in out) else None
    except Exception:
        return None


def disc_style_curve(img_path: str, target, max_dev: float = 0.25,
                     warm: float = 0.0, bias: float = 0.0, log=None):
    """把盘色**按亮度分档**推向目标廓线,返回 {"pointsR","pointsB"}(CT 曲线)或 None。

    【为什么不能再用全局增益(用户 2026-09-16 M31「盘面紫红」)】旧的 nudge_disc_color 是
    **一个全局增益、瞄一个标量目标、在一个测量带里量**。但盘的 B/G 本来就随亮度变
    (M31 实测 核 0.771 / 亮盘 0.780 / 盘 0.834 / 外盘 0.813),要让测量带够到 0.931,
    增益就得 ×1.25 —— 套到起点本来就低的亮盘上必然冲过中性:实测把亮盘从 0.780 顶到
    **1.018**,R、B 双高 = 洋红。**任何单一增益都没法把一条起伏的廓线映射到一个标量目标
    而不在某处过冲**,调参数只是在挑"让哪一层过冲"。
    → 改成和 chroma_restore_curve 同一套机制:每档各自对齐自己的目标,过冲从构造上消失。

    target:[(R/G, B/G), ...] 与 SIG_LAYERS 一一对应(None 占位=该档不动)。
    warm/bias:在目标之上的个人偏移(tR×(1+warm)、tB×(1+bias)),与旧接口语义一致。
    """
    import numpy as np
    prof = disc_color_profile(img_path)
    if not prof or not target:
        if log:
            log("  [盘调色·分档] 跳过:量不到盘色廓线")
        return None
    rows_r, rows_b = [], []
    _lg = []
    for i, cur in enumerate(prof):
        if cur is None or i >= len(target) or not target[i]:
            continue
        tR = float(target[i][0]) * (1.0 + float(warm))
        tB = float(target[i][1]) * (1.0 + float(bias))
        vg = cur["vg"]
        outR = cur["BGr"] + vg * tR
        outB = cur["BGb"] + vg * tB
        gR = float(np.clip(outR / max(cur["xr"], 1e-9), 1.0 - max_dev, 1.0 + max_dev))
        gB = float(np.clip(outB / max(cur["xb"], 1e-9), 1.0 - max_dev, 1.0 + max_dev))
        rows_r.append((cur["xr"], cur["xr"] * gR))
        rows_b.append((cur["xb"], cur["xb"] * gB))
        _lg.append("%s %.3f/%.3f→%.3f/%.3f" % (SIG_LAYER_NAMES[i], cur["rg"], cur["bg"], tR, tB))
    if len(rows_r) < 2:
        if log:
            log("  [盘调色·分档] 跳过:有效档位不足 2")
        return None

    def _mono(pts):
        out = [[0.0, 0.0]]
        for x, y in sorted(pts):
            if x > out[-1][0] + 1e-4 and y > out[-1][1] + 1e-4:
                out.append([round(float(x), 4), round(float(np.clip(y, 0.0, 1.0)), 4)])
        if out[-1][0] < 0.999:
            out.append([1.0, 1.0])
        return out

    # 背景锚定不动:背景色比已由 chroma_restore_curve 还原过,这一步只管天体
    _b0r = float(prof[0]["BGr"]) if prof[0] else float(next(p for p in prof if p)["BGr"])
    _b0b = float(prof[0]["BGb"]) if prof[0] else float(next(p for p in prof if p)["BGb"])
    pr = _mono([(_b0r, _b0r)] + rows_r)
    pb = _mono([(_b0b, _b0b)] + rows_b)
    if len(pr) < 3 or len(pb) < 3:
        if log:
            log("  [盘调色·分档] 跳过:曲线控制点不足(档位太密或非单调)")
        return None
    if log:
        log("  [盘调色·分档] 逐档对齐(硬限 ±%d%%):%s" % (int(max_dev * 100), " | ".join(_lg)))
    return {"pointsR": pr, "pointsB": pb}


def nudge_disc_color(img_path: str, target, out_path: str, max_dev: float = 0.10,
                     core_relief: float = 0.7, preview_path: str | None = None, log=None,
                     bias: float = 0.0, warm: float = 0.0, style_target=None) -> str:
    """把**星系/星云「盘」**的 RGB 色比温和地推向 target(量化目标,来自同视场参考的 disc_balance)。
    只作用在天体本体上、且**在核心处淡出**;每通道增益硬限 ±max_dev、归一保总亮度。测不到就原样拷。

    【为什么只修盘、不修核(用户 2026-09-14 要求"把蓝色的 RGB 数值做一个量化,这样调整也有方向")】
    实测四张基准(用户手动 + 三张 AstroBin 同视场),**盘几乎是中性的**而**核是暖的**:
      盘 中位 [0.999 0.990 1.017](用户手动 [0.988 0.987 1.035])
      核 范围 [1.023~1.186 / 0.974~0.997 / 0.845~0.981]
    当时程序:盘 [1.070 1.017 0.922](红高蓝低,B-G -9.5%)、**核 [1.111 1.019 0.870] 本就在基准范围内**
    —— 要修的是盘。全局增益会把已经对的核一起带偏,所以权重按亮度在核心处淡出(core_relief)。
    模拟实测:盘 [1.070 1.013 0.919] → **[1.001 0.990 1.010]**(目标 [0.999 0.990 1.017]),
    核 [1.105 1.017 0.878] → [1.073 1.008 0.920](仍在基准范围);径向 B-G 核 -12.7% → 盘 +2.0/+1.6/+0.7%,
    平滑单调、无台阶。

    用在**去星的星云/星系层**上(星点单独走 SPCC 真彩,不受影响)。见 [[pi-galaxy-disc-color-target]]。"""
    import numpy as np
    from xisf import XISF
    from . import quality
    try:
        from scipy.ndimage import gaussian_filter, label
    except Exception:
        gaussian_filter = None
    xn = XISF(img_path)
    img = _norm01(xn.read_image(0))
    if img.ndim == 2:
        img = np.stack([img] * 3, -1)
    img = np.clip(img[..., :3], 0, 1).astype(np.float32)
    # target=None → 纯风格偏置模式(不量盘色比):**整盘平均色比是简并指标**,暖核蓝臂的真星系
    #   和一张全灰的图能量出同一个值,拿它当控制量做全局增益会把径向色温梯度一起铲平
    #   (2026-09-14 M65/M66 实测:一步把核 R/B 1.182→1.051)。校色交给 SPCC + chroma_restore_curve,
    #   这里只做用户的审美偏置。见 [[pi-mtf-crushes-highlight-chroma]]。
    cur = quality.disc_balance(img) if target else None
    if gaussian_filter is None or (target and cur is None):
        XISF.write(out_path, img, *_read_meta(xn))
        if preview_path:
            _save_preview(img, preview_path)
        if log:
            log("  [盘调色] 跳过(测不到盘色比或缺 scipy)")
        return out_path
    if target:
        cur = np.array(cur, dtype=np.float32)
        tgt = np.array(target[:3], dtype=np.float32)
        gain = tgt / np.maximum(cur, 1e-6)
    else:
        b = float(np.clip(bias, -0.20, 0.20))
        rw = float(np.clip(warm, -0.20, 0.20))
        if abs(b) < 1e-4 and abs(rw) < 1e-4 and not style_target:
            XISF.write(out_path, img, *_read_meta(xn))
            if preview_path:
                _save_preview(img, preview_path)
            if log:
                log('  [盘调色] 跳过(风格偏置为 0)')
            return out_path
        # 【朝一个盘色目标做有界推移(用户 2026-09-15 定的产品方向)】审美不是「加一个固定增益」
        #   而是「收敛到一个目标盘色」—— 固定增益模型拟合残差 ~8%,固定目标色模型 ~5-6%。
        #   **目标从哪来(用户 2026-09-15 拍板):按目标取 AstroBin 同视场参考**,拿不到才退回
        #   用户手工库中位 [1.21, 0.99]。理由是单一全局目标服务不了所有星系 —— M51(蓝旋臂)
        #   真盘 B/G 1.16,M31(尘埃暖调)只有 0.87;12 张 M51 参考实测 [1.031, 1.015],
        #   家族中位是 [1.21, 0.99],**R/G 差 0.18**。见 pipeline 里 _sty 那段。
        #   ⚠ 早先写在这里的 (R/G 1.18±0.08、B/G 0.87±0.09) 是**坏口径**量出来的,已作废。
        #   偏暖/偏蓝是在目标之上的**个人偏移**(tR=目标×(1+warm)、tB=目标×(1+bias)):
        #   参考给客观锚点,偏移给个人口味 —— M51 实测 bias=0.10 把成片 B/G 从 0.972 带到 1.040。
        #   【为什么这次不会重蹈「整盘平均色比是简并指标」的覆辙】径向结构由 chroma_restore_curve
        #   负责(它按亮度分档还原 SPCC 的径向色温梯度);本步只是在其上叠一个**全局**增益,
        #   全局增益保持各区之间的比值、不会把暖核蓝臂压平。且增益有硬限,天生不同的星系
        #   (椭圆/正面向)不会被强行拉到同一个色。
        _st = style_target if (style_target and len(style_target) >= 2) else None
        if _st is not None:
            cur3 = disc_signal_color(img)
            if cur3 is None:
                XISF.write(out_path, img, *_read_meta(xn))
                if preview_path:
                    _save_preview(img, preview_path)
                if log:
                    log('  [盘调色] 跳过(量不到盘区信号色比)')
                return out_path
            tR = float(_st[0]) * (1.0 + rw); tB = float(_st[1]) * (1.0 + b)
            gain = np.array([tR / max(cur3[0], 1e-6), 1.0, tB / max(cur3[1], 1e-6)], dtype=np.float32)
            if log:
                log('  [盘调色] 家族盘色 实测 [R/G %.3f, B/G %.3f] → 目标 [%.3f, %.3f]'
                    % (cur3[0], cur3[1], tR, tB))
        else:
            gain = np.array([1.0 + rw, 1.0, 1.0 + b], dtype=np.float32)
    gain = gain / gain.mean()
    gain = np.clip(gain, 1.0 - max_dev, 1.0 + max_dev)
    gain = gain / gain.mean()
    L = img.mean(-1)
    H, W = L.shape
    sm = gaussian_filter(L, max(4.0, min(H, W) / 170.0))
    b, sg = _bg_stat(sm)
    body = sm > b + 12.0 * sg
    if int(body.sum()) < 2000 or sg <= 1e-9:
        XISF.write(out_path, img, *_read_meta(xn))
        if preview_path:
            _save_preview(img, preview_path)
        if log:
            log("  [盘调色] 跳过(找不到天体本体)")
        return out_path
    # 【权重必须在「盘」就爬满】旧写法 b+8σ→b+16σ 让**最亮的核拿满权重、盘反而拿不到**,
    #   与「只修盘不修核」正好相反(2026-09-14 M65/M66 实测:核有效权重 0.93、中盘只有 0.48,
    #   于是核的 R/B 被改动 -5.1% 而盘只有 -2.8%)。星系盘位于 b+14σ~b+34σ,故 b+3σ→b+8σ 爬满。
    w = np.clip((sm - (b + 3.0 * sg)) / (5.0 * sg), 0.0, 1.0)          # 本体权重(盘处=1)
    # 【暗盘/尘带也要淡出(用户 2026-09-16 M31「盘面紫红、核心黄绿」)】
    #   这一步是**全局增益**,但各亮度层的起点差很多。M31 实测:增益按测量带(中亮盘)
    #   算出来要 B×1.22,套到**暗盘**上就把它从 B/G 0.842 顶到 **1.083** —— 越过 1 就是
    #   R、B 双高 = 洋红,正是用户看到的紫红盘面。逐层实测(rG_chromarestore → r11f_disccolor):
    #     暗盘 [1.124, 0.842] → [1.280, **1.083**];核心 [1.022, 0.750] → [1.111, 0.884]
    #   低信号处的色比本来就最不可信(噪声/残留梯度占比大),**按测量带算出的增益不该原样
    #   套到它身上**。→ 和核心淡出对称,在暗端也加一道淡出:按**本体亮度分位**定
    #   (p20 起淡入、p45 爬满),直接对准"暗盘那一层",不依赖 σ 的绝对尺度。
    _bq20, _bq45 = (float(v) for v in np.percentile(sm[body], [20, 45]))
    if _bq45 > _bq20 + 1e-9:
        w = w * np.clip((sm - _bq20) / (_bq45 - _bq20), 0.0, 1.0)
    # 核心起点按**天体自身峰值**定,不用「本体内亮度分位」:小而亮的星系 p85 已经在核上,
    #   那样算出的 corew 在核心只有 0.33 = 几乎没保护。
    _top = float(np.percentile(L[body], 99.5))
    thr = b + 0.35 * (_top - b)                                        # 核心起点
    corew = np.clip((L - thr) / max(0.04, _top - thr), 0.0, 1.0)       # 核心淡出
    wt = gaussian_filter((w * (1.0 - float(core_relief) * corew)).astype(np.float32), 6.0)
    # 【增益只施加在**信号**上,不动背景基座(用户 2026-09-15「要把色彩调到我手调的水平」)】
    #   本体里的像素 = 背景基座 + 信号。乘性增益 g·(bg+sig) 会把基座一起抬 → 星系周围出现一圈
    #   淡蓝晕;而且信号拿到的实际增益被基座稀释(bg 0.088 / sig 0.10 时,g=1.15 只等效 1.07)。
    #   改成 bg + g·sig:背景严格不动,信号拿到的就是标称增益。用户手工成片的背景实测也是中性的
    #   (9 张星系片 R/G=1.000、B/G 0.96~1.07),所以背景不该被风格偏置碰。
    _bgc = np.median(img[sm < b + 1.0 * sg].reshape(-1, 3), 0).astype(np.float32) if int((sm < b + 1.0 * sg).sum()) > 5000 else np.zeros(3, np.float32)
    _sig = img - _bgc[None, None, :]
    out = _bgc[None, None, :] + _sig * (1.0 + (gain[None, None, :] - 1.0) * wt[..., None])
    out = np.clip(out, 0, 1).astype(np.float32)
    XISF.write(out_path, out, *_read_meta(xn))
    if preview_path:
        _save_preview(out, preview_path)
    if log:
        if target:
            log(f"  [盘调色] 盘色比 {[round(float(x),3) for x in cur]} → 目标 {list(target[:3])};"
                f"增益 {[round(float(x),3) for x in gain]}(硬限 ±{int(max_dev*100)}%,核心处淡出)")
        else:
            log(f"  [盘调色] 风格向量 偏蓝{bias:+.3f} 偏暖{warm:+.3f} → 增益 "
                f"{[round(float(x),3) for x in gain]}(硬限 ±{int(max_dev*100)}%,核心处淡出;"
                f"绝对校色交给 SPCC + 色比还原,这里只做审美)")
    return out_path


def chroma_restore_curve(linear_path: str, nonlinear_path: str, max_dev: float = 0.15,
                         log=None):
    """把**SPCC 校准过的线性色比**按亮度分档还原到拉伸后的图上,返回 {"pointsR":…, "pointsB":…}。

    【为什么需要】MTF 拉伸对三通道用**同一条**曲线,而这条曲线**高光段平、暗部段陡**:
    亮处通道差被压掉、暗处通道差被放大。实测 M65/M66(环带中位数):
      半径 0-12px(核) 线性 R/B 1.296 → 拉伸后 1.109(暖核被压平)
      半径 25-40px(盘) 线性 R/B 1.124 → 拉伸后 1.166(中盘反被抬暖)
    线性阶段单调下降的暖核梯度,被改造成"中盘隆起的驼峰"。此时若再用**整盘平均色比**当控制量
    去做全局增益,会把仅剩的核心一起铲平 —— 整盘平均是**简并指标**。
    见 [[pi-mtf-crushes-highlight-chroma]]。

    【必须先减背景再比色比(用户 2026-09-14 M63「星系太紫了」)】两张图的**背景完全不同**:
    线性图背景 ≈0.0014,非线性图背景 ≈0.14 且此刻**还带着色偏**(bgneutral 在更下游)。
    直接比原始通道比,低信号处量到的根本不是信号的颜色、是背景的色偏 —— M63 实测最外环
    非线性 R/G=**1.126**(那是背景红偏),被当成锚点后所有档位的增益都被除以它 = **整体加了 11% 的 R**,
    把星系盘推成品红(B 也被抬到 ×1.15)。改成**只比「信号 = 中位 − 背景」的色比**之后,
    同一张图的增益全部落回 ±4%,且方向正确(核心压 B 恢复暖色、外围几乎不动)。

    【做法】线性图是 SPCC/BN-CC 校准过的**真值**(用户:「星系的校色主要还是依靠 bn-cc 或 spcc,
    在此基础上再通过 CT 曲线微调」)——本函数正是那条 CT 曲线,不引入任何外部色彩目标。
    对每个环带,令输出的**信号**色比等于线性图的信号色比、G 通道不动:
        out_c = BG_nl[c] + sig_nl[G] · (sig_lin[c] / sig_lin[G])
    曲线天然过 (BG_nl[c], BG_nl[c]),背景不动;逐点硬限 ±max_dev。
    信号弱于 3σ 的环带直接丢弃(那里量到的是噪声)。

    用在**去星层**上(星点自己走 SPCC 真彩)。测不到天体/无需修正 → 返回 None。"""
    import numpy as np
    from xisf import XISF
    try:
        from scipy.ndimage import gaussian_filter, label
    except Exception:
        return None

    def _load(p):
        a = _norm01(XISF(p).read_image(0))
        if a.ndim == 2:
            a = np.stack([a] * 3, -1)
        return np.clip(a[..., :3], 0, 1).astype(np.float32)

    try:
        lin = _load(linear_path)
        nl = _load(nonlinear_path)
    except Exception:
        return None
    if lin.shape[:2] != nl.shape[:2]:
        if log:
            log("  [色比还原] 跳过:线性图与拉伸图尺寸不一致(中途裁切过)")
        return None

    H, W = nl.shape[:2]
    sc = min(H, W) / 2094.0
    bl = np.stack([gaussian_filter(lin[..., c], max(1.0, 6.0 * sc)) for c in range(3)], -1)
    bn = np.stack([gaussian_filter(nl[..., c], max(1.0, 6.0 * sc)) for c in range(3)], -1)

    # 找天体中心(用拉伸图;线性图上 argmax 会被热点/星点带偏,见 [[pi-galaxy-halo-vignette-degeneracy]])
    L = bn.mean(-1)
    sm = gaussian_filter(L, max(4.0, min(H, W) / 170.0))
    b0, sg = _bg_stat(sm)
    if sg <= 1e-9:
        return None
    bgm = sm < b0 + 1.0 * sg                      # **真背景**:两张图都在同一批像素上量
    if int(bgm.sum()) < 5000:
        return None
    BGn = np.median(bn[bgm], 0).astype(np.float64)
    BGl = np.median(bl[bgm], 0).astype(np.float64)
    # 【★背景也要还原(用户 2026-09-16 M31「背景看起来偏绿」)】原来这里把背景锚成"输出=输入",
    #   于是**拉伸制造出来的背景色偏一路留到 r13b 才被中和** —— 中间的色比还原、盘调色、
    #   提饱和全都在一个带色偏的底子上做,提饱和还会把它放大。
    #   机理(实测 M31):线性背景 R/G 0.997、B/G 0.988(SPCC 已定标,基本中性),拉伸后变成
    #   0.953 / 0.847 —— **1% 变 15%**。不是 linked 失效(曲线确实是同一条,H[3] 那一行),
    #   是**黑点减法**:c0 = med + shadowClip·MAD 把背景电平的 ~85% 减掉,剩下的残量里
    #   通道差的**相对**比例被放大,MTF 在黑点附近的陡斜率再放大一次。
    #   (同 [[pi-background-pin-curve]]「减常数偏移 → 分母砍半 → 相对量翻倍」的数学。)
    #   → 背景锚点改成"线性图那个色比",只撤掉拉伸**制造**的那部分,真实天光底色照样保留。
    _bgt = np.array([BGn[1] * float(BGl[0] / max(BGl[1], 1e-12)), BGn[1],
                     BGn[1] * float(BGl[2] / max(BGl[1], 1e-12))], dtype=np.float64)
    #   背景锚点用**比信号档更宽**的硬限:信号档的 ±max_dev 是防外推跑飞,而背景这个目标是
    #   **同一批像素在已定标线性图上的直接实测**,证据强得多。M31 实测要 B×1.23 才还原得回去,
    #   卡在 ±15% 只能做到 B/G 0.92(目标 0.99)。
    _bgdev = max(float(max_dev), 0.30)
    _bgt[0] = float(np.clip(_bgt[0], BGn[0] * (1 - _bgdev), BGn[0] * (1 + _bgdev)))
    _bgt[2] = float(np.clip(_bgt[2], BGn[2] * (1 - _bgdev), BGn[2] * (1 + _bgdev)))
    lab, _ = label(sm > b0 + 12.0 * sg)
    sz = np.bincount(lab.ravel())
    if sz.size < 2:
        return None
    ks = [k for k in (np.argsort(sz[1:])[::-1] + 1) if sz[k] > int(0.0004 * L.size)][:3]
    if not ks:
        return None
    cs = []
    for k in ks:
        ys, xs = np.nonzero(lab == k)
        cs.append((int(ys.mean()), int(xs.mean())))

    yy, xx = np.ogrid[:H, :W]
    dmin = None
    for (cy, cx) in cs:
        d = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        dmin = d if dmin is None else np.minimum(dmin, d)

    bands = [(0, 12), (12, 25), (25, 40), (40, 60), (60, 85), (85, 115), (115, 150), (150, 200)]
    rows = []
    for lo, hi in bands:
        m = (dmin >= lo * sc) & (dmin < hi * sc)
        if int(m.sum()) < 400:
            continue
        vn = np.median(bn[m], 0).astype(np.float64) - BGn        # 非线性图的**信号**
        vl = np.median(bl[m], 0).astype(np.float64) - BGl        # 线性图的**信号**
        if vn[1] <= 3.0 * sg or vl[1] <= 0:                      # 信号弱于 3σ → 那里量到的是噪声
            continue
        lr = vl[0] / max(vl[1], 1e-12); lb = vl[2] / max(vl[1], 1e-12)
        inR = float(BGn[0] + vn[0]); inB = float(BGn[2] + vn[2])
        outR = float(_bgt[0] + vn[1] * lr); outB = float(_bgt[2] + vn[1] * lb)
        gR = outR / max(inR, 1e-9); gB = outB / max(inB, 1e-9)
        gR = float(np.clip(gR, 1.0 - max_dev, 1.0 + max_dev))
        gB = float(np.clip(gB, 1.0 - max_dev, 1.0 + max_dev))
        rows.append((float(vn.mean()), inR, inB, inR * gR, inB * gB,
                     float(lr / max(vn[0] / max(vn[1], 1e-12), 1e-9)),
                     float(lb / max(vn[2] / max(vn[1], 1e-12), 1e-9))))
    if len(rows) < 2:
        if log:
            log("  [色比还原] 跳过:信号足够强的环带不足(天体太暗或太小)")
        return None

    rows.sort(key=lambda t: t[0])
    thin = [rows[0]]
    for rw in rows[1:]:
        if rw[0] - thin[-1][0] >= 0.03:        # 稀疏化:太密的点会让样条在背景附近振铃
            thin.append(rw)
    peak = max(max(abs(r[3] / max(r[1], 1e-9) - 1.0), abs(r[4] / max(r[2], 1e-9) - 1.0)) for r in thin)
    if peak < 0.02:
        if log:
            log("  [色比还原] 跳过:拉伸未明显压缩色比(最大偏差 <2%)")
        return None

    def _mono(pts):
        out = [[0.0, 0.0]]
        for x, y in pts:
            if x > out[-1][0] + 1e-4 and y > out[-1][1] + 1e-4:
                out.append([round(x, 4), round(float(np.clip(y, 0.0, 1.0)), 4)])
        if out[-1][0] < 0.999:
            out.append([1.0, 1.0])
        return out

    # 背景处显式锚定:输入=当前背景,输出=**线性色比对应的背景**(见上)
    pr = _mono([[float(BGn[0]), float(_bgt[0])]] + [[r[1], r[3]] for r in thin])
    pb = _mono([[float(BGn[2]), float(_bgt[2])]] + [[r[2], r[4]] for r in thin])
    if len(pr) < 3 or len(pb) < 3:
        return None
    if log:
        log("  [色比还原] 按**信号色比**(已扣两图各自的背景)还原;"
            + "核区需要的增益 R×" + str(round(thin[-1][5], 3)) + " B×" + str(round(thin[-1][6], 3))
            + ",硬限 ±" + str(int(max_dev * 100)) + "%"
            + ";背景按线性色比还原 R×" + str(round(float(_bgt[0] / max(BGn[0], 1e-12)), 3))
            + " B×" + str(round(float(_bgt[2] / max(BGn[2], 1e-12)), 3)) + ","
            + str(len(thin)) + " 个信号档")
    return {"pointsR": pr, "pointsB": pb}


def color_nudge(neb_path: str, target_balance, out_path: str, strength: float = 0.5,
                max_dev: float = 0.15, preview_path: str | None = None, log=None,
                anchor: str = "signal") -> str:
    """**温和有界**地把星云色调往 AstroBin 参考配色(target_balance=ref_targets 的 rgb_balance)靠:
    测当前信号区色彩平衡 → 部分移向目标(strength)→ 每通道增益**硬限 ±max_dev**、归一**保总亮度**。
    **绝不推翻 SPCC 的绝对色**,只做审美色调微调;只作用于星云(星点单独走 SPCC 真彩、不受此影响)。
    保 neb 的 xisf 头。测不到当前平衡/无目标 → 原样拷。见 [[pi-astrobin-reference]] 第二步。"""
    import numpy as np
    from xisf import XISF
    from . import quality

    xn = XISF(neb_path)
    neb = _norm01(xn.read_image(0))
    if neb.ndim == 2:
        neb = np.stack([neb] * 3, -1)
    neb = np.clip(neb[..., :3], 0, 1)

    # anchor="star":用**星点**测当前平衡(星点是两张图里同一批物理天体,比拿星系自己当基准可靠);
    #   "signal":原来的"亮且有色的像素"。
    cur = quality.star_balance(neb) if anchor == "star" else quality.signal_balance(neb)
    gain_log = "跳过(测不到信号平衡)"
    if cur is not None and target_balance:
        cur = np.array(cur, dtype=np.float32)
        tgt = np.array(target_balance[:3], dtype=np.float32)
        new = (1.0 - strength) * cur + strength * tgt          # 部分移向目标(不一步到位)
        gain = new / np.maximum(cur, 1e-6)
        gain = gain / gain.mean()                               # 先归一(保总亮度)
        gain = np.clip(gain, 1.0 - max_dev, 1.0 + max_dev)      # **最后**硬限每通道 ±max_dev(保证有界,不推翻 SPCC)
        neb = np.clip(neb * gain.reshape(1, 1, 3), 0.0, 1.0)
        gain_log = f"增益 {[round(float(g), 3) for g in gain]}(当前{[round(float(c),2) for c in cur]}→目标{[round(float(t),2) for t in tgt]})"
    out = neb.astype(np.float32)

    img_meta = None
    file_meta = None
    try:
        img_meta = xn.get_images_metadata()[0]
    except Exception:
        img_meta = None
    try:
        file_meta = xn.get_file_metadata()
    except Exception:
        file_meta = None
    XISF.write(out_path, out, image_metadata=img_meta, xisf_metadata=file_meta)
    if preview_path:
        _save_preview(out, preview_path)
    if log:
        log(f"  [调色] {gain_log}")
    return out_path
