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

W_KNEE = 0.04            # 星点权重拐点:star 亮度 >W_KNEE 即视为纯星点(实测 0.04 最优)
_EPS = 1e-5


def _norm01(a):
    import numpy as np
    a = a.astype(np.float32)
    mx = float(a.max()) if a.size else 1.0
    if mx > 1.5:
        a = a / (65535.0 if mx > 255 else 255.0)
    return a


def chroma_recombine(neb_path: str, stars_path: str, out_path: str,
                     star_amount: float = 1.0, preview_path: str | None = None) -> str:
    """把 stars_path(拉伸好的星点图,黑底)以**色度保持**方式合回 neb_path(去星星云),写 out_path。
    保留 neb 的 xisf 头(色彩空间/WCS/FITS 关键字)。可选出降采样预览 PNG。返回 out_path。"""
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
    Lo = 1.0 - (1.0 - Ln) * (1.0 - Ls)                       # screen 亮度
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
        try:
            from PIL import Image
            h, wd = out.shape[:2]
            s = min(1.0, 1600.0 / max(h, wd))
            im8 = (out * 255.0 + 0.5).astype(np.uint8)
            pim = Image.fromarray(im8, "RGB")
            if s < 1.0:
                pim = pim.resize((max(1, int(wd * s)), max(1, int(h * s))), Image.LANCZOS)
            pim.save(preview_path)
        except Exception:
            pass
    return out_path
