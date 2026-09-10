# -*- coding: utf-8 -*-
"""
biostat_engine.py —— 「AI 生物统计分析师」推理引擎（模拟层）
----------------------------------------------------------
对应 TensorZero 的 Gateway + Function：统一推理入口、结构化输出、全程可观测。

设计要点（面试讲法）：
- 回答不是"模型凭空生成"，而是由【资产层】组合生成：
    口径字典(metrics) + 统计方法知识(knowledge) + 纠错案例(fewshot)
  —— 这正是 JD「需求结构化：把模糊分析需求拆成 AI 可执行的知识结构」。
- asset_level="base"：只有内置初始知识（飞轮转动前，v1）
- asset_level="full" ：含反馈沉淀的学习层资产（飞轮转起来后，v2）
- 确定性引擎模拟大模型：零依赖、可复现；真实场景只需把 answer() 换成一次 LLM 调用。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"

# 关键词 -> 标签：把自然语言统计问题映射到知识结构（简化版需求结构化）
TAG_MAP = {
    "激素治疗": {"cox"},
    "无复发生存": {"生存"},
    "Cox": {"cox"},
    "影响": {"cox"},
    "独立预后": {"cox"},
    "预后因素": {"cox"},
    "estrec": {"estrec"},
    "tgrade": {"tgrade"},
    "编码": {"编码"},
    "线性": {"编码"},
    "PH": {"ph"},
    "违反": {"ph"},
    "分层": {"分层"},
    "随机生存森林": {"rsf"},
    "RSF": {"rsf"},
    "C-index": {"rsf", "vimp"},
    "超越": {"rsf"},
    "稳健性": {"稳健"},
}


class BiostatEngine:
    def __init__(self, asset_level: str = "full"):
        self.asset_level = asset_level
        self.metrics = self._load("metrics.json")
        self.knowledge = self._load("knowledge.json")
        self.fewshot = self._load("fewshot.json")

    def _load(self, name: str):
        with open(ASSET_DIR / name, encoding="utf-8") as f:
            data = json.load(f)
        if self.asset_level == "base":
            data = [e for e in data if e.get("tier", "base") == "base"]
        return data

    @staticmethod
    def _tags_of(query: str) -> set:
        tags: set = set()
        for kw, ts in TAG_MAP.items():
            if kw in query:
                tags |= ts
        return tags or {"通用"}

    @staticmethod
    def _recall(assets, tags: set):
        return [a for a in assets if set(a.get("query_tags", [])) & tags]

    def answer(self, query: str) -> str:
        """一次推理：召回资产 -> 组装结构化回答。"""
        tags = self._tags_of(query)
        metrics = self._recall(self.metrics, tags)
        knowledge = self._recall(self.knowledge, tags)
        fewshot = self._recall(self.fewshot, tags)

        lines = [f"【结论】针对「{query}」，从方法、口径、关键数值与方法学诊断四层回答："]
        lines.append("【方法与口径】")
        if metrics:
            lines += [f"  · {m['name']}：{m['definition']}" for m in metrics]
        else:
            lines.append("  · （无可用口径资产）")
        lines.append("【统计知识与关键数值】")
        if knowledge:
            lines += [f"  · {k['factor']}：{k['detail']}" for k in knowledge]
        else:
            lines.append("  · （无可用方法资产）")
        lines.append("【历史纠错提醒】")
        if fewshot:
            lines += [f"  · {f['lesson']}" for f in fewshot]
        else:
            lines.append("  · （无历史纠错记录）")
        lines.append("【建议】基于上述口径与方法交叉验证，输出统计结论；对模型设定保持审慎。")
        return "\n".join(lines)
