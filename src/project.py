"""Provincial cohort projection and teacher-gap estimation (2024 baseline to 2030).

Method: cohort progression
- Primary: grade 1 follows the national intake path (2025 from the bulletin, then scenario growth);
  grades 2-6 roll forward from the previous grade with a survival rate of 0.995.
- Junior secondary: grade 1 = primary graduates x provincial transition rate; grades 2-4 roll forward.
- Teacher demand under two conventions:
  A. Standard staffing: enrolment / national ratio (primary 19:1, junior 13.5:1), compared with current teachers
  B. Current ratio: hold the 2024 ratio, giving the number to add or reduce

External anchors (2025 national bulletin):
  primary intake 14.6174 million, primary enrolment 101.7829 million
  junior intake 18.5281 million, junior enrolment 55.0934 million
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import regdata as rd

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"

SURVIVE = 0.995                 # grade-to-grade survival rate
RATIO_STD = {"primary": 19.0, "junior": 13.5}   # national standard staffing ratios
ANCHOR = {"primary_entrants_2025": 14_617_400, "primary_enrol_2025": 101_782_900,
          "junior_entrants_2025": 18_528_100, "junior_enrol_2025": 55_093_400}
SCENARIOS = {"基准": -0.06, "温和": -0.03, "加速": -0.09}   # yearly change of primary intake from 2026
INTAKE_CAP = 0.10   # cap on the year-on-year change of junior intake (source grade mix is noisy)
JUNIOR_CALIB = 0.9556   # junior intake calibration: 2025 equals the bulletin value of 55.093 million


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
    """2024 baseline: enrolment, teachers, ratio, intake share and transition rate by province."""
    pri, jun = d["primary"], d["junior"]
    nat_pri_ent = sum(r.get("entrants", 0) for r in pri.values())
    out = {}
    for p in rd.PROVINCES:
        gp = pri.get(p, {})
        gj = jun.get(p, {})
        grades = [gp.get(f"g{i}", 0.0) for i in range(1, 7)]
        # Four-year junior secondary (Shanghai, Heilongjiang, Shandong): detect from data
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
            "junior_share": gj.get("entrants", 0.0),
            "j1_2024": jgrades[0],
            "pre_leavers": d["pre"].get(p, {}).get("leavers", 0.0),
        }
    return out


def project(base: dict, delta: float, years=range(2025, 2031)) -> dict:
    """Project by scenario; returns {year: {province: {...}}}."""
    # Reconstruct the 2024 national intake from provincial shares
    shares = {p: b["entry_share"] for p, b in base.items()}
    total_share = sum(shares.values()) or 1.0
    nat_2024 = ANCHOR["primary_entrants_2025"] / (1 + delta)   # back out 2024 from the 2025 anchor and the growth rate
    nat_entry = {2024: nat_2024, 2025: ANCHOR["primary_entrants_2025"]}
    for y in range(2026, (max(years) if years else 2030) + 1):
        nat_entry[y] = nat_entry[y - 1] * (1 + delta)

    # National junior-intake path: 2025 anchored to the bulletin, then graduates x rate x calibration
    grad_nat = {2024: sum(b["grades_p"][5] for b in base.values()) / 1e4}

    res = {}
    # 2024 baseline
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
            # Primary: grade 1 from national intake x provincial share; higher grades roll forward
            g1 = nat_entry[y] * (shares[p] / total_share if total_share else 0)
            new_gp = [g1] + [gp[i] * SURVIVE for i in range(5)]
            # Junior: grade 1 = primary graduates x transition rate; grades 2-3 roll forward
            grad_p = gp[5] * SURVIVE
            rate = (b["junior_intake_rate"] or 1.0) * JUNIOR_CALIB
            j1 = grad_p * rate
            prev_j1 = prev[p]["grades_j"][0] or b["j1_2024"]
            j1 = max(prev_j1 * (1 - INTAKE_CAP), min(prev_j1 * (1 + INTAKE_CAP), j1))
            if b.get("n_jun", 3) == 4:
                new_gj = [j1, gj[0] * SURVIVE, gj[1] * SURVIVE, gj[2] * SURVIVE]
            else:
                new_gj = [j1, gj[0] * SURVIVE, gj[1] * SURVIVE, 0.0]
            cur[p] = {"enrol_p": sum(new_gp), "enrol_j": sum(new_gj),
                      "grades_p": new_gp, "grades_j": new_gj}
        res[y] = cur
        grad_nat[y] = sum(cur[p]["grades_p"][5] for p in base) / 1e4
        prev = {p: {"grades_p": cur[p]["grades_p"], "grades_j": cur[p]["grades_j"]} for p in base}
    return res


def gaps(base: dict, proj: dict) -> dict:
    """Teacher gap / surplus under the two staffing conventions."""
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

    # Per-province yearly detail for the agent's cell-level queries
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
