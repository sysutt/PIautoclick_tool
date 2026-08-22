"""无 PI OSC 叠加引擎(zero-PixInsight):原始亮场(+可选暗/平/偏)→ Siril 校准 → 去马赛克 →
星点配准 → 整合 → master。全程不碰 PixInsight,补齐"零 PI 完整链路"里叠加这块拼图。

与 rgb_engine / hoo_engine / sho_engine 并列(它们做后期,本模块做前端叠加)。见 [[siril-stacking]]。

**踩通的坑(固化自 M51 S30 Pro 161 帧真机验证,2026-08-15)**:
1. **Seestar `_sub` 混 .jpg 预览/缩略图**(161 fit + 322 jpg)→ Siril convert 会全叠进去 → **只挑 .fit 暂存**。
2. **Siril convert 序列名带尾下划线** `light_`(不是 `light`)→ 后续 register/stack 必须用 `light_`。
3. **register 复用 `cache/*.lst` 里的旧星表**(换目标/重试会用错) → 配准前**清 cache**。
4. **线性帧星点弱**,默认 findstar 只找到 2 颗星 → **`setfindstar -sigma=0.5`** 降阈值才够配准。
5. **Siril 在中文 Windows 输出 GBK**,按 utf-8 解码会乱码 + 假 OSError(stdout TextIOWrapper)→ 自动 utf-8/gbk 双解码。
6. **大帧数彩色栈慢**(161×3通道×32位≈16GB):默认 Siril 内存上限低 → **`setmem` 提上限**单遍内存整合。
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time

import re
from collections import defaultdict

from . import config, siril

_LIGHT_EXTS = (".fit", ".fits", ".fts")

# 滤镜 → 路由:宽带(RGB)/ 窄带(HO/HOO/SHO)。Seestar:IRCUT/UV-IR=宽带、LP/双窄带=窄带。
_RGB_FILT = ("ircut", "uv/ir", "uvir", "uv-ir", "uv/ir block", "l", "lum", "lps", "none", "")
_NB_FILT = ("lp", "dual", "duo", "ha", "oiii", "o3", "sii", "s2", "sho", "hoo",
            "lextreme", "l-extreme", "lultimate", "l-ultimate", "lenhance", "l-enhance", "lpro")


def filter_kind(filt: str) -> str:
    """滤镜名 → "rgb"(宽带)/ "narrowband"(窄带)/ "unknown"。"""
    f = str(filt or "").strip().lower()
    if f in _RGB_FILT or "ircut" in f or "uv" in f:
        return "rgb"
    if f in _NB_FILT or "lp" in f or "dual" in f or "narrow" in f or f in ("ha", "oiii", "sii"):
        return "narrowband"
    return "unknown"


def _frame_meta(path: str) -> tuple[str, str, str]:
    """(FILTER, 时间戳YYYYMMDDHHMMSS, 曝光) —— Seestar 文件名优先(快,免读头),FITS 头兜底。
    文件名式 `Light_<目标>_<曝光>s_<FILTER>_<YYYYMMDD>-<HHMMSS>.fit`。"""
    b = os.path.basename(path)
    mf = re.search(r"_([A-Za-z0-9/\-]+)_(\d{8})-(\d{6})", b)
    me = re.search(r"_(\d+(?:\.\d+)?)s_", b)
    if mf:
        return mf.group(1), mf.group(2) + mf.group(3), (me.group(1) if me else "?")
    try:                                                    # 头兜底
        from astropy.io import fits
        h = fits.getheader(path)
        do = str(h.get("DATE-OBS", "")).replace("-", "").replace(":", "").replace("T", "")[:14]
        return str(h.get("FILTER", "?")), do or "?", str(h.get("EXPTIME") or h.get("EXPOSURE") or "?")
    except Exception:
        return "?", "?", "?"


def _ts_gap_h(a: str, b: str) -> float:
    """两个 YYYYMMDDHHMMSS 时间戳间隔(小时);解析失败返回大值(判为不同会话)。
    **用 datetime 精确算**(跨午夜/月/年都对:如 09-14 23点→09-15 0点=1h 同会话、
    09-30→10-01 也是 1 天而非跨月错算)——别用 *31天/*12月 近似(月/年边界会错)。"""
    import datetime as _dt
    try:
        da = _dt.datetime.strptime(a[:14], "%Y%m%d%H%M%S")
        db = _dt.datetime.strptime(b[:14], "%Y%m%d%H%M%S")
        return abs((db - da).total_seconds()) / 3600.0
    except Exception:
        return 1e6


def group_frames(light_dir: str, *, session_gap_h: float = 3.0, log=print) -> list[dict]:
    """**混合 Seestar 目录 → 按会话(时间间隔聚类)× 滤镜分组**。Seestar 同目标所有会话/滤镜堆一个目录、
    时间只在单帧(不像 Dwarf 目录名带时间)→ 盲叠会混不同夜/曝光/滤镜致配准错乱。见 [[siril-stacking]]。
    返回组列表 [{session,filter,exp,kind,frames,count,date,t0,t1}](按帧数降序);kind=rgb/narrowband/unknown。"""
    subs = []
    for e in _LIGHT_EXTS:
        subs += glob.glob(os.path.join(light_dir, "*" + e))
    subs = [x for x in subs if not os.path.basename(x).lower().startswith("failed")]
    if not subs:
        return []
    recs = sorted((_frame_meta(f) + (f,) for f in subs), key=lambda r: r[1])   # 按时间戳
    sessions, cur = [], [recs[0]]
    for r in recs[1:]:
        if _ts_gap_h(cur[-1][1], r[1]) > session_gap_h:
            sessions.append(cur); cur = [r]
        else:
            cur.append(r)
    sessions.append(cur)
    groups = []
    for si, sess in enumerate(sessions):
        byf = defaultdict(list)
        for filt, ts, exp, f in sess:
            byf[(filt, exp)].append((ts, f))
        for (filt, exp), items in byf.items():
            items.sort()
            groups.append({"session": si, "filter": filt, "exp": exp, "kind": filter_kind(filt),
                           "frames": [f for _, f in items], "count": len(items),
                           "date": items[0][0][:8], "t0": items[0][0], "t1": items[-1][0]})
    groups.sort(key=lambda g: -g["count"])
    log(f"[stack] 目录分组:{len(subs)} 帧 → {len(sessions)} 会话 / {len(groups)} 组")
    for g in groups:
        log(f"  会话{g['session']} {g['date']} FILTER={g['filter']}({g['kind']}) EXP={g['exp']}s: {g['count']}帧")
    return groups


def _decode(b: bytes) -> str:
    """Siril 输出:先试 utf-8(非中文环境),失败退 gbk(中文 Windows 的 CP936)。"""
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def _tail(out: str, n: int = 12) -> str:
    return "\n".join(ln for ln in out.splitlines() if "EXIF" not in ln)[-1200:] if out else ""


def _run_siril(cmds: list[str], *, timeout: float, log, tag: str,
               mem_ratio: float | None = None, bit16: bool = False) -> str:
    """跑 Siril 脚本(自建,GBK 感知),返回解码后的输出。成败由调用方查产出文件(Siril 退出常打伪错误)。
    bit16=True 前置 `set16bits`(register 默认升 32 位浮点→帧翻倍/IO 翻倍;16 位减半、叠加质量无损)。"""
    exe = siril.siril_exe()
    if not exe:
        raise RuntimeError("Siril 不可用:未找到 siril-cli.exe(在配置里填 siril_path)")
    body = (["requires 1.2.0"]
            + (["set16bits"] if bit16 else [])
            + ([f"setmem {mem_ratio}"] if mem_ratio else [])
            + list(cmds))
    sp = os.path.join(str(config.RUN_DIR), f"_stkeng_{tag}.ssf").replace("\\", "/")
    with open(sp, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    r = subprocess.run([exe, "-s", sp], capture_output=True, timeout=timeout)
    return _decode(r.stdout) + "\n" + _decode(r.stderr)


def _naxis(path: str) -> int:
    """FITS 图层数(2=单层 CFA / 3=已 debayer RGB)。读不出返回 2(当普通 CFA)。"""
    try:
        from astropy.io import fits
        h = fits.getheader(path)
        na = int(h.get("NAXIS") or 2)
        return 3 if (na == 3 or int(h.get("NAXIS3") or 1) > 1) else 2
    except Exception:
        return 2


def _stage_lights(light_dir, stage_dir: str, log) -> int:
    """只挑 .fit/.fits 光子帧(**排除 .jpg 预览、failed_ 废帧、Dwarf 机内成片 stacked-**)复制到干净暂存目录。
    light_dir 可为单个目录(str)或多个目录(list,多晚合并叠加:各晚 .fit 汇到同一暂存目录统一编号)。
    **图层一致性过滤**:Dwarf 亮场目录里混着机内叠加成片(3图层RGB,文件名 stacked-16_*),混进去会让
    calibrate 序列图层不一致而中止(实测 M80 124帧混 2 张→calibrate 崩、只出 11 帧)→ 只留占多数的图层数。"""
    dirs = [light_dir] if isinstance(light_dir, str) else list(light_dir)
    subs: list[str] = []
    for d in dirs:
        for e in _LIGHT_EXTS:
            subs += glob.glob(os.path.join(d, "*" + e))
    def _ok_name(p):
        b = os.path.basename(p).lower()
        return not b.startswith("failed") and not b.startswith("stacked-")   # 排废帧 + Dwarf 机内成片
    subs = sorted(x for x in subs if _ok_name(x))
    if not subs:
        raise RuntimeError(f"目录无 .fit 光子帧:{light_dir}")
    # 图层一致性:统计各帧图层数,只留占多数的那种(原始 CFA 是 2 层;混入的 debayer 帧是 3 层)
    lays = [_naxis(f) for f in subs]
    if len(set(lays)) > 1:
        from collections import Counter
        keep_l = Counter(lays).most_common(1)[0][0]
        drop = sum(1 for l in lays if l != keep_l)
        subs = [f for f, l in zip(subs, lays) if l == keep_l]
        log(f"[stack] 图层一致性过滤:剔除 {drop} 帧图层数≠{keep_l}的异常帧(Dwarf 机内成片/混入的 RGB 帧)")
    os.makedirs(stage_dir, exist_ok=True)
    for i, f in enumerate(subs):
        shutil.copy2(f, os.path.join(stage_dir, f"sub_{i:05d}.fit"))
    log(f"[stack] 暂存 {len(subs)} 帧光子帧(排除 .jpg 预览/failed_/机内成片/异常图层帧)")
    return len(subs)


def make_master(frame_dir: str, out_noext: str, *, method: str = "med",
                mem_ratio: float = 0.9, timeout: float = 3600.0, log=print) -> str:
    """原始定标帧目录(暗/平/偏)→ master(convert + stack)。method: med(暗/偏)/ rej(平)。返回 <out>.fit。"""
    R = str(config.RUN_DIR)
    work = os.path.join(R, "_cal_" + os.path.basename(out_noext)).replace("\\", "/")
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    n = _stage_lights(frame_dir, f"{work}/stage", log)
    out = str(out_noext).replace("\\", "/").rsplit(".", 1)[0] if str(out_noext).lower().endswith((".fit", ".fits")) else str(out_noext).replace("\\", "/")
    stk = f"stack cal_ {method} -nonorm -out={out}" if method == "med" else f"stack cal_ rej 3 3 -nonorm -out={out}"
    out_log = _run_siril([f'cd "{work}/stage"', f"convert cal -out={work}",
                          f'cd "{work}"', stk], timeout=timeout, log=log, tag="cal", mem_ratio=mem_ratio)
    if not glob.glob(f"{out}.fit*"):
        raise RuntimeError(f"master 定标帧整合失败({n}帧):" + _tail(out_log))
    log(f"[stack] master 定标帧({method},{n}帧)→ {out}.fit")
    return out + ".fit"


def stack_osc(light_dir, out_noext: str, *, dark: str | None = None, dark_root: str | None = None,
              flat: str | None = None, bias: str | None = None, debayer: bool = True,
              findstar_sigma: float = 0.5, sig_low: float = 3.0, sig_high: float = 3.0,
              norm: str = "addscale", bit16: bool = True, mem_ratio: float = 0.9,
              timeout: float = 7200.0, log=print) -> str:
    """**OSC 原始亮场 → master(零 PixInsight)**。
    light_dir=原始亮场目录(自动挑 .fit、排除 .jpg 预览);**可传目录列表**(多晚合并叠加);
    dark/flat/bias=master 定标帧文件(可选;Seestar 一体机无定标帧留空);
    **dark_root**=暗场根目录(如 `DWARF_DARK/`)→ 按亮场曝光/增益/温度**自动选最近那组**并整合成 master(dark 未显式给时)。
    返回 <out>.fit。流程:挑 .fit 暂存 → convert(去马赛克)→ 可选 calibrate → 清 cache + setfindstar 配准 → setmem 整合。"""
    R = str(config.RUN_DIR)
    # 【自动选暗场】给了暗场/校准场根目录且没显式给 master 暗场 → 用共享 calib_match 按曝光/增益/温度选最近那组 + 整合
    if dark_root and not dark:
        from . import calib_match
        _ref_light = light_dir if isinstance(light_dir, str) else light_dir[0]
        found = calib_match.auto_calib(dark_root, _ref_light, kinds=("dark",), log=log)
        if found.get("dark"):
            dark = make_master(found["dark"]["dir"], os.path.join(R, "_auto_dark"), method="med",
                               mem_ratio=mem_ratio, timeout=timeout, log=log)
        else:
            log("[stack] 未选到匹配暗场 → 按 lights-only 叠加(无暗场校准)")
    work = os.path.join(R, "_stack_osc").replace("\\", "/")
    stage, proc = f"{work}/stage", f"{work}/proc"
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(proc, exist_ok=True)
    t0 = time.time()
    n = _stage_lights(light_dir, stage, log)
    calibrated = bool(dark or flat or bias)
    out = str(out_noext).replace("\\", "/")
    if out.lower().endswith((".fit", ".fits")):
        out = out.rsplit(".", 1)[0]

    # ① convert(去马赛克;若后面 calibrate 则由 calibrate 去马赛克)
    conv = "convert light -out=" + proc + ("" if calibrated else (" -debayer" if debayer else ""))
    o = _run_siril([f'cd "{stage}"', conv], timeout=timeout, log=log, tag="conv", bit16=bit16)
    if not glob.glob(f"{proc}/light_*.fit"):
        raise RuntimeError("convert 失败(无输出帧):" + _tail(o))
    seq = "light_"
    log(f"[stack] convert 去马赛克完成 {len(glob.glob(f'{proc}/light_*.fit'))} 帧")

    # ②(可选)calibrate 校准 + 去马赛克
    if calibrated:
        # 【坑】-dark=/-flat=/-bias= **不能带引号**(同 -out=:Siril 会把引号当进路径→找不到+追加扩展名)。
        #   master 定标帧存在 _run(无空格),不加引号安全。
        cal = "calibrate light_"
        if dark:
            cal += f" -dark={dark}"
        if flat:
            cal += f" -flat={flat}"
        if bias:
            cal += f" -bias={bias}"
        cal += " -cfa -equalize_cfa" + (" -debayer" if debayer else "")
        o = _run_siril([f'cd "{proc}"', cal], timeout=timeout, log=log, tag="cal", bit16=bit16)
        pp = glob.glob(f"{proc}/pp_light_*.fit")
        if not pp:
            raise RuntimeError("校准失败(无 pp_ 帧):" + _tail(o))
        seq = "pp_light_"
        log(f"[stack] 校准+去马赛克完成 {len(pp)} 帧")

    # ③ 配准:**清 cache(旧星表)+ 降星点阈值(线性帧星弱)**
    if os.path.exists(f"{proc}/cache"):
        shutil.rmtree(f"{proc}/cache", ignore_errors=True)
    for f in glob.glob(f"{proc}/*.lst"):
        os.remove(f)
    o = _run_siril([f'cd "{proc}"', f"setfindstar -sigma={findstar_sigma} -roundness=0.4",
                    f"register {seq}"], timeout=timeout, log=log, tag="reg", bit16=bit16)
    rseq = "r_" + seq
    if not glob.glob(f"{proc}/{rseq}.seq"):
        raise RuntimeError("配准失败(星点不足?可再降 findstar_sigma):" + _tail(o))
    log(f"[stack] 配准完成(setfindstar sigma={findstar_sigma})")

    # ④ 整合:**setmem 提内存上限**(大帧数彩色栈,单遍内存整合免反复读盘)
    o = _run_siril([f'cd "{proc}"',
                    f"stack {rseq} rej {sig_low} {sig_high} -norm={norm} -output_norm -out={out}"],
                   timeout=timeout, log=log, tag="stk", mem_ratio=mem_ratio, bit16=bit16)
    if not glob.glob(f"{out}.fit*"):
        raise RuntimeError("整合失败:" + _tail(o))
    log(f"[stack] 整合完成 {n} 帧 → {out}.fit(全程零 PixInsight,用时 {int(time.time()-t0)}s)")
    return out + ".fit"


def _coverage_crop_rect(master_fit: str, *, margin: float = 0.03, thr_mult: float = 1.2,
                        max_frac: float = 0.15, log=print):
    """**多晚叠加公共覆盖区裁剪**(拉伸前用):两晚角度差→部分覆盖区只有单晚帧、噪声高约√(N总/N单)。
    在**线性 master** 上按局部噪声(高频中位)网格检测:逐边"该边噪声中位 > thr_mult×典型"内缩
    (抓右/下这类整边接缝)+ 四周固定 margin 安全边距(兜住对角楔形 corner)。返回 (x,y,w,h) 或 None。"""
    try:
        import cv2
        import numpy as np
        from astropy.io import fits
    except ImportError:
        log("[stack] 覆盖区裁剪跳过(缺 cv2/numpy/astropy)")
        return None
    d = np.squeeze(fits.getdata(master_fit).astype(np.float32))
    dd = d.mean(0) if d.ndim == 3 else d
    if dd.max() > 1.5:
        dd = dd / 65535.0
    h, w = dd.shape
    hf = np.abs(dd - cv2.GaussianBlur(dd, (0, 0), 2))
    GY, GX = 30, max(1, int(round(30 * w / h)))
    gy, gx = h // GY, w // GX
    grid = np.array([[np.median(hf[i * gy:(i + 1) * gy, j * gx:(j + 1) * gx])
                      for j in range(GX)] for i in range(GY)])
    thr = thr_mult * float(np.median(grid))

    def _trim(is_row):
        n = GY if is_row else GX
        lo, hi = 0, n
        for i in range(int(n * max_frac)):
            line = grid[i, :] if is_row else grid[:, i]
            if float(np.median(line)) > thr:
                lo = i + 1
            else:
                break
        for i in range(int(n * max_frac)):
            line = grid[n - 1 - i, :] if is_row else grid[:, n - 1 - i]
            if float(np.median(line)) > thr:
                hi = n - 1 - i
            else:
                break
        return lo, hi
    r0, r1 = _trim(True)
    c0, c1 = _trim(False)
    mx, my = int(w * margin), int(h * margin)                  # 安全边距(兜对角楔形)
    x, y = c0 * gx + mx, r0 * gy + my
    ww, hh = (c1 - c0) * gx - 2 * mx, (r1 - r0) * gy - 2 * my
    if ww <= 0 or hh <= 0 or ww * hh > 0.995 * w * h:          # 基本全覆盖 → 不裁
        return None
    log(f"[stack] 覆盖区裁剪:裁掉 左{c0*gx+mx} 右{w-c1*gx+mx} 上{r0*gy+my} 下{h-r1*gy+my}px "
        f"→ 保留 {ww*hh/(w*h)*100:.1f}%(去多晚部分覆盖接缝,拉伸前)")
    return (x, y, ww, hh)


def _apply_crop(master_fit: str, rect, *, bit16: bool, timeout: float, log=print) -> str:
    """Siril crop 裁 master(原地覆盖),rect=(x,y,w,h)。返回原路径。"""
    x, y, w, h = rect
    base = os.path.basename(master_fit).rsplit(".", 1)[0]
    d = os.path.dirname(master_fit).replace("\\", "/")
    _run_siril([f'cd "{d}"', f"load {base}", f"crop {x} {y} {w} {h}", f"save {base}"],
               timeout=timeout, log=log, tag="cvcrop", bit16=bit16)
    return master_fit


def _master_if_dir(path, tag: str, *, method: str, mem_ratio: float, timeout: float, log) -> str | None:
    """path 是原始定标帧目录 → make_master;是 master 文件 → 直接用;None → None。"""
    if not path:
        return None
    if os.path.isdir(path):
        return make_master(path, os.path.join(str(config.RUN_DIR), tag), method=method,
                           mem_ratio=mem_ratio, timeout=timeout, log=log)
    return str(path).replace("\\", "/")


def stack_osc_pernight(nights, out_noext: str, *, dark=None, bias=None, debayer: bool = True,
                       findstar_sigma: float = 0.5, sig_low: float = 3.0, sig_high: float = 3.0,
                       norm: str = "addscale", bit16: bool = True, mem_ratio: float = 0.9,
                       coverage_crop: bool = True, timeout: float = 7200.0, log=print) -> str:
    """**逐晚平场校准叠加(零 PixInsight)**。多晚数据每晚有各自平场(暗角/灰尘随夜变,同一张 flat 校不准)
    时,**每晚用自己的 flat(+ 共享或逐晚的 dark/bias)各自 calibrate → 汇合所有已校准帧 → 统一配准整合**。
    nights = [{"lights": 目录/列表, "flat": master.fit 或 原始平场目录, ["dark"/"bias": 该晚覆盖]}, ...]
    dark/bias = 共享 master 文件或原始目录(整晚共用;个别晚可在 night dict 里覆盖)。返回 <out>.fit。
    对比 stack_osc(单 flat 全帧校准),此函数专治多晚不同平场。"""
    R = str(config.RUN_DIR)
    work = os.path.join(R, "_stack_pn").replace("\\", "/")
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    pool, reg = f"{work}/pool", f"{work}/reg"
    os.makedirs(pool, exist_ok=True)
    os.makedirs(reg, exist_ok=True)
    out = str(out_noext).replace("\\", "/")
    if out.lower().endswith((".fit", ".fits")):
        out = out.rsplit(".", 1)[0]
    t0 = time.time()

    dark_shared = _master_if_dir(dark, "_pn_dark", method="med", mem_ratio=mem_ratio, timeout=timeout, log=log)
    bias_shared = _master_if_dir(bias, "_pn_bias", method="med", mem_ratio=mem_ratio, timeout=timeout, log=log)

    total = 0
    for i, night in enumerate(nights):
        ndark = _master_if_dir(night["dark"], f"_pn_dark{i}", method="med", mem_ratio=mem_ratio,
                               timeout=timeout, log=log) if night.get("dark") else dark_shared
        nbias = _master_if_dir(night["bias"], f"_pn_bias{i}", method="med", mem_ratio=mem_ratio,
                               timeout=timeout, log=log) if night.get("bias") else bias_shared
        nflat = _master_if_dir(night.get("flat"), f"_pn_flat{i}", method="rej", mem_ratio=mem_ratio,
                               timeout=timeout, log=log)
        stage_i, proc_i = f"{work}/n{i}/stage", f"{work}/n{i}/proc"
        os.makedirs(proc_i, exist_ok=True)
        ncnt = _stage_lights(night["lights"], stage_i, log)
        log(f"[stack] 第{i+1}/{len(nights)}晚:{ncnt}帧亮场 | flat={'有' if nflat else '无'} "
            f"dark={'有' if ndark else '无'} bias={'有' if nbias else '无'}")
        # convert(不去马赛克;由 calibrate 去)→ calibrate(该晚 flat)→ pp_light_
        _run_siril([f'cd "{stage_i}"', f"convert light -out={proc_i}"], timeout=timeout, log=log,
                   tag=f"conv{i}", bit16=bit16)
        if not glob.glob(f"{proc_i}/light_*.fit"):
            raise RuntimeError(f"第{i+1}晚 convert 失败(无输出帧)")
        cal = "calibrate light_"
        if ndark:
            cal += f" -dark={ndark}"
        if nflat:
            cal += f" -flat={nflat}"
        if nbias:
            cal += f" -bias={nbias}"
        cal += " -cfa -equalize_cfa" + (" -debayer" if debayer else "")
        o = _run_siril([f'cd "{proc_i}"', cal], timeout=timeout, log=log, tag=f"cal{i}", bit16=bit16)
        pp = sorted(glob.glob(f"{proc_i}/pp_light_*.fit"))
        if not pp:
            raise RuntimeError(f"第{i+1}晚校准失败(无 pp_ 帧):" + _tail(o))
        for f in pp:                                            # 汇合池,加晚前缀防重名
            shutil.move(f, f"{pool}/pn{i:02d}_{os.path.basename(f)}")
        total += len(pp)
        log(f"[stack] 第{i+1}晚校准完成 {len(pp)} 帧 → 汇合池")

    # 汇合池(已去马赛克的 3 图层 RGB 帧)→ convert 成序列 → 配准 → 整合
    o = _run_siril([f'cd "{pool}"', f"convert light -out={reg}"], timeout=timeout, log=log,
                   tag="poolconv", bit16=bit16)
    if not glob.glob(f"{reg}/light_*.fit"):
        raise RuntimeError("汇合池 convert 失败:" + _tail(o))
    if os.path.exists(f"{reg}/cache"):
        shutil.rmtree(f"{reg}/cache", ignore_errors=True)
    for f in glob.glob(f"{reg}/*.lst"):
        os.remove(f)
    o = _run_siril([f'cd "{reg}"', f"setfindstar -sigma={findstar_sigma} -roundness=0.4",
                    "register light_"], timeout=timeout, log=log, tag="reg", bit16=bit16)
    if not glob.glob(f"{reg}/r_light_.seq"):
        raise RuntimeError("配准失败(逐晚汇合池,星点不足?):" + _tail(o))
    o = _run_siril([f'cd "{reg}"',
                    f"stack r_light_ rej {sig_low} {sig_high} -norm={norm} -output_norm -out={out}"],
                   timeout=timeout, log=log, tag="stk", mem_ratio=mem_ratio, bit16=bit16)
    if not glob.glob(f"{out}.fit*"):
        raise RuntimeError("整合失败(逐晚汇合池):" + _tail(o))
    # 多晚公共覆盖区裁剪(**拉伸前**):去两晚角度差留下的部分覆盖接缝(右/下边+对角楔形)
    if coverage_crop and len(nights) > 1:
        rect = _coverage_crop_rect(out + ".fit", log=log)
        if rect:
            _apply_crop(out + ".fit", rect, bit16=bit16, timeout=timeout, log=log)
    log(f"[stack] 逐晚平场叠加完成:{len(nights)} 晚共 {total} 帧 → {out}.fit"
        f"(全程零 PixInsight,用时 {int(time.time()-t0)}s)")
    return out + ".fit"
