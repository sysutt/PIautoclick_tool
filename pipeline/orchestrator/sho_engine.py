"""无 PI SHO 引擎(zero-PixInsight narrowband SHO pipeline)。

从 WBPP registered 子帧(或已整合 master)到彩色成片,**全程不碰 PixInsight**,
用 Siril + StarNet2 + GraXpert/DeepSNR + numpy。SH2-132 / NGC7380 真机验证(2026-08-12)。

管线(每步都有踩坑固化,见注释):
  ① Siril 整合(convert+stack registered 子帧)—— stack_registered()
  ② 各通道 crop+subsky+适度 autostretch → StarNet2 去星(适度拉伸给 StarNet2 好输入)
  ③ GraXpert AI 降噪(通道级,**揭示前**,噪小高效)—— 可选
  ④ GHS 温和揭示(ght,**LP 护背景**,别过度——过度会冲淡暖红/抬 OIII 盖过 SII)
  ⑤ linear_match 通道平衡(把弱 SII/OIII 提到和 Ha 可比 → 出得来金/蓝;别 match 过头变灰)
  ⑥ **比例控制器调色** ratio_recolor()(用户核心洞见:SHO 调色=控 RGB 比例)
  ⑦ DeepSNR 降噪**彩色合成图**(比 GraXpert 强、能直接吃彩色;GraXpert 彩色 TIFF 会卡死)
  ⑧ hotpix_remove() 去 SII 弱通道残留热点(提红+饱和会放大成红点)
  ⑨ RGB 彩色星点(RGB 合成→StarNet2 纯星点层→screen 合回);无 RGB 则星点去饱和

【铁律】
- 去星/降噪/调色都**只对分出的层做**;星点转色/调色绝不带星云(见 [[pi-sho-narrowband]])。
- **DeepSNR 输出 FITS 会上下翻转**(FITS 底朝上约定)→ 降噪彩色合成图时让它**输出 PNG/TIFF**,numpy 直接读,不走 Siril FITS round-trip。
- **揭示别过度**:过度揭示把暗部 OIII/Ha 抬起盖过 SII → 核心从暖红变冷;过度提亮(gamma 太低)冲淡饱和/红。
- 暗目标黑边检测别用信号阈值(会误裁成窄条),从"覆盖区占比"推进。
"""
from __future__ import annotations

import os
import subprocess

import numpy as np
try:
    import cv2
except Exception:  # cv2 是降噪/热点/合星的硬依赖
    cv2 = None
from PIL import Image

from . import config, siril, graxpert


# 调色预设:一组比例旋钮 = 一个 palette(用户框架)。见 ratio_recolor 各参数含义。
PRESETS: dict[str, dict] = {
    # 暖橙 salmon(Ha 主导发射星云,如 SH2-132):平均中性去绿把 G 压到 R,B 之间 + 高 kr 提弱 SII → 暖红;
    #   核心暖红(R>G>B)、外围红 Ha 铺开。gamma 别太低(0.68 冲淡红;0.82 红浓)。
    "warm": dict(kr=2.0, kg=1.0, kb=1.05, clamp=1.0, clamp_mode="avg",
                 sat=0.35, preserve_lum=True, gamma=0.82, star_satu=1.3),
    # 金蓝 goldblue(OIII 有料,如 NGC7380 巫师):**avg 去绿(和 warm 同)把黄绿转金** + 提蓝(kb1.2)出蓝核。
    #   【坑】曾用 clamp_mode="max" → 只留黄绿+青、出不来金蓝(NGC7380 实测);avg 才对。核心蓝浓度靠 kb。
    "goldblue": dict(kr=1.8, kg=1.0, kb=1.2, clamp=1.0, clamp_mode="avg",
                     sat=0.4, preserve_lum=True, gamma=0.9, star_satu=1.2),
}

_NM = {"S": "SII", "H": "Ha", "O": "OIII", "R": "Red", "G": "Green", "B": "Blue"}


# ── ① 整合 ──────────────────────────────────────────────────────────────────
def stack_registered(src_dir: str, out_noext: str, *, sig_low: float = 3.0,
                     sig_high: float = 3.0, norm: str = "addscale",
                     timeout: float = 1800.0) -> str:
    """Siril 整合一个滤镜目录下的**已对齐(registered)**子帧 → master。零 PI。
    convert(转序列)→ stack rej(winsorized sigma 抑制)→ -output_norm 归一 [0,1]。返回 <out>.fit。
    已对齐故跳过 register。多夜同滤镜请先把子帧归拢到一个目录(见 driver 里的 shutil 拷贝)。"""
    R = str(config.RUN_DIR)
    work = os.path.join(R, "_sho_seq")
    os.makedirs(work, exist_ok=True)
    base = "sq" + os.path.basename(out_noext).replace("-", "").replace(".", "")[:12]
    out = str(out_noext).replace("\\", "/")
    for e in (".fit", ".fits", ".xisf"):
        if out.lower().endswith(e):
            out = out[:-len(e)]
    ok, _ = siril.run_script(
        [f'cd "{str(src_dir).replace(chr(92), "/")}"', f"convert {base} -out={work}",
         f"cd {work}", f"stack {base} rej {sig_low} {sig_high} -norm={norm} -output_norm -out={out}"],
        timeout=timeout)
    final = out + ".fit"
    if not os.path.exists(final):
        raise RuntimeError(f"Siril 整合失败(无 {final})")
    return final


# ── ⑥ 比例控制器(调色心脏)────────────────────────────────────────────────
def ratio_recolor(S: np.ndarray, H: np.ndarray, O: np.ndarray, *, kr: float = 2.0,
                  kg: float = 1.0, kb: float = 1.05, clamp: float = 1.0,
                  clamp_mode: str = "avg", sat: float = 0.5,
                  preserve_lum: bool = True) -> np.ndarray:
    """SHO 调色 = 控制 R:G:B 比例(用户核心洞见)。输入三通道(已背景减到≈0 的 [0,1] 数组,S→R/H→G/O→B)。
      kr/kg/kb  : 三通道增益(整体色调;暖调高 kr 提弱 SII)。
      clamp     : 去绿力度 0..1(=比例钳制;1=全钳)。
      clamp_mode: "avg"(G→(R+B)/2,暖调必用,把 G 压到 R 之下出暖色)/ "max"(G→max(R,B),保青核,金蓝用)。
      sat       : 从灰(1:1:1)推开的幅度。
      preserve_lum: 去绿只改色相、把亮度还原(标准 SCNR 行为,防去绿后星云变暗)。
    返回 [0,1] 的 HxWx3。"""
    Rr = np.clip(S, 0, 1) * kr
    Gg = np.clip(H, 0, 1) * kg
    Bb = np.clip(O, 0, 1) * kb
    lum0 = (Rr + Gg + Bb) / 3.0
    ref = (Rr + Bb) / 2.0 if clamp_mode == "avg" else np.maximum(Rr, Bb)
    Gg = Gg - clamp * np.maximum(0.0, Gg - ref)          # 去绿 = 比例钳制
    if preserve_lum:
        sc = lum0 / ((Rr + Gg + Bb) / 3.0 + 1e-4)
        Rr, Gg, Bb = Rr * sc, Gg * sc, Bb * sc
    lum = (Rr + Gg + Bb) / 3.0
    out = np.stack([lum + (1 + sat) * (Rr - lum),
                    lum + (1 + sat) * (Gg - lum),
                    lum + (1 + sat) * (Bb - lum)], axis=-1)
    return np.clip(out, 0, 1)


# ── ⑧ 热点去除 ───────────────────────────────────────────────────────────────
def hotpix_remove(img: np.ndarray, thr: float = 0.05) -> np.ndarray:
    """去孤立热点/坏点(SII 弱通道残留热点被提红+饱和放大成红点)。逐通道 3x3 中值,
    只替换"比局部中值亮出 thr"的孤立点 → 不伤扩展星云结构、不碰星点(星点在独立层)。"""
    if cv2 is None:
        return img
    out = img.copy()
    for c in range(3):
        ch = img[..., c].astype(np.float32)
        med = cv2.medianBlur(ch, 3)
        m = (ch - med) > thr
        out[..., c][m] = med[m]
    return out


# ── 内部工具 ─────────────────────────────────────────────────────────────────
def _bg_sub(a: np.ndarray, frac: float = 0.08) -> np.ndarray:
    """减角落中位背景 → 比例干净。"""
    h, w = a.shape[:2]
    return a - np.median(a[:int(h * frac), :int(w * frac)])


def _load_mono(fits_path: str, tag: str) -> np.ndarray:
    """Siril 载 FITS → savejpg → numpy 灰度 [0,1](8bit 足够调色)。"""
    R = str(config.RUN_DIR)
    siril.run_script([f"cd {R}", f"load {os.path.basename(fits_path)}", f"savejpg {tag} 95"], timeout=600)
    return np.asarray(Image.open(f"{R}/{tag}.jpg").convert("L")).astype(np.float32) / 255.0


def detect_crop(master_fits: str, target_bg: float = 0.10) -> str:
    """从一个 master 检覆盖区(去多夜对齐黑边)。信号够时按"覆盖占比"推进,返回 "x y w h";全覆盖返回 None。"""
    R = str(config.RUN_DIR)
    siril.run_script([f"cd {R}", f"load {os.path.basename(master_fits)}", "subsky 1",
                      f"autostretch -2.8 {target_bg}", "savejpg _crop_det 92"], timeout=600)
    im = np.asarray(Image.open(f"{R}/_crop_det.jpg").convert("L")).astype(np.float32) / 255.0
    H, W = im.shape
    cov = (im > 0.05)
    rc, cc = cov.mean(1), cov.mean(0)

    def edge(v, e=False):
        rr = range(len(v) - 1, -1, -1) if e else range(len(v))
        for i in rr:
            if v[i] > 0.5:
                return i
        return 0
    top, bot, left, right = edge(rc), edge(rc, True), edge(cc), edge(cc, True)
    sx, sy = int(W * 0.006), int(H * 0.006)
    x, y, w, h = left + sx, top + sy, (right - left + 1) - 2 * sx, (bot - top + 1) - 2 * sy
    if w * h > 0.985 * W * H:          # 基本全覆盖 → 不裁
        return None
    return f"{x} {y} {w} {h}"


# ── 主编排器 ─────────────────────────────────────────────────────────────────
def run_sho(masters: dict, out_noext: str, *, rgb_masters: dict | None = None,
            palette: str = "warm", crop: str | None = None, stretch_bg: float = 0.16,
            reveal: list[str] | None = None, denoise_channels: bool = True,
            deepsnr_composite: bool = True, hotpix: bool = True,
            overrides: dict | None = None, timeout: float = 1800.0) -> str:
    """无 PI SHO 全流程编排。masters={"S","H","O"}(整合好的 master 路径);
    rgb_masters={"R","G","B"}(可选,做 RGB 彩色星点;无则星点去饱和)。palette: PRESETS 键。
    返回成片 <out_noext>.png。各步见模块头注释。overrides 覆盖预设旋钮。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python(cv2)做降噪/热点/合星")
    R = str(config.RUN_DIR)
    p = {**PRESETS[palette], **(overrides or {})}
    reveal = reveal if reveal is not None else ["ght -D=3.0 -B=0 -LP=0.14 -SP=0.28 -HP=0.78"]
    if crop is None:
        crop = detect_crop(masters["H"], stretch_bg)
    print(f"[sho] palette={palette} crop={crop} 旋钮={p}")

    # ②③ 各通道:crop+subsky+适度拉伸 → StarNet2 去星 → [GraXpert 通道降噪]
    sn = siril.starnet_exe()
    if not sn:
        raise RuntimeError("StarNet2 CLI 不可用(配 starnet_path)")
    for nm in "SHO":
        cmds = [f"cd {R}", f"load {str(masters[nm]).replace(chr(92), '/')}"]
        if crop:
            cmds.append("crop " + crop)
        cmds += ["subsky 1", f"autostretch -2.8 {stretch_bg}", f"save _e_{nm}"]
        siril.run_script(cmds, timeout=timeout)
        subprocess.run([sn, "-i", f"{R}/_e_{nm}.fit", "-o", f"{R}/_sl_{nm}.fit", "-s", "256"],
                       capture_output=True, text=True, timeout=timeout)
        if denoise_channels:
            try:
                dn = graxpert.denoise(f"{R}/_sl_{nm}.fit", f"{R}/_dn_{nm}", strength=0.6,
                                      gpu=True, timeout=timeout)
                # GraXpert 输出可能 .fits;统一转存 _sl_{nm}.fit 供下游
                siril.run_script([f"cd {R}", f"load {os.path.basename(dn)}", f"save _sl_{nm}"], timeout=timeout)
            except Exception as e:
                print(f"  [warn] GraXpert 降噪 {nm} 跳过:{str(e)[:120]}")

    # ④⑤ GHS 温和揭示(LP 护背景)+ linear_match 平衡
    for nm in "SHO":
        siril.run_script([f"cd {R}", f"load _sl_{nm}"] + reveal + [f"save _r_{nm}"], timeout=timeout)
    siril.run_script([f"cd {R}", "load _r_S", "linear_match _r_H 0 0.92", "save _r_S"], timeout=timeout)
    siril.run_script([f"cd {R}", "load _r_O", "linear_match _r_H 0 0.92", "save _r_O"], timeout=timeout)

    # ⑥ 比例控制器调色 + gamma 提亮
    S = _bg_sub(_load_mono(f"{R}/_r_S.fit", "_rv_S"))
    H = _bg_sub(_load_mono(f"{R}/_r_H.fit", "_rv_H"))
    O = _bg_sub(_load_mono(f"{R}/_r_O.fit", "_rv_O"))
    neb = ratio_recolor(S, H, O, kr=p["kr"], kg=p["kg"], kb=p["kb"], clamp=p["clamp"],
                        clamp_mode=p["clamp_mode"], sat=p["sat"], preserve_lum=p["preserve_lum"])
    neb = np.clip(neb, 0, 1) ** p["gamma"]

    # ⑦ DeepSNR 降噪彩色合成图(输出 PNG 避免 FITS 翻转);无 DeepSNR 则跳过
    if deepsnr_composite and siril.deepsnr_exe():
        cv2.imwrite(f"{R}/_nebc.tiff", cv2.cvtColor((neb * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))
        subprocess.run([siril.deepsnr_exe(), "-i", f"{R}/_nebc.tiff", "-o", f"{R}/_nebc_dn.png",
                        "-m", "2", "-s", "480", "-q"], capture_output=True, text=True, timeout=timeout)
        if os.path.exists(f"{R}/_nebc_dn.png"):
            dn = cv2.cvtColor(cv2.imread(f"{R}/_nebc_dn.png", cv2.IMREAD_UNCHANGED), cv2.COLOR_BGR2RGB).astype(np.float32) / 65535.0
            lum = dn.mean(2, keepdims=True)
            neb = np.clip(lum + 1.0 * (dn - lum), 0, 1)   # DeepSNR 后不再补饱和(之前 1.2 过艳,用户定降饱和)

    # ⑧ 热点去除
    if hotpix:
        neb = hotpix_remove(neb, 0.05)

    # ⑨ 星点:RGB 彩色(有 rgb_masters)/ 否则 SHO 去星层去饱和
    stars = _make_stars(masters, rgb_masters, crop, stretch_bg, p, sn, timeout)
    fin = 1 - (1 - neb) * (1 - np.clip(stars * 0.9, 0, 1))

    out = str(out_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    Image.fromarray((np.clip(fin, 0, 1) * 255).astype(np.uint8)).save(out + ".png", optimize=True)
    return out + ".png"


def _make_stars(masters, rgb_masters, crop, stretch_bg, p, sn, timeout) -> np.ndarray:
    """出星点层(numpy [0,1] RGB)。有 RGB master → 彩色星点;否则 SHO 合成去星层去饱和。"""
    R = str(config.RUN_DIR)
    if rgb_masters and all(k in rgb_masters for k in "RGB"):
        for nm in "RGB":
            cmds = [f"cd {R}", f"load {str(rgb_masters[nm]).replace(chr(92), '/')}"]
            if crop:
                cmds.append("crop " + crop)
            cmds += ["subsky 1", f"autostretch -2.8 {max(stretch_bg, 0.12)}", f"save _rc_{nm}"]
            siril.run_script(cmds, timeout=timeout)
        siril.run_script([f"cd {R}", "rgbcomp _rc_R _rc_G _rc_B -out=_rgbc", "load _rgbc", "subsky 1", "save _rgbc"], timeout=timeout)
        subprocess.run([sn, "-i", f"{R}/_rgbc.fit", "-o", f"{R}/_rgb_sl.fit", "-n", f"{R}/_rgb_st.fit", "-s", "256"],
                       capture_output=True, text=True, timeout=timeout)
        siril.run_script([f"cd {R}", "load _rgb_st", "savejpg _rgb_st 95"], timeout=timeout)
        st = np.asarray(Image.open(f"{R}/_rgb_st.jpg").convert("RGB")).astype(np.float32) / 255.0
    else:
        # 无 RGB:SHO 合成去星层(纯星点)→ 去饱和(消 SHO 星点的品红/纯蓝)
        siril.run_script([f"cd {R}", "rgbcomp _e_S _e_H _e_O -out=_sho_c", "load _sho_c", "save _sho_c"], timeout=timeout)
        subprocess.run([sn, "-i", f"{R}/_sho_c.fit", "-o", f"{R}/_sho_sl.fit", "-n", f"{R}/_sho_st.fit", "-s", "256"],
                       capture_output=True, text=True, timeout=timeout)
        siril.run_script([f"cd {R}", "load _sho_st", "savejpg _sho_st 95"], timeout=timeout)
        st = np.asarray(Image.open(f"{R}/_sho_st.jpg").convert("RGB")).astype(np.float32) / 255.0
        lum = st.mean(2, keepdims=True)
        st = np.clip(lum + 0.2 * (st - lum), 0, 1)     # 去饱和到近中性
    return np.clip(st - np.median(st.reshape(-1, 3), 0), 0, 1)


# ── 从 registered 目录一把梭(GUI 用)──────────────────────────────────────────
def _classify_filter(tok: str) -> str | None:
    """WBPP 滤镜 token → 通道字母。支持全名(Ha/Oiii/Sii/Red/Green/Blue)和多夜前缀(d1h/d2o/d3s/d3r..)。"""
    t = tok.lower()
    for key, letter in (("sii", "S"), ("oiii", "O"), ("halpha", "H"), ("ha", "H"),
                        ("red", "R"), ("green", "G"), ("blue", "B")):
        if key in t:
            return letter
    return {"h": "H", "o": "O", "s": "S", "r": "R", "g": "G", "b": "B"}.get(t[-1:]) if t else None


def run_sho_from_dir(registered_dir: str, out_noext: str, *, palette: str = "goldblue",
                     crop: str | None = None, timeout: float = 1800.0, log=print) -> str:
    """从 WBPP registered 目录(含 Light_..._FILTER-<x>_mono 子目录)**一把梭出无 PI SHO 成片**:
    自动按 FILTER 分类 S/H/O(+可选 RGB 做彩色星点)→ 逐通道 Siril 整合(多夜归拢)→ run_sho()。GUI 入口。"""
    import glob
    import re
    import shutil
    R = str(config.RUN_DIR)
    groups: dict[str, list[str]] = {}
    for sub in sorted(glob.glob(os.path.join(registered_dir, "*"))):
        if not os.path.isdir(sub):
            continue
        m = re.search(r"FILTER-([^_]+)_", os.path.basename(sub))
        if not m:
            continue
        letter = _classify_filter(m.group(1))
        if not letter:
            continue
        xs = [x for x in glob.glob(os.path.join(sub, "*.xisf")) if not x.lower().endswith(".xdrz")]
        groups.setdefault(letter, []).extend(xs)
    for need in "SHO":
        if not groups.get(need):
            raise RuntimeError(f"registered 目录缺 {_NM[need]} 通道(找不到 FILTER-{need}* 子目录)")

    masters: dict[str, str] = {}
    rgb: dict[str, str] = {}
    for letter, subs in groups.items():
        d = os.path.join(R, f"_int_{letter}")
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for x in subs:
            shutil.copy2(x, d)
        log(f"[sho] 整合 {_NM[letter]}: {len(subs)} 帧")
        mst = stack_registered(d, os.path.join(R, f"eng_{letter}"), timeout=timeout)
        (masters if letter in "SHO" else rgb)[letter] = mst

    rgb_masters = rgb if all(k in rgb for k in "RGB") else None
    log(f"[sho] 整合完,RGB 彩色星点:{'有' if rgb_masters else '无(星点去饱和)'};开始后期(palette={palette})")
    return run_sho(masters, out_noext, rgb_masters=rgb_masters, palette=palette, crop=crop, timeout=timeout)
