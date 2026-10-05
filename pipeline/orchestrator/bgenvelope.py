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
