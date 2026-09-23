# -*- coding: utf-8 -*-
"""手动调色面板的**参数预设**:记下用户亲手调定的那一组,下次预填面板,并让全自动路照着跑。

缘起(用户 2026-09-21):
  "在我完成手动参数的处理后,你可以记录下这个参数,作为预设值。另外现在自动调色的管线
   也可以参照我调整的数值来修改,现在自动调色跑出来的颜色相当糟糕。"

【单一真源】"滑块数值 → 曲线控制点" 的换算只写在这里,GUI 实时预览 / GUI 最终应用 /
  全自动管线三处都调它(同类教训见记忆 pi-quality-gate 的"单一真源 quality.s_star_band")。

【⚠ 这不等于旧自动链修好了】我一开始把"自动调色很糟"诊断成"自动(AstroBin 盘色共识
  r11f_disccolor + 自有基准 r15_housecolor)和手动是两套机制,所以对不上"。**用户否掉了
  这个定性**:"即使是按照 AstroBin 共识 + 自有基准,调出来的颜色也不应该是我现在看到的
  那样。所以这里面的逻辑是有大问题的,需要全部大改。"
  → 本模块只是把旧链**整条绕过去**,旧链的缺陷一个都没查。等用户手动结果出来要回头重做。
  想强制走回旧链做对照诊断:设 color_preset_auto=false(否则一存预设就再也触发不到它)。

存盘位置:config.CONFIG_DIR/color_presets.json —— 跟 settings.json 同级,不在 `_run` 下
  (`_run` 会被 housekeep 按天清理,预设必须活得比它久)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from . import config

# 面板滑块的默认位置(= 什么都不改)。键名与 app_ui 的滑块 key 一一对应。
DEFAULTS: dict[str, float] = {
    "r": 1.0, "g": 1.0, "b": 1.0,      # 三通道两点曲线的增益(背景锚点固定)
    "x2": 0.25,                        # 第二控制点的作用亮度
    "sat": 1.0,                        # 主体饱和
    "bgsat": 1.0, "bglum": 1.0,        # 背景侧(蒙版补集):饱和 / 亮度
    "mask": 0.30,                      # 主体蒙版收紧度(= lum_sat_mask 的 body_frac)
}


def _store():
    return config.CONFIG_DIR / "color_presets.json"


def _key(target: str) -> str:
    return (target or "").strip().upper().replace(" ", "")


_DESIG_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(NGC|PGC|UGC|IC|SH2|ABELL|M)[ _-]{0,2}(\d{1,4})(?![0-9])",
    re.IGNORECASE)


def designation(text: str | None) -> str:
    """从一段自由文本里认出**第一个**星表编号,如 `M81` / `NGC2403`;认不出返回空串。

    【为什么需要它(用户 2026-09-22 M81)】预设的键本该是 FITS 的 `OBJECT`,但
    **智能望远镜不保证写这个关键字** —— M33 那份有 `OBJECT='M 33'`,M81 这份是 None。
    读不到就退回界面上的"项目目录",而那是 `251016-251116_D3_M81_M82` 这种带日期/器材/
    多目标的字符串:换个目录同一天体就取不回来了。
    只认带前缀的编号,所以目录名里的日期段(251016)不会误命中;多目标取第一个。
    **认不出就返回空,别猜** —— 拼一个错键出来比没有键更糟(会污染别的目标)。
    """
    m = _DESIG_RE.search(str(text or ""))
    return (m.group(1) + m.group(2)).upper() if m else ""


def curve_type() -> str:
    """面板预览与落盘共用的插值方式 —— 必须与 protocol._curve_type_policy 给出的一致。"""
    try:
        from . import config
        return "akima" if bool(config.get_setting("curves_akima", False)) else "cubic"
    except Exception:
        return "cubic"


def _read() -> dict[str, Any]:
    p = _store()
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write(d: dict[str, Any]) -> None:
    p = _store()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # 【写前留一代(2026-09-23)】用户亲手调的参数是**几十分钟的人工**,这个文件里
        #   每一条都补不回来(这天已经被误覆盖两次:一次是天体名认错,一次是我自己的测试脚本)。
        #   留一份 .prev 成本近乎为零,能救整轮工作。
        if p.exists():
            try:
                p.with_suffix(".json.prev").write_text(
                    p.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def clean(vals) -> dict[str, float]:
    """只留认识的键、转成 float、缺的补默认 —— 存进来和读出去都过这一道。"""
    out = dict(DEFAULTS)
    for k, v in (vals or {}).items():
        if k in DEFAULTS and v is not None:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                pass
    return out


SAME_FIELD_DEG = 0.5      # 同一天区的判定半径(度);智能望远镜视场都比这大不了多少


def _sep_deg(a, b) -> float | None:
    """两个 (ra, dec) 的角距(度)。任一为空则返回 None = 判不了。"""
    if not a or not b or a[0] is None or b[0] is None:
        return None
    import math
    ra1, de1, ra2, de2 = (math.radians(float(x)) for x in (a[0], a[1], b[0], b[1]))
    v = (math.sin(de1) * math.sin(de2)
         + math.cos(de1) * math.cos(de2) * math.cos(ra1 - ra2))
    return math.degrees(math.acos(max(-1.0, min(1.0, v))))


def save(target: str | None, vals, bg=None, note: str = "", pos=None) -> dict[str, Any]:
    """记下这一组。同时写 `last`(跨目标的默认预设)和 `targets[目标]`(本目标专用)。

    【★位置闸(用户 2026-09-23 M51 事故)】天体名是从 FITS/目录名**猜**出来的,猜错就会
    **把另一个目标的预设直接覆盖掉** —— 实测 M51 调完存进了 `M81`,把二十分钟前刚调好的
    M81 抹了(靠 done/ 里的曲线控制点才反解回来)。
    → 存盘时带上 `pos=(ra,dec)`:目标键已存在、且**两者都有坐标、相距超过 0.5°** 时
      **拒绝覆盖**,改存到带坐标后缀的键上,并在返回值里给 `conflict` 让调用方响亮报出来。
    名字猜错最多是多一条记录,再也不会丢数据。
    """
    rec = {"vals": clean(vals), "bg": (float(bg) if bg is not None else None),
           "saved": datetime.now().isoformat(timespec="seconds"),
           "target": (target or "").strip(), "note": note,
           "pos": ([float(pos[0]), float(pos[1])] if pos and pos[0] is not None else None)}
    d = _read()
    d["last"] = rec
    k = _key(target or "")
    if k:
        tg = d.setdefault("targets", {})
        old = tg.get(k) or {}
        sep = _sep_deg(rec.get("pos"), old.get("pos"))
        # 旧记录没存坐标(早期版本写的)→ **判不了就别赌**:同样改存新键,别把它抹掉。
        #   实测就是栽在这里:M51 那条刚补回来、还没有坐标,闸直接放行。
        if sep is None and rec.get("pos") and old and not old.get("pos"):
            sep = float("inf")
        if sep is not None and sep > SAME_FIELD_DEG:
            k2 = "%s@%+.2f%+.2f" % (k, rec["pos"][0], rec["pos"][1])
            rec["conflict"] = (
                "键「%s」上已有%s(存于 %s)→ 没有覆盖它,这一组改存到「%s」。"
                "多半是天体名认错了,建议核对项目目录/OBJECT。"
                % (k,
                   ("另一个天区的记录,相距 %.1f°" % sep) if sep != float("inf")
                   else "一条没存坐标、判不出同不同天区的记录",
                   old.get("saved"), k2))
            k = k2
        tg[k] = rec
        rec["key"] = k
    _write(d)
    return rec


def get(target: str | None = None, fallback_last: bool = True, pos=None):
    """取预设:先找本目标专用的,没有再退到最近一次(`last`)。

    返回里带 `source`:"target"=这个目标自己调过,"last"=借用最近一次调的另一个目标。
    调用方**必须把 source 打进日志** —— 借来的那组是"上次在别的目标上满意的档",
    不是对本目标的测量结论,两者可信度不同,不能混为一谈。
    """
    d = _read()
    tg = d.get("targets") if isinstance(d.get("targets"), dict) else {}
    # 两个候选键:原文(`M31_ALL` 这种自定义名要能精确命中)和抠出来的星表编号
    #   (`251016-251116_D3_M81_M82` → `M81`)。**两个都命中时取存得更晚的那条** ——
    #   老库里可能还留着按整段目录名存的旧记录,按顺序取会让它盖住新的。
    hits = []
    for k in (_key(target or ""), _key(designation(target))):
        if k and k in tg and not any(h[1] == k for h in hits):
            hits.append((str((tg[k] or {}).get("saved") or ""), k))
    if hits:
        rec = dict(tg[max(hits)[1]]); rec["source"] = "target"
        return rec
    # 名字命不中就按**天区坐标**找 —— 名字是猜的,坐标不是。
    if pos and pos[0] is not None:
        hit = [(s2, kk) for kk, rr in tg.items()
               for s2 in [_sep_deg(pos, (rr or {}).get("pos"))]
               if s2 is not None and s2 <= SAME_FIELD_DEG]
        if hit:
            rec = dict(tg[min(hit)[1]]); rec["source"] = "pos"
            return rec
    if fallback_last and isinstance(d.get("last"), dict):
        rec = dict(d["last"]); rec["source"] = "last"
        return rec
    return None


def forget(target: str | None = None) -> None:
    """删掉某个目标的预设(不传 target 则连 `last` 一起清空)。"""
    d = _read()
    if target:
        if isinstance(d.get("targets"), dict):
            d["targets"].pop(_key(target), None)
    else:
        d = {}
    _write(d)


# ── 滑块 → 曲线控制点(唯一实现;GUI 与管线共用)──────────────────────────────
def curves_for(vals, bg=None) -> dict[str, Any]:
    """主体侧:三通道两点曲线(都钉在背景锚点)+ 饱和曲线。"""
    from . import galaxycolor as gc
    v = clean(vals)
    b = float(bg) if bg is not None else 0.09     # 没标定背景就用典型成片电平兜底
    out: dict[str, Any] = {}
    for ch, key in (("R", "r"), ("G", "g"), ("B", "b")):
        gain = v[key]
        if abs(gain - 1.0) > 1e-4:
            out["points" + ch] = gc.two_point_curve(b, v["x2"], gain)
    sc = gc.sat_curve(v["sat"])
    if sc:
        out["pointsS"] = sc
    return out


def bg_curves_for(vals, bg=None) -> dict[str, Any]:
    """背景侧(蒙版补集):压饱和 + 压亮度。两者都以 1.0 为"不动"。"""
    from . import galaxycolor as gc
    v = clean(vals)
    b = float(bg) if bg is not None else 0.09
    out: dict[str, Any] = {}
    if v["bgsat"] < 0.999:
        sc = gc.sat_curve(v["bgsat"])
        if sc:
            out["pointsS"] = sc
    if v["bglum"] < 0.999:
        # 压亮度只压**背景电平附近**,高光钉在 1.0 不动 —— 否则落在背景里的星点会被一起压没。
        x = max(0.02, min(0.9, b))
        out["points"] = [[0.0, 0.0], [round(x, 5), round(max(0.0, x * v["bglum"]), 5)], [1.0, 1.0]]
    return out


def describe(vals) -> str:
    """一行人话,给日志用。只报**真的动了**的那几项。"""
    v = clean(vals)
    seg = []
    for k, lab in (("r", "R"), ("g", "G"), ("b", "B")):
        if abs(v[k] - 1.0) > 1e-4:
            seg.append("%s%+.0f%%" % (lab, (v[k] - 1.0) * 100.0))
    if abs(v["sat"] - 1.0) > 1e-4:
        seg.append("饱和%+.0f%%" % ((v["sat"] - 1.0) * 100.0))
    if v["bgsat"] < 0.999:
        seg.append("背景饱和%.0f%%" % (v["bgsat"] * 100.0))
    if v["bglum"] < 0.999:
        seg.append("背景亮度%.0f%%" % (v["bglum"] * 100.0))
    seg.append("作用亮度%.2f" % v["x2"])
    seg.append("蒙版%.2f" % v["mask"])
    return " / ".join(seg) if seg else "(全在原位)"

# ── 自动定其余:蒙版 / 背景侧 / 饱和 ─────────────────────────────────────────────
# 【为什么能自动(用户 2026-09-23)】八个滑块里跨目标真正在变的**只有蓝增益**(1.01~1.07),
#   而且那 6% 跨度里还有一大半是"锚点不同导致的不可比"(两点曲线绕背景锚点转,五个样本的
#   锚点是 0.09/0.1503/0.183/现测/0.1752)。其余六个要么几乎不动,要么**有可测的目标**:
#     · 蒙版  —— 有正确答案、不是审美:它该盖住本体、又别漏进背景 → 解一个最优化,不设拍脑袋阈值
#     · 饱和  —— 目标是盘饱和,可直接量出来后二分求解
#     · 背景侧/r/g/x2 —— 用户自己五组选择的中位(数据驱动的默认值,不是我编的)
#   这样每补一个样本的成本从"调八个滑块"降到"只定盘色"。
DISC_SAT_TARGET = 0.20      # 盘饱和目标:用户自有库中位 0.207(范围 0.123~0.273),
                            #   与最近两次干净成片(M51 自动 ~0.20 / M64 0.17)一致
MASK_LEAK_MAX = 0.02        # 背景里蒙版 >0.5 的**占比**上限(不是中位数,见 solve_mask)


def _preset_medians() -> dict:
    """用户已存的各组取中位,当"几乎不动"的那几个滑块的默认值。"""
    import statistics as _st
    d = _read()
    rows = [(r or {}).get("vals") or {} for r in (d.get("targets") or {}).values()]
    rows = [clean(v) for v in rows if v]
    out = dict(DEFAULTS)
    if not rows:
        return out
    for k in DEFAULTS:
        try:
            out[k] = float(_st.median([float(v[k]) for v in rows if v.get(k) is not None]))
        except Exception:
            pass
    return out


def solve_mask(img, bg, lo: float = 0.10, hi: float = 0.85, steps: int = 16) -> dict:
    """解蒙版收紧度:**盖住本体最多、同时漏进背景不超过 MASK_LEAK_MAX**。

    不设"覆盖率该是多少"这种拍脑袋的目标 —— 那个数我标定不了。这里解的是一个有明确
    物理意义的取舍:本体要被盖住(否则背景侧滑块会削到星系,M64 实测覆盖 1% 时外盘饱和被乘 0.38),
    背景不能被盖住(否则背景的噪声和色斑跟着一起提饱和)。两者都能直接量,所以是最优化不是猜。
    """
    from . import galaxycolor as gc
    import numpy as np
    a = np.asarray(img, dtype=np.float32)
    # 漏出一律走 galaxycolor.mask_leak(单一真源,口径见那个函数)。
    # 【两遍扫,别写成边走边比(2026-09-23 自己踩的坑)】先收集全部候选,再挑 ——
    #   写成"每一步跟上一个比、差在 0.01 内就接受"会变成**棘轮**:沿缓降的覆盖率曲线
    #   一路滑下去,实测从 0.10 一直走到 0.25(覆盖 80%→41%)。并列判断必须对**全局最优**做。
    cand = []
    for i in range(steps):
        f = lo + (hi - lo) * i / float(steps - 1)
        mk, _ = gc.lum_sat_mask_array(a, bg=bg, body_frac=f)
        cv = gc.mask_body_coverage(a, mk)
        if not cv:
            continue
        leak = float(gc.mask_leak(a, mk).get("leak") or 0.0)
        if leak > MASK_LEAK_MAX:
            continue
        cand.append({"mask": round(f, 3), "coverage": float(cv.get("body_med") or 0.0),
                     "leak": leak})
    best = None
    if cand:
        top = max(c["coverage"] for c in cand)
        # 覆盖在最优的 0.01 以内算并列 → 其中取**最大**的收紧度(同样覆盖、蒙版更挑;
        #   覆盖会在某档触顶后不再变化,因为再往下 `mid` 撞 clip+0.01 的夹子)。
        best = max((c for c in cand if c["coverage"] >= top - 0.01), key=lambda c: c["mask"])
    if best is None:                                # 全都漏 → 取最紧的一档
        mk, _ = gc.lum_sat_mask_array(a, bg=bg, body_frac=hi)
        cv = gc.mask_body_coverage(a, mk) or {}
        best = {"mask": hi, "coverage": float(cv.get("body_med") or 0.0),
                "leak": float(gc.mask_leak(a, mk).get("leak") or 0.0),
                "note": "所有档位都会漏进背景 → 取最紧的一档"}
    return best


def solve_sat(img, bg, vals, target: float = DISC_SAT_TARGET,
              lo: float = 1.0, hi: float = 10.0, iters: int = 12) -> dict:
    """二分求饱和增益,让**内盘(0.10~0.45 本体半径)的饱和**落到 target。

    饱和是"绕中性点放大"的那一步,所以必须在 r/g/b 定完之后解 —— 换了盘色要重解。
    """
    from . import galaxycolor as gc
    import numpy as np
    a = np.asarray(img, dtype=np.float64)
    mk, _ = gc.lum_sat_mask_array(np.asarray(img, np.float32), bg=bg,
                                  body_frac=float(vals.get("mask", 0.30)))
    cx, cy = gc.find_center(a)
    r0 = gc.body_radius(a)
    yy, xx = np.ogrid[:a.shape[0], :a.shape[1]]
    rr = np.hypot(yy - cy, xx - cx)
    band = (rr >= 0.10 * r0) & (rr < 0.45 * r0)
    ct = curve_type()

    def disc_sat(g):
        v = dict(vals); v["sat"] = g
        cur = curves_for(v, bg)
        o = gc.apply_curves_np(a, cur.get("pointsR"), cur.get("pointsG"),
                               cur.get("pointsB"), cur.get("pointsS"), curve_type=ct)
        o = a + (o - a) * mk[..., None]
        mx = o[..., :3].max(-1)
        return float(np.median(((mx - o[..., :3].min(-1)) / np.maximum(mx, 1e-9))[band]))

    slo, shi = disc_sat(lo), disc_sat(hi)
    if slo >= target:
        return {"sat": lo, "disc_sat": round(slo, 4), "note": "不提饱和就已达标"}
    if shi <= target:
        return {"sat": hi, "disc_sat": round(shi, 4), "note": "推到上限仍不到目标"}
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if disc_sat(mid) < target:
            lo = mid
        else:
            hi = mid
    g = 0.5 * (lo + hi)
    return {"sat": round(g, 2), "disc_sat": round(disc_sat(g), 4)}


def auto_solve(img, bg, vals=None) -> dict:
    """一次解完「除盘色以外」的滑块。返回 {vals, report}。

    盘色(r/g/b)沿用传进来的那组 —— **那是唯一留给人的决定**。
    """
    med = _preset_medians()
    v = dict(med)
    if vals:
        v.update({k: float(x) for k, x in clean(vals).items() if k in ("r", "g", "b", "x2")})
    rep = []
    mk = solve_mask(img, bg)
    v["mask"] = mk["mask"]
    rep.append("蒙版收紧 %.2f —— 盖住本体 %.0f%%、漏进背景 %.3f(上限 %.2f)%s"
               % (mk["mask"], 100 * mk["coverage"], 100 * mk["leak"], 100 * MASK_LEAK_MAX,
                  "；" + mk["note"] if mk.get("note") else ""))
    for k, lab in (("bgsat", "背景饱和"), ("bglum", "背景亮度")):
        v[k] = med[k]
        rep.append("%s %.2f —— 取你已存 %d 组的中位" % (lab, v[k], len(_read().get("targets") or {})))
    st = solve_sat(img, bg, v)
    v["sat"] = st["sat"]
    rep.append("饱和 %.2f —— 解到内盘饱和 %.3f(目标 %.2f)%s"
               % (st["sat"], st["disc_sat"], DISC_SAT_TARGET,
                  "；" + st["note"] if st.get("note") else ""))
    return {"vals": clean(v), "report": rep}

