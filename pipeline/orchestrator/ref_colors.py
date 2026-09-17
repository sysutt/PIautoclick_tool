"""按目标缓存 **AstroBin 参考的盘色廓线**(用户 2026-09-17 定的方向)。

用户的原话:"深空摄影的整体审美趋势里,星系盘面偏蓝是个大共识,只有少数星系偏黄或白
(IC342/M104);这些共识可以从 AstroBin 的图像里拿到,很多时候不需要专门去记忆它们。"
—— 这正是不该训模型的理由:**参考自带例外**。IC342/M104 不用维护一张例外清单,
查它们的参考量出来就是黄的。模型能多给的只是"没有参考时的外推",而那恰恰是不该做的
(M31 偏紫那次就是拿不到参考、退回家族均值,把 B 推了 28%,见 [[pi-galaxy-disc-color-target]])。

存什么:每目标、每环的 R/G 与 B/G 的**中位 + σ + 样本数**,外加度量函数版本。
**不存饱和度** —— 参考的 S 中位 0.231、σ 0.051(相对 22%),而色相 σ 只有 5~8%;
饱和度从参考取会发散,继续走我们自己的档(见 [[pi-quality-gate]])。

尺寸:测量抓 **qhd(2560px)**,展示/评委仍用 regular(620px)——
后者是用户为小程序端保护作品版权特意选的档,别拿高清图去做展示或外传。
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

import numpy as np

from . import config

CACHE_DIR = config.PIPELINE_DIR / "_config" / "ref_colors"
METRIC_VERSION = 1                 # discmetric 口径版本;改了度量就要作废旧缓存
MIN_REFS = 5                       # 少于这么多张就不给目标(宁可不推,也不拿几张凑)
MAX_SIGMA = 0.20                   # 某一环的 σ 超过这个 = 参考之间不成共识 → 该环不给目标


def _cache_path(target: str) -> Path:
    slug = re.sub(r"[^0-9A-Za-z_\-]+", "_", (target or "").strip())[:48] or "unknown"
    return CACHE_DIR / f"{slug}.json"


def load_cached(target: str, max_age_days: float = 180.0) -> Optional[dict]:
    """读缓存;不存在/过期/度量版本不符 → None。"""
    p = _cache_path(target)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if int(d.get("metric_version", 0)) != METRIC_VERSION:
        return None
    if (time.time() - float(d.get("fetched_at", 0))) > max_age_days * 86400.0:
        return None
    return d


def _download_big(items: list[dict], out_dir: Path, limit: int = 12) -> list[dict]:
    """按 qhd 下载参考原图(仅本地测量用)。返回 [{meta..., local_path}]。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, it in enumerate(items[:limit]):
        src = (it.get("image_url") or "")
        if not src:
            continue
        src = src.replace("/rawthumb/regular/", "/rawthumb/qhd/")
        if src.startswith("http://"):
            src = "https://" + src[len("http://"):]
        dst = out_dir / f"bigref_{i:02d}.jpg"
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                dst.write_bytes(resp.read())
        except Exception:
            continue
        saved.append({**it, "local_path": str(dst)})
    return saved


def build(target: str, band: str = "broad", limit: int = 12,
          out_dir: Path | None = None, log=None) -> Optional[dict]:
    """拉参考 → 逐张量盘色廓线 → 聚合成目标廓线,写缓存。拿不到/不成共识返回 None。"""
    from . import astrobin_ref, dso, discmetric as DM
    _log = log or (lambda *a: None)
    info = dso.lookup(target or "")
    if not info or info.get("ra") is None:
        _log(f"  [参考色] 查不到 {target} 的坐标 → 不给目标")
        return None
    try:
        res = astrobin_ref.fetch_similar(float(info["ra"]), float(info["dec"]),
                                         radius=2.0, pagesize=max(16, limit + 4))
    except Exception as e:
        _log(f"  [参考色] 检索失败({e})→ 不给目标")
        return None
    items = [it for it in (res.get("list") or []) if astrobin_ref.ref_band(it) == band]
    if len(items) < MIN_REFS:
        _log(f"  [参考色] 同视场同波段只有 {len(items)} 张(<{MIN_REFS})→ 不给目标")
        return None
    out_dir = Path(out_dir or (config.RUN_DIR / "astrobin_big"))
    got = _download_big(items, out_dir, limit=limit)
    rows, robj = [], []
    for g in got:
        try:
            m = DM.measure(DM.load_any(g["local_path"]))
        except Exception:
            continue
        if not any(m["rings"]):
            continue
        rows.append(m["rings"])
        robj.append(m["r_obj"])
    if len(rows) < MIN_REFS:
        _log(f"  [参考色] 量得出的只有 {len(rows)} 张(<{MIN_REFS})→ 不给目标")
        return None
    prof = []
    for i in range(len(DM.BANDS)):
        rg = np.array([r[i]["rg"] for r in rows if r[i]], dtype=float)
        bg = np.array([r[i]["bg"] for r in rows if r[i]], dtype=float)
        if len(bg) < MIN_REFS:
            prof.append(None)
            continue
        # 用中位 + 四分位距估离散:个别参考做得很极端(实测最外环有一张 B/G 3.22),
        # 标准差会被它一个人带走,IQR 不会。
        s_bg = float(np.subtract(*np.percentile(bg, [75, 25]))) / 1.349
        s_rg = float(np.subtract(*np.percentile(rg, [75, 25]))) / 1.349
        if s_bg > MAX_SIGMA:
            prof.append(None)        # 这一环参考之间不成共识 → 不给目标
            continue
        prof.append({"rg": round(float(np.median(rg)), 4), "rg_sd": round(s_rg, 4),
                     "bg": round(float(np.median(bg)), 4), "bg_sd": round(s_bg, 4),
                     "n": int(len(bg))})
    d = {"target": target, "band": band, "metric_version": METRIC_VERSION,
         "fetched_at": time.time(), "n_refs": len(rows),
         "r_obj_px": [round(float(x), 1) for x in robj],
         "bands": list(DM.BAND_NAMES), "profile": prof}
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(target).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    _log("  [参考色] %s:%d 张参考 → %s" % (target, len(rows), fmt(d)))
    return d


def get(target: str, band: str = "broad", refresh: bool = False, log=None) -> Optional[dict]:
    """取目标的参考廓线:先读缓存,没有再拉。"""
    if not refresh:
        d = load_cached(target)
        if d:
            (log or (lambda *a: None))("  [参考色] %s:命中缓存(%d 张)→ %s"
                                       % (target, d.get("n_refs", 0), fmt(d)))
            return d
    return build(target, band=band, log=log)


def fmt(d: dict) -> str:
    from . import discmetric as DM
    out = []
    for n, p in zip(d.get("bands") or DM.BAND_NAMES, d.get("profile") or []):
        out.append("%s R/G %.2f B/G %.2f(σ%.2f)" % (n, p["rg"], p["bg"], p["bg_sd"]) if p else "%s --" % n)
    return " | ".join(out)
