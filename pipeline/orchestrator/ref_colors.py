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
METRIC_VERSION = 2                 # discmetric 口径版本;改了度量就要作废旧缓存
#   v2(2026-09-18):参考定心改天测。v1 建的缓存里可能混进了星点/邻居星系的颜色,
#   全部作废重建(M77 实测 12 张里 7 张量错了对象)。
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
    # 【本体半径用**星表尺寸**锤,不再每张图自己猜(用户 2026-09-17 M31)】
    #   廓线法(降到峰值 10%)只在**天体完整入画**时成立。M31 实测 12/12 参考都没降到
    #   10% → 全部回退到 rmax*0.5 = 纯由取景决定的数(249~810px 乱跳)→ 各自量的不是同一块地方,
    #   各环 R/G 的 σ 高达 **0.96**(M74 只有 0.04~0.14),而聚合出来的"共识"是默的。
    #   交叉验证:M74 廓线法 4.83′ vs 星表 size_major/2 = 5.25′(差 8%)—— 能量的时候两者一致。
    _maj = 0.0
    try:
        _maj = float((info or {}).get("size_major") or 0.0)
    except (TypeError, ValueError):
        _maj = 0.0
    _q = DM.axis_ratio_from_catalog(target)        # 星表轴比 → 椭圆环(面朝星系退化成圆)
    rows, robj, skipped = [], [], 0
    for g in got:
        try:
            a = DM.load_any(g["local_path"])
        except Exception:
            continue
        _asp = _ref_arcsec_px(g, a.shape[1])
        _rpx = ((_maj / 2.0) * 60.0 / _asp) if (_maj > 0 and _asp) else None
        # 【先用天测确认"这张里到底有没有目标、在哪"(2026-09-18 M77)】
        #   同视场检索是按 2° 半径拉的,会把**以邻居为中心**的作品一起拉回来:
        #   M77 实测 12 张里有 4 张的目标期望离心 2611~4251px —— 而画幅才 2560px 宽,
        #   M77 根本不在那些图里(它们是 NGC 1055 的作品)。旧逻辑按亮度找峰,
        #   于是把星点和别的星系的颜色算进了"M77 共识"。
        _off = DM.expected_offset_px(g, float(info["ra"]), float(info["dec"]), _asp) if _asp else None
        _cx, _cy, _ok = DM.find_object(a, _rpx or (min(a.shape[:2]) * 0.2), expect_off_px=_off, log=_log)
        if not _ok:
            skipped += 1
            continue
        # 【图里装不下这个天体就别用(2026-09-17 M31)】M31 的参考里有不少是**局部特写**
        #   (反推出 0.86~1.10″/px → 本体半径 5172~6581px,而画幅半宽才 846~1280)。
        #   它们的"核环"装的根本不是核,而是人家取景到的那一块 —— 混进来就把共识搞脏
        #   (实测核环 R/G 的 σ 0.44)。天体半径超过短边尺寸 = 装不下,整张剔掉。
        if _rpx and _rpx > float(min(a.shape[:2])):
            skipped += 1
            continue
        try:
            m = DM.measure(a, r_obj_px=_rpx, q=_q, center=(_cx, _cy))
        except Exception:
            continue
        if _rpx is None and not m.get("fit"):
            skipped += 1                 # 既没星表锚、廓线也没落到 10% → 这张不可用
            continue
        if not any(m["rings"]):
            skipped += 1
            continue
        rows.append(m["rings"])
        robj.append(m["r_obj"])
    if skipped:
        _log(f"  [参考色] {skipped} 张量不出可比的本体半径(天体溢出画幅且无星表尺寸)→ 已剔除")
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
        # 【两个比值**各自**过闸(2026-09-17 两次调整)】
        #   第一版只查 B/G 的 σ → M31 的 R/G σ 0.96 一路畅通,放过了"这批测量不一致"的报警。
        #   第二版改成"两个都要过" → 又太钝:M31 的盘/外盘 **B/G σ 只有 0.023/0.014**
        #   (7 张参考互相差 1~2%,是四个环里最紧的),却因为 R/G σ 0.228/0.804 被一起丢掉。
        #   R 和 B 本来就是**两条独立的曲线**(pointsR/pointsB),没理由绑在一起。
        #   外盘 R/G 发散而 B/G 紧,本身就是个真实信号:蓝是共识,红是口味。
        _e = {"n": int(len(bg))}
        _e["rg"] = round(float(np.median(rg)), 4) if s_rg <= MAX_SIGMA else None
        _e["rg_sd"] = round(s_rg, 4)
        _e["bg"] = round(float(np.median(bg)), 4) if s_bg <= MAX_SIGMA else None
        _e["bg_sd"] = round(s_bg, 4)
        prof.append(_e if (_e["rg"] is not None or _e["bg"] is not None) else None)
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
        if not p:
            out.append("%s --" % n); continue
        _r = ("R/G %.2f" % p["rg"]) if p.get("rg") is not None else ("R/G --(σ%.2f)" % p.get("rg_sd", 9))
        _b = ("B/G %.2f(σ%.2f)" % (p["bg"], p.get("bg_sd", 0))) if p.get("bg") is not None else ("B/G --(σ%.2f)" % p.get("bg_sd", 9))
        out.append("%s %s %s" % (n, _r, _b))
    return " | ".join(out)


def _ref_arcsec_px(item: dict, width_px: int) -> Optional[float]:
    """从 AstroBin 条目的 fov("0.625° × 0.427°")反推**当前下载尺寸**的角分辨率。
    不能直接用 angular_resolution 字段 —— 那是原图的,而我们下的是 qhd 缩版。"""
    try:
        fov = str(item.get("fov") or "")
        nums = re.findall(r"([\d.]+)", fov)
        if len(nums) >= 1 and width_px:
            return float(nums[0]) * 3600.0 / float(width_px)
    except Exception:
        pass
    return None


# ── 天空亮度共识(用户 2026-10-09 M33「天空亮度也可以参考 AstroBin 的图像」)──────────────────────
#   M33 46 张露得出天空的参考:中位 0.085、四分位 0.077~0.105、p10~p90 0.054~0.117;
#   管线按用户预设中位(背景亮度 ×0.48)压到 0.055 = 参考的 p10。
SKY_VERSION = 1
SKY_VISIBLE_FRAC = 0.8     # 画幅半对角线 > 星表半长轴 × 它,才算露得出天空(特写里「最暗处」是天体外沿)


def sky_level(a) -> tuple[float, list]:
    """一张图的天空亮度(通道均值口径)与天空处 R/G/B。参考与成片**必须用这同一个函数量**。
    块边长 = 宽/80(qhd 2560 → 32px、降采样 1200 → 15px,按画幅等比)→ 每块每通道 p30 压星点
    → 最暗一半块的直方图众数。四角中位会被角落梯度带偏,众数不会。"""
    a = np.asarray(a, dtype=np.float32)
    if a.ndim == 2:
        a = np.stack([a] * 3, -1)
    a = np.clip(a[..., :3], 0.0, 1.0)
    h, w = a.shape[:2]
    B = max(8, w // 80)
    gh, gw = h // B, w // B
    cell = np.percentile(a[:gh * B, :gw * B].reshape(gh, B, gw, B, 3), 30, axis=(1, 3))
    L = cell.mean(-1)
    dark = L[L <= np.percentile(L, 50)]
    hist, ed = np.histogram(dark, bins=60)
    k = int(np.argmax(hist))
    sky = float((ed[k] + ed[k + 1]) / 2)
    near = cell[np.abs(L - sky) < max(0.01, float(ed[1] - ed[0]) * 2)]
    rgb = [float(x) for x in (np.median(near, 0) if len(near) >= 10 else [sky] * 3)]
    return sky, rgb


def sky_target(target: str, refresh: bool = False, limit: int = 16, log=None) -> Optional[dict]:
    """AstroBin 同目标宽带作品的天空亮度共识 {median, q25, q75, n}。拿不到 / 不足 MIN_REFS 张返回 None。"""
    from . import astrobin_ref, dso, discmetric as DM
    _log = log or (lambda *a: None)
    slug = re.sub(r"[^0-9A-Za-z_\-]+", "_", (target or "").strip())[:48] or "unknown"
    cp = CACHE_DIR / f"{slug}_sky.json"
    if not refresh and cp.exists():
        try:
            d = json.loads(cp.read_text(encoding="utf-8"))
            if d.get("version") == SKY_VERSION and time.time() - float(d.get("fetched_at", 0)) < 180 * 86400:
                _log("  [参考天空] %s:命中缓存(%d 张)中位 %.3f、四分位 %.3f~%.3f"
                     % (target, d["n"], d["median"], d["q25"], d["q75"]))
                return d
        except Exception:
            pass
    info = dso.lookup(target or "")
    if not info or info.get("ra") is None:
        _log(f"  [参考天空] 查不到 {target} 的坐标 → 不给目标")
        return None
    try:
        res = astrobin_ref.fetch_similar(float(info["ra"]), float(info["dec"]),
                                         radius=2.0, pagesize=max(16, limit + 4))
    except Exception as e:
        _log(f"  [参考天空] 检索失败({e})→ 不给目标")
        return None
    items = [it for it in (res.get("list") or []) if astrobin_ref.ref_band(it) == "broad"]
    if len(items) < MIN_REFS:
        _log(f"  [参考天空] 同视场宽带只有 {len(items)} 张(<{MIN_REFS})→ 不给目标")
        return None
    try:
        _maj = float(info.get("size_major") or 0.0)
    except (TypeError, ValueError):
        _maj = 0.0
    got = _download_big(items, config.RUN_DIR / "astrobin_sky", limit=limit)
    vals, hidden = [], 0
    for g in got:
        try:
            a = DM.load_any(g["local_path"])
        except Exception:
            continue
        asp = _ref_arcsec_px(g, a.shape[1])
        if _maj > 0 and asp:
            halfdiag = float(np.hypot(*a.shape[:2])) / 2.0 * asp / 60.0
            if halfdiag <= SKY_VISIBLE_FRAC * _maj / 2.0:
                hidden += 1
                continue
        vals.append(sky_level(a)[0])              # load_any 已归一到 0..1
    if hidden:
        _log(f"  [参考天空] {hidden} 张是特写、露不出天空 → 不计")
    if len(vals) < MIN_REFS:
        _log(f"  [参考天空] 量得出的只有 {len(vals)} 张(<{MIN_REFS})→ 不给目标")
        return None
    v = np.array(vals, float)
    d = {"target": target, "version": SKY_VERSION, "fetched_at": time.time(), "n": int(v.size),
         "median": round(float(np.median(v)), 4), "q25": round(float(np.percentile(v, 25)), 4),
         "q75": round(float(np.percentile(v, 75)), 4), "values": [round(float(x), 4) for x in v]}
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    _log("  [参考天空] %s:%d 张 → 中位 %.3f、四分位 %.3f~%.3f" % (target, d["n"], d["median"], d["q25"], d["q75"]))
    return d

