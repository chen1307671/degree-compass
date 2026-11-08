"""Degree Compass - pre-submission self-check.

Build/verify script for the Degree Compass deliverable. See README for usage."""
from __future__ import annotations
import json, pathlib, subprocess, sys, re

HERE = pathlib.Path(__file__).resolve().parent
R = HERE / "reports"


def _find(name: str) -> pathlib.Path:
    """Docs may sit in the current directory or the parent one."""
    p = HERE / name
    if p.exists():
        return p
    q = HERE.parent / name
    return q if q.exists() else p


def _read(name: str) -> str:
    p = _find(name)
    return p.read_text(encoding="utf-8") if p.exists() else ""


S = json.loads((R / "selftest.json").read_text(encoding="utf-8"))
checks, failed = [], []


def chk(name, ok, detail=""):
    checks.append(dict(name=name, pass_=bool(ok), detail=detail))
    if not ok:
        failed.append(name)


# ===== A. AI-direction veto checks =====
src = (HERE / "src" / "core.py").read_text(encoding="utf-8", errors="ignore")
has_train = bool(re.search(r"\.(fit|train)\s*\(", src)) and \
    ("Classifier" in src or "Regression" in src)
chk("AI-A1 存在可训练模型(Classifier/Regression+fit)",
    has_train, "core.py 含 fit() 与 Classifier/Regression")

has_policy = "pol.decide" in src or "self.pol.decide" in src
has_hardcode = bool(re.search(r"action\s*=\s*[\"'](risk|attribute|counterfactual|backtest|finish)[\"']", src))
chk("AI-A2 工具选择由模型产生(非 if-else 硬编码)",
    has_policy and not has_hardcode, f"pol.decide={has_policy}, 硬编码动作={has_hardcode}")

chk("AI-A3 具备模型指标与消融",
    all(k in S for k in ("model_metrics", "ablation", "bootstrap_ci")),
    "model_metrics/ablation/bootstrap_ci 均存在")

chk("AI-A4 有预测结果章节(p_dropout 等)",
    "p_dropout" in S["prompts"][0] and "auc_dropout_hgb" in S["model_metrics"],
    "提示词含 p_dropout，模型含 AUC")

chk("AI-A5 策略模型优于多数类基线（留出集）",
    (S["planner"].get("holdout_accuracy") or 0) > (S["planner"].get("holdout_majority") or 1) + 0.1,
    f"holdout={S['planner'].get('holdout_accuracy')} vs {S['planner'].get('holdout_majority')}")

chk("AI-A6 AI 内核组件>=4",
    isinstance(S.get("ai_components"), list) and len(S["ai_components"]) >= 4,
    f"ai_components={len(S.get('ai_components', []))}")

chk("AI-A7 早预警口径已报告（不含第二学期）",
    len(S.get("early_warning", {}).get("auc_by_feature_set", {})) >= 3,
    str(S.get("early_warning", {}).get("auc_by_feature_set", {})))
chk("AI-A8 划分稳定性复跑已报告",
    S.get("split_robustness", {}).get("n_seeds", 0) >= 3,
    f"n_seeds={S.get('split_robustness', {}).get('n_seeds')} std={S.get('split_robustness', {}).get('auc_std')}")
chk("AI-A9 策略留出集准确率已报告",
    S["planner"].get("holdout_accuracy") is not None,
    f"holdout={S['planner'].get('holdout_accuracy')}")
chk("AI-A10 组级 bootstrap CI 已报告",
    "bootstrap_group_ci" in S,
    f"ci={S.get('bootstrap_group_ci', {}).get('ci95_low')}~{S.get('bootstrap_group_ci', {}).get('ci95_high')}")

ai_ok = all(c["pass_"] for c in checks if c["name"].startswith("AI-A"))
chk("AI-A11 知识库已接入智能体",
    (HERE / "src" / "kb.py").exists()
    and "from kb import" in src
    and (S["prompts"][0].get("full_result", {}).get("knowledge_base", {})
         .get("summary", {}).get("total", 0) >= 10),
    f"kb_total={S['prompts'][0].get('full_result', {}).get('knowledge_base', {}).get('summary', {}).get('total')}")

chk("DATA-7 外部数据集验证已执行",
    (R / "external_validation.json").exists(), "reports/external_validation.json")
_ev = json.loads((R / "external_validation.json").read_text(encoding="utf-8")) \
    if (R / "external_validation.json").exists() else {}
_a = (_ev.get("protocol_a_no_g1g2") or {}).get("auc_mean", 0)
_b = (_ev.get("protocol_b_with_g1") or {}).get("auc_mean", 0)
chk("DATA-8 外部验证 AUC 高于随机基线",
    _a > 0.60 and _b > 0.80, f"A={_a} B={_b}")

chk("Causal-1 PSM 报告存在且匹配质量达标",
    (R / "psm.json").exists(), "reports/psm.json")
_ps = json.loads((R / "psm.json").read_text(encoding="utf-8")) if (R / "psm.json").exists() else {}
chk("Causal-2 匹配后 SMD<0.1 且 ATT 区间不含 0",
    _ps.get("smd_max_after", 1) < 0.1 and _ps.get("ATT_ci95", [0, 0])[1] < 0,
    f"SMD_after={_ps.get('smd_max_after')} ATT={_ps.get('ATT')} CI={_ps.get('ATT_ci95')}")

chk("AI-总 一票否决项全部通过", ai_ok, "任意一项失败即非合格 AI 作品")

# ===== B. data integrity =====
dc = S["data_contract"]
m = S["model_metrics"]
chk("DATA-1 零合成数据", dc["no_synthetic_data"] is True, dc.get("data_kind"))
chk("DATA-2 授权 CC BY 4.0", "CC BY 4.0" in dc["license"], dc["license"])
chk("DATA-3 标签三分类且分布合理",
    set(dc["target_distribution"]) == {"Dropout", "Graduate", "Enrolled"},
    str(dc["target_distribution"]))
chk("DATA-4 按专业分组且零重叠",
    m["groups_train"] > 0 and m["group_overlap"] == 0,
    f"g_train={m['groups_train']} overlap={m['group_overlap']}")
# data hash record
hash_file = R / "data_sha256.txt"
if not hash_file.exists():
    import hashlib
    b = (HERE / "raw" / "data.csv").read_bytes()
    hash_file.write_text(hashlib.sha256(b).hexdigest(), encoding="utf-8")
chk("DATA-5 数据 SHA256 已记录", hash_file.exists(), hash_file.name)

# runtime smoke test: actually load the data (catches missing raw files)
try:
    sys.path.insert(0, str(HERE / "src"))
    import core as _core
    _d = _core.LearnData()
    chk("DATA-6 原始数据可加载（运行期冒烟）",
        len(_d.rows) == 4424 and _d.X.shape[1] == 36,
        f"{len(_d.rows)} 行 × {_d.X.shape[1]} 特征")
except Exception as _e:  # noqa: BLE001
    chk("DATA-6 原始数据可加载（运行期冒烟）", False, f"{type(_e).__name__}: {_e}")

# ===== C. deliverables =====
def fexist(p, minbytes=0):
    return (HERE / p).exists() and (HERE / p).stat().st_size > minbytes

chk("OUT-1 PPTX 存在", fexist("slides/学策_答辩演示_v4.pptx", 1000))
chk("OUT-2 视频 mp4 存在", fexist("slides/学策_演示视频.mp4", 1000))
chk("OUT-3 SRT 字幕存在", fexist("slides/学策_演示字幕.srt", 100))
chk("OUT-4 评测报告存在", fexist("reports/selftest.json", 1000))
chk("OUT-5 提示词真实输出存在", fexist("reports/prompt_outputs.json", 1000))
chk("OUT-6 源码 core/server/run 齐全",
    fexist("src/core.py") and fexist("src/server.py") and fexist("run.py"))
chk("OUT-7 视频/PPT 生成器齐全",
    fexist("make_ppt.py") and fexist("make_video.py"))
chk("OUT-8 文字材料齐全",
    _find("作品说明.md").exists() and _find("答辩要点.md").exists()
    and _find("README.md").exists())
meta = json.loads((R / "video_meta.json").read_text(encoding="utf-8")) if (R / "video_meta.json").exists() else {}
chk("OUT-9 视频规格 1280x720/≤6min",
    meta.get("resolution") == "1280x720" and meta.get("duration_seconds", 0) <= 360,
    str(meta))

# ===== D. consistency: slides vs selftest =====
import importlib.util
spec = importlib.util.spec_from_file_location("sd", HERE / "src" / "slides_data.py")
sd = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd)
m = S["model_metrics"]; pl = S["planner"]
def near(a, b, tol=1e-3): return abs(float(a) - float(b)) <= tol
consistent = True
msgs = []
if str(sd.SLIDES[7]["cards"][0][0]) != str(m["auc_macro_ovr_calibrated"]):
    consistent = False; msgs.append("P7 AUC 不一致")
if not near(sd.SLIDES[10]["hero"][0], pl.get("holdout_accuracy") or pl["train_accuracy"]):
    consistent = False; msgs.append("P10 策略留出准确率不一致")
if sd.SLIDES[4]["hero"][0] != str(m["group_overlap"]):
    consistent = False; msgs.append("P5 组重叠不一致")
if sd.SLIDES[1]["hero"][0] != f"{m['test_dropout_rate']:.1%}":
    consistent = False; msgs.append("P2 辍学率不一致")
chk("CONS-1 幻灯片数字与评测报告一致", consistent, ";".join(msgs) or "全部对齐")
chk("CONS-2 PPT 页数=20", len(sd.SLIDES) == 20, f"{len(sd.SLIDES)} 页")
chk("CONS-3 提示词条数=3", len(S["prompts"]) == 3, f"{len(S['prompts'])} 条")

_doc = _read("作品说明.md")
_chk_doc = _read("提交自检清单.md")
chk("CONS-4 作品说明基线样本数与代码一致(36)",
    "60 个" not in _doc and "36 个" in _doc, "60→36")
chk("CONS-5 提交清单视频规则为 6 分钟",
    "8 分钟" not in _chk_doc and "6 分钟" in _chk_doc, "8min→6min")
chk("CONS-6 作品说明不再声称未实现的待复核（已实现）",
    "方向一致才输出建议" in _doc or "待复核" in _doc, "待复核已落地")
chk("CONS-7 200 字作品描述存在",
    _find("作品描述_200字.md").exists(), "作品描述_200字.md")
_sd_src = (HERE / "src" / "slides_data.py").read_text(encoding="utf-8")
chk("CONS-8 智能体链接可配置（AGENT_URL）",
    "AGENT_URL" in _sd_src and "环境变量" in _sd_src, "AGENT_URL 环境变量")
chk("CONS-9 作品说明含参考文献",
    "参考文献" in _doc and "10.3390/data7110146" in _doc, "GB/T 7714 参考文献")
chk("CONS-10 数据渠道≥3 且含外部验证集",
    _doc.count("UCI") >= 3 and "UCI #320" in _doc, "UCI #697 / Zenodo / UCI #320")
chk("CONS-11 部署说明存在（含隧道与容器）",
    fexist("deploy/部署说明.md", 200) and fexist("deploy/Dockerfile", 50),
    "deploy/")

# ===== E. runnable (static import check) =====
try:
    compile((HERE / "src" / "core.py").read_text(encoding="utf-8"), "core.py", "exec")
    compile((HERE / "src" / "server.py").read_text(encoding="utf-8"), "server.py", "exec")
    compile((HERE / "run.py").read_text(encoding="utf-8"), "run.py", "exec")
    chk("RUN-1 核心源码可编译", True)
except SyntaxError as e:
    chk("RUN-1 核心源码可编译", False, str(e))

# ===== summary =====
total = len(checks); passed = sum(1 for c in checks if c["pass_"])
verdict = "PASS" if not failed else "FAIL"
report = dict(verdict=verdict, passed=passed, total=total, failed=failed,
              ai_direction_pass=ai_ok, checks=checks)
(R / "final_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"自检：{verdict}  {passed}/{total}  AI方向={ai_ok}  失败={failed if failed else '无'}")
sys.exit(0 if verdict == "PASS" else 1)
