"""多模态 LLM 评委(VisionCritic)—— 任务 P3。

把处理后图像的**预览 + 指标 + 上下文**交给用户配置的视觉模型,返回结构化质量判断:
问题清单 / 调整方向(离散有界)/ 是否停止 / 置信度 / 理由。
用于数值指标够不着的语义/审美判断(偏色、过锐化伪影、过降噪塑料感、暗部假细节、
星点膨胀、背景发白、过饱和、边缘伪影/不均等,见技术方案 §6.4)。

多厂商:anthropic 用 Messages API;openai/kimi/deepseek/openai_compatible 用
OpenAI 兼容 chat/completions。配置来自 _config/settings.json(见 settings_ui)。
仅用 stdlib(urllib),不引额外依赖。

用法:
    python -m orchestrator.critic --image _run/r12_final.png --context "IC4592 宽带成片"
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import config

# 评委关注的问题类型(与 §6.4 过处理护栏对应)
ISSUES = [
    "color_cast",          # 偏色
    "over_sharpen",        # 过锐化 / 絮状蚯蚓纹理
    "over_denoise",        # 过降噪 / 塑料感
    "fake_detail",         # 暗部假细节
    "star_bloat",          # 星点膨胀 / 不自然
    "background_washout",  # 背景发白 / 被抬亮
    "over_saturation",     # 过饱和
    "edge_artifact",       # 边缘伪影 / 明暗不均
    "residual_gradient",   # 残余梯度
    "noise",               # 噪声偏高
]

# ── 评委问题 → 补救方案登记表（LLM 无关，pipeline 与 UI 共用）────────────────────
# 每个问题回答用户第 3 问："要修它，该从哪一步开始？成片阶段还有没有救？"
# 字段：
#   stage      —— 问题**根源**所在的流程阶段（stop_after 词表：integrate/crop_gc/bxt/
#                 denoise/stretch/combine/starless/color/final）。
#   in_place   —— 能否在**成片**上无损修掉（True=程序可自动/用户可手动，不必回退）。
#   knob       —— 要回退时该调的参数/开关（给 UI 显示成"调这个"）。
#   how        —— 一句话人话建议。
# 铁律 8/21：主观项与"已把信息压没"的项（过锐化/过降噪/拉爆核心）在成片阶段**不可逆**，
# 只能回退到根源阶段减力度重跑；这正是必须告诉用户"退回哪一步"的原因。
REMEDY = {
    "residual_gradient":  {"stage": "final",    "in_place": True,  "knob": None,
                           "how": "成片可直接再做一次梯度校正（程序已自动尝试）"},
    "edge_artifact":      {"stage": "final",    "in_place": True,  "knob": None,
                           "how": "成片可直接多裁一圈边缘（程序已自动尝试）"},
    "noise":              {"stage": "denoise",  "in_place": True,  "knob": "线性降噪力度",
                           "how": "轻噪成片可再降一次；明显噪声退回「线性降噪」加大力度更干净"},
    "over_saturation":    {"stage": "color",    "in_place": True,  "knob": "饱和度提升",
                           "how": "成片可直接降饱和；或退回「调色」调小 saturation"},
    "color_cast":         {"stage": "color",    "in_place": False, "knob": "配色 / 去绿目标",
                           "how": "退回「调色」换配色档或调去绿目标；成片强行去色会伤星云"},
    "background_washout": {"stage": "stretch",  "in_place": False, "knob": "tone_faint / GHS 力度",
                           "how": "退回「拉伸」调小 tone_faint——成片压中间调会压平梯度，无救"},
    "over_sharpen":       {"stage": "bxt",      "in_place": False, "knob": "BXT 锐化",
                           "how": "退回「BXT」减小锐化——蚯蚓纹/絮状是锐化过度，不可逆"},
    "over_denoise":       {"stage": "denoise",  "in_place": False, "knob": "降噪力度",
                           "how": "退回「线性降噪」减小力度——塑料感是降噪抹掉了细节，不可逆"},
    "star_bloat":         {"stage": "starless", "in_place": False, "knob": "星点流程",
                           "how": "退回「去星/星点」——星点膨胀要在星点处理阶段修，成片改不动"},
    "fake_detail":        {"stage": "stretch",  "in_place": False, "knob": "拉伸 / GHS 力度",
                           "how": "退回「拉伸」减力度——暗部假细节是拉太狠，成片无救"},
    # score() / judge_ghs 会用到的额外标签
    "blown_core":         {"stage": "stretch",  "in_place": False, "knob": "tone_core / GHS 力度",
                           "how": "退回「拉伸」降 tone_core——核心过曝在成片已无救"},
    "too_dark":           {"stage": "stretch",  "in_place": False, "knob": "tone_faint / GHS 力度",
                           "how": "退回「拉伸」加大力度——暗弱信号提亮要在拉伸阶段做"},
    "washed_out":         {"stage": "stretch",  "in_place": False, "knob": "tone_faint / GHS 力度",
                           "how": "退回「拉伸」调小力度，背景发白多因拉伸过猛"},
    "purple_cast":        {"stage": "stretch",  "in_place": False, "knob": "拉伸 / 背景校准",
                           "how": "退回「拉伸」减力度——暗部发紫是过拉，成片 SCNR 会伤色"},
}


def remedy_plan(issues, in_place_done=None):
    """把评委问题列表拆成【已自动修正】与【需你决定·退回某步】两组，供 UI/日志展示。

    in_place_done: 程序本轮**确实自动执行了**的 in_place 补救（问题名集合）。
    返回 {auto_fixed:[{issue,how}], needs_attention:[{issue,stage,in_place,knob,how}], unknown:[...]}。
    """
    done = set(in_place_done or [])
    auto_fixed, needs, unknown = [], [], []
    for iss in issues or []:
        r = REMEDY.get(iss)
        if not r:
            unknown.append(iss)
            continue
        if iss in done:
            auto_fixed.append({"issue": iss, "how": r["how"]})
        else:
            needs.append({"issue": iss, "stage": r["stage"], "in_place": r["in_place"],
                          "knob": r["knob"], "how": r["how"]})
    # 排序：需回退的（in_place=False，更要紧）排前面
    needs.sort(key=lambda d: (d["in_place"], d["stage"]))
    return {"auto_fixed": auto_fixed, "needs_attention": needs, "unknown": unknown}


MAX_TOKENS = 8192   # 推理模型(如 kimi-k3)会先消耗大量 reasoning token,需留足额度输出

_PROVIDER_BASEURL = {
    "openai": "https://api.openai.com/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

PROMPT = """你是资深深空天体摄影后期评审。下面给你一张已处理图像的【预览渲染】和一组数值指标。
请判断它在这些常见问题上的表现:{issues}。

原则:
- 结合你看到的画面 + 数值指标综合判断。
- 只能建议对已有信号做拉伸/参数调整,禁止建议"补画/凭空添加信号"。
- 调整用离散有界档位。

只输出严格 JSON(不要任何多余文字),格式:
{{"verdict":"ok|needs_adjustment|reject",
  "issues":[从问题列表里选中的若干],
  "actions":[{{"target":"参数名(如 saturation/stretch/denoise/scnr/crop 等)","direction":"increase|decrease","magnitude":"slight|moderate|strong","note":"简述"}}],
  "stop":true|false,
  "confidence":0.0到1.0,
  "reason":"一句话理由(中文)"}}

上下文:{context}
数值指标:{metrics}
"""


def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _http_json(url: str, headers: dict, body: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_anthropic(model: str, key: str, prompt: str, img_b64: str) -> str:
    body = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/png", "data": img_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    r = _http_json("https://api.anthropic.com/v1/messages", headers, body)
    parts = [c.get("text", "") for c in r.get("content", []) if c.get("type") == "text"]
    return "".join(parts)


def _call_openai_compatible(base_url: str, model: str, key: str,
                            prompt: str, img_b64: str) -> str:
    body = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        # 不发 temperature:部分模型(如 kimi-k3)只接受固定值,省略以最大兼容
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + img_b64}},
            ],
        }],
    }
    headers = {"Authorization": "Bearer " + key, "content-type": "application/json"}
    r = _http_json(base_url.rstrip("/") + "/chat/completions", headers, body)
    msg = r["choices"][0]["message"]
    # 推理模型:正文可能在 content;若为空则从 reasoning_content 兜底提取
    return (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "")


def _media_type(path: str) -> str:
    p = path.lower()
    if p.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if p.endswith(".webp"):
        return "image/webp"
    return "image/png"


def _call_anthropic_multi(model: str, key: str, prompt: str,
                          images: list[tuple[str, str]]) -> str:
    """images: [(label, path), ...];按 标签→图 交错,最后附 prompt。"""
    content: list[dict] = []
    for label, path in images:
        content.append({"type": "text", "text": label + "："})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": _media_type(path), "data": _b64(path)}})
    content.append({"type": "text", "text": prompt})
    body = {"model": model, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": content}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    r = _http_json("https://api.anthropic.com/v1/messages", headers, body)
    parts = [c.get("text", "") for c in r.get("content", []) if c.get("type") == "text"]
    return "".join(parts)


def _call_openai_multi(base_url: str, model: str, key: str, prompt: str,
                       images: list[tuple[str, str]]) -> str:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for label, path in images:
        content.append({"type": "text", "text": label + "："})
        content.append({"type": "image_url", "image_url": {
            "url": f"data:{_media_type(path)};base64," + _b64(path)}})
    body = {"model": model, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": content}]}
    headers = {"Authorization": "Bearer " + key, "content-type": "application/json"}
    r = _http_json(base_url.rstrip("/") + "/chat/completions", headers, body)
    msg = r["choices"][0]["message"]
    return (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "")


def _ask_multi(prompt: str, images: list[tuple[str, str]]) -> str:
    provider, model, key, base_url = _llm_config()
    if not (provider and model and key):
        raise ValueError("LLM 未配置(provider/model/api_key)。")
    if provider == "anthropic":
        return _call_anthropic_multi(model, key, prompt, images)
    url = base_url or _PROVIDER_BASEURL.get(provider)
    if not url:
        raise ValueError(f"未知供应商且未提供 base_url: {provider}")
    return _call_openai_multi(url, model, key, prompt, images)


def _ask_multi_safe(prompt: str, images: list[tuple[str, str]]):
    try:
        return _ask_multi(prompt, images), None
    except urllib.error.HTTPError as e:
        return None, {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"}
    except (urllib.error.URLError, OSError) as e:
        return None, {"error": f"网络错误: {e}"}
    except ValueError as e:
        return None, {"error": str(e)}


GHS_PROMPT = """你是资深深空天体摄影后期评审。第一张是【当前成片】(目标 {target},宽带 OSC,已去除星点 starless);
其余是同目标的 AstroBin 优秀参考作品。请**对照参考**,判断当前成片的**拉伸力度(GHS)**是否合适。

判据:
- 背景过亮 / 噪点明显 / 暗部出现发紫(紫斑) → 拉伸过猛,应减小 D;
- 星云主体太暗、看不出结构层次 → 拉伸不足,应增大 D;
- 目标观感(向参考靠拢):暗而干净的背景 + 蓝色反射核有内部结构且不死白 + 暖棕色尘埃。

当前 GHS 力度 D = {cur_d}(有效范围 0~2.5;越大,暗弱信号提得越亮)。
给出你建议的 D 值;若当前已接近参考、无需再调,置 stop=true。

只输出严格 JSON(无多余文字):
{{"suggested_D": 数值(0~2.5),
  "too_strong": true|false,
  "issues": [从 "purple_cast"、"noise"、"too_dark"、"washed_out"、"blown_core" 中选中的],
  "stop": true|false,
  "confidence": 0.0到1.0,
  "reason": "一句话中文理由"}}
上下文:{context}"""


def judge_ghs(render_path: str, ref_paths: list[str], target: str = "",
              context: str = "", cur_d: float = 1.0) -> dict:
    """对照参考图判断 GHS 力度,返回 {suggested_D, too_strong, issues, stop, confidence, reason} 或 {error}。"""
    images = [("当前成片", render_path)]
    images += [(f"参考{i + 1}", p) for i, p in enumerate(ref_paths)]
    prompt = GHS_PROMPT.format(target=target or "(未知)", cur_d=cur_d,
                               context=context or "(无)")
    text, err = _ask_multi_safe(prompt, images)
    if err:
        return err
    try:
        m = _parse_json(text)
        m["suggested_D"] = max(0.0, min(2.5, float(m.get("suggested_D", cur_d))))
        return m
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"error": "GHS 判断无法解析为 JSON", "raw": text[:800]}


STRETCH_MODE_PROMPT = """你是资深深空天体摄影后期评审。第一张是【当前目标的初步 STF 拉伸预览】(目标 {target},宽带 OSC),
其余(若有)是同目标的 AstroBin 优秀参考作品。请判断该目标应采用的**拉伸策略**。

判据:
- 明亮发射星云 / 星团 / 高面亮度主体(信号强、主体轮廓明确,标准 STF/HT 拉伸就已足够)
  → mode="stf"(不需要 GHS),通常**保留星点**;
- 暗弱反射星云 / 暗云 / 低面亮度弥散星云(主体淹没在暗背景里,需要额外提亮暗弱信号)
  → mode="ghs"(用 GHS 抠出主体),常做 **starless** 突出星云。
参考作品能帮助你判断该目标在社区里通常呈现为"明亮主体"还是"暗弱弥散"。

只输出严格 JSON(无多余文字):
{{"mode":"stf"|"ghs",
  "ghs_d": 数值(仅 mode=ghs 时有意义,0.3~1.5),
  "keep_stars": true|false,
  "confidence": 0.0到1.0,
  "reason":"一句话中文理由"}}
上下文:{context}"""


def judge_stretch_mode(preview_path: str, ref_paths: list[str] | None = None,
                       target: str = "", context: str = "") -> dict:
    """判断目标该用 STF 还是 GHS 拉伸(结合 AstroBin 参考图)。
    返回 {mode, ghs_d, keep_stars, confidence, reason} 或 {error}。"""
    images = [("当前目标STF预览", preview_path)]
    images += [(f"参考{i + 1}", p) for i, p in enumerate(ref_paths or [])]
    prompt = STRETCH_MODE_PROMPT.format(target=target or "(未知)", context=context or "(无)")
    text, err = _ask_multi_safe(prompt, images)
    if err:
        return err
    try:
        m = _parse_json(text)
        m["mode"] = "ghs" if str(m.get("mode", "")).lower() == "ghs" else "stf"
        try:
            m["ghs_d"] = max(0.3, min(1.5, float(m.get("ghs_d", 0.5))))
        except (TypeError, ValueError):
            m["ghs_d"] = 0.5
        m["keep_stars"] = bool(m.get("keep_stars", m["mode"] == "stf"))
        return m
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"error": "拉伸模式判断无法解析为 JSON", "raw": text[:800]}


FIELD_EXTENDED_PROMPT = """你是资深深空天体摄影后期评审。这是目标 {target} 的拉伸预览(宽带 OSC),
目录类型是**星团**。星团处理有个原则:若画面里除了星团/星点是空旷星场,就该把背景钉深黑
(拉背景只会发白成奶雾);但**若画面里还有较大面积的暗星云(暗云带/尘埃)或发射/反射星云**,
那就不能钉黑、要正常保留背景结构。

请只判断这一件事:**除了星团本身的密集恒星和零散星点,画面里有没有"较大面积、值得保留"的
暗云或星云结构?**(小范围、噪声级的不算;要成片、成带、占可观面积才算。)

只输出严格 JSON(无多余文字):
{{"has_extended": true|false,
  "kind": "darkcloud"|"nebula"|"both"|"none",
  "confidence": 0.0到1.0,
  "reason": "一句话中文理由"}}
上下文:{context}"""


def judge_field_extended(preview_path: str, target: str = "", context: str = "") -> dict:
    """判断星团画面里除了星点,有没有较大面积暗云/星云值得保留(=不该钉黑背景)。
    返回 {has_extended, kind, confidence, reason} 或 {error}。"""
    text, err = _ask_safe(
        FIELD_EXTENDED_PROMPT.format(target=target or "(未知)", context=context or "(无)"),
        preview_path)
    if err:
        return err
    try:
        m = _parse_json(text)
        m["has_extended"] = bool(m.get("has_extended", False))
        return m
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"error": "延展结构判断无法解析为 JSON", "raw": text[:800]}


DUST_PROMPT = """你是资深深空天体摄影后期评审。这是目标 {target} 的星云预览(窄带 SHO,已去星)。

请判断:**画面里有没有显著的暗星云 / 尘埃结构**(如象鼻状尘柱、暗带、球状暗云、
遮挡在发光气体前的暗色团块)?这类结构内部往往层次丰富,但容易被压成"死黑"一片,
需要专门提亮中间调把层次揭示出来;而**没有暗尘的目标**(纯发射气体、空旷星场)做这步
就是多余的提亮。

判据:
- 有大面积、成形的暗色结构嵌在发光星云中,且明显缺内部层次 → prominence "high";
- 有一些暗带/暗块但不主导画面 → "medium";
- 仅零星细小暗纹 → "low";
- 基本没有暗尘结构 → has_dust=false, prominence "none"。

只输出严格 JSON(无多余文字):
{{"has_dust": true|false,
  "prominence": "high"|"medium"|"low"|"none",
  "confidence": 0.0到1.0,
  "reason": "一句话中文理由"}}
上下文:{context}"""


def judge_dust(preview_path: str, target: str = "", context: str = "") -> dict:
    """判断画面有无显著暗星云/尘埃结构(决定是否做"暗尘层次揭示")。
    返回 {has_dust, prominence, confidence, reason} 或 {error}。"""
    text, err = _ask_safe(
        DUST_PROMPT.format(target=target or "(未知)", context=context or "(无)"), preview_path)
    if err:
        return err
    try:
        m = _parse_json(text)
        m["has_dust"] = bool(m.get("has_dust", False))
        p = str(m.get("prominence", "none")).lower()
        m["prominence"] = p if p in ("high", "medium", "low", "none") else "none"
        return m
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"error": "暗尘判断无法解析为 JSON", "raw": text[:800]}


SCORE_PROMPT = """你是资深深空天体摄影后期评审。请给这张成片打分(0-10,可小数),并给一句话总评。
维度:background=背景干净度/中性度;star_color=星点颜色自然度;core=主体/核心细节与层次。
只输出严格 JSON(无多余文字):
{{"overall":数值,"background":数值,"star_color":数值,"core":数值,"comment":"一句话中文"}}
上下文:{context}"""


def score(image_path: str, context: str = "") -> dict:
    """给成片打分,返回 {overall,background,star_color,core,comment} 或 {error}。"""
    text, err = _ask_safe(SCORE_PROMPT.format(context=context or "(无)"), image_path)
    if err:
        return err
    try:
        m = _parse_json(text)
        for k in ("overall", "background", "star_color", "core"):
            try:
                m[k] = max(0.0, min(10.0, float(m.get(k, 0))))
            except (TypeError, ValueError):
                m[k] = 0.0
        return m
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"error": "评分无法解析为 JSON", "raw": text[:600]}


def _parse_json(text: str) -> dict:
    """从模型输出里抽取 JSON(容忍 ```json 代码围栏)。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    # 取第一个 { 到最后一个 }
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        t = t[i:j + 1]
    return json.loads(t)


def _llm_config():
    llm = config.get_setting("llm", {}) or {}
    return ((llm.get("provider") or "").strip(), (llm.get("model") or "").strip(),
            (llm.get("api_key") or "").strip(), (llm.get("base_url") or "").strip())


def _ask(prompt: str, img_b64: str) -> str:
    """按配置供应商发起一次带图请求,返回模型文本(未配置/端点问题抛异常)。"""
    provider, model, key, base_url = _llm_config()
    if not (provider and model and key):
        raise ValueError("LLM 未配置(provider/model/api_key)。请先运行 "
                         "python -m orchestrator.settings_ui 填写。")
    if provider == "anthropic":
        return _call_anthropic(model, key, prompt, img_b64)
    url = base_url or _PROVIDER_BASEURL.get(provider)
    if not url:
        raise ValueError(f"未知供应商且未提供 base_url: {provider}")
    return _call_openai_compatible(url, model, key, prompt, img_b64)


def _ask_safe(prompt: str, image_path: str):
    """返回 (text, error_dict);二者其一非空。"""
    try:
        return _ask(prompt, _b64(image_path)), None
    except urllib.error.HTTPError as e:
        return None, {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"}
    except (urllib.error.URLError, OSError) as e:
        return None, {"error": f"网络错误: {e}"}
    except ValueError as e:
        return None, {"error": str(e)}


def critique(image_path: str, context: str = "", metrics: Any = None) -> dict:
    """调用配置的视觉模型评审图像,返回结构化判断(失败返回 {error:...})。"""
    prompt = PROMPT.format(issues="、".join(ISSUES),
                           context=context or "(无)",
                           metrics=json.dumps(metrics, ensure_ascii=False) if metrics else "(无)")
    text, err = _ask_safe(prompt, image_path)
    if err:
        return err
    try:
        verdict = _parse_json(text)
        provider, model, _, _ = _llm_config()
        verdict["_provider"], verdict["_model"] = provider, model
        return verdict
    except (json.JSONDecodeError, ValueError):
        return {"error": "模型返回无法解析为 JSON", "raw": text[:1000]}


CROP_PROMPT = """这张深空成片四周可能有边缘伪影/明暗不均/部分覆盖暗带。请判断为消除这些边缘问题、
应从每条边裁掉多少(占该方向尺寸的百分比,整数 0-15;干净的边给 0),在消除伪影前提下尽量少损失视场。
只输出严格 JSON:{{"left":n,"right":n,"top":n,"bottom":n}}。
上下文:{context}"""


def suggest_crop(image_path: str, context: str = "") -> dict:
    """让评委给出为消除边缘伪影应裁切的各边百分比。返回 {left,right,top,bottom}(%) 或 {error}。"""
    text, err = _ask_safe(CROP_PROMPT.format(context=context or "(无)"), image_path)
    if err:
        return err
    try:
        m = _parse_json(text)
        return {k: max(0.0, min(15.0, float(m.get(k, 0) or 0)))
                for k in ("left", "right", "top", "bottom")}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"error": "裁切建议无法解析为 JSON", "raw": text[:500]}


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    p = argparse.ArgumentParser(description="多模态 LLM 评委")
    p.add_argument("--image", required=True, help="要评审的预览 PNG")
    p.add_argument("--context", default="", help="上下文(目标/处理阶段等)")
    args = p.parse_args(argv)
    if not Path(args.image).exists():
        print(f"[✗] 图像不存在: {args.image}")
        return 1
    res = critique(args.image, context=args.context)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if "error" not in res else 2


if __name__ == "__main__":
    sys.exit(main())
