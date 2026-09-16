"""成片质量**确定性指标**(不依赖 LLM,可复现)——供管线闭环质量门 + 喂评委 + UI 展示。

背景:LLM 评分是主观的、且此前只展示不驱动改动。有些质量轴其实可以**直接量化测量**,
比它更硬、更快、不花 token。测出来超出目标带 → 管线可确定性地回退某阶段重跑(见 run_rgb 质量门)。

现有量化轴(M23 诊断得来,见记忆 pi-quality-gate):
- **S_star**:星点饱和度。星点颜色在**翼部**(核心过曝发白 S 低),故只取亮度中高、未 clip 的
  像素取 HSV-S 中位数。<0.18 发闷 / **0.22~0.40 自然有色(甜区,中心~0.25)** / >0.45 艳俗。(用户 2026-09-06 重定)
  实测甜区与本项目 NGC6888(8%→54%)一致。
- **背景中性度**:暗背景应近中性灰(R≈G≈B、S 低)。S 中位 <0.12 干净;失衡 (max-min)/mean <15%。
- **背景亮度**:疏散星团/纯亮场应把背景钉深(~0.10),抬太亮=奶雾/脏。

**实现刻意用纯 numpy**(不用 cv2):HSV 的 S=(max-min)/max、V=max 直接算即可,且 cv2 在
PyQt 子线程里(质量门在 Worker 线程调用)有 Windows 段错误风险(try/except 拦不住)——见崩溃教训。
"""
from __future__ import annotations

import numpy as np


# 目标带(可调):星点饱和度、背景中性度、背景亮度
S_STAR_LO, S_STAR_HI = 0.22, 0.40       # 星点饱和度甜区(用户 2026-09-06 重定:实测 s_star 0.25 舒服、
                                        #   0.08 太灰、0.33 偏艳 → 甜区中心 ~0.25。旧 0.30~0.55 是压饱和错假设年代的高值)
BG_S_MAX = 0.12                         # 背景中性度 S 上限(超=偏色)
BG_IMBAL_MAX = 0.15                     # 背景通道失衡上限
BG_LEVEL_MAX = 0.16                     # 背景亮度上限(星团/纯亮场;超=抬太亮)


def _to_rgb01(img) -> np.ndarray | None:
    """吃 PNG/JPG 路径 / xisf 路径 / ndarray → 归一化 RGB float(H,W,3) 0..1。纯 numpy + PIL/xisf,不用 cv2。"""
    if isinstance(img, np.ndarray):
        a = img.astype(np.float32)
    elif isinstance(img, str):
        low = img.lower()
        if low.endswith(".xisf"):
            try:
                from xisf import XISF
                a = XISF(img).read_image(0).astype(np.float32)
            except Exception:
                return None
        else:
            try:
                from PIL import Image
                a = np.asarray(Image.open(img).convert("RGB")).astype(np.float32)
            except Exception:
                return None
    else:
        return None
    if a.ndim == 2:
        a = np.stack([a] * 3, -1)
    if a.shape[-1] > 3:
        a = a[..., :3]
    mx = float(a.max()) if a.size else 1.0
    if mx > 1.5:
        a = a / (65535.0 if mx > 255 else 255.0)
    return np.clip(a, 0.0, 1.0)


def has_bright_core(img, blur: float = 6.0) -> dict:
    """检测**主导的集中亮核**(如 M42 猎户四边形/亮发射星云核、球状团核、亮星系核)。这类目标:
    ① ABE 会把亮核当背景拟合、在核周围过扣出**暗环(甜甜圈)**;② 拉伸后核心必**过曝**、需 HDR 压核。
    在**线性 colorcal 后**图上测(核未过曝、结构在)。模糊 σ6 抹掉星点(点源)、只留**延展**亮核 →
    峰值/中值比 + 峰区集中度判定。返回 {bright_core, peak_med_ratio, peak_frac,...}。用户 2026-09-09 M42。"""
    a = _to_rgb01(img)
    if a is None:
        return {"bright_core": False, "peak_med_ratio": 0.0}
    V = a.max(2)
    s = max(1, max(V.shape) // 512)
    V = V[::s, ::s]
    from scipy.ndimage import gaussian_filter
    Vb = gaussian_filter(V, blur)                          # 抹点源、留延展亮核
    med = max(float(np.median(Vb)), 1e-6)
    peak = float(Vb.max())
    ratio = peak / med                                     # 延展峰值相对背景中值(点源已被模糊抹平)
    hi = med + 0.7 * (peak - med)
    peak_frac = float((Vb > hi).mean())                    # 接近峰值的像素占比(集中的核→很小)
    bright_core = (ratio > 20.0) and (peak_frac < 0.015)
    return {"bright_core": bool(bright_core), "peak_med_ratio": round(ratio, 1),
            "peak_frac": round(peak_frac, 5), "peak": round(peak, 5), "med": round(med, 6)}


def core_blown(img, thr: float = 0.92) -> dict:
    """检测**核心过曝**:近饱和(V>thr)像素里**最大连通团**的大小——大团=过曝的星云核(而非零散星点)。
    在**拉伸后**图上测。返回 {blown, core_px, blown_frac, nblobs}。core_px 远大于星点(几百 px)即判过曝。"""
    a = _to_rgb01(img)
    if a is None:
        return {"blown": False, "core_px": 0, "blown_frac": 0.0}
    V = a.max(2)
    H, W = V.shape
    from scipy.ndimage import label
    lbl, n = label(V > thr)
    if n == 0:
        return {"blown": False, "core_px": 0, "blown_frac": 0.0, "nblobs": 0}
    core_px = int(np.bincount(lbl.ravel())[1:].max())
    blown = core_px > max(500, int(0.0003 * H * W))        # 最大近饱和团>0.03%画幅或500px=过曝核(非星点)
    return {"blown": bool(blown), "core_px": core_px, "blown_frac": round(core_px / float(H * W), 6),
            "nblobs": int(n)}


def abe_donut(before, after) -> dict:
    """检测 ABE/梯度校正在亮核周围过扣出的**暗环(甜甜圈)**:亮核外一圈背景被扣到**低于远处背景**。
    before/after=ABE 前后(线性)。找亮核中心→测 after 的径向中值剖面→环区最低点 vs 远处背景。
    返回 {donut, rel(环比远背景暗多少比例), depth,...}。rel>0.05(暗 5%+)判甜甜圈。用户 2026-09-09。"""
    a0 = _to_rgb01(before)
    a1 = _to_rgb01(after)
    if a0 is None or a1 is None:
        return {"donut": False, "rel": 0.0}
    from scipy.ndimage import gaussian_filter
    s = max(1, max(a0.shape[:2]) // 512)
    V0 = a0[::s, ::s].max(2)
    V1 = a1[::s, ::s].max(2)
    V0b = gaussian_filter(V0, 3.0)
    cy, cx = np.unravel_index(int(np.argmax(V0b)), V0b.shape)   # 亮核中心
    if V0b.max() / max(float(np.median(V0)), 1e-6) < 8.0:       # 无显著亮核 → 无甜甜圈之忧
        return {"donut": False, "rel": 0.0, "reason": "no_bright_core"}
    H, W = V1.shape
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    nb = 40
    bins = np.linspace(0, float(r.max()), nb + 1)
    idx = np.clip(np.digitize(r.ravel(), bins) - 1, 0, nb - 1)
    Vf = V1.ravel()
    prof = np.array([np.median(Vf[idx == b]) if np.any(idx == b) else np.nan for b in range(nb)])
    prof = prof[~np.isnan(prof)]
    if len(prof) < 12:
        return {"donut": False, "rel": 0.0}
    n = len(prof)
    far = float(np.median(prof[int(n * 0.6):]))                # 远处背景(外 40%)
    mid = prof[int(n * 0.12):int(n * 0.6)]                     # 核外中环(暗环所在)
    ring_min = float(np.min(mid)) if len(mid) else far
    rel = (far - ring_min) / (far + 1e-9)                       # 环比远背景暗多少
    return {"donut": bool(rel > 0.05), "rel": round(rel, 3), "far_bg": round(far, 5),
            "ring_min": round(ring_min, 5), "depth": round(far - ring_min, 5)}


def bg_uniformity(img, gy: int = 7, gx: int = 7, floor_pct: int = 15) -> dict:
    """**梯度校正效果的量化判据**(用户 2026-09-09 M45:星云周围一圈暗、外围又变亮、四角再变暗=残留梯度,
    却没有量化标准判它)。做法:把画面切 gy×gx 格,每格取**低分位**(默认 15%)当该处**背景 floor**(自动排除
    星点/星云亮像素)→ 得到背景的空间分布 → 量它的**不匀度**。返回:
    - `nonflat` = (格 p85 − 格 p15) / 中值 = **稳健的背景起伏比**(平场≈0;越大越不匀)。
    - `span`    = (格 max − 格 min) / 中值 = 极差比(更敏感,含孤立坏格)。
    - `vignette`= 1 − 四角格均值/中央格均值(>0=四角比中央暗=渐晕残留)。
    - `uneven`  = nonflat>0.18 或 span>0.55 → 判**梯度校正不到位**。
    离线标定(真 M45 r06_str vs 合成图):平场 nonflat 0.00/span 0.00;M45 nonflat **0.234**/span **0.745**/vignette 0.12
    (星云旁暗带+亮带);合成渐晕 nonflat 0.31/vignette 0.36。**在拉伸后图上测**(残留梯度拉伸后才显形)。"""
    a = _to_rgb01(img)
    if a is None:
        return {"uneven": False, "nonflat": 0.0, "span": 0.0, "vignette": 0.0}
    V = a.max(2)
    # 【线性图先拉伸(残留梯度在线性域幅度在噪底下、测不出;拉伸后才显)】median 极低=线性 → numpy MTF 自动拉伸到
    #   背景 ~0.15 再测(与在成片上测同标度)。见 [[pi-gradient-findings]]。
    _med0 = float(np.median(V))
    if _med0 < 0.02:
        _madN = float(np.median(np.abs(V - _med0))) * 1.4826
        _c0 = max(0.0, _med0 - 2.8 * _madN)
        _x = np.clip((V - _c0) / max(1e-6, 1.0 - _c0), 0.0, 1.0)
        _mid = _med0 - _c0
        _m = 0.15  # 目标背景
        # MTF: out = ((m-1)x)/((2m-1)x - m),此处 m=mtf(0.15, _mid) 的中点值
        if _mid > 0:
            _mm = ((_m - 1) * _mid) / ((2 * _m - 1) * _mid - _m) if _mid != _m else 0.5
            _mm = min(max(_mm, 1e-4), 0.5)
            V = np.where(_x <= 0, 0.0, np.where(_x >= 1, 1.0,
                         ((_mm - 1) * _x) / ((2 * _mm - 1) * _x - _mm)))
    s = max(1, max(V.shape) // 900)
    V = V[::s, ::s]
    H, W = V.shape
    grid = np.empty((gy, gx), dtype=np.float64)
    for j in range(gy):
        for i in range(gx):
            cell = V[j * H // gy:(j + 1) * H // gy, i * W // gx:(i + 1) * W // gx]
            grid[j, i] = np.percentile(cell, floor_pct) if cell.size else 0.0
    g = grid.ravel()
    med = max(float(np.median(g)), 1e-6)
    nonflat = float((np.percentile(g, 85) - np.percentile(g, 15)) / med)
    span = float((g.max() - g.min()) / med)
    corners = float(np.mean([grid[0, 0], grid[0, -1], grid[-1, 0], grid[-1, -1]]))
    center = float(grid[gy // 2 - 1:gy // 2 + 2, gx // 2 - 1:gx // 2 + 2].mean())
    vignette = float(1.0 - corners / max(center, 1e-6))
    uneven = (nonflat > 0.18) or (span > 0.55)
    return {"uneven": bool(uneven), "nonflat": round(nonflat, 3), "span": round(span, 3),
            "vignette": round(vignette, 3), "bg_med": round(med, 5),
            "bg_min": round(float(g.min()), 5), "bg_max": round(float(g.max()), 5)}


def _coarse_bg(V, frac: int = 12):
    """大尺度背景估计(降采样-升采样,PIL 纯像素、不用 cv2/scipy)。尺度 = 短边/frac(默认 1/12)。
    用途:把**基座/梯度**和**真信号(局部超出量)**分开——见 nebula_preserved。"""
    import numpy as _np
    try:
        from PIL import Image
        H, W = V.shape
        k = max(1, min(H, W) // max(2, int(frac)))
        im = Image.fromarray(_np.clip(V, 0.0, 1.0).astype(_np.float32), mode="F")
        sm = im.resize((max(1, W // k), max(1, H // k)), Image.BILINEAR)
        return _np.asarray(sm.resize((W, H), Image.BILINEAR), dtype=_np.float32)
    except Exception:
        return _np.full(V.shape, float(_np.median(V)), dtype=_np.float32)


def nebula_preserved(before, after, drop_tol: float = 0.15) -> dict:
    """背景扣除(GraXpert BGE / ABE / polybg 等)后**亮信号/星云是否被过扣**的安全判据
    (用户 2026-09-09 M45 梯度补救安全网)。返回 {kept, neb_ratio, struct_ratio, core_ratio, blackish};
    kept=False → 回退别用扣除结果。

    【2026-09-11 M63 重做判据(旧版把正确的修复否掉了)】旧版取 before 的**最亮 10%(V>p90)**当"星云",
    比 after 同位均值。可是背景残留梯度本身就横跨 0.056~0.148,而画面 10% = 77 万像素、星系+星点只有约 4 万——
    **蒙版里 95% 是背景的亮半边**。GraXpert 正确削平梯度 → 这 95% 的均值必然掉 → 被记成"星云被扣掉 26%"
    (M63 实测 neb_ratio 0.742 被否,而同一对图 V>p99.5 比值 0.996、V>p99.9 比值 1.001 = 主体分毫未动)。
    判据本身有梯度敏感性,治法=**改看对梯度不变的量**:

    - ① `struct_ratio`(结构判据):各自减掉大尺度背景得**局部超出量** E=V−coarse_bg(V),在 before 的
      E 高处比 after 的 E。扣掉平滑背景模型时 V 和 coarse_bg 同步下降 → E 不变 → 比值≈1;
      只有真结构被吃掉(星云/星系/星点被当背景减掉)才会掉。
    【判决用哪些量(2026-09-11 用 M63 真图 + 人为过扣做过 15 例标定)】
    - ② `core_ratio`**(主闸)**:最亮 0.3% 像素的**绝对亮度**,分 8×8 格、按亮度加权取低 2% 分位。
      真 GraXpert 0.948/0.942 放行;人为吃掉星系(半径 246px)35%/20% → 0.661/0.806 拦住;
      半径 82px 吃掉 45% → 0.608 拦住。
    - ③ `peak_ratio`(闸):全局最亮 0.02%,补住**极小亮天体**(M57 行星状星云约 30px,整体落在最亮一撮里)。
    - ④ `bg_ratio`(闸):背景中值不许塌到 0.5× 以下——兜住"整片基座被当背景扣掉"。
    - ⑤ `blackish`(闸):after 近全黑 = 把整幅当背景。
    - ① `struct_ratio`**只进日志、不参与判决**:见下方说明(会对正确的修复假警)。

    kept = core/peak/bg 三闸都过且 not blackish。neb_ratio = min(core, peak),保持旧字段语义(越低越危险)。

    【威胁模型边界(实测)】GraXpert 残差在 64px 以下几乎无结构(高通 std 0.004 = 残差跨度的 2.8%,
    256px 才到 10%),所以它**做不出几十像素宽的局部坑**;判据能拦到半径 21px(1313px²)的过扣,
    再小的合成用例超出该工具的能力范围,不作为判据目标。"""
    b = _to_rgb01(before)
    a = _to_rgb01(after)
    if b is None or a is None:
        return {"kept": False, "neb_ratio": 0.0, "struct_ratio": 0.0, "core_ratio": 0.0, "blackish": False}
    Vb, Va = b.max(2), a.max(2)
    blackish = (float(np.median(Va)) < 1e-5) and (float(Va.mean()) < 1e-4)

    # 局部超出量 E=V−大尺度背景:扣平滑背景模型时 V 与 coarse_bg 同步下降 → E 不变(对梯度免疫);
    #   只有真结构被当背景减掉才会掉。
    Eb = Vb - _coarse_bg(Vb)
    Ea = Va - _coarse_bg(Va)
    thr = max(0.015, float(np.percentile(Eb, 99.5)) * 0.2)
    mb = Eb > thr
    thc = float(np.percentile(Vb, 99.7))

    # 【分格取最差格(不能全图取均值)】M63 实测:全图均值会被满屏几千颗未受影响的星点稀释——
    #   人为把星系区乘 0.65(吃掉 35%)全图 struct 仍 0.953/core 0.936 = 放行。而**局部**过扣就是
    #   GraXpert 的典型事故形态(把某片星云/星系当背景减掉)→ 必须按格子量、取最差的那格。
    gy = gx = 8
    H, W = Vb.shape
    cell_min = max(300, int(H * W / (gy * gx) * 0.002))
    sr, cr = [], []
    for jj in range(gy):
        y0, y1 = jj * H // gy, (jj + 1) * H // gy
        for ii in range(gx):
            x0, x1 = ii * W // gx, (ii + 1) * W // gx
            m1 = mb[y0:y1, x0:x1]
            if int(m1.sum()) >= cell_min:
                _eb = Eb[y0:y1, x0:x1][m1]
                if float(_eb.mean()) > 1e-6:
                    sr.append((float(Ea[y0:y1, x0:x1][m1].mean()) / float(_eb.mean()), float(_eb.sum())))
            m2 = Vb[y0:y1, x0:x1] > thc      # 主体门槛放低到 100 像素:极小天体(M57 行星状星云)整体才几百像素
            if int(m2.sum()) >= 100:
                _vb = Vb[y0:y1, x0:x1][m2]
                if float(_vb.mean()) > 1e-6:
                    cr.append((float(Va[y0:y1, x0:x1][m2].mean()) / float(_vb.mean()), float(_vb.sum())))

    def _wq(pairs, q=0.02):
        """**按信号量加权的低分位**(不是简单 min)。只取最差格会被稀疏格的噪声带偏(M63 实测真 GraXpert
        被压到 0.857、贴着 0.85 闸门);而真被过扣的主体必然占住相当份额的亮信号 → 按亮度加权累计到 q
        (默认 2%)处取值:稀疏格权重微乎其微不影响判决,而哪怕只占 4% 亮信号的小天体被吃掉也照样抓到。"""
        if not pairs:
            return 1.0
        pairs = sorted(pairs)
        tot = sum(w for _, w in pairs) or 1.0
        acc = 0.0
        for v, w in pairs:
            acc += w
            if acc >= q * tot:
                return v
        return pairs[-1][0]

    struct = _wq(sr)
    core = _wq(cr)

    # 峰值判据(全局最亮 0.02%,不分格不加权):补住**极小天体**的漏洞——加权分位对只占几百像素
    #   (画面 0.006%)的小目标摊不出份额(实测半径 12px 的团被吃掉 60% 仍放行),而这类天体
    #   (M57 行星状星云约 30px)必然整体落在最亮那一撮里 → 直接量它的绝对亮度。真 GraXpert 只动
    #   星点下的局部背景(幅度 ~0.05),对 V≈0.9 的峰值只有几个百分点,不会假警。
    mp = Vb > float(np.percentile(Vb, 99.98))
    peak = (float(Va[mp].mean()) / max(float(Vb[mp].mean()), 1e-9)) if int(mp.sum()) >= 50 else 1.0

    # 基座判据:背景中值不许塌(整片被当背景减掉;GraXpert 正常修梯度时背景中值持平或略升)
    _mb0, _ma0 = float(np.median(Vb)), float(np.median(Va))
    bg_ratio = (_ma0 / _mb0) if _mb0 > 1e-6 else 1.0

    # 【闸门只用 core+bg(struct 只作日志诊断)】离线用 M63 真图 + 人为过扣做过全用例标定:
    #   core(分格·绝对亮度最差格)在所有用例上都判对了——真 GraXpert 0.948/0.942 放行;人为吃掉星系
    #   35%/20% → 0.661/0.806 拦住;全黑 → 0。
    #   **struct 只进日志、不参与判决**:它分不清"中尺度背景斑块"和"中尺度弥漫结构(星系外晕/银河卷云)",
    #   两者尺度重叠,做成闸门会把正确的梯度修复也否掉(M63 实测真 GraXpert 被压到 struct 0.29)。
    #   【但别把它读成"没事"(2026-09-13 教训)】M63 那个 0.29 报的是**真事**:成片终 GraXpert(smoothing 0.2)
    #   确实把 61% 的弥漫云气当背景减掉了,用户一眼看出"星系外围的暗云被截断"。当时我把它解释成"删掉的正是
    #   背景斑块、正合我意",是错的。→ **struct 低 = 有大量中尺度结构被减掉,必须去看图确认那是斑块还是真云气**;
    #   治法不是放宽这个判据,而是**在线性阶段就把梯度治好**(见 pipeline 星系分支改用 GraXpert BGE),
    #   让成片阶段根本不需要动背景。见 [[pi-gradient-safety-net]] [[pi-galaxy-halo-vignette-degeneracy]]。
    lo = 1.0 - float(drop_tol)
    kept = (core >= lo) and (peak >= lo) and (bg_ratio >= 0.5) and not blackish
    return {"kept": bool(kept), "neb_ratio": round(min(core, peak), 3),
            "struct_ratio": round(struct, 3), "core_ratio": round(core, 3),
            "peak_ratio": round(peak, 3), "bg_ratio": round(bg_ratio, 3),
            "blackish": bool(blackish)}


def core_compression(before, after, mid_tol: float = 1.05) -> dict:
    """**亮核压缩(hdrblend/HDR)是否真的发生了**。返回 {ok, peak_ratio, mid_ratio}。
    - `peak_ratio` = 最亮 0.05% 像素(取 before 的位置)的均值比。**<1 = 核被压下来了**,这正是目的。
    - `mid_ratio`  = 亮区(before 的 p99~p99.9 那一段)中位数之比。**>1.05 = 中间调被抬高 = 发白发平**,
      那是把核"推白"而不是"压回动态范围",要拒。
    ok = peak_ratio < 1 且 mid_ratio <= mid_tol。

    【为什么需要这道闸(用户 2026-09-14 狮子座三重星系「星系被拉爆」)】hdrblend 号称"压回核心动态范围、
    防过曝",实测在这个目标上**两头都坏**:
    ① 核心蒙版被羽化稀释成空操作 —— coreThr=min(0.85, 中位x2+0.35)=0.683,超阈的只有 8115px
      (画面 0.1%,还分散在三个星系上),feather=45 的高斯一糊,蒙版最大值只剩 **0.236**,再乘
      strength 0.6 = 0.141 → 融合几乎没发生(实测融合前后 M66 峰 0.956→0.957)。
    ② 就算修好蒙版也不该用 —— HDRMultiscaleTransform 对这种小而亮的星系是**反效果**:
      实测 rG_hdr 比输入更亮更平(M66 峰 0.956→0.973、中位 0.436→**0.587**)。
    所以不是去修羽化,而是**按实测判决**:真压下来了才采纳,否则保留原图。深数据大星系(M31 型,
    核心区够大、HDR 确实压得住)不受影响。见 [[pi-galaxy-deepdata]]。"""
    b = _to_rgb01(before)
    a = _to_rgb01(after)
    if b is None or a is None:
        return {"ok": False, "peak_ratio": 1.0, "mid_ratio": 1.0}
    Vb, Va = b.max(2), a.max(2)
    # 【必须先平滑掉星点】最亮 0.05% 的像素**全是星点**、不是星系核(实测按原始像素量,得到的是
    #   "星点被压了 4.5%",与亮核压没压毫无关系)。先做 ~10px 尺度的平滑:星点被摊平、星系核留下,
    #   再用它**定位**亮核区,回到原图上取值。
    smb = _coarse_bg(Vb, frac=200)
    mp = smb > float(np.percentile(smb, 99.9))
    if int(mp.sum()) < 200:
        return {"ok": False, "peak_ratio": 1.0, "mid_ratio": 1.0}
    peak = float(Va[mp].mean()) / max(float(Vb[mp].mean()), 1e-9)
    lo, hi = (float(v) for v in np.percentile(smb, [99.0, 99.8]))
    mm = (smb > lo) & (smb <= hi)
    mid = (float(np.median(Va[mm])) / max(float(np.median(Vb[mm])), 1e-9)) if int(mm.sum()) >= 50 else 1.0
    return {"ok": bool(peak < 1.0 and mid <= float(mid_tol)),
            "peak_ratio": round(peak, 3), "mid_ratio": round(mid, 3)}


def _hsv_sv(rgb: np.ndarray):
    """纯 numpy 的 HSV 分量:S=(max-min)/max、V=max(与 cv2 一致,差 ~0.002 量化误差)。"""
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    S = np.where(mx > 1e-9, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    return S, mx


def _star_mask_auto(V: np.ndarray) -> np.ndarray:
    """自动星点蒙版:**局部明显超出背景的紧凑亮点**=星点。用降采样-升采样估大尺度背景(PIL,纯像素、
    无 cv2),V−背景 超阈即星。**必须**——不然亮背景图里满屏中性背景像素会把 S 中位数拉低(M23 亮背景:
    整图测 0.28 vs 星蒙版测 0.53),星点饱和度根本测不准。"""
    try:
        from PIL import Image
        H, W = V.shape
        k = max(8, min(H, W) // 150)                    # 降采样倍数 → 大尺度局部背景
        v8 = (np.clip(V, 0, 1) * 255).astype(np.uint8)
        small = Image.fromarray(v8).resize((max(1, W // k), max(1, H // k)), Image.BILINEAR)
        bg = np.asarray(small.resize((W, H), Image.BILINEAR)).astype(np.float32) / 255.0
        return (V - bg > 0.05) & (V >= 0.15) & (V <= 0.92)
    except Exception:
        return (V >= 0.15) & (V <= 0.85)                # PIL 不可用 → 退回全中高亮度(暗背景仍准)


def star_saturation(img, v_lo: float = 0.15, v_hi: float = 0.85, stars=None) -> float:
    """S_star:**星点像素**上 HSV 饱和度中位数(星色在翼部,核心过曝 S 低,故限亮度中高)。测不到返回 0。
    stars=分离星层(路径/ndarray)时用它当精确蒙版(星区=星层有信号处);否则自动检测紧凑亮点。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return 0.0
    S, V = _hsv_sv(rgb)
    sm = None
    if stars is not None:
        sl = _to_rgb01(stars)
        if sl is not None and sl.shape[:2] == rgb.shape[:2]:
            sm = sl.mean(-1) > 0.03                     # 分离星层有信号处=星点(最准)
    if sm is None:
        sm = _star_mask_auto(V)                         # 无星层 → 自动检测
    m = sm & (V >= v_lo) & (V <= v_hi) & (S > 0.01)
    return round(float(np.median(S[m])), 3) if int(m.sum()) > 50 else 0.0


def background_stats(img, v_bg: float = 0.22) -> dict:
    """背景(暗像素 V<v_bg)中性度:S 中位、通道失衡 (max-min)/mean、亮度中位、偏色方向。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return {"bg_s": 0.0, "bg_imbalance": 0.0, "bg_level": 0.0, "bg_cast": "-", "bg_frac": 0.0}
    S, V = _hsv_sv(rgb)
    bg = V < v_bg
    if int(bg.sum()) < 200:
        bg = V < np.percentile(V, 20)          # 极亮图兜底:取最暗 20%
    means = [float(rgb[..., c][bg].mean()) for c in range(3)]
    mean_avg = sum(means) / 3.0 + 1e-6
    imbalance = (max(means) - min(means)) / mean_avg
    # bg_s = **背景均值色**的 HSV 饱和度(抗噪)。**别用逐像素 S 中位数**:暗背景(V 很小)每个像素的
    #   (max-min)/max 被噪声主导→虚高(M23 实测均值几乎中性却报 0.4),会假报"背景偏色"、还会误导 LLM。
    #   均值先把噪声平均掉,反映的是真实的通道偏色。
    bg_s = (max(means) - min(means)) / (max(means) + 1e-6)
    return {
        "bg_s": round(float(bg_s), 3),
        "bg_imbalance": round(float(imbalance), 3),
        "bg_level": round(float(np.median(V[bg])), 3),
        "bg_cast": ["R", "G", "B"][int(np.argmax(means))],
        "bg_frac": round(float(bg.mean()), 3),
    }


def measure(img, stars=None) -> dict:
    """一次性测全部确定性质量指标。img=成片 PNG/xisf 路径或 ndarray;stars=可选分离星层(路径/ndarray)
    → 用它当精确星蒙版测 s_star(管线里 sep.stars 可传;独立测 png 则自动检测)。异常吞成 error(绝不崩管线)。"""
    try:
        rgb = _to_rgb01(img)
        if rgb is None:
            return {"error": "无法读取图像"}
        out = {"s_star": star_saturation(rgb, stars=stars)}
        out.update(background_stats(rgb))
        # 梯度校正量化判据(用户 2026-09-09 M45):背景不匀度 → 判"梯度校平没有"(nonflat>0.18=残留梯度)
        try:
            _bgu = bg_uniformity(rgb)
            out["bg_nonflat"] = _bgu.get("nonflat")
            out["bg_uneven"] = _bgu.get("uneven")
            out["bg_vignette"] = _bgu.get("vignette")
        except Exception:
            pass
        return out
    except Exception as e:
        return {"error": f"测量异常:{e}"}


def signal_frac(img, thr: float = 0.25) -> float:
    """亮信号占比(V>thr 的像素比例)——区分填满画幅的星云(高)vs 星团/空场(低)。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return 0.0
    return round(float((rgb.max(-1) > thr).mean()), 3)


def signal_balance(img, v_lo: float = 0.25, s_lo: float = 0.10):
    """信号区(亮且有色的像素)的 RGB 色彩平衡 [r,g,b](归一化到均值=1)——该天体"该偏什么色调"。
    取亮(V>v_lo)且有色(S>s_lo)的像素均值:滤掉暗背景和中性星点,只看星云/尘埃主色。测不到返回 None。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return None
    S, V = _hsv_sv(rgb)
    m = (V > v_lo) & (S > s_lo)
    if int(m.sum()) < 100:
        return None
    means = np.array([float(rgb[..., c][m].mean()) for c in range(3)])
    avg = float(means.mean()) + 1e-6
    return (means / avg).tolist()              # 如 [1.25, 0.95, 0.80] = 偏红


def star_balance(img):
    """**星点**的 RGB 色彩平衡 [r,g,b](归一化到均值=1)。测不到返回 None。

    比 signal_balance 更适合当白平衡锚:**星点是两张图里同一批物理天体**,而 signal_balance 取的是
    "亮且有色的像素"——对星系场那就是星系自己,拿它对齐等于用待测量当基准。
    用途:当 SPCC 之后仍有系统性通道偏差时(实测 M65/M66:星点 B-G 本片 -14.4%、三张同视场参考
    -4.4/+3.5/-3.2%),用同视场参考图的**星点色比**做差分校正——星点是两张图里同一批物理天体,
    不依赖对采集端透过曲线的建模。见 [[pi-star-anchored-whitebalance]]。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return None
    m = _star_mask_auto(rgb.max(2))
    if int(m.sum()) < 500:
        return None
    v = np.array([float(np.median(rgb[..., c][m])) for c in range(3)])
    a = float(v.mean())
    if a <= 1e-9:
        return None
    return (v / a).tolist()


def disc_balance(img, blur_base: float = 3.0):
    """**星系/星云「盘」的 RGB 色比** [r,g,b](归一化到均值=1)。测不到返回 None。

    "盘" = 画面里显著延展源(最大的 3 个)内部**亮度 30~65 分位**那一圈 —— 避开过曝核心与外围噪声。
    **必须先按短边归一的核平滑**(默认 σ=3·短边/2094):低信噪区通道被 clip 到 0 时,噪声会把中位数
    抬高,不同噪声水平的两张图直接比色会得出不存在的差异(见 [[pi-noise-artifact-in-color-measurement]])。

    用途:给"星系盘该是什么颜色"一个**可量化的目标**(用户 2026-09-14:「蓝色是后期调过的,这确实很依赖
    肉眼判断,但最好还是能把蓝色的 RGB 数值做一个量化,这样调整也有方向」)。
    实测四张基准(用户手动 Image07 + 三张 AstroBin 同视场)——**盘几乎是中性的**:
      你手动 [0.988 0.987 1.035] | 参考00 [1.007 0.994 1.006] | 参考01 [0.991 0.980 1.028] | 参考02 [1.039 1.002 0.962]
      中位 **[0.999 0.990 1.017]**;而当时程序是 [1.070 1.017 0.922](红高蓝低)。
    对照:**核心**四张基准是 [1.023~1.186 / 0.974~0.997 / 0.845~0.981],程序 [1.111 1.019 0.870] 本就在范围内
    —— 所以要修的是**盘**,不是核。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return None
    try:
        from scipy.ndimage import gaussian_filter, label
    except Exception:
        return None
    try:
        H, W = rgb.shape[:2]
        sc = min(H, W) / 2094.0
        a = np.stack([gaussian_filter(rgb[..., c], max(0.5, blur_base * sc)) for c in range(3)], -1)
        L = a.mean(-1)
        sm = gaussian_filter(L, max(4.0, min(H, W) / 170.0))
        b = float(np.median(sm)); sg = float(np.median(np.abs(sm - b)) * 1.4826)
        if sg <= 1e-9:
            return None
        lab, _ = label(sm > b + 12.0 * sg)
        sz = np.bincount(lab.ravel())
        ks = [k for k in np.argsort(sz[1:])[::-1] + 1 if sz[k] > int(0.0004 * L.size)][:3]
        vals = []
        for k in ks:
            ys, xs = np.nonzero(lab == k)
            reg = L[ys, xs]
            lo, hi = (float(v) for v in np.percentile(reg, [30, 65]))
            sel = (reg > lo) & (reg <= hi)
            if int(sel.sum()) < 300:
                continue
            q = np.array([float(np.median(a[..., c][ys, xs][sel])) for c in range(3)])
            m = float(q.mean())
            if m > 1e-9:
                vals.append(q / m)
        if not vals:
            return None
        return [round(float(x), 3) for x in np.median(np.array(vals), 0)]
    except Exception:
        return None


# 【★参考图的 s_star 要先折算尺度再比(用户 2026-09-15)】参考是 620px 缩略图,我们的成片是 3800px,
#   而 **star_saturation 不是尺度不变量**:同一张图缩到 620px 量出来只有全分辨率的 0.74~0.80 倍
#   (实测用户手调 M31/M51/M63 = 0.76 / 0.74 / 0.80)—— 缩图把弱星糊进背景、只剩最亮那批,
#   而弱星恰恰是偏中性的那部分,被丢掉后中位数就抬上去了。
#   不折算就是**拿两把尺子量再相减**,和 disc_signal_color 那次"取样集合不同"是同一类错误。
_S_STAR_THUMB_GAIN = 0.77          # 620px / 全分辨率,三张实测中位


# 用户手工库五张星系实测 s_star(全分辨率):M51 0.147 / M31 0.169 / M64 0.180 / M63 0.205 /
#   M65_M66 0.229 —— 中位 0.180,整个范围 0.147~0.229。
#   **通用甜区 0.22~0.40 的下限高过他的整个范围**(只有 M65_M66 擦到边),所以按通用值判,
#   他自己满意的成片也会张张标红。AstroBin 同视场参考则是另一极端:M31 参考中位折算全分辨率
#   0.491(带 0.368~0.687)—— 获奖作品的星点颜色比用户风格浓 3 倍,那是**真实的审美差异**。
#   → 默认锚到**用户自己的库**(和盘色一样的分工:参考给客观锚点、自有库给个人口味)。
#   下限 0.14 贴着他的最低值(M51 0.147)、上限 0.32 留出余量(他最高 0.229)。
HOUSE_S_STAR = (0.14, 0.32)


def s_star_band(targets: dict | None = None, source: str | None = None, verbose: bool = False) -> tuple:
    """星点饱和的目标带 (lo, hi) —— **单一真源**:UI 徽章、评委上下文、质量门都从这里取,
    别在别处复制阈值([[pi-critic-scoring-bias]]:复制的迟早变废值还继续误导评委)。

    来源由设置 `s_star_target` 决定(用户 2026-09-15 先试 house):
      · "house"(默认)= 用户手工库那条带,反映**他的**标准;
      · "ref"         = 这个天体的 AstroBin 同视场参考中位(拿不到就退回 house);
      · "fixed"       = 通用甜区 0.22~0.40。
    verbose=True 时返回 (lo, hi, 来源标签) —— 让 UI/日志直接用这个标签,
    别自己再判一遍来源(那就是又一处会走样的复制)。
    """
    src = (source or "").strip().lower()
    if not src:
        try:
            from . import config as _cfg
            src = str(_cfg.get_setting("s_star_target") or "house").strip().lower()
        except Exception:
            src = "house"
    if src == "fixed":
        return (S_STAR_LO, S_STAR_HI, "通用甜区") if verbose else (S_STAR_LO, S_STAR_HI)
    if src == "ref":
        try:
            c = float((targets or {}).get("s_star_fullres") or 0.0)
        except (TypeError, ValueError):
            c = 0.0
        if c > 0:
            _b = (round(max(0.12, min(0.45, c * 0.75)), 3),
                  round(max(0.30, min(0.85, c * 1.40)), 3))
            return (_b[0], _b[1], "同视场参考") if verbose else _b
    return (HOUSE_S_STAR[0], HOUSE_S_STAR[1], "自有风格") if verbose else HOUSE_S_STAR


def ref_targets(ref_paths) -> dict | None:
    """测多张 AstroBin 同视场参考图 → 该天体的**经验目标**(中位数聚合,抗单张异常)。
    返回 {n, s_star, bg_level, bg_s, signal_frac, rgb_balance, star_balance, disc_balance,
    disc_signal, disc_signal_sd, disc_signal_n} 或 None(无有效参考)。
    **disc_signal = 该天体的盘色目标 [R/G, B/G]**(用户 2026-09-15 选的「按目标取参考」方案):
    单一全局家族目标服务不了所有星系 —— M51(蓝旋臂)真盘 B/G 1.16,M31(尘埃暖调)只有 0.87。
    12 张 M51 同视场参考实测中位 [1.031, 1.015](σ 0.079 / 0.088),而家族中位是 [1.21, 0.99]
    —— **R/G 差了 0.18**,这才是 M51 发灰的大头。
    用途:替代固定标准(星点多饱和/背景多暗)+ 反推该不该揭示(signal_frac)+ 调色对齐(rgb_balance 该偏什么色调)。
    见 [[pi-astrobin-reference]] 血泪 / [[pi-quality-gate]]。"""
    ss, bl, bs, sf, bal, sbal, dbal = [], [], [], [], [], [], []
    dsig = []          # 盘信号色比(扣背景 + 按本体自身尺度取环),见下
    dprof = []         # 盘色**廓线**(按信号占峰值分档);风格步逐档对齐用
    for p in ref_paths or []:
        rgb = _to_rgb01(p)
        if rgb is None:
            continue
        m = measure(rgb)                       # 参考图无分离星层 → 自动星点检测
        if m.get("error"):
            continue
        ss.append(m["s_star"]); bl.append(m["bg_level"]); bs.append(m["bg_s"])
        sf.append(signal_frac(rgb))
        _b = signal_balance(rgb)
        if _b:
            bal.append(_b)
        _sb = star_balance(rgb)
        if _sb:
            sbal.append(_sb)
        _db = disc_balance(rgb)
        if _db:
            dbal.append(_db)
        # 【★按目标取盘色(用户 2026-09-15 选的方案)】和成片侧用**同一个函数**量 ——
        #   风格步算的是 gain = 目标/当前,两边口径必须逐字一致,否则两个函数之间的系统偏差
        #   会原封不动变成成片的色偏。disc_balance 留着给别处用,但它不扣背景,不当目标源。
        try:
            from . import recombine as _rcq
            _dsg = _rcq.disc_signal_color(rgb)
            if _dsg:
                dsig.append([float(_dsg[0]), float(_dsg[1])])
            # 廓线:和成片侧用**同一个函数**量(单一口径);分档按信号占峰值的比例,
            #   与视场/缩略图尺寸无关 —— 620px 参考和 3800px 成片可以直接比。
            _dpf = _rcq.disc_color_profile(rgb)
            if _dpf:
                dprof.append([(None if o is None else (o["rg"], o["bg"])) for o in _dpf])
        except Exception:
            pass
    if not ss:
        return None

    def _med(a):
        return round(float(np.median(a)), 3)
    out = {"n": len(ss), "s_star": _med(ss), "bg_level": _med(bl),
           # 折算回全分辨率口径,才能和成片实测的 s_star 直接比(见 _S_STAR_THUMB_GAIN)
           "s_star_fullres": round(float(_med(ss)) / _S_STAR_THUMB_GAIN, 3),
           "bg_s": _med(bs), "signal_frac": _med(sf)}
    if bal:
        out["rgb_balance"] = [round(float(x), 3) for x in np.median(np.array(bal), axis=0)]
    if sbal:
        out["star_balance"] = [round(float(x), 3) for x in np.median(np.array(sbal), axis=0)]
    if dbal:
        out["disc_balance"] = [round(float(x), 3) for x in np.median(np.array(dbal), axis=0)]
    if dsig:
        _a = np.array(dsig)
        out["disc_signal"] = [round(float(x), 3) for x in np.median(_a, axis=0)]
        out["disc_signal_sd"] = [round(float(x), 3) for x in np.std(_a, axis=0)]
        out["disc_signal_n"] = int(len(dsig))   # 样本量决定能不能信它(见 [[pi-galaxy-disc-color-target]])
    if dprof:
        # 逐档取中位(每档各自统计有值的样本);某档有效样本 <3 张就置 None = 那一档不动
        _nl = max(len(p) for p in dprof)
        _med_prof, _cnt = [], []
        for _i in range(_nl):
            _v = [p[_i] for p in dprof if _i < len(p) and p[_i]]
            _cnt.append(len(_v))
            if len(_v) < 3:
                _med_prof.append(None)
            else:
                _a = np.array(_v, dtype=float)
                _med_prof.append([round(float(np.median(_a[:, 0])), 3),
                                  round(float(np.median(_a[:, 1])), 3)])
        out["disc_profile"] = _med_prof
        out["disc_profile_n"] = _cnt
    return out


def diagnose(m: dict, *, cluster_target: bool = False, targets: dict | None = None) -> list[dict]:
    """把指标对照目标带 → 问题列表(每个含 issue/knob/how,供质量门决定回退动作)。
    cluster_target=True(疏散/球状星团、纯亮场):额外要求背景钉深、近中性。
    targets=参考图导出的**因目标而异**目标(ref_targets):给了就用它校准 S_star 下限(取参考中位与固定甜区较
    宽松者当下限,避免对本就低饱和的天体误判;背景中性仍用固定判据,因优秀作品背景都该中性)。"""
    out = []
    if not m or m.get("error"):
        return out
    s = m.get("s_star", 0.0)
    # S_star 下限:有参考则用 min(固定甜区下限, 参考中位×0.8)——参考星点若本就不很饱和(如某些星系场)
    #   就别硬拿固定 0.30 卡;但也不低于一个地板 0.20(<0.20 一定发闷)。
    s_lo = S_STAR_LO
    # 目标带一律从 s_star_band 取(单一真源:来源/兜底都在那里面判)
    s_lo = s_star_band(targets)[0]
    if 0 < s < s_lo:
        out.append({"issue": "dull_stars", "metric": f"S_star={s}(目标≥{s_lo})",
                    "how": f"星点饱和度 {s}<{s_lo}(发闷)——多因合星到亮/偏色背景被稀释,或提饱和不足"})
    if m.get("bg_s", 0) > BG_S_MAX or m.get("bg_imbalance", 0) > BG_IMBAL_MAX:
        out.append({"issue": "dirty_background", "metric": f"bg_S={m.get('bg_s')} 失衡={m.get('bg_imbalance')}",
                    "how": f"背景偏色({m.get('bg_cast')} 偏高)——需加强背景中和/去色"})
    if cluster_target and m.get("bg_level", 0) > BG_LEVEL_MAX:
        out.append({"issue": "background_lifted", "metric": f"bg_level={m.get('bg_level')}",
                    "how": f"背景抬太亮({m.get('bg_level')}>{BG_LEVEL_MAX})——星团/纯亮场应钉深,别揭示背景"})
    return out
