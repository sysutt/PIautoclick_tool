"""SPCC 光度星表区块**按天区自动补装**(桌面应用固化)。

Siril 的 SPCC 光谱光度星表按 nside=2 nested 切成 48 块(见 [[siril-offline-spcc]]);
全下 20GB 没必要。本模块:装了**全天解析星表**(一次性)后,处理**任意目标**时自动
算它天区覆盖的区块、缺哪块就从 Zenodo 下哪块 → 之后复用。这样 SPCC 对任意目标即开即用。
"""
from __future__ import annotations

import bz2
import glob
import os
import re
import shutil
import urllib.request

SPCC_RECORD = 14738271          # Zenodo 记录(siril_cat1_healpix8_xpsamp_N.dat.bz2)
_URL = "https://zenodo.org/records/{rec}/files/siril_cat1_healpix8_xpsamp_{n}.dat.bz2?download=1"


def _siril_config_path() -> str | None:
    d = os.path.join(os.environ.get("LOCALAPPDATA", ""), "siril")
    cfgs = sorted(glob.glob(os.path.join(d, "config.*.ini")))
    return cfgs[-1] if cfgs else None


def photo_dir() -> str:
    """SPCC 区块目录(Siril config 的 catalogue_gaia_photo,否则默认)。"""
    cfg = _siril_config_path()
    if cfg and os.path.exists(cfg):
        try:
            for line in open(cfg, encoding="utf-8", errors="ignore"):
                if line.startswith("catalogue_gaia_photo="):
                    p = os.path.expanduser(line.split("=", 1)[1].strip())
                    if p:
                        return p
        except OSError:
            pass
    return os.path.expanduser("~/.local/share/siril/siril_cat1_healpix8_xpsamp")


def chunks_for_field(ra_deg: float, dec_deg: float, radius_deg: float = 2.5) -> list[int]:
    """目标天区(中心 + ±radius 采样网格)覆盖的 nside=2 nested 区块号。缺 astropy_healpix 则空。"""
    try:
        import math

        import numpy as np
        from astropy_healpix import HEALPix
        import astropy.units as u
    except Exception:
        return []
    hp = HEALPix(nside=2, order="nested")
    cs = set()
    for dr in np.linspace(-radius_deg, radius_deg, 5):
        for dd in np.linspace(-radius_deg, radius_deg, 5):
            ra = ra_deg + dr / max(0.1, math.cos(math.radians(dec_deg)))
            dec = max(-89.9, min(89.9, dec_deg + dd))
            cs.add(int(hp.lonlat_to_healpix(ra * u.deg, dec * u.deg)))
    return sorted(cs)


def installed_chunks() -> set[int]:
    out = set()
    for f in glob.glob(os.path.join(photo_dir(), "siril_cat1_healpix8_xpsamp_*.dat")):
        m = re.search(r"_(\d+)\.dat$", f)
        if m:
            out.add(int(m.group(1)))
    return out


def download_chunk(n: int, log=print, timeout: float = 1800.0) -> bool:
    """下载 + 解压一个区块到 SPCC 目录(已在则跳过)。返回是否就绪。"""
    d = photo_dir()
    os.makedirs(d, exist_ok=True)
    dat = os.path.join(d, f"siril_cat1_healpix8_xpsamp_{n}.dat")
    if os.path.exists(dat) and os.path.getsize(dat) > 1_000_000:
        return True
    bz2p = dat + ".bz2"
    log(f"[spcc] 该天区缺 SPCC 区块 {n},自动下载中(首次,之后复用)…")
    try:
        urllib.request.urlretrieve(_URL.format(rec=SPCC_RECORD, n=n), bz2p)
        with bz2.BZ2File(bz2p) as fi, open(dat, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
        os.remove(bz2p)
        log(f"[spcc] 区块 {n} 就绪({os.path.getsize(dat) // 1048576}MB)")
        return True
    except Exception as e:
        log(f"[spcc] 区块 {n} 下载失败(网络?):{str(e)[:120]}")
        for p in (bz2p, dat):
            if os.path.exists(p) and (p == bz2p or os.path.getsize(p) < 1_000_000):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return False


def ensure_for_field(ra_deg: float, dec_deg: float, *, radius_deg: float = 2.5,
                     log=print, timeout: float = 1800.0) -> tuple[list[int], bool]:
    """确保目标天区的 SPCC 区块都装好(缺的自动下)。返回 (需要的区块, 是否全部就绪)。"""
    need = chunks_for_field(ra_deg, dec_deg, radius_deg)
    if not need:
        return [], False
    have = installed_chunks()
    ok = True
    for c in need:
        if c not in have:
            ok = download_chunk(c, log=log, timeout=timeout) and ok
    return need, ok


def read_radec(master: str, siril_mod) -> tuple[float, float] | None:
    """从 master 头读天区中心 RA/DEC(度)。Siril dumpheader 解析 RA=/DEC=(度)或
    OBJCTRA/OBJCTDEC(H M S / D M S)。读不到返回 None。"""
    from . import config
    R = str(config.RUN_DIR)
    try:
        _ok, log = siril_mod.run_script(
            [f"cd {R}", f'load "{str(master).replace(chr(92), "/")}"', "dumpheader"], timeout=120)
    except Exception:
        return None
    ra = dec = None
    for line in log.split("\n"):
        m = re.search(r"\bRA\s*=\s*(-?\d+\.\d+)", line)
        if m and ra is None:
            ra = float(m.group(1))
        m = re.search(r"\bDEC\s*=\s*(-?\d+\.\d+)", line)
        if m and dec is None:
            dec = float(m.group(1))
    if ra is not None and dec is not None:
        return ra, dec
    # 退回 OBJCTRA/OBJCTDEC(六十进制)
    ora = odec = None
    for line in log.split("\n"):
        m = re.search(r"OBJCTRA\s*=\s*'?\s*([\d]+)\s+([\d]+)\s+([\d.]+)", line)
        if m:
            ora = (float(m.group(1)) + float(m.group(2)) / 60 + float(m.group(3)) / 3600) * 15
        m = re.search(r"OBJCTDEC\s*=\s*'?\s*([+-]?[\d]+)\s+([\d]+)\s+([\d.]+)", line)
        if m:
            sgn = -1 if m.group(1).strip().startswith("-") else 1
            odec = sgn * (abs(float(m.group(1))) + float(m.group(2)) / 60 + float(m.group(3)) / 3600)
    if ora is not None and odec is not None:
        return ora, odec
    return None
