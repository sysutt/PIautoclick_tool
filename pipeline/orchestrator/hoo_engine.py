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
    "classic": dict(reveal_ha_d=2.4, reveal_oiii_d=2.4, kg=1.10, kb=1.25,
                    ha_gamma=0.80, oiii_gamma=0.70, sat=0.50, bg_sub_frac=0.5, bg_gray=0.20),
    # OIII 主导(WR 泡如 SH2-308:Ha 弱→揭示狠、OIII 适度→不 blow 泡、提蓝出青泡)
    "oiii": dict(reveal_ha_d=2.8, reveal_oiii_d=2.0, kg=1.15, kb=1.35,
                 ha_gamma=0.72, oiii_gamma=0.60, sat=0.55, bg_sub_frac=0.45, bg_gray=0.20),
}


def _reveal(d: float, sp: float = 0.26, hp: float = 0.84, lp: float = 0.14) -> str:
    return f"ght -D={d} -B=0 -LP={lp} -SP={sp} -HP={hp}"


def _softsub(a: np.ndarray, frac: float) -> np.ndarray:
    """软背景减:只减 frac× 角落背景(不减满)→ 保住星云外缘暗弱**过渡带**,消除星云"贴图"割裂感。
    全减(frac=1)+clip 会把"刚比背景亮一点"的外缘信号硬裁成 0 → 硬边贴在背景上(用户实测忌讳)。"""
    h, w = a.shape[:2]
    return np.clip(a - np.median(a[:int(h * 0.08), :int(w * 0.08)]) * frac, 0, 1)


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
                   bge_smoothing: float = 0.85, timeout: float = 1800.0, log=print) -> tuple[str, str, str]:
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
        siril.run_script([f"cd {R}", f'load "{m}"', f"crop {mx} {my} {w - 2 * mx} {h - 2 * my}",
                          "subsky 1", "save _hoo_bge"], timeout=timeout)
        src = "_hoo_bge"
        log("[hoo] subsky 去梯度(默认;平背景+弥漫星云安全,无 GraXpert 过度扣除的暗环)")
    siril.run_script([f"cd {R}", f"load {src}", "split _cR _cG _cB"], timeout=timeout)   # ③ Ha=R, OIII=G
    return src, "_cR", "_cG"


# ── 主编排器 ─────────────────────────────────────────────────────────────────
def run_hoo(master: str, out_noext: str, *, palette: str = "oiii", bge: str = "subsky",
            crop_margin: float = 0.03, bge_smoothing: float = 0.85, stretch_bg: float = 0.16,
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
                                            bge_smoothing=bge_smoothing, timeout=timeout, log=log)

    # ④ 各通道:autostretch → StarNet2 去星 → 分别揭示(弱信号揭示更狠)
    revs = {"H": _reveal(p["reveal_ha_d"]), "O": _reveal(p["reveal_oiii_d"])}
    for ch, tag in ((ha_ch, "H"), (oiii_ch, "O")):
        siril.run_script([f"cd {R}", f"load {ch}", "subsky 1", f"autostretch -2.8 {stretch_bg}", f"save _e_{tag}"], timeout=timeout)
        subprocess.run([sn, "-i", f"{R}/_e_{tag}.fit", "-o", f"{R}/_sl_{tag}.fit", "-s", "256"],
                       capture_output=True, text=True, timeout=timeout)
        siril.run_script([f"cd {R}", f"load _sl_{tag}", revs[tag], f"save _r_{tag}"], timeout=timeout)

    # ⑤ HOO 合成(R=Ha, G=OIII, B=OIII)+ gamma 提亮弱信号 + 饱和。**不 linear_match**
    #   软减背景(bg_sub_frac)保住星云外缘过渡带,消除"贴图"割裂感(全减会硬裁成硬边)。
    Ha = _softsub(_load_mono(f"{R}/_r_H.fit", "_rv_H"), p["bg_sub_frac"]) ** p["ha_gamma"]
    O = _softsub(_load_mono(f"{R}/_r_O.fit", "_rv_O"), p["bg_sub_frac"]) ** p["oiii_gamma"]
    Rc, Gc, Bc = np.clip(Ha, 0, 1), np.clip(O * p["kg"], 0, 1), np.clip(O * p["kb"], 0, 1)
    lum = (Rc + Gc + Bc) / 3.0
    s = p["sat"]
    neb = np.clip(np.stack([lum + (1 + s) * (Rc - lum), lum + (1 + s) * (Gc - lum),
                            lum + (1 + s) * (Bc - lum)], -1), 0, 1)

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

    # ⑦ 背景抬中性灰(绝不死黑)
    fin = neutral_gray(fin, target=p["bg_gray"])

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
