"""学位罗盘 Compass · 统一入口

用法：
    python run.py --selftest          数据校验 + 三条提示词推演
    python run.py --serve [--port N]  启动演示服务
"""
from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from core import PROMPTS, Planner, RegionData  # noqa: E402
import regdata as rd  # noqa: E402


def selftest() -> int:
    print("=== 数据校验 ===")
    diag = rd.diagnostics()
    ok = True
    for stage, d in diag.items():
        if "grade_vs_enrol_diff_pct" in d:
            pct = d["grade_vs_enrol_diff_pct"]
            flag = "PASS" if abs(pct) < 0.01 else "FAIL"
            ok &= abs(pct) < 0.01
            print(f"[{flag}] {stage}: 分年级合计与在校生差异 {pct}%（{d['enrolment_sum']:,}）")

    print("\n=== 三条提示词 ===")
    data = RegionData()
    planner = Planner(data)
    cases = [("广东", "junior", 2030, "基准"), ("河南", "primary", 2030, "基准"), ("广东", "primary", 2030, "基准")]
    for i, (prov, stage, year, scen) in enumerate(cases, 1):
        r = planner.run(prov, stage, year, scen, PROMPTS[i - 1])
        s = r["summary"]
        print(f"  提示{i}: {prov} {stage} {year} → 在校生 {s['enrol_wan']} 万（{s['change_pct']}%），"
              f"{s['verdict']}，缺口/富余 {s['gap_wan']} 万，措施 {len(r['actions'])} 条，{r['elapsed_ms']} ms")
    return 0 if ok else 1


def serve(port: int) -> int:
    from server import init_state
    from server import serve as _serve
    data = RegionData()
    planner = Planner(data)
    init_state(data, planner)
    print(f"[compass] 数据就绪：{len(data.provinces)} 省", flush=True)
    _serve(port=port, host="0.0.0.0")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8767)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.serve:
        return serve(a.port)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
