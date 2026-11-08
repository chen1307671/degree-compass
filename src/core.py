"""Domain core for the degree-gap simulator (pure computation, no network I/O).

Input comes from reports/projection.json (produced by src/project.py).
Only one entry point is exposed: Planner.run(province, stage, year, scenario, question).

Verdict rules (three levels):
- Shortage: teacher demand (standard staffing convention) exceeds current teachers by 2% or more
- Balanced: between -5% and +2%
- Surplus: below -5%, i.e. clearly over-staffed against the standard
"""
from __future__ import annotations

import json
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parents[1]
REPORT = HERE / "reports" / "projection.json"

YEARS = list(range(2024, 2031))
SCENARIOS = ["温和", "基准", "加速"]
STAGES = {"primary": "小学", "junior": "初中"}

PROMPTS = [
    "Is Guangdong short of junior-secondary teachers in 2030?",
    "Compare Guangdong and Henan on primary-teacher surplus.",
    "What should Henan do about its large primary-teacher surplus?",
]

VERDICT_EN = {"紧缺": "Shortage", "平衡": "Balanced", "富余": "Surplus"}
PROV_EN = {"北京":"Beijing","天津":"Tianjin","河北":"Hebei","山西":"Shanxi","内蒙古":"Inner Mongolia",
 "辽宁":"Liaoning","吉林":"Jilin","黑龙江":"Heilongjiang","上海":"Shanghai","江苏":"Jiangsu",
 "浙江":"Zhejiang","安徽":"Anhui","福建":"Fujian","江西":"Jiangxi","山东":"Shandong","河南":"Henan",
 "湖北":"Hubei","湖南":"Hunan","广东":"Guangdong","广西":"Guangxi","海南":"Hainan","重庆":"Chongqing",
 "四川":"Sichuan","贵州":"Guizhou","云南":"Yunnan","西藏":"Tibet","陕西":"Shaanxi","甘肃":"Gansu",
 "青海":"Qinghai","宁夏":"Ningxia","新疆":"Xinjiang"}

def en(name: str) -> str:
    return PROV_EN.get(name, name)
STAGE_EN = {"primary": "primary", "junior": "junior secondary"}


class RegionData:
    def __init__(self) -> None:
        d = json.loads(REPORT.read_text(encoding="utf-8"))
        self.raw = d
        self.provinces = [p for p in d["baseline_2024"]]
        self.base = d["baseline_2024"]
        self.scen = d["scenarios"]

    def cell(self, prov: str, year: int, scen: str) -> dict | None:
        s = self.scen.get(scen)
        if not s:
            return None
        # Scenario summary holds 2030 by province; yearly detail is read from the cached file
        return s["summary"]["provinces_2030"].__class__ and None  # 占位

    def series(self, prov: str, stage: str, scen: str) -> dict:
        """Yearly series for one province and stage (enrolment and gap) for the frontend charts."""
        p = HERE / "reports" / "by_province.json"
        data = json.loads(p.read_text(encoding="utf-8"))[scen]
        years = sorted(int(y) for y in data)
        k = "p" if stage == "primary" else "j"
        return {"years": years,
                "enrol": [round(data[str(y)][prov][f"enrol_{k}"] / 1e4, 1) for y in years],
                "gap": [round(data[str(y)][prov][f"gap_{k}_std"] / 1e4, 1) for y in years]}

    def national(self, year: int, scen: str) -> dict:
        return self.scen[scen]["summary"]["national"][str(year)]

    def province_year(self, prov: str, year: int, scen: str) -> dict:
        """Per-province yearly metrics, read from reports/by_province.json."""
        p = HERE / "reports" / "by_province.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data[scen][str(year)][prov]
        raise FileNotFoundError("reports/by_province.json 缺失，请先运行 scripts/export_by_province.py")


class Planner:
    def __init__(self, data: RegionData) -> None:
        self.d = data

    # ---------- verdict ----------
    @staticmethod
    def verdict(gap_ratio: float) -> tuple[str, str]:
        if gap_ratio > 0.02:
            return "紧缺", "Add teachers or expand class capacity"
        if gap_ratio < -0.05:
            return "富余", "Above standard staffing; redeploy or shrink class size"
        return "平衡", "Broadly matched; watch subject and urban-rural structure"

    # ---------- main pipeline ----------
    def run(self, province: str, stage: str = "junior", year: int = 2030,
            scenario: str = "基准", question: str = "", migration: float = 0.0) -> dict:
        t0 = time.perf_counter()
        prov = province if province in self.d.provinces else self.d.provinces[0]
        stage = stage if stage in STAGES else "junior"
        year = year if year in YEARS else 2030
        scenario = scenario if scenario in SCENARIOS else "基准"

        cur = self.d.province_year(prov, year, scenario)
        base = self.d.base[prov]
        nat = self.d.national(year, scenario)

        k = "p" if stage == "primary" else "j"
        enrol = cur[f"enrol_{k}"] * (1 + migration)
        enrol24 = base[f"enrol_{k}"]
        teachers = base[f"teachers_{k}"]
        need_std = enrol / (19.0 if stage == "primary" else 13.5)
        gap = need_std - teachers
        shift = enrol / (base[f"ratio_{k}"] or 1.0) - teachers
        need_std = cur[f"need_{k}_std"]
        ratio_now = round(enrol / teachers, 2) if teachers else None
        gap_ratio = gap / teachers if teachers else 0.0
        verdict, verdict_note = self.verdict(gap_ratio)

        # national benchmark
        nat_enrol = nat[f"enrol_{k}"]
        nat_gap = nat[f"gap_{k}_std"]
        share = (enrol / 1e4) / nat_enrol if nat_enrol else 0.0   # 分子换成万人，与 nat_enrol 同单位
        change = (enrol - enrol24) / enrol24 if enrol24 else 0.0

        # grade structure (2024)
        grades = base.get(f"grades_{k}", [])
        structure = [{"grade": f"{STAGES[stage]}{i + 1}年级", "students": round(g, 1)}
                     for i, g in enumerate(grades) if g]

        actions = self._actions(verdict, stage, prov)

        trace = [
            {"step": 1, "action": "Parse", "action_source": "rule-based NLU",
             "observation": f"{en(prov)} · {STAGE_EN[stage]} · {year} · {scenario}"},
            {"step": 2, "action": "Project", "action_source": "cohort progression",
             "observation": f"{enrol / 1e4:,.1f} 万 students ({change:+.1%} vs 2024)"},
            {"step": 3, "action": "Compute", "action_source": "standard staffing ratio ({:.1f}:1)".format(
                19.0 if stage == "primary" else 13.5),
             "observation": f"need {need_std / 1e4:,.1f} 万 teachers, have {teachers / 1e4:,.1f} 万, "
                            f"{'shortage' if gap > 0 else 'surplus'} {abs(gap) / 1e4:,.1f} 万"},
            {"step": 4, "action": "Benchmark", "action_source": "national, same stage",
             "observation": f"national {'shortage' if nat_gap > 0 else 'surplus'} {abs(nat_gap):,.1f} 万; "
                            f"this province is {share:.1%} of national enrolment"},
            {"step": 5, "action": "Recommend", "action_source": "measure library",
             "observation": f"verdict: {VERDICT_EN.get(verdict, verdict)}"},
        ]

        evidence = {
            "province": prov, "stage": STAGES[stage], "year": year,
            "enrol_wan": round(enrol / 1e4, 1), "change_pct": round(change * 100, 1),
            "teachers_wan": round(teachers / 1e4, 1), "ratio": ratio_now,
            "gap_wan": round(gap / 1e4, 1), "shift_wan": round(shift / 1e4, 1),
            "verdict": verdict,
        }

        return {
            "query": {"province": prov, "stage": stage, "year": year,
                      "scenario": scenario, "question": question},
            "summary": {
                "enrol_wan": round(enrol / 1e4, 1), "enrol_2024_wan": round(enrol24 / 1e4, 1),
                "change_pct": round(change * 100, 1), "teachers_wan": round(teachers / 1e4, 1),
                "need_std_wan": round(need_std / 1e4, 1), "gap_wan": round(gap / 1e4, 1),
                "shift_wan": round(shift / 1e4, 1), "ratio": ratio_now,
                "verdict": verdict, "verdict_en": VERDICT_EN.get(verdict, verdict),
                "province_en": en(province), "stage_en": STAGE_EN.get(stage, stage),
                "verdict_note": verdict_note,
                "national_gap_wan": round(nat_gap, 1), "share_national": round(share, 4),
            },
            "structure": structure,
            "actions": actions,
            "trace": trace,
            "evidence": evidence,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    # ---------- conversational entry ----------
    def answer(self, question: str, defaults: dict) -> dict:
        """Parse a natural-language question, then dispatch (gap / causes / measures / redeployment / comparison)."""
        import nlu
        p = nlu.parse(question, defaults)
        stage_cn = "小学" if p["stage"] == "primary" else "初中"

        # multi-province comparison
        if p["intent"] == "compare" and len(p["provinces"]) > 1:
            rows = []
            for prov in p["provinces"][:6]:
                r = self.run(prov, p["stage"], p["year"], p["scenario"], question)
                s = r["summary"]
                rows.append({"province": prov, "enrol_wan": s["enrol_wan"],
                             "gap_wan": s["gap_wan"], "verdict": s["verdict"],
                             "shift_wan": s["shift_wan"], "ratio": s["ratio"]})
            worst = max(rows, key=lambda x: x["gap_wan"])
            best = min(rows, key=lambda x: x["gap_wan"])
            names = ", ".join(en(r["province"]) for r in rows)
            if worst["gap_wan"] > 0:
                text = (f"In {p['year']}, among {names}: {en(worst['province'])} has the largest shortage "
                    f"({worst['gap_wan']} 万), {en(best['province'])} the smallest ({best['gap_wan']} 万).")
            else:
                text = (f"In {p['year']}, all are in surplus: {en(best['province'])} has the largest surplus "
                        f"({abs(best['gap_wan'])} 万) and {en(worst['province'])} the smallest "
                        f"({abs(worst['gap_wan'])} 万).")
            return {"answer_type": "compare", "parsed": p, "parsed_text": nlu.describe(p),
                    "rows": rows, "answer_text": text, "query": p,
                    "summary": rows[0], "actions": [], "trace": [
                        {"step": 1, "action": "解析问句", "action_source": "规则 NLU",
                         "observation": nlu.describe(p)},
                        {"step": 2, "action": "逐省推演", "action_source": "队列递推",
                         "observation": "；".join(f"{r['province']} {r['enrol_wan']} 万" for r in rows)},
                        {"step": 3, "action": "对比排序", "action_source": "缺口绝对值",
                         "observation": text},
                    ], "evidence": {"provinces": [r["province"] for r in rows],
                                   "stage": stage_cn, "year": p["year"]}}

        base = self.run(p["provinces"][0] if p["provinces"] else "",
                        p["stage"], p["year"], p["scenario"], question,
                        migration=float(defaults.get("migration", 0.0) or 0.0))
        s = base["summary"]
        gap = s["gap_wan"]
        word = "缺口" if gap > 0 else "富余"
        st = STAGE_EN[p["stage"]]
        text = (f"{en(p['provinces'][0]) if p['provinces'] else 'The province'} has {s['enrol_wan']} 万 "
                f"{st} students in {p['year']}; against the standard staffing ratio it faces a "
                f"{abs(gap)} 万 {'shortage' if gap > 0 else 'surplus'} ({VERDICT_EN.get(s['verdict'], s['verdict'])}).")

        if p["intent"] == "why":
            reasons = [
                f"Enrolment is {s['change_pct']:+.1f}% vs 2024, shifting teacher demand by roughly "
                f"{round(s['enrol_wan'] / (19 if p['stage']=='primary' else 13.5), 1)} 万;",
                f"There are {s['teachers_wan']} 万 teachers now; the gap to the "
                f"{'19:1' if p['stage']=='primary' else '13.5:1'} standard drives the size of the "
                f"{'shortage' if gap > 0 else 'surplus'};",
                f"Nationally the same stage shows a {'shortage' if s['national_gap_wan']>0 else 'surplus'} "
                f"of {abs(s['national_gap_wan'])} 万; this province is "
                f"{round(s['share_national']*100,1)}% of national enrolment.",
            ]
            base["reasons"] = reasons
            text += " Three drivers are listed below."
        elif p["intent"] == "shift":
            text = (f"At the current ratio, {en(p['provinces'][0]) if p['provinces'] else 'the province'} needs "
                    f"{'more' if s['shift_wan'] >= 0 else 'fewer'} {abs(s['shift_wan'])} 万 "
                    f"{st} teachers in {p['year']}.")

        try:
            base["series"] = self.d.series(p["provinces"][0] if p["provinces"] else "",
                                           p["stage"], p["scenario"])
        except Exception:
            base["series"] = None
        base["parsed"] = p
        base["parsed_text"] = nlu.describe(p)
        base["answer_type"] = p["intent"]
        base["answer_text"] = text
        return base

    # ---------- measure library ----------
    def _actions(self, verdict: str, stage: str, prov: str) -> list[dict]:
        from kb import retrieve
        return retrieve(verdict, stage, top_k=4)
