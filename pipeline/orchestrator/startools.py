"""三级去星路由:rc-astro SXT(收费,最优)→ cosmicclarity darkstar(免费 AI)→ StarNet2(免费兜底)。

在**已拉伸 RGB [0,1] 数组**上做;星点层 = 原图 − starless(确定性,避免各家 stars 输出差异)。
各后端读写标准 RGB TIFF(cv2 imwrite 对 3 通道会转正确 RGB 写文件,imread 再 BGR2RGB,自洽不串色);
读回兼容 16bit(cv2)与 32F 浮点 TIFF(cv2 读不了 → tifffile,返回 RGB)。见 [[rcastro-and-setiastro]]。
"""
from __future__ import annotations

import os
import subprocess

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from . import config, siril


def _wr(path: str, rgb01: np.ndarray) -> None:
    cv2.imwrite(path, cv2.cvtColor((np.clip(rgb01, 0, 1) * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))


def _norm(im: np.ndarray) -> np.ndarray:
    if im.dtype == np.uint16:
        f = im.astype(np.float32) / 65535.0
    elif im.dtype == np.uint8:
        f = im.astype(np.float32) / 255.0
    else:
        f = im.astype(np.float32)
        mx = float(f.max()) if f.size else 1.0
        if mx > 1.5:                                   # 非 0-1 浮点(如 0-65535)→ 归一
            f = f / mx
    return np.clip(f, 0, 1)


def _rd(path: str):
    """读回 starless 为 RGB float[0,1]。cv2(BGR,16/8bit)优先;失败用 tifffile(RGB,支持 32F 浮点)。"""
    if not os.path.exists(path):
        return None
    try:
        im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    except Exception:
        im = None
    if im is not None:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2RGB) if im.ndim == 2 else cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        return _norm(im)
    try:                                               # cv2 读不了(常见 32F 浮点 TIFF)→ tifffile(RGB)
        import tifffile
        im = tifffile.imread(path)
        if im.ndim == 2:
            im = np.stack([im] * 3, -1)
        elif im.ndim == 3 and im.shape[0] in (3, 4) and im.shape[0] < im.shape[-1]:
            im = np.moveaxis(im[:3], 0, -1)            # (C,H,W)→(H,W,C)
        return _norm(np.asarray(im)[..., :3])
    except Exception:
        return None


def load_rgb(path: str):
    """读任意 FITS/图像为 RGB float[0,1]。FITS 用 astropy((3,H,W)→(H,W,C));其余走 _rd(cv2/tifffile)。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".fit", ".fits"):
        try:
            from astropy.io import fits
            d = np.asarray(fits.getdata(path), dtype=np.float32)
            if d.ndim == 3 and d.shape[0] <= 4:
                d = np.moveaxis(d, 0, -1)
            elif d.ndim == 2:
                d = np.stack([d] * 3, -1)
            return _norm(d[..., :3])
        except Exception:
            return None
    return _rd(path)


def remove_stars(rgb01: np.ndarray, *, tag: str = "img", s_tile: int = 256,
                 timeout: float = 1800.0, log=print):
    """已拉伸 RGB[0,1] 上三级去星,返回 (starless, stars)。stars=原图−starless(确定性)。
    全无可用后端则抛 RuntimeError(调用方可退回带星流程)。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python(cv2)")
    R = str(config.RUN_DIR)
    src = os.path.join(R, f"_sx_{tag}_in.tif")
    _wr(src, rgb01)
    starless, used = None, None

    try:                                               # ① rc-astro SXT(收费,最优)
        from . import rcastro
        if rcastro.enabled():
            o = os.path.join(R, f"_sx_{tag}_sl_sxt.tif")
            rcastro.sxt(src, o, timeout=timeout, log=log)
            starless = _rd(o)
            used = "rc-astro SXT"
            if starless is None:
                log("[stars] SXT 产物读取失败 → 退 cosmicclarity darkstar")
    except Exception as e:
        log(f"[stars] SXT 失败({repr(e)[:70]})→ 退 cosmicclarity darkstar")

    if starless is None:                               # ② 免费 cosmicclarity darkstar(已拉伸→temp_stretch=False)
        try:
            from . import setiastro
            if setiastro.available():
                o = os.path.join(R, f"_sx_{tag}_sl_ds.tif")
                setiastro.darkstar(src, o, mode="unscreen", path="hybrid_luma_color",
                                   temp_stretch=False, timeout=timeout, log=log)
                starless = _rd(o)
                used = "cosmicclarity darkstar"
                if starless is None:
                    log("[stars] darkstar 产物读取失败 → 退 StarNet2")
        except Exception as e:
            log(f"[stars] darkstar 失败({repr(e)[:70]})→ 退 StarNet2")

    if starless is None:                               # ③ 免费兜底 StarNet2
        sn = siril.starnet_exe()
        if not sn:
            raise RuntimeError("无 rc-astro SXT / cosmicclarity darkstar / StarNet2,无法去星")
        o = os.path.join(R, f"_sx_{tag}_sl_sn.tif")
        subprocess.run([sn, "-i", src, "-o", o, "-s", str(s_tile)],
                       capture_output=True, text=True, timeout=timeout)
        starless = _rd(o)
        if starless is None:
            raise RuntimeError("StarNet2 去星失败(无 starless 输出)")
        used = "StarNet2"

    if starless.shape[:2] != rgb01.shape[:2]:
        starless = cv2.resize(starless, (rgb01.shape[1], rgb01.shape[0]), interpolation=cv2.INTER_LINEAR)
    stars = np.clip(rgb01.astype(np.float32) - starless, 0, 1)
    log(f"[stars] 去星:{used} → starless + stars(原图−starless)")
    return starless.astype(np.float32), stars
