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


GOLDBLUE_DEFAULT = {"ks": 0.8, "kh": 0.85, "gate": 3.0, "kg": 0.65, "kog": 0.15, "kb": 2.8}


def compose_sho_stars(s_path: str, h_path: str, o_path: str, output_noext: str, *,
                      crop: str | None = None, bg: str = "1", degreen: int = 1,
                      satu: float = 0.7, stride: int = 256, target_bg: float = 0.08,
                      stretch: str = "auto", ght: dict | None = None, clahe: float = 0.0,
                      satu_bgf: float = 1.0, star_satu: float = 1.2,
                      palette: str = "classic", gb: dict | None = None,
                      timeout: float = 1800.0) -> str:
    """【无 PI 彩色 SHO + 星点转色】(2026-08-11 NGC7380 验证,需 StarNet2 CLI):
      通道拉伸 → `rgbcomp`(S→R,H→G,O→B) → **StarNet2 CLI 分星**(-n=纯星点层) →
      星点层重映射(R=H/G=½H+½O/B=O + star_satu 提饱和) → starless 调色 → `pm` screen 合回。零 PI。

    palette:
      "classic"(默认)= 逐通道 autostretch(见 _stretch_cmds)→ rgbcomp;starless 走 subsky/rmgreen/clahe/satu。
        出**有效但简单的 SHO**(青核金边,近 PI 的 hss/natural 档)。
      "goldblue" = **金橙弧+蓝 OIII 核心**(逼近 PI 的 sho 艺术档,gbK 定稿)。关键:
        ①**先 rgbcomp 成 linear → 合成图 `autostretch -linked` 统一拉伸**(单一 MTF 保通道相对强弱,
          否则逐通道 auto 抹平通道→无蓝核);②StarNet2 分星后,**对 starless split 出保比例的 S/H/O**、
          逐通道 subsky 压背景→0(否则残底被染品红)、再 pixel-math 重组:
          R=(S·ks+H·kh)·(1-O·gate) / G=H·kg·(1-O·gate)+O·kog / B=O·kb
          → Ha→金、SII→橙、OIII 门控把 R/G 逐出核心+提 B→蓝核;③recombine 后 subsky 中性化残底 + satu。
        gb 覆盖系数(默认 GOLDBLUE_DEFAULT)。**别把金蓝配方套到星点**(星点 OIII 亮→被门控成纯蓝,见铁律)。

    **铁律:重映射/调色只对 StarNet2 分出的层做**——星点转色只碰纯星点层,金蓝只碰 starless;绝不混。
    StarNet2 读 FITS(不读 XISF),故各步存 Siril FITS。缺 StarNet2 CLI 时抛错(去 starnetastro.com/cli-tools 装)。
    """
    import subprocess
    sn = starnet_exe()
    if not sn:
        raise RuntimeError("StarNet2 CLI 不可用:在配置填 starnet_path(下载 starnetastro.com/cli-tools)")
    R = str(config.RUN_DIR)
    if palette == "goldblue":
        # 逐通道只 crop+subsky(linear,不各自拉伸)→ rgbcomp linear → 合成图 linked 统一拉伸(保比例→蓝核)
        for name, p in (("S", s_path), ("H", h_path), ("O", o_path)):
            cmds = [f"cd {R}", "load " + str(p).replace("\\", "/")]
            if crop:
                cmds.append("crop " + crop)
            cmds += ["subsky " + bg, f"save _sn_{name}"]
            run_script(cmds, timeout=timeout)
            if not os.path.exists(os.path.join(R, f"_sn_{name}.fit")):
                raise RuntimeError(f"Siril SHO 通道 {name} 处理失败")
        run_script([f"cd {R}", "rgbcomp _sn_S _sn_H _sn_O -out=_sn_lin", "load _sn_lin",
                    f"autostretch -linked -2.8 {target_bg}", "save _sn_comp"], timeout=timeout)
    else:
        _str = _stretch_cmds(stretch, target_bg, ght)   # 三通道同一 target_bg → 背景对齐(逐通道 auto)
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
    # 【星点提饱和】重映射 R=H/G=½H+½O/B=O 对宽带星点(H≈O≈S)输出近白 → 单独提饱和放大冷暖色差,
    # 让星点有自己的蓝白/金色(bg_factor=0:黑底星点全提;不碰星云,合回前做 → 不违反"只调纯星点层")。
    if star_satu and star_satu > 0:
        run_script([f"cd {R}", "load _sn_rstars", f"satu {star_satu} 0", "save _sn_rstars"], timeout=timeout)
    # starless 调色(按 palette)→ 存 _sn_sless_p
    if palette == "goldblue":
        g = {**GOLDBLUE_DEFAULT, **(gb or {})}
        # starless split 出保比例 S/H/O(_sn_comp 是 linked 拉伸,故 starless 也保比例)→ 逐通道 subsky
        # 把各通道背景压到≈0(否则残底被 R=S+Ha/B=O·kb 染成品红)。再 pixel-math 金蓝重组。
        run_script([f"cd {R}", "load _sn_starless", "split _gb_s _gb_h _gb_o"], timeout=timeout)
        for c in ("_gb_s", "_gb_h", "_gb_o"):
            run_script([f"cd {R}", f"load {c}", "subsky 1", f"save {c}"], timeout=timeout)
        _ga = g["gate"]
        Rx = f'($_gb_s$*{g["ks"]}+$_gb_h$*{g["kh"]})*(1-$_gb_o$*{_ga})'   # Ha+SII→金,OIII门控压核心红
        Gx = f'$_gb_h$*{g["kg"]}*(1-$_gb_o$*{_ga})+$_gb_o$*{g["kog"]}'    # Ha→绿(金的黄分量),核心退绿
        Bx = f'$_gb_o$*{g["kb"]}'                                          # OIII→蓝(提权→蓝核)
        run_script([f"cd {R}", f'pm "{Rx}"', "save _gb_R"], timeout=timeout)
        run_script([f"cd {R}", f'pm "{Gx}"', "save _gb_G"], timeout=timeout)
        run_script([f"cd {R}", f'pm "{Bx}"', "save _gb_B"], timeout=timeout)
        proc = [f"cd {R}", "rgbcomp _gb_R _gb_G _gb_B -out=_gb_rgb", "load _gb_rgb", "subsky 1"]
        proc += ["rmgreen 1"] * max(0, int(degreen))   # 清门控外零星残绿
        if clahe and clahe > 0:
            proc.append(f"clahe {clahe} 8")
        if satu and satu > 0:
            proc.append(f"satu {satu} {satu_bgf}")
        proc.append("save _sn_sless_p")
        run_script(proc, timeout=timeout)
    else:
        # classic:背景中性(subsky)+ 最大中性去绿(rmgreen)+ [clahe] + 护背景提饱和
        proc = [f"cd {R}", "load _sn_starless", "subsky 1"] + ["rmgreen 1"] * max(0, int(degreen))
        if clahe and clahe > 0:
            proc.append(f"clahe {clahe} 8")          # 局部对比(= PI LHE);tileSize 8
        if satu and satu > 0:
            proc.append(f"satu {satu} {satu_bgf}")   # background_factor 护背景噪声不被提饱和
            # 【别加"饱和后 rmgreen"】会削暗青/蓝 OIII 核心(核心均亮 0.181→0.148);残绿本就~0.01 不值当。
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
        # (不加"饱和后 rmgreen":会削暗青/蓝 OIII 核心;残留绿很轻不值当,见 compose_sho_stars 注)
    cmds.append("savepng " + out)
    ok, log = run_script(cmds, timeout=timeout)
    final = out + ".png"
    if not os.path.exists(final):
        raise RuntimeError("Siril SHO 合成失败\n" + log[-1200:])
    return final
