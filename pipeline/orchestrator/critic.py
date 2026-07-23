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
