"""Natural-language layer: turns a question into a structured query.

Design notes
------------
Works without an LLM (offline, deterministic, testable); rules cover common phrasings.
If a model is configured, it can be used as a fallback parser.

Output: {provinces, stage, year, scenario, intent, confidence, notes}
- provinces: possibly several (comparison)
- intent: gap / why / act / compare / shift
- confidence: high = province and keywords found; low = partial, caller should use defaults
"""
from __future__ import annotations

import re

PROVINCES = [
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西",
    "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
]
ALIAS = {"内蒙": "内蒙古", "黑": "黑龙江", "沪": "上海", "京": "北京", "津": "天津",
         "渝": "重庆", "粤": "广东", "豫": "河南", "鲁": "山东", "苏": "江苏",
         "浙": "浙江", "闽": "福建", "皖": "安徽", "赣": "江西", "湘": "湖南",
         "鄂": "湖北", "桂": "广西", "川": "四川", "蜀": "四川", "黔": "贵州",
         "滇": "云南", "陕": "陕西", "甘": "甘肃", "青": "青海", "宁": "宁夏", "新": "新疆"}

EN_PROVINCES = {
    "Beijing":"北京","Tianjin":"天津","Hebei":"河北","Shanxi":"山西","Inner Mongolia":"内蒙古",
    "Liaoning":"辽宁","Jilin":"吉林","Heilongjiang":"黑龙江","Shanghai":"上海","Jiangsu":"江苏",
    "Zhejiang":"浙江","Anhui":"安徽","Fujian":"福建","Jiangxi":"江西","Shandong":"山东","Henan":"河南",
    "Hubei":"湖北","Hunan":"湖南","Guangdong":"广东","Guangxi":"广西","Hainan":"海南","Chongqing":"重庆",
    "Sichuan":"四川","Guizhou":"贵州","Yunnan":"云南","Tibet":"西藏","Shaanxi":"陕西","Gansu":"甘肃",
    "Qinghai":"青海","Ningxia":"宁夏","Xinjiang":"新疆",
}
REGIONS = {
    "长三角": ["上海", "江苏", "浙江", "安徽"],
    "京津冀": ["北京", "天津", "河北"],
    "大湾区": ["广东"], "粤港澳": ["广东"],
    "东北": ["辽宁", "吉林", "黑龙江"],
    "中部": ["山西", "安徽", "江西", "河南", "湖北", "湖南"],
    "西部": ["内蒙古", "广西", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆"],
    "yangtze delta": ["上海", "江苏", "浙江", "安徽"],
    "jing-jin-ji": ["北京", "天津", "河北"],
    "greater bay area": ["广东"],
    "northeast china": ["辽宁", "吉林", "黑龙江"],
}
STAGE_WORDS = {"小学": "primary", "初中": "junior", "义务教育": "junior",
               "primary": "primary", "elementary": "primary", "junior": "junior",
               "middle school": "junior", "lower secondary": "junior"}
SCEN_WORDS = {"温和": "温和", "保守": "温和", "基准": "基准", "中性": "基准", "加速": "加速", "悲观": "加速",
              "mild": "温和", "slow": "温和", "baseline": "基准", "base": "基准",
              "accelerated": "加速", "fast": "加速", "rapid": "加速"}

INTENT_RULES = [
    ("compare", ["哪个", "谁更", "对比", "比较", "分别",
                 "compare", "versus", "vs", "which", "more", "less"]),
    ("act", ["怎么办", "怎么解决", "如何", "建议", "措施", "对策", "安置",
             "what should", "how to", "recommend", "measure", "policy"]),
    ("why", ["为什么", "原因", "怎么会", "来源", "导致",
             "why", "reason", "cause", "driven"]),
    ("shift", ["转岗", "需减", "多出来", "过剩", "超员",
               "redeploy", "surplus", "excess", "reduce"]),
    ("gap", ["够不够", "缺", "缺口", "紧缺", "够用",
             "enough", "shortage", "gap", "sufficient", "need"]),
]


def _find_provinces(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for p in PROVINCES:
        i = text.find(p)
        if i >= 0:
            found.append((i, p))
    if not found:
        for a, full in ALIAS.items():
            i = text.find(a)
            if i >= 0:
                found.append((i, full))
    if not found:
        low = text.lower()
        for key, members in REGIONS.items():
            if (key in text) or (key.isascii() and key in low):
                base = text.find(key) if key in text else low.find(key)
                if base < 0:
                    base = 0
                found.extend((base + i / 100.0, m) for i, m in enumerate(members))
        for en, cn in EN_PROVINCES.items():
            i = low.find(en.lower())
            if i >= 0:
                found.append((i, cn))
    hits = [name for _, name in sorted(found)]
    # de-duplicate, keep order
    out: list[str] = []
    for h in hits:
        if h not in out:
            out.append(h)
    return out


def _find_year(text: str) -> int | None:
    m = re.search(r"(20[2-3]\d)\s*年?", text)
    if m:
        y = int(m.group(1))
        if 2024 <= y <= 2033:
            return y
        return None
    if "今年" in text:
        return 2025
    if "现在" in text or "当前" in text:
        return 2024
    return None


def parse(text: str, default: dict | None = None) -> dict:
    """Parse a question; unresolved fields fall back to defaults."""
    d = default or {}
    t = (text or "").strip()
    tl = t.lower()
    provs = _find_provinces(t)
    stage = next((v for k, v in STAGE_WORDS.items() if (k in t) or (k.isascii() and k in tl)), None)
    scen = next((v for k, v in SCEN_WORDS.items() if (k in t) or (k.isascii() and k in tl)), None)
    year = _find_year(t)
    intent = "gap"
    for name, kws in INTENT_RULES:
        if any((k in t) or (k.isascii() and k in tl) for k in kws):
            intent = name
            break

    notes = []
    if not provs:
        notes.append("No province detected — using the sidebar selection")
    if len(provs) > 1:
        intent = "compare"
    if not year:
        notes.append("No year detected — using the sidebar selection")

    conf = "high" if provs and (stage or year) else ("mid" if provs else "low")
    return {
        "provinces": provs or ([d["province"]] if d.get("province") else []),
        "stage": stage or d.get("stage", "junior"),
        "year": year or int(d.get("year", 2030)),
        "scenario": scen or d.get("scenario", "基准"),
        "intent": intent,
        "confidence": conf,
        "notes": notes,
        "parsed_from": "rule",
    }


_EN = {v: k for k, v in EN_PROVINCES.items()}

def describe(p: dict) -> str:
    stage_en = "Primary" if p["stage"] == "primary" else "Junior secondary"
    who = ", ".join(_EN.get(x, x) for x in p["provinces"]) if p["provinces"] else "not specified"
    it = {"gap": "shortage", "why": "causes", "act": "measures",
          "compare": "comparison", "shift": "redeployment"}[p["intent"]]
    scen = {"温和": "mild", "基准": "baseline", "加速": "accelerated"}[p["scenario"]]
    return f"{who} · {stage_en} · {p['year']} · {scen} scenario · intent: {it}"


if __name__ == "__main__":
    for q in ["广东2030初中教师够不够", "广东和河南哪个小学富余更多",
              "河南小学老师多了怎么办", "为什么山东初中缺教师", "浙江2028年小学要转岗多少"]:
        print(q, "→", describe(parse(q)))
