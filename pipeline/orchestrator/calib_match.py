"""校准场库**自动匹配**(暗场/偏置场/平场)——跨管线(PixInsight WBPP + Siril)统一逻辑。

用户有一套校准场库(按次整理的暗/偏/平各组文件夹)→ 给定亮场特征(曝光/增益/温度/时间/滤镜/尺寸),
按**统一原则**自动选最匹配的校准场组,免去手动一个个选文件夹。见 [[pi-stacking-engine-roadmap]]。

**匹配原则(用户 2026-08-15 定)**:
  1. **硬性匹配**(必须一致,否则不可用):
     - 暗场 dark = 曝光 + 增益(+ 传感器尺寸)
     - 偏置 bias = 增益(曝光≈0,不比曝光)(+ 尺寸)
     - 平场 flat = 滤镜(+ 尺寸)
  2. 满足硬性匹配后排序取最优:
     - 暗/偏:**温度最接近** → 温度相同则**拍摄时间最接近**
     - 平:**时间最接近** → 时间相同再比温度(平场随灰尘/对焦变、和拍摄时段绑定,时效性 > 温度)

模块只做"挑哪个文件夹",实际整合(make master)交给各管线(Siril=stack_engine.make_master;PI=WBPP)。
"""
from __future__ import annotations

import glob
import os
import re

from . import devices

_CAL_EXTS = (".fit", ".fits", ".fts", ".xisf")
# 各类型的排序键顺序(硬性匹配后):暗/偏 温度优先,平 时间优先
_RANK = {"dark": ("temp", "date"), "bias": ("temp", "date"),
         "flat": ("date", "temp"), "darkflat": ("temp", "date")}


def _first_frame(frame_dir: str) -> str | None:
    for e in _CAL_EXTS:
        fs = sorted(x for x in glob.glob(os.path.join(frame_dir, "*" + e))
                    if not os.path.basename(x).lower().startswith("failed"))
        if fs:
            return fs[0]
    return None


def parse_date(path: str, cards: dict | None = None) -> int | None:
    """拍摄时间 → 可比较整数 YYYYMMDDHHMMSS。FITS `DATE-OBS`(ISO)优先,取不到从文件名/父目录名兜底
    (Seestar `_20260107-032129`、Dwarf `_2026-08-09-00-02-02`)。取不到返回 None。"""
    val = None
    if cards is None:
        try:
            from astropy.io import fits
            cards = dict(fits.getheader(path))
        except Exception:
            cards = {}
    for k in ("DATE-OBS", "DATE_OBS", "DATE-LOC", "DATE"):
        if cards.get(k):
            val = str(cards[k])
            break
    text = val or (os.path.basename(path) + " " + os.path.basename(os.path.dirname(path)))
    # 抓 年 月 日 [时 分 秒](分隔符任意:- : T _ 空 或无)
    m = re.search(r"(\d{4})\D?(\d{2})\D?(\d{2})[\D_T ]{0,3}(\d{2})\D?(\d{2})\D?(\d{2})", text)
    if not m:
        m2 = re.search(r"(\d{4})\D?(\d{2})\D?(\d{2})", text)          # 只有日期
        if m2:
            return int(m2.group(1) + m2.group(2) + m2.group(3) + "000000")
        return None
    return int("".join(m.groups()))


def group_meta(frame_dir: str) -> dict | None:
    """一个校准场文件夹 → 组元数据。用首帧 devices.classify(类型/曝光/增益/温度/滤镜/尺寸)+ parse_date。"""
    f = _first_frame(frame_dir)
    if not f:
        return None
    try:
        c = devices.classify(f)
    except Exception:
        return None
    n = len([x for e in _CAL_EXTS for x in glob.glob(os.path.join(frame_dir, "*" + e))])
    return {"dir": frame_dir.replace("\\", "/"), "kind": c.get("type"), "exp": c.get("exp"),
            "gain": c.get("gain"), "temp": c.get("temp"), "filter": c.get("filter"),
            "width": c.get("width"), "height": c.get("height"), "date": parse_date(f), "count": n}


def scan_library(root: str, *, max_depth: int = 4, log=print) -> list[dict]:
    """扫描校准场库根目录 → 所有**校准场组**(dark/bias/flat/darkflat)。按"含校准帧的叶子文件夹"分组:
    每个直接含 FITS 的目录取首帧分类,类型为暗/偏/平才收。返回组元数据列表。"""
    root = str(root).replace("\\", "/")
    groups: list[dict] = []
    seen = set()
    for dp, _dn, fn in os.walk(root):
        depth = dp.replace("\\", "/").count("/") - root.count("/")
        if depth > max_depth:
            continue
        if not any(f.lower().endswith(_CAL_EXTS) for f in fn):
            continue
        g = group_meta(dp)
        if g and g["kind"] in ("dark", "bias", "flat", "darkflat") and g["dir"] not in seen:
            seen.add(g["dir"])
            groups.append(g)
    log(f"[calib] 校准场库扫描:{len(groups)} 组("
        + ", ".join(f"{k}×{sum(1 for g in groups if g['kind'] == k)}"
                    for k in ("dark", "bias", "flat", "darkflat") if any(g['kind'] == k for g in groups))
        + f");根={root}")
    return groups


def _dims_ok(light: dict, g: dict) -> bool:
    lw, lh, gw, gh = light.get("width"), light.get("height"), g.get("width"), g.get("height")
    if lw and lh and gw and gh:
        return lw == gw and lh == gh
    return True                                                     # 尺寸未知不拦


def _hard_ok(light: dict, g: dict, kind: str) -> bool:
    """硬性匹配:暗=曝光+增益;偏=增益;平=滤镜。都要尺寸一致(同传感器)。"""
    if not _dims_ok(light, g):
        return False
    le, lg, lf = light.get("exp"), light.get("gain"), light.get("filter")
    ge, gg, gf = g.get("exp"), g.get("gain"), g.get("filter")
    if kind in ("dark", "darkflat"):
        if le is not None and ge is not None and abs(le - ge) > 0.5:
            return False
        if lg is not None and gg is not None and lg != gg:
            return False
    elif kind == "bias":
        if lg is not None and gg is not None and lg != gg:
            return False
    elif kind == "flat":
        if lf and gf and str(lf).lower() != str(gf).lower():
            return False
    return True


def _diff(a, b, big: float) -> float:
    return abs(a - b) if (a is not None and b is not None) else big


def match(light: dict, groups: list[dict], kind: str, *, log=print) -> dict | None:
    """按原则选最匹配的校准组。light={exp,gain,temp,date,filter,width,height}。返回组 dict 或 None。
    暗/偏:温度→时间;平:时间→温度(见 _RANK)。"""
    cands = [g for g in groups if g.get("kind") == kind and _hard_ok(light, g, kind)]
    if not cands:
        return None
    order = _RANK.get(kind, ("temp", "date"))

    def keyf(g):
        dt = _diff(g.get("temp"), light.get("temp"), 1e6)
        dd = _diff(g.get("date"), light.get("date"), 1e18)
        vals = {"temp": dt, "date": dd}
        return tuple(vals[o] for o in order)
    cands.sort(key=keyf)
    b = cands[0]
    dt = _diff(b.get("temp"), light.get("temp"), None)
    dd = _diff(b.get("date"), light.get("date"), None)
    log(f"[calib] {kind} 自动匹配:{os.path.basename(b['dir'])}"
        f"(温差{'?' if dt is None else f'{dt:.0f}°'} 时差{'?' if dd is None else '近'};{len(cands)} 组候选)")
    return b


def auto_calib(library_root: str, light: dict, kinds=("dark",), *, log=print) -> dict:
    """便捷:扫库 + 为每种 kind 匹配。返回 {kind: 组 dict}(未匹配到的 kind 不在)。
    light 可传亮场目录(自动读首帧元数据)或已有 meta dict。"""
    if isinstance(light, str):
        f = _first_frame(light)
        light = group_meta(light) or {}
    groups = scan_library(library_root, log=log)
    out = {}
    for k in kinds:
        g = match(light, groups, k, log=log)
        if g:
            out[k] = g
    return out
