"""调色经验库:每次在调色面板点「就这样」,存一份这一组的**调前 / 调后**全幅图 + 主体放大图、
测量数值、滑块值、曲线控制点和一句「为什么这么调」(用户 2026-09-25)。

为什么要存图,而不是只存滑块值:滑块值是「这张图这次拉伸」的属性,换一张底图就不成立
(M64 同一组预设换一轮跑,盘面饱和 0.131 → 0.328,见 [[pi-sliders-not-transferable]])。
能迁移给自动调色(LLM)的是「看到什么 → 怎么调 → 变成什么」,再加上**原因**:同样把背景压暗,
是因为有竖条纹、蒙版漏光,还是纯口味,下一次该不该照做完全不同。
以前各目标调前的底图都在 `_run` 里被覆盖了、补不回来,所以只能从现在开始存。

目录:`<root>/<预设键>/<时间戳>/` 下 before_full.jpg / after_full.jpg / before_body.jpg /
after_body.jpg / sample.json。图用 JPEG q92 **4:4:4**(与 critic._encode 同参数:4:2:0 会把星点色度糊掉)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

VERSION = 1
BODY_CROP_MIN, BODY_CROP_MAX = 384, 1400      # 主体放大图边长(全分辨率像素)
BODY_CROP_RADII = 3.2                         # 边长 = 3.2 × 本体半径(本体外沿再留一圈外晕)


def apply_panel(a, prm, x0: int = 0, y0: int = 0, src_w=None, src_h=None):
    """把调色面板的一组变换施加到 a(0..1 浮点 RGB;源图上从 (x0, y0) 起的一块,源图 src_w × src_h)。

    纯 numpy、线程安全。**放大镜实时预览(app_ui._col_adjust_crop)和经验库的「调后」都走这里**
    —— 同一个变换只写一处,否则存下来的「调后」会和你在放大镜里看到的不一样。
    prm 来自 app_ui._col_adjust_params():{pts, bpts, use_mask, mask(预览分辨率), ct}。
    蒙版按预览分辨率那张**双线性取样**到这块的坐标(蒙版是高斯羽化的平滑场,放大后误差远小于一个像素级
    可见量;2026-09-23 实测与「整图调好再裁」RMSE 0.0019)。块与蒙版同尺寸且从原点起时直接用,不插值。
    """
    import numpy as np
    from . import galaxycolor as gc
    pts = prm.get("pts") or {}
    bpts = prm.get("bpts") or {}
    ct = prm.get("ct")
    if not pts and not bpts:
        return a
    h, w = a.shape[:2]
    src_w = src_w or w
    src_h = src_h or h
    out = (gc.apply_curves_np(a, pts.get("pointsR"), pts.get("pointsG"),
                              pts.get("pointsB"), pts.get("pointsS"), curve_type=ct)
           if pts else a)
    mk = None
    mfull = prm.get("mask")
    if ((pts and prm.get("use_mask")) or bpts) and mfull is not None:
        if mfull.shape[:2] == (h, w) and x0 == 0 and y0 == 0:
            mk = np.clip(mfull, 0.0, 1.0)
        else:
            from scipy.ndimage import map_coordinates
            sy = mfull.shape[0] / float(max(src_h, 1))
            sx = mfull.shape[1] / float(max(src_w, 1))
            gy, gx = np.meshgrid((np.arange(h) + y0) * sy, (np.arange(w) + x0) * sx, indexing="ij")
            mk = np.clip(map_coordinates(mfull, [gy, gx], order=1, mode="nearest"), 0.0, 1.0)
    if pts and prm.get("use_mask") and mk is not None:
        out = a + (out - a) * mk[..., None]
    if bpts and mk is not None:
        b = gc.apply_curves_np(out, None, None, None, bpts.get("pointsS"), curve_type=ct)
        if bpts.get("points"):
            b = gc.apply_curves_np(b, bpts["points"], bpts["points"], bpts["points"], curve_type=ct)
        out = out + (b - out) * (1.0 - mk)[..., None]
    return out


def _js(x):
    """numpy / tuple → 可写 JSON 的纯 Python。"""
    import numpy as np
    if isinstance(x, dict):
        return {str(k): _js(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_js(v) for v in x]
    if isinstance(x, np.ndarray):
        return _js(x.tolist())
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, float):
        return round(x, 4)
    return x


def measure(img, mask=None) -> dict:
    """一张(预览分辨率)图的调色相关测量。调前/调后用**同一张蒙版**,才是同一块区域上的对比。

    背景区按半径圈(>3 倍本体半径,太小再退到 1.6 倍),不按亮度圈 —— 按亮度会把蒙版真正漏出去的
    亮斑块排除在外(「取样集合由被测量本身定义」,当天栽过四次)。背景电平用直方图众数。
    """
    import numpy as np
    from . import galaxycolor as gc, recombine as rc
    a = np.clip(np.asarray(img, dtype=np.float64)[..., :3], 0.0, 1.0)
    H, W = a.shape[:2]
    cx, cy = gc.find_center(a)
    r0 = float(gc.body_radius(a))
    yy, xx = np.ogrid[:H, :W]
    d = np.hypot(yy - cy, xx - cx)
    far = d > 3.0 * r0
    if far.sum() < 2000:
        far = d > 1.6 * r0
    mx = a.max(-1)
    sat = np.where(mx > 1e-6, (mx - a.min(-1)) / np.maximum(mx, 1e-6), 0.0)
    lvl = [float(rc._sky_mode(a[..., c][far])) for c in range(3)]
    has_mask = mask is not None and tuple(mask.shape[:2]) == (H, W)
    body = (mask > 0.5) if has_mask else (d < r0)
    if body.sum() < 50:
        body = d < max(r0, 5.0)
    sig = np.median(a[body], axis=0) - np.asarray(lvl)
    out = {"center": [int(cx), int(cy)], "body_radius": r0,
           "bg": {"level": lvl, "sat": float(np.median(sat[far]))},
           "body": {"sat": float(np.median(sat[body])), "px": int(body.sum()),
                    "rg": (float(sig[0] / sig[1]) if sig[1] > 1e-4 else None),
                    "bg": (float(sig[2] / sig[1]) if sig[1] > 1e-4 else None)}}
    try:
        wp = gc.warm_profile(a, r0)
        if wp:
            out["profile"] = {k: wp.get(k) for k in ("bins", "rg", "bg", "sat", "peak", "peak_pos")}
    except Exception:
        pass
    if has_mask:
        try:
            cv = gc.mask_body_coverage(a, mask)
            out["mask"] = {"cover": cv.get("body_med"), "area": cv.get("area_gt50"),
                           "leak": gc.mask_leak(a, mask).get("leak")}
        except Exception:
            pass
    return _js(out)


def _save_jpeg(arr, path):
    import numpy as np
    from PIL import Image
    u8 = (np.clip(np.asarray(arr)[..., :3], 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(u8).save(str(path), format="JPEG", quality=92, subsampling=0)


def _read_full(path):
    """全分辨率 XISF → 0..1 浮点 RGB(整型按位深归一)。"""
    import numpy as np
    from xisf import XISF
    a = np.asarray(XISF(str(path)).read_image(0))
    if np.issubdtype(a.dtype, np.integer):
        a = a.astype(np.float32) / float(np.iinfo(a.dtype).max)
    else:
        a = np.clip(a.astype(np.float32), 0.0, 1.0)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    return a[..., :3]


def capture(root, prm, base, full, rec, reason: str = "", vals=None, bg=None) -> dict:
    """存一份经验。base = 面板那张预览分辨率底图(调前);full = 同一张的全分辨率 XISF 路径。

    主体放大图从**全分辨率**裁(放大镜能看到的细节,LLM 才能看到);调后那张用 apply_panel,
    与放大镜同一个变换。返回 {dir, files, measure}。"""
    import numpy as np
    from . import galaxycolor as gc
    key = str((rec or {}).get("key") or "").strip()
    if not key:
        raise ValueError("预设没有键,不知道归到哪个目标")
    safe = re.sub(r"[^A-Za-z0-9@+\-_.]", "_", key)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    d = Path(root) / safe / stamp
    d.mkdir(parents=True, exist_ok=True)

    b = np.clip(np.asarray(base, dtype=np.float64)[..., :3], 0.0, 1.0)
    h, w = b.shape[:2]
    after = apply_panel(b, prm, 0, 0, w, h)
    _save_jpeg(b, d / "before_full.jpg")
    _save_jpeg(after, d / "after_full.jpg")
    files = {"before_full": "before_full.jpg", "after_full": "after_full.jpg"}

    mask = prm.get("mask")
    meas = {"before": measure(b, mask), "after": measure(after, mask)}

    src = {"image": str(full or ""), "preview_size": [w, h]}
    if full and Path(str(full)).exists():
        try:
            fa = _read_full(full)
            FH, FW = fa.shape[:2]
            s = FW / float(w)
            cx, cy = gc.find_center(b)
            r0 = float(gc.body_radius(b))
            side = int(np.clip(BODY_CROP_RADII * r0 * s, BODY_CROP_MIN, min(BODY_CROP_MAX, FW, FH)))
            x0 = int(np.clip(cx * s - side / 2, 0, FW - side))
            y0 = int(np.clip(cy * s - side / 2, 0, FH - side))
            crop = fa[y0:y0 + side, x0:x0 + side].astype(np.float64)
            _save_jpeg(crop, d / "before_body.jpg")
            _save_jpeg(apply_panel(crop, prm, x0, y0, FW, FH), d / "after_body.jpg")
            files.update(before_body="before_body.jpg", after_body="after_body.jpg")
            src.update(full_size=[FW, FH], body_box=[x0, y0, side])
        except Exception as e:
            src["body_error"] = str(e)[:200]

    sample = {"version": VERSION, "saved": datetime.now().isoformat(timespec="seconds"),
              "target": (rec or {}).get("target"), "key": key, "pos": (rec or {}).get("pos"),
              "reason": (reason or "").strip(), "vals": vals or (rec or {}).get("vals"),
              "bg_anchor": bg, "curve_type": prm.get("ct"), "use_mask": bool(prm.get("use_mask")),
              "points": prm.get("pts") or {}, "bg_points": prm.get("bpts") or {},
              "source": src, "measure": meas, "files": files}
    (d / "sample.json").write_text(json.dumps(_js(sample), ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return {"dir": str(d), "files": files, "measure": meas}


def list_samples(root) -> list[dict]:
    """列出经验库里所有样本(新的在前)。给以后的自动调色读。"""
    out = []
    for p in sorted(Path(root).glob("*/*/sample.json"), reverse=True):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
            s["_dir"] = str(p.parent)
            out.append(s)
        except Exception:
            continue
    return out
