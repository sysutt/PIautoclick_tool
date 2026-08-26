"""成片质量**确定性指标**(不依赖 LLM,可复现)——供管线闭环质量门 + 喂评委 + UI 展示。

背景:LLM 评分是主观的、且此前只展示不驱动改动。有些质量轴其实可以**直接量化测量**,
比它更硬、更快、不花 token。测出来超出目标带 → 管线可确定性地回退某阶段重跑(见 run_rgb 质量门)。

现有量化轴(M23 诊断得来,见记忆 pi-quality-gate):
- **S_star**:星点饱和度。星点颜色在**翼部**(核心过曝发白 S 低),故只取亮度中高、未 clip 的
  像素取 HSV-S 中位数。<0.20 发闷 / 0.30~0.55 自然有色(甜区)/ >0.60 艳俗。
  实测甜区与本项目 NGC6888(8%→54%)一致。
- **背景中性度**:暗背景应近中性灰(R≈G≈B、S 低)。S 中位 <0.12 干净;失衡 (max-min)/mean <15%。
- **背景亮度**:疏散星团/纯亮场应把背景钉深(~0.10),抬太亮=奶雾/脏。

**实现刻意用纯 numpy**(不用 cv2):HSV 的 S=(max-min)/max、V=max 直接算即可,且 cv2 在
PyQt 子线程里(质量门在 Worker 线程调用)有 Windows 段错误风险(try/except 拦不住)——见崩溃教训。
"""
from __future__ import annotations

import numpy as np


# 目标带(可调):星点饱和度、背景中性度、背景亮度
S_STAR_LO, S_STAR_HI = 0.30, 0.55       # 星点饱和度甜区
BG_S_MAX = 0.12                         # 背景中性度 S 上限(超=偏色)
BG_IMBAL_MAX = 0.15                     # 背景通道失衡上限
BG_LEVEL_MAX = 0.16                     # 背景亮度上限(星团/纯亮场;超=抬太亮)


def _to_rgb01(img) -> np.ndarray | None:
    """吃 PNG/JPG 路径 / xisf 路径 / ndarray → 归一化 RGB float(H,W,3) 0..1。纯 numpy + PIL/xisf,不用 cv2。"""
    if isinstance(img, np.ndarray):
        a = img.astype(np.float32)
    elif isinstance(img, str):
        low = img.lower()
        if low.endswith(".xisf"):
            try:
                from xisf import XISF
                a = XISF(img).read_image(0).astype(np.float32)
            except Exception:
                return None
        else:
            try:
                from PIL import Image
                a = np.asarray(Image.open(img).convert("RGB")).astype(np.float32)
            except Exception:
                return None
    else:
        return None
    if a.ndim == 2:
        a = np.stack([a] * 3, -1)
    if a.shape[-1] > 3:
        a = a[..., :3]
    mx = float(a.max()) if a.size else 1.0
    if mx > 1.5:
        a = a / (65535.0 if mx > 255 else 255.0)
    return np.clip(a, 0.0, 1.0)


def _hsv_sv(rgb: np.ndarray):
    """纯 numpy 的 HSV 分量:S=(max-min)/max、V=max(与 cv2 一致,差 ~0.002 量化误差)。"""
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    S = np.where(mx > 1e-9, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    return S, mx


def _star_mask_auto(V: np.ndarray) -> np.ndarray:
    """自动星点蒙版:**局部明显超出背景的紧凑亮点**=星点。用降采样-升采样估大尺度背景(PIL,纯像素、
    无 cv2),V−背景 超阈即星。**必须**——不然亮背景图里满屏中性背景像素会把 S 中位数拉低(M23 亮背景:
    整图测 0.28 vs 星蒙版测 0.53),星点饱和度根本测不准。"""
    try:
        from PIL import Image
        H, W = V.shape
        k = max(8, min(H, W) // 150)                    # 降采样倍数 → 大尺度局部背景
        v8 = (np.clip(V, 0, 1) * 255).astype(np.uint8)
        small = Image.fromarray(v8).resize((max(1, W // k), max(1, H // k)), Image.BILINEAR)
        bg = np.asarray(small.resize((W, H), Image.BILINEAR)).astype(np.float32) / 255.0
        return (V - bg > 0.05) & (V >= 0.15) & (V <= 0.92)
    except Exception:
        return (V >= 0.15) & (V <= 0.85)                # PIL 不可用 → 退回全中高亮度(暗背景仍准)


def star_saturation(img, v_lo: float = 0.15, v_hi: float = 0.85, stars=None) -> float:
    """S_star:**星点像素**上 HSV 饱和度中位数(星色在翼部,核心过曝 S 低,故限亮度中高)。测不到返回 0。
    stars=分离星层(路径/ndarray)时用它当精确蒙版(星区=星层有信号处);否则自动检测紧凑亮点。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return 0.0
    S, V = _hsv_sv(rgb)
    sm = None
    if stars is not None:
        sl = _to_rgb01(stars)
        if sl is not None and sl.shape[:2] == rgb.shape[:2]:
            sm = sl.mean(-1) > 0.03                     # 分离星层有信号处=星点(最准)
    if sm is None:
        sm = _star_mask_auto(V)                         # 无星层 → 自动检测
    m = sm & (V >= v_lo) & (V <= v_hi) & (S > 0.01)
    return round(float(np.median(S[m])), 3) if int(m.sum()) > 50 else 0.0


def background_stats(img, v_bg: float = 0.22) -> dict:
    """背景(暗像素 V<v_bg)中性度:S 中位、通道失衡 (max-min)/mean、亮度中位、偏色方向。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return {"bg_s": 0.0, "bg_imbalance": 0.0, "bg_level": 0.0, "bg_cast": "-", "bg_frac": 0.0}
    S, V = _hsv_sv(rgb)
    bg = V < v_bg
    if int(bg.sum()) < 200:
        bg = V < np.percentile(V, 20)          # 极亮图兜底:取最暗 20%
    means = [float(rgb[..., c][bg].mean()) for c in range(3)]
    mean_avg = sum(means) / 3.0 + 1e-6
    imbalance = (max(means) - min(means)) / mean_avg
    return {
        "bg_s": round(float(np.median(S[bg])), 3),
        "bg_imbalance": round(float(imbalance), 3),
        "bg_level": round(float(np.median(V[bg])), 3),
        "bg_cast": ["R", "G", "B"][int(np.argmax(means))],
        "bg_frac": round(float(bg.mean()), 3),
    }


def measure(img, stars=None) -> dict:
    """一次性测全部确定性质量指标。img=成片 PNG/xisf 路径或 ndarray;stars=可选分离星层(路径/ndarray)
    → 用它当精确星蒙版测 s_star(管线里 sep.stars 可传;独立测 png 则自动检测)。异常吞成 error(绝不崩管线)。"""
    try:
        rgb = _to_rgb01(img)
        if rgb is None:
            return {"error": "无法读取图像"}
        out = {"s_star": star_saturation(rgb, stars=stars)}
        out.update(background_stats(rgb))
        return out
    except Exception as e:
        return {"error": f"测量异常:{e}"}


def signal_frac(img, thr: float = 0.25) -> float:
    """亮信号占比(V>thr 的像素比例)——区分填满画幅的星云(高)vs 星团/空场(低)。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return 0.0
    return round(float((rgb.max(-1) > thr).mean()), 3)


def signal_balance(img, v_lo: float = 0.25, s_lo: float = 0.10):
    """信号区(亮且有色的像素)的 RGB 色彩平衡 [r,g,b](归一化到均值=1)——该天体"该偏什么色调"。
    取亮(V>v_lo)且有色(S>s_lo)的像素均值:滤掉暗背景和中性星点,只看星云/尘埃主色。测不到返回 None。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return None
    S, V = _hsv_sv(rgb)
    m = (V > v_lo) & (S > s_lo)
    if int(m.sum()) < 100:
        return None
    means = np.array([float(rgb[..., c][m].mean()) for c in range(3)])
    avg = float(means.mean()) + 1e-6
    return (means / avg).tolist()              # 如 [1.25, 0.95, 0.80] = 偏红


def ref_targets(ref_paths) -> dict | None:
    """测多张 AstroBin 同视场参考图 → 该天体的**经验目标**(中位数聚合,抗单张异常)。
    返回 {n, s_star, bg_level, bg_s, signal_frac, rgb_balance} 或 None(无有效参考)。
    用途:替代固定标准(星点多饱和/背景多暗)+ 反推该不该揭示(signal_frac)+ 调色对齐(rgb_balance 该偏什么色调)。
    见 [[pi-astrobin-reference]] 血泪 / [[pi-quality-gate]]。"""
    ss, bl, bs, sf, bal = [], [], [], [], []
    for p in ref_paths or []:
        rgb = _to_rgb01(p)
        if rgb is None:
            continue
        m = measure(rgb)                       # 参考图无分离星层 → 自动星点检测
        if m.get("error"):
            continue
        ss.append(m["s_star"]); bl.append(m["bg_level"]); bs.append(m["bg_s"])
        sf.append(signal_frac(rgb))
        _b = signal_balance(rgb)
        if _b:
            bal.append(_b)
    if not ss:
        return None

    def _med(a):
        return round(float(np.median(a)), 3)
    out = {"n": len(ss), "s_star": _med(ss), "bg_level": _med(bl),
           "bg_s": _med(bs), "signal_frac": _med(sf)}
    if bal:
        out["rgb_balance"] = [round(float(x), 3) for x in np.median(np.array(bal), axis=0)]
    return out


def diagnose(m: dict, *, cluster_target: bool = False, targets: dict | None = None) -> list[dict]:
    """把指标对照目标带 → 问题列表(每个含 issue/knob/how,供质量门决定回退动作)。
    cluster_target=True(疏散/球状星团、纯亮场):额外要求背景钉深、近中性。
    targets=参考图导出的**因目标而异**目标(ref_targets):给了就用它校准 S_star 下限(取参考中位与固定甜区较
    宽松者当下限,避免对本就低饱和的天体误判;背景中性仍用固定判据,因优秀作品背景都该中性)。"""
    out = []
    if not m or m.get("error"):
        return out
    s = m.get("s_star", 0.0)
    # S_star 下限:有参考则用 min(固定甜区下限, 参考中位×0.8)——参考星点若本就不很饱和(如某些星系场)
    #   就别硬拿固定 0.30 卡;但也不低于一个地板 0.20(<0.20 一定发闷)。
    s_lo = S_STAR_LO
    if targets and targets.get("s_star"):
        s_lo = max(0.20, min(S_STAR_LO, round(float(targets["s_star"]) * 0.8, 3)))
    if 0 < s < s_lo:
        out.append({"issue": "dull_stars", "metric": f"S_star={s}(目标≥{s_lo})",
                    "how": f"星点饱和度 {s}<{s_lo}(发闷)——多因合星到亮/偏色背景被稀释,或提饱和不足"})
    if m.get("bg_s", 0) > BG_S_MAX or m.get("bg_imbalance", 0) > BG_IMBAL_MAX:
        out.append({"issue": "dirty_background", "metric": f"bg_S={m.get('bg_s')} 失衡={m.get('bg_imbalance')}",
                    "how": f"背景偏色({m.get('bg_cast')} 偏高)——需加强背景中和/去色"})
    if cluster_target and m.get("bg_level", 0) > BG_LEVEL_MAX:
        out.append({"issue": "background_lifted", "metric": f"bg_level={m.get('bg_level')}",
                    "how": f"背景抬太亮({m.get('bg_level')}>{BG_LEVEL_MAX})——星团/纯亮场应钉深,别揭示背景"})
    return out
