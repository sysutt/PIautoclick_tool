"""品牌图标 —— 移植自设计稿 design/TTAstroPiLot UI 方案.html 的 SVG。

图标概念(设计稿 1j):光圈同心圆=望远镜/相机;十字丝=瞄准(aim);
外圈切入中心的弧线=autopilot 自动驾驭轨迹(呼应 PiLot);中心亮点=锁定的深空目标。
纯品牌绿单色线性,16px 收缩为标题栏图标仍不失辨识度。

用 QSvgRenderer 渲染成 QPixmap/QIcon;`{c}` 占位=线条色(按主题传入 accent),
`{s2}`=点缀星点色(白)。HiDPI 下按 devicePixelRatio 超采样,保持清晰。
"""
from __future__ import annotations

from PyQt5.QtCore import QByteArray, QRectF, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

# 品牌标记(标题栏/banner 用):光圈 + 十字丝 + 中心锁定点
LOGO = ('<svg viewBox="0 0 24 24" fill="none">'
        '<circle cx="12" cy="12" r="9" stroke="{c}" stroke-width="1.8"/>'
        '<path d="M12 3v3M12 18v3M3 12h3M18 12h3" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
        '<circle cx="12" cy="12" r="2.2" fill="{c}"/></svg>')

# App/窗口图标(完整版:双环 + autopilot 弧线 + 点缀星)
APP = ('<svg viewBox="0 0 24 24" fill="none">'
       '<circle cx="12" cy="12" r="9.2" stroke="{c}" stroke-width="1.3"/>'
       '<circle cx="12" cy="12" r="6" stroke="{c}" stroke-width="0.9" stroke-opacity="0.5"/>'
       '<path d="M12 0.6v5M12 18.4v5M0.6 12h5M18.4 12h5" stroke="{c}" stroke-width="1.3" stroke-linecap="round"/>'
       '<path d="M6 18 A9 9 0 0 1 12 3" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-opacity="0.9"/>'
       '<circle cx="12" cy="12" r="2.4" fill="{c}"/>'
       '<circle cx="18.2" cy="6" r="1" fill="{s2}"/>'
       '<circle cx="5.5" cy="8" r="0.7" fill="{s2}"/></svg>')

# 图片/预览占位(成片预览空态)
PREVIEW = ('<svg viewBox="0 0 24 24" fill="none">'
           '<rect x="2.5" y="4" width="19" height="16" rx="2" stroke="{c}" stroke-width="1.2"/>'
           '<path d="M4 16l4-5 3 3 4-6 5 8" stroke="{c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
           '<circle cx="8" cy="9" r="1.4" fill="{c}"/></svg>')

# 眼睛(密码显隐)
EYE = ('<svg viewBox="0 0 24 24" fill="none">'
       '<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6Z" stroke="{c}" stroke-width="1.4"/>'
       '<circle cx="12" cy="12" r="2.6" stroke="{c}" stroke-width="1.4"/></svg>')

# 数值步进 加/减(±):QSpinBox up=加、down=减
PLUS = ('<svg viewBox="0 0 12 12" fill="none">'
        '<path d="M6 2.4v7.2M2.4 6h7.2" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/></svg>')
MINUS = ('<svg viewBox="0 0 12 12" fill="none">'
         '<path d="M2.4 6h7.2" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/></svg>')


def pixmap(tpl: str, size: int, color: str = "#68E098", star: str = "#ffffff", dpr: float = 2.0) -> QPixmap:
    """渲染 SVG 模板为透明底 QPixmap。size=逻辑像素;dpr 超采样保清晰。"""
    svg = tpl.format(c=color, s2=star)
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    px = QPixmap(max(1, int(round(size * dpr))), max(1, int(round(size * dpr))))
    px.fill(Qt.transparent)
    p = QPainter(px)
    try:
        p.setRenderHint(QPainter.Antialiasing, True)
        r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    finally:
        p.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(tpl: str, size: int = 24, color: str = "#68E098", star: str = "#ffffff") -> QIcon:
    return QIcon(pixmap(tpl, size, color, star))


_PNG_CACHE: dict = {}


def png_path(tpl: str, name: str, color: str, size: int = 12) -> str:
    """把图标渲染成 PNG 存缓存目录,返回**正斜杠**路径(供 QSS `image:url()` 用)。按 (name,color,size) 缓存。"""
    import os
    import tempfile
    key = (name, color, size)
    cached = _PNG_CACHE.get(key)
    if cached and os.path.exists(cached):
        return cached
    d = os.path.join(tempfile.gettempdir(), "ttastropilot_icons")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{name}_{color.lstrip('#')}_{size}.png")
    try:
        pixmap(tpl, size, color, dpr=2.0).save(path, "PNG")
    except Exception:
        return ""
    p = path.replace("\\", "/")
    _PNG_CACHE[key] = p
    return p
