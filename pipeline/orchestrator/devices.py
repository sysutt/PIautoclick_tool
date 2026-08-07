"""智能望远镜 / 相机原始素材的**帧特征识别**。

按「FITS 头优先、文件名兜底」判定:设备(Seestar / Dwarf / 通用)、帧类型
(light/dark/flat/bias/stacked)、以及曝光/增益/温度/滤镜/尺寸。**不依赖固定目录结构**
(用户可能任意摆放),也**不依赖 astropy**(只手工解析 FITS 主头)。

真实样本据以标定(2026-08,用户提供 H:/S30、S30 Pro、S50、Dwarf 3):
- Seestar:`IMAGETYP='Light'`(权威)、`FILTER=IRCUT|LP`、`BAYERPAT=GRBG`、`CCD-TEMP`、
  `INSTRUME='Seestar S50'`;文件名 `Light_<目标>_<曝光>s_<滤镜>_<时间>.fit`;
  设备内叠加成品为 `Stacked_<N>_...`(应排除出子帧栈)。无暗/平/偏。
- Dwarf3:**无 IMAGETYP**、`FILTER=Astro|VIS`(暗场为空)、`BAYERPAT=RGGB`、温度关键字是
  **`DET-TEMP`** 且文件名带 `_<温度>C`、`INSTRUME='DWARF 3'`;亮场名 `<目标>_<曝光>s<增益>_<滤镜>_..._<温度>C.fits`,
  暗场名 `raw_<曝光>s_<增益>_..._<温度>C.fits`,偏置极短曝光(~0.0001s)。
"""
from __future__ import annotations

import glob
import os
import re

# 温度关键字候选(Dwarf 用 DET-TEMP,Seestar/多数用 CCD-TEMP)
_TEMP_KEYS = ("DET-TEMP", "CCD-TEMP", "CCD_TEMP", "CCDTEMP", "SET-TEMP", "SENSOR-T", "TEMPERAT")
_FITS_EXT = (".fit", ".fits", ".fts", ".xisf")
# 文件名尾部温度:_42C / _-9C / _22.8C
_RE_NAME_TEMP = re.compile(r"[_-](-?\d+(?:\.\d+)?)\s*[cC](?=[._]|$)")
# 文件名曝光/增益:30s60 或 0.0001s60 或 30s_60(Dwarf);Seestar 用头,不强依赖名
_RE_NAME_EXPGAIN = re.compile(r"(\d+(?:\.\d+)?)s[_]?(\d+)", re.I)


def read_header(path: str, max_blocks: int = 12) -> dict:
    """解析 FITS 主头,返回 {大写KEY: 值字符串}(字符串已去引号/空白)。非 FITS/读失败→{}。"""
    if os.path.splitext(path)[1].lower() not in (".fit", ".fits", ".fts"):
        return {}
    try:
        with open(path, "rb") as f:
            blob = f.read(2880 * max_blocks)
    except OSError:
        return {}
    if not blob.startswith(b"SIMPLE"):
        return {}
    cards = {}
    for i in range(0, len(blob) - 80, 80):
        card = blob[i:i + 80].decode("latin-1", "replace")
        key = card[:8].strip().upper()
        if key == "END":
            break
        if card[8:10] == "= ":
            val = card[10:].split("/")[0].strip().strip("'").strip()
            cards[key] = val
    return cards


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def frame_temp(path: str, cards: dict | None = None) -> float | None:
    """传感器温度(°C):FITS 头(DET-TEMP/CCD-TEMP…)优先,取不到再从文件名 `_NNC` 兜底。"""
    cards = read_header(path) if cards is None else cards
    for k in _TEMP_KEYS:
        if k in cards:
            v = _num(cards[k])
            if v is not None:
                return v
    m = _RE_NAME_TEMP.search(os.path.basename(path))
    return float(m.group(1)) if m else None


def dir_temp(root, n: int = 8):
    """采样目录内前 n 张 FITS 的温度中位数,快速估该目录代表温度(亮/暗场匹配校验用)。取不到→None。"""
    import statistics
    temps = []
    for p in iter_frames(root):
        t = frame_temp(p)
        if t is not None:
            temps.append(t)
        if len(temps) >= n:
            break
    return statistics.median(temps) if temps else None


def _device_of(instrume: str, telescop: str = "") -> str:
    s = (instrume + " " + telescop).lower()
    if "seestar" in s or re.search(r"\bs[35]0\b", s):
        return "seestar"
    if "dwarf" in s:
        return "dwarf"
    return "unknown"


def _type_from_imagetyp(it: str) -> str | None:
    it = it.lower()
    if not it:
        return None
    if "light" in it:
        return "light"
    if "dark" in it and "flat" not in it:
        return "dark"
    if "flat" in it:
        return "flat"
    if "bias" in it or "zero" in it or "offset" in it:
        return "bias"
    return None


def classify(path: str) -> dict:
    """识别单个文件的特征。返回 dict:
    {path, name, device, type, filter, exp, gain, temp, width, height, is_stacked, confident}
    type ∈ light/dark/flat/bias/stacked/unknown。confident=是否由权威信号(IMAGETYP)判定。"""
    name = os.path.basename(path)
    low = name.lower()
    folder = os.path.dirname(path).replace("\\", "/").lower()
    cards = read_header(path)

    device = _device_of(cards.get("INSTRUME", ""), cards.get("TELESCOP", ""))
    filt = cards.get("FILTER", "") or ""
    exp = _num(cards.get("EXPTIME") or cards.get("EXPOSURE"))
    gain = _num(cards.get("GAIN"))
    temp = frame_temp(path, cards)
    w = _num(cards.get("NAXIS1")); h = _num(cards.get("NAXIS2"))
    is_stacked = low.startswith("stacked") or "restack" in cards.get("IMAGETYP", "").lower()

    # 名字里补曝光/增益(Dwarf 名里带;头缺时兜底)
    if exp is None or gain is None:
        m = _RE_NAME_EXPGAIN.search(low)
        if m:
            exp = exp if exp is not None else _num(m.group(1))
            gain = gain if gain is not None else _num(m.group(2))

    # Dwarf 会给质量不合格的子帧打 failed_ 前缀 → 视为废帧,别混进任何栈
    if low.startswith("failed"):
        return {"path": path.replace("\\", "/"), "name": name, "device": device, "type": "rejected",
                "filter": filt, "exp": exp, "gain": gain, "temp": temp,
                "width": int(w) if w else None, "height": int(h) if h else None,
                "is_stacked": is_stacked, "confident": True}

    confident = False
    ftype = _type_from_imagetyp(cards.get("IMAGETYP", ""))
    if ftype:
        confident = True
    else:
        # 无 IMAGETYP(典型 Dwarf):按 目录token → 文件名前缀 → 头信号 综合判定
        tok = folder + " " + low
        if re.search(r"(?:^|[/_ ])bias", tok) or (exp is not None and exp <= 0.05 and not filt):
            ftype = "bias"
        elif re.search(r"(?:^|[/_ ])flat", tok):
            ftype = "flat"
        elif re.search(r"(?:^|[/_ ])dark", tok) or low.startswith("raw_") or (not filt and exp and exp > 0.05):
            # 暗场:目录/文件名标注,或 FILTER 空且非极短曝光(Dwarf 暗场 FILTER 为空)
            ftype = "dark"
        elif filt:                      # 有真实滤镜(Astro/VIS/IRCUT/LP/Ha…)→ 亮场
            ftype = "light"
        else:
            ftype = "unknown"

    if is_stacked and ftype == "light":
        ftype = "stacked"               # 设备内叠加成品,别混进子帧栈

    return {"path": path.replace("\\", "/"), "name": name, "device": device, "type": ftype,
            "filter": filt, "exp": exp, "gain": gain, "temp": temp,
            "width": int(w) if w else None, "height": int(h) if h else None,
            "is_stacked": is_stacked, "confident": confident}


def iter_frames(roots):
    """递归遍历若干目录/文件,产出所有 FITS/XISF(跳过缩略图与非图像)。"""
    if isinstance(roots, str):
        roots = [roots]
    for r in roots:
        r = r.replace("\\", "/")
        if os.path.isfile(r):
            if os.path.splitext(r)[1].lower() in _FITS_EXT:
                yield r
        elif os.path.isdir(r):
            for dp, _dn, fns in os.walk(r):
                for fn in fns:
                    if os.path.splitext(fn)[1].lower() in _FITS_EXT and not fn.lower().endswith("_thn.jpg"):
                        yield os.path.join(dp, fn)


def scan(roots) -> dict:
    """扫描目录(可任意结构)→ 按帧类型分组 + 汇总。返回:
    {device, groups:{light/dark/flat/bias/stacked/unknown:[classify…]},
     summary:{type:{count, exps, gains, temps(min/max), filters}}, lights_by_filter:{filter:[…]}}"""
    groups = {k: [] for k in ("light", "dark", "flat", "bias", "stacked", "unknown")}
    devices = {}
    for p in iter_frames(roots):
        c = classify(p)
        groups.setdefault(c["type"], []).append(c)
        if c["device"] != "unknown":
            devices[c["device"]] = devices.get(c["device"], 0) + 1

    def _agg(items):
        exps = sorted({round(x["exp"], 4) for x in items if x["exp"] is not None})
        gains = sorted({int(x["gain"]) for x in items if x["gain"] is not None})
        temps = [x["temp"] for x in items if x["temp"] is not None]
        filts = sorted({x["filter"] for x in items if x["filter"]})
        return {"count": len(items), "exps": exps, "gains": gains,
                "temp_min": min(temps) if temps else None, "temp_max": max(temps) if temps else None,
                "filters": filts}

    lights_by_filter = {}
    for c in groups["light"]:
        lights_by_filter.setdefault(c["filter"] or "?", []).append(c)

    return {"device": max(devices, key=devices.get) if devices else "unknown",
            "device_counts": devices,
            "groups": groups,
            "summary": {t: _agg(items) for t, items in groups.items() if items},
            "lights_by_filter": {k: len(v) for k, v in lights_by_filter.items()}}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(scan(sys.argv[1:] or ["."]), ensure_ascii=False, indent=2, default=str))
