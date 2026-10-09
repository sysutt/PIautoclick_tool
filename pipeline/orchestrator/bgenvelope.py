"""铺满画面的星云:背景只贴最暗处拟合(自动版的手动 DBE)+「去背景吃没吃天体」的直接量。

【为什么要有(用户 2026-10-06 IC4592 蓝马头「主体拉伸严重不足」)】
天光梯度是主体自身信号的 4.4 倍,星云又铺满画面。拿用户手动 DBE 的 27 个采样点当背景真值去量:
管线开头的 GradientCorrection 只留住主体大尺度信号的 56%、尘埃 36%;ABE 被判「背景不平」后,
补救环按「背景越平越好」挑了 GraXpert smoothing 0.2,又只留 36%/26% —— 进拉伸前主体只剩 ~20%。
同刻度同拉伸下,主体内部被掏空、只剩边缘细丝;后面怎么加大 GHS / 揭示 / LHE 都补不回来,只会把
残余和噪声拉成斑驳。而只做用户的 DBE,与他成片的大尺度结构秩相关 0.885(管线 0.55)。

根子在于:**现有的安全网全在量高频 / 极亮 / 全局中值**(核心比、峰值比、基座比),大尺度的弥漫信号
被删掉它们看不见;平整度指标又**奖励**删星云(铺满画面时,删掉星云正是让背景最平的办法)。
见 [[pi-flatness-metric-deletes-nebula]]。这里补上缺的那个量,以及一个不删星云的背景模型。

两件东西:
1. **背景模型**:块中值去星 → 网格低分位 → **非对称稳健二次面**(低于曲面的格全权重,高出曲面的格按
   噪声尺度指数降权)。效果等于「只贴着最暗处」—— 但四角四边只要是暗的照样能锚住(先前「只留最暗 30%
   的格」版本漏掉了左上角和四边,二次面凹成碗,主体被多减 21%)。IC4592 实测与用户 DBE:
   结构秩相关 0.877(用户 0.880),主体 97% / 尘埃 99%。二次以上的阶会弯进星云(三阶 0.81、四阶 0.79),
   放宽降权(k=2/3)会让星云格把曲面顶上去(= GraXpert 的毛病),都不用。
2. **signal_keep**:某一步去背景之后,天体大尺度信号还剩多少。背景格只在「之前」那张上定一次、两张都用
   这组格拟合零点(像 DBE 的固定采样点;各自重定会让零点随选格漂,实测读出 polybg 0.91 > 它之前的 ABE
   0.66 这种不可能的数)。IC4592:GC 0.66、ABE 0.69、GraXpert(0.2) 0.48;M31 0.993、M51 0.983。
"""
from __future__ import annotations

import numpy as np

GRID_ROWS = 16          # 背景格网格行数(列数按画幅比例)
CELL_PCT = 25           # 每格取块中值图的这个分位当「地面」
ASYM_K = 1.0            # 高出曲面 r 的格权重 exp(-(r/(k·s))²);s = 曲面以下那侧残差的稳健尺度
DEGREE = 2


def _lum(a):
    if a.ndim == 2:
        return a
    if a.shape[2] >= 3:
        return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    return a[..., 0]


def _blocks(plane, bk):
    """bk×bk 块中值(压掉星点)+ 轻平滑。"""
    from scipy.ndimage import gaussian_filter
    H, W = plane.shape
    Hb, Wb = (H // bk) * bk, (W // bk) * bk
    m = np.median(plane[:Hb, :Wb].reshape(Hb // bk, bk, Wb // bk, bk)
                  .transpose(0, 2, 1, 3).reshape(Hb // bk, Wb // bk, bk * bk), axis=-1)
    return gaussian_filter(m.astype(np.float64), 1.0)


def _block_size(shape):
    return max(4, min(shape[0], shape[1]) // 480)


def _design(x, y, deg=DEGREE):
    t = [np.ones_like(x)]
    for d in range(1, deg + 1):
        for i in range(d + 1):
            t.append(x ** (d - i) * y ** i)
    return np.stack(t, -1)


def _cells(m, gh=GRID_ROWS, pct=CELL_PCT):
    h, w = m.shape
    gw = max(8, int(round(gh * w / h)))
    ch, cw = h // gh, w // gw
    cx, cy, cv = [], [], []
    for i in range(gh):
        for j in range(gw):
            cv.append(np.percentile(m[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw], pct))
            cy.append((i + .5) * ch / h)
            cx.append((j + .5) * cw / w)
    return np.array(cx), np.array(cy), np.array(cv)


def background_weights(m, k=ASYM_K):
    """非对称 IRLS → 每格的「是背景」权重(1=背景,→0=天体)。返回 (weights, 曲面以下残差的稳健尺度)。"""
    cx, cy, cv = _cells(m)
    A = _design(cx, cy)
    wts = np.ones(cv.size)
    s = 0.0
    for _ in range(40):
        sw = np.sqrt(wts)
        c, *_ = np.linalg.lstsq(A * sw[:, None], cv * sw, rcond=None)
        r = cv - A @ c
        neg = r[r <= 0]
        s = max(1.4826 * float(np.median(np.abs(neg))) if neg.size > 5 else float(np.std(r)), 1e-12)
        new = np.where(r <= 0, 1.0, np.exp(-(r / (k * s)) ** 2))
        if float(np.max(np.abs(new - wts))) < 1e-4:
            wts = new
            break
        wts = new
    return wts, s


def _fit(m, wts):
    cx, cy, cv = _cells(m)
    A = _design(cx, cy)
    sw = np.sqrt(wts)
    c, *_ = np.linalg.lstsq(A * sw[:, None], cv * sw, rcond=None)
    return c, cv


def _surface(c, h, w):
    yy, xx = np.mgrid[0:h, 0:w]
    return _design(xx / w, yy / h) @ c


def _read(path):
    from xisf import XISF
    x = XISF(str(path))
    a = np.asarray(x.read_image(0), np.float32)
    if a.ndim == 3 and a.shape[2] == 1:
        a = a[..., 0]
    return x, a


def signal_keep(before_path, after_path) -> dict:
    """去背景这一步之后,天体大尺度信号还剩多少(1.0 = 一点没吃)。
    天体区 = 「之前」那张高出背景面 max(25%·p99, 5σ) 的部分;不足画面 2% → keep=None(没有可吃的大尺度信号)。
    同刻度的步(GC/ABE/GraXpert/polybg 都是减法)直接比;逐通道缩放过的(SPCC)别拿来比。"""
    _, a = _read(before_path)
    _, b = _read(after_path)
    La, Lb = _lum(a), _lum(b)
    bk = _block_size(La.shape)
    mb, ma = _blocks(La, bk), _blocks(Lb, bk)
    if ma.shape != mb.shape:
        h, w = min(mb.shape[0], ma.shape[0]), min(mb.shape[1], ma.shape[1])
        mb, ma = mb[:h, :w], ma[:h, :w]
    wts, _ = background_weights(mb)
    h, w = mb.shape
    cb, _ = _fit(mb, wts)
    ca, _ = _fit(ma, wts)
    Sb = mb - _surface(cb, h, w)
    Sa = ma - _surface(ca, h, w)
    neg = Sb[Sb <= 0]
    noise = 1.4826 * float(np.median(np.abs(neg))) if neg.size > 10 else float(np.std(Sb))
    thr = max(0.25 * float(np.percentile(Sb, 99)), 5.0 * noise)
    R = Sb > thr
    out = {"region": round(float(R.mean()), 4), "bg_cells": round(float((wts > 0.5).mean()), 3)}
    if R.mean() < 0.02:
        out["keep"] = None
        return out
    v = Sb[R]
    hi, lo = R & (Sb > np.median(v)), R & (Sb <= np.median(v))
    out["keep"] = round(float(np.median(Sa[R]) / np.median(Sb[R])), 3)
    out["keep_bright"] = round(float(np.median(Sa[hi]) / np.median(Sb[hi])), 3)
    out["keep_faint"] = round(float(np.median(Sa[lo]) / np.median(Sb[lo])), 3)
    return out


def channel_keep(before_path, after_path) -> dict:
    """signal_keep 的**分通道**版,给铺满画面的星系用:去背景有没有把各通道吃得不一样(= 改了颜色)。

    【为什么(用户 2026-10-09 M33「色彩加得太满」)】BN+CC 刚做完,M33 核→外 R/G 1.12→0.92、B/G 0.95→1.045
    (暖核蓝外盘,与 AstroBin 共识同向)。两道线性去背景把外盘吃掉、且各通道不等(GraXpert 最外环
    R 留 91% / B 只留 79%)→ 外盘 B/G 掉到 0.944;后面提饱和 ×6 把这几个百分点放大成「内橙/中蓝/外黄绿」色环。
    亮度上的保留率看不见这件事(两道都过了「外晕保住」的验收)。
    天体区 = 亮度高出背景面 5σ 的全部块(要一直延伸到外盘;signal_keep 的「25%·p99」只圈得到内盘)。
    淡部 = 天体区里最暗的四分之一(外盘)。背景格只在「之前」那张上按亮度定一次,三个通道共用。
    返回 {region, keep:[R,G,B], keep_faint:[R,G,B], shift, shift_faint};shift = 通道间 max/min − 1。"""
    _, a = _read(before_path)
    _, b = _read(after_path)
    if a.ndim != 3 or b.ndim != 3 or a.shape[2] < 3 or b.shape[2] < 3 or a.shape != b.shape:
        return {"keep": None, "reason": "不是同尺寸的三通道图"}
    La = _lum(a)
    bk = _block_size(La.shape)
    mL = _blocks(La, bk)
    wts, _ = background_weights(mL)
    h, w = mL.shape
    cL, _ = _fit(mL, wts)
    SL = mL - _surface(cL, h, w)
    neg = SL[SL <= 0]
    noise = 1.4826 * float(np.median(np.abs(neg))) if neg.size > 10 else float(np.std(SL))
    R = SL > 5.0 * noise
    out = {"region": round(float(R.mean()), 4)}
    if R.mean() < 0.02:
        out["keep"] = None
        return out
    faint = R & (SL <= np.percentile(SL[R], 25))
    keep, keep_f = [], []
    for c in range(3):
        mb, ma = _blocks(a[..., c], bk), _blocks(b[..., c], bk)
        Sb = mb - _surface(_fit(mb, wts)[0], h, w)
        Sa = ma - _surface(_fit(ma, wts)[0], h, w)
        db, dbf = float(np.median(Sb[R])), float(np.median(Sb[faint]))
        if db <= 0 or dbf <= 0:
            return {**out, "keep": None, "reason": "某个通道在天体区量不出信号"}
        keep.append(float(np.median(Sa[R])) / db)
        keep_f.append(float(np.median(Sa[faint])) / dbf)
    out.update(keep=[round(x, 3) for x in keep], keep_faint=[round(x, 3) for x in keep_f],
               shift=round(max(keep) / max(min(keep), 1e-6) - 1.0, 4),
               shift_faint=round(max(keep_f) / max(min(keep_f), 1e-6) - 1.0, 4))
    return out


def _stf_preview(arr, path):
    """线性图预览:STF 式自动拉伸(只给人看,不进链路)。"""
    from PIL import Image
    d = arr[::4, ::4, :3] if arr.ndim == 3 else np.repeat(arr[::4, ::4, None], 3, axis=2)
    L = d.mean(-1)
    med = float(np.median(L))
    mad = float(np.median(np.abs(L - med))) * 1.4826
    c0 = max(0.0, med - 2.8 * mad)
    x = (med - c0) / max(1.0 - c0, 1e-6)
    mm = ((0.25 - 1) * x) / ((2 * 0.25 - 1) * x - 0.25) if x > 0 else 0.5
    y = np.clip((d - c0) / max(1.0 - c0, 1e-6), 0, 1)
    s = ((mm - 1) * y) / ((2 * mm - 1) * y - mm)
    Image.fromarray((np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path)
    return path


def subtract_envelope(in_path, out_path, preview_path=None, log=None) -> dict:
    """逐通道减去「只贴最暗处」的二次背景面(背景格按亮度选一次,三个通道用同一组格),保留原天光平均电平。
    返回 {image, preview, applied:{bg_cells, amp, amp_over_signal}}。"""
    from xisf import XISF
    x, a = _read(in_path)
    try:
        im_meta = x.get_images_metadata()[0]
    except Exception:
        im_meta = None
    try:
        f_meta = x.get_file_metadata()
    except Exception:
        f_meta = None
    planes = [a] if a.ndim == 2 else [a[..., c] for c in range(a.shape[2])]
    L = _lum(a)
    bk = _block_size(L.shape)
    mL = _blocks(L, bk)
    wts, s = background_weights(mL)
    h, w = mL.shape
    H, W = L.shape
    Wb, Hb = w * bk, h * bk
    # 全分辨率坐标 → 块图归一化坐标:块 j 的中心在全图 (j+0.5)·bk − 0.5 → x_m = (X+0.5)/Wb
    xs = ((np.arange(W, dtype=np.float32) + 0.5) / Wb)[None, :]
    ys = ((np.arange(H, dtype=np.float32) + 0.5) / Hb)[:, None]
    out = np.empty_like(a)
    amps = []
    cL, _ = _fit(mL, wts)
    sig = float(np.percentile(mL - _surface(cL, h, w), 99))
    for ci, p in enumerate(planes):
        mc = mL if len(planes) == 1 else _blocks(p, bk)
        c, cv = _fit(mc, wts)
        # 天光平均电平:背景格上曲面的加权平均 —— 只减起伏,不减电平(下游 BN / SPCC 照常工作)
        cxs, cys, _ = _cells(mc)
        ref = float(np.sum(wts * (_design(cxs, cys) @ c)) / max(np.sum(wts), 1e-12))
        model = np.zeros((H, W), np.float32)
        k = 0
        for d in range(0, DEGREE + 1):
            for i in range(d + 1):
                model += np.float32(c[k]) * (xs ** (d - i)) * (ys ** i)
                k += 1
        amps.append(float(model.max() - model.min()))
        q = p - (model - np.float32(ref))
        if a.ndim == 2:
            out = q
        else:
            out[..., ci] = q
        model = q = None
    out = np.clip(out, 0.0, 1.0).astype(np.float32)
    XISF.write(str(out_path), out, creator_app="TTAstroPiLot", image_metadata=im_meta, xisf_metadata=f_meta)
    pv = None
    if preview_path:
        try:
            pv = _stf_preview(out, str(preview_path))
        except Exception:
            pv = None
    amp = max(amps) if amps else 0.0
    info = {"bg_cells": round(float((wts > 0.5).mean()), 3), "amp": round(amp, 6),
            "amp_over_signal": round(amp / max(sig, 1e-12), 2)}
    if log:
        log("背景面(只贴最暗处的二次面):起伏 %.2e = 天体信号的 %.1f 倍;%d%% 的格当背景"
            % (amp, info["amp_over_signal"], int(100 * info["bg_cells"])))
    return {"status": "ok", "image": str(out_path), "preview": pv, "applied": info}


def neutralize_on_background(in_path, out_path, preview_path=None, max_dev=0.25, log=None) -> dict | None:
    """线性图背景色中和,**背景只取「只贴最暗处」那组格**(权重 > 0.5)。
    【为什么不用 SPCC 自带的 BN / neutralize_bg_offset】两者都按全图亮度分布挑「背景」—— 星云铺满画面时
    挑到的是淡星云本身,中和它的颜色等于把真天光推成补色(用户手动版 SPCC 没设背景参考区,暗部偏紫)。
    只减逐通道均匀偏移、不动结构;偏移超过 max_dev(相对背景电平)视为没选对背景,不动,返回 None。"""
    from xisf import XISF
    x, a = _read(in_path)
    if a.ndim == 2 or a.shape[2] < 3:
        return None
    try:
        im_meta = x.get_images_metadata()[0]
    except Exception:
        im_meta = None
    try:
        f_meta = x.get_file_metadata()
    except Exception:
        f_meta = None
    L = _lum(a)
    bk = _block_size(L.shape)
    mL = _blocks(L, bk)
    wts, _ = background_weights(mL)
    h, w = mL.shape
    gh = GRID_ROWS
    gw = max(8, int(round(gh * w / h)))
    ch, cw = h // gh, w // gw
    sel = np.zeros((h, w), bool)
    k = 0
    for i in range(gh):
        for j in range(gw):
            if wts[k] > 0.5:
                sel[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw] = True
            k += 1
    if sel.mean() < 0.02:
        if log:
            log("背景色中和:选得出的背景格不到画面 2%,不动")
        return None
    lev = np.array([float(np.median(_blocks(a[..., c], bk)[sel])) for c in range(3)])
    off = lev - lev.min()
    dev = float(off.max() / max(float(lev.max()), 1e-12))
    if log:
        log("背景色中和(最暗处那组格,占画面 %d%%):电平 R %.5f G %.5f B %.5f,偏移 %.2f%%"
            % (int(100 * sel.mean()), lev[0], lev[1], lev[2], 100 * dev))
    if dev > max_dev:
        if log:
            log("  → 偏移 %.1f%% 超过 %.0f%%,不像天光(可能选到了天体),不动" % (100 * dev, 100 * max_dev))
        return None
    out = np.clip(a[..., :3] - off[None, None, :].astype(np.float32), 0.0, 1.0).astype(np.float32)
    XISF.write(str(out_path), out, creator_app="TTAstroPiLot", image_metadata=im_meta, xisf_metadata=f_meta)
    pv = None
    if preview_path:
        try:
            pv = _stf_preview(out, str(preview_path))
        except Exception:
            pv = None
    return {"status": "ok", "image": str(out_path), "preview": pv,
            "applied": {"levels": [round(float(v), 6) for v in lev], "offsets": [round(float(v), 6) for v in off],
                        "dev": round(dev, 4), "bg_frac": round(float(sel.mean()), 3)}}

SKY_BLOCK = 32          # flatten_sky:天空块边长(px)
SKY_SIGMA = 2.0         # flatten_sky:只在天空块里做的归一化高斯平滑(块)
SKY_BODY_DILATE = 0.35  # flatten_sky:本体外扩多少倍等效半径当保护区(外晕余量)
SKY_MIN_CORR_SIG = 1.0  # 天空上最大改正量不到「天空块噪声 σ」的这么多倍就不动
#   (按 σ 定、不写绝对值:线性图天空 0.0024、σ 4e-6,成片天空 0.08、σ 0.006 —— 同一个函数两头都要用;
#    成片上 1σ ≈ 原来的绝对门槛 0.005)


def flatten_sky(in_path, out_path, preview_path=None, log=None, linear: bool = False,
                two_sided: bool = False, taper: float = 0.0) -> dict | None:
    """成片(非线性)天空上的局部亮斑/色斑压平 —— **只在天空上量、只在天空上改**,星系(外扩后)内改正量恒为 0。

    【为什么(用户 2026-10-09 M33 第九轮)】占满画面的星系线性阶段走「只贴最暗处」二次面,成片的 GraXpert
    随之跳过(它把外晕当梯度)。可二次面跟不住**局部**的角落亮起:第九轮下面两角 0.120 / 0.136、偏绿
    (G−(R+B)/2 +0.014 / +0.020),而天空 0.055 —— 原来是成片 GraXpert 顺手抹掉的。
    做法:32px 块逐通道 p30(压星点)→ 块亮度众数 + 暗侧σ 定天空,最大连通亮区 = 本体,外扩 0.35 倍等效半径
    留外晕余量 → 只用天空块做归一化高斯平滑 → 高于天空中位的部分减掉(只减多出来的亮,不抬暗处)。
    不用插值/样条去猜星系底下的背景:试过薄板样条,全局平滑跟不住角(只降到 0.08),局部化又在本体里
    凸出 +0.024 的假背景(会被当背景从星系上减掉)。实测:两角 → 0.067 / 0.063,偏绿 → +0.002,本体内改正 0。
    【线性阶段也用,而且主要在那用(用户 2026-10-09:「后面步骤修好了,但最好在前面就修」)】角落亮斑不是原始数据
    带的:r00 四角 −0.5σ/+0.3σ,是**「只贴最暗处」二次面造出来的**(M33 只有 15% 的格当背景,二次面在下两角外推
    偏低,减完那两角高出天空 +8.7σ/+10.5σ,只占天空电平 1.5%,拉伸后成了 0.12 vs 0.055)。在二次面后面立刻压平:
    两角 → +1.0σ/+0.8σ,外晕 900~2600px 各环信号保留 100%(改正量 0)。成片那次保留作安全网。
    返回 None = 没有要改的(或认不出本体)。"""
    from scipy import ndimage as ndi
    from xisf import XISF
    x, a = _read(in_path)
    if a.ndim == 2 or a.shape[2] < 3:
        return None
    try:
        im_meta = x.get_images_metadata()[0]
    except Exception:
        im_meta = None
    try:
        f_meta = x.get_file_metadata()
    except Exception:
        f_meta = None
    rgb = np.clip(a[..., :3], 0.0, 1.0)
    H, W = rgb.shape[:2]
    B = SKY_BLOCK
    gh, gw = -(-H // B), -(-W // B)
    pad = np.pad(rgb, ((0, gh * B - H), (0, gw * B - W), (0, 0)), mode="edge")
    cell = np.percentile(pad.reshape(gh, B, gw, B, 3), 30, axis=(1, 3))
    L = cell.mean(-1)
    hist, ed = np.histogram(L, bins=200, range=(0.0, float(np.percentile(L, 90))))
    i = int(np.argmax(hist))
    mode = float((ed[i] + ed[i + 1]) / 2)
    lo = L[L <= mode]
    sig = 1.4826 * float(np.median(mode - lo)) if lo.size > 10 else 0.0
    sig = max(sig, 1e-3 * max(mode, 1e-9))     # 地板随电平走:写死 1e-4 在线性图上 = 25σ,本体会缩到只剩核
    body = ndi.gaussian_filter(L, 1.5) > mode + 4.0 * sig
    lab, n = ndi.label(body)
    if not n:
        if log:
            log("天空局部压平:认不出本体,不动")
        return None
    sz = ndi.sum(body, lab, range(1, n + 1))
    body = lab == (1 + int(np.argmax(sz)))
    r_body = float(np.sqrt(body.sum() / np.pi))
    sky = ~ndi.binary_dilation(body, iterations=max(2, int(round(SKY_BODY_DILATE * r_body))))
    if sky.mean() < 0.10:
        if log:
            log("天空局部压平:外扩后天空不到画面 10%%(%.0f%%),量不准,不动" % (100 * sky.mean()))
        return None
    # 【亮星罩(2026-10-09 M33 第十三轮)】块 p30 压得住普通星点,压不住亮星的核和光晕:底边一颗饱和亮星(2997,4052)
    #   周围被当「天空偏亮」减掉 8e-5(天空σ 的 18 倍、平滑又把它摊到 150px),去星后留下一圈暗洞,合星后成黑斑。
    #   → 亮星核(高出天空 50 个像素噪声、面积不大的连通块)外扩 2.5 倍核半径 + 16px,罩住的像素不进块统计,
    #   罩掉三成以上的块不当天空、由周围插值(改正量照样平滑地施加到这些像素上)。
    Lp = rgb.mean(-1)
    sig_px = 1.4826 * float(np.median(np.abs(np.diff(Lp[::8], axis=1)))) / np.sqrt(2.0)
    # 线性图:像素噪声大,50σ 正好挑出亮星;成片:降噪后像素噪声极小,50σ 会把几乎所有星都挑上、罩掉大半天空
    #   (第十四轮 r14c「罩掉亮星后天空不到 10%」整步跳过)→ 成片上只认真亮的星核:高出天空到 1 之间的 40%。
    thr = 50.0 * max(sig_px, 1e-9)
    if not linear:
        thr = max(thr, 0.4 * (1.0 - mode))
    core = Lp > mode + thr
    clab, cn = ndi.label(core)
    star = np.zeros((gh, gw), bool)
    nstar = 0
    if cn:
        area = ndi.sum(core, clab, range(1, cn + 1))
        keep_id = np.zeros(cn + 1, bool)
        keep_id[1:] = (area >= 9) & (area <= np.pi * 60.0 ** 2)        # 太大的是星系核/本体,不是星
        nstar = int(keep_id.sum())
        if nstar:
            rad = np.zeros(cn + 1, np.float32)
            rad[1:] = np.minimum(2.5 * np.sqrt(area / np.pi) + 16.0, 150.0)
            sc = 4                                               # 罩在 1/4 分辨率上建,够准也快
            hs, ws = -(-H // sc), -(-W // sc)
            rmap = np.zeros((hs * sc, ws * sc), np.float32)
            rmap[:H, :W] = np.where(keep_id[clab], rad[clab], 0.0)
            rmap = rmap.reshape(hs, sc, ws, sc).max(axis=(1, 3)) / sc
            pm = np.zeros((hs, ws), bool)
            for rr in np.unique(np.round(rmap[rmap > 0])):
                dist = ndi.distance_transform_edt(~((rmap > 0) & (np.round(rmap) == rr)))
                pm |= dist <= rr
            pm = np.repeat(np.repeat(pm, sc, 0), sc, 1)[:H, :W]
            pmp = np.pad(pm, ((0, gh * B - H), (0, gw * B - W)), mode="edge")
            frac = pmp.reshape(gh, B, gw, B).mean(axis=(1, 3))
            star = frac > 0.3
            pad = np.where(pmp[..., None], np.inf, pad)
            with np.errstate(invalid="ignore"):          # 整块被罩 → inf−inf 插值出 nan,下一行换成天空电平
                cell = np.percentile(pad.reshape(gh, B, gw, B, 3), 30, axis=(1, 3))
            cell = np.where(np.isfinite(cell), cell, mode)
    sky_all = sky
    sky = sky & ~star
    if sky.mean() < 0.10:
        if log:
            log("天空局部压平:罩掉亮星后天空不到画面 10%,不动")
        return None
    v = sky.astype(np.float32)                 # 量:只用天空块(亮星块不算)
    # 改:天空里**连亮星块一起**改(值由周围插值),否则星周围一圈没改、邻居改了,反而留一块补丁。
    #   离本体(外扩后)越近改得越少:距离 0 → 0、≥ taper·r_body → 1,免得在保护区边上留台阶(双向改时尤其要)。
    wt = sky_all.astype(np.float32)
    if taper > 0:
        dist = ndi.distance_transform_edt(sky_all)
        wt = (np.clip(dist / max(taper * r_body, 1.0), 0.0, 1.0) * wt).astype(np.float32)
    den = np.maximum(ndi.gaussian_filter(v, SKY_SIGMA, mode="nearest"), 1e-3)
    corr = np.empty_like(cell)
    for c in range(3):
        sm = ndi.gaussian_filter(cell[..., c] * v, SKY_SIGMA, mode="nearest") / den
        dev = sm - float(np.median(sm[sky]))
        corr[..., c] = (dev if two_sided else np.maximum(dev, 0.0)) * wt
        corr[..., c] = ndi.gaussian_filter(corr[..., c], 1.0, mode="nearest")
    cmax = float(np.abs(corr.mean(-1)).max())
    if cmax < SKY_MIN_CORR_SIG * sig:
        if log:
            log("天空局部压平:天空上最大高出 %.3g(< %.1fσ = %.3g),不动" % (cmax, SKY_MIN_CORR_SIG, SKY_MIN_CORR_SIG * sig))
        return None
    out = a.astype(np.float32).copy()
    for c in range(3):
        out[..., c] = np.clip(rgb[..., c] - ndi.zoom(corr[..., c], B, order=1)[:H, :W], 0.0, 1.0)
    XISF.write(str(out_path), out, creator_app="TTAstroPiLot", image_metadata=im_meta, xisf_metadata=f_meta)
    pv = None
    if preview_path:
        try:
            if linear:
                pv = _stf_preview(out, str(preview_path))       # 线性图直接存会是一片黑
            else:
                from . import recombine as _rc
                _rc._save_preview(out[..., :3], str(preview_path))
                pv = str(preview_path)
        except Exception:
            pv = None
    info = {"sky_level": float(mode), "sky_sigma": float(sig), "sky_frac": round(float(sky.mean()), 3),
            "body_r_px": int(r_body * B), "max_corr": float(cmax),
            "corr_p95": float(np.percentile(corr.mean(-1)[sky], 95))}
    if log:
        log("天空局部压平:天空 %.3g(σ %.3g)、本体等效半径 %dpx(外扩后天空占 %.0f%%);天空上最大压掉 %.3g(%.1fσ)、p95 %.3g,本体内不动"
            % (mode, sig, info["body_r_px"], 100 * info["sky_frac"], cmax, cmax / sig, info["corr_p95"]))
    return {"status": "ok", "image": str(out_path), "preview": pv, "applied": info}
