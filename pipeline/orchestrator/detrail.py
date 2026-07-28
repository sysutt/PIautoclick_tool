"""卫星线 / 飞机线自动检测(在残差缩略图上做,配合 job-runner 的 residualset op)。

思路:静态的星云/星点在残差(帧 − 中位参考)里被抵消,只剩逐帧瞬时结构(卫星线、
飞机线、宇宙线)。用 cv2 概率霍夫在残差缩略图上检长直线;排除贴边的对齐边缘伪影;
返回"含轨迹的帧索引 + 检测线段"。上层据此把这些帧整帧剔除再整合(实测:检测帧准确,
整帧剔除轨迹必净;而精确 maskline 受缩略图定位精度限制,挖不净)。
"""
from __future__ import annotations

import glob
import math
import os
import re


def detect_trail_frames(thumb_dir: str, min_frac: float = 0.30,
                        audit_path: str | None = None) -> dict:
    """在 thumb_dir 下的 res_<idx>.png 残差缩略图上检测长直线(卫星/飞机线)。

    返回 {idx(int): {"line":[x1,y1,x2,y2](缩略图坐标), "len":float}}。
    min_frac:线长需 ≥ min_frac × 缩略图宽,才算轨迹(滤掉短的宇宙线/噪声)。
    audit_path:给了则把检出帧画线拼成审计图存该路径。
    """
    import cv2
    import numpy as np

    files = sorted(glob.glob(os.path.join(thumb_dir, "res_*.png")),
                   key=lambda f: int(re.search(r"res_(\d+)", os.path.basename(f)).group(1)))
    det: dict = {}
    overlays = []

    def edge_hug(x1, y1, x2, y2, w, h):
        m = max(6, int(0.04 * max(w, h)))
        horiz = abs(y2 - y1) < m
        vert = abs(x2 - x1) < m
        ay = (y1 + y2) / 2.0
        ax = (x1 + x2) / 2.0
        if horiz and (ay < m or ay > h - m):
            return True     # 贴顶/底的水平线 = 对齐后画面边缘伪影
        if vert and (ax < m or ax > w - m):
            return True     # 贴左/右的垂直线
        return False

    for f in files:
        idx = int(re.search(r"res_(\d+)", os.path.basename(f)).group(1))
        g = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        h, w = g.shape
        gb = cv2.GaussianBlur(g, (3, 3), 0)
        bg = cv2.medianBlur(gb, 31)          # 背景(大中值)
        hp = cv2.subtract(gb, bg)            # 高通:线/星点凸显,平滑背景去掉
        thr = max(6, int(hp.mean() + 3.5 * hp.std()))
        _, bw = cv2.threshold(hp, thr, 255, cv2.THRESH_BINARY)
        lines = cv2.HoughLinesP(bw, 1, math.pi / 180, threshold=60,
                                minLineLength=int(min_frac * w), maxLineGap=25)
        segs = [] if lines is None else [tuple(int(v) for v in np.asarray(l).reshape(-1)[:4]) for l in lines]
        segs = [s for s in segs if not edge_hug(*s, w, h)]
        best = None
        for (x1, y1, x2, y2) in segs:
            L = math.hypot(x2 - x1, y2 - y1)
            if best is None or L > best[4]:
                best = (x1, y1, x2, y2, L)
        ov = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        if best and best[4] >= min_frac * w:
            det[idx] = {"line": [best[0], best[1], best[2], best[3]], "len": round(best[4], 1)}
            cv2.line(ov, (best[0], best[1]), (best[2], best[3]), (0, 0, 255), 2)
        overlays.append((idx, ov, idx in det))

    if audit_path:
        try:
            show = [o for o in overlays if o[2]] or overlays[:8]
            if show:
                cols = 4
                rows = math.ceil(len(show) / cols)
                th, tw = show[0][1].shape[:2]
                sheet = np.full((rows * (th + 22), cols * tw, 3), 20, np.uint8)
                for i, (idx, ov, d) in enumerate(show):
                    r, c = divmod(i, cols)
                    y = r * (th + 22)
                    x = c * tw
                    cv2.putText(sheet, "#%d%s" % (idx, " TRAIL" if d else ""), (x + 4, y + 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 242, 180) if d else (200, 200, 200), 1)
                    sheet[y + 22:y + 22 + th, x:x + tw] = ov
                cv2.imwrite(audit_path, sheet)
        except Exception:
            pass
    return det
