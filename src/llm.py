"""大模型解释生成适配器（OpenAI 兼容协议，多厂商预设）。

设计原则
--------
1. **只生成解释，不参与决策**：不改风险概率、不改干预排序、不改判定。
2. **默认关闭**：未配置 Key 时返回模板文本，离线可跑。
3. **失败必降级**：超时/网络错误/限流/返回异常，一律回退模板，不抛异常。
4. **数字护栏**：模型输出中不得出现证据里没有的数字，否则判定违规并降级。
5. **可观测**：返回来源、模型名、耗时、重试次数、错误与护栏结果；另有 status() 供诊断。
6. **Key 只读环境变量**，不落盘、不写日志、不回传前端。

环境变量
--------
LLM_API_KEY    必填，缺失即视为未启用
LLM_BASE_URL   可选，缺省按 LLM_PROVIDER 预设
LLM_MODEL      可选，缺省按 LLM_PROVIDER 预设
LLM_PROVIDER   zhipu | dashscope | deepseek | openai | custom（默认 custom）
LLM_TIMEOUT    秒，默认 8
LLM_RETRIES    重试次数，默认 2
LLM_ENABLE     置 0 可强制关闭（即使配了 Key）
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

PRESETS = {
    "zhipu":     {"base": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "dashscope": {"base": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-turbo"},
    "deepseek":  {"base": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "openai":    {"base": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "custom":    {"base": "", "model": ""},
}

_CACHE: dict[str, dict] = {}
_STATE = {"fail": 0, "open_until": 0.0, "calls": 0, "fallbacks": 0, "last_error": ""}
CACHE_MAX = 128
BREAKER_THRESHOLD = 5       # 连续失败 5 次即熔断
BREAKER_COOLDOWN = 120.0    # 熔断 2 分钟


def _cfg() -> dict:
    prov = os.environ.get("LLM_PROVIDER", "custom").strip().lower()
    p = PRESETS.get(prov, PRESETS["custom"])
    return {
        "provider": prov,
        "key": os.environ.get("LLM_API_KEY", "").strip(),
        "base": (os.environ.get("LLM_BASE_URL") or p["base"]).rstrip("/"),
        "model": os.environ.get("LLM_MODEL") or p["model"],
        "timeout": float(os.environ.get("LLM_TIMEOUT", "8")),
        "retries": max(0, int(os.environ.get("LLM_RETRIES", "2"))),
        "enable": os.environ.get("LLM_ENABLE", "1") not in ("0", "false", "False"),
    }


def enabled() -> bool:
    c = _cfg()
    return bool(c["enable"] and c["key"] and c["base"] and c["model"])


def status() -> dict:
    """诊断用：不含 Key，可安全暴露给前端/日志。"""
    c = _cfg()
    now = time.time()
    return {
        "enabled": enabled(),
        "provider": c["provider"],
        "base_host": re.sub(r"^https?://([^/]+).*$", r"\1", c["base"]) if c["base"] else "",
        "model": c["model"],
        "timeout_s": c["timeout"],
        "retries": c["retries"],
        "circuit_open": _STATE["open_until"] > now,
        "circuit_cooldown_left_s": max(0, round(_STATE["open_until"] - now)),
        "stats": {"calls": _STATE["calls"], "fallbacks": _STATE["fallbacks"],
                  "consecutive_failures": _STATE["fail"], "cache_entries": len(_CACHE)},
        "last_error": _STATE["last_error"][:160],
    }


def _template(ev: dict) -> str:
    """规则模板：只用证据里的字段，绝不编造。"""
    prov = ev.get("province", "该省")
    stage = ev.get("stage", "该学段")
    year = ev.get("year", "")
    enrol = ev.get("enrol_wan")
    gap = ev.get("gap_wan")
    verdict = ev.get("verdict", "")
    parts = [f"{prov}{year} 年{stage}在校生 {enrol} 万人"]
    if isinstance(ev.get("change_pct"), (int, float)):
        parts.append(f"，较 2024 年 {ev['change_pct']:+.1f}%")
    parts.append("。")
    if isinstance(gap, (int, float)):
        parts.append(f"按标准编制测算，教师{'缺口' if gap > 0 else '富余'} {abs(gap):.1f} 万人，判定为「{verdict}」。")
    parts.append("（本段为规则模板生成，未调用大模型。）")
    return "".join(parts)


def _prompt(ev: dict) -> str:
    return (
        "你是学业支持助手。只依据给定的结构化证据，用不超过两句中文向辅导员说明风险与下一步。\n"
        "硬性要求：不得出现证据之外的任何数字；不得给出处分、劝退、贴标签类建议；语气客观。\n"
        f"证据：{json.dumps(ev, ensure_ascii=False)}"
    )


_NUM = re.compile(r"\d+(?:\.\d+)?")


def _guardrail(text: str, ev: dict) -> tuple[bool, str]:
    """输出中的数字必须与证据数值近似一致（容差匹配），否则判定违规。

    容差：绝对 0.02 或相对 1%，取大者。这样 "11.58%" 能对上 0.1158，
    而凭空出现的 "3 名学生" 会被拦下。
    """
    vals: list[float] = []
    for v in ev.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(abs(float(v)))
            vals.append(abs(float(v)) * 100.0)
    if not vals:
        return True, ""
    for m in _NUM.findall(text):
        x = float(m)
        if not any(abs(x - a) <= max(0.02, a * 0.01) for a in vals):
            return False, f"出现未授权数字：{m}"
    return True, ""


def _cache_key(ev: dict) -> str:
    return hashlib.sha256(json.dumps(ev, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


def generate(evidence: dict) -> dict:
    """返回 {source, text, model, latency_ms, retries, error?, guardrail?}。"""
    t0 = time.perf_counter()
    c = _cfg()
    base_res = {"model": c["model"] or "-", "provider": c["provider"]}

    if not enabled():
        return {**base_res, "source": "template", "text": _template(evidence),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "retries": 0}

    now = time.time()
    if _STATE["open_until"] > now:
        _STATE["fallbacks"] += 1
        return {**base_res, "source": "fallback", "text": _template(evidence),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "retries": 0,
                "error": f"circuit_open({round(_STATE['open_until'] - now)}s)"}

    key = _cache_key(evidence)
    if key in _CACHE:
        hit = dict(_CACHE[key])
        hit.update({"source": "cache", "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
        return hit

    payload = json.dumps({
        "model": c["model"],
        "messages": [{"role": "user", "content": _prompt(evidence)}],
        "temperature": 0.2,
        "max_tokens": 200,
    }).encode("utf-8")

    _STATE["calls"] += 1
    last_err, text = "", ""
    attempts = 0
    for attempt in range(c["retries"] + 1):
        attempts = attempt + 1
        req = urllib.request.Request(
            f'{c["base"]}/chat/completions', data=payload,
            headers={"Content-Type": "application/json", "Authorization": f'Bearer {c["key"]}'})
        try:
            with urllib.request.urlopen(req, timeout=c["timeout"]) as r:
                body = json.loads(r.read().decode("utf-8"))
            text = ((body.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "").strip()
            if not text:
                raise ValueError("empty completion")
            last_err = ""
            break
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in (401, 403):
                break                      # 鉴权错误不重试
            if e.code == 429:
                time.sleep(min(2.0, 0.4 * (attempt + 1)))
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}"
            time.sleep(min(1.0, 0.25 * (attempt + 1)))

    if not text:
        _STATE["fail"] += 1
        _STATE["fallbacks"] += 1
        _STATE["last_error"] = last_err or "unknown"
        if _STATE["fail"] >= BREAKER_THRESHOLD:
            _STATE["open_until"] = time.time() + BREAKER_COOLDOWN
        return {**base_res, "source": "fallback", "text": _template(evidence),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "retries": attempts - 1, "error": last_err}

    ok, why = _guardrail(text, evidence)
    if not ok:
        _STATE["fallbacks"] += 1
        _STATE["last_error"] = why
        return {**base_res, "source": "fallback", "text": _template(evidence),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "retries": attempts - 1, "guardrail": why}

    _STATE["fail"] = 0
    out = {**base_res, "source": "api", "text": text,
           "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
           "retries": attempts - 1}
    if len(_CACHE) >= CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)), None)
    _CACHE[key] = dict(out)
    return out
