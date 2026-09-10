# -*- coding: utf-8 -*-
"""
feedback.py —— 反馈回流与资产化沉淀
-----------------------------------
对应 TensorZero 的 Observability（反馈采集）与 JD「数据回流与反馈机制、
推动分析经验、指标口径与业务知识的资产化沉淀」。

机制：
1. 业务方/统计评审在真实使用中对 AI 分析结果给出纠错与补充（data/feedback.jsonl）
2. 每条反馈被转成一条可复用资产（口径修正->metrics / 知识补充->knowledge / 案例沉淀->fewshot），
   写入 assets/ 资产文件，tier=learned 并标注 source_feedback 溯源
3. 资产文件即"组织资产台账"：git 里能看到每一版沉淀了什么

本模块是幂等的：资产已存在则跳过，重复运行不会产生脏数据。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"
FEEDBACK_FILE = ROOT / "data" / "feedback.jsonl"

FILE_BY_TYPE = {
    "口径修正": "metrics.json",
    "知识补充": "knowledge.json",
    "案例沉淀": "fewshot.json",
}


def _load_asset_file(name: str):
    with open(ASSET_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _save_asset_file(name: str, data):
    with open(ASSET_DIR / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_feedback():
    records = []
    with open(FEEDBACK_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def apply_feedback(verbose: bool = True):
    """把 feedback.jsonl 逐条沉淀进资产文件，返回台账信息（幂等）。"""
    ledger = []
    for fb in load_feedback():
        fname = FILE_BY_TYPE.get(fb["feedback_type"])
        if fname is None:
            continue
        data = _load_asset_file(fname)
        exists = any(e["id"] == fb["asset_id"] for e in data)
        if not exists:
            entry = {
                "id": fb["asset_id"],
                "name": fb["asset_id"],   # metrics/fewshot 用 name/lesson 字段，knowledge 用 factor
                "factor": fb["asset_id"],
                "definition": fb["comment"],
                "detail": fb["comment"],
                "lesson": fb["comment"],
                "query_tags": fb.get("tags") or _tags_from_comment(fb["comment"]),
                "tier": "learned",
                "source_feedback": fb["id"],
                "note": f"由反馈 {fb['id']}（{fb['source_role']}）沉淀",
            }
            data.append(entry)
            _save_asset_file(fname, data)
        ledger.append(
            {
                "feedback_id": fb["id"],
                "source_role": fb["source_role"],
                "feedback_type": fb["feedback_type"],
                "asset_file": fname,
                "asset_id": fb["asset_id"],
            }
        )
    if verbose:
        for row in ledger:
            print(f"  ✓ {row['feedback_id']} [{row['source_role']}/{row['feedback_type']}] "
                  f"→ {row['asset_file']} #{row['asset_id']}")
    return ledger


def _tags_from_comment(comment: str) -> list:
    """从纠错文本推断资产标签（简化：命中知识关键词即打标签，兜底通用）。"""
    tags = []
    for kw, tag in [
        ("estrec", "estrec"), ("tgrade", "tgrade"), ("PH", "ph"), ("分层", "分层"),
        ("OOB", "oob"), ("ranger", "rsf"), ("randomForestSRC", "rsf"),
        ("tgrade", "编码"), ("非线性", "vimp"), ("预测重要性", "vimp"),
        ("稳健", "稳健"), ("列名", "口径"), ("cens", "口径"),
    ]:
        if kw in comment:
            tags.append(tag)
    return tags or ["通用"]
