"""
AstroBin 同视场参考图检索(经自有后端 /pipeline 代理)。

用途:plate-solve 得到目标 RA/DEC(可选旋转角)后,拉取 2° 半径内的
AstroBin 优秀作品,下载缩略图,交给 VisionCritic 当"审美目标"对照调参。

鉴权:请求头 X-Pipeline-Key,对应后端 .env 的 PIPELINE_API_KEY。
AstroBin 官方 key 始终只在后端使用,管线永不接触。
配置:_config/settings.json 的 astrobin_ref.{base_url,api_key}(见 settings_ui)。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from . import config


class AstrobinRefError(RuntimeError):
    pass


def _cfg() -> tuple[str, str]:
    base = (config.get_setting("astrobin_ref.base_url") or "").rstrip("/")
    key = config.get_setting("astrobin_ref.api_key") or ""
    if not base or not key:
        raise AstrobinRefError(
            "未配置 astrobin_ref.base_url / api_key(见配置界面)"
        )
    return base, key


def _post(action: str, d: dict, timeout: float = 30.0) -> dict:
    base, key = _cfg()
    url = base + "/pipeline"
    body = json.dumps({"a": action, "d": d}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Pipeline-Key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AstrobinRefError(f"HTTP {e.code}: {e.read()[:200]!r}") from e
    except urllib.error.URLError as e:
        raise AstrobinRefError(f"连接失败: {e}") from e
    result = payload.get("result") or {}
    if not result.get("success"):
        raise AstrobinRefError(payload.get("memo") or "后端返回失败")
    return result


def ping() -> dict:
    """健康检查:确认 base_url/key 有效、路由通。"""
    return _post("ping", {}, timeout=15.0)


def fetch_similar(
    ra_deg: float,
    dec_deg: float,
    rotate: Optional[float] = None,
    radius: float = 2.0,
    pagesize: int = 12,
    filter: Optional[str] = None,
    obj_type: Optional[str] = None,
) -> dict[str, Any]:
    """按坐标(可选旋转角/滤镜)检索同视场 AstroBin 作品,返回后端 result。"""
    d: dict[str, Any] = {
        "ra": ra_deg,
        "dec": dec_deg,
        "radius": radius,
        "more": {"start_pos": 0, "pagesize": pagesize},
    }
    if rotate is not None:
        d["rotate"] = rotate
    if filter:
        d["filter"] = filter
    if obj_type:
        d["type"] = obj_type
    return _post("astrobin_similar", d)


# 滤镜串 → 波段判定:含 LRGB/OSC 等宽带成分即算"宽带类"(可与彩机 RGB / 黑白 LRGB 对比);
# 纯 Ha/OIII/SII = 窄带。空滤镜多为 OSC 直拍 → 宽带。用户 2026-09-08:对比须同波段(宽带比宽带)。
_BROAD_KEYS = ("red", "green", "blue", "lumin", "bessell", "rgb", "osc", "ir-cut", "ircut",
               "uv/ir", "uvir", "cls", "clear", "l-pro", "l-enhance", "l-extreme", "uhc", "duo")
_NARROW_KEYS = ("h-alpha", "halpha", "hα", "oiii", "o iii", "s ii", "sii", "s2", "narrowband",
                "3nm", "5nm", "6nm", "7nm", "12nm")


def ref_band(item: dict) -> str:
    """AstroBin 作品波段类:'broad'(含 LRGB/OSC 宽带成分,可与 OSC RGB / 黑白 LRGB 对比)/ 'narrow'(纯窄带)。"""
    f = (item.get("filter") or "").lower()
    if not f:
        return "broad"                      # OSC 直拍常不填滤镜
    if any(k in f for k in _BROAD_KEYS):
        return "broad"                      # 有宽带成分(即便也叠了 Ha)→ 宽带类
    if any(k in f for k in _NARROW_KEYS):
        return "narrow"
    return "broad"


def fetch_for_target(name: str, band: str | None = None, out_dir: Path | None = None,
                     limit: int = 4, radius: float = 2.0, pagesize: int = 16) -> list[dict]:
    """**按目标名**(dso.lookup 查坐标,不依赖天文解析)拉同视场 AstroBin 作品,按 band 过滤后下载。
    band='broad'/'narrow'(None=不过滤)。查不到坐标 / 无同波段匹配 → 返回 []。用于评分对比(用户 2026-09-08:
    从 M1 到 M38 从没触发过——原因是旧逻辑只在天文解析成功时才拉,而解析对 Dwarf OSC 常失败)。"""
    from . import dso
    info = dso.lookup(name or "")
    if not info:
        return []
    ra, dec = info.get("ra"), info.get("dec")
    if ra is None or dec is None:
        return []
    res = fetch_similar(float(ra), float(dec), radius=radius, pagesize=pagesize)
    items = res.get("list") or []
    if band:
        items = [it for it in items if ref_band(it) == band]
    if not items:
        return []
    return download_thumbs(items, out_dir, limit=limit)


def download_thumbs(items: list[dict], out_dir: Path, limit: int = 6) -> list[dict]:
    """下载 top-N 参考缩略图到 out_dir,返回 [{meta..., local_path}]。下载失败的跳过。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict] = []
    for i, it in enumerate(items[:limit]):
        # image_url 是 rawthumb 端点(302→CDN 真实图);thumbnail_url 是 SPA 页面,不可直接下
        src = it.get("image_url") or it.get("thumbnail_url")
        if not src:
            continue
        if src.startswith("http://"):
            src = "https://" + src[len("http://"):]
        dst = out_dir / f"ref_{i:02d}.jpg"
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                dst.write_bytes(resp.read())
        except Exception:
            continue
        saved.append({**it, "local_path": str(dst)})
    return saved
