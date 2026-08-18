"""无 PI HOO 双窄带引擎(zero-PixInsight OSC dual-narrowband HOO pipeline)。

从 OSC 双窄带 master(彩色相机/智能望远镜 + Ha+OIII 双窄带滤镜)到彩色成片,**全程不碰 PixInsight**。
照搬 PI run_hoo 的阶段序,复用 SHO 基建(StarNet2/DeepSNR)。IC1805+SH2-308 真机验证(2026-08-13)。
见 [[hoo-zeropi-engine]]。

管线(**阶段序照 PI 铁律**):
  ① **先裁黑边**(黑边污染梯度拟合)—— PI 铁律。
  ② **梯度校正在线性、拉伸前**(PI 最大铁律;我曾在拉伸后治全白费)—— GraXpert bge(AI 背景提取=ABE 等价)。
  ③ Siril `split` → **Ha=R, OIII=G**(OSC 双窄带)。
  ④ 各通道 autostretch → StarNet2 去星 → **Ha/OIII 分别揭示**(弱的揭示更狠)。
  ⑤ HOO 合成 R=Ha,G=OIII,B=OIII + gamma 提亮弱信号 + 饱和。**不做 linear_match**(会把强信号压到弱信号)。
  ⑥ DeepSNR 降噪彩色 + 星点(原图去星层去饱和,消双窄带绿/品红星)。
  ⑦ **背景抬中性灰**(通用铁律,绝不死黑)。

【铁律】
- **梯度必须线性阶段治**:线性 median 看着平,但 faint glow 被激进 reveal 放大成"梯度";拉伸后治治不干净。
- **GraXpert bge 喂 TIFF**(读不了 Siril 非标 FITS 头)+ **smoothing≥0.7**(0.3 会把扩散弱泡当背景吃掉)。
- **不做 linear_match**:OIII 主导目标(Ha 弱)把强 OIII 匹配到弱 Ha 会把泡压没。
- **背景绝不死黑**:成片最后各通道背景对齐抬到中性灰≈0.20(R=G=B)。
"""
from __future__ import annotations

import os
import subprocess

import numpy as np
try:
    import cv2
except Exception:
    cv2 = None
from PIL import Image

from . import config, siril, graxpert
from .sho_engine import _load_mono, _bg_sub, neutral_gray

# 预设:一组旋钮 = 一个 palette。reveal_ha/oiii_d = 各通道揭示强度(弱信号那个调大);
#   kg/kb = OIII→G/B 增益(kb 高出青);ha/oiii_gamma = 提亮弱信号;bg_sub_frac = 软减背景强度(小=保过渡带、消割裂);bg_gray = 背景中性灰目标。
PRESETS: dict[str, dict] = {
    # 经典青红双色(标准哈勃感,信号较均衡的目标如 IC1805)
    "classic": dict(reveal_ha_d=2.0, reveal_oiii_d=2.0, kg=1.10, kb=1.25,
                    ha_gamma=0.88, oiii_gamma=0.80, sat=0.45, bg_sub_frac=0.5, bg_gray=0.20),
    # OIII 主导(WR 泡如 SH2-308:Ha 弱→揭示狠、OIII 适度→不 blow 泡、提蓝出青泡)
    "oiii": dict(reveal_ha_d=2.2, reveal_oiii_d=1.8, kg=1.15, kb=1.35,
                 ha_gamma=0.85, oiii_gamma=0.70, sat=0.45, bg_sub_frac=0.45, bg_gray=0.20),
}


def _reveal(d: float, sp: float = 0.26, hp: float = 0.84, lp: float = 0.14) -> str:
    return f"ght -D={d} -B=0 -LP={lp} -SP={sp} -HP={hp}"


def _soft_knee(x: np.ndarray, knee: float = 0.80) -> np.ndarray:
    """**软膝压顶**(防拉伸削顶→平顶硬边→边缘锯齿):knee 以下原样,knee 以上用
    tanh 平滑压进 [knee,1](渐近不到 1)。替代 np.clip 的硬截断。
    NGC6992 实测:Ha 硬 clip 1.9% 面积 → 丝的顶部被削平成硬边,视觉上就是锯齿。"""
    k = float(knee)
    out = x.copy()
    hi = x > k
    if hi.any():
        out[hi] = k + (1.0 - k) * np.tanh((x[hi] - k) / max(1.0 - k, 1e-6))
    return np.clip(out, 0, 1)


def _softsub(a: np.ndarray, frac: float) -> np.ndarray:
    """软背景减:只减 frac× 角落背景(不减满)→ 保住星云外缘暗弱**过渡带**,消除星云"贴图"割裂感。
    全减(frac=1)+clip 会把"刚比背景亮一点"的外缘信号硬裁成 0 → 硬边贴在背景上(用户实测忌讳)。"""
    h, w = a.shape[:2]
    return np.clip(a - np.median(a[:int(h * 0.08), :int(w * 0.08)]) * frac, 0, 1)


def _neutralize_bg_color(img: np.ndarray, target: float = 0.20, log=print) -> np.ndarray:
    """**HOO 背景去 teal + 抬中性灰**(取代角落版 neutral_gray):双窄带里 OIII(→G/B)背景常高于
    Ha(→R)→ 整个背景发青。按**暗像素(背景,亮度下半)全局**稳健估各通道背景电平 → 逐通道对齐到
    最低通道(背景 R=G=B)→ 整体抬到中性灰 target(绝不死黑)。星云信号(高于背景)相对不动。
    **比 neutral_gray 只采两个角落稳**:角落常被星云丝/边缘块(如面纱右下红块)污染 → 反而把背景弄偏。"""
    L = img.mean(2)
    m = L < np.percentile(L, 55)
    if m.sum() < 1000:
        return neutral_gray(img, target=target)
    bg = np.array([float(np.median(img[..., c][m])) for c in range(3)])
    lo = float(bg.min())
    out = img.copy()
    for c in range(3):
        out[..., c] = out[..., c] - (bg[c] - lo)      # 逐通道对齐 → 背景中性
    out = np.clip(out - lo + target, 0, 1)             # 整体抬到中性灰 target
    log(f"[hoo] 背景去 teal + 抬灰:各通道背景 R{bg[0]*100:.1f} G{bg[1]*100:.1f} B{bg[2]*100:.1f} → 对齐中性 + 抬到 {target*100:.0f}")
    return out


# ── ② GraXpert 背景提取(喂 TIFF 避 FITS 头坑)──────────────────────────────────
def graxpert_bge_tiff(tif_path: str, out_noext: str, *, smoothing: float = 0.7,
                      timeout: float = 1800.0) -> str | None:
    """GraXpert AI 背景提取。**必须喂 TIFF**(GraXpert/astropy 读不了 Siril 非标 FITS 头卡片)。
    输出 .fits,返回可供 Siril `load` 的基名(无扩展);失败返回 None。smoothing 高保住扩散弱天体。"""
    exe = graxpert.graxpert_exe()
    if not exe:
        return None
    ver = graxpert.installed_bge_version() or "1.0.1"
    out = str(out_noext).replace("\\", "/")
    subprocess.run([exe, "-cli", "-cmd", "background-extraction", "-correction", "Subtraction",
                    "-smoothing", str(smoothing), "-gpu", "true", "-ai_version", ver,
                    "-output", out, str(tif_path).replace("\\", "/")],
                   capture_output=True, text=True, timeout=timeout)
    for e in (".fits", ".xisf", ".fit"):
        if os.path.exists(out + e):
            return os.path.basename(out)
    return None


# ── ①②③ 裁边 + 线性去梯度 + 提取 Ha/OIII ─────────────────────────────────────
def extract_haoiii(master: str, *, crop_margin: float = 0.03, bge: str = "subsky",
                   bge_smoothing: float = 0.85, bg_extract: str = "rbf",
                   timeout: float = 1800.0, log=print) -> tuple[str, str, str]:
    """OSC 双窄带 master → 裁黑边 → 线性去梯度 → split。返回 (去梯度master基名, Ha=_cR, OIII=_cG)。
    bge:去梯度法——
      "subsky"(默认):轻 subsky。**平背景 + 有真实弥漫星云的目标**(如 SH2-308)安全、不造暗环。
      "graxpert":GraXpert AI 去梯度(=ABE)。**真有复杂梯度**(光污染/暗角)时用;但对平背景+弥漫目标
                 会把弥漫星云和亮物外缘当背景**过度扣除 → 泡周围暗环(moat)+ 抹真实信号**,慎用。"""
    R = str(config.RUN_DIR)
    m = str(master).replace("\\", "/")
    siril.run_script([f"cd {R}", f'load "{m}"', "savetif _hoo_full"], timeout=timeout)
    a = cv2.imread(f"{R}/_hoo_full.tif", cv2.IMREAD_UNCHANGED)
    h, w = a.shape[:2]
    mx, my = int(w * crop_margin), int(h * crop_margin)   # ① 裁黑边(黑边污染梯度拟合)
    if bge == "graxpert":
        cv2.imwrite(f"{R}/_hoo_c.tif", a[my:h - my, mx:w - mx])
        src = graxpert_bge_tiff(f"{R}/_hoo_c.tif", f"{R}/_hoo_bge", smoothing=bge_smoothing, timeout=timeout)
        if src is None:
            log("[hoo] [!] GraXpert bge 失败/卡(GPU 争用?重启 GraXpert)→ 退 subsky")
            siril.run_script([f"cd {R}", "load _hoo_c", "subsky 1", "save _hoo_bge"], timeout=timeout)
            src = "_hoo_bge"
        else:
            log(f"[hoo] GraXpert bge 去梯度(smoothing={bge_smoothing})")
    else:   # subsky(默认,无 moat)
        # 【梯度】默认 **rbf**(径向基):`subsky 1` 一阶平面**建不了径向渐晕** → 成片"中间发黑、四周偏绿"
        #   (NGC6992 实测:中心 L17.9/G-R−2.7 → 角落 L21.3/G-R+1.6)。rbf/高阶才压得住径向。
        from .rgb_engine import _subsky_cmds
        siril.run_script([f"cd {R}", f'load "{m}"', f"crop {mx} {my} {w - 2 * mx} {h - 2 * my}"]
                         + _subsky_cmds(bg_extract) + ["save _hoo_bge"], timeout=timeout)
        src = "_hoo_bge"
        log(f"[hoo] subsky 去梯度(bg_extract={bg_extract};径向渐晕需 rbf/高阶,一阶平面压不住)")
    siril.run_script([f"cd {R}", f"load {src}", "split _cR _cG _cB"], timeout=timeout)   # ③ Ha=R, OIII=G
    return src, "_cR", "_cG"


# ── 主编排器 ─────────────────────────────────────────────────────────────────
def run_hoo(master: str, out_noext: str, *, palette: str = "oiii", bge: str = "subsky",
            crop_margin: float = 0.03, bge_smoothing: float = 0.85, stretch_bg: float = 0.16,
            bg_extract: str = "rbf", knee: float = 0.80,
            overrides: dict | None = None, timeout: float = 1800.0, log=print) -> str:
    """无 PI HOO 全流程。master=OSC 双窄带整合 master。palette: PRESETS 键
    ("oiii"=OIII 主导如 SH2-308 / "classic"=均衡青红如 IC1805)。
    bge: 去梯度法 "subsky"(默认,平背景+弥漫星云安全)/ "graxpert"(复杂梯度用)。返回成片 <out>.png。"""
    if cv2 is None:
        raise RuntimeError("需要 opencv-python(cv2)")
    sn = siril.starnet_exe()
    if not sn:
        raise RuntimeError("StarNet2 CLI 不可用(配 starnet_path)")
    R = str(config.RUN_DIR)
    p = {**PRESETS[palette], **(overrides or {})}
    log(f"[hoo] palette={palette} 旋钮={p}")

    # ①②③ 裁边 + 线性去梯度 + 提取
    bgesrc, ha_ch, oiii_ch = extract_haoiii(master, crop_margin=crop_margin, bge=bge,
                                            bge_smoothing=bge_smoothing, bg_extract=bg_extract,
                                            timeout=timeout, log=log)

    # ④ 各通道:去梯度(**逐通道**:Ha/OIII 渐晕曲线不同 → 不逐通道治就留径向色偏)→ autostretch
    #    → StarNet2 去星 → 分别揭示(弱信号揭示更狠)
    from .rgb_engine import _subsky_cmds
    revs = {"H": _reveal(p["reveal_ha_d"]), "O": _reveal(p["reveal_oiii_d"])}
    for ch, tag in ((ha_ch, "H"), (oiii_ch, "O")):
        siril.run_script([f"cd {R}", f"load {ch}"] + _subsky_cmds(bg_extract)
                         + [f"autostretch -2.8 {stretch_bg}", f"save _e_{tag}"], timeout=timeout)
        subprocess.run([sn, "-i", f"{R}/_e_{tag}.fit", "-o", f"{R}/_sl_{tag}.fit", "-s", "256"],
                       capture_output=True, text=True, timeout=timeout)
        siril.run_script([f"cd {R}", f"load _sl_{tag}", revs[tag], f"save _r_{tag}"], timeout=timeout)

    # ⑤ HOO 合成(R=Ha, G=OIII, B=OIII)+ gamma 提亮弱信号 + 饱和。**不 linear_match**
    #   软减背景(bg_sub_frac)保住星云外缘过渡带,消除"贴图"割裂感(全减会硬裁成硬边)。
    Ha = _softsub(_load_mono(f"{R}/_r_H.fit", "_rv_H"), p["bg_sub_frac"]) ** p["ha_gamma"]
    O = _softsub(_load_mono(f"{R}/_r_O.fit", "_rv_O"), p["bg_sub_frac"]) ** p["oiii_gamma"]
    # **软膝压顶代替硬 clip**:硬 clip 会把丝的顶部削平成硬边 → 视觉锯齿(NGC6992 实测 Ha clip 1.9%)。
    Rc, Gc, Bc = _soft_knee(Ha, knee), _soft_knee(O * p["kg"], knee), _soft_knee(O * p["kb"], knee)
    lum = (Rc + Gc + Bc) / 3.0
    s = p["sat"]
    neb = _soft_knee(np.stack([lum + (1 + s) * (Rc - lum), lum + (1 + s) * (Gc - lum),
                               lum + (1 + s) * (Bc - lum)], -1).clip(0, None), knee)

    # ⑥ DeepSNR 降噪彩色合成图(输出 PNG 避 FITS 翻转)
    if siril.deepsnr_exe():
        cv2.imwrite(f"{R}/_hnb.tiff", cv2.cvtColor((neb * 65535).astype(np.uint16), cv2.COLOR_RGB2BGR))
        subprocess.run([siril.deepsnr_exe(), "-i", f"{R}/_hnb.tiff", "-o", f"{R}/_hnb_dn.png",
                        "-m", "2", "-s", "480", "-q"], capture_output=True, text=True, timeout=timeout)
        if os.path.exists(f"{R}/_hnb_dn.png"):
            dn = cv2.cvtColor(cv2.imread(f"{R}/_hnb_dn.png", cv2.IMREAD_UNCHANGED), cv2.COLOR_BGR2RGB).astype(np.float32) / 65535.0
            l = dn.mean(2, keepdims=True)
            neb = np.clip(l + 1.0 * (dn - l), 0, 1)

    # 星点:去梯度后的 master(含星点)→ 拉伸 → StarNet2 星点层 → 去饱和 → screen
    siril.run_script([f"cd {R}", f"load {bgesrc}", "autostretch -2.8 0.16", "save _hrgb"], timeout=timeout)
    subprocess.run([sn, "-i", f"{R}/_hrgb.fit", "-o", f"{R}/_hrgb_sl.fit", "-n", f"{R}/_hrgb_st.fit", "-s", "256"],
                   capture_output=True, text=True, timeout=timeout)
    siril.run_script([f"cd {R}", "load _hrgb_st", "savejpg _hrgb_st 95"], timeout=timeout)
    st = np.asarray(Image.open(f"{R}/_hrgb_st.jpg").convert("RGB")).astype(np.float32) / 255.0
    st = np.clip(st - np.median(st.reshape(-1, 3), 0), 0, 1)
    lst = st.mean(2, keepdims=True)
    st = np.clip(lst + 0.25 * (st - lst), 0, 1)     # 双窄带星点去饱和到近中性
    fin = 1 - (1 - neb) * (1 - np.clip(st * 0.9, 0, 1))

    # ⑦ 先裁叠加抖动边缘带(线性只 +1%、拉伸后放大成亮/暗带,如底部带被搓成右下暗红 blob;HOO 边缘带
    #    较大 → max_frac 放宽 0.22)→ 再背景去 teal + 抬中性灰(在裁净的图上采样,边缘带不再污染 → 顺带改善发青)。
    from .rgb_engine import _autocrop_edges, remove_residual_glow
    fin = _autocrop_edges(fin, max_frac=0.22, log=log)
    # **径向背景收尾**:逐通道网格背景模型(天生治径向亮度+径向色偏);全局常数偏移治不了
    #   "中间发黑、四周偏绿"(NGC6992 实测中心↔角落 L 差 3.4、G-R 差 4.3)。强制开(HOO 必有渐晕差)。
    fin = remove_residual_glow(fin, mode="on", log=log)
    fin = _neutralize_bg_color(fin, target=p["bg_gray"], log=log)

    out = str(out_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    Image.fromarray((np.clip(fin, 0, 1) * 255).astype(np.uint8)).save(out + ".png", optimize=True)
    log(f"[hoo] 完成 → {out}.png(全程零 PixInsight)")
    return out + ".png"


# ── 从目录/文件一把梭(GUI 用)────────────────────────────────────────────────
def run_hoo_from_dir(src: str, out_noext: str, *, palette: str = "oiii",
                     timeout: float = 1800.0, log=print) -> str:
    """从 OSC 双窄带输入一把梭出 HOO 成片。src 可为单张整合 master 或 registered 子帧目录
    (目录则先 Siril 整合)。GUI 入口。"""
    import glob
    R = str(config.RUN_DIR)
    if os.path.isfile(src):
        master = src
    elif os.path.isdir(src):
        from .sho_engine import stack_registered
        import shutil
        subs = [x for x in glob.glob(os.path.join(src, "**", "*.xisf"), recursive=True)
                if not x.lower().endswith(".xdrz")] or glob.glob(os.path.join(src, "**", "*.fit*"), recursive=True)
        if not subs:
            raise RuntimeError(f"目录无可整合子帧:{src}")
        d = os.path.join(R, "_int_HOO")
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)
        for x in subs:
            shutil.copy2(x, d)
        log(f"[hoo] 整合 {len(subs)} 帧双窄带子帧")
        master = stack_registered(d, os.path.join(R, "eng_HOO"), timeout=timeout)
    else:
        raise RuntimeError(f"输入不存在:{src}")
    return run_hoo(master, out_noext, palette=palette, timeout=timeout, log=log)
