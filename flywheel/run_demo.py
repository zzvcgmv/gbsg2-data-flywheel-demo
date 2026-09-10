# -*- coding: utf-8 -*-
"""
run_demo.py —— 数据飞轮 demo 主流程
-----------------------------------
对应 JD「数据回流与反馈机制」+「越用越准的数据飞轮」：

    golden_standard/ (R 侧金标准)  ──接口──▶  eval_set (评估集)
        v1 引擎（base 资产）──── 评估 48.1%
            │
        业务方/统计评审纠错 feedback.jsonl
            │
        反馈资产化沉淀（tier=learned, 带溯源）──── "分析经验资产化"
            │
        v2 引擎（full 资产）──── 评估 96.3%
            │
        唯一未命中检查点 → 成为下一轮反馈种子（飞轮持续转）
"""
import json
from pathlib import Path

from gen_eval_set import build as build_eval_set
from biostat_engine import BiostatEngine
from evaluator import load_eval_set, run_eval, run_eval_repeated
import feedback as fb

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT


def dump_inferences(run_result, path: Path):
    rows = []
    for r in run_result["results"]:
        for c in r["covered"]:
            rows.append(
                {
                    "question_id": r["id"],
                    "analysis_target": r.get("analysis_target"),
                    "point": c["point"],
                    "asset_type": c["asset_type"],
                    "hit": c["hit"],
                    "answer_snippet": r["answer"][:120],
                }
            )
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  推理日志 → {path.name}（{len(rows)} 条检查点记录）")


def main():
    print("=" * 60)
    print("STEP 0/4  从 golden_standard/ 生成评估集（接口对接）")
    build_eval_set()
    eval_set = load_eval_set()

    print("\nSTEP 1/4  跑 v1（base：只有初始内置统计知识）")
    engine_v1 = BiostatEngine(asset_level="base")
    r1 = run_eval(engine_v1, eval_set)
    stab1 = run_eval_repeated(engine_v1, eval_set, rounds=3)
    dump_inferences(r1, DATA_DIR / "inferences_v1.jsonl")
    print(f"  v1 accuracy = {r1['accuracy']*100:.1f}%  "
          f"({r1['hit_points']}/{r1['total_points']})  "
          f"稳定性 {stab1['accuracies']} 均值 {stab1['mean']} ± {stab1['stdev']}")

    print("\nSTEP 2/4  反馈回流：业务方/统计评审纠错 → 资产化沉淀（带溯源）")
    ledger = fb.apply_feedback(verbose=True)
    n_learned = len(ledger)

    print("\nSTEP 3/4  跑 v2（full：base + 反馈沉淀的学习层资产）")
    engine_v2 = BiostatEngine(asset_level="full")
    r2 = run_eval(engine_v2, eval_set)
    stab2 = run_eval_repeated(engine_v2, eval_set, rounds=3)
    dump_inferences(r2, DATA_DIR / "inferences_v2.jsonl")
    print(f"  v2 accuracy = {r2['accuracy']*100:.1f}%  "
          f"({r2['hit_points']}/{r2['total_points']})  "
          f"稳定性 {stab2['accuracies']} 均值 {stab2['mean']} ± {stab2['stdev']}")

    print("\nSTEP 4/4  生成对比报告")
    report = build_report(r1, r2, stab1, stab2, ledger, n_learned)
    (OUT_DIR / "report.md").write_text(report["md"], encoding="utf-8")
    (OUT_DIR / "report.html").write_text(report["html"], encoding="utf-8")
    print(f"  → report.md / report.html 已生成（{OUT_DIR}）")
    print("=" * 60)


def build_report(r1, r2, stab1, stab2, ledger, n_learned):
    md = []
    md.append("# 数据飞轮 Demo 报告 — AI 生物统计分析师\n")
    md.append(f"**数据集**：GBSG2（686 例，事件 299）· **金标准**：golden_standard/（5 题 27 检查点，R 真实运行产出）\n")
    md.append("## 飞轮结果\n")
    md.append("| 版本 | 准确率 | 检查点 | 稳定性(3 轮) | 说明 |")
    md.append("|---|---|---|---|---|")
    md.append(f"| v1（base 资产） | {r1['accuracy']*100:.1f}% | {r1['hit_points']}/{r1['total_points']} | {stab1['mean']}±{stab1['stdev']} | 只有初始内置统计知识 |")
    md.append(f"| v2（base+learned） | {r2['accuracy']*100:.1f}% | {r2['hit_points']}/{r2['total_points']} | {stab2['mean']}±{stab2['stdev']} | 含 {n_learned} 条反馈沉淀资产 |")
    md.append("")
    md.append(f"**提升：{(r2['accuracy']-r1['accuracy'])*100:.1f} 个百分点** —— 反馈回流 → 资产沉淀 → 准确率上升，飞轮转起来了。\n")
    md.append("## 逐题明细\n")
    md.append("| 题 | 目标 | v1 | v2 |")
    md.append("|---|---|---|---|")
    for a, b in zip(r1["results"], r2["results"]):
        md.append(f"| {a['id']} | {a['analysis_target']} | {a['hit_points']}/{a['n_points']} | {b['hit_points']}/{b['n_points']} |")
    md.append("")
    missing = [c["point"] for r in r2["results"] for c in r["covered"] if not c["hit"]]
    if missing:
        md.append("## 仍存在的缺口（下一轮反馈的种子）\n")
        for m in missing:
            md.append(f"- [ ] {m}")
    md.append("")
    md.append("## 反馈台账（资产化溯源）\n")
    md.append("| 反馈 ID | 来源 | 类型 | 沉淀资产 |")
    md.append("|---|---|---|---|")
    for row in ledger:
        md.append(f"| {row['feedback_id']} | {row['source_role']} | {row['feedback_type']} | {row['asset_file']} #{row['asset_id']} |")
    md.append("")
    md.append("## 接口与可复现性\n")
    md.append("- R 侧（金标准生产）：`golden_standard/`，seed=42，survival/ranger 真实运行")
    md.append("- 接口：JSON schema（question_id / question / golden_answer.key_points），`gen_eval_set.py` 自动生成评估集")
    md.append("- Python 侧（飞轮）：`flywheel/`，确定性引擎模拟 LLM，零依赖可复现；真实场景替换为 LLM 调用即可")
    md_text = "\n".join(md)

    rows_html = "".join(
        f"<tr><td>{a['id']}</td><td>{a['analysis_target']}</td>"
        f"<td>{a['hit_points']}/{a['n_points']}</td><td>{b['hit_points']}/{b['n_points']}</td></tr>"
        for a, b in zip(r1["results"], r2["results"])
    )
    fb_rows = "".join(
        f"<tr><td>{row['feedback_id']}</td><td>{row['source_role']}</td>"
        f"<td>{row['feedback_type']}</td><td>{row['asset_file']} #{row['asset_id']}</td></tr>"
        for row in ledger
    )
    missing_html = "".join(f"<li>⚠ {m}</li>" for m in missing) or "<li>无</li>"
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>数据飞轮 Demo 报告</title>
<style>
body{{font-family:'PingFang SC','Segoe UI',Arial,sans-serif;background:#F4F3EE;color:#1A1B1C;margin:0;padding:32px 16px;}}
.card{{max-width:880px;margin:0 auto;background:#fff;border:1px solid #E4E3DD;border-radius:14px;padding:24px 28px;}}
h1{{font-size:20px;margin:0 0 4px;}} .sub{{font-size:12px;color:#6B7280;margin-bottom:20px;}}
h2{{font-size:15px;margin:24px 0 10px;}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;}} th,td{{border:1px solid #E4E3DD;padding:7px 10px;text-align:left;}}
th{{background:#F0EFEA;font-weight:600;}}
.big{{font-size:26px;font-weight:700;color:#1A6B8F;}}
.delta{{font-size:14px;font-weight:600;color:#52C41A;margin:10px 0 0;}}
ul{{font-size:12.5px;}} li{{margin:4px 0;}}
</style></head>
<body><div class="card">
<h1>数据飞轮 Demo 报告 — AI 生物统计分析师</h1>
<div class="sub">数据集：GBSG2（686 例，事件 299）· 金标准：golden_standard/（5 题 27 检查点，R 真实运行产出）</div>
<h2>飞轮结果</h2>
<table><tr><th>版本</th><th>准确率</th><th>检查点</th><th>稳定性(3 轮)</th><th>说明</th></tr>
<tr><td>v1（base 资产）</td><td>{r1['accuracy']*100:.1f}%</td><td>{r1['hit_points']}/{r1['total_points']}</td><td>{stab1['mean']}±{stab1['stdev']}</td><td>只有初始内置统计知识</td></tr>
<tr><td>v2（base+learned）</td><td class="big">{r2['accuracy']*100:.1f}%</td><td>{r2['hit_points']}/{r2['total_points']}</td><td>{stab2['mean']}±{stab2['stdev']}</td><td>含 {n_learned} 条反馈沉淀资产</td></tr>
</table>
<p class="delta">提升 {(r2['accuracy']-r1['accuracy'])*100:.1f} 个百分点 —— 反馈回流 → 资产沉淀 → 准确率上升，飞轮转起来了。</p>
<h2>逐题明细</h2>
<table><tr><th>题</th><th>目标</th><th>v1</th><th>v2</th></tr>{rows_html}</table>
<h2>仍存在的缺口（下一轮反馈的种子）</h2><ul>{missing_html}</ul>
<h2>反馈台账（资产化溯源）</h2>
<table><tr><th>反馈 ID</th><th>来源</th><th>类型</th><th>沉淀资产</th></tr>{fb_rows}</table>
<h2>接口与可复现性</h2>
<ul><li>R 侧（金标准生产）：golden_standard/，seed=42，survival/ranger 真实运行</li>
<li>接口：JSON schema（question_id / question / golden_answer.key_points），gen_eval_set.py 自动生成评估集</li>
<li>Python 侧（飞轮）：flywheel/，确定性引擎模拟 LLM，零依赖可复现；真实场景替换为 LLM 调用即可</li></ul>
</div></body></html>"""
    return {"md": md_text, "html": html}


if __name__ == "__main__":
    main()
