"""Regional education data loader: resolves columns by label instead of position.

Source: China Ministry of Education, 2024 provincial tables (31 provinces), stored in raw/tables/*.csv.
Column names are given in raw/manifest.json (bilingual labels); this loader matches them by keyword.
"""
from __future__ import annotations

import csv
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
TABLES = RAW / "tables"
MANIFEST = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))

PROVINCES = [
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西",
    "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
]

# keyword -> semantic key (order matters: specific first)
RULES: list[tuple[str, str]] = [
    ("合计 Total", "total"),
    ("预计毕业生数", "expected_graduates"),
    ("毕业生数", "graduates"),
    ("招生数", "entrants"),
    ("在校生数", "enrolment"),
    ("预计毕业生数", "expected_graduates"),
    ("一年级", "g1"), ("二年级", "g2"), ("三年级", "g3"), ("四年级", "g4"),
    ("五年级", "g5"), ("六年级", "g6"),
    ("专任教师", "teachers"),
    ("班数", "classes"),
    ("教职工数", "staff"),
    ("校舍", "floor_area"),
    ("资产", "assets"),
    ("在园", "enrolment"),
    ("入园", "entrants"),
    ("离园", "leavers"),
    ("园数", "schools"),
]


def _table_meta(title_kw: str) -> dict:
    for t in MANIFEST["tables"]:
        if title_kw in t["title"]:
            return t
    raise KeyError(title_kw)


def load(title_kw: str) -> tuple[dict[str, dict], dict[str, str]]:
    """Returns (province -> {key: value}, column -> key)."""
    meta = _table_meta(title_kw)
    path = TABLES / meta["file"]
    labels: list[str] = meta["labels"]

    # Column 0 is the region; remaining columns map to keys by label
    col_key: dict[str, str] = {}
    for i, lab in enumerate(labels):
        if i == 0:
            continue
        for kw, key in RULES:
            if kw in lab:
                col_key[f"c{i}"] = key
                break

    out: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            prov = (row.get("地区") or "").strip()
            if prov not in PROVINCES:
                continue
            rec: dict[str, float] = {}
            for col, key in col_key.items():
                raw = (row.get(col) or "").replace(",", "").strip()
                if raw in ("", "-", "—"):
                    continue
                try:
                    rec[key] = float(raw)
                except ValueError:
                    continue
            out[prov] = rec
    return out, col_key


def national_total(stage: str, key: str) -> float:
    data, _ = load(stage)
    return sum(r.get(key, 0.0) for r in data.values())


def diagnostics() -> dict:
    """Self-check: grade totals equal enrolment and match the national bulletin."""
    rep: dict = {}
    for stage in ("小学教育学生数", "初中教育学生数"):
        data, mapping = load(stage)
        tot_enrol = sum(r.get("enrolment", 0) for r in data.values())
        grade_sum = sum(sum(r.get(f"g{i}", 0) for i in range(1, 7)) for r in data.values())
        rep[stage] = {
            "provinces": len(data),
            "enrolment_sum": int(tot_enrol),
            "grades_sum": int(grade_sum),
            "grade_vs_enrol_diff_pct": round((grade_sum - tot_enrol) / max(1, tot_enrol) * 100, 3),
            "columns": {k: v for k, v in mapping.items() if k in ("c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9")},
        }
    pre, _ = load("学前教育基本情况")
    rep["学前教育"] = {"provinces": len(pre),
                    "enrolment_sum": int(sum(r.get("enrolment", 0) for r in pre.values())),
                    "leavers_sum": int(sum(r.get("leavers", 0) for r in pre.values())),
                    "entrants_sum": int(sum(r.get("entrants", 0) for r in pre.values()))}
    return rep


if __name__ == "__main__":
    print(json.dumps(diagnostics(), ensure_ascii=False, indent=2))
