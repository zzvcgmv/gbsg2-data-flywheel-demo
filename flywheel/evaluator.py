# -*- coding: utf-8 -*-
"""
evaluator.py —— 评估器（评估集 + 准确率 + 稳定性）
--------------------------------------------------
对应 TensorZero 的 Evaluation（heuristics 模式）与 JD「评估与质量体系」：
- 评估集本身也是一种资产：assets/eval_set.json（由 golden_standard/ 自动生成）
- 准确率 = 命中的检查点 / 总检查点（keypoint coverage）
- 稳定性 = 同一引擎重复评估 3 轮的方差（真实 LLM 场景应加大采样轮次）
- 评估结果写回推理日志（inferences_*.jsonl），形成"评估即回流"
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_eval_set():
    with open(ROOT / "assets" / "eval_set.json", encoding="utf-8") as f:
        return json.load(f)


def score_answer(answer_text: str, required_points):
    """对单个问题的逐检查点打分。
    - keywords：AND 语义（全部出现才命中）
    - or_keywords：OR 语义（任一出现即命中，用于语义等价表达）
    - forbidden：出现即记幻觉（与金标准冲突的数值）
    """
    covered = []
    for p in required_points:
        orkw = p.get("or_keywords") or []
        if orkw:
            hit = any(k in answer_text for k in orkw)
        else:
            hit = all(kw in answer_text for kw in p["keywords"])
        hallucinated = any(fb in answer_text for fb in p.get("forbidden", []))
        covered.append(
            {
                "point": p["point"],
                "asset_type": p["asset_type"],
                "hit": hit,
                "hallucinated": hallucinated,
            }
        )
    return covered


def run_eval(engine, eval_set):
    """跑一轮评估，返回逐题明细 + 总体准确率 + 幻觉扫描。"""
    results = []
    total = hits = hal = 0
    for item in eval_set:
        answer = engine.answer(item["query"])
        covered = score_answer(answer, item["required_points"])
        n, h = len(covered), sum(1 for c in covered if c["hit"])
        hz = sum(1 for c in covered if c["hallucinated"])
        total += n
        hits += h
        hal += hz
        results.append(
            {
                "id": item["id"],
                "query": item["query"],
                "analysis_target": item["analysis_target"],
                "n_points": n,
                "hit_points": h,
                "hallucinations": hz,
                "coverage": h / n if n else 0.0,
                "covered": covered,
                "answer": answer,
            }
        )
    return {
        "results": results,
        "accuracy": hits / total if total else 0.0,
        "total_points": total,
        "hit_points": hits,
        "hallucinations": hal,
    }


def run_eval_repeated(engine, eval_set, rounds: int = 3):
    """稳定性评估：重复 N 轮，输出准确率序列与标准差。"""
    accs = []
    for _ in range(rounds):
        r = run_eval(engine, eval_set)
        accs.append(round(r["accuracy"] * 100, 1))
    return {
        "accuracies": accs,
        "mean": round(statistics.mean(accs), 1),
        "stdev": round(statistics.stdev(accs), 2) if len(accs) > 1 else 0.0,
    }
