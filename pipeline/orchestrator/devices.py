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


def _band_of(filt: str) -> str:
    """滤镜 → 波段:'broad'(宽带,走 RGB)/ 'narrow'(窄带,走 HOO)/ ''(未知)。
    Dwarf 语义(用户 2026-08 确认):Astro=没上滤镜直拍(全光谱宽带)、VIS=UV-IRcut(宽带)、
    Dual-Band=双窄(Ha+OIII)。"""
    f = (filt or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    if not f:
        return ""
    # 窄带:Dwarf=Duo-Band;Seestar=LP(名为光害滤镜,实为 Ha+OIII 双窄);及各窄带名
    if any(k in f for k in ("duoband", "dualband", "duo", "lp", "halpha", "ha", "oiii", "o3",
                            "sii", "s2", "narrow", "nb")):
        return "narrow"
    # 宽带:Dwarf=Astro(无滤镜直拍)/VIS(UV-IRcut);Seestar=IRCUT(标准);及各宽带名
    if any(k in f for k in ("astro", "vis", "ircut", "uvir", "uhc", "cls", "broad",
                            "lumin", "red", "green", "blue", "rgb", "osc")):
        return "broad"
    return ""


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
    obj = (cards.get("OBJECT", "") or "").strip()
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
    # 文件名兜底滤镜:Dwarf 的 header FILTER 常为空,但名里有 _Astro_/_Dual-Band_ 等。
    # 【注意】Astro=宽带(不是双窄!),Dual-Band/Duo 才是双窄;band 字段据此给流程选型用。
    if not filt:
        mf = re.search(r"_(Duo[-_ ]?Band|Dual[-_ ]?Band|DuoBand|DualBand|Duo|Astro|VIS|IRCUT|LP|UHC|Ha|OIII|O3|SII|S2)_",
                       name, re.I)
        if mf:
            filt = mf.group(1)
    band = _band_of(filt)               # 'broad' / 'narrow' / ''

    # Dwarf 会给质量不合格的子帧打 failed_ 前缀 → 视为废帧,别混进任何栈
    if low.startswith("failed"):
        return {"path": path.replace("\\", "/"), "name": name, "device": device, "type": "rejected",
                "filter": filt, "band": band, "object": obj, "exp": exp, "gain": gain, "temp": temp,
                "width": int(w) if w else None, "height": int(h) if h else None,
                "is_stacked": is_stacked, "confident": True}

    confident = False
    ftype = _type_from_imagetyp(cards.get("IMAGETYP", ""))
    if ftype:
        confident = True
    else:
        # 无 IMAGETYP(典型 Dwarf):目录/文件名/头信号综合判。
        # 【关键修正】不能用"FILTER 空→dark":Dwarf 很多亮场 header FILTER 也为空。
        # 亮场判据 = 有 OBJECT(真实目标)/ 文件名带 <目标>_<曝光>s<增益> / 在 DWARF_RAW_TELE_ 会话目录。
        tok = folder + " " + low
        looks_light = bool(obj) or bool(re.search(r"_\d+(?:\.\d+)?s\d+_", low)) or "dwarf_raw_tele" in folder
        if re.search(r"(?:^|[/_ ])bias", tok) or (exp is not None and exp <= 0.05):
            ftype = "bias"
        elif re.search(r"(?:^|[/_ ])flat", tok):
            ftype = "flat"
        elif low.startswith("raw_") or re.search(r"(?:^|[/_ ])dark", tok) or "dwarf_dark" in folder:
            ftype = "dark"          # 暗场:文件名 raw_ 前缀 / DWARF_DARK 目录 / 目录含 dark
        elif looks_light:
            ftype = "light"
        else:
            ftype = "dark" if (exp and exp > 1) else "unknown"   # 无目标信息的长曝光→兜底当暗场

    if is_stacked and ftype == "light":
        ftype = "stacked"               # 设备内叠加成品,别混进子帧栈

    return {"path": path.replace("\\", "/"), "name": name, "device": device, "type": ftype,
            "filter": filt, "band": band, "object": obj, "exp": exp, "gain": gain, "temp": temp,
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


def stacking_plan(scan_result: dict) -> dict:
    """把 scan 结果按「类型 → 所在目录」归并,供回填叠加面板。并检测是否有目录**混放多类型**
    (mixed=True 时 dir 级 WBPP 分不开,需 stage_frames 分拣)。返回:
    {device, light_dirs, dark_dirs, flat_dirs, bias_dirs, stacked_files, mixed}。"""
    groups = scan_result["groups"]
    dir_types: dict[str, set] = {}
    per_type = {}
    for t in ("light", "dark", "flat", "bias"):
        seen, dirs = set(), []
        for c in groups.get(t, []):
            d = os.path.dirname(c["path"])
            dir_types.setdefault(d, set()).add(t)
            if d not in seen:
                seen.add(d); dirs.append(d)
        per_type[t] = dirs
    return {"device": scan_result.get("device", "unknown"),
            "light_dirs": per_type["light"], "dark_dirs": per_type["dark"],
            "flat_dirs": per_type["flat"], "bias_dirs": per_type["bias"],
            "stacked_files": [c["path"] for c in groups.get("stacked", [])],
            "mixed": any(len(ts) > 1 for ts in dir_types.values())}


def stage_frames(scan_result: dict, stage_root: str, types=("light", "dark", "flat", "bias")) -> dict:
    """源目录混放多类型时:把已分类帧按类型**硬链接**(同盘瞬时零拷贝;跨盘退化为复制)到
    stage_root/{light,dark,…}/,给 WBPP 干净的按类型目录。返回 {type: 目录}。"""
    import shutil
    out = {}
    for t in types:
        items = scan_result["groups"].get(t, [])
        if not items:
            continue
        td = os.path.join(stage_root, t).replace("\\", "/")
        os.makedirs(td, exist_ok=True)
        for c in items:
            dst = os.path.join(td, os.path.basename(c["path"]))
            if os.path.exists(dst):
                continue
            try:
                os.link(c["path"], dst)             # 硬链接:同盘瞬时、零拷贝
            except OSError:
                try:
                    shutil.copy2(c["path"], dst)     # 跨盘退化为复制
                except OSError:
                    pass
        out[t] = td
    return out


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(scan(sys.argv[1:] or ["."]), ensure_ascii=False, indent=2, default=str))


# ── 黑白相机的单通道滤镜(用户 2026-09-28:宽带 + 窄带融合不该分彩色 / 黑白)────────────────
#   黑白相机一个滤镜一张母版:宽带 L/R/G/B 先合成一张 RGB 当底,窄带 Hα/OIII/SII 各是一层;
#   之后和彩色相机走同一套融合(彩色相机只是多一步把双窄带母版拆成单通道)。
MONO_FILTERS = ("L", "R", "G", "B", "Ha", "OIII", "SII")
MONO_BROADBAND = ("L", "R", "G", "B")


def read_xisf_keywords(path: str, max_bytes: int = 1 << 20) -> dict:
    """解析 XISF 头里的 FITSKeyword,返回 {大写KEY: 值字符串}(已去引号/空白)。非 XISF/读失败→{}。
    XISF 1.0 布局:8 字节签名 `XISF0100` + uint32(LE) 头长度 + 4 字节保留 + UTF-8 XML 头。"""
    import html
    if os.path.splitext(path)[1].lower() != ".xisf":
        return {}
    try:
        with open(path, "rb") as f:
            sig = f.read(16)
            if len(sig) < 16 or not sig.startswith(b"XISF0100"):
                return {}
            n = int.from_bytes(sig[8:12], "little")
            xml = f.read(min(n, max_bytes)).decode("utf-8", "replace")
    except OSError:
        return {}
    cards = {}
    for m in re.finditer(r'<FITSKeyword\s+name="([^"]+)"\s+value="([^"]*)"', xml):
        k = m.group(1).strip().upper()
        if k not in cards:
            cards[k] = html.unescape(m.group(2)).strip().strip("'").strip()
    return cards


_IMG_EXT = (".xisf", ".fit", ".fits", ".fts")


def first_image(src: str, max_depth: int = 2) -> str:
    """素材来源(文件或目录)→ 第一张图像文件路径;目录往下最多找两层(DWARF 的帧在时间戳子夹里)。
    跳过筛帧剔除夹(_ttlot_culled)和 failed_ 开头的帧。找不到返回 ''。"""
    if not src:
        return ""
    if os.path.isfile(src):
        return src if os.path.splitext(src)[1].lower() in _IMG_EXT else ""
    if not os.path.isdir(src):
        return ""
    base = os.path.normpath(src).count(os.sep)
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(x for x in dirs if not x.startswith("_ttlot_culled"))
        for fn in sorted(files):
            if os.path.splitext(fn)[1].lower() in _IMG_EXT and not fn.lower().startswith("failed_"):
                return os.path.join(root, fn)
        if os.path.normpath(root).count(os.sep) - base >= max_depth:
            dirs[:] = []
    return ""


def read_equipment(path: str) -> dict:
    """素材文件头里的器材信息(配置屏「设备」一节用),读不到的字段为 None:
    camera(INSTRUME)/ telescope(TELESCOP)/ focal_mm(FOCALLEN)/ pixel_um(XPIXSZ)/
    scale(″/px = 206.265 × XPIXSZ / FOCALLEN;XPIXSZ 已含 binning,不再乘 XBINNING)/ width / height。"""
    ext = os.path.splitext(path)[1].lower()
    cards = read_xisf_keywords(path) if ext == ".xisf" else read_header(path)
    w = h = None
    if ext == ".xisf":
        try:
            with open(path, "rb") as f:
                sig = f.read(16)
                n = int.from_bytes(sig[8:12], "little") if sig.startswith(b"XISF0100") else 0
                xml = f.read(min(n, 1 << 20)).decode("utf-8", "replace") if n else ""
            m = re.search(r'geometry="(\d+):(\d+)', xml)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
        except OSError:
            pass
    else:
        w, h = _num(cards.get("NAXIS1")), _num(cards.get("NAXIS2"))
        w = int(w) if w else None
        h = int(h) if h else None
    fl, px = _num(cards.get("FOCALLEN")), _num(cards.get("XPIXSZ"))
    return {"camera": (cards.get("INSTRUME") or "").strip() or None,
            "telescope": (cards.get("TELESCOP") or "").strip() or None,
            "focal_mm": fl if fl and fl > 0 else None, "pixel_um": px if px and px > 0 else None,
            "scale": (206.265 * px / fl) if (fl and px and fl > 0) else None,
            "width": w, "height": h}


def mono_filter_key(text: str) -> str:
    """滤镜名 → 'L'/'R'/'G'/'B'/'Ha'/'OIII'/'SII';认不出返回 ''。
    认 FITS FILTER 的常见写法(Ha / H-alpha / Ha 7nm / OIII / O3 / SII / S2 / Lum / Luminance / Red / R …),
    也认 PI 视图名被截短的(MasterLight_Gree)。Hβ 现在不参与融合,返回 ''。"""
    c = re.sub(r"[^a-z0-9]", "", (text or "").strip().lower().replace("α", "a"))
    if not c:
        return ""
    if c.startswith(("sii", "s2", "sulfur", "sulphur")):
        return "SII"
    if c.startswith(("oiii", "o3")):
        return "OIII"
    if c.startswith(("hb", "hbeta")):
        return ""
    if c.startswith(("ha", "halpha", "hydrogen")) or c == "h":
        return "Ha"
    if c.startswith("lum") or c in ("l", "clear"):
        return "L"
    if c.startswith("red") or c == "r":
        return "R"
    if c.startswith("gre") or c == "g":
        return "G"
    if c.startswith("blu") or c == "b":
        return "B"
    return ""


def mono_filter_of(path: str) -> str:
    """一张黑白母版是哪个滤镜:先看头(FITS / XISF 的 FILTER),再看文件名。认不出返回 ''。
    文件名先找 WBPP 的 `FILTER-<名>` 段;没有再从后往前逐段试(单个字母只认最后一段,
    免得把 `_c_r` 这类处理后缀当成滤镜)。"""
    cards = read_header(path) or read_xisf_keywords(path)
    k = mono_filter_key(cards.get("FILTER", ""))
    if k:
        return k
    name = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"FILTER-([^_]+)", name, re.I)
    if m:
        k = mono_filter_key(m.group(1))
        if k:
            return k
    toks = [t for t in re.split(r"[_\-\s.]+", name) if t]
    for i in range(len(toks) - 1, -1, -1):
        if len(toks[i]) == 1 and i != len(toks) - 1:
            continue
        k = mono_filter_key(toks[i])
        if k:
            return k
    return ""
