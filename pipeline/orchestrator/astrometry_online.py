# -*- coding: utf-8 -*-
"""nova.astrometry.net 在线天文解析(Tier 2 兜底,当本地 ImageSolver 盲解失败时用)。

零依赖(仅标准库 urllib)。流程:login → upload(可带 RA/Dec/尺度提示加速)→ 轮询
submission→job → calibration + 下载 wcs.fits。返回 {ok, ra, dec, pixscale, orientation,
parity, radius, wcs_path, jobid}。上层拿到解后可注入图像头供 SPCC 用。

API key 从 config 的 astrometry_api_key 读(用户在设置界面填,来自 nova.astrometry.net 账号页)。
"""
from __future__ import annotations
import json
import mimetypes
import time
import uuid
import urllib.request
import urllib.parse

BASE = "http://nova.astrometry.net/api"


def _post_json(path: str, args: dict, timeout: float = 60.0) -> dict:
    """POST application/x-www-form-urlencoded 的 request-json=<json>(nova 的约定)。"""
    data = urllib.parse.urlencode({"request-json": json.dumps(args)}).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_upload(path: str, args: dict, file_path: str, timeout: float = 180.0) -> dict:
    """multipart/form-data:字段 request-json=<json> + file=<图像>。手工构造 multipart。"""
    boundary = "----ttlot" + uuid.uuid4().hex
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    fname = file_path.replace("\\", "/").rsplit("/", 1)[-1]
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    pre = []
    # 字段 request-json
    pre.append("--" + boundary)
    pre.append('Content-Disposition: form-data; name="request-json"')
    pre.append("")
    pre.append(json.dumps(args))
    # 文件
    pre.append("--" + boundary)
    pre.append(f'Content-Disposition: form-data; name="file"; filename="{fname}"')
    pre.append("Content-Type: " + ctype)
    pre.append("")
    body = ("\r\n".join(pre) + "\r\n").encode("utf-8") + file_bytes + \
           ("\r\n--" + boundary + "--\r\n").encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url: str, timeout: float = 60.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def solve_online(image_path: str, api_key: str, ra=None, dec=None, radius=None,
                 scale_lower=None, scale_upper=None, scale_units="arcsecperpix",
                 wcs_out=None, poll=5.0, timeout=600.0, log=print) -> dict:
    """把 image_path 传给 nova 解析。ra/dec(度)/radius(度)/scale_*(角秒每像素)为可选提示,
    给了会显著加快并提高成功率。返回解析结果字典;失败 {ok:False, error}。"""
    if not (api_key or "").strip():
        return {"ok": False, "error": "未配置 astrometry_api_key(设置界面填 nova.astrometry.net 的 key)"}
    t_start = time.time()
    try:
        # 1) login
        r = _post_json("/login", {"apikey": api_key.strip()})
        if r.get("status") != "success":
            return {"ok": False, "error": "login 失败: " + json.dumps(r)}
        session = r["session"]
        log(f"  [nova] 登录成功 session={session[:6]}…")
        # 2) upload(带提示)
        args = {"session": session, "allow_commercial_use": "d", "allow_modifications": "d",
                "publicly_visible": "n"}
        if ra is not None and dec is not None:
            args["center_ra"] = float(ra); args["center_dec"] = float(dec)
            args["radius"] = float(radius) if radius is not None else 5.0
        if scale_lower is not None and scale_upper is not None:
            args["scale_units"] = scale_units
            args["scale_type"] = "ul"
            args["scale_lower"] = float(scale_lower); args["scale_upper"] = float(scale_upper)
        up = _post_upload("/upload", args, image_path)
        if up.get("status") != "success":
            return {"ok": False, "error": "upload 失败: " + json.dumps(up)}
        subid = up["subid"]
        log(f"  [nova] 上传成功 subid={subid},排队解析中…")
        # 3) 轮询 submission → jobid
        jobid = None
        while time.time() - t_start < timeout:
            sub = _get_json(f"{BASE}/submissions/{subid}")
            jobs = sub.get("jobs") or []
            if jobs and jobs[0] is not None:
                jobid = jobs[0]; break
            time.sleep(poll)
        if jobid is None:
            return {"ok": False, "error": f"排队超时({timeout}s)未开始解析"}
        log(f"  [nova] 开始解析 jobid={jobid}")
        # 4) 轮询 job → success/failure
        status = None
        while time.time() - t_start < timeout:
            js = _get_json(f"{BASE}/jobs/{jobid}")
            status = js.get("status")
            if status in ("success", "failure"):
                break
            time.sleep(poll)
        if status != "success":
            return {"ok": False, "error": f"解析失败/超时 status={status} jobid={jobid}"}
        # 5) calibration
        cal = _get_json(f"{BASE}/jobs/{jobid}/calibration/")
        # 6) 下载 wcs.fits(含标准 WCS 关键字,供注入)
        wcs_path = None
        if wcs_out:
            try:
                urllib.request.urlretrieve(f"http://nova.astrometry.net/wcs_file/{jobid}", wcs_out)
                wcs_path = wcs_out
            except Exception as e:
                log(f"  [nova] wcs.fits 下载失败(不影响标定):{e}")
        log(f"  [nova] 解析成功 用时 {time.time()-t_start:.0f}s | RA={cal.get('ra'):.4f} "
            f"Dec={cal.get('dec'):.4f} pixscale={cal.get('pixscale'):.3f}\"/px")
        return {"ok": True, "jobid": jobid, "wcs_path": wcs_path,
                "ra": cal.get("ra"), "dec": cal.get("dec"), "pixscale": cal.get("pixscale"),
                "orientation": cal.get("orientation"), "parity": cal.get("parity"),
                "radius": cal.get("radius")}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
