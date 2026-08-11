"""Siril 命令行集成(引擎中立后端 / 无 PixInsight 后期)。

#3 对等引擎的基石:Siril 有完整的脚本 CLI(siril-cli.exe -s script.ssf),原生读写 XISF/FITS,
把纯像素运算(背景提取/拉伸/合成/裁切/降噪…)映射到 Siril 命令 → 让管线**不依赖 PixInsight** 也能跑
(PI 本身收费,这是给买不起 PI 的用户的)。模板同 graxpert.py:resolve 路径 → 拼脚本 → subprocess → 校验产出。

已验证(2026-08-11,Siril 1.4.0-beta2):
- 原生读 XISF(load 直接吃 .xisf);save=FITS(.fit)、savepng/savejpg/savetif 出对应格式。
- subsky(背景提取,degree 多项式 或 -rbf)、autostretch(自动拉伸)可用。
- **denoise(NL-Bayes)在 1.4.0-beta2 有 bug**:处理到收尾必报 "no suitable data in src fits"(与图无关)
  → 降噪暂走 GraXpert CLI(graxpert.py,也不碰 PI);待 Siril 稳定版修复或换 denoise 命令。
"""
from __future__ import annotations

import os
import subprocess

from . import config


def siril_exe() -> str | None:
    """返回 siril-cli.exe 路径(config 的 siril_path 优先,否则常见安装位置)。"""
    try:
        p = config.load_settings().get("siril_path", "")
    except Exception:
        p = ""
    if p and os.path.exists(p):
        return p
    for c in [r"C:/Program Files/Siril/bin/siril-cli.exe",
              r"C:/Program Files/SiriL/bin/siril-cli.exe",
              r"C:/Program Files (x86)/Siril/bin/siril-cli.exe"]:
        if os.path.exists(c):
            return c
    return None


def available() -> bool:
    return siril_exe() is not None


def version() -> str | None:
    exe = siril_exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return (r.stdout or "").strip().splitlines()[0] if r.stdout else None
    except Exception:
        return None


def run_script(commands: list[str], *, requires: str = "1.2.0",
               timeout: float = 900.0) -> tuple[bool, str]:
    """把命令列表写成 .ssf → 跑 `siril-cli -s` → 返回 (ok, 合并输出)。
    ok 判据:输出含成功标记且无失败/error 标记(Siril 中文本地化会打"脚本执行成功完成"/"脚本执行失败")。"""
    exe = siril_exe()
    if not exe:
        raise RuntimeError("Siril 不可用:未找到 siril-cli.exe(在配置里填 siril_path)")
    script = "requires " + requires + "\n" + "\n".join(commands) + "\n"
    sd = str(config.RUN_DIR)
    os.makedirs(sd, exist_ok=True)
    sp = os.path.join(sd, "_siril_job.ssf").replace("\\", "/")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    r = subprocess.run([exe, "-s", sp], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    # 注:Siril 1.4-beta 退出时常打一条**伪错误** "error: no suitable data in src fits"(在脚本成功之后),
    #   不能当失败标志;只认显式的"脚本执行失败"/"Script execution failed"。真正成败由调用方查产出文件。
    fail = ("脚本执行失败" in out) or ("Script execution failed" in out)
    return (not fail), out


def process_poc(input_path: str, output_noext: str, *, bg: str = "1",
                denoise: str = "none", timeout: float = 1200.0) -> str:
    """【无 PI 整流程 POC】Siril:load → subsky 背景提取 → [denoise] → autostretch → savepng。
    全程不碰 PixInsight。返回 <output_noext>.png。

    bg: subsky 参数——数字=多项式阶数;或 "-rbf -samples=20 -smooth=0.5"。
    denoise: "none"(默认)/ "fmedian"(Siril 中值,基础降噪)。
      注:AI 级降噪目前 PI-free 都受阻——Siril 1.4-beta NL-Bayes 有 bug(收尾报 "no suitable data")、
      GraXpert denoise 模型未装且下载源不通;待 Siril 稳定版或手动装 GraXpert denoise 模型后再接。
    """
    inp = str(input_path).replace("\\", "/")
    out = str(output_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    cmds = [f"load {inp}", "subsky " + bg]
    if denoise == "fmedian":
        cmds.append("fmedian 3 1")   # 3x3 中值,1 次迭代(基础降噪,非 AI)
    cmds += ["autostretch", f"savepng {out}"]
    ok, log = run_script(cmds, timeout=timeout)
    final = out + ".png"
    # 成败以产出文件为准(Siril beta 退出伪错误不可信)
    if not os.path.exists(final):
        raise RuntimeError("Siril POC 失败(无产出 PNG)\n" + log[-1500:])
    return final


def starnet_exe() -> str | None:
    """StarNet2 独立 CLI 路径(config 的 starnet_path 优先,否则常见位置)。用于无 PI 分星。"""
    try:
        p = config.load_settings().get("starnet_path", "")
    except Exception:
        p = ""
    if p and os.path.exists(p):
        return p
    for c in [r"D:/Program Files/StarNet2/bin/starnet2.exe",
              r"C:/Program Files/StarNet2/bin/starnet2.exe"]:
        if os.path.exists(c):
            return c
    return None


def _stretch_cmds(stretch: str, target_bg: float, ght: dict | None) -> list[str]:
    """单通道拉伸命令(subsky 之后)。**背景对齐的关键**:三通道用**同一** target_bg,
    各自 autostretch 都落到该背景电平 → 合成后背景中性、无色偏(治好"发绿/底部偏色")。

    主拉伸恒为 `autostretch -2.8 <target_bg>`:shadowsclip -2.8σ(默认),target_bg 显式给
    (默认 0.25 偏亮 → 我们给 0.08 贴近 PI 的 0.10、暗 moody)。**别用 linear_match 对齐通道**:
    它会把 S/H/O 强行拟合到同一线性关系,抹掉窄带三线的信号差异(=丢色彩),只适合同信号帧(马赛克拼接)。

    stretch="ght"(GHS 揭示):在 autostretch **之后**再叠一层 `ght`(非线性域揭示暗弱)。
      **【实测铁律】GHS 不能当原始 linear 主拉伸**——深空 master subsky 后 median≈0.0008(归一),
      GHS 强度 D 上限 10 远不及 autostretch 的 MTF 对超低信号的提升,单用 ght 出全黑图(D=6~9 实测中位≤0.004)。
      正确用法(ghsastro 官方工作流亦如此):autostretch 先把背景抬到 target_bg,ght 再在非线性域温和揭示,
      SP≈faint 电平(非线性,~0.10-0.15)、D 小(1.5-3)、LP 护暗部、HP 护高光防星点膨胀。暗 moody 默认走纯 auto。"""
    cmds = [f"autostretch -2.8 {target_bg}"]
    if stretch == "ght":
        g = ght or {}
        d = float(g.get("D", 1.5)); b = float(g.get("B", 0.0))
        sp = float(g.get("SP", 0.12)); hp = float(g.get("HP", 0.80))
        # LP 默认**绑定背景电平**:护住 [0, ~target_bg] 为线性 → 揭示时背景不被一起抬亮(实测 LP=0.02
        # 护不住 0.08 背景 → 背景冲到 0.26)。上限卡在 SP 之下。用户可显式覆盖。
        lp = float(g.get("LP", round(min(max(target_bg - 0.005, 0.0), sp - 0.01), 3)))
        cmds.append(f"ght -D={d} -B={b} -LP={lp} -SP={sp} -HP={hp}")   # 非线性域揭示(在 autostretch 之后)
    return cmds


def compose_sho_stars(s_path: str, h_path: str, o_path: str, output_noext: str, *,
                      crop: str | None = None, bg: str = "1", degreen: int = 1,
                      satu: float = 0.7, stride: int = 256, target_bg: float = 0.08,
                      stretch: str = "auto", ght: dict | None = None, clahe: float = 0.0,
                      satu_bgf: float = 1.0, timeout: float = 1800.0) -> str:
    """【无 PI 彩色 SHO + 星点转色】(2026-08-11 NGC7380 验证,需 StarNet2 CLI):
      逐通道 load→[crop]→subsky→autostretch → `rgbcomp`(S→R,H→G,O→B) →
      **StarNet2 CLI 分星**(-i comp -o starless -n stars,`-n`=unscreen 纯星点层) →
      星点层重映射(split→`pm "$rs_h$*0.5+$rs_o$*0.5"`→rgbcomp,得 R=H/G=½H+½O/B=O) →
      starless 处理(subsky 中性化 + rmgreen 去绿 + satu) → `pm` screen 合回。返回 <output>.png,全程零 PI。

    **铁律:重映射只对 StarNet2 的纯星点层做,绝不带星云**(否则残留星云被重映射、合回出错色斑)。
    StarNet2 读 FITS(不读 XISF),故各步存 Siril FITS。缺 StarNet2 CLI 时抛错(去 starnetastro.com/cli-tools 装)。
    """
    import subprocess
    sn = starnet_exe()
    if not sn:
        raise RuntimeError("StarNet2 CLI 不可用:在配置填 starnet_path(下载 starnetastro.com/cli-tools)")
    R = str(config.RUN_DIR)
    _str = _stretch_cmds(stretch, target_bg, ght)   # 三通道同一拉伸(同 target_bg → 背景对齐)
    for name, p in (("S", s_path), ("H", h_path), ("O", o_path)):
        cmds = [f"cd {R}", "load " + str(p).replace("\\", "/")]
        if crop:
            cmds.append("crop " + crop)
        cmds += ["subsky " + bg] + _str + [f"save _sn_{name}"]
        run_script(cmds, timeout=timeout)
        if not os.path.exists(os.path.join(R, f"_sn_{name}.fit")):
            raise RuntimeError(f"Siril SHO 通道 {name} 处理失败")
    run_script([f"cd {R}", "rgbcomp _sn_S _sn_H _sn_O -out=_sn_comp"], timeout=timeout)
    comp = os.path.join(R, "_sn_comp.fit")
    if not os.path.exists(comp):
        raise RuntimeError("Siril rgbcomp 合成失败")
    # StarNet2 CLI 分星(-n = 纯星点层)
    sless = os.path.join(R, "_sn_starless.fit").replace("\\", "/")
    stars = os.path.join(R, "_sn_stars.fit").replace("\\", "/")
    subprocess.run([sn, "-i", comp.replace("\\", "/"), "-o", sless, "-n", stars, "-s", str(stride)],
                   capture_output=True, text=True, timeout=timeout)
    if not (os.path.exists(sless) and os.path.exists(stars)):
        raise RuntimeError("StarNet2 CLI 分星失败(未产出 starless/stars)")
    # 星点层重映射(纯星点,不带星云):R=H, G=½H+½O, B=O
    run_script([f"cd {R}", "load _sn_stars", "split _sn_rs _sn_rh _sn_ro"], timeout=timeout)
    run_script([f"cd {R}", 'pm "$_sn_rh$*0.5+$_sn_ro$*0.5"', "save _sn_rmix"], timeout=timeout)
    run_script([f"cd {R}", "rgbcomp _sn_rh _sn_rmix _sn_ro -out=_sn_rstars"], timeout=timeout)
    # starless 处理:背景中性(subsky)+ 最大中性去绿(rmgreen 1)+ [局部对比 clahe] + 护背景提饱和
    proc = [f"cd {R}", "load _sn_starless", "subsky 1"] + ["rmgreen 1"] * max(0, int(degreen))
    if clahe and clahe > 0:
        proc.append(f"clahe {clahe} 8")          # 局部对比(= PI LHE);tileSize 8
    if satu and satu > 0:
        proc.append(f"satu {satu} {satu_bgf}")   # background_factor 护背景噪声不被提饱和
        # 【关键】提饱和会把残留绿一起放大 → 饱和后再补一道去绿。rmgreen 最大中性只削"绿为最大通道"
        # 的像素,金(R≥G)/蓝(B≥G)完全不动 → 只去绿不伤金蓝(治好"高饱和后外围返绿")。
        proc += ["rmgreen 1"] * max(0, int(degreen))
    proc.append("save _sn_sless_p")
    run_script(proc, timeout=timeout)
    # screen 合回
    out = str(output_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    ok, log = run_script([f"cd {R}", 'pm "1-(1-$_sn_sless_p$)*(1-$_sn_rstars$)"', "savepng " + out],
                         timeout=timeout)
    final = out + ".png"
    if not os.path.exists(final):
        raise RuntimeError("Siril SHO(含星点转色)合回失败\n" + log[-1000:])
    return final


def compose_sho(s_path: str, h_path: str, o_path: str, output_noext: str, *,
                crop: str | None = None, bg: str = "1", degreen: int = 1,
                satu: float = 0.7, target_bg: float = 0.08, stretch: str = "auto",
                ght: dict | None = None, clahe: float = 0.0, satu_bgf: float = 1.0,
                timeout: float = 1800.0) -> str:
    """【无 PI 彩色 SHO 合成】(2026-08-11 NGC7380 验证 + 精修):
      逐通道 load→[crop 去黑边]→subsky 背景→**拉伸(见 _stretch_cmds,三通道同 target_bg 背景对齐)** →
      `rgbcomp`(S→R,H→G,O→B) → 合成图 `subsky 1` 中性化 → `rmgreen`×degreen 最大中性去绿 →
      [clahe 局部对比] → `satu`(护背景) → savepng。全程零 PixInsight。返回 <output_noext>.png。

    crop: "x y w h"(去对齐黑边);None=不裁。target_bg: 三通道统一背景电平(默认 0.08 暗 moody)。
    stretch: "auto"(纯 autostretch,稳,暗 moody 默认)/ "ght"(autostretch 后叠 GHS 揭示暗弱,见 _stretch_cmds)。
    clahe: >0 开局部对比(cliplimit,~2);satu_bgf: satu 的 background_factor(护背景噪声不被提饱和)。
    【NGC7380 实测取向】target_bg=0.08 暗 moody 星云清晰;stretch="ght" 大幅揭示外围淡云(偏亮偏绿,非 moody)。
    **待完善**:外围淡云的**绿→金 色彩转换**(rmgreen 最大中性只能中性化、做不到 Hubble 式转金;
      需色相旋转/分区上色,Siril 色彩工具有限)——审美方向留用户定。星点转色见 compose_sho_stars(已跑通)。
    """
    R = str(config.RUN_DIR)
    _str = _stretch_cmds(stretch, target_bg, ght)   # 三通道同一拉伸(同 target_bg → 背景对齐)
    for name, p in (("S", s_path), ("H", h_path), ("O", o_path)):
        cmds = [f"cd {R}", "load " + str(p).replace("\\", "/")]
        if crop:
            cmds.append("crop " + crop)
        cmds += ["subsky " + bg] + _str + [f"save _sho_{name}"]
        run_script(cmds, timeout=timeout)
        if not os.path.exists(os.path.join(R, f"_sho_{name}.fit")):
            raise RuntimeError(f"Siril SHO 通道 {name} 处理失败")
    out = str(output_noext).replace("\\", "/")
    if out.lower().endswith(".png"):
        out = out[:-4]
    cmds = [f"cd {R}", "rgbcomp _sho_S _sho_H _sho_O -out=_sho_rgb", "load _sho_rgb", "subsky 1"]
    cmds += ["rmgreen 1"] * max(0, int(degreen))
    if clahe and clahe > 0:
        cmds.append(f"clahe {clahe} 8")          # 局部对比(= PI LHE)
    if satu and satu > 0:
        cmds.append(f"satu {satu} {satu_bgf}")   # background_factor 护背景不被提饱和
        cmds += ["rmgreen 1"] * max(0, int(degreen))   # 提饱和会返绿 → 饱和后补去绿(只削绿不伤金蓝)
    cmds.append("savepng " + out)
    ok, log = run_script(cmds, timeout=timeout)
    final = out + ".png"
    if not os.path.exists(final):
        raise RuntimeError("Siril SHO 合成失败\n" + log[-1200:])
    return final
