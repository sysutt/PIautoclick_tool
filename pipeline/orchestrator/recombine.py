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

W_KNEE = 0.04            # 星点权重拐点:star 亮度 >W_KNEE 即视为纯星点(实测 0.04 最优)。
                         #   注:孤立测(recomb_test.py)降到 0.015 星区饱和更高(0.500→0.552),但**全流程反效果**
                         #   (M23:s_star 0.267→0.216 且背景变脏)——低拐点把星色度铺到暗弱区、弄脏背景。别再降。
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
                     mode: str = "auto") -> str:
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
    w = np.clip(Ls / W_KNEE, 0.0, 1.0)                        # 星点权重
    Cn = neb / (Ln + _EPS)                                    # 各自色度(去亮度)
    Cs = star / (Ls + _EPS)
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


def neutralize_background(img_path: str, out_path: str, v_bg: float = 0.22,
                          preview_path: str | None = None) -> str:
    """按评分补救·背景中和:把暗背景各通道均值对齐到最低通道(减去 per-channel 偏移)→ 去残留色铸。
    偏移是**加性天光**,全局减最正确;量很小(暗背景),不伤主体色。保 xisf 头。"""
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


def color_nudge(neb_path: str, target_balance, out_path: str, strength: float = 0.5,
                max_dev: float = 0.15, preview_path: str | None = None, log=None) -> str:
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

    cur = quality.signal_balance(neb)
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
