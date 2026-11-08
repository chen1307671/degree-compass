"""学位缺口推演：领域核心（纯计算，无 I/O 网络）。

输入来自 reports/projection.json（由 src/project.py 生成）。
对外只暴露一个入口：Planner.run(province, stage, year, scenario, question)。

判定规则（三级）
- 紧缺：教师需求（标准编制口径）超出现有教师 2% 以上
- 平衡：在 −5% ~ +2% 之间
- 富余：低于 −5%，即按标准编制明显超员，需转岗或小班化
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
    "广东省 2030 年初中教师够不够？缺口主要来自哪里？",
    "河南小学教师富余多少？该怎么安置？",
    "按基准情景，全国小学在校生到 2030 年减少多少？",
]


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
        # 情景汇总只含 2030 分省；分年明细需从 project 重算，故此处用缓存文件
        return s["summary"]["provinces_2030"].__class__ and None  # 占位

    def national(self, year: int, scen: str) -> dict:
        return self.scen[scen]["summary"]["national"][str(year)]

    def province_year(self, prov: str, year: int, scen: str) -> dict:
        """分省分年指标：来自 projection_by_province.json（若存在），否则按比例近似。"""
        p = HERE / "reports" / "by_province.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data[scen][str(year)][prov]
        raise FileNotFoundError("reports/by_province.json 缺失，请先运行 scripts/export_by_province.py")


class Planner:
    def __init__(self, data: RegionData) -> None:
        self.d = data

    # ---------- 判定 ----------
    @staticmethod
    def verdict(gap_ratio: float) -> tuple[str, str]:
        if gap_ratio > 0.02:
            return "紧缺", "需要补充教师或扩大班额"
        if gap_ratio < -0.05:
            return "富余", "按标准编制超员，需转岗或小班化"
        return "平衡", "总量基本匹配，关注学科与城乡结构"

    # ---------- 主流程 ----------
    def run(self, province: str, stage: str = "junior", year: int = 2030,
            scenario: str = "基准", question: str = "") -> dict:
        t0 = time.perf_counter()
        prov = province if province in self.d.provinces else self.d.provinces[0]
        stage = stage if stage in STAGES else "junior"
        year = year if year in YEARS else 2030
        scenario = scenario if scenario in SCENARIOS else "基准"

        cur = self.d.province_year(prov, year, scenario)
        base = self.d.base[prov]
        nat = self.d.national(year, scenario)

        k = "p" if stage == "primary" else "j"
        enrol = cur[f"enrol_{k}"]
        enrol24 = base[f"enrol_{k}"]
        teachers = base[f"teachers_{k}"]
        gap = cur[f"gap_{k}_std"]
        shift = cur[f"shift_{k}"]
        need_std = cur[f"need_{k}_std"]
        ratio_now = round(enrol / teachers, 2) if teachers else None
        gap_ratio = gap / teachers if teachers else 0.0
        verdict, verdict_note = self.verdict(gap_ratio)

        # 全国对标
        nat_enrol = nat[f"enrol_{k}"]
        nat_gap = nat[f"gap_{k}_std"]
        share = (enrol / 1e4) / nat_enrol if nat_enrol else 0.0   # 分子换成万人，与 nat_enrol 同单位
        change = (enrol - enrol24) / enrol24 if enrol24 else 0.0

        # 分年级结构（2024）
        grades = base.get(f"grades_{k}", [])
        structure = [{"grade": f"{STAGES[stage]}{i + 1}年级", "students": round(g, 1)}
                     for i, g in enumerate(grades) if g]

        actions = self._actions(verdict, stage, prov)

        trace = [
            {"step": 1, "action": "定位", "action_source": "规则解析",
             "observation": f"{prov} · {STAGES[stage]} · {year} 年 · {scenario} 情景"},
            {"step": 2, "action": "推演", "action_source": "队列递推模型",
             "observation": f"在校生 {enrol / 1e4:.1f} 万（较 2024 年 {change:+.1%}）"},
            {"step": 3, "action": "测算", "action_source": "标准编制口径（{:.1f}:1）".format(
                19.0 if stage == "primary" else 13.5),
             "observation": f"教师需求 {need_std / 1e4:.1f} 万，现有 {teachers / 1e4:.1f} 万，"
                            f"{'缺口' if gap > 0 else '富余'} {abs(gap) / 1e4:.1f} 万"},
            {"step": 4, "action": "对标", "action_source": "全国同口径",
             "observation": f"全国同阶段{'缺口' if nat_gap > 0 else '富余'} {abs(nat_gap):.1f} 万，"
                            f"本省占全国在校生 {share:.1%}"},
            {"step": 5, "action": "建议", "action_source": "措施库检索",
             "observation": f"判定为「{verdict}」：{verdict_note}"},
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
                "verdict": verdict, "verdict_note": verdict_note,
                "national_gap_wan": round(nat_gap, 1), "share_national": round(share, 4),
            },
            "structure": structure,
            "actions": actions,
            "trace": trace,
            "evidence": evidence,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    # ---------- 措施库 ----------
    def _actions(self, verdict: str, stage: str, prov: str) -> list[dict]:
        from kb import retrieve
        return retrieve(verdict, stage, top_k=4)
