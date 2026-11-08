"""自然语言理解层：把一句中文问题解析成结构化查询。

设计取舍
--------
不依赖大模型也能跑（离线、确定性、可测试），规则覆盖常见问法；
若配置了大模型，可用其兜底解析（见 parse_with_llm）。

产出：{provinces, stage, year, scenario, intent, confidence, notes}
- provinces：可能多个（对比场景）
- intent：gap（够不够）/ why（为什么）/ act（怎么办）/ compare（谁更…）/ shift（转岗多少）
- confidence：高=命中省份+关键词；低=只命中部分，需要前端取默认值
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

STAGE_WORDS = {"小学": "primary", "初中": "junior", "义务教育": "junior"}
SCEN_WORDS = {"温和": "温和", "保守": "温和", "基准": "基准", "中性": "基准", "加速": "加速", "悲观": "加速"}

INTENT_RULES = [
    ("compare", ["哪个", "谁更", "对比", "比较", "分别"]),
    ("act", ["怎么办", "怎么解决", "如何", "建议", "措施", "对策", "安置"]),
    ("why", ["为什么", "原因", "怎么会", "来源", "导致"]),
    ("shift", ["转岗", "需减", "多出来", "过剩", "超员"]),
    ("gap", ["够不够", "缺", "缺口", "紧缺", "够用"]),
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
    hits = [name for _, name in sorted(found)]
    # 去重保序
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
    """解析问题；未识别的字段用 default 兜底。"""
    d = default or {}
    t = (text or "").strip()
    provs = _find_provinces(t)
    stage = next((v for k, v in STAGE_WORDS.items() if k in t), None)
    scen = next((v for k, v in SCEN_WORDS.items() if k in t), None)
    year = _find_year(t)
    intent = "gap"
    for name, kws in INTENT_RULES:
        if any(k in t for k in kws):
            intent = name
            break

    notes = []
    if not provs:
        notes.append("未识别到省份，已沿用左侧所选")
    if len(provs) > 1:
        intent = "compare"
    if not year:
        notes.append("未识别到年份，已沿用左侧所选")

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


def describe(p: dict) -> str:
    stage_cn = "小学" if p["stage"] == "primary" else "初中"
    who = "、".join(p["provinces"]) if p["provinces"] else "未指定"
    it = {"gap": "缺口", "why": "归因", "act": "措施", "compare": "对比", "shift": "转岗"}[p["intent"]]
    return f"{who} · {stage_cn} · {p['year']} · {p['scenario']}情景 · 意图：{it}"


if __name__ == "__main__":
    for q in ["广东2030初中教师够不够", "广东和河南哪个小学富余更多",
              "河南小学老师多了怎么办", "为什么山东初中缺教师", "浙江2028年小学要转岗多少"]:
        print(q, "→", describe(parse(q)))
