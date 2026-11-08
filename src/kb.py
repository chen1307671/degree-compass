"""Measure library: turns shortage / balanced / surplus into executable actions.

Each entry has six fields: owner / action / precondition / taboo / indicator / evidence level.
Evidence level: A = clear policy basis or data support; B = plausible mechanism, not locally verified.
"""
from __future__ import annotations

MEASURES: list[dict] = [
    # --- shortage ---
    dict(id="S1", verdict="紧缺", stage="all", name="跨县跨校编制调剂",
         owner="省级教育行政部门", action="在编制总量内，从富余县区向紧缺县区调剂，教师随岗流动",
         precondition="省级统筹编制、岗位设置可调整", taboo="不得挤占乡村小规模学校编制",
         metric="调剂到位人数 / 缺口人数", evidence="A"),
    dict(id="S2", verdict="紧缺", stage="junior", name="特岗教师与公费师范生定向补充",
         owner="省级教育行政部门 + 高校", action="按缺口学科定向招聘，服务期不少于 6 年",
         precondition="有编制空缺、有培养计划", taboo="不得用于非教学岗位",
         metric="补充人数 / 缺口人数", evidence="A"),
    dict(id="S3", verdict="紧缺", stage="all", name="银龄讲学与退休教师返聘",
         owner="县级教育行政部门", action="返聘退休骨干教师承担学科教学与带教",
         precondition="身体健康、学科匹配", taboo="不得替代正式编制长期使用",
         metric="返聘人数、覆盖学科数", evidence="B"),
    dict(id="S4", verdict="紧缺", stage="junior", name="大班额扩容与过渡校区",
         owner="县级政府 + 学校", action="改扩建校舍、设置过渡校区，短期消化入学高峰",
         precondition="校舍安全鉴定通过、有过渡用地", taboo="不得长期维持超标准班额",
         metric="56 人以上班级占比", evidence="A"),
    dict(id="S5", verdict="紧缺", stage="all", name="双师课堂与信息化补位",
         owner="学校 + 教研机构", action="以县域优质校带薄弱校，薄弱学科同步课堂",
         precondition="网络与终端到位", taboo="不得替代实验课与体育课",
         metric="开课节次、学生覆盖数", evidence="B"),
    # --- surplus ---
    dict(id="F1", verdict="富余", stage="primary", name="小学教师转岗学前与特教",
         owner="省级教育行政部门", action="经培训取得资格后转岗幼儿园或特教学校",
         precondition="有岗位空缺、培训学时达标", taboo="不得强制转岗至无资质岗位",
         metric="转岗人数、持证比例", evidence="A"),
    dict(id="F2", verdict="富余", stage="primary", name="小班化教学",
         owner="县级政府 + 学校", action="下调班额上限，把富余教师转为小班教学与个性化辅导",
         precondition="财政可承担增班经费", taboo="不得以“小班化”名义变相择校",
         metric="班均人数、生师比", evidence="A"),
    dict(id="F3", verdict="富余", stage="all", name="跨学段调配（小学→初中/高中）",
         owner="省级教育行政部门", action="按学段峰值错位，提前 2–3 年安排学段间流动与培训",
         precondition="学历与资格符合高学段要求", taboo="不得无证上岗",
         metric="跨学段流动人数", evidence="B"),
    dict(id="F4", verdict="富余", stage="all", name="自然减员不补与岗位结构优化",
         owner="省级编制部门", action="退休不补、控制新增，同时保留紧缺学科补充通道",
         precondition="有退出机制与过渡期", taboo="不得一刀切导致音体美科学断档",
         metric="净减人数、紧缺学科补充率", evidence="A"),
    dict(id="F5", verdict="富余", stage="primary", name="课后服务与教研岗位转化",
         owner="学校", action="把富余课时转为课后服务、社团与教研岗位",
         precondition="有经费保障与考核办法", taboo="不得强制教师无偿承担",
         metric="课后服务参与率、教师课时结构", evidence="B"),
    # --- balanced ---
    dict(id="B1", verdict="平衡", stage="all", name="学科结构优化",
         owner="县级教育行政部门", action="按缺口学科补充音体美科学信息科技教师",
         precondition="有学科需求测算", taboo="不得只看总量不看结构",
         metric="紧缺学科达标率", evidence="A"),
    dict(id="B2", verdict="平衡", stage="all", name="城乡教师轮岗交流",
         owner="县级教育行政部门", action="骨干教师县域内轮岗，职称评聘与轮岗挂钩",
         precondition="有轮岗办法与补贴", taboo="不得只派新教师下乡",
         metric="轮岗比例、骨干占比", evidence="A"),
    dict(id="B3", verdict="平衡", stage="all", name="教师发展中心精准培训",
         owner="市级教研机构", action="按学科短板做小规模、主题式培训",
         precondition="有培训需求诊断", taboo="不得以培训替代编制补充",
         metric="培训学时、课堂改进抽检", evidence="B"),
]



EN = {
 "S1": ("Reallocate posts across counties", "Provincial education department",
        "Move posts from surplus counties to shortage counties within the total quota",
        "Provincial quota control and adjustable post plans", "Do not take posts from small rural schools",
        "Posts reallocated / shortage"),
 "S2": ("Targeted recruitment (special-post & funded teacher graduates)", "Province + universities",
        "Recruit by subject gap, service period of at least six years",
        "Vacant posts and a training pipeline", "Not for non-teaching roles",
        "Recruits / shortage"),
 "S3": ("Re-employ retired teachers", "County education bureau",
        "Rehire retired subject teachers for teaching and mentoring",
        "Health and subject fit", "Not a substitute for permanent posts",
        "Returnees, subjects covered"),
 "S4": ("Expand classrooms and temporary campuses", "County government + schools",
        "Renovate or add classrooms for the intake peak",
        "Safety certification and land", "No long-term over-standard class size",
        "Share of classes above 56 students"),
 "S5": ("Dual-teacher online classes", "Schools + teaching research bodies",
        "Pair strong schools with weak ones for synchronous classes",
        "Network and devices in place", "Not for lab or PE classes",
        "Sessions delivered, students covered"),
 "F1": ("Redeploy primary teachers to pre-school and special education", "Provincial education department",
        "Redeploy after training and certification",
        "Vacancies and training hours", "No forced moves to unqualified roles",
        "Redeployed staff, certification rate"),
 "F2": ("Smaller class sizes", "County government + schools",
        "Lower the class-size cap and shift surplus teachers into smaller classes",
        "Fiscal capacity for extra classes", "Not a route to school choice",
        "Students per class, student-teacher ratio"),
 "F3": ("Cross-stage redeployment (primary to secondary)", "Provincial education department",
        "Plan moves 2-3 years ahead of the stage-level peaks",
        "Qualification for the higher stage", "No unlicensed teaching",
        "Staff moved across stages"),
 "F4": ("Attrition-based reduction with structure protection", "Provincial staffing authority",
        "Do not replace retirees; keep hiring only for shortage subjects",
        "Exit mechanism and transition period", "No one-size-fits-all cuts",
        "Net reduction, shortage-subject hiring"),
 "F5": ("Convert surplus hours into after-school and research roles", "Schools",
        "Turn surplus teaching hours into after-school services and mentoring",
        "Funding and appraisal rules", "No unpaid compulsory extra work",
        "Participation rate, hour structure"),
 "B1": ("Optimise subject structure", "County education bureau",
        "Hire for art, PE, music, science and IT gaps",
        "Subject-level demand estimate", "Do not look at totals only",
        "Shortage-subject compliance"),
 "B2": ("Urban-rural teacher rotation", "County education bureau",
        "Rotate experienced teachers, linked to promotion",
        "Rotation rules and allowances", "Do not send only new teachers",
        "Rotation share, seniority mix"),
 "B3": ("Targeted training through teacher development centres", "Municipal research body",
        "Small, theme-based training on diagnosed weaknesses",
        "Needs diagnosis", "Training is not a substitute for posts",
        "Training hours, classroom follow-up"),
}

def retrieve(verdict: str, stage: str, top_k: int = 4) -> list[dict]:
    """Retrieve by verdict and stage: verdict match first, then stage."""
    def key(m: dict) -> tuple:
        return (0 if m["verdict"] == verdict else 1,
                0 if m["stage"] == stage else (0 if m["stage"] == "all" else 1))
    hits = [m for m in MEASURES if m["verdict"] == verdict or m["stage"] in (stage, "all")]
    out = []
    for m in sorted(hits, key=key)[:top_k]:
        d = dict(m)
        e = EN.get(m["id"])
        if e:
            d.update({"name_en": e[0], "owner_en": e[1], "action_en": e[2],
                      "precondition_en": e[3], "taboo_en": e[4], "metric_en": e[5]})
        out.append(d)
    return out


def summary() -> dict:
    out: dict = {}
    for m in MEASURES:
        out[m["verdict"]] = out.get(m["verdict"], 0) + 1
    return {"total": len(MEASURES), "by_verdict": out}


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), ensure_ascii=False))
    for m in retrieve("紧缺", "junior"):
        print(" -", m["name"], "|", m["owner"])
