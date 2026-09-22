# -*- coding: utf-8 -*-
"""自有盘色基准:从**用户自己手工处理的成片**量出星系盘色目标廓线。

【为什么要有这个(2026-09-20 用户拍板)】管线原来把 AstroBin 同视场共识当盘色目标。
在同一把尺子(discmetric,按本体半径归一)下实测 M31:

  | | B/G 核 / 内盘 / 盘 / 外盘 |
  |---|---|
  | 用户手工成品 | **1.069 / 1.209 / 1.281 / 1.208** |
  | AstroBin 共识 | 0.843 / 0.882 / 0.990 / 1.079 |

**共识比用户口味冷约 25%**,于是「盘色推移」这一步忠实地把已经对的盘色往回压
(实测 r11f_disccolor 把核 B/G 从 0.993 推到 0.878、中性交叉点 1.3% → 16.6%)。
用户 2026-09-20 拍板:**以自己的成品为准**,拿不到才退回 AstroBin 共识。

【哪些图算"用户手工成品"】PixInsight 手工导出的命名是 `ImageNN.jpg`;管线出的是
目标名命名(`M31.jpg`)。**只认 `Image*.jpg`**,否则拿管线自己的输出当目标就成了循环论证。

【口径】必须用 `discmetric.measure`(与成片侧同一个函数)。见 [[pi-galaxy-disc-color-target]]:
目标源与成片侧不同函数量 = 两函数的系统偏差直接变成成片色偏。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config

CACHE_DIR = config.PIPELINE_DIR / "_config" / "house_colors"
FAMILY_FILE = CACHE_DIR / "_family.json"
METRIC_VERSION = 2          # 跟 discmetric 口径版本对齐;改了度量要作废旧缓存

# 【只收最近处理的(用户 2026-09-21 指出)】"我手工处理的图像也不一定完全正确,
#   主要问题是处理时间比较久远、前后风格并不一致"。实测按处理日期排开,分界非常干脆:
#     2026-09-15~20 的四张(M51/M74/M77/M31)盘 B/G = 1.256/1.273/1.304/1.302 —— 跨度仅 0.05
#     2026-07 及更早(NGC3628/M63/M81/M33 等)          = 0.996~1.168
#   差 0.27,而且**新旧各自内部都很一致** → 是风格切换,不是噪声。
#   不卡时间窗就会把目标拉回用户已经不认可的那一档。
MAX_AGE_DAYS = 45.0

# 目录名 → 目标名。只收**真星系**;星云/星团即使目录名像星系编号也不能进(判据不通用)。
_GAL_DIR = re.compile(
    r"(?:^|_)(M\s?3[123]|M\s?49|M\s?5[19]|M\s?6[3456]|M\s?7[478]|M\s?8[1235]|M\s?9[04]|"
    r"M\s?10[168]|M\s?110|NGC\s?3628|NGC\s?5128|NGC\s?4565|IC\s?342)"
    r"(?:_(M\s?\d+))?(?:$|_)", re.I)
# 明确排除:名字像星系编号但其实是星云/星团的
_NOT_GAL = re.compile(r"(NGC\s?6302|NGC\s?3372|NGC\s?2026|NGC\s?1499|NGC\s?2244|"
                      r"IC\s?4592|IC\s?1396|IC\s?434|IC\s?443|IC\s?2118|C\s?80|C\s?92|"
                      r"milkyway|orion|sh2)", re.I)


def _target_of(dirname: str) -> str | None:
    """目录名 → 目标名;**多天体视场一律不收**。

    discmetric 的同心环模型假设画面里是**一个**居中星系。双星系视场量出来的是垃圾:
    实测 M65_M66 盘 B/G 0.416、M59_M60 0.689、M31_M32 0.889 —— 环里混进了另一个星系
    和大片空天。宁可少几个目标,也不能把这种数喂进调色目标。
    """
    if _NOT_GAL.search(dirname):
        return None
    m = _GAL_DIR.search(dirname)
    if not m:
        return None
    parts = [p.replace(" ", "") for p in m.groups() if p]
    if len(parts) > 1:
        return None
    return parts[0].upper()


def scan_manual_finals(root: str | None = None,
                       max_age_days: float | None = None) -> dict[str, Path]:
    """找用户手工成片:每个星系目录取**最新**的一张 Image*.jpg;
    并且**只收最近 max_age_days 天内处理的**(见模块头 MAX_AGE_DAYS 的实测理由)。"""
    import time as _time
    _age = MAX_AGE_DAYS if max_age_days is None else float(max_age_days)
    _cut = _time.time() - _age * 86400.0
    base = Path(root or config.get_setting("stacking_output_base") or "M:/Deepsky")
    out_root = Path(str(base).replace("Deepsky", "deepsky_output"))
    if not out_root.exists():
        out_root = Path("M:/deepsky_output")
    found: dict[str, tuple[float, Path]] = {}
    if not out_root.exists():
        return {}
    # **必须递归**:D3 拍的星系成片在 `deepsky_output/D3 Messier/<目录>` 下,
    #   只扫顶层会漏掉 M31/M33/M51/M63/M64/M65_M66/M74/M77/M49(实测只扫到 4/13)。
    dirs = [d for d in out_root.rglob("*") if d.is_dir()]
    for d in dirs:
        tgt = _target_of(d.name)
        if not tgt:
            continue
        cands = [f for f in d.glob("Image*.jpg")
                 if not re.search(r"(annotat|starless|crop|_ra|_astap)", f.name, re.I)]
        if not cands:
            continue
        newest = max(cands, key=lambda f: f.stat().st_mtime)
        mt = newest.stat().st_mtime
        if mt < _cut:                 # 太旧:风格与当前不一致,不收
            continue
        prev = found.get(tgt)
        if prev is None or mt > prev[0]:
            found[tgt] = (mt, newest)
    return {k: v[1] for k, v in found.items()}


def build(root: str | None = None, log=print) -> dict:
    """量全部手工星系成片 → 每目标一个 json + 一个家族中位。返回 {target: profile}。"""
    import numpy as np
    from . import discmetric as DM

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    finals = scan_manual_finals(root)
    out: dict[str, dict] = {}
    for tgt, p in sorted(finals.items()):
        try:
            m = DM.measure(DM.load_any(str(p)))
            rings = m.get("rings") or []
            prof = [{"rg": (r or {}).get("rg"), "bg": (r or {}).get("bg")} for r in rings]
            # 至少要量出内三环才算数 —— 外环常被画幅截断/信噪不足
            if sum(1 for x in prof[:3] if x.get("bg")) < 3:
                log(f"  [自有基准] {tgt}: 内三环量不全 → 跳过({p.name})")
                continue
            # 【同时存「颜色 vs 亮度」廓线】盘色目标有两种用途,自变量不同,必须各存各的:
            #   · ring profile(按本体半径分环)→ 给按环推倍率的 disc_push_curves
            #   · lum profile(按亮度分档)    → 给逐通道 CT 曲线(曲线的自变量就是亮度)
            #   混用会得出相反结论(实测:半径口径"外盘不够蓝",亮度口径"暗端偏蓝、中调偏红")。
            try:
                from . import galaxycolor as _gcp
                _lp, _lbg = _gcp.lum_color_profile(DM.load_any(str(p)))
            except Exception:
                _lp, _lbg = [], None
            rec = {"target": tgt, "source": str(p), "metric_version": METRIC_VERSION,
                   "r_obj_px": m.get("r_obj"), "profile": prof,
                   "lum_profile": [[round(a, 5), round(b, 5), round(c, 5)] for a, b, c in _lp],
                   "bg": ([round(float(x), 5) for x in _lbg] if _lbg is not None else None)}
            (CACHE_DIR / f"{tgt}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            out[tgt] = rec
            log("  [自有基准] %-10s B/G %s   R/G %s" %
                (tgt,
                 " / ".join(("%.3f" % x["bg"]) if x.get("bg") else "  -- " for x in prof),
                 " / ".join(("%.3f" % x["rg"]) if x.get("rg") else "  -- " for x in prof)))
        except Exception as e:
            log(f"  [自有基准] {tgt}: 量失败 {str(e)[:60]}")
    # 家族中位:拿不到某目标的自有基准时用
    if out:
        fam = []
        for i in range(4):
            bs = [r["profile"][i]["bg"] for r in out.values()
                  if i < len(r["profile"]) and r["profile"][i].get("bg")]
            rs = [r["profile"][i]["rg"] for r in out.values()
                  if i < len(r["profile"]) and r["profile"][i].get("rg")]
            fam.append({"bg": float(np.median(bs)) if bs else None,
                        "rg": float(np.median(rs)) if rs else None,
                        "n": len(bs)})
        FAMILY_FILE.write_text(json.dumps(
            {"metric_version": METRIC_VERSION, "n_targets": len(out), "profile": fam},
            ensure_ascii=False, indent=1), encoding="utf-8")
        log("  [自有基准] 家族中位(%d 个目标) B/G %s" %
            (len(out), " / ".join(("%.3f" % x["bg"]) if x.get("bg") else "--" for x in fam)))
    return out


def get(target: str, log=None) -> dict | None:
    """取某目标的自有基准廓线;没有就退家族中位;都没有返回 None(→ 调用方退 AstroBin)。

    **三态要分清**:有本目标的 / 只有家族中位的 / 什么都没有。返回值里 `source` 标明是哪一种,
    调用方不能把"家族中位"当成"这个目标的证据"(见 [[pi-galaxy-disc-color-target]]:
    没有针对这个天体的证据时,退回平均值比什么都不做更危险)。
    """
    t = (target or "").replace(" ", "").upper()
    f = CACHE_DIR / f"{t}.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("metric_version") == METRIC_VERSION:
                d["source"] = "self"
                if log:
                    log(f"  [自有基准] {t}: 用**该目标自己**的手工成片")
                return d
        except (OSError, ValueError):
            pass
    # 【故意不退家族中位】家族中位实测跨度极大(B/G 核 0.77~1.22、盘 0.61~1.30),
    #   那是**真实的类型差异**(椭圆星系没有蓝盘、正向旋涡盘很蓝),不是噪声。
    #   拿中位去推一个不知道类型的目标 = 把椭圆推蓝、把旋涡推黄。
    #   见 [[pi-galaxy-disc-color-target]]:没有针对这个天体的证据时,
    #   "退回一个平均值"比"什么都不做"更危险。→ 返回 None,调用方退 AstroBin 同视场共识。
    if log:
        log(f"  [自有基准] {t}: 没有该目标的手工成片 → 不用自有基准(退 AstroBin 同视场)")
    return None
