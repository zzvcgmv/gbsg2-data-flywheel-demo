# -*- coding: utf-8 -*-
"""
gen_eval_set.py —— 从 golden_standard/ 自动生成评估集
------------------------------------------------------
演示"接口"：R 侧金标准 JSON 是唯一数据源，Python 评估集由它生成，不做手工搬运。
- 每个 key_points[i] -> 一条 required_point（保留原文 + 评估 keywords）
- keywords 表是评估器的"打分调参"，与金标准内容解耦
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GS_DIR = ROOT.parent / "golden_standard"
OUT = ROOT / "assets" / "eval_set.json"

# 每题 key_points 的 keywords 与 asset_type（与 golden_standard 的 key_points 一一对应）
KP_SPEC = {
    "q01": {
        "query_suffix": "（请给出方法、关键数值、PH 诊断与稳健性说明）",
        # forbidden：与金标准冲突的数值，出现即记"幻觉"（评估器新维度）
        "forbidden": {0: ["0.642", "0.774"]},
        "points": [
            ("数值", ["0.707"]),
            ("诊断", ["0.625"]),
            ("数值", ["0.692"]),
            ("方法", ["pnodes", "progrec"]),
            ("诊断", ["estrec", "0.661"]),
            ("稳健性", ["0.695", "0.699"]),
            ("盲区", ["局限"]),
        ],
    },
    "q02": {
        "query_suffix": "（请给出方法、关键数值与稳健性说明）",
        "points": [
            ("方法", ["horTh", "tsize", "pnodes", "progrec"]),
            ("诊断", ["age", "0.309"]),
            ("诊断", ["0.60"]),
            ("稳健性", ["0.695", "0.707"]),
        ],
    },
    "q03": {
        "query_suffix": "（请给出方法、关键数值与稳健性说明）",
        "points": [
            ("方法", ["3489.464"]),
            ("数值", ["3490.349"]),
            ("诊断", ["0.089"]),
            ("诊断", ["0.099"]),
            ("方法", ["因子"]),
        ],
    },
    "q04": {
        "query_suffix": "（请给出方法、关键数值、PH 诊断与稳健性说明）",
        "points": [
            ("诊断", ["0.0037"]),
            ("诊断", ["menostat", "tgrade"]),
            ("稳健性", ["0.699"]),
            ("诊断", ["不改变"], ["不改变", "不受影响", "仍成立", "仍然成立"]),
            ("方法", ["结构不同"]),
        ],
    },
    "q05": {
        "query_suffix": "（请给出方法、关键数值与稳健性说明）",
        # LLM 曾把 p 值当 HR 并编造 CI：这些数值在金标准/资产中不存在
        "forbidden": {0: ["0.655", "0.761", "0.251", "0.377", "0.127", "0.198", "0.079", "0.124"]},
        "points": [
            ("数值", ["0.679", "0.692"]),
            ("口径", ["OOB"]),
            ("数值", ["pnodes", "0.041"]),
            ("方法", ["pnodes", "progrec"]),
            ("诊断", ["非线性"]),
            ("方法", ["预测重要性"]),
        ],
    },
}

def build():
    eval_set = []
    for qid, spec in KP_SPEC.items():
        gs = json.load(open(GS_DIR / f"{qid}.json", encoding="utf-8"))
        forbidden_map = spec.get("forbidden", {})
        points = [
            {
                "point": kp,
                "asset_type": atype,
                "keywords": kw,
                "or_keywords": orkw or [],   # OR 语义同义词组（命中其一即可）
                "forbidden": forbidden_map.get(i, []),  # 幻觉扫描用
            }
            for i, (kp, (atype, kw, *rest)) in enumerate(
                zip(gs["golden_answer"]["key_points"], spec["points"])
            )
            for orkw in [rest[0] if rest else None]
        ]
        eval_set.append(
            {
                "id": qid,
                "query": gs["question"] + spec["query_suffix"],
                "analysis_target": gs["analysis_target"],
                "required_points": points,
            }
        )
    OUT.write_text(json.dumps(eval_set, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = sum(len(e["required_points"]) for e in eval_set)
    print(f"生成 {OUT.name}：{len(eval_set)} 题 · {n} 检查点")

if __name__ == "__main__":
    build()
