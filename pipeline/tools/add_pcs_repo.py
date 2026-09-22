# -*- coding: utf-8 -*-
"""给 PixInsight 加上 PhotometricContinuumSubtraction 的更新仓库。

用途:星系混入窄带信号时做**测光连续谱扣除**(比手工估 k 的 `Ha − k·R` 可靠)。
  脚本:PhotometricContinuumSubtraction v1.4.2 — Charles Hagen
  仓库:https://raw.githubusercontent.com/charleshagen/pixinsight/main/updates/
  文档:https://www.nightphotons.com/software/photometric-continuum-subtraction/

【必须在 PixInsight 关闭时运行】PI 退出时会整个重写 PixInsight.ini,
  开着改等于白改(它会用内存里的旧设置覆盖回去)。脚本自己会拦这一条。

跑完还要在 PI 里手动走两步(PI 没有可编程的"检查更新"入口):
  资源 → 更新 → 检查更新 → 应用 → 重启 PI
"""
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

INI = Path.home() / "AppData/Roaming/Pleiades/PixInsight.ini"
REPO = "https://raw.githubusercontent.com/charleshagen/pixinsight/main/updates/"
KEY = r"Global\UpdateManager\Repositories"


def pi_running():
    """True=在跑 / False=没跑 / None=**查不出来**。三态必须分清。

    【这里踩过坑(2026-09-21)】原来写 `text=True`,而 Windows 的 tasklist 输出是 GBK ——
    UTF-8 解码在读取线程里抛异常,stdout 变成 None,`in` 触发 TypeError 被 except 吞掉
    → 返回 False → **守卫失效,在 PI 运行时照样改了配置**。
    守卫返回"没跑"和"查不出来"绝不能是同一个值:查不出来时要**拒绝执行**,不是放行。
    """
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq PixInsight.exe"],
                           capture_output=True, timeout=20)
        out = (r.stdout or b"").decode("gbk", errors="replace")
        return "PixInsight.exe" in out
    except Exception as e:
        print("  查进程失败(%s)—— 无法确认 PI 是否在跑" % str(e)[:60])
        return None


def main() -> int:
    if not INI.exists():
        print("找不到 PixInsight.ini:", INI)
        return 1
    st = pi_running()
    if st is not False:            # True 或 None(查不出来)都不动 —— 宁可不做
        print("PixInsight 还在运行" if st else "无法确认 PI 是否在运行")
        print("→ 不改配置。请完全退出 PI 后再跑本脚本。")
        print("  (PI 退出时会用内存里的设置整个重写 ini,现在改会被覆盖。)")
        return 2

    txt = INI.read_text(encoding="utf-8", errors="replace")
    if REPO.rstrip("/") in txt:
        print("仓库已经在列表里,无需重复添加。")
        return 0

    idx = [int(m.group(1)) for m in
           re.finditer(re.escape(KEY) + r"\\(\d{8})=", txt)]
    if not idx:
        print("ini 里找不到仓库条目,格式可能变了 —— 不动它,请手动添加。")
        return 3
    nxt = max(idx) + 1
    last = "%s\\%08d=" % (KEY, max(idx))
    i = txt.index(last)
    eol = txt.index("\n", i)
    line = "%s\\%08d=%s" % (KEY, nxt, REPO)
    new = txt[:eol + 1] + line + "\r\n" + txt[eol + 1:]

    bak = INI.with_suffix(".ini.bak_pcs_%d" % int(time.time()))
    shutil.copy2(INI, bak)
    INI.write_text(new, encoding="utf-8")
    print("已添加为第 %d 条:%s" % (nxt, REPO))
    print("备份:", bak)
    print()
    print("接下来在 PI 里:资源 → 更新 → 检查更新 → 应用 → 重启 PI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
