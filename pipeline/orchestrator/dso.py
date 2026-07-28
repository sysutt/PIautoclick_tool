"""按天体名查 DSO 目录(经自有后端 /weather dso_search),得到天体类型 + 面亮度 + 尺寸,
用于后期前的**目标分类**:决定该不该"揭示背景"。

核心判断(用户 2026-07-28 定的原则):**星团(球状/疏散)背景是空的**(没有星云/星系),
贸然拉伸背景只会发白成奶雾 → 星团要**克制拉伸、背景钉深黑、不揭示**;而星云/星系背景里
有真延展信号 → 才该揭示。

类型编码(dso 表 type 字段实测):Nb=星云 / Gxy=星系 / PN=行星状星云 / GCL=球状星团 /
OCL=疏散星团。→ GCL/OCL 归"星团(空背景)",其余归"有延展信号"。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import config

# 空背景、点源为主、不该拉背景的类型(星团 + 恒星/聚星)
_CLUSTER_TYPES = {"GCL", "OCL", "OC", "GC", "STAR", "AST", "DBLSTAR", "***"}


def _endpoint() -> str:
    base = (config.get_setting("astrobin_ref.base_url") or "https://app.tickwhale.com").rstrip("/")
    return base + "/weather"


def lookup(name: str, timeout: float = 20.0) -> dict | None:
    """按天体名/编号查 DSO 目录。name 可含引号/空格(如 FITS OBJECT="'M 22'")。
    先按 catalog_id 精确(去空格/去横杠/大写),再按 search_text 模糊。返回首条 dict 或 None。
    """
    if not name:
        return None
    clean = name.strip().strip("'\"").strip()
    if not clean:
        return None
    cat = clean.upper().replace(" ", "").replace("-", "")

    def _q(d: dict):
        body = json.dumps({"a": "dso_search", "d": d}).encode("utf-8")
        req = urllib.request.Request(_endpoint(), data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                j = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None
        lst = (j.get("result") or {}).get("list") or []
        return lst[0] if lst else None

    return _q({"catalog_id": cat}) or _q({"search_text": clean})


def is_cluster(info: dict | None) -> bool:
    """按 DSO 记录判断是否"空背景星团类"(该走克制模式、不拉背景)。"""
    if not info:
        return False
    t = str(info.get("type") or "").strip().upper()
    return t in _CLUSTER_TYPES


def classify(name: str) -> dict:
    """便捷入口:名字 → {name, info, cluster(bool), type}。查不到时 cluster=False(默认按有信号处理)。"""
    info = lookup(name)
    return {"name": name, "info": info, "cluster": is_cluster(info),
            "type": (info or {}).get("type")}
