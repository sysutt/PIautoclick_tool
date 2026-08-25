"""成片质量**确定性指标**(不依赖 LLM,可复现)——供管线闭环质量门 + 喂评委 + UI 展示。

背景:LLM 评分是主观的、且此前只展示不驱动改动。有些质量轴其实可以**直接量化测量**,
比它更硬、更快、不花 token。测出来超出目标带 → 管线可确定性地回退某阶段重跑(见 run_rgb 质量门)。

现有量化轴(M23 诊断得来,见记忆 pi-critic-tickwhale / rgb-zeropi-engine):
- **S_star**:星点饱和度。星点颜色在**翼部**(核心过曝发白 S 低),故只取亮度中高、未 clip 的
  像素取 HSV-S 中位数。<0.20 发闷 / 0.30~0.50 自然有色(甜区)/ >0.60 艳俗。
  实测甜区与本项目 NGC6888(8%→54%)一致。
- **背景中性度**:暗背景应近中性灰(R≈G≈B、S 低)。S 中位 <0.10 干净;失衡 (max-min)/mean <10%。
- **背景亮度**:疏散星团/纯亮场应把背景钉深(~0.10),抬太亮=奶雾/脏。
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:                       # cv2 缺失时降级(不该发生,主依赖)
    cv2 = None


# 目标带(可调):星点饱和度、背景中性度、背景亮度
S_STAR_LO, S_STAR_HI = 0.30, 0.55       # 星点饱和度甜区
BG_S_MAX = 0.12                         # 背景中性度 S 上限(超=偏色)
BG_IMBAL_MAX = 0.15                     # 背景通道失衡上限
BG_LEVEL_MAX = 0.16                     # 背景亮度上限(星团/纯亮场;超=抬太亮)


def _to_rgb01(img) -> np.ndarray | None:
    """吃 PNG 路径 / xisf 路径 / ndarray → 归一化 RGB float(H,W,3) 0..1。"""
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
            if cv2 is None:
                return None
            bgr = cv2.imread(img, cv2.IMREAD_COLOR)
            if bgr is None:
                return None
            a = bgr[..., ::-1].astype(np.float32)
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


def star_saturation(img, v_lo: float = 0.15, v_hi: float = 0.85) -> float:
    """S_star:亮度中高、未 clip 的像素上 HSV 饱和度中位数(星点颜色主要在翼部)。测不到返回 0。"""
    rgb = _to_rgb01(img)
    if rgb is None or cv2 is None:
        return 0.0
    hsv = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    S = hsv[..., 1] / 255.0
    V = hsv[..., 2] / 255.0
    m = (V >= v_lo) & (V <= v_hi) & (S > 0.01)
    return round(float(np.median(S[m])), 3) if int(m.sum()) > 50 else 0.0


def background_stats(img, v_bg: float = 0.22) -> dict:
    """背景(暗像素 V<v_bg)中性度:S 中位、通道失衡 (max-min)/mean、亮度中位、偏色方向。"""
    rgb = _to_rgb01(img)
    if rgb is None or cv2 is None:
        return {"bg_s": 0.0, "bg_imbalance": 0.0, "bg_level": 0.0, "bg_cast": "-", "bg_frac": 0.0}
    hsv = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    S = hsv[..., 1] / 255.0
    V = hsv[..., 2] / 255.0
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


def measure(img) -> dict:
    """一次性测全部确定性质量指标。img=成片 PNG/xisf 路径或 ndarray。"""
    rgb = _to_rgb01(img)
    if rgb is None:
        return {"error": "无法读取图像"}
    out = {"s_star": star_saturation(rgb)}
    out.update(background_stats(rgb))
    return out


def diagnose(m: dict, *, cluster_target: bool = False) -> list[dict]:
    """把指标对照目标带 → 问题列表(每个含 issue/knob/how,供质量门决定回退动作)。
    cluster_target=True(疏散/球状星团、纯亮场):额外要求背景钉深、近中性。"""
    out = []
    if m.get("error"):
        return out
    s = m.get("s_star", 0.0)
    if 0 < s < S_STAR_LO:
        out.append({"issue": "dull_stars", "metric": f"S_star={s}",
                    "how": f"星点饱和度 {s}<{S_STAR_LO}(发闷)——多因合星到亮/偏色背景被稀释,"
                           f"或提饱和不足"})
    if m.get("bg_s", 0) > BG_S_MAX or m.get("bg_imbalance", 0) > BG_IMBAL_MAX:
        out.append({"issue": "dirty_background", "metric": f"bg_S={m.get('bg_s')} 失衡={m.get('bg_imbalance')}",
                    "how": f"背景偏色({m.get('bg_cast')} 偏高)——需加强背景中和/去色"})
    if cluster_target and m.get("bg_level", 0) > BG_LEVEL_MAX:
        out.append({"issue": "background_lifted", "metric": f"bg_level={m.get('bg_level')}",
                    "how": f"背景抬太亮({m.get('bg_level')}>{BG_LEVEL_MAX})——星团/纯亮场应钉深,别揭示背景"})
    return out
