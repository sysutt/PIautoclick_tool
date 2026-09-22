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


def save(target: str | None, vals, bg=None, note: str = "") -> dict[str, Any]:
    """记下这一组。同时写 `last`(跨目标的默认预设)和 `targets[目标]`(本目标专用)。"""
    rec = {"vals": clean(vals), "bg": (float(bg) if bg is not None else None),
           "saved": datetime.now().isoformat(timespec="seconds"),
           "target": (target or "").strip(), "note": note}
    d = _read()
    d["last"] = rec
    if _key(target or ""):
        d.setdefault("targets", {})[_key(target or "")] = rec
    _write(d)
    return rec


def get(target: str | None = None, fallback_last: bool = True):
    """取预设:先找本目标专用的,没有再退到最近一次(`last`)。

    返回里带 `source`:"target"=这个目标自己调过,"last"=借用最近一次调的另一个目标。
    调用方**必须把 source 打进日志** —— 借来的那组是"上次在别的目标上满意的档",
    不是对本目标的测量结论,两者可信度不同,不能混为一谈。
    """
    d = _read()
    k = _key(target or "")
    if k and isinstance(d.get("targets"), dict) and k in d["targets"]:
        rec = dict(d["targets"][k]); rec["source"] = "target"
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
