"""分省分学段学龄人口推演与师资缺口测算（2024 基线 → 2030）。

方法：队列递推（cohort progression）
- 小学：一年级由全国招生路径驱动（2025 用公报值，之后按情景增速），二至六年级由
  上一年的低一年级按存活率递推；存活率取 0.995（转学/休学净影响，口径写死可改）。
- 初中：一年级 = 当年小学毕业生 × 分省升学率（2024 观测），二、三年级按 0.995 递推。
- 教师需求两种口径：
  A. 标准口径：在校生 ÷ 国家基本生师比（小学 19:1、初中 13.5:1）→ 与现有教师比，得缺口/富余
  B. 现状口径：保持 2024 实际生师比 → 需求随学龄人口同步变化，得"需转岗/需补充"人数

外部锚点（教育部 2025 年公报）：
  小学招生 1461.74 万、在校生 10178.29 万；初中招生 1852.81 万、在校生 5509.34 万。
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import regdata as rd

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"

SURVIVE = 0.995                 # 年级递推存活率
RATIO_STD = {"primary": 19.0, "junior": 13.5}   # 国家基本编制标准生师比
ANCHOR = {"primary_entrants_2025": 14_617_400, "primary_enrol_2025": 101_782_900,
          "junior_entrants_2025": 18_528_100, "junior_enrol_2025": 55_093_400}
SCENARIOS = {"基准": -0.06, "温和": -0.03, "加速": -0.09}   # 2026 起小学招生年变化
JUNIOR_CALIB = 0.9808   # 初中招生总量校准：使 2025 年全国预测精确对齐公报 5,509.3 万


def load_all() -> dict:
    pri, _ = rd.load("小学教育学生数")
    jun, _ = rd.load("初中教育学生数")
    pre, _ = rd.load("学前教育基本情况")
    t_pri, _ = rd.load("小学教育专任教师分学历")
    t_jun, _ = rd.load("初中教育专任教师分学历")
    return {"primary": pri, "junior": jun, "pre": pre,
            "t_primary": {k: v.get("total", 0) for k, v in t_pri.items()},
            "t_junior": {k: v.get("total", 0) for k, v in t_jun.items()}}


def baseline(d: dict) -> dict:
    """2024 基线：分省在校生、教师、生师比、招生份额、升学率。"""
    pri, jun = d["primary"], d["junior"]
    nat_pri_ent = sum(r.get("entrants", 0) for r in pri.values())
    out = {}
    for p in rd.PROVINCES:
        gp = pri.get(p, {})
        gj = jun.get(p, {})
        grades = [gp.get(f"g{i}", 0.0) for i in range(1, 7)]
        # 初中存在五四学制（4 个年级），按实际数据判定，避免按三年制硬推
        jgrades = [gj.get(f"g{i}", 0.0) for i in range(1, 5)]
        n_jun = 4 if jgrades[3] > 0.02 * max(1.0, sum(jgrades)) else 3
        enrol_p = gp.get("enrolment", sum(grades))
        enrol_j = gj.get("enrolment", sum(jgrades))
        tp = d["t_primary"].get(p, 0.0)
        tj = d["t_junior"].get(p, 0.0)
        out[p] = {
            "grades_p": grades, "grades_j": jgrades, "n_jun": n_jun,
            "enrol_p": enrol_p, "enrol_j": enrol_j,
            "teachers_p": tp, "teachers_j": tj,
            "ratio_p": round(enrol_p / tp, 3) if tp else None,
            "ratio_j": round(enrol_j / tj, 3) if tj else None,
            "entry_share": gp.get("entrants", 0) / nat_pri_ent if nat_pri_ent else 0.0,
            "grad_p": gp.get("graduates", 0.0),
            "junior_intake_rate": (gj.get("entrants", 0) / gp.get("graduates", 1.0)
                                   if gp.get("graduates") else None),
            "pre_leavers": d["pre"].get(p, {}).get("leavers", 0.0),
        }
    return out


def project(base: dict, delta: float, years=range(2025, 2031)) -> dict:
    """按情景递推，返回 {year: {province: {...}}}。"""
    nat_entry = {2024: sum(b["enrol_p"] for b in base.values()) * 0}  # 占位
    # 2024 全国招生 = 各省 entry_share × 全国招生，反推全国招生
    shares = {p: b["entry_share"] for p, b in base.items()}
    total_share = sum(shares.values()) or 1.0
    nat_2024 = ANCHOR["primary_entrants_2025"] / (1 + delta)   # 由 2025 锚点与增速反推 2024
    nat_entry = {2024: nat_2024, 2025: ANCHOR["primary_entrants_2025"]}
    for y in range(2026, (max(years) if years else 2030) + 1):
        nat_entry[y] = nat_entry[y - 1] * (1 + delta)

    res = {}
    # 2024 基线
    res[2024] = {p: {"enrol_p": b["enrol_p"], "enrol_j": b["enrol_j"],
                     "grades_p": b["grades_p"], "grades_j": b["grades_j"]}
                 for p, b in base.items()}

    prev = {p: {"grades_p": list(b["grades_p"]), "grades_j": list(b["grades_j"])}
            for p, b in base.items()}

    for y in years:
        cur = {}
        for p, b in base.items():
            gp = prev[p]["grades_p"]
            gj = prev[p]["grades_j"]
            # 小学：新生来自全国招生 × 省份额；高年级由低年级递推
            g1 = nat_entry[y] * (shares[p] / total_share if total_share else 0)
            new_gp = [g1] + [gp[i] * SURVIVE for i in range(5)]
            # 初中：初一 = 小学毕业生 × 升学率；初二初三递推
            grad_p = gp[5] * SURVIVE
            rate = (b["junior_intake_rate"] or 1.0) * JUNIOR_CALIB
            j1 = grad_p * rate
            if b.get("n_jun", 3) == 4:
                new_gj = [j1, gj[0] * SURVIVE, gj[1] * SURVIVE, gj[2] * SURVIVE]
            else:
                new_gj = [j1, gj[0] * SURVIVE, gj[1] * SURVIVE, 0.0]
            cur[p] = {"enrol_p": sum(new_gp), "enrol_j": sum(new_gj),
                      "grades_p": new_gp, "grades_j": new_gj}
        res[y] = cur
        prev = {p: {"grades_p": cur[p]["grades_p"], "grades_j": cur[p]["grades_j"]} for p in base}
    return res


def gaps(base: dict, proj: dict) -> dict:
    """两种口径的师资缺口/富余。"""
    out = {}
    for y, rows in proj.items():
        per = {}
        for p, r in rows.items():
            tp = base[p]["teachers_p"]
            tj = base[p]["teachers_j"]
            need_p_std = r["enrol_p"] / RATIO_STD["primary"]
            need_j_std = r["enrol_j"] / RATIO_STD["junior"]
            ratio_p = base[p]["ratio_p"] or RATIO_STD["primary"]
            ratio_j = base[p]["ratio_j"] or RATIO_STD["junior"]
            need_p_cur = r["enrol_p"] / ratio_p if ratio_p else 0
            need_j_cur = r["enrol_j"] / ratio_j if ratio_j else 0
            per[p] = {
                "need_p_std": need_p_std, "gap_p_std": need_p_std - tp,
                "need_j_std": need_j_std, "gap_j_std": need_j_std - tj,
                "need_p_cur": need_p_cur, "shift_p": need_p_cur - tp,
                "need_j_cur": need_j_cur, "shift_j": need_j_cur - tj,
            }
        out[y] = per
    return out


def summarize(base: dict, proj: dict, gap: dict) -> dict:
    def nat(y, key):
        return sum(v[key] for v in proj[y].values())

    def nat_gap(y, key):
        return sum(v[key] for v in gap[y].values())

    years = sorted(proj)
    return {
        "national": {
            str(y): {
                "enrol_p": round(nat(y, "enrol_p") / 1e4, 1),
                "enrol_j": round(nat(y, "enrol_j") / 1e4, 1),
                "teachers_p": round(sum(b["teachers_p"] for b in base.values()) / 1e4, 1),
                "teachers_j": round(sum(b["teachers_j"] for b in base.values()) / 1e4, 1),
                "gap_p_std": round(nat_gap(y, "gap_p_std") / 1e4, 1),
                "gap_j_std": round(nat_gap(y, "gap_j_std") / 1e4, 1),
                "shift_p": round(nat_gap(y, "shift_p") / 1e4, 1),
                "shift_j": round(nat_gap(y, "shift_j") / 1e4, 1),
            } for y in years
        },
        "provinces_2030": sorted(
            [{"province": p,
              "enrol_p_wan": round(proj[2030][p]["enrol_p"] / 1e4, 1),
              "enrol_j_wan": round(proj[2030][p]["enrol_j"] / 1e4, 1),
              "gap_p_std": round(gap[2030][p]["gap_p_std"] / 1e4, 1),
              "gap_j_std": round(gap[2030][p]["gap_j_std"] / 1e4, 1),
              "shift_p": round(gap[2030][p]["shift_p"] / 1e4, 1)} for p in base],
            key=lambda z: z["gap_j_std"], reverse=True),
    }


def main() -> int:
    d = load_all()
    base = baseline(d)
    out = {"anchor": ANCHOR, "assumptions": {"survive": SURVIVE, "ratio_std": RATIO_STD},
           "baseline_2024": {p: {k: (round(v, 2) if isinstance(v, float) else v)
                                 for k, v in b.items() if k not in ("grades_p", "grades_j")}
                             for p, b in base.items()},
           "scenarios": {}}
    for name, delta in SCENARIOS.items():
        proj = project(base, delta)
        gap = gaps(base, proj)
        out["scenarios"][name] = {"delta": delta, "summary": summarize(base, proj, gap)}

    REP.mkdir(exist_ok=True)
    (REP / "projection.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 分省分年明细（供智能体逐格查询）
    by_prov: dict = {}
    for name, delta in SCENARIOS.items():
        proj = project(base, delta)
        gap = gaps(base, proj)
        by_prov[name] = {
            str(y): {
                p: {
                    "enrol_p": round(proj[y][p]["enrol_p"], 1),
                    "enrol_j": round(proj[y][p]["enrol_j"], 1),
                    "need_p_std": round(gap[y][p]["need_p_std"], 1),
                    "gap_p_std": round(gap[y][p]["gap_p_std"], 1),
                    "need_j_std": round(gap[y][p]["need_j_std"], 1),
                    "gap_j_std": round(gap[y][p]["gap_j_std"], 1),
                    "shift_p": round(gap[y][p]["shift_p"], 1),
                    "shift_j": round(gap[y][p]["shift_j"], 1),
                } for p in base
            } for y in sorted(proj)
        }
    (REP / "by_province.json").write_text(json.dumps(by_prov, ensure_ascii=False, indent=1), encoding="utf-8")

    nat = out["scenarios"]["基准"]["summary"]["national"]
    print(f"{'年份':<6}{'小学在校生':>10}{'初中在校生':>10}{'小学教师缺口':>12}{'初中教师缺口':>12}{'小学需转岗':>12}")
    for y, v in nat.items():
        print(f"{y:<6}{v['enrol_p']:>10}{v['enrol_j']:>10}{v['gap_p_std']:>12}{v['gap_j_std']:>12}{v['shift_p']:>12}")
    print("\n2030 初中缺口最大的 5 省：")
    for r in out["scenarios"]["基准"]["summary"]["provinces_2030"][:5]:
        print("  ", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
