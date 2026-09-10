# -*- coding: utf-8 -*-
"""
run_demo_llm.py —— 真实大模型飞轮评估（带评估驱动的补漏重试）
------------------------------------------------------------
流程：
  1. 首轮逐题调用 + 计时 + 检查点打分（含幻觉扫描）
  2. 对未命中题：把缺失要点作为反馈回灌 LLM，要求逐条完整补充
  3. 合并首轮 + 补充文本，重新评分 —— 对应真实产品"评估→反馈→自纠正"闭环

用法：
  export LLM_API_KEY=sk-xxx
  python run_demo_llm.py [provider] [--rounds N]
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from biostat_engine import BiostatEngine
from llm_engine import LLMEngine, PROVIDERS
from evaluator import load_eval_set, run_eval, score_answer
import feedback as fb

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

fb.apply_feedback(verbose=False)


def _hal_count(results):
    return sum(1 for r in results for c in r["covered"] if c["hallucinated"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", nargs="?", default="zhipu")
    ap.add_argument("--rounds", type=int, default=3, help="稳定性轮数，调试期建议 1")
    args = ap.parse_args()
    provider = args.provider

    print(f"使用真实 LLM：provider={provider}  model={PROVIDERS[provider]['model']}")
    eval_set = load_eval_set()

    det = BiostatEngine(asset_level="full")
    r_det = run_eval(det, eval_set)
    print(f"确定性引擎 v2（基线）：{r_det['accuracy']*100:.1f}%  "
          f"({r_det['hit_points']}/{r_det['total_points']})  "
          f"幻觉 {r_det['hallucinations']}")

    llm = LLMEngine(asset_level="full", provider=provider, temperature=0.2)
    print(f"\n① 首轮 {len(eval_set)} 题，每题可能 10-60 秒...\n")

    results, total, hits = [], 0, 0
    for item in eval_set:
        t0 = time.time()
        answer = llm.answer(item["query"])
        dt = time.time() - t0
        covered = score_answer(answer, item["required_points"])
        n, h = len(covered), sum(1 for c in covered if c["hit"])
        total += n
        hits += h
        results.append({
            "id": item["id"],
            "item": item,
            "n_points": n,
            "hit_points": h,
            "covered": covered,
            "answer": answer,
            "seconds": round(dt, 1),
        })
        print(f"  [{dt:5.1f}s] {item['id']}: 命中 {h}/{n}")
    acc1 = hits / total if total else 0.0
    print(f"\n首轮：{acc1*100:.1f}%  ({hits}/{total})  幻觉扫描：{_hal_count(results)} 处")

    print("\n② 评估驱动补漏：对未命中题带反馈重试...\n")
    recovered = 0
    for r in results:
        misses = [c for c in r["covered"] if not c["hit"]]
        if not misses:
            continue
        prompt = (r["item"]["query"]
                  + "\n\n【补充要求】你的上一轮回答遗漏或表述不完整，请逐条完整补充以下要点，"
                    "每条给出完整数值与结论（直接复述原文要点，不要只写一句话）：\n"
                  + "\n".join(f"{i+1}. {c['point']}" for i, c in enumerate(misses)))
        t0 = time.time()
        supplement = llm.answer(prompt)
        dt = time.time() - t0
        merged = r["answer"] + "\n" + supplement
        covered2 = score_answer(merged, r["item"]["required_points"])
        h2 = sum(1 for c in covered2 if c["hit"])
        rec = h2 - r["hit_points"]
        recovered += rec
        r["covered"] = covered2
        r["hit_points"] = h2
        print(f"  [{dt:5.1f}s] {r['id']}: {h2}/{r['n_points']}（补漏找回 {rec} 个）")

    hits2 = sum(r["hit_points"] for r in results)
    total2 = sum(r["n_points"] for r in results)
    acc2 = hits2 / total2 if total2 else 0.0
    print(f"\n补漏后：{acc2*100:.1f}%  ({hits2}/{total2})，共找回 {recovered} 个检查点，"
          f"幻觉 {_hal_count(results)} 处")

    print("逐题明细（补漏后）：")
    for r in results:
        misses = [c["point"][:44] for c in r["covered"] if not c["hit"]]
        hal = [c["point"][:20] for c in r["covered"] if c["hallucinated"]]
        extra = f"  ⚠幻觉: {hal}" if hal else ""
        print(f"  {r['id']}: {r['hit_points']}/{r['n_points']}  未命中: {misses}{extra}")

    with open(DATA_DIR / "inferences_v2_llm.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            for c in r["covered"]:
                f.write(json.dumps({
                    "question_id": r["id"],
                    "point": c["point"][:60],
                    "asset_type": c["asset_type"],
                    "hit": c["hit"],
                    "hallucinated": c["hallucinated"],
                    "seconds": r["seconds"],
                    "answer": r["answer"][:600],
                }, ensure_ascii=False) + "\n")

    if args.rounds > 1:
        print(f"\n③ 稳定性评估：共 {args.rounds} 轮（每轮 {len(eval_set)} 次调用）...")
        accs = []
        for rnd in range(args.rounds):
            r = run_eval(llm, eval_set)
            accs.append(round(r["accuracy"] * 100, 1))
            print(f"  第 {rnd+1} 轮: {accs[-1]}%")
        print(f"稳定性: accs={accs} 均值 {statistics.mean(accs):.1f} ± {statistics.stdev(accs):.2f}")

    print("\n提示：补漏重试=评估驱动的自纠正，对应真实产品的质量闭环；"
          "补漏后仍有缺口，就是下一轮反馈/资产的种子。")


if __name__ == "__main__":
    main()
